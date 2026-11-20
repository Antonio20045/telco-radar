"""Kundenweg der Gegenprobe im Browser, an lokalen Seiten (``gegenprobe_browser``)."""

from __future__ import annotations

import pytest

from telco_radar.collect.geraete import gegenprobe_browser as gb
from telco_radar.collect.geraete import gegenprobe_wege as wege

SEITE = """
<html><body>
  <nav>Preisübersicht Werbung</nav>
  <main>
    <section id="gross">
      <div id="preis"><h2>Dein Angebot</h2><p>Gerät monatlich: 18,50 €</p>
        <p>einmalig gesamt: 7,99 €</p><p style="display:none">Geheim 1,00 €</p></div>
      <p>Weiteres</p>
    </section>
    <div style="display:none"><h2>Dein Angebot</h2>Gerät monatlich einmalig gesamt</div>
    <label id="a"><input type="radio" name="s"> 256 GB</label>
    <label id="b"><input type="radio" name="s" disabled> 512 GB</label>
  </main>
</body></html>
"""


@pytest.fixture
def seite(chromium):
    s = chromium.new_page()
    s.set_content(SEITE)
    yield s
    s.close()


@pytest.mark.parametrize(
    ("sku", "speicher"),
    [
        ("apple-iphone-17-pro-256gb-cosmic-orange", "256 GB"),
        ("samsung-galaxy-s26-ultra-1024gb-schwarz", "1 TB"),
        ("apple-iphone-17-pro-max-2048gb-silber", "2 TB"),
        ("xiaomi-18-pro-512gb-velvet-red", "512 GB"),
        ("apple-iphone-17-pro-1tb-silber", "1 TB"),
        ("ohne-speicher", None),
    ],
)
def test_speicher_aus_sku(sku, speicher):
    assert gb.speicher_aus_sku(sku) == speicher


def test_bereich_ist_das_kleinste_sichtbare_element_mit_allen_ankern(seite):
    element = gb.bereich(seite, ("Dein Angebot", "Gerät monatlich", "einmalig gesamt"))
    assert element.get_attribute("id") == "preis"


def test_text_des_bereichs_ohne_unsichtbares(seite):
    text = gb.text_von(seite, ("Dein Angebot", "einmalig gesamt"))
    assert "18,50 €" in text and "Geheim" not in text


def test_anker_ohne_gross_und_kleinschreibung(seite):
    element = gb.bereich(seite, ("DEIN ANGEBOT", "gerät MONATLICH"))
    assert element.get_attribute("id") == "preis"


def test_fehlender_bereich_ist_nicht_pruefbar_mit_ankern(seite):
    with pytest.raises(gb.NichtPruefbar, match="Preisbereich nicht gefunden: Fehlt"):
        gb.bereich(seite, ("Fehlt",))


def test_sichtbares_html_laesst_verstecktes_und_attribute_weg(seite):
    html = gb.sichtbares_html(seite, ("Dein Angebot", "einmalig gesamt"))
    assert "Geheim" not in html and "id=" not in html and "18,50 €" in html


def test_klick_auf_gesperrte_auswahl_ist_nicht_pruefbar(seite):
    with pytest.raises(gb.NichtPruefbar, match="gesperrt: 512 GB"):
        gb.klicke(seite, seite.locator("#b"), "512 GB")


def test_klick_ohne_treffer_ist_nicht_pruefbar(seite):
    with pytest.raises(gb.NichtPruefbar, match="nicht gefunden: 1 TB"):
        gb.klicke(seite, seite.get_by_text("1 TB"), "1 TB")


def test_klick_waehlt_die_option(seite):
    gb.klicke(seite, seite.locator("#a"), "256 GB")
    assert seite.locator("#a input").is_checked()


def test_einwilligung_wird_abgelehnt(chromium):
    s = chromium.new_page()
    try:
        s.set_content(
            "<div id='c'><button onclick=\"document.getElementById('c').remove()\">"
            "Alles ablehnen</button><button>Alles akzeptieren</button></div>"
        )
        gb.lehne_einwilligung_ab(s)
        assert s.locator("#c").count() == 0
    finally:
        s.close()


@pytest.mark.parametrize(
    ("text", "ablehnen"),
    [
        ("Alles ablehnen", True),
        ("Cookies ablehnen", True),
        ("Nur notwendige", True),
        ("Alles akzeptieren", False),
        ("Einstellungen verwalten", False),
    ],
)
def test_ablehnen_knopf_erkannt(text, ablehnen):
    assert bool(gb.EINWILLIGUNG_AB.search(text)) is ablehnen


def _antwort(seite, status: int, body: str = "<p>x</p>"):
    seite.route(
        "**/*",
        lambda route: route.fulfill(status=status, body=body, content_type="text/html"),
    )


@pytest.mark.parametrize("status", [401, 403, 429])
def test_sperre_wird_nicht_umgangen(chromium, status):
    s = chromium.new_page()
    try:
        _antwort(s, status)
        with pytest.raises(gb.Gesperrt, match=f"HTTP {status}"):
            gb.oeffne(s, "http://127.0.0.1:9/geraet")
    finally:
        s.close()


def test_fehlerseite_ist_nicht_pruefbar(chromium):
    s = chromium.new_page()
    try:
        _antwort(s, 500)
        with pytest.raises(gb.NichtPruefbar, match="HTTP 500"):
            gb.oeffne(s, "http://127.0.0.1:9/geraet")
    finally:
        s.close()


def test_captcha_ist_eine_sperre(chromium, monkeypatch):
    monkeypatch.setattr(gb, "NACH_LADEN_MS", 0)
    monkeypatch.setattr(gb, "RUHEFRIST_MS", 500)
    s = chromium.new_page()
    try:
        _antwort(s, 200, "<iframe src='about:blank#captcha'></iframe>")
        with pytest.raises(gb.Gesperrt, match="Captcha"):
            gb.oeffne(s, "http://127.0.0.1:9/geraet")
    finally:
        s.close()


def test_bild_des_bereichs_ist_webp(seite):
    bild, fehlt = gb.bild_von(seite, ("Dein Angebot", "einmalig gesamt"))
    assert fehlt is None and bild[:4] == b"RIFF" and bild[8:12] == b"WEBP"


def test_bild_ohne_bereich_nennt_den_grund(seite):
    bild, fehlt = gb.bild_von(seite, ("Fehlt",))
    assert bild is None and fehlt.startswith("Bild nicht aufgenommen")


def test_unbekannter_anbieter_hat_keinen_weg(chromium):
    with pytest.raises(gb.NichtPruefbar, match="keinen Kundenweg"):
        wege.lies(chromium, "fraenk", {"quelle_url": "http://127.0.0.1:9/"}, None)
