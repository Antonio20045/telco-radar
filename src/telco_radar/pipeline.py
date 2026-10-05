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
from functools import partial
from itertools import zip_longest
from datetime import datetime, timezone
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
from .analyze.begriffe import THEME_LABEL
from .analyze.diff_curator import DiffStore
from .analyze.diff_db import DiffDB
from .analyze import highlight_topics
from .analyze import redaktion_kontinuitaet
from .analyze import vorsortierung as vorsortierung_mod
from .uebersetzung import stufe as uebersetzung_stufe
from .analyze import llm
from .analyze.llm import llm_available, active_backend
from .collect import collect_all, tag_news_regions
from .config import is_theme_key, load_config
from .dedupe import ReportedTopics, SeenStore, filter_fresh
from .models import Item
from .naehte import PRODUKTION, Naehte
from .quellen_register import Quellenregister, quellen_der_config
from .report import bilder as report_bilder
from .report import diff_bilder
from .report import differenzierung_view
from .report import geraete_bewegung
from .report.ausfall import Ausfall
from .report.html import render_site

log = logging.getLogger("telco_radar")

LANGUAGES = {"de": "Deutsch", "en": "English"}

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
    rest = (
        float(settings.get("job_frist_sekunden", 3000))
        - verstrichen
        - float(settings.get("veroeffentlichung_reserve_sekunden", 420))
    )
    if rest < _GERAETE_MINDESTBUDGET:
        return None
    return min(float(settings.get("geraete_frist_sekunden", 600)), rest)


OPENAI_KOMPATIBEL = {
    "openai": ("llm_api_base", "openai_analyst_model", "openai_editor_model"),
    "deepseek": (
        "deepseek_api_base",
        "deepseek_analyst_model",
        "deepseek_editor_model",
    ),
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

    fehlt = (
        (wanted == "bedrock" and not has_bedrock)
        or (wanted in OPENAI_KOMPATIBEL and not (has_key and base_url))
        or (wanted == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"))
    )
    if fehlt:
        log.warning(
            "llm_provider=%s, aber Schluessel oder Basis-URL fehlen - "
            "der Lauf faellt auf den Notfall-Digest zurueck",
            wanted,
        )

    if wanted != "bedrock":
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    if wanted not in OPENAI_KOMPATIBEL:
        os.environ.pop("LLM_API_KEY", None)
    elif base_url:
        os.environ["LLM_API_BASE"] = base_url
    return wanted


def _modelle_fuer_anbieter(
    settings: dict, anbieter: str, fallback_model: str
) -> tuple[str, str]:
    """Liefert (Analystenmodell, Editormodell) des GEWAEHLTEN Anbieters.

    Als eigene Funktion herausgezogen, weil das Auseinanderlaufen von
    Anbieter und Modell-ID sich nicht selbst meldet: der Endpunkt antwortet
    einfach mit "unbekanntes Modell", die aufrufende Stufe faengt den Fehler
    ab, und der Lauf gilt als erfolgreich. Genau so stand die
    Wettbewerber-Seite zwei Laeufe lang leer da (siehe unten im
    Wettbewerber-Zweig). Jede Stufe holt ihr Modell ab jetzt hier.
    """
    if anbieter == "bedrock":
        chain_head = llm.set_model_chain(settings.get("bedrock_model_chain") or [])
        return (
            (settings.get("bedrock_analyst_model") or chain_head or fallback_model),
            (settings.get("bedrock_editor_model") or chain_head or fallback_model),
        )
    if anbieter in OPENAI_KOMPATIBEL:
        _, analyst_key, editor_key = OPENAI_KOMPATIBEL[anbieter]
        return (
            settings.get(analyst_key) or fallback_model,
            settings.get(editor_key) or fallback_model,
        )
    return (
        settings.get("analyst_model", fallback_model),
        settings.get("editor_model", fallback_model),
    )


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


ANKER_REDAKTION = "claude-sonnet-5"
ANKER_MECHANIK = "claude-haiku-4-5-20251001"


def anker_modelle(settings: dict) -> tuple[str, str]:
    """(Redaktionsanker, Mechanikanker) - oder ("", ""), wenn abgeschaltet.

    Eine Stelle, an der die zwei Namen herkommen: `_registriere_anker` haengt
    sie an die Ketten, und der Analyst bekommt seinen ueber `ausweich=` je
    Aufruf mitgegeben (siehe dort). Zwei Ableseorte waeren zwei Wahrheiten.
    """
    if not settings.get("llm_anker", True):
        return "", ""
    return (
        str(settings.get("anker_redaktion_model", ANKER_REDAKTION) or "").strip(),
        str(settings.get("anker_mechanik_model", ANKER_MECHANIK) or "").strip(),
    )


def _registriere_ausweichmodell(
    settings: dict, analyst_model: str, editor_model: str
) -> bool:
    """Das anbietereigene Ausweichmodell `editor -> analyst`, wenn es taugt.

    Es taugt genau dann NICHT, wenn der Claude-Anker aktiv ist: Analyst und
    Redaktion haengen am selben Anbieterkonto, ein HTTP 402 toetet beide
    zugleich, und ein Ausweichmodell auf demselben leeren Konto ist keins.
    Frueher hat `_registriere_anker` diese Zusicherung nachtraeglich
    ueberschrieben - das war die Stelle, an der eine ECHTE Praeferenzkette
    (`bedrock_model_chain`) mit ueberschrieben wurde. Die Entscheidung
    gehoert hierher, wo bekannt ist, dass beide Modelle demselben Anbieter
    gehoeren; `_registriere_anker` sieht nur Namen.
    """
    if not (settings.get("editor_model_fallback", True) and analyst_model):
        return False
    if any(anker_modelle(settings)):
        return False
    llm.set_fallback(editor_model, analyst_model)
    return True


def _registriere_anker(
    settings: dict, analyst_model: str, editor_model: str, mechanik_model: str
) -> dict[str, str]:
    """Haengt an das ENDE jeder Modellkette einen Claude-Anker.

    Der Anker greift NUR, wenn das Primaermodell hart gescheitert ist - im
    Normalfall kostet er nichts. Er existiert, weil eine Kette innerhalb
    EINES Anbieters keine leere Kasse ueberlebt: Analyst, Redaktion und
    Mechanik haengen am selben DeepSeek-Konto, und ein HTTP 402 toetet sie
    zugleich.

    **Ans Ende, nicht an den Kopf.** `set_fallback(modell, anker)` ersetzt den
    Nachfolger, den `modell` schon hatte - und das ist bei einer echten
    Praeferenzkette ein stiller Verlust: `bedrock_model_chain` registriert
    "das beste Modell, das dieses Konto wirklich bedient" als
    a -> b -> c, und ein Anker am Kopf wirft b und c weg, ohne dass es
    irgendwo auffiele. Ein Bedrock-403 ("not available for this account") ist
    gerade KEINE leere Kasse, sondern eine Aussage ueber genau ein Modell -
    die Kette ist die Antwort darauf und muss stehen bleiben. Der Anker ist
    das, was NACH ihr kommt.

    Text entsteht in der Redaktion, deshalb endet sie in einem grossen
    Modell; die Mechanik im kleinsten - sie macht die allermeisten Aufrufe.

    In JEDER heutigen Provider-Konfiguration ist `analyst_model ==
    editor_model` ("deepseek-v4-pro", ebenso die beiden openai_*_model), und
    `llm._FALLBACKS` haengt am MODELLNAMEN, nicht an der Rolle des Aufrufers:
    fuer denselben Namen kann es nur EINEN Nachfolger geben, und der gehoert
    der Redaktion (ein ausgefallener Bericht wiegt schwerer). Der Analyst
    bekommt seinen kleineren Anker deshalb NICHT hier, sondern je Aufruf
    ueber `agents.analyze_region(..., ausweich=...)` - siehe `llm._kette`.
    Genau daran hing der Fehler bis zum 27.08.2026: der Analyst, die mit
    Abstand aufrufstaerkste Stufe, waere im Ernstfall auf Sonnet gelandet.
    """
    redaktion, mechanik = anker_modelle(settings)
    if not (redaktion or mechanik):
        return {}
    gesetzt: dict[str, str] = {}
    anker_namen = {redaktion, mechanik} - {""}
    for modell, anker in (
        (editor_model, redaktion),
        (mechanik_model, mechanik),
        (analyst_model, mechanik),
    ):
        if not modell or not anker:
            continue
        kette = llm._chain_from(modell)
        if anker in kette:
            continue
        ende = kette[-1]
        if ende in gesetzt or ende in anker_namen:
            continue
        llm.set_fallback(ende, anker)
        gesetzt[ende] = anker
    return gesetzt


def _protokolliere_kosten(kosten: dict) -> None:
    """Was der Lauf verbraucht hat - je Modell, im Actions-Log.

    Die Summe allein sagt nichts: teuer wird ein Lauf an EINER Stufe (am
    27.08.2026 waren ~90 % der 1,95 $ der Analyst auf v4-pro), und ohne die
    Zeile je Modell ist nicht zu sehen, an welcher.
    """
    modelle = kosten.get("modelle") or {}
    log.info(
        "Kosten: %.4f $ ueber %d Aufruf(e) in %d Modell(en)%s",
        kosten.get("summe_usd", 0.0),
        sum(m["aufrufe"] for m in modelle.values()),
        len(modelle),
        f" - ohne Preiszeile: {', '.join(kosten['ohne_preis'])}"
        if kosten.get("ohne_preis")
        else "",
    )
    for name, m in modelle.items():
        log.info(
            "Kosten %-32s %5d Aufrufe, %9d ein / %9d aus -> %s",
            name,
            m["aufrufe"],
            m["prompt_tokens"],
            m["completion_tokens"],
            "?" if m.get("usd") is None else f"{m['usd']:.4f} $",
        )
    if kosten.get("budget_ueberschritten"):
        log.warning(
            "Kosten: WARNSCHWELLE UEBERSCHRITTEN - %.4f $ gegen "
            "%.2f $ (llm_budget_usd). Der Lauf wurde nicht "
            "beschnitten; die Schwelle gehoert nachkalibriert oder "
            "der Umfang gesenkt.",
            kosten.get("summe_usd", 0.0),
            kosten["budget_usd"],
        )


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


def zu_merkende_meldungen(
    new_items: list[Item],
    vertreter_item_von: dict[str, Item],
    ungelesene_meldungen: set[str],
    unanalysierte_regionen: set[str],
) -> list[Item]:
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
        return (
            chef.id not in ungelesene_meldungen
            and chef.region not in unanalysierte_regionen
        )

    return [i for i in new_items if gelesen(i)]


_VORSORTIERUNG_MINDESTBUDGET = 60.0


def vorsortierung_budget(settings: dict, verstrichen: float) -> float | None:
    """Wie viel Zeit die Vorsortierung bekommt, oder None fuer "nicht
    anfangen".

    Dieselbe Rechnung wie `geraete_budget()` und `uebersetzung.stufe.budget()`
    und aus demselben Grund: gerechnet wird gegen die RESTZEIT DES JOBS, nicht
    gegen das eigene Budget. Der Unterschied zu jenen beiden ist die
    POSITION - die Vorsortierung steht VOR dem Analysten, also vor der
    laengsten Stufe des Laufs. Ein festes `vorsortierung_frist_sekunden` ist
    deshalb die eigentliche Sicherung; die Restzeit-Rechnung faengt nur den
    Fall ab, dass der Job ohnehin schon knapp ist.
    """
    if not vorsortierung_mod.ist_eingeschaltet(settings):
        return None
    rest = (
        float(settings.get("job_frist_sekunden", 3000))
        - verstrichen
        - float(settings.get("veroeffentlichung_reserve_sekunden", 420))
    )
    if rest < _VORSORTIERUNG_MINDESTBUDGET:
        return None
    return min(float(settings.get("vorsortierung_frist_sekunden", 480)), rest)


def vorsortieren(
    items_by_region: dict[str, list[Item]],
    *,
    settings: dict,
    root: Path,
    model: str,
    use_llm: bool,
    verstrichen: float = 0.0,
) -> tuple[dict[str, list[Item]], dict]:
    """Die Vorsortierung so, wie der Lauf sie aufruft - und nur deshalb eine
    eigene Funktion: der Aufrufer sitzt mitten in `run()`, und was dort steht,
    haelt kein Test. Dieselbe Ueberlegung wie bei `zu_merkende_meldungen`.

    Ohne Modell, ohne Meldungen oder mit abgeschaltetem Schalter bleibt die
    Abbildung unveraendert und die Bilanz leer - dann verhaelt sich der Lauf
    exakt wie vor dem 27.08.2026.

    Zwei Sicherungen liegen hier und nicht im Modul, weil nur der Lauf sie
    kennt:

    * **Das Zeitbudget** (`vorsortierung_budget`) - die Stufe steht vor dem
      Analysten, und eine Stufe, die ihre Zeit ueberzieht, kostet nicht ein
      paar Meldungen, sondern den Bericht (Lauf 31422689829).
    * **Das try/except** - eine Stufe, die MELDUNGEN ENTFERNT, darf nie der
      Grund sein, dass der Lauf ausfaellt. Faellt sie aus, gehen alle
      Meldungen unveraendert zum Analysten; das ist teurer, aber vollstaendig.
    """
    if not (
        use_llm and items_by_region and vorsortierung_mod.ist_eingeschaltet(settings)
    ):
        return dict(items_by_region), {}
    frist = vorsortierung_budget(settings, verstrichen)
    if frist is None:
        log.warning(
            "Vorsortierung uebersprungen: unter %.0fs Restzeit im Job "
            "- alle Meldungen gehen ungefiltert zum Analysten",
            _VORSORTIERUNG_MINDESTBUDGET,
        )
        return dict(items_by_region), {}
    try:
        behalten, bilanz = vorsortierung_mod.sortiere_regionen_vor(
            dict(items_by_region),
            model=model,
            fokus=ctm_mod.lade_fokus(root),
            workers=int(settings.get("llm_max_workers", 4) or 1),
            deadline=time.monotonic() + frist,
        )
    except Exception as exc:  # noqa: BLE001
        log.error(
            "Vorsortierung fehlgeschlagen (%s) - alle Meldungen gehen "
            "ungefiltert zum Analysten",
            str(exc)[:200],
        )
        return dict(items_by_region), {}
    return behalten, bilanz.als_dict()


def promo_stats(promo_result: dict) -> dict:
    """Die Promo-Zahlen fuers Laufprotokoll - leer, wenn die Stufe nicht lief.

    Bewusst in `stats`, nicht nur im Log: der Promo-Ausfall seit dem
    14.08.2026 (43 gescheiterte Extraktionen an einem Tag) stand in KEINER
    Statistik, weil `stats` kein `promo_*`-Feld kannte. Dieselbe Lehre wie
    beim Geraeteradar.

    Zwei Regeln, und beide unterscheiden Faelle, die sonst gleich aussehen:

    1. **Kein Ergebnis, keine Felder.** Ein abgeschalteter
       (`promo_enabled: false`) oder uebersprungener Zweig liefert `{}`, und
       daraus wuerde ohne diese Regel "0 Aktionsseiten gelesen, 0 Angebote"
       auf transparenz.html - die Aussage eines Totalausfalls fuer eine
       Stufe, die es in diesem Lauf gar nicht gab. Die Seite, die Vertrauen
       herstellen soll, darf "gab es nicht" und "hat nichts gefunden" nicht
       verwechseln.
    2. **Neu UND bestaetigt.** Eine ruhige Woche (nichts neu, siebzig
       Aktionen bestaetigt) meldete als einzelne Zahl dasselbe wie ein
       stiller Ausfall der Extraktion.

    Als eigene Funktion herausgezogen, damit ein Test das halten kann -
    dieselbe Ueberlegung wie bei `zu_merkende_meldungen` und `vorsortieren`.
    """
    if not promo_result:
        return {}
    return {
        "promo_seiten_gelesen": promo_result.get("seiten_gelesen", 0),
        "promo_angebote_neu": promo_result.get("angebote_neu", 0),
        "promo_angebote_bestaetigt": promo_result.get("angebote_bestaetigt", 0),
        "promo_extraktion_fehler": promo_result.get("extraktion_fehlgeschlagen", 0),
    }


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
    order = sorted(buckets.values(), key=lambda b: _sort_key(b[0]), reverse=True)
    out: list[Item] = []
    for round_items in zip_longest(*order):
        out.extend(i for i in round_items if i is not None)
    return out


def run(
    root: Path,
    use_llm: bool | None = None,
    lookback_days: int | None = None,
    naehte: Naehte = PRODUKTION,
) -> tuple[Path, list[Ausfall]]:
    """Execute one full radar run.

    Returns the report path and the parts of the site that were not rebuilt."""
    uhr = naehte.setzen() or partial(datetime.now, timezone.utc)
    stoppuhr = naehte.stoppuhr or time.monotonic
    t0 = stoppuhr()
    started_at = uhr()
    cfg = load_config(root)
    lookback = lookback_days or cfg.lookback_days
    language = LANGUAGES.get(cfg.settings.get("report_language", "de"), "Deutsch")
    fallback_model = cfg.settings.get("model", "claude-sonnet-5")
    anbieter = _waehle_anbieter(cfg.settings)
    analyst_model, editor_model = _modelle_fuer_anbieter(
        cfg.settings, anbieter, fallback_model
    )
    mechanik_model = _mechanik_modell(cfg.settings, anbieter, analyst_model)
    ausweich_aktiv = _registriere_ausweichmodell(
        cfg.settings, analyst_model, editor_model
    )
    anker_redaktion, anker_mechanik = anker_modelle(cfg.settings)
    anker = _registriere_anker(
        cfg.settings, analyst_model, editor_model, mechanik_model
    )
    llm.kosten_reset()
    llm.budget_setzen(
        cfg.settings.get("llm_budget_usd", 1.5), cfg.settings.get("llm_preise") or {}
    )
    log.info(
        "LLM backend: %s | analyst=%s editor=%s mechanik=%s "
        "(Ausweichmodell: %s, Anker: %s, Analystenanker: %s, "
        "Warnschwelle: %s $)",
        active_backend(),
        analyst_model,
        editor_model,
        mechanik_model,
        analyst_model if ausweich_aktiv else "keins",
        ", ".join(sorted(set(anker.values()))) or "keiner",
        anker_mechanik or "keiner",
        cfg.settings.get("llm_budget_usd", 1.5) or "keine",
    )
    max_items = int(cfg.settings.get("max_items_per_region", 0) or 0) or None

    today = started_at.date()
    today_iso = today.isoformat()

    state_dir = root / "data" / "state"
    reports_dir = root / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    phases: list[dict] = []

    def phase(name: str, seconds: float, detail: str = "") -> None:
        phases.append({"name": name, "seconds": round(seconds, 1), "detail": detail})

    tc = stoppuhr()
    register = Quellenregister(state_dir / "quellen_register.json")
    items, source_results = collect_all(cfg, register=register)
    tag_news_regions(items, cfg.operators)

    lieferzeit_bilanz: dict = {}
    if cfg.settings.get("lieferzeit_radar_aktiv", True):
        try:
            from .collect import lieferzeit as lieferzeit_radar

            lieferzeit_bilanz = lieferzeit_radar.sammle(
                root, cfg.settings.get("http", {})
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Lieferzeit-Radar uebersprungen: %s", exc)

    aenderungs_bilanz: dict = {}
    if cfg.settings.get("aenderungsradar_aktiv", True):
        try:
            from .collect import aenderungen as aenderungsradar

            tarif_items, aenderungs_bilanz = aenderungsradar.sammle(
                root, cfg.settings.get("http", {})
            )
            items.extend(tarif_items)
        except Exception as exc:  # noqa: BLE001
            log.error("Aenderungsradar uebersprungen: %s", exc)

    tarif_bilanz: dict = {}
    if cfg.settings.get("tarif_radar_aktiv", True):
        try:
            from .collect import tarif_crawler

            dokument_items, tarif_bilanz = tarif_crawler.sammle(
                root, cfg.settings.get("http", {})
            )
            items.extend(dokument_items)
        except Exception as exc:  # noqa: BLE001
            log.error("Tarif-Sammler uebersprungen: %s", exc)

    ct_bilanz: dict = {}
    if cfg.settings.get("ct_radar_aktiv", True):
        try:
            from .collect import ct_log

            ct_items, ct_bilanz = ct_log.sammle(
                root,
                cfg.settings.get("http", {}),
                modell=(
                    mechanik_model if (use_llm is not False and llm_available()) else ""
                ),
            )
            items.extend(ct_items)
        except Exception as exc:  # noqa: BLE001
            log.error("CT-Radar uebersprungen: %s", exc)
    failed = [r["url"] for r in source_results if r["status"] == "fail"]
    n_ok = sum(1 for r in source_results if r["status"] == "ok")
    n_empty = sum(1 for r in source_results if r["status"] == "empty")
    n_quarantaene = sum(1 for r in source_results if r["status"] == "quarantaene")
    n_fail = len(failed)
    phase(
        "Sammeln",
        stoppuhr() - tc,
        f"{len(source_results) - n_quarantaene} Quellen abgefragt, "
        f"{len(items)} Meldungen gefunden"
        + (f", {n_quarantaene} stillgelegt" if n_quarantaene else ""),
    )
    log.info(
        "Collected %d items (%d ok / %d leer / %d fehlgeschlagen / %d stillgelegt)",
        len(items),
        n_ok,
        n_empty,
        n_fail,
        n_quarantaene,
    )

    td = stoppuhr()
    seen = SeenStore(state_dir / "seen.jsonl")
    first_run = len(seen) == 0
    new_items = filter_fresh(seen.filter_new(items), lookback)
    neu_je_quelle: dict[str, int] = defaultdict(int)
    for i in new_items:
        neu_je_quelle[i.source_url] += 1
    for rec in source_results:
        rec["new"] = neu_je_quelle.get(rec["url"], 0)
    register_zusammenfassung = register.verbuche_lauf(
        source_results,
        today_iso,
        quarantaene_nach=int(
            cfg.settings.get("quellen_quarantaene_nach_laeufen", 6) or 6
        ),
        quellen_der_config=quellen_der_config(cfg),
    )
    register.speichern()
    phase(
        "Nur Neues",
        stoppuhr() - td,
        f"{len(new_items)} neue Meldungen (Gedaechtnis: {len(seen)} bekannt)",
    )
    log.info(
        "Novelty filter: %d new items (seen store: %d known ids)",
        len(new_items),
        len(seen),
    )

    llm_was_explicitly_disabled = use_llm is False
    if use_llm is None:
        use_llm = llm_available()

    tk = stoppuhr()
    cluster_store = clustering.ClusterStore(state_dir / "clusters.jsonl")
    gruppen = clustering.gruppiere(
        sorted(new_items, key=_sort_key, reverse=True),
        model=mechanik_model,
        use_llm=bool(use_llm and cfg.settings.get("cluster_llm_pruefung", True)),
        max_llm_pruefungen=cfg.settings.get("cluster_max_llm_pruefungen"),
    )

    jetzt = uhr()
    nachklapp: list[clustering.Gruppe] = []
    aktuelle: list[clustering.Gruppe] = []
    for g in gruppen:
        if cluster_store.zuordnen(g.vertreter, jetzt) is not None:
            nachklapp.append(g)
        else:
            aktuelle.append(g)

    vertreter_items = [g.vertreter for g in aktuelle]
    belege_je_url = {g.vertreter.url: g for g in aktuelle}
    vertreter_item_von: dict[str, Item] = {}
    for g in gruppen:
        vertreter_item_von[g.vertreter.id] = g.vertreter
        for m in g.mitglieder:
            vertreter_item_von[m.id] = g.vertreter
    zusammengefasst = len(new_items) - len(vertreter_items)
    phase(
        "Ereignisse buendeln",
        stoppuhr() - tk,
        f"{len(vertreter_items)} Ereignisse aus {len(new_items)} Meldungen"
        + (f", {len(nachklapp)} Nachklapp" if nachklapp else ""),
    )
    log.info(
        "Ereignis-Cluster: %d Meldungen -> %d Ereignisse (%d gebuendelt, "
        "%d Nachklapp zu frueher berichteten Ereignissen)",
        len(new_items),
        len(vertreter_items),
        zusammengefasst,
        len(nachklapp),
    )

    items_by_region: dict[str, list[Item]] = defaultdict(list)
    for item in sorted(vertreter_items, key=_sort_key, reverse=True):
        items_by_region[item.region].append(item)
    for region_key, region_items in items_by_region.items():
        items_by_region[region_key] = _interleave_by_source(region_items)

    tvs = stoppuhr()
    items_by_region, vorsortierung_bilanz = vorsortieren(
        items_by_region,
        settings=cfg.settings,
        root=root,
        model=mechanik_model,
        use_llm=bool(use_llm and new_items),
        verstrichen=stoppuhr() - t0,
    )
    if vorsortierung_bilanz:
        phase(
            "Vorsortieren",
            stoppuhr() - tvs,
            f"{vorsortierung_bilanz['verworfen']} von "
            f"{vorsortierung_bilanz['angeboten']} aussortiert, "
            f"{vorsortierung_bilanz['durchlass']} direkt durchgelassen",
        )

    topics_store = ReportedTopics(
        state_dir / "reported_topics.jsonl",
        max_entries=int(cfg.settings.get("reported_topics_memory", 300)),
    )

    ta = stoppuhr()
    regional: dict[str, dict] = {}
    analyst_telemetry: list[dict] = []
    unanalysierte_regionen: set[str] = set()
    ungelesene_meldungen: set[str] = set()
    editor_used = False
    if use_llm and new_items:
        llm_workers = int(cfg.settings.get("llm_max_workers", 4))
        batch_workers = int(cfg.settings.get("analyst_batch_workers", 1) or 1)

        def _analyze_one(region_key, region_items):
            region_name = cfg.bereich_names.get(region_key, region_key)
            try:
                res = analyze_region(
                    region_name,
                    region_items,
                    model=analyst_model,
                    language=language,
                    max_items=max_items,
                    is_theme=is_theme_key(region_key),
                    batch_workers=batch_workers,
                    ausweich=anker_mechanik,
                )
                tel = dict(res.get("_telemetry", {}))
                tel["region"] = region_name
                if tel.get("batches") and not tel.get("batches_ok"):
                    unanalysierte_regionen.add(region_key)
                return region_name, res, tel
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "Analyst %s failed: %s - falling back to raw list", region_name, exc
                )
                unanalysierte_regionen.add(region_key)
                fallback = {
                    "region_summary": "",
                    "highlights": [
                        {
                            "title": i.title,
                            "operator": i.operator or "",
                            "url": i.url,
                            "category": "Sonstiges",
                            "relevance": 2,
                            "summary": i.summary[:200],
                            "why_it_matters": "",
                        }
                        for i in region_items[:10]
                    ],
                }
                return region_name, fallback, None

        with ThreadPoolExecutor(max_workers=max(1, llm_workers)) as _pool:
            _futs = [
                _pool.submit(_analyze_one, rk, ri) for rk, ri in items_by_region.items()
            ]
            for _fut in as_completed(_futs):
                region_name, res, tel = _fut.result()
                ungelesene_meldungen.update(res.pop("_ungelesen", []) or [])
                regional[region_name] = res
                if tel is not None:
                    analyst_telemetry.append(tel)
        themen_mit_inhalt = [
            cfg.theme_names[tk]
            for tk in cfg.theme_names
            if regional.get(cfg.theme_names[tk], {}).get("highlights")
        ]
        bewertete = sum(len(r.get("highlights") or []) for r in regional.values())
        zweistufig = _redaktion_zweistufig(cfg.settings, bewertete)
        try:
            if zweistufig:
                body, covered = editor.synthesize_zweistufig(
                    regional,
                    topics_store.recent(),
                    model=editor_model,
                    language=language,
                    themenbereiche=themen_mit_inhalt,
                    workers=int(cfg.settings.get("llm_max_workers", 4)),
                )
            else:
                body, covered = editor.synthesize(
                    regional,
                    topics_store.recent(),
                    model=editor_model,
                    language=language,
                    highlight_budget=int(
                        cfg.settings.get("editor_max_highlights", 0) or 0
                    ),
                    themenbereiche=themen_mit_inhalt,
                )
            editor_used = True
        except Exception as exc:  # noqa: BLE001
            if cfg.settings.get("publish_requires_editorial_briefing", True):
                raise RuntimeError(
                    "Editorial synthesis failed; refusing to publish a raw "
                    "source digest. The previous briefing remains live."
                ) from exc
            log.warning(
                "Editorial synthesis failed (%s); publishing a labelled "
                "source-linked fallback digest",
                str(exc)[:180],
            )
            fallback, covered = editor.build_digest(
                items_by_region,
                cfg.bereich_names,
                llm_was_available=False,
                include_note=False,
            )
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
        if (
            new_items
            and not llm_was_explicitly_disabled
            and cfg.settings.get("publish_requires_editorial_briefing", True)
        ):
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
                    {
                        "title": i.title,
                        "operator": i.operator or i.source_name,
                        "url": i.url,
                        "category": "Unbewertet",
                        "relevance": None,
                        "summary": i.summary[:220],
                        "why_it_matters": "",
                    }
                    for i in (
                        region_items if not max_items else region_items[:max_items]
                    )
                ],
            }
        body, covered = editor.build_digest(
            items_by_region, cfg.bereich_names, llm_was_available=bool(use_llm)
        )
        if first_run:
            body = (
                "> **Erster Lauf (Baseline):** Alle Quellen wurden initial "
                "eingelesen. Ab dem naechsten Lauf erscheinen nur noch "
                "wirklich neue Meldungen.\n\n" + body
            )
    phase(
        "Bewerten & Schreiben",
        stoppuhr() - ta,
        f"{sum(len(r.get('highlights') or []) for r in regional.values())} "
        f"bewertete Meldungen"
        if use_llm
        else "ohne KI (Roh-Digest)",
    )

    tctm = stoppuhr()
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
            alle,
            model=mechanik_model,
            use_llm=bool(
                use_llm and new_items and cfg.settings.get("ctm_belegpruefung", True)
            ),
        )
        log.info(
            "CTM-Linse: %d direkt / %d uebertragbar / %d Kontext / "
            "%d Hintergrund | Saetze: %d belegt, %d verworfen",
            ctm_bilanz.get("direkt", 0),
            ctm_bilanz.get("uebertragbar", 0),
            ctm_bilanz.get("kontext", 0),
            ctm_bilanz.get("hintergrund", 0),
            beleg_bilanz.get("belegt", 0),
            ctm_bilanz.get("saetze_verworfen", 0) + beleg_bilanz.get("verworfen", 0),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("CTM-Linse uebersprungen: %s", exc)
    phase(
        "Einordnen für uns",
        stoppuhr() - tctm,
        f"{ctm_bilanz.get('direkt', 0)} direkt handlungsrelevant, "
        f"{beleg_bilanz.get('belegt', 0)} belegte Folgerungssätze",
    )

    for r in regional.values():
        r.pop("_telemetry", None)

    competitor_profiles: list[dict] = []
    if use_llm and cfg.focus_competitors:
        tcomp = stoppuhr()
        try:
            comp_model = editor_model or analyst_model
            competitor_profiles = competitor_mod.analyze_all(
                cfg.focus_competitors,
                items,
                comp_model,
                language,
                max_workers=int(cfg.settings.get("llm_max_workers", 4)),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Competitor deep-dive failed: %s", exc)
        phase(
            "Wettbewerber-Analyse",
            stoppuhr() - tcomp,
            f"{len(competitor_profiles)} Profile "
            f"({sum(len(c.get('moves') or []) for c in competitor_profiles)} Moves)",
        )

    by_url = {i.url: i for i in new_items}
    for region in regional.values():
        for h in region.get("highlights", []):
            item = by_url.get(h.get("url", ""))
            if item is not None:
                h.setdefault(
                    "date",
                    item.published.date().isoformat() if item.published else None,
                )
                h.setdefault("source", item.source_name)
                h.setdefault("source_url", item.source_url)
                if getattr(item, "image_url", ""):
                    h.setdefault("image_url", item.image_url)
                gruppe = belege_je_url.get(h.get("url", ""))
                if gruppe is not None and gruppe.mitglieder:
                    h.setdefault("weitere_quellen", gruppe.belege())
                    h.setdefault("quellenzahl", gruppe.quellen)
                    h.setdefault("cluster_id", gruppe.id)
            else:
                h.setdefault("date", None)
                h.setdefault("source", "")
                h.setdefault("source_url", "")

    tbild = stoppuhr()
    alle_highlights = [h for r in regional.values() for h in r.get("highlights", [])]
    try:
        bild_bilanz = report_bilder.hole_bilder(alle_highlights, root)
    except Exception as exc:  # noqa: BLE001
        log.error("Bildbeschaffung fehlgeschlagen: %s", exc)
        bild_bilanz = {}
    n_bilder = bild_bilanz.get("geladen", 0)
    phase(
        "Bilder",
        stoppuhr() - tbild,
        f"{n_bilder} von {len(alle_highlights)} Meldungen mit Bild",
    )

    try:
        themen_bilanz = highlight_topics.pflege_highlight_themen(
            alle_highlights,
            state_dir,
            today_iso,
            model=editor_model or analyst_model,
            use_llm=bool(use_llm and new_items),
            reports_dir=reports_dir,
        )
        log.info(
            "Highlight-Themen: %d aktiv, %d Kandidat(en), neu: %s, beendet: %s",
            themen_bilanz["aktiv"],
            themen_bilanz["kandidaten"],
            ", ".join(themen_bilanz["neu"]) or "keins",
            ", ".join(themen_bilanz["beendet"]) or "keins",
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Highlight-Themen uebersprungen: %s", exc)

    try:
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
            flat_new,
            diff_store,
            today_iso,
            model=mechanik_model,
            use_llm=bool(use_llm and new_items),
        )
        log.info(
            "Differenzierung: %d neue Move(s) aufgenommen (Speicher: %d)",
            len(added),
            len(diff_store),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Differenzierungs-Kurator uebersprungen: %s", exc)

    try:
        category_sweep.run_sweep(
            state_dir,
            os.environ.get("BRAVE_API_KEY", ""),
            mechanik_model,
            bool(use_llm),
            today.isocalendar()[1],
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Kategorie-Sweep uebersprungen: %s", exc)

    promo_result: dict = {}
    if cfg.settings.get("promo_enabled", True):
        try:
            from .promo_pipeline import run_promo_stage

            promo_result = run_promo_stage(
                root,
                cfg.settings.get("http", {}),
                bool(use_llm),
                editor_model,
                language=language,
                settings=cfg.settings,
                score_model=mechanik_model,
                extract_model=mechanik_model,
            )
            log.info(
                "Promo-Uebersicht: %s (%d aktive Aktionen)",
                promo_result.get("mode"),
                promo_result.get("active", 0),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Promo-Uebersicht uebersprungen: %s", exc)

    geraete_bilanz: dict = {}
    _budget = geraete_budget(cfg.settings, stoppuhr() - t0)
    if _budget is None:
        if cfg.settings.get("geraete_enabled", False):
            log.warning(
                "Geraeteradar uebersprungen: zu wenig Jobzeit uebrig. "
                "Der naechtliche Lauf holt es nach - die "
                "Veroeffentlichung geht vor."
            )
    else:
        try:
            from .geraete_pipeline import run_geraete_stage

            geraete_bilanz = run_geraete_stage(
                root, cfg.settings.get("http", {}), today_iso, frist_sekunden=_budget
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Geraeteradar uebersprungen: %s", exc)

    diff_report_dir = reports_dir / "differenzierung"
    diff_report_dir.mkdir(parents=True, exist_ok=True)
    diff_db = DiffDB(state_dir / "differentiation_db.json")
    diff_entries = list(diff_db.entries.values())
    theme_labels = THEME_LABEL
    try:
        if use_llm and diff_entries:
            diff_body = differentiation_editor.synthesize(
                diff_entries, theme_labels, model=editor_model, language=language
            )
            diff_mode = "KI-Redaktion"
        else:
            diff_body = differentiation_editor.build_digest(diff_entries, theme_labels)
            diff_mode = "Regelbericht"
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "Differenzierungsbericht-Agent fehlgeschlagen (%s) – verwende Regelbericht",
            str(exc)[:160],
        )
        diff_body = differentiation_editor.build_digest(diff_entries, theme_labels)
        diff_mode = "Regelbericht (Fallback)"
    diff_report_path = diff_report_dir / f"{today.isoformat()}.md"
    diff_report_path.write_text(diff_body, encoding="utf-8")
    log.info("Differenzierungsbericht: %s (%d Moves)", diff_mode, len(diff_entries))

    try:
        diff_store_fuer_bilder = DiffStore(state_dir / "differentiation.jsonl")
        diff_bestand = differenzierung_view.merge(
            diff_entries, diff_store_fuer_bilder.entries()
        )
        bilanz = diff_bilder.beschaffe(
            diff_bestand, root, reports_dir, today.isoformat()
        )
        log.info(
            "Differenzierungs-Bilder: %d von %d Beispielen",
            bilanz.get("mit_bild", 0),
            bilanz.get("bestand", 0),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Differenzierungs-Bilder uebersprungen: %s", exc)

    total_sources = (
        sum(len(op.crawled_sources) for op in cfg.operators)
        + len(cfg.news_sources)
        + sum(1 for s in cfg.tech_sources if s.crawlable)
    )
    stats = {
        "sources_total": total_sources,
        "sources_ok": n_ok,
        "sources_empty": n_empty,
        "sources_failed": n_fail,
        "collected": len(items),
        "new": len(new_items),
        "events": len(vertreter_items),
        "bundled": zusammengefasst,
        "followups": len(nachklapp),
        "ctm_direkt": ctm_bilanz.get("direkt", 0),
        "ctm_uebertragbar": ctm_bilanz.get("uebertragbar", 0),
        "ctm_saetze": beleg_bilanz.get("belegt", 0),
        "ctm_saetze_verworfen": (
            ctm_bilanz.get("saetze_verworfen", 0) + beleg_bilanz.get("verworfen", 0)
        ),
        "tarif_seiten": aenderungs_bilanz.get("gelesen", 0),
        "tarif_aenderungen": aenderungs_bilanz.get("geaendert", 0),
        "lieferzeit_gemessen": lieferzeit_bilanz.get("gemessen", 0),
        "lieferzeit_engpaesse": len(lieferzeit_bilanz.get("engpaesse") or []),
        "tarif_dokumente": tarif_bilanz.get("gelesen", 0),
        "tarif_dokument_aenderungen": tarif_bilanz.get("geaendert", 0),
        "tarif_kleingedruckt": tarif_bilanz.get("kleingedruckt", 0),
        "ct_domains": ct_bilanz.get("gelesen", 0),
        "ct_funde": ct_bilanz.get("meldungen", 0),
        "ct_zeitueberschreitung": ct_bilanz.get("zeitueberschreitung", 0),
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
    stats |= promo_stats(promo_result)

    duration = stoppuhr() - t0
    kosten = llm.kosten_stand()

    kind_counts: dict[str, int] = defaultdict(int)
    for r in source_results:
        kind_counts[r["kind"]] += 1
    run_log = {
        "started_at": started_at.isoformat(),
        "finished_at": uhr().isoformat(),
        "duration_seconds": round(duration, 1),
        "used_llm": bool(use_llm and new_items),
        "editor_used": editor_used,
        "models": {
            "analyst": analyst_model if (use_llm and new_items) else None,
            "editor": editor_model if editor_used else None,
            "mechanik": mechanik_model if (use_llm and new_items) else None,
            "unavailable": sorted(llm.dead_models()) or None,
            "anker": anker or None,
        },
        "kosten": kosten,
        "vorsortierung": vorsortierung_bilanz or None,
        "phases": phases,
        "source_summary": {
            "total": len(source_results),
            "ok": n_ok,
            "empty": n_empty,
            "failed": n_fail,
            "quarantaene": n_quarantaene,
            "by_kind": dict(kind_counts),
        },
        "register": register_zusammenfassung,
        "sources": sorted(
            source_results,
            key=lambda r: (
                {"fail": 0, "ok": 1, "empty": 2}.get(r["status"], 3),
                -r.get("count", 0),
            ),
        ),
        "analysts": analyst_telemetry,
    }

    stats["bewertete"] = redaktion_kontinuitaet.bewertete_meldungen(
        {"regions": regional}
    )
    grund = (
        "es gab keine neuen Meldungen zu bewerten"
        if not new_items
        else "eine vorübergehende Störung des Analyse-Dienstes"
    )
    regional, body, competitor_profiles, redaktion_ausfall = (
        redaktion_kontinuitaet.uebernehmen(
            regional, body, competitor_profiles, reports_dir, today.isoformat(), grund
        )
    )

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
    if redaktion_ausfall:
        report_json["redaktion_ausfall"] = redaktion_ausfall
    report_json["geraete_bewegung"] = geraete_bewegung.fuer_bericht(
        root, today, reports_dir
    )
    json_path = reports_dir / f"{today.isoformat()}.json"
    json_path.write_text(
        json.dumps(report_json, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log.info("Report written: %s (+ .json), run took %.1fs", report_path, duration)

    zu_merken = zu_merkende_meldungen(
        new_items, vertreter_item_von, ungelesene_meldungen, unanalysierte_regionen
    )
    gemerkt = {i.id for i in zu_merken}
    uebersprungen = len(new_items) - len(zu_merken)
    if uebersprungen:
        log.warning(
            "%d Meldungen NICHT als gesehen markiert (%d Region(en) "
            "ganz ohne Analyse, %d Meldungen aus gescheiterten "
            "Stapeln) - der naechste Lauf holt sie erneut",
            uebersprungen,
            len(unanalysierte_regionen),
            len(ungelesene_meldungen),
        )
    seen.add(zu_merken)
    cluster_store.merke([g for g in aktuelle if g.vertreter.id in gemerkt], today_iso)
    if covered and editor_used:
        topics_store.add(covered, today.isoformat())
    elif covered:
        log.warning(
            "%d Themen stammen aus dem Notfall-Digest, nicht aus der "
            "Redaktion - sie werden NICHT als berichtet gemerkt",
            len(covered),
        )

    uebersetzung_bilanz: dict = {}
    _ueb_items = uebersetzung_stufe.berichtete_items(alle_highlights, by_url)
    if len(_ueb_items) < len(alle_highlights):
        log.info(
            "Uebersetzung: %d von %d berichteten Meldungen ohne "
            "zugehoeriges Item (Dubletten oder umgeschriebene Adresse)",
            len(alle_highlights) - len(_ueb_items),
            len(alle_highlights),
        )
    _ueb_budget = uebersetzung_stufe.budget(cfg.settings, stoppuhr() - t0)
    if _ueb_budget is None:
        if cfg.settings.get("uebersetzung_enabled", True):
            log.warning(
                "Uebersetzung uebersprungen: zu wenig Jobzeit uebrig. "
                "Die Veroeffentlichung geht vor."
            )
    elif not llm.llm_available():
        log.info("Uebersetzung uebersprungen: kein Modellzugang.")
    else:
        try:
            uebersetzung_bilanz = uebersetzung_stufe.lauf(
                _ueb_items,
                root,
                cfg.settings,
                mechanik_model,
                frist_sekunden=_ueb_budget,
                heute=today,
            )
            log.info("%s", uebersetzung_stufe.protokollzeile(uebersetzung_bilanz))
            run_log["uebersetzung"] = {
                k: (dict(v) if isinstance(v, Counter) else v)
                for k, v in uebersetzung_bilanz.items()
            }
        except Exception as exc:  # noqa: BLE001
            log.error("Uebersetzung uebersprungen: %s: %s", type(exc).__name__, exc)

    run_log["kosten"] = llm.kosten_stand()
    report_json["run"] = run_log
    _protokolliere_kosten(run_log["kosten"])
    json_path.write_text(
        json.dumps(report_json, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    try:
        report_bilder.raeume_auf(root, reports_dir)
    except Exception as exc:  # noqa: BLE001
        log.error("Bilder-Aufraeumen fehlgeschlagen: %s", exc)
    ausfaelle = render_site(root / "site", reports_dir, cfg)

    try:
        from .versand import versende

        run_log["versand"] = versende(root, report_json, cfg.settings)
        json_path.write_text(
            json.dumps(report_json, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Versand uebersprungen: %s", exc)

    return report_path, ausfaelle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Telco Radar pipeline")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="project root (contains config/, data/, site/)",
    )
    parser.add_argument(
        "--no-llm", action="store_true", help="skip LLM analysis, produce raw digest"
    )
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
        _, ausfaelle = run(
            args.root.resolve(),
            use_llm=False if args.no_llm else None,
            lookback_days=args.lookback_days,
        )
    except Exception:  # noqa: BLE001
        log.exception("Pipeline failed")
        return 1
    for ausfall in ausfaelle:
        log.error(
            "Seite nicht vollständig neu gebaut: %s (%s)", ausfall.teil, ausfall.grund
        )
    return 3 if ausfaelle else 0


if __name__ == "__main__":
    raise SystemExit(main())
