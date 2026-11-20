"""Tarifwelt-Zuordnung: jedes Modell der Tabelle ist ein Katalogmodell.

Nachmessung 20.11.2026: vier Katalogmodelle mit Tarifwelt-Seite und lieferbarer
Variante standen nicht in `MODELL_SLUGS` (Pixel 9 Pro, Magic7 Pro, Xiaomi 15,
edge 70). Kein Netz.
"""

from __future__ import annotations

import pathlib

import yaml
from bestand_pfad import lese_wurzel
from test_geraete_adapter_tarifwelt import LEITER

from telco_radar.collect.geraete import tarifwelt, tarifwelt_lauf
from telco_radar.collect.geraete.tarifwelt_modelle import MODELL_SLUGS
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import device_id, sku_id
from telco_radar.tco_model import buendel_id

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "geraete"
KATALOG = {
    device_id(g.hersteller, g.modell) for g in lade_katalog(lese_wurzel()).geraete
}
NEU = {
    "google-pixel-9-pro": "pixel-9-pro",
    "honor-magic7-pro": "magic-7-pro",
    "xiaomi-15": "15",
    "motorola-edge-70": "edge-70",
}


def test_jeder_schluessel_ist_die_katalog_id_seines_eintrags():
    for schluessel, eintrag in MODELL_SLUGS.items():
        assert device_id(eintrag[0], eintrag[1]) == schluessel
        assert schluessel in KATALOG, schluessel


def test_nachgemessene_katalogmodelle_stehen_in_der_tabelle():
    for modell, slug in NEU.items():
        assert MODELL_SLUGS[modell][3] == slug, modell


def test_jeder_slug_gehoert_nur_einem_modell():
    slugs = [e[3] for e in MODELL_SLUGS.values()]
    assert len(slugs) == len(set(slugs))


def test_edge_70_steht_nicht_mehr_als_nicht_lieferbare_luecke_gegenprobe():
    wurzel = pathlib.Path(__file__).resolve().parents[1]
    daten = yaml.safe_load(
        (wurzel / "config/geraete_abdeckung.yaml").read_text("utf-8")
    )
    saturn = [
        luecke
        for luecke in daten["belegte_luecken"]
        if str(luecke.get("anbieter", "")).startswith("Saturn/MediaMarkt")
    ]
    assert saturn
    for luecke in saturn:
        assert "motorola-edge-70" not in luecke["modelle"], luecke["anbieter"]
    assert any("samsung-galaxy-a17" in luecke["modelle"] for luecke in saturn)


def test_gleicher_tarifname_im_selben_netz_ueberschreibt_kein_buendel():
    """Die Buendel-ID kommt aus dem Tarifnamen. Die echte Tarifliste des iPhone 17
    (Fixture 08.11.2026) fuehrt bei o2 fuenf Tarife "Mobile Unlimited L Promo"
    und bei Telekom zwei "Allnet Flat 50GB": mit dem rohen Namen teilen sie sich
    je eine ID, das spaetere Buendel wuerde das fruehere ersetzen."""
    text = (FIXTURES / "tarifwelt_mm_tarifliste_iphone17_20261108.json").read_text()
    tarife = tarifwelt_lauf.vergleichbare_tarife(
        tarifwelt.lies_tarifliste(text), LEITER
    )
    sku = sku_id("apple-iphone-17", 256, None)

    def ids(zusaetze: dict[str, str]) -> list[str]:
        return [
            buendel_id(
                sku,
                tarifwelt.anbieter_zeile(t["netz"]),
                (t["name"] or t["tarif_name"]) + zusaetze.get(t["tarif_id"], ""),
                24,
            )
            for t in tarife
        ]

    roh = ids({})
    assert len(set(roh)) < len(roh), "Gegenprobe: ohne Zusatz kollidieren IDs"
    mit = ids(tarifwelt_lauf.namenszusaetze(tarife))
    assert len(mit) == len(tarife) and len(set(mit)) == len(mit)


def test_zusatz_nur_bei_gleichem_namen_und_mit_preis():
    t = [
        {"tarif_id": "a1", "netz": "o2", "name": "Mobile L", "grundgebuehr": 39.99},
        {"tarif_id": "a2", "netz": "o2", "name": "Mobile L", "grundgebuehr": 44.99},
        {"tarif_id": "b1", "netz": "o2", "name": "Mobile M", "grundgebuehr": 29.99},
        {
            "tarif_id": "c1",
            "netz": "freenet - Telekom",
            "name": "Mobile L",
            "grundgebuehr": 9.0,
        },
    ]
    z = tarifwelt_lauf.namenszusaetze(t)
    assert z == {"a1": " (39,99 €)", "a2": " (44,99 €)", "b1": "", "c1": ""}


def test_gleicher_name_und_gleicher_preis_bekommt_noch_die_id_endung():
    t = [
        {"tarif_id": "x-1111", "netz": "o2", "name": "Mobile L", "grundgebuehr": 39.99},
        {"tarif_id": "x-2222", "netz": "o2", "name": "Mobile L", "grundgebuehr": 39.99},
    ]
    z = tarifwelt_lauf.namenszusaetze(t)
    assert z["x-1111"] != z["x-2222"]
    assert "1111" in z["x-1111"]
