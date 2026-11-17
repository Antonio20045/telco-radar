"""Die Punktgrafik der Herstellersicht (Antonio, 17.11.2026).

Geprüft wird, was das Bild behauptet: die Achse umfasst jeden Wert und die
Null, ein Punkt sitzt an der Stelle seines Prozentwertes, ein fehlender Preis
ist kein Punkt bei 0, sondern eine benannte Lücke, und die Linie spannt vom
günstigsten zum teuersten Punkt. Keine Zahl ist fest verdrahtet.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from telco_radar.report import geraete_hersteller as hm
from telco_radar.report import geraete_hersteller_punkte as hp


def _zeile(name: str, werte: dict[str, tuple], gesamt: bool = False) -> dict:
    return {
        "hersteller": name,
        "name": name,
        "gesamt": gesamt,
        "zellen": [hm._zelle(a, m, n) for a, (m, n) in werte.items()],
    }


def _svg(zeilen: list[dict], ach: dict, schmal: bool = False) -> BeautifulSoup:
    return BeautifulSoup(hp.svg(zeilen, ach, "Einheit", schmal), "html.parser")


def test_achse_umfasst_jeden_wert_und_immer_die_null():
    ach = hp.achse([12.0, 31.5])
    assert ach["von"] <= 0 <= ach["bis"]
    assert ach["von"] <= 12.0 and ach["bis"] >= 31.5
    assert 0 in ach["ticks"]
    assert all(t % ach["schritt"] == 0 for t in ach["ticks"])
    assert len(ach["ticks"]) <= hp.MAX_TICKS


def test_achse_ohne_werte_ist_keine_leere_achse_sondern_none():
    assert hp.achse([]) is None


def test_punkt_sitzt_auf_seinem_prozentwert():
    ach = hp.achse([-40.0, 40.0])
    links = hp.x_fuer(ach["von"], ach, hp.BREIT)
    rechts = hp.x_fuer(ach["bis"], ach, hp.BREIT)
    assert links == hp.BREIT["x0"] and rechts == hp.BREIT["x1"]
    mitte = hp.x_fuer(0.0, ach, hp.BREIT)
    anteil = (0.0 - ach["von"]) / (ach["bis"] - ach["von"])
    assert abs(mitte - (links + anteil * (rechts - links))) < 1e-9


def test_ausreisser_bleibt_im_bild_und_laeuft_nicht_hinaus():
    ach = hp.achse([-10.0, 10.0])
    assert hp.x_fuer(999.0, ach, hp.BREIT) == hp.BREIT["x1"]
    assert hp.x_fuer(-999.0, ach, hp.BREIT) == hp.BREIT["x0"]


def test_zeile_zeichnet_punkt_spanne_und_beschriftung_an_den_enden():
    ach = hp.achse([-20.0, 30.0])
    zeilen = [_zeile("Apple", {"Telekom": (-12.0, 4), "congstar": (25.0, 4)})]
    s = _svg(zeilen, ach)
    g = s.select_one('.gr-hm-zeile[data-hersteller="Apple"]')
    punkte = g.select(".gr-pp-punkt")
    assert [p["data-anbieter"] for p in punkte] == ["Telekom", "congstar"]
    lage = {
        p["data-anbieter"]: float(
            re.match(r"translate\(([-\d.]+) ", p["transform"]).group(1)
        )
        for p in punkte
    }
    assert lage["Telekom"] == round(hp.x_fuer(-12.0, ach, hp.BREIT), 1)
    assert lage["congstar"] == round(hp.x_fuer(25.0, ach, hp.BREIT), 1)
    spanne = g.select_one(".gr-pp-spanne")
    assert not spanne.has_attr("hidden")
    assert float(spanne["x1"]) == lage["Telekom"]
    assert float(spanne["x2"]) == lage["congstar"]
    assert g.select_one(".gr-hm-tief").text == hm.prozent_text(-12.0)
    assert g.select_one(".gr-hm-hoch").text == hm.prozent_text(25.0)


def test_fehlender_preis_ist_kein_punkt_bei_null_sondern_eine_benannte_luecke():
    ach = hp.achse([-20.0, 30.0])
    zeilen = [_zeile("Samsung", {"Telekom": (-12.0, 4), "o2": (None, 0)})]
    s = _svg(zeilen, ach)
    o2 = s.select_one('.gr-pp-punkt[data-anbieter="o2"]')
    assert o2.has_attr("hidden")
    assert o2.title.text == f"o2: {hp.KEIN_PREIS}"
    assert s.select_one(".gr-pp-fehlt").text == f"o2: {hp.KEIN_PREIS}"
    assert hp.fehlt_text(zeilen[0]["zellen"]) == f"o2: {hp.KEIN_PREIS}"


def test_einzelner_punkt_bekommt_keine_spanne_und_keine_zweite_zahl():
    ach = hp.achse([-20.0, 30.0])
    zeilen = [_zeile("Fairphone", {"Telekom": (None, 0), "1&1": (16.0, 1)})]
    g = _svg(zeilen, ach).select_one(".gr-hm-zeile")
    assert g.select_one(".gr-pp-spanne").has_attr("hidden")
    assert g.select_one(".gr-hm-tief").text == ""
    assert g.select_one(".gr-hm-hoch").text == hm.prozent_text(16.0)


def test_tooltip_nennt_wert_richtung_und_modellzahl():
    zelle = hm._zelle("Telekom", -12.0, 1)
    assert hp.titel(zelle) == (
        f"Telekom: {hm.prozent_text(-12.0)} · günstiger · {hm.modell_wort(1)}"
    )


def test_kleine_stichprobe_ist_blasser_und_sagt_es_im_tooltip():
    ach = hp.achse([-20.0, 30.0])
    zeilen = [_zeile("Apple", {"Telekom": (-12.0, hm.KLEIN - 1)})]
    p = _svg(zeilen, ach).select_one(".gr-pp-punkt")
    assert "gr-pp-duenn" in p["class"]
    assert "nur" in p.title.text


def test_null_ist_die_vodafone_linie_und_traegt_eigene_teilstrichfarbe():
    ach = hp.achse([-20.0, 30.0])
    s = _svg([_zeile("Apple", {"Telekom": (-12.0, 4)})], ach)
    assert len(s.select(".gr-pp-null")) == 1
    assert [t.text for t in s.select(".gr-pp-tick--null")] == ["0"]
    assert hp.tick_text(0) == "0" and hp.tick_text(20) == hm.prozent_text(20)


def test_legende_nennt_blasse_punkte_als_kleine_stichprobe():
    spalten = [{"name": "Telekom", "slug": "telekom", "legende": "Telekom"}]
    aus = hp.legende(spalten)
    letzter = aus[-1]
    assert letzter["duenn"] is True
    assert f"weniger als {hm.KLEIN}" in letzter["name"]
    assert all(not a["duenn"] for a in aus[:-1])


def test_beide_breiten_zeichnen_dieselben_zeilen_an_eigener_stelle():
    ach = hp.achse([-20.0, 30.0])
    zeilen = [_zeile("Apple", {"Telekom": (-12.0, 4)})]
    breit = _svg(zeilen, ach).select_one(".gr-pp-punkt")["transform"]
    schmal = _svg(zeilen, ach, schmal=True).select_one(".gr-pp-punkt")["transform"]
    assert breit != schmal
    assert hp.MASSE == {"breit": hp.BREIT, "schmal": hp.SCHMAL}


def test_jede_zeile_traegt_ihre_hoehe_fuer_app_js():
    """`app.js` verschiebt die Punkte auf der Zeilenhöhe, die der Server
    gezeichnet hat - sie steht am Gruppenknoten, nichts wird geraten."""
    ach = hp.achse([-20.0, 30.0])
    zeilen = [_zeile("Apple", {"Telekom": (-12.0, 4)}), _zeile("Alle", {}, True)]
    gruppen = _svg(zeilen, ach).select(".gr-hm-zeile")
    hoehen = [float(g["data-y"]) for g in gruppen]
    assert hoehen == [
        hp.BREIT["kopf"] + hp.BREIT["punkt_y"],
        hp.BREIT["kopf"] + hp.BREIT["zeile"] + hp.BREIT["punkt_y"],
    ]
    assert "gr-hm-zeile--alle" in gruppen[1]["class"]
