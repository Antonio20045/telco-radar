"""Paket 36: der Laufzustand von ``analyze/llm.py`` steckt in ``LlmSitzung``."""

from __future__ import annotations

import contextlib
from concurrent.futures import ThreadPoolExecutor

import httpx

from telco_radar.analyze import llm
from telco_radar.naehte import PRODUKTION, Naehte


def test_jedes_setzen_beginnt_eine_frische_sitzung(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "probe")
    monkeypatch.setenv("LLM_API_BASE", "https://llm.example/v1")
    leer = httpx.MockTransport(lambda _: httpx.Response(402, json={"error": "leer"}))
    Naehte(transport=leer).setzen()
    llm.set_fallback("a", "b")
    llm.LlmSitzung.aktive().verbrauch["a"] = {"aufrufe": 1}
    with contextlib.suppress(llm.LLMModelUnavailable):
        llm.complete("s", "u", "a", retries=1)
    assert llm.dead_models() == {"a", "b"}

    PRODUKTION.setzen()

    sitzung = llm.LlmSitzung.aktive()
    assert (sitzung.ausweich, sitzung.verbrauch, llm.dead_models()) == ({}, {}, set())


def test_naehte_tragen_den_llm_client_in_die_sitzung():
    Naehte(llm_client=lambda s, u, m, t, r: f"{m}:{u}").setzen()
    assert llm.complete("s", "frage", "modell") == "modell:frage"
    assert llm.LlmSitzung.aktive().naehte is not None


def test_threads_eines_laufs_teilen_die_sitzung():
    def antwort(s, u, m, t, r):
        if m == "tot":
            raise RuntimeError("weg")
        return m

    Naehte(llm_client=antwort).setzen()
    llm.set_fallback("tot", "lebt")
    with ThreadPoolExecutor(max_workers=4) as pool:
        ergebnisse = list(pool.map(lambda _: llm.complete("s", "u", "tot"), range(8)))
    assert set(ergebnisse) == {"lebt"}
    assert llm.dead_models() == {"tot"}
