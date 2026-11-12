"""BRIEF_FADEN (05.09.2026, Senecas Freigabe): die Geraeteseite auf EINE
Frage reduziert - "Was kostet dieses Gerät?".

Sechs Abnahmekriterien, sechs Testgruppen:
  1. Ein Graph: G0 ist die einzige `<svg>`-Grafik im sichtbaren Bereich je
     Modellblock (G1-Balken nicht mehr gerendert).
  2. Kein Erklärtext zwischen Auswahl und Graph (die Antwortzeile ist mit
     Auflage 1, Pruefung PR #100, 12.11.2026 raus).
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


def test_der_eine_graph_ist_die_zeitreihe(tmp_path):
    """E2 (16.09.2026) dreht die Regel ein drittes Mal - diesmal auf
    Antonios ausdrueckliche Entscheidung (AUFTRAG_GERAETE_EINE_SEITE_V2
    §1a): der EINE Graph der Vergleichsansicht ist DIE TCO-ZEITREIHE, ein
    SVG-Koordinatensystem mit Punkten je Messung. Die Balkenform (O1) ist
    ERSETZT: .gr-hgraph und .gr-bz sind Reste, G1 bleibt verboten; G0 ist
    seit dem E3-Fix (QA 17.09.2026) ganz gefallen - der Verlaufs-Reiter
    traegt seine eigene Barpreis-Auswahl, keine zweite Grafik daneben."""
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


def test_zwischen_auswahl_und_graph_steht_kein_antwort_satz(tmp_path):
    """E2 verlangte Wahl-Leiste, dann Antwort-Satz, dann Graph (§4.2: nichts
    dazwischen). Pruefung PR #100, Auflage 1 (12.11.2026): Antonio wollte den
    Antwort-Satz raus - die Reihenfolge Wahl-Leiste -> Graph bleibt, nur
    ohne Satz dazwischen."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    auswahl = tafel.select_one("#gr-zr-wahl")
    assert auswahl is not None, "die Wahl-Leiste fehlt"
    assert tafel.select_one(".gr-zr-antwort") is None, "der Antwort-Satz steht noch"
    assert tafel.select_one(".gr-zr-rechnung") is None, (
        'der "So gerechnet"-Aufklapper steht noch'
    )
    graph = tafel.select_one(".gr-zr-graph")
    assert graph is not None, "der Zeitreihen-Graph fehlt"
    text = str(tafel)
    assert text.index('id="gr-zr-wahl"') < text.index('class="gr-zr-graph"')


def test_die_legende_nennt_weiterhin_anbieter_und_preis(tmp_path):
    """Seit Auflage 1 (PR #100, 12.11.2026) sagt kein Satz mehr, wer am
    günstigsten ist - die Preise selbst (Legende, Graph) bleiben stehen.
    Der Geraetepreis ohne Vertrag steht weiterhin auf jeder Bündel-Zeile."""
    s = _baue(tmp_path)
    legende = s.select_one("#tafel-tco .gr-zr-legende")
    assert legende is not None, "die Legende fehlt"
    text = " ".join(legende.get_text(" ", strip=True).split())
    assert "€" in text
    assert any(a in text for a in ("o2", "Vodafone", "1&1", "congstar")), (
        f"kein Anbieter in der Legende: {text}"
    )


def test_der_seitentitel_ist_sachlich(tmp_path):
    s = _baue(tmp_path)
    titel = s.select_one("title").get_text(strip=True)
    assert titel.endswith("· Gerätepreise")


def test_die_vergleichsansicht_traegt_keine_alarmtafel_mehr(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select_one(".gr-chips") is None, (
        "die Ampel-Kacheln stehen noch in der Vergleichsansicht"
    )
    assert tafel.select_one("#gr-alarme") is None
    assert tafel.select_one("#gr-tco-tabelle") is None, (
        "'Alle Bündel als Tabelle' ist in die Zeilen-Tabelle aufgegangen"
    )


def test_die_buendel_zeilen_stehen_ausserhalb_jeder_aufklappung(tmp_path):
    """Die Bündel-Zeilen (seit O2 die Kartenform) stehen OFFEN unter dem
    Graphen - nicht in einer Analyse-Aufklappung verschachtelt. Zwei
    Klapptiefen für dasselbe Angebot blieben verboten."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    for zeile in tafel.select("#gr-buendel .gr-bnd"):
        elter = zeile.parent
        while elter is not None and elter.name is not None:
            if elter.name == "details" and "gr-bnd" not in (elter.get("class") or []):
                pytest.fail(
                    "Bündelzeile steckt in einer Aufklappung: " + str(elter)[:80]
                )
            elter = elter.parent


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


def test_die_reiterleiste_traegt_vergleich_radar_verlauf_katalog(tmp_path):
    """E3 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1d): vier echte Tafeln in der
    Folge Vergleich · Radar · Preisverlauf · Gerätekatalog. Bis E3 war
    der Radar ein Link auf wettbewerbsradar.html (O3-Quasi-Reiter); der
    wird durch die Tafel DIESER Seite ersetzt - deshalb darf kein Link
    mehr in der Leiste stehen (der Umschalter würde sonst neben der
    Tafel noch einen Seitenwechsel anbieten)."""
    s = _baue(tmp_path)
    knoepfe = s.select(".gr-reiter button[data-tafel]")
    beschriftungen = [(k.get("data-tafel"), k.get_text(strip=True)) for k in knoepfe]
    assert beschriftungen == [
        ("tafel-tco", "Mit Tarif"),
        ("tafel-verlauf", "Einzelgerät"),
        ("tafel-radar", "Übersicht"),
    ]
    assert s.select_one(".gr-reiter a") is None, (
        "die Reiterleiste trägt noch einen Link (E3: vier Tafeln)"
    )


def test_die_portfolio_tafel_ist_weg(tmp_path):
    """O3 (§5.2): die Portfolio-Tafel ist GANZ weg - ein leer stehender
    Tab-Body wäre die nächste Waise. Die Abschnitte selbst leben weiter:
    seit E3 Schritt 3 (17.09.2026) als zugeklappte Sektionen im Radar-
    Reiter DIESER Seite (bis dahin auf der Schwesterseite, die seitdem
    eine Weiterleitung ist) - geprüft wird die TAFEL, nicht der Inhalt."""
    s = _baue(tmp_path)
    assert s.select_one("#tafel-portfolio") is None
    assert s.select_one(".gr-reiter [data-tafel='tafel-portfolio']") is None
    radar = s.select_one("#tafel-radar")
    assert radar is not None, "#tafel-radar fehlt - der Test prüft nichts"
    lifecycle = radar.select_one("#lifecycle")
    if lifecycle is not None:
        details = lifecycle.select_one("details.gr-auf")
        assert details is not None and not details.get("open")
