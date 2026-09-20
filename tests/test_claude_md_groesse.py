"""CLAUDE.md wird in jede Claude-Code-Sitzung und jeden Subagenten geladen.

Sie war auf 3.840 Zeilen / 279 KB (~70.000 Tokens) angewachsen, weil jede
Sitzung ihren Bericht dort anhing. Dieser Test hält sie klein.
"""
from pathlib import Path

CLAUDE_MD = Path(__file__).resolve().parents[1] / "CLAUDE.md"
MAX_ZEILEN = 200
MAX_BYTES = 20000

HINWEIS = (
    "CLAUDE.md ist zu groß ({ist}, erlaubt {soll}). Sie enthält nur dauerhaft "
    "gültige Regeln, Befehle und Pfade. Sitzungsberichte, Messungen mit Datum "
    "und Phasenstände gehören nach outputs/, Auftrags- und Strategietexte nach "
    "docs/ bzw. docs/archiv/. Die alte Fassung steht in der Git-Historie. "
    "Wer etwas ergänzt, entfernt etwas Veraltetes."
)


def test_claude_md_hat_hoechstens_200_zeilen():
    zeilen = len(CLAUDE_MD.read_text(encoding="utf-8").splitlines())
    assert zeilen <= MAX_ZEILEN, HINWEIS.format(
        ist=f"{zeilen} Zeilen", soll=f"{MAX_ZEILEN} Zeilen")


def test_claude_md_hat_hoechstens_20000_bytes():
    groesse = CLAUDE_MD.stat().st_size
    assert groesse <= MAX_BYTES, HINWEIS.format(
        ist=f"{groesse} Bytes", soll=f"{MAX_BYTES} Bytes")
