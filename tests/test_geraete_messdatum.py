"""Brief messdatum-0811 (Antonio, 08.11.2026 13:20): das letzte Messdatum je Anbieter.

Die Seite sagte „Stand 08.11.2026“ (Tag der Berechnung) und trug das Abrufdatum erst an
der einzelnen Zeile. Jetzt steht oben je Anbieter „zuletzt gemessen am …“, ein Anbieter
nicht vom jüngsten Messtag trägt „Stand vom TT.MM.“, und ohne lesbares Datum heißt es
„Messdatum unbekannt“ - nie das heutige (fail-closed, Clean Code 4).

Alle Fixtures setzen ihr Datum selbst (harte Regel 7): HEUTE ist der 08.11.2026, Telekom
wurde zuletzt am 07.11. gemessen (Schutzseite am Morgen des 08.11.).
"""

from __future__ import annotations

from pathlib import Path

from bestand_pfad import lese_wurzel
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_messdatum, geraete_tco_view, startseite
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-08"
_VORLAGEN = Path(geraete_messdatum.__file__).parent / "templates"


def _env():
    env = Environment(loader=FileSystemLoader(_VORLAGEN), autoescape=True)
    env.globals.update(startseite.VORLAGEN_HELFER)
    return env


def _b(anbieter, tag):
    return {"anbieter": anbieter, "abgerufen_am": tag}


def _zeilen(buendel, heute=HEUTE):
    ergebnis = geraete_messdatum.je_anbieter(buendel, heute)
    return {z["name"]: z for z in ergebnis["zeilen"]}


def test_jeder_anbieter_nennt_sein_juengstes_messdatum():
    z = _zeilen(
        [
            _b("Vodafone", "2026-11-08"),
            _b("Vodafone", "2026-11-02"),
            _b("Telekom", "2026-11-07"),
            _b("Telekom", "2026-10-20"),
            _b("o2", "2026-11-08"),
            _b("1&1", "2026-11-08"),
            _b("congstar", "2026-11-08"),
        ]
    )
    assert z["Telekom"]["satz"] == "Telekom: zuletzt gemessen am 07.11.2026"
    assert z["Vodafone"]["satz"] == "Vodafone: zuletzt gemessen am 08.11.2026"
    assert z["Telekom"]["stand"] == "Stand vom 07.11."
    assert z["Vodafone"]["stand"] == "" and not z["Vodafone"]["alt"]


def test_ohne_lesbares_datum_steht_messdatum_unbekannt_nie_heute():
    z = _zeilen(
        [
            _b("Vodafone", "2026-11-08"),
            _b("Telekom", ""),
            _b("Telekom", None),
            _b("o2", "kein-datum"),
            _b("1&1", "2026-11-09"),
        ]
    )
    for name in ("Telekom", "o2", "1&1", "congstar"):
        assert z[name]["satz"] == f"{name}: Messdatum unbekannt"
        assert z[name]["datum"] == ""
        assert "08.11.2026" not in z[name]["satz"]


def test_stand_vom_an_der_zeile():
    assert geraete_messdatum.stand_vom("2026-09-15", "2026-11-08") == "Stand vom 15.09."
    assert geraete_messdatum.stand_vom("2026-11-08", "2026-11-08") == ""
    assert geraete_messdatum.stand_vom("", "2026-11-08") == "Messdatum unbekannt"
    assert geraete_messdatum.stand_vom(None, "2026-11-08") == "Messdatum unbekannt"
    assert geraete_messdatum.stand_vom("2026-11-07", "") == ""


def test_die_seite_rendert_die_zeile_aus_den_gerechneten_buendeln():
    katalog = lade_katalog(lese_wurzel())
    sku = "apple-iphone-17-pro-256gb-schwarz"

    def bnd(anbieter, tag):
        return Buendel(
            sku_id=sku,
            anbieter=anbieter,
            tarif_name=f"{anbieter} L",
            buendel_monatlich=40.0,
            laufzeit_monate=24,
            quelle_url="https://example.invalid/x",
            abgerufen_am=tag,
        )

    tco = geraete_tco_view.aufbereiten(
        [bnd("Vodafone", "2026-11-08"), bnd("Telekom", "2026-11-07")],
        [],
        [],
        katalog,
        heute=HEUTE,
    )
    html = (
        _env()
        .get_template("_geraete_messdatum.html.j2")
        .render(geraete={"tco": tco, "stand": HEUTE})
    )
    suppe = BeautifulSoup(html, "html.parser")
    je = {
        li["data-anbieter"]: li.get_text(" ", strip=True)
        for li in suppe.select("#messdatum li")
    }
    assert je["Telekom"] == "Telekom: zuletzt gemessen am 07.11.2026 Stand vom 07.11."
    assert je["Vodafone"] == "Vodafone: zuletzt gemessen am 08.11.2026"
    assert je["o2"] == "o2: Messdatum unbekannt"
    leer = (
        _env()
        .get_template("_geraete_messdatum.html.j2")
        .render(geraete={"tco": geraete_tco_view.leer(), "stand": HEUTE})
    )
    assert leer.count("Messdatum unbekannt") == 5
