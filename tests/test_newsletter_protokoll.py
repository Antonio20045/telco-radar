"""Der Newsletter-Abschnitt der Quellenseite. Nur Zahlen, nie Adressen.

Der Abschnitt ist die Antwort auf das Premortem-Risiko "niemand pflegt es":
nach acht Wochen prueft keiner mehr Zustellquote, Rueckläufer und
Abmeldungen. Ein eigenes Dashboard waere ein zweiter Ort, an den niemand
geht - also steht es dort, wo in diesem Projekt ohnehin nachgesehen wird.

Jede Zahl auf einer Seite ist erst wahr, wenn ein Test sie gegen die Daten
haelt (CLAUDE.md §6). Deshalb prueft dieser Test nicht nur, DASS die Tabelle
steht, sondern dass ihre Werte aus der Statistikdatei stammen.
"""
import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from telco_radar.report import newsletter_protokoll as np
from telco_radar.report.html import render_site

WURZEL = Path(__file__).resolve().parents[1]

LAEUFE = [
    {"date": "2026-08-11", "segments": 12, "planned": 200, "delivered": 198,
     "skipped": 0, "failed": 2, "hard_fail": 1, "limit_left": 80,
     "new": 4, "unsubscribed": 1, "bounced": 1},
    {"date": "2026-08-08", "segments": 10, "planned": 150, "delivered": 150,
     "skipped": 0, "failed": 0, "hard_fail": 0, "limit_left": 130,
     "new": 9, "unsubscribed": 0, "bounced": 0},
]


def _stats(tmp_path, laeufe=None):
    pfad = tmp_path / "data" / "state" / "newsletter_stats.jsonl"
    for lauf in (laeufe if laeufe is not None else LAEUFE):
        np.vermerken(pfad, lauf)
    return pfad


# ============================================================  Rechnen  ====

def test_die_zustellquote_rechnet_gegen_die_versuchten(tmp_path):
    ausgaben = np.lade(_stats(tmp_path))
    assert ausgaben[0].datum == "2026-08-11"        # juengste zuerst
    assert ausgaben[0].zustellquote == round(198 / 200, 4)
    assert ausgaben[0].quote_prozent == 99


def test_uebersprungene_zaehlen_nicht_als_versuch(tmp_path):
    """Ein Wiederanlauf ueberspringt, was schon draussen ist. Als Versuch
    gezaehlt saehe eine perfekte Wiederholung wie ein Totalausfall aus."""
    pfad = _stats(tmp_path, [{"date": "2026-08-11", "planned": 200,
                              "skipped": 200, "delivered": 0}])
    assert np.lade(pfad)[0].zustellquote == 1.0


def test_die_auslastung_rechnet_gegen_das_tageslimit(tmp_path):
    ausgaben = np.lade(_stats(tmp_path))
    # 300 - 80 = 220 gebraucht -> 73 %
    assert ausgaben[0].auslastung == 73
    assert ausgaben[1].auslastung == 57


# ==========================================================  Warnungen  ====

def test_eine_niedrige_zustellquote_warnt(tmp_path):
    pfad = _stats(tmp_path, [{"date": "2026-08-11", "planned": 100,
                              "delivered": 90, "limit_left": 200}])
    warnungen = " ".join(np.lade(pfad)[0].warnungen)
    assert "90 %" in warnungen


def test_mehr_als_drei_harte_fehler_warnen(tmp_path):
    pfad = _stats(tmp_path, [{"date": "2026-08-11", "planned": 100,
                              "delivered": 96, "hard_fail": 4,
                              "limit_left": 200}])
    assert any("dauerhaft" in w for w in np.lade(pfad)[0].warnungen)


def test_ab_achtzig_prozent_des_kontingents_wird_gewarnt(tmp_path):
    """Die Warnung, die im Alltag ZUERST anschlaegt: 300/Tag ist die
    Verteilerobergrenze, nicht eine ferne Grenze."""
    pfad = _stats(tmp_path, [{"date": "2026-08-11", "planned": 240,
                              "delivered": 240, "limit_left": 40}])
    warnungen = np.lade(pfad)[0].warnungen
    assert any("87 %" in w and "300" in w for w in warnungen), warnungen
    assert any("Ausbaustufe B" in w for w in warnungen)


def test_ein_gesunder_lauf_warnt_nicht(tmp_path):
    """Die Gegenprobe - ohne sie belegen die Tests oben nur, dass IMMER
    gewarnt wird."""
    pfad = _stats(tmp_path, [{"date": "2026-08-11", "planned": 100,
                              "delivered": 100, "limit_left": 180}])
    assert np.lade(pfad)[0].warnungen == []


def test_die_schwellen_stimmen_mit_dem_versandmodul_ueberein():
    """Zwei Zahlen fuer dasselbe Limit waeren zwei Limits - und die
    strengere gaebe es nur an einer Stelle."""
    from telco_radar.newsletter import versand as v
    assert np.TAGESLIMIT == v.TAGESLIMIT == 300
    assert v.SCHWELLE < np.TAGESLIMIT


# =======================================================  Kein Personenbezug

def test_vermerken_uebernimmt_nur_die_bekannten_felder(tmp_path):
    """Der Payload kommt aus einem anderen Repo. Ein Feld mehr darf nicht
    bedeuten, dass eine Adresse ins oeffentliche Repo wandert."""
    pfad = tmp_path / "stats.jsonl"
    np.vermerken(pfad, {"date": "2026-08-11", "delivered": 5,
                        "email": "wer@beispiel.test",
                        "empfaenger": ["a@b.test", "c@d.test"]})
    inhalt = pfad.read_text(encoding="utf-8")
    assert "beispiel.test" not in inhalt
    zeile = json.loads(inhalt)
    assert set(zeile) == {"date", "segments", "planned", "delivered",
                          "skipped", "failed", "hard_fail", "limit_left",
                          "new", "unsubscribed", "bounced"}


def test_alles_wird_zu_zahlen(tmp_path):
    """Ein Textfeld im Payload wuerde sonst unveraendert in der Datei
    landen - und von dort auf die Seite."""
    pfad = tmp_path / "stats.jsonl"
    np.vermerken(pfad, {"date": "2026-08-11", "delivered": "wer@b.test"})
    assert json.loads(pfad.read_text(encoding="utf-8"))["delivered"] == 0


def test_ohne_datum_kein_eintrag(tmp_path):
    with pytest.raises(ValueError):
        np.vermerken(tmp_path / "stats.jsonl", {"delivered": 5})


def test_die_statistikdatei_des_repos_traegt_keine_adresse():
    """Der CI-Test aus dem Konzept. Zweite Sicherung nach der Filterung -
    sie kostet nichts und faengt den Fall, in dem jemand `vermerken()`
    erweitert."""
    pfad = WURZEL / "data" / "state" / "newsletter_stats.jsonl"
    if not pfad.exists():
        pytest.skip("noch kein Versandlauf")
    muster = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
    assert not muster.search(pfad.read_text(encoding="utf-8"))


# ==============================================================  Seite  ====

def _render(tmp_path, laeufe=None):
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    if laeufe is not None:
        _stats(tmp_path, laeufe)
    else:
        _stats(tmp_path)
    site = tmp_path / "site"
    render_site(site, reports, cfg=None)
    return site


def test_der_abschnitt_zeigt_die_zahlen_der_datei(tmp_path):
    """Jede Zahl auf einer Seite ist erst wahr, wenn ein Test sie gegen die
    Daten haelt."""
    site = _render(tmp_path)
    soup = BeautifulSoup((site / "transparenz.html").read_text(encoding="utf-8"),
                         "html.parser")
    kopf = [k for k in soup.select(".card-head h2")
            if "Newsletter" in k.get_text()]
    assert kopf, "kein Newsletter-Abschnitt"
    karte = kopf[0].find_parent(class_="card")
    zeilen = karte.select(".rowtable-row")
    assert len(zeilen) == len(LAEUFE)
    werte = [s.get_text(strip=True) for s in zeilen[0].select("span")]
    # Ausgabe, Segmente, Zugestellt, Fehler, Rueckläufer, Abmeldungen, Quote, Limit
    assert werte[1] == "12" and werte[2] == "198" and werte[3] == "2"
    assert werte[4] == "1" and werte[5] == "1"
    assert werte[6] == "99 %"
    assert "80" in werte[7]


def test_ohne_versandlauf_steht_der_abschnitt_nicht_da(tmp_path):
    """Der Normalzustand vor der Einrichtung. Ein leerer Abschnitt mit
    lauter Nullen behauptet einen Versand, den es nicht gab."""
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    site = tmp_path / "site"
    render_site(site, reports, cfg=None)
    assert "Newsletter-Versand" not in (
        site / "transparenz.html").read_text(encoding="utf-8")


def test_die_warnung_steht_ueber_der_tabelle(tmp_path):
    site = _render(tmp_path, [{"date": "2026-08-11", "planned": 260,
                               "delivered": 240, "hard_fail": 5,
                               "limit_left": 40}])
    soup = BeautifulSoup((site / "transparenz.html").read_text(encoding="utf-8"),
                         "html.parser")
    warn = soup.select_one(".nl-prot-warn")
    assert warn is not None and len(warn.select("p")) == 3
    tabelle = soup.select_one(".nl-prot-warn ~ .rowtable")
    assert tabelle is not None, "die Warnung steht nicht vor der Tabelle"


def test_auf_der_seite_steht_keine_adresse(tmp_path):
    site = _render(tmp_path)
    text = (site / "transparenz.html").read_text(encoding="utf-8")
    karte = BeautifulSoup(text, "html.parser")
    kopf = [k for k in karte.select(".card-head h2") if "Newsletter" in k.get_text()]
    abschnitt = kopf[0].find_parent(class_="card").get_text(" ", strip=True)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", abschnitt, re.I)


def test_eine_kaputte_zeile_kippt_die_seite_nicht(tmp_path):
    pfad = tmp_path / "data" / "state" / "newsletter_stats.jsonl"
    pfad.parent.mkdir(parents=True)
    pfad.write_text('{"date":"2026-08-11","delivered":5}\nKAPUTT\n',
                    encoding="utf-8")
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    site = tmp_path / "site"
    render_site(site, reports, cfg=None)
    assert "Newsletter-Versand" in (
        site / "transparenz.html").read_text(encoding="utf-8")
