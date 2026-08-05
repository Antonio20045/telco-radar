"""Novelty layer: persistent 'seen' store + freshness filter.

This is the heart of "only report what is new":
- every item id (hash of normalized URL) that was ever collected is stored
  in data/state/seen.jsonl (git-versioned, append-only)
- a second store data/state/reported_topics.jsonl remembers which topics the
  editor already covered, so reports never repeat themselves


Speicherformat - warum es sich geaendert hat
--------------------------------------------
Bis 08/2026 stand je Meldung ein ganzes JSON-Objekt in der Datei (id, volle
URL, Titel, Quelle, Zeitstempel), rund 300 Byte. Bei 130 Quellen waren das
1 968 Eintraege und 592 KB - unauffaellig. Bei 1000 Quellen sind es hochge-
rechnet ~2 250 neue Meldungen je Lauf, zwei Laeufe die Woche, also ~233 000
Eintraege und ~67 MB im Jahr. GitHubs hartes Limit je Datei liegt bei 100 MB:
das Format haette ein Ablaufdatum gehabt, und zwar mitten im zweiten Jahr.

Gespeichert wird jetzt nur noch, was die Kernaufgabe braucht: der Hash. Eine
Zeile ist 17 Byte statt ~300, aus 67 MB im Jahr werden ~4 MB. Damit ist die
Datei auch nach zehn Jahren unter dem Limit - und niemand muss die Garantie
antasten, dass eine einmal berichtete Meldung nie wieder auftaucht. Genau
deshalb ist dieser Weg dem naheliegenderen "Eintraege aelter als N Monate
verwerfen" vorgezogen worden: undatierte Meldungen bleiben ueber
filter_fresh() dauerhaft einsammelbar (sie haben kein Alter, das aus dem
Frischefenster fallen koennte), eine Altersgrenze wuerde sie also nach Ablauf
ein zweites Mal in den Bericht lassen.

Format (v2), bewusst zeilenweise und append-only, damit git weiter nur den
angehaengten Block speichert:

    # Kopfzeile/Kommentar
    @2026-08-05T09:12:33+00:00     <- gilt fuer alle folgenden Hashes
    7a0a90bd7dba14dd
    832407f91e270301

Zeilen im alten JSON-Format werden weiter gelesen (ein Bestand ohne Migration
funktioniert also unveraendert); geschrieben wird nur noch v2. Die einmalige
Umschreibung des Bestands macht scripts/migriere_seen_store.py.

Was mit dem alten Format verloren geht, ist die Zuordnung Meldung -> Quelle.
Die wird nicht mehr hier gebraucht: das Laufprotokoll haelt seit 08/2026 je
Quelle fest, wie viele ihrer Meldungen NEU waren ("new"), und genau daraus
rechnet scripts/quellen_trefferquote.py. Der historische Bestand ist vor der
Migration einmal nach data/state/quellen_register.json ausgewertet worden.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .models import Item

log = logging.getLogger(__name__)

KOPFZEILE = ("# telco-radar seen-store v2 - ein Item-Hash je Zeile, '@' setzt "
             "den Zeitstempel\n")


class SeenStore:
    """Append-only Speicher der Item-Hashes, die schon einmal gesammelt wurden.

    Bewusst ein `set` und kein `dict`: die Meldung selbst steht im Bericht,
    hier interessiert nur noch die Frage "kenne ich diesen Hash?". Bei 233 000
    Eintraegen im Jahr ist das auch der Unterschied zwischen ~16 MB und ~70 MB
    Arbeitsspeicher.
    """

    def __init__(self, path: Path):
        self.path = path
        self._seen: set[str] = set()
        self._letzter_stempel: str | None = None
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("@"):
                        self._letzter_stempel = line[1:]
                        continue
                    if line.startswith("{"):
                        # Altbestand (v1). Wird gelesen, aber nie geschrieben.
                        try:
                            self._seen.add(json.loads(line)["id"])
                        except (json.JSONDecodeError, KeyError):
                            log.warning("Ueberspringe defekte Zeile im "
                                        "Seen-Store: %.80s", line)
                        continue
                    self._seen.add(line)

    def __len__(self) -> int:
        return len(self._seen)

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._seen

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
        neu = []
        for item in items:
            if item.id in self._seen:
                continue
            self._seen.add(item.id)
            neu.append(item.id)
        if not neu:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        neu_angelegt = not self.path.exists() or self.path.stat().st_size == 0
        with open(self.path, "a", encoding="utf-8") as fh:
            if neu_angelegt:
                fh.write(KOPFZEILE)
            fh.write("@" + datetime.now(timezone.utc).isoformat() + "\n")
            fh.write("".join(h + "\n" for h in neu))


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
