"""Variante über eine eigene Adresse: Links der Seite, robots.txt, fremder Host.

BEISPIEL-Seiten nach der Erkundung vom 07.10.2026: Telekom führt den Tarif über die
Seitenadresse (``tariffId``), freenet jedes Bündel auf einer eigenen Seite. Die
Startseite zeigt Links je Tarif; der Crawler lädt jede Adresse, die die Seite zeigt,
und klickt dort den Speicher. Ein Link ist per robots.txt gesperrt, einer zeigt auf
einen anderen Host (``localhost`` statt ``127.0.0.1``), einem fehlt der Parameter,
einer nennt einen Tarif doppelt. Werte stehen als JSON im Skript der Seite. Keine
Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from klickbeispiel import karte, nach_auswahl, preis, seite
from klickserver import Antwort, html, klickserver, laufe

pytestmark = pytest.mark.browser

ROBOTS = "User-agent: *\nDisallow: /gesperrt/\n"
KOERPER = """
<nav id="tarife">
  <a class="tarif" href="/handy/x?tariffId=S&amp;color=blau">Tarif S</a>
  <a class="tarif" href="/handy/x?tariffId=M&amp;color=blau">Tarif M</a>
  <a class="tarif" href="/gesperrt/x?tariffId=L">Tarif L</a>
  <a class="tarif" id="fremd" href="/handy/x">Tarif XL</a>
  <a class="tarif" href="/handy/x?color=blau">Alle Tarife</a>
  <a class="tarif" href="/handy/x?tariffId=S&amp;color=rot">Tarif S in Rot</a>
</nav>
<div id="speicher">
  <button type="button" aria-pressed="true" data-wert="128">128 GB</button>
  <button type="button" aria-pressed="false" data-wert="256">256 GB</button>
</div>
<p id="tarifname">@TARIF@</p>
<section id="preis"></section>
<script type="application/json" id="zustand">@ZUSTAND@</script>"""
SKRIPT = """
document.getElementById("fremd").href =
  "http://localhost:" + location.port + "/handy/x?tariffId=XL";
const daten = JSON.parse(document.getElementById("zustand").textContent);
function waehle(knopf) {
  for (const k of document.querySelectorAll("#speicher button")) {
    k.setAttribute("aria-pressed", String(k === knopf));
  }
  if (daten.preise) zeige({preis: daten.preise[knopf.dataset.wert]});
}
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => waehle(k));
}
waehle(document.querySelector("#speicher button"));"""
ZEILE = "preise.{speicher}"
KARTE = {
    "knoepfe": {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"adressen": {"selektor": "a.tarif", "parameter": "tariffId"}},
        "laufzeit": {"fest": 36},
        "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
    },
    "seite": {"tarif": {"selektor": "#tarifname"}},
    "antwort": {
        "skript": "#zustand",
        "pfade": {
            "anzahlung": f"{ZEILE}.anzahlung",
            "rate": f"{ZEILE}.rate",
            "ratenzahl": f"{ZEILE}.raten",
            "tarifphasen": f"{ZEILE}.tarif",
            "tarifbindung": f"{ZEILE}.bindung",
            "anschluss": f"{ZEILE}.anschluss",
            "volumen_gb": f"{ZEILE}.volumen",
        },
        "variante": {"tarif": "tarif"},
    },
}


def _seite(tarif: str | None) -> str:
    zustand = {"tarif": tarif}
    if tarif is not None:
        zustand["preise"] = {s: preis(s, tarif, 36) for s in ("128", "256")}
    koerper = KOERPER.replace("@TARIF@", tarif or "keiner")
    return seite(koerper.replace("@ZUSTAND@", json.dumps(zustand)), SKRIPT)


def _laufe(chromium, stehend: bool = False):
    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path != "/handy/x":
            return Antwort(404)
        tarif = parse_qs(teile.query).get("tariffId", [None])[0]
        return html(_seite("S" if stehend and tarif is not None else tarif))

    with klickserver(antworte) as server:
        lauf = laufe(chromium, server.adresse("/handy/x"), karte(**KARTE), ROBOTS)
    return lauf, server


def test_jede_adresse_der_seite_ist_eine_option(chromium):
    lauf, server = _laufe(chromium)

    assert lauf.status == "gelesen", lauf.grund
    ergebnisse = nach_auswahl(lauf)
    gelesen = {k for k, e in ergebnisse.items() if e.status == "erfasst"}
    assert gelesen == {(s, t, 36) for s in ("128", "256") for t in ("S", "M")}, [
        e.grund for e in lauf.ergebnisse
    ]
    assert ergebnisse[("256", "M", 36)].werte.rate == 35.0
    assert server.abrufe == [
        "/handy/x",
        "/handy/x?tariffId=S&color=blau",
        "/handy/x?tariffId=M&color=blau",
    ]
    offen = [(e.variante.tarif, e.grund) for e in lauf.ergebnisse]
    gesperrt = [g for t, g in offen if t == "L"]
    assert len(gesperrt) == 1
    assert "robots" in gesperrt[0]
    assert [v.url for v in lauf.verworfen] == [server.adresse("/gesperrt/x?tariffId=L")]
    ohne = sorted(g.split(" (")[0] for t, g in offen if t is None)
    assert ohne == ["Adresse auf anderem Host", "Adresse ohne Parameter tariffId"]
    assert {e.status for e in lauf.ergebnisse if e.variante.speicher is None} == {
        "nicht_erfasst"
    }


def test_seite_die_den_tarif_nicht_wechselt_ist_ein_befund(chromium):
    lauf, _ = _laufe(chromium, stehend=True)

    falsch = nach_auswahl(lauf)[("128", "M", 36)]
    assert falsch.status == "befund"
    assert "Seite zeigt S statt M" in [b.grund for b in falsch.befunde]
    assert nach_auswahl(lauf)[("128", "S", 36)].status == "erfasst"


def test_ohne_passende_links_ist_der_tarif_nicht_erfasst(chromium):
    knoepfe = dict(KARTE["knoepfe"])
    knoepfe["tarif"] = {"adressen": {"selektor": "a.gibt-es-nicht", "parameter": "t"}}

    def antworte(pfad: str) -> Antwort:
        return html(_seite(None)) if pfad == "/handy/x" else Antwort(404)

    with klickserver(antworte) as server:
        k = karte(**{**KARTE, "knoepfe": knoepfe})
        lauf = laufe(chromium, server.adresse("/handy/x"), k, ROBOTS)

    assert [e.status for e in lauf.ergebnisse] == ["nicht_erfasst"]
    assert lauf.ergebnisse[0].grund == (
        "Adressen für tarif nicht gefunden (a.gibt-es-nicht)"
    )
    assert lauf.status == "gestoert"
    assert server.abrufe == ["/handy/x"]
