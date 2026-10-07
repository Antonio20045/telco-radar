"""Fundort je Feld außerhalb der Zusammenfassung, Ladeantwort doppelt, Filter je Farbe.

BEISPIEL-Seite nach der Erkundung Vodafone vom 07.10.2026: Optionen als Radio mit Label
in einem ``div``, gewählt nur als Eigenschaft ``checked``; die Laufzeit-Option
„Einmal“ (``value=1``) ist kein Ratenkauf und fällt per Selektor heraus. Die Preise
kommen einmal beim Laden, als xhr und als fetch mit gleichem Körper; die Werte stehen
in ``atomics`` je Speicher und Farbe (Farbe aus dem gewählten Radio) und
``composition`` je Laufzeit. Die Zusammenfassung nennt „1 € einmal“ und „33 € pro
Monat“, die Zahl der Raten nur das gewählte Laufzeit-Label. Tarif fest.
"""

from __future__ import annotations

import json

import pytest
from klickbeispiel import karte, laufe_mit, nach_auswahl, seite
from klickserver import Antwort, html

pytestmark = pytest.mark.browser

KOERPER = """
<fieldset id="farbe">
  <div><input type="radio" name="color" value="Blau" checked><label>Blau</label></div>
  <div><input type="radio" name="color" value="Orange"><label>Orange</label></div>
</fieldset>
<fieldset id="speicher">
  <div><input type="radio" name="capacity" value="262144" checked><label>256 GB
    1 € einmal</label></div>
  <div><input type="radio" name="capacity" value="524288"><label>512 GB 0,99 €
    einmal</label></div>
</fieldset>
<fieldset id="laufzeit">
  <div><input type="radio" name="dauer" value="36" checked><label>36 Raten
    33 €</label></div>
  <div><input type="radio" name="dauer" value="24"><label>24 Raten 49,50 €</label></div>
  <div><input type="radio" name="dauer" value="1"><label>Einmal 1199,90 €</label></div>
</fieldset>
<table id="preis"><tr><td id="einmal"></td></tr><tr><td id="monat"></td></tr>
  <tr><td>9,98 €</td></tr></table>"""
SKRIPT = """
let daten = null;
function gewaehlt(name) {
  return document.querySelector("input[name=" + name + "]:checked").value;
}
function zeigeVf() {
  const atom = daten.data.atomics.find((a) => String(a.capacity.sortValue)
    === gewaehlt("capacity") && a.color.displayLabel === gewaehlt("color"));
  const teil = atom.composition.find(
    (c) => String(c.financingDuration) === gewaehlt("dauer"));
  document.getElementById("einmal").innerText = euro(teil.einmal) + " einmal";
  document.getElementById("monat").innerText = euro(teil.monat) + " pro Monat";
}
for (const div of document.querySelectorAll("fieldset div")) {
  div.addEventListener("click", () => {
    div.querySelector("input").checked = true;
    if (daten !== null) zeigeVf();
  });
}
const xhr = new XMLHttpRequest();
xhr.open("GET", "/glados/virtualItem/7?financingType=rate");
xhr.send();
fetch("/glados/virtualItem/7?financingType=rate").then((a) => a.json())
  .then((d) => { daten = d; zeigeVf(); });"""
ATOM = "data.atomics[capacity.sortValue={speicher}][color.displayLabel={farbe}]"
TEIL = ATOM + ".composition[financingDuration={laufzeit}]"
OPTION = {"wert_in": "input", "wert": "value"}
KARTE = {
    "knoepfe": {
        "speicher": {"selektor": "#speicher div", **OPTION},
        "tarif": {"fest": "ohne Tarif"},
        "laufzeit": {"selektor": '#laufzeit div:not(:has(input[value="1"]))', **OPTION},
        "gewaehlt": {"passt": ":has(input:checked)"},
    },
    "seite": {"farbe": {"selektor": "#farbe input:checked", "attribut": "value"}},
    "antwort": {
        "url_muster": "/glados/virtualItem/",
        "laden": True,
        "pfade": {
            "anzahlung": f"{TEIL}.einmal",
            "rate": f"{TEIL}.monat",
            "ratenzahl": f"{TEIL}.financingDuration",
        },
        "variante": {"speicher": f"{ATOM}.capacity.sortValue"},
    },
    "zusammenfassung": {
        "selektor": "#preis",
        "muster": {
            "anzahlung": r"([\d.,]+)\s*€\s*einmal",
            "rate": r"([\d.,]+)\s*€\s*pro\s+Monat",
            "ratenzahl": {
                "selektor": "#laufzeit input:checked + label",
                "muster": r"(\d+)\s*Raten",
            },
        },
    },
}
MONAT = {262144: 33.0, 524288: 40.0}


def _daten() -> str:
    atomics = [
        {
            "capacity": {"sortValue": kapazitaet},
            "color": {"displayLabel": farbe},
            "composition": [
                {
                    "financingDuration": dauer,
                    "einmal": 1.0 if kapazitaet == 262144 else 0.99,
                    "monat": MONAT[kapazitaet] * 36 / dauer + aufschlag,
                }
                for dauer in (36, 24, 12)
            ],
        }
        for farbe, aufschlag in (("Blau", 0.0), ("Orange", 1.0))
        for kapazitaet in MONAT
    ]
    return json.dumps({"data": {"atomics": atomics}})


def _laufe(chromium, **ersetzt):
    koerper = _daten()
    seite_html = seite(KOERPER, SKRIPT)

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(seite_html)
        if pfad.startswith("/glados/virtualItem/7?"):
            return Antwort(200, "application/json", koerper)
        return Antwort(404)

    lauf, server = laufe_mit(chromium, antworte, karte(**{**KARTE, **ersetzt}))
    return nach_auswahl(lauf), lauf, server


def test_fundort_je_feld_doppelte_ladeantwort_und_filter_je_farbe(chromium):
    ergebnisse, lauf, server = _laufe(chromium)

    assert lauf.status == "gelesen", lauf.grund
    assert set(ergebnisse) == {
        (s, "ohne Tarif", lz) for s in ("262144", "524288") for lz in (36, 24)
    }
    assert {e.status for e in ergebnisse.values()} == {"erfasst"}, [
        e.grund for e in ergebnisse.values()
    ]
    werte = ergebnisse[("524288", "ohne Tarif", 24)].werte
    assert (werte.anzahlung, werte.rate, werte.ratenzahl) == (0.99, 60.0, 24)
    assert len(server.mit("/glados/")) == 2
    stellen = ergebnisse[("262144", "ohne Tarif", 36)].beleg.beleg.fundstellen
    assert {s.feld: (s.selektor, s.ausschnitt) for s in stellen} == {
        "anzahlung": ("#preis", "1,00 € einmal"),
        "rate": ("#preis", "33,00 € pro Monat"),
        "ratenzahl": ("#laufzeit input:checked + label", "36 Raten"),
    }


def test_ohne_eigenen_fundort_fehlt_die_ratenzahl_im_text(chromium):
    muster = dict(KARTE["zusammenfassung"]["muster"])
    del muster["ratenzahl"]
    lesung = {"selektor": "#preis", "muster": muster}

    ergebnisse, _, _ = _laufe(chromium, zusammenfassung=lesung)

    assert {e.status for e in ergebnisse.values()} == {"befund"}
    assert {b.feld for e in ergebnisse.values() for b in e.befunde} == {"ratenzahl"}


def test_ohne_filter_je_farbe_ist_die_antwort_mehrdeutig(chromium):
    ohne_farbe = "[color.displayLabel={farbe}]"
    antwort = json.loads(json.dumps(KARTE["antwort"]).replace(ohne_farbe, ""))

    ergebnisse, _, _ = _laufe(chromium, antwort=antwort)

    assert {e.status for e in ergebnisse.values()} == {"befund"}
    grund = ergebnisse[("262144", "ohne Tarif", 36)].befunde[0].grund
    assert grund == "fehlt in der Antwort, Text 33,00"
