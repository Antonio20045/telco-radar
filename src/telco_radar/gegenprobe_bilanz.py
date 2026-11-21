"""Bilanz der Gegenprobe je Anbieter und Tag: EINE Stelle für Seite, Wächter, Bericht.

``zusammenfassung`` zählt je Anbieter-Schlüssel über die angezeigten Bündel
(``angezeigte``: frisch nach ``report.geraete_tco_karten.ist_frisch``, derselben
Definition wie die Seite): wie viele im Fenster gegengeprüft sind
(``gegenprobe_fenster.im_fenster`` über ``Gegenproben.letzte_gute``, dieselbe Zeile,
die die Seite als Gegenprobe des Preises zeigt), mit welchem Status, wie viele
überfällig sind und wie viele davon nicht prüfbar mit welchem Grund
(``gegenprobe_reihe.fehlerart``).
Dazu ``mit_bild``: wie viele davon ein Bild der ganzen Konfiguration haben
(``gegenprobe_belege.bild_ganz``, dasselbe Bild, das die Seite am Preis zeigt).
Dazu aus den Läufen des Tages Seitenbesuche, Sekunden je Besuch, Bündel je Besuch und
jeder Ausfall (Schutzschalter, Sperre) mit Grund. Anteile rechnet nur dieses Modul;
wer sie zeigt oder prüft, liest die Felder der Datei
``data/state/gegenprobe/bilanz/<datum>.json``.

``lege_ab`` ist der Abschluss jedes Laufs: Zeilen in die Tagesdatei ergänzen
(``gegenprobe.ergaenze_tag``), die Läufe des Tages fortschreiben, Bilanz neu rechnen
und die verlinkten Bilder schreiben (``gegenprobe_belege.verlinkte``).
Derselbe Weg für den einzelnen Job und für das Ablegen der Teildateien einer Matrix.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

from . import gegenprobe as gp
from . import tco_historie
from .analyze.geraete_pruefstatus import buendel_aus_satz
from .gegenprobe_belege import bild_ganz, schreibe_verlinkt, verlinkte
from .gegenprobe_fenster import GEGENPROBE_FENSTER_TAGE, Gegenproben, im_fenster
from .gegenprobe_reihe import fehlerart
from .tco_model import kosten_ueber

log = logging.getLogger(__name__)

BILANZ_ORDNER = gp.ORDNER / "bilanz"
HISTORIE = Path("data") / "state" / "geraete_tco_historie.jsonl"
FORMAT = 1
ZAEHLER = (
    "angezeigt",
    "im_fenster",
    *gp.GEPRUEFT,
    "ueberfaellig",
    "nicht_pruefbar",
    "heute_geprueft",
    "mit_bild",
)
MESSUNG = ("besuche", "buendel_besucht", "sekunden", "zurueckgestellt")
"""Was die Läufe des Tages messen; fehlt ein Lauf oder ein Wert, ist es None mit
Grund in ``messung_fehlt``, nie 0."""
KEIN_LAUF = "kein Lauf an diesem Tag"


def gesamt_von(satz: Mapping) -> float | None:
    """Gesamtkosten eines Satzes über ``kosten_ueber``; None bei Lücke, bei einem
    unlesbaren Satz None mit Protokoll (der Preis ist dann seine Einzelposten)."""
    try:
        return kosten_ueber(buendel_aus_satz(satz)).gesamt
    except (TypeError, ValueError, KeyError) as fehler:
        log.warning(
            "Gegenprobe: Gesamtkosten von %s unlesbar: %s", satz.get("id"), fehler
        )
        return None


def angezeigte(buendel: Iterable[Mapping], datum: str) -> list[Mapping]:
    """Die Bündel, die die Seite an ``datum`` als frisch zeigt (``ist_frisch``)."""
    from .report.geraete_tco_karten import ist_frisch

    return [
        b
        for b in buendel
        if b.get("id")
        and ist_frisch(
            str(b.get("abgerufen_am") or ""), datum, str(b.get("herleitung") or "")
        )
    ]


def bilanzdatei(wurzel: Path, datum: str) -> Path:
    """``data/state/gegenprobe/bilanz/<datum>.json`` unter ``wurzel``."""
    return wurzel / BILANZ_ORDNER / f"{datum}.json"


def _anteil(zahl: int, von: int) -> float | None:
    return round(zahl / von, 4) if von else None


def _abschluss(e: dict) -> dict:
    """Die abgeleiteten Felder eines Zählers (prüfbar, Anteile, je Besuch)."""
    pruefbar = e["angezeigt"] - e["nicht_pruefbar"]
    e["pruefbar"] = pruefbar
    e["anteil_im_fenster"] = _anteil(e["im_fenster"], pruefbar)
    e["anteil_bestaetigt"] = _anteil(e[gp.BESTAETIGT], pruefbar)
    e["sekunden_je_besuch"] = _je(e["sekunden"], e["besuche"], 1)
    e["buendel_je_besuch"] = _je(e["buendel_besucht"], e["besuche"], 2)
    return e


def _je(menge: float | None, besuche: float | None, stellen: int) -> float | None:
    """Menge je Besuch; None ohne Besuch oder ohne gemessene Menge."""
    if menge is None or not besuche:
        return None
    return round(menge / besuche, stellen)


def _leer() -> dict:
    return {
        **dict.fromkeys(ZAEHLER, 0),
        **dict.fromkeys(MESSUNG),
        "messung_fehlt": KEIN_LAUF,
        "gruende": Counter(),
        "ausfall": [],
    }


def _messe(e: dict, laeufe: list[Mapping]) -> None:
    """Besuche, Bündel und Sekunden der Läufe eines Anbieters; ein Lauf ohne Wert
    (Teildatei fehlt, Messung fehlt) macht die Summe zur benannten Lücke."""
    if not laeufe:
        return
    werte = {
        "besuche": "besuche",
        "buendel_besucht": "buendel",
        "sekunden": "sekunden",
        "zurueckgestellt": "zurueckgestellt",
    }
    for feld, schluessel in werte.items():
        e[feld] = 0
        for lauf in laeufe:
            e[feld] = _plus(e[feld], lauf.get(schluessel))
    luecke = [
        str(lauf.get("ausfall") or "Lauf ohne Messung")
        for lauf in laeufe
        if any(lauf.get(k) is None for k in werte.values())
    ]
    e["messung_fehlt"] = "; ".join(luecke) if luecke else None


def _plus(a: float | None, b: float | None) -> float | None:
    """Summe zweier Messwerte; fehlt einer (None), ist die Summe nicht gemessen."""
    return None if a is None or b is None else a + b


def _zaehle(e: dict, datum: str, satz: Mapping, gegenproben: Gegenproben) -> None:
    bid = str(satz["id"])
    preis = gesamt_von(satz)
    e["angezeigt"] += 1
    gute = gegenproben.letzte_gute(bid, preis, satz)
    if gute is not None and im_fenster(datum, gute.datum):
        e["im_fenster"] += 1
        e[gute.status] += 1
        e["heute_geprueft"] += int(gute.datum == datum)
        e["mit_bild"] += int(bild_ganz(gute))
        return
    e["ueberfaellig"] += 1
    versuch = gegenproben.letzter_versuch(bid, preis, satz)
    if (
        versuch is not None
        and versuch.status == gp.NICHT_PRUEFBAR
        and im_fenster(datum, versuch.datum)
    ):
        e["nicht_pruefbar"] += 1
        e["gruende"][fehlerart(versuch.grund or "")] += 1


def zusammenfassung(
    datum: str,
    angezeigt: Iterable[Mapping],
    gegenproben: Gegenproben,
    laeufe: Iterable[Mapping],
) -> dict:
    """Die Bilanz des Tages je Anbieter-Schlüssel und in Summe (Modulkopf)."""
    je: dict[str, dict] = defaultdict(_leer)
    namen: dict[str, str] = {}
    for satz in angezeigt:
        schluessel = gp.anbieter_aus_id(str(satz["id"]))
        namen.setdefault(schluessel, str(satz.get("anbieter") or schluessel))
        _zaehle(je[schluessel], datum, satz, gegenproben)
    je_lauf: dict[str, list[Mapping]] = defaultdict(list)
    for lauf in laeufe:
        if lauf.get("datum") == datum:
            je_lauf[str(lauf["anbieter"])].append(lauf)
            if lauf.get("ausfall"):
                je[str(lauf["anbieter"])]["ausfall"].append(str(lauf["ausfall"]))
    for schluessel in list(je):
        _messe(je[schluessel], je_lauf[schluessel])
    summe = _leer()
    _messe(
        summe, [dict.fromkeys(("besuche", "buendel", "sekunden", "zurueckgestellt"), 0)]
    )
    fehlend = []
    for s, e in je.items():
        for name in ZAEHLER:
            summe[name] += e[name]
        for name in MESSUNG:
            summe[name] = _plus(summe[name], e[name])
        if e["messung_fehlt"]:
            fehlend.append(f"{s}: {e['messung_fehlt']}")
        summe["gruende"].update(e["gruende"])
        summe["ausfall"] += e["ausfall"]
    summe["messung_fehlt"] = "; ".join(fehlend) if fehlend else None
    anbieter = {
        s: {"name": namen.get(s, s), **_abschluss(e), "gruende": dict(e["gruende"])}
        for s, e in sorted(je.items())
    }
    return {
        "format": FORMAT,
        "datum": datum,
        "fenster_tage": GEGENPROBE_FENSTER_TAGE,
        "anbieter": anbieter,
        "summe": {**_abschluss(summe), "gruende": dict(summe["gruende"])},
    }


def lies_bilanz(pfad: Path) -> dict:
    """Die Bilanzdatei eines Tages; {} ohne Datei, ``GegenprobeFehler`` bei Unfug."""
    if not pfad.exists():
        return {}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except ValueError as fehler:
        raise gp.GegenprobeFehler(f"{pfad.name}: {fehler}") from fehler
    if not isinstance(daten, dict):
        raise gp.GegenprobeFehler(f"{pfad.name}: kein Objekt")
    return daten


def juengste(ordner: Path, stichtag: str = "") -> tuple[str, dict] | None:
    """(Tag, Bilanz) der jüngsten Bilanzdatei in ``ordner`` (``BILANZ_ORDNER``) bis
    ``stichtag`` (ohne: die jüngste); None ohne Datei, ``GegenprobeFehler`` bei einer
    unlesbaren."""
    dateien = sorted(
        p for p in ordner.glob("*.json") if not stichtag or p.stem <= stichtag
    )
    if not dateien:
        return None
    return dateien[-1].stem, lies_bilanz(dateien[-1])


def _laufkennung(lauf: Mapping) -> str:
    """Ein Eintrag je Lauf UND Anbieter (ein Sammeljob hat mehrere Anbieter)."""
    kennung = lauf.get("lauf_id")
    if kennung:
        return f"{kennung}|{lauf.get('anbieter')}"
    return json.dumps(dict(lauf), sort_keys=True, ensure_ascii=False)


def fuehre_laeufe(alt: Iterable[Mapping], neu: Iterable[Mapping]) -> list[dict]:
    """Die Läufe des Tages ohne Doppel: derselbe Lauf eines Anbieters (``lauf_id``,
    Anbieter) zählt einmal, auch wenn seine Teildatei zweimal abgelegt wird. Ein
    Platzhalter „Teildatei fehlt“ (``platzhalter``) fällt weg, sobald es am selben Tag
    einen gemessenen Lauf dieses Anbieters gibt, gleich in welcher Reihenfolge."""
    je: dict[str, dict] = {}
    for lauf in [*alt, *neu]:
        je[_laufkennung(lauf)] = dict(lauf)
    gemessen = {
        (v.get("datum"), v.get("anbieter"))
        for v in je.values()
        if not v.get("platzhalter")
    }
    return [
        v
        for v in je.values()
        if not (
            v.get("platzhalter") and (v.get("datum"), v.get("anbieter")) in gemessen
        )
    ]


def lege_ab(
    wurzel: Path,
    datum: str,
    ergebnisse: Iterable[gp.Ergebnis],
    laeufe: Iterable[Mapping],
    angezeigt: list[Mapping],
) -> dict:
    """Ergänzt Tagesdatei und Läufe des Tages und schreibt die Bilanz neu."""
    gp.ergaenze_tag(gp.tagesdatei(wurzel, datum), ergebnisse)
    pfad = bilanzdatei(wurzel, datum)
    alle_laeufe = fuehre_laeufe(lies_bilanz(pfad).get("laeufe") or [], laeufe)
    proben = Gegenproben(gp.lies_alle(wurzel / gp.ORDNER).values())
    bilanz = {
        **zusammenfassung(datum, angezeigt, proben, alle_laeufe),
        "laeufe": alle_laeufe,
    }
    pfad.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(bilanz, ensure_ascii=False, indent=1, sort_keys=True)
    pfad.write_text(text + "\n", encoding="utf-8")
    tage = tco_historie.tage(wurzel / HISTORIE)
    schreibe_verlinkt(
        wurzel, datum, verlinkte(datum, angezeigt, gesamt_von, proben, tage)
    )
    return bilanz
