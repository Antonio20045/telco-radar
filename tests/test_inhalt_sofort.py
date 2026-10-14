"""Inhalt sofort sichtbar (Antonio, 14.10.2026).

"Zu viel Bewegung ... es braucht zu lange, bis man zum Inhalt kommt." Auf
Meldungen, Wettbewerb, Geraete und Promo stand ein Startbild ueber eine
Scrollstrecke von 1,5 bis 2,3 Bildschirmhoehen; der Wochenbericht zeigte je
Kapitel ein Vollbild, das beim Scrollen aufschnitt, und blendete jeden
Absatz einzeln ein. Gemessen wird im Browser ohne zu scrollen: das Kopfband
ist flach, der erste Inhalt steht im ersten Bildschirm, die Bilder im
Bericht sind klein und stehen still, und der Text ist sofort deckend.
"""

from __future__ import annotations

import functools
import http.server
import shutil
import threading

import pytest
from bestand_pfad import BILDER_ZUSTAND, abbild

from telco_radar.config import load_config
from telco_radar.report.html import render_site

FORMATE = [(1440, 900), (390, 844)]

SEITEN = ["meldungen.html", "wettbewerb.html", "geraete.html", "promo/index.html"]

_ERSTER_INHALT = """() => {
  const band = document.querySelector('main .kopfband');
  const rumpf = band && band.nextElementSibling;
  let oben = null;
  if (rumpf) for (const el of rumpf.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    const blatt = el.children.length === 0 && el.textContent.trim();
    if (r.height > 8 && blatt) { oben = r.top; break; }
  }
  return {band: band && band.getBoundingClientRect().height,
          strecke: !!document.querySelector('[data-buehne]'), oben: oben};
}"""


@pytest.fixture(scope="module")
def adresse(tmp_path_factory):
    """Die echte Seite aus dem Datenabbild - mit Geraeten und Promo."""
    wurzel = tmp_path_factory.mktemp("sofort")
    berichte = abbild(wurzel)
    for name in ("promo_images", "report_images"):
        shutil.copytree(BILDER_ZUSTAND / name, wurzel / "data" / "state" / name)
    site = wurzel / "site"
    render_site(site, berichte, load_config(wurzel))
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.mark.parametrize("breite,hoehe", FORMATE)
@pytest.mark.parametrize("name", SEITEN)
def test_der_inhalt_steht_im_ersten_bildschirm(adresse, chromium, name, breite, hoehe):
    seite = chromium.new_page(viewport={"width": breite, "height": hoehe})
    try:
        seite.goto(f"{adresse}/{name}")
        m = seite.evaluate(_ERSTER_INHALT)
    finally:
        seite.close()
    assert m["band"] is not None, f"{name}: kein Kopfband"
    assert m["band"] <= hoehe * 0.45, f"{name}: Kopfband {m['band']} px hoch"
    assert not m["strecke"], f"{name}: Scrollstrecke data-buehne steht wieder da"
    assert m["oben"] is not None and m["oben"] < hoehe * 0.6, (
        f"{name}: erster Inhalt erst bei {m['oben']} px"
    )


@pytest.mark.parametrize("breite,hoehe", FORMATE)
def test_der_bericht_steht_still_mit_kleinen_bildern(adresse, chromium, breite, hoehe):
    seite = chromium.new_page(viewport={"width": breite, "height": hoehe})
    try:
        seite.goto(f"{adresse}/index.html")
        seite.wait_for_timeout(300)
        m = seite.evaluate(
            """() => {
              const alle = (s) => [...document.querySelectorAll(s)];
              const bilder = alle('.bericht .szene-bild');
              const texte = alle('.bericht .szene-text p, .bericht .szene-text li');
              const box = (b) => b.getBoundingClientRect();
              const stil = (b) => getComputedStyle(b);
              return {
                bilder: bilder.length,
                hoch: Math.max(0, ...bilder.map(b => box(b).height)),
                breit: Math.max(0, ...bilder.map(b => box(b).width)),
                geschnitten: bilder.filter(b => stil(b).clipPath !== 'none').length,
                texte: texte.length,
                versteckt: texte.filter(t => stil(t).opacity !== '1').length,
              };
            }"""
        )
    finally:
        seite.close()
    assert m["bilder"] > 0 and m["texte"] > 0, m
    assert m["hoch"] <= hoehe * 0.4, f"Kapitelbild {m['hoch']} px hoch"
    assert m["breit"] <= max(360, breite * 0.3) or breite < 900, m
    assert m["geschnitten"] == 0, m
    assert m["versteckt"] == 0, f"{m['versteckt']} Absaetze warten aufs Einblenden"
