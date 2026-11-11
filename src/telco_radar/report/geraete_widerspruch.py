"""Widerspruchsregel: ein Lücken-Grund gilt nicht gegen das, was der Radar selbst misst.

Stichprobe 10.11.2026 am Original: vier von zwölf „belegten“ Lücken waren falsch.
Eine Zelle „nicht im Portfolio“ braucht einen frischen, eindeutigen Beleg; sonst ist sie
eine Messlücke („Noch nicht erfasst“, Fail-closed).

* Führt der Radar für dieselbe Kombination (Anbieter, Gerät, Speicher) ein lieferbares,
  frisches Neugerät oder einen frischen Preis, fällt der Lücken-Grund weg: nicht
  gezeigt, nicht gezählt (``setze_luecken``, ``neugeraete``).
* Ein erneuertes Angebot neben einem Neugerät desselben Anbieters sagt nie „nur ein
  erneuertes Gerät“ (``erneuert_satz``). Im Oktober stand das für congstar Galaxy S26
  256 GB, Xiaomi 17 Ultra 512 GB und Galaxy S26 Ultra 512 GB in der Zeile des
  erneuerten Bündels, obwohl dieselbe Tabelle das Neugerät vergleichbar führte.
* Der Satz der Klick-Erfassung gilt nur mit Datum und höchstens
  ``klick_erfassung.BELEG_MAX_TAGE`` alt; die Karten der Config haben ihr ``bis``.

Eine Stelle für Karte, Bündelliste, Radar und Export: ``geraete_view`` ruft nur
``setze_luecken``.
"""

from __future__ import annotations

from ..analyze.klick_erfassung import KEINE_NEUGERAETE, Neugeraete
from ..analyze.klick_erfassung import fuer_modell as erfassung_fuer_modell
from ..geraete_model import STATUS_AKTIV
from . import geraete_luecken_beleg
from .geraete_tco_karten import ist_frisch

NEU = "neu"
LIEFERBAR = "lieferbar"
ERNEUERT_SATZ = (
    "{anbieter} führt für dieses Gerät nur ein {etikett} Gerät – "
    "kein Vergleich gegen ein Neugerät."
)
ERNEUERT_NEBEN_NEU = (
    "{anbieter}: erneuertes Angebot – kein Vergleich gegen ein Neugerät."
)


def neugeraete(listungen: list[dict], heute: str) -> Neugeraete:
    """Anbieter, Gerät und Speicher der aktiven, lieferbaren, frisch gelesenen
    Neugeräte (``geraete_tco_karten.ist_frisch``). Ohne Datum, Speicher oder Gerät
    zählt eine Listung nicht."""
    geraet, speicher = set(), set()
    for e in listungen:
        gb = e.get("speicher_gb")
        if (
            e.get("status") != STATUS_AKTIV
            or (e.get("zustand") or NEU) != NEU
            or e.get("verfuegbarkeit") != LIEFERBAR
            or not isinstance(gb, int)
            or not e.get("device_id")
            or not e.get("anbieter")
            or not heute
            or not ist_frisch(str(e.get("last_verified") or ""), heute)
        ):
            continue
        geraet.add((e["anbieter"], e["device_id"]))
        speicher.add((e["anbieter"], e["device_id"], gb))
    return Neugeraete(frozenset(geraet), frozenset(speicher))


def _frischer_preis(karte: dict) -> bool:
    return (
        (karte.get("zustand") or NEU) == NEU
        and karte.get("gesamt") is not None
        and bool(karte.get("frisch", True))
        and not karte.get("naeherung")
    )


def neu_da(modell: dict, neu: Neugeraete) -> list[str]:
    """Anbieter, die in diesem Modell ein Neugerät führen: frischer Preis auf einer
    Karte oder lieferbares Neugerät im Bestand."""
    gb, geraet = modell.get("speicher"), modell.get("device_id")
    da = {k.get("anbieter") for k in modell.get("karten") or [] if _frischer_preis(k)}
    da |= {a for a, d, s in neu.speicher if d == geraet and s == gb}
    return sorted(str(a) for a in da if a)


def erneuert_satz(anbieter: str, etikett: str | None, neben_neu: bool) -> str:
    """Der Grund einer erneuerten Zeile. „Nur ein erneuertes Gerät“ ist eine
    Portfolio-Aussage und steht nur, wenn der Anbieter in diesem Modell kein Neugerät
    führt (``neu_da``); sonst benennt die Zeile nur den Zustand."""
    vorlage = ERNEUERT_NEBEN_NEU if neben_neu else ERNEUERT_SATZ
    return vorlage.format(anbieter=anbieter, etikett=etikett or "nicht neues")


def setze_luecken(
    modelle: list[dict],
    erfassung: dict,
    belege: dict,
    listungen: list[dict],
    heute: str,
) -> None:
    """Gibt jedem Modell seine Lücken-Gründe (Klick-Erfassung und belegte Lücken der
    Config) ohne abgelaufene Belege und ohne Widerspruch des Radars, dazu ``neu_da``."""
    neu = neugeraete(listungen, heute)
    for modell in modelle:
        modell["erfassung"] = erfassung_fuer_modell(erfassung, modell, heute, neu)
        modell["belegte_luecken"] = geraete_luecken_beleg.fuer_modell(
            belege, modell, heute, neu
        )
        modell["neu_da"] = neu_da(modell, neu)


__all__ = ["KEINE_NEUGERAETE", "erneuert_satz", "neu_da", "neugeraete", "setze_luecken"]
