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
Preis ohne Phasen ist keine, außer der Ratenplan-Beleg (``klickratenplan``) bindet ihn
bis zur letzten Rate. Quelle ist die Seitenadresse des Belegs, sonst die Adresse
der Produktseite; ``quelle_art`` ist ``klick``. Eine ``herleitung`` trägt ein
Klick-Satz nur mit übernommenem Wert (``klickraster.HERLEITUNG_SCHLUSSZAHLUNG``).

Rohsatz wird jede Kombination mit Status ``erfasst``, auch mit ``beleg_status``
``offen``: das Belegarchiv (``belegablage``) braucht Antonios Speicherkonto und ist im
Tageslauf noch nicht angeschlossen. ``beleg_id`` und ``beleg_status`` gehen darum mit
ins Bündel, damit sichtbar bleibt, welche Messung noch ohne Beleg ist.

Jede andere Kombination wird gezählt, nie zu einem Nullwert: ``befund``,
``nicht_erfasst``, ``nicht_angeboten``, ``nicht_besucht`` (Grund beginnt mit „nicht
besucht“), dazu Seiten, die der Lauf nicht öffnete. Trägt die Kombination den
Nachweis ``tarifname`` (Vodafone: der Name zum Radio-Wert der Tarifauswahl), ist er der
Tarifname. Ein erfasster Wert ohne Tarif (``unbekannt``), ohne bekannten Speicher oder
ohne Preis ist ebenfalls eine
benannte Lücke; ohne Tarif gehen Anzahlung, Rate und Ratenzahl als ``ohne_tarif`` in die
Gegenprobe der Gerätepreise (``analyze.klick_geraetepreis``). Ein Tarif, den der
Tarifbestand nicht kennt, bleibt im Satz; über ihn entscheidet ``aus_rohsaetzen`` mit
derselben Regel wie für jeden Adapter (``ohne_tarifblatt``).

Dazu kommen die Sätze gelesener Übersichten (``uebersichten[]``, ``klickuebersicht``):
Gerät über den Titel (``erkenne_geraet``, Katalog samt Auto-Einträgen), Werte wie
gelesen, Quelle die Produktadresse aus dem Satz, sonst die Übersicht. ``angeboten``
hält jedes Gerät, das mit irgendeinem Speicher in einer Übersicht steht (auch in einem
1&1-Geräteraster). ``nicht_im_angebot`` nennt die Katalog-Geräte außerhalb davon nur,
wenn alle Übersichten der Datei gelesen und vollständig sind und kein Titel unbekannt
blieb; sonst ist es ``None`` (unbekannt, nie leer). Ein unbekannter erneuerter Titel
zählt nicht, der Katalog führt nur Neuware (Antonio, 10.10.2026).

Ein Satz einer 1&1-Tarifdetail-Seite (``art`` ``anschluss``) ist kein Rohsatz: sein
Anschlusspreis kommt auf jeden Produktseiten-Satz mit demselben Tarif-Slug, nur wenn
die Seite gelesen ist; sonst bleibt ``anschlusspreis`` ``None``. Ein Satz eines
1&1-Geräterasters (``art`` ``raster``) wird erst nach den Produktseiten Rohsatz, mit dem
Speicher, den ``klickraster.raster_roh`` an ihnen misst.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from ...geraete_model import (
    Katalog,
    erkenne_geraet,
    normalisiere,
    sku_id,
    zustand_aus_titel,
)
from ...tarif_model import QUELLE_KLICK
from .klickanschluss import ART_ANSCHLUSS
from .klickcrawler import GRUND_NICHT_BESUCHT
from .klickergebnis import GELESENE_SEITEN
from .klickkarte import EIN_VERTRAG
from .klicklauf import (
    BEFUND,
    BELEG_OFFEN,
    ERFASST,
    LAUF_GELESEN,
    NICHT_ANGEBOTEN,
    NICHT_ERFASST,
)
from .klickpfad import ohne_markup
from .klickraster import ART_RASTER, raster_roh
from .klickratenplan import ratenplan_phasen

log = logging.getLogger(__name__)

QUELLE = QUELLE_KLICK
ZUSTAND_NEU = "neu"
TARIF_UNBEKANNT = "unbekannt"
TB_IN_GB = 1024
LUECKE_NICHT_BESUCHT = "nicht_besucht"
LUECKE_SEITE = "seite_nicht_gelesen"
LUECKE_TARIF = "tarif_unbekannt"
NACHWEIS_TARIFNAME = "tarifname"
LUECKE_SPEICHER = "speicher_unbekannt"
LUECKE_GERAET = "geraet_unbekannt"
LUECKE_OHNE_PREIS = "ohne_preis"
LUECKE_ZUBEHOER = "buendel_mit_zubehoer"
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
    """Die Rohsätze eines Anbieters, je Lücke ihre Zahl und Gerätepreise ohne Tarif."""

    anbieter: str
    rohsaetze: list[dict] = field(default_factory=list)
    luecken: Counter[str] = field(default_factory=Counter)
    ohne_tarif: list[dict] = field(default_factory=list)
    angeboten: set[str] = field(default_factory=set)
    nicht_im_angebot: list[str] | None = None

    def als_daten(self) -> dict:
        """Zahlen für Bilanz und Protokoll, dazu das Angebot der Übersichten."""
        return {
            "rohsaetze": len(self.rohsaetze),
            "luecken": dict(self.luecken),
            "angeboten": sorted(self.angeboten),
            "nicht_im_angebot": self.nicht_im_angebot,
        }


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
    anschluss = _anschluesse(daten)
    for seite in daten.get("seiten") or []:
        if seite.get("status") not in GELESENE_SEITEN:
            ergebnis.luecken[LUECKE_SEITE] += 1
            continue
        for kombination in seite.get("kombinationen") or []:
            satz = rohsatz(kombination, seite, daten, katalog)
            if isinstance(satz, dict):
                if satz["anschlusspreis"] is None:
                    satz["anschlusspreis"] = anschluss.get(satz["tarif_name"])
                ergebnis.rohsaetze.append(satz)
                continue
            ergebnis.luecken[satz] += 1
            preis = geraetepreis(kombination, seite, daten, katalog)
            if satz == LUECKE_TARIF and preis is not None:
                ergebnis.ohne_tarif.append(preis)
    uebersichten = daten.get("uebersichten") or []
    ganz = bool(uebersichten)
    for uebersicht in uebersichten:
        ganz = ganz and uebersicht.get("status") == LAUF_GELESEN
        ganz = ganz and uebersicht.get("vollstaendig") is True
        if uebersicht.get("status") not in GELESENE_SEITEN:
            ergebnis.luecken[LUECKE_SEITE] += 1
            continue
        ganz = _nimm_uebersicht(ergebnis, uebersicht, daten, katalog) and ganz
    for roh in raster_roh(daten, list(ergebnis.rohsaetze), katalog):
        _nimm(ergebnis, uebersicht_rohsatz(roh, {}, daten, katalog))
    if ganz:
        alle = (g.device_id for g in katalog.geraete)
        ergebnis.nicht_im_angebot = sorted(set(alle) - ergebnis.angeboten)
    return ergebnis


def _nimm_uebersicht(
    ergebnis: Klickausbeute, uebersicht: dict, daten: dict, katalog: Katalog
) -> bool:
    """Rohsätze und angebotene Geräte einer gelesenen Übersicht; wahr, wenn jeder
    Gerätetitel im Katalog steht. Rastersätze zählen nur als angeboten."""
    erkannt = True
    for roh in uebersicht.get("saetze") or []:
        if roh.get("art") == ART_ANSCHLUSS:
            continue
        titel = str(roh.get("titel") or "")
        geraet = erkenne_geraet(titel, katalog)
        neuware = zustand_aus_titel(titel) == ZUSTAND_NEU
        erkannt = erkannt and (geraet is not None or not neuware)
        ergebnis.angeboten.update([geraet.device_id] if geraet else [])
        if roh.get("art") != ART_RASTER:
            _nimm(ergebnis, uebersicht_rohsatz(roh, uebersicht, daten, katalog))
    return erkannt


def _nimm(ergebnis: Klickausbeute, satz: dict | str) -> None:
    if isinstance(satz, dict):
        ergebnis.rohsaetze.append(satz)
    else:
        ergebnis.luecken[satz] += 1


def _anschluesse(daten: dict) -> dict[str, float]:
    """Anschlusspreis je Tarif-Slug aus heute gelesenen Tarifdetail-Seiten (1&1,
    ``klickanschluss.anschluss_saetze``), nur bei ``ein_vertrag``."""
    if daten.get("vertragsform") != EIN_VERTRAG:
        return {}
    return {
        str(roh.get("tarif_slug")): roh["anschlusspreis"]
        for u in daten.get("uebersichten") or []
        if u.get("status") in GELESENE_SEITEN
        for roh in u.get("saetze") or []
        if roh.get("art") == ART_ANSCHLUSS
    }


def uebersicht_rohsatz(
    roh: dict, uebersicht: dict, daten: dict, katalog: Katalog
) -> dict | str:
    """Der Rohsatz eines Satzes aus ``telekom.lies_buendel`` oder seine Lücke.

    Das Gerät kommt über den Titel aus dem Katalog samt Auto-Einträgen; ein
    unbekannter Titel ist die Lücke ``geraet_unbekannt`` und steht im Protokoll.
    Auch der Zustand kommt aus dem Titel („Erneuert Premium“ ist refurbished).
    """
    titel = str(roh.get("titel") or "")
    geraet = erkenne_geraet(titel, katalog)
    if geraet is None:
        log.info(
            "Klick-Übersicht %s: Gerät %r nicht im Katalog", daten.get("name"), titel
        )
        return LUECKE_GERAET
    if roh.get("zubehoer"):
        return LUECKE_ZUBEHOER
    gb = roh.get("speicher_gb")
    if gb not in (geraet.speicher or []):
        return LUECKE_SPEICHER
    zustand = zustand_aus_titel(titel)
    satz: dict[str, object] = {
        "sku_id": sku_id(geraet.device_id, gb, None, zustand),
        "anbieter": str(daten.get("name") or ""),
        "zustand": zustand,
        "device_id": geraet.device_id,
        "speicher_gb": gb,
        "tarif_name": str(roh.get("tarif_name") or ""),
        "tarif_slug": str(roh.get("tarif_slug") or ""),
        "laufzeit_monate": roh.get("laufzeit_monate"),
        "tarif_bindung_monate": None,
        "anschlusspreis": roh.get("anschlusspreis"),
        "volumen_gb": None,
        "quelle_url": str(roh.get("url") or uebersicht.get("adresse") or ""),
        "quelle": QUELLE,
        "quelle_art": QUELLE,
        "beleg_id": None,
        "beleg_status": BELEG_OFFEN,
        "abgerufen_am": daten.get("datum"),
        "geraet_zuzahlung": roh.get("geraet_zuzahlung"),
        "geraet_monatsrate": roh.get("geraet_monatsrate"),
        "tarif_monatlich": roh.get("tarif_monatlich"),
        "buendel_monatlich": roh.get("buendel_monatlich"),
        "tarif_phasen": [],
    }
    if roh.get("herleitung"):
        satz["herleitung"] = roh["herleitung"]
    if all(satz.get(f) is None for f in PREISFELDER):
        return LUECKE_OHNE_PREIS
    return satz


def geraetepreis(
    kombination: dict, seite: dict, daten: dict, katalog: Katalog
) -> dict | None:
    """Anzahlung, Rate und Ratenzahl einer erfassten Kombination in getrennter
    Preisform; ``None`` ohne Gerät, Speicher aus dem Katalog oder Rate."""
    if kombination.get("status") != ERFASST or daten.get("vertragsform") == EIN_VERTRAG:
        return None
    variante = kombination.get("variante") or {}
    geraet = katalog.nach_id(str(seite.get("geraet") or ""))
    gb = speicher_gb(variante.get("speicher"))
    werte = kombination.get("werte") or {}
    if geraet is None or gb not in (geraet.speicher or []) or werte.get("rate") is None:
        return None
    laufzeit = werte.get("ratenzahl")
    return {
        "anbieter": str(daten.get("name") or ""),
        "device_id": geraet.device_id,
        "speicher_gb": gb,
        "laufzeit_monate": variante.get("laufzeit") if laufzeit is None else laufzeit,
        "geraet_zuzahlung": werte.get("anzahlung"),
        "geraet_monatsrate": werte.get("rate"),
        "quelle_url": _quelle(kombination, seite),
    }


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
    name = (kombination.get("nachweise") or {}).get(NACHWEIS_TARIFNAME)
    tarif = name.strip() if isinstance(name, str) and name.strip() else tarif
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
    satz["tarif_phasen"] = _phasen(werte, satz, kombination)
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


def _phasen(werte: dict, satz: dict, kombination: dict) -> list[dict]:
    """Bündelphasen wie gelesen, eine offene bleibt offen; ein einzelner offener Preis
    ab Monat 1 ist keine, außer mit Ratenplan-Beleg (``klickratenplan``)."""
    roh = werte.get("tarifphasen")
    if satz.get("buendel_monatlich") is not None or not isinstance(roh, list):
        return []
    if len(roh) == 1 and roh[0][1] is None:
        if roh[0][0] != 1:
            return []
        laufzeit, betrag = satz["laufzeit_monate"], roh[0][2]
        return ratenplan_phasen(satz["anbieter"], kombination, laufzeit, betrag)
    beleg = f"Klick-Beleg {satz['beleg_id'] or satz['quelle_url']}"
    return [
        {"von_monat": von, "bis_monat": bis, "betrag": betrag, "beleg": beleg}
        for von, bis, betrag in roh
    ]


def _quelle(kombination: dict, seite: dict) -> str:
    beleg = kombination.get("beleg") or {}
    return str(beleg.get("seite") or seite.get("adresse") or "")
