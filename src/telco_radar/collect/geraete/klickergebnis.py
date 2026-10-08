"""Ergebnisdatei des Klick-Tageslaufs und Lesestand der Rotation (Datenkonzept §8).

Je Anbieter schreibt der Tageslauf (``klicktageslauf``) ein JSON: Kopf mit Anbieter,
Datum, Karte, Vertragsform, Laufstatus und Zeitbudget, je Produktseite ihr Klicklauf
mit allen Kombinationen. Screenshots, HAR, Seitentext und Cookies stehen nie darin,
Adressen nur ohne Geheimnisse (``klickspur.ohne_geheimnisse``); vom Beleg bleiben
``beleg_id``, Seitenadresse und Zeitpunkt.

Der Laufstatus des Anbieters (``laufstatus``) ist ``gestoert``, sobald eine Seite
gestört endete (Bot-Schutz, Challenge, Kanarienwert, Strukturbruch); ``gelesen``, wenn
eine gelesene Seite mindestens eine Kombination ``erfasst`` hat; ``leer``, wenn Seiten
gelesen wurden, aber keine Kombination erfasst ist; ``nicht_gelesen``, wenn keine Seite
gelesen wurde (gesperrt, nicht besucht, Karte fehlt). Nur ``gelesen`` ersetzt im
Gerätelauf etwas (``analyze.klick_zusammenfuehrung``).

Im Repo liegen die Dateien unter ``data/state/klick/<schluessel>.json`` (``ORDNER``,
abgelegt von ``analyze.klick_ablage`` im eigenen Workflow), daneben der Lesestand
``STAND_DATEI`` (``lies_stand``): je Anbieter das Datum, an dem jede Produktseite
zuletzt ganz gelesen wurde (``ROTATION_GELESEN``; eine an der Zeitgrenze abgeschnittene
Seite liefert ihre besuchten Varianten, gilt aber nicht als gelesen). Der Tageslauf
ordnet danach. ``FRISCHEGRENZE_TAGE`` ist die Frist, in der jede Seite wieder gelesen
sein soll und in der eine Klick-Messung im Bestand Vorrang vor dem Adapter behält.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .klickbeleg import werte_als_json
from .klickdiagnose import diagnose_als_daten
from .klickkarte import DIMENSIONEN
from .klicklauf import (
    ERFASST,
    LAUF_GELESEN,
    LAUF_GESTOERT,
    LAUF_ZEITGRENZE,
    Klicklauf,
    Kombiergebnis,
)
from .klickspur import ohne_geheimnisse

if TYPE_CHECKING:
    from .klickziele import Seitenziel

log = logging.getLogger(__name__)

FORMAT = 1
FRISCHEGRENZE_TAGE = 3
LAUF_LEER = "leer"
LAUF_NICHT_GELESEN = "nicht_gelesen"
SEITE_NICHT_BESUCHT = "nicht_besucht"
GELESENE_SEITEN = frozenset({LAUF_GELESEN, LAUF_ZEITGRENZE})
ROTATION_GELESEN = frozenset({LAUF_GELESEN})
GRUND_NICHTS_ERFASST = "keine Kombination erfasst"
GRUND_KEINE_SEITE = "keine Seite gelesen"
STAND_FORMAT = 1
ORDNER = Path("data") / "state" / "klick"
STAND_DATEI = "klick_stand.json"


def kombination_als_daten(ergebnis: Kombiergebnis) -> dict:
    """Eine Kombination als JSON ohne Screenshot, Text und Belegdateien; eine Kachel
    des Weiter-Schritts mit ``diagnose`` (``klickdiagnose``), eine aus der Kachel
    bestätigte mit ``echo_quelle``."""
    beleg = ergebnis.beleg.beleg if ergebnis.beleg is not None else None
    url = ergebnis.antwort_url
    daten = {
        "auswahl": dict(zip(DIMENSIONEN, ergebnis.auswahl, strict=False)),
        "variante": asdict(ergebnis.variante),
        "status": ergebnis.status,
        "grund": ergebnis.grund,
        "werte": werte_als_json(ergebnis.werte),
        "buendel": None if ergebnis.buendel is None else asdict(ergebnis.buendel),
        "luecken": list(ergebnis.luecken),
        "befunde": [{"feld": b.feld, "grund": b.grund} for b in ergebnis.befunde],
        "antwort_url": None if url is None else ohne_geheimnisse(url),
        "beleg": None
        if beleg is None
        else {
            "beleg_id": beleg.beleg_id,
            "seite": ohne_geheimnisse(beleg.seite),
            "zeitpunkt": beleg.zeitpunkt,
        },
        "beleg_status": ergebnis.beleg_status,
    }
    if ergebnis.diagnose is not None:
        daten["diagnose"] = diagnose_als_daten(ergebnis.diagnose)
    if ergebnis.echo_quelle is not None:
        daten["echo_quelle"] = ergebnis.echo_quelle
    return daten


def seite_als_daten(ziel: Seitenziel, lauf: Klicklauf) -> dict:
    """Eine gelesene, gestörte oder gesperrte Produktseite mit ihren Kombinationen."""
    bilanz = lauf.struktur
    return {
        "geraet": ziel.geraet,
        "speicher_gb": ziel.speicher_gb,
        "adresse": ohne_geheimnisse(ziel.adresse),
        "status": lauf.status,
        "grund": lauf.grund,
        "http_status": lauf.http_status,
        "struktur": {
            **asdict(bilanz),
            "anteil_knoepfe": bilanz.anteil_knoepfe,
            "anteil_felder": bilanz.anteil_felder,
        },
        "verworfen": len(lauf.verworfen),
        "gescheitert": len(lauf.gescheitert),
        "kombinationen": [kombination_als_daten(e) for e in lauf.ergebnisse],
    }


def nicht_besucht(ziel: Seitenziel, grund: str) -> dict:
    """Eine Seite, die der Lauf nicht öffnete, mit Grund; nie „leer“."""
    return {
        "geraet": ziel.geraet,
        "speicher_gb": ziel.speicher_gb,
        "adresse": ohne_geheimnisse(ziel.adresse),
        "status": SEITE_NICHT_BESUCHT,
        "grund": grund,
        "kombinationen": [],
    }


def laufstatus(seiten: list[dict]) -> tuple[str, str | None]:
    """Status und Grund des Anbieters aus seinen Seiten (siehe Modulkopf)."""
    gestoert = next((s for s in seiten if s["status"] == LAUF_GESTOERT), None)
    if gestoert is not None:
        return LAUF_GESTOERT, f"{gestoert['adresse']}: {gestoert['grund']}"
    gelesen = [s for s in seiten if s["status"] in GELESENE_SEITEN]
    if not gelesen:
        erste = seiten[0] if seiten else None
        grund = GRUND_KEINE_SEITE if erste is None else f"{erste['grund']}"
        return LAUF_NICHT_GELESEN, grund
    erfasst = any(k["status"] == ERFASST for s in gelesen for k in s["kombinationen"])
    return (LAUF_GELESEN, None) if erfasst else (LAUF_LEER, GRUND_NICHTS_ERFASST)


def schreibe(pfad: Path, daten: dict) -> None:
    """Schreibt die Ergebnisdatei als UTF-8-JSON."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(daten, ensure_ascii=False, indent=1, sort_keys=True)
    pfad.write_text(text + "\n", encoding="utf-8")


def lies_ergebnisse(ordner: Path) -> tuple[list[dict], list[str]]:
    """Alle Ergebnisdateien unter ``ordner`` und die unlesbaren mit Grund.

    Artefakte liegen je Anbieter in einem Unterordner; gesucht wird darum rekursiv.
    Eine Datei ohne passendes ``format`` ist unlesbar, nicht leer; der Lesestand
    (``STAND_DATEI``) ist keine Ergebnisdatei.
    """
    daten: list[dict] = []
    unlesbar: list[str] = []
    if not ordner.is_dir():
        return daten, [f"{ordner}: kein Ordner"]
    for datei in sorted(ordner.rglob("*.json")):
        if datei.name == STAND_DATEI:
            continue
        try:
            inhalt = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as fehler:
            unlesbar.append(f"{datei.name}: {type(fehler).__name__}")
            continue
        if not isinstance(inhalt, dict) or inhalt.get("format") != FORMAT:
            unlesbar.append(f"{datei.name}: Format nicht {FORMAT}")
            continue
        daten.append(inhalt)
    for zeile in unlesbar:
        log.warning("Klick-Ergebnis unlesbar: %s", zeile)
    return daten, unlesbar


def lies_stand(pfad: Path) -> dict:
    """Der Lesestand; fehlt er oder ist er unlesbar, ein leerer Stand mit Vermerk."""
    leer = {"format": STAND_FORMAT, "seiten": {}}
    try:
        stand = json.loads(pfad.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return leer
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as fehler:
        log.warning("Klick-Stand %s unlesbar (%s): Rotation ohne Stand", pfad, fehler)
        return leer
    if not isinstance(stand, dict) or stand.get("format") != STAND_FORMAT:
        log.warning("Klick-Stand %s: Format nicht %s", pfad, STAND_FORMAT)
        return leer
    stand.setdefault("seiten", {})
    return stand
