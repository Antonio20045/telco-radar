"""Konfigurationsbild der Gegenprobe: Gerät, gewählte Optionen und Preis in einem Bild.

Abnahmekriterium 3 (Antonio, 21.11.2026): je angezeigtem Preis ein Screenshot der
Anbieterseite mit genau dieser Konfiguration. ``aufnehme`` sucht nach der Wahl auf der
offenen Seite je Merkmal (``MERKMALE``) das sichtbare Element mit dem Text aus dem
Bestandssatz (Modell, Speicher, Tarif, Ratenzahl) und den Preisbereich
(Skripte und die Regeln, was „gewählt“ heißt: ``gegenprobe_bild_js``).

Ein Merkmal steht nur dann in ``zeigt``, wenn (i) es die GEWÄHLTE Option ist (oder eine
Zusammenfassung der Wahl), beim Preis: der Preisbereich zeigt dieselben Beträge wie
der gelesene Text (``warte_auf_preis``, sonst „Preis“ fehlt); (ii) sein Rechteck ganz
im Ausschnitt liegt und kein Vorfahre mit ``overflow`` es beschneidet; (iii) an fünf
Punkten das Element selbst oder ein Kind oben liegt. Vor dem Bild werden fest stehende
und haftende Leisten, die weder Preis noch Auswahl enthalten, nur für unser Bild
ausgeblendet; zeigt die Seite vorher einen zweiten, abweichenden Monatspreis
(``WIDERSPRUCH``), steht „widersprüchlicher Preis“ in ``ohne``. Was fehlt, nennt
``Aufnahme.ohne`` (die Seite zeigt es als Lücke); ``bild_ganz`` und der Text „zeigt …“
lesen genau diese Liste.

Der Ausschnitt ist das Rechteck um Preisbereich (ein niedriger Preiskasten ganz,
Saturn/MediaMarkt; in einer seitenhohen Spalte nur die Anker, o2 und Telekom) und die
Kacheln der gewählten Optionen; höher als ``HOEHE_HOECHSTENS_PX`` verliert es das
fernste Merkmal. Wo die Auswahl auf einer anderen Seite steht (Vodafone, 1&1), legt
``stapel`` zwei Bilder untereinander. WebP, höchstens ``BREITE_PX`` breit.
"""

from __future__ import annotations

import io
import re
import time
from dataclasses import dataclass, field
from html import escape
from typing import TYPE_CHECKING, Any

from . import gegenprobe_bild_js as js
from .gegenprobe_browser import (
    Lesung,
    NichtPruefbar,
    mit_beleg,
    sichtbares_html,
    text_von,
)
from .gegenprobe_merkmale import (
    GERAET,
    MERKMALE,
    PREIS,
    RATEN,
    SPEICHER,
    TARIF,
    angaben,
    bloecke,
    nadeln,
)
from .gegenprobe_merkmale import modell_text as modell_text
from .gegenprobe_merkmale import tarif_kern as tarif_kern

if TYPE_CHECKING:
    from playwright.sync_api import FloatRect, Page

WIDERSPRUCH = "widersprüchlicher Preis"
ORDNUNG = (GERAET, SPEICHER, TARIF, RATEN, PREIS, WIDERSPRUCH)
HOEHE_HOECHSTENS_PX = 1_900
"""Höher wird ein Ausschnitt nicht; darüber fällt das fernste Merkmal heraus."""
PREISKASTEN_HOECHSTENS_PX = 1_000
"""Ein so niedriger Preisbereich kommt ganz ins Bild, ein höherer nur mit den Ankern."""
FENSTER_HOECHSTENS_PX = 2_000
RAND_PX = 12
KOPF_FREI_PX = 140
"""Platz über dem Ausschnitt (dort lag vor dem Ausblenden die Kopfleiste)."""
LEISTE_HOECHSTENS = 0.5
"""Fest stehende Elemente bis zu diesem Anteil des Fensters gelten als Leiste."""
BREITE_PX = 800
QUALITAET = 55
WARTE_MS = 400
PREIS_WARTEN_MS = 6_000
"""So lange wartet das Bild höchstens darauf, dass der Preisbereich die gelesenen
Beträge zeigt (o2 füllt ihn nach; Teil von ``ZEIT_JE_BUENDEL_S`` im Skript)."""
TAKT_MS = 250
GRUND_NICHTS = "Weder Preisbereich noch Auswahl auf der Seite gefunden"
_BETRAG = re.compile(r"\d{1,4}(?:\.\d{3})*,(?:\d{2}|[–-]{1,2})")


@dataclass
class Aufnahme:
    """Ein Bild der gewählten Konfiguration und was darin steht."""

    bild: bytes | None
    zeigt: list[str] = field(default_factory=list)
    ohne: list[str] = field(default_factory=list)
    grund: str | None = None
    """Warum es kein Bild gibt (dann ``bild`` None)."""
    befund: dict[str, str] = field(default_factory=dict)
    """Je Merkmal, warum es nicht als gezeigt zählt (für das Protokoll)."""


def erwartet(b: dict, nur: tuple[str, ...] = MERKMALE) -> list[str]:
    """Die Merkmale, die ein Bild dieses Bündels zeigen soll. Ohne Geräterate keine
    Raten: Saturn/MediaMarkt verkauft das Gerät einmalig und nennt keine Laufzeit auf
    der Seite (Schnappschuss 21.11.2026: kein „Monat“ im Text)."""
    return [m for m in ORDNUNG if m in nadeln(b, nur) or (m == PREIS and m in nur)]


def _vereinige(kaesten: list[dict]) -> dict:
    x = min(k["x"] for k in kaesten)
    y = min(k["y"] for k in kaesten)
    x2 = max(k["x"] + k["w"] for k in kaesten)
    y2 = max(k["y"] + k["h"] for k in kaesten)
    return {"x": x, "y": y, "w": x2 - x, "h": y2 - y}


def waehle_kaesten(gefunden: dict) -> tuple[dict | None, list[str]]:
    """Das Rechteck um Preis und Merkmale (höchstens ``HOEHE_HOECHSTENS_PX`` hoch)
    und die Merkmale darin; ohne Preis zählt die Mitte der Merkmale."""
    preis = gefunden.get("preis")
    merkmale = dict(gefunden.get("merkmale") or {})
    if preis is None and not merkmale:
        return None, []
    mitte = preis or _vereinige(list(merkmale.values()))
    bezug = mitte["y"] + mitte["h"] / 2
    while True:
        kaesten = ([preis] if preis else []) + list(merkmale.values())
        if not kaesten:
            return None, []
        rechteck = _vereinige(kaesten)
        if rechteck["h"] <= HOEHE_HOECHSTENS_PX or not merkmale:
            break
        fern = max(merkmale, key=lambda m: abs(merkmale[m]["y"] - bezug))
        merkmale.pop(fern)
    drin = sorted(merkmale, key=ORDNUNG.index) + ([PREIS] if preis else [])
    return rechteck, drin


def betraege(text: str) -> set[str]:
    """Die Euro-Beträge eines Texts („40,00“; „44,–“ als „44,00“)."""
    return {re.sub(r"[–-]+$", "00", b) for b in _BETRAG.findall(text or "")}


def preis_passt(im_bild: str | None, gelesen: str) -> bool:
    """Zeigt der Preisbereich Beträge, und stehen sie alle im gelesenen Text?"""
    eigene = betraege(im_bild or "")
    return bool(eigene) and (not gelesen or eigene <= betraege(gelesen))


def warte_auf_preis(seite: Page, gelesen: str, frist_ms: int = PREIS_WARTEN_MS) -> bool:
    """Wartet, bis der Preisbereich ``preis_passt``; höchstens ``frist_ms``."""
    ende = time.monotonic() + frist_ms / 1000
    while True:
        if preis_passt(seite.evaluate(js.PREISTEXT), gelesen):
            return True
        if time.monotonic() >= ende:
            return False
        seite.wait_for_timeout(TAKT_MS)


def gewaehlte(
    seite: Page, b: dict, anker: tuple[str, ...] | None, nur: tuple[str, ...] = MERKMALE
) -> dict[str, bool]:
    """Je gefundenem Merkmal: gilt es als gewählte Option (``js.SUCHE``)? Merkt sich
    die Elemente für ``aufnehme`` auf der Seite."""
    teile = str(b.get("id") or "").split("--")
    schluessel = teile[1] if len(teile) > 2 else ""
    return seite.evaluate(
        js.SUCHE,
        {
            "anker": list(anker or ()),
            "merkmale": angaben(b, nur),
            "bloecke": bloecke(schluessel, b),
            "preis_hoechstens": PREISKASTEN_HOECHSTENS_PX,
        },
    )


def aufnehme(
    seite: Page,
    b: dict,
    anker: tuple[str, ...] | None,
    nur: tuple[str, ...] = MERKMALE,
    gelesen: str = "",
) -> Aufnahme:
    """Bild der gewählten Konfiguration auf der offenen Seite (Modulkopf); ``gelesen``
    ist der Text, den die Gegenprobe eben las (der Preis im Bild muss ihm gleichen)."""
    from playwright.sync_api import Error as PlaywrightFehler

    soll = erwartet(b, nur)
    try:
        gewaehlte(seite, b, anker, nur)
        preis_ok = not anker or warte_auf_preis(seite, gelesen)
        widerspruch = seite.evaluate(js.WIDERSPRUCH, None) if anker else None
        rechteck, drin = waehle_kaesten(seite.evaluate(js.KAESTEN))
        if rechteck is None:
            return Aufnahme(None, [], soll, GRUND_NICHTS)
        png, befund = _fotografiere(seite, rechteck, drin, gelesen if anker else None)
    except PlaywrightFehler as fehler:
        grund = f"Bild nicht aufgenommen: {str(fehler).splitlines()[0][:120]}"
        return Aufnahme(None, [], soll, grund)
    zeigt = [
        m
        for m in soll
        if m in drin and befund.get(m) == "" and (m != PREIS or preis_ok)
    ]
    widerspruch = widerspruch or befund.get(WIDERSPRUCH)
    ohne = [m for m in soll if m not in zeigt] + ([WIDERSPRUCH] if widerspruch else [])
    if not preis_ok:
        befund[PREIS] = "Preis im Bild nicht wie gelesen"
    if widerspruch:
        befund[WIDERSPRUCH] = widerspruch
    return Aufnahme(
        klein(png),
        zeigt,
        ohne,
        None,
        {m: befund.get(m) or "nicht gefunden" for m in ohne},
    )


def _fotografiere(
    seite: Page, rechteck: dict, drin: list[str], gelesen: str | None
) -> tuple[bytes, dict]:
    """Leisten ausblenden, das Fenster nur wenn nötig so hoch wie das Rechteck (ein
    Größenwechsel lässt manche Seiten neu zeichnen), dorthin rollen, auf den Preis
    warten, neu messen, je Merkmal prüfen (``js.PRUEFE``), fotografieren; danach alles
    wie vorher."""
    alt = seite.viewport_size
    breite = alt["width"] if alt else 1440
    noetig = int(rechteck["h"]) + 4 * RAND_PX + KOPF_FREI_PX
    hoehe = alt["height"] if alt else 1000
    seite.evaluate(js.AUSBLENDEN, LEISTE_HOECHSTENS)
    if noetig > hoehe:
        hoehe = min(noetig, FENSTER_HOECHSTENS_PX)
        seite.set_viewport_size({"width": breite, "height": hoehe})
    try:
        ziel = max(0, rechteck["y"] - RAND_PX - KOPF_FREI_PX)
        seite.evaluate("(y) => window.scrollTo(0, y)", ziel)
        seite.wait_for_timeout(WARTE_MS)
        seite.evaluate(js.AUSBLENDEN, LEISTE_HOECHSTENS)
        preis_da = gelesen is None or warte_auf_preis(seite, gelesen)
        neu = seite.evaluate(js.KAESTEN)
        kaesten = [neu["preis"]] if neu.get("preis") and PREIS in drin else []
        kaesten += [k for m, k in neu["merkmale"].items() if m in drin]
        r = _vereinige(kaesten) if kaesten else rechteck
        oben = seite.evaluate("() => scrollY")
        x = max(0.0, r["x"] - RAND_PX)
        y = max(0.0, r["y"] - oben - RAND_PX)
        clip: FloatRect = {
            "x": x,
            "y": y,
            "width": min(r["w"] + 2 * RAND_PX, breite - x),
            "height": min(r["h"] + 2 * RAND_PX, hoehe - y),
        }
        befund = seite.evaluate(js.PRUEFE, clip)
        if gelesen is not None and (im_bild := seite.evaluate(js.WIDERSPRUCH, clip)):
            befund[WIDERSPRUCH] = im_bild
        if not preis_da:
            befund[PREIS] = "Preis im Bild nicht wie gelesen"
        return seite.screenshot(clip=clip), befund
    finally:
        seite.evaluate(js.WIEDER)
        if alt and alt != seite.viewport_size:
            seite.set_viewport_size(alt)


def klein(png: bytes) -> bytes:
    """PNG → WebP, höchstens ``BREITE_PX`` breit; ohne Pillow bleibt es PNG."""
    try:
        from PIL import Image
    except ImportError:
        return png
    bild: Any = Image.open(io.BytesIO(png)).convert("RGB")
    if bild.width > BREITE_PX:
        hoehe = round(bild.height * BREITE_PX / bild.width)
        bild = bild.resize((BREITE_PX, hoehe), Image.Resampling.LANCZOS)
    ausgabe = io.BytesIO()
    bild.save(ausgabe, "WEBP", quality=QUALITAET, method=6)
    return ausgabe.getvalue()


def stapel(oben: Aufnahme | None, unten: Aufnahme) -> Aufnahme:
    """Zwei Bilder untereinander (Auswahl der Produktseite über Tarif und Preis);
    ``zeigt`` ist beider Vereinigung. Fehlt ein Bild, bleibt das andere."""
    if oben is None or oben.bild is None:
        return _mit_fehlendem(unten, oben)
    if unten.bild is None:
        return _mit_fehlendem(oben, unten)
    try:
        from PIL import Image
    except ImportError:
        return unten
    a = Image.open(io.BytesIO(oben.bild)).convert("RGB")
    b = Image.open(io.BytesIO(unten.bild)).convert("RGB")
    breite = max(a.width, b.width)
    ganz = Image.new("RGB", (breite, a.height + RAND_PX + b.height), "white")
    ganz.paste(a, (0, 0))
    ganz.paste(b, (0, a.height + RAND_PX))
    ausgabe = io.BytesIO()
    ganz.save(ausgabe, "WEBP", quality=QUALITAET, method=6)
    zeigt = [m for m in ORDNUNG if m in oben.zeigt or m in unten.zeigt]
    soll = [m for m in ORDNUNG if m in zeigt or m in oben.ohne or m in unten.ohne]
    return Aufnahme(ausgabe.getvalue(), zeigt, [m for m in soll if m not in zeigt])


def _mit_fehlendem(da: Aufnahme, weg: Aufnahme | None) -> Aufnahme:
    """``da`` und die Merkmale, die nur das fehlende Bild hätte zeigen sollen."""
    if weg is None:
        return da
    ohne = [m for m in ORDNUNG if (m in da.ohne or m in weg.ohne + weg.zeigt)]
    return Aufnahme(da.bild, da.zeigt, [m for m in ohne if m not in da.zeigt], da.grund)


class Vorab(str):
    """Sichtbarer Text vor der Lesung (``Weg.waehle``) und, wo die Auswahl auf einer
    früheren Seite stand, deren Bild (``aufnahme``, ``stapel`` legt es oben an)."""

    aufnahme: Aufnahme | None = None

    @classmethod
    def mit(cls, text: str, aufnahme: Aufnahme | None) -> Vorab:
        """Text mit dem Bild der vorigen Seite."""
        neu = cls(text)
        neu.aufnahme = aufnahme
        return neu


def lesung(
    seite: Page,
    b: dict,
    anker: tuple[tuple[tuple[str, ...], ...], tuple[str, ...]],
    vorab: str | Exception,
    aufnehmen: bool,
) -> Lesung | Exception:
    """Text und Konfigurationsbild NACH der Wahl, oder warum sie nicht lesbar waren
    (``NichtPruefbar`` mit Adresse und Bild); ``anker`` sind die Text- und die
    Preisanker des Wegs. Der Besuch geht danach weiter."""
    from playwright.sync_api import Error as PlaywrightFehler

    text_anker, bild_anker = anker
    if isinstance(vorab, Exception):
        return mit_beleg(vorab, seite)
    try:
        text = vorab + "\n".join(text_von(seite, a) for a in text_anker)
        html = ""
        if aufnehmen:
            zeilen = "".join(f"<div>{escape(z)}</div>" for z in vorab.splitlines())
            html = "\n".join([zeilen, *(sichtbares_html(seite, a) for a in text_anker)])
    except PlaywrightFehler as fehler:
        return mit_beleg(NichtPruefbar(browserfehler(fehler)), seite)
    except NichtPruefbar as fehler:
        return mit_beleg(fehler, seite)
    vorher = vorab.aufnahme if isinstance(vorab, Vorab) else None
    bild = stapel(vorher, aufnehme(seite, b, bild_anker, gelesen=text))
    return Lesung(text, seite.url, bild.bild, bild.grund, html, bild.zeigt, bild.ohne)


def browserfehler(fehler: Exception) -> str:
    """Die erste Zeile eines Playwright-Fehlers als Grund."""
    return f"Browser: {str(fehler).splitlines()[0][:160]}"
