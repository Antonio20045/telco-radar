"""Etikett 1&1 (Live-Abnahme 08.11.2026): das Ratenwort nennt, was die Summe trägt.

Eine 1&1-Zeile mit Vertrag über 36 Monate („24 + 12“) rechnet 24 Bündelbeträge, die
Einmalzahlung bei Kündigung und den Anschluss, aber KEINE 36 Geräteraten
(Datenkonzept Geräte 5.3). Ihr Etikett „Kosten über 24 Monate“ war richtig; falsch war
die Beschriftung des Zeilenbilds, die den Vertrag als „36 Raten“ neben die 803,66 €
setzte (66 Zeilen). Dieselbe Angabe stand an Zeilen ohne Preis („Preis veraltet“),
weil `preis_anzeige` den Bündelbetrag leert, aus dem die Vorlage das Wort ableitete.

Gegen den alten Stand rot: die Zeilenbild-Beschriftung nannte „36 Raten“ und kannte
kein `raten_text`. Gegenprobe in jedem Test: eine Zeile mit echten 36 Geräteraten
behält „36 Raten“ und ihr Etikett „24 Tarifmonate und 36 Geräteraten“.
"""

from __future__ import annotations

import pytest
import test_geraete_laufzeit_auf_der_seite as fixture
from bs4 import BeautifulSoup
from test_geraete_laufzeit_auf_der_seite import HEUTE, vorlage_text, zeile_html

from telco_radar.report import geraete_laufzeit, geraete_zeilenbelege

BEIDES = "Kosten über 24 Tarifmonate und 36 Geräteraten"
ABLOESE = "24 Monate + Ablöse"


@pytest.fixture(scope="module")
def modell():
    return fixture._modell(
        [
            fixture._einsundeins(),
            fixture._congstar(36, 25.5),
            fixture._congstar(24, 30.0),
            fixture._vodafone(),
        ]
    )


def _karte(modell, anbieter: str, raten: int) -> dict:
    treffer = [
        k
        for k in modell["karten"]
        if k["anbieter"] == anbieter and k["raten_laufzeit"] == raten
    ]
    assert len(treffer) == 1, (anbieter, raten, treffer)
    return treffer[0]


def _beschriftung(karte: dict) -> str:
    """Die Zeilenbild-Beschriftung dieser Karte an der ECHTEN Vorlage."""
    zeile_modell = {"id": "m", "zeilen_band": [karte], "zeilen_ohne_band": []}
    paar = {"anbieter": karte["anbieter"], "beleg": None}
    paar |= geraete_zeilenbelege.ergaenze_paare(
        [paar],
        zeile_modell,
        lambda k: {"datum": HEUTE, "gross": False, "url": "https://example.de/b.png"},
    )[0]
    env = fixture._env()
    env.globals["paarbelege"] = lambda m: [paar]
    html = env.from_string(
        '{% from "_geraete_buendel.html.j2" import belegpaare %}{{ belegpaare(m) }}'
    ).render(m=zeile_modell)
    summary = BeautifulSoup(html, "html.parser").select_one(
        "details.gr-belege--zeile summary"
    )
    assert summary is not None, html
    return " ".join(summary.get_text().split())


def _ratenwort_der_zeile(karte: dict) -> str:
    return vorlage_text(zeile_html(karte).select_one(".gr-bnd-raten"))


def test_die_beschriftung_nennt_beim_24_plus_12_vertrag_keine_36_raten(modell):
    karte = _karte(modell, "1&1", 36)
    assert karte["label"] == "Kosten über 24 Monate" and karte["gesamt"] is not None
    text = _beschriftung(karte)
    assert "36 Raten" not in text, text
    assert f"{ABLOESE} · Kosten über 24 Monate" in text, text


def test_beschriftung_und_zeile_sagen_dasselbe_ratenwort(modell):
    """Eine Regel, zwei Leser: das Ratenwort der Zeile steht im Zeilenbild."""
    for anbieter, raten in (("1&1", 36), ("congstar", 36), ("congstar", 24)):
        karte = _karte(modell, anbieter, raten)
        wort = _ratenwort_der_zeile(karte).split(" · Tarif")[0]
        assert f" · {wort} · Kosten über " in _beschriftung(karte), (anbieter, wort)


def test_echte_geraeteraten_behalten_ihr_wort_und_ihr_etikett(modell):
    karte = _karte(modell, "congstar", 36)
    assert karte["label"] == BEIDES
    text = _beschriftung(karte)
    assert f" · 36 Raten · {BEIDES}" in text, text
    assert " · 24 Raten · Kosten über 24 Monate" in _beschriftung(
        _karte(modell, "congstar", 24)
    )


def test_eine_veraltete_zeile_behauptet_keine_36_raten(modell):
    """Ohne Preis (`preis_anzeige` leert den Bündelbetrag) bleibt das Wort wahr."""
    alt = {**_karte(modell, "1&1", 36), "frisch": False}
    html = zeile_html(alt)
    assert html.select_one("details.gr-bnd--leer"), "die Zeile trägt noch einen Preis"
    assert _ratenwort_der_zeile(alt) == ABLOESE
    neu = {**_karte(modell, "congstar", 36), "frisch": False}
    assert _ratenwort_der_zeile(neu).startswith("36 Raten")


def test_die_regel_gilt_fuer_jeden_anbieter_ohne_sonderfall():
    """`raten_text` liest nur Bündelbetrag und Laufzeit, nie den Namen."""
    vertrag = {"buendel_monatlich": 25.99, "raten_laufzeit": 36}
    for anbieter in ("1&1", "Fremd", "freenet"):
        assert geraete_laufzeit.raten_text({**vertrag, "anbieter": anbieter}) == ABLOESE
    assert geraete_laufzeit.raten_text({**vertrag, "raten_laufzeit": 24}) == (
        "24 Monatsraten"
    )
    assert geraete_laufzeit.raten_text({"raten_laufzeit": 36}) == "36 Raten"
    assert geraete_laufzeit.raten_text({"raten_laufzeit": None}) is None
