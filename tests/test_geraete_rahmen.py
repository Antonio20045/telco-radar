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


def test_wie_gerechnet_ist_weg_so_gerechnet_steht_genau_einmal(tmp_path):
    """E2 (§3.1, Antonio 16.09.): 'Wie gerechnet?' ist ENDE - was bleibt,
    ist der EINE Rechenschafts-Aufklapper 'So gerechnet' unter dem
    Antwort-Satz des Startzustands. Dazu der Rechenweg je Bündel-Zeile
    (b) und der Fuss-Aufklapper (c): genau drei Aufklapper-Typen, kein
    vierter im Lesefluss."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert "Wie gerechnet?" not in tafel.get_text(" ")
    rechnung = tafel.select("details.gr-zr-rechnung")
    assert len(rechnung) == 1, \
        f"{len(rechnung)} Rechenschafts-Aufklapper statt genau einem"
    assert rechnung[0].select_one("summary").get_text(strip=True) == \
        "So gerechnet"
    assert "Kosten über 24 Monate" in rechnung[0].get_text(" ")
    assert "TCO-24" not in rechnung[0].get_text(" ")
    # Die alte seitenweite Aufklappung bleibt verboten.
    assert tafel.select_one("#gr-tco-wie") is None


def _ohne_details_ausser(tafel: BeautifulSoup, modellbloecke) -> str:
    """Der Text der Tafel ohne jeden Modellblock - fuer die Ausserhalb-Probe."""
    kopie = BeautifulSoup(str(tafel), "html.parser")
    for block in kopie.select(".gr-tmodell"):
        block.decompose()
    return kopie.get_text(" ")


def test_ein_modell_ohne_band_ist_nicht_waehlbar(tmp_path):
    """E2: mit O1 stand nur der Vorgabeblock im Dokument; die Zeitreihe
    geht weiter - ein Modell OHNE Bündel-Band hat keinen Graph-Zustand und
    keine Band-Zeilen, es ist in der Wahl nicht vorhanden (erlaubt leer).
    Der Leerlauf-Satz für Paare ohne Messreihe steht je Paar im Fragment."""
    import json
    s = _baue(tmp_path, graphloses_modell=True)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select_one(".gr-tmodell") is None, \
        "der Modellblock-Div ist mit der Zeitreihe gefallen"
    knoten = json.loads(
        s.select_one("#gr-zeitreihe-daten").get_text())
    assert knoten["erlaubt"].get("apple-iphone-16-pro-max-256") in \
        (None, []), "das bandlose Modell duerfte nicht wählbar sein"


def test_die_buendel_stehen_als_zeilen_unter_dem_graphen(tmp_path):
    """O2 ersetzt die OPTIK-6-Klappe: jede Karte ist EINE Zeile mit EINEM
    eigenen Aufklapper - keine geschlossene Sammelklappe mehr, kein
    Steuerpult. Die Anfangshöhe hält stattdessen die Zeilenform selbst
    (eine zusammengeklappte Zeile ist eine Zeile hoch)."""
    s = _baue(tmp_path, graphloses_modell=True)
    tafel = s.select_one("#tafel-tco")
    assert tafel is not None
    # E2: die Tabelle hängt an ihrem eigenen Abschnitt, nicht mehr am
    # Modellblock-Div (der ist mit der Zeitreihe gefallen).
    block = tafel.select_one("#gr-buendel")
    assert block is not None, "der Test prüft nichts ohne Bündel-Abschnitt"
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

def test_haendler_ohne_preis_stehen_nicht_einzeln(tmp_path):
    """E2 (Antonio 9b.7): die 'Beschaffung läuft'-Legende der Balkenform
    ist gefallen. Amazon und Expert stehen weder als Karte/Zeile noch in
    einer Legende der Hauptansicht - die Quellenseite nennt die
    Beschaffung, der Katalog die Listungen."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    kopie = BeautifulSoup(str(tafel), "html.parser")
    for k in kopie.select("script"):
        k.decompose()
    text = kopie.get_text(" ")
    assert "Beschaffung läuft" not in text
    for name in HAENDLER:
        assert name not in text, f"{name} steht einzeln in der Lesefläche"
    assert not tafel.select(".gr-kkarte--haendler"), \
        "Händlerplatzhalterkarten stehen noch"


def test_die_grafik_nennt_nur_buendel_anbieter(tmp_path):
    """Der Lückensatz unter dem Graphen nennt ausschließlich den Anbieter-
    kreis der Bündel (Telekom, Vodafone, o2, 1&1, congstar) - keine
    Händler, keine je-Anbieter-Zeilen, kein SVG in der Legende."""
    s = _baue(tmp_path)
    for legende in s.select("#tafel-tco .gr-lueckenzeile"):
        text = " ".join(legende.get_text(" ", strip=True).split())
        for name in HAENDLER:
            assert name not in text, f"{name} steht in der Lücken-Zeile"
        assert legende.find("svg") is None


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
