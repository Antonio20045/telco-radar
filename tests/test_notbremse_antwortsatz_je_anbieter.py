"""Antwortsatz der Geräteseite: jeder Anbieter genau EINMAL, ohne toten Verweis.

Befund des Prüfers zu PR 207 (21.11.2026): „steht kein Bündel im Vergleich:
o2 (Plus: 5,00 € günstiger mit Zweitprodukt), o2 (Rabatt nur mit Zweitprodukt),
o2 (nicht direkt genannt).“ - derselbe Anbieter dreimal, weil ``namen`` je
Anbieter UND Grund einen Eintrag bildete und jeder Plus-Betrag ein eigener Grund
war. Darunter verwies der Leersatz der Zeitreihe auf „Bündel-Zeilen darunter“,
die app.js seit dem 10.10.2026 verwirft.

Die Beträge kommen aus dem vorhandenen Feld ``plus_vorteil``; report/ rechnet
nichts, es wählt nur den größten genannten Betrag („bis“).
"""

from __future__ import annotations

import html
import json
import re
import shutil

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel
from test_geraete_zeitreihe_ansicht import baue

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_antwort as antwort
from telco_radar.report import geraete_notbremse as notbremse
from telco_radar.report import geraete_view, geraete_zeitreihe

LISTEN = ("steht kein Bündel im Vergleich: ", "Nicht im Vergleich: ")


def _plus(betrag: float | None) -> dict:
    return {
        "anbieter": "o2",
        "bedingter_tarif": True,
        "plus_vorteil": betrag,
        "zaehlt": False,
    }


def _schaetzung(anbieter: str = "o2") -> dict:
    return {"anbieter": anbieter, "schaetzung": True, "zaehlt": False}


def _text(roh: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", roh))


@pytest.fixture(scope="module")
def paare(tmp_path_factory) -> list[dict]:
    """Alle Paare der Zeitreihe am festen Bestand (2026-10-03)."""
    zustand = tmp_path_factory.mktemp("antwort-je-anbieter") / "state"
    shutil.copytree(ZUSTAND, zustand)
    wurzel = lese_wurzel()
    geraete = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute="2026-10-03"
    )
    return geraete["zeitreihe"]["paare"]


@pytest.fixture(scope="module")
def saetze(paare) -> list[str]:
    """Die Antwortsätze aller Paare am festen Bestand."""
    return [_text(p["antwort_html"]) for p in paare]


def _eintraege(satz: str) -> list[str]:
    """Die Anbieter der Liste „… im Vergleich: a (…), b (…).“ in Reihenfolge."""
    for kopf in LISTEN:
        if kopf in satz:
            liste = re.sub(r"\([^()]*\)", "", satz.split(kopf, 1)[1]).rstrip(". ")
            return [teil.strip() for teil in liste.split(",")]
    return []


def test_antwortsatz_nennt_jeden_anbieter_genau_einmal(saetze):
    mit_liste = [s for s in saetze if _eintraege(s)]
    assert mit_liste, "Fall fehlt: kein Antwortsatz mit gesperrten Anbietern"
    doppelt = [s for s in mit_liste if len(set(_eintraege(s))) < len(_eintraege(s))]
    assert not doppelt, (
        f"{len(doppelt)} Sätze nennen einen Anbieter mehrfach: {doppelt[:2]}"
    )


def test_gegenprobe_bestand_hat_einen_anbieter_mit_zwei_gruenden(saetze):
    """Ohne diesen Fall prüft der Test oben nichts: am Bestand hat o2 im selben
    Paar Schätzung UND Zweitprodukt-Rabatt."""
    assert any(" oder " in s for s in saetze if _eintraege(s))


def test_mehrere_plus_betraege_werden_zu_bis_dem_groessten():
    assert notbremse.namen([_plus(5.0), _plus(10.0)]) == [
        "o2 (Plus: bis 10,00 € günstiger mit Zweitprodukt)"
    ]


def test_zwei_gruende_desselben_anbieters_stehen_in_einer_klammer():
    eintraege = notbremse.namen([_plus(5.0), _schaetzung()])
    assert eintraege == [
        "o2 (Plus: 5,00 € günstiger mit Zweitprodukt oder nicht direkt genannt)"
    ]


def test_plus_ohne_betrag_neben_betrag_nennt_keinen_betrag():
    """Fehlt bei einem Plus-Tarif der Betrag, ist „bis 5,00 €“ nicht belegt:
    dann steht der Grund ohne Zahl (fehlender Wert ist eine Lücke, keine 0)."""
    assert notbremse.namen([_plus(5.0), _plus(None)]) == [
        "o2 (Rabatt nur mit Zweitprodukt)"
    ]


def test_gegenprobe_ein_betrag_und_zwei_anbieter_bleiben_wie_bisher():
    assert notbremse.namen([_plus(5.0), _plus(5.0)]) == [
        "o2 (Plus: 5,00 € günstiger mit Zweitprodukt)"
    ]
    assert notbremse.namen([_schaetzung("1&1"), _plus(5.0)]) == [
        "1&1 (nicht direkt genannt)",
        "o2 (Plus: 5,00 € günstiger mit Zweitprodukt)",
    ]


def test_leersatz_nennt_den_grund_nur_wenn_der_antwortsatz_ihn_nicht_nennt():
    slot = {"o2": {"2026-11-20": _plus(5.0), "2026-11-21": _schaetzung()}}
    genannt = antwort.leersatz(slot, antwort.FALL_GESPERRT)
    assert genannt == notbremse.LEERSATZ
    offen = antwort.leersatz(slot, antwort.FALL_UNVOLLSTAENDIG)
    assert offen is not None and "nicht direkt genannt" in offen, offen
    assert "Bündel-Zeilen" not in offen + genannt


def test_leersatz_widerspricht_nicht_kein_buendel_erfasst():
    slot = {"o2": {"2026-11-21": _schaetzung()}}
    assert antwort.leersatz(slot, antwort.FALL_NICHT_ERFASST) == (
        notbremse.LEERSATZ_NICHT_ERFASST
    )


def test_gegenprobe_leersatz_ohne_messungen_bleibt_none():
    for fall in (antwort.FALL_GESPERRT, antwort.FALL_NICHT_ERFASST):
        assert antwort.leersatz({}, fall) is None


TAG = "2026-10-14"
GESCHAETZT = "buendel--congstar--sku-b--tarif-x--24"


def _karte(**extra) -> dict:
    return {
        "anbieter": "congstar",
        "gesamt": 1200.0,
        "schnitt_monat": 50.0,
        "leitzahl_monate": 24,
        "raten_laufzeit": 24,
        "tarif": "Allnet Flat XS",
        "band": "xs",
        "vergleichbar": True,
        "belastbar": True,
        "frisch": True,
        "sku_id": "sku-b",
        "naeherung": False,
        "quelle_url": "https://example.de/congstar",
        "abgerufen_am": TAG,
        **extra,
    }


def _paare_mit(tmp_path, karten: list) -> list[dict]:
    """Die Paare eines kleinen erfundenen Stands: ein geschätztes congstar-Bündel
    mit zwei Messtagen (zählt nie), heute die Karten ``karten``."""
    state = tmp_path / "state"
    state.mkdir()
    buendel = {
        "id": GESCHAETZT,
        "sku_id": "sku-b",
        "anbieter": "congstar",
        "tarif_name": "Allnet Flat XS",
        "tarif_id": "tarif-x",
        "tarif_monatlich": 20.0,
        "geraet_zuzahlung": 0.0,
        "geraet_monatsrate": 30.0,
        "laufzeit_monate": 24,
        "anschlusspreis": 0.0,
        "zustand": "neu",
        "herleitung": "geschätzt",
        "quelle_url": "https://example.de/congstar",
        "abgerufen_am": TAG,
    }
    (state / "geraete_tco.json").write_text(
        json.dumps({"buendel": [buendel]}), encoding="utf-8"
    )
    zeilen = [
        {
            **{k: buendel[k] for k in ("id", "tarif_id", "quelle_url")},
            "datum": tag,
            "tarif_monatlich": 20.0,
            "geraet_zuzahlung": 0.0,
            "geraet_monatsrate": 30.0,
            "laufzeit_monate": 24,
            "anschlusspreis": 0.0,
            "gesamt": 1200.0,
            "abgerufen_am": tag,
        }
        for tag in ("2026-09-29", TAG)
    ]
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8"
    )
    tco = {
        "modelle": [
            {
                "id": "modell-x",
                "titel": "Testgerät 256 GB",
                "hersteller": "Test",
                "speicher": 256,
                "karten": karten,
            }
        ],
        "band_je_tarif": {"tarif-x": "xs"},
        "baender_katalog": [{"key": "xs", "label": "XS"}],
        "historie_lage": {},
    }
    return geraete_zeitreihe.aufbereiten(state, tco, heute=TAG)["paare"]


FAELLE = {
    "gesperrt": [_karte(zaehlt=False, schaetzung=True)],
    "unvollstaendig": [_karte(belastbar=False, gesamt=None)],
    "nicht_erfasst": [_karte(raten_laufzeit=36, leitzahl_monate=36)],
    "zeilen": [_karte()],
}


@pytest.fixture(scope="module")
def paare_ohne_kurve(tmp_path_factory) -> list[tuple[str, dict]]:
    return [
        (fall, p)
        for fall, karten in FAELLE.items()
        for p in _paare_mit(tmp_path_factory.mktemp(fall), karten)
        if (p["modell"], p["band"], p["laufzeit"]) == ("modell-x", "xs", 24)
    ]


def test_jedes_paar_ohne_kurve_nennt_einen_grund_ohne_widerspruch(
    paare_ohne_kurve,
):
    """Prüfer zu PR 209: „Keine Kurve: die Preise zählen hier nicht im Vergleich.“
    stand auch unter „hat kein Bündel einen vollständigen Preis: Vodafone.“ und
    „ist kein Bündel erfasst.“ - dort nannte kein Satz den Grund, und der zweite
    widersprach dem Leersatz."""
    ohne_kurve = [
        (p, _text(p["antwort_html"]), p["leer_text"] or "")
        for _, p in paare_ohne_kurve
        if p["punkte"] == 0
    ]
    faelle = {fall for fall, p in paare_ohne_kurve if p["punkte"] == 0}
    assert faelle == set(FAELLE), f"Fall fehlt: {set(FAELLE) - faelle}"
    ohne_grund, widerspruch = [], []
    for p, satz, leer in ohne_kurve:
        nennt = "im Vergleich: " in satz or re.search(r"\([^()]+\)\.$", leer)
        if not nennt and "kein Bündel erfasst" not in leer:
            ohne_grund.append((p["modell"], p["band"], p["laufzeit"], satz, leer))
        if "kein Bündel erfasst" in satz and "zählen" in leer:
            widerspruch.append((p["modell"], p["band"], p["laufzeit"], satz, leer))
    assert not ohne_grund, f"{len(ohne_grund)} ohne Grund: {ohne_grund[:2]}"
    assert not widerspruch, f"{len(widerspruch)} Widersprüche: {widerspruch[:2]}"
    doppelt = [
        (satz, leer)
        for _, satz, leer in ohne_kurve
        if "steht kein Bündel im Vergleich: " in satz and leer != notbremse.LEERSATZ
    ]
    assert not doppelt, f"Grund doppelt genannt: {doppelt[:2]}"


def test_satz_ohne_historie_verweist_nicht_auf_buendel_zeilen(tmp_path):
    root, state = baue(tmp_path)
    (state / "geraete_tco_historie.jsonl").write_text("", encoding="utf-8")
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute="2026-09-16"
    )
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    leer = [p["leer_text"] for p in a["paare"] if p["leer_text"]]
    assert leer, "Fall fehlt: kein Paar ohne Messreihe"
    assert not [t for t in leer if "Bündel-Zeilen" in t], leer[:2]
