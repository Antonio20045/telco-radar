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
import logging
import re
from typing import Optional

from .basis import GeraeteAbrufFehler, _preis
from ...geraete_model import probe_geht_auf

log = logging.getLogger(__name__)

_OFFER_RE = re.compile(
    r"^[a-z]+-(?P<slug>.+?)-(?P<zahl>\d+)(?P<einheit>gb|tb)-(?P<farbe>.+?)"
    r"-\d+x\w+$"
)


def _speicher(m) -> Optional[int]:
    if not m:
        return None
    return int(m.group("zahl")) * (1024 if m.group("einheit") == "tb" else 1)


_BUENDEL_RE = re.compile(r"\bmit\b", re.IGNORECASE)


_RATEN_RE = re.compile(r"-(?P<raten>\d+)x\w+$")


def _laufzeit(
    angebot: str,
    anzahlung: Optional[float],
    monatsrate: Optional[float],
    gesamt: Optional[float],
) -> Optional[int]:
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
    for h in daten.get("hardware") or []:
        if not isinstance(h, dict):
            continue
        modell = str(h.get("description") or "").strip()
        angebot = str(h.get("offerName") or "").strip()
        if not modell:
            continue
        if _BUENDEL_RE.search(modell) or _BUENDEL_RE.search(angebot):
            continue

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

        ziel = (
            (h.get("detailWwwAbsoluteCall") or {}).get("constantPayload") or {}
        ).get("link") or {}
        out.append(
            {
                "titel": " ".join(
                    x
                    for x in (modell, f"{speicher} GB" if speicher else "", farbe)
                    if x
                ),
                "strukturierter_name": modell,
                "preis": preis,
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
            }
        )
    return out


_DAUER_RE = re.compile(r"(\d+)")

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
    if _BUENDEL_RE.search(modell) or _BUENDEL_RE.search(angebot):
        return None

    buendel = h.get("bundle") or {}
    tarif_name = _ohne_markup(buendel.get("tariffName") or "")
    if not tarif_name:
        return None

    preisblock = h.get("price") or {}
    gesamt = _preis(preisblock.get("totalPrice"))
    monatlich = _preis(preisblock.get("monthlyPrice"))
    anzahlung = _preis(preisblock.get("oneTimePrice"))
    anschluss = _preis(preisblock.get("activationFee"))

    werte = (h.get("ecommerceProductValue") or {}).get("attributes") or {}
    geraet_rate = _preis(werte.get("metric3"))
    tarif_rate = _preis(werte.get("metric2"))

    if proben is not None:
        proben["kandidaten"] = int(proben.get("kandidaten", 0)) + 1
        fehlend: list[str] = []
        if monatlich is None:
            fehlend.append("monthlyPrice")
        else:
            if (
                geraet_rate is None
                or tarif_rate is None
                or not _gleich(geraet_rate + tarif_rate, monatlich)
            ):
                fehlend.append("metric3+metric2")
            if anzahlung is None or not _gleich(
                _preis(werte.get("metric5")), anzahlung
            ):
                fehlend.append("metric5")
            if anschluss is None or not _gleich(
                _preis(werte.get("metric4")), anschluss
            ):
                fehlend.append("metric4")
        if fehlend:
            for name in fehlend:
                proben[name] = int(proben.get(name, 0)) + 1
        else:
            proben["bestanden"] = int(proben.get("bestanden", 0)) + 1

    dauer = _DAUER_RE.search(str(h.get("rateDurationValue") or ""))
    laufzeit = int(dauer.group(1)) if dauer else None
    if laufzeit is None or not probe_geht_auf(anzahlung, monatlich, laufzeit, gesamt):
        return None

    if geraet_rate is None or tarif_rate is None:
        return None
    if not _gleich(geraet_rate + tarif_rate, monatlich):
        return None
    if not _gleich(_preis(werte.get("metric5")), anzahlung):
        return None
    if not _gleich(_preis(werte.get("metric4")), anschluss):
        return None

    m = _OFFER_RE.match(angebot)
    speicher = _speicher(m)
    farbe = m.group("farbe").replace("-", " ").strip() if m else ""
    ziel = ((h.get("detailWwwAbsoluteCall") or {}).get("constantPayload") or {}).get(
        "link"
    ) or {}
    return {
        "titel": " ".join(
            x for x in (modell, f"{speicher} GB" if speicher else "", farbe) if x
        ),
        "strukturierter_name": modell,
        "farbe": farbe,
        "speicher_gb": speicher,
        "sku": str(h.get("externalId") or "").strip(),
        "angebot": angebot,
        "tarif_name": tarif_name,
        "tarif_slug": str(werte.get("dimension59") or "").strip(),
        "tarif_monatlich": tarif_rate,
        "geraet_zuzahlung": anzahlung,
        "geraet_monatsrate": geraet_rate,
        "anschlusspreis": anschluss,
        "laufzeit_monate": laufzeit,
        "url": str(ziel.get("uri") or "").strip(),
        "quelle": "o2_buendel",
    }


def lies_buendel(text: str, url: str = "", proben: Optional[dict] = None) -> list[dict]:
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

    zustand = (
        (
            (daten.get("hwCatalogSwitcherStateValue") or {}).get(
                "hwOnlyOrBundleSwitcherValue"
            )
            or {}
        ).get("hwOnlyOrBundleState")
        or {}
    ).get("name")
    if zustand != "BUNDLE":
        raise GeraeteAbrufFehler(
            f"o2-Katalog steht auf {zustand!r} statt 'BUNDLE' - diese "
            f"Antwort traegt keine Tarifbuendel"
        )

    out: list[dict] = []
    for h in daten.get("hardware") or []:
        if not isinstance(h, dict):
            continue
        satz = _buendelsatz(h, proben)
        if satz is not None:
            out.append(satz)
    return out


_TIEF_QUELLE = "o2_tarifwahl"
HERLEITUNG_TARIFSUMME = "tarifsumme_minus_geraeterate"

_PAGE_VALUE_RE = re.compile(
    r'<script id="pageValue" type="application/json">(.*?)</script>', re.S
)
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
    return str(
        (((option or {}).get("selectCall") or {}).get("link") or {}).get("uri") or ""
    ).strip()


def _betrag(text) -> Optional[float]:
    m = _BETRAG_RE.search(str(text or ""))
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def _zusammenfassung(pv: dict) -> dict:
    """Die Zeilen der Preiszusammenfassung, Beschriftung -> Betrag."""
    ps = pv.get("priceSummary") or {}
    out: dict = {}
    for e in (ps.get("recurringChargesListEntries") or []) + (
        ps.get("nonRecurringChargesListEntries") or []
    ):
        if not isinstance(e, dict):
            continue
        name = _ohne_markup(_TAG_RE.split(str(e.get("description") or ""))[0])
        out[name] = _betrag(e.get("amount"))
    return out


def _ausgewaehlt(optionen) -> Optional[dict]:
    treffer = [o for o in (optionen or []) if isinstance(o, dict) and o.get("selected")]
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
    tarif_zeilen = [v for k, v in zeilen.items() if k.startswith("Tarif mtl.")]
    tarif_rate = tarif_zeilen[0] if len(tarif_zeilen) == 1 else None
    anzahlung = zeilen.get("Gerät Anzahlung:")
    anschluss = zeilen.get("einmaliger Anschlusspreis")
    summe = _preis(option.get("monthlyCharges"))
    if None in (rate, tarif_rate, anzahlung, anschluss, summe):
        return None
    if not _gleich(rate + tarif_rate, summe):
        return None
    werte = (pv.get("ecommerceProductValue") or {}).get("attributes") or {}
    return {
        "angebot": angebot,
        "laufzeit": int(m_knopf.group(1)),
        "rate": rate,
        "tarif_rate": tarif_rate,
        "anzahlung": anzahlung,
        "anschluss": anschluss,
        "summe": summe,
        "slug": str(werte.get("dimension59") or "").strip(),
        "name": _tarifname(option, pv),
        "anzeige": _ohne_markup(option.get("displayValue") or ""),
    }


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
        tarife[g["anzeige"]] = {"slug": g["slug"], "anschluss": g["anschluss"]}
    return tarife


def _rohsatz(
    basis: dict,
    g: dict,
    name: str,
    slug: str,
    tarif_rate: float,
    anschluss: float,
    url: str,
) -> dict:
    m = _OFFER_RE.match(g["angebot"])
    speicher = _speicher(m)
    farbe = m.group("farbe").replace("-", " ").strip() if m else ""
    modell = basis.get("strukturierter_name") or ""
    return {
        "titel": " ".join(
            x for x in (modell, f"{speicher} GB" if speicher else "", farbe) if x
        ),
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
        "url": url,
        "quelle": _TIEF_QUELLE,
    }


def _zaehle(z: dict, name: str, n: int = 1) -> None:
    z[name] = int(z.get(name, 0)) + n


def saetze_aus_konfiguration(
    pv: dict,
    basis: dict,
    referenz: Optional[dict],
    url: str,
    zaehler: Optional[dict] = None,
) -> list[dict]:
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
    out = [
        _rohsatz(basis, g, g["name"], g["slug"], g["tarif_rate"], g["anschluss"], url)
    ]
    _zaehle(z, "gemessen")
    if referenz is None:
        return out
    eigen = referenz.get(g["anzeige"])
    if (
        eigen is None
        or eigen["slug"] != g["slug"]
        or not _gleich(eigen["anschluss"], g["anschluss"])
    ):
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
        satz = _rohsatz(
            basis,
            g,
            _tarifname(option, pv),
            ref["slug"],
            tarif_rate,
            ref["anschluss"],
            url,
        )
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
    except Exception as exc:  # noqa: BLE001
        _zaehle(z, "unlesbar")
        log.warning(
            "o2-Vertiefung: %s nicht abrufbar (%s: %s)",
            url,
            type(exc).__name__,
            str(exc)[:120],
        )
    return None


def vertiefe_buendel(
    hole, rohsaetze: list, weiter=None, zaehler: Optional[dict] = None
) -> list[dict]:
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
                log.warning(
                    "o2-Vertiefung: der Referenzdurchlauf haelt die "
                    "Befunde nicht (Rate/Anzahlung tarifabhaengig "
                    "oder eine Probe faellt) - nur gemessene Saetze"
                )
        for pv in antworten:
            angebot = str((pv.get("hardware") or {}).get("offerName") or "")
            if angebot in gesehen:
                continue
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
    return list(katalog) + [
        s for s in tief if (s.get("angebot"), s.get("tarif_slug")) not in schon
    ]
