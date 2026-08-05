"""Quellenregister und automatische Quarantaene.

Kriterien 12 und 13 aus AUFTRAG_SKALIERUNG_1000.md. Der Kern ist nicht die
Buchhaltung, sondern die Frage, ob eine stillgelegte Quelle je zurueckkommt:
eine Quarantaene ohne Bewaehrungsabruf waere eine Falle. Telecompetitor
antwortet mal mit 403 und mal mit 200 - eine Quelle, die nach sechs schlechten
Laeufen nie wieder probiert wird, waere dauerhaft weg, obwohl ihr Server nur
zeitweise dicht war.
"""
from __future__ import annotations

import json

from telco_radar.collect import collect_all
from telco_radar.config import Source
from telco_radar.quellen_register import (
    PROBE_ALLE_LAEUFE, Quellenregister, quellen_der_config)


def _ergebnis(url="https://a.de/feed", status="ok", count=5, new=2, **kw):
    return {"name": "Alpha", "url": url, "status": status, "count": count,
            "new": new, "origin": "operator", "kind": "rss",
            "region": "europa", **kw}


def _lauf(register, tag, **kw):
    return register.verbuche_lauf([_ergebnis(**kw)], f"2026-08-{tag:02d}")


def test_erster_lauf_legt_den_eintrag_an(tmp_path):
    r = Quellenregister(tmp_path / "reg.json")
    _lauf(r, 1)
    e = r.eintrag("https://a.de/feed")
    assert e.erster_lauf == "2026-08-01"
    assert e.letzter_erfolg == "2026-08-01"
    assert (e.laeufe, e.erfolge, e.meldungen_gesamt, e.neu_gesamt) == (1, 1, 5, 2)


def test_zaehler_summieren_ueber_laeufe(tmp_path):
    r = Quellenregister(tmp_path / "reg.json")
    for tag in (1, 4, 8):
        _lauf(r, tag)
    e = r.eintrag("https://a.de/feed")
    assert (e.laeufe, e.erfolge, e.meldungen_gesamt) == (3, 3, 15)
    assert e.erfolgsquote == 1.0


def test_quarantaene_nach_sechs_leeren_laeufen(tmp_path):
    r = Quellenregister(tmp_path / "reg.json")
    for tag in range(1, 6):
        _lauf(r, tag, status="empty", count=0, new=0)
        assert not r.eintrag("https://a.de/feed").in_quarantaene
    zusammenfassung = _lauf(r, 6, status="empty", count=0, new=0)

    e = r.eintrag("https://a.de/feed")
    assert e.in_quarantaene and e.quarantaene_seit == "2026-08-06"
    assert "6 Laeufe ohne Meldung" in e.quarantaene_grund
    assert zusammenfassung["neu_stillgelegt"] == ["https://a.de/feed"]


def test_status_ok_ohne_meldungen_zaehlt_als_ausfall(tmp_path):
    """Eine Quelle, die 200 antwortet und nichts liefert, ist genauso tot."""
    r = Quellenregister(tmp_path / "reg.json")
    for tag in range(1, 7):
        _lauf(r, tag, status="ok", count=0, new=0)
    assert r.eintrag("https://a.de/feed").in_quarantaene


def test_ein_erfolg_setzt_die_fehlserie_zurueck(tmp_path):
    r = Quellenregister(tmp_path / "reg.json")
    for tag in range(1, 6):
        _lauf(r, tag, status="fail", count=0, new=0, error="403")
    _lauf(r, 6)  # ein Erfolg
    assert r.eintrag("https://a.de/feed").fehlserie == 0
    for tag in range(7, 12):
        _lauf(r, tag, status="fail", count=0, new=0)
    assert not r.eintrag("https://a.de/feed").in_quarantaene


def test_stillgelegte_quelle_wird_nicht_abgerufen(tmp_path):
    r = Quellenregister(tmp_path / "reg.json")
    for tag in range(1, 7):
        _lauf(r, tag, status="fail", count=0, new=0)
    assert r.wird_abgerufen("https://a.de/feed") is False
    assert r.wird_abgerufen("https://unbekannt.de/feed") is True


def test_bewaehrungsabruf_nach_zehn_laeufen(tmp_path):
    """Ohne das waere die Quarantaene eine Falle statt einer Massnahme."""
    r = Quellenregister(tmp_path / "reg.json")
    for tag in range(1, 7):
        _lauf(r, tag, status="fail", count=0, new=0)
    assert not r.wird_abgerufen("https://a.de/feed")

    # Laeufe, in denen die Quelle gar nicht vorkommt (weil uebersprungen)
    for _ in range(PROBE_ALLE_LAEUFE):
        r.verbuche_lauf([], "2026-09-01")
    assert r.wird_abgerufen("https://a.de/feed") is True


def test_erfolg_hebt_die_quarantaene_auf(tmp_path):
    r = Quellenregister(tmp_path / "reg.json")
    for tag in range(1, 7):
        _lauf(r, tag, status="fail", count=0, new=0)
    assert r.eintrag("https://a.de/feed").in_quarantaene

    zusammenfassung = _lauf(r, 20)
    e = r.eintrag("https://a.de/feed")
    assert not e.in_quarantaene and e.quarantaene_grund == ""
    assert zusammenfassung["rehabilitiert"] == ["https://a.de/feed"]
    assert r.wird_abgerufen("https://a.de/feed")


def test_register_ueberlebt_das_speichern(tmp_path):
    pfad = tmp_path / "reg.json"
    r = Quellenregister(pfad)
    for tag in range(1, 7):
        _lauf(r, tag, status="fail", count=0, new=0)
    r.speichern()

    wieder = Quellenregister(pfad)
    e = wieder.eintrag("https://a.de/feed")
    assert e.in_quarantaene and e.laeufe == 6
    assert not wieder.wird_abgerufen("https://a.de/feed")


def test_defektes_register_blockiert_den_lauf_nicht(tmp_path):
    pfad = tmp_path / "reg.json"
    pfad.write_text("{kaputt", encoding="utf-8")
    r = Quellenregister(pfad)
    assert len(r) == 0
    _lauf(r, 1)
    assert len(r) == 1


def test_unbekannte_felder_im_register_stoeren_nicht(tmp_path):
    """Ein aelteres oder neueres Format darf den Lauf nicht abbrechen."""
    pfad = tmp_path / "reg.json"
    pfad.write_text(json.dumps({"quellen": {"https://a.de/feed": {
        "url": "https://a.de/feed", "laeufe": 3, "irgendwas_neues": 42}}}),
        encoding="utf-8")
    assert Quellenregister(pfad).eintrag("https://a.de/feed").laeufe == 3


def test_redaktionelle_angaben_kommen_aus_der_konfiguration(tmp_path):
    class Cfg:
        operators = []
        news_sources = [Source(type="rss", url="https://a.de/feed", name="Alpha",
                               herkunft="muster:cision", abgenommen="2026-08-05")]
        tech_sources = []

    r = Quellenregister(tmp_path / "reg.json")
    r.verbuche_lauf([_ergebnis()], "2026-08-05",
                    quellen_der_config=quellen_der_config(Cfg()))
    e = r.eintrag("https://a.de/feed")
    assert e.herkunft == "muster:cision" and e.abgenommen == "2026-08-05"


# ------------------------------------------------- Zusammenspiel mit collect

class _Cfg:
    def __init__(self, urls):
        self.settings = {"collect_max_workers": 2}
        self.operators = []
        self.news_sources = [Source(type="rss", url=u, name=f"Q{i}",
                                    kind="trade_press")
                             for i, u in enumerate(urls)]
        self.tech_sources = []


def test_sammelphase_ueberspringt_stillgelegte_quellen(monkeypatch, tmp_path):
    from telco_radar.models import Item
    import telco_radar.collect as collect_mod

    monkeypatch.setattr(collect_mod, "collect_rss",
                        lambda s, *a, **k: [Item(title="Meldung",
                                                 url=s.url + "/1",
                                                 source_name="Q")])
    r = Quellenregister(tmp_path / "reg.json")
    for tag in range(1, 7):
        r.verbuche_lauf([_ergebnis(url="https://tot.de/feed", status="fail",
                                   count=0, new=0)], f"2026-08-{tag:02d}")

    items, results = collect_all(
        _Cfg(["https://lebt.de/feed", "https://tot.de/feed"]), register=r)

    assert len(items) == 1
    status = {r_["url"]: r_["status"] for r_ in results}
    assert status["https://lebt.de/feed"] == "ok"
    assert status["https://tot.de/feed"] == "quarantaene"


def test_ohne_register_wird_nichts_uebersprungen(monkeypatch):
    import telco_radar.collect as collect_mod
    monkeypatch.setattr(collect_mod, "collect_rss", lambda *a, **k: [])
    _, results = collect_all(_Cfg(["https://a.de/feed"]))
    assert results[0]["status"] == "empty"
