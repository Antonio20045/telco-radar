"""Dialog nach einem Klick (Telekom 20.11.2026, „Einmalzahlung“), ohne Netz.

Die Beispielseite aus ``tests/fixtures/klickcrawler/`` bekommt den echten, gekürzten
Dialog der Telekom (``telekom_dialog_einmalzahlung_20261120.html``): ein Klick auf
„256 GB“ wählt nichts, sondern öffnet den Dialog, dessen Overlay die ganze Seite
bedeckt. Vorher lief jeder weitere Klick in die Frist („nicht klickbar“); jetzt
schließt der Crawler den Dialog, nennt die Kombination „Dialog „Einmalzahlung“ …“ und
klickt weiter.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import yaml
from klickserver import Antwort, html, klickserver

from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten
from telco_radar.collect.geraete.robots import RobotsWaechter

FIXTURES = Path(__file__).parent / "fixtures" / "klickcrawler"
PRODUKTPFAD = "/handy/beispielhandy-x"
JETZT = datetime(2026, 11, 20, 5, 0, tzinfo=UTC)
ROBOTS = "User-agent: *\nDisallow: /privat/json/\n"
DIALOG = (FIXTURES / "telekom_dialog_einmalzahlung_20261120.html").read_text("utf-8")
FRIST_MS = 3000
STIL = """<style>
.ODSDialog-Overlay { position: fixed; inset: 0; z-index: 10; background: #0006; }
.ODSDialog { position: fixed; top: 20%; left: 30%; width: 40%; z-index: 11;
  background: #fff; }
</style>"""
OEFFNEN_JS = """<script>
"use strict";
document.addEventListener("click", (ereignis) => {
  if (!ereignis.target.closest('#speicher button[data-wert="256"]')) return;
  ereignis.stopPropagation();
  const huelle = document.createElement("div");
  huelle.innerHTML = document.getElementById("dialogvorlage").innerHTML;
  const portal = huelle.firstElementChild;
  document.body.appendChild(portal);
  if (ZU) {
    portal.querySelector(".ODSDialog-CloseButton").addEventListener(
      "click", () => portal.remove());
  }
}, true);
</script>"""


def _beispiel():
    """Beispielseite und Preisantworten aus den Fixtures (wie im Crawler-Gerüst)."""
    preise = json.loads((FIXTURES / "beispiel_preise.json").read_text("utf-8"))
    seite = (FIXTURES / "beispiel_produktseite.html").read_text("utf-8")

    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path == "/api/preis":
            frage = parse_qs(teile.query)
            teil = ("speicher", "tarif", "laufzeit")
            schluessel = "|".join(frage.get(t, [""])[0] for t in teil)
            antwort = preise.get(schluessel)
            if antwort is None:
                return Antwort(404)
            return Antwort(200, "application/json", json.dumps(antwort))
        if teile.path == PRODUKTPFAD:
            return html(seite)
        return Antwort(404)

    return antworte


def _karte():
    daten = yaml.safe_load((FIXTURES / "beispiel_karte.yaml").read_text("utf-8"))
    return klickkarte_aus_daten(daten, "Beispielkarte")


KOEDER = (
    '<button type="button" aria-label="Close dialog" '
    'onclick="this.dataset.geklickt = 1">Chat schließen</button>'
)
"""Ein fremder, sichtbarer Schließen-Knopf vor dem Dialog (etwa eines Chat-Fensters)."""


def _mit_dialog(schliessbar: bool, koeder: bool = False):
    innen = _beispiel()
    vorlage = f'<template id="dialogvorlage">{DIALOG}</template>'
    zusatz = STIL + vorlage + f"<script>const ZU = {str(schliessbar).lower()};</script>"
    if koeder:
        zusatz = KOEDER + zusatz

    def antworte(pfad: str) -> Antwort:
        antwort = innen(pfad)
        if pfad.split("?")[0] != PRODUKTPFAD:
            return antwort
        return html(antwort.koerper.replace("</body>", zusatz + OEFFNEN_JS + "</body>"))

    return antworte


def _laufe(chromium, schliessbar: bool, koeder: bool = False):
    from telco_radar.collect.geraete.klickcrawler import klicke_durch
    from telco_radar.collect.geraete.klicktor import Hostschleuse

    waechter = RobotsWaechter(hole=lambda url: (200, ROBOTS))
    schleuse = Hostschleuse(waechter, lambda: JETZT)
    with klickserver(_mit_dialog(schliessbar, koeder)) as server:
        return klicke_durch(
            chromium,
            server.adresse(PRODUKTPFAD),
            _karte(),
            waechter,
            lambda: JETZT,
            schleuse=schleuse,
            frist_ms=FRIST_MS,
        )


def _je_variante(lauf) -> dict:
    return {
        (e.variante.speicher, e.variante.tarif, e.variante.laufzeit): e
        for e in lauf.ergebnisse
    }


def test_fixture_ist_der_echte_dialog():
    assert Path(FIXTURES / "telekom_dialog_einmalzahlung_20261120.html").is_file()
    assert 'role="dialog"' in DIALOG
    assert "ODSDialog-Overlay" in DIALOG
    assert 'aria-label="Close dialog"' in DIALOG
    assert ">Einmalzahlung</h2>" in DIALOG


def test_dialog_wird_geschlossen_und_die_seite_weiter_geklickt(chromium):
    lauf = _laufe(chromium, schliessbar=True)
    je = _je_variante(lauf)

    gruende = [e.grund or "" for e in lauf.ergebnisse]
    assert not [g for g in gruende if "nicht klickbar" in g]
    assert je[("128", "S", 24)].status == "erfasst"
    assert je[("128", "M", 24)].status == "erfasst"
    assert je[("128", "M", 36)].status == "erfasst"
    mit_dialog = [e for v, e in je.items() if v[0] == "256"]
    assert mit_dialog
    for ergebnis in mit_dialog:
        assert ergebnis.status in ("nicht_erfasst", "nicht_angeboten")
    assert any(
        "Dialog „Einmalzahlung“ nach Klick auf speicher geschlossen" in (e.grund or "")
        for e in mit_dialog
    )


def test_dialog_ohne_schliessen_wird_benannt_ohne_fristkette(chromium):
    lauf = _laufe(chromium, schliessbar=False)

    gruende = [e.grund or "" for e in lauf.ergebnisse]
    assert not [g for g in gruende if "nicht klickbar" in g]
    assert any("Dialog „Einmalzahlung“ nicht zu schließen" in g for g in gruende)


def test_nur_der_schliessen_knopf_des_dialogs_zaehlt(chromium):
    """Prüferbefund PR 173: ein anderer sichtbarer Schließen-Knopf der Seite steht vor
    dem Dialog; geklickt wird nur der im verdeckenden Dialog."""
    lauf = _laufe(chromium, schliessbar=True, koeder=True)

    gruende = [e.grund or "" for e in lauf.ergebnisse]
    assert not [g for g in gruende if "nicht zu schließen" in g]
    assert any(
        "Dialog „Einmalzahlung“ nach Klick auf speicher geschlossen" in g
        for g in gruende
    )
