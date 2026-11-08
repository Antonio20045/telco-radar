"""Beleg je Preisposition (Ziel 1d): ein Bild hängt nur an der Zeile, die es zeigt.

Fail-closed: ein Beleg mit abweichendem Gerät oder Tarif wird abgelehnt, ein Paar mit
gleich teuren Positionen, mit neuerem Abruf oder ohne Klick-Messung bekommt keine Zeile
mit Bild. Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7). Die Seite wird mit
``render_site`` gebaut und als DOM gelesen.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import test_geraete_buendel_kopf_zeitraum as kopf_zeitraum
from bs4 import BeautifulSoup
from test_geraete_browser_fixture import HEUTE

from telco_radar.analyze import beleg_position as schluessel
from telco_radar.beleg_manifest import MANIFEST_NAME, baue_manifest, schreibe
from telco_radar.beleg_regeln import dateiname
from telco_radar.report import geraete_zeilenbelege as zeilen
from telco_radar.report.html import render_site

MODELL = kopf_zeitraum.MODELL
TAG = date.fromisoformat(HEUTE)
GESTERN = TAG - timedelta(days=1)
VERMERK = "Kein Screenshot zu genau dieser Zeile."
ID_O2 = "a" * 64
ID_TK_1 = "b" * 64
ID_TK_2 = "c" * 64
ID_CS = "d" * 64


def _satz(anbieter, tarif, tarif_id, laufzeit, rate, beleg_id, sku=None, tag=HEUTE):
    return {
        "id": f"buendel--{anbieter.lower()}--{tarif_id}--{laufzeit}--{beleg_id[:4]}",
        "sku_id": sku or "apple-iphone-17-pro-256gb-ohne-farbe",
        "anbieter": anbieter,
        "tarif_name": tarif,
        "tarif_id": tarif_id,
        "tarif_id_guete": "hoch",
        "tarif_monatlich": 24.99,
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": rate,
        "laufzeit_monate": laufzeit,
        "anschlusspreis": 0.0,
        "zustand": "neu",
        "rabatte": [],
        "quelle_url": f"https://example.de/{anbieter.lower()}",
        "abgerufen_am": tag,
        "first_seen": tag,
        "last_verified": tag,
        "quelle_art": "klick",
        "beleg_id": beleg_id,
        "beleg_status": "offen",
    }


def _bild(anbieter_id: str, tag: date = TAG) -> str:
    return dateiname(MODELL, anbieter_id, tag)


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """o2: eindeutig (ein Satz). Telekom: zwei gleich teure Sätze. congstar: Bild von
    gestern, Satz von heute. Vodafone: Bild, aber keine Klick-Messung."""
    site = kopf_zeitraum._baue(tmp_path_factory.mktemp("beleg_position"))
    wurzel = site.parent
    state = wurzel / "data" / "state"
    farbe = "apple-iphone-17-pro-256gb-orange"
    saetze = [
        _satz("o2", "O2 Mobile Klein", "o2:klein", 24, 18.0, ID_O2),
        _satz("Telekom", "MagentaMobil S", "tk:klein", 24, 12.0, ID_TK_1),
        _satz("Telekom", "MagentaMobil S", "tk:klein", 24, 12.0, ID_TK_2, sku=farbe),
        _satz("congstar", "Allnet Flat XS", "cs:klein", 24, 15.0, ID_CS),
    ]
    vodafone = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    vodafone = [b for b in vodafone["buendel"] if b["anbieter"] == "Vodafone"]
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": [*saetze, *vodafone], "sim_only": []}),
        encoding="utf-8",
    )
    anhaenge = {
        f"belege-{HEUTE}": [_bild("o2"), _bild("telekom"), _bild("vodafone")],
        f"belege-{GESTERN.isoformat()}": [_bild("congstar", GESTERN)],
    }
    schreibe(state / MANIFEST_NAME, baue_manifest(anhaenge, TAG))
    render_site(site, wurzel / "data" / "reports")
    return site


@pytest.fixture(scope="module")
def seite(site) -> BeautifulSoup:
    return BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


@pytest.fixture(scope="module")
def lager(site) -> BeautifulSoup:
    return BeautifulSoup(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        "html.parser",
    )


def _text(element) -> str:
    """Der Text eines Elements samt ``<template>``-Inhalt."""
    return "".join(element.find_all(string=True)).strip()


def _zeilen(*dom: BeautifulSoup) -> dict[str, list]:
    je_anbieter: dict[str, list] = {}
    for teil in dom:
        for z in teil.select(".gr-bnd"):
            je_anbieter.setdefault(z["data-anbieter"], []).append(z)
    return je_anbieter


def test_die_eindeutige_zeile_traegt_ihr_bild(lager, seite):
    """Positiv: o2 hat einen Satz, das Bild gehört genau zu dieser Zeile."""
    je_anbieter = _zeilen(lager, seite)
    assert je_anbieter["o2"], "Gegenprobe: die Fixture hat o2-Zeilen"
    for z in je_anbieter["o2"]:
        bild = z.select_one("details.gr-belege--zeile img[data-src]")
        assert bild is not None, z
        assert f"/belege-{HEUTE}/{_bild('o2')}" in bild["data-src"]
        assert z.select_one(".gr-kk-marke--zeilenbeleg") is not None
        assert VERMERK not in _text(z)


def test_unklare_zuordnung_zeigt_keinen_link_sondern_den_vermerk(lager, seite):
    """Fail-closed: gleich teure Sätze (Telekom), neuerer Abruf als das Bild (congstar)
    und fehlende Klick-Messung (Vodafone) ergeben nie ein Bild an einer Zeile, obwohl
    die Paare ein Seiten-Bild haben."""
    je_anbieter = _zeilen(lager, seite)
    for anbieter in ("Telekom", "congstar", "Vodafone"):
        assert je_anbieter[anbieter], f"Gegenprobe: Zeilen für {anbieter}"
        for z in je_anbieter[anbieter]:
            assert z.select("details.gr-belege--zeile, img, a[href*='releases']") == []
            assert z.select(".gr-kk-marke--zeilenbeleg") == []
            assert _text(z.select_one(".gr-beleg-zeilenfehlt")) == VERMERK


def test_quote_nennt_je_anbieter_zeilen_nicht_paare(lager, seite):
    """Die Seite zählt Zeilen je Anbieter, ehrlich auch bei 0."""
    je_anbieter = _zeilen(lager)
    n = {a: len(z) for a, z in je_anbieter.items()}
    satz = seite.select_one("#gr-zeilenquote").get_text(strip=True)
    erwartet = (
        "Screenshot genau zur Preiszeile (Gerät, Tarif und Laufzeit stimmen): "
        f"congstar 0 von {n['congstar']} · o2 {n['o2']} von {n['o2']} · "
        f"Telekom 0 von {n['Telekom']} · Vodafone 0 von {n['Vodafone']}; "
        f"zusammen {n['o2']} von {sum(n.values())}."
    )
    assert satz == erwartet
    assert "Paaren" not in satz


def test_paar_nennt_seine_zeilen_mit_bild(lager, seite):
    je_anbieter = {
        li.select_one(".gr-beleg-anbieter").get_text(strip=True): li
        for li in seite.select("#gr-bnd-gruppe .gr-beleg-paare li")
    }
    n_o2 = len(_zeilen(lager)["o2"])
    assert je_anbieter["o2"].select_one(".gr-beleg-zeilen").get_text(strip=True) == (
        f"{n_o2} von {n_o2} Preiszeilen mit eigenem Screenshot"
    )
    assert "0 von" in je_anbieter["Telekom"].select_one(".gr-beleg-zeilen").text


def _roh(beleg_id, rate, tag=HEUTE, **extra):
    satz = _satz("o2", "O2 Mobile Klein", "o2:klein", 24, rate, beleg_id, tag=tag)
    return {**satz, **extra}


def test_eindeutiger_spitzenreiter_ist_die_position():
    wahl = schluessel.position_des_bildes(
        [_roh("1" * 64, 30.0), _roh("2" * 64, 18.0)], HEUTE
    )
    assert wahl.satz is not None and wahl.satz["beleg_id"] == "2" * 64


@pytest.mark.parametrize(
    ("saetze", "grund"),
    [
        ([], schluessel.GRUND_KEIN_KLICKSATZ),
        ([_roh("", 18.0)], schluessel.GRUND_KEIN_KLICKSATZ),
        (
            [_roh("1" * 64, 18.0), _roh("2" * 64, 18.0)],
            schluessel.GRUND_GLEICHSTAND,
        ),
        (
            [_roh("1" * 64, 18.0), _roh("2" * 64, 30.0, tag="2026-09-12")],
            schluessel.GRUND_BESTAND_NEUER,
        ),
        ([_roh("1" * 64, 18.0, tag="2026-09-10")], schluessel.GRUND_KEIN_SATZ_VOM_TAG),
        ([_roh("1" * 64, 18.0, geraet_monatsrate=None)], schluessel.GRUND_KEINE_KOSTEN),
    ],
)
def test_ohne_beweis_keine_position(saetze, grund):
    wahl = schluessel.position_des_bildes(saetze, HEUTE)
    assert wahl.satz is None
    assert wahl.grund == grund


def _beleg() -> zeilen.Zeilenbeleg:
    return zeilen.Zeilenbeleg(
        geraet_id=MODELL,
        anbieter_id="o2",
        sku_id="apple-iphone-17-pro-256gb-ohne-farbe",
        tarif="O2 Mobile Klein",
        tarif_id="o2:klein",
        raten_laufzeit=24,
        beleg_id=ID_O2,
        datum=HEUTE,
        gross=False,
        url="https://example.de/bild.webp",
    )


def _karte(**abweichung) -> dict:
    karte = {
        "beleg_id": ID_O2,
        "modell_id": MODELL,
        "anbieter": "o2",
        "sku_id": "apple-iphone-17-pro-256gb-ohne-farbe",
        "tarif": "O2 Mobile Klein",
        "tarif_id": "o2:klein",
        "raten_laufzeit": 24,
    }
    return {**karte, **abweichung}


def test_passende_karte_wird_angenommen():
    assert zeilen.passt(_beleg(), _karte())


@pytest.mark.parametrize(
    "abweichung",
    [
        {"modell_id": "apple-iphone-17-pro-512"},
        {"anbieter": "Telekom"},
        {"sku_id": "apple-iphone-17-pro-256gb-orange"},
        {"tarif": "O2 Mobile Groß"},
        {"tarif_id": "o2:gross"},
        {"raten_laufzeit": 36},
        {"beleg_id": "e" * 64},
        {"beleg_id": ""},
    ],
)
def test_beleg_mit_abweichendem_geraet_oder_tarif_wird_abgelehnt(abweichung):
    """Das Bild einer anderen Variante oder eines anderen Tarifs ist nie ein Beleg."""
    assert not zeilen.passt(_beleg(), _karte(**abweichung))
    fuer = zeilen.zeilenbeleg_fuer({ID_O2: _beleg()})
    assert fuer(_karte(**abweichung)) is None
    assert fuer(_karte()) is not None


def test_bestand_ohne_datei_hat_keine_saetze_ein_kaputter_ist_ein_fehler(tmp_path):
    datei = tmp_path / "geraete_tco.json"
    assert schluessel.lies_buendel(datei) == []
    datei.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(ValueError, match="geraete_tco.json"):
        schluessel.lies_buendel(datei)
