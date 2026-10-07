"""Goldliste der Abnahme (Datenkonzept Geräte, Abschnitt 11): Laden und Auflösen.

Je Netzbetreiber höchstens ``GOLD_JE_ANBIETER`` feste Varianten in
``config/geraete_goldliste.yaml``, über stabile Schlüssel und nie über Titeltext:
``device_id`` aus dem Gerätekatalog, ``speicher_gb``, ``tarif_name`` wie im Bestand,
``laufzeit_monate`` (Ratenlaufzeit) und optional ``farbe`` wie in der SKU. Führt ein
Anbieter die Beispielseite (iPhone 17 Pro 256 GB, Abschnitt 2), steht sie zuerst.
``goldliste_aufloesen`` findet je Eintrag genau ein Bündel oder benennt den Befund:
``nicht gefunden`` oder ``mehrdeutig`` mit den IDs der Kandidaten.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..geraete_model import sku_id
from .geraete_pruefstatus import ERLAUBTE_RATENLAUFZEITEN

log = logging.getLogger(__name__)

GOLD_JE_ANBIETER = 10
BEISPIELSEITE = ("apple-iphone-17-pro", 256)
GOLDLISTE = Path("config") / "geraete_goldliste.yaml"
NICHT_GEFUNDEN = "nicht gefunden"
MEHRDEUTIG = "mehrdeutig"
_FELDER = {
    "device_id": str,
    "speicher_gb": int,
    "farbe": str,
    "tarif_name": str,
    "laufzeit_monate": int,
}
_PFLICHT = ("device_id", "speicher_gb", "tarif_name", "laufzeit_monate")

GeraetVon = Callable[[str], tuple[str, int | None]]


class GoldlisteFehler(ValueError):
    """Die Goldliste fehlt, ist unlesbar oder verletzt ihre Form."""


@dataclass(frozen=True)
class Goldeintrag:
    """Eine Variante der Goldliste."""

    anbieter: str
    device_id: str
    speicher_gb: int
    tarif_name: str
    laufzeit_monate: int
    farbe: str | None = None

    @property
    def variante(self) -> tuple[str, str, int, str, int]:
        """Anbieter, Gerät, Speicher, Tarif und Ratenlaufzeit."""
        return (
            self.anbieter,
            self.device_id,
            self.speicher_gb,
            self.tarif_name,
            self.laufzeit_monate,
        )

    @property
    def beispielseite(self) -> bool:
        """Gerät und Speicher der Beispielseite."""
        return (self.device_id, self.speicher_gb) == BEISPIELSEITE


@dataclass(frozen=True)
class Aufloesung:
    """Ein Eintrag der Goldliste mit seinem Bündel oder dem Befund, warum keins."""

    eintrag: Goldeintrag
    buendel: Mapping | None
    befund: str | None = None
    kandidaten: tuple[str, ...] = ()


def lade_goldliste(wurzel: Path) -> list[Goldeintrag]:
    """Die Goldliste unter ``wurzel``; wirft ``GoldlisteFehler`` mit Grund."""
    pfad = Path(wurzel) / GOLDLISTE
    try:
        roh = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        log.error("Goldliste %s unlesbar: %s", pfad, exc)
        raise GoldlisteFehler(f"{GOLDLISTE} unlesbar: {exc}") from exc
    return goldliste_aus(roh)


def goldliste_aus(roh: object) -> list[Goldeintrag]:
    """Die Einträge aus ``{"anbieter": {Name: [Eintrag, …]}}``.

    Je Anbieter 1 bis ``GOLD_JE_ANBIETER`` Einträge; führt er die Beispielseite, steht
    sie zuerst; keine Variante steht zweimal.
    """
    je_anbieter = roh.get("anbieter") if isinstance(roh, Mapping) else None
    if not isinstance(je_anbieter, Mapping):
        raise GoldlisteFehler("Goldliste ohne Zuordnung 'anbieter'")
    eintraege: list[Goldeintrag] = []
    for anbieter, liste in je_anbieter.items():
        if not isinstance(liste, list) or not 0 < len(liste) <= GOLD_JE_ANBIETER:
            raise GoldlisteFehler(f"{anbieter}: 1 bis {GOLD_JE_ANBIETER} Einträge")
        eigene = [_eintrag(str(anbieter), e) for e in liste]
        if any(e.beispielseite for e in eigene) and not eigene[0].beispielseite:
            raise GoldlisteFehler(f"{anbieter}: die Beispielseite steht nicht zuerst")
        eintraege += eigene
    doppelt = [v for v, n in Counter(e.variante for e in eintraege).items() if n > 1]
    if doppelt:
        raise GoldlisteFehler(f"Variante doppelt: {doppelt[0]}")
    return eintraege


def _eintrag(anbieter: str, roh: object) -> Goldeintrag:
    if not isinstance(roh, Mapping):
        raise GoldlisteFehler(f"{anbieter}: Eintrag ist keine Zuordnung: {roh!r}")
    fremd = sorted(set(map(str, roh)) - set(_FELDER))
    fehlt = [f for f in _PFLICHT if roh.get(f) is None]
    falsch = [f for f, typ in _FELDER.items() if f in roh and type(roh[f]) is not typ]
    if fremd or fehlt or falsch:
        raise GoldlisteFehler(
            f"{anbieter}: {roh!r} unbekannt {fremd}, fehlt {fehlt}, Typ falsch {falsch}"
        )
    if roh["laufzeit_monate"] not in ERLAUBTE_RATENLAUFZEITEN:
        raise GoldlisteFehler(f"{anbieter}: Ratenlaufzeit {roh['laufzeit_monate']}")
    return Goldeintrag(
        anbieter,
        roh["device_id"],
        roh["speicher_gb"],
        roh["tarif_name"],
        roh["laufzeit_monate"],
        roh.get("farbe"),
    )


def goldliste_aufloesen(
    goldliste: Iterable[Goldeintrag], buendel: Iterable[Mapping], geraet_von: GeraetVon
) -> list[Aufloesung]:
    """Je Eintrag das eine Bündel gleicher Variante, mit Farbe auch gleicher SKU.

    ``geraet_von`` ordnet einer SKU Gerät und Speicher zu, wie die Seite es tut
    (``report.geraete_tco_karten.geraet_aus_sku``). Ohne Bündel heißt der Befund
    ``NICHT_GEFUNDEN``, mit mehreren ``MEHRDEUTIG`` samt ihren IDs.
    """
    je_variante: dict[tuple, list[Mapping]] = {}
    for satz in buendel:
        geraet, speicher = geraet_von(str(satz.get("sku_id") or ""))
        variante = (
            satz.get("anbieter"),
            geraet,
            speicher,
            satz.get("tarif_name"),
            satz.get("laufzeit_monate"),
        )
        je_variante.setdefault(variante, []).append(satz)
    return [_aufloesung(e, je_variante.get(e.variante, [])) for e in goldliste]


def _aufloesung(eintrag: Goldeintrag, kandidaten: list[Mapping]) -> Aufloesung:
    if eintrag.farbe is not None:
        sku = sku_id(eintrag.device_id, eintrag.speicher_gb, eintrag.farbe)
        kandidaten = [s for s in kandidaten if s.get("sku_id") == sku]
    if len(kandidaten) == 1:
        return Aufloesung(eintrag, kandidaten[0])
    if not kandidaten:
        return Aufloesung(eintrag, None, NICHT_GEFUNDEN)
    ids = tuple(sorted(str(s.get("id") or "") for s in kandidaten))
    return Aufloesung(eintrag, None, MEHRDEUTIG, ids)
