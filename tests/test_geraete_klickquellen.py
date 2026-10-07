"""Zweite Lesung im Lauf: Antworten beim Laden unter einer Adresse, Warenkorb-Link.

BEISPIEL-Seite nach der Erkundung vom 07.10.2026: congstar und Vodafone laden die
Preise einmal unter derselben Adresse (drei Antworten, nur am Inhalt zu unterscheiden,
eine davon doppelt wie bei Vodafone xhr und fetch); kein Klick lädt etwas nach. Die
Variante zeigt ein Warenkorb-Link (congstar ``planId``, ``deviceVariantId``). Keine
Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import itertools
import json

import pytest
from klickbeispiel import (
    TARIF,
    VOLUMEN,
    karte,
    laufe_mit,
    nach_auswahl,
    preis,
    seite,
)
from klickserver import Antwort, html

pytestmark = pytest.mark.browser

KNOEPFE = {
    "speicher": {"selektor": "#speicher button"},
    "tarif": {"selektor": "#tarif button", "wert": "data-wert"},
    "laufzeit": {"selektor": "#laufzeit button", "muster": r"^(\d+)"},
    "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
}
LADEN_KOERPER = """
<div id="speicher">
  <button type="button" aria-pressed="true">128 GB</button>
  <button type="button" aria-pressed="false">256 GB</button>
</div>
<div id="tarif">
  <button type="button" aria-pressed="true" data-wert="540">Allnet S</button>
  <button type="button" aria-pressed="false" data-wert="541">Allnet M</button>
</div>
<div id="laufzeit">
  <button type="button" aria-pressed="true">36 mtl. Zahlungen</button>
  <button type="button" aria-pressed="false">24 mtl. Zahlungen</button>
</div>
<a id="warenkorb" href="/warenkorb">Weiter zum Warenkorb</a>
<section id="preis"></section>"""
LADEN_SKRIPT = """
const LINK_FEST = @FEST@;
const auswahl = {speicher: "128 GB", tarif: "540", laufzeit: "36"};
const daten = {};
const link = document.getElementById("warenkorb");
function wert(g, k) {
  if (g === "tarif") return k.dataset.wert;
  return g === "laufzeit" ? k.innerText.split(" ")[0] : k.innerText;
}
function markiere() {
  for (const g of ["speicher", "tarif", "laufzeit"]) {
    for (const k of document.querySelectorAll("#" + g + " button")) {
      k.setAttribute("aria-pressed", String(wert(g, k) === auswahl[g]));
    }
  }
}
function rechne() {
  const geraet = daten.geraete.find((v) => v.speicher === auswahl.speicher).id;
  const plan = daten.plans.find((p) => p.id === auswahl.tarif);
  const zeile = daten.matrix.find(
    (m) => m.plan === auswahl.tarif && m.geraet === geraet);
  const zw = zeile.zahlweisen.find((z) => String(z.dauer) === auswahl.laufzeit);
  if (!LINK_FEST || !link.search) {
    link.href = "/warenkorb?planId=" + auswahl.tarif + "&deviceVariantId=" + geraet;
  }
  zeige({preis: {anzahlung: zw.einmal, rate: zw.rate, raten: zw.dauer,
    tarif: plan.preis, bindung: plan.bindung, anschluss: 0, volumen: plan.volumen}});
}
for (const g of ["speicher", "tarif", "laufzeit"]) {
  for (const k of document.querySelectorAll("#" + g + " button")) {
    k.addEventListener("click", () => {
      auswahl[g] = wert(g, k); markiere(); rechne();
    });
  }
}
(async () => {
  for (let i = 0; i < 4; i++) {
    const d = (await (await fetch("/graphql")).json()).data;
    if (d.plans) daten.plans = d.plans;
    if (d.device) daten.geraete = d.device.variants;
    if (d.matrix) daten.matrix = d.matrix;
  }
  rechne();
})();"""
PLAN = "data.plans[id={tarif}]"
ZEILE = "data.matrix[plan={tarif}][geraet={geraet}].zahlweisen[dauer={laufzeit}]"
LADEN_QUELLEN = [
    {
        "url_muster": "/graphql$",
        "laden": True,
        "erkennung": "data.matrix",
        "pfade": {
            "anzahlung": f"{ZEILE}.einmal",
            "rate": f"{ZEILE}.rate",
            "ratenzahl": f"{ZEILE}.dauer",
        },
        "variante": {"speicher": "data.matrix[geraet={geraet}].speicher"},
    },
    {
        "url_muster": "/graphql$",
        "laden": True,
        "erkennung": "data.plans",
        "pfade": {
            "tarifphasen": f"{PLAN}.preis",
            "tarifbindung": f"{PLAN}.bindung",
            "anschluss": f"{PLAN}.anschluss",
            "volumen_gb": f"{PLAN}.volumen",
        },
    },
]
WARENKORB = {"selektor": "#warenkorb", "attribut": "href"}
LADEN_SEITE = {
    "tarif": {**WARENKORB, "parameter": "planId"},
    "geraet": {**WARENKORB, "parameter": "deviceVariantId"},
}
PLAENE = {"540": "S", "541": "M"}
GERAETE = {"128": "9128", "256": "9256"}


def _graphql():
    plans = [
        {
            "id": i,
            "preis": TARIF[t],
            "bindung": 24,
            "anschluss": 0.0,
            "volumen": VOLUMEN[t],
        }
        for i, t in PLAENE.items()
    ]
    geraete = [{"id": g, "speicher": f"{s} GB"} for s, g in GERAETE.items()]
    matrix = [
        {
            "plan": i,
            "geraet": g,
            "speicher": f"{s} GB",
            "zahlweisen": [
                {"dauer": lz, "einmal": 1.0, "rate": preis(s, t, lz)["rate"]}
                for lz in (36, 24)
            ],
        }
        for i, t in PLAENE.items()
        for s, g in GERAETE.items()
    ]
    folge = [{"plans": plans}, {"device": {"variants": geraete}}, {"matrix": matrix}]
    return [json.dumps({"data": d}) for d in (*folge, folge[-1])]


def _laden_antworter(seite_html: str):
    folge = itertools.cycle(_graphql())

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(seite_html)
        if pfad == "/graphql":
            return Antwort(200, "application/json", next(folge))
        return Antwort(404)

    return antworte


def _laden(chromium, fest: bool = False, quellen=None):
    k = karte(
        knoepfe=KNOEPFE,
        seite=LADEN_SEITE,
        antwort=LADEN_QUELLEN if quellen is None else quellen,
    )
    skript = LADEN_SKRIPT.replace("@FEST@", "true" if fest else "false")
    lauf, server = laufe_mit(
        chromium, _laden_antworter(seite(LADEN_KOERPER, skript)), k
    )
    return nach_auswahl(lauf), lauf, server


def test_antworten_beim_laden_mit_filtern_und_warenkorb_link(chromium):
    ergebnisse, lauf, server = _laden(chromium)

    assert lauf.status == "gelesen", lauf.grund
    assert len(ergebnisse) == 8
    assert {e.status for e in ergebnisse.values()} == {"erfasst"}, [
        e.grund for e in ergebnisse.values()
    ]
    teuer = ergebnisse[("256 GB", "541", 24)].werte
    assert (teuer.rate, teuer.tarifphasen[0].betrag, teuer.volumen_gb) == (
        40.0,
        29.99,
        50,
    )
    assert len(server.mit("/graphql")) == 4
    beleg = ergebnisse[("128 GB", "540", 36)].beleg.beleg
    assert beleg.antwort_url.endswith("/handy/x#lesung")
    assert {s.json_pfad.split(":")[0] for s in beleg.fundstellen} == {
        "[0] /graphql$",
        "[1] /graphql$",
    }


def test_ohne_erkennung_liest_jede_quelle_die_letzte_antwort(chromium):
    quellen = [{k: v for k, v in q.items() if k != "erkennung"} for q in LADEN_QUELLEN]

    ergebnisse, _, _ = _laden(chromium, quellen=quellen)

    assert {e.status for e in ergebnisse.values()} == {"befund"}
    felder = {b.feld for e in ergebnisse.values() for b in e.befunde}
    assert {"tarifphasen", "volumen_gb"} <= felder


def test_stehender_warenkorb_link_ist_ein_befund(chromium):
    ergebnisse, _, _ = _laden(chromium, fest=True)

    assert ergebnisse[("128 GB", "540", 36)].status == "erfasst"
    falsch = ergebnisse[("128 GB", "541", 36)]
    assert falsch.status == "befund"
    assert "Seite zeigt 540 statt 541" in [b.grund for b in falsch.befunde]
