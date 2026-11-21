"""Ein nicht geprüfter Kaufweg als Erfassungssatz für die Geräteseite.

Ein Adapter, der nur kaufbare Tarife behält, kann den Kaufweg nicht immer prüfen: o2
liest dafür die Tarifübersicht (`collect.geraete.o2_kaufbar`), Vodafone die
Ausblendung der Produktseite (`collect.geraete.vodafone_sicht`). Scheitert das,
trägt jeder Rohsatz `vodafone_sicht.UNGEPRUEFT`; bei o2 ist der Wert der Grund
(„Tarifübersicht nicht gelesen“), bei Vodafone `True`. `mit_kaufweg` macht daraus
je Anbieter einen Satz in `geraete_tco.json["erfassung"]` unter `<Anbieter>|kaufweg`
(`schluessel`); der
Schlüssel trifft nie eine Geräte-ID, die Gerätekarten (`klick_erfassung.ohne_karte`)
übergehen ihn also. Die Messdatum-Zeile der Seite liest ihn über `je_anbieter`.
"""

from __future__ import annotations

from datetime import date

from .klick_erfassung import TRENNER

KAUFWEG = "kaufweg"
MARKE = "Kaufweg nicht geprüft"
SATZ = "{anbieter}: " + MARKE + " ({grund}, {datum})"
GRUND_UNBEKANNT = "Sichtbarkeit der Tarife nicht gelesen"


def schluessel(anbieter: str) -> str:
    """Der Erfassungsschlüssel des Kaufwegs eines Anbieters."""
    return f"{anbieter}{TRENNER}{KAUFWEG}"


def mit_kaufweg(
    gruende: dict[str, str], rohbuendel: list, heute: str, merkmal: str
) -> dict:
    """Die Erfassungsgründe plus je Anbieter mit ungeprüftem Kaufweg sein Satz.

    ``merkmal`` ist der Schlüssel am Rohsatz (`vodafone_sicht.UNGEPRUEFT`); er kommt
    vom Aufrufer, weil die Seite dieses Modul liest und nie `collect` laden darf."""
    offen: dict[str, set[str]] = {}
    for satz in rohbuendel:
        wert = satz.get(merkmal)
        if wert:
            grund = wert if isinstance(wert, str) else GRUND_UNBEKANNT
            offen.setdefault(str(satz.get("anbieter") or ""), set()).add(grund)
    datum = date.fromisoformat(heute).strftime("%d.%m.%Y")
    neu = {
        schluessel(anbieter): SATZ.format(
            anbieter=anbieter, grund="; ".join(sorted(gruende_)), datum=datum
        )
        for anbieter, gruende_ in offen.items()
        if anbieter
    }
    return {**gruende, **neu}


def je_anbieter(gruende: dict[str, str] | None) -> dict[str, str]:
    """Anbieter -> Satz des ungeprüften Kaufwegs (leer, wenn alles geprüft ist)."""
    ende = TRENNER + KAUFWEG
    return {
        s.removesuffix(ende): satz
        for s, satz in (gruende or {}).items()
        if s.endswith(ende)
    }
