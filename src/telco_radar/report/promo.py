"""Anzeige-Vorbereitung fuer die Promo-Uebersicht (reine Datenaufbereitung,
kein LLM - analog zu report/differentiation.py's Rolle fuer die
Differenzierungs-Seite).

Die Frage der Seite ist eine einzige: **wer wirbt gerade womit?** Antonio am
07.08.2026: "Sinn ist ja, dass ich einen Ueberblick habe von meinen
Konkurrenten, welche Aktionen gerade laufen, was die machen, was sie fuer
Promos haben. Und ich moechte, dass sie da gut dargestellt sind, dass es
fuer mich kognitiv auch nicht so ein grosser Aufwand ist zu verstehen, worum
es in dieser Aktion geht."

Daraus folgt die Gliederung, und sie ist gegen die vorige getauscht:

    KARTEN     Je Wettbewerber GENAU EINE Karte - seine staerkste laufende
               Aktion, mit Kampagnenbild, Mechanik, Score und Frist. Gleiche
               Form, gleiche Felder, gleiche Reihenfolge fuer jede Marke.
               Vergleichen heisst Gleiches nebeneinander legen; eine Seite
               aus Aufmacher plus Beistellspalte plus Markenraster plus
               Ruhezone (so sah sie bis zum 07.08.2026 aus) zwingt den Leser,
               dreimal umzulernen.
    MECHANIKEN Was der Markt gerade FAEHRT, als Balken. Zwei Sekunden fuer
               die Lage: fuenf Marken werben mit Datenbonus, zwei mit
               Wechselpraemie.
    MARKEN     Alle uebrigen Aktionen, je Marke ein Block. Die Tiefe, nach
               der Uebersicht - nicht davor.

Sichtbarkeits-/Persistenzregel (siehe analyze/promo_store.py:mark_stale):
ein Angebot im Status "evtl. ausgelaufen" (= EINMAL nicht erneut bestaetigt)
bleibt sichtbar, nur gedaempft und markiert. Eine Karte soll nicht
verschwinden, weil eine einzelne Aktualisierung das Angebot nicht erneut
fand. Erst wer ZWEIMAL in Folge fehlt, gilt als beendet und faellt in die
Fussnote.

Marken ohne bestaetigte Aktion erscheinen weiterhin - als Zeile, nicht als
leerer Kasten. Sie belegen, dass hingesehen wurde; genau dafuer stehen sie
auf der Seite (Luecken zeigen statt verstecken).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..analyze.promo_ranker import MECHANICS

TIER_LABEL = {1: "Netzbetreiber", 2: "Discount- und Zweitmarke"}
TIER_COLOR = {1: "#3860be", 2: "#e07a00"}
_OWN_COLOR = "#e60000"
_RETIRED_STATUS = "ausgelaufen"
_SICHTBAR = ("aktiv", "evtl. ausgelaufen")


def _initials(name: str) -> str:
    words = [w for w in (name or "").replace("/", " ").split() if w[:1].isalnum()]
    letters = "".join(w[0] for w in words[:2]).upper()
    return letters or "?"


def _sortierschluessel(offer: dict) -> tuple:
    """Bestes Angebot zuerst: bestaetigt vor Kulanzfrist, dann Score, dann
    zuletzt gesehen. Ein Angebot ohne Score sortiert hinter jedes mit."""
    return (offer.get("status") == "aktiv",
            offer.get("score") is not None,
            offer.get("score") or 0,
            offer.get("last_verified") or "")


def _karte(brand: dict, offer: dict) -> dict:
    """Ein Angebot als Anzeigeeinheit - genau die Felder, die eine Karte
    zeigt. Die Vorlage rechnet nichts mehr aus."""
    return {
        "brand": brand,
        "offer": offer,
        "score": offer.get("score"),
        "highlight": bool(offer.get("highlight")),
        "reason": offer.get("score_reason") or "",
        "mechanic": MECHANICS.get(offer.get("mechanic") or "", ""),
        "bild": f"images/{offer['image']}" if offer.get("image") else "",
        "bild_w": offer.get("image_w"),
        "bild_h": offer.get("image_h"),
        # "motiv" = das Buehnenbild der Aktionsseite, nicht das Bild GENAU
        # dieses Angebots (siehe promo_bilder.zuordnen). Die Karte schreibt
        # das dazu, statt eine Verbindung zu behaupten, die nicht belegt ist.
        "bild_ist_motiv": offer.get("image_kind") == "motiv",
    }


def _mechanik_balken(karten: list[dict], marken: list[dict]) -> list[dict]:
    """Welche Mechanik faehrt der Markt gerade - und bei wie vielen Marken?

    Gezaehlt werden ALLE sichtbaren Wettbewerberangebote, nicht nur die
    Karten oben: die Frage ist die Marktlage, nicht die Auswahl der Seite.
    Die Marken-Zahl steht daneben, weil sie die eigentliche Aussage traegt -
    sechs Angebote derselben Marke sind eine Kampagne, sechs Angebote
    sechs verschiedener Marken sind ein Trend.
    """
    zaehler: dict[str, dict] = {}
    for b in marken:
        if b["internal_reference"]:
            continue
        for offer in b["active"]:
            key = offer.get("mechanic") or ""
            label = MECHANICS.get(key, "")
            if not label or key == "sonstiges":
                continue
            eintrag = zaehler.setdefault(key, {"key": key, "label": label,
                                               "n": 0, "marken": set()})
            eintrag["n"] += 1
            eintrag["marken"].add(b["name"])
    balken = sorted(zaehler.values(),
                    key=lambda z: (len(z["marken"]), z["n"]), reverse=True)
    hoechste = max((len(z["marken"]) for z in balken), default=0)
    return [{"key": z["key"], "label": z["label"], "n": z["n"],
             "marken": len(z["marken"]),
             "w": round(100 * len(z["marken"]) / hoechste) if hoechste else 0}
            for z in balken]


def prepare_promo_view(db_entries: list[dict], sources: list,
                       latest_date: str) -> dict:
    """Baut die Anzeigedaten der Promo-Uebersicht aus den PromoDB-Eintraegen.

    "neu" = seit weniger als 10 Tagen zum ersten Mal gesehen, gleiche Regel
    wie bei Differenzierung. Vodafone selbst (internal_reference=True) wird
    angezeigt, aber nicht in active_total/brands_active/brands_tracked
    mitgezaehlt - das sind Wettbewerbskennzahlen.

    Bilder kommen aus dem Eintrag selbst (`image`/`image_w`/`image_h`, von
    promo_bilder.py je ANGEBOT beschafft). Bis zum 07.08.2026 kam hier ein
    Bild je MARKE an - ein Screenshot ihrer Aktionsseite -, und die Karte
    zeigte fuer jedes ihrer acht Angebote dasselbe Bild. Das Bild gehoert
    zum Angebot, nicht zum Absender.
    """
    try:
        cutoff = (datetime.fromisoformat(latest_date) - timedelta(days=10)).date().isoformat()
    except ValueError:
        cutoff = ""

    by_brand_raw: dict[str, list[dict]] = {}
    for raw in db_entries:
        e = dict(raw)
        e["neu"] = bool((e.get("first_seen") or "") > cutoff)
        e["fading"] = e.get("status") == "evtl. ausgelaufen"
        by_brand_raw.setdefault(e.get("brand") or "", []).append(e)

    # Nur tatsaechlich gecrawlte Quellen (kind: static/js) werden gezeigt -
    # dokumentierte Sonderfaelle (kind: skip, z. B. Deutsche Glasfaser) haben
    # keinen Snapshot-Versuch und saehen faelschlich wie eine geprueft-leere
    # Marke aus. Sie stehen auf der Quellen-Unterseite.
    crawlable = [s for s in sources if getattr(s, "crawlable", True)]

    marken: list[dict] = []
    active_total = 0
    brands_active = 0
    for src in crawlable:
        eintraege = by_brand_raw.get(src.name, [])
        sichtbar = sorted((e for e in eintraege if e.get("status") in _SICHTBAR),
                          key=_sortierschluessel, reverse=True)
        bestaetigt = [e for e in sichtbar if e.get("status") == "aktiv"]
        beendet = [e for e in eintraege if e.get("status") == _RETIRED_STATUS]

        if not src.internal_reference and bestaetigt:
            active_total += len(bestaetigt)
            brands_active += 1

        marken.append({
            "name": src.name, "tier": src.tier,
            "tier_label": TIER_LABEL.get(src.tier, ""),
            "color": _OWN_COLOR if src.internal_reference else TIER_COLOR.get(src.tier, "#3860be"),
            "group": src.group, "url": src.url,
            "internal_reference": src.internal_reference,
            "initials": _initials(src.name),
            "active": sichtbar, "stale": beendet,
            "active_count": len(bestaetigt),
            "has_offers": bool(sichtbar),
        })

    # Wettbewerber mit sichtbarem Angebot zuerst, dann nach Tier/Name;
    # Vodafones eigene Referenzkarte immer als letzte.
    marken.sort(key=lambda b: (b["internal_reference"], not b["has_offers"],
                               b["tier"], b["name"]))

    # ------------------------------------------------------------ Karten
    # Eine Karte je Marke: ihre staerkste sichtbare Aktion. Diese Regel ist
    # keine Kosmetik, sondern die Lehre aus den echten Daten: gemessen am
    # Bestand vom 27.07.2026 lagen 36 Angebote ueber der Schwelle, aber
    # allein neun der besten fuenfzehn kamen von der Telekom - praktisch
    # dieselbe Geraeteaktion, einmal je Modell. Eine Uebersicht soll die
    # Marktbreite zeigen, nicht den Anbieter mit dem groessten
    # Geraetekatalog. Die uebrigen Aktionen verschwinden nicht, sie stehen
    # unten bei ihrer Marke.
    karten: list[dict] = []
    for b in marken:
        if b["internal_reference"] or not b["active"]:
            continue
        karten.append(_karte(b, b["active"][0]))
    # Bewertete zuerst, darunter nach Score - und bei gleichem Score die
    # Marke mit Bild vor der ohne. Nicht aus Kosmetik: eine Karte ohne Bild
    # ist eine halbe Karte, und oben stehen die, die am meisten tragen.
    karten.sort(key=lambda k: (k["highlight"], k["score"] is not None,
                               k["score"] or 0, bool(k["bild"])), reverse=True)

    eigen = None
    eigene_marke = next((b for b in marken if b["internal_reference"]), None)
    if eigene_marke and eigene_marke["active"]:
        eigen = _karte(eigene_marke, eigene_marke["active"][0])

    # Die Bloecke unten zeigen jede Marke mit ihren uebrigen Aktionen - was
    # oben schon als Karte steht, steht dort nicht noch einmal.
    oben = {k["offer"].get("id") for k in karten}
    if eigen:
        oben.add(eigen["offer"].get("id"))
    for b in marken:
        b["rest"] = [e for e in b["active"] if e.get("id") not in oben]

    mit_aktion = [b for b in marken if b["has_offers"]]
    ohne_aktion = [b for b in marken if not b["has_offers"]]

    return {
        # Alle beobachteten Marken in Anzeigereihenfolge - die Grundlage,
        # gegen die die Wahrheitstests rechnen. Die Seite zeigt sie in zwei
        # Gruppen, weil "hier laeuft gerade nichts" eine Zeile ist und keine
        # Kachel; die Zaehlung darf davon nicht abhaengen.
        "brands": marken,
        "marken": mit_aktion,
        "ohne_aktion": ohne_aktion,
        "karten": karten,
        "eigen": eigen,
        "mechaniken": _mechanik_balken(karten, marken),
        # Wie viele der Karten ein echtes Kampagnenbild tragen. Die Zahl
        # haengt am Abnahmekriterium der Seite (scripts/pruefe_portal.py)
        # und wird in tests/test_promo_seite.py gegen die Daten gehalten.
        "mit_bild": sum(1 for k in karten if k["bild"]),
        "bilder_gesamt": sum(1 for b in marken for e in b["active"] if e.get("image")),
        "highlight_count": sum(1 for k in karten if k["highlight"]),
        "scored_total": sum(1 for b in marken if not b["internal_reference"]
                            for e in b["active"] if e.get("score") is not None),
        "active_total": active_total,
        "brands_active": brands_active,
        "brands_tracked": len([s for s in crawlable if not s.internal_reference]),
    }
