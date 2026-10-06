"""Notbremse der Geräteseite: welche Karte in Sieger, Δ und Kernzahl zählt.

Datenkonzept Geräteradar, Schritt 1 (docs/datenkonzept-geraete.md): Nur gemessene
Bündel zählen. Ein Bündel mit ``herleitung`` (1&1 aus dem Tarifraster, o2 aus
Tarifsumme minus Geräterate) stand so nie auf der Anbieterseite und ist eine
Schätzung. Ein Bündel, in dessen Preis eine abgelaufene Aktion steckt, ist veraltet.
Beide bleiben als Zeile sichtbar, stellen aber weder Δ noch Referenz noch Sieger,
keine Bewegung und keinen Günstigst-Wert; der Export nennt denselben Zustand.
"""

from __future__ import annotations

from ..tco_model import Aktion, Buendel, aktionen_aus

DELTA_SCHAETZUNG = "Schätzung"
SATZ_SCHAETZUNG = "Kein Abstand zur Vodafone-Referenz: dieser Preis ist abgeleitet."
DELTA_AKTION_ABGELAUFEN = "Aktion abgelaufen"
SATZ_AKTION_ABGELAUFEN = (
    "Kein Abstand zur Vodafone-Referenz: die eingerechnete Aktion ist abgelaufen."
)


def felder(b: Buendel, heute: str) -> dict:
    """Die Notbremse-Felder einer Karte: Flags, ``zaehlt``, benannter Zustand.

    Abgelaufen ist eine eingerechnete Aktion, die der Anbieter vor ``heute``
    befristet hat (``Aktion.gilt_am``); ein Platzhalter-Ende wie 2050 läuft weiter.
    """
    return _felder(b.herleitung, b.aktionen, heute)


def felder_aus_satz(satz: dict, heute: str) -> dict:
    """Dieselben Felder für einen gelesenen Bündel-Rohsatz (``geraete_tco.json``),
    dessen Aktionen über ``aktionen_aus`` gelesen werden wie im Store."""
    herleitung = str(satz.get("herleitung") or "")
    return _felder(herleitung, aktionen_aus(satz.get("aktionen")), heute)


def _felder(herleitung: str, aktionen: list[Aktion], heute: str) -> dict:
    schaetzung = bool(herleitung.strip())
    veraltet = any(a.eingerechnet and not a.gilt_am(heute) for a in aktionen)
    flags = {"schaetzung": schaetzung, "veraltet_aktion": veraltet}
    return {
        **flags,
        "zaehlt": not schaetzung and not veraltet,
        "notbremse": zustand(flags),
    }


def zaehlt(karte: dict) -> bool:
    """Darf die Karte Δ, Referenz oder Sieger stellen? Karten ohne die Felder
    (Listungen ohne Bündel) zählen wie bisher."""
    return karte.get("zaehlt", True)


def zustand(karte: dict) -> dict | None:
    """Der benannte Δ-Zustand einer Karte, die nicht zählt, sonst ``None``."""
    if karte.get("schaetzung"):
        return {"kurz": DELTA_SCHAETZUNG, "satz": SATZ_SCHAETZUNG}
    if karte.get("veraltet_aktion"):
        return {"kurz": DELTA_AKTION_ABGELAUFEN, "satz": SATZ_AKTION_ABGELAUFEN}
    return None


def kurz(b: Buendel, heute: str) -> str:
    """Der kurze Zustand eines Bündels für eine Tabellenzelle, leer, wenn es zählt."""
    return (felder(b, heute)["notbremse"] or {}).get("kurz", "")


def namen(karten: list) -> list[str]:
    """„1&1 (Schätzung)“ je Anbieter und Grund, wo die Notbremse Karten nimmt."""
    return list(dict.fromkeys(f"{k['anbieter']} ({gruende([k])})" for k in karten))


def gruende(karten: list) -> str:
    """„Schätzung“, „Aktion abgelaufen“ oder beide, je Grund einmal."""
    return ", ".join(dict.fromkeys(zustand(k)["kurz"] for k in karten))


def nur_zaehlende(messungen: dict) -> dict:
    """Die Messungen der Zeitreihe (``{(modell, band): {anbieter: {tag: m}}}``) ohne
    die, deren Bündel nicht zählt; ein Anbieter ohne solche fällt heraus."""
    fertig: dict = {}
    for paar, anbieter in messungen.items():
        for name, slot in anbieter.items():
            if tage := {t: m for t, m in slot.items() if zaehlt(m)}:
                fertig.setdefault(paar, {})[name] = tage
    return fertig
