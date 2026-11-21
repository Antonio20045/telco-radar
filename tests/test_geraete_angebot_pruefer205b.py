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
"""

from __future__ import annotations

import pytest
import test_geraete_angebot as base

from telco_radar import geraete_angebot as ga
from telco_radar.geraete_angebot import einhaengen as ein
from telco_radar.geraete_vollstaendigkeit import Signale, baue
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


def _o2_lauf(tmp_path, ist, katalog, tarifuebersicht, grund=None):
    s = ga.Seite(
        "https://www.o2online.de/e-shop/smartphone/apple-iphone-17",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        tarife=[ga.Option("O2 Mobile S mit 15 GB+", "x")],
        laufzeiten=[ga.Option("24", "24")],
    )
    z = ga.Zaehlung("o2", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.tarifuebersicht, z.tarifuebersicht_grund = tarifuebersicht, grund
    ga.schreibe(tmp_path, z)
    sig = Signale()
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, sig)
    ein.haenge_ein(voll, tmp_path, TAG, ist, sig, katalog)
    return next(x for x in voll["anbieter"] if x["name"] == "o2")["ebenen"][
        "kombinationen"
    ]


def test_slug_zu_tarifname_haengt_nicht_von_der_reihenfolge_der_buendel_ab(
    tmp_path, katalog
):
    """Unter dem Startslug ``o2-mobile-unlimited-m`` stehen zwei Tarife; das Ergebnis
    darf nicht vom ersten Bündel abhängen, und „Unlimited M“ ist nie „Mobile S“."""
    url = "https://www.o2online.de/e-shop/x?tarif=o2-mobile-unlimited-m"
    sku = "apple-iphone-17-256gb-schwarz"

    def bd(slug, name):
        return {
            "id": f"buendel--x--{sku}--{slug}--24m",
            "sku_id": sku,
            "anbieter": "o2",
            "tarif_id": slug,
            "tarif_name": name,
            "laufzeit_monate": 24,
            "abgerufen_am": TAG,
            "quelle_url": url,
        }

    s = bd("o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)")
    m = bd(
        "o2-mobile-unlimited-m-mit-100-mbit-s-24-mon",
        "O2 Mobile Unlimited M mit 100 MBit/s (24 Mon.)",
    )
    karte = [ga.Option("O2 Mobile Unlimited M", "o2-mobile-unlimited-m")]
    a = _o2_lauf(tmp_path / "a", [s, m], katalog, karte)
    b = _o2_lauf(tmp_path / "b", [m, s], katalog, karte)
    felder = ("soll", "erfasst", "nicht_im_soll_zahl", "nicht_verglichen_zahl")
    assert [a[f] for f in felder] == [b[f] for f in felder] == [1, 1, 0, 1]


def test_o2_kaufbarer_tarif_der_uebersicht_wird_nicht_auf_falschen_messnamen_abgebildet(
    tmp_path, katalog
):
    """Tarifübersicht bietet 'O2 Mobile Unlimited M' (Slug o2-mobile-unlimited-m). Die
    Messung hat beide Tarife (S und Unlimited M) für iPhone 17 256 GB / 24 Mon.
    erfasst, beide Bündel mit quelle_url ...?tarif=o2-mobile-unlimited-m. Soll = S +
    Unlimited M, beides erfasst, nichts ohne Angebot."""
    url = "https://www.o2online.de/e-shop/smartphone/apple-iphone-17?tarif=o2-mobile-unlimited-m"
    sku = "apple-iphone-17-256gb-schwarz"

    def bd(slug, name):
        return {
            "id": f"buendel--x--{sku}--{slug}--24m",
            "sku_id": sku,
            "anbieter": "o2",
            "tarif_id": slug,
            "tarif_name": name,
            "laufzeit_monate": 24,
            "abgerufen_am": TAG,
            "quelle_url": url,
        }

    ist = [
        bd("o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)"),
        bd(
            "o2-mobile-unlimited-m-mit-100-mbit-s-24-mon",
            "O2 Mobile Unlimited M mit 100 MBit/s (24 Mon.)",
        ),
    ]
    s = ga.Seite(
        "https://www.o2online.de/e-shop/smartphone/apple-iphone-17",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        tarife=[ga.Option("O2 Mobile S mit 15 GB+", "x")],
        laufzeiten=[ga.Option("24", "24")],
    )
    z = ga.Zaehlung("o2", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.tarifuebersicht = [ga.Option("O2 Mobile Unlimited M", "o2-mobile-unlimited-m")]
    ga.schreibe(tmp_path, z)
    sig = Signale()
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, sig)
    ein.haenge_ein(voll, tmp_path, TAG, ist, sig, katalog)
    k = next(x for x in voll["anbieter"] if x["name"] == "o2")["ebenen"][
        "kombinationen"
    ]
    assert [e["grund"] for e in k["nicht_verglichen"]] == [
        "anderer Kaufweg (Tarifübersicht), nicht gezählt"
    ]
    assert (k["soll"], k["erfasst"], k["nicht_im_soll_zahl"]) == (1, 1, 0), (
        k["soll"],
        k["erfasst"],
        k["nicht_im_soll_zahl"],
        [e["schluessel"] for e in k["nicht_im_soll"]],
    )


def test_o2_tarifuebersicht_ausgefallen_dann_keine_preise_ohne_angebot_behaupten(
    tmp_path, katalog
):
    """Die Tarifübersicht konnte nicht gelesen werden (benannter Ausfall). Die Ist-
    Bündel des zweiten Kaufwegs (Tarif 'Unlimited M') dürfen dann nicht als 'Preise
    ohne Angebot auf der Seite' gezählt werden: der Weg wurde nicht gelesen."""
    sku = "apple-iphone-17-256gb-schwarz"

    def bd(slug, name):
        return {
            "id": f"buendel--x--{sku}--{slug}--24m",
            "sku_id": sku,
            "anbieter": "o2",
            "tarif_id": slug,
            "tarif_name": name,
            "laufzeit_monate": 24,
            "abgerufen_am": TAG,
            "quelle_url": "https://www.o2online.de/e-shop/x?tarif=o2-mobile-unlimited-m",
        }

    ist = [
        bd("o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)"),
        bd(
            "o2-mobile-unlimited-m-mit-100-mbit-s-24-mon",
            "O2 Mobile Unlimited M mit 100 MBit/s (24 Mon.)",
        ),
    ]
    s = ga.Seite(
        "https://www.o2online.de/e-shop/smartphone/apple-iphone-17",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        tarife=[ga.Option("O2 Mobile S mit 15 GB+", "x")],
        laufzeiten=[ga.Option("24", "24")],
    )
    z = ga.Zaehlung("o2", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.tarifuebersicht = None
    z.tarifuebersicht_grund = "Tarifübersicht nicht gelesen: Timeout"
    ga.schreibe(tmp_path, z)
    sig = Signale()
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, sig)
    ein.haenge_ein(voll, tmp_path, TAG, ist, sig, katalog)
    k = next(x for x in voll["anbieter"] if x["name"] == "o2")["ebenen"][
        "kombinationen"
    ]
    assert k["nicht_im_soll_zahl"] == 0, (
        k["nicht_im_soll_zahl"],
        [e["grund"] for e in k["nicht_im_soll"]],
    )
