"""Klick-Bündel im Gerätelauf: ersetzen, gegenprüfen, nichts verschweigen.

Datenkonzept Geräteradar §7: Hauptquelle ist allein die Anbieterseite, gelesen vom
Klick-Crawler; alles andere ist Gegenprobe. ``zusammenfuehren`` liest die
Ergebnisdateien des Klick-Tageslaufs (``collect.geraete.klickergebnis``) aus dem
genannten Ordner, sonst aus ``UMGEBUNG``, sonst aus ``data/state/klick`` (``ORDNER``),
wenn es ihn gibt; ohne Ordner bleibt alles wie ohne Klick-Crawler. Geplant sind die
Anbieter aus ``klickziele.TAGESDATEI``; fehlt die Datei eines geplanten Anbieters,
nennt ihn die Bilanz unter ``fehlt``. Aus den Dateien werden Rohsätze
(``klickrohsatz``), gemischt unter die Rohsätze der Adapter.

Messung ist nur eine Datei von heute mit Laufstatus ``gelesen``. Eine ältere liefert
nichts: was sie gemessen hat, steht mit ihrem Datum im Bestand, wenn ein Gerätelauf
sie an ihrem Tag gelesen hat. Ab ``FRISCHEGRENZE_TAGE`` heißt sie veraltet.

Schlüssel ist (Anbieter, Gerät, Speicher, Tarif, Ratenzahl); der Tarif gilt als gleich,
wenn der gelesene Tarif in Vergleichsform (``klickrohsatz.tarifschluessel``) dem Namen
oder dem Slug des Adaptersatzes entspricht. Ein Klick-Satz ersetzt einen Adaptersatz
mit seinem Schlüssel (nur Zustand neu), wenn er jedes Wertfeld nennt, das der
Adaptersatz nennt (``WERTFELDER``); dann übernimmt er dessen SKU, Tarifnamen und Slug,
die Bündel-ID bleibt. Sonst bleibt der Adaptersatz ganz, und die Bilanz zählt ihn unter
``unvollstaendig`` mit den fehlenden Feldern: zwei Quellen werden nie feldweise
gemischt. Ohne Gegenstück kommt ein Klick-Satz, wie er ist (Lücken bleiben ``None``),
nur mit dem Namen eines Adaptersatzes anderer Laufzeit (``klick_geschwister``).
Nennen zwei Klick-Sätze denselben Schlüssel, gilt einer, wenn ihre Werte gleich sind,
sonst keiner (``mehrdeutig``). Jeder ersetzte Adaptersatz ist Gegenprobe.

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
from datetime import date
from pathlib import Path

from ..collect.geraete.klickergebnis import FRISCHEGRENZE_TAGE, ORDNER, lies_ergebnisse
from ..collect.geraete.klicklauf import LAUF_GELESEN
from ..collect.geraete.klickrohsatz import (
    QUELLE,
    ZUSTAND_NEU,
    ausbeute,
    tarifschluessel,
)
from ..collect.geraete.klickziele import geplante_anbieter
from ..geraete_model import Katalog
from ..tarif_bezug import Tarifbestand
from ..tco_model import Buendel, laufzeit_in_monaten
from .klick_geschwister import Schluessel, geschwister, mit_namen
from .tco_buendel import Buendelbilanz, aus_rohsaetzen

log = logging.getLogger(__name__)

UMGEBUNG = "TELCO_KLICK_ERGEBNISSE"
VERGLEICHSFELDER = (
    "geraet_zuzahlung",
    "geraet_monatsrate",
    "tarif_monatlich",
    "buendel_monatlich",
    "anschlusspreis",
    "tarif_bindung_monate",
)
WERTFELDER = (*VERGLEICHSFELDER, "tarif_phasen", "aktionen")
"""Was ein Satz zum Bündel beiträgt; ein Klick-Satz muss alle nennen, die der Adapter
nennt, um ihn zu ersetzen."""
CENT = 0.005
BEISPIELE = 8
GRUND_NICHT_HEUTE = "Datei vom {datum}, nicht von heute"
GRUND_VERALTET = "Datei vom {datum}, älter als {tage} Tage"
GRUND_ZUKUNFT = "Datei vom {datum}, nach heute"
GRUND_DATUM = "Datum der Datei unlesbar: {datum!r}"
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
        fehlend = [f for f in WERTFELDER if _nennt(adapter, f) and not _nennt(klick, f)]
        self.unvollstaendig += bool(fehlend)
        self.fehlend.update(fehlend)
        return bool(fehlend)

    def vergleiche(self, klick: dict, adapter: dict) -> None:
        """Zählt einen ersetzten Adaptersatz; Felder nur, wo beide einen Wert haben."""
        beide = [f for f in VERGLEICHSFELDER if _nennt(klick, f) and _nennt(adapter, f)]
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
    for daten in ergebnisse:
        eintrag, aus_datei = _datei(daten, katalog, heute)
        eintraege.append(eintrag)
        saetze.extend(aus_datei)
    eindeutig, mehrdeutig = _eindeutig(saetze)
    index: dict[Schluessel, list[int]] = {}
    for stelle, satz in enumerate(adapter):
        for schluessel in _adapterschluessel(satz, geraet):
            index.setdefault(schluessel, []).append(stelle)
    probe = Gegenprobe()
    andere_laufzeit = geschwister(index)
    ersetzt: set[int] = set()
    neu: list[dict] = []
    ohne_gegenstueck = 0
    for satz in eindeutig:
        schluessel = klickschluessel(satz)
        treffer = sorted(set(index.get(schluessel, [])))
        if not treffer:
            ohne_gegenstueck += 1
            neu += mit_namen(satz, schluessel, adapter, andere_laufzeit, UEBERNOMMEN)
        for stelle in treffer:
            alt = adapter[stelle]
            if probe.unvollstaendig_fuer(satz, alt):
                continue
            probe.vergleiche(satz, alt)
            ersetzt.add(stelle)
            neu.append({**satz, **{f: alt.get(f) for f in UEBERNOMMEN}})
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
        "gegenprobe": probe.als_daten(),
    }
    _protokolliere(bilanz)
    bleiben = [satz for stelle, satz in enumerate(adapter) if stelle not in ersetzt]
    return Zusammenfuehrung(bleiben + neu, bilanz)


def klickschluessel(satz: dict) -> Schluessel:
    """Der Schlüssel eines Klick-Rohsatzes (siehe Modulkopf)."""
    return (
        str(satz.get("anbieter")),
        str(satz.get("device_id")),
        satz.get("speicher_gb"),
        tarifschluessel(satz.get("tarif_name")),
        laufzeit_in_monaten(satz.get("laufzeit_monate")),
    )


def schluesseltext(schluessel: Schluessel) -> str:
    """Der Schlüssel als Text für Bilanz und Protokoll."""
    return "|".join("" if teil is None else str(teil) for teil in schluessel)


def alter_tage(datum: object, heute: str) -> int | None:
    """Tage von ``datum`` bis ``heute``; ``None``, wenn ``datum`` kein ISO-Datum ist."""
    try:
        return (date.fromisoformat(heute) - date.fromisoformat(str(datum))).days
    except ValueError:
        return None


def _datei(daten: dict, katalog: Katalog, heute: str) -> tuple[dict, list[dict]]:
    """Kopf einer Ergebnisdatei für die Bilanz und, wenn verwendet, ihre Rohsätze."""
    status = daten.get("laufstatus")
    datum = daten.get("datum")
    alter = alter_tage(datum, heute)
    eintrag = {
        "anbieter": daten.get("name"),
        "datum": datum,
        "alter_tage": alter,
        "laufstatus": status,
        "grund": daten.get("grund"),
        "ueberfaellig": list(daten.get("ueberfaellig") or []),
        "verwendet": False,
        "warum_nicht": None,
    }
    if alter is None:
        eintrag["warum_nicht"] = GRUND_DATUM.format(datum=datum)
    elif alter < 0:
        eintrag["warum_nicht"] = GRUND_ZUKUNFT.format(datum=datum)
    elif alter >= FRISCHEGRENZE_TAGE:
        grund = GRUND_VERALTET.format(datum=datum, tage=FRISCHEGRENZE_TAGE)
        eintrag["warum_nicht"] = grund
    elif alter > 0:
        eintrag["warum_nicht"] = GRUND_NICHT_HEUTE.format(datum=datum)
    elif status != LAUF_GELESEN:
        eintrag["warum_nicht"] = f"Lauf {status}: {daten.get('grund')}"
    if eintrag["warum_nicht"] is not None:
        return eintrag, []
    aus = ausbeute(daten, katalog)
    eintrag.update(aus.als_daten(), verwendet=True)
    return eintrag, aus.rohsaetze


def _eindeutig(saetze: list[dict]) -> tuple[list[dict], list[str]]:
    """Je Schlüssel ein Satz; verschiedene Werte auf einem Schlüssel gelten nicht."""
    gruppen: dict[Schluessel, list[dict]] = {}
    for satz in saetze:
        gruppen.setdefault(klickschluessel(satz), []).append(satz)
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


def _nennt(satz: dict, feld: str) -> bool:
    wert = satz.get(feld)
    return wert is not None and wert != []


def _vorrang(buendel: Buendel, eintrag: dict | None, heute: str) -> bool:
    """Ein Adapterbündel, dessen Bestandseintrag eine frische Klick-Messung ist."""
    if buendel.quelle_art == QUELLE or eintrag is None:
        return False
    if eintrag.get("quelle_art") != QUELLE:
        return False
    alter = alter_tage(eintrag.get("abgerufen_am"), heute)
    return alter is not None and 0 <= alter < FRISCHEGRENZE_TAGE


def _adapterschluessel(satz: dict, geraet: Geraet) -> list[Schluessel]:
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
