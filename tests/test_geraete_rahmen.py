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
    """Gegenprobe: mindestens zwei der Marker tauchen an dieser Fixture
    UEBERHAUPT auf (nur eben hinter einer Aufklappung) - sonst prueft der
    Test oben nur, dass niemand danach sucht."""
    s = _baue(tmp_path)
    ganze_seite = str(s)
    gefunden = {m: ganze_seite.count(m) for m in VERBOTSMARKER}
    assert gefunden["Gerechnet wird"] >= 1, gefunden
    assert gefunden["Referenzrechnung, kein Angebot"] >= 1, gefunden


def test_die_seitenueberschrift_traegt_genau_eine_wie_gerechnet_aufklappung(tmp_path):
    """'genau EINER Aufklappung je Seite' - die zwei Methodensaetze stehen
    in EINEM neuen Block, nicht verteilt auf mehrere."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    block = tafel.select_one("#gr-tco-wie")
    assert block is not None, "die Seiten-Aufklappung 'Wie gerechnet?' fehlt"
    assert block.select_one("summary").get_text(strip=True) == "Wie gerechnet?"
    assert "Gerechnet wird" in block.get_text(" ")
    # Die alte Buendel-Sicht-Ueberschrift ist weg, nicht umbenannt.
    assert "Was ein Gerät mit Tarif wirklich kostet" not in str(s)


# --------------------------------------------------------------------------
# Kriterium 2: Haendler als benannte Luecke
# --------------------------------------------------------------------------

def test_haendler_stehen_je_modell_im_balkenblock_ohne_wert(tmp_path):
    s = _baue(tmp_path)
    for modell in s.select("#tafel-tco .gr-tmodell"):
        karten = {name: modell.select_one(
            f'.gr-kkarte--haendler[data-anbieter="{name}"]') for name in HAENDLER}
        for name, karte in karten.items():
            assert karte is not None, f"{name} fehlt im Balkenblock"
            # Keine erfundene Zahl: keins der data-*-Attribute, aus denen
            # Sortierung und G1-Balkenlaenge rechnen.
            for attr in ("data-gesamt", "data-schnitt", "data-einmalig"):
                assert karte.get(attr) in (None, ""), \
                    f"{name} traegt {attr}={karte.get(attr)!r}"
            assert "Beschaffung läuft" in karte.get_text(" ", strip=True)
            assert "€" not in karte.get_text(" ", strip=True)


def test_haendler_stehen_je_modell_als_legende_ohne_linie(tmp_path):
    s = _baue(tmp_path)
    for modell in s.select("#tafel-tco .gr-tmodell"):
        legende = modell.select_one(".gr-g0-haendler")
        assert legende is not None, "die Haendler-Legende fehlt am Zeitreihen-Block"
        text = " ".join(legende.get_text(" ", strip=True).split())
        for name in HAENDLER:
            assert name in text
        assert text.count("Beschaffung läuft") == 3
        assert "€" not in text
        # Kein Balken, keine Linie: die Legende steht ausserhalb des SVG.
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
# --------------------------------------------------------------------------

def test_die_ueberschrift_stellt_antonios_frage(tmp_path):
    s = _baue(tmp_path)
    h1 = s.select_one("h1")
    assert h1.get_text(strip=True) == \
        "Dieses Gerät — wo kaufe ich es am günstigsten?"
    titel = s.select_one("title").get_text(strip=True)
    assert "Dieses Gerät" in titel and "günstigsten" in titel
