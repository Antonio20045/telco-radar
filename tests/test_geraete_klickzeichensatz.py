"""Eine Seite in ISO-8859-1 ist kein Absturz: der Klick-Crawler liest sie zu Ende.

Erkundung 07.10.2026: Die Vodafone-Produktseite enthielt das Byte 0xE4 („ä“ in
ISO-8859-1). Playwrights ``text()`` liest nur UTF-8; der Fehler im Tor riss den Lauf
samt Ablage mit, und Vodafone fehlte in der Erkundung. Ein lokaler Server auf
127.0.0.1 liefert BEISPIEL-Seiten, von Hand geschrieben.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from klickserver import Antwort, karte, klickserver, laufe

from telco_radar.collect.geraete.klicklauf import antworttext

OFFEN = "User-agent: *\nDisallow:\n"
FRIST_MS = 3000
LATIN = "text/html; charset=iso-8859-1"
SEITE = """<!doctype html><html><body>
<h1 id="kanarie">Beispielhandy X</h1><p>Gerät für Händler, Grüße</p>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif">
 <button data-wert="S" aria-pressed="true">Tarif S</button>
 <button data-wert="M" aria-pressed="false">Tarif M</button>
</div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="preis"></section>
<script>
function lade(tarif) {
  fetch(`/api/preis?tarif=${tarif}`).then(r => r.json()).then(d => {
    document.getElementById("preis").innerText = `Monatliche Rate ${d.rate},00 \\u20ac`;
  });
}
for (const k of document.querySelectorAll("#tarif button")) {
  k.addEventListener("click", () => {
    for (const j of document.querySelectorAll("#tarif button")) {
      j.setAttribute("aria-pressed", String(j === k));
    }
    lade(k.dataset.wert);
  });
}
lade("S");
</script></body></html>"""
RADWARE = "<html><head><title>Radware Bot Manager Captcha</title></head><body>Händler"
RATE = {"S": 20, "M": 30}
ANTWORT = {
    "url_muster": r"/api/preis\?",
    "pfade": {"rate": "rate"},
    "parameter": {"tarif": "tarif"},
}


def _antworte(seite: Antwort):
    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return seite
        if urlsplit(pfad).path == "/api/preis":
            tarif = parse_qs(urlsplit(pfad).query)["tarif"][0]
            return Antwort(200, "application/json", json.dumps({"rate": RATE[tarif]}))
        return Antwort(200, "text/javascript", "")

    return antworte


def test_seite_in_iso_8859_1_wird_zu_ende_gelesen(chromium):
    seite = Antwort(200, LATIN, SEITE, kodierung="iso-8859-1")
    with klickserver(_antworte(seite)) as server:
        lauf = laufe(
            chromium,
            server.adresse("/handy/x"),
            karte(ANTWORT),
            OFFEN,
            frist_ms=FRIST_MS,
        )

    assert lauf.status == "gelesen", lauf.grund
    erfasst = {e.variante.tarif: e.werte.rate for e in lauf.ergebnisse}
    assert erfasst == {"S": 20.0, "M": 30.0}


def test_gegenprobe_challenge_in_iso_8859_1_bleibt_gestoert(chromium):
    seite = Antwort(200, LATIN, RADWARE, kodierung="iso-8859-1")
    with klickserver(_antworte(seite)) as server:
        lauf = laufe(
            chromium,
            server.adresse("/handy/x"),
            karte(ANTWORT),
            OFFEN,
            frist_ms=FRIST_MS,
        )

    assert server.abrufe == ["/handy/x"]
    assert lauf.status == "gestoert"
    assert "Challenge" in lauf.grund


@pytest.mark.parametrize(
    ("koerper", "typ", "text"),
    [
        ("Händler".encode("iso-8859-1"), LATIN, "Händler"),
        ("Händler".encode(), "text/html; charset=utf-8", "Händler"),
        ("Händler".encode("iso-8859-1"), "text/html", "H�ndler"),
        ("Händler".encode(), "text/html; charset=gibtesnicht", "Händler"),
    ],
    ids=["latin1", "utf8", "ohne_angabe", "unbekannt"],
)
def test_antworttext_nach_zeichensatz_der_kopfzeile(koerper, typ, text):
    assert antworttext(koerper, typ) == text
