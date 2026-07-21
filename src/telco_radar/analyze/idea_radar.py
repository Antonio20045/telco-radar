"""Ideen-Radar: wöchentlich vom Agenten aktualisierte Inspirations-Zeilen.

Für jeden Differenzierungs-Hebel eine kompakte "Vorbild → Idee"-Zeile: was macht
ein Wettbewerber gerade konkret, und welche Idee ergibt sich daraus für Vodafone.
Anders als der frühere, fest verdrahtete Katalog wird das hier bei jedem Lauf von
einem Kurator-Agenten aus der AKTUELLEN Marktlage (den gesammelten Meldungen der
Woche) neu geschrieben und in data/state/idea_radar.json persistiert.

Robust: Ohne LLM (oder bei Fehler) greift ein deterministischer Seed aus den
gepflegten Vorbildern/Impulsen der Hebel-Definitionen – die Seite bricht nie.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..report.differentiation import DIFF_THEMES
from .llm import complete, extract_json

log = logging.getLogger(__name__)

_THEME_BY_KEY = {t["key"]: t for t in DIFF_THEMES}


def _short(text: str, limit: int = 105) -> str:
    """Kürze den (langen) Seed-Impuls auf eine knappe Idee-Zeile (Wortgrenze)."""
    t = " ".join((text or "").split())
    for sep in (". ", "! ", "? ", " – ", " - "):
        k = t.find(sep)
        if 8 < k < limit:
            return t[:k].rstrip(" –-")
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0].rstrip(" ,;–-")
    return cut + "…"


def seed_radar() -> dict:
    """Deterministischer Fallback aus den Hebel-Definitionen."""
    out = {}
    for t in DIFF_THEMES:
        vb = t["vorbilder"][0]
        out[t["key"]] = {
            "label": t["label"], "color": t["color"],
            "vorbild": vb["name"], "idee": _short(t["impuls"]), "url": None,
        }
    return out


IDEA_SYSTEM = """\
Du pflegst den „Ideen-Radar" für Vodafone: pro Differenzierungs-Hebel EINE knappe,
aktuelle Zeile, wie sich Wettbewerber im Endkundengeschäft JENSEITS DES PREISES
abheben (eingebundene Dienste, Garantien, KI, Security, Fintech, Super-Apps,
Cloud, Smart Home, Gaming, Loyalty, Health – NICHT Netz/5G/Glasfaser, NICHT B2B,
NICHT Preis/Tarif).

Du bekommst die Liste der Hebel und einen Auszug der Wettbewerber-Meldungen dieser
Woche. Schreibe je Hebel:
- "vorbild": EIN konkreter, echter Betreiber + was er tut (max ~10 Wörter). Nimm
  bevorzugt ein Beispiel aus den Meldungen dieser Woche, wenn eines passt; sonst
  ein bekanntes, real existierendes Beispiel. Keine erfundenen Fakten.
- "idee": EINE konkrete, umsetzbare Idee für Vodafone daraus (max ~12 Wörter,
  Klartext, kein Marketing).

Antworte AUSSCHLIESSLICH mit JSON, ein Objekt pro Hebel:
[{"key":"<hebel-key>","vorbild":"...","idee":"..."}]
Nutze exakt die vorgegebenen key-Werte. Kein weiterer Text.
"""


def _llm_generate(news_digest: str, model: str) -> dict:
    themes = [{"key": t["key"], "hebel": t["label"], "worum": t["blurb"][:120]}
              for t in DIFF_THEMES]
    user = json.dumps({"hebel": themes, "meldungen_der_woche": news_digest},
                      ensure_ascii=False)
    raw = complete(IDEA_SYSTEM, user, model=model, max_tokens=1800)
    parsed = extract_json(raw)
    out = {}
    for row in parsed if isinstance(parsed, list) else []:
        if not isinstance(row, dict):
            continue
        k = row.get("key")
        if k in _THEME_BY_KEY and row.get("vorbild") and row.get("idee"):
            out[k] = {"vorbild": str(row["vorbild"]).strip(),
                      "idee": str(row["idee"]).strip()}
    return out


def refresh(path: Path, news_digest: str, model: str | None,
            use_llm: bool = False) -> dict:
    """Erzeuge den Ideen-Radar neu (Agent, sonst Seed) und persistiere ihn."""
    data = seed_radar()
    if use_llm and model and news_digest:
        try:
            gen = _llm_generate(news_digest, model)
            for k, v in gen.items():
                data[k]["vorbild"] = v["vorbild"]
                data[k]["idee"] = v["idee"]
            log.info("Ideen-Radar: %d/%d Hebel vom Agenten aktualisiert",
                     len(gen), len(data))
        except Exception as exc:  # noqa: BLE001
            log.warning("Ideen-Radar (LLM) fehlgeschlagen (%s) – Seed genutzt",
                        str(exc)[:160])
    save(path, data)
    return data


def save(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"levers": data}, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def load_or_seed(path: Path) -> dict:
    """Für das Rendering: gespeicherten Radar laden, fehlende Hebel/Felder aus
    dem Seed auffüllen (Label/Farbe kommen immer aus der aktuellen Definition)."""
    base = seed_radar()
    p = Path(path)
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            for k, v in (raw.get("levers") or {}).items():
                if k in base and isinstance(v, dict):
                    for f in ("vorbild", "idee", "url"):
                        if v.get(f):
                            base[k][f] = v[f]
        except (json.JSONDecodeError, OSError):
            log.warning("Ideen-Radar-Datei unlesbar – Seed genutzt")
    return base
