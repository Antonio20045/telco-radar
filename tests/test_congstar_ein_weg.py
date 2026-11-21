"""congstar hat einen Preisweg: den Adapter (Stand 21.11.2026).

Befund am Nachtstand 21.11.2026 (Klick-Lauf 44840854026) und einem lokalen
Adapterlauf am selben Tag: der Klick-Lauf brauchte 2150 s für 712 Kombinationen, jede
mit Adapter-Gegenstück und denselben Werten; der Adapter liest dieselben 920 Bündel
in rund 90 s. Die Tarifbindung, die vorher nur der Klick nannte, liest der Adapter
seitdem selbst (``tests/test_geraete_congstar_tarifbindung.py``). Seitdem steht
congstar nicht mehr in der Klick-Tagesdatei und trägt ``erfassung: adapter``.
"""

from __future__ import annotations

from pathlib import Path

from telco_radar.collect.geraete.klickziele import geplante_anbieter
from telco_radar.geraete_config import lade_quellen

WURZEL = Path(__file__).resolve().parents[1]


def test_congstar_misst_nur_der_adapter():
    congstar = lade_quellen(WURZEL).nach_name("congstar")
    assert (congstar.erfassung, congstar.methode) == ("adapter", "congstar_next")


def test_keine_congstar_seite_im_klick_tageslauf():
    text = (WURZEL / "config" / "klick_tageslauf.yaml").read_text(encoding="utf-8")
    assert "url: https://www.congstar.de" not in text
    assert "congstar" not in geplante_anbieter(WURZEL)


def test_gegenprobe_die_karte_bleibt_fuer_die_erkundung():
    assert (WURZEL / "config" / "klickkarten" / "congstar.yaml").is_file()
