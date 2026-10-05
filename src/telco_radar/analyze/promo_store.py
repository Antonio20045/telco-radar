"""Persistent state for the Promo-Uebersicht snapshot-diff pipeline.

Two separate stores, mirroring the split already used by the differentiation
branch (raw signal vs. curated display):

  SnapshotStore  data/state/promo_snapshots.json - one content hash per
                 SEITE (Marke + URL), used ONLY to detect "did this page
                 change since last run". Never shown on the site, never fed
                 to the LLM by itself. Je Seite, weil eine Marke mehrere
                 Seiten hat (promo_config.py).

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

import json
import logging
import re
from pathlib import Path
from typing import NamedTuple

from .promo_schluessel import (
    ID_FELD,
    ID_SCHLUESSEL,
    Schluessel,
    entry_id,
    id_aus_schluessel,
    migriere,
    rang,
    schluessel,
    schluessel_eintrag,
)

__all__ = ["PromoDB", "SnapshotStore", "UpsertBilanz", "entry_id", "snapshot_key"]

log = logging.getLogger(__name__)


class UpsertBilanz(NamedTuple):
    """Was EIN `PromoDB.upsert()`-Aufruf getan hat.

    Bewusst mit Namen statt als nacktes Tupel: die zwei Zahlen bedeuten
    Verschiedenes und wurden genau deshalb verwechselt. `neu` sind die
    Aktionen, die es vorher nicht gab; `bestaetigt` sind die bekannten, deren
    `last_verified` aufgefrischt wurde. Das Laufprotokoll wies bis zum
    27.08.2026 allein `neu` aus und nannte es "aktualisiert" - in einer
    ruhigen Woche stand dort "0 Angebote aktualisiert", obwohl siebzig
    Aktionen bestaetigt worden waren.
    """

    neu: int
    gesehene_ids: set[str]
    bestaetigt: int = 0


_FUZZY_HEADLINE_THRESHOLD = 0.6


def _normalize_headline(headline: str) -> str:
    return " ".join((headline or "").lower().split())


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text or ""))


def _word_overlap(headline_a: str, headline_b: str) -> float:
    words_a = set(_normalize_headline(headline_a).split())
    words_b = set(_normalize_headline(headline_b).split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / min(len(words_a), len(words_b))


def _same_offer(headline_a: str, headline_b: str) -> bool:
    """Heuristik fuer 'gleiches Angebot, nur anders formuliert'. Wort-
    Ueberlappung allein reicht nicht: "10 GB Bonus" und "20 GB Bonus" teilen
    sich fast alle Woerter, sind aber verschiedene Angebote - deshalb
    zusaetzlich ein Zahlen-Waechter: enthalten beide Headlines Zahlen (GB,
    Euro-Betraege, Alters-/Preisgrenzen - genau das, was ein Angebot von
    einem sonst fast gleich klingenden anderen unterscheidet) und haben sie
    KEINE einzige davon gemeinsam, ist es kein Match, egal wie aehnlich der
    Text sonst ist."""
    if _word_overlap(headline_a, headline_b) < _FUZZY_HEADLINE_THRESHOLD:
        return False
    nums_a, nums_b = _numbers(headline_a), _numbers(headline_b)
    if nums_a and nums_b and nums_a.isdisjoint(nums_b):
        return False
    return True


def snapshot_key(brand: str, url: str) -> str:
    """Schluessel einer Seite im SnapshotStore. Marke UND URL, weil eine
    Marke seit dem 08.08.2026 mehrere Seiten haben kann und jede ihren
    eigenen Aenderungsstand braucht."""
    return f"{(brand or '').strip()} | {(url or '').strip()}"


class SnapshotStore:
    """Last-known content hash per page, for change detection only."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._by_key: dict[str, dict] = {}
        if self.path.exists():
            try:
                self._by_key = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("promo_snapshots.json unlesbar - starte leer")

    def changed(self, key: str, text_hash: str, legacy_key: str | None = None) -> bool:
        """Hat sich diese Seite seit dem letzten Lauf geaendert?

        *legacy_key* ist der alte, reine Markenschluessel. Er wird nur
        gelesen, wenn der neue Seitenschluessel noch gar nicht existiert -
        also genau einmal, beim ersten Lauf nach der Umstellung. Ohne diesen
        Rueckfall wuerde jede Leitseite dort einmal grundlos als veraendert
        gelten und eine komplette LLM-Neuextraktion ueber alle Marken
        ausloesen."""
        rec = self._by_key.get(key)
        if rec is None and legacy_key:
            rec = self._by_key.get(legacy_key)
        return (rec or {}).get("hash") != text_hash

    def update(self, key: str, text_hash: str, fetched_at: str) -> None:
        self._by_key[key] = {"hash": text_hash, "fetched_at": fetched_at}

    def prune(self, gueltige_keys) -> int:
        """Schluessel entfernen, die keiner konfigurierten Seite mehr
        entsprechen - die alten Marken-Schluessel nach der Umstellung, und
        spaeter jede aus der YAML entfernte Seite. Gibt zurueck, wie viele
        Eintraege gefallen sind."""
        gueltig = set(gueltige_keys)
        veraltet = [k for k in self._by_key if k not in gueltig]
        for k in veraltet:
            del self._by_key[k]
        return len(veraltet)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._by_key, ensure_ascii=False, indent=1), encoding="utf-8"
        )


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
                roh = raw.get("entries", [])
                if raw.get(ID_FELD) == ID_SCHLUESSEL:
                    self.entries = {e["id"]: e for e in roh if e.get("id")}
                else:
                    self.entries = migriere(roh)
            except (json.JSONDecodeError, OSError):
                log.warning("promo_db.json unlesbar - starte leer")

    def __len__(self) -> int:
        return len(self.entries)

    def _find_existing_id(
        self, stamm: Schluessel, headline: str, vergeben: set[str]
    ) -> str | None:
        """Rückfall nach dem Schlüssel: unter den noch nicht vergebenen
        Einträgen derselben Marke und Zielseite der laut _same_offer()
        textlich ähnlichste."""
        best_id, best_overlap = None, 0.0
        for eid, e in self.entries.items():
            if eid in vergeben or schluessel_eintrag(e)[:2] != stamm[:2]:
                continue
            existing_headline = e.get("headline") or ""
            if not _same_offer(headline, existing_headline):
                continue
            overlap = _word_overlap(headline, existing_headline)
            if overlap > best_overlap:
                best_id, best_overlap = eid, overlap
        return best_id

    def upsert(
        self, items: list[dict], today: str, source_url: str = ""
    ) -> "UpsertBilanz":
        """Neue Aktionen aufnehmen, bekannte bestätigen; gibt die
        `UpsertBilanz` zurück. Ihre IDs gehen als checked_ids an mark_stale().
        *source_url* ist die gelesene Seite, mark_stale() altert nur deren
        Angebote.

        Abgleich: zuerst gleicher Schlüssel und gleiche Überschrift, dann
        gleicher Schlüssel, dann _same_offer unter derselben Marke und
        Zielseite. Ein Eintrag wird je Aufruf höchstens einmal bestätigt; ein
        weiteres Angebot mit gleichem Schlüssel bekommt die nächste
        Laufnummer, dieselbe Überschrift zweimal ist ein Angebot."""
        angebote: list[tuple[dict, str, Schluessel, tuple[Schluessel, str]]] = []
        for it in items:
            brand = (it.get("brand") or "").strip()
            headline = (it.get("headline") or "").strip()
            if not brand or not headline:
                continue
            stamm = schluessel(brand, it.get("url"), source_url, it.get("description"))
            angebote.append(
                (it, headline, stamm, (stamm, _normalize_headline(headline)))
            )
        nach_stamm: dict[Schluessel, list[str]] = {}
        for eid, e in self.entries.items():
            nach_stamm.setdefault(schluessel_eintrag(e), []).append(eid)
        vergeben: set[str] = set()
        im_aufruf: dict[tuple[Schluessel, str], str] = {}
        for _, _, stamm, kopf in angebote:
            gleich = [
                eid
                for eid in nach_stamm.get(stamm, [])
                if eid not in vergeben and self._kopf(eid) == kopf[1]
            ]
            if gleich and kopf not in im_aufruf:
                eid = max(gleich, key=lambda k: rang(self.entries[k]))
                vergeben.add(eid)
                im_aufruf[kopf] = eid
        neu_ids: set[str] = set()
        for it, headline, stamm, kopf in angebote:
            if kopf in im_aufruf:
                continue
            frei = [eid for eid in nach_stamm.get(stamm, []) if eid not in vergeben]
            treffer = self._gleicher_schluessel(frei, headline)
            if treffer is None:
                treffer = self._find_existing_id(stamm, headline, vergeben)
            if treffer is None:
                treffer = self._lege_an(it, headline, stamm, today, source_url)
                neu_ids.add(treffer)
            vergeben.add(treffer)
            im_aufruf[kopf] = treffer
        for it, headline, _, kopf in angebote:
            eid = im_aufruf[kopf]
            if eid not in neu_ids:
                self._bestaetige(self.entries[eid], it, headline, today, source_url)
        return UpsertBilanz(len(neu_ids), vergeben, len(vergeben - neu_ids))

    def _gleicher_schluessel(self, frei: list[str], headline: str) -> str | None:
        """Unter freien Einträgen gleichen Schlüssels zuerst _same_offer, dann
        aktiv, dann zuletzt bestätigt."""
        if not frei:
            return None
        return max(
            frei,
            key=lambda k: (
                _same_offer(headline, self.entries[k].get("headline") or ""),
                *rang(self.entries[k]),
            ),
        )

    def _kopf(self, eid: str) -> str:
        return _normalize_headline(self.entries[eid].get("headline") or "")

    def _lege_an(
        self, it: dict, headline: str, stamm: Schluessel, today: str, source_url: str
    ) -> str:
        """Neuer Eintrag mit der kleinsten freien Laufnummer seines Schlüssels."""
        laufnummer = 1
        while id_aus_schluessel(stamm, laufnummer) in self.entries:
            laufnummer += 1
        eid = id_aus_schluessel(stamm, laufnummer)
        self.entries[eid] = {
            "id": eid,
            "brand": (it.get("brand") or "").strip(),
            "tier": it.get("tier"),
            "headline": headline,
            "description": it.get("description", ""),
            "valid_until": it.get("valid_until"),
            "url": it.get("url", ""),
            "image_url": it.get("image_url"),
            "source_url": source_url,
            "first_seen": today,
            "last_verified": today,
            "status": "aktiv",
            "missed_checks": 0,
        }
        return eid

    @staticmethod
    def _bestaetige(
        e: dict, it: dict, headline: str, today: str, source_url: str
    ) -> None:
        """Wiedergefunden: aktiv, Fehltreffer zurück, Felder aufgefrischt."""
        e["headline"] = headline
        e["last_verified"] = today
        e["status"] = "aktiv"
        e["missed_checks"] = 0
        e.pop("stale_since", None)
        if source_url:
            e["source_url"] = source_url
        for feld in ("description", "valid_until", "url", "image_url"):
            if it.get(feld):
                e[feld] = it[feld]

    def mark_stale(
        self,
        brand: str,
        checked_ids: set,
        today: str,
        gepruefte_seiten: set | None = None,
        leitseite: str = "",
    ) -> None:
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
        mit missed_checks=0.

        *gepruefte_seiten*: die URLs der Seiten dieser Marke, die in DIESEM
        Lauf wirklich neu extrahiert wurden. Nur Angebote von diesen Seiten
        koennen hier fehlen und damit altern. Das ist die Bedingung dafuer,
        dass mehrere Seiten je Marke ueberhaupt funktionieren: eine Marke mit
        vier Seiten hat pro Lauf typischerweise EINE geaenderte, und ohne
        diese Einschraenkung wuerden die Angebote der drei unveraenderten
        jedes Mal einen Schritt Richtung "ausgelaufen" ruecken - nach zwei
        Laeufen waere die halbe Marke verschwunden, obwohl sich nichts
        geaendert hat. None = alte Bedeutung (alle Eintraege der Marke),
        fuer Aufrufer, die noch keine Seiten kennen.

        *leitseite*: Heimatseite fuer Bestandseintraege ohne `source_url`
        (angelegt, bevor es mehrere Seiten gab). Sie hingen alle an der
        einzigen damals konfigurierten Seite - also an der Leitseite."""
        for e in self.entries.values():
            if e.get("brand") != brand or e["id"] in checked_ids:
                continue
            if gepruefte_seiten is not None:
                heimat = (e.get("source_url") or leitseite or "").strip()
                if heimat not in gepruefte_seiten:
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
                reverse=True,
            )
        return out

    def save(self, today: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated": today,
            ID_FELD: ID_SCHLUESSEL,
            "entries": sorted(
                self.entries.values(),
                key=lambda e: (e.get("brand") or "", e.get("first_seen") or ""),
            ),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
