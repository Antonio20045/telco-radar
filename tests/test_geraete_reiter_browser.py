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

from test_geraete_zeitreihe_browser import waehle_modell
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
        # ZWEI ANBIETER ZU DEMSELBEN GERAET: `vf-1` und `o2-1` gehoeren
        # beide zur `device_id` mit Index 1 (siehe `_bestand`). Mit vier
        # verschiedenen Geraeten haette JEDES Modell nur einen Balken, G1
        # entstuende nach C.1 gar nicht - und der Browser-Test daneben
        # pruefte eine Grafik, die es nicht gibt.
        [("Vodafone", "vf-1"), ("o2", "o2-1"),
         ("Vodafone", "vf-3"), ("o2", "o2-3")])
]

_TCO = {"updated": "2026-09-04", "buendel": _TCO_BUENDEL,
        "sim_only": _TCO_REFERENZEN}

# DER TARIFBESTAND GEHOERT ZUR FIXTURE, seit die Leitzahl ueber die BINDUNG
# rechnet (Phase R): die Mindestlaufzeit des Tarifs steht in `tarife.jsonl`
# und in keiner Geraetenutzlast. Ohne diese Datei traegt jedes Buendel die
# Luecke "Tarifbindung", keine Karte ist belastbar - und die ganze
# Hauptansicht der Seite waere von keinem Browser-Test gedeckt. Dieselbe
# Falle wie das fehlende `geraete_tco.json` am 04.09.2026, eine Ebene
# weiter.
#
# Die Preisphase mit `bis_monat: 24` und die zweite ab 25 sind kein
# Beiwerk: an ihnen haengt die Zeile "ab Monat 25" (Katalog D).
_TARIFE = [
    # O1 (11.09.2026): `datenvolumen_gb` je Tarif (10 + 10*i verteilt die
    # 14 Tarife ueber alle drei Baender) - ohne Volumen hat kein Modell ein
    # Band und der Graph der Vergleichsansicht waere von keinem dieser
    # Tests gedeckt (derselbe Fixture-Fehler wie das fehlende
    # `geraete_tco.json` am 04.09.2026, eine Ebene weiter).
    {"anbieter": a, "name": f"{a} Tarif {i}", "tarif_id": f"{a.lower()}:tarif-{i}",
     "art": "mobilfunk", "grundgebuehr": 19.99 + i, "laufzeit_monate": 24,
     "datenvolumen_gb": 10 + i * 10,
     "preisphasen": [{"von_monat": 1, "bis_monat": 24, "betrag": 19.99 + i},
                     {"von_monat": 25, "bis_monat": None,
                      "betrag": 24.99 + i}],
     "dokument_url": f"https://example.de/pib/{a.lower()}-{i}",
     "abgerufen_am": "2026-09-04", "confidence": {}, "fundstellen": {}}
    for i, a in enumerate(["Vodafone", "o2"] * 7)
]


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


def _zeige_tafel(seite, tafel_id):
    """Wie ein Klick auf den Reiter-Knopf - ohne Knopf.

    BRIEF_FADEN (05.09.2026): "Preis- und TCO-Historie" und "Portfolio"
    haben ihren Knopf in `.gr-reiter` verloren (die Tafeln selbst bleiben
    im Dokument, sie sind nur nicht mehr verlinkt - PM entscheidet separat
    ueber ihr Schicksal). Diese Tests pruefen weiterhin den INHALT dieser
    Tafeln, unveraendert seit ihrem jeweiligen Bau; nur der Weg dorthin ist
    jetzt ein direkter DOM-Zugriff statt eines Klicks. Dieselbe Wirkung wie
    `app.js`s `zeige()`, nur ohne dessen Knopf-Referenz.
    """
    seite.evaluate(
        "(id) => { document.querySelectorAll('.gr-tafel').forEach("
        "e => e.classList.toggle('gr-tafel--aus', e.id !== id)); "
        "document.querySelectorAll('.gr-reiter button[data-tafel]').forEach("
        "b => b.setAttribute('aria-selected', "
        "b.getAttribute('data-tafel') === id ? 'true' : 'false')); }",
        tafel_id)


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
    _zeige_tafel(seite, "tafel-verlauf")
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
    # E2: die TCO-HISTORIE - ohne sie haette die Hauptansicht dieser
    # Fixture keine Zeitreihe (nur den Leer-Satz), und der Pflichtgrafik-
    # Test pruefte einen Leerzustand. Drei Messtage fuer die ersten zwei
    # Bündel des Bestands.
    _tco_historie = []
    for b in _TCO["buendel"][:2]:
        for tag, gesamt in (("2026-09-02", 1000.0), ("2026-09-03", 990.0),
                            ("2026-09-04", 980.0)):
            _tco_historie.append({**b, "datum": tag, "gesamt": gesamt})
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in _tco_historie) + "\n",
        encoding="utf-8")
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in _TARIFE) + "\n", encoding="utf-8")
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


def _sichtbare_zeilen(seite, wurzel="#tafel-tco"):
    """Was der Leser WIRKLICH sieht, nicht was das Attribut sagt.

    Die erste Fassung zaehlte `:not([hidden])`. Damit war sie blind fuer den
    Fehler, den sie haette finden sollen: eine Autorenregel schlaegt das
    `[hidden]{display:none}` des Browsers, und nach "alle anzeigen" standen
    weggefilterte Zeilen weiter in der Tabelle - Helfer sagte 10, der
    Browser zeigte 13.

    Seit O2 (11.09.2026) lebt die Alarmtabelle auf dem Wettbewerbs-Radar -
    die Wurzel ist deshalb ein Parameter ('#wr-alarme' dort).
    """
    return seite.eval_on_selector_all(
        f"{wurzel} .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none').length")


def _sichtbare_marken(seite, wurzel="#tafel-tco"):
    return seite.eval_on_selector_all(
        f"{wurzel} .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none')"
        "      .map(x => x.dataset.marke)")


# --------------------------------------------------------------------------
# Die drei Regeln, die ueber allem stehen
# --------------------------------------------------------------------------

def test_die_startansicht_traegt_genau_die_pflichtgrafik(_seite):
    """UMGEKEHRT SEIT PHASE R, dann UMGEKEHRT SEIT BRIEF_FADEN.

    Bis zum 04.09.2026 hiess diese Zusicherung "auf der Startansicht steht
    ueberhaupt kein Diagramm" - richtig, solange die Startansicht die
    Alarmtabelle war. Das Lastenheft drehte sie um (A3): die Hauptansicht
    IST die TCO-Sicht, und zwischen BRIEF_ZEITREIHE und BRIEF_FADEN standen
    hier ZWEI Grafiken (G0 und G1).

    BRIEF_FADEN (05.09.2026, Kriterium 1): G1 verlaesst DIESE Ansicht -
    G0 (die Zeitreihe) ist die einzige Grafik je Modellblock. G1s Rechnung
    bleibt im Code (`geraete_tco_grafik.balken()`, `m.svg`/`m.legende`
    werden weiterhin gefuellt) und ist ab jetzt in
    `tests/test_geraete_tco_hauptansicht.py` statisch geprueft - nur der
    Aufruf im Template ist geloescht.

    O1 (11.09.2026) dreht die Regel ein drittes Mal: G0 verlaesst die
    Vergleichsansicht ebenfalls (O4 bindet ihn im Verlaufs-Reiter wieder
    an) - der EINE Graph ist der HTML/CSS-Balken `.gr-hgraph`, und in der
    ganzen Tafel steht kein SVG mehr. Was BLEIBT, ist die Regel gegen die
    geloeschte Positionskarte: kein Bild mit allen Geraeten in einer
    Flaeche, keine gedrehten Etiketten.
    """
    # E2 dreht auch diese Zeile: die Zeitreihe IST ein SVG (Antonios
    # Graph-Entscheidung). Verboten bleibt jedes ANDERE SVG der Tafel -
    # G0 gehoert in den Verlaufs-Reiter, G1 ist ersatzlos gefallen.
    fremde = _seite.eval_on_selector_all(
        "#tafel-tco svg:not(.gr-zr)", "e => e.length")
    assert fremde == 0, f"{fremde} SVGs ausser der Zeitreihe in der Tafel"
    assert _seite.eval_on_selector_all(
        "#tafel-tco svg.gr-zr", "e => e.length") >= 1, \
        "die Zeitreihe des gewaehlten Modells steht nicht da"
    # Genau EIN sichtbares Bild: die breite und die schmale Variante
    # stehen im DOM, das Mediaquery zeigt eine (Spezifitaets-Falle, siehe
    # style.css) - ein zweites SICHTBARES waere der alte Panel-Stapel.
    sichtbar = _seite.eval_on_selector_all(
        "#tafel-tco svg.gr-zr", "e => e.filter(s => "
        "s.getBoundingClientRect().width > 0).length")
    assert sichtbar == 1, f"{sichtbar} sichtbare Graph-Bilder statt einem"
    # Kein Rest der geloeschten Preisgrafik.
    assert _seite.eval_on_selector_all(
        "#tafel-tco .gr-punkt, #tafel-tco .gr-etikett, #tafel-tco .gr-band",
        "e => e.length") == 0
    # O2 (11.09.2026): die Alarmtabelle ist AUS der Vergleichsansicht auf
    # den Wettbewerbs-Radar gezogen - hier steht keine `.gr-alarm`-Tabelle
    # mehr. Der flache Katalog in Reiter 2 teilt sich Aussehen und
    # Filterlogik weiterhin mit ihr (auf dem Radar), und genau das haelt
    # `test_wettbewerbsradar_alarme.py` am neuen Ort fest.
    assert _seite.eval_on_selector_all("#tafel-tco .gr-alarm",
                                       "e => e.length") == 0


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


@pytest.mark.parametrize("tid", ["tafel-tco"])
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
    # E2: die Meta-Etiketten des GENEHMIGTEN Zeitreihen-Prototyps (kleiner
    # Erst-Wert, "unser Angebot"-Chip, Abrufdatum am Linienende) stehen
    # bewusst bei 10-11 px - sie stuetzen, sie tragen keine Information
    # allein (Antonios Graph-Entscheidung schlaegt hier die alte Regel).
    zu_klein = _seite.evaluate(f"""() => Array.from(
        document.querySelectorAll('#{tid} *')).filter(el =>
          el.textContent.trim()
          && el.children.length === 0
          && !['gr-zr-chip', 'gr-zr-datum', 'gr-zr-wert--erst']
              .some(c => el.classList.contains(c))
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
    assert "…" not in _seite.eval_on_selector("#tafel-tco", "e => e.innerText")


# --------------------------------------------------------------------------
# Die Reiter
# --------------------------------------------------------------------------

def test_der_reiter_blendet_ohne_neuladen_um(_seite):
    """O3 (STRATEGIE_GERAETE_OPTIK §3): DREI klickbare Tafeln in
    `.gr-reiter` - der Verlaufs-Reiter ist zurück (die Einzelgerät-
    Zeitreihe war fertig gebaut und unerreichbar). Der vierte Eintrag ist
    der Radar-LINK; dass er KEIN Tab ist, hält der nächste Test."""
    for tid in ("tafel-katalog", "tafel-tco", "tafel-verlauf"):
        _seite.click(f".gr-reiter button[data-tafel='{tid}']")
        _seite.wait_for_timeout(60)
        sichtbar = _seite.eval_on_selector_all(
            ".gr-tafel:not(.gr-tafel--aus)", "e => e.map(x => x.id)")
        assert sichtbar == [tid], tid
        aktiv = _seite.eval_on_selector_all(
            ".gr-reiter button[aria-selected='true']",
            "e => e.map(x => x.getAttribute('data-tafel'))")
        assert aktiv == [tid], "genau ein Reiter ist ausgewaehlt"


def test_die_reiterleiste_traegt_vier_knoepfe_ohne_link(_seite):
    """E3 (§1d): vier echte Tafeln - der O3-Quasi-Reiter (Link auf
    wettbewerbsradar.html) ist der Tafel dieser Seite gewichen."""
    knoepfe = _seite.eval_on_selector_all(
        ".gr-reiter button[data-tafel]",
        "e => e.map(x => x.getAttribute('data-tafel'))")
    assert knoepfe == ["tafel-tco", "tafel-radar", "tafel-verlauf",
                       "tafel-katalog"]
    beschriftung = _seite.eval_on_selector_all(
        ".gr-reiter button", "e => e.map(x => x.textContent.trim())")
    assert beschriftung == ["Vergleich", "Radar", "Preisverlauf",
                            "Gerätekatalog"]
    links = _seite.eval_on_selector_all(
        ".gr-reiter a", "e => e.length")
    assert links == 0, "die Reiterleiste trägt noch einen Link (E3: Tafel)"
    _zeige_tafel(_seite, "tafel-tco")


def test_die_portfolio_tafel_ist_weg_der_verlauf_ist_verknuepft(_seite):
    """O3 (S4/§5.2): die zwei ehemaligen Waisen sind verschieden entschieden
    - `#tafel-verlauf` ist wieder verknüpft (lebendig), `#tafel-portfolio`
    ist GANZ weg (seine Abschnitte stehen auf dem Wettbewerbs-Radar)."""
    _seite.click(".gr-reiter button[data-tafel='tafel-verlauf']")
    _seite.wait_for_timeout(60)
    sichtbar = _seite.eval_on_selector_all(
        ".gr-tafel:not(.gr-tafel--aus)", "e => e.map(x => x.id)")
    assert sichtbar == ["tafel-verlauf"]

    assert _seite.evaluate(
        "() => !document.getElementById('tafel-portfolio')"), \
        "#tafel-portfolio steht noch auf der Geräteseite"
    _zeige_tafel(_seite, "tafel-tco")


@pytest.mark.parametrize("tid", ["tafel-tco", "tafel-radar", "tafel-katalog",
                                 "tafel-verlauf"])
def test_jeder_reiter_bleibt_unter_drei_bildschirmen(_seite, tid):
    """Der Auftrag: unter 3.000 px auf 1440 px Breite. Die alte Seite war
    18.412 px hoch.

    E3: die Radar-Tafel steht mit auf dieser Seite; ihr Platzhalter-
    Gerüst ist bewusst klein (der Inhalt montiert E3 Schritt 2)."""
    _zeige_tafel(_seite, tid)
    _seite.wait_for_timeout(60)
    hoehe = _seite.evaluate("document.documentElement.scrollHeight")
    assert hoehe < MAX_HOEHE, f"{tid}: {hoehe} px"


# --------------------------------------------------------------------------
# Filter, Suche, Aufklapper
# --------------------------------------------------------------------------

def _radar_url(seite):
    """Die Adresse des Radar-REITERS derselben Seite. Bis E3 Schritt 3
    (17.09.2026) war der Radar eine eigene Seite (wettbewerbsradar.html);
    seitdem ist deren Alt-URL eine Meta-Refresh-Weiterleitung, und die
    Tests gehen direkt aufs Ziel - der Hash schaltet den Reiter (app.js)."""
    return seite.url.rsplit("/", 1)[0] + "/geraete.html#tafel-radar"


def _frisch(seite):
    """Ein unberuehrter Ausgangszustand der GERAETESEITE.

    Die Fixture hat Modulgueltigkeit, und "alle anzeigen" ist eine Klasse an
    der Tabelle, die kein Filter zuruecknimmt. Ein Test, der danach laeuft,
    misst sonst eine Seite, die ein anderer aufgeklappt hat. Seit O2 kann
    dieselbe Seite auch die RADAR-Seite zeigen (die Alarmtests dort) -
    deshalb `goto` auf die volle Adresse statt `reload`, das trifft immer
    die richtige Seite.
    """
    seite.goto(seite.url.rsplit("/", 1)[0] + "/geraete.html",
               wait_until="load")
    seite.click(".gr-reiter button[data-tafel='tafel-tco']")
    seite.wait_for_timeout(60)


def _radar_frisch(seite):
    """Dasselbe fuer die RADAR-Tafel: die Alarmtabelle lebt seit E3 in
    deren erster Sektion; der Hash in der Adresse schaltet den Reiter
    (app.js `ausHash`), kein Klick noetig.

    P4/D1 (STRATEGIE_GERAETE_V3, 18.09.2026): die Alarmtabelle steht
    seit dem Design-Durchlauf IM AUFKLAPPER unter der Balkengrafik (die
    Frage des Reiters liest sich zuerst als Bild). Die Interaktions-
    tests oeffnen ihn HIER - select_option/fill/click warten auf
    sichtbare Felder, und der Aufklapper ist Teil des Lesewegs, kein
    Sonderzustand."""
    seite.goto(_radar_url(seite), wait_until="load")
    seite.wait_for_timeout(150)
    auf = seite.query_selector("#wr-alarme details.gr-auf:not([open])")
    if auf:
        auf.query_selector("summary").click()
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
    _radar_frisch(_seite)
    gesamt = _seite.eval_on_selector_all("#wr-alarme .gr-a-zeile", "e => e.length")
    assert gesamt > SICHTBAR_MAX, "die Fixture reisst den Deckel nicht"
    assert _sichtbare_zeilen(_seite, "#wr-alarme") == SICHTBAR_MAX
    assert _seite.query_selector("#gr-mehr") is not None


def test_der_markenfilter_laesst_nur_die_passende_zeile(_seite):
    """Zwei Geraete, zwei Hersteller - so trennt der Filter wirklich. Ein
    Fixture, in dem beide Marken ueberall vorkommen, koennte gruen sein,
    ohne dass der Filter etwas tut."""
    _radar_frisch(_seite)
    _seite.select_option("#wr-alarme [data-filter='marke']", "Samsung")
    _seite.wait_for_timeout(60)
    marken = _sichtbare_marken(_seite, "#wr-alarme")
    assert marken, "keine Zeile sichtbar - der Test misst nichts"
    assert set(marken) == {"Samsung"}, marken
    # Gegenprobe: ohne Filter sind BEIDE Marken da, sonst traefe der Filter
    # eine Fixture, die ohnehin nur Samsung kennt.
    _seite.select_option("#wr-alarme [data-filter='marke']", "")
    _seite.wait_for_timeout(60)
    assert set(_sichtbare_marken(_seite, "#wr-alarme")) == {"Apple", "Samsung"}


def test_ein_aktiver_filter_ist_rot_hinterlegt(_seite):
    """"Aktive Filter werden rot hinterlegt mit weisser Schrift." Sie
    veraendern, was darunter steht, und das muss man sehen, ohne die Auswahl
    zu lesen."""
    # Der eigene Ausgangszustand. Die erste Fassung verliess sich darauf,
    # dass der Test davor "Samsung" gewaehlt hatte - einzeln ausgefuehrt fiel
    # sie durch, und zwei Tests weiter unten steht der Kommentar, warum man
    # das nicht tut.
    _radar_frisch(_seite)
    _seite.select_option("#wr-alarme [data-filter='marke']", "Samsung")
    _seite.wait_for_timeout(60)
    an = _seite.eval_on_selector(
        "#wr-alarme [data-filter='marke']",
        "e => e.closest('label').classList.contains('gr-filter--an')")
    assert an is True
    farbe = _seite.eval_on_selector(
        "#wr-alarme [data-filter='marke']",
        "e => getComputedStyle(e.closest('label')).backgroundColor")
    assert farbe == "rgb(230, 0, 0)", farbe


def test_die_suche_grenzt_ein(_seite):
    _radar_frisch(_seite)
    # E3 (17.09.2026): zuerst "alle anzeigen" - sonst misst der Test den
    # DECKEL gegen die Treffer, nicht die Suche gegen den Bestand. Mit dem
    # Alarm-Deckel bei 12 war "vorher" zufaellig groesser als die Treffer-
    # zahl; seit E3 teilen sich drei Sektionen das Budget EINER Tafel und
    # der Deckel steht bei 5 - Suche und Deckel lieferten dann gleich viele
    # sichtbare Zeilen, und der Test pruefte nichts mehr.
    mehr = _seite.query_selector("#gr-mehr")
    if mehr:
        mehr.click()
        _seite.wait_for_timeout(60)
    vorher = _sichtbare_zeilen(_seite, "#wr-alarme")
    _seite.fill("#wr-alarme [data-filter='suche']", "medimax")
    _seite.wait_for_timeout(60)
    nachher = _sichtbare_zeilen(_seite, "#wr-alarme")
    assert 0 < nachher < vorher, (vorher, nachher)
    treffer = _seite.eval_on_selector_all(
        "#wr-alarme .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none')"
        "      .map(x => x.textContent.toLowerCase().includes('medimax'))")
    assert all(treffer), "eine Zeile ohne den Suchbegriff ist sichtbar"


def test_eine_leere_auswahl_zeigt_einen_satz_statt_einer_leeren_flaeche(_seite):
    """Der Befund vom 29.08.2026, im Browser gesehen und nicht im HTML: eine
    leere Tabelle ohne Erklaerung liest sich als kaputte Seite."""
    _radar_frisch(_seite)
    _seite.fill("#wr-alarme [data-filter='suche']", "gibtesnicht")
    _seite.wait_for_timeout(60)
    assert _sichtbare_zeilen(_seite, "#wr-alarme") == 0
    assert _seite.eval_on_selector("#wr-alarme .gr-a-leer", "e => !e.hidden") is True
    _seite.fill("#wr-alarme [data-filter='suche']", "")


def test_der_klick_auf_eine_zeile_zeigt_alle_anbieter(_seite):
    """Ohne Klick steht die Anbieterliste NICHT da - sonst waere die Tabelle
    dreimal so hoch."""
    # Der eigene Ausgangszustand, nicht der des vorigen Tests: ein Test, der
    # auf dem Aufraeumen eines anderen sitzt, faellt aus, sobald der andere
    # ausfaellt - und meldet dann etwas, das mit ihm nichts zu tun hat.
    _radar_frisch(_seite)
    zeile = "#wr-alarme .gr-a-zeile:not([hidden])"
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
    _radar_frisch(_seite)
    mehr = _seite.query_selector("#gr-mehr")
    if mehr is not None:
        mehr.click()
        _seite.wait_for_timeout(60)

    _seite.select_option("#wr-alarme [data-filter='marke']", "Samsung")
    _seite.wait_for_timeout(60)
    marken = _sichtbare_marken(_seite, "#wr-alarme")
    assert marken, "keine Zeile sichtbar - der Test misst nichts"
    assert set(marken) == {"Samsung"}, marken


def test_ein_aufklapper_verschwindet_mit_seiner_zeile(_seite):
    """Sonst haengt eine Anbieterliste unter einer Zeile, die nicht mehr da
    ist - dieselbe Kaskadenfalle wie eine Ebene darueber."""
    _radar_frisch(_seite)
    _seite.select_option("#wr-alarme [data-filter='marke']", "")
    _seite.fill("#wr-alarme [data-filter='suche']", "")
    _radar_frisch(_seite)
    zeile = "#wr-alarme .gr-a-zeile:not([hidden])"
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

    _seite.fill("#wr-alarme [data-filter='suche']", "gibtesnichtwirklich")
    _seite.wait_for_timeout(60)
    assert _seite.eval_on_selector(
        aufklapper, "e => getComputedStyle(e).display") == "none"
    _seite.fill("#wr-alarme [data-filter='suche']", "")


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
    _radar_frisch(_seite)
    rest = _seite.eval_on_selector_all(
        "#wr-alarme .gr-a-rest.gr-a-zeile", "e => e.length")
    assert rest, "die Fixture hat keine Zeilen hinter 'alle anzeigen'"
    suchwort = _seite.eval_on_selector(
        "#wr-alarme .gr-a-rest.gr-a-zeile .gr-a-modell",
        "e => e.textContent.trim()")
    _seite.fill("#wr-alarme [data-filter='suche']", suchwort)
    _seite.wait_for_timeout(60)
    assert _sichtbare_zeilen(_seite, "#wr-alarme") == 1, (
        "der einzige Treffer der Suche bleibt versteckt")
    assert _seite.eval_on_selector(
        "#wr-alarme .gr-a-leer", "e => getComputedStyle(e).display") == "none"
    gefundenes_modell = _seite.eval_on_selector(
        "#wr-alarme .gr-a-zeile:not([hidden]) .gr-a-modell",
        "e => e.textContent.trim()")
    assert gefundenes_modell == suchwort, (
        "die sichtbare Zeile ist nicht die gesuchte")
    _seite.fill("#wr-alarme [data-filter='suche']", "")


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
    # NICHT ueber `_frisch`, aber mit expliziter Adresse: die gemeinsame
    # Seite kann nach einem Alarmtest gerade die RADAR-Seite zeigen.
    _seite.goto(_seite.url.rsplit("/", 1)[0] + "/geraete.html",
                wait_until="load")
    _seite.wait_for_timeout(60)
    for tid in ("tafel-tco", "tafel-katalog",
                "tafel-verlauf", "tafel-portfolio"):
        _zeige_tafel(_seite, tid)
        _seite.wait_for_timeout(60)
        offen = _seite.eval_on_selector_all(
            f"#{tid} details[open]", "e => e.length")
        assert offen == 0, tid
    _zeige_tafel(_seite, "tafel-tco")


def test_die_seite_traegt_das_echte_abrufdatum(_seite):
    """Faellt der naechtliche Lauf zwei Wochen aus, sind die Preise zwei
    Wochen alt - die Seite darf trotzdem nicht den Berichtstag behaupten.
    Auf einer Seite, deren Verkaufsargument der Belegzwang ist, ist das die
    teuerste Sorte falscher Zahl.

    Die Zusicherung stand als Kommentar in `geraete_view`, ihr Test hing an
    der Legende der geloeschten Grafik - und war damit vom 30.08.2026 an
    unbelegt.

    Seit O2 (11.09.2026) leben die Datums an ZWEI Orten, und der Test
    haelt beide fest: die ALARMTABELLE (Listungs-Datum, in der Fixture der
    11.08.) traegt es weiterhin SICHTBAR (seit E3 Schritt 3 in der ersten
    Sektion des Radar-Reiters); die Buendel-Zeilen tragen ihres (4.09.) im
    Rechenweg-Aufklapper - der Test oeffnet die Klappen dafuer und nimmt
    sie danach zurueck, denn die Fixture hat Modulgueltigkeit und ein
    anderer Test misst `details[open] == 0`.
    """
    _radar_frisch(_seite)
    radar_text = _seite.eval_on_selector("#tafel-radar", "e => e.innerText")
    assert "11. August 2026" in radar_text, (
        "das Abrufdatum der Listungen fehlt auf dem Wettbewerbs-Radar")

    _frisch(_seite)
    _seite.evaluate("() => document.querySelectorAll("
                    "'#tafel-tco details').forEach(d => d.open = true)")
    text = _seite.eval_on_selector("body", "e => e.innerText")
    _seite.evaluate("() => document.querySelectorAll("
                    "'#tafel-tco details').forEach(d => d.open = false)")
    assert "4. September 2026" in text, (
        "das Abrufdatum der Bündel fehlt auf der Geräteseite")


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
    _zeige_tafel(seite, "tafel-verlauf")
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


def test_ohne_klick_steht_das_diagramm_des_ersten_geraets_da(_seite):
    """P2 (Antonio F4, 17.09.2026): Der Reiter beginnt mit einem Bild, nicht
    mit einem Satz. Ohne jeden Klick ist das ERSTE Gerät der Liste gewählt
    (nach Messtagen sortiert, das meistgemessene steht oben) - die alte
    B4-Regel „ohne Auswahl kein Diagramm" ist bewusst gekippt; sie schützte
    den Zustand, in dem über dem Wähler noch der feste G2-Marktgraph stand.
    Der Leer-Satz lebt weiter als Rückbau-Zustand beim Suchfeld-Tippen
    (siehe test_eine_neue_eingabe_raeumt_das_alte_diagramm_weg)."""
    _frisch(_seite)
    _zeige_tafel(_seite, "tafel-verlauf")
    _seite.wait_for_timeout(200)
    assert _seite.eval_on_selector_all("#gr-vbild svg", "e => e.length") == 1
    # Das vorausgewählte Gerät erreicht die Diagramm-Schwelle: die Fixture
    # legt sechs Messtage an, das erste der Liste ist damit zeichnungsfähig.
    punkte = _seite.eval_on_selector_all("#gr-vbild .gr-vpunkt", "e => e.length")
    assert punkte >= 4, f"Auto-Auswahl zeichnet nur {punkte} Punkte"
    # Das Suchfeld nennt das gezeichnete Gerät - sonst stünde ein Bild da,
    # ohne dass der Leser wüsste, wessen Preis er sieht.
    feldwert = _seite.eval_on_selector("#gr-vsuche", "e => e.value")
    assert feldwert, "das Suchfeld nennt das vorausgewählte Gerät nicht"
    assert _seite.eval_on_selector(
        "#gr-vleer", "e => getComputedStyle(e).display") == "none", (
        "mit Auto-Vorauswahl steht der Leer-Satz nicht im Ausgangszustand")


# SICHTBARKEIT, NICHT DAS ATTRIBUT (P4b, Re-Check 18.09.2026): die erste
# Fassung dieses Tests assertete `e.hidden` - und war gruen, waehrend die
# Leitzahl sichtbar stehenblieb, weil `.gr-leit{display:flex}` das
# Browser-[hidden] uebersteuerte. Ein Test, der die Zusicherung nicht
# wirklich prueft, prueft nichts (CLAUDE.md 6). Gemessen wird computed
# display UND Boxhoehe - das, was der Leser sieht.
_LEERZUSTAND_MESSUNG = """() => {
  const erg = {};
  for (const id of ['gr-vleit', 'gr-vkacheln']) {
    const e = document.getElementById(id);
    if (!e) { erg[id] = null; continue; }
    const st = getComputedStyle(e);
    const r = e.getBoundingClientRect();
    erg[id] = {display: st.display, hoehe: Math.round(r.height),
               sichtbar: st.display !== 'none' && r.height > 0};
  }
  return erg;
}"""


def test_die_leitzahl_und_die_kacheln_schweigen_in_beiden_leerzustaenden(_seite):
    """P4-Fix (Code-Prüfung 18.09., S2) + P4b (Re-Check, S1): die Leitzahl
    (#gr-vleit) ist die größte Zahl der Tafel - im Leerfall behauptete sie
    trotzdem weiter den Preis des VORHERIGEN Zustands („919,00 €" neben
    „Kein Gerät gefunden.", 81 px hoch), und die vier Kachelzahlen
    (Niedrigster/Höchster/Anbieter/Termine) standen ebenso da - fünf Zahlen
    von gestern in einer Tafel, die sagt, dass sie nichts findet. Beide
    Rückbau-Pfade (Suchfeld, leeres Zeitfenster) laufen in satzFuer(null)
    zusammen; app.js setzt hidden, und die globale Regel
    `[hidden]{display:none!important}` lässt es WIRKEN - deshalb misst
    dieser Test die Sichtbarkeit, nicht das Attribut. Der Gatter-Fall
    (kurze Reihe) bleibt dagegen SICHTBAR - gerade dort ist die Leitzahl
    die wichtigste Auskunft (D4)."""
    _frisch(_seite)
    _zeige_tafel(_seite, "tafel-verlauf")
    _seite.wait_for_timeout(200)
    # Gegenprobe: mit Auto-Vorauswahl sind Leitzahl UND Kacheln DA (sonst
    # misst der Test einen Leerzustand, der nie gefüllt war).
    anfang = _seite.evaluate(_LEERZUSTAND_MESSUNG)
    assert anfang["gr-vleit"] and anfang["gr-vleit"]["sichtbar"], (
        "Fixture-Voraussetzung: die Leitzahl steht im Ausgangszustand")
    assert anfang["gr-vkacheln"] and anfang["gr-vkacheln"]["sichtbar"], (
        "Fixture-Voraussetzung: die Kachelreihe steht im Ausgangszustand")

    # 1) Suchfeld ohne Treffer: Rückbau - Leitzahl und Kachelzahlen weg.
    _seite.fill("#gr-vsuche", "zzzz")
    _seite.wait_for_timeout(150)
    assert "Kein Gerät gefunden." in _seite.inner_text("#tafel-verlauf")
    weg = _seite.evaluate(_LEERZUSTAND_MESSUNG)
    assert not weg["gr-vleit"]["sichtbar"], (
        "unter 'Kein Gerät gefunden.' steht noch der Preis des vorherigen "
        f"Geräts (display:{weg['gr-vleit']['display']}, "
        f"{weg['gr-vleit']['hoehe']} px) - die größte Zahl der Tafel lügt")
    assert not weg["gr-vkacheln"]["sichtbar"], (
        "im Leerzustand stehen noch die Kachelzahlen des vorherigen "
        f"Geräts (display:{weg['gr-vkacheln']['display']}) - leer heißt leer")

    # 2) Leeres Zeitfenster: derselbe Rückbau über den anderen Pfad.
    _frisch(_seite)
    _zeige_tafel(_seite, "tafel-verlauf")
    _seite.wait_for_timeout(200)
    _seite.fill("#gr-vvon", "2027-01-01")
    _seite.wait_for_timeout(200)
    assert "keine Messpunkte" in _seite.inner_text("#tafel-verlauf")
    weg2 = _seite.evaluate(_LEERZUSTAND_MESSUNG)
    assert not weg2["gr-vleit"]["sichtbar"], (
        "im leeren Zeitfenster steht noch der alte Preis "
        f"(display:{weg2['gr-vleit']['display']}) - dieselbe Lüge über "
        "den zweiten Pfad")
    assert not weg2["gr-vkacheln"]["sichtbar"], (
        "im leeren Zeitfenster stehen noch die Kachelzahlen von gestern "
        f"(display:{weg2['gr-vkacheln']['display']})")


def test_ein_deep_link_schlaegt_die_auto_vorauswahl(_seite):
    """P2: `?modell=` hat Vorrang vor der Auto-Vorauswahl - der Deep-Link
    der Abweichungstafel und die Auto-Auswahl dürfen nicht zwei Geräte
    zeigen. Eine unbekannte id fällt still aufs erste Gerät zurück
    (derselbe Grundsatz wie beim Deep-Link des Vergleichs-Reiters)."""
    _frisch(_seite)
    _zeige_tafel(_seite, "tafel-verlauf")
    _seite.wait_for_timeout(150)
    geraete = _seite.eval_on_selector(
        "#gr-verlaufdaten",
        "e => JSON.parse(e.textContent).map(g => ({id: g.id, label: g.label}))")
    assert len(geraete) >= 2, "die Fixture braucht zwei waehlbare Geraete"
    letztes = geraete[-1]
    assert letztes["id"] != geraete[0]["id"], (
        "die Fixture legt nur ein Geraet an - der Test prueft nichts")

    _seite.goto(_seite.url.rsplit("/", 1)[0] +
                f"/geraete.html?modell={letztes['id']}",
                wait_until="load")
    _zeige_tafel(_seite, "tafel-verlauf")
    _seite.wait_for_timeout(200)
    assert _seite.eval_on_selector("#gr-vsuche", "e => e.value") \
        == letztes["label"], "der Deep-Link waehlt nicht sein Geraet"

    # Unbekannte id: still aufs erste Geraet, kein Bruch.
    _seite.goto(_seite.url.rsplit("/", 1)[0] +
                "/geraete.html?modell=gibtesnicht-999",
                wait_until="load")
    _zeige_tafel(_seite, "tafel-verlauf")
    _seite.wait_for_timeout(200)
    assert _seite.eval_on_selector("#gr-vsuche", "e => e.value") \
        == geraete[0]["label"], (
        "eine unbekannte id muss still aufs erste Geraet fallen")
    # Die module-weite Seite fuer die Folgetests zuruecklassen: ohne
    # Parameter, Vergleichs-Reiter aktiv (Ladezustand).
    _frisch(_seite)


def test_nach_der_auswahl_steht_genau_ein_diagramm_fuer_ein_geraet(_seite):
    _frisch(_seite)
    assert _waehle_geraet(_seite), "die Fixture liefert kein waehlbares Geraet"
    assert _seite.eval_on_selector_all("#gr-vbild svg", "e => e.length") == 1
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
    assert _seite.eval_on_selector_all("#gr-vbild svg", "e => e.length") == 0
    assert _seite.eval_on_selector(
        "#gr-vleer", "e => getComputedStyle(e).display") != "none"


def test_der_rueckbau_satz_steht_an_beiden_orten_gleich():
    """P2-Fix (Code-Prüfung S3-1, 17.09.2026): Der Rückbau-Satz entsteht
    ZWEIMAL - als initial hidden-Text der Vorlage und als `leer.textContent`
    in `app.js`, wenn das Tippen im Suchfeld die Auswahl löst. Zwei
    Umsetzungen derselben Sache laufen auseinander, ohne dass es ein Test
    merkt - dasselbe Muster wie beim Übersetzungs-Link
    (`test_die_beschriftung_ist_an_beiden_orten_dieselbe`). Der Text wird
    aus der VORLAGE ausgelesen und im JS gesucht, nicht hier wiederholt:
    eine dritte Kopie im Test wäre derselbe Fehler noch einmal."""
    vorlagen = REPO / "src" / "telco_radar" / "report" / "templates"
    template = (vorlagen / "geraete.html.j2").read_text(encoding="utf-8")
    js = (vorlagen / "app.js").read_text(encoding="utf-8")
    zeile = [z for z in template.splitlines() if 'id="gr-vleer"' in z]
    assert len(zeile) == 1, "die Vorlage trägt nicht genau eine gr-vleer-Zeile"
    treffer = re.search(r'id="gr-vleer"[^>]*>(.*?)</p>', zeile[0])
    assert treffer, "der Rückbau-Satz ließ sich nicht aus der Vorlage auslesen"
    text = treffer.group(1).strip()
    assert text, "der Rückbau-Satz ist leer"
    assert f"leer.textContent = '{text}'" in js, (
        f"app.js schreibt einen anderen Rückbau-Satz als die Vorlage "
        f"({text!r})")


def test_die_kurve_beginnt_im_ersten_viewport(_umgebung):
    """P2-Fix (Sicht-Prüfung 17.09.2026, der FAIL auf 390): Der Reiter soll
    mit dem Diagramm aufgehen (Antonio F4: den Modell-Wahl-Graphen GANZ
    OBEN). Vorher begann das SVG auf 390x844 bei 1008 px - 164 px unter der
    Falz -, weil h2 zweizeilig, die Von/Bis-Gruppe gestapelt und die
    Kacheln 2x2 standen. Messlatte wie beim Sicht-Prüfer: auf dem Telefon
    beginnt das SVG im ersten Viewport; auf dem Schirm beginnt dort schon
    die KURVE (Sicht-Prüfung 7.2: vorher 34 px Kurve, 866 px bei Falz 900).

    Gemessen wird der unberührte Anfangszustand: Reiter umgeblendet, an den
    Anfang gescrollt, keine weitere Eingabe."""
    browser, wurzel = _umgebung
    sichten = ((390, 844), (1440, 900))
    ergebnis = {}
    for breite, hoehe in sichten:
        s = browser.new_page(viewport={"width": breite, "height": hoehe})
        try:
            s.goto(wurzel, wait_until="load")
            s.wait_for_timeout(350)
            _zeige_tafel(s, "tafel-verlauf")
            s.wait_for_timeout(350)
            s.evaluate("window.scrollTo(0, 0)")
            ergebnis[breite] = s.evaluate("""() => {
                const bild = document.getElementById('gr-vbild');
                const svg = bild && bild.querySelector('svg');
                const kurve = bild && bild.querySelector('path');
                if (!svg || bild.hidden) return null;
                const dok = e => Math.round(
                    e.getBoundingClientRect().top + window.scrollY);
                return { svg: dok(svg),
                         kurve: kurve ? dok(kurve) : null,
                         punkte: bild.querySelectorAll('.gr-vpunkt').length };
            }""")
        finally:
            s.close()
    for breite, hoehe in sichten:
        mess = ergebnis[breite]
        assert mess, (
            f"{breite}: die Auto-Vorauswahl zeichnet kein Diagramm "
            f"(Fixture prüfen)")
        assert mess["punkte"] >= 4, f"{breite}: {mess}"
        assert mess["svg"] <= hoehe, (
            f"{breite}: das SVG beginnt {mess['svg'] - hoehe} px unter der "
            f"Falz - der Reiter öffnet wieder mit Gerüst statt Kurve")
        if breite == 1440:
            assert mess["kurve"] is not None and mess["kurve"] < hoehe, (
                f"1440: die erste Kurve beginnt erst bei {mess['kurve']} px "
                f"- unter der Falz {hoehe}")


def test_kein_kachelbetrag_bricht_um(_umgebung):
    """P2-Fix (Sicht-Prüfung 17.09., im AUGE gefunden): Seit die Kachelreihe
    NEBEN der Zeitraum-Steuer steht, ist eine Kachel auf dem Schirm 129 px
    (mobil 87 px) breit - der laengste Betrag des Bestands ("1.171,00 €")
    brach bei 24 px fett in die zweite Zeile und das "€" stand allein.
    Regel: ein Kachelbetrag ist EINZEILIG - ein Geldbetrag, der umbricht,
    ist keine Zahl mehr, sondern zwei Zeilen Text. Der Fall wird gestellt
    (die Standard-Fixture haelt ihre Preise dicht beieinander), gerechnet
    und gesetzt wird vom echten app.js."""
    browser, wurzel = _umgebung
    tage = list(_MESSTAGE)
    geraet = {
        "id": "probe", "label": "Probefall 128 GB", "hersteller": "Probe",
        "speicher": 128, "suchtext": "probefall", "min": 919, "max": 1171,
        "anbieter": 2, "messpunkte": 2 * len(tage), "messtermine": len(tage),
        "tage": tage, "aktuell": [],
        "reihen": [
            {"anbieter": "mobilcom-debitel", "farbe": "#2b5bd7",
             "eigen": False,
             "punkte": [{"datum": t, "preis": 1171.0} for t in tage]},
            {"anbieter": "Vodafone", "farbe": "#e60000", "eigen": True,
             "punkte": [{"datum": t, "preis": 919.0} for t in tage]},
        ]}
    for breite, hoehe in ((1440, 900), (390, 844)):
        s = browser.new_page(viewport={"width": breite, "height": hoehe})
        try:
            s.goto(wurzel, wait_until="load")
            s.wait_for_timeout(250)
            _stelle_daten(s, geraet)
            s.wait_for_timeout(250)
            lage = s.evaluate(
                """() => Array.from(document.querySelectorAll('.gr-vkachel b'))
                    .map(b => ({text: b.textContent,
                                hoehe: Math.round(
                                    b.getBoundingClientRect().height),
                                fs: parseFloat(
                                    getComputedStyle(b).fontSize)}))""")
            assert lage and any("1.171,00" in b["text"] for b in lage), (
                f"{breite}: der lange Betrag steht nicht in der Kachel: "
                f"{lage}")
            for b in lage:
                assert b["hoehe"] <= b["fs"] * 1.6, (
                    f"{breite}: {b['text']!r} ist {b['hoehe']} px hoch bei "
                    f"{b['fs']} px Schrift - der Betrag bricht um")
        finally:
            s.close()



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


def test_telekom_farbe_kommt_aus_der_einen_quelle_und_ist_magenta(
        _eigene_seite):
    """P2/D1, BEFUND: die alte HASH-PALETTE in `geraete_verlauf.py`
    (`md5(anbietername) % 7`) traf fuer 'Telekom' auf `#217a3c` (Gruen) -
    die Telekom stand gruen im Preisverlauf, waehrend dieselbe Telekom in
    der TCO-Zeitreihe (`geraete_zeitreihe.ANB_FARBE`) magenta war.

    Die Farbe der REIHEN kommt hier aus der ECHTEN Funktion
    (`geraete_verlauf._reihen`, die jetzt `anbieter_farben.stil_fuer()`
    liest) - kein Wert wird in diesem Test von Hand behauptet. Gemessen
    wird die COMPUTED color im echten Chromium, nicht die Zeichenkette im
    Quelltext: eine computed color kann durch eine CSS-Regel ueberschrieben
    sein, die ein reiner String-Vergleich nie saehe. Der Selektor
    `.gr-anb--telekom` prueft zugleich, dass `app.js` die Anbieterklasse
    wirklich an die Linie haengt (P2/D1 in `app.js`)."""
    from telco_radar.report import geraete_verlauf as verlauf

    tage = list(_MESSTAGE)
    punkte = []
    for i, t in enumerate(tage):
        punkte.append({"datum": t, "anbieter": "Telekom",
                       "preis": 600.0 + i, "art": "gemessen"})
        punkte.append({"datum": t, "anbieter": "Vodafone",
                       "preis": 650.0 - i, "art": "gemessen"})
    reihen = verlauf._reihen(punkte)
    telekom = next(r for r in reihen if r["anbieter"] == "Telekom")
    assert telekom["farbe"] == "#e20074", (
        "die EINE Quelle liefert nicht die erwartete Markenfarbe: "
        + telekom["farbe"])
    assert telekom["slug"] == "telekom"

    seite = _eigene_seite
    _stelle_daten(seite, {
        "id": "probe-telekom", "label": "Farbprobe 128 GB",
        "hersteller": "Probe", "speicher": 128, "suchtext": "farbprobe",
        "min": 500, "max": 700, "anbieter": len(reihen),
        "messpunkte": len(punkte), "messtermine": len(tage),
        "tage": tage, "aktuell": [], "reihen": reihen})

    farbe = seite.eval_on_selector(
        "#gr-vbild path.gr-vlinie.gr-anb--telekom",
        "e => getComputedStyle(e).stroke")
    assert farbe == "rgb(226, 0, 116)", farbe
    assert farbe != "rgb(33, 122, 60)", (
        "das ist die alte Hash-Gruen-Farbe #217a3c - der Bug ist zurueck")


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
    ("wr-alarme", "euro", "sEuro"),
    ("wr-alarme", "prozent", "sProzent"),
    ("tafel-katalog", "preis", "sPreis"),
])
def test_ein_klick_auf_den_spaltenkopf_sortiert_nach_dem_rohwert(
        _seite, tafel, knopf, schluessel):
    """"Bei acht Spalten und 24 Zeilen ist Sortieren nach Euro-Abstand statt
    Prozent die erste Frage, die jemand hat."

    Sortiert wird nach dem ROHWERT an der Zeile, nicht nach dem Zelltext:
    "1.099,90 €" ist als Zeichenkette kleiner als "199,00 €", und ein
    Sortierer, der die Zelle liest, stellt den teuersten Preis nach vorn und
    sieht dabei richtig aus.

    Seit O2 (11.09.2026) lebt die Alarmtabelle auf dem Wettbewerbs-Radar
    ('wr-alarme'); der Katalog bleibt auf der Geraeteseite."""
    if tafel == "wr-alarme":
        _radar_frisch(_seite)
    else:
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
    _radar_frisch(_seite)

    def sichtbar(schluessel):
        return _seite.eval_on_selector_all(
            "#wr-alarme .gr-a-zeile",
            "(e, k) => e.filter(x => getComputedStyle(x).display !== 'none')"
            "           .map(x => parseFloat(x.dataset[k]))", schluessel)

    def alle(schluessel):
        return _seite.eval_on_selector_all(
            "#wr-alarme .gr-a-zeile",
            "(e, k) => e.map(x => parseFloat(x.dataset[k]))", schluessel)

    # Gegenprobe: der Deckel muss ueberhaupt greifen, sonst ist der Fall
    # nicht ausloesbar und der Test gruen ohne Aussage.
    assert len(sichtbar("sEuro")) < len(alle("sEuro")), (
        "kein Deckel aktiv - dann prueft dieser Test nichts")
    # Und die zwei Ordnungen muessen sich unterscheiden.
    nach_prozent = sorted(alle("sProzent"), reverse=True)
    assert nach_prozent != sorted(alle("sEuro"), reverse=True), (
        "Prozent und Euro ordnen gleich - der Fall ist nicht ausloesbar")

    _seite.click('#wr-alarme .gr-sort[data-sort="euro"]')
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


def test_der_ansichtsregler_steht_von_anfang_an_auf_barpreis(_b5_seite):
    """P3-Nachfolger des Zustandsfilters ("steht von Anfang an auf neu"):
    der Zustands-<select> ist mit der Listungs-Tabelle entfallen - seine
    Zusicherung (die zuerst gezeigten Preise sind NEU-Preise) ist seit C1
    in der AGGREGATION verankert (`barpreise()` laeuft nur ueber
    VERGLEICHBARE_ZUSTAENDE, B1). Die Steuerung, die jetzt eine Vorbelegung
    hat, ist der ANSICHTS-Umschalter: Einzelgerätpreis ist aktiv, ohne
    dass jemand klickt - ein geteilter Link soll die Grundfrage zeigen."""
    seite = _b5_frisch(_b5_seite)
    zustaende = seite.eval_on_selector_all(
        "#tafel-katalog .gr-kansicht button[data-ansicht]",
        "e => e.map(k => ({ansicht: k.dataset.ansicht,"
        "                  aktiv: k.classList.contains('is-aktiv'),"
        "                  gedrueckt: k.getAttribute('aria-pressed')}))")
    assert {z["ansicht"] for z in zustaende} == {"barpreis", "tco"}, zustaende
    aktive = [z for z in zustaende if z["aktiv"]]
    assert len(aktive) == 1 and aktive[0]["ansicht"] == "barpreis", zustaende
    assert aktive[0]["gedrueckt"] == "true", zustaende
    # Die Tabelle steht auf Barpreis: die Barpreis-Spalten sind sichtbar,
    # die TCO-Spalten nicht (die Umschaltung passiert ueber die Klasse
    # `gr-katalog--tco`, kein Reload, kein zweites Rendering). Gemessen an
    # den ZELLEN der ersten Modellzeile (`z.cells`) - ein td-Selektor
    # griffe auch in die geschlossenen Aufklapper-Tabellen hinein, deren
    # Zellen tragen ihre eigene display-Eigenschaft weiter.
    sichtbar = seite.eval_on_selector(
        "#gr-katalogtabelle .gr-k-zeile",
        "z => Array.from(z.cells)"
        "      .map(c => getComputedStyle(c).display !== 'none')")
    assert sichtbar[:4] == [True, True, True, True], sichtbar
    assert not any(sichtbar[4:]), sichtbar


def test_die_vorbelegung_versteckt_serverseitig_keine_zeile(_b5_seite):
    """Der Fehler vom 30.08. (Commit 79085f0): drei Zahlen liefen
    auseinander, weil eine Vorbelegung Zeilen per JS versteckte, die
    Ueberschrift und der "alle anzeigen"-Knopf aber weiterhin die volle
    Zahl nannten. Diese Fassung filtert serverseitig nichts heraus - die
    Gegenprobe: die Zahl der MODELLZEILEN IM DOM (versteckt oder nicht)
    ist exakt die Modellzahl des Bestands, unabhaengig von Filterwahl
    oder Ansicht. (Bis P3 zaehlte dieser Test Listungszeilen.)"""
    seite = _b5_frisch(_b5_seite)
    anzahl = seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-k-zeile", "e => e.length")
    assert anzahl == _b5_modellzahl(), (
        f"{anzahl} Modellzeilen im DOM, erwartet {_b5_modellzahl()}")
    ueberschrift = seite.text_content(".gr-katalog h2 .rubrik-zahl").strip()
    assert ueberschrift == str(_b5_modellzahl()), ueberschrift


# Die MESSREGEL des Rot-Deckels (P4b, Re-Check 18.09.2026). Bis hierhin war
# der Deckel nirgends als Regel genagelt - deshalb konnten fix.md („Katalog
# 5") und die Realitaet (12 vollrote Elemente) auseinanderlaufen, ohne dass
# ein Test es meldete. Die Ursache des Falls: `.src-table a{color:var(--red)}`
# (Spezifitaet 0-1-1) schlug `.gr-sprung` (0-1-0) - elf Sprung-Links standen
# VOLLROT da, obwohl die P4-Regel „grau, Rot erst im Hover" im Stylesheet
# stand. Gezaehlt wird am GERENDERTEN Katalog (computed styles, echte
# Chromium-Rechnung), der Farbwert aus der CSS-Konstante gelesen - ein
# hardcoded rgb(230,0,0) wuerde mit einer Umbenennung der Konstanten still
# verrosten.
_ROT_ZAEHLER = """() => {
  const probe = document.createElement('span');
  probe.style.color = 'var(--red)';
  document.body.appendChild(probe);
  const rot = getComputedStyle(probe).color;
  probe.remove();
  const tafel = document.getElementById('tafel-katalog');
  const vollrot = [];
  for (const el of tafel.querySelectorAll('*')) {
    if (el.closest('svg') || el.closest('template')) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const st = getComputedStyle(el);
    const eltern = el.parentElement ? getComputedStyle(el.parentElement) : null;
    // EIGENES Rot: die Farbe weicht vom Elternelement ab - sonst zaehlte
    // jedes Kind eines roten Links ein zweites Mal.
    const farbe = st.color === rot && (!eltern || eltern.color !== rot);
    const flaeche = st.backgroundColor === rot;
    const rand = ['borderTopColor', 'borderBottomColor',
                  'borderLeftColor', 'borderRightColor'].some(
      p => st[p] === rot && parseFloat(st[p.replace('Color', 'Width')]) > 0);
    if (farbe || flaeche || rand)
      vollrot.push({tag: el.tagName, klasse: String(el.className).slice(0, 40),
                    text: el.textContent.replace(/\\s+/g, ' ').trim().slice(0, 30)});
  }
  return {rot, n: vollrot.length, elemente: vollrot};
}"""


def test_der_rotdeckel_des_katalogs_ist_eine_messregel(_seite):
    """Initial stehen HOECHSTENS ZEHN vollrot eingefaerbte Elemente im
    Katalog (Re-Check 18.09.: 12 - elf rote Sprung-Links plus aktiver
    Knopf). Die Regel: eigenes Rot in Farbe, Flaeche ODER Rand, Farbwert
    aus var(--red) gelesen, ohne SVG (Vodafone-Datenfarbe zaehlt nicht),
    ohne template, nur gerenderte Elemente, Links gezaehlt wie jedes
    Element. Dazu die konkrete Entsättigung: die Sprung-Links sind
    NAVIGATION, kein Befund - sie stehen grau, Rot erst im Hover."""
    _frisch(_seite)
    _zeige_tafel(_seite, "tafel-katalog")
    _seite.wait_for_timeout(150)
    # Fixture-Wache: ohne Sprung-Links pruefte der zweite Assert nichts
    # (die Entsättigung ist an genau dieser Link-Klasse gebunden).
    spruenge = _seite.eval_on_selector_all(
        "#gr-katalogtabelle a.gr-sprung", "e => e.length")
    assert spruenge >= 1, "kein gr-sprung im Katalog der Fixture"
    # Gegenprobe des Zaehlers selbst: ein gestellt rotes Element muss
    # gezaehlt werden - sonst zaehlte die Regel still nichts (derselbe
    # Grundsatz wie beim Lookup ins Leere: gruen waere beweislos).
    _seite.evaluate(
        """() => {
          const tafel = document.getElementById('tafel-katalog');
          const k = document.createElement('span');
          k.dataset.rotprobe = '1';
          k.style.color = 'var(--red)';
          k.textContent = 'gegenprobe';
          tafel.appendChild(k);
        }""")
    mit_probe = _seite.evaluate(_ROT_ZAEHLER)
    assert any(e["klasse"] == "" and "gegenprobe" in e["text"]
               for e in mit_probe["elemente"]), (
        "der Rot-Zaehler zaehlt kein gestellt rotes Element - er misst "
        "nichts")
    _seite.evaluate(
        "() => document.querySelector('#tafel-katalog [data-rotprobe]')"
        ".remove()")
    # Die eigentlichen Zusicherungen (ohne das Gegenprobe-Element).
    erg = _seite.evaluate(_ROT_ZAEHLER)
    assert not any("gegenprobe" in e["text"] for e in erg["elemente"]), (
        "die Gegenprobe klebt noch in der Tafel")
    rot = _seite.eval_on_selector(
        "#gr-katalogtabelle a.gr-sprung", "e => getComputedStyle(e).color")
    assert rot != erg["rot"], (
        f"Sprung-Link steht VOLLROT ({rot}) - Navigation ist kein Befund; "
        "die P4-Regel 'grau, Rot erst im Hover' wird von .src-table a "
        "uebersteuert")
    assert erg["n"] <= 10, (
        f"{erg['n']} vollrote Elemente im initialen Katalog (Deckel 10): "
        f"{erg['elemente'][:6]}")


# --------------------------------------------------------------------------
# B2/B3 der Zurueckweisung (31.08.2026): der Deckel folgt der Sortierung,
# nicht der Position. Seit P3 wird nach der MODELLZEILE sortiert (Bis-P3:
# Spalte "Zustand" der Listungstabelle) - der Reproduktionskern bleibt:
# zwei Klicks auf einen Spaltenkopf, der Deckel darf nicht kollabieren,
# und der "alle anzeigen"-Knopf liefert seine genannte Zahl.
# --------------------------------------------------------------------------

def _b5_modellzahl() -> int:
    """Die Modellzahl der B5-Fixture, ALS ERWARTUNG ausgeschrieben:

    4 Hersteller x 7 Modelle = 28 (device, 256 GB)-Paare. Die drei
    refurbished-Zeilen liegen auf drei schon vorhandenen Paaren (Modell 1
    je Apple/Samsung/Xiaomi) und aendern die Modellzahl nicht - genau das
    ist der Unterschied, den dieser Testsatz seit P3 gegen Listungs-
    zaehlungen (31) haelt."""
    return 28


def test_b2_zwei_sortierklicks_lassen_den_deckel_nicht_kollabieren(_b5_seite):
    """B2: "Zwei Klicks auf den Spaltenkopf Zustand" liessen elf
    nicht-passende Zeilen in den Deckel rutschen, waehrend die passenden
    dahinter verschwanden - sichtbar fiel von zwoelf auf eins.

    Seit P3 heisst die (jetzt einzige) Preisspalte "Einzelgerätepreis"
    (`data-sort="preis"`); sortiert wird die Modellzeile. Zwei Klicks
    deckeln nicht: nach AUF- wie nach ABSTEIGEND bleibt die Zahl der
    sichtbaren Zeilen genau der Deckel.

    Gegengeprueft per Hand: in `app.js` `deckel > 0 && !alleZeigen` durch
    `false` ersetzt (der Deckel greift nie), dieser Test faellt (sichtbar
    > deckel statt ==).
    """
    from telco_radar.report.geraete_view import KATALOG_SICHTBAR
    seite = _b5_frisch(_b5_seite)
    for _ in range(2):
        seite.click('#gr-katalogtabelle .gr-sort[data-sort="preis"]')
        seite.wait_for_timeout(120)
        sichtbar = seite.eval_on_selector_all(
            "#gr-katalogtabelle .gr-a-zeile",
            "e => e.filter(x => getComputedStyle(x).display !== 'none')"
            "      .length")
        erwartet = min(KATALOG_SICHTBAR, _b5_modellzahl())
        assert sichtbar == erwartet, (
            f"{sichtbar} sichtbar nach Sortierklicks, erwartet {erwartet}")


def test_b3_alle_anzeigen_liefert_was_der_knopf_verspricht(_b5_seite):
    """B3: der Knopf versprach "alle 360 zeigen", lieferte 349 - die im
    Knopf genannte Zahl und die nach dem Klick sichtbare muessen
    uebereinstimmen, unabhaengig vom aktiven Filter.

    Seit P3 verspricht der Knopf MODELLZEILEN (28), nicht Listungen (31)
    - die drei refurbished-Zeilen stehen im AUFKLAPPER ihrer Modelle und
    zaehlen nicht als eigene Zeilen.

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
    assert versprochen == _b5_modellzahl(), (
        "der Knopf verspricht nicht die Zahl der MODELLZEILEN: "
        f"{versprochen} != {_b5_modellzahl()}")



# --------------------------------------------------------------------------
# B4/B5/B7 der Zurueckweisung (31.08.2026): der Quelllink im Anker - auf
# der grossen, gemeinsamen Fixture (`_seite`), nicht auf der B5-eigenen:
# diese drei Zusicherungen sind unabhaengig von Herstellervielfalt oder
# Filterzustand und gelten fuer BEIDE Tabellen des echten Bestands.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tafel,anker", [
    ("wr-alarme", "#wr-alarme .gr-a-quelle"),
    # P3: die ANBIETERZELLE des Katalogs lebt im Zeilen-Aufklapper
    # (`gr-k-listungen`) - in der Haupttabelle ist der Anker Teil der
    # PREISzelle ("ab X € bei Y↗"), dort steht der Betrag vor dem Anker,
    # was keine Rueckabwicklung ist (dafuer der eigene Test darunter).
    ("tafel-katalog", "#tafel-katalog .gr-k-listungen .gr-a-quelle"),
])
def test_b7_der_anbietername_liegt_im_anker(_seite, tafel, anker):
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
    if tafel == "wr-alarme":
        _radar_frisch(_seite)
    else:
        _frisch(_seite)
        _seite.click(f".gr-reiter button[data-tafel='{tafel}']")
        _seite.wait_for_timeout(80)
    ergebnis = _seite.eval_on_selector(anker, """
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


def test_p3_der_anker_der_modellzeile_traegt_den_haendlernamen(_seite):
    """B7 auf der MODELLZEILE des P3-Katalogs: dort steht der Anker in der
    PREISzelle ("ab 1.179,00 € bei Saturn↗") - der Text davor ist der
    BETRAG, und der Haendlername muss IM Anker stehen. Waere er unverbunden
    daneben gesetzt ("ab X € Saturn↗-Link"), waere der Name wieder nur zum
    Teil klickbar - derselbe Befund, eine Vorlage hoher."""
    _frisch(_seite)
    _seite.click(".gr-reiter button[data-tafel='tafel-katalog']")
    _seite.wait_for_timeout(80)
    ergebnisse = _seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-k-zeile td .gr-a-quelle", """
      (anker) => anker.map(a => ({
        ankerText: a.textContent.trim(),
        href: a.getAttribute('href'),
        zelle: a.closest('td').textContent.trim()
      }))
    """)
    assert ergebnisse, "keine belegten Modellzeilen-Anker in der Fixture"
    for e in ergebnisse:
        # Whitespace normalisieren: zwischen "bei" und dem Namen steht die
        # Jinja-Einrueckung im Markup - fuer den LESER ist das ein Leer-
        # zeichen, fuer textContent ein Zeilenumbruch.
        anker = " ".join(e["ankerText"].split())
        assert anker.startswith("bei ") and len(anker) > len("bei "), (
            f"der Anker nennt den Haendler nicht beim Namen: {anker!r}")
        assert e["href"] and e["href"] != "#", (
            f"Modellzeilen-Anker ohne Ziel: {e!r}")
        # Der BETRAG steht in derselben Zelle (vor dem Anker) - die Zeile
        # zeigt Preis UND Haendler zusammen, beide belegt.
        assert "€" in e["zelle"], e["zelle"]


@pytest.mark.parametrize("tafel", ["wr-alarme", "tafel-katalog"])
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
    if tafel == "wr-alarme":
        _radar_frisch(_seite)
    else:
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


@pytest.mark.parametrize("tafel", ["wr-alarme", "tafel-katalog"])
def test_b5_enter_auf_dem_fokussierten_quelllink_wird_nicht_verhindert(_seite, tafel):
    """B5: der `keydown`-Handler auf der Zeile rief fuer Enter/Space
    `preventDefault()` auf ALLEM innerhalb `.gr-a-zeile` auf - ohne den
    `closest('a')`-Ausstieg, den der `click`-Handler daneben hat. Ein
    fokussierter Quelllink war damit per Tastatur nicht auszuloesen.

    Gegengeprueft per Hand: den `closest('a')`-Ausstieg im
    `keydown`-Handler in `app.js` entfernt, dieser Test faellt
    (`defaultPrevented` wird `true`).
    """
    if tafel == "wr-alarme":
        _radar_frisch(_seite)
    else:
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
    zu pruefen. Gemessen wird direkt gegen `katalog_modellzeilen()` auf
    dem echten Bestand - keine Fixture, keine Erfindung. Seit P3 ist der
    Fall eine Aussage ueber die MODELLZAHL JE HERSTELLER: ohne das Reihum
    wuerde der Hersteller mit den meisten Modellen die sichtbaren
    Modellzeilen allein fuellen.
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
    modelle = geraete_view.katalog_modellzeilen(bestand, katalog)

    from collections import Counter
    je_hersteller = Counter(m["hersteller"] for m in modelle)
    groesster = max(je_hersteller.values())
    halbe_sichtflaeche = geraete_view.KATALOG_SICHTBAR / 2
    assert groesster > halbe_sichtflaeche, (
        f"die Datenlage kann den Fall nicht ausloesen - der staerkste "
        f"Hersteller hat {groesster} Modelle, das sind nicht mehr als die "
        f"Haelfte von {geraete_view.KATALOG_SICHTBAR} sichtbaren Zeilen. "
        "Dieser Test misst nichts, solange das nicht stimmt."
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


def test_p1_der_deckel_zaehlt_modelle_ohne_alle_anzeigen(_echte_seite):
    """P3-Nachfolger von "kein Block zeigt mehr als zwei Zeilen": der
    BLOCK-Deckel (`BLOCK_SICHTBAR`) ist mit der Listungs-Tabelle entfallen
    - ein Modell IST jetzt eine Zeile, seine Farb- und Anbieter-Varianten
    stehen komplett im Aufklapper. Was bleibt, ist die Kehrseite des
    Deckels an echten Daten: ohne "alle anzeigen" sind hoechstens
    `KATALOG_SICHTBAR` MODELLZEILEN sichtbar - unabhaengig davon, wie
    voll das Regal eines Herstellers ist (111 Modelle im echten Bestand)."""
    from telco_radar.report import geraete_view

    zeilen = _echte_seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-a-zeile",
        "e => e.filter(x => getComputedStyle(x).display !== 'none')"
        "      .map(x => x.dataset.sGeraet)")
    assert zeilen, "keine Zeile sichtbar - der Test misst nichts"
    assert len(zeilen) <= geraete_view.KATALOG_SICHTBAR, (
        f"{len(zeilen)} sichtbare Modellzeilen ohne 'alle anzeigen', "
        f"Deckel ist {geraete_view.KATALOG_SICHTBAR}")
    # Und es sind MODELLZEILEN, keine Listungen: kein Geraet-Speicher-Paar
    # kommt zweimal vor (die 24 Zeilen des iPhone 17 Pro haetten bis P3
    # als 24 Zeilen gezaehlt).
    from collections import Counter
    doppel = {g: n for g, n in Counter(zeilen).items() if n > 1}
    assert not doppel, f"Modelle mit mehr als einer Zeile: {doppel}"


def test_p3_wertlose_sortierung_steht_unten_nicht_oben(_seite):
    """P3/C2-Empfehlung: der Katalog der Modellebene hat BENANNTE
    Leerwerte (62 von 111 Modellen ohne wesentliche Spanne, 19 ohne
    Bündel) - `parseFloat("")` ist NaN, und die Sortierung schob NaN
    aufsteigend an den ANFANG. Eine Zeile OHNE Spanne steht seit dem
    C2-Fix in BEIDEN Richtungen unter den Zeilen mit Wert.

    Die `_seite`-Fixture spannt den Mix auf: ihre 20 Modelle haben
    Abstaende von 5 bis rund 216 EUR - der kleinste liegt unter der
    Wesentlichkeits-Schwelle (3 % / 15 EUR, ODER-Verknuepfung) und traegt
    KEINE Spanne, die grossen eine. Die spannenlosen Modelle liegen hinten
    und unterm Deckel - deshalb wird zuerst "alle anzeigen" geklickt,
    sonst misst der Test nur die gefuellten. Sortiert wird die Spannen-
    Spalte, auf- und absteigend."""
    _frisch(_seite)
    _seite.click(".gr-reiter button[data-tafel='tafel-katalog']")
    _seite.wait_for_timeout(80)
    _seite.click("#gr-kmehr")
    _seite.wait_for_timeout(120)
    for _ in range(2):  # 1. Klick: absteigend, 2. Klick: aufsteigend
        _seite.click('#gr-katalogtabelle .gr-sort[data-sort="spanne"]')
        _seite.wait_for_timeout(120)
        lage = _seite.eval_on_selector_all(
            "#gr-katalogtabelle .gr-a-zeile", """
            (zeilen) => {
              var sichtbar = zeilen.filter(
                z => getComputedStyle(z).display !== 'none');
              var werte = sichtbar.map(z => z.getAttribute('data-s-spanne'));
              var erste_leere = werte.indexOf('');
              var letzte_wert = -1;
              werte.forEach(function (w, i) {
                if (w !== '') letzte_wert = i;
              });
              return {werte: werte,
                      erste_leere: erste_leere,
                      letzte_wert: letzte_wert,
                      anzahl_sichtbar: sichtbar.length};
            }
          """)
        assert lage["anzahl_sichtbar"] > 0, "keine sichtbare Zeile"
        assert "" in lage["werte"], (
            "die Fixture spannt den Fall nicht auf - alle sichtbaren "
            f"Zeilen haben eine Spanne: {lage['werte']}")
        assert lage["letzte_wert"] < lage["erste_leere"], (
            f"eine Zeile ohne Spanne steht ueber einer mit Wert "
            f"(erste leere bei Index {lage['erste_leere']}, letzte mit "
            f"Wert bei {lage['letzte_wert']}): {lage['werte']}")


def test_p3_der_ansichtwechsel_nimmt_die_sortierung_mit(_seite):
    """Sicht-Pruefung Wesentliches 1 (18.09.2026): nach "Einzelgeraepreis"
    (ab) sortiert und auf TCO umgeschaltet, blieb die Sortierung an der
    jetzt UNSICHTBAREN Spalte haengen - live gemessen standen die
    TCO-Werte danach unsortiert (3357.66 / 2705.66 / 2927.80 Euro), und
    der Sortierpfeil war weg, weil seine Kopfzelle ausgeblendet war.

    Seit dem Fix (app.js 'gr-ansicht'-Event): die Hauptpreisspalte wird
    GEMAPPT (Einzelgeraetepreis <-> TCO-24, Erstklick-Richtung wie von
    Hand), jede andere Sortierung (Haendler/Spanne nur Barpreis,
    Ø/Delta nur TCO) faellt auf die SERVER-Ordnung zurueck - gemessen
    als: kein Kopf traegt data-vor mehr, und die Zeilen stehen wieder in
    der Reihenfolge des gerenderten Dokuments."""
    _frisch(_seite)
    _seite.click(".gr-reiter button[data-tafel='tafel-katalog']")
    _seite.wait_for_timeout(80)
    _seite.click("#gr-kmehr")
    _seite.wait_for_timeout(120)
    # Achtung: das Attribut heisst data-s-GERAET - `dataset.geraet` laese
    # sich still zu null auf JEDE Zeile auslesen, und der Vergleich unten
    # vergliche zwei leere Listen (die "Test prueft nichts"-Falle).
    anfangs = _seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-a-zeile",
        "z => z.map(r => r.getAttribute('data-s-geraet'))")
    assert all(anfangs), "kein Modellname an den Zeilen - der Test misst nichts"

    # --- Fall 1: Hauptpreisspalte wird gemappt (preis -> tco).
    _seite.click('#gr-katalogtabelle .gr-sort[data-sort="preis"]')
    _seite.wait_for_timeout(120)
    _seite.click("#tafel-katalog .gr-kansicht button[data-ansicht='tco']")
    _seite.wait_for_timeout(150)
    lage = _seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-a-zeile", """
        (zeilen) => {
          var sichtbar = zeilen.filter(
            z => getComputedStyle(z).display !== 'none');
          var werte = sichtbar.map(z => z.getAttribute('data-s-tco'));
          var zahl = werte.map(w => w === '' ? null : parseFloat(w));
          var mit = zahl.filter(v => v !== null);
          return {werte: werte,
                  monoton_fallend: mit.every(
                    (v, i) => i === 0 || mit[i - 1] >= v),
                  anzahl_mit_zahl: mit.length};
        }
      """)
    # Der aktive Sortierkopf ist JETZT der TCO-Kopf - sichtbar und mit
    # Pfeil - und die TCO-Werte stehen monoton (Erstklick = absteigend).
    aktiv = _seite.eval_on_selector(
        "#gr-katalogtabelle thead .gr-sort[data-vor]", """
        k => ({spalte: k ? k.getAttribute('data-sort') : null,
               richtung: k ? k.getAttribute('data-vor') : null})
      """)
    assert aktiv["spalte"] == "tco", (
        f"nach dem Wechsel sortiert noch {aktiv} - die unsichtbare "
        "Preisspalte hätte gemappt werden müssen")
    assert aktiv["richtung"] == "ab"
    assert lage["anzahl_mit_zahl"] >= 2, (
        "die Fixture spannt keine sortierbare TCO-Spalte auf - der Test "
        f"misst nichts: {lage['werte']}")
    assert lage["monoton_fallend"], (
        f"TCO-Werte nach dem Wechsel unsortiert: {lage['werte']}")

    # --- Fall 2: eine Spalte OHNE Entsprechung (delta nur in der
    # TCO-Ansicht) faellt auf die Server-Ordnung zurueck.
    _seite.click('#gr-katalogtabelle .gr-sort[data-sort="delta"]')
    _seite.wait_for_timeout(120)
    _seite.click("#tafel-katalog .gr-kansicht button[data-ansicht='barpreis']")
    _seite.wait_for_timeout(150)
    ohne_pfeil = _seite.eval_on_selector_all(
        "#gr-katalogtabelle thead .gr-sort[data-vor]", "k => k.length > 0")
    jetzt = _seite.eval_on_selector_all(
        "#gr-katalogtabelle .gr-a-zeile",
        "z => z.map(r => r.getAttribute('data-s-geraet'))")
    assert not ohne_pfeil, (
        "ein Sortierpfeil haengt an einer Spalte, nach der niemand "
        "sortieren konnte")
    assert jetzt == anfangs, (
        "nach dem Wechsel steht nicht die Server-Ordnung: "
        f"{jetzt[:4]} statt {anfangs[:4]}")


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


@pytest.mark.parametrize("tid", ["tafel-tco", "tafel-katalog",
                                 "tafel-verlauf", "tafel-portfolio"])
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
        _zeige_tafel(seite, tid)
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
    # P2 (17.09.2026): es sind noch DREI Tabellen - die vierte war die
    # G2-Tabelle des Verlaufs-Reiters und ist mit dem Block gefallen.
    assert len(tabellen) >= 3, (
        f"die Fixture muss alle Tabellen des TCO-Reiters zeigen: {tabellen}")
    ohne = [t["klassen"] for t in tabellen if not t["drin"]]
    assert not ohne, f"Tabellen ohne Rollbehaelter: {ohne}"
    # P2-Fix (Code-Prüfung S4-3): die dynamische Verlaufstabelle trägt nicht
    # `gr-ttab` (sie rollt im eigenen Behälter `#gr-vtabelle`, nicht in
    # `.gr-scroll`) - die REGEL gilt für sie genauso: jede breite Tabelle
    # dieser Seite rollt in sich, nie die ganze Seite.
    verlauf = _seite.evaluate(
        """() => Array.from(document.querySelectorAll('#gr-vtabelle table'))
                     .map(t => ({klassen: t.className,
                                 drin: !!t.closest('.gr-vtabelle')}))""")
    assert len(verlauf) >= 1, (
        "die Auto-Vorauswahl muss die Verlaufstabelle füllen: "
        f"{verlauf}")
    ohne_v = [t["klassen"] for t in verlauf if not t["drin"]]
    assert not ohne_v, f"Verlaufstabellen ohne Rollbehaelter: {ohne_v}"


# ==========================================================================
# PHASE R - die TCO-Hauptansicht im echten Browser (04.09.2026)
#
# Diese Faelle stehen hier und nicht im Modultest, weil sie erst im Browser
# entstehen: die Modellauswahl blendet um, ohne zu laden. Ein HTML-Test
# saehe dabei nur Markup.
#
# DIE BALKENLAENGE (G1) IST SEIT BRIEF_FADEN (05.09.2026) NICHT MEHR HIER:
# G1 wird in dieser Ansicht nicht mehr gerendert (Kriterium 1), und seine
# Geometrie ist ohnehin SERVERGERECHNET, keine Browser-Layoutfrage - die
# Zusicherung steht jetzt statisch in
# `tests/test_geraete_tco_hauptansicht.py::test_die_balkenlaenge_entspricht_dem_betrag`.
#
# O2 (11.09.2026): die Karten sind TABILLENZEILEN geworden (`.gr-bnd`), und
# die JS-Sortierung samt Sortier-/Filter-Control ist entfallen (§4
# Entscheidung 3) - die Zeilen stehen serverseitig nach TCO-24. Geprueft
# wird jetzt ebendiese Ordnung im Browser.
# ==========================================================================

def test_die_zeilen_stehen_nach_tco24_sortiert(_seite):
    """Der Entwurf sortiert die Bandliste aufsteigend nach TCO-24 - im
    Browser nachgemessen, nicht nur im Markup (ein Server-Sortierfehler
    stuende auch im Markup, aber der Blick gehoert dazu)."""
    _frisch(_seite)
    werte = _seite.evaluate("""() => Array.from(
      document.querySelectorAll('#gr-bndliste .gr-bnd[data-gesamt]'))
        .map(z => parseFloat(z.getAttribute('data-gesamt')))
        .filter(v => !isNaN(v))""")
    assert len(werte) >= 2, "die Fixture braucht mindestens zwei Zeilen"
    assert werte == sorted(werte), werte


def test_die_modellauswahl_blendet_ohne_neuladen_um(_seite):
    """E2: statt 88 Bloecke umzublenden setzt app.js den fertigen
    Graph-Zustand (Antwort-Satz, Messtag-Zeile, SVG) aus dem Fragment ein
    und die Bündel-Zeilen desselben Modells - ohne Neuladen, mit demselben
    Markup wie der Server-Render (kein Client-Renderer, keine Zahl im
    Client)."""
    auswahl = _seite.eval_on_selector(
        "#gr-zeitreihe-daten",
        "k => Object.keys(JSON.parse(k.textContent).erlaubt)")
    assert len(auswahl) >= 2, "die Fixture kennt nur ein Modell"
    vorgabe = _seite.eval_on_selector(
        "#gr-zeitreihe-daten",
        "k => JSON.parse(k.textContent).vorgabe")
    fremd = next(m for m in auswahl if m != vorgabe)
    waehle_modell(_seite, fremd)
    antwort = _seite.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                      "e => e.textContent")
    assert antwort.strip(), "der Antwort-Satz des gewaehlten Modells fehlt"
    erwartete = _seite.evaluate(
        """(id) => Object.keys(JSON.parse(
             document.getElementById('gr-zeitreihe-daten').textContent)
           .bnd_titel[id])""",
        fremd)
    assert erwartete, "keine Bänder im Knoten"
    zeilen = _seite.eval_on_selector_all(
        "#gr-buendel .gr-bnd:not([hidden])",
        "e => e.map(x => x.getAttribute('data-anbieter'))")
    assert zeilen, "keine sichtbaren Bündel-Zeilen des gewaehlten Modells"


def test_jede_zeile_mit_zahl_beantwortet_die_leitfrage(_seite):
    """A5.2 ist eine PFLICHTZEILE - auch und gerade bei 36 Monaten Bindung;
    seit O2 steht sie im Rechenweg-Aufklapper der Zeile."""
    _frisch(_seite)
    fehlend = _seite.evaluate("""() => Array.from(
      document.querySelectorAll('.gr-tmodell:not([hidden]) .gr-bnd'))
        .filter(z => z.getAttribute('data-gesamt')
                     && !z.querySelector('.gr-kk-24'))
        .map(z => z.getAttribute('data-anbieter'))""")
    assert fehlend == []


# ==========================================================================
# O2 (11.09.2026): die Bündel-Zeilen - Nachfolger der OPTIK-6-Klappe
#
# Die Klappe ist entfallen (die Karte ist eine Zeile geworden, jede mit
# ihrem EIGENEN kleinen Aufklapper; Sortier- und Anbieterfilter-Controls
# sind mit ihr gegangen, §4 Entscheidung 3). Was von den OPTIK-6-Tests
# bleibt, ist das, was 11b NICHT messen kann: dass die Zeilen geschlossen
# starten (kein `open`-Attribut im HTML) und dass ihr Öffnen ohne EINEN
# Netzwerkabruf sichtbar wird (statisch im Dokument, reines UI).
# ==========================================================================

def test_die_buendelzeilen_starten_geschlossen(_seite):
    """Der Anfangszustand ist der, den 11b misst: stünde eine Zeile im HTML
    offen (`open`-Attribut), klaffte ihr Rechenweg in der Anfangshöhe -
    die Kompaktheit wäre nur gerendert, nicht gebaut."""
    _seite.goto(_seite.url.rsplit("/", 1)[0] + "/geraete.html",
                wait_until="load")
    _seite.click(".gr-reiter button[data-tafel='tafel-tco']")
    _seite.wait_for_timeout(60)
    zustand = _seite.evaluate("""() => {
      const zeilen = document.querySelectorAll('#gr-bndliste .gr-bnd');
      return {zahl: zeilen.length,
              offen: [...zeilen].filter(z => z.open).length};
    }""")
    assert zustand["zahl"] > 0, "keine Bündelzeile im Dokument"
    assert zustand["offen"] == 0, "Zeilen starten offen"


def test_die_buendelzeile_oeffnet_ohne_netzwerk(_seite):
    """E1 + Aufklapp-Pflicht aus dem Auftrag: alles bleibt im Dokument
    erreichbar, und das Oeffnen ist reines UI - kein Nachladen, keine
    Serverinteraktion. Jede Anfrage, die waehrend des Oeffnens entsteht,
    macht diesen Test rot.

    Gezaehlt werden nur SAME-ORIGIN-Anfragen: die Webfonts der Seite
    (Google Fonts, display=swap) duerfen auch NACH dem load-Event noch
    einsetzen, und auf einem kalten Runner wuerde genau so eine den Test
    falsch rot machen. Fuer die Zusicherung "kein Nachladen von Inhalten"
    ist der Ursprung der scharfe Massstab - Inhalte laegen unter der
    eigenen Adresse."""
    _frisch(_seite)
    ursprung = _seite.url.rsplit("/", 1)[0]

    anfragen: list[str] = []

    def _zaehle(anfrage) -> None:
        if anfrage.url.startswith(ursprung):
            anfragen.append(anfrage.url)

    _seite.on("request", _zaehle)
    try:
        ergebnis = _seite.evaluate("""() => {
          const z = document.querySelector('#gr-bndliste .gr-bnd');
          if (!z) return null;
          // P4-Fix (Sicht-Pruefung 18.09.): Rechenweg-Montage beim
          // OEFFNEN - summary.click() ist der Nutzerweg (Default-Action
          // oeffnet synchron nach dem click-Dispatch, die Montage laeuft
          // im Delegaten desselben Dispatches).
          z.querySelector('summary').click();
          const rw = z.querySelector('.gr-bnd-rw');
          return {sichtbar: !!rw.offsetParent,
                  hoehe: Math.round(rw.getBoundingClientRect().height)};
        }""")
        _seite.wait_for_timeout(200)
    finally:
        _seite.remove_listener("request", _zaehle)
        # Den Ausgangszustand zurueckgeben: die Seite hat Modulgueltigkeit,
        # und ein spaeterer Test misst sonst eine aufgeklappte Zeile.
        _seite.evaluate(
            "() => document.querySelectorAll('.gr-bnd')"
            ".forEach(z => { z.open = false; })")
    assert ergebnis is not None, "keine Bündelzeile im Modellblock"
    assert ergebnis["sichtbar"], "der Rechenweg bleibt unsichtbar"
    assert ergebnis["hoehe"] > 60, \
        f"der Rechenweg hat nur {ergebnis['hoehe']} px Höhe"
    assert anfragen == [], \
        f"das Oeffnen hat Netzwerkanfragen ausgeloest: {anfragen}"


def test_die_alt_url_landet_im_radar_reiter(_umgebung):
    """E3 Schritt 3 (17.09.2026), im Ganzen gemessen: die Alt-URL
    wettbewerbsradar.html ist ein Meta-Refresh auf geraete.html#tafel-
    radar - ein Lesezeichen muss am Radar-Reiter ANKOMMEN, nicht nur auf
    der richtigen Seite. app.js normalisiert die Adresse danach auf die
    Deep-Link-Form (?modell=…&band=…); entscheidend ist der AKTIVE
    Reiter, nicht der Hash in der Adresszeile."""
    browser, adresse = _umgebung
    # `_umgebung` traegt die VOLLE Adresse der Modulseite - inklusive des
    # ?modell-Deep-Links, den app.js per replaceState hineingeschrieben
    # hat. Als Basis einer neuen Adresse wuerde daraus ein Phantom-Pfad
    # (.../geraete.html?modell=.../wettbewerbsradar.html), den der
    # Testserver mit der UNVERANDERTEN Geräteseite beantwortet - der Test
    # mässe dann den Deep-Link, nicht die Weiterleitung.
    basis = adresse.rsplit("/", 1)[0]
    seite = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        seite.goto(f"{basis}/wettbewerbsradar.html", wait_until="load")
        seite.wait_for_timeout(1000)   # Meta-Refresh 0s + Reiter-Schaltung
        assert "geraete.html" in seite.url, \
            f"der Meta-Refresh hat nicht weitergeleitet: {seite.url}"
        aktiv = seite.evaluate(
            "() => document.querySelector(\".gr-reiter button[aria-selected='true']\")"
            ".getAttribute('data-tafel')")
        assert aktiv == "tafel-radar", \
            f"die Alt-URL landet im Reiter {aktiv!r}, nicht im Radar-Reiter"
    finally:
        seite.close()
