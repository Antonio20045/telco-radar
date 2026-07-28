"""Tests fuer den Wichtigkeits-Score der Promo-Uebersicht.

Schwerpunkt liegt bewusst auf den Eigenschaften, die den Score ueber die Zeit
brauchbar machen: feste (nicht relative) Skala, eingefrorene LLM-Achsen,
Hysterese an der Highlight-Schwelle und ein hartes Belegerfordernis fuer die
beiden vom Modell bewerteten Achsen.
"""
from types import SimpleNamespace

import pytest

from telco_radar.analyze import promo_ranker as pr


def _src(name, tier=2, reach=None):
    return SimpleNamespace(name=name, tier=tier, reach=reach)


def _entry(eid, brand="Marke", headline="Titel", description="Beschreibung",
           status="aktiv", **extra):
    e = {"id": eid, "brand": brand, "headline": headline,
         "description": description, "status": status}
    e.update(extra)
    return e


# --------------------------------------------------------------- Achse C

def test_reach_axis_uses_explicit_config_value():
    assert pr.reach_axis(_src("ALDI TALK", tier=2, reach=2)) == 2
    assert pr.reach_axis(_src("simplytel", tier=2, reach=1)) == 1


def test_reach_axis_falls_back_to_tier_when_field_missing():
    assert pr.reach_axis(_src("Telekom", tier=1)) == 3
    assert pr.reach_axis(_src("Irgendwer", tier=2)) == 2


def test_reach_axis_unknown_brand_scores_zero_instead_of_guessing():
    assert pr.reach_axis(None) == 0


def test_reach_axis_clamps_out_of_range_config():
    assert pr.reach_axis(_src("X", reach=9)) == 3
    assert pr.reach_axis(_src("X", reach=-4)) == 0


# --------------------------------------------------------------- Achse D

def test_momentum_counts_other_brands_not_own():
    entries = [
        _entry("1", brand="A", mechanic="wechselpraemie"),
        _entry("2", brand="A", mechanic="wechselpraemie"),
        _entry("3", brand="B", mechanic="wechselpraemie"),
    ]
    index = pr.mechanic_brand_index(entries)
    # A sieht nur B, nicht sich selbst - zwei eigene Angebote derselben
    # Mechanik duerfen die eigene Marktbreite nicht aufblasen.
    assert pr.momentum_axis("wechselpraemie", "A", index) == 1


def test_momentum_scales_with_number_of_other_brands():
    def index_with(n):
        return {"datenbonus": {f"M{i}" for i in range(n)} | {"Eigen"}}
    assert pr.momentum_axis("datenbonus", "Eigen", index_with(0)) == 0
    assert pr.momentum_axis("datenbonus", "Eigen", index_with(1)) == 1
    assert pr.momentum_axis("datenbonus", "Eigen", index_with(3)) == 2
    assert pr.momentum_axis("datenbonus", "Eigen", index_with(4)) == 3


def test_momentum_ignores_catchall_mechanic():
    index = pr.mechanic_brand_index([
        _entry("1", brand="A", mechanic="sonstiges"),
        _entry("2", brand="B", mechanic="sonstiges"),
    ])
    assert index == {}
    assert pr.momentum_axis("sonstiges", "A", index) == 0
    assert pr.momentum_axis(None, "A", index) == 0


def test_mechanic_index_skips_retired_entries():
    index = pr.mechanic_brand_index([
        _entry("1", brand="A", mechanic="zugabe"),
        _entry("2", brand="B", mechanic="zugabe", status="ausgelaufen"),
    ])
    assert index == {"zugabe": {"A"}}


# --------------------------------------------------------------- Achse E

@pytest.mark.parametrize("raw,expected", [
    (None, 0),
    ("", 0),
    ("Nur für kurze Zeit", 1),
    ("solange der Vorrat reicht", 1),
    ("31.12.2026", 2),
    ("gültig bis 2026-12-31", 2),
    ("05.08.2026", 3),
    ("2026-08-05", 3),
    ("01.01.2020", 0),
])
def test_campaign_axis(raw, expected):
    assert pr.campaign_axis(raw, "2026-07-27") == expected


def test_campaign_axis_survives_broken_today():
    assert pr.campaign_axis("31.12.2026", "keindatum") == 2


def test_parse_valid_until_rejects_impossible_dates():
    assert pr.parse_valid_until("32.13.2026") is None
    assert pr.parse_valid_until("kein Datum") is None


# ------------------------------------------------------------ Aggregation

def test_composite_is_absolute_not_relative():
    """Derselbe Achsensatz muss unabhaengig vom uebrigen Bestand immer
    dieselbe Zahl ergeben - genau das leistet eine relative Normalisierung
    (Min-Max/z-Score ueber den Wochenbestand) NICHT."""
    axes = {"lever": 2, "depth": 3, "reach": 3, "momentum": 2, "campaign": 2}
    assert pr.composite(axes) == pr.composite(axes) == 82


def test_composite_bounds():
    assert pr.composite({k: 0 for k in pr.DEFAULT_WEIGHTS}) == 0
    assert pr.composite({k: 3 for k in pr.DEFAULT_WEIGHTS}) == 100


def test_composite_treats_missing_and_bogus_axes_as_zero():
    assert pr.composite({"reach": 3}) == 20
    assert pr.composite({"reach": "kaputt", "lever": None, "depth": 3}) == 25


def test_composite_clamps_out_of_range_axis():
    assert pr.composite({"lever": 99}) == pr.composite({"lever": 3})


def test_normalise_weights_rescales_to_one():
    w = pr.normalise_weights({"lever": 3, "depth": 1, "reach": 1,
                              "momentum": 1, "campaign": 1})
    assert pytest.approx(sum(w.values())) == 1.0
    assert w["lever"] > w["depth"]


def test_normalise_weights_falls_back_on_unusable_config():
    assert pr.normalise_weights(None) == pr.DEFAULT_WEIGHTS
    assert pr.normalise_weights({"lever": "viel"}) == pr.DEFAULT_WEIGHTS
    assert pr.normalise_weights({k: 0 for k in pr.DEFAULT_WEIGHTS}) == pr.DEFAULT_WEIGHTS


# -------------------------------------------------------- Score-Caching

def test_needs_judgement_for_unscored_entry():
    assert pr.needs_judgement(_entry("1"), "modell-a") is True


def test_frozen_judgement_is_not_reevaluated():
    e = _entry("1")
    e["judged"] = {"basis": pr.score_basis(e), "model": "modell-a",
                   "rubric_version": pr.RUBRIC_VERSION}
    assert pr.needs_judgement(e, "modell-a") is False


def test_changed_offer_text_triggers_reevaluation():
    e = _entry("1")
    e["judged"] = {"basis": pr.score_basis(e), "model": "modell-a",
                   "rubric_version": pr.RUBRIC_VERSION}
    e["description"] = "jetzt mit 300 Euro Wechselprämie"
    assert pr.needs_judgement(e, "modell-a") is True


def test_new_rubric_version_or_model_triggers_reevaluation():
    e = _entry("1")
    e["judged"] = {"basis": pr.score_basis(e), "model": "modell-a",
                   "rubric_version": pr.RUBRIC_VERSION - 1}
    assert pr.needs_judgement(e, "modell-a") is True
    e["judged"]["rubric_version"] = pr.RUBRIC_VERSION
    assert pr.needs_judgement(e, "modell-b") is True


def test_score_basis_ignores_whitespace_but_not_wording():
    a = _entry("1", headline="Wechselprämie  300 €")
    b = _entry("1", headline="Wechselprämie 300 €")
    c = _entry("1", headline="Wechselprämie 200 €")
    assert pr.score_basis(a) == pr.score_basis(b)
    assert pr.score_basis(a) != pr.score_basis(c)


# ----------------------------------------------------------- Hysterese

def test_hysteresis_enters_above_threshold():
    assert pr.apply_hysteresis({}, 70, 68, 60) is True


def test_hysteresis_keeps_existing_highlight_inside_the_band():
    assert pr.apply_hysteresis({"highlight": True}, 63, 68, 60) is True
    assert pr.apply_hysteresis({"highlight": False}, 63, 68, 60) is False


def test_hysteresis_drops_below_exit_threshold():
    assert pr.apply_hysteresis({"highlight": True}, 59, 68, 60) is False


def test_retired_offer_is_never_a_highlight():
    assert pr.apply_hysteresis({"highlight": True, "status": "ausgelaufen"},
                               99, 68, 60) is False


# ------------------------------------------------- LLM-Achsen (judge_offers)

class _FakeComplete:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, system, user, model, max_tokens=0):
        self.calls.append({"system": system, "user": user, "model": model})
        return self.payload


def _patch_complete(monkeypatch, payload):
    fake = _FakeComplete(payload)
    monkeypatch.setattr(pr, "complete", fake)
    return fake


def test_judge_offers_accepts_a_supported_verdict(monkeypatch):
    entry = _entry("abc", headline="300 € Wechselprämie",
                   description="Wer wechselt, bekommt 300 Euro Prämie.")
    _patch_complete(monkeypatch, '[{"id":"abc","evidence":"bekommt 300 Euro Prämie",'
                                 '"reason":"Direkter Wechselanreiz.","lever":3,'
                                 '"depth":3,"mechanic":"wechselpraemie"}]')
    out = pr.judge_offers("Marke", [entry], "modell-a")
    assert out["abc"]["lever"] == 3
    assert out["abc"]["depth"] == 3
    assert out["abc"]["mechanic"] == "wechselpraemie"
    assert out["abc"]["evidence_ok"] is True
    assert out["abc"]["basis"] == pr.score_basis(entry)


def test_unsupported_evidence_caps_the_llm_axes(monkeypatch):
    """Ein frei erfundenes Zitat darf keine hohe Stufe tragen. Der Eintrag
    wird nicht verworfen - er wird gedeckelt."""
    entry = _entry("abc", headline="Sommeraktion",
                   description="Ein Angebot für den Sommer.")
    _patch_complete(monkeypatch, '[{"id":"abc","evidence":"500 Euro Prämie für alle",'
                                 '"reason":"x","lever":3,"depth":3,'
                                 '"mechanic":"wechselpraemie"}]')
    out = pr.judge_offers("Marke", [entry], "modell-a")
    assert out["abc"]["lever"] == 1
    assert out["abc"]["depth"] == 1
    assert out["abc"]["evidence_ok"] is False
    assert out["abc"]["evidence"] == ""


def test_missing_evidence_also_caps(monkeypatch):
    entry = _entry("abc")
    _patch_complete(monkeypatch, '[{"id":"abc","evidence":"","reason":"x",'
                                 '"lever":3,"depth":2,"mechanic":"zugabe"}]')
    out = pr.judge_offers("Marke", [entry], "modell-a")
    assert (out["abc"]["lever"], out["abc"]["depth"]) == (1, 1)


def test_unknown_mechanic_falls_back_to_catchall(monkeypatch):
    entry = _entry("abc", description="Ein sehr konkretes Angebot hier.")
    _patch_complete(monkeypatch, '[{"id":"abc","evidence":"sehr konkretes Angebot",'
                                 '"reason":"x","lever":2,"depth":2,'
                                 '"mechanic":"quatschkategorie"}]')
    out = pr.judge_offers("Marke", [entry], "modell-a")
    assert out["abc"]["mechanic"] == "sonstiges"


def test_verdicts_for_unknown_ids_are_ignored(monkeypatch):
    """Das Modell darf keine Bewertung fuer ein Angebot unterschieben, das
    ihm gar nicht vorgelegt wurde."""
    entry = _entry("abc", description="Ein sehr konkretes Angebot hier.")
    _patch_complete(monkeypatch, '[{"id":"fremd","evidence":"sehr konkretes Angebot",'
                                 '"reason":"x","lever":3,"depth":3,"mechanic":"zugabe"}]')
    assert pr.judge_offers("Marke", [entry], "modell-a") == {}


def test_judge_offers_survives_a_broken_model_answer(monkeypatch):
    _patch_complete(monkeypatch, "das ist gar kein JSON")
    assert pr.judge_offers("Marke", [_entry("abc")], "modell-a") == {}


def test_judge_offers_survives_a_provider_error(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("503 ResourceExhausted")
    monkeypatch.setattr(pr, "complete", boom)
    assert pr.judge_offers("Marke", [_entry("abc")], "modell-a") == {}


def test_judge_offers_without_entries_makes_no_call(monkeypatch):
    fake = _patch_complete(monkeypatch, "[]")
    assert pr.judge_offers("Marke", [], "modell-a") == {}
    assert fake.calls == []


# ------------------------------------------------------------- score_all

def test_score_all_without_llm_leaves_entries_unscored():
    """Ohne LLM-Achsen waere ein Score nicht mit bewerteten Angeboten
    vergleichbar - dann lieber ehrlich None als eine zu niedrige Zahl."""
    entries = [_entry("1", brand="Telekom")]
    summary = pr.score_all(entries, [_src("Telekom", tier=1)], "2026-07-27",
                           model="m", use_llm=False)
    assert entries[0]["score"] is None
    assert entries[0]["highlight"] is False
    assert summary["scored"] == 0


def test_score_all_scores_and_highlights(monkeypatch):
    entry = _entry("abc", brand="Telekom",
                   headline="300 € Wechselprämie",
                   description="Wer zu uns wechselt, bekommt 300 Euro Prämie.",
                   valid_until="05.08.2026")
    _patch_complete(monkeypatch, '[{"id":"abc","evidence":"bekommt 300 Euro Prämie",'
                                 '"reason":"Greift die Wechselhürde direkt an.",'
                                 '"lever":3,"depth":3,"mechanic":"wechselpraemie"}]')
    summary = pr.score_all([entry], [_src("Telekom", tier=1, reach=3)],
                           "2026-07-27", model="m", use_llm=True)
    # lever 3, depth 3, reach 3, momentum 0 (allein), campaign 3
    assert entry["score"] == pr.composite(
        {"lever": 3, "depth": 3, "reach": 3, "momentum": 0, "campaign": 3})
    assert entry["highlight"] is True
    assert entry["score_reason"] == "Greift die Wechselhürde direkt an."
    assert entry["scored_at"] == "2026-07-27"
    assert summary["judged_new"] == 1 and summary["highlights"] == 1


def test_score_all_reuses_frozen_judgement_without_calling_the_model(monkeypatch):
    entry = _entry("abc", brand="Telekom", description="Ein Angebot mit Prämie.")
    entry["judged"] = {"basis": pr.score_basis(entry), "model": "m",
                       "rubric_version": pr.RUBRIC_VERSION,
                       "lever": 2, "depth": 2, "mechanic": "geraetesubvention",
                       "reason": "eingefroren"}
    fake = _patch_complete(monkeypatch, "[]")
    pr.score_all([entry], [_src("Telekom", tier=1)], "2026-07-27",
                 model="m", use_llm=True)
    assert fake.calls == []
    assert entry["score"] is not None
    assert entry["score_reason"] == "eingefroren"


def test_deterministic_axes_are_recomputed_even_for_frozen_entries(monkeypatch):
    """Ein eingefrorenes Urteil heisst nicht eingefrorener Score: rueckt das
    Enddatum naeher, muss die Zahl mitgehen - ohne LLM-Aufruf."""
    entry = _entry("abc", brand="Telekom", description="Ein Angebot mit Prämie.",
                   valid_until="05.08.2026")
    entry["judged"] = {"basis": pr.score_basis(entry), "model": "m",
                       "rubric_version": pr.RUBRIC_VERSION,
                       "lever": 2, "depth": 2, "mechanic": "geraetesubvention"}
    _patch_complete(monkeypatch, "[]")
    pr.score_all([entry], [_src("Telekom", tier=1)], "2026-07-01",
                 model="m", use_llm=True)
    far = entry["score"]
    pr.score_all([entry], [_src("Telekom", tier=1)], "2026-07-27",
                 model="m", use_llm=True)
    assert entry["score"] > far


def test_score_all_uses_configured_weights_and_thresholds(monkeypatch):
    entry = _entry("abc", brand="simplytel", description="Ein Angebot mit Prämie.")
    entry["judged"] = {"basis": pr.score_basis(entry), "model": "m",
                       "rubric_version": pr.RUBRIC_VERSION,
                       "lever": 3, "depth": 3, "mechanic": "wechselpraemie"}
    _patch_complete(monkeypatch, "[]")
    settings = {"promo_score": {
        "weights": {"lever": 1, "depth": 1, "reach": 0, "momentum": 0, "campaign": 0},
        "highlight_enter": 90, "highlight_exit": 80}}
    summary = pr.score_all([entry], [_src("simplytel", reach=1)], "2026-07-27",
                           model="m", use_llm=True, settings=settings)
    assert entry["score"] == 100          # reach/momentum/campaign ausgeblendet
    assert entry["highlight"] is True
    assert (summary["enter"], summary["exit"]) == (90, 80)


def test_score_all_ignores_an_exit_threshold_above_enter(monkeypatch):
    _patch_complete(monkeypatch, "[]")
    summary = pr.score_all([], [], "2026-07-27", model="m", use_llm=False,
                           settings={"promo_score": {"highlight_enter": 60,
                                                     "highlight_exit": 90}})
    assert summary["exit"] == summary["enter"] == 60


def test_score_all_clears_highlight_on_retired_entries(monkeypatch):
    entry = _entry("abc", brand="Telekom", status="ausgelaufen", highlight=True)
    _patch_complete(monkeypatch, "[]")
    pr.score_all([entry], [_src("Telekom", tier=1)], "2026-07-27",
                 model="m", use_llm=True)
    assert entry["highlight"] is False


def test_score_all_survives_a_failing_judgement(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("503")
    monkeypatch.setattr(pr, "complete", boom)
    entry = _entry("abc", brand="Telekom")
    summary = pr.score_all([entry], [_src("Telekom", tier=1)], "2026-07-27",
                           model="m", use_llm=True)
    assert entry["score"] is None
    assert summary["judged_failed"] == 1


def test_score_all_skips_brands_that_are_no_longer_configured(monkeypatch):
    """Die DB haelt Eintraege entfernter Quellen als totes Datum weiter vor.
    Die sind auf der Seite unsichtbar und duerfen keinen LLM-Aufruf kosten."""
    fake = _patch_complete(monkeypatch, "[]")
    entries = [_entry("1", brand="PŸUR"), _entry("2", brand="Telekom")]
    pr.score_all(entries, [_src("Telekom", tier=1)], "2026-07-27",
                 model="m", use_llm=True)
    assert [c["system"].splitlines()[1] for c in fake.calls] == [
        "einzelne laufende Angebote von Telekom (deutscher Mobilfunkmarkt) sind."]
    assert "score" not in entries[0]
