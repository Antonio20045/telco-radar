"""Reproduktionen des Prüfers zu PR 205, Runde 5 (``/tmp/pruefer/k205d``), übernommen;
gegen den Stand ``9ae52d80a`` rot. Dazu: ein Karussell, dessen „Weiter“ noch aktiv
ist, ergibt eine teilweise gelesene Auswahl; nicht verglichene Preise verbieten
„vollständig“; eine Teilzählung trägt die Marke „Teilzählung“."""

from __future__ import annotations

import test_geraete_angebot as base

from telco_radar import geraete_angebot as ga
from telco_radar import geraete_lauf
from telco_radar.geraete_angebot import einhaengen as ein
from telco_radar.geraete_angebot import wege
from telco_radar.geraete_vollstaendigkeit import Signale, baue
from telco_radar.report import geraete_vollstaendigkeit as seite

TAG = base.TAG
T_NETZ = "Saturn/MediaMarkt · Telekom-Netz"
O_NETZ = "Saturn/MediaMarkt · o2-Netz"
SKU = "apple-iphone-17-256gb-schwarz"


def _katalog():
    return base.Katalog(geraete=[base.Geraet("Apple", "iPhone 17")])


def _b(sku, slug, name, laufzeit=24, anbieter="o2"):
    return {
        "id": f"buendel--x--{sku}--{slug}--{laufzeit}m",
        "sku_id": sku,
        "anbieter": anbieter,
        "tarif_id": slug,
        "tarif_name": name,
        "laufzeit_monate": laufzeit,
        "abgerufen_am": TAG,
        "quelle_url": "https://www.o2online.de/e-shop/x?tarif=o2-mobile-unlimited-m",
    }


def _lauf(tmp_path, z, ist, name):
    ga.schreibe(tmp_path, z)
    sig = Signale()
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, sig)
    ein.haenge_ein(voll, tmp_path, TAG, ist, sig, _katalog())
    voll["datum"] = TAG
    zeile = next(x for x in voll["anbieter"] if x["name"] == name)
    return voll, zeile


def test_andere_variante_eines_angebotenen_tarifs_ist_kein_anderer_kaufweg(
    tmp_path,
):
    """Die Produktseite bietet 'O2 Mobile Unlimited M Plus mit 100 MBit/s'. Gemessen
    ist auch die Variante 'mit 50 MBit/s', die die Seite nicht anbietet. Das ist ein
    Preis, den o2 so nicht anbietet (Wächter-relevant), kein 'anderer Kaufweg': der
    Tarif steht ja auf der Produktseite."""
    s = ga.Seite(
        "https://www.o2online.de/e-shop/apple/apple-iphone-17-256gb-schwarz-details",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        kombinationen=[["256 GB", "O2 Mobile Unlimited M Plus mit 100 MBit/s", 24]],
    )
    z = ga.Zaehlung("o2", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.tarifuebersicht = [
        ga.Option("O2 Mobile Unlimited M Plus", "o2-mobile-unlimited-m-plus")
    ]
    ist = [
        _b(
            SKU,
            "o2-mobile-unlimited-m-plus-mit-100-mbit-s-24-mon",
            "O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)",
        ),
        _b(
            SKU,
            "o2-mobile-unlimited-m-plus-mit-50-mbit-s-24-mon",
            "O2 Mobile Unlimited M Plus mit 50 MBit/s (24 Mon.)",
        ),
    ]
    voll, zeile = _lauf(tmp_path, z, ist, "o2")
    k = zeile["ebenen"]["kombinationen"]
    gruende = {e["grund"] for e in k["nicht_verglichen"]}
    assert "anderer Kaufweg (Tarifübersicht), nicht gezählt" not in gruende, (
        k["nicht_verglichen"],
        k["nicht_im_soll"],
    )
    assert k["nicht_im_soll_zahl"] == 1


def _tw_seite(unvoll):
    return ga.Seite(
        "https://tarife.mediamarkt.de/smartphones/apple/iphone-17/",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        kombinationen=[["256 GB", "Mobile Unlimited L", 24, "o2", "1-59.99"]],
        unvollstaendig=unvoll,
    )


def test_tarifwelt_netz_klick_gescheitert_zeile_ohne_kombis_nicht_vollstaendig(
    tmp_path,
):
    """Netzfilter 'telekom' ließ sich nicht klicken (seite.unvollstaendig). Die
    Telekom-Netz-Zeile hat deshalb keine Kombinationen; sie darf nicht als 'Soll 0
    gezählt, Gerät gezählt, vollständig' erscheinen."""
    s = _tw_seite(
        [
            "256 GB, Netz telekom: Option „256 GB, Netz telekom“ ließ sich nicht "
            "wählen, nicht gelesen"
        ]
    )
    z = ga.Zaehlung("tarifwelt", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.uebersicht_ende = "Seite ohne Nachlade-Knopf, ganz gescrollt"
    z.konkurrenz = "keine parallelen Läufe auf diesem Host"
    voll, zeile = _lauf(tmp_path, z, [], T_NETZ)
    v = geraete_lauf.vorbehalte(zeile)
    assert v, (
        "Telekom-Netz ohne jeden Vorbehalt trotz gescheitertem Netzklick: "
        f"angebot={zeile['angebot']}"
    )
    assert (
        zeile["angebot"]["geraete"]["gezaehlt"] == 0
        or zeile["angebot"]["unvollstaendig"]
    )


def test_tarifwelt_netz_klick_gescheitert_marke_nicht_vollstaendig(tmp_path):
    """Dieselbe Lage, an der Anzeige: die Zeile der Telekom-Netz-Zeile darf nicht
    'vollständig' tragen."""
    s = _tw_seite(
        [
            "256 GB, Netz telekom: Option „256 GB, Netz telekom“ ließ sich nicht "
            "wählen, nicht gelesen"
        ]
    )
    z = ga.Zaehlung("tarifwelt", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.uebersicht_ende = "Seite ohne Nachlade-Knopf, ganz gescrollt"
    z.konkurrenz = "keine parallelen Läufe auf diesem Host"
    voll, zeile = _lauf(tmp_path, z, [], T_NETZ)
    row = next(
        x
        for x in seite.zeilen({"vollstaendigkeit": voll}, TAG)["zeilen"]
        if x["name"] == T_NETZ
    )
    assert "vollständig" not in row["marke"], (row["satz"], row["marke"])


def test_gescheiterter_speicherklick_wird_nicht_als_speicher_nicht_in_auswahl_benannt(
    tmp_path,
):
    s = ga.Seite(
        "https://www.o2online.de/e-shop/apple/apple-iphone-17-256gb-schwarz-details",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB"), ga.Option("512 GB", "512 GB")],
        kombinationen=[["256 GB", "O2 Mobile S mit 15 GB+", 24]],
        unvollstaendig=["Option „512 GB“ ließ sich nicht wählen, nicht gelesen"],
    )
    z = ga.Zaehlung("o2", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.tarifuebersicht = []
    z.uebersicht_ende = "Seite ohne Nachlade-Knopf, ganz gescrollt"
    z.konkurrenz = "keine parallelen Läufe auf diesem Host"
    s512 = "apple-iphone-17-512gb-schwarz"
    ist = [
        _b(SKU, "o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)"),
        _b(s512, "o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)"),
    ]
    voll, zeile = _lauf(tmp_path, z, ist, "o2")
    k = zeile["ebenen"]["kombinationen"]
    assert {e["grund"] for e in k["nicht_im_soll"]} == set(), k["nicht_im_soll"]
    assert geraete_lauf.vorbehalte(zeile)
    assert zeile["angebot"]["geraete"]["gezaehlt"] == 0


class _Knopf:
    def __init__(self, aktiv):
        self.aktiv, self.klicks = aktiv, 0

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def is_enabled(self):
        return self.aktiv

    def click(self):
        self.klicks += 1


class _Seite:
    def __init__(self, knopf):
        self.knopf = knopf

    def locator(self, selektor):
        return self

    @property
    def first(self):
        return self

    def get_by_role(self, rolle, name):
        return self.knopf

    def wait_for_timeout(self, ms):
        return None


class _Sitzung:
    def __init__(self, aktiv):
        self.page = _Seite(_Knopf(aktiv))
        self.tor = self

    def passiere(self, url):
        return None

    def oeffne(self, url):
        return None

    def html(self, name):
        return base._html("o2_galaxy_s26")

    def waehle_radio(self, name, wert, warte_ms=0):
        return True


def test_karussell_mit_aktivem_weiter_ist_nur_teilweise_gelesen():
    """Fünf Kacheln im DOM (Morgen-Schnappschuss) und ein „Weiter“, das nie endet: die
    Auswahl ist nicht vollständig gelesen; endet das Karussell, ist sie es."""
    offen = ga.Seite("https://www.o2online.de/e-shop/x", "Samsung Galaxy S26")
    sitzung = _Sitzung(aktiv=True)
    wege.o2(sitzung, offen)
    assert sitzung.page.knopf.klicks == wege.KARUSSELL_HOECHSTENS
    assert "Tarifkarussell nicht bis zum Ende gelesen" in offen.unvollstaendig
    fertig = ga.Seite("https://www.o2online.de/e-shop/x", "Samsung Galaxy S26")
    wege.o2(_Sitzung(aktiv=False), fertig)
    assert not [u for u in fertig.unvollstaendig if "Karussell" in u]


def test_nicht_verglichene_preise_und_teilzaehlung_verbieten_vollstaendig(tmp_path):
    s = ga.Seite(
        "https://www.o2online.de/e-shop/apple/apple-iphone-17-256gb-schwarz-details",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        kombinationen=[["256 GB", "O2 Mobile S mit 15 GB+", 24]],
        unvollstaendig=["Tarifkarussell nicht bis zum Ende gelesen"],
    )
    z = ga.Zaehlung("o2", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.uebersicht_ende = "Seite ohne Nachlade-Knopf, ganz gescrollt"
    z.konkurrenz = "keine parallelen Läufe auf diesem Host"
    ist = [
        _b(SKU, "o2-mobile-s-mit-15-gb-24-mon", "O2 Mobile S mit 15 GB+ (24 Mon.)"),
        _b(SKU, "o2-mobile-l-mit-150-gb-24-mon", "O2 Mobile L mit 150 GB+ (24 Mon.)"),
    ]
    voll, zeile = _lauf(tmp_path, z, ist, "o2")
    k = zeile["ebenen"]["kombinationen"]
    assert (k["nicht_im_soll_zahl"], k["nicht_verglichen_zahl"]) == (0, 1)
    row = next(
        x
        for x in seite.zeilen({"vollstaendigkeit": voll}, TAG)["zeilen"]
        if x["name"] == "o2"
    )
    assert "vollständig" not in row["marke"]
    assert row["marke"].startswith("Teilzählung")
    assert "Preise nicht verglichen" in geraete_lauf.vorbehalte(zeile)
