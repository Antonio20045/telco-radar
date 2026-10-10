"""O2 (STRATEGIE_GERAETE_OPTIK §3, 11.09.2026): die Bündel-Zeilen im echten
Chromium - dieselbe Bauform wie `tests/test_geraete_o1_hauptgraph_browser.py`:
eigener Server auf 127.0.0.1, kein `file://`, kein Netz, Chromium an beiden
bekannten Orten gesucht (diese Helfer werden von dort importiert).

Die Abnahmekriterien des O2-Auftrags, hier als Messung:
  A1  <details> über der Falz (1440x900 UND 390x844) höchstens EINER -
      O1 erreichte 0/1, O2 hält das (die Zeilen-Aufklapper stehen unter
      dem Graphen, also unter der Falz).
  A2  <details> gesamt im Hauptpfad deutlich unter 100 - am VORGABEMODELL
      der Fixture nachgezählt (eine Zeile je Bündel).
  Mobil 390: Zeilen stapeln (Entwurf `.bnd summary` grid-areas), kein
      Querscroll.

Die EIGENE Fixture erweitert die O1-Lage um eine Zeile OHNE Band am
Vorgabemodell (unbegrenzter Tarif, §7): die Gruppe unter der Bandliste
braucht ihren eigenen Fall, und die O1-Fixture durfte nicht geändert
werden - ihre Zahlen stehen in O1-Tests.

Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite (Antonio):
unter dem Graphen steht nur die Zeile der fehlenden Anbieter. Was der
Browser an den Bündelzeilen maß, prüfen die Tests statisch am Fragment
`data/geraete-buendel.html`; was auf der Seite bleibt, misst weiter Chromium.
"""

from __future__ import annotations

import contextlib
import json
import math

import pytest
from bs4 import BeautifulSoup

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
from test_geraete_tco_zustand import vorlage_text
from test_geraete_zeitreihe_browser import waehle_band, waehle_modell

_BAENDER_BUENDEL = [
    ("apple-iphone-17-pro", 256, "o2", "o2:klein", "O2 Mobile Klein", 10, 18.0),
    ("apple-iphone-17-pro", 256, "Vodafone", "vf:klein", "Vodafone Mobil XS", 18, 26.0),
    ("apple-iphone-17-pro", 256, "congstar", "cs:mittel", "Allnet Flat S", 50, 20.0),
    ("apple-iphone-17-pro", 256, "o2", "o2:unlimited", "O2 Unlimited", math.inf, 30.0),
    ("samsung-galaxy-s26", 256, "1&1", "11:klein", "All-Net-Flat S", 10, 15.0),
]


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
                    for n in ("Vodafone", "o2", "1&1")
                },
                "listungen": listungen,
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = []
    for device_id, speicher, anbieter, tarif_id, tarif, gb, rate in _BAENDER_BUENDEL:
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
        for _d, _s, anbieter, tarif_id, tarif, gb, _r in _BAENDER_BUENDEL
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
def _browser_ctx(site, chromium):
    with _server(site) as basis:
        yield chromium, basis


@pytest.fixture(scope="module")
def _site(tmp_path_factory):
    return _baue(tmp_path_factory.mktemp("o2zeilen"))


@pytest.fixture(scope="module")
def _browser_seite(_site, chromium):
    with _browser_ctx(_site, chromium) as paar:
        yield paar


@pytest.fixture(scope="module")
def fragment(_site):
    """Das Bündel-Fragment mit den Zeilen aller Modelle."""
    pfad = _site / "data" / "geraete-buendel.html"
    return BeautifulSoup(pfad.read_text(encoding="utf-8"), "html.parser")


@pytest.fixture(scope="module")
def vorgabe(fragment):
    """Die Bündelzeilen des Startmodells im Fragment (`#gr-bnd-vorgabe`)."""
    lager = fragment.select_one("#gr-bnd-vorgabe")
    assert lager is not None, "das Fragment trägt kein Startmodell"
    return lager


def _sichtbare_fehlende(s) -> list:
    """Die sichtbaren Zeilen der fehlenden Anbieter unter dem Graphen."""
    return s.evaluate("""() => Array.from(
      document.querySelectorAll('#gr-bnd-gruppe .gr-anb-fehlt'))
      .filter(z => z.getClientRects().length > 0
                   && getComputedStyle(z).display !== 'none')
      .map(z => ({anbieter: z.dataset.anbieter, band: z.dataset.band,
                  lz: z.dataset.fehltLz}))""")


@pytest.fixture
def seite(_browser_seite):
    browser, basis = _browser_seite
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    s.goto(f"{basis}/geraete.html", wait_until="load")
    s.click(".gr-reiter button[data-tafel='tafel-tco']")
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def telefon(_browser_seite):
    browser, basis = _browser_seite
    s = browser.new_page(viewport={"width": 390, "height": 844})
    s.goto(f"{basis}/geraete.html", wait_until="load")
    s.click(".gr-reiter button[data-tafel='tafel-tco']")
    try:
        yield s
    finally:
        s.close()


@pytest.mark.parametrize("fixture_name", ["seite", "telefon"])
def test_hoechstens_ein_aufklapper_ueber_der_falz(fixture_name, request):
    """O2 hielt A1 von O1; E2 verschiebt die Grenze um eine Kategorie: die
    Bündel-ZEILEN sind Aufklapper des INHALTS (§3.1b) und dürfen über die
    Falz ragen - Erklärlast darf es nicht. Über der Falz bleibt höchstens
    der EINE Rechenschafts-Aufklapper 'So gerechnet'."""
    s = request.getfixturevalue(fixture_name)
    falz = s.viewport_size["height"]
    ueber = s.evaluate(
        """(falz) => Array.from(
        document.querySelectorAll('#tafel-tco details'))
        .filter(d => {
          if (d.classList.contains('gr-bnd')) return false;
          const b = d.getBoundingClientRect();
          return b.height > 0 && b.top < falz;
        }).map(d => d.className)""",
        falz,
    )
    assert len(ueber) <= 1, (
        f"{len(ueber)} Erklär-Aufklapper über der Falz ({falz} px): {ueber}"
    )


@pytest.mark.parametrize("fixture_name", ["seite", "telefon"])
def test_die_erste_buendelzeile_ist_ohne_scroll_erreichbar(fixture_name, request):
    """Der Entwurf will die Tabelle UNTER dem Graphen - aber die ERSTE
    Zeile gehört noch ins erste Bild, sonst ist der Weg zur Tabelle eine
    Blindheit. (1440: die erste Zeile endet im ersten Bildschirm;
    390: sie endet im zweiten - der Graph hat Vorrang an der Falz.)

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; gemessen
    wird die erste sichtbare Zeile der fehlenden Anbieter unter dem Graphen."""
    s = request.getfixturevalue(fixture_name)
    grenze = 2 * s.viewport_size["height"]
    assert s.evaluate("() => !document.querySelector('#tafel-tco .gr-bnd')"), (
        "Bündelzeilen stehen noch auf der Seite"
    )
    box = s.evaluate("""() => {
      for (const e of document.querySelectorAll('#gr-bnd-gruppe .gr-anb-fehlt')) {
        const r = e.getBoundingClientRect();
        if (r.height > 0)
          return {top: Math.round(r.top), endet: Math.round(r.bottom)};
      }
      return null;
    }""")
    assert box is not None, "keine sichtbare Zeile fehlender Anbieter"
    assert box["endet"] <= grenze, (
        f"die erste Zeile endet bei {box['endet']} px - tiefer als zwei "
        f"Bildschirme ({grenze} px)"
    )


def test_deutlich_unter_hundert_aufklapper(seite, vorgabe):
    """A2 am Vorgabemodell: eine Zeile je Bündel, je Zeile EIN Rechenweg-
    Aufklapper - zusammen mit 'Wie gerechnet?', Maßstab und Datenlage
    deutlich unter 100.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    anzahl = seite.eval_on_selector_all("#tafel-tco details", "e => e.length")
    auf_der_seite = seite.eval_on_selector_all("#tafel-tco .gr-bnd", "e => e.length")
    assert auf_der_seite == 0, f"{auf_der_seite} Bündelzeilen auf der Seite"
    assert anzahl < 100, f"{anzahl} <details> in der Vergleichsansicht"
    zeilen = vorgabe.select(".gr-bnd")
    assert len(zeilen) >= 3, f"die Fixture trägt nur {len(zeilen)} Zeilen"
    assert all(z.name == "details" for z in zeilen)
    assert len(vorgabe.select("details")) == len(zeilen) < 100
    rw = vorgabe.select(".gr-bnd-rw ~ details, details details")
    assert not rw, f"{len(rw)} verschachtelte Aufklapper in den Zeilen"


def test_der_bandwechsel_versteckt_zeilen_anderer_baender(seite, vorgabe):
    """Dieselbe Auswahl, dieselbe Tabelle: der Wechsel auf ein anderes
    Band versteckt die Zeilen des alten - die Liste ist danach eine
    ANDERE (P1/UX-1 für die Zeilenform).

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite: im
    Browser folgt die Zeile der fehlenden Anbieter der Bandwahl, und das
    Band nennt der gedrückte Band-Knopf; dass die Bündelzeilen je Band
    verschieden sind, prüft das Fragment."""
    vorher = _sichtbare_fehlende(seite)
    waehle_band(seite, "m")
    seite.wait_for_timeout(120)
    nachher = _sichtbare_fehlende(seite)
    assert vorher and {z["band"] for z in vorher} == {"xs"}, vorher
    assert nachher and {z["band"] for z in nachher} == {"m"}, nachher
    verdeckt = seite.evaluate("""() => Array.from(document.querySelectorAll(
      "#gr-bnd-gruppe .gr-anb-fehlt[data-band='xs']"))
      .map(e => getComputedStyle(e).display !== 'none'
                && e.getClientRects().length > 0)""")
    assert verdeckt and not any(verdeckt), "eine Klein-Zeile bleibt sichtbar"
    gedrueckt = seite.evaluate(
        "() => Array.from(document.querySelectorAll("
        "'#gr-zr-baender button[aria-pressed=\"true\"]'))"
        ".map(k => k.getAttribute('data-band'))"
    )
    assert gedrueckt == ["m"], gedrueckt
    klein = [
        z["data-anbieter"]
        for z in vorgabe.select("#gr-bndliste .gr-bnd[data-band='xs']")
    ]
    mittel = [
        z["data-anbieter"]
        for z in vorgabe.select("#gr-bndliste .gr-bnd[data-band='m']")
    ]
    assert "o2" in klein, klein
    assert mittel and mittel != klein, (
        f"die Zeilenliste folgt der Bandwahl nicht: {klein} == {mittel}"
    )


def test_die_ohne_tarifband_zeilen_bleiben_stehen(vorgabe):
    """§7: die Zeilen ohne Band gehören zu KEINEM Band - sie bleiben bei
    jedem Bandwechsel stehen (sie hängen nicht an der Auswahl an).

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment: die Zeilen ohne Band tragen kein `data-band`, an dem
    ein Bandfilter sie verstecken könnte, und stehen nicht versteckt da."""
    ohne = vorgabe.select("#gr-ohneband .gr-bnd")
    assert ohne, "die Fixture trägt keine Zeile ohne Band"
    assert [z["data-anbieter"] for z in ohne] == ["o2"], ohne
    for z in ohne:
        assert z.get("data-band") is None, z.get("data-band")
        assert not z.has_attr("hidden")
    assert vorgabe.select_one("#gr-bndliste #gr-ohneband") is None
    mit_band = vorgabe.select("#gr-bndliste .gr-bnd")
    assert mit_band and all(z.get("data-band") for z in mit_band)


def test_der_modellwechsel_setzt_die_eigenen_zeilen_ein(seite, fragment):
    """O3 (S3): die Tabelle mit Rechenwegen gehört zum GEWÄHLTEN Modell -
    der Wechsel setzt die Zeilen des anderen Geräts ein (aus dem Fragment,
    `data/geraete-buendel.html`), statt sich zu verstecken. Bis O3 tat sie
    genau das; die O2-Fassung dieses Tests nagelte das Verstecken fest.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite: der
    Wechsel setzt die Zeile der fehlenden Anbieter des anderen Geräts ein,
    die Bündelzeilen je Modell prüft das Fragment."""
    sichtbar = seite.eval_on_selector("#gr-buendel", "e => !e.hidden")
    assert sichtbar, "beim Vorgabemodell steht die Tabelle offen da"
    vorher = {z["anbieter"] for z in _sichtbare_fehlende(seite)}
    auswahl = seite.eval_on_selector(
        "#gr-zeitreihe-daten", "k => Object.keys(JSON.parse(k.textContent).erlaubt)"
    )
    vorgabe = seite.eval_on_selector(
        "#gr-zeitreihe-daten", "k => JSON.parse(k.textContent).vorgabe"
    )
    fremd = [o for o in auswahl if o != vorgabe]
    assert fremd, "die Fixture braucht ein zweites Modell"
    waehle_modell(seite, fremd[0])
    seite.wait_for_timeout(300)
    assert seite.eval_on_selector("#gr-buendel", "e => !e.hidden")
    assert seite.evaluate("() => !document.querySelector('#gr-buendel .gr-bnd')")
    nachher = {z["anbieter"] for z in _sichtbare_fehlende(seite)}
    assert "1&1" in vorher and "1&1" not in nachher, (vorher, nachher)
    assert nachher and nachher != vorher, (vorher, nachher)
    lager = fragment.select_one(f'.gr-bnd-lager[data-modell="{fremd[0]}"]')
    assert lager is not None, f"das Fragment trägt {fremd[0]} nicht"
    anbieter = [z["data-anbieter"] for z in lager.select(".gr-bnd")]
    assert set(anbieter) == {"1&1"}, anbieter
    assert seite.evaluate("() => !document.getElementById('gr-karten-hinweis')"), (
        "der Vorgabegerät-Hinweis ist mit S3 entfallen"
    )


def test_der_modellwechsel_laedt_nur_das_gewaehlte_modell(seite):
    """Seite schneller (10.10.2026): ein Modellwechsel holt nur die Dateien
    des gewählten Modells aus `data/zr/` und `data/bnd/`, nie die
    Gesamtfragmente mit allen Geräten (47 MB und 24 MB am echten Bestand)."""
    daten = seite.eval_on_selector(
        "#gr-zeitreihe-daten", "k => JSON.parse(k.textContent)"
    )
    fremd = [o for o in daten["erlaubt"] if o != daten["vorgabe"]]
    anfragen: list[str] = []
    seite.on("request", lambda r: anfragen.append(r.url))
    waehle_modell(seite, fremd[0])
    seite.wait_for_timeout(300)
    geholt = [u.split("/data/", 1)[1] for u in anfragen if "/data/" in u]
    assert f"zr/{fremd[0]}.html" in geholt, geholt
    assert f"bnd/{fremd[0]}.html" in geholt, geholt
    assert not [u for u in geholt if u.startswith("geraete-")], geholt


def test_der_zeilen_aufklapper_oeffnet_ohne_netzwerk(vorgabe):
    """E1: alles bleibt im Dokument erreichbar - das Öffnen einer Zeile ist
    reines UI (derselbe Maßstab wie der OPTIK-6-Klapptest, nur an der
    Zeile).

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment: jede Zeile trägt ihren ganzen Rechenweg als Vorlage
    bei sich und verweist auf keine nachzuladende Adresse."""
    zeilen = vorgabe.select(".gr-bnd")
    assert zeilen, "keine Zeile im Fragment"
    for z in zeilen:
        assert z.name == "details" and z.select_one("summary") is not None
        assert z.select_one(".gr-bnd-rw") is not None, "Zeile ohne Montageziel"
        vorlage = z.select_one("template.gr-bnd-rw-vorlage")
        assert vorlage is not None, f"{z['data-anbieter']}: kein Rechenweg"
        assert vorlage.select(".gr-tposten li"), "Rechenweg ohne Postenliste"
        assert len(vorlage_text(vorlage)) > 200, vorlage_text(vorlage)
        nachlade = [
            el
            for el in [z, *z.find_all(True)]
            if any(a in el.attrs for a in ("src", "data-src", "data-url"))
        ]
        assert not nachlade, f"{z['data-anbieter']}: lädt nach: {nachlade}"


def test_der_rechenweg_wird_erst_beim_oeffnen_montiert(vorgabe):
    """P4-Fix (Sicht-Pruefung 18.09., Kriterium 13 / FM 4): der Aufklapp-
    Inhalt der Bündel-Zeilen steht im <template> und wird ERST BEIM
    ÖFFNEN montiert. Bis hierher zählte der Rechenweg-Text mit zum
    Fließtext-Deckel des Vergleichs-Reiters (18 048 von 6000 erlaubten
    Zeichen - der Deckel war das einzige rote Kriterium der Abnahme).
    Drei Zusicherungen: (1) das Montageziel ist im Server-HTML LEER,
    (2) die Vorlage trägt den Inhalt, (3) der summary-Klick füllt das
    Ziel - reine Montage, keine Zahl entsteht im Client.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment: (1) und (2) an jeder Zeile, für (3) dass das Ziel und
    die Vorlage in derselben, zugeklappten Zeile stehen."""
    zeilen = vorgabe.select(".gr-bnd")
    assert zeilen, "keine Bündelzeile - der Test prüft nichts"
    for z in zeilen:
        assert not z.has_attr("open"), f"{z['data-anbieter']}: steht schon offen"
        rw = z.select_one(".gr-bnd-rw")
        assert rw is not None and rw.get_text(strip=True) == "", (
            f"{z['data-anbieter']}: das Montageziel ist nicht leer"
        )
        assert not rw.find(True), "das Montageziel trägt schon Knoten"
        vorlage = z.select_one("template.gr-bnd-rw-vorlage")
        assert vorlage is not None and vorlage.find_parent("details") is z
        zeichen = len(vorlage_text(vorlage))
        assert zeichen > 200, (
            f"die Vorlage ist zu duenn ({zeichen} Z) - "
            "der Test misst einen leeren Rechenweg"
        )
        assert vorlage.select(".gr-tposten li"), "Vorlage ohne Postenliste"


def test_zeilen_stapeln_sich_auf_dem_telefon_ohne_querscroll(telefon, vorgabe):
    """Auftrag 1: 'Mobile 390: Tabelle darf quer laufen IN einem
    Scroll-Container NUR wenn unvermeidbar - bevorzugt Zeilen-Stapel wie
    im Entwurf.' Gemessen: keine Zeile läuft aus dem 390-px-Rahmen, und
    die Seite rollt nicht waagerecht.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite: im
    Browser läuft keine Zeile der fehlenden Anbieter aus dem Rahmen; dass die
    Bündelzeile Anbieter, Tarif und Kosten als eigene Zellen trägt, die das
    Telefon stapeln kann, prüft das Fragment."""
    quer = telefon.evaluate(
        "() => Math.max(document.documentElement.scrollWidth,"
        "               document.body.scrollWidth)"
    )
    assert quer <= 391, f"die Seite ist {quer} px breit"
    rahmen = telefon.evaluate("""() => Array.from(
        document.querySelectorAll('#gr-bnd-gruppe .gr-anb-fehlt'))
        .filter(z => z.getClientRects().length > 0)
        .map(z => ({rechts: Math.round(z.getBoundingClientRect().right),
                    quer: z.scrollWidth > z.clientWidth + 1}))""")
    assert rahmen, "keine sichtbare Zeile fehlender Anbieter"
    zu_breit = [z for z in rahmen if z["quer"] or z["rechts"] > 391]
    assert not zu_breit, f"{len(zu_breit)} Zeilen laufen quer aus: {zu_breit}"
    for z in vorgabe.select("#gr-bndliste .gr-bnd"):
        summary = z.select_one("summary")
        assert summary is not None
        zellen = [
            summary.select_one(k)
            for k in (".gr-bnd-an", ".gr-bnd-tarif", ".gr-bnd-tco")
        ]
        assert all(zellen), f"{z['data-anbieter']}: eine Zelle fehlt"
        for zelle in zellen:
            assert zelle.parent is summary or zelle.find_parent("summary") is summary
        assert summary.select_one("table") is None, "eine Tabelle läuft quer"
