"""Kartenprobe der Klick-Erkundung (Datenkonzept Geräteradar, Schritt 5), ohne Netz.

Ein lokaler Server auf 127.0.0.1 liefert die BEISPIEL-Produktseite aus
``tests/fixtures/klickcrawler/`` (von Hand geschrieben, kein echter Anbieter), hier mit
je einer dritten Option für Speicher und Tarif: 3 × 3 × 2 = 18 Kombinationen, mehr als
``HOECHSTE_KOMBINATIONEN_PROBE``. Die Preisantwort rechnet der Server aus der Auswahl.
Die Klick-Karte ist ``beispiel_karte.yaml``, kopiert in ein Kartenverzeichnis unter
``tmp_path``. Geprüft wird: mit Karte schreibt die Erkundung ``karte-1.json`` mit
erfassten Kombinationen und nennt die über dem Deckel ``nicht besucht``, mit demselben
User-Agent und denselben robots-Regeln; ohne Karte entsteht keine Datei; eine kaputte
Karte ist ein Befund im Index; endet die Probe mit Bot-Schutz, geht für den Anbieter
keine Anfrage mehr hinaus.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from klickserver import JETZT, Antwort, html, klickserver

from telco_radar.collect.geraete.klickerkundung import (
    GRUND_NACH_BOT,
    erkunde_anbieter,
)
from telco_radar.collect.geraete.klickkartenprobe import HOECHSTE_KOMBINATIONEN_PROBE
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel

FIXTURES = Path(__file__).parent / "fixtures" / "klickcrawler"
TAG = JETZT.date().isoformat()
ROBOTS = "User-agent: *\nDisallow: /privat/json/\n"
KENNUNG = "TelcoRadarProbe/1.0 (+https://example.invalid/bot)"
KARTE = "beispiel.yaml"
KNOPF = '<button type="button" data-wert="{w}" aria-pressed="false">{t}</button>'
SPEICHER_256 = KNOPF.format(w="256", t="256 GB")
TARIF_M = KNOPF.format(w="M", t="Tarif M")
ZUSCHLAG = {"128": 0.0, "256": 5.0, "512": 10.0}
RATE = {"S": 20.0, "M": 18.0, "L": 15.0}
GRUNDPREIS = {"S": 29.99, "M": 39.99, "L": 49.99}
VOLUMEN = {"S": 25, "M": 50, "L": 1000}
PRUEFSEITE = "<!doctype html><html><body>Einen Moment bitte …</body></html>"


def _seite() -> str:
    seite = (FIXTURES / "beispiel_produktseite.html").read_text("utf-8")
    assert SPEICHER_256 in seite and TARIF_M in seite
    speicher = KNOPF.format(w="512", t="512 GB")
    tarif = KNOPF.format(w="L", t="Tarif L")
    seite = seite.replace(SPEICHER_256, f"{SPEICHER_256}\n  {speicher}")
    return seite.replace(TARIF_M, f"{TARIF_M}\n  {tarif}")


def _preis(speicher: str, tarif: str, laufzeit: str) -> dict:
    monate = int(laufzeit)
    rate = RATE[tarif] + ZUSCHLAG[speicher] - (5.0 if monate == 36 else 0.0)
    grund = GRUNDPREIS[tarif]
    return {
        "auswahl": {"speicher": speicher, "tarif": tarif, "laufzeit": monate},
        "preis": {"anzahlung": 99.0, "rate": rate, "raten": monate},
        "tarif": {
            "phasen": [
                {"ab": 1, "bis": 24, "betrag": grund},
                {"ab": 25, "bis": None, "betrag": round(grund + 5, 2)},
            ],
            "mindestlaufzeit": 24,
            "anschluss": 39.99,
            "volumen_gb": VOLUMEN[tarif],
        },
    }


def _beispiel(seite: str):
    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path.startswith("/handy/"):
            return html(seite)
        if teile.path == "/api/preis":
            frage = parse_qs(teile.query)
            auswahl = (frage[t][0] for t in ("speicher", "tarif", "laufzeit"))
            return Antwort(200, "application/json", json.dumps(_preis(*auswahl)))
        return Antwort(404)

    return antworte


def _ziel(server, *pfade: str, modell: str | None = None) -> Erkundungsziel:
    seiten = tuple(
        Seitenziel("beispielhandy-x", 256, server.adresse(p), modell=modell)
        for p in pfade
    )
    return Erkundungsziel("beispiel", "Beispielanbieter", seiten, KENNUNG, 0.0)


def _karten(tmp_path: Path, inhalt: str | None = None) -> Path:
    ordner = tmp_path / "karten"
    ordner.mkdir()
    if inhalt is None:
        shutil.copyfile(FIXTURES / "beispiel_karte.yaml", ordner / KARTE)
    else:
        (ordner / KARTE).write_text(inhalt, encoding="utf-8")
    return ordner


def _erkunde(chromium, ziel, tmp_path: Path, karten: Path) -> dict:
    def hole(url: str) -> tuple[int, str]:
        return 200, ROBOTS

    ende = time.monotonic() + 600
    return erkunde_anbieter(
        chromium, ziel, lambda: JETZT, hole, tmp_path / "aus", ende, karten=karten
    )


def _lies(tmp_path: Path, name: str) -> dict:
    ordner = tmp_path / "aus" / "beispiel" / TAG
    return json.loads((ordner / name).read_text(encoding="utf-8"))


def test_karte_laeuft_auf_der_seite_und_der_deckel_greift(chromium, tmp_path):
    karten = _karten(tmp_path)
    with klickserver(_beispiel(_seite())) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path, karten)

    seite = index["seiten"][0]
    assert (index["status"], seite["status"]) == ("gelesen", "gelesen")
    assert seite["dateien"]["karte"] == "karte-1.json"
    eintrag = seite["karte"]
    zaehlung = eintrag.pop("zaehlung")
    assert eintrag == {
        "status": "gelaufen",
        "karte": KARTE,
        "grund": None,
        "datei": "karte-1.json",
        "laufstatus": "gelesen",
        "bot_schutz": False,
    }
    assert zaehlung.pop("verworfen") >= 1
    assert zaehlung == {
        "kombinationen": 18,
        "erfasst": 10,
        "nicht_angeboten": 2,
        "nicht_erfasst": 6,
        "befund": 0,
        "nicht_besucht": 6,
        "gescheitert": 0,
    }
    probe = _lies(tmp_path, "karte-1.json")
    assert probe["zaehlung"]["kombinationen"] == 18
    assert (probe["status"], probe["grund"], probe["bot_schutz"]) == (
        "gelesen",
        None,
        False,
    )
    assert probe["hoechste_kombinationen"] == HOECHSTE_KOMBINATIONEN_PROBE == 12
    kombinationen = probe["kombinationen"]
    erste = kombinationen[0]
    assert erste["auswahl"] == {"speicher": "128", "tarif": "S", "laufzeit": "24"}
    assert erste["variante"] == {"speicher": "128", "tarif": "S", "laufzeit": 24}
    assert (erste["status"], erste["grund"]) == ("erfasst", None)
    werte = {
        "anzahlung": 99.0,
        "rate": 20.0,
        "ratenzahl": 24,
        "tarifphasen": [[1, 24, 29.99], [25, None, 34.99]],
        "tarifbindung": 24,
        "anschluss": 39.99,
        "volumen_gb": 25.0,
    }
    assert erste["werte"] == erste["werte_text"] == erste["werte_antwort"] == werte
    assert erste["echo"] == {"befunde": [], "luecken": []}
    assert "Monatliche Gerätrate 20,00 €" in erste["text"]
    assert "speicher=128&tarif=S&laufzeit=24" in erste["antwort_url"]
    assert erste["beleg_status"] == "offen"
    gross = next(k for k in kombinationen if k["variante"]["speicher"] == "256")
    assert gross["werte"]["rate"] == 25.0
    gesperrt = kombinationen[1]
    assert (gesperrt["status"], gesperrt["werte_text"]) == ("nicht_angeboten", None)
    assert "36" in gesperrt["grund"]
    ueber_deckel = kombinationen[HOECHSTE_KOMBINATIONEN_PROBE:]
    assert [k["auswahl"]["speicher"] for k in ueber_deckel] == ["512"] * 6
    assert {(k["status"], k["grund"]) for k in ueber_deckel} == {
        ("nicht_erfasst", "nicht besucht: mehr als 12 Kombinationen")
    }
    gefunden = probe["gefunden"]
    assert {d: k["werte"] for d, k in gefunden["knoepfe"].items()} == {
        "speicher": ["128", "256", "512"],
        "tarif": ["S", "M", "L"],
        "laufzeit": ["24", "36"],
    }
    assert gefunden["felder"]["rate"] == {"text": 10, "antwort": 10}
    assert probe["struktur"]["anteil_knoepfe"] == 1.0
    assert probe["struktur"]["anteil_felder"] == 1.0
    assert server.mit("/handy/") == ["/handy/x", "/handy/x"]
    assert set(server.kennungen) == {KENNUNG}
    assert server.mit("/privat/") == []
    assert {urlsplit(v["url"]).path for v in probe["verworfen"]} == {
        "/privat/json/zaehler"
    }


def test_ohne_karte_aendert_sich_nichts(chromium, tmp_path):
    karten = tmp_path / "karten"
    karten.mkdir()
    with klickserver(_beispiel(_seite())) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path, karten)

    seite = index["seiten"][0]
    assert seite["status"] == "gelesen"
    assert seite["karte"] == {
        "status": "keine_karte",
        "karte": KARTE,
        "grund": f"{KARTE} nicht vorhanden",
    }
    assert "karte" not in seite["dateien"]
    ordner = tmp_path / "aus" / "beispiel" / TAG
    assert list(ordner.glob("karte-*")) == []
    assert server.mit("/handy/") == ["/handy/x"]


def test_kaputte_karte_ist_ein_befund_im_index(chromium, tmp_path):
    ohne_kanarie = (FIXTURES / "beispiel_karte.yaml").read_text("utf-8")
    ohne_kanarie = ohne_kanarie.split("kanarie:")[0]
    karten = _karten(tmp_path, ohne_kanarie)
    with klickserver(_beispiel(_seite())) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path, karten)

    assert index["status"] == "gelesen"
    seite = index["seiten"][0]
    assert seite["karte"] == {
        "status": "kartenfehler",
        "karte": KARTE,
        "grund": "Feld kanarie: Pflichtfeld fehlt oder ist leer",
    }
    assert "karte" not in seite["dateien"]
    assert list((tmp_path / "aus" / "beispiel" / TAG).glob("karte-*")) == []
    assert _lies(tmp_path, "index.json") == index
    assert server.mit("/handy/") == ["/handy/x"]


def test_bot_schutz_in_der_probe_beendet_den_anbieter(chromium, tmp_path):
    karten = _karten(tmp_path)
    antworte = _beispiel(_seite())
    geoeffnet: list[str] = []

    def mit_sperre(pfad: str) -> Antwort:
        if urlsplit(pfad).path.startswith("/handy/"):
            geoeffnet.append(pfad)
            if len(geoeffnet) > 1:
                return html(PRUEFSEITE, 403)
        return antworte(pfad)

    with klickserver(mit_sperre) as server:
        ziel = _ziel(server, "/handy/x", "/handy/y")
        index = _erkunde(chromium, ziel, tmp_path, karten)

    assert server.mit("/handy/y") == []
    assert server.abrufe[-1] == "/handy/x"
    erste, zweite = index["seiten"]
    assert erste["status"] == "gelesen"
    assert erste["karte"]["laufstatus"] == "gestoert"
    assert erste["karte"]["bot_schutz"] is True
    assert "HTTP 403" in erste["karte"]["grund"]
    assert _lies(tmp_path, "karte-1.json")["bot_schutz"] is True
    assert (zweite["status"], zweite["grund"]) == ("nicht_besucht", GRUND_NACH_BOT)
    assert zweite["karte"] == {
        "status": "nicht_besucht",
        "karte": KARTE,
        "grund": GRUND_NACH_BOT,
    }


def test_kanarienwert_mit_modellname_kommt_aus_dem_ziel(chromium, tmp_path):
    karte = (FIXTURES / "beispiel_karte.yaml").read_text("utf-8")
    assert "  enthaelt: Beispielhandy X\n" in karte
    karte = karte.replace("  enthaelt: Beispielhandy X\n", '  enthaelt: "{modell}"\n')
    ergebnisse = {}
    for modell in ("Beispielhandy X", None):
        aus = tmp_path / str(modell)
        aus.mkdir()
        with klickserver(_beispiel(_seite())) as server:
            ziel = _ziel(server, "/handy/x", modell=modell)
            index = _erkunde(chromium, ziel, aus, _karten(aus, karte))
        ergebnisse[modell] = index["seiten"][0]["karte"]

    assert ergebnisse["Beispielhandy X"]["laufstatus"] == "gelesen"
    assert ergebnisse[None]["laufstatus"] == "gestoert"
    assert "Modellnamen" in ergebnisse[None]["grund"]
