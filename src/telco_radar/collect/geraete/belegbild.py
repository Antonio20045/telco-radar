"""Das Bild zum Preis: Ausschnitt der Anbieterseite als kleines WebP.

Der Klick-Crawler macht von jedem Preisbereich ein PNG
(``Kombiergebnis.screenshot_png``). Für die Seite „Belege“ wird es höchstens
``BREITE_MAX`` Pixel breit und als WebP so stark gepackt, dass der Preis lesbar bleibt
und die Datei unter ``ZIEL_BYTES`` liegt: erst sinkt die Qualität (``QUALITAETEN``),
reicht das nicht, wird das Bild schmaler (``SCHRITT_BREITE``), nie schmaler als
``BREITE_MIN``. Im Artefakt heißt die Datei
``<beleg_id>.webp`` (``zwischenname``); ihren endgültigen Namen mit Gerät und Anbieter
(``beleg_regeln.dateiname``) bekommt sie erst beim Veröffentlichen, wenn der Bestand
das Gerät kennt. Die Folgebilder der Bildfolge (``klickbildfolge``) gehen denselben Weg
mit denselben Grenzen: ``<beleg_id>_<schritt>.webp`` (``folgename``); den Schritt
``preis`` zeigt das Einzelbild.

Das ist nicht das beweissichere Belegpaket (``klickbeleg``, verlustfrei samt HAR): es
ist die Ansicht für Manager, kein Beweis vor Gericht. Kein Netz, kein LLM.

Scheitern ist nicht leer: ``speichere_bilder`` zählt, was es nicht schreiben konnte, und
protokolliert es; der Lauf geht weiter, das Bild fehlt dann auf der Seite als benannte
Lücke (CLAUDE.md Clean Code 5).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError, features

from .klicklauf import ERFASST, Klicklauf

log = logging.getLogger(__name__)

BREITE_MAX = 1280
BREITE_MIN = 480
SCHRITT_BREITE = 0.8
ZIEL_BYTES = 80 * 1024
QUALITAETEN = (80, 70, 60, 50, 40)
ORDNER = "belege"
"""Unterordner der Ausgabe des Tageslaufs (``klick/belege``), als Artefakt."""


def zwischenname(beleg_id: str) -> str:
    """Name der Datei im Artefakt des Klick-Jobs."""
    return f"{beleg_id}.webp"


def folgename(beleg_id: str, schritt: str) -> str:
    """Name der Datei eines Folgebilds im Artefakt: ``<beleg_id>_<schritt>.webp``."""
    return f"{beleg_id}_{schritt}.webp"


class BildFehler(ValueError):
    """Das Bild ließ sich nicht verkleinern (kein WebP in Pillow, kein Bild)."""


def verkleinere(png: bytes) -> bytes:
    """WebP, höchstens ``BREITE_MAX`` breit, möglichst unter ``ZIEL_BYTES``."""
    if not features.check("webp"):
        raise BildFehler("Pillow ohne WebP")
    try:
        with Image.open(io.BytesIO(png)) as roh:
            bild = roh.convert("RGB")
    except (OSError, UnidentifiedImageError) as fehler:
        raise BildFehler(f"kein Bild: {fehler}") from fehler
    if bild.width > BREITE_MAX:
        bild = bild.resize(
            (BREITE_MAX, max(1, round(bild.height * BREITE_MAX / bild.width))),
            Image.Resampling.LANCZOS,
        )
    letzte = b""
    while True:
        for qualitaet in QUALITAETEN:
            ziel = io.BytesIO()
            bild.save(ziel, "WEBP", quality=qualitaet, method=4)
            letzte = ziel.getvalue()
            if len(letzte) <= ZIEL_BYTES:
                return letzte
        breite = round(bild.width * SCHRITT_BREITE)
        if breite < BREITE_MIN:
            return letzte
        bild = bild.resize(
            (breite, max(1, round(bild.height * SCHRITT_BREITE))),
            Image.Resampling.LANCZOS,
        )


@dataclass
class Schreibbilanz:
    """Was ``speichere_bilder`` geschrieben hat und was nicht."""

    geschrieben: int = 0
    ohne_bild: int = 0
    fehler: int = 0
    folgebilder: int = 0


def speichere_bilder(lauf: Klicklauf, ordner: Path) -> Schreibbilanz:
    """Schreibt das Bild jeder erfassten Kombination mit Beleg nach ``ordner``."""
    bilanz = Schreibbilanz()
    for ergebnis in lauf.ergebnisse:
        if ergebnis.status != ERFASST:
            continue
        if ergebnis.beleg is None or ergebnis.screenshot_png is None:
            bilanz.ohne_bild += 1
            continue
        try:
            ziel = ordner / zwischenname(ergebnis.beleg.beleg.beleg_id)
            ordner.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(verkleinere(ergebnis.screenshot_png))
            bilanz.geschrieben += 1
        except (BildFehler, OSError, ValueError) as fehler:
            bilanz.fehler += 1
            log.warning("Belegbild nicht geschrieben (%s): %s", lauf.adresse, fehler)
            continue
        _speichere_folge(ergebnis.beleg, ordner, bilanz, lauf.adresse)
    return bilanz


def _speichere_folge(paket, ordner: Path, bilanz: Schreibbilanz, adresse: str) -> None:
    """Die Folgebilder eines Belegs neben das Einzelbild; ein Fehler lässt nur diesen
    Schritt aus (er fehlt dann im Artefakt, die Seite nennt ihn)."""
    kennung = paket.beleg.beleg_id
    for schritt in paket.beleg.bildfolge:
        daten = paket.folgebilder.get(schritt.datei)
        if daten is None:
            continue
        try:
            (ordner / folgename(kennung, schritt.schritt)).write_bytes(
                verkleinere(daten)
            )
            bilanz.folgebilder += 1
        except (BildFehler, OSError, ValueError) as fehler:
            bilanz.fehler += 1
            log.warning(
                "Folgebild %s nicht geschrieben (%s): %s",
                schritt.schritt,
                adresse,
                fehler,
            )
