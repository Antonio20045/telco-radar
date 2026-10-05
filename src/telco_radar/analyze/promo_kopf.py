"""Vergleich zweier Promo-Überschriften: gleiches Angebot oder zwei."""

from __future__ import annotations

import re

_FUZZY_HEADLINE_THRESHOLD = 0.6


def _normalize_headline(headline: str) -> str:
    return " ".join((headline or "").lower().split())


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text or ""))


def _word_overlap(headline_a: str, headline_b: str) -> float:
    words_a = set(_normalize_headline(headline_a).split())
    words_b = set(_normalize_headline(headline_b).split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / min(len(words_a), len(words_b))


def _zahlen_widersprechen(headline_a: str, headline_b: str) -> bool:
    """Beide Überschriften nennen Zahlen, aber keine gemeinsame."""
    nums_a, nums_b = _numbers(headline_a), _numbers(headline_b)
    return bool(nums_a and nums_b and nums_a.isdisjoint(nums_b))


def _same_offer(headline_a: str, headline_b: str) -> bool:
    """Heuristik fuer 'gleiches Angebot, nur anders formuliert'. Wort-
    Ueberlappung allein reicht nicht: "10 GB Bonus" und "20 GB Bonus" teilen
    sich fast alle Woerter, sind aber verschiedene Angebote - deshalb
    zusaetzlich ein Zahlen-Waechter: enthalten beide Headlines Zahlen (GB,
    Euro-Betraege, Alters-/Preisgrenzen - genau das, was ein Angebot von
    einem sonst fast gleich klingenden anderen unterscheidet) und haben sie
    KEINE einzige davon gemeinsam, ist es kein Match, egal wie aehnlich der
    Text sonst ist."""
    if _word_overlap(headline_a, headline_b) < _FUZZY_HEADLINE_THRESHOLD:
        return False
    return not _zahlen_widersprechen(headline_a, headline_b)
