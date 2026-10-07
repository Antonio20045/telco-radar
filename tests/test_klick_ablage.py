"""Ablage der Klick-Ergebnisse unter ``data/state/klick`` (``analyze.klick_ablage``).

Alles in ``tmp_path``; die Ergebnisdateien tragen echte Lesungen
(``tests/klickergebnisse.py``). Abgelegt wird jede Datei, den Lesestand führt nur eine
gelesene fort; Varianten jenseits der Frischegrenze fallen weg, Seiten bleiben.
"""

from __future__ import annotations

import importlib.util

import pytest
from bestand_pfad import WURZEL, lese_wurzel, verlinke_neben_data
from klickergebnisse import O2_SEITE, erfasst, ergebnisdatei, lauf, o2_lesung

from telco_radar.analyze.klick_ablage import lege_ab
from telco_radar.collect.geraete.klickergebnis import (
    ORDNER,
    STAND_DATEI,
    lies_ergebnisse,
    lies_stand,
    schreibe,
)
from telco_radar.collect.geraete.klicklauf import LAUF_GESTOERT
from telco_radar.geraete_config import lade_katalog

HEUTE = "2026-09-29"
VARIANTE = "o2|apple-iphone-17-pro|256|o2-mobile-unlimited-m-plus-mit-100-mbit-s|36"
_SKRIPT = WURZEL / "scripts" / "klick_ablegen.py"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _o2(datum=HEUTE, **felder):
    kombination = erfasst(o2_lesung("256 GB", "O2 Mobile Unlimited M Plus", 36))
    seiten = [(O2_SEITE, lauf(O2_SEITE, [kombination], **felder))]
    return ergebnisdatei("o2", "o2", seiten, datum)


def _gestoert():
    gestoert = lauf(
        O2_SEITE, [], status=LAUF_GESTOERT, grund="Abruf gestört (HTTP 403)"
    )
    return ergebnisdatei("Telekom", "telekom", [(O2_SEITE, gestoert)], HEUTE)


def test_jede_datei_wird_abgelegt_nur_gelesene_fuehren_den_stand(tmp_path, katalog):
    ziel = tmp_path / "klick"

    ablage = lege_ab([_o2(), _gestoert()], ziel, katalog, HEUTE)

    assert ablage.abgelegt == ["o2", "telekom"] and ablage.abgelehnt == []
    gelesen, unlesbar = lies_ergebnisse(ziel)
    assert [d["anbieter"] for d in gelesen] == ["o2", "telekom"] and unlesbar == []
    stand = lies_stand(ziel / STAND_DATEI)
    assert stand["seiten"] == {"o2": {O2_SEITE.adresse: HEUTE}}
    assert stand["varianten"] == {"o2": {VARIANTE: HEUTE}}


def test_alte_varianten_fallen_weg_seiten_bleiben(tmp_path, katalog):
    ziel = tmp_path / "klick"
    alt = "o2|apple-iphone-17-pro|512|o2-mobile-unlimited-m-plus|24"
    jung = "o2|apple-iphone-17-pro|512|o2-mobile-unlimited-m-plus|36"
    schreibe(
        ziel / STAND_DATEI,
        {
            "format": 1,
            "seiten": {"o2": {O2_SEITE.adresse: "2026-09-01"}},
            "varianten": {"o2": {alt: "2026-09-26", jung: "2026-09-27"}},
        },
    )

    stand = lege_ab([], ziel, katalog, HEUTE).stand

    assert stand["varianten"] == {"o2": {jung: "2026-09-27"}}
    assert stand["seiten"] == {"o2": {O2_SEITE.adresse: "2026-09-01"}}
    assert lies_stand(ziel / STAND_DATEI) == stand


def test_ungueltiger_schluessel_wird_nicht_abgelegt(tmp_path, katalog):
    daten = {**_o2(), "anbieter": "../o2"}

    ablage = lege_ab([daten], tmp_path / "klick", katalog, HEUTE)

    assert ablage.abgelegt == []
    assert ablage.abgelehnt == ["Anbieterschlüssel '../o2' ungültig"]
    assert sorted(p.name for p in tmp_path.rglob("*.json")) == [STAND_DATEI]


def _skript():
    spec = importlib.util.spec_from_file_location("klick_ablegen", _SKRIPT)
    skript = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skript)
    return skript


def test_skript_legt_die_artefakte_ins_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    verlinke_neben_data(root)
    quelle = tmp_path / "artefakte"
    schreibe(quelle / "klick-o2" / "o2.json", _o2())
    (quelle / "klick-vodafone").mkdir()
    (quelle / "klick-vodafone" / "vodafone.json").write_text("{", encoding="utf-8")

    rueckgabe = _skript().main(["--root", str(root), "--quelle", str(quelle)])

    assert rueckgabe == 1
    assert sorted(p.name for p in (root / ORDNER).iterdir()) == [
        "klick_stand.json",
        "o2.json",
    ]
    assert lies_stand(root / ORDNER / STAND_DATEI)["seiten"] == {
        "o2": {O2_SEITE.adresse: HEUTE}
    }


def test_skript_ohne_artefakte_laesst_alles_stehen(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    rueckgabe = _skript().main(["--root", str(root), "--quelle", str(tmp_path / "x")])

    assert rueckgabe == 0 and list(root.iterdir()) == []
