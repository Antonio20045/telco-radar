"""Drei Lehren der ersten Kartenprobe (Actions, 07.10.2026) an ihren echten Daten.

Fixture ``kartenprobe_texte_20261007.json``: je gelesener Kombination aus
``erkundung/<anbieter>/2026-10-07/karte-<n>.json`` (Zweig klick-erkundung, Commit
c8ce1f77) Auswahl, Status, Text und die drei Lesungen, Werte unverändert
(Herkunft in ``_herkunft.json``).

1. Erfasst heißt: mindestens ein Preiswert (Rate, Ratenzahl, bei ``ein_vertrag``
   Bündelbetrag). 1&1 stand als „erfasst“ mit leeren Werten in ``karte-1.json``; der
   Bündelbetrag war gelesen, die Datei nannte ihn nicht.
2. 1&1 setzt Euro, Komma und Cent in eigene Elemente: „44\\n,\\n99\\n€/Monat“ ist 44,99,
   nicht 99,00. congstar, o2 und Vodafone lesen sich danach wie in der Probe.
3. o2 setzt den Tarifbetrag in eine eigene Zeile; alle 20 Kombinationen waren
   ``befund`` „fehlt im Text“. Mit dem Muster der Karte stimmen Text und Antwort.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from telco_radar.collect.geraete.klickbeleg import werte_als_json, werte_aus_json
from telco_radar.collect.geraete.klickecho import (
    Antwortlesung,
    Befund,
    pruefe_echo,
    variante_aus,
)
from telco_radar.collect.geraete.klickkarte import (
    DIMENSIONEN,
    Klickkarte,
    lade_klickkarte,
)
from telco_radar.collect.geraete.klickkartenprobe import (
    GELAUFEN,
    Kartenprobe,
    als_daten,
)
from telco_radar.collect.geraete.klickkartentypen import Textmuster
from telco_radar.collect.geraete.klicklauf import (
    BEFUND,
    ERFASST,
    GRUND_OHNE_PREISWERT,
    NICHT_ERFASST,
    Klicklauf,
    Kombiergebnis,
    lesestatus,
)
from telco_radar.collect.geraete.klicktext import (
    Buendelwerte,
    Preiswerte,
    zahlen_ohne_leerraum,
)
from telco_radar.collect.geraete.klicktextleser import Textleser
from telco_radar.tarif_model import Preisphase

WURZEL = Path(__file__).parent.parent
KARTEN = WURZEL / "config" / "klickkarten"
FIXTURE = (
    Path(__file__).parent / "fixtures" / "geraete" / "kartenprobe_texte_20261007.json"
)
BEISPIELKARTE = (
    Path(__file__).parent / "fixtures" / "klickcrawler" / "beispiel_karte.yaml"
)
KOMBINATIONEN = json.loads(FIXTURE.read_text(encoding="utf-8"))["kombinationen"]
BUENDEL_1UND1 = [44.99, 51.99, 32.99, 38.99]
"""Bündelbeträge der vier 1&1-Kombinationen (karte-1 Nr. 0/1, karte-2 Nr. 0/1)."""


class _Bereich:
    """Ein Selektor ohne Treffer: Textmuster mit eigenem Fundort lesen nichts."""

    def count(self) -> int:
        return 0


class _Seite:
    def locator(self, _selektor: str) -> _Bereich:
        return _Bereich()


def _von(anbieter: str) -> list[dict]:
    return [k for k in KOMBINATIONEN if k["datei"].startswith(f"erkundung/{anbieter}/")]


def _id(kombination: dict) -> str:
    seite = kombination["datei"].rsplit("/", 1)[-1].removesuffix(".json")
    return f"{seite}-{kombination['kombination']}"


def _karte(anbieter: str) -> Klickkarte:
    return lade_klickkarte(KARTEN / f"{anbieter}.yaml")


def _textwerte(karte: Klickkarte, text: str) -> tuple[Preiswerte, Buendelwerte]:
    werte, buendel, _ = Textleser(_Seite(), karte, 1000).textwerte(text)
    return werte, buendel


def _echo_o2(text: str, kombination: dict):
    gewaehlt = variante_aus(**kombination["variante"])
    im_text, _ = _textwerte(_karte("o2"), text)
    antwort = Antwortlesung(werte_aus_json(kombination["werte_antwort"]), {})
    return pruefe_echo(gewaehlt, gewaehlt, im_text, antwort)


def test_fixture_haelt_die_kombinationen_der_probe():
    je_anbieter = {a: len(_von(a)) for a in ("1und1", "congstar", "o2", "vodafone")}
    assert je_anbieter == {"1und1": 4, "congstar": 20, "o2": 20, "vodafone": 15}
    erste = _von("1und1")[0]
    assert (erste["status"], erste["datei"], erste["kombination"]) == (
        "erfasst",
        "erkundung/1und1/2026-10-07/karte-1.json",
        0,
    )
    assert set(erste["werte"].values()) == {None}


def test_ohne_preiswert_ist_die_kombination_nicht_erfasst():
    """1&1 karte-1 Nr. 0, wie die Datei sie nennt: keine Werte, kein Bündelbetrag."""
    werte = werte_aus_json(_von("1und1")[0]["werte"])

    assert lesestatus((), werte, Buendelwerte()) == (
        NICHT_ERFASST,
        GRUND_OHNE_PREISWERT,
    )
    assert lesestatus((), werte, None) == (NICHT_ERFASST, GRUND_OHNE_PREISWERT)


def test_volumen_und_bindung_allein_sind_nicht_erfasst():
    """congstar karte-1 Nr. 0 ohne Rate und Ratenzahl: Tarif, Bindung, Anschluss und
    Volumen stimmen, ein Gerätepreis fehlt."""
    werte = werte_aus_json(_von("congstar")[0]["werte"])
    assert werte.tarifbindung is not None and werte.volumen_gb is not None

    ohne_preis = replace(werte, rate=None, ratenzahl=None)

    assert lesestatus((), ohne_preis, None)[0] == NICHT_ERFASST
    assert lesestatus((), replace(werte, ratenzahl=None), None) == (ERFASST, None)
    assert lesestatus((), replace(werte, rate=None), None) == (ERFASST, None)


@pytest.mark.parametrize("nummer", range(4))
def test_gegenprobe_buendelbetrag_aus_dem_text_ist_erfasst(nummer):
    """Derselbe 1&1-Text nennt den Bündelbetrag; mit ihm ist die Kombination erfasst."""
    kombination = _von("1und1")[nummer]
    werte = werte_aus_json(kombination["werte"])
    buendel = Buendelwerte(buendelbetrag=BUENDEL_1UND1[nummer])
    assert kombination["text"].startswith(str(BUENDEL_1UND1[nummer]).split(".")[0])

    assert lesestatus((), werte, buendel) == (ERFASST, None)


def test_befund_geht_vor_der_preisregel():
    befund = Befund("tarifphasen", "fehlt im Text")

    assert lesestatus((befund,), Preiswerte(), None) == (BEFUND, "fehlt im Text")


def test_karte_json_nennt_den_buendelbetrag():
    """Ohne ``buendel`` sah 1&1 in ``karte-1.json`` leer aus."""
    kombination = _von("1und1")[0]
    variante = variante_aus(**kombination["variante"])
    auswahl = tuple(kombination["auswahl"][d] for d in DIMENSIONEN)
    buendel = Buendelwerte(buendelbetrag=44.99)
    lauf = Klicklauf(
        "1&1",
        kombination["adresse"],
        ergebnisse=[
            Kombiergebnis(
                variante,
                ERFASST,
                auswahl=auswahl,
                buendel=buendel,
                text=kombination["text"],
            ),
            Kombiergebnis(
                variante, NICHT_ERFASST, GRUND_OHNE_PREISWERT, auswahl=auswahl
            ),
        ],
    )
    probe = Kartenprobe(GELAUFEN, "1und1.yaml", lauf=lauf, karte=_beispielkarte())

    mit, ohne = als_daten(probe)["kombinationen"]

    assert mit["buendel"] == {"buendelbetrag": 44.99, "einmalzahlung": None}
    assert ohne["buendel"] is None
    assert ohne["grund"] == GRUND_OHNE_PREISWERT


def _beispielkarte() -> Klickkarte:
    return lade_klickkarte(BEISPIELKARTE)


@pytest.mark.parametrize("nummer", range(4))
def test_betrag_mit_leerraum_ist_ganz(nummer):
    """Ein Muster im Stil der o2-Karte („([\\d.,]+)\\s*€“) las „99\\n€“ als 99,00."""
    text = _von("1und1")[nummer]["text"]
    erwartet = BUENDEL_1UND1[nummer]
    muster = {"rate": Textmuster(re.compile(r"([\d.,]+)\s*€/Monat"))}
    beispiel = _beispielkarte()
    karte = replace(beispiel, textlesung=replace(beispiel.textlesung, muster=muster))

    werte, _ = _textwerte(karte, text)

    assert werte.rate == erwartet
    assert zahlen_ohne_leerraum(text).startswith(f"{erwartet:.2f}".replace(".", ","))


@pytest.mark.parametrize(
    "text",
    [
        "Gerät mtl. (36 Raten):\n36,50\xa0€\nTarif mtl. (Mindestlaufzeit 24 Monate):",
        "Laufzeit 12, 24 oder 36 Monate",
        "Summe 1. bis 36. Monat\n24,00 €",
    ],
    ids=["zeilen_bleiben_getrennt", "komma_ohne_leerraum_davor", "zahl_vor_umbruch"],
)
def test_gegenprobe_zahlen_bleiben_getrennt(text):
    assert zahlen_ohne_leerraum(text) == text


@pytest.mark.parametrize("anbieter", ["congstar", "o2", "vodafone"])
def test_texte_lesen_sich_wie_in_der_probe(anbieter):
    """Alle Felder ohne eigenen Fundort wie in ``werte_text`` der Probe; einzig o2
    ``tarifphasen`` ist neu gelesen und gleicht dann der Antwort (Lehre 3)."""
    karte = _karte(anbieter)
    eigener_ort = {f for f, m in karte.textlesung.muster.items() if m.selektor}
    for kombination in _von(anbieter):
        assert zahlen_ohne_leerraum(kombination["text"]) == kombination["text"]
        werte, _ = _textwerte(karte, kombination["text"])
        gelesen = werte_als_json(werte)
        erwartet = dict(kombination["werte_text"])
        if anbieter == "o2":
            assert erwartet["tarifphasen"] is None
            erwartet["tarifphasen"] = kombination["werte_antwort"]["tarifphasen"]
        for feld, wert in erwartet.items():
            if feld not in eigener_ort:
                assert gelesen[feld] == wert, (_id(kombination), feld)


@pytest.mark.parametrize("kombination", _von("o2"), ids=_id)
def test_o2_tarifphasen_aus_text_und_antwort_stimmen(kombination):
    echo = _echo_o2(kombination["text"], kombination)

    assert [b for b in echo.befunde if b.feld == "tarifphasen"] == []
    antwort = werte_aus_json(kombination["werte_antwort"]).tarifphasen
    assert echo.werte.tarifphasen == antwort
    assert antwort is not None and len(antwort) == 1


def test_gegenprobe_o2_anderer_tarifpreis_ist_ein_befund():
    kombination = _von("o2")[0]
    text = kombination["text"]
    assert "Monate):\n29,99\xa0€" in text
    anders = text.replace("Monate):\n29,99\xa0€", "Monate):\n24,99\xa0€")

    echo = _echo_o2(anders, kombination)

    befunde = [b.grund for b in echo.befunde if b.feld == "tarifphasen"]
    assert befunde == [
        "Text Monat 1 und danach: 24,99, Antwort Monat 1 und danach: 29,99"
    ]


@pytest.mark.parametrize(
    "folge",
    ["\nab dem 25. Monat:\n29,99\xa0€", "\nab dem 25. Monat: 29,99 €\t"],
    ids=["eigene_zeile", "eine_zeile"],
)
def test_o2_folgezeile_ab_monat_25_bleibt_zweite_phase(folge):
    """O2 Mobile Special, Folgezeile wie in test_geraete_klickphasen_folgezeile."""
    text = _von("o2")[2]["text"]
    stelle = "Monate):\n19,99\xa0€"
    assert stelle in text

    werte, _ = _textwerte(_karte("o2"), text.replace(stelle, stelle + folge))

    assert werte.tarifphasen == (
        Preisphase(1, 24, 19.99),
        Preisphase(25, None, 29.99),
    )
