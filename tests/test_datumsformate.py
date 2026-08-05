"""Der Datums-Parser in mehr als englisch.

Warum das eine eigene Testdatei wert ist: eine undatierte Meldung sortiert im
Lauf ans Ende und wird faktisch nie bewertet (CLAUDE.md, "Der Analyst sieht nur
die ersten max_items_per_region Meldungen"). Ein Datumsformat, das der Parser
nicht kennt, macht eine Quelle also nicht schlechter lesbar, sondern
unsichtbar - und der Abnahme-Check wirft sie an Kriterium 3 raus. In Welle 2
war das nach dem Sucher die zweitgroesste Verlustquelle.

Kein Netz noetig.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from telco_radar.collect.newsroom import _date_from_text, _ist_monat, _monat


def _d(y, m, t):
    return datetime(y, m, t, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Tag Monat Jahr - die haeufigste Form, jetzt in vielen Sprachen
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text,erwartet", [
    # schon vorher gekonnt - darf nicht kaputtgehen
    ("15 July 2026", _d(2026, 7, 15)),
    ("15. Juli 2026", _d(2026, 7, 15)),
    ("30 de julho de 2026", _d(2026, 7, 30)),
    ("24 Temmuz 2026", _d(2026, 7, 24)),
    # neu: slawische Sprachen
    ("15 lipca 2026", _d(2026, 7, 15)),
    ("3 listopada 2026", _d(2026, 11, 3)),
    ("28 grudnia 2026", _d(2026, 12, 28)),
    ("15. srpna 2026", _d(2026, 8, 15)),
    ("2. prosince 2026", _d(2026, 12, 2)),
    # neu: nordisch und baltisch
    ("15 kesäkuuta 2026", _d(2026, 6, 15)),
    ("9 marraskuuta 2026", _d(2026, 11, 9)),
    ("9 maaliskuuta 2026", _d(2026, 3, 9)),
    ("15 juulil 2026", _d(2026, 7, 15)),
    ("15 rugpjūčio 2026", _d(2026, 8, 15)),
    # neu: romanisch und suedosteuropaeisch
    ("15 iulie 2026", _d(2026, 7, 15)),
    ("15 noiembrie 2026", _d(2026, 11, 15)),
    ("15 luglio 2026", _d(2026, 7, 15)),
    ("15 maart 2026", _d(2026, 3, 15)),
    # neu: griechisch, kyrillisch, arabisch, hindi
    ("15 Ιουλίου 2026", _d(2026, 7, 15)),
    ("15 июля 2026", _d(2026, 7, 15)),
    ("15 листопада 2026", _d(2026, 11, 15)),
    ("15 يوليو 2026", _d(2026, 7, 15)),
    ("15 अगस्त 2026", _d(2026, 8, 15)),
])
def test_tag_monat_jahr(text, erwartet):
    assert _date_from_text(text) == erwartet


# --------------------------------------------------------------------------- #
# Monat Tag Jahr - vorher auf eine feste Liste englischer Namen begrenzt
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text,erwartet", [
    ("July 15, 2026", _d(2026, 7, 15)),
    ("Julho 15, 2026", _d(2026, 7, 15)),
    ("Enero 9, 2026", _d(2026, 1, 9)),
    ("Ağustos 15, 2026", _d(2026, 8, 15)),
])
def test_monat_tag_jahr(text, erwartet):
    assert _date_from_text(text) == erwartet


# --------------------------------------------------------------------------- #
# Jahr zuerst
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text,erwartet", [
    ("2026-07-15", _d(2026, 7, 15)),
    ("2026. július 15.", _d(2026, 7, 15)),        # ungarisch
    ("2026年7月15日", _d(2026, 7, 15)),            # japanisch/chinesisch
    ("2026년 7월 15일", _d(2026, 7, 15)),          # koreanisch
    ("ngày 15 tháng 7 năm 2026", _d(2026, 7, 15)),  # vietnamesisch
])
def test_jahr_zuerst(text, erwartet):
    assert _date_from_text(text) == erwartet


# --------------------------------------------------------------------------- #
# Was NICHT als Datum durchgehen darf
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text", [
    "15 Werke 2026",          # Phantasiewort - stand schon in test_collect.py
    "Strategie 2030",
    "Vodafone 15, 2026",      # kein Monat, nur ein Firmenname
    "Awards 2026 5",
    "15 Vodafone 2026",
])
def test_kein_datum(text):
    assert _date_from_text(text) is None


def test_laengster_stamm_gewinnt():
    """Finnisch "marraskuuta" faengt mit "mar" an und ist trotzdem November."""
    assert _monat("marraskuuta") == 11
    assert _monat("marzo") == 3
    assert _monat("maaliskuuta") == 3
    assert _monat("mars") == 3


def test_ist_monat_prueft_zahlen_und_woerter():
    assert _ist_monat("7")
    assert _ist_monat("12")
    assert not _ist_monat("13")
    assert not _ist_monat("0")
    assert _ist_monat("lipca")
    assert not _ist_monat("Vodafone")


def test_mehrdeutige_abkuerzungen_bleiben_draussen():
    """Tschechisch cerven (Juni) und cervenec (Juli) sind als Stamm nicht
    trennbar - dann lieber undatiert als falsch datiert."""
    assert _monat("cervence") is None
    assert _monat("června") is None
    # franzoesisch: nur die vollen Formen, "jui" allein bliebe mehrdeutig
    assert _monat("juin") == 6
    assert _monat("juillet") == 7
