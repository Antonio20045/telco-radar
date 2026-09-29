"""Hergeleitete Beträge bleiben als hergeleitet erkennbar - bis in den
Bestand und die Historie.

1&1 (Tarifaufschlag aus dem Tarifraster) und o2 (Tarifsumme minus
Geräterate) liefern seit dem 29.09.2026 Bündel, deren Tarif- bzw.
Bündelbetrag nicht wörtlich auf der Seite steht. Ohne dieses Feld wären sie
im Bestand von gemessenen nicht zu unterscheiden.
"""
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.tarif_bezug import Tarifbestand

TAG = "2026-03-10"


def _bestand():
    return Tarifbestand([
        {"tarif_id": "congstar:allnet-flat-m", "anbieter": "congstar",
         "name": "Allnet Flat M", "grundgebuehr": 24.0}])


def _roh(**extra):
    return {"anbieter": "congstar", "tarif_name": "Allnet Flat M",
            "sku_id": "apple-iphone-17-256gb-schwarz",
            "tarif_monatlich": 24.0, "geraet_monatsrate": 26.5,
            "geraet_zuzahlung": 19.0, "laufzeit_monate": 36,
            "anschlusspreis": 0.0, "zustand": "neu",
            "quelle_url": "https://www.congstar.de/geraete/apple/x/",
            **extra}


def test_herleitung_reist_vom_rohsatz_bis_in_bestand_und_historie(tmp_path):
    bilanz = aus_rohsaetzen(
        [_roh(herleitung="tarifsumme_minus_geraeterate"),
         _roh(sku_id="apple-iphone-17-512gb-schwarz")], _bestand(), TAG)
    assert [b.herleitung for b in bilanz.buendel] == \
        ["tarifsumme_minus_geraeterate", ""]

    db = TcoDB(tmp_path / "tco.json", tmp_path / "historie.jsonl")
    db.upsert_buendel(bilanz.buendel, TAG)
    db.save(TAG)
    je_sku = {s["sku_id"]: s for s in TcoDB(tmp_path / "tco.json").buendel()}
    assert je_sku["apple-iphone-17-256gb-schwarz"]["herleitung"] == \
        "tarifsumme_minus_geraeterate"
    # Gegenprobe: gemessen bleibt leer, nicht None und nicht geraten.
    assert je_sku["apple-iphone-17-512gb-schwarz"]["herleitung"] == ""
    historie = (tmp_path / "historie.jsonl").read_text(encoding="utf-8")
    assert '"herleitung": "tarifsumme_minus_geraeterate"' in historie
