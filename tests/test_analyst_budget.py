"""Der Kostenzaehler greift NICHT in den Analysten ein (E3, revidiert 27.08.2026).

Die erste Fassung von E3 stoppte weitere Analysten-Stapel, sobald die
Kostenschwelle erreicht war. Antonio hat das noch am selben Tag verworfen,
und die Begruendung stand schon in den Laeufen vom 15. bis 27.08.2026: ein
Lauf, der auf halber Strecke aufhoert zu lesen, ist von einer duennen
Nachrichtenwoche nicht zu unterscheiden. Der Zaehler zaehlt und warnt.

Ein Test fuer etwas, das NICHT passiert, ist hier der richtige Test: die
Sperre war gebaut, und sie wieder einzubauen waere eine Zeile.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from telco_radar.analyze import agents, llm
from telco_radar.models import Item


@pytest.fixture(autouse=True)
def _sauber():
    llm.kosten_reset()
    llm.budget_setzen(0, {})
    yield
    llm.kosten_reset()
    llm.budget_setzen(0, {})


def _items(n: int) -> list[Item]:
    return [Item(id=f"id{i}", title=f"Meldung {i}",
                 url=f"https://example.com/{i}", source_name="Quelle",
                 published=datetime(2026, 8, 27, tzinfo=timezone.utc),
                 region="Europa")
            for i in range(n)]


def _stapelweise(monkeypatch) -> list[int]:
    """Ersetzt den Modellaufruf und zaehlt die Stapel."""
    aufrufe: list[int] = []

    def fake_complete(system, user, model, max_tokens=4096, retries=3,
                      ausweich=""):
        aufrufe.append(len(aufrufe) + 1)
        return json.dumps({"region_summary": "s.", "highlights": []})

    monkeypatch.setattr(agents, "complete", fake_complete)
    return aufrufe


def test_eine_ueberschrittene_schwelle_stoppt_keinen_stapel(monkeypatch):
    """Die Zusicherung, um die es geht: der Lauf liest zu Ende."""
    llm.budget_setzen(0.000001, {"m": {"ein": 1000.0, "aus": 1000.0}})
    # Die Schwelle ist von der ersten gezaehlten Antwort an ueberschritten.
    llm._VERBRAUCH["m"] = {"aufrufe": 1, "prompt_tokens": 1_000_000,
                           "completion_tokens": 1_000_000}
    assert llm.budget_ueberschritten()

    aufrufe = _stapelweise(monkeypatch)
    items = _items(agents.BATCH_SIZE * 3)
    ergebnis = agents.analyze_region("Europa", items, model="m")

    assert len(aufrufe) == 3
    assert ergebnis["_ungelesen"] == []
    assert ergebnis["_telemetry"]["batches_ok"] == 3


def test_der_analyst_fragt_den_zaehler_gar_nicht(monkeypatch):
    """Gegenprobe auf der Code-Ebene: haette die Sperre einen anderen Namen,
    fiele der Test oben nicht auf sie herein - dieser hier schon."""
    import inspect

    quelle = inspect.getsource(agents)
    assert "budget_ueberschritten" not in quelle
    assert "budget_erschoepft" not in quelle


def test_grosse_stapel_sparen_denkspur(monkeypatch):
    """E1 (revidiert): gespart wird an den Token, nicht am Urteil.

    Die Denkspur faellt je AUFRUF an (~8-9k Token bei deepseek-v4-pro),
    kaum je Meldung. Mit 15er-Stapeln brauchten 72 Meldungen fuenf Aufrufe,
    mit 24er drei. Der Test haelt beides: die neue Groesse UND dass keine
    Meldung dabei unter den Tisch faellt.
    """
    aufrufe = _stapelweise(monkeypatch)
    items = _items(72)
    ergebnis = agents.analyze_region("Europa", items, model="m")

    assert agents.BATCH_SIZE == 24
    assert len(aufrufe) == 3
    assert ergebnis["_telemetry"]["items_in"] == 72
    # Das Ausgabebudget traegt Denkspur PLUS Antwort des groesseren Stapels.
    assert agents.ANALYST_MAX_TOKENS >= 16000 + 9 * 190
