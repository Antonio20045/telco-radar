"""Vodafone: der eigene Preis, ohne den es keinen Vergleich gibt.

WARUM DIESER ADAPTER ZUERST GEBAUT WURDE
----------------------------------------
Die Seite beantwortet die Frage "wer ist guenstiger als Vodafone?". Ohne die
eigene Listung hat diese Frage keinen Bezugspunkt - jede andere Zahl steht
dann allein da. Deshalb ist Vodafone der erste neue Anbieter dieser Stufe und
nicht der letzte.

DER WEG, GEMESSEN AM 28.08.2026
-------------------------------
Im Roh-HTML von /privat/handys-tablets-tarife/alle-smartphones.html steht
kein Preis - das war der Befund vom 11.08.2026 und er stimmt weiterhin. Der
Preis entsteht im Browser aus derselben oeffentlichen Schnittstelle, die
diese Seite selbst benutzt:

    GET https://api.vodafone.de/glados/v2/hardware/v2
        ?businessTransaction=newContract&salesChannel=Online.Consumer
    GET https://api.vodafone.de/glados/v2/hardware/v2/virtualItem/<id>?…

Die Adresse, die zwei Pflichtparameter und der oeffentliche Browser-Schluessel
stehen woertlich in Vodafones eigenem Skriptbuendel
`/simplicity/device-overview/device-overview.bundle.js`; jeder Besucher der
Seite schickt sie mit. `api.vodafone.de` hat keine robots.txt (HTTP 404, also
keine Regeln).

ZWEI PREISE, UND NUR EINER IST DER GERAETEPREIS
-----------------------------------------------
Die Liste traegt unter `prices.composition` ausschliesslich Buendelzahlen
(Tarif plus Geraet, 1 EUR Anzahlung). Der Preis OHNE Vertrag steht eine Ebene
tiefer, je Variante, unter

    atomics[].prices.hardware.priceByType.rate.onetime.withoutDiscounts.gross

Deshalb ruft dieser Adapter je Geraet die Detailnutzlast ab, statt sich die
Liste zu sparen: die Liste allein haette 1-Euro-Lockpreise geliefert, und
genau die haelt der Lockpreis-Waechter seit dem 10.08.2026 heraus.

DIE REGEL "NUR VERLINKTE ADRESSEN" GILT UNVERAENDERT
----------------------------------------------------
Die `virtualItemId` jedes Geraets steht in der Nutzlast der Einstiegsseite.
Es wird keine ID hochgezaehlt - dieselbe Grenze wie beim Tarif-Sammler
(§ 87b UrhG).

BUENDELPREISE (B1, 05.09.2026): DIESELBE ANTWORT, EINE ZWEITE LESART
----------------------------------------------------------------------
Die Detailnutzlast, die `lies()` schon in Listungen zerlegt, traegt unter
`atomics[].prices.composition` zusaetzlich 2-4 Geraet-plus-Tarif-Angebote je
Variante: `financingType`, `offerCoreHash`, `totalMonthlyRatePrice` (die
Gesamtrate der ERSTEN Phase) und `priceByComponent.{tariff,hardware}` mit
Einmal- und Monatsbetrag. `lies_buendel()` liest das - EIN Abruf, zwei
Lesarten, kein zweiter Einstieg noetig (das braucht nur, wer wie o2 eine
EIGENE Adresse fuer den Buendelkatalog hat).

DIE RECHENPROBE ENTSCHEIDET, NICHT `financingType`
---------------------------------------------------
Gemessen an allen Kompositionen des Musterbuendels (Google Pixel 11,
hardwareId 58060/58061/58063): bei `financingType: "rate"` geht
`tarif.month + hardware.month == totalMonthlyRatePrice[0]` in JEDEM Fall
exakt auf (12/24/36 Monate Ratenlaufzeit). Bei `financingType: "sub"` geht
diese Summe NIE auf - `hardware.month` (z. B. 30 EUR) ist dort ein
Vergleichswert, keine tatsaechlich zusaetzlich berechnete Rate, denn
`tarif.month` ALLEIN entspricht schon der Gesamtrate (69,99 EUR = 69,99
EUR). Das Geraet steckt in diesem Fall vollstaendig im hoeheren Tarifpreis;
eine separate Geraeterate gibt es nicht. Deshalb probiert
`_buendelsatz_aus_komposition()` ERST die Summe MIT Geraeterate, dann OHNE
(dann `geraet_monatsrate=None`) - und verwirft nur, wenn KEINE der beiden
Rechnungen aufgeht. Das haengt nicht am Namen `financingType`, der koennte
sich aendern; es haengt an der Zahl.

ALLE LAUFZEITEN SIND SCHON ERFASST - GEMESSEN, NICHT VERMUTET (P0-B2a)
------------------------------------------------------------------------
`lies_buendel()` iteriert bereits ueber JEDE Komposition in
`prices.composition` (2-4 je Variante) und legt fuer jede einen eigenen
Rohsatz an - 12/24/36 Monate UND `sub` kommen alle vier als eigene Buendel
heraus (gemessen am Musterbuendel: 3 Varianten x 4 Kompositionen = 12
Saetze, `test_zwoelf_buendel_aus_drei_varianten_und_vier_kompositionen`).
Anders als bei Telekom/congstar musste hier also keine Auswahl aufgehoben
werden.

Eine ZWEITE Phase in `totalMonthlyRatePrice` (36-Monats-Finanzierung: Monate
1-24 Tarif+Geraet, 25-36 nur noch Geraet) ist KEIN verlorener Messpunkt:
`geraet_monatsrate` kommt nicht aus `_periode0()`, sondern flach aus
`priceByComponent.hardware.priceByType.rate.month`, das schon die GANZE
Ratenlaufzeit abdeckt (`recurrenceEnd == financingDuration`). Nachgerechnet
an allen drei Ratenfaellen der Fixture (12/24/36 Monate):
Zuzahlung + Laufzeit x Rate trifft `priceByComponent.hardware...total.
onetime.withoutDiscounts.gross` auf den Cent genau
(`test_alle_phasen_ergeben_den_richtigen_geraete_gesamtpreis`).

WOHER DIE LAUFZEIT KOMMT - DREI QUELLEN, KEINE VERMISCHUNG (FIX3)
------------------------------------------------------------------
`_laufzeit()` nimmt `financingDuration`; fehlt sie, das ENDE DER
GERAETERATE (`priceByComponent.hardware...rate.month.withoutDiscounts.
recurrenceEnd`, gemessen in allen 9 Ratenkompositionen der Fixture exakt
gleich `financingDuration`); und nur wenn es gar keine Geraeterate gibt -
der `sub`-Fall -, die Vertragsmindestlaufzeit aus den Phasen von
`totalMonthlyRatePrice` (`_letztes_phasenende`).

Die Phasen beschreiben den GANZEN VERTRAG und laufen laenger als die
Finanzierung. Sie auch im Ratenfall als Rueckfall zu nehmen, verdoppelte
die Geraetekosten: gemessen an der echten 12-Monats-Komposition ohne
`financingDuration` ergaben 64,50 EUR ueber 24 statt 12 Monate 1549,00 EUR
statt der in derselben Nutzlast belegten 775,00 EUR.

EINE OFFENE PHASE IST KEINE LAUFZEIT (FIX3, 21.09.2026)
--------------------------------------------------------
Die erste Fassung dieses Rueckfalls las `perioden[-1]["recurrenceEnd"]`
und verlor damit ein ganzes Buendel STILL: traegt die letzte Phase kein
Ende (`recurrenceEnd: null`, die uebliche Form einer offenen
Anschlussphase "ab Monat 25"), wurde `int(None)` zum TypeError, die
Laufzeit blieb None und der Satz fiel ohne Protokoll heraus. Kein
gespeicherter Abruf zeigt so eine Phase im `sub`-Fall - alle DREI
`sub`-Kompositionen der Fixture tragen genau `(1, 24)`, und
`recurrenceEnd: null` kommt in der Datei nicht vor; gemessen ist der
Verlust an der Fixture mit einer IM TEST ergaenzten zweiten Phase
`{recurrenceStart: 25, recurrenceEnd: null}`: 0 Saetze statt 1. Seither
gilt: eine Phase ohne Ende ist eine offene Anschlussphase und traegt keine
Laufzeit, die Vertragsmindestlaufzeit bleibt der Rueckfall - und wenn gar
keine Laufzeit bestimmbar ist, nennt das Protokoll Hash, Geraeterate und
Phasenenden, statt das Angebot lautlos zu verschlucken.

DIE OFFENE TARIFNAMEN-FRAGE IST GEKLAERT: JA, ES GIBT EINEN ENDPUNKT
----------------------------------------------------------------------
`prices.composition[].offerCoreHash` nennt keinen Klarnamen - aber
`/glados/v2/tariff/v2/hardware?hardwareId=<hardwareId>&businessTransaction=
newContract&salesChannel=Online.Consumer` (Pfad `xy+Ty[V2]` im
Skriptbuendel, Parameter `hardwareId` = `fy` in dessen Variablennamen)
liefert je Geraet die Liste seiner buchbaren Tarife MIT `tariffName` UND
dem GLEICHEN `offerCoreHash` in ihren eigenen `atomics[].prices.composition`
-Eintraegen. Live gemessen (05.09.2026, 15 Geraete, reiner HTTP-GET, `x-api-
key` wie beim Hauptendpunkt): 11 von 30 Kompositions-Hashes lösten auf (9 von
15 Geraeten mit mindestens einem Treffer) - u. a. "Mobil S", "Mobil M",
"FamilyCard M". Nicht jeder Hash steht in der Antwort (Kampagnen- oder
auslaufende Tarife fehlen dort); das ist keine Luecke der Aufloesung,
sondern der Antwort selbst - `loese_tarifnamen()` verwirft in diesem Fall
nichts, der Rohsatz bleibt mit `tarif_name=""` stehen und faellt spaeter in
`tco_buendel.aus_rohsaetzen()` in den Zweig "ohne aufloesbaren Tarif".

`loese_tarifnamen()` macht dafuer EINEN zusaetzlichen GET je EINDEUTIGER
`hardwareId` (nicht je Rohsatz) und wird NICHT von `lies_buendel()` selbst
aufgerufen - ein Adapter bleibt ein reiner Text-zu-Daten-Uebersetzer ohne
eigenes Netz. Aufgerufen wird sie von der Pipeline (`geraete_pipeline.py`),
nachdem alle Anbieter gesammelt sind, ueber den generischen Adapter-Haken
`Adapter.loese_tarifnamen`.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Callable, Optional
from urllib.parse import urlsplit

from . import GeraeteAbrufFehler
# DIE EINE STELLE, die entscheidet, ob ein Rohwert eine Ratenlaufzeit IST
# (Clean Code 1) - dieselbe Pruefung, die `buendel_id` und `Buendel` lesen.
# Eine eigene `int()`-Zeile hier waere eine zweite, schwaechere Definition:
# sie wuerde 24,5 still auf 24 abschneiden.
from ...tco_model import laufzeit_in_monaten

log = logging.getLogger(__name__)

# Die zwei Pflichtparameter. Ohne sie antwortet die Schnittstelle mit
# HTTP 400 und nennt das fehlende Feld beim Namen - beide Werte stammen aus
# dem Skriptbuendel der Seite, nicht aus einem Versuch.
_PARAMETER = "businessTransaction=newContract&salesChannel=Online.Consumer"

_GB_RE = re.compile(r"(\d+)\s*(GB|TB)", re.IGNORECASE)


def _json(text: str, was: str) -> dict:
    try:
        daten = json.loads(text or "")
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(f"{was} unlesbar: {exc}") from exc
    if not isinstance(daten, dict):
        raise GeraeteAbrufFehler(f"{was}: kein Objekt")
    return daten


def _speicher_gb(label: str) -> Optional[int]:
    """"256 GB" -> 256, "1 TB" -> 1024.

    Bewusst am `displayLabel` und nicht am `sortValue`: der ist in Mebibyte
    (262144 fuer 256 GB) und braeuchte eine zweite Umrechnung, die bei
    1 TB stillschweigend danebenliegen kann.
    """
    m = _GB_RE.search(label or "")
    if not m:
        return None
    zahl = int(m.group(1))
    return zahl * 1024 if m.group(2).upper() == "TB" else zahl


def _pfad(nutzlast: dict, *stufen):
    """Einen tiefen Pfad lesen, ohne bei jeder fehlenden Stufe zu werfen."""
    knoten = nutzlast
    for stufe in stufen:
        if not isinstance(knoten, dict):
            return None
        knoten = knoten.get(stufe)
    return knoten


def ernte(text: str, basis_url: str, pfadmuster="", kind: str = "") -> list[str]:
    """Aus der Geraeteliste die Detailadressen - eine je Geraet.

    Die Adressen entstehen aus den `virtualItemId`, die die Liste selbst
    nennt. Ein Geraet ohne Id wird uebersprungen und nicht geraten.
    """
    daten = _json(text, "Geraeteliste")
    geraete = _pfad(daten, "data", "devices") or []
    teile = urlsplit(basis_url)
    herkunft = f"{teile.scheme}://{teile.netloc}"
    out: list[str] = []
    gesehen: set[str] = set()
    for geraet in geraete:
        if not isinstance(geraet, dict):
            continue
        vid = str(geraet.get("virtualItemId") or "").strip()
        if not vid or vid in gesehen:
            continue
        gesehen.add(vid)
        out.append(f"{herkunft}/glados/v2/hardware/v2/virtualItem/{vid}"
                   f"?{_PARAMETER}")
    return out


def lies(text: str, url: str = "") -> list[dict]:
    """Aus der Detailnutzlast eines Geraets je Variante einen Rohsatz.

    Eine Variante ohne Geraetepreis wird uebergangen statt mit ihrer
    Buendelzahl gefuellt - eine Zuzahlung ohne Tarifreferenz ist nach der
    Disziplin dieses Projekts kein Preis.
    """
    daten = _json(text, "Geraetedetail")
    knoten = daten.get("data") if isinstance(daten.get("data"), dict) else daten
    modell = str(knoten.get("modelName") or "").strip()
    if not modell:
        raise GeraeteAbrufFehler("Geraetedetail ohne modelName")

    # Die Produktseite, die ein Mensch aufrufen kann. Der rohe
    # Schnittstellenaufruf waere als Quellenlink wertlos: die Seite
    # verspricht zu jeder Zahl einen nachpruefbaren Beleg, und niemand
    # prueft eine JSON-Antwort mit Schluessel nach.
    #
    # ABSOLUT, und zwar auf www.vodafone.de. Die Nutzlast nennt den Pfad
    # relativ ("/privat/handys/iphone-15.html"), und der Collector loest ihn
    # gegen die QUELLE auf - das ist hier api.vodafone.de. Im ersten Lauf
    # standen deshalb 150 Quelllinks auf "https://api.vodafone.de/privat/
    # handys/..." in der Datenbank und im CSV-Export: Adressen, die es nicht
    # gibt. Kein Test hat das gemeldet; aufgefallen ist es beim Lesen der
    # exportierten Tabelle.
    hubpage = str(_pfad(knoten, "hubpage", "href") or "").strip()
    if hubpage.startswith("/"):
        hubpage = "https://www.vodafone.de" + hubpage

    out: list[dict] = []
    for atom in (knoten.get("atomics") or []):
        if not isinstance(atom, dict):
            continue
        preis = _pfad(atom, "prices", "hardware", "priceByType", "rate",
                      "onetime", "withoutDiscounts", "gross")
        if preis is None:
            continue
        speicher = _speicher_gb(str(_pfad(atom, "capacity", "displayLabel") or ""))
        farbe = str(_pfad(atom, "color", "displayLabel") or "").strip()
        # Der Titel wird aus MODELL, Speicher und Farbe gebaut, nicht aus
        # `label` uebernommen: dort steht "Google Pixel Hibiscus (256 GB)" -
        # ohne die Generation, weil die Farbe den Modellnamen verdraengt hat.
        # Aus so einem Titel findet die Geraeteerkennung ihren Katalogeintrag
        # nicht mehr.
        titel = " ".join(x for x in (modell,
                                     f"{speicher} GB" if speicher else "",
                                     farbe) if x)
        out.append({
            "titel": titel,
            # E4-Auto-Erkennung: der strukturierte NAME (Feld `modelName`),
            # getrennt vom zusammengesetzten Titel.
            "strukturierter_name": modell,
            "preis": float(preis),
            "waehrung": "EUR",
            # `shippingInfo` nennt einen Liefertermin, wenn es einen gibt.
            # Daraus "lieferbar" zu machen waere eine Behauptung ueber den
            # Lagerbestand, die dort nicht steht.
            "verfuegbarkeit": ("lieferbar"
                               if _pfad(atom, "shippingInfo", "date")
                               else "unbekannt"),
            "sku": str(atom.get("hardwareId") or "").strip(),
            "ean": "",
            "farbe": farbe,
            "speicher_gb": speicher,
            "url": hubpage,
            "quelle": "vodafone_api",
        })
    return out


# --------------------------------------------------------------------------
# BUENDELPREISE - siehe Modulkopf, Abschnitt B1
# --------------------------------------------------------------------------

def _preis(wert) -> Optional[float]:
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def _gleich(a: Optional[float], b: Optional[float]) -> bool:
    """Ein Cent ist kein Rundungsfehler - dieselbe Toleranz wie bei o2."""
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) < 0.005


def _perioden(komposition: dict) -> list[dict]:
    """ALLE Phasen von `totalMonthlyRatePrice.withoutDiscounts` - eine
    Ratenlaufzeit ueber 24 Monate hinaus (financingDuration 36) traegt
    zwei (Monate 1-24 Tarif+Geraet, 25-36 nur noch die Geraeterate)."""
    perioden = _pfad(komposition, "totalMonthlyRatePrice", "withoutDiscounts")
    if not isinstance(perioden, list):
        return []
    return [p for p in perioden if isinstance(p, dict)]


def _periode0(komposition: dict) -> Optional[dict]:
    """Die ERSTE Phase - die, gegen die die Komponentenbetraege
    (`recurrenceStart: 1`) nachgerechnet werden.

    Die ZWEITE Phase (falls vorhanden) zaehlt fuer DIESE Probe nicht mit -
    sie ist keine zusaetzliche Messung, sondern derselbe Vertrag in seinem
    zweiten Abschnitt. Die Geraeterate selbst kommt nicht von hier: sie
    steht flach fuer die GANZE Ratenlaufzeit unter
    `priceByComponent.hardware.priceByType.rate.month` (gemessen an allen
    12/24/36-Kompositionen der Fixture `vodafone_virtualitem.json`:
    Zuzahlung + Laufzeit x Rate ergibt dort exakt
    `priceByComponent.hardware...total.onetime.withoutDiscounts.gross` -
    kein Phasenwechsel noetig). Nur der LAUFZEIT-Fallback ohne eigene
    `financingDuration` (der "sub"-Fall) braucht mehr als Phase 0, siehe
    `_buendelsatz_aus_komposition`."""
    perioden = _perioden(komposition)
    return perioden[0] if perioden else None


def _letztes_phasenende(komposition: dict) -> Optional[int]:
    """Das ENDE DER LETZTEN BEPREISTEN PHASE des Vertrags - oder None.

    In der gemessenen Form ist das die Vertragsmindestlaufzeit: der
    `sub`-Fall der Fixture traegt genau eine Phase (1 bis 24). Traegt eine
    Antwort mehrere bepreiste Abschnitte, gilt der spaeteste - weiter
    reicht diese Zahl nicht, und sie heisst deshalb nach dem, was sie
    misst, nicht nach dem, wofuer sie verwendet wird.

    `totalMonthlyRatePrice` beschreibt den GANZEN Vertrag, nicht die
    Geraetefinanzierung - diese Zahl gilt deshalb nur im `sub`-Fall, in
    dem es gar keine Geraeterate gibt (siehe `_laufzeit`).

    EINE PHASE OHNE `recurrenceEnd` IST KEINE LAUFZEIT. `recurrenceEnd:
    null` ist die uebliche Form einer offenen Anschlussphase ("ab Monat
    25, bis auf Weiteres") - sie endet nicht und kann deshalb keine
    Mindestlaufzeit tragen. Genommen wird die spaeteste Endgrenze, die
    ueberhaupt genannt ist (in den gemessenen Kompositionen laufen die
    Phasen aufsteigend, dort ist das die letzte mit einem Ende).

    Der Rueckfall auf `perioden[-1]["recurrenceEnd"]` (21.09.2026, P0-B2a)
    hat genau daran ein GANZES Buendel verloren: die offene Anschlussphase
    machte `int(None)` zum TypeError, die Laufzeit blieb None und der Satz
    fiel ohne Protokoll heraus (Behebung FIX3).
    """
    enden = [ende for ende in (laufzeit_in_monaten(p.get("recurrenceEnd"))
                               for p in _perioden(komposition))
             if ende is not None]         # None = offene Phase, kein Ende
    return max(enden) if enden else None


def _laufzeit(komposition: dict,
              geraet_monatsrate: Optional[float]) -> Optional[int]:
    """Die Ratenlaufzeit dieser Komposition - oder None als Luecke.

    DREI QUELLEN, IN DIESER ORDNUNG, UND KEINE VERMISCHUNG:

    1. `financingDuration` - die Laufzeit, die die Nutzlast selbst nennt.
    2. Fehlt sie und gibt es eine GERAETERATE, nennt die Rate ihr eigenes
       Ende: `priceByComponent.hardware...rate.month.withoutDiscounts.
       recurrenceEnd`. Gemessen an allen drei Ratenfaellen der Fixture ist
       das exakt `financingDuration` (12/24/36) - dieselbe Zahl, zweite
       Stelle.
    3. Gibt es KEINE Geraeterate (der `sub`-Fall), gibt es auch keine
       Finanzierung; dann gilt die Vertragsmindestlaufzeit aus den Phasen
       (`_letztes_phasenende`).

    Die Phasen von `totalMonthlyRatePrice` beschreiben den ganzen Vertrag
    und koennen LAENGER laufen als die Geraetefinanzierung. Sie als
    Rueckfall auch fuer den Ratenfall zu nehmen, verdoppelte die
    Geraetekosten: gemessen an der echten 12-Monats-Komposition ohne
    `financingDuration` ergab die Rate 64,50 EUR ueber 24 statt 12 Monate
    1549,00 EUR statt der belegten 775,00 EUR (FIX3).
    """
    laufzeit = laufzeit_in_monaten(komposition.get("financingDuration"))
    if laufzeit is not None:
        return laufzeit
    if geraet_monatsrate is not None:
        return laufzeit_in_monaten(
            _pfad(komposition, "priceByComponent", "hardware", "priceByType",
                  "rate", "month", "withoutDiscounts", "recurrenceEnd"))
    return _letztes_phasenende(komposition)


def _buendelsatz_aus_komposition(modell: str, hubpage: str, hardware_id: str,
                                 farbe: str, speicher: Optional[int],
                                 komposition: dict) -> Optional[dict]:
    """Eine Komposition wird ein Buendel-Rohsatz - oder nichts, siehe
    Modulkopf (die Rechenprobe entscheidet, nicht `financingType`)."""
    hash_ = str(komposition.get("offerCoreHash") or "").strip()
    if not hash_:
        # Ohne `offerCoreHash` gibt es keinen Schluessel, ueber den
        # `loese_tarifnamen()` je einen Tarifnamen findet - der Satz waere
        # ein Buendel ohne benennbaren Tarif.
        log.info("Vodafone-Buendel: Komposition ohne offerCoreHash "
                 "(financingType %r) - verworfen",
                 komposition.get("financingType"))
        return None

    periode = _periode0(komposition)
    gesamt = _preis((periode or {}).get("gross")) if periode else None
    if gesamt is None:
        log.info("Vodafone-Buendel: Komposition %s ohne Gesamtrate in "
                 "totalMonthlyRatePrice - verworfen", hash_)
        return None

    tarif = _pfad(komposition, "priceByComponent", "tariff",
                  "priceByType", "rate") or {}
    hardware = _pfad(komposition, "priceByComponent", "hardware",
                     "priceByType", "rate") or {}
    t_monat = _preis(_pfad(tarif, "month", "withoutDiscounts", "gross"))
    t_einmalig = _preis(_pfad(tarif, "onetime", "withoutDiscounts", "gross"))
    h_monat = _preis(_pfad(hardware, "month", "withoutDiscounts", "gross"))
    h_einmalig = _preis(_pfad(hardware, "onetime", "withoutDiscounts", "gross"))
    if t_monat is None:
        # Ohne Tarifrate keine Buendelaussage - und der Ausfall wird
        # benannt, nicht verschluckt.
        log.info("Vodafone-Buendel: Komposition %s ohne Tarif-Monatsrate "
                 "- verworfen", hash_)
        return None

    if h_monat is not None and _gleich(t_monat + h_monat, gesamt):
        geraet_monatsrate = h_monat
    elif _gleich(t_monat, gesamt):
        # "financingType": "sub" - das Geraet steckt vollstaendig im
        # Tarifpreis, eine separate Rate wird nicht berechnet (Modulkopf).
        geraet_monatsrate = None
    else:
        log.info("Vodafone-Buendel: Komposition %s geht nicht auf "
                 "(Tarif %s + Geraet %s gegen Gesamtrate %s) - verworfen",
                 hash_, t_monat, h_monat, gesamt)
        return None                       # Summe geht nicht auf - verwerfen

    laufzeit = _laufzeit(komposition, geraet_monatsrate)
    if laufzeit is None:
        # BENANNTE LUECKE statt stillem Verlust: hier verschwindet ein
        # gemessenes Angebot, und der Grund steht im Protokoll.
        log.info("Vodafone-Buendel: Komposition %s ohne bestimmbare "
                 "Ratenlaufzeit (financingDuration %r, Geraeterate %r, "
                 "Ende der Geraeterate %r, Phasenenden %r) - verworfen",
                 hash_, komposition.get("financingDuration"),
                 geraet_monatsrate,
                 _pfad(komposition, "priceByComponent", "hardware",
                       "priceByType", "rate", "month", "withoutDiscounts",
                       "recurrenceEnd"),
                 [p.get("recurrenceEnd") for p in _perioden(komposition)])
        return None

    return {
        "titel": modell,
        "strukturierter_name": modell,
        "farbe": farbe,
        "speicher_gb": speicher,
        # Vodafones `hardwareId` - der Schluessel, ueber den
        # `loese_tarifnamen()` spaeter die Tarifschnittstelle je Geraet
        # GENAU EINMAL befragt (nicht je Rohsatz).
        "sku": hardware_id,
        # Kein Klarname in dieser Antwort (siehe Modulkopf) - nicht raten.
        "tarif_name": "",
        "tarif_slug": hash_,
        "tarif_monatlich": t_monat,
        "geraet_zuzahlung": h_einmalig,
        "geraet_monatsrate": geraet_monatsrate,
        "anschlusspreis": t_einmalig,
        "laufzeit_monate": laufzeit,
        "url": hubpage,
        "quelle": "vodafone_buendel",
    }


# `proben` ist die Schnittstelle der Provider-Probe (FM-2, P5 - siehe
# Adapter-Docstring in collect/geraete/__init__.py); dieser Adapter
# traegt keine Feld-Proben hinein.
def lies_buendel(text: str, url: str = "",
                 proben: Optional[dict] = None) -> list[dict]:
    """Aus DERSELBEN Detailnutzlast, die `lies()` liest, die Buendelsaetze.

    Kein eigener Abruf: `text` ist exakt die Antwort, die der Sammler fuer
    diese Seite ohnehin schon geholt hat (siehe Modulkopf, B1). Ein Geraet
    ohne lesbaren Modellnamen liefert eine leere Liste statt zu werfen -
    `lies()` hat auf derselben Seite bereits geworfen, wenn das der Fall
    waere, und diese Funktion soll keinen zweiten, redundanten Fehler
    melden.
    """
    daten = _json(text, "Geraetedetail (Buendel)")
    knoten = daten.get("data") if isinstance(daten.get("data"), dict) else daten
    modell = str(knoten.get("modelName") or "").strip()
    if not modell:
        return []

    hubpage = str(_pfad(knoten, "hubpage", "href") or "").strip()
    if hubpage.startswith("/"):
        hubpage = "https://www.vodafone.de" + hubpage

    out: list[dict] = []
    for atom in (knoten.get("atomics") or []):
        if not isinstance(atom, dict):
            continue
        hardware_id = str(atom.get("hardwareId") or "").strip()
        if not hardware_id:
            continue
        speicher = _speicher_gb(str(_pfad(atom, "capacity", "displayLabel") or ""))
        farbe = str(_pfad(atom, "color", "displayLabel") or "").strip()
        for eintrag in (_pfad(atom, "prices", "composition") or []):
            if not isinstance(eintrag, dict):
                continue
            satz = _buendelsatz_aus_komposition(
                modell, hubpage, hardware_id, farbe, speicher, eintrag)
            if satz is not None:
                out.append(satz)
    return out


# --------------------------------------------------------------------------
# TARIFNAMEN AUFLOESEN - siehe Modulkopf, Abschnitt B1
# --------------------------------------------------------------------------

def _hash_namen_aus_tarifantwort(text: str) -> dict:
    """offerCoreHash -> Tarifname aus `/glados/v2/tariff/v2/hardware`.

    Dieselbe `prices.composition`-Form wie in der Geraeteliste, nur je
    TARIF gruppiert und mit `tariffName` versehen - derselbe Hash, ein
    zweiter Endpunkt. Eine unlesbare oder leere Antwort ergibt ein leeres
    Woerterbuch, kein Fehler - der Aufrufer behandelt "nichts aufgeloest"
    ohnehin wie einen Nichttreffer.
    """
    try:
        daten = json.loads(text or "")
    except (json.JSONDecodeError, ValueError):
        return {}
    out: dict[str, str] = {}
    for eintrag in (_pfad(daten, "data") if isinstance(daten, dict) else None) or []:
        if not isinstance(eintrag, dict):
            continue
        for tarif in (eintrag.get("tariffs") or []):
            if not isinstance(tarif, dict):
                continue
            name = str(tarif.get("tariffName") or "").strip()
            if not name:
                continue
            for atom in (tarif.get("atomics") or []):
                if not isinstance(atom, dict):
                    continue
                for komposition in (_pfad(atom, "prices", "composition") or []):
                    if not isinstance(komposition, dict):
                        continue
                    h = str(komposition.get("offerCoreHash") or "").strip()
                    if h:
                        out[h] = name
    return out


# Derselbe Mindestabstand wie `rate_limit_sekunden` des Anbieters in
# `geraete_quellen.yaml` (2s) - diese Aufloesung ist ein ZUSAETZLICHER
# GET-Strom gegen denselben Host und soll ihn nicht haerter treffen als
# der Hauptabruf.
_TARIF_RATE_LIMIT = 2.0


def loese_tarifnamen(hole: Callable, kopfzeilen: dict, rohbuendel: list) -> int:
    """Fuellt `tarif_name` in bereits gesammelten Buendel-Rohsaetzen.

    EIN GET je eindeutiger `sku` (= Vodafones `hardwareId`), nicht je
    Rohsatz - ein Geraet traegt bis zu vier Kompositionen, die alle in
    derselben Tarifantwort stehen. Nicht von `lies_buendel()` selbst
    aufgerufen: ein Adapter bleibt ein reiner Text-zu-Daten-Uebersetzer
    ohne eigenes Netz (siehe Modulkopf); diese Funktion wird von der
    Pipeline ueber `Adapter.loese_tarifnamen` aufgerufen, NACHDEM alle
    Anbieter gesammelt sind.

    Mutiert die Eintraege in `rohbuendel` in place (dieselben dict-Objekte,
    die auch in `Anbieterbilanz.buendel` stehen) und gibt die Zahl der neu
    aufgeloesten Saetze zurueck. Ein Hash, der in der Tarifantwort nicht
    steht, bleibt unveraendert bei `tarif_name=""` - nicht raten.
    """
    ziele = sorted({
        str(r.get("sku") or "").strip()
        for r in rohbuendel
        if r.get("quelle") == "vodafone_buendel"
        and not str(r.get("tarif_name") or "").strip()
        and str(r.get("sku") or "").strip()
    })
    aufgeloest = 0
    letzter = 0.0
    for hwid in ziele:
        warte = _TARIF_RATE_LIMIT - (time.monotonic() - letzter)
        if letzter and warte > 0:
            time.sleep(warte)
        letzter = time.monotonic()
        url = (f"https://api.vodafone.de/glados/v2/tariff/v2/hardware"
              f"?hardwareId={hwid}&{_PARAMETER}")
        try:
            status, text = hole(url, kopfzeilen=kopfzeilen)
        except Exception:                                 # noqa: BLE001
            continue
        if not (200 <= int(status) < 300):
            continue
        namen = _hash_namen_aus_tarifantwort(text)
        if not namen:
            continue
        for r in rohbuendel:
            if r.get("sku") != hwid or str(r.get("tarif_name") or "").strip():
                continue
            name = namen.get(str(r.get("tarif_slug") or "").strip())
            if name:
                r["tarif_name"] = name
                aufgeloest += 1
    return aufgeloest
