"""Die versionierte Differenzierungs-Datenbank (`differentiation_db.json`).

Ohne LLM- und Netzimport, damit `report/` den Bestand lesen kann.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urlsplit

from ..models import normalize_url
from .begriffe import THEMES

log = logging.getLogger(__name__)


class DiffDB:
    """Versionierte Differenzierungs-Datenbank (data/state/differentiation_db.json)."""

    def __init__(self, path):
        from pathlib import Path

        self.path = Path(path)
        self.entries: dict[str, dict] = {}
        self.updated = None
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.updated = raw.get("updated")
                for e in raw.get("entries", []):
                    eid = e.get("id") or normalize_url(e.get("url", ""))
                    if eid:
                        self.entries[eid] = e
            except (json.JSONDecodeError, OSError):
                log.warning("differentiation_db.json unlesbar – starte leer")

    def __len__(self):
        return len(self.entries)

    def upsert(self, items: list[dict], today: str) -> int:
        """Neue Moves aufnehmen / bekannte re-verifizieren. Gibt #neu zurück."""
        new = 0
        for it in items:
            eid = normalize_url(it.get("url", ""))
            if not eid:
                continue
            src = _domain(it.get("url"))
            if eid in self.entries:
                e = self.entries[eid]
                e["last_verified"] = today
                e["status"] = "aktiv"
            else:
                self.entries[eid] = {
                    "id": eid,
                    "theme": it.get("theme"),
                    "operator": it.get("operator"),
                    "region": it.get("region"),
                    "what": it.get("what"),
                    "url": it.get("url"),
                    "source": src,
                    "date": it.get("date"),
                    "why": it.get("why"),
                    "first_seen": it.get("first_seen") or today,
                    "last_verified": today,
                    "status": "aktiv",
                }
                new += 1
        return new

    def by_theme(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {k: [] for k, _ in THEMES}
        for e in self.entries.values():
            out.setdefault(e.get("theme") or "_", []).append(e)
        for k in out:
            out[k].sort(
                key=lambda e: (e.get("first_seen") or "", e.get("date") or ""),
                reverse=True,
            )
        return out

    def save(self, today: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated": today,
            "entries": sorted(
                self.entries.values(),
                key=lambda e: (e.get("theme") or "", e.get("first_seen") or ""),
            ),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def _domain(url: str) -> str:
    return urlsplit(url or "").netloc.removeprefix("www.")
