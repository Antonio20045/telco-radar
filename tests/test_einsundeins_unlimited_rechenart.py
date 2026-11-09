"""1&1 Unlimited XL im Export: Rechnung, Stufe und Herkunft gegen echte Daten.

Die Fixture ``tests/fixtures/einsundeins_unlimited`` ist ein Auszug aus dem Bestand
vom 09.11.2026: die 40 Gerätezeilen und die SIM-only-Zeile von "1&1 Unlimited XL"
(``stand.json``), der Tarif so, wie der Sammler ihn schreibt, mit Vodafones Leiter
(``tarife.jsonl``, Volumen unbegrenzt), und der Verlauf der zehn Zeilen, die am
Gerät gemessen sind oder deren Verlauf die Ursache zeigt (``historie.jsonl``, ab
01.11.). Erwartet wird nichts aus
festen Zahlen: jede Summe kommt aus den Feldern derselben Zeile, jede Stufe aus der
Herkunft und dem Verlauf der Fixture.

Die Ursache der zwei Stände (iPhone 18 Pro 256: 74,99 EUR/420 EUR und 77,99 EUR/460 EUR
im Wechsel) ist ein A/B-Test von 1&1 (``analyze/geraete_schwankung``).
"""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.analyze.geraete_pruefstatus import (
    HERLEITUNG_SCHLUSSZAHLUNG,
    HERLEITUNG_TARIFRASTER,
)
from telco_radar.analyze.geraete_schwankung import (
    rueckspruenge,
    schwankende_buendel,
)
from telco_radar.band_regel import band_fuer
from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_view
from telco_radar.report.geraete_laufzeit import raten_text
from telco_radar.report.geraete_zeilenband import zeilen_baender
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import Buendel

FIXTURE = Path(__file__).parent / "fixtures" / "einsundeins_unlimited"
HEUTE = "2026-11-09"
TARIF = "1&1 Unlimited XL"


@pytest.fixture(scope="module")
def stand() -> dict:
    return json.loads((FIXTURE / "stand.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tarife() -> dict:
    return Tarifbestand.aus_datei(FIXTURE / "tarife.jsonl").je_id


@pytest.fixture(scope="module")
def verlauf() -> dict[str, dict[str, tuple]]:
    """Je Bündel-ID: Messtag -> (Bündelpreis, Ablöse), wie die Historie ihn führt."""
    je_id: dict[str, dict[str, tuple]] = defaultdict(dict)
    for zeile in (FIXTURE / "historie.jsonl").read_text(encoding="utf-8").splitlines():
        satz = json.loads(zeile)
        je_id[satz["id"]][satz["datum"]] = (
            satz["buendel_monatlich"],
            satz["geraet_zuzahlung"],
        )
    return je_id


@pytest.fixture
def altdatei(tmp_path: Path) -> Path:
    """Die Historie der Fixture in der Ablage des Betriebs: eine Datei je Messtag."""
    je_tag: dict[str, list[str]] = defaultdict(list)
    for zeile in (FIXTURE / "historie.jsonl").read_text(encoding="utf-8").splitlines():
        je_tag[json.loads(zeile)["datum"]].append(zeile)
    ordner = tmp_path / "geraete_tco_historie"
    ordner.mkdir()
    for tag, zeilen in je_tag.items():
        (ordner / f"{tag}.jsonl").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return tmp_path / "geraete_tco_historie.jsonl"


def _auswertung(stand: dict, tarife: dict, tco_historie: dict | None) -> dict:
    return geraete_tco_view.aufbereiten(
        copy.deepcopy(stand["buendel"]),
        copy.deepcopy(stand["sim_only"]),
        copy.deepcopy(stand["listungen"]),
        lade_katalog(lese_wurzel()),
        tarife=tarife,
        tco_historie=tco_historie,
        heute=HEUTE,
    )


def _mit_verlauf(stand: dict, tarife: dict, altdatei: Path) -> dict:
    schwankend = schwankende_buendel(altdatei)
    assert schwankend is not None
    return _auswertung(stand, tarife, {"schwankend": sorted(schwankend)})


def _zeilen_je_sku(auswertung: dict) -> dict[str, dict]:
    return {
        z["sku_id"]: z for z in auswertung["export"]["buendel"] if z["tarif"] == TARIF
    }


def _springend(verlauf: dict, fenster: int = 7) -> set[str]:
    """Die Gegenprobe zu ``schwankende_buendel``: ein Stand kehrt wieder, den die Zeile
    zwischendurch verlassen hatte (aus den Rohwerten der Fixture, nicht dem Modul)."""
    tage = sorted({t for je_tag in verlauf.values() for t in je_tag})[-fenster:]
    ids = set()
    for bid, je_tag in verlauf.items():
        folge = [je_tag[t] for t in tage if t in je_tag]
        for i, wert in enumerate(folge):
            if i and wert != folge[i - 1] and wert in folge[: i - 1]:
                ids.add(bid)
    return ids


def _buendel(satz: dict, **aenderung) -> Buendel:
    felder = {k: v for k, v in satz.items() if k in Buendel.__dataclass_fields__}
    felder.pop("rabatte", None)
    return Buendel(**{**felder, **aenderung})


def test_die_ursache_der_zwei_staende_steht_im_verlauf(verlauf, stand, altdatei):
    """iPhone 18 Pro 256: zwei Stände im Wechsel, keine Preisbewegung einer Richtung."""
    pro = next(b for b in stand["buendel"] if "iphone-18-pro-256" in b["id"])
    staende = set(verlauf[pro["id"]].values())
    assert len(staende) == 2
    niedrig, hoch = sorted(staende)
    assert niedrig[0] < hoch[0] and niedrig[1] < hoch[1]
    assert schwankende_buendel(altdatei) == _springend(verlauf)
    assert pro["id"] in schwankende_buendel(altdatei)


def test_zwei_preisanstiege_nacheinander_sind_kein_wechsel(verlauf, stand, altdatei):
    """S26 Ultra stieg in einer Woche zweimal; zum alten Stand kehrte er nie zurück."""
    ultra = next(b for b in stand["buendel"] if "galaxy-s26-ultra" in b["id"])
    werte = list(verlauf[ultra["id"]].values())
    assert len(set(werte)) >= 3
    assert rueckspruenge(werte) == 0
    assert ultra["id"] not in schwankende_buendel(altdatei)


def test_jede_exportzeile_rechnet_aus_den_feldern_ihres_satzes(stand, tarife, altdatei):
    """24 x Bündelbetrag + Anschluss + Ablöse, aus dem Satz gelesen, nie eingetippt."""
    zeilen = _zeilen_je_sku(_mit_verlauf(stand, tarife, altdatei))
    saetze = [b for b in stand["buendel"] if b["tarif_name"] == TARIF]
    assert len(zeilen) == len(saetze) >= 40
    for satz in saetze:
        erwartet = (
            24 * satz["buendel_monatlich"]
            + satz["anschlusspreis"]
            + satz["geraet_zuzahlung"]
        )
        assert zeilen[satz["sku_id"]]["tco24"] == pytest.approx(erwartet), satz["id"]


def test_stufe_xl_nur_fuer_gemessene_zeilen_ohne_widerspruch(
    stand, tarife, verlauf, altdatei
):
    zeilen = _zeilen_je_sku(_mit_verlauf(stand, tarife, altdatei))
    widerspruch = _springend(verlauf)
    erwartet = {
        s["sku_id"]
        for s in stand["buendel"]
        if s["herleitung"] == HERLEITUNG_SCHLUSSZAHLUNG
        and s.get("quelle_art") == "klick"
        and s["id"] not in widerspruch
    }
    in_xl = {sku for sku, z in zeilen.items() if z["band"] == "XL"}
    assert in_xl == erwartet
    assert len(in_xl) >= 8
    abgeleitet = {
        s["sku_id"]
        for s in stand["buendel"]
        if s["herleitung"] == HERLEITUNG_TARIFRASTER
    }
    assert abgeleitet and all(zeilen[sku]["band"] == "" for sku in abgeleitet)
    pro = next(s for s in stand["buendel"] if "iphone-18-pro-256" in s["id"])
    assert pro["id"] in widerspruch and zeilen[pro["sku_id"]]["band"] == ""
    assert zeilen[pro["sku_id"]]["tco24"] is not None


def test_die_karte_traegt_dieselbe_stufe_wie_die_exportzeile(stand, tarife, altdatei):
    auswertung = _mit_verlauf(stand, tarife, altdatei)
    zeilen = _zeilen_je_sku(auswertung)
    gesehen = 0
    for modell in auswertung["modelle"]:
        for karte in modell["karten"]:
            if karte.get("tarif") == TARIF and karte.get("sku_id"):
                assert (karte["band"] or "").upper() == zeilen[karte["sku_id"]]["band"]
                gesehen += 1
    assert gesehen >= 8


def test_ohne_gelesenen_verlauf_bekommt_keine_unbegrenzt_zeile_eine_stufe(
    stand, tarife
):
    """Fail-closed: ist der Verlauf unbekannt, trägt keine Zeile des Tarifs ein Band;
    die SIM-only-Zeile (kein Gerät, keine Ablöse) bleibt in XL."""
    auswertung = _auswertung(stand, tarife, None)
    zeilen = _zeilen_je_sku(auswertung)
    assert zeilen and all(z["band"] == "" for z in zeilen.values())
    sim = [z for z in auswertung["export"]["sim_only"] if z["tarif"] == TARIF]
    assert sim and all(z["band"] == "XL" for z in sim)


def test_die_regel_kennt_keinen_anbieter(stand, tarife, altdatei):
    """Derselbe Satz unter anderem Anbieternamen: gleiche Stufe, gleiche Lücke."""
    schwankend = schwankende_buendel(altdatei)
    mess = next(b for b in stand["buendel"] if "iphone-17-pro-256" in b["id"])
    abgel = next(b for b in stand["buendel"] if "galaxy-s26-ultra" in b["id"])

    def stufen(anbieter: str) -> list:
        saetze = [_buendel(s, anbieter=anbieter) for s in (mess, abgel)]
        baender = zeilen_baender(tarife, saetze, schwankend)
        return [band_fuer(baender, s.tarif_id, s.id) for s in saetze]

    assert stufen("1&1") == stufen("Anderer Anbieter") == ["xl", None]


def test_eine_andere_herleitung_ist_nicht_sache_dieser_regel(stand, tarife):
    """Was die Notbremse als Schätzung führt (z.B. o2 'Tarifsumme minus Geräterate'),
    behält seine Stufe: hier geht es nur um das Raster und die Klick-Messung."""
    satz = next(b for b in stand["buendel"] if "iphone-17-pro-256" in b["id"])
    b = _buendel(satz, herleitung="tarifsumme_minus_geraeterate", quelle_art="")
    baender = zeilen_baender(tarife, [b], [])
    assert band_fuer(baender, b.tarif_id, b.id) == "xl"


def test_das_etikett_ist_24_monate_plus_abloese(stand):
    satz = next(b for b in stand["buendel"] if b["tarif_name"] == TARIF)
    karte = {
        "raten_laufzeit": satz["laufzeit_monate"],
        "buendel_monatlich": satz["buendel_monatlich"],
    }
    assert raten_text(karte) == "24 Monate + Ablöse"
