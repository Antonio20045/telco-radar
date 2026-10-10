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
- ``andere_farbe``: CSS-Selektor; ein Klickziel, das darauf passt, gibt es nur in einer
  anderen Farbe. Die Karte klickt keine Farbe, die Kombination heißt ``nicht_erfasst``,
  nie ``nicht_angeboten`` (congstar: ``aria-label`` „512 GB nicht vorhanden“).
- ``vorbereitung``: Liste von ``{klick, bis, pruefe}``; vor jeder Lesung muss das
  Element zu ``pruefe`` (ohne: zu ``klick``) auf den CSS-Selektor ``bis`` passen, sonst
  klickt der Crawler ``klick`` (congstar: Rückgabedeal-Schalter aus; 1&1: vorgewähltes
  Zubehör ab). Wird der Zustand nicht erreicht, ist der Lauf gestört.
- ``zusammenfassung.oeffnen`` und ``schliessen``: Dialog, der vor der Lesung geöffnet
  und danach geschlossen wird (Telekom „Preisübersicht anzeigen“).
- ``kanarie.enthaelt`` mit ``{modell}`` (Modellname aus dem Katalog, o2 und 1&1) und
  ``kanarie.attribut``: der Wert dieses Attributs statt des Texts (1&1 ``aria-label``).

Zweite Lesung (Stufe 2 von Format 2):

- ``antwort`` als Liste von Quellen; je Wertfeld zählt die erste mit Wert. Je Quelle
  genau eines von ``url_muster``, ``skript`` (CSS eines Skripts mit JSON: o2
  ``script#pageValue``, Telekom), ``global`` (Name oder Liste globaler Variablen,
  Pfade beginnen mit dem Namen: 1&1 ``hwdVariantsPrices``) und ``seitenwerte: true``
  (Pfade sind Namen aus ``seite``: Telekom ohne ``/v2/details``). ``laden: true``: die
  Antwort kommt beim Laden und gilt für jede Kombination (congstar, Vodafone);
  ``start: true``: die Quelle gilt nur bis zum ersten Klick (o2, der Startzustand
  steht nur im Skript); ``erkennung``: unter Antworten derselben Adresse die mit einem
  Wert an diesem Pfad (congstar: drei GraphQL-Antworten; Vodafone: dieselbe als xhr
  und fetch); ``segment``: Muster, dessen erste Gruppe in der Antwortadresse Base64
  mit ``name=wert;…`` ist, als weitere Parameter (o2 ``/configuration/<base64>``).
- Pfade (``klickpfad``) mit Filtern ``[feld=wert]``, ``*`` und Platzhaltern
  ``{speicher}``, ``{tarif}``, ``{laufzeit}`` (geklickte Werte), ``{modell}`` und
  Seitenwerten (o2 ``paymentOptions[selected=true]``, congstar
  ``variants[id={plan}]``, Vodafone ``atomics[capacity.sortValue={speicher}]``, 1&1
  ``product-{farbe}-{speicher}``). Ein Pfad darf ``{pfad, einheit, muster}`` sein:
  ``einheit: cent`` (1&1) oder ``mb`` (o2), ``muster`` nimmt die erste Gruppe (o2
  „24xhigh“); ``parameter`` ebenso als ``{name, muster}``. Volumen -1 heißt
  unbegrenzt (o2); Markup in Varianten fällt weg (o2 „O<sub>2</sub>“).
- ``seite``: benannte Seitenwerte ``{selektor, attribut, parameter, muster}``, ohne
  ``selektor`` aus der Seitenadresse (1&1 ``size``, freenet ``ds``), sonst etwa aus
  dem Warenkorb-Link (congstar ``planId``). Heißt ein Seitenwert wie eine Dimension,
  ist er das Echo „Seite zeigt“; jeder ist Platzhalter.
- ``antwort.platzhalter``: benannte Pfade in dieselbe Antwort; ihr Wert ist in
  ``pfade`` und ``variante`` dieser Quelle ein weiterer Platzhalter (Telekom
  ``/v2/details``: drei Anzahlungsstufen je Laufzeit, der Plan folgt aus Laufzeit und
  der Anzahlung der Seite, die Rate aus dem Plan).
- ``zusammenfassung.selektor`` als Liste von Bereichen und ``ohne`` mit Ausschlüssen
  (Telekom: Tarif- und Zahlungsblock ohne Werbeblock); ``zusammenfassung.muster`` je
  Wertfeld ein regulärer Ausdruck oder ``{muster, selektor}`` mit eigenem Fundort
  (o2 „Gerät mtl. (36 Raten)“, 1&1 „44 , 99 €/Monat“, Vodafone „… € einmal“ und
  Ratenzahl im gewählten Label).

Stufe 3 von Format 2:

- ``knoepfe.<dimension>.adressen: {selektor, attribut, parameter}``: die Optionen sind
  eigene Seiten (Telekom ``tariffId``, freenet Bündel je Tarif ``ts``, 1&1
  ``chosenTariff``). Der Crawler liest auf der Startseite die Adressen aus ``attribut``
  (Standard ``href``) der Elemente zu ``selektor``; der Parameter ``parameter`` ist der
  Optionswert. Er lädt jede Adresse über das Tor (robots.txt, Crawl-delay) und klickt
  dort die übrigen Dimensionen. Adressen werden nie zusammengesetzt oder hochgezählt;
  ein anderer Host, ein fehlender Parameter oder robots.txt machen die Option
  ``nicht_erfasst`` mit Grund (``klickadressen``). Höchstens eine Dimension; das Echo
  „Seite zeigt“ kommt aus einem gleichnamigen Seitenwert oder der zweiten Lesung.
- ``vertragsform: ein_vertrag`` (1&1, freenet; Standard ``tarif_plus_ratenkauf``):
  die Wertfelder ``buendelbetrag`` und ``einmalzahlung`` in ``antwort.pfade`` und
  ``zusammenfassung.muster``; ``rate`` und ``ratenzahl`` entfallen planmäßig, sind
  keine Lücke und dort verboten. Der Beleg trägt sie ab Version 2 (``klickbeleg``).

Stufe 4 von Format 2 (1&1, Erkundung 07.10.2026, Commit c8ce1f77, Seiten 3 und 4):

- ``weiter: {selektor, text, kacheln}``: Die Optionen der Dimension ``kacheln`` gibt
  es erst nach einem Klick in die Bestellstrecke (1&1: 24 oder „24+12“ Monate nach
  „Weiter zur Tarifauswahl“), dort als Kacheln nebeneinander. Je Kombination der
  übrigen Dimensionen wählt der Crawler sie auf der Startseite, liest dort Seitenwerte
  und zweite Lesung, klickt den einen Weiter-Knopf und liest auf der Folgeseite jede
  Kachel: ``knoepfe.<kacheln>`` trifft die Kacheln (Wert wie bei Knöpfen, keine Marke,
  nie geklickt), die Zusammenfassung ist die Kachel selbst (einziger Bereich gleich
  dem Selektor der Kacheln, Textmuster ohne eigenen Selektor). Jede weitere
  Kombination beginnt in einem frischen Kontext; die Regeln stehen in ``klickweiter``.
  Schließt ``adressen`` und jeden zweiten Klick (``oeffnen``, ``schliessen``) aus.
- ``weiter: {selektor, text, klicken}`` (Vodafone, Erkundung 10.10.2026, Zweig
  klick-erkundung d969c6e1): statt Kacheln zu lesen, klickt der Crawler die Optionen
  der Dimension ``klicken`` auf der Folgeseite einzeln (Knopf mit Selektor und Marke
  wie auf einer Startseite) und liest nach jedem Klick Quellen und Zusammenfassung neu
  (``klickfolgeklick``). Genau eins von ``kacheln`` und ``klicken``.

Selektoren der Klickziele sind Playwright-Selektoren (``:text-matches`` und
``:has-text`` gehen); ``passt``, ``bis`` und ``wert_in`` sind reines CSS.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .klickkartenleser import Kartenleser
from .klickkartentypen import (
    BUENDELFELDER,
    DIMENSIONEN,
    EIN_VERTRAG,
    GEWAEHLT,
    GRUND_FEHLT,
    GRUND_KEIN_TEXT,
    GRUND_KEINE_ZUORDNUNG,
    GRUND_MUSTER,
    GRUND_OHNE_VARIANTE,
    GRUND_UNBEKANNT,
    GRUND_VERTRAGSFORM,
    GRUND_YAML,
    PHASENFELD,
    PHASENTEILE,
    PLATZHALTER_MODELL,
    SUMMENFELD,
    VERTRAGSFORMEN,
    WERTFELDER,
    Adressen,
    Antwortmuster,
    Auswahlmarke,
    Kanarie,
    Klickkarte,
    KlickkartenFehler,
    Knopf,
    Phasenpfad,
    Seitenwert,
    Textlesung,
    Textmuster,
    Vorbereitung,
    Weiterschritt,
    Wertpfad,
)
from .klickquellenleser import lies_quellen, lies_seite, pruefe_felder

__all__ = [
    "Adressen",
    "BUENDELFELDER",
    "DIMENSIONEN",
    "EIN_VERTRAG",
    "VERTRAGSFORMEN",
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
    "Seitenwert",
    "Textlesung",
    "Textmuster",
    "Vorbereitung",
    "Weiterschritt",
    "Wertpfad",
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
    "seite",
    "vertragsform",
    "weiter",
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
    roh_weiter = daten.get("weiter")
    kacheln = roh_weiter.get("kacheln") if isinstance(roh_weiter, dict) else None
    knoepfe, gewaehlt = leser.knoepfe(daten.get("knoepfe"), kacheln)
    textlesung = leser.textlesung(daten.get("zusammenfassung"))
    vertragsform = leser.wahlweise_text(daten, "vertragsform", "")
    if vertragsform is None:
        vertragsform = VERTRAGSFORMEN[0]
    if vertragsform not in VERTRAGSFORMEN:
        raise leser.fehler("vertragsform", f"{GRUND_VERTRAGSFORM} {vertragsform}")
    ein_vertrag = vertragsform == EIN_VERTRAG
    seite = lies_seite(leser, daten.get("seite"))
    quellen = lies_quellen(leser, daten.get("antwort"), seite)
    summe = SUMMENFELD in textlesung.muster and any(
        SUMMENFELD in q.pfade for q in quellen
    )
    ort = "zusammenfassung.muster"
    pruefe_felder(leser, textlesung.muster, ort, ein_vertrag, summe)
    liste = isinstance(daten.get("antwort"), list)
    for stelle, antwort in enumerate(quellen):
        ort = f"antwort.{stelle}.pfade" if liste else "antwort.pfade"
        pruefe_felder(leser, antwort.pfade, ort, ein_vertrag, summe)
    return Klickkarte(
        anbieter=leser.text(daten, "anbieter", ""),
        knoepfe=knoepfe,
        gewaehlt=gewaehlt,
        zusammenfassung=", ".join(textlesung.selektoren),
        antwort=quellen[0],
        kanarie=leser.kanarie(daten.get("kanarie")),
        textlesung=textlesung,
        vorbereitung=leser.vorbereitung(daten.get("vorbereitung")),
        quellen=quellen,
        seite=seite,
        vertragsform=vertragsform,
        weiter=leser.weiter(roh_weiter, knoepfe, textlesung),
    )
