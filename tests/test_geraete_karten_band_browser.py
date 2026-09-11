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


def _tarif(anbieter, tarif_id, tarif_name, gb):
    return {"anbieter": anbieter, "name": tarif_name, "tarif_id": tarif_id,
            "art": "mobilfunk", "grundgebuehr": 24.99, "laufzeit_monate": 24,
            "datenvolumen_gb": gb,
            "preisphasen": [{"von_monat": 1, "bis_monat": None,
                             "betrag": 24.99}],
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
        # 1,00 + 36 x 25,00 = 901,00 €; TCO-24 = 1 + 24x24 + 24x25 = 1.177,00 €
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
        _tarif("o2", "o2:klein", "O2 Mobile Klein", 18.0),
        _tarif("Vodafone", "vodafone:mittel", "Vodafone Mittel", 40.0),
        # Unbegrenzt liegt außerhalb aller Bänder (§7) - json schreibt dafuer
        # Infinity, genau wie der echte Tarifbestand.
        _tarif("o2", "o2:unlimited", "O2 Unlimited", math.inf),
        _tarif("congstar", "congstar:allnet-m", "Allnet Flat M", 25.0),
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


def _klappe_auf(seite):
    """Die Kartenklappe des sichtbaren Modellblocks öffnen - die Karten
    stehen statisch im Dokument, aber unsichtbar, solange die Klappe zu
    ist (Transitivitaet der `<details>`-UA-Regel)."""
    seite.evaluate("""() => document.querySelectorAll(
         '.gr-tmodell:not([hidden]) details.gr-karten-auf')
       .forEach(k => { k.open = true; })""")
    seite.wait_for_timeout(60)


def _sichtbare_anbieter(seite):
    """Anbieter der Karten, die der Leser wirklich sieht - nicht die, die
    nur kein `hidden`-Attribut tragen (dieselbe Messregel wie
    `_sichtbare_zeilen` in test_geraete_reiter_browser.py)."""
    return seite.eval_on_selector_all(
        ".gr-tmodell:not([hidden]) .gr-kkarte",
        "e => e.filter(k => getComputedStyle(k).display !== 'none')"
        "      .map(k => k.dataset.anbieter)")


# --------------------------------------------------------------------------
# Auftrag 2: die Bandwahl filtert die Kartenansicht
# --------------------------------------------------------------------------

def test_die_kartenliste_aendert_sich_bei_bandwechsel(_seite):
    """UX-1: bis P1 zeigte die Klappe bei jedem Band dieselben Karten aller
    Bänder gemischt. Jetzt zeigt sie die Karten des gewählten Bands - und
    die Liste ist nach dem Wechsel eine ANDERE."""
    _klappe_auf(_seite)
    _seite.select_option("#gr-band", "klein")
    _seite.wait_for_timeout(120)
    klein = _sichtbare_anbieter(_seite)
    assert "o2" in klein, f"Band klein zeigt keine o2-Karte: {klein}"
    # congstar führt nur ein Mittel-Band-Bündel - in Klein gehört sie nicht
    # in die Auswahl des Bands.
    assert "congstar" not in klein, klein

    _seite.select_option("#gr-band", "mittel")
    _seite.wait_for_timeout(120)
    mittel = _sichtbare_anbieter(_seite)
    assert "congstar" in mittel and "Vodafone" in mittel, mittel
    assert klein != mittel, (
        f"die Kartenliste folgt der Bandwahl nicht: {klein} == {mittel}")


def test_karten_anderer_baender_bleiben_im_dokument_und_verstecken_sich(_seite):
    """Versteckt, nicht entfernt: die Klappe ist statisch im Dokument, und
    ein Bandwechsel darf kein Nachladen auslösen (OPTIK-6/E1)."""
    _klappe_auf(_seite)
    _seite.select_option("#gr-band", "mittel")
    _seite.wait_for_timeout(120)
    verdeckt = _seite.eval_on_selector(
        '.gr-tmodell:not([hidden]) .gr-kkarte[data-band="klein"]',
        "e => ({versteckt: e.hidden,"
        "       sichtbar: getComputedStyle(e).display !== 'none'})")
    assert verdeckt["versteckt"] is True, "die Klein-Karte trägt kein hidden"
    assert verdeckt["sichtbar"] is False, "die Klein-Karte steht noch da"


def test_jede_bandkarte_traegt_ihre_gb_angabe(_seite):
    """Ohne GB-Angabe ist eine Bandauswahl nicht nachprüfbar: der Leser
    muss sehen, WARUM diese Karte im Band Klein steht."""
    _klappe_auf(_seite)
    _seite.select_option("#gr-band", "mittel")
    _seite.wait_for_timeout(120)
    gb = _seite.eval_on_selector_all(
        ".gr-tmodell:not([hidden]) .gr-kkarte[data-band]",
        "e => e.map(k => ({anbieter: k.dataset.anbieter,"
        "                  gb: (k.querySelector('.gr-kk-tarif') || {})"
        "                       .textContent || ''}))")
    assert gb, "keine Karte mit Band im Dokument"
    for eintrag in gb:
        assert "GB" in eintrag["gb"] or "unbegrenzt" in eintrag["gb"], (
            f"{eintrag['anbieter']} nennt kein Datenvolumen: {eintrag}")


# --------------------------------------------------------------------------
# Auftrag 1: Karten ohne Band als eigene, klar markierte Gruppe
# --------------------------------------------------------------------------

def test_karten_ohne_tarifband_bilden_eine_markierte_gruppe(_seite):
    """§7: Unbegrenzte Tarife und Tarife ohne erhobenes Volumen fallen aus
    dem Bandraster - sie werden als eigene Gruppe NACH dem Band geführt,
    nicht heimlich in ein Band einsortiert (o2-Unlimited-Karte, UX-1)."""
    _klappe_auf(_seite)
    _seite.select_option("#gr-band", "mittel")
    _seite.wait_for_timeout(120)
    lage = _seite.evaluate("""() => {
      const klappe = document.querySelector(
        '.gr-tmodell:not([hidden]) details.gr-karten-auf');
      const behaelter = klappe.querySelector('.gr-karten');
      const gruppe = behaelter.querySelector('.gr-kband-gruppe');
      const karten = [...behaelter.querySelectorAll('.gr-kkarte')];
      return {
        gruppeDa: !!gruppe,
        gruppeSichtbar: !!gruppe && getComputedStyle(gruppe).display !== 'none',
        gruppeText: gruppe ? gruppe.textContent.trim() : '',
        // Position: alle Karten MIT Band stehen vor der Gruppe, alle ohne
        // dahinter - die Gruppe trennt, sie sortiert nicht ein.
        davor: karten.filter(k => k.compareDocumentPosition(gruppe)
                            & Node.DOCUMENT_POSITION_FOLLOWING
                            && k.hasAttribute('data-band')).length,
        ohneBandDahinter: karten.filter(
            k => !(k.compareDocumentPosition(gruppe)
                   & Node.DOCUMENT_POSITION_FOLLOWING)
               && !k.hasAttribute('data-band')).length,
        unlimitedOhneBand: karten.some(k => k.dataset.anbieter === 'o2'
            && k.textContent.includes('O2 Unlimited')
            && !k.hasAttribute('data-band')),
      };
    }""")
    assert lage["gruppeDa"], "es gibt keine markierte Gruppe ohne Tarifband"
    assert lage["gruppeSichtbar"], "die Gruppe ist versteckt"
    assert "Ohne Tarifband" in lage["gruppeText"], lage["gruppeText"]
    assert lage["davor"] > 0, "keine Bandkarte vor der Gruppe"
    assert lage["ohneBandDahinter"] > 0, "keine Karte ohne Band hinter der Gruppe"
    assert lage["unlimitedOhneBand"], (
        "die o2-Unlimited-Karte ist in ein Band einsortiert statt markiert")


# --------------------------------------------------------------------------
# Auftrag 3: TCO-24 ohne Hover, Desktop und Mobil
# --------------------------------------------------------------------------

def test_die_tco_werte_des_bands_stehen_ohne_hover_im_dom(_seite):
    """UX-5: die exakten Werte steckten nur im SVG-Tooltip, den es am
    Telefon nicht gibt. Jetzt trägt jedes Band-Panel eine Werteliste als
    sichtbaren Text."""
    _seite.select_option("#gr-band", "klein")
    _seite.wait_for_timeout(120)
    klein = _seite.eval_on_selector(
        ".gr-tmodell:not([hidden]) .gr-tband[data-band='klein']",
        "e => e.innerText")
    assert "1.032,76" in klein, (
        f"der o2-TCO-24 (1 + 24x24,99 + 24x18) steht nicht als Text: {klein}")
    assert "18 GB" in klein, "das Datenvolumen des Band-Tarifs fehlt"

    _seite.select_option("#gr-band", "mittel")
    _seite.wait_for_timeout(120)
    mittel = _seite.eval_on_selector(
        ".gr-tmodell:not([hidden]) .gr-tband[data-band='mittel']",
        "e => e.innerText")
    # Vodafone: 1 + 24x26,99 + 24x15 = 1.008,76; congstar: 1.177,00
    assert "1.008,76" in mittel and "1.177,00" in mittel, mittel


def test_die_werteliste_nennt_dieselben_zahlen_wie_die_karten(_seite):
    """Keine zweite Rechnung: die Werte unter dem Chart sind dieselben, die
    die Karte je Anbieter trägt (`data-gesamt`) - zwei Stellen, eine Zahl."""
    _klappe_auf(_seite)
    _seite.select_option("#gr-band", "mittel")
    _seite.wait_for_timeout(120)
    lage = _seite.evaluate("""() => {
      const block = document.querySelector('.gr-tmodell:not([hidden])');
      const panel = block.querySelector(".gr-tband[data-band='mittel']");
      const karten = [...block.querySelectorAll('.gr-kkarte')]
          .filter(k => k.getAttribute('data-band') === 'mittel');
      return {
        werte: panel.querySelector('.gr-tband-werte')
               ? panel.querySelector('.gr-tband-werte').innerText : '',
        karten: karten.map(k => ({anbieter: k.dataset.anbieter,
                                 gesamt: k.getAttribute('data-gesamt')})),
      };
    }""")
    assert lage["werte"], "keine Werteliste im Band-Panel"
    for karte in lage["karten"]:
        # `data-gesamt` trägt den Rohwert (Punkt als Dezimaltrenner);
        # die Seite schreibt deutsch.
        erwartet = (f"{float(karte['gesamt']):,.2f}"
                    .replace(",", "X").replace(".", ",").replace("X", "."))
        assert erwartet in lage["werte"], (
            f"{karte['anbieter']}: Kartenwert {erwartet} fehlt in der "
            f"Werteliste: {lage['werte']!r}")


def test_mobil_bleibt_ohne_querscroll_und_mit_werteliste_lesbar(_seite):
    """390 px: die Werteliste muss ohne Hover UND ohne Querscroll lesbar
    sein - sonst ist sie am Telefon die alte Tooltip-Falle in neuem Gewand."""
    seite = _seite.context.browser.new_page(viewport={"width": 390,
                                                      "height": 844})
    try:
        seite.goto(_seite.url, wait_until="load")
        seite.click('[data-tafel="tafel-tco"]')
        seite.select_option("#gr-band", "mittel")
        seite.wait_for_timeout(120)
        breite = seite.evaluate("document.documentElement.scrollWidth")
        sichtbar = seite.evaluate("document.documentElement.clientWidth")
        assert breite <= sichtbar, f"{breite} px statt {sichtbar} px"
        text = seite.eval_on_selector(
            ".gr-tmodell:not([hidden]) .gr-tband[data-band='mittel']",
            "e => e.innerText")
        assert "1.008,76" in text and "1.177,00" in text, text
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
    _klappe_auf(_seite)
    _seite.select_option("#gr-band", "mittel")
    _seite.wait_for_timeout(120)
    congstar = _seite.eval_on_selector(
        ".gr-tmodell:not([hidden]) .gr-kkarte[data-anbieter='congstar']",
        """e => ({
             leit: e.querySelector('.gr-kk-leit b').textContent,
             text: e.innerText,
             gesamt: e.getAttribute('data-gesamt') })""")
    assert congstar["leit"] == "Finanzierung gesamt", congstar["leit"]
    # 1,00 € Zuzahlung + 36 x 25,00 € Raten
    assert "901,00" in congstar["text"], congstar["text"]
    # Die Karte behauptet keinen REINEN Gerätepreis ohne Vertrag - weder als
    # Zahl noch als Wort an der Leitzahl.
    assert "Gerätepreis" not in congstar["text"].split("Rechenweg")[0], (
        congstar["text"])
    assert "nicht erhoben" in congstar["text"], (
        "die Karte nennt die Lücke beim Gerätepreis ohne Vertrag nicht")
    # Die TCO-24 bleibt die zweite, getrennte Zahl.
    assert "TCO-24" in congstar["text"] and "1.177,00" in congstar["text"]


def test_ein_gemessener_barpreis_fuehrt_weiter_als_geraetepreis(_seite):
    """Gegenprobe: Karten mit gemessenem eigenen Barpreis (o2, Vodafone)
    führen unverändert mit „Gerätepreis“ - das neue Etikett gilt nur der
    Finanzierungssumme, nicht dem Barpreis."""
    _klappe_auf(_seite)
    _seite.select_option("#gr-band", "klein")
    _seite.wait_for_timeout(120)
    o2 = _seite.eval_on_selector(
        ".gr-tmodell:not([hidden]) .gr-kkarte[data-anbieter='o2']"
        "[data-band='klein']",
        "e => ({leit: e.querySelector('.gr-kk-leit b').textContent,"
        "          text: e.innerText})")
    assert o2["leit"] == "Gerätepreis", o2["leit"]
    assert "999,00" in o2["text"], o2["text"]


def test_die_antwortzeile_fuehrt_keine_finanzierungssumme_als_geraetepreis(
        _seite):
    """Dieselbe Trennung eine Ebene höher: „Günstigster Gerätepreis“ ist ein
    Preis OHNE Vertrag - die congstar-Finanzierungssumme (901,00 €) ist
    billiger als jeder Barpreis und dürfte die Antwortzeile nicht führen,
    sonst widerspräche die Leitzahl ihrer eigenen Kartenklappe."""
    zeile = _seite.eval_on_selector(
        ".gr-tmodell:not([hidden]) .gr-antwort",
        "e => e.innerText")
    # Die Zeile trägt `text-transform` - geprüft wird kleingeschrieben
    # gegen den gerenderten Text, nicht gegen das Markup.
    assert "günstigster gerätepreis" in zeile.lower(), zeile
    assert "901,00" not in zeile, (
        f"die Finanzierungssumme führt die Gerätepreis-Antwort: {zeile}")
    assert "999,00" in zeile and "o2" in zeile, zeile


# --------------------------------------------------------------------------
# Randnotiz aus der Audit-Gegenprobe: doppelt-escaped Tooltips heilen
# --------------------------------------------------------------------------

def test_die_bandpanel_tooltips_sind_nicht_doppelt_escaped(_seite):
    """UX-Nebenbefund: die `<title>` der Band-Panels standen als
    `&lt;title&gt;…` im DOM - doppelt escaped, damit zeigt der Browser
    keinen Tooltip. Geheilt wird mit derselben Berührung (P1)."""
    _seite.select_option("#gr-band", "klein")
    _seite.wait_for_timeout(120)
    titel = _seite.eval_on_selector_all(
        ".gr-tmodell:not([hidden]) .gr-tband[data-band='klein'] title",
        "e => e.map(t => t.textContent)")
    assert titel, "das Panel trägt überhaupt keinen Tooltip-Titel"
    kaputt = [t for t in titel if "<title" in t or "&lt;" in t or "&amp;" in t]
    assert kaputt == [], f"doppelt escapte Tooltips: {kaputt[:2]}"
    # Und der gepanzerte Punkt nennt Anbieter, Datum und Betrag - derselbe
    # Belegzwang wie überall auf dieser Seite.
    assert any("·" in t and "€" in t for t in titel), titel
