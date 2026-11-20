"""Am Telefon (390 px) zeigt eine Gerätekarte in "Alle Geräte" höchstens
zwei Textzeilen (RUHIG-RUNDE3-1119-R4, 20.11.2026, Prüfbefund
pruefung-ruhig-pr160-1120.md).

Die style.css-Regel fuer `td[data-k="Ø €/Monat"]` und `td[data-k="Stufe"]`
(display:none im @media max-width:700px-Block) wurde beim Laden von der
spezifischeren Block-Regel der TCO-Ansicht (`.gr-katalog-mod.gr-katalog--tco
>tbody>tr.gr-a-zeile>td:not(.gr-sp--barpreis){display:block}`) überschrieben
- die Standardansicht beim Laden IST die TCO-Ansicht, der Fehler betraf also
den normalen ersten Blick. Dieser Test prueft den COMPUTED `display` im
echten Chromium, nicht das Attribut - genau der Fall, den eine reine
Markup-Pruefung nicht sieht (`report/CLAUDE.md`: "Sichtbarkeit ... werden
im Browser gemessen").
"""

from __future__ import annotations

import functools
import http.server
import threading

import pytest
import test_geraete_seite


@pytest.fixture(scope="module")
def basis(tmp_path_factory):
    site = test_geraete_seite._baue(tmp_path_factory.mktemp("katalog-karte"))
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


def _anzeige_je_spalte(chromium, basis, breite, hoehe):
    seite = chromium.new_page(viewport={"width": breite, "height": hoehe})
    try:
        seite.goto(f"{basis}/geraete.html")
        tabelle = seite.locator("#gr-katalogtabelle")
        assert tabelle.count() == 1
        assert "gr-katalog--tco" in (tabelle.get_attribute("class") or "")
        monat = tabelle.locator('tbody>tr.gr-a-zeile>td[data-k="Ø €/Monat"]').first
        stufe = tabelle.locator('tbody>tr.gr-a-zeile>td[data-k="Stufe"]').first
        assert monat.count() == 1
        assert stufe.count() == 1
        return (
            monat.evaluate("e => getComputedStyle(e).display"),
            stufe.evaluate("e => getComputedStyle(e).display"),
        )
    finally:
        seite.close()


def test_am_telefon_sind_monat_und_stufe_ausgeblendet(basis, chromium):
    monat, stufe = _anzeige_je_spalte(chromium, basis, 390, 844)
    assert monat == "none"
    assert stufe == "none"


def test_am_rechner_bleiben_monat_und_stufe_sichtbar(basis, chromium):
    monat, stufe = _anzeige_je_spalte(chromium, basis, 1440, 900)
    assert monat != "none"
    assert stufe != "none"
