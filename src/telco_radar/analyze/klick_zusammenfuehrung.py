"""Klick-Bündel im Gerätelauf: ersetzen, gegenprüfen, nichts verschweigen.

Datenkonzept Geräteradar §7: Hauptquelle ist allein die Anbieterseite, gelesen vom
Klick-Crawler; alles andere ist Gegenprobe. ``zusammenfuehren`` liest die
Ergebnisdateien des Klick-Tageslaufs (``collect.geraete.klickergebnis``) aus dem
genannten Ordner, sonst aus ``UMGEBUNG``, sonst aus ``data/state/klick`` (``ORDNER``),
wenn es ihn gibt; ohne Ordner bleibt alles wie ohne Klick-Crawler. Geplant sind die
Anbieter aus ``klickziele.TAGESDATEI``; fehlt die Datei eines geplanten Anbieters,
nennt ihn die Bilanz unter ``fehlt``. Aus den Dateien werden Rohsätze
(``klickrohsatz``), gemischt unter die Rohsätze der Adapter.

Messung ist eine Datei von heute, ``gelesen`` oder ``gestoert`` (``klick_teillauf``).
Eine ältere liefert nichts: was sie gemessen hat, steht mit ihrem Datum im Bestand,
wenn ein Gerätelauf sie an ihrem Tag gelesen hat. Ab ``FRISCHEGRENZE_TAGE`` veraltet.

Schlüssel ist (Anbieter, Gerät, Speicher, Tarif, Ratenzahl); der Tarif gilt als gleich,
wenn der gelesene Tarif in Vergleichsform (``klickrohsatz.tarifschluessel``) dem Namen
oder dem Slug des Adaptersatzes entspricht. Ein Klick-Satz ersetzt einen Adaptersatz
mit seinem Schlüssel (nur Zustand neu), wenn er jedes Wertfeld nennt, das der
Adaptersatz nennt (``klick_vollstaendig``); dann übernimmt er dessen SKU, Tarifnamen,
Slug und nicht eingerechnete Aktionen, die Bündel-ID bleibt. Sonst bleibt der
Adaptersatz ganz, und die Bilanz zählt ihn unter ``unvollstaendig`` mit den fehlenden
Feldern: zwei Quellen werden nie feldweise gemischt. Ohne Gegenstück kommt ein
Klick-Satz, wie er ist (Lücken bleiben ``None``), nur mit dem Namen eines
Adaptersatzes anderer Laufzeit (``klick_geschwister``).
Nennen zwei Klick-Sätze denselben Schlüssel (ein Zustand außer neu zählt mit), gilt
einer, wenn ihre Werte gleich sind, sonst keiner (``mehrdeutig``). Jeder ersetzte
Adaptersatz ist Gegenprobe, Gerätepreise ohne Tarif sind es über ``klick_geraetepreis``.

Widerspricht ein 1&1-Klick-Satz dem Adaptersatz, ersetzt er ihn nicht
(``klick_widerspruch``).

Vorrang steht im Bestand, nicht im Lesestand: ``Zusammenfuehrung.buendel`` lässt jedes
Adapterbündel weg, dessen Eintrag im Bestand eine Klick-Messung jünger als
``FRISCHEGRENZE_TAGE`` trägt (``klick_vorrang``), auch an einem Tag, an dem der
Klick-Lauf gestört ist oder fehlt. Der Eintrag behält Wert und Datum; keine
Preisbewegung ohne Preisänderung. Vorrang hat nur, was wirklich ein Klick-Bündel wurde.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..collect.geraete.klickergebnis import FRISCHEGRENZE_TAGE, ORDNER, lies_ergebnisse
from ..collect.geraete.klickrohsatz import QUELLE, ZUSTAND_NEU, tarifschluessel
from ..collect.geraete.klickziele import geplante_anbieter
from ..geraete_model import Katalog
from ..tarif_bezug import Tarifbestand
from ..tco_model import Buendel, laufzeit_in_monaten
from .geraete_pruefstatus import HERLEITUNG_WIDERSPRUCH
from .klick_erfassung import Angebot, erfassungsgruende
from .klick_ergebnisdatei import alter_tage, kopf_der_datei
from .klick_geraetepreis import gegenprobe_geraet
from .klick_geschwister import Schluessel, geschwister, mit_namen
from .klick_vollstaendig import CENT, VERGLEICHSFELDER, begleitend, fehlend, nennt
from .klick_widerspruch import widerspruch_luecke
from .tco_buendel import Buendelbilanz, aus_rohsaetzen

log = logging.getLogger(__name__)

UMGEBUNG = "TELCO_KLICK_ERGEBNISSE"
BEISPIELE = 8
UEBERNOMMEN = ("sku_id", "tarif_name", "tarif_slug")

Geraet = Callable[[str], tuple[str, int | None]]


@dataclass
class Gegenprobe:
    """Adaptersätze gegen Klick-Sätze: gleich, abweichend oder unvollständig."""

    gleich: int = 0
    abweichend: int = 0
    ohne_vergleich: int = 0
    felder: Counter[str] = field(default_factory=Counter)
    beispiele: list[str] = field(default_factory=list)
    unvollstaendig: int = 0
    fehlend: Counter[str] = field(default_factory=Counter)

    def unvollstaendig_fuer(self, klick: dict, adapter: dict) -> bool:
        """Zählt einen Adaptersatz mit Wertfeldern, die der Klick-Satz nicht nennt."""
        felder = fehlend(klick, adapter)
        self.unvollstaendig += bool(felder)
        self.fehlend.update(felder)
        return bool(felder)

    def vergleiche(self, klick: dict, adapter: dict) -> list[str]:
        """Zählt einen ersetzten Adaptersatz; Felder nur, wo beide einen Wert haben.

        Gibt die Felder zurück, in denen beide Sätze verschiedene Werte nennen."""
        beide = [f for f in VERGLEICHSFELDER if nennt(klick, f) and nennt(adapter, f)]
        anders = [f for f in beide if abs(klick[f] - adapter[f]) > CENT]
        if not beide:
            self.ohne_vergleich += 1
        elif anders:
            self.abweichend += 1
            self.felder.update(anders)
            if len(self.beispiele) < BEISPIELE:
                teile = ", ".join(f"{f} {klick[f]} statt {adapter[f]}" for f in anders)
                self.beispiele.append(
                    f"{adapter.get('sku_id')} {_zeige(klick)}: {teile}"
                )
        else:
            self.gleich += 1
        return anders

    def als_daten(self) -> dict:
        """Zahlen und Beispiele für Bilanz und Protokoll."""
        return {
            "gleich": self.gleich,
            "abweichend": self.abweichend,
            "ohne_vergleich": self.ohne_vergleich,
            "felder": dict(self.felder),
            "beispiele": list(self.beispiele),
        }


@dataclass
class Zusammenfuehrung:
    """Die Rohsätze für ``aus_rohsaetzen`` und die Bilanz (``None`` ohne Ordner)."""

    rohsaetze: list[dict]
    bilanz: dict | None = None
    angebot: Angebot = field(default_factory=dict)

    @property
    def erfassung(self) -> dict[str, str]:
        """Je Anbieter der Grund eines gestörten Klick-Laufs (``klick_erfassung``)."""
        return erfassungsgruende(self.bilanz)

    def buendel(
        self,
        bestand: Tarifbestand,
        heute: str,
        nach_id: Callable[[str], dict | None],
    ) -> Buendelbilanz:
        """Die Bündel; ein Adapterbündel weicht einer frischen Klick-Messung."""
        bilanz = aus_rohsaetzen(self.rohsaetze, bestand, heute)
        bleiben = [b for b in bilanz.buendel if not _vorrang(b, nach_id(b.id), heute)]
        vorrang = len(bilanz.buendel) - len(bleiben)
        bilanz.buendel = bleiben
        if self.bilanz is not None:
            self.bilanz["klick_vorrang"] = vorrang
        if vorrang:
            log.info("Klick-Bündel: %d Adapterbündel weichen frischer Messung", vorrang)
        return bilanz


def klickordner(umgebung: Mapping[str, str] | None = None) -> Path | None:
    """Der Ordner aus ``UMGEBUNG``; leer oder nicht gesetzt heißt kein Klick-Ordner."""
    wert = (os.environ if umgebung is None else umgebung).get(UMGEBUNG, "")
    return Path(wert) if wert else None


def zusammenfuehren(
    adapter: list[dict],
    ordner: Path | None,
    root: Path,
    katalog: Katalog,
    heute: str,
    geraet: Geraet,
) -> Zusammenfuehrung:
    """Liest die Ergebnisse (Ordner wie im Modulkopf) und führt zusammen."""
    if ordner is None:
        ordner = klickordner()
    if ordner is None and (root / ORDNER).is_dir():
        ordner = root / ORDNER
    if ordner is None:
        return Zusammenfuehrung(list(adapter))
    ergebnisse, unlesbar = lies_ergebnisse(ordner)
    geplant = geplante_anbieter(root)
    return fuehre_zusammen(
        adapter, ergebnisse, katalog, heute, geraet, unlesbar, geplant
    )


def fuehre_zusammen(
    adapter: list[dict],
    ergebnisse: list[dict],
    katalog: Katalog,
    heute: str,
    geraet: Geraet,
    unlesbar: Iterable[str] = (),
    geplant: list[str] | None = None,
) -> Zusammenfuehrung:
    """Klick-Sätze ersetzen Adaptersätze mit gleichem Schlüssel (siehe Modulkopf)."""
    eintraege: list[dict] = []
    saetze: list[dict] = []
    ohne_tarif: list[dict] = []
    for daten in ergebnisse:
        eintrag, aus_datei, geraetepreise = kopf_der_datei(daten, katalog, heute)
        eintraege.append(eintrag)
        saetze.extend(aus_datei)
        ohne_tarif.extend(geraetepreise)
    eindeutig, mehrdeutig = _eindeutig(saetze)
    index: dict[Schluessel, list[int]] = {}
    for stelle, satz in enumerate(adapter):
        for schluessel in adapterschluessel(satz, geraet):
            index.setdefault(schluessel, []).append(stelle)
    probe = Gegenprobe()
    andere_laufzeit = geschwister(index)
    ersetzt: set[int] = set()
    neu: list[dict] = []
    ohne_gegenstueck = 0
    widersprueche = 0
    for satz in eindeutig:
        schluessel = klickschluessel(satz)
        treffer = sorted(set(index.get(schluessel, []) if _neu(satz) else []))
        if not treffer:
            ohne_gegenstueck += 1
            neu += mit_namen(satz, schluessel, adapter, andere_laufzeit, UEBERNOMMEN)
        for stelle in treffer:
            alt = adapter[stelle]
            if probe.unvollstaendig_fuer(satz, alt):
                continue
            anders = probe.vergleiche(satz, alt)
            ersetzt.add(stelle)
            if luecke := widerspruch_luecke(schluessel, satz, alt, anders):
                widersprueche += 1
                neu.append(luecke)
                continue
            uebernommen = {f: alt.get(f) for f in UEBERNOMMEN}
            neu.append({**satz, **uebernommen, **begleitend(satz, alt)})
    vorhanden = {e["anbieter"] for e in eintraege}
    bilanz = {
        "dateien": eintraege,
        "unlesbar": list(unlesbar),
        "geplant": geplant,
        "fehlt": [name for name in geplant or [] if name not in vorhanden],
        "klick_rohsaetze": len(neu),
        "ersetzt": len(ersetzt),
        "unvollstaendig": {
            "nicht_ersetzt": probe.unvollstaendig,
            "felder": dict(probe.fehlend),
        },
        "mehrdeutig": mehrdeutig,
        "ohne_gegenstueck": ohne_gegenstueck,
        "klick_vorrang": 0,
        "widerspruch_24_plus_12": widersprueche,
        "gegenprobe": probe.als_daten(),
        "gegenprobe_geraet": gegenprobe_geraet(ohne_tarif, adapter, geraet),
    }
    _protokolliere(bilanz)
    bleiben = [satz for stelle, satz in enumerate(adapter) if stelle not in ersetzt]
    return Zusammenfuehrung(bleiben + neu, bilanz)


def klickschluessel(satz: dict, mit_zustand: bool = False) -> Schluessel:
    """Der Schlüssel eines Klick-Rohsatzes (Modulkopf), ``mit_zustand`` samt Zustand."""
    zustand = () if not mit_zustand or _neu(satz) else (str(satz.get("zustand")),)
    anbieter, device = str(satz.get("anbieter")), str(satz.get("device_id"))
    tarif = tarifschluessel(satz.get("tarif_name"))
    laufzeit = laufzeit_in_monaten(satz.get("laufzeit_monate"))
    return (anbieter, device, satz.get("speicher_gb"), tarif, laufzeit, *zustand)


def _neu(satz: dict) -> bool:
    """Zustand neu („iPhone 15 Erneuert“ neben „iPhone 15“, Telekom 10.10.2026)."""
    return str(satz.get("zustand") or ZUSTAND_NEU) == ZUSTAND_NEU


def schluesseltext(schluessel: Schluessel) -> str:
    """Der Schlüssel als Text für Bilanz und Protokoll."""
    return "|".join("" if teil is None else str(teil) for teil in schluessel)


def _eindeutig(saetze: list[dict]) -> tuple[list[dict], list[str]]:
    """Je Schlüssel ein Satz; verschiedene Werte auf einem Schlüssel gelten nicht."""
    gruppen: dict[Schluessel, list[dict]] = {}
    for satz in saetze:
        gruppen.setdefault(klickschluessel(satz, mit_zustand=True), []).append(satz)
    eindeutig = [g[0] for g in gruppen.values() if len({_werte(s) for s in g}) == 1]
    mehrdeutig = [
        schluesseltext(k) for k, g in gruppen.items() if len({_werte(s) for s in g}) > 1
    ]
    return eindeutig, mehrdeutig


def _werte(satz: dict) -> tuple:
    phasen = tuple(
        (p.get("von_monat"), p.get("bis_monat"), p.get("betrag"))
        for p in satz.get("tarif_phasen") or []
    )
    return (*(satz.get(f) for f in VERGLEICHSFELDER), phasen)


def _vorrang(buendel: Buendel, eintrag: dict | None, heute: str) -> bool:
    """Ein Adapterbündel, dessen Bestandseintrag eine frische Klick-Messung ist."""
    if buendel.quelle_art == QUELLE or eintrag is None:
        return False
    if buendel.herleitung == HERLEITUNG_WIDERSPRUCH:
        return False
    if eintrag.get("quelle_art") != QUELLE:
        return False
    alter = alter_tage(eintrag.get("abgerufen_am"), heute)
    return alter is not None and 0 <= alter < FRISCHEGRENZE_TAGE


def adapterschluessel(satz: dict, geraet: Geraet) -> list[Schluessel]:
    """Je Tarifschreibweise (Name, Slug) ein Schlüssel; nur Geräte im Zustand neu."""
    if str(satz.get("zustand") or ZUSTAND_NEU) != ZUSTAND_NEU:
        return []
    device, speicher = geraet(str(satz.get("sku_id") or ""))
    if not device:
        return []
    speicher = satz.get("speicher_gb") if speicher is None else speicher
    laufzeit = laufzeit_in_monaten(satz.get("laufzeit_monate"))
    tarife = {tarifschluessel(satz.get(f)) for f in ("tarif_name", "tarif_slug")}
    anbieter = str(satz.get("anbieter"))
    return [(anbieter, device, speicher, t, laufzeit) for t in sorted(tarife) if t]


def _zeige(satz: dict) -> str:
    return (
        f"{satz.get('anbieter')} {satz.get('tarif_name')}"
        f" {satz.get('laufzeit_monate')} Raten"
    )


def _protokolliere(bilanz: dict) -> None:
    for datei in bilanz["dateien"]:
        if not datei["verwendet"]:
            log.warning(
                "Klick-Ergebnis %s ersetzt nichts: %s",
                datei["anbieter"],
                datei["warum_nicht"],
            )
        if datei["ueberfaellig"]:
            log.warning(
                "Klick-Ergebnis %s: %d Seiten überfällig",
                datei["anbieter"],
                len(datei["ueberfaellig"]),
            )
    if bilanz["geplant"] is None:
        log.warning("Klick-Tagesplan fehlt: geplante Anbieter unbekannt")
    for name in bilanz["fehlt"]:
        log.warning("Klick-Ergebnis %s fehlt: keine Datei im Ordner", name)
    for schluessel in bilanz["mehrdeutig"]:
        log.warning("Klick-Sätze mehrdeutig, keiner verwendet: %s", schluessel)
    unvollstaendig = bilanz["unvollstaendig"]
    if unvollstaendig["nicht_ersetzt"]:
        log.warning(
            "Klick-Sätze unvollständig, %d Adaptersätze nicht ersetzt: %s",
            unvollstaendig["nicht_ersetzt"],
            ", ".join(f"{f} {n}" for f, n in unvollstaendig["felder"].items()),
        )
    probe = bilanz["gegenprobe"]
    log.info(
        "Klick-Bündel: %d Sätze, %d Adaptersätze ersetzt (%d gleich, %d abweichend,"
        " %d ohne Vergleich), %d ohne Gegenstück",
        bilanz["klick_rohsaetze"],
        bilanz["ersetzt"],
        probe["gleich"],
        probe["abweichend"],
        probe["ohne_vergleich"],
        bilanz["ohne_gegenstueck"],
    )
    for beispiel in probe["beispiele"]:
        log.warning("Klick-Gegenprobe weicht ab: %s", beispiel)
