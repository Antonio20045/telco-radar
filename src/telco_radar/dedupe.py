"""Novelty layer: persistent 'seen' store + freshness filter.

This is the heart of "only report what is new":
- every item id (hash of normalized URL) that was ever collected is stored
  in data/state/seen.jsonl (git-versioned, human-readable)
- a second store data/state/reported_topics.jsonl remembers which topics the
  editor already covered, so reports never repeat themselves
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .models import Item

log = logging.getLogger(__name__)


class SeenStore:
    """Append-only JSONL store of item ids that were already collected."""

    def __init__(self, path: Path):
        self.path = path
        self._seen: dict[str, dict] = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        self._seen[rec["id"]] = rec
                    except (json.JSONDecodeError, KeyError):
                        log.warning("Skipping corrupt seen-store line: %.80s", line)

    def __len__(self) -> int:
        return len(self._seen)

    def is_new(self, item: Item) -> bool:
        return item.id not in self._seen

    def filter_new(self, items: list[Item]) -> list[Item]:
        out, seen_this_run = [], set()
        for item in items:
            if item.id in seen_this_run or not self.is_new(item):
                continue
            seen_this_run.add(item.id)
            out.append(item)
        return out

    def add(self, items: list[Item]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            for item in items:
                if item.id in self._seen:
                    continue
                rec = {
                    "id": item.id,
                    "url": item.url,
                    "title": item.title[:200],
                    "source": item.source_name,
                    "first_seen": now,
                }
                self._seen[item.id] = rec
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


class ReportedTopics:
    """Memory of topics that already appeared in a published report."""

    def __init__(self, path: Path, max_entries: int = 300):
        self.path = path
        self.max_entries = max_entries
        self.topics: list[dict] = []
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            self.topics.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

    def recent(self) -> list[str]:
        return [t.get("topic", "") for t in self.topics[-self.max_entries:]]

    def add(self, topics: list[str], report_date: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            for topic in topics:
                rec = {"topic": topic[:200], "report": report_date}
                self.topics.append(rec)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def filter_fresh(items: list[Item], lookback_days: int) -> list[Item]:
    """Keep items published within the window; keep undated items (they are
    new by definition if they passed the seen filter). Ignore dates more than
    one day in the future because archive pages can expose scheduled items."""
    out = []
    for item in items:
        age = item.age_days()
        if age is None or (-1.0 <= age <= lookback_days):
            out.append(item)
    return out
