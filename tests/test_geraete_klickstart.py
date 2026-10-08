"""Zweite Lesung im Lauf: Startzustand im Skript, Antwort je Klick, Base64-Echo.

BEISPIEL-Seite nach der Erkundung vom 07.10.2026 (o2): je Klick eine Antwort unter
``/configuration/<base64>`` mit der Variante im Pfadsegment, den Startzustand gibt es
nur in ``script#pageValue``, die Rate nur in „Gerät mtl. (36 Raten): …“, das Volumen
in MB mit -1 für unbegrenzt, den Tarifnamen mit Markup. Keine Anfrage verlässt den
Rechner.
"""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from klickbeispiel import RATE, karte, laufe_mit, nach_auswahl, preis, seite
from klickserver import Antwort, html

from telco_radar.collect.geraete.klickecho import Variante

pytestmark = pytest.mark.browser

KNOEPFE = {
    "speicher": {"selektor": "#speicher button", "muster": r"^(\d+)"},
    "tarif": {"selektor": "#tarif button"},
    "laufzeit": {"selektor": "#laufzeit button", "muster": r"^(\d+)"},
    "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
}
O2_KOERPER = """
<div id="speicher">
  <button type="button" aria-pressed="true">128 GB</button>
  <button type="button" aria-pressed="false">256 GB</button>
</div>
<div id="tarif">
  <button type="button" aria-pressed="true" data-wert="s">O<sub>2</sub>
    Mobile S</button>
  <button type="button" aria-pressed="false" data-wert="m">O<sub>2</sub>
    Mobile M</button>
</div>
<div id="laufzeit">
  <button type="button" aria-pressed="true">36 Monate</button>
  <button type="button" aria-pressed="false">24 Monate</button>
</div>
<section id="preis"></section>
<script type="application/json" id="pageValue">@START@</script>"""
O2_SKRIPT = """
const LAUFZEIT_FALSCH = @FALSCH@;
const auswahl = {speicher: "128", tarif: "s", laufzeit: "36"};
function wert(g, k) {
  return g === "tarif" ? k.dataset.wert : k.innerText.split(" ")[0];
}
function zeigeO2(d) {
  const s = d.priceSummary;
  document.getElementById("preis").innerText = [...s.monatlich, ...s.einmal]
    .map((z) => z.description + " " + z.amount)
    .concat(["Datenvolumen " + d.volumenText]).join("\\n");
}
for (const g of ["speicher", "tarif", "laufzeit"]) {
  for (const k of document.querySelectorAll("#" + g + " button")) {
    k.addEventListener("click", () => {
      auswahl[g] = wert(g, k);
      for (const a of document.querySelectorAll("#" + g + " button")) {
        a.setAttribute("aria-pressed", String(a === k));
      }
      const lz = LAUFZEIT_FALSCH ? "24" : auswahl.laufzeit;
      const roh = "type=B;hardware=x-geraet-" + auswahl.speicher + "gb-blau-" + lz
        + "xhigh;tariff=" + auswahl.tarif;
      const segment = btoa(roh).replace(/=+$/, "")
        .replace(/\\+/g, "-").replace(/\\//g, "_");
      fetch("/configuration/" + segment).then((a) => a.json()).then(zeigeO2);
    });
  }
}
zeigeO2(JSON.parse(document.getElementById("pageValue").textContent));"""
EINTRAG = "tariff.tariffOptions[selected=true]"
O2_PFADE = {
    "anzahlung": "priceSummary.einmal.0.amount",
    "rate": "priceSummary.monatlich.0.amount",
    "ratenzahl": "priceSummary.monatlich.0.description",
    "tarifphasen": "priceSummary.monatlich.1.amount",
    "tarifbindung": "priceSummary.monatlich.1.description",
    "anschluss": "priceSummary.einmal.1.amount",
    "volumen_gb": {"pfad": f"{EINTRAG}.dataVolumeMb", "einheit": "mb"},
}
O2_ANTWORT = {
    "url_muster": "/configuration/",
    "segment": "/configuration/([^/?#]+)",
    "pfade": O2_PFADE,
    "variante": {"tarif": f"{EINTRAG}.name"},
    "parameter": {
        "speicher": {"name": "hardware", "muster": r"-(\d+)gb-"},
        "laufzeit": {"name": "hardware", "muster": r"-(\d+)xhigh"},
    },
}
O2_START = {
    "skript": "script#pageValue",
    "start": True,
    "pfade": O2_PFADE,
    "variante": {"tarif": f"{EINTRAG}.name"},
}
O2_RATE = {"muster": {"rate": r"Gerät mtl\. \(\d+ Raten\):\s*([\d.,]+\s*€)"}}


def _euro(betrag: float) -> str:
    return f"{betrag:.2f}".replace(".", ",") + " €"


def _o2_daten(speicher: str, tarif: str, laufzeit: int) -> dict:
    p = preis(speicher, tarif.upper(), laufzeit)
    optionen = [
        {
            "name": "O<sub>2</sub> Mobile S",
            "selected": tarif == "s",
            "dataVolumeMb": 20480,
        },
        {
            "name": "O<sub>2</sub> Mobile M",
            "selected": tarif == "m",
            "dataVolumeMb": -1,
        },
    ]
    return {
        "priceSummary": {
            "monatlich": [
                {
                    "description": f"Gerät mtl. ({laufzeit} Raten):",
                    "amount": _euro(p["rate"]),
                },
                {
                    "description": "Tarif mtl. (Mindestlaufzeit 24 Monate):",
                    "amount": _euro(p["tarif"]),
                },
            ],
            "einmal": [
                {"description": "Gerät Anzahlung:", "amount": "1,00 €"},
                {"description": "einmaliger Anschlusspreis", "amount": "0,00 €"},
            ],
        },
        "tariff": {"tariffOptions": optionen},
        "volumenText": "20 GB" if tarif == "s" else "unbegrenzt",
    }


def _o2_antworter(falsch: bool = False):
    start = json.dumps(_o2_daten("128", "s", 36))
    skript = O2_SKRIPT.replace("@FALSCH@", "true" if falsch else "false")
    seite_html = seite(O2_KOERPER.replace("@START@", start), skript)

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(seite_html)
        if not pfad.startswith("/configuration/"):
            return Antwort(404)
        roh = pfad.removeprefix("/configuration/")
        text = base64.urlsafe_b64decode(roh + "=" * (-len(roh) % 4)).decode()
        teile = parse_qs(urlsplit("?" + text.replace(";", "&")).query)
        hardware = teile["hardware"][0].split("-")
        daten = _o2_daten(
            hardware[2].removesuffix("gb"), teile["tariff"][0], int(hardware[4][:2])
        )
        return Antwort(200, "application/json", json.dumps(daten))

    return antworte


def _o2(chromium, quellen, falsch: bool = False, zusammenfassung=None):
    lesung = {
        "selektor": "#preis",
        **(O2_RATE if zusammenfassung is None else zusammenfassung),
    }
    k = karte(knoepfe=KNOEPFE, antwort=quellen, zusammenfassung=lesung)
    lauf, _ = laufe_mit(chromium, _o2_antworter(falsch), k)
    return nach_auswahl(lauf), lauf


def test_o2_start_im_skript_dann_antwort_mit_base64_echo(chromium):
    ergebnisse, lauf = _o2(chromium, [O2_START, O2_ANTWORT])

    assert lauf.status == "gelesen", lauf.grund
    assert len(ergebnisse) == 8
    assert {e.status for e in ergebnisse.values()} == {"erfasst"}, [
        e.grund for e in ergebnisse.values()
    ]
    start = ergebnisse[("128", "O2 Mobile S", 36)]
    assert (start.werte.rate, start.werte.volumen_gb) == (30.0, 20.0)
    assert start.beleg.beleg.antwort_url.endswith("#lesung")
    m = ergebnisse[("256", "O2 Mobile M", 24)]
    assert (m.werte.rate, m.werte.volumen_gb) == (RATE["256"] + 5, float("inf"))
    assert "/configuration/" in m.beleg.beleg.antwort_url


def test_o2_ohne_startquelle_holt_der_lauf_den_start_nach(chromium):
    """Ohne Startquelle hat der Start beim ersten Besuch keine Antwort; am Ende klickt
    der Lauf ihn aus einem anderen Zustand wieder an (``klicknachholen``)."""
    ergebnisse, lauf = _o2(chromium, O2_ANTWORT)

    assert lauf.ergebnisse[0].variante == Variante("128", "O2 Mobile S", 36)
    start = ergebnisse.pop(("128", "O2 Mobile S", 36))
    assert (start.status, start.werte.rate) == ("erfasst", 30.0)
    assert "/configuration/" in start.antwort_url
    assert {e.status for e in ergebnisse.values()} == {"erfasst"}


def test_o2_startquelle_ohne_start_liest_nach_dem_klick_den_alten_zustand(chromium):
    stehend = {k: v for k, v in O2_START.items() if k != "start"}

    ergebnisse, _ = _o2(chromium, [stehend, O2_ANTWORT])

    assert ergebnisse.pop(("128", "O2 Mobile S", 36)).status == "erfasst"
    assert {e.status for e in ergebnisse.values()} == {"befund"}


def test_o2_antwort_mit_anderer_laufzeit_im_segment_ist_ein_befund(chromium):
    ergebnisse, _ = _o2(chromium, [O2_START, O2_ANTWORT], falsch=True)

    falsch = ergebnisse[("256", "O2 Mobile S", 36)]
    assert "Antwort nennt 24 statt 36" in [b.grund for b in falsch.befunde]


def test_o2_ohne_textmuster_fehlt_die_rate_im_text(chromium):
    ergebnisse, _ = _o2(chromium, [O2_START, O2_ANTWORT], zusammenfassung={})

    befunde = {b.feld for e in ergebnisse.values() for b in e.befunde}
    assert befunde == {"rate"}
