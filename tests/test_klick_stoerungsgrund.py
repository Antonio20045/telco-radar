"""Ein gestörter Klick-Lauf nennt auf geraete.html seinen Grund (Pitch 1, Schnitt 2).

Die Klick-Ergebnisdatei ``data/state/klick/<anbieter>.json`` eines gestörten Laufs
(``laufstatus`` „gestoert“, ``grund`` mit „HTTP 202“) wird zum Erfassungsgrund der
Bilanz: „Telekom nicht erfasst: Seite sperrt automatisches Lesen (HTTP 202,
08.10.2026)“, Anbieter, Status und Datum aus der Datei. Der Gerätelauf legt ihn in
``geraete_tco.json`` ab, und wo der Anbieter im Radar „kein Bündel erhoben“ zeigt,
steht er stattdessen. Gemessen am Bestand vom 2026-10-03 (iPhone 17 Pro 256 GB ohne
Telekom-Bündel). Gegenprobe: ohne Störung bleibt der alte Satz.
"""

from __future__ import annotations

import json
import shutil

import pytest
import yaml
from bestand_pfad import WURZEL, ZUSTAND, abbild, lese_wurzel

from telco_radar.analyze.klick_erfassung import erfassungsgruende
from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.collect.geraete.klickergebnis import ORDNER
from telco_radar.config import load_config
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.geraete_pipeline import run_geraete_stage
from telco_radar.report import geraete_radar, geraete_view
from telco_radar.report.html import render_site

TAG = "2026-10-08"
BESTAND_TAG = "2026-10-02"
MODELL = "apple-iphone-17-pro-256"
ADRESSE = "https://www.telekom.de/shop/geraet/apple/apple-iphone-17-pro/tiefblau-256-gb"
SATZ = "Telekom nicht erfasst: Seite sperrt automatisches Lesen (HTTP 202, 08.10.2026)"
ALT = "Für dieses Modell ist bei Telekom kein Bündel erhoben."
O2_OHNE_ANTWORT = {
    "name": "o2",
    "typ": "netzbetreiber",
    "methode": "o2_katalog",
    "basis_url": "https://www.o2online.de",
    "rate_limit_sekunden": 0,
    "einstiege": [
        {"url": "https://www.o2online.de/katalog", "label": "x", "kind": "buendel"}
    ],
}
"""Ein Anbieter, dessen Abrufe alle mit 404 enden: der Lauf sammelt nichts."""


def _datei(name="Telekom", datum=TAG, laufstatus="gestoert", grund=None) -> dict:
    """Kopf einer Klick-Ergebnisdatei wie ``data/state/klick/telekom.json``."""
    if grund is None and laufstatus == "gestoert":
        grund = f"{ADRESSE}: Abruf gestört (HTTP 202)"
    return {
        "anbieter": name.lower(),
        "name": name,
        "datum": datum,
        "format": 1,
        "laufstatus": laufstatus,
        "grund": grund,
        "seiten": [],
    }


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _zug(dateien, katalog, heute=TAG):
    return fuehre_zusammen([], dateien, katalog, heute, lambda sku: ("", None))


def test_gestoerte_klickdatei_wird_erfassungsgrund(katalog):
    zug = _zug([_datei()], katalog)
    assert erfassungsgruende(zug.bilanz) == {"Telekom": SATZ}
    assert zug.erfassung == {"Telekom": SATZ}


@pytest.mark.parametrize(
    ("datei", "erwartet"),
    [
        (
            _datei("o2", "2026-10-07", grund="x: Abruf gestört (HTTP 403)"),
            "o2 nicht erfasst: Seite sperrt automatisches Lesen (HTTP 403, 07.10.2026)",
        ),
        (
            _datei("1&1", grund="x: Abruf gestört (HTTP 503)"),
            "1&1 nicht erfasst: Lesen gestört (HTTP 503, 08.10.2026)",
        ),
        (
            _datei("congstar", grund="x: Abruf gestört (keine Antwort)"),
            "congstar nicht erfasst: Lesen gestört (08.10.2026)",
        ),
    ],
    ids=["403", "503", "ohne-status"],
)
def test_anbieter_status_und_datum_kommen_aus_der_datei(katalog, datei, erwartet):
    assert _zug([datei], katalog).erfassung == {datei["name"]: erwartet}


@pytest.mark.parametrize(
    "datei",
    [
        _datei(laufstatus="gelesen"),
        _datei(datum="2026-10-05"),
        _datei(datum="2026-10-09"),
    ],
    ids=["gelesen", "veraltet", "zukunft"],
)
def test_gegenprobe_ohne_frische_stoerung_kein_grund(katalog, datei):
    assert _zug([datei], katalog).erfassung == {}
    assert erfassungsgruende(None) == {}


def test_tco_speicher_behaelt_den_grund(tmp_path):
    pfad = tmp_path / "geraete_tco.json"
    referenz = {"id": "vf--xs", "anbieter": "Vodafone", "tarif_name": "Mobil XS"}
    pfad.write_text(json.dumps({"updated": TAG, "sim_only": [referenz]}))
    tco = TcoDB(pfad)
    assert tco.erfassung == {}
    tco.erfassung = {"Telekom": SATZ}
    assert tco.save(TAG)
    assert TcoDB(pfad).erfassung == {"Telekom": SATZ}


def test_geraetelauf_schreibt_den_grund_in_den_bestand(tmp_path, monkeypatch):
    """``run_geraete_stage`` ohne Anbieter, mit gestörter Telekom-Datei im Repo."""
    monkeypatch.delenv("TELCO_KLICK_ERGEBNISSE", raising=False)
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    for name in ("geraete_katalog.yaml", "farben.yaml"):
        shutil.copy(WURZEL / "config" / name, root / "config" / name)
    quellen = yaml.safe_dump({"anbieter": [O2_OHNE_ANTWORT]})
    (root / "config" / "geraete_quellen.yaml").write_text(quellen, encoding="utf-8")
    (root / ORDNER).mkdir(parents=True)
    shutil.copy(ZUSTAND / "tarife.jsonl", root / "data" / "state" / "tarife.jsonl")
    datei = json.dumps(_datei(), ensure_ascii=False)
    (root / ORDNER / "telekom.json").write_text(datei, encoding="utf-8")

    bilanz = run_geraete_stage(
        root, {}, TAG, hole=lambda url, kopfzeilen=None: (404, "")
    )

    assert bilanz["klick"]["dateien"][0]["laufstatus"] == "gestoert"
    store = json.loads((root / "data/state/geraete_tco.json").read_text("utf-8"))
    assert store["erfassung"] == {"Telekom": SATZ}


def _telekom_iphone(zustand) -> dict:
    """Die Telekom-Zeile des iPhone 17 Pro 256 GB im Radar."""
    wurzel = lese_wurzel()
    geraete = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=BESTAND_TAG
    )
    sicht = geraete_radar.radar(
        geraete["tco"], geraete["vergleich"]["ohne_vertrag"], geraete["quellenlage"]
    )
    (gruppe,) = [g for g in sicht["gruppen"] if g["id"] == MODELL]
    (zeile,) = [z for z in gruppe["zeilen"] if z["anbieter"] == "Telekom"]
    return zeile


def _mit_grund(zustand) -> None:
    pfad = zustand / "geraete_tco.json"
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    daten["erfassung"] = {"Telekom": SATZ}
    pfad.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")


def test_radar_nennt_den_grund_statt_kein_buendel(tmp_path):
    zustand = tmp_path / "state"
    shutil.copytree(ZUSTAND, zustand)
    vorher = _telekom_iphone(zustand)
    assert (vorher["status"], vorher["grund"]) == ("kein_buendel", ALT)

    _mit_grund(zustand)
    nachher = _telekom_iphone(zustand)
    assert (nachher["status"], nachher["grund"]) == ("kein_buendel", SATZ)
    assert nachher["gesamt"] is None


def test_gerenderte_seite_traegt_den_satz(tmp_path):
    berichte = abbild(tmp_path)
    _mit_grund(tmp_path / "data" / "state")
    render_site(tmp_path / "site", berichte, load_config(tmp_path))
    seite = (tmp_path / "site" / "geraete.html").read_text(encoding="utf-8")
    assert f'<span class="wr-grund">{SATZ}</span>' in seite
    assert ALT not in seite
