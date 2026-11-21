"""o2: ein Gerät mit eigenem Anschlusspreis bekommt trotzdem alle Tarife.

DER BEFUND (Gerätelauf 44858465074, 21.11.2026, und lokaler Lauf am selben Tag)
------------------------------------------------------------------------------
Xiaomi Redmi 17 128 GB: die Antwort mit „O2 Mobile on Demand M“ berechnet 39,99 €
Anschlusspreis, die Referenz des Laufs (erstes Gerät) nennt für denselben Tarif
0,00 €. ``o2_referenz.passt`` prüfte den Anschlusspreis mit, die Antwort zählte als
``referenz_widerspricht``, und es blieb nur der gemessene Tarif: 2 statt 24 Zeilen.
Der Klick-Lauf las für dasselbe Gerät L, Unlimited M und Unlimited L (6 Zeilen), die
der Adapter nicht hatte. Seit #179 nimmt kein abgeleiteter Satz den Anschlusspreis
mehr aus der Referenz; aus ihr kommt nur der Slug. Ob abgeleitet wird, entscheidet
darum der Slug.

DIE FUSSNOTE TRÄGT HIER NICHT
-----------------------------
Dieselbe Antwort zeigt, dass eine Geräteaktion den Anschlusspreis auch ÜBER den
Listenpreis der Fußnote heben kann: Fußnote „Einmaliger Anschlusspreis 0 €“, berechnet
39,99 €. Hebt die Antwort ihren eigenen Tarif über dessen Fußnote, gilt die Fußnote
auch für die übrigen Tarife dieser Antwort nicht als Beleg: ihr Anschlusspreis ist
die Lücke.

DIE FIXTURE (echter Abruf 21.11.2026, TelcoRadar/1.0, gekürzt, Werte unverändert)
--------------------------------------------------------------------------------
``o2_redmi17_tarifoptionen_20261121.json.gz``, gewählt „on Demand M“, 36 Raten.
"""

import gzip
import re
from pathlib import Path

import pytest

from telco_radar.collect.geraete import o2, o2_anschluss

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_DATEI = "o2_redmi17_tarifoptionen_20261121.json.gz"
_URL = (
    "https://www.o2online.de/e-shop/xiaomi/xiaomi-redmi-17-128gb-blue-5g-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36"
    "&vertragsart=ratenzahlung&tarif=o2-mobile-on-demand-m"
)
_TAG = re.compile(r"<[^>]+>")


def _anzeige(option: dict) -> str:
    return " ".join(_TAG.sub("", option.get("displayValue") or "").split())


def _slug(anzeige: str) -> str:
    name = re.sub(r"\s+mit\s+.*$", "", anzeige.replace("O2", "o2"))
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@pytest.fixture(scope="module")
def antwort() -> dict:
    with gzip.open(_FIX / _DATEI, "rt", encoding="utf-8") as fh:
        return o2.lies_konfiguration(fh.read())


@pytest.fixture(scope="module")
def referenz(antwort: dict) -> dict:
    """Referenz wie im Lauf vom 21.11.2026: jeder Tarif mit Slug, Anschluss vom
    ersten Gerät (Mobile S 39,99 €, sonst 0,00 €)."""
    return {
        _anzeige(o): {
            "slug": _slug(_anzeige(o)),
            "anschluss": 39.99 if _slug(_anzeige(o)) == "o2-mobile-s" else 0.0,
        }
        for o in antwort["tariff"]["tariffOptions"]
    }


@pytest.fixture(scope="module")
def saetze(antwort: dict, referenz: dict) -> dict:
    zaehler: dict = {}
    basis = {"strukturierter_name": "Xiaomi Redmi 17 5G", "sku": "x", "url": _URL}
    roh = o2.saetze_aus_konfiguration(antwort, basis, referenz, _URL, zaehler)
    return {"saetze": {s["tarif_slug"]: s for s in roh}, "zaehler": zaehler}


def test_eigener_anschluss_ist_gemessen(saetze):
    eigen = saetze["saetze"]["o2-mobile-on-demand-m"]
    assert "herleitung" not in eigen
    assert eigen["anschlusspreis"] == 39.99
    assert eigen["geraet_monatsrate"] == 7.0


def test_abweichender_anschluss_haelt_die_ableitung_nicht_auf(saetze):
    """Vorher: nur der gemessene Satz (``referenz_widerspricht``)."""
    assert "referenz_widerspricht" not in saetze["zaehler"]
    assert len(saetze["saetze"]) == 7
    assert saetze["zaehler"]["abgeleitet"] == 6


def test_abgeleitete_tarife_wie_die_klick_messung(saetze):
    """Klick-Lauf 21.11.2026 (o2-tarife.json), 36 Raten, Rate 7,00 €: L 24,99 €,
    Unlimited M 29,99 €, Unlimited L 39,99 €."""
    tarif = {k: s["tarif_monatlich"] for k, s in saetze["saetze"].items()}
    assert tarif["o2-mobile-l"] == 24.99
    assert tarif["o2-mobile-unlimited-m"] == 29.99
    assert tarif["o2-mobile-unlimited-l"] == 39.99
    for s in saetze["saetze"].values():
        assert (s["geraet_zuzahlung"], s["geraet_monatsrate"]) == (1.0, 7.0)


def test_fussnote_unter_dem_berechneten_betrag_belegt_nichts(saetze):
    abgeleitet = [s for s in saetze["saetze"].values() if s.get("herleitung")]
    assert [s["anschlusspreis"] for s in abgeleitet] == [None] * 6
    assert saetze["zaehler"][o2_anschluss.ZAEHLER_ANSCHLUSS_OFFEN] == 6


def test_gegenprobe_fussnote_nennt_null_berechnet_ist_mehr(antwort):
    gewaehlt = next(o for o in antwort["tariff"]["tariffOptions"] if o["selected"])
    assert o2_anschluss.listen_anschluss(gewaehlt) == 0.0
    assert o2._gemessen(antwort)["anschluss"] == 39.99


def test_gegenprobe_anderer_slug_bleibt_ohne_ableitung(antwort, referenz):
    """Nennt die Referenz den eigenen Tarif unter einem anderen Slug, wird weiter
    nicht abgeleitet."""
    falsch = {**referenz}
    optionen = antwort["tariff"]["tariffOptions"]
    eigen = _anzeige(next(o for o in optionen if o["selected"]))
    falsch[eigen] = {"slug": "anderer-slug", "anschluss": 39.99}
    zaehler: dict = {}
    basis = {"strukturierter_name": "Xiaomi Redmi 17 5G", "sku": "x", "url": _URL}
    roh = o2.saetze_aus_konfiguration(antwort, basis, falsch, _URL, zaehler)
    assert len(roh) == 1
    assert zaehler["referenz_widerspricht"] == 1
