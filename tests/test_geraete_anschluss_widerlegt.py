"""Regel 16: Ein Anschlusspreis, den eine neuere Messung desselben Tarifs widerlegt.

Fall aus der Ist-Aufnahme vom 12.11.2026 (Befund D1): congstar misst am 11.11. den
Bereitstellungspreis 15,00 € (24 Monate) bzw. 35,00 € (Flex) und am 12.11. am selben
Tarif 0,00 €. Die Zeilen vom 11.11. blieben gueltig und trugen den alten Betrag weiter.
Ein Preis, den die juengste Messung desselben Tarifs widerlegt, ist nicht mehr belegt
und zaehlt nicht (CLAUDE.md, Harte Regel 11 und Clean Code 6).
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


def _satz(
    bid: str,
    *,
    anschluss: float,
    tag: str,
    tarif_id: str = "congstar:allnet-flat-xs-mit-gb",
    anbieter: str = "congstar",
    sku: str = "apple-iphone-16-128gb-weiss",
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
        "laufzeit_monate": 24,
        "anschlusspreis": anschluss,
        "zustand": "neu",
        "abgerufen_am": tag,
        "quelle_url": "https://www.congstar.de/geraete/apple/apple-iphone-16/",
    }


def _kontext(**felder) -> Kontext:
    """Kontext, in dem jede Messung der letzten Tage frisch ist (Regel 16, Frische)."""
    return Kontext(heute=HEUTE, frisch=lambda tag, heute, herleitung: True, **felder)


def _status(ergebnisse, bid):
    return ergebnisse[bid].status


def _regeln(ergebnisse, bid):
    return [b.regel for b in ergebnisse[bid].je(VERLETZT)]


def test_aelterer_anschluss_wird_von_der_juengsten_messung_widerlegt():
    """Die Zeile vom 11.11. mit 15,00 € zaehlt nicht mehr, die vom 12.11. schon."""
    alt = _satz("alt", anschluss=15.0, tag="2026-11-11")
    neu = _satz("neu", anschluss=0.0, tag=HEUTE, sku="apple-iphone-16-256gb-weiss")

    ergebnisse = pruefe_bestand([alt, neu], _kontext())

    assert _status(ergebnisse, "alt") == VERALTET
    assert 16 in _regeln(ergebnisse, "alt")
    assert _status(ergebnisse, "neu") == GUELTIG


def test_der_befund_nennt_beide_betraege_und_beide_tage():
    alt = _satz("alt", anschluss=35.0, tag="2026-11-11")
    neu = _satz("neu", anschluss=0.0, tag=HEUTE, sku="apple-iphone-16-256gb-weiss")

    ergebnisse = pruefe_bestand([alt, neu], _kontext())
    saetze = [b.satz for b in ergebnisse["alt"].je(VERLETZT) if b.regel == 16]

    assert saetze, "die Zeile hat keinen Befund 16"
    assert "35,00 €" in saetze[0]
    assert "0,00 €" in saetze[0]
    assert "11.11.2026" in saetze[0]
    assert "12.11.2026" in saetze[0]


def test_gegenprobe_gleicher_betrag_bleibt_gueltig():
    """Gegenprobe: Misst der juengere Tag denselben Betrag, aendert sich nichts."""
    alt = _satz("alt", anschluss=15.0, tag="2026-11-11")
    neu = _satz("neu", anschluss=15.0, tag=HEUTE, sku="apple-iphone-16-256gb-weiss")

    ergebnisse = pruefe_bestand([alt, neu], _kontext())

    assert _status(ergebnisse, "alt") == GUELTIG
    assert _status(ergebnisse, "neu") == GUELTIG


def test_gegenprobe_anderer_tarif_widerlegt_nichts():
    """Gegenprobe: Der Bereitstellungspreis gilt je Tarif, nicht je Anbieter."""
    alt = _satz("alt", anschluss=15.0, tag="2026-11-11")
    neu = _satz(
        "neu",
        anschluss=0.0,
        tag=HEUTE,
        tarif_id="congstar:allnet-flat-l",
        sku="apple-iphone-16-256gb-weiss",
    )

    ergebnisse = pruefe_bestand([alt, neu], _kontext())

    assert _status(ergebnisse, "alt") == GUELTIG


def test_gegenprobe_ohne_juengere_messung_bleibt_alles_gueltig():
    """Gegenprobe: Ohne neuere Messung ist der alte Betrag der einzige Beleg."""
    a = _satz("a", anschluss=15.0, tag="2026-11-11")
    b = _satz("b", anschluss=15.0, tag="2026-11-11", sku="apple-iphone-16-256gb-weiss")

    ergebnisse = pruefe_bestand([a, b], _kontext())

    assert _status(ergebnisse, "a") == GUELTIG
    assert _status(ergebnisse, "b") == GUELTIG


def test_gegenprobe_uneindeutiger_juengster_tag_widerlegt_nichts():
    """Zwei Betraege am selben juengsten Tag belegen keinen: niemand wird widerlegt."""
    alt = _satz("alt", anschluss=15.0, tag="2026-11-11")
    neu_a = _satz("na", anschluss=0.0, tag=HEUTE, sku="apple-iphone-16-256gb-weiss")
    neu_b = _satz("nb", anschluss=5.0, tag=HEUTE, sku="apple-iphone-16-512gb-weiss")

    ergebnisse = pruefe_bestand([alt, neu_a, neu_b], _kontext())

    assert _status(ergebnisse, "alt") == GUELTIG


def test_gegenprobe_zeile_ohne_anschluss_bleibt_unberuehrt():
    """Ein fehlender Anschluss ist eine Luecke (Regel 14), kein Widerspruch."""
    alt = _satz("alt", anschluss=15.0, tag="2026-11-11")
    alt["anschlusspreis"] = None
    neu = _satz("neu", anschluss=0.0, tag=HEUTE, sku="apple-iphone-16-256gb-weiss")

    ergebnisse = pruefe_bestand([alt, neu], _kontext())

    assert 16 not in _regeln(ergebnisse, "alt")


@pytest.mark.parametrize("anbieter", ["congstar", "o2", "Telekom"])
def test_die_regel_kennt_keinen_anbieter(anbieter):
    """Keine Anbietersonderlogik: dieselbe Regel trifft jeden Anbieter."""
    alt = _satz("alt", anschluss=39.99, tag="2026-11-10", anbieter=anbieter)
    neu = _satz(
        "neu",
        anschluss=0.0,
        tag=HEUTE,
        anbieter=anbieter,
        sku="apple-iphone-16-256gb-weiss",
    )

    ergebnisse = pruefe_bestand([alt, neu], _kontext())

    assert _status(ergebnisse, "alt") == VERALTET
