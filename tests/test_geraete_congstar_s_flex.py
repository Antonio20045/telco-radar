"""congstar: "Allnet Flat S Flex" fällt nicht mehr aus jedem Bündel.

BEFUND 20.11.2026 (Geräte-Lauf, Rohlog): "Buendel: 117 Saetze ohne aufloesbaren
Tarif verworfen - im Tarifbestand fehlen 2 Tarife, haeufigste: Allnet Flat S Flex
(115x)". Jedes congstar-Gerät verlor damit eine von acht Tarifstufen.

Ursache in `data/state/tarife.jsonl`: das Pflichtblatt 559 steht zweimal im
Bestand - am 17.11.2026 gelesen als `congstar:allnet-flat-s-flex-mit-gb`, am
19.11.2026 als `congstar:allnet-flat-s-flex-vermarktung-seit-01-07` mit dem Namen
"Allnet Flat S Flex (Postpaid Mobilfunk) Vermarktung seit: 01/07/2026". Die
Namenszeile des neuen Blatts trägt das Vermarktungsdatum hinter der Klammer, das
Namensmuster verlangte das Zeilenende direkt nach ihr. Zwei Sätze mit Nummer 559
machten die Nummern-Brücke (`ergaenze_pib_slug`) mehrdeutig, also gab es keine.
"""

from __future__ import annotations

from telco_radar.collect.geraete.congstar import ergaenze_pib_slug
from telco_radar.collect.tarif_pdf import lies_text
from telco_radar.tarif_bezug import Tarifbestand

_BLATT_559 = (
    "https://www.congstar.de/fileadmin/produktinformationsblatt/"
    "Produktinformationsblatt_559.pdf"
)


def _satz(tarif_id: str, name: str, abgerufen_am: str | None) -> dict:
    satz = {
        "tarif_id": tarif_id,
        "anbieter": "congstar",
        "name": name,
        "grundgebuehr": 20.0,
        "dokument_url": _BLATT_559,
    }
    if abgerufen_am is not None:
        satz["abgerufen_am"] = abgerufen_am
    return satz


def test_die_juengste_lesung_desselben_blatts_bekommt_die_bruecke():
    bestand = Tarifbestand(
        [
            _satz(
                "congstar:allnet-flat-s-flex-mit-gb",
                "Allnet Flat S Flex mit GB+",
                "2026-11-17",
            ),
            _satz("congstar:allnet-flat-s-flex", "Allnet Flat S Flex", "2026-11-19"),
        ]
    )
    assert ergaenze_pib_slug(bestand) == 1
    assert bestand.je_id["congstar:allnet-flat-s-flex"]["buendel_slug"] == "559"
    assert "buendel_slug" not in bestand.je_id["congstar:allnet-flat-s-flex-mit-gb"]


def test_die_lesungen_aus_dem_bestand_vom_17_und_19_11_sind_derselbe_tarif():
    bestand = Tarifbestand(
        [
            _satz(
                "congstar:allnet-flat-s-flex-mit-gb",
                "Allnet Flat S Flex mit GB+",
                "2026-11-17",
            ),
            _satz(
                "congstar:allnet-flat-s-flex-vermarktung-seit-01-07",
                "Allnet Flat S Flex (Postpaid Mobilfunk) Vermarktung seit: 01/07/2026",
                "2026-11-19",
            ),
        ]
    )
    assert ergaenze_pib_slug(bestand) == 1
    neu = bestand.je_id["congstar:allnet-flat-s-flex-vermarktung-seit-01-07"]
    assert neu["buendel_slug"] == "559"


def test_zwei_verschiedene_tarife_mit_derselben_nummer_bekommen_keine_bruecke():
    bestand = Tarifbestand(
        [
            _satz("congstar:allnet-flat-s-flex", "Allnet Flat S Flex", "2026-11-17"),
            _satz("congstar:allnet-flat-m", "Allnet Flat M", "2026-11-19"),
        ]
    )
    assert ergaenze_pib_slug(bestand) == 0


def test_derselbe_name_mit_anderer_grundgebuehr_bekommt_keine_bruecke():
    alt = _satz("congstar:s-flex-alt", "Allnet Flat S Flex", "2026-11-17")
    neu = {**_satz("congstar:s-flex", "Allnet Flat S Flex", "2026-11-19")}
    neu["grundgebuehr"] = 25.0
    assert ergaenze_pib_slug(Tarifbestand([alt, neu])) == 0


def test_zwei_lesungen_vom_selben_tag_bleiben_mehrdeutig():
    bestand = Tarifbestand(
        [
            _satz("congstar:a", "A", "2026-11-19"),
            _satz("congstar:b", "B", "2026-11-19"),
        ]
    )
    assert ergaenze_pib_slug(bestand) == 0


def test_ohne_lesedatum_bleibt_eine_doppelte_nummer_mehrdeutig():
    bestand = Tarifbestand(
        [_satz("congstar:a", "A", None), _satz("congstar:b", "B", "2026-11-19")]
    )
    assert ergaenze_pib_slug(bestand) == 0


def test_das_vermarktungsdatum_hinter_der_klammer_gehoert_nicht_zum_namen():
    roh = (
        "Produktinformationsblatt gem. § 1 TK-Transparenzverordnung\n"
        "Allnet Flat S Flex (Postpaid Mobilfunk) Vermarktung seit: 01/07/2026\n"
        "Keine Mindestvertragslaufzeit\n"
        "Entgelt Allnet Flat S Flex (ohne Endgerät) 20,00 € / Monat\n"
    )
    t = lies_text(roh)
    assert t.name == "Allnet Flat S Flex"
    assert t.art == "mobilfunk"
    assert t.fehlende_belege() == []
