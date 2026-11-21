"""Je Anbieter eine Zeile: angezeigte Preise in 7 Tagen gegengeprüft und mit Bild.

Die Zahlen stehen fertig in der Bilanz der Gegenprobe
(``data/state/gegenprobe/bilanz/<datum>.json``, ``gegenprobe_bilanz``: ``angezeigt``,
``im_fenster``, ``mit_bild``); hier stehen nur Lesen und Text (Vertrag
``report-rechnet-nur``, Clean Code 1). Gelesen wird die jüngste Bilanz bis zum
Messtag der Seite; ist sie älter, trägt jede Zeile „Stand vom TT.MM.“. Fehlt die
Bilanz oder ein Feld, steht die Lücke mit Namen da, nie eine 0.
"""

from __future__ import annotations

from pathlib import Path

from ..gegenprobe_bilanz import juengste
from ..gegenprobe_zeile import GegenprobeFehler

ORDNER = Path("gegenprobe") / "bilanz"
"""Die Bilanzen unter ``data/state`` (``gegenprobe_bilanz.BILANZ_ORDNER``)."""
REIHENFOLGE = ("Vodafone", "Telekom", "o2", "1&1", "congstar")
SATZ = "{name}: {im} von {von} in {tage} Tagen gegengeprüft · {bild} mit Bild"
SATZ_OHNE_BILDZAHL = "{name}: {im} von {von} in {tage} Tagen gegengeprüft"
FEHLT = "Gegenprobe: noch keine Bilanz"
UNLESBAR = "Gegenprobe: Bilanz unlesbar ({grund})"
BILD_TITEL = "Bild mit Gerät, Speicher, Tarif, Raten und Preis"


def _zahl(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _zeile(schluessel: str, e: dict, tage: int) -> dict:
    """Eine Zeile; fehlt ``im_fenster`` oder ``angezeigt``, ist die Bilanz unlesbar
    (``KeyError``), fehlt nur ``mit_bild`` (ältere Bilanz), entfällt die Bildzahl."""
    name = str(e.get("name") or schluessel)
    im, von, bild = int(e["im_fenster"]), int(e["angezeigt"]), e.get("mit_bild")
    werte = {"name": name, "im": _zahl(im), "von": _zahl(von), "tage": tage}
    if bild is None:
        satz = SATZ_OHNE_BILDZAHL.format(**werte)
    else:
        satz = SATZ.format(**werte, bild=_zahl(int(bild)))
    return {
        "name": name,
        "schluessel": schluessel,
        "satz": satz,
        "im_fenster": im,
        "angezeigt": von,
        "mit_bild": bild,
    }


def _rang(zeile: dict) -> tuple:
    name = zeile["name"]
    return (REIHENFOLGE.index(name) if name in REIHENFOLGE else len(REIHENFOLGE), name)


def stand(state_dir: Path, stichtag: str = "") -> dict:
    """``{"zeilen": [...], "datum": iso, "stand": "Stand vom TT.MM." | "", "fehlt":
    Text | ""}`` aus der jüngsten Bilanz bis ``stichtag`` (Modulkopf)."""
    leer = {"zeilen": [], "datum": "", "stand": "", "titel": BILD_TITEL}
    try:
        gefunden = juengste(state_dir / ORDNER, stichtag)
        if gefunden is None:
            return {**leer, "fehlt": FEHLT}
        datum, daten = gefunden
        tage = int(daten["fenster_tage"])
        zeilen = sorted(
            (_zeile(s, e, tage) for s, e in (daten.get("anbieter") or {}).items()),
            key=_rang,
        )
    except (GegenprobeFehler, ValueError, KeyError, TypeError, AttributeError) as f:
        grund = f"{type(f).__name__}: {f}"[:120]
        return {**leer, "fehlt": UNLESBAR.format(grund=grund)}
    alt = bool(stichtag) and datum != stichtag
    stand_text = f"Stand vom {datum[8:10]}.{datum[5:7]}." if alt else ""
    return {**leer, "zeilen": zeilen, "datum": datum, "stand": stand_text, "fehlt": ""}
