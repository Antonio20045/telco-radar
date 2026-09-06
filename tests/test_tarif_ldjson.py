"""Die zweite Lesart einer Tarifquelle: die Shop-Seite statt des Blattes.

WARUM DIESE STUFE UEBERHAUPT EXISTIERT
--------------------------------------
Das Produktinformationsblatt nach § 1 TK-TransparenzV ist die belastbarste
Quelle dieses Marktes und die traegste. Es traegt den Vermarktungsstand,
die Shop-Seite den Preis von heute. Beide sind richtig, und sie duerfen
auseinanderlaufen - die Abweichung IST die Auskunft. Deshalb traegt jeder
Satz seit dem 04.09.2026, woher seine Zahl kommt (`Tarif.preistyp`), und
kein Sammler rechnet die Differenz weg.

DIE FIXTURE IST EIN GESPEICHERTER ECHTER ABRUF
----------------------------------------------
`tests/fixtures/tarife/1und1_handytarife.html.gz` ist die rohe, ungekuerzte
Antwort von https://www.1und1.de/handytarife vom 04.09.2026 (HTTP 200,
452 KB, Absender `TelcoRadar/1.0`). Herkunft und sha256 des entpackten
Inhalts stehen in `tests/fixtures/tarife/_herkunft.json`.

Die kleinen HTML-Schnipsel weiter unten stellen Ausfaelle nach, die sich
nicht ehrlich herbeimessen lassen (fremde Marke, fremde Waehrung, kaputter
Block) - sie geben sich nicht als Messung aus.
"""
import gzip
import json
from pathlib import Path

from telco_radar.collect import tarif_ldjson
from telco_radar.tarif_model import PREISTYP_LIVE_SHOP

_FIX = Path(__file__).parent / "fixtures" / "tarife"
_URL = "https://www.1und1.de/handytarife"


def _seite() -> str:
    with gzip.open(_FIX / "1und1_handytarife.html.gz", "rt", encoding="utf-8") as fh:
        return fh.read()


def _tarife(html=None):
    return tarif_ldjson.tarife_aus_html(html if html is not None else _seite(),
                                        anbieter="1&1", seiten_url=_URL,
                                        abgerufen_am="2026-09-04")


def _knoten(name="1&1 All-Net-Flat S", marke="1&1", preis="14.99",
            waehrung="EUR", beschreibung="1&1 All-Net-Flat S 10 GB") -> str:
    knoten = {"@context": "https://schema.org", "@type": "Product",
              "name": name, "description": beschreibung,
              "brand": {"@type": "Brand", "name": marke},
              "offers": {"@type": "Offer", "priceCurrency": waehrung,
                         "price": preis}}
    return ('<script type="application/ld+json">'
            + json.dumps(knoten, ensure_ascii=False) + "</script>")


# --------------------------------------------------------------------------
# Die gemessene Seite
# --------------------------------------------------------------------------

def test_die_sieben_tarife_der_seite():
    gefunden = _tarife()
    assert [(t.name, t.grundgebuehr) for t, _ in gefunden] == [
        ("1&1 All-Net-Flat S", 14.99),
        ("1&1 All-Net-Flat M", 14.99),
        ("1&1 All-Net-Flat L", 19.99),
        ("1&1 Unlimited on demand S", 19.99),
        ("1&1 Unlimited on demand M", 19.99),
        ("1&1 Unlimited on demand L", 24.99),
        ("1&1 Unlimited XL", 39.99),
    ]


def test_zwei_tarife_mit_demselben_betrag_werden_nicht_geglaettet():
    """S und M tragen am 04.09.2026 beide 14,99 EUR. Das steht so in der
    Quelle. Eine Stufe daraus zu machen waere eine Korrektur an einer
    Messung."""
    nach_name = {t.name: t.grundgebuehr for t, _ in _tarife()}
    assert nach_name["1&1 All-Net-Flat S"] == nach_name["1&1 All-Net-Flat M"]


def test_das_datenvolumen_kommt_aus_der_beschreibung():
    nach_name = {t.name: t.datenvolumen_gb for t, _ in _tarife()}
    assert nach_name["1&1 All-Net-Flat S"] == 10.0
    assert nach_name["1&1 All-Net-Flat L"] == 150.0
    # "1&1 Unlimited XL" nennt in seiner description keine GB-Zahl. Dann
    # steht dort nichts - nicht "unbegrenzt", nicht 0.
    assert nach_name["1&1 Unlimited XL"] is None


def test_keine_laufzeit_wird_abgeleitet():
    """Die Knoten nennen keine Mindestlaufzeit. 24 Monate als Marktueblich
    zu setzen waere geraten - und `laufzeit_monate` ist ein Pflichtfeld,
    also faellt die Luecke auf, statt sich zu verstecken."""
    assert all(t.laufzeit_monate is None for t, _ in _tarife())


def test_keine_preisphase_wird_erfunden():
    """"ab dem 7. Monat" kommt im gemessenen HTML kein einziges Mal vor.
    Ob 14,99 EUR Aktions- oder Dauerpreis ist, sagt die Quelle nicht - und
    dieses Modul sagt es deshalb auch nicht."""
    assert all(not t.preisphasen for t, _ in _tarife())


def test_jeder_satz_traegt_seinen_preistyp():
    assert all(t.preistyp == PREISTYP_LIVE_SHOP for t, _ in _tarife())


def test_die_fundstelle_steht_woertlich_im_rohtext():
    """`pruefe_belege()` ist die Zusage, dass jede Zahl nachschlagbar ist.
    Sie gilt fuer die Shop-Seite genauso wie fuer das PDF."""
    for tarif, _ in _tarife():
        tarif.pruefe_belege()
        assert '"price"' in tarif.fundstellen["grundgebuehr"]


def test_die_quelle_ist_die_seite_und_nicht_der_bestellweg():
    """`offers.url` waere verlockend - 1&1 setzt dort aber fuer alle sieben
    Tarife dieselbe Adresse. Die Fundstelle ist die Seite, auf der die Zahl
    stand."""
    assert all(t.dokument_url == _URL for t, _ in _tarife())


def test_der_fingerabdruck_haengt_am_knoten_und_nicht_an_der_seite():
    """Sieben Tarife auf einer Seite haetten sonst denselben Hash: eine
    Aenderung an einem einzigen liesse alle sieben als geaendert gelten."""
    hashes = [h for _, h in _tarife()]
    assert len(set(hashes)) == len(hashes) == 7


def test_kein_tarif_geraet_in_quarantaene():
    assert all(not t.ist_quarantaene for t, _ in _tarife())


# --------------------------------------------------------------------------
# Abgrenzung und Ausfaelle
# --------------------------------------------------------------------------

def test_ein_geraet_ist_kein_tarif():
    """mobile.1und1.de/iphone-17-pro traegt AUCH einen Product-Knoten mit
    `offers.price` - dort 44,99 EUR als Monatspreis des BUENDELS. Getrennt
    werden die zwei an der Marke: der Anbieter verkauft seinen eigenen
    Tarif und Apples Telefon."""
    assert _tarife(_knoten(name="iPhone 17 Pro", marke="Apple",
                           preis="44.99")) == []


def test_die_marke_wird_verglichen_und_nicht_buchstabiert():
    """Im Graph steht `1&1`, im HTML-Text `1&amp;1`, in der Konfiguration
    `1&1`. Nach der Vereinfachung ist alles davon `11`."""
    assert len(_tarife(_knoten(marke="1 & 1"))) == 1


def test_fremde_waehrung_ist_kein_vergleichswert():
    assert _tarife(_knoten(waehrung="CHF")) == []


def test_knoten_ohne_betrag_wird_uebergangen():
    assert _tarife(_knoten(preis=None)) == []


def test_knoten_ohne_namen_wird_uebergangen():
    assert _tarife(_knoten(name="")) == []


def test_ein_kaputter_block_kippt_die_seite_nicht():
    """Bei 1&1 stehen FAQPage, WebSite und Organization neben dem
    Tarifgraphen. Ein unlesbarer Block darf die heilen nicht mitnehmen."""
    html = ('<script type="application/ld+json">{kaputt</script>'
            + _knoten())
    assert len(_tarife(html)) == 1


def test_der_graph_wird_genauso_gelesen_wie_das_einzelobjekt():
    """schema.org kennt drei Verpackungen; 1&1 benutzt `@graph`. Wer nur
    eine liest, findet bei der naechsten Umstellung nichts mehr - ohne dass
    etwas wirft."""
    einzeln = {"@type": "Product", "name": "1&1 All-Net-Flat S",
               "brand": {"name": "1&1"},
               "offers": {"priceCurrency": "EUR", "price": "14.99"}}
    for verpackung in ({"@graph": [einzeln]}, [einzeln], einzeln):
        html = ('<script type="application/ld+json">'
                + json.dumps(verpackung) + "</script>")
        assert [t.name for t, _ in _tarife(html)] == ["1&1 All-Net-Flat S"]


def test_derselbe_knoten_zweimal_ist_eine_dublette_und_kein_zweiter_tarif():
    assert len(_tarife(_knoten() + _knoten())) == 1


def test_seite_ohne_strukturierte_daten_liefert_nichts():
    assert _tarife("") == []
    assert _tarife("<html><body>Unsere Tarife ab 9,99 &euro;</body></html>") == []
