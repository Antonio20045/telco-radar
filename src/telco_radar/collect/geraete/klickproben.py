"""Klick-Proben der Erkundung: was ein Klick auf eine andere Option auslöst.

Je Gruppe, die nach Speicher, Laufzeit oder Tarif aussieht (``klickinventar``),
höchstens ``HOECHSTE_GRUPPEN_JE_ART`` Gruppen je Art, klickt ``probiere`` höchstens
``HOECHSTE_KLICKS_JE_GRUPPE`` andere Optionen: sichtbar, nicht gesperrt, nicht gewählt,
keine Kauf- oder Anmeldeaktion, kein Link auf einen anderen Pfad oder in ein neues
Fenster. Nach jedem Klick wartet die Probe auf Ruhe und hält fest, welche Anfragen
kamen, welche €-Texte sich änderten (vorher, nachher) und ob die Wahl sichtbar
übernommen wurde: ``ja``, ``nein`` oder ``unbekannt``, wenn die Gruppe keine Marke der
Wahl zeigt oder das Element fehlt. Wechselt die Seite, endet die Probe dort. Vorher
lehnt ``lehne_einwilligung_ab`` eine Einwilligungsabfrage ab, wenn ein Knopf dafür
sichtbar ist (``einwilligungsknopf``, auch für den Klick-Crawler); gesucht wird nach
dem zugänglichen Namen, den ein ``aria-label`` stellt (1&1: „Ablehnen“ mit
``aria-label`` „Cookies ablehnen“). Jede Probe steht im Protokoll, bevor eine Störung
den Lauf beendet.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightFehler

from .klickinventar import (
    ARTEN,
    KLICKARTEN,
    KURZE_ARTEN,
    Gruppe,
    Inventar,
    preistexte,
    texte_von,
    zustand,
)
from .klickspur import Spur, als_daten, ohne_geheimnisse
from .klicktor import kurz

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

HOECHSTE_KLICKS_JE_GRUPPE = 2
HOECHSTE_GRUPPEN_JE_ART = 2
HOECHSTE_AENDERUNGEN = 100
KLICK_FRIST_MS = 5000
HOECHSTE_EINWILLIGUNGSKNOEPFE = 5
JA, NEIN, UNBEKANNT = "ja", "nein", "unbekannt"
AKTIONSWORT = re.compile(
    r"warenkorb|bestell|kaufen|weiter\b|anmeld|login|abschlie|zur kasse", re.I
)
EINWILLIGUNG_AB = re.compile(
    r"^\s*(?:alle\s+)?(?:cookies\s+)?ablehnen|nur\s+(?:notwendige|erforderliche)"
    r"|weiter\s+ohne"
    r"|verweigern|^\s*reject",
    re.I,
)


class Gang(Protocol):
    """Was eine Probe von der Seite braucht: Seite, Spur, Ruhe, Prüfung, Umleitung."""

    seite: Page
    spur: Spur

    def ruhe(self) -> bool:
        """Wartet auf Ruhe; wahr, wenn sie eintrat."""

    def pruefe(self) -> None:
        """Wirft ``Abbruch`` bei Bot-Schutz oder erreichter Zeitgrenze."""

    def umgeleitet(self) -> str | None:
        """Ziel einer Umleitung der Hauptseite, sonst ``None``."""


def einwilligungsknopf(seite: Page) -> Locator | None:
    """Der erste sichtbare Ablehnen-Knopf einer Einwilligungsabfrage, sonst ``None``."""
    knoepfe = seite.get_by_role("button", name=EINWILLIGUNG_AB)
    for stelle in range(min(knoepfe.count(), HOECHSTE_EINWILLIGUNGSKNOEPFE)):
        knopf = knoepfe.nth(stelle)
        if knopf.is_visible():
            return knopf
    return None


def lehne_einwilligung_ab(gang: Gang) -> dict:
    """Klickt den ersten sichtbaren Ablehnen-Knopf einer Einwilligungsabfrage."""
    knopf = einwilligungsknopf(gang.seite)
    if knopf is None:
        return {"geklickt": None, "grund": "kein Ablehnen-Knopf sichtbar"}
    text = knopf.inner_text().strip()
    marke = gang.spur.marke()
    try:
        knopf.click(timeout=KLICK_FRIST_MS)
    except PlaywrightFehler as fehler:
        return {"geklickt": None, "text": text, "fehler": kurz(fehler)}
    gang.pruefe()
    ruhe = gang.ruhe()
    anfragen = als_daten(gang.spur.seit(marke))
    return {"geklickt": text, "ruhe": ruhe, "anfragen": anfragen}


def probiere(gang: Gang, inventar: Inventar, protokoll: list[dict]) -> None:
    """Klickt Optionen der passenden Gruppen und schreibt jede Probe ins Protokoll."""
    for gruppe in waehle_gruppen(inventar):
        for stelle, wert in ziele(gruppe, inventar)[:HOECHSTE_KLICKS_JE_GRUPPE]:
            gang.pruefe()
            probe = _probe(gang, gruppe, inventar.elemente[stelle], wert, protokoll)
            if probe["navigiert"] is not None or probe["umleitung"] is not None:
                return


def waehle_gruppen(inventar: Inventar) -> list[Gruppe]:
    """Je Klick-Art die ersten Gruppen mit mindestens einem Klickziel."""
    gewaehlt: list[Gruppe] = []
    for art in KLICKARTEN:
        passend = [g for g in inventar.gruppen if g.art == art and ziele(g, inventar)]
        gewaehlt += passend[:HOECHSTE_GRUPPEN_JE_ART]
    return gewaehlt


def ziele(gruppe: Gruppe, inventar: Inventar) -> list[tuple[int, str | None]]:
    """Stelle des Elements und, bei einem Select, der Wert jeder klickbaren Option."""
    if gruppe.select:
        stelle = gruppe.elemente[0]
        optionen = inventar.elemente[stelle]["optionen"] or []
        return [
            (stelle, o["wert"])
            for o in optionen
            if not o["gewaehlt"] and not o["deaktiviert"]
        ]
    muster = ARTEN[gruppe.art]
    seite = urlsplit(inventar.adresse)
    aus: list[tuple[int, str | None]] = []
    for stelle in gruppe.elemente:
        e = inventar.elemente[stelle]
        text = e["text"] or ""
        knapp, ganz = texte_von(e)
        pruefe = knapp if gruppe.art in KURZE_ARTEN else ganz
        if (
            e["sichtbar"]
            and not e["deaktiviert"]
            and e["gewaehlt"] is None
            and e["typ"] != "submit"
            and e["ziel"] in (None, "_self")
            and not AKTIONSWORT.search(text)
            and muster.search(pruefe)
            and _gleicher_pfad(e["href"], seite.path)
        ):
            aus.append((stelle, None))
    return aus


def unterschiede(vorher: dict[str, str], nachher: dict[str, str]) -> list[dict]:
    """Je Pfad, dessen €-Text sich änderte, kam oder ging: vorher und nachher."""
    aus = []
    for pfad in dict.fromkeys([*vorher, *nachher]):
        alt, neu = vorher.get(pfad), nachher.get(pfad)
        if alt != neu:
            aus.append({"pfad": pfad, "vorher": alt, "nachher": neu})
    return aus[:HOECHSTE_AENDERUNGEN]


def _probe(
    gang: Gang, gruppe: Gruppe, element: dict, wert: str | None, protokoll: list[dict]
) -> dict:
    seite = gang.seite
    vorher, adresse, marke = preistexte(seite), seite.url, gang.spur.marke()
    probe: dict = {
        "gruppe": gruppe.nummer,
        "art": gruppe.art,
        "pfad": element["pfad"],
        "text": element["text"],
        "wert": wert,
        "fehler": None,
        "navigiert": None,
        "umleitung": None,
    }
    protokoll.append(probe)
    ort = seite.locator(element["pfad"]).first
    try:
        if wert is None:
            ort.click(timeout=KLICK_FRIST_MS)
        else:
            ort.select_option(value=wert, timeout=KLICK_FRIST_MS)
    except PlaywrightFehler as fehler:
        probe["fehler"] = kurz(fehler)
    try:
        gang.pruefe()
        probe["ruhe"] = gang.ruhe()
    finally:
        probe["anfragen"] = als_daten(gang.spur.seit(marke))
    umleitung = gang.umgeleitet()
    probe["umleitung"] = ohne_geheimnisse(umleitung) if umleitung else None
    if seite.url != adresse:
        probe["navigiert"] = ohne_geheimnisse(seite.url)
        return probe
    probe["preise_geaendert"] = unterschiede(vorher, preistexte(seite))
    jetzt = zustand(seite, element["pfad"])
    probe["marke_nachher"] = None if jetzt is None else jetzt["gewaehlt"]
    probe["uebernommen"] = _uebernommen(gruppe, element, wert, jetzt)
    return probe


def _uebernommen(
    gruppe: Gruppe, element: dict, wert: str | None, jetzt: dict | None
) -> str:
    if jetzt is None:
        return UNBEKANNT
    if wert is not None:
        return JA if jetzt["wert"] == wert else NEIN
    if jetzt["gewaehlt"]:
        return JA
    return NEIN if gruppe.mit_marke else UNBEKANNT


def _gleicher_pfad(href: str | None, pfad: str) -> bool:
    if not href:
        return True
    ziel = urlsplit(href)
    return ziel.scheme not in ("http", "https") or ziel.path == pfad
