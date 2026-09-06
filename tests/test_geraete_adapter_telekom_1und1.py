"""Telekom und 1&1: die zwei Netzbetreiber-Adapter vom 04.09.2026.

WARUM DIESE ZWEI NEBENEINANDER STEHEN
-------------------------------------
Beide waren jahrelang `aktiv: false`, beide aus DEMSELBEN Grund - ihre
Zahl war keine Barpreiszahl, und keine Zahl ist besser als eine plausibel
falsche. Beide sind jetzt angebunden, weil die Preisform mitgeschrieben
wird statt weggelassen zu werden:

    Telekom   `totalPrice` ist ein 36-Monats-Ratengesamtbetrag. Er kommt
              nur mit `anzahlung`, `monatsrate` und `laufzeit_monate` in
              den Bestand - und nur, wenn die drei ihn ergeben.
    1&1       `offers.price` ist der Monatspreis des BUENDELS. Er kommt
              nur mit `tarif_referenz` und `laufzeit_monate` in den
              Bestand - und nie in `preis_ohne_vertrag`.

JEDE FIXTURE IST EIN GESPEICHERTER ECHTER ABRUF vom 04.09.2026, roh und
ungekuerzt, mit dem Absender `TelcoRadar/1.0` geholt. Herkunft, HTTP-Status
und sha256 des entpackten Inhalts stehen in
`tests/fixtures/geraete/_herkunft.json`. Das ist die Lehre vom 11.08.2026:
ein Bau-Subagent hatte damals eine Fixture ERFUNDEN, und nur der
adversarische Pruefdurchgang hat es aufgedeckt.

Die kleinen, im Code stehenden HTML-Schnipsel weiter unten sind KEINE
Messungen und geben sich auch nicht als solche aus - sie stellen Ausfaelle
nach (Challenge-Antwort, kaputtes JSON, fehlender Tarifname), die man nicht
ehrlich herbeimessen kann.
"""
import gzip
from datetime import datetime, timezone
from pathlib import Path

import pytest

from telco_radar.collect.geraete import (
    GeraeteAbrufFehler, einsundeins, sammle_anbieter, telekom,
)
from telco_radar.collect.geraete import _preisfelder
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import (
    Anbieter, Einstieg, lade_farben, lade_katalog, lade_quellen,
)
from telco_radar.geraete_model import probe_geht_auf

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

_TELEKOM_URL = "https://www.telekom.de/shop/geraete/smartphones/ohne-vertrag"
_EE_KATEGORIE = "https://mobile.1und1.de/smartphones"
_EE_PRODUKT = "https://mobile.1und1.de/iphone-17-pro"


def _gz(name: str) -> str:
    with gzip.open(_FIX / name, "rt", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def telekom_html():
    return _gz("telekom_kategorie_smartphones_ohne_vertrag.html.gz")


@pytest.fixture(scope="module")
def ee_kategorie():
    return _gz("1und1_kategorie_smartphones.html.gz")


@pytest.fixture(scope="module")
def ee_produkt():
    return _gz("1und1_produkt_iphone17pro.html.gz")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(_WURZEL)


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


# ==========================================================================
# Telekom - die Kategorieseite IST die Nutzlast
# ==========================================================================

def test_telekom_liest_die_zehn_geraete_der_kategorieseite(telekom_html):
    saetze = telekom.lies(telekom_html, _TELEKOM_URL)
    assert len(saetze) == 10
    pro = [s for s in saetze if s["titel"].startswith("Apple iPhone 17 Pro 256")]
    assert len(pro) == 1
    assert pro[0]["preis"] == 1197.0
    assert pro[0]["anzahlung"] == 99.0
    assert pro[0]["monatsrate"] == 30.5
    assert pro[0]["laufzeit_monate"] == 36
    assert pro[0]["speicher_gb"] == 256
    assert pro[0]["farbe"] == "tiefblau"


def test_telekom_jeder_gesamtbetrag_geht_auf(telekom_html):
    """Die Rechenprobe ist die Zulassungsbedingung, nicht eine Zugabe.

    Ein Gesamtbetrag, der seinen eigenen Bestandteilen widerspricht, ist
    keine Messung, sondern ein geaendertes Nutzlastformat - und das soll
    auffallen und nicht als Preis in den Bestand.
    """
    for satz in telekom.lies(telekom_html, _TELEKOM_URL):
        assert probe_geht_auf(satz["anzahlung"], satz["monatsrate"],
                              satz["laufzeit_monate"], satz["preis"]), satz["titel"]


def test_telekom_nennt_keinen_zinssatz_und_behauptet_auch_keinen(telekom_html):
    """`None` heisst unbekannt. 0.0 waere die Behauptung "zinsfrei", und die
    steht nirgends auf dieser Seite - o2 bekommt seine 0.0 nur, weil die
    Produktseite sie woertlich als Finanzierungshinweis nennt."""
    assert all(s["zins_effektiv"] is None
               for s in telekom.lies(telekom_html, _TELEKOM_URL))


def test_telekom_adresse_kommt_aus_dem_html_und_nicht_aus_dem_slug(telekom_html):
    """Aus brandSlug/productSlug/variantSlug LIESSE sich eine Adresse
    zusammensetzen. Das waere eine geratene Adresse (§ 87b). Genommen wird
    nur, was als echtes `<a href>` auf der Seite steht - erkennbar daran,
    dass die Abfrageparameter der Seite mitkommen."""
    saetze = telekom.lies(telekom_html, _TELEKOM_URL)
    pro = next(s for s in saetze if s["titel"].startswith("Apple iPhone 17 Pro 256"))
    assert pro["url"] == (
        "https://www.telekom.de/shop/geraet/apple/apple-iphone-17-pro/"
        "tiefblau-256-gb?hardwareOnlySale=true&categoryId=smartphones")


def test_telekom_ohne_passende_adresse_bleibt_das_feld_leer():
    """Kein Link zum Geraet: dann traegt der Satz keine Produktadresse und
    erbt spaeter die Kategorieseite. Eine konstruierte Adresse waere ein
    404 mit dem Anschein einer Fundstelle."""
    html = ('<html><body><script>window.__INITIAL_STATE__ = '
            '{"productList": {"data": [{"name": "Apple iPhone 17", '
            '"brandSlug": "apple", "productSlug": "apple-iphone-17", '
            '"variantSlug": "schwarz-256-gb", "availabilityStatus": "IN_STOCK", '
            '"price": {"upfrontPrice": 99, "installments": [{"numberOfInstallments": 36, '
            '"recurringPrice": 25, "totalPrice": 999}]}}]}};</script></body></html>')
    satz = telekom.lies(html, _TELEKOM_URL)[0]
    assert satz["url"] == ""
    assert satz["preis"] == 999.0


def test_telekom_terabyte_wird_nicht_als_gigabyte_gelesen():
    html = ('<script>window.__INITIAL_STATE__ = {"productList": {"data": '
            '[{"name": "Apple iPhone 17 Pro Max", "variantSlug": "silber-1-tb", '
            '"price": {"upfrontPrice": 0, "installments": [{"numberOfInstallments": 24, '
            '"recurringPrice": 50, "totalPrice": 1200}]}}]}};</script>')
    assert telekom.lies(html, _TELEKOM_URL)[0]["speicher_gb"] == 1024


def test_telekom_gesamtbetrag_der_nicht_aufgeht_wird_verworfen():
    """99 + 36 x 30,50 sind 1197,00 und nicht 1500,00. Der Satz faellt
    ganz weg - denn ohne belegte Bestandteile waere die Zahl ein Barpreis,
    der sie nicht ist."""
    html = ('<script>window.__INITIAL_STATE__ = {"productList": {"data": '
            '[{"name": "Apple iPhone 17 Pro", "variantSlug": "tiefblau-256-gb", '
            '"price": {"upfrontPrice": 99, "installments": [{"numberOfInstallments": 36, '
            '"recurringPrice": 30.5, "totalPrice": 1500}]}}]}};</script>')
    assert telekom.lies(html, _TELEKOM_URL) == []


def test_telekom_eintrag_ganz_ohne_ratenform_wird_verworfen():
    html = ('<script>window.__INITIAL_STATE__ = {"productList": {"data": '
            '[{"name": "Apple iPhone 17", "variantSlug": "schwarz-256-gb", '
            '"price": {"upfrontPrice": 799}}]}};</script>')
    assert telekom.lies(html, _TELEKOM_URL) == []


def test_telekom_challenge_antwort_wirft_statt_leer_zurueckzugeben():
    """Aus dem Actions-IP-Bereich antwortet telekom.de mit HTTP 202 und rund
    2 KB Challenge-HTML. Das ist KEIN leerer Katalog - der Unterschied
    entscheidet, ob der Bestand gealtert wird oder nicht."""
    challenge = ('<html><head><title>Bitte warten</title></head><body>'
                 '<script src="https://de-fra.captcha-sdk.awswaf.com/x.js">'
                 '</script></body></html>')
    with pytest.raises(GeraeteAbrufFehler) as fehler:
        telekom.lies(challenge, _TELEKOM_URL)
    assert "INITIAL_STATE" in str(fehler.value)


def test_telekom_leere_antwort_wirft():
    with pytest.raises(GeraeteAbrufFehler):
        telekom.lies("", _TELEKOM_URL)


def test_telekom_kaputtes_zustandsobjekt_wirft():
    with pytest.raises(GeraeteAbrufFehler) as fehler:
        telekom.lies("<script>window.__INITIAL_STATE__ = {kaputt;</script>",
                     _TELEKOM_URL)
    assert "unlesbar" in str(fehler.value)


def test_telekom_productlist_ohne_liste_wirft():
    with pytest.raises(GeraeteAbrufFehler):
        telekom.lies('<script>window.__INITIAL_STATE__ = '
                     '{"productList": {"data": "nichts"}};</script>', _TELEKOM_URL)


def test_telekom_ende_des_zustands_wird_nicht_am_ersten_semikolon_geraten():
    """Ein Regex bis zum naechsten `;` schnitte mitten im Marketingtext ab.
    Gelesen wird mit dem JSON-Dekoder, der sein Ende selbst findet."""
    html = ('<script>window.__INITIAL_STATE__ = {"productList": {"data": '
            '[{"name": "Apple iPhone 17", "variantSlug": "schwarz-256-gb", '
            '"claim": "Jetzt sichern; nur kurze Zeit", '
            '"price": {"upfrontPrice": 0, "installments": [{"numberOfInstallments": 24, '
            '"recurringPrice": 40, "totalPrice": 960}]}}]}};</script>')
    assert telekom.lies(html, _TELEKOM_URL)[0]["preis"] == 960.0


def test_telekom_landet_als_listung_mit_preisform_im_bestand(katalog, farben,
                                                             telekom_html):
    """Der ganze Weg, mit der AUSGELIEFERTEN Konfiguration: ein Abruf, zehn
    Listungen, und jede traegt ihren Ratenhinweis."""
    anbieter = lade_quellen(_WURZEL).nach_name("Telekom")
    assert anbieter.aktiv and anbieter.methode == "telekom_kategorie"
    anbieter.rate_limit_sekunden = 0

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /is-bin/intershop.static/\n")
        return (200, telekom_html)

    bilanz = sammle_anbieter(anbieter, katalog, farben, hole, "2026-09-04",
                             RobotsWaechter(hole=hole),
                             datetime(2026, 9, 4, 3, tzinfo=timezone.utc))
    assert bilanz.status == "ok"
    # `direkt=True`: die Kategorieseite ist die Nutzlast, es wird KEINE
    # Produktseite nachgeladen.
    assert [u for u in bilanz.besucht if not u.endswith("robots.txt")] == [_TELEKOM_URL]
    assert len(bilanz.listungen) == 10
    for listung in bilanz.listungen:
        assert listung.ratenhinweis == "in 36 Raten"
        assert listung.ratenzahlung is not None


# ==========================================================================
# 1&1 - der Monatspreis des Buendels
# ==========================================================================

def test_einsundeins_erntet_nur_die_katalogkacheln(ee_kategorie):
    """Die Seite fuehrt 167 Adressen der eigenen Domain, davon 42
    Produktseiten. Geerntet wird, was die Seite selbst als Kachel
    auszeichnet - ein Pfadmuster kann das nicht: /iphone-17-pro und
    /handyvertrag-ohne-laufzeit sind pfadgleich."""
    links = einsundeins.ernte(ee_kategorie, _EE_KATEGORIE)
    assert len(links) == 42
    assert len(set(links)) == 42
    assert _EE_PRODUKT in links
    assert all(l.startswith("https://mobile.1und1.de/") for l in links)
    assert not [l for l in links if "/_catalog/images" in l]
    assert "https://mobile.1und1.de/handyvertrag-ohne-laufzeit" not in links
    assert "https://mobile.1und1.de/smartphone-neuheiten" not in links


def test_einsundeins_ernte_ohne_kacheln_liefert_nichts_und_wirft_nicht():
    """Ein leeres Raster ist ein anderer Zustand als eine nicht gelesene
    Seite. Der Sammler unterscheidet die zwei - eine Ausnahme hier machte
    sie ununterscheidbar."""
    assert einsundeins.ernte("<html><body><a href='/x'>x</a></body></html>",
                             _EE_KATEGORIE) == []
    assert einsundeins.ernte("", _EE_KATEGORIE) == []


def test_einsundeins_liest_den_monatspreis_des_buendels(ee_produkt):
    saetze = einsundeins.lies(ee_produkt, _EE_PRODUKT)
    assert len(saetze) == 1
    satz = saetze[0]
    assert satz["monatspreis"] == 44.99
    assert satz["tarif"] == "1&1 All-Net-Flat S"
    assert satz["laufzeit_monate"] == 36
    assert satz["speicher_gb"] == 256
    assert satz["farbe"] == "cosmic orange"
    assert satz["waehrung"] == "EUR"


def test_einsundeins_traegt_keinen_barpreis(ee_produkt):
    """44,99 EUR ist kein Preis fuer ein Telefon. Es gibt bei 1&1 keinen
    Barpreis - und eine Zahl, die es nicht gibt, wird nicht gerechnet."""
    assert einsundeins.lies(ee_produkt, _EE_PRODUKT)[0]["preis"] is None


def test_einsundeins_genau_eine_variante_je_seite(ee_produkt):
    """Die Seite bepreist die VORAUSGEWAEHLTE Variante. Drei Farben mal drei
    Speicherstufen daraus zu vervielfaeltigen hiesse, acht von neun Saetzen
    zu erfinden."""
    assert len(einsundeins.lies(ee_produkt, _EE_PRODUKT)) == 1


def test_einsundeins_ohne_tarif_in_der_beschreibung_faellt_der_satz():
    html = ('<script type="application/ld+json">{"@type": "Product", '
            '"name": "iPhone 17 Pro", "description": "Das neue iPhone", '
            '"offers": {"priceCurrency": "EUR", "price": "44.99"}}</script>')
    assert einsundeins.lies(html, _EE_PRODUKT) == []


def test_einsundeins_kaputter_ldjson_block_kippt_die_seite_nicht():
    """Shops liefern regelmaessig einen kaputten Block neben heilen - bei
    1&1 stehen FAQPage, WebSite und Organization daneben."""
    html = ('<script type="application/ld+json">{kaputt</script>'
            '<script type="application/ld+json">{"@type": "Product", '
            '"name": "iPhone 17 Pro", "description": "iPhone 17 Pro mit '
            '1&amp;1 All-Net-Flat S", "offers": {"priceCurrency": "EUR", '
            '"price": "44.99"}}</script>')
    saetze = einsundeins.lies(html, _EE_PRODUKT)
    assert len(saetze) == 1
    assert saetze[0]["tarif"] == "1&1 All-Net-Flat S"


def test_einsundeins_leere_seite_liefert_nichts():
    assert einsundeins.lies("", _EE_PRODUKT) == []
    assert einsundeins.lies("<html><body>nichts</body></html>", _EE_PRODUKT) == []


def test_einsundeins_laufzeit_kommt_aus_der_seite_und_wird_nicht_gesetzt():
    """Ohne `currentHardwareOfferDuration` bleibt die Laufzeit leer. 36 als
    Vorgabe waere eine Bindungsdauer, die niemand gemessen hat."""
    html = ('<script type="application/ld+json">{"@type": "Product", '
            '"name": "iPhone 17 Pro", "description": "iPhone 17 Pro mit '
            '1&amp;1 All-Net-Flat S", "offers": {"price": "44.99"}}</script>')
    assert einsundeins.lies(html, _EE_PRODUKT)[0]["laufzeit_monate"] is None


def test_buendelpreis_ohne_zuzahlung_landet_nicht_in_der_barpreisspalte(ee_produkt):
    """Die Weiche, die den ganzen Anbieter moeglich macht: ein Buendel
    braucht seit dem 04.09.2026 keine Zuzahlung mehr, um gespeichert zu
    werden - aber sein Monatspreis bleibt aus `preis_ohne_vertrag` heraus."""
    satz = einsundeins.lies(ee_produkt, _EE_PRODUKT)[0]
    felder = _preisfelder(None, satz)
    assert felder["preis_ohne_vertrag"] is None
    assert felder["preis_mit_vertrag_ab"] == 44.99
    assert felder["tarif_referenz"] == "1&1 All-Net-Flat S"
    assert felder["laufzeit_monate"] == 36


def test_einsundeins_landet_als_buendellistung_im_bestand(katalog, farben,
                                                          ee_kategorie, ee_produkt):
    """Der ganze Weg: Kachelernte, eine Produktseite, eine Buendellistung -
    mit Tarif und Laufzeit, ohne Barpreis."""
    anbieter = Anbieter(
        name="1&1", typ="netzbetreiber", methode="einsundeins_buendel",
        basis_url="https://mobile.1und1.de", rate_limit_sekunden=0,
        max_produkte=45,
        einstiege=[Einstieg(url=_EE_KATEGORIE, kind="static")])

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent:*\nDisallow:/xml/\nDisallow:/static/\n")
        if url == _EE_KATEGORIE:
            return (200, ee_kategorie)
        if url == _EE_PRODUKT:
            return (200, ee_produkt)
        return (200, "<html></html>")

    bilanz = sammle_anbieter(anbieter, katalog, farben, hole, "2026-09-04",
                             RobotsWaechter(hole=hole),
                             datetime(2026, 9, 4, 3, tzinfo=timezone.utc))
    # 42 Kacheln, alle abgerufen - der Deckel von 45 greift nicht.
    assert bilanz.gedeckelt == []
    treffer = [l for l in bilanz.listungen if l.quelle_url == _EE_PRODUKT]
    assert len(treffer) == 1
    assert treffer[0].preis_ohne_vertrag is None
    assert treffer[0].preis_mit_vertrag_ab == 44.99
    assert treffer[0].tarif_referenz == "1&1 All-Net-Flat S"
    assert treffer[0].laufzeit_monate == 36


def test_die_ausgelieferte_konfiguration_haelt_was_der_hinweis_verspricht():
    """Beide Anbieter sind aktiv, tragen einen GEBAUTEN Adapter und
    erklaeren sich weiterhin woertlich auf /geraete-quellen.html."""
    quellen = lade_quellen(_WURZEL)
    for name, methode in (("Telekom", "telekom_kategorie"),
                          ("1&1", "einsundeins_buendel")):
        anbieter = quellen.nach_name(name)
        assert anbieter.aktiv is True, name
        assert anbieter.crawlbar is True, name
        assert anbieter.methode == methode, name
        # `grund` beantwortet "warum NICHT aktiv" - die Frage stellt sich
        # nicht mehr. Der Messstand steht in `hinweis` und damit weiterhin
        # auf der Quellenseite.
        assert anbieter.grund == "", name
        assert "04.09.2026" in anbieter.hinweis, name
