"""Belegbilder: Dateiname, Schwelle der großen Änderung, Aufbewahrung.

Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7).
"""

from __future__ import annotations

from datetime import date

import pytest

from telco_radar.beleg_regeln import (
    AUFBEWAHRUNG_GROSS_TAGE,
    AUFBEWAHRUNG_TAGE,
    GROSS_EURO,
    GROSS_PROZENT,
    dateiname,
    gross_tag,
    ist_abgelaufen,
    ist_beleg_tag,
    ist_gross_tag,
    ist_grosse_aenderung,
    ist_sichtbar,
    release_abgelaufen,
    release_ende,
    tages_tag,
    zerlege_dateiname,
)

TAG = date(2026, 11, 3)


def test_dateiname_traegt_geraet_anbieter_und_tag():
    assert (
        dateiname("apple-iphone-17-256", "vodafone", TAG)
        == "apple-iphone-17-256__vodafone__2026-11-03.webp"
    )


def test_dateiname_rundreise():
    name = dateiname("apple-iphone-17-256", "o2", TAG)
    teile = zerlege_dateiname(name)
    assert teile is not None
    assert (teile.geraet_id, teile.anbieter_id, teile.datum) == (
        "apple-iphone-17-256",
        "o2",
        TAG,
    )
    assert teile.schluessel == "apple-iphone-17-256__o2"


@pytest.mark.parametrize(
    "geraet_id", ["iPhone 17 Pro", "", "a__b", "-x", "x-", "Ä", "a/b"]
)
def test_dateiname_lehnt_titeltext_und_fremde_ids_ab(geraet_id):
    with pytest.raises(ValueError):
        dateiname(geraet_id, "o2", TAG)


@pytest.mark.parametrize(
    "name",
    [
        "foto.webp",
        "a__b__2026-11-03.png",
        "a__b__2026-13-40.webp",
        "A__b__2026-11-03.webp",
        "a__b.webp",
        "a__b__c__2026-11-03.webp",
        "",
    ],
)
def test_fremde_dateinamen_sind_kein_beleg(name):
    assert zerlege_dateiname(name) is None


@pytest.mark.parametrize(
    ("vorher", "jetzt", "gross"),
    [
        (1000.0, 1049.99, False),
        (1000.0, 1050.0, True),
        (1000.0, 950.0, True),
        (1000.0, 1000.0, False),
        (200.0, 209.99, False),
        (200.0, 210.0, True),
        (200.0, 209.0, False),
        (2000.0, 2049.99, False),
        (2000.0, 2050.0, True),
        (None, 1000.0, False),
        (1000.0, None, False),
        (None, None, False),
        (0.0, 0.01, True),
    ],
)
def test_schwelle_grosse_aenderung(vorher, jetzt, gross):
    assert ist_grosse_aenderung(vorher, jetzt) is gross


def test_schwellen_sind_benannte_konstanten():
    assert (GROSS_PROZENT, GROSS_EURO) == (5, 50)
    assert (AUFBEWAHRUNG_TAGE, AUFBEWAHRUNG_GROSS_TAGE) == (7, 90)


def test_release_tags():
    assert tages_tag(TAG) == "belege-2026-11-03"
    assert tages_tag(TAG, 2) == "belege-2026-11-03-2"
    assert gross_tag(TAG) == "belege-gross-2026-11"
    assert gross_tag(TAG, 3) == "belege-gross-2026-11-3"
    assert ist_gross_tag("belege-gross-2026-11")
    assert not ist_gross_tag("belege-2026-11-03")
    for tag in ("belege-2026-11-03", "belege-gross-2026-11", "belege-2026-11-03-2"):
        assert ist_beleg_tag(tag)
    for tag in ("v1.0", "belege", "belege-2026-11", "latest", "belege-gross-2026"):
        assert not ist_beleg_tag(tag)


def test_release_ende_ist_tag_oder_monatsende():
    assert release_ende("belege-2026-11-03") == date(2026, 11, 3)
    assert release_ende("belege-gross-2026-11") == date(2026, 11, 30)
    assert release_ende("belege-gross-2026-12") == date(2026, 12, 31)
    assert release_ende("belege-gross-2028-02") == date(2028, 2, 29)
    assert release_ende("belege-gross-2026-13") is None
    assert release_ende("belege-2026-02-31") is None
    assert release_ende("v1") is None


def test_aufbewahrung_tag_sieben_bleibt_acht_geht():
    heute = date(2026, 11, 10)
    assert not ist_abgelaufen(date(2026, 11, 3), heute, gross=False)
    assert ist_abgelaufen(date(2026, 11, 2), heute, gross=False)


def test_aufbewahrung_gross_neunzig_bleibt_einundneunzig_geht():
    heute = date(2027, 2, 1)
    assert not ist_abgelaufen(date(2026, 11, 3), heute, gross=True)
    assert ist_abgelaufen(date(2026, 11, 2), heute, gross=True)


def test_release_abgelaufen_tages_und_monatsrelease():
    heute = date(2026, 11, 10)
    assert not release_abgelaufen("belege-2026-11-03", heute)
    assert release_abgelaufen("belege-2026-11-02", heute)
    assert not release_abgelaufen("belege-gross-2026-08", date(2026, 11, 28))
    assert release_abgelaufen("belege-gross-2026-08", date(2026, 11, 30))


def test_fremde_releases_loescht_nichts():
    heute = date(2030, 1, 1)
    for tag in ("v1.0", "belege-2026-13-01", "nightly", "belege-gross-2026-13"):
        assert not release_abgelaufen(tag, heute)


def test_sichtbarkeit_teilt_die_regel_mit_dem_loeschen():
    heute = date(2026, 11, 10)
    neu = dateiname("g", "o2", date(2026, 11, 3))
    alt = dateiname("g", "o2", date(2026, 11, 2))
    assert ist_sichtbar("belege-2026-11-03", neu, heute)
    assert not ist_sichtbar("belege-2026-11-02", alt, heute)
    assert ist_sichtbar("belege-gross-2026-11", alt, heute)
    assert not ist_sichtbar("belege-2026-11-10", alt, heute)


def test_fremdes_ist_nie_sichtbar():
    heute = date(2026, 11, 10)
    assert not ist_sichtbar("belege-2026-11-10", "foto.webp", heute)
    assert not ist_sichtbar("v1.0", dateiname("g", "o2", heute), heute)
