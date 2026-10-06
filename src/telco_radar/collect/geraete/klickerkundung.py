"""Klick-Erkundung (Datenkonzept Geräteradar, Schritt 5a): Material für Klick-Karten.

Je Anbieter (``klickziele``) und Produktseite öffnet ``erkunde_anbieter`` einen Kontext
wie der Klick-Crawler (``klickkontext``) mit demselben Tor (``klicktor``): robots.txt
samt Crawl-delay und Visit-time je Anfrage, Vorabladen aus, keine Tarnung, als
Kopfzeile nur der User-Agent aus ``geraete_quellen.yaml`` (``klickseite``). Nach Laden
und Ruhe lehnt sie eine Einwilligungsabfrage ab und hält fest: die gerenderte Seite
(gzip), einen Screenshot des Fensters, Bedienelemente in Gruppen und Preis-Kandidaten
(``klickinventar``), die Klick-Proben (``klickproben``) und den Mitschnitt aller
Anfragen mit den Körpern der JSON- und Textantworten (``klickspur``). Alles landet
über ``klickablage`` unter ``<ausgabe>/<anbieter>/<JJJJ-MM-TT>/`` mit ``index.json``.

Bot-Schutz (Hauptseite mit 202, 4xx außer 404/410 oder 5xx, Challenge-Muster, oder eine
Antwort der eigenen Website mit 403/429 oder Challenge) beendet die Seite als
``gestoert``; danach geht für diesen Anbieter keine Anfrage mehr hinaus (CLAUDE.md
Regel 4). Sperrt robots.txt die Seite, ist sie ``gesperrt``. Jeder Anbieter hat
``ZEIT_JE_ANBIETER_S``, jede Seite ``ZEIT_JE_SEITE_S``, beides gegen die Gesamtfrist
``ende`` (``time.monotonic``); die ``Fristschleuse`` lässt danach keine Anfrage mehr
hinaus. Was nicht gelesen wurde, heißt so und ist nie leer: ``nicht_besucht`` mit Grund.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .. import http
from .klickablage import Ablage
from .klicklauf import LAUF_GELESEN, LAUF_GESPERRT, LAUF_GESTOERT
from .klickseite import GRUND_FRIST, Fristschleuse, Seitenergebnis, Seitenlauf
from .klickspur import als_daten, ohne_geheimnisse
from .klicktor import Hostschleuse
from .klickziele import Erkundungsziel, Seitenziel
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import Browser

log = logging.getLogger(__name__)

ZEIT_JE_ANBIETER_S = 50 * 60
ZEIT_JE_SEITE_S = 25 * 60
MINDESTZEIT_SEITE_S = 3 * 60
GROESSE_JE_ANBIETER = 8_000_000
ROBOTS_FRIST_S = 20.0
NICHT_BESUCHT = "nicht_besucht"
GRUND_NACH_BOT = "nach Bot-Schutz keine weitere Anfrage (CLAUDE.md Regel 4)"
HOECHSTE_LISTE = 200

Robotsholer = Callable[[str], Callable[[str], tuple[int, str]]]


def robots_holer(kennung: str) -> Callable[[str], tuple[int, str]]:
    """Holt robots.txt mit ``kennung``: ein Versuch, kein Kennungswechsel."""

    def hole(url: str) -> tuple[int, str]:
        kopf = {"User-Agent": kennung}
        antwort = http.get(
            url, headers=kopf, timeout=ROBOTS_FRIST_S, follow_redirects=True
        )
        return antwort.status_code, antwort.text

    return hole


def erkunde(
    browser: Browser,
    ziele: list[Erkundungsziel],
    uhr: Callable[[], datetime],
    ausgabe: Path,
    ende: float,
    holer: Robotsholer = robots_holer,
    grenze: int = GROESSE_JE_ANBIETER,
) -> list[dict]:
    """Erkundet die Anbieter nacheinander; je Anbieter der Inhalt von ``index.json``."""
    return [
        erkunde_anbieter(
            browser, z, uhr, holer(z.kennung or http.BOT_UA), ausgabe, ende, grenze
        )
        for z in ziele
    ]


def erkunde_anbieter(
    browser: Browser,
    ziel: Erkundungsziel,
    uhr: Callable[[], datetime],
    hole_robots: Callable[[str], tuple[int, str]],
    ausgabe: Path,
    ende: float,
    grenze: int = GROESSE_JE_ANBIETER,
) -> dict:
    """Alle Seiten eines Anbieters; schreibt den Ordner, gibt ``index.json`` zurück."""
    start = time.monotonic()
    tag = uhr().date().isoformat()
    ablage = Ablage(ausgabe / ziel.schluessel / tag, grenze)
    waechter = RobotsWaechter(hole=hole_robots)
    anbieter_ende = min(ende, start + ZEIT_JE_ANBIETER_S)
    innen = Hostschleuse(waechter, uhr, ziel.rate_limit_sekunden)
    schleuse = Fristschleuse(innen, anbieter_ende)
    seiten: list[dict] = []
    stopp: str | None = None
    for nummer, seite in enumerate(ziel.seiten, 1):
        rest = anbieter_ende - time.monotonic()
        if stopp is None and rest < MINDESTZEIT_SEITE_S:
            stopp = f"{GRUND_FRIST}: noch {max(0, round(rest))} s"
        if stopp is not None:
            seiten.append(_nicht_besucht(nummer, seite, stopp))
            continue
        schleuse.setze(min(anbieter_ende, time.monotonic() + ZEIT_JE_SEITE_S))
        anteil = ablage.platz // (len(ziel.seiten) - nummer + 1)
        lauf = Seitenlauf(browser, ziel, seite, waechter, uhr, schleuse)
        ergebnis = lauf.laufe()
        seiten.append(_lege_ab(ablage, nummer, seite, ergebnis, lauf, anteil))
        if ergebnis.bot:
            stopp = GRUND_NACH_BOT
    status, grund = gesamtstatus(seiten)
    adresse = ziel.seiten[0].adresse
    index = {
        "anbieter": ziel.schluessel,
        "name": ziel.name,
        "datum": tag,
        "status": status,
        "grund": grund,
        "kennung": ziel.kennung,
        "abstand_sekunden": schleuse.abstand(adresse),
        "besuchszeit": _besuchszeit(waechter, adresse),
        "dauer_sekunden": round(time.monotonic() - start, 1),
        "zeitgrenze_sekunden": ZEIT_JE_ANBIETER_S,
        "seiten": seiten,
    }
    ablage.schreibe_index(index)
    log.info("Klick-Erkundung %s: %s %s", ziel.schluessel, status, grund or "")
    return index


def gesamtstatus(seiten: list[dict]) -> tuple[str, str | None]:
    """Gelesen nur, wenn jede Seite gelesen ist; gesperrt, wenn jede gesperrt ist."""
    offen = [s for s in seiten if s["status"] != LAUF_GELESEN]
    if not offen:
        return LAUF_GELESEN, None
    if all(s["status"] == LAUF_GESPERRT for s in seiten):
        return LAUF_GESPERRT, offen[0]["grund"]
    erste = next((s for s in offen if s["status"] == LAUF_GESTOERT), offen[0])
    return LAUF_GESTOERT, f"Seite {erste['nummer']}: {erste['grund']}"


def _lege_ab(
    ablage: Ablage,
    nummer: int,
    seite: Seitenziel,
    ergebnis: Seitenergebnis,
    lauf: Seitenlauf,
    anteil: int,
) -> dict:
    """Schreibt die Dateien einer Seite in ``anteil`` Bytes; gibt ihren Indexeintrag."""
    ablage.merke_cookies(ergebnis.cookies)
    start = ablage.belegt
    dateien: dict[str, str | None] = {}

    def frei() -> int:
        return anteil - (ablage.belegt - start)

    inventar = ergebnis.inventar
    if inventar is not None:
        name = f"bedienelemente-{nummer}.json"
        dateien["bedienelemente"] = ablage.schreibe_json(
            name, inventar.als_daten(), frei()
        )
        preise = {"preise_gesamt": inventar.preise_gesamt, "preise": inventar.preise}
        dateien["preise"] = ablage.schreibe_json(
            f"preise-{nummer}.json", preise, frei()
        )
        klicks = {
            "einwilligung": ergebnis.einwilligung,
            "vermerk": ergebnis.klick_vermerk,
            "proben": ergebnis.klicks,
        }
        dateien["klicks"] = ablage.schreibe_json(
            f"klicks-{nummer}.json", klicks, frei()
        )
    if ergebnis.bild is not None:
        dateien["screenshot"] = ablage.schreibe(
            f"seite-{nummer}.png", ergebnis.bild, frei()
        )
    if ergebnis.html is not None:
        name = f"seite-{nummer}.html.gz"
        dateien["html"] = ablage.schreibe_html(name, ergebnis.html, frei())
    anfragen = als_daten(lauf.spur.eintraege)
    platz = frei() - len(ablage.json_bytes(anfragen))
    antworten = ablage.passe_mitschnitt(lauf.spur.mitschnitt, platz)
    mitschnitt = {"anfragen": anfragen, "antworten": antworten}
    dateien["mitschnitt"] = ablage.schreibe_json(
        f"mitschnitt-{nummer}.json", mitschnitt, frei()
    )
    return {
        "nummer": nummer,
        "geraet": seite.geraet,
        "speicher_gb": seite.speicher_gb,
        "adresse": ohne_geheimnisse(seite.adresse),
        "endadresse": ergebnis.endadresse,
        "status": ergebnis.status,
        "grund": ergebnis.grund,
        "bot_schutz": ergebnis.bot,
        "http_status": lauf.tor.haupt_status,
        "ruhe": ergebnis.ruhe,
        "dateien": dateien,
        "zaehlung": _zaehlung(ergebnis, lauf),
        "verworfen": [
            {"url": ohne_geheimnisse(v.url), "grund": v.grund}
            for v in lauf.lauf.verworfen[:HOECHSTE_LISTE]
        ],
        "gescheitert": [
            {"url": ohne_geheimnisse(g.url), "grund": g.grund}
            for g in lauf.lauf.gescheitert[:HOECHSTE_LISTE]
        ],
    }


def _zaehlung(ergebnis: Seitenergebnis, lauf: Seitenlauf) -> dict:
    inventar = ergebnis.inventar
    je_art: dict[str, int] = {}
    for gruppe in inventar.gruppen if inventar else []:
        je_art[gruppe.art] = je_art.get(gruppe.art, 0) + 1
    return {
        "anfragen": len(lauf.spur.eintraege),
        "verworfen": len(lauf.lauf.verworfen),
        "gescheitert": len(lauf.lauf.gescheitert),
        "mitschnitt": len(lauf.spur.mitschnitt),
        "elemente": None if inventar is None else inventar.gesamt,
        "gruppen_je_art": None if inventar is None else je_art,
        "preis_kandidaten": None if inventar is None else inventar.preise_gesamt,
        "klicks": None if inventar is None else len(ergebnis.klicks),
    }


def _nicht_besucht(nummer: int, seite: Seitenziel, grund: str) -> dict:
    return {
        "nummer": nummer,
        "geraet": seite.geraet,
        "speicher_gb": seite.speicher_gb,
        "adresse": ohne_geheimnisse(seite.adresse),
        "status": NICHT_BESUCHT,
        "grund": grund,
        "dateien": {},
    }


def _besuchszeit(waechter: RobotsWaechter, adresse: str) -> str | None:
    """Die Besuchszeit laut robots.txt; ``None``, wenn der Host keine nennt."""
    regeln = waechter.regeln(adresse)
    return None if regeln.visit_von is None else regeln.fenster_text
