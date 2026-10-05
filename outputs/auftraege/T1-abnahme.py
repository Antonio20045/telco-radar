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
