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
import functools
import http.server
import json
import re
import socket
import threading

import pytest
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


def _baue_site(tmp_path):
    root, _state = baue(tmp_path)
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
        assert {"Telekom", "1&1"}.isdisjoint(z["anbieter"] for z in zeilen)
        assert _euro(SOLL[36]["congstar"]) not in s.inner_text("#tafel-tco")
        _waehle(s, "36")
        assert _euro(SOLL[36]["congstar"]) in s.inner_text("#tafel-tco")


def test_laufzeit_36_zeigt_1und1_mit_delta(_basis):
    """1&1 gegen die Vodafone-Karte mit 36 Raten im selben Band - ein Betrag,
    nicht mehr „andere Laufzeit“. Gegenprobe: in der 24er-Ansicht keine
    1&1-Zeile, also auch kein Δ."""
    soll = round(SOLL[36]["1&1"] - SOLL[36]["Vodafone"], 2)
    with _oeffne(_basis, "?laufzeit=36") as s:
        assert _gedrueckt(s) == ["36"]
        eins = [z for z in _zeilen(s) if z["anbieter"] == "1&1"]
        assert len(eins) == 1, eins
        delta = " ".join(eins[0]["delta"].split())
        assert delta.startswith(f"−{_euro(-soll)} €"), delta
        assert "andere Laufzeit" not in delta
        _waehle(s, "24")
        assert not [z for z in _zeilen(s) if z["anbieter"] == "1&1"]


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
        text = _antwort(s)
        assert re.search(r"24 Raten nicht erfasst: [^.]*Telekom", text), text
        assert "Telekom" not in {z["anbieter"] for z in _zeilen(s)}
        _waehle(s, "36")
        text = _antwort(s)
        assert (
            "nicht erfasst: " not in text
            or "Telekom" not in text.split("nicht erfasst: ", 1)[1].split(".")[0]
        ), text
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
        assert len(zeilen) == sum(len(v) for v in SOLL.values()), zeilen
        assert {z["deltaSichtbar"] for z in zeilen} == {"hidden"}
        koepfe = s.evaluate("""() => [...document.querySelectorAll(
            '#gr-bndliste .gr-bnd-lzkopf')].filter(k => !k.hidden).map(k => [
              k.textContent.trim(),
              k.nextElementSibling && k.nextElementSibling.dataset.lz])""")
        assert koepfe == [["12 Raten", "12"], ["24 Raten", "24"], ["36 Raten", "36"]]
        assert "ab" not in _kachelpreis(s), "unter „alle“ kein ab-Preis"
        _waehle(s, "24")
        assert {z["deltaSichtbar"] for z in _zeilen(s)} == {"visible"}
        assert s.evaluate(
            "() => [...document.querySelectorAll('.gr-bnd-lzkopf')]"
            ".every(k => k.hidden)"
        )


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
