"""Nothing Phone (4a) Pro mit 128 GB: 1&1 verkauft ihn, der Katalog führt die Größe."""

from __future__ import annotations

from dataclasses import replace

from bestand_pfad import lese_wurzel
from klickergebnisse import einsundeins_lesung, erfasst, ergebnisdatei, lauf

from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.collect.geraete.klickziele import Seitenziel
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import sku_id

HEUTE = "2026-10-09"
ZIEL = Seitenziel(
    "nothing-phone-4a-pro", None, "https://mobile.1und1.de/nothing-phone-4a-pro"
)


def test_128_gb_wird_rohsatz():
    katalog = lade_katalog(lese_wurzel())
    lesung = einsundeins_lesung()
    buendel = replace(lesung.buendel, buendelbetrag=25.99, einmalzahlung=140.0)
    kombination = erfasst(replace(lesung, buendel=buendel), "128", "tariff-anf-s-mvl")
    seite = (ZIEL, lauf(ZIEL, [kombination]))
    daten = ergebnisdatei("1&1", "1und1", [seite], HEUTE, vertragsform="ein_vertrag")

    (satz,) = ausbeute(daten, katalog).rohsaetze

    assert satz["sku_id"] == sku_id("nothing-phone-4a-pro", 128, None, "neu")
    assert (satz["buendel_monatlich"], satz["geraet_zuzahlung"]) == (25.99, 140.0)
