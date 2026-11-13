"""Gleiches Abrufdatum, gleiches Urteil - und eine frische Zeile heisst nie veraltet.

Paket P1 der Abdeckungsanalyse A-RUJNK5 vom 13.11.2026 (Abschnitt 2 (d)): 744
congstar-Buendel vom 11.11. trugen am 13.11. den Vermerk ``veraltet 16``, 306
o2-Buendel und 8 Telekom-Buendel mit DEMSELBEN ``abgerufen_am`` und derselben
(leeren) ``herleitung`` dagegen ``gueltig``. Die Seite schrieb an diese Zeilen
``Preis veraltet: Preis vom 11.11.2026.`` - die Marke „Preis vom …" wird nur an eine
FRISCHE Zeile vergeben (``report/geraete_preisstand.marke``), der Satz sagte also
frisch und veraltet in einem Atemzug.

Die Wurzel ist keine zu strenge Frischegrenze: ``ALT_AB_TAGEN`` traf alle drei
Anbieter gleich (gemessen am Bestand, 2 Tage Alter gegen Grenze 3). Zwei
verschiedene Befunde trugen dieselbe Nummer 16 - das Alter der Zeile und ein
Anschlusspreis, den eine neuere Messung desselben Tarifs widerlegt
(``analyze/geraete_anschluss``, seit 12.11.2026). Weder Seite noch Export konnten
sie auseinanderhalten und nannten beide „veraltet". Seit 13.11.2026 ist die
Widerlegung Regel 18 und traegt ihren eigenen Satz.

Die Tests hier halten beides fest: gleiche Eingaben ergeben gleiche Urteile (ueber
Anbieter hinweg), eine frische Zeile bekommt nie den Satz „Preis veraltet", und ein
wirklich alter Preis rutscht nicht durch die Frischegrenze.
"""

from __future__ import annotations

from dataclasses import replace

from telco_radar.analyze.geraete_pruefstatus import (
    GUELTIG,
    VERALTET,
    VERLETZT,
    Kontext,
    buendel_aus_satz,
    lies_vermerk,
    vermerk,
)
from telco_radar.analyze.geraete_regeln import pruefe_bestand
from telco_radar.report import geraete_notbremse, geraete_preisstand
from telco_radar.report.geraete_tco_karten import ist_frisch

HEUTE = "2026-11-13"
VORGESTERN = "2026-11-11"
LANGE_HER = "2026-10-20"

IPHONE = "apple-iphone-16-128gb-weiss"
IPHONE_256 = "apple-iphone-16-256gb-weiss"
IPHONE_512 = "apple-iphone-16-512gb-weiss"


def _satz(
    bid: str,
    *,
    tag: str,
    anbieter: str = "congstar",
    tarif_id: str = "congstar:allnet-flat-l",
    anschluss: float = 15.0,
    sku: str = IPHONE,
    herleitung: str = "",
) -> dict:
    """Ein Buendelsatz wie im Store - die Felder der 744 congstar-Zeilen."""
    return {
        "id": bid,
        "sku_id": sku,
        "anbieter": anbieter,
        "tarif_name": "Allnet Flat L",
        "tarif_id": tarif_id,
        "tarif_id_guete": "hoch",
        "tarif_monatlich": 30.0,
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 27.0,
        "laufzeit_monate": 24,
        "anschlusspreis": anschluss,
        "zustand": "neu",
        "abgerufen_am": tag,
        "herleitung": herleitung,
        "quelle_url": "https://www.congstar.de/geraete/apple/apple-iphone-16/",
    }


def _kontext() -> Kontext:
    """Der Kontext der Pruefstelle mit der Frische-Definition der Seite."""
    return Kontext(heute=HEUTE, frisch=ist_frisch)


def _vermerk(ergebnisse, bid: str) -> str:
    return vermerk(ergebnisse[bid].als_feld()).als_text()


def _mit_vermerk(satz: dict, ergebnisse):
    """Das Buendel, wie es nach dem Lauf im Store steht: mit seinem Vermerk."""
    return replace(buendel_aus_satz(satz), pruefung=_vermerk(ergebnisse, satz["id"]))


def _luecke(satz: dict, ergebnisse) -> str:
    """Der Satz, den Seite und Export an dieser Zeile schreiben."""
    return geraete_preisstand.buendel_luecke(_mit_vermerk(satz, ergebnisse), HEUTE)


def _status_spalte(satz: dict, ergebnisse) -> str:
    """Die Spalte „Status" der Export-Zeile (``report/geraete_export.tco_csv``)."""
    return geraete_notbremse.kurz(_mit_vermerk(satz, ergebnisse), HEUTE)


def test_gleiches_abrufdatum_und_gleiche_herleitung_ergeben_denselben_status():
    """Die Abnahme aus P1: zwei Buendel, identisch in ``abgerufen_am`` und
    ``herleitung``, nur bei verschiedenen Anbietern - derselbe Status."""
    congstar = _satz("congstar", tag=VORGESTERN, anbieter="congstar")
    o2 = _satz("o2", tag=VORGESTERN, anbieter="o2", tarif_id="o2:o2-mobile-l")
    telekom = _satz(
        "telekom", tag=VORGESTERN, anbieter="Telekom", tarif_id="telekom:magenta-m"
    )

    ergebnisse = pruefe_bestand([congstar, o2, telekom], _kontext())

    urteile = {bid: ergebnisse[bid].status for bid in ("congstar", "o2", "telekom")}
    assert len(set(urteile.values())) == 1, urteile
    assert urteile["congstar"] == GUELTIG


def test_eine_frische_zeile_heisst_nie_veraltet():
    """Der Fall der 744: der Anschlusspreis ist widerlegt, die Zeile ist frisch.

    Vorher trug sie ``veraltet 16`` und den Satz „Preis veraltet: Preis vom
    11.11.2026." - frisch und veraltet zugleich.
    """
    alt = _satz("alt", tag=VORGESTERN, anschluss=15.0)
    neu_a = _satz("neu_a", tag=HEUTE, anschluss=0.0, sku=IPHONE_256)
    neu_b = _satz("neu_b", tag=HEUTE, anschluss=0.0, sku=IPHONE_512)

    ergebnisse = pruefe_bestand([alt, neu_a, neu_b], _kontext())

    assert ist_frisch(alt["abgerufen_am"], HEUTE, ""), (
        "Vorbedingung: die Zeile ist frisch"
    )
    regeln = [b.regel for b in ergebnisse["alt"].je(VERLETZT)]
    assert 18 in regeln, "der widerlegte Anschlusspreis ist Regel 18"
    assert 16 not in regeln, "eine frische Zeile traegt nie die Nummer der Frische"
    satz = _luecke(alt, ergebnisse)
    assert geraete_preisstand.KURZ_VERALTET not in satz, satz
    assert "Preis vom " not in satz, satz
    assert "Anschlusspreis" in satz and "11.11.2026" in satz, satz
    assert _status_spalte(alt, ergebnisse) == geraete_notbremse.DELTA_ANSCHLUSS


def test_kein_wirklich_veralteter_preis_rutscht_durch():
    """Gegenprobe zur Frischegrenze: 24 Tage alt bleibt veraltet, mit Regel 16."""
    alt = _satz("alt", tag=LANGE_HER)

    ergebnisse = pruefe_bestand([alt], _kontext())

    assert ergebnisse["alt"].status == VERALTET
    assert 16 in [b.regel for b in ergebnisse["alt"].je(VERLETZT)]
    assert geraete_preisstand.KURZ_VERALTET in _luecke(alt, ergebnisse)


def test_die_statusspalte_trennt_die_beiden_gruende():
    """Export und Seite lesen zwei verschiedene Woerter - sonst war der Befund
    nicht lesbar (Analyse A-RUJNK5: 372 Zeilen „veraltet" + „Preis vom …")."""
    widerlegt = _satz("widerlegt", tag=VORGESTERN, anschluss=15.0)
    gealtert = _satz("gealtert", tag=LANGE_HER, tarif_id="congstar:allnet-flat-xs")
    neu_a = _satz("neu_a", tag=HEUTE, anschluss=0.0, sku=IPHONE_256)
    neu_b = _satz("neu_b", tag=HEUTE, anschluss=0.0, sku=IPHONE_512)

    ergebnisse = pruefe_bestand([widerlegt, gealtert, neu_a, neu_b], _kontext())

    assert _status_spalte(widerlegt, ergebnisse) != _status_spalte(gealtert, ergebnisse)
    assert lies_vermerk(_vermerk(ergebnisse, "widerlegt")).status == VERALTET
