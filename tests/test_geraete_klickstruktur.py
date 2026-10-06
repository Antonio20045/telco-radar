"""Strukturwächter des Klick-Crawlers: wann ein Lauf nicht als gelesen gilt.

Mindestanteile gefundener Knöpfe und Wertfelder gelten auch ohne Vorlauf; nur ein
gelesener Lauf ist Bezug für den nächsten; ein Lauf nur aus nicht angebotenen
Kombinationen ist gestört. Fall aus der dritten Prüfrunde zu Schritt 4: ein Erstlauf,
dessen Preiszusammenfassung der Selektor nie trifft, heißt gestört und wird kein
Bezug. Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand geschrieben.
"""

from __future__ import annotations

import json

import pytest
from klickserver import Antwort, html, karte, klickserver, laufe

OFFEN = "User-agent: *\nDisallow:\n"
FELDER_GESUCHT = 70
ZWEI_TARIFE = """<!doctype html><html><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif">
 <button data-wert="S" aria-pressed="true">Tarif S</button>
 <button data-wert="M" aria-pressed="false">Tarif M</button>
</div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="ORT"></section>
<script>
function lade(tarif) {
  fetch(`/api/preis?tarif=${tarif}`).then(r => r.json()).then(d => {
    document.getElementById("ORT").innerText = `Monatliche Rate ${d.rate},00 €`;
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
ANTWORT = {
    "url_muster": r"/api/preis\?",
    "pfade": {"rate": "rate"},
    "parameter": {"tarif": "tarif"},
}


def _lauf(gefunden, status="gelesen", felder=FELDER_GESUCHT):
    from telco_radar.collect.geraete.klicklauf import Klicklauf, Strukturbilanz

    return Klicklauf(
        anbieter="Beispielanbieter",
        adresse="https://beispiel.invalid/handy/x",
        status=status,
        struktur=Strukturbilanz(10, gefunden, FELDER_GESUCHT, felder),
    )


@pytest.mark.parametrize(
    ("gefunden", "bruch"), [(0, True), (4, True), (5, False), (10, False)]
)
def test_mindestanteil_gefundener_knoepfe_gilt_ohne_vorlauf(gefunden, bruch):
    from telco_radar.collect.geraete.klicklauf import pruefe_struktur

    grund = pruefe_struktur(_lauf(gefunden), None)

    assert (grund is not None) is bruch
    if bruch:
        assert "Strukturbruch" in grund


@pytest.mark.parametrize(
    ("felder", "bruch"), [(0, True), (6, True), (7, False), (FELDER_GESUCHT, False)]
)
def test_mindestanteil_gefundener_felder_gilt_ohne_vorlauf(felder, bruch):
    from telco_radar.collect.geraete.klicklauf import (
        MINDESTANTEIL_FELDER,
        pruefe_struktur,
    )

    lauf = _lauf(10, felder=felder)

    grund = pruefe_struktur(lauf, None)

    assert (felder / FELDER_GESUCHT < MINDESTANTEIL_FELDER) is bruch
    assert (grund is not None) is bruch
    if bruch:
        assert "Felder" in grund


@pytest.mark.parametrize(
    ("status_vorlauf", "bruch"),
    [("gelesen", True), ("gestoert", False), ("gesperrt", False)],
)
def test_nur_ein_gelesener_lauf_ist_bezug(status_vorlauf, bruch):
    from telco_radar.collect.geraete.klicklauf import pruefe_struktur

    lauf = _lauf(7)

    grund = pruefe_struktur(lauf, _lauf(10, status_vorlauf))

    assert (grund is not None) is bruch
    assert (lauf.bezug is not None) is bruch


def test_bleibender_strukturbruch_bleibt_gestoert():
    from telco_radar.collect.geraete.klicklauf import pruefe_struktur

    erster, zweiter, dritter = _lauf(10), _lauf(6), _lauf(6)
    vierter, fuenfter = _lauf(10), _lauf(10)

    assert pruefe_struktur(erster, None) is None
    grund_zwei = pruefe_struktur(zweiter, erster)
    zweiter.status, zweiter.grund = "gestoert", grund_zwei
    grund_drei = pruefe_struktur(dritter, zweiter)
    dritter.status, dritter.grund = "gestoert", grund_drei

    assert grund_zwei is not None
    assert grund_drei is not None
    assert dritter.bezug == erster.struktur
    assert pruefe_struktur(vierter, dritter) is None
    assert pruefe_struktur(fuenfter, vierter) is None
    assert fuenfter.bezug == vierter.struktur


@pytest.mark.parametrize(
    ("status", "gestoert"),
    [
        (("nicht_angeboten", "nicht_angeboten"), True),
        (("nicht_angeboten", "erfasst"), False),
        (("nicht_angeboten", "nicht_erfasst"), False),
        ((), False),
    ],
)
def test_lauf_mit_nur_nicht_angebotenen_kombinationen_ist_gestoert(status, gestoert):
    from telco_radar.collect.geraete.klickecho import Variante
    from telco_radar.collect.geraete.klicklauf import Kombiergebnis, ergebnisgrund

    ergebnisse = [Kombiergebnis(Variante("128", "S", 24), s) for s in status]

    grund = ergebnisgrund(ergebnisse)

    assert (grund is not None) is gestoert


def _antworte(ort):
    seite = ZWEI_TARIFE.replace("ORT", ort)

    def antworte(pfad: str) -> Antwort:
        if pfad.startswith("/api/preis"):
            rate = 30 if "tarif=M" in pfad else 20
            return Antwort(200, "application/json", json.dumps({"rate": rate}))
        return html(seite)

    return antworte


def test_erstlauf_ohne_gefundene_zusammenfassung_ist_gestoert_und_kein_bezug(
    chromium,
):
    k = karte(ANTWORT)
    with klickserver(_antworte("summe")) as server:
        erster = laufe(chromium, server.adresse("/handy/x"), k, OFFEN, frist_ms=1500)
    with klickserver(_antworte("preis")) as server:
        zweiter = laufe(
            chromium,
            server.adresse("/handy/x"),
            k,
            OFFEN,
            frist_ms=1500,
            vorlauf=erster,
        )

    assert {e.status for e in erster.ergebnisse} == {"nicht_erfasst"}
    assert erster.struktur.anteil_felder == 0.0
    assert erster.struktur.anteil_knoepfe == 1.0
    assert erster.status == "gestoert"
    assert "Felder" in erster.grund
    assert [e.werte.rate for e in zweiter.ergebnisse] == [20.0, 30.0]
    assert zweiter.status == "gelesen"
    assert zweiter.bezug is None
