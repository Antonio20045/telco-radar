"""Kachel als eigene Quelle im Lauf: Prüferbefunde zu 3da878d3 und a1ed9e94.

BEISPIEL-Seiten aus ``test_geraete_klickweiter`` (1&1, Erkundung 07.10.2026), ohne
Netz. Die Kachel 24 nennt im Hinweis die Einmalzahlung von 24+12: Ihr Satz trägt nie
eine Einmalzahlung, nur die Lücke; die Kachel 24+12 behält ihre aus dem Echo gegen die
Globale. Trifft der Kachel-Selektor einen Rahmen mit beiden Labels, ist die Kombination
Befund; getrennte Kacheln sind die Gegenprobe. Die gespeicherte Diagnose nennt keine
Beträge (der Bündelwert daneben schon), und Warenkorb-Kennung und JSON Web Token in
Pfaden von Globalen der Folgeseite werden ``*``, die Namen davor bleiben.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
import test_geraete_klickweiter as weiter
from klickbeispiel import frage, karte, laufe_mit, nach_auswahl, seite
from klickserver import Antwort, html, umleitung

pytestmark = pytest.mark.browser

TEIL = """
<div class="teil"><add-to-cart-button
  data-linkid="content_tile :: button :: Weiter mit HW@LAUFZEIT@">Weiter
  </add-to-cart-button><p>@TEXT@</p></div>"""
KORB = "Qx7LmN2pRzWkTv"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJrdW5kZSJ9.c2lnbmF0dXI"
GLOBALE = (
    "<script>window.shop = {cart: {"
    f'"{KORB}": {{items: [{{price: 59.99}}]}}'
    "}, sitzung: {"
    f'"{JWT}": {{preis: "59.99"}}'
    "}};</script>"
)


def _preis(speicher: str) -> str:
    cent = weiter.BUENDEL[speicher]
    return f"{cent // 100} , {cent % 100:02d}"


def _mit_hinweis(speicher: str) -> str:
    """Die Kachel 24 nennt im Hinweis Betrag und Einmalzahlung von 24+12."""
    einmal = weiter.EINMAL[speicher]
    kacheln = [
        (
            "24",
            f"{weiter.OHNE_VERLAENGERUNG[speicher]} €/Mon. Tipp: mit HW24+12 nur"
            f" {_preis(speicher)} €/Mon. und Gerät nach 24 Monaten einmalig {einmal} €"
            " behalten.",
        ),
        ("24+12", f"{_preis(speicher)} €/Mon. Gerät einmalig {einmal} € behalten."),
    ]
    koerper = "".join(
        weiter.KACHEL.replace("@LAUFZEIT@", z).replace("@TEXT@", t) for z, t in kacheln
    )
    return seite(f'<div id="kacheln">{koerper}</div>', weiter.FOLGE_SKRIPT)


def _im_rahmen(speicher: str) -> str:
    """Beide Labels in einem Element, das der Kachel-Selektor als eine Kachel trifft."""
    teile = [
        ("24", f"{weiter.OHNE_VERLAENGERUNG[speicher]} €/Mon."),
        (
            "24+12",
            f"{_preis(speicher)} €/Mon. Gerät einmalig {weiter.EINMAL[speicher]} €"
            " behalten.",
        ),
    ]
    innen = "".join(
        TEIL.replace("@LAUFZEIT@", z).replace("@TEXT@", t) for z, t in teile
    )
    rahmen = f'<div id="kacheln"><div class="kachel">{innen}</div></div>'
    return seite(rahmen, weiter.FOLGE_SKRIPT)


def _antworter(folgeseite):
    start = seite(
        weiter.START.replace("@TEXT@", "Weiter zur Tarifauswahl"), weiter.START_SKRIPT
    )

    def antworte(pfad: str) -> Antwort:
        ort = urlsplit(pfad).path
        if ort == "/handy/x":
            return html(start)
        if ort == "/korb":
            return Antwort(200, "application/json", "true")
        if ort == "/bestellung/start":
            return umleitung(f"/bestellung/laufzeit?speicher={frage(pfad)['speicher']}")
        if ort == "/bestellung/laufzeit":
            return html(folgeseite(frage(pfad)["speicher"]))
        return Antwort(204)

    return antworte


def _laufe(chromium, antworte):
    lauf, _ = laufe_mit(chromium, antworte, karte(**weiter.KARTE))
    assert lauf.status == "gelesen", lauf.grund
    return nach_auswahl(lauf)


def test_kachel_24_traegt_nie_die_einmalzahlung_aus_ihrem_hinweis(chromium):
    from telco_radar.collect.geraete.klicklauf import ERFASST
    from telco_radar.collect.geraete.klicktext import Buendelwerte

    ergebnisse = _laufe(chromium, _antworter(_mit_hinweis))

    for speicher, ohne, einmal in (("128", 59.99, 300.0), ("256", 66.99, 360.0)):
        kurz = ergebnisse[(speicher, "S", 24)]
        lang = ergebnisse[(speicher, "S", 36)]
        assert kurz.textbuendel.einmalzahlung == einmal
        assert kurz.status == ERFASST, kurz.befunde
        assert kurz.buendel == Buendelwerte(buendelbetrag=ohne)
        assert "einmalzahlung" in kurz.luecken
        assert lang.status == ERFASST, lang.befunde
        assert lang.buendel.einmalzahlung == einmal


@pytest.mark.parametrize("im_rahmen", [True, False], ids=["rahmen", "gegenprobe"])
def test_kachel_mit_zwei_labels_ist_befund(chromium, im_rahmen):
    from telco_radar.collect.geraete.klicklauf import BEFUND, ERFASST

    folgeseite = _im_rahmen if im_rahmen else _mit_hinweis
    kurz = _laufe(chromium, _antworter(folgeseite))[("128", "S", 24)]

    if im_rahmen:
        assert kurz.status == BEFUND
        assert [(b.feld, b.grund) for b in kurz.befunde] == [
            ("kachel.laufzeit", "Kachel nennt 2 Optionen für laufzeit: 24, 24+12")
        ]
        assert (kurz.buendel.buendelbetrag, kurz.echo_quelle) == (None, None)
    else:
        assert kurz.status == ERFASST, kurz.befunde


def _betraege(daten: object) -> list[float]:
    if isinstance(daten, dict):
        return [x for v in daten.values() for x in _betraege(v)]
    if isinstance(daten, list):
        return [x for v in daten for x in _betraege(v)]
    return [daten] if isinstance(daten, float) else []


def test_diagnose_speichert_orte_und_merkmale_ohne_betraege(chromium):
    from telco_radar.collect.geraete.klickergebnis import kombination_als_daten

    ergebnisse = _laufe(chromium, weiter._antworter())

    for ergebnis in ergebnisse.values():
        daten = kombination_als_daten(ergebnis)
        assert _betraege(daten["diagnose"]) == []
        assert _betraege(daten["buendel"]), "Gegenprobe: der Bündelwert ist ein Betrag"
        assert daten["diagnose"]["kachel_betrag"] is True


def test_fundstellen_der_folgeseite_ohne_warenkorb_kennung_und_token(chromium):
    from telco_radar.collect.geraete.klickergebnis import kombination_als_daten

    ergebnisse = _laufe(chromium, weiter._antworter(zusatz=GLOBALE))
    funde = kombination_als_daten(ergebnisse[("128", "S", 24)])["diagnose"][
        "fundstellen"
    ]

    assert "window.shop.cart.*.items[0].price" in funde
    assert 'window.shop.sitzung["*"].preis' in funde
    assert [f for f in funde if KORB in f or JWT.split(".")[0] in f] == []
