"""Weiter-Schritt der Klick-Karte im Lauf: Startseite wählen, einmal weiter, Kacheln.

BEISPIEL-Seiten nach der Erkundung vom 07.10.2026 (1&1, Commit c8ce1f77, Seiten 3/4):
Die Produktseite wählt den Speicher und hält Bündelbetrag, Einmalzahlung und Laufzeit
(„36“) in Globalen; „Weiter zur Tarifauswahl“ legt per POST einen Warenkorb an, leitet
über eine Umleitung auf die Folgeseite, und dort stehen zwei Laufzeit-Kacheln
(„HW24“, „HW24+12“). Die Folgeseite schickt selbst ein POST, das nie hinausgehen darf.
Erwartet: je Speicher ein frischer Kontext (der Warenkorb-POST sieht kein Cookie), die
Kachel 24+12 erfasst mit Bündelbetrag und Einmalzahlung, die Kachel 24 bleibt Befund
(die Globale nennt 36). Jede Kachel trägt ihre Diagnose: Folgeseite, beide Lesungen
und wo ihr Betrag auf der Folgeseite sonst steht, nicht auf der Startseite.
Gegenproben: eine Folgeseite mit Passwortfeld beendet den Lauf, ein Weiter-Knopf mit
Kaufwort wird nie geklickt. Keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

import pytest
from klickbeispiel import frage, karte, laufe_mit, nach_auswahl, seite
from klickserver import Antwort, html, klickserver, laufe, umleitung

pytestmark = pytest.mark.browser

BUENDEL = {"128": 4499, "256": 5199}
EINMAL = {"128": "300,–", "256": "360,–"}
OHNE_VERLAENGERUNG = {"128": "59 , 99", "256": "66 , 99"}
START = """
<div id="speicher">
  <button type="button" aria-pressed="true" data-wert="128">128 GB</button>
  <button type="button" aria-pressed="false" data-wert="256">256 GB</button>
</div>
<div id="weiter">
  <button type="button">@TEXT@</button>
  <button type="button" style="display:none">@TEXT@</button>
</div>"""
START_SKRIPT = f"""
window.buendel = {json.dumps(BUENDEL)};
window.einmal = {json.dumps(EINMAL, ensure_ascii=False)};
window.dauer = "36";
for (const k of document.querySelectorAll("#speicher button")) {{
  k.addEventListener("click", () => {{
    for (const a of document.querySelectorAll("#speicher button")) {{
      a.setAttribute("aria-pressed", String(a === k));
    }}
  }});
}}
for (const k of document.querySelectorAll("#weiter button")) {{
  k.addEventListener("click", () => {{
    const speicher = document.querySelector('#speicher [aria-pressed="true"]')
      .dataset.wert;
    fetch("/korb", {{method: "POST",
                    body: JSON.stringify({{speicher, cookie: document.cookie}})}})
      .then(() => {{
        document.cookie = "korb=" + speicher + "; path=/";
        location.href = "/bestellung/start?speicher=" + speicher;
      }});
  }});
}}"""
KACHEL = """
<div class="kachel"><add-to-cart-button
  data-linkid="content_tile :: button :: Weiter mit HW@LAUFZEIT@">Weiter
  </add-to-cart-button><p>@TEXT@</p></div>"""
FOLGE_SKRIPT = """
fetch("/zaehlung", {method: "POST", body: "gesehen"});"""
KARTE = {
    "vertragsform": "ein_vertrag",
    "knoepfe": {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"fest": "S"},
        "laufzeit": {
            "selektor": "#kacheln > div.kachel",
            "wert_in": "add-to-cart-button",
            "wert": "data-linkid",
            "muster": r"Weiter mit HW(\d+(?:\+\d+)?)$",
        },
        "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
    },
    "weiter": {
        "selektor": "#weiter button",
        "text": "Weiter zur Tarifauswahl",
        "kacheln": "laufzeit",
    },
    "zusammenfassung": {
        "selektor": "#kacheln > div.kachel",
        "muster": {
            "buendelbetrag": r"(\d+\s*,\s*\d{2})\s*€/Mon\.",
            "einmalzahlung": r"einmalig\s+(\d[\d.]*,(?:\d{2}|–))\s*€",
        },
    },
    "antwort": {
        "global": ["buendel", "einmal", "dauer"],
        "pfade": {
            "buendelbetrag": {"pfad": "buendel.{speicher}", "einheit": "cent"},
            "einmalzahlung": "einmal.{speicher}",
        },
        "variante": {"laufzeit": "dauer"},
    },
}


def _folgeseite(speicher: str, zusatz: str) -> str:
    preis = f"{BUENDEL[speicher] // 100} , {BUENDEL[speicher] % 100:02d}"
    kacheln = [
        ("24", f"{OHNE_VERLAENGERUNG[speicher]} €/Mon."),
        ("24+12", f"{preis} €/Mon. Gerät einmalig {EINMAL[speicher]} € behalten."),
    ]
    koerper = "".join(
        KACHEL.replace("@LAUFZEIT@", z).replace("@TEXT@", t) for z, t in kacheln
    )
    return seite(f'<div id="kacheln">{koerper}</div>{zusatz}', FOLGE_SKRIPT)


def _antworter(text: str = "Weiter zur Tarifauswahl", zusatz: str = ""):
    start = seite(START.replace("@TEXT@", text), START_SKRIPT)

    def antworte(pfad: str) -> Antwort:
        ort = urlsplit(pfad).path
        if ort == "/handy/x":
            return html(start)
        if ort == "/korb":
            return Antwort(200, "application/json", "true")
        if ort == "/bestellung/start":
            return umleitung(f"/bestellung/laufzeit?speicher={frage(pfad)['speicher']}")
        if ort == "/bestellung/laufzeit":
            return html(_folgeseite(frage(pfad)["speicher"], zusatz))
        return Antwort(204)

    return antworte


def _laufe(chromium, text: str = "Weiter zur Tarifauswahl", zusatz: str = ""):
    cookies: set[str] = set()
    antworte = _antworter(text, zusatz)
    lauf, server = laufe_mit(chromium, antworte, karte(**KARTE), cookies=cookies)
    return lauf, server, cookies


def test_je_speicher_frischer_kontext_kachel_36_erfasst_24_befund(chromium):
    from telco_radar.collect.geraete.klicklauf import BEFUND, ERFASST
    from telco_radar.collect.geraete.klicktext import Buendelwerte
    from telco_radar.collect.geraete.klicktor import GRUND_NUR_LESEN

    lauf, server, cookies = _laufe(chromium)
    ergebnisse = nach_auswahl(lauf)

    assert lauf.status == "gelesen", lauf.grund
    assert set(ergebnisse) == {(s, "S", m) for s in ("128", "256") for m in (24, 36)}
    for speicher, betrag, einmal in (("128", 44.99, 300.0), ("256", 51.99, 360.0)):
        lang = ergebnisse[(speicher, "S", 36)]
        kurz = ergebnisse[(speicher, "S", 24)]
        assert lang.status == ERFASST, lang.befunde
        assert lang.auswahl == (speicher, "S", "24+12")
        assert lang.buendel == Buendelwerte(buendelbetrag=betrag, einmalzahlung=einmal)
        assert kurz.status == BEFUND
        assert [(b.feld, b.grund) for b in kurz.befunde] == [
            ("antwort.laufzeit", "Antwort nennt 36 statt 24")
        ]
    koerbe = [json.loads(k) for p, k in server.posts if p == "/korb"]
    assert koerbe == [
        {"speicher": "128", "cookie": ""},
        {"speicher": "256", "cookie": ""},
    ]
    assert [p for p, _ in server.posts if p != "/korb"] == []
    assert {v.grund for v in lauf.verworfen} == {GRUND_NUR_LESEN}
    assert {"128", "256"} <= cookies


def test_diagnose_je_kachel_folgeseite_lesungen_und_fundstellen(chromium):
    """Nur die Folgeseite zählt: 44,99 steht als Globale auf der Startseite und ist
    dort keine Fundstelle; 59,99 steht im JSON-LD der Folgeseite, 66,99 nirgends."""
    from telco_radar.collect.geraete.klickergebnis import kombination_als_daten
    from telco_radar.collect.geraete.klicktext import Buendelwerte

    angebot = '<script type="application/ld+json">{"price": "59.99"}</script>'
    lauf, _, _ = _laufe(chromium, zusatz=angebot)
    ergebnisse = nach_auswahl(lauf)
    diagnosen = {k: e.diagnose for k, e in ergebnisse.items()}

    assert lauf.status == "gelesen", lauf.grund
    for (speicher, _, monate), diagnose in diagnosen.items():
        adresse = urlsplit(diagnose.folgeseite)
        assert (adresse.path, adresse.query) == (
            "/bestellung/laufzeit",
            f"speicher={speicher}",
        )
        assert diagnose.antwort_laufzeit == 36
        assert diagnose.ohne_suche is None
        if monate == 36:
            assert diagnose.kachel == diagnose.antwort
            assert diagnose.fundstellen == ()
    kurz = diagnosen[("128", "S", 24)]
    assert kurz.kachel == Buendelwerte(buendelbetrag=59.99)
    assert kurz.antwort == Buendelwerte(buendelbetrag=44.99, einmalzahlung=300.0)
    assert len(kurz.fundstellen) == 1
    assert re.fullmatch(
        r"script \d+ \(application/ld\+json\) bei price", kurz.fundstellen[0]
    )
    assert diagnosen[("256", "S", 24)].kachel == Buendelwerte(buendelbetrag=66.99)
    assert diagnosen[("256", "S", 24)].fundstellen == ()
    daten = kombination_als_daten(ergebnisse[("128", "S", 24)])["diagnose"]
    assert daten["kachel"] == {"buendelbetrag": 59.99, "einmalzahlung": None}
    assert (daten["antwort_laufzeit"], daten["fundstellen"]) == (
        36,
        list(kurz.fundstellen),
    )


def test_gegenprobe_folgeseite_mit_passwortfeld_beendet_den_lauf(chromium):
    lauf, server, _ = _laufe(chromium, zusatz='<input type="password" name="pw">')

    assert lauf.status == "gestoert"
    assert lauf.grund == "Folgeseite zeigt Anmeldung (Passwortfeld)"
    assert [p for p, _ in server.posts] == ["/korb"]
    assert lauf.ergebnisse == []


def test_gegenprobe_weiter_mit_kaufwort_wird_nie_geklickt(chromium):
    from telco_radar.collect.geraete.klicklauf import NICHT_ERFASST

    lauf, server, _ = _laufe(chromium, text="Weiter zur Tarifauswahl und kaufen")

    assert server.posts == []
    assert server.mit("/bestellung") == []
    assert {e.status for e in lauf.ergebnisse} == {NICHT_ERFASST}
    assert {e.grund for e in lauf.ergebnisse} == {
        "Weiter-Knopf „Weiter zur Tarifauswahl und kaufen“ sieht nach Kauf, Kasse"
        " oder Anmeldung aus"
    }


def test_gegenprobe_robots_sperrt_die_folgeseite(chromium):
    regeln = "User-agent: *\nDisallow: /bestellung/laufzeit\n"
    with klickserver(_antworter()) as server:
        ziel = server.adresse("/handy/x")
        lauf = laufe(chromium, ziel, karte(**KARTE), regeln, frist_ms=3000)

    assert lauf.status == "gesperrt"
    assert lauf.grund.startswith(
        f"Weiter-Knopf: GET {server.adresse('/bestellung/laufzeit')}"
    )
    assert "robots.txt" in lauf.grund
    assert server.mit("/bestellung/laufzeit") == []
    assert lauf.ergebnisse == []
