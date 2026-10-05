"""Abnahme T1: ein umformuliertes Angebot behält seine ID und ist nur einmal aktiv."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from bestand_pfad import ZUSTAND

from telco_radar.analyze.promo_store import PromoDB

AKTIVE_NACHHER = 103
ALTE_ID_ZAHL = 330
NEUE_ID_ZAHL = 294
HEUTE = "2026-10-04"
LIDL = "https://www.lidl-connect.de/"

GRUPPEN: dict[str, tuple[str, ...]] = {
    "1und1-familientarife": ("15735d57b5951513", "790c4ab46edcb3c0"),
    "1und1-junge-leute": ("5fe4db9eb5a712dd", "5b1ad95d70152994"),
    "lidl-jahrestarife": ("9d71dfa986538d37", "42c0ad4774f86984"),
    "telekom-cashback": ("a79c28b519174475", "7fc231d3785dc0c0", "88086e25870a70a5"),
    "telekom-pluskarten": ("9182cfc1a5b5ed35", "6a8ee022223e6f6d"),
    "vodafone-familycard-xl": ("886c392bc4433289", "449a6737e39f600f"),
    "congstar-kennenlernen": ("365d677e413a7e3f", "9e9c506688d9e8b1"),
    "congstar-partnerkarte": ("1d45e1771b77d972", "ef70a13413b4de22"),
    "congstar-prepaid-allnet-m": (
        "67546409aa0f8b11",
        "03e4bca3e1b19c06",
        "c8ac71f4c90e6685",
    ),
    "congstar-young": ("84a4e51cc4cbefc8", "be2c2a92a41d4d29"),
    "winsim-tablets": ("189d1aad620b3801", "3e8fcf37a6c0dfef"),
    "winsim-unlimited": ("248f53cbe9742b97", "69837d8ae72029d6", "23615f0eeb6abc31"),
}


GLEICHZEITIG: tuple[tuple[str, ...], ...] = (
    ("25f937a05e4ceebf", "91207751dbad9ec6"),
    ("6e8996f3908ca548", "00f29071b8f4c3f8"),
    ("58e982a0c21dd5c4", "2757e782ab161d7d"),
    ("b9cbb466cc3d60df", "87b081daa94cde57"),
    ("b0ce4d3f7b148372", "392086949b1153a7", "dcc41ce633965250"),
    ("545c14d1a7e133a8", "2feb47012adf77c4"),
    ("3e3a7059160dcdbf", "2510e5ebf4ff470c"),
    ("823ef305c34f962b", "67afec896dab5425"),
    ("ea3f198e2db9dded", "8d81a04a9540b372"),
)


def _lade(tmp_path: Path) -> PromoDB:
    """Lädt eine Kopie der Promo-Datenbank aus dem Schnappschuss."""
    ziel = tmp_path / "promo_db.json"
    shutil.copy2(ZUSTAND / "promo_db.json", ziel)
    return PromoDB(ziel)


def _bekannte_ids(eintrag: dict) -> set[str]:
    """Die eigene ID und alle alten IDs eines Eintrags."""
    return {eintrag.get("id"), *eintrag.get("alteIds", [])}


@pytest.mark.parametrize("name", list(GRUPPEN), ids=list(GRUPPEN))
def test_gruppe_ist_ein_aktiver_eintrag(tmp_path: Path, name: str) -> None:
    """Alle alten IDs einer Gruppe landen in genau einem aktiven Eintrag."""
    alte = set(GRUPPEN[name])
    db = _lade(tmp_path)
    treffer = [e for e in db.entries.values() if _bekannte_ids(e) & alte]
    n = len(treffer)
    assert n == 1, f"{name}: erwartet 1 Eintrag, erhalten {n}"
    assert treffer[0].get("status") == "aktiv", (
        f"{name}: Status {treffer[0].get('status')!r} statt 'aktiv'"
    )


def test_zahl_aktiver_eintraege(tmp_path: Path) -> None:
    """Nach dem Zusammenlegen bleiben genau 103 aktive Angebote."""
    db = _lade(tmp_path)
    aktiv = sum(1 for e in db.entries.values() if e.get("status") == "aktiv")
    assert aktiv == AKTIVE_NACHHER, (
        f"aktive Einträge: erwartet {AKTIVE_NACHHER}, erhalten {aktiv}"
    )


def test_laden_ist_wiederholbar_und_verliert_keine_id(tmp_path: Path) -> None:
    """Zweimal laden gibt dieselben IDs; jede alte ID steht in genau einem Eintrag."""
    erste = _lade(tmp_path)
    zweite = PromoDB(tmp_path / "promo_db.json")
    assert set(erste.entries) == set(zweite.entries)

    roh = json.loads((ZUSTAND / "promo_db.json").read_text(encoding="utf-8"))
    alte_ids = [e["id"] for e in roh["entries"]]
    assert len(set(alte_ids)) == ALTE_ID_ZAHL

    for alte_id in alte_ids:
        n = sum(1 for e in erste.entries.values() if alte_id in _bekannte_ids(e))
        assert n == 1, f"{alte_id}: in {n} Einträgen statt in genau einem"


def test_zahl_der_ids_nach_dem_zusammenlegen(tmp_path: Path) -> None:
    """Aus 330 alten Einträgen werden genau 294, nicht mehr und nicht weniger."""
    db = _lade(tmp_path)
    assert len(db.entries) == NEUE_ID_ZAHL, (
        f"IDs: erwartet {NEUE_ID_ZAHL}, erhalten {len(db.entries)}"
    )


@pytest.mark.parametrize("ids", GLEICHZEITIG, ids=[g[0] for g in GLEICHZEITIG])
def test_gleichzeitig_gelesene_bleiben_getrennt(
    tmp_path: Path, ids: tuple[str, ...]
) -> None:
    """Gleicher Schlüssel aus demselben Lauf und derselben Seite bleibt getrennt."""
    db = _lade(tmp_path)
    ziele = [
        eid
        for alte_id in ids
        for eid, e in db.entries.items()
        if alte_id in _bekannte_ids(e)
    ]
    assert len(ziele) == len(ids), f"{ids}: in {len(ziele)} Einträgen gefunden"
    assert len(set(ziele)) == len(ids), f"{ids}: zusammengelegt zu {set(ziele)}"


def test_laden_schreibt_nichts(tmp_path: Path) -> None:
    """Die Migration ändert promo_db.json erst mit save()."""
    datei = tmp_path / "promo_db.json"
    shutil.copy2(ZUSTAND / "promo_db.json", datei)
    vorher = datei.read_bytes()
    PromoDB(datei)
    assert datei.read_bytes() == vorher


def test_umformuliertes_angebot_behaelt_seine_id(tmp_path: Path) -> None:
    """Neue Überschrift, gleiche Marke, Zielseite und Zahlen: kein neuer Eintrag."""
    db = _lade(tmp_path)
    alte = set(GRUPPEN["lidl-jahrestarife"])
    treffer = [k for k, e in db.entries.items() if _bekannte_ids(e) & alte]
    assert len(treffer) == 1, (
        f"lidl-jahrestarife: erwartet 1 Eintrag, erhalten {len(treffer)}"
    )
    angebot = {
        "brand": "Lidl Connect",
        "headline": "Ein Jahr surfen ohne Monatsrechnung",
        "description": "Für 149 €, 99,99 € oder 69,99 € einmalig, 100 Mbit/s.",
        "url": LIDL,
    }
    bilanz = db.upsert([angebot], HEUTE, source_url=LIDL)
    assert bilanz.neu == 0, f"umformuliert: {bilanz.neu} neue Einträge statt 0"
    assert bilanz.gesehene_ids == set(treffer)


def test_zwei_angebote_eines_aufrufs_bleiben_zwei(tmp_path: Path) -> None:
    """Ein Aufruf mit zwei Angeboten gleichen Schlüssels legt zwei Einträge an."""
    db = PromoDB(tmp_path / "leer.json")
    seite = "https://www.example.org/aktionen"
    angebote = [
        {"brand": "Probe", "headline": h, "description": "10 GB für 5 €", "url": seite}
        for h in ("Bonus für Neukunden", "Bonus für Bestandskunden")
    ]
    bilanz = db.upsert(angebote, HEUTE, source_url=seite)
    assert bilanz.neu == 2, f"gleichzeitig: {bilanz.neu} neue Einträge statt 2"
    assert len(bilanz.gesehene_ids) == 2


def test_nicht_gelesene_seite_altert_nicht(tmp_path: Path) -> None:
    """mark_stale ohne gelesene Seite ändert keinen Status."""
    db = _lade(tmp_path)
    vorher = {k: e.get("status") for k, e in db.entries.items()}
    for marke in {e.get("brand") for e in db.entries.values()}:
        db.mark_stale(marke, set(), HEUTE, gepruefte_seiten=set())
    assert {k: e.get("status") for k, e in db.entries.items()} == vorher


def test_zweiter_lauf_aendert_nichts(tmp_path: Path) -> None:
    """Dieselben Angebote zweimal: der zweite Aufruf legt nichts an."""
    db = _lade(tmp_path)
    angebote = [
        {k: e.get(k) for k in ("brand", "headline", "description", "url")}
        for e in db.entries.values()
        if e.get("status") == "aktiv"
    ]
    db.upsert(angebote, HEUTE)
    zahl = len(db.entries)
    vorher = {k: e.get("status") for k, e in db.entries.items()}
    bilanz = db.upsert(angebote, HEUTE)
    assert bilanz.neu == 0
    assert len(db.entries) == zahl
    assert {k: e.get("status") for k, e in db.entries.items()} == vorher
