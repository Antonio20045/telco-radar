"""Der Geraete-Collector: Linkernte, strukturierte Daten, Zeitbudget.

Das Parsen anbieterbezogener Seiten laeuft gegen echte Abrufe mit Eintrag in
tests/fixtures/geraete/_herkunft.json (congstar JSON-LD, smartmobil
Microdata, EDEKA smart products.json, congstar-Sitemap, klarmobil-
Kategorieseite). Die Crawler-Mechanik laeuft gegen sichtbar konstruierte
Seiten unter der neutralen Domain haendler.test. Kein Test fasst das Netz an.
"""

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest

from telco_radar.collect.geraete import (
    GeraeteAbrufFehler,
    ernte_links,
    produkte_aus_shopify,
    sammle,
    sammle_anbieter,
)
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.collect.geraete.strukturdaten import (
    ist_lockpreis,
    lies_preis,
    produkte_aus_html,
    produkte_aus_ldjson,
    produkte_aus_microdata,
    verfuegbarkeit_aus_schema,
)
from telco_radar.geraete_config import Anbieter, Einstieg, QuellenConfig
from telco_radar.geraete_model import Geraet, Katalog

_FIX = Path(__file__).parent / "fixtures" / "geraete"


def _echt(name: str) -> str:
    """Ein echter Abruf aus tests/fixtures/geraete/ (gzip wird entpackt)."""
    roh = (_FIX / name).read_bytes()
    if name.endswith(".gz"):
        roh = gzip.decompress(roh)
    return roh.decode("utf-8")


def _herkunft_url(name: str) -> str:
    eintraege = json.loads((_FIX / "_herkunft.json").read_text(encoding="utf-8"))
    return next(e["url"] for e in eintraege["eintraege"] if e["datei"] == name)


def _ldjson_seite(name: str, preis: str, farbe: str = "", waehrung: str = "EUR") -> str:
    """Eine konstruierte Produktseite mit genau einem Product-Knoten."""
    produkt = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "offers": {
            "@type": "Offer",
            "priceCurrency": waehrung,
            "price": preis,
            "availability": "http://schema.org/InStock",
        },
    }
    if farbe:
        produkt["color"] = farbe
    return (
        '<html><head><script type="application/ld+json">'
        f"{json.dumps(produkt)}</script></head><body></body></html>"
    )


_BASIS = "https://www.haendler.test"
_EINSTIEG = f"{_BASIS}/c/116/smartphones"
_KATEGORIE = """<!doctype html><html lang="de"><head><title>Smartphones</title></head>
<body><nav><a href="/cart">Warenkorb</a><a href="/my-account">Konto</a></nav>
<ul>
  <li><a href="/p/1518897/galaxy-a57-5g-128gb">Galaxy A57 5G 128GB</a></li>
  <li><a href="/p/1514136/iphone-17-pro-max-256gb">iPhone 17 Pro Max 256GB</a></li>
  <li><a href="/p/1514200/huelle-iphone-17">Schutzhuelle fuer iPhone 17 Pro Max</a></li>
  <li><a href="https://www.anderer-laden.test/p/1/etwas">Fremder Shop</a></li>
  <li><a href="/c/117/tablets">Tablets</a></li>
</ul></body></html>"""
_IPHONE_SEITE = _ldjson_seite(
    "Apple iPhone 17 Pro Max 256GB Titannatur", "1449.00", "Titannatur"
)
_A57_SEITE = _ldjson_seite("Samsung Galaxy A57 5G 128GB Blau", "349.00", "Blau")
_PRODUKT_MIT_VARIANTEN = """<html><head>
<script type="application/ld+json">{"@type":"BreadcrumbList"}</script>
<script type="application/ld+json">
{"@type":"Product","name":"Google Pixel 10 Pro","color":"Obsidian",
 "offers":{"@type":"Offer","priceCurrency":"EUR","price":"1099",
           "availability":"http://schema.org/InStock"},
 "isSimilarTo":[
  {"@type":"Product","name":"Google Pixel 10 Pro 256 GB","color":"Porcelain",
   "offers":{"@type":"Offer","priceCurrency":"EUR","price":"1199",
             "availability":"http://schema.org/InStock"}},
  {"@type":"Product","name":"Google Pixel 10 Pro 128 GB","color":"Moonstone",
   "offers":{"@type":"Offer","priceCurrency":"EUR","price":"1099",
             "availability":"http://schema.org/OutOfStock"}}]}
</script></head><body></body></html>"""


_KATALOG = Katalog(
    geraete=[
        Geraet(
            hersteller="Apple",
            modell="iPhone 17 Pro Max",
            generation=17,
            speicher=[256, 512, 1024],
            segment="flagship",
        ),
        Geraet(
            hersteller="Samsung",
            modell="Galaxy A57",
            generation=57,
            speicher=[128, 256],
            segment="mid",
        ),
        Geraet(
            hersteller="Google",
            modell="Pixel 10 Pro",
            generation=10,
            speicher=[128, 256],
            segment="flagship",
        ),
        Geraet(
            hersteller="Motorola",
            modell="Motorola moto g85",
            generation=85,
            speicher=[128, 256],
            segment="mid",
        ),
    ]
)
_FARBEN = {
    "titannatur": "titan-natur",
    "blau": "blau",
    "obsidian": "schwarz",
    "porcelain": "weiss",
    "moonstone": "grau",
}


def _jetzt(stunde=3):
    return datetime(2026, 8, 11, stunde, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Preise lesen
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "roh,erwartet",
    [
        ("1449.00", 1449.0),
        (1099, 1099.0),
        ("1099", 1099.0),
        ("1.099,00", 1099.0),
        ("1.099", 1099.0),
        ("189,99", 189.99),
        ("1.234.567,89", 1234567.89 if False else None),  # ueber der Obergrenze
        ("349,00 €", 349.0),
        ("", None),
        (None, None),
        ("kostenlos", None),
        ("0", None),
        ("-5", None),
    ],
)
def test_preisformate(roh, erwartet):
    assert lies_preis(roh) == erwartet


def test_deutscher_tausenderpunkt_wird_nicht_zum_dezimaltrenner():
    """ "1.099" ist 1099 Euro und nicht 1,099 Euro - der Fehler, der einen
    Flaggschiffpreis in die Entry-Spalte der Positionskarte schiebt."""
    assert lies_preis("1.099") == 1099.0
    assert lies_preis("1.99") == 1.99  # zwei Nachkommastellen: Dezimal


@pytest.mark.parametrize(
    "wert,erwartet",
    [
        ("http://schema.org/InStock", "lieferbar"),
        ("https://schema.org/PreOrder", "vorbestellbar"),
        ("https://schema.org/BackOrder", "nicht_lieferbar"),
        ("http://schema.org/OutOfStock", "ausverkauft"),
        ("", "unbekannt"),
        ("Quatsch", "unbekannt"),
    ],
)
def test_verfuegbarkeit(wert, erwartet):
    assert verfuegbarkeit_aus_schema(wert) == erwartet


def test_ausverkauft_ist_keine_auslistung():
    # Teil F: eine Verfuegbarkeitsstufe ist kein Portfolio-Ende. Das Wort
    # "ausgelistet" darf aus einer einzelnen Seite gar nicht entstehen.
    werte = {
        verfuegbarkeit_aus_schema(w)
        for w in ("InStock", "OutOfStock", "SoldOut", "Discontinued", "BackOrder")
    }
    assert "ausgelistet" not in werte


def test_lockpreis_erkannt():
    assert ist_lockpreis(1.0) and ist_lockpreis(0.99)
    assert not ist_lockpreis(189.99)
    assert not ist_lockpreis(None)


# --------------------------------------------------------------------------
# Strukturierte Daten
# --------------------------------------------------------------------------


def test_ldjson_produkt():
    """Echter Abruf congstar Pixel 11 (31.08.2026). Der einzige Product-Knoten
    der Seite traegt "price":646, "priceCurrency":"EUR",
    "availability":"https://schema.org/InStock", "color":"Frost",
    "gtin":"0840353956216", "sku":"540_304720"; die BreadcrumbList der Seite
    ist kein Produkt und zaehlt nicht."""
    html = _echt("congstar_produkt_pixel11.html.gz")
    assert html.count('"@type":"Product"') == 1
    saetze = produkte_aus_ldjson(html)
    assert len(saetze) == 1
    s = saetze[0]
    assert s["preis"] == 646.0 and s["waehrung"] == "EUR"
    assert s["verfuegbarkeit"] == "lieferbar"
    assert s["farbe"] == "Frost" and s["ean"] == "0840353956216"
    assert s["sku"] == "540_304720" and s["titel"] == "Google Pixel 11"


def test_varianten_unter_issimilarto_kommen_mit():
    """Speicher- und Farbvarianten mit eigenem Preis unter `isSimilarTo` -
    die Granularitaet, die eine SKU-Matrix braucht. Keine echte Fixture mit
    Herkunft fuehrt diese Spielart, deshalb ein konstruiertes Literal:
    Hauptknoten 1099 + Varianten 1199 und 1099 (OutOfStock)."""
    saetze = produkte_aus_ldjson(_PRODUKT_MIT_VARIANTEN)
    assert len(saetze) == 3
    assert sorted(s["preis"] for s in saetze) == [1099.0, 1099.0, 1199.0]
    assert {s["farbe"] for s in saetze} == {"Obsidian", "Porcelain", "Moonstone"}
    assert any(s["verfuegbarkeit"] == "ausverkauft" for s in saetze)


def test_microdata_wenn_kein_ldjson():
    """Echter Abruf smartmobil iPhone 17 (31.08.2026): kein Product-JSON-LD,
    aber vier Product-itemscope-Bloecke (je Tarifbuendel einer) mit
    itemprop price 89.98, 59.98, 59.98 und 30.99, color "Lavendel"."""
    html = _echt("smartmobil_produkt_iphone17.html.gz")
    assert produkte_aus_ldjson(html) == []
    assert html.count('itemtype="https://schema.org/Offer"') == 4
    saetze = produkte_aus_microdata(html)
    assert len(saetze) == 4
    assert [s["preis"] for s in saetze] == [89.98, 59.98, 59.98, 30.99]
    assert {s["farbe"] for s in saetze} == {"Lavendel"}


def test_kaskade_nimmt_ldjson_zuerst():
    assert (
        produkte_aus_html(_echt("congstar_produkt_pixel11.html.gz"))[0]["quelle"]
        == "ldjson"
    )
    assert (
        produkte_aus_html(_echt("smartmobil_produkt_iphone17.html.gz"))[0]["quelle"]
        == "microdata"
    )


def test_kaputtes_ldjson_kippt_die_seite_nicht():
    html = (
        '<script type="application/ld+json">{kaputt</script>'
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Apple iPhone 17 Pro Max 256GB",'
        '"offers":{"price":"1449.00","priceCurrency":"EUR"}}</script>'
    )
    assert len(produkte_aus_ldjson(html)) == 1


def test_kein_rueckfall_auf_textextraktion():
    """Bricht das strukturierte Datum weg, ist die Quelle tot und sagt das.
    Ein Regex ueber den sichtbaren Preis waere eine Zahl, die aussieht wie
    gemessen und geraten ist."""
    html = "<html><body><h1>Apple iPhone 17 Pro Max</h1><b>1.449,00 €</b></body></html>"
    assert produkte_aus_html(html) == []


def test_shopify_katalog():
    """Echter Abruf EDEKA smart products.json (31.08.2026): 17 Produkte mit je
    einer Variante, also 17 Saetze. Das erste Produkt ist "EDEKA smart
    Smartphone-Tarif-Bundle", handle "bundle", Variante "Default Title" zu
    "149.95" - der Titel bleibt ohne Zusatz, die Adresse /products/bundle."""
    roh = _echt("edeka_smart_products.json")
    varianten = sum(len(p["variants"]) for p in json.loads(roh)["products"])
    saetze = produkte_aus_shopify(roh)
    assert len(saetze) == varianten == 17
    assert saetze[0]["preis"] == 149.95 and saetze[0]["url"] == "/products/bundle"
    assert saetze[0]["titel"] == "EDEKA smart Smartphone-Tarif-Bundle"


def test_kaputtes_shopify_json_wirft_statt_leer_zurueckzugeben():
    """Ein gescheiterter Abruf darf nie wie 'nichts gefunden' aussehen -
    sonst altert die Auslistungslogik einen ganzen Shop weg."""
    with pytest.raises(GeraeteAbrufFehler):
        produkte_aus_shopify("<html>Fehlerseite</html>")


# --------------------------------------------------------------------------
# Linkernte
# --------------------------------------------------------------------------


_KLARMOBIL_KAT = "klarmobil_kategorie_handy_kaufen.html.gz"
_CONGSTAR_SITEMAP = "congstar_sitemap_devices.xml"


def test_linkernte_aus_html_mit_pfadmuster():
    """Echter Abruf der klarmobil-Kategorieseite (31.08.2026): zwoelf
    `href` mit "/P-M-", jede Produktadresse steht zweimal (Bild und Titel).
    Entdoppelt in Seitenreihenfolge bleiben sechs absolute Adressen."""
    links = ernte_links(_echt(_KLARMOBIL_KAT), _herkunft_url(_KLARMOBIL_KAT), "/P-M-")
    basis = "https://www.klarmobil.de/handy-kaufen/"
    assert links == [
        basis + "samsung/samsung-galaxy-s26-ultra/P-M-4475373/",
        basis + "samsung/samsung-galaxy-s26/P-M-4466891/",
        basis + "apple/iphone-17/P-M-4234655/",
        basis + "samsung/samsung-galaxy-s26-tab-a11/P-M-4599675/",
        basis + "apple/iphone-17e/P-M-4506544/",
        basis + "apple/iphone-17-pro/P-M-4234664/",
    ]


def test_fremde_domain_faellt_raus():
    """Dieselbe echte Seite verlinkt auch www.freenet.de, www.facebook.com und
    weitere fremde Hosts; ohne Muster bleibt nur www.klarmobil.de."""
    html = _echt(_KLARMOBIL_KAT)
    assert 'href="https://www.freenet.de' in html  # Gegenprobe: es gibt sie
    links = ernte_links(html, _herkunft_url(_KLARMOBIL_KAT), "")
    assert links
    assert {urlparse(link).netloc for link in links} == {"www.klarmobil.de"}


def test_linkernte_aus_sitemap():
    """Echte congstar-Sitemap /sitemap/devices.xml (31.08.2026): 16 der 55
    `<loc>` liegen unter /geraete/apple/ - sieben iPhones, aber auch fuenf
    iPads, zwei AirPods und zwei Watches. Ein Muster allein trifft diese
    Streuung, fuer die es die Musterliste (Test darunter) braucht."""
    links = ernte_links(
        _echt(_CONGSTAR_SITEMAP),
        _herkunft_url(_CONGSTAR_SITEMAP),
        "/geraete/apple/",
        kind="sitemap",
    )
    assert len(links) == 16
    assert sum("-ipad-" in link for link in links) == 5
    assert sum("/airpods-" in link for link in links) == 2
    assert sum("-watch-" in link for link in links) == 2
    assert sum("-iphone-" in link for link in links) == 7


def test_musterliste_verlangt_alle_teile():
    """Eine Liste von Pfadmustern ist ein UND. Aus den 16 Apple-Adressen der
    echten congstar-Sitemap bleiben mit ["/geraete/apple/", "-iphone-"] nur
    die sieben iPhones; jede andere Seite kostete Crawl-delay-Sekunden des
    Zeitbudgets, ohne je den Katalog treffen zu koennen."""
    links = ernte_links(
        _echt(_CONGSTAR_SITEMAP),
        _herkunft_url(_CONGSTAR_SITEMAP),
        ["/geraete/apple/", "-iphone-"],
        kind="sitemap",
    )
    basis = "https://www.congstar.de/geraete/apple/apple-iphone-"
    assert links == [
        basis + "16/",
        basis + "16e/",
        basis + "17-pro-max/",
        basis + "17-pro/",
        basis + "17/",
        basis + "17e/",
        basis + "air/",
    ]


def test_sitemap_ohne_muster_nimmt_alles_der_domain():
    """Alle 55 `<loc>` der echten congstar-Sitemap liegen auf www.congstar.de
    und sind verschieden; ohne Muster kommen alle 55."""
    roh = _echt(_CONGSTAR_SITEMAP)
    links = ernte_links(roh, _herkunft_url(_CONGSTAR_SITEMAP), "", kind="sitemap")
    assert roh.count("<loc>https://www.congstar.de/") == roh.count("<loc>") == 55
    assert len(links) == 55


# --------------------------------------------------------------------------
# Ein Anbieter, Ende zu Ende
# --------------------------------------------------------------------------

_ROBOTS_FREI = (200, "User-agent: *\nDisallow: /cart\n")


def _anbieter(**kw):
    grund = kw.pop("einstieg_kind", "static")
    vor = {
        "name": "Haendler",
        "typ": "handel",
        "methode": "ldjson",
        "basis_url": _BASIS,
        "rate_limit_sekunden": 0,
        "einstiege": [
            Einstieg(
                url=_EINSTIEG,
                label="Smartphones",
                kind=grund,
                pfadmuster="/p/",
            )
        ],
    }
    vor.update(kw)
    return Anbieter(**vor)


def _hole_fabrik(seiten, protokoll=None):
    def hole(url):
        if protokoll is not None:
            protokoll.append(url)
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        if url in seiten:
            return (200, seiten[url])
        return (404, "")

    return hole


_IPHONE_URL = f"{_BASIS}/p/1514136/iphone-17-pro-max-256gb"
_HUELLE_URL = f"{_BASIS}/p/1514200/huelle-iphone-17"
_SEITEN = {
    _EINSTIEG: _KATEGORIE,
    f"{_BASIS}/p/1518897/galaxy-a57-5g-128gb": _A57_SEITE,
    _IPHONE_URL: _IPHONE_SEITE,
    _HUELLE_URL: "<html><body>Zubehoer ohne strukturierte Daten</body></html>",
}


def _lauf(anbieter=None, seiten=None, protokoll=None, jetzt=None, frist_bis=None):
    hole = _hole_fabrik(seiten if seiten is not None else _SEITEN, protokoll)
    waechter = RobotsWaechter(hole=hole)
    return sammle_anbieter(
        anbieter or _anbieter(),
        _KATALOG,
        _FARBEN,
        hole,
        "2026-08-11",
        waechter,
        jetzt or _jetzt(),
        frist_bis=frist_bis,
    )


def test_ende_zu_ende_ergibt_belegte_listungen():
    bilanz = _lauf()
    assert bilanz.status == "ok"
    assert bilanz.produkte_abgerufen == 3
    assert len(bilanz.listungen) == 2  # die Huelle liefert nichts
    a57, iphone = bilanz.listungen
    assert a57.sku_id == "samsung-galaxy-a57-128gb-blau"
    assert a57.preis_ohne_vertrag == 349.0
    assert iphone.preis_ohne_vertrag == 1449.0
    assert iphone.sku_id == "apple-iphone-17-pro-max-256gb-titan-natur"
    assert iphone.quelle_url.startswith(f"{_BASIS}/p/")
    assert iphone.abgerufen_am == "2026-08-11"
    assert iphone.confidence == "hoch"
    assert iphone.einstieg_url == _EINSTIEG


def test_einstiegsseite_gilt_als_gelesen():
    assert _lauf().gelesene_einstiege == {_EINSTIEG}


def test_es_wird_nur_abgerufen_was_verlinkt_war():
    """Die Regel aus Teil C2, mit derselben Falle wie beim Tarif-Sammler:
    eine erreichbare, aber NICHT verlinkte Adresse darf nicht angefasst
    werden."""
    seiten = dict(_SEITEN)
    falle = f"{_BASIS}/p/1514137/nicht-verlinkt"
    seiten[falle] = _IPHONE_SEITE
    protokoll = []
    bilanz = _lauf(seiten=seiten, protokoll=protokoll)
    assert bilanz.nicht_verlinkt == []
    assert falle not in protokoll
    # Gegenprobe: die Falle war wirklich erreichbar.
    assert falle in seiten


def test_ausserhalb_der_besuchszeit_wird_nichts_geholt_und_nichts_gelesen():
    """Der Kern des Befunds: Medimax erlaubt nur 02:00-08:00 UTC, der
    Wochenlauf startet 08:30. Dann darf der Anbieter WEDER abgerufen NOCH
    als gelesen gefuehrt werden - sonst altert jeder Tageslauf seine
    Geraete Richtung 'ausgelistet'."""
    robots = "User-agent: *\nCrawl-delay: 0\nVisit-time: 0200-0800\n"
    seiten = dict(_SEITEN)
    protokoll = []

    def hole(url):
        protokoll.append(url)
        if url.endswith("/robots.txt"):
            return (200, robots)
        return (200, seiten.get(url, ""))

    waechter = RobotsWaechter(hole=hole)
    bilanz = sammle_anbieter(
        _anbieter(),
        _KATALOG,
        _FARBEN,
        hole,
        "2026-08-11",
        waechter,
        _jetzt(8),
        frist_bis=None,
    )
    assert bilanz.gelesene_einstiege == set()
    assert bilanz.vollstaendig is False
    assert "Besuchszeit" in bilanz.grund
    assert [u for u in protokoll if "/p/" in u] == []


def test_gesperrter_pfad_wird_nicht_abgerufen():
    seiten = dict(_SEITEN)
    protokoll = []

    def hole(url):
        protokoll.append(url)
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /p/\n")
        return (200, seiten.get(url, ""))

    waechter = RobotsWaechter(hole=hole)
    bilanz = sammle_anbieter(
        _anbieter(),
        _KATALOG,
        _FARBEN,
        hole,
        "2026-08-11",
        waechter,
        _jetzt(),
        frist_bis=None,
    )
    assert [u for u in protokoll if "/p/" in u] == []
    assert bilanz.listungen == []
    # Die Kategorieseite war lesbar, aber keins ihrer Produkte - sie gilt
    # deshalb NICHT als vollstaendig gelesen.
    assert bilanz.gelesene_einstiege == set()


def test_zeitbudget_bricht_sauber_ab_und_altert_nichts():
    """Teil F: bei Fristablauf sauber abbrechen, Teilergebnis behalten - und
    die halb gelesene Seite NICHT als gelesen fuehren."""
    import time

    bilanz = _lauf(frist_bis=time.monotonic() - 1)
    assert bilanz.status == "frist"
    assert bilanz.gelesene_einstiege == set()
    assert bilanz.vollstaendig is False


def test_unbekannte_titel_werden_gemeldet_statt_verworfen():
    seiten = dict(_SEITEN)
    seiten[_HUELLE_URL] = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Fairphone 6 256 GB","offers":{"price":"599.00","priceCurrency":"EUR"}}'
        "</script>"
    )
    bilanz = _lauf(seiten=seiten)
    assert "Fairphone 6 256 GB" in bilanz.unbekannte_titel


def test_fremde_waehrung_wird_nicht_uebernommen():
    seiten = dict(_SEITEN)
    seiten[_IPHONE_URL] = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Apple iPhone 17 Pro Max 256GB Titannatur",'
        '"offers":{"price":"1449.00","priceCurrency":"CHF"}}</script>'
    )
    bilanz = _lauf(seiten=seiten)
    assert len(bilanz.listungen) == 1


def test_lockpreis_wird_nicht_als_ladenpreis_gefuehrt():
    """Die gemessene Falle: WinSIM, o2 und Blau tragen im voellig korrekten
    offers.price die Zahl 1 - die Zuzahlung im Buendel."""
    seiten = dict(_SEITEN)
    seiten[_IPHONE_URL] = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Apple iPhone 17 Pro Max 256GB Titannatur",'
        '"offers":{"price":"1.00","priceCurrency":"EUR"}}</script>'
    )
    bilanz = _lauf(seiten=seiten)
    lock = [
        l for l in bilanz.listungen if l.quelle_url.endswith("iphone-17-pro-max-256gb")
    ]
    assert len(lock) == 1
    assert lock[0].preis_ohne_vertrag is None
    assert lock[0].preisart == "kein_preis"


def test_deckel_je_anbieter():
    bilanz = _lauf(_anbieter(max_produkte=1))
    assert bilanz.produkte_abgerufen == 1


def test_gescheiterter_einstieg_ist_kein_leeres_ergebnis():
    bilanz = _lauf(_anbieter(), seiten={})
    assert bilanz.status == "fehler"
    assert bilanz.vollstaendig is False
    assert "404" in bilanz.grund


def test_nicht_umgesetzte_methode_sagt_das_und_ruehrt_nichts_an():
    protokoll = []
    bilanz = _lauf(
        _anbieter(
            name="Zustandsshop",
            methode="json_endpunkt",
            grund="Preis nur im Zustandsobjekt",
        ),
        protokoll=protokoll,
    )
    assert bilanz.status == "nicht_umgesetzt"
    assert bilanz.grund == "Preis nur im Zustandsobjekt"
    assert protokoll == []
    assert bilanz.vollstaendig is False


def test_deaktivierter_anbieter_behaelt_seinen_grund():
    bilanz = _lauf(
        _anbieter(
            name="Plattform",
            aktiv=False,
            methode="deaktiviert",
            grund="erfordert Product-Advertising-API-Zugang",
        )
    )
    assert bilanz.status == "uebersprungen"
    assert "API" in bilanz.grund


# --------------------------------------------------------------------------
# Alle Anbieter
# --------------------------------------------------------------------------


def test_sammle_geht_alle_anbieter_durch_und_meldet_jeden():
    quellen = QuellenConfig(
        anbieter=[
            _anbieter(rang=1),
            _anbieter(
                name="Plattform",
                rang=2,
                aktiv=False,
                methode="deaktiviert",
                grund="API nötig",
            ),
            _anbieter(
                name="Nur-SIM",
                rang=3,
                methode="kein_hardware",
                grund="vermarktet keine Hardware",
            ),
        ]
    )
    ergebnis = sammle(
        quellen, _KATALOG, _FARBEN, _hole_fabrik(_SEITEN), "2026-08-11", _jetzt()
    )
    assert len(ergebnis["anbieter"]) == 3
    assert {b.name for b in ergebnis["anbieter"]} == {
        "Haendler",
        "Plattform",
        "Nur-SIM",
    }
    assert len(ergebnis["listungen"]) == 2
    # Kein Anbieter faellt stillschweigend weg: jeder nicht gelaufene nennt
    # einen Grund (Akzeptanzkriterium Teil E).
    for b in ergebnis["anbieter"]:
        if b.status != "ok":
            assert b.grund


# --------------------------------------------------------------------------
# Die Befunde des Reviews vom 10.08.2026
# --------------------------------------------------------------------------


def test_abgeschnittene_seite_gilt_nicht_als_gelesen():
    """Befund 3, und er haette am meisten Schaden angerichtet: `max_produkte`
    schnitt die Linkliste ab, die Seite galt trotzdem als gelesen, und
    `mark_stale` alterte alles jenseits des Deckels. Live gemessen: die
    freenet-Sitemap liefert 83 Adressen zum konfigurierten Pfadmuster - bei
    einem Deckel von 60 waeren das 23 Geraete je Lauf, nach zwei Laeufen
    "ausgelistet", und das Protokoll saehe normal aus."""
    bilanz = _lauf(_anbieter(max_produkte=2))
    assert bilanz.produkte_abgerufen == 2
    assert bilanz.gelesene_einstiege == set()
    assert bilanz.vollstaendig is False
    # Und der Deckel meldet sich - keine stille Kappung (CLAUDE.md §6).
    assert bilanz.gedeckelt and "3 Adressen" in bilanz.gedeckelt[0]


def test_ein_gedeckelter_anbieter_heisst_nicht_kein_einstieg_lesbar():
    """Befund des ersten echten Laufs (10.08.2026): mobilcom-debitel stand
    mit "fehler (kein Einstieg lesbar)" im Protokoll und hatte dabei 84
    Listungen geliefert. Die Einstiegsseite WAR lesbar - nur ihr Deckel war
    erreicht. Wer das Protokoll liest, muss den Unterschied sehen; sonst
    sucht die naechste Session einen Ausfall, den es nicht gibt."""
    bilanz = _lauf(_anbieter(max_produkte=2))
    assert bilanz.status == "fehler"  # richtig: nichts darf altern
    assert "kein Einstieg lesbar" not in bilanz.grund
    assert "3 Adressen" in bilanz.grund  # der Deckel steht drin


def test_kein_einstieg_lesbar_bleibt_fuer_den_echten_ausfall():
    """Gegenprobe: wenn die Einstiegsseite wirklich nicht kommt, soll genau
    das dastehen - und nicht ploetzlich eine Deckelmeldung."""
    bilanz = _lauf(seiten={})  # die Einstiegsseite antwortet 404
    assert bilanz.status == "fehler"
    assert bilanz.produkte_abgerufen == 0
    assert "HTTP 404" in bilanz.grund
    assert "unvollstaendig ausgewertet" not in bilanz.grund


def test_unter_dem_deckel_gilt_die_seite_weiterhin_als_gelesen():
    # Gegenprobe: die Sperre darf den Normalfall nicht lahmlegen.
    bilanz = _lauf(_anbieter(max_produkte=50))
    assert bilanz.gedeckelt == []
    assert bilanz.vollstaendig is True


def test_sammelknoten_einer_produktseite_wird_verworfen():
    """Befund 17: freenet traegt je Seite einen Product-Knoten fuer das
    Geraet UND je einen fuer seine Varianten. Der erste hat keinen Speicher -
    als eigene Listung geschrieben kollidiert er mit jeder Variante, deren
    Speicher nicht gelesen werden konnte."""
    seiten = {
        _EINSTIEG: '<a href="/p/1/pixel">Pixel</a>',
        f"{_BASIS}/p/1/pixel": _PRODUKT_MIT_VARIANTEN,
    }
    bilanz = _lauf(seiten=seiten)
    speicher = sorted(l.speicher_gb for l in bilanz.listungen)
    assert speicher == [128, 256], f"Sammelknoten nicht verworfen: {speicher}"


def test_seite_mit_nur_einem_sammelknoten_behaelt_ihn():
    seiten = {
        _EINSTIEG: '<a href="/p/1/x">X</a>',
        f"{_BASIS}/p/1/x": '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Apple iPhone 17 Pro Max","offers":{"price":"1449.00",'
        '"priceCurrency":"EUR"}}</script>',
    }
    bilanz = _lauf(seiten=seiten)
    assert len(bilanz.listungen) == 1
    assert bilanz.listungen[0].speicher_gb is None


def test_unbekannte_farbe_der_quelle_landet_in_der_arbeitsliste():
    """Die Arbeitsliste fuer config/farben.yaml - der Farbbericht am
    Seitenende speist sich daraus."""
    seiten = dict(_SEITEN)
    seiten[_IPHONE_URL] = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Apple iPhone 17 Pro Max 256GB","color":"Desert Mocha",'
        '"offers":{"price":"1449.00","priceCurrency":"EUR"}}</script>'
    )
    bilanz = _lauf(seiten=seiten)
    assert "Desert Mocha" in bilanz.unbekannte_farben


# --------------------------------------------------------------------------
# Das Zeitbudget ist keine gemeinsame Weide (Diagnose G0 vom 28.08.2026)
# --------------------------------------------------------------------------


def test_ein_grosser_anbieter_laesst_den_naechsten_nicht_verhungern(monkeypatch):
    """Der Befund: freenet (Rang 4, ueber 70 Produktseiten mal Crawl-Abstand)
    verbrauchte das gesamte 1500-s-Budget, und ALDI TALK stand ab dem
    15.08.2026 jede Nacht mit "frist, 0 Listungen" da. Jeder noch
    ausstehende crawlende Anbieter muss eine Mindestreserve behalten -
    gegen den alten Stand (ein gemeinsames frist_bis fuer alle) faellt
    dieser Test durch."""
    import telco_radar.collect.geraete as g

    uhr = {"t": 0.0}
    monkeypatch.setattr(g.time, "monotonic", lambda: uhr["t"])
    monkeypatch.setattr(g.time, "sleep", lambda s: uhr.__setitem__("t", uhr["t"] + s))

    produkt = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Apple iPhone 17 Pro Max 256GB Titannatur",'
        '"offers":{"price":"1449.00","priceCurrency":"EUR"}}</script>'
    )
    seiten = {
        "https://www.gross.test/kat": "".join(
            f'<a href="/p/{i}">P{i}</a>' for i in range(20)
        ),
        "https://www.klein.test/kat": '<a href="/p/1">P1</a>',
        "https://www.klein.test/p/1": produkt,
    }
    seiten.update({f"https://www.gross.test/p/{i}": produkt for i in range(20)})

    def hole(url):
        uhr["t"] += 30.0  # jeder Abruf kostet 30 Sekunden
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        return (200, seiten[url]) if url in seiten else (404, "")

    quellen = QuellenConfig(
        anbieter=[
            _anbieter(
                name="Gross",
                rang=1,
                basis_url="https://www.gross.test",
                einstiege=[
                    Einstieg(
                        url="https://www.gross.test/kat",
                        kind="static",
                        pfadmuster="/p/",
                    )
                ],
            ),
            _anbieter(
                name="Klein",
                rang=2,
                basis_url="https://www.klein.test",
                einstiege=[
                    Einstieg(
                        url="https://www.klein.test/kat",
                        kind="static",
                        pfadmuster="/p/",
                    )
                ],
            ),
        ]
    )
    ergebnis = sammle(
        quellen, _KATALOG, _FARBEN, hole, "2026-08-28", _jetzt(), frist_sekunden=600.0
    )
    gross, klein = ergebnis["anbieter"]
    assert gross.status == "frist", "der Grosse laeuft in seinen Anteil"
    assert gross.produkte_abgerufen > 0, "das Teilergebnis bleibt"
    assert klein.vollstaendig is True, (
        "der Kleine bekommt seine Reserve und liest zu Ende"
    )


def test_bei_knappem_budget_verhungert_nicht_jeder_ausser_dem_letzten(monkeypatch):
    """Der Fehler in der ERSTEN Fassung dieser Aufteilung, beim Selbstreview
    gefunden: mit `max(0, rest - nach_mir * MINDEST)` frisst die Reserve fuer
    die Nachfolgenden bei knappem Budget den eigenen Anteil vollstaendig auf.

    Rechenbeispiel: 240 s Budget, 6 crawlende Anbieter -> der erste haette
    240 - 5*120 = -360, also null Sekunden. Und der zweite auch, und der
    dritte - nur der letzte bekaeme etwas. Das ist dasselbe Verhungern, das
    die Aufteilung verhindern soll, nur am anderen Ende der Liste."""
    import telco_radar.collect.geraete as g

    uhr = {"t": 0.0}
    monkeypatch.setattr(g.time, "monotonic", lambda: uhr["t"])
    monkeypatch.setattr(g.time, "sleep", lambda s: uhr.__setitem__("t", uhr["t"] + s))

    produkt = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Apple iPhone 17 Pro Max 256GB Titannatur",'
        '"offers":{"price":"1449.00","priceCurrency":"EUR"}}</script>'
    )
    seiten, anbieter = {}, []
    for i in range(4):
        host = f"https://www.a{i}.test"
        seiten[f"{host}/kat"] = f'<a href="/p/1">P</a>'
        seiten[f"{host}/p/1"] = produkt
        anbieter.append(
            _anbieter(
                name=f"A{i}",
                rang=i,
                basis_url=host,
                einstiege=[
                    Einstieg(url=f"{host}/kat", kind="static", pfadmuster="/p/")
                ],
            )
        )

    def hole(url):
        uhr["t"] += 20.0
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        return (200, seiten[url]) if url in seiten else (404, "")

    # 240 s fuer vier Anbieter: nicht genug fuer alle, aber die ersten
    # muessen etwas bekommen - nicht null.
    ergebnis = sammle(
        QuellenConfig(anbieter=anbieter),
        _KATALOG,
        _FARBEN,
        hole,
        "2026-08-29",
        _jetzt(),
        frist_sekunden=240.0,
    )
    mit_funden = [b for b in ergebnis["anbieter"] if b.listungen]
    assert mit_funden, "bei knappem Budget liefert KEIN Anbieter etwas"
    assert mit_funden[0].name == "A0", (
        "der erste Anbieter kommt zuerst dran, nicht der letzte"
    )
