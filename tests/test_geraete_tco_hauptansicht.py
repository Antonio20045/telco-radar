"""Die TCO-Hauptansicht: Karten, G1, G2 - gegen den ECHTEN Bestand.

Gerechnet wird gegen `data/state/geraete_tco.json`, `geraete_db.json` und
`tarife.jsonl`, nicht gegen eine Fixture. Eine Fixture beweist, dass die
Rechnung mit sich selbst uebereinstimmt; hier soll sie mit dem Markt
uebereinstimmen.

Die drei Zusicherungen, an denen diese Ansicht haengt:
  * Jedes Modell zeigt VIER Anbieter - mit einer Zahl oder mit einem
    benannten Leerzustand (B.2.5).
  * Kein Euro-Delta ueber verschiedene Bindungsdauern (A5.4).
  * Die Grafik zeichnet nur, was in den Karten steht - sie rechnet nichts.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_grafik as grafik
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import Buendel, SimOnlyReferenz

WURZEL = pathlib.Path(__file__).resolve().parents[1]
ZUSTAND = WURZEL / "data" / "state"


@pytest.fixture(scope="module")
def bestand():
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    db = json.loads((ZUSTAND / "geraete_db.json").read_text(encoding="utf-8"))
    tarife = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl").je_id
    buendel = []
    for satz in tco["buendel"]:
        b = Buendel(sku_id=satz["sku_id"], anbieter=satz["anbieter"],
                    tarif_name=satz["tarif_name"],
                    tarif_id=satz.get("tarif_id", ""),
                    tarif_monatlich=satz.get("tarif_monatlich"),
                    geraet_zuzahlung=satz.get("geraet_zuzahlung"),
                    geraet_monatsrate=satz.get("geraet_monatsrate"),
                    laufzeit_monate=satz.get("laufzeit_monate", 24),
                    anschlusspreis=satz.get("anschlusspreis"),
                    quelle_url=satz.get("quelle_url", ""),
                    abgerufen_am=satz.get("abgerufen_am", ""))
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
    return karten.modelle(buendel, db["listungen"], referenzen, tarife,
                          lade_katalog(WURZEL))


def _modell(bestand, mid):
    treffer = [m for m in bestand["modelle"] if m["id"] == mid]
    assert treffer, f"{mid} steht nicht im Bestand"
    return treffer[0]


# --------------------------------------------------------------------------
# Die Karten
# --------------------------------------------------------------------------

def test_die_leitfrage_des_lastenhefts_ist_die_vorgabe(bestand):
    """Das Lastenheft stellt seine Frage an EINEM Geraet, und die Abnahme
    prueft daran (G3)."""
    assert bestand["vorgabe"] == "apple-iphone-17-pro-256"


def test_jedes_modell_zeigt_alle_vier_anbieter(bestand):
    """B.2.5: ein weggelassener Anbieter sieht aus wie ein Anbieter, den es
    nicht gibt."""
    assert bestand["modelle"], "der Bestand traegt kein Buendel"
    for modell in bestand["modelle"]:
        anbieter = [k["anbieter"] for k in modell["karten"]]
        for pflicht in karten.ANBIETER_REIHENFOLGE:
            assert pflicht in anbieter, f"{modell['id']}: {pflicht} fehlt"


def test_jede_karte_ohne_zahl_nennt_ihren_grund(bestand):
    leer = [k for m in bestand["modelle"] for k in m["karten"]
            if not k["belastbar"]]
    assert leer, "der Test prueft nichts, wenn es keine leere Karte gibt"
    for k in leer:
        assert k["leer_grund"].strip(), f"{k['anbieter']} ohne Begruendung"


def test_telekom_steht_ueberall_mit_ihrem_datenstand(bestand):
    """Telekom hat 0 Listungen (202-Challenge). Genau das sagt die Karte -
    und sie nennt die Phase, die es aufloest."""
    for modell in bestand["modelle"]:
        karte = [k for k in modell["karten"] if k["anbieter"] == "Telekom"][0]
        assert not karte["belastbar"]
        assert "Datenstand fehlt" in karte["leer_grund"]
        assert "Phase T" in karte["leer_grund"]


def test_die_rechenprobe_steht_auf_der_karte(bestand):
    """iPhone 17 Pro 256 GB bei o2 - dieselben Betraege wie im Rechenkern."""
    karte = [k for k in _modell(bestand, "apple-iphone-17-pro-256")["karten"]
             if k["anbieter"] == "o2"][0]
    assert karte["label"] == "TCO-36"
    assert karte["gesamt"] == 1794.76
    assert karte["schnitt_monat"] == 49.85
    assert karte["gezahlt_nach_24"] == 1356.76
    assert karte["offen_nach_24"] == 438.00
    assert karte["offene_raten"] == 12


def test_eins_und_eins_wird_nicht_in_tarif_und_geraet_zerlegt(bestand):
    """§ 13.2: der Anbieter nennt EINEN Monatsbetrag. Ihn aufzuteilen waere
    unsere Rechnung."""
    karte = [k for k in _modell(bestand, "apple-iphone-17-pro-256")["karten"]
             if k["anbieter"] == "1&1"][0]
    assert karte["buendel_monatlich"] == 44.99
    assert karte["monatlich"] is None and karte["rate"] is None
    assert [p["kategorie"] for p in karte["bestandteile"]] == ["buendel"]


def test_die_vodafone_referenz_ist_als_gerechnet_gekennzeichnet(bestand):
    modell = _modell(bestand, "apple-iphone-17-pro-256")
    karte = [k for k in modell["karten"] if k["naeherung"]][0]
    ref = modell["referenz"]
    assert karte["anbieter"] == "Vodafone"
    # Beide Summanden sind gemessen, gerechnet ist nur ihre Summe.
    assert karte["gesamt"] == round(ref["tarif_summe"] + ref["geraet_betrag"], 2)
    assert ref["tarif_quelle_url"] and ref["geraet_quelle_url"]
    assert karte["leer_grund"] == "", \
        "eine Karte mit Zahl darf keinen Leergrund tragen"


def test_die_referenz_nimmt_den_guenstigsten_belegten_vodafone_tarif(bestand):
    """Die konservative Wahl: der guenstigste eigene Tarif ist die fuer uns
    unguenstigste Referenz."""
    ref = _modell(bestand, "apple-iphone-17-pro-256")["referenz"]
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    betraege = [r["tarif_sim_only_monatlich"] for r in tco["sim_only"]
                if r["anbieter"] == "Vodafone"
                and r["tarif_sim_only_monatlich"] is not None]
    assert ref["monatlich"] == min(betraege)


def test_die_referenzkarte_traegt_ihre_eigene_bindung(bestand):
    """QA-Befund F-R2-2 (A5.1): alle 30 Referenzkarten trugen "TCO-36" und
    "Gerechnet ueber 36 Monate Bindung" - gerechnet waren 24 Tarifmonate
    plus Barkauf. Das Etikett nennt jetzt die Bindung der REFERENZ; das
    Vergleichsfenster bleibt am Referenz-Dict (`monate`, E-2)."""
    referenzen = [(m, k) for m in bestand["modelle"] for k in m["karten"]
                  if k["naeherung"]]
    assert referenzen, "keine Referenzkarte - der Test prueft nichts"
    for modell, karte in referenzen:
        ref = modell["referenz"]
        assert karte["label"] == f"TCO-{ref['tarif_monate']}"
        assert karte["laufzeit"] == karte["tarif_bindung"] == ref["tarif_monate"]
        assert karte["fenster"] == ref["monate"]
    # Der Fall tritt WIRKLICH ein: mindestens eine Referenz rechnet
    # kuerzer, als das verglichene Buendel bindet.
    assert any(k["laufzeit"] != k["fenster"] for _, k in referenzen), \
        "kein Modell mit 24 Tarifmonaten gegen 36 Monate Bindung"


def test_die_beschriftung_der_referenz_aendert_kein_delta(bestand):
    """Die Gegenprobe des Auftrags: das Euro-Delta rechnet weiter gegen das
    Fenster, nicht gegen das neue Etikett. Zwei Betraege auf den Cent,
    dazu die Regel fuer alle."""
    def delta(mid, anbieter):
        return [k["delta"] for k in _modell(bestand, mid)["karten"]
                if k["anbieter"] == anbieter and k["zustand"] == "neu"][0]
    assert delta("apple-iphone-17-pro-256", "o2")["betrag"] == -123.94
    assert delta("apple-iphone-15-128", "o2")["betrag"] == -307.95
    for modell in bestand["modelle"]:
        ref = modell["referenz"]
        if not ref or ref.get("aus_buendel"):
            continue
        for k in modell["karten"]:
            if k.get("delta"):
                assert k["delta"]["gleiche_laufzeit"] == \
                    (k["laufzeit"] == ref["monate"])
                if k["laufzeit"] == ref["monate"]:
                    assert k["delta"]["betrag"] == \
                        round(k["gesamt"] - ref["gesamt"], 2)


def test_g1_stellt_die_referenz_in_ihre_eigene_bindungsgruppe(bestand):
    """Der Gruppenkopf "36 Monate Bindung" stand ueber dem Vodafone-Balken.
    Jetzt steht der Balken unter "24 Monate Bindung"; die Referenzlinie
    bleibt in der 36er-Gruppe und sagt, woraus sie besteht."""
    svg = grafik.balken(_modell(bestand, "apple-iphone-15-128"))
    kopf24 = svg.index("24 Monate Bindung")
    kopf36 = svg.index("36 Monate Bindung")
    balken = svg.index("Vodafone <tspan")
    assert kopf24 < balken < kopf36
    linie = svg.index('class="gr-g1-ref"')
    assert linie > kopf36
    assert "Barkauf + 24 Monate Tarif" in svg
    assert svg.count("gr-g1-null") == 2


def test_das_delta_nennt_referenztarif_und_datum(bestand):
    deltas = [k["delta"] for m in bestand["modelle"] for k in m["karten"]
              if k.get("delta")]
    assert deltas, "kein einziges Delta - der Test prueft nichts"
    for d in deltas:
        assert d["referenz_tarif"] and d["referenz_datum"]
        # Euro primaer, Prozent sekundaer - aber nur bei gleicher Laufzeit.
        if d["gleiche_laufzeit"]:
            assert d["betrag"] is not None
        else:
            assert d["betrag"] is None, \
                "ueber zwei Bindungsdauern gibt es kein Euro-Delta (A5.4)"


def test_kein_delta_an_der_referenz_selbst(bestand):
    for modell in bestand["modelle"]:
        for karte in modell["karten"]:
            if karte["naeherung"]:
                assert not karte.get("delta"), \
                    "die Referenz kann nicht von sich selbst abweichen"


def test_der_effektivpreis_nennt_seinen_barpreis(bestand):
    mit_eff = [k for m in bestand["modelle"] for k in m["karten"]
               if k["eff_ohne_geraet"] is not None]
    assert mit_eff
    for k in mit_eff:
        assert k["eff_basis"]["betrag"] > 0
        assert k["eff_basis"]["quelle_url"], "ein Barpreis ohne Beleg"
        # Ein FREMDER Barpreis muss seinen Anbieter nennen - sonst stuende
        # eine Zahl von Vodafone in einer Rechnung ueber 1&1.
        if k["eff_basis"]["fremd"]:
            assert k["eff_basis"]["anbieter"]


# --------------------------------------------------------------------------
# G1
# --------------------------------------------------------------------------

def test_g1_entsteht_erst_ab_zwei_zahlen(bestand):
    """C.1: unter zwei Anbietern mit gueltiger TCO gibt es eine Texttafel,
    keine Grafik mit einem Balken."""
    einer, mehrere = 0, 0
    for modell in bestand["modelle"]:
        zahlen = sum(1 for k in modell["karten"] if k["belastbar"])
        svg = grafik.balken(modell)
        if zahlen < 2:
            assert svg == "", modell["id"]
            einer += 1
        else:
            assert svg.startswith("<svg"), modell["id"]
            mehrere += 1
    assert mehrere, "kein Modell mit zwei Zahlen - der Test prueft nichts"
    assert einer, "kein Modell mit nur einer Zahl - die Gegenprobe fehlt"


def test_g1_zeichnet_keine_karte_ohne_zahl(bestand):
    modell = _modell(bestand, "apple-iphone-17-pro-256")
    svg = grafik.balken(modell)
    assert "Telekom" not in svg, \
        "ein Balken der Laenge null mit Namen liest sich als kostenlos"
    for anbieter in ("o2", "1&amp;1", "Vodafone"):
        assert anbieter in svg


def test_g1_trennt_die_laufzeiten_mit_eigener_nulllinie():
    """A5.4 - der Fall existiert im Bestand heute nicht (alle Buendel binden
    36 Monate), deshalb wird er hier gestellt. Ohne diesen Test faellt die
    Trennung beim ersten 24-Monats-Angebot lautlos aus."""
    def karte(anbieter, laufzeit, gesamt):
        return {"anbieter": anbieter, "tarif": f"Tarif {laufzeit}",
                "belastbar": True, "gesamt": gesamt, "laufzeit": laufzeit,
                "naeherung": False, "boni": [],
                "bestandteile": [{"name": "Tarif", "betrag": gesamt,
                                  "kategorie": "tarif"}]}
    modell = {"name": "Testgerät", "referenz": None,
              "karten": [karte("o2", 36, 1800.0), karte("Telekom", 24, 1200.0)]}
    svg = grafik.balken(modell)
    assert svg.count("gr-g1-null") == 2, "je Laufzeitgruppe eine Nulllinie"
    assert "24 Monate Bindung" in svg and "36 Monate Bindung" in svg


def test_jeder_balken_traegt_seine_aussage_als_text(bestand):
    """Eine Grafik ohne Textfassung ist auf einem Screenreader leer."""
    svg = grafik.balken(_modell(bestand, "apple-iphone-17-pro-256"))
    assert svg.count("<title>") >= 1
    assert 'role="img"' in svg and "aria-label=" in svg


def test_die_grafik_rechnet_keine_eigene_zahl(bestand):
    """Der Betrag am Balkenende ist der der Karte - Zeichen fuer Zeichen."""
    modell = _modell(bestand, "apple-iphone-17-pro-256")
    svg = grafik.balken(modell)
    for karte in modell["karten"]:
        if karte["belastbar"]:
            assert grafik.euro(karte["gesamt"]) in svg, karte["anbieter"]


def test_ein_bonus_verkuerzt_den_balken_statt_ihn_zu_verlaengern():
    """Der Bonus ist ein NEGATIVES Segment (C.1). Am Balkenende steht die
    Leitzahl, nicht die Summe vor Abzug."""
    def karte(name, gesamt, boni):
        posten = [{"name": "Tarif", "betrag": gesamt + sum(
            b["betrag"] for b in boni), "kategorie": "tarif"}]
        posten += [{"name": f"Bonus · {b['name']}", "betrag": -b["betrag"],
                    "kategorie": "bonus"} for b in boni]
        return {"anbieter": name, "tarif": "T", "belastbar": True,
                "gesamt": gesamt, "laufzeit": 24, "naeherung": False,
                "boni": boni, "bestandteile": posten}
    modell = {"name": "X", "referenz": None,
              "karten": [karte("o2", 950.0, [{"name": "Wechselbonus",
                                              "betrag": 50.0}]),
                         karte("1&1", 1000.0, [])]}
    svg = grafik.balken(modell)
    assert "gr-g1-bonus" in svg
    assert grafik.euro(950.0) in svg


# --------------------------------------------------------------------------
# G2
# --------------------------------------------------------------------------

def test_g2_zeichnet_nur_reihen_mit_zwei_messpunkten():
    reihen = [
        {"name": "A", "anbieter": "o2", "quelle_url": "https://example.invalid",
         "punkte": [{"datum": "2026-08-29", "betrag": 500.0},
                    {"datum": "2026-09-03", "betrag": 450.0}]},
        {"name": "B", "anbieter": "congstar", "quelle_url": "",
         "punkte": [{"datum": "2026-09-03", "betrag": 800.0}]},
    ]
    ergebnis = grafik.historie(reihen)
    assert ergebnis["reihen"] == 1
    assert [t["name"] for t in ergebnis["tabelle"]] == ["A"]
    assert ergebnis["ereignisse"][0]["delta"] == -50.0
    assert ergebnis["ereignisse"][0]["richtung"] == "runter"
    assert "↓" in ergebnis["svg"]


def test_g2_bleibt_ohne_zwei_messpunkte_leer():
    """C.2: keine interpolierte Scheinkurve."""
    ergebnis = grafik.historie([
        {"name": "A", "anbieter": "o2", "punkte": [
            {"datum": "2026-09-03", "betrag": 800.0}]}])
    assert ergebnis["svg"] == "" and ergebnis["tabelle"] == []


def test_g2_traegt_jede_zahl_auch_als_tabelle():
    """C.2 verlangt die Tabelle unter der Grafik - auf dem Telefon rollt
    keine Legende, und ein Screenreader liest keine Linie."""
    reihen = [{"name": "A", "anbieter": "o2", "quelle_url": "https://x.invalid",
               "punkte": [{"datum": "2026-08-29", "betrag": 500.0},
                          {"datum": "2026-09-03", "betrag": 550.0}]}]
    ergebnis = grafik.historie(reihen)
    zeile = ergebnis["tabelle"][0]
    assert zeile["von"] == 500.0 and zeile["bis"] == 550.0
    assert zeile["delta"] == 50.0
    assert len(zeile["punkte"]) == 2
    assert "↑" in ergebnis["svg"]


def _reihe(name, *betraege, anbieter="o2"):
    """Eine G2-Reihe mit einem Messtag je Betrag, ab dem 29.08.2026."""
    return {"name": name, "anbieter": anbieter,
            "quelle_url": f"https://x.invalid/{name}",
            "punkte": [{"datum": f"2026-08-{29 + i:02d}" if i < 3
                        else f"2026-09-{i - 2:02d}", "betrag": float(b)}
                       for i, b in enumerate(betraege)]}


def test_g2_zeichnet_bewegte_reihen_vor_flachen():
    """QA-Befund F-R2-1: bei Gleichstand in der Punktzahl brach das
    ALPHABET - fuenf flache "Galaxy"-Linien standen im Bild, der groesste
    Preissprung des Bestands (Pixel 10 Pro, +180 EUR) nicht. Sieben Reihen
    mit je zwei Punkten, nur die zwei alphabetisch LETZTEN bewegen sich:
    beide werden gezeichnet, die groessere Bewegung zuerst."""
    reihen = [_reihe(n, 500, 500) for n in ("A", "B", "C", "D", "E")]
    reihen += [_reihe("Y", 343, 379), _reihe("Z", 793, 973)]
    ergebnis = grafik.historie(reihen)
    namen = [z["name"] for z in ergebnis["tabelle"]]
    assert ergebnis["reihen"] == grafik.MAX_REIHEN
    assert ergebnis["reihen_gesamt"] == 7 and ergebnis["bewegt"] == 2
    assert namen[:2] == ["Z", "Y"], namen
    # Der Gegenfall stellt sich WIRKLICH: alphabetisch laegen Z und Y
    # hinter dem Deckel.
    assert sorted(r["name"] for r in reihen)[:grafik.MAX_REIHEN] == \
        ["A", "B", "C", "D", "E"]
    # Keine flache Reihe verdraengt eine bewegte.
    ungezeichnet = {r["name"] for r in reihen} - set(namen)
    assert all(r["punkte"][0]["betrag"] == r["punkte"][-1]["betrag"]
               for r in reihen if r["name"] in ungezeichnet)


def test_g2_nennt_die_ereignisse_der_grundmenge():
    """Der Satz "Erhoehungen und Senkungen im Messzeitraum" ist ein Satz
    ueber den Bestand, nicht ueber die fuenf gezeichneten Reihen. Sieben
    bewegte Reihen: gezeichnet fuenf, benannt alle sieben - und die Marker
    im Bild sind genau die Ereignisse der gezeichneten Reihen."""
    reihen = [_reihe(f"R{i}", 500, 500 + 10 * (i + 1)) for i in range(7)]
    ergebnis = grafik.historie(reihen)
    assert ergebnis["reihen"] == 5 and ergebnis["reihen_gesamt"] == 7
    assert len(ergebnis["ereignisse"]) == 7 and ergebnis["bewegt"] == 7
    gezeichnet = {z["name"] for z in ergebnis["tabelle"]}
    # Die zwei kleinsten Bewegungen fallen unter den Deckel ...
    assert {"R0", "R1"}.isdisjoint(gezeichnet)
    # ... und stehen trotzdem im Fliesstext.
    assert {e["name"] for e in ergebnis["ereignisse"]} >= {"R0", "R1"}
    marker = ergebnis["svg"].count("gr-g2-marker")
    assert marker == sum(1 for e in ergebnis["ereignisse"]
                         if e["name"] in gezeichnet) == 5


def test_g2_rangfolge_haelt_am_echten_bestand():
    """Am Bestand von heute: keine gezeichnete flache Reihe, solange eine
    bewegte ungezeichnet ist, und jedes Ereignis der Grundmenge steht im
    Fliesstext. Die Regel, nicht die Namen - der Bestand wandert jede
    Nacht."""
    from telco_radar.analyze.geraete_store import Preishistorie
    pfad = ZUSTAND / "geraete_preise.jsonl"
    if not pfad.exists():
        pytest.skip("keine Preishistorie im Checkout")
    db = json.loads((ZUSTAND / "geraete_db.json").read_text(encoding="utf-8"))
    reihen = karten.historienreihen(db["listungen"], Preishistorie(pfad),
                                    lade_katalog(WURZEL))
    ergebnis = grafik.historie(reihen)
    if ergebnis["reihen_gesamt"] <= ergebnis["reihen"]:
        pytest.skip("der Deckel greift heute nicht - nichts zu verdraengen")
    grundmenge = [r for r in reihen if len(r["punkte"]) >= grafik.MIND_PUNKTE]
    assert len(ergebnis["ereignisse"]) == \
        sum(len(grafik._ereignisse(r)) for r in grundmenge)
    gezeichnet = {(z["name"], z["anbieter"]) for z in ergebnis["tabelle"]}
    bewegt_ungezeichnet = [r for r in grundmenge if grafik._ereignisse(r)
                           and (r["name"], r["anbieter"]) not in gezeichnet]
    if bewegt_ungezeichnet:
        assert all(z["delta"] != 0 or any(
            e["name"] == z["name"] and e["anbieter"] == z["anbieter"]
            for e in ergebnis["ereignisse"]) for z in ergebnis["tabelle"])


def test_die_x_achse_traegt_ein_wochenraster():
    """C.2: Wochenraster kurzfristig, Monatsraster ab drei Monaten."""
    kurz = grafik.historie([{"name": "A", "anbieter": "o2", "punkte": [
        {"datum": "2026-07-01", "betrag": 500.0},
        {"datum": "2026-07-29", "betrag": 520.0}]}])
    lang = grafik.historie([{"name": "A", "anbieter": "o2", "punkte": [
        {"datum": "2026-01-01", "betrag": 500.0},
        {"datum": "2026-09-01", "betrag": 520.0}]}])
    assert kurz["svg"].count("gr-g2-raster--x") == 5      # 28 Tage / 7
    assert lang["svg"].count("gr-g2-raster--x") == 9      # 243 Tage / 30


def test_die_anbieterfarbe_traegt_denselben_slug_ueberall(bestand):
    """C.3: eine Anbieterfarbe, konsistent ueber alle Grafiken und Karten."""
    karte = [k for k in _modell(bestand, "apple-iphone-17-pro-256")["karten"]
             if k["anbieter"] == "1&1"][0]
    assert karte["slug"] == grafik.anbieter_slug("1&1") == "1-1"
    reihen = [{"name": "A", "anbieter": "1&1", "punkte": [
        {"datum": "2026-08-29", "betrag": 500.0},
        {"datum": "2026-09-03", "betrag": 450.0}]}]
    assert "gr-anb--1-1" in grafik.historie(reihen)["svg"]


def test_ein_eigenes_buendel_verdraengt_die_naeherung():
    """Vodafone steht je Modell EINMAL - als Angebot oder als Rechnung.

    Der Fall gibt es im Bestand vom 04.09.2026 nicht (Vodafone fuehrt 151
    Listungen, alle mit Barpreis, keine mit Tarifbezug), er entsteht mit
    dem ersten Vodafone-Buendeladapter. Ohne diesen Test stuenden dann zwei
    Vodafone-Karten nebeneinander, und der Leser muesste raten, welche
    "unser Preis" ist.
    """
    buendel = [Buendel(sku_id="sku-1", anbieter="Vodafone",
                       tarif_name="Vodafone Mobil M", tarif_id="vf:m",
                       tarif_monatlich=49.95, tarif_bindung_monate=24,
                       geraet_zuzahlung=1.0, geraet_monatsrate=20.0,
                       laufzeit_monate=24, anschlusspreis=39.99,
                       quelle_url="https://vodafone.invalid/x"),
               Buendel(sku_id="sku-1", anbieter="o2", tarif_name="O2 L",
                       tarif_id="o2:l", tarif_monatlich=24.99,
                       tarif_bindung_monate=24, geraet_zuzahlung=1.0,
                       geraet_monatsrate=25.0, laufzeit_monate=24,
                       anschlusspreis=0.0,
                       quelle_url="https://o2.invalid/x")]
    listungen = [{"id": "vodafone--sku-1", "sku_id": "sku-1",
                  "device_id": "apple-iphone-17-pro", "anbieter": "Vodafone",
                  "speicher_gb": 256, "zustand": "neu", "status": "aktiv",
                  "preis_ohne_vertrag": 1199.90,
                  "quelle_url": "https://vodafone.invalid/p",
                  "abgerufen_am": "2026-09-04"},
                 # Seit dem 04.09.2026 (B1) gilt ein Buendel ohne belegten
                 # Zustand als "unbekannt" und steht ausserhalb des
                 # Vergleichs - ein Delta bekommt nur ein belegtes
                 # Neugeraet. Die o2-Listung derselben SKU belegt ihn.
                 {"id": "o2--sku-1", "sku_id": "sku-1",
                  "device_id": "apple-iphone-17-pro", "anbieter": "o2",
                  "speicher_gb": 256, "zustand": "neu", "status": "aktiv",
                  "preis_ohne_vertrag": 1149.00,
                  "quelle_url": "https://o2.invalid/p",
                  "abgerufen_am": "2026-09-04"}]
    referenzen = [SimOnlyReferenz(anbieter="Vodafone",
                                  tarif_name="Vodafone Mobil XS",
                                  tarif_id="vf:xs",
                                  tarif_sim_only_monatlich=29.95,
                                  quelle_url="https://vodafone.invalid/pib",
                                  abgerufen_am="2026-09-04")]
    ergebnis = karten.modelle(buendel, listungen, referenzen, {},
                              lade_katalog(WURZEL))
    modell = ergebnis["modelle"][0]
    vodafone = [k for k in modell["karten"] if k["anbieter"] == "Vodafone"]
    assert len(vodafone) == 1, "Vodafone steht je Modell genau einmal"
    assert not vodafone[0]["naeherung"], "das eigene Buendel schlaegt die Rechnung"
    assert modell["referenz"]["gesamt"] == vodafone[0]["gesamt"]
    # Und das Delta des Wettbewerbers rechnet gegen genau diese Zahl.
    o2 = [k for k in modell["karten"] if k["anbieter"] == "o2"][0]
    assert o2["delta"]["betrag"] == round(o2["gesamt"] - vodafone[0]["gesamt"], 2)
