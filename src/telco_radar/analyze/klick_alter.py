"""Das Alter einer Klick-Messung in Tagen (``alter_tage``).

Bis 21.11.2026 stand hier auch die Protokollzeile für congstar-Bündel, die einer
älteren, widersprechenden Klick-Messung wichen (Befund 13.11.2026, Lauf
43401542782). Seit congstar nur noch der Adapter misst, gibt es diesen Fall nicht
mehr (``klick_messtag``).
"""

from __future__ import annotations

from datetime import date


def alter_tage(datum: object, heute: str) -> int | None:
    """Tage von ``datum`` bis ``heute``; ``None``, wenn ``datum`` kein ISO-Datum ist."""
    try:
        return (date.fromisoformat(heute) - date.fromisoformat(str(datum))).days
    except ValueError:
        return None
