"""Zeitungsprinzip der KI-Seite (Pitch 9, Schnitt 2).

Jede KI-Meldung trägt genau ein KI-Ressort. Je Ressort stehen höchstens
zwölf Meldungen im Blatt, die neuesten; die älteren wandern ins Archiv.
Gegenprobe: elf Meldungen lassen das Archiv leer. Auf ``ki.html`` nennt der
Archivtitel genau so viele Meldungen, wie die Liste darunter führt. Feste
Tage, kein heute.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import pytest
from bestand_pfad import verlinke_neben_data

from telco_radar.analyze import ki_blatt
from telco_radar.config import load_config
from telco_radar.report.html import render_site

ANFANG = date(2026, 9, 1)
NETZBETREIBER = frozenset({"Deutsche Telekom", "SK Telecom"})


def _tag(i: int) -> str:
    return (ANFANG + timedelta(days=i)).isoformat()


def _meldung(i: int, titel: str, operator: str = "") -> dict:
    return {
        "url": f"https://example.org/ki/{i}",
        "title": titel,
        "summary": "",
        "operator": operator,
        "ki_datum": _tag(i),
        "relevance": 3,
    }


def _modelle(anzahl: int) -> list[dict]:
    return [_meldung(i, f"Neues Sprachmodell Nummer {i}") for i in range(anzahl)]


@pytest.mark.parametrize(
    ("titel", "operator", "erwartet"),
    [
        ("OpenAI stellt neues Sprachmodell vor", "OpenAI", "Modelle"),
        (
            "Nvidia liefert mehr GPUs für Rechenzentren",
            "Nvidia",
            "Chips & Rechenzentren",
        ),
        ("Start-up sammelt 200 Millionen Dollar ein", "", "Start-ups & Geld"),
        ("Neue App fasst E-Mails zusammen", "Apple", "Produkte"),
        ("EU verschärft Regeln des AI Act", "EU", "Regeln & Recht"),
        ("Forscher zeigen, wie Agenten planen", "", "Forschung"),
        ("Neue App fasst E-Mails zusammen", "Deutsche Telekom", "KI im Mobilfunk"),
        ("Operators test AI in the RAN", "", "KI im Mobilfunk"),
    ],
)
def test_jede_meldung_bekommt_ihr_ressort(titel, operator, erwartet):
    assert (
        ki_blatt.ressort({"title": titel, "operator": operator}, NETZBETREIBER)
        == erwartet
    )


def test_ressorts_sind_die_sieben_ki_ressorts():
    assert ki_blatt.RESSORTS == (
        "Modelle",
        "Chips & Rechenzentren",
        "Start-ups & Geld",
        "Produkte",
        "Regeln & Recht",
        "Forschung",
        "KI im Mobilfunk",
    )


def test_fuenfzehn_meldungen_zwoelf_im_blatt_drei_aelteste_im_archiv():
    meldungen = _modelle(15)
    blatt, archiv = ki_blatt.blatt(list(reversed(meldungen)), NETZBETREIBER)
    assert ki_blatt.HOECHSTENS_JE_RESSORT == 12
    assert [h["url"] for h in blatt] == [m["url"] for m in reversed(meldungen[3:])]
    assert [h["url"] for h in archiv] == [m["url"] for m in reversed(meldungen[:3])]


def test_elf_meldungen_lassen_das_archiv_leer():
    blatt, archiv = ki_blatt.blatt(_modelle(11), NETZBETREIBER)
    assert len(blatt) == 11
    assert archiv == []


def test_jede_meldung_genau_einmal_mit_genau_einem_ressort():
    meldungen = _modelle(14) + [
        _meldung(100 + i, "Telekom testet KI im Netz", "Deutsche Telekom")
        for i in range(13)
    ]
    blatt, archiv = ki_blatt.blatt(meldungen, NETZBETREIBER)
    urls = [h["url"] for h in blatt + archiv]
    assert sorted(urls) == sorted(m["url"] for m in meldungen)
    assert all(h["ki_ressort"] in ki_blatt.RESSORTS for h in blatt + archiv)
    je_ressort = {
        r: sum(h["ki_ressort"] == r for h in blatt) for r in ki_blatt.RESSORTS
    }
    assert je_ressort["Modelle"] == 12
    assert je_ressort["KI im Mobilfunk"] == 12
    assert len(archiv) == 3


def _ki_seite(tmp_path, anzahl: int) -> str:
    root = tmp_path / "repo"
    berichte = root / "data" / "reports"
    berichte.mkdir(parents=True)
    verlinke_neben_data(root)
    highlights = [
        {
            "url": f"https://example.org/ki-anbieter/{i}",
            "title": f"Neues Sprachmodell Nummer {i}",
            "summary": f"Neues Sprachmodell Nummer {i}",
            "source": "Beispielquelle",
            "date": _tag(i),
            "relevance": 3,
            "category": "Netz/Technologie",
        }
        for i in range(anzahl)
    ]
    bericht = {
        "date": "2026-10-09",
        "regions": {"KI-Anbieter": {"highlights": highlights}},
    }
    (berichte / "2026-10-09.json").write_text(json.dumps(bericht), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, berichte, load_config(root))
    return (site / "ki.html").read_text(encoding="utf-8")


def test_ki_seite_fuehrt_zwoelf_im_blatt_und_das_archiv_zugeklappt(tmp_path):
    ki = _ki_seite(tmp_path, 15)
    blatt = re.search(r'<section class="ki-blatt".*?</section>', ki, re.S).group(0)
    assert len(re.findall(r'<article class="ki-meldung', blatt)) == 12
    assert re.findall(r'<p class="ki-kicker">([^<]+)</p>', blatt) == ["Modelle"] * 12
    assert "höchstens 12 je Ressort, die älteste wandert ins Archiv." in blatt
    archiv = re.search(r'<details id="ki-archiv".*?</details>', blatt, re.S).group(0)
    assert '<details id="ki-archiv" open' not in archiv
    assert "Archiv · 3 ältere Meldungen" in archiv
    eintraege = re.findall(r'<a href="(https://example.org/ki-anbieter/\d+)"', archiv)
    assert eintraege == [f"https://example.org/ki-anbieter/{i}" for i in (2, 1, 0)]


def test_ki_seite_ohne_archiv_bei_elf_meldungen(tmp_path):
    ki = _ki_seite(tmp_path, 11)
    assert 'id="ki-archiv"' not in ki
    assert len(re.findall(r'<article class="ki-meldung', ki)) == 11
