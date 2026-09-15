"""SQ67 (15.09.2026): drei Stellen der Geraeteseite, die fuer die Zielgruppe
(Vodafone-Device-Einkaeufer, keine Endkunden) klarer werden.

  1. Das Klapplabel nennt die HANDLUNG und die Zahl - "Anbieterkarten (22)"
     war ein Etikett ueber einem Bedienelement, dessen Wirkung niemand
     beschrieb.

Alle Tests dieser Datei sind NEU - rot-vor gilt nicht, der alte Stand kannte
keines der Merkmale. Dieselbe Fixture wie `test_geraete_rahmen` (o2 neu und
erneuert, Vodafone als Referenzrechnung, optional 1&1 ohne Geraetepreis):
Sie traegt beide Kartenarten MIT zwei Preisen (Barpreis- und
Finanzierungszweig) plus eine Karte ohne Geraetepreis als Gegenprobe.
"""
from __future__ import annotations

import re

from test_geraete_tco_zustand import _baue


# --------------------------------------------------------------------------
# 1. Das Klapplabel
# --------------------------------------------------------------------------

def test_das_klapplabel_nennt_handlung_und_zahl(tmp_path):
    """Jede Kartenklappe traegt "<N> Anbieterangebote anzeigen" - die Zahl
    und ein Aktionswort, und beides IM TEXTKNOTEN (das Abnahmekriterium
    greift die Zeile per grep am Quelltext; ein eingeschlossenes Tag
    zwischen Zahl und Wort wuerde ihn schweigen lassen)."""
    s = _baue(tmp_path)
    klappen = s.select("#tafel-tco details.gr-karten-auf")
    assert klappen, "der Test prueft nichts ohne Kartenklappe"
    for klappe in klappen:
        summary = klappe.select_one("summary")
        # Der RUMPF des summary (reiner Text, keine Kind-Elemente mehr,
        # seit die Zahl nackt steht).
        text = re.sub(r"\s+", " ", summary.get_text(" ", strip=True))
        treffer = re.search(r"(\d+)\s+Anbieter[a-zäöü]* anzeigen", text)
        assert treffer, f"Label ohne Zahl und Handlung: {text!r}"
        karten = klappe.select(".gr-kkarte")
        assert int(treffer.group(1)) == len(karten), (
            f"{text!r} zaehlt {treffer.group(1)}, die Klappe traegt "
            f"{len(karten)} Karten")
        # Der Wortlaut steht auch im Quelltext der Seite selbst - der
        # grep-Beweis des Auftrags laeuft gegen genau diese Form.
        assert "Anbieterangebote anzeigen" in str(summary)


def test_app_js_baut_dasselbe_klapplabel_nach():
    """Der Labeltext steht ZWEIMAL im Code (Jinja-Template statisch, app.js
    fuer den gefilterten Zustand "5 von 22 ...") - laufen die auseinander,
    verschwindet das Aktionswort beim ersten Filterklick. Dieselbe Regel
    wie beim Uebersetzungs-Link (CLAUDE.md Sektion 5)."""
    from pathlib import Path
    app_js = (Path(__file__).resolve().parents[1]
              / "src/telco_radar/report/templates/app.js").read_text(
                  encoding="utf-8")
    assert "' Anbieterangebote anzeigen'" in app_js, \
        "app.js setzt den Klapplabel-Wortlaut nicht nach"
