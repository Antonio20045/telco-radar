"""Ablage der Klick-Ergebnisse unter ``data/state/klick`` (``analyze.klick_ablage``).

Alles in ``tmp_path``; die Ergebnisdateien tragen echte Lesungen
(``tests/klickergebnisse.py``). Abgelegt wird jede Datei. Den Lesestand der Rotation
führt jede Datei fort, auch eine leere; eine an der Zeitgrenze abgeschnittene Seite
zählt nicht als gelesen. Varianten führt der Lesestand nicht: Vorrang steht im Bestand.
"""

from __future__ import annotations

import importlib.util

import pytest
from bestand_pfad import WURZEL, verlinke_neben_data
from klickergebnisse import O2_SEITE, erfasst, ergebnisdatei, lauf, o2_lesung

from telco_radar.analyze.klick_ablage import lege_ab
from telco_radar.collect.geraete.klickergebnis import (
    LAUF_LEER,
    ORDNER,
    STAND_DATEI,
    lies_ergebnisse,
    lies_stand,
    schreibe,
)
from telco_radar.collect.geraete.klicklauf import (
    LAUF_GELESEN,
    LAUF_GESTOERT,
    LAUF_ZEITGRENZE,
)

HEUTE = "2026-09-29"
FRUEHER = "2026-09-01"
_SKRIPT = WURZEL / "scripts" / "klick_ablegen.py"


def _o2(datum=HEUTE, kombinationen=None, **felder):
    if kombinationen is None:
        kombinationen = [erfasst(o2_lesung("256 GB", "O2 Mobile Unlimited M Plus", 36))]
    seiten = [(O2_SEITE, lauf(O2_SEITE, kombinationen, **felder))]
    return ergebnisdatei("o2", "o2", seiten, datum)


def _gestoert():
    gestoert = lauf(
        O2_SEITE, [], status=LAUF_GESTOERT, grund="Abruf gestört (HTTP 403)"
    )
    return ergebnisdatei("Telekom", "telekom", [(O2_SEITE, gestoert)], HEUTE)


def test_jede_datei_wird_abgelegt_gelesene_seiten_fuehren_den_stand(tmp_path):
    ziel = tmp_path / "klick"

    ablage = lege_ab([_o2(), _gestoert()], ziel)

    assert ablage.abgelegt == ["o2", "telekom"] and ablage.abgelehnt == []
    gelesen, unlesbar = lies_ergebnisse(ziel)
    assert [d["anbieter"] for d in gelesen] == ["o2", "telekom"] and unlesbar == []
    stand = lies_stand(ziel / STAND_DATEI)
    assert stand["seiten"] == {"o2": {O2_SEITE.adresse: HEUTE}}
    assert "varianten" not in stand


@pytest.mark.parametrize(
    ("kombinationen", "seitenstatus", "laufstatus", "datum"),
    [
        ([], LAUF_GELESEN, LAUF_LEER, HEUTE),
        (None, LAUF_ZEITGRENZE, LAUF_GELESEN, FRUEHER),
    ],
    ids=["leer", "zeitgrenze"],
)
def test_rotation_nach_leerem_lauf_und_nicht_nach_abgeschnittener_seite(
    tmp_path, kombinationen, seitenstatus, laufstatus, datum
):
    """Ein Lauf ohne Erfasstes hat die Seite ganz gelesen: sie rückt nach hinten. Eine
    an der Zeitgrenze abgeschnittene Seite bleibt vorn, auch wenn der Lauf vorher eine
    Variante erfasst hat (deren Messung zählt im Gerätelauf, die Rotation nicht)."""
    ziel = tmp_path / "klick"
    schreibe(
        ziel / STAND_DATEI, {"format": 1, "seiten": {"o2": {O2_SEITE.adresse: FRUEHER}}}
    )
    daten = _o2(kombinationen=kombinationen, status=seitenstatus)

    stand = lege_ab([daten], ziel).stand

    assert daten["laufstatus"] == laufstatus
    assert stand["seiten"] == {"o2": {O2_SEITE.adresse: datum}}
    assert lies_stand(ziel / STAND_DATEI) == stand


def test_ungueltiger_schluessel_wird_nicht_abgelegt(tmp_path):
    daten = {**_o2(), "anbieter": "../o2"}

    ablage = lege_ab([daten], tmp_path / "klick")

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
