"""Welche Gegenprobe einen Preis und eine Preisänderung belegt, welche Bilder darum
bleiben, und die Zahl „mit Bild“ je Anbieter (Abnahmekriterium 3). Feste Daten, keine
Uhr, kein Netz."""

from __future__ import annotations

import json
from datetime import date

import pytest
from beleg_attrappe import AttrappeReleases
from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_ablage as ga
from telco_radar import gegenprobe_belege as gb
from telco_radar import gegenprobe_bilanz as bz
from telco_radar.gegenprobe_fenster import Gegenproben
from telco_radar.report import geraete_gegenprobe_stand as stand

BID = "buendel--o2--apple-iphone-17-256gb-schwarz--o2-mobile-l--24m"
BLAU = "buendel--o2--apple-iphone-17-256gb-blau--o2-mobile-l--24m"
ALT_TAG, NEU_TAG = "2026-11-18", "2026-11-22"
GANZ = ["Gerät", "Speicher", "Tarif", "Raten", "Preis"]


def _messung(datum: str, rate: float, bid: str = BID) -> dict:
    return {
        "id": bid,
        "datum": datum,
        "abgerufen_am": datum,
        "tarif_monatlich": 24.99,
        "geraet_monatsrate": rate,
        "laufzeit_monate": 24,
        "geraet_zuzahlung": 1.0,
        "anschlusspreis": 0.0,
    }


def _probe(datum: str, rate: float, status=gp.BESTAETIGT, bid=BID, **anders):
    werte = {
        "datum": datum,
        "buendel_id": bid,
        "anbieter": "o2",
        "status": status,
        "anlass": gp.ANLASS_FENSTER,
        "gespeichert": gp.gespeicherte_werte(_messung(datum, rate, bid)),
        "bild": ga.url(f"gegenprobe-{datum}-o2", f"{datum}-{rate}.webp"),
        "bild_zeigt": GANZ,
        "bild_ohne": [],
    }
    if status == gp.NICHT_PRUEFBAR:
        werte["grund"] = "Auswahl nicht gefunden: 256 GB"
    werte.update(anders)
    return gp.Ergebnis(**werte)


def test_alter_preis_ist_die_letzte_gute_pruefung_davor():
    proben = Gegenproben(
        [
            _probe("2026-11-15", 18.0),
            _probe("2026-11-17", 18.0),
            _probe("2026-11-17", 16.0, bid=BLAU),
            _probe("2026-11-20", 18.0, status=gp.NICHT_PRUEFBAR),
            _probe(NEU_TAG, 20.0),
        ]
    )
    vorher = _messung(ALT_TAG, 18.0)
    e = gb.alter_preis(proben, vorher, NEU_TAG)
    assert (e.datum, e.buendel_id, e.status) == ("2026-11-17", BID, gp.BESTAETIGT)
    assert gb.alter_preis(proben, _messung(ALT_TAG, 17.0), NEU_TAG) is None


def test_alter_preis_darf_eine_andere_farbe_mit_gleichen_posten_sein():
    proben = Gegenproben([_probe("2026-11-17", 18.0, bid=BLAU)])
    e = gb.alter_preis(proben, _messung(ALT_TAG, 18.0), NEU_TAG)
    assert e is not None and e.buendel_id == BLAU


def test_neuer_preis_ist_die_pruefung_des_aenderungstags():
    proben = Gegenproben([_probe("2026-11-21", 20.0), _probe(NEU_TAG, 20.0)])
    e = gb.neuer_preis(proben, _messung(NEU_TAG, 20.0), NEU_TAG)
    assert e.datum == NEU_TAG
    assert gb.neuer_preis(proben, _messung(NEU_TAG, 21.0), NEU_TAG) is None


def test_ungeoeffnete_pruefung_des_tages_steht_mit_grund():
    offen = _probe(
        NEU_TAG,
        20.0,
        status=gp.NICHT_GEGENGEPRUEFT,
        grund=gp.GRUND_ZEITBUDGET,
        bild=None,
    )
    e = gb.neuer_preis(Gegenproben([offen]), _messung(NEU_TAG, 20.0), NEU_TAG)
    assert e is offen


def _tage():
    return [
        (ALT_TAG, [_messung(ALT_TAG, 18.0)]),
        (NEU_TAG, [_messung(NEU_TAG, 20.0)]),
    ]


def test_verlinkt_sind_preisbild_und_beide_tage_der_aenderung():
    alt, neu = _probe("2026-11-17", 18.0), _probe(NEU_TAG, 20.0)
    fremd = _probe("2026-11-10", 99.0)
    proben = Gegenproben([alt, neu, fremd])
    angezeigt = [{**_messung(NEU_TAG, 20.0)}]
    urls = gb.verlinkte(NEU_TAG, angezeigt, lambda s: None, proben, _tage())
    assert urls == {alt.bild, neu.bild}


def test_bilder_bleiben_hoechstens_die_aufbewahrungsfrist():
    alt, neu = _probe("2026-11-17", 18.0), _probe(NEU_TAG, 20.0)
    assert gb.aufbewahrt("2027-02-15", "2026-11-17")
    assert not gb.aufbewahrt("2027-02-16", "2026-11-17")
    proben = Gegenproben([alt, neu])
    urls = gb.verlinkte("2027-02-16", [], lambda s: None, proben, _tage())
    assert urls == {neu.bild}
    assert gb.verlinkte("2027-03-01", [], lambda s: None, proben, _tage()) == set()


def test_mit_bild_zaehlt_nur_ganze_konfiguration_im_fenster():
    saetze = [
        _messung(NEU_TAG, 20.0),
        _messung(NEU_TAG, 20.0, BLAU),
        _messung(NEU_TAG, 20.0, BID.replace("256gb", "512gb")),
    ]
    proben = Gegenproben(
        [
            _probe(NEU_TAG, 20.0),
            _probe(NEU_TAG, 20.0, bid=BLAU, bild_ohne=["Speicher"]),
        ]
    )
    bilanz = bz.zusammenfassung(NEU_TAG, saetze, proben, [])
    o2 = bilanz["anbieter"]["o2"]
    assert (o2["angezeigt"], o2["im_fenster"], o2["mit_bild"]) == (3, 2, 1)
    ganz = [
        s
        for s in saetze
        if gb.bild_ganz(proben.letzte_gute(s["id"], bz.gesamt_von(s), s))
    ]
    assert o2["mit_bild"] == len(ganz)
    assert bilanz["summe"]["mit_bild"] == 1


def test_bild_vor_dem_22_11_zaehlt_nicht_als_konfiguration():
    assert not gb.bild_ganz(_probe(NEU_TAG, 20.0, bild_zeigt=None))
    assert not gb.bild_ganz(_probe(NEU_TAG, 20.0, bild=None))
    assert gb.bild_ganz(_probe(NEU_TAG, 20.0))


def _bilanzdatei(state, datum, anbieter):
    ordner = state / "gegenprobe" / "bilanz"
    ordner.mkdir(parents=True, exist_ok=True)
    daten = {"format": 1, "datum": datum, "fenster_tage": 7, "anbieter": anbieter}
    (ordner / f"{datum}.json").write_text(json.dumps(daten), encoding="utf-8")


def test_zeile_je_anbieter_liest_die_felder_der_bilanz(tmp_path):
    _bilanzdatei(
        tmp_path,
        NEU_TAG,
        {
            "o2": {"name": "o2", "angezeigt": 2704, "im_fenster": 812, "mit_bild": 790},
            "telekom": {"name": "Telekom", "angezeigt": 10, "im_fenster": 3},
        },
    )
    gs = stand.stand(tmp_path, NEU_TAG)
    assert [z["name"] for z in gs["zeilen"]] == ["Telekom", "o2"]
    o2 = gs["zeilen"][1]
    assert (o2["im_fenster"], o2["angezeigt"], o2["mit_bild"]) == (812, 2704, 790)
    assert o2["satz"] == ("o2: 812 von 2.704 in 7 Tagen gegengeprüft · 790 mit Bild")
    assert gs["zeilen"][0]["satz"].endswith("gegengeprüft")
    assert gs["stand"] == ""


def test_aeltere_bilanz_traegt_den_stand_und_fehlende_ist_benannt(tmp_path):
    assert stand.stand(tmp_path, NEU_TAG)["fehlt"] == stand.FEHLT
    _bilanzdatei(tmp_path, "2026-11-20", {})
    gs = stand.stand(tmp_path, NEU_TAG)
    assert gs["stand"] == "Stand vom 20.11." and gs["fehlt"] == ""
    (tmp_path / "gegenprobe" / "bilanz" / "2026-11-21.json").write_text("{kaputt")
    assert stand.stand(tmp_path, NEU_TAG)["fehlt"].startswith(
        "Gegenprobe: Bilanz unlesbar"
    )


def test_belege_manifest_loescht_nur_nicht_verlinkte_gegenprobe_bilder(tmp_path):
    heute = date(2026, 12, 10)
    alt = "gegenprobe-2026-11-22-o2"
    gb.schreibe_verlinkt(tmp_path, "2026-12-09", [ga.url(alt, "a.webp")])
    modul = lade_skript("belege_manifest")
    gh = AttrappeReleases({alt: ["a.webp", "b.webp"]})
    plan = modul.gegenprobe_plan(tmp_path, heute, gh)
    assert plan.dateien == [(alt, "b.webp")]
    assert modul.loesche_gegenprobe(plan, gh) == []
    assert gh.assets_geloescht == [(alt, "b.webp")]
    assert ga.als_abschnitt(heute, plan.bleibt)["anhaenge"] == {alt: ["a.webp"]}


def test_ohne_frische_verweisliste_loescht_niemand(tmp_path):
    heute = date(2026, 12, 10)
    alt = "gegenprobe-2026-11-22-o2"
    modul = lade_skript("belege_manifest")
    gh = AttrappeReleases({alt: ["a.webp"]})
    assert modul.gegenprobe_plan(tmp_path, heute, gh).dateien == []
    gb.schreibe_verlinkt(tmp_path, "2026-11-30", [])
    plan = modul.gegenprobe_plan(tmp_path, heute, gh)
    assert plan.releases == [] and plan.dateien == []


def test_aenderung_behaelt_beide_bilder_bis_zur_frist():
    """Prüfer PR 204: eine 45 Tage alte Änderung zeigt weiter beide Tage."""
    proben = Gegenproben([_probe("2026-11-28", 5.0), _probe("2026-12-01", 9.5)])
    tage = [
        ("2026-11-28", [_messung("2026-11-28", 5.0)]),
        ("2026-12-01", [_messung("2026-12-01", 9.5)]),
    ]
    assert len(gb.verlinkte("2027-01-15", [], lambda s: None, proben, tage)) == 2


def _loeschlauf(tmp_path, schreibe):
    """``erneuere`` des Belege-Skripts mit einer Gegenprobe-Attrappe."""
    alt = "gegenprobe-2026-11-01-o2"
    schreibe(tmp_path)
    gh = AttrappeReleases({alt: ["a.webp", "b.webp"]})
    lade_skript("belege_manifest").erneuere(
        tmp_path, date(2026, 12, 10), False, AttrappeReleases(), gh
    )
    return gh


def _verweis_kaputt(pfad):
    (pfad / gb.VERLINKT).parent.mkdir(parents=True, exist_ok=True)
    (pfad / gb.VERLINKT).write_text("{kaputt", encoding="utf-8")


def _verweis_text(pfad):
    (pfad / gb.VERLINKT).parent.mkdir(parents=True, exist_ok=True)
    daten = {"format": 1, "datum": "2026-12-09", "bilder": 5}
    (pfad / gb.VERLINKT).write_text(json.dumps(daten), encoding="utf-8")


@pytest.mark.parametrize(
    "schreibe",
    [
        lambda p: gb.schreibe_verlinkt(p, "2026-12-09", []),
        lambda p: None,
        _verweis_kaputt,
        _verweis_text,
    ],
    ids=["leer", "fehlt", "kaputt", "text-statt-liste"],
)
def test_ohne_brauchbare_verweisliste_loescht_niemand(tmp_path, schreibe):
    """Prüfer PR 204: eine frische, aber leere Liste löschte alles über 9 Tage."""
    gh = _loeschlauf(tmp_path, schreibe)
    assert gh.releases_geloescht == [] and gh.assets_geloescht == []


def test_verweisliste_mit_zu_wenigen_jungen_bildern_ist_unplausibel():
    heute = date(2026, 12, 10)
    jung = "gegenprobe-2026-12-08-o2"
    anhaenge = {jung: ["a.webp", "b.webp", "c.webp"]}
    eins = {ga.url(jung, "a.webp")}
    assert "1 von 3" in ga.unplausibel(anhaenge, eins, heute)
    zwei = eins | {ga.url(jung, "b.webp")}
    assert ga.unplausibel(anhaenge, zwei, heute) is None
