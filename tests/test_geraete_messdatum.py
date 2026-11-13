"""Brief messdatum-0811 (Antonio, 08.11.2026 13:20): das letzte Messdatum je Anbieter.

Die Seite sagte „Stand 08.11.2026“ (Tag der Berechnung) und trug das Abrufdatum erst an
der einzelnen Zeile. Jetzt steht oben je Anbieter „zuletzt gemessen am …“, ein Anbieter
nicht vom jüngsten Messtag trägt „Stand vom TT.MM.“, und ohne lesbares Datum heißt es
„Messdatum unbekannt“ - nie das heutige (fail-closed, Clean Code 4).

Alle Fixtures setzen ihr Datum selbst (harte Regel 7): HEUTE ist der 08.11.2026, Telekom
wurde zuletzt am 07.11. gemessen (Schutzseite am Morgen des 08.11.).
"""

from __future__ import annotations

import json
import shutil

import test_geraete_buendel_kopf_zeitraum as basis
from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_messdatum, geraete_view
from telco_radar.report.html import render_site

HEUTE = "2026-11-08"
BERICHT = "2026-11-07"


def _b(anbieter, tag):
    return {"anbieter": anbieter, "abgerufen_am": tag}


def _zeilen(buendel, heute=HEUTE):
    ergebnis = geraete_messdatum.je_anbieter(buendel, heute)
    return {z["name"]: z for z in ergebnis["zeilen"]}


def test_jeder_anbieter_nennt_sein_juengstes_messdatum():
    z = _zeilen(
        [
            _b("Vodafone", "2026-11-08"),
            _b("Vodafone", "2026-11-02"),
            _b("Telekom", "2026-11-07"),
            _b("Telekom", "2026-10-20"),
            _b("o2", "2026-11-08"),
            _b("1&1", "2026-11-08"),
            _b("congstar", "2026-11-08"),
        ]
    )
    assert z["Telekom"]["satz"] == "Telekom: zuletzt gemessen am 07.11.2026"
    assert z["Vodafone"]["satz"] == "Vodafone: zuletzt gemessen am 08.11.2026"
    assert z["Telekom"]["stand"] == "Stand vom 07.11."
    assert z["Vodafone"]["stand"] == "" and not z["Vodafone"]["alt"]


def test_ohne_lesbares_datum_steht_messdatum_unbekannt_nie_heute():
    z = _zeilen(
        [
            _b("Vodafone", "2026-11-08"),
            _b("Telekom", ""),
            _b("Telekom", None),
            _b("o2", "kein-datum"),
            _b("1&1", "2026-11-09"),
        ]
    )
    for name in ("Telekom", "o2", "1&1", "congstar"):
        assert z[name]["satz"] == f"{name}: Messdatum unbekannt"
        assert z[name]["datum"] == ""
        assert "08.11.2026" not in z[name]["satz"]


def test_stand_vom_an_der_zeile():
    assert geraete_messdatum.stand_vom("2026-09-15", "2026-11-08") == "Stand vom 15.09."
    assert geraete_messdatum.stand_vom("2026-11-08", "2026-11-08") == ""
    assert geraete_messdatum.stand_vom("", "2026-11-08") == "Messdatum unbekannt"
    assert geraete_messdatum.stand_vom(None, "2026-11-08") == "Messdatum unbekannt"


def test_stand_vom_faengt_zukunft_und_unlesbares_fail_closed():
    """Zukunft gegen den Vergleichstag, unlesbar, kein Vergleichstag: nie geraten."""
    assert (
        geraete_messdatum.stand_vom("2026-12-31", "2026-11-08") == "Messdatum unbekannt"
    )
    assert (
        geraete_messdatum.stand_vom("kein-datum", "2026-11-08") == "Messdatum unbekannt"
    )
    assert geraete_messdatum.stand_vom("2026-11-07", "") == "Messdatum unbekannt"


def test_juengster_tag_laesst_unlesbares_und_zukunft_nicht_gewinnen():
    """String-Sort stellt „kein-datum“ und „2026-12-31“ nach oben; sie zählen nicht."""
    daten = ["2026-11-07", "kein-datum", "2026-12-31", "", None, "2026-11-08"]
    assert geraete_messdatum.juengster_tag(daten, HEUTE) == "2026-11-08"
    assert geraete_messdatum.juengster_tag(["kein-datum", ""], HEUTE) == ""


def test_anteil_je_anbieter_n_von_m():
    z = _zeilen(
        [_b("o2", "2026-11-08")] * 2
        + [_b("o2", "2026-11-07"), _b("o2", ""), _b("Vodafone", "2026-11-08")]
    )
    assert z["o2"]["anteil"] == "2 von 4 gezeigten Preisen von diesem Tag"
    assert z["Vodafone"]["anteil"] == "1 von 1 gezeigten Preisen von diesem Tag"
    assert z["Telekom"]["anteil"] == ""
    viele = _zeilen([_b("o2", "2026-11-08")] * 1200)
    assert viele["o2"]["anteil"] == "1.200 von 1.200 gezeigten Preisen von diesem Tag"


def test_anteil_zaehlt_die_karten_der_seite_nicht_die_farben_im_bestand():
    """Gegen `origin/main` rot: der Nenner las die rohen Bündel und zählte dieselbe
    Zeile je Farbe mit - die Karten-Dedupe der Seite zeigt davon nur die frische
    (Befund 13.11.2026: 976 der 1.995 „nicht von heute“ waren solche Farbvarianten).
    Eine Karte ohne Messdatum ist ein Leerzustand und zählt in keiner der beiden
    Zahlen."""
    tco = {
        "modelle": [
            {
                "karten": [
                    {"anbieter": "o2", "abgerufen_am": HEUTE},
                    {"anbieter": "o2", "abgerufen_am": None},
                ]
            }
        ],
        "export": {
            "buendel": [
                _b("o2", HEUTE),
                _b("o2", "2026-10-20"),
                _b("o2", "2026-10-20"),
            ]
        },
    }
    felder = geraete_messdatum.felder([], tco, HEUTE, HEUTE, HEUTE)
    zeilen = {z["name"]: z for z in felder["messdatum"]["zeilen"]}
    assert zeilen["o2"]["anteil"] == "1 von 1 gezeigten Preisen von diesem Tag"
    assert zeilen["o2"]["datum"] == HEUTE


def _baue_wie_live(tmp_path, einzel=None):
    """Der echte Pfad, wie am 08.11.2026: der jüngste Tagesbericht ist vom 07.11., die
    Bündeldatei trägt `updated` 08.11.; Vodafone, o2 und congstar sind am 08.11.
    gemessen, Telekom nur am 07.11. Gerendert wird aus dem Bestand auf der Platte -
    kein `heute`, kein `geraete`-Dict von Hand."""
    site = basis._baue(tmp_path)
    wurzel = site.parent
    state = wurzel / "data" / "state"
    datei = state / "geraete_tco.json"
    tco = json.loads(datei.read_text(encoding="utf-8"))
    tco["updated"] = HEUTE
    for b in tco["buendel"]:
        b["abgerufen_am"] = "2026-11-07" if b["anbieter"] == "Telekom" else HEUTE
    datei.write_text(json.dumps(tco), encoding="utf-8")
    dbdatei = state / "geraete_db.json"
    db = json.loads(dbdatei.read_text(encoding="utf-8"))
    db["updated"] = HEUTE
    for listung, tag in zip(db["listungen"], einzel or (), strict=False):
        listung["abgerufen_am"] = tag
    dbdatei.write_text(json.dumps(db), encoding="utf-8")
    berichte = wurzel / "data" / "reports"
    for alt in berichte.iterdir():
        alt.unlink()
    (berichte / f"{BERICHT}.json").write_text(
        json.dumps(
            {
                "date": BERICHT,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- x\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (berichte / f"{BERICHT}.md").write_text("# Bericht\n", encoding="utf-8")
    shutil.rmtree(site)
    render_site(site, berichte)
    return site


def _liste(site):
    suppe = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    return suppe, {
        li["data-anbieter"]: li.get_text(" ", strip=True)
        for li in suppe.select("#messdatum li")
    }


def test_die_seite_nennt_aus_dem_bestand_vodafone_0811_und_telekom_0711(tmp_path):
    """Ohne die Korrektur rot: die Zukunftssperre nahm `geraete.stand` (07.11., Datum
    des jüngsten Tagesberichts) und verwarf alle Messungen vom 08.11.; Vodafone stand
    dann als „Messdatum unbekannt“, die Telekom-Lücke blieb unsichtbar."""
    site = _baue_wie_live(tmp_path)
    _, je = _liste(site)
    assert je["Vodafone"].startswith("Vodafone: zuletzt gemessen am 08.11.2026"), je
    assert je["o2"].startswith("o2: zuletzt gemessen am 08.11.2026"), je
    assert je["congstar"].startswith("congstar: zuletzt gemessen am 08.11.2026"), je
    assert je["Telekom"].startswith("Telekom: zuletzt gemessen am 07.11.2026"), je
    assert je["Telekom"].endswith("Stand vom 07.11."), je
    assert "Stand vom" not in je["Vodafone"] + je["o2"] + je["congstar"]
    assert "1 von 1 gezeigten Preisen von diesem Tag" in je["Telekom"]
    assert je["1&1"] == "1&1: Messdatum unbekannt"


def test_das_view_feld_traegt_den_messstichtag_nicht_das_berichtsdatum(tmp_path):
    site = _baue_wie_live(tmp_path)
    wurzel = site.parent
    geraete = geraete_view.aufbereiten(
        wurzel / "data" / "state",
        lade_quellen(wurzel),
        lade_katalog(wurzel),
        heute=BERICHT,
    )
    assert geraete["messdatum"]["juengster"] == HEUTE
    assert geraete["stand"] == BERICHT


def test_einzelgeraet_zelle_faengt_zukunft_und_unlesbares_ab(tmp_path):
    site = _baue_wie_live(tmp_path, einzel=["2026-11-08", "kein-datum"])
    suppe, _ = _liste(site)
    zellen = [
        td.get_text(" ", strip=True) for td in suppe.select("td:has(.gr-a-datum)")
    ]
    assert zellen, "keine Einzelgerät-Zelle gefunden - der Test prüft nichts"
    assert any(z.endswith("Messdatum unbekannt") for z in zellen), zellen
    assert any(z == "8. November 2026" for z in zellen), zellen
    suppe2, _ = _liste(
        _baue_wie_live(tmp_path / "zwei", einzel=["2026-11-08", "2026-11-08"])
    )
    zellen2 = [
        td.get_text(" ", strip=True) for td in suppe2.select("td:has(.gr-a-datum)")
    ]
    assert not any("Messdatum unbekannt" in z or "Stand vom" in z for z in zellen2), (
        zellen2
    )
