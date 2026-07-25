"""Tests fuer die Promo-Uebersicht State-Schicht (analyze/promo_store.py).

Offline: kein Netz/LLM noetig.
"""
from telco_radar.analyze.promo_store import PromoDB, SnapshotStore, entry_id


def _item(brand="congstar", headline="10 GB Bonus", description="", valid_until=None,
          url="https://example.test/aktion", image_url=None):
    return {"brand": brand, "headline": headline, "description": description,
            "valid_until": valid_until, "url": url, "tier": 2, "image_url": image_url}


def test_snapshot_store_change_detection(tmp_path):
    store = SnapshotStore(tmp_path / "snap.json")
    assert store.changed("congstar", "hash1") is True
    store.update("congstar", "hash1", "2026-07-25")
    store.save()
    store2 = SnapshotStore(tmp_path / "snap.json")
    assert store2.changed("congstar", "hash1") is False
    assert store2.changed("congstar", "hash2") is True


def test_promo_db_upsert_and_dedup(tmp_path):
    db = PromoDB(tmp_path / "db.json")
    n = db.upsert([_item(), _item()], "2026-07-25")
    assert n == 1 and len(db) == 1


def test_promo_db_reverify_keeps_first_seen(tmp_path):
    p = tmp_path / "db.json"
    db = PromoDB(p)
    db.upsert([_item()], "2026-07-04")
    db.save("2026-07-04")
    db2 = PromoDB(p)
    db2.upsert([_item()], "2026-07-25")
    entry = list(db2.entries.values())[0]
    assert entry["first_seen"] == "2026-07-04"
    assert entry["last_verified"] == "2026-07-25"
    assert entry["status"] == "aktiv"


def test_mark_stale_flags_but_does_not_delete(tmp_path):
    db = PromoDB(tmp_path / "db.json")
    db.upsert([_item(headline="Alte Aktion"), _item(headline="Neue Aktion")], "2026-07-25")
    still_running = {entry_id("congstar", "Neue Aktion")}
    db.mark_stale("congstar", still_running, "2026-08-01")
    by_headline = {e["headline"]: e for e in db.entries.values()}
    assert by_headline["Alte Aktion"]["status"] == "evtl. ausgelaufen"
    assert by_headline["Neue Aktion"]["status"] == "aktiv"
    assert len(db) == 2  # nichts geloescht


def test_by_brand_groups(tmp_path):
    db = PromoDB(tmp_path / "db.json")
    db.upsert([_item(brand="congstar"), _item(brand="o2", headline="anderes Angebot")],
              "2026-07-25")
    bb = db.by_brand()
    assert len(bb["congstar"]) == 1 and len(bb["o2"]) == 1


def test_persistence_roundtrip(tmp_path):
    p = tmp_path / "db.json"
    db = PromoDB(p)
    db.upsert([_item()], "2026-07-25")
    db.save("2026-07-25")
    assert len(PromoDB(p)) == 1


def test_upsert_stores_image_url_on_new_entry(tmp_path):
    db = PromoDB(tmp_path / "db.json")
    db.upsert([_item(image_url="https://example.test/hero.jpg")], "2026-07-25")
    entry = list(db.entries.values())[0]
    assert entry["image_url"] == "https://example.test/hero.jpg"


def test_upsert_updates_image_url_on_reverify_but_keeps_old_if_missing(tmp_path):
    db = PromoDB(tmp_path / "db.json")
    db.upsert([_item(image_url="https://example.test/first.jpg")], "2026-07-04")
    # Re-verified later without a fresh image (e.g. og:image tag disappeared) -
    # the previously known image must not be silently dropped.
    db.upsert([_item(image_url=None)], "2026-07-25")
    entry = list(db.entries.values())[0]
    assert entry["image_url"] == "https://example.test/first.jpg"
    # A genuinely new image on re-verify does update it.
    db.upsert([_item(image_url="https://example.test/second.jpg")], "2026-08-01")
    entry = list(db.entries.values())[0]
    assert entry["image_url"] == "https://example.test/second.jpg"
