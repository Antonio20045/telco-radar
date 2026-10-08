"""Klick-Karte congstar (config/klickkarten/congstar.yaml) gegen gespeicherte Daten.

- congstar_graphql_20261007.json.gz: die drei GraphQL-Antworten beim Laden je Seite der
  Klick-Erkundung vom 07.10.2026 (Seite 1 iPhone 17 Pro, Seite 2 Galaxy S26),
  unverändert.
  Seite 2 Nr. 63 (Tarife) gleicht Seite 1 Nr. 62 und liegt nicht doppelt im Fixture.
  Seite 2 ist im Kameleoon-Test 453: der Warenkorb-Link nennt die Gerätevariante nur in
  data-kam-dke-453-source (bedienelemente-2.json El. 509), darum ``geraet_ab``.
- congstar_produkt_*.html.gz (29.09. und 31.08.2026): serverseitig gerenderte
  Produktseiten mit denselben Knöpfen und Kästen; ohne Skripte sind sie bis zur
  Hydrierung unsichtbar, der Test macht sie sichtbar (sonst ist ``innerText`` leer).

Kontrollsummen aus der Seite vom 07.10. (preise-1/-2.json Nr. 10): „Maximaler
Gesamtpreis … 1295,00 €“ = 179 + 36 × 31 und „613,00 €“ = 1 + 36 × 17; mit Rückgabedeal
zeigte die Seite 24,00 € und 179,00 € (preise-1.json Nr. 0–2), „Summe einmalig
194,00 €“ ist Anzahlung plus Bereitstellung 15 € (Nr. 46).
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import pytest

from telco_radar.collect.geraete import klicktextleser
from telco_radar.collect.geraete.klickbedienung import kanarientext
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klickoptionen import lies_optionen
from telco_radar.collect.geraete.klickpfad import am_pfad
from telco_radar.collect.geraete.klickquellen import Quellenleser
from telco_radar.collect.geraete.klicktextleser import Textleser
from telco_radar.tarif_model import Preisphase

WURZEL = Path(__file__).parent.parent
_FIX = Path(__file__).parent / "fixtures" / "geraete"
KARTE = lade_klickkarte(WURZEL / "config" / "klickkarten" / "congstar.yaml")
LADEN = json.loads(
    gzip.decompress((_FIX / "congstar_graphql_20261007.json.gz").read_bytes())
)["antworten"]
SEITE_1 = ("1/62", "1/63", "1/64")
SEITE_2 = ("1/62", "2/64", "2/65")
WARENKORB_1 = (
    "https://www.congstar.de/handytarife/addon/5g-option"
    "?planId=540&deviceVariantId=304327"
)
KAMELEOON_2 = "/handytarife/addon/5g-option?planId=540&deviceVariantId=304534"
SICHTBAR = "*{visibility:visible !important}"


class _Anfrage:
    method = "POST"
    post_data_buffer = None

    def all_headers(self):
        return {}


class _Antwort:
    status = 200
    status_text = "OK"
    request = _Anfrage()
    url = "https://www.congstar.de/webshop-graphql/graphql"

    def __init__(self, roh: str) -> None:
        self._roh = roh

    def json(self):
        return json.loads(self._roh)

    def body(self):
        return self._roh.encode("utf-8")

    def all_headers(self):
        return {"content-type": "application/json"}


class _Mitschnitt:
    def __init__(self, schluessel: tuple[str, ...]) -> None:
        self._antworten = [_Antwort(LADEN[s]) for s in schluessel]

    def antworten_seit(self, seit):
        return self._antworten[seit:]


class _Seite:
    url = "https://www.congstar.de/geraete/apple/apple-iphone-17-pro/"


def _lies(schluessel, **platz):
    leser = Quellenleser(_Seite(), KARTE, _Mitschnitt(schluessel))
    voll = {"plan": None, "geraet": None, "geraet_ab": None, "modell": None, **platz}
    return leser.lies(0, False, voll, 0)


def test_karte_laedt_mit_fuenf_ladequellen():
    assert KARTE.anbieter == "congstar"
    assert set(KARTE.seite) == {"plan", "geraet", "geraet_ab"}
    assert len(KARTE.lesequellen) == 5
    assert all(q.laden for q in KARTE.lesequellen)
    assert all(q.passt(_Antwort.url) for q in KARTE.lesequellen)


@pytest.mark.parametrize(
    ("schluessel", "platz", "erwartet"),
    [
        (
            SEITE_1,
            {"geraet": "304327", "speicher": "512 GB", "laufzeit": "36"},
            (179.0, 31.0, 36, "512 GB"),
        ),
        (
            SEITE_1,
            {"geraet": "304327", "speicher": "512 GB", "laufzeit": "24"},
            (179.0, 46.5, 24, "512 GB"),
        ),
        (
            SEITE_2,
            {"geraet_ab": "304534", "speicher": "256 GB", "laufzeit": "36"},
            (1.0, 17.0, 36, "256 GB"),
        ),
    ],
    ids=["seite1_36", "seite1_24", "seite2_kameleoon_36"],
)
def test_kombination_aus_den_ladeantworten(schluessel, platz, erwartet):
    lesung = _lies(schluessel, plan="540", tarif="Allnet Flat M", **platz)

    assert lesung.befund is None
    w, v = lesung.lesung.werte, lesung.lesung.variante
    assert (w.anzahlung, w.rate, w.ratenzahl, v["speicher"]) == erwartet
    assert w.tarifphasen == (Preisphase(1, None, 25.0),)
    assert (w.tarifbindung, w.volumen_gb, w.anschluss) == (24, 125.0, 15.0)
    assert v["tarif"] == "Allnet Flat M"
    assert set(lesung.json_pfade) == {
        "anschluss",
        "anzahlung",
        "rate",
        "ratenzahl",
        "tarifphasen",
        "tarifbindung",
        "volumen_gb",
    }


def test_anderer_tarif_liest_seine_variante():
    lesung = _lies(
        SEITE_1, plan="560", geraet="304327", tarif="Allnet Flat S", laufzeit="36"
    )

    w = lesung.lesung.werte
    assert lesung.lesung.variante["tarif"] == "Allnet Flat S"
    assert (w.tarifphasen, w.volumen_gb) == ((Preisphase(1, None, 20.0),), 50.0)
    flex = _lies(SEITE_1, plan="548", geraet="304327", laufzeit="36")
    assert flex.lesung.variante["tarif"] == "Allnet Flat M Flex"
    assert (flex.lesung.werte.tarifbindung, flex.lesung.werte.anschluss) == (0, 35.0)


@pytest.mark.parametrize(
    ("platz", "fehlt"),
    [
        ({"plan": "540"}, "rate"),
        ({"plan": "540", "geraet": "304327", "laufzeit": "12"}, "rate"),
        ({"geraet": "304327", "laufzeit": "36"}, "tarifphasen"),
    ],
    ids=["ohne_geraet", "laufzeit_ohne_angebot", "ohne_plan"],
)
def test_gegenprobe_ohne_seitenwert_kein_wert(platz, fehlt):
    lesung = _lies(SEITE_1, tarif="Allnet Flat M", speicher="512 GB", **platz)

    assert lesung.lesung is not None
    assert getattr(lesung.lesung.werte, fehlt) is None


def test_gesamtpreis_und_rueckgabedeal_der_seite():
    daten = json.loads(LADEN["1/64"])
    zahlweise = (
        "data.plans.*.variants[id=540].devices.*.variants[id=304327]"
        ".prices.paymentVariants[subtype={art}][contractDuration=36]"
    )
    ohne = zahlweise.replace("{art}", "UNSPECIFIED")
    mit = zahlweise.replace("{art}", "TRADE_IN")

    assert am_pfad(daten, ohne + ".total") == 1295.0 == 179 + 36 * 31
    assert am_pfad(daten, mit + ".recurring.discounted") == 24.0
    assert am_pfad(daten, mit + ".oneTime.discounted") == 179.0
    plan = json.loads(LADEN["1/62"])
    bereitstellung = "data.plans.*.variants[id=540].prices.activation.discounted"
    assert 179.0 + am_pfad(plan, bereitstellung) == 194.0


def _ssr(chromium, datei: str):
    html = gzip.decompress((_FIX / datei).read_bytes()).decode("utf-8")
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S)
    html = re.sub(r"<link\b[^>]*>", "", html)
    seite = chromium.new_page(viewport={"width": 1280, "height": 900})
    seite.set_content(html, wait_until="domcontentloaded")
    seite.add_style_tag(content=SICHTBAR)
    return seite


def _optionen(seite, dimension):
    return [(o.wert, o.gewaehlt) for o in lies_optionen(seite, KARTE, dimension)]


def test_knoepfe_marken_und_seitenwerte_der_produktseite(chromium):
    seite = _ssr(chromium, "congstar_produkt_iphone17_20260929.html.gz")
    try:
        assert _optionen(seite, "speicher") == [("256 GB", True), ("512 GB", False)]
        assert _optionen(seite, "tarif") == [
            ("Allnet Flat XS", False),
            ("Allnet Flat S", False),
            ("Allnet Flat M", True),
            ("Allnet Flat L", False),
        ]
        assert _optionen(seite, "laufzeit") == [("36", True), ("24", False)]
        kanarie = seite.locator(KARTE.kanarie.selektor).inner_text()
        assert kanarientext(KARTE.kanarie, None) in kanarie

        leser = Quellenleser(seite, KARTE, _Mitschnitt(()))
        assert leser.seitenwerte() == {"plan": "540", "geraet": None, "geraet_ab": None}
        link = seite.locator("a", has_text="Weiter zum Warenkorb")
        assert link.get_attribute("href") == "/handytarife/addon/5g-option"
        link.evaluate("(a, h) => a.setAttribute('href', h)", WARENKORB_1)
        assert leser.seitenwerte()["geraet"] == "304327"
        link.evaluate("(a, h) => a.setAttribute('href', h)", "/checkout/")
        link.evaluate(
            "(a, h) => a.setAttribute('data-kam-dke-453-source', h)", KAMELEOON_2
        )
        assert leser.seitenwerte() == {
            "plan": "540",
            "geraet": None,
            "geraet_ab": "304534",
        }
    finally:
        seite.close()


@pytest.mark.parametrize(
    ("datei", "erwartet"),
    [
        (
            "congstar_produkt_pixel11.html.gz",
            [("256 GB", False, True), ("512 GB", True, False)],
        ),
        (
            "congstar_produkt_iphone17_20260929.html.gz",
            [("256 GB", False, True), ("512 GB", False, False)],
        ),
    ],
)
def test_speicher_nicht_vorhanden_ist_gesperrt(chromium, datei, erwartet):
    """Pixel 11: aria-label „512 GB nicht vorhanden“ ohne disabled (Tageslauf 08.10.:
    acht Kombinationen ohne Tarifknöpfe); Gegenprobe iPhone 17, 512 GB lieferbar."""
    seite = _ssr(chromium, datei)
    try:
        optionen = lies_optionen(seite, KARTE, "speicher")
        assert [(o.wert, o.deaktiviert, o.gewaehlt) for o in optionen] == erwartet
    finally:
        seite.close()


@pytest.mark.parametrize(
    ("datei", "rueckgabedeal"),
    [
        ("congstar_produkt_iphone17_20260929.html.gz", True),
        ("congstar_produkt_galaxy_s25.html.gz", False),
        ("congstar_produkt_redmi_note_17_pro.html.gz", False),
    ],
)
def test_vorbereitung_klickt_nur_mit_rueckgabedeal(chromium, datei, rueckgabedeal):
    (schritt,) = KARTE.vorbereitung
    seite = _ssr(chromium, datei)
    try:
        assert seite.locator(schritt.pruefe).count() == 1
        erfuellt = seite.locator(schritt.pruefe).first.evaluate(
            "(e, css) => e.matches(css)", schritt.bis
        )
        assert erfuellt is not rueckgabedeal
        assert seite.locator(schritt.klick).count() == int(rueckgabedeal)
    finally:
        seite.close()


def test_zusammenfassung_ohne_rueckgabedeal(chromium, monkeypatch):
    """Selektoren und Muster der Textlesung; der Lesetakt (50 ms je Versuch) reicht
    unter paralleler Testlast nicht einmal für „body“ und ist hier verlängert."""
    monkeypatch.setattr(klicktextleser, "WARTE_TAKT_MS", 1000)
    seite = _ssr(chromium, "congstar_produkt_galaxy_s25.html.gz")
    try:
        leser = Textleser(seite, KARTE, 1000)
        text = leser.zusammenfassung(seite.locator(KARTE.zusammenfassung).first)
        werte, _, fundorte = leser.textwerte(text)
    finally:
        seite.close()

    assert "Summe ab dem 37. Monat" in text
    assert (werte.rate, werte.ratenzahl, werte.anzahlung) == (14.0, 36, 15.0)
    assert werte.tarifphasen == (Preisphase(1, None, 24.0),)
    assert (werte.tarifbindung, werte.volumen_gb, werte.anschluss) == (24, 125.0, 15.0)
    assert set(fundorte) == {
        "anschluss",
        "rate",
        "ratenzahl",
        "tarifphasen",
        "anzahlung",
        "tarifbindung",
        "volumen_gb",
    }
