"""O1 (STRATEGIE_GERAETE_OPTIK, 11.09.2026): der EINE Balkengraph.

"TCO-24 je Anbieter" für das gewählte Modell × Band - sortierte horizontale
Balken, der Wert GEDRUCKT (Cent genau, deutsch), Δ zur Vodafone-Referenz als
"−466,80 € · −29,9 %", Vodafone als Emphasis mit dem Wort "Referenz" statt
eines Δ. Diese Datei prüft die DATENSEITE (`geraete_tco_band.balken` und
`geraete_tco_view.aufbereiten`); die Falz, der Selektor und die details-Zahl
misst `tests/test_geraete_o1_hauptgraph_browser.py` im echten Chromium.

DIE DREI REGELN, DIE HIER PRUEFBAR SIND
---------------------------------------
1. GERECHNET WIRD NUR IN `tco_model`. Der Balken liest `gesamt` aus den
   Karten, die `tco_24()` schon gerechnet hat - dieses Modul addiert keinen
   Euro. Δ ist Differenzbildung gegen die günstigste echte Vodafone-Karte
   DESSELBEN BANDES (der Entwurf: "Δ = Abstand zum günstigsten
   Vodafone-Bündel im selben Band"), keine zweite TCO.
2. NUR ECHTE, NEUE Bündel tragen Zeilen. Die Näherungskarte ist kein
   Angebot (Modulkopf `geraete_tco_band`, Regel 2), ein erneuertes Gerät
   ist eine andere Preisdimension (QA-Befund B1) - beides steht in der
   EINEN Legendenzeile, nicht im Graphen.
3. KEINE ZWEITE FORMATIERUNG. `gesamt_text` und `delta_text` entstehen an
   EINER Stelle in Python - `app.js` setzt sie nur, der Browser-Test hält
   Server-Render und JS-Render gegen denselben JSON-Knoten zusammen.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_band as bandmod
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import Buendel, SimOnlyReferenz

WURZEL = pathlib.Path(__file__).resolve().parents[1]
ZUSTAND = WURZEL / "data" / "state"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bestand():
    """Der ECHTE Bestand aus data/state - dieselbe Quelle wie die Seite."""
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    db = json.loads((ZUSTAND / "geraete_db.json").read_text(encoding="utf-8"))
    tarife = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl").je_id
    buendel = [Buendel(
        sku_id=s["sku_id"], anbieter=s["anbieter"],
        tarif_name=s["tarif_name"], tarif_id=s.get("tarif_id", ""),
        tarif_monatlich=s.get("tarif_monatlich"),
        buendel_monatlich=s.get("buendel_monatlich"),
        geraet_zuzahlung=s.get("geraet_zuzahlung"),
        geraet_monatsrate=s.get("geraet_monatsrate"),
        laufzeit_monate=s.get("laufzeit_monate", 24),
        anschlusspreis=s.get("anschlusspreis"),
        zustand=s.get("zustand") or "",
        quelle_url=s.get("quelle_url", ""),
        abgerufen_am=s.get("abgerufen_am", "")) for s in tco["buendel"]]
    referenzen = [SimOnlyReferenz(
        anbieter=r["anbieter"], tarif_name=r["tarif_name"],
        tarif_id=r.get("tarif_id", ""),
        tarif_sim_only_monatlich=r.get("tarif_sim_only_monatlich"),
        anschlusspreis=r.get("anschlusspreis"),
        quelle_url=r.get("quelle_url", ""),
        abgerufen_am=r.get("abgerufen_am", "")) for r in tco["sim_only"]]
    return karten.modelle(buendel, db["listungen"], referenzen, tarife,
                          lade_katalog(WURZEL))


def _baender(modell, tarife):
    gb = {tid: (satz or {}).get("datenvolumen_gb")
          for tid, satz in tarife.items()}
    return bandmod.baender_fuer_modell(modell, bandmod.tarif_baender(tarife),
                                       gb)


def _balken(modell, tarife, key="klein"):
    for b in _baender(modell, tarife):
        if b["key"] == key:
            return b["balken"]
    pytest.fail(f"Band {key} fehlt - der Graph hat nichts zu prüfen")


def _mit_zwei_anbietern(bestand):
    """Ein Band mit mindestens zwei Zeilen - sonst misst der Test nur eine
    Karte statt einer Ordnung."""
    tarife = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl").je_id
    for modell in bestand["modelle"]:
        for band in _baender(modell, tarife):
            zeilen = band["balken"]["zeilen"]
            if len(zeilen) >= 2:
                return modell, tarife, band
    pytest.fail("kein Modell×Band mit zwei Zeilen im Bestand")


# --------------------------------------------------------------------------
# Regel 1: Ordnung, Breite, Δ - gegen den echten Bestand
# --------------------------------------------------------------------------

def test_die_zeilen_stehen_nach_gesamtkosten_sortiert(bestand):
    """Der günstigste Anbieter zuerst (O1-Auftrag: "sortierte horizontale
    Balken (günstigster zuerst)"). Die alte Band-Werteliste ordnete den
    EIGENEN Anbieter vor - im Balken führt der Preis."""
    modell, tarife, band = _mit_zwei_anbietern(bestand)
    zeilen = band["balken"]["zeilen"]
    betraege = [z["gesamt"] for z in zeilen]
    assert betraege == sorted(betraege), \
        f"{modell['titel']} / {band['key']}: {betraege}"


def test_der_laengste_balken_ist_hundert_prozent(bestand):
    """Breite proportional zum Wert, längster Balken = 100 % - der Maßstab
    einer Balkengrafik ist ihre größte Zeile."""
    modell, tarife, band = _mit_zwei_anbietern(bestand)
    zeilen = band["balken"]["zeilen"]
    assert max(z["breite"] for z in zeilen) == 100.0
    teuerster = max(zeilen, key=lambda z: z["gesamt"])
    guenstigste = min(zeilen, key=lambda z: z["gesamt"])
    assert guenstigste["breite"] < teuerster["breite"]
    # Proportionalität: breite/gesamt weicht um weniger als einen Prozentpunkt
    # ab (Rundung auf eine Dezimalstelle).
    bezug = 100.0 / max(z["gesamt"] for z in zeilen)
    for z in zeilen:
        assert abs(z["breite"] - z["gesamt"] * bezug) < 0.1


def test_genau_eine_referenzzeile_und_deltas_dagegen(bestand):
    """Vodafone trägt als ECHTES Bündel die Emphasis-Zeile ("Referenz",
    kein Δ); jede andere Zeile trägt Δ gegen genau diese Zahl. Gibt es kein
    echtes Vodafone-Bündel im Band, gibt es auch kein Δ - der Entwurf sagt
    das im Band Groß wörtlich ("keine Δ-Angabe"), und die Näherung bleibt
    der Massstab der Karten, keine Zeile des Graphen."""
    modell, tarife, band = _mit_zwei_anbietern(bestand)
    balken = band["balken"]
    referenz = [z for z in balken["zeilen"] if z["referenz"]]
    assert len(referenz) == bool(balken["referenz_da"]), \
        "referenz_da und die Zahl der Referenzzeilen fallen auseinander"
    if not balken["referenz_da"]:
        assert all(z["delta_text"] is None for z in balken["zeilen"])
        assert "keine Δ-Angabe" in band["unterzeile"]
        return
    ref = referenz[0]
    assert ref["eigen"], "die Referenzzeile ist nicht die eigene"
    assert ref["delta_text"] is None, "die Referenz trägt kein Δ gegen sich"
    for z in balken["zeilen"]:
        if z is ref:
            continue
        assert z["delta_euro"] == round(z["gesamt"] - ref["gesamt"], 2)
        assert z["delta_prozent"] == round(
            abs(z["delta_euro"]) / ref["gesamt"] * 100, 1)


def test_die_delta_texte_sind_deutsch_und_vorzeichenbehaftet(bestand):
    """"−466,80 € · −29,9 %" - echtes Minus (U+2212), deutsches Komma,
    Prozent mit einer Nachkommastelle. Diese Strings entstehen EINMAL hier
    in Python; app.js und Vorlage setzen sie nur."""
    modell, tarife, band = _mit_zwei_anbietern(bestand)
    for z in band["balken"]["zeilen"]:
        if z["delta_text"] is None:
            continue
        assert z["delta_text"].startswith(("−", "+")), z["delta_text"]
        assert " € · " in z["delta_text"], z["delta_text"]
        assert "%)" in z["delta_text"], z["delta_text"]
        assert "," in z["delta_text"], z["delta_text"]
        vorzeichen = "−" if z["delta_euro"] < 0 else "+"
        assert z["delta_text"].startswith(vorzeichen)


def test_die_werte_sind_cent_genau_gedruckt(bestand):
    modell, tarife, band = _mit_zwei_anbietern(bestand)
    for z in band["balken"]["zeilen"]:
        assert z["gesamt_text"].endswith(" €")
        # Zwei Nachkommastellen, Tausenderpunkt - das `euro`-Format des
        # Portals, nicht eine zweite Beschriftung.
        assert z["gesamt_text"] == f"{z['gesamt']:,.2f}".replace(
            ",", "#").replace(".", ",").replace("#", ".") + " €"


# --------------------------------------------------------------------------
# Regel 2: keine Näherung, kein erneuertes Gerät als Zeile
# --------------------------------------------------------------------------

def test_naeherung_und_erneuerte_stehen_nie_als_zeile(bestand):
    tarife = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl").je_id
    for modell in bestand["modelle"]:
        for band in _baender(modell, tarife):
            for z in band["balken"]["zeilen"]:
                assert not z.get("naeherung"), \
                    "die Referenzrechnung steht als Anbieter-Zeile im Graph"
                assert not z["zustand_etikett"], \
                    f"{z['anbieter']}: erneuertes Gerät trägt die Anbieter-Zeile"


def test_die_luecke_nennt_namen_ohne_einzelsaetze():
    """EINE Zeile, nur Namen. Die 145 "führt kein Bündel in diesem Band"-
    Einzelsätze der alten Band-Panels entfallen mit dem Graph - ein Name
    pro fehlendem Anbieter, gruppiert nach Grund."""
    buendel = [
        # Ein echtes o2-Bündel im Band Klein und ein ERNEUERTES Telekom-
        # Bündel im selben Band: o2 trägt die Zeile, Telekom steht als
        # "nur erneuert" in der Lücke, 1&1 und Vodafone als "kein Bündel".
        Buendel(sku_id="apple-iphone-17-pro-256gb-schwarz", anbieter="o2",
                tarif_name="O2 Klein", tarif_id="o2:klein",
                tarif_monatlich=20.0, geraet_zuzahlung=1.0,
                geraet_monatsrate=20.0, laufzeit_monate=24,
                anschlusspreis=0.0, zustand="neu",
                quelle_url="https://o2.invalid/x",
                abgerufen_am="2026-09-11"),
        Buendel(sku_id="apple-iphone-17-pro-256gb-schwarz", anbieter="Telekom",
                tarif_name="TK Klein", tarif_id="tk:klein",
                tarif_monatlich=20.0, geraet_zuzahlung=1.0,
                geraet_monatsrate=10.0, laufzeit_monate=24,
                anschlusspreis=0.0, zustand="refurbished",
                quelle_url="https://tk.invalid/x",
                abgerufen_am="2026-09-11"),
    ]
    listungen = [
        {"id": "o2--s", "sku_id": "apple-iphone-17-pro-256gb-schwarz",
         "device_id": "apple-iphone-17-pro", "anbieter": "o2",
         "speicher_gb": 256, "zustand": "neu", "status": "aktiv",
         "preis_ohne_vertrag": None, "quelle_url": "",
         "abgerufen_am": ""},
    ]
    tarife = {
        "o2:klein": {"datenvolumen_gb": 10},
        "tk:klein": {"datenvolumen_gb": 15},
    }
    modell = karten.modelle(buendel, listungen, [], tarife,
                            lade_katalog(WURZEL))["modelle"][0]
    balken = _baender(modell, tarife)[0]["balken"]
    assert [z["anbieter"] for z in balken["zeilen"]] == ["o2"]
    assert balken["luecke"]["nur_erneuert"] == ["Telekom"]
    assert sorted(balken["luecke"]["kein_buendel"]) == ["1&1", "Vodafone"]


# --------------------------------------------------------------------------
# Der JSON-Knoten für den Selektor: alle Modelle, dieselben Zahlen
# --------------------------------------------------------------------------

def _aufbereitung():
    """Die volle Aufbereitung gegen den echten Bestand - so, wie sie
    `render_site` aufruft."""
    from telco_radar.report import geraete_tco_view
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    db = json.loads((ZUSTAND / "geraete_db.json").read_text(encoding="utf-8"))
    tarife = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl").je_id
    return geraete_tco_view.aufbereiten(
        tco["buendel"], tco["sim_only"], db["listungen"],
        lade_katalog(WURZEL), tarife=tarife)


def test_der_graph_knoten_traegt_alle_modelle():
    """DER SELEKTOR IST FÜR ALLE GERÄTE FUNKTIONAL (O1-Auftrag Punkt 2) -
    deshalb muss der JSON-Knoten jedes Modell mit allen Bändern tragen.
    Die Zuordnung wird nachgezählt (CLAUDE.md § 6: ein Lookup, das ins
    Leere geht, ist grün und prüft nichts)."""
    daten = _aufbereitung()
    knoten = daten["graph_daten"]
    ids_seite = [m["id"] for m in daten["modelle"]]
    ids_knoten = [m["id"] for m in knoten["modelle"]]
    assert len(ids_knoten) == len(ids_seite)
    assert sorted(ids_knoten) == sorted(ids_seite)
    assert knoten["vorgabe"] == daten["modell_vorgabe"]
    assert knoten["gesamt"] == daten["modelle_gesamt"]


def test_der_graph_knoten_traegt_dieselben_zahlen_wie_die_balken():
    """KEINE ZWEITE RECHNUNG: was der Server für das Vorgabemodell rendert
    und was app.js für jedes andere Modell baut, kommt aus DEMSELBEN
    `balken`-Feld - der Knoten serialisiert es nur."""
    daten = _aufbereitung()
    knoten = dict((m["id"], m) for m in daten["graph_daten"]["modelle"])
    tarife = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl").je_id
    geprueft = 0
    for modell in daten["modelle"]:
        for band in _baender(modell, tarife):
            im_knoten = knoten[modell["id"]]["baender"][band["key"]]
            assert im_knoten["zeilen"] == band["balken"]["zeilen"]
            geprueft += 1
    assert geprueft >= 100, \
        f"nur {geprueft} Modell×Band-Paare geprüft - der Bestand hat mehr"


def test_der_stand_der_fussnote_ist_der_der_buendel():
    """„Stand {Datum}" der EINEN Fußnote ist der späteste Bündel-Abruf -
    nicht der Berichtstag (derselbe Fehler wie das Kopfdatum am 30.08.)."""
    daten = _aufbereitung()
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    erwartet = max((b.get("abgerufen_am") or "" for b in tco["buendel"]),
                   default="")
    assert daten["graph_daten"]["stand"] == erwartet
