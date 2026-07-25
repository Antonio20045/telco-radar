"""Die Retry-Politik muss billige und teure Fehler unterschiedlich behandeln.

Gemessen am 25.07.2026: ein HTTP 503 "ResourceExhausted" kommt nach 0,3-0,4s
zurueck und bedeutet "gerade voll, frag gleich nochmal". Ein Read-Timeout
kostet die vollen 180s und bringt nichts. Die alte Logik gab nach 3 Versuchen
auf - bei den billigen Fehlern viel zu frueh, bei den teuren viel zu spaet.
"""
from __future__ import annotations

import httpx
import pytest

from telco_radar.analyze import llm


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    """Backoff nicht wirklich schlafen, aber die Uhr weiterlaufen lassen."""
    clock = {"t": 0.0}
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(llm.time, "sleep",
                        lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setenv("LLM_HTTP_TIMEOUT", "180")
    monkeypatch.setenv("LLM_CALL_BUDGET", "300")
    return clock


def _resp(status: int, body: str = "{}"):
    return httpx.Response(status, text=body,
                          request=httpx.Request("POST", "https://x/y"))


BUSY = ('{"error":{"message":"ResourceExhausted: Worker local total request '
        'limit reached (48/48)","type":"Service Unavailable","code":503}}')


def test_viele_billige_503_werden_durchgehalten(monkeypatch, _fast):
    """Der Kern des Fixes: 6x 503 in 0.4s darf nicht zum Abbruch fuehren."""
    calls = {"n": 0}

    def post(url, **kw):
        calls["n"] += 1
        _fast["t"] += 0.4          # ein 503 kommt sofort zurueck
        if calls["n"] <= 6:
            return _resp(503, BUSY)
        return _resp(200, '{"choices":[{"message":{"content":"fertig"}}]}')

    monkeypatch.setattr(llm.httpx, "post", post)
    out = llm._post_with_retries("https://x/y", {}, {}, 3,
                                 lambda d: d["choices"][0]["message"]["content"])
    assert out == "fertig"
    assert calls["n"] == 7


def test_langsame_timeouts_brechen_schnell_ab(monkeypatch, _fast):
    """Ein Modell, das nie antwortet, darf nicht 3x180s kosten."""
    calls = {"n": 0}

    def post(url, **kw):
        calls["n"] += 1
        _fast["t"] += 180.0        # volles HTTP-Timeout verbrannt
        raise httpx.ReadTimeout("The read operation timed out")

    monkeypatch.setattr(llm.httpx, "post", post)
    with pytest.raises(RuntimeError, match="slow"):
        llm._post_with_retries("https://x/y", {}, {}, 3, lambda d: d)
    assert calls["n"] == llm.MAX_SLOW_FAILURES


def test_zeitbudget_begrenzt_den_gesamtaufruf(monkeypatch, _fast):
    def post(url, **kw):
        _fast["t"] += 0.4
        return _resp(503, BUSY)

    monkeypatch.setattr(llm.httpx, "post", post)
    with pytest.raises(RuntimeError, match="budget"):
        llm._post_with_retries("https://x/y", {}, {}, 3, lambda d: d)
    assert _fast["t"] <= 300 + 15


def test_fatale_fehler_werden_nicht_wiederholt(monkeypatch, _fast):
    calls = {"n": 0}

    def post(url, **kw):
        calls["n"] += 1
        _fast["t"] += 0.2
        return _resp(401, '{"error":"invalid key"}')

    monkeypatch.setattr(llm.httpx, "post", post)
    with pytest.raises(llm.LLMFatalError):
        llm._post_with_retries("https://x/y", {}, {}, 3, lambda d: d)
    assert calls["n"] == 1


def test_timeout_default_ist_nicht_mehr_gesenkt(monkeypatch):
    monkeypatch.delenv("LLM_HTTP_TIMEOUT", raising=False)
    assert llm.http_timeout() == 180.0
    monkeypatch.delenv("LLM_CALL_BUDGET", raising=False)
    assert llm.call_budget() == 300.0
