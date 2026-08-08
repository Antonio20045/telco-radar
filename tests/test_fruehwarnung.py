"""Frühwarn-Board (report/fruehwarnung.py).

Die Methode heisst "Indicators & Warnings", und ihr Wert steckt in einem
einzigen Wort: VORHER. Ein Indikator, der nach dem Ereignis formuliert wird,
ist keine Warnung, sondern eine Erklaerung. Deshalb steht hier ein
Wortabgleich gegen eine Konfigurationsdatei und kein Modell - ein Modell
gaebe jede Woche eine andere Auslegung derselben Frage, und damit genau das
Gegenteil eines Fruehwarnsystems.
"""
from __future__ import annotations

from pathlib import Path

from telco_radar.report import fruehwarnung as F

WURZEL = Path(__file__).resolve().parents[1]


def _h(titel, operator="", summary=""):
    return {"schlagzeile": titel, "title": titel, "summary": summary,
            "operator": operator, "url": "https://x.test/1"}


def _wochen(*ausgaben):
    """(datum, [highlights]) -> die Struktur, die render_site fuehrt."""
    return [{"date": d, "highlights": hs} for d, hs in ausgaben]


def _konfig(tmp_path, text):
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "fruehwarnung.yaml").write_text(text,
                                                           encoding="utf-8")
    return tmp_path


EINE_FRAGE = """
fragen:
  - frage: "Kippt die Preisuntergrenze?"
    warum: "Test."
    indikatoren:
      - name: "Unlimited unter 35 Euro"
        stichworte: ["unlimited", "flatrate"]
        marken: ["Telekom", "O2"]
      - name: "Anschlusspreis fällt weg"
        stichworte: ["anschlusspreis"]
fenster_ausgaben: 3
"""


def test_treffer_in_der_aktuellen_ausgabe_ist_aktiv(tmp_path):
    root = _konfig(tmp_path, EINE_FRAGE)
    v = F.aufbereiten(_wochen(
        ("2026-08-08", [_h("Telekom bringt Unlimited-Flat", "Deutsche Telekom")])),
        root)
    ind = v["fragen"][0]["indikatoren"][0]
    assert ind["zustand"] == F.AKTIV
    assert ind["belege"][0]["datum"] == "2026-08-08"


def test_treffer_nur_in_einer_frueheren_ausgabe_ist_beobachtet(tmp_path):
    root = _konfig(tmp_path, EINE_FRAGE)
    v = F.aufbereiten(_wochen(
        ("2026-08-08", [_h("Etwas ganz anderes")]),
        ("2026-08-05", [_h("Telekom bringt Unlimited-Flat", "Deutsche Telekom")])),
        root)
    assert v["fragen"][0]["indikatoren"][0]["zustand"] == F.BEOBACHTET


def test_ausserhalb_des_fensters_ist_ruhend(tmp_path):
    root = _konfig(tmp_path, EINE_FRAGE)
    v = F.aufbereiten(_wochen(
        ("2026-08-08", [_h("x")]), ("2026-08-07", [_h("x")]),
        ("2026-08-06", [_h("x")]),
        ("2026-07-01", [_h("Telekom Unlimited-Flat", "Deutsche Telekom")])),
        root)
    assert v["fragen"][0]["indikatoren"][0]["zustand"] == F.RUHEND


def test_ruhende_fragen_bleiben_stehen(tmp_path):
    """Eine Frage, zu der seit Wochen nichts kommt, ist beantwortet: es
    passiert gerade nichts. Sie wegzulassen liesse das Board jede Woche
    gleich voll aussehen."""
    root = _konfig(tmp_path, EINE_FRAGE)
    v = F.aufbereiten(_wochen(("2026-08-08", [_h("Etwas anderes")])), root)
    assert len(v["fragen"]) == 1
    assert v["fragen"][0]["zustand"] == F.RUHEND
    assert v["n_aktiv"] == 0


def test_aktive_fragen_stehen_oben(tmp_path):
    # Die zweite Frage muss VOR `fenster_ausgaben` stehen - danach ist die
    # Liste `fragen` beendet und ein weiterer Eintrag waere ungueltiges YAML.
    root = _konfig(tmp_path, EINE_FRAGE.replace(
        "fenster_ausgaben: 3",
        '  - frage: "Zweite Frage?"\n'
        '    warum: "Test."\n'
        '    indikatoren:\n'
        '      - name: "Nie"\n'
        '        stichworte: ["kommtnichtvor"]\n'
        "fenster_ausgaben: 3"))
    v = F.aufbereiten(_wochen(
        ("2026-08-08", [_h("Telekom Unlimited-Flat", "Deutsche Telekom")])),
        root)
    assert v["fragen"][0]["zustand"] == F.AKTIV
    assert v["fragen"][-1]["zustand"] == F.RUHEND


# ------------------------------------------------------------- Trennschaerfe

def test_die_marke_schraenkt_ein(tmp_path):
    """Ein Indikator ohne `marken` feuert bei jedem Absender - fuer
    Preisfragen ist das falsch."""
    root = _konfig(tmp_path, EINE_FRAGE)
    v = F.aufbereiten(_wochen(
        ("2026-08-08", [_h("Jio bringt Unlimited-Flat", "Reliance Jio")])),
        root)
    assert v["fragen"][0]["indikatoren"][0]["zustand"] == F.RUHEND


def test_die_marke_darf_auch_im_titel_stehen(tmp_path):
    """Eine Fachpressemeldung ueber die Telekom traegt den Namen oft nur im
    Titel, nicht im Absenderfeld."""
    root = _konfig(tmp_path, EINE_FRAGE)
    v = F.aufbereiten(_wochen(
        ("2026-08-08", [_h("Telekom bringt Unlimited-Flat", "teltarif")])),
        root)
    assert v["fragen"][0]["indikatoren"][0]["zustand"] == F.AKTIV


def test_wortgrenzen_gelten(tmp_path):
    """Ohne sie faende "d2d" jedes "ad2do" und "O2" jedes "CO2"."""
    root = _konfig(tmp_path, """
fragen:
  - frage: "Test?"
    indikatoren:
      - name: "D2D"
        stichworte: ["d2d"]
""")
    v = F.aufbereiten(_wochen(
        ("2026-08-08", [_h("Neue CO2-Bilanz und ad2do-Studie")])), root)
    assert v["fragen"][0]["indikatoren"][0]["zustand"] == F.RUHEND


def test_ohne_konfiguration_kein_board(tmp_path):
    v = F.aufbereiten(_wochen(("2026-08-08", [_h("x")])), tmp_path)
    assert v["aktiv"] is False


def test_ohne_ausgaben_kein_board(tmp_path):
    assert F.aufbereiten([], _konfig(tmp_path, EINE_FRAGE))["aktiv"] is False


# ------------------------------------------------------------ ausgelieferte

def test_die_ausgelieferten_fragen_sind_falsifizierbar():
    """Ein Indikator muss aus Woertern bestehen, die in einer Meldung stehen
    oder nicht stehen. "Der Markt konsolidiert sich" ist keiner."""
    fragen, fenster = F.lade_fragen(WURZEL)
    assert 4 <= len(fragen) <= 6, "vier bis fuenf Kernfragen, nicht zwanzig"
    assert fenster >= 2
    for f in fragen:
        assert f.frage.endswith("?"), f.frage
        assert f.warum, f"{f.frage}: ohne Begruendung ist es eine Behauptung"
        assert f.indikatoren, f.frage
        for i in f.indikatoren:
            assert i.stichworte, f"{i.name}: nicht falsifizierbar"


def test_belege_werden_begrenzt(tmp_path):
    """Mehr als zwei macht aus dem Board eine zweite Meldungsliste."""
    root = _konfig(tmp_path, EINE_FRAGE)
    viele = [_h(f"Telekom Unlimited-Flat {i}", "Deutsche Telekom")
             for i in range(9)]
    v = F.aufbereiten(_wochen(("2026-08-08", viele)), root)
    ind = v["fragen"][0]["indikatoren"][0]
    assert ind["n_jetzt"] == 9
    assert len(ind["belege"]) == F.MAX_BELEGE
