"""Geräteseite und „Preisänderungen“ zeigen je Preis den Beleg mit allen sechs Teilen
(Bild, Quelle, Messzeit, Rohwerte, Rechenweg, Gegenprobe) und je Änderung beide Tage
mit Bild; fehlt etwas, steht die Lücke mit Grund da (Abnahmekriterium 3). Wegwerfseite
aus festen Daten, kein Netz, keine Uhr."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import test_geraete_buendel_kopf_zeitraum as kopf
from bs4 import BeautifulSoup
from test_geraete_preisaenderungen import O2, TAG, VORTAG

from telco_radar import gegenprobe as gp
from telco_radar.report import geraete_preisaenderungen as pa
from telco_radar.report import geraete_preisbeleg as pb
from telco_radar.report.html import render_site

GANZ = ["Gerät", "Speicher", "Tarif", "Raten", "Preis"]


def _zeile(bid: str, datum: str, rate: float) -> dict:
    """Eine gemessene Zeile der Preishistorie (wie in test_geraete_preisaenderungen)."""
    return {
        "id": bid,
        "datum": datum,
        "abgerufen_am": datum,
        "tarif_id": "o2:klein",
        "tarif_monatlich": 24.99,
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": rate,
        "laufzeit_monate": 24,
        "anschlusspreis": 0.0,
        "quelle_url": f"https://example.de/{datum}",
        "rechenweise": 1,
        "gesamt": 1.0,
    }


def _historie(state: Path, tage: dict[str, list[dict]]) -> None:
    ordner = state / "geraete_tco_historie"
    ordner.mkdir(exist_ok=True)
    for datum, zeilen in tage.items():
        (ordner / f"{datum}.jsonl").write_text(
            "".join(json.dumps(z) + "\n" for z in zeilen), encoding="utf-8"
        )


RELEASES = "https://github.com/Antonio20045/telco-radar/releases/download"
BILD_ALT = f"{RELEASES}/gegenprobe-{VORTAG}-o2/alt0000000000000.webp"
BILD_NEU = f"{RELEASES}/gegenprobe-{TAG}-o2/neu0000000000000.webp"


def _probe(datum: str, rate: float, bild: str, **anders) -> gp.Ergebnis:
    werte = {
        "datum": datum,
        "buendel_id": O2,
        "anbieter": "o2",
        "status": gp.BESTAETIGT,
        "anlass": gp.ANLASS_AENDERUNG,
        "geprueft_um": f"{datum}T05:00:00+00:00",
        "gemessen_um": f"{datum}T03:10:00+00:00",
        "gespeichert": gp.gespeicherte_werte(_zeile(O2, datum, rate)),
        "gelesen": {"roh": {"Gerät monatlich": f"{rate:.2f} €"}},
        "bild": bild,
        "bild_zeigt": GANZ,
        "bild_ohne": [],
    }
    werte.update(anders)
    return gp.Ergebnis(**werte)


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """o2 ändert die Rate von 16 auf 18 €; der alte Preis ist am Vortag gegengeprüft,
    der neue am Tag der Änderung, beide mit Konfigurationsbild. congstar ist nie
    gegengeprüft. Die Bilanz des Tages nennt je Anbieter die Zahlen."""
    site = kopf._baue(tmp_path_factory.mktemp("k3"))
    state = site.parent / "data" / "state"
    _historie(state, {VORTAG: [_zeile(O2, VORTAG, 16.0)], TAG: [_zeile(O2, TAG, 18.0)]})
    gp.schreibe_tag(
        gp.tagesdatei(site.parent, VORTAG), [_probe(VORTAG, 16.0, BILD_ALT)]
    )
    neu = _probe(TAG, 18.0, BILD_NEU, gesamt_gespeichert=kopf._SOLL["o2"])
    gp.schreibe_tag(gp.tagesdatei(site.parent, TAG), [neu])
    bilanz = state / "gegenprobe" / "bilanz"
    bilanz.mkdir(parents=True)
    (bilanz / f"{TAG}.json").write_text(
        json.dumps(
            {
                "format": 1,
                "datum": TAG,
                "fenster_tage": 7,
                "anbieter": {
                    "o2": {
                        "name": "o2",
                        "angezeigt": 3,
                        "im_fenster": 1,
                        "mit_bild": 1,
                    },
                    "congstar": {
                        "name": "congstar",
                        "angezeigt": 2,
                        "im_fenster": 0,
                        "mit_bild": 0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    render_site(site, site.parent / "data" / "reports")
    return site


def _suppe(pfad: Path) -> BeautifulSoup:
    return BeautifulSoup(pfad.read_text(encoding="utf-8"), "html.parser")


def _belege(site) -> dict:
    suppe = _suppe(site / "geraete.html")
    return {b["data-anbieter"]: b for b in suppe.select("#gr-bnd-gruppe .gr-pb")}


def test_beleg_je_preis_hat_alle_sechs_teile(site):
    o2 = _belege(site)["o2"]
    daten = {
        dt.get_text(strip=True): dd
        for dt, dd in zip(o2.select("dl dt"), o2.select("dl dd"), strict=True)
    }
    assert {
        "Quelle",
        "Gemessen",
        "Rohwerte",
        "Rechenweg",
        "Screenshot",
        "Gegenprobe",
    } <= set(daten)
    assert daten["Quelle"].select_one("a")["href"].startswith("https://example.de/")
    assert daten["Gemessen"].get_text(strip=True).startswith("11.09.2026")
    roh = daten["Rohwerte"].get_text(" ", strip=True)
    assert "Geräterate: 18,00 €" in roh and "Gerät monatlich: 18.00 €" in roh
    assert daten["Rechenweg"].select(".gr-pb-term")
    img = daten["Screenshot"].select_one("img.gr-pb-bild")
    assert img["data-src"] == BILD_NEU and not img.get("src")
    assert (
        "zeigt Gerät, Speicher, Tarif, Raten, Preis" in daten["Screenshot"].get_text()
    )
    assert daten["Gegenprobe"].select_one(".gr-pb-gp--bestaetigt") is not None
    assert "Gegenprobe 11.09.2026" in daten["Gegenprobe"].get_text(" ", strip=True)


def test_preis_ohne_gegenprobe_nennt_luecke_und_frist(site):
    text = _belege(site)["congstar"].get_text(" ", strip=True)
    assert "Kein Screenshot zu diesem Preis: noch nicht gegengeprüft" in text
    assert "Noch nicht gegengeprüft (fällig bis 18.09.2026)" in text


def test_preisaenderung_zeigt_beide_tage_mit_bild(site):
    tag = _suppe(site / pa.ORDNER / f"{TAG}.html")
    zeile = tag.select_one(".pa-zeile")
    vorher, neu = zeile.select(".pa-tagbeleg")
    assert vorher.select_one(".pa-vorschau img")["src"] == BILD_ALT
    assert neu.select_one(".pa-vorschau img")["src"] == BILD_NEU
    assert "Gegenprobe vom 10.09.2026" in vorher.select_one(".pa-vorschau").get_text()
    assert vorher.select_one(".gr-pb-gp--bestaetigt") is not None
    assert neu.select_one(".gr-pb-gp--bestaetigt") is not None
    zeile_csv = pa.csv_text({"aenderungen": [_eintrag(site)]}).splitlines()[1]
    assert BILD_NEU in zeile_csv and BILD_ALT in zeile_csv


def _eintrag(site) -> dict:
    state = site.parent / "data" / "state"
    proben = pb.Gegenproben(gp.lies_alle(state / "gegenprobe").values())
    (tag,) = [
        t
        for t in pa.aufbereiten(state, {}, proben, lambda k: None)
        if t["datum"] == TAG
    ]
    return tag["aenderungen"][0]


def test_vortag_ohne_gute_pruefung_ist_benannte_luecke(tmp_path):
    kopf_state = tmp_path
    _historie(
        kopf_state, {VORTAG: [_zeile(O2, VORTAG, 16.0)], TAG: [_zeile(O2, TAG, 18.0)]}
    )
    (kopf_state / "geraete_tco.json").write_text(json.dumps({"buendel": []}), "utf-8")
    proben = pb.Gegenproben([_probe(TAG, 18.0, BILD_NEU)])
    (tag,) = pa.aufbereiten(kopf_state, {}, proben, lambda k: None)
    a = tag["aenderungen"][0]
    assert a["alt"]["beleg"]["konfig"] is None
    assert a["alt"]["beleg"]["konfig_fehlt"].endswith(
        ": keine gute Gegenprobe des alten Preises"
    )
    assert a["neu"]["beleg"]["konfig"]["url"] == BILD_NEU


def test_geloeschtes_bild_ist_benannt_nicht_tot_verlinkt():
    from telco_radar.gegenprobe_ablage import Liste

    alt = _probe("2026-08-01", 16.0, f"{RELEASES}/gegenprobe-2026-08-01-o2/x.webp")
    liste = Liste(date(2026, 9, 11), frozenset())
    bild, grund = pb.konfig(alt, liste)
    assert bild is None and grund == "nicht mehr im Release"
    assert pb.konfig(alt, None)[0]["url"] == alt.bild


def test_bild_nur_des_preisbereichs_ist_als_solches_benannt():
    e = _probe(TAG, 18.0, BILD_NEU, bild_zeigt=None, bild_ohne=None)
    bild, _ = pb.konfig(e)
    assert bild["nur_preis"] and bild["zeigt"] == ""
    teil = _probe(
        TAG, 18.0, BILD_NEU, bild_zeigt=["Tarif", "Preis"], bild_ohne=["Speicher"]
    )
    assert pb.konfig(teil)[0]["ohne"] == "Speicher"


def test_zeile_je_anbieter_steht_auf_der_seite_wie_in_der_bilanz(site):
    suppe = _suppe(site / "geraete.html")
    zeilen = {z["data-anbieter"]: z for z in suppe.select("#gegenprobe-stand .gr-gs-z")}
    daten = json.loads(
        (site.parent / "data/state/gegenprobe/bilanz" / f"{TAG}.json").read_text()
    )["anbieter"]
    assert set(zeilen) == set(daten)
    for schluessel, z in zeilen.items():
        e = daten[schluessel]
        assert int(z["data-im-fenster"]) == e["im_fenster"]
        assert int(z["data-angezeigt"]) == e["angezeigt"]
        assert int(z["data-mit-bild"]) == e["mit_bild"]
        assert z.get_text(" ", strip=True).startswith(
            f"{e['name']}: {e['im_fenster']} von {e['angezeigt']} in 7 Tagen"
        )
        assert f"· {e['mit_bild']} mit Bild" in z.get_text(" ", strip=True)


def test_alter_preis_zeigt_das_bild_seiner_letzten_guten_pruefung(tmp_path):
    """Der alte Preis ist am 08.09. gemessen und am 09.09. gegengeprüft (ohne neue
    Messung), am 11.09. ändert er sich: der Beleg „vorher“ zeigt das Bild vom 09.09.
    Bis 21.11.2026 bekam der Vortag nie ein Bild (nur eine Prüfung genau am Messtag)."""
    gemessen, geprueft = "2026-09-08", "2026-09-09"
    _historie(
        tmp_path, {gemessen: [_zeile(O2, gemessen, 16.0)], TAG: [_zeile(O2, TAG, 18.0)]}
    )
    (tmp_path / "geraete_tco.json").write_text(json.dumps({"buendel": []}), "utf-8")
    probe = gp.Ergebnis(
        datum=geprueft,
        buendel_id=O2,
        anbieter="o2",
        status=gp.BESTAETIGT,
        anlass=gp.ANLASS_FENSTER,
        gespeichert=gp.gespeicherte_werte(_zeile(O2, gemessen, 16.0)),
        bild=BILD_ALT,
    )
    (tag,) = pa.aufbereiten(tmp_path, {}, pb.Gegenproben([probe]), lambda k: None)
    alt = tag["aenderungen"][0]["alt"]["beleg"]
    assert alt["bild"] is not None, "Vortag ohne Bild"
    assert (alt["bild"]["url"], alt["bild"]["datum"]) == (BILD_ALT, "09.09.2026")
    assert alt["gegenprobe"]["wort"] == "bestätigt"


def test_bild_nach_der_aufbewahrungsfrist_ist_benannte_luecke():
    from telco_radar.gegenprobe_belege import AUFBEWAHRUNG_TAGE, GRUND_ALT

    alt = _probe("2026-08-01", 16.0, f"{RELEASES}/gegenprobe-2026-08-01-o2/x.webp")
    bild, grund = pb.konfig(alt, None, "2026-09-11")
    assert bild is None and grund == GRUND_ALT
    assert str(AUFBEWAHRUNG_TAGE) in grund
    assert pb.konfig(alt, None, "2026-08-31")[0]["url"] == alt.bild
