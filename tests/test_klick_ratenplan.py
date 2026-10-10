"""Tarifpreis über die ganze Ratenlaufzeit aus dem Klick-Lauf (Pitch 3, Weg A).

Die Klick-Karte o2 liest den Satz des Ratenplan-Hinweises als Nachweis
(``klickkarte.NACHWEISFELDER``), nie als Wertfeld: weder Echo noch Lesefeld noch
Beleg. Mit dem Tarifcode „-hwv-<n>m-“ der Antwortadresse wird ein einzelner offener
Tarifpreis zur Phase 1 bis n (``klickratenplan``), sonst bleibt alles wie zuvor.

Fixtures: ``o2_ratenplan_galaxy_s26_20261007.json.gz`` (zwei Konfigurationsantworten
mit dem Hinweis, 07.10.2026) und ``klick_ergebnisse_20261010.json.gz`` (die fünf
Ergebnisdateien des Klick-Laufs vom 10.10.2026, noch ohne Nachweise); Herkunft in
``_herkunft.json``. Am 10.10.2026 trugen 120 von 568 erfassten o2-Kombinationen den
Tarifcode zur Ratenzahl.
"""

from __future__ import annotations

import base64
import copy
import gzip
import json
import re
from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete.klickantwort import lies_antwort
from telco_radar.collect.geraete.klickecho import Variante
from telco_radar.collect.geraete.klickergebnis import kombination_als_daten
from telco_radar.collect.geraete.klickkarte import (
    KlickkartenFehler,
    klickkarte_aus_daten,
    lade_klickkarte,
)
from telco_radar.collect.geraete.klicklauf import ERFASST, Kombiergebnis
from telco_radar.collect.geraete.klickratenplan import NACHWEIS, ratenplan_phasen
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.geraete_config import lade_katalog

WURZEL = Path(__file__).resolve().parents[1]
FIX = WURZEL / "tests" / "fixtures" / "geraete"
O2_YAML = WURZEL / "config" / "klickkarten" / "o2.yaml"
SATZ = "über die gesamte Laufzeit deines Geräte-Ratenplans"
ANDERE = ("congstar", "1und1", "telekom", "vodafone")
_RATEN = re.compile(r"-hwv-(\d+)m-")


def _gz(name: str):
    with gzip.open(FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def ergebnisse() -> dict:
    return _gz("klick_ergebnisse_20261010.json.gz")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(O2_YAML)


def _mit_nachweis(daten: dict) -> dict:
    neu = copy.deepcopy(daten)
    for seite in neu.get("seiten") or []:
        for kombination in seite.get("kombinationen") or []:
            kombination["nachweise"] = {NACHWEIS: f"Rabatt {SATZ} auf deinen Tarif."}
    return neu


def _tarif(adresse: str) -> str:
    kennung = adresse.rsplit("/", 1)[-1]
    text = base64.b64decode(kennung + "=" * (-len(kennung) % 4)).decode("utf-8")
    return text.split("tariff=", 1)[1].split(";", 1)[0]


def test_karte_liest_den_satz_als_nachweis_nicht_als_wert(karte):
    antworten = _gz("o2_ratenplan_galaxy_s26_20261007.json.gz")["antworten"]
    for adresse, nutzlast in antworten.items():
        lesung = lies_antwort(nutzlast, karte.antwort, adresse)
        assert SATZ in lesung.nachweise[NACHWEIS]
        assert lesung.nachweise[NACHWEIS].endswith("Rabatt auf deinen Tarif.")
    assert NACHWEIS not in karte.lesefelder
    assert NACHWEIS not in karte.textlesung.muster


def test_ohne_hinweis_kein_nachweis(karte):
    leer = lies_antwort({"hardware": {"contents": {}}}, karte.antwort, None)

    assert leer.nachweise == {}


def test_nachweis_nur_in_der_antwort_nie_im_textmuster():
    roh = {
        "anbieter": "test",
        "knoepfe": {d: {"fest": "x"} for d in ("speicher", "tarif", "laufzeit")},
        "zusammenfassung": {"selektor": "#z", "muster": {NACHWEIS: "(.+)"}},
        "antwort": {"url_muster": "^https://", "pfade": {"rate": "a"}},
        "kanarie": {"selektor": "#z", "enthaelt": "x"},
    }
    with pytest.raises(KlickkartenFehler, match=NACHWEIS):
        klickkarte_aus_daten(roh, "test")


def test_alte_ergebnisdateien_bleiben_gleich(ergebnisse):
    """Eine Kombination ohne Nachweis schreibt dieselben Schlüssel wie vor dem Kanal."""
    alt = {
        frozenset(k)
        for daten in ergebnisse.values()
        for seite in daten.get("seiten") or []
        for k in seite.get("kombinationen") or []
        if "diagnose" not in k and "echo_quelle" not in k
    }
    ohne = kombination_als_daten(Kombiergebnis(Variante(None, None, None), ERFASST))
    mit = kombination_als_daten(
        Kombiergebnis(Variante(None, None, None), ERFASST, nachweise={NACHWEIS: "S."})
    )

    assert alt == {frozenset(ohne)}
    assert mit == {**ohne, "nachweise": {NACHWEIS: "S."}}


def test_andere_anbieter_bekommen_mit_nachweis_nichts_neues(ergebnisse, katalog):
    for name in ANDERE:
        vorher = ausbeute(ergebnisse[name], katalog)
        nachher = ausbeute(_mit_nachweis(ergebnisse[name]), katalog)

        assert nachher.rohsaetze == vorher.rohsaetze, name
        assert nachher.luecken == vorher.luecken, name


def test_o2_bekommt_die_phase_nur_mit_tarifcode_zur_ratenzahl(ergebnisse, katalog):
    vorher = ausbeute(ergebnisse["o2"], katalog)
    nachher = ausbeute(_mit_nachweis(ergebnisse["o2"]), katalog)

    assert nachher.luecken == vorher.luecken
    assert len(nachher.rohsaetze) == len(vorher.rohsaetze)
    neu = []
    for alt, satz in zip(vorher.rohsaetze, nachher.rohsaetze, strict=True):
        assert alt["tarif_phasen"] == []
        assert {**satz, "tarif_phasen": []} == alt
        if satz["tarif_phasen"]:
            neu.append(satz)
    assert len(neu) > 0
    for satz in neu:
        (phase,) = satz["tarif_phasen"]
        assert (phase["von_monat"], phase["bis_monat"]) == (1, satz["laufzeit_monate"])
        assert phase["betrag"] == satz["tarif_monatlich"]
        assert SATZ in phase["beleg"]
        assert f"-hwv-{satz['laufzeit_monate']}m-" in phase["beleg"]


def test_o2_zaehlt_genau_die_kombinationen_mit_tarifcode(ergebnisse, katalog):
    """Gegenprobe: die Zahl der Phasen gleich der Zahl erfasster Kombinationen, deren
    Tarifcode die Ratenzahl trägt und die ein Rohsatz werden."""
    daten = _mit_nachweis(ergebnisse["o2"])
    erwartet = 0
    for seite in daten["seiten"]:
        einzeln = {**daten, "seiten": [{**seite, "kombinationen": []}]}
        for k in seite.get("kombinationen") or []:
            if k.get("status") != ERFASST or not k.get("antwort_url"):
                continue
            treffer = _RATEN.search(_tarif(k["antwort_url"]))
            if treffer is None or int(treffer[1]) != k["werte"]["ratenzahl"]:
                continue
            einzeln["seiten"][0]["kombinationen"] = [k]
            erwartet += len(ausbeute(einzeln, katalog).rohsaetze)

    saetze = ausbeute(daten, katalog).rohsaetze
    assert sum(1 for s in saetze if s["tarif_phasen"]) == erwartet > 0


@pytest.mark.parametrize(
    ("anbieter", "nachweise", "tarif", "laufzeit"),
    [
        ("o2", {}, "privatkunden-o2-mobile-l-online-hwv-36m-05-00", 36),
        ("o2", {NACHWEIS: "S."}, "privatkunden-o2-mobile-l-online-hwv", 36),
        ("o2", {NACHWEIS: "S."}, "privatkunden-o2-mobile-l-online-hwv-24m-05-00", 36),
        ("congstar", {NACHWEIS: "S."}, "x-hwv-36m-05-00", 36),
        ("o2", {NACHWEIS: "S."}, "privatkunden-o2-mobile-l-online-hwv-36m-05-00", None),
    ],
)
def test_ohne_vollen_beleg_keine_phase(anbieter, nachweise, tarif, laufzeit):
    teile = f"type=X;hardware=o2shop::h;tariff=o2shop::{tarif};packs=p"
    kennung = base64.b64encode(teile.encode()).decode().rstrip("=")
    kombination = {
        "antwort_url": f"https://www.o2online.de/e-shop/rest/configuration/{kennung}",
        "nachweise": nachweise,
    }

    assert ratenplan_phasen(anbieter, kombination, laufzeit, 29.99) == []
    voll = {**kombination, "nachweise": {NACHWEIS: "S."}}
    belegt = laufzeit == 36 and "hwv-36m" in tarif
    assert bool(ratenplan_phasen("o2", voll, laufzeit, 29.99)) == belegt
