"""Tests für die dynamische Differenzierungs-DB (analyze/category_sweep.py).

Offline: kein Brave/LLM nötig (upsert/dedup/rotation).
"""
from telco_radar.analyze.category_sweep import DiffDB, rotation_slice, THEMES


def _item(url, theme="ki", op="Op", what="tut etwas"):
    return {"theme": theme, "operator": op, "region": "Europa",
            "what": what, "url": url, "why": "relevant"}


def test_upsert_and_dedup(tmp_path):
    db = DiffDB(tmp_path / "db.json")
    n = db.upsert([_item("https://a.test/1"), _item("https://a.test/1")], "2026-07-21")
    assert n == 1 and len(db) == 1


def test_reverify_updates_last_verified(tmp_path):
    p = tmp_path / "db.json"
    db = DiffDB(p)
    db.upsert([_item("https://a.test/1")], "2026-07-01")
    db.save("2026-07-01")
    db2 = DiffDB(p)
    db2.upsert([_item("https://a.test/1")], "2026-07-21")   # gleiche URL erneut gesehen
    assert len(db2) == 1
    assert list(db2.entries.values())[0]["last_verified"] == "2026-07-21"
    assert list(db2.entries.values())[0]["first_seen"] == "2026-07-01"


def test_by_theme_groups(tmp_path):
    db = DiffDB(tmp_path / "db.json")
    db.upsert([_item("https://a.test/1", theme="ki"),
               _item("https://a.test/2", theme="cloud")], "2026-07-21")
    bt = db.by_theme()
    assert len(bt["ki"]) == 1 and len(bt["cloud"]) == 1


def test_persistence_roundtrip(tmp_path):
    p = tmp_path / "db.json"
    db = DiffDB(p)
    db.upsert([_item("https://a.test/1")], "2026-07-21")
    db.save("2026-07-21")
    assert len(DiffDB(p)) == 1


def test_rotation_covers_all_over_weeks():
    keys = {k for k, _ in THEMES}
    seen = set()
    for w in range(0, 6):
        seen.update(rotation_slice(w, per_run=4))
    assert seen == keys            # nach wenigen Wochen sind alle Hebel dran


def test_seed_db_loads():
    # Der ausgelieferte Startbestand muss ladbar und nicht leer sein.
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "data" / "state" / "differentiation_db.json"
    if p.exists():
        db = DiffDB(p)
        assert len(db) > 10
