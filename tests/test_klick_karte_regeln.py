"""Ratenplan und Tarifkennung stehen in der Klick-Karte (Schritt 4a „Eine Methode“).

Der Code liest ``ratenplan`` und ``tarifslug`` aus der Karte des Anbieters
(``klickregeln``) und verzweigt nach der ``art``, nie nach dem Anbieternamen. Fehlt das
Feld in der Karte, gibt es keine geratene Phase und keinen geratenen Slug, sondern eine
benannte Lücke (``ratenplan_regel_fehlt``, Tarif ohne Auflösung).
"""

from __future__ import annotations

import base64
import copy
import gzip
import json
from pathlib import Path

import pytest
import yaml
from bestand_pfad import ZUSTAND, lese_wurzel

from telco_radar.analyze.klick_tarifslug import klick_beleglink, klick_slug
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import klickratenplan, klickregeln
from telco_radar.collect.geraete.congstar import ergaenze_pib_slug
from telco_radar.collect.geraete.klickkarte import (
    KlickkartenFehler,
    klickkarte_aus_daten,
    lade_klickkarte,
)
from telco_radar.collect.geraete.klickratenplan import NACHWEIS, ratenplan_phasen
from telco_radar.collect.geraete.klickregeln import regeln
from telco_radar.collect.geraete.klickrohsatz import (
    LUECKE_RATENPLAN_REGEL,
    ausbeute,
)
from telco_radar.geraete_config import lade_katalog
from telco_radar.tarif_bezug import Tarifbestand

WURZEL = Path(__file__).resolve().parents[1]
KARTEN = WURZEL / "config" / "klickkarten"
FIX = WURZEL / "tests" / "fixtures" / "geraete"
ANBIETERKARTEN = ("o2.yaml", "o2-tarife.yaml", "congstar.yaml")
SATZ = "über die gesamte Laufzeit deines Geräte-Ratenplans"
HEUTE = "2026-10-10"
O2_SEITE = (
    "https://www.o2online.de/e-shop/apple/apple-iphone-16-128gb-schwarz-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36&vertragsart=ratenzahlung"
    "&tarif=o2-mobile-on-demand-m-plus"
)
CONGSTAR_SEITE = "https://www.congstar.de/geraete/apple/apple-iphone-16/?planId={}"


def _kartenordner(ziel: Path, ohne: tuple[str, ...] = (), nur: tuple[str, ...] = ()):
    """Kopie der Karten; ``ohne`` streicht diese Kopffelder aus den Karten von o2
    und congstar, ``nur`` die Kartendateien, die es betrifft (Vorgabe: alle drei)."""
    ziel.mkdir(parents=True, exist_ok=True)
    for pfad in KARTEN.glob("*.yaml"):
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        if pfad.name in (nur or ANBIETERKARTEN):
            for feld in ohne:
                daten.pop(feld, None)
        (ziel / pfad.name).write_text(
            yaml.safe_dump(daten, allow_unicode=True), encoding="utf-8"
        )
    return ziel


def _satz(anbieter: str, tarif: str, url: str) -> dict:
    return {
        "sku_id": "apple-iphone-16-128gb-ohne-farbe",
        "anbieter": anbieter,
        "zustand": "neu",
        "device_id": "apple-iphone-16",
        "speicher_gb": 128,
        "tarif_name": tarif,
        "tarif_slug": "",
        "laufzeit_monate": 36,
        "tarif_bindung_monate": 24,
        "quelle_url": url,
        "quelle": "klick",
        "quelle_art": "klick",
        "abgerufen_am": HEUTE,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 20.0,
        "tarif_monatlich": 30.0,
        "buendel_monatlich": None,
        "tarif_phasen": [],
    }


@pytest.fixture(scope="module")
def saetze():
    o2 = [
        _satz("o2", tarif, O2_SEITE)
        for tarif in (
            "O2 Mobile L Plus mit 150 GB+",
            "O2 Mobile Unlimited M Plus mit 100 MBit/s",
            "O2 Mobile on Demand M mit 50 GB+",
            "O2 Mobile Unlimited L mit 300 MBit/s",
        )
    ]
    congstar = [
        _satz("congstar", "Allnet Flat XS", CONGSTAR_SEITE.format(543)),
        _satz("congstar", "Allnet Flat M", CONGSTAR_SEITE.format(540)),
    ]
    return o2 + congstar


@pytest.fixture(scope="module")
def bestand():
    tarife = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")
    ergaenze_pib_slug(tarife)
    return tarife


@pytest.fixture(scope="module")
def o2_ergebnis() -> dict:
    with gzip.open(
        FIX / "klick_ergebnisse_20261010.json.gz", "rt", encoding="utf-8"
    ) as f:
        daten = json.load(f)["o2"]
    neu = copy.deepcopy(daten)
    for seite in neu.get("seiten") or []:
        for kombination in seite.get("kombinationen") or []:
            kombination["nachweise"] = {NACHWEIS: f"Rabatt {SATZ} auf deinen Tarif."}
    return neu


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _config_adresse(tarif: str) -> str:
    teile = f"type=X;hardware=o2shop::h;tariff=o2shop::{tarif};packs=p"
    kennung = base64.b64encode(teile.encode()).decode().rstrip("=")
    return f"https://www.o2online.de/e-shop/rest/configuration/{kennung}"


def test_die_karten_tragen_die_felder():
    o2, congstar = regeln("o2"), regeln("congstar")

    assert (o2.ratenplan.art, o2.ratenplan.teil) == ("tarifcode", "tariff")
    assert (o2.tarifslug.art, o2.tarifslug.beleglink) == ("name", "konfiguration")
    assert congstar.ratenplan.nachweis == "[]"
    assert (congstar.tarifslug.art, congstar.tarifslug.parameter) == (
        "seitenparameter",
        "planId",
    )
    assert congstar.tarifslug.beleglink is None
    assert o2.liest_ratenplan_nachweis and congstar.liest_ratenplan_nachweis


@pytest.mark.parametrize("anbieter", ["Telekom", "Vodafone", "1&1", "unbekannt", ""])
def test_andere_anbieter_haben_keine_regel(anbieter):
    assert regeln(anbieter) == klickregeln.Kartenregeln()


def test_beide_o2_karten_sagen_dasselbe():
    assert lade_klickkarte(KARTEN / "o2.yaml").ratenplan == (
        lade_klickkarte(KARTEN / "o2-tarife.yaml").ratenplan
    )
    assert lade_klickkarte(KARTEN / "o2.yaml").tarifslug == (
        lade_klickkarte(KARTEN / "o2-tarife.yaml").tarifslug
    )


def test_ohne_ratenplan_in_der_karte_keine_geratene_phase(
    tmp_path, monkeypatch, o2_ergebnis, katalog
):
    """Fail-closed: die Karte liest den Nachweis, nennt aber die Regel nicht. Ohne
    Kartenfeld entstanden bisher trotzdem Phasen (die Regel stand im Python)."""
    mit = ausbeute(o2_ergebnis, katalog)
    assert sum(1 for s in mit.rohsaetze if s["tarif_phasen"]) > 0
    assert LUECKE_RATENPLAN_REGEL not in mit.luecken

    ohne = _kartenordner(tmp_path / "karten", ohne=("ratenplan",))
    monkeypatch.setattr(klickregeln, "KARTENORDNER", ohne)
    leer = ausbeute(o2_ergebnis, katalog)

    assert sum(1 for s in leer.rohsaetze if s["tarif_phasen"]) == 0
    assert leer.luecken[LUECKE_RATENPLAN_REGEL] > 0
    assert len(leer.rohsaetze) < len(mit.rohsaetze)


def test_ohne_ratenplan_wirft_die_phase_eine_benannte_ausnahme(tmp_path):
    ohne = _kartenordner(tmp_path / "karten", ohne=("ratenplan",))
    kombination = {
        "antwort_url": _config_adresse("privatkunden-o2-mobile-l-online-hwv-36m-05-00"),
        "nachweise": {NACHWEIS: "S."},
    }

    with pytest.raises(klickratenplan.RatenplanRegelFehlt, match="ratenplan"):
        ratenplan_phasen("o2", kombination, 36, 29.99, karten=ohne)
    assert ratenplan_phasen("o2", kombination, 36, 29.99)


def test_ohne_tarifslug_in_der_karte_kein_geratener_slug(
    tmp_path, monkeypatch, bestand, saetze
):
    """Fail-closed: ohne ``tarifslug`` bekommt der Satz keinen Slug und fällt als Tarif
    ohne Auflösung aus dem Bündelbau (benannt in ``offene_tarife``)."""
    mit = aus_rohsaetzen(saetze, bestand, HEUTE)
    assert (mit.ohne_tarif, len(mit.buendel)) == (0, 6)

    ohne = _kartenordner(tmp_path / "karten", ohne=("tarifslug",))
    monkeypatch.setattr(klickregeln, "KARTENORDNER", ohne)
    leer = aus_rohsaetzen(saetze, bestand, HEUTE)

    assert klick_slug(saetze[0]) == "" and klick_slug(saetze[-1]) == ""
    assert leer.ohne_tarif == 5
    assert [b.tarif_name for b in leer.buendel] == ["Allnet Flat M"]
    assert "Allnet Flat XS" in leer.offene_tarife


def test_ohne_beleglink_in_der_karte_bleibt_die_adresse_der_seite(tmp_path, saetze):
    ohne = tmp_path / "karten"
    _kartenordner(ohne, ohne=("tarifslug",))
    o2 = {**saetze[0], "laufzeit_monate": 24}

    assert klick_beleglink(o2) != O2_SEITE
    assert klick_beleglink(o2, karten=ohne) == O2_SEITE


def test_uneinige_karten_eines_anbieters_geben_keine_regel(tmp_path, caplog):
    """Eine der beiden o2-Karten ohne Feld: keine Regel, das Protokoll sagt es."""
    ordner = _kartenordner(tmp_path / "karten", ohne=("ratenplan",), nur=("o2.yaml",))

    with caplog.at_level("WARNING"):
        ergebnis = regeln("o2", ordner)

    assert ergebnis.ratenplan is None
    assert ergebnis.tarifslug is not None
    assert "ratenplan" in caplog.text and "uneinig" in caplog.text


def test_eine_neue_karte_genuegt_ohne_code_fuer_einen_anbieter(tmp_path):
    """Die Regel kommt aus der Karte: ein anderer Anbieter mit eigenem Muster und
    eigenem Nachweis bekommt die Phase, ohne dass im Python sein Name steht."""
    roh = yaml.safe_load((KARTEN / "o2.yaml").read_text(encoding="utf-8"))
    roh["anbieter"] = "Neuanbieter"
    roh["ratenplan"] = {"art": "tarifcode", "teil": "tariff", "muster": r"-rp-(\d+)x-"}
    roh["tarifslug"] = {"art": "seitenparameter", "parameter": "tid"}
    ordner = tmp_path / "karten"
    ordner.mkdir()
    (ordner / "neu.yaml").write_text(yaml.safe_dump(roh, allow_unicode=True))
    kombination = {
        "antwort_url": _config_adresse("abc-rp-24x-z"),
        "nachweise": {NACHWEIS: "S."},
    }

    (phase,) = ratenplan_phasen("Neuanbieter", kombination, 24, 9.99, karten=ordner)
    assert (phase["von_monat"], phase["bis_monat"], phase["betrag"]) == (1, 24, 9.99)
    assert ratenplan_phasen("Neuanbieter", kombination, 36, 9.99, karten=ordner) == []
    assert ratenplan_phasen("o2", kombination, 24, 9.99) == []
    satz = _satz("Neuanbieter", "X", "https://x.de/p?tid=77")
    assert klick_slug(satz, karten=ordner) == "77"
    assert klick_slug({**satz, "anbieter": "congstar"}, karten=ordner) == ""


@pytest.fixture(scope="module")
def roh_o2() -> dict:
    return yaml.safe_load((KARTEN / "o2.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("feld", "wert", "stelle"),
    [
        ("ratenplan", {"art": "geraten"}, "ratenplan.art"),
        ("ratenplan", {"art": "tarifcode", "teil": "tariff"}, "ratenplan.muster"),
        (
            "ratenplan",
            {
                "art": "tarifcode",
                "teil": "t",
                "muster": "(",
            },
            "ratenplan.muster",
        ),
        (
            "ratenplan",
            {"art": "tarifcode", "teil": "t", "muster": "x", "nachweis": "[]"},
            "ratenplan.nachweis",
        ),
        ("ratenplan", {"art": "ohne_rabattphase"}, "ratenplan.nachweis"),
        (
            "ratenplan",
            {"art": "ohne_rabattphase", "nachweis": "[]", "x": 1},
            "ratenplan.x",
        ),
        ("tarifslug", {"art": "seitenparameter"}, "tarifslug.parameter"),
        ("tarifslug", {"art": "name", "parameter": "planId"}, "tarifslug.parameter"),
        ("tarifslug", {"art": "name", "beleglink": "raten"}, "tarifslug.beleglink"),
        ("tarifslug", {"art": "erraten"}, "tarifslug.art"),
        ("tarifslug", {}, "tarifslug.art"),
    ],
)
def test_kaputte_regel_wirft_mit_stelle(roh_o2, feld, wert, stelle):
    roh = {**roh_o2, feld: wert}

    with pytest.raises(KlickkartenFehler) as fehler:
        klickkarte_aus_daten(roh, "test")

    assert fehler.value.feld == stelle
