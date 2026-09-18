#!/usr/bin/env python3
"""P5-LIVE-FALL-Pruefung: 'iPhone 18 muss automatisch erkannt und gefuehrt werden.'

Laeuft gegen den frisch gerenderten site/-Stand (18.09.2026) ueber einen
lokalen Server auf 127.0.0.1:8774. Kein Bau-Kontext, nur gerenderte Seite,
echter Bestand, echter Browser (Playwright/Chromium).

Prueft:
  1. Katalog: Suche 'iPhone 18' -> Modellzeilen, Preis/benannter Zustand
  2. (statisch, separat) Export-CSVs
  3. Zeitreihen-Wahl: 'iphone 18' -> Grund/Aussen, kein toter Sprung;
     Kontrollklick auf ein Modell MIT Zeitreihe
  4. Wearables (Watches/Tabs/AirPods): Katalog ja, Zeitreihen-Wahl nein
  5. P4-Stichprobe: kein Querscroll 390, Leitzahl groesste Schrift,
     Katalog-Umschalter Barpreis/TCO
"""
from __future__ import annotations

import contextlib
import http.server
import re
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
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield
    finally:
        httpd.shutdown()
        httpd.server_close()


def sichtbare_zeilen(page):
    return page.eval_on_selector_all(
        '#tafel-katalog tr.gr-a-zeile',
        "els => els.filter(e => e.offsetParent !== null && "
        "getComputedStyle(e).display !== 'none').map(e => ({"
        "modell: e.getAttribute('data-modell'),"
        "text: e.innerText.replace(/\\s+/g,' ').trim()}))")


def main():
    erg = {}
    with server(), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(URL, wait_until="load")
        page.wait_for_timeout(800)

        # ---------- 1. KATALOG: iPhone 18 ----------
        page.click('button[data-tafel="tafel-katalog"]')
        page.wait_for_timeout(400)
        KATSUCHE = '#tafel-katalog input[data-filter="suche"]'
        page.fill(KATSUCHE, "iPhone 18")
        page.wait_for_timeout(400)
        zeilen = sichtbare_zeilen(page)
        ip18 = [z for z in zeilen if "iphone-18" in z["modell"]]
        erg["katalog_ip18_zeilen"] = len(ip18)
        erg["katalog_ip18_detail"] = []
        for z in ip18:
            hat_preis = "€" in z["text"]
            benannt = any(s in z["text"] for s in
                          ["kein Bündel gemessen", "nur im Bündel", "noch keine Zeitreihe",
                           "ein Preis", "Händler", "bei "])
            erg["katalog_ip18_detail"].append({
                "modell": z["modell"],
                "preis_oder_benannt": bool(hat_preis or benannt),
                "text": z["text"][:220],
            })

        # Klick auf iPhone-18-Pro-256-Zeile -> Aufklapper oeffnet (nicht tot).
        # Der Katalog deckelt die Standardansicht; die Suche macht die Zeile
        # sichtbar - der Klick-Test laeuft deshalb MIT Suchfilter.
        page.fill(KATSUCHE, "iPhone 18 Pro 256")
        page.wait_for_timeout(400)
        ziel = page.query_selector('#tafel-katalog tr[data-modell="apple-iphone-18-pro-256"]:not([hidden])') or \
               page.query_selector('#tafel-katalog tr[data-modell="apple-iphone-18-pro-256"]')
        erg["katalog_klick_zeile_da"] = ziel is not None
        if ziel:
            auf_id = ziel.get_attribute("data-auf")
            ziel.scroll_into_view_if_needed()
            ziel.click()
            page.wait_for_timeout(500)
            det = page.query_selector(f'#{auf_id}') if auf_id else None
            erg["katalog_ip18_aufklapper"] = (
                det is not None and det.is_visible()
                and "€" in (det.inner_text() or ""))

        # ohne-details-Zeile (S24 Ultra 512): klick darf nichts oeffnen
        page.fill(KATSUCHE, "S24 Ultra 512")
        page.wait_for_timeout(400)
        ziel2 = page.query_selector(
            '#tafel-katalog tr[data-modell="samsung-galaxy-s24-ultra-512"]')
        erg["ohne_details_zeile_da"] = ziel2 is not None
        if ziel2:
            offen_vor = page.eval_on_selector_all(
                "#tafel-katalog details[open]", "els => els.length")
            ziel2.scroll_into_view_if_needed()
            ziel2.click()
            page.wait_for_timeout(400)
            offen_nach = page.eval_on_selector_all(
                "#tafel-katalog details[open]", "els => els.length")
            erg["ohne_details_klick_oeffnet_nichts"] = offen_nach <= offen_vor

        # ---------- 4. Wearables im Katalog ----------
        for begriff in ["Watch", "AirPods", "Tab S11"]:
            page.fill(KATSUCHE, begriff)
            page.wait_for_timeout(350)
            zs = sichtbare_zeilen(page)
            erg[f"katalog_{begriff.replace(' ', '_').lower()}_zeilen"] = len(zs)
            erg[f"katalog_{begriff.replace(' ', '_').lower()}_modelle"] = [
                z["modell"] for z in zs]
            erg[f"katalog_{begriff.replace(' ', '_').lower()}_preise"] = sum(
                1 for z in zs if "€" in z["text"])
        page.fill(KATSUCHE, "")

        # Umschalter Barpreis/TCO (P3) - Stichprobe
        knoepfe = page.eval_on_selector_all(
            '#tafel-katalog button',
            "els => els.filter(e => e.offsetParent !== null).map("
            "e => ({txt: e.innerText.trim().slice(0,40),"
            " pressed: e.getAttribute('aria-pressed')}))")
        erg["katalog_knoepfe"] = knoepfe
        um = page.query_selector('#tafel-katalog button[data-preis-art="tco"]') or \
             page.query_selector('#tafel-katalog button.um')
        erg["umschalter_gefunden"] = um is not None
        if um:
            vor = page.eval_on_selector(
                '#tafel-katalog', "e => e.innerText.length")
            um.click()
            page.wait_for_timeout(400)
            nach = page.eval_on_selector(
                '#tafel-katalog', "e => e.innerText.length")
            pressed = page.eval_on_selector_all(
                '#tafel-katalog button[data-preis-art]',
                "els => els.map(e => [e.getAttribute('data-preis-art'),"
                " e.getAttribute('aria-pressed')])")
            erg["umschalter_wirkt"] = {"text_geaendert": vor != nach,
                                       "pressed": pressed}

        # ---------- 3. Zeitreihen-Wahl ----------
        page.click('button[data-tafel="tafel-tco"]')
        page.wait_for_timeout(500)
        erg["zr_treffer_stand"] = page.inner_text("#gr-zr-treffer")
        for begriff in ["iphone 18", "iphone 1", "watch", "airpods", "tab s11"]:
            page.fill("#gr-zr-suche", begriff)
            page.wait_for_timeout(450)
            treffer = page.inner_text("#gr-zr-treffer").strip()
            vorschau = page.eval_on_selector_all(
                "#gr-zr-vorschau button",
                "els => els.map(e => e.innerText.trim().slice(0,50))")
            erg[f"zr_suche[{begriff}]"] = {"treffer": treffer,
                                           "vorschau": vorschau[:8]}
        # Kontrollklick: iphone 17 -> Zeitreihe erscheint
        page.fill("#gr-zr-suche", "iphone 17")
        page.wait_for_timeout(450)
        erster = page.query_selector("#gr-zr-vorschau button")
        erg["zr_iphone17_vorschau_da"] = erster is not None
        if erster:
            erster.click()
            page.wait_for_timeout(900)
            lager = page.eval_on_selector_all(
                "#gr-zr-gruppe .gr-zr-lager, #gr-zeitreihe svg, #gr-zr-gruppe svg",
                "els => els.filter(e => e.offsetParent !== null).length")
            antwort = page.inner_text("#gr-zr-antwort") if page.query_selector(
                "#gr-zr-antwort") else ""
            erg["zr_iphone17_klick"] = {"sichtbare_elemente": lager,
                                        "antwort": antwort[:200]}
        page.fill("#gr-zr-suche", "")

        # ---------- 5a. Leitzahl groesste Schrift (1440) ----------
        erg["schrift"] = page.evaluate("""
        () => {
          const out = [];
          document.querySelectorAll('#tafel-tco *').forEach(e => {
            if (e.offsetParent === null || !e.innerText || !e.innerText.trim())
              return;
            if (e.children.length > 0) return;   // nur Blatt-Knoten
            const fs = parseFloat(getComputedStyle(e).fontSize);
            if (fs > 0) out.push([fs, e.className && e.className.toString().slice(0,40),
                                  e.innerText.trim().slice(0,40)]);
          });
          out.sort((a,b) => b[0]-a[0]);
          return out.slice(0, 8);
        }""")

        # ---------- 2./3. tote Spruenge: Katalog/Hash-Spruenge aufs TCO-Modell --
        # gr-ksprung Links: alle zeigen ?modell=<id>; nach Klick muss der
        # Titel des gewaehlten Modells erscheinen (kein stiller Rueckfall)
        page.click('button[data-tafel="tafel-radar"]')
        page.wait_for_timeout(400)
        erg["radar_sprung_anzahl"] = page.eval_on_selector_all(
            "a.gr-ksprung", "els => els.length")
        href = page.evaluate(
            "() => { const s = Array.from(document.querySelectorAll('a.gr-ksprung'))"
            ".filter(e => e.offsetParent !== null);"
            " if (!s.length) return null; s[0].scrollIntoView({block:'center'});"
            " return s[0].getAttribute('href'); }")
        if href:
            page.wait_for_timeout(300)
            page.evaluate(
                "() => { const s = Array.from(document.querySelectorAll('a.gr-ksprung'))"
                ".filter(e => e.offsetParent !== null); s[0].click(); }")
            page.wait_for_timeout(900)
            titel = page.inner_text("#gr-zr-treffer").strip()
            mod = re.search(r"modell=([a-z0-9-]+)", href or "")
            erg["radar_sprung"] = {"href": href, "treffer_nach_klick": titel}

        # ---------- 5b. Querscroll 390 ----------
        m = browser.new_page(viewport={"width": 390, "height": 844})
        m.goto(URL, wait_until="load")
        m.wait_for_timeout(800)
        erg["querscroll_390"] = m.evaluate(
            "() => ({inner: window.innerWidth,"
            " doc: document.documentElement.scrollWidth,"
            " body: document.body.scrollWidth})")
        # auch im Katalog-Reiter (Tabellen sind der kritische Fall)
        m.click('button[data-tafel="tafel-katalog"]')
        m.wait_for_timeout(500)
        erg["querscroll_390_katalog"] = m.evaluate(
            "() => ({inner: window.innerWidth,"
            " doc: document.documentElement.scrollWidth,"
            " body: document.body.scrollWidth})")
        m.close()

        browser.close()

    for k, v in erg.items():
        print(f"### {k}: {v}")


if __name__ == "__main__":
    main()
