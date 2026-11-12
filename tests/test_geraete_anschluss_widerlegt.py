"""Regel 16: Ein Anschlusspreis, den eine neuere Messung desselben Tarifs widerlegt.

Fall aus der Ist-Aufnahme vom 12.11.2026 (Befund D1): congstar misst am 11.11. den
Bereitstellungspreis 15,00 € (24 Monate) bzw. 35,00 € (Flex) und am 12.11. am selben
Tarif 0,00 €. Die Zeilen vom 11.11. blieben gueltig und trugen den alten Betrag weiter.
Ein Preis, den die juengste Messung desselben Tarifs widerlegt, ist nicht mehr belegt
und zaehlt nicht (CLAUDE.md, Harte Regel 11 und Clean Code 6).

Nachbesserung nach Pruefung A-DBURQP (Auflagen 1 und 2): Die Gruppe ist die
Vertragsform (Anbieter, Tarif, Zustand, Ratenlaufzeit), der juengste Messtag braucht
eine Mindeststuetze, und eine Zeile, deren eigener Messtag schon uneins war, wird nicht
widerlegt.
"""

from __future__ import annotations

import pytest

from telco_radar.analyze.geraete_pruefstatus import (
    GUELTIG,
    VERALTET,
    VERLETZT,
    Kontext,
)
from telco_radar.analyze.geraete_regeln import pruefe_bestand

HEUTE = "2026-11-12"
GESTERN = "2026-11-11"

IPHONE_16 = "apple-iphone-16-128gb-weiss"
IPHONE_16_256 = "apple-iphone-16-256gb-weiss"
IPHONE_16_512 = "apple-iphone-16-512gb-weiss"


def _satz(
    bid: str,
    *,
    anschluss: float,
    tag: str,
    tarif_id: str = "congstar:allnet-flat-xs-mit-gb",
    anbieter: str = "congstar",
    sku: str = IPHONE_16,
    zustand: str = "neu",
    laufzeit: int = 24,
) -> dict:
    return {
        "id": bid,
        "sku_id": sku,
        "anbieter": anbieter,
        "tarif_name": "Allnet Flat XS",
        "tarif_id": tarif_id,
        "tarif_id_guete": "hoch",
        "tarif_monatlich": 15.0,
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 27.0,
        "laufzeit_monate": laufzeit,
        "anschlusspreis": anschluss,
        "zustand": zustand,
        "abgerufen_am": tag,
        "quelle_url": "https://www.congstar.de/geraete/apple/apple-iphone-16/",
    }


def _juengste(anschluss: float, **felder) -> list[dict]:
    """Ein juengster Messtag mit Mindeststuetze: derselbe Betrag an zwei Geraeten."""
    return [
        _satz("neu_a", anschluss=anschluss, tag=HEUTE, sku=IPHONE_16_256, **felder),
        _satz("neu_b", anschluss=anschluss, tag=HEUTE, sku=IPHONE_16_512, **felder),
    ]


def _kontext(**felder) -> Kontext:
    """Kontext, in dem jede Messung der letzten Tage frisch ist (Regel 16, Frische)."""
    return Kontext(heute=HEUTE, frisch=lambda tag, heute, herleitung: True, **felder)


def _status(ergebnisse, bid):
    return ergebnisse[bid].status


def _regeln(ergebnisse, bid):
    return [b.regel for b in ergebnisse[bid].je(VERLETZT)]


def test_aelterer_anschluss_wird_von_der_juengsten_messung_widerlegt():
    """Die Zeile vom 11.11. mit 15,00 € zaehlt nicht mehr, die vom 12.11. schon."""
    alt = _satz("alt", anschluss=15.0, tag=GESTERN)

    ergebnisse = pruefe_bestand([alt, *_juengste(0.0)], _kontext())

    assert _status(ergebnisse, "alt") == VERALTET
    assert 16 in _regeln(ergebnisse, "alt")
    assert _status(ergebnisse, "neu_a") == GUELTIG


def test_der_befund_nennt_beide_betraege_und_beide_tage():
    alt = _satz("alt", anschluss=35.0, tag=GESTERN)

    ergebnisse = pruefe_bestand([alt, *_juengste(0.0)], _kontext())
    saetze = [b.satz for b in ergebnisse["alt"].je(VERLETZT) if b.regel == 16]

    assert saetze, "die Zeile hat keinen Befund 16"
    assert "35,00 €" in saetze[0]
    assert "0,00 €" in saetze[0]
    assert "11.11.2026" in saetze[0]
    assert "12.11.2026" in saetze[0]


def test_gegenprobe_gleicher_betrag_bleibt_gueltig():
    """Gegenprobe: Misst der juengere Tag denselben Betrag, aendert sich nichts."""
    alt = _satz("alt", anschluss=15.0, tag=GESTERN)

    ergebnisse = pruefe_bestand([alt, *_juengste(15.0)], _kontext())

    assert _status(ergebnisse, "alt") == GUELTIG
    assert _status(ergebnisse, "neu_a") == GUELTIG


def test_gegenprobe_anderer_tarif_widerlegt_nichts():
    """Gegenprobe: Der Bereitstellungspreis gilt je Tarif, nicht je Anbieter."""
    alt = _satz("alt", anschluss=15.0, tag=GESTERN)
    neu = _juengste(0.0, tarif_id="congstar:allnet-flat-l")

    ergebnisse = pruefe_bestand([alt, *neu], _kontext())

    assert _status(ergebnisse, "alt") == GUELTIG


def test_gegenprobe_ohne_juengere_messung_bleibt_alles_gueltig():
    """Gegenprobe: Ohne neuere Messung ist der alte Betrag der einzige Beleg."""
    a = _satz("a", anschluss=15.0, tag=GESTERN)
    b = _satz("b", anschluss=15.0, tag=GESTERN, sku=IPHONE_16_256)

    ergebnisse = pruefe_bestand([a, b], _kontext())

    assert _status(ergebnisse, "a") == GUELTIG
    assert _status(ergebnisse, "b") == GUELTIG


def test_gegenprobe_uneindeutiger_juengster_tag_widerlegt_nichts():
    """Zwei Betraege am selben juengsten Tag belegen keinen: niemand wird widerlegt."""
    alt = _satz("alt", anschluss=15.0, tag=GESTERN)
    neu_a = _satz("na", anschluss=0.0, tag=HEUTE, sku=IPHONE_16_256)
    neu_b = _satz("nb", anschluss=5.0, tag=HEUTE, sku=IPHONE_16_512)

    ergebnisse = pruefe_bestand([alt, neu_a, neu_b], _kontext())

    assert _status(ergebnisse, "alt") == GUELTIG


def test_gegenprobe_zeile_ohne_anschluss_bleibt_unberuehrt():
    """Ein fehlender Anschluss ist eine Luecke (Regel 14), kein Widerspruch."""
    alt = _satz("alt", anschluss=15.0, tag=GESTERN)
    alt["anschlusspreis"] = None

    ergebnisse = pruefe_bestand([alt, *_juengste(0.0)], _kontext())

    assert 16 not in _regeln(ergebnisse, "alt")


@pytest.mark.parametrize("anbieter", ["congstar", "o2", "Telekom"])
def test_die_regel_kennt_keinen_anbieter(anbieter):
    """Keine Anbietersonderlogik: dieselbe Regel trifft jeden Anbieter."""
    alt = _satz("alt", anschluss=39.99, tag="2026-11-10", anbieter=anbieter)

    ergebnisse = pruefe_bestand([alt, *_juengste(0.0, anbieter=anbieter)], _kontext())

    assert _status(ergebnisse, "alt") == VERALTET


def test_einzelne_unbelegte_neue_zeile_loescht_keinen_tarif():
    """Gegentest zur Auflage 2: EIN Lesefehler am juengsten Tag darf die 100 Zeilen
    des Vortags nicht streichen. Eine einzige Zeile ohne Klick-Beleg traegt nichts."""
    alte = [
        _satz(f"alt{i}", anschluss=15.0, tag=GESTERN, sku=f"geraet-{i}")
        for i in range(100)
    ]
    lesefehler = _satz("fehler", anschluss=0.0, tag=HEUTE, sku=IPHONE_16_256)

    ergebnisse = pruefe_bestand([*alte, lesefehler], _kontext())

    assert all(_status(ergebnisse, f"alt{i}") == GUELTIG for i in range(100))


def test_zwei_geraete_am_juengsten_tag_stuetzen_die_messung():
    """Dieselbe Lage mit zwei Geraeten statt einem: die Messung traegt."""
    alte = [
        _satz(f"alt{i}", anschluss=15.0, tag=GESTERN, sku=f"geraet-{i}")
        for i in range(100)
    ]

    ergebnisse = pruefe_bestand([*alte, *_juengste(0.0)], _kontext())

    assert all(_status(ergebnisse, f"alt{i}") == VERALTET for i in range(100))


def test_eine_zeile_mit_klick_beleg_stuetzt_allein():
    """Ein Klick-Beleg ist ein Bildbeleg der Seite: eine Zeile genuegt."""
    alt = _satz("alt", anschluss=15.0, tag=GESTERN)
    neu = _satz("neu", anschluss=0.0, tag=HEUTE, sku=IPHONE_16_256)
    neu["quelle_art"] = "klick"
    neu["beleg_id"] = "congstar-2026-11-12-0001"
    neu["beleg_status"] = "belegt"

    ergebnisse = pruefe_bestand([alt, neu], _kontext())

    assert _status(ergebnisse, "alt") == VERALTET


def test_uneindeutiger_eigener_messtag_wird_nicht_widerlegt():
    """Der o2-Befund der Pruefung: „Unlimited S Special Plus“ fuehrte am 11.11.
    nebeneinander 0,00 € und 39,99 €. Welchen Betrag die Messung vom 12.11. ersetzt,
    ist nicht entscheidbar - also wird keiner widerlegt."""
    teuer = _satz("teuer", anschluss=39.99, tag=GESTERN, anbieter="o2")
    billig = _satz(
        "billig", anschluss=0.0, tag=GESTERN, anbieter="o2", sku=IPHONE_16_256
    )

    ergebnisse = pruefe_bestand(
        [teuer, billig, *_juengste(0.0, anbieter="o2")], _kontext()
    )

    assert _status(ergebnisse, "teuer") == GUELTIG
    assert 16 not in _regeln(ergebnisse, "teuer")


def test_refurbished_widerlegt_keine_neuware():
    """Refurbished-Ware ist eine eigene Vertragsform mit eigenem Bestand."""
    alt = _satz("alt", anschluss=15.0, tag=GESTERN, zustand="neu")

    ergebnisse = pruefe_bestand(
        [alt, *_juengste(0.0, zustand="refurbished")], _kontext()
    )

    assert _status(ergebnisse, "alt") == GUELTIG


def test_andere_ratenlaufzeit_widerlegt_nicht():
    """congstar nimmt 15,00 € auf 24 Monate und 35,00 € flex: die Ratenlaufzeit
    gehoert zum Anschlusspreis."""
    alt = _satz("alt", anschluss=15.0, tag=GESTERN, laufzeit=24)

    ergebnisse = pruefe_bestand([alt, *_juengste(0.0, laufzeit=36)], _kontext())

    assert _status(ergebnisse, "alt") == GUELTIG
