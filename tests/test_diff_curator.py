"""Tests für den persistenten Differenzierungs-Kurator (analyze/diff_curator.py).

Offline, deterministisch (use_llm=False) – kein Netz/LLM nötig.
"""
from telco_radar.analyze.diff_curator import DiffStore, curate, MAX_PER_THEME


def _hl(**kw):
    base = {"title": "", "summary": "", "category": "Produktlaunch",
            "operator": "X", "url": "http://example.com/a", "relevance": 4,
            "why_it_matters": "", "region": "Global", "source": "src"}
    base.update(kw)
    return base


def test_store_add_and_dedup(tmp_path):
    store = DiffStore(tmp_path / "d.jsonl")
    hl = _hl(title="Telekom AI Phone bundles free Perplexity Pro",
             summary="assistant for customers", url="http://a.test/1")
    added = curate([hl, dict(hl)], store, "2026-07-20", use_llm=False)
    assert len(added) == 1                 # dieselbe URL nur einmal
    assert len(store) == 1
    assert store.entries()[0]["theme"] == "ki"
    assert store.entries()[0]["first_seen"] == "2026-07-20"


def test_price_and_infra_not_stored(tmp_path):
    store = DiffStore(tmp_path / "d.jsonl")
    added = curate([
        _hl(title="Operator cuts tariff price", category="Tarif/Pricing",
            url="http://a.test/price"),
        _hl(title="Nokia AI-RAN pilot doubles spectrum",
            category="Netz/Technologie", url="http://a.test/ran"),
    ], store, "2026-07-20", use_llm=False)
    assert added == [] and len(store) == 0


def test_relevance_threshold(tmp_path):
    store = DiffStore(tmp_path / "d.jsonl")
    weak = _hl(title="Carrier adds Netflix streaming bundle",
               summary="entertainment bundle", relevance=2, url="http://a.test/w")
    strong = _hl(title="Carrier adds Netflix streaming bundle",
                 summary="entertainment bundle", relevance=5, url="http://a.test/s")
    added = curate([weak, strong], store, "2026-07-20", use_llm=False)
    assert len(added) == 1 and store.entries()[0]["url"] == "http://a.test/s"


def test_unrated_items_kept(tmp_path):
    # --no-llm-Modus: relevance None -> trotzdem behalten, damit die Bibliothek
    # nie leer bleibt.
    store = DiffStore(tmp_path / "d.jsonl")
    hl = _hl(title="Operator gives free Spotify to customers",
             summary="music streaming perk", relevance=None, url="http://a.test/u")
    added = curate([hl], store, "2026-07-20", use_llm=False)
    assert len(added) == 1


def test_persistence_across_weeks(tmp_path):
    p = tmp_path / "d.jsonl"
    week1 = DiffStore(p)
    curate([_hl(title="Telekom bundles Perplexity Pro AI assistant",
                url="http://a.test/w1")], week1, "2026-07-13", use_llm=False)
    # Neue Woche, neue Store-Instanz aus derselben Datei:
    week2 = DiffStore(p)
    assert len(week2) == 1                       # alter Move ueberlebt
    added = curate([_hl(title="Free Le Chat Mistral AI for all customers",
                        url="http://a.test/w2")], week2, "2026-07-20", use_llm=False)
    assert len(added) == 1 and len(week2) == 2   # beide Wochen vorhanden
    assert len(DiffStore(p)) == 2                # dauerhaft geschrieben


def test_store_caps_per_theme(tmp_path):
    store = DiffStore(tmp_path / "d.jsonl")
    many = [_hl(title="Telekom AI assistant Perplexity bundle",
                summary="ki-assistent perk", relevance=4,
                url=f"http://a.test/{i}") for i in range(MAX_PER_THEME + 15)]
    curate(many, store, "2026-07-20", use_llm=False)
    assert len(store) == MAX_PER_THEME           # gedeckelt, waechst nicht endlos
