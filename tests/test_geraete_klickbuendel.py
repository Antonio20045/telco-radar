"""Vertragsform ``ein_vertrag`` im Lauf: Bündelbetrag und Einmalzahlung statt Rate.

BEISPIEL-Seite nach der Erkundung vom 07.10.2026 (1&1, freenet): Gerät und Tarif sind
ein Vertrag; die Seite nennt „44 , 99 €/Monat“ in getrennten Elementen und die
Einmalzahlung in einem eigenen Block, die Werte stehen in Cent in einer globalen
Variable. Rate und Ratenzahl gibt es nicht; sie entfallen planmäßig und sind keine
Lücke. Der Beleg (Version 2) trägt die Bündelwerte mit Fundstellen. Keine Anfrage
verlässt den Rechner.
"""

from __future__ import annotations

import pytest
from klickbeispiel import karte, laufe_mit, nach_auswahl, seite
from klickserver import Antwort, html

pytestmark = pytest.mark.browser

KOERPER = """
<div id="speicher">
  <button type="button" aria-pressed="true" data-wert="128">128 GB</button>
  <button type="button" aria-pressed="false" data-wert="256">256 GB</button>
</div>
<div id="preis"></div>
<div id="einmal"></div>"""
SKRIPT = """
window.buendel = {"128": {monat: 4499, einmal: 2999, tarif: "All-Net-Flat S"},
                  "256": {monat: 5199, einmal: 2999, tarif: "All-Net-Flat S"}};
const TEXT_EINMAL = @EINMAL@;
function zeigeBuendel(speicher) {
  const b = buendel[speicher];
  document.getElementById("preis").innerHTML = "<span>" + Math.floor(b.monat / 100)
    + "</span> , <span>" + String(b.monat % 100).padStart(2, "0") + "</span> €/Monat";
  const einmal = speicher === "256" && TEXT_EINMAL !== null ? TEXT_EINMAL : b.einmal;
  document.getElementById("einmal").innerText = "Einmalig " + euro(einmal / 100);
}
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    for (const a of document.querySelectorAll("#speicher button")) {
      a.setAttribute("aria-pressed", String(a === k));
    }
    zeigeBuendel(k.dataset.wert);
  });
}
zeigeBuendel("128");"""
FELD = "buendel.{speicher}"
KARTE = {
    "vertragsform": "ein_vertrag",
    "knoepfe": {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"fest": "All-Net-Flat S"},
        "laufzeit": {"fest": 24},
        "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
    },
    "antwort": {
        "global": "buendel",
        "pfade": {
            "buendelbetrag": {"pfad": f"{FELD}.monat", "einheit": "cent"},
            "einmalzahlung": {"pfad": f"{FELD}.einmal", "einheit": "cent"},
        },
        "variante": {"tarif": f"{FELD}.tarif"},
    },
    "zusammenfassung": {
        "selektor": "#preis",
        "muster": {
            "buendelbetrag": r"(\d+\s*,\s*\d{2})\s*€/Monat",
            "einmalzahlung": {"selektor": "#einmal", "muster": r"Einmalig\s*([\d,]+)"},
        },
    },
}


def _laufe(chromium, text_einmal: str = "null"):
    seite_html = seite(KOERPER, SKRIPT.replace("@EINMAL@", text_einmal))

    def antworte(pfad: str) -> Antwort:
        return html(seite_html) if pfad == "/handy/x" else Antwort(404)

    lauf, _ = laufe_mit(chromium, antworte, karte(**KARTE))
    return nach_auswahl(lauf), lauf


def test_buendelwerte_bestaetigt_rate_entfaellt_beleg_traegt_sie(chromium):
    from telco_radar.collect.geraete.klickbeleg import BELEG_VERSION
    from telco_radar.collect.geraete.klicktext import Buendelwerte

    ergebnisse, lauf = _laufe(chromium)

    assert lauf.status == "gelesen", lauf.grund
    assert set(ergebnisse) == {(s, "All-Net-Flat S", 24) for s in ("128", "256")}
    teuer = ergebnisse[("256", "All-Net-Flat S", 24)]
    assert teuer.buendel == Buendelwerte(buendelbetrag=51.99, einmalzahlung=29.99)
    assert teuer.textbuendel == teuer.antwortbuendel == teuer.buendel
    for ergebnis in ergebnisse.values():
        assert ergebnis.befunde == ()
        assert not {"rate", "ratenzahl"} & set(ergebnis.luecken)
        assert ergebnis.beleg_status == "offen"
        assert ergebnis.beleg is not None
        assert ergebnis.beleg.beleg.version == BELEG_VERSION == 2
    beleg = teuer.beleg.beleg
    assert (beleg.werte["buendelbetrag"], beleg.werte["einmalzahlung"]) == (
        51.99,
        29.99,
    )
    assert beleg.werte["rate"] is None
    assert {s.feld for s in beleg.fundstellen} == {"buendelbetrag", "einmalzahlung"}
    assert lauf.struktur.anteil_felder == pytest.approx(2 / 7)


def test_abweichende_einmalzahlung_im_text_ist_ein_befund(chromium):
    ergebnisse, _ = _laufe(chromium, text_einmal="1999")

    falsch = ergebnisse[("256", "All-Net-Flat S", 24)]
    assert [(b.feld, b.grund) for b in falsch.befunde][0] == (
        "einmalzahlung",
        "Text 19,99, Antwort 29,99",
    )
    assert falsch.buendel.einmalzahlung is None
    assert falsch.buendel.buendelbetrag == 51.99
    assert falsch.textbuendel.einmalzahlung == 19.99
    assert falsch.antwortbuendel.einmalzahlung == 29.99
