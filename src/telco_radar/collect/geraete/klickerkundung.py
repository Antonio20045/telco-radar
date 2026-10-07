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
Regel 4). Sperrt robots.txt die Seite, ist sie ``gesperrt``; zeigt sie kein
Bedienelement oder keinen Preis, ist sie ``leer``. Vor jeder Seite fragt die
``Laufpruefung`` (``klickparallel``), ob ein Gerätelauf oder Radarlauf ansteht oder
läuft; dann ist der Rest ``verschoben``, ohne Anfrage. Jeder Anbieter hat
``ZEIT_JE_ANBIETER_S``, jede Seite ``ZEIT_JE_SEITE_S``, beides gegen die Gesamtfrist
``ende`` (``time.monotonic``); danach lassen ``Fristschleuse`` und der Abruf von
robots.txt keine Anfrage mehr hinaus. Was nicht gelesen wurde, heißt so und ist nie
leer: ``nicht_besucht`` mit Grund; Abstand und Besuchszeit stehen nur im Index, wenn
robots.txt gelesen wurde. Screenshot und Seite gehören nur ins Artefakt des Laufs
(``scripts/erkundung_ablegen.py`` lässt sie vom öffentlichen Zweig).

Liegt unter ``karten`` eine Klick-Karte des Anbieters, erprobt die ``klickkartenprobe``
sie nach jeder gelesenen oder leeren Seite auf derselben Seite, mit Tor, Schleuse und
Zeitgrenze der Seite; ihr Ergebnis steht in ``karte-<n>.json``, ihr Status je Seite im
Index unter ``karte``. Endet die Probe gestört, gilt dasselbe wie nach Bot-Schutz der
Seite; ihre Cookie-Werte schwärzt die Ablage wie die der Seite.

Trägt eine Seite ``weiter``, folgt nach Seite und Kartenprobe ihre Folgeseite
(``klickfolgeseite``) als eigener Schritt mit eigener Nummer, eigenen Dateien und
``folge_von`` im Index, ohne Klick-Proben und ohne Kartenprobe, mit denselben Grenzen
für Zeit, Parallelläufe und Bot-Schutz. Ist die Ausgangsseite weder gelesen noch leer,
ist die Folgeseite ``nicht_besucht``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .. import http
from .basis import GeraeteAbrufFehler
from .klickablage import HOECHSTE_LISTE, Ablage
from .klickfolgeseite import (
    LAUF_BEFUND,
    Folge,
    Folgelauf,
    angabe,
    ohne_ausgang,
    plane,
)
from .klickkartenprobe import (
    NICHT_BESUCHT,
    Kartenprobe,
    Probenmittel,
    als_daten,
    indexeintrag,
    lade_karte,
    ohne_probe,
    probiere,
)
from .klicklauf import LAUF_GELESEN, LAUF_GESPERRT, LAUF_GESTOERT
from .klickparallel import Laufpruefung
from .klickseite import (
    GRUND_FRIST,
    LAUF_LEER,
    Fristschleuse,
    Seitenergebnis,
    Seitenlauf,
)
from .klickspur import ohne_geheimnisse
from .klicktor import Hostschleuse
from .klickziele import Erkundungsziel, Seitenziel
from .robots import RobotsWaechter, host_von

if TYPE_CHECKING:
    from playwright.sync_api import Browser

log = logging.getLogger(__name__)

ZEIT_JE_ANBIETER_S = 50 * 60
ZEIT_JE_SEITE_S = 25 * 60
MINDESTZEIT_SEITE_S = 3 * 60
GROESSE_JE_ANBIETER = 8_000_000
ROBOTS_FRIST_S = 20.0
VERSCHOBEN = "verschoben"
PRUEFUNG_AUS = "aus"
PRUEFUNG_AN = "vor jeder Seite"
GRUND_NACH_BOT = "nach Bot-Schutz keine weitere Anfrage (CLAUDE.md Regel 4)"

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
    *,
    laeufe: Laufpruefung | None,
    holer: Robotsholer = robots_holer,
    grenze: int = GROESSE_JE_ANBIETER,
    karten: Path | None = None,
) -> list[dict]:
    """Erkundet die Anbieter nacheinander; je Anbieter der Inhalt von ``index.json``.

    ``laeufe`` ist Pflicht; ``None`` schaltet die Parallellauf-Prüfung ausdrücklich ab
    (nur für lokale Läufe), und ``index.json`` sagt das. ``karten`` ist das Verzeichnis
    der Klick-Karten (``klickkartenprobe.KARTEN``); ohne es läuft keine Kartenprobe.
    """
    return [
        erkunde_anbieter(
            browser,
            z,
            uhr,
            holer(z.kennung or http.BOT_UA),
            ausgabe,
            ende,
            grenze,
            laeufe=laeufe,
            karten=karten,
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
    *,
    laeufe: Laufpruefung | None = None,
    karten: Path | None = None,
) -> dict:
    """Alle Seiten eines Anbieters; schreibt den Ordner, gibt ``index.json`` zurück."""
    start = time.monotonic()
    tag = uhr().date().isoformat()
    ablage = Ablage(ausgabe / ziel.schluessel / tag, grenze)
    gelesen: set[str] = set()
    anbieter_ende = min(ende, start + ZEIT_JE_ANBIETER_S)

    def hole_mit_frist(url: str) -> tuple[int, str]:
        if time.monotonic() >= schleuse.ende:
            raise GeraeteAbrufFehler(f"{GRUND_FRIST}, robots.txt nicht abgerufen")
        antwort = hole_robots(url)
        gelesen.add(host_von(url))
        return antwort

    waechter = RobotsWaechter(hole=hole_mit_frist)
    schleuse = Fristschleuse(
        Hostschleuse(waechter, uhr, ziel.rate_limit_sekunden), anbieter_ende
    )
    lage = lade_karte(karten, ziel.schluessel)
    mittel = Probenmittel(waechter, uhr, schleuse)
    seiten: list[dict] = []
    ausgang: dict[int, Seitenergebnis] = {}
    stopp: tuple[str, str] | None = None
    schritte = plane(ziel.seiten)
    for stelle, schritt in enumerate(schritte):
        nummer, seite, folge = schritt.nummer, schritt.seite, schritt.folge
        rest = anbieter_ende - time.monotonic()
        if stopp is None and rest < MINDESTZEIT_SEITE_S:
            stopp = NICHT_BESUCHT, f"{GRUND_FRIST}: noch {max(0, round(rest))} s"
        if stopp is None and laeufe is not None:
            belegt = laeufe()
            stopp = None if belegt is None else (VERSCHOBEN, belegt)
        offen = stopp
        if offen is None and folge is not None:
            grund = ohne_ausgang(ausgang.get(folge.von), folge.von)
            offen = None if grund is None else (NICHT_BESUCHT, grund)
        if offen is not None:
            probe = None if folge is not None else ohne_probe(lage, offen[1])
            eintrag = _nicht_besucht(nummer, seite, *offen, probe)
            seiten.append(_mit_folge(eintrag, folge, None))
            continue
        schleuse.setze(min(anbieter_ende, time.monotonic() + ZEIT_JE_SEITE_S))
        anteil = ablage.platz // (len(schritte) - stelle)
        if folge is None:
            ergebnis = Seitenlauf(browser, ziel, seite, waechter, uhr, schleuse).laufe()
            probe = probiere(browser, ziel, seite, lage, ergebnis, mittel)
            ausgang[nummer] = ergebnis
        else:
            ergebnis = Folgelauf(
                browser, ziel, seite, waechter, uhr, schleuse, folge.weiter
            ).laufe()
            probe = None
        eintrag = lege_ab(ablage, nummer, seite, ergebnis, anteil, probe)
        seiten.append(_mit_folge(eintrag, folge, ergebnis))
        if ergebnis.bot or (probe is not None and probe.bot):
            stopp = NICHT_BESUCHT, GRUND_NACH_BOT
    status, grund = gesamtstatus(seiten)
    adresse = ziel.seiten[0].adresse
    robots = host_von(adresse) in gelesen
    index = {
        "anbieter": ziel.schluessel,
        "name": ziel.name,
        "datum": tag,
        "status": status,
        "grund": grund,
        "kennung": ziel.kennung,
        "parallelpruefung": PRUEFUNG_AUS if laeufe is None else PRUEFUNG_AN,
        "robots_gelesen": robots,
        "abstand_sekunden": schleuse.abstand(adresse) if robots else None,
        "besuchszeit": _besuchszeit(waechter, adresse) if robots else None,
        "dauer_sekunden": round(time.monotonic() - start, 1),
        "zeitgrenze_sekunden": ZEIT_JE_ANBIETER_S,
        "seiten": seiten,
    }
    ablage.schreibe_index(index)
    log.info("Klick-Erkundung %s: %s %s", ziel.schluessel, status, grund or "")
    return index


def gesamtstatus(seiten: list[dict]) -> tuple[str, str | None]:
    """Gelesen nur, wenn jede Seite gelesen ist; sonst der schwerste Befund mit Seite.

    Gestört geht vor verschoben, verschoben vor einem Befund (Folgeseite); leer gilt,
    wenn jede andere Seite gelesen ist; gesperrt, wenn jede Seite gesperrt ist; jede
    andere Mischung heißt gestört.
    """
    offen = [s for s in seiten if s["status"] != LAUF_GELESEN]
    if not offen:
        return LAUF_GELESEN, None
    if all(s["status"] == LAUF_GESPERRT for s in seiten):
        return LAUF_GESPERRT, offen[0]["grund"]
    for status in (LAUF_GESTOERT, VERSCHOBEN, LAUF_BEFUND):
        erste = next((s for s in offen if s["status"] == status), None)
        if erste is not None:
            return status, f"Seite {erste['nummer']}: {erste['grund']}"
    if all(s["status"] == LAUF_LEER for s in offen):
        return LAUF_LEER, f"Seite {offen[0]['nummer']}: {offen[0]['grund']}"
    erste = next(s for s in offen if s["status"] != LAUF_LEER)
    return LAUF_GESTOERT, f"Seite {erste['nummer']}: {erste['grund']}"


def lege_ab(
    ablage: Ablage,
    nummer: int,
    seite: Seitenziel,
    ergebnis: Seitenergebnis,
    anteil: int,
    probe: Kartenprobe | None = None,
) -> dict:
    """Schreibt die Dateien einer Seite in ``anteil`` Bytes; gibt ihren Indexeintrag.

    Die Kartenprobe kommt vor Mitschnitt, Screenshot und Seite; ohne ``probe`` ist der
    Kartenstatus ``None``. Cookie-Werte von Seite und Probe sind vorher gemerkt.
    """
    ablage.merke_cookies(ergebnis.cookies)
    if probe is not None:
        ablage.merke_cookies(probe.cookies)
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
    karte = None if probe is None else als_daten(probe)
    if karte is not None:
        name = f"karte-{nummer}.json"
        dateien["karte"] = ablage.schreibe_json(name, karte, frei())
    platz = frei() - len(ablage.json_bytes(ergebnis.anfragen))
    antworten = ablage.passe_mitschnitt(ergebnis.mitschnitt, platz)
    mitschnitt = {"anfragen": ergebnis.anfragen, "antworten": antworten}
    dateien["mitschnitt"] = ablage.schreibe_json(
        f"mitschnitt-{nummer}.json", mitschnitt, frei()
    )
    if ergebnis.bild is not None:
        dateien["screenshot"] = ablage.schreibe(
            f"seite-{nummer}.png", ergebnis.bild, frei()
        )
    if ergebnis.html is not None:
        name = f"seite-{nummer}.html.gz"
        dateien["html"] = ablage.schreibe_html(name, ergebnis.html, frei())
    return {
        "nummer": nummer,
        "geraet": seite.geraet,
        "speicher_gb": seite.speicher_gb,
        "adresse": ohne_geheimnisse(seite.adresse),
        "endadresse": ergebnis.endadresse,
        "status": ergebnis.status,
        "grund": ergebnis.grund,
        "bot_schutz": ergebnis.bot,
        "http_status": ergebnis.http_status,
        "ruhe": ergebnis.ruhe,
        "dateien": dateien,
        "zaehlung": _zaehlung(ergebnis),
        "verworfen": ergebnis.verworfen[:HOECHSTE_LISTE],
        "gescheitert": ergebnis.gescheitert[:HOECHSTE_LISTE],
        "karte": None if probe is None else indexeintrag(probe, dateien.get("karte")),
    }


def _zaehlung(ergebnis: Seitenergebnis) -> dict:
    inventar = ergebnis.inventar
    je_art: dict[str, int] = {}
    for gruppe in inventar.gruppen if inventar else []:
        je_art[gruppe.art] = je_art.get(gruppe.art, 0) + 1
    return {
        "anfragen": len(ergebnis.anfragen),
        "verworfen": len(ergebnis.verworfen),
        "gescheitert": len(ergebnis.gescheitert),
        "mitschnitt": len(ergebnis.mitschnitt),
        "elemente": None if inventar is None else inventar.gesamt,
        "gruppen_je_art": None if inventar is None else je_art,
        "preis_kandidaten": None if inventar is None else inventar.preise_gesamt,
        "klicks": None if inventar is None else len(ergebnis.klicks),
    }


def _mit_folge(
    eintrag: dict, folge: Folge | None, ergebnis: Seitenergebnis | None
) -> dict:
    """Eine Folgeseite nennt ihre Ausgangsseite und ihren Weiter-Klick."""
    if folge is None:
        return eintrag
    weiter = angabe(folge.weiter) if ergebnis is None else ergebnis.weiter
    return eintrag | {"folge_von": folge.von, "weiter": weiter}


def _nicht_besucht(
    nummer: int,
    seite: Seitenziel,
    status: str,
    grund: str,
    probe: Kartenprobe | None,
) -> dict:
    return {
        "nummer": nummer,
        "geraet": seite.geraet,
        "speicher_gb": seite.speicher_gb,
        "adresse": ohne_geheimnisse(seite.adresse),
        "status": status,
        "grund": grund,
        "dateien": {},
        "karte": None if probe is None else indexeintrag(probe, None),
    }


def _besuchszeit(waechter: RobotsWaechter, adresse: str) -> str | None:
    """Die Besuchszeit laut robots.txt; ``None``, wenn der Host keine nennt."""
    regeln = waechter.regeln(adresse)
    return None if regeln.visit_von is None else regeln.fenster_text
