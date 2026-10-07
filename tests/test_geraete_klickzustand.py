"""Zweite Lesung aus dem Seitenzustand: globale Variable, Skript-JSON, Textbereiche.

BEISPIEL-Seiten nach der Erkundung vom 07.10.2026. 1&1: Preise in Cent in
``hwdVariantsPrices['product-<FARBE>-<GB>']``, Farbe und Speicher nur in der
Seitenadresse (``?color=…&size=…``), der Betrag „44 , 99 €/Monat“ in getrennten
Elementen (Fundstelle ohne den Leerraum: „44,99 €/Monat“); Tarif und Laufzeit fest.
Telekom: serverseitig gerendert, Werte im Skript-JSON, Zusammenfassung aus zwei
Blöcken ohne den Werbeblock (sonst liest der Text „unbegrenztes Datenvolumen“ als
Volumen), mit Geräterate: ohne Preiswert wäre die Kombination nicht erfasst
(``klicklauf.lesestatus``). Keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import pytest
from klickbeispiel import karte, laufe_mit, nach_auswahl, seite
from klickserver import Antwort, html

pytestmark = pytest.mark.browser

EINSUNDEINS_KOERPER = """
<div id="speicher">
  <button type="button" aria-pressed="true" data-wert="128">128 GB</button>
  <button type="button" aria-pressed="false" data-wert="256">256 GB</button>
</div>
<div id="preis"></div>"""
EINSUNDEINS_SKRIPT = """
const ADRESSE_FEST = @FEST@;
window.hwdVariantsPrices = {
  "product-SCHWARZ-128": [4499], "product-SCHWARZ-256": [5199]};
let speicher = "128";
function zeigePreis() {
  const cent = hwdVariantsPrices["product-SCHWARZ-" + speicher][0];
  document.getElementById("preis").innerHTML = "<span>" + Math.floor(cent / 100)
    + "</span> , <span>" + String(cent % 100).padStart(2, "0") + "</span> €/Monat";
}
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    for (const a of document.querySelectorAll("#speicher button")) {
      a.setAttribute("aria-pressed", String(a === k));
    }
    speicher = k.dataset.wert;
    if (!ADRESSE_FEST) {
      history.replaceState(null, "", "?color=SCHWARZ&size=" + speicher);
    }
    zeigePreis();
  });
}
history.replaceState(null, "", "?color=SCHWARZ&size=128");
zeigePreis();"""
EINSUNDEINS_KARTE = {
    "knoepfe": {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"fest": "All-Net-Flat S"},
        "laufzeit": {"fest": 36},
        "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
    },
    "seite": {"farbe": {"parameter": "color"}, "speicher": {"parameter": "size"}},
    "antwort": {
        "global": "hwdVariantsPrices",
        "pfade": {
            "rate": {
                "pfad": "hwdVariantsPrices.product-{farbe}-{speicher}.0",
                "einheit": "cent",
            }
        },
    },
    "zusammenfassung": {
        "selektor": "#preis",
        "muster": {"rate": r"(\d+\s*,\s*\d{2})\s*€/Monat"},
    },
}
TELEKOM_KOERPER = """
<aside>
  <div id="zahlung">Einmalige Zahlung 138,95 € inkl. Bereitstellung 39,95 €
    <div>Gerät: Rate 21,00 € mtl.</div>
    <div id="werbung">Doppeltes oder unbegrenztes Datenvolumen mit MagentaEINS</div>
  </div>
  <div id="tarifblock">MagentaMobil M<br>Tarif 49,95 € mtl.<br>Datenvolumen 50 GB</div>
</aside>
<script type="application/json" id="zustand">
  {"tarif": {"name": "MagentaMobil M", "preis": 49.95, "anschluss": 39.95,
   "volumen": 50}, "geraet": {"rate": 21.0}}
</script>"""
TELEKOM_KARTE = {
    "knoepfe": {
        "speicher": {"fest": "256 GB"},
        "tarif": {"fest": "MagentaMobil M"},
        "laufzeit": {"fest": 36},
    },
    "antwort": {
        "skript": "#zustand",
        "pfade": {
            "rate": "geraet.rate",
            "tarifphasen": "tarif.preis",
            "anschluss": "tarif.anschluss",
            "volumen_gb": "tarif.volumen",
        },
        "variante": {"tarif": "tarif.name"},
    },
    "zusammenfassung": {"selektor": ["#zahlung", "#tarifblock"], "ohne": "#werbung"},
}


def _antworter(seite_html: str):
    def antworte(pfad: str) -> Antwort:
        return html(seite_html) if pfad == "/handy/x" else Antwort(404)

    return antworte


def _einsundeins(chromium, fest: bool = False, **ersetzt):
    skript = EINSUNDEINS_SKRIPT.replace("@FEST@", "true" if fest else "false")
    k = karte(**{**EINSUNDEINS_KARTE, **ersetzt})
    seite_html = seite(EINSUNDEINS_KOERPER, skript)
    lauf, server = laufe_mit(chromium, _antworter(seite_html), k)
    return nach_auswahl(lauf), lauf, server


def test_globale_in_cent_mit_schluessel_aus_der_seitenadresse(chromium):
    ergebnisse, lauf, server = _einsundeins(chromium)

    assert lauf.status == "gelesen", lauf.grund
    assert set(ergebnisse) == {
        ("128", "All-Net-Flat S", 36),
        ("256", "All-Net-Flat S", 36),
    }
    assert {e.status for e in ergebnisse.values()} == {"erfasst"}, [
        e.grund for e in ergebnisse.values()
    ]
    rate = ergebnisse[("256", "All-Net-Flat S", 36)].werte.rate
    assert rate == 51.99
    beleg = ergebnisse[("256", "All-Net-Flat S", 36)].beleg.beleg
    assert [(s.feld, s.selektor, s.ausschnitt) for s in beleg.fundstellen] == [
        ("rate", "#preis", "51,99 €/Monat")
    ]
    assert (
        beleg.fundstellen[0].json_pfad
        == "hwdVariantsPrices.product-{farbe}-{speicher}.0"
    )
    assert server.mit("/handy/x") == ["/handy/x"]


def test_stehende_seitenadresse_zeigt_den_alten_speicher(chromium):
    ergebnisse, _, _ = _einsundeins(chromium, fest=True)

    falsch = ergebnisse[("256", "All-Net-Flat S", 36)]
    assert falsch.status == "befund"
    assert falsch.befunde[0].grund == "Seite zeigt 128 statt 256"


def test_ohne_einheit_widerspricht_der_centbetrag_dem_text(chromium):
    antwort = {
        "global": "hwdVariantsPrices",
        "pfade": {"rate": "hwdVariantsPrices.product-{farbe}-{speicher}.0"},
    }

    ergebnisse, _, _ = _einsundeins(chromium, antwort=antwort)

    assert {e.status for e in ergebnisse.values()} == {"befund"}
    assert ergebnisse[("128", "All-Net-Flat S", 36)].befunde[0].grund == (
        "Text 44,99, Antwort 4.499,00"
    )


def _telekom(chromium, **ersetzt):
    k = karte(**{**TELEKOM_KARTE, **ersetzt})
    lauf, _ = laufe_mit(chromium, _antworter(seite(TELEKOM_KOERPER, "")), k)
    return nach_auswahl(lauf), lauf


def test_skript_json_und_zwei_bereiche_ohne_werbeblock(chromium):
    ergebnisse, lauf = _telekom(chromium)

    assert lauf.status == "gelesen", lauf.grund
    ergebnis = ergebnisse[("256 GB", "MagentaMobil M", 36)]
    assert ergebnis.status == "erfasst", ergebnis.grund
    werte = ergebnis.werte
    assert (werte.rate, werte.anschluss, werte.volumen_gb) == (21.0, 39.95, 50.0)
    assert werte.tarifphasen[0].betrag == 49.95
    assert "unbegrenzt" not in ergebnis.text
    assert ergebnis.beleg.beleg.antwort_url.endswith("/handy/x#lesung")


def test_ohne_ausschluss_liest_der_text_unbegrenztes_volumen(chromium):
    lesung = {"selektor": ["#zahlung", "#tarifblock"]}

    ergebnisse, _ = _telekom(chromium, zusammenfassung=lesung)

    ergebnis = ergebnisse[("256 GB", "MagentaMobil M", 36)]
    assert ergebnis.status == "befund"
    assert [b.grund for b in ergebnis.befunde] == ["Text unbegrenzt, Antwort 50,00"]
