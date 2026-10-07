"""BEISPIEL-Seiten für Klick-Karte Format 2: von Hand geschrieben, kein echter Anbieter.

Jede Seite bildet ein Muster aus der Erkundung vom 07.10.2026 nach (o2, congstar, 1&1,
Telekom, freenet). ``seite`` setzt Körper und Skript in ein Gerüst mit ``euro``,
``zeige`` (Preiszusammenfassung aus einer Antwort in ``#preis``) und ``lade`` (holt
``/api/preis`` mit den Parametern der Auswahl). ``preis`` rechnet die Antwort, die der
Server liefert; ``KARTE`` ist eine Karte mit den Pfaden dieser Antwort. ``laufe`` ruft
den Klick-Crawler mit eigener Hostschleuse; keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import copy
import json
from urllib.parse import parse_qs, urlsplit

from klickserver import JETZT, Antwort, html, klickserver

GERUEST = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>BEISPIEL</title></head>
<body><p>BEISPIEL: von Hand geschrieben, kein echter Anbieter.</p>
<h1 id="kanarie">Beispielhandy X</h1>
@KOERPER@
<script>
"use strict";
function euro(b) { return b.toFixed(2).replace(".", ",") + " €"; }
function zeige(d) {
  const p = d.preis;
  const ort = document.getElementById("preis");
  if (ort === null) return;
  ort.innerText = [
    "Anzahlung " + euro(p.anzahlung),
    "Monatliche Rate " + euro(p.rate) + " · " + p.raten + " Raten",
    "Tarif " + euro(p.tarif) + " mtl.",
    "Mindestlaufzeit " + p.bindung + " Monate",
    "Anschlusspreis " + euro(p.anschluss),
    "Datenvolumen " + p.volumen + " GB",
  ].join("\\n");
}
function lade(frage) {
  return fetch("/api/preis?" + new URLSearchParams(frage))
    .then((a) => a.json()).then((d) => { window.letzte = d; zeige(d); });
}
@SKRIPT@
</script></body></html>"""
RATE = {"128": 30.0, "256": 35.0}
TARIF = {"S": 19.99, "M": 29.99}
VOLUMEN = {"S": 20, "M": 50}
PFADE = {
    "anzahlung": "preis.anzahlung",
    "rate": "preis.rate",
    "ratenzahl": "preis.raten",
    "tarifphasen": "preis.tarif",
    "tarifbindung": "preis.bindung",
    "anschluss": "preis.anschluss",
    "volumen_gb": "preis.volumen",
}
KARTE = {
    "anbieter": "Beispielanbieter",
    "zusammenfassung": {"selektor": "#preis"},
    "antwort": {
        "url_muster": r"/api/preis\?",
        "pfade": PFADE,
        "variante": {
            "speicher": "auswahl.speicher",
            "tarif": "auswahl.tarif",
            "laufzeit": "auswahl.laufzeit",
        },
    },
    "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
}


def seite(koerper: str, skript: str) -> str:
    """Eine BEISPIEL-Seite aus Körper und Skript."""
    return GERUEST.replace("@KOERPER@", koerper).replace("@SKRIPT@", skript)


def preis(speicher: str, tarif: str, laufzeit: int, abzug: float = 0.0) -> dict:
    """Die Preise einer Variante; ``abzug`` senkt die Rate (Rückgabedeal, Aktion)."""
    rate = RATE[speicher] + (5.0 if laufzeit == 24 else 0.0) - abzug
    return {
        "anzahlung": 1.0,
        "rate": rate,
        "raten": laufzeit,
        "tarif": TARIF[tarif],
        "bindung": 24,
        "anschluss": 0.0,
        "volumen": VOLUMEN[tarif],
    }


def frage(pfad: str) -> dict[str, str]:
    """Die Parameter einer Adresse, je Name der erste Wert."""
    return {k: v[0] for k, v in parse_qs(urlsplit(pfad).query).items()}


def antworter(seite_html: str, rechne, pfad_seite: str = "/handy/x"):
    """Die Seite unter ``pfad_seite``, ``/api/preis`` aus ``rechne``."""

    def antworte(pfad: str) -> Antwort:
        if urlsplit(pfad).path == pfad_seite:
            return html(seite_html)
        if pfad.startswith("/api/preis"):
            daten = rechne(frage(pfad))
            if daten is None:
                return Antwort(404)
            return Antwort(200, "application/json", json.dumps(daten))
        return Antwort(404)

    return antworte


def karte(**teile):
    """Die Beispielkarte mit ersetzten Teilen der obersten Ebene."""
    from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten

    daten = copy.deepcopy(KARTE)
    daten.update(teile)
    return klickkarte_aus_daten({k: v for k, v in daten.items() if v is not None}, "B")


def laufe(browser, seite_html: str, rechne, k, frist_ms: int = 3000, **weiter):
    """Lässt den Crawler über die Seite laufen; Lauf und Server."""
    from telco_radar.collect.geraete.klickcrawler import klicke_durch
    from telco_radar.collect.geraete.klicktor import Hostschleuse
    from telco_radar.collect.geraete.robots import RobotsWaechter

    waechter = RobotsWaechter(hole=lambda url: (200, "User-agent: *\n"))
    schleuse = Hostschleuse(waechter, lambda: JETZT)
    with klickserver(antworter(seite_html, rechne)) as server:
        lauf = klicke_durch(
            browser,
            server.adresse("/handy/x"),
            k,
            waechter,
            lambda: JETZT,
            schleuse=schleuse,
            frist_ms=frist_ms,
            **weiter,
        )
    return lauf, server


def nach_auswahl(lauf) -> dict:
    """Die Ergebnisse je Variante (Speicher, Tarif, Laufzeit)."""
    return {
        (e.variante.speicher, e.variante.tarif, e.variante.laufzeit): e
        for e in lauf.ergebnisse
    }
