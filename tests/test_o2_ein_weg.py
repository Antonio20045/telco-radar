"""o2 hat einen Preisweg: den Adapter (Stand 21.11.2026).

Befund am Nachtstand 21.11.2026 (Gerätelauf 44858465074, Klick-Lauf 44840854026) und
einem lokalen Adapterlauf am selben Tag: der Klick-Lauf brauchte 24.700 s Jobzeit für
523 Kombinationen (ein Job gestört, 224 Seiten überfällig); der Adapter liest alle
Katalogbündel (72 Geräte) mit 209 Abrufen in 545 s. Jede Klick-Messung mit
Adapter-Gegenstück nennt dieselben Werte; die übrigen liefert der Adapter seit diesem
Stand selbst oder sie waren falsch (erneuerte Seite als Neuware,
``tests/test_klickliste_auto_zustand.py``). Seitdem steht o2 nicht mehr in der
Klick-Tagesdatei und trägt ``erfassung: adapter``.
"""

from __future__ import annotations

from pathlib import Path

from telco_radar.collect.geraete.klickziele import geplante_anbieter
from telco_radar.geraete_config import lade_quellen

WURZEL = Path(__file__).resolve().parents[1]


def test_o2_misst_nur_der_adapter():
    o2 = lade_quellen(WURZEL).nach_name("o2")
    assert (o2.erfassung, o2.methode) == ("adapter", "o2_katalog")


def test_keine_o2_seite_im_klick_tageslauf():
    text = (WURZEL / "config" / "klick_tageslauf.yaml").read_text(encoding="utf-8")
    assert "o2online.de" not in text
    assert "o2" not in geplante_anbieter(WURZEL)


def test_gegenprobe_die_anderen_klick_anbieter_bleiben():
    assert {"Vodafone", "Telekom", "1&1", "congstar"} <= set(geplante_anbieter(WURZEL))
