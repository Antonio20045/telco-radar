"""congstar-Flex (planId 548) mit der Karte config/klickkarten/congstar.yaml.

Die Erkundung vom 10.10.2026 (Zweig klick-erkundung 0e0d2207, congstar/2026-10-10)
zeigt mit ?planId=548 das Label „Ohne Laufzeit (mtl. kündbar)“ gewählt, ohne Zahl;
die Zahl steht nur am Input „Mindestlaufzeit von 0 Monaten“ (bedienelemente-2.json
El. 108–111). Die Zusammenfassung schreibt „Tarif (mtl. kündbar) 15,00 €“ statt
„Tarif 15,00 €“ (karte-2.json). Der Test stellt die gespeicherte Produktseite
congstar_produkt_galaxy_s25.html.gz auf diesen Zustand um: die Wahl liegt auf der
Flex-Kachel (Input 548), die Tarifzeile trägt den Flex-Zusatz. Erwartet: Bindung 0 aus
dem Attribut und der Tarifbetrag. Gegenprobe ohne Umstellung: Bindung 24.
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path

import pytest
from klickbeispiel import karte
from test_geraete_klickfolgeklick import KARTE as FOLGEKARTE
from test_klickkarte_congstar import KARTE, SICHTBAR

from telco_radar.collect.geraete import klicktextleser
from telco_radar.collect.geraete.klickkarte import KlickkartenFehler
from telco_radar.collect.geraete.klickkartentypen import GRUND_ATTRIBUT_OHNE_SELEKTOR
from telco_radar.collect.geraete.klicktextleser import Textleser
from telco_radar.tarif_model import Preisphase

pytestmark = pytest.mark.browser

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "geraete"
    / "congstar_produkt_galaxy_s25.html.gz"
)

AUF_FLEX = """() => {
  const wahl = (wert) => document
    .querySelector(`input[aria-label^="Mindestlaufzeit von"][value="${wert}"]`)
    .closest("label");
  wahl("540").removeAttribute("data-selected");
  wahl("548").setAttribute("data-selected", "true");
  for (const zelle of document.querySelectorAll("div")) {
    if (zelle.children.length === 0 && zelle.textContent === "Tarif") {
      zelle.textContent = "Tarif (mtl. kündbar)";
    }
  }
}"""


def _lies(chromium, monkeypatch, flex: bool):
    monkeypatch.setattr(klicktextleser, "WARTE_TAKT_MS", 1000)
    html = gzip.decompress(FIXTURE.read_bytes()).decode("utf-8")
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S)
    html = re.sub(r"<link\b[^>]*>", "", html)
    seite = chromium.new_page(viewport={"width": 1280, "height": 900})
    seite.set_content(html, wait_until="domcontentloaded")
    seite.add_style_tag(content=SICHTBAR)
    try:
        if flex:
            seite.evaluate(AUF_FLEX)
        leser = Textleser(seite, KARTE, 1000)
        text = leser.zusammenfassung(seite.locator(KARTE.zusammenfassung).first)
        werte, _, fundorte = leser.textwerte(text)
    finally:
        seite.close()
    return text, werte, fundorte


def test_flex_bindung_aus_dem_attribut_und_tarif_mit_zusatz(chromium, monkeypatch):
    text, werte, fundorte = _lies(chromium, monkeypatch, flex=True)

    assert "Tarif (mtl. kündbar)" in text
    assert werte.tarifbindung == 0
    assert werte.tarifphasen == (Preisphase(1, None, 24.0),)
    assert fundorte["tarifbindung"][1] == "Mindestlaufzeit von 0 Monaten"


def test_gegenprobe_ohne_flex_bleibt_die_bindung_24(chromium, monkeypatch):
    _, werte, fundorte = _lies(chromium, monkeypatch, flex=False)

    assert werte.tarifbindung == 24
    assert fundorte["tarifbindung"][1] == "Mindestlaufzeit von 24 Monaten"


def test_karte_liest_die_bindung_am_attribut():
    muster = KARTE.textlesung.muster["tarifbindung"]

    assert muster.attribut == "aria-label"
    assert muster.selektor is not None


def test_gegenprobe_attribut_ohne_selektor_laedt_nicht():
    daten = {
        "zusammenfassung": {
            "selektor": "#preis",
            "muster": {"tarifbindung": {"muster": r"(\d+)", "attribut": "title"}},
        }
    }
    with pytest.raises(
        KlickkartenFehler, match=re.escape(GRUND_ATTRIBUT_OHNE_SELEKTOR)
    ):
        karte(**{**FOLGEKARTE, **daten})
