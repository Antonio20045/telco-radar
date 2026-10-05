"""Abnahme T3: Zahlen trennen Angebote, ein Wiederfund ohne Link bestätigt."""

from __future__ import annotations

import shutil
from pathlib import Path

from bestand_pfad import ZUSTAND

from telco_radar.analyze.promo_store import PromoDB

GESTERN = "2026-10-04"
HEUTE = "2026-10-05"
MARKE = "Blau"
BLAU_S = "76cf8ed5f2632a42"
SEITE = "https://www.blau.de/tarife/handyvertrag-fuer-studenten"
ANDERE_SEITE = "https://www.blau.de/tarife/prepaid"
BONUS_ZIEL = "https://www.blau.de/aktion/datenbonus"


def _lade(tmp_path: Path) -> PromoDB:
    """Lädt eine Kopie der Promo-Datenbank aus dem Schnappschuss."""
    ziel = tmp_path / "promo_db.json"
    shutil.copy2(ZUSTAND / "promo_db.json", ziel)
    return PromoDB(ziel)


def _eintrag_mit_alter_id(db: PromoDB, alte_id: str) -> dict:
    """Der eine Eintrag, der die alte ID trägt."""
    treffer = [
        e
        for e in db.entries.values()
        if alte_id in {e.get("id"), *e.get("alteIds", [])}
    ]
    assert len(treffer) == 1, f"{alte_id}: {len(treffer)} Einträge im Schnappschuss"
    return treffer[0]


def _aktive(db: PromoDB) -> int:
    """Zahl der aktiven Einträge."""
    return sum(1 for e in db.entries.values() if e.get("status") == "aktiv")


def _bonus(headline: str) -> dict:
    """Ein Angebot der Marke mit gemeinsamer Zielseite und leerer Beschreibung."""
    return {"brand": MARKE, "headline": headline, "description": "", "url": BONUS_ZIEL}


def _ids_mit_ueberschrift(db: PromoDB, headline: str) -> set[str]:
    """IDs der Einträge, deren Überschrift genau so lautet."""
    return {eid for eid, e in db.entries.items() if e.get("headline") == headline}


def test_zahlen_in_der_ueberschrift_trennen_angebote(tmp_path: Path) -> None:
    """10 GB Bonus und später 20 GB Bonus bleiben zwei Einträge."""
    db = _lade(tmp_path)
    db.upsert([_bonus("10 GB Bonus")], GESTERN, SEITE)
    vorher = len(db)
    bilanz = db.upsert([_bonus("20 GB Bonus")], HEUTE, SEITE)
    zehn = _ids_mit_ueberschrift(db, "10 GB Bonus")
    zwanzig = _ids_mit_ueberschrift(db, "20 GB Bonus")
    assert bilanz.neu == 1 and len(db) == vorher + 1 and zehn and zwanzig, (
        "10 GB und 20 GB zusammengelegt: "
        f"neu={bilanz.neu}, Einträge {vorher}->{len(db)}, "
        f"10 GB in {sorted(zehn)}, 20 GB in {sorted(zwanzig)}"
    )
    assert zehn.isdisjoint(zwanzig)


def test_wiederfund_ohne_link_bestaetigt_bekannten_eintrag(tmp_path: Path) -> None:
    """Ohne URL und source_url wird Blau Allnet S bestätigt, sein Link bleibt."""
    db = _lade(tmp_path)
    bekannt = _eintrag_mit_alter_id(db, BLAU_S)
    link = bekannt["url"]
    aktiv_vorher = _aktive(db)
    vorher = len(db)
    angebot = {
        "brand": MARKE,
        "headline": bekannt["headline"],
        "description": bekannt["description"],
        "url": "",
    }
    bilanz = db.upsert([angebot], HEUTE, "")
    assert bilanz.neu == 0 and len(db) == vorher, (
        f"Wiederfund ohne Link legte neu an: neu={bilanz.neu}, "
        f"Einträge {vorher}->{len(db)}"
    )
    assert bekannt["id"] in bilanz.gesehene_ids, "bekannter Eintrag nicht bestätigt"
    assert bekannt["last_verified"] == HEUTE
    assert bekannt["url"] == link, f"Link überschrieben: {bekannt['url']!r}"
    assert _aktive(db) == aktiv_vorher


def test_dieselben_angebote_zweimal_ergeben_nichts_neues(tmp_path: Path) -> None:
    """Der zweite Aufruf mit denselben Angeboten legt nichts an."""
    db = _lade(tmp_path)
    angebote = [_bonus("10 GB Bonus"), _bonus("Gratis-Monat Bonus")]
    db.upsert(angebote, GESTERN, SEITE)
    vorher = len(db)
    bilanz = db.upsert(angebote, HEUTE, SEITE)
    assert bilanz.neu == 0 and len(db) == vorher
    assert bilanz.bestaetigt == 2


def test_gleicher_schluessel_im_selben_aufruf_bleibt_getrennt(tmp_path: Path) -> None:
    """Zwei Angebote eines Aufrufs, gleicher Schlüssel, andere Überschrift."""
    db = _lade(tmp_path)
    vorher = len(db)
    bilanz = db.upsert(
        [_bonus("Gratis-Monat Bonus"), _bonus("Startguthaben Bonus")], HEUTE, SEITE
    )
    assert bilanz.neu == 2 and len(db) == vorher + 2


def test_nicht_gelesene_seite_altert_nicht(tmp_path: Path) -> None:
    """mark_stale altert nur Einträge der gelesenen Seiten."""
    db = _lade(tmp_path)
    db.upsert([_bonus("10 GB Bonus")], GESTERN, SEITE)
    (eid,) = _ids_mit_ueberschrift(db, "10 GB Bonus")
    db.mark_stale(MARKE, set(), HEUTE, gepruefte_seiten={ANDERE_SEITE})
    assert db.entries[eid]["status"] == "aktiv"
    assert db.entries[eid]["missed_checks"] == 0


def test_upsert_schreibt_nicht_auf_die_platte(tmp_path: Path) -> None:
    """Nur save() schreibt die Datei."""
    db = _lade(tmp_path)
    vorher = db.path.read_bytes()
    db.upsert([_bonus("10 GB Bonus"), _bonus("20 GB Bonus")], HEUTE, SEITE)
    assert db.path.read_bytes() == vorher
