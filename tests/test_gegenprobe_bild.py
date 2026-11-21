"""Konfigurationsbild der Gegenprobe (Abnahmekriterium 3): je gut gelesenem Bündel ein
eigenes Bild, aufgenommen NACH der Wahl, mit Gerät, Auswahl und Preis; was fehlt, ist
benannt. Lokale Seiten im Chromium ohne Netz; Bildlogik ohne Browser."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from telco_radar.collect.geraete import gegenprobe_bild as bild
from telco_radar.collect.geraete import gegenprobe_browser as gbr
from telco_radar.collect.geraete import gegenprobe_wege as wege

SEITE = """<html><body style="margin:0;font:16px sans-serif">
<main style="display:flex;gap:40px">
  <section id="konf" style="width:600px">
    <h1>Apple iPhone 17</h1>
    <p>Speicher: <b>256 GB</b></p>
    <p>Tarif: O₂ Mobile L</p>
    <label><input type="radio" name="r" onclick="w(24)"> 24 Raten</label>
    <label><input type="radio" name="r" onclick="w(36)"> 36 Raten</label>
  </section>
  <aside id="preis" style="width:400px">
    <h2>Dein Angebot</h2><p id="g">noch keine Wahl</p>
    <p>Gerät monatlich: <span id="b">–</span></p><p>einmalig gesamt: 7,99 €</p>
  </aside>
</main>
<script>function w(n){
  document.getElementById('g').textContent='Ratenzahlung: '+n+' Monate';
  document.getElementById('b').textContent=n==24?'40,00 €':'30,00 €';}</script>
</body></html>"""
ANKER = ("Dein Angebot", "einmalig gesamt")


def _satz(n: int, sku: str = "apple-iphone-17-256gb-schwarz") -> dict:
    return {
        "id": f"buendel--test--{sku}--o2-mobile-l--{n}m",
        "sku_id": sku,
        "tarif_name": "O2 Mobile L mit 150 GB+ (24 Mon.)",
        "laufzeit_monate": n,
        "geraet_monatsrate": 40.0,
    }


@pytest.fixture
def seite(chromium):
    s = chromium.new_page(viewport={"width": 1440, "height": 1000})
    s.set_content(SEITE)
    yield s
    s.close()


def test_bild_zeigt_geraet_auswahl_und_preis(seite):
    seite.get_by_text("24 Raten", exact=True).click()
    a = bild.aufnehme(seite, _satz(24), ANKER)
    assert a.grund is None and a.bild[:4] == b"RIFF"
    assert a.zeigt == ["Gerät", "Speicher", "Tarif", "Raten", "Preis"]
    assert a.ohne == []
    assert Image.open(io.BytesIO(a.bild)).width <= bild.BREITE_PX


def test_was_die_seite_nicht_zeigt_ist_benannt(seite):
    a = bild.aufnehme(seite, _satz(24, "apple-iphone-17-512gb-schwarz"), ANKER)
    assert "Speicher" in a.ohne and "Speicher" not in a.zeigt
    assert a.bild is not None


def test_ohne_preis_und_auswahl_kein_bild_mit_grund(chromium):
    s = chromium.new_page()
    s.set_content("<p>Leer</p>")
    a = bild.aufnehme(s, _satz(24), ANKER)
    s.close()
    assert a.bild is None and a.grund == bild.GRUND_NICHTS
    assert a.ohne == ["Gerät", "Speicher", "Tarif", "Raten", "Preis"]


@pytest.fixture
def besuchsweg(monkeypatch):
    """Ein Weg für die lokale Seite: öffnet einmal, klickt je Bündel die Raten; jeder
    Klick und jede Aufnahme landet im Protokoll."""
    monkeypatch.setattr(gbr, "NACH_LADEN_MS", 0)
    monkeypatch.setattr(gbr, "NACH_KLICK_MS", 0)
    monkeypatch.setattr(gbr, "RUHEFRIST_MS", 500)
    protokoll: list[str] = []
    aufnehme = bild.aufnehme

    def merke_aufnahme(seite, b, anker, nur=bild.MERKMALE, gelesen=""):
        protokoll.append(f"Bild {b['laufzeit_monate']}")
        return aufnehme(seite, b, anker, nur, gelesen)

    monkeypatch.setattr(bild, "aufnehme", merke_aufnahme)

    def waehle(seite, gruppe, oeffnen):
        seite.route(
            "http://127.0.0.1:9/**",
            lambda r: r.fulfill(body=SEITE, content_type="text/html; charset=utf-8"),
        )
        oeffnen(seite, "http://127.0.0.1:9/geraet")
        for b in gruppe:
            n = b["laufzeit_monate"]
            gbr.klicke(seite, seite.get_by_text(f"{n} Raten", exact=True), f"{n}")
            protokoll.append(f"Klick {n}")
            yield b, ""

    monkeypatch.setitem(wege.WEGE, "test", wege.Weg(waehle, (ANKER,), ANKER))
    return protokoll


def test_je_buendel_ein_eigenes_bild_nach_seiner_wahl(chromium, besuchsweg):
    ergebnis = dict(
        (b["id"], lesung)
        for b, lesung in wege.lies_gruppe(
            chromium, "test", [_satz(24), _satz(36)], None
        )
    )
    assert besuchsweg == ["Klick 24", "Bild 24", "Klick 36", "Bild 36"]
    eins, zwei = ergebnis[_satz(24)["id"]], ergebnis[_satz(36)["id"]]
    assert eins.bild is not None and zwei.bild is not None
    assert eins.bild != zwei.bild
    assert eins.bild_zeigt == zwei.bild_zeigt == list(bild.MERKMALE)
    assert "Ratenzahlung: 24 Monate" in eins.text
    assert "Ratenzahlung: 36 Monate" in zwei.text


def _aufnahme(farbe: str, hoehe: int, zeigt, ohne) -> bild.Aufnahme:
    puffer = io.BytesIO()
    Image.new("RGB", (100, hoehe), farbe).save(puffer, "WEBP")
    return bild.Aufnahme(puffer.getvalue(), list(zeigt), list(ohne))


def test_stapel_legt_auswahl_ueber_preis_und_vereinigt_den_inhalt():
    oben = _aufnahme("red", 40, ["Gerät", "Speicher", "Raten"], [])
    unten = _aufnahme("blue", 60, ["Tarif", "Preis"], ["Speicher"])
    ganz = bild.stapel(oben, unten)
    assert ganz.zeigt == ["Gerät", "Speicher", "Tarif", "Raten", "Preis"]
    assert ganz.ohne == []
    assert Image.open(io.BytesIO(ganz.bild)).height == 40 + bild.RAND_PX + 60


def test_fehlt_das_bild_der_vorseite_ist_ihr_inhalt_benannt():
    oben = bild.Aufnahme(None, [], ["Speicher", "Raten"], "kaputt")
    unten = _aufnahme("blue", 60, ["Tarif", "Preis"], [])
    ganz = bild.stapel(oben, unten)
    assert ganz.bild == unten.bild
    assert ganz.ohne == ["Speicher", "Raten"]


def test_zu_hohes_rechteck_verliert_das_fernste_merkmal():
    gefunden = {
        "preis": {"x": 0, "y": 1000, "w": 300, "h": 400},
        "merkmale": {
            "Gerät": {"x": 0, "y": 100, "w": 300, "h": 30},
            "Raten": {"x": 0, "y": 900, "w": 300, "h": 30},
        },
    }
    _, drin = bild.waehle_kaesten(gefunden)
    assert drin == ["Gerät", "Raten", "Preis"]
    gefunden["merkmale"]["Gerät"]["y"] = 1000 - bild.HOEHE_HOECHSTENS_PX
    _, drin = bild.waehle_kaesten(gefunden)
    assert drin == ["Raten", "Preis"]


@pytest.mark.parametrize(
    ("sku", "modell"),
    [
        ("apple-iphone-17-pro-256gb-schwarz", "iphone 17 pro"),
        ("samsung-galaxy-s26-ultra-1024gb-titan", "galaxy s26 ultra"),
        ("google-pixel-10a-128gb-blau-refurbished", "pixel 10a"),
    ],
)
def test_modell_ohne_marke_und_speicher(sku, modell):
    assert bild.modell_text(sku) == modell


def test_nadeln_aus_dem_bestandssatz():
    n = bild.nadeln(_satz(24, "samsung-galaxy-s26-1024gb-schwarz"))
    assert n["Tarif"] == ["O2 Mobile L"]
    assert n["Speicher"] == ["1 TB", "1024 GB"]
    assert "x 24" in n["Raten"] and "24 Monate" not in n["Raten"]
    einmal = {**_satz(24), "geraet_monatsrate": 0.0}
    assert "Raten" not in bild.nadeln(einmal)
    assert bild.erwartet(einmal) == ["Gerät", "Speicher", "Tarif", "Preis"]


def test_von_einer_leiste_verdecktes_merkmal_ist_nicht_im_bild(chromium):
    """Ein Banner über der Speicherwahl (1&1, Live-Prüfung 21.11.2026): der Text steht
    im Ausschnitt, ist aber verdeckt und zählt darum nicht als gezeigt."""
    s = chromium.new_page(viewport={"width": 1440, "height": 1000})
    s.set_content(
        SEITE.replace(
            "<p>Speicher: <b>256 GB</b></p>",
            '<p id="sp">Speicher: <b>256 GB</b></p><div style="position:absolute;'
            'left:0;width:700px;height:60px;background:#fff;z-index:5" id="banner">'
            "Herzlich willkommen</div>",
        )
    )
    s.evaluate(
        """() => { const b = document.getElementById('banner');
        const r = document.getElementById('sp').getBoundingClientRect();
        b.style.top = (r.top + scrollY - 20) + 'px'; }"""
    )
    a = bild.aufnehme(s, _satz(24), ANKER)
    s.close()
    assert "Speicher" in a.ohne and "Speicher" not in a.zeigt
    assert "Preis" in a.zeigt


GEKAPPT = """<html><body style="margin:0;font:16px sans-serif">
<h1>Apple iPhone 17</h1>
<div style="height:24px;overflow:hidden;width:500px;border:1px solid #888">
  <p style="margin:0">Auswahl</p>
  <div style="height:60px"></div>
  <p>Speicher: <b>256 GB</b></p>
</div>
<p>Tarif: O2 Mobile L</p><p>Ratenzahlung: 24 Monate</p>
<aside><h2>Dein Angebot</h2><p>Gerät monatlich: 40,00 €</p>
<p>einmalig gesamt: 7,99 €</p></aside>
</body></html>"""

LEISTE = """<html><body style="margin:0;font:16px sans-serif">
<h1>Apple iPhone 17</h1><p>Speicher: <b>256 GB</b></p>
<p>Tarif: O2 Mobile L</p><p>Ratenzahlung: 24 Monate</p>
<aside><h2>Dein Angebot</h2><p>Gerät monatlich: 40,00 €</p>
<p>einmalig gesamt: 7,99 €</p></aside>
<div style="position:fixed;left:0;top:0;width:300px;background:#fff;
 border:2px solid red">49,99 €/Mon. Allnet Flat S</div>
<div style="height:3000px"></div>
</body></html>"""


def _auf(chromium, html: str) -> bild.Aufnahme:
    s = chromium.new_page(viewport={"width": 1440, "height": 1000})
    s.set_content(html)
    try:
        return bild.aufnehme(s, _satz(24), ANKER)
    finally:
        s.close()


def test_abgeschnittenes_merkmal_zaehlt_nicht(chromium):
    """Prüfer PR 204: ein Merkmal im beschnittenen Teil einer Zeile (overflow)."""
    a = _auf(chromium, GEKAPPT)
    assert a.bild is not None
    assert "Speicher" in a.ohne and "Speicher" not in a.zeigt


def test_leiste_mit_fremdem_preis_ist_keine_ganze_konfiguration(chromium):
    """Prüfer PR 204 (1&1, 21.11.2026): eine haftende Leiste mit anderem Monatspreis."""
    a = _auf(chromium, LEISTE)
    assert bild.WIDERSPRUCH in a.ohne
    assert "Preis" in a.zeigt


def test_nicht_gewaehlte_kachel_zaehlt_nicht(chromium):
    """Vor der Wahl steht „24 Raten“ auf einer Kachel, gewählt ist sie nicht."""
    s = chromium.new_page(viewport={"width": 1440, "height": 1000})
    s.set_content(SEITE)
    a = bild.aufnehme(s, _satz(24), ANKER)
    s.get_by_text("24 Raten", exact=True).click()
    b = bild.aufnehme(s, _satz(24), ANKER)
    s.close()
    assert "Raten" in a.ohne
    assert "Raten" in b.zeigt


def test_bild_wartet_bis_der_preis_dem_gelesenen_gleicht(chromium):
    """o2 füllt die Beträge nach: das Bild nimmt erst den gefüllten Preisbereich."""
    s = chromium.new_page(viewport={"width": 1440, "height": 1000})
    s.set_content(
        SEITE.replace('<span id="b">–</span>', '<span id="b"></span>').replace(
            "einmalig gesamt: 7,99 €", "einmalig gesamt: <span id='e'></span>"
        )
        + "<script>setTimeout(() => { document.getElementById('b').textContent ="
        " '40,00 €'; document.getElementById('e').textContent = '7,99 €'; }, 800)"
        "</script>"
    )
    a = bild.aufnehme(s, _satz(24), ANKER, gelesen="Gerät monatlich: 40,00 € 7,99 €")
    falsch = bild.aufnehme(s, _satz(24), ANKER, gelesen="Gerät monatlich: 41,00 €")
    s.close()
    assert "Preis" in a.zeigt
    assert "Preis" in falsch.ohne
