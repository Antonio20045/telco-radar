"""Phase Bewerten ohne LLM: Roh-Digest, Erster Lauf und Abbruch ohne Redaktion."""

from __future__ import annotations

from pathlib import Path

import pytest

from telco_radar.analyze.bewertung import bewerten
from telco_radar.analyze.takt import Takt
from telco_radar.config import load_config
from telco_radar.models import Item

WURZEL = Path(__file__).resolve().parents[1]


def _item(n: int) -> Item:
    return Item(
        title=f"Meldung {n}",
        url=f"https://example.com/{n}",
        source_name="Fachpresse",
        summary="x" * 300,
    )


def _bewerten(
    neu: list[Item], first_run: bool, llm_modus: tuple[bool, bool], pflicht=False
):
    cfg = load_config(WURZEL)
    cfg.settings["publish_requires_editorial_briefing"] = pflicht
    phasen: list[tuple[str, float, str]] = []
    bewertung = bewerten(
        cfg,
        {"de": neu},
        (neu, first_run),
        llm_modus,
        ("analyst", "editor", "ausweich"),
        "Deutsch",
        list,
        Takt(lambda: 0.0, lambda *p: phasen.append(p), lambda aufgabe, _: aufgabe()),
    )
    return bewertung, phasen


def test_ohne_llm_wird_jede_meldung_unbewertet_gelistet():
    bewertung, phasen = _bewerten([_item(1), _item(2)], False, (False, True))

    highlights = [h for r in bewertung.regional.values() for h in r["highlights"]]
    assert [h["url"] for h in highlights] == [
        "https://example.com/1",
        "https://example.com/2",
    ]
    assert {h["category"] for h in highlights} == {"Unbewertet"}
    assert {h["relevance"] for h in highlights} == {None}
    assert {len(h["summary"]) for h in highlights} == {220}
    assert bewertung.editor_used is False
    assert "Erster Lauf" not in bewertung.body
    assert phasen == [("Bewerten & Schreiben", 0.0, "ohne KI (Roh-Digest)")]


def test_erster_lauf_steht_ueber_dem_roh_digest():
    bewertung, _ = _bewerten([_item(1)], True, (False, True))

    assert bewertung.body.startswith("> **Erster Lauf (Baseline):**")


def test_ohne_modell_mit_redaktionspflicht_bricht_der_lauf_ab():
    with pytest.raises(RuntimeError, match="No editorial model"):
        _bewerten([_item(1)], False, (False, False), pflicht=True)


def test_ohne_modell_ohne_redaktionspflicht_kommt_der_roh_digest():
    bewertung, _ = _bewerten([_item(1)], False, (False, False))

    assert bewertung.regional
    assert bewertung.editor_used is False
