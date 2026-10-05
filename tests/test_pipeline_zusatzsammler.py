"""Ein Zusatzsammler, dessen Modul nicht lädt, fällt allein aus, nicht der Lauf."""

from __future__ import annotations

import logging
import sys

from telco_radar import pipeline

AUS = {
    "lieferzeit_radar_aktiv": False,
    "aenderungsradar_aktiv": False,
    "tarif_radar_aktiv": False,
    "ct_radar_aktiv": False,
}


def test_kaputter_sammlerimport_ueberspringt_nur_diesen_sammler(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setitem(sys.modules, "telco_radar.collect.lieferzeit", None)
    settings = {**AUS, "lieferzeit_radar_aktiv": True}

    with caplog.at_level(logging.ERROR, logger="telco_radar"):
        items, bilanzen = pipeline._zusatzsammler(tmp_path, settings, "")

    assert items == []
    assert bilanzen == {"lieferzeit": {}, "aenderung": {}, "tarif": {}, "ct": {}}
    assert any(
        "Lieferzeit-Radar uebersprungen" in r.getMessage()
        and "telco_radar.collect.lieferzeit" in r.getMessage()
        for r in caplog.records
    )
