"""Zahlenfehler F2, F7 und F9 im echten Chromium (Übergabe Antonio, 14.10.2026).

Der Reiter „Preisverlauf“ rechnet im Browser (`app.js`): Wochenraster,
Kacheln „Niedrigster/Höchster Preis“ und die große Zahl „aktuell“. Fixture:
ein Gerät, o2 mit fünf Messtagen in zwei Kalenderwochen (Tiefstwert mitten
in der ersten Woche), Vodafone günstiger, aber zuletzt am 20.08. gelesen.
"""

from __future__ import annotations

import contextlib
import json

import pytest
import test_geraete_browser_fixture as fx
import yaml

from telco_radar.report.html import render_site

DEVICE = "apple-iphone-17-pro"
SPEICHER = 256

_O2 = [
    ("2026-09-01", 950.00),
    ("2026-09-02", 899.00),
    ("2026-09-04", 949.00),
    ("2026-09-05", 955.00),
    ("2026-09-10", 960.00),
]
_VODAFONE_ALT = ("2026-08-20", 930.00)


def _punkt(anbieter, tag, preis):
    return {
        "listung_id": f"{anbieter.lower()}--{fx._sku(DEVICE, SPEICHER)}",
        "datum": tag,
        "preis_ohne_vertrag": preis,
        "preisart": "ohne_vertrag",
        "quelle_url": "https://example.de/beleg",
    }


def _baue(tmp_path):
    root = tmp_path / "site_baum"
    (root / "config").mkdir(parents=True)
    for name, daten in (
        ("geraete_katalog.yaml", fx._KATALOG),
        ("farben.yaml", fx._FARBEN),
        ("geraete_quellen.yaml", fx._QUELLEN),
    ):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    state = root / "data" / "state"
    state.mkdir(parents=True)
    o2 = fx._listung("o2", DEVICE, SPEICHER, _O2[-1][1])
    o2["last_verified"] = _O2[-1][0]
    vf = fx._listung("Vodafone", DEVICE, SPEICHER, _VODAFONE_ALT[1])
    vf["last_verified"] = vf["abgerufen_am"] = _VODAFONE_ALT[0]
    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": fx.HEUTE,
                "anbieter": {
                    "o2": {"laeufe": 4, "funde_gesamt": 1},
                    "Vodafone": {"laeufe": 4, "funde_gesamt": 1},
                },
                "listungen": [o2, vf],
            }
        ),
        encoding="utf-8",
    )
    punkte = [_punkt("o2", t, p) for t, p in _O2]
    punkte.append(_punkt("Vodafone", *_VODAFONE_ALT))
    punkte.append(_punkt("Vodafone", "2026-08-10", 940.0))
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps(p) for p in punkte) + "\n", encoding="utf-8"
    )
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": fx.HEUTE, "buendel": [], "sim_only": []}),
        encoding="utf-8",
    )
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{fx.HEUTE}.json").write_text(
        json.dumps(
            {
                "date": fx.HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{fx.HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@contextlib.contextmanager
def _browser_ctx(tmp_path_factory, chromium):
    site = _baue(tmp_path_factory.mktemp("zahlenfehler"))
    with fx._server(site) as wurzel:
        yield wurzel, chromium


@pytest.fixture(scope="module")
def _browser_paar(tmp_path_factory, chromium):
    with _browser_ctx(tmp_path_factory, chromium) as (wurzel, browser):
        yield wurzel, browser


@pytest.fixture
def seite(_browser_paar):
    wurzel, browser = _browser_paar
    s = browser.new_page()
    s.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
    s.click('.gr-reiter [data-tafel="tafel-verlauf"]')
    s.wait_for_timeout(120)
    s.fill("#gr-vsuche", "iPhone 17 Pro")
    s.wait_for_timeout(150)
    s.click("#gr-vtreffer li:first-child")
    s.wait_for_timeout(300)
    yield s
    s.close()


def _text(seite, sel):
    return seite.eval_on_selector(sel, "e => e.textContent.trim()")


def test_f7_tiefst_und_hoechstwert_kommen_aus_allen_messpunkten(seite):
    """Das Wochenraster behält je Woche den letzten Punkt (955 € am 05.09.);
    der Tiefstwert 899 € vom 02.09. gehört trotzdem in die Kachel."""
    assert _text(seite, "#gr-vmin") == "899,00 €"
    assert _text(seite, "#gr-vmax") == "960,00 €"


def test_f7_woche_beginnt_am_montag(seite):
    """Di 01.09. bis Sa 05.09. liegen in derselben Kalenderwoche, Do 10.09. in
    der nächsten: die o2-Linie hat genau zwei Punkte, der 05.09. bleibt."""
    titel = seite.evaluate(
        "() => [...document.querySelectorAll('#gr-vbild circle.gr-vpunkt title')]"
        ".map(t => t.textContent).filter(t => t.startsWith('o2:'))"
    )
    assert titel == ["o2: 955,00 € am 5.9.", "o2: 960,00 € am 10.9."], titel


def test_f2_aktuell_nennt_keinen_alten_preis(seite):
    """Vodafone ist mit 930 € günstiger, aber seit dem 20.08. nicht gelesen:
    „aktuell“ ist o2 mit 960 € vom 10.09."""
    assert _text(seite, "#gr-vaktuell") == "960,00 €"
    assert "o2" in _text(seite, "#gr-vleit-label")
