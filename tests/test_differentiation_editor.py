"""Offline tests for the dedicated differentiation report editor."""

from telco_radar.analyze.differentiation_editor import (
    build_digest,
    validate_briefing,
)


def _entry(theme="ki", operator="Telekom"):
    return {
        "theme": theme,
        "operator": operator,
        "region": "Europa",
        "what": "bietet Kunden einen Premium-Assistenten als Vorteil",
        "why": "Ein gebündelter Dienst schafft einen Grund zur Bindung",
        "url": "https://example.com/move",
        "source": "example.com",
        "date": "2026-07-21",
        "first_seen": "2026-07-21",
        "last_verified": "2026-07-21",
    }


def test_fallback_is_a_report_with_source_links():
    report = build_digest([_entry()], {"ki": "KI & Assistenten"})
    validate_briefing(report)
    assert "## Das Wichtigste" in report
    assert "## Wie sich Differenzierung aktuell zeigt" in report
    assert "### " not in report
    assert "[Telekom – example.com](https://example.com/move)" in report
    assert "Empfehlung" not in report
    assert "Für Vodafone" not in report


def test_validation_rejects_missing_section():
    try:
        validate_briefing("## Auf einen Blick\n\n- test")
    except Exception as exc:  # noqa: BLE001
        assert "unvollstaendig" in str(exc)
    else:
        raise AssertionError("incomplete briefing was accepted")


def test_validation_rejects_vodafone_advice():
    report = """## Das Wichtigste
Text.
## Wie sich Differenzierung aktuell zeigt
Text [Quelle](https://example.com/move).
## Welche Muster dahinter liegen
Text.
## Quellenbasis
[Quelle](https://example.com/move)
Für Vodafone: Das sollte Vodafone prüfen.
"""
    try:
        validate_briefing(report)
    except Exception as exc:  # noqa: BLE001
        assert "Vodafone-Empfehlung" in str(exc)
    else:
        raise AssertionError("Vodafone advice was accepted")
