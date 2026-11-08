"""Teile der Klick-Karte: die Auswertungsregeln ``ratenplan`` und ``tarifslug`` und der
Weiterschritt in die Bestellstrecke.

Das Format beschreibt ``klickkarte``, die Regeln wenden ``klickratenplan`` und
``analyze.klick_tarifslug`` an. Dieses Modul hält nur Namen und Datentypen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RATENPLAN_TARIFCODE = "tarifcode"
RATENPLAN_OHNE_RABATTPHASE = "ohne_rabattphase"
RATENPLAN_ARTEN = (RATENPLAN_TARIFCODE, RATENPLAN_OHNE_RABATTPHASE)
TARIFSLUG_NAME = "name"
TARIFSLUG_SEITENPARAMETER = "seitenparameter"
TARIFSLUG_ARTEN = (TARIFSLUG_NAME, TARIFSLUG_SEITENPARAMETER)
BELEGLINK_KONFIGURATION = "konfiguration"
GRUND_ART = "unbekannte Art"
GRUND_NICHT_ZUR_ART = "gehört nicht zu dieser Art"
GRUND_WEITER_DIMENSION = "weiter braucht genau eins von kacheln und klicken"
BILDFOLGE_SCHRITTE = ("geraet_speicher", "tarif", "laufzeit")


@dataclass(frozen=True)
class Ratenplanregel:
    """Wie der Tarifpreis an die Ratenlaufzeit gebunden wird (``klickratenplan``).

    ``art`` ``tarifcode``: der Nachweis ``ratenplan`` trägt den Satz des Hinweises, und
    der ``teil`` der Konfiguration in der Antwortadresse nennt mit ``muster`` (erste
    Gruppe) dieselbe Ratenzahl. ``art`` ``ohne_rabattphase``: der Nachweis ist genau
    ``nachweis``, die leere Rabattliste des Tarifs. Ohne Regel in der Karte gibt es
    keine Phase."""

    art: str
    teil: str | None = None
    muster: re.Pattern[str] | None = None
    nachweis: str | None = None


@dataclass(frozen=True)
class Tarifslugregel:
    """Woher der Tarif-Slug eines Klick-Satzes kommt (``analyze.klick_tarifslug``).

    ``art`` ``name``: der Tarifname ohne Leistungszusatz. ``art`` ``seitenparameter``:
    die Zahl im ``parameter`` der Seitenadresse. ``beleglink`` ``konfiguration``: der
    Beleglink trägt Tarif und Ratenzahl der Zeile statt die der Startkonfiguration."""

    art: str
    parameter: str | None = None
    beleglink: str | None = None


@dataclass(frozen=True)
class Weiterschritt:
    """Der eine Klick in die Bestellstrecke und die Dimension auf der Folgeseite.

    ``selektor`` und ``text`` nennen den Weiter-Knopf der Startseite; die Optionen von
    ``kacheln`` stehen auf der Folgeseite als Kacheln nebeneinander und werden gelesen,
    nie geklickt. Statt ``kacheln`` nennt ``klicken`` eine Dimension, deren Optionen auf
    der Folgeseite einzeln geklickt werden (Vodafone: Tarif); genau eins von beiden.
    """

    selektor: str
    text: str
    kacheln: str | None = None
    klicken: str | None = None

    @property
    def dimension(self) -> str:
        """Die Dimension der Folgeseite, gelesen oder geklickt."""
        dimension = self.kacheln if self.kacheln is not None else self.klicken
        if dimension is None:
            raise ValueError(GRUND_WEITER_DIMENSION)
        return dimension
