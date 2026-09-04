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
import shutil
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


# SECHS Tage, nicht vier. Mit genau `DIAGRAMM_AB_TERMINEN` Messtagen faellt
# JEDE Verengung des Zeitraums unters Gatter - und damit war
# `test_die_tabelle_zeigt_dieselben_anbieter_wie_das_diagramm` nicht mehr
# formulierbar: es gab keine Lage mehr, in der ein Anbieter aus einem
# VERENGTEN, aber noch gezeichneten Fenster faellt. Mit sechs Tagen bleibt
# nach der Verengung auf vier ein Diagramm stehen, und die alte
# Gleichheitspruefung greift wieder.
#
# Der 03. und der 04.08. liegen bewusst in DERSELBEN Kalenderwoche: daran
# haengt der Test, dass der Rasterschalter die Zahl der Messtermine nicht
# veraendert.
_MESSTAGE = ("2026-08-03", "2026-08-04", "2026-08-11", "2026-08-18",
             "2026-08-25", "2026-08-28")


# Medimax wird NUR an den ersten zwei Tagen gesehen.
#
# Ohne diese Ungleichheit hat jede Listung dieselben sechs Messtage, und dann
# faellt beim Verengen des Zeitraums NIE ein Anbieter aus dem Bild - die
# Zusicherung "Legende und Tabelle nennen dieselben Anbieter" ist damit nicht
# ausloesbar, und `test_die_tabelle_zeigt_dieselben_anbieter_wie_das_diagramm`
# war gruen, auch wenn die Tabelle wieder ueber den vollen Zeitraum rechnete
# (nachgeprueft: der eingebaute alte Fehler blieb unentdeckt). Ein Anbieter,
# der frueh verschwindet, ist ausserdem der Normalfall dieses Radars -
# mobilcom-debitel hoerte am 21.08. auf zu liefern.
_NUR_FRUEH = "Medimax"


def _listung(anbieter, typ, sku, preis, gid, speicher=256):
    return {
        "id": f"{anbieter.lower()}--{sku}", "sku_id": sku, "device_id": gid,
        "anbieter": anbieter, "anbieter_typ": typ, "netz": "",
        "speicher_gb": speicher, "farbe_roh": "Titannatur",
        "farbe_normalisiert": "titan-natur", "zustand": "neu",
        # `last_verified` MUSS zum letzten Messtag des Anbieters passen:
        # `geraete_verlauf._punkte` haengt daran den Bestaetigungstag an und
        # verlaengert die Kurve bis dorthin. Mit einem festen 11.08. fuer
        # alle bekam Medimax trotz seiner zwei Messtage einen dritten Punkt
        # mitten im verengten Fenster - und fiel deshalb nie heraus.
        "first_seen": "2026-08-01",
        "last_verified": (_MESSTAGE[1] if anbieter == _NUR_FRUEH
                          else _MESSTAGE[-1]),
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


# Der TCO-Bestand der Fixture.
#
# Bis zum 04.09.2026 gab es ihn nicht, und das machte den Reiter "Was kostet
# es" zur halb ungeprueften Seite: ohne `geraete_tco.json` startet `TcoDB`
# leer, `referenzen()` und `buendel()` geben `[]`, und damit rendern ZWEI der
# drei Tabellen dieses Reiters ueberhaupt nicht - die SIM-only-Referenzen
# (Makro, zweimal aufgerufen) und die Leitzahl-Tabelle. Der Breitentest
# darunter wurde allein von der dritten rot, und die Behaelter der zwei
# anderen waren von keinem Test der Suite gedeckt.
#
# 14 Referenzen, weil `REFERENZEN_SICHTBAR` bei 12 deckelt: so entsteht auch
# der Aufklapper "Die uebrigen N Tarife" und mit ihm der ZWEITE Aufruf des
# Makros. Vier Buendel mit Tarifgrundpreis UND Geraeterate, damit
# `tco_24()` belastbar rechnet und die Leitzahl-Tabelle Zeilen bekommt -
# der Zustand, den Phase 4 herstellen wird.
_TCO_REFERENZEN = [
    {"id": f"simonly--{a.lower()}--tarif-{i}", "anbieter": a,
     "tarif_name": f"{a} Tarif {i}", "tarif_id": f"{a.lower()}:tarif-{i}",
     "tarif_id_guete": "hoch", "tarif_sim_only_monatlich": 19.99 + i,
     "anschlusspreis": None, "rabatte": [],
     "quelle_url": f"https://example.de/pib/{a.lower()}-{i}",
     "abgerufen_am": "2026-09-04", "first_seen": "2026-09-04",
     "last_verified": "2026-09-04"}
    for i, a in enumerate(["Vodafone", "o2"] * 7)
]

_TCO_BUENDEL = [
    {"id": f"buendel--{sku}", "sku_id": sku, "anbieter": anb,
     "tarif_name": f"{anb} Tarif {i}", "tarif_id": f"{anb.lower()}:tarif-{i}",
     "tarif_id_guete": "hoch", "tarif_monatlich": 19.99 + i,
     "geraet_zuzahlung": 1.0, "geraet_monatsrate": 20.0 + i,
     "laufzeit_monate": 24, "anschlusspreis": None, "rabatte": [],
     "quelle_url": f"https://example.de/p/{sku}",
     "abgerufen_am": "2026-09-04", "first_seen": "2026-09-04",
     "last_verified": "2026-09-04"}
    for i, (anb, sku) in enumerate(
        [("Vodafone", "vf-0"), ("o2", "o2-1"),
         ("Vodafone", "vf-2"), ("o2", "o2-3")])
]

_TCO = {"updated": "2026-09-04", "buendel": _TCO_BUENDEL,
        "sim_only": _TCO_REFERENZEN}


def _historie():
    zeilen = []
    for e in _DB["listungen"]:
        tage = _MESSTAGE[:2] if e["anbieter"] == _NUR_FRUEH else _MESSTAGE
        for i, tag in enumerate(tage):
            zeilen.append({
                "listung_id": e["id"], "device_id": e["device_id"],
                "anbieter": e["anbieter"], "datum": tag,
                # Ein leicht fallender Preis: eine echte Bewegung, damit die
                # Spalte "Veraenderung" etwas zu sagen hat.
                "preis_ohne_vertrag": round(e["preis_ohne_vertrag"] + (3 - i) * 5.0, 2),
                "verfuegbarkeit": "lieferbar", "quelle_url": e["quelle_url"]})
    return zeilen


# Vier Messtage je Listung (30.08.2026).
#
# Bis dahin lief diese Fixture mit einer LEEREN Preishistorie: jede Listung
# hatte genau einen Messtag, den aus `last_verified`. Das reichte, solange
# jedes gewaehlte Geraet ein Diagramm bekam - seit ein Verlauf erst ab
# `DIAGRAMM_AB_TERMINEN` Messterminen gezeichnet wird (zwei Punkte sind eine
# Gerade, und eine Gerade durch zwei Punkte sieht aus wie ein Trend), stand
# hier kein SVG mehr, und vier Tests massen einen Leerzustand statt der
# Grafik, die sie pruefen sollen.
#
# Die Tage liegen bewusst in DREI Kalenderwochen: der 03. und der 04.08.
# fallen in dieselbe: daran laesst sich zeigen, dass der Rasterschalter die
# Zahl der MESSTERMINE nicht veraendert.


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
def _umgebung(_seite):
    """Browser und Basisadresse, fuer Tests mit einer EIGENEN Seite.

    Zwei Tests stellen ihre Daten selbst (eine verdeckte Linie, eine
    Achse mit winziger Spanne) - im echten Bestand gibt es beide Faelle
    heute nicht. Sie ersetzen dafuer den JSON-Block und laden neu, und das
    darf die gemeinsame Seite nicht anfassen: sie hat Modulgueltigkeit, und
    ein Test, der danach laeuft, saehe sonst gestellte Daten. Genau das ist
    beim Bauen einmal passiert - `test_die_achse_erfindet_keinen_preis` fiel
    aus, weil ein Test vor ihm die Seite ueberschrieben hatte.
    """
    return _seite.context.browser, _seite.url


@pytest.fixture
def _eigene_seite(_umgebung):
    """Eine frische Seite je Test, aus demselben Browser."""
    browser, url = _umgebung
    seite = browser.new_page(viewport={"width": 1440, "height": 900})
    seite.goto(url, wait_until="load")
    try:
        yield seite
    finally:
        seite.close()


def _stelle_daten(seite, geraet):
    """Den Verlaufsblock ersetzen und `app.js` frisch darauf laufen lassen.

    `app.js` liest den Block beim Laden, deshalb wird der geaenderte Baum als
    Inhalt neu gesetzt. Das geht NUR auf einer eigenen Seite - auf der
    gemeinsamen bliebe der gestellte Stand fuer alle folgenden Tests stehen.
    """
    seite.evaluate(
        "(g) => { document.getElementById('gr-verlaufdaten').textContent ="
        "           JSON.stringify([g]); }", geraet)
    seite.set_content(seite.evaluate("document.documentElement.outerHTML"))
    seite.wait_for_timeout(150)
    seite.click(".gr-reiter button[data-tafel='tafel-verlauf']")
    seite.fill("#gr-vsuche", geraet["label"].split()[0][:8])
    seite.wait_for_timeout(150)
    seite.click(".gr-vtreffer-zeile")
    seite.wait_for_timeout(250)


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
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps(z) for z in _historie()) + "\n", encoding="utf-8")
    (state / "geraete_tco.json").write_text(json.dumps(_TCO), encoding="utf-8")
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
    for tid in ("tafel-katalog", "tafel-tco", "tafel-verlauf",
                "tafel-portfolio", "tafel-alarme"):
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
                                 "tafel-verlauf", "tafel-portfolio",
                                 "tafel-tco"])
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
    _seite.select_option("#tafel-alarme [data-filter='marke']", "Samsung")
    _seite.wait_for_timeout(60)
    marken = _sichtbare_marken(_seite)
    assert marken, "keine Zeile sichtbar - der Test misst nichts"
    assert set(marken) == {"Samsung"}, marken
    # Gegenprobe: ohne Filter sind BEIDE Marken da, sonst traefe der Filter
    # eine Fixture, die ohnehin nur Samsung kennt.
    _seite.select_option("#tafel-alarme [data-filter='marke']", "")
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
    _seite.select_option("#tafel-alarme [data-filter='marke']", "Samsung")
    _seite.wait_for_timeout(60)
    an = _seite.eval_on_selector(
        "#tafel-alarme [data-filter='marke']",
        "e => e.closest('label').classList.contains('gr-filter--an')")
    assert an is True
    farbe = _seite.eval_on_selector(
        "#tafel-alarme [data-filter='marke']",
        "e => getComputedStyle(e.closest('label')).backgroundColor")
    assert farbe == "rgb(230, 0, 0)", farbe


def test_die_suche_grenzt_ein(_seite):
    _frisch(_seite)
    vorher = _sichtbare_zeilen(_seite)
    _seite.fill("#tafel-alarme [data-filter='suche']", "medimax")
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
    _seite.fill("#tafel-alarme [data-filter='suche']", "gibtesnicht")
    _seite.wait_for_timeout(60)
    assert _sichtbare_zeilen(_seite) == 0
    assert _seite.eval_on_selector("#tafel-alarme .gr-a-leer", "e => !e.hidden") is True
    _seite.fill("#tafel-alarme [data-filter='suche']", "")


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

    _seite.select_option("#tafel-alarme [data-filter='marke']", "Samsung")
    _seite.wait_for_timeout(60)
    marken = _sichtbare_marken(_seite)
    assert marken, "keine Zeile sichtbar - der Test misst nichts"
    assert set(marken) == {"Samsung"}, marken


def test_ein_aufklapper_verschwindet_mit_seiner_zeile(_seite):
    """Sonst haengt eine Anbieterliste unter einer Zeile, die nicht mehr da
    ist - dieselbe Kaskadenfalle wie eine Ebene darueber."""
    _seite.click(".gr-reiter button[data-tafel='tafel-alarme']")
    _seite.select_option("#tafel-alarme [data-filter='marke']", "")
    _seite.fill("#tafel-alarme [data-filter='suche']", "")
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

    _seite.fill("#tafel-alarme [data-filter='suche']", "gibtesnichtwirklich")
    _seite.wait_for_timeout(60)
    assert _seite.eval_on_selector(
        aufklapper, "e => getComputedStyle(e).display") == "none"
    _seite.fill("#tafel-alarme [data-filter='suche']", "")


def test_eine_suche_ueber_eine_zunaechst_versteckte_zeile_zeigt_sie(_seite):
    """UMGEDREHT durch die B2-Nachbesserung vom 31.08.2026, mit Begruendung.

    Bis dahin blieb eine Zeile hinter "alle anzeigen" (`gr-a-rest`) auch
    dann versteckt, wenn die Suche sie als EINZIGEN Treffer fand - der
    Leser sah "kein Treffer" fuer eine Zeile, die wirklich im Bestand
    steht. Exakt derselbe Fehlertyp wie B2 (der Deckel haengt an der
    POSITION, nicht am Filter): zwei Klicks auf einen Spaltenkopf liessen
    dort 348 passende Zeilen hinter dem Deckel verschwinden, hier laesst
    eine einzige Suche eine passende Zeile verschwinden - dieselbe Ursache,
    zwei Ausloeser.

    Seit dem Fix zaehlt `anwenden()` nur unter den TREFFERN: ein einzelner
    Treffer liegt IMMER unter dem Deckel (1 <= irgendein Deckel > 0) und
    wird deshalb gezeigt, unabhaengig davon, ob er vor der Suche als
    `gr-a-rest` markiert war. Die alte Fassung dieses Tests verlangte das
    Gegenteil - eine Suche mit genau einem Treffer, die "kein Treffer"
    zeigt - und hielt damit den Fehler fest, den B2 behebt.
    """
    _frisch(_seite)
    rest = _seite.eval_on_selector_all(
        "#tafel-alarme .gr-a-rest.gr-a-zeile", "e => e.length")
    assert rest, "die Fixture hat keine Zeilen hinter 'alle anzeigen'"
    suchwort = _seite.eval_on_selector(
        "#tafel-alarme .gr-a-rest.gr-a-zeile .gr-a-modell",
        "e => e.textContent.trim()")
    _seite.fill("#tafel-alarme [data-filter='suche']", suchwort)
    _seite.wait_for_timeout(60)
    assert _sichtbare_zeilen(_seite) == 1, (
        "der einzige Treffer der Suche bleibt versteckt")
    assert _seite.eval_on_selector(
        "#tafel-alarme .gr-a-leer", "e => getComputedStyle(e).display") == "none"
    gefundenes_modell = _seite.eval_on_selector(
        "#tafel-alarme .gr-a-zeile:not([hidden]) .gr-a-modell",
        "e => e.textContent.trim()")
    assert gefundenes_modell == suchwort, (
        "die sichtbare Zeile ist nicht die gesuchte")
    _seite.fill("#tafel-alarme [data-filter='suche']", "")


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
    for tid in ("tafel-alarme", "tafel-tco", "tafel-katalog",
                "tafel-verlauf", "tafel-portfolio"):
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


# --------------------------------------------------------------------------
# Reiter 3: das einzige Diagramm der Seite
#
# Diese Tests sind am 30.08.2026 nachgetragen worden, nachdem der Review
# festgestellt hat, dass KEIN Test je in `#gr-vsuche` tippt: der ganze
# Reiter war ungeprueft, waehrend seine Modul-Docstring das Gegenteil
# behauptete. Die drei harten Regeln des Auftrags leben in `app.js` und sind
# nur im Browser sichtbar - CLAUDE.md §6: "Eine Grafik ist erst fertig, wenn
# sie jemand ANGESEHEN hat."
# --------------------------------------------------------------------------

def _waehle_geraet(seite, begriff="galaxy"):
    """Ein Geraet im Suchfeld auswaehlen. Gibt False, wenn die Fixture keins
    hergibt - dann darf der Aufrufer nicht schweigend durchlaufen."""
    seite.click(".gr-reiter button[data-tafel='tafel-verlauf']")
    seite.wait_for_timeout(80)
    if seite.query_selector("#gr-vsuche") is None:
        return False
    seite.fill("#gr-vsuche", begriff)
    seite.wait_for_timeout(150)
    if not seite.eval_on_selector_all(".gr-vtreffer-zeile", "e => e.length"):
        return False
    seite.click(".gr-vtreffer-zeile")
    seite.wait_for_timeout(250)
    return True


def test_ohne_auswahl_steht_kein_diagramm_da(_seite):
    """"Solange kein Gerät gewählt ist, steht hier KEIN Diagramm. Auch kein
    leeres." Ein leerer Rahmen sieht aus, als seien die Daten weg."""
    _frisch(_seite)
    _seite.click(".gr-reiter button[data-tafel='tafel-verlauf']")
    _seite.wait_for_timeout(80)
    assert _seite.eval_on_selector_all("#tafel-verlauf svg", "e => e.length") == 0
    assert _seite.eval_on_selector(
        "#gr-vleer", "e => getComputedStyle(e).display") != "none"


def test_nach_der_auswahl_steht_genau_ein_diagramm_fuer_ein_geraet(_seite):
    _frisch(_seite)
    assert _waehle_geraet(_seite), "die Fixture liefert kein waehlbares Geraet"
    assert _seite.eval_on_selector_all("#tafel-verlauf svg", "e => e.length") == 1
    # Eine Linie JE ANBIETER, und die Legende nennt genau diese.
    legende = _seite.eval_on_selector_all(".gr-vlegende-teil", "e => e.length")
    assert legende > 0
    assert legende <= 8, "hoechstens acht Linien"


def test_hoechstens_acht_waagerechte_datumsmarken(_seite):
    """Diese Grenze ist der Ersatz fuer die 114 gedrehten Etiketten der
    geloeschten Grafik. Sie ist nicht verhandelbar."""
    _frisch(_seite)
    assert _waehle_geraet(_seite)
    marken = _seite.eval_on_selector_all(
        ".gr-vsvg text",
        "e => e.filter(t => !t.textContent.includes('\u20ac') "
        "&& /[0-9]/.test(t.textContent)).length")
    assert 0 < marken <= 8, marken
    gedreht = _seite.eval_on_selector_all(
        ".gr-vsvg text",
        "e => e.filter(t => /rotate|matrix/.test("
        "(t.getAttribute('transform')||'') + getComputedStyle(t).transform)).length")
    assert gedreht == 0
    klein = _seite.eval_on_selector_all(
        ".gr-vsvg text",
        "e => e.filter(t => parseFloat(getComputedStyle(t).fontSize) < 12).length")
    assert klein == 0


def test_die_achse_erfindet_keinen_preis(_seite):
    """41 der 89 waehlbaren Geraete haben genau EINEN Preis. Die erste
    Fassung schob dafuer die Obergrenze auf `lo + 1` und beschriftete die
    Hilfslinien daraus: bei 999,00 EUR stand dreimal "1000 €" an der Achse -
    ein Preis, den es im Datensatz nicht gibt."""
    _frisch(_seite)
    assert _waehle_geraet(_seite)
    # DEUTSCHE SCHREIBWEISE LESEN, nicht `parseFloat`. Die Achse schreibt
    # wie der Rest der Seite ("1.099,00 €"), und `parseFloat("1.099")` ist
    # 1,099 - der Test meldete damit eine Achse ausserhalb der Daten, die es
    # nicht gab. Beim Bauen ist daraufhin einmal die SEITE angepasst worden
    # (Achse ohne Tausendertrenner); das war die falsche Richtung, und der
    # Reviewer hat es gemeldet: ein schwacher Testparser darf nicht
    # bestimmen, wie die Seite aussieht.
    achse = _seite.eval_on_selector_all(
        ".gr-vsvg text",
        "e => e.filter(t => t.textContent.includes('€'))"
        "      .map(t => parseFloat(t.textContent"
        "                 .replace(/[^0-9.,]/g, '')"
        "                 .replace(/\\./g, '')"
        "                 .replace(',', '.')))")
    assert all(w == w for w in achse), f"unlesbare Achsenmarke: {achse}"
    punkte = _seite.eval_on_selector_all(
        ".gr-vpunkt title",
        "e => e.map(t => parseFloat(t.textContent.replace(/[^0-9,]/g,'')"
        "                                        .replace(',', '.')))")
    assert achse, "keine Preisachse"
    lo, hi = min(punkte), max(punkte)
    for wert in achse:
        assert lo - 1 <= wert <= hi + 1, (wert, lo, hi)


def test_die_tabelle_zeigt_dieselben_anbieter_wie_das_diagramm(_seite):
    """Zwei Zahlen fuer dieselbe Sache auf einem Bildschirm. Die Tabelle
    rechnete ueber den vollen Zeitraum, waehrend Diagramm, Legende und
    Kacheln dem Zeitraumfilter folgten - sie nannte einen Anbieter, der im
    Bild nicht vorkam, mit einem Datum ausserhalb des Fensters.

    Seit dem 30.08.2026 in DREI Lagen geprueft, und die mittlere ist die
    eigentliche: volles Fenster (Diagramm steht), verengtes Fenster mit noch
    genug Messtagen (Diagramm steht WEITER, ein frueher Anbieter faellt
    heraus - hier greift die urspruengliche Gleichheitspruefung), und
    Fenster auf einen Tag (kein Diagramm, Tabelle bleibt).

    Die mittlere Lage war kurzzeitig verloren: mit genau
    `DIAGRAMM_AB_TERMINEN` Messtagen in der Fixture fiel jede Verengung
    unters Gatter, und der Ersatz - "ohne Diagramm bleibt die Tabelle
    stehen" - war gegen den alten Fehler blind. Eine Tabelle, die wieder
    ueber den vollen Zeitraum rechnete, waere gruen geblieben."""
    _frisch(_seite)
    assert _waehle_geraet(_seite)

    def anbieter_der_tabelle():
        return set(_seite.eval_on_selector_all(
            "#gr-vtabelle tbody tr td:first-child",
            "e => e.map(x => x.textContent.trim())"))

    def legende():
        return set(_seite.eval_on_selector_all(
            ".gr-vlegende-teil", "e => e.map(x => x.textContent.trim())"))

    # 1. Volles Fenster: das Diagramm steht, und beide nennen dasselbe.
    assert _seite.is_visible("#gr-vbild svg"), (
        "ohne Diagramm prueft der erste Zweig nichts")
    voll = anbieter_der_tabelle()
    assert voll and voll == legende(), (voll, legende())
    assert _seite.eval_on_selector("#gr-vanb", "e => e.textContent.trim()") \
        == str(len(voll))

    # 2. Fenster VERENGT, aber noch ueber der Schwelle: das Diagramm bleibt
    #    stehen, ein frueher Anbieter faellt heraus - und Legende und
    #    Tabelle muessen weiter dieselben nennen.
    #
    #    Das ist die urspruengliche Zusicherung dieses Tests, und sie war
    #    kurzzeitig verloren: mit genau `DIAGRAMM_AB_TERMINEN` Messtagen in
    #    der Fixture fiel JEDE Verengung unters Gatter, es gab kein
    #    Diagramm mehr und folglich keine Legende zum Vergleichen. Der
    #    Ersatz war gegen den alten Fehler blind - eine Tabelle, die wieder
    #    ueber den vollen Zeitraum rechnete, waere gruen geblieben. Die
    #    Fixture hat deshalb sechs Messtage.
    _seite.fill("#gr-vvon", _MESSTAGE[2])
    _seite.wait_for_timeout(200)
    assert _seite.is_visible("#gr-vbild svg"), (
        "nach der Verengung auf vier Messtage muss das Diagramm stehen "
        "bleiben - sonst prueft dieser Zweig die Gleichheit gar nicht")
    # GEGENPROBE AN DER LEGENDE, nicht an der Tabelle. Die Legende entsteht
    # aus den gezeichneten Reihen; die Tabelle ist der Verdaechtige dieses
    # Tests. Haengt die Gegenprobe an der Tabelle, meldet ein Fehler in
    # genau ihr "der Test kann den Fall nicht ausloesen" - also den falschen
    # Grund. Es MUSS beim Verengen einer herausfallen, sonst ist die
    # Gleichheit darunter trivial erfuellt.
    im_bild = legende()
    assert im_bild < voll, (
        f"beim Verengen faellt kein Anbieter aus dem BILD ({im_bild} von "
        f"{voll}) - der Test kann den Fall nicht ausloesen")
    verengt = anbieter_der_tabelle()
    assert verengt == im_bild, (
        f"die Tabelle nennt {verengt}, das Bild zeigt {im_bild} - rechnet "
        f"sie wieder ueber den vollen Zeitraum?")
    tage = set(_seite.eval_on_selector_all(
        "#gr-vtabelle tbody tr td:last-child",
        "e => e.map(x => x.textContent.trim())"))
    fenster = set(_seite.eval_on_selector_all(
        "#gr-vbild .gr-vpunkt title",
        "e => e.map(x => x.textContent.split(' am ')[1])"))
    assert tage <= fenster, (
        f"die Tabelle nennt ein Datum, das im Bild nicht vorkommt: "
        f"{tage - fenster}")

    # 3. Fenster auf EINEN Tag: unter der Schwelle, also kein Bild - die
    #    Tabelle bleibt und folgt weiter dem Filter.
    bis = _seite.eval_on_selector("#gr-vbis", "e => e.value")
    _seite.fill("#gr-vvon", bis)
    _seite.wait_for_timeout(200)
    assert not _seite.is_visible("#gr-vbild svg"), (
        "ein Tag ist kein Verlauf - hier darf kein Diagramm stehen")
    assert not legende(), "keine Legende ohne Diagramm"
    eng = anbieter_der_tabelle()
    assert eng, "die Tabelle verschwindet nicht mit dem Diagramm"
    assert eng <= voll, (eng, voll)
    ein_tag = set(_seite.eval_on_selector_all(
        "#gr-vtabelle tbody tr td:last-child",
        "e => e.map(x => x.textContent.trim())"))
    assert len(ein_tag) == 1, (
        f"die Tabelle folgt dem Filter nicht: {ein_tag}")



def test_eine_neue_eingabe_raeumt_das_alte_diagramm_weg(_seite):
    """Sonst steht unter dem Suchwort "zzzz" unveraendert der Verlauf des
    zuletzt gewaehlten Geraets."""
    _frisch(_seite)
    assert _waehle_geraet(_seite)
    _seite.fill("#gr-vsuche", "zzzzgibtesnicht")
    _seite.wait_for_timeout(200)
    assert _seite.eval_on_selector_all("#tafel-verlauf svg", "e => e.length") == 0
    assert _seite.eval_on_selector(
        "#gr-vleer", "e => getComputedStyle(e).display") != "none"



# ==========================================================================
# NACHBESSERUNG 30.08.2026 - im echten Chromium, weil es im HTML nicht steht
# ==========================================================================

def test_die_kachel_und_der_satz_nennen_dieselbe_zahl(_seite):
    """Antonios Befund: "Die Kachel sagt 4 Messpunkte, der Satz darunter
    5 Messtermine."

    Beide Zahlen stimmten und zaehlten Verschiedenes: die Kachel die
    Preispunkte ueber alle Anbieter dieses Geraets, der Satz die Messtage
    ueber ALLE Geraete. Fuer den Leser sind das zwei Zahlen fuer dieselbe
    Sache. Jetzt zaehlen beide Messtage, und sobald eine Auswahl steht,
    spricht auch der Satz ueber dieses eine Geraet."""
    _frisch(_seite)
    assert _waehle_geraet(_seite)

    kacheln = _seite.eval_on_selector_all(
        ".gr-vkachel", "e => e.map(x => x.innerText.replace(/\\n/g, ' '))")
    passend = [k for k in kacheln if "Messtermin" in k]
    assert len(passend) == 1, kacheln
    aus_kachel = int(re.search(r"\d+", passend[0]).group())
    assert aus_kachel == len(_MESSTAGE), (passend, _MESSTAGE)

    satz = (_seite.text_content("#gr-vstand") or "").strip()
    assert f"{aus_kachel} Messtermine" in satz, (satz, aus_kachel)
    assert ".." not in satz, f"doppelter Satzpunkt: {satz!r}"
    # Der Gattersatz schweigt hier - sonst stuende dieselbe Zahl zweimal.
    assert not _seite.is_visible("#gr-vzukurz")


def test_das_raster_veraendert_die_zahl_der_messtermine_nicht(_seite):
    """Ein Messtermin ist ein TAG, an dem gemessen wurde.

    Die erste Fassung zaehlte NACH der Rasterung: der 03. und der 04.08.
    liegen in derselben Kalenderwoche und waren damit EIN Termin, und im
    Quartalsraster haette jedes Geraet genau einen gehabt. Der Umschalter
    haette so die Zahl der Messungen veraendert. Das Raster formt die LINIE,
    es formt nicht die Datenlage."""
    _frisch(_seite)
    assert _waehle_geraet(_seite)

    # Gegenprobe: zwei Messtage MUESSEN in dieselbe Woche fallen, sonst
    # koennte die Rasterung die Zahl gar nicht veraendern und der Test
    # prueft eine Regel, die nicht greifen kann.
    from datetime import date
    wochen = {date.fromisoformat(t).isocalendar()[:2] for t in _MESSTAGE}
    assert len(wochen) < len(_MESSTAGE), (
        f"alle Messtage in verschiedenen Wochen: {_MESSTAGE}")

    def termine():
        return _seite.text_content("#gr-vpkt").strip()

    def bild():
        """Was WIRKLICH gezeichnet ist - nicht nur, dass ein <svg> dasteht.

        Genau hier ist der Fehler durchgerutscht: der Test zaehlte nur die
        Kachel. Im Monats- und Quartalsraster fallen alle Messtage in EIN
        Zeitfenster, jede Reihe hat dann einen Punkt, und `<path>` wird fuer
        eine Reihe mit einem Punkt gar nicht gezeichnet - es stand ein
        "Preisverlauf" mit null Linien da, und die Kachel sagte weiter die
        richtige Zahl."""
        return _seite.evaluate("""() => ({
            svg: !!document.querySelector('#gr-vbild svg'),
            sichtbar: !document.getElementById('gr-vbild').hidden,
            linien: document.querySelectorAll('#gr-vbild path').length,
        })""")

    assert termine() == str(len(_MESSTAGE)), termine()
    for raster in ("monat", "quartal", "woche"):
        _seite.click(f'.gr-vknopf[data-raster="{raster}"]')
        _seite.wait_for_timeout(150)
        assert termine() == str(len(_MESSTAGE)), f"{raster}: {termine()}"
        # KEIN DIAGRAMM OHNE LINIE. Entweder es steht eins da und traegt
        # wenigstens eine Linie, oder es steht keins da - ein leeres Bild
        # ist genau das, wogegen das Gatter gebaut ist.
        z = bild()
        assert not z["sichtbar"] or z["linien"] > 0, (
            f"{raster}: Diagramm ohne eine einzige Linie - {z}")


def test_eine_verdeckte_linie_wird_sichtbar_gemacht(_eigene_seite):
    """Antonios Befund: "Die Vodafone-Linie ist unsichtbar - sie liegt bei
    1.099,90 EUR exakt unter der mobilcom-debitel-Linie bei 1.099,00 EUR,
    90 Cent Abstand auf einer Achse von 793 bis 1.100 EUR. In der Legende
    steht Vodafone, im Bild ist es nicht."

    Sie wird gestrichelt gezeichnet und bekommt ein Etikett an ihrem Ende -
    beides auf ihrer WAHREN Hoehe. VERSCHOBEN WIRD NICHTS: die Y-Achse
    gehoert dem Preis, das ist die Lehre aus der geloeschten Positionskarte,
    deren Etiketten bis zu 235 px neben ihrem Punkt standen.

    Der Fall wird gestellt - die Fixture haelt ihre Preise bewusst weit
    auseinander. Gerechnet wird trotzdem vom echten `app.js`."""
    seite = _eigene_seite
    tage = list(_MESSTAGE)
    _stelle_daten(seite, {
        "id": "probe", "label": "Probefall 128 GB", "hersteller": "Probe",
        "speicher": 128, "suchtext": "probefall", "min": 793, "max": 1100,
        "anbieter": 3, "messpunkte": 3 * len(tage), "messtermine": len(tage),
        "tage": tage, "aktuell": [],
        "reihen": [
            {"anbieter": "mobilcom-debitel", "farbe": "#2b5bd7", "eigen": False,
             "punkte": [{"datum": t, "preis": 1099.0} for t in tage]},
            {"anbieter": "Vodafone", "farbe": "#e60000", "eigen": True,
             "punkte": [{"datum": t, "preis": 1099.9} for t in tage]},
            {"anbieter": "o2", "farbe": "#217a3c", "eigen": False,
             "punkte": [{"datum": t, "preis": 793.0 + i * 35}
                        for i, t in enumerate(tage)]},
        ]})

    striche = seite.eval_on_selector_all(
        "#gr-vbild path", "e => e.map(x => x.getAttribute('stroke-dasharray'))")
    assert len(striche) == 3, striche
    assert len([x for x in striche if x]) == 1, (
        f"genau eine der drei Linien liegt verdeckt: {striche}")

    etiketten = seite.eval_on_selector_all(
        "#gr-vbild .gr-vetikett", "e => e.map(x => x.textContent)")
    assert len(etiketten) == 1, etiketten
    assert "Vodafone" in etiketten[0] and "1.099,90" in etiketten[0], etiketten

    lage = seite.evaluate("""() => {
        const svg = document.querySelector('#gr-vbild svg');
        const t = svg.querySelector('.gr-vetikett');
        const kasten = t.getBBox();
        const kreise = [...svg.querySelectorAll('circle')]
            .map(c => +c.getAttribute('cy'));
        const y = +t.getAttribute('y');
        return { abstand: Math.min(...kreise.map(cy => Math.abs(cy - y))),
                 rechts: kasten.x + kasten.width,
                 breite: svg.viewBox.baseVal.width,
                 groesse: parseFloat(getComputedStyle(t).fontSize) };
    }""")
    assert lage["abstand"] <= 6, (
        f"das Etikett steht {lage['abstand']} px neben jedem Punkt - genau "
        f"der Fehler der geloeschten Positionskarte")
    assert lage["rechts"] <= lage["breite"], (
        f"das Etikett laeuft aus dem Bild: {lage['rechts']} > {lage['breite']}")
    assert lage["groesse"] >= MIN_SCHRIFT, lage["groesse"]


def test_unter_vier_messterminen_steht_kein_diagramm(_seite):
    """Antonios Befund: "Bei Pixel 10 Pro 128 GB zwei Datumsmarken (10.8. und
    30.8.), dazwischen nichts."

    Zwei Punkte ergeben eine Gerade, und eine Gerade durch zwei Punkte sieht
    aus wie ein Trend. Unter der Schwelle steht deshalb die Tabelle allein,
    mit einem Satz darueber.

    Der Fall wird ueber den Zeitraumfilter hergestellt - er verengt die
    Auswahl auf zwei Messtage, und das ist genau die Datenlage, die Antonio
    vor sich hatte."""
    _frisch(_seite)
    assert _waehle_geraet(_seite)
    assert _seite.is_visible("#gr-vbild svg"), (
        "ohne Diagramm im Ausgangszustand prueft der Test nicht die Aenderung")

    _seite.fill("#gr-vvon", _MESSTAGE[0])
    _seite.fill("#gr-vbis", _MESSTAGE[1])
    _seite.wait_for_timeout(200)

    assert not _seite.is_visible("#gr-vbild svg"), (
        "unter der Schwelle darf kein Diagramm stehen - auch kein leeres")
    assert not _seite.eval_on_selector_all(".gr-vlegende-teil", "e => e.length")
    hinweis = (_seite.text_content("#gr-vzukurz") or "").strip()
    assert "2 Messtermine" in hinweis, hinweis
    assert "ab 4" in hinweis, hinweis
    assert ".." not in hinweis, f"doppelter Satzpunkt: {hinweis!r}"
    # Und die Zahl steht nur EINMAL da.
    assert not _seite.is_visible("#gr-vstand")
    assert _seite.is_visible("#gr-vtabelle table"), (
        "die Tabelle ersetzt das Diagramm, sie verschwindet nicht mit ihm")


@pytest.mark.parametrize("tafel,knopf,schluessel", [
    ("tafel-alarme", "euro", "sEuro"),
    ("tafel-alarme", "prozent", "sProzent"),
    ("tafel-katalog", "preis", "sPreis"),
])
def test_ein_klick_auf_den_spaltenkopf_sortiert_nach_dem_rohwert(
        _seite, tafel, knopf, schluessel):
    """"Bei acht Spalten und 24 Zeilen ist Sortieren nach Euro-Abstand statt
    Prozent die erste Frage, die jemand hat."

    Sortiert wird nach dem ROHWERT an der Zeile, nicht nach dem Zelltext:
    "1.099,90 €" ist als Zeichenkette kleiner als "199,00 €", und ein
    Sortierer, der die Zelle liest, stellt den teuersten Preis nach vorn und
    sieht dabei richtig aus."""
    _frisch(_seite)
    _seite.click(f".gr-reiter button[data-tafel='{tafel}']")
    _seite.wait_for_timeout(80)

    def sichtbare_werte():
        return _seite.eval_on_selector_all(
            f"#{tafel} .gr-a-zeile",
            "(e, k) => e.filter(x => getComputedStyle(x).display !== 'none')"
            "           .map(x => parseFloat(x.dataset[k]))", schluessel)

    wahl = f'#{tafel} .gr-sort[data-sort="{knopf}"]'

    def geordnet():
        """Die Reihenfolge MUSS zu dem passen, was `aria-sort` behauptet.

        Absolut zu pruefen ginge hier fehl: die Prozentspalte steht schon in
        der Vorgabe absteigend (so liefert `geraete_alarme.zeilen()`), und
        ein Klick darauf dreht sie folglich auf aufsteigend. Ein Test, der
        auf dem ersten Klick "absteigend" verlangt, misst nicht die
        Sortierung, sondern die Vorbelegung."""
        richtung = _seite.get_attribute(wahl, "aria-sort")
        assert richtung in ("ascending", "descending"), richtung
        werte = sichtbare_werte()
        assert len(werte) > 1, f"{tafel}: zu wenige sichtbare Zeilen"
        if richtung == "descending":
            assert all(werte[i] >= werte[i + 1] for i in range(len(werte) - 1)), werte
        else:
            assert all(werte[i] <= werte[i + 1] for i in range(len(werte) - 1)), werte
        return richtung

    _seite.click(wahl)
    _seite.wait_for_timeout(150)
    erste = geordnet()

    _seite.click(wahl)
    _seite.wait_for_timeout(150)
    zweite = geordnet()
    assert erste != zweite, (
        f"der zweite Klick dreht die Richtung nicht: {erste}")


def test_die_sortierung_vergibt_den_zeilendeckel_neu(_seite):
    """Der teuerste Fehler, den eine Sortierung mit Deckel machen kann.

    `SICHTBAR_MAX` begrenzt die Seitenhoehe; die sichtbaren Zeilen sind die
    ERSTEN zwoelf der aktuellen Ordnung. Bliebe `gr-a-rest` an den
    urspruenglichen Zeilen kleben, zeigte eine Sortierung nach Euro die
    zwoelf groessten PROZENTwerte, untereinander nach Euro geordnet - eine
    Rangliste, die es nicht gibt, und der groesste Euro-Abstand stuende
    nicht darunter."""
    _frisch(_seite)

    def sichtbar(schluessel):
        return _seite.eval_on_selector_all(
            "#tafel-alarme .gr-a-zeile",
            "(e, k) => e.filter(x => getComputedStyle(x).display !== 'none')"
            "           .map(x => parseFloat(x.dataset[k]))", schluessel)

    def alle(schluessel):
        return _seite.eval_on_selector_all(
            "#tafel-alarme .gr-a-zeile",
            "(e, k) => e.map(x => parseFloat(x.dataset[k]))", schluessel)

    # Gegenprobe: der Deckel muss ueberhaupt greifen, sonst ist der Fall
    # nicht ausloesbar und der Test gruen ohne Aussage.
    assert len(sichtbar("sEuro")) < len(alle("sEuro")), (
        "kein Deckel aktiv - dann prueft dieser Test nichts")
    # Und die zwei Ordnungen muessen sich unterscheiden.
    nach_prozent = sorted(alle("sProzent"), reverse=True)
    assert nach_prozent != sorted(alle("sEuro"), reverse=True), (
        "Prozent und Euro ordnen gleich - der Fall ist nicht ausloesbar")

    _seite.click('#tafel-alarme .gr-sort[data-sort="euro"]')
    _seite.wait_for_timeout(150)
    oben = sichtbar("sEuro")
    assert oben, "keine sichtbare Zeile nach dem Sortieren"
    assert max(oben) == max(alle("sEuro")), (
        "der groesste Euro-Abstand steht nicht unter den sichtbaren Zeilen - "
        "der Deckel klebt an der alten Ordnung")


def test_die_achse_beschriftet_keine_zwei_linien_gleich(_eigene_seite):
    """Beim Durchspielen der Randfaelle gefunden, nicht auf Antonios Liste.

    `Math.round` reicht, solange die Preisspanne mehrere Euro breit ist. Bei
    drei Anbietern zwischen 900,00 und 900,20 EUR stand die Achse fuenfmal
    mit "900 €" da - fuenf Hilfslinien, die behaupten, fuenf verschiedene
    Hoehen zu benennen. Dieselbe Fehlerklasse wie die drei "1000 €" bei
    einem Preis von 999,00, gegen die `test_die_achse_erfindet_keinen_preis`
    gebaut ist: eine Achse, der man nicht glauben kann."""
    seite = _eigene_seite
    tage = list(_MESSTAGE)
    _stelle_daten(seite, {
        "id": "eng", "label": "Engfall 128 GB", "hersteller": "Eng",
        "speicher": 128, "suchtext": "engfall", "min": 900.0, "max": 900.2,
        "anbieter": 3, "messpunkte": 3 * len(tage), "messtermine": len(tage),
        "tage": tage, "aktuell": [],
        "reihen": [
            {"anbieter": "o2", "farbe": "#2b5bd7", "eigen": False,
             "punkte": [{"datum": t, "preis": 900.0} for t in tage]},
            {"anbieter": "Vodafone", "farbe": "#e60000", "eigen": True,
             "punkte": [{"datum": t, "preis": 900.1} for t in tage]},
            {"anbieter": "mobilcom-debitel", "farbe": "#217a3c", "eigen": False,
             "punkte": [{"datum": t, "preis": 900.2} for t in tage]},
        ]})

    achse = seite.eval_on_selector_all(
        ".gr-vsvg text",
        "e => e.filter(t => t.textContent.includes('€'))"
        "      .map(t => t.textContent.trim())")
    assert len(achse) > 1, (
        f"nur {len(achse)} Achsenmarke(n) - der Fall ist nicht ausloesbar: {achse}")
    assert len(set(achse)) == len(achse), (
        f"zwei Hilfslinien mit demselben Text: {achse}")

    # Und keine Marke liegt ausserhalb der Daten - die Regel von 30.08.2026
    # gilt weiter, sie wird nur genauer beschriftet.
    werte = [float(t.replace("\u00a0", "").replace("€", "").strip()
                    .replace(".", "").replace(",", ".")) for t in achse]
    assert min(werte) >= 900.0 - 0.01 and max(werte) <= 900.2 + 0.01, achse


def test_die_preiskacheln_stehen_so_im_datensatz(_seite):
    """`#gr-vmin` und `#gr-vmax` wurden von keinem Test gegen die Daten
    gehalten - und sie wiegen seit dem 30.08.2026 schwerer, weil sie auch im
    Zustand OHNE Diagramm dastehen. An den Echtdaten trifft das 86 von 89
    Geräten.

    Geprüft wird gegen die Punkte, die das Bild wirklich trägt (Tooltip je
    Messpunkt), nicht gegen eine zweite Rechnung: zwei Rechnungen für
    dieselbe Zahl sind zwei Zahlen (CLAUDE.md §6)."""
    _frisch(_seite)
    assert _waehle_geraet(_seite)

    def euro_zu_zahl(text):
        return float(text.replace(" ", "").replace("€", "").strip()
                     .replace(".", "").replace(",", "."))

    preise = _seite.eval_on_selector_all(
        "#gr-vbild .gr-vpunkt title",
        "e => e.map(x => x.textContent.split(': ')[1].split(' am ')[0])")
    assert preise, "keine Messpunkte im Bild - der Test misst nichts"
    werte = [euro_zu_zahl(p) for p in preise]

    kachel_min = euro_zu_zahl(_seite.text_content("#gr-vmin"))
    kachel_max = euro_zu_zahl(_seite.text_content("#gr-vmax"))
    assert kachel_min == min(werte), (kachel_min, min(werte))
    assert kachel_max == max(werte), (kachel_max, max(werte))
    # Gegenprobe: die zwei Kacheln müssen sich unterscheiden, sonst sagt der
    # Test nichts darüber, ob min und max verwechselt sind.
    assert kachel_min != kachel_max, (
        "alle Preise gleich - der Test kann eine Verwechslung nicht sehen")


# --------------------------------------------------------------------------
# B5 (31.08.2026): "Standardansicht nach Hersteller und Aktualitaet
# sortiert, vorgefiltert auf Zustand = neu, erste Bildschirmseite zeigt
# mindestens drei Hersteller."
#
# EIGENE Seite, EIGENER Bestand - nicht `_seite`/`_KATALOG`. Die gemeinsame
# Fixture kennt nur zwei Hersteller (Apple/Samsung im Wechsel); die
# Zusicherung "mindestens drei Hersteller ohne Scrollen" ist mit ihr gar
# nicht auslösbar. Ein eigener Bau ist hier billiger als ein Fixture-Umbau,
# der Dutzende andere Tests (Alarmstufen, Markenfilter) mitreissen wuerde.
# --------------------------------------------------------------------------

_B5_HERSTELLER = ("Apple", "Samsung", "Google", "Xiaomi")

# SIEBEN Geraete je Hersteller, nicht zwei (Nachbesserung, 31.08.2026,
# B7 der Zurueckweisung Runde 2). Mit zwei Geraeten je Hersteller passt
# schon eine REINE Gruppierung (kein Reihum) in die sichtbaren acht Zeilen
# und schliesst alle vier Hersteller ein - der Mutationstest "Reihum
# entfernen" faellt an keinem der beiden Tests auf, die genau das pruefen
# sollen sollen. Mit sieben Geraeten fuellt "Apple" allein die ganze
# sichtbare Flaeche, und nur ein echtes Reihum zeigt einen zweiten
# Hersteller.
_B5_KATALOG = {"geraete": [
    {"hersteller": h, "modell": f"{h} Modell {n}", "generation": n,
     "speicher": [256], "segment": "flagship"}
    for h in ("Apple", "Samsung", "Google", "Xiaomi") for n in range(1, 8)
]}
_B5_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_B5_QUELLEN = {"anbieter": [
    {"name": "Medimax", "typ": "handel", "rang": 1, "methode": "ldjson",
     "basis_url": "https://www.medimax.de",
     "einstiege": [{"url": "https://www.medimax.de/c/116"}]},
]}


def _b5_listung(modell: str, hersteller: str, preis: float,
                zustand: str = "neu") -> dict:
    # `device_id()` aus `geraete_model`, NICHT eine eigene Nachbildung: eine
    # zweite Rechnung fuer dieselbe ID lief hier schon einmal auseinander
    # (Xiaomi/Redmi-Fall der ersten Nachbesserung) - `device_id()` kuerzt
    # den Hersteller aus dem Modellnamen, wenn er ihn bereits traegt
    # ("Apple Modell 1" -> "apple-modell-1", NICHT
    # "apple-apple-modell-1"), und genau das tat diese Fixture nicht.
    from telco_radar.geraete_model import device_id
    gid = device_id(hersteller, modell)
    sku = f"{gid}-256gb-schwarz{'-ref' if zustand != 'neu' else ''}"
    return {
        "id": f"medimax--{sku}", "sku_id": sku, "device_id": gid,
        "anbieter": "Medimax", "anbieter_typ": "handel", "netz": "",
        "speicher_gb": 256, "farbe_roh": "Schwarz",
        "farbe_normalisiert": "schwarz", "zustand": zustand,
        "first_seen": "2026-08-01", "last_verified": "2026-08-31",
        "status": "aktiv", "missed_checks": 0, "preis_ohne_vertrag": preis,
        "erstpreis": preis, "erstpreis_art": "ohne_vertrag",
        "erstpreis_am": "2026-08-01",
        "quelle_url": f"https://example.de/p/{sku}",
        "abgerufen_am": "2026-08-31", "verfuegbarkeit": "lieferbar",
        "confidence": "hoch", "einstiege": ["https://example.de/liste"],
    }


def _b5_bestand() -> list:
    """Sieben NEUgeraete je Hersteller (28 insgesamt, ueber dem Deckel von
    zwoelf), dazu DREI refurbished Zeilen - je eine bei Apple, Samsung und
    Xiaomi, auf ein bereits vorhandenes neu-Geraet desselben Herstellers
    (B2/B3-Nachbesserung, 31.08.2026): so bleibt "Zustand: neu" filterbar
    UND jeder Hersteller behaelt mindestens sechs passende Zeilen, auch
    nachdem die drei nicht-passenden herausgefiltert sind."""
    zeilen = []
    for g in _B5_KATALOG["geraete"]:
        zeilen.append(_b5_listung(g["modell"], g["hersteller"],
                                  1.0 * g["generation"] * 40))
    for h in ("Apple", "Samsung", "Xiaomi"):
        zeilen.append(_b5_listung(f"{h} Modell 1", h, 55.0,
                                  zustand="refurbished"))
    return zeilen


_B5_DB = {"updated": "2026-08-31",
         "anbieter": {"Medimax": {"laeufe": 4, "funde_gesamt": 9}},
         "listungen": _b5_bestand()}


@pytest.fixture(scope="module")
def _b5_seite(_seite, tmp_path_factory):
    """Eine eigene Seite, aber im SELBEN Browser wie `_seite` - ein zweiter
    `sync_playwright()`-Kontext im selben Prozess scheitert ("It looks like
    you are using Playwright Sync API inside the asyncio loop"), solange der
    erste noch offen ist (Modulgueltigkeit von `_seite`). Dieselbe
    Wiederverwendung wie bei `_umgebung`/`_eigene_seite`, nur mit einem
    EIGENEN lokalen Server fuer den abweichenden Bestand.
    """
    root = tmp_path_factory.mktemp("b5")
    (root / "config").mkdir()
    for name, daten in (("geraete_katalog.yaml", _B5_KATALOG),
                        ("farben.yaml", _B5_FARBEN),
                        ("geraete_quellen.yaml", _B5_QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps(_B5_DB), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    site = root / "site"
    render_site(site, reports, cfg=None)

    browser = _seite.context.browser
    with _server(site) as basis:
        seite = browser.new_page(viewport={"width": 1440, "height": 900})
        seite.goto(f"{basis}/geraete.html", wait_until="load")
        yield {"seite": seite, "basis": basis}
        seite.close()


def _b5_frisch(_b5_seite):
    """Ein unberuehrter Ausgangszustand fuer einen Test - `_b5_seite` ist
    modulgueltig und mehrere Tests klicken auf denselben Spaltenkopf; ohne
    einen echten Neuladen saehe ein Test die Sortierung/Filterwahl eines
    vorigen Tests. Dieselbe Rolle wie `_frisch()` fuer `_seite`."""
    seite = _b5_seite["seite"]
    seite.goto(f"{_b5_seite['basis']}/geraete.html", wait_until="load")
    seite.click(".gr-reiter button[data-tafel='tafel-katalog']")
    seite.wait_for_timeout(80)
    # "Erste Bildschirmseite" gilt AB DEM REITER, nicht ab dem Seitenkopf:
    # der Zeitungskopf plus die Reihen der Titelseite darueber sind ein
    # Preis, den jede Unterseite dieser Site einmal zahlt, unabhaengig von
    # der Sortierung DIESES Reiters. Ohne den Scroll misst der Test, ob der
    # Zeitungskopf kurz ist - nicht, ob der Katalog es ist. An der echten
    # Ausgabe gemessen: ohne Scroll passt GAR KEINE Zeile mehr ins Bild (der
    # Kopf allein braucht ueber 840 px), mit Scroll zum Reiter acht.
    seite.eval_on_selector(".gr-reiter", "e => e.scrollIntoView({block:'start'})")
    seite.wait_for_timeout(80)
    return seite


def test_die_erste_bildschirmseite_zeigt_mindestens_drei_hersteller(_b5_seite):
    """Wortlaut des Auftrags. Gemessen wird in PIXELN (Bounding-Box
    innerhalb des Sichtfensters), nicht an der Zeilenzahl - "erste
    Bildschirmseite" ist eine Aussage ueber das, was ohne Scrollen zu sehen
    ist, keine ueber die Position in einer Liste.

    B7 der Zurueckweisung (Runde 2): mit ZWEI Geraeten je Hersteller fuellt
    schon eine REINE Gruppierung (kein Reihum) die acht sichtbaren Zeilen
    mit allen vier Herstellern - der Mutationstest "Reihum entfernen" fiel
    an diesem Test nicht auf. Die Fixture traegt seitdem SIEBEN Geraete je
    Hersteller: "Apple" allein wuerde die ganze sichtbare Flaeche fuellen,
    und nur ein echtes Reihum zeigt einen zweiten Hersteller. Gegengeprueft
    per Hand: mit `_interleave_je_hersteller` durch eine reine
    `sorted(zeilen, key=...)` ersetzt, faellt dieser Test (1 statt >=3
    Hersteller).
    """
    seite = _b5_frisch(_b5_seite)
    marken = seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-k-zeile",
        "(zeilen, hoehe) => zeilen"
        "  .filter(z => getComputedStyle(z).display !== 'none'"
        "             && z.getBoundingClientRect().top < hoehe"
        "             && z.getBoundingClientRect().top >= 0)"
        "  .map(z => z.dataset.marke)", 900)
    assert len(set(marken)) >= 3, (
        f"nur {len(set(marken))} Hersteller ohne Scrollen: {marken}")


def test_der_zustandsfilter_steht_von_anfang_an_auf_neu(_b5_seite):
    """Die Vorbelegung des <select> - sichtbar, ohne dass jemand klickt."""
    seite = _b5_frisch(_b5_seite)
    wert = seite.eval_on_selector(
        "#tafel-katalog [data-filter='zustand']", "e => e.value")
    assert wert == "neu", wert


def test_die_vorbelegung_versteckt_serverseitig_keine_zeile(_b5_seite):
    """Der Fehler vom 30.08. (Commit 79085f0): drei Zahlen liefen
    auseinander, weil eine Vorbelegung Zeilen per JS versteckte, die
    Ueberschrift und der "alle anzeigen"-Knopf aber weiterhin die volle
    Zahl nannten. Diese Fassung filtert serverseitig nichts heraus - die
    Gegenprobe: die Zahl der ZEILEN IM DOM (versteckt oder nicht) ist exakt
    der Bestand, unabhaengig von der Vorbelegung des Filters."""
    seite = _b5_frisch(_b5_seite)
    anzahl = seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-k-zeile", "e => e.length")
    assert anzahl == len(_B5_DB["listungen"])
    ueberschrift = seite.text_content(".gr-katalog h2 .rubrik-zahl").strip()
    assert ueberschrift == str(len(_B5_DB["listungen"]))


# --------------------------------------------------------------------------
# B2/B3 der Zurueckweisung (31.08.2026): der Deckel folgt jetzt dem Filter,
# nicht mehr der Position. Beide Tests fahren die Reproduktion des Pruefers
# selbst nach: zwei Klicks auf die Spalte "Zustand", danach "alle anzeigen".
# --------------------------------------------------------------------------

def _b5_treffer_neu() -> int:
    return sum(1 for e in _B5_DB["listungen"] if e["zustand"] == "neu")


def test_b2_zwei_sortierklicks_lassen_den_deckel_nicht_kollabieren(_b5_seite):
    """B2: "Zwei Klicks auf den Spaltenkopf Zustand" liessen elf
    nicht-passende Zeilen in den Deckel rutschen, waehrend die passenden
    dahinter verschwanden - sichtbar fiel von zwoelf auf eins.

    Gegengeprueft per Hand: in `app.js` `deckel > 0 && !alleZeigen` durch
    `false` ersetzt (der Deckel greift nie), dieser Test faellt (sichtbar
    > deckel statt ==).
    """
    from telco_radar.report.geraete_view import KATALOG_SICHTBAR
    seite = _b5_frisch(_b5_seite)
    seite.click('#gr-katalogtabelle .gr-sort[data-sort="zustand"]')
    seite.wait_for_timeout(120)
    seite.click('#gr-katalogtabelle .gr-sort[data-sort="zustand"]')
    seite.wait_for_timeout(120)
    sichtbar = seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none').length")
    erwartet = min(KATALOG_SICHTBAR, _b5_treffer_neu())
    assert sichtbar == erwartet, (
        f"{sichtbar} sichtbar nach zwei Sortierklicks, erwartet {erwartet}")


def test_b3_alle_anzeigen_liefert_was_der_knopf_verspricht(_b5_seite):
    """B3: der Knopf versprach "alle 360 zeigen", lieferte 349 - die im
    Knopf genannte Zahl und die nach dem Klick sichtbare muessen
    uebereinstimmen, unabhaengig vom aktiven Filter.

    Gegengeprueft per Hand: `mehr.textContent = ...` in `app.js`
    entfernt (der Knopf behaelt seinen SSR-Text mit der Gesamtzahl), dieser
    Test faellt, weil die im Knopf genannte Zahl dann nicht mehr zur
    tatsaechlich sichtbaren passt.
    """
    seite = _b5_frisch(_b5_seite)
    knopf_text = seite.text_content("#gr-kmehr")
    versprochen = int(knopf_text.split()[1])
    seite.click("#gr-kmehr")
    seite.wait_for_timeout(120)
    sichtbar = seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none').length")
    assert sichtbar == versprochen, (
        f"Knopf versprach {versprochen}, sichtbar sind {sichtbar}")
    assert versprochen == _b5_treffer_neu(), (
        "der Knopf verspricht nicht die Zahl der TREFFER unter dem "
        f"aktiven Filter: {versprochen} != {_b5_treffer_neu()}")


# --------------------------------------------------------------------------
# B4/B5/B7 der Zurueckweisung (31.08.2026): der Quelllink im Anker - auf
# der grossen, gemeinsamen Fixture (`_seite`), nicht auf der B5-eigenen:
# diese drei Zusicherungen sind unabhaengig von Herstellervielfalt oder
# Filterzustand und gelten fuer BEIDE Tabellen des echten Bestands.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tafel", ["tafel-alarme", "tafel-katalog"])
def test_b7_der_anbietername_liegt_im_anker(_seite, tafel):
    """B7 (Runde 2): fuenf neue Tests der ersten Nachbesserung waren alle
    B5-Tests - keiner hielt B7 selbst. Eine Rueckabwicklung (Name wieder
    als Text VOR dem Anker, wie vor der ersten Nachbesserung) liess keinen
    von ihnen fallen. Diese Zusicherung prueft die Struktur direkt: kein
    Zeichen der Anbieterzelle steht vor dem `<a>`.

    Gegengeprueft per Hand: die Vorlage auf
    `{{ z.anbieter }}<a class="gr-a-quelle">...</a>` zurueckgedreht (Name
    ausserhalb des Ankers), dieser Test faellt (`vorText` ist dann der
    Anbietername statt eines leeren Strings).
    """
    _frisch(_seite)
    _seite.click(f".gr-reiter button[data-tafel='{tafel}']")
    _seite.wait_for_timeout(80)
    ergebnis = _seite.eval_on_selector(f"#{tafel} .gr-a-quelle", """
      (a) => {
        var zelle = a.closest('td');
        var vorText = '';
        for (var n = zelle.firstChild; n && n !== a; n = n.nextSibling) {
          vorText += n.textContent || '';
        }
        return {vorText: vorText.trim(), ankerText: a.textContent.trim()};
      }
    """)
    assert ergebnis["vorText"] == "", (
        f"{tafel}: Text VOR dem Anker in der Anbieterzelle: "
        f"{ergebnis['vorText']!r}")
    assert ergebnis["ankerText"], f"{tafel}: der Anker ist leer"


@pytest.mark.parametrize("tafel", ["tafel-alarme", "tafel-katalog"])
def test_b4_der_anker_traegt_keine_fremde_quellentabellen_typografie(_seite, tafel):
    """B4: `.src-table a` (Spezifitaet 0-1-1) schlug `.gr-a-quelle`
    (0-1-0) im Katalog - der Name erbte 10 px, Grossbuchstaben, Fettschrift,
    Rot. In der Alarmtabelle (kein `.src-table`) blieb dagegen selbst mit
    korrekter Farbe nur der Pfeil als Hinweis auf einen Link - keine
    dauerhafte Unterstreichung, B7s urspruengliche Beschwerde erneut.

    Gegengeprueft per Hand: `.gr-alarm a.gr-a-quelle` in `style.css` auf
    `.gr-a-quelle` (ohne `.gr-alarm`, ohne `a`) zurueckgestutzt - im
    Katalog schlaegt danach wieder `.src-table a` (fontSize 10px statt
    14px), dieser Test faellt.
    """
    _frisch(_seite)
    _seite.click(f".gr-reiter button[data-tafel='{tafel}']")
    _seite.wait_for_timeout(80)
    link = _seite.eval_on_selector(f"#{tafel} .gr-a-quelle", """
      (a) => ({
        fontSize: getComputedStyle(a).fontSize,
        textTransform: getComputedStyle(a).textTransform,
        color: getComputedStyle(a).color,
        zellFarbe: getComputedStyle(a.closest('td')).color,
        textDecorationLine: getComputedStyle(a).textDecorationLine,
      })
    """)
    assert link["fontSize"] == "14px", link
    assert link["textTransform"] == "none", link
    assert link["color"] == link["zellFarbe"], (
        "der Link faerbt sich anders als sein Zelltext ohne Hover: " + str(link))
    assert link["textDecorationLine"] == "underline", (
        "kein dauerhafter Hinweis auf einen Link ohne Hover: " + str(link))


@pytest.mark.parametrize("tafel", ["tafel-alarme", "tafel-katalog"])
def test_b5_enter_auf_dem_fokussierten_quelllink_wird_nicht_verhindert(_seite, tafel):
    """B5: der `keydown`-Handler auf der Zeile rief fuer Enter/Space
    `preventDefault()` auf ALLEM innerhalb `.gr-a-zeile` auf - ohne den
    `closest('a')`-Ausstieg, den der `click`-Handler daneben hat. Ein
    fokussierter Quelllink war damit per Tastatur nicht auszuloesen.

    Gegengeprueft per Hand: den `closest('a')`-Ausstieg im
    `keydown`-Handler in `app.js` entfernt, dieser Test faellt
    (`defaultPrevented` wird `true`).
    """
    _frisch(_seite)
    _seite.click(f".gr-reiter button[data-tafel='{tafel}']")
    _seite.wait_for_timeout(80)
    ergebnis = _seite.eval_on_selector(f"#{tafel} .gr-a-quelle", """
      (el) => {
        el.focus();
        var ev = new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true});
        var nichtVerhindert = el.dispatchEvent(ev);
        return {defaultPrevented: !nichtVerhindert, fokussiert: document.activeElement === el};
      }
    """)
    assert ergebnis["fokussiert"], f"{tafel}: der Link laesst sich nicht fokussieren"
    assert not ergebnis["defaultPrevented"], (
        f"{tafel}: Enter auf dem Link wird verhindert - die Tastatur "
        "kann ihn nicht ausloesen")



# --------------------------------------------------------------------------
# P1 (dritte Nachbesserung, 31.08.2026): Rueckweisung des Coordinators.
# "Deine Fixture hat den Fall zweimal nicht ausgeloest." Beide vorigen
# Fassungen bauten ihre EIGENE, kleine Fixture - und beide Male kam die
# Datenlage der SYNTHETISCHEN Fixture zufaellig anders heraus als die der
# ECHTEN Daten (erst zwei Geraete je Hersteller, dann sieben Geraete je
# Hersteller statt sieben FARBEN eines einzigen Geraets). Dieser Test misst
# deshalb direkt gegen `data/state/geraete_db.json` und
# `config/geraete_katalog.yaml` - keine eigene Erfindung mehr dazwischen.
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _echte_seite(_seite, tmp_path_factory):
    """Dieselbe Seite wie `_seite`, aber aus dem ECHTEN Bestand des Repos
    gerendert - nicht aus `_KATALOG`/`_DB`. Wiederverwendet den Browser von
    `_seite` aus demselben Grund wie `_b5_seite`: ein zweiter
    `sync_playwright()`-Kontext im selben Prozess scheitert, solange der
    erste noch offen ist.
    """
    root = tmp_path_factory.mktemp("echt")
    (root / "config").mkdir()
    for name in ("geraete_katalog.yaml", "farben.yaml", "geraete_quellen.yaml"):
        shutil.copy(REPO / "config" / name, root / "config" / name)
    state = root / "data" / "state"
    state.mkdir(parents=True)
    shutil.copy(REPO / "data" / "state" / "geraete_db.json",
               state / "geraete_db.json")
    shutil.copy(REPO / "data" / "state" / "geraete_preise.jsonl",
               state / "geraete_preise.jsonl")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    site = root / "site"
    render_site(site, reports, cfg=None)

    browser = _seite.context.browser
    with _server(site) as basis:
        seite = browser.new_page(viewport={"width": 1440, "height": 900})
        seite.goto(f"{basis}/geraete.html", wait_until="load")
        seite.click(".gr-reiter button[data-tafel='tafel-katalog']")
        seite.wait_for_timeout(100)
        seite.eval_on_selector(".gr-reiter", "e => e.scrollIntoView({block:'start'})")
        seite.wait_for_timeout(100)
        yield seite
        seite.close()


def test_p1_die_erste_seite_zeigt_mindestens_drei_hersteller_an_echten_daten(
        _echte_seite):
    """Die Rueckweisung woertlich: an den echten Daten gemessen standen
    zwoelf sichtbare Zeilen fuer nur ZWEI Hersteller (iPhone 17 Pro x7,
    Fairphone 6 x5) - ein einzelner Geraeteblock fuellte mehr als die
    Haelfte der zwoelf sichtbaren Zeilen allein.

    ERST die Gegenprobe: die Datenlage muss den Fall ueberhaupt ausloesen
    koennen, sonst ist dieser Test wie die beiden vorigen grün, ohne etwas
    zu pruefen. Gemessen wird direkt gegen `katalogzeilen()` auf dem echten
    Bestand - keine Fixture, keine Erfindung.
    """
    from telco_radar.geraete_config import lade_katalog
    from telco_radar.analyze.geraete_store import (
        GeraeteDB, STATUS_AKTIV, STATUS_VERMUTLICH,
    )
    from telco_radar.report import geraete_view

    katalog = lade_katalog(REPO)
    db = GeraeteDB(REPO / "data" / "state" / "geraete_db.json")
    alle = db.eintraege()
    sichtbar_roh = [e for e in alle
                    if e.get("status") in (STATUS_AKTIV, STATUS_VERMUTLICH)]
    _pruefung, bestand, _belastbar = geraete_view.bestand_und_belastbar(
        sichtbar_roh, katalog)
    zeilen = geraete_view.katalogzeilen(bestand, katalog)

    from collections import Counter
    bloecke = Counter((z["hersteller"], z["modell"], z["speicher"]) for z in zeilen)
    groesster_block = max(bloecke.values())
    halbe_sichtflaeche = geraete_view.KATALOG_SICHTBAR / 2
    assert groesster_block > halbe_sichtflaeche, (
        f"die Datenlage kann den Fall nicht ausloesen - groesster Block "
        f"hat {groesster_block} Zeilen, das sind nicht mehr als die Haelfte "
        f"von {geraete_view.KATALOG_SICHTBAR} sichtbaren Zeilen. Dieser "
        "Test misst nichts, solange das nicht stimmt."
    )

    # JETZT die eigentliche Zusicherung, im echten Chromium auf den echten
    # Daten - genau der Ort, an dem der Coordinator den Fehler zweimal
    # gefunden hat, nachdem zwei synthetische Fixtures ihn verfehlten.
    marken = _echte_seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none')"
        "      .map(x => x.dataset.marke)")
    assert len(marken) > 0, "keine einzige Zeile sichtbar - der Test misst nichts"
    assert len(set(marken)) >= 3, (
        f"nur {len(set(marken))} Hersteller unter den {len(marken)} "
        f"sichtbaren Zeilen an den echten Daten: {sorted(set(marken))}")


def test_p1_kein_block_zeigt_mehr_als_zwei_zeilen_ohne_alle_anzeigen(_echte_seite):
    """Die Kehrseite derselben Rueckweisung: der Deckel darf die B6-Gruppierung
    nicht wieder aufloesen. Kein Geraet darf mehr als `BLOCK_SICHTBAR`
    Zeilen zeigen, bevor "alle anzeigen" gedrueckt wurde - unabhaengig
    davon, wie viele Farbvarianten es wirklich gibt."""
    from telco_radar.report import geraete_view
    from collections import Counter

    zeilen = _echte_seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none')"
        "      .map(x => x.dataset.sGeraet)")
    verteilung = Counter(zeilen)
    ueberschritten = {g: n for g, n in verteilung.items()
                      if n > geraete_view.BLOCK_SICHTBAR}
    assert not ueberschritten, (
        f"Geraete mit mehr als {geraete_view.BLOCK_SICHTBAR} sichtbaren "
        f"Zeilen ohne 'alle anzeigen': {ueberschritten}")


# --------------------------------------------------------------------------
# Der Bestpreis-Stempel (04.09.2026, idealo-Muster)
#
# Die Kachel "Niedrigster Preis" sagt, WIE tief es war. Der Stempel sagt,
# WANN - und das ist die einzige der beiden Auskuenfte, die nur das Bild
# geben kann.
# --------------------------------------------------------------------------

def _probe_mit_tiefpunkt(tage, tiefster: int):
    """Eine Reihe, deren billigster Tag feststeht - der an Position
    `tiefster`. Alle anderen Punkte liegen darueber."""
    return {
        "id": "probe", "label": "Probefall 128 GB", "hersteller": "Probe",
        "speicher": 128, "suchtext": "probefall", "min": 700, "max": 900,
        "anbieter": 1, "messpunkte": len(tage), "messtermine": len(tage),
        "tage": list(tage), "aktuell": [],
        "reihen": [{"anbieter": "o2", "farbe": "#217a3c", "eigen": False,
                    "punkte": [{"datum": t,
                                "preis": 700.0 if i == tiefster else 900.0}
                               for i, t in enumerate(tage)]}],
    }


def test_der_bestpreis_stempel_sitzt_auf_dem_billigsten_punkt(_eigene_seite):
    """Der Ring steht auf der PREISHOEHE des tiefsten Punktes.

    Die Y-Achse gehoert dem Preis - dieselbe Regel, an der die geloeschte
    Positionskarte gescheitert ist (Etiketten bis zu 235 px neben ihrem
    Punkt). Ein Stempel, der ein paar Pixel neben seinem Tiefpunkt sitzt,
    behauptet einen anderen Tag.
    """
    seite = _eigene_seite
    tage = list(_MESSTAGE)
    _stelle_daten(seite, _probe_mit_tiefpunkt(tage, tiefster=1))

    lage = seite.evaluate("""() => {
        const svg = document.querySelector('#gr-vbild svg');
        const ring = svg.querySelector('.gr-vbest');
        if (!ring) return null;
        // Der tiefste gezeichnete Punkt ist der mit dem GROESSTEN cy:
        // die SVG-Y-Achse zeigt nach unten, ein niedriger Preis liegt tief.
        const punkte = [...svg.querySelectorAll('circle.gr-vpunkt')]
            .map(c => ({ cx: +c.getAttribute('cx'), cy: +c.getAttribute('cy') }));
        const tief = punkte.reduce((a, b) => (b.cy > a.cy ? b : a));
        return { rx: +ring.getAttribute('cx'), ry: +ring.getAttribute('cy'),
                 px: tief.cx, py: tief.cy };
    }""")
    assert lage is not None, "es gibt einen Bestpreis-Stempel"
    assert abs(lage["ry"] - lage["py"]) < 0.5, (
        f"der Ring sitzt auf der Preishoehe des Tiefpunkts: {lage}")
    assert abs(lage["rx"] - lage["px"]) < 0.5, (
        f"und auf seinem Tag: {lage}")


def test_der_bestpreis_stempel_nennt_den_tag_und_nicht_den_preis(_eigene_seite):
    """Die Zahl steht schon in der Kachel "Niedrigster Preis".

    "Eine Zahl steht je Ort genau EINMAL" gilt auch dann, wenn die zweite
    Stelle ein SVG ist. Der Stempel traegt deshalb das DATUM; der Preis
    steht in seinem `title` und damit nicht auf der Seite.
    """
    seite = _eigene_seite
    tage = list(_MESSTAGE)
    _stelle_daten(seite, _probe_mit_tiefpunkt(tage, tiefster=1))

    text = seite.eval_on_selector("#gr-vbild .gr-vbestmarke",
                                  "e => e.textContent")
    assert "700" not in text and "€" not in text, (
        f"der Stempel wiederholt den Preis der Kachel nicht: {text!r}")
    # Der zweite Messtag der Fixture, in der Schreibweise der Seite.
    tag, monat = tage[1].split("-")[2], tage[1].split("-")[1]
    assert f"{int(tag)}.{int(monat)}." in text, (
        f"der Stempel nennt den billigsten Tag: {text!r} (erwartet {tage[1]})")


def test_ohne_preisunterschied_gibt_es_keinen_bestpreis_stempel(_eigene_seite):
    """Wenn jeder Punkt derselbe Preis ist, ist jeder der billigste.

    Ein Stempel behauptete dann einen Tiefpunkt, den es nicht gibt - und er
    stuende auf einem beliebigen der gleich hohen Tage. Die Gegenprobe steht
    im Test darueber: mit Unterschied gibt es ihn sehr wohl.
    """
    seite = _eigene_seite
    tage = list(_MESSTAGE)
    flach = _probe_mit_tiefpunkt(tage, tiefster=-1)
    for p in flach["reihen"][0]["punkte"]:
        p["preis"] = 900.0
    flach["min"] = flach["max"] = 900
    _stelle_daten(seite, flach)

    assert seite.eval_on_selector_all("#gr-vbild .gr-vbest",
                                      "e => e.length") == 0, (
        "eine flache Reihe bekommt keinen Bestpreis-Stempel")


@pytest.mark.parametrize("tiefster", range(len(_MESSTAGE)))
def test_der_bestpreis_stempel_bleibt_im_bild(_eigene_seite, tiefster):
    """Das Etikett bleibt in der Zeichenflaeche - an JEDER Lage des
    Tiefpunkts.

    JEDE, und das ist der Punkt. Die erste Fassung dieses Tests legte den
    Tiefpunkt nur auf den LETZTEN Tag; dort kippt das Etikett ohnehin, der
    Test mass also genau die Seite des `if`, die funktioniert. Auch zwei
    ausgesuchte Lagen reichen nicht: an dieser Fixture gemessen liegt der
    kritische Bereich zwischen zwei Messtagen, und welcher Tag ihn trifft,
    haengt am Zeitraster - eine Zahl, die sich mit dem naechsten
    Rasterschalter verschiebt.

    Die Breite wird deshalb GEMESSEN und nicht geschaetzt: die Marke ist im
    Chromium 114-118 px breit, die alte Schaetzung reservierte 78.
    """
    seite = _eigene_seite
    tage = list(_MESSTAGE)
    _stelle_daten(seite, _probe_mit_tiefpunkt(tage, tiefster=tiefster))

    lage = seite.evaluate("""() => {
        const svg = document.querySelector('#gr-vbild svg');
        const t = svg.querySelector('.gr-vbestmarke');
        if (!t) return null;
        const k = t.getBBox();
        return { links: k.x, rechts: k.x + k.width,
                 breite: svg.viewBox.baseVal.width };
    }""")
    if lage is None:
        # Faellt der Tiefpunkt im Wochenraster mit einem Nachbarn zusammen,
        # ist die Reihe flach und traegt zu Recht keinen Stempel.
        pytest.skip("in diesem Raster gibt es keinen eigenen Tiefpunkt")
    assert lage["links"] >= 0, f"das Etikett beginnt im Bild: {lage}"
    assert lage["rechts"] <= lage["breite"], (
        f"und endet darin: {lage}")


@pytest.mark.parametrize("tid", ["tafel-alarme", "tafel-katalog",
                                 "tafel-verlauf", "tafel-portfolio",
                                 "tafel-tco"])
def test_kein_reiter_rollt_auf_dem_telefon_waagerecht(_umgebung, tid):
    """Eine Seite, die waagerecht rollt, ist auf dem Telefon unbenutzbar.

    Die Regel steht seit dem Geraete-Neubau im Stylesheet ("Eine breite
    Tabelle rollt IN SICH, nie die ganze Seite") - geprueft hat sie
    niemand, und zwei Tabellen des TCO-Reiters hielten sie nicht: die
    Bereitschaftstabelle (vorbestehend seit Phase 6a) und die
    SIM-only-Referenzen. Gemessen schoben sie das Dokument auf einem
    390-px-Telefon auf 480 px.

    Der bestehende Hoehentest misst auf 1440 px und sieht das nicht; und
    `test_keine_seite_rollt_waagerecht` prueft die Seite im
    AUSGANGSzustand, in dem vier der fuenf Reiter ausgeblendet sind.
    Gemessen wird deshalb hier, Reiter fuer Reiter, im Telefonformat.
    """
    browser, url = _umgebung
    seite = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        seite.goto(url, wait_until="load")
        seite.click(f".gr-reiter button[data-tafel='{tid}']")
        seite.wait_for_timeout(80)
        breite = seite.evaluate("document.documentElement.scrollWidth")
        sichtbar = seite.evaluate("document.documentElement.clientWidth")
        assert breite <= sichtbar, f"{tid}: {breite} px statt {sichtbar} px"
    finally:
        seite.close()


def test_jede_breite_tabelle_liegt_in_ihrem_rollbehaelter(_seite):
    """Jede `.gr-ttab` sitzt in einem `.gr-scroll`.

    Der Breitentest darueber misst die WIRKUNG und ist damit an die
    Datenlage gebunden: eine Tabelle, die heute keine Zeilen hat, rendert
    nicht und kann nicht ueberlaufen. Genau daran ist die erste Fassung
    dieses Reiters vorbeigelaufen - die Leitzahl-Tabelle steht hinter
    `{% if geraete.tco.zeilen %}` und bekommt ihre Zeilen erst, wenn ein
    Adapter Buendel liefert (Phase 4).

    Dieser Test misst deshalb die REGEL statt ihrer Wirkung: er faellt auch
    dann, wenn jemand eine vierte Tabelle ohne Behaelter ergaenzt, und er
    faellt, bevor sie Daten hat.
    """
    tabellen = _seite.evaluate(
        """() => Array.from(document.querySelectorAll('table.gr-ttab'))
                     .map(t => ({klassen: t.className,
                                 drin: !!t.closest('.gr-scroll')}))""")
    # Ohne diese Zeile prueft der Test bei leerem Reiter nichts und ist
    # trotzdem gruen - dieselbe Falle wie der Lookup, der 0 von 7 traf.
    assert len(tabellen) >= 4, (
        f"die Fixture muss alle Tabellen des TCO-Reiters zeigen: {tabellen}")
    ohne = [t["klassen"] for t in tabellen if not t["drin"]]
    assert not ohne, f"Tabellen ohne Rollbehaelter: {ohne}"
