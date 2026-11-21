"""o2: jeder Tarif der Antwort wird ein Bündel, ein nicht angebotener keiner.

DER BEFUND (21.11.2026)
-----------------------
Die Produktseite des Galaxy S26 256 GB zeigt in der Tarifauswahl (Neukunden) fünf
Kacheln, alle „Plus“, vorgewählt „O2 Mobile on Demand M Plus mit 50 GB+“ für 44,99 €
im Monat (Browser, 21.11.2026). Die Tagesdatei vom 21.11. hatte für dieses Gerät nur
die sieben Tarife ohne „Plus“: der Klick-Lauf ersetzte die Adapterzeilen (seit #191
misst o2 nur der Adapter). Die Konfigurationsantwort der Seite nennt zwölf Optionen,
die fünf der Kacheln und sieben ohne „Plus“, die die Seite über ihre Adresse wählt.
Ein lokaler Adapterlauf am selben Tag las 190 Antworten mit 2.230 Optionen und
erzeugte zu jeder ein Bündel.

Jede Option trägt `disabled`; die Seite rendert damit ihren Knopf. Eine Option mit
`disabled: true` bietet o2 zu diesem Gerät nicht an: sie wird kein Bündel, wird nicht
geprobt und altert im Bestand. Am 21.11. war keine der 2.230 so markiert.

DIE FIXTURE (echter Abruf 21.11.2026, TelcoRadar/1.0, gekürzt, Werte unverändert)
--------------------------------------------------------------------------------
``o2_galaxy_s26_tarifoptionen_20261121.json.gz``: Galaxy S26 256 GB cobalt violet,
36 Raten, gewählt „on Demand M Plus“. Gegenprobe im Browser (Preiszusammenfassung):
on Demand M Plus 33,50 € + 11,49 €, Anzahlung 1,00 €, Anschluss 0,00 €; Unlimited M
Plus (S26+ 256 GB) und L Plus (24 Raten) siehe PR-Text.
"""

from __future__ import annotations

import copy
import gzip
import re
from pathlib import Path

import pytest

from telco_radar.collect.geraete import o2
from telco_radar.collect.geraete.o2_referenz import Referenzstand

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_DATEI = "o2_galaxy_s26_tarifoptionen_20261121.json.gz"
_URL = (
    "https://www.o2online.de/e-shop/samsung/samsung-galaxy-s26-256gb-cobalt-violet"
    "-details?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36"
    "&vertragsart=ratenzahlung&tarif=o2-mobile-on-demand-m-plus"
)
_TAG = re.compile(r"<[^>]+>")
_PLUS = (
    "O2 Mobile Unlimited L Plus mit 300 MBit/s",
    "O2 Mobile Unlimited M Plus mit 100 MBit/s",
    "O2 Mobile Unlimited S Special Plus mit 15 MBit/s",
    "O2 Mobile L Plus mit 150 GB+",
    "O2 Mobile on Demand M Plus mit 50 GB+",
)


def _anzeige(option: dict) -> str:
    return " ".join(_TAG.sub("", option.get("displayValue") or "").split())


def _slug(anzeige: str) -> str:
    name = re.sub(r"\s+mit\s+.*$", "", anzeige.replace("O2", "o2"))
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@pytest.fixture(scope="module")
def antwort() -> dict:
    with gzip.open(_FIX / _DATEI, "rt", encoding="utf-8") as fh:
        return o2.lies_konfiguration(fh.read())


def _referenz(antwort: dict) -> dict:
    return {
        _anzeige(o): {"slug": _slug(_anzeige(o)), "anschluss": 0.0}
        for o in antwort["tariff"]["tariffOptions"]
    }


def _saetze(antwort: dict) -> tuple[dict, dict]:
    zaehler: dict = {}
    basis = {"strukturierter_name": "Samsung Galaxy S26", "sku": "x", "url": _URL}
    roh = o2.saetze_aus_konfiguration(antwort, basis, _referenz(antwort), _URL, zaehler)
    return {s["tarif_slug"]: s for s in roh}, zaehler


def _abgeschaltet(antwort: dict, anzeige: str) -> dict:
    kopie = copy.deepcopy(antwort)
    for option in kopie["tariff"]["tariffOptions"]:
        if _anzeige(option) == anzeige:
            option["disabled"] = True
    return kopie


def test_die_antwort_nennt_zwoelf_tarife_davon_fuenf_plus(antwort):
    anzeigen = [_anzeige(o) for o in antwort["tariff"]["tariffOptions"]]
    assert len(anzeigen) == 12
    assert set(_PLUS) <= set(anzeigen)
    assert all(o.get("disabled") is False for o in antwort["tariff"]["tariffOptions"])


def test_jeder_angebotene_tarif_wird_ein_buendel(antwort):
    saetze, zaehler = _saetze(antwort)
    assert len(saetze) == 12
    assert (zaehler["angeboten"], zaehler["nicht_erfasst"]) == (12, 0)
    assert "nicht_angeboten" not in zaehler


def test_der_vorgewaehlte_plus_tarif_ist_gemessen_wie_die_seite(antwort):
    s = _saetze(antwort)[0]["o2-mobile-on-demand-m-plus"]
    assert s.get("herleitung") is None
    werte = (s["geraet_monatsrate"], s["tarif_monatlich"], s["geraet_zuzahlung"])
    assert werte == (33.5, 11.49, 1.0)
    assert s["anschlusspreis"] == 0.0
    assert s["laufzeit_monate"] == 36


def test_plus_tarife_sind_abgeleitet_mit_eigener_monatssumme(antwort):
    """Monatssumme der Option minus Gerätrate 33,50 €: 49,99 € (L Plus), 59,99 €
    (Unlimited L Plus), 53,49 € (on Demand M ohne Plus)."""
    saetze = _saetze(antwort)[0]
    assert saetze["o2-mobile-l-plus"]["tarif_monatlich"] == pytest.approx(16.49)
    assert saetze["o2-mobile-unlimited-l-plus"]["tarif_monatlich"] == pytest.approx(
        26.49
    )
    assert saetze["o2-mobile-on-demand-m"]["tarif_monatlich"] == pytest.approx(19.99)


def test_nicht_angebotene_option_wird_kein_buendel(antwort):
    gesperrt = "O2 Mobile L Plus mit 150 GB+"
    saetze, zaehler = _saetze(_abgeschaltet(antwort, gesperrt))
    assert "o2-mobile-l-plus" not in saetze
    assert len(saetze) == 11
    assert zaehler["nicht_angeboten"] == 1
    assert (zaehler["angeboten"], zaehler["nicht_erfasst"]) == (11, 0)


def test_gegenprobe_ohne_feld_gilt_die_option_als_angeboten(antwort):
    kopie = copy.deepcopy(antwort)
    for option in kopie["tariff"]["tariffOptions"]:
        option.pop("disabled", None)
    saetze, zaehler = _saetze(kopie)
    assert len(saetze) == 12
    assert "nicht_angeboten" not in zaehler


def test_ohne_eigene_messung_ist_alles_nicht_erfasst(antwort):
    kopie = copy.deepcopy(antwort)
    kopie["priceSummary"] = {}
    zaehler: dict = {}
    basis = {"strukturierter_name": "Samsung Galaxy S26", "sku": "x", "url": _URL}
    assert o2.saetze_aus_konfiguration(kopie, basis, None, _URL, zaehler) == []
    assert (zaehler["angeboten"], zaehler["nicht_erfasst"]) == (12, 12)


def _stand(abgerufen: list) -> Referenzstand:
    return Referenzstand(
        lambda u: abgerufen.append(u),
        o2._gemessen,
        o2._link,
        o2._ohne_markup,
        lambda: True,
        {},
    )


def test_referenzdurchlauf_ruft_keine_gesperrte_option_ab(antwort):
    gesperrt = "O2 Mobile Unlimited L Plus mit 300 MBit/s"
    link = next(
        o2._link(o)
        for o in antwort["tariff"]["tariffOptions"]
        if _anzeige(o) == gesperrt
    )
    abgerufen: list = []
    _stand(abgerufen).erster_durchlauf(_abgeschaltet(antwort, gesperrt))
    assert link not in abgerufen
    assert len(abgerufen) == 10


def test_gegenprobe_referenzdurchlauf_ruft_jede_angebotene_ab(antwort):
    abgerufen: list = []
    _stand(abgerufen).erster_durchlauf(antwort)
    assert len(abgerufen) == 11
