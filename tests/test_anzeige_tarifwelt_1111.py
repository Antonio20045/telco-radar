"""Zwei Anzeigefehler der Prüfung vom 11.11.2026 rund um Saturn/MediaMarkt mit Tarif.

(1) Die drei Netzzeilen („Saturn/MediaMarkt · Telekom-Netz“ …) hatten keinen Stil und
standen 48-mal mit dem Zusatz „(Farbe nicht hinterlegt)“ auf der Geräteseite.
(2) Die Tafel „Welche Händler keine Daten liefern“ nannte die Quelle „MediaMarkt/Saturn
Tarifwelt“, während ihre Bündel auf derselben Seite standen. Gegenproben: ein fremder
Name bleibt die benannte Lücke; ohne frisches Bündel bleibt die Quelle in der Liste.
"""

from __future__ import annotations

import pytest

from telco_radar.collect.geraete.tarifwelt import anbieter_zeile
from telco_radar.report import anbieter_farben as af
from telco_radar.report import geraete_radar
from telco_radar.report.geraete_tarifwelt_lage import liefert, ohne_lieferndes
from telco_radar.report.geraete_tco_grafik import anbieter_slug
from telco_radar.tarifwelt_bestand import METHODE, PRAEFIX

QUELLE = "MediaMarkt/Saturn Tarifwelt"
NETZE = ("o2", "freenet - Telekom", "freenet - Vodafone")


@pytest.mark.parametrize("netz", NETZE)
def test_jede_netzzeile_der_tarifwelt_hat_einen_stil(netz):
    name = anbieter_zeile(netz)
    assert af.ist_bekannt(name)
    assert af.legendenname(name) == name
    stil = af.stil_fuer(name)
    assert stil.farbe == af.GRAU_HAENDLER and stil.strich == "gestrichelt"
    assert stil.slug == anbieter_slug(name)


def test_die_netzzeilen_unterscheiden_sich_an_der_form():
    marker = [af.stil_fuer(anbieter_zeile(n)).marker for n in NETZE]
    assert len(set(marker)) == len(marker) and "kreuz" not in marker
    assert af.ist_bekannt("MediaMarkt")


def test_gegenprobe_fremder_name_bleibt_die_benannte_luecke():
    name = "Saturn/MediaMarkt · Mond-Netz"
    assert not af.ist_bekannt(name)
    assert af.legendenname(name).endswith(f"({af.LUECKE_NAME_ZUSATZ})")


def _quellenlage() -> dict:
    zeile = {"typ": "handel", "zustand": "ohne_daten", "aktiv": True, "grund": "x"}
    return {
        "zeilen": [
            {**zeile, "name": QUELLE, "methode": METHODE},
            {**zeile, "name": "Coolblue", "methode": "html", "aktiv": False},
        ]
    }


def _tco(frisch: bool = True, gesamt: float | None = 1385.69) -> dict:
    karte = {"tarif_id": f"{PRAEFIX}123", "frisch": frisch, "gesamt": gesamt}
    return {"modelle": [{"karten": [karte, {"tarif_id": "o2:m", "frisch": True}]}]}


def test_tarifwelt_mit_frischem_buendel_steht_nicht_unter_ohne_daten():
    lage = _quellenlage()
    fehlt = geraete_radar.nicht_erhebbar(lage)
    assert [z["anbieter"] for z in fehlt] == ["Coolblue", QUELLE]
    assert liefert(_tco())
    assert [z["anbieter"] for z in ohne_lieferndes(fehlt, lage, _tco())] == ["Coolblue"]
    tafel = geraete_radar.radar(_tco() | {"modelle": []}, {}, lage)
    assert QUELLE in [z["anbieter"] for z in tafel["nicht_erhebbar"]]


@pytest.mark.parametrize("tco", [_tco(frisch=False), _tco(gesamt=None), {}])
def test_gegenprobe_ohne_frisches_buendel_bleibt_die_quelle_genannt(tco):
    lage = _quellenlage()
    fehlt = geraete_radar.nicht_erhebbar(lage)
    assert not liefert(tco)
    assert ohne_lieferndes(fehlt, lage, tco) == fehlt
