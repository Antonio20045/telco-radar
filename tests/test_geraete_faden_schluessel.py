"""P4 SCHRITT 2c (STRATEGIE_GERAETE_V3, 18.09.2026): EINE Modell-Menge
statt drei - der rote Faden zwischen den Reitern.

Die Sprünge zwischen Katalog, Radar und Zeitreihe sind mit dem Neuentwurf
der Geräteseite (29.09.2026, eine Kosten-Rangliste ohne Reiter) gefallen,
mit ihnen die Seitentests dieser Datei. Geblieben ist die Einheit, die
`geraete_view.katalog_modellzeilen` weiter rechnet: `zr` ist fail-closed.
"""
from __future__ import annotations

import json

import pytest

from test_geraete_zeitreihe_ansicht import _baue as _baue_zeitreihe


def test_zr_feld_ohne_erlaubnis_bleibt_false(tmp_path):
    """Unit auf `katalog_modellzeilen`: ohne `zr_erlaubt` (None oder
    leer) ist `zr` ueberall False - fail-closed. Mit erlaubt nur True,
    wo das Modell wirklich drinsteht (gelesen, nie nachgerechnet)."""
    from telco_radar.geraete_config import lade_katalog
    from telco_radar.report.geraete_view import katalog_modellzeilen

    root, _ = _baue_zeitreihe(tmp_path)
    roh = json.loads((root / "data" / "state" / "geraete_db.json")
                     .read_text(encoding="utf-8"))
    eintraege = roh["listungen"]
    katalog = lade_katalog(root)

    ohne = katalog_modellzeilen(eintraege, katalog)
    assert ohne and not any(m["zr"] for m in ohne), \
        "zr=True ohne zr_erlaubt - der Link stünde blind"

    schluessel = {m["schluessel"] for m in ohne}
    teil = schluessel - {"google-pixel-11-128"}
    mit = katalog_modellzeilen(eintraege, katalog, zr_erlaubt=
                               {k: ["xs"] for k in teil})
    wahr = {m["schluessel"] for m in mit if m["zr"]}
    assert wahr == teil, \
        f"zr trifft nicht die uebergebene Menge: {wahr} != {teil}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
