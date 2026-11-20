"""Tarifwelt-Stufe: liest ALLE Modelle mit Tarifwelt-Seite und haelt ihr Zeitbudget.

Befund 20.11.2026: `geraete_tarifwelt.lauf` filterte `MODELL_SLUGS` auf die
Pflichtmodelle des Waechters. Die 20 weiteren, sitemap-bestaetigten Modelle
(Baupaket P6) blieben dadurch fuer immer ungelesen. Dazu hatte die Stufe kein
Zeitbudget: mit allen Tarifen je Modell waere der Job (70 Minuten) gerissen.
Kein Netz, kein Zugriff auf data/, kein heutiges Datum.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest
from test_geraete_adapter_tarifwelt import LEITER, fixture_hole

from telco_radar import geraete_tarifwelt
from telco_radar.band_regel import stufe_fuer
from telco_radar.collect.geraete import tarifwelt, tarifwelt_lauf
from telco_radar.collect.geraete.buendel_prioritaet import pflicht_modelle


@dataclass
class _Quelle:
    methode: str
    aktiv: bool
    rate_limit_sekunden: float = 0.0


@dataclass
class _Quellen:
    anbieter: list


def _vodafone_tarife() -> dict:
    return {
        f"vodafone:mobil-{k}": {
            "anbieter": "Vodafone",
            "name": f"Vodafone Mobil {k.upper()} mit Smartphone",
            "datenvolumen_gb": gb,
            "grundgebuehr": 20.0 + i * 10,
        }
        for i, (k, gb) in enumerate(LEITER)
    }


QUELLEN = _Quellen([_Quelle("mediamarkt_tarifwelt", aktiv=True)])


def _hole_slugs():
    """Antwortet auf jede Uebersicht mit Nicht-JSON (eine Luecke je Modell, ein
    Abruf je Modell) und merkt sich die gefragten Seiten."""
    slugs: list[str] = []

    def hole(url, **kw):
        slugs.append(url.rsplit("/", 1)[-1])
        return (200, "kein json")

    return hole, slugs


def test_stufe_liest_auch_die_modelle_ausserhalb_der_pflichtliste():
    hole, slugs = _hole_slugs()
    e = geraete_tarifwelt.lauf(
        QUELLEN, _vodafone_tarife(), hole, "2026-11-20", warte=lambda s: None
    )
    erwartet = [eintrag[3] for eintrag in tarifwelt_lauf.MODELL_SLUGS.values()]
    assert slugs == erwartet
    assert e.modelle == len(tarifwelt_lauf.MODELL_SLUGS)
    ausserhalb = set(tarifwelt_lauf.MODELL_SLUGS) - pflicht_modelle()
    assert len(ausserhalb) >= 20, "Gegenprobe: es gibt Modelle ausserhalb der Pflicht"
    gelesen = {s for s in slugs}
    for modell in ausserhalb:
        assert tarifwelt_lauf.MODELL_SLUGS[modell][3] in gelesen, modell


def test_pflichtmodelle_stehen_vor_den_zusaetzlichen():
    namen = list(tarifwelt_lauf.MODELL_SLUGS)
    pflicht = [i for i, m in enumerate(namen) if m in pflicht_modelle()]
    rest = [i for i, m in enumerate(namen) if m not in pflicht_modelle()]
    assert max(pflicht) < min(rest)


def test_zeitbudget_aufgebraucht_stoppt_vor_dem_naechsten_modell():
    hole, slugs = _hole_slugs()
    stand = {"t": 0.0}

    def monoton():
        return stand["t"]

    def warte(s):
        stand["t"] += 100.0

    def hole_mit_zeit(url, **kw):
        stand["t"] += 100.0
        return hole(url, **kw)

    e = geraete_tarifwelt.lauf(
        QUELLEN,
        _vodafone_tarife(),
        hole_mit_zeit,
        "2026-11-20",
        warte=warte,
        frist_sekunden=250.0,
        monoton=monoton,
    )
    assert e.status == "frist"
    assert e.modelle == 3 and len(slugs) == 3
    namen = list(tarifwelt_lauf.MODELL_SLUGS)
    assert e.ungelesen == namen[3:]
    assert "nicht vollstaendig gelesen" in e.grund
    assert e.als_dict()["ungelesen"] == namen[3:]


def test_ohne_zeitbudget_werden_alle_modelle_gelesen_gegenprobe():
    hole, slugs = _hole_slugs()
    e = geraete_tarifwelt.lauf(
        QUELLEN, _vodafone_tarife(), hole, "2026-11-20", warte=lambda s: None
    )
    assert e.status == "ok" and e.ungelesen == []


def test_stufen_frist_rechnet_gegen_die_restzeit_des_jobs():
    voll = (
        geraete_tarifwelt.JOB_FRIST_SEKUNDEN
        - geraete_tarifwelt.RESERVE_NACH_STUFE_SEKUNDEN
    )
    assert geraete_tarifwelt.stufen_frist(0.0) == voll
    assert geraete_tarifwelt.stufen_frist(1000.0) == voll - 1000.0
    spaet = geraete_tarifwelt.JOB_FRIST_SEKUNDEN - 600.0 - 120.0
    assert geraete_tarifwelt.stufen_frist(spaet) == pytest.approx(120.0)
    assert geraete_tarifwelt.stufen_frist(geraete_tarifwelt.JOB_FRIST_SEKUNDEN) == 0.0
    assert geraete_tarifwelt.stufen_frist(10**9) == 0.0


@pytest.mark.parametrize("vergangen", [0.0, 2000.0, 3500.0])
def test_stufe_reicht_die_restzeit_als_frist_an_den_lauf_weiter(
    monkeypatch, tmp_path, vergangen
):
    import time
    from datetime import UTC, datetime

    from telco_radar.analyze.tco_store import TcoDB
    from telco_radar.tarif_bezug import Tarifbestand

    gesehen = {}

    def lauf(*args, **kwargs):
        gesehen.update(kwargs)
        return geraete_tarifwelt.Ergebnis(status="ok")

    monkeypatch.setattr(geraete_tarifwelt, "lauf", lauf)
    bestand = Tarifbestand(
        [{"tarif_id": tid, **satz} for tid, satz in _vodafone_tarife().items()]
    )

    def stufe(beginn):
        geraete_tarifwelt.stufe(
            QUELLEN,
            bestand,
            lambda url, **kw: (404, ""),
            lambda: datetime(2026, 11, 20, 3, tzinfo=UTC),
            "2026-11-20",
            tmp_path,
            TcoDB(tmp_path / "geraete_tco.json"),
            beginn,
        )

    stufe(time.monotonic() - vergangen)
    erwartet = geraete_tarifwelt.stufen_frist(vergangen)
    assert gesehen["frist_sekunden"] == pytest.approx(erwartet, abs=5.0)
    assert gesehen["bekannt"] == {}
    stufe(None)
    assert gesehen["frist_sekunden"] is None


FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "geraete"
MODELLE = ["apple-iphone-17", "samsung-galaxy-s26"]


def _uhr_je_abruf(hole):
    stand = {"t": 0.0}

    def mit_zeit(url, **kw):
        stand["t"] += 1.0
        return hole(url, **kw)

    return mit_zeit, lambda: stand["t"]


def test_kern_kommt_zuerst_der_rest_ohne_neue_uebersicht_oder_liste():
    hole, aufrufe = fixture_hole()
    lauf = tarifwelt_lauf.lies_modell(
        "samsung-galaxy-s26",
        LEITER,
        hole,
        "2026-11-20",
        warte=lambda s: None,
        nur_kern=True,
    )
    assert lauf.offen and not [z for z in lauf.offen if z.kern]
    nach_kern = len(aufrufe)
    rest = len(lauf.offen)
    tarifwelt_lauf.lies_offene(lauf, hole, "2026-11-20", warte=lambda s: None)
    assert lauf.offen == []
    assert len(aufrufe) == nach_kern + rest
    listen = [u for u in aufrufe if "/tariff?" in u]
    assert len(listen) == len(set(listen))
    uebersichten = [u for u in aufrufe if "?" not in u]
    assert len(uebersichten) == 1


def test_kern_ist_je_netz_und_band_genau_ein_tarif():
    text = (FIXTURES / "tarifwelt_mm_tarifliste_iphone17_20261108.json").read_text()
    tarife = tarifwelt_lauf.vergleichbare_tarife(
        tarifwelt.lies_tarifliste(text), LEITER
    )
    kern = tarifwelt.kern_je_netz_und_band(tarife, LEITER)

    def gruppe(t):
        return (t["netz"], stufe_fuer(t["datenvolumen_gb"], LEITER))

    gruppen = {gruppe(t) for t in tarife}
    assert len(kern) == len(gruppen) < len(tarife)
    for g in gruppen:
        assert sum(t["tarif_id"] in kern for t in tarife if gruppe(t) == g) == 1
    assert tarifwelt.kern_je_netz_und_band([], LEITER) == set()


def _stufe(monkeypatch, frist):
    monkeypatch.setattr(geraete_tarifwelt, "modelle_der_stufe", lambda: MODELLE)
    api, _ = fixture_hole()
    hole, uhr = _uhr_je_abruf(api)
    return geraete_tarifwelt.lauf(
        QUELLEN,
        _vodafone_tarife(),
        hole,
        "2026-11-20",
        warte=lambda s: None,
        frist_sekunden=frist,
        monoton=uhr,
    )


def test_zeitbudget_nur_fuer_den_kern_liest_den_kern_aller_modelle_zuerst(monkeypatch):
    voll = _stufe(monkeypatch, 10_000.0)
    assert voll.status == "ok" and voll.ungelesen == []
    kern_abrufe = 0
    api, aufrufe = fixture_hole()
    for modell in MODELLE:
        kern_abrufe += tarifwelt_lauf.lies_modell(
            modell,
            LEITER,
            api,
            "2026-11-20",
            warte=lambda s: None,
            nur_kern=True,
        ).abrufe
    assert kern_abrufe < voll.abrufe
    knapp = _stufe(monkeypatch, float(kern_abrufe))
    assert knapp.status == "frist"
    assert knapp.abrufe == kern_abrufe
    assert knapp.modelle == len(MODELLE)
    assert knapp.ungelesen == MODELLE
    assert {b.id for b in knapp.buendel} <= {b.id for b in voll.buendel}
    assert {b.id for b in knapp.buendel}
