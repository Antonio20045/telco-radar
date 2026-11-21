"""Gründe für Differenzen zwischen Angebotszählung und Messung, nur aus Signalen.

Eine **Lücke** (auf der Seite angeboten, nicht gemessen) bekommt in dieser
Reihenfolge einen Grund: Ausfallvermerk des Anbieters; Tarifwelt-Lücke der Messung
zu genau dieser Kombination (``tw['luecken_liste']``); Tarif mit Sonderbedingung
(``tarif_sonderbedingung``, nur Tarifwelt); gleichnamiger Tarif mit anderem Preis
gemessen („nicht eindeutig zuordenbar“); Vermerk zum Modell, wenn Modell oder
Speicher im Ist ganz fehlen; Katalog. Sonst ``UNBENANNT``.

Ein **erfasster Preis ohne Angebot auf der Seite** (Ist ohne Soll) ist benannt, wenn
die Seite die Kombination selbst ausschließt (Vodafone: „XS und S nicht in 36
Raten“) oder ein gleichnamiger Tarif mit anderem Preis auf der Seite steht; sonst
``UNBENANNT`` und damit ein Befund des Wächters (Prüfung PR 205).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..geraete_tarifschluessel import grundtarif, kern
from ..geraete_vollstaendigkeit import (
    GRUND_NICHT_IM_KATALOG,
    SATURN_NETZE,
    UNBENANNT,
    Ist,
    SichtbareAuswahl,
    Signale,
    grund_fuer,
    modell_der_kombination,
)
from ..tarif_sonderbedingung import sonderbedingung

NICHT_EINDEUTIG = "gleichnamiger Tarif mit anderem Preis, nicht eindeutig zuordenbar"
AUSGESCHLOSSEN = "laut Seite nicht wählbar ({tarif} mit {monate} Raten)"


@dataclass
class ZeilenSoll:
    """Das Soll einer Anbieterzeile aus der Zählung."""

    modelle: dict[str, dict] = field(default_factory=dict)
    speicher: set[str] = field(default_factory=set)
    auswahlen: list[SichtbareAuswahl] = field(default_factory=list)
    nicht_gezaehlt: list[dict] = field(default_factory=list)
    tarifnamen: dict[str, str] = field(default_factory=dict)
    ausgeschlossen: dict[tuple[str, str, int], str] = field(default_factory=dict)
    unvollstaendig: list[str] = field(default_factory=list)
    namen: dict[str, str] = field(default_factory=dict)
    kachelmodelle: set[str] = field(default_factory=set)
    gelesen: set[str] = field(default_factory=set)
    teilweise_gelesen: set[str] = field(default_factory=set)


def _teile(schluessel: str) -> tuple[str, str, str]:
    teile = (schluessel.split("--") + ["", ""])[:3]
    return teile[0], teile[1], teile[2]


def _gleichnamig(schluessel: str, andere: set[str]) -> bool:
    ms, tarif, laufzeit = _teile(schluessel)
    return any(
        k != schluessel
        and _teile(k)[0] == ms
        and _teile(k)[2] == laufzeit
        and kern(_teile(k)[1]) == kern(tarif)
        for k in andere
    )


def _tarifwelt_luecke(signale: Signale, modell: str, ms: str, tarif: str) -> str | None:
    """Die Lücke der Tarifwelt-Messung zu dieser Kombination („<modell> 256 GB …“)."""
    gb = ms[len(modell) + 1 :].removesuffix("gb")
    vorne = f"{modell} {gb} GB"
    for eintrag in signale.tarifwelt.get("luecken_liste") or ():
        text, grund = str(eintrag[0]), str(eintrag[1])
        if text == vorne or (
            text.startswith(vorne + " ") and kern(tarif) in grundtarif(text)
        ):
            return f"Tarifwelt: {grund}"
    return None


def grund_der_luecke(
    name: str,
    soll: ZeilenSoll,
    ist: Ist,
    signale: Signale,
    ist_je: dict,
) -> Callable[[str], str]:
    """Der Grund einer fehlenden Kombination oder eines fehlenden Speichers."""
    tarifwelt = name in SATURN_NETZE

    def grund(schluessel: str) -> str:
        vermerk = signale.erfassung.get(name) or signale.ausfall
        if vermerk:
            return str(vermerk)
        ms, tarif, _ = _teile(schluessel)
        modell = modell_der_kombination(schluessel)
        info = soll.modelle.get(modell or "")
        if info is None or not info["im_katalog"] or modell is None:
            return GRUND_NICHT_IM_KATALOG
        if tarifwelt and tarif:
            besonders = _tarifwelt_luecke(
                signale, modell, ms, tarif
            ) or sonderbedingung(soll.tarifnamen.get(kern(tarif), tarif))
            if besonders:
                return besonders
        if tarif and _gleichnamig(schluessel, ist.kombinationen):
            return NICHT_EINDEUTIG
        if ms in ist.modell_speicher:
            return UNBENANNT
        return grund_fuer(name, info, signale, ist_je)

    return grund


def grund_ohne_angebot(soll: ZeilenSoll) -> Callable[[str], str]:
    """Der Grund eines erfassten Preises, den die Seite nicht anbietet."""
    angeboten = (
        set().union(*(a.schluessel() for a in soll.auswahlen))
        if soll.auswahlen
        else set()
    )

    def grund(schluessel: str) -> str:
        _, tarif, laufzeit = _teile(schluessel)
        modell = modell_der_kombination(schluessel) or ""
        monate = int(laufzeit.removesuffix("m")) if laufzeit[:-1].isdigit() else -1
        ausschluss = soll.ausgeschlossen.get((modell, kern(tarif), monate))
        if ausschluss:
            return AUSGESCHLOSSEN.format(tarif=ausschluss, monate=monate)
        if _gleichnamig(schluessel, angeboten):
            return NICHT_EINDEUTIG
        return UNBENANNT

    return grund
