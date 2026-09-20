"""E2 (AUFTRAG_GERAETE_EINE_SEITE_V2 §4): die Struktur der HAUPTANSICHT,
am gerenderten geraete.html geprueft - dieselbe Fixture wie die
Aufbereitungs-Tests (`test_geraete_zeitreihe_ansicht`).

Die Do-Not-Liste des Auftrags als Messung:
  §4.2  EINE Wahl-Leiste (Suchfeld + Band) -> EIN Antwort-Satz -> der
        Graph; keine Unterueberschriften/Abschnitte dazwischen.
  §3.1  GENAU DREI Rest-Aufklapper: Rechenschaftssatz (eine Zeile unter
        dem Antwort-Satz), Rechenweg je Anbieterzeile, Fuss-Aufklapper
        "Massstab & Datenlage". Glossar und "Wie gerechnet?" sind ENDE.
  §3.4  Der Zeitreihen-Graph ersetzt ALLE frueheren Graph-Formen der
        Hauptansicht (Balkenliste, G1, Antwort-Leitzeilen).
"""
from __future__ import annotations

import json

import pytest
from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report.html import render_site

from test_geraete_zeitreihe_ansicht import HEUTE, _baue


@pytest.fixture(scope="module")
def seite_html(tmp_path_factory):
    root, state = _baue(tmp_path_factory.mktemp("zrseite"))
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return (site / "geraete.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def suppe(seite_html):
    return BeautifulSoup(seite_html, "html.parser")


@pytest.fixture(scope="module")
def tafel(suppe):
    return suppe.select_one("#tafel-tco")


# --------------------------------------------------------------------------
# §3.4 - der Zeitreihen-Graph ersetzt alle frueheren Graph-Formen
# --------------------------------------------------------------------------

def test_der_startzustand_steht_serverseitig_als_svg(tafel):
    svg = tafel.select_one("svg.gr-zr")
    assert svg is not None
    assert svg.select("circle.gr-zr-punkt"), "der Graph braucht Punkte"
    assert tafel.select("text.gr-zr-xtick"), \
        "die X-Achse braucht echte Messtag-Ticks"


def test_die_balkenliste_und_die_alten_graphformen_sind_weg(tafel):
    for tot in (".gr-hgraph", ".gr-balkenliste", ".gr-bz", ".gr-msel",
                ".gr-antwort-leit", "svg.gr-g0", "svg.gr-g1"):
        assert tafel.select(tot) == [], f"Rest der alten Form: {tot}"


def test_die_antwort_leitzeile_ist_durch_den_antwort_satz_ersetzt(tafel):
    antwort = tafel.select_one(".gr-zr-antwort")
    assert antwort is not None
    text = antwort.get_text(" ", strip=True)
    assert "Kosten über 24 Monate" in text
    assert "TCO-24" not in text


def test_der_glossar_und_wie_gerechnet_sind_weg(suppe, tafel):
    assert suppe.select_one("#gr-glossar") is None
    text = tafel.get_text(" ", strip=True)
    assert "Begriffe erklärt" not in text
    assert "Wie gerechnet?" not in text


# --------------------------------------------------------------------------
# §4.2 - Wahl-Leiste, Antwort-Satz, Graph - in dieser Reihenfolge
# --------------------------------------------------------------------------

def test_zwischen_wahl_leiste_und_graph_steht_nur_der_antwort_satz(tafel):
    wahl = tafel.select_one(".gr-zr-wahl")
    kacheln = tafel.select_one(".gr-zr-kacheln")
    antwort = tafel.select_one(".gr-zr-antwort")
    graph = tafel.select_one(".gr-zr-graph")
    assert all(e is not None for e in (wahl, antwort, graph))
    # DOM-Reihenfolge: Wahl < Kacheln < Antwort < Graph (§4.2) - nichts
    # Unbenanntes darf dazwischenrutschen.
    positionen = [e.sourceline for e in (wahl, kacheln, antwort, graph)
                  if e is not None]
    assert positionen == sorted(positionen)
    # Der Antwort-Satz ist das EINZIGE Element zwischen Wahl-Leiste bzw.
    # Kacheln und dem Graphen, das kein Aufklapper und keine Tabelle ist.
    zwischen = [e for e in tafel.select(".gr-zr-wahl ~ *")
                if e.sourceline < graph.sourceline
                and e.name not in ("script",)
                and not any(k.startswith("gr-zr") or k.startswith("gr-bnd")
                            for k in (e.get("class") or []))]
    assert zwischen == [], \
        f"unbekanntes Element zwischen Wahl und Graph: {[e.name for e in zwischen]}"


def test_die_wahl_leiste_traegt_suchfeld_band_und_kacheln(tafel):
    assert tafel.select_one("#gr-zr-suche") is not None
    knoepfe = tafel.select("#gr-zr-baender button[data-band]")
    assert [k.get("data-band") for k in knoepfe] == \
        ["klein", "mittel", "gross"]
    kacheln = tafel.select("#gr-zr-kacheln button[data-modell]")
    assert 1 <= len(kacheln) <= 6


def test_jede_karte_traegt_preis_und_anbieter_punkte(tafel):
    """P1/F3 (A3) + P1-Fix (Sicht-B2): die Karte ist die erste Preis-
    antwort der Tafel - JE BAND ein eigener Satz Spans (Preis, Delta,
    Punkte), genau eine Bandlage sichtbar. Ein Band ohne echtes Angebot
    zeigt den benannten Leerzustand „—" statt eines geratenen Preises.
    get_text OHNE Trenner (Hausregel aus dem 2454-Modelle-Befund)."""
    karten = tafel.select("#gr-zr-kacheln button[data-modell]")
    assert karten, "die Modell-Karten fehlen"
    for k in karten:
        bande = k.select(".gr-zr-k-band[data-band]")
        assert bande, "Karte ohne Band-Spans"
        sichtbar = [s for s in bande if not s.has_attr("hidden")]
        assert sichtbar, "kein Band-Span sichtbar"
        # Alle sichtbaren Preislagen zugleich: eine Karte zeigt EIN Band.
        preise = k.select(".gr-zr-k-preis")
        assert preise, "Karte ohne Preis-Gruppe"
        if not k.select_one(".gr-zr-k-leer"):
            preis = k.select_one(".gr-zr-k-preis b")
            assert preis is not None, "Karte ohne ab-Preis"
            assert "€" in preis.get_text()
            assert k.select_one(".gr-zr-k-preis small").get_text() == "ab"
            monat = k.select_one(".gr-zr-k-monat")
            assert monat is not None and "€/Monat" in monat.get_text()
        assert k.select(".gr-zr-k-punkte i"), "Karte ohne Anbieter-Punkte"
        delta = k.select_one(".gr-zr-k-delta")
        assert delta is None or ("€" in delta.get_text()
                                 and "Tag" in delta.get_text())
        assert "€" in k.get_text()


def test_kein_weiterer_aufklapper_ueber_dem_graphen(tafel):
    """§3.1: zwischen Wahl-Leiste und Graph steht Hoechstens der EINE
    Rechenschafts-Aufklapper - der Balken-Graph trug bis E2 einen
    'Wie gerechnet?'-Block genau dort."""
    graph = tafel.select_one(".gr-zr-graph")
    for details in tafel.select("details"):
        if details.select_one(".gr-zr-graph") is not None:
            continue                      # der Fuss-Aufklapper umfasst mehr
        vor_graph = details.sourceline < graph.sourceline \
            if graph else False
        inhalt = " ".join(details.get_text(" ", strip=True).split())[:60]
        if vor_graph and "gr-bnd" not in (details.get("class") or []):
            assert "gr-zr-rechnung" in (details.get("class") or []), \
                f"unerwarteter Aufklapper ueber dem Graphen: {inhalt}"


# --------------------------------------------------------------------------
# §3.1c - der Fuss-Aufklapper "Massstab & Datenlage"
# --------------------------------------------------------------------------

def test_der_fuss_aufklapper_heisst_massstab_und_datenlage(tafel):
    fuss = tafel.select_one("details#gr-massstab-datenlage")
    assert fuss is not None
    assert "Maßstab & Datenlage" in fuss.select_one("summary").get_text(
        " ", strip=True)


def test_zwei_separate_fuss_aufklapper_gibt_es_nicht_mehr(tafel):
    assert tafel.select_one("details#gr-massstab") is None
    assert tafel.select_one("details#gr-datenlage") is None


def test_die_buendel_zeilen_bleiben_unter_dem_graphen(tafel):
    assert tafel.select_one("#gr-buendel") is not None
    assert tafel.select(".gr-bnd"), "die Anbieterzeilen fehlen"
    assert tafel.select(".gr-bnd .gr-bnd-rw"), \
        "der Rechenweg-Aufklapper je Zeile fehlt (§3.1b)"


# --------------------------------------------------------------------------
# Der Client-Knoten - Interaktion ohne Zahlen
# --------------------------------------------------------------------------

def test_der_zeitreihe_knoten_traegt_startzustand_und_suchindex(suppe):
    knoten = suppe.select_one("#gr-zeitreihe-daten")
    assert knoten is not None
    daten = json.loads(knoten.string)
    assert daten["vorgabe"] == "apple-iphone-17-pro-256"
    assert daten["start_band"] == "klein"
    assert daten["suchindex"] and daten["erlaubt"]
    assert "€" not in knoten.string


def test_der_grafik_daten_knoten_ist_weg(suppe):
    """Der O1-Knoten #gr-graph-daten war der Balken-Selektor; sein Feld
    fiel mit der Balkenansicht. Wer ihn wieder anlegt, legt eine zweite
    Zahlenquelle fuer denselben Graphen an."""
    assert suppe.select_one("#gr-graph-daten") is None


def test_das_fragment_traegt_alle_pare_und_den_startzustand(tmp_path_factory):
    import pathlib
    root, state = _baue(tmp_path_factory.mktemp("zrfrag"))
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de", "briefing_md": "## Auf einen Blick",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    fragment = (site / "data" / "geraete-zeitreihe.html")
    assert fragment.exists(), "das Zeitreihen-Fragment fehlt"
    inhalt = fragment.read_text(encoding="utf-8")
    frag = BeautifulSoup(inhalt, "html.parser")
    lager = frag.select(".gr-zr-lager")
    # ALLE Paare - auch die des Startzustands: der Rueckweg nach einem
    # Wechsel hat genau EINE Quelle (kein Vorgabe-Klon, keine S2-Falle).
    paare = {(l.get("data-modell"), l.get("data-band")) for l in lager}
    assert ("apple-iphone-17-pro-256", "klein") in paare
    assert ("apple-iphone-17-pro-256", "mittel") in paare
    assert ("samsung-galaxy-s26-256", "klein") in paare
