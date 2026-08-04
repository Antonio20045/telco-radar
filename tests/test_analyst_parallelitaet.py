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


# --------------------------------------------------- ein Pool fuer alle
# Lauf #69: 793 von 984 neuen Meldungen lagen im Bereich "Global" - jede
# Fachpressemeldung ohne Betreiber im Titel. 53 Stapel dort, 19 in den
# zwoelf anderen Bereichen zusammen. Mit einem Pool JE BEREICH arbeitete
# Global zu viert, waehrend die uebrigen Worker stillagen.

def test_ein_grosser_bereich_nutzt_den_ganzen_pool(monkeypatch):
    hoechststand = 0
    gleichzeitig = 0
    sperre = threading.Lock()

    def fake_complete(system, user, model, max_tokens):
        nonlocal gleichzeitig, hoechststand
        with sperre:
            gleichzeitig += 1
            hoechststand = max(hoechststand, gleichzeitig)
        threading.Event().wait(0.02)
        with sperre:
            gleichzeitig -= 1
        rows = json.loads(user.split("\n", 1)[1])
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    bereiche = [("Global", _items(agents.BATCH_SIZE * 20), False),
                ("Europa", _items(agents.BATCH_SIZE), False)]

    ergebnisse = agents.analyze_bereiche(bereiche, model="m", workers=12)

    assert hoechststand > 4, f"nur {hoechststand} gleichzeitig - der Pool " \
        "wird von einem grossen Bereich nicht ausgenutzt"
    assert set(ergebnisse) == {"Global", "Europa"}
    assert ergebnisse["Global"]["_telemetry"]["batches"] == 20
    assert ergebnisse["Europa"]["_telemetry"]["batches"] == 1


def test_gescheiterte_stapel_bleiben_je_bereich_zugeordnet(monkeypatch):
    monkeypatch.setattr(agents.time, "sleep", lambda s: None)

    def fake_complete(system, user, model, max_tokens):
        if "Europa" in user:
            raise RuntimeError("Anbieter ueberlastet")
        rows = json.loads(user.split("\n", 1)[1])
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    bereiche = [("Global", _items(agents.BATCH_SIZE), False),
                ("Europa", _items(agents.BATCH_SIZE * 2), False)]

    ergebnisse = agents.analyze_bereiche(bereiche, model="m", workers=4)

    assert ergebnisse["Global"]["_telemetry"]["unread_items"] == 0
    assert ergebnisse["Europa"]["_telemetry"]["unread_items"] == \
        agents.BATCH_SIZE * 2
    assert len(ergebnisse["Europa"]["_ungelesen"]) == agents.BATCH_SIZE * 2


def test_themenfelder_bekommen_ihren_eigenen_prompt(monkeypatch):
    gesehen: list[str] = []

    def fake_complete(system, user, model, max_tokens):
        gesehen.append(system)
        rows = json.loads(user.split("\n", 1)[1])
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    agents.analyze_bereiche([("Europa", _items(2), False),
                             ("Chips & Modems", _items(2), True)],
                            model="m", workers=2)

    assert any("NOT from competing operators" in s for s in gesehen)
    assert any("competitive-intelligence analyst" in s for s in gesehen)


def test_gescheiterte_stapel_bekommen_einen_nachlauf(monkeypatch):
    """Lauf #69: 42 von 72 Stapeln fielen aus, weil der Anbieter unter dem
    Burst wegbrach - nicht, weil er tot war. Ein entdrosselter zweiter
    Durchgang trifft ihn freier an."""
    monkeypatch.setattr(agents.time, "sleep", lambda s: None)
    runde = {"n": 0}

    def fake_complete(system, user, model, max_tokens):
        runde["n"] += 1
        if runde["n"] <= 3:            # der Burst scheitert
            raise RuntimeError("Anbieter ueberlastet")
        rows = json.loads(user.split("\n", 1)[1])
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    ergebnisse = agents.analyze_bereiche(
        [("Global", _items(agents.BATCH_SIZE * 5), False)],
        model="m", workers=8)

    tel = ergebnisse["Global"]["_telemetry"]
    assert tel["batches"] == 5
    assert tel["batches_ok"] == 5, "der Nachlauf hat nichts gerettet"
    assert tel["unread_items"] == 0


def test_was_auch_im_nachlauf_scheitert_bleibt_ungelesen(monkeypatch):
    """Der Nachlauf ist kein Ersatz fuer den Schutz - nur eine Milderung."""
    monkeypatch.setattr(agents.time, "sleep", lambda s: None)

    def fake_complete(system, user, model, max_tokens):
        if "Meldung 0" in user:
            raise RuntimeError("dauerhaft kaputt")
        rows = json.loads(user.split("\n", 1)[1])
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    ergebnisse = agents.analyze_bereiche(
        [("Global", _items(agents.BATCH_SIZE * 3), False)],
        model="m", workers=4)

    assert ergebnisse["Global"]["_telemetry"]["unread_items"] == agents.BATCH_SIZE


def test_ohne_ausfall_kein_nachlauf(monkeypatch):
    aufrufe = {"n": 0}

    def fake_complete(system, user, model, max_tokens):
        aufrufe["n"] += 1
        rows = json.loads(user.split("\n", 1)[1])
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    agents.analyze_bereiche([("Global", _items(agents.BATCH_SIZE * 3), False)],
                            model="m", workers=4)
    assert aufrufe["n"] == 3


def test_analysten_budget_reicht_fuer_das_nachdenken():
    """Lauf #71: 22 von 30 Stapeln kamen LEER zurueck - json.loads("") -,
    kein einziger 429. Bei einem Reasoning-Modell zaehlt das Nachdenken
    gegen max_tokens; reicht das Budget nur dafuer, kommt nichts zurueck."""
    assert agents.ANALYST_MAX_TOKENS >= 16000


def test_stapel_nutzt_das_konfigurierte_budget(monkeypatch):
    gesehen: list[int] = []

    def fake_complete(system, user, model, max_tokens):
        gesehen.append(max_tokens)
        rows = json.loads(user.split("\n", 1)[1])
        return _antwort([r["title"] for r in rows])

    monkeypatch.setattr(agents, "complete", fake_complete)
    agents.analyze_bereiche([("Europa", _items(2), False)], model="m")
    assert gesehen == [agents.ANALYST_MAX_TOKENS]
