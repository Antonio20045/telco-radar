"""Der Ausfallhinweis der Titelseite nennt den echten Grund.

Vom 04.09. bis 07.10.2026 stand dort „eine vorübergehende Störung des
Analyse-Dienstes“, obwohl der Grund ein ungültiger Schlüssel war (HTTP 401).
"""

from __future__ import annotations

import contextlib

from telco_radar.analyze import llm
from telco_radar.analyze.redaktion_kontinuitaet import (
    GRUND_ABGELEHNT,
    GRUND_KEIN_SCHLUESSEL,
    GRUND_KONTINGENT,
    GRUND_STOERUNG,
    ausfallgrund,
)

DEEPSEEK_0710 = (
    'LLM fatal error: HTTP 401: {"error":{"message":"Authentication Fails, '
    'Your api key: ****0e0e is invalid"}}'
)


def test_ohne_schluessel():
    assert ausfallgrund({}, schluessel_da=False) == GRUND_KEIN_SCHLUESSEL


def test_alle_abgelehnt_wie_am_07_10():
    tote = {"google:gemma": DEEPSEEK_0710, "groq:x": "Schluessel GROQ fehlt fuer x"}
    assert ausfallgrund(tote, schluessel_da=True) == GRUND_ABGELEHNT


def test_kontingent_leer():
    tote = {
        "google:gemma": "daily token quota exhausted: GenerateRequestsPerDay",
        "groq:x": DEEPSEEK_0710,
    }
    assert ausfallgrund(tote, schluessel_da=True) == GRUND_KONTINGENT


def test_sonst_allgemeine_stoerung():
    tote = {"google:gemma": "LLM call failed after 3 attempts: ReadTimeout"}
    assert ausfallgrund(tote, schluessel_da=True) == GRUND_STOERUNG
    assert ausfallgrund({}, schluessel_da=True) == GRUND_STOERUNG


def test_complete_merkt_den_grund_je_modell():
    def antwort(s, u, m, t, r):
        raise llm.LLMModelUnavailable(DEEPSEEK_0710)

    llm.LlmSitzung(naehte=_Naehte(antwort)).aktivieren()
    try:
        with contextlib.suppress(llm.LLMModelUnavailable):
            llm.complete("s", "u", "a")
        assert "HTTP 401" in llm.LlmSitzung.aktive().tote_modelle["a"]
    finally:
        llm.LlmSitzung().aktivieren()


class _Naehte:
    transport = None

    def __init__(self, client):
        self.llm_client = client
