"""Weiter-Schritt mit Klicks auf der Folgeseite (``weiter.klicken``, Schnitt 8b Teil 1).

BEISPIEL-Seiten nach der Vodafone-Erkundung vom 10.10.2026 (Zweig klick-erkundung
d969c6e1, klicks-3.json und mitschnitt-3.json): Die Produktseite wählt den Speicher,
„Zur Tarifauswahl“ führt per GET auf die Folgeseite. Dort lädt eine Antwort alle Tarife
auf einmal; ein Klick auf einen Tarif fragt nichts nach, er ändert nur Markierung und
Preiszusammenfassung (und schickt ein Tracking-POST, das nie hinausgehen darf).
Erwartet: je Speicher und Tarif eine erfasste Kombination mit den Werten des Tarifs aus
der Antwort der Folgeseite und dem Speicher als Seitenwert der Startseite. Gegenproben:
folgt die Zusammenfassung dem Klick nicht, oder markiert die Seite den Tarif nicht,
ist die Kombination ein Befund. Keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest
from klickbeispiel import frage, karte, laufe_mit, nach_auswahl, preis, seite
from klickserver import Antwort, html

pytestmark = pytest.mark.browser

START = """
<div id="speicher">
  <button type="button" aria-pressed="true" data-wert="128">128 GB</button>
  <button type="button" aria-pressed="false" data-wert="256">256 GB</button>
</div>
<div id="weiter"><a href="/tarife?speicher=128">Zur Tarifauswahl</a></div>"""
START_SKRIPT = """
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    for (const a of document.querySelectorAll("#speicher button")) {
      a.setAttribute("aria-pressed", String(a === k));
    }
    document.querySelector("#weiter a").href = "/tarife?speicher=" + k.dataset.wert;
  });
}"""
FOLGE = """
<div id="tarif">
  <button type="button" aria-pressed="true" data-wert="S">Mobil S</button>
  <button type="button" aria-pressed="false" data-wert="M">Mobil M</button>
</div>
<div id="preis"></div>"""
FOLGE_SKRIPT = """
const speicher = new URLSearchParams(location.search).get("speicher");
fetch("/api/tarife?speicher=" + speicher).then((a) => a.json()).then((d) => {
  window.tarife = d;
  zeige({preis: d.tarife.S});
});
for (const k of document.querySelectorAll("#tarif button")) {
  k.addEventListener("click", () => {
    if (@MARKIERT@) {
      for (const a of document.querySelectorAll("#tarif button")) {
        a.setAttribute("aria-pressed", String(a === k));
      }
    }
    if (@FOLGT@) zeige({preis: window.tarife.tarife[k.dataset.wert]});
    fetch("/zaehlung", {method: "POST", body: k.dataset.wert});
  });
}"""
PFADE = {
    "anzahlung": "tarife.{tarif}.anzahlung",
    "rate": "tarife.{tarif}.rate",
    "ratenzahl": "tarife.{tarif}.raten",
    "tarifphasen": "tarife.{tarif}.tarif",
    "tarifbindung": "tarife.{tarif}.bindung",
    "anschluss": "tarife.{tarif}.anschluss",
    "volumen_gb": "tarife.{tarif}.volumen",
}
KARTE = {
    "knoepfe": {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"selektor": "#tarif button", "wert": "data-wert"},
        "laufzeit": {"fest": 36},
        "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
    },
    "weiter": {"selektor": "#weiter a", "text": "Zur Tarifauswahl", "klicken": "tarif"},
    "seite": {
        "speicher": {
            "selektor": '#speicher [aria-pressed="true"]',
            "attribut": "data-wert",
        }
    },
    "antwort": {
        "url_muster": r"/api/tarife\?",
        "laden": True,
        "pfade": PFADE,
        "variante": {"speicher": "speicher"},
    },
}


def _antworter(folgt: bool = True, markiert: bool = True):
    start = seite(START, START_SKRIPT)
    skript = FOLGE_SKRIPT.replace("@FOLGT@", json.dumps(folgt)).replace(
        "@MARKIERT@", json.dumps(markiert)
    )
    folge = seite(FOLGE, skript)

    def antworte(pfad: str) -> Antwort:
        ort = urlsplit(pfad).path
        if ort == "/handy/x":
            return html(start)
        if ort == "/tarife":
            return html(folge)
        if ort == "/api/tarife":
            speicher = frage(pfad)["speicher"]
            tarife = {t: preis(speicher, t, 36) for t in ("S", "M")}
            daten = {"speicher": speicher, "tarife": tarife}
            return Antwort(200, "application/json", json.dumps(daten))
        return Antwort(204)

    return antworte


def _laufe(chromium, **schalter):
    return laufe_mit(chromium, _antworter(**schalter), karte(**KARTE))


def test_je_speicher_jeder_tarif_der_folgeseite_geklickt_und_erfasst(chromium):
    from telco_radar.collect.geraete.klicklauf import ERFASST
    from telco_radar.collect.geraete.klicktor import GRUND_NUR_LESEN

    lauf, server = _laufe(chromium)
    ergebnisse = nach_auswahl(lauf)

    assert lauf.status == "gelesen", lauf.grund
    assert set(ergebnisse) == {(s, t, 36) for s in ("128", "256") for t in ("S", "M")}
    for (speicher, tarif, _), ergebnis in ergebnisse.items():
        erwartet = preis(speicher, tarif, 36)
        assert ergebnis.status == ERFASST, (speicher, tarif, ergebnis.befunde)
        assert ergebnis.auswahl == (speicher, tarif, "36")
        assert ergebnis.werte.rate == erwartet["rate"]
        assert ergebnis.werte.volumen_gb == erwartet["volumen"]
        assert ergebnis.werte.tarifphasen[0].betrag == erwartet["tarif"]
        assert ergebnis.antwort_url.endswith(f"/api/tarife?speicher={speicher}")
    assert server.posts == []
    assert {v.grund for v in lauf.verworfen} == {GRUND_NUR_LESEN}


def test_gegenprobe_zusammenfassung_folgt_dem_klick_nicht(chromium):
    from telco_radar.collect.geraete.klicklauf import BEFUND, ERFASST

    lauf, _ = _laufe(chromium, folgt=False)
    ergebnisse = nach_auswahl(lauf)

    for speicher in ("128", "256"):
        assert ergebnisse[(speicher, "S", 36)].status == ERFASST
        assert ergebnisse[(speicher, "M", 36)].status == BEFUND


def test_gegenprobe_seite_markiert_den_geklickten_tarif_nicht(chromium):
    from telco_radar.collect.geraete.klicklauf import BEFUND

    lauf, _ = _laufe(chromium, markiert=False)
    ergebnisse = nach_auswahl(lauf)

    for speicher in ("128", "256"):
        ergebnis = ergebnisse[(speicher, "M", 36)]
        assert ergebnis.status == BEFUND
        assert "Seite zeigt S statt M" in ergebnis.grund
