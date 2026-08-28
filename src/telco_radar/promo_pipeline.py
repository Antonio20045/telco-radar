"""Promo-Uebersicht Pipeline-Stufe: Snapshot-Diff -> LLM-Extraktion -> DB ->
Bericht.

Ein eigener, in sich geschlossener Zweig neben dem Haupt-Collect/Analyze-
Ablauf in pipeline.py: andere Quellenart (Endkunden-Aktionsseiten statt
Presse-Newsrooms), anderer Collector (Snapshot-Diff statt RSS/Newsroom),
eigener persistenter State (data/state/promo_snapshots.json,
data/state/promo_db.json). Failsafe wie die Differenzierungs-Zweige: ein
Fehler hier bricht den Gesamtlauf nie ab (siehe pipeline.py, wo dieser Aufruf
in try/except steht).
"""
from __future__ import annotations

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from . import promo_bilder
from .analyze import promo_editor, promo_ranker
from .analyze.promo_analyst import PromoExtractionError, extract_promos
from .analyze.promo_store import PromoDB, SnapshotStore, snapshot_key
from .collect.promo_snapshot import content_hash, fetch_snapshot
from .promo_config import load_promo_config

log = logging.getLogger(__name__)


def _fetch_one(src, page, http_cfg: dict) -> dict:
    """Runs in a worker thread: fetch + hash only, no shared state touched -
    keeps this safe to parallelise like collect/__init__.py's collect_all.

    Abgefragt wird eine SEITE, nicht eine Marke: seit dem 08.08.2026 hat
    eine Marke mehrere (promo_config.PromoSource.pages). Deshalb steht im
    Protokolleintrag beides - `brand` fuer die Zuordnung, `url`/`label` fuer
    die Seite. `leitseite` markiert die Seite, die die Marke auf der
    Uebersicht verlinkt."""
    rec = {"brand": src.name, "url": page.url, "tier": src.tier,
           "kind": page.kind, "label": page.label,
           "leitseite": page.url == src.url}
    try:
        snap = fetch_snapshot(page.url, page.kind, http_cfg)
        rec["text"] = snap["text"]
        rec["links"] = snap.get("links") or []
        rec["hash"] = content_hash(snap["text"], rec["links"])
        rec["image_url"] = snap.get("image_url")
        rec["images"] = snap.get("images") or []
    except Exception as exc:  # noqa: BLE001
        rec["status"] = "fail"
        rec["error"] = f"{type(exc).__name__}: {str(exc)[:140]}"
    return rec


def _resolve_item_url(item_url: str | None, brand_url: str) -> str:
    """The LLM-selected deep link if extract_promos() found one, else the
    brand's configured overview URL - exactly the pre-deep-links behaviour
    in the fallback case, never worse (see
    claude/promo-tiefenlinks-konzept.md Anforderung 2)."""
    return (item_url or "").strip() or brand_url


def _seiten_gelesen(zaehler: dict, gesamt: int) -> int:
    """Wie viele der abgefragten Seiten wirklich ABGERUFEN wurden.

    "gelesen" ist der Abruf, nicht die Extraktion danach - eine Seite mit
    gescheiterter Extraktion (`extraktion_fehlgeschlagen`) wurde trotzdem
    gelesen, nur ihr Ergebnis kam nicht an. Nur ein fehlgeschlagener
    Seitenabruf selbst (`fail`) zaehlt nicht als gelesen.
    """
    return gesamt - zaehler.get("fail", 0)


def _angebote_neu(results: list[dict]) -> int:
    """Angebote, die es in der Datenbank vorher NICHT gab (`upsert.neu`)."""
    return sum(r.get("new_items") or 0 for r in results)


def _angebote_bestaetigt(results: list[dict]) -> int:
    """Bekannte Angebote, die in diesem Lauf wiedergefunden wurden.

    Die zweite Zahl, und sie beantwortet eine andere Frage als die erste.
    Bis zum 27.08.2026 wies das Protokoll nur die NEUEN aus und nannte sie
    "aktualisiert": eine ruhige Woche meldete damit "0 Angebote
    aktualisiert" - dasselbe Bild wie ein stiller Totalausfall der
    Extraktion. Erst beide Zahlen nebeneinander unterscheiden die Faelle.
    """
    return sum(r.get("confirmed_items") or 0 for r in results)


def run_promo_stage(root: Path, http_cfg: dict, use_llm: bool, model: str,
                    language: str = "Deutsch", max_workers: int = 4,
                    settings: dict | None = None,
                    score_model: str | None = None,
                    extract_model: str | None = None) -> dict:
    """Fuehrt den Promo-Uebersicht-Zweig aus. Gibt einen Status-Dict fuer das
    Protokoll zurueck. Wirft nur bei fatalen Konfigurationsfehlern - einzelne
    Quellenfehler werden pro Quelle abgefangen und geloggt.

    Der Seitenabruf laeuft nebenlaeufig (I/O-lastig, ~17 Quellen, mehrere
    davon per Playwright) - gleiches Muster wie collect_all(). Diff-Check,
    LLM-Extraktion und DB-Update laufen danach sequentiell, weil sie den
    gemeinsamen State (SnapshotStore/PromoDB) mutieren."""
    today = date.today().isoformat()
    state_dir = root / "data" / "state"
    reports_dir = root / "data" / "reports" / "promo"
    reports_dir.mkdir(parents=True, exist_ok=True)

    promo_cfg = load_promo_config(root)
    snap_store = SnapshotStore(state_dir / "promo_snapshots.json")
    db = PromoDB(state_dir / "promo_db.json")

    sources = promo_cfg.crawled_sources
    by_name = {s.name: s for s in sources}
    # Ein Auftrag je SEITE, nicht je Marke. Die Nebenlaeufigkeit wirkt damit
    # auch INNERHALB einer Marke - eine Marke mit fuenf Seiten haelt den Lauf
    # nicht fuenfmal so lange auf wie eine mit einer.
    auftraege = [(src, page) for src in sources for page in src.crawled_pages]
    fetched: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = [pool.submit(_fetch_one, src, page, http_cfg)
                   for src, page in auftraege]
        for fut in as_completed(futures):
            fetched.append(fut.result())
    fetched.sort(key=lambda r: (r["brand"], not r["leitseite"], r["url"]))

    # Bildkandidaten je Marke, aus DIESEM Abruf (siehe promo_bilder.py). Sie
    # entstehen im selben Seitenaufruf wie Text und Links - anders als der
    # Screenshot-Pfad davor, der je Marke einen zweiten, eigenen Chromium
    # startete. Gesammelt wird fuer jede erfolgreich abgerufene Marke, auch
    # fuer eine unveraenderte: ein Angebot aus einem frueheren Lauf kann
    # sehr wohl noch ohne Bild dastehen.
    bild_kandidaten: dict[str, list[dict]] = {}

    # Je Marke sammeln, was in DIESEM Lauf wirklich neu gelesen wurde:
    # welche Seiten (URLs) und welche Angebots-IDs dabei wiedergefunden
    # wurden. mark_stale() laeuft erst, wenn alle Seiten der Marke durch
    # sind - sonst wuerde die erste Seite die Angebote der zweiten altern
    # lassen, bevor diese ueberhaupt gelesen ist.
    gepruefte_seiten: dict[str, set[str]] = {}
    gesehene_ids: dict[str, set[str]] = {}

    results: list[dict] = []
    for rec in fetched:
        if rec.get("status") == "fail":
            log.warning("Promo-Snapshot fehlgeschlagen (%s / %s): %s",
                       rec["brand"], rec["url"], rec.get("error"))
            results.append(rec)
            continue
        src_name, text, h = rec["brand"], rec.pop("text"), rec.pop("hash")
        page_url = rec["url"]
        links = rec.pop("links", [])
        image_url = rec.get("image_url")
        # Das og:image der Seite haengt hinten an: es ist der schwaechste
        # Kandidat (meist ein generisches Markenlogo, siehe
        # collect/promo_snapshot.extract_hero_image), aber der einzige fuer
        # eine Seite, aus der sich kein einziges <img> lesen laesst. Als
        # LETZTER in der Liste kommt er nur zum Zug, wenn nichts davor
        # taugte - genau die Rolle, die ihm zusteht.
        # Bildkandidaten ALLER Seiten einer Marke landen in einem Topf: das
        # Motiv eines Angebots steht nicht zwangslaeufig auf der Seite, auf
        # der der Text gefunden wurde (eine Uebersicht zeigt die Kachel, die
        # Detailseite den Text). promo_bilder.zuordnen() entscheidet ueber
        # Anker und Textnaehe, nicht ueber die Herkunftsseite.
        # `page` haelt fest, VON WELCHER Seite ein Kandidat stammt. Stufe 4
        # der Zuordnung (promo_bilder._seitenmotive) vergibt das Buehnenbild
        # je Seite; ohne diese Marke bekaeme eine Marke mit sieben Seiten
        # weiterhin genau ein Motiv.
        seiten_bilder = rec.pop("images", []) + (
            [{"src": image_url, "anchor": "", "context": "", "hint_w": 0}]
            if image_url else [])
        for kandidat in seiten_bilder:
            kandidat["page"] = page_url
        bild_kandidaten.setdefault(src_name, []).extend(seiten_bilder)
        key = snapshot_key(src_name, page_url)
        # Der reine Markenschluessel ist der Stand VOR dem 08.08.2026. Er
        # zaehlt nur fuer die Leitseite und nur so lange, bis der neue
        # Schluessel einmal geschrieben wurde.
        legacy = src_name if rec.get("leitseite") else None
        changed = snap_store.changed(key, h, legacy_key=legacy)
        # Den Stand IMMER unter dem SEITENschluessel festhalten, auch wenn er
        # sich nicht geaendert hat. Das stand bis Lauf #83 hinter dem
        # `continue` weiter unten - mit der Folge, dass genau die unveraenderte
        # Leitseite ihren neuen Schluessel nie bekam: sie galt ueber den alten
        # Markenschluessel als unveraendert, sprang aus der Schleife, und
        # prune() raeumte den alten Schluessel danach weg. Ergebnis in #83:
        # 10 der 15 Leitseiten standen anschliessend ohne Hash da und waeren
        # in JEDEM weiteren Lauf erneut durch die LLM-Extraktion gegangen,
        # ohne dass sich etwas geaendert hat. Ein Schreibvorgang mehr je
        # Seite ist dagegen kostenlos.
        snap_store.update(key, h, today)
        try:
            if not changed:
                rec["status"] = "unveraendert"
                results.append(rec)
                continue
            if use_llm and text.strip():
                # Extraktion ist Mechanik (Angebote aus HTML lesen), die
                # Promo-Redaktion unten (promo_editor.synthesize) bleibt auf
                # dem Redaktionsmodell - dieselbe Trennung wie in der
                # Hauptpipeline (_mechanik_modell).
                items = extract_promos(src_name, text,
                                       extract_model or model, links=links)
                for it in items:
                    it["tier"] = rec["tier"]
                    it["url"] = _resolve_item_url(it.get("url"), page_url)
                    it["image_url"] = image_url
                bilanz = db.upsert(items, today, source_url=page_url)
                gepruefte_seiten.setdefault(src_name, set()).add(page_url)
                gesehene_ids.setdefault(src_name, set()).update(bilanz.gesehene_ids)
                rec["status"] = "ok"
                rec["new_items"] = bilanz.neu
                rec["confirmed_items"] = bilanz.bestaetigt
                rec["extracted"] = len(items)
            else:
                rec["status"] = "changed_no_llm"
        except PromoExtractionError as exc:
            # Der Aufruf ist gescheitert, nicht die Seite. Sie kommt bewusst
            # NICHT in gepruefte_seiten - damit laesst mark_stale ihre
            # bestehenden Angebote unangetastet, statt sie wegen eines
            # API-Aussetzers Richtung "ausgelaufen" zu schieben.
            rec["status"] = "extraktion_fehlgeschlagen"
            rec["error"] = str(exc)
            log.warning("Promo-Extraktion fehlgeschlagen (%s / %s): %s - "
                        "Angebote dieser Seite bleiben unveraendert",
                        src_name, page_url, rec["error"])
        except Exception as exc:  # noqa: BLE001
            rec["status"] = "fail"
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:140]}"
            log.warning("Promo-Verarbeitung fehlgeschlagen (%s / %s): %s",
                       src_name, page_url, rec["error"])
        results.append(rec)

    # Alterung erst NACH allen Seiten einer Marke, und nur fuer die Seiten,
    # die diesmal wirklich neu gelesen wurden (siehe PromoDB.mark_stale).
    for brand, seiten in gepruefte_seiten.items():
        src = by_name.get(brand)
        db.mark_stale(brand, gesehene_ids.get(brand, set()), today,
                      gepruefte_seiten=seiten,
                      leitseite=src.url if src else "")

    entfernt = snap_store.prune(
        snapshot_key(s.name, p.url) for s in sources for p in s.crawled_pages)
    if entfernt:
        log.info("Promo-Snapshots: %d veraltete Schluessel entfernt", entfernt)
    snap_store.save()

    # Wichtigkeits-Score: laeuft ueber ALLE nicht-ausgelaufenen Eintraege der
    # DB, nicht nur ueber die dieses Mal neu extrahierten - ein Angebot, das
    # seit drei Wochen unveraendert laeuft, ist deshalb ja nicht unwichtig.
    # Die teuren LLM-Achsen werden trotzdem nur einmal je Angebotstext
    # angefragt und danach eingefroren (siehe promo_ranker.needs_judgement),
    # der Dauerbetrieb kostet also nur die paar wirklich neuen Angebote.
    # Failsafe wie ueberall hier: ein Fehler laesst die Scores unveraendert,
    # bricht aber weder diesen Zweig noch den Gesamtlauf ab.
    score_summary: dict = {}
    try:
        score_summary = promo_ranker.score_all(
            list(db.entries.values()), promo_cfg.sources, today,
            model=score_model or model, use_llm=use_llm, settings=settings,
            max_workers=max_workers)
        log.info("Promo-Bewertung: %d Angebote bewertet, %d neu beurteilt, "
                 "%d ohne Urteil, %d Highlights (Schwelle %d/%d)",
                 score_summary.get("scored", 0), score_summary.get("judged_new", 0),
                 score_summary.get("judged_failed", 0),
                 score_summary.get("highlights", 0),
                 score_summary.get("enter", 0), score_summary.get("exit", 0))
    except Exception as exc:  # noqa: BLE001
        log.warning("Promo-Bewertung uebersprungen: %s", str(exc)[:160])

    # Kampagnenbilder: je Angebot das Motiv, das die Aktionsseite dafuer
    # zeigt (siehe promo_bilder.py). Laeuft NACH der Bewertung, weil die
    # Reihenfolge der Angebote entscheidet, wer ein doppelt belegtes Bild
    # bekommt - das hoeher bewertete Angebot. Fehler je Marke werden
    # einzeln gefangen: eine Karte ohne Bild wird eine Zeile, nie ein
    # Abbruch.
    bilder_bilanz: Counter = Counter()
    for brand, kandidaten in bild_kandidaten.items():
        if not kandidaten:
            continue
        sichtbar = sorted(
            (e for e in db.entries.values()
             if e.get("brand") == brand
             and e.get("status") in ("aktiv", "evtl. ausgelaufen")),
            key=lambda e: -(e.get("score") or 0))
        if not sichtbar:
            continue
        try:
            zuordnung = promo_bilder.zuordnen(
                sichtbar, kandidaten,
                leitseite=by_name[brand].url if brand in by_name else "")
            bilder_bilanz.update(
                promo_bilder.hole_bilder(zuordnung, db.entries, root))
        except Exception as exc:  # noqa: BLE001
            log.warning("Promo-Bilder (%s) uebersprungen: %s", brand, str(exc)[:160])
    if bilder_bilanz:
        log.info("Promo-Bilder: %d von %d Angeboten haben eins (%s)",
                 bilder_bilanz["geladen"] + bilder_bilanz["unveraendert"],
                 bilder_bilanz["geprueft"],
                 ", ".join(f"{k}={v}" for k, v in sorted(bilder_bilanz.items())))
    promo_bilder.raeume_auf(root, list(db.entries.values()))

    db.save(today)

    entries = list(db.entries.values())
    try:
        if use_llm and entries:
            body = promo_editor.synthesize(entries, model=model, language=language)
            mode = "KI-Redaktion"
        else:
            body = promo_editor.build_digest(entries)
            mode = "Regelbericht"
    except Exception as exc:  # noqa: BLE001
        log.warning("Promo-Redaktion fehlgeschlagen (%s) - verwende Regelbericht",
                   str(exc)[:160])
        body = promo_editor.build_digest(entries)
        mode = "Regelbericht (Fallback)"

    (reports_dir / f"{today}.md").write_text(body, encoding="utf-8")
    active = sum(1 for e in entries if e.get("status") == "aktiv")
    zaehler = Counter(r.get("status") for r in results)
    log.info("Promo-Uebersicht: %s (%d aktive Aktionen, %d Marken / %d Seiten "
             "abgefragt: %s)",
             mode, active, len(sources), len(auftraege),
             ", ".join(f"{n}x {s}" for s, n in sorted(zaehler.items())))
    # Gescheiterte Extraktionen einzeln benennen. Ein Sammelzaehler reicht
    # hier nicht: nach Lauf #83 war unklar, ob Telekom nichts LIEFERTE oder
    # ob die Extraktion scheiterte - und genau diese Frage entscheidet, ob
    # eine Quelle taugt oder nur gerade Pech hatte.
    gescheitert = [r for r in results if r.get("status") == "extraktion_fehlgeschlagen"]
    if gescheitert:
        log.warning("Promo: %d Seite(n) mit gescheiterter Extraktion - ihre "
                    "Angebote wurden NICHT gealtert: %s", len(gescheitert),
                    "; ".join(f"{r['brand']} {r['url']} ({r.get('error','')})"
                              for r in gescheitert))
    # Wie viele Seiten haben wirklich etwas beigetragen? Die Zahl beantwortet
    # die Frage, um die es beim Ausbau geht - eine Seite, die ueber Wochen
    # 0 Angebote liefert, ist Ballast.
    ergiebig = sum(1 for r in results if r.get("extracted"))
    log.info("Promo-Ergiebigkeit: %d von %d gelesenen Seiten lieferten "
             "mindestens ein Angebot", ergiebig, zaehler.get("ok", 0))
    # Drei Zahlen fuers Laufprotokoll (pipeline.py::stats, siehe dort): der
    # Ausfall seit dem 14.08.2026 (Strategie 2026-08-27, B6) stand sonst in
    # KEINER Statistik, nur im Actions-Log, das niemand liest.
    return {"mode": mode, "sources": results, "db_size": len(db), "active": active,
            "images": dict(bilder_bilanz),
            "brands": len(sources), "pages": len(auftraege),
            "status": dict(zaehler), "ergiebig": ergiebig,
            "extraktion_fehlgeschlagen": len(gescheitert),
            "seiten_gelesen": _seiten_gelesen(zaehler, len(auftraege)),
            "angebote_neu": _angebote_neu(results),
            "angebote_bestaetigt": _angebote_bestaetigt(results),
            "score": score_summary}
