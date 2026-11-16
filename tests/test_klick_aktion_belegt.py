"""Eine belegte eingerechnete Aktion hält den Klick-Satz nicht mehr zurück.

BEFUND 15./16.11.2026: Die Klick-Bilanz nannte für congstar 760 Sätze
„unvollständig (aktionen 760)“ - gemessene Preise der Anbieterseite, die wegen eines
einzigen Feldes nicht in den Bestand kamen. Das Feld ist der erlassene
Bereitstellungspreis: congstar hängt ihn als Aktion ``anschluss_erlassen`` an JEDEN
Bündelsatz, mit Fußnote, Betrag 15,00 € und ``eingerechnet: true`` - und schreibt im
selben Satz ``anschlusspreis: 0.0``. Der Klick-Crawler misst auf derselben Seite
dieselbe Null, kennt aber kein Aktionsfeld; damit galt er als unvollständig.

Der Adaptersatz dieses Tests ist ECHT: er kommt aus
``tests/fixtures/geraete/congstar_produkt_galaxy_s26_20261116.html.gz``, der am
16.11.2026 mit dem ehrlichen Absender ``TelcoRadar/1.0`` abgerufenen Produktseite
(HTTP 200, Eintrag in ``_herkunft.json``), gelesen vom echten Adapter
(``collect.geraete.congstar.lies_buendel``). Die Werte des Klick-Satzes sind die der
echten Lesung derselben Seite vom 13.11.2026
(``data/state/klick/congstar.json``, Galaxy S26 256 GB, Allnet Flat XS, 36 Raten:
Zuzahlung 1,00 €, Rate 25,50 €, Anschluss 0,00 €).

Gegenprobe: dieselbe Aktion mit abgelaufener Frist (die refurbished-Bündel mit der am
29.09.2026 abgelaufenen Aktion), ohne Fußnote, ohne Betrag oder neben einem
abweichenden Anschlusspreis hält den Klick-Satz weiter zurück - lieber ein Preis
weniger als ein falscher (CLAUDE.md Regel 10, Clean Code 5).
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from telco_radar.analyze.klick_vollstaendig import begleitend, fehlend
from telco_radar.collect.geraete.congstar import lies_buendel

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_SEITE = "congstar_produkt_galaxy_s26_20261116.html.gz"
_URL = "https://www.congstar.de/geraete/samsung/samsung-galaxy-s26/"
MESSTAG = "2026-11-16"
ABGELAUFEN = "2026-09-29"


@pytest.fixture(scope="module")
def adaptersatz() -> dict:
    """Ein echter congstar-Bündelsatz MIT der eingerechneten Aktion."""
    with gzip.open(_FIX / _SEITE, "rb") as fh:
        text = fh.read().decode("utf-8", "replace")
    saetze = [
        s
        for s in lies_buendel(text, _URL)
        if any(a["art"] == "anschluss_erlassen" for a in s.get("aktionen") or [])
    ]
    assert saetze, "Fixtur ohne eingerechnete Aktion - Befund nicht mehr abgebildet"
    return saetze[0]


@pytest.fixture(scope="module")
def aktion(adaptersatz: dict) -> dict:
    (treffer,) = [
        a for a in adaptersatz["aktionen"] if a["art"] == "anschluss_erlassen"
    ]
    return treffer


def _klicksatz(adaptersatz: dict, **felder) -> dict:
    """Die Werte der echten Klick-Lesung: dieselben Zahlen, kein Aktionsfeld."""
    return {
        "quelle_art": "klick",
        "abgerufen_am": MESSTAG,
        "geraet_zuzahlung": adaptersatz["geraet_zuzahlung"],
        "geraet_monatsrate": adaptersatz["geraet_monatsrate"],
        "tarif_monatlich": adaptersatz["tarif_monatlich"],
        "anschlusspreis": adaptersatz["anschlusspreis"],
        **felder,
    }


def test_die_aktion_ist_so_belegt_wie_der_befund_sie_beschreibt(adaptersatz, aktion):
    """Vorbedingung des Tests, an der echten Seite: Fußnote, Betrag, Frist - und
    ein Anschlusspreis von 0,00 € im selben Satz."""
    assert aktion["eingerechnet"] is True
    assert aktion["bedingung"].startswith("Bei Abschluss bis zum")
    assert aktion["betrag"] > 0
    assert aktion["gueltig_bis"] > MESSTAG
    assert adaptersatz["anschlusspreis"] == 0.0


def test_belegte_aktion_haelt_den_klicksatz_nicht_mehr_zurueck(adaptersatz):
    """Vorher rot: ``aktionen`` stand in der Liste der fehlenden Felder, und der
    gemessene Satz fiel unter „unvollständig“."""
    klick = _klicksatz(adaptersatz)

    assert fehlend(klick, adaptersatz, MESSTAG) == []


def test_die_belegte_aktion_reist_mit(adaptersatz, aktion):
    """Der ersetzende Klick-Satz trägt sie weiter - die Seite nennt sie weiter."""
    klick = _klicksatz(adaptersatz)

    mit = begleitend(klick, adaptersatz, MESSTAG)["aktionen"]

    assert mit == adaptersatz["aktionen"]
    assert aktion in mit


def test_abgelaufene_aktion_haelt_den_klicksatz_zurueck(adaptersatz, aktion):
    """Die refurbished-Bündel mit der am 29.09.2026 abgelaufenen Aktion bleiben
    draußen: eine abgelaufene Aktion ist kein gültiger Preis."""
    alt = {**adaptersatz, "aktionen": [{**aktion, "gueltig_bis": ABGELAUFEN}]}

    assert fehlend(_klicksatz(alt), alt, MESSTAG) == ["aktionen"]


@pytest.mark.parametrize(
    ("feld", "wert"),
    [("bedingung", ""), ("betrag", None), ("gueltig_bis", ""), ("art", "bonus")],
    ids=["ohne-fussnote", "ohne-betrag", "ohne-frist", "keinem-feld-zuzuordnen"],
)
def test_nicht_belegte_aktion_bleibt_eine_luecke(adaptersatz, aktion, feld, wert):
    alt = {**adaptersatz, "aktionen": [{**aktion, feld: wert}]}

    assert fehlend(_klicksatz(alt), alt, MESSTAG) == ["aktionen"]


def test_anderer_anschlusspreis_im_klick_haelt_zurueck(adaptersatz):
    """Misst der Klick 15,00 € Anschluss, wo der Adapter 0,00 € nennt, hat die
    Aktion dort nicht gegriffen - dann ist sie nicht eindeutig zuordenbar."""
    klick = _klicksatz(adaptersatz, anschlusspreis=15.0)

    assert fehlend(klick, adaptersatz, MESSTAG) == ["aktionen"]


def test_ohne_messtag_bleibt_es_bei_der_strengen_lesart(adaptersatz):
    """Ohne Messtag ist die Frist nicht prüfbar - unbekannt fällt aus dem
    Vergleich, der Satz bleibt zurück."""
    assert fehlend(_klicksatz(adaptersatz), adaptersatz) == ["aktionen"]
