"""Die Auto-Erkennung legt nur Smartphones an (29.09.2026).

o2 führt AirPods, Uhren und Tablets mit Tarif. Die Auto-Erkennung machte
daraus Katalogmodelle, und die Geräteseite bot „AirPods 5“ neben dem
iPhone an. Die Namen unten stehen wörtlich so im Auto-Katalog vom 29.09.
"""
import json

from telco_radar.collect.geraete.autoerkennung import (
    lade_auto_zusaetze, schale)
from telco_radar.geraete_model import Geraet, Katalog

NICHT_SMARTPHONES = [
    "Apple AirPods 5", "Google Pixel Buds Pro 2",
    "Apple Watch Series 12 46 Aluminium", "Apple Watch Ultra 4 Natur",
    "Apple iPad Pro 11 (2025)", "Apple iPad (2025)",
    "Samsung Galaxy Tab S11 Ultra", "Samsung Galaxy Tab A11+"]
SMARTPHONES = ["Apple iPhone 18 Pro Max", "Samsung Galaxy XCover7 Pro EE",
               "Samsung Galaxy Z Fold8", "Google Pixel 11 Pro XL"]


def _katalog():
    return Katalog([Geraet("Apple", "iPhone 17"),
                    Geraet("Samsung", "Galaxy S26"),
                    Geraet("Google", "Pixel 11")])


def test_schale_verwirft_nicht_smartphones():
    assert [n for n in NICHT_SMARTPHONES if schale(n, _katalog())] == []
    # Gegenprobe: Smartphones werden weiter geschält.
    assert all(schale(n, _katalog()) for n in SMARTPHONES)


def test_alte_auto_eintraege_ohne_smartphone_fallen_beim_laden_heraus(
        tmp_path):
    zustand = tmp_path / "data" / "state"
    zustand.mkdir(parents=True)
    (zustand / "geraete_katalog_auto.json").write_text(json.dumps(
        {"geraete": [
            {"hersteller": "Apple", "modell": "AirPods 5",
             "auto": "2026-09-20"},
            {"hersteller": "Apple", "modell": "iPad Pro 11 (2025)",
             "auto": "2026-09-20"},
            {"hersteller": "Apple", "modell": "iPhone 18 Pro",
             "auto": "2026-09-20"}]}), encoding="utf-8")
    katalog = _katalog()
    lade_auto_zusaetze(tmp_path, katalog)
    modelle = {g.modell for g in katalog.geraete}
    assert "iPhone 18 Pro" in modelle
    assert "AirPods 5" not in modelle
    assert "iPad Pro 11 (2025)" not in modelle


def test_geraeteseite_zeigt_keine_airpods_aus_dem_altbestand(tmp_path):
    """Was vor dem Filter in den Bestand kam, fällt auf der Seite heraus."""
    from telco_radar.geraete_config import lade_katalog, lade_quellen
    from telco_radar.report import geraete_view
    from test_geraete_laufzeit_auf_der_seite import (
        HEUTE, SKU, _listung, _zeitreihe_wurzel)

    root, state = _zeitreihe_wurzel(tmp_path, f"buendel--o2--{SKU}--m--24m")
    airpods = "apple-airpods-5-ohne-speicher-ohne-farbe"
    db = json.loads((state / "geraete_db.json").read_text("utf-8"))
    db["listungen"].append(dict(_listung("o2", 139.0, sku=airpods),
                                device_id="apple-airpods-5"))
    (state / "geraete_db.json").write_text(json.dumps(db), encoding="utf-8")
    tco = json.loads((state / "geraete_tco.json").read_text("utf-8"))
    tco["buendel"].append(dict(tco["buendel"][0], sku_id=airpods,
                               id=f"buendel--o2--{airpods}--m--24m"))
    (state / "geraete_tco.json").write_text(json.dumps(tco), encoding="utf-8")

    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)
    text = json.dumps(g, default=str)
    assert "airpods" not in text
    # Gegenprobe: das Smartphone aus demselben Bestand bleibt.
    assert SKU in text
