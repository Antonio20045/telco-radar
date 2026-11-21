"""o2: offene Anschlusspreise nach der Tarifwelt-Stufe nachmessen.

Modul ``geraete_o2_anschluss``.

Befund 21.11.2026: 568 abgeleitete o2-Bündel ohne Anschlusspreis; die Seite jedes
Bündels nennt ihn, wenn ihr Tarif gewählt ist. Die Nachmessung darf die
Tarifwelt-Stufe (Restzeit des Jobs, rund 813 s seit #185) nicht verdrängen: sie läuft
danach, nur in der dann verbleibenden Restzeit. Eine Messung gilt
``ANSCHLUSS_GUELTIG_TAGE`` Tage; nie gemessene Bündel kommen zuerst, dann die ältesten.
Die Fixture ist die Redmi-17-Seite vom 21.11.2026 (gewählt „on Demand M“, 36 Raten,
berechnet 39,99 €).
"""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import yaml
from bestand_pfad import WURZEL, ZUSTAND, lese_wurzel

from telco_radar import geraete_o2_anschluss as stufe_o2
from telco_radar import geraete_pipeline, geraete_tarifwelt
from telco_radar.collect.geraete import o2
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report.geraete_tco_view import aufbereiten
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-21"
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
_FIX = Path(__file__).parent / "fixtures" / "geraete"
_REDMI = _FIX / "o2_redmi17_tarifoptionen_20261121.json.gz"
_URL = (
    "https://www.o2online.de/e-shop/xiaomi/xiaomi-redmi-17-128gb-blue-5g-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36"
    "&vertragsart=ratenzahlung&tarif=o2-mobile-on-demand-m"
)


def _offen(**mehr) -> Buendel:
    felder = dict(
        sku_id="xiaomi-redmi-17-128gb-blue-5g",
        anbieter="o2",
        tarif_name="O2 Mobile on Demand M mit 50 GB+ (24 Mon.)",
        tarif_id="o2:o2-mobile-on-demand-m",
        tarif_monatlich=19.99,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=7.0,
        laufzeit_monate=36,
        quelle_url=_URL,
        abgerufen_am=HEUTE,
        herleitung=o2.HERLEITUNG_TARIFSUMME,
    )
    return Buendel(**{**felder, **mehr})


def _seite(url: str) -> str:
    return gzip.decompress(_REDMI.read_bytes()).decode()


def test_offener_anschluss_wird_an_der_seite_gemessen():
    z: dict = {}
    (b,) = stufe_o2.nachmessen([_offen()], _seite, HEUTE, lambda: True, z)
    assert (b.anschlusspreis, b.anschluss_gemessen_am, b.herleitung) == (
        39.99,
        HEUTE,
        "",
    )
    assert z == {"gemessen": 1}


def test_gegenprobe_andere_betraege_lassen_die_luecke():
    z: dict = {}
    (b,) = stufe_o2.nachmessen(
        [_offen(geraet_monatsrate=8.0)], _seite, HEUTE, lambda: True, z
    )
    assert b.anschlusspreis is None and b.herleitung == o2.HERLEITUNG_TARIFSUMME
    assert z == {"widerspricht": 1}


def test_ohne_restzeit_kein_abruf():
    abrufe: list[str] = []
    z: dict = {}
    stufe_o2.nachmessen(
        [_offen()], lambda u: abrufe.append(u) or "", HEUTE, lambda: False, z
    )
    assert abrufe == [] and z == {"frist": 1}


ANGEBOT = {
    "laufzeit_monate": 36,
    "geraet_monatsrate": 7.0,
    "geraet_zuzahlung": 1.0,
    "tarif_monatlich": 19.99,
}


def test_messung_gilt_sieben_tage():
    alt = {"anschlusspreis": 39.99, "anschluss_gemessen_am": "2026-11-14", **ANGEBOT}
    b = stufe_o2.uebernimm(_offen(), alt, HEUTE)
    assert (b.anschlusspreis, b.anschluss_gemessen_am) == (39.99, "2026-11-14")
    assert stufe_o2.ANSCHLUSS_GUELTIG_TAGE == 7


def test_gegenprobe_achttaegige_messung_gilt_nicht():
    alt = {"anschlusspreis": 39.99, "anschluss_gemessen_am": "2026-11-13", **ANGEBOT}
    assert stufe_o2.uebernimm(_offen(), alt, HEUTE).anschlusspreis is None
    ohne_datum = {"anschlusspreis": 39.99, **ANGEBOT}
    assert stufe_o2.uebernimm(_offen(), ohne_datum, HEUTE).anschlusspreis is None


def test_nie_gemessene_zuerst_dann_die_aeltesten():
    saetze = [
        _offen(anschlusspreis=0.0, anschluss_gemessen_am="2026-11-18"),
        _offen(),
        _offen(anschlusspreis=0.0, anschluss_gemessen_am="2026-11-15"),
        _offen(herleitung=""),
    ]
    assert stufe_o2.reihenfolge(saetze) == [1, 2, 0]


def test_restzeit_wie_bei_der_tarifwelt_mit_benannter_reserve():
    tw = geraete_tarifwelt
    voll = tw.JOB_FRIST_SEKUNDEN - tw.VORLAUF_SEKUNDEN
    reserve = stufe_o2.RESERVE_NACH_NACHMESSUNG_SEKUNDEN
    assert stufe_o2.frist(0) == voll - reserve
    assert stufe_o2.frist(voll - reserve) == 0
    assert stufe_o2.frist(voll) == 0


def test_die_nachmessung_laeuft_nach_der_tarifwelt(tmp_path, monkeypatch):
    """Reihenfolge im Gerätelauf: erst die Tarifwelt, dann die o2-Nachmessung."""
    monkeypatch.delenv("TELCO_KLICK_ERGEBNISSE", raising=False)
    folge: list[str] = []
    monkeypatch.setattr(
        geraete_tarifwelt,
        "stufe",
        lambda *a, **k: folge.append("tarifwelt") or {"status": "aus"},
    )
    monkeypatch.setattr(
        geraete_pipeline, "o2_messe", lambda *a, **k: folge.append("o2") or 0
    )
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    for name in ("geraete_katalog.yaml", "farben.yaml"):
        shutil.copy(WURZEL / "config" / name, root / "config" / name)
    (root / "config" / "geraete_quellen.yaml").write_text(
        yaml.safe_dump({"anbieter": [O2_OHNE_ANTWORT]}), encoding="utf-8"
    )
    (root / "data" / "state").mkdir(parents=True)
    shutil.copy(ZUSTAND / "tarife.jsonl", root / "data" / "state" / "tarife.jsonl")
    geraete_pipeline.run_geraete_stage(root, {}, HEUTE, hole=lambda *a, **k: (404, ""))
    assert folge == ["tarifwelt", "o2"]


def test_beleg_nennt_das_messdatum_des_anschlusspreises():
    b = _offen(anschlusspreis=39.99, anschluss_gemessen_am="2026-11-18")
    satz = {"id": b.id, "first_seen": HEUTE, **b.__dict__}
    satz.pop("rabatte"), satz.pop("aktionen"), satz.pop("tarif_phasen")
    ergebnis = aufbereiten([satz], [], [], lade_katalog(lese_wurzel()), heute=HEUTE)
    karten = [k for m in ergebnis["modelle"] for k in m["karten"] if k.get("sku_id")]
    assert [k["anschluss_gemessen_am"] for k in karten] == ["2026-11-18"]


def test_o2_aus_den_quellen_ist_aktiv():
    o2_quelle = lade_quellen(WURZEL).nach_name(stufe_o2.ANBIETER)
    assert o2_quelle is not None and o2_quelle.crawlbar


def test_luecke_vor_bereits_gefuellten_fussnotenzeilen():
    """Prüfung PR 191: 980 von 1425 abgeleiteten Zeilen (Nacht 21.11.) tragen schon
    0,00 € aus der Fußnote (ohne Datum), 445 die Lücke. Bei knapper Restzeit muss die
    Lücke zuerst gemessen werden."""
    gefuellt = [
        _offen(anschlusspreis=0.0, geraet_monatsrate=8.0 + i * 0.01) for i in range(30)
    ]
    saetze = [*gefuellt, _offen()]
    erlaubt = iter([True] * 10 + [False] * 100)
    z: dict = {}
    aus = stufe_o2.nachmessen(saetze, _seite, HEUTE, lambda: next(erlaubt), z)
    assert aus[-1].anschlusspreis == 39.99, z


def test_uebernommener_anschlusspreis_nach_preisaenderung():
    """Prüfung PR 191: dieselbe Bündel-ID, aber andere Rate, Anzahlung und
    Tarifpreis als bei der Messung: der alte Anschlusspreis gilt nicht."""
    alt = {
        "anschlusspreis": 0.0,
        "anschluss_gemessen_am": "2026-11-18",
        "laufzeit_monate": 36,
        "geraet_monatsrate": 7.0,
        "geraet_zuzahlung": 1.0,
        "tarif_monatlich": 19.99,
    }
    neu = _offen(geraet_monatsrate=20.0, geraet_zuzahlung=25.0, tarif_monatlich=24.99)
    assert neu.id == _offen().id
    assert stufe_o2.uebernimm(neu, alt, HEUTE).anschlusspreis is None
    gleich = stufe_o2.uebernimm(_offen(), alt, HEUTE)
    assert (gleich.anschlusspreis, gleich.anschluss_gemessen_am) == (0.0, "2026-11-18")


def test_unlesbare_seite_heisst_nicht_gelesen():
    z: dict = {}
    stufe_o2.nachmessen([_offen()], lambda u: "<html></html>", HEUTE, lambda: True, z)
    assert z == {"nicht_gelesen": 1}


def test_historie_nennt_das_messdatum_des_anschlusspreises(tmp_path):
    from telco_radar.analyze.tco_store import TcoDB

    tco = TcoDB(tmp_path / "geraete_tco.json")
    b = _offen(anschlusspreis=0.0, anschluss_gemessen_am="2026-11-18")
    tco.upsert_buendel([b], HEUTE)
    tco.save(HEUTE)
    tag = (tmp_path / "geraete_tco_historie" / f"{HEUTE}.jsonl").read_text("utf-8")
    assert '"anschluss_gemessen_am": "2026-11-18"' in tag
    assert tco.nach_id(b.id)["anschluss_gemessen_am"] == "2026-11-18"
