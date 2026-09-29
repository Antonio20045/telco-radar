"""Kostenvergleich der Geräteseite (`report/geraete_kosten.py`).

Die Rangliste wählt je Anbieter die günstigste Karte einer Auswahl und
sortiert; gerechnet wird in `tco_model`. Die Tests halten die Auswahl an
kleinen, selbst gebauten Karten fest und die Zahlen der Seite am echten
Bestand gegen `tco_24()`.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from telco_radar.report import geraete_kosten as gk
from telco_radar.tco_model import Buendel, tco_24

WURZEL = pathlib.Path(__file__).resolve().parents[1]
ZUSTAND = WURZEL / "data" / "state"

STUFEN = [{"key": "xs", "label": "XS", "bereich": "15 GB"},
          {"key": "s", "label": "S", "bereich": "30 GB"},
          {"key": "xl", "label": "XL", "bereich": ""}]


def _karte(anbieter, gesamt, band="s", raten=24, monate=24, **extra):
    k = {"anbieter": anbieter, "sku_id": f"sku-{anbieter}", "band": band,
         "band_gb_text": "30 GB", "tarif": f"{anbieter} Tarif",
         "raten_laufzeit": raten, "leitzahl_monate": monate,
         "gesamt": gesamt, "belastbar": True, "vergleichbar": True,
         "naeherung": False, "frisch": True, "zuzahlung": 1.0,
         "rate": 40.0, "monatlich": 20.0, "buendel_monatlich": None,
         "zerlegung": [{"name": "Tarif über 24 Monate", "betrag": 480.0,
                        "offen": False}],
         "quelle_url": f"https://example.com/{anbieter}",
         "abgerufen_am": "2026-09-01"}
    k.update(extra)
    return k


def _tco(*modelle):
    return {"baender_katalog": STUFEN, "modelle": list(modelle)}


def _modell(mid, name, speicher, karten, hersteller="Apple"):
    return {"id": mid, "name": name, "speicher": speicher,
            "hersteller": hersteller, "karten": karten}


def _daten(karten, **modell):
    return gk.aufbereiten(_tco(_modell("apple-iphone-18-pro-256",
                                       "iPhone 18 Pro 256 GB", 256, karten,
                                       **modell)))


def _zeilen(r):
    return [z for g in r["gruppen"] for z in g["zeilen"]]


def test_guenstigste_zuerst_mit_abstand_und_luecken():
    d = _daten([_karte("o2", 1900.0), _karte("congstar", 1700.0),
                _karte("Vodafone", 2000.0)])
    r = gk.rangliste(d, "apple-iphone-18-pro-256", "s", "alle")
    zeilen = _zeilen(r)
    assert [z["anbieter"] for z in zeilen] == ["congstar", "o2", "Vodafone"]
    assert zeilen[0]["sieger"] and zeilen[0]["abstand"] == 0.0
    assert zeilen[2]["abstand"] == 300.0
    # Gegenprobe: die Lücken sind benannt, nicht weggelassen und nicht 0.
    assert r["ohne"] == ["Telekom", "1&1"]


def test_je_anbieter_nur_das_guenstigste_angebot():
    d = _daten([_karte("congstar", 1800.0, raten=36),
                _karte("congstar", 1750.0, raten=24),
                _karte("Vodafone", 2000.0)])
    r = gk.rangliste(d, "apple-iphone-18-pro-256", "s", "alle")
    assert _zeilen(r)[0]["angebot"]["gesamt"] == 1750.0
    assert [z["anbieter"] for z in _zeilen(r)].count("congstar") == 1


def test_ratenfilter_laesst_andere_laufzeiten_weg():
    d = _daten([_karte("congstar", 1700.0, raten=36),
                _karte("Vodafone", 2000.0, raten=24)])
    r = gk.rangliste(d, "apple-iphone-18-pro-256", "s", 24)
    assert [z["anbieter"] for z in _zeilen(r)] == ["Vodafone"]
    # congstar fehlt nicht, der Filter blendet es aus: es steht mit seiner
    # Ratenzahl zum Umschalten da, nicht bei den Lücken.
    assert r["anders"] == [{"anbieter": "congstar", "raten": [36]}]
    assert "congstar" not in r["ohne"]
    # Gegenprobe: ohne Filter keine Umschalter.
    assert gk.rangliste(d, "apple-iphone-18-pro-256", "s", "alle")["anders"] == []


def test_ein_einzelnes_angebot_ist_kein_sieger():
    d = _daten([_karte("Vodafone", 2000.0)])
    r = gk.rangliste(d, "apple-iphone-18-pro-256", "s", "alle")
    assert not _zeilen(r)[0]["sieger"] and _zeilen(r)[0]["abstand"] is None


def test_anderer_zeitraum_steht_in_eigener_gruppe_danach():
    d = _daten([_karte("1&1", 1500.0, raten=36, monate=36),
                _karte("congstar", 1700.0), _karte("Vodafone", 2000.0)])
    r = gk.rangliste(d, "apple-iphone-18-pro-256", "s", "alle")
    assert [g["monate"] for g in r["gruppen"]] == [24, 36]
    assert [z["anbieter"] for z in r["gruppen"][0]["zeilen"]] == \
        ["congstar", "Vodafone"]
    eins = r["gruppen"][1]["zeilen"][0]
    assert eins["abstand"] is None and not eins["sieger"]


def test_unbrauchbare_karten_fallen_heraus():
    d = _daten([_karte("congstar", 1700.0),
                _karte("o2", 900.0, vergleichbar=False),
                _karte("Telekom", 800.0, belastbar=False),
                _karte("Vodafone", 700.0, naeherung=True)])
    anbieter = {a["anbieter"] for a in d["angebote"]["apple-iphone-18-pro-256"]}
    assert anbieter == {"congstar"}


def test_unbegrenzter_tarif_ohne_band_faellt_in_die_oberste_stufe():
    d = _daten([_karte("o2", 1900.0, band=None,
                       tarif="O2 Mobile Unlimited M"),
                _karte("Telekom", 2500.0, band=None, tarif="MagentaMobil XL",
                       band_gb_text="unbegrenzt"),
                _karte("congstar", 1500.0, band=None, tarif="Allnet Flat",
                       band_gb_text="")])
    stufen = {a["anbieter"]: a["stufe"]
              for a in d["angebote"]["apple-iphone-18-pro-256"]}
    assert stufen == {"o2": "xl", "Telekom": "xl"}
    # Der Chip der obersten Stufe rät kein Volumen: die Leiter kennt es
    # (noch) nicht, also steht dort nichts (Clean Code 3).
    assert d["stufen"][-1]["gb"] == ""


def test_start_ist_die_stufe_mit_den_meisten_anbietern():
    d = _daten([_karte("Vodafone", 2000.0, band="s"),
                _karte("Vodafone", 1900.0, band="xs"),
                _karte("congstar", 1700.0, band="xs")])
    assert d["start"] == {"familie": "apple-iphone-18-pro",
                          "modell": "apple-iphone-18-pro-256",
                          "stufe": "xs", "raten": "alle"}


def test_familien_und_speicher():
    tco = _tco(
        _modell("apple-iphone-18-pro-512", "iPhone 18 Pro 512 GB", 512,
                [_karte("congstar", 1900.0)]),
        _modell("apple-iphone-18-pro-256", "iPhone 18 Pro 256 GB", 256,
                [_karte("congstar", 1700.0)]),
        _modell("apple-iphone-18-pro-1024", "iPhone 18 Pro 1024 GB", 1024,
                [_karte("congstar", 2100.0)]),
        _modell("apple-iphone-17-256", "iPhone 17 256 GB", 256,
                [_karte("congstar", 1100.0)]),
        _modell("apple-iphone-16-128", "iPhone 16 128 GB", 128, []))
    d = gk.aufbereiten(tco)
    assert [f["name"] for f in d["geraete"]] == ["iPhone 18 Pro", "iPhone 17"]
    assert [s["text"] for s in d["geraete"][0]["speicher"]] == \
        ["256 GB", "512 GB", "1 TB"]


def test_geraete_folge_aktuelle_flaggschiffe_zuerst():
    from types import SimpleNamespace as NS
    namen = ["Galaxy S25", "Galaxy Z Fold 7", "Galaxy S26 Ultra", "Galaxy A57",
             "Galaxy Z Fold8", "Galaxy S26", "iPhone Air", "iPhone 18 Pro",
             "iPhone 17", "iPhone 17 Pro"]
    info = {"Galaxy S25": (25, "premium"), "Galaxy Z Fold 7": (7, "flagship"),
            "Galaxy S26 Ultra": (26, "flagship"), "Galaxy A57": (57, "mid"),
            "Galaxy Z Fold8": (8, "flagship"), "Galaxy S26": (26, "premium"),
            "iPhone Air": (17, "flagship"), "iPhone 18 Pro": (18, ""),
            "iPhone 17": (17, "premium"), "iPhone 17 Pro": (17, "flagship")}
    fid = {n: n.lower().replace(" ", "-") for n in namen}
    katalog = NS(geraete=[NS(device_id=fid[n], generation=g, segment=s)
                          for n, (g, s) in info.items()])
    familien = [{"id": fid[n], "name": n,
                 "hersteller": "Apple" if n.startswith("iPhone") else "Samsung"}
                for n in namen]
    folge = [f["name"] for f in gk._geraete_folge(
        familien, ["Apple", "Samsung"], gk._katalog_info(katalog))]
    assert folge == [
        "iPhone 18 Pro", "iPhone Air", "iPhone 17 Pro", "iPhone 17",
        "Galaxy S26 Ultra", "Galaxy Z Fold8", "Galaxy S26", "Galaxy A57",
        "Galaxy S25", "Galaxy Z Fold 7"]
    # Gegenprobe: ohne Katalog zählt die Zahl im Namen, das A57 (57) wäre
    # sonst das "neueste" Samsung - die Baureihe hält es auseinander.
    ohne = [f["name"] for f in gk._geraete_folge(familien, ["Apple", "Samsung"], {})]
    assert ohne.index("Galaxy S26 Ultra") < ohne.index("Galaxy S25")


def test_groesserer_zusatz_steht_vorn():
    assert sorted(["Pixel 11 Pro", "Pixel 11 Pro XL", "Pixel 11"],
                  key=gk._Absteigend) == ["Pixel 11 Pro XL", "Pixel 11 Pro",
                                          "Pixel 11"]


def test_ansicht_graut_stufen_und_raten_ohne_angebot_aus():
    d = _daten([_karte("congstar", 1700.0, band="s", raten=24)])
    a = gk.ansicht(d, d["start"])
    stufe = {c["wert"]: c for c in
             next(r for r in a["reihen"] if r["name"] == "stufe")["chips"]}
    assert stufe["s"]["an"] and not stufe["s"]["aus"]
    assert stufe["xs"]["aus"] and stufe["xl"]["aus"]
    raten = {c["wert"]: c for c in
             next(r for r in a["reihen"] if r["name"] == "raten")["chips"]}
    assert not raten[24]["aus"] and raten[36]["aus"] and not raten["alle"]["aus"]


def test_seite_ohne_daten():
    s = gk.seite({})
    assert s["hat_daten"] is False and s["ansicht"] is None


def test_json_bricht_das_script_nicht_auf():
    d = gk.seite(_tco(_modell("apple-iphone-18-pro-256", "iPhone 18 Pro 256 GB",
                              256, [_karte("congstar", 1700.0,
                                           tarif="</script><b>")])))
    assert "</script>" not in d["json"]
    assert json.loads(d["json"])["angebote"]


# --------------------------------------------------------------------------
# Echter Bestand: jede Zahl der Seite ist die tco_24() eines Bündels
# --------------------------------------------------------------------------

BESTAND_DA = all((ZUSTAND / n).exists() for n in
                 ("geraete_tco.json", "geraete_db.json", "tarife.jsonl"))


def _buendel(satz):
    return Buendel(
        sku_id=satz.get("sku_id") or "", anbieter=satz.get("anbieter") or "?",
        tarif_name=satz.get("tarif_name") or "",
        tarif_id=satz.get("tarif_id") or "",
        tarif_monatlich=satz.get("tarif_monatlich"),
        tarif_bindung_monate=satz.get("tarif_bindung_monate"),
        buendel_monatlich=satz.get("buendel_monatlich"),
        geraet_zuzahlung=satz.get("geraet_zuzahlung"),
        geraet_monatsrate=satz.get("geraet_monatsrate"),
        laufzeit_monate=int(satz.get("laufzeit_monate") or 24),
        anschlusspreis=satz.get("anschlusspreis"),
        zustand=satz.get("zustand") or "",
        quelle_url=satz.get("quelle_url") or "",
        abgerufen_am=satz.get("abgerufen_am") or "")


@pytest.fixture(scope="module")
def echte_seite():
    if not BESTAND_DA:
        pytest.skip("kein ausgelieferter Bestand")
    from telco_radar.geraete_config import lade_katalog, lade_quellen
    from telco_radar.report import geraete_view
    g = geraete_view.aufbereiten(ZUSTAND, lade_quellen(WURZEL),
                                 lade_katalog(WURZEL))
    return gk.seite(g["tco"])


def test_jede_summe_ist_die_tco_eines_buendels_im_bestand(echte_seite):
    store = json.loads((ZUSTAND / "geraete_tco.json").read_text("utf-8"))
    je_schluessel: dict = {}
    for satz in store["buendel"]:
        schluessel = (satz["sku_id"], satz["anbieter"],
                      satz.get("laufzeit_monate"))
        je_schluessel.setdefault(schluessel, []).append(satz)
    geprueft = 0
    for angebote in echte_seite["angebote"].values():
        for a in angebote:
            saetze = je_schluessel.get((a["sku"], a["anbieter"], a["raten"]))
            assert saetze, a
            summen = {tco_24(_buendel(s)).gesamt for s in saetze}
            assert a["gesamt"] in summen, (a, summen)
            assert round(sum(p["betrag"] for p in a["posten"]), 2) == a["gesamt"]
            geprueft += 1
    # Gegenprobe: der Lookup läuft nicht ins Leere.
    assert geprueft > 50


def test_startansicht_am_echten_bestand_hat_mehrere_anbieter(echte_seite):
    erste = echte_seite["ansicht"]["gruppen"][0]
    assert erste["monate"] == gk.HORIZONT and len(erste["zeilen"]) >= 2
    assert erste["zeilen"][0]["sieger"]
    assert erste["zeilen"][0]["angebot"]["gesamt"] == min(
        z["angebot"]["gesamt"] for z in erste["zeilen"])


def test_rechenweg_nennt_faktoren_nur_wenn_sie_aufgehen(echte_seite):
    geprueft = 0
    for angebote in echte_seite["angebote"].values():
        for a in angebote:
            for p in a["posten"]:
                if p["mal"]:
                    anzahl, _, betrag = p["mal"].partition(" × ")
                    wert = float(betrag.replace(" €", "").replace(".", "")
                                 .replace(",", "."))
                    assert round(int(anzahl) * wert, 2) == p["betrag"], p
                    geprueft += 1
    assert geprueft > 50


def test_unbegrenzter_tarif_ohne_volumen_nennt_unbegrenzt():
    karte = _karte("o2", 1758.76, band=None)
    karte["tarif"] = "O2 Mobile Unlimited M Plus"
    karte["band_gb_text"] = ""
    d = _daten([karte, _karte("congstar", 1700.0)])
    oben = d["stufen"][-1]["key"]
    a = [x for x in d["angebote"]["apple-iphone-18-pro-256"] if x["anbieter"] == "o2"]
    assert [(x["stufe"], x["gb"]) for x in a] == [(oben, "unbegrenzt")]
    # Gegenprobe: ein Tarif mit Volumen behält seine Zahl.
    c = [x for x in d["angebote"]["apple-iphone-18-pro-256"] if x["anbieter"] == "congstar"]
    assert c[0]["gb"] != "unbegrenzt"


def test_veralteter_preis_verdraengt_keinen_frischen():
    d = _daten([_karte("o2", 1500.0, frisch=False, abgerufen_am="2026-09-08"),
                _karte("congstar", 1700.0), _karte("Vodafone", 2000.0)])
    zeilen = _zeilen(gk.rangliste(d, "apple-iphone-18-pro-256", "s", "alle"))
    assert [z["anbieter"] for z in zeilen] == ["congstar", "Vodafone", "o2"]
    assert zeilen[0]["sieger"] and zeilen[1]["abstand"] == 300.0
    # Der alte Preis steht dabei, aber ohne Abstand und mit Stand-Marke.
    assert zeilen[2]["abstand"] is None and not zeilen[2]["sieger"]
    assert zeilen[2]["angebot"]["alt"] == "Stand 08.09."
    # Gegenprobe: frisch gerechnet wäre o2 die günstigste.
    d2 = _daten([_karte("o2", 1500.0), _karte("congstar", 1700.0)])
    assert _zeilen(gk.rangliste(d2, "apple-iphone-18-pro-256", "s",
                                "alle"))[0]["anbieter"] == "o2"


def test_frisches_angebot_schlaegt_billigeres_altes_desselben_anbieters():
    d = _daten([_karte("congstar", 1500.0, raten=36, frisch=False),
                _karte("congstar", 1700.0, raten=24)])
    a = _zeilen(gk.rangliste(d, "apple-iphone-18-pro-256", "s", "alle"))[0]
    assert a["angebot"]["gesamt"] == 1700.0 and a["angebot"]["alt"] == ""


def test_veraltet_ohne_datum_heisst_stand_unbekannt():
    d = _daten([_karte("o2", 1500.0, frisch=False, abgerufen_am=None)])
    a = _zeilen(gk.rangliste(d, "apple-iphone-18-pro-256", "s", "alle"))[0]
    assert a["angebot"]["alt"] == "Stand unbekannt"


def test_angebot_ohne_raten_steht_unter_filter_zum_umschalten():
    d = _daten([_karte("congstar", 1700.0, raten=None),
                _karte("Vodafone", 2000.0, raten=24)])
    r = gk.rangliste(d, "apple-iphone-18-pro-256", "s", 24)
    assert r["anders"] == [{"anbieter": "congstar", "raten": [None]}]
    assert "congstar" not in r["ohne"]


def test_unbekannter_anbieter_bleibt_unter_filter_sichtbar():
    d = _daten([_karte("Aldi Talk", 1700.0, raten=36),
                _karte("Vodafone", 2000.0, raten=24)])
    r = gk.rangliste(d, "apple-iphone-18-pro-256", "s", 24)
    assert r["anders"] == [{"anbieter": "Aldi Talk", "raten": [36]}]


def test_nur_web_adressen_werden_verlinkt():
    d = _daten([_karte("o2", 1500.0, quelle_url="javascript:alert(1)"),
                _karte("congstar", 1700.0)])
    zeilen = _zeilen(gk.rangliste(d, "apple-iphone-18-pro-256", "s", "alle"))
    urls = {z["anbieter"]: z["angebot"]["url"] for z in zeilen}
    assert not urls["o2"]
    assert urls["congstar"] == "https://example.com/congstar"


def test_json_maskiert_spitze_klammern():
    d = gk.seite(_tco(_modell("apple-iphone-18-pro-256", "iPhone 18 Pro 256 GB",
                              256, [_karte("congstar", 1700.0,
                                           tarif="<!--<script>")])))
    assert "<" not in d["json"]
    assert "<!--<script>" in json.dumps(json.loads(d["json"]), ensure_ascii=False)
