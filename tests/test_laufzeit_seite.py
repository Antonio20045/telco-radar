"""Datenkonzept Geräte, Schritt 3: die Ratenlaufzeit auf der Seite.

Ein Umschalter „12 | 24 | 36 Monate | alle“ neben dem Band steuert die ganze
Tafel: Kacheln, Antwortsatz, Graph, Zeilen und Δ. Standard ist 24, der Link
trägt `?laufzeit=`. Unter „alle“ stehen die Zeilen nach Laufzeit gruppiert,
ohne Sieger und ohne Δ.

Bestand und Erwartungen sind die von `test_laufzeit_vergleich` (iPhone 17 Pro
256 GB, Band XS; die Beträge stehen dort als Rechnung aus den Rohwerten). Die
Rechnungen und das Umblenden laufen im Browser und werden im echten Chromium
geprüft. Vor Schritt 3 gab es den Umschalter nicht: die Tafel zeigte immer die
24er-Ansicht, die Zeilen blendete ein eigener Filter je Modell und stellte
dabei 36 Raten als „nächstgelegene“ unter „24 Monate“.
"""

from __future__ import annotations

import contextlib
import csv
import functools
import http.server
import io
import json
import re
import socket
import threading
import urllib.request

import pytest
from bs4 import BeautifulSoup
from test_laufzeit_grafik_export import portal
from test_laufzeit_vergleich import HEUTE, MODELL, SOLL, ansicht, baue, bestand

from telco_radar.report.geraete_laufzeit import ALLE_TEXT
from telco_radar.report.html import render_site


def _euro(betrag: float) -> str:
    return f"{betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html or "").split())


def _paar(g, laufzeit: int) -> dict:
    return next(
        p
        for p in g["zeitreihe"]["paare"]
        if (p["modell"], p["band"], p["laufzeit"]) == (MODELL, "xs", laufzeit)
    )


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


def _baue_site(tmp_path, buendel=None, ohne_barpreis=False):
    root, state = baue(tmp_path, buendel)
    if ohne_barpreis:
        db = json.loads((state / "geraete_db.json").read_text("utf-8"))
        for e in db["listungen"]:
            e["preis_ohne_vertrag"] = None
            e["erstpreis"] = None
        (state / "geraete_db.json").write_text(json.dumps(db), "utf-8")
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


@pytest.fixture(scope="module")
def _basis(tmp_path_factory, chromium):
    site = _baue_site(tmp_path_factory.mktemp("lzseite"))
    with _server(site) as basis:
        yield chromium, basis


@contextlib.contextmanager
def _oeffne(_basis, abfrage="", breite=1440, hoehe=900):
    browser, basis = _basis
    s = browser.new_page(viewport={"width": breite, "height": hoehe})
    try:
        s.goto(f"{basis}/geraete.html{abfrage}", wait_until="networkidle")
        s.click(".gr-reiter button[data-tafel='tafel-tco']")
        s.click(".gx-bnd-auf")
        s.wait_for_timeout(300)
        yield s
    finally:
        s.close()


def _waehle(s, laufzeit: str) -> None:
    s.click(f"#gr-zr-laufzeiten button[data-lz='{laufzeit}']")
    s.wait_for_timeout(600)


_ZEILEN = """() => [...document.querySelectorAll('#gr-bnd-gruppe .gr-bnd')]
  .filter(z => !z.hidden)
  .map(z => ({anbieter: z.dataset.anbieter, lz: z.dataset.lz,
              gesamt: z.dataset.gesamt,
              raten: (z.querySelector('.gr-bnd-raten') || {}).textContent || '',
              delta: (z.querySelector('.gr-bnd-delta') || {}).textContent || '',
              deltaSichtbar: getComputedStyle(z.querySelector('.gr-bnd-delta'))
                .visibility}))"""


def _zeilen(s) -> list[dict]:
    return s.evaluate(_ZEILEN)


def _fehlend(s) -> dict:
    """Die sichtbaren Zeilen fehlender Anbieter, gemessen an ``display``."""
    return s.evaluate("""() => Object.fromEntries(
      [...document.querySelectorAll('#gr-bnd-gruppe .gr-anb-fehlt')]
        .filter(z => getComputedStyle(z).display !== 'none')
        .map(z => [z.dataset.anbieter, z.textContent.replace(z.dataset.anbieter, '')
          .trim()]))""")


def _antwort(s) -> str:
    return " ".join(s.inner_text("#gr-zr-gruppe").split())


def _gedrueckt(s) -> list[str]:
    return s.eval_on_selector_all(
        "#gr-zr-laufzeiten button[aria-pressed='true']",
        "e => e.map(k => k.dataset.lz)",
    )


def _kachelpreis(s) -> str:
    return s.eval_on_selector_all(
        "#gr-zr-kacheln button[aria-pressed='true'] .gr-zr-k-band",
        "e => e.filter(x => !x.hidden).map(x => x.textContent).join(' ')",
    )


def test_ohne_parameter_gilt_24_und_der_link_traegt_die_laufzeit(_basis):
    with _oeffne(_basis) as s:
        assert _gedrueckt(s) == ["24"]
        assert "laufzeit=24" in s.evaluate("location.search")
        zeilen = _zeilen(s)
        assert zeilen and {z["lz"] for z in zeilen} == {"24"}, zeilen


@pytest.mark.parametrize("laufzeit", [12, 24, 36])
def test_der_sieger_jeder_ansicht_hat_ihre_raten(_basis, laufzeit):
    """Antwortsatz, Kachel und günstigste Zeile nennen dieselbe Zahl - die
    kleinste der Ansicht aus dem Modulkopf von `test_laufzeit_vergleich`."""
    soll = SOLL[laufzeit]
    sieger = min(soll, key=soll.get)
    with _oeffne(_basis, f"?laufzeit={laufzeit}") as s:
        antwort = _antwort(s)
        assert f"mit {laufzeit} Raten ist {sieger} am günstigsten" in antwort, antwort
        assert f"{_euro(soll[sieger])} € Kosten über {max(laufzeit, 24)} Monate" in (
            antwort
        )
        zeilen = _zeilen(s)
        guenstigste = min(zeilen, key=lambda z: float(z["gesamt"]))
        assert guenstigste["anbieter"] == sieger, zeilen
        assert guenstigste["raten"].startswith(f"{laufzeit} "), guenstigste
        assert f"ab{_euro(soll[sieger])}€" in _kachelpreis(s).replace(" ", "")
        assert sorted(z["anbieter"] for z in zeilen) == sorted(soll), zeilen


def test_ein_36_raten_buendel_erscheint_nicht_in_der_24er_ansicht(_basis):
    with _oeffne(_basis) as s:
        zeilen = _zeilen(s)
        assert not [z for z in zeilen if not z["raten"].startswith("24 ")], zeilen
        assert "Telekom" not in {z["anbieter"] for z in zeilen}
        assert _euro(SOLL[36]["congstar"]) not in s.inner_text("#tafel-tco")
        _waehle(s, "36")
        assert _euro(SOLL[36]["congstar"]) in s.inner_text("#tafel-tco")


def test_1und1_steht_unter_24_monaten_mit_delta(_basis):
    """Ein Betrag für Tarif und Gerät über 36 Monate wird nur über 24 Monate
    verglichen (Antonio 10.10.2026): 24 Beträge plus Ablöse stehen unter 24 mit
    Δ gegen Vodafone 24, die 36er-Ansicht nennt den Grund."""
    with _oeffne(_basis, "?laufzeit=36") as s:
        assert _gedrueckt(s) == ["36"]
        assert not [z for z in _zeilen(s) if z["anbieter"] == "1&1"]
        assert _fehlend(s).get("1&1", "").startswith("Nur über 24 Monate verglichen")
        _waehle(s, "24")
        eins = [z for z in _zeilen(s) if z["anbieter"] == "1&1"]
        assert [float(z["gesamt"]) for z in eins] == [SOLL[24]["1&1"]], eins
        assert eins[0]["raten"].startswith("24 Monate + Ablöse"), eins
        assert eins[0]["deltaSichtbar"] == "visible"
        delta = " ".join(eins[0]["delta"].split())
        assert delta.startswith(f"−{_euro(SOLL[24]['Vodafone'] - SOLL[24]['1&1'])} €")


@pytest.mark.parametrize("laufzeit", [12, 24, 36])
def test_antwortsatz_und_grafikachse_nennen_die_laufzeit(_basis, laufzeit):
    """Nach dem Klick (nicht nur per Link) steht der Block der Ansicht da:
    Antwortsatz und Achsenkopf des Graphen nennen die Raten und H."""
    with _oeffne(_basis) as s:
        if laufzeit != 24:
            _waehle(s, str(laufzeit))
        h = max(laufzeit, 24)
        antwort = _antwort(s)
        assert f"mit {laufzeit} Raten" in antwort, antwort
        assert f"Kosten über {h} Monate" in antwort, antwort
        kopf = s.eval_on_selector(
            "#gr-zr-gruppe svg.gr-zr--breit", "e => e.getAttribute('aria-label')"
        )
        assert f"Kosten über {h} Monate · {laufzeit} Raten" in kopf, kopf
        graph = s.eval_on_selector(
            "#gr-zr-gruppe .gr-zr-graph", "e => e.getAttribute('aria-label')"
        )
        assert f"Kosten über {h} Monate mit {laufzeit} Raten" in graph, graph
        assert f"laufzeit={laufzeit}" in s.evaluate("location.search")


def test_telekom_ist_in_der_24er_ansicht_nicht_erfasst(_basis):
    with _oeffne(_basis) as s:
        fehlend = _fehlend(s)
        assert fehlend.get("Telekom", "").startswith("Mit 24 Raten nicht erfasst"), (
            fehlend
        )
        assert "Telekom" not in {z["anbieter"] for z in _zeilen(s)}
        _waehle(s, "36")
        assert "Telekom" not in _fehlend(s)
        telekom = [z for z in _zeilen(s) if z["anbieter"] == "Telekom"]
        assert [float(z["gesamt"]) for z in telekom] == [SOLL[36]["Telekom"]]


def test_alle_gruppiert_die_zeilen_ohne_sieger_und_ohne_delta(_basis):
    with _oeffne(_basis, "?laufzeit=alle") as s:
        assert _gedrueckt(s) == ["alle"]
        assert _antwort(s) == ALLE_TEXT
        assert s.query_selector("#gr-zr-gruppe .gr-leit-zahl") is None
        zeilen = _zeilen(s)
        folge = [int(z["lz"]) for z in zeilen]
        assert folge == sorted(folge) and set(folge) == {12, 24, 36}, folge
        assert len(folge) == sum(len(v) for v in SOLL.values()), zeilen
        assert {z["deltaSichtbar"] for z in zeilen} == {"hidden"}
        koepfe = s.evaluate("""() => [...document.querySelectorAll(
            '#gr-bndliste .gr-bnd-lzkopf')].filter(k => !k.hidden).map(k => [
              k.textContent.trim(),
              k.nextElementSibling && k.nextElementSibling.dataset.lz])""")
        assert koepfe == [
            ["12 Raten", "12"],
            ["24 Raten", "24"],
            ["36 Raten", "36"],
        ]
        assert "ab" not in _kachelpreis(s), "unter „alle“ kein ab-Preis"
        _waehle(s, "24")
        assert {z["deltaSichtbar"] for z in _zeilen(s)} == {"visible"}
        assert s.evaluate(
            "() => [...document.querySelectorAll('.gr-bnd-lzkopf')]"
            ".every(k => k.hidden)"
        )


_DELTA_SICHTBAR = """() => [...document.querySelectorAll(
  '#gr-bnd-gruppe .gr-bnd[open] .gr-kk-delta,'
  + '#gr-bnd-gruppe .gr-bnd[open] .gr-kk-luecke--delta')]
  .filter(e => e.offsetParent !== null
               && getComputedStyle(e).visibility !== 'hidden')
  .map(e => e.textContent.replace(/\\s+/g, ' ').trim())"""


def test_unter_alle_steht_kein_delta_auch_nicht_aufgeklappt(_basis):
    """Prüfrunde DK23: „alle“ zeigt kein Δ - auch nicht der Satz in der
    aufgeklappten Zeile (o2 mit 24 Raten, 238,80 € unter Vodafone). Gegenprobe:
    unter 24 steht derselbe Satz in derselben offenen Zeile."""
    with _oeffne(_basis, "?laufzeit=alle") as s:
        zeile = s.locator(
            "#gr-bnd-gruppe details.gr-bnd[data-anbieter='o2'][data-lz='24']"
        ).first
        assert zeile.get_attribute("data-delta") == "-238.8"
        zeile.locator("summary").click()
        s.wait_for_timeout(400)
        assert zeile.get_attribute("open") is not None
        assert s.evaluate(_DELTA_SICHTBAR) == []
        _waehle(s, "24")
        sichtbar = s.evaluate(_DELTA_SICHTBAR)
        assert len(sichtbar) == 1 and _euro(238.8) in sichtbar[0], sichtbar


def test_der_link_haelt_die_wahl_und_verwirft_fremde_werte(_basis):
    with _oeffne(_basis) as s:
        _waehle(s, "12")
        assert "laufzeit=12" in s.evaluate("location.search")
        s.reload(wait_until="networkidle")
        s.click(".gr-reiter button[data-tafel='tafel-tco']")
        s.wait_for_timeout(600)
        assert _gedrueckt(s) == ["12"]
        assert {z["lz"] for z in _zeilen(s)} == {"12"}
    with _oeffne(_basis, "?laufzeit=30") as s:
        assert _gedrueckt(s) == ["24"]
        assert "laufzeit=24" in s.evaluate("location.search")


def test_am_telefon_stehen_band_und_laufzeit_in_einer_zeile(_basis):
    """Eine zweite Zeile schöbe Antwort und Kurve unter die Falz (11c)."""
    with _oeffne(_basis, "", 390, 844) as s:
        lage = s.evaluate("""() => {
          const b = document.getElementById('gr-zr-baender').getBoundingClientRect();
          const l = document.getElementById('gr-zr-laufzeiten')
            .getBoundingClientRect();
          return {b: Math.round(b.top), l: Math.round(l.top),
                  rechts: Math.round(l.right), breit: window.innerWidth,
                  quer: document.documentElement.scrollWidth};
        }""")
        assert lage["b"] == lage["l"], lage
        assert lage["rechts"] <= lage["breit"] and lage["quer"] <= lage["breit"]


def test_der_katalog_nennt_die_raten_seines_monatsbetrags(tmp_path):
    """Prüfrunde DK23: die Katalogzeile eines Geräts, das es nur im Bündel gibt,
    nennt den Monatsbetrag der Standardansicht samt Raten (o2 mit 24 Raten,
    25,00 + 40,00 €), nicht Vodafones 36er (60,95 €) ohne Laufzeit."""
    buendel = [s for s in bestand() if s["anbieter"] in ("Vodafone", "o2")]
    site = _baue_site(tmp_path, buendel, ohne_barpreis=True)
    suppe = BeautifulSoup((site / "geraete.html").read_text("utf-8"), "html.parser")
    zeile = next(
        z
        for z in suppe.select("#gr-katalogtabelle tr.gr-k-zeile")
        if z.get("data-modell") == MODELL
    )
    text = " ".join(zeile.get_text(" ", strip=True).split())
    assert "nur im Bündel" in text, text
    assert f"ab {_euro(65.0)} €/Monat mit 24 Raten bei o2" in text, text
    assert _euro(60.95) not in text, text


def test_vodafone_ohne_zahl_heisst_nicht_nicht_erfasst(tmp_path):
    """Führt Vodafone ein Bündel mit 36 Raten, aber ohne vollständige Zahl, ist
    es erfasst - der Satz sagt „ohne Zahl“. Gegenprobe: ohne das Bündel heißt
    es „nicht erfasst“."""
    ohne_zahl = ansicht(
        tmp_path / "a", bestand(aendern={("Vodafone", 36): {"anschlusspreis": None}})
    )
    satz = _text(_paar(ohne_zahl, 36)["antwort_html"])
    assert "Vodafone mit 36 Raten ohne Zahl" in satz, satz
    assert "nicht erfasst" not in satz, satz
    ohne = ansicht(tmp_path / "b", bestand(ohne={("Vodafone", 36)}))
    satz = _text(_paar(ohne, 36)["antwort_html"])
    assert "Vodafone ist mit 36 Raten nicht erfasst" in satz, satz


_EXPORT = """() => { const a = document.getElementById('gr-export-tco');
  return a && {href: a.getAttribute('href'), text: a.textContent.trim()}; }"""


def _laden(basis: str, pfad: str) -> str:
    with urllib.request.urlopen(f"{basis}/{pfad}") as antwort:
        return antwort.read().decode("utf-8-sig")


def test_der_export_folgt_dem_umschalter(_basis):
    """Datenkonzept 5.4: der Umschalter steuert auch den Export. Bei
    ?laufzeit=36 zeigt der Bündel-Export auf die 36er-Datei, und die Datei
    trägt genau die Bündel mit 36 Raten. Gegenproben: 24 ohne Parameter,
    12 nach dem Klick, „alle“ auf den Gesamtexport."""
    _browser, basis = _basis
    with _oeffne(_basis, "?laufzeit=36") as s:
        link = s.evaluate(_EXPORT)
        assert link == {
            "href": "exporte/geraete-tco-36.csv",
            "text": f"Bündel-TCO 36 Monate ({len(SOLL[36])})",
        }, link
        text = _laden(basis, link["href"])
        zeilen = [
            z
            for z in csv.DictReader(io.StringIO(text), delimiter=";")
            if z["Art"] == "Bündel"
        ]
        assert sorted(z["Anbieter"] for z in zeilen) == sorted(SOLL[36]), zeilen
        assert {z["Laufzeit Monate"] for z in zeilen} == {"36"}
        _waehle(s, "12")
        assert s.evaluate(_EXPORT)["href"] == "exporte/geraete-tco-12.csv"
        _waehle(s, "alle")
        assert s.evaluate(_EXPORT)["href"] == "exporte/geraete-tco.csv"
    with _oeffne(_basis) as s:
        assert s.evaluate(_EXPORT)["href"] == "exporte/geraete-tco-24.csv"


def test_kriterium_11_haelt_an_der_gerenderten_seite(_basis):
    """Die Portal-Abnahme (Kriterium 11) an der echten Vorlage: jede Zeile mit
    Zahl nennt „über H Monate“. Gegenprobe: ohne Etikett wird sie rot."""
    _browser, basis = _basis
    seite = BeautifulSoup(_laden(basis, "geraete.html"), "html.parser")
    tafel = seite.select_one("#tafel-tco")
    mit_zahl = tafel.select(".gr-bnd[data-gesamt]:not([data-gesamt=''])")
    assert len(mit_zahl) == sum(len(v) for v in SOLL.values()), len(mit_zahl)
    assert portal.zeitraum_maengel(tafel) == []
    for etikett in tafel.select(".gr-bnd-tco .gr-bnd-label"):
        etikett.decompose()
    assert portal.zeitraum_maengel(tafel) == [
        f"{len(mit_zahl)} Bündelzeilen ohne 'über H Monate'"
    ]


def test_die_36er_zeile_sagt_ab_wann_nur_die_rate_zaehlt(_basis):
    """Antonio 10.10.2026: der Rechenweg einer 36-Raten-Zeile nennt 24 Monate
    Tarif und „Monat 25–36 nur die Rate“, nicht 36 Monate Tarif. Gegenprobe:
    die 24er-Zeilen tragen den Satz nicht, 1&1 (ein Betrag) auch nicht."""
    _browser, basis = _basis
    seite = BeautifulSoup(_laden(basis, "geraete.html"), "html.parser")
    gesehen = set()
    for zeile in seite.select("#tafel-tco .gr-bnd[data-gesamt]"):
        text = " ".join(
            "".join(t.decode_contents() for t in zeile.select("template")).split()
        )
        text = " ".join(re.sub(r"<[^>]+>", " ", text).split())
        satz = "Tarif 24 Monate – Monat 25–36 nur die Rate"
        if zeile["data-laufzeit"] == "36" and zeile["data-anbieter"] != "1&1":
            gesehen.add(zeile["data-anbieter"])
            assert satz in text, (zeile["data-anbieter"], text[:400])
            assert "36 Monate Tarif" not in text, text[:400]
        else:
            assert "nur die Rate" not in text, (zeile["data-anbieter"], text[:400])
    assert gesehen >= {"congstar", "Telekom", "Vodafone"}, gesehen
