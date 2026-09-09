"""Die Bündellesart der 1&1-Geräteseite: Default-Tarif je Speichergröße (B4)
und die Einmalzahlung je Variante (S2-C, 09.09.2026).

WAS HIER GEPRÜFT WIRD, UND WARUM ES EINE EIGENE DATEI IST
--------------------------------------------------------
Bis zum 08.09.2026 waren 1&1-Bündel nur über den Listung-Umweg in der
TCO-Tafel (`geraete_tco_karten.buendel_aus_listungen`) - OHNE tarif_id und
damit ohne Band: kein Datenbanksatz, kein Radar-Paar. B4 liest dieselbe
Geräteseite, die der Ernte-Weg ohnehin holt, mit einer zweiten Lesart:
`hwdVariantsPrices` preist den DEFAULT-Tarif über alle Farben und
Speichergrößen serverseitig (Cent-Beträge), der Tarifname steht in
`<span id="tariff-description">`, die Laufzeit in
`window.currentHardwareOfferDuration`.

DIE FIXTURES SIND GESPEICHERTE ECHTE ABRUFE
--------------------------------------------
`einsundeins_produktseite_iphone_17_pro.html.gz` ist die Antwort auf
`/iphone-17-pro` (08.09.2026, HTTP 200, 327 KB, Absender
`TelcoRadar/1.0`, reiner HTTP-GET): Preiskarte mit 3 Farben × 3
Speichergrößen (44,99 / 51,99 / 58,99 €) je Farbe identisch - 3 Sätze,
Einmalzahlungen 360,– / 450,– / 530,– €.
`einsundeins_produktseite_galaxy_a57.html.gz` ist die A57-Seite
(339 KB, 2 Speichergrößen: 25,99 / 27,99 €; Einmalzahlungen 140,– / 160,– €).
`einsundeins_tarifdetails_anf_s.html.gz` ist der Tarifdetails-Iframe zu
`chosenTariff=tariff-anf-s-mvl&chosenDevice=hw-apple-iphone-17-pro`
(09.09.2026, HTTP 200, 48 112 B, Absender `TelcoRadar/1.0`): die
Bereitstellungsgebühr steht in seiner Tariftabelle (Modulkopf des Adapters).
S2-C liest aus DEMSELBEN Geräteseiten-Response zwei Felder mehr:
`hwdVariantsOneOffPaymentFees` (Geräte-Einmalzahlung je Farbe×Speicher,
deutsche Betragszeichenketten wie "360,–") und den Tarifdetails-Link
(`data-iframe`), hinter dem die BEREITSTELLUNGSGEBÜHR des Tarifs steht
("Tarif mit Smartphone: 39,90 €") - Erhebung per `ergaenze_buendel`-Haken,
EIN GET je Tarif-Slug.

DIE DREI REGELN, AN DENEN DIESES PAKET SCHEITERN KANN
-----------------------------------------------------
1. **§ 13.2: der Monatsbetrag wird NICHT aufgeteilt.** Der Datalayer der
   Seite nennt Hardware-Rate 45,00 und Tarif 14,99 - zusammen 59,99, während
   das Bündel 44,99 kostet. Die Zahlen widersprechen sich; wer sie als
   `geraet_monatsrate`/`tarif_monatlich` speicherte, spalte einen Betrag
   ohne Beleg. Der Satz trägt NUR `buendel_monatlich`.
2. **Zubehör-Schüssel verfallen über ihre FORM.** Die `-bundle-hw-…`-Keys
   der Preiskarte sind AirPods-Zusatzbuendel, kein Tarifbund - ihr Preis
   steht HÖHER (53,99). Verworfen wird über den Schlüssel (das
   Anführungszeichen direkt hinter der Speicherzahl), nie über den Betrag.
3. **Fehlend bleibt fehlend (E1).** Der Einmalzahlungs-Block steht hinter
   `currentHardwareOfferDuration === '36'`; fehlt er, bleibt
   `geraet_zuzahlung` leer - "nicht genannt" ist keine Zahl und kein 0,00.
   Dasselbe gilt für die Bereitstellungsgebühr: Ein Iframe ohne die Zeile
   (oder ein gescheiterter Abruf) setzt KEINEN Default.
"""
import gzip
import json
from pathlib import Path

import pytest

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import (
    ADAPTER,
    GeraeteAbrufFehler,
    sammle_anbieter,
)
from telco_radar.collect.geraete.einsundeins import (
    bereitstellungsgebuehr,
    ergaenze_bereitstellungsgebuehr,
    lies_buendel,
)
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog
from telco_radar.report.geraete_tco_band import tarif_baender
from telco_radar.report.geraete_tco_karten import modelle
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import POSTEN_ZUZAHLUNG, Buendel, tco_24

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

_IPHONE_URL = "https://mobile.1und1.de/iphone-17-pro"
_A57_URL = "https://mobile.1und1.de/samsung-galaxy-a57"
_IFRAME_URL = ("https://mobile.1und1.de/details-all-net-flat-preisliste"
               "?chosenTariff=tariff-anf-s-mvl&chosenNet=1u1"
               "&chosenDevice=hw-apple-iphone-17-pro&color=COSMIC_ORANGE"
               "&size=256&lightbox=true&bk=false")

_ROBOTS_FREI = (200, "User-agent: *\n")


def _fixture(name: str) -> str:
    pfad = _FIX / name
    if pfad.suffix == ".gz":
        return gzip.open(pfad, "rb").read().decode("utf-8", "replace")
    return pfad.read_text(encoding="utf-8")


def _saetze():
    return lies_buendel(_fixture("einsundeins_produktseite_iphone_17_pro.html.gz"),
                        url=_IPHONE_URL)


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(_WURZEL)


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


# ==========================================================================
# lies_buendel(): Struktur der Sätze
# ==========================================================================

def test_drei_saetze_je_speichergroesse_und_eine_je_farbe():
    """Die Karte trägt 9 Schlüssel ohne Zubehör-Segment (3 Farben × 3
    Speicher); je Speichergröße bleibt EIN Satz - der Preis ist bei jeder
    Farbe derselben Größe identisch (gemessen), die erste Farbe vertritt
    ihn (dieselbe Dedupe-Regel wie congstar B3)."""
    saetze = _saetze()
    assert [s["speicher_gb"] for s in saetze] == [256, 512, 1024]
    assert len({(s["speicher_gb"], s["farbe"]) for s in saetze}) == 3


def test_tarifname_slug_und_laufen_kommen_aus_der_antwort():
    """Tarifname (`tariff-description`-Span), Slug (Tarifdetails-Link der
    Seite) und Laufzeit (`currentHardwareOfferDuration`) stehen alle in
    derselben Antwort - 1&1 braucht anders als Vodafone keinen zweiten
    Endpunkt und keinen Auflöse-Haken."""
    for s in _saetze():
        assert s["tarif_name"] == "1&1 All-Net-Flat S"
        assert s["tarif_slug"] == "tariff-anf-s-mvl"
        assert s["laufzeit_monate"] == 36


def test_der_iphone_satz_nach_rechnung():
    """44,99 €/Monat über 36 Monate: TCO-24 = 24 × 44,99 = 1.079,76 €,
    danach noch offen 12 × 44,99 = 539,88 €. `tco_24()` und Handrechnung
    müssen exakt gleich sein - die zusammen-Formel ist der Bewährungsfall
    aus TCO24-1, hier an einem echten Satz des Bestands."""
    s = next(x for x in _saetze() if x["speicher_gb"] == 256)
    b = Buendel(sku_id="apple-iphone-17-pro-256gb-cosmic-orange",
                anbieter="1&1", tarif_name=s["tarif_name"],
                buendel_monatlich=s["buendel_monatlich"],
                laufzeit_monate=s["laufzeit_monate"])
    tco = tco_24(b)
    assert s["buendel_monatlich"] == 44.99
    assert tco.gesamt == pytest.approx(24 * 44.99)
    assert tco.restbetrag == pytest.approx(12 * 44.99)
    assert tco.monatlich == pytest.approx(44.99)
    assert tco.belastbar


def test_keine_vorzeitige_aufspaltung_des_monatsbetrags():
    """§ 13.2: der Satz trägt NUR den kombinierten Betrag. Die
    Datalayer-Aufteilung der Fixture (Hardware 45,00 + Tarif 14,99)
    widerspricht dem Bündelpreis (44,99) - keine der beiden Zahlen darf
    als `geraet_monatsrate` oder `tarif_monatlich` in den Satz."""
    roh = _fixture("einsundeins_produktseite_iphone_17_pro.html.gz")
    assert '"cost":45.00' in roh, \
        "die Fixture muss die Datalayer-Hardware-Rate tragen (Gegenprobe)"
    assert '"cost":14.99' in roh, \
        "die Fixture muss den Datalayer-Tarifpreis tragen (Gegenprobe)"
    for s in _saetze():
        assert "tarif_monatlich" not in s
        assert "geraet_monatsrate" not in s
        assert s["buendel_monatlich"] not in (45.00, 14.99)


def test_zubehoer_schluessel_verfallen_ueber_die_form():
    """Die `-bundle-…`-Keys der Karte sind Zubehör (höherer Preis, hier
    53,99/49,99) - sie dürfen auch dann nicht gelesen werden, wenn ihr
    Preis der NIEDRIGERE wäre. Gegenprobe an der echten Fixture: kein Satz
    trägt einen der Zubehör-Beträge."""
    saetze = _saetze()
    zubehoer = {5399, 4999, 6099, 5699, 6799, 6399}    # Cent, gemessen
    for s in saetze:
        assert round(s["buendel_monatlich"] * 100) not in zubehoer
    # Und der konstruierte Fall: ein Zubehör-Key mit STOLZ niedrigem Preis
    # verführt - er fällt trotzdem, weil das Anführungszeichen direkt
    # hinter der Speicherzahl gefordert wird.
    seite = ('<script>function setHwdPrices() { hwdVariantsPrices = {'
             "'product-SCHWARZ-128': [1599,],"
             "'product-SCHWARZ-128-bundle-hw-x-309a2ab835d0-WEISS-0': [199,],"
             '}; }</script>'
             '<span id="tariff-description">1&1 All-Net-Flat S</span>'
             "<script>window.currentHardwareOfferDuration = '36';</script>"
             '<script type="application/ld+json">{"@type":"Product",'
             '"name":"Testgerät","brand":"Testmarke"}</script>')
    satz = lies_buendel(seite, url="https://mobile.1und1.de/testgeraet")
    assert len(satz) == 1
    assert satz[0]["buendel_monatlich"] == 15.99


# ==========================================================================
# S2-C: die Geräte-Einmalzahlung (`hwdVariantsOneOffPaymentFees`)
# ==========================================================================

def test_die_einmalzahlung_je_variante_aus_der_echten_seite():
    """S2-C, Kriterium 1b: `hwdVariantsOneOffPaymentFees` steht in
    DEMSELBEN Response wie die Preiskarte, geschlüsselt über dieselben
    Produkt-Schlüssel. Werte der echten iPhone-Fixture: 360/450/530 €
    (der Spike nennt für TIEFBLAU/1024 wörtlich "530,–")."""
    assert [(s["speicher_gb"], s["geraet_zuzahlung"])
            for s in _saetze()] == [(256, 360.0), (512, 450.0), (1024, 530.0)]
    # Zweite echte Seite: die A57-Fixture, 140/160 €
    saetze = lies_buendel(
        _fixture("einsundeins_produktseite_galaxy_a57.html.gz"), url=_A57_URL)
    assert [(s["speicher_gb"], s["geraet_zuzahlung"]) for s in saetze] == \
        [(128, 140.0), (256, 160.0)]


def test_fehlender_block_laesst_die_einmalzahlung_offen():
    """E1: die Zuweisung steht hinter `currentHardwareOfferDuration
    === '36'`. Fehlt der Block (andere Laufzeit, anderes Angebot), bleibt
    `geraet_zuzahlung` None - "nicht genannt" ist keine Zahl und kein 0,00.
    Der Bündelsatz selbst bleibt vollständig: der Monatspreis steht."""
    seite = ('<script>function setHwdPrices() { hwdVariantsPrices = {'
             "'product-SCHWARZ-128': [1599,],}; }</script>"
             '<span id="tariff-description">1&1 All-Net-Flat S</span>'
             "<script>window.currentHardwareOfferDuration = '24';</script>"
             '<script type="application/ld+json">{"@type":"Product",'
             '"name":"Testgerät","brand":"Testmarke"}</script>')
    assert "hwdVariantsOneOffPaymentFees" not in seite, \
        "die Gegenprobe braucht eine Seite OHNE den Block"
    saetze = lies_buendel(seite, url="https://mobile.1und1.de/testgeraet")
    assert len(saetze) == 1
    assert saetze[0]["geraet_zuzahlung"] is None
    assert saetze[0]["buendel_monatlich"] == 15.99


def test_die_einmalzahlung_gilt_nur_fuer_die_eigene_variante():
    """Der Schlüssel ist (Farbe in ROHSCHREIBWEISE, GB) - derselbe Schlüssel
    wie die Preiskarte. Fehlt der der übernehmenden ersten Farbe, bleibt
    das Feld offen: der Betrag einer ANDEREN Farbe derselben Größe wäre
    eine Annahme, keine Messung."""
    seite = ('<script>function setHwdPrices() { hwdVariantsPrices = {'
             "'product-SCHWARZ-128': [1599,],"
             "'product-BLAU-128': [1599,],}; }</script>"
             "hwdVariantsOneOffPaymentFees = {"
             "'product-BLAU-128': \"140,–\",};"
             '<span id="tariff-description">1&1 All-Net-Flat S</span>'
             "<script>window.currentHardwareOfferDuration = '36';</script>"
             '<script type="application/ld+json">{"@type":"Product",'
             '"name":"Testgerät","brand":"Testmarke"}</script>')
    saetze = lies_buendel(seite, url="https://mobile.1und1.de/testgeraet")
    assert len(saetze) == 1
    assert saetze[0]["farbe"] == "schwarz"
    assert saetze[0]["geraet_zuzahlung"] is None


def test_die_einmalzahlung_steht_in_der_leitzahl():
    """S2-C, Kriterium 3: die Leitzahl rechnet die Einmalzahlung MIT -
    24 x 44,99 + 360 + 39,90 = 1.479,66 €. Ohne sie steht sie als LÜCKE
    da (`tco_24`), nicht als 0,00 - dieselbe Regel wie beim
    Anschlusspreis. Ohne BEIDE bleibt die Zahl, die der Anbieter nennt."""
    komplett = Buendel(
        sku_id="apple-iphone-17-pro-256gb-cosmic-orange", anbieter="1&1",
        tarif_name="1&1 All-Net-Flat S", buendel_monatlich=44.99,
        geraet_zuzahlung=360.0, anschlusspreis=39.9, laufzeit_monate=36)
    tco = tco_24(komplett)
    assert tco.gesamt == pytest.approx(24 * 44.99 + 360.0 + 39.9)
    assert POSTEN_ZUZAHLUNG not in tco.luecken
    ohne_zuzahlung = Buendel(
        sku_id="apple-iphone-17-pro-256gb-cosmic-orange", anbieter="1&1",
        tarif_name="1&1 All-Net-Flat S", buendel_monatlich=44.99,
        anschlusspreis=39.9, laufzeit_monate=36)
    tco_offen = tco_24(ohne_zuzahlung)
    assert POSTEN_ZUZAHLUNG in tco_offen.luecken
    assert tco_offen.gesamt == pytest.approx(24 * 44.99 + 39.9)


# ==========================================================================
# S2-C: die Bereitstellungsgebühr aus dem Tarifdetails-Iframe
# ==========================================================================

def test_tarifdetails_adresse_kommt_aus_dem_data_iframe_attribut():
    """Die Adresse nimmt der Adapter unverändert aus dem `data-iframe`-
    Attribut der Geräteseite, aufgelöst gegen die Seiten-URL - nur
    verlinkte Adressen, nichts gerechnet. Sie steht auf jedem Satz."""
    for s in _saetze():
        assert s["tarifdetails_url"] == _IFRAME_URL


def test_bereitstellungsgebuehr_mit_smartphone_aus_dem_echten_iframe():
    """S2-C, Kriterium 2: der echte Iframe nennt beide Beträge wortgleich
    ("ohne Smartphone: 19,90 € / mit Smartphone: 39,90 €"). Erhoben wird
    der MIT-Smartphone-Preis - das Bündel hat immer ein Gerät; der 19,90-
    Preis gehört zum SIM-only-Tarif und steht im Tarifbestand."""
    assert bereitstellungsgebuehr(
        _fixture("einsundeins_tarifdetails_anf_s.html.gz")) == 39.9


def test_iframe_ohne_die_zeile_setzt_nichts():
    """E1: ein Iframe ohne die Zeile ist eine gültige Tarifseite - None,
    kein Default, keine 0,00."""
    assert bereitstellungsgebuehr(
        "<html><body>Tariftabelle ohne Bereitstellung</body></html>") is None


def _gebuhr_saetze() -> list[dict]:
    """Drei 1&1-Rohsätze auf einem Slug, einer ohne Slug - die Bauform,
    mit der `sammle_anbieter` die Bündel abliefert."""
    basis = {"quelle": "einsundeins_buendel",
             "tarif_slug": "tariff-anf-s-mvl",
             "tarifdetails_url": _IFRAME_URL,
             "buendel_monatlich": 44.99}
    return [dict(basis), dict(basis), {**basis, "tarif_slug": "",
                                       "tarifdetails_url": ""}]


def test_ergaenze_holt_ein_get_je_slug_und_setzt_alle_saetze():
    """EIN GET JE TARIF-SLUG, nicht je Gerät: die Gebühr ist tarif- und
    geräteunabhängig (Modulkopf), alle drei Sätze teilen sich den Abruf.
    Der Satz ohne Slug bleibt unangetastet - ohne Adresse kein Abruf."""
    abrufe: list[str] = []
    iframe = _fixture("einsundeins_tarifdetails_anf_s.html.gz")

    def hole(url, kopfzeilen=None):
        abrufe.append(url)
        return 200, iframe

    saetze = _gebuhr_saetze()
    gesetzt = ergaenze_bereitstellungsgebuehr(hole, {}, saetze)
    assert abrufe == [_IFRAME_URL]
    assert gesetzt == 2
    assert saetze[0]["anschlusspreis"] == 39.9
    assert saetze[1]["anschlusspreis"] == 39.9
    assert "anschlusspreis" not in saetze[2]


def test_gescheiterter_abruf_setzt_keinen_default():
    """E1: ein Iframe mit HTTP 500 oder einer Ausnahme lässt die Sätze
    UNVERÄNDERT - kein Default, und ein einziger toter Iframe darf die
    Bündel des Laufs nicht kosten."""
    def hole_500(url, kopfzeilen=None):
        return 500, "server error"

    def hole_wirft(url, kopfzeilen=None):
        raise RuntimeError("netz weg")

    for hole in (hole_500, hole_wirft):
        saetze = _gebuhr_saetze()
        assert ergaenze_bereitstellungsgebuehr(hole, {}, saetze) == 0
        assert all("anschlusspreis" not in s for s in saetze)


def test_nur_einsundeins_saetze_werden_angefasst():
    """Hausregel: ein Satz eines ANDEREN Anbieters in derselben Liste
    bleibt unberührt - die Gebühr ist eine 1&1-Angabe, und die Felder
    anderer Anbieter stehen nicht zur Debatte."""
    fremd = {"quelle": "o2_buendel", "tarif_slug": "tariff-anf-s-mvl",
             "tarifdetails_url": _IFRAME_URL, "buendel_monatlich": 19.99}
    iframe = _fixture("einsundeins_tarifdetails_anf_s.html.gz")

    def hole(url, kopfzeilen=None):
        return 200, iframe

    ergaenze_bereitstellungsgebuehr(hole, {}, [fremd])
    assert "anschlusspreis" not in fremd


# ==========================================================================
# S2-C: gemessene Bündel schlagen die Listungs-Brücke desselben Angebots
# ==========================================================================

def test_die_listung_verdraengt_das_gemessene_buendel_nicht(katalog):
    """Der Befund des ersten Renderns nach S2-C: 1&1 steht dasselbe Angebot
    ZWEIMAL im Bestand - als Listung (nur der Monatsbetrag, aus der Zeit
    vor der Bündellesart) und als gemessenes Bündel (mit Einmalzahlung und
    Bereitstellungsgebühr). Die Angebots-Dedupe nahm die GÜNSTIGSTE Karte,
    und das war die Listung - sie ist im Ø/Monat billiger, weil ihr Posten
    FEHLEN. Sie verdrängte das gemessene Angebot samt tarif_id; im
    Wettbewerbs-Radar standen alle 1&1-Zeilen als Band-Mismatch da.

    Jetzt gilt QUELLE vor Preis: das gemessene Bündel gewinnt, egal was
    die Listung kostet. Die Listung allein bleibt eine vollgültige Karte
    (sie ist die Brücke für Anbieter ohne Bündel-Adapter) - hier nur
    keine zweite mehr."""
    sku = "apple-iphone-15-128gb-schwarz"
    gemessen = Buendel(
        sku_id=sku, anbieter="1&1", tarif_name="1&1 All-Net-Flat S",
        tarif_id="11:1-1-all-net-flat-s",
        buendel_monatlich=44.99, geraet_zuzahlung=360.0,
        anschlusspreis=39.9, laufzeit_monate=36, zustand="neu",
        quelle_url=_IPHONE_URL, abgerufen_am="2026-09-09")
    listung = {"sku_id": sku, "device_id": "apple-iphone-15",
               "anbieter": "1&1", "speicher_gb": 128, "zustand": "neu",
               "preis_mit_vertrag_ab": 44.99,
               "tarif_referenz": "1&1 All-Net-Flat S",
               "laufzeit_monate": 36,
               "quelle_url": _IPHONE_URL, "abgerufen_am": "2026-09-08"}
    ergebnis = modelle([gemessen], [listung], referenzen=[], tarife={},
                       katalog=katalog)
    karten = [k for m in ergebnis["modelle"] for k in m["karten"]
              if k["anbieter"] == "1&1"]
    assert len(karten) == 1
    assert karten[0]["zuzahlung"] == 360.0
    assert karten[0]["anschlusspreis"] == 39.9
    assert karten[0]["tarif_id"] == "11:1-1-all-net-flat-s"
    # Gegenprobe: OHNE gemessenes Bündel bleibt die Listung die Karte -
    # die Brücke steht weiter (derselbe Aufruf, leerer erster Parameter).
    nur_listung = modelle([], [listung], referenzen=[], tarife={},
                          katalog=katalog)
    karten2 = [k for m in nur_listung["modelle"] for k in m["karten"]
               if k["anbieter"] == "1&1"]
    assert len(karten2) == 1
    assert karten2[0]["zuzahlung"] is None


def test_zwei_preise_einer_groesse_bleiben_beim_ersten():
    """Gemessen trägt jede Farbe derselben Größe denselben Preis. Tut sie
    es nicht, bleibt der ERSTE Eintrag - still die billigste Farbe zu
    nehmen wäre eine Auswahl ohne Beleg."""
    seite = ('<script>function setHwdPrices() { hwdVariantsPrices = {'
             "'product-SCHWARZ-128': [1599,],"
             "'product-BLAU-128': [1399,],"
             '}; }</script>'
             '<span id="tariff-description">1&1 All-Net-Flat S</span>'
             "<script>window.currentHardwareOfferDuration = '36';</script>"
             '<script type="application/ld+json">{"@type":"Product",'
             '"name":"Testgerät","brand":"Testmarke"}</script>')
    satz = lies_buendel(seite, url="https://mobile.1und1.de/testgeraet")
    assert len(satz) == 1
    assert satz[0]["buendel_monatlich"] == 15.99
    assert satz[0]["farbe"] == "schwarz"


def test_seite_ohne_preiskarte_wirft():
    """Eine Geräteseite ohne `hwdVariantsPrices` ist ein geändertes Markup
    - ein leeres Ergebnis wäre die falsche Meldung dafür (dasselbe Muster
    wie bei o2, Telekom und congstar)."""
    with pytest.raises(GeraeteAbrufFehler):
        lies_buendel("<html><body>ohne Karte</body></html>", url="x")


def test_ohne_tarifnamen_gibt_es_keinen_satz():
    """Ein Bündel ohne benannten Tarif ist bedeutungslos (`lies()` wirft
    ihn aus demselben Grund weg) - hier als leere Ausbeute, nicht als
    Ausnahme, denn die Karte unter dem Namen kann noch liefern."""
    seite = ('<script>function setHwdPrices() { hwdVariantsPrices = {'
             "'product-SCHWARZ-128': [1599,],}; }</script>"
             "<script>window.currentHardwareOfferDuration = '36';</script>")
    assert lies_buendel(seite, url="x") == []


# ==========================================================================
# Der Weg in den Bestand: aus_rohsaetzen() gegen den echten tarife.jsonl
# ==========================================================================

def test_der_ganze_weg_bis_zum_buendel_mit_echtem_bestand():
    """Ende zu Ende gegen den echten tarife.jsonl-Bestand: der Name der
    Seite („1&1 All-Net-Flat S") löst mit Güte HOCH auf - der Vorbefund
    „1&1-tarif_id löst nie auf ein Datenvolumen auf" traf die Listung ohne
    tarif_id, nicht diesen Weg. Der aufgelöste Tarif trägt 10 GB und damit
    das Band Klein: die Voraussetzung für Radar-Paare."""
    bestand = Tarifbestand.aus_datei(_WURZEL / "data" / "state" / "tarife.jsonl")
    rohsaetze = [{**s, "anbieter": "1&1",
                  "sku_id": f"sku-{i}", "quelle_url": s["url"]}
                 for i, s in enumerate(_saetze())]
    bilanz = aus_rohsaetzen(rohsaetze, bestand, "2026-09-08")
    assert len(bilanz.buendel) == 3, (
        f"{bilanz.ohne_tarif} ohne auflösbaren Tarif, "
        f"häufigste: {bilanz.offene_tarife}")
    assert all(b.tarif_id == "11:1-1-all-net-flat-s" for b in bilanz.buendel)
    assert all(b.tarif_id_guete == "hoch" for b in bilanz.buendel)
    baender = tarif_baender(bestand.je_id)
    assert baender["11:1-1-all-net-flat-s"] == "klein"
    b = next(x for x in bilanz.buendel if x.sku_id == "sku-0")
    assert b.buendel_monatlich == 44.99
    assert b.laufzeit_monate == 36


def test_aus_rohsaetzen_reicht_buendel_monatlich_durch():
    """Der Durchgriff: ohne die Zeile in `aus_rohsaetzen` käme ein Satz
    mit EINEM Monatsbetrag still PREISLOS durch die Stufe - `Buendel`
    nimmt den Betrag nur an, wenn ihn jemand durchreicht (derselbe
    Fehlertyp wie die Positivliste `_MESSFELDER` im Store)."""
    bestand = Tarifbestand([{
        "tarif_id": "11:1-1-all-net-flat-s", "anbieter": "1&1",
        "name": "1&1 All-Net-Flat S", "grundgebuehr": 14.99,
    }])
    bilanz = aus_rohsaetzen([{
        "anbieter": "1&1", "tarif_name": "1&1 All-Net-Flat S",
        "sku_id": "apple-iphone-17-pro-256gb-cosmic-orange",
        "buendel_monatlich": 44.99, "laufzeit_monate": 36,
        "quelle_url": _IPHONE_URL,
    }], bestand, "2026-09-08")
    assert len(bilanz.buendel) == 1
    assert bilanz.buendel[0].buendel_monatlich == 44.99
    assert tco_24(bilanz.buendel[0]).gesamt == pytest.approx(1079.76)


def test_der_zustand_kommt_als_neu_aus_dem_titelweg(katalog, farben):
    """1&1 nennt keinen strukturierten Zustand; die Sätze laufen durch
    denselben `lies_listung`-Weg wie jede Listung und erben dessen
    Erkennung (kein Kennzeichen in Titel/Farbe/Hinweis -> neu). Ein
    Bündel ohne belegten Zustand wäre in der Tafel nicht vergleichbar
    (QA-Befund B1)."""
    # Die echte A57-Seite, NUR der Farbschlüssel der 128-GB-Zeile trägt ein
    # Kennzeichen (o2 schreibt "erneuert" genauso in die Farbe). Der 256-GB-
    # Satz bleibt sauber - ein Lauf zeigt damit beide Richtungen: ohne
    # Kennzeichen wird "neu" GELEITET (Titelweg), nicht vergeblich
    # weggefasst, und mit Kennzeichen wäre ein fester "neu"-Default rot.
    seite = _fixture("einsundeins_produktseite_galaxy_a57.html.gz").replace(
        "AWESOME_GRAY-128", "GRAU_ERNEUERT-128")

    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        if url.endswith("/smartphones"):
            return 200, _katalogseite(_A57_URL)
        return 200, seite

    bilanz = sammle_anbieter(_anbieter(), katalog, farben, hole,
                             "2026-09-08", RobotsWaechter(hole=hole))
    assert bilanz.status == "ok"
    assert [b["zustand"] for b in bilanz.buendel] == ["refurbished", "neu"]
    # Der Zustand ist dieselbe Erkennung, aus der die `-refurbished`-Strecke
    # der SKU entsteht - ohne sie wäre die Tafel-Zeile nicht vergleichbar.
    assert "refurbished" in bilanz.buendel[0]["sku_id"]
    assert "refurbished" not in bilanz.buendel[1]["sku_id"]


# ==========================================================================
# Die Verdrahtung: sammle_anbieter() auf den Produktseiten des Ernte-Wegs
# ==========================================================================

def _anbieter():
    return Anbieter(
        name="1&1", typ="netzbetreiber", gruppe="United Internet",
        methode="einsundeins_buendel", basis_url="https://mobile.1und1.de",
        rate_limit_sekunden=0,
        einstiege=[Einstieg(url="https://mobile.1und1.de/smartphones",
                            label="Smartphones", kind="static")])


def _katalogseite(ziel: str) -> str:
    """Eine Kategorieseite mit EINER Kachel - die Klasse
    `hardware-box__heading` ist die Auswahl, die 1&1 selbst trifft."""
    return (f'<a class="hardware-box__heading" href="{ziel}">Gerät</a>')


def test_sammle_liefert_listung_und_buendel_aus_einer_antwort(katalog, farben):
    """B1-Muster für 1&1: dieselbe Produktseiten-Antwort liefert die
    LISTUNG (ld+json) und die BÜNDEL je Speichergröße (Preiskarte). Die
    Produktseite wird GENAU EINMAL abgerufen - kein zweiter Request für
    die zweite Lesart."""
    abrufe: list[str] = []

    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        if url.endswith("/smartphones"):
            return 200, _katalogseite(_A57_URL)
        abrufe.append(url)
        return 200, _fixture("einsundeins_produktseite_galaxy_a57.html.gz")

    bilanz = sammle_anbieter(_anbieter(), katalog, farben, hole,
                             "2026-09-08", RobotsWaechter(hole=hole))
    assert bilanz.status == "ok"
    assert abrufe == [_A57_URL]
    assert len(bilanz.listungen) == 1          # die vorausgewählte Variante
    assert len(bilanz.buendel) == 2            # 128 GB und 256 GB
    b = bilanz.buendel[0]
    assert b["anbieter"] == "1&1"
    assert b["tarif_name"] == "1&1 All-Net-Flat S"
    assert b["buendel_monatlich"] == 25.99
    assert b["zustand"] == "neu"
    assert b["quelle_url"] == _A57_URL


def test_adapter_registry_traegt_den_buendelhaken():
    adapter = ADAPTER["einsundeins_buendel"]
    assert adapter.lies_buendel is not None
    # Die zweite Lesart läuft auf den Produktseiten des Ernte-Wegs MIT -
    # die Bündel stehen in derselben Antwort, ein eigener `kind: buendel`-
    # Einstieg (o2/Telekom/congstar) wäre ein zweiter Abruf derselben
    # Adresse. Der Tarifname steht in derselben Antwort, deshalb braucht
    # 1&1 anders als Vodafone keinen `loese_tarifnamen`-Haken.
    assert adapter.buendel_auf_produktseite is True
    assert adapter.loese_tarifnamen is None
    # S2-C: der BETRAGS-Haken - die Bereitstellungsgebühr steht erst im
    # Tarifdetails-Iframe, einer eigenen, von der Geräteseite verlinkten
    # Adresse. Er läuft über dieselbe Stelle der Pipeline wie Vodafones
    # `loese_tarifnamen`: NACH dem Sammeln, VOR `aus_rohsaetzen`.
    assert adapter.ergaenze_buendel is ergaenze_bereitstellungsgebuehr


def test_die_konfiguration_braucht_keinen_buendel_einstieg():
    """1&1 braucht anders als Telekom (tariffId) und congstar (Tarifseiten)
    KEINE eigenen Bündel-Einstiege: die Kategorieseite des Bestands ern-
    tet die Produktseiten, und auf jeder steht die Karte. Ein Eintrag
    `kind: buendel` auf einer Produktadresse wäre ein zweiter Abruf
    derselben Antwort."""
    from telco_radar.geraete_config import lade_quellen
    quellen = lade_quellen(_WURZEL)
    anbieter = next(a for a in quellen.anbieter if a.name == "1&1")
    assert [e.kind for e in anbieter.einstiege] == ["static"]
