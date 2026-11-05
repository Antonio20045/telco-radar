"""Belegbilder neben dem Preis: aus dem Manifest zur Vorlagenfunktion ``belege_fuer``.

Gelesen wird allein ``data/state/belege_manifest.json`` (``beleg_manifest``),
geschrieben von ``scripts/belege_manifest.py`` aus den Release-Anhängen. Kein Netz, kein
LLM; ein Bild wird erst vom Browser geladen, wenn der Leser „Belege“ aufklappt. Fehlt
die Datei oder ein Bild, erscheint nichts. Eine kaputte Datei ist ein benannter Ausfall
(Regel 6).

Der Schlüssel eines Bilds ist ``(geraet_id, anbieter_id)`` = ``(m.schluessel,
anbieter_schluessel(Anbietername))`` der Preiszeile; beide Teile des Bilds kommen
aus dem Dateinamen, nie aus Titeltexten. Neueste Bilder zuerst, höchstens eins je Tag
(``beleg_manifest`` führt Tag und Monat zusammen).

Angezeigt werden die Belege der letzten ``ANZEIGE_TAGE`` Tage und dazu höchstens die
letzten ``ANZEIGE_GROSS_ANZAHL`` älteren großen Änderungen; die 90 Tage Aufbewahrung
sind keine Anzeige. Hat das Manifest einen Störungsvermerk (Geräte-Lauf konnte es nicht
erneuern), nennt die Seite ihn als Ausfall „Belegbilder“.

Je Preiszeile (Modell × Anbieter × Tarif, ``zeilenbeleg``) gilt dasselbe Bild: das
jüngste Bild des Paares (Modell, Anbieter). Der Messweg lichtet je Paar nur die
günstigste Konfiguration ab (``scripts/belege_veroeffentlichen.py``); das Bild
trägt keinen Tarif im Namen. Die Zeile sagt das (``HINWEIS_PAAR``), statt ein Bild
als Beleg genau ihres Tarifs auszugeben. Eine Zeile ohne Bild nennt den Grund
(``GRUND_*``); ``quote`` zählt dieselben Zeilen mit derselben Funktion (Clean Code 1).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from ..beleg_manifest import MANIFEST_NAME, Beleg, BelegManifestFehler, lies_manifest
from ..beleg_regeln import (
    ANZEIGE_GROSS_ANZAHL,
    ANZEIGE_TAGE,
    anbieter_schluessel,
    ist_anzeige_neu,
)
from .ausfall import Ausfall
from .geraete_preisstand import anzeige as preis_anzeige

TEIL = "Belegbilder"
HINWEIS_PAAR = (
    "Der Messlauf lichtet je Gerät und Anbieter die günstigste Konfiguration ab; "
    "bei einem anderen Tarif kann das Bild einen anderen Tarif zeigen."
)
GRUND_KLICK = (
    "Ohne Beleg: der Preis wurde im Klick-Lauf gelesen, aber zu diesem Gerät und "
    "Anbieter liegt kein Screenshot der letzten {tage} Tage vor (Bild nicht "
    "aufgenommen, nicht hochgeladen oder abgelaufen)."
)
GRUND_LISTE = (
    "Ohne Beleg: der Preis stammt aus der Anbieterliste oder einer Schnittstelle, "
    "nicht aus dem Klick-Lauf; nur dort entsteht ein Screenshot."
)
GRUND_MANIFEST = (
    "Ohne Beleg: die Liste der Belegbilder konnte nicht gelesen werden "
    "(siehe Ausfall „Belegbilder“)."
)


def _heute(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def sortiert_je_preis(
    belege: list[Beleg], heute: date | None
) -> dict[tuple[str, str], list[dict]]:
    """Angezeigte Belege je ``(geraet_id, anbieter_id)``, neueste zuerst.

    Alle der letzten ``ANZEIGE_TAGE`` Tage, dazu höchstens ``ANZEIGE_GROSS_ANZAHL``
    ältere große Änderungen. Was nicht mehr aufbewahrt wird (``Beleg.sichtbar``), fällt
    ganz heraus. Ohne ``heute`` (kein Bericht) bleibt es bei dem, was das Manifest schon
    gefiltert hat.
    """
    je_preis: dict[tuple[str, str], list[dict]] = {}
    aeltere_grosse: dict[tuple[str, str], int] = {}
    for beleg in sorted(belege, key=lambda b: b.datum, reverse=True):
        schluessel = (beleg.geraet_id, beleg.anbieter_id)
        if heute is not None:
            if not beleg.sichtbar(heute):
                continue
            if not ist_anzeige_neu(beleg.datum, heute):
                if not beleg.gross or aeltere_grosse.get(schluessel, 0) >= (
                    ANZEIGE_GROSS_ANZAHL
                ):
                    continue
                aeltere_grosse[schluessel] = aeltere_grosse.get(schluessel, 0) + 1
        je_preis.setdefault(schluessel, []).append(
            {"datum": beleg.datum.isoformat(), "gross": beleg.gross, "url": beleg.url}
        )
    return je_preis


def zeilenbeleg_fuer(
    belege_fuer: Callable[[str, str], list[dict]], manifest_ok: bool = True
) -> Callable[[str, dict], dict]:
    """Baut ``zeilenbeleg(modell_id, karte)``: Bild oder Grund einer Preiszeile.

    Ergebnis: ``beleg`` (jüngstes Bild des Paares oder ``None``), ``grund`` (Satz, wenn
    kein Bild), ``hinweis`` (``HINWEIS_PAAR``, wenn ein Bild da ist).
    """

    def zeilenbeleg(modell_id: str, karte: dict) -> dict:
        bilder = belege_fuer(modell_id, karte.get("anbieter") or "")
        if bilder:
            return {"beleg": bilder[0], "grund": "", "hinweis": HINWEIS_PAAR}
        if not manifest_ok:
            grund = GRUND_MANIFEST
        elif karte.get("vom_crawler"):
            grund = GRUND_KLICK.format(tage=ANZEIGE_TAGE)
        else:
            grund = GRUND_LISTE
        return {"beleg": None, "grund": grund, "hinweis": ""}

    return zeilenbeleg


def quote(zeilenbeleg: Callable[[str, dict], dict], modelle: list[dict]) -> dict:
    """Wie viele der angezeigten Preiszeilen ein Bild tragen.

    Gezählt wird, was die Vorlage als Preis zeigt: Zeilen von ``zeilen_band`` und
    ``zeilen_ohne_band`` jedes Modells, deren Karte nach ``preis_anzeige`` belastbar
    ist (ein veralteter Preis ist eine Lücke, kein Preis). ``satz`` ist der fertige
    Text der Seite; ohne Preiszeile bleibt er leer.
    """
    mit = gesamt = 0
    for modell in modelle:
        for karte in [
            *modell.get("zeilen_band", []),
            *modell.get("zeilen_ohne_band", []),
        ]:
            if not preis_anzeige(karte).get("belastbar"):
                continue
            gesamt += 1
            if zeilenbeleg(modell["id"], karte)["beleg"]:
                mit += 1
    satz = (
        f"{mit} von {gesamt} Preisen mit Screenshot vom Original "
        "(je Gerät und Anbieter die günstigste Konfiguration; "
        "jede Zeile ohne Bild nennt den Grund)."
        if gesamt
        else ""
    )
    return {"mit": mit, "gesamt": gesamt, "satz": satz}


def installiere(env: Any, state_dir: Path, berichte: list[dict]) -> list[Ausfall]:
    """Macht ``belege_fuer(geraet_id, anbietername)`` für die Vorlagen verfügbar.

    ``berichte``: neuester zuerst; sein ``date`` ist das Berichtsdatum.
    """
    heute = berichte[0].get("date", "") if berichte else ""
    ausfaelle: list[Ausfall] = []
    manifest_ok = True
    try:
        manifest = lies_manifest(state_dir / MANIFEST_NAME)
        je_preis = sortiert_je_preis(manifest.belege, _heute(heute))
        if manifest.ausfall:
            ausfaelle.append(
                Ausfall(
                    TEIL,
                    f"Manifest nicht erneuert, Stand von zuvor: {manifest.ausfall}",
                )
            )
    except BelegManifestFehler as fehler:
        ausfaelle.append(Ausfall.aus_ausnahme(TEIL, fehler))
        je_preis = {}
        manifest_ok = False
    env.globals["belege_fuer"] = lambda geraet_id, anbieter: je_preis.get(
        (geraet_id, anbieter_schluessel(anbieter or "")), []
    )
    zeilenbeleg = zeilenbeleg_fuer(env.globals["belege_fuer"], manifest_ok)
    env.globals["zeilenbeleg"] = zeilenbeleg
    env.globals["belegquote"] = lambda modelle: quote(zeilenbeleg, modelle or [])
    return ausfaelle
