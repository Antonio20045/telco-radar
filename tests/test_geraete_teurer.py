"""Die Listen "Vodafone über 10 % teurer" der Geräteseite (10.10.2026)."""

from __future__ import annotations

from telco_radar.report import geraete_teurer as gt


def _modell(schluessel, ab, delta, prozent=None, band="m"):
    """Eine Katalogzeile; `delta` ist Wettbewerber minus Vodafone im Band."""
    teurer = (
        {
            "anbieter": "congstar",
            "preis": ab,
            "vodafone": round(ab - delta, 2),
            "band": band,
            "band_label": band.upper(),
        }
        if delta is not None and delta < 0
        else None
    )
    return {
        "schluessel": schluessel,
        "titel": schluessel.upper(),
        "tco_ab": ab,
        "tco_delta": delta,
        "tco_delta_prozent": prozent,
        "tco_anbieter": "congstar",
        "tco_band": band,
        "tco_vodafone_teurer": teurer,
    }


def test_mit_tarif_nimmt_nur_deutlich_teurere_vodafone_bündel():
    """D1 (14.10.2026): Basis ist der Wettbewerberpreis. "b" liegt mit
    1.100 gegen 1.000 genau 10 % darüber und zählt; "f" mit 1.090 nicht."""
    modelle = [
        _modell("a", 900.0, -300.0),
        _modell("b", 1000.0, -100.0),
        _modell("c", 1000.0, 120.0),
        _modell("d", 800.0, -400.0),
        _modell("e", 800.0, None),
        _modell("f", 1000.0, -90.0),
    ]
    zeilen = gt.mit_tarif(modelle)
    assert [z["id"] for z in zeilen] == ["d", "a", "b"]
    assert zeilen[0]["vodafone"] == 1200.0
    assert zeilen[0]["abstand"] == 400.0
    assert zeilen[0]["prozent"] == 50.0
    assert zeilen[1]["vodafone"] - zeilen[1]["preis"] == zeilen[1]["abstand"]


def test_mit_tarif_grenze_genau_zehn_prozent_zaehlt():
    assert [z["id"] for z in gt.mit_tarif([_modell("x", 1000.0, -100.0)])] == ["x"]


def test_d1_basis_ist_der_wettbewerberpreis():
    """Galaxy S25 128: 9,3 % gemessen an Vodafone, 10,2 % am Wettbewerber."""
    assert gt.prozent(1100.0, 1000.0) == 10.0
    zeilen = gt.einzelgeraet(_geraete_d1())
    assert [(z["id"], z["prozent"]) for z in zeilen] == [("s25", 10.2)]


def _geraete_d1():
    return [_geraet("s25", [("Vodafone", 799.9), ("o2", 725.9)])]


def _geraet(gid, preise):
    return {
        "id": gid,
        "label": gid,
        "aktuell": [
            {"anbieter": a, "eigen": a == "Vodafone", "preis": p} for a, p in preise
        ],
    }


def test_einzelgeraet_vergleicht_den_günstigsten_mit_vodafone():
    geraete = [
        _geraet("pixel", [("Vodafone", 549.9), ("congstar", 397.0), ("o2", 541.0)]),
        _geraet("iphone", [("Vodafone", 1000.0), ("o2", 950.0)]),
        _geraet("ohne-vf", [("o2", 300.0), ("congstar", 200.0)]),
    ]
    zeilen = gt.einzelgeraet(geraete)
    assert [z["id"] for z in zeilen] == ["pixel"]
    assert zeilen[0]["anbieter"] == "congstar"
    assert zeilen[0]["abstand"] == 152.9
    assert zeilen[0]["prozent"] == 38.5


def test_listen_liest_katalog_und_verlauf():
    ansicht = {
        "katalog_modelle": [_modell("a", 900.0, -300.0)],
        "verlauf": {"geraete": [_geraet("p", [("Vodafone", 100.0), ("o2", 50.0)])]},
    }
    listen = gt.listen(ansicht)
    assert len(listen["tarif"]) == 1 and len(listen["geraet"]) == 1
    assert gt.listen({}) == {"tarif": [], "geraet": [], "schwelle": 10.0}


def test_seite_zeigt_die_zahl_und_die_zeilen_aus_den_preisdaten(tmp_path):
    import json

    import test_geraete_seite
    from bs4 import BeautifulSoup

    site = test_geraete_seite._baue(tmp_path)
    s = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    geraete = json.loads(s.select_one("#gr-verlaufdaten").get_text())
    erwartet = 0
    for g in geraete:
        vf = [p["preis"] for p in g.get("aktuell") or [] if p.get("eigen")]
        andere = [p["preis"] for p in g.get("aktuell") or [] if not p.get("eigen")]
        if vf and andere and gt.prozent(vf[0], min(andere)) >= gt.SCHWELLE_PROZENT:
            erwartet += 1
    zahl = s.select_one(".gx-held .gx-art--geraet b")
    assert int(zahl.get_text()) == erwartet
    assert len(s.select("#teuer .gx-art--geraet a.gx-vsprung")) == erwartet
    tarif = int(s.select_one(".gx-held .gx-art--tarif b").get_text())
    assert len(s.select("#teuer .gx-art--tarif a.gr-sprung")) == tarif
    assert [b.get_text() for b in s.select(".gr-reiter button:not([hidden])")] == [
        "Mit Tarif",
        "Einzelgerät",
    ]


def test_seite_zeigt_acht_zeilen_und_den_rest_hinter_einem_klick(tmp_path, monkeypatch):
    import test_geraete_seite
    from bs4 import BeautifulSoup

    zeilen = [
        {
            "id": f"g{i}",
            "titel": f"Gerät {i}",
            "anbieter": "o2",
            "klasse": "o2",
            "preis": 500.0,
            "vodafone": 600.0 + i,
            "abstand": 100.0 + i,
            "prozent": 16.7,
        }
        for i in range(11)
    ]
    monkeypatch.setattr(
        gt, "listen", lambda g: {"tarif": [], "geraet": zeilen, "schwelle": 10.0}
    )
    site = test_geraete_seite._baue(tmp_path)
    s = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    assert s.select_one(".gx-held .gx-art--geraet b").get_text() == "11"
    teil = s.select_one("#teuer > div.gx-art--geraet")
    assert len(teil.select(":scope > ol > li")) == 8
    assert teil.select_one("details.gx-mehr summary").get_text() == "Alle 11 zeigen"
    assert len(teil.select("details.gx-mehr li")) == 3
    assert s.select_one(".gx-held .gx-art--tarif b").get_text() == "0"
    assert s.select_one("#teuer > div.gx-art--tarif .gx-leer") is not None


def _karte_m(anbieter, band, gesamt):
    """Eine Bündelkarte der Standardansicht (24 Raten) im Aufbau der Seite."""
    return {
        "anbieter": anbieter,
        "eigen": anbieter == "Vodafone",
        "band": band,
        "gesamt": gesamt,
        "vergleichbar": True,
        "belastbar": True,
        "frisch": True,
        "zaehlt": True,
        "naeherung": False,
        "raten_laufzeit": 24,
        "leitzahl_monate": 24,
        "quelle_url": f"https://beispiel.test/{anbieter}?tarif={band}",
    }


def _modell_m(schluessel, karten):
    """Das Modell wie die Seite es führt: Wettbewerber tragen `delta` gegen
    Vodafone im selben Band (so rechnet die Tarifaufbereitung)."""
    eigen = {k["band"]: k["gesamt"] for k in karten if k["eigen"]}
    return {
        "id": schluessel,
        "karten": [
            k
            if k["eigen"]
            else {**k, "delta": {"betrag": round(k["gesamt"] - eigen[k["band"]], 2)}}
            for k in karten
        ],
    }


IPHONE17 = _modell_m(
    "apple-iphone-17-256",
    [
        _karte_m("Vodafone", "m", 1797.4),
        _karte_m("Vodafone", "l", 1947.4),
        _karte_m("congstar", "m", 1360.0),
        _karte_m("congstar", "l", 1336.0),
    ],
)
"""iPhone 17 256 GB (Livestand 03.11.2026): Vodafone M 1.797,40 (Diagramm),
L 1.947,40; congstar M 1.360,00, L 1.336,00."""


def _zeile_aus(modell):
    from telco_radar.report import geraete_delta_wort, geraete_view

    spalte = geraete_delta_wort.ergaenze(geraete_view._tco_spalte(modell), modell)
    (z,) = gt.mit_tarif([{"schluessel": modell["id"], "titel": "X", **spalte}])
    return z


def test_block_und_diagramm_nennen_denselben_vodafone_betrag():
    """Punkt 1: der Block „Über 10 % teurer“ rechnet auf Tarif M, 24 Monate wie
    das Diagramm „Preispositionierung“ - Vodafone 1.797,40 statt 1.947,40 (L)."""
    from telco_radar.report import geraete_preisposition_preise as pre

    karten = pre.preise_je_anbieter(IPHONE17)
    assert karten["Vodafone"]["gesamt"] == 1797.4
    z = _zeile_aus(IPHONE17)
    assert z["vodafone"] == karten["Vodafone"]["gesamt"] == 1797.4
    assert z["preis"] == karten["congstar"]["gesamt"] == 1360.0
    assert (z["abstand"], z["prozent"], z["band"]) == (437.4, 32.2, "m")


def test_gegenprobe_liegt_nur_das_band_l_ueber_der_schwelle_fehlt_die_zeile():
    """Gegenprobe: in L ist Vodafone 611,40 teurer, in M nur 3,3 % - dann steht
    das Modell nicht im Block (früher stand es mit dem L-Betrag darin)."""
    modell = _modell_m(
        "apple-iphone-17-256",
        [
            _karte_m("Vodafone", "m", 1380.0),
            _karte_m("Vodafone", "l", 1947.4),
            _karte_m("congstar", "m", 1336.0),
            _karte_m("congstar", "l", 1336.0),
        ],
    )
    from telco_radar.report import geraete_view

    spalte = geraete_view._tco_spalte(modell)
    assert gt.mit_tarif([{"schluessel": "x", "titel": "X", **spalte}]) == []


def test_ohne_geprueften_m_preis_steht_keine_zeile():
    """Ein fehlender Vodafone-Preis in M ist eine Lücke, kein Vergleich."""
    modell = _modell_m(
        "x", [_karte_m("Vodafone", "l", 1947.4), _karte_m("congstar", "l", 1000.0)]
    )
    from telco_radar.report import geraete_view

    spalte = geraete_view._tco_spalte(modell)
    assert gt.mit_tarif([{"schluessel": "x", "titel": "X", **spalte}]) == []
