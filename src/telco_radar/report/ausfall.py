"""Benannte Ausfälle beim Bauen der Website."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

KONFIGURATION_TEIL = "Konfiguration"
NEWSLETTER_TEIL = "Newsletter-Anmeldung"


@dataclass(frozen=True)
class Ausfall:
    """Ein Teil der Website, der nicht neu gebaut wurde, mit seinem Grund."""

    teil: str
    grund: str

    @classmethod
    def aus_ausnahme(cls, teil: str, exc: BaseException) -> "Ausfall":
        """Baut den Ausfall aus einer gefangenen Ausnahme (Grund: "Typ: Meldung")."""
        return cls(teil=teil, grund=f"{type(exc).__name__}: {exc}")


def ohne_konfiguration(wurzel: Path) -> list[Ausfall]:
    """Der Ausfall „Konfiguration“, wenn unter ``wurzel`` kein ``config/`` liegt."""
    if (wurzel / "config").is_dir():
        return []
    return [Ausfall(teil=KONFIGURATION_TEIL, grund=f"config/ fehlt unter {wurzel}")]
