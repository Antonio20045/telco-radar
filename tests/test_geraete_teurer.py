"""Die Listen "Vodafone über 10 % teurer" der Geräteseite (10.10.2026)."""

from __future__ import annotations

from telco_radar.report import geraete_teurer as gt


def _modell(schluessel, ab, delta, prozent=None, band="m"):
    """Eine Katalogzeile; `delta` ist Wettbewerber minus Vodafone im Band."""
    teurer = (
        [
            {
                "anbieter": "congstar",
                "preis": ab,
                "vodafone": round(ab - delta, 2),
                "band": band,
                "band_label": band.upper(),
            }
        ]
        if delta is not None and delta < 0
        else []
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


def test_d3_ein_anderes_band_reicht():
    """Pixel 11 Pro Fold 256: das günstigste Angebot liegt in XS knapp unter
    Vodafone, in XL ist o2 deutlich günstiger - das Modell steht in der Liste,
    mit dem Band, in dem Vodafone teurer ist."""
    m = _modell("fold", 2500.0, -50.0, band="xs")
    m["tco_vodafone_teurer"].append(
        {
            "anbieter": "o2",
            "preis": 3120.0,
            "vodafone": 3788.88,
            "band": "xl",
            "band_label": "XL",
        }
    )
    (z,) = gt.mit_tarif([m])
    assert (z["anbieter"], z["band"], z["abstand"]) == ("o2", "xl", 668.88)
    assert z["prozent"] == 21.4


def test_d3_das_band_des_guenstigsten_angebots_bleibt_vorn():
    """Liegt schon das Band des günstigsten Angebots über der Schwelle, zeigt
    die Liste dieses Band, auch wenn ein anderes Band höher liegt."""
    m = _modell("air", 1192.0, -427.8, band="xs")
    m["tco_vodafone_teurer"].append(
        {
            "anbieter": "o2",
            "preis": 1470.76,
            "vodafone": 2211.64,
            "band": "xl",
            "band_label": "XL",
        }
    )
    (z,) = gt.mit_tarif([m])
    assert (z["band"], z["preis"]) == ("xs", 1192.0)


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
