"""Reproduktionen des Prüfers zu PR 205, Runde 3 (``/tmp/pruefer/k205b``),
übernommen; gegen den Stand ``4a7efc1b3`` rot.

Runde 4: Das Soll kommt allein aus der Produktseite; der Test „kaufbarer Tarif der
Übersicht“ erwartet darum (1, 1, 0) und den Preis von Unlimited M als „anderer
Kaufweg (Tarifübersicht), nicht gezählt“ statt (2, 2, 0).

Abweichungen: Im ersten Test bleiben die zehn 36-Monats-Preise des GELESENEN iPhone
17 (die Seite bietet nur 24 Monate) nach Regel 1 „so nicht angeboten“; geprüft wird,
dass kein Preis eines Geräts ohne gelesene Auswahl (Pixel 11, Galaxy A57) zählt.
„Slug -> Tarifname hängt nicht von der Reihenfolge ab“ prüft jetzt das
Ergebnis des Einhängens für beide Reihenfolgen der Bündel (die Abbildung Slug ->
Messname über den Bestand gibt es nicht mehr; der Name kommt von der Kachel).

Runde 5: Die Tests zum zweiten o2-Kaufweg (Slug-Reihenfolge, kaufbarer Tarif der
Übersicht, Ausfall der Übersicht) sind entfernt; den Kaufweg gibt es nicht mehr
(Karussell-Befund: die Produktseite bietet alle 11 Tarife selbst).
"""

from __future__ import annotations

import pytest
import test_geraete_angebot as base

from telco_radar import geraete_angebot as ga
from telco_radar.report import geraete_vollstaendigkeit as seite

TAG = base.TAG


@pytest.fixture
def katalog():
    return base.Katalog(
        geraete=[
            base.Geraet("Apple", "iPhone 17"),
            base.Geraet("Google", "Pixel 11"),
            base.Geraet("Samsung", "Galaxy A57"),
        ]
    )


def _telekom(genannt, beleg_ende=None):
    gelesen = ga.Seite(
        "https://www.telekom.de/shop/geraet/apple/apple-iphone-17/schwarz-256-gb",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB"), ga.Option("512 GB", "512 GB")],
        tarife=[ga.Option(f"MagentaMobil {g}", g) for g in ("XS", "S", "M", "L", "XL")],
        laufzeiten=[ga.Option("24", "24")],
    )
    z = ga.Zaehlung("telekom", TAG, f"{TAG}T23:10:00+00:00", seiten=[gelesen])
    z.kacheln = [ga.Kachel(gelesen.url, gelesen.titel)]
    z.genannt = genannt
    if beleg_ende:
        z.uebersicht_ende = beleg_ende
    return z


def _marke(tmp_path, z, katalog):
    zeilen, voll = base._voll(tmp_path, [z], katalog)
    voll["datum"] = TAG
    row = next(
        x
        for x in seite.zeilen({"vollstaendigkeit": voll}, TAG)["zeilen"]
        if x["name"] == "Telekom"
    )
    return zeilen["Telekom"]["ebenen"]["kombinationen"], row


def test_unvollstaendige_uebersicht_modelle_ohne_seite_sind_kein_preis_ohne_angebot(
    tmp_path, katalog
):
    """Übersicht nennt 95, gelesen 1 Kachel. Pixel 11 und Galaxy A57 stehen im Ist,
    ihre Seite wurde nie gelesen. Ihre Bündel dürfen nicht als 'Preise ohne Angebot
    auf der Seite' zählen (die Seite wurde nicht gesehen)."""
    k, row = _marke(tmp_path, _telekom(95), katalog)
    modelle = {
        e["schluessel"].split("-256gb")[0].split("-512gb")[0]
        for e in k["nicht_im_soll"]
    }
    assert modelle <= {"apple-iphone-17"}, (modelle, row["marke"])
    assert all(e["schluessel"].endswith("--36m") for e in k["nicht_im_soll"])


def test_modell_ausserhalb_der_uebersicht_zaehlt_nicht_als_preis_ohne_angebot(
    tmp_path, katalog
):
    """Auch bei vollständiger Übersicht: Modell nicht in der Übersicht heißt, es gibt
    keine gelesene Auswahl; die Modell-Ebene meldet es, nicht die Preis-Ebene."""
    z = _telekom(1)
    k, row = _marke(tmp_path, z, katalog)
    assert "Preise ohne Angebot" not in row["marke"], row["marke"]
    assert not [e for e in k["nicht_im_soll"] if "pixel" in e["schluessel"]]
    zeilen, _ = base._voll(tmp_path / "zwei", [_telekom(1)], katalog)
    modelle = zeilen["Telekom"]["ebenen"]["modelle"]
    assert {e["schluessel"] for e in modelle["nicht_im_soll"]} == {
        "google-pixel-11",
        "samsung-galaxy-a57",
    }
    assert {e["grund"] for e in modelle["nicht_im_soll"]} == {
        "nicht in der Übersicht des Anbieters"
    }
