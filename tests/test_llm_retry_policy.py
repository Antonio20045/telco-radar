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


# ------------------------------------------------- Leeres Guthaben (402)
BEZAHLUNG = ('{"error":{"message":"Insufficient Balance","type":'
             '"unknown_error","code":"invalid_request_error"}}')


def test_ein_402_wird_nicht_ein_einziges_mal_wiederholt(monkeypatch, _fast):
    """Der Fehler, der am 15.08.2026 einen ganzen Lauf gekostet hat.

    DeepSeeks Guthaben war 26 Minuten nach dem Start aufgebraucht. Weil 402
    nicht als endgueltig galt, lief es durch den Wiederholungspfad wie ein
    voruebergehender Kapazitaetsengpass: 1245 Wiederholungen ueber zwei
    Stunden, 45 gescheiterte Analysten-Stapel, 20 von 810 Meldungen bewertet,
    0 Uebersetzungen - und der Lauf sah dabei aus wie eine duenne
    Nachrichtenwoche. Ein leeres Konto wird beim 32. Versuch nicht voller.
    """
    calls = {"n": 0}

    def post(url, **kw):
        calls["n"] += 1
        _fast["t"] += 0.8          # ein 402 kommt sofort zurueck: "billig"
        return _resp(402, BEZAHLUNG)

    monkeypatch.setattr(llm.httpx, "post", post)
    with pytest.raises(llm.LLMModelUnavailable):
        llm._post_with_retries("https://x/y", {}, {}, 5,
                               lambda d: d["choices"][0]["message"]["content"])
    assert calls["n"] == 1, (
        f"402 wurde {calls['n']}x versucht - ein leeres Konto ist so "
        f"endgueltig wie ein falscher Schluessel")


def test_das_leere_guthaben_nennt_sich_beim_namen(monkeypatch, _fast):
    """Im Protokoll muss stehen, WARUM der Lauf duenn ist."""
    monkeypatch.setattr(llm.httpx, "post",
                        lambda url, **kw: _resp(402, BEZAHLUNG))
    with pytest.raises(llm.LLMModelUnavailable) as fehler:
        llm._post_with_retries("https://x/y", {}, {}, 3, lambda d: d)
    text = str(fehler.value)
    assert "402" in text and "Guthaben" in text


def test_ein_402_laesst_die_anbieterkette_weiterlaufen(monkeypatch, _fast):
    """Ein leeres Konto ist eine Ablehnung des ANBIETERS, kein defekter
    Request: ein Modell bei einem anderen Anbieter kann sehr wohl antworten.

    Als LLMFatalError waere der Lauf zu Ende, ohne den zweiten Anbieter auch
    nur zu fragen - deshalb ist die Klasse LLMModelUnavailable, die von
    `_complete_with_fallback` als "dieses Modell ueberspringen" behandelt
    wird. Geprueft wird an `complete()` - die Kette lebt dort.
    """
    assert issubclass(llm.LLMModelUnavailable, llm.LLMFatalError)
    gesehen = []

    def _dispatch(system, user, candidate, max_tokens, retries):
        gesehen.append(candidate)
        if len(gesehen) == 1:
            raise llm.LLMModelUnavailable("HTTP 402 Payment Required "
                                          "(Guthaben aufgebraucht)")
        return "vom zweiten Anbieter"

    monkeypatch.setattr(llm, "_dispatch", _dispatch)
    monkeypatch.setattr(llm, "_chain_from", lambda m: ["erstes", "zweites"])
    llm._DEAD_MODELS.clear()
    try:
        out = llm.complete("s", "u", "erstes", max_tokens=100, retries=3)
        assert out == "vom zweiten Anbieter"
        assert gesehen == ["erstes", "zweites"]
        assert "erstes" in llm.dead_models(), (
            "das leere Konto muss fuer den Rest des Laufs vermerkt sein - "
            "sonst steht der Befund nicht auf transparenz.html")
    finally:
        llm._DEAD_MODELS.clear()
