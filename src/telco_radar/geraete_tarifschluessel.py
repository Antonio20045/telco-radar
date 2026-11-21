"""Tarifschlüssel für den Vergleich Soll gegen Ist (Abnahmekriterium 1, Stufe 2).

Die Seite eines Anbieters nennt einen Tarif anders als die Bündel-ID: „O2 Mobile L
Plus mit 150 GB+“ auf der Kachel, ``o2-mobile-l-plus-mit-150-gb-24-mon`` im Bestand.
``grundtarif`` bringt beide auf dieselbe Form; ``nummeriert`` zählt gleichnamige
Tarife je Modell-Speicher und Laufzeit durch. Beide Seiten (Zähler und
``geraete_vollstaendigkeit.ist_zaehlung``) rufen genau diese Funktionen.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_VARIANTE = re.compile(r"-(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])([0-9a-f]{6})$")


def grundtarif(name: str) -> str:
    """Der Tarif, wie ihn Seite und Bündel-ID gemeinsam haben: Schlüsselform ohne
    „mit 150 GB+“ und ohne „(24 Mon.)“. „O2 Mobile L Plus mit 150 GB+ (24 Mon.)“ und
    die Kachel „O2 Mobile L Plus mit 150 GB+“ ergeben beide „o2-mobile-l-plus“; die
    Kennung einer Tarifwelt-Variante („-02033e“) bleibt stehen."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    slug = re.sub(r"-\d+-mon$", "", slug)
    variante = _VARIANTE.search(slug)
    kern = slug[: variante.start()] if variante else slug
    kern = kern.split("-mit-")[0]
    return f"{kern}-{variante.group(1)}" if variante else kern


def nummeriert(eintraege: Iterable[tuple[str, str, str, str]]) -> set[str]:
    """Vergleichsschlüssel aus (Modell-Speicher, Grundtarif, Variante, Laufzeit):
    gleichnamige Tarife (Tarifwelt: fünfmal „Mobile Unlimited L Promo“) werden je
    Modell-Speicher und Laufzeit durchgezählt (``…~2``), damit Soll und Ist die
    Vielfachheit vergleichen, nicht nur den Namen."""
    gruppen: dict[tuple[str, str, str], set[str]] = {}
    for ms, tarif, variante, laufzeit in eintraege:
        gruppen.setdefault((ms, tarif, laufzeit), set()).add(variante)
    schluessel = set()
    for (ms, tarif, laufzeit), varianten in gruppen.items():
        for i, _ in enumerate(sorted(varianten), start=1):
            nummer = "" if i == 1 else f"~{i}"
            schluessel.add(f"{ms}--{tarif}{nummer}--{laufzeit}")
    return schluessel


def vergleich_eintrag(kombi: str) -> tuple[str, str, str, str]:
    """Eine Ist-Kombination (``kombi_schluessel``) als Eintrag für ``nummeriert``."""
    ms, tarif, laufzeit = kombi.split("--")
    grund = grundtarif(tarif)
    variante = _VARIANTE.search(grund)
    if variante:
        return ms, grund[: variante.start()], variante.group(1), laufzeit
    return ms, grund, "", laufzeit
