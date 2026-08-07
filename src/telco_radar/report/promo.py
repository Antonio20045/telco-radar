"""Anzeige-Vorbereitung fuer die Promo-Uebersicht (reine Datenaufbereitung,
kein LLM - analog zu report/differentiation.py's Rolle fuer die
Differenzierungs-Seite).

Die Frage der Seite ist eine einzige: **wer wirbt gerade womit?** Antonio am
07.08.2026: "Sinn ist ja, dass ich einen Ueberblick habe von meinen
Konkurrenten, welche Aktionen gerade laufen, was die machen, was sie fuer
Promos haben."

Dritter Anlauf, 08.08.2026. Der zweite hatte die Karten eingefuehrt - je
Wettbewerber EINE, seine staerkste - und alles Weitere darunter als
Zeilenwand nach Anbieter. Damit standen wieder ZWEI Darstellungen derselben
Sache auf der Seite, und wer eine Marke verstehen wollte, musste zwischen
ihnen springen. Antonio: "Total unuebersichtlich, nicht zugaenglich, nicht
schoen. Ich will wissen, welche Promo-Aktionen bei meinen Wettbewerbern
laufen."

Der Leser denkt in Wettbewerbern. Also gliedert die Seite nach Marken, und
je Marke stehen ALLE ihre Aktionen in EINEM Raster:

    LAGE      Welche Mechanik faehrt der Markt gerade, als Balken. Zwei
              Sekunden fuer die Marktlage, mehr soll es nicht sein.
    BLOECKE   Je Marke ein Block: Rubrikleiste mit Markenname, darunter die
              staerkste Aktion als grosse Karte und die uebrigen als
              kleinere Karten derselben Form. Kein "oben die Auswahl, unten
              der Rest" mehr - jede Aktion steht genau einmal, bei ihrer
              Marke.
    EIGEN     Vodafone am Ende, als Vergleichsanker markiert.

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

import re
from datetime import datetime, timedelta

from ..analyze.promo_ranker import MECHANICS

TIER_LABEL = {1: "Netzbetreiber", 2: "Discount- und Zweitmarke"}
TIER_COLOR = {1: "#3860be", 2: "#e07a00"}
_OWN_COLOR = "#e60000"
_RETIRED_STATUS = "ausgelaufen"
_SICHTBAR = ("aktiv", "evtl. ausgelaufen")

# Die harte Aussage eines Angebots: Preis, Datenmenge, Bandbreite, Rabatt.
# Genau das gehoert auf eine Schriftkachel - "20 GB fuer 6,99 €" sagt in
# zwei Zahlen, worum es geht. Bis zum 08.08.2026 stand dort die MECHANIK
# ("Wechsel- oder Altgeraetpraemie"), und weil vier Marken dieselbe fahren,
# standen vier identische Kacheln nebeneinander - das liest sich als Fehler,
# nicht als Gestaltung.
_ZAHL_RE = re.compile(
    r"\d[\d.,]*\s?(?:€|EUR|%|GB|TB|MBit/s|Mbit/s|MB/s|MB|Cent)", re.I)
# Wo eine Ueberschrift ihren ersten Sinnabschnitt beendet. Nur zum
# ABTRENNEN, nie zum Abschneiden mitten im Wort - die Kachel traegt kein
# "…" (CLAUDE.md §5: keine gekuerzten Ueberschriften).
_KLAUSEL_RE = re.compile(r"\s*[:–—(]\s*|,\s+")
# Wo der Kern einer Ueberschrift endet und ihre Naeherbestimmung beginnt:
# "Junge-Leute-Rabatt AUF Magenta Mobil Young 5G Tarife". Erst hier, nach
# der Zeichensetzung - eine Praeposition ist die schwaechere Grenze.
_NAEHER_RE = re.compile(r"\s+(?:auf|für|fuer|mit|bei|ohne|zum|zur|im|in|von)\s+")
# Laenger gesetzt wirkt eine Kachel nicht mehr wie ein Motiv, sondern wie
# ein zweiter Absatz.
_KACHEL_MAX = 34


def _initials(name: str) -> str:
    words = [w for w in (name or "").replace("/", " ").split() if w[:1].isalnum()]
    letters = "".join(w[0] for w in words[:2]).upper()
    return letters or "?"


def _kachel_text(offer: dict, mechanik: str) -> str:
    """Was auf der Schriftkachel gross steht, wenn es kein Bild gibt.

    Drei Stufen, konkret vor generisch: die Zahlen der Ueberschrift ("20 GB
    · 6,99 €"), sonst ihr erster Sinnabschnitt, sonst die Mechanik. Die
    Mechanik ist ausdruecklich die LETZTE Wahl - sie beschreibt eine
    Angebotsart und unterscheidet zwei Marken nicht.
    """
    headline = " ".join((offer.get("headline") or "").split())
    zahlen: list[str] = []
    for m in _ZAHL_RE.finditer(headline):
        wert = " ".join(m.group(0).split())
        if wert not in zahlen:
            zahlen.append(wert)
        if len(zahlen) == 2:
            break
    if zahlen:
        return " · ".join(zahlen)
    erster = _KLAUSEL_RE.split(headline)[0].strip()
    if len(erster) > _KACHEL_MAX:
        erster = _NAEHER_RE.split(erster)[0].strip()
    # Die ganze Ueberschrift taugt nicht als Kachel: sie steht zwei Zeilen
    # tiefer noch einmal, und dieselbe Aussage zweimal untereinander liest
    # sich als Panne. Ein AUSSCHNITT ist etwas anderes - er hebt hervor.
    if erster and erster != headline and len(erster) <= _KACHEL_MAX:
        return erster
    return mechanik or "Aktion"


# Ab diesem Seitenverhaeltnis ist ein Bild ein Banner und kein Motiv. 2,2
# liegt bewusst ueber 16:9 (1,78) und unter dem flachsten echten Foto im
# Bestand vom 08.08.2026 (800x419 = 1,91): beschnitten wuerden sonst auch
# gewoehnliche Querformate.
_PANORAMA_AB = 2.2


def _ist_panorama(breite, hoehe) -> bool:
    return bool(breite and hoehe and breite / hoehe > _PANORAMA_AB)


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
    mechanik = MECHANICS.get(offer.get("mechanic") or "", "")
    return {
        "brand": brand,
        "offer": offer,
        "score": offer.get("score"),
        "highlight": bool(offer.get("highlight")),
        "reason": offer.get("score_reason") or "",
        "mechanic": mechanik,
        "kachel": _kachel_text(offer, mechanik),
        "frist": offer.get("valid_until") or "",
        "bild": f"images/{offer['image']}" if offer.get("image") else "",
        "bild_w": offer.get("image_w"),
        "bild_h": offer.get("image_h"),
        # Ein Werbebanner ist kein Bildausschnitt. Ein 1280x410-Motiv im
        # 16:9-Kasten formatfuellend zu beschneiden schneidet genau die
        # Haelfte weg, in der die Aussage steht - bei simplytel blieb blaue
        # Flaeche uebrig und die FRITZ!Box stand am Rand. Solche Formate
        # werden deshalb vollstaendig gezeigt, nicht beschnitten.
        "bild_panorama": _ist_panorama(offer.get("image_w"), offer.get("image_h")),
        # "motiv" = das Buehnenbild der Aktionsseite, nicht das Bild GENAU
        # dieses Angebots (siehe promo_bilder.zuordnen). Die Karte schreibt
        # das dazu, statt eine Verbindung zu behaupten, die nicht belegt ist.
        "bild_ist_motiv": offer.get("image_kind") == "motiv",
    }


def _mechanik_balken(marken: list[dict]) -> list[dict]:
    """Welche Mechanik faehrt der Markt gerade - und bei wie vielen Marken?

    Gezaehlt werden ALLE sichtbaren Wettbewerberangebote. Die Marken-Zahl
    steht daneben, weil sie die eigentliche Aussage traegt - sechs Angebote
    derselben Marke sind eine Kampagne, sechs Angebote sechs verschiedener
    Marken sind ein Trend.
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


def _block(brand: dict) -> dict:
    """Eine Marke mit allen ihren sichtbaren Aktionen als Kartenblock.

    `lead` ist die staerkste (grosse Karte), `weitere` sind die uebrigen in
    derselben Form. Getrennt gefuehrt, weil die Vorlage sie verschieden
    GEWICHTET - nicht, weil sie an zwei Orten stehen. Genau diese Trennung
    war bis zum 08.08.2026 eine Trennung im Seitenaufbau, und das war der
    Fehler.
    """
    karten = [_karte(brand, o) for o in brand["active"]]
    return dict(brand, lead=karten[0] if karten else None,
                weitere=karten[1:], karten=karten,
                top_score=karten[0]["score"] if karten else None)


def _entdoppele_bilder(karten: list[dict]) -> None:
    """Jedes Motiv steht hoechstens EINMAL auf der Seite.

    promo_bilder.zuordnen() vergibt jeden Bildkandidaten schon nur einmal -
    aber je Marke und je Lauf. Ein Eintrag, dessen Seite in diesem Lauf
    unveraendert blieb, behaelt sein Bild aus einem frueheren; taucht
    derselbe Kandidat jetzt bei einem anderen Angebot auf, steht dasselbe
    Motiv zweimal. Genau so passiert am 08.08.2026 bei O2, zweimal derselbe
    Router unter zwei verschiedenen Schlagzeilen - das liest sich als Fehler.
    Die spaetere (also schwaechere) Karte verliert es und wird eine
    Textkarte; ein Bild wegzulassen ist ehrlicher, als eins zu wiederholen.
    """
    gesehen: set[str] = set()
    for k in karten:
        if not k["bild"]:
            continue
        if k["bild"] in gesehen:
            k["bild"] = ""
            k["bild_w"] = k["bild_h"] = None
            k["bild_ist_motiv"] = False
            continue
        gesehen.add(k["bild"])


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

    # ----------------------------------------------------------- Bloecke
    # Je Marke ein Block, staerkste Marke zuerst. Sortiert wird ueber den
    # Score ihrer besten Aktion - eine Marke ohne bewertete Aktion faellt
    # hinter jede bewertete, verschwindet aber nicht (vor dem ersten
    # Bewertungslauf und bei LLM-Ausfall ist das der Normalfall).
    bloecke = [_block(b) for b in marken
               if b["has_offers"] and not b["internal_reference"]]
    bloecke.sort(key=lambda b: (b["top_score"] is not None, b["top_score"] or 0),
                 reverse=True)

    eigene_marke = next((b for b in marken
                         if b["internal_reference"] and b["has_offers"]), None)
    eigen = _block(eigene_marke) if eigene_marke else None

    # Alle Wettbewerberkarten in Seitenreihenfolge - die Grundlage, gegen die
    # die Wahrheitstests rechnen ("jede sichtbare Aktion genau einmal").
    karten = [k for b in bloecke for k in b["karten"]]
    alle_karten = karten + (eigen["karten"] if eigen else [])
    _entdoppele_bilder(alle_karten)

    ohne_aktion = [b for b in marken if not b["has_offers"]]

    return {
        # Alle beobachteten Marken in Anzeigereihenfolge - die Grundlage,
        # gegen die die Wahrheitstests rechnen. Die Seite zeigt sie in zwei
        # Gruppen, weil "hier laeuft gerade nichts" eine Zeile ist und keine
        # Kachel; die Zaehlung darf davon nicht abhaengen.
        "brands": marken,
        "bloecke": bloecke,
        "ohne_aktion": ohne_aktion,
        "karten": karten,
        "eigen": eigen,
        "mechaniken": _mechanik_balken(marken),
        # Wie viele der gezeigten Karten ein echtes Kampagnenbild tragen. Die
        # Zahl haengt am Abnahmekriterium der Seite (scripts/pruefe_portal.py)
        # und wird in tests/test_promo_seite.py gegen die Daten gehalten.
        "mit_bild": sum(1 for k in alle_karten if k["bild"]),
        "bilder_gesamt": sum(1 for b in marken for e in b["active"] if e.get("image")),
        "highlight_count": sum(1 for k in karten if k["highlight"]),
        "scored_total": sum(1 for b in marken if not b["internal_reference"]
                            for e in b["active"] if e.get("score") is not None),
        "active_total": active_total,
        "brands_active": brands_active,
        "brands_tracked": len([s for s in crawlable if not s.internal_reference]),
    }
