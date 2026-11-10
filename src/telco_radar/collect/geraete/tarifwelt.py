"""MediaMarkt/Saturn Tarifwelt: Geraet + Fremdtarif (o2, freenet-Telekom,
freenet-Vodafone) auf derselben Ceconomy-Plattform.

Herkunft: Recherche vom 08.11.2026 (Commit afb32aa3) - tarife.mediamarkt.de
laedt seine Tarifliste aus der oeffentlichen, nicht authentifizierten
Schnittstelle tarife-api2.mediamarkt.de/v1/productdetail/<id>/tariff (kein
robots.txt, ehrliche Kennung TelcoRadar/1.0). Jeder Eintrag der Liste
traegt NEBEN dem Tarifnamen auch das Netz (`simCards[].carrier.name`:
"o2" | "freenet - Telekom" | "freenet - Vodafone"), das Datenvolumen
(`dataVolume`, GB) und den Monatspreis (`monthlyPrice`) UNGEFRAGT in
derselben Antwort - ein Browserlesen des sichtbaren Preises ist NICHT
noetig, die vier Fixtures vom 08.11.2026
(tests/fixtures/geraete/tarifwelt_mm_*.json) belegen Preis und Netz
direkt im JSON.

OFFEN (deshalb `aktiv: false` in config/geraete_quellen.yaml):
1. Die Zuordnung Katalog-Modell -> `offerGroupId`/`hwi` ist noch nicht
   geloest - die vier Fixtures tragen die IDs von Hand aus der Recherche,
   nicht aus einer Ernte-Schleife ueber die Kampagnenseite.
2. Ein Tarifwelt-Satz traegt `netz` JE ZEILE (dieselbe Seite fuehrt o2,
   freenet-Telekom UND freenet-Vodafone gleichzeitig); das bestehende
   Buendelschema (`vodafone.py`, `o2.py`, ...) kennt `netz` nur als
   Anbieter-Eigenschaft in `config/geraete_quellen.yaml`, nicht je Satz.
   Vor `aktiv: true` muss das sauber in `geraete_tco.json` eingehaengt
   werden (Clean Code 1: eine Zahl an genau einer Stelle).
Lieber inaktiv und korrekt als aktiv und falsch (CLAUDE.md, harte
Regeln).
"""

from __future__ import annotations

import json
import logging

from ...band_regel import abstand_schluessel, stufe_fuer
from .tarifwelt_merkmale import preiswechsel

log = logging.getLogger(__name__)


def lies(text: str, url: str = "") -> list[dict]:
    """Diese Quelle liefert keine reine Geraeteliste, nur Tarifbuendel
    (`lies_tarifliste`) - der Geraete-Barpreis steht schon unter
    `mediamarkt_angebote` bzw. `saturn_brand`."""
    return []


def _json_liste(text: str) -> list:
    try:
        daten = json.loads(text or "")
    except (json.JSONDecodeError, ValueError):
        log.warning("Tarifwelt: Tarifliste nicht lesbar (kein JSON)")
        return []
    return daten if isinstance(daten, list) else []


def _netz(eintrag: dict) -> str | None:
    for sim in eintrag.get("simCards") or []:
        if not isinstance(sim, dict):
            continue
        name = str((sim.get("carrier") or {}).get("name") or "").strip()
        if name:
            return name
    return None


def _gb(eintrag: dict) -> float | None:
    wert = eintrag.get("dataVolume")
    if wert is None:
        return None
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    if zahl == 0:
        return float("inf")
    return zahl if zahl > 0 else None


def lies_tarifliste(text: str, url: str = "") -> list[dict]:
    """Eine Tarifliste (`/v1/productdetail/<id>/tariff`) in normierte
    Tarifsaetze - noch OHNE Geraetebezug (`einmalpreis_ab` ist ein
    "ab"-Wert ueber alle Speichervarianten, keine SKU-genaue Zuzahlung).

    Ein Doppelkarten-Tarif (zwei SIM-Karten zu einem Gesamtpreis) bleibt
    im Satz (`doppelkarte: True`) statt verworfen zu werden -
    `ohne_doppelkarte` filtert ihn fuer den Vergleich, damit sichtbar
    bleibt, WARUM ein Tarif fehlt (Clean Code 5)."""
    out: list[dict] = []
    for eintrag in _json_liste(text):
        if not isinstance(eintrag, dict):
            continue
        tarif_id = str(eintrag.get("_id") or "").strip()
        if not tarif_id:
            continue
        out.append(
            {
                "tarif_id": tarif_id,
                "tarif_name": str(eintrag.get("nameSlug") or "").strip() or None,
                "netz": _netz(eintrag),
                "datenvolumen_gb": _gb(eintrag),
                "grundgebuehr": eintrag.get("monthlyPrice"),
                "einmalpreis_ab": eintrag.get("oneTimePriceFrom"),
                "doppelkarte": eintrag.get("doubleCardAddendum") is not None,
                "name": str(eintrag.get("name") or "").strip() or None,
                "cashback": eintrag.get("cashback"),
                "seniors": bool(eintrag.get("seniors")),
                "preiswechsel": preiswechsel(eintrag.get("pricingIntervals")),
                "quelle": "mediamarkt_tarifwelt",
                "url": url,
            }
        )
    return out


_POSTEN_ANSCHLUSS = "Anschlusspreis Tarif"
_POSTEN_VERSAND = "Versandkosten"


def _summe_monat(daten: dict) -> float | None:
    """Summe der monatlichen Kostenposten; `None`, wenn keine lesbar sind."""
    posten = ((daten.get("costs") or {}).get("monthlyCosts") or {}).get("items") or []
    betraege = [p.get("amount") for p in posten if isinstance(p, dict)]
    zahlen = [b for b in betraege if isinstance(b, (int, float))]
    if not zahlen or len(zahlen) != len(betraege):
        return None
    return round(sum(zahlen), 2)


def lies_produktdetail(text: str, url: str = "") -> dict | None:
    """Die SKU-genaue Antwort `/v1/productdetail/<id>?tfi=<tarif_id>` (EIN
    vorgewaehlter Tarif) in einen Buendel-Satz - anders als `lies_tarifliste`
    mit der exakten Geraetezuzahlung dieses Tarifs statt eines "ab"-Werts.
    `costs.oneTimeCosts.items` traegt immer drei Posten (Geraet, Anschluss,
    Versand); welcher der Geraeteposten ist, steht nicht am Namen (der
    Hardware-Name ist kuerzer als das Item-Label mit Farbe/Speicher), also
    ist er der Posten ohne einen der beiden festen Namen. Gibt es mehr als
    einen (`geraeteposten`), nimmt der Leser keinen davon: `_pruefe` macht
    daraus eine Luecke."""
    try:
        daten = json.loads(text or "")
    except (json.JSONDecodeError, ValueError):
        log.warning("Tarifwelt: Produktdetail nicht lesbar (kein JSON)")
        return None
    if not isinstance(daten, dict):
        return None
    tariff = daten.get("tariff") or {}
    tarif_id = str(tariff.get("_id") or "").strip()
    if not tarif_id:
        return None
    posten = {
        str(p.get("label") or "").strip(): p.get("amount")
        for p in ((daten.get("costs") or {}).get("oneTimeCosts") or {}).get("items")
        or []
        if isinstance(p, dict)
    }
    geraeteposten = [
        (label, betrag)
        for label, betrag in posten.items()
        if label not in (_POSTEN_ANSCHLUSS, _POSTEN_VERSAND)
    ]
    geraet_label, geraet_zuzahlung = geraeteposten[0] if geraeteposten else (None, None)
    return {
        "tarif_id": tarif_id,
        "tarif_name": str(tariff.get("name") or tariff.get("nameSlug") or "").strip()
        or None,
        "netz": str(tariff.get("carrierName") or "").strip() or None,
        "datenvolumen_gb": _gb(tariff),
        "grundgebuehr": tariff.get("monthlyPrice"),
        "laufzeit_monate": tariff.get("contractTerm"),
        "geraet_zuzahlung": geraet_zuzahlung,
        "geraet_label": geraet_label,
        "geraeteposten": len(geraeteposten),
        "versand": posten.get(_POSTEN_VERSAND),
        "monat_posten": _summe_monat(daten),
        "anschlusspreis": posten.get(_POSTEN_ANSCHLUSS),
        "doppelkarte": tariff.get("doubleCardAddendum") is not None,
        "cashback": tariff.get("cashback"),
        "seniors": bool(tariff.get("seniors")),
        "preiswechsel": preiswechsel(tariff.get("pricingIntervals")),
        "hinweise": tariff.get("bullets"),
        "quelle": "mediamarkt_tarifwelt",
        "url": url,
    }


_NETZ_LABEL = {
    "o2": "o2-Netz",
    "freenet - Telekom": "Telekom-Netz",
    "freenet - Vodafone": "Vodafone-Netz",
}


def anbieter_zeile(netz: str | None) -> str | None:
    """Die Anbieterzeile "Saturn/MediaMarkt · <Netz>-Netz" (Auftrag
    brief-tarifwelt-0811.md) - ein unbekanntes Netz bleibt eine benannte
    Luecke statt eine geratene Zeile."""
    label = _NETZ_LABEL.get((netz or "").strip())
    return f"Saturn/MediaMarkt · {label}" if label else None


def ohne_doppelkarte(saetze: list[dict]) -> list[dict]:
    """Nur Tarife mit einer eigenstaendigen SIM - ein Doppelkarten-Paket
    (zwei Tarife zu einem Preis) ist kein Vergleichswert je Geraet."""
    return [s for s in saetze if not s.get("doppelkarte")]


def rangliste_je_band(saetze: list[dict], leiter_gb) -> dict[str, list[dict]]:
    """Je Sprosse der uebergebenen Baender-Leiter (Folge von `(key, gb)`) die
    Tarife in Reihenfolge der Eignung - der erste ist DER Tarif des Bandes.
    Zuerst bekommt jeder Tarif sein Band nach DERSELBEN Regel wie im
    Bericht (`band_regel.stufe_fuer`, der Baustein hinter
    `report.geraete_tco_band.band_von_gb`; Sammeln importiert die
    Berichtsschicht nicht, `.importlinter`): naechstes Volumen, Gleichstand
    das groessere, unbegrenzt in die oberste Stufe. Ein Tarif ohne
    Band faellt weg. Je Band gewinnt das Volumen mit dem kleinsten Abstand
    zum Bandwert (Gleichstand: das groessere), danach der niedrigere
    Monatspreis. So steht kein Tarif in einem Band, in das der Bericht ihn
    gar nicht legen wuerde. Die Folgeplaetze brauchen nur Geraete, fuer die
    der erste Tarif nicht waehlbar ist (die Schnittstelle fuehrt Tarife auf,
    die fuer ein Geraet eine leere Antwort geben)."""
    leiter = tuple(leiter_gb)
    gb_je_band = dict(leiter)
    je_band: dict[str, list[dict]] = {}
    for satz in saetze:
        band = stufe_fuer(satz.get("datenvolumen_gb"), leiter)
        if band is not None:
            je_band.setdefault(band, []).append(satz)
    out: dict[str, list[dict]] = {}
    for key, kandidaten in je_band.items():
        ziel = gb_je_band[key]

        def rang(s: dict, ziel=ziel) -> tuple:
            gb = s["datenvolumen_gb"]
            unbegrenzt = gb == float("inf")
            abstand = (
                0.0 if unbegrenzt or gb == ziel else abstand_schluessel(gb, ziel)[0]
            )
            preis = s.get("grundgebuehr")
            return (abstand, -gb, float("inf") if preis is None else preis)

        out[key] = sorted(kandidaten, key=rang)
    return out


def waehle_je_band(saetze: list[dict], leiter_gb) -> dict[str, dict]:
    """Je Band genau EIN Tarif: der erste der `rangliste_je_band`."""
    return {k: v[0] for k, v in rangliste_je_band(saetze, leiter_gb).items()}
