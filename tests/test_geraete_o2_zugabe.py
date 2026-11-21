"""o2: eine Gratis-Zugabe in der Beschreibung ist kein Zubehörbündel.

DER BEFUND (21.11.2026)
-----------------------
Der Katalog mit Tarif führt „Google Pixel 11 mit Fitbit Charge 6“ und „Google Pixel 11
Pro XL mit Fitbit Charge 6“; ihr Angebotsname ist der des Geräts allein
(``…-pixel-11-256gb-frost-36xhigh``, ohne ``-mit-``), der Trackingblock nennt das
Modell „Pixel 11“. Die Produktseite sagt: „Entscheide Dich jetzt für das Google Pixel
11 und erhalte die Fitbit Charge 6 gratis dazu“, „Gesamtpreis Gerät: 991,00 €“
(1 € + 36 × 27,50 €). Der Adapter verwarf beide wegen „mit“ in der Beschreibung; o2
hatte am 21.11. keine Adapterzeile für diese zwei Geräte, nur 12 Klick-Zeilen.
Ein echtes Bündel trägt das Zubehör im Angebotsnamen
(``…-pixel-11-256gb-obsidian-mit-pixel-buds-pro-2-hazel-36xhigh``) und fällt weiter
heraus.

DIE FIXTURE: ``o2_katalog_zugabe_20261121.json`` (echter Abruf, gekürzt auf drei
Einträge, Werte unverändert).
"""

from pathlib import Path

import pytest

from telco_radar.collect.geraete import o2

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_FIX = _FIX / "o2_katalog_zugabe_20261121.json"


@pytest.fixture(scope="module")
def saetze() -> dict:
    roh = o2.lies_buendel(_FIX.read_text(encoding="utf-8"))
    return {s["angebot"]: s for s in roh}


def test_geraet_mit_gratis_zugabe_wird_gelesen(saetze):
    satz = saetze["privatkunden-google-pixel-11-256gb-frost-36xhigh"]
    assert satz["strukturierter_name"] == "Google Pixel 11"
    assert satz["titel"] == "Google Pixel 11 256 GB frost"
    assert (satz["geraet_zuzahlung"], satz["geraet_monatsrate"]) == (1.0, 27.5)
    assert satz["tarif_monatlich"] == 14.99
    assert satz["anschlusspreis"] == 0.0
    assert satz["laufzeit_monate"] == 36


def test_pro_xl_mit_gratis_zugabe_wird_gelesen(saetze):
    satz = saetze["privatkunden-google-pixel-11-pro-xl-256gb-canyon-36xhigh"]
    assert satz["strukturierter_name"] == "Google Pixel 11 Pro XL"


def test_gegenprobe_zubehoer_im_angebotsnamen_bleibt_verworfen(saetze):
    assert len(saetze) == 2
    assert not [a for a in saetze if "-mit-" in a]


def test_gegenprobe_barpreis_katalog_liest_dasselbe_modell():
    roh = o2.lies(_FIX.read_text(encoding="utf-8"))
    assert sorted(s["strukturierter_name"] for s in roh) == [
        "Google Pixel 11",
        "Google Pixel 11 Pro XL",
    ]
