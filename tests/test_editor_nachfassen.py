"""Der Editor bekommt einen zweiten Versuch, bevor der Wochenbericht faellt.

Im Lauf #63 (04.08.2026) hatte Sonnet 5 den Bericht geschrieben - Inhalt war
da, nur die Gliederung stimmte nicht. Ergebnis war trotzdem der Roh-Digest auf
der Startseite. Das ist die teuerste moegliche Reaktion auf einen Formfehler.
"""
from __future__ import annotations

import pytest

from telco_radar.analyze import editor


GUELTIG = """## Auf einen Blick
- Punkt eins

## Das Wichtigste
Vier Saetze zur Lage.

## Die wichtigsten Signale
**Telekom - Titel** (Netz, Dringlichkeit 4/5)
Detail. [Quelle](https://example.com/a)

## Muster der Woche
Ein Muster.
"""

REGIONAL = {"Europa": {"highlights": [{"title": "x"}]}}


def _antworten(monkeypatch, folge: list[str]) -> list[str]:
    """Gibt die Antworten der Reihe nach zurueck; sammelt die System-Prompts."""
    gesehen: list[str] = []

    def fake_complete(system, user, model, max_tokens=5000):
        gesehen.append(system)
        return folge[len(gesehen) - 1]

    monkeypatch.setattr(editor, "complete", fake_complete)
    return gesehen


def test_erster_versuch_reicht_wenn_die_gliederung_stimmt(monkeypatch):
    gesehen = _antworten(monkeypatch, [GUELTIG])
    markdown, _ = editor.synthesize(REGIONAL, [], model="m")
    assert markdown.startswith("## Auf einen Blick")
    assert len(gesehen) == 1, "es wurde unnoetig nachgefasst"


def test_falsche_gliederung_loest_genau_einen_korrekturversuch_aus(monkeypatch):
    gesehen = _antworten(monkeypatch, ["## Wochenrueckblick\nfalsch", GUELTIG])
    markdown, _ = editor.synthesize(REGIONAL, [], model="m")
    assert markdown.startswith("## Auf einen Blick")
    assert len(gesehen) == 2
    assert "WICHTIG" in gesehen[1], "der zweite Versuch bekam keinen Hinweis"
    assert "WICHTIG" not in gesehen[0], "der erste Versuch war schon veraendert"


def test_zweimal_falsch_faellt_weiterhin_auf_den_digest(monkeypatch):
    """Der Schutz gegen einen Roh-Digest auf der Startseite bleibt bestehen."""
    _antworten(monkeypatch, ["## Falsch\na", "## Immer noch falsch\nb"])
    with pytest.raises(editor.EditorialBriefingError):
        editor.synthesize(REGIONAL, [], model="m")


def test_codeblock_um_den_bericht_wird_entfernt(monkeypatch):
    _antworten(monkeypatch, ["```markdown\n" + GUELTIG + "```"])
    markdown, _ = editor.synthesize(REGIONAL, [], model="m")
    assert markdown.startswith("## Auf einen Blick")


def test_fehlermeldung_nennt_die_tatsaechliche_ausgabe():
    """Ohne das bleibt im Protokoll nur 'passt nicht' - nicht diagnostizierbar."""
    with pytest.raises(editor.EditorialBriefingError) as exc:
        editor.validate_editorial_briefing("## Zusammenfassung\nText hier.")
    text = str(exc.value)
    assert "## zusammenfassung" in text, "die gefundene Ueberschrift fehlt"
    assert "Zusammenfassung" in text and "Text hier" in text, "der Anfang fehlt"


def test_themenliste_passt_in_das_token_budget():
    """147 Themen brauchen mehr als die alten 5000 Token."""
    assert editor.EDITOR_MAX_TOKENS >= 8000
