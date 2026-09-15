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
    optionen = seite.select("#gr-modell option")
    assert len(optionen) >= 3, "am echten Bestand stehen mehr Modelle"
    for opt in optionen:
        assert not _OPTION_RE.search(opt.get_text()), \
            f"Option traegt noch eine Anbieterzahl: {opt.get_text()!r}"
    werte = [opt.get("value") for opt in optionen]
    assert all(werte), "eine Option ohne value"
    assert len(werte) == len(set(werte)), \
        f"Modell-IDs im Selektor nicht eindeutig: " \
        f"{sorted(v for v in werte if werte.count(v) > 1)[:3]}"


def test_die_vorgabe_des_dropdowns_ist_die_leitfrage(seite):
    """Was das Dropdown ohne Klick zeigt, entscheidet `modell_vorgabe` -
    am echten Bestand das Leitfragegeraet (G3 der Abnahme). Der JSON-Knoten
    traeg dieselbe Vorgabe: app.js und Server starten im selben Modell."""
    selektiert = [o for o in seite.select("#gr-modell option")
                  if o.has_attr("selected")]
    assert len(selektiert) == 1
    knoten = seite.select_one("#gr-graph-daten")
    assert knoten is not None, "der JSON-Knoten fuer den Selektor fehlt"
    import json
    vorgabe = json.loads(knoten.text)["vorgabe"]
    assert vorgabe == selektiert[0]["value"]


def test_modell_ohne_zeitreihe_steht_ohne_widerspruch_da(tmp_path):
    """`graphloses_modell=True` haengt ein Buendel OHNE Listung und OHNE
    Preishistorie an. Vor O1 stand hier der Widerspruch "1 Anbieter" ohne
    Chart; heute steht das Modell ohne jede Zahl da - der Leerzustand des
    Graphen ist der ehrliche."""
    s = _baue(tmp_path, graphloses_modell=True)
    graphlos = "apple-iphone-16-pro-max-256"

    option = s.select_one(f'#gr-modell option[value="{graphlos}"]')
    assert option is not None, f"{graphlos} fehlt im Dropdown"
    assert not _OPTION_RE.search(option.get_text())

    # Der Modellblock des Vorgabegeraets traegt keinen Chart-SVG mehr -
    # der Graph ist HTML/CSS-Balken (A2), G0 wandert in O4 in den
    # Verlaufs-Reiter.
    assert not s.select("#tafel-tco svg"), \
        "in der Vergleichsansicht steht noch ein SVG"

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
