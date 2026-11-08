"""Jede Exportzeile trägt die Kosten ihres eigenen Bündels (Preisprüfung 03.11.2026).

Befund (Karte 13873a06, am 08.11.2026 nachgeprüft: kein Rechenfehler): Vodafone
Mobil M, iPhone 17 256 GB, 12 Raten (Tarif 28,35 €, Rate 90 €, Anzahlung 1 €)
stand mit 1.797,40 € im Export, genau wie die 24-Raten-Zeile. Das ist keine
Verwechslung: Die 12-Raten-Zeile hat zwei Tarifphasen (Monat 1 bis 12 28,35 €,
Monat 13 bis 24 31,35 €), `Tarif/Monat EUR` nennt nur die erste. Die
24-Raten-Zeile kommt mit 24 × 29,85 € + 24 × 45 € + 1 € auf dieselbe Summe.

Die Summen unten sind von Hand aus den Feldern der Zeile gerechnet, nicht aus
`kosten_ueber`. Gegenprobe: dieselben Felder ohne zweite Phase ergeben die
Summe, die ein Leser mit nur einem Tarifpreis erwartet.
"""

from __future__ import annotations

import csv
import io

from telco_radar.report import geraete_tco_view
from telco_radar.report.geraete_export import (
    SPALTE_UEBER_24,
    SPALTE_UEBER_LAUFZEIT,
    tco_csv,
)
from telco_radar.tarif_model import Preisphase
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-03"
SKU = "apple-iphone-17-256gb-gruen"


def _vodafone(laufzeit, tarif, rate, phasen):
    return Buendel(
        sku_id=SKU,
        anbieter="Vodafone",
        tarif_name="Mobil M",
        tarif_monatlich=tarif,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=rate,
        laufzeit_monate=laufzeit,
        anschlusspreis=0.0,
        quelle_url="https://www.vodafone.de/privat/handys/iphone-17.html",
        abgerufen_am=HEUTE,
        zustand="neu",
        tarif_phasen=[Preisphase(*p) for p in phasen],
    )


def _nach_laufzeit(*buendel):
    zeilen = geraete_tco_view._export_zeilen(
        list(buendel), [], [], None, {}, None, HEUTE
    )
    kopf, *rest = csv.reader(io.StringIO(tco_csv(zeilen)[0]), delimiter=";")
    return {
        r[kopf.index("Laufzeit Monate")]: dict(zip(kopf, r, strict=True)) for r in rest
    }


def _kosten(zeile):
    return zeile[SPALTE_UEBER_24] or zeile[SPALTE_UEBER_LAUFZEIT]


def test_jede_zeile_traegt_die_kosten_ihrer_eigenen_felder():
    """12 Raten: 1 + 12 × 28,35 + 12 × 31,35 + 12 × 90. 24 Raten: 1 + 24 × 29,85
    + 24 × 45, zufällig dieselbe Summe. 36 Raten: 1 + 24 × 30,35 + 36 × 30."""
    z = _nach_laufzeit(
        _vodafone(12, 28.35, 90.0, [(1, 12, 28.35), (13, 24, 31.35)]),
        _vodafone(24, 29.85, 45.0, [(1, 24, 29.85)]),
        _vodafone(36, 30.35, 30.0, [(1, 24, 30.35)]),
    )
    assert _kosten(z["12"]) == "1797,40"
    assert _kosten(z["24"]) == "1797,40"
    assert _kosten(z["36"]) == "1809,40"


def test_gegenprobe_12_raten_ohne_zweite_phase_rechnet_den_einen_tarifpreis():
    """12 Raten mit einem Tarifpreis: 1 + 24 × 28,35 + 12 × 90."""
    z = _nach_laufzeit(
        _vodafone(12, 28.35, 90.0, [(1, 24, 28.35)]),
        _vodafone(24, 29.85, 45.0, [(1, 24, 29.85)]),
    )
    assert _kosten(z["12"]) == "1761,40"
    assert _kosten(z["24"]) == "1797,40"


def test_12_raten_zaehlen_zwoelf_raten_nicht_vierundzwanzig():
    """Karte 13873a06, Gegenprobe zur Verwechslung: 12 Raten à 90 € sind 1.080 €.
    Würde die Rate 24 Monate gezählt, stünde 1 + 24 × 28,35 + 24 × 90 = 2.841,40 €
    in der Zeile; die Zeile trägt 1 + 24 × 28,35 + 12 × 90 = 1.761,40 €."""
    z = _nach_laufzeit(_vodafone(12, 28.35, 90.0, [(1, 24, 28.35)]))
    assert _kosten(z["12"]) == "1761,40"
    assert _kosten(z["12"]) != "2841,40"


def test_ohne_ratenlaufzeit_keine_summe_und_benannte_luecke():
    """Fail-closed: kennt die Zeile ihre Ratenlaufzeit nicht, rechnet der Export
    weder mit 12 noch mit 24, sondern lässt die Summe leer und nennt die Lücke."""
    zeilen = geraete_tco_view._export_zeilen(
        [_vodafone(None, 28.35, 90.0, [(1, 24, 28.35)])], [], [], None, {}, None, HEUTE
    )
    kopf, zeile = list(csv.reader(io.StringIO(tco_csv(zeilen)[0]), delimiter=";"))
    z = dict(zip(kopf, zeile, strict=True))
    assert _kosten(z) == ""
    assert "Ratenlaufzeit" in z["Lücke"]
