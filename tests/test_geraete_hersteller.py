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


def test_gleichauf_gilt_mit_fester_toleranz_von_einem_prozent():
    assert hm.richtung(1.0) == "gleichauf"
    assert hm.richtung(-1.4) == "gleichauf"
    assert hm.richtung(0.0) == "gleichauf"
    assert hm.richtung(1.6) == "teurer"
    assert hm.richtung(-1.6) == "günstiger"


def test_prozenttext_mit_echtem_minus_und_geschuetztem_leerzeichen():
    assert hm.prozent_text(12.4) == "+12 %"
    assert hm.prozent_text(-16.6) == "−17 %"
    assert hm.prozent_text(0.2) == "0 %"
    assert ht.runde(2.5) == 3 and ht.runde(-2.5) == -2


def test_kleine_stichprobe_ist_benannt():
    assert hm.modell_wort(1) == "nur 1 Modell"
    assert hm.modell_wort(2) == "nur 2 Modelle"
    assert hm.modell_wort(hm.KLEIN) == f"{hm.KLEIN} Modelle"


def test_aktuell_ist_das_mittel_je_hersteller_und_luecke_statt_null():
    welt = _welt()
    r = _rechne(welt)
    assert [m["hersteller"] for m in r["modelle"]] == ["Apple", "Samsung"]
    assert r["aktuell"][0][:2] == [pytest.approx(-12.0), pytest.approx(10.0)]
    assert all(w is None for w in r["aktuell"][0][2:])
    assert r["aktuell"][1][:2] == [pytest.approx(-20.0), None]
    z = hm.zellen(r, r["aktuell"])
    assert z["Apple"][0] == (pytest.approx(-12.0), 1)
    assert z["Samsung"][1] == (None, 0)
    assert z[hm.GESAMT][0] == (pytest.approx(-16.0), 2)
    assert z[hm.GESAMT][1] == (pytest.approx(10.0), 1)


def test_zeitraum_mittelt_die_messtage_je_modell():
    r = _rechne(_welt())
    zeilen, tage = hm.mittel_ueber_tage(r, "2026-10-30", "2026-11-01")
    assert tage == 3
    assert zeilen[0][0] == pytest.approx(-16.0)
    zeilen, tage = hm.mittel_ueber_tage(r, "2026-10-31", "2026-11-01")
    assert tage == 2 and zeilen[0][0] == pytest.approx(-14.0)
    zeilen, tage = hm.zeitraum(r, 2)
    assert tage == 2 and zeilen[0][0] == pytest.approx(-14.0)
    zeilen, tage = hm.mittel_ueber_tage(r, "2026-01-01", "2026-01-02")
    assert tage == 0 and all(x is None for z in zeilen for x in z)


def test_veraltete_messung_zaehlt_in_keinem_zeitraum():
    welt = _welt()
    alt = welt["messungen"][("apple-iphone-18-pro-256", "m", LAUFZEIT)]["Telekom"]
    alt["2026-11-01"]["satz"]["abgerufen_am"] = "2026-09-01"
    r = _rechne(welt)
    assert r["pct"]["2026-11-01"][0][0] is None
    assert r["pct"]["2026-10-31"][0][0] is not None


def test_zeilen_spalten_und_luecken_aus_den_daten():
    welt = _welt()
    d = hm.aufbereiten(welt["messungen"], welt["tco"], welt["katalog"], "2026-11-01")
    assert [z["hersteller"] for z in d["zeilen"]] == ["Apple", "Samsung", hm.GESAMT]
    assert [w["name"] for w in d["wettbewerber"]] == ["Telekom", "o2"]
    apple = d["zeilen"][0]["zellen"]
    assert apple[0]["text"] == "−12 %" and apple[0]["richtung"] == "günstiger"
    samsung_o2 = d["zeilen"][1]["zellen"][1]
    assert samsung_o2["leer"] and samsung_o2["text"] == "–"
    assert samsung_o2["n_text"] == "kein Preis" and "wert" not in samsung_o2
    daten = json.loads(d["json"].replace("<\\/", "</"))
    assert daten["tage"] == list(TAGE) and daten["h"] == ["Apple", "Samsung"]
    assert daten["gleichauf"] == hm.GLEICHAUF and daten["klein"] == hm.KLEIN


def test_spalte_ohne_jeden_preis_wird_zum_schmalen_hinweis():
    welt = _welt()
    d = hm.aufbereiten(welt["messungen"], welt["tco"], welt["katalog"], "2026-11-01")
    ohne = {o["name"] for o in d["ohne_spalte"]}
    spalten = {w["name"] for w in d["wettbewerber"]}
    assert ohne and not ohne & spalten
    assert ohne | spalten == set(hm.WETTBEWERBER)
    for o in d["ohne_spalte"]:
        assert o["text"].endswith(f"kein {LAUFZEIT}-Monats-Preis")
    for z in d["zeilen"]:
        assert len(z["zellen"]) == len(spalten)


def test_spalten_folgen_den_daten_nicht_einem_festen_anbieter(monkeypatch):
    monkeypatch.setattr(hm, "WETTBEWERBER", ("Telekom", "Neuling"))
    welt = _welt(("Telekom", "Neuling"))
    d = hm.aufbereiten(welt["messungen"], welt["tco"], welt["katalog"], "2026-11-01")
    assert [w["name"] for w in d["wettbewerber"]] == ["Telekom", "Neuling"]
    assert d["ohne_spalte"] == []
    assert d["zeilen"][0]["zellen"][1]["text"] == "+10 %"


def test_erklaerung_nennt_tarife_toleranz_gewichtung_und_luecken():
    welt = _welt()
    d = hm.aufbereiten(welt["messungen"], welt["tco"], welt["katalog"], "2026-11-01")
    text = " ".join(d["erklaerung"])
    assert "Vodafone: Vodafone Mobil M" in text
    assert "Telekom: Telekom Tarif M" in text and "o2: o2 Tarif M" in text
    assert f"±{hm.GLEICHAUF} %" in text and "gleichauf" in text
    assert "nach Modellzahl gewichtet" in text
    assert f"weniger als {hm.KLEIN} Modellen" in text
    for o in d["ohne_spalte"]:
        assert o["name"] in text and ht.FEHLT_TEXT in text
    assert f"{LAUFZEIT} Monate" in text


def test_ohne_modelle_oder_messungen_kein_stilles_bild():
    welt = _welt()
    assert hm.aufbereiten(None, welt["tco"], welt["katalog"], "x")["fehler"]
    leer = hm.aufbereiten({}, welt["tco"], welt["katalog"], "2026-11-01")
    assert leer == {"fehler": "", "leer": True}


def test_eigenmarke_eines_anbieters_steht_nicht_unter_ohne_vodafone_preis():
    welt = _welt()
    welt["katalog"].geraete.append(_g("Telekom", "T Phone 3", 3))
    welt["katalog"].geraete.append(_g("Nothing", "Phone 4", 4))
    d = hm.aufbereiten(welt["messungen"], welt["tco"], welt["katalog"], "2026-11-01")
    satz = d["erklaerung"][-1]
    assert "Nothing" in satz and "Telekom" not in satz


def _rendern(welt: dict) -> BeautifulSoup:
    hersteller = hm.aufbereiten(
        welt["messungen"], welt["tco"], welt["katalog"], "2026-11-01"
    )
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(VORLAGEN), autoescape=True)
    html = env.get_template("_geraete_hersteller.html.j2").render(
        geraete={"hersteller": hersteller}
    )
    return BeautifulSoup(html, "html.parser")


def test_vorlage_zeichnet_zellen_balken_und_zeitwahl():
    s = _rendern(_welt())
    assert s.select_one("section#hersteller h2").text == "Preisposition je Hersteller"
    assert [b["data-zeit"] for b in s.select("#hm-zeit button")] == [
        "aktuell",
        "7",
        "30",
        "eigen",
    ]
    assert s.select_one("#hm-zeit").has_attr("hidden")
    zeile = s.select_one('.gr-hm-zeile[data-hersteller="Apple"]')
    zelle = zeile.select_one('.gr-hm-zelle[data-anbieter="Telekom"]')
    assert zelle["data-wert"] == "-12.00" and zelle["data-n"] == "1"
    assert "gr-hm-duenn" in zelle["class"]
    assert zelle.select_one(".gr-hm-m").text == "nur 1 Modell"
    leer = s.select_one('.gr-hm-zeile[data-hersteller="Samsung"] .gr-hm-leer')
    assert leer.select_one(".gr-hm-zahl").text == "–"
    assert leer.select_one(".gr-hm-balken").has_attr("hidden")
    assert "data-wert" not in leer.attrs
    assert s.select_one("#hm-einheit")["data-basis"].endswith(f"{LAUFZEIT} Monate")
    assert s.select_one("#hm-daten").text.strip().startswith("{")


def test_vorlage_benennt_ausfall_und_leerzustand():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(VORLAGEN), autoescape=True)
    vorlage = env.get_template("_geraete_hersteller.html.j2")
    fehler = vorlage.render(geraete={"hersteller": {"fehler": "kaputt", "leer": False}})
    assert "nicht verfügbar: kaputt" in fehler
    leer = vorlage.render(geraete={"hersteller": {"fehler": "", "leer": True}})
    assert "Kein geprüfter Preis" in leer
    assert "nicht berechnet" in vorlage.render(geraete={})


def test_seite_zeigt_die_herstellergrafik_vor_der_modellgrafik(tmp_path):
    seite = test_geraete_tco_zustand._baue(tmp_path)
    ids = [e.get("id") for e in seite.select("section[id]")]
    assert "hersteller" in ids and "preisposition" in ids
    assert ids.index("hersteller") < ids.index("preisposition")
    assert seite.select_one("#pp-titel").text == "Preispositionierung je Modell"


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
    d = hm.aufbereiten(welt["messungen"], welt["tco"], welt["katalog"], "2026-11-01")
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


def _zellenwerte(seite) -> dict[str, tuple]:
    return {
        k: tuple(v)
        for k, v in seite.evaluate(
            """() => Object.fromEntries([...document.querySelectorAll('.gr-hm-zeile')]
              .flatMap(z => [...z.querySelectorAll('.gr-hm-zelle')].map(c => [
                z.dataset.hersteller + '|' + c.dataset.anbieter,
                [c.dataset.wert ?? null, c.dataset.n ?? null,
                 c.querySelector('.gr-hm-zahl').textContent,
                 c.querySelector('.gr-hm-m').textContent]])))"""
        ).items()
    }


def _erwartet(r: dict, zeilen, spalten: list[str]) -> dict[str, tuple]:
    aus = {}
    for h, zellen in hm.zellen(r, zeilen).items():
        for name, (m, n) in zip(hm.WETTBEWERBER, zellen, strict=True):
            if name not in spalten:
                continue
            if m is None:
                aus[f"{h}|{name}"] = (None, None, "–", "kein Preis")
            else:
                aus[f"{h}|{name}"] = (
                    f"{m:.2f}",
                    str(n),
                    hm.prozent_text(m),
                    hm.modell_wort(n),
                )
    return aus


@pytest.mark.parametrize("modus", ["7", "30", "eigen"])
def test_browser_rechnet_wie_die_python_referenz(chromium, _site, modus):
    welt = _welt()
    r = _rechne(welt)
    d, seite, fehler = _lade(chromium, _site, welt)
    spalten = [w["name"] for w in d["wettbewerber"]]
    try:
        with _server(_site) as basis:
            seite.goto(f"{basis}/hm.html", wait_until="load")
            assert fehler == []
            assert not seite.is_hidden("#hm-zeit")
            assert _zellenwerte(seite) == _erwartet(r, r["aktuell"], spalten)
            if modus == "eigen":
                seite.click("button[data-zeit=eigen]")
                seite.fill("#hm-von", "2026-10-31")
                seite.fill("#hm-bis", "2026-11-01")
                seite.dispatch_event("#hm-bis", "change")
                zeilen, tage = hm.mittel_ueber_tage(r, "2026-10-31", "2026-11-01")
            else:
                seite.click(f"button[data-zeit='{modus}']")
                zeilen, tage = hm.zeitraum(r, int(modus))
            assert _zellenwerte(seite) == _erwartet(r, zeilen, spalten)
            assert f"Mittel aus {tage} Messtagen" in seite.inner_text("#hm-einheit")
            pressed = seite.get_attribute(
                f"button[data-zeit='{modus}']", "aria-pressed"
            )
            assert pressed == "true"
    finally:
        seite.close()


def test_browser_zeitraum_ohne_messtage_zeigt_luecken_statt_null(chromium, _site):
    d, seite, fehler = _lade(chromium, _site, _welt())
    try:
        with _server(_site) as basis:
            seite.goto(f"{basis}/hm.html", wait_until="load")
            seite.click("button[data-zeit=eigen]")
            seite.evaluate("document.getElementById('hm-von').min = '2000-01-01'")
            seite.fill("#hm-von", "2026-01-01")
            seite.fill("#hm-bis", "2026-01-02")
            seite.dispatch_event("#hm-bis", "change")
            werte = _zellenwerte(seite)
            assert werte and all(v[0] is None and v[2] == "–" for v in werte.values())
            assert "Keine Messtage" in seite.inner_text("#hm-einheit")
            assert fehler == []
    finally:
        seite.close()
