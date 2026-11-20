"""Preisänderungen je Messtag mit Beleg beider Tage (``geraete_preisaenderungen``)
und der Beleg je Preiszeile auf der Geräteseite.

Feste Daten (CLAUDE.md Regel 7): ein Wegwerf-Bestand mit zwei Messtagen; die Seite
wird mit ``render_site`` gebaut (Bestand von ``test_geraete_buendel_kopf_zeitraum``).
"""

from __future__ import annotations

import csv
import functools
import http.server
import io
import json
import threading
from pathlib import Path

import pytest
import test_geraete_buendel_kopf_zeitraum as kopf
from bs4 import BeautifulSoup

from telco_radar import gegenprobe as gp
from telco_radar import tco_historie
from telco_radar.report import geraete_preisaenderungen as pa
from telco_radar.report.geraete_preisbeleg import Gegenproben
from telco_radar.report.html import render_site
from telco_radar.tco_model import buendel_id

VORTAG, TAG = "2026-09-10", kopf.HEUTE
SKU = kopf._sku(kopf.DEVICE, 256)
O2 = buendel_id(SKU, "o2", "O2 Mobile Klein", 24)
CS = buendel_id(SKU, "congstar", "Allnet Flat XS", 24)


def _zeile(bid, datum, rate, **anders):
    werte = {
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
    werte.update(anders)
    return werte


def _historie(state: Path, tage: dict[str, list[dict]]) -> None:
    ordner = state / "geraete_tco_historie"
    ordner.mkdir(exist_ok=True)
    for datum, zeilen in tage.items():
        (ordner / f"{datum}.jsonl").write_text(
            "".join(json.dumps(z) + "\n" for z in zeilen), encoding="utf-8"
        )


def _bestand(state: Path) -> None:
    satz = {
        "id": O2,
        "sku_id": SKU,
        "anbieter": "o2",
        "tarif_name": "O2 Mobile Klein",
        "tarif_id": "o2:klein",
    }
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": TAG, "buendel": [satz]}), encoding="utf-8"
    )


def _tage(tmp_path, zeilen_vortag, zeilen_tag, proben=()):
    _bestand(tmp_path)
    _historie(tmp_path, {VORTAG: zeilen_vortag, TAG: zeilen_tag})
    return pa.aufbereiten(tmp_path, {}, Gegenproben(proben), lambda karte: None)


def test_geaenderte_rate_steht_mit_beiden_tagen_und_differenz(tmp_path):
    tage = _tage(tmp_path, [_zeile(O2, VORTAG, 18.0)], [_zeile(O2, TAG, 20.0)])
    assert [t["datum"] for t in tage] == [TAG]
    a = tage[0]["aenderungen"][0]
    assert a["posten"] == ["Geräterate 18,00 € → 20,00 €"]
    assert a["delta"] == pytest.approx(24 * 2.0)
    assert a["neu"]["gesamt"] - a["alt"]["gesamt"] == pytest.approx(a["delta"])
    assert a["alt"]["beleg"]["quelle_url"] == f"https://example.de/{VORTAG}"
    assert a["neu"]["beleg"]["gelesen_am"] == "11.09.2026"


def test_rechenweg_beider_tage_ergibt_ihre_summe(tmp_path):
    tage = _tage(tmp_path, [_zeile(O2, VORTAG, 18.0)], [_zeile(O2, TAG, 20.0)])
    a = tage[0]["aenderungen"][0]
    for t in (a["alt"], a["neu"]):
        assert t["beleg"]["rechenweg"]["text"].endswith(f"= {pa.euro(t['gesamt'])}")


def test_unveraenderter_preis_ist_keine_aenderung(tmp_path):
    assert _tage(tmp_path, [_zeile(O2, VORTAG, 18.0)], [_zeile(O2, TAG, 18.0)]) == []


def test_nur_andere_rechenweise_ist_keine_aenderung(tmp_path):
    alt = _zeile(O2, VORTAG, 18.0, gesamt=900.0, rechenweise=1)
    neu = _zeile(O2, TAG, 18.0, gesamt=950.0, rechenweise=2)
    assert _tage(tmp_path, [alt], [neu]) == []


def test_nicht_gemessene_zeile_zaehlt_nicht(tmp_path):
    neu = _zeile(O2, TAG, 20.0, abgerufen_am=VORTAG)
    assert _tage(tmp_path, [_zeile(O2, VORTAG, 18.0)], [neu]) == []


def test_letzte_messung_davor_auch_ueber_eine_luecke(tmp_path):
    _bestand(tmp_path)
    _historie(
        tmp_path,
        {
            "2026-09-08": [_zeile(O2, "2026-09-08", 18.0)],
            VORTAG: [],
            TAG: [_zeile(O2, TAG, 20.0)],
        },
    )
    tage = pa.aufbereiten(tmp_path, {}, Gegenproben(), lambda k: None)
    assert tage[0]["aenderungen"][0]["alt"]["datum"] == "2026-09-08"


def test_groesste_aenderung_zuerst(tmp_path):
    tage = _tage(
        tmp_path,
        [_zeile(O2, VORTAG, 18.0), _zeile(CS, VORTAG, 10.0)],
        [_zeile(O2, TAG, 19.0), _zeile(CS, TAG, 15.0)],
    )
    assert [a["id"] for a in tage[0]["aenderungen"]] == [CS, O2]


def test_buendel_ausserhalb_des_bestands_rechnet_aus_seinem_schluessel(tmp_path):
    tage = _tage(tmp_path, [_zeile(CS, VORTAG, 10.0)], [_zeile(CS, TAG, 15.0)])
    a = tage[0]["aenderungen"][0]
    assert (a["anbieter"], a["geraet"]) == ("congstar", SKU)
    assert a["delta"] == pytest.approx(24 * 5.0)


def test_gegenprobe_des_tages_steht_am_beleg_und_in_der_bilanz(tmp_path):
    probe = gp.Ergebnis(
        datum=TAG,
        buendel_id=O2,
        anbieter="o2",
        status=gp.ABWEICHEND,
        anlass=gp.ANLASS_AENDERUNG,
        abweichungen=[
            {"feld": "geraet_monatsrate", "gespeichert": 20.0, "gelesen": 18.0}
        ],
    )
    tage = _tage(tmp_path, [_zeile(O2, VORTAG, 18.0)], [_zeile(O2, TAG, 20.0)], [probe])
    a = tage[0]["aenderungen"][0]
    assert a["neu"]["beleg"]["gegenprobe"]["wort"] == "abweichend"
    assert a["alt"]["beleg"]["gegenprobe"] is None
    assert tage[0]["gegenprobe"] == {
        gp.BESTAETIGT: 0,
        gp.TEILWEISE: 0,
        gp.ABWEICHEND: 1,
        gp.NICHT_PRUEFBAR: 0,
        "offen": 0,
    }


def test_nur_eingefrorenes_gesamt_anders_ist_keine_preisaenderung(tmp_path):
    alt = _zeile(O2, VORTAG, 18.0, gesamt=900.0)
    neu = _zeile(O2, TAG, 18.0, gesamt=950.0)
    assert _tage(tmp_path, [alt], [neu]) == []


def test_seite_und_auswahl_der_gegenprobe_zaehlen_dieselben_aenderungen(tmp_path):
    """Lücke im Vortag: die Seite vergleicht mit der letzten Messung davor, die
    Auswahl der Gegenprobe ebenso (eine Definition, ``gegenprobe.aenderungen``)."""
    _bestand(tmp_path)
    _historie(
        tmp_path,
        {
            "2026-09-08": [
                _zeile(O2, "2026-09-08", 18.0),
                _zeile(CS, "2026-09-08", 9.0),
            ],
            VORTAG: [_zeile(CS, VORTAG, 10.0)],
            TAG: [_zeile(O2, TAG, 20.0), _zeile(CS, TAG, 10.0)],
        },
    )
    seite = pa.aufbereiten(tmp_path, {}, Gegenproben(), lambda k: None)
    tage = tco_historie.tage(tmp_path / pa.HISTORIE)
    vorher = gp.letzte_messungen([(d, s) for d, s in tage if d < TAG])
    heute = next(s for d, s in tage if d == TAG)
    wahl = [b for b, a in gp.auswahl(TAG, heute, vorher.values(), 0)]
    neu = {a["id"] for t in seite if t["datum"] == TAG for a in t["aenderungen"]}
    assert neu == set(wahl) == {O2}


def test_zeitbudget_zaehlt_als_nicht_gegengeprueft(tmp_path):
    probe = gp.Ergebnis(
        datum=TAG,
        buendel_id=O2,
        anbieter="o2",
        status=gp.NICHT_PRUEFBAR,
        anlass=gp.ANLASS_AENDERUNG,
        grund=gp.GRUND_ZEITBUDGET,
    )
    tage = _tage(tmp_path, [_zeile(O2, VORTAG, 18.0)], [_zeile(O2, TAG, 20.0)], [probe])
    assert tage[0]["gegenprobe"][pa.OFFEN] == 1
    assert tage[0]["gegenprobe"][gp.NICHT_PRUEFBAR] == 0


def test_export_traegt_jede_aenderung_mit_belegangaben(tmp_path):
    tage = _tage(
        tmp_path,
        [_zeile(O2, VORTAG, 18.0), _zeile(CS, VORTAG, 10.0)],
        [_zeile(O2, TAG, 19.0), _zeile(CS, TAG, 15.0)],
    )
    zeilen = list(csv.reader(io.StringIO(pa.csv_text(tage[0])), delimiter=";"))
    assert tuple(zeilen[0]) == pa.CSV_SPALTEN
    assert len(zeilen) == 1 + 2
    o2 = next(z for z in zeilen[1:] if z[0] == "o2")
    spalte = dict(zip(pa.CSV_SPALTEN, o2, strict=True))
    assert spalte["Änderung EUR"] == "24.00"
    assert spalte["Rechenweg"].startswith("24 × 19,00 € Gerät")
    assert spalte["Quelle vorher"] == f"https://example.de/{VORTAG}"


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """Wegwerfseite: o2 ändert die Rate von 18 auf 20 €, die Gegenprobe des Tages
    bestätigt den neuen Preis (gleiche Gesamtkosten)."""
    site = kopf._baue(tmp_path_factory.mktemp("preisaenderungen"))
    state = site.parent / "data" / "state"
    _historie(state, {VORTAG: [_zeile(O2, VORTAG, 16.0)], TAG: [_zeile(O2, TAG, 18.0)]})
    gesamt = kopf._SOLL["o2"]
    gp.schreibe_tag(
        gp.tagesdatei(site.parent, TAG),
        [
            gp.Ergebnis(
                datum=TAG,
                buendel_id=O2,
                anbieter="o2",
                status=gp.BESTAETIGT,
                anlass=gp.ANLASS_AENDERUNG,
                geprueft_um=f"{TAG}T05:00:00+00:00",
                gesamt_gespeichert=gesamt,
            )
        ],
    )
    render_site(site, site.parent / "data" / "reports")
    return site


def _suppe(pfad: Path) -> BeautifulSoup:
    return BeautifulSoup(pfad.read_text(encoding="utf-8"), "html.parser")


def test_jede_preiszeile_hat_ihren_beleg(site):
    suppe = _suppe(site / "geraete.html")
    belege = suppe.select("#gr-bnd-gruppe .gr-preisbelege .gr-pb")
    assert {b["data-anbieter"] for b in belege} == set(kopf._SOLL)
    for b in belege:
        rw = b.select_one(".gr-pb-rw")
        assert rw.select(".gr-pb-term"), b["data-anbieter"]
        ergebnis = rw.select_one(".gr-pb-ergebnis").get_text(strip=True)
        summe = b.select_one(".gr-pb-summe").get_text(strip=True)
        assert ergebnis == summe == pa.euro(kopf._SOLL[b["data-anbieter"]])


def test_terme_der_seite_ergeben_die_summe(site):
    suppe = _suppe(site / "geraete.html")
    for b in suppe.select("#gr-bnd-gruppe .gr-pb"):
        summe = 0.0
        for t in b.select(".gr-pb-term"):
            text = t.get_text(" ", strip=True)
            betrag = float(
                text.split("€")[0]
                .split("×")[-1]
                .strip()
                .replace(".", "")
                .replace(",", ".")
            )
            anzahl = int(text.split("×")[0]) if "×" in text else 1
            summe += anzahl * betrag
        assert round(summe, 2) == kopf._SOLL[b["data-anbieter"]], b["data-anbieter"]


def test_gegenprobe_und_luecken_stehen_benannt_an_der_zeile(site):
    suppe = _suppe(site / "geraete.html")
    je = {b["data-anbieter"]: b for b in suppe.select("#gr-bnd-gruppe .gr-pb")}
    assert je["o2"].select_one(".gr-pb-gp--bestaetigt") is not None
    assert "07:00 Uhr" in je["o2"].get_text(" ", strip=True)
    congstar = je["congstar"].get_text(" ", strip=True)
    assert "nicht gegengeprüft" in congstar
    assert "Noch nicht gegengeprüft" in congstar
    assert "Kein Screenshot zu diesem Preis" in congstar


def test_seite_preisaenderungen_listet_den_tag_mit_beleg(site):
    uebersicht = _suppe(site / pa.SEITE)
    link = uebersicht.select_one(".pa-tageszeile a.pa-datum")
    assert link["href"] == f"{pa.ORDNER}/{TAG}.html"
    assert "1 Preis geändert" in uebersicht.select_one(".pa-zahl").get_text()
    tag = _suppe(site / pa.ORDNER / f"{TAG}.html")
    zeile = tag.select_one(".pa-zeile")
    assert "Geräterate 16,00 € → 18,00 €" in zeile.get_text(" ", strip=True)
    belege = zeile.select(".pa-beleg")
    assert len(belege) == 2
    assert belege[1].select_one(".gr-pb-gp--bestaetigt") is not None
    assert (site / pa.ORDNER / f"{TAG}.csv").is_file()


def test_geraeteseite_verlinkt_die_preisaenderungen(site):
    suppe = _suppe(site / "geraete.html")
    assert suppe.select_one(f'a[href="{pa.SEITE}"]') is not None


def _sichtbar(chromium, site: Path, laufzeit: str, breite: int) -> dict:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    ctx = chromium.new_context(viewport={"width": breite, "height": 900})
    try:
        s = ctx.new_page()
        fehler: list[str] = []
        s.on("pageerror", lambda e: fehler.append(str(e)))
        port = httpd.server_address[1]
        s.goto(
            f"http://127.0.0.1:{port}/geraete.html?laufzeit={laufzeit}",
            wait_until="domcontentloaded",
        )
        s.wait_for_selector("#gr-bnd-gruppe .gr-preisbelege", state="attached")
        s.wait_for_timeout(300)
        liste = s.locator("#gr-bnd-gruppe .gr-preisbelege")
        zahl = s.locator("#gr-bnd-gruppe .gr-pb-zahl").inner_text()
        liste.locator(".gr-pb-kopf").click()
        zeilen = s.locator("#gr-bnd-gruppe .gr-pb")
        sichtbar = [
            zeilen.nth(i).get_attribute("data-anbieter")
            for i in range(zeilen.count())
            if zeilen.nth(i).is_visible()
        ]
        kopf_sichtbar = liste.is_visible()
        if sichtbar:
            zeile = s.locator("#gr-bnd-gruppe .gr-pb:visible .gr-pb-zeile").first
            zeile.click()
            offen = zeile.get_attribute("aria-expanded")
            inhalt = s.locator("#gr-bnd-gruppe .gr-pb:visible .gr-pb-inhalt").first
            sichtbar_inhalt = inhalt.is_visible()
        else:
            offen, sichtbar_inhalt = None, False
        breit = s.evaluate("document.documentElement.scrollWidth")
        return {
            "anbieter": sichtbar,
            "kopf": kopf_sichtbar,
            "zahl": zahl,
            "offen": offen,
            "inhalt": sichtbar_inhalt,
            "breit": breit,
            "fehler": fehler,
        }
    finally:
        ctx.close()
        httpd.shutdown()


@pytest.mark.browser
@pytest.mark.parametrize("breite", [1440, 390])
def test_belege_folgen_der_gewaehlten_laufzeit(site, chromium, breite):
    """Im echten Chromium: unter 24 Raten nur die Belege der 24-Raten-Zeilen, unter
    36 nur der Telekom-Beleg; aufgeklappt kein Querscrollen, keine Skriptfehler."""
    v24 = _sichtbar(chromium, site, "24", breite)
    assert sorted(v24["anbieter"]) == ["Vodafone", "congstar", "o2"]
    v36 = _sichtbar(chromium, site, "36", breite)
    assert v36["anbieter"] == ["Telekom"]
    assert (v24["zahl"], v36["zahl"]) == ("· 3 Preise", "· 1 Preis")
    for v in (v24, v36):
        assert v["kopf"] and v["fehler"] == [] and v["breit"] <= breite
        assert v["offen"] == "true" and v["inhalt"]
