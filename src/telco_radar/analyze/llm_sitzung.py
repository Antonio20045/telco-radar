"""Der veränderliche Zustand eines LLM-Laufs als Objekt statt als Modulzustand.

``analyze/llm.py`` liest den Zustand nur über ``LlmSitzung.aktive()``;
``naehte.Naehte.setzen`` legt je Lauf eine frische Sitzung an.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Protocol

from ..collect.http import Transport

LlmClient = Callable[[str, str, str, int, int], str]
"""``(system, user, modell, max_tokens, versuche) -> Antworttext``."""


class LlmNaehte(Protocol):
    """Was die Sitzung von ``naehte.Naehte`` braucht: Netz und LLM-Client."""

    @property
    def transport(self) -> Transport | None:
        """Transport für den LLM-Endpunkt, ``None`` heißt echtes Netz."""

    @property
    def llm_client(self) -> LlmClient | None:
        """Ersatz für den Anbieteraufruf, ``None`` heißt echter Anbieter."""


@dataclass
class LlmSitzung:
    """Der veränderliche Zustand eines Laufs: Nähte, Ketten, Verbrauch, Budget.

    ``naehte.Naehte.setzen`` aktiviert je Lauf eine frische Sitzung, damit weder
    tote Modelle noch Verbrauch aus einem vorigen Lauf hängen bleiben. Alle
    Threads eines Laufs teilen die aktive Sitzung.
    """

    naehte: LlmNaehte | None = None
    ausweich: dict[str, str] = field(default_factory=dict)
    verbrauch: dict[str, dict[str, int]] = field(default_factory=dict)
    preise: dict[str, dict[str, float]] = field(default_factory=dict)
    budget_usd: float | None = None
    tote_modelle: set[str] = field(default_factory=set)
    _aktiv: ClassVar[LlmSitzung | None] = None

    @classmethod
    def aktive(cls) -> LlmSitzung:
        """Die Sitzung des laufenden Laufs; ohne Lauf eine frische."""
        if LlmSitzung._aktiv is None:
            LlmSitzung._aktiv = cls()
        return LlmSitzung._aktiv

    def aktivieren(self) -> LlmSitzung:
        """Macht diese Sitzung zur aktiven und gibt sie zurück."""
        LlmSitzung._aktiv = self
        return self

    @property
    def transport(self) -> Transport | None:
        """Transport aus den Nähten, ``None`` heißt echtes Netz."""
        return self.naehte.transport if self.naehte else None

    @property
    def client(self) -> LlmClient | None:
        """LLM-Client aus den Nähten, ``None`` heißt echter Anbieter."""
        return self.naehte.llm_client if self.naehte else None
