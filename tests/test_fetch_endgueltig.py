"""Ein 404 oder 410 ist eine Antwort, kein Ausfall: ein Abruf, kein zweiter Absender.

Gerätelauf 07.10.2026: neun tote Saturn-Markenseiten kosteten je sechs Abrufe
(drei Versuche mal zwei Absender) und zusammen rund fünf Minuten Zeitbudget, das o2
danach fehlte. Ein anderer Absender nach einem 404 wäre zudem ein Umweg um eine
Sperre (CLAUDE.md Regel 4).
"""

from __future__ import annotations

import httpx
import pytest

from telco_radar.collect import http


@pytest.fixture
def naht(monkeypatch):
    def setze(status: int) -> list[httpx.Request]:
        gesehen: list[httpx.Request] = []

        def antworte(anfrage: httpx.Request) -> httpx.Response:
            gesehen.append(anfrage)
            return httpx.Response(status, text="x")

        monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(antworte))
        monkeypatch.setattr(http, "_BACKOFF_WAITS", (0.0, 0.0))
        return gesehen

    return setze


@pytest.mark.parametrize("status", [404, 410])
def test_tote_adresse_kostet_genau_einen_abruf(naht, status):
    gesehen = naht(status)
    with pytest.raises(httpx.HTTPStatusError) as fehler:
        http.fetch("https://www.saturn.de/de/brand/apple/iphone/iphone-14", {})
    assert fehler.value.response.status_code == status
    assert len(gesehen) == 1


def test_gegenprobe_serverfehler_wird_weiter_wiederholt(naht):
    gesehen = naht(503)
    with pytest.raises(httpx.HTTPStatusError):
        http.fetch("https://www.saturn.de/de/brand/apple/iphone/iphone-17", {})
    assert len(gesehen) == 3


def test_gegenprobe_anderer_client_fehler_bleibt_bei_der_ausdauer(naht):
    gesehen = naht(400)
    with pytest.raises(httpx.HTTPStatusError):
        http.fetch("https://www.saturn.de/de/brand/apple/iphone/iphone-17", {})
    assert len(gesehen) == 6
