"""Tests fuer die Promo-Pipeline-Verklebung (promo_pipeline.py) - nur die
reinen, ohne Netz/LLM testbaren Bausteine. Der volle run_promo_stage()-Ablauf
(Fetch + LLM + Screenshots) wird bewusst nicht hier getestet, exakt wie
schon vor diesem Feature - siehe die anderen test_promo_*.py-Dateien, die
jeweils nur ihre eigene Schicht isoliert pruefen.
"""
from telco_radar.promo_pipeline import _resolve_item_url


def test_resolve_item_url_prefers_the_llm_selected_deep_link():
    assert _resolve_item_url("https://example.test/geraet-a",
                             "https://example.test/deals/") == "https://example.test/geraet-a"


def test_resolve_item_url_falls_back_to_brand_url_when_missing():
    assert _resolve_item_url(None, "https://example.test/deals/") == "https://example.test/deals/"
    assert _resolve_item_url("", "https://example.test/deals/") == "https://example.test/deals/"


def test_resolve_item_url_falls_back_to_brand_url_when_blank():
    assert _resolve_item_url("   ", "https://example.test/deals/") == "https://example.test/deals/"
