"""Kompaktes Seen-Store-Format (v2) und die Migration des Bestands.

Der Seen-Store ist die einzige Instanz, die verhindert, dass sich der Bericht
wiederholt. Ein Formatwechsel darf deshalb nichts kosten: was vor der
Migration bekannt war, muss danach bekannt sein - sonst kaeme bereits
Berichtetes zurueck in den naechsten Wochenbericht. Genau das pruefen diese
Tests, und zwar getrennt fuer Lesen, Schreiben, Mischbestand und Migration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from telco_radar.dedupe import SeenStore
from telco_radar.models import Item

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import migriere_seen_store as migration  # noqa: E402


def _item(url: str, titel: str = "Eine Meldung", quelle: str = "Testquelle") -> Item:
    return Item(title=titel, url=url, source_name=quelle)


def _v1_zeile(item: Item, stempel: str = "2026-07-17T12:00:00+00:00") -> str:
    return json.dumps({"id": item.id, "url": item.url, "title": item.title,
                       "source": item.source_name, "first_seen": stempel},
                      ensure_ascii=False)


def test_neuer_store_schreibt_kompakt(tmp_path):
    pfad = tmp_path / "seen.jsonl"
    items = [_item(f"https://beispiel.de/{i}") for i in range(3)]
    SeenStore(pfad).add(items)

    text = pfad.read_text(encoding="utf-8")
    assert text.startswith("#")
    hashes = [z for z in text.splitlines() if not z.startswith(("#", "@"))]
    assert hashes == [i.id for i in items]
    # 3 Hashes + Kopfzeile + ein Zeitstempel - deutlich unter dem alten Format
    assert len(text) < 200


def test_hashzeile_ist_17_byte():
    """Die ganze Rechnung 67 MB -> 4 MB haengt an dieser Zeilenlaenge."""
    assert len((_item("https://beispiel.de/x").id + "\n").encode()) == 17


def test_altes_format_wird_weiter_gelesen(tmp_path):
    """Ein Bestand ohne Migration muss unveraendert funktionieren."""
    pfad = tmp_path / "seen.jsonl"
    a, b = _item("https://beispiel.de/a"), _item("https://beispiel.de/b")
    pfad.write_text(_v1_zeile(a) + "\n" + _v1_zeile(b) + "\n", encoding="utf-8")

    store = SeenStore(pfad)
    assert len(store) == 2
    assert not store.is_new(a) and not store.is_new(b)


def test_mischbestand_aus_v1_und_v2(tmp_path):
    """Nach dem ersten Lauf auf einem alten Bestand stehen beide Formate drin."""
    pfad = tmp_path / "seen.jsonl"
    alt = _item("https://beispiel.de/alt")
    pfad.write_text(_v1_zeile(alt) + "\n", encoding="utf-8")

    neu = _item("https://beispiel.de/neu")
    SeenStore(pfad).add([neu])

    wieder = SeenStore(pfad)
    assert len(wieder) == 2
    assert wieder.filter_new([alt, neu]) == []


def test_defekte_zeile_bricht_nicht_ab(tmp_path):
    pfad = tmp_path / "seen.jsonl"
    gut = _item("https://beispiel.de/gut")
    pfad.write_text('{"kaputt": ', encoding="utf-8")
    with open(pfad, "a", encoding="utf-8") as fh:
        fh.write("\n" + gut.id + "\n")
    assert len(SeenStore(pfad)) == 1


def test_add_schreibt_keine_dubletten(tmp_path):
    pfad = tmp_path / "seen.jsonl"
    a = _item("https://beispiel.de/a")
    store = SeenStore(pfad)
    store.add([a])
    store.add([a, _item("https://beispiel.de/b")])
    hashes = [z for z in pfad.read_text().splitlines()
              if not z.startswith(("#", "@"))]
    assert len(hashes) == len(set(hashes)) == 2


def test_add_ohne_neue_meldungen_schreibt_nichts(tmp_path):
    """Sonst waechst die Datei bei jedem Lauf um eine leere Zeitstempelzeile."""
    pfad = tmp_path / "seen.jsonl"
    a = _item("https://beispiel.de/a")
    store = SeenStore(pfad)
    store.add([a])
    vorher = pfad.read_text()
    store.add([a])
    assert pfad.read_text() == vorher


# --------------------------------------------------------------- Migration

def test_migration_erhaelt_jeden_hash(tmp_path):
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True)
    pfad = state / "seen.jsonl"
    items = [_item(f"https://beispiel.de/{i}", quelle=f"Quelle {i % 3}")
             for i in range(20)]
    pfad.write_text("".join(_v1_zeile(i) + "\n" for i in items), encoding="utf-8")
    vorher = {i.id for i in items}

    assert migration.main(["--root", str(tmp_path), "--schreiben"]) == 0

    danach = SeenStore(pfad)
    assert set(danach._seen) == vorher
    assert "{" not in pfad.read_text()


def test_migration_schrumpft_deutlich(tmp_path):
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True)
    pfad = state / "seen.jsonl"
    items = [_item(f"https://beispiel.de/ein-recht-langer-pfad-{i}")
             for i in range(50)]
    pfad.write_text("".join(_v1_zeile(i) + "\n" for i in items), encoding="utf-8")
    vorher = pfad.stat().st_size

    migration.main(["--root", str(tmp_path), "--schreiben"])
    assert pfad.stat().st_size < vorher / 5


def test_migration_ohne_schreiben_aendert_nichts(tmp_path):
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True)
    pfad = state / "seen.jsonl"
    inhalt = _v1_zeile(_item("https://beispiel.de/a")) + "\n"
    pfad.write_text(inhalt, encoding="utf-8")

    assert migration.main(["--root", str(tmp_path)]) == 0
    assert pfad.read_text() == inhalt


def test_migration_haelt_historie_je_quelle_fest(tmp_path):
    """Die Quellen-Zuordnung geht im neuen Format verloren - vorher wird sie
    ausgewertet, sonst waere der historische Nenner der Trefferquote weg."""
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True)
    zeilen = [_v1_zeile(_item(f"https://beispiel.de/a{i}", quelle="Alpha"),
                        "2026-07-17T12:00:00+00:00") for i in range(3)]
    zeilen += [_v1_zeile(_item("https://beispiel.de/b1", quelle="Beta"),
                         "2026-07-20T12:00:00+00:00")]
    (state / "seen.jsonl").write_text("\n".join(zeilen) + "\n", encoding="utf-8")

    migration.main(["--root", str(tmp_path), "--schreiben"])

    historie = json.loads(
        (state / "seen_historie_je_quelle.json").read_text(encoding="utf-8"))
    je_quelle = {e["quelle"]: e for e in historie}
    assert je_quelle["Alpha"]["neu_gesamt"] == 3
    assert je_quelle["Beta"]["erste_meldung"] == "2026-07-20"


def test_migration_ist_wiederholbar(tmp_path):
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True)
    pfad = state / "seen.jsonl"
    pfad.write_text(_v1_zeile(_item("https://beispiel.de/a")) + "\n",
                    encoding="utf-8")
    migration.main(["--root", str(tmp_path), "--schreiben"])
    text = pfad.read_text()
    assert migration.main(["--root", str(tmp_path), "--schreiben"]) == 0
    assert pfad.read_text() == text
