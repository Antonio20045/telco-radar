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


def _variante(daten: dict) -> dict:
    """Die Variante, die die Antwort selbst ausweist (`hardware.variants`) -
    Geraet, Speicher, Farbe, Barpreis und Lagerbestand dieser EINEN Hardware.
    Eine Antwort mit genau einer Variante ist die Regel; alles andere traegt
    `variantenzahl != 1` und wird in `tarifwelt_lauf._pruefe` zur Luecke.
    Diese Felder sind der Beleg, dass Preis UND Lieferbarkeit zu Geraet und
    Speicher der Zeile gehoeren - nicht das freie Text-Label des Kostenpostens
    (Befund A2 vom 12.11.2026)."""
    hardware = daten.get("hardware") or {}
    varianten = [v for v in (hardware.get("variants") or []) if isinstance(v, dict)]
    eine = varianten[0] if len(varianten) == 1 else {}
    ebootis = eine.get("ebootisId")
    return {
        "geraet_name": str(hardware.get("name") or "").strip() or None,
        "variantenzahl": len(varianten),
        "variante_hwi": (
            f"{hardware.get('id')}_{ebootis}"
            if hardware.get("id") and ebootis
            else None
        ),
        "variante_speicher": (
            eine.get("storage") if isinstance(eine.get("storage"), int) else None
        ),
        "variante_bestand": (
            eine.get("stock") if isinstance(eine.get("stock"), int) else None
        ),
        "variante_preis": (
            float(eine["price"])
            if isinstance(eine.get("price"), (int, float))
            else None
        ),
        "variante_farbe": str((eine.get("color") or {}).get("name") or "").strip()
        or None,
    }


def lies_produktdetail(text: str, url: str = "") -> dict | None:
    """Die SKU-genaue Antwort `/v1/productdetail/<id>?tfi=<tarif_id>` (EIN
    vorgewaehlter Tarif) in einen Buendel-Satz - anders als `lies_tarifliste`
    mit der exakten Geraetezuzahlung dieses Tarifs statt eines "ab"-Werts.
    `costs.oneTimeCosts.items` traegt immer drei Posten (Geraet, Anschluss,
    Versand); welcher der Geraeteposten ist, steht nicht am Namen (der
    Hardware-Name ist kuerzer als das Item-Label mit Farbe/Speicher), also
    ist er der Posten ohne einen der beiden festen Namen. Gibt es mehr als
    einen (`geraeteposten`), nimmt der Leser keinen davon: `_pruefe` macht
    daraus eine Luecke. Dazu kommen die Merkmale der gelieferten Variante
    (`_variante`)."""
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
        **_variante(daten),
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


def tarife_mit_band(saetze: list[dict], leiter_gb) -> list[dict]:
    """ALLE Tarife, die der Bericht in ein Band der uebergebenen Leiter (Folge
    von `(key, gb)`) legt - je Tarif (`tarif_id`) einmal, nach Datenvolumen,
    Monatspreis und ID sortiert (feste Reihenfolge). Das Band bestimmt
    DIESELBE Regel wie im Bericht (`band_regel.stufe_fuer`, der Baustein hinter
    `report.geraete_tco_band.band_von_gb`; Sammeln importiert die
    Berichtsschicht nicht, `.importlinter`): naechstes Volumen, Gleichstand
    das groessere, unbegrenzt in die oberste Stufe. Ein Tarif ohne Band
    (Volumen fehlt oder keine passende Stufe) faellt weg: der Bericht wuerde
    ihn in kein Band legen, ein Abruf dafuer waere vertan. Mehrere Tarife
    desselben Bandes bleiben ALLE erhalten - gemessen wird jeder Tarif, welcher
    davon im Bericht gezeigt wird, entscheidet nicht das Sammeln."""
    leiter = tuple(leiter_gb)
    gesehen: set[str] = set()
    out: list[dict] = []
    for satz in saetze:
        tarif_id = satz["tarif_id"]
        if tarif_id in gesehen:
            continue
        if stufe_fuer(satz.get("datenvolumen_gb"), leiter) is None:
            continue
        gesehen.add(tarif_id)
        out.append(satz)

    def rang(s: dict) -> tuple:
        preis = s.get("grundgebuehr")
        return (
            s["datenvolumen_gb"],
            float("inf") if preis is None else preis,
            str(s.get("tarif_id")),
        )

    return sorted(out, key=rang)


def kern_je_netz_und_band(saetze: list[dict], leiter_gb) -> set[str]:
    """Die `tarif_id`s, die ZUERST gelesen werden: je (Netz, Band) der Tarif, dessen
    Volumen dem Bandwert am naechsten liegt (Gleichstand: das groessere, dann der
    niedrigere Monatspreis) - der Tarif, den die Auswahl vor dem 20.11.2026
    allein las. Er ist nur noch eine Reihenfolge, keine Auswahl: reicht das
    Zeitbudget der Stufe nicht fuer alle Tarife, bleibt so mindestens der alte
    Stand. Band und Abstand wie in `tarife_mit_band` (`band_regel`)."""
    leiter = tuple(leiter_gb)
    gb_je_band = dict(leiter)
    je_gruppe: dict[tuple[str, str], list[dict]] = {}
    for satz in saetze:
        band = stufe_fuer(satz.get("datenvolumen_gb"), leiter)
        if band is not None:
            je_gruppe.setdefault((str(satz.get("netz")), band), []).append(satz)

    def rang(satz: dict, ziel: float) -> tuple:
        gb = satz["datenvolumen_gb"]
        abstand = 0.0 if gb in (float("inf"), ziel) else abstand_schluessel(gb, ziel)[0]
        preis = satz.get("grundgebuehr")
        return (abstand, -gb, float("inf") if preis is None else preis)

    return {
        min(gruppe, key=lambda s: rang(s, gb_je_band[band]))["tarif_id"]
        for (_, band), gruppe in je_gruppe.items()
    }
