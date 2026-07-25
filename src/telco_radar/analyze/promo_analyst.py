"""LLM-Extraktion konkreter Promo-/Kampagnenangebote aus einem Seiten-Snapshot.

Bekommt NUR den Klartext einer Aktionsseite, die sich seit dem letzten Lauf
veraendert hat (siehe collect/promo_snapshot.py + analyze/promo_store.py).
Extrahiert daraus 0-N konkrete, aktuell laufende Angebote. Erfindet nie einen
Preis oder ein Enddatum, das nicht im Text steht - Stale-Preis-Risiko ist der
Hauptgrund, warum diese Seite ueberhaupt nur Mechaniken statt Fixpreisen
zeigen soll (siehe claude/promo-uebersicht-konzept.md, Risiko d).
"""
from __future__ import annotations

import json
import logging

from .llm import complete, extract_json

log = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """\
Du extrahierst fuer ein internes Vodafone-Wettbewerbsbriefing die aktuell
laufenden Tarif-, Rabatt- und Kampagnenangebote von {brand} in Deutschland
(Kategorie: Preis-/Promo-Aktionen - NICHT Netzausbau, NICHT
Unternehmens-Differenzierung jenseits des Preises).

Du bekommst den Klartext der oeffentlichen Aktions-/Tarifseite von {brand}.
Gib NUR Eintraege zurueck, die ein KONKRETES, aktuell beworbenes Angebot fuer
Endkunden beschreiben (Tarifrabatt, Startguthaben, Datenvolumen-Bonus,
Geraete-Bundle, saisonale Aktion, Wechsler-Praemie). VERWIRF Navigations-/
Menuereste, rechtliche Fussnoten, Cookie-Hinweise, allgemeine
Markenaussagen ohne konkretes Angebot und alles, was nicht wie ein Angebot
fuer Endkunden aussieht.

Erfinde NIE einen Preis, Rabattbetrag oder ein Enddatum, das nicht woertlich
oder eindeutig sinngemaess im Text steht. Wenn kein Enddatum genannt wird,
lasse "valid_until" weg (null) - nicht raten. Beschreibe die Mechanik in
eigenen Worten, kurz und laienverstaendlich, statt den Werbetext zu kopieren.

Pro gueltigem Eintrag:
- "headline": kurzer Titel des Angebots auf Deutsch (max. 12 Woerter)
- "description": 1-2 Saetze auf Deutsch, was das Angebot konkret ist
- "valid_until": Enddatum/Gueltigkeitszeitraum, GENAU wie im Text angegeben,
  sonst null

Wenn die Seite KEIN erkennbares Angebot mehr enthaelt oder nur Navigation
zeigt, gib [] zurueck. Antworte AUSSCHLIESSLICH mit einem JSON-Array, kein
weiterer Text.
"""


def extract_promos(brand: str, snapshot_text: str, model: str,
                   max_tokens: int = 1800) -> list[dict]:
    """LLM-Extraktion. Failsafe: bei jedem Fehler leere Liste - der
    bestehende PromoDB-Stand fuer diesen Brand bleibt dann einfach
    unveraendert (kein Absturz, kein stillschweigendes Loeschen)."""
    if not (snapshot_text or "").strip():
        return []
    try:
        raw = complete(
            _EXTRACT_SYSTEM.format(brand=brand), snapshot_text[:10000],
            model=model, max_tokens=max_tokens)
        parsed = extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("Promo-Extraktion (%s) fehlgeschlagen: %s", brand, str(exc)[:140])
        return []
    out = []
    for row in parsed if isinstance(parsed, list) else []:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("headline") or "").strip()
        if not headline:
            continue
        out.append({
            "brand": brand,
            "headline": headline,
            "description": str(row.get("description") or "").strip(),
            "valid_until": (str(row["valid_until"]).strip()
                           if row.get("valid_until") else None),
        })
    return out
