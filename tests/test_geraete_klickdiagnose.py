"""Diagnose je Kachel (``klickdiagnose``) gegen die echte Produktseite iPhone 17 Pro.

Der erste Klick-Tageslauf (Actions 37740022815, 08.10.2026) ließ jede 1&1-Kachel 24
als Befund „Antwort nennt 36 statt 24“: Die zweite Lesung sind die Globalen der
Produktseite, und die nennen nur den Betrag der Kachel 24+12. Beleg: die Produktseite
vom 08.09.2026 (``einsundeins_produktseite_iphone_17_pro.html.gz``) in Chromium ohne
Netz; die Beträge der Kacheln stammen aus der Erkundung vom 07.10.2026
(``einsundeins_bestellweg_laufzeit_20261007.json``, Seite 3). Die Suche findet den
Betrag der Kachel 24+12 in ``hwdVariantsPrices`` und im JSON-LD; Gegenprobe: den
Betrag der Kachel 24 nennt die Produktseite nirgends. Ohne Betrag oder bei einem
Fehler wird nicht gesucht, mit Grund, nie „nichts gefunden“.
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightFehler

from telco_radar.collect.geraete.klickantwort import Antwortlesung
from telco_radar.collect.geraete.klickdiagnose import (
    GRUND_GESCHEITERT,
    GRUND_OHNE_BETRAG,
    betragsmuster,
    diagnose,
    diagnose_als_daten,
    fundstellen,
)
from telco_radar.collect.geraete.klickecho import variante_aus
from telco_radar.collect.geraete.klicklauf import BEFUND, Kombiergebnis
from telco_radar.collect.geraete.klicklesung import Vorlesung
from telco_radar.collect.geraete.klickquellen import Quellenlesung
from telco_radar.collect.geraete.klicktext import Buendelwerte, Preiswerte

FIXTURES = Path(__file__).parent / "fixtures" / "geraete"
SEITE = FIXTURES / "einsundeins_produktseite_iphone_17_pro.html.gz"
BESTELLWEG = FIXTURES / "einsundeins_bestellweg_laufzeit_20261007.json"
KACHEL = "#tariff-cards-container > div > div:has(add-to-cart-button)"
BETRAG = re.compile(r"(\d+) , (\d{2}) €/Mon\.")
FOLGESEITE = "https://mobile.1und1.de/flow2/mobile/ssc-private/tariffContractDuration"


def _kachelbetraege() -> list[float]:
    """Die Bündelbeträge der Kacheln 24 und 24+12, wie die Erkundung sie las."""
    preise = json.loads(BESTELLWEG.read_text(encoding="utf-8"))["seite_3"]["preise"]
    treffer = [BETRAG.fullmatch(p["kontext"]) for p in preise.values()]
    return [float(f"{t[1]}.{t[2]}") for t in treffer if t is not None]


@pytest.fixture(scope="module")
def produktseite(chromium):
    blatt = chromium.new_page()
    html = gzip.decompress(SEITE.read_bytes()).decode("utf-8")
    blatt.set_content(html, wait_until="domcontentloaded", timeout=30_000)
    yield blatt
    blatt.close()


@pytest.mark.browser
def test_produktseite_nennt_nur_den_betrag_der_kachel_24_plus_12(produktseite):
    kurz, lang = _kachelbetraege()

    funde = fundstellen(produktseite, lang, KACHEL)

    assert (kurz, lang) == (59.99, 44.99)
    assert 'window.hwdVariantsPrices["product-COSMIC_ORANGE-256"][0]' in funde
    assert any(
        re.fullmatch(r"script \d+ \(application/ld\+json\) bei price", f) for f in funde
    )
    preise = [f for f in funde if f.startswith("window.hwdVariantsPrices")]
    assert preise and all(f.endswith('-256"][0]') for f in preise)
    assert produktseite.evaluate("() => window.currentHardwareOfferDuration") == "36"
    assert fundstellen(produktseite, kurz, KACHEL) == ()


def test_betragsmuster_nur_als_ganzer_betrag():
    muster = re.compile(betragsmuster(59.99))

    for text in ("59,99", "59.99", "5999", "ab 59,99 €", '"price":"59.99"'):
        assert muster.search(text), text
    for text in ("159,99", "59,991", "59.9", "a5999", "59999", "1.59,99"):
        assert muster.search(text) is None, text


class _Seite:
    url = f"{FOLGESEITE}?traceId=x&token=geheim"

    def __init__(self, fehler: BaseException | None = None) -> None:
        self.fehler, self.aufrufe = fehler, 0

    def evaluate(self, *_: object) -> list[str]:
        self.aufrufe += 1
        if self.fehler is not None:
            raise self.fehler
        return []


def _vorab() -> Vorlesung:
    lesung = Antwortlesung(
        Preiswerte(), {"laufzeit": 36}, Buendelwerte(buendelbetrag=44.99)
    )
    return Vorlesung({}, Quellenlesung(lesung))


def _ergebnis(gezeigt: Buendelwerte | None) -> Kombiergebnis:
    variante = variante_aus("256", "tariff-anf-s-mvl", "24")
    return Kombiergebnis(variante, BEFUND, textbuendel=gezeigt)


def test_ohne_betrag_oder_bei_fehler_keine_fundstellen_sondern_grund():
    ohne = _Seite()
    gescheitert = _Seite(PlaywrightFehler("Execution context was destroyed"))
    gesucht = _Seite()

    gezeigt = Buendelwerte(buendelbetrag=59.99)
    leer = diagnose(ohne, _ergebnis(None), _vorab(), KACHEL)
    fehler = diagnose(gescheitert, _ergebnis(gezeigt), _vorab(), KACHEL)
    nichts = diagnose(gesucht, _ergebnis(gezeigt), _vorab(), KACHEL)
    daten = diagnose_als_daten(nichts)
    folgeseite = daten.pop("folgeseite")

    assert (ohne.aufrufe, leer.fundstellen, leer.ohne_suche) == (
        0,
        None,
        GRUND_OHNE_BETRAG,
    )
    assert fehler.fundstellen is None
    assert fehler.ohne_suche == f"{GRUND_GESCHEITERT}: Execution context was destroyed"
    assert (nichts.fundstellen, nichts.ohne_suche) == ((), None)
    assert daten == {
        "kachel": {"buendelbetrag": 59.99, "einmalzahlung": None},
        "antwort": {"buendelbetrag": 44.99, "einmalzahlung": None},
        "antwort_laufzeit": 36,
        "fundstellen": [],
        "ohne_suche": None,
    }
    assert folgeseite.startswith(f"{FOLGESEITE}?traceId=x&token=")
    assert "geheim" not in folgeseite
