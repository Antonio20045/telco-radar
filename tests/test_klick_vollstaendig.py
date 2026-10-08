"""Wann ein Klick-Satz einen Adaptersatz ersetzt (``analyze.klick_vollstaendig``).

Klick-Satz: die echte o2-Lesung zu iPhone 17 Pro 512 GB, M Plus, 24 Raten
(``tests/klickergebnisse.py``). Der Adaptersatz trägt dieselben Werte und dazu eine
Preisphase oder eine Aktion, wie sie der Gerätelauf am 08.10.2026 bei congstar und o2
las: die Phase 1–24 zum Grundpreis bei 24 Monaten Bindung oder ein nicht
eingerechneter Trade-in. Beide sagen nichts über die Werte hinaus und halten den
Klick-Satz nicht zurück; eine Phase über die Bindung hinaus, ein anderer Betrag auch um
einen halben Cent, zwei Phasen, ein Listenpreis daneben oder eine eingerechnete Aktion
schon. Die Leitzahl bleibt dieselbe.
"""

from __future__ import annotations

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel
from klickergebnisse import O2_SEITE, erfasst, ergebnisdatei, lauf, o2_lesung

from telco_radar.analyze.klick_vollstaendig import VERGLEICHSFELDER
from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.geraete_config import lade_katalog
from telco_radar.report.geraete_tco_karten import geraet_aus_sku
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_kosten import kosten_ueber

HEUTE = "2026-09-29"
SKU = "apple-iphone-17-pro-512gb-silber"
M_PLUS = "O2 Mobile Unlimited M Plus"
M_PLUS_ADAPTER = "O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)"
M_PLUS_SLUG = "o2-mobile-unlimited-m-plus"
TRADE_IN = {
    "art": "trade_in",
    "bedingung": "Altgerät eintauschen",
    "quelle_url": "https://www.o2online.de/",
    "betrag": 150.0,
    "betrag_monatlich": None,
    "eingerechnet": False,
    "gueltig_bis": None,
}


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def bestand():
    return Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")


def _geraet(katalog):
    return lambda sku: geraet_aus_sku(sku, katalog)


def _datei():
    kombination = erfasst(o2_lesung("512 GB", M_PLUS, 24))
    return ergebnisdatei("o2", "o2", [(O2_SEITE, lauf(O2_SEITE, [kombination]))], HEUTE)


@pytest.fixture(scope="module")
def klicksatz(katalog):
    """Die Lesung als Rohsatz ohne Gegenstück: 19,99 € Tarif, 24 Monate Bindung."""
    zug = fuehre_zusammen([], [_datei()], katalog, HEUTE, _geraet(katalog))
    (satz,) = zug.rohsaetze
    assert (satz["tarif_monatlich"], satz["tarif_bindung_monate"]) == (19.99, 24)
    assert satz["tarif_phasen"] == [] and "aktionen" not in satz
    return satz


def _adapter(klicksatz: dict, **felder) -> dict:
    """Ein o2-Adaptersatz mit denselben Werten wie die Lesung."""
    return {
        "sku_id": SKU,
        "anbieter": "o2",
        "zustand": "neu",
        "tarif_name": M_PLUS_ADAPTER,
        "tarif_slug": M_PLUS_SLUG,
        "laufzeit_monate": 24,
        **{f: klicksatz[f] for f in VERGLEICHSFELDER},
        **felder,
    }


def _phase(von: int, bis: int | None, betrag: float) -> dict:
    return {"von_monat": von, "bis_monat": bis, "betrag": betrag, "beleg": "Adapter"}


def _zusammen(katalog, alt: dict):
    return fuehre_zusammen([alt], [_datei()], katalog, HEUTE, _geraet(katalog))


@pytest.mark.parametrize(
    ("phasen", "bindung"),
    [
        ([_phase(1, 24, 19.99)], 24),
        ([_phase(1, None, 19.99)], 24),
        ([_phase(1, 24, 19.99)], None),
        ([_phase(1, 24, 19.99)], 0),
    ],
    ids=["bis-bindung", "offen", "ohne-bindung", "bindung-null"],
)
def test_grundpreisphase_haelt_den_klick_nicht_zurueck(
    katalog, bestand, klicksatz, phasen, bindung
):
    alt = _adapter(klicksatz, tarif_phasen=phasen, tarif_bindung_monate=bindung)

    zug = _zusammen(katalog, alt)

    (satz,) = zug.rohsaetze
    assert satz["quelle_art"] == "klick" and satz["sku_id"] == SKU
    assert zug.bilanz["ersetzt"] == 1
    assert zug.bilanz["unvollstaendig"] == {"nicht_ersetzt": 0, "felder": {}}
    (vorher,) = aus_rohsaetzen([alt], bestand, HEUTE).buendel
    (nachher,) = aus_rohsaetzen(zug.rohsaetze, bestand, HEUTE).buendel
    assert kosten_ueber(vorher).gesamt == kosten_ueber(nachher).gesamt
    assert kosten_ueber(nachher).gesamt == round(7.0 + 24 * 66.0 + 24 * 19.99, 2)


@pytest.mark.parametrize(
    ("phasen", "bindung"),
    [
        ([_phase(1, 36, 19.99)], 24),
        ([_phase(1, 24, 24.99)], 24),
        ([_phase(1, 12, 9.99), _phase(13, 24, 19.99)], 24),
        ([_phase(1, 12, 19.99)], 24),
        ([_phase(2, 24, 19.99)], 24),
        ([_phase(1, 24, 19.99)], 12),
        ([_phase(1, 24, 19.985)], 24),
        ([_phase(1, 36, 19.99)], None),
    ],
    ids=[
        "ueber-die-bindung",
        "anderer-betrag",
        "zwei-phasen",
        "vor-der-bindung-zu-ende",
        "nicht-ab-monat-eins",
        "bindung-kuerzer",
        "halber-cent",
        "ohne-bindung-bis-36",
    ],
)
def test_gemessene_phase_haelt_den_klick_zurueck(katalog, klicksatz, phasen, bindung):
    alt = _adapter(klicksatz, tarif_phasen=phasen, tarif_bindung_monate=bindung)

    zug = _zusammen(katalog, alt)

    assert zug.rohsaetze == [alt]
    assert zug.bilanz["ersetzt"] == 0
    assert zug.bilanz["unvollstaendig"]["felder"]["tarif_phasen"] == 1


def test_aktionspreis_mit_listenpreis_haelt_den_klick_zurueck(katalog, klicksatz):
    """Vodafone, Rechenweise 2: die Phase zu 19,99 € ist der Aktionspreis, der
    Listenpreis 29,99 € steht daneben. Ohne Listenpreis im Klick bliebe Regel 3 ohne
    Maßstab; der Adaptersatz bleibt ganz."""
    alt = _adapter(
        klicksatz, tarif_listenpreis=29.99, tarif_phasen=[_phase(1, 24, 19.99)]
    )

    zug = _zusammen(katalog, alt)

    assert zug.rohsaetze == [alt]
    assert zug.bilanz["unvollstaendig"] == {
        "nicht_ersetzt": 1,
        "felder": {"tarif_listenpreis": 1, "tarif_phasen": 1},
    }


def test_nicht_eingerechnete_aktion_reist_mit(katalog, bestand, klicksatz):
    alt = _adapter(klicksatz, aktionen=[TRADE_IN])

    zug = _zusammen(katalog, alt)

    (satz,) = zug.rohsaetze
    assert satz["quelle_art"] == "klick" and satz["aktionen"] == [TRADE_IN]
    assert zug.bilanz["ersetzt"] == 1
    (b,) = aus_rohsaetzen(zug.rohsaetze, bestand, HEUTE).buendel
    assert [(a.art, a.betrag, a.eingerechnet) for a in b.aktionen] == [
        ("trade_in", 150.0, False)
    ]


@pytest.mark.parametrize(
    "aktion",
    [
        {**TRADE_IN, "art": "tarifrabatt", "eingerechnet": True},
        {k: v for k, v in TRADE_IN.items() if k != "eingerechnet"},
        {**TRADE_IN, "eingerechnet": "nein"},
    ],
    ids=["eingerechnet", "ohne-angabe", "unlesbar"],
)
def test_eingerechnete_oder_unklare_aktion_haelt_den_klick_zurueck(
    katalog, klicksatz, aktion
):
    alt = _adapter(klicksatz, aktionen=[TRADE_IN, aktion])

    zug = _zusammen(katalog, alt)

    assert zug.rohsaetze == [alt]
    assert zug.bilanz["unvollstaendig"] == {
        "nicht_ersetzt": 1,
        "felder": {"aktionen": 1},
    }


def test_ohne_phase_und_aktion_wie_bisher(katalog, klicksatz):
    """Gegenprobe: ein Adaptersatz ohne Phase und Aktion wird ersetzt, ohne dass der
    Klick-Satz eine Aktion bekommt."""
    zug = _zusammen(katalog, _adapter(klicksatz))

    (satz,) = zug.rohsaetze
    assert satz["quelle_art"] == "klick" and "aktionen" not in satz
    assert zug.bilanz["gegenprobe"]["gleich"] == 1
