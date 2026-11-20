"""Gegenprobe gespeicherter Bündelpreise im echten Browser (``gegenprobe.yml``).

AUFRUF
------
    PYTHONPATH=src python scripts/gegenprobe.py [--root .] [--datum JJJJ-MM-TT]
        [--je-anbieter 5] [--anbieter o2 ...] [--hoechstens N] [--bilder ORDNER]
        [--hochladen] [--job-start EPOCHE] [--job-frist-sekunden 3000]

Gewählt wird nach ``gegenprobe.auswahl``: jedes Bündel, dessen Gesamtkosten oder
Posten sich zum vorigen Messtag geändert haben (Historie
``data/state/geraete_tco_historie/<datum>.jsonl``), dazu je Anbieter
``STICHPROBE_JE_ANBIETER`` unveränderte, zufällig, aber fest je Datum. Je Bündel geht
``collect.geraete.gegenprobe_browser.lies`` den Kundenweg, der Leser des Anbieters
(``gegenprobe_sicht.LESER``) liest den sichtbaren Text, ``gegenprobe.vergleiche``
vergleicht mit dem Bestand ``geraete_tco.json``. Ergebnis:
``data/state/gegenprobe/<datum>.jsonl``; die Bilder gehen mit ``--hochladen`` ins
Release ``gegenprobe-<datum>`` (``beleg_ablage.Gh``), sonst bleiben sie in ``--bilder``.

Zeit (Harte Regel 8): ``--job-frist-sekunden`` ist die Restzeit des Jobs ab
``--job-start``; ein Bündel beginnt nur, wenn ``ZEIT_JE_BUENDEL_S`` davor noch Platz
hat. Was danach übrig ist, steht als „nicht prüfbar: Zeitbudget“ in der Datei, nie
als stilles Fehlen.

Exit-Code 0: gelaufen (auch mit Abweichungen, das sind Befunde); 2: Eingabe unlesbar.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path

import yaml

from telco_radar import gegenprobe as gp
from telco_radar import tco_historie
from telco_radar.analyze.geraete_pruefstatus import buendel_aus_satz
from telco_radar.collect.geraete.gegenprobe_browser import (
    Gesperrt,
    Lesung,
    NichtPruefbar,
)
from telco_radar.collect.geraete.gegenprobe_sicht import LESER
from telco_radar.collect.geraete.gegenprobe_wege import lies
from telco_radar.collect.geraete.robots import RobotsWaechter, host_von
from telco_radar.tco_model import kosten_ueber

FEHLER_EINGABE = 2
TCO_DATEI = Path("data") / "state" / "geraete_tco.json"
HISTORIE = Path("data") / "state" / "geraete_tco_historie"
QUELLEN = Path("config") / "geraete_quellen.yaml"
JOB_MINUTEN = 60
"""``timeout-minutes`` des Jobs in ``gegenprobe.yml`` (ein Test hält beide gleich)."""
PUFFER_S = 600
"""Einrichten des Läufers, Hochladen und Commit nach dem letzten Bündel."""
JOB_FRIST_S = JOB_MINUTEN * 60 - PUFFER_S
ZEIT_JE_BUENDEL_S = 90
"""So lange darf ein Kundenweg höchstens dauern (Laden, Klicks, Bild)."""
MINDESTABSTAND_S = 5.0
"""Abstand zweier Seitenaufrufe beim selben Host, wenn robots.txt nicht mehr nennt."""
KENNUNG_ROBOTS = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"


def kennungen(root: Path) -> dict[str, str]:
    """User-Agent je Anbieter aus ``geraete_quellen.yaml`` (sonst der des Browsers)."""
    daten = yaml.safe_load((root / QUELLEN).read_text(encoding="utf-8")) or {}
    eintraege = daten.get("quellen") or daten.get("anbieter") or []
    return {
        str(e.get("name")): str(e["user_agent"])
        for e in eintraege
        if isinstance(e, dict) and e.get("user_agent")
    }


def lies_historie(
    ordner: Path, datum: str
) -> tuple[list[dict], list[dict], str | None]:
    """Zeilen des Tages ``datum``, je Bündel die letzte Messung davor
    (``gegenprobe.letzte_messungen``, wie die Seite „Preisänderungen“) und das Datum
    des vorigen Messtags (oder None)."""
    tage = tco_historie.tage(ordner.parent / f"{ordner.name}.jsonl")
    vorher = [(tag, saetze) for tag, saetze in tage if tag < datum]
    heute = next((saetze for tag, saetze in tage if tag == datum), [])
    zuletzt = gp.letzte_messungen(vorher)
    return heute, [dict(z) for z in zuletzt.values()], vorher[-1][0] if vorher else None


def _norm(text: str) -> str:
    return "".join(z for z in text.lower() if z.isalnum())


def anderer_tarif(gespeichert: str, gelesen: str | None) -> bool:
    """Zeigt die Seite einen anderen Tarif als den des Bündels?"""
    if not gelesen:
        return False
    a, b = _norm(gespeichert), _norm(gelesen)
    return not (a.startswith(b) or b.startswith(a))


def gesamt(satz: dict) -> float | None:
    """Gesamtkosten eines Satzes über ``kosten_ueber`` (None bei Lücke oder Unfug)."""
    try:
        return kosten_ueber(buendel_aus_satz(satz)).gesamt
    except (TypeError, ValueError, KeyError):
        return None


def mit_gelesenen(satz: dict, gelesen: dict) -> dict:
    """Der Satz mit den gelesenen Posten; weicht der Tarif ab, gelten keine Phasen."""
    neu = {**satz, **gelesen}
    tarif = gelesen.get("tarif_monatlich")
    alt = satz.get("tarif_monatlich")
    if tarif is not None and alt is not None and not gp.gleich(tarif, alt):
        neu["tarif_phasen"] = None
    return neu


Lesen = Callable[[str, dict], Lesung]
"""(Anbieter-Schlüssel, Bestandssatz) -> Lesung; im Lauf ``gegenprobe_browser.lies``."""


def pruefe(
    lesen: Lesen, satz: dict, anlass: str, datum: str
) -> tuple[gp.Ergebnis, Lesung | None]:
    """Eine Gegenprobe: Kundenweg, Leser, Vergleich. Nie eine Ausnahme nach außen."""
    schluessel = gp.anbieter_aus_id(satz["id"])
    basis = {
        "datum": datum,
        "buendel_id": satz["id"],
        "anbieter": satz.get("anbieter") or "",
        "anlass": anlass,
        "sku_id": satz.get("sku_id") or "",
        "tarif_name": satz.get("tarif_name") or "",
        "laufzeit_monate": satz.get("laufzeit_monate"),
        "gespeichert": gp.gespeicherte_werte(satz),
        "gesamt_gespeichert": gesamt(satz),
        "geprueft_um": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    leser = LESER.get(schluessel)
    if leser is None:
        return gp.Ergebnis(
            **basis, status=gp.NICHT_PRUEFBAR, grund=gp.GRUND_KEIN_LESER
        ), None
    try:
        lesung = lesen(schluessel, satz)
    except Gesperrt as fehler:
        grund = f"{gp.GRUND_GESPERRT} ({fehler})"
        return gp.Ergebnis(**basis, status=gp.NICHT_PRUEFBAR, grund=grund), None
    except NichtPruefbar as fehler:
        return gp.Ergebnis(**basis, status=gp.NICHT_PRUEFBAR, grund=str(fehler)), None
    sicht = leser(lesung.text)
    gelesen = sicht.werte()
    extra = {
        "seite": lesung.seite,
        "text": lesung.text[: gp.TEXT_HOECHSTENS],
        "gelesen": {**gelesen, "tarif_name": sicht.tarif_name, "roh": sicht.roh},
        "bild_fehlt": lesung.bild_fehlt,
    }
    if anderer_tarif(satz.get("tarif_name") or "", sicht.tarif_name):
        grund = f"Die Seite zeigt einen anderen Tarif: {sicht.tarif_name}"
        ergebnis = gp.Ergebnis(**basis, **extra, status=gp.NICHT_PRUEFBAR, grund=grund)
        return ergebnis, lesung
    status, abweichungen, fehlt, grund = gp.vergleiche(basis["gespeichert"], gelesen)
    nicht_gelesen = [
        f for f in gp.FELDER if satz.get(f) is not None and f not in gelesen
    ]
    ergebnis = gp.Ergebnis(
        **basis,
        **extra,
        status=status,
        grund=grund,
        abweichungen=abweichungen,
        nicht_gelesen=nicht_gelesen,
        gesamt_gelesen=gesamt(mit_gelesenen(satz, gelesen))
        if status != gp.NICHT_PRUEFBAR
        else None,
    )
    return ergebnis, lesung


def main(argumente: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--datum")
    parser.add_argument("--je-anbieter", type=int, default=gp.STICHPROBE_JE_ANBIETER)
    parser.add_argument("--anbieter", action="append", default=[])
    parser.add_argument("--hoechstens", type=int)
    parser.add_argument("--bilder", type=Path)
    parser.add_argument("--hochladen", action="store_true")
    parser.add_argument("--ausgabe", type=Path, help="statt der Tagesdatei (lokal)")
    parser.add_argument("--aufnehmen", type=Path, help="Ordner für Test-Fixtures")
    parser.add_argument("--job-start", type=float)
    parser.add_argument("--job-frist-sekunden", type=float, default=JOB_FRIST_S)
    args = parser.parse_args(argumente)
    beginn = time.time()
    verstrichen = max(0.0, beginn - (args.job_start or beginn))
    frist = min(args.job_frist_sekunden, JOB_FRIST_S) - verstrichen - ZEIT_JE_BUENDEL_S
    ende = time.monotonic() + max(0.0, frist)
    try:
        bestand = json.loads((args.root / TCO_DATEI).read_text(encoding="utf-8"))
        datum = (
            args.datum or bestand.get("updated") or datetime.now(UTC).date().isoformat()
        )
        date.fromisoformat(datum)
        saetze = {b["id"]: b for b in bestand["buendel"]}
        heute, vortag, vortag_datum = lies_historie(args.root / HISTORIE, datum)
        ua = kennungen(args.root)
    except (OSError, ValueError, KeyError) as fehler:
        print(f"Gegenprobe: Eingabe unlesbar: {fehler}", file=sys.stderr)
        return FEHLER_EINGABE
    wahl = [
        (bid, anlass)
        for bid, anlass in gp.auswahl(datum, heute, vortag, args.je_anbieter)
        if bid in saetze
        and (not args.anbieter or gp.anbieter_aus_id(bid) in args.anbieter)
    ][: args.hoechstens]
    print(
        f"Gegenprobe {datum} (Vortag {vortag_datum}): {len(wahl)} Bündel, davon "
        f"{sum(a == gp.ANLASS_AENDERUNG for _, a in wahl)} Preisänderungen"
    )
    ergebnisse, bilder = laufe(args, wahl, saetze, datum, ua, ende)
    veroeffentliche(args, datum, ergebnisse, bilder)
    gp.schreibe_tag(args.ausgabe or gp.tagesdatei(args.root, datum), ergebnisse)
    for e in ergebnisse:
        print(f"{e.status:15} {e.anbieter:35} {e.buendel_id} {e.grund or ''}")
    return 0


def laufe(args, wahl, saetze, datum, ua, ende):
    """Geht die Auswahl durch, bis die Frist reicht; danach Zeitbudget-Zeilen."""
    from playwright.sync_api import sync_playwright

    from telco_radar.collect import http

    def hole(url: str) -> tuple[int, str]:
        antwort = http.get(
            url,
            headers={"User-Agent": KENNUNG_ROBOTS},
            timeout=20,
            follow_redirects=True,
        )
        return antwort.status_code, antwort.text

    robots = RobotsWaechter(hole)
    aufnehmen = args.aufnehmen is not None
    zuletzt: dict[str, float] = {}
    ergebnisse: list[gp.Ergebnis] = []
    bilder: dict[str, bytes] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for bid, anlass in wahl:
                satz = saetze[bid]
                if time.monotonic() > ende:
                    ergebnisse.append(
                        _ohne_lauf(satz, anlass, datum, gp.GRUND_ZEITBUDGET)
                    )
                    continue
                url = satz.get("quelle_url") or ""
                darf, grund = robots.darf(url, datetime.now(UTC))
                if not darf:
                    ergebnisse.append(
                        _ohne_lauf(satz, anlass, datum, f"{gp.GRUND_ROBOTS}: {grund}")
                    )
                    continue
                host = host_von(url)
                warte = zuletzt.get(host, 0.0) + robots.abstand(url, MINDESTABSTAND_S)
                time.sleep(max(0.0, warte - time.monotonic()))
                zuletzt[host] = time.monotonic()
                kennung = ua.get(satz.get("anbieter") or "")
                ergebnis, lesung = pruefe(
                    partial(lies, browser, kennung=kennung, aufnehmen=aufnehmen),
                    satz,
                    anlass,
                    datum,
                )
                if lesung is not None and lesung.bild is not None:
                    bilder[bid] = lesung.bild
                if aufnehmen and lesung is not None and lesung.html:
                    args.aufnehmen.mkdir(parents=True, exist_ok=True)
                    datei = args.aufnehmen / f"{gp.anbieter_aus_id(bid)}.html"
                    datei.write_text(lesung.html + "\n", encoding="utf-8")
                ergebnisse.append(ergebnis)
                print(f"  {ergebnis.status:15} {bid}", flush=True)
        finally:
            browser.close()
    return ergebnisse, bilder


def _ohne_lauf(satz: dict, anlass: str, datum: str, grund: str) -> gp.Ergebnis:
    return gp.Ergebnis(
        datum=datum,
        buendel_id=satz["id"],
        anbieter=satz.get("anbieter") or "",
        status=gp.NICHT_PRUEFBAR,
        anlass=anlass,
        grund=grund,
        sku_id=satz.get("sku_id") or "",
        tarif_name=satz.get("tarif_name") or "",
        laufzeit_monate=satz.get("laufzeit_monate"),
        gespeichert=gp.gespeicherte_werte(satz),
        gesamt_gespeichert=gesamt(satz),
    )


def veroeffentliche(args, datum, ergebnisse, bilder) -> None:
    """Legt die Bilder ab und lädt sie mit ``--hochladen`` ins Tages-Release."""
    ordner = args.bilder or Path(tempfile.gettempdir()) / "gegenprobe-bilder" / datum
    ordner.mkdir(parents=True, exist_ok=True)
    dateien: dict[str, Path] = {}
    for e in ergebnisse:
        bild = bilder.get(e.buendel_id)
        if bild is None:
            continue
        endung = "webp" if bild[:4] == b"RIFF" else "png"
        datei = ordner / f"{gp.kennung(e.buendel_id, datum)}.{endung}"
        datei.write_bytes(bild)
        dateien[e.buendel_id] = datei
    if not args.hochladen:
        for e in ergebnisse:
            if e.buendel_id in dateien:
                e.bild_fehlt = f"nicht veröffentlicht (lokal: {dateien[e.buendel_id]})"
        return
    from telco_radar.beleg_ablage import Gh, GhFehler

    gh = Gh()
    tag = gp.release_tag(datum)
    try:
        gh.release_anlegen(tag, f"Gegenprobe {datum}")
    except GhFehler as fehler:
        print(f"Gegenprobe: Release {tag} nicht angelegt (gibt es ihn?): {fehler}")
    try:
        gh.hochladen(tag, list(dateien.values()))
    except GhFehler as fehler:
        print(f"Gegenprobe: Bilder nicht hochgeladen: {fehler}", file=sys.stderr)
        for e in ergebnisse:
            if e.buendel_id in dateien:
                e.bild_fehlt = "Bild nicht veröffentlicht (Release gestört)"
        return
    for e in ergebnisse:
        if e.buendel_id in dateien:
            e.bild = gp.bild_url(datum, dateien[e.buendel_id].name)


if __name__ == "__main__":
    sys.exit(main())
