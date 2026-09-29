"""BRIEF_FADEN (05.09.2026, Senecas Freigabe): die Geraeteseite auf EINE
Frage reduziert - "Was kostet dieses Gerät?".

Seit dem Neuentwurf vom 29.09.2026 (eine Kosten-Rangliste, keine Reiter,
kein Graph) bleibt von den sechs Abnahmekriterien nur die sachliche
Titelzeile; die übrigen prüften Markup, das es nicht mehr gibt. Die Seite
selbst halten `tests/test_geraete_kosten.py` und
`tests/test_geraete_kosten_browser.py` fest.

Fixture: `test_geraete_tco_zustand._baue`, ein Modell (iPhone 15 128 GB),
o2 neu + erneuert, Vodafone als Referenzrechnung.
"""
from __future__ import annotations

from test_geraete_tco_zustand import _baue


def test_der_seitentitel_ist_sachlich(tmp_path):
    s = _baue(tmp_path)
    titel = s.select_one("title").get_text(strip=True)
    assert titel.endswith("· Gerätepreise")
