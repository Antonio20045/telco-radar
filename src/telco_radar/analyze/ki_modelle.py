"""Die zehn stärksten KI-Modelle aus zwei Ranglisten (Pitch 9, Schnitt 6).

Es zählen nur Modelle aus ``config/ki_modelle.yaml``, die in beiden Listen
stehen. Je Liste zählt der Platz innerhalb dieser gemeinsamen Menge; bei
Artificial Analysis teilen sich Modelle mit gleichem Index den mittleren Platz.
Der Rang ist das Mittel der beiden Plätze, bei Gleichstand entscheidet der
höhere AA-Index, dann der bessere Arena-Platz. Der Store
``data/state/ki_rangliste.json`` hält Stand, Top 10 und je Quelle ``error``;
fällt ein Abruf aus, bleibt die letzte Rangliste stehen. Lesen ohne Netz, damit
``report/`` den Store laden darf.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

STORE_NAME = "ki_rangliste.json"
KATALOG = Path("config") / "ki_modelle.yaml"
TOP = 10
QUELLEN_NAMEN = {"aa": "Artificial Analysis", "arena": "Arena"}
FIRMENFARBE = {
    "Anthropic": "--ki-anthropic",
    "OpenAI": "--ki-openai",
    "Google": "--ki-google",
    "Meta": "--ki-meta",
    "xAI": "--ki-xai",
    "Alibaba": "--ki-alibaba",
    "DeepSeek": "--ki-deepseek",
    "Mistral": "--ki-mistral",
}
_EINSTELLUNG = re.compile(r"\s*\([^)]*\)$")


def katalog(root: Path) -> list[dict]:
    """Die Modelle der Tabelle von Hand; ohne Datei keines."""
    pfad = Path(root) / KATALOG
    if not pfad.exists():
        return []
    return yaml.safe_load(pfad.read_text(encoding="utf-8")).get("modelle") or []


def grundname(aa_name: str) -> str:
    """„Claude Opus 5.5 (max with fallback)“ → „Claude Opus 5.5“."""
    return _EINSTELLUNG.sub("", aa_name).strip()


def _mittlere_plaetze(werte: list[float]) -> list[float]:
    """Platz je Wert, höchster zuerst; Gleichstand teilt sich den mittleren Platz."""
    return [
        sum(w > v for w in werte) + (sum(w == v for w in werte) + 1) / 2 for v in werte
    ]


def rangliste(modelle: list[dict], aa: list[dict], arena: list[dict]) -> list[dict]:
    """Die besten ``TOP`` Modelle, die in beiden Listen stehen."""
    index: dict[str, float] = {}
    for zeile in aa:
        name = grundname(zeile["name"])
        index[name] = max(index.get(name, zeile["index"]), zeile["index"])
    platz_arena: dict[str, int] = {}
    for zeile in arena:
        platz_arena.setdefault(zeile["name"], zeile["platz"])
    gemeinsam = []
    for m in modelle:
        werte = [index[n] for n in m["aa"] if n in index]
        plaetze = [platz_arena[n] for n in m["arena"] if n in platz_arena]
        if werte and plaetze:
            gemeinsam.append((m, max(werte), min(plaetze)))
    aa_plaetze = _mittlere_plaetze([wert for _, wert, _ in gemeinsam])
    arena_reihe = sorted(roh for _, _, roh in gemeinsam)
    eintraege = [
        {
            "name": m["name"],
            "kurz": m.get("kurz") or m["name"],
            "firma": m["firma"],
            "farbe": FIRMENFARBE.get(m["firma"], "--ink-3"),
            "aa_index": wert,
            "aa_platz": aa_platz,
            "arena_platz": arena_reihe.index(roh) + 1,
            "mittel": (aa_platz + arena_reihe.index(roh) + 1) / 2,
        }
        for (m, wert, roh), aa_platz in zip(gemeinsam, aa_plaetze, strict=True)
    ]
    eintraege.sort(key=lambda e: (e["mittel"], -e["aa_index"], e["arena_platz"]))
    return [dict(e, platz=i) for i, e in enumerate(eintraege[:TOP], start=1)]


def lade(state_dir: Path) -> dict:
    """Der Store; fehlt er, ist nichts abgerufen. Einziger Einstieg für report/."""
    pfad = Path(state_dir) / STORE_NAME
    leer: dict = {"stand": None, "top": [], "quellen": {}}
    if not pfad.exists():
        return leer
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("%s unlesbar: %s", pfad, exc)
        return dict(leer, error=f"{STORE_NAME} unlesbar")


def aktualisiere(
    state_dir: Path, modelle: list[dict], abruf: dict[str, dict], heute: date
) -> dict:
    """Neue Rangliste, wenn beide Listen kamen; sonst bleibt der letzte Stand."""
    alt = lade(state_dir)
    tag = heute.isoformat()
    quellen = {}
    for name, ergebnis in abruf.items():
        vorher = (alt.get("quellen") or {}).get(name) or {}
        quellen[name] = {
            "url": ergebnis["url"],
            "error": ergebnis.get("error"),
            "versucht": tag,
            "abgerufen": vorher.get("abgerufen") if "error" in ergebnis else tag,
        }
    store = {"stand": alt.get("stand"), "top": alt.get("top") or [], "quellen": quellen}
    if not any("error" in e for e in abruf.values()):
        top = rangliste(modelle, abruf["aa"]["eintraege"], abruf["arena"]["eintraege"])
        if top:
            store.update(stand=tag, top=top)
        else:
            store["error"] = "keine Modelle in beiden Listen"
    pfad = Path(state_dir) / STORE_NAME
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    return store
