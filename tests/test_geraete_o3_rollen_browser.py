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

from tarifleiter_testbestand import mit_leiter
import yaml

from telco_radar.report.html import render_site

from test_geraete_browser_fixture import (
    HEUTE,
    _KATALOG,
    _FARBEN,
    _listung,
    _QUELLEN,
    _server,
    _sku,
)
from test_geraete_zeitreihe_browser import waehle_band, waehle_modell

_BUENDEL = [
    ("apple-iphone-17-pro", 256, "o2", "o2:klein", "O2 Mobile Klein", 10, 18.0),
    ("apple-iphone-17-pro", 256, "Vodafone", "vf:klein", "Vodafone Mobil XS", 18, 26.0),
    ("apple-iphone-17-pro", 256, "congstar", "cs:mittel", "Allnet Flat S", 50, 20.0),
    ("apple-iphone-17-pro", 256, "o2", "o2:unlimited", "O2 Unlimited", math.inf, 30.0),
    ("samsung-galaxy-s26", 256, "1&1", "11:klein", "All-Net-Flat S", 10, 15.0),
    ("google-pixel-11", 256, "congstar", "cs:klein2", "Allnet Flat XS", 8, 12.0),
    ("google-pixel-11", 256, "o2", "o2:mittel2", "O2 Mobile M", 40, 22.0),
]

_ERWARTET = {
    "apple-iphone-17-pro-256": {"o2", "Vodafone", "congstar"},
    "samsung-galaxy-s26-256": {"1&1"},
    "google-pixel-11-256": {"congstar", "o2"},
}


def _baue(tmp_path):
    root = tmp_path / "site_baum"
    (root / "config").mkdir(parents=True)
    for name, daten in (
        ("geraete_katalog.yaml", _KATALOG),
        ("farben.yaml", _FARBEN),
        ("geraete_quellen.yaml", _QUELLEN),
    ):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    state = root / "data" / "state"
    state.mkdir(parents=True)
    listungen = [
        _listung("Vodafone", "apple-iphone-17-pro", 256, 1199.90),
        _listung("o2", "apple-iphone-17-pro", 256, 1099.00),
        _listung("1&1", "samsung-galaxy-s26", 256, 1049.00),
    ]
    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": HEUTE,
                "anbieter": {
                    n: {"laeufe": 4, "funde_gesamt": 1}
                    for n in ("Vodafone", "o2", "1&1", "congstar")
                },
                "listungen": listungen,
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = []
    for device_id, speicher, anbieter, tarif_id, tarif, gb, rate in _BUENDEL:
        buendel.append(
            {
                "id": f"buendel--{anbieter.lower()}--{_sku(device_id, speicher)}"
                f"--{tarif_id}",
                "sku_id": _sku(device_id, speicher),
                "anbieter": anbieter,
                "tarif_name": tarif,
                "tarif_id": tarif_id,
                "tarif_id_guete": "hoch",
                "tarif_monatlich": 24.99,
                "geraet_zuzahlung": 1.0,
                "geraet_monatsrate": rate,
                "laufzeit_monate": 24,
                "anschlusspreis": 0.0,
                "zustand": "neu",
                "rabatte": [],
                "quelle_url": f"https://example.de/{anbieter.lower()}/{device_id}",
                "abgerufen_am": HEUTE,
                "first_seen": HEUTE,
                "last_verified": HEUTE,
            }
        )
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8",
    )
    tarife = [
        {
            "anbieter": anbieter,
            "name": tarif,
            "tarif_id": tarif_id,
            "art": "mobilfunk",
            "grundgebuehr": 24.99,
            "laufzeit_monate": 24,
            "datenvolumen_gb": gb,
            "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 24.99}],
            "dokument_url": f"https://example.de/pib/{tarif_id}",
            "abgerufen_am": HEUTE,
            "confidence": {},
            "fundstellen": {},
        }
        for _d, _s, anbieter, tarif_id, tarif, gb, _r in _BUENDEL
    ]
    tarife = mit_leiter(tarife)
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8"
    )
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(
        json.dumps(
            {
                "date": HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@contextlib.contextmanager
def _browser_ctx(tmp_path_factory, chromium):
    site = _baue(tmp_path_factory.mktemp("o3rollen"))
    with _server(site) as wurzel:
        yield site, wurzel, chromium


@pytest.fixture(scope="module")
def ctx(tmp_path_factory, chromium):
    with _browser_ctx(tmp_path_factory, chromium) as c:
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
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.anbieter)"
    )


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
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.gesamt)"
    )
    assert len(ursprung) == 4, (
        f"die Vorgabe-Fixture trägt 4 Zeilen, nicht {len(ursprung)}"
    )
    seite.goto(
        seite.url.split("?")[0] + "?modell=samsung-galaxy-s26-256",
        wait_until="networkidle",
    )
    seite.wait_for_timeout(300)
    fremd = seite.eval_on_selector_all(
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.gesamt)"
    )
    assert len(fremd) == 1, f"Deep-Link zeigt nicht das Fremdmodell: {fremd}"
    waehle_modell(seite, "apple-iphone-17-pro-256")
    seite.wait_for_timeout(300)
    danach = seite.eval_on_selector_all(
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.gesamt)"
    )
    assert danach == ursprung, (
        f"Rückweg nach Deep-Link: {danach} statt dem Vorgabe-Stand {ursprung}"
    )


@pytest.mark.parametrize("mid,erwartet", sorted(_ERWARTET.items()))
def test_der_modellwechsel_zeigt_die_eigenen_zeilen(seite, mid, erwartet):
    """S3, die Evaluator-Auflage: Für JEDES wählbare Gerät stehen seine
    eigenen Bündelzeilen da — nicht die des Vorgabegeräts, nicht eine
    Fehlermeldung, nicht versteckt."""
    waehle_modell(seite, mid)
    seite.wait_for_timeout(300)
    assert seite.eval_on_selector("#gr-buendel", "e => !e.hidden")
    anbieter = set(_zeilen_anbieter(seite))
    assert anbieter == erwartet, f"{mid}: {sorted(anbieter)} statt {sorted(erwartet)}"
    titel = seite.eval_on_selector("#gr-bnd-titel", "e => e.textContent")
    assert mid.split("-256")[0].replace("-", " ") in " ".join(titel.lower().split()), (
        titel
    )


def test_zurueck_zur_vorgabe_zeigt_die_vorgabezeilen(seite):
    """Der Weg zurück darf kein Modell 'stehen lassen': nach zwei Wechseln
    steht wieder der Original-Inhalt der Seite (aus dem Cache, ohne neue
    Anfrage)."""
    waehle_modell(seite, "samsung-galaxy-s26-256")
    seite.wait_for_timeout(250)
    waehle_modell(seite, "apple-iphone-17-pro-256")
    seite.wait_for_timeout(250)
    assert set(_zeilen_anbieter(seite)) == _ERWARTET["apple-iphone-17-pro-256"]


def test_der_deep_link_oeffnet_das_angegebene_modell(ctx):
    """B5: geraete.html?modell=<id> öffnet die Seite MIT DIESEM Modell —
    der Selektor, der Titel und die Zeilen gehören zusammen."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        s.goto(
            f"{wurzel}/geraete.html?modell=google-pixel-11-256",
            wait_until="networkidle",
        )
        s.wait_for_timeout(300)
        assert "modell=google-pixel-11-256" in s.url
        antwort = s.eval_on_selector("#tafel-tco .gr-zr-antwort", "e => e.textContent")
        assert "Pixel 11" in antwort, antwort
        assert set(_zeilen_anbieter(s)) == _ERWARTET["google-pixel-11-256"]
    finally:
        s.close()


def test_der_querlink_des_radars_deep_linket(ctx):
    """B5 im Ganzen (E3-Fassung): der Sprung-Link je Modell-Zeile der
    Abweichungsliste trägt ?modell=<id>, und der führt zu genau dem
    Modell, dessen Zeile ihn trägt. Bis E3 Schritt 3 standen die Links auf
    wettbewerbsradar.html (Seitenwechsel); der Radar ist jetzt der Reiter
    - der Sprung bleibt ein Deep-Link, app.js wechselt nur in-page."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        s.goto(f"{wurzel}/geraete.html#tafel-radar", wait_until="networkidle")
        s.wait_for_timeout(150)
        links = s.eval_on_selector_all(
            "#wr-abweichung a.gr-sprung[href^='geraete.html?modell=']",
            "e => e.map(a => a.href)",
        )
        assert links, "die Modell-Liste trägt keinen Sprung-Link"
        ziel = links[0]
        s.goto(ziel, wait_until="networkidle")
        s.wait_for_timeout(300)
        gewollt = ziel.split("modell=", 1)[1].split("&", 1)[0]
        assert f"modell={gewollt}" in s.url
        assert set(_zeilen_anbieter(s)) == _ERWARTET[gewollt], (
            gewollt,
            sorted(_zeilen_anbieter(s)),
        )
    finally:
        s.close()


def test_die_sortierung_ordnet_ohne_reload(seite):
    """C: TCO-24 (Server-Default, bleibt), Δ und Anbieter sortierbar per
    Kopfknopf — ohne Reload. Ein gesetztes window-Flag überlebt nur ohne
    Navigation. Gemessen wird die BANDLISTE (`#gr-bndliste`): die
    Ohne-Band-Gruppe darunter ist eine eigene Liste mit eigenem Kopf."""
    seite.evaluate(
        "() => {const b = document.querySelector('.gx-bnd-auf');"
        " if (b && b.getAttribute('aria-expanded') !== 'true') b.click();}"
    )
    seite.evaluate("window.__o3_kein_reload = 1")
    werte = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden])",
        "e => e.map(z => parseFloat(z.dataset.gesamt))",
    )
    assert len([w for w in werte if w is not None]) >= 2
    assert werte == sorted(werte), "Server-Vorsortierung nach TCO-24 fehlt"

    seite.click("#gr-buendel .gr-bnd-kopf button[data-bsort='anbieter']")
    seite.wait_for_timeout(120)
    namen = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden])", "e => e.map(z => z.dataset.anbieter)"
    )
    assert namen == sorted(namen, key=str.lower), (
        f"Anbieter-Sortierung greift nicht: {namen}"
    )

    seite.click("#gr-buendel .gr-bnd-kopf button[data-bsort='tco']")
    seite.wait_for_timeout(120)
    werte = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden])",
        "e => e.map(z => parseFloat(z.dataset.gesamt))",
    )
    assert werte == sorted(werte), "TCO-Sortierung greift nicht"
    assert seite.evaluate("window.__o3_kein_reload") == 1, (
        "die Sortierung hat die Seite neu geladen"
    )


def test_die_delta_sortierung_stellt_den_guenstigsten_nach_vorn(seite):
    """C: Δ aufsteigend heißt: der negativste Abstand zur Vodafone-Referenz
    zuerst. Zeilen ohne Δ (Referenz, Näherung) stehen dahinter."""
    seite.evaluate(
        "() => {const b = document.querySelector('.gx-bnd-auf');"
        " if (b && b.getAttribute('aria-expanded') !== 'true') b.click();}"
    )
    seite.click("#gr-buendel .gr-bnd-kopf button[data-bsort='delta']")
    seite.wait_for_timeout(120)
    deltas = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden])",
        "e => e.map(z => z.dataset.delta === '' ? null : parseFloat(z.dataset.delta))",
    )
    zahlwerte = [d for d in deltas if d is not None]
    assert zahlwerte, "keine Zeile mit Δ in der Fixture"
    assert zahlwerte == sorted(zahlwerte), deltas
    assert deltas[len(zahlwerte) :] == [None] * (len(deltas) - len(zahlwerte)), deltas


def test_der_verlaufs_reiter_ist_erreichbar(seite):
    """B2: Der Knopf existiert, die Tafel ist erreichbar und nicht tot.
    P2 (Antonio F4): Der Reiter öffnet mit einer AUSWAHL statt eines
    Leer-Satzes - die Auto-Vorauswahl wählt das erste Gerät der Liste.
    Ob daraus ein Diagramm oder (unter der Diagramm-Schwelle) Kacheln und
    Tabelle werden, entscheidet die Datenlage; geprüft wird die Regel:
    Suchfeld nennt das ERSTE Gerät, die Tabelle steht. Ohne Messreihen
    bleibt der ehrliche Leerzustand."""
    assert seite.eval_on_selector(".gr-reiter [data-tafel='tafel-verlauf']", "e => !!e")
    seite.click(".gr-reiter [data-tafel='tafel-verlauf']")
    seite.wait_for_timeout(250)
    sichtbar = seite.eval_on_selector(
        "#tafel-verlauf", "e => !e.classList.contains('gr-tafel--aus')"
    )
    assert sichtbar
    inhalt = seite.eval_on_selector("#tafel-verlauf", "e => e.innerText.slice(0, 2000)")
    if "liegen noch keine Messreihen vor" in inhalt:
        return
    erstes = seite.eval_on_selector(
        "#gr-verlaufdaten", "k => JSON.parse(k.textContent)[0].label"
    )
    assert erstes, "die Fixture legt kein waehlbares Geraet an"
    feld = seite.eval_on_selector("#gr-vsuche", "e => e.value")
    assert feld == erstes, (
        f"Auto-Vorauswahl waehlt nicht das erste Geraet: {feld!r} statt {erstes!r}"
    )
    assert seite.eval_on_selector_all("#gr-vtabelle table", "e => e.length") >= 1, (
        "die Verlaufs-Tafel öffnet ohne Diagramm und ohne Tabelle"
    )


def test_kein_querscroll_auf_dem_telefon_geraete(ctx):
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        s.goto(f"{wurzel}/geraete.html", wait_until="load")
        s.wait_for_timeout(400)
        quer = s.evaluate(
            "Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)"
        )
        assert quer <= 391, f"geraete.html rollt waagerecht: {quer} px"
    finally:
        s.close()


def test_kein_querscroll_auf_dem_telefon_radar(ctx):
    """E3 Schritt 3: die Radar-Tafel ist der Reiter der EINEN Geräteseite -
    gemessen wird sie dort (der Hash schaltet den Reiter), nicht auf der
    Alt-URL, die nur noch weiterleitet."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        s.goto(f"{wurzel}/geraete.html#tafel-radar", wait_until="load")
        s.wait_for_timeout(400)
        quer = s.evaluate(
            "Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)"
        )
        assert quer <= 391, f"der Radar-Reiter rollt waagerecht: {quer} px"
    finally:
        s.close()


def test_die_frage_der_uebersicht_steht_am_telefon_in_hoechstens_zwei_zeilen(ctx):
    """28.09.2026: bei 390 px stand die Frage des Reiters in drei Zeilen
    zu 25,5 px (109 px Höhe) über einer Leitzahl von 30 px - die Frage
    drängte sich vor ihre Antwort. Gemessen im Browser: höchstens zwei
    Zeilen, und die Leitzahl bleibt die größte Schrift."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        s.goto(f"{wurzel}/geraete.html#tafel-radar", wait_until="load")
        s.wait_for_timeout(400)
        m = s.evaluate("""() => {
          const h = document.querySelector('#tafel-radar h2.rubrik');
          const z = document.querySelector('#tafel-radar .gr-leit-zahl');
          if (!h || !z) return null;
          const cs = getComputedStyle(h);
          // Inhaltshöhe: die Rubrik trägt Linie und Innenabstand oben.
          const rand = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom)
            + parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
          return {hoehe: h.getBoundingClientRect().height - rand,
                  zeile: parseFloat(cs.lineHeight),
                  frage: parseFloat(cs.fontSize),
                  zahl: parseFloat(getComputedStyle(z).fontSize)};
        }""")
        assert m is not None, "Frage oder Leitzahl fehlt"
        assert m["zeile"] > 0, m
        assert m["hoehe"] <= 2 * m["zeile"] + 2, m
        assert m["zahl"] > m["frage"], m
    finally:
        s.close()


def test_die_balkenwerte_links_laufen_nicht_in_die_modellnamen(ctx):
    """28.09.2026: ein günstigerer Wettbewerber steht links der Vodafone-
    Linie, Wert und Laden stehen zwischen Namensspalte und Balkenende.
    Gemessen am ungünstigsten Fall (vierstelliger Abstand, langer
    Ladenname, langer Modellname) in der echten Seite: keine Überlappung.
    Geprüft wird die Eigenschaft, keine Pixelbreite (Rückfallschrift)."""
    from telco_radar.report import geraete_radar as wr

    zeilen = [
        {
            "device_id": "a",
            "speicher": 1024,
            "modell": "Galaxy S26 Ultra",
            "hersteller": "x",
            "delta": 1012.50,
            "prozent": 40.0,
            "laden": "ElectronicPartner",
            "vf_preis": 2500.0,
            "gegen_preis": 1487.50,
        },
        {
            "device_id": "b",
            "speicher": 128,
            "modell": "iPhone 16",
            "hersteller": "x",
            "delta": -30.0,
            "prozent": -3.0,
            "laden": "Saturn",
            "vf_preis": 1000.0,
            "gegen_preis": 1030.0,
        },
    ]
    svg = wr._grafik_svg(zeilen, ("a", 1024), True)
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        s.goto(f"{wurzel}/geraete.html#tafel-radar", wait_until="load")
        s.wait_for_timeout(300)
        ueber = s.evaluate(
            """svg => {
          const bild = document.querySelector('#tafel-radar .wr-grafik-bild');
          if (!bild) return null;
          bild.innerHTML = svg;
          const g = bild.querySelector('svg.wr-gr--breit');
          const namen = [...g.querySelectorAll('text.wr-gr-name')];
          const werte = [...g.querySelectorAll('text.wr-gr-wert')];
          return namen.map((n, i) => {
            const a = n.getBoundingClientRect(), b = werte[i].getBoundingClientRect();
            return {name: a.right, wert: b.left, breit: b.width};
          });
        }""",
            svg,
        )
        assert ueber, "keine Grafik auf der Seite"
        assert all(z["breit"] > 20 for z in ueber), ueber
        for z in ueber:
            assert z["wert"] >= z["name"], ueber
    finally:
        s.close()


@pytest.mark.parametrize("breite", [1440, 390])
def test_jede_buendelzeile_traegt_genau_ein_aufklappzeichen(ctx, breite):
    """28.09.2026: jede Bündelzeile trug zwei Aufklappzeichen - das „+"
    der Chevron-Zelle und das rote „▾" der Tafel-Regel, das als eigenes
    Grid-Element in eine neue Zeile unter den Anbieternamen rutschte.
    Gemessen: das ::after der Zeile IST das „+"/„−" und sitzt in der
    Chevron-Spalte, die Chevron-Zelle nimmt keinen Platz; geöffnet steht
    „−" (nicht das „▴" der Tafel-Regel), wieder zu „+"."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": breite, "height": 900})
    try:
        s.goto(f"{wurzel}/geraete.html", wait_until="load")
        s.evaluate(
            "() => {const b = document.querySelector('.gx-bnd-auf');"
            " if (b && b.getAttribute('aria-expanded') !== 'true') b.click();}"
        )
        s.wait_for_timeout(300)
        lies = """() => [...document.querySelectorAll(
            '#tafel-tco details.gr-bnd')].filter(d => d.offsetParent)
          .map(d => {
            const su = d.querySelector(':scope>summary');
            const nach = getComputedStyle(su, '::after');
            const chev = d.querySelector('.gr-bnd-chev');
            return {inhalt: nach.content, spalte: nach.gridColumnStart,
                    zeile: nach.gridRowStart,
                    chev: chev ? getComputedStyle(chev).display : 'none'};
          })"""
        m = s.evaluate(lies)
        assert m, "keine sichtbare Bündelzeile"
        for z in m:
            assert z["inhalt"] == '"+"', z
            assert z["chev"] == "none", z
            if breite > 900:
                assert z["spalte"] == "6" and z["zeile"] == "1", z
            else:
                assert z["spalte"] == "chev", z
        erste = s.locator("#tafel-tco details.gr-bnd > summary").first
        erste.click()
        s.wait_for_timeout(150)
        assert s.evaluate(lies)[0]["inhalt"] == '"−"'
        erste.click()
        s.wait_for_timeout(150)
        assert s.evaluate(lies)[0]["inhalt"] == '"+"'
    finally:
        s.close()


@pytest.mark.parametrize("breite", [390, 360, 320])
def test_der_zweite_preis_der_buendelzeile_ist_am_telefon_benannt(ctx, breite):
    """Mobil fehlt der Spaltenkopf „Gerät ohne Vertrag" - der zweite
    Euro-Betrag der Zeile stand nackt neben dem Tarif. Jetzt steht sein
    Name als eigene Zeile darüber, vor „–" steht nichts. Die Zeile läuft auch bei 320 px nicht über, und
    das Δ steht links wie sein Präfix."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": breite, "height": 844})
    try:
        s.goto(f"{wurzel}/geraete.html", wait_until="load")
        s.evaluate(
            "() => {const b = document.querySelector('.gx-bnd-auf');"
            " if (b && b.getAttribute('aria-expanded') !== 'true') b.click();}"
        )
        s.wait_for_timeout(300)
        m = s.evaluate("""() => [...document.querySelectorAll(
            '#tafel-tco details.gr-bnd')].filter(d => d.offsetParent)
          .map(d => {
            const su = d.querySelector(':scope>summary');
            const bar = su.querySelector('.gr-bnd-bar');
            const dl = su.querySelector('.gr-bnd-delta');
            const rechts = Math.max(...[...su.querySelectorAll('*')]
              .map(e => e.getBoundingClientRect().right));
            return {text: bar.textContent.trim(),
                    vor: getComputedStyle(bar, '::before').content,
                    ausrichtung: getComputedStyle(dl).textAlign,
                    ueber: rechts - su.getBoundingClientRect().right};
          })""")
        quer = s.evaluate("document.documentElement.scrollWidth")
        assert quer <= breite, f"die Seite rollt waagerecht: {quer} px"
        zahlen = [z for z in m if z["text"].endswith("€")]
        assert zahlen, m
        for z in m:
            assert z["ueber"] <= 1, z
            assert z["ausrichtung"] in ("left", "start"), z
            if z["text"].endswith("€"):
                assert z["vor"] == '"ohne Vertrag"', z
            else:
                assert z["vor"] in ("none", "normal"), z
    finally:
        s.close()


_KATALOG_MESSEN = """() => {
  const t = document.getElementById('gr-katalogtabelle');
  const box = t.parentElement.getBoundingClientRect();
  const sichtbar = e => getComputedStyle(e).display !== 'none';
  const zeilen = [...t.querySelectorAll('tbody > tr.gr-a-zeile')];
  return {
    breite: innerWidth,
    boxRechts: box.right,
    zeilen: zeilen.map(z => ({
      rest: z.classList.contains('gr-a-rest'),
      hidden: z.hidden,
      an: sichtbar(z),
      rechts: Math.max(...[...z.children].filter(sichtbar)
        .map(c => c.getBoundingClientRect().right)),
      bar: [...z.querySelectorAll('td.gr-sp--barpreis')].map(
        c => getComputedStyle(c).display),
      tco: [...z.querySelectorAll('td.gr-sp--tco')].map(
        c => getComputedStyle(c).display),
    })),
  };
}"""


def test_der_katalog_steht_am_telefon_als_karten(ctx):
    """28.09.2026: bei 390 px zeigte der Katalog nur Modell und einen
    angeschnittenen Preis („bei Satu"), der Rest der Tabelle lag rechts im
    Rollbehälter. Jetzt stapelt jede sichtbare Modellzeile ihre Zellen:
    nichts ragt über den Behälter, der Umschalter tauscht die Zellen der
    Ansicht, jede Zelle nennt ihre Spalte. Gegenprobe am Schirm: dort
    bleibt die Tabelle eine Tabelle."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        s.goto(f"{wurzel}/geraete.html#tafel-katalog", wait_until="load")
        s.evaluate("document.getElementById('tafel-katalog').scrollIntoView()")
        s.wait_for_timeout(300)
        m = s.evaluate(_KATALOG_MESSEN)
        an = [z for z in m["zeilen"] if z["an"]]
        assert an, "keine sichtbare Katalogzeile"
        for z in an:
            assert z["rechts"] <= m["boxRechts"] + 1, (z, m["boxRechts"])
            assert all(d == "none" for d in z["bar"]), z
            assert all(d == "block" for d in z["tco"]), z
        s.click(".gr-reiter [data-tafel=tafel-verlauf]")
        s.wait_for_timeout(200)
        m = s.evaluate(_KATALOG_MESSEN)
        for z in (z for z in m["zeilen"] if z["an"]):
            assert all(d == "block" for d in z["bar"]), z
            assert all(d == "none" for d in z["tco"]), z
        s.click(".gr-reiter [data-tafel=tafel-tco]")
        s.wait_for_timeout(200)
        etikett = s.evaluate("""() => getComputedStyle(document.querySelector(
          '#gr-katalogtabelle tr.gr-a-zeile td.gr-sp--tco'), '::before').content""")
        kopf = s.evaluate("""() => document.querySelector(
          '#gr-katalogtabelle thead th.gr-sp--tco').textContent.replace(/\\s+/g, ' ').trim()""")
        assert kopf.startswith("Kosten über"), kopf
        assert etikett.strip('" ') == kopf, (etikett, kopf)
    finally:
        s.close()
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        s.goto(f"{wurzel}/geraete.html#tafel-katalog", wait_until="load")
        s.evaluate("document.getElementById('tafel-katalog').scrollIntoView()")
        s.wait_for_timeout(300)
        m = s.evaluate(_KATALOG_MESSEN)
        an = [z for z in m["zeilen"] if z["an"]]
        assert an and all(d == "table-cell" for z in an for d in z["tco"]), an
    finally:
        s.close()


_KARTE_ANZEIGE = """() => {
  const z = document.querySelector('#gr-katalogtabelle tbody tr.gr-a-zeile');
  return getComputedStyle(z).display;
}"""


def test_katalogkarten_folgen_den_sichtbarkeitsregeln_der_tabelle(ctx):
    """Die Karten fassen die Zeile selbst nicht an: gefiltert ([hidden])
    und hinter dem Deckel (`gr-a-rest`) ist sie weg, mit „alle zeigen"
    wieder da. Die Fixture hat weniger Modelle als der Deckel und keinen
    Filter, also setzt der Test beide Zustände selbst - sonst prüfte die
    Schleife nichts."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        s.goto(f"{wurzel}/geraete.html#tafel-katalog", wait_until="load")
        s.evaluate("document.getElementById('tafel-katalog').scrollIntoView()")
        s.wait_for_timeout(300)
        assert s.evaluate(_KARTE_ANZEIGE) != "none"
        s.evaluate("""() => { document.querySelector(
          '#gr-katalogtabelle tbody tr.gr-a-zeile').hidden = true; }""")
        assert s.evaluate(_KARTE_ANZEIGE) == "none"
        s.evaluate("""() => { const z = document.querySelector(
          '#gr-katalogtabelle tbody tr.gr-a-zeile');
          z.hidden = false; z.classList.add('gr-a-rest'); }""")
        assert s.evaluate(_KARTE_ANZEIGE) == "none"
        s.evaluate("""() => document.getElementById('gr-katalogtabelle')
          .classList.add('gr-alarm--alle')""")
        assert s.evaluate(_KARTE_ANZEIGE) != "none"
    finally:
        s.close()


def test_aufgeklappte_katalogkarte_rollt_in_sich_und_ziel_ist_markiert(ctx):
    """Die breite Listungstabelle einer aufgeklappten Karte schob die ganze
    Katalogtabelle auf 562 px; sie rollt jetzt in ihrer eigenen Box. Und
    der Radar-Sprung markiert die Zielkarte am Telefon (der rote Rahmen
    der Tabellenzeile fiel mit `border:0` der Kartenzellen weg)."""
    _site, wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        s.goto(f"{wurzel}/geraete.html#tafel-katalog", wait_until="load")
        s.evaluate("document.getElementById('tafel-katalog').scrollIntoView()")
        s.wait_for_timeout(300)
        s.focus("#gr-katalogtabelle tbody tr.gr-a-zeile:not(.gr-k--ohne-details)")
        s.keyboard.press("Enter")
        s.wait_for_timeout(200)
        m = s.evaluate("""() => {
          const t = document.getElementById('gr-katalogtabelle');
          const auf = t.querySelector('tr.gr-a-auf--an');
          const liste = auf.querySelector('.gr-k-listungen');
          return {tabelle: t.getBoundingClientRect().width,
                  box: t.parentElement.clientWidth,
                  auf: getComputedStyle(auf).display,
                  liste: liste.getBoundingClientRect().width,
                  seite: document.documentElement.scrollWidth};
        }""")
        assert m["auf"] != "none", m
        assert m["liste"] > m["box"], m
        assert m["tabelle"] <= m["box"] + 1, m
        assert m["seite"] <= 390, m
        oben = s.evaluate("""() => parseFloat(getComputedStyle(document.querySelector(
          '#gr-katalogtabelle tr.gr-a-zeile > td')).paddingTop)""")
        assert oben >= 8, oben
        ziel = s.evaluate("""() => {
          const z = document.querySelector('#gr-katalogtabelle tr.gr-k-zeile');
          const td = z.querySelector('td');
          const vorher = getComputedStyle(td).boxShadow;
          z.classList.add('gr-k-ziel');
          const text = td.querySelector('.gr-a-modell').getBoundingClientRect().left;
          return {vorher, nachher: getComputedStyle(td).boxShadow,
                  abstand: text - td.getBoundingClientRect().left};
        }""")
        assert ziel["vorher"] == "none" and ziel["nachher"] != "none", ziel
        assert ziel["abstand"] >= 6, ziel
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
        s.evaluate(
            "() => window.scrollTo(0, document.getElementById('tco')"
            ".getBoundingClientRect().top + window.scrollY)"
        )
        s.wait_for_timeout(400)
        box = s.evaluate("""() => {
          const e = document.querySelector('#tafel-tco .gr-zr-antwort');
          if (!e) return null;
          return Math.round(e.getBoundingClientRect().bottom);
        }""")
        assert box is not None and box <= 844, (
            f"der Antwort-Satz endet bei {box} px (Falz 844)"
        )
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
                "[...document.querySelectorAll('details:not(.gr-bnd)')]"
                ".filter(d => { const r = d.getBoundingClientRect();"
                "              return r.top < 844 && r.bottom > 0; }).length"
            )
            assert zahl <= 1, f"{breite}px: {zahl} Aufklapper über der Falz (erlaubt 1)"
        finally:
            s.close()
