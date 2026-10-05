"""Welche ``#``-Kommentare Stufe 0 erlaubt: Werkzeugschalter und die Shebang-Zeile.

Das Löschwerkzeug ``tools/kommentare_loeschen.py`` und die Zählung ``kommentar`` in
``waechter_regeln.py`` teilen diese Definition.
"""

from __future__ import annotations

import io
import re
import tokenize

_RUFF = r"[A-Z]+[0-9]+(?:,\s*[A-Z]+[0-9]+)*"
_MYPY = r"[a-z][a-z0-9-]*(?:,\s*[a-z][a-z0-9-]*)*"
_SCHALTER = (
    rf"(?i:noqa)(?::\s*{_RUFF})?",
    rf"type:\s*ignore(?:\[{_MYPY}\])?",
    r"fmt:\s*(?:off|on|skip)",
    r"isort:\s*(?:skip_file|skip|off|on)",
    rf"ruff:\s*(?:(?:disable|enable)(?:\[{_RUFF}\])?|noqa(?::\s*{_RUFF})?)",
    rf"mypy:\s*(?:ignore-errors|disable-error-code\s*=\s*\"?{_MYPY}\"?|[a-z]+(?:-[a-z]+)+)",
)
SCHALTER_VORN = re.compile(r"#\s*(?:" + "|".join(_SCHALTER) + ")")
_NUR_SCHALTER = re.compile(r"#\s*(?:" + "|".join(_SCHALTER) + r")\s*")
SHEBANGS = frozenset({"#!/usr/bin/env python3", "#!/usr/bin/python3"})
SHEBANG_ORDNER = ("scripts/", "tools/")


def ist_erlaubter_kommentar(kommentar: str, zeile: int, pfad: str) -> bool:
    """Wahr für genau einen Werkzeugschalter je Kommentar und für die Python-Shebang
    in Zeile 1 unter ``scripts/`` und ``tools/``; jeden anderen ``#``-Kommentar zählt
    Stufe 0 als ``kommentar``."""
    if zeile == 1 and kommentar in SHEBANGS and pfad.startswith(SHEBANG_ORDNER):
        return True
    return _NUR_SCHALTER.fullmatch(kommentar) is not None


def freie_kommentare(text: str, pfad: str) -> list[tuple[int, str]]:
    """Zeile und Text jedes ``#``-Kommentars, der kein erlaubter Kommentar ist."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return []
    return [
        (t.start[0], t.string)
        for t in tokens
        if t.type == tokenize.COMMENT
        and not ist_erlaubter_kommentar(t.string, t.start[0], pfad)
    ]
