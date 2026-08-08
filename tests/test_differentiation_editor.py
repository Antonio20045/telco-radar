"""Offline tests for the dedicated differentiation report editor."""

from telco_radar.analyze.differentiation_editor import (
    build_digest,
    validate_briefing,
)


def _entry(theme="ki", operator="Telekom"):
    return {
        "theme": theme,
        "operator": operator,
        "region": "Europa",
        "what": "bietet Kunden einen Premium-Assistenten als Vorteil",
        "why": "Ein gebündelter Dienst schafft einen Grund zur Bindung",
        "url": "https://example.com/move",
        "source": "example.com",
        "date": "2026-07-21",
        "first_seen": "2026-07-21",
        "last_verified": "2026-07-21",
    }


def test_fallback_is_a_report_with_source_links():
    """Der Notfall-Digest schreibt DIESELBE Gliederung wie die KI-Redaktion.

    Faellt der Redakteur aus, aendert sich der Ton der Seite, nicht ihr
    Aufbau - `report/differenzierung_bericht.py` zerlegt beide gleich.
    """
    report = build_digest([_entry()], {"ki": "KI & Assistenten"})
    validate_briefing(report)
    assert "## Das Bild" in report
    assert "## Muster" in report
    assert "## Einordnung" in report
    # Die alte Gliederung ist weg: "Konkrete Entwicklungen" war die
    # Aufzaehlung, die auf der Seite schon als Karten steht, und
    # "Quellenbasis" fuehrte dieselben Quellen ein drittes Mal auf.
    assert "## Konkrete Entwicklungen" not in report
    assert "## Quellenbasis" not in report
    assert "[Telekom – example.com](https://example.com/move)" in report
    assert "Empfehlung" not in report
    assert "Für Vodafone" not in report


def test_die_einordnung_traegt_nur_hebel_mit_mehr_als_einem_beispiel():
    """Ein Hebel mit genau einem Beispiel bekommt keinen Einordnungssatz -
    er wuerde die Karte darunter bloss wiederholen."""
    labels = {"ki": "KI & Assistenten", "gaming": "Gaming"}
    report = build_digest(
        [_entry(), _entry(operator="O2"), _entry(theme="gaming")], labels)
    assert "### KI & Assistenten" in report
    assert "### Gaming" not in report


def test_ein_absatz_in_aufzaehlungslaenge_wird_abgelehnt():
    """Der wahrscheinlichste Rueckfall: das Modell haengt wieder alle
    Beispiele mit Semikolon in einen Absatz. Gemessen am Bericht vom
    07.08.2026 waren das 2100 Zeichen in EINEM Absatz."""
    wand = "## Das Bild\n\n" + ("Ein Betreiber bietet etwas an; " * 60) \
        + "[Q](https://example.com/x).\n\n## Muster\n\nText.\n\n## Einordnung\n"
    try:
        validate_briefing(wand)
    except Exception as exc:  # noqa: BLE001
        assert "Aufzaehlung" in str(exc)
    else:
        raise AssertionError("die Absatzwand wurde angenommen")


def test_ein_bericht_ohne_belegte_beispiele_bleibt_gueltig():
    """Eine leere Bibliothek darf keinen Fehler werfen - die Seite steht
    dann mit dem gerechneten Marktbild."""
    validate_briefing.__doc__  # noqa: B018 - nur Dokumentationsbezug
    report = build_digest([], {})
    assert "## Das Bild" in report and "## Einordnung" in report


def test_validation_rejects_missing_section():
    try:
        validate_briefing("## Auf einen Blick\n\n- test")
    except Exception as exc:  # noqa: BLE001
        assert "unvollstaendig" in str(exc)
    else:
        raise AssertionError("incomplete briefing was accepted")


def test_validation_rejects_vodafone_advice():
    report = """## Das Bild
Text [Quelle](https://example.com/move).
## Muster
**Bündel** Zwei Anbieter tun dasselbe [Quelle](https://example.com/move).
## Einordnung
### KI & Assistenten
Für Vodafone: Das sollte Vodafone prüfen.
"""
    try:
        validate_briefing(report)
    except Exception as exc:  # noqa: BLE001
        assert "Vodafone-Empfehlung" in str(exc)
    else:
        raise AssertionError("Vodafone advice was accepted")
