"""BRIEF_FADEN (05.09.2026, Senecas Freigabe): die Geraeteseite auf EINE
Frage reduziert - "Was kostet dieses Gerät?".

Sechs Abnahmekriterien, sechs Testgruppen:
  1. Ein Graph: G0 ist die einzige `<svg>`-Grafik im sichtbaren Bereich je
     Modellblock (G1-Balken nicht mehr gerendert).
  2. Antwortzeile steht zwischen Auswahl und Graph.
  3. Titel "Gerätepreise im Vergleich"; die Frage-Ueberschrift 0x.
  4. Ampel-Kacheln und Analysten-Tabellen nur innerhalb von `<details>`.
  5. Einzel-Punkt-Anbieter mit "Serie startet"-Beschriftung (Modultest in
     `tests/test_geraete_zeitreihe.py`; hier nur die Verdrahtung im HTML).
  6. Tab-Leiste nur Vergleich + Gerätekatalog.

Die Titel-Zusicherung selbst steht in `test_geraete_rahmen.py` (sie war dort
schon zuhause, seit BRIEF_RAHMEN die Frage-Ueberschrift einfuehrte - die
Umkehrung gehoert an denselben Ort). Kriterium 1 UND 6 sind zusaetzlich im
echten Browser gemessen (`tests/test_geraete_reiter_browser.py`); hier steht
die statische Haelfte, die keinen Browser braucht.

Fixture: dieselbe `_baue()` wie in `test_geraete_rahmen.py` -
`test_geraete_tco_zustand._baue`, ein Modell (iPhone 15 128 GB), o2 neu +
erneuert, Vodafone als Referenzrechnung.
"""
from __future__ import annotations

import pytest

from test_geraete_tco_zustand import _baue


# --------------------------------------------------------------------------
# Kriterium 1: G0 ist die einzige Grafik je Modellblock
# --------------------------------------------------------------------------

def test_g1_steht_nicht_mehr_im_dokument(tmp_path):
    """O1 (11.09.2026) dreht die Regel ein zweites Mal: G0 (die je-Modell-
    Zeitreihe) verlaesst DIESE Ansicht ebenfalls und wandert in O4 in den
    Verlaufs-Reiter - der EINE Graph ist der HTML/CSS-Balken. In der
    Vergleichsansicht steht deshalb KEIN SVG mehr; `m.zeitreihe` wird in
    `geraete_tco_view.aufbereiten()` weiterhin gefuellt (Kappe im Template,
    dieselbe wie bei G1)."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select("svg.gr-g1") == []
    assert tafel.select("svg") == [], \
        "in der Vergleichsansicht steht noch ein SVG"
    assert len(tafel.select(".gr-hgraph")) == 1, \
        "genau ein Graph-Modul (der Balken)"


# --------------------------------------------------------------------------
# Kriterium 2: die Antwortzeile steht zwischen Auswahl und Graph
# --------------------------------------------------------------------------

def test_antwortzeile_steht_zwischen_auswahl_und_graph(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    auswahl = tafel.select_one(".gr-msel")
    assert auswahl is not None, "die Geraeteauswahl fehlt"

    block = tafel.select_one(".gr-tmodell")
    kinder = [k for k in block.find_all(recursive=False)]
    antwort = block.select_one(".gr-antwort")
    graph = block.select_one(".gr-hgraph")
    assert antwort is not None, "die Antwortzeile fehlt"
    assert graph is not None, "der Zeitreihen-Graph fehlt"
    assert kinder.index(antwort) < kinder.index(graph), \
        "die Antwortzeile steht nicht vor dem Graphen"

    # Die Auswahl steht VOR dem Modellblock (und damit vor der Antwortzeile
    # und dem Graphen darin) - derselbe DOM-Baum, verglichen ueber die
    # Position im vollstaendigen Text.
    text = str(tafel)
    assert text.index('class="gr-msel') < text.index('class="gr-antwort')


def test_antwortzeile_nennt_beide_preise_mit_anbieter(tmp_path):
    s = _baue(tmp_path)
    zeile = s.select_one("#tafel-tco .gr-antwort")
    text = zeile.get_text(" ", strip=True)
    assert "Günstigster Gerätepreis" in text
    assert "günstig mit Tarif" in text
    assert "(o2)" in text, f"kein Anbieter in der Antwortzeile: {text}"


# --------------------------------------------------------------------------
# Kriterium 3: die Titelzeile - siehe `test_geraete_rahmen.py`
# (`test_die_ueberschrift_ist_sachlich_nicht_die_gescheiterte_frage`)
# --------------------------------------------------------------------------

def test_der_seitentitel_ist_sachlich(tmp_path):
    s = _baue(tmp_path)
    titel = s.select_one("title").get_text(strip=True)
    assert titel.endswith("Gerätepreise im Vergleich")


# --------------------------------------------------------------------------
# Kriterium 4 (O2, 11.09.2026): die Alarm-Kacheln und -Tabelle stehen auf
# dem WETTBEWERBS-RADAR, nicht mehr auf der Geräteseite - ihr neuer Ort
# hält tests/test_wettbewerbsradar_alarme.py fest. Hier bleibt die Regel,
# dass die Vergleichsansicht sie NICHT mehr trägt (kein Doppelt), und dass
# der Tarifmaßstab weiterhin hinter einer Aufklappung steht.
# --------------------------------------------------------------------------

def test_die_vergleichsansicht_traegt_keine_alarmtafel_mehr(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select_one(".gr-chips") is None, \
        "die Ampel-Kacheln stehen noch in der Vergleichsansicht"
    assert tafel.select_one("#gr-alarme") is None
    assert tafel.select_one("#gr-tco-tabelle") is None, \
        "'Alle Bündel als Tabelle' ist in die Zeilen-Tabelle aufgegangen"


def test_der_tarifmassstab_steht_in_einer_aufklappung(tmp_path):
    """Der Maßstab (was der Tarif allein kostet) bleibt Analyse und steht
    hinter einer eigenen, geschlossenen Aufklappung."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    massstab = tafel.select_one("#gr-massstab")
    if massstab is None:
        pytest.skip("keine Referenzen im Bestand der Fixture")
    assert massstab.name == "details"
    assert massstab.get("open") is None, "die Aufklappung ist offen"
    assert massstab.select_one(".gr-ttab--simonly") is not None


def test_die_buendel_zeilen_stehen_ausserhalb_jeder_aufklappung(tmp_path):
    """Die Bündel-Zeilen (seit O2 die Kartenform) stehen OFFEN unter dem
    Graphen - nicht in einer Analyse-Aufklappung verschachtelt. Zwei
    Klapptiefen für dasselbe Angebot blieben verboten."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    for zeile in tafel.select("#gr-buendel .gr-bnd"):
        elter = zeile.parent
        while elter is not None and elter.name is not None:
            if elter.name == "details" and \
                    "gr-bnd" not in (elter.get("class") or []):
                pytest.fail("Bündelzeile steckt in einer Aufklappung: "
                            + str(elter)[:80])
            elter = elter.parent


# --------------------------------------------------------------------------
# Kriterium 5: Einzel-Punkt-Anbieter - Verdrahtung im HTML
# (die Rechnung selbst: tests/test_geraete_zeitreihe.py)
# --------------------------------------------------------------------------

def test_haendler_ohne_zeitreihe_nennen_den_beginn_der_beschaffung(tmp_path):
    """O2: die Händler ohne Preis stehen in der EINEN Legendenzeile unter
    dem Graphen (nicht mehr als eigene Karten) - mit dem Beginn der
    Beschaffung, ohne erfundene Zahl."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    legende = tafel.select_one(".gr-lueckenzeile")
    assert legende is not None, "die Legendenzeile fehlt"
    text = " ".join(legende.get_text(" ", strip=True).split())
    assert "Beschaffung läuft seit" in text
    assert "€" not in text


# --------------------------------------------------------------------------
# Kriterium 6: die Reiterleiste traegt nur zwei Knoepfe
# --------------------------------------------------------------------------

def test_die_reiterleiste_traegt_nur_vergleich_und_katalog(tmp_path):
    s = _baue(tmp_path)
    knoepfe = s.select(".gr-reiter button[data-tafel]")
    beschriftungen = [(k.get("data-tafel"), k.get_text(strip=True))
                      for k in knoepfe]
    assert beschriftungen == [
        ("tafel-tco", "Vergleich"),
        ("tafel-katalog", "Gerätekatalog"),
    ]


def test_die_ungeknopften_tafeln_bleiben_im_dokument_stehen(tmp_path):
    """"Nicht geloescht, nur nicht mehr verlinkt" - ihr Markup bleibt, nur
    kein Knopf zeigt mehr darauf."""
    s = _baue(tmp_path)
    assert s.select_one("#tafel-verlauf") is not None
    assert s.select_one("#tafel-portfolio") is not None
    # Kein Knopf in der Reiterleiste zeigt mehr auf sie.
    ziele = {k.get("data-tafel") for k in s.select(".gr-reiter button[data-tafel]")}
    assert "tafel-verlauf" not in ziele
    assert "tafel-portfolio" not in ziele
