"""Der Pflichtversand steht in den Kosten über 24 Monate (Ziel 1b, Antonio 05.11.2026).

„Einmalkosten eingerechnet“: Pflicht-Versandkosten wie die 6,99 € bei o2 zählen bei
jedem Anbieter, der sie ausweist; wo einer keine ausweist, zählt nichts dazu, und wo
der Versand nicht belegt ist, nennt die Seite die Lücke, statt 0 zu behaupten. Die
Beträge stehen mit URL und Abrufdatum in `config/versandkosten.yaml`. Dieses Modul
rechnet mit den echten Beträgen (`conftest._versand_nur_wo_er_gemeint_ist`).

`SOLL` sind die am 05.11.2026 an den Kostenübersichten der Anbieter gemessenen Beträge
(Belege: Bereich telcoradar/abnahme/versand-0511), bewusst noch einmal hier: weicht die
Datei ab, schlägt der Test aus.
"""

from __future__ import annotations

import datetime as dt

import pytest
import yaml
from bestand_pfad import abbild
from bs4 import BeautifulSoup
from test_geraete_zeitreihe_rechenweg import O2_MESSUNG, O2_TARIFE

from telco_radar import versandkosten
from telco_radar.config import load_config
from telco_radar.report import geraete_rechenweg as rechenweg
from telco_radar.report.geraete_rechnung import felder
from telco_radar.report.html import render_site
from telco_radar.tco_kosten import SCHRITT_VERSAND
from telco_radar.tco_model import Buendel, kosten_ueber, tco_24, tco_bindung
from telco_radar.versandkosten import POSTEN_VERSAND, versand_fuer

SOLL = {
    "Vodafone": 9.98,
    "Telekom": 0.0,
    "o2": 6.99,
    "congstar": 4.99,
    "1&1": 0.0,
}


def _messung(anbieter: str = "o2") -> dict:
    stand = {
        "id": O2_MESSUNG["id"],
        "sku_id": "samsung-galaxy-s23-128gb-rosa",
        "anbieter": anbieter,
        "tarif_name": "O2 Mobile on Demand M Plus",
    }
    return {"satz": dict(O2_MESSUNG), "stand": stand}


def _buendel(anbieter: str = "o2", **felder_) -> Buendel:
    werte = {
        "anbieter": anbieter,
        "sku_id": "apple-iphone-17-pro-256gb",
        "tarif_name": "O2 Mobile M",
        "tarif_monatlich": 14.99,
        "geraet_monatsrate": 54.5,
        "laufzeit_monate": 24,
        "geraet_zuzahlung": 7.0,
        "anschlusspreis": 39.99,
        "tarif_bindung_monate": 24,
    }
    werte.update(felder_)
    return Buendel(**werte)


def test_jeder_anbieter_hat_betrag_quelle_und_abrufdatum():
    tabelle = versandkosten.tabelle()
    assert {a.anbieter for a in tabelle.values()} == set(SOLL)
    for angabe in tabelle.values():
        assert angabe.betrag is not None, angabe.anbieter
        assert angabe.quelle.startswith("https://"), angabe.anbieter
        dt.date.fromisoformat(angabe.datum)
        assert angabe.screenshot, angabe.anbieter


@pytest.mark.parametrize(("anbieter", "betrag"), SOLL.items())
def test_betrag_je_anbieter(anbieter, betrag):
    assert versand_fuer(anbieter).betrag == betrag
    assert versand_fuer(anbieter.upper()).betrag == betrag, "Schreibweise egal"


@pytest.mark.parametrize(("anbieter", "betrag"), SOLL.items())
def test_versand_zaehlt_bei_jedem_anbieter_einmal_in_die_kosten(anbieter, betrag):
    """Dieselbe Regel für alle: der Betrag aus der Datei kommt einmal dazu."""
    mit = kosten_ueber(_buendel(anbieter))
    ohne = kosten_ueber(_buendel("Fantasie-Anbieter"))
    assert mit.gesamt == pytest.approx(ohne.gesamt + betrag, abs=0.001)
    assert (POSTEN_VERSAND in mit.posten) == (betrag > 0)
    assert (SCHRITT_VERSAND in {s.art for s in mit.rechnung}) == (betrag > 0)
    assert round(sum(s.summe for s in mit.rechnung), 2) == mit.gesamt
    assert mit.hinweise == [], "belegt: keine Lücke zu benennen"


def test_beispiel_o2_vorher_nachher():
    """1.714,75 € (Zeile der Rechenprobe) plus 6,99 € Versand."""
    k = kosten_ueber(_buendel("o2"))
    assert k.posten[POSTEN_VERSAND] == 6.99
    assert k.gesamt == 1721.74
    assert [(s.art, s.betrag) for s in k.rechnung][-2:] == [
        ("anschluss", 39.99),
        ("versand", 6.99),
    ]
    assert kosten_ueber(_buendel("Telekom")).gesamt == 1714.75, "0 € Versand"


def test_unbelegter_anbieter_zaehlt_nichts_dazu_und_sagt_es():
    """Nicht 0 erfinden: der Anbieter fehlt in der Datei, die Zahl bleibt, die
    Lücke steht in den Hinweisen."""
    k = kosten_ueber(_buendel("Fantasie-Anbieter"))
    assert k.gesamt == 1714.75
    assert POSTEN_VERSAND not in k.posten
    assert k.hinweise == ["Versand bei Fantasie-Anbieter nicht belegt"]
    assert felder(k)["versand_hinweise"] == k.hinweise
    assert felder(kosten_ueber(_buendel("o2")))["versand_hinweise"] == []


def test_betrag_null_in_der_datei_ist_eine_luecke_kein_nullbetrag(tmp_path):
    pfad = tmp_path / "versandkosten.yaml"
    pfad.write_text(
        yaml.safe_dump({"anbieter": {"X": {"betrag": None}, "Y": {"betrag": 0}}}),
        encoding="utf-8",
    )
    tabelle = versandkosten.laden(pfad)
    assert tabelle["x"].betrag is None
    assert tabelle["y"].betrag == 0.0
    pfad.write_text(
        yaml.safe_dump({"anbieter": {"Z": {"betrag": -1}}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Versand von Z"):
        versandkosten.laden(pfad)


def test_andere_rechnungen_derselben_zahl_zaehlen_denselben_versand():
    """Klappkarte (`tco_24`) und Bindungsrechnung (`tco_bindung`) rechnen wie
    `kosten_ueber`: eine Zahl, eine Regel."""
    b = _buendel("congstar")
    assert tco_24(b).bestandteile[POSTEN_VERSAND] == 4.99
    assert tco_24(b).gesamt == kosten_ueber(b).gesamt
    posten = [p for p in tco_bindung(b).bestandteile if p["name"] == POSTEN_VERSAND]
    assert posten == [{"name": POSTEN_VERSAND, "betrag": 4.99, "kategorie": "einmalig"}]
    assert POSTEN_VERSAND not in tco_24(_buendel("1&1")).bestandteile


def test_rechenweg_zeigt_den_versandposten():
    """Das Panel zerlegt die heutige Rechnung: der Versand steht als eigener
    Posten, und die Posten ergeben die Leitzahl."""
    r = rechenweg._rechung(_messung(), O2_TARIFE)
    assert [p["label"] for p in r["posten"]][:3] == [
        "Gerätezuzahlung",
        "Anschlusspreis",
        "Versand",
    ]
    versand = next(p for p in r["posten"] if p["label"] == "Versand")
    assert versand["betrag"] == 6.99
    assert round(sum(p["betrag"] for p in r["posten"]), 2) == r["gesamt"] == 1127.74
    assert "Versand" in rechenweg._rechung_html("o2", _messung(), O2_TARIFE)
    tk = rechenweg._rechung(_messung("Telekom"), O2_TARIFE)
    assert "Versand" not in [p["label"] for p in tk["posten"]]
    assert tk["gesamt"] == 1120.75


@pytest.fixture(scope="module")
def quellenseite(tmp_path_factory):
    wurzel = tmp_path_factory.mktemp("versand-seite")
    site = wurzel / "site"
    render_site(site, abbild(wurzel), load_config(wurzel))
    return BeautifulSoup(
        (site / "geraete-quellen.html").read_text(encoding="utf-8"), "html.parser"
    )


def test_die_seite_sagt_in_einem_satz_wie_versand_zaehlt(quellenseite):
    zeilen = [
        li
        for li in quellenseite.select("li.list-row")
        if li.select_one(".list-row-date").get_text(strip=True) == "Versandkosten"
    ]
    assert len(zeilen) == 1
    text = " ".join(zeilen[0].get_text(" ", strip=True).split())
    assert "einmalig in die Kosten über 24 Monate" in text
    assert "bei jedem Anbieter, der sie ausweist" in text
    assert "nicht erfasst" in text, "die Lücke wird benannt"


def test_gerenderte_zeile_nennt_den_unbelegten_versand(tmp_path, monkeypatch):
    """Muss-Auflage 1 der Prüfung PR 41: nicht nur die Datenebene (`hinweise`),
    die gerenderte Seite trägt den Satz an der Zeile des Anbieters. Gegenprobe:
    ist der Versand belegt, steht der Satz nirgends."""
    import test_geraete_tco_zustand as zustand

    _baue, lager, vorlage_text = (
        getattr(zustand, n) for n in ("_baue", "lager", "vorlage_text")
    )

    belegt = dict(versandkosten.tabelle())
    assert "o2" in belegt and belegt["o2"].betrag == 6.99

    monkeypatch.setattr(
        versandkosten, "_TABELLE", {k: v for k, v in belegt.items() if k != "o2"}
    )
    _baue(tmp_path / "unbelegt")
    zeilen = lager(tmp_path / "unbelegt").select('.gr-bnd[data-anbieter="o2"]')
    assert zeilen, "keine o2-Zeile gerendert"
    for zeile in zeilen:
        satz = zeile.select_one(".gr-bnd-versand-luecke")
        assert satz is not None, "der Hinweis fehlt auf der gerenderten Zeile"
        assert vorlage_text(satz) == "Versand bei o2 nicht belegt – mit 0 € gerechnet"

    monkeypatch.setattr(versandkosten, "_TABELLE", belegt)
    _baue(tmp_path / "belegt")
    seite = lager(tmp_path / "belegt")
    assert not seite.select(".gr-bnd-versand-luecke")
    assert "nicht belegt – mit 0 €" not in vorlage_text(seite)
