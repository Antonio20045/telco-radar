"""E9 (Strategie 2026-08-27, B7/§2): zehn Betreiber lieferten zusammen 105
neue Meldungen und 0 bewertete ueber 23 Laeufe (scripts/quellen_trefferquote.py) -
Analystentoken fuer Meldungen, die nie eine Chance auf den Bericht hatten.

Ihre crawlbaren `sources`-Eintraege sind am 27.08.2026 aus
`config/watchlist.yaml` entfernt worden. Die Betreiber selbst bleiben stehen
(Konvention: ein Operator OHNE `sources` gilt als bot-geschuetzt/Referenz und
wird ueber das Fachpresse-Tagging seiner Aliase mitabgedeckt, CLAUDE.md §4) -
geloescht wurde nur ihr Eintrag im Quellenbestand, nicht ihre Kenntnis. Eine
Wiederaufnahme bleibt jederzeit moeglich, wenn sich die Trefferquote aendert.
"""
from __future__ import annotations

from pathlib import Path

from telco_radar.config import load_config

REPO = Path(__file__).resolve().parents[1]

# Name -> vorher gemessene neue Meldungen (Strategie 2026-08-27, §2 E9).
BALLASTQUELLEN = {
    "PLDT": 31,
    "AIS": 13,
    "Turk Telekom": 10,
    "du": 9,
    "Orange MEA": 9,
    "MTN Group": 9,
    "Airtel Africa": 7,
    "Liquid Intelligent Technologies": 6,
    "Chunghwa Telecom": 6,
    "Swisscom": 5,
}


def _operatoren_nach_name() -> dict:
    cfg = load_config(REPO)
    op = {o.name: o for o in cfg.operators}
    # Der Lookup muss wirklich treffen - sonst prueft der Test unten nichts
    # (dieselbe Falle wie beim Faden-Test in CLAUDE.md §6: ein Lookup ins
    # Leere ist gruen und beweist nichts).
    assert len(op) == len(cfg.operators), "doppelte Betreibernamen in der Watchlist"
    return op


def test_die_ballastquellen_operatoren_stehen_noch_in_der_watchlist():
    """Geloescht wird der Quelleneintrag, nicht das Wissen um den Betreiber -
    ein Leser der Quellenseite soll weiterhin sehen, dass er beobachtet
    wurde, nur eben nicht mehr abgefragt wird."""
    operatoren = _operatoren_nach_name()
    fehlend = [name for name in BALLASTQUELLEN if name not in operatoren]
    assert not fehlend, f"aus der Watchlist verschwunden statt nur entkoppelt: {fehlend}"


def test_die_ballastquellen_operatoren_haben_keine_crawlbaren_quellen_mehr():
    """Die eigentliche Aenderung: kein Lauf fragt diese zehn Betreiber mehr
    ab. `sources` OHNE Eintrag ist die Konvention fuer "bot-geschuetzt /
    ueber Fachpresse-Tagging abgedeckt" (CLAUDE.md §4)."""
    operatoren = _operatoren_nach_name()
    noch_crawlbar = {name: len(operatoren[name].crawled_sources)
                     for name in BALLASTQUELLEN}
    uebrig = {name: n for name, n in noch_crawlbar.items() if n}
    assert not uebrig, f"haben noch crawlbare Quellen: {uebrig}"


def test_die_ballastquellen_operatoren_behalten_ihre_aliase():
    """Ohne eigene Quelle laeuft ein Betreiber nur noch ueber das
    Fachpresse-Tagging seiner Aliase - wer die Aliase mit der Quelle
    mitgeloescht haette, machte den Betreiber unsichtbar statt nur
    unabgefragt. Nachgezaehlt nur dort, wo vorher welche standen."""
    operatoren = _operatoren_nach_name()
    vorher_mit_aliasen = {"MTN Group": ["MTN"], "du": ["EITC"],
                          "AIS": ["Advanced Info Service"],
                          "Orange MEA": ["Orange Egypt", "Orange Jordan"],
                          "Liquid Intelligent Technologies": ["Liquid Telecom"],
                          "Chunghwa Telecom": ["Chunghwa"]}
    for name, erwartet in vorher_mit_aliasen.items():
        assert set(erwartet) <= set(operatoren[name].aliases), name
