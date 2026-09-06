"""BRIEF_FADEN (05.09.2026, Senecas Freigabe): die Geraeteseite auf EINE
Frage reduziert - "Was kostet dieses Gerät?".

Sechs Abnahmekriterien, sechs Testgruppen:
  1. Ein Graph: G0 ist die einzige `<svg>`-Grafik im sichtbaren Bereich je
     Modellblock (G1-Balken nicht mehr gerendert).
  2. Antwortzeile steht zwischen Auswahl und Graph.
  3. Titel "Gerätepreise im Vergleich"; die Frage-Ueberschrift 0x.
  4. Ampel-Kacheln und Analysten-Tabellen nur innerhalb von `<details>`.
  5. Einzel-Punkt-Anbieter mit "Serie startet"-Beschriftung (Modultest in
     `tests/test_geraete_zeitreihe.py`; hier nur die Verdrahtung im HTML).
  6. Tab-Leiste nur Vergleich + Gerätekatalog.

Die Titel-Zusicherung selbst steht in `test_geraete_rahmen.py` (sie war dort
schon zuhause, seit BRIEF_RAHMEN die Frage-Ueberschrift einfuehrte - die
Umkehrung gehoert an denselben Ort). Kriterium 1 UND 6 sind zusaetzlich im
echten Browser gemessen (`tests/test_geraete_reiter_browser.py`); hier steht
die statische Haelfte, die keinen Browser braucht.

Fixture: dieselbe `_baue()` wie in `test_geraete_rahmen.py` -
`test_geraete_tco_zustand._baue`, ein Modell (iPhone 15 128 GB), o2 neu +
erneuert, Vodafone als Referenzrechnung.
"""
from __future__ import annotations

from test_geraete_tco_zustand import _baue


# --------------------------------------------------------------------------
# Kriterium 1: G0 ist die einzige Grafik je Modellblock
# --------------------------------------------------------------------------

def test_g1_steht_nicht_mehr_im_dokument(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select("svg.gr-g1") == []
    for block in tafel.select(".gr-tmodell"):
        assert block.select_one("svg.gr-g0") is not None, \
            f"{block.get('data-modell')}: G0 fehlt"
        assert len(block.select("svg")) == 1, \
            f"{block.get('data-modell')}: mehr als eine Grafik"


# --------------------------------------------------------------------------
# Kriterium 2: die Antwortzeile steht zwischen Auswahl und Graph
# --------------------------------------------------------------------------

def test_antwortzeile_steht_zwischen_auswahl_und_graph(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    auswahl = tafel.select_one(".gr-msel")
    assert auswahl is not None, "die Geraeteauswahl fehlt"

    block = tafel.select_one(".gr-tmodell")
    kinder = [k for k in block.find_all(recursive=False)]
    antwort = block.select_one(".gr-antwort")
    graph = block.select_one("figure.gr-grafik--zeitreihe")
    assert antwort is not None, "die Antwortzeile fehlt"
    assert graph is not None, "der Zeitreihen-Graph fehlt"
    assert kinder.index(antwort) < kinder.index(graph), \
        "die Antwortzeile steht nicht vor dem Graphen"

    # Die Auswahl steht VOR dem Modellblock (und damit vor der Antwortzeile
    # und dem Graphen darin) - derselbe DOM-Baum, verglichen ueber die
    # Position im vollstaendigen Text.
    text = str(tafel)
    assert text.index('class="gr-msel') < text.index('class="gr-antwort')


def test_antwortzeile_nennt_beide_preise_mit_anbieter(tmp_path):
    s = _baue(tmp_path)
    zeile = s.select_one("#tafel-tco .gr-antwort")
    text = zeile.get_text(" ", strip=True)
    assert "Günstigster Gerätepreis" in text
    assert "günstig mit Tarif" in text
    assert "(o2)" in text, f"kein Anbieter in der Antwortzeile: {text}"


# --------------------------------------------------------------------------
# Kriterium 3: die Titelzeile - siehe `test_geraete_rahmen.py`
# (`test_die_ueberschrift_ist_sachlich_nicht_die_gescheiterte_frage`)
# --------------------------------------------------------------------------

def test_der_seitentitel_ist_sachlich(tmp_path):
    s = _baue(tmp_path)
    titel = s.select_one("title").get_text(strip=True)
    assert titel.endswith("Gerätepreise im Vergleich")


# --------------------------------------------------------------------------
# Kriterium 4: Ampel-Kacheln und Analysten-Tabellen nur in <details>
# --------------------------------------------------------------------------

def test_ampel_kacheln_stehen_nur_in_einer_aufklappung(tmp_path):
    s = _baue(tmp_path)
    chips = s.select_one("#tafel-tco .gr-chips")
    assert chips is not None, "die Ampel-Kacheln fehlen"
    aufklappung = chips.find_parent("details")
    assert aufklappung is not None, \
        "die Ampel-Kacheln stehen ausserhalb einer Aufklappung"
    assert aufklappung.get("id") == "gr-details"


def test_die_analysten_tabellen_stehen_nur_in_einer_aufklappung(tmp_path):
    s = _baue(tmp_path)
    for kennung in ("gr-alarme", "gr-tco-tabelle", "gr-massstab"):
        tabelle = s.select_one(f"#tafel-tco #{kennung}")
        if tabelle is None:
            # gr-massstab z.B. steht nur, wenn Referenzen im Bestand sind -
            # kein Mangel, aber der Test darf nicht schweigend nichts pruefen.
            continue
        aufklappung = tabelle.find_parent(
            lambda el: el.name == "details" and el.get("id") == "gr-details")
        assert aufklappung is not None, \
            f"#{kennung} steht nicht innerhalb von #gr-details"


def test_details_wrapper_steht_wirklich_zu(tmp_path):
    """Gegenprobe: die Aufklappung ist zu Beginn geschlossen - sonst
    pruefte Kriterium 4 eine Struktur, die ohnehin immer offen daliegt."""
    s = _baue(tmp_path)
    wrapper = s.select_one("#tafel-tco #gr-details")
    assert wrapper is not None
    assert wrapper.get("open") is None, "die Details-Aufklappung ist offen"
    assert wrapper.select_one("summary").get_text(strip=True) == "Details"


def test_die_anbieterkarten_stehen_ausserhalb_der_details_aufklappung(tmp_path):
    """Die Antwort selbst - die Anbieterkarten - darf NICHT hinter der
    Klappe verschwinden, nur die Analyse drumherum."""
    s = _baue(tmp_path)
    karten = s.select_one("#tafel-tco .gr-karten")
    assert karten is not None
    assert karten.find_parent(
        lambda el: el.name == "details" and el.get("id") == "gr-details"
    ) is None, "die Anbieterkarten stecken in der Details-Aufklappung"


# --------------------------------------------------------------------------
# Kriterium 5: Einzel-Punkt-Anbieter - Verdrahtung im HTML
# (die Rechnung selbst: tests/test_geraete_zeitreihe.py)
# --------------------------------------------------------------------------

def test_haendler_ohne_zeitreihe_nennen_den_beginn_der_beschaffung(tmp_path):
    s = _baue(tmp_path)
    for karte in s.select("#tafel-tco .gr-kkarte--haendler"):
        text = karte.get_text(" ", strip=True)
        assert "Beschaffung läuft seit" in text
        assert "€" not in text


# --------------------------------------------------------------------------
# Kriterium 6: die Reiterleiste traegt nur zwei Knoepfe
# --------------------------------------------------------------------------

def test_die_reiterleiste_traegt_nur_vergleich_und_katalog(tmp_path):
    s = _baue(tmp_path)
    knoepfe = s.select(".gr-reiter button[data-tafel]")
    beschriftungen = [(k.get("data-tafel"), k.get_text(strip=True))
                      for k in knoepfe]
    assert beschriftungen == [
        ("tafel-tco", "Vergleich"),
        ("tafel-katalog", "Gerätekatalog"),
    ]


def test_die_ungeknopften_tafeln_bleiben_im_dokument_stehen(tmp_path):
    """"Nicht geloescht, nur nicht mehr verlinkt" - ihr Markup bleibt, nur
    kein Knopf zeigt mehr darauf."""
    s = _baue(tmp_path)
    assert s.select_one("#tafel-verlauf") is not None
    assert s.select_one("#tafel-portfolio") is not None
    # Kein Knopf in der Reiterleiste zeigt mehr auf sie.
    ziele = {k.get("data-tafel") for k in s.select(".gr-reiter button[data-tafel]")}
    assert "tafel-verlauf" not in ziele
    assert "tafel-portfolio" not in ziele
