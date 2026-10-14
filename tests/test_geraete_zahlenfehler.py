"""Zahlenfehler der Geräteseite F1 bis F9 (Übergabe Antonio, 14.10.2026).

Jeder Test war gegen den Stand `ec44a26` rot. Die Daten sind klein und
erfunden; der Bezugstag ist fest, nie das heutige Datum.
"""

from __future__ import annotations

import json
import re

from telco_radar.report import geraete_zeitreihe

HEUTE = "2026-10-14"


def _buendel(bid, sku, rate, **extra):
    return {
        "id": bid,
        "sku_id": sku,
        "anbieter": "congstar",
        "tarif_name": "Allnet Flat XS",
        "tarif_id": "tarif-x",
        "tarif_id_guete": "hoch",
        "tarif_monatlich": 20.0,
        "geraet_zuzahlung": 0.0,
        "geraet_monatsrate": rate,
        "laufzeit_monate": 24,
        "anschlusspreis": 0.0,
        "zustand": "neu",
        "quelle_url": "https://example.de/congstar",
        "abgerufen_am": HEUTE,
        **extra,
    }


def _zeile(bid, datum, rate):
    return {
        "id": bid,
        "datum": datum,
        "tarif_id": "tarif-x",
        "tarif_monatlich": 20.0,
        "geraet_zuzahlung": 0.0,
        "geraet_monatsrate": rate,
        "laufzeit_monate": 24,
        "anschlusspreis": 0.0,
        "gesamt": 24 * 20.0 + 24 * rate,
        "quelle_url": "https://example.de/congstar",
        "abgerufen_am": datum,
    }


def _karte(sku, vergleichbar=True, gesamt=1200.0):
    return {
        "anbieter": "congstar",
        "gesamt": gesamt,
        "schnitt_monat": round(gesamt / 24, 2),
        "leitzahl_monate": 24,
        "raten_laufzeit": 24,
        "tarif": "Allnet Flat XS",
        "band": "xs",
        "band_gb_text": "15 GB",
        "vergleichbar": vergleichbar,
        "belastbar": True,
        "frisch": True,
        "sku_id": sku,
        "naeherung": False,
        "quelle_url": "https://example.de/congstar",
        "abgerufen_am": HEUTE,
    }


def _state(tmp_path, buendel, zeilen, karten):
    state = tmp_path / "state"
    state.mkdir()
    (state / "geraete_tco.json").write_text(
        json.dumps({"buendel": buendel}), encoding="utf-8"
    )
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8"
    )
    tco = {
        "modelle": [
            {
                "id": "modell-x",
                "titel": "Testgerät 256 GB",
                "hersteller": "Test",
                "speicher": 256,
                "karten": karten,
            }
        ],
        "band_je_tarif": {"tarif-x": "xs"},
        "baender_katalog": [{"key": "xs", "label": "XS"}],
        "historie_lage": {},
    }
    return state, tco


def _paar(a, laufzeit=24):
    return next(
        p
        for p in a["paare"]
        if (p["modell"], p["band"], p["laufzeit"]) == ("modell-x", "xs", laufzeit)
    )


def _f1(tmp_path):
    neu = "buendel--congstar--sku-neu--tarif-x--24"
    alt = "buendel--congstar--sku-neu-refurbished--tarif-x--24"
    return _state(
        tmp_path,
        [
            _buendel(neu, "sku-neu", 40.0),
            _buendel(alt, "sku-neu-refurbished", 20.0, zustand="refurbished"),
        ],
        [
            _zeile(neu, "2026-09-29", 40.0),
            _zeile(alt, "2026-09-29", 20.0),
            _zeile(neu, "2026-10-14", 40.0),
            _zeile(alt, "2026-10-14", 10.0),
        ],
        [_karte("sku-neu", gesamt=1440.0), _karte("sku-neu-refurbished", False, 720.0)],
    )


def test_f1_refurbished_punkt_steht_nicht_in_der_zeitreihe(tmp_path):
    state, tco = _f1(tmp_path)
    mess = geraete_zeitreihe._messungen(state, tco, heute=HEUTE)
    tage = mess[("modell-x", "xs", 24)]["congstar"]
    assert {t: m["wert"] for t, m in tage.items()} == {
        "2026-09-29": 1440.0,
        "2026-10-14": 1440.0,
    }


def test_f1_refurbished_punkt_fehlt_in_kurve_legende_und_kachel(tmp_path):
    state, tco = _f1(tmp_path)
    a = geraete_zeitreihe.aufbereiten(state, tco, heute=HEUTE)
    paar = _paar(a)
    assert "720" not in paar["legende_html"] and "960" not in paar["legende_html"]
    assert "zuletzt 1.440" in paar["legende_html"]
    for svg in (paar["svg_breit"], paar["svg_schmal"]):
        assert "960" not in svg and "720" not in svg
    kachel = a["kacheln"][0]["baender"]["xs"][24]
    assert (kachel["delta_text"] or "").startswith("±0"), kachel["delta_text"]


def _f3(tmp_path):
    echt = "buendel--congstar--sku-a--tarif-x--24"
    geschaetzt = "buendel--congstar--sku-b--tarif-x--24"
    return _state(
        tmp_path,
        [
            _buendel(echt, "sku-a", 40.0),
            _buendel(geschaetzt, "sku-b", 30.0, herleitung="aus Tarifliste geschätzt"),
        ],
        [
            _zeile(echt, "2026-09-29", 45.0),
            _zeile(geschaetzt, "2026-09-29", 30.0),
            _zeile(echt, "2026-10-14", 40.0),
            _zeile(geschaetzt, "2026-10-14", 30.0),
        ],
        [_karte("sku-a", gesamt=1440.0), _karte("sku-b", gesamt=1200.0)],
    )


def test_f3_tag_bleibt_mit_dem_zaehlenden_wert(tmp_path):
    state, tco = _f3(tmp_path)
    mess = geraete_zeitreihe._messungen(state, tco, heute=HEUTE)
    tage = mess[("modell-x", "xs", 24)]["congstar"]
    assert {t: m["wert"] for t, m in tage.items()} == {
        "2026-09-29": 1560.0,
        "2026-10-14": 1440.0,
    }
    assert all(m["zaehlt"] for m in tage.values())


def test_f3_kurve_zeigt_keine_schaetzung_und_kachel_nennt_die_bewegung(tmp_path):
    state, tco = _f3(tmp_path)
    a = geraete_zeitreihe.aufbereiten(state, tco, heute=HEUTE)
    paar = _paar(a)
    assert "1.200" not in paar["legende_html"], paar["legende_html"]
    for svg in (paar["svg_breit"], paar["svg_schmal"]):
        assert "1.200" not in svg
    kachel = a["kacheln"][0]["baender"]["xs"][24]
    assert kachel["delta_text"] and re.search(r"120", kachel["delta_text"]), kachel


def test_f3_nur_schaetzungen_nennen_den_grund_statt_leerer_messreihe(tmp_path):
    geschaetzt = "buendel--congstar--sku-b--tarif-x--24"
    state, tco = _state(
        tmp_path,
        [_buendel(geschaetzt, "sku-b", 30.0, herleitung="geschätzt")],
        [_zeile(geschaetzt, "2026-09-29", 30.0), _zeile(geschaetzt, HEUTE, 30.0)],
        [_karte("sku-b", gesamt=1200.0)],
    )
    a = geraete_zeitreihe.aufbereiten(state, tco, heute=HEUTE)
    paar = _paar(a)
    assert paar["punkte"] == 0
    assert "nicht im Vergleich" in (paar["leer_text"] or ""), paar["leer_text"]


class _Historie:
    def reihe(self, listung_id):
        return []


def _listung(kennung, anbieter, preis, tag):
    return {
        "id": kennung,
        "anbieter": anbieter,
        "anbieter_typ": "handel",
        "status": "aktiv",
        "device_id": "samsung-galaxy-s26",
        "speicher_gb": 256,
        "zustand": "neu",
        "preis_ohne_vertrag": preis,
        "last_verified": tag,
        "abgerufen_am": tag,
        "quelle_url": f"https://example.de/{kennung}",
        "farbe_normalisiert": "schwarz",
    }


_F2 = [
    _listung("vf", "Vodafone", 899.9, HEUTE),
    _listung("cg", "congstar", 793.0, HEUTE),
    _listung("mm", "Medimax", 699.0, "2026-09-29"),
]


def test_f2_alter_preis_steht_nicht_in_aktuell_und_nicht_in_ueber_10_prozent():
    from telco_radar.report import geraete_teurer, geraete_verlauf

    geraete = geraete_verlauf.geraete_mit_verlauf(_F2, _Historie(), None, HEUTE)
    (g,) = geraete
    assert [a["anbieter"] for a in g["aktuell"]] == ["congstar", "Vodafone"]
    zeilen = geraete_teurer.einzelgeraet(geraete)
    assert [(z["anbieter"], z["preis"]) for z in zeilen] == [("congstar", 793.0)]
    medimax = next(r for r in g["reihen"] if r["anbieter"] == "Medimax")
    assert medimax["frisch"] is False, "die Kurve bleibt, aber nicht als aktuell"


def test_f2_ohne_vertrag_vergleich_sieht_nur_frische_preise():
    from telco_radar.report import geraete_verlauf

    v = geraete_verlauf.vergleich_frisch(_F2, None, {}, HEUTE)["ohne_vertrag"]
    (zeile,) = v["zeilen"]
    assert zeile["bester"]["anbieter"] == "congstar"
    assert zeile["bester"]["preis"] == 793.0


def test_f9_ein_laden_heisst_im_verlauf_wie_in_der_alarmtabelle():
    from telco_radar.report import geraete_verlauf

    listungen = [
        _listung("vf", "Vodafone", 699.9, HEUTE),
        _listung("md", "mobilcom-debitel", 629.0, HEUTE),
    ]
    laeden = {"mobilcom-debitel": "freenet"}
    (g,) = geraete_verlauf.geraete_mit_verlauf(
        listungen, _Historie(), None, HEUTE, laeden
    )
    assert g["aktuell"][0]["anbieter"] == "freenet"


def _vodafone_12():
    stand = {
        "id": "buendel--vodafone--apple-iphone-16-128gb-blau--mobil-m--12m",
        "sku_id": "apple-iphone-16-128gb-blau",
        "anbieter": "Vodafone",
        "tarif_name": "Mobil M",
        "tarif_id": "vodafone:vodafone-mobil-m-mit-smartphone",
        "tarif_id_guete": "hoch",
        "tarif_monatlich": 27.61,
        "tarif_bindung_monate": None,
        "buendel_monatlich": None,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 70.0,
        "laufzeit_monate": 12,
        "anschlusspreis": 0.0,
        "quelle_url": "https://www.vodafone.de/privat/handys/iphone-16.html",
        "abgerufen_am": HEUTE,
        "zustand": "neu",
        "herleitung": "",
        "tarif_phasen": [
            {"von_monat": 1, "bis_monat": 12, "betrag": 27.61, "beleg": "Monat 1-12"},
            {"von_monat": 13, "bis_monat": 24, "betrag": 30.61, "beleg": "Monat 13-24"},
        ],
        "rechenweise": 2,
    }
    return {"satz": {**stand, "datum": HEUTE}, "stand": stand}


def test_f4_rechenweg_nennt_die_phasen_statt_24_mal_monat_1():
    from telco_radar.report import geraete_rechenweg

    html = geraete_rechenweg._rechung_html("Vodafone", _vodafone_12())
    text = re.sub(r"<[^>]+>", " ", html)
    assert "24 × 27,61 €" not in text, text
    assert "12 × 27,61 € + 12 × 30,61 €" in text, text
    assert "698,64 €" in text


def test_f5_ueber_24_monate_ist_bei_jedem_anbieter_24_mal_der_monatspreis():
    from telco_radar.report import geraete_tco_view
    from telco_radar.tco_model import SimOnlyReferenz

    refs = [
        SimOnlyReferenz(
            anbieter="1&1",
            tarif_name="All-Net-Flat S",
            tarif_id="1und1:s",
            tarif_sim_only_monatlich=14.99,
            anschlusspreis=19.90,
        ),
        SimOnlyReferenz(
            anbieter="Telekom",
            tarif_name="MagentaMobil S",
            tarif_id="telekom:s",
            tarif_sim_only_monatlich=42.95,
        ),
    ]
    zeilen = {z["anbieter"]: z for z in geraete_tco_view._referenztabelle(refs)}
    assert zeilen["1&1"]["tarif_ueber_horizont"] == 359.76
    assert zeilen["Telekom"]["tarif_ueber_horizont"] == 1030.8
    assert zeilen["1&1"]["ueber_horizont"] == 379.66


class _Modell:
    modell = "Galaxy S26 Ultra"


class _Katalog:
    def nach_id(self, gid):
        return _Modell()


class _Verlauf:
    def __init__(self, reihen):
        self._reihen = reihen

    def reihe(self, lid):
        return self._reihen.get(lid, [])

    def alle_punkte(self):
        return [p for r in self._reihen.values() for p in r]


def _bewegung(lid, speicher, von, auf):
    e = {
        "id": lid,
        "anbieter": "congstar",
        "device_id": "samsung-galaxy-s26-ultra",
        "speicher_gb": speicher,
        "quelle_url": f"https://example.de/{lid}",
        "status": "aktiv",
    }
    reihe = [
        {"datum": "2026-09-01", "preis_ohne_vertrag": von},
        {"datum": "2026-10-13", "preis_ohne_vertrag": auf},
    ]
    return e, reihe


def test_f6_eine_bewegung_je_speicher_und_anbieter_deutsch_formatiert():
    from telco_radar.report import geraete_view

    paare = [
        _bewegung("schwarz-256", 256, 965.0, 1219.0),
        _bewegung("blau-256", 256, 965.0, 1219.0),
        _bewegung("grau-256", 256, 975.0, 1219.0),
        _bewegung("schwarz-512", 512, 1175.0, 1419.0),
    ]
    eintraege = [e for e, _ in paare]
    verlauf = _Verlauf({e["id"]: r for e, r in paare})
    auf = geraete_view._auffaellig(eintraege, verlauf, _Katalog(), HEUTE, laeufe=9)
    zeilen = [(b["modell"], b["delta"]) for b in auf["bewegungen"]]
    assert zeilen == [
        ("Galaxy S26 Ultra 256 GB", 254.0),
        ("Galaxy S26 Ultra 512 GB", 244.0),
    ]
    text = " ".join(auf["saetze"])
    assert "1.219,00 €" in text and "1219,00" not in text, text


def test_f6_delta_in_der_tabelle_mit_minuszeichen_und_komma(tmp_path):
    from jinja2 import Environment, FileSystemLoader

    from telco_radar.report import html as html_mod

    env = Environment(
        loader=FileSystemLoader(
            str(html_mod.Path(html_mod.__file__).parent / "templates")
        )
    )
    env.filters.update(
        euro=html_mod._geraete_tco_grafik.euro,
        date_de=lambda s: s,
        domain=lambda s: s,
    )
    makro = env.get_template("_geraete_radar.html.j2").module.wochenkarte
    port = {
        "fenster_tage": 7,
        "auffaellig": {
            "hat_daten": True,
            "saetze": [],
            "bewegungen": [
                {
                    "modell": "Pixel 10 128 GB",
                    "anbieter": "o2",
                    "von": 1199.0,
                    "auf": 909.0,
                    "delta": -290.0,
                    "datum": HEUTE,
                    "url": "",
                }
            ],
        },
    }
    html = str(makro(port))
    assert "−290,00 €" in html and "-290.00" not in html, html


def _gruppe(mid, prozent, gesamt, vf, monate):
    return {
        "id": mid,
        "titel": mid,
        "hersteller": "X",
        "speicher": 256,
        "vodafone": {"gesamt": vf},
        "vodafone_grund": "",
        "rang": prozent,
        "zeilen": [
            {
                "anbieter": "congstar",
                "status": "vergleichbar",
                "prozent": prozent,
                "gesamt": gesamt,
                "vf_gesamt": vf,
                "monate": monate,
                "tarif": "XS",
                "band": "xs",
                "band_label": "XS",
                "quelle_url": "",
                "abgerufen_am": "",
            }
        ],
    }


def test_f8_leitzahl_ist_der_groesste_euro_abstand_mit_seinem_zeitraum():
    from telco_radar.report import geraete_radar

    ml = geraete_radar.modellliste(
        [
            _gruppe("pixel-10a", -45.8, 760.0, 1401.64, 36),
            _gruppe("iphone-air", -30.0, 1812.72, 2589.6, 24),
        ]
    )
    assert ml["spitze"]["id"] == "iphone-air"
    assert ml["spitze"]["monate"] == 24
    assert ml["zeilen"][0]["monate"] == 36


def _vergleich(*paare):
    zeilen = []
    for modell, vf, gegen in paare:
        guenstiger = gegen < vf
        angebot = {"preis": gegen, "laden": "o2", "anbieter": "o2"}
        zeilen.append(
            {
                "device_id": modell,
                "speicher": 256,
                "modell": modell,
                "vodafone": {"preis": vf},
                "guenstiger": [angebot] if guenstiger else [],
                "teurer": [] if guenstiger else [angebot],
                "differenz": round(vf - gegen, 2) if guenstiger else None,
                "prozent": None,
            }
        )
    return {"zeilen": zeilen}


def test_f8_grafik_zeigt_nur_vodafone_teurer_und_bleibt_im_bild():
    from telco_radar.report import geraete_radar

    g = geraete_radar.grafik(
        _vergleich(
            ("a", 1000.0, 700.0),
            ("b", 800.0, 750.0),
            ("c", 1000.0, 1499.1),
        )
    )
    assert [z["device_id"] for z in g["zeilen"]] == ["a", "b"]
    assert (g["n"], g["basis"]) == (2, 3)
    for svg in (g["svg_breit"], g["svg_schmal"]):
        breite = float(re.search(r"viewBox='0 0 (\d+)", svg).group(1))
        for zahl in re.findall(r"[MHL]\s?(-?[\d.]+)", svg):
            assert -1 <= float(zahl) <= breite, (zahl, breite)


def test_f8_skala_haelt_beide_richtungen_im_bild():
    from telco_radar.report import geraete_radar

    zeilen = geraete_radar.grafik_zeilen(
        _vergleich(("a", 1000.0, 700.0), ("c", 1000.0, 1499.1))
    )
    svg = geraete_radar._grafik_svg(zeilen, None, True)
    for zahl in re.findall(r"H(-?[\d.]+)", svg):
        assert float(zahl) <= 1120, zahl


def test_f9_einsundeins_ablose_zaehlt_nicht_zusaetzlich_zu_monat_25_bis_36():
    from telco_radar.analyze.geraete_pruefstatus import geraetepreis
    from telco_radar.tco_model import Buendel

    b = Buendel(
        sku_id="samsung-galaxy-s26-ultra-256gb-schwarz",
        anbieter="1&1",
        tarif_name="All-Net-Flat S",
        tarif_id="1und1:s",
        buendel_monatlich=42.99,
        laufzeit_monate=36,
        geraet_zuzahlung=340.0,
        anschlusspreis=39.90,
    )
    assert geraetepreis(b) == 1587.54


def test_f9_legende_nennt_den_ersten_wert_anfangs():
    from telco_radar.report import geraete_zeitreihe as zr

    html = zr._legende_html({"congstar": [("2026-09-29", 1243.0), (HEUTE, 1117.0)]})
    assert "anfangs 1.243 €" in html and "ab 1.243" not in html, html
