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


def test_die_mail_gliedert_nach_bereichen_wie_die_tabs():
    from telco_radar.newsletter.render import abschnitte, lade_chrome

    items = [
        {"titel": "A", "bereich": "promo"},
        {"titel": "B", "bereich": "marktrecherche"},
        {"titel": "C", "bereich": "unbekannt"},
    ]
    aus = abschnitte(items, lade_chrome())
    assert [a["titel"] for a in aus] == ["Meldungen", "Promo"]
    assert [i["titel"] for i in aus[0]["items"]] == ["B", "C"]
    assert sum(len(a["items"]) for a in aus) == len(items)


def test_viele_aktionen_verdraengen_keine_meldung(katalog):
    from telco_radar.newsletter.filters import Eintrag

    def eintrag(nr, bereich, gewicht):
        return Eintrag(
            id=f"{bereich}-{nr}",
            bereich=bereich,
            titel=f"{bereich} {nr}",
            text="",
            url=f"https://beispiel.test/{bereich}/{nr}",
            gewicht=gewicht,
        )

    aktionen = [eintrag(n, "promo", 30) for n in range(20)]
    meldungen = [eintrag(n, "marktrecherche", 2) for n in range(3)]
    deckel = katalog.grenzen.max_eintraege
    gewaehlt = [
        t.eintrag.bereich for t in waehle(aktionen + meldungen, Filtersatz(), katalog)
    ]
    assert gewaehlt.count("marktrecherche") == 3
    assert gewaehlt.count("promo") == deckel


def test_der_betreff_nennt_die_erste_meldung_vor_aktionen(katalog):
    from telco_radar.newsletter.filters import Eintrag
    from telco_radar.newsletter.render import betreff, lade_chrome

    aktion = Eintrag(
        id="a", bereich="promo", titel="Aktion", text="", url="u", gewicht=30
    )
    meldung = Eintrag(
        id="m", bereich="marktrecherche", titel="Meldung", text="", url="v"
    )
    treffer = waehle([aktion, meldung], Filtersatz(), katalog)
    assert treffer[0].eintrag.titel == "Aktion"
    assert "Meldung (+1 weitere)" in betreff("10. Oktober 2026", treffer, lade_chrome())
