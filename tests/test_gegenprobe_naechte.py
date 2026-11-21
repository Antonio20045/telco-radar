"""Gegenprobe über mehrere Nächte (dritte Prüfung zu PR 200, Testhilfe
``gegenprobe_nacht``): Dauerfehler dürfen prüfbare Bündel nie aus dem 7-Tage-Fenster
drängen, gleich ob neu, im ersten Lauf oder früher einmal gut. Vorher schaltete eine
Fehlerserie Seiten ohne gute Prüfung ab (``NUR_BEKANNT``) und nach einer zweiten den
Anbieter. Seitdem: verdächtig ist nur, wessen letzter Versuch scheiterte, davon
höchstens ``VERDAECHTIG_JE_NACHT`` je Nacht; nie versuchte Seiten laufen immer.
"""

from __future__ import annotations

from gegenprobe_nacht import nacht, satz, tag, zeile

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_bilanz as bz
from telco_radar import gegenprobe_fenster as gf

START = "2026-11-22"


def test_neue_pruefbare_neben_dauerfehlern_werden_binnen_7_tagen_geprueft():
    kaputt = [satz(n) for n in range(12)]
    bekannt = [satz(n) for n in range(100, 105)]
    neu = [satz(n, first_seen=START) for n in range(200, 203)]
    alle = {s["id"]: s for s in kaputt + bekannt + neu}
    rows = [zeile(s, tag(START, -1), gp.BESTAETIGT) for s in bekannt]
    gut_am: dict[str, str] = {}
    for i in range(7):
        d = tag(START, i)
        _, neue, _ = nacht(d, alle, rows, {s["id"] for s in kaputt}, 10_000)
        rows += neue
        for z in neue:
            if z.status in gp.GEPRUEFT:
                gut_am.setdefault(z.buendel_id, d)
    offen = [s["id"] for s in neu if s["id"] not in gut_am]
    assert not offen, f"{len(offen)} von {len(neu)} neuen Bündeln nie gegengeprüft"


def test_erster_lauf_viele_dauerfehler_sperren_lesbare_nicht_dauerhaft():
    kaputt = [satz(n, "1-1", first_seen="2026-11-05") for n in range(240)]
    lesbar = [satz(n, "1-1", first_seen="2026-11-15") for n in range(1000, 1020)]
    alle = {s["id"]: s for s in kaputt + lesbar}
    rows: list[gp.Ergebnis] = []
    gut: set[str] = set()
    for i in range(10):
        _, neue, _ = nacht(tag(START, i), alle, rows, {s["id"] for s in kaputt}, 10_000)
        rows += neue
        gut |= {z.buendel_id for z in neue if z.status in gp.GEPRUEFT}
    offen = [s["id"] for s in lesbar if s["id"] not in gut]
    assert not offen, f"{len(offen)} von {len(lesbar)} lesbaren Bündeln nie geprüft"


def test_dauerfehler_mit_alter_guter_pruefung_verdraengen_pruefbare_nicht():
    kaputt = [satz(n) for n in range(30)]
    gut = [satz(n) for n in range(100, 108)]
    alle = {s["id"]: s for s in kaputt + gut}
    rows = [zeile(s, "2026-11-01", gp.BESTAETIGT) for s in kaputt]
    rows += [zeile(s, tag(START, -6), gp.BESTAETIGT) for s in gut]
    letzte = {s["id"]: tag(START, -6) for s in gut}
    luecken = []
    for i in range(8):
        d = tag(START, i)
        _, neue, _ = nacht(d, alle, rows, {s["id"] for s in kaputt}, 10_000)
        rows += neue
        letzte.update({z.buendel_id: d for z in neue if z.status in gp.GEPRUEFT})
        raus = [b for b, am in letzte.items() if not gf.im_fenster(d, am)]
        if raus:
            luecken.append((d, len(raus)))
    assert not luecken, f"außerhalb des Fensters (Tag, Anzahl): {luecken}"


def test_verdaechtige_seiten_je_nacht_begrenzt_und_benannt():
    kaputt = [satz(n) for n in range(3 * gf.VERDAECHTIG_JE_NACHT)]
    alle = {s["id"]: s for s in kaputt}
    rows = [zeile(s, tag(START, -3), gp.NICHT_PRUEFBAR) for s in kaputt]
    lauf, neue, _ = nacht(START, alle, rows, set(alle), 10_000)
    assert len(neue) == gf.VERDAECHTIG_JE_NACHT
    (eintrag,) = lauf.laeufe()
    assert eintrag["zurueckgestellt"] == 2 * gf.VERDAECHTIG_JE_NACHT
    assert eintrag["ausfall"] is None


def _fair(naechte, mit_kaputt, kapazitaet, aenderungen_je_tag=4, kaputt_n=20):
    gut = [satz(n) for n in range(60)]
    kaputt = [satz(n) for n in range(500, 500 + kaputt_n)] if mit_kaputt else []
    alle = {s["id"]: s for s in gut + kaputt}
    rows = [zeile(s, tag(START, -(i % 7)), gp.BESTAETIGT) for i, s in enumerate(gut)]
    verletzt = []
    for i in range(naechte):
        d = tag(START, i)
        aend = []
        for j in range(aenderungen_je_tag):
            s = gut[(i * aenderungen_je_tag + j) % len(gut)]
            s["tarif_monatlich"] = float(s["tarif_monatlich"]) + 1
            aend.append(s["id"])
        _, neue, _ = nacht(d, alle, rows, {s["id"] for s in kaputt}, kapazitaet, aend)
        rows += neue
        proben = gf.Gegenproben(rows)
        for s in gut:
            g = proben.letzte_gute(s["id"], bz.gesamt_von(s), s)
            if g is None or not gf.im_fenster(d, g.datum):
                verletzt.append((d, s["id"][-30:-14]))
    return verletzt


def test_fair_ohne_dauerfehler_reicht_kapazitaet():
    verletzt = _fair(14, False, 16 * 4)
    assert not verletzt, f"{len(verletzt)} Verletzungen, erste {verletzt[:3]}"


def test_fair_mit_dauerfehlern_verdraengen_pruefbare_nicht():
    verletzt = _fair(14, True, 40 * 4)
    assert not verletzt, f"{len(verletzt)} Verletzungen, erste {verletzt[:3]}"


def test_ohne_first_seen_gilt_buendel_nicht_jede_nacht_als_neu():
    s = satz(1)
    del s["first_seen"]
    faellig = []
    for i in range(10):
        d = tag(START, i)
        s["abgerufen_am"] = d
        wahl = gf.kandidaten(d, [s], bz.gesamt_von, gf.Gegenproben([]), [])
        faellig.append(wahl[0].faellig)
    assert all(faellig)
    assert gf.ohne_erste_anzeige(s)
