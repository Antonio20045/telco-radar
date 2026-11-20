"""1&1-Tarifübersichten: die Helfer, die nach dem Wegfall der hergeleiteten
Tarifstufen (20.11.2026, `test_einsundeins_gemessen_2011.py`) bleiben.

`tarifraster_adressen` hält die Klick-Tagesdatei gegen die Übersichten,
`tarifname_bereinigt` lesen Klick-Raster und Klick-Anschluss.

DIE FIXTURES SIND GESPEICHERTE ECHTE ABRUFE (29.09.2026, HTTP 200, reines
HTTP-GET, Absender TelcoRadar/1.0): `einsundeins_tarifuebersicht_all_net_flat_
2026-09-29.html.gz` = `/all-net-flat-vergleich`, `..._unlimited_...` =
`/unbegrenztes-datenvolumen`, beide vollständig.
"""

import gzip
from pathlib import Path

from telco_radar.collect.geraete import einsundeins as E

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_TAG = "2026-09-29"

_ANF = "https://mobile.1und1.de/all-net-flat-vergleich"
_UNL = "https://mobile.1und1.de/unbegrenztes-datenvolumen"
_RASTER = (
    "all-net-flat-s",
    "all-net-flat-m",
    "all-net-flat-l",
    "unlimited-s",
    "unlimited-m",
    "unlimited-l",
    "unlimited-xl",
)
_UEBERSICHTEN = {
    _ANF: f"einsundeins_tarifuebersicht_all_net_flat_{_TAG}.html.gz",
    _UNL: f"einsundeins_tarifuebersicht_unlimited_{_TAG}.html.gz",
}


def _fixture(name: str) -> str:
    return gzip.open(_FIX / name, "rb").read().decode("utf-8", "replace")


def test_die_uebersichten_verlinken_sieben_geraeteraster():
    adressen = set()
    for url, name in _UEBERSICHTEN.items():
        adressen.update(E.tarifraster_adressen(_fixture(name), url))
    assert adressen == {f"https://mobile.1und1.de/smartphones-{t}" for t in _RASTER}
    assert not any("?" in a for a in adressen)


def test_tarifname_ohne_volumenklammer():
    assert (
        E.tarifname_bereinigt("1&amp;1 All-Net-Flat M (50 GB)") == "1&1 All-Net-Flat M"
    )
    assert E.tarifname_bereinigt("1&1 Unlimited XL (unlimited)") == "1&1 Unlimited XL"
    assert E.tarifname_bereinigt("1&1 All-Net-Flat S") == "1&1 All-Net-Flat S"
