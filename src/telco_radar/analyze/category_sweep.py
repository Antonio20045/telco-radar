"""Dynamischer Kategorie-Sweep für die Differenzierungs-Seite.

Zweite Datenquelle NEBEN dem Newsroom-Crawl: durchsucht bei jedem Lauf aktiv das
Web (Brave Search API) je Differenzierungs-Kategorie nach echten, aktuellen
Endkunden-Moves der Wettbewerber jenseits des Preises, lässt die Treffer vom LLM
GEGROUNDET filtern/zusammenfassen (nur belegbare Operator-Moves, sonst nichts)
und pflegt sie in eine versionierte DB (data/state/differentiation_db.json) mit
Quelle, Datum und "zuletzt geprüft". Alte Einträge werden re-verifiziert; ohne
Bestätigung als "evtl. eingestellt" markiert.

Kein hartkodierter Katalog: jeder Eintrag hat Quelle + Datum, wird aktualisiert
und re-verifiziert. Failsafe: ohne Brave/LLM passiert einfach nichts Neues, die
bestehende DB bleibt.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from ..collect import http
from .begriffe import THEME_LABEL, THEMES
from .diff_db import DiffDB
from .llm import complete, extract_json

log = logging.getLogger(__name__)


CATEGORY_QUERIES = {
    "ki": [
        "telecom operator free AI assistant Perplexity OR Gemini OR Copilot included mobile plan"
    ],
    "entertainment": [
        "mobile operator free Netflix OR Disney+ OR Spotify OR streaming bundle plan"
    ],
    "garantie": [
        "telecom operator price guarantee OR multi-year warranty OR satisfaction guarantee"
    ],
    "geraete": [
        "carrier annual phone upgrade program OR trade-in OR device as a service"
    ],
    "security": [
        "telecom operator free scam OR fraud OR spam protection network deepfake"
    ],
    "fintech": ["telecom operator mobile money OR wallet OR fintech super app"],
    "superapp": ["telecom operator super app mini apps everyday services"],
    "cloud": ["mobile operator free cloud storage plan perk customers"],
    "smarthome": ["telecom operator smart home security bundle service customers"],
    "gaming": ["telecom operator cloud gaming bundle GeForce Now OR Game Pass"],
    "loyalty": ["telecom operator loyalty rewards perks Priority OR Magenta Moments"],
    "health": ["telecom operator telemedicine OR health app OR wellbeing plan"],
}

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


def brave_search(
    query: str, key: str, count: int = 8, freshness: str = "py"
) -> list[dict]:
    """Brave Web Search -> Liste {title, url, description, age}. Failsafe: []."""
    if not key:
        return []
    try:
        antwort = http.get(
            BRAVE_URL,
            params={"q": query, "count": count, "freshness": freshness},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
            timeout=20,
        )
        antwort.raise_for_status()
        data = antwort.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("Brave-Suche fehlgeschlagen (%s): %s", query[:40], str(exc)[:120])
        return []
    return [
        {
            "title": x.get("title"),
            "url": x.get("url"),
            "description": x.get("description"),
            "age": x.get("age"),
        }
        for x in data.get("web", {}).get("results", [])
        if x.get("url")
    ]


_EXTRACT_SYSTEM = """\
Du extrahierst für Vodafone echte Differenzierungs-Moves von Telko-Wettbewerbern
im ENDKUNDENGESCHÄFT JENSEITS DES PREISES (Kategorie: {label}).

Du bekommst Web-Suchtreffer (Titel, URL, Snippet). Gib NUR Einträge zurück, die
einen KONKRETEN Move eines benannten Netzbetreibers/Anbieters beschreiben (z. B.
„Betreiber X schenkt Kunden Dienst Y"). VERWIRF Vergleichs-/Ratgeber-/Listicle-
Seiten, allgemeine Markttrends, reine Preis-/Tarif-/Netz-/5G-/B2B-Themen und
alles ohne benannten Betreiber. Erfinde nichts; nutze nur die Treffer.

Pro gültigem Eintrag:
- "operator": Name des Betreibers
- "region": eine von: Europa, Nordamerika, Lateinamerika, Afrika & Naher Osten, Asien, Ozeanien
- "what": 1 Satz auf Deutsch, was der Betreiber konkret tut (mit Zahlen, wenn im Snippet)
- "url": die exakte Quell-URL aus dem Treffer (nicht erfinden)
- "why": 1 neutraler Satz auf Deutsch, warum dieser Move als
  Differenzierungsbeispiel interessant ist (keine Empfehlung, kein „Vodafone
  sollte/könnte", keine Handlungsempfehlung)

Wenn KEIN Treffer einen echten Move zeigt, gib [] zurück. Antworte AUSSCHLIESSLICH
mit JSON-Array, kein weiterer Text.
"""


def _llm_extract(theme_key: str, results: list[dict], model: str) -> list[dict]:
    if not results:
        return []
    payload = [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": (r.get("description") or "")[:280],
        }
        for r in results
    ]
    try:
        raw = complete(
            _EXTRACT_SYSTEM.format(label=THEME_LABEL.get(theme_key, theme_key)),
            json.dumps(payload, ensure_ascii=False),
            model=model,
            max_tokens=16000,
        )
        parsed = extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM-Extraktion (%s) fehlgeschlagen: %s", theme_key, str(exc)[:120])
        return []
    valid_urls = {r.get("url") for r in results}
    out = []
    for row in parsed if isinstance(parsed, list) else []:
        if not isinstance(row, dict):
            continue
        if row.get("operator") and row.get("what") and row.get("url") in valid_urls:
            out.append(
                {
                    "theme": theme_key,
                    "operator": str(row["operator"]).strip(),
                    "region": str(row.get("region") or "").strip(),
                    "what": str(row["what"]).strip(),
                    "url": row["url"],
                    "why": str(row.get("why") or "").strip(),
                }
            )
    return out


def rotation_slice(week: int, per_run: int = 4) -> list[str]:
    keys = [k for k, _ in THEMES]
    start = (week * per_run) % len(keys)
    return [keys[(start + i) % len(keys)] for i in range(per_run)]


def sweep(
    db: DiffDB, brave_key: str, model: str, today: str, theme_keys: list[str]
) -> int:
    """Führe den Sweep für die gegebenen Kategorien aus. Gibt #neu zurück."""
    total_new = 0
    for tk in theme_keys:
        results = []
        for q in CATEGORY_QUERIES.get(tk, []):
            results.extend(brave_search(q, brave_key))
        items = _llm_extract(tk, results, model)
        total_new += db.upsert(items, today)
    return total_new


def run_sweep(
    state_dir, brave_key: str, model: str, use_llm: bool, week: int, per_run: int = 4
) -> None:
    """Pipeline-Einstieg: DB laden, rotierenden Sweep fahren, speichern."""
    from pathlib import Path

    db = DiffDB(Path(state_dir) / "differentiation_db.json")
    today = date.today().isoformat()
    if use_llm and brave_key:
        keys = rotation_slice(week, per_run)
        try:
            n = sweep(db, brave_key, model, today, keys)
            log.info(
                "Kategorie-Sweep: %s -> %d neu (DB: %d)", ",".join(keys), n, len(db)
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Kategorie-Sweep fehlgeschlagen: %s", exc)
    db.save(today)
