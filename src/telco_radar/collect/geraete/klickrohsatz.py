"""Vom Klick-Ergebnis zum Bündel-Rohsatz (Datenkonzept Geräteradar §7 und §8).

Hauptquelle ist die Anbieterseite, gelesen vom Klick-Crawler. ``ausbeute`` macht aus
einer Ergebnisdatei (``klickergebnis``) Bündel-Rohsätze im Format, das
``analyze.tco_buendel.aus_rohsaetzen`` liest, nur aus Kombinationen mit Status
``erfasst`` und nur von gelesenen Seiten. Das Gerät kommt aus dem Katalog über die
Geräte-ID der Seite, der Speicher aus der gelesenen Variante (muss beim Gerät stehen),
die SKU über ``geraete_model.sku_id`` ohne Farbe (die Karte klickt keine Farbe).
Ratenzahl ist die bestätigte Ratenzahl, sonst die gewählte Laufzeit.

Werte: Anzahlung, Rate, Tarifpreis ab Monat 1, Tarifbindung, Anschluss und Volumen wie
gelesen; bei ``ein_vertrag`` Bündelbetrag statt Rate und Tarifpreis, die Einmalzahlung
als Zuzahlung, wenn keine Anzahlung gelesen ist. Tarifphasen werden zu Bündelphasen
(``tarif_model.Buendelphase``) mit dem Beleg als Wortlaut. Eine offene letzte Phase
(„ab dem 25. Monat …“) bleibt offen (``bis_monat`` ``None``): ihr Ende steht nicht
auf der Seite, und ``buendelphasen_aus`` lässt sie mit Protokoll fallen; ein einzelner
Preis ohne Phasen ist keine. Quelle ist die Seitenadresse des Belegs, sonst die Adresse
der Produktseite; ``quelle_art`` ist ``klick``. Eine ``herleitung`` trägt kein
Klick-Satz: er ist gemessen.

Rohsatz wird jede Kombination mit Status ``erfasst``, auch mit ``beleg_status``
``offen``: das Belegarchiv (``belegablage``) braucht Antonios Speicherkonto und ist im
Tageslauf noch nicht angeschlossen. ``beleg_id`` und ``beleg_status`` gehen darum mit
ins Bündel, damit sichtbar bleibt, welche Messung noch ohne Beleg ist.

Jede andere Kombination wird gezählt, nie zu einem Nullwert: ``befund``,
``nicht_erfasst``, ``nicht_angeboten``, ``nicht_besucht`` (Grund beginnt mit „nicht
besucht“), dazu Seiten, die der Lauf nicht öffnete. Ein erfasster Wert ohne Tarif
(Vodafone: ``unbekannt``), ohne bekannten Speicher oder ohne Preis ist ebenfalls eine
benannte Lücke. Ein Tarif, den der Tarifbestand nicht kennt, bleibt im Satz; über ihn
entscheidet ``aus_rohsaetzen`` mit derselben Regel wie für jeden Adapter
(``ohne_tarifblatt``).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from ...geraete_model import Katalog, normalisiere, sku_id
from .klickcrawler import GRUND_NICHT_BESUCHT
from .klickergebnis import GELESENE_SEITEN
from .klickkarte import EIN_VERTRAG
from .klicklauf import BEFUND, ERFASST, NICHT_ANGEBOTEN, NICHT_ERFASST
from .klickpfad import ohne_markup

QUELLE = "klick"
ZUSTAND_NEU = "neu"
TARIF_UNBEKANNT = "unbekannt"
TB_IN_GB = 1024
LUECKE_NICHT_BESUCHT = "nicht_besucht"
LUECKE_SEITE = "seite_nicht_gelesen"
LUECKE_TARIF = "tarif_unbekannt"
LUECKE_SPEICHER = "speicher_unbekannt"
LUECKE_GERAET = "geraet_unbekannt"
LUECKE_OHNE_PREIS = "ohne_preis"
LUECKEN_JE_STATUS = {
    BEFUND: BEFUND,
    NICHT_ERFASST: NICHT_ERFASST,
    NICHT_ANGEBOTEN: NICHT_ANGEBOTEN,
}
PREISFELDER = ("geraet_monatsrate", "tarif_monatlich", "buendel_monatlich")

_SPEICHER = re.compile(r"^\s*(\d{1,4})\s*(GB|TB)?\s*$", re.I)
_BINDUNG_IM_NAMEN = re.compile(r"\(\s*\d+\s*Mon\.?\s*\)\s*$", re.I)


@dataclass
class Klickausbeute:
    """Die Rohsätze eines Anbieters und je Lücke ihre Zahl."""

    anbieter: str
    rohsaetze: list[dict] = field(default_factory=list)
    luecken: Counter[str] = field(default_factory=Counter)

    def als_daten(self) -> dict:
        """Zahlen für Bilanz und Protokoll."""
        return {"rohsaetze": len(self.rohsaetze), "luecken": dict(self.luecken)}


def tarifschluessel(text: object) -> str:
    """Vergleichsform eines Tarifs: ohne Markup und ohne Bindungszusatz „(24 Mon.)“."""
    if not isinstance(text, str):
        return ""
    return normalisiere(_BINDUNG_IM_NAMEN.sub("", ohne_markup(text)))


def speicher_gb(text: object) -> int | None:
    """GB aus „256 GB“, „1 TB“ oder „256“; sonst ``None``."""
    treffer = _SPEICHER.match(str(text)) if text is not None else None
    if treffer is None:
        return None
    wert = int(treffer[1])
    return wert * TB_IN_GB if (treffer[2] or "").upper() == "TB" else wert


def ausbeute(daten: dict, katalog: Katalog) -> Klickausbeute:
    """Alle Rohsätze und Lücken einer Ergebnisdatei."""
    ergebnis = Klickausbeute(anbieter=str(daten.get("name") or ""))
    for seite in daten.get("seiten") or []:
        if seite.get("status") not in GELESENE_SEITEN:
            ergebnis.luecken[LUECKE_SEITE] += 1
            continue
        for kombination in seite.get("kombinationen") or []:
            satz = rohsatz(kombination, seite, daten, katalog)
            if isinstance(satz, dict):
                ergebnis.rohsaetze.append(satz)
            else:
                ergebnis.luecken[satz] += 1
    return ergebnis


def rohsatz(
    kombination: dict, seite: dict, daten: dict, katalog: Katalog
) -> dict | str:
    """Der Rohsatz einer Kombination oder der Name ihrer Lücke."""
    status = kombination.get("status")
    if status != ERFASST:
        grund = str(kombination.get("grund") or "")
        if status == NICHT_ERFASST and grund.startswith(GRUND_NICHT_BESUCHT):
            return LUECKE_NICHT_BESUCHT
        return LUECKEN_JE_STATUS.get(str(status), str(status))
    variante = kombination.get("variante") or {}
    geraet = katalog.nach_id(str(seite.get("geraet") or ""))
    if geraet is None:
        return LUECKE_GERAET
    gb = speicher_gb(variante.get("speicher"))
    if gb is None or gb not in (geraet.speicher or []):
        return LUECKE_SPEICHER
    tarif = str(variante.get("tarif") or "").strip()
    if not tarif or tarif.casefold() == TARIF_UNBEKANNT:
        return LUECKE_TARIF
    werte = kombination.get("werte") or {}
    laufzeit = werte.get("ratenzahl")
    laufzeit = variante.get("laufzeit") if laufzeit is None else laufzeit
    satz = {
        "sku_id": sku_id(geraet.device_id, gb, None, ZUSTAND_NEU),
        "anbieter": str(daten.get("name") or ""),
        "zustand": ZUSTAND_NEU,
        "device_id": geraet.device_id,
        "speicher_gb": gb,
        "tarif_name": tarif,
        "tarif_slug": "",
        "laufzeit_monate": laufzeit,
        "tarif_bindung_monate": werte.get("tarifbindung"),
        "anschlusspreis": werte.get("anschluss"),
        "volumen_gb": werte.get("volumen_gb"),
        "quelle_url": _quelle(kombination, seite),
        "quelle": QUELLE,
        "quelle_art": QUELLE,
        "beleg_id": (kombination.get("beleg") or {}).get("beleg_id"),
        "beleg_status": kombination.get("beleg_status"),
        "abgerufen_am": daten.get("datum"),
        **_preise(werte, kombination.get("buendel"), daten.get("vertragsform")),
    }
    satz["tarif_phasen"] = _phasen(werte, satz)
    if all(satz.get(f) is None for f in PREISFELDER):
        return LUECKE_OHNE_PREIS
    return satz


def _preise(werte: dict, buendel: dict | None, vertragsform: object) -> dict:
    if vertragsform == EIN_VERTRAG:
        buendel = buendel or {}
        anzahlung = werte.get("anzahlung")
        return {
            "buendel_monatlich": buendel.get("buendelbetrag"),
            "einmalzahlung": buendel.get("einmalzahlung"),
            "geraet_zuzahlung": anzahlung
            if anzahlung is not None
            else buendel.get("einmalzahlung"),
            "geraet_monatsrate": None,
            "tarif_monatlich": None,
        }
    return {
        "geraet_zuzahlung": werte.get("anzahlung"),
        "geraet_monatsrate": werte.get("rate"),
        "tarif_monatlich": _ab_monat_eins(werte.get("tarifphasen")),
        "buendel_monatlich": None,
    }


def _ab_monat_eins(phasen: object) -> float | None:
    for von, _bis, betrag in phasen if isinstance(phasen, list) else []:
        if von == 1:
            return betrag
    return None


def _phasen(werte: dict, satz: dict) -> list[dict]:
    """Bündelphasen wie gelesen, eine offene bleibt offen; ein einzelner offener Preis
    ab Monat 1 ist keine."""
    roh = werte.get("tarifphasen")
    if satz.get("buendel_monatlich") is not None or not isinstance(roh, list):
        return []
    if len(roh) == 1 and roh[0][1] is None:
        return []
    beleg = f"Klick-Beleg {satz['beleg_id'] or satz['quelle_url']}"
    return [
        {"von_monat": von, "bis_monat": bis, "betrag": betrag, "beleg": beleg}
        for von, bis, betrag in roh
    ]


def _quelle(kombination: dict, seite: dict) -> str:
    beleg = kombination.get("beleg") or {}
    return str(beleg.get("seite") or seite.get("adresse") or "")
