"""Anzeige-Vorbereitung fuer die Promo-Uebersicht (reine Datenaufbereitung,
kein LLM - analog zu report/differentiation.py's Rolle fuer die
Differenzierungs-Seite).

Die Seite soll auf einen Blick zeigen, welche Aktion gerade bei welchem
Wettbewerber laeuft (siehe claude/promo-uebersicht-konzept.md) - deshalb ist
die Marke hier die primaere Gruppierung, nicht der Tier. prepare_promo_view()
baut pro beobachteter Marke eine Karte mit ihren aktiven Angeboten; Marken
ohne aktuell bestaetigtes Angebot erscheinen trotzdem (leer/gedaempft), damit
die Seite die tatsaechliche Beobachtungsabdeckung zeigt, statt Luecken zu
verstecken.

Sichtbarkeits-/Persistenzregel (siehe analyze/promo_store.py:mark_stale):
ein Angebot, das im PromoDB-Status "evtl. ausgelaufen" ist (= EINMAL nicht
erneut bestaetigt), bleibt hier trotzdem in der normalen Angebotsliste
sichtbar - nur gedaempft und mit einem kleinen Hinweis-Tag markiert. Eine
Karte soll nicht verschwinden, nur weil eine einzelne Aktualisierung das
Angebot nicht erneut fand (unzuverlaessige LLM-Extraktion, leicht andere
Formulierung o.ae.). Erst wer ZWEIMAL in Folge nicht erneut bestaetigt wurde
(Status "ausgelaufen") gilt als wirklich beendet und faellt aus der
Angebotsliste in die knappe Fussnote."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..analyze.promo_ranker import MECHANICS

TIER_LABEL = {1: "Netzbetreiber", 2: "Discount- und Zweitmarke"}
TIER_COLOR = {1: "#3860be", 2: "#e07a00"}
_OWN_COLOR = "#e60000"
_RETIRED_STATUS = "ausgelaufen"


def _initials(name: str) -> str:
    words = [w for w in (name or "").replace("/", " ").split() if w[:1].isalnum()]
    letters = "".join(w[0] for w in words[:2]).upper()
    return letters or "?"


# Anzeigebremse, kein Auswahlkriterium: die Auswahl trifft allein die
# Score-Schwelle in analyze/promo_ranker.py. Diese Kappung greift nur, falls
# eine aussergewoehnlich bewegte Woche zweistellig viele Highlights
# produziert - dann waere die Sektion wieder eine Liste statt eines
# Ueberblicks. Wird gekappt, sagt die Seite das offen (siehe Template).
_MAX_HIGHLIGHTS = 9


def _rank_highlights(competitor_brands: list[dict]) -> tuple[list[dict], int]:
    """Hoechstens EIN Highlight je Marke, absteigend nach Score, plus die
    Zahl der uebrigen Angebote ueber der Schwelle.

    Die Ein-je-Marke-Regel ist keine Kosmetik, sondern die Lehre aus den
    echten Daten: gemessen am Bestand vom 27.07.2026 lagen 36 Angebote ueber
    der Schwelle, aber allein neun der besten fuenfzehn kamen von der
    Telekom - praktisch dieselbe Geraeteaktion, einmal je Modell. Eine
    Highlight-Sektion soll die Marktbreite zeigen, nicht den Anbieter mit dem
    groessten Geraetekatalog. Die uebrigen Treffer verschwinden nicht: sie
    stehen unten bei ihrer Marke, dort mit demselben Score als kleiner Punkt
    markiert.

    Ein Angebot ohne Score kann hier nie auftauchen - promo_ranker setzt das
    Flag ausschliesslich zusammen mit einer Zahl."""
    best: dict[str, dict] = {}
    total = 0
    for b in competitor_brands:
        for offer in b["active"]:
            if not (offer.get("highlight") and offer.get("score") is not None):
                continue
            total += 1
            item = {
                "brand": b, "offer": offer, "score": int(offer["score"]),
                "reason": offer.get("score_reason") or "",
                "mechanic": MECHANICS.get(offer.get("mechanic") or "", ""),
            }
            current = best.get(b["name"])
            if current is None or item["score"] > current["score"]:
                best[b["name"]] = item
    items = sorted(best.values(),
                   key=lambda i: (i["score"], i["offer"].get("first_seen") or "",
                                  i["brand"]["name"]), reverse=True)
    return items, total


def prepare_promo_view(db_entries: list[dict], sources: list, latest_date: str,
                       images: dict[str, str] | None = None) -> dict:
    """Gruppiert PromoDB-Eintraege nach Marke fuer die Wettbewerber-Board-
    Ansicht. "neu" = seit weniger als 10 Tagen zum ersten Mal gesehen, gleiche
    Regel wie bei Differenzierung. Vodafone selbst (internal_reference=True)
    wird angezeigt, aber nicht in active_total/brands_active/brands_tracked
    mitgezaehlt - das sind Wettbewerbskennzahlen.

    *images* ist eine optionale Zuordnung Markenname -> site-relativer
    Bildpfad (z. B. "images/congstar.jpg"), von report/html.py aus dem
    Playwright-Screenshot-Cache (data/state/promo_images/, siehe
    promo_images.py) gebaut. Ein echter Screenshot hat Vorrang vor dem
    per-Eintrag og:image/twitter:image-Fund (meist nur ein generisches
    Marken-Logo, siehe collect/promo_snapshot.py) - dieser bleibt nur als
    zweite Absicherung, falls fuer eine Marke (noch) kein Screenshot
    vorliegt. Fehlt beides, faellt die Karte auf die Farbverlauf+Initialen-
    Kachel zurueck (siehe promo_index.html.j2)."""
    images = images or {}
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
        # "aktiv" (bestaetigt) und "evtl. ausgelaufen" (einmal nicht erneut
        # bestaetigt, Kulanzfrist) bleiben BEIDE in der sichtbaren Liste -
        # nur wirklich "ausgelaufen" (zweimal in Folge nicht bestaetigt)
        # verschwindet in die Fussnote. Siehe Modul-Docstring.
        confirmed = [e for e in entries if e.get("status") == "aktiv"]
        grace = [e for e in entries if e.get("status") == "evtl. ausgelaufen"]
        for e in grace:
            e["fading"] = True
        visible = confirmed + grace
        retired = [e for e in entries if e.get("status") == _RETIRED_STATUS]
        image_url = images.get(src.name) or next(
            (e.get("image_url") for e in entries if e.get("image_url")), None)

        if not src.internal_reference and confirmed:
            active_total += len(confirmed)
            brands_active += 1

        brands.append({
            "name": src.name, "tier": src.tier,
            "tier_label": TIER_LABEL.get(src.tier, ""),
            "color": _OWN_COLOR if src.internal_reference else TIER_COLOR.get(src.tier, "#3860be"),
            "group": src.group, "internal_reference": src.internal_reference,
            "initials": _initials(src.name), "image_url": image_url,
            "active": visible, "stale": retired, "active_count": len(confirmed),
            "has_offers": bool(visible),
        })

    # Wettbewerber mit sichtbarem Angebot zuerst (bestaetigt oder in der
    # Kulanzfrist), dann nach Tier/Name; Vodafones eigene Referenzkarte immer
    # als letzte (siehe internal_reference). Bewusst has_offers statt
    # active_count==0, damit eine Marke mit nur einem Kulanzfrist-Angebot
    # nicht faelschlich wie eine unbeobachtete Marke ans Ende rutscht.
    brands.sort(key=lambda b: (b["internal_reference"], not b["has_offers"],
                                b["tier"], b["name"]))

    own_brand = next((b for b in brands if b["internal_reference"]), None)

    # ---------------------------------------------------------- Highlights
    # "Was ist gerade am wichtigsten?" - die Auswahl trifft NICHT diese
    # Anzeigefunktion, sondern der Wichtigkeits-Score aus
    # analyze/promo_ranker.py: dort wird pro Angebot ein Score 0-100 auf
    # einer festen Skala gebildet und mit Hysterese ein "highlight"-Flag
    # gesetzt (rein ab Schwelle, raus erst deutlich darunter). Hier wird nur
    # noch gelesen und sortiert. Dadurch ist die ANZAHL der Highlights
    # bewusst dynamisch: in einer ruhigen Woche stehen oben vielleicht zwei
    # Angebote, in einer bewegten zehn - statt per Perzentil kuenstlich
    # konstant gehalten zu werden.
    ranked, flagged_total = _rank_highlights(
        [b for b in brands if not b["internal_reference"]])
    highlights = ranked[:_MAX_HIGHLIGHTS]

    # Vodafone als Vergleichsanker: das eigene bestbewertete sichtbare
    # Angebot, unabhaengig von der Highlight-Schwelle. Es steht bewusst
    # NICHT in der Wettbewerbsrangfolge (sonst wuerde die eigene Marke die
    # Wettbewerbsbeobachtung mitgestalten), sondern daneben - damit man
    # Druck und eigene Antwort nebeneinander sieht.
    own_anchor = None
    if own_brand and own_brand["active"]:
        best = sorted(own_brand["active"],
                      key=lambda e: (e.get("score") is not None, e.get("score") or 0),
                      reverse=True)[0]
        own_anchor = {
            "brand": own_brand, "offer": best, "score": best.get("score"),
            "reason": best.get("score_reason") or "",
            "mechanic": MECHANICS.get(best.get("mechanic") or "", ""),
        }

    # Featured/Hero-Karte: das wichtigste Wettbewerberangebot, sobald
    # Bewertungen vorliegen. Ohne Scores (erster Lauf nach dem Deploy, oder
    # LLM-Ausfall) faellt die Karte auf das bisherige Verhalten zurueck -
    # Vodafones eigenes Top-Angebot, sonst der erste Wettbewerber mit einem
    # sichtbaren Angebot. Nie leer, nie faelschlich beschriftet: das Label
    # nutzt immer den echten Markennamen.
    if highlights:
        hero = highlights[0]
    elif own_brand and own_brand["active"]:
        hero = {"brand": own_brand, "offer": own_brand["active"][0]}
    else:
        fallback = next((b for b in brands if not b["internal_reference"] and b["active"]), None)
        hero = {"brand": fallback, "offer": fallback["active"][0]} if fallback else None

    # Die Wettbewerber-Kachel-Reihe zeigt nie die im Hero gezeigte Marke ein
    # zweites Mal (i.d.R. ohnehin Vodafone selbst, siehe internal_reference-
    # Filter unten - der Ausschluss per Namen greift nur im Ausnahmefall,
    # in dem der Fallback-Wettbewerber oben als Hero einspringt).
    hero_name = hero["brand"]["name"] if hero else None
    grid_brands = [b for b in brands
                   if not b["internal_reference"] and b["name"] != hero_name]

    return {
        "brands": brands,
        "grid_brands": grid_brands,
        "hero": hero,
        "highlights": highlights,
        "highlight_rest": highlights[1:],
        "highlight_count": len(highlights),
        # Alle uebrigen Angebote ueber der Schwelle, die oben NICHT gezeigt
        # werden - weitere Treffer derselben Marke plus alles jenseits der
        # Kappung. Die Seite sagt das offen, statt still zu kuerzen.
        "highlight_dropped": max(0, flagged_total - len(highlights)),
        "own_anchor": own_anchor,
        "scored_total": sum(1 for b in brands if not b["internal_reference"]
                            for e in b["active"] if e.get("score") is not None),
        "active_total": active_total,
        "brands_active": brands_active,
        "brands_tracked": len([s for s in crawlable if not s.internal_reference]),
    }
