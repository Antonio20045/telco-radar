"""Bereiche wie die Tabs: Meldungen, Promo, Geraete - und was wofuer gilt."""

from pathlib import Path

import pytest

from telco_radar.newsletter.config import lade_katalog
from telco_radar.newsletter.filters import Filtersatz, waehle
from telco_radar.newsletter.quelle import aus_promo
from telco_radar.newsletter.segments import Segment, geraete_fuer

WURZEL = Path(__file__).resolve().parents[1]

AKTIONEN = [
    {
        "id": "alt",
        "brand": "Telekom",
        "headline": "Alte Aktion",
        "status": "aktiv",
        "url": "https://beispiel.test/alt",
        "first_seen": "2026-10-02T08:00:00",
    },
    {
        "id": "neu",
        "brand": "o2",
        "headline": "Neue Aktion",
        "status": "aktiv",
        "url": "https://beispiel.test/neu",
        "first_seen": "2026-10-10T08:00:00",
    },
]

BLOCK = {
    "im_newsletter": True,
    "vergleichstag": "2026-10-03",
    "stichtag": "2026-10-10",
    "geprueft": 4,
    "zeilen": [{"anbieter": "Telekom"}, {"anbieter": "o2"}],
}


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(WURZEL)


def test_der_katalog_folgt_den_tabs(katalog):
    assert [a.label for a in katalog.bereiche] == ["Meldungen", "Promo", "Geräte"]


def test_nur_aktionen_seit_der_vorigen_ausgabe():
    assert [e.titel for e in aus_promo(AKTIONEN)] == ["Alte Aktion", "Neue Aktion"]
    assert [e.titel for e in aus_promo(AKTIONEN, neu_nach="2026-10-09")] == [
        "Neue Aktion"
    ]


def test_region_und_thema_filtern_keine_aktionen_weg(katalog):
    satz = Filtersatz(bereiche=("promo",), regionen=("asien",), kategorien=("netz",))
    assert len(waehle(aus_promo(AKTIONEN), satz, katalog)) == 2
    satz = Filtersatz(bereiche=("promo",), wettbewerber=("o2",))
    assert [t.eintrag.titel for t in waehle(aus_promo(AKTIONEN), satz, katalog)] == [
        "Neue Aktion"
    ]


def test_geraeteblock_nach_bereich_und_wettbewerber(katalog):
    assert geraete_fuer(Filtersatz(), BLOCK, katalog) is BLOCK
    assert geraete_fuer(Filtersatz(bereiche=("promo",)), BLOCK, katalog) is None
    nur_telekom = geraete_fuer(
        Filtersatz(bereiche=("geraete",), wettbewerber=("telekom",)), BLOCK, katalog
    )
    assert nur_telekom["zeilen"] == [{"anbieter": "Telekom"}]
    assert geraete_fuer(Filtersatz(), None, katalog) is None


def test_ein_segment_mit_geraetebewegung_ist_nicht_leer():
    assert Segment(hash="h", filter=Filtersatz()).leer
    assert not Segment(hash="h", filter=Filtersatz(), geraete=BLOCK).leer
    ohne_woche = dict(BLOCK, im_newsletter=False)
    assert Segment(hash="h", filter=Filtersatz(), geraete=ohne_woche).leer
    ohne_zeilen = dict(BLOCK, zeilen=[])
    assert Segment(hash="h", filter=Filtersatz(), geraete=ohne_zeilen).leer
