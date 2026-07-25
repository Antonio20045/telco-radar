"""Persistent state for the Promo-Uebersicht snapshot-diff pipeline.

Two separate stores, mirroring the split already used by the differentiation
branch (raw signal vs. curated display):

  SnapshotStore  data/state/promo_snapshots.json - one content hash per brand,
                 used ONLY to detect "did this page change since last run".
                 Never shown on the site, never fed to the LLM by itself.

  PromoDB        data/state/promo_db.json - the curated, versioned list of
                 extracted promotions actually shown on the site, with
                 first_seen/last_verified/status. Structurally mirrors
                 analyze/category_sweep.py's DiffDB: entries persist across
                 weeks (a promo does not vanish from the page just because a
                 week went by without a new snapshot) and are re-verified,
                 never silently deleted, when re-observed.

Status lifecycle (two-strike, see mark_stale): "aktiv" -> (one missed
re-verification) -> "evtl. ausgelaufen" (still shown on the site, just
flagged - a single missed re-extraction is not proof the offer is gone,
extraction can be noisy) -> (missed AGAIN, still not reconfirmed) ->
"ausgelaufen" (now folded into the site's collapsed footnote, no longer an
individual visible card). Any re-confirmation at any point resets straight
back to "aktiv" with missed_checks=0 - a single blip never accumulates
towards retirement. Nothing is ever deleted from the JSON itself.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class SnapshotStore:
    """Last-known content hash per brand, for change detection only."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._by_brand: dict[str, dict] = {}
        if self.path.exists():
            try:
                self._by_brand = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("promo_snapshots.json unlesbar - starte leer")

    def changed(self, brand: str, text_hash: str) -> bool:
        return self._by_brand.get(brand, {}).get("hash") != text_hash

    def update(self, brand: str, text_hash: str, fetched_at: str) -> None:
        self._by_brand[brand] = {"hash": text_hash, "fetched_at": fetched_at}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._by_brand, ensure_ascii=False, indent=1),
            encoding="utf-8")


def entry_id(brand: str, headline: str) -> str:
    basis = f"{(brand or '').strip().lower()}|{' '.join((headline or '').lower().split())}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


class PromoDB:
    """Versionierte, kuratierte Promo-Datenbank (data/state/promo_db.json)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: dict[str, dict] = {}
        self.updated = None
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.updated = raw.get("updated")
                for e in raw.get("entries", []):
                    eid = e.get("id") or entry_id(e.get("brand", ""), e.get("headline", ""))
                    if eid:
                        self.entries[eid] = e
            except (json.JSONDecodeError, OSError):
                log.warning("promo_db.json unlesbar - starte leer")

    def __len__(self) -> int:
        return len(self.entries)

    def upsert(self, items: list[dict], today: str) -> int:
        """Neue Aktionen aufnehmen bzw. bekannte re-verifizieren (gleicher
        Brand + gleiche Kernaussage taucht im neuen Snapshot wieder auf).
        Gibt die Anzahl NEU aufgenommener Eintraege zurueck."""
        new = 0
        for it in items:
            brand = (it.get("brand") or "").strip()
            headline = (it.get("headline") or "").strip()
            if not brand or not headline:
                continue
            eid = entry_id(brand, headline)
            if eid in self.entries:
                e = self.entries[eid]
                e["last_verified"] = today
                e["status"] = "aktiv"
                e["missed_checks"] = 0
                e.pop("stale_since", None)
                if it.get("description"):
                    e["description"] = it["description"]
                if it.get("valid_until"):
                    e["valid_until"] = it["valid_until"]
                if it.get("image_url"):
                    e["image_url"] = it["image_url"]
            else:
                self.entries[eid] = {
                    "id": eid, "brand": brand, "tier": it.get("tier"),
                    "headline": headline,
                    "description": it.get("description", ""),
                    "valid_until": it.get("valid_until"),
                    "url": it.get("url", ""),
                    "image_url": it.get("image_url"),
                    "first_seen": today, "last_verified": today,
                    "status": "aktiv", "missed_checks": 0,
                }
                new += 1
        return new

    def mark_stale(self, brand: str, checked_ids: set, today: str) -> None:
        """Nach einem Snapshot-Wechsel fuer *brand*: Eintraege dieses Brands,
        die NICHT unter *checked_ids* sind (im neuen Snapshot nicht mehr
        wiedergefunden), ruecken einen Schritt in Richtung "beendet" -
        zwei Stufen, nie sofort und nie stillschweigend geloescht:

          "aktiv"              -> "evtl. ausgelaufen" (1. Fehltreffer, bleibt
                                   auf der Seite sichtbar, nur markiert)
          "evtl. ausgelaufen"   -> "ausgelaufen" (2. Fehltreffer IN FOLGE,
                                   gilt jetzt als wirklich beendet)

        Ein einzelner Fehltreffer reicht also nie aus, um eine Karte
        verschwinden zu lassen - das war der eigentliche Bug: eine einzelne
        unvollstaendige LLM-Extraktion (oder eine minimal andere Formulierung
        desselben Angebots) durfte ein noch gueltiges Angebot nicht sofort
        aus der Ansicht werfen. Wird ein Eintrag zwischendurch wieder
        bestaetigt (upsert), springt der Status sofort zurueck auf "aktiv"
        mit missed_checks=0."""
        for e in self.entries.values():
            if e.get("brand") != brand or e["id"] in checked_ids:
                continue
            status = e.get("status")
            if status not in ("aktiv", "evtl. ausgelaufen"):
                continue
            e["missed_checks"] = int(e.get("missed_checks") or 0) + 1
            if status == "aktiv":
                e["status"] = "evtl. ausgelaufen"
                e["stale_since"] = today
            else:
                e["status"] = "ausgelaufen"
                e["ended_since"] = today

    def by_brand(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for e in self.entries.values():
            out.setdefault(e.get("brand") or "_", []).append(e)
        for k in out:
            out[k].sort(
                key=lambda e: (e.get("status") == "aktiv", e.get("first_seen") or ""),
                reverse=True)
        return out

    def save(self, today: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated": today,
            "entries": sorted(
                self.entries.values(),
                key=lambda e: (e.get("brand") or "", e.get("first_seen") or "")),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
