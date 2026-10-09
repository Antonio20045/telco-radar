"""Der Übersetzungsspeicher schreibt keine E-Mail-Adresse nach ``data/``.

Lauf 117 (09.10.2026): eine übersetzte Pressemeldung enthielt die
Kontaktadresse der Pressestelle, der Leck-Wächter hielt den Bot-Commit an,
und der ganze Bericht ging verloren.
"""

from __future__ import annotations

import sys
from pathlib import Path

from telco_radar.uebersetzung.store import Uebersetzung, UebersetzungsStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_speichern_entfernt_adressen(tmp_path):
    import waechter_leck

    pfad = tmp_path / "uebersetzungen.jsonl"
    store = UebersetzungsStore(pfad)
    store.add(
        Uebersetzung(
            item_id="a1",
            quell_hash="h",
            titel_de="Neuer Tarif",
            absaetze=["Pressekontakt: presse.team@example-telco.com, Tel. 0211"],
        )
    )
    store.speichern()
    roh = pfad.read_bytes()
    assert not waechter_leck.ADRESSE.search(roh)
    geladen = UebersetzungsStore(pfad).get("a1")
    assert geladen is not None
    assert geladen.absaetze == ["Pressekontakt: [E-Mail-Adresse entfernt], Tel. 0211"]
