"""Zweiter o2-Job: Karte o2-tarife.yaml und Seiten in config/klick_tageslauf.yaml.

Die Produktseite zeigt einen Tarif ohne Kachel nur, wenn er als ``tarif=`` in der
Adresse steht, dann gewählt (Erkundung 10.10.2026, Zweig klick-erkundung,
erkundung/o2/2026-10-10/bedienelemente-2.json: Input select-tariff aria-checked true am
Label „O2 Mobile Unlimited M mit 100 MBit/s mtl. 66,49 €“). Die BEISPIEL-Seite bildet
die vier Kacheln dieser Erkundung von Hand nach. Die Tarif-Slugs stammen aus o2s eigener
Antwort (tests/fixtures/geraete/o2_vertiefung_iphone17pro.json.gz).
"""

from __future__ import annotations

import gzip
import re
from dataclasses import replace
from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klickoptionen import lies_optionen
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele

WURZEL = Path(__file__).parent.parent
KARTEN = WURZEL / "config" / "klickkarten"
O2 = lade_klickkarte(KARTEN / "o2.yaml")
TARIFE = lade_klickkarte(KARTEN / "o2-tarife.yaml")
VERTIEFUNG = (
    WURZEL / "tests" / "fixtures" / "geraete" / "o2_vertiefung_iphone17pro.json.gz"
)
KACHELN = (
    ("786", "O2 Mobile Unlimited M Plus mit 100 MBit/s mtl. 56,49 €", False),
    ("432", "O2 Mobile L Plus mit 150 GB+ mtl. 56,49 €", False),
    ("846", "O2 Mobile on Demand M Plus mit 50 GB+ mtl. 46,49 €", False),
    ("510", "O2 Mobile Unlimited M mit 100 MBit/s mtl. 66,49 €", True),
)
TARIF_IN_ADRESSE = re.compile(r"[?&]tarif=([^&]+)")
SLUG = re.compile(r'(o2-mobile-[a-z]+(?:-[a-z]+)*)\\"')


def _seite() -> str:
    kacheln = "".join(
        f'<tef-choice-panel><input type="radio" name="select-tariff"'
        f' id="choice-panel-input-{n}"{" checked" if an else ""}>'
        f'<label for="choice-panel-input-{n}">{text}</label></tef-choice-panel>'
        for n, text, an in KACHELN
    )
    return (
        "<!doctype html><html><body>"
        "<p>BEISPIEL: von Hand geschrieben, kein echter Anbieter.</p>"
        f'<div id="content">{kacheln}</div></body></html>'
    )


def _tarife(chromium, karte) -> list[tuple[str | None, bool]]:
    seite = chromium.new_page()
    try:
        seite.set_content(_seite())
        return [(o.wert, o.gewaehlt) for o in lies_optionen(seite, karte, "tarif")]
    finally:
        seite.close()


@pytest.mark.browser
def test_nur_der_tarif_aus_der_adresse_ist_option(chromium):
    assert _tarife(chromium, TARIFE) == [("O2 Mobile Unlimited M mit 100 MBit/s", True)]


@pytest.mark.browser
def test_gegenprobe_die_o2_karte_sieht_alle_vier_kacheln(chromium):
    assert len(_tarife(chromium, O2)) == len(KACHELN)


def test_karte_gleicht_o2_bis_auf_den_tarifknopf():
    knoepfe = {**TARIFE.knoepfe, "tarif": O2.knoepfe["tarif"]}

    assert replace(TARIFE, knoepfe=knoepfe) == O2
    assert TARIFE.knoepfe["tarif"] != O2.knoepfe["tarif"]


def _ziele():
    return {
        z.schluessel: z for z in lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    }


def test_jeder_tarif_ohne_kachel_je_geraet_einmal():
    ziele = _ziele()
    antwort = gzip.decompress(VERTIEFUNG.read_bytes()).decode()
    alle = set(SLUG.findall(antwort))
    ohne_kachel = alle - {
        "o2-mobile-unlimited-l-plus",
        "o2-mobile-unlimited-m-plus",
        "o2-mobile-l-plus",
        "o2-mobile-on-demand-m-plus",
    }
    schon = {
        (s.geraet, TARIF_IN_ADRESSE.search(s.adresse)[1]) for s in ziele["o2"].seiten
    }
    geraete = {s.geraet for s in ziele["o2"].seiten}
    seiten = ziele["o2-tarife"].seiten + ziele["o2-tarife-2"].seiten
    paare = [(s.geraet, TARIF_IN_ADRESSE.search(s.adresse)[1]) for s in seiten]

    assert len(ohne_kachel) == 8
    assert len(paare) == len(set(paare))
    assert set(paare) == {(g, t) for g in geraete for t in ohne_kachel} - schon
    assert ziele["o2-tarife"].name == ziele["o2"].name
    assert ziele["o2-tarife-2"].name == ziele["o2"].name
    assert ziele["o2-tarife-2"].kartenschluessel == "o2-tarife"
