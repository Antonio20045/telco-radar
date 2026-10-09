"""Anbieter ``frei``: kostenlose Modelle verschiedener Anbieter als eine Kette.

Anlass: vom 04.09. bis 07.10.2026 bewertete der Radar 0 Meldungen, weil DeepSeek
jede Anfrage mit HTTP 401 ablehnte und ein 401 den Lauf ohne Ersatzmodell
beendete. Im Anbieter ``frei`` legt ein Anbieter mit falschem oder fehlendem
Schlüssel nur sein eigenes Modell still, die Kette geht weiter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
import pytest

from telco_radar.analyze import llm, llm_frei

ANBIETER = {
    "google": {"base_url": "https://google.invalid/v1", "key_env": "TEST_GEMINI"},
    "groq": {"base_url": "https://groq.invalid/v1", "key_env": "TEST_GROQ"},
    "ovh": {"base_url": "https://ovh.invalid/v1", "key_env": ""},
}
ENDPUNKTE = [
    {"anbieter": "google", "modell": "gemini-flash", "stufen": ["redaktion"]},
    {
        "anbieter": "google",
        "modell": "gemma",
        "stufen": ["mechanik"],
        "system_im_user": True,
        "max_output": 4096,
    },
    {"anbieter": "groq", "modell": "gpt-oss", "stufen": ["mechanik", "redaktion"]},
    {"anbieter": "ovh", "modell": "gpt-oss-120b", "stufen": ["mechanik"]},
]
FLASH, GEMMA, GROQ, OVH = (
    "google:gemini-flash",
    "google:gemma",
    "groq:gpt-oss",
    "ovh:gpt-oss-120b",
)


@dataclass
class _Naehte:
    transport: httpx.MockTransport
    llm_client: None = None


def _antwort(text: str) -> dict:
    return {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


@pytest.fixture
def netz(monkeypatch):
    """Antwortet je Host nach `verhalten`; merkt sich jede Anfrage."""
    monkeypatch.setenv("TEST_GEMINI", "g-key")
    monkeypatch.setenv("TEST_GROQ", "q-key")
    verhalten: dict[str, tuple[int, dict | str]] = {}
    anfragen: list[tuple[str, dict, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        koerper = json.loads(request.content)
        anfragen.append((request.url.host, koerper, dict(request.headers)))
        status, inhalt = verhalten.get(request.url.host, (200, _antwort("ok")))
        if isinstance(inhalt, dict):
            return httpx.Response(status, json=inhalt)
        return httpx.Response(status, text=inhalt)

    llm.LlmSitzung(naehte=_Naehte(httpx.MockTransport(handler))).aktivieren()
    llm_frei.registrieren(ANBIETER, ENDPUNKTE)
    for kette in llm_frei.ketten().values():
        llm.set_model_chain(kette)
    yield verhalten, anfragen
    llm_frei.registrieren({}, [])
    llm.LlmSitzung().aktivieren()


def test_ketten_redaktion_zuerst_dann_mechanik():
    llm_frei.registrieren(ANBIETER, ENDPUNKTE)
    try:
        ketten = llm_frei.ketten()
    finally:
        llm_frei.registrieren({}, [])
    assert ketten["mechanik"] == [GEMMA, GROQ, OVH]
    assert ketten["redaktion"] == [FLASH, GEMMA, GROQ, OVH]


def test_401_legt_nur_diesen_anbieter_still(netz):
    """Der Fehler vom 07.10.: ein ungültiger Schlüssel darf den Lauf nicht beenden."""
    verhalten, anfragen = netz
    verhalten["google.invalid"] = (401, '{"error":"Authentication Fails"}')
    assert llm.complete("sys", "user", GEMMA) == "ok"
    assert [h for h, _, _ in anfragen] == ["google.invalid", "groq.invalid"]
    assert GEMMA in llm.dead_models()


def test_ohne_schluessel_wird_der_anbieter_ohne_anfrage_uebersprungen(
    netz, monkeypatch
):
    _, anfragen = netz
    monkeypatch.delenv("TEST_GEMINI")
    assert llm.complete("sys", "user", FLASH) == "ok"
    assert [h for h, _, _ in anfragen] == ["groq.invalid"]


def test_tageskontingent_leer_geht_zum_naechsten(netz):
    verhalten, anfragen = netz
    verhalten["google.invalid"] = (
        429,
        '{"error":{"message":"Quota exceeded","details":[{"quotaId":'
        '"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}',
    )
    assert llm.complete("sys", "user", GEMMA) == "ok"
    assert [h for h, _, _ in anfragen] == ["google.invalid", "groq.invalid"]


def test_zu_grosse_anfrage_toetet_das_modell_nicht(netz):
    """413 (Groq: über dem Minutenbudget) gilt nur für diese eine Anfrage."""
    verhalten, anfragen = netz
    verhalten["google.invalid"] = (401, "nein")
    verhalten["groq.invalid"] = (413, "Request too large")
    assert llm.complete("sys", "user", GEMMA) == "ok"
    assert [h for h, _, _ in anfragen] == [
        "google.invalid",
        "groq.invalid",
        "ovh.invalid",
    ]
    assert GROQ not in llm.dead_models()


def test_anfrage_traegt_schluessel_modell_und_obergrenze(netz):
    _, anfragen = netz
    llm.complete("SYS", "USER", GEMMA, max_tokens=16000)
    host, koerper, kopf = anfragen[0]
    assert host == "google.invalid"
    assert kopf["authorization"] == "Bearer g-key"
    assert koerper["model"] == "gemma"
    assert koerper["max_tokens"] == 4096
    assert koerper["messages"] == [{"role": "user", "content": "SYS\n\nUSER"}]


def test_anonymer_anbieter_ohne_authorization(netz, monkeypatch):
    verhalten, anfragen = netz
    monkeypatch.delenv("TEST_GROQ")
    verhalten["google.invalid"] = (403, "nein")
    assert llm.complete("sys", "user", GEMMA) == "ok"
    assert anfragen[-1][0] == "ovh.invalid"
    assert "authorization" not in anfragen[-1][2]


def test_verfuegbar_nur_mit_schluessel(monkeypatch):
    monkeypatch.delenv("TEST_GEMINI", raising=False)
    monkeypatch.delenv("TEST_GROQ", raising=False)
    llm_frei.registrieren(ANBIETER, ENDPUNKTE)
    try:
        assert not llm_frei.verfuegbar()
        monkeypatch.setenv("TEST_GROQ", "x")
        assert llm_frei.verfuegbar()
        assert llm.llm_available()
    finally:
        llm_frei.registrieren({}, [])


def test_pipeline_waehlt_frei(monkeypatch):
    import telco_radar.pipeline as pipeline_mod

    monkeypatch.setenv("TEST_GEMINI", "g-key")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm.LlmSitzung().aktivieren()
    settings = {
        "llm_provider": "frei",
        "frei_anbieter": ANBIETER,
        "frei_endpunkte": ENDPUNKTE,
        "llm_anker": False,
    }
    try:
        modelle = pipeline_mod._modelle_waehlen(settings)
        assert (modelle.analyst, modelle.editor, modelle.mechanik) == (
            GEMMA,
            FLASH,
            GEMMA,
        )
        assert llm.kosten_stand()["ohne_preis"] == []
        assert llm.active_backend().startswith("frei")
    finally:
        llm_frei.registrieren({}, [])
        llm.LlmSitzung().aktivieren()


def test_settings_frei_ist_vollstaendig():
    """Die echte Konfiguration: jede Kette hat Glieder, jeder Anbieter eine URL."""
    from pathlib import Path

    from telco_radar.config import load_config

    s = load_config(Path(__file__).resolve().parents[1]).settings
    assert s["llm_provider"] == "frei"
    llm_frei.registrieren(s["frei_anbieter"], s["frei_endpunkte"])
    try:
        ketten = llm_frei.ketten()
    finally:
        llm_frei.registrieren({}, [])
    assert ketten["mechanik"][0].startswith("google:")
    assert ketten["redaktion"][0].startswith("google:")
    assert set(ketten["mechanik"]) <= set(ketten["redaktion"])
