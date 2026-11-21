"""Konfigurationsbild der Gegenprobe: Gerät, gewählte Optionen und Preis in einem Bild.

Abnahmekriterium 3 (Antonio, 21.11.2026): je angezeigtem Preis ein Screenshot der
Anbieterseite mit genau dieser Konfiguration. Der Preisbereich allein (bis 21.11.2026)
zeigt bei keinem Anbieter Gerät, Speicher und Tarif zusammen (Telekom: nur Beträge,
o2: Raten, aber kein Gerät). ``aufnehme`` sucht darum nach der Wahl auf der offenen
Seite je Merkmal (``MERKMALE``) das sichtbare Element, das es nennt (Text aus dem
Bestandssatz: Modell, Speicher, Tarif, Ratenzahl), nimmt je Merkmal das dem
Preisbereich nächste (darunter zählt der Abstand anderthalbfach: die Auswahl steht
meist über dem Preis) und fotografiert das Rechteck, das alle umschließt. Der
Preisbereich selbst ist das Rechteck um seine Anker (je Anker das tiefste Element im
kleinsten Element mit allen Ankern), nicht dessen Hülle: o2 und Telekom setzen den
Preiskasten in eine seitenhohe Spalte (Live-Prüfung 21.11.2026). Was nicht im
Bild steht, nennt ``Aufnahme.ohne`` (die Seite zeigt es als Lücke), nie stillschweigend.
Ist das Rechteck höher als ``HOEHE_HOECHSTENS_PX``, fällt das vom Preis fernste
Merkmal heraus (und steht in ``ohne``).

Wo die Auswahl auf einer anderen Seite steht als der Preis (Vodafone und 1&1: Speicher
und Raten auf der Produktseite, Tarif und Preis auf der Tarifauswahl), nimmt der Weg
auf beiden Seiten ein Bild auf, ``stapel`` legt sie untereinander. Klein im Release:
WebP, höchstens ``BREITE_PX`` breit, Qualität ``QUALITAET``.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from html import escape
from typing import TYPE_CHECKING, Any

from .gegenprobe_browser import (
    Lesung,
    NichtPruefbar,
    mit_beleg,
    sichtbares_html,
    speicher_aus_sku,
    text_von,
)

if TYPE_CHECKING:
    from playwright.sync_api import FloatRect, Page

GERAET, SPEICHER, TARIF, RATEN, PREIS = "Gerät", "Speicher", "Tarif", "Raten", "Preis"
MERKMALE = (GERAET, SPEICHER, TARIF, RATEN, PREIS)
"""Was ein Konfigurationsbild zeigen soll, in der Reihenfolge der Seite."""
HOEHE_HOECHSTENS_PX = 1_900
"""Höher wird ein Ausschnitt nicht; darüber fällt das fernste Merkmal heraus."""
FENSTER_HOECHSTENS_PX = 2_000
RAND_PX = 12
KOPF_FREI_PX = 140
"""So viel Platz bleibt über dem Ausschnitt frei: dort liegen fest stehende
Kopfleisten (Telekom, Vodafone), die sonst die oberste Auswahl verdecken."""
BREITE_PX = 800
QUALITAET = 55
WARTE_MS = 400
GRUND_NICHTS = "Weder Preisbereich noch Auswahl auf der Seite gefunden"

_SUCHE_JS = """(arg) => {
  const norm = s => (s || '').normalize('NFKC').toLowerCase()
    .replace(/[^a-z0-9äöüß]/g, '');
  const text = new Map();
  const alle = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (getComputedStyle(el).visibility === 'hidden') continue;
    text.set(el, norm(el.innerText));
    alle.push(el);
  }
  let preis = null, laenge = Infinity;
  const anker = (arg.anker || []).map(norm);
  if (anker.length) {
    for (const el of alle) {
      const t = text.get(el);
      if (t.length < laenge && anker.every(a => t.includes(a))) {
        preis = el;
        laenge = t.length;
      }
    }
  }
  const teile = [];
  if (preis) {
    const innen = alle.filter(el => preis.contains(el));
    for (const a of anker) {
      const hat = el => (text.get(el) || '').includes(a);
      const tief = innen.find(el => hat(el) && !Array.from(el.children).some(hat));
      if (tief) teile.push(tief);
    }
  }
  const oben = Math.min(...teile.map(el => el.getBoundingClientRect().top));
  const unten = Math.max(...teile.map(el => el.getBoundingClientRect().bottom));
  const mitte = teile.length ? (oben + unten) / 2 : 0;
  const gefunden = {};
  for (const [name, nadeln] of Object.entries(arg.merkmale)) {
    const n = nadeln.map(norm).filter(x => x);
    const hat = el => n.some(x => (text.get(el) || '').includes(x));
    let bestes = null, abstand = Infinity;
    for (const el of alle) {
      if (!hat(el) || Array.from(el.children).some(hat)) continue;
      const r = el.getBoundingClientRect();
      const mitte_el = r.top + r.height / 2;
      const d = mitte_el > mitte ? (mitte_el - mitte) * 1.5 : mitte - mitte_el;
      if (d < abstand) { bestes = el; abstand = d; }
    }
    if (bestes) gefunden[name] = bestes;
  }
  window.__gegenprobeBild = {preis: teile, gefunden};
  return true;
}"""

_KAESTEN_JS = """() => {
  const k = window.__gegenprobeBild || {gefunden: {}};
  const kasten = el => {
    if (!el || !el.isConnected) return null;
    const r = el.getBoundingClientRect();
    const oben = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    const frei = !!oben && (el.contains(oben) || oben.contains(el));
    return {x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height, frei};
  };
  const teile = (k.preis || []).map(kasten).filter(b => b);
  const x = Math.min(...teile.map(b => b.x)), y = Math.min(...teile.map(b => b.y));
  const preis = teile.length ? {
    x, y,
    w: Math.max(...teile.map(b => b.x + b.w)) - x,
    h: Math.max(...teile.map(b => b.y + b.h)) - y,
  } : null;
  const out = {preis, merkmale: {}};
  for (const [name, el] of Object.entries(k.gefunden)) {
    const b = kasten(el);
    if (b) out.merkmale[name] = b;
  }
  return out;
}"""


@dataclass
class Aufnahme:
    """Ein Bild der gewählten Konfiguration und was darin steht."""

    bild: bytes | None
    zeigt: list[str] = field(default_factory=list)
    ohne: list[str] = field(default_factory=list)
    grund: str | None = None
    """Warum es kein Bild gibt (dann ``bild`` None)."""


def modell_text(sku_id: str) -> str | None:
    """„iphone 17 pro“ aus ``apple-iphone-17-pro-256gb-…`` (ohne Marke und Speicher)."""
    vorne = re.split(r"-\d+(?:gb|tb)(?:-|$)", sku_id or "")[0]
    teile = [t for t in vorne.split("-") if t]
    if len(teile) > 1:
        teile = teile[1:]
    return " ".join(teile) or None


def tarif_kern(name: str) -> str | None:
    """Tarifname ohne Zusätze („O2 Mobile L mit 150 GB+ (24 Mon.)“: „O2 Mobile L“)."""
    kern = re.split(r"\s+mit\s+|\s*\(|\s*\+", name or "", maxsplit=1)[0].strip()
    return kern or None


def nadeln(b: dict, nur: tuple[str, ...] = MERKMALE) -> dict[str, list[str]]:
    """Je Merkmal die Texte, an denen die Seite es nennt (aus dem Bestandssatz)."""
    out: dict[str, list[str]] = {}
    modell = modell_text(str(b.get("sku_id") or ""))
    if modell:
        out[GERAET] = [modell]
    speicher = speicher_aus_sku(str(b.get("sku_id") or ""))
    if speicher:
        zahl, einheit = speicher.split()
        out[SPEICHER] = [speicher] + (
            [f"{int(zahl) * 1024} GB"] if einheit == "TB" else []
        )
    tarif = tarif_kern(str(b.get("tarif_name") or ""))
    if tarif:
        out[TARIF] = [tarif]
    n = b.get("laufzeit_monate")
    if n and (b.get("geraet_monatsrate") or b.get("buendel_monatlich") is not None):
        out[RATEN] = [
            f"x {n}",
            f"{n} Raten",
            f"Ratenzahlung: {n} Monate",
            f"Ratenzahlung Hardware: {n} Monate",
            f"{n} mtl. Zahlungen",
        ]
    return {k: v for k, v in out.items() if k in nur}


def erwartet(b: dict, nur: tuple[str, ...] = MERKMALE) -> list[str]:
    """Die Merkmale, die ein Bild dieses Bündels zeigen soll."""
    return [m for m in MERKMALE if m in nadeln(b, nur) or (m == PREIS and m in nur)]


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
    drin = sorted(merkmale, key=MERKMALE.index) + ([PREIS] if preis else [])
    return rechteck, drin


def aufnehme(
    seite: Page, b: dict, anker: tuple[str, ...] | None, nur: tuple[str, ...] = MERKMALE
) -> Aufnahme:
    """Bild der gewählten Konfiguration auf der offenen Seite (Modulkopf)."""
    from playwright.sync_api import Error as PlaywrightFehler

    soll = erwartet(b, nur)
    try:
        seite.evaluate(
            _SUCHE_JS, {"anker": list(anker or ()), "merkmale": nadeln(b, nur)}
        )
        rechteck, drin = waehle_kaesten(seite.evaluate(_KAESTEN_JS))
        if rechteck is None:
            return Aufnahme(None, [], soll, GRUND_NICHTS)
        png, drin = _fotografiere(seite, rechteck, drin)
    except PlaywrightFehler as fehler:
        grund = f"Bild nicht aufgenommen: {str(fehler).splitlines()[0][:120]}"
        return Aufnahme(None, [], soll, grund)
    zeigt = [m for m in soll if m in drin]
    return Aufnahme(klein(png), zeigt, [m for m in soll if m not in zeigt])


def _fotografiere(seite: Page, rechteck: dict, drin: list[str]) -> tuple[bytes, list]:
    """Fenster so hoch wie das Rechteck, dorthin rollen, neu messen (fest stehende
    Kästen wandern mit), fotografieren; danach wieder das alte Fenster."""
    alt = seite.viewport_size
    breite = alt["width"] if alt else 1440
    hoehe = min(int(rechteck["h"]) + 4 * RAND_PX + KOPF_FREI_PX, FENSTER_HOECHSTENS_PX)
    seite.set_viewport_size({"width": breite, "height": max(hoehe, 600)})
    try:
        ziel = max(0, rechteck["y"] - RAND_PX - KOPF_FREI_PX)
        seite.evaluate("(y) => window.scrollTo(0, y)", ziel)
        seite.wait_for_timeout(WARTE_MS)
        neu = seite.evaluate(_KAESTEN_JS)
        kaesten = [neu["preis"]] if neu.get("preis") and "Preis" in drin else []
        kaesten += [k for m, k in neu["merkmale"].items() if m in drin]
        r = _vereinige(kaesten) if kaesten else rechteck
        oben = seite.evaluate("() => scrollY")
        x = max(0.0, r["x"] - RAND_PX)
        y = max(0.0, r["y"] - oben - RAND_PX)
        clip: FloatRect = {
            "x": x,
            "y": y,
            "width": min(r["w"] + 2 * RAND_PX, breite - x),
            "height": min(r["h"] + 2 * RAND_PX, max(hoehe, 600) - y),
        }
        sichtbar = [
            m
            for m in drin
            if _im_bild(
                neu["preis"] if m == PREIS else neu["merkmale"].get(m), clip, oben
            )
        ]
        return seite.screenshot(clip=clip), sichtbar
    finally:
        if alt:
            seite.set_viewport_size(alt)


def _im_bild(kasten: dict | None, clip: FloatRect, oben: float) -> bool:
    """Liegt der Kasten (Seitenkoordinaten) wenigstens zur Hälfte im Ausschnitt und
    ist seine Mitte nicht verdeckt (``frei``: kein Banner, keine Leiste darüber)?"""
    if not kasten or kasten.get("frei") is False:
        return False
    y = kasten["y"] - oben
    innen = min(y + kasten["h"], clip["y"] + clip["height"]) - max(y, clip["y"])
    return innen >= kasten["h"] / 2


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
    zeigt = [m for m in MERKMALE if m in oben.zeigt or m in unten.zeigt]
    soll = [m for m in MERKMALE if m in zeigt or m in oben.ohne or m in unten.ohne]
    return Aufnahme(ausgabe.getvalue(), zeigt, [m for m in soll if m not in zeigt])


def _mit_fehlendem(da: Aufnahme, weg: Aufnahme | None) -> Aufnahme:
    """``da`` und die Merkmale, die nur das fehlende Bild hätte zeigen sollen."""
    if weg is None:
        return da
    ohne = [m for m in MERKMALE if (m in da.ohne or m in weg.ohne + weg.zeigt)]
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
    bild = stapel(vorher, aufnehme(seite, b, bild_anker))
    return Lesung(text, seite.url, bild.bild, bild.grund, html, bild.zeigt, bild.ohne)


def browserfehler(fehler: Exception) -> str:
    """Die erste Zeile eines Playwright-Fehlers als Grund."""
    return f"Browser: {str(fehler).splitlines()[0][:160]}"
