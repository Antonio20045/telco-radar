"""Tarifschlüssel für den Vergleich Soll gegen Ist (Abnahmekriterium 1, Stufe 2).

Die Seite eines Anbieters schreibt einen Tarif anders als die Bündel-ID: „O2 Mobile L
Plus mit 150 GB+“ auf der Kachel, ``o2-mobile-l-plus-mit-150-gb-24-mon`` im Bestand.
``grundtarif`` bringt nur Schreibvarianten DESSELBEN Tarifs zusammen (Groß/Klein,
Satzzeichen, Zusatz „(24 Mon.)“); verschiedene Datenvolumen („mit 150 GB“, „mit
300 GB“) bleiben verschiedene Tarife (Prüfung PR 205).

Gleichnamige Tarife der Tarifwelt („Mobile Unlimited L Promo“ fünfmal, je mit anderem
Preis) werden über ein stabiles Merkmal der Seite unterschieden: den Preis, den Karte
und Bündel nennen (``preis_code``: Gerät einmalig, Tarif monatlich). Nur was danach
noch gleich ist, wird durchgezählt (``~2``). Beide Seiten (Zähler und
``geraete_vollstaendigkeit.ist_zaehlung``) rufen genau diese Funktionen.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_VARIANTE = re.compile(r"-(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])([0-9a-f]{6})$")
PREIS = "@"
NUMMER = "~"


def grundtarif(name: str) -> str:
    """Schlüsselform eines Tarifnamens ohne den Zusatz „(24 Mon.)“ und mit „35 GB“ =
    „35GB“; die Kennung einer Tarifwelt-Variante („-02033e“) bleibt stehen
    (``ohne_variante`` trennt sie)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    slug = re.sub(r"(\d)-(gb|mb|tb)\b", r"\1\2", slug)
    return re.sub(r"-\d+-mon$", "", slug)


def ohne_variante(slug: str) -> tuple[str, str]:
    """(Tarif, Variantenkennung) – „allnet-flat-25gb-02033e“ -> („allnet-flat-25gb“,
    „02033e“); ohne Kennung ist die Variante leer."""
    treffer = _VARIANTE.search(slug)
    if treffer is None:
        return slug, ""
    return slug[: treffer.start()], treffer.group(1)


def _betrag(wert: float) -> str:
    return f"{float(wert):.2f}".rstrip("0").rstrip(".")


def preis_code(geraet: float | None, monatlich: float | None) -> str:
    """„1-59.99“ aus Gerätepreis einmalig und Tarif monatlich; leer, wenn einer fehlt
    (dann bleibt nur das Durchzählen)."""
    if geraet is None or monatlich is None:
        return ""
    return f"{_betrag(geraet)}-{_betrag(monatlich)}"


def mit_preis(tarif: str, preis: str) -> str:
    """Tarifschlüssel mit Preis als Merkmal (nur Tarifwelt)."""
    return f"{tarif}{PREIS}{preis}" if preis else tarif


def kern(tarif_teil: str) -> str:
    """Der Tarif eines Kombinationsschlüssels ohne Preis und Nummer."""
    return tarif_teil.split(NUMMER)[0].split(PREIS)[0]


def normiert(tarif_teil: str) -> str:
    """Ein Tarifteil eines Schlüssels in Grundform; Preis und Nummer bleiben."""
    teil = re.match(rf"^([^{PREIS}{NUMMER}]*)(.*)$", tarif_teil)
    assert teil is not None
    return grundtarif(teil.group(1)) + teil.group(2)


def nummeriert(eintraege: Iterable[tuple[str, str, str, str]]) -> set[str]:
    """Vergleichsschlüssel aus (Modell-Speicher, Tarif, Variante, Laufzeit): was nach
    Name und Preis noch gleich ist, wird je Modell-Speicher und Laufzeit durchgezählt
    (``…~2``)."""
    gruppen: dict[tuple[str, str, str], set[str]] = {}
    for ms, tarif, variante, laufzeit in eintraege:
        gruppen.setdefault((ms, tarif, laufzeit), set()).add(variante)
    schluessel = set()
    for (ms, tarif, laufzeit), varianten in gruppen.items():
        for i, _ in enumerate(sorted(varianten), start=1):
            nummer = "" if i == 1 else f"{NUMMER}{i}"
            schluessel.add(f"{ms}--{tarif}{nummer}--{laufzeit}")
    return schluessel


def vergleich_eintrag(kombi: str, preis: str = "") -> tuple[str, str, str, str]:
    """Eine Ist-Kombination (``kombi_schluessel``) als Eintrag für ``nummeriert``;
    ``preis`` (``preis_code``) nur für die Tarifwelt."""
    ms, tarif, laufzeit = kombi.split("--")
    name, variante = ohne_variante(grundtarif(tarif))
    return ms, mit_preis(name, preis), variante, laufzeit
