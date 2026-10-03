"""o2: jede Tarifstufe x Speicher x Ratenlaufzeit, nicht nur das Katalogbuendel.

WAS DER ALTE STAND LIEFERTE
---------------------------
Der Buendelkatalog nennt je Geraet EIN Buendel (ein Speicher, ein Tarif,
36 Raten). Im Bestand vom 29.09.2026 standen deshalb 61 aktuelle
o2-Buendel, 51 davon im selben Tarif, alle mit 36 Raten. Die Vertiefung
(`o2.vertiefe_buendel`) folgt den Schaltern der Produktseite und liefert
die ganze Auswahl.

DIE FIXTURES SIND GESPEICHERTE ECHTE ABRUFE (29.09.2026, TelcoRadar/1.0)
-------------------------------------------------------------------------
`o2_vertiefung_iphone17pro.json.gz`: der Katalogeintrag "Apple iPhone 17
Pro" aus dem Buendelkatalog und die 15 Antworten, die die Vertiefung von
dort aus abruft (Produktseite, 3 Speicher/Laufzeit-Schalter, 11 Tarife der
Referenz). Gekuerzt auf die gelesenen Felder, Werte unveraendert; Adresse,
Status, Groesse und sha256 jeder ungekuerzten Antwort stehen in der Datei
unter `herkunft`.
`o2_tarifdurchlauf_xiaomi17.json.gz`: 22 Konfigurationsantworten zu Xiaomi
17 512 GB, je Tarif und Laufzeit eine - das Geraet mit dem staerksten
geraeteabhaengigen Tarifrabatt (on Demand M Plus 8,49 statt 14,99 EUR).
"""

import copy
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete import GeraeteAbrufFehler, o2
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import HOCH

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent


def _lade(name):
    with gzip.open(_FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def mitschnitt():
    return _lade("o2_vertiefung_iphone17pro.json.gz")


@pytest.fixture(scope="module")
def xiaomi():
    return _lade("o2_tarifdurchlauf_xiaomi17.json.gz")["seiten"]


def _hole_aus(mitschnitt, protokoll=None):
    def hole(url):
        if protokoll is not None:
            protokoll.append(url)
        if url not in mitschnitt["antworten"]:
            raise GeraeteAbrufFehler("nicht im Mitschnitt", status=404)
        return mitschnitt["antworten"][url]

    return hole


def _katalogsaetze(mitschnitt):
    return o2.lies_buendel(json.dumps(mitschnitt["katalog"]))


def _vertieft(mitschnitt, weiter=None, zaehler=None):
    return o2.vertiefe_buendel(
        _hole_aus(mitschnitt), _katalogsaetze(mitschnitt), weiter, zaehler
    )


# --------------------------------------------------------------- Umfang


def test_zwoelf_tarife_zwei_speicher_zwei_laufzeiten(mitschnitt):
    saetze = _vertieft(mitschnitt)
    kombis = {(s["speicher_gb"], s["laufzeit_monate"], s["tarif_slug"]) for s in saetze}
    assert len(saetze) == len(kombis) == 48
    assert {s["speicher_gb"] for s in saetze} == {256, 512}
    assert {s["laufzeit_monate"] for s in saetze} == {24, 36}
    assert len({s["tarif_slug"] for s in saetze}) == 12
    # Gegenprobe: der alte Stand kannte genau ein Buendel fuer dieses Geraet.
    assert len(_katalogsaetze(mitschnitt)) == 1


def test_abrufe_je_geraet_und_nur_verlinkte_adressen(mitschnitt):
    protokoll = []
    o2.vertiefe_buendel(_hole_aus(mitschnitt, protokoll), _katalogsaetze(mitschnitt))
    # 1 Produktseite + 1 Speicher + 2 Laufzeitschalter + 11 Referenztarife
    assert len(protokoll) == 15
    assert all(u in mitschnitt["antworten"] for u in protokoll)
    assert all(u.startswith("https://www.o2online.de/") for u in protokoll)


def test_jeder_satz_traegt_seine_posten(mitschnitt):
    for s in _vertieft(mitschnitt):
        for feld in (
            "tarif_monatlich",
            "geraet_monatsrate",
            "geraet_zuzahlung",
            "anschlusspreis",
        ):
            assert isinstance(s[feld], float), (feld, s)
        assert s["tarif_name"] and s["tarif_slug"]
        assert s["url"].startswith("https://www.o2online.de/e-shop/")


# ------------------------------------------------ gemessene Einzelwerte


def _satz(saetze, speicher, laufzeit, slug):
    treffer = [
        s
        for s in saetze
        if (s["speicher_gb"], s["laufzeit_monate"], s["tarif_slug"])
        == (speicher, laufzeit, slug)
    ]
    assert len(treffer) == 1
    return treffer[0]


def test_iphone_17_pro_256_zwei_tarife_gegen_die_seite(mitschnitt):
    """Die Referenzantworten sind die Seiten genau dieser Kombination: ihre
    Preiszusammenfassung nennt Geraet mtl. 36,50, Tarif mtl. 39,99 (Unlimited
    L) bzw. 14,99 (Mobile S), Anzahlung 1,00, Anschluss 0,00 / 39,99."""
    saetze = _vertieft(mitschnitt)
    ul = _satz(saetze, 256, 36, "o2-mobile-unlimited-l")
    assert (
        ul["geraet_monatsrate"],
        ul["tarif_monatlich"],
        ul["geraet_zuzahlung"],
        ul["anschlusspreis"],
    ) == (36.5, 39.99, 1.0, 0.0)
    s = _satz(saetze, 256, 36, "o2-mobile-s")
    assert (s["tarif_monatlich"], s["anschlusspreis"]) == (14.99, 39.99)
    # 24 Raten: eigene Rate und eigene Anzahlung, derselbe Tarifbetrag
    s24 = _satz(saetze, 256, 24, "o2-mobile-unlimited-m-plus")
    assert (
        s24["geraet_monatsrate"],
        s24["geraet_zuzahlung"],
        s24["tarif_monatlich"],
    ) == (54.5, 7.0, 19.99)


def test_512_gb_hat_eigene_rate_und_anzahlung(mitschnitt):
    saetze = _vertieft(mitschnitt)
    s = _satz(saetze, 512, 36, "o2-mobile-unlimited-m-plus")
    assert (s["geraet_monatsrate"], s["geraet_zuzahlung"]) == (43.5, 25.0)
    assert (
        _satz(saetze, 256, 36, "o2-mobile-unlimited-m-plus")["geraet_monatsrate"]
        == 36.5
    )


# ---------------------------------------------------- die Ableitung


def test_abgeleiteter_tarifbetrag_trifft_die_messung(xiaomi):
    """Der Kernbefund, an 22 echten Antworten: fuer JEDEN Tarif T ist
    `monthlyCharges(T) - Geraeterate` aus einer beliebigen Antwort derselben
    Laufzeit genau der Tarifbetrag, den die Antwort MIT T ausgewaehlt misst
    - obwohl der Rabatt geraete- und laufzeitabhaengig ist (8,49 EUR)."""
    for laufzeit in (24, 36):
        seiten = [
            pv
            for pv in xiaomi
            if pv["hardware"]["offerName"].endswith(f"-{laufzeit}xhigh")
        ]
        assert len(seiten) >= 10
        referenz = o2.referenz_aus(seiten)
        assert referenz is not None
        gemessen = {}
        for pv in seiten:
            s = o2.saetze_aus_konfiguration(pv, {}, None, "u")[0]
            gemessen[s["tarif_slug"]] = s
        verglichen = 0
        for pv in seiten:
            for s in o2.saetze_aus_konfiguration(pv, {}, referenz, "u")[1:]:
                g = gemessen.get(s["tarif_slug"])
                if g is None:
                    continue
                verglichen += 1
                for feld in (
                    "tarif_monatlich",
                    "geraet_monatsrate",
                    "geraet_zuzahlung",
                    "anschlusspreis",
                    "tarif_name",
                ):
                    assert s[feld] == g[feld], (laufzeit, s["tarif_slug"], feld)
        assert verglichen > 80
    rabatt = [
        s
        for s in (o2.saetze_aus_konfiguration(pv, {}, None, "u")[0] for pv in xiaomi)
        if s["tarif_slug"] == "o2-mobile-on-demand-m-plus"
        and s["laufzeit_monate"] == 36
    ]
    assert rabatt and rabatt[0]["tarif_monatlich"] == 8.49


def test_tarifabhaengige_rate_verhindert_jede_ableitung(xiaomi):
    seiten = copy.deepcopy(
        [pv for pv in xiaomi if pv["hardware"]["offerName"].endswith("-36xhigh")]
    )
    # Eine Antwort mit anderer Rate, in sich stimmig (Probe geht auf).
    pv = seiten[1]
    attr = pv["ecommerceProductValue"]["attributes"]
    attr["metric3"] = str(float(attr["metric3"]) + 1)
    for o in pv["tariff"]["tariffOptions"]:
        if o.get("selected"):
            o["monthlyCharges"] = round(o["monthlyCharges"] + 1, 2)
    assert o2.referenz_aus(seiten) is None
    assert o2.referenz_aus(seiten[:1] + [None] + seiten[2:]) is None


def test_ohne_referenz_nur_der_gemessene_satz(mitschnitt):
    start = o2.lies_konfiguration(
        mitschnitt["antworten"][_katalogsaetze(mitschnitt)[0]["url"]]
    )
    assert len(o2.saetze_aus_konfiguration(start, {}, None, "u")) == 1


def test_widerspricht_die_antwort_der_referenz_wird_nicht_abgeleitet(mitschnitt):
    start = o2.lies_konfiguration(
        mitschnitt["antworten"][_katalogsaetze(mitschnitt)[0]["url"]]
    )
    anzeige = [
        o["displayValue"] for o in start["tariff"]["tariffOptions"] if o["selected"]
    ][0]
    from telco_radar.collect.geraete.o2 import _ohne_markup

    referenz = {
        _ohne_markup(o["displayValue"]): {"slug": "x", "anschluss": 0.0}
        for o in start["tariff"]["tariffOptions"]
    }
    referenz[_ohne_markup(anzeige)] = {
        "slug": "o2-mobile-unlimited-m-plus",
        "anschluss": 39.99,
    }
    z = {}
    assert len(o2.saetze_aus_konfiguration(start, {}, referenz, "u", z)) == 1
    assert z["referenz_widerspricht"] == 1


# ------------------------------------------------ Frist und Zusammenfuehren


def test_ohne_zeit_kein_abruf(mitschnitt):
    protokoll, z = [], {}
    tief = o2.vertiefe_buendel(
        _hole_aus(mitschnitt, protokoll), _katalogsaetze(mitschnitt), lambda: False, z
    )
    assert tief == [] and protokoll == [] and z["frist"] == 1


def test_katalogname_und_vertiefung_ergeben_dieselbe_buendel_id(mitschnitt):
    katalog = _katalogsaetze(mitschnitt)
    tief = _vertieft(mitschnitt)
    gleich = [
        s
        for s in tief
        if (s["angebot"], s["tarif_slug"])
        == (katalog[0]["angebot"], katalog[0]["tarif_slug"])
    ]
    assert len(gleich) == 1
    assert gleich[0]["tarif_name"] == katalog[0]["tarif_name"]
    for feld in (
        "tarif_monatlich",
        "geraet_monatsrate",
        "geraet_zuzahlung",
        "anschlusspreis",
        "laufzeit_monate",
    ):
        assert gleich[0][feld] == katalog[0][feld], feld
    zusammen = o2.fuehre_zusammen(katalog, tief)
    assert len(zusammen) == 48
    assert zusammen[0] is katalog[0]


def test_der_sammler_vertieft_und_vergibt_die_sku(mitschnitt):
    from telco_radar.collect.geraete import sammle_anbieter
    from telco_radar.collect.geraete.robots import RobotsWaechter
    from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog

    katalog_url = (
        "https://www.o2online.de/e-shop/rest/catalog/o2shop/"
        "privatkunden/ratenzahlung/default/__not-specified__/"
        "__not-specified__/__not-specified__"
    )
    antworten = dict(mitschnitt["antworten"])
    antworten[katalog_url] = json.dumps(mitschnitt["katalog"])

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /postpaid/\n")
        if url not in antworten:
            return (404, "")
        return (200, antworten[url])

    anbieter = Anbieter(
        name="o2",
        typ="netzbetreiber",
        methode="o2_katalog",
        basis_url="https://www.o2online.de",
        rate_limit_sekunden=0,
        kopfzeilen={"Accept": "application/vnd.commerce.message+json"},
        einstiege=[Einstieg(url=katalog_url, kind="buendel")],
    )
    bilanz = sammle_anbieter(
        anbieter,
        lade_katalog(lese_wurzel()),
        lade_farben(_WURZEL),
        hole,
        "2026-09-29",
        RobotsWaechter(hole=hole),
        datetime(2026, 9, 29, 3, tzinfo=UTC),
    )
    assert len(bilanz.buendel) == 48
    skus = {b["sku_id"] for b in bilanz.buendel}
    assert len(skus) == 2
    assert any("256gb" in s for s in skus) and any("512gb" in s for s in skus)
    assert all(b["anbieter"] == "o2" for b in bilanz.buendel)


# ------------------------------------------------ iPhone 18 Pro: TB, Tracking


def test_terabyte_bekommt_eigenen_speicher():
    """Vor dem Fix fielen 1 TB und 2 TB beide auf `speicher_gb=None` -
    zwei Preise auf einer sku_id `...-ohne-speicher-ohne-farbe`."""
    m = _lade("o2_vertiefung_iphone18pro.json.gz")
    saetze = _vertieft(m)
    assert {s["speicher_gb"] for s in saetze} == {256, 512, 1024, 2048}
    assert len(saetze) == 4 * 2 * 7
    s = _satz(saetze, 2048, 36, "o2-mobile-unlimited-m")
    assert (s["geraet_monatsrate"], s["tarif_monatlich"]) == (89.0, 24.99)


def test_die_preiszusammenfassung_schlaegt_den_trackingblock():
    """iPhone 18 Pro 256 GB, 24 Raten: metric2 sagt 34,99, die Seite
    'Tarif mtl. 24,99' - und nur 65,00 + 24,99 ergibt die typisierte
    Summe 89,99. Vorher fiel die Antwort ganz heraus (Probe gegen metric2)."""
    m = _lade("o2_vertiefung_iphone18pro.json.gz")
    seite = [
        o2.lies_konfiguration(t)
        for t in m["antworten"].values()
        if "256gb-burgunder-24xhigh" in t and '"metric2": "34.99"' in t
    ]
    assert seite, "der Widerspruchsfall fehlt in der Fixture"
    s = o2.saetze_aus_konfiguration(seite[0], {}, None, "u")
    assert len(s) == 1
    assert (
        s[0]["geraet_monatsrate"],
        s[0]["tarif_monatlich"],
        s[0]["laufzeit_monate"],
    ) == (65.0, 24.99, 24)


# ------------------------------------------------ Tarifbezug


def _bestand():
    zeile = dict(anbieter="o2", preistyp="live_shop", abgerufen_am="2026-09-29")
    return Tarifbestand(
        [
            {
                **zeile,
                "tarif_id": "o2:o2-mobile-unlimited-m",
                "name": "O2 Mobile Unlimited M",
                "grundgebuehr": 29.99,
                "buendel_slug": "o2-mobile-unlimited-m-plus",
            },
            {
                **zeile,
                "tarif_id": "o2:o2-mobile-unlimited-l",
                "name": "O2 Mobile Unlimited L",
                "grundgebuehr": 39.99,
                "buendel_slug": "o2-mobile-unlimited-l",
            },
            {
                **zeile,
                "tarif_id": "o2:o2-mobile-on-demand-m",
                "name": "O2 Mobile on Demand M",
                "grundgebuehr": 19.99,
                "buendel_slug": "o2-mobile-on-demand-m-plus",
            },
        ]
    )


def test_der_tarif_ohne_plus_loest_ueber_seine_tarif_id_auf():
    """Log vom 29.09.2026: "O2 Mobile on Demand M mit 50 GB+ (24 Mon.)" (7x)
    und "O2 Mobile Unlimited M mit 100 MBit/s (24 Mon.)" (2x) verworfen."""
    b = _bestand()
    for name, slug, ziel in (
        (
            "O2 Mobile on Demand M mit 50 GB+ (24 Mon.)",
            "o2-mobile-on-demand-m",
            "o2:o2-mobile-on-demand-m",
        ),
        (
            "O2 Mobile Unlimited M mit 100 MBit/s (24 Mon.)",
            "o2-mobile-unlimited-m",
            "o2:o2-mobile-unlimited-m",
        ),
    ):
        bezug = b.loese("o2", name, slug=slug)
        assert bezug is not None and bezug.tarif_id == ziel
        assert bezug.guete == HOCH


def test_plus_wird_nie_auf_den_tarif_ohne_plus_geraten():
    b = _bestand()
    assert (
        b.loese(
            "o2",
            "O2 Mobile Unlimited L Plus mit 300 MBit/s (24 Mon.)",
            slug="o2-mobile-unlimited-l-plus",
        )
        is None
    )
    assert b.loese("o2", "x", slug="o2-mobile-unlimited") is None
    # Der Kachel-Slug bleibt der staerkere Weg
    bezug = b.loese("o2", "x", slug="o2-mobile-unlimited-m-plus")
    assert bezug.tarif_id == "o2:o2-mobile-unlimited-m"
    assert "SIM-only-Kachel" in bezug.grund


def test_der_slugweg_gilt_nur_im_eigenen_anbieter():
    assert _bestand().loese("Telekom", "x", slug="o2-mobile-unlimited-m") is None
