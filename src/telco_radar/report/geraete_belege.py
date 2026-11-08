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

Das Bild gehört zum Paar (Modell, Anbieter), nicht zu einer Preiszeile: der Messlauf
lichtet je Paar nur eine Konfiguration ab (``scripts/belege_veroeffentlichen.py``), der
Dateiname trägt keinen Tarif. Welche Zeile das Bild zeigt, ist maschinell nicht
feststellbar. Die Seite verlinkt es deshalb einmal je Paar (``paarbelege``) als
„Screenshot der Angebotsseite vom <Datum> (zeigt nicht jeden Tarif)“ und setzt nichts
an eine Preiszeile. Ein Paar mit belastbarem Preis, aber ohne Bild, steht mit dem
Vermerk „kein Screenshot vorhanden“ daneben, damit „kein Preis“ und „kein Bild“
unterscheidbar bleiben. ``quote`` zählt Paare, keine Preise (Clean Code 1: dieselbe
Funktion für Link und Satz).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from ..beleg_manifest import MANIFEST_NAME, Beleg, BelegManifestFehler, lies_manifest
from ..beleg_regeln import (
    ANZEIGE_GROSS_ANZAHL,
    anbieter_schluessel,
    ist_anzeige_neu,
)
from .ausfall import Ausfall
from .geraete_preisstand import anzeige as preis_anzeige

TEIL = "Belegbilder"


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


def paarbelege(
    belege_fuer: Callable[[str, str], list[dict]], modell: dict
) -> list[dict]:
    """Die Paare (Modell, Anbieter) mit Bild, in der Reihenfolge der Preiszeilen.

    Ein Paar zählt, wenn das Modell dort mindestens eine belastbare Preiszeile zeigt
    (``preis_anzeige``: ein veralteter Preis ist eine Lücke). Ergebnis je Paar:
    ``anbieter`` (Name der ersten Zeile), ``beleg`` (jüngstes Bild oder ``None``).
    Die 24- und 36-Raten-Zeilen desselben Tarifs fallen im selben Paar zusammen.
    """
    gesehen: dict[str, dict] = {}
    for karte in [*modell.get("zeilen_band", []), *modell.get("zeilen_ohne_band", [])]:
        if not preis_anzeige(karte).get("belastbar"):
            continue
        name = karte.get("anbieter") or ""
        schluessel = anbieter_schluessel(name)
        if schluessel in gesehen:
            continue
        bilder = belege_fuer(modell.get("id", ""), name)
        gesehen[schluessel] = {"anbieter": name, "beleg": bilder[0] if bilder else None}
    return list(gesehen.values())


def quote(
    paare_fuer: Callable[[dict], list[dict]],
    modelle: list[dict],
    manifest_ok: bool = True,
) -> dict:
    """Für wie viele Gerät-Anbieter-Paare ein Screenshot der Angebotsseite vorliegt.

    Gezählt werden die Paare, die ``paarbelege`` je Modell nennt. ``satz`` ist der
    fertige Text der Seite; ohne Paar oder bei unlesbarer Belegliste (der Ausfall
    „Belegbilder“ nennt das) bleibt er leer, statt „0 von N“ zu behaupten.
    """
    mit = gesamt = 0
    for modell in modelle:
        for paar in paare_fuer(modell):
            gesamt += 1
            mit += 1 if paar["beleg"] else 0
    satz = (
        f"Für {mit} von {gesamt} Gerät-Anbieter-Paaren liegt ein Screenshot "
        "der Angebotsseite vor."
        if gesamt and manifest_ok
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

    def paare_fuer(modell: dict) -> list[dict]:
        return paarbelege(env.globals["belege_fuer"], modell)

    env.globals["paarbelege"] = paare_fuer
    env.globals["belegquote"] = lambda modelle: quote(
        paare_fuer, modelle or [], manifest_ok
    )
    return ausfaelle
