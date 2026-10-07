"""Klick-Karte 1&1 gegen eine gespeicherte echte Produktseite, ohne Browser.

1&1 nennt den Preis in keiner Antwort, sondern in der Globalen ``hwdVariantsPrices``
der Seite (Cent je ``product-<FARBE>-<Speicher>``). Kein Mitschnitt der
Klick-Erkundung hält das Dokument; Beleg ist darum die Produktseite iPhone 17 Pro vom
08.09.2026 (``einsundeins_produktseite_iphone_17_pro.html.gz``, Herkunft in
``tests/fixtures/geraete/_herkunft.json``). Ihr Preis 44,99 € ist derselbe, den die
Erkundung vom 07.10.2026 sichtbar las (Zweig ``klick-erkundung``, Commit a9b45f5a,
``erkundung/1und1/2026-10-07/preise-1.json`` Kandidat 5 „44 , 99 €/Monat“). Die
Selektoren der Karte laufen hier über BeautifulSoup auf derselben Seite. Gegenprobe:
512 GB liest seinen eigenen Betrag, nie den eines Zubehör-Bündels, und eine Farbe,
die es nicht gibt, liest keinen.
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import pytest
from bs4 import BeautifulSoup

from telco_radar.collect.geraete.klickecho import (
    feldwert,
    lies_antwort,
    pruefe_echo,
    variante_aus,
)
from telco_radar.collect.geraete.klickkartenprobe import GELADEN, lade_karte
from telco_radar.collect.geraete.klicktext import Buendelwerte, Preiswerte

KARTEN = Path(__file__).resolve().parents[1] / "config" / "klickkarten"
SEITE = (
    Path(__file__).parent
    / "fixtures"
    / "geraete"
    / "einsundeins_produktseite_iphone_17_pro.html.gz"
)
ADRESSE = "https://mobile.1und1.de/iphone-17-pro"
PREISE = re.compile(r"hwdVariantsPrices\s*=\s*\{(.*?)\};", re.S)
EINTRAG = re.compile(r"'([^']+)'\s*:\s*\[\s*(\d+)\s*,?\s*\]")
LAUFZEIT = re.compile(r"window\.currentHardwareOfferDuration\s*=\s*'(\d+)'")


@pytest.fixture(scope="module")
def karte():
    lage = lade_karte(KARTEN, "1und1")
    assert (lage.status, lage.grund) == (GELADEN, None)
    return lage.karte


@pytest.fixture(scope="module")
def html() -> str:
    return gzip.decompress(SEITE.read_bytes()).decode("utf-8")


@pytest.fixture(scope="module")
def dom(html):
    return BeautifulSoup(html, "html.parser")


@pytest.fixture(scope="module")
def globale(html) -> dict:
    """Was ``window.hwdVariantsPrices`` und die Laufzeit der Seite liefern."""
    preise = {k: [int(v)] for k, v in EINTRAG.findall(PREISE.search(html)[1])}
    return {
        "hwdVariantsPrices": preise,
        "currentHardwareOfferDuration": LAUFZEIT.search(html)[1],
    }


def _seitenwert(dom, karte, name: str) -> str | None:
    wert = karte.seite[name]
    element = dom.select_one(wert.selektor)
    roh = element.get(wert.attribut) if wert.attribut else element.get_text(" ")
    if wert.parameter is not None:
        roh = parse_qs(urlparse(urljoin(ADRESSE, roh)).query)[wert.parameter][0]
    return roh


def test_selektoren_der_karte_treffen_die_seite(karte, dom):
    knoepfe = dom.select(karte.knoepfe["speicher"].selektor)
    werte = [k.select_one(karte.knoepfe["speicher"].wert_in)["value"] for k in knoepfe]
    gewaehlt = [k for k in knoepfe if k.select_one("input:checked") is not None]
    kanarie = dom.select_one(karte.kanarie.selektor)

    assert werte[:2] == ["256", "512"]
    assert len(gewaehlt) == 1
    assert "iPhone 17 Pro" in kanarie[karte.kanarie.attribut]
    assert len(dom.select(karte.vorbereitung[0].klick)) == 1
    assert {n: _seitenwert(dom, karte, n) for n in ("speicher", "tarif", "farbe")} == {
        "speicher": "256",
        "tarif": "tariff-anf-s-mvl",
        "farbe": "COSMIC_ORANGE",
    }


def test_buendelbetrag_aus_text_und_globaler_stimmt_ueberein(karte, dom, globale):
    platz = {
        "speicher": "256",
        "tarif": "tariff-anf-s-mvl",
        "laufzeit": "36",
        "farbe": "COSMIC_ORANGE",
    }
    text = dom.select_one(karte.zusammenfassung).get_text(" ", strip=True)
    treffer = karte.textlesung.muster["buendelbetrag"].muster.search(text)
    im_text = feldwert("buendelbetrag", "".join(treffer[1].split()))
    lesung = lies_antwort(globale, karte.antwort, None, platz)
    variante = variante_aus("256", "tariff-anf-s-mvl", 36)

    echo = pruefe_echo(
        variante,
        variante,
        Preiswerte(),
        lesung,
        buendel=Buendelwerte(buendelbetrag=im_text),
        entfallen=karte.entfallen,
    )

    assert text.startswith("44 , 99 €/Monat")
    assert dict(lesung.variante) == {"laufzeit": 36}
    assert echo.stimmt, echo.befunde
    assert echo.buendel == Buendelwerte(buendelbetrag=44.99)
    assert "einmalzahlung" in echo.luecken and "rate" not in echo.luecken


def test_gegenprobe_anderer_speicher_kein_buendel_keine_fremde_farbe(karte, globale):
    def betrag(speicher: str, farbe: str) -> float | None:
        platz = {"speicher": speicher, "farbe": farbe}
        return lies_antwort(globale, karte.antwort, None, platz).buendel.buendelbetrag

    preise = globale["hwdVariantsPrices"]
    buendel = preise[
        "product-COSMIC_ORANGE-512-bundle-hw-apple-iphone-17-pro-30996563240e-WEISS-0"
    ]

    eigener = preise["product-COSMIC_ORANGE-512"][0]
    assert betrag("512", "COSMIC_ORANGE") == eigener / 100
    assert betrag("512", "COSMIC_ORANGE") != buendel[0] / 100
    assert betrag("256", "VIOLETT") is None


def test_laufzeit_der_seite_ist_echo_der_festen_laufzeit(karte, globale):
    platz = {"speicher": "256", "farbe": "COSMIC_ORANGE"}
    vierundzwanzig = {**globale, "currentHardwareOfferDuration": "24"}
    lesung = lies_antwort(vierundzwanzig, karte.antwort, None, platz)
    variante = variante_aus("256", "tariff-anf-s-mvl", 36)

    echo = pruefe_echo(
        variante,
        variante,
        Preiswerte(),
        lesung,
        buendel=Buendelwerte(buendelbetrag=44.99),
        entfallen=karte.entfallen,
    )

    assert karte.knoepfe["laufzeit"].fest == "36"
    assert [b.feld for b in echo.befunde] == ["antwort.laufzeit"]
