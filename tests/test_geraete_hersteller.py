"""Preisposition je Hersteller (Geräteseite, erste Übersichtsgrafik).

Die Zahl einer Zelle ist der mittlere Abstand der Vodafone-Gesamtkosten
(Leitzahl der Seite, 24 Monate, Band M) zum Wettbewerber, gemittelt über die
aktuellen Modelle eines Herstellers. Fehlt ein Preis, fehlt die Zelle - nie
ein Wert 0. Alle Namen, Tarife und Spalten kommen aus den Daten; die Tests
hängen nicht am Datum und nicht an einem festen Wettbewerber.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import socket
import threading
from pathlib import Path

import jinja2
import pytest
import test_geraete_tco_zustand
from bs4 import BeautifulSoup

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_hersteller as hm
from telco_radar.report import geraete_hersteller_text as ht
from telco_radar.report.html import render_site

VORLAGEN = Path(hm.__file__).parent / "templates"
LAUFZEIT = hm.LAUFZEIT


def _g(hersteller: str, modell: str, generation: int, auto: str = "") -> Geraet:
    return Geraet(
        hersteller=hersteller,
        modell=modell,
        generation=generation,
        speicher=[256, 512],
        auto=auto,
    )


def _karte(anbieter: str, gesamt: float, tarif: str = "") -> dict:
    return {
        "anbieter": anbieter,
        "band": "m",
        "gesamt": gesamt,
        "tarif": tarif or f"{anbieter} M",
        "vergleichbar": True,
        "belastbar": True,
        "frisch": True,
        "zaehlt": True,
        "naeherung": False,
        "raten_laufzeit": LAUFZEIT,
        "leitzahl_monate": LAUFZEIT,
        "quelle_url": f"https://beispiel.test/{anbieter}?tarif=m",
    }


def _messung(wert: float, tag: str) -> dict:
    return {
        "wert": wert,
        "monate": LAUFZEIT,
        "zaehlt": True,
        "satz": {"abgerufen_am": tag},
    }


TAGE = ("2026-10-30", "2026-10-31", "2026-11-01")


def _welt(wettbewerber: tuple[str, ...] = ("Telekom", "o2")) -> dict:
    """Ein Apple-Modell und ein Samsung-Modell, drei Messtage.

    Apple: Vodafone 2000 -> 2100 -> 2200; Telekom 2500 gleichbleibend;
    der zweite Wettbewerber 2000. Samsung: Vodafone 1000, Telekom 1250
    (kein Preis beim zweiten Wettbewerber)."""
    katalog = Katalog(
        geraete=[
            _g("Apple", "iPhone 18 Pro", 18),
            _g("Samsung", "Galaxy S26", 26),
        ]
    )
    karten_apple = [_karte("Vodafone", 2200.0, "Vodafone Mobil M")]
    karten_samsung = [_karte("Vodafone", 1000.0, "Vodafone Mobil M")]
    messungen: dict = {}
    for mid, vf, preise in (
        ("apple-iphone-18-pro-256", [2000.0, 2100.0, 2200.0], {0: 2500.0, 1: 2000.0}),
        ("samsung-galaxy-s26-256", [1000.0] * 3, {0: 1250.0}),
    ):
        je = {"Vodafone": {t: _messung(v, t) for t, v in zip(TAGE, vf, strict=True)}}
        karten = karten_apple if mid.startswith("apple") else karten_samsung
        for j, preis in preise.items():
            name = wettbewerber[j]
            je[name] = {t: _messung(preis, t) for t in TAGE}
            karten.append(_karte(name, preis, f"{name} Tarif M"))
        messungen[(mid, "m", LAUFZEIT)] = je
    tco = {
        "baender_katalog": [{"key": "m", "label": "M"}],
        "modelle": [
            {"id": "apple-iphone-18-pro-256", "karten": karten_apple},
            {"id": "samsung-galaxy-s26-256", "karten": karten_samsung},
        ],
    }
    return {"katalog": katalog, "tco": tco, "messungen": messungen}


def _rechne(welt: dict) -> dict:
    return hm.berechne(welt["messungen"], welt["tco"], welt["katalog"], "2026-11-01")


def test_nur_die_neueste_generation_je_reihe_und_nicht_das_iphone_air():
    katalog = Katalog(
        geraete=[
            _g("Apple", "iPhone Air", 17),
            _g("Apple", "iPhone 17e", 17),
            _g("Apple", "iPhone 18 Pro", 18),
            _g("Apple", "iPhone 18 Pro Max", 18),
            _g("Samsung", "Galaxy S26", 26),
            _g("Samsung", "Galaxy S25", 25),
            _g("Samsung", "Galaxy A57", 57),
            _g("Google", "Pixel 11", 11),
            _g("Google", "Pixel 10a", 10),
            _g("Apple", "iPhone 18 Auto", 18, auto="2026-10-01"),
        ]
    )
    namen = {g.modell for g in hm.aktuelle_geraete(katalog)}
    assert namen == {
        "iPhone 18 Pro",
        "iPhone 18 Pro Max",
        "Galaxy S26",
        "Galaxy A57",
        "Pixel 11",
    }


def test_eine_reihe_ohne_zahl_bleibt_wenn_die_familie_keine_neuere_hat():
    katalog = Katalog(geraete=[_g("Apple", "iPhone Air", 17)])
    assert [g.modell for g in hm.aktuelle_geraete(katalog)] == ["iPhone Air"]


def test_modell_ohne_vodafone_preis_ist_eine_benannte_luecke():
    welt = _welt()
    welt["messungen"][("samsung-galaxy-s26-256", "m", LAUFZEIT)].pop("Vodafone")
    modelle, ohne = hm.modelle_waehlen(welt["katalog"], welt["tco"], welt["messungen"])
    assert [m["hersteller"] for m in modelle] == ["Apple"]
    assert ohne == ["Samsung"]


def test_abstand_plus_heisst_vodafone_teurer():
    assert hm.abstand(2200.0, 2000.0) == pytest.approx(10.0)
    assert hm.abstand(1000.0, 1250.0) == pytest.approx(-20.0)


def test_gleichauf_und_prozenttext_kommen_aus_dem_textmodul():
    assert ht.richtung(1.0) == "gleichauf" and ht.richtung(-1.4) == "gleichauf"
    assert ht.richtung(1.6) == "teurer" and ht.richtung(-1.6) == "günstiger"
    assert ht.prozent_text(12.4) == f"+12{ht.NBSP}%"
    assert ht.prozent_text(-16.6) == f"{ht.MINUS}17{ht.NBSP}%"
    assert ht.prozent_text(0.2) == f"0{ht.NBSP}%"
    assert ht.runde(2.5) == 3 and ht.runde(-2.5) == -2


def test_veraltete_messung_zaehlt_an_keinem_tag():
    welt = _welt()
    alt = welt["messungen"][("apple-iphone-18-pro-256", "m", LAUFZEIT)]["Telekom"]
    alt["2026-11-01"]["satz"]["abgerufen_am"] = "2026-09-01"
    r = _rechne(welt)
    assert r["pct"]["2026-11-01"][0][0] is None
    assert r["pct"]["2026-10-31"][0][0] is not None


def test_berechne_traegt_nur_noch_tageswerte():
    """Die Spalte „aktuell“ (Karten statt Messtage) ist mit der Tafel gefallen:
    das Bild hat EINE Zahlenbasis, nicht zwei nebeneinander."""
    r = _rechne(_welt())
    assert set(r) == {"stand", "modelle", "ohne", "tage", "pct"}
    assert r["tage"] == list(TAGE)


def test_fenster_waehlt_die_letzten_kalendertage_bis_zum_stand():
    tage = ["2026-10-01", "2026-10-30", "2026-10-31", "2026-11-01"]
    assert hm.fenster_tage(tage, "2026-11-01", 2) == ["2026-10-31", "2026-11-01"]
    assert hm.fenster_tage(tage, "2026-11-01", 30) == tage[1:]
    assert hm.fenster_tage([], "2026-11-01", 7) == []


def _gross(wettbewerber: tuple[str, ...] = ("Telekom", "o2")) -> dict:
    """Wie `_welt`, aber mit `KLEIN` Modellen je Hersteller - erst damit sind
    die Messtage Vergleichstage (`geraete_hersteller_grafik.MINDEST_MODELLE`)."""
    n = ht.KLEIN
    geraete, modelle, messungen = [], [], {}
    for marke, reihe, vf, preise in (
        ("Apple", "iPhone", 2200.0, (2500.0, 2000.0)),
        ("Samsung", "Galaxy", 1000.0, (1250.0, 1000.0)),
    ):
        for i in range(n):
            geraet = _g(marke, f"{reihe}{chr(65 + i)} 30", 30)
            geraete.append(geraet)
            mid = f"{geraet.device_id}-256"
            karten = [_karte("Vodafone", vf, "Vodafone Mobil M")]
            je = {"Vodafone": {t: _messung(vf, t) for t in TAGE}}
            for j, preis in enumerate(preise):
                name = wettbewerber[j]
                je[name] = {t: _messung(preis, t) for t in TAGE}
                karten.append(_karte(name, preis, f"{name} Tarif M"))
            messungen[(mid, "m", LAUFZEIT)] = je
            modelle.append({"id": mid, "karten": karten})
    tco = {"baender_katalog": [{"key": "m", "label": "M"}], "modelle": modelle}
    return {"katalog": Katalog(geraete=geraete), "tco": tco, "messungen": messungen}


def _bild(welt: dict) -> dict:
    return hm.aufbereiten(welt["messungen"], welt["tco"], welt["katalog"], "2026-11-01")


def test_das_bild_traegt_eine_linie_je_hersteller_und_die_leitlinie():
    d = _bild(_gross())
    assert [r["name"] for r in d["reihen"]] == ["Apple", "Samsung", "Alle Hersteller"]
    assert [legende["name"] for legende in d["legende"]] == [
        r["name"] for r in d["reihen"]
    ]
    apple = d["reihen"][0]
    assert [p["tag"] for p in apple["punkte"]] == list(TAGE)
    gegen_telekom = hm.abstand(2200.0, 2500.0)
    gegen_o2 = hm.abstand(2200.0, 2000.0)
    assert apple["punkte"][0]["wert"] == pytest.approx(
        (gegen_telekom + gegen_o2) / 2, abs=0.01
    )


def test_spalten_und_stand_folgen_den_daten():
    d = _bild(_gross())
    assert [w["name"] for w in d["wettbewerber"]] == ["Telekom", "o2"]
    assert d["stand"] == TAGE[-1]
    assert d["tage_von"] == TAGE[0] and d["tage_bis"] == TAGE[-1]
    daten = json.loads(d["json"].replace("<\\/", "</"))
    assert daten["tage"] == list(TAGE)
    assert daten["vorgabe"] == hm.VORGABE_FENSTER
    assert daten["fenster"] == list(hm.FENSTER)
    assert [s["name"] for s in daten["stile"]][-1] == "Alle Hersteller"
    assert daten["belegt"] == [hm.WETTBEWERBER.index(w) for w in ("Telekom", "o2")]


def test_spalten_folgen_den_daten_nicht_einem_festen_anbieter(monkeypatch):
    monkeypatch.setattr(hm, "WETTBEWERBER", ("Telekom", "Neuling"))
    d = _bild(_gross(("Telekom", "Neuling")))
    assert [w["name"] for w in d["wettbewerber"]] == ["Telekom", "Neuling"]


def test_ohne_vergleichstag_bleibt_das_bild_leer_statt_halb():
    """Nur ein Modell je Hersteller: kein Tag erreicht `MINDEST_MODELLE`."""
    d = _bild(_welt())
    assert d == {"fehler": "", "leer": True}


def test_ohne_modelle_oder_messungen_kein_stilles_bild():
    welt = _welt()
    assert hm.aufbereiten(None, welt["tco"], welt["katalog"], "x")["fehler"]
    leer = hm.aufbereiten({}, welt["tco"], welt["katalog"], "2026-11-01")
    assert leer == {"fehler": "", "leer": True}


def test_um_das_bild_herum_steht_kein_erklaertext():
    """Antonio, 12.12.2026: „Gutes Design braucht keine Erklärung." Die
    Erklärabsätze und die Spaltenhinweise sind gefallen."""
    d = _bild(_gross())
    assert "erklaerung" not in d and "ohne_spalte" not in d and "zeilen" not in d
    assert "Gesamtkosten" in d["einheit"]


def _rendern(welt: dict) -> BeautifulSoup:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(VORLAGEN), autoescape=True)
    html = env.get_template("_geraete_hersteller.html.j2").render(
        geraete={"hersteller": _bild(welt)}
    )
    return BeautifulSoup(html, "html.parser")


def test_vorlage_zeigt_zeitwahl_legende_und_zwei_bilder():
    s = _rendern(_gross())
    assert s.select_one("section#hersteller h2").text == "Preisposition je Hersteller"
    assert [b["data-zeit"] for b in s.select("#hm-zeit button")] == ["7", "30", "eigen"]
    assert s.select_one("#hm-zeit").has_attr("hidden")
    vorgabe = s.select_one(f"#hm-zeit button[data-zeit='{hm.VORGABE_FENSTER}']")
    assert vorgabe["aria-pressed"] == "true"
    assert [li.text.strip() for li in s.select(".gr-hm-leg")] == [
        "Apple",
        "Samsung",
        "Alle Hersteller",
    ]
    assert s.select_one("#hm-bild-breit svg.gr-hl") is not None
    assert s.select_one("#hm-bild-schmal svg.gr-hl") is not None
    assert s.select_one("#hm-daten").text.strip().startswith("{")
    assert s.select_one(".gr-hm-erklaerung") is None
    assert s.select_one("#hm-einheit") is None


def test_vorlage_benennt_ausfall_und_leerzustand():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(VORLAGEN), autoescape=True)
    vorlage = env.get_template("_geraete_hersteller.html.j2")
    fehler = vorlage.render(geraete={"hersteller": {"fehler": "kaputt", "leer": False}})
    assert "nicht verfügbar: kaputt" in fehler
    leer = vorlage.render(geraete={"hersteller": {"fehler": "", "leer": True}})
    assert "Kein vergleichbarer Messtag" in leer
    assert "nicht berechnet" in vorlage.render(geraete={})


def test_seite_zeigt_ein_preisbild_und_keine_modellgrafik(tmp_path):
    seite = test_geraete_tco_zustand._baue(tmp_path)
    ids = [e.get("id") for e in seite.select("section[id]")]
    assert "hersteller" in ids
    assert "preisposition" not in ids
    assert seite.select_one("#messdatum") is None
    assert "Preispositionierung je Modell" not in seite.get_text()
    fuss = seite.select_one(".dz-foot--stand")
    assert fuss is not None and fuss.text.startswith("Preise Stand ")


@contextlib.contextmanager
def _server(site: Path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


@pytest.fixture(scope="module")
def _site(tmp_path_factory):
    """Die ausgelieferte `app.js`: `render_site` kopiert sie; der Test liest
    keinen Quelltext, er laedt sie im Browser neben den gerenderten Abschnitt."""
    root = tmp_path_factory.mktemp("hersteller")
    site = root / "site"
    reports = root / "reports"
    reports.mkdir()
    render_site(site, reports, cfg=None)
    return site


def _lade(chromium, site: Path, welt: dict, breite: int = 1440):
    d = _bild(welt)
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(VORLAGEN), autoescape=True)
    html = env.get_template("_geraete_hersteller.html.j2").render(
        geraete={"hersteller": d}
    )
    (site / "hm.html").write_text(
        f"<!doctype html><meta charset=utf-8><body>{html}"
        '<script src="app.js"></script>',
        encoding="utf-8",
    )
    seite = chromium.new_page(viewport={"width": breite, "height": 900})
    fehler: list[str] = []
    seite.on("pageerror", lambda e: fehler.append(str(e)))
    return d, seite, fehler


def _gezeichnet(seite) -> dict:
    """Je Reihe die Endbeschriftung und die Zahl der Punkte aus dem DOM."""
    return seite.evaluate(
        """() => {
          const svg = document.querySelector('#hm-bild-breit svg');
          const text = (el) => el.textContent;
          const enden = [...svg.querySelectorAll('.gr-hl-ende')].map(text);
          const punkte = [...svg.querySelectorAll('.gr-hl-punkte')]
            .map(g => g.children.length);
          const namen = [...document.querySelectorAll('.gr-hm-leg')]
            .map(l => l.textContent.trim());
          return {enden, punkte, namen};
        }"""
    )


def _erwartet(d: dict, von: str, bis: str) -> dict:
    tage = [t for t in d["json_tage"] if von <= t <= bis]
    reihen = [
        r
        for r in d["alle_reihen"]
        if [p for p in r["punkte"] if von <= p["tag"] <= bis]
    ]
    return {
        "enden": [
            ht.prozent_text(
                [p for p in r["punkte"] if von <= p["tag"] <= bis][-1]["wert"]
            )
            for r in reihen
        ],
        "punkte": [
            len([p for p in r["punkte"] if von <= p["tag"] <= bis]) for r in reihen
        ],
        "namen": [r["name"] for r in reihen],
        "tage": tage,
    }


@pytest.mark.parametrize("modus", ["7", "eigen"])
def test_browser_rechnet_wie_die_python_referenz(chromium, _site, modus):
    """Dieselbe Regel in beiden Sprachen: der Browser lockert weder die
    Vergleichstage noch das Zweistufen-Mittel."""
    welt = _gross()
    d = _bild(welt)
    daten = json.loads(d["json"].replace("<\\/", "</"))
    d = {**d, "json_tage": daten["tage"], "alle_reihen": d["reihen"]}
    _d, seite, fehler = _lade(chromium, _site, welt)
    try:
        with _server(_site) as basis:
            seite.goto(f"{basis}/hm.html", wait_until="load")
            assert fehler == []
            assert not seite.is_hidden("#hm-zeit")
            if modus == "eigen":
                von, bis = TAGE[1], TAGE[2]
                seite.click("button[data-zeit=eigen]")
                seite.fill("#hm-von", von)
                seite.fill("#hm-bis", bis)
                seite.dispatch_event("#hm-bis", "change")
            else:
                von, bis = TAGE[0], TAGE[2]
                seite.click(f"button[data-zeit='{modus}']")
            erwartet = _erwartet(d, von, bis)
            gezeichnet = _gezeichnet(seite)
            assert gezeichnet["namen"] == erwartet["namen"]
            assert gezeichnet["enden"] == erwartet["enden"]
            assert gezeichnet["punkte"] == erwartet["punkte"]
            pressed = seite.get_attribute(
                f"button[data-zeit='{modus}']", "aria-pressed"
            )
            assert pressed == "true"
            assert fehler == []
    finally:
        seite.close()


def test_browser_zeitraum_ohne_messtage_zeigt_eine_benannte_luecke(chromium, _site):
    _d, seite, fehler = _lade(chromium, _site, _gross())
    try:
        with _server(_site) as basis:
            seite.goto(f"{basis}/hm.html", wait_until="load")
            seite.click("button[data-zeit=eigen]")
            seite.evaluate("document.getElementById('hm-von').min = '2000-01-01'")
            seite.fill("#hm-von", "2026-01-01")
            seite.fill("#hm-bis", "2026-01-02")
            seite.dispatch_event("#hm-bis", "change")
            assert seite.inner_text("#hm-ohne-tag").startswith("Kein vergleichbarer")
            assert not seite.is_hidden("#hm-ohne-tag")
            assert (
                seite.evaluate(
                    "() => document.querySelectorAll('#hm-bild-breit svg').length"
                )
                == 0
            )
            assert fehler == []
    finally:
        seite.close()
