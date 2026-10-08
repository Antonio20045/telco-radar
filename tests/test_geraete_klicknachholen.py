"""Nachholen (``klicknachholen``): Kombinationen ohne Antwort am Ende neu besuchen.

Muster aus dem Tageslauf vom 08.10.2026 (Actions-Lauf 37740022815, Telekom iPhone 17
Pro, ``data/state/klick/telekom.json``): ``/v2/details`` kam erst nach einem
Speicherklick; der vorgewählte Speicher und jeder Laufzeitklick luden nichts, darum
drei Befunde „keine Antwort mitgeschnitten“. Die BEISPIEL-Seite bildet das nach: die
Seite zeigt den vorgewählten Speicher aus eingebetteten Daten und holt ``/api/preis``
nur beim Speicherklick. Keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from klickbeispiel import (
    TARIF,
    VOLUMEN,
    antworter,
    karte,
    laufe_mit,
    nach_auswahl,
    preis,
    seite,
)

from telco_radar.collect.geraete.klickecho import Variante
from telco_radar.collect.geraete.klicklauf import (
    BEFUND,
    ERFASST,
    NICHT_ERFASST,
    Klicklauf,
    Kombiergebnis,
)
from telco_radar.collect.geraete.klicknachholen import OHNE_ANTWORT, Nachholen

PLAN = "plaene[raten={laufzeit}]"
KNOEPFE = {
    "speicher": {"selektor": "#speicher button"},
    "tarif": {"fest": "M"},
    "laufzeit": {"selektor": "#laufzeit button", "muster": r"^(\d+)"},
    "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
}
ANTWORT = {
    "url_muster": r"/api/preis\?",
    "laden": True,
    "pfade": {
        "anzahlung": f"{PLAN}.anzahlung",
        "rate": f"{PLAN}.rate",
        "ratenzahl": f"{PLAN}.raten",
        "tarifphasen": "tarif",
        "tarifbindung": "bindung",
        "anschluss": "anschluss",
        "volumen_gb": "volumen",
    },
    "variante": {"speicher": "speicher"},
}
KOERPER = """
<div id="speicher">
  <button type="button" aria-pressed="true">128 GB</button>
  <button type="button" aria-pressed="false">256 GB</button>
</div>
<div id="laufzeit">
  <button type="button" aria-pressed="true">36 Monate</button>
  <button type="button" aria-pressed="false">24 Monate</button>
</div>
<section id="preis"></section>"""
SKRIPT = """
const NIE = @NIE@;
let daten = @VORGEWAEHLT@;
const auswahl = {speicher: "128 GB", laufzeit: "36"};
function wert(g, k) {
  return g === "laufzeit" ? k.innerText.split(" ")[0] : k.innerText;
}
function markiere() {
  for (const g of ["speicher", "laufzeit"]) {
    for (const k of document.querySelectorAll("#" + g + " button")) {
      k.setAttribute("aria-pressed", String(wert(g, k) === auswahl[g]));
    }
  }
}
function rechne() {
  const z = daten.plaene.find((p) => String(p.raten) === auswahl.laufzeit);
  zeige({preis: {anzahlung: z.anzahlung, rate: z.rate, raten: z.raten,
    tarif: daten.tarif, bindung: daten.bindung, anschluss: daten.anschluss,
    volumen: daten.volumen}});
}
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    auswahl.speicher = wert("speicher", k); markiere();
    if (auswahl.speicher === NIE) return;
    fetch("/api/preis?" + new URLSearchParams({speicher: auswahl.speicher}))
      .then((a) => a.json()).then((d) => { daten = d; rechne(); });
  });
}
for (const k of document.querySelectorAll("#laufzeit button")) {
  k.addEventListener("click", () => {
    auswahl.laufzeit = wert("laufzeit", k); markiere(); rechne();
  });
}
rechne();"""


def _details(speicher: str) -> dict:
    groesse = speicher.split()[0]
    plaene = []
    for laufzeit in (36, 24):
        p = preis(groesse, "M", laufzeit)
        plaene.append(
            {"raten": laufzeit, "anzahlung": p["anzahlung"], "rate": p["rate"]}
        )
    return {
        "speicher": speicher,
        "plaene": plaene,
        "tarif": TARIF["M"],
        "bindung": 24,
        "anschluss": 0.0,
        "volumen": VOLUMEN["M"],
    }


def _laufe(chromium, nie: str | None = None):
    skript = SKRIPT.replace("@NIE@", json.dumps(nie)).replace(
        "@VORGEWAEHLT@", json.dumps(_details("128 GB"))
    )
    html = seite(KOERPER, skript)
    k = karte(knoepfe=KNOEPFE, antwort=ANTWORT)
    lauf, server = laufe_mit(
        chromium, antworter(html, lambda f: _details(f["speicher"])), k
    )
    return lauf, server


@pytest.mark.browser
def test_vorgewaehlter_speicher_wird_am_ende_nachgeholt(chromium):
    lauf, server = _laufe(chromium)

    assert lauf.status == "gelesen", lauf.grund
    assert [(e.variante.speicher, e.variante.laufzeit) for e in lauf.ergebnisse] == [
        ("128 GB", 36),
        ("128 GB", 24),
        ("256 GB", 36),
        ("256 GB", 24),
    ]
    assert {e.status for e in lauf.ergebnisse} == {ERFASST}, [
        e.grund for e in lauf.ergebnisse
    ]
    ergebnisse = nach_auswahl(lauf)
    assert ergebnisse[("128 GB", "M", 24)].werte.rate == 35.0
    assert ergebnisse[("256 GB", "M", 36)].werte.rate == 35.0
    assert ergebnisse[("128 GB", "M", 36)].werte.rate == 30.0
    assert server.mit("/api/preis") == [
        "/api/preis?speicher=256+GB",
        "/api/preis?speicher=128+GB",
    ]


@pytest.mark.browser
def test_ohne_antwort_bleibt_es_ein_befund_ohne_werte(chromium):
    lauf, server = _laufe(chromium, nie="128 GB")

    assert lauf.status == "gelesen", lauf.grund
    assert len(lauf.ergebnisse) == 4
    ergebnisse = nach_auswahl(lauf)
    for laufzeit in (36, 24):
        offen = ergebnisse[("128 GB", "M", laufzeit)]
        assert offen.status == BEFUND
        assert offen.werte.rate is None
    assert ergebnisse[("256 GB", "M", 36)].status == ERFASST
    assert server.mit("/api/preis") == ["/api/preis?speicher=256+GB"]


@dataclass
class _Gang:
    lauf: Klicklauf = field(default_factory=lambda: Klicklauf("B", "/handy/x"))
    nach_frist: int = 0
    um: bool = False

    def zeit_um(self) -> bool:
        return self.um


def _ergebnis(auswahl, status=BEFUND, befunde=(OHNE_ANTWORT,), grund=None):
    variante = Variante("128 GB", "M", int(auswahl[2]))
    return Kombiergebnis(
        variante, status, grund, befunde=befunde, auswahl=tuple(auswahl)
    )


def test_nachholen_ersetzt_nur_gelesenes_und_zaehlt_keine_frist():
    gang = _Gang()
    nachholen = Nachholen(gang)
    erste, zweite = ("128 GB", "M", "36"), ("128 GB", "M", "24")
    nachholen.lege_ab(_ergebnis(erste))
    nachholen.lege_ab(_ergebnis(zweite))
    nachholen.lege_ab(_ergebnis(("256 GB", "M", "36"), ERFASST, ()))
    assert nachholen.naechste() == erste
    nachholen.lege_ab(_ergebnis(erste, ERFASST, ()))
    assert nachholen.naechste() == zweite
    gang.nach_frist = 1
    nachholen.lege_ab(_ergebnis(zweite, NICHT_ERFASST, (), "nicht besucht"))
    assert nachholen.naechste() is None

    assert [e.status for e in gang.lauf.ergebnisse] == [ERFASST, BEFUND, ERFASST]
    assert gang.nach_frist == 0


def test_nach_der_frist_wird_nichts_nachgeholt():
    gang = _Gang(um=True)
    nachholen = Nachholen(gang)
    nachholen.lege_ab(_ergebnis(("128 GB", "M", "36")))
    assert nachholen.naechste() is None
    assert [e.status for e in gang.lauf.ergebnisse] == [BEFUND]
