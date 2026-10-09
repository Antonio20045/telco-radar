"""Telekom-Übersicht im Browser: Einwilligung und JavaScript-Prüfung eines Nebenabrufs.

Klick-Tageslauf 09.10.2026 13:25 UTC (Actions-Lauf 37936538296, Commit b0f8172f):
MF_17791 und MF_17779 endeten mit „Rückgabedeal-Schalter lässt sich nicht ausschalten:
Locator.click: Timeout 15000ms exceeded“, denn über dem Schalter lag die
Einwilligungsabfrage, die nur der Klick-Crawler der Produktseiten ablehnte. MF_17785
endete gestört mit „HTTP 202 auf …/legalnote-replacer/build/p-befae207.js“: das Tor der
Übersicht hatte keinen Beobachter, also ging die JavaScript-Prüfung des Nebenabrufs
nicht durch ``klicksperre.Pruefung`` wie auf Produktseiten (Entscheidung Antonio
08.10.2026, eine Prüfung je Seite). Eine zweite 202 derselben Seite beendet den Lauf
weiter. Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand
geschrieben, und die abgeleitete Listenantwort aus ``test_klick_uebersicht_liste``.
"""

from __future__ import annotations

import json

import pytest
from klickergebnisse import WURZEL
from klickserver import Antwort, klickserver
from test_klick_uebersicht_liste import (
    FIXTURE,
    LISTING,
    PFAD,
    SEITE,
    antworte_liste,
    lies_testseite,
    listenseiten,
)

from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN, LAUF_GESTOERT

SKRIPT = "/resources/ag2/legalnote-replacer/build/p-befae207.js"
ZWEITES = "/resources/ag2/legalnote-replacer/build/p-596b2685.js"
WAF = "x-amzn-waf-action"
EINWILLIGUNG = """<div id="einwilligung" style="position:fixed;inset:0;z-index:9;
 background:#fff"><p>Cookies</p><button id="alle">Alle akzeptieren</button>
<button id="ab">Nur erforderliche</button></div>
<script>
document.getElementById("ab").addEventListener("click",
  () => document.getElementById("einwilligung").remove());
document.getElementById("alle").addEventListener("click", () => {
  document.cookie = "alle=ja";
  document.getElementById("einwilligung").remove();
});
</script>"""


def _pruefung() -> Antwort:
    return Antwort(
        202, "text/html; charset=utf-8", "<p>Prüfung</p>", {WAF: "challenge"}
    )


def _mit_skripten(echt: dict, *pfade: str):
    seite = SEITE.replace(
        "<body>", "<body>" + "".join(f'<script src="{p}"></script>' for p in pfade)
    )
    grund = antworte_liste(seite, listenseiten(echt))

    def antworte(pfad: str) -> Antwort:
        return _pruefung() if pfad in pfade else grund(pfad)

    return antworte


@pytest.fixture(scope="module")
def echt() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "telekom.yaml")


def test_einwilligung_ueber_dem_schalter_wird_abgelehnt(chromium, karte, echt):
    seite = SEITE.replace("<body>", "<body>" + EINWILLIGUNG)
    with klickserver(antworte_liste(seite, listenseiten(echt))) as server:
        ergebnis = lies_testseite(chromium, karte, server.adresse(PFAD))
        listings = server.mit(LISTING)
    assert ergebnis["status"] == LAUF_GELESEN, ergebnis["grund"]
    liste = ergebnis["seiten"][0]["liste"]
    assert liste["einwilligung"] == "Nur erforderliche"
    assert liste["schalter_nachher"] == "false"
    assert f"{LISTING}?deal=false&seite=1" in listings
    assert len(ergebnis["saetze"]) == 2


def test_pruefung_eines_nebenabrufs_haelt_uebersicht_nicht_an(chromium, karte, echt):
    with klickserver(_mit_skripten(echt, SKRIPT)) as server:
        ergebnis = lies_testseite(chromium, karte, server.adresse(PFAD))
    assert ergebnis["status"] == LAUF_GELESEN, ergebnis["grund"]
    assert ergebnis["vollstaendig"] is True, ergebnis["unvollstaendig"]
    assert len(ergebnis["saetze"]) == 2


def test_zweite_pruefung_derselben_seite_bleibt_gestoert(chromium, karte, echt):
    with klickserver(_mit_skripten(echt, SKRIPT, ZWEITES)) as server:
        ergebnis = lies_testseite(chromium, karte, server.adresse(PFAD))
    assert ergebnis["status"] == LAUF_GESTOERT
    assert ergebnis["saetze"] == []
