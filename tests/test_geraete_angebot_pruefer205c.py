"""Reproduktionen des Prüfers zu PR 205, Runde 4 (``/tmp/pruefer/k205c``),
übernommen; gegen den Stand ``efd265726`` rot. Soll allein aus der Produktseite,
gescheiterte Klicks und ungelesene Zweitseiten machen die Auswahl „teilweise“,
nicht verglichene Preise verbieten „vollständig“."""

from __future__ import annotations

import pytest
import test_geraete_angebot as base

from telco_radar import geraete_angebot as ga
from telco_radar.geraete_angebot import einhaengen as ein
from telco_radar.geraete_angebot import wege
from telco_radar.geraete_vollstaendigkeit import Signale, baue
from telco_radar.report import geraete_vollstaendigkeit as seite

TAG = base.TAG


@pytest.fixture
def katalog():
    return base.Katalog(geraete=[base.Geraet("Apple", "iPhone 17")])


def _bd(sku, slug, name, laufzeit=24):
    return {
        "id": f"buendel--x--{sku}--{slug}--{laufzeit}m",
        "sku_id": sku,
        "anbieter": "o2",
        "tarif_id": slug,
        "tarif_name": name,
        "laufzeit_monate": laufzeit,
        "abgerufen_am": TAG,
        "quelle_url": "https://www.o2online.de/e-shop/x?tarif=o2-mobile-unlimited-m",
    }


def _o2(
    tmp_path, ist, katalog, karten, speicher=("256 GB",), laufzeiten=("24",), unvoll=()
):
    s = ga.Seite(
        "https://www.o2online.de/e-shop/smartphone/apple-iphone-17",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option(x, x) for x in speicher],
        tarife=[ga.Option("O2 Mobile S mit 15 GB+", "x")],
        laufzeiten=[ga.Option(x, x) for x in laufzeiten],
        unvollstaendig=list(unvoll),
    )
    z = ga.Zaehlung("o2", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.tarifuebersicht = karten
    ga.schreibe(tmp_path, z)
    sig = Signale()
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, sig)
    ein.haenge_ein(voll, tmp_path, TAG, ist, sig, katalog)
    zeile = next(x for x in voll["anbieter"] if x["name"] == "o2")
    voll["datum"] = TAG
    row = next(
        x
        for x in seite.zeilen({"vollstaendigkeit": voll}, TAG)["zeilen"]
        if x["name"] == "o2"
    )
    return zeile["ebenen"]["kombinationen"], row


def test_zweiter_kaufweg_haengt_ist_nicht_ins_soll_der_angebotszahl(tmp_path, katalog):
    """Die Produktseite nennt genau 1 Kombination (iPhone 17 / 256 GB / S / 24).
    Unlimited M steht nur in der Tarifübersicht; im Ist hat es vier Bündel (256/512
    GB x 24/36). Soll der Angebotszahl ist die unabhängig gezählte Produktseite = 1;
    die vier Bündel des zweiten Wegs sind Ist, kein Soll (sonst ist y aus dem
    Sammler abgeleitet)."""
    s256 = "apple-iphone-17-256gb-schwarz"
    s512 = "apple-iphone-17-512gb-schwarz"
    ist = [
        _bd(s256, "o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)")
    ]
    for sku in (s256, s512):
        for m in (24, 36):
            ist.append(
                _bd(
                    sku,
                    "o2-mobile-unlimited-m-mit-100-mbit-s-24-mon",
                    "O2 Mobile Unlimited M mit 100 MBit/s (24 Mon.)",
                    m,
                )
            )
    k, row = _o2(
        tmp_path,
        ist,
        katalog,
        [ga.Option("O2 Mobile Unlimited M", "o2-mobile-unlimited-m")],
    )
    assert (k["soll"], k["erfasst"]) == (1, 1), (
        f"Soll {k['soll']} / erfasst {k['erfasst']}: "
        "Ist des zweiten Kaufwegs wird als Soll gezählt; "
        f"Zeile: {row['satz']} | {row['marke']}"
    )


def test_o2_unlimited_m_ohne_plus_ist_nicht_unlimited_m_plus(tmp_path, katalog):
    """Kachel 'Unlimited M Plus' (Slug ...-plus) bestätigt NICHT 'Unlimited M' ohne
    Plus."""
    sku = "apple-iphone-17-256gb-schwarz"
    ist = [
        _bd(sku, "o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)"),
        _bd(
            sku,
            "o2-mobile-unlimited-m-mit-100-mbit-s-24-mon",
            "O2 Mobile Unlimited M mit 100 MBit/s (24 Mon.)",
        ),
    ]
    k, _ = _o2(
        tmp_path,
        ist,
        katalog,
        [ga.Option("O2 Mobile Unlimited M Plus", "o2-mobile-unlimited-m-plus")],
    )
    assert k["nicht_im_soll_zahl"] == 1


def test_mehrere_kacheln_passen_ist_nicht_eindeutig(tmp_path, katalog):
    sku = "apple-iphone-17-256gb-schwarz"
    ist = [
        _bd(sku, "o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)"),
        _bd(
            sku,
            "o2-mobile-unlimited-m-mit-100-mbit-s-24-mon",
            "O2 Mobile Unlimited M mit 100 MBit/s (24 Mon.)",
        ),
    ]
    karten = [
        ga.Option("O2 Mobile Unlimited M", "a"),
        ga.Option("O2 Mobile Unlimited M mit 100 MBit/s", "b"),
    ]
    k, _ = _o2(tmp_path, ist, katalog, karten)
    assert k["nicht_im_soll_zahl"] == 0
    assert k["erfasst"] == 1, k["erfasst"]
    assert k["nicht_verglichen_zahl"] == 1, k.get("nicht_verglichen_zahl")


def test_teilweise_gelesene_auswahl_zaehlt_nicht(tmp_path, katalog):
    """Seite gelesen, aber 'unvollstaendig' vermerkt: kein Preis darf 'nicht angeboten'
    sein."""
    sku = "apple-iphone-17-256gb-schwarz"
    ist = [
        _bd(sku, "o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)"),
        _bd(sku, "o2-mobile-l-mit-150-gb-24-mon", "O2 Mobile L mit 150 GB+ (24 Mon.)"),
    ]
    k, row = _o2(
        tmp_path,
        ist,
        katalog,
        [ga.Option("O2 Mobile Unlimited L", "o2-mobile-unlimited-l")],
        unvoll=["Seite nennt 6 Tarife, gelesen 1"],
    )
    assert k["nicht_im_soll_zahl"] == 0, row["marke"]


class _Tor:
    def passiere(self, url):
        pass


class _Sitzung:
    """Stand-in: Produktseite mit 256 und 512 GB; der Klick auf 512 GB scheitert."""

    def __init__(self):
        self.tor = _Tor()

    def oeffne(self, url):
        pass

    def html(self, name):
        return base._html("o2_galaxy_s26")

    def waehle_radio(self, name, wert, warte_ms=0):
        return False


def test_gescheiterter_speicherklick_macht_aus_dem_preis_kein_nicht_angeboten(tmp_path):
    """o2-Produktseite zeigt 256 und 512 GB wählbar; der Klick auf 512 GB scheitert
    (waehle_radio False). Die Auswahl ist dann nur teilweise gelesen: Preise für 512
    GB dürfen nicht als 'vom Anbieter so nicht angeboten' zählen."""
    seite = ga.Seite(
        "https://www.o2online.de/e-shop/samsung/galaxy-s26",
        "Samsung Galaxy S26",
        status=ga.GELESEN,
    )
    wege.o2(_Sitzung(), seite)
    assert [o.text for o in seite.speicher] == ["256 GB", "512 GB"]
    kat = base.Katalog(geraete=[base.Geraet("Samsung", "Galaxy S26")])
    z = ga.Zaehlung("o2", TAG, f"{TAG}T23:10:00+00:00", seiten=[seite], genannt=1)
    z.kacheln = [ga.Kachel(seite.url, seite.titel)]
    z.tarifuebersicht = [ga.Option("O2 Mobile Unlimited L", "o2-mobile-unlimited-l")]
    ga.schreibe(tmp_path, z)
    tarife = [t.text for t in seite.tarife if t.waehlbar]
    ist = []
    for sku, _sp in (
        ("samsung-galaxy-s26-256gb-x", "256"),
        ("samsung-galaxy-s26-512gb-x", "512"),
    ):
        for t in tarife:
            name = t
            slug = "".join(c if c.isalnum() else "-" for c in t.lower())
            ist.append(
                {
                    "id": f"buendel--x--{sku}--{slug}--24m",
                    "sku_id": sku,
                    "anbieter": "o2",
                    "tarif_id": slug,
                    "tarif_name": name,
                    "laufzeit_monate": 24,
                    "abgerufen_am": TAG,
                    "quelle_url": "https://www.o2online.de/e-shop/x",
                }
            )
    sig = Signale()
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, sig)
    ein.haenge_ein(voll, tmp_path, TAG, ist, sig, kat)
    k = next(x for x in voll["anbieter"] if x["name"] == "o2")["ebenen"][
        "kombinationen"
    ]
    ohne512 = [
        e["schluessel"] for e in k["nicht_im_soll"] if "512gb" in e["schluessel"]
    ]
    assert not ohne512, (
        f"{len(ohne512)} Preise (512 GB) als 'nicht angeboten', "
        "obwohl 512 GB nie gelesen wurde "
        f"(Seite.unvollstaendig={seite.unvollstaendig})"
    )


def test_zweite_seite_desselben_geraets_nicht_gelesen_dann_kein_nicht_angeboten(
    tmp_path,
):
    """Saturn/MediaMarkt hat je Gerät zwei Seiten (…/iphone-17/ und
    …/iphone-17-aktion/). Die Aktionsseite wurde nicht gelesen (benannter Grund);
    die Normalseite schon. Ein Preis, den nur die Aktionsseite führen kann, darf
    nicht als 'vom Anbieter so nicht angeboten' zählen, und das Gerät ist nicht
    'vollständig' gezählt."""
    T = "Saturn/MediaMarkt · Telekom-Netz"
    sku = "apple-iphone-17-256gb-schwarz"
    kat = base.Katalog(geraete=[base.Geraet("Apple", "iPhone 17")])
    normal = ga.Seite(
        "https://tarife.mediamarkt.de/smartphones/apple/iphone-17/",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        kombinationen=[["256 GB", "Magenta Mobil XL 5G", 24, "telekom"]],
    )
    aktion = ga.Seite(
        "https://tarife.mediamarkt.de/smartphones/apple/iphone-17-aktion/",
        "Apple iPhone 17 Aktion",
        status=ga.NICHT_GELESEN,
        grund="Timeout",
    )
    z = ga.Zaehlung(
        "tarifwelt", TAG, f"{TAG}T23:10:00+00:00", seiten=[normal, aktion], genannt=2
    )
    z.kacheln = [
        ga.Kachel(normal.url, normal.titel),
        ga.Kachel(aktion.url, aktion.titel),
    ]
    ga.schreibe(tmp_path, z)
    ist = [
        _bd(sku, "magenta-mobil-xl-5g", "Magenta Mobil XL 5G"),
        _bd(sku, "magenta-mobil-m-5g-aktion-xyz", "Magenta Mobil M 5G"),
    ]
    for b in ist:
        b["anbieter"] = T
    sig = Signale()
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, sig)
    ein.haenge_ein(voll, tmp_path, TAG, ist, sig, kat)
    zeile = next(x for x in voll["anbieter"] if x["name"] == T)
    k = zeile["ebenen"]["kombinationen"]
    voll["datum"] = TAG
    row = next(
        x
        for x in seite.zeilen({"vollstaendigkeit": voll}, TAG)["zeilen"]
        if x["name"] == T
    )
    assert k["nicht_im_soll_zahl"] == 0, (
        f"{k['nicht_im_soll_zahl']} Preise 'nicht angeboten', "
        "obwohl die zweite Seite des Geräts nicht gelesen wurde; "
        f"Zeile: {row['satz']} | {row['marke']}"
    )


def test_nicht_verglichene_preise_verbieten_vollstaendig(tmp_path, katalog):
    """Kachel-Zuordnung nicht eindeutig: 1 Preis ist 'nicht verglichen'. Die Zeile darf
    dann nicht 'vollständig' heißen (alle Geräte gezählt, erfasst = Soll, aber ein
    Preis ungeprüft)."""
    sku = "apple-iphone-17-256gb-schwarz"
    ist = [
        _bd(sku, "o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)"),
        _bd(
            sku,
            "o2-mobile-unlimited-m-mit-100-mbit-s-24-mon",
            "O2 Mobile Unlimited M mit 100 MBit/s (24 Mon.)",
        ),
    ]
    karten = [
        ga.Option("O2 Mobile Unlimited M", "a"),
        ga.Option("O2 Mobile Unlimited M mit 100 MBit/s", "b"),
    ]
    k, row = _o2(tmp_path, ist, katalog, karten)
    assert k["nicht_verglichen_zahl"] == 1
    assert "vollständig" not in row["marke"], row["marke"]
