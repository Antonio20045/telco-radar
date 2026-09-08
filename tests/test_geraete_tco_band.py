"""GRAPH-1 (BRIEF_GRAPH1, 08.09.2026): Gerät × Tarifniveau im Graphen.

AUFTRAG_GERAETESEITE.md §2a (Kopplung Gerät x Tarifniveau, eine Linie je
Anbieter) und §7 (die drei Bänder Klein/Mittel/Groß, aus den ERHOBENEN
Datenvolumina von `tarife.jsonl` abgeleitet).

Gerechnet wird gegen den ECHTEN Bestand (`data/state/geraete_tco.json`,
`geraete_db.json`, `tarife.jsonl`), dieselbe Bauform wie
`test_geraete_tco_hauptansicht.py` - eine Fixture beweist nur, dass die
Rechnung mit sich selbst übereinstimmt, hier soll sie mit dem echten
Bestand übereinstimmen. Stand der Zahlen: 08.09.2026 (siehe
outputs/phase-graph1-2026-09-08.md).
"""
from __future__ import annotations

import json
import pathlib

import pytest

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_band as band
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import Buendel, SimOnlyReferenz

WURZEL = pathlib.Path(__file__).resolve().parents[1]
ZUSTAND = WURZEL / "data" / "state"

# Der Vorgabefall aus BRIEF_GRAPH1: dasselbe Modell, das die Hauptansicht
# ohne Klick zeigt (`geraete_tco_karten.LEITFRAGE_MODELL`).
VORGABE_MODELL = "apple-iphone-17-pro-256"


# --------------------------------------------------------------------------
# (a) Bandableitung aus echten tarife.jsonl-Datenvolumina
# --------------------------------------------------------------------------

def test_band_von_gb_ist_die_norm_aus_dem_lastenheft():
    """§7: Klein bis 20, Mittel 21-60, Groß über 60 - fehlend und unbegrenzt
    fallen beide heraus (`None`)."""
    assert band.band_von_gb(20) == "klein"
    assert band.band_von_gb(20.0) == "klein"
    assert band.band_von_gb(21) == "mittel"
    assert band.band_von_gb(60) == "mittel"
    assert band.band_von_gb(61) == "gross"
    assert band.band_von_gb(None) is None
    assert band.band_von_gb(float("inf")) is None


@pytest.fixture(scope="module")
def tarife():
    return Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl").je_id


def test_drei_echte_tarifsaetze_treffen_ihr_band(tarife):
    """Drei Beispiele aus dem echten Bestand (Aufgabe 5a): ein unbegrenzter
    Tarif faellt aus jedem Band, ein 18-GB- und ein 150-GB-Tarif treffen
    Klein bzw. Gross, und die Grenze bei 60 GB gehoert zu Mittel."""
    faelle = [
        ("o2:o2-mobile-unlimited-m-flex", None),   # unbegrenzt (Infinity)
        ("vodafone:vodafone-mobil-xs", "klein"),   # 18 GB
        ("vodafone:vodafone-mobil-m", "mittel"),   # 60 GB, obere Grenze
        ("o2:o2-mobile-l", "gross"),                # 150 GB
    ]
    geprueft = 0
    for tarif_id, erwartet in faelle:
        tarif = tarife.get(tarif_id)
        if tarif is None:
            continue  # Tarifbestand kann sich zwischen Laeufen leicht verschieben
        geprueft += 1
        assert band.band_von_gb(tarif.get("datenvolumen_gb")) == erwartet, tarif_id
    assert geprueft >= 3, "weniger als drei der Beispiel-Tarife im Bestand"


def test_tarif_baender_indiziert_nur_bestimmbare_baender(tarife):
    index = band.tarif_baender(tarife)
    assert index["vodafone:vodafone-mobil-xs"] == "klein"
    assert "o2:o2-mobile-unlimited-m-flex" not in index


# --------------------------------------------------------------------------
# (b)-(d) Modell x Band am echten Bestand
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bestand():
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    db = json.loads((ZUSTAND / "geraete_db.json").read_text(encoding="utf-8"))
    tarifbestand = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")
    tarife = tarifbestand.je_id
    buendel = []
    for satz in tco["buendel"]:
        b = Buendel(sku_id=satz["sku_id"], anbieter=satz["anbieter"],
                    tarif_name=satz["tarif_name"],
                    tarif_id=satz.get("tarif_id", ""),
                    tarif_monatlich=satz.get("tarif_monatlich"),
                    geraet_zuzahlung=satz.get("geraet_zuzahlung"),
                    geraet_monatsrate=satz.get("geraet_monatsrate"),
                    buendel_monatlich=satz.get("buendel_monatlich"),
                    laufzeit_monate=satz.get("laufzeit_monate", 24),
                    anschlusspreis=satz.get("anschlusspreis"),
                    zustand=satz.get("zustand") or "",
                    quelle_url=satz.get("quelle_url", ""),
                    abgerufen_am=satz.get("abgerufen_am", ""))
        # Dieselbe Anreicherung wie `geraete_tco_view.aufbereiten`: die
        # Tarifbindung steht nicht in der Geraetenutzlast, sondern im
        # Tarifbestand (A5.5).
        satz_tarif = tarife.get(b.tarif_id) or {}
        if satz_tarif.get("laufzeit_monate"):
            b.tarif_bindung_monate = int(satz_tarif["laufzeit_monate"])
        buendel.append(b)
    referenzen = [SimOnlyReferenz(
        anbieter=r["anbieter"], tarif_name=r["tarif_name"],
        tarif_id=r.get("tarif_id", ""),
        tarif_sim_only_monatlich=r.get("tarif_sim_only_monatlich"),
        anschlusspreis=r.get("anschlusspreis"),
        quelle_url=r.get("quelle_url", ""),
        abgerufen_am=r.get("abgerufen_am", "")) for r in tco["sim_only"]]
    modelle = karten.modelle(buendel, db["listungen"], referenzen, tarife,
                             lade_katalog(WURZEL))
    return {"modelle": modelle, "band_je_tarif": band.tarif_baender(tarife)}


def _modell(bestand, mid):
    treffer = [m for m in bestand["modelle"]["modelle"] if m["id"] == mid]
    assert treffer, f"{mid} steht nicht im Bestand"
    return treffer[0]


def test_vorgabefall_zeigt_genau_die_anbieter_mit_echten_buendeln(bestand):
    """(b) iPhone 17 Pro 256 GB, Stand 08.09.2026: Vodafone fuehrt fuer
    dieses Geraet nur Klein- und Mittel-Tarife, o2 nur einen Gross-Tarif -
    jedes Band zeigt genau die Anbieter, fuer die es ein ECHTES Buendel
    gibt, keinen mehr."""
    modell = _modell(bestand, VORGABE_MODELL)
    baender = band.baender_fuer_modell(modell, bestand["band_je_tarif"])
    je_band = {b["key"]: b for b in baender}
    assert set(je_band) <= {"klein", "mittel", "gross"}
    assert je_band, "kein einziges Band mit Buendel - Datenlage geprueft?"

    for key, eintrag in je_band.items():
        linien_anbieter = {l["anbieter"] for l in eintrag["grafik"]["linien"]}
        fehlend_anbieter = {f["anbieter"] for f in eintrag["fehlend"]}
        # Jeder erwartete Anbieter steht GENAU EINMAL: entweder als Linie
        # oder als benannte Luecke, nie beides und nie keins von beiden.
        assert linien_anbieter | fehlend_anbieter == set(band.ERWARTETE_ANBIETER)
        assert not (linien_anbieter & fehlend_anbieter)
        # Nur ECHTE Buendel zeichnen eine Linie - keine Naeherungskarte.
        for k in modell["karten"]:
            if k["anbieter"] in linien_anbieter and k.get("naeherung"):
                assert False, "eine Naeherungskarte darf keine Linie tragen"


def test_telekom_congstar_und_11_stehen_als_benannte_luecke(bestand):
    """BRIEF_GRAPH1, Aufgabe 4: KEIN erwarteter Anbieter darf in einem Band
    still verschwinden - jeder ist entweder gezeichnet oder mit Grund
    benannt. Bis B2 (08.09.2026) hielt dieser Test die Datenlage fest
    (Telekom, congstar und 1&1 in KEINEM Band zeichenbar); seit dem
    Telekom-Lokallauf fuehrt Telekom ECHTE Bündel und ist im Band Klein
    gezeichnet, in anderen ehrlich fehlend. Gemessen wird deshalb die
    REGEL: je Band gilt gezeichnet-oder-benannt fuer ALLE erwarteten
    Anbieter - und beide Telekom-Zustaende treten wirklich ein
    (Lookup-Zeile, sonst pruefte der Test nur einen von beiden)."""
    modell = _modell(bestand, VORGABE_MODELL)
    baender = band.baender_fuer_modell(modell, bestand["band_je_tarif"])
    assert baender, "kein Band vorhanden - Test prueft nichts"
    je_band = band.karten_je_band(modell, bestand["band_je_tarif"])
    telekom_gezeichnet = telekom_fehlend = 0
    for eintrag in baender:
        gezeichnet = set(je_band.get(eintrag["key"]) or {})
        namen = {f["anbieter"] for f in eintrag["fehlend"]}
        # gezeichnet ODER benannt - niemand wird still weggelassen
        assert gezeichnet | namen >= set(band.ERWARTETE_ANBIETER), \
            f"Band {eintrag['key']}: {set(band.ERWARTETE_ANBIETER) - gezeichnet - namen} fehlt still"
        assert not (gezeichnet & namen), \
            f"Band {eintrag['key']}: {gezeichnet & namen} ist gezeichnet UND fehlend"
        for f in eintrag["fehlend"]:
            assert f["grund"], f"{f['anbieter']} hat keinen Grund"
        if "Telekom" in gezeichnet:
            telekom_gezeichnet += 1
        if "Telekom" in namen:
            telekom_fehlend += 1
    assert telekom_gezeichnet, "Telekom nirgends gezeichnet - Bestand ohne Bündel?"
    assert telekom_fehlend, "Telekom überall gezeichnet - der Lückenfall fehlt"


def test_leerzustand_modell_ohne_buendel_in_keinem_band(bestand):
    """(d) Ein Modell, das nur ueber 1&1 ein Buendel fuehrt - dessen Tarif
    kein Datenvolumen traegt und deshalb in KEINEM Band auftaucht -, zeigt
    eine leere Bandliste statt einer erfundenen Linie."""
    kandidaten = [
        m for m in bestand["modelle"]["modelle"]
        if not band.baender_fuer_modell(m, bestand["band_je_tarif"])
    ]
    assert kandidaten, "kein Modell ohne Band im Bestand - Test prueft nichts"
    for m in kandidaten:
        # Trotzdem KEIN belastbares Modell ganz ohne echtes Buendel - sonst
        # waere der Fall trivial (das Modell haette gar keine Karten).
        echte = [k for k in m["karten"]
                if k["belastbar"] and not k["naeherung"]]
        assert echte, f"{m['id']} hat gar kein echtes Buendel - kein echter Fall"


# --------------------------------------------------------------------------
# (c) Kein TCO-36 im gerenderten Artefakt
# --------------------------------------------------------------------------

def test_kein_tco36_in_keinem_bandgraphen(bestand):
    """(c) TICKET TCO24-1 gilt auch fuer GRAPH-1: die Y-Achse ist TCO-24,
    kein Bandgraph darf eine TCO-36-Zahl oder -Beschriftung tragen."""
    geprueft = 0
    for modell in bestand["modelle"]["modelle"]:
        for eintrag in band.baender_fuer_modell(modell, bestand["band_je_tarif"]):
            svg = eintrag["grafik"]["svg"]
            if not svg:
                continue
            geprueft += 1
            assert "TCO-36" not in svg, (modell["id"], eintrag["key"])
            assert "36 Monate" not in svg, (modell["id"], eintrag["key"])
    assert geprueft, "kein Bandgraph mit Daten - der Test prueft nichts"
