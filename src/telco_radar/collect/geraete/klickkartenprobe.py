"""Kartenprobe der Klick-Erkundung (Datenkonzept Geräteradar, Schritt 5).

Die Anbieterseiten sind nur aus GitHub Actions erreichbar; dort erprobt die Erkundung
eine Klick-Karte gleich mit. Liegt ``KARTEN/<schluessel>.yaml`` vor, lädt
``lade_karte`` sie einmal je Anbieter (``klickkarte.lade_klickkarte``): eine kaputte
Karte ist ``kartenfehler`` mit Grund, ohne Karte heißt es ``keine_karte``, und es
ändert sich nichts. Nach Inventar und Klick-Proben einer gelesenen oder leeren Seite
lässt ``probiere`` den Klick-Crawler (``klickcrawler.klicke_durch``) auf derselben Seite
laufen, mit demselben Tor samt Beobachtung (``klickseite.beobachte``: eine 403 oder 429
der eigenen Website ist Bot-Schutz), derselben Schleuse samt Crawl-delay und Zeitgrenze
der Seite (``klickseite.Fristschleuse.offen``), denselben robots-Regeln und demselben
User-Agent, für höchstens ``HOECHSTE_KOMBINATIONEN_PROBE`` Kombinationen; jede weitere
heißt ``nicht besucht``. Ist die Zeit vor der Probe um, heißt sie ``nicht_besucht``.
Endet der Lauf ``gestoert`` (Bot-Schutz, Challenge, fehlender Kanarienwert, gescheiterte
Preisantwort, Strukturbruch), ist ``Kartenprobe.bot`` wahr, und für den Anbieter geht
keine Anfrage mehr hinaus (CLAUDE.md Regel 4). Set-Cookie- und Kontextwerte der Probe
stehen in ``Kartenprobe.cookies``; die Ablage schwärzt sie vor jedem Schreiben.
``als_daten`` ist der Inhalt von ``karte-<n>.json``, ``indexeintrag`` der Kartenstatus
einer Seite in ``index.json``. Belege archiviert die Probe nicht (kein Konto); ihr
Status bleibt, wie der Crawler ihn setzt.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .klickablage import HOECHSTE_LISTE
from .klickbeleg import werte_als_json
from .klickcrawler import GRUND_NICHT_BESUCHT, klicke_durch
from .klickkarte import (
    DIMENSIONEN,
    WERTFELDER,
    Klickkarte,
    KlickkartenFehler,
    lade_klickkarte,
)
from .klicklauf import (
    BEFUND,
    ERFASST,
    LAUF_GELESEN,
    LAUF_GESTOERT,
    NICHT_ANGEBOTEN,
    NICHT_ERFASST,
    Klicklauf,
    Kombiergebnis,
)
from .klickseite import GRUND_FRIST, LAUF_LEER, Fristschleuse, Seitenergebnis, beobachte
from .klickspur import ohne_geheimnisse
from .klicktext import Preiswerte
from .klickziele import Erkundungsziel, Seitenziel
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import APIResponse, Browser, Request

log = logging.getLogger(__name__)

KARTEN = Path("config") / "klickkarten"
HOECHSTE_KOMBINATIONEN_PROBE = 12
KEINE_KARTE = "keine_karte"
KARTENFEHLER = "kartenfehler"
GELADEN = "geladen"
GELAUFEN = "gelaufen"
NICHT_BESUCHT = "nicht_besucht"
GRUND_VOR_PROBE = f"{GRUND_FRIST}, Probe nicht begonnen"
GRUND_OHNE_VERZEICHNIS = "kein Kartenverzeichnis angegeben"
BELEGE = "nicht archiviert (kein Konto)"
SEITE_PROBIERBAR = frozenset({LAUF_GELESEN, LAUF_LEER})
STATUS_JE_KOMBINATION = (ERFASST, NICHT_ANGEBOTEN, NICHT_ERFASST, BEFUND)


@dataclass(frozen=True)
class Kartenlage:
    """Die Klick-Karte eines Anbieters oder warum es keine gibt."""

    datei: str
    karte: Klickkarte | None = None
    status: str = KEINE_KARTE
    grund: str | None = None


@dataclass(frozen=True)
class Kartenprobe:
    """Was die Probe einer Seite ergab; ``lauf`` nur, wenn der Crawler lief."""

    status: str
    datei: str
    grund: str | None = None
    lauf: Klicklauf | None = None
    karte: Klickkarte | None = None
    cookies: frozenset[str] = frozenset()

    @property
    def bot(self) -> bool:
        """Wahr, wenn der Lauf ``gestoert`` endete; dann keine Anfrage mehr."""
        return self.lauf is not None and self.lauf.status == LAUF_GESTOERT


@dataclass(frozen=True)
class Probenmittel:
    """Was die Probe mit der Seite teilt: robots-Wächter, Uhr, Schleuse samt Frist."""

    waechter: RobotsWaechter
    uhr: Callable[[], datetime]
    schleuse: Fristschleuse


def lade_karte(karten: Path | None, schluessel: str) -> Kartenlage:
    """Die Karte ``<karten>/<schluessel>.yaml``; fehlt oder bricht sie, mit Grund."""
    datei = f"{schluessel}.yaml"
    if karten is None:
        return Kartenlage(datei, grund=GRUND_OHNE_VERZEICHNIS)
    pfad = karten / datei
    if not pfad.is_file():
        return Kartenlage(datei, grund=f"{datei} nicht vorhanden")
    try:
        karte = lade_klickkarte(pfad)
    except KlickkartenFehler as fehler:
        grund = f"Feld {fehler.feld}: {fehler.grund}" if fehler.feld else fehler.grund
    except (OSError, UnicodeDecodeError) as fehler:
        grund = f"nicht lesbar ({type(fehler).__name__})"
    else:
        return Kartenlage(datei, karte, GELADEN)
    log.warning("Klick-Karte %s: %s", datei, grund)
    return Kartenlage(datei, status=KARTENFEHLER, grund=grund)


def ohne_probe(lage: Kartenlage, grund: str) -> Kartenprobe:
    """Kartenstatus einer Seite, auf der die Probe nicht lief, mit Grund."""
    if lage.karte is None:
        return Kartenprobe(lage.status, lage.datei, lage.grund)
    return Kartenprobe(NICHT_BESUCHT, lage.datei, grund)


def probiere(
    browser: Browser,
    ziel: Erkundungsziel,
    seite: Seitenziel,
    lage: Kartenlage,
    ergebnis: Seitenergebnis,
    mittel: Probenmittel,
) -> Kartenprobe:
    """Lässt den Klick-Crawler mit der Karte über die Seite laufen; wirft nie."""
    if lage.karte is None or ergebnis.status not in SEITE_PROBIERBAR:
        return ohne_probe(lage, f"Seite {ergebnis.status}: {ergebnis.grund}")
    if not mittel.schleuse.offen(seite.adresse):
        return ohne_probe(lage, GRUND_VOR_PROBE)
    cookies: set[str] = set()

    def beobachter(anfrage: Request, antwort: APIResponse) -> str | None:
        return beobachte(anfrage, antwort, seite.adresse, cookies)

    lauf = klicke_durch(
        browser,
        seite.adresse,
        lage.karte,
        mittel.waechter,
        mittel.uhr,
        schleuse=mittel.schleuse,
        kennung=ziel.kennung,
        hoechste=HOECHSTE_KOMBINATIONEN_PROBE,
        frist=mittel.schleuse.offen,
        beobachter=beobachter,
        cookies=cookies,
        modell=seite.modell,
    )
    log.info("Kartenprobe %s %s: %s", ziel.schluessel, seite.adresse, lauf.status)
    kekse = frozenset(cookies)
    return Kartenprobe(GELAUFEN, lage.datei, lauf.grund, lauf, lage.karte, kekse)


def indexeintrag(probe: Kartenprobe, datei: str | None) -> dict:
    """Der Kartenstatus einer Seite; ``datei`` ist ``karte-<n>.json`` oder ``None``."""
    eintrag: dict = {"status": probe.status, "karte": probe.datei, "grund": probe.grund}
    if probe.lauf is not None:
        eintrag["datei"] = datei
        eintrag["laufstatus"] = probe.lauf.status
        eintrag["bot_schutz"] = probe.bot
        eintrag["zaehlung"] = zaehlung(probe.lauf)
    return eintrag


def als_daten(probe: Kartenprobe) -> dict | None:
    """Inhalt von ``karte-<n>.json``; ``None``, wenn der Crawler nicht lief."""
    lauf, karte = probe.lauf, probe.karte
    if lauf is None or karte is None:
        return None
    return {
        "karte": probe.datei,
        "anbieter": lauf.anbieter,
        "adresse": ohne_geheimnisse(lauf.adresse),
        "status": lauf.status,
        "grund": lauf.grund,
        "bot_schutz": probe.bot,
        "http_status": lauf.http_status,
        "hoechste_kombinationen": HOECHSTE_KOMBINATIONEN_PROBE,
        "belege": BELEGE,
        "zaehlung": zaehlung(lauf),
        "struktur": _struktur(lauf),
        "gefunden": _gefunden(lauf, karte),
        "kombinationen": [_kombination(e) for e in lauf.ergebnisse],
        "verworfen": [
            {"url": ohne_geheimnisse(v.url), "grund": v.grund}
            for v in lauf.verworfen[:HOECHSTE_LISTE]
        ],
        "gescheitert": [
            {"url": ohne_geheimnisse(g.url), "grund": g.grund}
            for g in lauf.gescheitert[:HOECHSTE_LISTE]
        ],
        "hilfsdateien": [
            {"url": ohne_geheimnisse(h.url), "art": h.art, "grund": h.grund}
            for h in lauf.hilfsdateien[:HOECHSTE_LISTE]
        ],
    }


def zaehlung(lauf: Klicklauf) -> dict[str, int]:
    """Kombinationen je Status, davon nicht besucht, und Adressen ohne Antwort."""
    je_status = Counter(e.status for e in lauf.ergebnisse)
    return {
        "kombinationen": len(lauf.ergebnisse),
        **{status: je_status[status] for status in STATUS_JE_KOMBINATION},
        "nicht_besucht": sum(_nicht_besucht(e) for e in lauf.ergebnisse),
        "verworfen": len(lauf.verworfen),
        "gescheitert": len(lauf.gescheitert),
    }


def _nicht_besucht(ergebnis: Kombiergebnis) -> bool:
    grund = ergebnis.grund or ""
    return ergebnis.status == NICHT_ERFASST and grund.startswith(GRUND_NICHT_BESUCHT)


def _struktur(lauf: Klicklauf) -> dict:
    bilanz = lauf.struktur
    return {
        **asdict(bilanz),
        "anteil_knoepfe": bilanz.anteil_knoepfe,
        "anteil_felder": bilanz.anteil_felder,
    }


def _gefunden(lauf: Klicklauf, karte: Klickkarte) -> dict:
    """Je Dimension Selektor und gesehene Knopfwerte, je Wertfeld die Lesungen."""
    werte: dict[str, list[str]] = {d: [] for d in DIMENSIONEN}
    for ergebnis in lauf.ergebnisse:
        for dimension, wert in zip(DIMENSIONEN, ergebnis.auswahl, strict=True):
            if wert is not None and wert not in werte[dimension]:
                werte[dimension].append(wert)
    felder = {
        feld: {
            "text": _gelesen(lauf, feld, "textwerte"),
            "antwort": _gelesen(lauf, feld, "antwortwerte"),
        }
        for feld in WERTFELDER
    }
    return {
        "knoepfe": {
            d: {"selektor": karte.knoepfe[d].selektor, "werte": werte[d]}
            for d in DIMENSIONEN
        },
        "zusammenfassung": karte.zusammenfassung,
        "felder": felder,
    }


def _gelesen(lauf: Klicklauf, feld: str, lesung: str) -> int:
    """Zahl der Kombinationen, deren Lesung ``lesung`` das Wertfeld ``feld`` nennt."""
    return sum(
        getattr(werte, feld) is not None
        for werte in (getattr(e, lesung) for e in lauf.ergebnisse)
        if werte is not None
    )


def _kombination(ergebnis: Kombiergebnis) -> dict:
    url = ergebnis.antwort_url
    return {
        "auswahl": dict(zip(DIMENSIONEN, ergebnis.auswahl, strict=True)),
        "variante": asdict(ergebnis.variante),
        "status": ergebnis.status,
        "grund": ergebnis.grund,
        "werte": werte_als_json(ergebnis.werte),
        "werte_text": _werte(ergebnis.textwerte),
        "werte_antwort": _werte(ergebnis.antwortwerte),
        "echo": {
            "befunde": [{"feld": b.feld, "grund": b.grund} for b in ergebnis.befunde],
            "luecken": list(ergebnis.luecken),
        },
        "text": ergebnis.text,
        "antwort_url": None if url is None else ohne_geheimnisse(url),
        "beleg_status": ergebnis.beleg_status,
    }


def _werte(werte: Preiswerte | None) -> dict | None:
    return None if werte is None else werte_als_json(werte)
