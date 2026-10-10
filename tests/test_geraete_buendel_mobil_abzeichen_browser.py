"""QA-Fix 24.09.2026, Punkt 7: MOBILE Bündelzeilen der Vergleichstafel
(Reiter „Vergleich"). Zwei Befunde am selben Screenshot:

  a) der Preis stand bei Vodafone ("unser Angebot") und Telekom ("kein
     aktueller Stand seit …") uneinheitlich zu den anderen Zeilen - Ziel
     ist dieselbe rechte Kante und dieselbe Lage zum Anbieternamen in
     JEDER Zeile.
  b) das Abzeichen (`.gr-kk-marke`) war `inline-block` mit `max-content`-
     Breite - eine schmale Box (~90 px), in der "kein aktueller Stand
     seit 09.09.2026" auf drei enge Zeilen umbrach und die Telekom-Zeile
     insgesamt vierfach. Fix: `display:block;width:100%` am Telefon.

Fixture: vier Anbieter desselben Bündels - Vodafone (eigen, "unser
Angebot"), Telekom (Abruf 9 Tage alt, "kein aktueller Stand seit …",
ueber `geraete_tco_karten.ALT_AB_TAGEN`), o2 und 1&1 ohne Abzeichen.

Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft wird
das Fragment: der Bauplan jeder Zeile aus `data/geraete-buendel.html`, die
Regeln von style.css, die bei 390 px gelten, und im Browser, was dort noch
steht (Breite der Gruppe, Textbreite des Abzeichens, kein waagerechtes
Rollen)."""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import re
import socket
import threading

import pytest
from bs4 import BeautifulSoup

from tarifleiter_testbestand import mit_leiter
import yaml

from telco_radar.report import geraete_tco_karten
from telco_radar.report.html import render_site

HEUTE = "2026-09-24"
ALT_ABGERUFEN = "2026-09-15"

_KATALOG = {
    "geraete": [
        {
            "hersteller": "Apple",
            "modell": "iPhone 17 Pro",
            "generation": 17,
            "marktstart": "2025-09-19",
            "speicher": [256],
            "segment": "premium",
        },
    ]
}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {
    "anbieter": [
        {
            "name": "Vodafone",
            "typ": "netzbetreiber",
            "rang": 1,
            "eigen": True,
            "methode": "ldjson",
            "basis_url": "https://www.vodafone.de",
            "einstiege": [{"url": "https://www.vodafone.de/handys"}],
        },
        {
            "name": "Telekom",
            "typ": "netzbetreiber",
            "rang": 2,
            "methode": "ldjson",
            "basis_url": "https://www.telekom.de",
            "einstiege": [{"url": "https://www.telekom.de/handys"}],
        },
        {
            "name": "o2",
            "typ": "netzbetreiber",
            "rang": 3,
            "methode": "ldjson",
            "basis_url": "https://www.o2online.de",
            "einstiege": [{"url": "https://www.o2online.de/handys"}],
        },
        {
            "name": "congstar",
            "typ": "netzbetreiber",
            "rang": 4,
            "methode": "ldjson",
            "basis_url": "https://www.congstar.de",
            "einstiege": [{"url": "https://www.congstar.de/handys"}],
        },
    ]
}

DEVICE = "apple-iphone-17-pro"
SPEICHER = 256

_BUENDEL = [
    ("Vodafone", "vf:klein", "Vodafone Mobil XS", 26.0, HEUTE),
    ("Telekom", "tk:klein", "MagentaMobil XS", 24.0, ALT_ABGERUFEN),
    ("congstar", "cs:klein", "Allnet Flat XS Flex", 18.0, HEUTE),
    ("1&1", "11:klein", "All-Net-Flat S", 15.0, HEUTE),
]


def _sku(device_id, speicher):
    return f"{device_id}-{speicher}gb-schwarz"


def _listung(anbieter, preis, abgerufen_am):
    return {
        "id": f"{anbieter.lower()}--{_sku(DEVICE, SPEICHER)}",
        "sku_id": _sku(DEVICE, SPEICHER),
        "device_id": DEVICE,
        "anbieter": anbieter,
        "anbieter_typ": "netzbetreiber",
        "netz": anbieter,
        "speicher_gb": SPEICHER,
        "farbe_roh": "Schwarz",
        "farbe_normalisiert": "schwarz",
        "zustand": "neu",
        "first_seen": "2026-08-01",
        "last_verified": abgerufen_am,
        "status": "aktiv",
        "missed_checks": 0,
        "preis_ohne_vertrag": preis,
        "erstpreis": preis,
        "erstpreis_art": "ohne_vertrag",
        "erstpreis_am": "2026-08-01",
        "quelle_url": f"https://example.de/{anbieter.lower()}/{DEVICE}",
        "abgerufen_am": abgerufen_am,
        "verfuegbarkeit": "lieferbar",
        "confidence": "hoch",
        "einstiege": ["https://example.de/liste"],
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
        _listung(a, 1099.00 + i, ab) for i, (a, _t, _n, _r, ab) in enumerate(_BUENDEL)
    ]
    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": HEUTE,
                "anbieter": {
                    a: {"laeufe": 4, "funde_gesamt": 1} for a, *_r in _BUENDEL
                },
                "listungen": listungen,
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = []
    for anbieter, tarif_id, tarif, rate, abgerufen_am in _BUENDEL:
        buendel.append(
            {
                "id": f"buendel--{anbieter.lower()}--{_sku(DEVICE, SPEICHER)}"
                f"--{tarif_id}",
                "sku_id": _sku(DEVICE, SPEICHER),
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
                "quelle_url": f"https://example.de/{anbieter.lower()}/{DEVICE}",
                "abgerufen_am": abgerufen_am,
                "first_seen": HEUTE,
                "last_verified": abgerufen_am,
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
            "datenvolumen_gb": 10,
            "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 24.99}],
            "dokument_url": f"https://example.de/pib/{tarif_id}",
            "abgerufen_am": HEUTE,
            "confidence": {},
            "fundstellen": {},
        }
        for anbieter, tarif_id, tarif, _r, _ab in _BUENDEL
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
                "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
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
def _server(site):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


BREITE = 390


def _css_fuer(site, breite) -> str:
    """Die Regeln von style.css, die bei dieser Breite gelten: alles außerhalb
    von @media plus die Blöcke `max-width` >= breite und `min-width` <= breite.
    Leerraum ist zu einem Zeichen gefaltet."""
    css = re.sub(r"\s+", " ", (site / "style.css").read_text(encoding="utf-8"))
    css = re.sub(r"/\*.*?\*/", "", css)
    teile, rest, pos = [], [], 0
    for treffer in re.finditer(r"@media([^{]*)\{", css):
        if treffer.start() < pos:
            continue
        tiefe, ende = 1, treffer.end()
        while tiefe:
            tiefe += {"{": 1, "}": -1}.get(css[ende], 0)
            ende += 1
        rest.append(css[pos : treffer.start()])
        bedingung = treffer.group(1)
        maxi = re.search(r"max-width:\s*(\d+)px", bedingung)
        mini = re.search(r"min-width:\s*(\d+)px", bedingung)
        passt = (not maxi or int(maxi.group(1)) >= breite) and (
            not mini or int(mini.group(1)) <= breite
        )
        if passt and "print" not in bedingung and "hover" not in bedingung:
            teile.append(css[treffer.end() : ende - 1])
        pos = ende
    rest.append(css[pos:])
    return " ".join(rest + teile)


def _zeile(d) -> dict:
    """Bauplan einer Bündelzeile des Fragments: die Zellen des Zeilenkopfs
    in ihrer Reihenfolge, Name und Abzeichen der Anbieterzelle."""
    kopf = d.find("summary", recursive=False)
    assert kopf is not None, d.attrs
    an = kopf.select(":scope > .gr-bnd-an")
    assert len(an) == 1, d.attrs
    marke = an[0].select_one(".gr-kk-marke")
    return {
        "name": an[0].select_one(".gr-bnd-name").get_text(strip=True),
        "marke": marke.get_text(" ", strip=True) if marke else None,
        "markeKlassen": marke.get("class", []) if marke else [],
        "zellen": [k.get("class", [""])[0] for k in kopf.find_all(recursive=False)],
    }


_MESSEN = """(texte) => {
  const g = document.getElementById('gr-bnd-gruppe').getBoundingClientRect();
  const wurzel = getComputedStyle(document.documentElement);
  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = '12px ' + wurzel.getPropertyValue('--sans').trim();
  return {
    gruppeBreite: g.width, gruppeRechts: g.right, innen: innerWidth,
    quer: document.documentElement.scrollWidth,
    zeilenAufSeite: document.querySelectorAll('.gr-bnd, .gx-bnd-auf').length,
    textBreiten: texte.map(t => ctx.measureText(t).width),
  };
}"""


@pytest.fixture(scope="module")
def zeilen(tmp_path_factory, chromium):
    site = _baue(tmp_path_factory.mktemp("bnd390"))
    lager = BeautifulSoup(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        "html.parser",
    )
    daten = [_zeile(d) for d in lager.select("#gr-bnd-vorgabe details.gr-bnd")]
    with _server(site) as wurzel:
        ctx = chromium.new_context(viewport={"width": BREITE, "height": 1400})
        try:
            s = ctx.new_page()
            s.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
            s.click(".gr-reiter button[data-tafel='tafel-tco']")
            s.wait_for_timeout(300)
            browser = s.evaluate(_MESSEN, [z["marke"] for z in daten if z["marke"]])
        finally:
            ctx.close()
    return {"zeilen": daten, "css": _css_fuer(site, BREITE), "browser": browser}


def test_alle_preise_haben_dieselbe_rechte_kante(zeilen):
    """Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite;
    geprüft wird das Fragment: jede Zeile trägt genau eine Preiszelle im
    Zeilenkopf, und am Telefon steht sie auf einer eigenen vollen Grid-Zeile,
    rechts ausgerichtet (`justify-self:end`) - dieselbe rechte Kante in
    jeder Zeile, unabhängig vom Inhalt. Im Browser rollt nichts waagerecht."""
    daten, css, browser = zeilen["zeilen"], zeilen["css"], zeilen["browser"]
    assert len(daten) == 4, daten
    for z in daten:
        assert z["zellen"].count("gr-bnd-tco") == 1, z
    assert (
        ".gr-bnd summary{ grid-template-columns:minmax(0,1fr) auto;row-gap:3px; "
        'grid-template-areas:"an an" "tco tco" ' in css
    )
    assert (
        ".gr-bnd-tco{grid-area:tco;text-align:right;align-self:start; "
        "justify-self:end;width:max-content;max-width:100%}" in css
    )
    assert ".gr-bnd-an,.gr-bnd-tco,.gr-bnd-delta,.gr-bnd-bar{grid-row" not in css
    assert browser["zeilenAufSeite"] == 0, browser
    assert browser["gruppeBreite"] > 0, browser
    assert browser["gruppeRechts"] <= browser["innen"] + 0.5, browser
    assert browser["quer"] <= browser["innen"], browser


def test_der_preis_liegt_in_jeder_zeile_gleich_zum_namen(zeilen):
    """Nachtrag (Lead-Befund 24.09.2026): NICHT die absolute Hoehe zaehlt
    (an/tco stehen seit dem Grid-Fix je auf einer eigenen vollen Zeile),
    sondern dass der ABSTAND zwischen Namens- und Preiszeile bei GLEICHEM
    Bauplan (mit/ohne Abzeichen) GLEICH ist - vorher bestimmte der Inhalt
    der Preiszelle (Ziffern- und Textlaenge) eine eigene Spaltenaufteilung
    je Zeile, und zwei Zeilen mit identischem Bauplan sahen verschieden
    aus (Preis neben dem Namen vs. eine Zeile tiefer). Ein Abzeichen
    fuegt selbst legitim eine Zeile Hoehe hinzu - verglichen wird darum
    je Gruppe (mit/ohne Abzeichen), nicht ueber beide hinweg. Seit
    10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft wird
    das Fragment: je Gruppe derselbe Bauplan des Zeilenkopfs, und style.css
    legt bei 390 px die Preiszeile direkt unter die Namenszeile, je über
    die volle Breite, ohne Spalte, die der Inhalt bestimmt."""
    daten, css = zeilen["zeilen"], zeilen["css"]
    assert len(daten) == 4, daten
    for hat_marke in (True, False):
        gruppe = [z for z in daten if bool(z["marke"]) == hat_marke]
        if len(gruppe) < 2:
            continue
        bauplaene = {tuple(z["zellen"]) for z in gruppe}
        assert len(bauplaene) == 1, (
            f"der Bauplan unterscheidet sich innerhalb derselben "
            f"Bauform (Abzeichen={hat_marke}): {gruppe}"
        )
    assert 'grid-template-areas:"an an" "tco tco" "tar bar"' in css
    assert ".gr-bnd-an{grid-area:an;min-width:0}" in css
    assert "grid-template-columns:minmax(0,1fr) auto;row-gap:3px;" in css


def test_das_abzeichen_steht_auf_einer_zeile(zeilen):
    """Nachtrag (Lead-Befund 24.09.2026): der fruehere Test verglich die
    Abzeichenbreite mit der Breite SEINER EIGENEN Zelle - tautologisch,
    sobald das Abzeichen `width:100%` dieser Zelle traegt, auch wenn die
    Zelle selbst nur ~75 px breit ist. Die eigentliche Regel: der Text
    passt auf EINE Zeile (Rechteckhoehe ~ eine Zeilenhoehe), nicht auf
    zwei bis vier enge Zeilen gestapelt. Seit 10.10.2026 steht die
    Bündelliste nicht mehr auf der Seite; geprüft wird das Fragment (das
    Abzeichen steht in der Anbieterzelle), style.css bei 390 px (Block über
    die volle Zeile, 12 px) und im Browser die Breite des Abzeichentextes
    in dieser Schrift gegen die Breite der Gruppe."""
    daten, css, browser = zeilen["zeilen"], zeilen["css"], zeilen["browser"]
    mit_marke = [z for z in daten if z["marke"]]
    assert len(mit_marke) == 1, daten
    for z in mit_marke:
        assert "gr-kk-marke--notbremse" not in z["markeKlassen"], z
    assert (
        ".gr-bnd-an .gr-kk-marke{display:block;width:100%;box-sizing:border-box;" in css
    )
    assert re.search(r"\.gr-bnd-an \.gr-kk-marke\{[^}]*font-size:12px", css)
    breiten = browser["textBreiten"]
    assert len(breiten) == len(mit_marke), browser
    for z, breite in zip(mit_marke, breiten, strict=True):
        assert 0 < breite < browser["gruppeBreite"] - 24, (
            f"das Abzeichen steht nicht auf einer Zeile: {z} {browser}"
        )


def test_die_alte_telekom_zeile_traegt_wirklich_die_alte_marke(zeilen):
    """Gegenprobe: die Fixture trifft wirklich `ALT_AB_TAGEN` - sonst
    testet `test_das_abzeichen_hat_die_volle_breite_der_an_zelle` an
    einer Zeile ohne Marke vorbei. Seit 10.10.2026 steht die Bündelliste
    nicht mehr auf der Seite; geprüft wird das Fragment."""
    telekom = [z for z in zeilen["zeilen"] if z["name"] == "Telekom"]
    assert telekom, zeilen
    assert telekom[0]["marke"] == geraete_tco_karten.alt_marke_fuer(ALT_ABGERUFEN), (
        telekom
    )
    assert "gr-kk-marke--alt" in telekom[0]["markeKlassen"], telekom
    assert (
        geraete_tco_karten.alter_in_tagen(ALT_ABGERUFEN, HEUTE)
        > geraete_tco_karten.ALT_AB_TAGEN
    )
