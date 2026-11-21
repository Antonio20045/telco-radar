"""Fällt eine Telekom-Übersicht aus, verschwinden ihre Seiten nicht still (PR 173).

Prüferbefund 20.11.2026 (Reproduktion ``/tmp/pruefer/test_uebersicht_ausfall.py``):
war eine Übersicht des letzten Laufs nicht gelesen (HTTP 202, gestört), fielen die
Seiten ihres Tarifs ohne Hinweis weg (248 → 195); fielen alle aus, blieben 40 Seiten,
und weil die Ablage ``telekom.json`` überschreibt, hielt der Ausfall bis zum nächsten
Tag an. Jetzt trägt die Ablage den Kachelvorrat der zuletzt ganz gelesenen Übersicht
weiter (``fuehre_vorrat``, höchstens ``VORRAT_HOECHSTALTER_TAGE`` alt), und jede nicht
ganz gelesene Übersicht steht als Grund im Ergebnis und auf der Seite.
Grundlage ist die echte Fixture ``telekom_uebersichten_20261120.json``.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
from bestand_pfad import AUTO_KATALOG, KACHELN, ZUSTAND, verlinke_neben_data

from telco_radar.analyze.klick_ablage import lege_ab
from telco_radar.analyze.klick_erfassung import erfassungsgrund
from telco_radar.collect.geraete.klickliste_kacheln import (
    VORRAT,
    VORRAT_HOECHSTALTER_TAGE,
    fuehre_vorrat,
)
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele

GESTERN = "2026-11-20"
HEUTE = "2026-11-21"
GRUND = "Abruf gestört (HTTP 202)"


def _gut() -> dict:
    return json.loads(KACHELN.read_text(encoding="utf-8"))


def _gestoert(daten: dict, stellen, datum: str = HEUTE) -> dict:
    """Der Lauf von ``datum``: die Übersichten an ``stellen`` gestört, ohne Sätze."""
    neu = copy.deepcopy(daten)
    neu["datum"] = datum
    for stelle in stellen:
        uebersicht = neu["uebersichten"][stelle]
        uebersicht.update(status="gestoert", grund=GRUND, saetze=[], seiten=[])
        uebersicht.pop(VORRAT, None)
    return neu


def _root(tmp_path: Path, daten: dict | str) -> Path:
    root = tmp_path / "r"
    (root / "data" / "state" / "klick").mkdir(parents=True)
    shutil.copy2(ZUSTAND / AUTO_KATALOG, root / "data" / "state" / AUTO_KATALOG)
    verlinke_neben_data(root)
    text = daten if isinstance(daten, str) else json.dumps(daten, ensure_ascii=False)
    (root / "data" / "state" / "klick" / "telekom.json").write_text(text, "utf-8")
    return root


def _telekom(root: Path):
    ziele = lade_ziele(root, TAGESDATEI, hoechste=None, auto=True)
    return [z for z in ziele if z.name == "Telekom"]


def _seiten(ziele) -> int:
    return sum(len(z.seiten) for z in ziele)


@pytest.fixture(scope="module")
def voll(tmp_path_factory) -> int:
    return _seiten(_telekom(_root(tmp_path_factory.mktemp("voll"), _gut())))


def test_gesund_viele_seiten_ohne_grund(tmp_path, voll):
    ziele = _telekom(_root(tmp_path, _gut()))
    assert voll > 200
    assert all(z.seitengrund is None for z in ziele)


def test_alle_uebersichten_gestoert_kein_totalausfall(tmp_path, voll):
    heute = fuehre_vorrat(_gestoert(_gut(), range(5)), _gut())

    ziele = _telekom(_root(tmp_path, heute))

    assert _seiten(ziele) == voll
    grund = ziele[0].seitengrund
    assert grund is not None and grund.count("nicht ganz gelesen") == 5
    assert "Seiten aus den Kacheln vom 20.11.2026" in grund


def test_eine_uebersicht_gestoert_tarif_faellt_nicht_still_weg(tmp_path, voll):
    heute = fuehre_vorrat(_gestoert(_gut(), [1]), _gut())

    ziele = _telekom(_root(tmp_path, heute))

    assert _seiten(ziele) == voll
    grund = ziele[0].seitengrund or ""
    assert f"MagentaMobil XS am 21.11.2026 nicht ganz gelesen ({GRUND})" in grund
    assert all(z.seitengrund == grund for z in ziele)


def test_ohne_vorrat_wird_der_tarif_benannt_nicht_still(tmp_path, voll):
    """Der Befund des Prüfers wörtlich: gestört und kein Vorrat. Dann fehlen die Seiten
    des Tarifs, aber benannt."""
    ziele = _telekom(_root(tmp_path, _gestoert(_gut(), [1])))

    assert 0 < _seiten(ziele) < voll
    grund = ziele[0].seitengrund or ""
    assert "nicht ganz gelesen" in grund
    assert f"keine Kacheln jünger als {VORRAT_HOECHSTALTER_TAGE} Tage" in grund


def test_zu_alter_vorrat_ist_eine_luecke(tmp_path, voll):
    spaet = f"2026-11-{20 + VORRAT_HOECHSTALTER_TAGE + 1}"
    heute = fuehre_vorrat(_gestoert(_gut(), [1], spaet), _gut())

    ziele = _telekom(_root(tmp_path, heute))

    assert _seiten(ziele) < voll
    assert "keine Kacheln jünger als" in (ziele[0].seitengrund or "")


def test_kaputte_telekom_datei_legt_nicht_alle_anbieter_lahm(tmp_path):
    root = _root(tmp_path, "{kaputt")

    ziele = lade_ziele(root, TAGESDATEI, hoechste=None, auto=True)

    assert {z.name for z in ziele} >= {"1&1", "Vodafone", "Telekom"}
    telekom = [z for z in ziele if z.name == "Telekom" and z.seitenquelle]
    assert all("nicht lesbar" in (z.seitengrund or "") for z in telekom)


def test_ablage_traegt_den_vorrat_ueber_zwei_ausfalltage(tmp_path):
    ordner = tmp_path / "klick"
    gut = {**_gut(), "anbieter": "telekom", "seiten": []}
    lege_ab([gut], ordner)
    tag1 = {**_gestoert(gut, [1]), "anbieter": "telekom"}
    lege_ab([tag1], ordner)
    tag2 = {**_gestoert(gut, [1], "2026-11-22"), "anbieter": "telekom"}

    lege_ab([tag2], ordner)

    abgelegt = json.loads((ordner / "telekom.json").read_text("utf-8"))
    xs = abgelegt["uebersichten"][1]
    assert xs["status"] == "gestoert"
    assert xs[VORRAT]["datum"] == GESTERN
    assert xs[VORRAT]["tarif"] == "MagentaMobil XS"
    urls = {s["url"] for s in _gut()["uebersichten"][1]["saetze"]}
    assert {k["url"] for k in xs[VORRAT]["kacheln"]} == urls
    assert VORRAT not in abgelegt["uebersichten"][0]


def test_teilausfall_erreicht_die_seite_als_benannte_luecke():
    grund = "236 Seiten aus den Übersichten (Übersicht MagentaMobil XS …)"
    eintrag = {
        "anbieter": "Telekom",
        "laufstatus": "gelesen",
        "alter_tage": 0,
        "datum": HEUTE,
        "seitengrund": grund,
    }

    assert erfassungsgrund(eintrag) == f"Telekom teilweise erfasst: {grund}"
    assert erfassungsgrund({**eintrag, "seitengrund": None}) is None
