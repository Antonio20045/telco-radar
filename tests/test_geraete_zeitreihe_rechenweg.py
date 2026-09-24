"""P1 (STRATEGIE_GERAETE_V3, 17.09.2026): der RECHENWEG JE MESSUNG,
serverseitig - `report/geraete_zeitreihe.py`.

Antonios Forderung 2: Klick auf den Preis zeigt die Erklärung, WIE der
Preis zustande kommt - dynamisch je Messung („morgen ist das der Preis,
dann steht da 70 Euro mal 24"). Diese Tests messen die serverseitige
Hälfte (Variante V1 aus vergleich.md):

  - je Messung eine POSTENLISTE (Zuzahlung, Anschlusspreis, Tarif ×
    Monate, Rate × Monate = gesamt) - die HEUTIGE Rechnung (A1: alle
    Raten der eigenen Laufzeit, Tarif phasengewichtet ueber den
    Tarifbestand), nicht das eingefrorene `gesamt` der Historie;
  - je Serie/Messung ein `<template data-m=...>` unter dem SVG, inklusive
    `data-anb`/`data-m` an den Kreisen und eine unsichtbare Trefferfläche
    (`gr-zr-hit`, r=12 - NICHT `gr-zr-treffer`, die Klasse gehört der
    Suchvorschau);
  - Vodafone-Näherung: benannter Leerzustand, kein erfundener Posten.

Die beiden ECHTEN Beispielzeilen unten sind aus
`data/state/geraede_tco_historie.jsonl` kopiert (12.09.2026) - dieselben,
an denen vergleich.md die Summe nachgerechnet hat.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_zeitreihe as zr
from telco_radar.tco_model import tco_24
from telco_radar.report.html import render_site

from test_geraete_zeitreihe_ansicht import HEUTE, _baue

WURZEL = pathlib.Path(__file__).resolve().parents[1]

# Die o2-Zeile des Bestands (12.09.2026, samsung-galaxy-s23): die Rechnung
# aus vergleich.md - 37 + 39,99 + 24 × 14,99 + 24 × 19,00 = 892,75 - mit
# gekappter Rate (24 von 36). Wörtlich aus der Historie kopiert.
O2_MESSUNG = {"id": "buendel--o2--samsung-galaxy-s23-128gb-rosa--o2-mobile-on-demand-m-plus-mit-50-gb-24-mon",
              "datum": "2026-09-12",
              "tarif_id": "o2:o2-mobile-on-demand-m",
              "tarif_id_guete": "hoch", "tarif_monatlich": 14.99,
              "tarif_bindung_monate": None, "buendel_monatlich": None,
              "geraet_zuzahlung": 37.0, "geraet_monatsrate": 19.0,
              "laufzeit_monate": 36, "anschlusspreis": 39.99,
              "quelle_url": "https://www.o2online.de/e-shop/samsung/s23",
              "abgerufen_am": "2026-09-12", "zustand": "neu",
              "gesamt": 892.75}

# Die 1&1-Zeile desselben Messtags: die ZUSAMMEN-Form (ein Bündelmonats-
# preis, § 13.2) - 420 + 39,90 + 24 × 49,99 = 1.659,66.
EINS_EINS_MESSUNG = {"id": "buendel--1-1--apple-iphone-17-pro-max-256gb-silber--1-1-all-net-flat-s",
                     "datum": "2026-09-12",
                     "tarif_id": "11:1-1-all-net-flat-s",
                     "tarif_id_guete": "hoch", "tarif_monatlich": None,
                     "tarif_bindung_monate": None,
                     "buendel_monatlich": 49.99,
                     "geraet_zuzahlung": 420.0, "geraet_monatsrate": None,
                     "laufzeit_monate": 36, "anschlusspreis": 39.9,
                     "quelle_url": "https://mobile.1und1.de/iphone-17-pro-max",
                     "abgerufen_am": "2026-09-12", "zustand": "neu",
                     "gesamt": 1659.66}


def _messung(satz, *, anbieter="o2", tarif="O2 Mobile on Demand M Plus"):
    stand = {"id": satz["id"], "sku_id": "samsung-galaxy-s23-128gb-rosa",
             "anbieter": anbieter, "tarif_name": tarif}
    return {"satz": dict(satz), "stand": stand}


# --------------------------------------------------------------------------
# Die Postenliste - nachgebaut aus der Zeile, Summe == eingefrorene Zahl
# --------------------------------------------------------------------------

def test_die_posten_der_o2_messung_ergeben_die_heutige_summe():
    """A1: das Panel zerlegt die HEUTIGE Rechnung - alle 36 Raten -
    und geht mit ihr auf (37 + 39,99 + 24 × 14,99 + 36 × 19,00)."""
    r = zr._rechung(_messung(O2_MESSUNG))
    assert r is not None
    assert round(sum(p["betrag"] for p in r["posten"]), 2) == 1120.75
    assert r["gesamt"] == 1120.75
    # Gegenprobe: die eingefrorene 892,75 der Kappungsformel ist es NICHT.
    assert r["gesamt"] != O2_MESSUNG["gesamt"]


def test_die_posten_stehen_in_der_reihenfolge_der_aufgabe():
    r = zr._rechung(_messung(O2_MESSUNG))
    assert [p["label"] for p in r["posten"]] == \
        ["Gerätezuzahlung", "Anschlusspreis", "Tarif", "Geräterate"]


def test_die_rate_zaehlt_alle_laufzeitmonate():
    """A1: 36 Raten laufen, gerechnet werden ALLE 36 - die Laufzeit steht
    im Faktor (36 × 19,00 = 684,00), die Kappungsklammer ist gefallen."""
    r = zr._rechung(_messung(O2_MESSUNG))
    rate = next(p for p in r["posten"] if p["label"] == "Geräterate")
    assert rate["anzahl"] == 36 and rate["einzeln"] == 19.0
    assert rate["betrag"] == 684.0
    assert rate["klammer"] == ""


def test_die_zusammenform_hat_einen_buendelposten_und_erfindet_keine_teile():
    """1&1 nennt EINEN Monatsbetrag für Tarif und Gerät - ihn in zwei
    Hälften zu zerlegen wäre unsere Rechnung (§ 13.2). Der Posten heißt
    Bündelpreis; Tarif und Geräterate erscheinen NICHT. A1: alle 36
    Laufzeitmonate zaehlen (36 × 49,99 = 1.799,64)."""
    r = zr._rechung(_messung(EINS_EINS_MESSUNG, anbieter="1&1",
                             tarif="1&1 All-Net-Flat S"))
    assert round(sum(p["betrag"] for p in r["posten"]), 2) == 2259.54
    labels = [p["label"] for p in r["posten"]]
    assert labels == ["Gerätezuzahlung", "Anschlusspreis",
                      "Bündelpreis (Tarif und Gerät zusammen)"]
    buendel = r["posten"][2]
    assert buendel["anzahl"] == 36 and buendel["einzeln"] == 49.99
    assert buendel["betrag"] == round(36 * 49.99, 2)
    assert buendel["klammer"] == ""


def test_kein_anschlusspreis_ist_eine_luecke_und_null_null_ein_betrag():
    """Hausregel aus tco_model: None ist „nicht gemessen" (kein Posten,
    keine Null), 0.0 ist ein gemessener „keine". Genau das trennt eine
    ehrliche Rechung von einer geratenen."""
    satz = dict(O2_MESSUNG, anschlusspreis=None,
                gesamt=round(892.75 - 39.99, 2))
    r = zr._rechung(_messung(satz))
    assert "Anschlusspreis" not in [p["label"] for p in r["posten"]]
    satz0 = dict(O2_MESSUNG, anschlusspreis=0.0, gesamt=852.76)
    r0 = zr._rechung(_messung(satz0))
    anschluss = next(p for p in r0["posten"]
                     if p["label"] == "Anschlusspreis")
    assert anschluss["betrag"] == 0.0


def test_boni_erscheinen_nicht_die_historie_hat_keine():
    r = zr._rechung(_messung(O2_MESSUNG))
    text = json.dumps(r, ensure_ascii=False)
    assert "Bonus" not in text and "Rabatt" not in text


# --------------------------------------------------------------------------
# A1 (20.09.2026): der GRAPH haengt am Stand des Markts, nicht am Stand der
# Formel. Die Historie traegt eingefrorene `gesamt`-Werte der ALTEN (auf 24
# Monate gekappten) Rechnung - die Punkte und die Auswahl des guenstigsten
# Bündels je Tag werden mit der HEUTIGEN Leitzahl neu gerechnet:
#
#   o2:   37 + 39,99 + 24 × 14,99 + 36 × 19,00 = 1.120,75 (statt 892,75)
#   1&1:  420 + 39,90 + 36 × 49,99          = 2.259,54 (statt 1.659,66)
#
# Der eingefrorene Wert bleibt unangetastet (Historie wird nie umge-
# schrieben); nur die Anzeige rechnet neu.
# --------------------------------------------------------------------------

def test_die_serie_rechnet_die_punkte_mit_der_heutigen_leitzahl():
    """Der Punkt der o2-Messung ist die NEU gerechnete 1.120,75 - nicht die
    eingefrorene 892,75 der gekappten Rechnung."""
    messungen = {("m", "b"): {"o2": {"2026-09-12": _messung(O2_MESSUNG)}}}
    assert zr._serien_aus(messungen) == \
        {("m", "b"): {"o2": [("2026-09-12", 1120.75)]}}


def test_die_zusammenform_behaelt_ihre_kurve_und_nennt_ihren_zeitraum():
    """P0-B-z1 (21.09.2026): die 36-Monats-Summe BEHAELT ihre Kurve.

    ROT gegen den vorigen Stand (P0-B-h3): dort gab `_messwert` hier
    `(None, 36)` zurueck und `_serien_aus` eine LEERE Reihe - das
    gemessene Angebot verschwand aus dem Bild, die Tafel zaehlte einen
    Anbieter weniger, und der Leser verlor die Information, dass dieser
    Anbieter das Gerät überhaupt führt. Ein verschwiegenes Angebot ist
    schlimmer als ein beschriftetes (CLAUDE.md: Meldungen werden nie
    gekappt, harte Regel 9).

    Die Kurve steht also - und der Zeitraum, den sie trägt, wird GELESEN
    (`Tco.leitzahl_monate`) und ans Kurvenende geschrieben (`_svg`). Das
    Tor wirkt weiter am Vorzeichen und an der Rangfolge (`_bewegung`,
    `_band_zeilen`), nicht an der Sichtbarkeit.
    """
    m = _messung(EINS_EINS_MESSUNG, anbieter="1&1",
                 tarif="1&1 All-Net-Flat S")
    messungen = {("m", "b"): {"1&1": {"2026-09-12": m}}}
    assert zr._messwert(m) == (2259.54, 36)
    assert zr._serien_aus(messungen) == \
        {("m", "b"): {"1&1": [("2026-09-12", 2259.54)]}}
    # Der Zeitraum JE KURVE - aus derselben Lesung, nicht nachgerechnet.
    assert zr._zeitraeume_aus(messungen) == {("m", "b"): {"1&1": [36]}}
    # Gegenrechnung, dass keine Zahl verbogen wird: die Kennzahl selbst
    # ist unveraendert 2.259,54 EUR ueber 36 Monate.
    kennzahl = tco_24(zr._buendel_aus_messung(m))
    assert (kennzahl.gesamt, kennzahl.leitzahl_monate) == (2259.54, 36)
    assert kennzahl.gesamt == round(420.0 + 39.90 + 36 * 49.99, 2)


def test_die_aufgeteilte_form_nennt_ihre_24_monate_genauso():
    """Die Gegenprobe: o2 rechnet 24 Tarifmonate plus alle Raten - die
    Leitzahl traegt 24 Monate, und `_messwert` NENNT sie. Dass der
    Zeitraum immer mitkommt, ist genau der Unterschied zum alten Stand,
    an dem `None` zweierlei hiess ("passt auf die Achse" und "nicht
    gemessen")."""
    m = _messung(O2_MESSUNG)
    assert zr._messwert(m) == (1120.75, 24)
    assert tco_24(zr._buendel_aus_messung(m)).leitzahl_monate == 24


def test_ohne_belastbare_zahl_gibt_es_weiter_keinen_punkt():
    """Die Grenze des neuen Verhaltens: ein fremder Zeitraum ist KEIN
    Ausfall, eine fehlende Ratenlaufzeit schon. Ohne `laufzeit_monate`
    fehlt der ganze Monatsblock der Zusammenform - kein Punkt, keine
    geratene Hoehe (Clean Code 3)."""
    m = _messung(dict(EINS_EINS_MESSUNG, laufzeit_monate=None),
                 anbieter="1&1", tarif="1&1 All-Net-Flat S")
    assert zr._messwert(m) == (None, None)
    assert zr._serien_aus({("m", "b"): {"1&1": {"2026-09-12": m}}}) == \
        {("m", "b"): {"1&1": []}}
    assert zr._zeitraeume_aus({("m", "b"): {"1&1": {"2026-09-12": m}}}) == \
        {("m", "b"): {"1&1": []}}


def test_die_auswahl_des_guenstigsten_buendels_je_tag_rechnet_neu(tmp_path):
    """Zwei Bündel desselben Anbieters am selben Tag - die eingefrorenen
    Werte sagen A ist günstiger (892,75 < 919,75), die heutige Leitzahl
    sagt B (979,75 < 1.120,75, weil B die kürzere Rate hat). Gewählt wird
    nach der HEUTIGEN Rechnung - sonst klänge der Graph von einer Formel,
    die es nicht mehr gibt."""
    # B: 400 + 39,99 + 24 × 14,99 + 24 × 5,00 = 919,75 (alt eingefroren),
    #    heute: 400 + 39,99 + 24 × 14,99 + 36 × 5,00 = 979,75
    b_satz = dict(O2_MESSUNG, id="buendel--o2--samsung-galaxy-s23-128gb-rosa--b",
                  geraet_zuzahlung=400.0, geraet_monatsrate=5.0, gesamt=919.75)
    (tmp_path / "geraete_tco_historie.jsonl").write_text(
        json.dumps(O2_MESSUNG) + "\n" + json.dumps(b_satz) + "\n",
        encoding="utf-8")
    roh = {"buendel": [
        {"id": O2_MESSUNG["id"], "sku_id": "samsung-galaxy-s23-128gb-rosa",
         "anbieter": "o2", "tarif_id": O2_MESSUNG["tarif_id"],
         "tarif_name": "O2 Mobile on Demand M Plus"},
        {"id": b_satz["id"], "sku_id": "samsung-galaxy-s23-128gb-rosa",
         "anbieter": "o2", "tarif_id": b_satz["tarif_id"],
         "tarif_name": "O2 Mobile on Demand M Plus"}]}
    (tmp_path / "geraete_tco.json").write_text(json.dumps(roh), encoding="utf-8")
    tco = {"modelle": [{"id": "m", "karten": [
        {"sku_id": "samsung-galaxy-s23-128gb-rosa"}]}],
        "band_je_tarif": {O2_MESSUNG["tarif_id"]: "b"}}
    messungen = zr._messungen(tmp_path, tco)
    assert zr._serien_aus(messungen) == \
        {("m", "b"): {"o2": [("2026-09-12", 979.75)]}}
    # Gegenprobe: die eingefrorene Zahl bleibt in der Historien-Zeile
    # stehen - nichts wird umgeschrieben, nur die Anzeige rechnet neu.
    zeilen = [json.loads(z) for z in
              (tmp_path / "geraete_tco_historie.jsonl").read_text(
                  encoding="utf-8").splitlines()]
    assert sorted(z["gesamt"] for z in zeilen) == [892.75, 919.75]


# --------------------------------------------------------------------------
# Der Template-Block - die gesetzte Rechung als Markup
# --------------------------------------------------------------------------

def test_der_block_zeigt_das_mal_muster_und_die_summe():
    """design.md Regel 6: die Rechung ist GESETZT („70,00 € × 24 =
    1 680 €"), keine prose Erklärung - und die Werte genau dieser
    Messung. A1: alle 36 Raten, Summe mit dem Etikett der Leitzahl."""
    html = zr._rechung_html("o2", _messung(O2_MESSUNG))
    assert "24 × 14,99 €" in html and "= 359,76 €" in html
    assert "36 × 19,00 €" in html and "= 684,00 €" in html
    assert "= <b>1.120,75 €</b>" in html
    assert "Kosten über 24 Monate" in html
    assert "TCO-24" not in html


# --------------------------------------------------------------------------
# P1-Fix (17.09.2026, Sicht-A2/A3 + Code-S3-1): Quittungs-Panel - Balken,
# Restschuld, Farbpunkt, 12-px-Regel
# --------------------------------------------------------------------------

def test_jeder_posten_traegt_seinen_anteil_als_balken():
    """Sicht-A2: „nicht nur Zeilen" - je Posten ein Balken in der Breite
    seines Anteils an der Summe. Die Breite ist eine fertige Prozent-
    angabe aus EINER Rechnung (Server), der Client setzt nur ein; der
    groesste Posten hat den breitesten Balken."""
    html = zr._rechung_html("o2", _messung(O2_MESSUNG))
    suppe = BeautifulSoup(html, "html.parser")
    balken = suppe.select("li.gr-zr-posten")
    assert len(balken) == 4
    r = zr._rechung(_messung(O2_MESSUNG))
    breiten = []
    for li, p in zip(balken, r["posten"]):
        i = li.select_one(".gr-zr-pbar i")
        assert i is not None, f"Posten {p['label']} ohne Balken"
        erwartet = f"{p['betrag'] / r['gesamt'] * 100:.1f}%"
        assert i.get("style") == f"width:{erwartet}", i.get("style")
        breiten.append(float(i["style"].split(":")[1].rstrip("%")))
    # Der Tarifposten (359,76 von 892,75) ist breiter als die Zuzahlung
    # (37,00 von 892,75) - die Balken unterscheiden sich sichtbar.
    assert breiten[2] > breiten[0]


def test_die_restschuld_steht_in_der_rechnung_wenn_die_rate_laenger_laeuft():
    """Sicht-A3, seit A1 „davon nach Monat 24 noch zu zahlen" - die Rest-
    schuld IST in der Summe und wird zusaetzlich ausgewiesen (o2: 36
    Raten, 12 × 19,00 € laufen nach Monat 24 weiter). Bei 24 Monaten
    Laufzeit gibt es keine Restschuld (None, keine Zeile) - „nichts
    offen" ist eine Aussage, aber keine Zeile wert."""
    r = zr._rechung(_messung(O2_MESSUNG))
    assert r["offen"] == {"anzahl": 12, "einzeln": 19.0, "betrag": 228.0}
    html = zr._rechung_html("o2", _messung(O2_MESSUNG))
    assert "davon nach Monat 24 noch zu zahlen: 12 × 19,00 €" in html
    assert "= 228,00 €" in html
    # zusammen-Form (1&1): der Bündelbetrag laeuft weiter, derselbe Satz
    r11 = zr._rechung(_messung(EINS_EINS_MESSUNG, anbieter="1&1",
                               tarif="1&1 All-Net-Flat S"))
    assert r11["offen"] == {"anzahl": 12, "einzeln": 49.99,
                            "betrag": round(12 * 49.99, 2)}
    html11 = zr._rechung_html("1&1", _messung(
        EINS_EINS_MESSUNG, anbieter="1&1", tarif="1&1 All-Net-Flat S"))
    assert "davon nach Monat 24 noch zu zahlen: 12 × 49,99 € = 599,88 €" \
        in html11
    # 24 Monate: keine Zeile
    kurz = dict(O2_MESSUNG, laufzeit_monate=24, gesamt=round(
        37.0 + 39.99 + 24 * 14.99 + 24 * 19.0, 2))
    rk = zr._rechung(_messung(kurz))
    assert rk["offen"] is None
    assert "davon nach Monat 24" not in zr._rechung_html("o2", _messung(kurz))


def test_der_rechnungskopf_traegt_den_farbpunkt_des_anbieters():
    """Sicht 12: Anbieter-Farbpunkt im Panel-Kopf - dieselbe Farbe wie die
    Linie im Graphen (die Kopplung, die das Lesen des Charts lehrt)."""
    html = zr._rechung_html("o2", _messung(O2_MESSUNG))
    assert "<i class='gr-zr-rpunkt' style='background:#0019a5'" in html
    html11 = zr._rechung_html("1&1", _messung(EINS_EINS_MESSUNG,
                                              anbieter="1&1",
                                              tarif="1&1 All-Net-Flat S"))
    assert "background:#2f7fd1" in html11


def test_der_klammer_text_und_das_label_erfuellen_die_12_px_regel():
    """Code-S3-1: die Klammer („24 von 36 Raten") erklaert den Faktor und
    das „TCO-24"-Etikett die Summe - lesende Labels, die im Panel erst
    nach dem Klick entstehen (Template-Inhalt): 13 bzw. 12 px."""
    css = (WURZEL / "src" / "telco_radar" / "report" / "templates"
           / "style.css").read_text(encoding="utf-8")
    klammer = re.search(r"\.gr-zr-pk\{[^}]*font-size:(\d+(?:\.\d+)?)px",
                        css)
    label = re.search(r"\.gr-zr-plabel\{[^}]*font-size:(\d+(?:\.\d+)?)px",
                      css)
    assert klammer and float(klammer.group(1)) >= 12, "Klammer unter 12 px"
    assert label and float(label.group(1)) >= 12, "TCO-Label unter 12 px"


def test_der_block_traegt_anbieter_messtag_und_beleg_dieses_tages():
    html = zr._rechenwege_html(
        {"o2": {"2026-09-12": _messung(O2_MESSUNG)}}, [])
    assert "data-anb='o2'" in html and "data-m='2026-09-12'" in html
    assert "Messung vom 12. September 2026" in html
    # Der Beleg nennt das Abrufdatum der MESSUNG, nicht das von heute -
    # genau das war die Lücke des statischen „So gerechnet"-Satzes.
    assert "abgerufen 12.09.2026" in html
    assert "https://www.o2online.de/e-shop/samsung/s23" in html


def test_je_serie_und_messung_gibt_es_genau_ein_template():
    messungen = {"o2": {"2026-09-12": _messung(O2_MESSUNG),
                        "2026-09-13": _messung(dict(O2_MESSUNG,
                                                    datum="2026-09-13"))}}
    html = zr._rechenwege_html(messungen, [])
    suppe = BeautifulSoup(html, "html.parser")
    templates = suppe.select("template[data-anb][data-m]")
    assert len(templates) == 2
    assert {t["data-m"] for t in templates} == {"2026-09-12", "2026-09-13"}
    assert suppe.select_one(".gr-zr-rechnungen") is not None
    assert suppe.select_one(".gr-zr-rechnungen").has_attr("hidden")


def test_die_naeherung_bekommt_einen_benannten_leerzustand():
    """Vodafone-Näherungspunkte haben keine Historien-Zeile - der Klick
    darf nicht ins Leere laufen. Kein Posten wird erfunden."""
    html = zr._rechenwege_html({}, [{"anbieter": "Vodafone",
                                     "naeherung": True, "gesamt": 123.0}])
    suppe = BeautifulSoup(html, "html.parser")
    leer = suppe.select_one("template[data-anb='Vodafone']"
                            "[data-m='naeherung']")
    assert leer is not None
    text = leer.get_text(" ", strip=True)
    assert "Referenzrechnung, kein Angebot" in text
    assert "keine Messung je Messtag" in text
    # kein erfundener Posten im Leerzustand:
    assert leer.select(".gr-zr-posten") == []


def test_der_leerzustands_text_steht_woertlich_in_der_buendel_vorlage():
    """Der Satz ist der Hinweis von der Bündel-Karte (`gr-kk-hinweis`),
    nicht neu erfunden - und dieser Test meldet, wenn einer der beiden
    Orte geändert wird und der andere driftet."""
    vorlage = (WURZEL / "src" / "telco_radar" / "report" / "templates"
               / "_geraete_buendel.html.j2").read_text(encoding="utf-8")
    kompakt = " ".join(zr._NAEHERUNG_SATZ.split())
    assert kompakt in " ".join(vorlage.split())


def test_zwei_preisformen_am_selben_tag_bleiben_zwei_templates():
    messungen = {"o2": {"2026-09-12": _messung(O2_MESSUNG)},
                 "1&1": {"2026-09-12": _messung(EINS_EINS_MESSUNG,
                                                anbieter="1&1",
                                                tarif="1&1 All-Net-Flat S")}}
    html = zr._rechenwege_html(messungen, [])
    suppe = BeautifulSoup(html, "html.parser")
    paare = {(t["data-anb"], t["data-m"])
             for t in suppe.select("template[data-anb][data-m]")}
    assert paare == {("o2", "2026-09-12"), ("1&1", "2026-09-12")}


# --------------------------------------------------------------------------
# Das SVG - jeder Punkt findet seinen Rechenweg
# --------------------------------------------------------------------------

def _serien():
    return {"o2": [["2026-09-12", 892.75], ["2026-09-13", 890.0]]}


def test_jeder_kreis_traegt_anbieter_und_messtag():
    svg = zr._svg(_serien(), True, {"o2": ("https://b", "2026-09-13")})
    suppe = BeautifulSoup(svg, "html.parser")
    punkte = suppe.select("circle.gr-zr-punkt[data-anb][data-m]")
    assert {(p["data-anb"], p["data-m"]) for p in punkte} == \
        {("o2", "2026-09-12"), ("o2", "2026-09-13")}


def test_ueber_jedem_punkt_liegt_eine_unsichtbare_trefferflaeche():
    """r=4,5 ist auf dem Telefon nicht zu treffen (Strategie P1). Die
    Klasse ist `gr-zr-hit` - `gr-zr-treffer` gehört der Suchvorschau
    (style.css) und darf nicht doppelt benutzt werden."""
    svg = zr._svg(_serien(), True, {"o2": ("https://b", "2026-09-13")})
    suppe = BeautifulSoup(svg, "html.parser")
    hits = suppe.select("circle.gr-zr-hit")
    punkte = suppe.select("circle.gr-zr-punkt")
    assert len(hits) == len(punkte) == 2
    assert all(h.get("r") == "12" for h in hits)
    assert all(h.get("fill") == "transparent" for h in hits)
    assert {(h["data-anb"], h["data-m"]) for h in hits} == \
        {("o2", "2026-09-12"), ("o2", "2026-09-13")}
    assert "gr-zr-treffer" not in svg


def test_jeder_punkt_traegt_eine_hover_vorschau():
    """Sicht 11: vor dem Klick sieht die Maus, was sie trifft - Anbieter,
    Messtag und Betrag als nativer <title> am Hit-Kreis (fertige Zeichen-
    kette vom Server, nichts wird im Client gebaut)."""
    svg = zr._svg(_serien(), True, {"o2": ("https://b", "2026-09-13")})
    suppe = BeautifulSoup(svg, "html.parser")
    titel = {t.get_text(strip=True): (t.parent.get("data-anb"),
                                      t.parent.get("data-m"))
             for t in suppe.select("circle.gr-zr-hit > title")}
    assert titel == {
        "o2 · 12.9. · 893 €": ("o2", "2026-09-12"),
        "o2 · 13.9. · 890 €": ("o2", "2026-09-13"),
    }


def test_zwei_zeitraeume_stehen_an_den_kurven_und_in_der_beschriftung():
    """P0-B-z1: das Bild trägt zwei Laufzeiten - und sagt das.

    ROT gegen den vorigen Stand zweifach: `_svg` kannte den vierten
    Parameter nicht (die Kurve des fremden Zeitraums war schon vorher
    weggenommen), und das aria-label behauptete fest "Kosten über 24
    Monate" über jeder Kurve im Bild. Jetzt nennt die Beschriftung beide
    Zeitraeume, und JEDE Kurve trägt ihren am Ende - einer allein liest
    sich, als gelte er auch fuer die anderen.
    """
    serien = {"o2": [["2026-09-12", 892.75], ["2026-09-13", 890.0]],
              "1&1": [["2026-09-12", 2019.54], ["2026-09-13", 2019.54]]}
    svg = zr._svg(serien, True, {"o2": ("https://b", "2026-09-13")},
                  {"o2": [24], "1&1": [36]})
    assert ("aria-label='Kosten über 24 und 36 Monate je Messtag und "
            "Anbieter: o2, 1&amp;1'") in svg, svg[:400]
    suppe = BeautifulSoup(svg, "html.parser")
    etiketten = [t.get_text(strip=True)
                 for t in suppe.select("text.gr-zr-mon")]
    assert sorted(etiketten) == ["24 Mon.", "36 Mon."], etiketten
    # Die Kurve selbst ist da: zwei Punkte je Anbieter.
    assert len(suppe.select("circle.gr-zr-punkt[data-anb='1&1']")) == 2


def test_ein_einziger_zeitraum_steht_nur_in_der_beschriftung():
    """Die Gegenprobe zu Antonios „wenig Text": gilt EIN Zeitraum fuer
    alle Kurven, sagt ihn die Beschriftung - und keine Kurve wiederholt
    ihn (eine Angabe je Ort)."""
    svg = zr._svg(_serien(), True, {"o2": ("https://b", "2026-09-13")},
                  {"o2": [24]})
    assert "aria-label='Kosten über 24 Monate je Messtag und " \
        "Anbieter: o2'" in svg
    assert "gr-zr-mon" not in svg


def test_ohne_gelesenen_zeitraum_behauptet_die_beschriftung_keinen():
    """Clean Code 3/4: ist kein Zeitraum gelesen, steht keiner da - eine
    angenommene 24 waere genau die falsche Beschriftung, die P0-B-z1
    abstellt."""
    svg = zr._svg(_serien(), True, {"o2": ("https://b", "2026-09-13")}, {})
    assert "aria-label='Kosten je Messtag und Anbieter: o2'" in svg
    assert "Monate" not in svg


def test_ein_einzelmesstag_traegt_einen_halo_und_heisst_erstmals():
    """Sicht 15: eine Serie mit EINEM Messtag ist „erstmals gemessen" -
    ein Halo-Ring macht den Punkt absichtlich auffaellig (ein nackter
    Punkt ohne Linie liest sich sonst wie ein Fehler). Der zweite
    Messtag macht die Serie zur Linie und laesst den Halo verschwinden."""
    eine = {"o2": [["2026-09-12", 892.75]]}
    svg = zr._svg(eine, True, {"o2": ("https://b", "2026-09-12")})
    suppe = BeautifulSoup(svg, "html.parser")
    assert len(suppe.select("circle.gr-zr-halo")) == 1
    titel = suppe.select_one("circle.gr-zr-hit > title").get_text(
        strip=True)
    assert titel == "o2 · 12.9. · 893 € · erstmals gemessen"
    # Drei Messungen: kein Halo, kein „erstmals" mehr
    svg3 = zr._svg({"o2": [["2026-09-12", 892.75],
                           ["2026-09-13", 890.0],
                           ["2026-09-14", 891.0]]},
                   True, {"o2": ("https://b", "2026-09-14")})
    suppe3 = BeautifulSoup(svg3, "html.parser")
    assert suppe3.select("circle.gr-zr-halo") == []
    assert "erstmals" not in svg3


# --------------------------------------------------------------------------
# Integration - First Paint und Fragment tragen dieselben Vorlagen
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gerendert(tmp_path_factory):
    root, state = _baue(tmp_path_factory.mktemp("zrrechen"))
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


def _treffer_und_vorlagen(container: BeautifulSoup) -> tuple[set, set]:
    """(Kreis-Paare, Template-Paare) eines Blocks - die Kreise kommen in
    beiden SVG-Varianten doppelt vor, Templates nicht."""
    kreise = {(c["data-anb"], c["data-m"])
              for c in container.select("circle.gr-zr-hit")}
    vorlagen = {(t["data-anb"], t["data-m"])
                for t in container.select("template[data-anb][data-m]")}
    return kreise, vorlagen


def test_im_first_paint_findet_jeder_kreis_sein_template(gerendert):
    suppe = BeautifulSoup((gerendert / "geraete.html").read_text(
        encoding="utf-8"), "html.parser")
    block = suppe.select_one("#tafel-tco .gr-zr-graph")
    assert block is not None
    kreise, vorlagen = _treffer_und_vorlagen(block)
    assert kreise, "der Startblock braucht Punkte mit Trefferfläche"
    assert kreise <= vorlagen, \
        f"Kreise ohne Rechenweg-Vorlage: {kreise - vorlagen}"


def test_im_fragment_findet_jeder_kreis_sein_template(gerendert):
    inhalt = (gerendert / "data" / "geraete-zeitreihe.html").read_text(
        encoding="utf-8")
    suppe = BeautifulSoup(inhalt, "html.parser")
    lager = suppe.select(".gr-zr-lager")
    assert lager, "das Fragment braucht Blöcke"
    for block in lager:
        kreise, vorlagen = _treffer_und_vorlagen(block)
        if not kreise:
            continue                    # Paar ohne Serie (ehrlicher Leer-Satz)
        assert kreise <= vorlagen, \
            f"{block.get('data-modell')}/{block.get('data-band')}: " \
            f"Kreise ohne Vorlage: {kreise - vorlagen}"


def test_der_rechenweg_steht_unter_dem_svg_nicht_daneben(gerendert):
    """Montagevertrag mit app.js (A2): die Vorlagen liegen IM Graph-Block
    unter dem Bild - der Klick-Handler findet sie relativ zum SVG."""
    suppe = BeautifulSoup((gerendert / "geraete.html").read_text(
        encoding="utf-8"), "html.parser")
    graph = suppe.select_one("#tafel-tco .gr-zr-graph")
    bild = graph.select_one(".gr-zr-bild")
    lager = graph.select_one(".gr-zr-rechnungen")
    assert lager is not None
    assert bild is not None and lager.sourceline > bild.sourceline


def test_der_json_knoten_bleibt_zahlenfrei(gerendert):
    """Regel 1 des Moduls: die Beträge stehen im HTML (Vorlage), nicht im
    JSON-Knoten für den Client - sonst rechnete oder formatierte der
    Browser doch."""
    suppe = BeautifulSoup((gerendert / "geraete.html").read_text(
        encoding="utf-8"), "html.parser")
    knoten = suppe.select_one("#gr-zeitreihe-daten")
    assert knoten is not None
    assert "€" not in knoten.string
    assert "×" not in knoten.string
