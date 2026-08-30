"""Die vier Reiter der Geraeteseite - im echten Browser gemessen.

WARUM IM BROWSER
----------------
Der Reiter und die Filter sind die einzigen Stellen der Seite, die im HTML
nicht zu sehen sind: alle Tafeln stehen fertig da und werden per Klasse
umgeblendet, die Filter setzen `hidden`. Ein statischer Test saehe nur, dass
alles dasteht.

Und die drei harten Verbote des Auftrags - kein gedrehter Text, keine Schrift
unter 12 px, keine mit "..." abgeschnittene Beschriftung - sind ausdruecklich
"im gerenderten SVG geprueft, nicht im Quelltext". Genau daran ist die
Vorgaengersitzung gescheitert: sie hatte Tests geschrieben und das Ergebnis
nie angesehen, und die Positionskarte ging mit Etiketten live, die bis zu
235 px neben ihrem Punkt standen.

Diese Datei ersetzt `test_geraete_vergleich_browser.py` (Anbieterfilter des
alten Preisvergleichs) und `test_geraete_hoehe_browser.py` (Hoehe der
geloeschten Grafik). Beide massen Bedienelemente, die es nicht mehr gibt.

Dieselbe Bauform wie `tests/test_falz_browser.py`: eigener Server auf
127.0.0.1 (kein file://, kein Netz), Chromium an beiden bekannten Orten
gesucht, ein Browserstart je Testlauf.
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import json
import re
import socket
import threading
from pathlib import Path

import pytest
import yaml

from telco_radar.report.html import render_site

REPO = Path(__file__).resolve().parents[1]

# Zwanzig Geraete, nicht zwei. Die erste Fassung hatte zwei - damit greift
# `SICHTBAR_MAX` (15) nie, "alle anzeigen" steht nicht auf der Seite, und der
# Test dafuer uebersprang sich selbst. Ein Skip sieht im Protokoll aus wie ein
# Erfolg (CLAUDE.md 6).
#
# Zwei Hersteller im Wechsel, damit der Markenfilter wirklich trennt, und je
# Geraet ein guenstigerer Wettbewerber, damit jede Zeile in die Alarmtabelle
# kommt.
_MODELLE = [(f"iPhone 1{n}" if n % 2 else f"Galaxy S2{n}",
             "Apple" if n % 2 else "Samsung") for n in range(20)]

_KATALOG = {"geraete": [
    {"hersteller": marke, "modell": modell, "generation": 20 + i,
     "speicher": [256], "segment": "flagship"}
    for i, (modell, marke) in enumerate(_MODELLE)
]}
_FARBEN = {"farben": {"titan-natur": ["Titannatur"], "schwarz": ["Schwarz"]}}
_QUELLEN = {"anbieter": [
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 1, "eigen": True,
     "methode": "ldjson", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://www.vodafone.de/handys"}]},
    {"name": "o2", "typ": "netzbetreiber", "rang": 2, "methode": "ldjson",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/handys"}]},
    {"name": "Medimax", "typ": "handel", "rang": 3, "methode": "ldjson",
     "basis_url": "https://www.medimax.de",
     "einstiege": [{"url": "https://www.medimax.de/c/116"}]},
]}


def _kennung(modell: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", modell.lower()).strip("-")


def _listung(anbieter, typ, sku, preis, gid, speicher=256):
    return {
        "id": f"{anbieter.lower()}--{sku}", "sku_id": sku, "device_id": gid,
        "anbieter": anbieter, "anbieter_typ": typ, "netz": "",
        "speicher_gb": speicher, "farbe_roh": "Titannatur",
        "farbe_normalisiert": "titan-natur", "zustand": "neu",
        "first_seen": "2026-08-01", "last_verified": "2026-08-11",
        "status": "aktiv", "missed_checks": 0, "preis_ohne_vertrag": preis,
        "erstpreis": preis, "erstpreis_art": "ohne_vertrag",
        "erstpreis_am": "2026-08-01",
        "quelle_url": f"https://example.de/p/{sku}",
        "abgerufen_am": "2026-08-11", "verfuegbarkeit": "lieferbar",
        "confidence": "hoch", "einstiege": ["https://example.de/liste"],
    }


def _bestand():
    """Je Geraet unser Preis und ein guenstigerer Wettbewerber.

    Der Abstand waechst mit dem Index, damit die vier Alarmstufen alle
    besetzt sind - eine Fixture, in der nur "kritisch" vorkommt, laesst drei
    Kacheln ungeprueft.
    """
    zeilen = []
    for i, (modell, _marke) in enumerate(_MODELLE):
        gid = f"{'apple' if i % 2 else 'samsung'}-{_kennung(modell)}"
        eigen = 1000.0 + i
        # 0,5 % bis 20 % Abstand, im Wechsel Netzbetreiber und Fachhandel.
        fremd = round(eigen * (1 - (0.005 + i * 0.011)), 2)
        zeilen.append(_listung("Vodafone", "netzbetreiber", f"vf-{i}", eigen, gid))
        wer, typ = ("o2", "netzbetreiber") if i % 2 else ("Medimax", "handel")
        zeilen.append(_listung(wer, typ, f"{wer.lower()}-{i}", fremd, gid))
    return zeilen


_DB = {"updated": "2026-08-11", "anbieter": {
    "Vodafone": {"laeufe": 4, "funde_gesamt": 20},
    "o2": {"laeufe": 4, "funde_gesamt": 10},
    "Medimax": {"laeufe": 4, "funde_gesamt": 10},
}, "listungen": _bestand()}


def _chromium():
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@contextlib.contextmanager
def _server(site: Path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(site))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


# Die Grenze aus dem Auftrag: jeder Reiter bleibt unter drei Bildschirmen.
MAX_HOEHE = 3000

# Keine Beschriftung unter dieser Groesse. Die alte Grafik hatte 236 Texte
# darunter, auf einem 390-px-Telefon real 2,7 CSS-Pixel.
MIN_SCHRIFT = 12


@pytest.fixture(scope="module")
def _seite(tmp_path_factory):
    """Ein Browser, eine Seite - die Tests lesen daraus."""
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright

    root = tmp_path_factory.mktemp("reiter")
    (root / "config").mkdir()
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps(_DB), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    site = root / "site"
    render_site(site, reports, cfg=None)

    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        seite = browser.new_page(viewport={"width": 1440, "height": 900})
        seite.goto(f"{basis}/geraete.html", wait_until="load")
        yield seite
        browser.close()


def _sichtbare_zeilen(seite):
    """Was der Leser WIRKLICH sieht, nicht was das Attribut sagt.

    Die erste Fassung zaehlte `:not([hidden])`. Damit war sie blind fuer den
    Fehler, den sie haette finden sollen: eine Autorenregel schlaegt das
    `[hidden]{display:none}` des Browsers, und nach "alle anzeigen" standen
    weggefilterte Zeilen weiter in der Tabelle - Helfer sagte 10, der
    Browser zeigte 13.
    """
    return seite.eval_on_selector_all(
        "#tafel-alarme .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none').length")


def _sichtbare_marken(seite):
    return seite.eval_on_selector_all(
        "#tafel-alarme .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none')"
        "      .map(x => x.dataset.marke)")


# --------------------------------------------------------------------------
# Die drei Regeln, die ueber allem stehen
# --------------------------------------------------------------------------

def test_die_startansicht_traegt_kein_diagramm(_seite):
    """Regel 2 des Auftrags: die Uebersicht ueber alle Geraete ist eine
    TABELLE. Auf der Startansicht steht ueberhaupt kein Diagramm."""
    tafel = _seite.eval_on_selector(
        "#tafel-alarme", "e => e.querySelectorAll('svg').length")
    assert tafel == 0
    # ZWEI Tabellen tragen diese Klasse: die Alarme in Reiter 1 und der
    # flache Katalog in Reiter 2. Sie teilen sich Aussehen und Filterlogik
    # bewusst - eine zweite Kopie waere eine zweite Stelle, an der die
    # Kaskadenfalle mit `hidden` repariert werden muesste.
    assert _seite.eval_on_selector_all("#tafel-alarme .gr-alarm",
                                       "e => e.length") == 1


def test_kein_gedrehter_text_auf_der_ganzen_seite(_seite):
    """Regel aus Abschnitt 0. Die alte Grafik hatte 114 senkrecht gedrehte
    Achsenbeschriftungen - gemessen im gerenderten Dokument, nicht im
    Quelltext."""
    gedreht = _seite.evaluate("""() => Array.from(
        document.querySelectorAll('svg text, text, .gr-tafel *')).filter(el => {
          const t = (el.getAttribute && el.getAttribute('transform')) || '';
          const c = getComputedStyle(el).transform;
          return /rotate/.test(t) || /matrix\\(-?0?\\.|rotate/.test(c);
        }).length""")
    assert gedreht == 0


@pytest.mark.parametrize("tid", ["tafel-alarme"])
def test_keine_beschriftung_unter_zwoelf_pixeln(_seite, tid):
    """Passt ein Name nicht hin, ist die Ansicht zu voll - dann fallen
    Eintraege, nicht Buchstaben.

    Gemessen wird vorerst nur Reiter 1. Reiter 2 und 3 tragen bis B5/B6 noch
    die verschobenen Alt-Abschnitte, und deren Etiketten (`rubrik-zahl` und
    die Tabellenschrift der SKU-Matrix) sind seiteneigene Typografie - die
    darf dieser Umbau nicht anfassen, derselbe Auftrag verlangt sie
    unveraendert. Wer B5 oder B6 baut, traegt seinen Reiter hier ein; genau
    dafuer steht die Liste als Parameter da.
    """
    _seite.click(f".gr-reiter button[data-tafel='{tid}']")
    _seite.wait_for_timeout(60)
    zu_klein = _seite.evaluate(f"""() => Array.from(
        document.querySelectorAll('#{tid} *')).filter(el =>
          el.textContent.trim()
          && el.children.length === 0
          && parseFloat(getComputedStyle(el).fontSize) < {MIN_SCHRIFT}
        ).map(el => el.className + ': ' + el.textContent.trim().slice(0, 30))""")
    assert zu_klein == []


def test_keine_beschriftung_wird_mit_punkten_abgeschnitten(_seite):
    """`text-overflow: ellipsis` schneidet Text ab, ohne dass es im HTML zu
    sehen ist - und der alte `_kurz()` tat dasselbe im Python."""
    gekuerzt = _seite.evaluate("""() => Array.from(
        document.querySelectorAll('.gr-tafel *')).filter(el =>
          getComputedStyle(el).textOverflow === 'ellipsis'
          && el.scrollWidth > el.clientWidth + 1
        ).length""")
    assert gekuerzt == 0
    assert "…" not in _seite.eval_on_selector("#tafel-alarme", "e => e.innerText")


# --------------------------------------------------------------------------
# Die Reiter
# --------------------------------------------------------------------------

def test_der_reiter_blendet_ohne_neuladen_um(_seite):
    for tid in ("tafel-katalog", "tafel-portfolio", "tafel-alarme"):
        _seite.click(f".gr-reiter button[data-tafel='{tid}']")
        _seite.wait_for_timeout(60)
        sichtbar = _seite.eval_on_selector_all(
            ".gr-tafel:not(.gr-tafel--aus)", "e => e.map(x => x.id)")
        assert sichtbar == [tid], tid
        aktiv = _seite.eval_on_selector_all(
            ".gr-reiter button[aria-selected='true']",
            "e => e.map(x => x.getAttribute('data-tafel'))")
        assert aktiv == [tid], "genau ein Reiter ist ausgewaehlt"


@pytest.mark.parametrize("tid", ["tafel-alarme", "tafel-katalog",
                                 "tafel-portfolio"])
def test_jeder_reiter_bleibt_unter_drei_bildschirmen(_seite, tid):
    """Der Auftrag: unter 3.000 px auf 1440 px Breite. Die alte Seite war
    18.412 px hoch."""
    _seite.click(f".gr-reiter button[data-tafel='{tid}']")
    _seite.wait_for_timeout(60)
    hoehe = _seite.evaluate("document.documentElement.scrollHeight")
    assert hoehe < MAX_HOEHE, f"{tid}: {hoehe} px"


# --------------------------------------------------------------------------
# Filter, Suche, Aufklapper
# --------------------------------------------------------------------------

def _frisch(seite):
    """Ein unberuehrter Ausgangszustand.

    Die Fixture hat Modulgueltigkeit, und "alle anzeigen" ist eine Klasse an
    der Tabelle, die kein Filter zuruecknimmt. Ein Test, der danach laeuft,
    misst sonst eine Seite, die ein anderer aufgeklappt hat.
    """
    seite.reload(wait_until="load")
    seite.click(".gr-reiter button[data-tafel='tafel-alarme']")
    seite.wait_for_timeout(60)


def test_ohne_filter_greift_der_zeilendeckel(_seite):
    """`SICHTBAR_MAX` deckelt die Seitenhoehe STRUKTURELL. Ohne den Deckel
    haengt sie am Datenbestand, und zwei zusaetzliche Zeilen kippen den
    Abnahmetest, ohne dass sich eine Zeile Code aendert.

    Die Zahl wird aus dem Modul gelesen, nicht abgeschrieben: sie ist am
    30.08.2026 von 15 auf 12 gefallen, weil der Reiter mit 15 Zeilen 3154 px
    mass und damit die andere Vorgabe desselben Auftrags riss. Ein Test, der
    die 15 festhaelt, haette die Korrektur als Fehler gemeldet.
    """
    from telco_radar.report.geraete_alarme import SICHTBAR_MAX
    _frisch(_seite)
    gesamt = _seite.eval_on_selector_all("#tafel-alarme .gr-a-zeile", "e => e.length")
    assert gesamt > SICHTBAR_MAX, "die Fixture reisst den Deckel nicht"
    assert _sichtbare_zeilen(_seite) == SICHTBAR_MAX
    assert _seite.query_selector("#gr-mehr") is not None


def test_der_markenfilter_laesst_nur_die_passende_zeile(_seite):
    """Zwei Geraete, zwei Hersteller - so trennt der Filter wirklich. Ein
    Fixture, in dem beide Marken ueberall vorkommen, koennte gruen sein,
    ohne dass der Filter etwas tut."""
    _frisch(_seite)
    _seite.select_option("[data-filter='marke']", "Samsung")
    _seite.wait_for_timeout(60)
    marken = _sichtbare_marken(_seite)
    assert marken, "keine Zeile sichtbar - der Test misst nichts"
    assert set(marken) == {"Samsung"}, marken
    # Gegenprobe: ohne Filter sind BEIDE Marken da, sonst traefe der Filter
    # eine Fixture, die ohnehin nur Samsung kennt.
    _seite.select_option("[data-filter='marke']", "")
    _seite.wait_for_timeout(60)
    assert set(_sichtbare_marken(_seite)) == {"Apple", "Samsung"}


def test_ein_aktiver_filter_ist_rot_hinterlegt(_seite):
    """"Aktive Filter werden rot hinterlegt mit weisser Schrift." Sie
    veraendern, was darunter steht, und das muss man sehen, ohne die Auswahl
    zu lesen."""
    # Der eigene Ausgangszustand. Die erste Fassung verliess sich darauf,
    # dass der Test davor "Samsung" gewaehlt hatte - einzeln ausgefuehrt fiel
    # sie durch, und zwei Tests weiter unten steht der Kommentar, warum man
    # das nicht tut.
    _frisch(_seite)
    _seite.select_option("[data-filter='marke']", "Samsung")
    _seite.wait_for_timeout(60)
    an = _seite.eval_on_selector(
        "[data-filter='marke']",
        "e => e.closest('label').classList.contains('gr-filter--an')")
    assert an is True
    farbe = _seite.eval_on_selector(
        "[data-filter='marke']",
        "e => getComputedStyle(e.closest('label')).backgroundColor")
    assert farbe == "rgb(230, 0, 0)", farbe


def test_die_suche_grenzt_ein(_seite):
    _frisch(_seite)
    vorher = _sichtbare_zeilen(_seite)
    _seite.fill("[data-filter='suche']", "medimax")
    _seite.wait_for_timeout(60)
    nachher = _sichtbare_zeilen(_seite)
    assert 0 < nachher < vorher, (vorher, nachher)
    treffer = _seite.eval_on_selector_all(
        "#tafel-alarme .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none')"
        "      .map(x => x.textContent.toLowerCase().includes('medimax'))")
    assert all(treffer), "eine Zeile ohne den Suchbegriff ist sichtbar"


def test_eine_leere_auswahl_zeigt_einen_satz_statt_einer_leeren_flaeche(_seite):
    """Der Befund vom 29.08.2026, im Browser gesehen und nicht im HTML: eine
    leere Tabelle ohne Erklaerung liest sich als kaputte Seite."""
    _seite.fill("[data-filter='suche']", "gibtesnicht")
    _seite.wait_for_timeout(60)
    assert _sichtbare_zeilen(_seite) == 0
    assert _seite.eval_on_selector("#tafel-alarme .gr-a-leer", "e => !e.hidden") is True
    _seite.fill("[data-filter='suche']", "")


def test_der_klick_auf_eine_zeile_zeigt_alle_anbieter(_seite):
    """Ohne Klick steht die Anbieterliste NICHT da - sonst waere die Tabelle
    dreimal so hoch."""
    # Der eigene Ausgangszustand, nicht der des vorigen Tests: ein Test, der
    # auf dem Aufraeumen eines anderen sitzt, faellt aus, sobald der andere
    # ausfaellt - und meldet dann etwas, das mit ihm nichts zu tun hat.
    _frisch(_seite)
    zeile = "#tafel-alarme .gr-a-zeile:not([hidden])"
    aufklapper = _seite.eval_on_selector(zeile, "e => '#' + e.dataset.auf")
    assert _seite.eval_on_selector(aufklapper, "e => e.offsetParent") is None
    _seite.click(f"{zeile} .gr-a-modell")
    _seite.wait_for_timeout(60)
    assert _seite.eval_on_selector(aufklapper, "e => e.offsetParent") is not None
    eintraege = _seite.eval_on_selector_all(
        f"{aufklapper} .gr-a-liste li", "e => e.length")
    assert eintraege >= 2, "der Aufklapper zeigt unseren Preis und den fremden"


# --------------------------------------------------------------------------
# "Alle anzeigen" - und was danach passiert
# --------------------------------------------------------------------------

def test_der_filter_wirkt_auch_nach_alle_anzeigen(_seite):
    """Der teuerste Befund des B2-Reviews, und kein statischer Test konnte ihn
    sehen.

    `.gr-alarm--alle .gr-a-rest` ist eine AUTORENregel und schlaegt das
    `[hidden]{display:none}` des Browsers - Ursprung geht vor Spezifitaet.
    Aufgeklappt auf 20 Zeilen und auf Samsung gefiltert standen drei
    Apple-Zeilen mitten in der Tabelle, waehrend das `hidden`-Attribut
    korrekt sass.
    """
    _frisch(_seite)
    mehr = _seite.query_selector("#gr-mehr")
    if mehr is not None:
        mehr.click()
        _seite.wait_for_timeout(60)

    _seite.select_option("[data-filter='marke']", "Samsung")
    _seite.wait_for_timeout(60)
    marken = _sichtbare_marken(_seite)
    assert marken, "keine Zeile sichtbar - der Test misst nichts"
    assert set(marken) == {"Samsung"}, marken


def test_ein_aufklapper_verschwindet_mit_seiner_zeile(_seite):
    """Sonst haengt eine Anbieterliste unter einer Zeile, die nicht mehr da
    ist - dieselbe Kaskadenfalle wie eine Ebene darueber."""
    _seite.click(".gr-reiter button[data-tafel='tafel-alarme']")
    _seite.select_option("[data-filter='marke']", "")
    _seite.fill("[data-filter='suche']", "")
    _frisch(_seite)
    zeile = "#tafel-alarme .gr-a-zeile:not([hidden])"
    aufklapper = _seite.eval_on_selector(zeile, "e => '#' + e.dataset.auf")
    # Der Klick TOGGELT. Die Fixture hat Modulgueltigkeit, ein Test davor kann
    # denselben Aufklapper schon geoeffnet haben - dann klappt ein blinder
    # Klick ihn zu, und der Test misst das Gegenteil dessen, was er behauptet.
    if _seite.eval_on_selector(aufklapper,
                               "e => getComputedStyle(e).display") == "none":
        _seite.click(f"{zeile} .gr-a-modell")
        _seite.wait_for_timeout(60)
    # Gegenprobe: er ist wirklich offen, sonst misst der Test nichts.
    assert _seite.eval_on_selector(
        aufklapper, "e => getComputedStyle(e).display") != "none"

    _seite.fill("[data-filter='suche']", "gibtesnichtwirklich")
    _seite.wait_for_timeout(60)
    assert _seite.eval_on_selector(
        aufklapper, "e => getComputedStyle(e).display") == "none"
    _seite.fill("[data-filter='suche']", "")


def test_eine_leere_auswahl_ueber_versteckte_zeilen_zeigt_den_satz(_seite):
    """Trifft die Suche NUR eine Zeile, die hinter "alle anzeigen" steckt,
    sieht der Leser eine Tabellenkopfzeile mit nichts darunter. Gezaehlt
    werden muss, was wirklich dasteht - nicht, was zum Filter passt."""
    _frisch(_seite)
    rest = _seite.eval_on_selector_all(
        "#tafel-alarme .gr-a-rest.gr-a-zeile", "e => e.length")
    assert rest, "die Fixture hat keine Zeilen hinter 'alle anzeigen'"
    suchwort = _seite.eval_on_selector(
        "#tafel-alarme .gr-a-rest.gr-a-zeile .gr-a-modell",
        "e => e.textContent.trim()")
    _seite.fill("[data-filter='suche']", suchwort)
    _seite.wait_for_timeout(60)
    assert _sichtbare_zeilen(_seite) == 0
    assert _seite.eval_on_selector(
        "#tafel-alarme .gr-a-leer", "e => getComputedStyle(e).display") != "none"
    _seite.fill("[data-filter='suche']", "")


def test_kein_aufklapper_steht_offen(_seite):
    """Die Kuerze der Seite haengt daran, dass die `<details>` ZU sind. Ein
    versehentliches `open` macht sie wieder zwanzig Bildschirme lang, ohne
    dass sich eine Zeile Inhalt aendert - CLAUDE.md nennt diesen Waechter
    namentlich.

    Er ist beim Umbau am 30.08.2026 mit `test_geraete_hoehe_browser.py`
    verlorengegangen, weil diese Datei ausserdem die geloeschte Grafik
    vermass. Die Hoehenmessung allein ersetzt ihn nicht: sie laeuft auf einer
    Fixture, in der ein offenes `<details>` fast nichts kostet.
    """
    _frisch(_seite)
    for tid in ("tafel-alarme", "tafel-katalog", "tafel-portfolio"):
        _seite.click(f".gr-reiter button[data-tafel='{tid}']")
        _seite.wait_for_timeout(60)
        offen = _seite.eval_on_selector_all(
            f"#{tid} details[open]", "e => e.length")
        assert offen == 0, tid


def test_die_seite_traegt_das_echte_abrufdatum(_seite):
    """Faellt der naechtliche Lauf zwei Wochen aus, sind die Preise zwei
    Wochen alt - die Seite darf trotzdem nicht den Berichtstag behaupten.
    Auf einer Seite, deren Verkaufsargument der Belegzwang ist, ist das die
    teuerste Sorte falscher Zahl.

    Die Zusicherung stand als Kommentar in `geraete_view`, ihr Test hing an
    der Legende der geloeschten Grafik - und war damit vom 30.08.2026 an
    unbelegt.
    """
    _frisch(_seite)
    text = _seite.eval_on_selector("body", "e => e.innerText")
    assert "11. August 2026" in text, "das Abrufdatum der Listungen fehlt"
