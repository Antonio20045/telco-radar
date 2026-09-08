"""congstar: der Preis im Next.js-Flight-Payload, nicht im ld+json.

WARUM DIESER ANBIETER
----------------------
Eine Messrunde vom 31.08.2026 hat congstar als den einen Anbieter
identifiziert, der echte neue Marktinformation bringt: er liegt im
TELEKOM-NETZ, und die Telekom selbst steht nicht in dieser Datenbank, weil
sie ihren Geraetepreis nur als Ratenzahlung ausweist. (Bis zum 03.09.2026
stand hier "wegen ihrer AWS-WAF". Nachgemessen: die WAF ist vorhanden -
AWS_WAF_API_KEY und ein awswaf.com-Captcha im ausgelieferten HTML -, aber sie
blockiert den Abruf nicht; die Kategorieseite antwortet mit TelcoRadar/1.0
ueber HTTP/2 mit HTTP 200. Der Grund steht vollstaendig bei `Telekom` in
`config/geraete_quellen.yaml`.) Er trifft Apple, Samsung, Google UND Xiaomi -
Google fehlt der Fachabteilung in ihrer bisherigen Loesung ausdruecklich.

Der Befund vom 30.08.2026 (siehe die alte `grund`-Zeile in
`config/geraete_quellen.yaml`, noch als Kommentar dort nachzulesen) bleibt
fuer das ld+json der Seite richtig: dessen `price` ist der Einmalpreis IM
TARIFBUENDEL, nicht der Geraetepreis ohne Vertrag, und er traegt keine
Speichergroesse. Dieser Adapter liest deshalb NICHT das ld+json, sondern die
Nutzlast, aus der React die Seite selbst zusammensetzt.

WO DER PREIS WIRKLICH STEHT
----------------------------
Next.js liefert den Seiteninhalt als Folge von

    <script>self.__next_f.push([1,"…escaped JSON…"])</script>

Zeilen. Aneinandergehaengt (`_nutzlast`) ergeben ihre zweiten Elemente EINEN
Text, in dem die Variantenobjekte der Produktfamilie stehen:

    {"id":304317,"gtin":"0195950643787",
     "title":"Apple iPhone 17 256 GB weiß","condition":"NEW",
     "color":{"name":"White",...},"memory":{"size":256,...},
     "availability":{"status":"IN_STOCK","infoText":"..."},
     "prices":{"paymentVariants":[...]}}

Jede Variante traegt in `prices.paymentVariants[]` mehrere Zahlweisen -
Ratenkauf mit und ohne Tarif, Einmalkauf. Der Geraetepreis ohne Vertrag ist
der Eintrag mit `type == "ONE_TIME_PURCHASE"` UND `contractDuration == 0`;
sein Wert ist `oneTime.listed`.

DIE EINE REGEL, AN DER DIESES PAKET SCHEITERN KANN: `listed`, NIE `discounted`
------------------------------------------------------------------------------
Derselbe Zahlweisen-Knoten traegt neben `listed` (dem reinen Geraetepreis)
auch `discounted` - einen Rabatt, der laut der Fussnote des Angebots "bei
Abschluss der ANF M" entsteht, also an einen TARIFABSCHLUSS gebunden ist,
nicht an den Kauf ohne Vertrag. `discounted` als Barpreis zu speichern waere
exakt die Fehlerklasse, die die Sitzung vom 30.08.2026 an anderer Stelle
beseitigt hat (o2s `oneTimePrice`, Vodafones Buendelzahl). Gemessen an den
vier Belegdateien dieses Pakets:

    Geraet                       listed (richtig)  discounted (Falle)
    iPhone 17 256 GB                    919,00              811
    Galaxy S25 128 GB                   699,00              519
    Pixel 11 256 GB                     991,00              757
    Redmi Note 17 Pro 256 GB            477,00              225

Der Abstand geht bis 252 EUR. `tests/test_geraete_adapter_congstar.py::
test_discounted_gegenprobe_faellt_bei_der_falschen_zahl_durch` faellt genau
dann durch, wenn hier `discounted` statt `listed` gelesen wird.

EINE UNSICHERHEIT, DIE HIER STEHEN BLEIBT
------------------------------------------
Ob das Geraet auch WIRKLICH ganz ohne SIM-Vertrag an der Kasse zu diesem
Preis zu haben ist, ist NICHT statisch bewiesen - die Kauflabels rendert
React erst im Browser nach, ein reiner HTML-Abruf sieht sie nicht. Belegt
ist: `contractDuration: 0`, `recurring.listed: 0` (keine monatliche Rate
neben dem Einmalpreis), und der Marktvergleich stuetzt es (919/699/991/477
gegen Vodafones 949,90/849,90/999,90/499,90 fuer dieselben Geraete - immer
in derselben Groessenordnung, nie um den Faktor, den ein versteckter
Tarifzwang verursachen wuerde). Wer diese Zahlen spaeter nachpruefen will,
findet hier den Grund, warum das noetig bleibt.

DIE PRODUKTSEITE IST IHR EIGENER QUELLLINK
--------------------------------------------
Anders als bei Vodafone (Schnittstelle getrennt von der Menschenseite)
IST die abgerufene Seite hier schon die Seite, die ein Mensch aufruft - die
Sitemap nennt `https://www.congstar.de/geraete/<hersteller>/<modell>/`
direkt, und genau diese Adresse steht als Quelllink an der Listung. Kein
`urljoin` gegen eine API-Basis noetig, also auch keine Chance auf die
Vodafone-Falle vom 29.08.2026 ("150 Links auf `api.vodafone.de/privat/…`").

ROBOTS.TXT
----------
Wird ueber den bestehenden `RobotsWaechter` geprueft wie bei jedem anderen
Anbieter (`sammle_anbieter` in `collect/geraete/__init__.py`) - dieser
Adapter umgeht ihn nicht und bringt keine eigene Pruefung mit. Fuer diese
Messrunde liegt keine gespeicherte robots.txt vor; ein Host ohne robots.txt
(HTTP 404) ist im Web der Normalfall und bedeutet "keine Regeln", nicht
"nicht anfassen" - dieselbe Lehre wie bei api.vodafone.de.

DER BUENDELKATALOG: DIE TARIFFSEITE, NICHT DIE GERAETESEITE (B3, 08.09.2026)
-----------------------------------------------------------------------------
Die Zahlweisen der GERAETEseite (oben) tragen nur die Hardware: `oneTime`
und `recurring` sind `DevicePrice`-Objekte, ein Tarifpreis steht dort
nicht - die Fussnoten der Rabatte nennen zwar "Bei Abschluss der ANF M",
aber was die ANF M kostet, sagt die Gerateseite nicht. Der Kauffluss mit
Tarifwahl ist ein clientseitiger Konfigurator.

Die Kombinatorik Geraet x Tarif steht stattdessen auf den vier Tarifseiten

    https://www.congstar.de/handytarife/allnet-flat-tarife/allnet-flat-xs/
    .../allnet-flat-s/   .../allnet-flat-m/   .../allnet-flat-l/

und zwar serverseitig, im selben Flight-Payload wie oben, unter

    prefetchedPlan.variants[]   je Tarif + Flex-Variante, MIT Preisen:
        title, minimumContractDuration,
        prices.recurring.{listed,discounted}     Tarif monatlich
        prices.activation.{listed,discounted}    Bereitstellungspreis
        media.productInformationSheetUrl         das Pflichtblatt
    variants[].devices[]       je PlanVariant die Geraete
    devices[].variants[]       je Geraet Speicher x Farbe (condition, gtin)
    variants[].prices.paymentVariants[]  je Variante die Zahlweisen

Diese vier Adressen nennt congstar selbst: die Sitemap pages.xml fuehrt
genau sie (`/sitemap-index.xml` -> `pages.xml`), und die Navigation jeder
Gerate- und Tarifseite verlinkt sie. Keine Adresse ist geraten; eine
Postpaid-Seite "allnet-flat-xl" existiert nicht (gemessen 08.09.2026 in
pages.xml) - XL laeuft nur als Pflichtblatt im Bestand, und das ist eine
ehrlich benannte Messgrenze, keine Luecke dieser Erhebung.

DIE EINE REGEL: IM BUENDEL GILT DER RABATT - `discounted`, NICHT `listed`
-------------------------------------------------------------------------
Fuer den BARPREIS ist `listed` richtig und `discounted` die Falle (oben).
Im Buendel ist es GENAU UMGEKEHRT: Der Nachlass auf die Hardware-Rate
entsteht laut Fussnote "Bei Abschluss der ANF M (24 Monate Laufzeit) ...
reduziert sich die monatliche Rate der Hardware dauerhaft" - er gilt also
genau fuer den Abschluss, den ein Buendel IST. Wer das Buendel mit der
listed-Rate rechnen wuerde, berechnete einen Preis, den kein Kunde dieser
Kombination zahlt. Dasselbe gilt fuer Tarif und Anschlusspreis: M kostet
listed 25 EUR, aber "Bei Abschluss bis zum 29.09.2026 reduziert sich der
monatliche Grundpreis dauerhaft um 1 EUR" (24), und der Bereitstellungspreis
ist "geschenkt" (0 statt 15/35 EUR). Gespeichert wird, was der Kundschaft
dieser Kombination berechnet wird - dieselbe Regel wie bei o2 ("gespeichert
wird, was fuer dieses Buendel zu zahlen ist").

DIE NACHRECHNUNG IST BEDINGUNG, NICHT PROTOKOLL
-----------------------------------------------
`total` der Zahlweise ist der Gesamtbetrag MIT Rabatten; die Probe
`oneTime.discounted + n x recurring.discounted == total` geht bei der
36-Monats-Zahlweise der M-Seite an allen Varianten exakt auf (z. B.
iPhone 17 Pro 512 GB: 97 + 36 x 33,50 = 1303). Geht sie nicht auf -
etwa weil ein Rabatt nur fuer einen Teil der Raten gilt -, wird der Satz
verworfen: ein Gesamtbetrag, der seinen eigenen Bestandteilen widerspricht,
ist keine Messung.

ZWEI ZAHLWEISEN, EIN SAETZ
--------------------------
Je Variante stehen ZWEI Ratenlaeufen nebeneinander (24 und 36 Monate, beide
gleiches `total` - congstar finanziert zum Nulltarif, kuerzer heisst hoehere
Rate) und dazu eine TRADE_IN-Zahlweise, die ein Altgerat voraussetzt. Der
Bestandsschluessel eines Buendels ist (SKU x Anbieter x Tarif) OHNE Laufzeit
(`tco_model.buendel_id`); beide Laeufe zu liefern wuerde still einer den
anderen ueberschreiben. Erhoben wird die 36-Monats-Finanzierung - o2 und
Telekom fuehren ihre Buendel ebenfalls als 36-Raten-Vertrag bei 24 Monaten
Tarifbindung, und A5.5 (Phase R) setzt die laengere Laufzeit als die, die
die Karte fuehrt. Die 24er-Zahlweise ist dadurch kein Datenverlust: sie
rechnet sich aus demselben `total` (kuerzere Laufzeit, hoehere Rate).

DER SLUG IST DIE NUMMER DES PFLICHTBLATTS
-----------------------------------------
congstar nummeriert Tarif und Pflichtblatt mit derselben Zahl: die
PlanVariant 540 ("Allnet Flat M") verlinkt `Produktinformationsblatt_540.pdf`,
und der Bestandssatz `congstar:allnet-flat-m` traegt dieselbe Adresse in
`dokument_url` (alle 10 congstar-Saetze, Nummern 543-560, jeweils
eindeutig - gemessen 08.09.2026). Der ADAPTER liest die Nummer aus dem
`productInformationSheetUrl` der PlanVariant; `ergaenze_pib_slug()` setzt
das Gegenstueck am Bestandssatz (o2-analog: der Anbieter stellt die
Verbindung her, dieses Modul liest sie nur nach - dort ist es der
"Handy hinzufugen"-Slug der Kachel, hier die Blattnummer).

Der Name allein traegt NICHT: die Seite nennt den S-Tarif "Allnet Flat S",
das Pflichtblatt "Allnet Flat S mit GB+" - ueber den Namen treffen sich die
zwei nie, und der SIM-only-Betrag (20 EUR) steht fuer S UND S Flex im
Blattbestand, ist also als Bruecke mehrdeutig. Ohne die Nummernbruecke
fielen vier der acht PlanVarianten (XS, S samt Flex) sang- und klanglos
unter "ohne aufloesbaren Tarif".

DER SPEICHER KOMMT AUS `referenceGB`, NICHT AUS `size`
------------------------------------------------------
Das Galaxy S26 Ultra mit 1 TB traegt `size: 1` und `referenceGB: 1024` -
`size` allein waere "1 GB" und wuerde eine eigene SKU gebaeren, die kein
Katalogeintrag je trifft (dieselbe Falle wie "silber-1-tb" bei der Telekom,
die dort die Einheit im Slug loest). `referenceGB` steht bei jeder Variante
und stimmt mit der Einheit im Namen ueberein.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from . import GeraeteAbrufFehler
from ...geraete_model import probe_geht_auf

log = logging.getLogger(__name__)

# Jedes Fragment ist EIN JS-Stringliteral: `[1,"...escaped..."]`. Die
# Escapes (\", \\, \n, \uXXXX) folgen derselben Grammatik wie JSON-Strings,
# darum genuegt `json.loads` auf dem ganzen Array - kein eigener Entschaerfer
# noetig. Die Alternative "|\\." im Zeichensatz laesst ein `\"` NICHT als
# Ende des Strings gelten; ohne sie schnitte die erste escapte Anfuehrung
# jedes Fragment vorzeitig ab.
_PUSH_RE = re.compile(r'self\.__next_f\.push\((\[\d+,"(?:[^"\\]|\\.)*"\])\)')

# Der Anfang eines Variantenobjekts: `id` und `gtin` stehen NUR dort
# zusammen - Zahlweisen-Knoten tragen `id` (eine kleine Ganzzahl wie 510),
# aber kein `gtin`.
_VARIANTE_START_RE = re.compile(r'\{"id":\d+,"gtin":"')

# Congstars Verfuegbarkeitswerte, gemessen an den vier Belegdateien
# (IN_STOCK, PRE_MARKETING). Ein unbekannter Wert faellt auf "unbekannt" -
# geraten wird nichts.
_VERFUEGBARKEIT = {
    "IN_STOCK": "lieferbar",
    # "wieder lieferbar in 5-6 Wochen" im begleitenden infoText - das ist
    # eine angekuendigte Nachlieferung, kein dauerhafter Abgang.
    "PRE_MARKETING": "nicht_lieferbar",
    "OUT_OF_STOCK": "ausverkauft",
    "DISCONTINUED": "ausverkauft",
}


def _nutzlast(text: str) -> str:
    """Alle `self.__next_f.push([1,"…"])`-Fragmente zu EINEM Text
    verketten. Fragmente ohne Stringnutzlast (`[0]`, `[1,3]` fuer eine
    Referenz) werden uebersprungen - sie tragen kein Variantenobjekt."""
    teile: list[str] = []
    for roh in _PUSH_RE.findall(text or ""):
        try:
            arr = json.loads(roh)
        except (json.JSONDecodeError, ValueError):
            continue
        if len(arr) >= 2 and isinstance(arr[1], str):
            teile.append(arr[1])
    return "".join(teile)


def _balanciertes_objekt(text: str, start: int) -> Optional[str]:
    """Von der oeffnenden `{` bei `start` bis zur PASSENDEN `}`.

    Ein einfacher `find("}")` schnitte an der ersten verschachtelten
    Klammer ab (jede Variante traegt `discounts`, `media`, `availability`
    als eigene Objekte). Anfuehrungszeichen und ihre Escapes werden dabei
    respektiert, sonst zaehlt eine `}` innerhalb eines Textfelds
    (Energieeffizienzerklaerungen tragen Zeilenumbrueche und Doppelpunkte,
    aber testweise auch geschweifte Klammern in anderen Feldern) als
    Klammer statt als Zeichen.
    """
    tiefe = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        zeichen = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif zeichen == "\\":
                escaped = True
            elif zeichen == '"':
                in_string = False
            continue
        if zeichen == '"':
            in_string = True
        elif zeichen == "{":
            tiefe += 1
        elif zeichen == "}":
            tiefe -= 1
            if tiefe == 0:
                return text[start:i + 1]
    return None


def _varianten(nutzlast: str) -> list[dict]:
    """Alle Variantenobjekte der verketteten Nutzlast, geparst und mit
    einer `prices`-Struktur - alles andere ist kein Geraetevariante."""
    out: list[dict] = []
    for treffer in _VARIANTE_START_RE.finditer(nutzlast):
        roh = _balanciertes_objekt(nutzlast, treffer.start())
        if roh is None:
            continue
        try:
            obj = json.loads(roh)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get("prices"), dict):
            out.append(obj)
    return out


def _einmalpreis(variante: dict) -> Optional[float]:
    """Der Geraetepreis ohne Vertrag - `oneTime.listed` der Zahlweise
    `ONE_TIME_PURCHASE` mit `contractDuration == 0`. Siehe Modulkopf: NIE
    `discounted`, das ist ein tarifgebundener Rabatt."""
    zahlweisen = (variante.get("prices") or {}).get("paymentVariants") or []
    for zahlweise in zahlweisen:
        if not isinstance(zahlweise, dict):
            continue
        if zahlweise.get("type") != "ONE_TIME_PURCHASE":
            continue
        if zahlweise.get("contractDuration") != 0:
            continue
        wert = (zahlweise.get("oneTime") or {}).get("listed")
        try:
            return float(wert)
        except (TypeError, ValueError):
            return None
    return None


def lies(text: str, url: str = "") -> list[dict]:
    """Aus einer Produktseite je Variante einen Rohsatz.

    `zustand_hinweis` traegt das rohe `condition`-Feld ungeprueft weiter -
    die Einordnung "neu"/"refurbished"/"b-ware" leistet
    `geraete_model.zustand_aus_feldern()` ueber `lies_listung`
    (`collect/geraete/__init__.py::_als_listung_satz`), nicht dieser
    Adapter. Eine zweite Fassung der Zustandslogik hier waere genau die
    Verdopplung, die Teil E des Auftrags verbietet.
    """
    nutzlast = _nutzlast(text)
    if not nutzlast:
        raise GeraeteAbrufFehler(
            "congstar-Produktseite ohne Next.js-Flight-Nutzlast (self.__next_f)")
    varianten = _varianten(nutzlast)
    if not varianten:
        raise GeraeteAbrufFehler("congstar-Produktseite ohne Variantenobjekte")

    out: list[dict] = []
    for v in varianten:
        titel = str(v.get("title") or "").strip()
        if not titel:
            continue
        preis = _einmalpreis(v)
        if preis is None:
            continue                  # keine Einmalkauf-Zahlweise ohne Vertrag

        speicher = (v.get("memory") or {}).get("size")
        try:
            speicher_gb = int(speicher) if speicher is not None else None
        except (TypeError, ValueError):
            speicher_gb = None

        farbe = str((v.get("color") or {}).get("name") or "").strip()
        status = str((v.get("availability") or {}).get("status") or "").strip().upper()

        out.append({
            "titel": titel,
            "preis": preis,
            "waehrung": "EUR",
            "verfuegbarkeit": _VERFUEGBARKEIT.get(status, "unbekannt"),
            "sku": str(v.get("id") or "").strip(),
            "ean": str(v.get("gtin") or "").strip(),
            "farbe": farbe,
            "speicher_gb": speicher_gb,
            # Der einzige Traeger des Zustands bei congstar - anders als bei
            # o2 (§29.08.2026) steht er hier NICHT in der Farbe, sondern in
            # einem eigenen strukturierten Feld. Beides landet gleichwertig
            # in der Pruefung, siehe Docstring.
            "zustand_hinweis": str(v.get("condition") or ""),
            # Die abgerufene Seite IST die Menschenseite - kein separater
            # Beleglink noetig, siehe Modulkopf.
            "url": url,
            "quelle": "congstar_next",
        })
    return out


# --------------------------------------------------------------------------
# DER BUENDELKATALOG - die Tarifseite, siehe Modulkopf (B3, 08.09.2026)
# --------------------------------------------------------------------------

# Der Anfang eines PlanVariant-Objekts: `type` UND `title` zusammen stehen
# nur dort - Geraeteobjekte tragen `category`, Zahlweisen gar keinen Titel.
_PLAN_START_RE = re.compile(r'\{"id":\d+,"type":"POSTPAID","title":"')

# ".../Produktinformationsblatt_540.pdf" -> "540". Der Pfad davor variiert
# (/fileadmin/produktinformationsblatt/ wie auch /fileadmin/files_congstar/
# documents/PIBs/2026/congstar/ - gemessen im Bestand 08.09.2026), deshalb
# steht das Muster auf dem DATEINAMEN und nicht auf einem Verzeichnis -
# dieselbe Lehre wie beim congstar-Block in `config/tarif_quellen.yaml`.
_PIB_NR_RE = re.compile(r"Produktinformationsblatt_(\d+)\.pdf")

# Die Ratenlaufzeit der erhobenen Zahlweise - siehe Modulkopf
# ("ZWEI ZAHLWEISEN, EIN SAETZ").
_RATENLAUFZEIT = 36


def _preis(wert) -> Optional[float]:
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def _planvarianten(nutzlast: str) -> list[dict]:
    """Alle PlanVariant-Objekte (Tarif und seine Flex-Variante) der
    Tarifseite-Nutzlast - dieselbe Bauart wie `_varianten`, nur mit dem
    Anfangsmuster des Plans statt des Geraets."""
    out: list[dict] = []
    for treffer in _PLAN_START_RE.finditer(nutzlast):
        roh = _balanciertes_objekt(nutzlast, treffer.start())
        if roh is None:
            continue
        try:
            obj = json.loads(roh)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get("prices"), dict):
            out.append(obj)
    return out


def _pib_nummer(plan: dict) -> str:
    """Die Nummer des Pflichtblatts, das DIESE PlanVariant selbst verlinkt.

    Die Probe haengt an der Plan-ID: die PlanVariant 540 ("Allnet Flat M")
    verlinkt `Produktinformationsblatt_540.pdf`. Stimmt der Dateiname nicht
    mit der ID ueberein, ist die Verbindung keine - dann bleibt der Satz
    beim Namens- und Betragsweg der Aufloesung (`tarif_slug` leer, nicht
    geraten).
    """
    pid = str(plan.get("id") or "").strip()
    url = str(((plan.get("media") or {}).get("productInformationSheetUrl"))
              or "").strip()
    treffer = _PIB_NR_RE.search(url)
    if not treffer or not pid or treffer.group(1) != pid:
        return ""
    return treffer.group(1)


def _buendelzahlweise(variante: dict) -> Optional[dict]:
    """Zuzahlung und Rate der 36-Monats-Zahlweise - nur wenn die Probe
    aufgeht (Modulkopf: die Nachrechnung ist Bedingung, nicht Protokoll)."""
    for zahlweise in (variante.get("prices") or {}).get("paymentVariants") or []:
        if not isinstance(zahlweise, dict):
            continue
        if zahlweise.get("type") != "INSTALLMENT_PLAN":
            continue          # ONE_TIME_PURCHASE ist der Barpreis (lies, oben)
        if str(zahlweise.get("subtype") or "").upper() != "UNSPECIFIED":
            continue          # TRADE_IN setzt die Einnahme eines Altgeraets voraus
        if zahlweise.get("contractDuration") != _RATENLAUFZEIT:
            continue
        anzahlung = _preis((zahlweise.get("oneTime") or {}).get("discounted"))
        rate = _preis((zahlweise.get("recurring") or {}).get("discounted"))
        gesamt = _preis(zahlweise.get("total"))
        if anzahlung is None or rate is None or gesamt is None:
            continue
        if not probe_geht_auf(anzahlung, rate, _RATENLAUFZEIT, gesamt):
            continue
        return {"zuzahlung": anzahlung, "rate": rate}
    return None


def _speicher_gb(memory) -> Optional[int]:
    """`referenceGB` vor `size` - das 1-TB-Geraet traegt `size: 1`
    (Modulkopf, "DER SPEICHER KOMMT AUS referenceGB")."""
    for feld in ("referenceGB", "size"):
        try:
            return int((memory or {}).get(feld))
        except (TypeError, ValueError):
            continue
    return None


def lies_buendel(text: str, url: str = "") -> list[dict]:
    """Aus einer Tarifseite je (PlanVariant x Geraet x Speicher) einen
    Buendel-Rohsatz (`kind: buendel`-Einstieg, keine Ernte, keine
    Produktseite wird nachgeladen - die Seite IST die Nutzlast).

    Wirft, wenn die Antwort gar keine Tarifseite ist (kein Flight-Payload,
    kein `prefetchedPlan`) - dasselbe Muster wie bei o2 und Telekom: ein
    leeres Ergebnis waere die falsche Meldung fuer ein geaendertes
    Nutzlastformat. Eine einzelne PlanVariant ohne Tarifpreis oder ohne
    Geraete liefert dagegen nur ihre leere Ausbeute - die andere Variante
    derselben Seite kann noch liefern.
    """
    nutzlast = _nutzlast(text)
    if not nutzlast:
        raise GeraeteAbrufFehler(
            "congstar-Tarifseite ohne Next.js-Flight-Nutzlast (self.__next_f)")
    plaene = _planvarianten(nutzlast)
    if not plaene:
        raise GeraeteAbrufFehler(
            "congstar-Tarifseite ohne prefetchedPlan.variants - keine "
            "Buendelantwort (Tarifseite umgezogen?)")

    out: list[dict] = []
    for plan in plaene:
        tarif_name = str(plan.get("title") or "").strip()
        if not tarif_name:
            continue
        preise = plan.get("prices") or {}
        tarif_monatlich = _preis((preise.get("recurring") or {}).get("discounted"))
        if tarif_monatlich is None:
            # Ohne Tarifpreis ist keine Buendelaussage moeglich - derselbe
            # Grund wie beim Telekom-selectedPlan ohne recurringFee.
            log.info("congstar-Buendel: PlanVariant %r ohne Tarifpreis - "
                     "uebersprungen", tarif_name)
            continue
        anschluss = _preis((preise.get("activation") or {}).get("discounted"))
        tarif_slug = _pib_nummer(plan)

        for geraet in (plan.get("devices") or []):
            if not isinstance(geraet, dict):
                continue
            # JE SPEICHERGROESSE (UND ZUSTAND) EIN SATZ: die Zahlweise ist
            # bei jeder Farbe derselben Groesse identisch (gemessen an allen
            # vier Tarifseiten); die erste Variante mit lesbarer Zahlweise
            # vertritt den Satz - dedupliziert, wie der Auftrag es verlangt.
            gesehen: set = set()
            for variante in (geraet.get("variants") or []):
                if not isinstance(variante, dict):
                    continue
                speicher = _speicher_gb(variante.get("memory"))
                zustand = str(variante.get("condition") or "").strip().upper()
                if (speicher, zustand) in gesehen:
                    continue
                form = _buendelzahlweise(variante)
                if form is None:
                    continue
                titel = str(variante.get("title") or "").strip()
                if not titel:
                    continue
                gesehen.add((speicher, zustand))
                out.append({
                    "titel": titel,
                    "farbe": str((variante.get("color") or {})
                                 .get("name") or "").strip(),
                    "speicher_gb": speicher,
                    "sku": str(variante.get("id") or "").strip(),
                    "ean": str(variante.get("gtin") or "").strip(),
                    # Dasselbe rohe `condition`-Feld wie im Listungsweg -
                    # die Einordnung leistet `zustand_aus_feldern` ueber
                    # `lies_listung`, siehe Docstring von `lies()`.
                    "zustand_hinweis": str(variante.get("condition") or ""),
                    "tarif_name": tarif_name,
                    # Die Pflichtblattnummer, siehe Modulkopf ("DER SLUG
                    # IST DIE NUMMER DES PFLICHTBLATTS").
                    "tarif_slug": tarif_slug,
                    "tarif_monatlich": tarif_monatlich,
                    "geraet_zuzahlung": form["zuzahlung"],
                    "geraet_monatsrate": form["rate"],
                    "anschlusspreis": anschluss,
                    "laufzeit_monate": _RATENLAUFZEIT,
                    # Die Tarifseite ist die Seite, auf der diese Zahlen
                    # stehen - dieselbe Regel wie bei der Telekom-Kategorie.
                    "url": url,
                    "quelle": "congstar_tarifseite",
                })
    return out


def ergaenze_pib_slug(bestand) -> int:
    """Am congstar-Tarifbestand die Nummern-Bruecke setzen (Modulkopf,
    "DER SLUG IST DIE NUMMER DES PFLICHTBLATTS").

    Ergaenzt congstar-Saetzen OHNE `buendel_slug` die Nummer aus ihrer
    Pflichtblatt-Adresse - nur wo die Nummer unter den congstar-Saetzen
    EINDEUTIG ist; zwei Blatter derselben Nummer waeren keine Bruecke,
    sondern eine Mehrdeutigkeit (dieselbe Regel wie `ueber_slug`). Schon
    gesetzte Werte bleiben unberuehrt. Gibt die Zahl der ergaenzten
    Saetze zurueck.

    Aufgerufen von der Pipeline, direkt nach dem Laden des Bestands. Das
    ist bewusst KEINE dauerhafte Aenderung an `tarife.jsonl`: die Zeitreihe
    bleibt unberuehrt, und die Bruecke entsteht bei jedem Lauf neu aus der
    Blattnummer, die der Anbieter in beide Adressen schreibt.
    """
    saetze = [s for s in bestand.je_id.values()
              if str(s.get("anbieter") or "").lower() == "congstar"]
    nummern: dict[str, list] = {}
    for satz in saetze:
        treffer = _PIB_NR_RE.search(str(satz.get("dokument_url") or ""))
        if treffer:
            nummern.setdefault(treffer.group(1), []).append(satz)
    gesetzt = 0
    for nummer, gruppe in nummern.items():
        if len(gruppe) != 1:
            continue
        satz = gruppe[0]
        if str(satz.get("buendel_slug") or "").strip():
            continue
        satz["buendel_slug"] = nummer
        gesetzt += 1
    return gesetzt
