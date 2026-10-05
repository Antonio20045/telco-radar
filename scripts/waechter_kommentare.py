"""Welche ``#``-Kommentare Stufe 0 erlaubt: Werkzeugschalter und die Shebang-Zeile.

Das Löschwerkzeug ``tools/kommentare_loeschen.py`` und die Zählung ``kommentar`` in
``waechter_regeln.py`` teilen diese Definition.
"""

from __future__ import annotations

import io
import re
import tokenize

_SCHALTER = (
    r"(?i:noqa)(?::\s*[A-Z]+[0-9]+(?:[\s,]+[A-Z]+[0-9]+)*)?"
    r"|type:\s*ignore(?:\[[^\]]*\])?|pragma:\s*no cover"
    r"|(?:mypy|ruff|isort|fmt):\s*[\w-]+(?:\[[^\]]*\]|\s*=\s*[^#\s]+)?"
)
SCHALTER_VORN = re.compile(rf"#\s*(?:{_SCHALTER})")
_NUR_SCHALTER = re.compile(rf"#\s*(?:{_SCHALTER})(?:\s*#\s*(?:{_SCHALTER}))*\s*")
SHEBANG = "#!"


def ist_erlaubter_kommentar(kommentar: str, zeile: int) -> bool:
    """Wahr für reine Werkzeugschalter und die Shebang-Zeile; jeden anderen
    ``#``-Kommentar zählt Stufe 0 als ``kommentar``."""
    if zeile == 1 and kommentar.startswith(SHEBANG):
        return True
    return _NUR_SCHALTER.fullmatch(kommentar) is not None


def freie_kommentare(text: str) -> list[tuple[int, str]]:
    """Zeile und Text jedes ``#``-Kommentars, der kein erlaubter Kommentar ist."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return []
    return [
        (t.start[0], t.string)
        for t in tokens
        if t.type == tokenize.COMMENT
        and not ist_erlaubter_kommentar(t.string, t.start[0])
    ]
