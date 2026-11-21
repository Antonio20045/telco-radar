"""o2 „Plus“: der Hinweis steht dort, wo die Geräteseite den Plus-Zustand zeigt.

Prüfung PR 207 (21.11.2026): „mit Zweitprodukt x € im Monat günstiger“ stand nur in
den Bündelzeilen der Fragmente (`data/bnd/*.html`), die `app.js` beim Modellwechsel
verwirft; sichtbar war auf `geraete.html` nur „nur mit Zweitprodukt“ in der Δ-Spalte.
Jetzt nennt genau diese Stelle „Plus: x € günstiger mit Zweitprodukt“ - x ist das
Feld `plus_vorteil` am Plus-Bündel (`tco_plus`, im Gerätelauf gesetzt), die Seite
rechnet nichts. Ohne Feld heißt es „Rabatt nur mit Zweitprodukt“, ohne Betrag.

Fixture: der synthetische Bestand aus `test_geraete_buendel_kopf_zeitraum` (iPhone 17
Pro 256 GB), darin nur Vodafone und o2; der o2-Tarif heißt „… Plus“. Vodafone stellt
das Minimum, o2 zählt nicht - die Δ-Zelle der Modellzeile nennt den Zustand der
o2-Karte. Gerendert mit `render_site`, geprüft wird `geraete.html`, nicht die
Fragmente; dazu ein Blick im echten Chromium mit Deep-Link.
"""

from __future__ import annotations

import functools
import http.server
import json
import re
import shutil
import threading

import pytest
import test_geraete_buendel_kopf_zeitraum as basis

from telco_radar.report.html import render_site

HINWEIS = "Plus: 5,00 € günstiger mit Zweitprodukt"
OHNE = "Rabatt nur mit Zweitprodukt"
_ALT = re.compile(r"(?<!Rabatt )nur mit Zweitprodukt")


def _seite(tmp_path, plus_vorteil):
    site = basis._baue(tmp_path)
    wurzel = site.parent
    datei = wurzel / "data" / "state" / "geraete_tco.json"
    tco = json.loads(datei.read_text(encoding="utf-8"))
    behalten = []
    for b in tco["buendel"]:
        if b["anbieter"] == "o2":
            b["tarif_name"] = "O2 Mobile Klein Plus"
            if plus_vorteil is not None:
                b["plus_vorteil"] = plus_vorteil
        if b["anbieter"] in ("o2", "Vodafone"):
            behalten.append(b)
    tco["buendel"] = behalten
    datei.write_text(json.dumps(tco), encoding="utf-8")
    shutil.rmtree(site)
    render_site(site, wurzel / "data" / "reports")
    return site


@pytest.fixture(scope="module")
def mit_betrag(tmp_path_factory):
    return _seite(tmp_path_factory.mktemp("plus5"), 5.0)


def test_geraeteseite_nennt_den_plus_abstand_statt_nur_mit_zweitprodukt(mit_betrag):
    html = (mit_betrag / "geraete.html").read_text(encoding="utf-8")
    assert HINWEIS in html
    assert not _ALT.search(html), "der alte Text steht noch daneben"


def test_gegenprobe_ohne_feld_kein_betrag(tmp_path):
    html = (_seite(tmp_path, None) / "geraete.html").read_text(encoding="utf-8")
    assert OHNE in html
    assert "günstiger mit Zweitprodukt" not in html


@pytest.mark.browser
def test_hinweis_ist_im_browser_sichtbar(mit_betrag, chromium):
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(mit_betrag)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        for breite in (1440, 390):
            ctx = chromium.new_context(viewport={"width": breite, "height": 900})
            try:
                s = ctx.new_page()
                url = (
                    f"http://127.0.0.1:{httpd.server_address[1]}/geraete.html"
                    f"?modell={basis.MODELL}"
                )
                s.goto(url, wait_until="domcontentloaded")
                s.wait_for_timeout(1500)
                treffer = s.get_by_text(HINWEIS, exact=True)
                assert any(
                    treffer.nth(i).is_visible() for i in range(treffer.count())
                ), breite
            finally:
                ctx.close()
    finally:
        httpd.shutdown()
