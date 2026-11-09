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

import contextlib
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
    from playwright.sync_api import FloatRect, Locator, Page

GERAET_SPEICHER, TARIF, LAUFZEIT = BILDFOLGE_SCHRITTE
PREIS = "preis"
GEWAEHLT = BILDFOLGE_SCHRITTE
SCHRITTE = (*GEWAEHLT, PREIS)
SCHRITT_JE_DIMENSION = dict(zip(DIMENSIONEN, GEWAEHLT, strict=True))
VOLLSTAENDIG = "vollstaendig"
UNVOLLSTAENDIG = "unvollstaendig"
HOECHSTE_OPTIONEN = 12
HOECHSTE_BREITE = 1280
HOECHSTE_HOEHE = 760
RAND = 10
OBEN_FREI = 120
BILDER_WARTEN_MS = 2000
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
        if schritt in karte.bildfolge_ohne:
            luecken[schritt] = karte.bildfolge_ohne[schritt]
        elif selektor is None:
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
    """Der Ausschnitt um alle Treffer von ``selektor``; sonst der Grund als Text.

    Liegen die Treffer weiter auseinander als das Fenster hoch ist (Gerätename oben,
    Speicherknöpfe weiter unten), rollt die Seite den Ausschnitt ins Fenster, unter
    eine feste Kopfleiste; Bilder, die noch laden, werden kurz abgewartet.
    """
    try:
        treffer = seite.locator(selektor)
        anzahl = min(treffer.count(), HOECHSTE_OPTIONEN)
        fenster = seite.viewport_size
        sichtbar = _boxen(treffer, anzahl, frist_ms)
        if sichtbar:
            treffer.nth(sichtbar[0][0]).scroll_into_view_if_needed(timeout=frist_ms)
            sichtbar = _boxen(treffer, anzahl, frist_ms)
        boxen = [box for _, box in sichtbar]
        rahmen = umfang(boxen, fenster["width"], fenster["height"]) if fenster else None
        if fenster and boxen and _schiebe(seite, boxen, fenster["height"]):
            boxen = [box for _, box in _boxen(treffer, anzahl, frist_ms)]
            rahmen = umfang(boxen, fenster["width"], fenster["height"])
        if rahmen is None:
            return GRUND_UNSICHTBAR
        _warte_auf_bilder(seite, rahmen)
        png = seite.screenshot(type="png", clip=rahmen, timeout=frist_ms)
    except PlaywrightFehler as fehler:
        return f"Ausschnitt fehlt: {kurz(fehler)}"
    return Folgebild(schritt, png)


def _boxen(treffer: Locator, anzahl: int, frist_ms: int) -> list[tuple[int, FloatRect]]:
    """Stelle und Box der sichtbaren unter den ersten ``anzahl`` Treffern; ein
    verborgener Treffer (Größe 0) zählt nicht und wird nie angescrollt."""
    boxen = []
    for stelle in range(anzahl):
        box = treffer.nth(stelle).bounding_box(timeout=frist_ms)
        if box is not None and box["width"] > 0 and box["height"] > 0:
            boxen.append((stelle, box))
    return boxen


def _schiebe(seite: Page, boxen: list[FloatRect], hoehe: int) -> bool:
    """Rollt die Seite, bis der Umfang der ``boxen`` unter einer festen Kopfleiste und
    über dem Fensterrand liegt (``OBEN_FREI``, ``RAND``); ist er höher als der Platz,
    beginnt er unter der Kopfleiste. ``True``, wenn gerollt wurde."""
    oben = min(b["y"] for b in boxen)
    unten = max(b["y"] + b["height"] for b in boxen)
    if unten - oben > hoehe - OBEN_FREI - RAND or oben < OBEN_FREI:
        schub = oben - OBEN_FREI
    elif unten + RAND > hoehe:
        schub = unten + RAND - hoehe
    else:
        return False
    if abs(schub) < 1:
        return False
    seite.evaluate("schub => window.scrollBy(0, schub)", schub)
    return True


_BILDER_LADEN = """async ([rahmen, frist]) => {
  const im_rahmen = (b) => b.width > 0
    && b.right > rahmen.x && b.left < rahmen.x + rahmen.width
    && b.bottom > rahmen.y && b.top < rahmen.y + rahmen.height;
  const offen = [...document.images].filter(
    (i) => !i.complete && im_rahmen(i.getBoundingClientRect()));
  const fertig = offen.map((i) => new Promise((ok) => {
    i.addEventListener("load", ok, {once: true});
    i.addEventListener("error", ok, {once: true});
  }));
  await Promise.race([Promise.all(fertig), new Promise((ok) => setTimeout(ok, frist))]);
}"""


def _warte_auf_bilder(seite: Page, rahmen: FloatRect) -> None:
    """Wartet höchstens ``BILDER_WARTEN_MS`` auf Bilder im Ausschnitt, die noch laden
    (träge Bilder), damit kein Platzhalter im Beleg steht; ein Fehler ändert nichts."""
    with contextlib.suppress(PlaywrightFehler):
        seite.evaluate(_BILDER_LADEN, [rahmen, BILDER_WARTEN_MS])


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
