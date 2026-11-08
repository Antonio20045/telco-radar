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
                "quelle": "mediamarkt_tarifwelt",
                "url": url,
            }
        )
    return out


def ohne_doppelkarte(saetze: list[dict]) -> list[dict]:
    """Nur Tarife mit einer eigenstaendigen SIM - ein Doppelkarten-Paket
    (zwei Tarife zu einem Preis) ist kein Vergleichswert je Geraet."""
    return [s for s in saetze if not s.get("doppelkarte")]


def waehle_je_band(saetze: list[dict], leiter_gb) -> dict[str, dict]:
    """Je Sprosse der uebergebenen Baender-Leiter (Folge von `(key, gb)`)
    den Tarif mit dem naechstgelegenen Datenvolumen - dieselbe Regel wie
    `report.geraete_tco_band.band_von_gb` (naechstgelegenes Volumen, bei
    Gleichstand das groessere), hier ohne Importabhaengigkeit zur
    Berichtsschicht nachgebaut (`.importlinter`: Sammeln zitiert nie
    Berichten). Bei mehreren gleich nahen Tarifen entscheidet der
    niedrigere Monatspreis."""
    brauchbar = [s for s in saetze if s.get("datenvolumen_gb") is not None]
    out: dict[str, dict] = {}
    for key, gb in leiter_gb:
        kandidaten = sorted(
            brauchbar,
            key=lambda s: (
                abs(s["datenvolumen_gb"] - gb),
                -s["datenvolumen_gb"],
                s["grundgebuehr"]
                if s.get("grundgebuehr") is not None
                else float("inf"),
            ),
        )
        if kandidaten:
            out[key] = kandidaten[0]
    return out
