"""1&1: der Tarifname ohne Volumenklammer, den Klick-Raster und Klick-Anschluss lesen.

Die hergeleiteten Tarifstufen und der 1&1-Adapter sind entfallen (20.11.2026);
`tarifname_bereinigt` bleibt als Leser des Klick-Laufs.
"""

from telco_radar.collect.geraete import einsundeins as E


def test_tarifname_ohne_volumenklammer():
    assert (
        E.tarifname_bereinigt("1&amp;1 All-Net-Flat M (50 GB)") == "1&1 All-Net-Flat M"
    )
    assert E.tarifname_bereinigt("1&1 Unlimited XL (unlimited)") == "1&1 Unlimited XL"
    assert E.tarifname_bereinigt("1&1 All-Net-Flat S") == "1&1 All-Net-Flat S"
