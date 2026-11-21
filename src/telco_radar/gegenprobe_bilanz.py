"""Bilanz der Gegenprobe je Anbieter und Tag: EINE Stelle für Seite, Wächter, Bericht.

``zusammenfassung`` zählt je Anbieter-Schlüssel über die angezeigten Bündel
(``angezeigte``: frisch nach ``report.geraete_tco_karten.ist_frisch``, derselben
Definition wie die Seite): wie viele im Fenster gegengeprüft sind
(``gegenprobe_fenster.im_fenster`` über ``Gegenproben.zum_preis``, wie die Seite die
Gegenprobe eines Preises findet), mit welchem Status, wie viele überfällig sind und
wie viele davon nicht prüfbar mit welchem Grund (``gegenprobe_reihe.fehlerart``).
Dazu aus den Läufen des Tages Seitenbesuche, Sekunden je Besuch, Bündel je Besuch und
jeder Ausfall (Schutzschalter, Sperre) mit Grund. Anteile rechnet nur dieses Modul;
wer sie zeigt oder prüft, liest die Felder der Datei
``data/state/gegenprobe/bilanz/<datum>.json``.

``lege_ab`` ist der Abschluss jedes Laufs: Zeilen in die Tagesdatei ergänzen
(``gegenprobe.ergaenze_tag``), die Läufe des Tages fortschreiben, Bilanz neu rechnen.
Derselbe Weg für den einzelnen Job und für das Ablegen der Teildateien einer Matrix.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

from . import gegenprobe as gp
from .analyze.geraete_pruefstatus import buendel_aus_satz
from .gegenprobe_fenster import GEGENPROBE_FENSTER_TAGE, Gegenproben, im_fenster
from .gegenprobe_reihe import fehlerart
from .tco_model import kosten_ueber

BILANZ_ORDNER = gp.ORDNER / "bilanz"
FORMAT = 1
ZAEHLER = (
    "angezeigt",
    "im_fenster",
    *gp.GEPRUEFT,
    "ueberfaellig",
    "nicht_pruefbar",
    "heute_geprueft",
    "besuche",
    "buendel_besucht",
)


def gesamt_von(satz: Mapping) -> float | None:
    """Gesamtkosten eines Satzes über ``kosten_ueber`` (None bei Lücke oder Unfug)."""
    try:
        return kosten_ueber(buendel_aus_satz(satz)).gesamt
    except (TypeError, ValueError, KeyError):
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
    besuche = e["besuche"]
    e["sekunden_je_besuch"] = round(e["sekunden"] / besuche, 1) if besuche else None
    e["buendel_je_besuch"] = (
        round(e["buendel_besucht"] / besuche, 2) if besuche else None
    )
    return e


def _leer() -> dict:
    return {
        **dict.fromkeys(ZAEHLER, 0),
        "sekunden": 0.0,
        "gruende": Counter(),
        "ausfall": [],
    }


def _zaehle(e: dict, datum: str, satz: Mapping, gegenproben: Gegenproben) -> None:
    bid = str(satz["id"])
    preis = gesamt_von(satz)
    e["angezeigt"] += 1
    probe = gegenproben.zum_preis(bid, preis, gp.GEPRUEFT)
    if probe is not None and im_fenster(datum, probe.datum):
        e["im_fenster"] += 1
        e[probe.status] += 1
        e["heute_geprueft"] += int(probe.datum == datum)
        return
    e["ueberfaellig"] += 1
    versuch = gegenproben.zum_preis(bid, preis, gp.VERSUCHT)
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
    for lauf in laeufe:
        if lauf.get("datum") != datum:
            continue
        e = je[str(lauf["anbieter"])]
        e["besuche"] += int(lauf.get("besuche") or 0)
        e["buendel_besucht"] += int(lauf.get("buendel") or 0)
        e["sekunden"] += float(lauf.get("sekunden") or 0.0)
        if lauf.get("ausfall"):
            e["ausfall"].append(str(lauf["ausfall"]))
    summe = _leer()
    for e in je.values():
        for name in (*ZAEHLER, "sekunden"):
            summe[name] += e[name]
        summe["gruende"].update(e["gruende"])
        summe["ausfall"] += e["ausfall"]
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
    alle_laeufe = [*(lies_bilanz(pfad).get("laeufe") or []), *map(dict, laeufe)]
    proben = Gegenproben(gp.lies_alle(wurzel / gp.ORDNER).values())
    bilanz = {
        **zusammenfassung(datum, angezeigt, proben, alle_laeufe),
        "laeufe": alle_laeufe,
    }
    pfad.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(bilanz, ensure_ascii=False, indent=1, sort_keys=True)
    pfad.write_text(text + "\n", encoding="utf-8")
    return bilanz
