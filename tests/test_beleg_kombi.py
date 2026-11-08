"""Der Beleg folgt der gewählten Kombination (Antonio, 08.11.2026).

Gerät × Speicher × Tarifband × Laufzeit × Anbieter: die Seite zeigt nur ein Bild, dessen
Preiszeile zur Wahl passt, wechselt es mit der Wahl und sagt ohne Bild „Für diese
Kombination liegt noch kein Screenshot vor“, nie das Bild einer anderen Kombination.
Ein Beleg mit ``bildfolge`` zeigt alle Bilder in Reihenfolge mit Schrittbeschriftung.
Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7). Die Seite wird mit
``render_site`` gebaut (Fixture von ``test_beleg_position``), die Wahl im echten
Chromium getroffen.
"""

from __future__ import annotations

import functools
import http.server
import json
import threading
from datetime import date
from pathlib import Path

import pytest
import test_beleg_position as pos
import test_geraete_buendel_kopf_zeitraum as kopf_zeitraum
from bs4 import BeautifulSoup

from telco_radar.beleg_bildfolge import ADRESSE_ANFANG, SCHRITTE, normalisiere
from telco_radar.beleg_manifest import (
    MANIFEST_NAME,
    Beleg,
    baue_manifest,
    lies,
    schreibe,
)
from telco_radar.report.html import render_site

ID_O2_36 = "e" * 64
KEINS = "Für diese Kombination liegt noch kein Screenshot vor."
FOLGE = [
    ("geraet_speicher", "iPhone 17 Pro 256 GB gewählt"),
    ("tarif", "O2 Mobile Klein gewählt"),
    ("preis", "1,00 € Zuzahlung, 18,00 € im Monat"),
]
PNG = pos.PNG


def _datei(nr: int) -> str:
    return f"{pos.MODELL}__o2__{pos.HEUTE}__schritt{nr}.webp"


def _adresse(nr: int) -> str:
    """Die Adresse eines veröffentlichten Anhangs (nur eine Adresse zählt)."""
    return f"{ADRESSE_ANFANG}{pos.HEUTE}/{_datei(nr)}"


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """o2 mit zwei Zeilen: 24 Raten (eindeutig günstigster Satz, Bild mit Bildfolge)
    und 36 Raten (kein Bild)."""
    site = kopf_zeitraum._baue(tmp_path_factory.mktemp("beleg_kombi"))
    wurzel = site.parent
    state = wurzel / "data" / "state"
    bestand = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    vodafone = [b for b in bestand["buendel"] if b["anbieter"] == "Vodafone"]
    saetze = [
        pos._satz("o2", "O2 Mobile Klein", "o2:klein", 24, 18.0, pos.ID_O2),
        pos._satz("o2", "O2 Mobile Klein", "o2:klein", 36, 20.0, ID_O2_36),
    ]
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": pos.HEUTE, "buendel": [*saetze, *vodafone]}),
        encoding="utf-8",
    )
    manifest = baue_manifest({f"belege-{pos.HEUTE}": [pos._bild("o2")]}, pos.TAG)
    manifest["belege"][0]["bildfolge"] = [
        {"datei": _adresse(nr), "schritt": schritt, "text": text}
        for nr, (schritt, text) in enumerate(FOLGE, start=1)
    ]
    schreibe(state / MANIFEST_NAME, manifest)
    render_site(site, wurzel / "data" / "reports")
    return site


@pytest.fixture(scope="module")
def seite(site) -> BeautifulSoup:
    return BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


def _o2(seite: BeautifulSoup):
    return next(
        li for li in seite.select(".gr-beleg-paar") if li["data-anbieter"] == "o2"
    )


def test_bildfolge_mit_drei_eintraegen_steht_in_reihenfolge(seite):
    """Drei Bilder, Reihenfolge und Schrittbeschriftung wie im Datensatz."""
    zeile = _o2(seite).select_one(".gr-beleg-zeile")
    schritte = zeile.select(".gr-bildfolge > li")
    assert len(schritte) == len(FOLGE)
    for nr, (li, (schritt, text)) in enumerate(
        zip(schritte, FOLGE, strict=True), start=1
    ):
        assert li.select_one(".gr-bildfolge-schritt").get_text(strip=True) == (
            f"Schritt {nr} von {len(FOLGE)}: {SCHRITTE[schritt]}"
        )
        assert li.select_one(".gr-bildfolge-text").get_text(strip=True) == text
        assert li.select_one("img")["data-src"].endswith(f"/{_datei(nr)}")
    assert "Screenshot-Folge (3 Bilder)" in zeile.summary.get_text(" ", strip=True)


def test_ohne_bildfolge_bleibt_es_ein_bild(tmp_path):
    """Rückwärtskompatibel: ein Manifest ohne ``bildfolge`` zeigt das eine Bild."""
    manifest = baue_manifest({f"belege-{pos.HEUTE}": [pos._bild("o2")]}, pos.TAG)
    schreibe(tmp_path / MANIFEST_NAME, manifest)
    (beleg,) = lies(tmp_path / MANIFEST_NAME)
    assert beleg.bildfolge == ()


def test_bildfolge_wird_normalisiert_nie_aufgefuellt():
    """Nur die Adresse eines Release-Anhangs zählt: ein Dateiname, ein Pfad, eine fremde
    Adresse oder ein Eintrag ohne Datei fällt weg (#70 baute Links aus Namen)."""
    gut = f"{ADRESSE_ANFANG}2026-11-08/a__b__2026-11-08__tarif__0123456789abcdef.webp"
    roh = [
        {"datei": "a.webp", "schritt": "tarif", "text": "t"},
        {"datei": "../b.webp", "schritt": "preis"},
        {"schritt": "preis"},
        "kaputt",
        {"datei": "https://y.invalid/c.webp", "schritt": "neu"},
        {"datei": f"{ADRESSE_ANFANG}2026-11-08/../x.webp", "schritt": "neu"},
        {"datei": gut, "schritt": "tarif", "text": "t"},
    ]
    folge = normalisiere(roh)
    assert [(f["url"], f["name"]) for f in folge] == [(gut, SCHRITTE["tarif"])]
    assert normalisiere(None) == () and normalisiere("x") == ()
    assert normalisiere([{"datei": "a.webp", "schritt": "tarif"}]) == ()
    basis = f"{ADRESSE_ANFANG}2026-11-08/a__b__2026-11-08.webp"
    assert Beleg("g", "a", date(2026, 11, 8), False, basis).bildfolge == ()


def test_luecke_steht_an_der_stelle_ihres_schritts_mit_grund():
    """Fehlt ein Schritt, nennt ihn die Folge mit Grund und zählt ihn mit."""
    adresse = f"{ADRESSE_ANFANG}2026-11-08/"
    roh = [
        {
            "datei": f"{adresse}n__a__2026-11-08__tarif__0123456789abcdef.webp",
            "schritt": "geraet_speicher",
        },
        {"datei": f"{adresse}n__a__2026-11-08.webp", "schritt": "preis"},
    ]
    folge = normalisiere(roh, ["tarif: Seite markiert keine Option", "kaputt"])
    assert [(f["schritt"], bool(f["url"]), f["fehlt"]) for f in folge] == [
        ("geraet_speicher", True, ""),
        ("tarif", False, "Seite markiert keine Option"),
        ("preis", True, ""),
    ]
    assert normalisiere([], ["tarif: x"]) == ()


def _sichtbar(s, anbieter: str) -> dict:
    """Was der Leser unter dem Anbieter sieht: Zeilen mit Bild und Vermerke."""
    return s.evaluate(
        """(anb) => {
          const li = [...document.querySelectorAll('#gr-bnd-gruppe .gr-beleg-paar')]
            .find(l => l.getAttribute('data-anbieter') === anb);
          const sicht = e => e.getBoundingClientRect().height > 0
            && !e.closest('[hidden]');
          if (!li || !sicht(li)) return {anbieter: false};
          return {anbieter: true,
            zeilen: [...li.querySelectorAll('.gr-beleg-zeile')].filter(sicht)
              .map(z => z.querySelector('summary').textContent),
            bilder: [...li.querySelectorAll('.gr-beleg-zeile img')]
              .filter(i => sicht(i) || !i.closest('[hidden]')).length,
            vermerke: [...li.querySelectorAll('.gr-beleg-keins')].filter(sicht)
              .map(k => k.textContent.trim())};
        }""",
        anbieter,
    )


def _offene_bilder(s) -> int:
    """Klappt jeden Aufklapper der Belegstelle auf, zählt die sichtbaren Bilder."""
    return s.evaluate(
        """() => {
          document.querySelectorAll('#gr-bnd-gruppe .gr-beleg-paare details')
            .forEach(d => { d.open = true; });
          return [...document.querySelectorAll('#gr-bnd-gruppe .gr-beleg-paare img')]
            .filter(i => i.getBoundingClientRect().height > 0).length;
        }"""
    )


@pytest.mark.browser
def test_der_beleg_wechselt_mit_der_laufzeit_und_zeigt_nie_ein_fremdes_bild(
    site, chromium
):
    """Bei 24 Raten steht das Bild (Bildfolge); bei 36 Raten, wo keins vorliegt, steht
    der Vermerk und kein einziges Bild; zurück auf 24 kommt es wieder."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        for breite in (1440, 390):
            ctx = chromium.new_context(viewport={"width": breite, "height": 900})
            try:
                ctx.route(
                    "https://github.com/**",
                    lambda r: r.fulfill(body=PNG, content_type="image/png"),
                )
                s = ctx.new_page()
                meldungen: list[str] = []
                s.on("console", lambda m, k=meldungen: k.append(m.text))
                s.on("pageerror", lambda e, k=meldungen: k.append(str(e)))
                adresse = f"http://127.0.0.1:{httpd.server_address[1]}/geraete.html"
                s.goto(adresse, wait_until="domcontentloaded")
                s.click("#gr-zr-laufzeiten button[data-lz='24']")
                a = _sichtbar(s, "o2")
                assert len(a["zeilen"]) == 1 and "24 Raten" in a["zeilen"][0], a
                assert a["bilder"] == len(FOLGE) and a["vermerke"] == [], a
                s.click("#gr-zr-laufzeiten button[data-lz='36']")
                b = _sichtbar(s, "o2")
                assert b["zeilen"] == [] and b["bilder"] == 0, b
                assert b["vermerke"] == [KEINS], b
                assert _offene_bilder(s) == 0, breite
                s.click("#gr-zr-laufzeiten button[data-lz='24']")
                assert _sichtbar(s, "o2")["bilder"] == len(FOLGE)
                assert _offene_bilder(s) == len(FOLGE), breite
                s.locator("#gr-bnd-gruppe .gr-beleg-zeile summary").first.click()
                s.wait_for_function(
                    "[...document.querySelectorAll('.gr-bildfolge img')]"
                    ".every(i => i.hasAttribute('src'))"
                )
                assert s.evaluate("document.documentElement.scrollWidth") <= breite
                assert meldungen == [], breite
            finally:
                ctx.close()
    finally:
        httpd.shutdown()
