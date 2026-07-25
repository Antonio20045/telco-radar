"""Tests fuer die Promo-Redaktion (analyze/promo_editor.py) - Validierung und
regelbasierten Fallback, ohne LLM."""
import pytest

from telco_radar.analyze.promo_editor import (
    PromoBriefingError, build_digest, validate_briefing,
)


def _entry(brand="congstar", headline="10 GB Bonus", status="aktiv",
          url="https://example.test/aktion", valid_until=None):
    return {"brand": brand, "headline": headline, "description": "Testbeschreibung.",
            "valid_until": valid_until, "url": url, "status": status,
            "first_seen": "2026-07-20", "last_verified": "2026-07-25"}


def test_build_digest_without_entries_is_still_valid_markdown():
    md = build_digest([])
    assert "## Was diese Woche auffaellt" in md
    assert "## Quellenbasis" in md


def test_build_digest_includes_source_link():
    md = build_digest([_entry()])
    assert "https://example.test/aktion" in md
    assert "congstar" in md.lower()


def test_build_digest_skips_stale_entries():
    md = build_digest([_entry(status="evtl. ausgelaufen")])
    assert "example.test" not in md


def test_validate_briefing_requires_both_headings():
    with pytest.raises(PromoBriefingError):
        validate_briefing("## Was diese Woche auffaellt\nText ohne Link.")


def test_validate_briefing_requires_source_link():
    with pytest.raises(PromoBriefingError):
        validate_briefing(
            "## Was diese Woche auffaellt\nText.\n\n## Quellenbasis\nKein Link.")


def test_validate_briefing_rejects_vodafone_advice():
    md = ("## Was diese Woche auffaellt\nVodafone sollte reagieren. "
          "[X](https://a.test)\n\n## Quellenbasis\n- [X](https://a.test)")
    with pytest.raises(PromoBriefingError):
        validate_briefing(md)


def test_validate_briefing_accepts_well_formed_markdown():
    md = ("## Was diese Woche auffaellt\nMehrere Discounter senken den Einstiegspreis. "
          "[congstar – 10 GB Bonus](https://example.test/aktion)\n\n"
          "## Quellenbasis\n- [congstar – 10 GB Bonus](https://example.test/aktion)")
    validate_briefing(md)  # must not raise
