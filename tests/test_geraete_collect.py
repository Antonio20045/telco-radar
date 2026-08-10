"""Der Geraete-Collector: Linkernte, strukturierte Daten, Zeitbudget.

Die Fixtures unter tests/fixtures/geraete/ bilden nach, was am 10.08.2026
wirklich gemessen wurde: Medimax und freenet liefern Product/offers als
JSON-LD (freenet mitsamt Varianten unter `isSimilarTo`), ALDI TALK
schema.org-Microdata, Shopify-Shops ihren Katalog als products.json.
Kein Test fasst das Netz an.
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from telco_radar.collect.geraete import (
    Anbieterbilanz,
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


def _fixture(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
           speicher=[256, 512, 1024], segment="flagship"),
    Geraet(hersteller="Samsung", modell="Galaxy A57", generation=57,
           speicher=[128, 256], segment="mid"),
    Geraet(hersteller="Google", modell="Pixel 10 Pro", generation=10,
           speicher=[128, 256], segment="flagship"),
    Geraet(hersteller="Motorola", modell="Motorola moto g85", generation=85,
           speicher=[128, 256], segment="mid"),
])
_FARBEN = {"titannatur": "titan-natur", "blau": "blau", "obsidian": "schwarz",
           "porcelain": "weiss", "moonstone": "grau"}


def _jetzt(stunde=3):
    return datetime(2026, 8, 11, stunde, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Preise lesen
# --------------------------------------------------------------------------

@pytest.mark.parametrize("roh,erwartet", [
    ("1449.00", 1449.0), (1099, 1099.0), ("1099", 1099.0),
    ("1.099,00", 1099.0), ("1.099", 1099.0), ("189,99", 189.99),
    ("1.234.567,89", 1234567.89 if False else None),   # ueber der Obergrenze
    ("349,00 €", 349.0), ("", None), (None, None), ("kostenlos", None),
    ("0", None), ("-5", None),
])
def test_preisformate(roh, erwartet):
    assert lies_preis(roh) == erwartet


def test_deutscher_tausenderpunkt_wird_nicht_zum_dezimaltrenner():
    """"1.099" ist 1099 Euro und nicht 1,099 Euro - der Fehler, der einen
    Flaggschiffpreis in die Entry-Spalte der Positionskarte schiebt."""
    assert lies_preis("1.099") == 1099.0
    assert lies_preis("1.99") == 1.99      # zwei Nachkommastellen: Dezimal


@pytest.mark.parametrize("wert,erwartet", [
    ("http://schema.org/InStock", "lieferbar"),
    ("https://schema.org/PreOrder", "vorbestellbar"),
    ("https://schema.org/BackOrder", "nicht_lieferbar"),
    ("http://schema.org/OutOfStock", "ausverkauft"),
    ("", "unbekannt"), ("Quatsch", "unbekannt"),
])
def test_verfuegbarkeit(wert, erwartet):
    assert verfuegbarkeit_aus_schema(wert) == erwartet


def test_ausverkauft_ist_keine_auslistung():
    # Teil F: eine Verfuegbarkeitsstufe ist kein Portfolio-Ende. Das Wort
    # "ausgelistet" darf aus einer einzelnen Seite gar nicht entstehen.
    werte = {verfuegbarkeit_aus_schema(w) for w in
             ("InStock", "OutOfStock", "SoldOut", "Discontinued", "BackOrder")}
    assert "ausgelistet" not in werte


def test_lockpreis_erkannt():
    assert ist_lockpreis(1.0) and ist_lockpreis(0.99)
    assert not ist_lockpreis(189.99)
    assert not ist_lockpreis(None)


# --------------------------------------------------------------------------
# Strukturierte Daten
# --------------------------------------------------------------------------

def test_ldjson_produkt():
    saetze = produkte_aus_ldjson(_fixture("medimax_produkt.html"))
    assert len(saetze) == 1
    s = saetze[0]
    assert s["preis"] == 1449.0 and s["waehrung"] == "EUR"
    assert s["verfuegbarkeit"] == "lieferbar"
    assert s["farbe"] == "Titannatur" and s["ean"] == "0194253000000"


def test_varianten_unter_issimilarto_kommen_mit():
    """freenet haengt Speicher- und Farbvarianten mit eigenem Preis dorthin -
    genau die Granularitaet, die eine SKU-Matrix braucht."""
    saetze = produkte_aus_ldjson(_fixture("freenet_produkt.html"))
    assert len(saetze) == 3
    assert sorted(s["preis"] for s in saetze) == [1099.0, 1099.0, 1199.0]
    assert {s["farbe"] for s in saetze} == {"Obsidian", "Porcelain", "Moonstone"}
    assert any(s["verfuegbarkeit"] == "ausverkauft" for s in saetze)


def test_microdata_wenn_kein_ldjson():
    html = _fixture("alditalk_produkt.html")
    assert produkte_aus_ldjson(html) == []
    saetze = produkte_aus_microdata(html)
    assert len(saetze) == 1
    assert saetze[0]["preis"] == 189.99 and saetze[0]["farbe"] == "Blau"


def test_kaskade_nimmt_ldjson_zuerst():
    assert produkte_aus_html(_fixture("medimax_produkt.html"))[0]["quelle"] == "ldjson"
    assert produkte_aus_html(_fixture("alditalk_produkt.html"))[0]["quelle"] == "microdata"


def test_kaputtes_ldjson_kippt_die_seite_nicht():
    html = ('<script type="application/ld+json">{kaputt</script>'
            '<script type="application/ld+json">'
            '{"@type":"Product","name":"Apple iPhone 17 Pro Max 256GB",'
            '"offers":{"price":"1449.00","priceCurrency":"EUR"}}</script>')
    assert len(produkte_aus_ldjson(html)) == 1


def test_kein_rueckfall_auf_textextraktion():
    """Bricht das strukturierte Datum weg, ist die Quelle tot und sagt das.
    Ein Regex ueber den sichtbaren Preis waere eine Zahl, die aussieht wie
    gemessen und geraten ist."""
    html = "<html><body><h1>Apple iPhone 17 Pro Max</h1><b>1.449,00 €</b></body></html>"
    assert produkte_aus_html(html) == []


def test_shopify_katalog():
    saetze = produkte_aus_shopify(_fixture("shopify_products.json"))
    assert len(saetze) == 2
    assert saetze[0]["preis"] == 99.99 and saetze[0]["url"] == "/products/bundle"


def test_kaputtes_shopify_json_wirft_statt_leer_zurueckzugeben():
    """Ein gescheiterter Abruf darf nie wie 'nichts gefunden' aussehen -
    sonst altert die Auslistungslogik einen ganzen Shop weg."""
    with pytest.raises(GeraeteAbrufFehler):
        produkte_aus_shopify("<html>Fehlerseite</html>")


# --------------------------------------------------------------------------
# Linkernte
# --------------------------------------------------------------------------

def test_linkernte_aus_html_mit_pfadmuster():
    links = ernte_links(_fixture("medimax_kategorie.html"),
                        "https://www.medimax.de/c/116/smartphones", "/p/")
    assert links == [
        "https://www.medimax.de/p/1518897/galaxy-a57-5g-a576b-128gb",
        "https://www.medimax.de/p/1514136/iphone-17-pro-max-256gb",
        "https://www.medimax.de/p/1514200/huelle-iphone-17",
    ]


def test_fremde_domain_faellt_raus():
    links = ernte_links(_fixture("medimax_kategorie.html"),
                        "https://www.medimax.de/c/116/smartphones", "")
    assert not any("fremd.de" in l for l in links)


def test_linkernte_aus_sitemap():
    links = ernte_links(_fixture("freenet_sitemap.xml"),
                        "https://www.freenet.de/sitemap.xml",
                        "-ohne-vertrag/p/P-M-", kind="sitemap")
    assert links == ["https://www.freenet.de/handys-smartphones/google/"
                     "google-pixel-10-pro-ohne-vertrag/p/P-M-4206120"]


def test_sitemap_ohne_muster_nimmt_alles_der_domain():
    links = ernte_links(_fixture("freenet_sitemap.xml"),
                        "https://www.freenet.de/sitemap.xml", "", kind="sitemap")
    assert len(links) == 4


# --------------------------------------------------------------------------
# Ein Anbieter, Ende zu Ende
# --------------------------------------------------------------------------

_ROBOTS_FREI = (200, "User-agent: *\nDisallow: /cart\n")


def _anbieter(**kw):
    grund = kw.pop("einstieg_kind", "static")
    vor = {"name": "Medimax", "typ": "handel", "methode": "ldjson",
           "basis_url": "https://www.medimax.de", "rate_limit_sekunden": 0,
           "einstiege": [Einstieg(url="https://www.medimax.de/c/116/smartphones",
                                  label="Smartphones", kind=grund, pfadmuster="/p/")]}
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


_SEITEN = {
    "https://www.medimax.de/c/116/smartphones": _fixture("medimax_kategorie.html"),
    "https://www.medimax.de/p/1518897/galaxy-a57-5g-a576b-128gb":
        _fixture("medimax_produkt.html"),
    "https://www.medimax.de/p/1514136/iphone-17-pro-max-256gb":
        _fixture("medimax_produkt.html"),
    "https://www.medimax.de/p/1514200/huelle-iphone-17":
        "<html><body>Zubehör ohne strukturierte Daten</body></html>",
}


def _lauf(anbieter=None, seiten=None, protokoll=None, jetzt=None, frist_bis=None):
    hole = _hole_fabrik(seiten if seiten is not None else _SEITEN, protokoll)
    waechter = RobotsWaechter(hole=hole)
    return sammle_anbieter(anbieter or _anbieter(), _KATALOG, _FARBEN, hole,
                           "2026-08-11", waechter, jetzt or _jetzt(),
                           frist_bis=frist_bis)


def test_ende_zu_ende_ergibt_belegte_listungen():
    bilanz = _lauf()
    assert bilanz.status == "ok"
    assert bilanz.produkte_abgerufen == 3
    assert len(bilanz.listungen) == 2      # die Huelle liefert nichts
    l = bilanz.listungen[0]
    assert l.preis_ohne_vertrag == 1449.0
    assert l.sku_id == "apple-iphone-17-pro-max-256gb-titan-natur"
    assert l.quelle_url.startswith("https://www.medimax.de/p/")
    assert l.abgerufen_am == "2026-08-11"
    assert l.confidence == "hoch"
    assert l.einstieg_url == "https://www.medimax.de/c/116/smartphones"


def test_einstiegsseite_gilt_als_gelesen():
    assert _lauf().gelesene_einstiege == {"https://www.medimax.de/c/116/smartphones"}


def test_es_wird_nur_abgerufen_was_verlinkt_war():
    """Die Regel aus Teil C2, mit derselben Falle wie beim Tarif-Sammler:
    eine erreichbare, aber NICHT verlinkte Adresse darf nicht angefasst
    werden."""
    seiten = dict(_SEITEN)
    falle = "https://www.medimax.de/p/1514137/nicht-verlinkt"
    seiten[falle] = _fixture("medimax_produkt.html")
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
    bilanz = sammle_anbieter(_anbieter(), _KATALOG, _FARBEN, hole, "2026-08-11",
                             waechter, _jetzt(8), frist_bis=None)
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
    bilanz = sammle_anbieter(_anbieter(), _KATALOG, _FARBEN, hole, "2026-08-11",
                             waechter, _jetzt(), frist_bis=None)
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
    seiten["https://www.medimax.de/p/1514200/huelle-iphone-17"] = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Fairphone 6 256 GB","offers":{"price":"599.00","priceCurrency":"EUR"}}'
        "</script>")
    bilanz = _lauf(seiten=seiten)
    assert "Fairphone 6 256 GB" in bilanz.unbekannte_titel


def test_fremde_waehrung_wird_nicht_uebernommen():
    seiten = dict(_SEITEN)
    seiten["https://www.medimax.de/p/1514136/iphone-17-pro-max-256gb"] = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Apple iPhone 17 Pro Max 256GB Titannatur",'
        '"offers":{"price":"1449.00","priceCurrency":"CHF"}}</script>')
    bilanz = _lauf(seiten=seiten)
    assert len(bilanz.listungen) == 1


def test_lockpreis_wird_nicht_als_ladenpreis_gefuehrt():
    """Die gemessene Falle: WinSIM, o2 und Blau tragen im voellig korrekten
    offers.price die Zahl 1 - die Zuzahlung im Buendel."""
    seiten = dict(_SEITEN)
    seiten["https://www.medimax.de/p/1514136/iphone-17-pro-max-256gb"] = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Apple iPhone 17 Pro Max 256GB Titannatur",'
        '"offers":{"price":"1.00","priceCurrency":"EUR"}}</script>')
    bilanz = _lauf(seiten=seiten)
    lock = [l for l in bilanz.listungen
            if l.quelle_url.endswith("iphone-17-pro-max-256gb")]
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
    bilanz = _lauf(_anbieter(name="Telekom", methode="json_endpunkt",
                             grund="Preis nur im Zustandsobjekt"),
                   protokoll=protokoll)
    assert bilanz.status == "nicht_umgesetzt"
    assert bilanz.grund == "Preis nur im Zustandsobjekt"
    assert protokoll == []
    assert bilanz.vollstaendig is False


def test_deaktivierter_anbieter_behaelt_seinen_grund():
    bilanz = _lauf(_anbieter(name="Amazon", aktiv=False, methode="deaktiviert",
                             grund="erfordert Product-Advertising-API-Zugang"))
    assert bilanz.status == "uebersprungen"
    assert "API" in bilanz.grund


# --------------------------------------------------------------------------
# Alle Anbieter
# --------------------------------------------------------------------------

def test_sammle_geht_alle_anbieter_durch_und_meldet_jeden():
    quellen = QuellenConfig(anbieter=[
        _anbieter(rang=1),
        _anbieter(name="Amazon", rang=2, aktiv=False, methode="deaktiviert",
                  grund="API nötig"),
        _anbieter(name="fraenk", rang=3, methode="kein_hardware",
                  grund="vermarktet keine Hardware"),
    ])
    ergebnis = sammle(quellen, _KATALOG, _FARBEN, _hole_fabrik(_SEITEN),
                      "2026-08-11", _jetzt())
    assert len(ergebnis["anbieter"]) == 3
    assert {b.name for b in ergebnis["anbieter"]} == {"Medimax", "Amazon", "fraenk"}
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
        "https://www.medimax.de/c/116/smartphones":
            '<a href="/p/1/pixel">Pixel</a>',
        "https://www.medimax.de/p/1/pixel": _fixture("freenet_produkt.html"),
    }
    bilanz = _lauf(seiten=seiten)
    speicher = sorted(l.speicher_gb for l in bilanz.listungen)
    assert speicher == [128, 256], f"Sammelknoten nicht verworfen: {speicher}"


def test_seite_mit_nur_einem_sammelknoten_behaelt_ihn():
    seiten = {
        "https://www.medimax.de/c/116/smartphones": '<a href="/p/1/x">X</a>',
        "https://www.medimax.de/p/1/x":
            '<script type="application/ld+json">{"@type":"Product",'
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
    seiten["https://www.medimax.de/p/1514136/iphone-17-pro-max-256gb"] = (
        '<script type="application/ld+json">{"@type":"Product",'
        '"name":"Apple iPhone 17 Pro Max 256GB","color":"Desert Mocha",'
        '"offers":{"price":"1449.00","priceCurrency":"EUR"}}</script>')
    bilanz = _lauf(seiten=seiten)
    assert "Desert Mocha" in bilanz.unbekannte_farben
