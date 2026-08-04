"""llm_provider: der Anbieter wird konfiguriert, nicht aus Zufall gewaehlt.

Unter "auto" gewinnt der zuerst gefundene Schluessel. Solange der NVIDIA-
Schluessel im Repo liegt, kaeme Anthropic damit nie zum Zug - deshalb muss ein
Anbieterwechsel eine Konfigurationszeile sein und kein Loeschen von Secrets.
"""
from __future__ import annotations

import pytest

from telco_radar.analyze import llm


ALLE_SCHLUESSEL = ("AWS_BEARER_TOKEN_BEDROCK", "LLM_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture
def umgebung(monkeypatch):
    """Alle drei Schluessel gesetzt - der Streitfall, um den es geht."""
    for name in ALLE_SCHLUESSEL:
        monkeypatch.setenv(name, f"test-{name.lower()}")
    return monkeypatch


def _aktives_backend(settings: dict) -> str:
    """Fuehrt die Anbieterwahl der Pipeline aus und fragt llm.py, wer gewann.

    Bewusst ueber active_backend() geprueft und nicht ueber die Variablen der
    Pipeline: llm.py entscheidet allein anhand der Umgebung, und genau dieses
    Auseinanderlaufen soll der Test ausschliessen.
    """
    from telco_radar.pipeline import _waehle_anbieter

    _waehle_anbieter(settings)
    return llm.active_backend()


BASIS = {"llm_api_base": "https://example.invalid/v1"}


def test_anthropic_gewinnt_trotz_gesetztem_nvidia_schluessel(umgebung):
    assert _aktives_backend({**BASIS, "llm_provider": "anthropic"}) == "anthropic"


def test_openai_erzwingbar_obwohl_bedrock_token_da_ist(umgebung):
    assert _aktives_backend({**BASIS, "llm_provider": "openai"}).startswith("openai")


def test_bedrock_erzwingbar(umgebung):
    assert _aktives_backend({**BASIS, "llm_provider": "bedrock"}).startswith("bedrock")


def test_auto_behaelt_die_alte_reihenfolge(umgebung):
    assert _aktives_backend({**BASIS, "llm_provider": "auto"}).startswith("bedrock")


def test_fehlende_einstellung_verhaelt_sich_wie_auto(umgebung):
    assert _aktives_backend(dict(BASIS)).startswith("bedrock")


def test_unbekannter_wert_faellt_auf_auto_zurueck(umgebung):
    assert _aktives_backend({**BASIS, "llm_provider": "quatsch"}).startswith("bedrock")


def test_anthropic_ohne_anthropic_schluessel_waehlt_nicht_heimlich_nvidia(monkeypatch):
    """Ohne Schluessel soll der Lauf in den Digest laufen, nicht still den
    Anbieter wechseln - sonst stuende ein anderes Modell im Bericht als
    konfiguriert."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-nvidia")
    assert _aktives_backend({**BASIS, "llm_provider": "anthropic"}) == "none"
