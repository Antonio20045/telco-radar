"""Tarifwelt: eine Sekunde von Abruf zu Abruf, nicht zwei.

Lauf 44858465074 (21.11.2026): 561 Abrufe in 1121 s, Median-Abstand 2,0 s,
obwohl `PAUSE_SEKUNDEN` seit dem 20.11. 1 s ist. Zwei Bremsen lagen
hintereinander: der Leser wartete 1 s NACH dem Ende des letzten Abrufs, danach
liess die `Abrufschleuse` den Abruf erst 2 s nach dem Start des letzten durch
(`rate_limit_sekunden` fehlte in `config/geraete_quellen.yaml`, also galt der
Standard 2 s aus `geraete_config`). Mit allen 808 Abrufen der 42 Modelle waren
das 1616 s fuer ein Budget von 1121 s. Uhr und Schlaf sind gefaelscht: kein
Netz, kein Warten, kein heutiges Datum.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_geraete_adapter_tarifwelt import LEITER, fixture_hole

from telco_radar.collect.geraete import tarifwelt_lauf
from telco_radar.geraete_abruf import hole_fuer_anbieter
from telco_radar.geraete_config import lade_quellen
from telco_radar.geraete_tarifwelt import METHODE

WURZEL = Path(__file__).resolve().parents[1]


def _abstaende(monkeypatch, latenz: float) -> list[float]:
    """Startzeiten der Abrufe eines Modells durch den echten Abrufweg der Stufe
    (`hole_fuer_anbieter` mit der Quelle aus der Config), jede Antwort braucht
    `latenz` Sekunden."""
    uhr = {"t": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: uhr["t"])
    monkeypatch.setattr(time, "sleep", lambda s: uhr.update(t=uhr["t"] + max(s, 0)))
    roh, _ = fixture_hole()
    starts: list[float] = []

    def hole(url, *args, **kwargs):
        if url.endswith("/robots.txt"):
            return (404, "")
        starts.append(uhr["t"])
        uhr["t"] += latenz
        return roh(url, **kwargs)

    anbieter = next(a for a in lade_quellen(WURZEL).anbieter if a.methode == METHODE)
    gebremst = hole_fuer_anbieter(
        hole, anbieter, lambda: datetime(2026, 11, 21, 3, 30, tzinfo=UTC)
    )
    tarifwelt_lauf.lies_modell(
        "apple-iphone-17", LEITER, gebremst, "2026-11-21", warte=time.sleep
    )
    assert len(starts) > 5
    return [b - a for a, b in zip(starts, starts[1:], strict=False)]


def test_abstand_ist_die_pause_ab_dem_start_des_letzten_abrufs(monkeypatch):
    abstaende = _abstaende(monkeypatch, latenz=0.3)
    assert max(abstaende) == pytest.approx(tarifwelt_lauf.PAUSE_SEKUNDEN)
    assert min(abstaende) == pytest.approx(tarifwelt_lauf.PAUSE_SEKUNDEN)


def test_gegenprobe_langsame_antwort_wartet_nicht_noch_zusaetzlich(monkeypatch):
    """Braucht die Antwort laenger als die Pause, geht der naechste Abruf sofort."""
    abstaende = _abstaende(monkeypatch, latenz=1.5)
    assert max(abstaende) == pytest.approx(1.5)


def test_die_schleuse_der_quelle_bremst_nicht_staerker_als_die_pause():
    anbieter = next(a for a in lade_quellen(WURZEL).anbieter if a.methode == METHODE)
    assert anbieter.rate_limit_sekunden == tarifwelt_lauf.PAUSE_SEKUNDEN
