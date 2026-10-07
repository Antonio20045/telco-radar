"""Tarifphasen aus einer eigenen Folgezeile „ab dem 25. Monat: 29,99 €“ (o2).

o2 nennt den Tarifpreis nach der Aktion in einer eigenen Zeile unter „Tarif mtl.“ und
in der Antwort als eigenen Posten ohne ``amount``
(``priceSummary.recurringChargesListEntries``, Tarif O2 Mobile Special,
o2_vertiefung_iphone17pro.json.gz vom 29.09.2026). Text und
Antwort lasen beide nur die erste Zeile und stimmten in einer falschen Phase ohne Ende
überein. Gegenproben: ohne Folgezeile, mit „Summe ab dem 37. Monat“ (congstar) und mit
einer Zeile dazwischen bleibt es eine Phase.
"""

from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

import pytest

from telco_radar.collect.geraete.klickantwort import feldwert
from telco_radar.collect.geraete.klicktext import fundstellen, lies_zusammenfassung
from telco_radar.tarif_model import Preisphase

GERAETE = Path(__file__).parent / "fixtures" / "geraete"
FIXTURE = GERAETE / "o2_vertiefung_iphone17pro.json.gz"
TARIF = "Tarif mtl. (Mindestlaufzeit 24 Monate):\t14,99 €"
FOLGE = "ab dem 25. Monat: 29,99 €\t"
ZWEI = (Preisphase(1, 24, 14.99), Preisphase(25, None, 29.99))
EINE = (Preisphase(1, None, 14.99),)


def _posten(tarif: str) -> list:
    """``recurringChargesListEntries`` der Konfiguration zum Tarif-Slug ``tarif``."""
    daten = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    for url, roh in daten["antworten"].items():
        if "/rest/configuration/" not in url:
            continue
        kennung = url.rsplit("/", 1)[-1]
        klar = base64.b64decode(kennung + "=" * (-len(kennung) % 4)).decode()
        if f"privatkunden-{tarif};" in klar:
            return json.loads(roh)["priceSummary"]["recurringChargesListEntries"]
    raise AssertionError(f"Konfiguration {tarif} fehlt im Fixture")


def test_folgezeile_ergibt_zweite_phase_im_text():
    text = "\n".join(["Gerät mtl. (36 Raten):\t36,50 €", TARIF, FOLGE, "56,49 €"])

    assert lies_zusammenfassung(text).tarifphasen == ZWEI
    stelle = fundstellen(text)["tarifphasen"]
    assert stelle == f"{TARIF}\n{FOLGE}"
    assert stelle in text
    assert lies_zusammenfassung(stelle).tarifphasen == ZWEI


@pytest.mark.parametrize(
    "text",
    [
        f"{TARIF}\n56,49 €",
        f"{TARIF}\nSumme ab dem 37. Monat 29,99 €",
        f"{TARIF}\nGerät Anzahlung: 1,00 €\n{FOLGE}",
    ],
    ids=["ohne_folgezeile", "summe_ab_monat", "zeile_dazwischen"],
)
def test_ohne_direkte_folgezeile_bleibt_eine_phase(text):
    assert lies_zusammenfassung(text).tarifphasen == EINE
    assert fundstellen(text)["tarifphasen"] == TARIF


def test_postenliste_der_antwort_ergibt_dieselben_phasen():
    posten = _posten("o2-mobile-special-online")
    assert " ".join(posten[2]["description"].split()) == "ab dem 25. Monat: 29,99 €"
    assert posten[2]["amount"] is None

    assert feldwert("tarifphasen", posten) == ZWEI


def test_postenliste_ohne_folgeposten_bleibt_eine_phase():
    posten = _posten("o2-mobile-unlimited-m-plus-online-hwv-36m-05-00")

    assert len(posten) == 2
    assert feldwert("tarifphasen", posten) == (Preisphase(1, None, 19.99),)
    assert feldwert("tarifphasen", "19,99 €") == (Preisphase(1, None, 19.99),)
    ohne_tarif = [{"description": "Gerät mtl.:", "amount": "36,50 €"}]
    assert feldwert("tarifphasen", ohne_tarif) is None
