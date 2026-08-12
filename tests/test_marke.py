"""Der Name des Portals - an EINER Stelle festgehalten.

Am 11.08.2026 ist aus "Vodafone Insights" das laengere "Vodafone Product and
Services Insights" geworden. Der Name stand an elf Stellen in den Vorlagen
(Seitentitel je Unterseite, Zeitungskopf, aria-Label, Fusszeile, die
Weiterleitungsseiten in html.py), und eine Umbenennung, die neun davon trifft,
sieht auf der Startseite fertig aus - auffallen wuerde sie erst auf der
Tarifseite oder in einem alten Lesezeichen.

Der Zeitungskopf ist der zweite Teil des Tests, und er ist der teurere: der
volle Name in EINER Schriftgroesse ist 475 statt 214 px breit und passte nicht
mehr in die Kopfleiste - auf dem Telefon lief er 61 px aus dem Bild, die ganze
Seite liess sich seitwaerts schieben. Deshalb steht der Mittelteil kleiner
(`.brand-zusatz`), und deshalb haelt ein Test die drei Bestandteile
zusammen: der Kopf muss den Namen VOLLSTAENDIG lesen, in der richtigen
Reihenfolge, mit dem kursiven Akzent am Ende.

Die Geometrie selbst (Versatz aus der Mitte, kein Seitwaertslauf) misst
scripts/pruefe_portal.py als Kriterium 12 im echten Browser - ein statischer
Test kann sie nicht sehen.
"""
import re

import pytest

from telco_radar.report.html import render_site

MARKE = "Vodafone Product and Services Insights"

# Alle Seiten, die base.html.j2 erben. promo/ liegt eine Ebene tiefer und
# traegt denselben Kopf - genau dort faellt ein halber Rename auf.
SEITEN = ("index.html", "meldungen.html", "differenzierung.html",
          "wettbewerb.html", "transparenz.html", "suche.html",
          "tarife.html", "lieferzeit.html", "geraete.html",
          "geraete-quellen.html", "promo/index.html", "promo/quellen.html")


def _site(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"
    render_site(site_dir, reports_dir, cfg=None)
    return site_dir


def _kopftext(html: str) -> str:
    """Der Zeitungskopf als reiner Text - so, wie ein Leser ihn liest.

    Der Name ist ausgezeichnet (`.brand-zusatz` klein, `<em>` kursiv); ein
    Test, der auf die Zeichenkette im HTML prueft, wuerde deshalb genau die
    Fassung durchwinken, die auf dem Telefon aus dem Bild laeuft."""
    treffer = re.search(r'<span class="brand-name">(.*?)</span>\s*</a>',
                        html, re.S)
    assert treffer, "kein Zeitungskopf (.brand-name) auf der Seite"
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", treffer.group(1))).strip()


def test_jede_seite_traegt_den_namen_im_titel(tmp_path):
    site_dir = _site(tmp_path)
    ohne = []
    for name in SEITEN:
        datei = site_dir / name
        if not datei.exists():          # geraete.html haengt an Daten
            continue
        titel = re.search(r"<title>(.*?)</title>",
                          datei.read_text(encoding="utf-8"), re.S)
        assert titel, name
        # Die Unterseiten der Promo Uebersicht und der Marktrecherche tragen
        # ihre eigene Ueberschrift im Titel ("Promo Uebersicht - Quellen").
        # Sie muessen den Markennamen nicht wiederholen; der Kopf tut es.
        # Wer ihn aber traegt, traegt ihn vollstaendig.
        text = titel.group(1)
        if "Insights" in text and MARKE not in text:
            ohne.append((name, text.strip()))
    assert not ohne, f"halber Rename im Seitentitel: {ohne}"


def test_der_zeitungskopf_liest_den_vollen_namen(tmp_path):
    """Der eigentliche Fall: Kopf und Titel koennen auseinanderlaufen."""
    site_dir = _site(tmp_path)
    gepruefte = 0
    for name in SEITEN:
        datei = site_dir / name
        if not datei.exists():
            continue
        assert _kopftext(datei.read_text(encoding="utf-8")) == MARKE, name
        gepruefte += 1
    # Ohne diese Zeile prueft der Test nichts, wenn render_site die Namen
    # aendert - dieselbe Falle wie am 09.08.2026 beim Schlagzeilen-Lookup.
    assert gepruefte >= 8, f"nur {gepruefte} Seiten geprueft"


def test_der_kopf_behaelt_seinen_kursiven_akzent(tmp_path):
    """Der Stil des Kopfes: Serife, roemisch, und das letzte Wort kursiv.

    Faellt das <em>, ist es kein Zeitungskopf mehr, sondern eine Zeile."""
    html = (_site(tmp_path) / "index.html").read_text(encoding="utf-8")
    kopf = re.search(r'<span class="brand-name">(.*?)</span>\s*</a>', html, re.S)
    assert kopf
    roh = kopf.group(1)
    assert "<em>Insights</em>" in roh
    assert '<span class="brand-zusatz">Product and Services</span>' in roh
    # Reihenfolge: der Zusatz steht ZWISCHEN "Vodafone" und "Insights" - als
    # Anhaengsel hinter dem kursiven Wort waere es ein anderer Name.
    assert roh.index("brand-zusatz") < roh.index("<em>")


def test_der_zusatz_steht_kleiner_als_der_rest(tmp_path):
    """Die eine Regel, die den Kopf in die Leiste passen laesst.

    Ohne sie ist der Name 475 statt 373 px breit - gemessen am 11.08.2026 im
    Browser -, sitzt 169 px links der Mitte und laeuft auf 390 px Breite aus
    dem Bild."""
    css = (_site(tmp_path) / "style.css").read_text(encoding="utf-8")
    regel = re.search(r"\.brand-name \.brand-zusatz\{([^}]*)\}", css)
    assert regel, "die Regel fuer den Namenszusatz fehlt"
    groesse = re.search(r"font-size:(\.?\d*\.?\d+)em", regel.group(1))
    assert groesse, regel.group(1)
    assert float(groesse.group(1)) <= 0.6


def test_die_alten_seiten_leiten_unter_dem_neuen_namen_weiter(tmp_path):
    """Die Weiterleitungen stehen in Lesezeichen und Mails - sie sind der
    Ort, an dem der alte Name am laengsten ueberlebt haette."""
    site_dir = _site(tmp_path)
    for alt in ("bericht.html", "archive.html", "sources.html",
                "protokoll.html", "wettbewerber.html"):
        datei = site_dir / alt
        if not datei.exists():
            continue
        text = datei.read_text(encoding="utf-8")
        assert MARKE in text, alt


def test_kein_alter_name_mehr_in_den_vorlagen():
    """Gegen die Quelle, nicht gegen die Ausgabe: eine Vorlage, die heute
    nicht gerendert wird (thema/, folien/), faellt sonst durch jedes Raster."""
    from pathlib import Path
    wurzel = Path(__file__).resolve().parent.parent / "src" / "telco_radar"
    reste = []
    for datei in [*wurzel.rglob("*.j2"), *wurzel.rglob("*.py"),
                  *wurzel.rglob("*.css")]:
        text = datei.read_text(encoding="utf-8")
        for treffer in re.finditer(r"Vodafone Insights", text):
            reste.append(f"{datei.name}:{text[:treffer.start()].count(chr(10)) + 1}")
    assert not reste, f"alter Name uebrig: {reste}"


# ==========================================  Der Kopf und die Schriftbreite ==
# Der teuerste Fehler dieser Kopfleiste ist nicht, dass sie zu breit ist -
# sondern dass ihre Breite gegen EINE Schrift kalibriert war.

def _chromium():
    import os
    for kandidat in ("/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                     os.path.expanduser(
                         "~/.cache/ms-playwright/chromium-1194/chrome-linux/chrome"),
                     os.environ.get("CHROMIUM_PFAD", "")):
        if kandidat and os.path.exists(kandidat):
            return kandidat
    return None


def test_der_kopf_laeuft_auch_mit_breiterer_schrift_nicht_aus_dem_bild(tmp_path):
    """Die Regressionsprobe zu CI-Lauf #159.

    Bis zum 12.08.2026 trug `.brand-name` auch auf dem Telefon
    `white-space:nowrap`, und die Passgenauigkeit haengte an einer gemessenen
    Zahl: 307 px bei 390 px Bildbreite. Gemessen war sie allerdings in einer
    Sandbox, in der Google Fonts nicht laden - es war die Breite der
    RUECKFALLSCHRIFT. In GitHub Actions laedt die echte Source Serif 4, sie
    ist breiter, und die Geraeteseiten liefen waagerecht aus dem Bild.

    Dieser Test misst deshalb nicht eine Breite, sondern eine EIGENSCHAFT:
    der Kopf darf auch dann nicht ueberlaufen, wenn der Name deutlich
    breiter rendert als heute. Simuliert wird das mit `letter-spacing` -
    unabhaengig davon, welche Schrift die Testmaschine wirklich bekommt.
    Ein Test, der die echte Schrift braeuchte, waere in der Sandbox gruen und
    in CI rot, also genau so viel wert wie keiner.
    """
    import contextlib
    import functools
    import http.server
    import socket
    import threading

    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    exe = _chromium()
    if exe is None:
        pytest.skip("kein Chromium gefunden")

    site_dir = _site(tmp_path)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(site_dir))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    gemessen = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=exe,
                args=["--no-sandbox", "--disable-dev-shm-usage"])
            for aufschlag in (0, 1.2, 3.0):
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.goto(f"http://127.0.0.1:{port}/index.html")
                # Der Aufschlag macht den Namen breiter, ohne eine bestimmte
                # Schrift vorauszusetzen. 3 px je Zeichen sind rund 40 % mehr
                # Breite - deutlich mehr, als eine Serife gegenueber ihrer
                # Rueckfallschrift ausmacht.
                page.add_style_tag(content=(
                    f".brand-name{{letter-spacing:{aufschlag}px}}"))
                page.wait_for_timeout(120)
                gemessen[aufschlag] = page.evaluate(
                    """() => ({
                         doc: document.documentElement.scrollWidth,
                         fenster: window.innerWidth,
                         kopf: Math.ceil(
                           document.querySelector('.brand-name')
                                   .getBoundingClientRect().right),
                       })""")
                page.close()
            browser.close()
    finally:
        httpd.shutdown()

    schuldig = [f"+{a} px Sperrung: Seite {m['doc']} px breit bei "
                f"{m['fenster']} px Fenster"
                for a, m in gemessen.items() if m["doc"] > m["fenster"] + 1]
    assert not schuldig, schuldig
    # ... und der Kopf selbst bleibt im Bild.
    ragt = [f"+{a} px: Kopf endet bei {m['kopf']} px"
            for a, m in gemessen.items() if m["kopf"] > m["fenster"] + 1]
    assert not ragt, ragt
    # Gegenprobe: der Aufschlag hat wirklich etwas veraendert - sonst misst
    # der Test dreimal dasselbe.
    breiten = {m["kopf"] for m in gemessen.values()}
    assert len(breiten) > 1, f"Aufschlag ohne Wirkung: {gemessen}"
