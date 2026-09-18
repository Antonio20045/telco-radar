"""PM-6 (P5 Auftrag 4): Fragmentwachstum messbar - Skript und Protokollzeile.

Warum dieser Test existiert (Premortem FM 3): das Zeitreihen-Fragment
waechst mit jedem Messtag, die Wachstumsrate war bis zum 17.09.2026 eine
Schaetzung ("~7 KB je Paar"), und die Deckel-Entscheidung vom 01.10.
braucht eine REPRODUZIERBARE Rechnung. Er prueft die Zaehlung der
Historie (idempotent), die Projektionsformel (Ceil ab dem letzten
Messtag) und den CLI-Bericht gegen eine kleine Fixture in tmp/ - echte
State-Dateien werden nie angefasst.

Hausregel: jede Funktion nimmt ihr Datum als Parameter (`heute=` bzw.
der Anker aus der Historie) - deshalb ist die gesamte Rechnung hier
deterministisch und zweimal identisch.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

from telco_radar.geraete_fragment import (
    GRENZE_BYTES,
    lies_historie,
    prognose,
    protokoll_zeile,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "geraete_fragment_wachstum.py"


def _lade_skript():
    """Das Skript als Modul - scripts/ ist kein Package, also per Pfad.

    Damit laeuft der Test gegen DIESEN Quelltext und nicht gegen eine
    Kopie der Formel (zwei Umsetzungen derselben Rechnung waeren zwei
    Zahlen - CLAUDE.md 6).
    """
    spec = importlib.util.spec_from_file_location("geraete_fragment_wachstum",
                                                  SCRIPT)
    modul = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modul)
    return modul


def _fixture(root: Path) -> None:
    """Drei Messtage zu je 10 Paaren (plus eine Dublette), 30k/500k Fragmente.

    30 Messpaare, 30.000 Bytes Zeitreihe -> exakt 1.000 B/Paar; Rate
    30/3 = 10 Paare/Messtag; Anker 2026-09-12. Jede Zahl dieser Fixture
    ist so gewaehlt, dass die Prognose im Kopf nachrechenbar ist.
    """
    zustand = root / "data" / "state"
    zustand.mkdir(parents=True)
    zeilen = []
    for tag in ("2026-09-10", "2026-09-11", "2026-09-12"):
        for nr in range(10):
            zeilen.append(json.dumps(
                {"id": f"buendel--anbieter--modell-{nr}", "datum": tag,
                 "gesamt": 100.0 + nr}))
    # Dieselbe (id, datum)-Zeile noch einmal: die Historie ersetzt beim
    # zweiten Lauf desselben Tages - die Zaehlung muss das nachbilden.
    zeilen.append(zeilen[0])
    (zustand / "geraete_tco_historie.jsonl").write_text(
        "\n".join(zeilen) + "\n", encoding="utf-8")
    site_daten = root / "site" / "data"
    site_daten.mkdir(parents=True)
    (site_daten / "geraete-zeitreihe.html").write_text(
        "x" * 30_000, encoding="utf-8")
    (site_daten / "geraete-buendel.html").write_text(
        "y" * 500_000, encoding="utf-8")


def test_historie_zaehlt_idempotent_und_je_messtag(tmp_path):
    _fixture(tmp_path)
    bestand = lies_historie(
        tmp_path / "data" / "state" / "geraete_tco_historie.jsonl")
    assert bestand.messtage == 3
    assert bestand.paare == 30            # die Dublette zaehlt nicht doppelt
    assert bestand.tage == ((date(2026, 9, 10), 10), (date(2026, 9, 11), 10),
                            (date(2026, 9, 12), 10))
    assert bestand.anker == date(2026, 9, 12)
    assert bestand.rate_je_messtag() == 10.0
    # Fehlt die Datei, ist das eine leere Messung und kein Fehler - der
    # erste Lauf ohne Buendel legt sie noch nicht an.
    assert lies_historie(tmp_path / "nix.jsonl").paare == 0


def test_rate_ist_unbestimmt_mit_einem_messtag(tmp_path):
    zustand = tmp_path / "data" / "state"
    zustand.mkdir(parents=True)
    (zustand / "geraete_tco_historie.jsonl").write_text(
        json.dumps({"id": "b--1", "datum": "2026-09-10"}) + "\n",
        encoding="utf-8")
    bestand = lies_historie(zustand / "geraete_tco_historie.jsonl")
    assert bestand.paare == 1
    assert bestand.rate_je_messtag() is None   # keine Rate aus einem Punkt


def test_prognose_formel_ceil_ab_anker():
    """Linear durch den Nullpunkt, CEIL zum naechsten Messtag, ab Anker.

    1.000 B/Paar, 30 Paare, 10 Paare/Messtag: die 5-MB-Grenze braucht
    5.000 Paare, also (5.000 - 30) / 10 = 497 Messtage - ein Resttag
    (z. B. 0,4) zaehlt als GANZER, denn halbe Laeufe gibt es nicht.
    """
    grenz_datum, tage, drueber = prognose(
        bytes_je_paar=1_000.0, paare=30, rate=10.0,
        grenze=5_000_000, anker=date(2026, 9, 12))
    assert (tage, drueber) == (497, False)
    assert grenz_datum == date(2026, 9, 12) + timedelta(days=497)
    assert grenz_datum == date(2028, 1, 22)
    # Bruchteile aufrunden: 34 Paare an der Grenze brauchen 0,4 -> 1 Tag.
    _, tage, drueber = prognose(1_000.0, 30, 10.0, 34_000, date(2026, 9, 12))
    assert (tage, drueber) == (1, False)
    # Ein Tag GENAU auf der Grenze gilt als gehalten, erst der naechste
    # ueberschreitet: 40 Paare = 40.000 B -> 1 Tag.
    _, tage, _ = prognose(1_000.0, 30, 10.0, 40_000, date(2026, 9, 12))
    assert tage == 1
    # Bereits ueberschritten: der Anker selbst, ohne Frist.
    grenz_datum, tage, drueber = prognose(
        1_000.0, 30, 10.0, 29_000, date(2026, 9, 12))
    assert (grenz_datum, tage, drueber) == (date(2026, 9, 12), 0, True)


def test_skript_rechnet_gegen_die_fixture(tmp_path, capsys):
    """Der CLI-Weg: Optionen auf die Fixture, Ausgabe mit den echten Zahlen.

    Die Grenze 34.000 B wird per --grenze-mb 0.0324 (33.973 B) gesetzt -
    sie liegt ueber den heutigen 30.000 B und unter 40.000 B, die Prognose
    muss deshalb den naechsten Messtag nennen. heute ist Parameter, nie
    date.today() (Hausregel, CLAUDE.md 6).
    """
    _fixture(tmp_path)
    modul = _lade_skript()
    rc = modul.main(["--root", str(tmp_path), "--heute", "2026-09-18",
                     "--grenze-mb", "0.0324"])
    assert rc == 0
    text = capsys.readouterr().out
    assert "Stand 2026-09-18" in text
    assert "2026-09-12" in text                    # Anker = letzter Messtag
    assert "10 Paare/Messtag" in text
    assert "30,000 B" in text                      # gemessene Fragmentgroesse
    assert "<-- GRENZE" in text
    assert "erreicht am 2026-09-13" in text        # Anker + 1 Messtag
    assert "NICHT gebaut" in text                  # der Deckel ist Empfehlung


def test_bericht_ist_deterministisch(tmp_path):
    """Zwei Aufrufe, byte-identisch - gzip mit mtime=0, heute als Parameter."""
    _fixture(tmp_path)
    modul = _lade_skript()
    erster = modul.bericht(tmp_path, heute=date(2026, 9, 18))
    zweiter = modul.bericht(tmp_path, heute=date(2026, 9, 18))
    assert erster == zweiter
    assert "5-MB-Grenze" in erster
    assert "erreicht am 2028-01-22" in erster      # 497 Messtage, s. Formeltest


def test_protokollzeile_nennt_die_drei_zahlen(tmp_path):
    """Die Pipeline-Zeile: Messtage, Messpaare, Fragment-KB - aus EINER
    Quelle wie das Skript (geraete_fragment.protokoll_zeile)."""
    _fixture(tmp_path)
    assert protokoll_zeile(tmp_path) == (
        "Fragmentgroesse: 3 Messtage, 30 Messpaare, 517 KB Fragmente")
    # Fragmente fehlen (erster Lauf vor dem ersten Render): die Messzahlen
    # stehen trotzdem, die Reihe reisst nicht - aber ohne Zahl kein Punkt.
    nur_state = tmp_path / "ohne_site"
    (nur_state / "data" / "state").mkdir(parents=True)
    (nur_state / "data" / "state" / "geraete_tco_historie.jsonl").write_text(
        json.dumps({"id": "b--1", "datum": "2026-09-10"}) + "\n",
        encoding="utf-8")
    assert protokoll_zeile(nur_state) == (
        "Fragmentgroesse: 1 Messtage, 1 Messpaare, "
        "kein Fragment auf Platt (Render laeuft nach diesem Schritt)")
    # Keine Historie: KEINE Zeile - 0/0/0 waere ein vorgetaeuschter
    # Messpunkt in der PM-6-Reihe.
    assert protokoll_zeile(tmp_path / "leer") is None


def test_grenze_gilt_je_fragment_nicht_als_summe(tmp_path):
    """Die 5 MB gelten JE Fragment - die Summe beider stand am 18.09.2026
    bereits bei 5,1 MB, eine Summengrenze waere bei der Entscheidung schon
    ueberschritten. Der Bericht muss beide Fragmente NENNBAR einzeln
    ausweisen (und nennt die Summe nur zusaetzlich). Bewusst KEIN Test
    gegen die echte site/: er wuerde am Prognosetag (20.09.2026) rot
    werden und damit die Deckel-Entscheidung vorwegnehmen, die dem
    01.10. vorbehalten ist - das ist der Unterschied zwischen messen
    und kippen.
    """
    _fixture(tmp_path)
    modul = _lade_skript()
    text = modul.bericht(tmp_path, heute=date(2026, 9, 18))
    assert GRENZE_BYTES == 5_000_000
    assert "geraete-zeitreihe.html" in text and "30,000 B" in text
    assert "geraete-buendel.html" in text and "500,000 B" in text
    assert "Summe" in text
    assert "530,000 B" in text
