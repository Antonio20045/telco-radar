"""SQ67 (15.09.2026): drei Stellen der Geraeteseite, die fuer die Zielgruppe
(Vodafone-Device-Einkaeufer, keine Endkunden) klarer werden.

  1. Das Klapplabel nennt die HANDLUNG und die Zahl - "Anbieterkarten (22)"
     war ein Etikett ueber einem Bedienelement, dessen Wirkung niemand
     beschrieb.
  2. Die Paradox-Zeile: "Gerät 999 € / mit Tarif 941 €" ohne Erklaerung ist
     ein Widerspruch der Karte gegen sich selbst (die mit-Tarif-Zahl kann
     hoeher wie niedriger liegen). Ein kurzer Satz direkt darunter, mit dem
     Zeitraum, der die Zahl traegt.

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


# --------------------------------------------------------------------------
# 2. Die Paradox-Zeile
# --------------------------------------------------------------------------

def test_jede_karte_mit_zwei_preisen_traegt_die_paradox_zeile(tmp_path):
    """Eine Karte, die Geraetepreis UND mit-Tarif-Zahl zeigt, erklaert in
    einem Satz direkt darunter, was die zweite Zahl enthaelt - mit dem
    Zeitraum, der sie traegt (24 Monate am TCO-24 der Fixture)."""
    s = _baue(tmp_path, eins_und_eins=True)
    karten = s.select("#tafel-tco .gr-kkarte")
    assert karten, "der Test prueft nichts ohne Karte"
    mit_tarif = 0
    for karte in karten:
        if "mit Tarif:" not in karte.get_text():
            continue
        mit_tarif += 1
        paradox = karte.select_one(".gr-kk-paradox")
        assert paradox is not None, (
            f"Karte {karte.get('data-anbieter')}: zwei Preise ohne "
            "Erklaerzeile")
        text = re.sub(r"\s+", " ", paradox.get_text(" ", strip=True))
        assert "Gerät" in text and "Tarif" in text, text
        assert "24 Monate" in text or "24 Monatsraten" in text, (
            f"Erklaerzeile ohne Zeitraum: {text!r}")
        # Die Zeile steht DIREKT unter den zwei Preisen: nach "mit Tarif:",
        # vor der Ø-Zeile - nicht erst im Rechenweg-Aufklapper.
        html = str(karte)
        assert html.index("mit Tarif:") < html.index("gr-kk-paradox") \
            < html.index("gr-kk-omonat"), (
            f"Karte {karte.get('data-anbieter')}: Paradox-Zeile steht nicht "
            "zwischen Preis- und Ø-Zeile")
        # Sichtbar ohne weiteren Klick: kein EIGENER <details>-Block zwischen
        # Kartengrenze und Zeile (die Kartenklappe selbst ist der Ort, an dem
        # jede Karte erst sichtbar wird - das ist ihre Bedingung, nicht eine
        # zweite).
        for ahne in paradox.parents:
            if ahne.name == "details":
                assert "gr-karten-auf" in (ahne.get("class") or []), (
                    "die Paradox-Zeile steckt in einer weiteren Aufklappung")
    # Gegenprobe gegen die Lookup-Falle: ohne eine Karte mit zwei Preisen
    # pruefte der Test nichts. Die 1&1-Karte der Fixture hat KEINEN
    # Geraetepreis und damit keine "mit Tarif:"-Zeile - sie bleibt hier
    # bewusst aussen vor.
    assert mit_tarif > 0, "die Fixture traegt keine Karte mit zwei Preisen"


def test_die_paradox_zeile_nennt_den_zeitraum_ihres_labels(tmp_path):
    """Der Zeitraum in der Erklaerzeile ist der des TCO-Labels derselben
    Karte (`k.laufzeit`), keine feste 24 - sonst logen TCO-36-Karten ihre
    Erklaerzeile in die eigene Zukunft."""
    s = _baue(tmp_path)
    for karte in s.select("#tafel-tco .gr-kkarte"):
        label = karte.select_one(".gr-kk-zweit b")
        paradox = karte.select_one(".gr-kk-paradox")
        if label is None or paradox is None:
            continue
        treffer = re.search(r"TCO-(\d+)", label.get_text())
        assert treffer, label.get_text()
        fluss = re.sub(r"\s+", " ", paradox.get_text(" ", strip=True))
        assert f"{treffer.group(1)} Monate" in fluss \
            or f"{treffer.group(1)} Monatsraten" in fluss, (
            f"Karte {karte.get('data-anbieter')}: Label "
            f"{treffer.group(0)}, aber Erklaerzeile {fluss!r}")
