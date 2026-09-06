"""BRIEF_F5_ANBIETERZAEHLUNG (05.09.2026): eine Zahl, ein Wort.

Der Befund: auf derselben Modelltafel bedeutete "Anbieter" zwei
verschiedene Dinge - die Geraeteauswahl zaehlte die Anbieter mit einem
TCO-Buendel ("Apple iPhone 17 Pro 256 GB - 2 Anbieter"), der Zeitreihen-
Chart darunter (aria-label und `chrome`-Zeile) zaehlte die Preispunkte-
Reihen der Zeitreihe ("5 Anbieter"). Zwei Zaehlweisen, dasselbe Wort.

Die PM-Regel: "Anbieter" zaehlt UEBERALL die Preispunkte-Reihen der
Zeitreihe - dieselbe Zahl, die der Nutzer als Linien/Punkte im Chart
sieht. Haendler (Amazon/Expert/Saturn) tragen ihr eigenes Wort
("Haendler") und sind fuer diese Zaehlung nicht ausgenommen, sobald sie
als Reihe im Chart stehen - eine Ausnahme dafuer waere eine DRITTE
Zaehlweise (siehe die offene Frage im Abschlussbericht).

Umsetzung: `geraete_tco_grafik.zeitreihe()` liefert seine eigene Reihenzahl
jetzt als Feld (`anbieterzahl`) zurueck, statt sie nur in den aria-label-
Text zu schreiben. Die Vorlage (`geraete.html.j2`) liest fuer das Dropdown-
Label genau dieses Feld (`m.zeitreihe.anbieterzahl`) - dieselbe Rechnung,
keine zweite Kopie. Die vorherige, TCO-Buendel-basierte Zaehlung lebt intern
unter `bundle_anbieter` weiter (sie entscheidet nur noch die
Dropdown-Reihenfolge und die Leitfrage-Vorgabe, keine sichtbare
"Anbieter"-Zahl mehr).

Drei Testgruppen (Abnahmekriterien 1 und 3 aus dem Ticket):
  a) am echten Bestand: Dropdown-Label == Chart-Anbieterzahl, mindestens
     drei Modelle inkl. apple-iphone-17-pro-256.
  b) generisch: fuer JEDES Modell im Dropdown gilt Label == Chart-Zahl.
  c) ein Modell ohne Zeitreihendaten faellt nicht in einen Widerspruch -
     kein Chart, und das Dropdown behauptet keine erfundene Zahl (0, nicht
     die Zahl seiner TCO-Buendel-Anbieter).
"""
from __future__ import annotations

import pathlib
import re

import pytest
from bs4 import BeautifulSoup

from telco_radar.report import geraete_tco_grafik as grafik
from telco_radar.report.html import render_site

from test_geraete_tco_zustand import _baue

WURZEL = pathlib.Path(__file__).resolve().parents[1]

_OPTION_RE = re.compile(r"–\s*(\d+)\s*Anbieter\s*$")
_ARIA_RE = re.compile(r"Gerätepreis über die Zeit, (\d+) Anbieter,")


# --------------------------------------------------------------------------
# Am echten Bestand: die ganze Seite, gerendert gegen data/state + config
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def seite(tmp_path_factory) -> BeautifulSoup:
    site = tmp_path_factory.mktemp("f5-anbieterzaehlung") / "site"
    render_site(site, WURZEL / "data" / "reports")
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


def _dropdown_anbieterzahlen(seite: BeautifulSoup) -> dict:
    zahlen = {}
    for opt in seite.select("#gr-modell option"):
        treffer = _OPTION_RE.search(opt.text)
        assert treffer, f"Dropdown-Label ohne Anbieterzahl: {opt.text!r}"
        zahlen[opt["value"]] = int(treffer.group(1))
    return zahlen


def _chart_anbieterzahlen(seite: BeautifulSoup) -> dict:
    """0 fuer ein Modell ohne Chart - derselbe Leerzustand, den das
    Dropdown fuer ein solches Modell zeigen muss (Kriterium c)."""
    zahlen = {}
    for block in seite.select(".gr-tmodell"):
        mid = block["data-modell"]
        svg = block.select_one("svg.gr-g0")
        if svg is None:
            zahlen[mid] = 0
            continue
        treffer = _ARIA_RE.search(svg.get("aria-label", ""))
        assert treffer, f"{mid}: aria-label ohne Anbieterzahl"
        zahlen[mid] = int(treffer.group(1))
    return zahlen


# --------------------------------------------------------------------------
# a) am echten Bestand, mindestens drei Modelle inkl. der Leitfrage
# --------------------------------------------------------------------------

@pytest.mark.parametrize("modell_id", [
    "apple-iphone-17-pro-256",
    "apple-iphone-16-128",
    "samsung-galaxy-s25-128",
])
def test_dropdown_und_chart_nennen_am_echten_bestand_dieselbe_zahl(
        seite, modell_id):
    dropdown = _dropdown_anbieterzahlen(seite)
    chart = _chart_anbieterzahlen(seite)
    assert modell_id in dropdown, f"{modell_id} steht nicht im Bestand"
    assert modell_id in chart, f"{modell_id} hat keinen Modellblock"
    assert dropdown[modell_id] == chart[modell_id], (
        f"{modell_id}: Dropdown sagt {dropdown[modell_id]} Anbieter, "
        f"Chart sagt {chart[modell_id]}"
    )


def test_die_leitfrage_zeigt_wirklich_preispunkte_reihen_nicht_null(seite):
    """Reine Gegenprobe gegen einen trivial erfuellten Test: die Leitfrage
    (apple-iphone-17-pro-256) hat am echten Bestand tatsaechlich mehrere
    Preispunkte-Reihen, 0 == 0 waere kein Beweis."""
    dropdown = _dropdown_anbieterzahlen(seite)
    assert dropdown["apple-iphone-17-pro-256"] >= 2


# --------------------------------------------------------------------------
# b) generisch: ALLE Modelle im Dropdown
# --------------------------------------------------------------------------

def test_jedes_modell_im_dropdown_stimmt_mit_seinem_chart_ueberein(seite):
    dropdown = _dropdown_anbieterzahlen(seite)
    chart = _chart_anbieterzahlen(seite)
    # Ein Lookup, der ins Leere geht, ist ein grueber Test (CLAUDE.md §6) -
    # deshalb erst die Mengen selbst vergleichen.
    assert set(dropdown) == set(chart), \
        "Dropdown und Modellbloecke fuehren nicht dieselben Geraete"
    assert dropdown, "am echten Bestand muss mindestens ein Modell stehen"
    abweichungen = {mid: (n, chart[mid]) for mid, n in dropdown.items()
                    if n != chart[mid]}
    assert not abweichungen, f"Widerspruch bei: {abweichungen}"


# --------------------------------------------------------------------------
# c) ein Modell ohne Zeitreihendaten faellt nicht in einen Widerspruch
# --------------------------------------------------------------------------

def test_modell_ohne_zeitreihe_bleibt_ein_ehrlicher_leerzustand(tmp_path):
    """`graphloses_modell=True` (BRIEF_RAHMEN2_R3) haengt ein Buendel OHNE
    Listung und OHNE Preishistorie an - belastbare Karte, aber
    `zeitreihe.hat_daten == False`. Vor dieser Aenderung stand hier "1
    Anbieter" (die Zahl seines einen TCO-Buendels), obwohl kein Chart und
    keine einzige Preispunkte-Reihe existiert - der genaue Widerspruch, den
    dieses Ticket schliesst."""
    s = _baue(tmp_path, graphloses_modell=True)
    graphlos = "apple-iphone-16-pro-max-256"

    block = s.select_one(f'.gr-tmodell[data-modell="{graphlos}"]')
    assert block is not None, f"{graphlos} fehlt auf der Seite"
    assert block.select_one("svg.gr-g0") is None, \
        "ohne Zeitreihendaten darf kein Chart stehen"

    option = s.select_one(f'#gr-modell option[value="{graphlos}"]')
    assert option is not None, f"{graphlos} fehlt im Dropdown"
    treffer = _OPTION_RE.search(option.text)
    assert treffer, f"Dropdown-Label ohne Anbieterzahl: {option.text!r}"
    assert int(treffer.group(1)) == 0, (
        "ein Modell ohne Zeitreihendaten darf im Dropdown keine erfundene "
        "Anbieterzahl behaupten - 0 ist der ehrliche Leerzustand, den auch "
        "der fehlende Chart zeigt"
    )

    # Die Gegenprobe: das ANDERE Modell derselben Seite hat sehr wohl einen
    # Chart, und sein Dropdown-Label stimmt weiterhin mit ihm ueberein -
    # der Leerzustand darf die normale Zaehlung nicht mitreissen.
    normal = "apple-iphone-15-128"
    normal_block = s.select_one(f'.gr-tmodell[data-modell="{normal}"]')
    normal_svg = normal_block.select_one("svg.gr-g0")
    assert normal_svg is not None
    chart_treffer = _ARIA_RE.search(normal_svg.get("aria-label", ""))
    assert chart_treffer
    normal_option = s.select_one(f'#gr-modell option[value="{normal}"]')
    dropdown_treffer = _OPTION_RE.search(normal_option.text)
    assert dropdown_treffer
    assert int(dropdown_treffer.group(1)) == int(chart_treffer.group(1))


# --------------------------------------------------------------------------
# Die eine Rechnung: `zeitreihe()` liefert ihre Reihenzahl als Feld
# --------------------------------------------------------------------------

def _reihe(anbieter, punkte):
    return {"anbieter": anbieter, "farbe": "#123456", "eigen": False,
            "punkte": [{"datum": d, "preis": p} for d, p in punkte]}


def test_zeitreihe_liefert_ihre_eigene_reihenzahl_als_feld():
    """Das Feld, das die Vorlage fuer das Dropdown-Label liest, muss
    dieselbe Zahl tragen wie das aria-label - beide entstehen aus
    `len(reihen)`, nicht aus zwei getrennten Zaehlungen."""
    reihen = [
        _reihe("Vodafone", [("2026-08-20", 1000.0), ("2026-09-01", 1000.0)]),
        _reihe("congstar", [("2026-08-20", 990.0)]),
        _reihe("o2", [("2026-08-20", 980.0), ("2026-09-01", 970.0)]),
    ]
    ergebnis = grafik.zeitreihe(reihen)
    assert ergebnis["anbieterzahl"] == 3 == len(reihen)
    assert f"{ergebnis['anbieterzahl']} Anbieter" in ergebnis["svg"]


def test_zeitreihe_ohne_jeden_messpunkt_traegt_die_zahl_null():
    ergebnis = grafik.zeitreihe([])
    assert ergebnis["hat_daten"] is False
    assert ergebnis["anbieterzahl"] == 0
