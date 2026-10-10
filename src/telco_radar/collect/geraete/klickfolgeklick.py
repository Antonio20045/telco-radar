"""Gang des Weiter-Schritts und die Klicks auf der Folgeseite (``weiter.klicken``).

``klickweiter`` wählt die Startseite, klickt weiter und liest Kacheln. Trägt der
Weiter-Schritt statt ``kacheln`` die Dimension ``klicken`` (Vodafone: der Tarif steht
erst auf der Folgeseite „Zur Tarifauswahl“, Erkundung 10.10.2026, Zweig klick-erkundung
d969c6e1, klicks-3.json), klickt ``folgeklicks`` dort jede Option nacheinander wie auf
einer Startseite (``Gang.waehle``) und liest danach: die zweite Lesung neu
(``klicklesung.Leser.folgelesung``, Seitenwerte der Startseite), Markierung der
geklickten Option, Text der Zusammenfassung. Das Tor lässt nach dem Weiter-Klick nur
GET und HEAD durch (``klicktor.GRUND_NUR_LESEN``); ein solcher Klick kann also nichts
schreiben. Zeigt die Seite danach Anmeldung, Checkout oder Zahlung, endet der Lauf.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from .klickecho import LAUFZEIT, Variante, variante_aus
from .klickkarte import DIMENSIONEN
from .klicklauf import BEFUND, ERFASST, LAUF_GESTOERT, NICHT_ERFASST, Kombiergebnis
from .klickstrecke import FELDER_JS, streckenende
from .klickwache import Abbruch

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from .klickbedienung import Bedienung
    from .klickkarte import Klickkarte
    from .klicklauf import Klicklauf
    from .klicklesung import Leser, Vorlesung
    from .klicktor import Tor
    from .klickwache import Wache

GRUND_NICHT_BESUCHT = "nicht besucht"


class Gang(Protocol):
    """Was der Weiter-Schritt vom Lauf des Klick-Crawlers braucht."""

    seite: Page
    karte: Klickkarte
    tor: Tor
    lauf: Klicklauf
    wache: Wache
    leser: Leser
    bedienung: Bedienung
    frist_ms: int
    hoechste: int
    unberuehrt: bool

    def oeffne_neu(self) -> None:
        """Ein frischer Kontext mit geladener Startseite."""

    def waehle(
        self, dimension: str, wert: str, variante: Variante
    ) -> Kombiergebnis | None:
        """Klickt ``wert``, wenn nötig; sonst das Ergebnis, das den Weg beendet."""

    def zeit_um(self) -> bool:
        """Ob die Frist des Laufs abgelaufen ist."""

    def nicht_besucht(self, variante: Variante) -> Kombiergebnis:
        """Die Kombination als „nicht besucht: Zeitgrenze erreicht“."""

    def nach_zeitgrenze(self, abbruch: Abbruch) -> Abbruch | None:
        """Eine Sperre bei geschlossener Frist als ``zeitgrenze``; sonst ``None``."""


def fehlen(karte: Klickkarte, dimension: str) -> str:
    """Der Grund, wenn die Knöpfe einer Dimension fehlen."""
    selektor = karte.knoepfe[dimension].selektor
    return f"Knöpfe für {dimension} nicht gefunden ({selektor})"


def folgeklicks(
    gang: Gang, dimension: str, ziel: dict[str, str | None], vorab: Vorlesung
) -> list[Kombiergebnis]:
    """Klickt jede Option von ``dimension`` auf der Folgeseite und liest danach."""
    ergebnisse: list[Kombiergebnis] = []
    for wert in gang.leser.angebotene(dimension, gang.lauf.struktur):
        kombi = {**ziel, dimension: wert}
        variante = variante_aus(*(kombi[d] for d in DIMENSIONEN))
        unlesbar = gang.leser.unlesbar_in(kombi)
        if wert is None:
            ergebnis = Kombiergebnis(
                variante, NICHT_ERFASST, fehlen(gang.karte, dimension)
            )
        elif unlesbar is not None:
            ergebnis = Kombiergebnis(variante, NICHT_ERFASST, unlesbar)
        elif variante.laufzeit is None:
            grund = f"Laufzeit „{kombi[LAUFZEIT]}“ nicht lesbar"
            ergebnis = Kombiergebnis(variante, NICHT_ERFASST, grund)
        elif len(gang.lauf.ergebnisse) + len(ergebnisse) >= gang.hoechste:
            ergebnis = zu_viele(gang, variante)
        elif gang.zeit_um():
            ergebnis = gang.nicht_besucht(variante)
        else:
            ergebnis = _klicke_und_lies(gang, dimension, kombi, variante, vorab)
        auswahl = tuple(kombi[d] for d in DIMENSIONEN)
        ergebnisse.append(replace(ergebnis, auswahl=auswahl))
    return ergebnisse


def _klicke_und_lies(
    gang: Gang,
    dimension: str,
    kombi: dict[str, str | None],
    variante: Variante,
    vorab: Vorlesung,
) -> Kombiergebnis:
    """Ein Klick auf der Folgeseite (nur GET und HEAD gehen hinaus), dann die Lesung."""
    ergebnis = gang.waehle(dimension, str(kombi[dimension]), variante)
    if ergebnis is not None:
        return ergebnis
    pruefe_strecke(gang.seite)
    nach = gang.leser.folgelesung(vorab, kombi, dimension)
    return lies_kombination(gang, variante, kombi, nach, 0)


def lies_kombination(
    gang: Gang,
    variante: Variante,
    kombi: dict[str, str | None],
    vorab: Vorlesung,
    stelle: int,
) -> Kombiergebnis:
    """Liest die Kombination nach ``vorab``; erfasst oder Befund mit Beleg."""
    struktur = gang.lauf.struktur
    ergebnis = gang.leser.lies(variante, kombi, struktur, vorab=vorab, stelle=stelle)
    if ergebnis.status not in (ERFASST, BEFUND):
        return ergebnis
    return gang.leser.belege(ergebnis, variante, gang.lauf, gang.tor.uhr())


def zu_viele(gang: Gang, variante: Variante) -> Kombiergebnis:
    """Die Kombination jenseits der Höchstzahl als „nicht besucht“."""
    grund = f"{GRUND_NICHT_BESUCHT}: mehr als {gang.hoechste} Kombinationen"
    return Kombiergebnis(variante, NICHT_ERFASST, grund)


def pruefe_strecke(seite: Page) -> None:
    """Beendet den Lauf, wenn Adresse oder Seite Anmeldung, Checkout oder Zahlung
    zeigen."""
    ende = streckenende(seite.url, seite.evaluate(FELDER_JS))
    if ende is not None:
        raise Abbruch(LAUF_GESTOERT, f"Folgeseite zeigt {ende}")
