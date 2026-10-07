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
      parameter: {tarif: tarif}
    kanarie: {selektor: "#kanarie", enthaelt: Beispielhandy X}

``wert`` eines Knopfs nennt das Attribut mit dem Optionswert; ohne es gilt der
sichtbare Text. Pfade sind Punktpfade in die JSON-Antwort, Listenstellen als Zahl
(``tarif.phasen.0.betrag``). ``tarifphasen`` ist entweder ein einfacher Pfad auf einen
Monatspreis ohne Phasen oder eine Liste von Phasen mit den Feldnamen für ersten Monat,
letzten Monat und Betrag. Woran die Antwort ihre Variante nennt, ist Pflicht:
``variante`` mit Pfaden in die JSON-Antwort, ``parameter`` mit Namen der Parameter ihrer
Adresse oder beides, zusammen mindestens eine Dimension. Der Crawler nimmt eine Antwort
nur, wenn sie die gewählte Variante nennt.

Format 2 ergänzt; jedes Merkmal nur, weil die Erkundung vom 07.10.2026 es bei einem
Anbieter verlangt (Befunde je Anbieter):

- ``knoepfe.<dimension>.gewaehlt``: Marke je Dimension statt der einen der Karte
  (congstar: Speicher ``aria-checked``, Tarif und Laufzeit ``data-selected``; Telekom).
  ``knoepfe.gewaehlt`` bleibt der Standard und darf fehlen, wenn jede geklickte
  Dimension eine eigene Marke trägt.
- Marke als ``{passt: <CSS>}``: das Klickziel ist gewählt, wenn es auf den Selektor
  passt. So zeigt die Karte die DOM-Eigenschaft ``checked`` am Element (``:checked``),
  am Input im Label (``:has(input:checked)``, 1&1, congstar) oder am Input davor
  (``input:checked + label``, o2), ein Klassen-Token (``.-active``, freenet) und ein
  Attribut (``[aria-checked="true"]``).
- ``wert_in``: CSS-Selektor eines Kind-Elements, das den Wert trägt; geklickt wird
  weiter das Klickziel (congstar: ``aria-label`` des Inputs im Label).
- ``muster``: regulärer Ausdruck, dessen erste Gruppe der Wert ist (o2: Tarifname ohne
  den Preis, der mit dem Speicher wechselt; congstar: „36 mtl. Zahlungen“ → 36).
- ``fest``: eine Dimension ohne Knöpfe mit festem Wert (1&1: Laufzeit 36). Sie wird
  nie geklickt und nie an einer Marke geprüft.
- ``vorbereitung``: Liste von ``{klick, bis, pruefe}``; vor jeder Lesung muss das
  Element zu ``pruefe`` (ohne: zu ``klick``) auf den CSS-Selektor ``bis`` passen, sonst
  klickt der Crawler ``klick`` (congstar: Rückgabedeal-Schalter aus; 1&1: vorgewähltes
  Zubehör ab). Wird der Zustand nicht erreicht, ist der Lauf gestört.
- ``zusammenfassung.oeffnen`` und ``schliessen``: Dialog, der vor der Lesung geöffnet
  und danach geschlossen wird (Telekom „Preisübersicht anzeigen“).
- ``kanarie.enthaelt`` mit ``{modell}`` (Modellname aus dem Katalog, o2 und 1&1) und
  ``kanarie.attribut``: der Wert dieses Attributs statt des Texts (1&1 ``aria-label``).

Selektoren der Klickziele sind Playwright-Selektoren (``:text-matches`` und
``:has-text`` gehen); ``passt``, ``bis`` und ``wert_in`` sind reines CSS.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .klickkartenleser import Kartenleser
from .klickkartentypen import (
    DIMENSIONEN,
    GEWAEHLT,
    GRUND_FEHLT,
    GRUND_KEIN_TEXT,
    GRUND_KEINE_ZUORDNUNG,
    GRUND_MUSTER,
    GRUND_OHNE_VARIANTE,
    GRUND_UNBEKANNT,
    GRUND_YAML,
    PHASENFELD,
    PHASENTEILE,
    PLATZHALTER_MODELL,
    WERTFELDER,
    Antwortmuster,
    Auswahlmarke,
    Kanarie,
    Klickkarte,
    KlickkartenFehler,
    Knopf,
    Phasenpfad,
    Textlesung,
    Vorbereitung,
)

__all__ = [
    "DIMENSIONEN",
    "GEWAEHLT",
    "GRUND_FEHLT",
    "GRUND_KEINE_ZUORDNUNG",
    "GRUND_KEIN_TEXT",
    "GRUND_MUSTER",
    "GRUND_OHNE_VARIANTE",
    "GRUND_UNBEKANNT",
    "GRUND_YAML",
    "KOPFFELDER",
    "PHASENFELD",
    "PHASENTEILE",
    "PLATZHALTER_MODELL",
    "WERTFELDER",
    "Antwortmuster",
    "Auswahlmarke",
    "Kanarie",
    "KlickkartenFehler",
    "Klickkarte",
    "Knopf",
    "Phasenpfad",
    "Textlesung",
    "Vorbereitung",
    "klickkarte_aus_daten",
    "lade_klickkarte",
]

KOPFFELDER = (
    "anbieter",
    "knoepfe",
    "zusammenfassung",
    "antwort",
    "kanarie",
    "vorbereitung",
)


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
    leser = Kartenleser(quelle)
    daten = leser.zuordnung(roh, "", KOPFFELDER)
    knoepfe, gewaehlt = leser.knoepfe(daten.get("knoepfe"))
    textlesung = leser.textlesung(daten.get("zusammenfassung"))
    return Klickkarte(
        anbieter=leser.text(daten, "anbieter", ""),
        knoepfe=knoepfe,
        gewaehlt=gewaehlt,
        zusammenfassung=", ".join(textlesung.selektoren),
        antwort=leser.antwort(daten.get("antwort")),
        kanarie=leser.kanarie(daten.get("kanarie")),
        textlesung=textlesung,
        vorbereitung=leser.vorbereitung(daten.get("vorbereitung")),
    )
