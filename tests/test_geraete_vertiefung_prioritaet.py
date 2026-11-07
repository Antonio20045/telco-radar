"""Pflichtmodelle zuerst in die Buendel-Vertiefung.

BEFUND 07.11.2026
-----------------
`o2.vertiefe_buendel` teilt ihr Zeitbudget ueber ALLE Geraete des Katalogs,
in Katalogreihenfolge. Ohne eigene Reihenfolge blieb das Budget oft an
Geraeten ohne Pflichtzelle (`config/geraete_abdeckung.yaml`) haengen, bevor
Pflichtmodelle wie iPhone Air oder Pixel 11 ihre groesseren Speicherstufen
erreichten. Die Pflichtliste entscheidet jetzt die Reihenfolge, bevor die
Vertiefung beginnt - dieselbe Datei, die der Waechter schon prueft, keine
neue Sonderliste.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete import buendel_prioritaet, sammle_anbieter
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent


def test_pflicht_modelle_kommt_aus_der_abdeckung_config():
    modelle = buendel_prioritaet.pflicht_modelle()
    assert "apple-iphone-17-pro" in modelle
    assert "samsung-galaxy-s26" in modelle
    assert len(modelle) >= 17


def test_nach_prioritaet_stellt_pflichtmodelle_stabil_voran():
    saetze = [
        {"device_id": "motorola-edge-60-neo", "n": 1},
        {"device_id": "apple-iphone-17-pro", "n": 2},
        {"device_id": "xiaomi-17", "n": 3},
        {"device_id": "samsung-galaxy-s26", "n": 4},
        {"device_id": "apple-iphone-17", "n": 5},
    ]
    geordnet = buendel_prioritaet.nach_prioritaet(saetze)
    pflicht = buendel_prioritaet.pflicht_modelle()
    grenze = sum(1 for s in saetze if s["device_id"] in pflicht)

    assert all(s["device_id"] in pflicht for s in geordnet[:grenze])
    assert all(s["device_id"] not in pflicht for s in geordnet[grenze:])
    assert [s["n"] for s in geordnet[:grenze]] == sorted(
        s["n"] for s in saetze if s["device_id"] in pflicht
    )
    assert [s["n"] for s in geordnet[grenze:]] == sorted(
        s["n"] for s in saetze if s["device_id"] not in pflicht
    )


def test_ohne_pflichtliste_bleibt_die_reihenfolge_unveraendert(monkeypatch):
    monkeypatch.setattr(buendel_prioritaet, "pflicht_modelle", lambda: frozenset())
    saetze = [{"device_id": "a"}, {"device_id": "b"}]
    assert buendel_prioritaet.nach_prioritaet(saetze) is saetze


def _o2_sammler_bilanz():
    with gzip.open(
        _FIX / "o2_vertiefung_iphone17pro.json.gz", "rt", encoding="utf-8"
    ) as fh:
        mitschnitt = json.load(fh)
    katalog_url = (
        "https://www.o2online.de/e-shop/rest/catalog/o2shop/"
        "privatkunden/ratenzahlung/default/__not-specified__/"
        "__not-specified__/__not-specified__"
    )
    antworten = dict(mitschnitt["antworten"])
    antworten[katalog_url] = json.dumps(mitschnitt["katalog"])

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /postpaid/\n")
        if url not in antworten:
            return (404, "")
        return (200, antworten[url])

    anbieter = Anbieter(
        name="o2",
        typ="netzbetreiber",
        methode="o2_katalog",
        basis_url="https://www.o2online.de",
        rate_limit_sekunden=0,
        kopfzeilen={"Accept": "application/vnd.commerce.message+json"},
        einstiege=[Einstieg(url=katalog_url, kind="buendel")],
    )
    return sammle_anbieter(
        anbieter,
        lade_katalog(lese_wurzel()),
        lade_farben(_WURZEL),
        hole,
        "2026-09-29",
        RobotsWaechter(hole=hole),
        datetime(2026, 9, 29, 3, tzinfo=UTC),
    )


def test_der_sammler_haengt_jedem_buendel_seine_device_id_an():
    bilanz = _o2_sammler_bilanz()
    assert bilanz.buendel
    assert all(b.get("device_id") == "apple-iphone-17-pro" for b in bilanz.buendel)
