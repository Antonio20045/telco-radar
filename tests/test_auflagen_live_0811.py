"""Auflagen der Live-Abnahmen 08.11. 17:30 und 09.11.2026 auf geraete.html.

A6 (09.11.): die Katalogzeile „ab X €/Monat“ eines nur im Bündel geführten Geräts nannte
bei 1&1 (Vertrag „24 + 12“, 36 Monate) „mit 36 Raten“, obwohl die Summe 24 Beträge plus
Ablöse trägt. Dieselbe Regel wie am Zeilenetikett (`geraete_laufzeit.raten_text`).
Gegen den alten Stand rot: das Feld `buendel_raten_zusatz` gab es nicht, die Seite
schrieb „mit 36 Raten bei 1&1“. Gegenprobe: echte Raten (o2 24) behalten ihr Wort.
"""

from __future__ import annotations

import functools
import html
import http.server
import json
import re
import threading
from pathlib import Path

import pytest
import test_beleg_kombi as kombi
import test_beleg_position as pos
import test_geraete_buendel_kopf_zeitraum as kopf_zeitraum
import test_laufzeit_seite as seite
import test_laufzeit_vergleich as vergleich
from bestand_pfad import abbild, lese_wurzel
from bs4 import BeautifulSoup

from telco_radar.analyze import beleg_position
from telco_radar.beleg_manifest import MANIFEST_NAME, baue_manifest, schreibe
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import (
    geraete_view,
    geraete_zeitreihe,
    geraete_zeitreihe_legende,
    geraete_zeitreihe_uebertrag,
)
from telco_radar.report.html import render_site

ABLOESE = "24 Monate + Ablöse"


def _katalogtext(tmp_path, anbieter: str) -> str:
    buendel = [s for s in vergleich.bestand() if s["anbieter"] == anbieter]
    site = seite._baue_site(tmp_path, buendel, ohne_barpreis=True)
    suppe = BeautifulSoup((site / "geraete.html").read_text("utf-8"), "html.parser")
    zeile = next(
        z
        for z in suppe.select("#gr-katalogtabelle tr.gr-k-zeile")
        if z.get("data-modell") == vergleich.MODELL
    )
    return " ".join(zeile.get_text(" ", strip=True).split())


def test_a6_katalog_nennt_beim_1und1_vertrag_keine_36_raten(tmp_path):
    zeile = vergleich._nur_im_buendel(
        tmp_path / "a", [s for s in vergleich.bestand() if s["anbieter"] == "1&1"]
    )
    assert zeile["buendel_anbieter"] == "1&1" and zeile["buendel_raten"] == 36, zeile
    assert zeile["buendel_raten_zusatz"] == f" · {ABLOESE}", zeile
    text = _katalogtext(tmp_path / "b", "1&1")
    assert "36 Raten" not in text, text
    assert f"/Monat · {ABLOESE} bei 1&1" in text, text


def test_a6_gegenprobe_echte_raten_behalten_ihr_wort(tmp_path):
    zeile = vergleich._nur_im_buendel(
        tmp_path / "a", [s for s in vergleich.bestand() if s["anbieter"] == "o2"]
    )
    assert zeile["buendel_raten_zusatz"] == " mit 24 Raten", zeile
    assert "mit 24 Raten bei o2" in _katalogtext(tmp_path / "b", "o2")


HEUTE_BESTAND = "2026-10-03"
ZULETZT = re.compile(
    r"<i style='background:[^']*'></i>([^<]*?) "
    r"<span class='gr-zr-leg-wert'>[^<]*zuletzt ([\d.]+) €"
)


def _abweichungen(zustand) -> tuple[int, list]:
    wurzel = lese_wurzel()
    g = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE_BESTAND
    )
    zeilen = {}
    for m in g["tco"]["modelle"]:
        for lz in (12, 24, 36):
            for band, satz in geraete_zeitreihe.band_zeilen(m, lz).items():
                for z in satz["zeilen"]:
                    zeilen[(m["id"], band, lz, z["anbieter"])] = z["gesamt"]
    verglichen, abw = 0, []
    for p in g["zeitreihe"]["paare"]:
        for anbieter, zahl in ZULETZT.findall(p["legende_html"]):
            soll = zeilen.get(
                (p["modell"], p["band"], p["laufzeit"], anbieter.replace("&amp;", "&"))
            )
            if soll is None:
                continue
            verglichen += 1
            if f"{soll:,.0f}".replace(",", ".") != zahl:
                abw.append(
                    (p["modell"], p["band"], p["laufzeit"], anbieter, zahl, soll)
                )
    return verglichen, abw


@pytest.fixture(scope="module")
def zustand(tmp_path_factory):
    wurzel = tmp_path_factory.mktemp("a5")
    abbild(wurzel)
    return wurzel / "data" / "state"


def test_a5_legende_nennt_den_wert_der_zeile(zustand):
    verglichen, abw = _abweichungen(zustand)
    assert verglichen > 50, verglichen
    assert not abw, f"{len(abw)} von {verglichen}: {abw[:3]}"


def _mess(wert, datum, tarif_id, zaehlt=True, monate=24):
    return {
        "satz": {"datum": datum},
        "stand": {"tarif_id": tarif_id, "sku_id": "s"},
        "wert": wert,
        "monate": monate,
        "laufzeit": 24,
        "zaehlt": zaehlt,
    }


def _linie(heute="2026-11-08"):
    """1&1 im Band XS, 24 Raten: das günstige Bündel wurde gestern, ein teureres heute
    gelesen - der Fall S26 Ultra 256 (1.591,66 € gegen 1.711,66 €)."""
    guenstig = _mess(1591.66, "2026-11-07", "t-alt")
    teuer = _mess(1711.66, "2026-11-08", "t-neu")
    messungen = {
        ("m", "xs", 24): {
            "1&1": {"2026-11-07": guenstig, "2026-11-08": teuer},
        }
    }
    letzte = {
        ("m", "xs", 24, "1&1"): {
            "alt": ("2026-11-07", guenstig),
            "neu": ("2026-11-08", teuer),
        }
    }
    return messungen, letzte, heute


GEFUEHRT = {
    ("m", "xs", 24, "1&1", "t-alt", "s"),
    ("m", "xs", 24, "1&1", "t-neu", "s"),
}


def _uebertrage(messungen, letzte, heute, gefuehrt=GEFUEHRT):
    geraete_zeitreihe_uebertrag.gilt_weiter(messungen, letzte, heute, gefuehrt)


def test_a5_juengster_tag_traegt_das_guenstigste_frische_buendel():
    messungen, letzte, heute = _linie()
    _uebertrage(messungen, letzte, heute)
    slot = messungen[("m", "xs", 24)]["1&1"]
    assert slot["2026-11-08"]["wert"] == 1591.66, slot
    assert slot["2026-11-08"]["satz"]["datum"] == "2026-11-07"
    assert slot["2026-11-07"]["wert"] == 1591.66


def test_a5_gegenprobe_zu_altes_oder_nicht_zaehlendes_buendel_zieht_nicht():
    messungen, letzte, heute = _linie("2026-11-11")
    _uebertrage(messungen, letzte, heute)
    assert messungen[("m", "xs", 24)]["1&1"]["2026-11-08"]["wert"] == 1711.66
    messungen, letzte, heute = _linie()
    letzte[("m", "xs", 24, "1&1")]["alt"][1]["zaehlt"] = False
    _uebertrage(messungen, letzte, heute)
    assert messungen[("m", "xs", 24)]["1&1"]["2026-11-08"]["wert"] == 1711.66


def test_a5_ein_teureres_altes_buendel_verdraengt_das_heutige_nicht():
    messungen, letzte, heute = _linie()
    letzte[("m", "xs", 24, "1&1")]["alt"][1]["wert"] = 1800.0
    _uebertrage(messungen, letzte, heute)
    assert messungen[("m", "xs", 24)]["1&1"]["2026-11-08"]["wert"] == 1711.66


def test_a5_ein_buendel_ausserhalb_der_tafel_wird_nicht_uebertragen():
    """iPhone 14 128, o2, M: die Tafel führt „On Demand M Plus“, gelesen wurde aber
    „On Demand M“. Die Linie läuft dann nicht weiter."""
    messungen, letzte, heute = _linie()
    _uebertrage(messungen, letzte, heute, {("m", "xs", 24, "1&1", "t-neu", "s")})
    assert messungen[("m", "xs", 24)]["1&1"]["2026-11-08"]["wert"] == 1711.66


def test_a5_der_tooltip_nennt_den_lesetag_des_uebertragenen_punkts():
    messungen, letzte, heute = _linie()
    _uebertrage(messungen, letzte, heute)
    punkt = messungen[("m", "xs", 24)]["1&1"]["2026-11-08"]
    tag = geraete_zeitreihe_uebertrag.messtag("2026-11-08", punkt)
    assert tag == "2026-11-08" and tag.gelesen == "2026-11-07"
    text = geraete_zeitreihe_uebertrag.gelesen_text(tag, lambda t: t[-2:])
    assert text == " · gelesen am 07"
    gelesen = geraete_zeitreihe_uebertrag.messtag("2026-11-07", punkt)
    assert geraete_zeitreihe_uebertrag.gelesen_text(gelesen, str) == ""


def test_a5_kein_uebertragener_punkt_ohne_zeile_in_der_tafel(zustand):
    wurzel = lese_wurzel()
    g = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE_BESTAND
    )
    modelle = {m["id"]: m for m in g["tco"]["modelle"]}
    uebertragen = 0
    for p in g["zeitreihe"]["paare"]:
        zeilen = geraete_zeitreihe.band_zeilen(modelle[p["modell"]], p["laufzeit"])
        hat = {z["anbieter"] for z in zeilen.get(p["band"], {}).get("zeilen", [])}
        for roh in re.findall(r"<title>([^<]*?) · [^<]*gelesen am", p["svg_breit"]):
            anbieter = html.unescape(roh)
            uebertragen += 1
            assert anbieter in hat, (p["modell"], p["band"], p["laufzeit"], anbieter)
    assert uebertragen >= 0


def test_a5_schaetzung_in_der_tafel_wird_neben_der_legende_erklaert():
    schaetzung = {
        "anbieter": "o2",
        "sku_id": "s",
        "gesamt": 1333.75,
        "zaehlt": False,
        "schaetzung": True,
    }
    satz = {"zeilen": [], "karten": [schaetzung], "gesperrt": [schaetzung]}
    mess = {"o2": {"2026-11-05": {"zaehlt": True}}}
    serien = {"o2": [("2026-11-05", 1374.0)]}
    html = geraete_zeitreihe_legende.schaetzung_html(satz, mess, serien)
    assert "nicht zählen" in html and "letzte zählende Messung (1.374 €)" in html
    unzaehlend = {"o2": {"2026-11-05": {"zaehlt": False}}}
    assert geraete_zeitreihe_legende.schaetzung_html(satz, unzaehlend, serien) == ""
    mit_zeile = {**satz, "zeilen": [{"anbieter": "o2"}]}
    assert geraete_zeitreihe_legende.schaetzung_html(mit_zeile, mess, serien) == ""


GRUENDE = [
    getattr(beleg_position, n) for n in dir(beleg_position) if n.startswith("GRUND_")
]


def test_a2_grund_behauptet_nicht_was_ein_bild_zeigt():
    """Der Grund steht nur, wenn die Liste KEIN Bild zeigt (`.gr-beleg-keins`)."""
    assert len(GRUENDE) >= 5, GRUENDE
    falsch = [g for g in GRUENDE if "zeigt" in g]
    assert not falsch, falsch
    assert "keiner zuordnen" in beleg_position.GRUND_GLEICHSTAND


def _tarif(vorlage: dict, tarif_id: str, name: str, gb) -> dict:
    return {**vorlage, "tarif_id": tarif_id, "name": name, "datenvolumen_gb": gb}


@pytest.fixture(scope="module")
def stufen_site(tmp_path_factory) -> Path:
    """o2 hat einen Tarif in XS (mit Bild) und einen ohne Stufe (ohne Bild); Vodafone
    hat zusätzlich Stufe M. Wählt der Leser M, führt o2 dort keinen Tarif."""
    site = kopf_zeitraum._baue(tmp_path_factory.mktemp("a3"))
    wurzel = site.parent
    state = wurzel / "data" / "state"
    tarife_datei = state / "tarife.jsonl"
    tarife = [json.loads(z) for z in tarife_datei.read_text("utf-8").splitlines()]
    vorlage = next(t for t in tarife if t["tarif_id"] == "vf:klein")
    tarife += [
        _tarif(vorlage, "vf:s", "Vodafone Mobil S", 30),
        _tarif(vorlage, "o2:ohne", "O2 Ohne Stufe", None),
    ]
    tarife_datei.write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8"
    )
    bestand = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    vodafone = [b for b in bestand["buendel"] if b["anbieter"] == "Vodafone"]
    vodafone.append(
        {**vodafone[0], "tarif_id": "vf:s", "tarif_name": "Vodafone Mobil S"}
    )
    saetze = [
        pos._satz("o2", "O2 Mobile Klein", "o2:klein", 24, 18.0, pos.ID_O2),
        pos._satz("o2", "O2 Ohne Stufe", "o2:ohne", 24, 20.0, "f" * 64),
    ]
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": pos.HEUTE, "buendel": [*saetze, *vodafone]}),
        encoding="utf-8",
    )
    schreibe(
        state / MANIFEST_NAME,
        baue_manifest({f"belege-{pos.HEUTE}": [pos._bild("o2")]}, pos.TAG),
    )
    render_site(site, wurzel / "data" / "reports")
    return site


def test_a3_fixture_hat_die_lage(stufen_site):
    """Vorbedingung: o2 hat eine Kombination ohne Stufe (``:24``) und eine in XS."""
    text = (stufen_site / "data" / "geraete-buendel.html").read_text(encoding="utf-8")
    kombis = re.search(r'data-anbieter="o2" data-kombis="([^"]*)"', text)
    assert kombis and ":24" in kombis.group(1).split(), kombis
    assert "xs:24" in kombis.group(1).split(), kombis


@pytest.mark.browser
def test_a3_anbieter_ohne_tarif_in_der_stufe_steht_nicht_mit_kein_screenshot(
    stufen_site, chromium
):
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(stufen_site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        for breite in (1440, 390):
            ctx = chromium.new_context(viewport={"width": breite, "height": 900})
            try:
                ctx.route(
                    "https://github.com/**",
                    lambda r: r.fulfill(body=pos.PNG, content_type="image/png"),
                )
                s = ctx.new_page()
                s.goto(
                    f"http://127.0.0.1:{httpd.server_address[1]}/geraete.html",
                    wait_until="domcontentloaded",
                )
                s.click("#gr-zr-laufzeiten button[data-lz='24']")
                s.click("#gr-zr-baender button[data-band='xs']")
                xs = kombi._sichtbar(s, "o2")
                assert xs["anbieter"] and xs["bilder"] >= 1, xs
                assert s.locator("#gr-zr-baender button[data-band='m']").is_enabled()
                s.click("#gr-zr-baender button[data-band='m']")
                stufe_s = kombi._sichtbar(s, "o2")
                assert stufe_s == {"anbieter": False}, (breite, stufe_s)
            finally:
                ctx.close()
    finally:
        httpd.shutdown()


def test_a4_kopfsatz_nennt_die_gewaehlte_laufzeit(zustand):
    """Nicht reproduzierbar als Rückfall (Live-Abnahme 08.11.: XS/12 „mit 24 Raten“):
    jedes Paar nennt seine eigene Ratenlaufzeit; die „24“ dort ist der Zeitraum
    („Kosten über 24 Monate“ gilt auch bei 12 Raten). Dieser Test hält das fest."""
    wurzel = lese_wurzel()
    g = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE_BESTAND
    )
    nach_lz = {12: 0, 24: 0, 36: 0}
    for p in g["zeitreihe"]["paare"]:
        genannt = re.findall(r"mit (\d+) Raten", p["antwort_html"])
        assert genannt and set(genannt) == {str(p["laufzeit"])}, (
            p["modell"],
            p["band"],
            p["laufzeit"],
            genannt,
        )
        nach_lz[p["laufzeit"]] += 1
    assert all(nach_lz.values()), nach_lz
