"""Die dritte Lesart einer Tarifquelle: die Preiskachel.

WARUM ES SIE GIBT UND WARUM SIE DIE LETZTE WAHL IST
---------------------------------------------------
Ein Pflichtdokument ist rechtlich bewehrt, ein ld+json ist ein Datenformat
- eine Kachel ist Seitengestaltung. Sie kann sich mit einem Redesign
aendern, ohne dass jemand einen Vertrag bricht. Genau deshalb wird sie nur
dort gelesen, wo es die anderen zwei Wege nicht gibt.

Bei o2 gibt es sie nicht (gemessen 04.09.2026):
* `/tarife/handyvertrag-ohne-handy/` traegt genau EIN ld+json, und das ist
  eine `BreadcrumbList`.
* Die Rechtsseite verlinkt DREI PDFs, davon ein einziges zu einem
  Mobilfunktarif.
* Die uebrigen Blaetter liegen unter `/assets/` - ein Pfad, den die fuer
  uns gueltige robots-Gruppe `User-agent: *` sperrt. Sie werden nicht
  geholt.

DIE FIXTURE IST EIN GESPEICHERTER ECHTER ABRUF
----------------------------------------------
`tests/fixtures/tarife/o2_handyvertrag_ohne_handy.html.gz` ist die rohe,
ungekuerzte Antwort von https://www.o2online.de/tarife/handyvertrag-ohne-handy/
vom 04.09.2026 (HTTP 200, 210.306 Bytes, Absender `TelcoRadar/1.0`).
Herkunft und sha256 des entpackten Inhalts stehen in
`tests/fixtures/tarife/_herkunft.json`.

Die kleinen HTML-Schnipsel weiter unten stellen Faelle nach, die sich nicht
ehrlich herbeimessen lassen (ein Werbeteaser mit Preis, eine Kachel ohne
Betrag) - sie geben sich nicht als Messung aus.
"""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from telco_radar.collect import tarif_kacheln
from telco_radar.collect.tarif_crawler import tarif_id
from telco_radar.tarif_model import PREISTYP_LIVE_SHOP

_FIX = Path(__file__).parent / "fixtures" / "tarife"
_DATEI = "o2_handyvertrag_ohne_handy.html.gz"
_URL = "https://www.o2online.de/tarife/handyvertrag-ohne-handy/"


def _seite() -> str:
    with gzip.open(_FIX / _DATEI, "rt", encoding="utf-8") as fh:
        return fh.read()


def _tarife(html=None):
    return tarif_kacheln.tarife_aus_html(
        html if html is not None else _seite(), anbieter="o2",
        seiten_url=_URL, abgerufen_am="2026-09-04")


def _kachel(name="O<sub>2</sub> Mobile S", volumen="15 GB+", preis="19,99 €",
            nachtext="+ einm. Anschlusspreis 39,99 €",
            laufzeit='<div class="radio"><input type="radio" checked="checked"/>'
                     '<label><span class="radio-title">24 Monate</span></label>'
                     '</div>',
            links='<a href="https://www.o2online.de/e-shop/directbuy/offer;'
                  'name=privatkunden-o2-mobile-s-online;shopContext=o2shop"'
                  ' title="Zum Warenkorb">Zum Warenkorb</a>'
                  '<a href="https://www.o2online.de/e-shop/?tarif=o2-mobile-s"'
                  ' title="Handy hinzufügen">Handy hinzufügen</a>') -> str:
    """Eine Kachel in der Form, die o2 am 04.09.2026 wirklich ausliefert."""
    return (
        '<article class="teaser teaser-switchable teaser-with-price">'
        f'<div class="content"><div class="headline">'
        f'<span class="small">{name}</span><br />{volumen}<br />'
        f'<span class="small">5G mit max. 300 MBit/s</span></div>'
        f'<div class="form">{laufzeit}</div></div>'
        f'<div class="pricing"><tef-price class="price">'
        f'<span slot="before">monatlich</span>'
        f'<span slot="price">{preis}</span>'
        f'<span slot="after">{nachtext}</span></tef-price></div>'
        f'<ul class="links">{links}</ul></article>')


# --------------------------------------------------------------------------
# Die gemessene Seite
# --------------------------------------------------------------------------

def test_die_zwoelf_kacheln_der_seite():
    """Zwoelf Tarife, jeder mit Name und Betrag - so gemessen am 04.09.2026."""
    tarife = [t for t, _ in _tarife()]
    assert [(t.name, t.grundgebuehr) for t in tarife] == [
        ("O2 Mobile S", 19.99),
        ("O2 Mobile S Flex", 19.99),
        ("O2 Mobile on Demand M", 19.99),
        ("O2 Mobile on Demand M Flex", 29.99),
        ("O2 Mobile L", 24.99),
        ("O2 Mobile L Flex", 34.99),
        ("O2 Mobile Unlimited S Special", 24.99),
        ("O2 Mobile Unlimited S Special Flex", 34.99),
        ("O2 Mobile Unlimited M", 29.99),
        ("O2 Mobile Unlimited M Flex", 39.99),
        ("O2 Mobile Unlimited L", 39.99),
        ("O2 Mobile Unlimited L Flex", 59.99),
    ]


def test_jeder_satz_traegt_seinen_beleg():
    """`pruefe_belege` ist die Zusage: jede Zahl steht woertlich im Rohtext."""
    for tarif, _ in _tarife():
        tarif.pruefe_belege()
        assert tarif.preistyp == PREISTYP_LIVE_SHOP
        assert tarif.dokument_url == _URL


def test_der_name_traegt_die_tiefgestellte_ziffer_zusammen():
    """`O<sub>2</sub>` ist "O2" und nicht "O 2".

    Der Unterschied ist kein Schoenheitsfehler: der stabile Schluessel
    hiesse sonst `o2:o-2-mobile-unlimited-m-flex`, und der Satz aus dem
    Produktinformationsblatt (`o2:o2-mobile-unlimited-m-flex`) waere ein
    anderer Tarif.
    """
    namen = [t.name for t, _ in _tarife()]
    assert all(n.startswith("O2 ") for n in namen)
    assert tarif_id("o2", "O2 Mobile Unlimited M Flex") == \
        "o2:o2-mobile-unlimited-m-flex"


def test_der_kachelpreis_trifft_das_produktinformationsblatt():
    """Die Gegenprobe, die dieser Lesart ihr Vertrauen gibt.

    "O2 Mobile Unlimited M Flex" steht im ausgelieferten Bestand mit
    39,99 EUR - gelesen aus dem PDF, dem einzigen o2-Mobilfunkblatt, das
    die Rechtsseite verlinkt. Die Kachel derselben Seite nennt denselben
    Betrag. Zwei getrennte Wege, dieselbe Zahl.
    """
    bestand = Path(__file__).resolve().parents[1] / "data" / "state" / "tarife.jsonl"
    aus_blatt = None
    for zeile in bestand.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        satz = json.loads(zeile)
        if satz.get("tarif_id") == "o2:o2-mobile-unlimited-m-flex":
            aus_blatt = satz
    assert aus_blatt is not None, "der PIB-Satz ist aus dem Bestand verschwunden"
    # Der Satz ist vom 10.06.2026 und traegt das Feld `preistyp` noch gar
    # nicht - es gibt es erst seit dem 04.09.2026. Genau dafuer ist sein
    # Vorgabewert gemacht: ein Bestandssatz bleibt beim Wiedereinlesen das,
    # was er war.
    assert aus_blatt.get("preistyp", "dokument") == "dokument"
    # Das Blatt traegt die Jahreszahl im Namen, die Kachel nicht - und
    # genau die wirft `tarif_id` weg. Sonst waeren es zwei Tarife.
    assert aus_blatt["name"] == "O2 Mobile Unlimited M Flex (2026)"

    aus_kachel = [t for t, _ in _tarife()
                  if t.name == "O2 Mobile Unlimited M Flex"]
    assert len(aus_kachel) == 1
    assert aus_kachel[0].grundgebuehr == aus_blatt["grundgebuehr"] == 39.99


def test_flex_kacheln_bekommen_keine_laufzeit():
    """"Monatlich kündbar" ist eine Aussage, aber keine Monatszahl.

    Eine 1 dort waere erfunden - und der Effektivpreis rechnete mit ihr.
    """
    je_name = {t.name: t for t, _ in _tarife()}
    assert je_name["O2 Mobile S"].laufzeit_monate == 24
    assert je_name["O2 Mobile S Flex"].laufzeit_monate is None
    assert je_name["O2 Mobile Unlimited L Flex"].laufzeit_monate is None


def test_unbegrenzte_kacheln_bekommen_kein_datenvolumen():
    """"Unbegrenzt" ist keine Zahl, und None heisst "die Quelle nennt keine"."""
    je_name = {t.name: t for t, _ in _tarife()}
    assert je_name["O2 Mobile L"].datenvolumen_gb == 150.0
    assert je_name["O2 Mobile Unlimited M"].datenvolumen_gb is None


def test_die_geschwindigkeit_wird_nicht_fuer_volumen_gehalten():
    """"5G mit max. 300 MBit/s" steht in derselben Ueberschrift wie "15 GB+"."""
    je_name = {t.name: t for t, _ in _tarife()}
    assert je_name["O2 Mobile S"].datenvolumen_gb == 15.0


def test_anschlusspreis_null_statt_neununddreissig():
    """"0,00 € statt 39,99 €": es gilt, was heute zu zahlen ist."""
    je_name = {t.name: t for t, _ in _tarife()}
    assert je_name["O2 Mobile L"].anschlusspreis == 0.0
    assert je_name["O2 Mobile S"].anschlusspreis == 39.99


def test_der_buendel_slug_kommt_aus_dem_eigenen_link():
    """Die Bruecke zum Geraetekatalog - vom Anbieter selbst gesetzt.

    Die Kachel heisst "O2 Mobile on Demand M", der Katalog nennt seinen
    Tarif "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)". Die zwei
    Namen treffen sich nie; der Slug tut es.
    """
    je_name = {t.name: t for t, _ in _tarife()}
    assert je_name["O2 Mobile on Demand M"].buendel_slug == \
        "o2-mobile-on-demand-m-plus"
    assert je_name["O2 Mobile L"].buendel_slug == "o2-mobile-l-plus"
    assert all(t.buendel_slug for t, _ in _tarife())


def test_jede_kachel_hat_ihren_eigenen_fingerabdruck():
    """Sonst liesse eine Preisaenderung alle zwoelf als geaendert gelten."""
    hashes = [h for _, h in _tarife()]
    assert len(set(hashes)) == len(hashes) == 12


def test_die_fixture_ist_der_unveraenderte_abruf():
    eintrag = [e for e in json.loads((_FIX / "_herkunft.json").read_text(
        encoding="utf-8"))["eintraege"] if e["datei"] == _DATEI]
    assert len(eintrag) == 1
    roh = gzip.open(_FIX / _DATEI, "rb").read()
    assert hashlib.sha256(roh).hexdigest() == eintrag[0]["sha256_roh"]
    assert len(roh) == eintrag[0]["bytes_roh"] == 210306
    assert eintrag[0]["http_status"] == 200
    assert eintrag[0]["url"] == _URL


# --------------------------------------------------------------------------
# Was NICHT hereinkommt
# --------------------------------------------------------------------------

def test_ein_werbeteaser_ohne_bestellweg_ist_kein_tarif():
    """"Internet schon ab 19,99 €" traegt einen Preis und kein Produkt.

    Unterschieden wird STRUKTURELL: eine Tarifkachel traegt einen
    Bestellweg oder den Weg ins Geraetebuendel. Ein Namensfilter waere hier
    das falsche Werkzeug - er muesste raten, welche Produktnamen es gibt.
    """
    assert _tarife(_kachel(links='<a href="/internet-festnetz/">'
                                 'Verfügbarkeit prüfen</a>')) == []


def test_eine_kachel_ohne_betrag_ist_kein_tarif():
    assert _tarife(_kachel(preis="")) == []


def test_eine_kachel_ohne_namen_ist_kein_tarif():
    assert _tarife(_kachel(name="")) == []


def test_ohne_handy_hinzufuegen_bleibt_der_slug_leer():
    """Ein Bestellweg reicht fuer den Tarif - der Slug bleibt dann leer.

    Leer heisst "der Anbieter stellt diese Verbindung nicht her", nicht
    "wir haben nicht nachgesehen". Ein Buendel ohne aufloesbaren Tarif
    wird spaeter verworfen, und das ist die richtige Folge.
    """
    gefunden = _tarife(_kachel(
        links='<a href="https://www.o2online.de/e-shop/directbuy/offer;'
              'name=privatkunden-o2-mobile-s-online" title="Zum Warenkorb">'
              'Zum Warenkorb</a>'))
    assert len(gefunden) == 1
    assert gefunden[0][0].buendel_slug == ""
    gefunden[0][0].pruefe_belege()


def test_ein_fremder_tarif_parameter_woanders_zaehlt_nicht():
    """Gelesen wird nur der Link, den die Kachel selbst so beschriftet."""
    gefunden = _tarife(_kachel(
        links='<a href="https://www.o2online.de/e-shop/directbuy/offer;'
              'name=privatkunden-o2-mobile-s-online" title="Zum Warenkorb">x</a>'
              '<a href="/e-shop/?tarif=irgendwas-anderes" title="Mehr Infos">y</a>'))
    assert gefunden[0][0].buendel_slug == ""


def test_zwei_gleiche_kacheln_sind_ein_tarif():
    """o2 liefert seine Uebersicht in mehreren Reitern aus."""
    assert len(_tarife(_kachel() + _kachel())) == 1


def test_die_leere_seite_wirft_nicht():
    assert _tarife("") == []
    assert _tarife("<html><body><p>nichts</p></body></html>") == []


@pytest.mark.parametrize("titel", ["Monatlich kündbar", "", "ohne Bindung"])
def test_ein_auswahlknopf_ohne_monatszahl_setzt_keine_laufzeit(titel):
    gefunden = _tarife(_kachel(
        laufzeit='<div class="radio"><input type="radio" checked="checked"/>'
                 f'<label><span class="radio-title">{titel}</span></label>'
                 '</div>'))
    assert gefunden[0][0].laufzeit_monate is None


def test_nur_der_angekreuzte_auswahlknopf_zaehlt():
    """Die Kachel bietet zwei Laufzeiten an - nur eine gehoert zum Preis."""
    gefunden = _tarife(_kachel(
        laufzeit='<div class="radio"><input type="radio"/>'
                 '<label><span class="radio-title">36 Monate</span></label>'
                 '</div>'
                 '<div class="radio"><input type="radio" checked="checked"/>'
                 '<label><span class="radio-title">24 Monate</span></label>'
                 '</div>'))
    assert gefunden[0][0].laufzeit_monate == 24
