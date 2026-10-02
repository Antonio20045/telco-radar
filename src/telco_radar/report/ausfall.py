"""Benannte Ausfälle beim Bauen der Website."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ausfall:
    """Ein Teil der Website, der nicht neu gebaut wurde, mit seinem Grund."""

    teil: str
    grund: str

    @classmethod
    def aus_ausnahme(cls, teil: str, exc: BaseException) -> "Ausfall":
        """Baut den Ausfall aus einer gefangenen Ausnahme (Grund: "Typ: Meldung")."""
        return cls(teil=teil, grund=f"{type(exc).__name__}: {exc}")
