"""Der Katalog der Anmeldeseite: config/newsletter.yaml, geladen und geprueft.

Eigenes Modul und nicht Teil von `filters.py`, weil drei Stellen ihn
brauchen und keine von der anderen abhaengen soll: das Formular (welche
Haekchen gibt es), die Filter (was bedeutet `telekom`) und der Store (ist
dieser Schluessel ueberhaupt gueltig).

Die Pruefung beim Laden ist der eigentliche Zweck. Ein Schluessel, den es
nicht gibt, ist im Abo-Datensatz ein stillschweigend leerer Filter - der
Abonnent bekommt dann nicht "nichts", sondern nach der Regel "leer heisst
alles" plotzlich ALLES. Ein Tippfehler in dieser Datei kehrt also die
Auswahl eines Menschen ins Gegenteil, ohne dass irgendwo etwas rot wird.
Deshalb: unbekannter Schluessel -> `ValueError` beim Laden, nicht spaeter.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..textwerkzeug import begriffs_muster

log = logging.getLogger(__name__)

DIMENSIONEN = ("bereiche", "regionen", "wettbewerber", "kategorien")

# Die Namen, unter denen eine Dimension im Abo-Datensatz steht. Englisch,
# weil sie im JSON eines Abos landen und dort neben `email`, `filters` und
# `state` stehen - ein halb uebersetztes Schema ist schlimmer als ein ganz
# englisches oder ein ganz deutsches.
FELD_JE_DIMENSION = {"bereiche": "branches", "regionen": "regions",
                     "wettbewerber": "competitors", "kategorien": "categories"}


@dataclass(frozen=True)
class Auswahl:
    """Ein waehlbarer Eintrag einer Dimension."""
    key: str
    label: str
    beschreibung: str = ""
    treffer: tuple[str, ...] = ()
    ressorts: tuple[str, ...] = ()

    @property
    def muster(self):
        """Wortgrenzen-Muster ueber `treffer` - oder None."""
        return begriffs_muster(self.treffer, kein_punkt_davor=True)


@dataclass(frozen=True)
class Grenzen:
    max_eintraege: int = 8
    max_stichwoerter: int = 10
    min_stichwort_laenge: int = 4
    vorschau_warnung_ab: int = 25
    vorschau_tage: int = 30


@dataclass
class NewsletterKatalog:
    bereiche: list[Auswahl] = field(default_factory=list)
    regionen: list[Auswahl] = field(default_factory=list)
    wettbewerber: list[Auswahl] = field(default_factory=list)
    kategorien: list[Auswahl] = field(default_factory=list)
    grenzen: Grenzen = field(default_factory=Grenzen)

    def eintraege(self, dimension: str) -> list[Auswahl]:
        return getattr(self, dimension)

    def schluessel(self, dimension: str) -> set[str]:
        return {a.key for a in self.eintraege(dimension)}

    def finde(self, dimension: str, key: str) -> Auswahl | None:
        for a in self.eintraege(dimension):
            if a.key == key:
                return a
        return None

    def label(self, dimension: str, key: str) -> str:
        a = self.finde(dimension, key)
        return a.label if a else key


def _auswahl(roh: dict, dimension: str) -> Auswahl:
    key = str(roh.get("key") or "").strip()
    if not key:
        raise ValueError(f"newsletter.yaml: Eintrag ohne 'key' in {dimension}")
    return Auswahl(
        key=key,
        label=str(roh.get("label") or key),
        beschreibung=str(roh.get("beschreibung") or ""),
        treffer=tuple(str(t) for t in (roh.get("treffer") or [])),
        ressorts=tuple(str(r) for r in (roh.get("ressorts") or [])),
    )


def lade_katalog(root: Path) -> NewsletterKatalog:
    """config/newsletter.yaml laden. Fehlt sie, gibt es keinen Newsletter.

    Bewusst KEIN stiller Rueckfall auf einen leeren Katalog: bei leeren
    Dimensionen wuerde die Regel "leer heisst alles" jedem Abonnenten alles
    schicken. Ein fehlender Katalog ist ein Fehler, kein Standardfall.
    """
    pfad = Path(root) / "config" / "newsletter.yaml"
    if not pfad.exists():
        raise FileNotFoundError(f"config/newsletter.yaml fehlt ({pfad})")
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}

    katalog = NewsletterKatalog(
        grenzen=Grenzen(**{k: int(v) for k, v in
                           (daten.get("grenzen") or {}).items()
                           if k in Grenzen.__dataclass_fields__}))
    for dimension in DIMENSIONEN:
        eintraege = [_auswahl(r, dimension) for r in (daten.get(dimension) or [])]
        if not eintraege:
            raise ValueError(f"newsletter.yaml: Dimension '{dimension}' ist leer")
        gesehen: set[str] = set()
        for a in eintraege:
            if a.key in gesehen:
                raise ValueError(
                    f"newsletter.yaml: Schluessel '{a.key}' kommt in "
                    f"'{dimension}' zweimal vor")
            gesehen.add(a.key)
        setattr(katalog, dimension, eintraege)
    return katalog
