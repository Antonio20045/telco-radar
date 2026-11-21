"""Gegenprobe: faire Reihenfolge und Seitengruppen (``gegenprobe.auswahl``,
``gegenprobe_reihe.gruppiere``).

Lauf 21.11.2026 (Actions 44863947277): die Änderungen standen nach Größe über alle
Anbieter vor jeder Stichprobe; o2s 452 Änderungen nahmen das ganze Zeitbudget, die
Stichproben von Vodafone, congstar und Saturn/MediaMarkt blieben ungeprüft. Seitdem:
zuerst die Stichprobe jedes Anbieters, dann die Änderungen reihum.
"""

from __future__ import annotations

from telco_radar import gegenprobe as gp
from telco_radar.gegenprobe_reihe import gruppiere

TAG = "2026-11-20"
VORTAG = "2026-11-19"


def _zeile(bid, datum, rate):
    return {
        "id": bid,
        "datum": datum,
        "abgerufen_am": datum,
        "tarif_monatlich": 10.0,
        "geraet_monatsrate": rate,
    }


def _id(anbieter, n):
    return f"buendel--{anbieter}--geraet-{n}--tarif--24m"


def _tag(aenderungen: dict[str, list[float]], ruhig: dict[str, int]):
    heute, vortag = [], []
    for anbieter, deltas in aenderungen.items():
        for i, delta in enumerate(deltas):
            bid = _id(anbieter, f"a{i}")
            heute.append(_zeile(bid, TAG, 10.0 + delta))
            vortag.append(_zeile(bid, VORTAG, 10.0))
    for anbieter, n in ruhig.items():
        for i in range(n):
            bid = _id(anbieter, f"r{i}")
            heute.append(_zeile(bid, TAG, 10.0))
            vortag.append(_zeile(bid, VORTAG, 10.0))
    return heute, vortag


def test_stichprobe_jedes_anbieters_kommt_vor_jeder_aenderung():
    heute, vortag = _tag({"o2": [5.0, 4.0, 3.0]}, {"o2": 2, "vodafone": 2})
    wahl = gp.auswahl(TAG, heute, vortag, 2)
    anlaesse = [a for _, a in wahl]
    assert anlaesse == [gp.ANLASS_STICHPROBE] * 4 + [gp.ANLASS_AENDERUNG] * 3
    assert {gp.anbieter_aus_id(b) for b, _ in wahl[:4]} == {"o2", "vodafone"}


def test_stichproben_reihum_ueber_die_anbieter():
    heute, vortag = _tag({}, {"o2": 3, "telekom": 3, "vodafone": 3})
    wahl = gp.auswahl(TAG, heute, vortag, 2)
    assert [gp.anbieter_aus_id(b) for b, _ in wahl] == [
        "o2",
        "telekom",
        "vodafone",
    ] * 2


def test_aenderungen_reihum_groesste_zuerst_je_anbieter():
    heute, vortag = _tag({"o2": [1.0, 9.0, 5.0], "telekom": [2.0]}, {})
    wahl = gp.auswahl(TAG, heute, vortag, 0)
    assert wahl == [
        (_id("o2", "a1"), gp.ANLASS_AENDERUNG),
        (_id("telekom", "a0"), gp.ANLASS_AENDERUNG),
        (_id("o2", "a2"), gp.ANLASS_AENDERUNG),
        (_id("o2", "a0"), gp.ANLASS_AENDERUNG),
    ]


def test_ein_grosser_anbieter_verdraengt_keinen_kleinen():
    """Reicht das Budget für 10 Prüfungen, kommt jeder Anbieter dran (21.11.2026)."""
    heute, vortag = _tag(
        {"o2": [float(i + 1) for i in range(400)], "1-1": [1.0] * 100},
        {"o2": 5, "1-1": 5, "telekom": 5, "vodafone": 5, "congstar": 5},
    )
    ersten = gp.auswahl(TAG, heute, vortag, 5)[:10]
    assert {gp.anbieter_aus_id(b) for b, _ in ersten} == {
        "o2",
        "1-1",
        "telekom",
        "vodafone",
        "congstar",
    }


def test_gruppen_in_der_reihenfolge_ihres_ersten_buendels():
    wahl = [("a", "x"), ("b", "x"), ("c", "x"), ("d", "x"), ("e", "x")]
    seite = {"a": "p1", "b": "p2", "c": "p1", "d": "p3", "e": "p2"}
    assert gruppiere(wahl, seite.__getitem__) == [
        [("a", "x"), ("c", "x")],
        [("b", "x"), ("e", "x")],
        [("d", "x")],
    ]


def test_gruppieren_verliert_und_verdoppelt_nichts():
    wahl = [(str(i), gp.ANLASS_AENDERUNG) for i in range(50)]
    gruppen = gruppiere(wahl, lambda bid: str(int(bid) % 7))
    flach = [p for g in gruppen for p in g]
    assert sorted(flach) == sorted(wahl) and len(gruppen) == 7
