"""Belegte Lücke auf dem Telefon (390 px): kein Querscrollen, Grund als Text.

PR #59, Prüfung 08.11.2026: der Legendeneintrag „frühere Preise überholt“ der
Zeitreihe (`.gr-zr-leg-ueberholt`) war `nowrap` und schob die Seite auf 452 px.
Dazu steht der Grund der Lücke sichtbar in der Zeile des Anbieters, nicht nur im
Tooltip (`title`), den ein Telefon nicht zeigt.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import test_geraete_export_mobil_browser as export
import test_geraete_zeitreihe_ansicht as bestand
import yaml

from telco_radar.report.html import render_site

HEUTE = bestand.HEUTE

GRUND = (
    "Gerät ist nicht in der Geräteliste (Apple-Übersicht) und nicht in der "
    "Sitemap; die Seite leitet auf die Übersicht um"
)


def _baue_site(tmp_path: pathlib.Path) -> pathlib.Path:
    """Das Zeitreihen-Testbestand; o2 iPhone 17 Pro ist am Abrufdatum seines
    Bündels als nicht im Sortiment geprüft (Gleichstand: der Preis ist überholt,
    die Messtage davor bleiben als Reihe ohne Serie übrig). Widerspruchsregel vom
    10.11.2026: ein lieferbares, frisches Neugerät derselben Kombination hebt die
    Lücke auf, also ist o2 iPhone 17 Pro in der Geräteliste nicht lieferbar."""
    root, _ = bestand._baue(tmp_path)
    db_pfad = root / "data" / "state" / "geraete_db.json"
    db = json.loads(db_pfad.read_text(encoding="utf-8"))
    for e in db["listungen"]:
        if e["anbieter"] == "o2" and e["device_id"] == "apple-iphone-17-pro":
            e["verfuegbarkeit"] = "nicht_lieferbar"
    db_pfad.write_text(json.dumps(db), encoding="utf-8")
    (root / "config" / "geraete_abdeckung.yaml").write_text(
        yaml.safe_dump(
            {
                "pflicht_anbieter": ["o2"],
                "belegte_luecken": [
                    {
                        "anbieter": "o2",
                        "modelle": ["apple-iphone-17-pro"],
                        "grund": GRUND,
                        "art": "nicht_im_portfolio",
                        "beleg": "https://example.de/beleg.png",
                        "original": "https://example.de/original",
                        "geprueft": HEUTE,
                        "bis": "2026-09-30",
                    }
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
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
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@pytest.fixture(scope="module")
def _seite(tmp_path_factory, chromium):
    site = _baue_site(tmp_path_factory.mktemp("luecke_mobil"))
    with export._server(site) as basis:
        yield chromium, basis


def _messe(chromium, basis, breite):
    kontext = chromium.new_context(viewport={"width": breite, "height": 844})
    s = kontext.new_page()
    try:
        s.goto(f"{basis}/geraete.html?modell=apple-iphone-17-pro-256")
        s.wait_for_timeout(400)
        return s.evaluate(
            """() => {
              const sichtbar = (el) => el && el.getClientRects().length > 0;
              const leg = document.querySelector('.gr-zr-leg-ueberholt');
              const fehl = [...document.querySelectorAll('.gr-anb-fehlt')]
                .find((z) => z.dataset.anbieter === 'o2');
              const detail = fehl && fehl.querySelector('.gr-anb-fehlt-detail');
              return {
                doc: document.documentElement.scrollWidth,
                fenster: window.innerWidth,
                legende: leg ? leg.textContent : null,
                legende_sichtbar: sichtbar(leg),
                detail: detail ? detail.textContent : null,
                detail_sichtbar: sichtbar(detail),
              };
            }"""
        )
    finally:
        kontext.close()


def test_der_legendeneintrag_schiebt_die_seite_auf_390_px_nicht(_seite):
    chromium, basis = _seite
    m = _messe(chromium, basis, 390)
    assert m["legende"] and "überholt" in m["legende"], m
    assert m["legende_sichtbar"], m
    assert m["doc"] <= m["fenster"], m


def test_der_grund_der_luecke_steht_sichtbar_in_der_zeile(_seite):
    chromium, basis = _seite
    m = _messe(chromium, basis, 390)
    assert m["detail"] == GRUND and m["detail_sichtbar"], m
    assert m["doc"] <= m["fenster"], m
