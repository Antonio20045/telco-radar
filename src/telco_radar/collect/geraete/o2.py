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
   der Zubehoerpreis ist, steht nirgends. Erkannt wird ein solches Buendel
   am Angebotsnamen, nicht an der Beschreibung: "mit" NUR in der
   Beschreibung ist eine Gratiszugabe zum nackten Geraet (siehe
   `_BUENDEL_RE`, gemessen am 29.09.2026). Belege: Pixel 11 Pro „mit
   Fitbit Charge 6“ kostet 1189 EUR wie das nackte Geraet, das echte Paket
   mit Pixel Watch 5 1333 EUR; das Galaxy S25 FE „mit Tab S10 FE“ (Katalog
   vom 04.09.) kostete 775 EUR, genau so viel wie am 29.09. das S25 FE ohne
   Zugabe. Fehlt der Angebotsname, entscheidet die Beschreibung (streng).
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
import logging
import re
from typing import Optional

from . import GeraeteAbrufFehler
from ...geraete_model import probe_geht_auf

log = logging.getLogger(__name__)

# "privatkunden-google-pixel-11-pro-xl-256gb-canyon-24xhigh"
#   -> Speicher 256, Farbe "canyon"
# Der Modellname kommt NICHT von hier, sondern aus `description` - der
# Angebotsname ist ein Slug, und aus einem Slug ein Modell zu raten ist
# genau die Titel-Hasherei, die Teil E verbietet.
#
# TERABYTE (29.09.2026): "privatkunden-apple-iphone-18-pro-1tb-burgunder-
# 36xhigh". Ohne die Einheit fielen 1 TB und 2 TB beide auf
# `ohne-speicher` und damit auf DIESELBE sku_id - zwei Preise, ein
# Schluessel. Gezaehlt wird wie in `geraete_model` (1 TB = 1024 GB).
_OFFER_RE = re.compile(
    r"^[a-z]+-(?P<slug>.+?)-(?P<zahl>\d+)(?P<einheit>gb|tb)-(?P<farbe>.+?)"
    r"-\d+x\w+$")


def _speicher(m) -> Optional[int]:
    if not m:
        return None
    return int(m.group("zahl")) * (1024 if m.group("einheit") == "tb" else 1)

# Ein Zubehoerbuendel erkennt man am "-mit-" im ANGEBOTSNAMEN - der Name
# des Artikels, den o2 verkauft ("...-17-pro-256gb-tiefblau-mit-watch-ultra-
# 3-schwarz-ocean-36xhigh"). Gemessen an den 93 Eintraegen vom 28.08.2026:
# 18 Treffer, alle echt (Watch, Buds, Headphone, Pad, Tab). Die
# Beschreibung allein zaehlt NICHT, in beide Richtungen:
#   * "Samsung Galaxy Z Fold8 + Watch Ultra2" traegt kein "mit", der
#     Angebotsname schon ("...-mit-watch-ultra-2-36xhigh") - verworfen.
#   * "Google Pixel 11 Pro mit Fitbit Charge 6" und "Xiaomi 17 Ultra mit
#     Redmi Pad 2" tragen es NUR in der Beschreibung; ihr Angebotsname ist
#     der des nackten Geraets. Das ist eine Gratiszugabe, kein Buendel -
#     gemessen am 29.09.2026 an den Produktseiten, die der Katalog selbst
#     verlinkt: "erhalte die Fitbit Charge 6 ... kostenlos dazu" (Pixel 11
#     Pro, Registrierung im Hardware-Extra-Portal, bis 06.10.2026) und
#     "Xiaomi 17 Ultra mit gratis Redmi Pad 2". Der Geraetepreis ist der
#     des Geraets: Pixel 11 Pro 256 GB 1.189,00 EUR gegen 1.333,00 EUR fuer
#     den echten Artikel "...-mit-pixel-watch-5-..." derselben Antwort.
#     Bis zum 29.09.2026 fiel das Pixel 11 Pro dadurch bei o2 ganz heraus
#     (Pflichtmodell ohne Buendel im Abdeckungswaechter).
# Die Zugabe wird aus dem Modellnamen gestrichen (`_ohne_zugabe`), sonst
# faende der Katalog das Geraet nicht.
_BUENDEL_RE = re.compile(r"\bmit\b", re.IGNORECASE)
_ZUGABE_RE = re.compile(r"\s+mit\s+.*$", re.IGNORECASE)


def _ist_zubehoerbuendel(angebot: str, beschreibung: str) -> bool:
    """Geraet plus Zubehoer? Entschieden am Angebotsnamen. Fehlt er (ein
    geaendertes Nutzlastformat), gilt die alte, strengere Probe auf der
    Beschreibung: lieber eine Gratiszugabe verworfen als einen
    Paketpreis still als Geraetepreis gespeichert."""
    if not angebot:
        return bool(_BUENDEL_RE.search(beschreibung))
    return bool(_BUENDEL_RE.search(angebot))


def _ohne_zugabe(beschreibung: str) -> str:
    """Der Modellname ohne die Gratiszugabe: "Google Pixel 11 Pro mit Fitbit
    Charge 6" -> "Google Pixel 11 Pro". Nur fuer Eintraege, deren
    Angebotsname KEIN Zubehoerbuendel ist - siehe `_BUENDEL_RE`."""
    return _ZUGABE_RE.sub("", beschreibung).strip()


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
        if _ist_zubehoerbuendel(angebot, modell):
            continue                      # Geraet plus Zubehoer, siehe Modulkopf
        modell = _ohne_zugabe(modell)

        preisblock = h.get("price") or {}
        preis = _preis(preisblock.get("totalPrice"))
        if preis is None:
            continue

        m = _OFFER_RE.match(angebot)
        speicher = _speicher(m)
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
            # E4-Auto-Erkennung: der strukturierte NAME (Feld `description`),
            # getrennt vom zusammengesetzten Titel.
            "strukturierter_name": modell,
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
# WAS DER TARIFBETRAG IST - UND WAS NICHT (Stand P0-B-h5, 21.09.2026)
# ------------------------------------------------------------------------
# 19,99 EUR (Beispiel "O2 Mobile on Demand M Plus") ist der Tarifpreis IN
# DIESEM BUENDEL. Die SIM-only-Kachel DESSELBEN Tarifs (aufgeloest ueber
# den Slug, siehe `tco_buendel.py`) nennt je Geraet 19,99/24,99/... EUR,
# und o2 nennt die Differenz auf der Produktseite selbst "einen
# attraktiven monatlichen Rabatt auf deinen Tarif". Der Betrag ist
# gemessen: bei diesem Geraeteratenplan 19,99 statt 24,99 SIM-only, also
# -5,00 EUR im Monat.
#
# DIESE DIFFERENZ IST DER PREIS UND KEIN ABZUG. Das ist die Lesart seit
# P0-B-fix1 und sie steht ausgeschrieben in `analyze/tco_buendel.py`
# ("KEIN BETRAG WIRD UMGERECHNET"): "der Anbieter sagt Rabatt" ist nicht
# dasselbe wie "bedingter Nachlass". Wer die -5,00 EUR als
# `tco_model.Rabatt` neben den Betrag legt, weist eine Ersparnis aus, die
# mit diesem Ratenplan niemand mehr holen kann, und hebt die Leitzahl
# aller 72 o2-Buendel um 120,00 bis 276,00 EUR, ohne dass sich ein
# o2-Preis geaendert hat. Genau das war fuer einen Tag eingebaut und ist
# zurueckgenommen.
#
# Dieser Adapter speichert deshalb den GEMESSENEN Buendelbetrag
# (`tarif_monatlich`, das, was fuer DIESES Buendel zu zahlen ist) und
# rechnet nichts um. Er fuehrt dazu auch KEIN Deutungsflag mehr: bis
# P0-B-h5 hing an jedem Rohsatz ein `tarif_rabatt_beleg=True`, dessen
# einziger Leser mit der Ruecknahme entfallen war. Ein Feld ohne Leser,
# dessen Beschreibung eine Vertragsstelle nennt, die es nicht mehr gibt,
# ist die Bauanleitung fuer denselben Fehler - der BETRAG gehoert
# dokumentiert (oben), die Deutung nicht in ein Datenfeld.
#
# Was der SIM-only-Preis desselben Tarifs leistet, leistet er anderswo:
# als Massstab in `analyze/tarif_referenzen.py` und als Geraeteanteil in
# `tco_model.geraeteanteil()` - dort steht die Differenz als Differenz.
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


def _buendelsatz(h: dict, proben: Optional[dict] = None) -> Optional[dict]:
    """Ein Katalogeintrag wird ein Buendel-Rohsatz - oder nichts.

    `proben` ist der Zaehler der PROVIDER-PROBE (FM-2, P5-Auftrag 2): er
    wird VOR jedem Verwurf erhoeht, solange der Satz die Felder UEBERHAUPT
    tragen sollte (kein Zubehoer, Tarifname da). So misst der Lauf jede
    Nacht, ob die Feldstruktur der Antwort noch stimmt - auch wenn am Ende
    kein Satz uebrig bleibt. Auch der TOTALTOD des Referenzfeldes ist eine
    GESCHEITERTE Probe (monthlyPrice komplett weg - P5-Codepruefung S2-1):
    die drei metric-Ebenen haengen an dieser Referenz, ohne sie waere
    "kein Kandidat" die Meldung "Schnittstelle umbau, niemand sieht eine
    Zeile". Die drei Proben selbst sind unveraendert Bedingung, nicht
    Protokoll.
    """
    modell = str(h.get("description") or "").strip()
    angebot = str(h.get("offerName") or "").strip()
    if not modell:
        return None
    if _ist_zubehoerbuendel(angebot, modell):
        return None                       # Geraet plus Zubehoer
    modell = _ohne_zugabe(modell)

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

    werte = (h.get("ecommerceProductValue") or {}).get("attributes") or {}
    geraet_rate = _preis(werte.get("metric3"))
    tarif_rate = _preis(werte.get("metric2"))

    # DIE PROVIDER-PROBE - Existenz-Schwelle ueber die Feldstruktur. Sie
    # zaehlt JE Kandidat, ob die drei Feldebenen noch da sind und
    # zusammenpassen; ein fehlender Referenzbetrag (oneTimePrice weg,
    # activationFee weg) ist dabei eine GESCHEITERTE Probe, kein
    # ungeeigneter Kandidat - genau das Verschwinden soll sie ja melden.
    # Dasselbe gilt fuer monthlyPrice SELBST (S2-1 der P5-Codepruefung):
    # fehlt die Referenz, entfaellt der Satz als "monthlyPrice"-Ebene -
    # die metric-Vergleiche sind ohne Referenz nicht pruefbar und werden
    # nicht zusätzlich als gescheitert gezaehlt (die Ebene, die weg ist,
    # heisst der Grund). Zaehlung VOR der Laufzeitprobe: die Probe misst
    # die Felder, nicht die Satzannahme (dafuer steht die Buendelzeile
    # der Pipeline).
    if proben is not None:
        proben["kandidaten"] = int(proben.get("kandidaten", 0)) + 1
        fehlend: list[str] = []
        if monatlich is None:
            fehlend.append("monthlyPrice")
        else:
            if geraet_rate is None or tarif_rate is None \
                    or not _gleich(geraet_rate + tarif_rate, monatlich):
                fehlend.append("metric3+metric2")
            if anzahlung is None or not _gleich(_preis(werte.get("metric5")),
                                                anzahlung):
                fehlend.append("metric5")
            if anschluss is None or not _gleich(_preis(werte.get("metric4")),
                                                anschluss):
                fehlend.append("metric4")
        if fehlend:
            for name in fehlend:
                proben[name] = int(proben.get(name, 0)) + 1
        else:
            proben["bestanden"] = int(proben.get("bestanden", 0)) + 1

    dauer = _DAUER_RE.search(str(h.get("rateDurationValue") or ""))
    laufzeit = int(dauer.group(1)) if dauer else None
    if laufzeit is None or not probe_geht_auf(anzahlung, monatlich,
                                              laufzeit, gesamt):
        # Dieselbe Probe wie beim Geraetekatalog, hier auf der Summe aus
        # Rate und Tarif. Geht sie nicht auf, stimmt die Laufzeit nicht -
        # und ohne Laufzeit ist eine Monatszahl keine Aussage.
        return None

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
    speicher = _speicher(m)
    farbe = m.group("farbe").replace("-", " ").strip() if m else ""
    ziel = ((h.get("detailWwwAbsoluteCall") or {}).get("constantPayload")
            or {}).get("link") or {}
    return {
        "titel": " ".join(x for x in (modell,
                                      f"{speicher} GB" if speicher else "",
                                      farbe) if x),
        "strukturierter_name": modell,
        "farbe": farbe,
        "speicher_gb": speicher,
        "sku": str(h.get("externalId") or "").strip(),
        # Der Hardware-Angebotsname (Speicher, Farbe, Ratenzahl) - der
        # Schluessel, ueber den `fuehre_zusammen` dasselbe Buendel aus der
        # Vertiefung erkennt.
        "angebot": angebot,
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
        # Kein Deutungsflag zum Tarifbetrag - siehe Modulkopf "WAS DER
        # TARIFBETRAG IST - UND WAS NICHT". `tarif_monatlich` oben IST der
        # Preis dieses Buendels; die -5,00 EUR gegenueber der
        # SIM-only-Kachel sind Teil davon und kein Abzug daneben.
    }


def lies_buendel(text: str, url: str = "",
                 proben: Optional[dict] = None) -> list[dict]:
    """Den Buendelkatalog in Rohsaetze zerlegen.

    Wirft, wenn die Antwort gar keine Buendelantwort ist. Das ist NICHT
    dasselbe wie "keine Buendel gefunden": eine Antwort im Zustand
    `HW_ONLY` an dieser Stelle heisst, dass der Umschalter sich geaendert
    hat, und ihre Geraete als Buendel zu lesen ergaebe 95 Saetze ohne
    Tarif. Ein leeres Ergebnis waere dafuer die falsche Meldung - dieselbe
    Unterscheidung wie bei `GeraeteAbrufFehler` ueberall sonst.

    `proben` (optional, FM-2) sammelt die Existenz-Schwelle der
    Feldebenen fuer diesen Abruf - siehe `_buendelsatz`.
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
        satz = _buendelsatz(h, proben)
        if satz is not None:
            out.append(satz)
    return out


# --------------------------------------------------------------------------
# DIE VERTIEFUNG - jede Tarifstufe, jeder Speicher, jede Ratenlaufzeit
# --------------------------------------------------------------------------
# GEMESSEN AM 29.09.2026
# ----------------------
# Der Buendelkatalog nennt je Geraet EIN Buendel: einen Speicher, einen
# Tarif (meist "O2 Mobile on Demand M Plus"), 36 Raten. Die Produktseite,
# die der Katalog selbst verlinkt (`detailWwwAbsoluteCall`), traegt in
# ihrem `<script id="pageValue">` die GANZE Auswahl, die ein Kunde dort
# umschalten kann - und fuer jeden Schalter die Adresse, die die Seite
# beim Klick selbst laedt:
#
#     hardware.storageOptions[].selectCall.link.uri     Speicher
#     hardware.paymentOptions[].selectCall.link.uri     24 / 36 Raten
#     tariff.tariffOptions[].selectCall.link.uri        12 Tarife
#
# Alle drei zeigen auf GET /e-shop/rest/configuration/<id> (Medientyp
# `application/vnd.commerce.message+json`, `mediaType` am Link selbst),
# und die Antwort ist dieselbe `pdp:PageValue`-Nutzlast wie auf der
# Produktseite. Gefolgt wird NUR, was eine Antwort selbst verlinkt - keine
# Adresse wird gebaut, keine ID gezaehlt. robots.txt (`User-agent: *`)
# sperrt /e-shop/rest/ nicht, siehe Modulkopf.
#
# WAS EINE ANTWORT TRAEGT
# -----------------------
# * fuer den AUSGEWAEHLTEN Tarif die volle Aufteilung in der
#   Preiszusammenfassung, die der Kunde sieht: "Geraet mtl. (36 Raten)",
#   "Tarif mtl.", "Geraet Anzahlung", "einmaliger Anschlusspreis" (der
#   Trackingblock metric2-5 kann davon abweichen, siehe `_gemessen`);
# * fuer JEDEN der zwoelf Tarife `monthlyCharges` - Geraeterate PLUS
#   Tarifbetrag, als typisierte Zahl.
#
# Die Aufteilung der ANDEREN elf Tarife steht nicht in der Antwort. Jeden
# einzeln abzurufen hiesse 12 x Speicher x Laufzeit Abrufe je Geraet -
# rund 2.400 Abrufe a 420 KB, gut anderthalb Stunden je Nacht.
#
# DIE ZWEI BEFUNDE, AUF DENEN DIE ABLEITUNG STEHT - UND IHRE PROBEN
# -----------------------------------------------------------------
# 29.09.2026, je 12 Tarife x 2 Laufzeiten fuer iPhone 17 Pro 256 GB und
# Xiaomi 17 512 GB, dazu 12 Tarife fuer Galaxy A56 128 GB (60 Antworten):
#
# 1. Geraeterate und Anzahlung haengen NICHT am Tarif. Bei jedem Geraet
#    und jeder Laufzeit standen dieselben zwei Zahlen unter allen zwoelf
#    Tarifen (iPhone 17 Pro, 36 Raten: 36,50 / 1,00 EUR) - es ist der
#    getrennte Ratenkaufvertrag. Der Rabatt steckt im TARIF, und der IST
#    geraete- und laufzeitabhaengig (on Demand M Plus: 14,99 beim iPhone,
#    8,49 beim Xiaomi 17 mit 36 Raten, 14,99 mit 24 Raten). Also
#        tarif(T) = monthlyCharges(T) - Geraeterate
#    mit der Rate DERSELBEN Antwort. In allen 60 Antworten ging das fuer
#    den ausgewaehlten Tarif auf den Cent auf.
# 2. Der Anschlusspreis haengt nur am Tarif (39,99 oder 0,00 EUR) - bei
#    allen drei Geraeten, beiden Laufzeiten und allen 93 Katalogeintraegen.
#
# Beides wird JEDE NACHT neu gemessen und ist Bedingung, nicht Annahme:
# die REFERENZ ist ein vollstaendiger Tarifdurchlauf (11 Abrufe) am ersten
# vertieften Geraet. Nur wenn dort Rate und Anzahlung unter allen Tarifen
# gleich sind und jede Einzelprobe aufgeht, wird ueberhaupt abgeleitet;
# Slug und Anschlusspreis je Tarif kommen aus derselben Referenz. Jede
# weitere Antwort prueft ihren EIGENEN ausgewaehlten Tarif gegen die
# Referenz (Slug und Anschluss gleich) - faellt das durch, liefert sie nur
# ihren direkt gemessenen Satz.
#
# ABRUFE JE LAUF: je Katalogbuendel 1 Produktseite plus (Speicher x
# Laufzeiten - 1) Konfigurationsantworten, einmal 11 fuer die Referenz.

_TIEF_QUELLE = "o2_tarifwahl"
# Markiert einen Tarifbetrag, der als monthlyCharges(T) minus gemessener
# Geraeterate derselben Antwort entsteht - nicht direkt abgelesen. Reist
# bis in den Bestand (`tco_model.Buendel.herleitung`).
HERLEITUNG_TARIFSUMME = "tarifsumme_minus_geraeterate"

_PAGE_VALUE_RE = re.compile(
    r'<script id="pageValue" type="application/json">(.*?)</script>', re.S)
_BETRAG_RE = re.compile(r"(-?\d{1,3}(?:\.\d{3})*,\d{2})")


def lies_konfiguration(text: str) -> dict:
    """Die `pdp:PageValue`-Nutzlast - aus der Produktseite ODER der
    Konfigurationsantwort. Beide tragen dieselbe Struktur; die Produktseite
    bettet sie als `<script id="pageValue">` ein."""
    roh = text or ""
    if not roh.lstrip().startswith("{"):
        m = _PAGE_VALUE_RE.search(roh)
        if not m:
            raise GeraeteAbrufFehler("o2-Produktseite ohne pageValue")
        roh = m.group(1)
    try:
        daten = json.loads(roh)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(f"o2-Konfiguration unlesbar: {exc}") from exc
    if not isinstance(daten, dict) or daten.get("@type") != "pdp:PageValue":
        raise GeraeteAbrufFehler("o2-Antwort ist keine pdp:PageValue")
    return daten


def _link(option: dict) -> str:
    return str((((option or {}).get("selectCall") or {}).get("link") or {})
               .get("uri") or "").strip()


def _betrag(text) -> Optional[float]:
    m = _BETRAG_RE.search(str(text or ""))
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def _zusammenfassung(pv: dict) -> dict:
    """Die Zeilen der Preiszusammenfassung, Beschriftung -> Betrag."""
    ps = pv.get("priceSummary") or {}
    out: dict = {}
    for e in ((ps.get("recurringChargesListEntries") or [])
              + (ps.get("nonRecurringChargesListEntries") or [])):
        if not isinstance(e, dict):
            continue
        name = _ohne_markup(_TAG_RE.split(str(e.get("description") or ""))[0])
        out[name] = _betrag(e.get("amount"))
    return out


def _ausgewaehlt(optionen) -> Optional[dict]:
    treffer = [o for o in (optionen or []) if isinstance(o, dict)
               and o.get("selected")]
    return treffer[0] if len(treffer) == 1 else None


def _tarifname(option: dict, pv: dict) -> str:
    """Der Tarifname so, wie der Katalog ihn schreibt.

    Die Produktseite nennt "O2 Mobile on Demand M Plus mit 50 GB+", der
    Katalog "... (24 Mon.)"; die Mindestlaufzeit steht auf der Seite im
    ausgewaehlten Laufzeitknopf ("Monate 24"). Beide Teile stammen aus der
    Antwort. Zusammengesetzt ergeben sie dieselbe Buendel-ID wie der
    Katalogsatz desselben Tarifs (`tco_model.buendel_id` geht ueber den
    Namen), und die Zeitreihe reisst nicht ab. Ohne lesbare Mindestlaufzeit
    bleibt der Name der Seite stehen.
    """
    name = _ohne_markup(option.get("displayValue") or "")
    dauer = _ausgewaehlt((pv.get("tariff") or {}).get("tariffDurationOptions"))
    m = _DAUER_RE.search(str((dauer or {}).get("displayValue") or ""))
    return f"{name} ({m.group(1)} Mon.)" if (name and m) else name


def _gemessen(pv: dict) -> Optional[dict]:
    """Der direkt gemessene Satz einer Antwort - ihr ausgewaehlter Tarif.

    Gelesen wird die PREISZUSAMMENFASSUNG, die der Kunde auf der Seite
    sieht ("Geraet mtl. (36 Raten):", "Tarif mtl. (Mindestlaufzeit 24
    Monate):", "Geraet Anzahlung:", "einmaliger Anschlusspreis") - NICHT
    der Trackingblock. Gemessen am 29.09.2026, iPhone 18 Pro 256 GB mit 24
    Raten: metric2 nennt 34,99 EUR, die Zusammenfassung 24,99 EUR, und
    nur die zweite geht mit der Rate (65,00) auf die typisierte Summe des
    Tarifs (`monthlyCharges` 89,99) auf. Die Probe ist Bedingung:
    Geraeterate + Tarifbetrag == monthlyCharges. Dazu die Laufzeitprobe:
    Ratenknopf ("36 Monate"), Angebotsname ("-36xhigh") und die
    Ratenzeile ("(36 Raten)") nennen dieselbe Zahl. Geht eine nicht auf,
    gibt es keinen Satz. Aus dem Trackingblock kommt nur der Tarif-Slug.
    """
    hw = pv.get("hardware") or {}
    option = _ausgewaehlt((pv.get("tariff") or {}).get("tariffOptions"))
    zahlung = _ausgewaehlt(hw.get("paymentOptions"))
    if option is None or zahlung is None:
        return None
    angebot = str(hw.get("offerName") or "").strip()
    m_raten = _RATEN_RE.search(angebot)
    m_knopf = _DAUER_RE.search(str(zahlung.get("displayValue") or ""))
    if not (m_raten and m_knopf) or m_raten.group("raten") != m_knopf.group(1):
        return None
    raten = m_knopf.group(1)
    zeilen = _zusammenfassung(pv)
    rate = zeilen.get(f"Gerät mtl. ({raten} Raten):")
    tarif_zeilen = [v for k, v in zeilen.items()
                    if k.startswith("Tarif mtl.")]
    tarif_rate = tarif_zeilen[0] if len(tarif_zeilen) == 1 else None
    anzahlung = zeilen.get("Gerät Anzahlung:")
    anschluss = zeilen.get("einmaliger Anschlusspreis")
    summe = _preis(option.get("monthlyCharges"))
    if None in (rate, tarif_rate, anzahlung, anschluss, summe):
        return None
    if not _gleich(rate + tarif_rate, summe):
        return None
    werte = (pv.get("ecommerceProductValue") or {}).get("attributes") or {}
    return {"angebot": angebot, "laufzeit": int(m_knopf.group(1)),
            "rate": rate, "tarif_rate": tarif_rate, "anzahlung": anzahlung,
            "anschluss": anschluss, "summe": summe,
            "slug": str(werte.get("dimension59") or "").strip(),
            "name": _tarifname(option, pv),
            "anzeige": _ohne_markup(option.get("displayValue") or "")}


def referenz_aus(seiten: list) -> Optional[dict]:
    """Aus einem vollstaendigen Tarifdurchlauf die Referenz - oder nichts.

    `seiten` sind die Antworten EINES Geraets (ein Speicher, eine
    Laufzeit), je Tarif eine; ein Eintrag `None` ist ein gescheiterter
    Abruf und macht den Durchlauf unvollstaendig. Geliefert wird je
    Tarifanzeige Slug und Anschlusspreis - aber nur, wenn die zwei Befunde
    aus dem Kopf dieses Abschnitts an diesem Durchlauf halten.
    """
    gemessen = [_gemessen(pv) if pv else None for pv in seiten]
    if len(gemessen) < 2 or any(g is None for g in gemessen):
        return None
    if len({g["rate"] for g in gemessen}) != 1:
        return None
    if len({g["anzahlung"] for g in gemessen}) != 1:
        return None
    tarife: dict = {}
    for g in gemessen:
        if not g["slug"] or g["anzeige"] in tarife:
            return None
        tarife[g["anzeige"]] = {"slug": g["slug"],
                                "anschluss": g["anschluss"]}
    return tarife


def _rohsatz(basis: dict, g: dict, name: str, slug: str,
             tarif_rate: float, anschluss: float, url: str) -> dict:
    m = _OFFER_RE.match(g["angebot"])
    speicher = _speicher(m)
    farbe = m.group("farbe").replace("-", " ").strip() if m else ""
    modell = basis.get("strukturierter_name") or ""
    return {
        "titel": " ".join(x for x in (modell,
                                      f"{speicher} GB" if speicher else "",
                                      farbe) if x),
        "strukturierter_name": modell,
        "farbe": farbe,
        "speicher_gb": speicher,
        "sku": basis.get("sku") or "",
        "angebot": g["angebot"],
        "tarif_name": name,
        "tarif_slug": slug,
        "tarif_monatlich": tarif_rate,
        "geraet_zuzahlung": g["anzahlung"],
        "geraet_monatsrate": g["rate"],
        "anschlusspreis": anschluss,
        "laufzeit_monate": g["laufzeit"],
        # Die Produktseite, von der aus diese Auswahl erreicht wurde. Die
        # Konfigurationsantwort selbst nennt keine eigene Seitenadresse,
        # und eine Adresse zu BAUEN waere geraten.
        "url": url,
        "quelle": _TIEF_QUELLE,
    }


def _zaehle(z: dict, name: str, n: int = 1) -> None:
    z[name] = int(z.get(name, 0)) + n


def saetze_aus_konfiguration(pv: dict, basis: dict,
                             referenz: Optional[dict], url: str,
                             zaehler: Optional[dict] = None) -> list[dict]:
    """Alle Buendel einer Antwort: der gemessene Tarif plus die abgeleiteten.

    Abgeleitet wird nur mit Referenz, nur wenn der eigene Tarif dieser
    Antwort zur Referenz passt (gleicher Slug, gleicher Anschlusspreis),
    und nur fuer Tarife, die die Referenz kennt. Jeder Verzicht wird
    gezaehlt.
    """
    z = zaehler if zaehler is not None else {}
    g = _gemessen(pv)
    if g is None:
        _zaehle(z, "ohne_probe")
        return []
    out = [_rohsatz(basis, g, g["name"], g["slug"], g["tarif_rate"],
                    g["anschluss"], url)]
    _zaehle(z, "gemessen")
    if referenz is None:
        return out
    eigen = referenz.get(g["anzeige"])
    if eigen is None or eigen["slug"] != g["slug"] \
            or not _gleich(eigen["anschluss"], g["anschluss"]):
        _zaehle(z, "referenz_widerspricht")
        return out
    for option in (pv.get("tariff") or {}).get("tariffOptions") or []:
        if not isinstance(option, dict) or option.get("selected"):
            continue
        ref = referenz.get(_ohne_markup(option.get("displayValue") or ""))
        summe = _preis(option.get("monthlyCharges"))
        if ref is None or summe is None:
            _zaehle(z, "ohne_referenz")
            continue
        tarif_rate = round(summe - g["rate"], 2)
        if tarif_rate <= 0:
            _zaehle(z, "unplausibel")
            continue
        satz = _rohsatz(basis, g, _tarifname(option, pv), ref["slug"],
                        tarif_rate, ref["anschluss"], url)
        satz["herleitung"] = HERLEITUNG_TARIFSUMME
        out.append(satz)
        _zaehle(z, "abgeleitet")
    return out


def _hole_seite(hole, url: str, z: dict) -> Optional[dict]:
    _zaehle(z, "abrufe")
    try:
        return lies_konfiguration(hole(url))
    except GeraeteAbrufFehler as exc:
        _zaehle(z, "unlesbar")
        log.info("o2-Vertiefung: %s nicht lesbar (%s)", url, exc)
    except Exception as exc:                          # noqa: BLE001
        _zaehle(z, "unlesbar")
        log.warning("o2-Vertiefung: %s nicht abrufbar (%s: %s)", url,
                    type(exc).__name__, str(exc)[:120])
    return None


def vertiefe_buendel(hole, rohsaetze: list, weiter=None,
                     zaehler: Optional[dict] = None) -> list[dict]:
    """Je Katalogbuendel alle Speicher x Laufzeiten x Tarife als Rohsaetze.

    `hole(url) -> text` ist der gebremste Abruf des Sammlers (robots,
    Abstand, Besuchszeit). `weiter()` sagt, ob noch Zeit ist; ohne Zeit
    hoert die Vertiefung auf und behaelt, was sie hat - die Katalogsaetze
    stehen ohnehin. Geliefert werden NUR die Saetze der Vertiefung; das
    Zusammenfuehren mit dem Katalog macht `fuehre_zusammen`.
    """
    z = zaehler if zaehler is not None else {}
    weiter = weiter or (lambda: True)
    referenz: Optional[dict] = None
    referenz_versucht = False
    gesehen: set = set()
    out: list[dict] = []
    for basis in rohsaetze or []:
        url = str(basis.get("url") or "").strip()
        if not url or basis.get("quelle") != "o2_buendel":
            continue
        if not weiter():
            _zaehle(z, "frist")
            break
        start = _hole_seite(hole, url, z)
        if start is None:
            continue
        _zaehle(z, "geraete")
        # Speicher x Laufzeit: jede Antwort, die ein Kunde hier ueber die
        # zwei Schalter erreicht - und nur ueber deren eigene Links.
        speicherseiten = [start]
        for option in (start.get("hardware") or {}).get("storageOptions") or []:
            if option.get("selected") or not _link(option) or not weiter():
                continue
            pv = _hole_seite(hole, _link(option), z)
            if pv is not None:
                speicherseiten.append(pv)
        antworten = []
        for seite in speicherseiten:
            antworten.append(seite)
            for option in (seite.get("hardware") or {}).get("paymentOptions") or []:
                if option.get("selected") or not _link(option) or not weiter():
                    continue
                pv = _hole_seite(hole, _link(option), z)
                if pv is not None:
                    antworten.append(pv)
        if not referenz_versucht and weiter():
            referenz_versucht = True
            durchlauf: list = [start]
            for option in (start.get("tariff") or {}).get("tariffOptions") or []:
                if option.get("selected") or not _link(option):
                    continue
                if not weiter():
                    durchlauf.append(None)
                    break
                durchlauf.append(_hole_seite(hole, _link(option), z))
            referenz = referenz_aus(durchlauf)
            z["referenz_tarife"] = len(referenz or {})
            if referenz is None:
                log.warning("o2-Vertiefung: der Referenzdurchlauf haelt die "
                            "Befunde nicht (Rate/Anzahlung tarifabhaengig "
                            "oder eine Probe faellt) - nur gemessene Saetze")
        for pv in antworten:
            angebot = str((pv.get("hardware") or {}).get("offerName") or "")
            if angebot in gesehen:
                continue          # derselbe Speicher ueber zwei Katalogeintraege
            gesehen.add(angebot)
            out.extend(saetze_aus_konfiguration(pv, basis, referenz, url, z))
    return out


def fuehre_zusammen(katalog: list, tief: list) -> list:
    """Katalogsaetze plus Vertiefung, ohne dasselbe Buendel zweimal.

    Derselbe Hardware-Angebotsname (Speicher, Farbe, Ratenzahl) mit
    demselben Tarif-Slug ist dasselbe Buendel; der Katalogsatz bleibt dann
    stehen und die Vertiefung faellt weg. Er ist ueber seine Proben gegen
    den typisierten Katalogpreis gelaufen, und seine Adresse ist die
    Produktseite genau dieses Buendels.
    """
    schon = {(s.get("angebot"), s.get("tarif_slug")) for s in katalog}
    return list(katalog) + [s for s in tief
                            if (s.get("angebot"), s.get("tarif_slug"))
                            not in schon]
