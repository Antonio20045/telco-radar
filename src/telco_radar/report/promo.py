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
from .suchindex import marken_anker
from ..analyze.promo_store import _same_offer

TIER_LABEL = {1: "Netzbetreiber", 2: "Discount- und Zweitmarke"}
TIER_COLOR = {1: "#3860be", 2: "#e07a00"}
# Wo eine Marke ohne gepflegten `rang` einsortiert wird: hinter jede
# gepflegte, dort nach Tier und Reichweite. Eine neu eingetragene Marke
# verschwindet damit nicht, sie draengelt sich nur nicht nach vorn.
RANG_UNGESETZT = 900
_OWN_COLOR = "#e60000"
_RETIRED_STATUS = "ausgelaufen"
_SICHTBAR = ("aktiv", "evtl. ausgelaufen")

# Die harte Aussage eines Angebots: Preis, Datenmenge, Bandbreite, Rabatt.
# Genau das gehoert auf eine Schriftkachel - "20 GB fuer 6,99 €" sagt in
# zwei Zahlen, worum es geht. Bis zum 08.08.2026 stand dort die MECHANIK
# ("Wechsel- oder Altgeraetpraemie"), und weil vier Marken dieselbe fahren,
# standen vier identische Kacheln nebeneinander - das liest sich als Fehler,
# nicht als Gestaltung.
# Die abschliessende Grenze ist nicht kosmetisch: ohne sie schnitt "EUR"
# mitten aus "1 Euro einmalig" ein "1 Eur" heraus, und genau so stand es am
# 08.08.2026 als Schriftkachel auf der Otelo-Karte.
_ZAHL_RE = re.compile(
    r"\d[\d.,]*\s?(?:€|Euro|EUR|%|GB|TB|MBit/s|Mbit/s|MB/s|MB|Cent)"
    r"(?![A-Za-zÄÖÜäöüß])", re.I)
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


def _rang(src) -> tuple:
    """Der Platz einer Marke in der Anbieter-Rangfolge.

    Antonio am 08.08.2026: "die groessten Anbieter wie Telekom etc. an
    erster Stelle, soll also nach Wichtigkeit der Anbieter geordnet werden."
    Gepflegt wird das in config/promo_sources.yaml (`rang`, dort steht auch
    die Begruendung der Reihenfolge). Ohne gepflegten Rang entscheiden Tier,
    Reichweite und Name - damit eine frisch eingetragene Marke eine
    definierte Stelle hat, statt nach Zufall irgendwo zu landen.
    """
    rang = getattr(src, "rang", None)
    if rang:
        return (rang, 0, 0, "")
    return (RANG_UNGESETZT, getattr(src, "tier", 2) or 2,
            -(getattr(src, "reach", None) or 0), (getattr(src, "name", "") or "").lower())


def _initials(name: str) -> str:
    words = [w for w in (name or "").replace("/", " ").split() if w[:1].isalnum()]
    letters = "".join(w[0] for w in words[:2]).upper()
    return letters or "?"


def _kachel_kandidaten(offer: dict, mechanik: str) -> list[str]:
    """Was auf der Schriftkachel stehen kann, konkret vor generisch.

    Eine Liste statt eines Werts, weil die Kachel sich innerhalb einer Marke
    nicht wiederholen darf (siehe _entdoppele_kacheln): steht in einem Block
    zweimal "10 €" untereinander, liest sich das als Fehler, obwohl beide
    Angebote wirklich 10 € kosten.

    Die Stufen: die Zahlen der Ueberschrift ("20 GB · 6,99 €"), dann alle
    ihre Zahlen, dann ihr erster Sinnabschnitt, dann die Mechanik. Die
    Mechanik ist ausdruecklich die LETZTE Wahl - sie beschreibt eine
    Angebotsart und unterscheidet zwei Angebote nicht. "sonstiges" faellt
    ganz heraus: es ist der Sammelschluessel des Bewertungsagenten und sagt
    einem Leser nichts.
    """
    headline = " ".join((offer.get("headline") or "").split())
    zahlen: list[str] = []
    for m in _ZAHL_RE.finditer(headline):
        wert = " ".join(m.group(0).split())
        if wert not in zahlen:
            zahlen.append(wert)
    kandidaten = []
    if zahlen:
        kandidaten.append(" · ".join(zahlen[:2]))
        if len(zahlen) > 2:
            kandidaten.append(" · ".join(zahlen[2:4]))
    erster = _KLAUSEL_RE.split(headline)[0].strip()
    if len(erster) > _KACHEL_MAX:
        erster = _NAEHER_RE.split(erster)[0].strip()
    # Die ganze Ueberschrift taugt nicht als Kachel: sie steht zwei Zeilen
    # tiefer noch einmal, und dieselbe Aussage zweimal untereinander liest
    # sich als Panne. Ein AUSSCHNITT ist etwas anderes - er hebt hervor.
    if erster and erster != headline and len(erster) <= _KACHEL_MAX:
        kandidaten.append(erster)
    if mechanik and mechanik != "sonstiges":
        kandidaten.append(mechanik)
    kandidaten.append("Aktion")
    return list(dict.fromkeys(k for k in kandidaten if k))


def _kachel_text(offer: dict, mechanik: str) -> str:
    """Die beste Schriftkachel eines Angebots ohne Ruecksicht auf seine
    Nachbarn - der Normalfall und die Grundlage der Tests."""
    return _kachel_kandidaten(offer, mechanik)[0]


def _entdoppele_kacheln(karten: list[dict]) -> None:
    """Innerhalb eines Markenblocks traegt jede Schriftkachel einen eigenen
    Text.

    Seit dem 08.08.2026 hat JEDE Karte ohne Motiv eine Kachel (vorher nur
    die grosse), und damit stehen in einem Block bis zu acht davon
    nebeneinander - bei winSIM zweimal "1 GB" und zweimal "Jahrestarife",
    bei PremiumSIM zweimal "25 GB". Zwei gleiche Kacheln untereinander sind
    genau der Eindruck, den diese Runde loswerden soll. Wer schon vergeben
    ist, nimmt die naechste Stufe seiner eigenen Kandidatenliste; ist auch
    die vergeben, bleibt es beim besten Text - eine falsche Zahl waere
    schlimmer als eine wiederholte.
    """
    vergeben: set[str] = set()
    for k in karten:
        if k["bild"]:
            continue
        for kandidat in k["kachel_kandidaten"]:
            if kandidat not in vergeben:
                k["kachel"] = kandidat
                break
        vergeben.add(k["kachel"])


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


def _ohne_dubletten(sichtbar: list[dict]) -> list[dict]:
    """Dasselbe Angebot steht nur einmal im Block.

    PromoDB.upsert erkennt eine Umformulierung derselben Aktion und
    aktualisiert den bestehenden Eintrag, statt einen zweiten anzulegen
    (_find_existing_id). Was vor dieser Erkennung entstanden ist, liegt
    trotzdem doppelt in der Datenbank - am 08.08.2026 bei Lidl Connect
    gleich zweimal: "SMART Tarife mit 5G und Flatrate" neben
    "SMART-Tarife mit 5G und Flatrate", "Jahrestarife – einmal zahlen"
    neben "Jahrestarife: Einmal zahlen". Auf der Seite standen sie als zwei
    Karten nebeneinander, und das liest sich als Fehler, nicht als zwei
    Angebote.

    Gerechnet wird mit derselben Heuristik wie im Store (`_same_offer`:
    Wortueberlappung plus Zahlenwaechter, damit "10 GB Bonus" und "20 GB
    Bonus" getrennt bleiben). Die Liste kommt bereits sortiert - der
    staerkere Eintrag steht vorn und bleibt. Die DATENBANK wird nicht
    angefasst: das hier ist ein Anzeigefilter, kein stiller Loeschvorgang.
    """
    behalten: list[dict] = []
    for eintrag in sichtbar:
        kopf = eintrag.get("headline") or ""
        zwilling = next((b for b in behalten
                         if _same_offer(kopf, b.get("headline") or "")), None)
        if zwilling is None:
            behalten.append(eintrag)
            continue
        # Das Motiv der Dublette gehoert derselben Aktion - es faellt nicht
        # weg, nur weil die andere Schreibweise gewinnt.
        if eintrag.get("image") and not zwilling.get("image"):
            for feld in ("image", "image_w", "image_h", "image_kind"):
                if eintrag.get(feld) is not None:
                    zwilling[feld] = eintrag[feld]
    return behalten


def _karte(brand: dict, offer: dict) -> dict:
    """Ein Angebot als Anzeigeeinheit - genau die Felder, die eine Karte
    zeigt. Die Vorlage rechnet nichts mehr aus."""
    mechanik = MECHANICS.get(offer.get("mechanic") or "", "")
    kandidaten = _kachel_kandidaten(offer, mechanik)
    return {
        "brand": brand,
        "offer": offer,
        "score": offer.get("score"),
        "highlight": bool(offer.get("highlight")),
        "reason": offer.get("score_reason") or "",
        "mechanic": mechanik,
        # `kachel` ist die Vorauswahl; _entdoppele_kacheln() entscheidet
        # innerhalb des Markenblocks endgueltig.
        "kachel": kandidaten[0],
        "kachel_kandidaten": kandidaten,
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


# Was die grosse Flaeche verlangt. Sie ist bei 1440 px Fensterbreite 579 px
# breit; auf dem Schirm, auf dem diese Seite gelesen wird (MacBook, zwei
# Geraetepixel je CSS-Pixel), sind das 1158 echte Pixel. Ein 620-px-Motiv
# dort ist nicht hochskaliert im Sinne von Kriterium 6 - es ist trotzdem
# unscharf, und genau so sah Antonio es am 16.08.2026. Unterhalb dieser
# Breite fuehrt die Aktion ihren Block weiterhin an, aber in der kleinen
# Flaeche: das Motiv bleibt, die Unschaerfe geht.
LEAD_MIND_BREITE = 900
# Ab wie vielen weiteren Karten die Aufmacherkarte zwei Rasterzeilen hoch
# steht. Zwei Zeilen brauchen VIER volle Zellen daneben (2 Spalten x 2
# Zeilen) - mit drei blieb am 27.08.2026 die Zelle unten rechts leer (ALDI
# TALK, live gemessen). Darunter bleibt neben ihr eine Zelle leer - und eine
# Luecke MITTEN im Raster ist genau das "kreuz und quer", das diese Fassung
# abstellt.
_HOCH_AB_WEITEREN = 4


def _block(brand: dict) -> dict:
    """Eine Marke mit allen ihren sichtbaren Aktionen als Kartenblock.

    `lead` ist die staerkste (grosse Karte), `weitere` sind die uebrigen in
    derselben Form. Getrennt gefuehrt, weil die Vorlage sie verschieden
    GEWICHTET - nicht, weil sie an zwei Orten stehen. Genau diese Trennung
    war bis zum 08.08.2026 eine Trennung im Seitenaufbau, und das war der
    Fehler.

    `lead_gross` und `lead_hoch` rechnet DIESE Stelle, nicht die Vorlage:
    beide haengen an Zahlen (Motivbreite, Zahl der uebrigen Karten), und
    eine Vorlage, die Zahlen vergleicht, ist eine Vorlage, die niemand
    testet.
    """
    karten = [_karte(brand, o) for o in brand["active"]]
    block = dict(brand, lead=karten[0] if karten else None,
                 weitere=karten[1:], karten=karten,
                 top_score=karten[0]["score"] if karten else None)
    gewichte(block)
    return block


def gewichte(block: dict) -> None:
    """Setzt `lead_gross` und `lead_hoch` eines Blocks.

    Eigene Funktion, weil sie ZWEIMAL laufen muss: `_entdoppele_bilder()`
    kann der Aufmacherkarte ihr Motiv noch nehmen, und eine Karte ohne
    Motiv beantwortet die Breitenfrage anders als eine mit einem zu
    schmalen. Wer sie nur in `_block()` rechnet, bekommt eine Aufmacherkarte,
    die aus einem Grund klein bleibt, den es auf der Seite nicht mehr gibt.

    Beide Gewichte werden gegen die TATSAECHLICHE Kartenzahl gerechnet, nicht
    nur gegen die Motivbreite - live gemessen am 27.08.2026: PremiumSIM und
    simplytel hatten genau EINE weitere Karte neben der zweispaltigen
    Aufmacherkarte, und die vierte Spalte blieb leer. Eine zweispaltige
    Aufmacherkarte braucht deshalb entweder GAR keine oder MINDESTENS zwei
    weitere Karten daneben, sonst faellt sie auf die normale Breite zurueck -
    zwei kleine Karten mit Rest-Weissraum rechts sind eine normale kurze
    Reihe, keine Luecke neben einer groesseren Karte.
    """
    lead = block.get("lead")
    weitere = len(block["karten"]) - 1
    # Eine Schriftkachel ist Text und in jeder Groesse scharf - nur ein
    # Rasterbild muss die Flaeche fuellen koennen.
    bildtauglich = bool(lead) and (not lead["bild"]
                                  or (lead["bild_w"] or 0) >= LEAD_MIND_BREITE)
    hoch = bildtauglich and weitere >= _HOCH_AB_WEITEREN
    gross = bildtauglich and not (not hoch and weitere == 1)
    block["lead_gross"] = gross
    block["lead_hoch"] = gross and hoch


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
        sichtbar = _ohne_dubletten(
            sorted((e for e in eintraege if e.get("status") in _SICHTBAR),
                   key=_sortierschluessel, reverse=True))
        bestaetigt = [e for e in sichtbar if e.get("status") == "aktiv"]
        beendet = [e for e in eintraege if e.get("status") == _RETIRED_STATUS]

        if not src.internal_reference and bestaetigt:
            active_total += len(bestaetigt)
            brands_active += 1

        marken.append({
            "name": src.name, "tier": src.tier, "rang": _rang(src),
            # Sprungziel fuer die Dossier-Suche: ein Treffer vom Typ "Aktion"
            # verlinkt hierher. Die Rechnung steht in report/suchindex.py -
            # dort wird der Link geschrieben, hier der Anker gesetzt, und wenn
            # die zwei auseinanderlaufen, springt die Suche ins Leere.
            "anker": marken_anker(src.name),
            "tier_label": TIER_LABEL.get(src.tier, ""),
            "color": _OWN_COLOR if src.internal_reference else TIER_COLOR.get(src.tier, "#3860be"),
            "group": src.group, "url": src.url,
            "internal_reference": src.internal_reference,
            "initials": _initials(src.name),
            "active": sichtbar, "stale": beendet,
            "active_count": len(bestaetigt),
            "has_offers": bool(sichtbar),
        })

    # Wettbewerber mit sichtbarem Angebot zuerst, dann nach Anbieterrang;
    # Vodafones eigene Referenzkarte immer als letzte.
    marken.sort(key=lambda b: (b["internal_reference"], not b["has_offers"],
                               b["rang"]))

    # ----------------------------------------------------------- Bloecke
    # Je Marke ein Block, WICHTIGSTER ANBIETER ZUERST (siehe _rang).
    #
    # Bis zum 08.08.2026 sortierte hier der Score der staerksten Aktion. Das
    # war eine Rangliste der Angebote, keine des Marktes, und sie hing an
    # einem einzigen Lauf: die Telekom stand auf Platz zehn, weil ihre
    # JS-Seiten an dem Tag nur zwei Angebote hergaben, waehrend Otelo mit
    # einer starken Freundschaftswerbung die Seite anfuehrte. Wer wissen
    # will, was die Telekom macht, soll nicht scrollen muessen - und die
    # Reihenfolge soll nicht jede Woche eine andere sein.
    #
    # Der Score ordnet weiterhin INNERHALB einer Marke (siehe
    # _sortierschluessel) und traegt die Hervorhebung "wichtig".
    bloecke = [_block(b) for b in marken
               if b["has_offers"] and not b["internal_reference"]]
    bloecke.sort(key=lambda b: b["rang"])

    eigene_marke = next((b for b in marken
                         if b["internal_reference"] and b["has_offers"]), None)
    eigen = _block(eigene_marke) if eigene_marke else None

    # Alle Wettbewerberkarten in Seitenreihenfolge - die Grundlage, gegen die
    # die Wahrheitstests rechnen ("jede sichtbare Aktion genau einmal").
    karten = [k for b in bloecke for k in b["karten"]]
    alle_karten = karten + (eigen["karten"] if eigen else [])
    # Erst die Motive entdoppeln, dann die Kacheln: die erste Runde kann
    # einer Karte ihr Bild nehmen, und die wird dadurch zur Schriftkachel.
    _entdoppele_bilder(alle_karten)
    for block in bloecke + ([eigen] if eigen else []):
        _entdoppele_kacheln(block["karten"])
        # Nach dem Entdoppeln, nicht davor: eine Aufmacherkarte, die hier ihr
        # Motiv verloren hat, ist eine Schriftkachel und darf die grosse
        # Flaeche wieder tragen.
        gewichte(block)

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
