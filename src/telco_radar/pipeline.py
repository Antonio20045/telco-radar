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
from collections.abc import Callable
from functools import partial
from itertools import zip_longest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from .analyze import bewertung as bewertung_mod
from .analyze import editor
from .analyze import clustering
from .analyze import ctm as ctm_mod
from .analyze import einordnung as einordnung_mod
from .analyze import category_sweep
from .analyze import differentiation_editor
from .analyze.begriffe import THEME_LABEL
from .analyze.diff_curator import DiffStore
from .analyze.diff_db import DiffDB
from .analyze import redaktion_kontinuitaet
from .analyze import vorsortierung as vorsortierung_mod
from .uebersetzung import stufe as uebersetzung_stufe
from .analyze import llm
from .analyze.llm import llm_available, active_backend
from .analyze.takt import Takt
from .collect import collect_all, tag_news_regions
from .config import Config, load_config
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

T = TypeVar("T")

LANGUAGES = {"de": "Deutsch", "en": "English"}

_GERAETE_MINDESTBUDGET = 240.0

_STATUS_SCHLUESSEL = {
    "ok": "ok",
    "empty": "empty",
    "failed": "fail",
    "quarantaene": "quarantaene",
}
_STATUS_RANG = {"fail": 0, "ok": 1, "empty": 2}


def geraete_budget(settings: dict, verstrichen: float):
    """Restzeit des Jobs für die Gerätestufe; ``None`` heißt nicht anfangen."""
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
    return str(settings.get(f"{anbieter}_mechanik_model") or "").strip() or fallback


ANKER_REDAKTION = "claude-sonnet-5"
ANKER_MECHANIK = "claude-haiku-4-5-20251001"


def anker_modelle(settings: dict) -> tuple[str, str]:
    """(Redaktionsanker, Mechanikanker), oder ``("", "")``, wenn abgeschaltet."""
    if not settings.get("llm_anker", True):
        return "", ""
    return (
        str(settings.get("anker_redaktion_model", ANKER_REDAKTION) or "").strip(),
        str(settings.get("anker_mechanik_model", ANKER_MECHANIK) or "").strip(),
    )


def _registriere_ausweichmodell(
    settings: dict, analyst_model: str, editor_model: str
) -> bool:
    if not (settings.get("editor_model_fallback", True) and analyst_model):
        return False
    if any(anker_modelle(settings)):
        return False
    llm.set_fallback(editor_model, analyst_model)
    return True


def _registriere_anker(
    settings: dict, analyst_model: str, editor_model: str, mechanik_model: str
) -> dict[str, str]:
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


def zu_merkende_meldungen(
    new_items: list[Item],
    vertreter_item_von: dict[str, Item],
    ungelesene_meldungen: set[str],
    unanalysierte_regionen: set[str],
) -> list[Item]:
    """Welche Meldungen als gesehen gelten; ein Beleg zählt über seinen Vertreter."""

    def gelesen(item: Item) -> bool:
        chef = vertreter_item_von.get(item.id, item)
        return (
            chef.id not in ungelesene_meldungen
            and chef.region not in unanalysierte_regionen
        )

    return [i for i in new_items if gelesen(i)]


_VORSORTIERUNG_MINDESTBUDGET = 60.0


def vorsortierung_budget(settings: dict, verstrichen: float) -> float | None:
    """Zeit für die Vorsortierung aus der Restzeit; ``None`` heißt nicht anfangen."""
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
    """Die Vorsortierung, wie der Lauf sie aufruft; fällt sie aus, bleibt alles."""
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
    """Die Promo-Zahlen fürs Laufprotokoll; leer, wenn die Stufe nicht lief."""
    if not promo_result:
        return {}
    return {
        "promo_seiten_gelesen": promo_result.get("seiten_gelesen", 0),
        "promo_angebote_neu": promo_result.get("angebote_neu", 0),
        "promo_angebote_bestaetigt": promo_result.get("angebote_bestaetigt", 0),
        "promo_extraktion_fehler": promo_result.get("extraktion_fehlgeschlagen", 0),
    }


def _sort_key(item: Item):
    pub = item.published
    if pub is None:
        return (0, "")
    return (1, pub.isoformat())


def _interleave_by_source(items: list[Item]) -> list[Item]:
    buckets: dict[str, list[Item]] = defaultdict(list)
    for item in sorted(items, key=_sort_key, reverse=True):
        buckets[item.operator or item.source_name].append(item)
    order = sorted(buckets.values(), key=lambda b: _sort_key(b[0]), reverse=True)
    out: list[Item] = []
    for round_items in zip_longest(*order):
        out.extend(i for i in round_items if i is not None)
    return out


@dataclass(frozen=True)
class Modelle:
    """Die für einen Lauf gewählten Modelle samt Ausweich- und Ankermodellen."""

    analyst: str
    editor: str
    mechanik: str
    anker: dict
    anker_mechanik: str


@dataclass(frozen=True)
class Sammlung:
    """Ergebnis der Phase Sammeln: Meldungen, Quellenstatus, Zusatzbilanzen."""

    items: list[Item]
    source_results: list[dict]
    register: Quellenregister
    bilanzen: dict[str, dict]
    state_dir: Path

    def zaehle(self, status: str) -> int:
        """Wie viele Quellen dieses Laufs den Status ``status`` hatten."""
        return sum(1 for r in self.source_results if r["status"] == status)

    def kennzahlen(self, cfg: Config) -> dict:
        """Die Quellenzahlen am Anfang von ``stats`` im Berichts-JSON."""
        return {
            "sources_total": sum(len(op.crawled_sources) for op in cfg.operators)
            + len(cfg.news_sources)
            + sum(1 for s in cfg.tech_sources if s.crawlable),
            "sources_ok": self.zaehle("ok"),
            "sources_empty": self.zaehle("empty"),
            "sources_failed": self.zaehle("fail"),
            "collected": len(self.items),
        }

    def zusatz_kennzahlen(self) -> dict:
        """Die Zahlen der Zusatzsammler für ``stats`` im Berichts-JSON."""
        b = self.bilanzen
        return {
            "tarif_seiten": b["aenderung"].get("gelesen", 0),
            "tarif_aenderungen": b["aenderung"].get("geaendert", 0),
            "lieferzeit_gemessen": b["lieferzeit"].get("gemessen", 0),
            "lieferzeit_engpaesse": len(b["lieferzeit"].get("engpaesse") or []),
            "tarif_dokumente": b["tarif"].get("gelesen", 0),
            "tarif_dokument_aenderungen": b["tarif"].get("geaendert", 0),
            "tarif_kleingedruckt": b["tarif"].get("kleingedruckt", 0),
            "ct_domains": b["ct"].get("gelesen", 0),
            "ct_funde": b["ct"].get("meldungen", 0),
            "ct_zeitueberschreitung": b["ct"].get("zeitueberschreitung", 0),
        }

    def zusammenfassung(self) -> dict:
        """Quellenzahlen je Status und je Art für ``run.source_summary``."""
        return {
            "total": len(self.source_results),
            **{k: self.zaehle(s) for k, s in _STATUS_SCHLUESSEL.items()},
            "by_kind": dict(Counter(r["kind"] for r in self.source_results)),
        }

    def sortiert(self) -> list[dict]:
        """Quellen für ``run.sources``: erst gescheiterte, dann nach Meldungszahl."""
        return sorted(
            self.source_results,
            key=lambda r: (_STATUS_RANG.get(r["status"], 3), -r.get("count", 0)),
        )


@dataclass(frozen=True)
class Neuheit:
    """Ergebnis der Phase Nur Neues: Seen-Store, neue Meldungen, Registerbilanz."""

    seen: SeenStore
    first_run: bool
    new_items: list[Item]
    register_zusammenfassung: dict


@dataclass(frozen=True)
class Buendel:
    """Ergebnis der Phase Bündeln: Ereignisse, Nachklapp und Meldungen je Bereich."""

    cluster_store: clustering.ClusterStore
    aktuelle: list[clustering.Gruppe]
    nachklapp: list[clustering.Gruppe]
    vertreter_items: list[Item]
    vertreter_item_von: dict[str, Item]
    items_by_region: dict[str, list[Item]]

    @property
    def belege_je_url(self) -> dict[str, clustering.Gruppe]:
        """Die Gruppe jedes aktuellen Ereignisses unter der Adresse ihres Vertreters."""
        return {g.vertreter.url: g for g in self.aktuelle}


def _phase_eintragen(liste: list[dict], name: str, sek: float, detail: str) -> None:
    liste.append({"name": name, "seconds": round(sek, 1), "detail": detail})


def _modelle_waehlen(settings: dict) -> Modelle:
    fallback_model = settings.get("model", "claude-sonnet-5")
    anbieter = _waehle_anbieter(settings)
    analyst_model, editor_model = _modelle_fuer_anbieter(
        settings, anbieter, fallback_model
    )
    mechanik_model = _mechanik_modell(settings, anbieter, analyst_model)
    ausweich_aktiv = _registriere_ausweichmodell(settings, analyst_model, editor_model)
    _, anker_mechanik = anker_modelle(settings)
    anker = _registriere_anker(settings, analyst_model, editor_model, mechanik_model)
    llm.kosten_reset()
    llm.budget_setzen(
        settings.get("llm_budget_usd", 1.5), settings.get("llm_preise") or {}
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
        settings.get("llm_budget_usd", 1.5) or "keine",
    )
    return Modelle(analyst_model, editor_model, mechanik_model, anker, anker_mechanik)


def _hole(art: str, root: Path, http: dict, modell: str) -> tuple[list[Item], dict]:
    if art == "lieferzeit":
        from .collect import lieferzeit

        return [], lieferzeit.sammle(root, http)
    if art == "aenderung":
        from .collect import aenderungen

        return aenderungen.sammle(root, http)
    if art == "tarif":
        from .collect import tarif_crawler

        return tarif_crawler.sammle(root, http)
    from .collect import ct_log

    return ct_log.sammle(root, http, modell=modell, komplett=llm.complete)


_ZUSATZSAMMLER = {
    "lieferzeit": ("lieferzeit_radar_aktiv", "Lieferzeit-Radar"),
    "aenderung": ("aenderungsradar_aktiv", "Aenderungsradar"),
    "tarif": ("tarif_radar_aktiv", "Tarif-Sammler"),
    "ct": ("ct_radar_aktiv", "CT-Radar"),
}


def _zusatzsammler(
    root: Path, settings: dict, ct_modell: str
) -> tuple[list[Item], dict[str, dict]]:
    http = settings.get("http", {})
    items: list[Item] = []
    bilanzen: dict[str, dict] = {}
    for schluessel, (schalter, name) in _ZUSATZSAMMLER.items():
        bilanzen[schluessel] = {}
        if not settings.get(schalter, True):
            continue
        try:
            neue, bilanzen[schluessel] = _hole(schluessel, root, http, ct_modell)
            items.extend(neue)
        except Exception as exc:  # noqa: BLE001
            log.error("%s uebersprungen: %s", name, exc)
    return items, bilanzen


def _sammeln(
    root: Path,
    cfg: Config,
    modell: str,
    use_llm: bool | None,
    stoppuhr: Callable[[], float],
    phase: Callable[[str, float, str], None],
) -> Sammlung:
    ct_modell = modell if (use_llm is not False and llm_available()) else ""
    tc = stoppuhr()
    state_dir = root / "data" / "state"
    register = Quellenregister(state_dir / "quellen_register.json")
    items, source_results = collect_all(cfg, register=register)
    tag_news_regions(items, cfg.operators)
    zusatz, bilanzen = _zusatzsammler(root, cfg.settings, ct_modell)
    items.extend(zusatz)
    sammlung = Sammlung(items, source_results, register, bilanzen, state_dir)
    n_quarantaene = sammlung.zaehle("quarantaene")
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
        sammlung.zaehle("ok"),
        sammlung.zaehle("empty"),
        sammlung.zaehle("fail"),
        n_quarantaene,
    )
    return sammlung


def _nur_neues(
    sammlung: Sammlung,
    cfg: Config,
    lookback_days: int | None,
    today_iso: str,
    stoppuhr: Callable[[], float],
    phase: Callable[[str, float, str], None],
) -> Neuheit:
    td = stoppuhr()
    seen = SeenStore(sammlung.state_dir / "seen.jsonl")
    first_run = len(seen) == 0
    lookback = lookback_days or cfg.lookback_days
    new_items = filter_fresh(seen.filter_new(sammlung.items), lookback)
    neu_je_quelle: dict[str, int] = defaultdict(int)
    for i in new_items:
        neu_je_quelle[i.source_url] += 1
    for rec in sammlung.source_results:
        rec["new"] = neu_je_quelle.get(rec["url"], 0)
    register_zusammenfassung = sammlung.register.verbuche_lauf(
        sammlung.source_results,
        today_iso,
        quarantaene_nach=int(
            cfg.settings.get("quellen_quarantaene_nach_laeufen", 6) or 6
        ),
        quellen_der_config=quellen_der_config(cfg),
    )
    sammlung.register.speichern()
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
    return Neuheit(seen, first_run, new_items, register_zusammenfassung)


def _buendeln(
    new_items: list[Item],
    cfg: Config,
    state_dir: Path,
    mechanik_model: str,
    use_llm: bool,
    uhr: Callable[[], datetime],
    stoppuhr: Callable[[], float],
    phase: Callable[[str, float, str], None],
) -> Buendel:
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
    vertreter_item_von: dict[str, Item] = {}
    for g in gruppen:
        vertreter_item_von[g.vertreter.id] = g.vertreter
        for m in g.mitglieder:
            vertreter_item_von[m.id] = g.vertreter
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
        len(new_items) - len(vertreter_items),
        len(nachklapp),
    )
    items_by_region: dict[str, list[Item]] = defaultdict(list)
    for item in sorted(vertreter_items, key=_sort_key, reverse=True):
        items_by_region[item.region].append(item)
    for region_key, region_items in items_by_region.items():
        items_by_region[region_key] = _interleave_by_source(region_items)
    return Buendel(
        cluster_store,
        aktuelle,
        nachklapp,
        vertreter_items,
        vertreter_item_von,
        items_by_region,
    )


def _belege_anhaengen(
    regional: dict[str, dict], by_url: dict[str, Item], buendel: Buendel
) -> None:
    for region in regional.values():
        for h in region.get("highlights", []):
            item = by_url.get(h.get("url", ""))
            if item is None:
                h.setdefault("date", None)
                h.setdefault("source", "")
                h.setdefault("source_url", "")
                continue
            h.setdefault(
                "date", item.published.date().isoformat() if item.published else None
            )
            h.setdefault("source", item.source_name)
            h.setdefault("source_url", item.source_url)
            if getattr(item, "image_url", ""):
                h.setdefault("image_url", item.image_url)
            gruppe = buendel.belege_je_url.get(h.get("url", ""))
            if gruppe is not None and gruppe.mitglieder:
                h.setdefault("weitere_quellen", gruppe.belege())
                h.setdefault("quellenzahl", gruppe.quellen)
                h.setdefault("cluster_id", gruppe.id)


def _gesehen_merken(
    neuheit: Neuheit,
    buendel: Buendel,
    ungelesene: set[str],
    unanalysierte: set[str],
    today_iso: str,
) -> None:
    zu_merken = zu_merkende_meldungen(
        neuheit.new_items, buendel.vertreter_item_von, ungelesene, unanalysierte
    )
    gemerkt = {i.id for i in zu_merken}
    uebersprungen = len(neuheit.new_items) - len(zu_merken)
    if uebersprungen:
        log.warning(
            "%d Meldungen NICHT als gesehen markiert (%d Region(en) "
            "ganz ohne Analyse, %d Meldungen aus gescheiterten "
            "Stapeln) - der naechste Lauf holt sie erneut",
            uebersprungen,
            len(unanalysierte),
            len(ungelesene),
        )
    neuheit.seen.add(zu_merken)
    buendel.cluster_store.merke(
        [g for g in buendel.aktuelle if g.vertreter.id in gemerkt], today_iso
    )


def _abgesichert(aufgabe: Callable[[], T], bei_fehler: Callable[[Exception], T]) -> T:
    try:
        return aufgabe()
    except Exception as exc:  # noqa: BLE001
        return bei_fehler(exc)


@dataclass(frozen=True)
class Vorsortierung:
    """Ergebnis der Phase Vorsortieren: Meldungen je Bereich und ihre Bilanz."""

    items_by_region: dict[str, list[Item]]
    bilanz: dict


def _vorsortieren(
    buendel: Buendel,
    cfg: Config,
    root: Path,
    mechanik_model: str,
    use_llm: bool,
    t0: float,
    stoppuhr: Callable[[], float],
    phase: Callable[[str, float, str], None],
) -> Vorsortierung:
    tvs = stoppuhr()
    items_by_region, bilanz = vorsortieren(
        buendel.items_by_region,
        settings=cfg.settings,
        root=root,
        model=mechanik_model,
        use_llm=use_llm,
        verstrichen=stoppuhr() - t0,
    )
    if bilanz:
        phase(
            "Vorsortieren",
            stoppuhr() - tvs,
            f"{bilanz['verworfen']} von {bilanz['angeboten']} aussortiert, "
            f"{bilanz['durchlass']} direkt durchgelassen",
        )
    return Vorsortierung(items_by_region, bilanz)


def _bilder(
    regional: dict[str, dict],
    root: Path,
    stoppuhr: Callable[[], float],
    phase: Callable[[str, float, str], None],
) -> list[dict]:
    tbild = stoppuhr()
    alle_highlights = [h for r in regional.values() for h in r.get("highlights", [])]
    try:
        bild_bilanz = report_bilder.hole_bilder(alle_highlights, root)
    except Exception as exc:  # noqa: BLE001
        log.error("Bildbeschaffung fehlgeschlagen: %s", exc)
        bild_bilanz = {}
    phase(
        "Bilder",
        stoppuhr() - tbild,
        f"{bild_bilanz.get('geladen', 0)} von {len(alle_highlights)} "
        "Meldungen mit Bild",
    )
    return alle_highlights


def run(
    root: Path,
    use_llm: bool | None = None,
    lookback_days: int | None = None,
    naehte: Naehte = PRODUKTION,
) -> tuple[Path, list[Ausfall]]:
    """Execute one full radar run; returns the report path and unbuilt site parts."""
    uhr = naehte.setzen() or partial(datetime.now, timezone.utc)
    stoppuhr = naehte.stoppuhr or time.monotonic
    t0 = stoppuhr()
    started_at = uhr()
    cfg = load_config(root)
    language = LANGUAGES.get(cfg.settings.get("report_language", "de"), "Deutsch")
    modelle = _modelle_waehlen(cfg.settings)
    analyst_model, editor_model = modelle.analyst, modelle.editor
    mechanik_model, anker = modelle.mechanik, modelle.anker
    today = started_at.date()
    today_iso = today.isoformat()
    state_dir = root / "data" / "state"
    reports_dir = root / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    phases: list[dict] = []
    phase = partial(_phase_eintragen, phases)
    sammlung = _sammeln(root, cfg, mechanik_model, use_llm, stoppuhr, phase)
    neuheit = _nur_neues(sammlung, cfg, lookback_days, today_iso, stoppuhr, phase)
    new_items = neuheit.new_items
    llm_was_explicitly_disabled = use_llm is False
    if use_llm is None:
        use_llm = llm_available()

    buendel = _buendeln(
        new_items, cfg, state_dir, mechanik_model, use_llm, uhr, stoppuhr, phase
    )
    mit_llm = bool(use_llm and new_items)
    vorsortierung = _vorsortieren(
        buendel, cfg, root, mechanik_model, mit_llm, t0, stoppuhr, phase
    )
    topics_store = ReportedTopics(
        state_dir / "reported_topics.jsonl",
        max_entries=int(cfg.settings.get("reported_topics_memory", 300)),
    )
    takt = Takt(stoppuhr, phase, _abgesichert)
    bewertung = bewertung_mod.bewerten(
        cfg,
        vorsortierung.items_by_region,
        (new_items, neuheit.first_run),
        (use_llm, llm_was_explicitly_disabled),
        (analyst_model, editor_model, modelle.anker_mechanik),
        language,
        topics_store.recent,
        takt,
    )
    regional, body, covered = bewertung.regional, bewertung.body, bewertung.covered
    editor_used = bewertung.editor_used
    einordnung = einordnung_mod.einordnen(
        regional, cfg, root, mechanik_model, mit_llm, takt
    )
    ctm_bilanz, beleg_bilanz = einordnung.ctm, einordnung.beleg
    competitor_profiles: list[dict] = []
    if use_llm and cfg.focus_competitors:
        competitor_profiles = einordnung_mod.wettbewerber(
            cfg,
            sammlung.items,
            editor_model or analyst_model,
            language,
            takt,
        )

    by_url = {i.url: i for i in new_items}
    _belege_anhaengen(regional, by_url, buendel)

    alle_highlights = _bilder(regional, root, stoppuhr, phase)
    einordnung_mod.themen_und_moves(
        regional,
        cfg,
        (state_dir, reports_dir, today_iso),
        (editor_model or analyst_model, mechanik_model),
        mit_llm,
        takt,
    )

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

    stats = {
        **sammlung.kennzahlen(cfg),
        "new": len(new_items),
        "events": len(buendel.vertreter_items),
        "bundled": len(new_items) - len(buendel.vertreter_items),
        "followups": len(buendel.nachklapp),
        "ctm_direkt": ctm_bilanz.get("direkt", 0),
        "ctm_uebertragbar": ctm_bilanz.get("uebertragbar", 0),
        "ctm_saetze": beleg_bilanz.get("belegt", 0),
        "ctm_saetze_verworfen": (
            ctm_bilanz.get("saetze_verworfen", 0) + beleg_bilanz.get("verworfen", 0)
        ),
        **sammlung.zusatz_kennzahlen(),
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

    run_log = {
        "started_at": started_at.isoformat(),
        "finished_at": uhr().isoformat(),
        "duration_seconds": round(duration, 1),
        "used_llm": mit_llm,
        "editor_used": editor_used,
        "models": {
            "analyst": analyst_model if mit_llm else None,
            "editor": editor_model if editor_used else None,
            "mechanik": mechanik_model if mit_llm else None,
            "unavailable": sorted(llm.dead_models()) or None,
            "anker": anker or None,
        },
        "kosten": kosten,
        "vorsortierung": vorsortierung.bilanz or None,
        "phases": phases,
        "source_summary": sammlung.zusammenfassung(),
        "register": neuheit.register_zusammenfassung,
        "sources": sammlung.sortiert(),
        "analysts": bewertung.analyst_telemetry,
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
        "generated_with_llm": mit_llm,
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

    _gesehen_merken(
        neuheit,
        buendel,
        bewertung.ungelesene_meldungen,
        bewertung.unanalysierte_regionen,
        today_iso,
    )
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
