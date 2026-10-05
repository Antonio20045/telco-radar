"""Ohne Bericht und ohne übergebene Zeit rechnet keine Seite gegen die Wanduhr."""

from __future__ import annotations

import json
from datetime import date

from telco_radar.newsletter.filters import baue_stichwort_index
from telco_radar.report.html import render_site

ZUKUNFT = "2999-01-01"


def test_ohne_bericht_ist_kein_beispiel_der_differenzierung_neu(tmp_path):
    zustand = tmp_path / "data" / "state"
    zustand.mkdir(parents=True)
    eintrag = {
        "id": "https://beispiel.de/ki-assistent",
        "theme": "ki",
        "operator": "Beispielnetz",
        "region": "de",
        "what": "Beispielnetz startet einen KI-Assistenten",
        "url": "https://beispiel.de/ki-assistent",
        "source": "beispiel.de",
        "first_seen": ZUKUNFT,
        "last_verified": ZUKUNFT,
        "status": "aktiv",
    }
    (zustand / "differentiation_db.json").write_text(
        json.dumps({"updated": ZUKUNFT, "entries": [eintrag]}), encoding="utf-8"
    )
    berichte = tmp_path / "data" / "reports"
    berichte.mkdir()

    render_site(tmp_path / "site", berichte, cfg=None)

    seite = (tmp_path / "site" / "differenzierung.html").read_text(encoding="utf-8")
    assert "Beispielnetz startet einen KI-Assistenten" in seite
    assert 'class="dz-new"' not in seite


def test_ein_leeres_archiv_hat_keinen_stand(tmp_path):
    """Ohne Bericht gibt es keinen Datenstand; die Wanduhr ersetzt ihn nicht."""
    index = baue_stichwort_index(tmp_path, tage=30)
    assert index["stand"] is None
    assert index["meldungen"] == 0
    assert (
        baue_stichwort_index(tmp_path, tage=30, heute=date(2026, 8, 11))["stand"]
        == "2026-08-11"
    )
