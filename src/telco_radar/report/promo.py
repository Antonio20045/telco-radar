"""Anzeige-Vorbereitung fuer die Promo-Uebersicht (reine Datenaufbereitung,
kein LLM - analog zu report/differentiation.py's Rolle fuer die
Differenzierungs-Seite).

Die Seite soll auf einen Blick zeigen, welche Aktion gerade bei welchem
Wettbewerber laeuft (siehe claude/promo-uebersicht-konzept.md) - deshalb ist
die Marke hier die primaere Gruppierung, nicht der Tier. prepare_promo_view()
baut pro beobachteter Marke eine Karte mit ihren aktiven Angeboten; Marken
ohne aktuell bestaetigtes Angebot erscheinen trotzdem (leer/gedaempft), damit
die Seite die tatsaechliche Beobachtungsabdeckung zeigt, statt Luecken zu
verstecken."""
from __future__ import annotations

from datetime import datetime, timedelta

TIER_LABEL = {1: "Netzbetreiber", 2: "Discount- und Zweitmarke",
              3: "Festnetz, Kabel, Glasfaser"}
TIER_COLOR = {1: "#3860be", 2: "#e07a00", 3: "#1a8f4c"}
_OWN_COLOR = "#e60000"


def _initials(name: str) -> str:
    words = [w for w in (name or "").replace("/", " ").split() if w[:1].isalnum()]
    letters = "".join(w[0] for w in words[:2]).upper()
    return letters or "?"


def prepare_promo_view(db_entries: list[dict], sources: list, latest_date: str) -> dict:
    """Gruppiert PromoDB-Eintraege nach Marke fuer die Wettbewerber-Board-
    Ansicht. "neu" = seit weniger als 10 Tagen zum ersten Mal gesehen, gleiche
    Regel wie bei Differenzierung. Vodafone selbst (internal_reference=True)
    wird angezeigt, aber nicht in active_total/brands_active/brands_tracked
    mitgezaehlt - das sind Wettbewerbskennzahlen."""
    try:
        cutoff = (datetime.fromisoformat(latest_date) - timedelta(days=10)).date().isoformat()
    except ValueError:
        cutoff = ""

    by_brand_raw: dict[str, list[dict]] = {}
    for raw in db_entries:
        e = dict(raw)
        e["neu"] = bool((e.get("first_seen") or "") > cutoff)
        by_brand_raw.setdefault(e.get("brand") or "", []).append(e)

    # Nur tatsaechlich gecrawlte Quellen (kind: static/js) werden als Karte
    # gezeigt - dokumentierte Sonderfaelle (kind: skip, z. B. Deutsche
    # Glasfaser) haben keinen Snapshot-Versuch und wuerden faelschlich wie
    # eine geprueft-leere Marke aussehen. Diese Faelle stehen bereits auf der
    # Quellen-Unterseite.
    crawlable = [s for s in sources if getattr(s, "crawlable", True)]

    brands = []
    active_total = 0
    brands_active = 0
    for src in crawlable:
        entries = by_brand_raw.get(src.name, [])
        entries = sorted(
            entries,
            key=lambda e: (e.get("status") == "aktiv", e.get("last_verified") or ""),
            reverse=True)
        active = [e for e in entries if e.get("status") == "aktiv"]
        stale = [e for e in entries if e.get("status") != "aktiv"]
        image_url = next((e.get("image_url") for e in entries if e.get("image_url")), None)

        if not src.internal_reference and active:
            active_total += len(active)
            brands_active += 1

        brands.append({
            "name": src.name, "tier": src.tier,
            "tier_label": TIER_LABEL.get(src.tier, ""),
            "color": _OWN_COLOR if src.internal_reference else TIER_COLOR.get(src.tier, "#3860be"),
            "group": src.group, "internal_reference": src.internal_reference,
            "initials": _initials(src.name), "image_url": image_url,
            "active": active, "stale": stale, "active_count": len(active),
        })

    # Wettbewerber mit laufender Aktion zuerst, dann nach Tier/Name; Vodafones
    # eigene Referenzkarte immer als letzte (siehe internal_reference).
    brands.sort(key=lambda b: (b["internal_reference"], b["active_count"] == 0,
                                b["tier"], b["name"]))

    return {
        "brands": brands,
        "active_total": active_total,
        "brands_active": brands_active,
        "brands_tracked": len([s for s in crawlable if not s.internal_reference]),
    }
