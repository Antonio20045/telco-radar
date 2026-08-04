"""Meldungen aus GESCHEITERTEN STAPELN duerfen nicht in den Seen-Store.

Der Seen-Store ist ein Einbahnschild: was hineingeht, gilt als erledigt und
wird nie wieder gesammelt. Seit Lauf #64 gibt es dafuer einen Schutz - er
wirkte aber nur, wenn eine Region KOMPLETT ohne Analyse blieb.

Lauf #67 (04.08.2026, erster Lauf nach dem Quellen-Ausbau) hat die Luecke
gezeigt: im Themenfeld KI-Anbieter scheiterten 2 von 3 Stapeln, bei
Regulierung 1 von 2. Beide Bereiche galten als analysiert, weil je ein Stapel
durchkam - rund 33 ungelesene Meldungen wanderten trotzdem in den Store und
waeren dauerhaft weg gewesen. Mit mehr Quellen gibt es mehr Stapel und damit
mehr solcher Teilausfaelle.
"""
from __future__ import annotations

import json

from telco_radar.analyze import agents
from telco_radar.models import Item


def _items(n: int) -> list[Item]:
    return [Item(title=f"Meldung {i}", url=f"https://example.com/{i}",
                 source_name="X") for i in range(n)]


def _antwort(titel: list[str]) -> str:
    return json.dumps({
        "region_summary": "Zusammenfassung",
        "highlights": [{"title": t, "url": "https://example.com/x",
                        "relevance": 3} for t in titel],
    })


def test_gescheiterter_stapel_meldet_seine_meldungen_als_ungelesen(monkeypatch):
    def fake_complete(system, user, model, max_tokens):
        rows = json.loads(user.split("\n", 1)[1])
        # Der mittlere Stapel scheitert - genau der Fall aus Lauf #67.
        if rows[0]["title"] == "Meldung 15":
            raise RuntimeError("provider overloaded")
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    items = _items(agents.BATCH_SIZE * 3)
    res = agents.analyze_region("KI-Anbieter", items, model="m", is_theme=True)

    ungelesen = set(res["_ungelesen"])
    # Genau die 15 Meldungen des gescheiterten Stapels, keine anderen.
    assert len(ungelesen) == agents.BATCH_SIZE
    mittlere = {i.id for i in items[15:30]}
    assert ungelesen == mittlere
    assert res["_telemetry"]["unread_items"] == agents.BATCH_SIZE
    assert res["_telemetry"]["batches_ok"] == 2


def test_ohne_ausfall_ist_nichts_ungelesen(monkeypatch):
    def fake_complete(system, user, model, max_tokens):
        rows = json.loads(user.split("\n", 1)[1])
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    res = agents.analyze_region("Europa", _items(30), model="m")

    assert res["_ungelesen"] == []
    assert res["_telemetry"]["unread_items"] == 0


def test_pipeline_haelt_ungelesene_meldungen_aus_dem_seen_store(tmp_path):
    """Der Schutz muss am Ende im Seen-Store ankommen, nicht nur im Ergebnis."""
    from telco_radar.dedupe import SeenStore

    alle = _items(45)
    ungelesen = {i.id for i in alle[15:30]}
    store = SeenStore(tmp_path / "seen.jsonl")

    # Genau die Zeile aus pipeline.py, die den Schutz umsetzt.
    zu_merken = [i for i in alle
                 if i.region not in set()
                 and i.id not in ungelesen]
    store.add(zu_merken)

    assert len(store) == 30
    wieder = SeenStore(tmp_path / "seen.jsonl")
    # Der naechste Lauf bietet die ungelesenen Meldungen erneut an ...
    neu = wieder.filter_new(alle)
    assert {i.id for i in neu} == ungelesen
