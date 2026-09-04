"""o2: der Katalog, den die Einstiegsseite selbst abruft.

DER WEG, GEMESSEN AM 28.08.2026
-------------------------------
Der Befund vom 11.08.2026 bleibt richtig: das ld+json der Produktseite traegt
`"price":"1.00"`, also den Lockpreis im Tarifbuendel, und die Einstiegsseite
hat ueberhaupt kein Produktschema. Der belastbare Katalog liegt hinter

    GET /e-shop/rest/catalog/o2shop/privatkunden/ratenzahlung/default/
        __not-specified__/__not-specified__/__not-specified__?hwOnly=true
    Accept: application/vnd.commerce.message+json

Diese vollstaendige Adresse samt Medientyp steht woertlich in der Nutzlast
von /e-shop/ - die Seite ruft sie selbst auf. Sie liefert 93 Geraete mit
Preis in EINER Antwort; es wird keine Produktseite nachgeladen und keine ID
hochgezaehlt.

ROBOTS.TXT: DIE SPERRE STEHT IN DER GOOGLEBOT-GRUPPE, NICHT IN UNSERER
----------------------------------------------------------------------
o2online.de fuehrt zwei Gruppen. `User-agent: *` - die fuer uns gueltige -
sperrt /auth/, /login/, /aktionen/, /postpaid/ und weitere, aber NICHT
/e-shop/rest/. Erst die Gruppe `User-agent: googlebot` nennt
`Disallow: /e-shop/rest/`, zusammen mit /chat-ui/, /ebooking/ und
/benefit-service/ - das Muster einer Suchmaschinen-Hygiene, nicht einer
Crawlersperre. Unser Absender ist `TelcoRadar/1.0`, also gilt die
`*`-Gruppe; `lies_robots()` liest genau die und keine andere.

Diese Unterscheidung steht hier ausgeschrieben, weil sie das Gegenteil der
sonstigen Annahme dieses Projekts ist: der Modulkopf von `robots.py` nennt
`*` "die strengere und immer gueltige Lesart". Bei o2 ist die Googlebot-
Gruppe die strengere. Wer die Regel spaeter verschaerfen will, findet hier,
was zu entscheiden ist - und `grund` auf /geraete-quellen.html sagt es dem
Leser.

ZWEI FALLEN IN DIESEM KATALOG
-----------------------------
1. **Zubehoerbuendel.** 18 der 93 Eintraege sind Geraet PLUS Zubehoer
   ("Apple iPhone 17 Pro Max mit Watch Ultra 3", 2323 EUR). Der Preis gilt
   fuer beides zusammen; als Geraetepreis gespeichert waere er um den Wert
   einer Smartwatch zu hoch. Sie werden verworfen, nicht korrigiert - was
   der Zubehoerpreis ist, steht nirgends.
2. **`oneTimePrice` ist die Anzahlung, nicht der Preis.** Der Geraetepreis
   ist `totalPrice`, und er ist nachrechenbar: Anzahlung plus 24 Monatsraten
   (gemessen: 92 von 93 Eintraegen gehen exakt auf). Wer `oneTimePrice`
   naehme, schriebe 1 EUR in die Preisspalte - genau den Lockpreis, den der
   Waechter draussen haelt.

DIE ZAHL IST KEIN BARPREIS (ergaenzt am 03.09.2026)
---------------------------------------------------
`totalPrice` ist der Gesamtbetrag eines Teilzahlungsgeschaefts, nicht der
Preis an einer Kasse. Das iPhone 14 128 GB mitternacht steht mit
`oneTimePrice: 1`, `monthlyPrice: 30.0`, `totalPrice: 721.0` im Katalog, und
die verlinkte Produktseite sagt es woertlich: "Geraet Anzahlung: 1,00 EUR",
"(Gesamtpreis Geraet: 721,00 EUR)". Bis zum 03.09.2026 stand diese Zahl in
derselben Spalte wie freenets Barpreis von 949,00 EUR - gleiche Optik, andere
Groesse.

Deshalb liest dieser Adapter jetzt die ganze Struktur und nicht nur die
Summe: `anzahlung`, `monatsrate` und `laufzeit_monate`. Die Laufzeit steht im
Angebotsnamen (`...-24xhigh`), also in der Quelle selbst - sie wird nicht aus
Summe und Rate zurueckgerechnet, denn ein Ergebnis, das nur ZUFAELLIG
aufgeht, waere geraten. Geht die Probe `anzahlung + n * rate == totalPrice`
nicht auf, wird die Laufzeit verworfen und die Zahl steht unetikettiert da -
lieber kein Etikett als ein falsches.

`zins_effektiv` traegt die 0.0, weil o2 sie auf der Produktseite als
gesetzlichen Finanzierungshinweis ausweist ("Der Sollzins liegt bei 0 %, der
effektive Jahreszins bei 0 %"). Sie ist damit belegt, nicht angenommen; ein
Anbieter ohne diesen Nachweis bekaeme hier `None`.

Die Preishistorie bleibt davon unberuehrt: gespeichert wird weiterhin
`totalPrice`, und kein Preispunkt aus einem frueheren Lauf wird umgedeutet.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from . import GeraeteAbrufFehler
from ...geraete_model import probe_geht_auf

# "privatkunden-google-pixel-11-pro-xl-256gb-canyon-24xhigh"
#   -> Speicher 256, Farbe "canyon"
# Der Modellname kommt NICHT von hier, sondern aus `description` - der
# Angebotsname ist ein Slug, und aus einem Slug ein Modell zu raten ist
# genau die Titel-Hasherei, die Teil E verbietet.
_OFFER_RE = re.compile(
    r"^[a-z]+-(?P<slug>.+?)-(?P<gb>\d+)gb-(?P<farbe>.+?)-\d+x\w+$")

# Ein Zubehoerbuendel erkennt man am " mit " im ANGEBOTSNAMEN. Gemessen an
# den 93 Eintraegen vom 28.08.2026: 18 Treffer, alle echt (Watch, Buds,
# Headphone, Pad, Tab). Geprueft wird auf `description` UND `offerName` -
# "Xiaomi 17 Ultra mit Redmi Pad 2" traegt das Wort nur in der Beschreibung.
_BUENDEL_RE = re.compile(r"\bmit\b", re.IGNORECASE)


# Die Ratenzahl steht am Ende des Angebotsnamens: "...-mitternacht-24xhigh".
# Bewusst ein EIGENER Ausdruck neben `_OFFER_RE` und nicht dessen Gruppe:
# `_OFFER_RE` verlangt den ganzen Slug samt Speicher und Farbe. Ein Eintrag,
# dessen Name davon abweicht, verliert dann Speicher und Farbe - er soll
# deswegen aber nicht auch noch seine Preisform verlieren.
_RATEN_RE = re.compile(r"-(?P<raten>\d+)x\w+$")


def _preis(wert) -> Optional[float]:
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def _laufzeit(angebot: str, anzahlung: Optional[float],
              monatsrate: Optional[float],
              gesamt: Optional[float]) -> Optional[int]:
    """Die Ratenzahl aus dem Angebotsnamen - aber nur, wenn sie aufgeht.

    Die Zahl kommt aus der Quelle, die Rechenprobe entscheidet, ob sie
    benutzt wird: `anzahlung + n * rate == totalPrice` (Toleranz ein Cent).
    Das ist dieselbe Kontrolle, die der Modulkopf seit dem 28.08.2026 als
    Messbefund nennt - hier wird sie zur Bedingung, statt nur protokolliert
    zu werden. Faellt sie durch, gibt es kein Etikett; die Zahl bleibt, was
    sie ist, und behauptet nur nichts mehr ueber ihre Form.

    Gerechnet wird sie in `geraete_model.probe_geht_auf` und nur dort - der
    Ratengesamtbetrag im Buendel (`tco_model`) prueft mit derselben Zeile.
    Hier steht das, was NUR fuer o2 gilt: dass die Ratenzahl im
    Angebotsnamen steht.
    """
    m = _RATEN_RE.search(angebot or "")
    if not m:
        return None
    raten = int(m.group("raten"))
    if not probe_geht_auf(anzahlung, monatsrate, raten, gesamt):
        return None
    return raten


def lies(text: str, url: str = "") -> list[dict]:
    """Den Katalog in Rohsaetze zerlegen. Die Einstiegsseite IST die Nutzlast."""
    try:
        daten = json.loads(text or "")
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(f"o2-Katalog unlesbar: {exc}") from exc
    if not isinstance(daten, dict) or "hardware" not in daten:
        raise GeraeteAbrufFehler("o2-Katalog ohne Feld 'hardware'")

    out: list[dict] = []
    for h in (daten.get("hardware") or []):
        if not isinstance(h, dict):
            continue
        modell = str(h.get("description") or "").strip()
        angebot = str(h.get("offerName") or "").strip()
        if not modell:
            continue
        if _BUENDEL_RE.search(modell) or _BUENDEL_RE.search(angebot):
            continue                      # Geraet plus Zubehoer, siehe Modulkopf

        preisblock = h.get("price") or {}
        preis = _preis(preisblock.get("totalPrice"))
        if preis is None:
            continue

        m = _OFFER_RE.match(angebot)
        speicher = int(m.group("gb")) if m else None
        farbe = m.group("farbe").replace("-", " ").strip() if m else ""

        anzahlung = _preis(preisblock.get("oneTimePrice"))
        monatsrate = _preis(preisblock.get("monthlyPrice"))
        laufzeit = _laufzeit(angebot, anzahlung, monatsrate, preis)

        # Die Seite, die ein Mensch aufrufen kann - sie traegt in ihrer
        # eigenen Adresse `ohne-tarif=ja`, also genau die Preisart, die hier
        # gespeichert wird.
        ziel = ((h.get("detailWwwAbsoluteCall") or {}).get("constantPayload")
                or {}).get("link") or {}
        out.append({
            "titel": " ".join(x for x in (modell,
                                          f"{speicher} GB" if speicher else "",
                                          farbe) if x),
            "preis": preis,
            # Die Preisform, aus der Quelle gelesen - siehe Modulkopf.
            "anzahlung": anzahlung if laufzeit else None,
            "monatsrate": monatsrate if laufzeit else None,
            "laufzeit_monate": laufzeit,
            "zins_effektiv": 0.0 if laufzeit else None,
            "waehrung": "EUR",
            "verfuegbarkeit": "unbekannt",
            "sku": str(h.get("externalId") or "").strip(),
            "ean": "",
            "farbe": farbe,
            "speicher_gb": speicher,
            "url": str(ziel.get("uri") or "").strip(),
            "quelle": "o2_katalog",
        })
    return out


# --------------------------------------------------------------------------
# DER BUENDELKATALOG - dieselbe Adresse, ein Parameter weniger
# --------------------------------------------------------------------------
# GEMESSEN AM 04.09.2026
# ----------------------
# `/e-shop/` gibt die Katalogadresse in ZWEI Fassungen aus, beide woertlich
# in seiner eigenen Nutzlast:
#
#     .../__not-specified__?hwOnly=true     95 Geraete OHNE Tarif
#     .../__not-specified__                 88 Geraete MIT Tarif
#
# Es ist derselbe Pfad und derselbe Umschalter, den die Seite ihren Lesern
# anbietet: die Antwort sagt selbst, in welchem Zustand sie steht
# (`hwCatalogSwitcherStateValue.hwOnlyOrBundleState` = `HW_ONLY` bzw.
# `BUNDLE`, `showSwitcher: true`). Es wird also kein Parameter erraten und
# keine Kombinatorik durchprobiert - die zweite Adresse steht in der
# Konfiguration, weil o2 sie in seiner ersten ausliefert.
#
# Der Buendeleintrag traegt, was ein `tco_model.Buendel` braucht:
#
#     price.oneTimePrice     1,00 EUR   Geraetezuzahlung
#     price.monthlyPrice    60,49 EUR   Geraeterate PLUS Tarif, zusammen
#     price.activationFee   39,99 EUR   Anschlusspreis
#     rateDurationValue     36 Monate   Laufzeit der Geraeteraten
#     bundle.tariffName     "O<sub>2</sub> Mobile L Plus mit 150 GB+ (24 Mon.)"
#     bundle.tariffOfferName "privatkunden-o2-mobile-l-plus-online-hwv"
#
# DIE AUFTEILUNG STEHT IM TRACKINGBLOCK - UND SIE WIRD NACHGERECHNET
# ------------------------------------------------------------------
# `monthlyPrice` ist die SUMME aus Geraeterate und Tarif. Getrennt stehen
# die zwei nur in `ecommerceProductValue.attributes`, dem Block, mit dem die
# Seite ihre Webanalyse fuettert:
#
#     metric3  "40.5"   Geraet mtl.
#     metric2  "19.99"  Tarif mtl.
#     metric5  "1"      Anzahlung
#     metric4  "0.0"    Anschlusspreis
#     dimension59 "o2-mobile-l-plus"   der Tarif-Slug
#
# Ein Trackingfeld ist kein Preisfeld, und deshalb wird ihm hier nichts
# geglaubt, was sich nicht gegen die TYPISIERTEN Zahlen derselben Antwort
# nachrechnen laesst. Drei Proben, alle drei Bedingung:
#
#     metric3 + metric2 == price.monthlyPrice
#     metric5           == price.oneTimePrice
#     metric4           == price.activationFee
#
# Ueber die 66 Buendel des Messtags gehen alle drei bei 66 von 66 auf. Geht
# eine nicht auf, wird der Satz verworfen - ein Trackingblock, der der
# Preisstruktur widerspricht, ist keine Messung, sondern ein geaendertes
# Nutzlastformat.
#
# Zusaetzlich gegengeprueft an den Produktseiten, die o2 selbst verlinkt:
# acht `-details?tarif=...`-Seiten tragen serverseitig einen
# `pdp:PriceSummaryValue` mit den Zeilen "Geraet mtl. (36 Raten)" und
# "Tarif mtl. (Mindestlaufzeit 24 Monate)". Bei sieben von acht (die achte
# fuehrt der Katalog unter anderem Namen) stimmen die Betraege auf den Cent
# mit metric3/metric2 ueberein. Die Detailseiten werden im Betrieb NICHT
# abgerufen: 66 Seiten a rund 950 KB waeren 63 MB je Nacht fuer eine
# Aufteilung, die schon in der einen Katalogantwort steht.
#
# WAS DER TARIFBETRAG IST - UND WAS NICHT
# ---------------------------------------
# 19,99 EUR ist der Tarifpreis IN DIESEM BUENDEL. Die SIM-only-Kachel
# desselben Tarifs nennt 24,99 EUR; o2 sagt auf der Produktseite selbst,
# dass es zum Geraeteratenplan "einen attraktiven monatlichen Rabatt auf
# deinen Tarif" gibt. Beide Zahlen stehen im Bestand, und die Differenz ist
# genau die Auskunft, um die es geht - `Geraeteanteil` zieht die eine TCO
# von der anderen ab. Hier wird deshalb NICHT der Kachelpreis eingesetzt
# und auch kein Rabatt daraus gerechnet: gespeichert wird, was fuer dieses
# Buendel zu zahlen ist.
#
# Die Zubehoerbuendel werden mit derselben Regel verworfen wie im
# Geraetekatalog (` mit ` in Beschreibung oder Angebotsname): 22 der 88.
# Ihr Preis gilt fuer Geraet PLUS Zubehoer, und was der Zubehoerteil ist,
# steht nirgends.

# "36 Monate" - mit geschuetztem Leerzeichen in der Quelle.
_DAUER_RE = re.compile(r"(\d+)")

# Die Trackingfelder tragen HTML: "O<sub>2</sub> Mobile L Plus mit 150 GB+".
# Der Tarifname wandert in `Buendel.tarif_name` und von dort auf die Seite;
# ein `<sub>` im Datenfeld waere dort entweder sichtbares Markup oder eine
# stille Abhaengigkeit von der Escaping-Regel der Vorlage.
_TAG_RE = re.compile(r"<[^>]+>")


def _ohne_markup(text: str) -> str:
    return " ".join(_TAG_RE.sub("", text or "").split())


def _gleich(a: Optional[float], b: Optional[float]) -> bool:
    """Ein Cent ist kein Rundungsfehler - dieselbe Toleranz wie ueberall."""
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) < 0.005


def _buendelsatz(h: dict) -> Optional[dict]:
    """Ein Katalogeintrag wird ein Buendel-Rohsatz - oder nichts."""
    modell = str(h.get("description") or "").strip()
    angebot = str(h.get("offerName") or "").strip()
    if not modell:
        return None
    if _BUENDEL_RE.search(modell) or _BUENDEL_RE.search(angebot):
        return None                       # Geraet plus Zubehoer

    buendel = h.get("bundle") or {}
    tarif_name = _ohne_markup(buendel.get("tariffName") or "")
    if not tarif_name:
        # Ohne Tarif ist eine Buendelzahl bedeutungslos - dieselbe Regel
        # wie in `geraete_model.Listung` und `tco_model.Buendel`.
        return None

    preisblock = h.get("price") or {}
    gesamt = _preis(preisblock.get("totalPrice"))
    monatlich = _preis(preisblock.get("monthlyPrice"))
    anzahlung = _preis(preisblock.get("oneTimePrice"))
    anschluss = _preis(preisblock.get("activationFee"))

    dauer = _DAUER_RE.search(str(h.get("rateDurationValue") or ""))
    laufzeit = int(dauer.group(1)) if dauer else None
    if laufzeit is None or not probe_geht_auf(anzahlung, monatlich,
                                              laufzeit, gesamt):
        # Dieselbe Probe wie beim Geraetekatalog, hier auf der Summe aus
        # Rate und Tarif. Geht sie nicht auf, stimmt die Laufzeit nicht -
        # und ohne Laufzeit ist eine Monatszahl keine Aussage.
        return None

    werte = (h.get("ecommerceProductValue") or {}).get("attributes") or {}
    geraet_rate = _preis(werte.get("metric3"))
    tarif_rate = _preis(werte.get("metric2"))
    if geraet_rate is None or tarif_rate is None:
        return None
    # Die drei Proben aus dem Modulkopf. Sie sind Bedingung, nicht Protokoll.
    if not _gleich(geraet_rate + tarif_rate, monatlich):
        return None
    if not _gleich(_preis(werte.get("metric5")), anzahlung):
        return None
    if not _gleich(_preis(werte.get("metric4")), anschluss):
        return None

    m = _OFFER_RE.match(angebot)
    speicher = int(m.group("gb")) if m else None
    farbe = m.group("farbe").replace("-", " ").strip() if m else ""
    ziel = ((h.get("detailWwwAbsoluteCall") or {}).get("constantPayload")
            or {}).get("link") or {}
    return {
        "titel": " ".join(x for x in (modell,
                                      f"{speicher} GB" if speicher else "",
                                      farbe) if x),
        "farbe": farbe,
        "speicher_gb": speicher,
        "sku": str(h.get("externalId") or "").strip(),
        "tarif_name": tarif_name,
        # Der Slug, ueber den `tarif_bezug.ueber_slug` aufloest. Er steht im
        # Katalog am Buendel und in der SIM-only-Kachel am Link "Handy
        # hinzufuegen" - o2 stellt die Verbindung her, nicht dieses Modul.
        "tarif_slug": str(werte.get("dimension59") or "").strip(),
        "tarif_monatlich": tarif_rate,
        "geraet_zuzahlung": anzahlung,
        "geraet_monatsrate": geraet_rate,
        "anschlusspreis": anschluss,
        "laufzeit_monate": laufzeit,
        "url": str(ziel.get("uri") or "").strip(),
        "quelle": "o2_buendel",
    }


def lies_buendel(text: str, url: str = "") -> list[dict]:
    """Den Buendelkatalog in Rohsaetze zerlegen.

    Wirft, wenn die Antwort gar keine Buendelantwort ist. Das ist NICHT
    dasselbe wie "keine Buendel gefunden": eine Antwort im Zustand
    `HW_ONLY` an dieser Stelle heisst, dass der Umschalter sich geaendert
    hat, und ihre Geraete als Buendel zu lesen ergaebe 95 Saetze ohne
    Tarif. Ein leeres Ergebnis waere dafuer die falsche Meldung - dieselbe
    Unterscheidung wie bei `GeraeteAbrufFehler` ueberall sonst.
    """
    try:
        daten = json.loads(text or "")
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(f"o2-Buendelkatalog unlesbar: {exc}") from exc
    if not isinstance(daten, dict) or "hardware" not in daten:
        raise GeraeteAbrufFehler("o2-Buendelkatalog ohne Feld 'hardware'")

    zustand = (((daten.get("hwCatalogSwitcherStateValue") or {})
                .get("hwOnlyOrBundleSwitcherValue") or {})
               .get("hwOnlyOrBundleState") or {}).get("name")
    if zustand != "BUNDLE":
        raise GeraeteAbrufFehler(
            f"o2-Katalog steht auf {zustand!r} statt 'BUNDLE' - diese "
            f"Antwort traegt keine Tarifbuendel")

    out: list[dict] = []
    for h in (daten.get("hardware") or []):
        if not isinstance(h, dict):
            continue
        satz = _buendelsatz(h)
        if satz is not None:
            out.append(satz)
    return out
