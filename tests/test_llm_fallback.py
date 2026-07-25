"""Verhalten bei einem Provider, der ein Modell nicht mehr bedient.

Reproduziert den Ausfall vom 25.07.2026: der Endpunkt nimmt die Verbindung an
und liefert fuer deepseek-v4-pro kein Token, waehrend v4-flash normal antwortet.
"""
from __future__ import annotations

import pytest

from telco_radar.analyze import llm

PRO = "deepseek-ai/deepseek-v4-pro"
FLASH = "deepseek-ai/deepseek-v4-flash"


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    llm.reset_model_health()
    llm._FALLBACKS.clear()
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid/v1")
    yield
    llm.reset_model_health()
    llm._FALLBACKS.clear()


def _stub(monkeypatch, dead: set[str]) -> list[str]:
    """Ersetzt den Netzwerkaufruf: Modelle in `dead` scheitern wie ein Timeout."""
    calls: list[str] = []

    def fake(system, user, model, max_tokens, retries):
        calls.append(model)
        if model in dead:
            raise RuntimeError("LLM call failed after 3 attempts: "
                               "The read operation timed out")
        return f"antwort von {model}"

    monkeypatch.setattr(llm, "_dispatch", fake)
    return calls


def test_ohne_fallback_schlaegt_der_aufruf_durch(monkeypatch):
    """Ohne registriertes Ausweichmodell bleibt das Verhalten wie vorher."""
    _stub(monkeypatch, {PRO})
    with pytest.raises(RuntimeError):
        llm.complete("sys", "user", PRO)


def test_totes_modell_weicht_auf_das_ausweichmodell_aus(monkeypatch):
    calls = _stub(monkeypatch, {PRO})
    llm.set_fallback(PRO, FLASH)

    assert llm.complete("sys", "user", PRO) == f"antwort von {FLASH}"
    assert calls == [PRO, FLASH]


def test_zweite_stufe_versucht_das_tote_modell_nicht_erneut(monkeypatch):
    """Der Kern des Fixes: 4 Stufen duerfen nicht 4x ins Timeout laufen."""
    calls = _stub(monkeypatch, {PRO})
    llm.set_fallback(PRO, FLASH)

    for _ in range(4):
        assert llm.complete("sys", "user", PRO) == f"antwort von {FLASH}"

    # genau ein Fehlversuch auf PRO, danach direkt FLASH
    assert calls.count(PRO) == 1
    assert calls.count(FLASH) == 4
    assert llm.dead_models() == {PRO}


def test_gesundes_modell_wird_nicht_ersetzt(monkeypatch):
    calls = _stub(monkeypatch, set())
    llm.set_fallback(PRO, FLASH)

    assert llm.complete("sys", "user", PRO) == f"antwort von {PRO}"
    assert calls == [PRO]
    assert llm.dead_models() == set()


def test_fataler_fehler_loest_keinen_fallback_aus(monkeypatch):
    """Ein falscher Key scheitert auf jedem Modell - nicht doppelt versuchen."""
    calls: list[str] = []

    def fake(system, user, model, max_tokens, retries):
        calls.append(model)
        raise llm.LLMFatalError("LLM fatal error: HTTP 401")

    monkeypatch.setattr(llm, "_dispatch", fake)
    llm.set_fallback(PRO, FLASH)

    with pytest.raises(llm.LLMFatalError):
        llm.complete("sys", "user", PRO)
    assert calls == [PRO]


def test_set_fallback_ignoriert_selbstreferenz():
    llm.set_fallback(PRO, PRO)
    llm.set_fallback(PRO, "")
    assert llm._FALLBACKS == {}


def test_http_timeout_ist_konfigurierbar(monkeypatch):
    assert llm.http_timeout() == llm.DEFAULT_HTTP_TIMEOUT
    monkeypatch.setenv("LLM_HTTP_TIMEOUT", "30")
    assert llm.http_timeout() == 30.0
    monkeypatch.setenv("LLM_HTTP_TIMEOUT", "unsinn")
    assert llm.http_timeout() == llm.DEFAULT_HTTP_TIMEOUT
    monkeypatch.setenv("LLM_HTTP_TIMEOUT", "0")
    assert llm.http_timeout() == llm.DEFAULT_HTTP_TIMEOUT
