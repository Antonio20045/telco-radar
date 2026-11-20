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


def _t(tid, preis, name="Mobile L", netz="o2"):
    return {"tarif_id": tid, "netz": netz, "name": name, "grundgebuehr": preis}


def test_zusatz_nur_bei_gleichem_namen_und_aus_der_tarif_id():
    t = [
        _t("aaaa000001", 39.99),
        _t("aaaa000002", 44.99),
        _t("bbbb000001", 29.99, "Mobile M"),
        _t("cccc000001", 9.0, netz="freenet - Telekom"),
    ]
    z = tarifwelt_lauf.namenszusaetze(t)
    assert z == {
        "aaaa000001": " (000001)",
        "aaaa000002": " (000002)",
        "bbbb000001": "",
        "cccc000001": "",
    }


def test_preiswechsel_aendert_den_zusatz_und_damit_die_buendel_id_nicht():
    vorher = [_t("aaaa000001", 39.99), _t("aaaa000002", 44.99)]
    nachher = [_t("aaaa000001", 41.99), _t("aaaa000002", 46.99)]
    assert tarifwelt_lauf.namenszusaetze(vorher) == tarifwelt_lauf.namenszusaetze(
        nachher
    )


def test_gleicher_name_und_gleiche_id_endung_wird_laenger_statt_gleich():
    z = tarifwelt_lauf.namenszusaetze(
        [_t("xx1111111111", 1.0), _t("yy2222111111", 1.0)]
    )
    assert z["xx1111111111"] != z["yy2222111111"]


def _bestand(sku, name, tarif_id):
    return {
        "anbieter": "Saturn/MediaMarkt · o2-Netz",
        "sku_id": sku,
        "tarif_name": name,
        "tarif_id": f"mediamarkt_tarifwelt:{tarif_id}",
    }


def test_frueher_gesammelter_tarif_behaelt_seinen_namen_und_damit_die_id():
    sku = "apple-iphone-17-256gb"
    t = [_t("aaaa000001", 39.99), _t("aaaa000002", 44.99), _t("aaaa000003", 49.99)]
    bekannt = tarifwelt_lauf.plain_halter([_bestand(sku, "Mobile L", "aaaa000002")])
    z = tarifwelt_lauf.namenszusaetze(t, sku, bekannt)
    assert z["aaaa000002"] == ""
    assert z["aaaa000001"] and z["aaaa000003"]
    neben = tarifwelt_lauf.namenszusaetze(t, "apple-iphone-17-512gb", bekannt)
    assert all(neben.values()), "Halter gilt nur fuer seine SKU"
    ohne = tarifwelt_lauf.namenszusaetze(t, sku, {})
    assert all(ohne.values())


def test_halter_mit_zusatz_im_bestand_ist_kein_plain_halter():
    sku = "apple-iphone-17-256gb"
    bekannt = tarifwelt_lauf.plain_halter(
        [_bestand(sku, "Mobile L (000002)", "aaaa000002")]
    )
    t = [_t("aaaa000001", 39.99), _t("aaaa000002", 44.99)]
    z = tarifwelt_lauf.namenszusaetze(t, sku, bekannt)
    assert z["aaaa000001"] and z["aaaa000002"]


def _ids(sku, anbieter, tarife, zusaetze):
    from telco_radar.tco_model import buendel_id

    return {
        t["tarif_id"]: buendel_id(
            sku, anbieter, "Mobile L" + zusaetze[t["tarif_id"]], 24
        )
        for t in tarife
    }


def test_buendel_ids_bleiben_ueber_preiswechsel_und_folgetag_gleich():
    sku = "apple-iphone-17-256gb"
    anbieter = "Saturn/MediaMarkt · o2-Netz"
    t1 = [_t("aaaa000001", 39.99), _t("aaaa000002", 44.99)]
    z1 = tarifwelt_lauf.namenszusaetze(t1)
    t2 = [_t("aaaa000001", 42.99), _t("aaaa000002", 47.99)]
    bestand = [_bestand(sku, "Mobile L" + z1[i], i) for i in z1]
    halter = tarifwelt_lauf.plain_halter(bestand)
    z2 = tarifwelt_lauf.namenszusaetze(t2, sku, halter)
    ids1 = _ids(sku, anbieter, t1, z1)
    assert ids1 == _ids(sku, anbieter, t2, z2)
    assert len(set(ids1.values())) == 2


def test_alte_ids_der_bestandszeilen_bleiben_in_der_echten_iphone17_liste():
    """Die Bandauswahl vor dem 20.11.2026 legte je Tarifname EINE Zeile mit dem
    Namen ohne Zusatz an. Wer so im Bestand steht, behaelt die ID."""

    text = (FIXTURES / "tarifwelt_mm_tarifliste_iphone17_20261108.json").read_text()
    tarife = tarifwelt_lauf.vergleichbare_tarife(
        tarifwelt.lies_tarifliste(text), LEITER
    )
    sku = sku_id("apple-iphone-17", 256, None)
    kern = tarifwelt.kern_je_netz_und_band(tarife, LEITER)
    bestand = [
        {
            "anbieter": tarifwelt.anbieter_zeile(t["netz"]),
            "sku_id": sku,
            "tarif_name": t["name"],
            "tarif_id": f"mediamarkt_tarifwelt:{t['tarif_id']}",
        }
        for t in tarife
        if t["tarif_id"] in kern
    ]
    z = tarifwelt_lauf.namenszusaetze(tarife, sku, tarifwelt_lauf.plain_halter(bestand))
    for t in tarife:
        if t["tarif_id"] in kern:
            assert z[t["tarif_id"]] == "", t["name"]
