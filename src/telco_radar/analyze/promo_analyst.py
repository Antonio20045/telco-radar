"""LLM-Extraktion konkreter Promo-/Kampagnenangebote aus einem Seiten-Snapshot.

Bekommt NUR den Klartext einer Aktionsseite, die sich seit dem letzten Lauf
veraendert hat (siehe collect/promo_snapshot.py + analyze/promo_store.py).
Extrahiert daraus 0-N konkrete, aktuell laufende Angebote. Erfindet nie einen
Preis oder ein Enddatum, das nicht im Text steht - Stale-Preis-Risiko ist der
Hauptgrund, warum diese Seite ueberhaupt nur Mechaniken statt Fixpreisen
zeigen soll (siehe claude/promo-uebersicht-konzept.md, Risiko d).

Deep links (claude/promo-tiefenlinks-konzept.md): zusaetzlich zum Seitentext
kann eine nummerierte Liste von Link-Kandidaten uebergeben werden (siehe
collect/promo_snapshot.extract_link_candidates). Das Modell darf fuer einen
Eintrag hoechstens EINE Kandidaten-Nummer zurueckgeben - nie eine eigene URL
erfinden (gleiches Erfindungsverbot-Prinzip wie bei Preisen/Enddaten). Ein
fehlender, ungueltiger oder nicht referenzierter Index bleibt einfach leer;
promo_pipeline.py faellt dann auf die bisherige Markenseiten-URL zurueck -
keine Verschlechterung gegenueber vorher.
"""
from __future__ import annotations

import json
import logging

from .llm import complete, extract_json

log = logging.getLogger(__name__)


class PromoExtractionError(RuntimeError):
    """Der Extraktionsaufruf selbst ist gescheitert (API-Fehler, unlesbare
    Antwort) - im Unterschied zu "das Modell hat auf dieser Seite kein
    Angebot gefunden", was eine leere Liste bleibt.

    Die Unterscheidung ist keine Kosmetik, sie entscheidet ueber Datenverlust.
    Bis Lauf #83 gab beides `[]` zurueck, und die Pipeline konnte die Faelle
    nicht auseinanderhalten: sie zaehlte die Seite als geprueft und liess
    mark_stale ueber deren Angebote laufen. Ein einzelner API-Aussetzer
    schob damit noch laufende Aktionen Richtung "ausgelaufen" - dieselbe
    Luecke, die im Presse-Zweig der Seen-Store-Stapelschutz schliesst
    (siehe CLAUDE.md: gescheiterte Stapel duerfen nicht als gelesen gelten).
    """

# Harte Obergrenze pro SEITE und Lauf, unabhaengig davon, ob die
# Prompt-Anweisung (keine SKU-fuer-SKU-Liste) tatsaechlich befolgt wird - eine
# Karte mit 20 Einzelgeraete-Eintraegen ist nicht "auf einen Blick" lesbar.
# Nimmt bewusst die ERSTEN Eintraege (das Modell wird angewiesen, die
# wichtigsten/unterschiedlichsten Aktionen zuerst zu nennen), nicht die
# groessten - eine harte Kappung ohne Rangfolge waere willkuerlich.
#
# Von 8 auf 6 gesenkt am 08.08.2026, weil sich die BEZUGSGROESSE geaendert
# hat: bis dahin hatte jede Marke genau eine Seite, die Zahl war also zugleich
# die Obergrenze je Marke. Seit eine Marke mehrere Seiten hat (O2 hat sieben),
# multipliziert sie sich - 7 x 8 waeren 56 Zeilen unter einem Absender, und
# der Markenblock auf der Uebersicht listet sie alle. 6 je Seite ist reichlich
# fuer eine einzelne Aktionsseite (die meisten fuehren zwei bis vier klar
# unterscheidbare Aktionen) und haelt die Summe je Marke im Lesbaren. Der
# eigentliche Schutz gegen Wiederholungen sitzt ohnehin eine Schicht tiefer:
# PromoDB.upsert erkennt dasselbe Angebot auf zwei Seiten als einen Eintrag.
_MAX_ENTRIES_PER_PAGE = 6

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

NUR MOBILFUNK. Verwirf Festnetz-, DSL-, Kabel- und Glasfaserangebote
(z. B. MagentaZuhause, "Internet fuer Zuhause", Homespot-/Router-Tarife) -
dieses Segment wird bewusst nicht beobachtet. Mobile Datentarife fuer
Tablet, Smartwatch oder Multi-SIM gehoeren dagegen dazu.

Erfinde NIE einen Preis, Rabattbetrag oder ein Enddatum, das nicht woertlich
oder eindeutig sinngemaess im Text steht. Wenn kein Enddatum genannt wird,
lasse "valid_until" weg (null) - nicht raten. Beschreibe die Mechanik in
eigenen Worten, kurz und laienverstaendlich, statt den Werbetext zu kopieren.

WICHTIG - keine Geraete-/SKU-Liste: Wenn dieselbe Kampagne (gleicher Rabatt,
gleiche Vertragsmechanik) nur mit unterschiedlichen Geraetemodellen oder
Tarifvarianten wiederholt wird (z. B. "iPhone 17 ab X", "Galaxy S26 ab Y",
"Xiaomi ab Z" - alle mit demselben Grundtarif), fasse das zu EINEM Eintrag
zusammen und nenne die Preisspanne oder 1-2 Beispiele in der Beschreibung,
statt jedes Geraetemodell einzeln aufzulisten. Ziel ist eine kleine Zahl klar
unterscheidbarer Aktionen pro Anbieter (typischerweise 1-6), keine
SKU-fuer-SKU-Liste - das Ergebnis muss sich auf einen Blick ueberblicken
lassen.

Pro gueltigem Eintrag:
- "headline": kurzer Titel des Angebots auf Deutsch (max. 12 Woerter)
- "description": 1-2 Saetze auf Deutsch, was das Angebot konkret ist
- "valid_until": Enddatum/Gueltigkeitszeitraum, GENAU wie im Text angegeben,
  sonst null

Wenn die Seite KEIN erkennbares Angebot mehr enthaelt oder nur Navigation
zeigt, gib [] zurueck. Antworte AUSSCHLIESSLICH mit einem JSON-Array, kein
weiterer Text.
"""

# Nur angehaengt, wenn tatsaechlich Link-Kandidaten vorliegen (siehe
# extract_promos). Getrennt vom Basis-Prompt, damit ein Aufruf ohne
# Kandidaten (z. B. Fallback, aeltere Tests) den Prompt nicht unnoetig
# aufblaeht oder ein Feld erwaehnt, das es dann gar nicht geben kann.
_LINK_SELECTION_INSTRUCTIONS = """

Zusaetzlich bekommst du unten eine NUMMERIERTE LISTE echter Links von dieser
Seite ("LINK-KANDIDATEN"). Wenn einer dieser Kandidaten eindeutig und
konkret auf die Detailseite GENAU DIESES Angebots verweist (nicht nur
allgemein auf die Marken-/Uebersichtsseite), gib zusaetzlich
"link_index": <Nummer> zurueck. Nutze IMMER eine Nummer aus der Liste, NIE
eine selbst erdachte oder veraenderte URL. Bist du unsicher, welcher
Kandidat passt, oder passt keiner wirklich zu diesem konkreten Angebot,
lasse "link_index" ganz weg (oder setze null) - raten ist schlimmer als
gar keinen Link vorzuschlagen."""


def _format_link_candidates(links: list[dict]) -> str:
    """Numbered "N. \"context\" -> href" block for the prompt. Skips
    candidates without a usable href defensively; context is truncated so
    one oddly long candidate cannot dominate the prompt."""
    lines = []
    for link in links:
        href = (link.get("href") or "").strip()
        if not href:
            continue
        text = (link.get("text") or "").strip()[:120] or "(kein Text)"
        lines.append(f"{len(lines) + 1}. \"{text}\" -> {href}")
    return "\n".join(lines)


def _resolve_link_index(row: dict, links: list[dict]) -> str | None:
    """Defensively resolve row["link_index"] (1-based, as offered in the
    prompt) to an href. Any shape the model might return that is not a
    clean in-range integer - missing, null, float, string, out of bounds -
    resolves to None rather than raising, exactly like the existing
    valid_until/headline handling in this module. NEVER falls back to a
    free-form "url"/"link" field the model might have added on its own -
    the only path to a URL here is a candidate the page itself offered."""
    raw_index = row.get("link_index")
    if raw_index is None or isinstance(raw_index, bool):
        return None
    idx = None
    if isinstance(raw_index, int):
        idx = raw_index
    elif isinstance(raw_index, float) and raw_index.is_integer():
        idx = int(raw_index)
    elif isinstance(raw_index, str) and raw_index.strip().lstrip("-").isdigit():
        idx = int(raw_index.strip())
    if idx is None or not (1 <= idx <= len(links)):
        return None
    href = (links[idx - 1].get("href") or "").strip()
    return href or None


def extract_promos(brand: str, snapshot_text: str, model: str,
                   links: list[dict] | None = None,
                   max_tokens: int = 8000) -> list[dict]:
    """LLM-Extraktion.

    Rueckgabe: die gefundenen Angebote. Eine LEERE Liste heisst "auf dieser
    Seite steht gerade kein Angebot" - eine belastbare Aussage, die
    mark_stale auswerten darf. Scheitert dagegen der Aufruf selbst, fliegt
    ein `PromoExtractionError`; der Aufrufer muss die Seite dann als
    ungelesen behandeln und ihre bestehenden Angebote in Ruhe lassen.

    *links* (optional): Kandidaten aus
    collect/promo_snapshot.extract_link_candidates. Wird eine passende
    Nummer vom Modell zurueckgegeben, traegt der Eintrag zusaetzlich "url" -
    fehlt sie oder ist sie ungueltig, bleibt "url" schlicht weg und
    promo_pipeline.py setzt die bisherige Markenseiten-URL ein."""
    if not (snapshot_text or "").strip():
        return []
    links = links or []
    candidates_block = _format_link_candidates(links)
    system = _EXTRACT_SYSTEM.format(brand=brand)
    user = snapshot_text[:10000]
    if candidates_block:
        system += _LINK_SELECTION_INSTRUCTIONS
        user += "\n\nLINK-KANDIDATEN:\n" + candidates_block
    try:
        raw = complete(system, user, model=model, max_tokens=max_tokens)
        parsed = extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("Promo-Extraktion (%s) fehlgeschlagen: %s", brand, str(exc)[:140])
        raise PromoExtractionError(f"{type(exc).__name__}: {str(exc)[:140]}") from exc
    out = []
    for row in parsed if isinstance(parsed, list) else []:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("headline") or "").strip()
        if not headline:
            continue
        entry = {
            "brand": brand,
            "headline": headline,
            "description": str(row.get("description") or "").strip(),
            "valid_until": (str(row["valid_until"]).strip()
                           if row.get("valid_until") else None),
        }
        if links:
            href = _resolve_link_index(row, links)
            if href:
                entry["url"] = href
        out.append(entry)
    if len(out) > _MAX_ENTRIES_PER_PAGE:
        log.info("Promo-Extraktion (%s): %d Eintraege auf %d gekappt",
                 brand, len(out), _MAX_ENTRIES_PER_PAGE)
        out = out[:_MAX_ENTRIES_PER_PAGE]
    return out
