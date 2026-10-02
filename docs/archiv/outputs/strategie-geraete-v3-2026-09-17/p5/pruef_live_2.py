#!/usr/bin/env python3
"""Nachlauf P5: Katalog-Umschalter Barpreis/TCO + Deep-Link-Fallback."""
from __future__ import annotations

import contextlib
import http.server
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"
URL = "http://127.0.0.1:8774/geraete.html"


@contextlib.contextmanager
def server():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(SITE), **kw)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 8774), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield
    finally:
        httpd.shutdown()
        httpd.server_close()


def main():
    erg = {}
    with server(), sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto(URL, wait_until="load")
        page.wait_for_timeout(600)
        page.click('button[data-tafel="tafel-katalog"]')
        page.wait_for_timeout(400)

        tco_knopf = page.get_by_role("button", name="Gesamtkosten (TCO-24)")
        bar_knopf = page.get_by_role("button", name="Einzelgerätpreis")
        erg["knoepfe_da"] = bool(tco_knopf and bar_knopf)

        # Sichtbare Spaltenkoepfe + Stichprobenzelle vorher
        koepfe_vor = page.eval_on_selector_all(
            '#tafel-katalog thead th',
            "els => els.filter(e => e.offsetParent !== null)"
            ".map(e => e.innerText.trim())")
        # iPhone-18-Zeile holen (Suche macht sie sichtbar)
        page.fill('#tafel-katalog input[data-filter="suche"]', "iPhone 18 Pro 256")
        page.wait_for_timeout(400)
        zelle_vor = page.eval_on_selector(
            '#tafel-katalog tr[data-modell="apple-iphone-18-pro-256"]',
            "e => e.innerText.replace(/\\s+/g,' ')")
        page.fill('#tafel-katalog input[data-filter="suche"]', "")
        page.wait_for_timeout(300)

        tco_knopf.click()
        page.wait_for_timeout(500)
        koepfe_nach = page.eval_on_selector_all(
            '#tafel-katalog thead th',
            "els => els.filter(e => e.offsetParent !== null)"
            ".map(e => e.innerText.trim())")
        page.fill('#tafel-katalog input[data-filter="suche"]', "iPhone 18 Pro 256")
        page.wait_for_timeout(400)
        zelle_nach = page.eval_on_selector(
            '#tafel-katalog tr[data-modell="apple-iphone-18-pro-256"]',
            "e => e.innerText.replace(/\\s+/g,' ')")
        pressed = page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'#tafel-katalog button[aria-pressed]'))"
            ".map(e => [e.innerText.trim().slice(0,30),"
            " e.getAttribute('aria-pressed')])")
        erg["koepfe_vor"] = koepfe_vor
        erg["koepfe_nach"] = koepfe_nach
        erg["zelle_vor"] = zelle_vor[:260]
        erg["zelle_nach"] = zelle_nach[:260]
        erg["aria_pressed_nach_klick"] = pressed

        # Deep-Link auf Modell OHNE Zeitreihe: stiller Rueckfall erlaubt,
        # KEIN toter/leerer Zustand
        page.goto(URL + "?modell=apple-iphone-18-pro-256&band=klein",
                  wait_until="load")
        page.wait_for_timeout(1500)
        antwort = page.inner_text("#gr-zr-antwort") if page.query_selector(
            "#gr-zr-antwort") else ""
        svg = page.eval_on_selector_all(
            "#gr-zr-gruppe svg", "els => els.filter("
            "e => e.offsetParent !== null).length")
        titel = page.inner_text("#gr-zr-treffer").strip()
        erg["deeplink_ip18"] = {"antwort": antwort[:200], "svg_sichtbar": svg,
                                "treffer": titel}

        b.close()
    for k, v in erg.items():
        print(f"### {k}: {v}")


if __name__ == "__main__":
    main()
