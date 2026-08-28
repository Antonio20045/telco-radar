"""llm_provider: der Anbieter wird konfiguriert, nicht aus Zufall gewaehlt.

Unter "auto" gewinnt der zuerst gefundene Schluessel. Solange der NVIDIA-
Schluessel im Repo liegt, kaeme Anthropic damit nie zum Zug - deshalb muss ein
Anbieterwechsel eine Konfigurationszeile sein und kein Loeschen von Secrets.
"""
from __future__ import annotations

import pytest

from telco_radar.analyze import llm


ALLE_SCHLUESSEL = ("AWS_BEARER_TOKEN_BEDROCK", "LLM_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture(autouse=True)
def _keine_basis_url_von_vorher(monkeypatch):
    """LLM_API_BASE setzt die Anbieterwahl DIREKT in os.environ.

    monkeypatch raeumt nur auf, was es selbst kennt - ohne dieses delenv
    schleppt ein Test die URL des vorherigen mit und besteht dann aus dem
    falschen Grund.
    """
    monkeypatch.delenv("LLM_API_BASE", raising=False)


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


BASIS = {"llm_api_base": "https://nvidia.invalid/v1",
         "deepseek_api_base": "https://deepseek.invalid"}


def test_anthropic_gewinnt_trotz_gesetztem_nvidia_schluessel(umgebung):
    assert _aktives_backend({**BASIS, "llm_provider": "anthropic"}) == "anthropic"


def test_openai_erzwingbar_obwohl_bedrock_token_da_ist(umgebung):
    assert _aktives_backend({**BASIS, "llm_provider": "openai"}).startswith("openai")


def test_deepseek_benutzt_seine_eigene_basis_url(umgebung):
    """deepseek und openai teilen LLM_API_KEY - nur die URL unterscheidet sie.
    Waere sie falsch, ginge der DeepSeek-Schluessel an NVIDIA."""
    assert "deepseek.invalid" in _aktives_backend({**BASIS,
                                                   "llm_provider": "deepseek"})


def test_wechsel_ueberschreibt_eine_alte_basis_url(umgebung, monkeypatch):
    """Ohne Ueberschreiben bliebe beim Wechsel die alte URL stehen."""
    monkeypatch.setenv("LLM_API_BASE", "https://nvidia.invalid/v1")
    assert "deepseek.invalid" in _aktives_backend({**BASIS,
                                                   "llm_provider": "deepseek"})


def test_deepseek_ohne_basis_url_weicht_nicht_auf_nvidia_aus(umgebung):
    """Ein Tippfehler in der DeepSeek-URL darf den Lauf nicht an NVIDIA geben -
    dort liegt derselbe Schluessel und ein anderer Endpunkt.

    Bis zum 27.08.2026 verlangte dieser Test zusaetzlich, dass auch Anthropic
    ausfaellt (`backend == "none"`), mit der Begruendung, man zahle sonst
    still beim teuren Anbieter weiter. Diese Haelfte ist mit E2 bewusst
    aufgegeben: der Anthropic-Schluessel ist jetzt der Rettungsanker der
    Modellketten, und llm._dispatch routet je MODELL - nur eine `claude-*`-ID
    geht an die Anthropic-API. Eine DeepSeek-Modell-ID dort ist eine
    abgelehnte Anfrage, keine Rechnung. Der Preis der alten Fassung war
    dagegen bezifferbar: sieben Laeufe in Folge ohne Wochenbericht.
    """
    from telco_radar.pipeline import _waehle_anbieter

    _waehle_anbieter({"llm_api_base": "https://nvidia.invalid/v1",
                      "llm_provider": "deepseek"})
    assert not llm._use_openai(), "still auf den NVIDIA-Endpunkt ausgewichen"
    assert not llm._use_bedrock()


def test_deepseek_weicht_nicht_auf_anthropic_aus(umgebung):
    """Gewaehlt ist gewaehlt - auch wenn ein Anthropic-Schluessel bereitliegt.

    Je Test nur EIN Aufruf: die Wahl entfernt die Schluessel der Verlierer aus
    der Prozessumgebung, ein zweiter Aufruf saehe also eine halb abgeraeumte
    Umgebung. Ein Lauf waehlt genau einmal.
    """
    assert "deepseek.invalid" in _aktives_backend({**BASIS,
                                                   "llm_provider": "deepseek"})


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
