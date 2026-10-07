"""HTTP 202 auf eine Unteranfrage der eigenen Website beendet den Lauf als gestört.

Erkundung Telekom vom 07.10.2026, Seite 2: ``/opt-in/cookie.php`` (xhr) und eine
statische Skriptdatei kamen mit HTTP 202 und einer Sperrseite, während das Dokument
HTTP 200 trug. CLAUDE.md Regel 4: keine Umgehung, der Lauf endet gestört, danach geht
keine Anfrage mehr hinaus. Ein 202 von einem anderen Host (``localhost`` statt
``127.0.0.1``) stört nicht. BEISPIEL-Seite, von Hand geschrieben; keine Anfrage
verlässt den Rechner.
"""

from __future__ import annotations

import pytest
from klickbeispiel import KARTE, antworter, karte, laufe_mit, preis, seite
from klickserver import Antwort, html

pytestmark = pytest.mark.browser

KOERPER = """
<div id="speicher">
  <button type="button" aria-pressed="true" data-wert="128">128 GB</button>
  <button type="button" aria-pressed="false" data-wert="256">256 GB</button>
</div>
<section id="preis"></section>"""
SKRIPT = """
const auswahl = {speicher: "128", tarif: "S", laufzeit: "36"};
const ZIEL = @ZIEL@;
function hole() {
  if (ZIEL.art === "script") {
    const s = document.createElement("script");
    s.src = ZIEL.host + "/legalnote/p-5962.js";
    document.head.appendChild(s);
  } else {
    fetch(ZIEL.host + "/opt-in/cookie.php").catch(() => {});
  }
}
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    for (const a of document.querySelectorAll("#speicher button")) {
      a.setAttribute("aria-pressed", String(a === k));
    }
    auswahl.speicher = k.dataset.wert;
    hole();
    lade(auswahl);
  });
}
lade(auswahl);"""
KNOEPFE = {
    "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
    "tarif": {"fest": "S"},
    "laufzeit": {"fest": 36},
    "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
}
ANTWORT = {**KARTE["antwort"], "variante": {"speicher": "auswahl.speicher"}}
SPERRSEITE = "<!doctype html><html><body>Bitte warten</body></html>"
SPERRPFADE = ("/legalnote/p-5962.js", "/opt-in/cookie.php")


def _laufe(chromium, art: str, host: str):
    ziel = '{art: "' + art + '", host: ' + host + "}"
    seite_html = seite(KOERPER, SKRIPT.replace("@ZIEL@", ziel))
    basis = antworter(seite_html, _rechne)

    def antworte(pfad: str) -> Antwort:
        return html(SPERRSEITE, 202) if pfad in SPERRPFADE else basis(pfad)

    k = karte(knoepfe=KNOEPFE, antwort=ANTWORT)
    return laufe_mit(chromium, antworte, k)


def _rechne(frage: dict[str, str]) -> dict:
    speicher = frage["speicher"]
    return {"preis": preis(speicher, "S", 36), "auswahl": {"speicher": speicher}}


@pytest.mark.parametrize("art", ["fetch", "script"])
def test_202_der_eigenen_website_beendet_den_lauf(chromium, art):
    lauf, server = _laufe(chromium, art, '""')

    assert lauf.status == "gestoert"
    assert "HTTP 202" in lauf.grund
    assert [(e.variante.speicher, e.status) for e in lauf.ergebnisse] == [
        ("128", "erfasst")
    ]
    assert len([p for p in server.abrufe if p in SPERRPFADE]) == 1
    assert server.mit("/handy/") == ["/handy/x"]


def test_202_eines_anderen_hosts_stoert_nicht(chromium):
    lauf, server = _laufe(chromium, "script", '"http://localhost:" + location.port')

    assert lauf.status == "gelesen", lauf.grund
    assert {e.status for e in lauf.ergebnisse} == {"erfasst"}, [
        e.grund for e in lauf.ergebnisse
    ]
    assert server.mit("/legalnote/") == ["/legalnote/p-5962.js"]
