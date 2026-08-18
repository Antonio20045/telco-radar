"""Telco Radar pipeline: collect -> dedupe -> analyze -> report -> site.

Usage:
    python -m telco_radar.pipeline [--root .] [--no-llm] [--lookback-days N]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import zip_longest
from datetime import date, datetime, timezone
from pathlib import Path

from .analyze import editor
from .analyze import clustering
from .analyze import ctm as ctm_mod
from .analyze import faithfulness
from .analyze.agents import analyze_region
from .analyze import competitors as competitor_mod
from .analyze import diff_curator
from .analyze import category_sweep
from .analyze import differentiation_editor
from .analyze.diff_curator import DiffStore
from .analyze import highlight_topics
from .uebersetzung import stufe as uebersetzung_stufe
from .analyze import llm
from .analyze.llm import llm_available, active_backend
from .collect import collect_all, tag_news_regions
from .config import is_theme_key, load_config
from .dedupe import ReportedTopics, SeenStore, filter_fresh
from .models import Item
from .quellen_register import Quellenregister, quellen_der_config
from .report import bilder as report_bilder
from .report import diff_bilder
from .report import differenzierung_view
from .report.html import render_site

log = logging.getLogger("telco_radar")

LANGUAGES = {"de": "Deutsch", "en": "English"}

# Unter dieser Restzeit lohnt die Geraetestufe nicht: ein einzelner Anbieter
# mit zehn Sekunden Abstand je Abruf braucht Minuten, und ein halber Abruf
# ist ohnehin kein gelesener Anbieter (`bilanz.vollstaendig`). Lieber gar
# nicht anfangen als die Veroeffentlichung riskieren.
_GERAETE_MINDESTBUDGET = 240.0


def geraete_budget(settings: dict, verstrichen: float):
    """Wie viel Zeit die Geraetestufe im Wochenlauf noch bekommt.

    `None` heisst "nicht anfangen". Gerechnet wird gegen die RESTZEIT DES
    JOBS, nicht gegen das eigene Budget - genau daran ist Lauf 31422689829
    gescheitert. Die Reserve gehoert dem Rendern, Committen und Deployen;
    sie ist der Teil, den ein Nutzer zu sehen bekommt.
    """
    if not settings.get("geraete_enabled", False):
        return None
    rest = (float(settings.get("job_frist_sekunden", 3000)) - verstrichen
            - float(settings.get("veroeffentlichung_reserve_sekunden", 420)))
    if rest < _GERAETE_MINDESTBUDGET:
        return None
    return min(float(settings.get("geraete_frist_sekunden", 600)), rest)

# Anbieter, die das OpenAI-Chat-Protokoll sprechen, mit ihren
# Konfigurationsschluesseln: (Basis-URL, Analyst-Modell, Editor-Modell).
# Sie teilen sich EINEN Schluessel (LLM_API_KEY) - es kann also immer nur
# einer davon aktiv sein, was genau richtig ist: sonst muesste man im Secret
# raten, zu welchem Endpunkt der hinterlegte Schluessel gehoert.
OPENAI_KOMPATIBEL = {
    "openai": ("llm_api_base", "openai_analyst_model", "openai_editor_model"),
    "deepseek": ("deepseek_api_base", "deepseek_analyst_model",
                 "deepseek_editor_model"),
}

ANBIETER = ("auto", "anthropic", "bedrock", *OPENAI_KOMPATIBEL)


def _waehle_anbieter(settings: dict) -> str:
    """Legt den LLM-Anbieter fest und liefert seinen Namen.

    "auto" behaelt die alte Reihenfolge (Bedrock > OpenAI-kompatibel >
    Anthropic) und nimmt damit, welcher Schluessel gerade da ist. Genau das
    ist das Problem, das llm_provider loest: solange der NVIDIA-Schluessel im
    Repo liegt, gewinnt er, und Anthropic kaeme nie zum Zug.

    Bei einer expliziten Wahl werden die Schluessel der unterlegenen Anbieter
    aus der Prozessumgebung entfernt. Das ist noetig, weil llm.py seinen
    Backend allein aus der Umgebung ableitet - sonst wuerde hier der eine
    Anbieter die Modell-IDs bestimmen, waehrend dort der andere aufgerufen
    wird. Nur die Kopie dieses Prozesses ist betroffen.
    """
    wanted = str(settings.get("llm_provider", "auto") or "auto").lower()
    if wanted not in ANBIETER:
        log.warning("Unbekannter llm_provider %r - benutze auto", wanted)
        wanted = "auto"

    has_bedrock = bool(os.environ.get("AWS_BEARER_TOKEN_BEDROCK"))
    has_key = bool(os.environ.get("LLM_API_KEY"))

    if wanted == "auto":
        if has_bedrock:
            return "bedrock"
        return "openai" if (has_key and settings.get("llm_api_base")) else "anthropic"

    base_url = ""
    if wanted in OPENAI_KOMPATIBEL:
        base_url = str(settings.get(OPENAI_KOMPATIBEL[wanted][0]) or "")

    # Ein gewaehlter Anbieter ohne seinen Schluessel laesst jede Stufe
    # scheitern - das einmal deutlich sagen, statt es jeden Aufruf einzeln
    # herausfinden zu lassen.
    fehlt = ((wanted == "bedrock" and not has_bedrock)
             or (wanted in OPENAI_KOMPATIBEL and not (has_key and base_url))
             or (wanted == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY")))
    if fehlt:
        log.warning("llm_provider=%s, aber Schluessel oder Basis-URL fehlen - "
                    "der Lauf faellt auf den Notfall-Digest zurueck", wanted)

    if wanted != "bedrock":
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    if wanted not in OPENAI_KOMPATIBEL:
        os.environ.pop("LLM_API_KEY", None)
    elif base_url:
        # Muss HIER passieren, nicht erst beim Setzen der Modell-IDs: llm.py
        # erkennt den OpenAI-Zweig nur an LLM_API_KEY *und* LLM_API_BASE.
        # Fehlt die Basis-URL, waehlt es still einen anderen Anbieter - die
        # Wahl waere getroffen und nicht umgesetzt. Kein setdefault: beim
        # Wechsel von NVIDIA auf DeepSeek stuende sonst eine von aussen
        # gesetzte alte URL gegen den konfigurierten Anbieter.
        os.environ["LLM_API_BASE"] = base_url
    if wanted != "anthropic":
        # Auch den Anthropic-Schluessel entfernen. llm.py behandelt ihn sonst
        # als letzte Rueckfallebene: bei einem Tippfehler in der DeepSeek-URL
        # liefe der ganze Lauf still ueber Anthropic - also genau ueber den
        # teuren Anbieter, von dem hier gerade weggeschaltet wurde. Die
        # Warnung oben verspricht den Notfall-Digest; das hier haelt sie ein.
        os.environ.pop("ANTHROPIC_API_KEY", None)
    return wanted


def _modelle_fuer_anbieter(settings: dict, anbieter: str,
                           fallback_model: str) -> tuple[str, str]:
    """Liefert (Analystenmodell, Editormodell) des GEWAEHLTEN Anbieters.

    Als eigene Funktion herausgezogen, weil das Auseinanderlaufen von
    Anbieter und Modell-ID sich nicht selbst meldet: der Endpunkt antwortet
    einfach mit "unbekanntes Modell", die aufrufende Stufe faengt den Fehler
    ab, und der Lauf gilt als erfolgreich. Genau so stand die
    Wettbewerber-Seite zwei Laeufe lang leer da (siehe unten im
    Wettbewerber-Zweig). Jede Stufe holt ihr Modell ab jetzt hier.
    """
    if anbieter == "bedrock":
        # Which Claude models a Bedrock account may call is per-account and
        # changes without notice (agreements, quotas, AWS Sales). Instead of
        # pinning one id, register the configured preference chain and let the
        # run settle on the best model that actually answers.
        chain_head = llm.set_model_chain(settings.get("bedrock_model_chain") or [])
        return ((settings.get("bedrock_analyst_model") or chain_head or fallback_model),
                (settings.get("bedrock_editor_model") or chain_head or fallback_model))
    if anbieter in OPENAI_KOMPATIBEL:
        # Die Basis-URL hat _waehle_anbieter bereits gesetzt; hier nur noch
        # die Modelle des gewaehlten Endpunkts. NIE die Schluessel eines
        # anderen OpenAI-kompatiblen Anbieters lesen - sie zeigen auf einen
        # Endpunkt, der gerade nicht aktiv ist.
        _, analyst_key, editor_key = OPENAI_KOMPATIBEL[anbieter]
        return (settings.get(analyst_key) or fallback_model,
                settings.get(editor_key) or fallback_model)
    return (settings.get("analyst_model", fallback_model),
            settings.get("editor_model", fallback_model))


def _mechanik_modell(settings: dict, anbieter: str, fallback: str) -> str:
    """Das Modell der MECHANIK-Stufen (Uebersetzung, Clustering-Pruefung,
    Beleg-Pruefung, Promo-Extraktion/-Score, Kategorie-Sweep, CT-Radar,
    Diff-Kurator).

    Diese Stufen brauchen kein Urteil, nur Fleiss - und ein Denkspur-Modell
    wie deepseek-v4-pro bezahlt je Aufruf ~8-9k Token Nachdenken, egal wie
    klein die Aufgabe ist (18.08.2026, der groesste Kostenposten des Laufs).
    Der Schluessel folgt demselben Muster wie _modelle_fuer_anbieter
    (`<anbieter>_mechanik_model`); fehlt er, laeuft alles wie bisher auf dem
    uebergebenen Modell - ein Anbieter ohne den Eintrag verhaelt sich exakt
    wie vor dieser Aenderung.
    """
    return str(settings.get(f"{anbieter}_mechanik_model") or "").strip() or fallback


def _redaktion_zweistufig(settings: dict, bewertete: int) -> bool:
    """Entscheidet, ob die zweistufige Redaktion laeuft.

    Beides hat seine Groesse: bei 36 bewerteten Meldungen (Lauf #67) schreibt
    EIN Aufruf einen besseren, zusammenhaengenderen Bericht als dreizehn, und
    er kostet ein Zwoelftel. Ab ein paar hundert Meldungen kippt es - dann kann
    ein einzelner Aufruf nicht mehr abwaegen, sondern nur noch aufzaehlen, und
    ein Fehlschlag kostet den ganzen Wochenbericht.

    Deshalb eine Schwelle statt einer Grundsatzentscheidung. "auto" ist der
    Normalfall; "einstufig"/"zweistufig" erzwingen einen Modus, was der
    Abnahme neuer Wellen dient (ein echter Lauf mit erzwungener Zweistufigkeit,
    bevor die Meldungsmenge sie ohnehin ausloest).
    """
    modus = str(settings.get("editor_modus", "auto") or "auto").lower()
    if modus == "zweistufig":
        return True
    if modus == "einstufig":
        return False
    if modus != "auto":
        log.warning("Unbekannter editor_modus %r - benutze auto", modus)
    schwelle = int(settings.get("editor_zweistufig_ab_meldungen", 120) or 120)
    return bewertete >= schwelle


def zu_merkende_meldungen(new_items: list[Item],
                          vertreter_item_von: dict[str, Item],
                          ungelesene_meldungen: set[str],
                          unanalysierte_regionen: set[str]) -> list[Item]:
    """Welche Meldungen als "gesehen" abgelegt werden duerfen.

    Der Seen-Store ist ein Einbahnschild: was hineingeht, gilt als erledigt
    und wird nie wieder gesammelt. Zwei Schutzstufen gab es dafuer schon (die
    komplett ausgefallene Region aus Lauf #64, der einzelne gescheiterte
    Stapel aus Lauf #67); mit dem Ereignis-Clustering kommt eine dritte dazu.

    Ein BELEG wird nie einzeln bewertet - er haengt an seinem Vertreter. Ohne
    diese Umleitung waeren gebuendelte Meldungen der teuerste Fall ueberhaupt:
    der Vertreter kaeme beim naechsten Lauf wieder, seine drei Belege nie, und
    das Protokoll saehe normal aus. Als eigene Funktion herausgezogen, damit
    genau das ein Test halten kann.
    """
    def gelesen(item: Item) -> bool:
        chef = vertreter_item_von.get(item.id, item)
        return (chef.id not in ungelesene_meldungen
                and chef.region not in unanalysierte_regionen)

    return [i for i in new_items if gelesen(i)]


def _sort_key(item: Item):
    """Freshest first; undated items last."""
    pub = item.published
    if pub is None:
        return (0, "")
    return (1, pub.isoformat())


def _interleave_by_source(items: list[Item]) -> list[Item]:
    """Order a region's items so every operator gets a slot before any
    operator gets a second one.

    The analyst reads at most `max_items_per_region` items, so the order here
    decides what is even looked at. Straight recency ordering let one
    high-volume feed take the whole budget: in the 2026-07-31 run 220 new
    items produced only 70 analysed ones, and the operator newsrooms - the
    entire point of the watchlist - lost every slot to the trade press.
    Round-robin over the sources keeps the breadth; within a source the
    freshest item still comes first.
    """
    buckets: dict[str, list[Item]] = defaultdict(list)
    for item in sorted(items, key=_sort_key, reverse=True):
        buckets[item.operator or item.source_name].append(item)
    # Operators with a dated newest item go first, so a source that publishes
    # undated pages cannot outrank one with a verifiable fresh release.
    order = sorted(buckets.values(), key=lambda b: _sort_key(b[0]), reverse=True)
    out: list[Item] = []
    for round_items in zip_longest(*order):
        out.extend(i for i in round_items if i is not None)
    return out


def run(root: Path, use_llm: bool | None = None,
        lookback_days: int | None = None) -> Path:
    """Execute one full radar run. Returns the path of the written report."""
    t0 = time.monotonic()
    started_at = datetime.now(timezone.utc)
    cfg = load_config(root)
    lookback = lookback_days or cfg.lookback_days
    language = LANGUAGES.get(cfg.settings.get("report_language", "de"), "Deutsch")
    fallback_model = cfg.settings.get("model", "claude-sonnet-5")
    anbieter = _waehle_anbieter(cfg.settings)
    use_openai = anbieter in OPENAI_KOMPATIBEL
    analyst_model, editor_model = _modelle_fuer_anbieter(
        cfg.settings, anbieter, fallback_model)
    # The editor model is the big one and the first to lose its slot when the
    # provider is oversubscribed: the connection is accepted and no token ever
    # arrives. Four stages run on it, so without a stand-in one provider outage
    # burns 4x the retry budget and the job timeout kills the run before it can
    # publish anything. Register the (smaller, still-served) analyst model as
    # the stand-in - used only after the editor model has failed hard once.
    mechanik_model = _mechanik_modell(cfg.settings, anbieter, analyst_model)
    if cfg.settings.get("editor_model_fallback", True) and analyst_model:
        llm.set_fallback(editor_model, analyst_model)
    log.info("LLM backend: %s | analyst=%s editor=%s mechanik=%s "
             "(Ausweichmodell: %s)",
             active_backend(), analyst_model, editor_model, mechanik_model,
             analyst_model if analyst_model != editor_model else "keins")
    # 0 (oder fehlend) heisst: keine Kappung - jede neue Meldung wird bewertet.
    max_items = int(cfg.settings.get("max_items_per_region", 0) or 0) or None

    today = date.today()
    today_iso = today.isoformat()

    state_dir = root / "data" / "state"
    reports_dir = root / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    phases: list[dict] = []

    def phase(name: str, seconds: float, detail: str = "") -> None:
        phases.append({"name": name, "seconds": round(seconds, 1), "detail": detail})

    # ------------------------------------------------------------- collect
    tc = time.monotonic()
    register = Quellenregister(state_dir / "quellen_register.json")
    items, source_results = collect_all(cfg, register=register)
    tag_news_regions(items, cfg.operators)

    # ---------------------------------------------------- Aenderungsradar
    # Die wichtigsten Preisbewegungen im Endkundengeschaeft werden NIE per
    # Pressemitteilung kommuniziert: eine geaenderte Option, ein neuer
    # Anschlusspreis, ein still verschwundener Aktionstarif stehen nur auf der
    # Tarifseite. Newsmonitoring erwischt das strukturell nicht.
    #
    # Die gefundenen Aenderungen gehen als normale Meldungen weiter - durch
    # Delta-Schicht, Clustering, Analyst, CTM-Linse und Bericht. Sie tragen
    # eine eigene `id` (aus URL plus Inhalt der Aenderung), sonst haette der
    # Seen-Store die zweite Preisaenderung derselben Seite fuer eine schon
    # berichtete gehalten. Failsafe: bricht den Lauf nie ab.
    # ---------------------------------------------------- Lieferzeit-Radar
    # Es existiert keine oeffentliche Studie, die Lieferzeiten der deutschen
    # Anbieter systematisch vergleicht. Was hier entsteht, ist Eigenwissen -
    # und deshalb eine eigene Stufe mit eigenem Speicher, nicht eine weitere
    # Quelle. Failsafe wie alle Nebenstufen.
    lieferzeit_bilanz: dict = {}
    if cfg.settings.get("lieferzeit_radar_aktiv", True):
        try:
            from .collect import lieferzeit as lieferzeit_radar
            lieferzeit_bilanz = lieferzeit_radar.sammle(
                root, cfg.settings.get("http", {}))
        except Exception as exc:  # noqa: BLE001
            log.error("Lieferzeit-Radar uebersprungen: %s", exc)

    aenderungs_bilanz: dict = {}
    if cfg.settings.get("aenderungsradar_aktiv", True):
        try:
            from .collect import aenderungen as aenderungsradar
            tarif_items, aenderungs_bilanz = aenderungsradar.sammle(
                root, cfg.settings.get("http", {}))
            items.extend(tarif_items)
        except Exception as exc:  # noqa: BLE001
            log.error("Aenderungsradar uebersprungen: %s", exc)

    # ------------------------------------------------------- Tarif-Sammler
    # Die Produktinformationsblaetter nach § 1 TK-TransparenzV sind die
    # einzige Quelle dieses Marktes, die rechtlich wahrheitsbewehrt ist.
    # Woechentlich, weil sie sich selten aendern - und genau deshalb ist
    # jede Aenderung ein Signal. Failsafe wie alle Nebenstufen.
    tarif_bilanz: dict = {}
    if cfg.settings.get("tarif_radar_aktiv", True):
        try:
            from .collect import tarif_crawler
            dokument_items, tarif_bilanz = tarif_crawler.sammle(
                root, cfg.settings.get("http", {}))
            items.extend(dokument_items)
        except Exception as exc:  # noqa: BLE001
            log.error("Tarif-Sammler uebersprungen: %s", exc)

    # ----------------------------------------------------------- CT-Radar
    # Die einzige Ebene, die VOR der Veroeffentlichung liegt: ein
    # Zertifikat entsteht, waehrend die Seite gebaut wird. Die Meldungen
    # tragen ihren Vorbehalt im Text - es sind Indizien, keine Meldungen.
    # Failsafe wie alle Nebenstufen.
    ct_bilanz: dict = {}
    if cfg.settings.get("ct_radar_aktiv", True):
        try:
            from .collect import ct_log
            # `use_llm` faellt erst weiter unten; hier zaehlt nur, ob ein
            # Backend ueberhaupt erreichbar ist. Ohne Modell laeuft der Radar
            # vollstaendig weiter, nur ohne die Aussortierstufe.
            ct_items, ct_bilanz = ct_log.sammle(
                root, cfg.settings.get("http", {}),
                modell=(mechanik_model if (use_llm is not False
                                           and llm_available()) else ""))
            items.extend(ct_items)
        except Exception as exc:  # noqa: BLE001
            log.error("CT-Radar uebersprungen: %s", exc)
    failed = [r["url"] for r in source_results if r["status"] == "fail"]
    n_ok = sum(1 for r in source_results if r["status"] == "ok")
    n_empty = sum(1 for r in source_results if r["status"] == "empty")
    n_quarantaene = sum(1 for r in source_results if r["status"] == "quarantaene")
    n_fail = len(failed)
    phase("Sammeln", time.monotonic() - tc,
          f"{len(source_results) - n_quarantaene} Quellen abgefragt, "
          f"{len(items)} Meldungen gefunden"
          + (f", {n_quarantaene} stillgelegt" if n_quarantaene else ""))
    log.info("Collected %d items (%d ok / %d leer / %d fehlgeschlagen / "
             "%d stillgelegt)", len(items), n_ok, n_empty, n_fail, n_quarantaene)

    # -------------------------------------------------------------- dedupe
    td = time.monotonic()
    seen = SeenStore(state_dir / "seen.jsonl")
    first_run = len(seen) == 0
    new_items = filter_fresh(seen.filter_new(items), lookback)
    # Neue Meldungen JE QUELLE ins Laufprotokoll. Das ist der Nenner der
    # Trefferquote (scripts/quellen_trefferquote.py): "gesammelt" taugt dafuer
    # nicht, weil ein Newsroom bei jedem Abruf dieselben 30 Meldungen liefert -
    # eine Quelle saehe damit schlecht aus, nur weil sie eine statische Seite
    # hat. Seit dem kompakten Seen-Store steht die Zuordnung Meldung -> Quelle
    # auch nirgends sonst mehr.
    neu_je_quelle: dict[str, int] = defaultdict(int)
    for i in new_items:
        neu_je_quelle[i.source_url] += 1
    for rec in source_results:
        rec["new"] = neu_je_quelle.get(rec["url"], 0)
    # Erst JETZT verbuchen: die Quarantaene entscheidet an "hat geliefert",
    # und die Zahl der neuen Meldungen steht erst nach der Delta-Schicht fest.
    register_zusammenfassung = register.verbuche_lauf(
        source_results, today_iso,
        quarantaene_nach=int(cfg.settings.get(
            "quellen_quarantaene_nach_laeufen", 6) or 6),
        quellen_der_config=quellen_der_config(cfg))
    register.speichern()
    phase("Nur Neues", time.monotonic() - td,
          f"{len(new_items)} neue Meldungen (Gedaechtnis: {len(seen)} bekannt)")
    log.info("Novelty filter: %d new items (seen store: %d known ids)",
             len(new_items), len(seen))

    # ------------------------------------------------------ Ereignis-Cluster
    # Der Seen-Store dedupliziert die URL, nicht das EREIGNIS. Drei Fachmedien
    # ueber dieselbe Sache waren bis zum 08.08.2026 drei Meldungen, drei
    # Bewertungen und im schlimmsten Fall drei Plaetze auf der Titelseite - in
    # der Ausgabe vom 07.08. standen zwei Varianten derselben rumaenischen
    # Spamfilter-Ankuendigung auf Platz 2 und Platz 5 der Spalte "Was wichtig
    # ist". Hier wird daraus EINE Meldung mit mehreren Belegen.
    #
    # Die Reihenfolge ist wichtig: sortiert wird VOR dem Gruppieren nach
    # Datum absteigend, damit die frischeste Meldung eines Ereignisses es
    # anfuehrt und die aelteren als Belege darunterstehen.
    llm_was_explicitly_disabled = use_llm is False
    if use_llm is None:
        use_llm = llm_available()

    tk = time.monotonic()
    cluster_store = clustering.ClusterStore(state_dir / "clusters.jsonl")
    gruppen = clustering.gruppiere(
        sorted(new_items, key=_sort_key, reverse=True),
        model=mechanik_model,
        use_llm=bool(use_llm and cfg.settings.get("cluster_llm_pruefung", True)),
        max_llm_pruefungen=cfg.settings.get("cluster_max_llm_pruefungen"))

    # Gruppen, deren Ereignis ein frueherer Lauf schon berichtet hat. Das
    # greift NUR bei praktisch gleicher Ueberschrift innerhalb von 72 Stunden
    # (clustering.SCHWELLE_SICHER) - also beim Nachdruck derselben Meldung,
    # nicht bei einer Entwicklung des Themas. Alles darunter bleibt eine
    # eigene Meldung: eine falsche Verbindung ist schlimmer als keine.
    jetzt = datetime.now(timezone.utc)
    nachklapp: list[clustering.Gruppe] = []
    aktuelle: list[clustering.Gruppe] = []
    for g in gruppen:
        if cluster_store.zuordnen(g.vertreter, jetzt) is not None:
            nachklapp.append(g)
        else:
            aktuelle.append(g)

    # Nur der Vertreter geht in die Bewertung; seine Belege haengen an ihm.
    vertreter_items = [g.vertreter for g in aktuelle]
    belege_je_url = {g.vertreter.url: g for g in aktuelle}
    # Wer haengt an wem - fuer den Seen-Store weiter unten. Ein Beleg darf nur
    # dann als erledigt gelten, wenn SEIN Vertreter wirklich gelesen wurde.
    vertreter_item_von: dict[str, Item] = {}
    for g in gruppen:
        vertreter_item_von[g.vertreter.id] = g.vertreter
        for m in g.mitglieder:
            vertreter_item_von[m.id] = g.vertreter
    zusammengefasst = len(new_items) - len(vertreter_items)
    phase("Ereignisse buendeln", time.monotonic() - tk,
          f"{len(vertreter_items)} Ereignisse aus {len(new_items)} Meldungen"
          + (f", {len(nachklapp)} Nachklapp" if nachklapp else ""))
    log.info("Ereignis-Cluster: %d Meldungen -> %d Ereignisse (%d gebuendelt, "
             "%d Nachklapp zu frueher berichteten Ereignissen)",
             len(new_items), len(vertreter_items), zusammengefasst,
             len(nachklapp))

    items_by_region: dict[str, list[Item]] = defaultdict(list)
    for item in sorted(vertreter_items, key=_sort_key, reverse=True):
        items_by_region[item.region].append(item)
    for region_key, region_items in items_by_region.items():
        items_by_region[region_key] = _interleave_by_source(region_items)

    # ------------------------------------------------------------- analyze
    topics_store = ReportedTopics(
        state_dir / "reported_topics.jsonl",
        max_entries=int(cfg.settings.get("reported_topics_memory", 300)),
    )

    ta = time.monotonic()
    regional: dict[str, dict] = {}
    analyst_telemetry: list[dict] = []
    # Regionen, deren Analyse vollstaendig ausgefallen ist. Ihre Meldungen
    # duerfen NICHT in den Seen-Store: dort gelten sie sonst als erledigt und
    # tauchen nie wieder auf, obwohl sie kein Analyst je gelesen hat.
    unanalysierte_regionen: set[str] = set()
    # Einzelne Meldungen aus gescheiterten Stapeln - dieselbe Logik eine Ebene
    # feiner. Der Regionsschutz allein reicht nicht: im Lauf #67 fielen 2 von
    # 3 Stapeln eines Themenfelds aus, die Region galt damit als analysiert,
    # und rund 33 ungelesene Meldungen wanderten trotzdem in den Seen-Store.
    ungelesene_meldungen: set[str] = set()
    editor_used = False
    if use_llm and new_items:
        # Analysts are independent per region -> run them concurrently. Only
        # ~6 calls, well under any rate cap, but overlapping their latency
        # turns a ~9x sequential wait into ~1-2x. Same models, same output.
        llm_workers = int(cfg.settings.get("llm_max_workers", 4))
        # Zweite Ebene der Parallelitaet: die Stapel INNERHALB einer Region.
        # Ohne sie haengt die Laufzeit an der groessten Region - und die ist
        # seit dem Quellen-Ausbau deutlich groesser geworden.
        batch_workers = int(cfg.settings.get("analyst_batch_workers", 1) or 1)

        def _analyze_one(region_key, region_items):
            region_name = cfg.bereich_names.get(region_key, region_key)
            try:
                res = analyze_region(
                    region_name, region_items, model=analyst_model,
                    language=language, max_items=max_items,
                    is_theme=is_theme_key(region_key),
                    batch_workers=batch_workers)
                tel = dict(res.get("_telemetry", {}))
                tel["region"] = region_name
                if tel.get("batches") and not tel.get("batches_ok"):
                    # Jeder Stapel gescheitert - die Meldungen sind ungelesen.
                    unanalysierte_regionen.add(region_key)
                return region_name, res, tel
            except Exception as exc:  # noqa: BLE001
                log.error("Analyst %s failed: %s - falling back to raw list",
                          region_name, exc)
                unanalysierte_regionen.add(region_key)
                fallback = {
                    "region_summary": "",
                    "highlights": [
                        {"title": i.title, "operator": i.operator or "",
                         "url": i.url, "category": "Sonstiges", "relevance": 2,
                         "summary": i.summary[:200], "why_it_matters": ""}
                        for i in region_items[:10]
                    ],
                }
                return region_name, fallback, None

        with ThreadPoolExecutor(max_workers=max(1, llm_workers)) as _pool:
            _futs = [_pool.submit(_analyze_one, rk, ri)
                     for rk, ri in items_by_region.items()]
            for _fut in as_completed(_futs):
                region_name, res, tel = _fut.result()
                ungelesene_meldungen.update(res.pop("_ungelesen", []) or [])
                regional[region_name] = res
                if tel is not None:
                    analyst_telemetry.append(tel)
        # Nur die Themenfelder, die in DIESEM Lauf auch bewertete Meldungen
        # haben - sonst verlangt der Editor-Check eine Ueberschrift, zu der es
        # nichts zu schreiben gibt.
        themen_mit_inhalt = [
            cfg.theme_names[tk] for tk in cfg.theme_names
            if regional.get(cfg.theme_names[tk], {}).get("highlights")
        ]
        bewertete = sum(len(r.get("highlights") or []) for r in regional.values())
        zweistufig = _redaktion_zweistufig(cfg.settings, bewertete)
        try:
            if zweistufig:
                body, covered = editor.synthesize_zweistufig(
                    regional, topics_store.recent(), model=editor_model,
                    language=language, themenbereiche=themen_mit_inhalt,
                    workers=int(cfg.settings.get("llm_max_workers", 4)))
            else:
                body, covered = editor.synthesize(
                    regional, topics_store.recent(), model=editor_model,
                    language=language,
                    highlight_budget=int(
                        cfg.settings.get("editor_max_highlights", 0) or 0),
                    themenbereiche=themen_mit_inhalt)
            editor_used = True
        except Exception as exc:  # noqa: BLE001
            if cfg.settings.get("publish_requires_editorial_briefing", True):
                raise RuntimeError(
                    "Editorial synthesis failed; refusing to publish a raw "
                    "source digest. The previous briefing remains live."
                ) from exc
            log.warning(
                "Editorial synthesis failed (%s); publishing a labelled "
                "source-linked fallback digest", str(exc)[:180])
            fallback, covered = editor.build_digest(
                items_by_region, cfg.bereich_names, llm_was_available=False,
                include_note=False)  # the Redaktions-Fallback note below says it
            body = (
                "## Redaktions-Fallback\n\n"
                "> Die aktuelle Quellenliste konnte wegen einer vorübergehenden "
                "Störung des Analyse-Dienstes nicht redaktionell verdichtet "
                "werden. Die Links und Meldungen stammen trotzdem aus diesem "
                "Lauf; die automatische Redaktion wird im nächsten Lauf erneut "
                "versucht.\n\n" + fallback
            )
            editor_used = False
    else:
        if (new_items and not llm_was_explicitly_disabled
                and cfg.settings.get("publish_requires_editorial_briefing", True)):
            raise RuntimeError(
                "No editorial model is available; refusing to publish a raw "
                "source digest. The previous briefing remains live."
            )
        if use_llm and not new_items:
            log.info("No new items - writing empty briefing")
        for region_key, region_items in items_by_region.items():
            region_name = cfg.bereich_names.get(region_key, region_key)
            regional[region_name] = {
                "region_summary": "",
                "highlights": [
                    {"title": i.title, "operator": i.operator or i.source_name,
                     "url": i.url, "category": "Unbewertet", "relevance": None,
                     "summary": i.summary[:220], "why_it_matters": ""}
                    for i in (region_items if not max_items
                              else region_items[:max_items])
                ],
            }
        body, covered = editor.build_digest(
            items_by_region, cfg.bereich_names, llm_was_available=bool(use_llm))
        if first_run:
            body = (
                "> **Erster Lauf (Baseline):** Alle Quellen wurden initial "
                "eingelesen. Ab dem naechsten Lauf erscheinen nur noch "
                "wirklich neue Meldungen.\n\n" + body
            )
    phase("Bewerten & Schreiben", time.monotonic() - ta,
          f"{sum(len(r.get('highlights') or []) for r in regional.values())} "
          f"bewertete Meldungen" if use_llm else "ohne KI (Roh-Digest)")

    # ------------------------------------------------------------ CTM-Linse
    # Die zweite Bewertungsachse: nicht "ist das wichtig?", sondern "ist das
    # fuer UNS wichtig?". Sie laeuft NACH den Analysten und VOR allem, was
    # sortiert - Stufe 3 rechnet der Code aus config/ctm_fokus.yaml, die
    # Stufen 0-2 kommen vom Modell. Danach der Prueflauf gegen den
    # Originaltext: sobald das System folgert statt zusammenzufasst, ist ein
    # plausibel klingender Fehler das eigentliche Risiko, und ein
    # ungeprueft veroeffentlichter Folgerungssatz waere genau das.
    tctm = time.monotonic()
    ctm_bilanz: dict = {}
    beleg_bilanz: dict = {}
    try:
        fokus = ctm_mod.lade_fokus(root)
        for region_name, r in regional.items():
            for h in r.get("highlights", []):
                h.setdefault("region", region_name)
        alle = [h for r in regional.values() for h in r.get("highlights", [])]
        ctm_bilanz = ctm_mod.veredle(alle, fokus)
        beleg_bilanz = faithfulness.pruefe(
            alle, model=mechanik_model,
            use_llm=bool(use_llm and new_items
                         and cfg.settings.get("ctm_belegpruefung", True)))
        log.info("CTM-Linse: %d direkt / %d uebertragbar / %d Kontext / "
                 "%d Hintergrund | Saetze: %d belegt, %d verworfen",
                 ctm_bilanz.get("direkt", 0), ctm_bilanz.get("uebertragbar", 0),
                 ctm_bilanz.get("kontext", 0), ctm_bilanz.get("hintergrund", 0),
                 beleg_bilanz.get("belegt", 0),
                 ctm_bilanz.get("saetze_verworfen", 0)
                 + beleg_bilanz.get("verworfen", 0))
    except Exception as exc:  # noqa: BLE001 - die Linse kippt keinen Lauf
        log.error("CTM-Linse uebersprungen: %s", exc)
    phase("Einordnen für uns", time.monotonic() - tctm,
          f"{ctm_bilanz.get('direkt', 0)} direkt handlungsrelevant, "
          f"{beleg_bilanz.get('belegt', 0)} belegte Folgerungssätze")

    # strip internal telemetry from the regional dict before it is stored
    for r in regional.values():
        r.pop("_telemetry", None)

    # ------------------------------------------------ competitor deep-dives
    competitor_profiles: list[dict] = []
    if use_llm and cfg.focus_competitors:
        tcomp = time.monotonic()
        try:
            # Das Analystenmodell des AKTIVEN Anbieters, nicht der fest
            # verdrahtete openai-Schluessel. Solange "openai" der einzige
            # OpenAI-kompatible Anbieter war, war beides dasselbe; seit
            # c9c30f1 (DeepSeek, 04.08.2026) nicht mehr - die Wettbewerber-
            # Analyse schickte "deepseek-ai/deepseek-v4-flash" an den
            # DeepSeek-Endpunkt, der nur "deepseek-v4-flash" kennt, und alle
            # drei Profile scheiterten in 0,6 s. Zwei Laeufe lang stand die
            # Seite deshalb leer da (Lauf #74 und #75).
            comp_model = analyst_model if use_openai else editor_model
            competitor_profiles = competitor_mod.analyze_all(
                cfg.focus_competitors, items, comp_model, language,
                max_workers=int(cfg.settings.get('llm_max_workers', 4)))
        except Exception as exc:  # noqa: BLE001
            log.error("Competitor deep-dive failed: %s", exc)
        phase("Wettbewerber-Analyse", time.monotonic() - tcomp,
              f"{len(competitor_profiles)} Profile "
              f"({sum(len(c.get('moves') or []) for c in competitor_profiles)} Moves)")

    # enrich highlights with date + source from the collected items
    by_url = {i.url: i for i in new_items}
    for region in regional.values():
        for h in region.get("highlights", []):
            item = by_url.get(h.get("url", ""))
            if item is not None:
                h.setdefault("date", item.published.date().isoformat()
                             if item.published else None)
                h.setdefault("source", item.source_name)
                # Der Anzeigename allein reicht nicht: ein Betreiber mit
                # Newsroom UND Investor Relations traegt in beiden denselben.
                # Ohne die Kanal-URL waere die Trefferquote je Kanal - und
                # damit die Frage, welcher Zweitkanal sich lohnt - nicht
                # berechenbar.
                h.setdefault("source_url", item.source_url)
                # Bild aus dem Feed-Eintrag, falls der Feed eins mitliefert.
                # Kostet keinen Abruf; report/bilder.py versucht danach nur
                # noch fuer die Meldungen ohne eins die Artikelseite.
                if getattr(item, "image_url", ""):
                    h.setdefault("image_url", item.image_url)
                # Die weiteren Quellen desselben Ereignisses. Dass drei
                # unabhaengige Fachmedien dieselbe Sache melden, ist in der
                # Regel der bessere Wichtigkeitsindikator als jede
                # LLM-Einschaetzung - deshalb steht die Zahl an der Meldung
                # und nicht nur im Protokoll.
                gruppe = belege_je_url.get(h.get("url", ""))
                if gruppe is not None and gruppe.mitglieder:
                    h.setdefault("weitere_quellen", gruppe.belege())
                    h.setdefault("quellenzahl", gruppe.quellen)
                    h.setdefault("cluster_id", gruppe.id)
            else:
                h.setdefault("date", None)
                h.setdefault("source", "")
                h.setdefault("source_url", "")

    # ------------------------------------------------------------- Bilder
    # Eine Zeitung ohne Bilder ist eine Textwueste. JEDE Meldung wird
    # versucht - bis zum 06.08.2026 lag hier ein Deckel bei 40, und 153 von
    # 193 Meldungen wurden nie auch nur gefragt. Ein Fehlschlag bleibt
    # folgenlos: der Satz kommt ohne Bild aus (viele Fachpresseseiten weisen
    # den direkten Abruf mit 403 ab).
    tbild = time.monotonic()
    alle_highlights = [h for r in regional.values() for h in r.get("highlights", [])]
    try:
        bild_bilanz = report_bilder.hole_bilder(alle_highlights, root)
    except Exception as exc:  # noqa: BLE001 - Bilder duerfen nie den Lauf kippen
        log.error("Bildbeschaffung fehlgeschlagen: %s", exc)
        bild_bilanz = {}
    n_bilder = bild_bilanz.get("geladen", 0)
    phase("Bilder", time.monotonic() - tbild,
          f"{n_bilder} von {len(alle_highlights)} Meldungen mit Bild")

    # -------------------------------------------------- Highlight-Themen
    # Erkennt, wenn viele Meldungen dasselbe Ereignis meinen (Samsungs
    # Foldable-Launch, eine Uebernahme, ein Netzausfall), und pflegt dafuer
    # eine temporaere Themenseite. NACH der Bilderphase, damit die Meldungen
    # eines Themas ihre Bilder mitbringen. Failsafe wie Kurator und Sweep:
    # bricht den Lauf nie ab.
    try:
        themen_bilanz = highlight_topics.pflege_highlight_themen(
            alle_highlights, state_dir, today_iso,
            model=analyst_model or editor_model,
            use_llm=bool(use_llm and new_items),
            reports_dir=reports_dir)
        log.info("Highlight-Themen: %d aktiv, %d Kandidat(en), neu: %s, "
                 "beendet: %s", themen_bilanz["aktiv"],
                 themen_bilanz["kandidaten"],
                 ", ".join(themen_bilanz["neu"]) or "keins",
                 ", ".join(themen_bilanz["beendet"]) or "keins")
    except Exception as exc:  # noqa: BLE001
        log.error("Highlight-Themen uebersprungen: %s", exc)

    # -------------------------------------------- Differenzierungs-Kurator
    # Nimmt aufnahmewuerdige Differenzierungs-Moves dieser Woche in den
    # persistenten Speicher auf (data/state/differentiation.jsonl), damit sie
    # auch spaeter noch als Inspiration sichtbar bleiben. Failsafe: Fehler
    # brechen den Lauf nicht ab.
    try:
        # Die Themenfelder bleiben hier bewusst aussen vor: die
        # Differenzierungs-Bibliothek sammelt Moves, mit denen sich ein
        # BETREIBER von anderen Betreibern abhebt. Eine Chip- oder
        # Regulierungsmeldung ist kein solcher Move - sie wuerde den Speicher
        # fuellen, ohne je als Vorbild taugen zu koennen.
        themen_namen = set(cfg.theme_names.values())
        flat_new = []
        for region_name, r in regional.items():
            if region_name in themen_namen:
                continue
            for h in r.get("highlights", []):
                hh = dict(h)
                hh["region"] = region_name
                flat_new.append(hh)
        diff_store = DiffStore(state_dir / "differentiation.jsonl")
        added = diff_curator.curate(
            flat_new, diff_store, date.today().isoformat(),
            model=mechanik_model, use_llm=bool(use_llm and new_items))
        log.info("Differenzierung: %d neue Move(s) aufgenommen (Speicher: %d)",
                 len(added), len(diff_store))
    except Exception as exc:  # noqa: BLE001
        log.error("Differenzierungs-Kurator uebersprungen: %s", exc)

    # ------------------------------------- Dynamischer Kategorie-Sweep (Web)
    # Zweite Datenquelle fuer die Differenzierungs-Seite: durchsucht je Lauf
    # rotierend aktiv das Web (Brave Search) nach echten Differenzierungs-Moves
    # der Wettbewerber und pflegt sie mit Quelle + Datum in die versionierte DB
    # (data/state/differentiation_db.json). Failsafe: bricht nie ab.
    try:
        category_sweep.run_sweep(
            state_dir, os.environ.get("BRAVE_API_KEY", ""),
            mechanik_model, bool(use_llm), date.today().isocalendar()[1])
    except Exception as exc:  # noqa: BLE001
        log.error("Kategorie-Sweep uebersprungen: %s", exc)

    # ---------------------------------------------- Promo-Uebersicht (DE)
    # Eigener zweiter Anwendungsfall neben Marktrecherche: Tarif-/Kampagnen-
    # aktionen aller Telcos in Deutschland, per Snapshot-Diff der jeweils
    # eigenen Aktionsseite gesammelt statt per Presse-RSS (siehe
    # promo_pipeline.py + config/promo_sources.yaml). Failsafe: bricht den
    # Gesamtlauf nie ab; per settings.yaml (promo_enabled) abschaltbar.
    promo_result: dict = {}
    if cfg.settings.get("promo_enabled", True):
        try:
            from .promo_pipeline import run_promo_stage
            promo_result = run_promo_stage(
                root, cfg.settings.get("http", {}), bool(use_llm),
                editor_model, language=language, settings=cfg.settings,
                score_model=mechanik_model,
                extract_model=mechanik_model)
            log.info("Promo-Uebersicht: %s (%d aktive Aktionen)",
                     promo_result.get("mode"), promo_result.get("active", 0))
        except Exception as exc:  # noqa: BLE001
            log.error("Promo-Uebersicht uebersprungen: %s", exc)

    # ------------------------------------------- Geraete- und Preisradar (DE)
    # Dritter Beobachtungsraum neben Presse und Aktionsseiten: was die
    # Wettbewerber an GERAETEN fuehren und was sie kosten. Wie der Promo-Zweig
    # eine Nebenstufe mit eigenem try/except - aber mit einem echten
    # Zeitbudget, denn der Kernlauf liegt bereits bei rund 27 Minuten.
    #
    # Der Tageslauf startet um 08:30 UTC. Zwei Haendler erlauben Abrufe laut
    # eigener robots.txt nur zwischen 02:00 und 08:00; sie werden hier
    # uebersprungen (und dabei ausdruecklich NICHT gealtert) und vom
    # naechtlichen Lauf .github/workflows/geraete.yml nachgeholt.
    #
    # DIE HARTE LEHRE AUS LAUF 31422689829 (10.08.2026)
    # ------------------------------------------------
    # Die Stufe hatte ihr eigenes Budget - und trotzdem hat sie den ganzen
    # Lauf gekostet. Der Kernlauf war um 19:54:48 fertig, also 44:39 nach
    # Jobbeginn; die Stufe startete mit zehn Minuten Budget in einen Job, der
    # noch fuenf Minuten hatte. Um 19:59:46 kam das Job-Timeout, und weil
    # diese Stufe VOR dem Rendern und Committen steht, ist nichts von den 45
    # erfolgreichen Minuten veroeffentlicht worden: kein Bericht, keine
    # Website, kein Deploy. Ein eigenes Zeitbudget schuetzt nur, wenn es
    # gegen die verbleibende Jobzeit gerechnet wird - nicht gegen sich selbst.
    #
    # Deshalb zwei Sicherungen. Erstens ist die Stufe im Wochenlauf AUS
    # (`geraete_enabled: false`): sie hat mit `.github/workflows/geraete.yml`
    # einen eigenen naechtlichen Job, der sie taeglich und im Besuchsfenster
    # der zwei Haendler faehrt. Zweitens - falls sie jemand wieder anschaltet -
    # bekommt sie nur, was der Job noch uebrig hat, und laeuft gar nicht
    # erst an, wenn das Rendern dadurch in Gefahr geraet.
    geraete_bilanz: dict = {}
    _budget = geraete_budget(cfg.settings, time.monotonic() - t0)
    if _budget is None:
        if cfg.settings.get("geraete_enabled", False):
            log.warning("Geraeteradar uebersprungen: zu wenig Jobzeit uebrig. "
                        "Der naechtliche Lauf holt es nach - die "
                        "Veroeffentlichung geht vor.")
    else:
        try:
            from .geraete_pipeline import run_geraete_stage
            geraete_bilanz = run_geraete_stage(
                root, cfg.settings.get("http", {}), today_iso,
                frist_sekunden=_budget)
        except Exception as exc:  # noqa: BLE001
            log.error("Geraeteradar uebersprungen: %s", exc)

    # ----------------------------------------- Differenzierungsbericht-Agent
    # Der Bericht arbeitet auf der aktualisierten, versionierten DB. Er ist
    # deshalb ein eigener Editorial-Schritt und nicht nur eine Umformatierung
    # der darunterstehenden Move-Liste. Ohne LLM bleibt die Seite mit einem
    # quellengebundenen Regelbericht nutzbar.
    diff_report_dir = reports_dir / "differenzierung"
    diff_report_dir.mkdir(parents=True, exist_ok=True)
    diff_db = category_sweep.DiffDB(state_dir / "differentiation_db.json")
    diff_entries = list(diff_db.entries.values())
    theme_labels = category_sweep.THEME_LABEL
    try:
        if use_llm and diff_entries:
            diff_body = differentiation_editor.synthesize(
                diff_entries, theme_labels, model=editor_model, language=language)
            diff_mode = "KI-Redaktion"
        else:
            diff_body = differentiation_editor.build_digest(diff_entries, theme_labels)
            diff_mode = "Regelbericht"
    except Exception as exc:  # noqa: BLE001
        log.warning("Differenzierungsbericht-Agent fehlgeschlagen (%s) – "
                    "verwende Regelbericht", str(exc)[:160])
        diff_body = differentiation_editor.build_digest(diff_entries, theme_labels)
        diff_mode = "Regelbericht (Fallback)"
    diff_report_path = diff_report_dir / f"{today.isoformat()}.md"
    diff_report_path.write_text(diff_body, encoding="utf-8")
    log.info("Differenzierungsbericht: %s (%d Moves)", diff_mode, len(diff_entries))

    # ----------------------------------------- Bilder der Differenzierung
    # Die Seite zeigte bis zum 08.08.2026 77 Karten und null Bilder - Antonio:
    # "Keine Bilder, es ist schwer zu verstehen." Hier werden sie beschafft
    # (erst aus den Bildern des Wochenberichts, dann per og:image), damit
    # `render_site()` offline bleiben kann. Failsafe: ein fehlendes Bild ist
    # kein Grund, einen Lauf zu kippen - die Karte bekommt dann eine
    # Schriftkachel.
    try:
        diff_store_fuer_bilder = DiffStore(state_dir / "differentiation.jsonl")
        diff_bestand = differenzierung_view.merge(
            diff_entries, diff_store_fuer_bilder.entries())
        bilanz = diff_bilder.beschaffe(diff_bestand, root, reports_dir,
                                       today.isoformat())
        log.info("Differenzierungs-Bilder: %d von %d Beispielen",
                 bilanz.get("mit_bild", 0), bilanz.get("bestand", 0))
    except Exception as exc:  # noqa: BLE001
        log.error("Differenzierungs-Bilder uebersprungen: %s", exc)

    # -------------------------------------------------------------- report
    total_sources = sum(len(op.crawled_sources) for op in cfg.operators) \
        + len(cfg.news_sources) \
        + sum(1 for s in cfg.tech_sources if s.crawlable)
    stats = {
        "sources_total": total_sources,
        "sources_ok": n_ok,
        "sources_empty": n_empty,
        "sources_failed": n_fail,
        "collected": len(items),
        "new": len(new_items),
        # Was nach dem Buendeln uebrig bleibt. "new" zaehlt Meldungen,
        # "events" zaehlt Ereignisse - der Unterschied ist genau die
        # Mehrfachberichterstattung, die vorher als eigene Meldung durchging.
        "events": len(vertreter_items),
        "bundled": zusammengefasst,
        "followups": len(nachklapp),
        # Die CTM-Linse. `ctm_direkt` ist die Zahl, an der sich ablesen
        # laesst, ob eine Woche ueberhaupt etwas fuer das eigene Portfolio
        # hergab - eine Null ist ein Befund, kein Fehler.
        "ctm_direkt": ctm_bilanz.get("direkt", 0),
        "ctm_uebertragbar": ctm_bilanz.get("uebertragbar", 0),
        "ctm_saetze": beleg_bilanz.get("belegt", 0),
        "ctm_saetze_verworfen": (ctm_bilanz.get("saetze_verworfen", 0)
                                 + beleg_bilanz.get("verworfen", 0)),
        # Aenderungsradar: was still auf einer Tarifseite anders wurde.
        "tarif_seiten": aenderungs_bilanz.get("gelesen", 0),
        "tarif_aenderungen": aenderungs_bilanz.get("geaendert", 0),
        # Lieferzeit-Radar: gemessene Punkte des Warenkorbs.
        "lieferzeit_gemessen": lieferzeit_bilanz.get("gemessen", 0),
        "lieferzeit_engpaesse": len(lieferzeit_bilanz.get("engpaesse") or []),
        # CT-Radar: neue Subdomains als Indiz. `ct_zeitueberschreitung` ist
        # ausdruecklich eigen gefuehrt - eine Domain, die certspotter nicht
        # beantwortet hat, ist NICHT eine Domain ohne neue Namen.
        # Tarif-Datenbank. `tarif_kleingedruckt` ist eigen gefuehrt: eine
        # Aenderung ohne Preisbewegung ist die Meldung, die es sonst nirgends
        # gibt, und sie darf in der Summe nicht untergehen.
        "tarif_dokumente": tarif_bilanz.get("gelesen", 0),
        "tarif_dokument_aenderungen": tarif_bilanz.get("geaendert", 0),
        "tarif_kleingedruckt": tarif_bilanz.get("kleingedruckt", 0),
        "ct_domains": ct_bilanz.get("gelesen", 0),
        "ct_funde": ct_bilanz.get("meldungen", 0),
        "ct_zeitueberschreitung": ct_bilanz.get("zeitueberschreitung", 0),
        # Geraeteradar. Bewusst in `stats` und nicht nur im Log: der
        # Promo-Zweig ist auf der Website unsichtbar, weil sein Ergebnis
        # nirgends eingetragen wird - dieser hier soll es nicht sein.
        # `geraete_gealtert` steht eigen: ein Geraet, das Richtung
        # "ausgelistet" rueckt, ist die Meldung, nicht die Fussnote.
        "geraete_anbieter": geraete_bilanz.get("abgefragt", 0),
        "geraete_listungen": geraete_bilanz.get("listungen", 0),
        "geraete_neu": geraete_bilanz.get("neu", 0),
        "geraete_gealtert": geraete_bilanz.get("gealtert", 0),
        "geraete_preispunkte": geraete_bilanz.get("preispunkte", 0),
        "geraete_bestand": geraete_bilanz.get("bestand", 0),
        "operators": len(cfg.operators),
        "regions": len(cfg.region_names) - 1,
        "themes": len(cfg.theme_names),
    }

    # ------------------------------------------------------- run log (transparency)
    duration = time.monotonic() - t0
    kind_counts: dict[str, int] = defaultdict(int)
    for r in source_results:
        kind_counts[r["kind"]] += 1
    run_log = {
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 1),
        "used_llm": bool(use_llm and new_items),
        "editor_used": editor_used,
        "models": {
            "analyst": analyst_model if (use_llm and new_items) else None,
            "editor": editor_model if editor_used else None,
            "mechanik": mechanik_model if (use_llm and new_items) else None,
            # Models the provider stopped serving mid-run. Visible in
            # protokoll.html so a degraded run is recognisable as such instead
            # of looking like a thin news week.
            "unavailable": sorted(llm.dead_models()) or None,
        },
        "phases": phases,
        "source_summary": {
            "total": len(source_results),
            "ok": n_ok, "empty": n_empty, "failed": n_fail,
            "quarantaene": n_quarantaene,
            "by_kind": dict(kind_counts),
        },
        # Ohne diesen Block waere bei 1000 Quellen nirgends zu sehen, dass
        # eine Quelle stillgelegt wurde - genau das ist der Unterschied
        # zwischen einer gepflegten und einer verrottenden Konfiguration.
        "register": register_zusammenfassung,
        "sources": sorted(
            source_results,
            key=lambda r: ({"fail": 0, "ok": 1, "empty": 2}.get(r["status"], 3),
                           -r.get("count", 0))),
        "analysts": analyst_telemetry,
    }

    report_md = editor.report_header(today, stats) + body
    report_path = reports_dir / f"{today.isoformat()}.md"
    report_path.write_text(report_md, encoding="utf-8")

    report_json = {
        "date": today.isoformat(),
        "generated_with_llm": bool(use_llm and new_items),
        "stats": stats,
        "briefing_md": body,
        "regions": regional,
        "competitors": competitor_profiles,
        "run": run_log,
    }
    json_path = reports_dir / f"{today.isoformat()}.json"
    json_path.write_text(
        json.dumps(report_json, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Report written: %s (+ .json), run took %.1fs", report_path, duration)

    # ------------------------------------------------------ persist state
    # Der Seen-Store ist ein Einbahnschild: was hier hineingeht, gilt als
    # erledigt und wird nie wieder gesammelt. Meldungen einer Region, deren
    # Analyse komplett gescheitert ist, gehoeren deshalb NICHT hinein - sie
    # waeren sonst still verloren. Lauf #64 (04.08.2026) hat genau das getan:
    # das Anthropic-Guthaben war leer, jeder Analysten-Stapel scheiterte mit
    # HTTP 400, und trotzdem wanderten 223 ungelesene Meldungen in den Store.
    # Beim naechsten Lauf mit Guthaben waeren sie nicht mehr aufgetaucht.
    # Ein Beleg haengt am Schicksal SEINES Vertreters: gilt der als ungelesen,
    # ist es der Beleg auch. Ohne diese Umleitung waeren die zusammengefassten
    # Meldungen der teuerste Fall ueberhaupt - der Vertreter kaeme im naechsten
    # Lauf wieder, seine drei Belege nie.
    zu_merken = zu_merkende_meldungen(
        new_items, vertreter_item_von, ungelesene_meldungen,
        unanalysierte_regionen)
    gemerkt = {i.id for i in zu_merken}
    uebersprungen = len(new_items) - len(zu_merken)
    if uebersprungen:
        log.warning("%d Meldungen NICHT als gesehen markiert (%d Region(en) "
                    "ganz ohne Analyse, %d Meldungen aus gescheiterten "
                    "Stapeln) - der naechste Lauf holt sie erneut",
                    uebersprungen, len(unanalysierte_regionen),
                    len(ungelesene_meldungen))
    seen.add(zu_merken)
    # Der Ereignis-Speicher merkt sich nur, was auch gelesen wurde - sonst
    # gaelte ein Ereignis als berichtet, das nie im Bericht stand, und der
    # naechste Lauf wuerde seine Nachzuegler als Nachklapp verwerfen.
    cluster_store.merke([g for g in aktuelle if g.vertreter.id in gemerkt],
                        today_iso)
    # Dieselbe Logik fuer das Themengedaechtnis: Themen aus einem Notfall-
    # Digest als "schon berichtet" abzulegen wuerde die Redaktion daran
    # hindern, sie spaeter richtig zu behandeln.
    if covered and editor_used:
        topics_store.add(covered, today.isoformat())
    elif covered:
        log.warning("%d Themen stammen aus dem Notfall-Digest, nicht aus der "
                    "Redaktion - sie werden NICHT als berichtet gemerkt",
                    len(covered))

    # ------------------------------------------------------- Uebersetzung
    # Fremdsprachige Meldungen bekommen eine vollstaendige deutsche Fassung
    # als eigene Seite. Die Stufe steht VOR dem Rendern, weil der rote Link
    # auf der gerenderten Karte stehen muss - und genau deshalb bekommt sie
    # dieselbe Sicherung wie das Geraeteradar: ihr Budget rechnet gegen die
    # RESTZEIT DES JOBS abzueglich der Reserve fuers Veroeffentlichen, nicht
    # gegen sich selbst. Lauf 31422689829 hat gezeigt, was die andere
    # Rechnung kostet: 45 erfolgreiche Minuten, von denen nichts
    # veroeffentlicht wurde.
    #
    # Failsafe daneben: ein Fehler dieser Stufe darf den Bericht nie kosten.
    #
    # Sie laeuft auf den BERICHTETEN Meldungen, nicht auf `new_items`. Das
    # war der Fehler, an dem das ganze Vorhaben still gescheitert ist: der
    # rote Link haengt an der Karte einer Meldung, und eine Karte bekommt nur,
    # was der Analyst behalten hat. Am 14.08.2026 liefen 944 neue Meldungen
    # durch die Stufe, 58 kamen in den Bericht - und alle vier
    # Uebersetzungen, die entstanden, gehoerten zu Meldungen, die in KEINEM
    # Bericht stehen. Vier fertige Seiten, vier Modellaufrufe, 415 Sekunden,
    # und auf der Website nicht ein einziger Link. Die Stufe hat funktioniert
    # und war trotzdem vollstaendig unsichtbar.
    uebersetzung_bilanz: dict = {}
    # In Berichtsreihenfolge, also nach Relevanz. Die Stufe ordnet INNERHALB
    # dieser Reihenfolge noch einmal um - erkannt Fremdsprachige vor
    # Unbestimmten (`stufe._kandidaten`) -, damit ein sicherer Treffer nicht
    # hinter einem "vielleicht" verhungert. Die Zusicherung ist deshalb die
    # kleinere: es schneidet nicht die zufaellig letzte Meldung weg, sondern
    # innerhalb jeder der beiden Gruppen die unwichtigste. Ueber die URL
    # zurueck auf das Item, weil nur das den
    # Feed-Volltext und den Original-Teaser traegt - das Highlight traegt die
    # DEUTSCHE Zusammenfassung des Analysten, auf der jede Spracherkennung
    # "deutsch" messen wuerde.
    _ueb_items = uebersetzung_stufe.berichtete_items(alle_highlights, by_url)
    if len(_ueb_items) < len(alle_highlights):
        log.info("Uebersetzung: %d von %d berichteten Meldungen ohne "
                 "zugehoeriges Item (Dubletten oder umgeschriebene Adresse)",
                 len(alle_highlights) - len(_ueb_items), len(alle_highlights))
    _ueb_budget = uebersetzung_stufe.budget(cfg.settings, time.monotonic() - t0)
    if _ueb_budget is None:
        if cfg.settings.get("uebersetzung_enabled", True):
            log.warning("Uebersetzung uebersprungen: zu wenig Jobzeit uebrig. "
                        "Die Veroeffentlichung geht vor.")
    elif not llm.llm_available():
        log.info("Uebersetzung uebersprungen: kein Modellzugang.")
    else:
        try:
            uebersetzung_bilanz = uebersetzung_stufe.lauf(
                _ueb_items, root, cfg.settings, mechanik_model,
                frist_sekunden=_ueb_budget, heute=today)
            log.info("%s", uebersetzung_stufe.protokollzeile(uebersetzung_bilanz))
            run_log["uebersetzung"] = {
                k: (dict(v) if isinstance(v, Counter) else v)
                for k, v in uebersetzung_bilanz.items()}
        except Exception as exc:  # noqa: BLE001
            log.error("Uebersetzung uebersprungen: %s: %s",
                      type(exc).__name__, exc)

    # ---------------------------------------------------------------- site
    # Erst aufraeumen, dann rendern: render_site kopiert den Bildordner nach
    # site/images/, und was hier faellt, soll dort gar nicht erst landen.
    try:
        report_bilder.raeume_auf(root, reports_dir)
    except Exception as exc:  # noqa: BLE001
        log.error("Bilder-Aufraeumen fehlgeschlagen: %s", exc)
    render_site(root / "site", reports_dir, cfg)

    # ------------------------------------------------------------- Versand
    # Ganz zuletzt und failsafe: eine Mail, die nicht hinausgeht, ist
    # aergerlich - ein Lauf, der deshalb keinen Bericht veroeffentlicht,
    # waere schlimmer. Die Bilanz landet im Laufprotokoll, damit ein stiller
    # Dauerausfall auffaellt (versand.py verschickt nie stillschweigend
    # nichts).
    try:
        from .versand import versende
        run_log["versand"] = versende(root, report_json, cfg.settings)
        json_path.write_text(
            json.dumps(report_json, ensure_ascii=False, indent=1),
            encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.error("Versand uebersprungen: %s", exc)

    return report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Telco Radar pipeline")
    parser.add_argument("--root", type=Path, default=Path("."),
                        help="project root (contains config/, data/, site/)")
    parser.add_argument("--no-llm", action="store_true",
                        help="skip LLM analysis, produce raw digest")
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        run(args.root.resolve(),
            use_llm=False if args.no_llm else None,
            lookback_days=args.lookback_days)
    except Exception:  # noqa: BLE001
        log.exception("Pipeline failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
