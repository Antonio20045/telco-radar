"""E2 (AUFTRAG_GERAETE_EINE_SEITE_V2 §4): die Struktur der HAUPTANSICHT,
am gerenderten geraete.html geprueft - dieselbe Fixture wie die
Aufbereitungs-Tests (`test_geraete_zeitreihe_ansicht`).

Die Do-Not-Liste des Auftrags als Messung:
  §4.2  EINE Wahl-Leiste (Suchfeld + Band) -> der Graph; keine
        Unterueberschriften/Abschnitte/Erklaertext dazwischen (Pruefung
        PR #100, Auflage 1, 12.11.2026: der Antwort-Satz und sein
        "So gerechnet"-Aufklapper sind raus, die Zahl bleibt).
  §3.1  GENAU ZWEI Rest-Aufklapper: Rechenweg je Anbieterzeile,
        Fuss-Aufklapper "Massstab & Datenlage". Glossar und
        "Wie gerechnet?" sind ENDE.
  §3.4  Der Zeitreihen-Graph ersetzt ALLE frueheren Graph-Formen der
        Hauptansicht (Balkenliste, G1, Antwort-Leitzeilen).
"""

from __future__ import annotations

import json

import pytest
import zeitreihe_fragment
from bs4 import BeautifulSoup
from test_geraete_zeitreihe_ansicht import HEUTE, _baue

from telco_radar.report.html import render_site


@pytest.fixture(scope="module")
def gebaute_site(tmp_path_factory):
    root, state = _baue(tmp_path_factory.mktemp("zrseite"))
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(
        json.dumps(
            {
                "date": HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@pytest.fixture(scope="module")
def seite_html(gebaute_site):
    return (gebaute_site / "geraete.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fragment(gebaute_site):
    """Das Bündel-Fragment mit den Zeilen aller Modelle."""
    pfad = gebaute_site / "data" / "geraete-buendel.html"
    return BeautifulSoup(pfad.read_text(encoding="utf-8"), "html.parser")


@pytest.fixture(scope="module")
def suppe(seite_html):
    return BeautifulSoup(seite_html, "html.parser")


@pytest.fixture(scope="module")
def tafel(suppe):
    return suppe.select_one("#tafel-tco")


def test_der_startzustand_steht_serverseitig_als_svg(tafel):
    svg = tafel.select_one("svg.gr-zr")
    assert svg is not None
    assert svg.select("circle.gr-zr-punkt"), "der Graph braucht Punkte"
    assert tafel.select("text.gr-zr-xtick"), "die X-Achse braucht echte Messtag-Ticks"


def test_die_balkenliste_und_die_alten_graphformen_sind_weg(tafel):
    for tot in (
        ".gr-hgraph",
        ".gr-balkenliste",
        ".gr-bz",
        ".gr-msel",
        ".gr-antwort-leit",
        "svg.gr-g0",
        "svg.gr-g1",
    ):
        assert tafel.select(tot) == [], f"Rest der alten Form: {tot}"


def test_der_antwort_satz_und_sein_aufklapper_sind_fuer_auflage_1_weg(tafel):
    """Pruefung PR #100, Auflage 1 (12.11.2026): Antonio wollte den
    Ergebnissatz ("Beim ... am günstigsten: ...") und den "So gerechnet"-
    Link raus. Die Leitzahl (groesste Zahl des Viewports) und der Graph
    bleiben stehen."""
    assert tafel.select_one(".gr-zr-antwort") is None
    assert tafel.select_one(".gr-zr-rechnung") is None
    assert "TCO-24" not in tafel.get_text(" ", strip=True)


def test_der_glossar_und_wie_gerechnet_sind_weg(suppe, tafel):
    assert suppe.select_one("#gr-glossar") is None
    text = tafel.get_text(" ", strip=True)
    assert "Begriffe erklärt" not in text
    assert "Wie gerechnet?" not in text


def test_zwischen_wahl_leiste_und_graph_steht_kein_erklaertext(tafel):
    """Seit Auflage 1 (PR #100, 12.11.2026) bleibt hier hoechstens die
    Leitzahl (.gr-zr-leit) stehen, kein Antwort-Satz mehr."""
    wahl = tafel.select_one(".gr-zr-wahl")
    graph = tafel.select_one(".gr-zr-graph")
    assert all(e is not None for e in (wahl, graph))
    positionen = [e.sourceline for e in (wahl, graph) if e is not None]
    assert positionen == sorted(positionen)
    zwischen = [
        e
        for e in tafel.select(".gr-zr-wahl ~ *")
        if e.sourceline < graph.sourceline
        and e.name not in ("script",)
        and not any(
            k.startswith("gr-zr") or k.startswith("gr-bnd")
            for k in (e.get("class") or [])
        )
    ]
    assert zwischen == [], (
        f"unbekanntes Element zwischen Wahl und Graph: {[e.name for e in zwischen]}"
    )


def test_die_wahl_leiste_traegt_suchfeld_und_band_aber_keine_kacheln(tafel):
    assert tafel.select_one("#gr-zr-suche") is not None
    knoepfe = tafel.select("#gr-zr-baender button[data-band]")
    assert [k.get("data-band") for k in knoepfe] == ["xs", "m", "l"]
    assert tafel.select_one("#gr-zr-kacheln") is None


def test_kein_aufklapper_ueber_dem_graphen(tafel):
    """§3.1: zwischen Wahl-Leiste und Graph steht KEIN Aufklapper mehr -
    der Rechenschafts-Aufklapper ("So gerechnet") ist mit Auflage 1
    (PR #100, 12.11.2026) weg; der Balken-Graph trug bis E2 einen
    'Wie gerechnet?'-Block genau dort."""
    graph = tafel.select_one(".gr-zr-graph")
    for details in tafel.select("details"):
        if details.select_one(".gr-zr-graph") is not None:
            continue
        vor_graph = details.sourceline < graph.sourceline if graph else False
        inhalt = " ".join(details.get_text(" ", strip=True).split())[:60]
        if vor_graph and "gr-bnd" not in (details.get("class") or []):
            raise AssertionError(f"unerwarteter Aufklapper ueber dem Graphen: {inhalt}")


def test_der_fuss_aufklapper_tarife_ohne_geraet_ist_weg(tafel):
    assert tafel.select_one("details#gr-massstab-datenlage") is None


def test_zwei_separate_fuss_aufklapper_gibt_es_nicht_mehr(tafel):
    assert tafel.select_one("details#gr-massstab") is None
    assert tafel.select_one("details#gr-datenlage") is None


def test_die_buendel_zeilen_bleiben_unter_dem_graphen(tafel, fragment):
    """Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment. Unter dem Graphen bleibt der Abschnitt mit der Zeile
    der fehlenden Anbieter."""
    block = tafel.select_one("#gr-buendel")
    assert block is not None
    assert block.select_one("#gr-bnd-gruppe") is not None
    assert not tafel.select(".gr-bnd"), "Bündelzeilen stehen noch auf der Seite"
    lager = fragment.select_one("#gr-bnd-vorgabe")
    assert lager is not None, "das Fragment trägt kein Startmodell"
    assert lager.select(".gr-bnd"), "die Anbieterzeilen fehlen"
    assert lager.select(".gr-bnd .gr-bnd-rw"), (
        "der Rechenweg-Aufklapper je Zeile fehlt (§3.1b)"
    )


def test_der_zeitreihe_knoten_traegt_startzustand_und_suchindex(suppe):
    knoten = suppe.select_one("#gr-zeitreihe-daten")
    assert knoten is not None
    daten = json.loads(knoten.string)
    assert daten["vorgabe"] == "apple-iphone-17-pro-256"
    assert daten["start_band"] == "xs"
    assert daten["suchindex"] and daten["erlaubt"]
    assert "€" not in knoten.string


def test_der_grafik_daten_knoten_ist_weg(suppe):
    """Der O1-Knoten #gr-graph-daten war der Balken-Selektor; sein Feld
    fiel mit der Balkenansicht. Wer ihn wieder anlegt, legt eine zweite
    Zahlenquelle fuer denselben Graphen an."""
    assert suppe.select_one("#gr-graph-daten") is None


def test_das_fragment_traegt_alle_pare_und_den_startzustand(tmp_path_factory):

    root, state = _baue(tmp_path_factory.mktemp("zrfrag"))
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(
        json.dumps(
            {
                "date": HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    assert not (site / "data" / "geraete-zeitreihe.html").exists()
    inhalt = zeitreihe_fragment.lies(site / "data")
    frag = BeautifulSoup(inhalt, "html.parser")
    lager = frag.select(".gr-zr-lager")
    paare = {(l.get("data-modell"), l.get("data-band")) for l in lager}
    assert ("apple-iphone-17-pro-256", "xs") in paare
    assert ("apple-iphone-17-pro-256", "m") in paare
    assert ("samsung-galaxy-s26-256", "xs") in paare
