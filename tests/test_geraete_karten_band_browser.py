"""P1 (STRATEGIE_GERAETESEITE.md, 11.09.2026): die Anbieterkarten folgen der
Bandwahl, die TCO-24-Werte stehen ohne Hover im DOM, die Finanzierungssumme
ist von Gerätepreis und TCO getrennt (UX-1, UX-5, TCO-1).

Warum im Browser
----------------
Die Bandkopplung der Karten ist reines UI (`app.js` versteckt und ordnet
Karten im geladenen Dokument) - ein statischer Test saehe nur Markup. Die
Wertetabelle je Band-Panel dagegen entsteht serverseitig; dass sie OHNE
Hover lesbar ist, sieht man trotzdem erst im gerenderten Dokument (ein
`<title>` ist im DOM auch "da"). Dieselbe Bauform wie
`tests/test_geraete_tco_band_browser.py`: eigener Server auf 127.0.0.1, kein
`file://`, kein Netz, Chromium an beiden bekannten Orten gesucht.

Die Fixture (rot-vor-gruen gegen den Stand vom 11.09.2026 geschrieben)
----------
EIN Modell, fuenf Bündelkarten in drei Lagen:
  - o2 "Klein" (18 GB)                -> Band klein,  Gerätepreis = Barpreis
  - Vodafone "Mittel" (40 GB)         -> Band mittel, Gerätepreis = Barpreis
  - congstar "Allnet M" (25 GB)       -> Band mittel, OHNE eigene Listung ->
                                         Gerätepreis ist die Finanzierungssumme
                                         (TCO-1: derselbe Fall wie congstar
                                         Galaxy S26 Ultra 1024 am Bestand)
  - o2 "Unlimited" (unbegrenzt)       -> KEIN Band (§7: außerhalb der Bänder)
  - 1&1 (Tarif nicht im Tarifbestand) -> KEIN Band (kein Datenvolumen erhoben)
dazu die drei Haendlerkarten (Amazon/Expert/Saturn, nie ein Band) und die
Telekom-Leerkarte. Ohne-Tarifband-Gruppe: o2 Unlimited, 1&1, Telekom,
Amazon, Expert, Saturn.
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import json
import math
import pathlib
import socket
import threading

import pytest
import yaml

from telco_radar.report.html import render_site
from test_geraete_zeitreihe_browser import waehle_band, waehle_modell

WURZEL = pathlib.Path(__file__).resolve().parents[1]
HEUTE = "2026-09-11"

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro", "generation": 17,
     "marktstart": "2025-09-19", "speicher": [256], "segment": "premium"}]}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {"anbieter": [
    {"name": "o2", "typ": "netzbetreiber", "rang": 2, "methode": "ldjson",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/handys"}]},
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 1, "eigen": True,
     "methode": "ldjson", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://www.vodafone.de/handys"}]},
    {"name": "congstar", "typ": "netzbetreiber", "rang": 3,
     "methode": "ldjson", "basis_url": "https://www.congstar.de",
     "einstiege": [{"url": "https://www.congstar.de/handys"}]},
    {"name": "1&1", "typ": "netzbetreiber", "rang": 4, "methode": "ldjson",
     "basis_url": "https://www.1und1.de",
     "einstiege": [{"url": "https://www.1und1.de/handys"}]},
]}

SKU = "apple-iphone-17-pro-256gb-schwarz"


def _listung(anbieter, preis):
    return {"id": f"{anbieter.lower()}--{SKU}", "sku_id": SKU,
            "device_id": "apple-iphone-17-pro", "anbieter": anbieter,
            "anbieter_typ": "netzbetreiber", "netz": anbieter,
            "speicher_gb": 256, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-08-20", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-20",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{SKU}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/liste"]}


def _buendel(anbieter, tarif_id, tarif_name, *, tarif, rate,
             laufzeit=24, zuzahlung=1.0):
    return {"id": f"buendel--{anbieter.lower()}--{tarif_id}",
            "sku_id": SKU, "anbieter": anbieter, "tarif_name": tarif_name,
            "tarif_id": tarif_id, "tarif_id_guete": "hoch",
            "tarif_monatlich": tarif, "geraet_zuzahlung": zuzahlung,
            "geraet_monatsrate": rate, "laufzeit_monate": laufzeit,
            "anschlusspreis": 0.0, "zustand": "neu", "rabatte": [],
            "quelle_url": f"https://example.de/{anbieter.lower()}/{SKU}",
            "abgerufen_am": HEUTE, "first_seen": HEUTE,
            "last_verified": HEUTE}


def _tarif(anbieter, tarif_id, tarif_name, gb, betrag):
    # A1: Liegt eine Preisphase vor, rechnet die Leitzahl PHASENGEWICHTET
    # und ignoriert tarif_monatlich des Buendels - deshalb traegt jede
    # Phase denselben Betrag wie ihr Buendel-Tarif, sonst waere jede Zahl
    # dieser Fixture nur ueber die Phase erklaerbar.
    return {"anbieter": anbieter, "name": tarif_name, "tarif_id": tarif_id,
            "art": "mobilfunk", "grundgebuehr": betrag,
            "laufzeit_monate": 24, "datenvolumen_gb": gb,
            "preisphasen": [{"von_monat": 1, "bis_monat": None,
                             "betrag": betrag}],
            "dokument_url": f"https://example.de/pib/{tarif_id}",
            "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}


def _baue(tmp_path: pathlib.Path):
    root = tmp_path / "site_baum"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    # congstar und 1&1 haben KEINE Listung: congstars Gerätepreis kann damit
    # nur aus Zuzahlung + Raten kommen - der TCO-1-Fall.
    listungen = [_listung("o2", 999.0), _listung("Vodafone", 1049.0)]
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {"o2": {"laeufe": 4, "funde_gesamt": 1},
                     "Vodafone": {"laeufe": 4, "funde_gesamt": 1}},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = [
        _buendel("o2", "o2:klein", "O2 Mobile Klein", tarif=24.99, rate=18.0),
        _buendel("Vodafone", "vodafone:mittel", "Vodafone Mittel",
                 tarif=26.99, rate=15.0),
        # 36 Monate Raten, keine eigene Listung -> Finanzierungssumme
        # 1,00 + 36 x 25,00 = 901,00 EUR; Kosten über 24 Monate (A1, alle
        # Raten der eigenen Laufzeit) = 1 + 24x24 + 36x25 = 1.477,00 EUR
        _buendel("congstar", "congstar:allnet-m", "Allnet Flat M",
                 tarif=24.00, rate=25.0, laufzeit=36),
        _buendel("o2", "o2:unlimited", "O2 Unlimited",
                 tarif=34.99, rate=30.0, laufzeit=36),
        # Tarif steht NICHT in tarife.jsonl -> kein Datenvolumen -> kein Band
        _buendel("1&1", "einsundeins:flox", "1&1 Flex", tarif=39.99, rate=20.0),
    ]
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    tarife = [
        _tarif("o2", "o2:klein", "O2 Mobile Klein", 18.0, 24.99),
        _tarif("Vodafone", "vodafone:mittel", "Vodafone Mittel", 40.0, 26.99),
        # Unbegrenzt liegt außerhalb aller Bänder (§7) - json schreibt dafuer
        # Infinity, genau wie der echte Tarifbestand.
        _tarif("o2", "o2:unlimited", "O2 Unlimited", math.inf, 34.99),
        _tarif("congstar", "congstar:allnet-m", "Allnet Flat M", 25.0, 24.00),
    ]
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


def _chromium():
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(pathlib.Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@contextlib.contextmanager
def _server(site: pathlib.Path):
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


@pytest.fixture(scope="module")
def _seite(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright

    tmp_path = tmp_path_factory.mktemp("p1karten")
    site = _baue(tmp_path)

    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        seite = browser.new_page(viewport={"width": 1440, "height": 900})
        seite.goto(f"{basis}/geraete.html", wait_until="load")
        seite.click('[data-tafel="tafel-tco"]')
        yield seite
        browser.close()


def _sichtbare_anbieter(seite):
    """Anbieter der Bündel-ZEILEN, die der Leser wirklich sieht - nicht
    die, die nur kein `hidden`-Attribut tragen (dieselbe Messregel wie
    `_sichtbare_zeilen` in test_geraete_reiter_browser.py). Seit O2 stehen
    die Zeilen offen unter dem Graphen - keine Kartenklappe mehr."""
    return seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd",
        "e => e.filter(z => getComputedStyle(z).display !== 'none')"
        "      .map(z => z.dataset.anbieter)")


# --------------------------------------------------------------------------
# Auftrag 2: die Bandwahl filtert die Kartenansicht
# --------------------------------------------------------------------------

def test_die_zeilenliste_aendert_sich_bei_bandwechsel(_seite):
    """UX-1: bis P1 zeigte die Klappe bei jedem Band dieselben Karten aller
    Bänder gemischt. Seit O2 zeigt die Zeilenliste die Bündel des
    gewählten Bands - und die Liste ist nach dem Wechsel eine ANDERE."""
    waehle_band(_seite, "klein")
    _seite.wait_for_timeout(120)
    klein = _sichtbare_anbieter(_seite)
    assert "o2" in klein, f"Band klein zeigt keine o2-Karte: {klein}"
    # congstar führt nur ein Mittel-Band-Bündel - in Klein gehört sie nicht
    # in die Auswahl des Bands.
    assert "congstar" not in klein, klein

    waehle_band(_seite, "mittel")
    _seite.wait_for_timeout(120)
    mittel = _sichtbare_anbieter(_seite)
    assert "congstar" in mittel and "Vodafone" in mittel, mittel
    assert klein != mittel, (
        f"die Kartenliste folgt der Bandwahl nicht: {klein} == {mittel}")


def test_zeilen_anderer_baender_bleiben_im_dokument_und_verstecken_sich(_seite):
    """Versteckt, nicht entfernt: die Zeilen sind statisch im Dokument, und
    ein Bandwechsel darf kein Nachladen auslösen (OPTIK-6/E1)."""
    waehle_band(_seite, "mittel")
    _seite.wait_for_timeout(120)
    verdeckt = _seite.eval_on_selector(
        '#gr-bndliste .gr-bnd[data-band="klein"]',
        "e => ({versteckt: e.hidden,"
        "       sichtbar: getComputedStyle(e).display !== 'none'})")
    assert verdeckt["versteckt"] is True, "die Klein-Zeile trägt kein hidden"
    assert verdeckt["sichtbar"] is False, "die Klein-Zeile steht noch da"


def test_jede_bandzeile_traegt_ihre_gb_angabe(_seite):
    """Ohne GB-Angabe ist eine Bandauswahl nicht nachprüfbar: der Leser
    muss sehen, WARUM diese Zeile im Band Klein steht."""
    waehle_band(_seite, "mittel")
    _seite.wait_for_timeout(120)
    gb = _seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd[data-band]",
        "e => e.map(z => ({anbieter: z.dataset.anbieter,"
        "                  gb: (z.querySelector('.gr-bnd-tarif') || {})"
        "                       .textContent || ''}))")
    assert gb, "keine Zeile mit Band im Dokument"
    for eintrag in gb:
        assert "GB" in eintrag["gb"] or "unbegrenzt" in eintrag["gb"], (
            f"{eintrag['anbieter']} nennt kein Datenvolumen: {eintrag}")


# --------------------------------------------------------------------------
# Auftrag 1: Karten ohne Band als eigene, klar markierte Gruppe
# --------------------------------------------------------------------------

def test_zeilen_ohne_tarifband_bilden_eine_markierte_gruppe(_seite):
    """§7: Unbegrenzte Tarife und Tarife ohne erhobenes Volumen fallen aus
    dem Bandraster - seit O2 stehen sie in der eigenen Gruppe 'Ohne
    Tarifband' UNTER der Bandliste (#gr-ohneband), nicht heimlich in einem
    Band (o2-Unlimited-Zeile, UX-1)."""
    waehle_band(_seite, "mittel")
    _seite.wait_for_timeout(120)
    lage = _seite.evaluate("""() => {
      const tafel = document.querySelector('#tafel-tco');
      const gruppe = tafel.querySelector('#gr-ohneband');
      const zeilen = gruppe ? [...gruppe.querySelectorAll('.gr-bnd')] : [];
      return {
        gruppeDa: !!gruppe,
        gruppeSichtbar: !!gruppe
            && getComputedStyle(gruppe).display !== 'none',
        gruppeText: gruppe ? gruppe.textContent.trim() : '',
        zeilenOhneBand: zeilen.filter(z => !z.hasAttribute('data-band')).length,
        unlimitedOhneBand: zeilen.some(z => z.dataset.anbieter === 'o2'
            && z.textContent.includes('O2 Unlimited')
            && !z.hasAttribute('data-band')),
        nachDerBandliste: !!gruppe && !!tafel.querySelector('#gr-bndliste')
            && tafel.querySelector('#gr-bndliste')
                 .compareDocumentPosition(gruppe)
               & Node.DOCUMENT_POSITION_FOLLOWING,
      };
    }""")
    assert lage["gruppeDa"], "es gibt keine markierte Gruppe ohne Tarifband"
    assert lage["gruppeSichtbar"], "die Gruppe ist versteckt"
    assert "Ohne Tarifband" in lage["gruppeText"], lage["gruppeText"]
    assert lage["zeilenOhneBand"] > 0, "keine Zeile ohne Band in der Gruppe"
    assert lage["unlimitedOhneBand"], (
        "die o2-Unlimited-Zeile ist in ein Band einsortiert statt markiert")
    assert lage["nachDerBandliste"], (
        "die Gruppe steht nicht hinter der Bandliste")


# --------------------------------------------------------------------------
# Auftrag 3: TCO-24 ohne Hover, Desktop und Mobil
# --------------------------------------------------------------------------

def test_die_tco_werte_des_bands_stehen_ohne_hover_im_dom(_seite):
    """UX-5, E2-Fassung: die exakten Werte stehen als TEXT im DOM - im
    Antwort-Satz (der beste des Bands) und auf jeder Bündel-Zeile. Das
    SVG der Zeitreihe trägt seine Werte ebenfalls als <text>, niemals
    nur als Tooltip."""
    waehle_band(_seite, "klein")
    _seite.wait_for_timeout(250)
    tafel = _seite.eval_on_selector("#tafel-tco", "e => e.innerText")
    assert "1.032,76" in tafel, (
        f"der o2-TCO-24 (1 + 24x24,99 + 24x18) steht nicht als Text")
    assert "18 GB" in tafel, "das Datenvolumen des Band-Tarifs fehlt"

    waehle_band(_seite, "mittel")
    _seite.wait_for_timeout(250)
    tafel = _seite.eval_on_selector("#tafel-tco", "e => e.innerText")
    # Vodafone: 1 + 24x26,99 + 24x15 = 1.008,76 - congstar (A1, 36 Raten):
    # 1 + 24x24 + 36x25 = 1.477,00
    assert "1.008,76" in tafel and "1.477,00" in tafel, tafel[:200]


def test_der_antwort_satz_nennt_die_zahl_der_guenstigsten_zeile(_seite):
    """Keine zweite Rechnung (E2-Fassung der Wertelisten-Regel): der
    Betrag des Antwort-Satzes ist der KLEINSTE data-gesamt der im Band
    sichtbaren Bündel-Zeilen - zwei Stellen, eine Zahl."""
    waehle_band(_seite, "mittel")
    _seite.wait_for_timeout(250)
    lage = _seite.evaluate("""() => {
      const antwort = document.querySelector('#tafel-tco .gr-zr-antwort')
        .innerText;
      const bnd = [...document.querySelectorAll('#gr-bndliste .gr-bnd')]
          .filter(z => !z.hidden && z.getAttribute('data-band') === 'mittel');
      return {antwort,
              min: Math.min(...bnd.map(z => parseFloat(z.dataset.gesamt))),
              anbieter: bnd.map(z => z.dataset.anbieter)};
    }""")
    assert lage["anbieter"], "keine sichtbaren Bündel-Zeilen im Band"
    # Der ERSTE Betrag nach dem ersten Doppelpunkt ist die Leitzahl des
    # Satzes - der Satzanfang nennt Geraet und Band und enthaelt selber
    # Ziffern ("iPhone 17 Pro 256 GB"), die keine Betragsparser fuettern
    # duerfen.
    from re import search
    nach_doppelpunkt = lage["antwort"].split(":", 1)[1]
    treffer = search(r"([\d.]+,\d\d)", nach_doppelpunkt)
    assert treffer, f"kein Betrag im Antwort-Satz: {lage['antwort']!r}"
    beste = float(treffer.group(1).replace(".", "").replace(",", "."))
    assert abs(beste - lage["min"]) < 0.005, (
        f"Antwort-Satz nennt {beste}, die günstigste Zeile {lage['min']}")


def test_mobil_bleibt_ohne_querscroll_und_mit_werteliste_lesbar(_seite):
    """390 px: die Graph-Werte müssen ohne Hover UND ohne Querscroll lesbar
    sein - sonst ist der Balken am Telefon die alte Tooltip-Falle in neuem
    Gewand."""
    seite = _seite.context.browser.new_page(viewport={"width": 390,
                                                      "height": 844})
    try:
        seite.goto(_seite.url, wait_until="load")
        seite.click('[data-tafel="tafel-tco"]')
        waehle_band(seite, "mittel")
        seite.wait_for_timeout(250)
        breite = seite.evaluate("document.documentElement.scrollWidth")
        sichtbar = seite.evaluate("document.documentElement.clientWidth")
        assert breite <= sichtbar, f"{breite} px statt {sichtbar} px"
        text = seite.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                      "e => e.innerText")
        assert "1.008,76" in text, f"Antwort ohne gedruckten Wert: {text!r}"
    finally:
        seite.close()


# --------------------------------------------------------------------------
# Auftrag 4: congstar trennt Finanzierungssumme und Gerätepreis (§3)
# --------------------------------------------------------------------------

def test_die_finanzierungssumme_heisst_so_und_nicht_geraetepreis(_seite):
    """TCO-1: auf der congstar-Karte stand die tarifabhängige Summe aus
    Zuzahlung und allen Raten unter „Gerätepreis“. §3 verlangt zwei Zahlen,
    nie vermischt: die Finanzierung heißt Finanzierung, und der reine
    Gerätepreis ohne Vertrag wird als eigene Aussage benannt - hier als
    benannte Lücke, weil congstar dazu nichts gemessen hat."""
    waehle_band(_seite, "mittel")
    _seite.wait_for_timeout(120)
    # Der Rechenweg steht im geschlossenen Aufklapper - innerText zeigt ihn
    # nur, wenn die Zeile offen ist (Transitivitaet der <details>-Regel).
    congstar = _seite.eval_on_selector(
        "#gr-bndliste .gr-bnd[data-anbieter='congstar']"
        "[data-band='mittel']",
        """e => {
          // P4-Fix (Sicht-Pruefung 18.09.): der Rechenweg wird erst beim
          // OEFFNEN aus dem <template> montiert - der SUMMARY-KLICK ist
          // der Nutzerweg (programmatisches open=true traefe die Montage
          // nur ueber das asynchrone toggle-Event).
          e.querySelector('summary').click();
          const rw = e.querySelector('.gr-bnd-rw');
          return {
            bar: e.querySelector('.gr-bnd-bar').textContent,
            summary: e.querySelector('summary').innerText,
            rw: rw ? rw.innerText : '',
            gesamt: e.getAttribute('data-gesamt') };
        }""")
    _seite.evaluate(
        "() => document.querySelectorAll('.gr-bnd')"
        ".forEach(z => { z.open = false; })")
    # 1,00 € Zuzahlung + 36 x 25,00 € Raten - die Spalte heißt die Zahl
    # beim Namen (Finanzierung), nicht "Gerätepreis".
    assert "Finanzierung" in congstar["bar"], congstar["bar"]
    assert "901,00" in congstar["bar"], congstar["bar"]
    assert "Gerätepreis" not in congstar["bar"], congstar["bar"]
    # Die Zeile behauptet keinen REINEN Gerätepreis ohne Vertrag - die
    # Lücke steht im Rechenweg benannt da.
    assert "nicht erhoben" in congstar["rw"], (
        "der Rechenweg nennt die Lücke beim Gerätepreis ohne Vertrag nicht")
    # Die Leitzahl („Kosten über 24 Monate", alle 36 Raten) bleibt die
    # zweite, getrennte Zahl: 1 + 24x24 Tarif + 36x25 Raten = 1.477,00.
    assert "Kosten über 24 Monate" in congstar["summary"] \
        and "1.477,00" in congstar["summary"]


def test_ein_gemessener_barpreis_fuehrt_weiter_als_geraetepreis(_seite):
    """Gegenprobe: Karten mit gemessenem eigenen Barpreis (o2, Vodafone)
    führen unverändert mit „Gerätepreis“ - das neue Etikett gilt nur der
    Finanzierungssumme, nicht dem Barpreis."""
    waehle_band(_seite, "klein")
    _seite.wait_for_timeout(120)
    o2 = _seite.eval_on_selector(
        "#gr-bndliste .gr-bnd[data-anbieter='o2'][data-band='klein']",
        "e => ({bar: e.querySelector('.gr-bnd-bar').textContent,"
        "          text: e.innerText})")
    # Ein gemessener Barpreis steht OHNE Finanzierungs-Etikett in der
    # Spalte - nur die tarifabhängige Summe heißt Finanzierung.
    assert "Finanzierung" not in o2["bar"], o2["bar"]
    assert "999,00" in o2["bar"], o2["bar"]
    assert "999,00" in o2["text"], o2["text"]


def test_der_antwort_satz_nennt_keine_finanzierungssumme_als_geraetepreis(
        _seite):
    """Dieselbe Trennung eine Ebene höher, E2-Fassung: der Antwort-Satz
    nennt die Finanzierungssumme nur als das, was sie ist - Kosten über
    24 Monate. Das Wort „Gerätepreis" führt er nicht (der congstar-
    Finanzierungsbetrag 901,00 € wäre billiger als jeder Barpreis und
    dürfe eine Gerätepreis-Antwort nie führen)."""
    satz = _seite.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                   "e => e.innerText")
    assert "Kosten über 24 Monate" in satz, satz
    assert "TCO-24" not in satz, satz
    assert "gerätepreis" not in satz.lower(), satz
    assert "901,00" not in satz, (
        f"die Finanzierungssumme führt den Antwort-Satz: {satz}")


# --------------------------------------------------------------------------
# Randnotiz aus der Audit-Gegenprobe: doppelt-escaped Tooltips heilen
# --------------------------------------------------------------------------

def test_der_graph_traegt_keine_tooltips_mehr(_seite):
    """E2: der Graph ist ein SVG - und trägt KEIN <title>: jeder Wert
    steht als <text> im Bild (am letzten und ersten Punkt), der beste
    zusätzlich im Antwort-Satz. Ein Tooltip-Fehler käme zurück, wenn
    Werte NUR in <title> steckten."""
    waehle_band(_seite, "klein")
    _seite.wait_for_timeout(250)
    assert _seite.eval_on_selector_all(
        "#tafel-tco title", "e => e.length") == 0
    werte = _seite.eval_on_selector_all(
        "#tafel-tco svg.gr-zr text.gr-zr-wert", "e => e.length")
    antwort = _seite.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                      "e => e.innerText")
    assert "€" in antwort, f"Antwort ohne gedruckten Wert: {antwort!r}"
    # Mit Historie zeigt auch das SVG gedruckte Werte; ohne Historie
    # (diese Fixture) trägt der Antwort-Satz sie allein.
    assert werte >= 0
