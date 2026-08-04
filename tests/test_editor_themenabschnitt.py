"""Die Themen-Klammer im Wochenbericht.

Mit den Themenfeldern (config/tech_sources.yaml) kommen Meldungen von
Zulieferern, Geraeteherstellern und Regulierern in den Bericht. Ohne eigenen
Abschnitt stehen sie zwischen den Betreibermeldungen, gehen dort unter und
machen den Bericht zur Linkliste - genau das, was der Ausbau-Auftrag
verhindern will.

Seit der zweistufigen Redaktion setzt der Code die Klammer: eine gemeinsame
H2-Ueberschrift, darunter je Themenfeld ein H3-Abschnitt seines Redakteurs.
Die Klammer ist bedingt - ein Lauf ohne Themenmeldungen darf keine
Ueberschrift verlangen, zu der es nichts zu schreiben gibt. Aufbau UND
Pflichtpruefung haengen deshalb am selben Schalter.
"""
from __future__ import annotations

import json

import pytest

from telco_radar.analyze import editor

BASIS = """## Auf einen Blick
- Punkt eins

## Das Wichtigste
Vier Saetze zur Lage.

## Die wichtigsten Signale
**Telekom - Titel** (Netz, Dringlichkeit 4/5)
Detail. [Quelle](https://example.com/a)

## Muster der Woche
Ein Muster.
"""

MIT_THEMEN = BASIS.replace(
    "## Muster der Woche",
    "## Technologie, Geräte & Regulierung\nQualcomm liefert. "
    "[Quelle](https://example.com/b)\n\n## Muster der Woche")


def _regional(*bereiche: str) -> dict:
    return {
        b: {"region_summary": f"Lage in {b}.",
            "highlights": [{"title": f"Titel {b}", "operator": "Firma",
                            "url": f"https://example.com/{b}",
                            "relevance": 4, "summary": "Etwas passierte."}]}
        for b in bereiche
    }


def _stufen(monkeypatch, chef: str = BASIS) -> list[str]:
    """Beide Stufen bedienen; liefert die gesehenen System-Prompts."""
    gesehen: list[str] = []

    def fake_complete(system, user, model, max_tokens=5000):
        gesehen.append(system)
        if system.startswith("You are the section editor"):
            return ("===KURZFASSUNG===\nKurz.\n===ABSCHNITT===\n"
                    "Abschnittstext. [Quelle](https://example.com/x)\n")
        return chef

    monkeypatch.setattr(editor, "complete", fake_complete)
    return gesehen


def test_ohne_themen_bleibt_die_pflicht_unveraendert():
    editor.validate_editorial_briefing(BASIS)


def test_mit_themen_ist_der_abschnitt_pflicht():
    with pytest.raises(editor.EditorialBriefingError) as exc:
        editor.validate_editorial_briefing(
            BASIS, frozenset({editor.THEMEN_UEBERSCHRIFT}))
    assert "technologie" in str(exc.value).lower()

    # Mit Abschnitt geht derselbe Bericht durch.
    editor.validate_editorial_briefing(
        MIT_THEMEN, frozenset({editor.THEMEN_UEBERSCHRIFT}))


def test_klammer_erscheint_nur_bei_themen(monkeypatch):
    _stufen(monkeypatch)

    ohne, _ = editor.synthesize(_regional("Europa"), [], model="m")
    assert editor.THEMEN_TITEL not in ohne

    mit, _ = editor.synthesize(
        _regional("Europa", "KI-Anbieter", "Chips & Modems"), [], model="m",
        themenbereiche=["KI-Anbieter", "Chips & Modems"])
    assert f"## {editor.THEMEN_TITEL}" in mit
    # Die Themenfelder stehen als H3 UNTER der gemeinsamen Klammer, die
    # Region bleibt eine eigene H2.
    assert "### KI-Anbieter" in mit and "### Chips & Modems" in mit
    assert "## Europa" in mit and "### Europa" not in mit
    assert mit.index(f"## {editor.THEMEN_TITEL}") < mit.index("### KI-Anbieter")


def test_themenredakteur_bekommt_den_zulieferer_prompt(monkeypatch):
    """Ein Chiphersteller ist kein Wettbewerber - der Prompt muss das sagen."""
    gesehen = _stufen(monkeypatch)
    editor.synthesize(_regional("Europa", "KI-Anbieter"), [], model="m",
                      themenbereiche=["KI-Anbieter"])

    bereichs_prompts = [s for s in gesehen
                        if s.startswith("You are the section editor")]
    thema = next(s for s in bereichs_prompts if "KI-Anbieter" in s)
    region = next(s for s in bereichs_prompts if "Europa" in s)
    assert "NOT competing operators" in thema
    assert "NOT competing operators" not in region


def test_ohne_themenmeldungen_keine_leere_klammer(monkeypatch):
    """Ein Themenfeld ohne bewertete Meldung darf keine Ueberschrift erzwingen."""
    _stufen(monkeypatch)
    regional = _regional("Europa")
    regional["KI-Anbieter"] = {"region_summary": "", "highlights": []}

    bericht, _ = editor.synthesize(regional, [], model="m",
                                   themenbereiche=["KI-Anbieter"])

    assert editor.THEMEN_TITEL not in bericht
