from pathlib import Path

from telco_radar.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def test_news_sources_have_a_group():
    cfg = load_config(ROOT)
    groups = {s.group for s in cfg.news_sources}
    assert groups <= {"telco", "tech"}
    assert any(s.group == "telco" for s in cfg.news_sources)
    assert any(s.group == "tech" for s in cfg.news_sources)


def test_operator_sources_default_to_telco_group():
    cfg = load_config(ROOT)
    for op in cfg.operators:
        for src in op.sources:
            assert src.group == "telco"
