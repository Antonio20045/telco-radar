"""Issue 125: ohne Händlerreihe bleibt die Ausgabe gleich.

Bis origin/main stand das Namensetikett des teuersten Anbieters genau an
seiner Kurve (y = Endpunkt + 4), die folgenden rückten nur nach unten.
Gerendert mit dem echten Bestand unterscheiden sich 9 zr-Paare und 42
zf-Fenster ohne jede Händlerreihe, z. B. fairphone-6-256 xs/24 (1&1 315.8 -> 274.2).
"""

import re

from telco_radar.report import geraete_zeitreihe as gz

SERIEN = {
    "Telekom": [("2026-11-01", 1000.0), ("2026-11-02", 1000.0)],
    "Vodafone": [("2026-11-01", 998.0), ("2026-11-02", 998.0)],
    "o2": [("2026-11-01", 996.0), ("2026-11-02", 996.0)],
    "congstar": [("2026-11-01", 700.0), ("2026-11-02", 700.0)],
}


def _endpunkt_y(svg: str, anbieter: str) -> float:
    muster = (
        r"<circle class='gr-zr-punkt' cx='[\d.]+' cy='([\d.]+)'[^>]*"
        rf"data-anb='{anbieter}'"
    )
    cys = re.findall(muster, svg)
    return float(cys[-1])


def _etikett_y(svg: str, anbieter: str) -> float:
    m = re.search(
        rf"<text class='gr-zr-name' x='[\d.]+' y='([\d.]+)'[^>]*>{anbieter}[<]", svg
    )
    assert m, f"kein Etikett für {anbieter}"
    return float(m.group(1))


def test_oberstes_etikett_bleibt_an_seiner_kurve_ohne_haendler():
    for breit in (True, False):
        svg = gz._svg(SERIEN, breit, {}, {}, laufzeit=24)
        soll = _endpunkt_y(svg, "Telekom") + 4
        ist = _etikett_y(svg, "Telekom")
        assert ist == soll, (
            f"breit={breit}: Telekom-Etikett y={ist}, bis main {soll} - "
            "ohne Händlerreihe hat sich die Grafik geändert"
        )
