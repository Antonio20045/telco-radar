"""Die Bedrock-Praeferenzkette: nimm das beste Modell, das das Konto bedient.

Welche Claude-Modelle ein Bedrock-Konto aufrufen darf, haengt an Agreements,
Kontingenten und AWS-Vertrieb und aendert sich ohne Ankuendigung. Der Lauf soll
deshalb nicht auf eine ID festgenagelt sein, sondern die Kette ablaufen.
"""
from __future__ import annotations

import pytest

from telco_radar.analyze import llm


@pytest.fixture(autouse=True)
def _sauberer_zustand():
    llm._FALLBACKS.clear()
    llm.reset_model_health()
    yield
    llm._FALLBACKS.clear()
    llm.reset_model_health()


def _antworten(monkeypatch, verhalten: dict[str, object]) -> list[str]:
    """Ersetzt den Backend-Versand; protokolliert die tatsaechliche Reihenfolge."""
    versucht: list[str] = []

    def fake_dispatch(system, user, model, max_tokens, retries):
        versucht.append(model)
        ergebnis = verhalten.get(model)
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return ergebnis if ergebnis is not None else f"ok:{model}"

    monkeypatch.setattr(llm, "_dispatch", fake_dispatch)
    return versucht


def test_kette_nimmt_das_erste_modell_das_antwortet(monkeypatch):
    kopf = llm.set_model_chain(["best", "mittel", "klein"])
    assert kopf == "best"
    versucht = _antworten(monkeypatch, {
        "best": llm.LLMModelUnavailable("not available for this account"),
        "mittel": "ok:mittel",
    })
    assert llm.complete("s", "u", kopf) == "ok:mittel"
    assert versucht == ["best", "mittel"]


def test_kette_ueberspringt_totes_modell_beim_zweiten_aufruf(monkeypatch):
    """Ein abgelehntes Modell darf nicht bei jeder Stufe erneut kosten."""
    kopf = llm.set_model_chain(["best", "mittel"])
    versucht = _antworten(monkeypatch, {
        "best": llm.LLMModelUnavailable("INVALID_PAYMENT_INSTRUMENT"),
    })
    llm.complete("s", "u", kopf)
    versucht.clear()
    llm.complete("s", "u", kopf)
    assert versucht == ["mittel"], "das tote Modell wurde erneut angefragt"


def test_echter_konfigurationsfehler_bricht_ab(monkeypatch):
    """Ein kaputter Key ist kein Grund, die ganze Kette durchzuprobieren."""
    kopf = llm.set_model_chain(["best", "mittel"])
    versucht = _antworten(monkeypatch, {
        "best": llm.LLMFatalError("HTTP 401: invalid api key"),
    })
    with pytest.raises(llm.LLMFatalError):
        llm.complete("s", "u", kopf)
    assert versucht == ["best"], "nach einem 401 wurde weitergesucht"


def test_letzter_fehler_wird_gemeldet_wenn_nichts_geht(monkeypatch):
    kopf = llm.set_model_chain(["a", "b"])
    _antworten(monkeypatch, {
        "a": llm.LLMModelUnavailable("kein Zugriff"),
        "b": llm.LLMModelUnavailable("auch kein Zugriff"),
    })
    with pytest.raises(llm.LLMModelUnavailable, match="auch kein Zugriff"):
        llm.complete("s", "u", kopf)


def test_kette_bricht_zyklen_auf():
    llm.set_fallback("a", "b")
    llm.set_fallback("b", "a")
    assert llm._chain_from("a") == ["a", "b"]


def test_gesetzter_vorzug_schlaegt_die_kette():
    """editor->analyst wird von der Kette nicht ueberschrieben."""
    llm.set_fallback("gross", "klein")
    llm.set_model_chain(["gross", "mittel"])
    assert llm._FALLBACKS["gross"] == "klein"


@pytest.mark.parametrize("text,erwartet", [
    ("anthropic.claude-sonnet-5 is not available for this account", True),
    ("Model access is denied due to INVALID_PAYMENT_INSTRUMENT", True),
    ("The model 'anthropic.claude-sonnet-4-6' does not exist", True),
    ("Model use case details have not been submitted", True),
    ("HTTP 401: invalid api key", False),
    ("HTTP 400: max_tokens is required", False),
])
def test_nur_modellbezogene_ablehnungen_gelten_als_modellfehler(text, erwartet):
    assert llm._is_model_access_error(text) is erwartet


def test_leere_antwort_wird_erklaert(caplog):
    """Ohne stop_reason und Blocktypen ist eine leere Antwort nicht deutbar."""
    import logging
    with caplog.at_level(logging.WARNING):
        text = llm._anthropic_text({
            "content": [{"type": "thinking", "thinking": "..."}],
            "stop_reason": "max_tokens",
            "usage": {"output_tokens": 8000},
        })
    assert text == ""
    assert "max_tokens" in caplog.text and "thinking" in caplog.text


def test_normale_antwort_meldet_nichts(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        assert llm._anthropic_text(
            {"content": [{"type": "text", "text": "Hallo"}]}) == "Hallo"
    assert caplog.text == ""
