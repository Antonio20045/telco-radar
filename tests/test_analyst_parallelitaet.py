"""Stapel einer Region duerfen parallel laufen - ohne die Ausgabe zu aendern.

Der Quellen-Ausbau vervielfacht die Zahl der Meldungen. Der Lauf vom
31.07.2026 brauchte mit 220 neuen Meldungen bereits 49 von 50 zulaessigen
Minuten, weil jede Region ihre Stapel streng nacheinander abarbeitete. Eine
Kappung ist ausgeschlossen (der Seen-Store merkt sich jede neue Meldung als
erledigt, egal ob sie jemand gelesen hat) - also muss die Parallelitaet
steigen. Diese Tests halten fest, dass dabei nichts verloren geht.
"""
from __future__ import annotations

import json
import threading

from telco_radar.analyze import agents
from telco_radar.models import Item


def _items(n: int) -> list[Item]:
    return [Item(title=f"Meldung {i}", url=f"https://example.com/{i}",
                 source_name="X") for i in range(n)]


def _antwort(titel: list[str]) -> str:
    return json.dumps({
        "region_summary": f"Zusammenfassung {titel[0]}",
        "highlights": [{"title": t, "url": "https://example.com/x",
                        "relevance": 3} for t in titel],
    })


def test_parallele_stapel_liefern_dieselbe_reihenfolge(monkeypatch):
    def fake_complete(system, user, model, max_tokens):
        rows = json.loads(user.split("\n", 1)[1])
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    items = _items(agents.BATCH_SIZE * 4)

    seriell = agents.analyze_region("Europa", items, model="m", batch_workers=1)
    parallel = agents.analyze_region("Europa", items, model="m", batch_workers=4)

    assert [h["title"] for h in parallel["highlights"]] == \
        [h["title"] for h in seriell["highlights"]]
    assert parallel["region_summary"] == seriell["region_summary"]
    assert parallel["_telemetry"]["batches_ok"] == 4


def test_parallele_stapel_laufen_wirklich_gleichzeitig(monkeypatch):
    gleichzeitig = 0
    hoechststand = 0
    sperre = threading.Lock()
    tor = threading.Barrier(3, timeout=5)

    def fake_complete(system, user, model, max_tokens):
        nonlocal gleichzeitig, hoechststand
        with sperre:
            gleichzeitig += 1
            hoechststand = max(hoechststand, gleichzeitig)
        # Blockiert, bis drei Stapel gleichzeitig hier stehen. Bei serieller
        # Abarbeitung laeuft die Barriere in ihren Timeout.
        tor.wait()
        with sperre:
            gleichzeitig -= 1
        return _antwort(["A"])

    monkeypatch.setattr(agents, "complete", fake_complete)
    res = agents.analyze_region("Europa", _items(agents.BATCH_SIZE * 3),
                                model="m", batch_workers=3)

    assert hoechststand == 3
    assert res["_telemetry"]["batches_ok"] == 3


def test_ein_gescheiterter_stapel_kostet_nur_seine_meldungen(monkeypatch):
    """Genau wie im seriellen Fall: der Stapel faellt aus, der Lauf nicht."""
    def fake_complete(system, user, model, max_tokens):
        rows = json.loads(user.split("\n", 1)[1])
        if rows[0]["title"] == "Meldung 15":
            raise RuntimeError("provider overloaded")
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    res = agents.analyze_region("Europa", _items(agents.BATCH_SIZE * 3),
                                model="m", batch_workers=3)

    assert res["_telemetry"]["batches"] == 3
    assert res["_telemetry"]["batches_ok"] == 2
    titel = {h["title"] for h in res["highlights"]}
    assert "Meldung 0" in titel and "Meldung 30" in titel
    assert "Meldung 15" not in titel
