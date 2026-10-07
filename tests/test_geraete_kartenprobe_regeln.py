"""Regeln der Kartenprobe (Datenkonzept Geräteradar, Schritt 5), ohne Netz.

Ein lokaler Server auf 127.0.0.1 liefert die BEISPIEL-Produktseite aus
``tests/fixtures/klickcrawler/`` (von Hand geschrieben, kein echter Anbieter), je Test
leicht abgewandelt; die Preisantwort rechnet der Server aus der Auswahl. Für die Probe
gelten dieselben Regeln wie für die Seitenerkundung: ihre Sitzungswerte, ob per
Set-Cookie oder per Skript gesetzt, stehen in keiner abgelegten Datei (CLAUDE.md
Regel 2); eine 403 der eigenen Website auf eine Datenanfrage und eine Warteseite ohne
Kanarienwert beenden den Anbieter (Regel 4); die Zeitgrenze ist die der Schleuse. Ist
sie vor der Probe um, heißt die Probe ``nicht_besucht`` und fragt nichts an; reicht sie
mit Crawl-delay nicht für alle Kombinationen, nennt ``karte-<n>.json`` trotzdem jede.
"""

from __future__ import annotations

import gzip
import json
import shutil
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from klickserver import JETZT, Antwort, html, klickserver

from telco_radar.collect.geraete.klickablage import GESCHWAERZT
from telco_radar.collect.geraete.klickerkundung import (
    GRUND_NACH_BOT,
    erkunde_anbieter,
)
from telco_radar.collect.geraete.klickkartenprobe import (
    GRUND_VOR_PROBE,
    Probenmittel,
    als_daten,
    indexeintrag,
    lade_karte,
    probiere,
)
from telco_radar.collect.geraete.klickseite import Fristschleuse, Seitenergebnis
from telco_radar.collect.geraete.klicktor import Hostschleuse
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel
from telco_radar.collect.geraete.robots import RobotsWaechter

FIXTURES = Path(__file__).parent / "fixtures" / "klickcrawler"
TAG = JETZT.date().isoformat()
ROBOTS = "User-agent: *\nDisallow: /privat/json/\n"
KENNUNG = "TelcoRadarProbe/1.0 (+https://example.invalid/bot)"
KARTE = "beispiel.yaml"
LADE = "fetch(`/api/preis?${frage}`).then((antwort) => antwort.json()).then(zeige);"
LADE_MIT_KORB = (
    "fetch(`/api/preis?${frage}&korb=${KORB}`)"
    ".then((antwort) => antwort.json()).then(zeige);"
)
LADE_MIT_KORBABRUF = f'{LADE} fetch("/api/korb").catch(() => {{}});'
PRUEFSEITE = "<!doctype html><html><body>Einen Moment bitte …</body></html>"
KOMBINATIONEN = 8
CRAWL_DELAY = 3
NICHT_BESUCHT = "nicht besucht: Zeitgrenze erreicht"


def _seite(lade: str = LADE, kopf: str = "") -> str:
    seite = (FIXTURES / "beispiel_produktseite.html").read_text("utf-8")
    assert LADE in seite
    seite = seite.replace(LADE, lade)
    return seite.replace('"use strict";', f'"use strict";\n{kopf}', 1)


def _daten(pfad: str) -> Antwort:
    teile = urlsplit(pfad)
    if teile.path != "/api/preis":
        return Antwort(404)
    frage = parse_qs(teile.query)
    speicher, tarif, laufzeit = (frage[t][0] for t in ("speicher", "tarif", "laufzeit"))
    monate = int(laufzeit)
    grund = {"S": 29.99, "M": 39.99}[tarif]
    daten = {
        "auswahl": {"speicher": speicher, "tarif": tarif, "laufzeit": monate},
        "preis": {
            "anzahlung": 99.0,
            "rate": {"S": 20.0, "M": 18.0}[tarif] + {"128": 0.0, "256": 5.0}[speicher],
            "raten": monate,
        },
        "tarif": {
            "phasen": [
                {"ab": 1, "bis": 24, "betrag": grund},
                {"ab": 25, "bis": None, "betrag": round(grund + 5, 2)},
            ],
            "mindestlaufzeit": 24,
            "anschluss": 39.99,
            "volumen_gb": 25,
        },
    }
    return Antwort(200, "application/json", json.dumps(daten))


def _ziel(server, *pfade: str) -> Erkundungsziel:
    seiten = tuple(Seitenziel("beispielhandy-x", 256, server.adresse(p)) for p in pfade)
    return Erkundungsziel("beispiel", "Beispielanbieter", seiten, KENNUNG, 0.0)


def _karten(tmp_path: Path) -> Path:
    ordner = tmp_path / "karten"
    ordner.mkdir()
    shutil.copyfile(FIXTURES / "beispiel_karte.yaml", ordner / KARTE)
    return ordner


def _erkunde(chromium, ziel, tmp_path: Path) -> dict:
    def hole(url: str) -> tuple[int, str]:
        return 200, ROBOTS

    ende = time.monotonic() + 600
    return erkunde_anbieter(
        chromium,
        ziel,
        lambda: JETZT,
        hole,
        tmp_path / "aus",
        ende,
        karten=_karten(tmp_path),
    )


def _texte(tmp_path: Path) -> dict[str, str]:
    texte: dict[str, str] = {}
    for datei in sorted((tmp_path / "aus" / "beispiel" / TAG).iterdir()):
        roh = datei.read_bytes()
        if datei.suffix == ".gz":
            roh = gzip.decompress(roh)
        texte[datei.name] = roh.decode("utf-8", errors="replace")
    return texte


def _mit_korb(per_skript: bool):
    vergeben: list[str] = []

    def antworte(pfad: str) -> Antwort:
        if not urlsplit(pfad).path.startswith("/handy/"):
            return _daten(pfad)
        wert = f"k{len(vergeben) + 1}Qm4Lp9Zr2Tv7Hx"
        vergeben.append(wert)
        kopf = f'const KORB = "{wert}";'
        if per_skript:
            kopf += "\ndocument.cookie = `korb=${KORB}; path=/`;"
            return html(_seite(LADE_MIT_KORB, kopf))
        setze = {"Set-Cookie": f"korb={wert}; Path=/"}
        seite = _seite(LADE_MIT_KORB, kopf)
        return Antwort(200, "text/html; charset=utf-8", seite, setze)

    return antworte, vergeben


@pytest.mark.parametrize("per_skript", [False, True], ids=["set-cookie", "skript"])
def test_sitzungswert_der_probe_steht_in_keiner_datei(chromium, tmp_path, per_skript):
    antworte, vergeben = _mit_korb(per_skript)
    with klickserver(antworte) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path)

    eintrag = index["seiten"][0]["karte"]
    assert (eintrag["status"], eintrag["laufstatus"]) == ("gelaufen", "gelesen")
    assert len(vergeben) == 2
    seitenwert, probenwert = vergeben
    karte = json.loads(_texte(tmp_path)["karte-1.json"])
    urls = [k["antwort_url"] for k in karte["kombinationen"] if k["antwort_url"]]
    assert urls and all(f"korb={GESCHWAERZT}" in url for url in urls)
    dateien = _texte(tmp_path)
    assert GESCHWAERZT in dateien["mitschnitt-1.json"]
    assert [n for n, t in dateien.items() if seitenwert in t or probenwert in t] == []


def _korb_sperrt_ab(besuch: int):
    pfade: list[str] = []
    sperren: list[int] = []

    def antworte(pfad: str) -> Antwort:
        pfade.append(pfad)
        teile = urlsplit(pfad)
        if teile.path.startswith("/handy/"):
            return html(_seite(LADE_MIT_KORBABRUF))
        if teile.path == "/api/korb":
            if len([p for p in pfade if p.startswith("/handy/")]) < besuch:
                return Antwort(200, "application/json", "{}")
            sperren.append(len(pfade))
            return Antwort(403, "application/json", '{"fehler": "gesperrt"}')
        return _daten(pfad)

    return antworte, pfade, sperren


def test_403_der_eigenen_website_in_der_probe_beendet_den_anbieter(chromium, tmp_path):
    antworte, pfade, sperren = _korb_sperrt_ab(besuch=2)
    with klickserver(antworte) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x", "/handy/y"), tmp_path)

    erste, zweite = index["seiten"]
    assert erste["status"] == "gelesen"
    assert "/api/korb" in pfade[: pfade.index("/handy/x", 1)]
    assert sperren and pfade[sperren[0] :] == []
    assert erste["karte"]["laufstatus"] == "gestoert"
    assert erste["karte"]["bot_schutz"] is True
    assert "HTTP 403 auf" in erste["karte"]["grund"]
    assert server.mit("/handy/y") == []
    assert (zweite["status"], zweite["grund"]) == ("nicht_besucht", GRUND_NACH_BOT)


def test_warteseite_ohne_kanarienwert_in_der_probe_beendet_den_anbieter(
    chromium, tmp_path
):
    besuche: list[str] = []

    def antworte(pfad: str) -> Antwort:
        if not urlsplit(pfad).path.startswith("/handy/"):
            return _daten(pfad)
        besuche.append(pfad)
        return html(PRUEFSEITE if len(besuche) > 1 else _seite())

    with klickserver(antworte) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x", "/handy/y"), tmp_path)

    erste, zweite = index["seiten"]
    assert erste["status"] == "gelesen"
    assert erste["karte"]["laufstatus"] == "gestoert"
    assert "Kanarienwert fehlt" in erste["karte"]["grund"]
    assert erste["karte"]["bot_schutz"] is True
    assert besuche == ["/handy/x", "/handy/x"]
    assert server.mit("/handy/y") == []
    assert (zweite["status"], zweite["grund"]) == ("nicht_besucht", GRUND_NACH_BOT)


def _antworte(pfad: str) -> Antwort:
    if urlsplit(pfad).path.startswith("/handy/"):
        return html(_seite())
    return _daten(pfad)


def _probe(chromium, tmp_path: Path, server, robots: str, ende: float):
    waechter = RobotsWaechter(hole=lambda url: (200, robots))
    schleuse = Fristschleuse(Hostschleuse(waechter, lambda: JETZT), ende)
    ziel = _ziel(server, "/handy/x")
    lage = lade_karte(_karten(tmp_path), "beispiel")
    assert lage.karte is not None
    mittel = Probenmittel(waechter, lambda: JETZT, schleuse)
    return probiere(chromium, ziel, ziel.seiten[0], lage, Seitenergebnis(), mittel)


def test_ist_die_zeit_vor_der_probe_um_heisst_sie_nicht_besucht(chromium, tmp_path):
    with klickserver(_antworte) as server:
        probe = _probe(chromium, tmp_path, server, ROBOTS, time.monotonic())

    assert server.abrufe == []
    assert indexeintrag(probe, None) == {
        "status": "nicht_besucht",
        "karte": KARTE,
        "grund": GRUND_VOR_PROBE,
    }
    assert GRUND_VOR_PROBE.startswith("Zeitgrenze erreicht")
    assert probe.bot is False
    assert als_daten(probe) is None


def test_zeitgrenze_mit_crawl_delay_nennt_jede_kombination(chromium, tmp_path):
    robots = f"User-agent: *\nCrawl-delay: {CRAWL_DELAY}\nDisallow: /privat/json/\n"
    with klickserver(_antworte) as server:
        ende = time.monotonic() + 2 * CRAWL_DELAY
        probe = _probe(chromium, tmp_path, server, robots, ende)

    daten = als_daten(probe)
    assert daten is not None
    kombinationen = daten["kombinationen"]
    assert len(kombinationen) == KOMBINATIONEN
    status = [k["status"] for k in kombinationen]
    assert "erfasst" in status
    nicht_besucht = [k for k in kombinationen if k["grund"] == NICHT_BESUCHT]
    assert nicht_besucht and {k["status"] for k in nicht_besucht} == {"nicht_erfasst"}
    assert status.count("nicht_erfasst") == len(nicht_besucht)
    anzahl = len(nicht_besucht)
    assert daten["status"] == "zeitgrenze"
    assert (
        daten["grund"] == f"Zeitgrenze erreicht: {anzahl} Kombinationen nicht besucht"
    )
    eintrag = indexeintrag(probe, "karte-1.json")
    assert (eintrag["status"], eintrag["bot_schutz"]) == ("gelaufen", False)
    assert eintrag["zaehlung"]["nicht_besucht"] == anzahl
    assert all(abstand >= CRAWL_DELAY - 0.05 for abstand in server.luecken("/"))
