"""BRIEF_RAHMEN (05.09.2026): die Geraeteseite zieht in den Rahmen der von
Antonio gebilligten Skizze (`entwurf_geraete_v2.html`) um.

Drei Abnahmekriterien, drei Testgruppen:
  1. Erklaertexte raus (A-R1): kein erklaerender Fliesstext mehr im
     Lesefluss - die vier benannten Wortlaute zaehlen ausserhalb eines
     `<details>`-Blocks 0-mal.
  2. Haendler als benannte Luecke (A-R3): Amazon, Expert und Saturn stehen
     je Modell als graue Zeile OHNE Wert - im Balkenblock UND als
     Legenden-Eintrag ohne Linie in der Zeitreihe.
  3. Die Seiten-Ueberschrift stellt Antonios Frage woertlich.

Dieselbe Fixture wie `test_geraete_tco_zustand._baue` (ein Modell, o2
neu+erneuert, Vodafone als Referenzrechnung) - sie deckt genau die zwei
Kartenarten ab, die die Erklaerzeilen bisher trugen.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from test_geraete_tco_zustand import _baue

# Wortlaut wie im Auftrag benannt (BRIEF_RAHMEN, Kriterium 1). Die
# typografischen Anfuehrungszeichen sind Absicht - so steht der Satz im
# Repo, ein glatter Apostroph traefe ihn nicht.
VERBOTSMARKER = ("Gerechnet wird", "Die Grenze:", "Monatspreis „ab“",
                  "Referenzrechnung, kein Angebot")

HAENDLER = ("Amazon", "Expert", "Saturn")


def _ohne_details(suppe: BeautifulSoup) -> str:
    """Der Lesefluss: derselbe Baum, aber jeder `<details>`-Block samt
    Inhalt entfernt. Eine neue Kopie, damit der Aufrufer die Original-Suppe
    unangetastet weiterverwenden kann."""
    kopie = BeautifulSoup(str(suppe), "html.parser")
    for block in kopie.find_all("details"):
        block.decompose()
    return kopie.get_text(" ")


# --------------------------------------------------------------------------
# Kriterium 1: Erklaertexte raus
# --------------------------------------------------------------------------

def test_keine_erklaerung_steht_ausserhalb_einer_aufklappung(tmp_path):
    s = _baue(tmp_path)
    lesefluss = _ohne_details(s)
    treffer = {m: lesefluss.count(m) for m in VERBOTSMARKER}
    assert not any(treffer.values()), (
        f"Erklaerung(en) ausserhalb einer Aufklappung: {treffer}")


def test_der_waechter_prueft_wirklich_etwas(tmp_path):
    """Gegenprobe: mindestens einer der Marker taucht an dieser Fixture
    UEBERHAUPT auf (nur eben hinter einer Aufklappung) - sonst prueft der
    Test oben nur, dass niemand danach sucht.

    BRIEF_RAHMEN2 (05.09.2026, Befund 2): "Gerechnet wird" stand in der
    seitenweiten "Wie gerechnet?"-Aufklappung, die ersatzlos gestrichen ist
    (sie stand doppelt - siehe `test_wie_gerechnet_steht_hoechstens_einmal_
    je_modellblock`). Der Marker zaehlt seitdem 0-mal, auch hinter einer
    Aufklappung, und ist deshalb kein Beleg mehr fuer diesen Waechter.
    """
    s = _baue(tmp_path)
    ganze_seite = str(s)
    gefunden = {m: ganze_seite.count(m) for m in VERBOTSMARKER}
    assert gefunden["Referenzrechnung, kein Angebot"] >= 1, gefunden


def test_wie_gerechnet_steht_hoechstens_einmal_je_modellblock(tmp_path):
    """BRIEF_RAHMEN2 (05.09.2026, Befund 2): 'Wie gerechnet?' stand
    zweimal - einmal seitenweit ueber der Kennzahlenreihe (`#gr-tco-wie`),
    einmal je Modell unter dem Zeitreihen-Graph. Die obere ist ERSATZLOS
    gestrichen, die untere bleibt (sie ist beim Graphen richtig
    platziert): GENAU EINE Aufklappung dieses Namens je Modellblock, keine
    ausserhalb.

    BRIEF_RAHMEN2_R3 (05.09.2026): die Fixture traegt seitdem zusaetzlich
    einen GRAPHLOSEN Block (`graphloses_modell=True`) - drei echte
    Modellbloecke im Bestand haben keinen Zeitreihen-Graphen und trugen
    deshalb GAR KEINE Aufklappung. `== 1` gilt seitdem fuer beide Arten
    von Block."""
    s = _baue(tmp_path, graphloses_modell=True)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select_one("#gr-tco-wie") is None, \
        "die seitenweite 'Wie gerechnet?'-Aufklappung ist nicht mehr da"

    modellbloecke = tafel.select(".gr-tmodell")
    assert modellbloecke, "der Test prueft nichts ohne Modellblock"
    for block in modellbloecke:
        wie_gerechnet = [d for d in block.select("details.gr-auf")
                         if d.select_one("summary").get_text(strip=True)
                         == "Wie gerechnet?"]
        assert len(wie_gerechnet) == 1, \
            f"{block.get('data-modell')}: {len(wie_gerechnet)} statt 1"

    # Ausserhalb jedes Modellblocks, aber innerhalb der Tafel, darf keine
    # weitere "Wie gerechnet?"-Aufklappung stehen - sonst waere die
    # Verdopplung nur verschoben, nicht behoben.
    ausserhalb = _ohne_details_ausser(tafel, modellbloecke)
    assert "Wie gerechnet?" not in ausserhalb
    # Die alte Buendel-Sicht-Ueberschrift ist weg, nicht umbenannt.
    assert "Was ein Gerät mit Tarif wirklich kostet" not in str(s)


def _ohne_details_ausser(tafel: BeautifulSoup, modellbloecke) -> str:
    """Der Text der Tafel ohne jeden Modellblock - fuer die Ausserhalb-Probe."""
    kopie = BeautifulSoup(str(tafel), "html.parser")
    for block in kopie.select(".gr-tmodell"):
        block.decompose()
    return kopie.get_text(" ")


def test_ein_block_ohne_graph_traegt_trotzdem_eine_wie_gerechnet_aufklappung(tmp_path):
    """BRIEF_RAHMEN2_R3 (05.09.2026) fand 3 von 59 Modellbloecken ohne
    Aufklappung. O1 (11.09.2026) hat den Fall umgedreht: Es steht nur noch
    der EINE Modellblock der Vorgabe im Dokument, und die
    "Wie gerechnet?"-Aufklappung haengt am GRAPHEN. Ein Modell ohne ein
    einziges Band steht im Dropdown UND im JSON-Knoten mit seinem
    Leerlauf-Satz - der Wechsel dorthin ist derselbe Pfad wie jeder andere
    Modellwechsel, und der Leerlauf ist der ehrliche Zustand statt einer
    Aufklappung ueber nichts."""
    import json
    s = _baue(tmp_path, graphloses_modell=True)
    tafel = s.select_one("#tafel-tco")

    assert s.select_one(
        '.gr-tmodell[data-modell="apple-iphone-16-pro-max-256"]') is None, \
        "mit O1 steht nur der Vorgabeblock im Dokument (die 88-fache " \
        "Wiederholung entfaellt)"

    option = s.select_one(
        '#gr-modell option[value="apple-iphone-16-pro-max-256"]')
    assert option is not None, "das band-lose Modell fehlt im Dropdown"
    knoten = json.loads(tafel.select_one("#gr-graph-daten").get_text())
    im_json = [m for m in knoten["modelle"]
               if m["id"] == "apple-iphone-16-pro-max-256"]
    assert im_json and im_json[0]["band_leer"], \
        "der Leerlauf-Satz fehlt im JSON-Knoten"

    vorgabe = tafel.select_one(".gr-tmodell")
    wie_gerechnet = [d for d in vorgabe.select("details.gr-auf")
                     if d.select_one("summary").get_text(strip=True)
                     == "Wie gerechnet?"]
    assert len(wie_gerechnet) == 1
    kinder = [k for k in vorgabe.find_all(recursive=False)]
    tabelle = vorgabe.select_one("#gr-buendel")
    assert tabelle is not None, "die Bündel-Tabelle fehlt"
    # Die Aufklappung steht IM Graph-Modul, die Tabelle DANACH - beide sind
    # direkte Kinder des Modellblocks, in dieser Reihenfolge (O2: die
    # Kartenklappe ist die offene Tabelle geworden).
    hgraph = vorgabe.select_one(".gr-hgraph")
    assert wie_gerechnet[0].find_parent("section", class_="gr-hgraph") is hgraph
    assert kinder.index(hgraph) < kinder.index(tabelle)


# --------------------------------------------------------------------------
# O2 (11.09.2026): die Bündel-Zeilen - Kartenklappe und Karten sind weg
# --------------------------------------------------------------------------

def test_die_buendel_stehen_als_zeilen_unter_dem_graphen(tmp_path):
    """O2 ersetzt die OPTIK-6-Klappe: jede Karte ist EINE Zeile mit EINEM
    eigenen Aufklapper - keine geschlossene Sammelklappe mehr, kein
    Steuerpult. Die Anfangshöhe hält stattdessen die Zeilenform selbst
    (eine zusammengeklappte Zeile ist eine Zeile hoch)."""
    s = _baue(tmp_path, graphloses_modell=True)
    tafel = s.select_one("#tafel-tco")
    assert tafel is not None
    block = tafel.select_one(".gr-tmodell")
    assert block is not None, "der Test prüft nichts ohne Modellblock"
    assert block.select_one("details.gr-karten-auf") is None, \
        "die Kartenklappe steht noch"
    assert not block.select(".gr-kkarte"), "Karten stehen noch"
    zeilen = block.select("#gr-bndliste .gr-bnd")
    assert zeilen, "die Zeilenliste ist leer"
    for zeile in zeilen:
        assert not zeile.has_attr("open"), \
            f"{zeile.get('data-anbieter')}: Zeile steht offen im HTML"
    # Keine Zähler in der Überschrift der Tabelle - eine Klammer, die
    # anders zählt als der Bestand darunter, bleibt verboten (O1-Regel,
    # jetzt an der Tabelle; der Modellname mit seiner GB-Zahl ist kein
    # Zähler).
    titel = block.select_one("#gr-bnd-titel")
    assert titel is not None
    assert "Karten" not in titel.get_text(), titel.get_text()
    assert not re.search(r"\(\d+", titel.get_text()), titel.get_text()


# --------------------------------------------------------------------------
# Kriterium 2: Haendler als benannte Luecke
# --------------------------------------------------------------------------

def test_haendler_ohne_preis_stehen_nur_in_der_legende(tmp_path):
    """O2: die 'Beschaffung läuft'-Platzhalterkarten fallen - die
    Legendenzeile aus O1 trägt dieselbe Information (Auftrag 2). Amazon und
    Expert stehen also NUR dort, nirgends als Karte oder Zeile mit
    'Beschaffung läuft'-Satz."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    kopie = BeautifulSoup(str(tafel), "html.parser")
    for k in kopie.select("script"):
        k.decompose()
    text = kopie.get_text(" ")
    for name in HAENDLER:
        assert name in text, f"{name} fehlt ganz"
    assert text.count("Beschaffung läuft") == 1, \
        "der Satz steht mehrfach da - die Legende trägt ihn allein"
    assert not tafel.select(".gr-kkarte--haendler"), \
        "Händlerplatzhalterkarten stehen noch"


def test_haendler_stehen_je_modell_als_legende_ohne_linie(tmp_path):
    """O1 (11.09.2026): die drei 'Beschaffung läuft'-Einzelsaetze am
    Zeitreihen-Block sind EINE Legendenzeile unter dem Graphen - dieselbe
    Zeile, die auch fehlende Buendel-Anbieter nennt (A3). Keine Linie,
    kein Balken, kein erfundener Wert."""
    s = _baue(tmp_path)
    for modell in s.select("#tafel-tco .gr-tmodell"):
        legende = modell.select_one(".gr-lueckenzeile")
        assert legende is not None, "die Legendenzeile fehlt unter dem Graphen"
        text = " ".join(legende.get_text(" ", strip=True).split())
        for name in HAENDLER:
            assert name in text, f"{name} fehlt in der Legendenzeile"
        assert text.count("Beschaffung läuft") == 1
        assert "€" not in text
        assert legende.find("svg") is None


def test_keine_balkengrafik_zeichnet_einen_haendler():
    """G1 (der Balken-SVG) bleibt inhaltlich unangetastet - die drei
    Haendler duerfen darin nicht als Balken auftauchen, auch nicht mit
    Laenge null (das laese sich als "kostenlos")."""
    from telco_radar.report import geraete_tco_grafik as grafik
    from test_geraete_tco_zustand import _modell

    svg = grafik.balken(_modell())
    for name in HAENDLER:
        assert name not in svg


# --------------------------------------------------------------------------
# Kriterium 3: die Seitenueberschrift
#
# BRIEF_FADEN (05.09.2026, PM/Seneca): die Frage-Ueberschrift aus
# BRIEF_RAHMEN ist gescheitert (Antonio: "Digga, spinnst du?" - flapsig,
# "ich" mehrdeutig) und weicht der sachlichen "Gerätepreise im Vergleich".
# Dieser Test hielt bis dahin die AELTERE Entscheidung fest; er haelt jetzt
# die neuere - derselbe Vorgang wie bei jeder umgekehrten Regel dieses
# Projekts (CLAUDE.md §6: "eine falsche Vorgabe kassiert").
# --------------------------------------------------------------------------

def test_die_ueberschrift_ist_sachlich_nicht_die_gescheiterte_frage(tmp_path):
    s = _baue(tmp_path)
    h1 = s.select_one("h1")
    assert h1.get_text(strip=True) == "Gerätepreise im Vergleich"
    titel = s.select_one("title").get_text(strip=True)
    assert "Gerätepreise im Vergleich" in titel
    assert "Dieses Gerät" not in str(s)
    assert "wo kaufe ich es am günstigsten" not in str(s)
