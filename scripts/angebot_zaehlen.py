"""Angebotszählung im Browser je Anbieter (Abnahmekriterium 1, Stufe 2).

Aufruf (Workflow-Vorlage ``angebot.yml``, ein Job je Anbieter)::

    PYTHONPATH=src python scripts/angebot_zaehlen.py --root . --anbieter telekom \
        --job-start "$JOB_START" --job-frist-sekunden 2700

Lokal (sparsam, nie Produktionsdaten committen; immer mit ``PYTHONPATH=src``)::

    PYTHONPATH=src python scripts/angebot_zaehlen.py --anbieter congstar \
        --seiten https://www.congstar.de/geraete/apple/apple-iphone-17/ \
        --ausgabe /tmp/angebot --aufnehmen /tmp/angebot/dom

Zählt im echten Chromium, was ein Kunde sieht: die Smartphone-Übersicht bis zum Ende,
je Modellseite Speicher, Tarife und Laufzeiten (``telco_radar.geraete_angebot``).
Ehrliche Kennung (Browserkennung plus ``TelcoRadar/1.0``), robots.txt samt
Crawl-delay und Visit-time, Mindestabstand je Host (``MINDESTABSTAND_S`` oder
``rate_limit_sekunden`` aus ``config/geraete_quellen.yaml``). Eine Schutzseite beendet
den Anbieter benannt („gesperrt“), nie umgangen.

Zeitbudget (CLAUDE.md Regel 8): Ende = früheres von Jobfrist (``--job-start`` +
``--job-frist-sekunden``) und Beginn des Sperrfensters (Klick-Lauf, Gerätelauf,
Gegenprobe auf denselben Hosts) minus ``PUFFER_SPERRE_S``. Im Sperrfenster gestartet,
zählt das Skript nichts und schreibt keine Datei (eine gültige Zählung des Messtags
bleibt stehen). Eine Modellseite beginnt
nur mit ``SEKUNDEN_JE_SEITE_RESERVE`` Rest; die übrigen stehen als „zeitgrenze“ mit
Grund in der Datei. ``JOB_MINUTEN`` ist das ``timeout-minutes`` der Vorlage.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import yaml
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from telco_radar import geraete_angebot as ga
from telco_radar.geraete_angebot import wege
from telco_radar.geraete_angebot.konkurrenz import Konkurrenz, NichtPruefbar
from telco_radar.geraete_angebot.lesen import (
    LeserFehler,
    ist_smartphone,
    name_aus_adresse,
)
from telco_radar.geraete_angebot.sitzung import Sitzung
from telco_radar.geraete_angebot.tor import Gesperrt, Tor

JOB_MINUTEN = {"tarifwelt": 150}
JOB_MINUTEN_STANDARD = 50
PUFFER_S = 300
"""Einrichtung (Python, Chromium) und Schreiben nach dem Zählen."""
PUFFER_SPERRE_S = 180
WARTENDE_STATUS = ("in_progress", "queued", "waiting", "requested", "pending")
"""Läufe in diesen Zuständen besuchen den Host gleich oder gerade (GitHub-Status)."""
SERIENFEHLER = 3
"""So viele gestörte Seiten in Folge beenden den Anbieter („Schutzschalter“)."""


def job_frist(schluessel: str) -> int:
    """``--job-frist-sekunden`` der Vorlage: Jobminuten minus Puffer."""
    return JOB_MINUTEN.get(schluessel, JOB_MINUTEN_STANDARD) * 60 - PUFFER_S


def abstand(root: Path, name: str) -> float:
    """Mindestabstand je Host: ``rate_limit_sekunden`` des Anbieters, mindestens
    ``MINDESTABSTAND_S`` (Konfiguration direkt gelesen, ohne den Sammler)."""
    try:
        daten = yaml.safe_load(
            (root / "config" / "geraete_quellen.yaml").read_text("utf-8")
        )
    except (OSError, yaml.YAMLError) as fehler:
        print(f"::warning::Konfiguration nicht lesbar ({fehler}), Mindestabstand gilt")
        return ga.MINDESTABSTAND_S
    eintraege = [e for v in (daten or {}).values() if isinstance(v, list) for e in v]
    eintrag = next(
        (e for e in eintraege if isinstance(e, dict) and e.get("name") == name), {}
    )
    return max(ga.MINDESTABSTAND_S, float(eintrag.get("rate_limit_sekunden") or 0.0))


def seiten_aus(kacheln: list[ga.Kachel], hoechstens: int | None) -> list[ga.Seite]:
    """Je Smartphone-Kachel ohne Paket eine Seite (Pakete zählen nur als Modell)."""
    seiten = [
        ga.Seite(k.url, k.titel)
        for k in kacheln
        if ist_smartphone(k.titel) and not k.paket
    ]
    return seiten[:hoechstens] if hoechstens else seiten


def _status(z: ga.Zaehlung) -> str:
    gelesen = sum(1 for s in z.seiten if s.status == ga.GELESEN)
    if z.laufstatus in (ga.GESPERRT, ga.GESTOERT, ga.ZEITGRENZE):
        return z.laufstatus
    ganz, beleg = ga.uebersicht_pruefung(z)
    if not ganz and z.kacheln:
        z.grund = z.grund or beleg
    if gelesen == len(z.seiten) and z.kacheln and ganz:
        return ga.GELESEN
    return ga.TEILWEISE if gelesen else ga.GESTOERT


def gh_abfrage() -> Callable[[str], int] | None:
    """Zahl laufender und wartender Läufe eines Workflows über ``gh api`` (nur
    lesend); ``None`` ohne ``GITHUB_REPOSITORY`` oder ``gh`` (lokal)."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo or not shutil.which("gh"):
        return None

    def abfrage(workflow: str) -> int:
        zahl = 0
        for status in WARTENDE_STATUS:
            pfad = f"repos/{repo}/actions/workflows/{workflow}/runs?status={status}"
            try:
                aus = subprocess.run(
                    ["gh", "api", pfad, "--jq", ".total_count"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as fehler:
                raise NichtPruefbar(str(fehler)) from fehler
            if aus.returncode != 0 or not aus.stdout.strip().isdigit():
                raise NichtPruefbar((aus.stderr or aus.stdout).strip()[:150])
            zahl += int(aus.stdout.strip())
        return zahl

    return abfrage


def kurzgrund(fehler: Exception) -> str:
    """Lesbarer Grund: der Text eines Lesers, bei Browserfehlern die erste Zeile."""
    if isinstance(fehler, LeserFehler):
        return str(fehler)[:300]
    zeile = str(fehler).splitlines()[0] if str(fehler) else type(fehler).__name__
    return f"Browserfehler: {zeile}"[:300]


def zaehle_seiten(
    z: ga.Zaehlung, s: Sitzung, weg, ende: float, mono, konkurrenz: Konkurrenz
) -> None:
    """Liest jede Seite, solange Zeit ist; Sperre, Serienfehler und ein paralleler
    Lauf auf demselben Host beenden benannt."""
    fehler_folge, abbruch = 0, None
    for seite in z.seiten:
        if abbruch is None and (anderer := konkurrenz.zwischendurch(ende)):
            abbruch = f"nicht gezählt: {anderer}"
        if abbruch:
            seite.status, seite.grund = ga.NICHT_GELESEN, abbruch
            continue
        if ende - mono() < ga.SEKUNDEN_JE_SEITE_RESERVE:
            seite.status = ga.ZEITGRENZE
            seite.grund = "Zeitbudget des Jobs erschöpft (Jobfrist oder Sperrfenster)"
            continue
        beginn = mono()
        try:
            weg(s, seite)
        except Gesperrt as sperre:
            seite.status, seite.grund = ga.GESPERRT, str(sperre)
            z.laufstatus, z.grund = ga.GESPERRT, str(sperre)
            abbruch = f"nicht gezählt: {sperre}"
            continue
        except (LeserFehler, PlaywrightError) as fehler:
            fehler_folge += 1
            seite.status, seite.grund = ga.GESTOERT, kurzgrund(fehler)
            print(f"::warning::{z.schluessel} {seite.url}: {seite.grund}")
            if fehler_folge >= SERIENFEHLER:
                abbruch = f"nicht gezählt: {SERIENFEHLER} Seiten in Folge gestört"
            continue
        fehler_folge = 0
        seite.status, seite.sekunden = ga.GELESEN, round(mono() - beginn, 1)
        print(f"{z.schluessel}: {seite.titel}: {seite.sekunden} s")


def tarifuebersicht(z: ga.Zaehlung, s: Sitzung) -> None:
    """o2: Tarife der Tarifübersicht mit „Handy hinzufügen“; ein Ausfall wird
    benannt, die Produktseiten-Auswahl gilt dann allein."""
    try:
        z.tarifuebersicht = wege.o2_tarifuebersicht(s)
    except (LeserFehler, PlaywrightError) as fehler:
        z.tarifuebersicht_grund = f"Tarifübersicht nicht gelesen: {kurzgrund(fehler)}"
        print(f"::warning::o2 {z.tarifuebersicht_grund}")


def lauf(
    args, anbieter: ga.Anbieter, jetzt: datetime, ende: float, mono
) -> ga.Zaehlung:
    """Ein Anbieter: Übersicht (oder ``--seiten``), dann die Modellseiten."""
    z = ga.Zaehlung(
        anbieter.schluessel, ga.messtag(jetzt), jetzt.isoformat(timespec="seconds")
    )
    z.uebersicht = anbieter.uebersicht
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        probe = browser.new_page()
        kennung = f"{probe.evaluate('navigator.userAgent')} {ga.KENNUNG}"
        probe.close()
        kontext = browser.new_context(
            user_agent=kennung,
            viewport={"width": 1440, "height": 1000},
            locale="de-DE",
            service_workers="block",
        )

        def hole_robots(url: str) -> tuple[int, str]:
            try:
                antwort = kontext.request.get(url, timeout=20000)
            except PlaywrightError as fehler:
                print(f"::warning::robots.txt {url}: {fehler}")
                return 0, ""
            return antwort.status, antwort.text()

        tor = Tor(
            hole_robots,
            lambda: datetime.now(UTC),
            mono,
            time.sleep,
            abstand(Path(args.root), anbieter.abstand_konfig),
        )
        s = Sitzung(kontext.new_page(), tor, args.aufnehmen)
        konkurrenz = Konkurrenz(gh_abfrage(), anbieter.schluessel, mono, time.sleep)
        try:
            if anderer := konkurrenz.frei(ende):
                raise Gesperrt(f"nicht gezählt: {anderer}")
            if args.seiten:
                z.kacheln = [ga.Kachel(u, name_aus_adresse(u)) for u in args.seiten]
            else:
                beginn = mono()
                z.kacheln, z.genannt, z.uebersicht_ende = wege.uebersicht(
                    anbieter.schluessel, s, anbieter.uebersicht
                )
                z.sekunden_uebersicht = round(mono() - beginn, 1)
                if anbieter.schluessel == "o2":
                    tarifuebersicht(z, s)
                print(
                    f"{z.schluessel}: Übersicht {len(z.kacheln)} Kacheln, "
                    f"genannt {z.genannt}, {z.sekunden_uebersicht} s"
                )
        except Gesperrt as sperre:
            gesperrt = not str(sperre).startswith("nicht gezählt")
            z.laufstatus = ga.GESPERRT if gesperrt else ga.ZEITGRENZE
            z.grund = str(sperre)
        except (LeserFehler, PlaywrightError) as fehler:
            z.laufstatus, z.grund = ga.GESTOERT, f"Übersicht: {kurzgrund(fehler)}"
        z.seiten = [] if args.nur_uebersicht else seiten_aus(z.kacheln, args.hoechstens)
        if z.laufstatus == ga.NICHT_GELESEN:
            weg = wege.SEITEN[anbieter.schluessel]
            zaehle_seiten(z, s, weg, ende, mono, konkurrenz)
        z.konkurrenz = konkurrenz.vermerk or "keine parallelen Läufe auf diesem Host"
        browser.close()
    z.laufstatus = _status(z)
    z.gezaehlt_bis = datetime.now(UTC).isoformat(timespec="seconds")
    return z


def main(argv: list[str] | None = None) -> int:
    """Zählt einen Anbieter, schreibt ``data/state/angebot/<messtag>-<key>.json``."""
    p = argparse.ArgumentParser(description="Angebotszaehlung im Browser")
    p.add_argument("--root", default=".")
    p.add_argument("--anbieter", required=True, choices=sorted(ga.ANBIETER))
    p.add_argument("--job-start", type=float, default=None)
    p.add_argument("--job-frist-sekunden", type=float, default=None)
    p.add_argument("--hoechstens", type=int, default=None)
    p.add_argument("--nur-uebersicht", action="store_true")
    p.add_argument("--seiten", nargs="*", default=None)
    p.add_argument("--ausgabe", type=Path, default=None)
    p.add_argument("--aufnehmen", type=Path, default=None)
    args = p.parse_args(argv)
    anbieter = ga.ANBIETER[args.anbieter]
    jetzt = datetime.now(UTC)
    ausgabe = args.ausgabe or Path(args.root) / "data" / "state"
    sperre = ga.sperre_ab(jetzt, anbieter.sperrfenster)
    if sperre is None:
        von, bis = anbieter.sperrfenster
        print(
            f"{anbieter.schluessel}: im Sperrfenster {von:02d}-{bis:02d} Uhr UTC "
            "gestartet (Klick-Lauf, Gerätelauf, Gegenprobe), nichts gezählt, "
            "keine Datei geschrieben"
        )
        return 0
    start = args.job_start if args.job_start else time.time()
    frist = (
        args.job_frist_sekunden
        if args.job_frist_sekunden
        else job_frist(anbieter.schluessel)
    )
    rest = min(
        start + frist - time.time(), (sperre - jetzt).total_seconds() - PUFFER_SPERRE_S
    )
    ende = time.monotonic() + rest
    print(f"{anbieter.schluessel}: Messtag {ga.messtag(jetzt)}, Restzeit {int(rest)} s")
    z = lauf(args, anbieter, jetzt, ende, time.monotonic)
    print(
        f"Datei: {ga.schreibe(ausgabe, z)} ({z.laufstatus}, {z.grund or 'ohne Befund'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
