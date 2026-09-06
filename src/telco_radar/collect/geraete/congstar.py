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
"""
from __future__ import annotations

import json
import re
from typing import Optional

from . import GeraeteAbrufFehler

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
