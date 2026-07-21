"""Tests for the weekly differentiation lens (report/differentiation.py)."""
from telco_radar.report.differentiation import build_differentiation, DIFF_THEMES


def _hl(**kw):
    base = {"title": "", "summary": "", "category": "Produktlaunch",
            "operator": "X", "url": "http://example.com/a", "relevance": 3,
            "why_it_matters": "", "region": "Global", "source": "src"}
    base.update(kw)
    return base


def test_price_moves_excluded():
    r = build_differentiation([_hl(title="Operator cuts tariff price",
                                   category="Tarif/Pricing")])
    assert r["total"] == 0


def test_network_ai_infra_excluded():
    r = build_differentiation([_hl(title="Nokia and NVIDIA launch AI-RAN pilot",
                                   summary="double spectrum capacity",
                                   category="Netz/Technologie")])
    assert r["total"] == 0


def test_warranty_classified_as_garantie():
    r = build_differentiation([_hl(title="Operator launches 5-year warranty and price lock",
                                   summary="Garantie und Preisgarantie fuer Kunden",
                                   category="Produktlaunch", relevance=5)])
    assert r["total"] == 1 and r["active"][0]["key"] == "garantie"


def test_trade_in_classified_as_geraete():
    r = build_differentiation([_hl(title="Carrier expands trade-in and annual upgrade program",
                                   summary="Inzahlungnahme und jaehrliches Upgrade",
                                   category="Produktlaunch", relevance=4)])
    assert r["total"] == 1 and r["active"][0]["key"] == "geraete"


def test_consumer_ai_bundle_kept():
    r = build_differentiation([_hl(title="Telekom AI Phone bundles free Perplexity Pro",
                                   summary="assistant for customers", relevance=5)])
    assert r["total"] == 1 and r["active"][0]["key"] == "ki"


def test_quiet_themes_always_present():
    r = build_differentiation([])
    assert r["total"] == 0
    assert len(r["quiet"]) == len(DIFF_THEMES)


def test_dedup_same_url():
    hl = _hl(title="M-Pesa launches new wallet feature", category="Partnerschaft")
    r = build_differentiation([hl, dict(hl)])
    assert r["total"] == 1
