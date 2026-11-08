"""Bildfolge je Preisposition: ein Bild je Schritt des Klickwegs, nie ein fremdes.

Der Beleg einer Position zeigt nicht nur die Preiszahl, sondern den Weg dahin
(``klickbeleg.Beleg.bildfolge``): (1) ``geraet_speicher`` gewählt, (2) ``tarif``
gewählt, (3) ``laufzeit`` (Raten) gewählt, (4) ``preis`` mit Zuzahlung und Monatsrate.
Eine Methode für alle Anbieter, ohne Sonderlogik: Nachdem der Crawler alle Dimensionen
gewählt hat, schneidet ``lies_folge`` je Dimension aus der Seite den Ausschnitt, der
alle Knöpfe der Dimension umfasst (Selektor aus ``Klickkarte.knoepfe``); die gewählte
Option trägt die Markierung der Seite selbst. Das Bild entsteht nur, wenn die Seite
genau die Option der Position markiert (dieselbe Lesung wie ``Leser._abweichung``). Hat
die
Dimension keinen Knopf (fest, Adresse), gilt der Selektor aus ``Klickkarte.bildfolge``
(optional), sonst fehlt der Schritt mit Grund; eine Kachel ohne Markierung fehlt auch.
Das Bild des vierten Schritts ist der Screenshot des Preisbereichs, den der Beleg
ohnehin trägt.

Fail-closed: Ein Schritt ohne Bild bleibt in ``fehlt`` mit Grund, die Folge heißt dann
``unvollstaendig``; nichts wird mit dem Bild einer anderen Position gefüllt. Grenzen:
Ausschnitt höchstens ``HOECHSTE_BREITE`` × ``HOECHSTE_HOEHE`` Pixel, Datei höchstens
``HOECHSTE_BYTES``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klickecho import Variante
from .klickkarte import DIMENSIONEN, Klickkarte
from .klickkartenteile import BILDFOLGE_SCHRITTE
from .klickoptionen import lies_optionen
from .klicktext import Buendelwerte, Preiswerte, betraege_im_text
from .klicktor import kurz

if TYPE_CHECKING:
    from playwright.sync_api import FloatRect, Page

GERAET_SPEICHER, TARIF, LAUFZEIT = BILDFOLGE_SCHRITTE
PREIS = "preis"
GEWAEHLT = BILDFOLGE_SCHRITTE
SCHRITTE = (*GEWAEHLT, PREIS)
SCHRITT_JE_DIMENSION = dict(zip(DIMENSIONEN, GEWAEHLT, strict=True))
VOLLSTAENDIG = "vollstaendig"
UNVOLLSTAENDIG = "unvollstaendig"
HOECHSTE_OPTIONEN = 12
HOECHSTE_BREITE = 1280
HOECHSTE_HOEHE = 360
RAND = 10
HOECHSTE_BYTES = 150_000
GRUND_NICHT_AUFGENOMMEN = "nicht aufgenommen"
GRUND_OHNE_KNOPF = "Dimension ohne Knopf und ohne Selektor in der Karte"
GRUND_KACHEL = "Option ist eine Kachel ohne Markierung"
GRUND_UNSICHTBAR = "Optionen nicht sichtbar"
TEXT_OHNE_BETRAG = "Preisbereich der Anbieterseite nach der Wahl"


@dataclass(frozen=True)
class Folgebild:
    """Ein aufgenommener Schritt: sein Name und das PNG des Ausschnitts."""

    schritt: str
    png: bytes = field(repr=False)


def lies_folge(
    seite: Page,
    karte: Klickkarte,
    ziel: Mapping[str, str | None],
    frist_ms: int,
) -> tuple[dict[str, Folgebild], dict[str, str]]:
    """Die Bilder der drei gewählten Schritte und die Gründe der fehlenden.

    Ein Bild entsteht nur, wenn die Seite genau die Option ``ziel`` der Dimension
    markiert. Wirft nie.
    """
    bilder: dict[str, Folgebild] = {}
    luecken: dict[str, str] = {}
    for dimension, schritt in SCHRITT_JE_DIMENSION.items():
        knopf = karte.knoepfe[dimension]
        selektor = karte.bildfolge.get(schritt, knopf.selektor)
        if selektor is None:
            luecken[schritt] = GRUND_OHNE_KNOPF
        elif dimension == karte.kacheldimension:
            luecken[schritt] = GRUND_KACHEL
        else:
            grund = _gewaehlt_gegen(
                seite, karte, dimension, ziel[dimension], knopf.fest
            )
            ergebnis = grund or schnappe(seite, selektor, schritt, frist_ms)
            if isinstance(ergebnis, str):
                luecken[schritt] = ergebnis
            else:
                bilder[schritt] = ergebnis
    return bilder, luecken


def _gewaehlt_gegen(
    seite: Page, karte: Klickkarte, dimension: str, soll: str | None, fest: str | None
) -> str | None:
    """Der Grund, wenn die Seite nicht genau ``soll`` markiert; ``None`` bei Treffer
    (eine feste Dimension hat keine Markierung)."""
    if fest is not None:
        return None
    try:
        optionen = lies_optionen(seite, karte, dimension)
    except PlaywrightFehler as fehler:
        return f"Markierung nicht lesbar: {kurz(fehler)}"
    gewaehlt = [o.wert for o in optionen if o.gewaehlt]
    if gewaehlt == [soll]:
        return None
    return f"Seite markiert {gewaehlt or 'nichts'} statt {soll}"


def schnappe(
    seite: Page, selektor: str, schritt: str, frist_ms: int
) -> Folgebild | str:
    """Der Ausschnitt um alle Treffer von ``selektor``; sonst der Grund als Text."""
    try:
        treffer = seite.locator(selektor)
        boxen = []
        for stelle in range(min(treffer.count(), HOECHSTE_OPTIONEN)):
            if stelle == 0:
                treffer.nth(0).scroll_into_view_if_needed(timeout=frist_ms)
            box = treffer.nth(stelle).bounding_box(timeout=frist_ms)
            if box is not None and box["width"] > 0 and box["height"] > 0:
                boxen.append(box)
        fenster = seite.viewport_size
        rahmen = umfang(boxen, fenster["width"], fenster["height"]) if fenster else None
        if rahmen is None:
            return GRUND_UNSICHTBAR
        png = seite.screenshot(type="png", clip=rahmen, timeout=frist_ms)
    except PlaywrightFehler as fehler:
        return f"Ausschnitt fehlt: {kurz(fehler)}"
    return Folgebild(schritt, png)


def umfang(boxen: list[FloatRect], breite: int, hoehe: int) -> FloatRect | None:
    """Der Rahmen um alle ``boxen`` mit Rand, im Fenster und höchstens so groß wie
    ``HOECHSTE_BREITE`` × ``HOECHSTE_HOEHE``; ``None`` ohne sichtbare Box."""
    if not boxen:
        return None
    links = max(0.0, min(b["x"] for b in boxen) - RAND)
    oben = max(0.0, min(b["y"] for b in boxen) - RAND)
    rechts = min(float(breite), max(b["x"] + b["width"] for b in boxen) + RAND)
    unten = min(float(hoehe), max(b["y"] + b["height"] for b in boxen) + RAND)
    if rechts <= links or unten <= oben:
        return None
    return {
        "x": links,
        "y": oben,
        "width": min(rechts - links, float(HOECHSTE_BREITE)),
        "height": min(unten - oben, float(HOECHSTE_HOEHE)),
    }


def euro(betrag: float | None) -> str:
    """Ein Betrag deutsch mit Komma; ``nicht gelesen`` für eine Lücke."""
    if betrag is None:
        return "nicht gelesen"
    ganz, rest = f"{betrag:.2f}".split(".")
    gruppen = f"{int(ganz):,}".replace(",", ".")
    return f"{gruppen},{rest} €"


def schritttext(
    schritt: str,
    variante: Variante,
    modell: str | None = None,
    werte: Preiswerte | None = None,
    buendel: Buendelwerte | None = None,
    bildtext: str | None = None,
) -> str:
    """Was der Schritt zeigt, als Satz für die Seite; aus der Variante, nie geraten."""
    if schritt == GERAET_SPEICHER:
        teile = [t for t in (modell, variante.speicher) if t]
        return "Gerät und Speicher gewählt: " + " · ".join(teile)
    if schritt == TARIF:
        return f"Tarif gewählt: {variante.tarif}"
    if schritt == LAUFZEIT:
        return f"Laufzeit und Raten gewählt: {variante.laufzeit} Monate"
    return preistext(werte or Preiswerte(), buendel, bildtext)


def preistext(
    werte: Preiswerte, buendel: Buendelwerte | None, bildtext: str | None
) -> str:
    """Die Beträge, die im Bild des Preisbereichs stehen, mit ihrer Bedeutung.

    Gelesen sind Zuzahlung und Monatsrate des Geräts, bei Bündeln Einmalzahlung und
    Monatsbetrag. Zeigt die Seite stattdessen die Summe aus Gerät und Tarif (Zuzahlung
    plus Anschluss, Rate plus erster Tarifpreis), nennt der Text sie. Ein Betrag steht
    nur im Text, wenn ``bildtext`` (der sichtbare Text des Bildes) ihn enthält; ist
    keiner sicher, nennt der Text keine Zahl.
    """
    gezeigt = betraege_im_text(bildtext or "")
    zusammen = _gezeigt(
        gezeigt,
        ("einmalig", _einmalig(werte, buendel)),
        ("monatlich", _monatlich(werte, buendel)),
    )
    geraet = _gezeigt(
        gezeigt,
        ("Zuzahlung", werte.anzahlung),
        ("Monatsrate", werte.rate),
    )
    if geraet and geraet[-1].startswith("Monatsrate") and werte.ratenzahl is not None:
        raten = rf"(?:[x×]\s*{werte.ratenzahl}\b|\b{werte.ratenzahl}\s*Raten\b)"
        if re.search(raten, bildtext or ""):
            geraet[-1] += f" × {werte.ratenzahl}"
    teile = []
    if zusammen:
        teile.append(" · ".join(zusammen) + " (Gerät und Tarif zusammen)")
    teile.extend(geraet)
    if not teile:
        return TEXT_OHNE_BETRAG
    return "Im Bild: " + " · ".join(teile)


def _gezeigt(gezeigt: frozenset[int], *posten: tuple[str, float | None]) -> list[str]:
    """``Name Betrag`` je Posten, dessen Betrag im Bild steht."""
    return [
        f"{name} {euro(betrag)}"
        for name, betrag in posten
        if betrag is not None and round(betrag * 100) in gezeigt
    ]


def _plus(*summanden: float | None) -> float | None:
    """Die Summe; ``None``, sobald ein Summand nicht gelesen ist."""
    if any(s is None for s in summanden):
        return None
    return sum(s for s in summanden if s is not None)


def _einmalig(werte: Preiswerte, buendel: Buendelwerte | None) -> float | None:
    """Einmalbetrag von Gerät und Tarif: Bündelwert, sonst Zuzahlung plus Anschluss."""
    if buendel is not None and buendel.einmalzahlung is not None:
        return buendel.einmalzahlung
    return _plus(werte.anzahlung, werte.anschluss)


def _monatlich(werte: Preiswerte, buendel: Buendelwerte | None) -> float | None:
    """Monatsbetrag von Gerät und Tarif: Bündelwert, sonst Rate plus Tarifpreis."""
    if buendel is not None and buendel.buendelbetrag is not None:
        return buendel.buendelbetrag
    erste = [p.betrag for p in werte.tarifphasen or () if p.von_monat == 1]
    return _plus(werte.rate, erste[0] if erste else None)
