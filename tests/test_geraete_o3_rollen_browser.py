"""O3 (STRATEGIE_GERAETE_OPTIK §3, 15.09.2026) im echten Chromium —
Rollen, Deep-Link, Sortierung, Modellwechsel.

Dieselbe Bauform wie `tests/test_geraete_o2_zeilen_browser.py`: eigener
Server auf 127.0.0.1 (kein `file://` — das Bündel-Fragment wird per
fetch geladen und wäre unter file:// von der Same-Origin-Regel gesperrt,
dieselbe Lehre wie search_index.json), Chromium an beiden bekannten
Orten gesucht.

Die EIGENE Fixture erweitert die O2-Lage um ein DRITTES Modell mit zwei
eigenen Bündeln: der S3-Test braucht drei Stichproben mit
UNTERSCHIEDLICHEN Zeilen je Modell, und die O2-Lage trägt nur zwei
Modelle (das zweite mit einer einzigen Zeile).
"""
from __future__ import annotations

import contextlib
import json
import math

import pytest
import yaml

from telco_radar.report.html import render_site

from test_geraete_o1_hauptgraph_browser import (
    HEUTE, _chromium, _KATALOG, _FARBEN, _listung, _QUELLEN, _server, _sku)

# DREI Modelle mit eigenen Bündeln — je Modell eine andere Anbietermenge,
# damit der Test misst, dass die Zeilen MITGEWECHSELT werden (S3), nicht
# nur sichtbar bleiben:
#   apple-iphone-17-pro 256 (VORGABE): o2 klein, Vodafone klein (Referenz),
#       congstar mittel, o2 unbegrenzt (ohne Band)
#   samsung-galaxy-s26 256:            1&1 klein
#   google-pixel-11 256:               congstar klein, o2 mittel
_BUENDEL = [
    ("apple-iphone-17-pro", 256, "o2", "o2:klein", "O2 Mobile Klein",
     10, 18.0),
    ("apple-iphone-17-pro", 256, "Vodafone", "vf:klein", "Vodafone Mobil XS",
     18, 26.0),
    ("apple-iphone-17-pro", 256, "congstar", "cs:mittel", "Allnet Flat S",
     50, 20.0),
    ("apple-iphone-17-pro", 256, "o2", "o2:unlimited", "O2 Unlimited",
     math.inf, 30.0),
    ("samsung-galaxy-s26", 256, "1&1", "11:klein", "All-Net-Flat S",
     10, 15.0),
    ("google-pixel-11", 256, "congstar", "cs:klein2", "Allnet Flat XS",
     8, 12.0),
    ("google-pixel-11", 256, "o2", "o2:mittel2", "O2 Mobile M",
     40, 22.0),
]

_ERWARTET = {
    "apple-iphone-17-pro-256": {"o2", "Vodafone", "congstar"},
    "samsung-galaxy-s26-256": {"1&1"},
    "google-pixel-11-256": {"congstar", "o2"},
}


def _baue(tmp_path):
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
    listungen = [
        _listung("Vodafone", "apple-iphone-17-pro", 256, 1199.90),
        _listung("o2", "apple-iphone-17-pro", 256, 1099.00),
        _listung("1&1", "samsung-galaxy-s26", 256, 1049.00),
    ]
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE, "anbieter": {
            n: {"laeufe": 4, "funde_gesamt": 1}
            for n in ("Vodafone", "o2", "1&1", "congstar")},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = []
    for device_id, speicher, anbieter, tarif_id, tarif, gb, rate in _BUENDEL:
        buendel.append({
            "id": f"buendel--{anbieter.lower()}--{_sku(device_id, speicher)}"
                  f"--{tarif_id}",
            "sku_id": _sku(device_id, speicher), "anbieter": anbieter,
            "tarif_name": tarif, "tarif_id": tarif_id,
            "tarif_id_guete": "hoch", "tarif_monatlich": 24.99,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": rate,
            "laufzeit_monate": 24, "anschlusspreis": 0.0,
            "zustand": "neu", "rabatte": [],
            "quelle_url": f"https://example.de/{anbieter.lower()}/{device_id}",
            "abgerufen_am": HEUTE, "first_seen": HEUTE,
            "last_verified": HEUTE})
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    tarife = [
        {"anbieter": anbieter, "name": tarif, "tarif_id": tarif_id,
         "art": "mobilfunk", "grundgebuehr": 24.99, "laufzeit_monate": 24,
         "datenvolumen_gb": gb,
         "preisphasen": [{"von_monat": 1, "bis_monat": None,
                          "betrag": 24.99}],
         "dokument_url": f"https://example.de/pib/{tarif_id}",
         "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}
        for _d, _s, anbieter, tarif_id, tarif, gb, _r in _BUENDEL
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


@contextlib.contextmanager
def _browser_ctx(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    site = _baue(tmp_path_factory.mktemp("o3rollen"))
    exe = _chromium()
    with _server(site) as wurzel, sync_playwright() as p:
        # Dasselbe Muster wie der O1-Browsertest: `launch()` ohne Pfad
        # nimmt den von Playwright verwalteten Browser (auf dem Mac der
        # einzige Fund - `_chromium()` kennt nur die Linux-Ablagen).
        try:
            browser = (p.chromium.launch(executable_path=exe) if exe
                       else p.chromium.launch())
        except Exception:                    # noqa: BLE001
            pytest.skip("kein Chromium gefunden")
        try:
            yield site, wurzel, browser
        finally:
            browser.close()


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    with _browser_ctx(tmp_path_factory) as c:
        yield c


@pytest.fixture()
def seite(ctx):
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        s.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
        yield s
    finally:
        s.close()


def _zeilen_anbieter(s):
    """Die Anbieter ALLER Bündelzeilen des gewählten Modells - OHNE
    hidden-Filter: die Bandwahl versteckt Zeilen anderer Bänder, und der
    Test misst die EIGENTÜMERSCHAFT der Zeilen (gehören sie zum gewählten
    Modell?), nicht ihre Sichtbarkeit im aktuellen Band."""
    return s.eval_on_selector_all(
        "#gr-buendel .gr-bnd",
        "e => e.map(z => z.dataset.anbieter)")


# --------------------------------------------------------------------------
# A (S3): Modellwechsel zeigt EIGENE Zeilen
# --------------------------------------------------------------------------

def test_rueckwechsel_nach_deep_link_zeigt_die_vorgabezeilen(seite):
    """S2 (O3-Evaluation): der Vorgabe-Klon wurde bislang erst IM Vorgabe-
    Durchlauf von `setzeBuendel` gezogen - bei einem Deep-Link auf ein
    FREMDmodell (genau das, was jeder der 88 Radar-Querlinks tut) war der
    erste Durchlauf fremd, und der Rückwechsel klonte dann die FREMDEN
    Zeilen als „Vorgabe". Der Evaluationsfall am echten Bestand: Deep-Link
    auf samsung-galaxy-a56-128, Rückkehr zum Vorgabegerät - Titel und
    Graph sagten iPhone 17 Pro, die Tabelle zeigte die EINE a56-Zeile
    (664,75 €), die 19 Zeilen des Vorgabegeräts fehlten. Hier dieselbe
    Kombination an der Fixture: Zeilenzahl UND Werte müssen nach dem
    Rückweg dem Server-Stand des Vorgabemodells entsprechen."""
    ursprung = seite.eval_on_selector_all(
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.gesamt)")
    assert len(ursprung) == 4, \
        f"die Vorgabe-Fixture trägt 4 Zeilen, nicht {len(ursprung)}"
    # Der Deep-Link, wie ihn jeder Radar-Querlink setzt:
    seite.goto(seite.url + "?modell=samsung-galaxy-s26-256",
               wait_until="networkidle")
    seite.wait_for_timeout(300)
    fremd = seite.eval_on_selector_all(
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.gesamt)")
    assert len(fremd) == 1, f"Deep-Link zeigt nicht das Fremdmodell: {fremd}"
    # Rückkehr zum Vorgabegerät - der eine Schritt, der den Klon brauchte:
    seite.select_option("#gr-modell", "apple-iphone-17-pro-256")
    seite.wait_for_timeout(300)
    danach = seite.eval_on_selector_all(
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.gesamt)")
    assert danach == ursprung, \
        f"Rückweg nach Deep-Link: {danach} statt dem Vorgabe-Stand {ursprung}"


@pytest.mark.parametrize("mid,erwartet", sorted(_ERWARTET.items()))
def test_der_modellwechsel_zeigt_die_eigenen_zeilen(seite, mid, erwartet):
    """S3, die Evaluator-Auflage: Für JEDES wählbare Gerät stehen seine
    eigenen Bündelzeilen da — nicht die des Vorgabegeräts, nicht eine
    Fehlermeldung, nicht versteckt."""
    seite.select_option("#gr-modell", mid)
    seite.wait_for_timeout(300)
    assert seite.eval_on_selector("#gr-buendel", "e => !e.hidden")
    anbieter = set(_zeilen_anbieter(seite))
    assert anbieter == erwartet, \
        f"{mid}: {sorted(anbieter)} statt {sorted(erwartet)}"
    # Der Tabellentitel nennt das GEWÄHLTE Gerät (die Fixture kennt die
    # Katalogeinträge nicht - der Titel trägt dann die device-id, die
    # enthält den Modell-Slug immer).
    titel = seite.eval_on_selector("#gr-bnd-titel", "e => e.textContent")
    assert mid.split("-256")[0].replace("-", " ") in " ".join(
        titel.lower().split()), titel


def test_zurueck_zur_vorgabe_zeigt_die_vorgabezeilen(seite):
    """Der Weg zurück darf kein Modell 'stehen lassen': nach zwei Wechseln
    steht wieder der Original-Inhalt der Seite (aus dem Cache, ohne neue
    Anfrage)."""
    seite.select_option("#gr-modell", "samsung-galaxy-s26-256")
    seite.wait_for_timeout(250)
    seite.select_option("#gr-modell", "apple-iphone-17-pro-256")
    seite.wait_for_timeout(250)
    assert set(_zeilen_anbieter(seite)) == _ERWARTET[
        "apple-iphone-17-pro-256"]


def test_der_deep_link_oeffnet_das_angegebene_modell(ctx):
    """B5: geraete.html?modell=<id> öffnet die Seite MIT DIESEM Modell —
    der Selektor, der Titel und die Zeilen gehören zusammen."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        s.goto(f"{wurzel}/geraete.html?modell=google-pixel-11-256",
               wait_until="networkidle")
        s.wait_for_timeout(300)
        assert s.eval_on_selector("#gr-modell", "e => e.value") == \
            "google-pixel-11-256"
        titel = s.eval_on_selector("#gr-tco-titel", "e => e.textContent")
        assert "pixel" in titel.lower(), titel
        assert set(_zeilen_anbieter(s)) == _ERWARTET["google-pixel-11-256"]
    finally:
        s.close()


def test_der_querlink_des_radars_deep_linket(ctx):
    """B5 im Ganzen: der Querlink auf wettbewerbsradar.html trägt
    ?modell=<id>, und der führt auf der Geräteseite zu genau dem Modell,
    dessen Block ihn trägt."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        s.goto(f"{wurzel}/wettbewerbsradar.html", wait_until="networkidle")
        links = s.eval_on_selector_all(
            "a[href^='geraete.html?modell=']", "e => e.map(a => a.href)")
        assert links, "der Radar trägt keinen Querlink"
        ziel = links[0]
        s.goto(ziel, wait_until="networkidle")
        s.wait_for_timeout(300)
        gewollt = ziel.split("modell=", 1)[1]
        assert s.eval_on_selector("#gr-modell", "e => e.value") == gewollt
    finally:
        s.close()


# --------------------------------------------------------------------------
# C: sortierbare Bündeltabelle
# --------------------------------------------------------------------------

def test_die_sortierung_ordnet_ohne_reload(seite):
    """C: TCO-24 (Server-Default, bleibt), Δ und Anbieter sortierbar per
    Kopfknopf — ohne Reload. Ein gesetztes window-Flag überlebt nur ohne
    Navigation. Gemessen wird die BANDLISTE (`#gr-bndliste`): die
    Ohne-Band-Gruppe darunter ist eine eigene Liste mit eigenem Kopf."""
    seite.evaluate("window.__o3_kein_reload = 1")
    # Voraussetzung: mehr als eine sichtbare Zeile, Default nach TCO-24
    werte = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden])",
        "e => e.map(z => parseFloat(z.dataset.gesamt))")
    assert len([w for w in werte if w is not None]) >= 2
    assert werte == sorted(werte), "Server-Vorsortierung nach TCO-24 fehlt"

    seite.click("#gr-buendel .gr-bnd-kopf button[data-bsort='anbieter']")
    seite.wait_for_timeout(120)
    namen = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden])",
        "e => e.map(z => z.dataset.anbieter)")
    # localeCompare('de') im Browser - alphabetisch, nicht nach Codepoint
    # (sonst stünde 'Vodafone' vor 'congstar'; Python sorted() misst das
    # anders als der Leser liest).
    assert namen == sorted(namen, key=str.lower), \
        f"Anbieter-Sortierung greift nicht: {namen}"

    seite.click("#gr-buendel .gr-bnd-kopf button[data-bsort='tco']")
    seite.wait_for_timeout(120)
    werte = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden])",
        "e => e.map(z => parseFloat(z.dataset.gesamt))")
    assert werte == sorted(werte), "TCO-Sortierung greift nicht"
    assert seite.evaluate("window.__o3_kein_reload") == 1, \
        "die Sortierung hat die Seite neu geladen"


def test_die_delta_sortierung_stellt_den_guenstigsten_nach_vorn(seite):
    """C: Δ aufsteigend heißt: der negativste Abstand zur Vodafone-Referenz
    zuerst. Zeilen ohne Δ (Referenz, Näherung) stehen dahinter."""
    seite.click("#gr-buendel .gr-bnd-kopf button[data-bsort='delta']")
    seite.wait_for_timeout(120)
    deltas = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden])",
        "e => e.map(z => z.dataset.delta === '' ? null : "
        "parseFloat(z.dataset.delta))")
    zahlwerte = [d for d in deltas if d is not None]
    assert zahlwerte, "keine Zeile mit Δ in der Fixture"
    assert zahlwerte == sorted(zahlwerte), deltas
    # Die Zeilen OHNE Δ stehen am Ende, nicht in der Mitte.
    assert deltas[len(zahlwerte):] == [None] * (len(deltas) - len(zahlwerte)), \
        deltas


# --------------------------------------------------------------------------
# B: Reiter, Verlauf, Falz, Querscroll
# --------------------------------------------------------------------------

def test_der_verlaufs_reiter_ist_erreichbar(seite):
    """B2: Der Knopf existiert, die Tafel ist erreichbar und nicht tot —
    hier der ehrliche Leerzustand (die Fixture trägt keine Messreihen)."""
    assert seite.eval_on_selector(
        ".gr-reiter [data-tafel='tafel-verlauf']", "e => !!e")
    seite.click(".gr-reiter [data-tafel='tafel-verlauf']")
    seite.wait_for_timeout(120)
    sichtbar = seite.eval_on_selector("#tafel-verlauf", "e => !e.classList"
                                      ".contains('gr-tafel--aus')")
    assert sichtbar
    inhalt = seite.eval_on_selector(
        "#tafel-verlauf", "e => e.innerText.slice(0, 2000)")
    assert ("Wählen Sie oben ein Gerät" in inhalt
            or "liegen noch keine Messreihen vor" in inhalt
            or "keine Reihe aus Gerät und Anbieter" in inhalt), \
        "die Verlaufs-Tafel ist leer ohne Auskunft"


def test_kein_querscroll_auf_dem_telefon_geraete(ctx):
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        s.goto(f"{wurzel}/geraete.html", wait_until="load")
        s.wait_for_timeout(400)
        quer = s.evaluate(
            "Math.max(document.documentElement.scrollWidth,"
            "document.body.scrollWidth)")
        assert quer <= 391, f"geraete.html rollt waagerecht: {quer} px"
    finally:
        s.close()


def test_kein_querscroll_auf_dem_telefon_radar(ctx):
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        s.goto(f"{wurzel}/wettbewerbsradar.html", wait_until="load")
        s.wait_for_timeout(400)
        quer = s.evaluate(
            "Math.max(document.documentElement.scrollWidth,"
            "document.body.scrollWidth)")
        assert quer <= 391, f"wettbewerbsradar.html rollt waagerecht: {quer} px"
    finally:
        s.close()


def test_die_erste_balkenzeile_bleibt_ueber_der_telefon_falz(ctx):
    """11c am eigenen Maß: Untertitel + vierter Reiter kosten Höhe über
    der ersten Balkenzeile — die Leitantwort (A1) geht vor. Der Entwurfs-
    Schwester-Link ist auf dem Telefon bewusst weg (derselbe Link steht
    als Quasi-Reiter daneben); gemessen wird, nicht behauptet."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        s.goto(f"{wurzel}/geraete.html", wait_until="load")
        s.wait_for_timeout(400)
        box = s.evaluate("""() => {
          const e = document.querySelector('#tafel-tco .gr-bz');
          if (!e) return null;
          return Math.round(e.getBoundingClientRect().bottom);
        }""")
        assert box is not None and box <= 844, \
            f"die erste Balkenzeile endet bei {box} px (Falz 844)"
    finally:
        s.close()


def test_details_ueber_der_falz_bleibt_es_hoechstens_einer(ctx):
    """A2/O2-Maßstab bleibt: höchstens EIN Aufklapper über der Falz, am
    Telefon UND am Schirm — der Untertitel darf die Zahl nicht ändern."""
    _site, wurzel, browser = ctx
    for breite in (1440, 390):
        s = browser.new_page(viewport={"width": breite, "height": 844})
        try:
            s.goto(f"{wurzel}/geraete.html", wait_until="load")
            s.wait_for_timeout(400)
            zahl = s.evaluate(
                "[...document.querySelectorAll('details')]"
                ".filter(d => { const r = d.getBoundingClientRect();"
                "              return r.top < 844 && r.bottom > 0; }).length")
            assert zahl <= 1, \
                f"{breite}px: {zahl} Aufklapper über der Falz (erlaubt 1)"
        finally:
            s.close()
