"""Push statt Pull (src/telco_radar/versand.py).

Der Kanal, an dem so etwas stirbt, ist nicht der technische - es ist die
Schwelle. Ein Empfaenger, der zweimal dieselbe Mail bekommt oder taeglich
eine Teams-Meldung, schaltet den Kanal stumm, und ein stummgeschalteter
Kanal ist schlimmer als keiner: er erweckt den Eindruck von Zustellung.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from telco_radar import versand


def _report(highlights, datum="2026-08-10"):
    return {"date": datum,
            "stats": {"new": 100, "events": 90, "sources_total": 207},
            "regions": {"Europa": {"highlights": highlights}}}


def _h(**kw):
    basis = {"title": "Titel", "headline": "Schlagzeile", "url": "https://x.test/1",
             "operator": "Deutsche Telekom", "relevance": 5, "ctm_bezug": 3,
             "ctm_satz": "Drückt unsere Preisuntergrenze deutlich nach unten.",
             "source": "teltarif"}
    basis.update(kw)
    return basis


# ------------------------------------------------------------------- Inhalt

def test_die_mail_zeigt_genau_den_zwei_minuten_pfad():
    """Eine Mail, die etwas anderes hervorhebt als die Seite, auf die sie
    verlinkt, ist schlimmer als keine Mail - deshalb dieselbe Funktion."""
    r = _report([_h(url="https://x.test/1"),
                 _h(url="https://x.test/2", operator="O2",
                    ctm_satz="Zwingt uns zu einer Antwort beim Anschlusspreis."),
                 _h(url="https://x.test/3", ctm_bezug=1, operator="Jio")])
    betreff, text, html = versand.baue_mail(r)
    assert "Preisuntergrenze" in text and "Anschlusspreis" in text
    assert "Jio" not in text            # Stufe 1 gehoert nicht hinein
    assert "https://x.test/1" in text
    assert "telco-radar.onrender.com" in text


def test_leere_lage_wird_als_befund_geschrieben():
    """Eine Woche ohne direkte Portfoliofrage ist ein Befund. Die Mail sagt
    das - sie faellt nicht aus und sie fuellt auch nichts auf."""
    betreff, text, html = versand.baue_mail(_report([_h(ctm_bezug=1)]))
    assert "nichts Direktes" in betreff
    assert "keine Meldung mit direktem Bezug" in text


def test_die_mail_hat_immer_eine_textfassung():
    """Ohne sie steht in der Vorschau des Mailprogramms "Diese Nachricht kann
    nicht angezeigt werden"."""
    _, text, html = versand.baue_mail(_report([_h()]))
    assert text.strip() and "<" not in text.split("http")[0]
    assert html.startswith("<div")


def test_html_wird_maskiert():
    r = _report([_h(operator="Tarif & <script>alert(1)</script>")])
    _, _, html = versand.baue_mail(r)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ------------------------------------------------------------------ Schwelle

def test_teams_nur_bei_beiden_bedingungen():
    r = _report([
        _h(url="https://x.test/a", ctm_bezug=3, relevance=5),   # ja
        _h(url="https://x.test/b", ctm_bezug=3, relevance=4),   # nein
        _h(url="https://x.test/c", ctm_bezug=2, relevance=5),   # nein
    ])
    assert [h["url"] for h in versand.ausnahmen(r)] == ["https://x.test/a"]


def test_mail_nur_am_versandtag():
    assert versand.ist_versandtag(date(2026, 8, 10), 0)     # ein Montag
    assert not versand.ist_versandtag(date(2026, 8, 11), 0)


def test_kein_versandtag_heisst_keine_mail(tmp_path, monkeypatch):
    monkeypatch.setattr(versand, "sende_mail",
                        lambda *a, **k: pytest.fail("kein Versandtag"))
    bilanz = versand.versende(tmp_path, _report([_h()], datum="2026-08-11"),
                              {"versand": {"mail_aktiv": True,
                                           "teams_aktiv": False}})
    assert "kein Versandtag" in bilanz["mail"]


# ------------------------------------------------------- Zustellgedaechtnis

def test_dieselbe_ausgabe_geht_nur_einmal_hinaus(tmp_path, monkeypatch):
    gesendet = []
    monkeypatch.setattr(versand, "sende_mail",
                        lambda *a, **k: gesendet.append(1) or "ok")
    cfg = {"versand": {"mail_aktiv": True, "teams_aktiv": False}}
    r = _report([_h()], datum="2026-08-10")     # Montag
    versand.versende(tmp_path, r, cfg)
    versand.versende(tmp_path, r, cfg)
    assert len(gesendet) == 1


def test_dieselbe_ausnahme_geht_nur_einmal_hinaus(tmp_path, monkeypatch):
    gesendet = []
    monkeypatch.setattr(versand, "sende_teams",
                        lambda *a, **k: gesendet.append(1) or "ok")
    cfg = {"versand": {"mail_aktiv": False, "teams_aktiv": True}}
    versand.versende(tmp_path, _report([_h()]), cfg)
    # zweiter Lauf, dieselbe Meldung plus eine neue
    versand.versende(tmp_path, _report([_h(), _h(url="https://x.test/neu")]), cfg)
    assert len(gesendet) == 2
    buch = json.loads((tmp_path / "data" / "state" / "versand.json")
                      .read_text(encoding="utf-8"))
    assert set(buch["teams"]) == {"https://x.test/1", "https://x.test/neu"}


# ----------------------------------------------------------- Fehlerverhalten

def test_fehlende_zugangsdaten_werden_gemeldet_nicht_verschwiegen(monkeypatch):
    """Ein stiller Nichtversand ist der Fehler, den man erst nach Wochen
    bemerkt."""
    for name in ("SMTP_HOST", "MAIL_FROM", "MAIL_TO"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(versand.VersandFehler):
        versand.sende_mail("b", "t", "<p>h</p>")


def test_ein_versandfehler_steht_in_der_bilanz(tmp_path, monkeypatch):
    def kaputt(*a, **k):
        raise versand.VersandFehler("SMTP: Verbindung abgelehnt")

    monkeypatch.setattr(versand, "sende_mail", kaputt)
    bilanz = versand.versende(tmp_path, _report([_h()], datum="2026-08-10"),
                              {"versand": {"mail_aktiv": True,
                                           "teams_aktiv": False}})
    assert bilanz["mail"].startswith("FEHLER")


def test_trockenlauf_verschickt_nichts(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail.test")
    monkeypatch.setenv("MAIL_FROM", "a@test")
    monkeypatch.setenv("MAIL_TO", "b@test")
    monkeypatch.setattr(versand.smtplib, "SMTP",
                        lambda *a, **k: pytest.fail("trocken heißt trocken"))
    bilanz = versand.versende(tmp_path, _report([_h()], datum="2026-08-10"),
                              {"versand": {"mail_aktiv": True,
                                           "teams_aktiv": False}},
                              trocken=True)
    assert "trocken" in bilanz["mail"]
    # ... und merkt sich nichts, sonst bliebe der echte Versand aus.
    assert not (tmp_path / "data" / "state" / "versand.json").exists()
