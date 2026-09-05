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
import re
import time
from typing import Callable, Optional
from urllib.parse import urlsplit

from . import GeraeteAbrufFehler

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


def _periode0(komposition: dict) -> Optional[dict]:
    """Die ERSTE Phase von `totalMonthlyRatePrice` - die, gegen die die
    Komponentenbetraege (`recurrenceStart: 1`) nachgerechnet werden. Eine
    Ratenlaufzeit ueber 24 Monate hinaus (financingDuration 36) traegt eine
    ZWEITE, niedrigere Phase (nur noch die Geraeterate) - die zaehlt hier
    nicht mit, sie ist keine zusaetzliche Messung, sondern derselbe Vertrag
    in seinem zweiten Abschnitt."""
    perioden = _pfad(komposition, "totalMonthlyRatePrice", "withoutDiscounts")
    if not isinstance(perioden, list) or not perioden:
        return None
    erste = perioden[0]
    return erste if isinstance(erste, dict) else None


def _buendelsatz_aus_komposition(modell: str, hubpage: str, hardware_id: str,
                                 farbe: str, speicher: Optional[int],
                                 komposition: dict) -> Optional[dict]:
    """Eine Komposition wird ein Buendel-Rohsatz - oder nichts, siehe
    Modulkopf (die Rechenprobe entscheidet, nicht `financingType`)."""
    hash_ = str(komposition.get("offerCoreHash") or "").strip()
    if not hash_:
        return None

    periode = _periode0(komposition)
    gesamt = _preis((periode or {}).get("gross")) if periode else None
    if gesamt is None:
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
        return None                       # ohne Tarifrate keine Buendelaussage

    if h_monat is not None and _gleich(t_monat + h_monat, gesamt):
        geraet_monatsrate = h_monat
    elif _gleich(t_monat, gesamt):
        # "financingType": "sub" - das Geraet steckt vollstaendig im
        # Tarifpreis, eine separate Rate wird nicht berechnet (Modulkopf).
        geraet_monatsrate = None
    else:
        return None                       # Summe geht nicht auf - verwerfen

    laufzeit = komposition.get("financingDuration")
    try:
        laufzeit = int(laufzeit)
    except (TypeError, ValueError):
        laufzeit = None
    if not laufzeit:
        # Ohne eigene Ratenlaufzeit (financingType "sub") gilt die Phase,
        # fuer die dieser Preis genannt wird - die Vertragsmindestlaufzeit.
        ende = (periode or {}).get("recurrenceEnd")
        try:
            laufzeit = int(ende)
        except (TypeError, ValueError):
            laufzeit = None
    if not laufzeit or laufzeit <= 0:
        return None

    return {
        "titel": modell,
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


def lies_buendel(text: str, url: str = "") -> list[dict]:
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
