"""Der Laufzeit-Filter der Bündeltabelle, Standard 24 Monate.

Python entscheidet, welche Zeile unter welcher Wahl steht
(`geraete_laufzeit.setze_ansicht`), app.js blendet nur. Seit Datenkonzept
Geräte Schritt 3 steht eine Zeile genau unter ihrer eigenen Ratenlaufzeit:
die frühere Regel (P3-E2), wer die gewählte Laufzeit nicht anbietet, stehe
mit seiner nächstgelegenen da, stellte 36 Raten unter „24 Monate“ - genau
der Vergleich, den Regel 5 verbietet. Wer fehlt, nennt der Lückensatz der
Ansicht („Mit 24 Raten nicht erfasst: …“). Der Umschalter steht seither
einmal für die ganze Tafel in der Wahl-Leiste (`#gr-zr-laufzeiten`).

Die Browser-Tests laufen im echten Chromium auf eigenem Server - dieselbe
Bauform wie `tests/test_geraete_o2_zeilen_browser.py`.
"""

from __future__ import annotations

import contextlib
import json

import pytest
import yaml

from telco_radar.report import geraete_laufzeit
from telco_radar.report import geraete_tco_karten as karten
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
from tarifleiter_testbestand import mit_leiter
from test_geraete_zeitreihe_browser import waehle_band


def _k(anbieter, tarif, lz, zustand="neu"):
    return {
        "anbieter": anbieter,
        "tarif": tarif,
        "raten_laufzeit": lz,
        "zustand": zustand,
    }


def test_jede_wahl_zeigt_nur_zeilen_ihrer_laufzeit():
    cs24, cs36 = _k("congstar", "XS", 24), _k("congstar", "XS", 36)
    o2 = _k("o2", "M", 36)
    vf12, vf24 = _k("Vodafone", "S", 12), _k("Vodafone", "S", 24)
    ref = _k("Vodafone", "Referenz", None)
    alle = [cs24, cs36, o2, vf12, vf24, ref]
    geraete_laufzeit.setze_ansicht(alle)
    assert cs24["laufzeit_sichtbar"] == "24"
    assert cs36["laufzeit_sichtbar"] == "36"
    assert o2["laufzeit_sichtbar"] == "36", "36 Raten nie unter 12 oder 24"
    assert vf12["laufzeit_sichtbar"] == "12"
    assert vf24["laufzeit_sichtbar"] == "24", "24 Raten nie unter 36"
    assert ref["laufzeit_sichtbar"] == "alle", "ohne Raten nur unter „alle“"
    soll = {
        "12": {("Vodafone", "S")},
        "24": {("congstar", "XS"), ("Vodafone", "S")},
        "36": {("congstar", "XS"), ("o2", "M")},
    }
    for lz, angebote in soll.items():
        je_angebot: dict = {}
        for k in alle:
            if k["laufzeit_sichtbar"] == lz:
                je_angebot.setdefault((k["anbieter"], k["tarif"]), []).append(k)
        assert all(len(v) == 1 for v in je_angebot.values()), (lz, je_angebot)
        assert set(je_angebot) == angebote, (lz, je_angebot)
        assert {k["raten_laufzeit"] for v in je_angebot.values() for k in v} == {
            int(lz)
        }


def test_der_zustand_aendert_die_ansicht_nicht():
    neu = _k("o2", "M", 24)
    erneuert = _k("o2", "M", 36, zustand="refurbished")
    geraete_laufzeit.setze_ansicht([neu, erneuert])
    assert (neu["laufzeit_sichtbar"], erneuert["laufzeit_sichtbar"]) == ("24", "36")


def test_auch_eine_einzige_laufzeit_steht_unter_ihrer_ansicht():
    k, tk = _k("o2", "M", 36), _k("Telekom", "L", 36)
    geraete_laufzeit.setze_ansicht([k, tk])
    assert k["laufzeit_sichtbar"] == tk["laufzeit_sichtbar"] == "36"


def test_eine_fremde_laufzeit_steht_unter_keiner_ansicht():
    zwoelf, dreissig = _k("a", "t", 12), _k("b", "t", 30)
    geraete_laufzeit.setze_ansicht([zwoelf, dreissig])
    assert zwoelf["laufzeit_sichtbar"] == "12"
    assert dreissig["laufzeit_sichtbar"] == "alle", "nie als nächstgelegene"
    assert karten.LAUFZEIT_STANDARD == 24
    assert geraete_laufzeit.LAUFZEITEN == (12, 24, 36)


_GERAET = "apple-iphone-17-pro"
_BUENDEL = [
    (
        "congstar",
        "cs:xs",
        "Allnet Flat XS",
        24,
        41.25,
        [
            {
                "art": "trade_in",
                "bedingung": "nur mit Eintausch eines Altgeräts",
                "quelle_url": "https://www.congstar.de/handytarife/allnet-flat-tarife/"
                "allnet-flat-xs/",
                "betrag": 324.0,
                "eingerechnet": False,
                "gueltig_bis": "",
            }
        ],
    ),
    ("congstar", "cs:xs", "Allnet Flat XS", 36, 27.5, []),
    ("o2", "o2:klein", "O2 Mobile Klein", 36, 30.0, []),
    ("Vodafone", "vf:klein", "Vodafone Mobil XS", 24, 45.0, []),
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
    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": HEUTE,
                "anbieter": {
                    n: {"laeufe": 4, "funde_gesamt": 1}
                    for n in ("Vodafone", "o2", "congstar")
                },
                "listungen": [
                    _listung("Vodafone", _GERAET, 256, 1199.90),
                    _listung("o2", _GERAET, 256, 1099.00),
                    _listung("congstar", _GERAET, 256, 1225.00),
                ],
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = [
        {
            "id": f"buendel--{a.lower()}--{_sku(_GERAET, 256)}--{tid}--{lz}m",
            "sku_id": _sku(_GERAET, 256),
            "anbieter": a,
            "tarif_name": tarif,
            "tarif_id": tid,
            "tarif_id_guete": "hoch",
            "tarif_monatlich": 24.0,
            "geraet_zuzahlung": 1.0,
            "geraet_monatsrate": rate,
            "laufzeit_monate": lz,
            "anschlusspreis": 0.0,
            "zustand": "neu",
            "rabatte": [],
            "aktionen": aktionen,
            "quelle_url": f"https://example.de/{a.lower()}/{tid}",
            "abgerufen_am": HEUTE,
            "first_seen": HEUTE,
            "last_verified": HEUTE,
        }
        for a, tid, tarif, lz, rate, aktionen in _BUENDEL
    ]
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8",
    )
    tarife = {tid: (a, tarif) for a, tid, tarif, *_ in _BUENDEL}
    (state / "tarife.jsonl").write_text(
        "\n".join(
            json.dumps(t)
            for t in mit_leiter(
                [
                    {
                        "anbieter": a,
                        "name": tarif,
                        "tarif_id": tid,
                        "art": "mobilfunk",
                        "grundgebuehr": 24.0,
                        "laufzeit_monate": 24,
                        "datenvolumen_gb": 15,
                        "preisphasen": [
                            {"von_monat": 1, "bis_monat": None, "betrag": 24.0}
                        ],
                        "dokument_url": f"https://example.de/pib/{tid}",
                        "abgerufen_am": HEUTE,
                        "confidence": {},
                        "fundstellen": {},
                    }
                    for tid, (a, tarif) in tarife.items()
                ],
                HEUTE,
            )
        )
        + "\n",
        encoding="utf-8",
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
    site = _baue(tmp_path_factory.mktemp("laufzeitfilter"))
    with _server(site) as basis:
        yield chromium, basis


@pytest.fixture(scope="module")
def _browser_seite(tmp_path_factory, chromium):
    with _browser_ctx(tmp_path_factory, chromium) as paar:
        yield paar


@pytest.fixture(params=[(1440, 900), (390, 844)], ids=["breit", "telefon"])
def seite(_browser_seite, request):
    browser, basis = _browser_seite
    breite, hoehe = request.param
    s = browser.new_page(viewport={"width": breite, "height": hoehe})
    s.goto(f"{basis}/geraete.html", wait_until="load")
    s.click(".gr-reiter button[data-tafel='tafel-tco']")
    s.click(".gx-bnd-auf")
    try:
        yield s
    finally:
        s.close()


_SICHTBAR = """() => Array.from(document.querySelectorAll('#gr-bnd-gruppe .gr-bnd'))
  .filter(z => z.getBoundingClientRect().height > 0)
  .map(z => z.dataset.anbieter + ' ' + z.querySelector('.gr-bnd-raten')
                                       .textContent.trim().split(' ')[0])
  .sort()"""


def _waehle(seite, lz):
    seite.click(f"#gr-zr-laufzeiten button[data-lz='{lz}']")
    seite.wait_for_timeout(300)


def test_ohne_klick_stehen_24_monate(seite):
    gedrueckt = seite.eval_on_selector_all(
        "#gr-zr-laufzeiten button[aria-pressed='true']",
        "e => e.map(k => k.dataset.lz)",
    )
    assert gedrueckt == ["24"]
    assert seite.evaluate(_SICHTBAR) == ["Vodafone 24", "congstar 24"]
    assert "laufzeit=24" in seite.evaluate("location.search")


def test_die_wahl_36_zeigt_nur_36_raten(seite):
    _waehle(seite, "36")
    assert seite.evaluate(_SICHTBAR) == ["congstar 36", "o2 36"]
    _waehle(seite, "alle")
    assert seite.evaluate(_SICHTBAR) == [
        "Vodafone 24",
        "congstar 24",
        "congstar 36",
        "o2 36",
    ]


def test_die_laufzeitwahl_ueberlebt_den_bandwechsel(seite):
    _waehle(seite, "36")
    waehle_band(seite, "xs")
    assert seite.evaluate(_SICHTBAR) == ["congstar 36", "o2 36"]
    assert "laufzeit=36" in seite.evaluate("location.search")


def test_der_filter_laeuft_nicht_aus_dem_bild(seite):
    ueber = seite.evaluate("""() => {
      const l = document.querySelector('#gr-zr-laufzeiten')
        .getBoundingClientRect();
      return Array.from(document.querySelectorAll('#gr-zr-laufzeiten button'))
        .filter(k => k.getBoundingClientRect().right > l.right + 0.5
                  || k.getBoundingClientRect().right > window.innerWidth)
        .map(k => k.textContent)}""")
    assert ueber == []
    assert seite.evaluate(
        "() => document.documentElement.scrollWidth <= window.innerWidth"
    )


def test_der_trade_in_steht_neben_der_leitzahl_und_im_rechenweg(seite):
    zeile = seite.query_selector(
        "#gr-bnd-gruppe .gr-bnd[data-anbieter='congstar']:not([hidden])"
    )
    assert (
        zeile.query_selector(".gr-bnd-aktion").inner_text()
        == "bis −324,00 € mit Altgerät"
    )
    assert "1.567,00 €" in zeile.query_selector(".gr-bnd-tco").inner_text()
    zeile.query_selector("summary").click()
    seite.wait_for_timeout(150)
    text = zeile.query_selector(".gr-kk-aktion").inner_text()
    assert "Trade-in −324,00 €" in text and "nicht eingerechnet" in text
    assert (
        zeile.query_selector(".gr-kk-aktion a")
        .get_attribute("href")
        .startswith("https://www.congstar.de/")
    )
    _waehle(seite, "36")
    ohne = seite.query_selector(
        "#gr-bnd-gruppe .gr-bnd[data-anbieter='congstar']:not([hidden])"
    )
    assert ohne.query_selector(".gr-bnd-aktion") is None
