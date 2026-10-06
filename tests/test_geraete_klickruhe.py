"""Ruhe und Fristen des Klick-Crawlers: gesperrte Knöpfe und offene Preisanfragen.

Eine gesperrte Option heißt nur ``nicht_angeboten``, wenn die Seite ruht: keine
Anfrage der Seite läuft, auch keine außerhalb des Antwortmusters, und zwei Lesungen
sind gleich. Eine Preisantwort, die über die Frist offen bleibt, macht die Kombination
``nicht_erfasst``, an jeder Stelle des Laufs gleich, und bleibt sie auch danach offen,
ist der Lauf gestört. Fälle aus der dritten Prüfrunde zu Schritt 4: eine Ladesperre
über eine zweite, langsame Anfrage (Bestand) und eine hängende letzte Preisantwort,
je mit schneller Gegenprobe. Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten,
von Hand geschrieben.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from klickserver import Antwort, html, karte, klickserver, laufe

OFFEN = "User-agent: *\nDisallow:\n"
GESPERRTE_KNOEPFE = """<!doctype html><html><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif">
 <button data-wert="S" aria-pressed="true">Tarif S</button>
 <button data-wert="M" aria-pressed="false">Tarif M</button>
</div>
<div id="laufzeit">
 <button data-wert="24" aria-pressed="true">24 Monate</button>
 <button data-wert="36" aria-pressed="false">36 Monate</button>
</div>
<section id="preis"></section>
<script>
const MUSTER = "MUSTERNAME";
const auswahl = {tarif: "S", laufzeit: "24"};
function markiere() {
  const paare = [["#tarif", auswahl.tarif], ["#laufzeit", auswahl.laufzeit]];
  for (const [ort, wert] of paare) {
    for (const k of document.querySelectorAll(ort + " button")) {
      k.setAttribute("aria-pressed", String(k.dataset.wert === wert));
      if (MUSTER === "aktiv_gesperrt") {
        k.setAttribute("aria-disabled", String(k.dataset.wert === wert));
      }
      if (MUSTER === "wirklich_gesperrt") {
        k.disabled = auswahl.tarif === "S" && k.dataset.wert === "36";
      }
    }
  }
}
function sperre(an) {
  if (MUSTER !== "ladesperre" && MUSTER !== "bestand") return;
  for (const k of document.querySelectorAll("#tarif button, #laufzeit button")) {
    k.disabled = an;
  }
}
async function lade() {
  markiere();
  sperre(true);
  const frage = `tarif=${auswahl.tarif}&laufzeit=${auswahl.laufzeit}`;
  const d = await (await fetch(`/api/preis?${frage}`)).json();
  document.getElementById("preis").innerText =
    `Monatliche Rate ${d.rate},00 € · ${auswahl.laufzeit} Raten`;
  if (MUSTER === "bestand") await fetch("/api/bestand");
  setTimeout(() => sperre(false), 200);
}
for (const k of document.querySelectorAll("#tarif button")) {
  k.addEventListener("click", () => {
    auswahl.tarif = k.dataset.wert;
    const sperrt = MUSTER === "wirklich_gesperrt" && auswahl.tarif === "S";
    if (sperrt) auswahl.laufzeit = "24";
    lade();
  });
}
for (const k of document.querySelectorAll("#laufzeit button")) {
  k.addEventListener("click", () => { auswahl.laufzeit = k.dataset.wert; lade(); });
}
lade();
</script></body></html>"""
RATE_JE_KOMBINATION = {
    ("S", "24"): 30,
    ("S", "36"): 25,
    ("M", "24"): 35,
    ("M", "36"): 28,
}
DREI_TARIFE = """<!doctype html><html><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif">
 <button data-wert="S" aria-pressed="true">Tarif S</button>
 <button data-wert="M" aria-pressed="false">Tarif M</button>
 <button data-wert="L" aria-pressed="false">Tarif L</button>
</div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="preis"></section>
<script>
function lade(tarif) {
  fetch(`/api/preis?tarif=${tarif}`).then(r => r.json()).then(d => {
    document.getElementById("preis").innerText = `Monatliche Rate ${d.rate},00 €`;
  }).catch(() => {});
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
RATE_JE_TARIF = {"S": 20, "M": 30, "L": 40}
HAENGT_S = 4.0
KURZE_FRIST_MS = 1000


@pytest.mark.parametrize(
    ("muster", "bestand_s", "erwartet"),
    [
        ("aktiv_gesperrt", 0.0, "erfasst"),
        ("ladesperre", 0.0, "erfasst"),
        ("bestand", 2.0, "erfasst"),
        ("bestand", 0.0, "erfasst"),
        ("wirklich_gesperrt", 0.0, "nicht_angeboten"),
    ],
)
def test_gesperrter_knopf_ist_nur_nach_ruhe_nicht_angeboten(
    chromium, muster, bestand_s, erwartet
):
    seite = GESPERRTE_KNOEPFE.replace("MUSTERNAME", muster)

    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path == "/handy/x":
            return html(seite)
        if teile.path == "/api/bestand":
            return Antwort(200, "application/json", "{}", verzug=bestand_s)
        frage = parse_qs(teile.query)
        tarif, laufzeit = frage["tarif"][0], frage["laufzeit"][0]
        rate = RATE_JE_KOMBINATION[tarif, laufzeit]
        koerper = json.dumps({"rate": rate, "raten": int(laufzeit)})
        return Antwort(200, "application/json", koerper)

    k = karte(
        {
            "url_muster": r"/api/preis\?",
            "pfade": {"rate": "rate", "ratenzahl": "raten"},
            "parameter": {"tarif": "tarif", "laufzeit": "laufzeit"},
        }
    )
    with klickserver(antworte) as server:
        lauf = laufe(chromium, server.adresse("/handy/x"), k, OFFEN, frist_ms=5000)

    status = {
        (e.variante.tarif, e.variante.laufzeit): e.status for e in lauf.ergebnisse
    }
    assert lauf.status == "gelesen", lauf.grund
    assert status.pop(("S", 36)) == erwartet
    assert set(status.values()) == {"erfasst"}
    assert len(status) == 3


@pytest.mark.parametrize(
    ("haengt", "verzug"),
    [("L", HAENGT_S), ("M", HAENGT_S), (None, 0.0)],
)
def test_offene_preisantwort_ist_an_jeder_stelle_nicht_erfasst(
    chromium, haengt, verzug
):
    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path == "/handy/x":
            return html(DREI_TARIFE)
        tarif = parse_qs(teile.query)["tarif"][0]
        koerper = json.dumps({"rate": RATE_JE_TARIF[tarif]})
        warte = verzug if tarif == haengt else 0.0
        return Antwort(200, "application/json", koerper, verzug=warte)

    k = karte(
        {
            "url_muster": r"/api/preis\?",
            "pfade": {"rate": "rate"},
            "parameter": {"tarif": "tarif"},
        }
    )
    with klickserver(antworte) as server:
        lauf = laufe(
            chromium, server.adresse("/handy/x"), k, OFFEN, frist_ms=KURZE_FRIST_MS
        )

    je_tarif = {e.variante.tarif: e for e in lauf.ergebnisse}
    if haengt is None:
        assert lauf.status == "gelesen"
        assert {t: e.werte.rate for t, e in je_tarif.items()} == {
            t: float(r) for t, r in RATE_JE_TARIF.items()
        }
        return
    bis_dahin = list(RATE_JE_TARIF)[: list(RATE_JE_TARIF).index(haengt) + 1]
    assert list(je_tarif) == bis_dahin
    assert {je_tarif[t].status for t in bis_dahin if t != haengt} == {"erfasst"}
    assert je_tarif[haengt].status == "nicht_erfasst"
    assert "offen" in je_tarif[haengt].grund
    assert je_tarif[haengt].antwort_url is None
    assert lauf.status == "gestoert"
    assert "offen" in lauf.grund
