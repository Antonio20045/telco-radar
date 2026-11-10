"""Saturn/MediaMarkt mit Vertrag (Tarifwelt) stehen in „Mit Tarif“ wie jeder Anbieter.

Zwei Ursachen hielten die 214 gelesenen Bündel draußen (Auftrag haendler-mit-tarif):

1. Der Leser trägt die Herkunftsmarke ``tarifwelt_productdetail`` in ``herleitung``; die
   Notbremse hielt jede nicht leere ``herleitung`` für einen Rechenweg und damit für
   eine Schätzung („nicht direkt genannt“): kein Δ, keine Referenz, kein Sieger, im
   Export der Status „nicht direkt genannt“. Das Bündel ist aber die SKU-genaue Antwort
   der Schnittstelle.
2. Die Stammdaten der Händlertarife (Datenvolumen → Tarifband) lagen in einer Datei,
   die der Tageslauf nie ins Repo brachte; jede außerhalb des Messlaufs gebaute Seite
   führte die Zeilen „ohne Tarifband“. Sie stehen jetzt in ``geraete_tco.json``.

Die Gegenproben halten fest, dass echte Schätzungen draußen bleiben und andere
Anbieter nicht berührt werden.
"""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest
from bestand_pfad import lese_wurzel
from test_geraete_adapter_tarifwelt import LEITER, fixture_hole

from telco_radar import tarifwelt_bestand
from telco_radar.analyze.geraete_pruefstatus import ist_schaetzung
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.collect.geraete import tarifwelt_lauf
from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_notbremse
from telco_radar.report import geraete_tco_view as tco_view
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-08"
HAENDLER = "Saturn/MediaMarkt"
KATALOG = lade_katalog(lese_wurzel())


def vodafone_tarife() -> dict:
    return {
        f"vodafone:mobil-{k}": {
            "anbieter": "Vodafone",
            "name": f"Vodafone Mobil {k.upper()} mit Smartphone",
            "datenvolumen_gb": gb,
            "grundgebuehr": 20.0 + i * 10,
        }
        for i, (k, gb) in enumerate(LEITER)
    }


def lauf_beide_geraete():
    hole, _ = fixture_hole()
    return [
        tarifwelt_lauf.lies_modell(m, LEITER, hole, HEUTE, warte=lambda s: None)
        for m in ("apple-iphone-17", "samsung-galaxy-s26")
    ]


def _haendler():
    tarife: dict = {}
    buendel: list[Buendel] = []
    for teil in lauf_beide_geraete():
        tarife.update(teil.tarife)
        buendel.extend(teil.buendel)
    assert buendel
    return buendel, tarife


def test_haendler_buendel_zaehlt_wie_ein_gemessenes():
    buendel, _ = _haendler()
    for b in buendel:
        assert b.herleitung == "tarifwelt_productdetail"
        assert not ist_schaetzung(b.herleitung)
        felder = geraete_notbremse.felder(b, HEUTE)
        assert felder["zaehlt"] is True and felder["notbremse"] is None, b.anbieter
        assert geraete_notbremse.kurz(b, HEUTE) == ""
        roh = geraete_notbremse.felder_aus_satz(asdict(b), HEUTE)
        assert roh["zaehlt"] is True and roh["notbremse"] is None


def test_gegenprobe_echte_schaetzung_bleibt_draussen():
    buendel, _ = _haendler()
    rechnung = replace(buendel[0], herleitung="tarifsumme_minus_geraeterate")
    assert ist_schaetzung(rechnung.herleitung)
    felder = geraete_notbremse.felder(rechnung, HEUTE)
    assert felder["zaehlt"] is False
    assert felder["notbremse"]["kurz"] == "nicht direkt genannt"
    assert ist_schaetzung("irgendeine_marke")


def test_haendlertarife_ueberleben_speichern_und_lesen(tmp_path):
    buendel, tarife = _haendler()
    pfad = tmp_path / "geraete_tco.json"
    db = TcoDB(pfad)
    db.upsert_buendel(buendel, HEUTE)
    db.haendler_tarife.update(tarife)
    assert db.save(HEUTE)
    neu = TcoDB(pfad)
    assert neu.haendler_tarife == tarife
    vf = vodafone_tarife()
    gesamt = tarifwelt_bestand.mit_tarifwelt(vf, neu.haendler_tarife)
    assert set(tarife) <= set(gesamt) and all(gesamt[k] == v for k, v in vf.items())
    leer = TcoDB(tmp_path / "leer.json")
    leer.upsert_buendel([replace(buendel[0], anbieter="Vodafone")], HEUTE)
    leer.save(HEUTE)
    assert "haendler_tarife" not in (tmp_path / "leer.json").read_text()


def test_haendlerzeilen_stehen_im_band_ohne_status_und_mit_beleg():
    """Seite und Export lesen dasselbe: Stufe, kein Status, Summe, Beleglink; der
    Anbietername nennt Händler und Netz."""
    buendel, tarife = _haendler()
    vf = vodafone_tarife()
    ergebnis = tco_view.aufbereiten(
        [asdict(b) for b in buendel],
        [],
        [],
        KATALOG,
        tarife={**tarife, **vf},
        tco_historie={"schwankend": []},
        heute=HEUTE,
    )
    zeilen = ergebnis["export"]["buendel"]
    assert len(zeilen) == len(buendel)
    for z in zeilen:
        assert z["anbieter"].startswith(f"{HAENDLER} · ")
        assert z["anbieter"].endswith("-Netz")
        assert z["status"] == "", z
        assert z["band"], f"keine Stufe: {z['anbieter']} {z['tarif']}"
        assert z["leitzahl_monate"] == 24
        assert z["quelle_url"].startswith("https://tarife.mediamarkt.de/")
        assert z["luecke"] == ""
    for z, b in zip(
        sorted(zeilen, key=lambda z: z["quelle_url"]),
        sorted(buendel, key=lambda b: b.quelle_url),
        strict=True,
    ):
        erwartet = b.geraet_zuzahlung + 24 * b.tarif_monatlich + b.anschlusspreis
        assert z["tco24"] == pytest.approx(erwartet + 5.95, abs=0.005), z["anbieter"]
    karten = [k for m in ergebnis["modelle"] for k in m["zeilen_band"]]
    assert len(karten) == len(buendel)
    assert all(k["zaehlt"] and k["notbremse"] is None for k in karten)
