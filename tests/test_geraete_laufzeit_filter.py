"""P3-E2: der Laufzeit-Filter der Bündeltabelle, Standard 24 Monate.

Python entscheidet, welche Zeile unter welcher Wahl steht
(`geraete_tco_karten.laufzeit_wahl`), app.js blendet nur. Die Wahl blendet
keinen Anbieter aus: wer die gewaehlte Laufzeit nicht anbietet, steht mit
seiner naechstgelegenen da (Telekom, o2 und 1&1 bieten heute nur 36 Raten).

Die Browser-Tests der Bündeltabelle sind mit dem Neuentwurf der
Geräteseite (29.09.2026, eine Kosten-Rangliste mit eigenem Ratenfilter,
siehe `tests/test_geraete_kosten_browser.py`) gefallen.
"""
from __future__ import annotations

from telco_radar.report import geraete_tco_karten as karten


def _k(anbieter, tarif, lz, zustand="neu"):
    return {"anbieter": anbieter, "tarif": tarif, "raten_laufzeit": lz,
            "zustand": zustand}


# --------------------------------------------------------------------------
# Python: wer steht unter welcher Wahl
# --------------------------------------------------------------------------

def test_jede_wahl_zeigt_je_angebot_genau_eine_zeile():
    cs24, cs36 = _k("congstar", "XS", 24), _k("congstar", "XS", 36)
    o2 = _k("o2", "M", 36)
    vf12, vf24 = _k("Vodafone", "S", 12), _k("Vodafone", "S", 24)
    ref = _k("Vodafone", "Referenz", None)
    alle = [cs24, cs36, o2, vf12, vf24, ref]
    wahl = karten.laufzeit_wahl(alle)
    assert wahl == {"optionen": [12, 24, 36], "start": 24}
    assert cs24["laufzeit_sichtbar"] == "12 24"
    assert cs36["laufzeit_sichtbar"] == "36"
    assert o2["laufzeit_sichtbar"] == "12 24 36"
    assert vf12["laufzeit_sichtbar"] == "12"
    assert vf24["laufzeit_sichtbar"] == "24 36"
    assert ref["laufzeit_sichtbar"] == "", "ohne Raten gehoert sie zu keiner Wahl"
    # Gegenprobe: je Wahl und Angebot genau EINE Zeile.
    for lz in ("12", "24", "36"):
        je_angebot: dict = {}
        for k in alle[:-1]:
            if lz in k["laufzeit_sichtbar"].split():
                je_angebot.setdefault((k["anbieter"], k["tarif"]), []).append(k)
        assert all(len(v) == 1 for v in je_angebot.values()), (lz, je_angebot)
        assert len(je_angebot) == 3


def test_der_zustand_trennt_die_angebote():
    neu = _k("o2", "M", 24)
    erneuert = _k("o2", "M", 36, zustand="refurbished")
    karten.laufzeit_wahl([neu, erneuert])
    assert erneuert["laufzeit_sichtbar"] == "24 36"


def test_ohne_zwei_laufzeiten_gibt_es_nichts_zu_waehlen():
    k = _k("o2", "M", 36)
    assert karten.laufzeit_wahl([k, _k("Telekom", "L", 36)]) is None
    assert k["laufzeit_sichtbar"] == ""


def test_fehlt_die_standardlaufzeit_gilt_die_naechste_kuerzere():
    assert karten.laufzeit_wahl([_k("a", "t", 12), _k("b", "t", 36)])[
        "start"] == 12
    assert karten.laufzeit_wahl([_k("a", "t", 30), _k("b", "t", 36)])[
        "start"] == 30
    assert karten.LAUFZEIT_STANDARD == 24
