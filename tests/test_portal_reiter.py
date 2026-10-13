"""Kriterium 11b von scripts/pruefe_portal.py schaltet jeden Reiter der
Geraeteseite. Der Reiter "Uebersicht" ist versteckt und nur ueber den Anker
erreichbar; ein Klick darauf wartete bis zum Timeout und die Abnahme hing
(Campus-Thread, 13.10.2026)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from test_glas_schalter import server

from telco_radar.report.html import schreibe_statische_dateien

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
pruefe_portal = importlib.import_module("pruefe_portal")


_SEITE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="style.css"></head><body><main>
<nav class="gr-reiter" role="tablist">
<button type="button" role="tab" aria-selected="true" data-tafel="tafel-tco">A</button>
<button type="button" role="tab" aria-selected="false" data-tafel="tafel-verlauf">B
</button><button type="button" role="tab" aria-selected="false" hidden
 data-tafel="tafel-radar">C</button></nav>
<div class="gr-tafel" id="tafel-tco">a</div>
<div class="gr-tafel gr-tafel--aus" id="tafel-verlauf">b</div>
<div class="gr-tafel gr-tafel--aus" id="tafel-radar">c</div>
</main><script src="app.js"></script></body></html>"""


@pytest.fixture(scope="module")
def basis(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("portal")
    schreibe_statische_dateien(ordner)
    (ordner / "geraete.html").write_text(_SEITE, encoding="utf-8")
    with server(ordner) as adresse:
        yield adresse


def test_jeder_reiter_wird_geschaltet_auch_der_versteckte(chromium, basis):
    context = chromium.new_context(viewport={"width": 1440, "height": 900})
    s = context.new_page()
    s.set_default_timeout(5000)
    try:
        s.goto(f"{basis}/geraete.html", wait_until="load")
        knoepfe = s.query_selector_all(".gr-reiter [data-tafel]")
        assert any(not k.is_visible() for k in knoepfe)
        gezeigt = []
        for knopf in knoepfe:
            tid = knopf.get_attribute("data-tafel")
            pruefe_portal.waehle_tafel(s, knopf, tid)
            sichtbar = s.evaluate(
                "(tid) => getComputedStyle(document.getElementById(tid)).display",
                tid,
            )
            assert sichtbar != "none"
            gezeigt.append(tid)
        assert gezeigt == ["tafel-tco", "tafel-verlauf", "tafel-radar"]
    finally:
        context.close()
