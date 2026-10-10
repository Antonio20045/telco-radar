"""Handys laden die großen Bilder in 1200 px (Seite schneller, 10.10.2026).

Ein Kopfbild mit 2400 px wog auf dem Handy bis 570 KB und kam bei 4G erst
nach 2,3 s. Die 1200-px-Fassung sieht auf dem Handy gleich groß aus. Ihr
Dateiname trägt den Inhalt des Originals: ein getauschtes Bild ohne neue
Fassung lädt wieder das große Original, nie ein altes Motiv.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from telco_radar import bild_vorschau
from telco_radar.report import statik

_TEMPLATES = Path(statik.__file__).parent / "templates"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    from orakel.test_seiten_inhalt import PORTAL, render

    return render(tmp_path_factory.mktemp("klein"), highlights=PORTAL)


def _seite(site, name):
    from orakel.test_seiten_inhalt import lies_seite

    return BeautifulSoup(lies_seite(site, name), "html.parser")


def _klein_pfad(site, eintrag: str) -> Path:
    url, breite = eintrag.strip().split(" ")
    assert breite == "1200w", eintrag
    return site / url


def test_jedes_grosse_motiv_hat_eine_gueltige_handyfassung():
    ordner = _TEMPLATES / "static" / "bilder"
    fassungen = statik.kleine(_TEMPLATES)
    for bild in sorted(ordner.glob("*.jpg")):
        with Image.open(bild) as im:
            breit = im.width > bild_vorschau.KLEIN_BREITE
        assert (bild.stem in fassungen) == breit, bild.name
    for pfad in fassungen.values():
        with Image.open(ordner / pfad) as im:
            assert im.width == bild_vorschau.KLEIN_BREITE, pfad


def test_ein_getauschtes_bild_ohne_neue_fassung_faellt_aufs_original(tmp_path):
    for name, farbe in (("eins", (200, 30, 30)), ("zwei", (30, 30, 200))):
        Image.new("RGB", (2400, 1029), farbe).save(tmp_path / f"{name}.jpg")
        bild_vorschau.schreibe_kleine_fassung(tmp_path / f"{name}.jpg")
    Image.new("RGB", (800, 600), (0, 0, 0)).save(tmp_path / "schmal.jpg")
    assert bild_vorschau.schreibe_kleine_fassung(tmp_path / "schmal.jpg") is None
    assert set(bild_vorschau.kleine_fassungen(tmp_path)) == {"eins", "zwei"}
    Image.new("RGB", (2400, 1029), (30, 200, 30)).save(tmp_path / "eins.jpg")
    assert set(bild_vorschau.kleine_fassungen(tmp_path)) == {"zwei"}


def test_kopfbilder_bieten_dem_handy_die_kleine_fassung(site):
    bild = _seite(site, "meldungen.html").select_one(".wa-bild img.wa-motiv")
    klein, gross = bild["srcset"].split(",")
    assert _klein_pfad(site, klein).is_file()
    assert gross.strip() == "static/bilder/band-meldungen.jpg 2400w"
    assert bild["sizes"] == "100vw"
    ebenen = _seite(site, "index.html").select(".buehne-ebene[data-zeit-bild]")
    assert len(ebenen) == 4
    for ebene in ebenen:
        klein = ebene["data-srcset"].split(",")[0]
        assert _klein_pfad(site, klein).is_file(), ebene["data-zeit-bild"]
