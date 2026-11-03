"""Die Kopfzeile der Geräteseite nennt den Vergleichsgegenstand.

"teurer" braucht ein Gegenüber: gerechnet wird gegen den günstigsten
Wettbewerber (`geraete_teurer.mit_tarif` und `einzelgeraet`), nie gegen
einen Durchschnitt oder gegen Vodafone selbst.
"""

from __future__ import annotations

import test_geraete_seite
from bs4 import BeautifulSoup

GEGENSTAND = "als beim günstigsten Wettbewerber"


def _kopf(tmp_path):
    site = test_geraete_seite._baue(tmp_path)
    s = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    return s.select_one("h1.gx-held")


def test_beide_saetze_nennen_den_vergleichsgegenstand(tmp_path):
    kopf = _kopf(tmp_path)
    for art in ("tarif", "geraet"):
        satz = " ".join(
            kopf.select_one(f".gx-art--{art} span").get_text(" ", strip=True).split()
        )
        assert satz.endswith(f"teurer {GEGENSTAND}."), satz


def test_gegenprobe_der_gegenstand_steht_nur_in_den_zwei_saetzen(tmp_path):
    kopf = _kopf(tmp_path)
    text = " ".join(kopf.get_text(" ", strip=True).split())
    assert text.count(GEGENSTAND) == 2
