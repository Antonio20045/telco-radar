"""Klick-Karte Vodafone gegen die echte Preisantwort der Klick-Erkundung, ohne Browser.

Die Karte ist die eingefrorene Produktseiten-Karte (``fixtures/geraete/
klickkarten_produktseite``); die Tarifauswahl prüft ``test_klick_karte_vodafone_tarif``.

Die Antwort ist ``virtualItem/226`` aus ``mitschnitt-1.json`` Antwort 149 (Zweig
``klick-erkundung``, Commit a9b45f5a, Produktseite iPhone 17 Pro, 07.10.2026; Herkunft
in ``tests/fixtures/geraete/_herkunft.json``). Die Texte sind die sichtbaren Kandidaten
derselben Seite (``preise-1.json`` 11 und 13, ``bedienelemente-1.json`` 46–58).
Gegenprobe: eine andere Laufzeit liest andere Werte, eine Variante, die es nicht gibt,
liest keine, und die Antwort der Folgeseite „Zur Tarifauswahl“ (``mitschnitt-3.json``
Anfrage 337) passt nicht auf das Adressmuster.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from telco_radar.collect.geraete.klickecho import (
    feldwert,
    lies_antwort,
    pruefe_echo,
    variante_aus,
)
from telco_radar.collect.geraete.klickkartenprobe import GELADEN, lade_karte
from telco_radar.collect.geraete.klickoptionen import wert_nach_muster
from telco_radar.collect.geraete.klicktext import Preiswerte

KARTEN = Path(__file__).parent / "fixtures" / "geraete" / "klickkarten_produktseite"
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "geraete"
    / "vodafone_virtualitem_iphone_17_pro_20261007.json.gz"
)
URL = (
    "https://api.vodafone.de/glados/v2/hardware/v2/virtualItem/226"
    "?businessTransaction=newContract&salesChannel=Online.Consumer&financingType=rate"
)
TARIFAUSWAHL = (
    "https://api.vodafone.de/glados/v2/tariff/v2/hardware?businessTransaction="
    "newContract&salesChannel=Online.Consumer&hardwareId=57562&virtualItemId=267"
    "&financingType=rate&financingDuration=36"
)
SPEICHERLABELS = ("256 GB 1 € einmal", "512 GB 0,99 € einmal", "1 TB 1 € einmal")
LAUFZEITLABELS = ("36 Raten 33 €", "24 Raten 49,50 €", "12 Raten 99 €")
ZUSAMMENFASSUNG = "1 € einmal\n1 €\n33 € pro Monat\n33 €\n9,98 €"
OHNE_TARIFAUSWAHL = ("tarifphasen", "tarifbindung", "anschluss", "volumen_gb")


@pytest.fixture(scope="module")
def karte():
    lage = lade_karte(KARTEN, "vodafone")
    assert (lage.status, lage.grund) == (GELADEN, None)
    return lage.karte


@pytest.fixture(scope="module")
def antwort():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def _platz(speicher: str, laufzeit: str, farbe: str = "Cosmic Orange") -> dict:
    return {
        "speicher": speicher,
        "tarif": "unbekannt",
        "laufzeit": laufzeit,
        "farbe": farbe,
    }


def _textwert(karte, feld: str, text: str) -> object:
    """Wie ``Textleser.textwerte``: erste Gruppe ohne Leerraum, dann ``feldwert``."""
    treffer = karte.textlesung.muster[feld].muster.search(text)
    assert treffer is not None, (feld, text)
    return feldwert(feld, "".join(treffer[1].split()))


def test_optionswerte_aus_den_labels_der_erkundung(karte):
    speicher = karte.knoepfe["speicher"].muster
    laufzeit = karte.knoepfe["laufzeit"].muster

    assert [wert_nach_muster(t, speicher) for t in SPEICHERLABELS] == [
        "256 GB",
        "512 GB",
        "1 TB",
    ]
    assert [wert_nach_muster(t, laufzeit) for t in LAUFZEITLABELS] == ["36", "24", "12"]
    assert wert_nach_muster("Einmal 1199,90 €", laufzeit) is None
    assert 'input[value="1"]' in karte.knoepfe["laufzeit"].selektor


def test_die_erkundete_kombination_wird_erfasst(karte, antwort):
    assert karte.antwort.passt(URL) and karte.antwort.laden

    lesung = lies_antwort(antwort, karte.antwort, URL, _platz("256 GB", "36"))
    text = Preiswerte(
        anzahlung=_textwert(karte, "anzahlung", ZUSAMMENFASSUNG),
        rate=_textwert(karte, "rate", ZUSAMMENFASSUNG),
        ratenzahl=_textwert(karte, "ratenzahl", LAUFZEITLABELS[0]),
    )
    variante = variante_aus("256 GB", "unbekannt", "36")
    echo = pruefe_echo(variante, variante, text, lesung)

    assert echo.stimmt, echo.befunde
    assert (echo.werte.anzahlung, echo.werte.rate, echo.werte.ratenzahl) == (
        1.0,
        33.0,
        36,
    )
    assert echo.luecken == OHNE_TARIFAUSWAHL


def test_gegenprobe_andere_laufzeit_und_fehlende_variante(karte, antwort):
    vierundzwanzig = lies_antwort(antwort, karte.antwort, URL, _platz("512 GB", "24"))
    ohne = lies_antwort(antwort, karte.antwort, URL, _platz("1 TB", "36", "Silber"))

    werte = vierundzwanzig.werte
    assert (werte.anzahlung, werte.rate, werte.ratenzahl) == (0.99, 60.0, 24)
    assert ohne.werte == Preiswerte()
    assert not karte.antwort.passt(TARIFAUSWAHL)


def test_falscher_text_ist_ein_befund_kein_wert(karte, antwort):
    lesung = lies_antwort(antwort, karte.antwort, URL, _platz("256 GB", "24"))
    text = Preiswerte(anzahlung=1.0, rate=33.0, ratenzahl=24)
    variante = variante_aus("256 GB", "unbekannt", "24")

    echo = pruefe_echo(variante, variante, text, lesung)

    assert [b.feld for b in echo.befunde] == ["rate"]
    assert echo.werte.rate is None
