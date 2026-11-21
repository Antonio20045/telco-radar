"""Gegenprobe im festen Fenster (``gegenprobe_fenster``): Auswahl, Reihenfolge,
Seitenbesuche und Anbieter-Schnitt.

Lauf 21.11.2026: nur die am Tag gemessenen Änderungen und fünf Stichproben je Anbieter
kamen dran, ältere Bündel nie; 420 von 674 blieben ungeöffnet, Vodafone, congstar und
Saturn/MediaMarkt ohne einen Besuch. Seitdem ist jedes angezeigte Bündel binnen
``GEGENPROBE_FENSTER_TAGE`` fällig, die Änderungen des Tages zuerst.
"""

from __future__ import annotations

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_fenster as gf

TAG = "2026-11-21"


def _id(anbieter: str, n: int) -> str:
    return f"buendel--{anbieter}--geraet-{n}-128gb-schwarz--tarif--24m"


def _satz(anbieter: str, n: int, seite: str = "", gesamt: float = 100.0) -> dict:
    return {
        "id": _id(anbieter, n),
        "anbieter": anbieter,
        "seite": seite or f"{anbieter}-{n}",
        "gesamt": gesamt,
    }


def _probe(bid: str, datum: str, status: str = gp.BESTAETIGT, **anders) -> gp.Ergebnis:
    werte = {
        "datum": datum,
        "buendel_id": bid,
        "anbieter": "x",
        "status": status,
        "anlass": gp.ANLASS_FENSTER,
        "gesamt_gespeichert": 100.0,
        "grund": None if status in gp.GEPRUEFT else "Auswahl nicht gefunden: 256 GB",
    }
    werte.update(anders)
    return gp.Ergebnis(**werte)


def _kandidaten(saetze, proben=(), aenderungen=(), nur=None):
    return gf.kandidaten(
        TAG,
        saetze,
        lambda s: s["gesamt"],
        gf.Gegenproben(proben),
        list(aenderungen),
        nur,
    )


def _plan(saetze, proben=(), aenderungen=()):
    seiten = {s["id"]: s["seite"] for s in saetze}
    return gf.plane(_kandidaten(saetze, proben, aenderungen), seiten.__getitem__)


def test_fenster_ist_eine_benannte_konstante_von_sieben_tagen():
    assert gf.GEGENPROBE_FENSTER_TAGE == 7
    assert gf.im_fenster(TAG, "2026-11-15")
    assert not gf.im_fenster(TAG, "2026-11-14")
    assert not gf.im_fenster(TAG, None)


def test_fenster_konstante_wirkt(monkeypatch):
    monkeypatch.setattr(gf, "GEGENPROBE_FENSTER_TAGE", 3)
    monkeypatch.setattr(gf, "VORLAUF_TAGE", 0)
    assert not gf.im_fenster(TAG, "2026-11-18")
    saetze = [_satz("o2", 1)]
    kand = _kandidaten(saetze, [_probe(saetze[0]["id"], "2026-11-18")])
    assert [(k.anlass, k.faellig) for k in kand] == [(gp.ANLASS_FENSTER, True)]


def test_preisaenderung_des_tages_kommt_vor_jedem_faelligen():
    saetze = [_satz("o2", 1), _satz("o2", 2)]
    proben = [_probe(saetze[1]["id"], "2026-11-20")]
    kand = _kandidaten(saetze, proben, aenderungen=[saetze[1]["id"]])
    assert [(k.buendel_id, k.anlass) for k in kand] == [
        (saetze[1]["id"], gp.ANLASS_AENDERUNG),
        (saetze[0]["id"], gp.ANLASS_FENSTER),
    ]


def test_nie_gepruefte_zuerst_dann_die_aelteste_pruefung():
    saetze = [_satz("o2", n) for n in range(4)]
    proben = [
        _probe(saetze[1]["id"], "2026-11-13"),
        _probe(saetze[2]["id"], "2026-11-16"),
        _probe(saetze[3]["id"], "2026-11-20"),
    ]
    kand = _kandidaten(saetze, proben)
    assert [k.buendel_id for k in kand] == [s["id"] for s in saetze]
    assert [k.faellig for k in kand] == [True, True, True, False]
    assert kand[3].anlass == gp.ANLASS_GLEICHE_SEITE


def test_gescheiterter_versuch_kommt_nach_den_nie_versuchten():
    saetze = [_satz("1-1", 1), _satz("1-1", 2)]
    proben = [_probe(saetze[0]["id"], "2026-11-19", gp.NICHT_PRUEFBAR)]
    kand = _kandidaten(saetze, proben)
    assert [k.buendel_id for k in kand] == [saetze[1]["id"], saetze[0]["id"]]
    assert all(k.faellig for k in kand)


def test_heute_geoeffnet_kommt_nicht_noch_einmal_nicht_geoeffnet_schon():
    saetze = [_satz("o2", n) for n in range(4)]
    proben = [
        _probe(saetze[0]["id"], TAG),
        _probe(saetze[1]["id"], TAG, gp.NICHT_PRUEFBAR),
        _probe(saetze[2]["id"], TAG, gp.NICHT_GEGENGEPRUEFT, grund="Zeitbudget"),
    ]
    kand = _kandidaten(saetze, proben)
    assert [k.buendel_id for k in kand] == [saetze[2]["id"], saetze[3]["id"]]


def test_neuer_preis_am_selben_tag_ist_wieder_offen():
    """Ein zweiter Gerätelauf misst einen neuen Preis: die Gegenprobe des alten
    Preises von heute zählt nicht, der zweite Lauf prüft ihn."""
    saetze = [_satz("o2", 1, gesamt=120.0)]
    kand = _kandidaten(saetze, [_probe(saetze[0]["id"], TAG)], [saetze[0]["id"]])
    assert [(k.buendel_id, k.anlass) for k in kand] == [
        (saetze[0]["id"], gp.ANLASS_AENDERUNG)
    ]


def test_andere_farbe_mit_gleichem_preis_zaehlt_als_gegenprobe():
    saetze = [_satz("vodafone", 1)]
    farbe = saetze[0]["id"].replace("schwarz", "blau")
    kand = _kandidaten(saetze, [_probe(farbe, "2026-11-20")])
    assert [k.faellig for k in kand] == [False]


def test_ein_besuch_prueft_alle_buendel_seiner_seite():
    saetze = [
        _satz("o2", 1, seite="a"),
        _satz("o2", 2, seite="a"),
        _satz("o2", 3, seite="b"),
    ]
    proben = [
        _probe(saetze[1]["id"], "2026-11-20"),
        _probe(saetze[2]["id"], "2026-11-20"),
    ]
    assert _plan(saetze, proben) == [
        [
            (saetze[0]["id"], gp.ANLASS_FENSTER),
            (saetze[1]["id"], gp.ANLASS_GLEICHE_SEITE),
        ]
    ]


def test_besuche_reihum_ueber_die_anbieter():
    saetze = [_satz("o2", n) for n in range(3)] + [_satz("congstar", 9)]
    plan = _plan(saetze)
    assert [gp.anbieter_aus_id(g[0][0]) for g in plan] == ["congstar", "o2", "o2", "o2"]


def test_saturn_netze_bilden_einen_job_je_host():
    netze = gf.SAMMELJOBS["saturn-mediamarkt"]
    assert {gf.job_von(s) for s in netze} == {"saturn-mediamarkt"}
    assert gf.schluessel_der_jobs(["saturn-mediamarkt"]) == frozenset(netze)
    assert gf.schluessel_der_jobs(["o2"]) == frozenset({"o2"})
    assert gf.schluessel_der_jobs([]) is None


SCHLUESSEL = (
    "telekom",
    "o2",
    "vodafone",
    "congstar",
    "1-1",
    *gf.SAMMELJOBS["saturn-mediamarkt"],
)


def test_anbieter_schnitt_deckt_jedes_buendel_genau_einmal():
    saetze = [_satz(s, n) for s in SCHLUESSEL for n in range(3)]
    alle = {k.buendel_id for k in _kandidaten(saetze)}
    jobs = gf.jobs(_kandidaten(saetze))
    assert jobs == sorted(
        {"telekom", "o2", "vodafone", "congstar", "1-1", "saturn-mediamarkt"}
    )
    teile = [
        {k.buendel_id for k in _kandidaten(saetze, nur=gf.schluessel_der_jobs([j]))}
        for j in jobs
    ]
    assert set().union(*teile) == alle == {s["id"] for s in saetze}
    assert sum(len(t) for t in teile) == len(alle)


def test_jeder_schluessel_gehoert_genau_einem_job():
    jobs = sorted({gf.job_von(s) for s in SCHLUESSEL})
    for s in SCHLUESSEL:
        treffer = [j for j in jobs if s in (gf.schluessel_der_jobs([j]) or ())]
        assert treffer == [gf.job_von(s)]


def test_ohne_faelliges_kein_job():
    saetze = [_satz("o2", 1), _satz("telekom", 1)]
    proben = [_probe(saetze[0]["id"], "2026-11-20"), _probe(saetze[1]["id"], TAG)]
    assert gf.jobs(_kandidaten(saetze, proben)) == []
    assert _plan(saetze, proben) == []
