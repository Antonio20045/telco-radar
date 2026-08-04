"""Der Themenabschnitt im Wochenbericht.

Mit den Themenfeldern (config/tech_sources.yaml) kommen Meldungen von
Zulieferern, Geraeteherstellern und Regulierern in den Bericht. Ohne eigenen
Abschnitt verteilt der Editor sie auf die Regionsabschnitte, wo sie zwischen
den Betreibermeldungen untergehen - der Bericht wird zur Linkliste, genau das,
was der Ausbau-Auftrag verhindern will.

Der Abschnitt ist deshalb bedingt: Prompt UND Pflichtpruefung haengen am
selben Schalter. Ein Lauf ohne Themenmeldungen darf keine Ueberschrift
verlangen, zu der es nichts zu schreiben gibt.
"""
from __future__ import annotations

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

REGIONAL = {"Europa": {"highlights": [{"title": "x"}]}}


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


def test_synthesize_setzt_abschnitt_nur_bei_themen(monkeypatch):
    gesehen: list[str] = []

    def fake_complete(system, user, model, max_tokens):
        gesehen.append(system)
        return MIT_THEMEN if "Technologie" in system else BASIS

    monkeypatch.setattr(editor, "complete", fake_complete)

    editor.synthesize(REGIONAL, [], model="m")
    assert "## Technologie, Geräte & Regulierung" not in gesehen[-1]

    editor.synthesize(REGIONAL, [], model="m",
                      themenbereiche=["KI-Anbieter", "Chips & Modems"])
    assert "## Technologie, Geräte & Regulierung" in gesehen[-1]
    # Die aktiven Themenfelder stehen namentlich im Prompt, damit der Editor
    # weiss, worueber er den Abschnitt schreibt.
    assert "KI-Anbieter" in gesehen[-1] and "Chips & Modems" in gesehen[-1]


def test_fehlender_themenabschnitt_loest_korrekturversuch_aus(monkeypatch):
    """Ein vergessener Abschnitt darf den Wochenbericht nicht kosten -
    dafuer gibt es den einen Nachfass-Versuch."""
    antworten = [BASIS, MIT_THEMEN]

    def fake_complete(system, user, model, max_tokens):
        return antworten.pop(0)

    monkeypatch.setattr(editor, "complete", fake_complete)
    markdown, _ = editor.synthesize(REGIONAL, [], model="m",
                                    themenbereiche=["KI-Anbieter"])

    assert "## Technologie, Geräte & Regulierung" in markdown
    assert not antworten  # beide Versuche wurden gebraucht
