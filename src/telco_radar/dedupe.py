"""Novelty layer: persistent 'seen' store + freshness filter.

This is the heart of "only report what is new":
- every item id (hash of normalized URL) that was ever collected is stored
  in data/state/seen.tsv (git-versioned, one short line per id)
- a second store data/state/reported_topics.jsonl remembers which topics the
  editor already covered, so reports never repeat themselves
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from .models import Item

log = logging.getLogger(__name__)


# Tag 0 des kompakten Formats. Ein fester Bezugspunkt statt eines
# Zeitstempels je Zeile: die Tagesnummer braucht 4-5 Zeichen statt 32.
EPOCHE = date(2020, 1, 1)

KOPFZEILE = (
    "# telco-radar seen-store v1 - eine Zeile je jemals gesammelter Meldung.\n"
    "# Spalten: <id>\\t<tag>   id = sha256 der normalisierten URL (16 Zeichen),\n"
    "# tag = Tage seit 2020-01-01, an denen sie zuerst gesehen wurde, oder 'u'\n"
    "# fuer Meldungen ohne erkanntes Datum. 'u'-Zeilen verfallen NIE.\n"
)

# Ab wie vielen verfallenen Zeilen die Datei beim naechsten Schreiben neu
# geschrieben wird. Ein Rewrite erzeugt einen grossen Git-Diff, deshalb nicht
# bei jedem Lauf - aber oft genug, dass die Datei nicht ueber ihr Verfallsmass
# hinauswaechst.
_KOMPAKTIEREN_AB = 2000


def _tagesnummer(wann: datetime | date | None = None) -> int:
    if wann is None:
        wann = datetime.now(timezone.utc)
    if isinstance(wann, datetime):
        wann = wann.date()
    return (wann - EPOCHE).days


class SeenStore:
    """Append-only Store der bereits gesammelten Item-IDs.

    Warum kein JSONL mit URL und Titel mehr
    ---------------------------------------
    Bis Session 4 stand je Eintrag id, volle URL, Titel, Quelle und ein
    ISO-Zeitstempel - rund 300 Byte. Bei 1000 Quellen sind das ~233 000
    Eintraege im Jahr, also ~67 MB/Jahr in einer git-versionierten Datei,
    deren hartes Limit bei GitHub 100 MB betraegt. Das war kein
    Komfortproblem, sondern ein Ablaufdatum.

    Jetzt steht je Eintrag nur noch der Hash und die Tagesnummer: ~22 Byte,
    also ~5 MB/Jahr. URL und Titel gehen dabei nicht verloren - sie stehen
    im Berichtsarchiv (data/reports/*.json), wo man sie tatsaechlich sucht.

    Verfall, ohne die Kerngarantie anzutasten
    -----------------------------------------
    Die Garantie lautet: was einmal berichtet wurde, kommt nie wieder.
    Eintraege verfallen deshalb nur unter einer Bedingung, die genau das
    sicherstellt: Die Meldung hatte ein erkanntes Datum. Taucht sie nach dem
    Verfall erneut auf einer Quellenseite auf, wirft der Frischefilter sie
    weg, weil ihr Datum weit ausserhalb des Frischefensters (8 Tage) liegt.
    Meldungen OHNE erkanntes Datum kann der Frischefilter nicht abfangen -
    die bleiben deshalb dauerhaft im Store, kosten aber fast nichts, weil sie
    die Minderheit sind.

    `max_age_days=None` schaltet den Verfall ganz ab; dann verhaelt sich der
    Store wie vorher, nur kompakter.
    """

    def __init__(self, path: Path, max_age_days: int | None = None,
                 legacy_path: Path | None = None):
        self.path = path
        self.max_age_days = max_age_days
        self._seen: dict[str, int | None] = {}
        self.verfallen = 0
        self._migriert = False
        heute = _tagesnummer()
        grenze = None if max_age_days is None else heute - int(max_age_days)

        if path.exists():
            zeilen = path.read_text(encoding="utf-8").splitlines()
            if any(z.lstrip().startswith("{") for z in zeilen[:3]):
                # Jemand zeigt mit dem neuen Store auf die alte Datei. Ohne
                # diese Weiche wuerde jede JSON-Zeile als ein einziger
                # (nie passender) Hash gelesen - das Gedaechtnis waere still
                # weg und der naechste Bericht wiederholte die halbe Woche.
                self._lese_legacy(path, grenze)
                self._migriert = True
            else:
                self._lesen(zeilen, grenze)
        else:
            # Altbestand uebernehmen. Ein Lauf, der das Gedaechtnis verliert,
            # wuerde die halbe Woche doppelt berichten - der Import laeuft
            # deshalb automatisch und nicht nur per Migrationsskript.
            alt = legacy_path if legacy_path is not None else \
                path.with_suffix(".jsonl")
            if alt.exists():
                anzahl = self._lese_legacy(alt, grenze)
                self._migriert = True
                log.info("Seen-Store: %d Eintraege aus %s uebernommen",
                         anzahl, alt.name)

        if self.verfallen:
            log.info("Seen-Store: %d Eintraege aelter als %s Tage verfallen "
                     "(nur datierte - undatierte bleiben dauerhaft)",
                     self.verfallen, max_age_days)

    # ------------------------------------------------------------- lesen
    def _lesen(self, zeilen: list[str], grenze: int | None) -> None:
        for zeile in zeilen:
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#"):
                continue
            teile = zeile.split("\t")
            ident = teile[0]
            if len(ident) < 4:
                log.warning("Seen-Store: unbrauchbare Zeile %.40s", zeile)
                continue
            roh = teile[1] if len(teile) > 1 else "u"
            if roh == "u":
                self._seen[ident] = None
                continue
            try:
                tag = int(roh)
            except ValueError:
                self._seen[ident] = None
                continue
            if grenze is not None and tag < grenze:
                self.verfallen += 1
                continue
            self._seen[ident] = tag

    def _lese_legacy(self, pfad: Path, grenze: int | None) -> int:
        """Das alte JSONL-Format einlesen (id/url/title/source/first_seen)."""
        vorher = len(self._seen)
        with open(pfad, "r", encoding="utf-8") as fh:
            for zeile in fh:
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    rec = json.loads(zeile)
                    ident = rec["id"]
                except (json.JSONDecodeError, KeyError):
                    log.warning("Seen-Store: unbrauchbare Altzeile %.60s", zeile)
                    continue
                tag = None
                gesehen = rec.get("first_seen")
                if isinstance(gesehen, str) and gesehen:
                    try:
                        tag = _tagesnummer(datetime.fromisoformat(gesehen))
                    except ValueError:
                        tag = None
                if tag is not None and grenze is not None and tag < grenze:
                    self.verfallen += 1
                    continue
                self._seen[ident] = tag
        return len(self._seen) - vorher

    # ------------------------------------------------------------ abfragen
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

    # ------------------------------------------------------------ schreiben
    def add(self, items: list[Item]) -> None:
        heute = _tagesnummer()
        neu: list[tuple[str, int | None]] = []
        for item in items:
            if item.id in self._seen:
                continue
            # Undatiert heisst: der Frischefilter kann diese Meldung nie
            # abfangen. Solche Eintraege duerfen deshalb nicht verfallen.
            tag = heute if item.published is not None else None
            self._seen[item.id] = tag
            neu.append((item.id, tag))
        if not neu and not (self.verfallen or self._migriert):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Neu schreiben statt anhaengen, wenn genug verfallen ist oder gerade
        # aus dem Altformat uebernommen wurde - sonst stuende der Ballast
        # weiter in der Datei und der Verfall haette nichts gebracht.
        if self._migriert or self.verfallen >= _KOMPAKTIEREN_AB \
                or not self.path.exists():
            self.schreibe_neu()
            return
        with open(self.path, "a", encoding="utf-8") as fh:
            for ident, tag in neu:
                fh.write(f"{ident}\t{'u' if tag is None else tag}\n")

    def schreibe_neu(self) -> None:
        """Die ganze Datei neu schreiben (Kompaktierung / Migration)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        zeilen = [KOPFZEILE]
        zeilen.extend(f"{ident}\t{'u' if tag is None else tag}\n"
                      for ident, tag in self._seen.items())
        self.path.write_text("".join(zeilen), encoding="utf-8")
        self.verfallen = 0
        self._migriert = False


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
