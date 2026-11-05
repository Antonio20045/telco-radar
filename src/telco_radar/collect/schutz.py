"""Was eine Schutzantwort ist: Merkmale, Ausnahme, `Retry-After`.

Eine Schutzantwort (403, 406, 429, 503 mit Challenge) umgeht der Abruf nicht
(CLAUDE.md Regel 4); `http.fetch` wertet sie hier aus. Ohne httpx-Import:
Abrufe laufen nur ueber `collect.http`.
"""

from __future__ import annotations

from typing import Any

SCHUTZ_STATUSES = {403, 406}
RETRY_AFTER_MAX = 60.0
CHALLENGE_KOPF = "cf-mitigated"
CHALLENGE_MARKEN = (
    "just a moment",
    "challenge-platform",
    "cf-chl",
    "attention required",
    "captcha",
    "_incapsula_",
    "perfdrive",
    "px-captcha",
)


def ist_challenge(resp: Any) -> bool:
    """Trägt eine Fehlerantwort die Merkmale einer Challenge- oder Captcha-Seite?"""
    if CHALLENGE_KOPF in resp.headers:
        return True
    if resp.status_code < 500:
        return False
    try:
        text = resp.text[:20000].lower()
    except (RuntimeError, UnicodeDecodeError):
        return False
    return any(marke in text for marke in CHALLENGE_MARKEN)


def retry_after(resp: Any) -> float | None:
    """Sekunden aus `Retry-After`; nur die Form mit Sekunden, sonst `None`."""
    wert = resp.headers.get("retry-after", "").strip()
    return float(wert) if wert.isdigit() else None
