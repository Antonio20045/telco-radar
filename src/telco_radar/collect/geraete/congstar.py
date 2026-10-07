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

NACHTRAG 29.09.2026: DIE PRODUKTSEITE TRAEGT DIE GANZE MATRIX
-------------------------------------------------------------
Die Tarifseiten fuehren nur vier Aufmachergeraete (iPhone 18 Pro Max,
18 Pro, 17 Pro, Galaxy S26 Ultra - auf allen vier Seiten dieselben), und
genau daran lag, dass congstar nur zehn SKUs als Buendel lieferte. Die
Aussage "die Gerateseite traegt nur die Hardware" oben stimmt nur fuer
`prefetchedDevice.variants[].prices`: dieselbe Nutzlast traegt daneben
`prefetchedPlans` (alle acht PlanVarianten mit Preisen und Pflichtblatt)
und `prefetchedPlansWithDevicesPrices` (je PlanVariant und
Geraetevariante die tarifabhaengigen Zahlweisen). `lies_buendel` liest
deshalb bevorzugt diese Matrix (`_produktseiten_plaene`) und faellt nur
ohne sie auf die Tarifseitenform zurueck; der Adapter ruft es auf jeder
Produktseite. Auch dort gibt es keine XL-PlanVariant.

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

ZWEI ZAHLWEISEN, ZWEI SAETZE (P0-B2a, 21.09.2026)
--------------------------------------------------
Je Variante stehen ZWEI Ratenlaeufen nebeneinander (24 und 36 Monate, beide
gleiches `total` - congstar finanziert zum Nulltarif, kuerzer heisst hoehere
Rate) und dazu eine TRADE_IN-Zahlweise, die ein Altgerat voraussetzt.

Bis zum 21.09.2026 war das ein Zwang: der Bestandsschluessel kannte die
Laufzeit nicht, und beide Laeufe zu liefern haette still einer den anderen
ueberschrieben - erhoben wurde deshalb nur die 36-Monats-Finanzierung.
Seit B1 traegt `tco_model.buendel_id` die Ratenlaufzeit im Schluessel:
zwei Zahlweisen sind jetzt zwei Buendel und werden auch beide abgelegt.
`_buendelzahlweisen()` liest jede Zahlweise, deren `contractDuration` in
`_RATENLAUFZEITEN` (24, 36) steht, `lies_buendel()` legt fuer jede
gefundene Laufzeit einen eigenen Satz an. Die TRADE_IN-Zahlweise bleibt
aussen vor - sie setzt die Einnahme eines Altgeraets voraus und ist damit
kein Preis fuer einen Neuabschluss ohne Eintausch. Seit P3-E3 (28.09.2026)
haengt sie als AKTION am Satz derselben Laufzeit (`_trade_in_aktion`,
nicht eingerechnet), zusammen mit den Nachlaessen, die im Preis schon
stecken (`_rabatt_aktionen`: Geraeterabatt, Grundpreisnachlass,
geschenkter Bereitstellungspreis - jeweils mit Fussnote als Bedingung).

`_RATENLAUFZEITEN` ist eine POSITIVLISTE, und sie sagt das laut (FIX3,
21.09.2026): eine Zahlweise mit anderer Dauer - 12 oder 48 Monate, oder
eine Dauer, die diese Antwort ueberhaupt nicht als Zahl nennt - fiel bis
dahin OHNE Protokoll heraus. Jetzt nennt `_buendelzahlweisen()` jede
uebergangene Zahlweise samt Grund, und eine Dauer, die als Zeichenkette
kommt ("36"), wird gelesen statt verworfen: die Positivliste gilt fuer
LAUFZEITEN, nicht fuer JSON-Typen.

Was die Liste kostet, ist gemessen und nicht geschaetzt: dreht man die
36er der gespeicherten Tarifseite auf 48, bleiben 18 statt 36 Saetze -
die 18 fehlenden stehen als 18 Protokollzeilen da und nicht auf der
Seite. Die Liste bleibt trotzdem eine Liste: eine Laufzeit, die kein
gespeicherter Abruf zeigt, soll auffallen und geprueft werden, bevor sie
in den Bestand wandert (CLAUDE.md Fallstrick 16).

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

from .basis import GeraeteAbrufFehler, _preis
from .ratenlaufzeit import congstar_phasen
from ...geraete_model import probe_geht_auf
from ...tco_model import (
    AKTION_ANSCHLUSS_ERLASSEN,
    AKTION_GERAETERABATT,
    AKTION_TARIFRABATT,
    AKTION_TRADE_IN,
    laufzeit_in_monaten,
)

log = logging.getLogger(__name__)

_PUSH_RE = re.compile(r'self\.__next_f\.push\((\[\d+,"(?:[^"\\]|\\.)*"\])\)')

_VARIANTE_START_RE = re.compile(r'\{"id":\d+,"gtin":"')

_VERFUEGBARKEIT = {
    "IN_STOCK": "lieferbar",
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
    """Von der oeffnenden `{` (oder `[`) bei `start` bis zur PASSENDEN
    schliessenden Klammer. Beide Klammerarten zaehlen in dieselbe Tiefe -
    in gueltigem JSON schliesst Tiefe 0 genau an der passenden Klammer, und
    die Produktseite braucht die Listen `prefetchedPlans` und
    `prefetchedPlansWithDevicesPrices` als Ganzes (29.09.2026).

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
        elif zeichen in "{[":
            tiefe += 1
        elif zeichen in "}]":
            tiefe -= 1
            if tiefe == 0:
                return text[start : i + 1]
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


def _ist_ohne_vertrag(zahlweise: dict) -> bool:
    """Traegt diese Zahlweise `contractDuration == 0`, also "ohne Vertrag"?

    Keine zweite Laufzeit-Lesart: gefragt ist nicht, WIE LANG der Vertrag
    laeuft, sondern ob es gar keinen gibt. Deshalb hier nicht
    `laufzeit_in_monaten` - das macht aus einer 0 ein None, und an DIESER
    Stelle ist die 0 eine Aussage (CLAUDE.md Clean Code 3).

    Gelesen wird die ZAHL, nicht ihr JSON-Typ: `"0"` ist dieselbe Aussage
    wie `0`. Der strikte Vergleich gegen die Zahl 0 liess die
    Barpreis-Zahlweise sonst durchfallen und mit ihr die ganze Seite
    (FIX3, gemessen an der echten Produktseite: 7 Rohsaetze gegen 0).
    """
    wert = zahlweise.get("contractDuration")
    if isinstance(wert, bool):
        return False
    try:
        return float(wert) == 0.0
    except (TypeError, ValueError):
        return False


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
        if not _ist_ohne_vertrag(zahlweise):
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
            "congstar-Produktseite ohne Next.js-Flight-Nutzlast (self.__next_f)"
        )
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
            log.info(
                "congstar: Variante %r ohne Einmalkauf-Zahlweise "
                "(ONE_TIME_PURCHASE mit contractDuration 0) - kein "
                "Satz",
                titel,
            )
            continue

        speicher_gb = _speicher_gb(v.get("memory"))

        farbe = str((v.get("color") or {}).get("name") or "").strip()
        status = str((v.get("availability") or {}).get("status") or "").strip().upper()

        out.append(
            {
                "titel": titel,
                "preis": preis,
                "waehrung": "EUR",
                "verfuegbarkeit": _VERFUEGBARKEIT.get(status, "unbekannt"),
                "sku": str(v.get("id") or "").strip(),
                "ean": str(v.get("gtin") or "").strip(),
                "farbe": farbe,
                "speicher_gb": speicher_gb,
                "zustand_hinweis": str(v.get("condition") or ""),
                "url": url,
                "quelle": "congstar_next",
            }
        )
    return out


_PLAN_START_RE = re.compile(r'\{"id":\d+,"type":"POSTPAID","title":"')

_PIB_NR_RE = re.compile(r"Produktinformationsblatt_(\d+)\.pdf")

_RATENLAUFZEITEN = (24, 36)


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
    url = str(
        ((plan.get("media") or {}).get("productInformationSheetUrl")) or ""
    ).strip()
    treffer = _PIB_NR_RE.search(url)
    if not treffer or not pid or treffer.group(1) != pid:
        return ""
    return treffer.group(1)


_BIS_ZUM_RE = re.compile(r"bis zum (\d{1,2})\.(\d{1,2})\.(\d{4})")

TRADE_IN_BEDINGUNG = "nur mit Eintausch eines Altgeräts"

_TRADE_IN_TOLERANZ_EUR = 0.005


def _gueltig_bis(text: str) -> str:
    treffer = _BIS_ZUM_RE.search(text or "")
    if not treffer:
        return ""
    tag, monat, jahr = (int(t) for t in treffer.groups())
    return f"{jahr:04d}-{monat:02d}-{tag:02d}"


def _rabatt_aktionen(preis: dict, art: str, url: str) -> list[dict]:
    """Die `discounts[]` eines congstar-Preisknotens als Aktions-Rohsaetze
    (P3-E3). Jeder Nachlass mit Fussnote wird eine Aktion - ohne Fussnote
    fehlt die Bedingung, und eine Aktion ohne Bedingung ist nicht
    nachpruefbar (`tco_model.Aktion`).

    Betrag: LIMITED ueber `iterations` Monate = amount x iterations (die
    Summe ueber die Laufzeit); ONGOING ("dauerhaft") = amount je Monat.
    `eingerechnet` folgt `ignoreForPriceCalculation`: der Adapter speichert
    `discounted`, und darin steckt jeder Nachlass, den congstar nicht
    ausdruecklich von der Preisrechnung ausnimmt."""
    out: list[dict] = []
    for rabatt in (preis or {}).get("discounts") or []:
        if not isinstance(rabatt, dict):
            continue
        bedingung = str(rabatt.get("footnoteText") or "").strip()
        betrag = _preis(rabatt.get("amount"))
        if not bedingung or betrag is None or betrag <= 0:
            log.info(
                "congstar-Aktion ohne Fussnote oder Betrag - uebergangen: %r", rabatt
            )
            continue
        satz = {
            "art": art,
            "bedingung": bedingung,
            "quelle_url": url,
            "eingerechnet": not rabatt.get("ignoreForPriceCalculation"),
            "gueltig_bis": _gueltig_bis(bedingung),
        }
        typ = str(rabatt.get("iterationType") or "").upper()
        if typ == "ONGOING":
            satz["betrag_monatlich"] = betrag
        elif (
            typ == "LIMITED"
            and (wiederholungen := laufzeit_in_monaten(rabatt.get("iterations")))
            is not None
        ):
            satz["betrag"] = round(betrag * wiederholungen, 2)
        else:
            log.info(
                "congstar-Aktion mit unbekannter Dauer (%r, %r) - uebergangen",
                typ,
                rabatt.get("iterations"),
            )
            continue
        out.append(satz)
    return out


def _trade_in_aktion(trade_in: dict, gesamt_ohne: float, url: str) -> Optional[dict]:
    """Die TRADE_IN-Zahlweise als Aktion (P3-E3) - NICHT eingerechnet, sie
    setzt die Einnahme eines Altgeraets voraus.

    Der Vorteil ist `benefit.amount`, und er gilt nur, wenn er sich selbst
    traegt: Gesamtbetrag ohne Eintausch minus Gesamtbetrag mit Eintausch
    muss genau dieser Betrag sein (iPhone 17 Pro 512 GB, ANF M, 36 Raten:
    1303 - 1033 = 270). Geht die Probe nicht auf, ist der Satz keine
    Messung - dieselbe Regel wie fuer die Zahlweise selbst (Modulkopf)."""
    vorteil = _preis((trade_in.get("benefit") or {}).get("amount"))
    gesamt_mit = _preis(trade_in.get("total"))
    if vorteil is None or vorteil <= 0 or gesamt_mit is None:
        log.info("congstar-Trade-in ohne Vorteil oder Gesamtbetrag - uebergangen")
        return None
    if abs((gesamt_ohne - gesamt_mit) - vorteil) > _TRADE_IN_TOLERANZ_EUR:
        log.info(
            "congstar-Trade-in: %.2f - %.2f ist nicht der genannte "
            "Vorteil %.2f - verworfen",
            gesamt_ohne,
            gesamt_mit,
            vorteil,
        )
        return None
    return {
        "art": AKTION_TRADE_IN,
        "bedingung": TRADE_IN_BEDINGUNG,
        "quelle_url": url,
        "betrag": vorteil,
        "eingerechnet": False,
        "gueltig_bis": "",
    }


def _buendelzahlweisen(variante: dict, url: str = "") -> dict:
    """Zuzahlung und Rate JEDER erlaubten Zahlweise (`_RATENLAUFZEITEN`) -
    nur wenn ihre Probe aufgeht (Modulkopf: die Nachrechnung ist
    Bedingung, nicht Protokoll). Eine Zahlweise, deren Probe nicht
    aufgeht, faellt fuer sich - die anderen bleiben.

    Ergebnis: `{laufzeit_monate: {"zuzahlung":.., "rate":..}}`, hoechstens
    ein Eintrag je Laufzeit (die erste lesbare gewinnt, falls eine Antwort
    dieselbe Laufzeit doppelt nennen sollte).

    JEDE uebergangene Zahlweise wird benannt: unlesbare Dauer, Dauer
    ausserhalb von `_RATENLAUFZEITEN`, Dauer schon vorhanden, unvollstaendige
    Betraege, Probe geht nicht auf. Die Positivliste ist damit sichtbar und
    nicht mehr still (FIX3, 21.09.2026)."""
    gefunden: dict = {}
    trade_in: dict = {}
    for zahlweise in (variante.get("prices") or {}).get("paymentVariants") or []:
        if not isinstance(zahlweise, dict):
            continue
        if zahlweise.get("type") != "INSTALLMENT_PLAN":
            continue
        subtyp = str(zahlweise.get("subtype") or "").upper()
        if subtyp == "TRADE_IN":
            dauer_ti = laufzeit_in_monaten(zahlweise.get("contractDuration"))
            if dauer_ti is not None:
                trade_in.setdefault(dauer_ti, zahlweise)
        if subtyp != "UNSPECIFIED":
            continue
        dauer = laufzeit_in_monaten(zahlweise.get("contractDuration"))
        if dauer is None:
            log.info(
                "congstar-Buendel: Zahlweise ohne lesbare "
                "contractDuration (%r) - uebergangen",
                zahlweise.get("contractDuration"),
            )
            continue
        if dauer not in _RATENLAUFZEITEN:
            log.info(
                "congstar-Buendel: Zahlweise ueber %d Monate steht "
                "nicht in den erhobenen Ratenlaufzeiten %s - "
                "uebergangen",
                dauer,
                list(_RATENLAUFZEITEN),
            )
            continue
        if dauer in gefunden:
            log.info(
                "congstar-Buendel: zweite Zahlweise ueber %d Monate - "
                "die erste lesbare gilt, diese uebergangen",
                dauer,
            )
            continue
        anzahlung = _preis((zahlweise.get("oneTime") or {}).get("discounted"))
        rate = _preis((zahlweise.get("recurring") or {}).get("discounted"))
        gesamt = _preis(zahlweise.get("total"))
        if anzahlung is None or rate is None or gesamt is None:
            log.info(
                "congstar-Buendel: %d-Monats-Zahlweise ohne "
                "vollstaendige Betraege (Zuzahlung %r, Rate %r, "
                "Gesamt %r) - uebergangen",
                dauer,
                anzahlung,
                rate,
                gesamt,
            )
            continue
        if not probe_geht_auf(anzahlung, rate, dauer, gesamt):
            log.info(
                "congstar-Buendel: %s-Monats-Zahlweise ohne "
                "aufgehende Rechenprobe - verworfen",
                dauer,
            )
            continue
        aktionen = _rabatt_aktionen(
            zahlweise.get("oneTime"), AKTION_GERAETERABATT, url
        ) + _rabatt_aktionen(zahlweise.get("recurring"), AKTION_GERAETERABATT, url)
        gefunden[dauer] = {
            "zuzahlung": anzahlung,
            "rate": rate,
            "gesamt": gesamt,
            "aktionen": aktionen,
        }
    for dauer, form in gefunden.items():
        if dauer in trade_in:
            aktion = _trade_in_aktion(trade_in[dauer], form["gesamt"], url)
            if aktion is not None:
                form["aktionen"].append(aktion)
    return gefunden


def _speicher_gb(memory) -> Optional[int]:
    """`referenceGB` vor `size` - das 1-TB-Geraet traegt `size: 1`
    (Modulkopf, "DER SPEICHER KOMMT AUS referenceGB")."""
    for feld in ("referenceGB", "size"):
        try:
            return int((memory or {}).get(feld))
        except (TypeError, ValueError):
            continue
    return None


def _json_unter(nutzlast: str, schluessel: str):
    """Der Wert des ersten `"schluessel":{...}` oder `"schluessel":[...]`
    der Nutzlast, geparst - oder None.

    Next.js schreibt einen schon gesendeten Wert als Verweis
    (`"prefetchedDeviceVariant":"$8:1:props:..."`); ein Treffer, hinter dem
    keine Klammer steht, ist so ein Verweis und wird uebergangen."""
    muster = f'"{schluessel}":'
    pos = nutzlast.find(muster)
    while pos >= 0:
        start = pos + len(muster)
        if start < len(nutzlast) and nutzlast[start] in "{[":
            roh = _balanciertes_objekt(nutzlast, start)
            if roh is not None:
                try:
                    return json.loads(roh)
                except (json.JSONDecodeError, ValueError):
                    log.info("congstar: %s nicht als JSON lesbar", schluessel)
                    return None
        pos = nutzlast.find(muster, start)
    return None


def _produktseiten_plaene(nutzlast: str) -> Optional[list[dict]]:
    """Die Buendelmatrix der PRODUKTseite als PlanVarianten in derselben
    Form wie auf der Tarifseite (`plan["devices"][]["variants"][]`) - oder
    None, wenn die Seite die Matrix nicht traegt.

    Gemessen 29.09.2026 an /geraete/apple/apple-iphone-17/ (HTTP 200,
    920 KB, TelcoRadar/1.0): die Geraeteseite traegt serverseitig DREI
    Knoten, die zusammen die volle Kombinatorik ergeben -

        prefetchedDevice.variants[]          Titel, Farbe, Speicher,
                                             Zustand, gtin je Variante
        prefetchedPlans[].variants[]         alle acht PlanVarianten (XS, S,
                                             M, L je mit Flex) samt Tarif-
                                             und Bereitstellungspreis und
                                             Pflichtblatt
        prefetchedPlansWithDevicesPrices[]   je PlanVariant-ID und je
             .variants[].devices[].variants[]   Geraetevarianten-ID die
                                             Zahlweisen (24/36 Monate) -
                                             tarifabhaengig: dieselbe
                                             Variante kostet in XS eine
                                             andere Rate als in L oder Flex

    Die Tarifseiten fuehren dagegen nur vier Aufmachergeraete (gemessen:
    iPhone 18 Pro Max, 18 Pro, 17 Pro, Galaxy S26 Ultra auf allen vier
    Seiten) - das war die Ursache, dass congstar nur zehn SKUs als
    Buendel lieferte.
    """
    preise = _json_unter(nutzlast, "prefetchedPlansWithDevicesPrices")
    if not isinstance(preise, list):
        return None
    geraet = _json_unter(nutzlast, "prefetchedDevice")
    tarife = _json_unter(nutzlast, "prefetchedPlans")
    if not isinstance(geraet, dict) or not isinstance(tarife, list):
        return None
    varianten = {
        v.get("id"): v for v in (geraet.get("variants") or []) if isinstance(v, dict)
    }
    planvarianten = {
        pv.get("id"): pv
        for tarif in tarife
        if isinstance(tarif, dict)
        for pv in (tarif.get("variants") or [])
        if isinstance(pv, dict)
    }
    out: list[dict] = []
    for tarif in preise:
        for pv in (tarif or {}).get("variants") or []:
            if not isinstance(pv, dict):
                continue
            plan = planvarianten.get(pv.get("id"))
            if plan is None:
                log.info(
                    "congstar-Produktseite: Preise fuer PlanVariant %r "
                    "ohne Tarifknoten - uebergangen",
                    pv.get("id"),
                )
                continue
            zusammen: list[dict] = []
            for dev in pv.get("devices") or []:
                for v in (dev or {}).get("variants") or []:
                    if not isinstance(v, dict):
                        continue
                    meta = varianten.get(v.get("id"))
                    if meta is None:
                        log.info(
                            "congstar-Produktseite: Preise fuer "
                            "Variante %r ohne Geraeteknoten - "
                            "uebergangen",
                            v.get("id"),
                        )
                        continue
                    zusammen.append({**meta, "prices": v.get("prices")})
            out.append({**plan, "devices": [{"variants": zusammen}]})
    return out


def lies_buendel(text: str, url: str = "", proben: Optional[dict] = None) -> list[dict]:
    """Je (PlanVariant x Geraet x Speicher x Laufzeit) einen
    Buendel-Rohsatz - aus einer PRODUKTseite (die ganze Tarifmatrix eines
    Geraets, siehe `_produktseiten_plaene`) oder aus einer Tarifseite
    (`kind: buendel`-Einstieg, nur deren Aufmachergeraete).

    Wirft, wenn die Antwort keins von beiden traegt (kein Flight-Payload,
    weder Produktmatrix noch `prefetchedPlan`) - dasselbe Muster wie bei o2
    und Telekom: ein leeres Ergebnis waere die falsche Meldung fuer ein
    geaendertes Nutzlastformat. Eine einzelne PlanVariant ohne Tarifpreis
    oder ohne Geraete liefert dagegen nur ihre leere Ausbeute - die anderen
    Varianten derselben Seite koennen noch liefern.
    """
    nutzlast = _nutzlast(text)
    if not nutzlast:
        raise GeraeteAbrufFehler(
            "congstar-Seite ohne Next.js-Flight-Nutzlast (self.__next_f)"
        )
    plaene = _produktseiten_plaene(nutzlast)
    quelle = "congstar_produktseite"
    if plaene is None:
        plaene = _planvarianten(nutzlast)
        quelle = "congstar_tarifseite"
    if not plaene:
        raise GeraeteAbrufFehler(
            "congstar-Seite weder mit prefetchedPlansWithDevicesPrices "
            "(Produktseite) noch mit prefetchedPlan.variants (Tarifseite) - "
            "keine Buendelantwort"
        )

    out: list[dict] = []
    for plan in plaene:
        out.extend(_saetze_eines_plans(plan, url, quelle))
    return out


def _saetze_eines_plans(plan: dict, url: str, quelle: str) -> list[dict]:
    """Die Buendel-Rohsaetze EINER PlanVariant (Tarif oder Flex) ueber alle
    ihre Geraete, Speichergroessen und Ratenlaufzeiten."""
    out: list[dict] = []
    tarif_name = str(plan.get("title") or "").strip()
    if not tarif_name:
        return out
    preise = plan.get("prices") or {}
    tarif_monatlich = _preis((preise.get("recurring") or {}).get("discounted"))
    if tarif_monatlich is None:
        log.info(
            "congstar-Buendel: PlanVariant %r ohne Tarifpreis - uebersprungen",
            tarif_name,
        )
        return out
    anschluss = _preis((preise.get("activation") or {}).get("discounted"))
    tarif_slug = _pib_nummer(plan)
    tarif_aktionen = _rabatt_aktionen(
        preise.get("recurring"), AKTION_TARIFRABATT, url
    ) + _rabatt_aktionen(preise.get("activation"), AKTION_ANSCHLUSS_ERLASSEN, url)

    for geraet in plan.get("devices") or []:
        if not isinstance(geraet, dict):
            continue
        gesehen: set = set()
        for variante in geraet.get("variants") or []:
            if not isinstance(variante, dict):
                continue
            speicher = _speicher_gb(variante.get("memory"))
            zustand = str(variante.get("condition") or "").strip().upper()
            if (speicher, zustand) in gesehen:
                continue
            formen = _buendelzahlweisen(variante, url)
            if not formen:
                continue
            titel = str(variante.get("title") or "").strip()
            if not titel:
                continue
            gesehen.add((speicher, zustand))
            farbe = str((variante.get("color") or {}).get("name") or "").strip()
            sku = str(variante.get("id") or "").strip()
            ean = str(variante.get("gtin") or "").strip()
            zustand_hinweis = str(variante.get("condition") or "")
            for laufzeit in sorted(formen):
                form = formen[laufzeit]
                out.append(
                    {
                        "titel": titel,
                        "farbe": farbe,
                        "speicher_gb": speicher,
                        "sku": sku,
                        "ean": ean,
                        "zustand_hinweis": zustand_hinweis,
                        "tarif_name": tarif_name,
                        "tarif_slug": tarif_slug,
                        "tarif_monatlich": tarif_monatlich,
                        "geraet_zuzahlung": form["zuzahlung"],
                        "geraet_monatsrate": form["rate"],
                        "anschlusspreis": anschluss,
                        "laufzeit_monate": laufzeit,
                        "aktionen": [
                            dict(a) for a in tarif_aktionen + form["aktionen"]
                        ],
                        "url": url,
                        "quelle": quelle,
                    }
                )
    return congstar_phasen(out, preise.get("recurring"))


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
    saetze = [
        s
        for s in bestand.je_id.values()
        if str(s.get("anbieter") or "").lower() == "congstar"
    ]
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
