"""Überholte Klick-Bündel: Galaxy A57 256 GB mit Buds-Preisen vom 09.10.2026."""

from telco_radar.report.klick_ueberholt import ohne_ueberholte, ueberholt


def _b(sku, tarif, datum, quelle="klick", anbieter="1&1"):
    return {
        "id": f"{anbieter}|{sku}|{tarif}|{datum}",
        "anbieter": anbieter,
        "sku_id": sku,
        "tarif_name": tarif,
        "abgerufen_am": datum,
        "quelle_art": quelle,
    }


A57_256 = "samsung-galaxy-a57-256gb-awesome-gray"
A57_256_OHNE = "samsung-galaxy-a57-256gb-ohne-farbe"
IPHONE = "apple-iphone-17-pro-256gb-cosmic-orange"


def _bestand():
    return [
        _b(A57_256, "1&1 All-Net-Flat S", "2026-10-09"),
        _b(A57_256, "1&1 All-Net-Flat M", "2026-10-09"),
        _b(A57_256_OHNE, "1&1 Unlimited XL", "2026-10-09"),
        _b(A57_256, "1&1 All-Net-Flat S", "2026-10-10"),
        _b(IPHONE, "1&1 All-Net-Flat M", "2026-10-10"),
        _b(IPHONE, "1&1 Unlimited XL", "2026-10-10"),
    ]


def test_nicht_wieder_gelesene_a57_zeilen_sind_ueberholt():
    weg = ueberholt(_bestand())
    assert weg == {
        f"1&1|{A57_256}|1&1 All-Net-Flat S|2026-10-09",
        f"1&1|{A57_256}|1&1 All-Net-Flat M|2026-10-09",
        f"1&1|{A57_256_OHNE}|1&1 Unlimited XL|2026-10-09",
    }


def test_ohne_ueberholte_behaelt_die_frischen_zeilen():
    rest = ohne_ueberholte(_bestand())
    assert [(e["sku_id"], e["tarif_name"]) for e in rest] == [
        (A57_256, "1&1 All-Net-Flat S"),
        (IPHONE, "1&1 All-Net-Flat M"),
        (IPHONE, "1&1 Unlimited XL"),
    ]


def test_ein_nicht_wieder_gelesener_tarif_bleibt():
    bestand = [
        _b(A57_256, "1&1 All-Net-Flat M", "2026-10-09"),
        _b(A57_256, "1&1 All-Net-Flat S", "2026-10-10"),
    ]
    assert ueberholt(bestand) == set()


def test_eine_nicht_wieder_gelesene_geraeteseite_bleibt():
    bestand = [
        _b(A57_256, "1&1 All-Net-Flat M", "2026-10-09"),
        _b(IPHONE, "1&1 All-Net-Flat M", "2026-10-10"),
    ]
    assert ueberholt(bestand) == set()


def test_andere_speichergroesse_belegt_die_geraeteseite_nicht():
    bestand = [
        _b(A57_256, "1&1 All-Net-Flat M", "2026-10-09"),
        _b("samsung-galaxy-a57-128gb-awesome-gray", "1&1 All-Net-Flat S", "2026-10-10"),
        _b(IPHONE, "1&1 All-Net-Flat M", "2026-10-10"),
    ]
    assert ueberholt(bestand) == set()


def test_adapterzeilen_und_andere_anbieter_bleiben():
    bestand = [
        _b(A57_256, "1&1 All-Net-Flat M", "2026-10-09", quelle=None),
        _b(A57_256, "1&1 All-Net-Flat M", "2026-10-09", anbieter="o2"),
        _b(A57_256, "1&1 All-Net-Flat S", "2026-10-10"),
        _b(IPHONE, "1&1 All-Net-Flat M", "2026-10-10"),
    ]
    assert ueberholt(bestand) == set()


def test_am_selben_tag_bestaetigt_ist_nicht_ueberholt():
    bestand = [
        _b(A57_256, "1&1 All-Net-Flat M", "2026-10-10"),
        _b(A57_256, "1&1 All-Net-Flat S", "2026-10-10"),
        _b(IPHONE, "1&1 All-Net-Flat M", "2026-10-10"),
    ]
    assert ueberholt(bestand) == set()
