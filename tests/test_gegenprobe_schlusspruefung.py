"""Schlussprüfung PR 200 (Testhilfe ``gegenprobe_nacht``): ein Sammeljob verliert keinen
Anbieter in der Bilanz, ein Platzhalter fällt unabhängig von der Reihenfolge weg,
hängende Einzelseiten (Timeout) stoppen nie den Anbieter, und eine kaputte Seite mit
einem noch gültigen Bündel umgeht die Kappung ``VERDAECHTIG_JE_NACHT`` nicht.
"""

from __future__ import annotations

import pytest
from gegenprobe_nacht import FORM, TIMEOUT, nacht, satz, tag, zeile

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_bilanz as bz
from telco_radar import gegenprobe_fenster as gf

START = "2026-11-22"


def test_ein_lauf_mehrere_anbieter_geht_in_der_bilanz_nicht_verloren():
    a = satz(1, anbieter="saturn-mediamarkt-o2-netz")
    b = satz(2, anbieter="saturn-mediamarkt-telekom-netz")
    lauf, _, _ = nacht(START, {s["id"]: s for s in (a, b)}, [], set())
    laeufe = lauf.laeufe()
    assert len(laeufe) == 2
    gefuehrt = bz.fuehre_laeufe([], laeufe)
    assert {e["anbieter"] for e in gefuehrt} == {e["anbieter"] for e in laeufe}


def test_bilanz_hat_je_netz_des_sammeljobs_seine_besuche(tmp_path):
    alle = {}
    for netz in ("telekom", "vodafone", "o2"):
        s = satz(len(alle), anbieter=f"saturn-mediamarkt-{netz}-netz")
        alle[s["id"]] = s
    lauf, neue, _ = nacht(START, alle, [], set())
    laeufe = lauf.laeufe()
    assert len(laeufe) == 3
    bilanz = bz.lege_ab(tmp_path, START, neue, laeufe, list(alle.values()))
    assert [e["besuche"] for e in bilanz["anbieter"].values()] == [1, 1, 1]


def test_platzhalter_nach_gemessenem_lauf_desselben_tages_faellt_weg():
    gemessen = {
        "datum": START,
        "anbieter": "o2",
        "besuche": 3,
        "sekunden": 9.0,
        "buendel": 5,
        "ausfall": None,
        "lauf_id": "abc",
    }
    platz = {
        "datum": START,
        "anbieter": "o2",
        "besuche": None,
        "sekunden": None,
        "buendel": None,
        "ausfall": "Teildatei fehlt",
        "platzhalter": True,
        "lauf_id": "fehlt-x",
    }
    for alt, neu in (([gemessen], [platz]), ([platz], [gemessen])):
        out = bz.fuehre_laeufe(alt, neu)
        assert [e.get("platzhalter") for e in out] == [None]


@pytest.mark.parametrize("fehlertext", [TIMEOUT, FORM])
def test_haengende_einzelseiten_stoppen_nicht_den_anbieter(fehlertext):
    haenger = [satz(n, first_seen="2026-10-01") for n in range(10)]
    lesbar = [satz(n) for n in range(100, 130)]
    alle = {s["id"]: s for s in haenger + lesbar}
    kaputt = {s["id"]: fehlertext for s in haenger}
    rows = [zeile(s, tag(START, -(i % 7)), gp.BESTAETIGT) for i, s in enumerate(lesbar)]
    luecken = []
    for i in range(14):
        d = tag(START, i)
        lauf, neue, _ = nacht(d, alle, rows, kaputt)
        rows += neue
        proben = gf.Gegenproben(rows)
        raus = [
            s["id"]
            for s in lesbar
            if (g := proben.letzte_gute(s["id"], bz.gesamt_von(s), s)) is None
            or not gf.im_fenster(d, g.datum)
        ]
        if raus:
            luecken.append((d, len(raus), lauf.laeufe()[0]["ausfall"]))
    assert not luecken, f"außerhalb des Fensters (Tag, Anzahl, Ausfall): {luecken[:3]}"


def test_serverfehler_auf_verdaechtigen_seiten_belegen_keinen_hostausfall():
    haenger = [satz(n, first_seen="2026-10-01") for n in range(20)]
    lesbar = [satz(n) for n in range(100, 105)]
    alle = {s["id"]: s for s in haenger + lesbar}
    kaputt = {s["id"]: "Seite antwortet mit HTTP 503" for s in haenger}
    rows = [
        zeile(s, tag(START, -3), gp.NICHT_PRUEFBAR, kaputt[s["id"]]) for s in haenger
    ]
    lauf, neue, _ = nacht(START, alle, rows, kaputt)
    assert lauf.laeufe()[0]["ausfall"] is None
    assert {z.buendel_id for z in neue if z.status in gp.GEPRUEFT} == {
        s["id"] for s in lesbar
    }


def test_kaputte_seiten_mit_gueltigem_buendel_umgehen_kappung_nicht():
    saetze, kaputt, rows = {}, {}, []
    for p in range(40):
        url = f"https://o2.example/seite-{p}"
        x = satz(1000 + p, seite=url)
        y = satz(2000 + p, seite=url)
        for s in (x, y):
            saetze[s["id"]] = s
            kaputt[s["id"]] = FORM
        rows += [
            zeile(x, tag(START, -20), gp.BESTAETIGT),
            zeile(x, tag(START, -3), gp.NICHT_PRUEFBAR),
            zeile(y, tag(START, -1), gp.BESTAETIGT),
        ]
    je_nacht = []
    for i in range(6):
        lauf, neue, _ = nacht(tag(START, i), saetze, rows, kaputt, je_url=True)
        rows += neue
        je_nacht.append(lauf.laeufe()[0]["besuche"] if lauf.laeufe() else 0)
    assert max(je_nacht) <= gf.VERDAECHTIG_JE_NACHT, f"Besuche je Nacht: {je_nacht}"


def test_seite_mit_einzelnem_tarif_fehler_bleibt_lesbar():
    """Vodafone 21.11.: auf einer Seite stand ein Tarif nicht zur Wahl, die anderen
    wurden gelesen. Die Seite ist lesbar, nicht verdächtig; ganz gescheitert ist sie
    verdächtig."""
    url = "https://vodafone.example/iphone"
    m = satz(1, "vodafone", seite=url)
    xs = satz(2, "vodafone", seite=url)
    proben = gf.Gegenproben(
        [
            zeile(m, tag(START, -6), gp.NICHT_PRUEFBAR),
            zeile(xs, tag(START, -6), gp.BESTAETIGT),
        ]
    )
    wahl = gf.kandidaten(START, [m, xs], bz.gesamt_von, proben, [])
    (gruppe,) = gf.plane(wahl, lambda bid: url)
    assert not gf.verdaechtige_seite(gruppe)
    proben = gf.Gegenproben([zeile(m, tag(START, -6), gp.NICHT_PRUEFBAR)])
    wahl = gf.kandidaten(START, [m, xs], bz.gesamt_von, proben, [])
    (gruppe,) = gf.plane(wahl, lambda bid: url)
    assert gf.verdaechtige_seite(gruppe)
