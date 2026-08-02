"""Der Roh-Digest darf keine falsche Ursache behaupten.

Am 25.07.2026 stand auf der oeffentlichen Berichtsseite "ANTHROPIC_API_KEY ist
nicht gesetzt", obwohl der Key vorhanden war und nur der Provider nicht
antwortete.
"""
from __future__ import annotations

from datetime import datetime, timezone

from telco_radar.analyze.editor import build_digest
from telco_radar.models import Item

REGIONS = {"europa": "Europa"}


def _items():
    return {"europa": [Item(
        title="Testmeldung", url="https://example.com/a",
        source_name="Test", region="europa", operator="Vodafone",
        published=datetime(2026, 7, 25, tzinfo=timezone.utc), summary="Text")]}


def test_kein_key_konfiguriert_nennt_die_konfiguration(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    body, _ = build_digest(_items(), REGIONS)
    assert "kein Zugang zu einem Analyse-Modell konfiguriert" in body
    assert "ANTHROPIC_API_KEY" not in body


def test_key_vorhanden_nennt_den_provider_nicht_den_key(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid/v1")
    body, _ = build_digest(_items(), REGIONS)
    assert "nicht erreichbar" in body
    assert "ANTHROPIC_API_KEY" not in body
    assert "nicht gesetzt" not in body


def test_ohne_note_bleibt_die_erklaerung_dem_aufrufer(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    body, _ = build_digest(_items(), REGIONS, include_note=False)
    assert body.startswith("## Roh-Digest")
    assert "nicht erreichbar" not in body
    assert "Testmeldung" in body
