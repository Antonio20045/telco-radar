"""Notbremse der Geräteseite: welche Karte in Sieger, Δ und Kernzahl zählt.

Datenkonzept Geräteradar, Schritt 1 (docs/datenkonzept-geraete.md): Nur gemessene
Bündel zählen. Ein Bündel mit ``herleitung`` (1&1 aus dem Tarifraster, o2 aus
Tarifsumme minus Geräterate) stand so nie auf der Anbieterseite und ist eine
Schätzung. Ein Bündel, in dessen Preis eine abgelaufene Aktion steckt, ist veraltet.
Beide bleiben als Zeile sichtbar, stellen aber weder Δ noch Referenz noch Sieger,
keine Bewegung und keinen Günstigst-Wert; der Export nennt denselben Zustand.

Schritt 7: Ebenso ein Bündel, dem die Prüfstelle (``analyze/geraete_regeln``) den Status
Quarantäne oder veraltet gegeben hat oder an dem sie gescheitert ist (``unbekannt``).
Ein Bündel ohne Feld ``pruefung`` ist nie geprüft worden und zählt wie vor der
Prüfstelle; die Quellen-Seite zählt es als „nicht geprüft“.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..analyze.geraete_pruefstatus import (
    FELD_PRUEFUNG,
    GUELTIG,
    QUARANTAENE,
    UNBEKANNT,
    VERALTET,
    abgelaufene_aktionen,
    status_aus_feld,
)
from ..tco_model import Aktion, Buendel, aktionen_aus

DELTA_SCHAETZUNG = "Schätzung"
SATZ_SCHAETZUNG = "Kein Abstand zur Vodafone-Referenz: dieser Preis ist abgeleitet."
DELTA_AKTION_ABGELAUFEN = "Aktion abgelaufen"
SATZ_AKTION_ABGELAUFEN = (
    "Kein Abstand zur Vodafone-Referenz: die eingerechnete Aktion ist abgelaufen."
)
DELTA_QUARANTAENE = "Quarantäne"
SATZ_QUARANTAENE = (
    "Kein Abstand zur Vodafone-Referenz: dieser Preis verletzt eine Prüfregel."
)
DELTA_VERALTET = "veraltet"
SATZ_VERALTET = "Kein Abstand zur Vodafone-Referenz: dieser Preis ist veraltet."
DELTA_UNGEPRUEFT = "Prüfung gescheitert"
SATZ_UNGEPRUEFT = (
    "Kein Abstand zur Vodafone-Referenz: die Prüfung dieses Preises ist gescheitert."
)
_PRUEFZUSTAENDE = (
    ("quarantaene", DELTA_QUARANTAENE, SATZ_QUARANTAENE),
    ("veraltet_pruefung", DELTA_VERALTET, SATZ_VERALTET),
    ("pruefung_gescheitert", DELTA_UNGEPRUEFT, SATZ_UNGEPRUEFT),
)


def felder(b: Buendel, heute: str) -> dict:
    """Die Notbremse-Felder einer Karte: Flags, ``zaehlt``, benannter Zustand.

    Abgelaufen ist eine eingerechnete Aktion, die der Anbieter vor ``heute``
    befristet hat (``Aktion.gilt_am``); ein Platzhalter-Ende wie 2050 läuft weiter.
    """
    return _felder(b.herleitung, b.aktionen, heute, b.pruefung)


def felder_aus_satz(satz: dict, heute: str) -> dict:
    """Dieselben Felder für einen gelesenen Bündel-Rohsatz (``geraete_tco.json``),
    dessen Aktionen über ``aktionen_aus`` gelesen werden wie im Store."""
    herleitung = str(satz.get("herleitung") or "")
    aktionen = aktionen_aus(satz.get("aktionen"))
    return _felder(herleitung, aktionen, heute, satz.get(FELD_PRUEFUNG))


def _felder(
    herleitung: str, aktionen: Iterable[Aktion], heute: str, pruefung: object
) -> dict:
    schaetzung = bool(herleitung.strip())
    veraltet = bool(abgelaufene_aktionen(aktionen, heute))
    status = status_aus_feld(pruefung)
    flags = {
        "schaetzung": schaetzung,
        "veraltet_aktion": veraltet,
        "quarantaene": status == QUARANTAENE,
        "veraltet_pruefung": status == VERALTET,
        "pruefung_gescheitert": status == UNBEKANNT,
        "pruefgruende": _pruefgruende(pruefung),
    }
    return {
        **flags,
        "zaehlt": not schaetzung and not veraltet and status in (None, GUELTIG),
        "notbremse": zustand(flags),
    }


def _pruefgruende(pruefung: object) -> list[str]:
    """„Regel 3: Tarif mit Gerät 14,99 € unter SIM-only 19,99 €“ je Grund."""
    gruende = pruefung.get("gruende") if isinstance(pruefung, Mapping) else None
    return [f"Regel {g.get('regel')}: {g.get('satz')}" for g in gruende or []]


def zaehlt(karte: dict) -> bool:
    """Darf die Karte Δ, Referenz oder Sieger stellen? Nur ohne Schätzung, ohne
    abgelaufene Aktion und mit Status gültig; Karten ohne die Felder (Listungen ohne
    Bündel) und nie geprüfte Bündel zählen wie bisher."""
    return karte.get("zaehlt", True)


def zustand(karte: dict) -> dict | None:
    """Der benannte Δ-Zustand einer Karte, die nicht zählt, sonst ``None``.

    Ein Zustand der Prüfstelle nennt im Satz jede verletzte Regel mit Nummer.
    """
    if karte.get("schaetzung"):
        return {"kurz": DELTA_SCHAETZUNG, "satz": SATZ_SCHAETZUNG}
    if karte.get("veraltet_aktion"):
        return {"kurz": DELTA_AKTION_ABGELAUFEN, "satz": SATZ_AKTION_ABGELAUFEN}
    gruende = [f"{g}." for g in karte.get("pruefgruende") or []]
    for flag, kurz_, satz in _PRUEFZUSTAENDE:
        if karte.get(flag):
            return {"kurz": kurz_, "satz": " ".join([satz, *gruende])}
    return None


def kurz(b: Buendel, heute: str) -> str:
    """Der kurze Zustand eines Bündels für eine Tabellenzelle, leer, wenn es zählt."""
    return (felder(b, heute)["notbremse"] or {}).get("kurz", "")


def namen(karten: list) -> list[str]:
    """„1&1 (Schätzung)“ je Anbieter und Grund, wo die Notbremse Karten nimmt."""
    return list(dict.fromkeys(f"{k['anbieter']} ({gruende([k])})" for k in karten))


def gruende(karten: list) -> str:
    """„Schätzung“, „Aktion abgelaufen“, „Quarantäne“ …, je Grund einmal."""
    return ", ".join(dict.fromkeys((zustand(k) or {}).get("kurz", "") for k in karten))


def nur_zaehlende(messungen: dict) -> dict:
    """Die Messungen der Zeitreihe (``{(modell, band): {anbieter: {tag: m}}}``) ohne
    die, deren Bündel nicht zählt; ein Anbieter ohne solche fällt heraus."""
    fertig: dict = {}
    for paar, anbieter in messungen.items():
        for name, slot in anbieter.items():
            if tage := {t: m for t, m in slot.items() if zaehlt(m)}:
                fertig.setdefault(paar, {})[name] = tage
    return fertig
