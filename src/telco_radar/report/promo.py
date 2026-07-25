"""Anzeige-Vorbereitung fuer die Promo-Uebersicht (reine Datenaufbereitung,
kein LLM - analog zu report/differentiation.py's Rolle fuer die
Differenzierungs-Seite)."""
from __future__ import annotations

from datetime import datetime, timedelta


def prepare_promo_view(db_entries: list[dict], sources: list, latest_date: str) -> dict:
    """Gruppiert PromoDB-Eintraege nach Tier fuer die Templates und markiert
    kuerzlich neu aufgenommene Eintraege ("neu"-Badge, wie bei
    Differenzierung: neu = seit weniger als 10 Tagen zum ersten Mal gesehen)."""
    by_tier: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    tier_by_brand = {s.name: s.tier for s in sources}
    try:
        cutoff = (datetime.fromisoformat(latest_date) - timedelta(days=10)).date().isoformat()
    except ValueError:
        cutoff = ""

    active_total = 0
    brands_active: set[str] = set()
    for raw in db_entries:
        e = dict(raw)
        e["neu"] = bool((e.get("first_seen") or "") > cutoff)
        tier = tier_by_brand.get(e.get("brand"), e.get("tier") or 2)
        by_tier.setdefault(tier, []).append(e)
        if e.get("status") == "aktiv":
            active_total += 1
            brands_active.add(e.get("brand"))
    for t in by_tier:
        by_tier[t].sort(
            key=lambda e: (e.get("status") == "aktiv", e.get("first_seen") or ""),
            reverse=True)

    return {
        "by_tier": by_tier,
        "active_total": active_total,
        "brands_active": len(brands_active),
        "brands_tracked": len(sources),
    }
