"""Werkzeuge der Gegenprobe im Browser; die Wege je Anbieter: ``gegenprobe_wege``.

Ein Weg öffnet die Seite, die der Bestand als Quelle nennt (``quelle_url``), wählt wie
ein Kunde Speicher, Zahlweise und Tarif per Klick auf den sichtbaren Text und gibt
den ``innerText`` des Preisbereichs zurück, dazu ein Bild davon. Den Preisbereich
findet ``bereich`` über seine Beschriftungen (kleinstes sichtbares Element, das alle
Anker enthält), nicht über Klassennamen, die die Seiten bei jedem Bau neu würfeln.

Harte Regel 4: ehrliche Kennung, keine Tarnung. Eine Einwilligungsabfrage wird
abgelehnt (der sichtbare Ablehnen-Knopf), eine JavaScript-Prüfung (202) darf der
Browser durchlaufen; 401/403/429 oder ein Captcha enden als ``Gesperrt`` und werden
nicht umgangen. robots.txt prüft der Aufrufer (``scripts/gegenprobe.py``).
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import ElementHandle, Page, ViewportSize

log = logging.getLogger(__name__)

FENSTER: ViewportSize = {"width": 1440, "height": 1000}
SPRACHE = "de-DE"
LADEFRIST_MS = 45_000
RUHEFRIST_MS = 15_000
NACH_KLICK_MS = 2_000
NACH_LADEN_MS = 3_000
KLICKFRIST_MS = 8_000
BILD_HOECHSTENS_PX = 1_800
BILD_QUALITAET = 70
SPERRSTATUS = (401, 403, 429)
EINWILLIGUNG_AB = re.compile(
    r"^\s*(?:alles?\s+)?(?:cookies\s+)?ablehnen|nur\s+(?:notwendige|erforderliche)"
    r"|weiter\s+ohne|verweigern|^\s*reject",
    re.I,
)

_BEREICH_JS = """(anker) => {
  const klein = anker.map(a => a.toLowerCase());
  let bestes = null, laenge = Infinity;
  for (const el of document.querySelectorAll('body *')) {
    const t = (el.innerText || '').toLowerCase();
    if (t.length < laenge && klein.every(a => t.includes(a))) {
      const box = el.getBoundingClientRect();
      if (box.width > 0 && box.height > 0) { bestes = el; laenge = t.length; }
    }
  }
  return bestes;
}"""


_SICHTBAR_JS = """(el) => {
  const kopie = (quelle) => {
    if (quelle.nodeType === Node.TEXT_NODE) return document.createTextNode(quelle.data);
    if (quelle.nodeType !== Node.ELEMENT_NODE) return null;
    const weg = ['SCRIPT', 'STYLE', 'IMG', 'NOSCRIPT', 'IFRAME', 'svg'];
    if (weg.includes(quelle.tagName)) return null;
    const stil = getComputedStyle(quelle);
    if (stil.display === 'none' || stil.visibility === 'hidden') return null;
    const art = stil.display.startsWith('inline') ? 'span' : 'div';
    const neu = document.createElement(art);
    for (const kind of quelle.childNodes) {
      const k = kopie(kind);
      if (k) neu.appendChild(k);
    }
    return neu;
  };
  return kopie(el).outerHTML;
}"""


class Gesperrt(RuntimeError):
    """Der Anbieter hat den Abruf abgelehnt (Bot-Schutz); nicht umgehen."""

    seite: str = ""
    """Die Adresse, die der Browser zuletzt zeigte (``mit_beleg``)."""
    bild: bytes | None = None
    """Bild des Fensters beim Scheitern (``mit_beleg``)."""


class NichtPruefbar(RuntimeError):
    """Der Kundenweg kam nicht bis zum Preis; die Nachricht nennt den Grund."""

    seite: str = ""
    """Die Adresse, die der Browser zuletzt zeigte (``mit_beleg``)."""
    bild: bytes | None = None
    """Bild des Fensters beim Scheitern (``mit_beleg``)."""


def mit_beleg(fehler: Exception, seite: Page) -> Exception:
    """Hängt an ``Gesperrt``/``NichtPruefbar`` einmal Adresse und Bild des Fensters,
    damit „nicht prüfbar“ zeigt, was der Browser sah (21.11.2026: 169 leere Zeilen).
    Ohne geladene Seite (``about:blank``) bleibt beides leer."""
    from playwright.sync_api import Error as PlaywrightFehler

    if not isinstance(fehler, (Gesperrt, NichtPruefbar)) or fehler.seite:
        return fehler
    try:
        if not seite.url.startswith("http"):
            return fehler
        fehler.seite = seite.url
        fehler.bild = als_webp(seite.screenshot(timeout=KLICKFRIST_MS))
    except PlaywrightFehler as problem:
        log.info("Gegenprobe: kein Bild zum Fehler %s: %s", fehler, problem)
    return fehler


@dataclass
class Lesung:
    """Was der Browser gesehen hat: Text des Preisbereichs, Bild, geöffnete Adresse."""

    text: str
    seite: str
    bild: bytes | None = None
    bild_fehlt: str | None = None
    html: str = ""
    """Sichtbares HTML der Textbereiche (nur mit ``aufnehmen``, für Fixtures)."""
    bild_zeigt: list[str] | None = None
    """Was das Bild zeigt (``gegenprobe_bild.MERKMALE``); None: nicht geprüft."""
    bild_ohne: list[str] | None = None
    """Was das Bild zeigen sollte, aber nicht zeigt."""


def speicher_aus_sku(sku_id: str) -> str | None:
    """„256 GB“ bzw. „1 TB“ aus einer SKU wie ``apple-iphone-17-256gb-schwarz``."""
    treffer = re.search(r"-(\d+)(gb|tb)(?:-|$)", sku_id)
    if not treffer:
        return None
    zahl, einheit = int(treffer.group(1)), treffer.group(2)
    if einheit == "gb" and zahl >= 1024 and zahl % 1024 == 0:
        return f"{zahl // 1024} TB"
    return f"{zahl} {einheit.upper()}"


def oeffne(seite: Page, url: str) -> None:
    """Lädt ``url`` und wartet auf Ruhe; wirft ``Gesperrt`` bei Sperre oder Captcha."""
    antwort = seite.goto(url, wait_until="domcontentloaded", timeout=LADEFRIST_MS)
    status = antwort.status if antwort is not None else 0
    if status in SPERRSTATUS:
        raise Gesperrt(f"HTTP {status}")
    if status >= 400:
        raise NichtPruefbar(f"Seite antwortet mit HTTP {status}")
    ruhe(seite)
    if "captcha" in seite.url.lower() or seite.locator("iframe[src*=captcha]").count():
        raise Gesperrt("Captcha")
    lehne_einwilligung_ab(seite)


def ruhe(seite: Page) -> None:
    """Wartet auf Netzruhe (höchstens ``RUHEFRIST_MS``) und ``NACH_LADEN_MS`` dazu."""
    from playwright.sync_api import Error as PlaywrightFehler

    try:
        seite.wait_for_load_state("networkidle", timeout=RUHEFRIST_MS)
    except PlaywrightFehler:
        log.info("Gegenprobe: %s wird nicht ruhig, lese trotzdem", seite.url)
    seite.wait_for_timeout(NACH_LADEN_MS)


def lehne_einwilligung_ab(seite: Page) -> None:
    """Klickt den ersten sichtbaren Ablehnen-Knopf einer Einwilligungsabfrage."""
    knoepfe = seite.get_by_role("button", name=EINWILLIGUNG_AB)
    for stelle in range(min(knoepfe.count(), 5)):
        knopf = knoepfe.nth(stelle)
        if knopf.is_visible():
            knopf.click(timeout=KLICKFRIST_MS)
            seite.wait_for_timeout(NACH_KLICK_MS)
            return


def klicke(seite: Page, ziel: Any, was: str) -> None:
    """Klickt den ersten sichtbaren Treffer von ``ziel`` (Locator); sonst NichtPruefbar.

    Eine spät eingeblendete Einwilligungsabfrage wird vorher abgelehnt."""
    lehne_einwilligung_ab(seite)
    for stelle in range(min(ziel.count(), 10)):
        kandidat = ziel.nth(stelle)
        if kandidat.is_visible():
            if not kandidat.is_enabled():
                raise NichtPruefbar(f"Auswahl auf der Seite gesperrt: {was}")
            kandidat.click(timeout=KLICKFRIST_MS)
            seite.wait_for_timeout(NACH_KLICK_MS)
            return
    raise NichtPruefbar(f"Auswahl nicht gefunden: {was}")


def bereich(seite: Page, anker: tuple[str, ...]) -> ElementHandle:
    """Das kleinste sichtbare Element, dessen Text alle ``anker`` enthält."""
    griff = seite.evaluate_handle(_BEREICH_JS, list(anker))
    element = griff.as_element()
    if element is None:
        raise NichtPruefbar("Preisbereich nicht gefunden: " + ", ".join(anker))
    return element


def text_von(seite: Page, anker: tuple[str, ...]) -> str:
    """Der sichtbare Text (``innerText``) des Bereichs mit diesen Ankern."""
    return str(bereich(seite, anker).evaluate("e => e.innerText"))


def sichtbares_html(seite: Page, anker: tuple[str, ...]) -> str:
    """Der Bereich als schlichtes HTML nur aus sichtbaren Knoten (für Test-Fixtures):
    ohne Attribute, Skripte und Bilder; Block- und Inline-Elemente bleiben als div/span,
    damit ``innerText`` dieselben Zeilen ergibt."""
    return str(bereich(seite, anker).evaluate(_SICHTBAR_JS))


def bild_von(seite: Page, anker: tuple[str, ...]) -> tuple[bytes | None, str | None]:
    """Ein WebP des Bereichs (höchstens ``BILD_HOECHSTENS_PX`` hoch) oder der Grund."""
    from playwright.sync_api import Error as PlaywrightFehler

    try:
        element = bereich(seite, anker)
        element.scroll_into_view_if_needed(timeout=KLICKFRIST_MS)
        box = element.bounding_box()
        if box is None:
            return None, "Preisbereich ohne Fläche"
        png = seite.screenshot(
            clip={
                "x": box["x"],
                "y": box["y"],
                "width": box["width"],
                "height": min(box["height"], BILD_HOECHSTENS_PX),
            }
        )
    except (PlaywrightFehler, NichtPruefbar) as fehler:
        return None, f"Bild nicht aufgenommen: {str(fehler)[:120]}"
    return als_webp(png), None


def als_webp(png: bytes) -> bytes:
    """PNG → WebP (kleiner im Release); ohne Pillow bleibt es PNG."""
    try:
        from PIL import Image
    except ImportError:
        return png
    ausgabe = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").save(
        ausgabe, "WEBP", quality=BILD_QUALITAET
    )
    return ausgabe.getvalue()
