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

# Der Cent, um den eine Rechenprobe danebenliegen darf. Groesser gewaehlt
# waere sie keine Probe mehr, kleiner scheiterte sie an der Rundung.
_TOLERANZ = 0.01


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
    """
    m = _RATEN_RE.search(angebot or "")
    if not m or anzahlung is None or monatsrate is None or gesamt is None:
        return None
    raten = int(m.group("raten"))
    if raten <= 0:
        return None
    if abs(anzahlung + raten * monatsrate - gesamt) > _TOLERANZ:
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
