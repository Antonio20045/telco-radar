"""Persistenter, kuratierter Differenzierungs-Speicher.

Problem: Der Wochenbericht zeigt bewusst nur die NEUEN Meldungen einer Woche.
Ein Differenzierungs-Move (z. B. „Telekom schenkt jedem Kunden Perplexity Pro")
ist aber oft monatelang relevant – er soll nicht verschwinden, nur weil eine
Woche vergangen ist. Gleichzeitig darf die Differenzierungs-Seite nicht auf
hunderte Einträge anwachsen.

Lösung: eine eigene, git-versionierte Gedächtnis-Schicht
(data/state/differentiation.jsonl), unabhängig davon, wie lange die
Wochen-Report-JSONs aufgehoben werden. Jede Woche prüft ein Kurator die NEUEN
Meldungen:
  1. Vorfilter (deterministisch): dieselbe Klassifikation wie die Anzeige
     (report/differentiation.classify) – nur echte Differenzierungs-Hebel,
     keine Preis-/Netz-/B2B-Meldungen, plus eine Relevanz-Schwelle.
  2. Kurator-Agent (LLM, optional & failsafe): entscheidet je Kandidat, ob der
     Move es wert ist, dauerhaft in die Inspirations-Bibliothek aufgenommen zu
     werden. Fällt der Agent aus, greift der deterministische Vorfilter.
Aufgenommene Moves werden angehängt (dedupliziert per normalisierter URL) und
pro Hebel gedeckelt, damit der Speicher schlank bleibt.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..models import normalize_url
from ..report.differentiation import classify, _THEME_BY_KEY
from .llm import complete, extract_json

log = logging.getLogger(__name__)

# Felder eines Highlights, die für Anzeige (build_differentiation) UND Speicher
# gebraucht werden.
_KEEP_FIELDS = ("title", "summary", "url", "operator", "region", "date",
                "category", "relevance", "why_it_matters", "source")

# Ab dieser Bewertung (1–5) gilt ein klassifizierter Move als aufnahmewürdig,
# wenn kein LLM-Kurator läuft. Unbewertete Items (relevance None, z. B. --no-llm)
# werden ebenfalls behalten, damit der Speicher nie leer bleibt.
MIN_RELEVANCE = 3
# Obergrenze je Hebel im Speicher, damit die Datei über Jahre nicht ausufert.
MAX_PER_THEME = 60


class DiffStore:
    """Append-only JSONL-Speicher kuratierter Differenzierungs-Moves."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._by_id: dict[str, dict] = {}
        self._order: list[str] = []
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        rid = rec.get("id") or normalize_url(rec.get("url", ""))
                        if rid and rid not in self._by_id:
                            self._by_id[rid] = rec
                            self._order.append(rid)
                    except json.JSONDecodeError:
                        log.warning("Skipping corrupt diff-store line: %.80s", line)

    def __len__(self) -> int:
        return len(self._by_id)

    def known_ids(self) -> set[str]:
        return set(self._by_id)

    def entries(self) -> list[dict]:
        """Alle gespeicherten Moves als highlight-artige Dicts (für die Anzeige)."""
        return [self._by_id[i] for i in self._order]

    def add(self, highlights: list[dict], report_date: str) -> list[dict]:
        """Neue Moves aufnehmen (dedupliziert). Gibt die tatsächlich neu
        aufgenommenen Einträge zurück."""
        added: list[dict] = []
        for hl in highlights:
            rid = normalize_url(hl.get("url", ""))
            if not rid or rid in self._by_id:
                continue
            theme = hl.get("theme") or classify(hl)
            rec = {"id": rid, "first_seen": report_date, "theme": theme}
            rec.update({k: hl.get(k) for k in _KEEP_FIELDS})
            self._by_id[rid] = rec
            self._order.append(rid)
            added.append(rec)
        if added:
            self._rewrite()
        return added

    def _rewrite(self) -> None:
        """Speicher pro Hebel deckeln (relevanteste + neueste behalten) und
        vollständig zurückschreiben."""
        by_theme: dict[str, list[dict]] = {}
        for rid in self._order:
            rec = self._by_id[rid]
            by_theme.setdefault(rec.get("theme") or "_", []).append(rec)
        keep_ids: set[str] = set()
        for recs in by_theme.values():
            recs_sorted = sorted(
                recs,
                key=lambda r: ((r.get("relevance") or 0), r.get("first_seen") or ""),
                reverse=True,
            )
            for r in recs_sorted[:MAX_PER_THEME]:
                keep_ids.add(r["id"])
        # Reihenfolge (Aufnahme-Reihenfolge) beibehalten, nur gekappte entfernen.
        self._order = [i for i in self._order if i in keep_ids]
        self._by_id = {i: self._by_id[i] for i in self._order}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            for rid in self._order:
                fh.write(json.dumps(self._by_id[rid], ensure_ascii=False) + "\n")


_CURATOR_SYSTEM = """\
Du kuratierst die dauerhafte „Differenzierungs-Bibliothek" für Vodafone. Sie
sammelt, wie sich Telko-Wettbewerber weltweit im ENDKUNDENGESCHÄFT JENSEITS DES
PREISES abheben: eingebundene Dienste (Netflix, Spotify, KI-Assistenten wie
Perplexity/Gemini), Garantie-/Service-Versprechen (5-Jahres-Garantie, Preislock),
Geräte-Programme, Security, Fintech, Super-Apps, Cloud, Smart Home, Gaming,
Loyalty-Perks, Health.

Du bekommst neue Kandidaten-Meldungen. Entscheide je Meldung, ob sie es WERT ist,
dauerhaft (auch in Wochen noch) als Inspiration aufgehoben zu werden.

Behalte NUR, wenn es ein konkreter, nachahmbarer Differenzierungs-Move eines
Betreibers für Privatkunden ist. Verwirf reine Preis-/Tarif-Aktionen, Netz-/5G-/
Glasfaser-/Infrastruktur-Themen, B2B/Enterprise, Konzernfinanzen/M&A, vage
Ankündigungen ohne Substanz und reine Marktkommentare.

Antworte AUSSCHLIESSLICH mit einem JSON-Array, ein Objekt pro Kandidat:
[{"i": <index>, "keep": true|false, "grund": "<max 12 Wörter, warum>"}]
Kein weiterer Text.
"""


def _llm_judge(candidates: list[dict], model: str) -> list[dict]:
    """LLM-Kurator: filtert die Kandidaten. Failsafe – bei jedem Fehler werden
    alle Kandidaten behalten (deterministischer Rückfall)."""
    payload = [
        {"i": i,
         "operator": c.get("operator") or c.get("source") or "",
         "titel": (c.get("title") or "")[:200],
         "zusammenfassung": (c.get("summary") or "")[:400],
         "hebel": c.get("theme")}
        for i, c in enumerate(candidates)
    ]
    try:
        raw = complete(_CURATOR_SYSTEM,
                       json.dumps(payload, ensure_ascii=False),
                       model=model, max_tokens=1500)
        verdicts = extract_json(raw)
        keep_idx = {int(v["i"]) for v in verdicts
                    if isinstance(v, dict) and v.get("keep")}
        kept = [c for i, c in enumerate(candidates) if i in keep_idx]
        log.info("Diff-Kurator: %d/%d Kandidaten behalten",
                 len(kept), len(candidates))
        return kept
    except Exception as exc:  # noqa: BLE001
        log.warning("Diff-Kurator (LLM) fehlgeschlagen (%s) – behalte alle "
                    "Kandidaten deterministisch", str(exc)[:160])
        return candidates


def curate(new_highlights: list[dict], store: DiffStore, report_date: str,
           model: str | None = None, use_llm: bool = False,
           min_relevance: int = MIN_RELEVANCE) -> list[dict]:
    """Prüfe die neuen Highlights der Woche und nimm aufnahmewürdige
    Differenzierungs-Moves in den Speicher auf. Gibt die neu aufgenommenen
    Einträge zurück."""
    known = store.known_ids()
    candidates: list[dict] = []
    for hl in new_highlights or []:
        theme = classify(hl)
        if theme is None:
            continue
        rid = normalize_url(hl.get("url", ""))
        if not rid or rid in known:
            continue
        rel = hl.get("relevance")
        if rel is not None and rel < min_relevance:
            continue
        hl = dict(hl)
        hl["theme"] = theme
        candidates.append(hl)

    if not candidates:
        return []

    if use_llm and model:
        candidates = _llm_judge(candidates, model)

    return store.add(candidates, report_date)
