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

from bs4 import BeautifulSoup

from test_geraete_tco_zustand import _baue


# --------------------------------------------------------------------------
# Kriterium 1: G0 ist die einzige Grafik je Modellblock
# --------------------------------------------------------------------------

def test_der_eine_graph_ist_die_zeitreihe(tmp_path):
    """E2 (16.09.2026) dreht die Regel ein drittes Mal - diesmal auf
    Antonios ausdrueckliche Entscheidung (AUFTRAG_GERAETE_EINE_SEITE_V2
    §1a): der EINE Graph der Vergleichsansicht ist DIE TCO-ZEITREIHE, ein
    SVG-Koordinatensystem mit Punkten je Messung. Die Balkenform (O1) ist
    ERSETZT: .gr-hgraph und .gr-bz sind Reste, G1 bleibt verboten; G0
    wohnt weiter im Verlaufs-Reiter."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select("svg.gr-g1") == []
    for rest in (".gr-hgraph", ".gr-bz", ".gr-balkenliste"):
        assert tafel.select(rest) == [], f"Rest der Balkenform: {rest}"
    assert tafel.select_one("svg.gr-g0") is None
    svgs = tafel.select("svg.gr-zr")
    assert svgs, "die Zeitreihe fehlt"
    for svg in svgs:
        assert svg.select("circle.gr-zr-punkt"), "SVG ohne Messpunkte"


# --------------------------------------------------------------------------
# Kriterium 2: die Antwortzeile steht zwischen Auswahl und Graph
# --------------------------------------------------------------------------

def test_antwortzeile_steht_zwischen_auswahl_und_graph(tmp_path):
    """E2: dieselbe Invariante am neuen Aufbau - Wahl-Leiste, dann der
    Antwort-Satz, dann der Graph (§4.2: nichts dazwischen)."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    auswahl = tafel.select_one("#gr-zr-wahl")
    assert auswahl is not None, "die Wahl-Leiste fehlt"
    antwort = tafel.select_one(".gr-zr-antwort")
    graph = tafel.select_one(".gr-zr-graph")
    assert antwort is not None, "der Antwort-Satz fehlt"
    assert graph is not None, "der Zeitreihen-Graph fehlt"
    text = str(tafel)
    assert text.index('id="gr-zr-wahl"') < \
        text.index('class="gr-zr-antwort"') < \
        text.index('class="gr-zr-graph"')


def test_der_antwort_satz_nennt_anbieter_und_loest_tco24_auf(tmp_path):
    """E2 ersetzt die zwei Leitzahlen der alten Antwortzeile durch den
    EINEN Antwort-Satz des Prototyps: Geraet, Band, bester Anbieter,
    TCO-24 - und das Wort TCO-24 wird im Satz selbst aufgeloest (§4.9).
    Der Geraetepreis ohne Vertrag steht weiterhin auf jeder Bündel-Zeile."""
    s = _baue(tmp_path)
    satz = s.select_one("#tafel-tco .gr-zr-antwort")
    assert satz is not None, "der Antwort-Satz fehlt"
    text = " ".join(satz.get_text(" ", strip=True).split())
    assert "über 24 Monate (TCO-24)" in text, text
    assert "€" in text
    assert any(a in text for a in ("o2", "Vodafone", "1&1", "congstar")), \
        f"kein Anbieter im Antwort-Satz: {text}"


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
    # E2: der Massstab wohnt im EINEN Fuss-Aufklapper "Massstab &
    # Datenlage" (§3.1c) - zwei eigene Aufklapper waeren die Verdopplung.
    massstab = tafel.select_one("#gr-massstab-datenlage")
    if massstab is None or massstab.select_one(".gr-ttab--simonly") is None:
        pytest.skip("keine Referenzen im Bestand der Fixture")
    assert massstab.name == "details"
    assert massstab.get("open") is None, "die Aufklappung ist offen"
    assert tafel.select_one("#gr-massstab") is None, \
        "der Massstab steht doppelt (alter Aufklapper zurueckgekehrt)"


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

def test_haendler_ohne_preis_stehen_nicht_einzeln_da(tmp_path):
    """E2 (Antonio 9b.7 + §3.1): die 'Beschaffung läuft'-Legende ist mit
    der Balkenform gefallen. Ein Händler OHNE Preis ist kein Bündel-
    Anbieter - er steht nicht einzeln da (die Quellenseite nennt die
    Beschaffung, der Katalog die Listungen). Der Lückensatz unter dem
    Graphen nennt NUR den Anbieterkreis der Bündel."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    kopie = BeautifulSoup(str(tafel), "html.parser")
    for k in kopie.select("script"):
        k.decompose()
    text = kopie.get_text(" ")
    assert "Beschaffung läuft" not in text
    for name in ("Amazon", "Expert"):
        assert name not in text, f"{name} steht einzeln in der Lesefläche"


# --------------------------------------------------------------------------
# Kriterium 6: die Reiterleiste (E3: vier echte Tafeln auf EINER Seite)
# --------------------------------------------------------------------------

def test_die_reiterleiste_traegt_vergleich_radar_verlauf_katalog(tmp_path):
    """E3 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1d): vier echte Tafeln in der
    Folge Vergleich · Radar · Preisverlauf · Gerätekatalog. Bis E3 war
    der Radar ein Link auf wettbewerbsradar.html (O3-Quasi-Reiter); der
    wird durch die Tafel DIESER Seite ersetzt - deshalb darf kein Link
    mehr in der Leiste stehen (der Umschalter würde sonst neben der
    Tafel noch einen Seitenwechsel anbieten)."""
    s = _baue(tmp_path)
    knoepfe = s.select(".gr-reiter button[data-tafel]")
    beschriftungen = [(k.get("data-tafel"), k.get_text(strip=True))
                      for k in knoepfe]
    assert beschriftungen == [
        ("tafel-tco", "Vergleich"),
        ("tafel-radar", "Radar"),
        ("tafel-verlauf", "Preisverlauf"),
        ("tafel-katalog", "Gerätekatalog"),
    ]
    assert s.select_one(".gr-reiter a") is None, \
        "die Reiterleiste trägt noch einen Link (E3: vier Tafeln)"


def test_die_portfolio_tafel_ist_weg(tmp_path):
    """O3 (§5.2): die Portfolio-Tafel ist GANZ weg - Container und
    Abschnitte stehen auf dem Wettbewerbs-Radar. Eine leer stehende
    Tafel wäre die nächste Waise."""
    s = _baue(tmp_path)
    assert s.select_one("#tafel-portfolio") is None
    assert "Wie lange ein Gerät im Markt lebt" not in s.get_text()
