"""BRIEF_F5_ANBIETERZAEHLUNG (05.09.2026): eine Zahl, ein Wort.

Der Befund: auf derselben Modelltafel bedeutete "Anbieter" zwei
verschiedene Dinge - die Geraeteauswahl zaehlte die Anbieter mit einem
TCO-Buendel ("Apple iPhone 17 Pro 256 GB - 2 Anbieter"), der Zeitreihen-
Chart darunter (aria-label und chrome-Zeile) zaehlte die Preispunkte-
Reihen der Zeitreihe ("5 Anbieter"). Zwei Zaehlweisen, dasselbe Wort.

O1 (STRATEGIE_GERAETE_OPTIK, 11.09.2026) hat das Problem AN DER WURZEL
geloest, nicht umgangen: Das "- N Anbieter"-Suffix existiert nicht mehr.
Die Geraeteauswahl nennt nur den Geraetenamen, und die fuenf Zehlsysteme
der Vergleichsansicht sind auf EINE Fussnote unter dem Graphen gesammelt
("N Geraete mit mindestens einem erhebbaren Buendel"). Der Zeitreihen-
Chart ist mit O1 aus der Vergleichsansicht entfernt (O4 bindet ihn im
Verlaufs-Reiter wieder an).

Diese Datei sichert seither zwei Dinge:
  a) Das Dropdown nennt KEINE Anbieterzahl mehr - am echten Bestand und
     an der Fixture (nichts sieht einer Zahl aehnlich, die eine andere
     Menge meint).
  b) Die EINE Rechnung bleibt: `zeitreihe()` liefert seine Reihenzahl als
     Feld - dieselbe Zahl wie im aria-label. O4 liest sie wieder.
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

# Alles, was nach einer Zahl mit Wort "Anbieter" aussieht - O1 entfernt
# dieses Muster vollstaendig aus der Vergleichsansicht.
_OPTION_RE = re.compile(r"\d+\s*Anbieter")


# --------------------------------------------------------------------------
# Am echten Bestand: die ganze Seite, gerendert gegen data/state + config
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def seite(tmp_path_factory) -> BeautifulSoup:
    site = tmp_path_factory.mktemp("f5-anbieterzaehlung") / "site"
    render_site(site, WURZEL / "data" / "reports")
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


def test_keine_dropdown_option_nennt_eine_anbieterzahl_mehr(seite):
    """O1-Auftrag Punkt 6: '- N Anbieter'-Suffixe entfallen. Am echten
    Bestand stehen 80+ Optionen - keine darf die alte Doppelzaehlung
    zurueckbringen.

    O3 (D2): der letzte Assert war `... or True` und prüfte nichts - als
    echter wäre er immer rot gefallen, denn value ist die Modell-ID und
    der Text der Titel (zwei verschiedene Dinge, seit O1). Die echte
    Zusicherung dahinter: JEDE Option trägt einen nicht-leeren, EIN-
    DEUTIGEN value - der O3-Deep-Link `?modell=<id>` und die Querlinks
    des Radars wählen darüber EIN Modell; eine doppelte ID nähme der
    Browser als erste, und der Link zeigte ein anderes Gerät, als sein
    Radar-Block versprach."""
    # E2: der Selektor ist das Suchfeld - waehlbar ist, was der Zeitreihen-
    # Knoten als erlaubt traegt. Dieselben Zusicherungen am neuen Ort:
    # keine Anbieterzahl im NAMEN, eindeutige IDs fuer den Deep-Link.
    import json
    knoten = json.loads(
        seite.select_one("#gr-zeitreihe-daten").get_text())
    ids = list(knoten["erlaubt"])
    assert len(ids) >= 3, "am echten Bestand stehen mehr Modelle"
    assert all(ids), "eine Modell-ID ist leer"
    assert len(ids) == len(set(ids)), \
        f"Modell-IDs nicht eindeutig: " \
        f"{sorted(v for v in ids if ids.count(v) > 1)[:3]}"
    titel = knoten["titel"]
    for mid in ids:
        assert not _OPTION_RE.search(titel.get(mid, "")), \
            f"Titel traegt noch eine Anbieterzahl: {titel.get(mid)!r}"


def test_der_startzustand_ist_derselbe_im_knoten_und_im_serverblock(seite):
    """E2: was ohne Klick da steht, entscheidet der ZEITREIHEN-Startzustand
    (`geraete_zeitreihe.aufbereiten`: die meisten Anbieter, dann Punkte -
    aus den Daten). Der JSON-Knoten traegt dieselbe Vorgabe wie der
    Server-First-Paint: app.js und Server starten im selben Modell."""
    import json
    knoten = json.loads(
        seite.select_one("#gr-zeitreihe-daten").get_text())
    vorgabe = knoten["vorgabe"]
    assert vorgabe and vorgabe in knoten["erlaubt"], \
        "die Start-Vorgabe ist kein wählbares Modell"
    titel = knoten["titel"][vorgabe]
    antwort = seite.select_one("#tafel-tco .gr-zr-antwort")
    assert antwort is not None, "der Server-Startblock fehlt"
    # Der Antwort-Satz nennt das Startgeraet beim Kurznamen - der Titel
    # ist "Hersteller Modell Speicher GB"; geprueft wird das Modellstück.
    modell_stueck = " ".join(titel.split()[1:-2]) if titel.split()[-1] == \
        "GB" else titel
    assert modell_stueck in antwort.get_text(" ", strip=True), \
        f"Server-Block nennt nicht das Startgeraet {titel!r}"


def test_modell_ohne_zeitreihe_steht_ohne_widerspruch_da(tmp_path):
    """`graphloses_modell=True` haengt ein Buendel OHNE Listung und OHNE
    Preishistorie an. Vor O1 stand hier der Widerspruch "1 Anbieter" ohne
    Chart; heute steht das Modell ohne jede Zahl da - der Leerzustand des
    Graphen ist der ehrliche."""
    s = _baue(tmp_path, graphloses_modell=True)
    graphlos = "apple-iphone-16-pro-max-256"

    # E2: ein Modell ohne Bündel-Band ist in der Zeitreihen-Ansicht nicht
    # wählbar (erlaubt leer) - es hat keinen Graph-Zustand und keine
    # Band-Zeilen. Der Katalog zeigt seine Listungen; die Modell-Liste der
    # Seite kommt mit E3 (S2: die Abweichungstabelle).
    import json
    knoten = json.loads(
        s.select_one("#gr-zeitreihe-daten").get_text())
    assert knoten["erlaubt"].get(graphlos) in (None, []), \
        "das bandlose Modell duerfte nicht wählbar sein"
    assert graphlos not in {e["id"] for e in knoten["suchindex"]}

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
