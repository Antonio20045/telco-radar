"""Frag das Archiv.

Der Test, der den Auftrag entscheidet, ist
`test_frage_ohne_treffer_erfindet_nichts`: eine Frage, zu der es nichts im
Archiv gibt, muss zu "nichts gefunden" fuehren - nicht zu einer freundlich
formulierten Erfindung.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from telco_radar.report.archiv_dossier import (
    MIND_SCORE, ArchivIndex, als_dict, frage, verlauf, zerlege,
)


def _e(titel: str, summary: str = "", **kw) -> dict:
    d = {"kind": "bericht", "title": titel, "summary": summary,
         "operator": kw.pop("operator", ""), "category": kw.pop("category", ""),
         "source_label": kw.pop("quelle", "presse"),
         "url": kw.pop("url", f"https://x.de/{abs(hash(titel)) % 10000}"),
         "date": kw.pop("date", "2026-08-01")}
    d.update(kw)
    return d


ARCHIV = [
    _e("Telekom hebt den Preis für MagentaMobil L an",
       "Der Grundpreis steigt von 59,95 auf 64,95 Euro.",
       operator="Deutsche Telekom", date="2026-07-04"),
    _e("o2 senkt den Preis für unbegrenzte Tarife",
       "Unlimited Max kostet künftig 10 Euro weniger im Monat.",
       operator="o2", date="2026-07-18"),
    _e("Vodafone bündelt Streaming in den Mobilfunktarif",
       "Ein Streamingdienst liegt dem Tarif bei.",
       operator="Vodafone", date="2026-08-01"),
    _e("1&1 startet Wechselbonus für Neukunden",
       "Bis zu 100 Euro Bonus bei Rufnummernmitnahme.",
       operator="1&1", date="2026-08-05"),
    _e("MTN übernimmt IHS Towers",
       "Der Funkturmbetreiber wechselt den Eigentümer.",
       operator="MTN", date="2026-06-02"),
]


@pytest.fixture(scope="module")
def index() -> ArchivIndex:
    return ArchivIndex(ARCHIV)


# --------------------------------------------------------------------------- #
# Die Zusage des Auftrags
# --------------------------------------------------------------------------- #

def test_frage_ohne_treffer_erfindet_nichts(index):
    """DER Test dieses Moduls.

    Eine freundlich formulierte Nicht-Antwort ist schlimmer als ein
    ehrliches "dazu steht nichts im Archiv": sie kostet dieselbe Zeit und
    hinterlaesst den Eindruck, die Frage sei beantwortet.
    """
    antwort = frage(index, "Wie viele Satelliten hat Starlink über Grönland?")
    assert not antwort.gefunden
    assert antwort.belege == []
    assert "steht nichts im Archiv" in antwort.begruendung


def test_jede_fussnote_zeigt_auf_einen_echten_eintrag(index):
    """Die zweite Zusage: keine Fussnote ohne real existierendes Item."""
    antwort = frage(index, "Preis unbegrenzte Tarife")
    urls = {e["url"] for e in ARCHIV}
    titel = {e["title"] for e in ARCHIV}
    assert antwort.gefunden
    for beleg in antwort.belege:
        assert beleg.url in urls
        assert beleg.titel in titel


def test_die_aussage_ist_der_eintrag(index):
    """Extraktiv, nicht generativ: es gibt keinen Satz, den nicht schon
    jemand belegt geschrieben hat."""
    antwort = frage(index, "Wechselbonus Rufnummernmitnahme")
    quelle = {e["title"]: e["summary"] for e in ARCHIV}
    for beleg in antwort.belege:
        assert beleg.text == quelle[beleg.titel]


def test_leeres_archiv_sagt_das(index):
    antwort = frage(ArchivIndex([]), "Preis")
    assert not antwort.gefunden and "leer" in antwort.begruendung


def test_frage_ohne_begriffe(index):
    antwort = frage(index, "und die was ist")
    assert not antwort.gefunden
    assert "keine durchsuchbaren Begriffe" in antwort.begruendung


# --------------------------------------------------------------------------- #
# BM25: seltene Woerter tragen die Frage
# --------------------------------------------------------------------------- #

def test_seltener_begriff_schlaegt_haeufigen(index):
    """"Wie hat sich der Preis unbegrenzter Tarife entwickelt" enthaelt vier
    haeufige und zwei seltene Woerter - nur die seltenen tragen die Frage."""
    antwort = frage(index, "Wie hat sich der Preis für unbegrenzte Tarife "
                           "entwickelt?")
    assert antwort.belege[0].titel.startswith("o2 senkt den Preis")


def test_treffer_werden_benannt(index):
    antwort = frage(index, "Wechselbonus")
    assert "wechselbonus" in antwort.belege[0].treffer


def test_stoppwoerter_fliegen_raus():
    assert zerlege("Die Frage ist, was der Preis macht") == ["frage", "preis",
                                                             "macht"]


def test_zerlege_vertraegt_leer():
    assert zerlege("") == [] and zerlege(None) == []


def test_haeufiges_wort_bekommt_kein_negatives_gewicht():
    """Ohne den +1 im Logarithmus zoege ein Wort, das in mehr als der Haelfte
    der Eintraege steht, die Treffer nach UNTEN, die es enthalten."""
    viele = [_e(f"Telekom Meldung {i}", "Telekom tut etwas") for i in range(10)]
    idx = ArchivIndex(viele + [_e("Anderes Thema", "Nichts davon")])
    antwort = frage(idx, "Telekom", mind_score=0.0)
    assert antwort.gefunden
    assert all(b.score > 0 for b in antwort.belege)


# Die folgenden vier Tests messen die RANGFOLGE, nicht die Schwelle, und
# arbeiten dafuer mit winzigen Korpora. Dort steht der Suchbegriff in jedem
# Eintrag, also ist sein IDF-Gewicht korrekterweise nahe null und der Score
# bleibt unter MIND_SCORE. Am echten Bestand (737 Eintraege) erreichen echte
# Fragen 6 bis 9 Punkte und eine Unsinnsfrage exakt 0 - die Schwelle wird
# deshalb hier ausgeschaltet und in test_mind_score_ist_wirksam sowie
# test_frage_ohne_treffer_erfindet_nichts eigens geprueft.
OHNE_SCHWELLE = 0.0


def test_lange_eintraege_werden_nicht_bevorzugt():
    kurz = _e("Wechselbonus", "Wechselbonus")
    lang = _e("Langer Eintrag", "Wechselbonus " + "Fuellwort " * 200)
    idx = ArchivIndex([kurz, lang])
    antwort = frage(idx, "Wechselbonus", mind_score=OHNE_SCHWELLE)
    assert antwort.belege[0].titel == "Wechselbonus"


# --------------------------------------------------------------------------- #
# Form der Antwort
# --------------------------------------------------------------------------- #

def test_antwort_ist_gedeckelt(index):
    viele = [_e(f"Preis Meldung {i}", "Preis Preis") for i in range(40)]
    antwort = frage(ArchivIndex(viele), "Preis", max_belege=5,
                    mind_score=OHNE_SCHWELLE)
    assert len(antwort.belege) == 5


def test_dubletten_erscheinen_einmal():
    doppelt = [_e("A", "Wechselbonus", url="https://x.de/1"),
               _e("B", "Wechselbonus", url="https://x.de/1")]
    antwort = frage(ArchivIndex(doppelt), "Wechselbonus",
                    mind_score=OHNE_SCHWELLE)
    assert len(antwort.belege) == 1


def test_bei_gleichstand_zuerst_das_juengere():
    gleich = [_e("Alt", "Wechselbonus", url="https://x.de/1", date="2026-01-01"),
              _e("Neu", "Wechselbonus", url="https://x.de/2", date="2026-08-01")]
    antwort = frage(ArchivIndex(gleich), "Wechselbonus",
                    mind_score=OHNE_SCHWELLE)
    assert antwort.belege[0].titel == "Neu"


def test_verlauf_zaehlt_die_monate(index):
    antwort = frage(index, "Preis Tarif Bonus", mind_score=0.1)
    reihe = verlauf(antwort)
    assert reihe == sorted(reihe, key=lambda p: p["monat"])
    assert sum(p["anzahl"] for p in reihe) == len(antwort.belege)


def test_als_dict_ist_json_faehig(index):
    d = als_dict(frage(index, "Wechselbonus"))
    json.dumps(d)  # wirft, wenn etwas nicht serialisierbar ist
    assert d["gefunden"] is True
    assert d["belege"][0]["url"].startswith("https://")


def test_als_dict_bei_nichts_gefunden(index):
    d = als_dict(frage(index, "Quantenkryptographie auf dem Mond"))
    assert d["gefunden"] is False and d["belege"] == []
    assert d["begruendung"]


def test_mind_score_ist_wirksam(index):
    """Ohne Schwelle kaeme auf jede Frage irgendetwas zurueck."""
    streng = frage(index, "Türme", mind_score=99.0)
    assert not streng.gefunden


# --------------------------------------------------------------------------- #
# Gegen den echten Suchindex
# --------------------------------------------------------------------------- #

def test_laeuft_gegen_den_echten_bestand():
    """Nicht gegen ein Konstrukt: gegen die Meldungen, die wirklich im
    Archiv stehen."""
    pfad = Path(__file__).resolve().parents[1] / "data" / "reports"
    berichte = sorted(pfad.glob("2*.json")) if pfad.exists() else []
    if not berichte:
        pytest.skip("kein Bericht im Archiv")

    from telco_radar.report import suchindex
    bericht = json.loads(berichte[-1].read_text(encoding="utf-8"))
    eintraege = []
    regionen = bericht.get("regions") or {}
    for inhalt in (regionen.values() if isinstance(regionen, dict)
                   else regionen):
        for h in (inhalt or {}).get("highlights") or []:
            eintraege.append(suchindex.eintrag_bericht(h, bericht["date"]))
    if not eintraege:
        pytest.skip("Ausgabe ohne Meldungen")

    idx = ArchivIndex(eintraege)
    # Eine Frage, zu der es nichts geben kann.
    leer = frage(idx, "Unterwasserarchäologie im Bodensee")
    assert not leer.gefunden

    # Eine Frage aus dem Bestand selbst muss sich finden.
    ein_titel = eintraege[0]["title"]
    treffer = frage(idx, ein_titel)
    assert treffer.gefunden
    assert any(b.titel == ein_titel for b in treffer.belege)


# --------------------------------------------------------------------------- #
# Python und Browser muessen dasselbe antworten
# --------------------------------------------------------------------------- #

def _app_js() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "telco_radar" /
            "report" / "templates" / "app.js").read_text(encoding="utf-8")


def test_js_fassung_nutzt_dieselben_konstanten():
    """Die Browserfassung ist eine zweite Umsetzung derselben Rechnung.

    Laufen die Konstanten auseinander, antwortet die Seite anders als der
    Test - und niemand merkt es, weil beide fuer sich gruen sind.
    """
    from telco_radar.report import archiv_dossier as ad
    js = _app_js()
    assert "var K1 = %s, B = %s, MIND_SCORE = %s, MAX_BELEGE = %d;" % (
        ad.K1, ad.B, ad.MIND_SCORE, ad.MAX_BELEGE) in js


def test_js_fassung_kennt_dieselben_stoppwoerter():
    from telco_radar.report import archiv_dossier as ad
    js = _app_js()
    block = js.split("var STOPP = (")[1].split(").split(' ')")[0]
    im_js = set(block.replace("'", "").replace("+", "").split())
    assert im_js == ad.STOPP


def test_js_fassung_sagt_dasselbe_wenn_nichts_gefunden():
    from telco_radar.report import archiv_dossier as ad
    leer = frage(ArchivIndex([]), "x")
    js = _app_js()
    assert "Das Archiv ist leer." in js
    assert leer.begruendung in js
    ohne = frage(ArchivIndex(ARCHIV), "Quantenkryptographie auf dem Mond")
    # Der Satz steht im JS in zwei Zeilen umbrochen - verglichen wird der
    # Anfang, der ihn eindeutig macht.
    assert "Dazu steht nichts im Archiv." in js
    assert ohne.begruendung.startswith("Dazu steht nichts im Archiv.")


def test_suchseite_hat_den_behaelter_fuer_die_antwort():
    tpl = (Path(__file__).resolve().parents[1] / "src" / "telco_radar" /
           "report" / "templates" / "suche.html.j2").read_text(encoding="utf-8")
    assert 'id="dossier-antwort"' in tpl
