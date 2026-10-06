"""Klick-Karte je Anbieter: welche Knöpfe der Klick-Crawler drückt und was er liest.

Eine Maschine für alle Anbieter (Datenkonzept Geräteradar, Abschnitt 8). Je Anbieter
gibt es nur diese Karte: Knöpfe für Speicher, Tarif und Ratenlaufzeit, die Marke der
gewählten Option, den Ort der Preiszusammenfassung, das Adressmuster der
mitzuschneidenden Antwort mit den Pfaden ihrer Werte und den Kanarienwert. Ändert ein
Anbieter seine Seite, ändert sich nur die Karte.

Eine unvollständige Karte endet nicht als leerer Lauf: jedes fehlende, leere oder
falsch geformte Pflichtfeld und jedes unbekannte Feld wirft ``KlickkartenFehler`` mit
der Stelle als Punktpfad. Dieses Modul ruft kein Netz und liest nur die eine Datei.

Format (YAML)::

    anbieter: Beispielanbieter
    knoepfe:
      speicher: {selektor: "#speicher button", wert: data-wert}
      tarif: {selektor: "#tarif button", wert: data-wert}
      laufzeit: {selektor: "#laufzeit button"}
      gewaehlt: {attribut: aria-pressed, wert: "true"}
    zusammenfassung: {selektor: "#preis"}
    antwort:
      url_muster: "/api/preis\\?"
      pfade:
        rate: preis.rate
        tarifphasen: {liste: tarif.phasen, von: ab, bis: bis, betrag: betrag}
      variante: {speicher: auswahl.speicher}
    kanarie: {selektor: "#kanarie", enthaelt: Beispielhandy X}

``wert`` eines Knopfs nennt das Attribut mit dem Optionswert; ohne es gilt der
sichtbare Text. Pfade sind Punktpfade in die JSON-Antwort, Listenstellen als Zahl
(``tarif.phasen.0.betrag``). ``tarifphasen`` ist entweder ein einfacher Pfad auf einen
Monatspreis ohne Phasen oder eine Liste von Phasen mit den Feldnamen für ersten Monat,
letzten Monat und Betrag. ``variante`` ist wahlweise: nennt die Antwort die Variante,
prüft der Crawler sie mit.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

DIMENSIONEN = ("speicher", "tarif", "laufzeit")
WERTFELDER = (
    "anzahlung",
    "rate",
    "ratenzahl",
    "tarifphasen",
    "tarifbindung",
    "anschluss",
    "volumen_gb",
)
PHASENFELD = "tarifphasen"
PHASENTEILE = ("liste", "von", "bis", "betrag")
GEWAEHLT = "gewaehlt"
KOPFFELDER = ("anbieter", "knoepfe", "zusammenfassung", "antwort", "kanarie")
GRUND_FEHLT = "Pflichtfeld fehlt oder ist leer"
GRUND_KEINE_ZUORDNUNG = "ist keine Zuordnung"
GRUND_KEIN_TEXT = "ist kein Text"
GRUND_UNBEKANNT = "unbekanntes Feld"
GRUND_MUSTER = "kein gültiger regulärer Ausdruck"
GRUND_YAML = "kein lesbares YAML"


class KlickkartenFehler(ValueError):
    """Die Karte ist unvollständig oder falsch geformt; ``feld`` nennt die Stelle."""

    def __init__(self, quelle: str, feld: str, grund: str) -> None:
        self.quelle = quelle
        self.feld = feld
        self.grund = grund
        stelle = f", Feld {feld}" if feld else ""
        super().__init__(f"Klick-Karte {quelle}{stelle}: {grund}")


@dataclass(frozen=True)
class Knopf:
    """Selektor der Optionsknöpfe einer Dimension; Wert aus Attribut oder Text."""

    selektor: str
    wert_attribut: str | None = None


@dataclass(frozen=True)
class Auswahlmarke:
    """Woran die Seite die gewählte Option zeigt: Attribut und sein Wert."""

    attribut: str
    wert: str


@dataclass(frozen=True)
class Phasenpfad:
    """Liste der Preisphasen in der Antwort und die Feldnamen je Phase."""

    liste: str
    von: str
    bis: str
    betrag: str


@dataclass(frozen=True)
class Antwortmuster:
    """Welche Antwort mitgeschnitten wird und wo ihre Werte stehen."""

    url_muster: re.Pattern[str]
    pfade: Mapping[str, str | Phasenpfad]
    variante: Mapping[str, str]

    def passt(self, url: str) -> bool:
        """Wahr, wenn ``url`` die mitzuschneidende Antwort ist."""
        return self.url_muster.search(url) is not None


@dataclass(frozen=True)
class Kanarie:
    """Ein Text, der an fester Stelle stehen muss, solange die Karte zur Seite passt."""

    selektor: str
    enthaelt: str


@dataclass(frozen=True)
class Klickkarte:
    """Die Klick-Karte eines Anbieters."""

    anbieter: str
    knoepfe: Mapping[str, Knopf]
    gewaehlt: Auswahlmarke
    zusammenfassung: str
    antwort: Antwortmuster
    kanarie: Kanarie


def lade_klickkarte(pfad: Path) -> Klickkarte:
    """Liest die Karte aus ``pfad``; eine kaputte Karte wirft ``KlickkartenFehler``."""
    quelle = str(pfad)
    try:
        roh = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    except yaml.YAMLError as fehler:
        erste_zeile = str(fehler).splitlines()[0] if str(fehler) else ""
        grund = f"{GRUND_YAML} ({erste_zeile})"
        raise KlickkartenFehler(quelle, "", grund) from fehler
    return klickkarte_aus_daten(roh, quelle)


def klickkarte_aus_daten(roh: object, quelle: str) -> Klickkarte:
    """Baut die Karte aus geladenen YAML-Daten; ``quelle`` steht in jedem Fehler."""
    leser = _Leser(quelle)
    daten = leser.zuordnung(roh, "", KOPFFELDER)
    knoepfe = leser.zuordnung(daten.get("knoepfe"), "knoepfe", (*DIMENSIONEN, GEWAEHLT))
    marke = leser.zuordnung(
        knoepfe.get(GEWAEHLT), "knoepfe.gewaehlt", ("attribut", "wert")
    )
    zusammenfassung = leser.zuordnung(
        daten.get("zusammenfassung"), "zusammenfassung", ("selektor",)
    )
    kanarie = leser.zuordnung(daten.get("kanarie"), "kanarie", ("selektor", "enthaelt"))
    return Klickkarte(
        anbieter=leser.text(daten, "anbieter", ""),
        knoepfe={d: _knopf(leser, knoepfe, d) for d in DIMENSIONEN},
        gewaehlt=Auswahlmarke(
            attribut=leser.text(marke, "attribut", "knoepfe.gewaehlt"),
            wert=leser.text(marke, "wert", "knoepfe.gewaehlt"),
        ),
        zusammenfassung=leser.text(zusammenfassung, "selektor", "zusammenfassung"),
        antwort=_antwort(leser, daten),
        kanarie=Kanarie(
            selektor=leser.text(kanarie, "selektor", "kanarie"),
            enthaelt=leser.text(kanarie, "enthaelt", "kanarie"),
        ),
    )


def _knopf(leser: _Leser, knoepfe: Mapping, dimension: str) -> Knopf:
    feld = f"knoepfe.{dimension}"
    daten = leser.zuordnung(knoepfe.get(dimension), feld, ("selektor", "wert"))
    return Knopf(
        selektor=leser.text(daten, "selektor", feld),
        wert_attribut=leser.wahlweise_text(daten, "wert", feld),
    )


def _antwort(leser: _Leser, daten: Mapping) -> Antwortmuster:
    antwort = leser.zuordnung(
        daten.get("antwort"), "antwort", ("url_muster", "pfade", "variante")
    )
    muster = leser.text(antwort, "url_muster", "antwort")
    try:
        url_muster = re.compile(muster)
    except re.error as fehler:
        grund = f"{GRUND_MUSTER} ({fehler})"
        raise KlickkartenFehler(leser.quelle, "antwort.url_muster", grund) from fehler
    pfade = leser.zuordnung(antwort.get("pfade"), "antwort.pfade", WERTFELDER)
    if not pfade:
        raise leser.fehler("antwort.pfade", GRUND_FEHLT)
    variante = antwort.get("variante")
    return Antwortmuster(
        url_muster=url_muster,
        pfade={feld: _pfad(leser, pfade, feld) for feld in pfade},
        variante=(
            {}
            if variante is None
            else {
                d: leser.text(variante, d, "antwort.variante")
                for d in leser.zuordnung(variante, "antwort.variante", DIMENSIONEN)
            }
        ),
    )


def _pfad(leser: _Leser, pfade: Mapping, feld: str) -> str | Phasenpfad:
    if feld != PHASENFELD or not isinstance(pfade.get(feld), Mapping):
        return leser.text(pfade, feld, "antwort.pfade")
    stelle = f"antwort.pfade.{feld}"
    teile = leser.zuordnung(pfade[feld], stelle, PHASENTEILE)
    liste, von, bis, betrag = (leser.text(teile, t, stelle) for t in PHASENTEILE)
    return Phasenpfad(liste=liste, von=von, bis=bis, betrag=betrag)


class _Leser:
    """Liest Felder der Roh-Daten und wirft mit Quelle und Punktpfad."""

    def __init__(self, quelle: str) -> None:
        self.quelle = quelle

    def fehler(self, feld: str, grund: str) -> KlickkartenFehler:
        return KlickkartenFehler(self.quelle, feld, grund)

    def zuordnung(self, wert: object, feld: str, erlaubt: tuple[str, ...]) -> Mapping:
        if wert is None:
            raise self.fehler(feld, GRUND_FEHLT)
        if not isinstance(wert, Mapping):
            raise self.fehler(feld, GRUND_KEINE_ZUORDNUNG)
        for schluessel in wert:
            if schluessel not in erlaubt:
                raise self.fehler(_stelle(feld, str(schluessel)), GRUND_UNBEKANNT)
        return wert

    def wahlweise_text(self, daten: Mapping, schluessel: str, feld: str) -> str | None:
        if daten.get(schluessel) is None:
            return None
        return self.text(daten, schluessel, feld)

    def text(self, daten: Mapping, schluessel: str, feld: str) -> str:
        stelle = _stelle(feld, schluessel)
        wert = daten.get(schluessel)
        if isinstance(wert, bool):
            return "true" if wert else "false"
        if isinstance(wert, int | float):
            return str(wert)
        if wert is not None and not isinstance(wert, str):
            raise self.fehler(stelle, GRUND_KEIN_TEXT)
        if wert is None or not wert.strip():
            raise self.fehler(stelle, GRUND_FEHLT)
        return wert.strip()


def _stelle(feld: str, schluessel: str) -> str:
    return f"{feld}.{schluessel}" if feld else schluessel
