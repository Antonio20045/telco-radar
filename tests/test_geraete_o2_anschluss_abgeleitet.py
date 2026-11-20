"""o2: Anschlusspreis abgeleiteter Tarife aus der eigenen Antwort, nicht der Referenz.

DER BEFUND (Gegenprobe 20.11.2026, PR #177)
-------------------------------------------
iPhone 14 128 GB (erneuert), „O2 Mobile Unlimited S Special Plus“, 24 und 36 Raten:
gespeichert 39,99 € Anschlusspreis, die Seite zeigt 0,00 € (39,99 € durchgestrichen).
Die Zeilen waren abgeleitet (``tarifsumme_minus_geraeterate``) aus der Antwort mit
„O2 Mobile on Demand M Plus“; den Anschlusspreis nahmen sie aus der Referenz, also
vom ersten Gerät des Laufs.

DIE FIXTURE (echter Abruf 20.11.2026, TelcoRadar/1.0, gekürzt, Werte unverändert)
--------------------------------------------------------------------------------
``o2_iphone14_erneuert_tarifoptionen_20261120.json.gz``: dieselbe Antwort, aus der
die Zeilen am 20.11. abgeleitet wurden (iPhone 14 erneuert, 24 Raten, gewählt
„on Demand M Plus“). Ihre Preiszusammenfassung nennt den Anschlusspreis nur für den
gewählten Tarif. Für jeden anderen Tarif steht in dessen Fußnote nur der Listenpreis
(„Einmaliger Anschlusspreis 39,99 €“ bei S Special Plus und Mobile S, „0 €“ bei den
übrigen, keine Angabe bei der Zweitkarte „O2 Mobile Special“).
"""

import gzip
import re
from pathlib import Path

import pytest

from telco_radar.collect.geraete import o2, o2_anschluss

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_DATEI = "o2_iphone14_erneuert_tarifoptionen_20261120.json.gz"
_URL = (
    "https://www.o2online.de/e-shop/apple/apple-iphone-14-128gb-mitternacht-erneuert-"
    "details?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=24"
    "&vertragsart=ratenzahlung&tarif=o2-mobile-on-demand-m-plus"
)
_TAG = re.compile(r"<[^>]+>")
_S_SPECIAL_PLUS = "o2-mobile-unlimited-s-special-plus"
_MOBILE_S = "o2-mobile-s"
_SPECIAL = "o2-mobile-special"
_L_PLUS = "o2-mobile-unlimited-l-plus"


def _anzeige(option: dict) -> str:
    return " ".join(_TAG.sub("", option.get("displayValue") or "").split())


def _slug(anzeige: str) -> str:
    """Slug wie in der Referenz des Laufs (Kleinschreibung, Bindestriche)."""
    name = re.sub(r"\s+mit\s+.*$", "", anzeige.replace("O2", "o2"))
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@pytest.fixture(scope="module")
def antwort() -> dict:
    with gzip.open(_FIX / _DATEI, "rt", encoding="utf-8") as fh:
        return o2.lies_konfiguration(fh.read())


@pytest.fixture(scope="module")
def referenz(antwort: dict) -> dict:
    """Referenz wie im Lauf vom 20.11.2026: jeder Tarif bekannt, S Special Plus und
    Mobile S mit 39,99 € vom ersten Gerät, der Rest mit 0,00 €."""
    tarife = {}
    for option in antwort["tariff"]["tariffOptions"]:
        anzeige = _anzeige(option)
        slug = _slug(anzeige)
        teuer = slug in (_S_SPECIAL_PLUS, _MOBILE_S)
        tarife[anzeige] = {"slug": slug, "anschluss": 39.99 if teuer else 0.0}
    return tarife


@pytest.fixture(scope="module")
def saetze(antwort: dict, referenz: dict) -> dict:
    zaehler: dict = {}
    basis = {"strukturierter_name": "Apple iPhone 14", "sku": "x", "url": _URL}
    roh = o2.saetze_aus_konfiguration(antwort, basis, referenz, _URL, zaehler)
    return {"saetze": {s["tarif_slug"]: s for s in roh}, "zaehler": zaehler}


def test_gemessener_tarif_traegt_den_anschluss_seiner_zusammenfassung(saetze):
    eigen = saetze["saetze"]["o2-mobile-on-demand-m-plus"]
    assert "herleitung" not in eigen
    assert eigen["anschlusspreis"] == 0.0


def test_listenpreis_ueber_null_ist_eine_luecke_nicht_der_referenzwert(saetze):
    """S Special Plus: Fußnote 39,99 €, die Seite berechnet für dieses Gerät 0,00 €.
    Die Antwort nennt den berechneten Betrag nicht, also keiner (vorher 39,99 €)."""
    for slug in (_S_SPECIAL_PLUS, _MOBILE_S):
        satz = saetze["saetze"][slug]
        assert satz["herleitung"] == o2.HERLEITUNG_TARIFSUMME
        assert satz["anschlusspreis"] is None, slug


def test_ohne_angabe_in_der_antwort_ist_der_anschluss_eine_luecke(saetze):
    assert saetze["saetze"][_SPECIAL]["anschlusspreis"] is None


def test_listenpreis_null_ist_der_berechnete_betrag(saetze):
    """Eine Aktion kann den Anschlusspreis nur senken; 0 € in der Fußnote ist 0 €."""
    assert saetze["saetze"][_L_PLUS]["anschlusspreis"] == 0.0


def test_jede_luecke_ist_gezaehlt(saetze):
    offen = [s for s in saetze["saetze"].values() if s["anschlusspreis"] is None]
    assert len(offen) == 3
    assert saetze["zaehler"][o2_anschluss.ZAEHLER_ANSCHLUSS_OFFEN] == len(offen)


def test_listenpreis_der_fussnote(antwort):
    """Gegenprobe des Lesers: 39,99 € und 0 € stehen in der Fußnote, die Zweitkarte
    nennt keinen."""
    je_slug = {
        _slug(_anzeige(o)): o2_anschluss.listen_anschluss(o)
        for o in antwort["tariff"]["tariffOptions"]
    }
    assert je_slug[_S_SPECIAL_PLUS] == 39.99
    assert je_slug[_MOBILE_S] == 39.99
    assert je_slug[_L_PLUS] == 0.0
    assert je_slug[_SPECIAL] is None
