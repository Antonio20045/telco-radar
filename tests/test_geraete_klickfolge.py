"""Klickfolge des Klick-Crawlers: welche Antwort zu welchem Klick gehört, welche
Optionen ein Lauf führt und wann ein Lauf ohne Knöpfe nicht als gelesen gilt.

Fälle aus dem Prüferbefund zu Schritt 4: eine verspätete Antwort des vorigen Klicks,
eine Option, die erst nach einem Klick erscheint, eine Seite ohne Knöpfe, eine nicht
lesbare Laufzeit und eine Seite, die eine andere Option markiert als die geklickte.
Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand geschrieben.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from klickserver import Antwort, html, klickserver

from telco_radar.collect.geraete.robots import RobotsWaechter

JETZT = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)
OFFEN = "User-agent: *\nDisallow:\n"
RATE = {"S": 20, "M": 30, "L": 40}
VERZUG = {"S": 0.0, "M": 1.4, "L": 3.0}
SPAETE_FRIST_MS = 1000
TARIFE = """<!doctype html><html><body>
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
LAUFZEIT_JE_TARIF = """<!doctype html><html><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher"><button data-wert="256" aria-pressed="true">256 GB</button></div>
<div id="tarif">
 <button data-wert="S" aria-pressed="true">Tarif S</button>
 <button data-wert="M" aria-pressed="false">Tarif M</button>
</div>
<div id="laufzeit"></div>
<section id="preis"></section>
<script>
const auswahl = {tarif: "S", laufzeit: "24"};
function knoepfe() {
  const lz = LAUFZEITEN;
  if (!lz.includes(auswahl.laufzeit)) auswahl.laufzeit = lz[0];
  const ort = document.getElementById("laufzeit");
  ort.innerHTML = "";
  for (const w of lz) {
    const k = document.createElement("button");
    k.dataset.wert = w;
    k.textContent = w;
    k.setAttribute("aria-pressed", String(w === MARKIERT));
    k.addEventListener("click", () => { auswahl.laufzeit = w; zeige(); });
    ort.appendChild(k);
  }
  for (const k of document.querySelectorAll("#tarif button")) {
    k.setAttribute("aria-pressed", String(k.dataset.wert === auswahl.tarif));
  }
}
function zeige() {
  knoepfe();
  const lz = encodeURIComponent(auswahl.laufzeit);
  const frage = `tarif=${auswahl.tarif}&laufzeit=${lz}`;
  fetch(`/api/preis?${frage}`).then(r => r.json()).then(d => {
    document.getElementById("preis").innerText =
      `Monatliche Rate ${d.rate},00 € · ${d.raten} Raten`;
  });
}
for (const k of document.querySelectorAll("#tarif button")) {
  k.addEventListener("click", () => { auswahl.tarif = k.dataset.wert; zeige(); });
}
zeige();
</script></body></html>"""
NUR_BEI_M = 'auswahl.tarif === "M" ? ["24", "36"] : ["24"]'


def _karte(parameter, pfade=None):
    from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten

    daten = {
        "anbieter": "Beispielanbieter",
        "knoepfe": {
            "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
            "tarif": {"selektor": "#tarif button", "wert": "data-wert"},
            "laufzeit": {"selektor": "#laufzeit button", "wert": "data-wert"},
            "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
        },
        "zusammenfassung": {"selektor": "#preis"},
        "antwort": {
            "url_muster": r"/api/preis\?",
            "pfade": pfade or {"rate": "rate"},
            "parameter": parameter,
        },
        "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
    }
    return klickkarte_aus_daten(daten, "Prüfkarte")


def _laufe(chromium, adresse, karte, frist_ms=3000, vorlauf=None):
    from telco_radar.collect.geraete.klickcrawler import klicke_durch
    from telco_radar.collect.geraete.klicktor import Hostschleuse

    waechter = RobotsWaechter(hole=lambda url: (200, OFFEN))
    return klicke_durch(
        chromium,
        adresse,
        karte,
        waechter,
        lambda: JETZT,
        schleuse=Hostschleuse(waechter, lambda: JETZT),
        vorlauf=vorlauf,
        frist_ms=frist_ms,
    )


def _je_tarif_und_laufzeit(seite, rate):
    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path == "/handy/x":
            return html(seite)
        if teile.path == "/api/preis":
            frage = parse_qs(teile.query)
            tarif, laufzeit = frage["tarif"][0], frage["laufzeit"][0]
            koerper = {"rate": rate(tarif, laufzeit), "raten": int(laufzeit[:2])}
            return Antwort(200, "application/json", json.dumps(koerper))
        return Antwort(404)

    return antworte


def test_verspaetete_antwort_gehoert_nie_zum_naechsten_klick(chromium):
    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path == "/handy/x":
            return html(TARIFE)
        tarif = parse_qs(teile.query)["tarif"][0]
        koerper = json.dumps({"rate": RATE[tarif]})
        return Antwort(200, "application/json", koerper, verzug=VERZUG[tarif])

    with klickserver(antworte) as server:
        karte = _karte({"tarif": "tarif"})
        lauf = _laufe(chromium, server.adresse("/handy/x"), karte, SPAETE_FRIST_MS)

    je_tarif = {e.variante.tarif: e for e in lauf.ergebnisse}
    assert set(je_tarif) == {"S", "M", "L"}
    assert (je_tarif["S"].status, je_tarif["S"].werte.rate) == ("erfasst", 20.0)
    falsch = {
        t: e.werte.rate
        for t, e in je_tarif.items()
        if e.status == "erfasst" and e.werte.rate != RATE[t]
    }
    assert falsch == {}
    assert je_tarif["M"].status != "erfasst"
    assert je_tarif["L"].status != "erfasst"
    assert je_tarif["L"].antwort_url is None


def test_option_die_erst_nach_einem_klick_erscheint_wird_gefuehrt(chromium):
    rate = {("S", "24"): 30, ("M", "24"): 35, ("M", "36"): 25}
    seite = LAUFZEIT_JE_TARIF.replace("LAUFZEITEN", NUR_BEI_M).replace(
        "MARKIERT", "auswahl.laufzeit"
    )
    antworte = _je_tarif_und_laufzeit(seite, lambda t, lz: rate[(t, lz)])
    karte = _karte(
        {"tarif": "tarif", "laufzeit": "laufzeit"},
        {"rate": "rate", "ratenzahl": "raten"},
    )

    with klickserver(antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), karte)

    gefuehrt = {(e.variante.tarif, e.variante.laufzeit): e for e in lauf.ergebnisse}
    assert lauf.status == "gelesen"
    assert {k: e.status for k, e in gefuehrt.items()} == {
        ("S", 24): "erfasst",
        ("M", 24): "erfasst",
        ("S", 36): "nicht_erfasst",
        ("M", 36): "erfasst",
    }
    assert gefuehrt[("M", 36)].werte.rate == 25.0
    assert "36" in gefuehrt[("S", 36)].grund


def test_nicht_lesbare_laufzeit_heisst_nicht_erfasst_ohne_klick(chromium):
    seite = LAUFZEIT_JE_TARIF.replace("LAUFZEITEN", '["24", "Einmalzahlung"]').replace(
        "MARKIERT", "auswahl.laufzeit"
    )
    antworte = _je_tarif_und_laufzeit(seite, lambda t, lz: 30)
    karte = _karte({"tarif": "tarif"}, {"rate": "rate", "ratenzahl": "raten"})

    with klickserver(antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), karte)

    einmal = [e for e in lauf.ergebnisse if e.auswahl[2] == "Einmalzahlung"]
    assert [e.status for e in einmal] == ["nicht_erfasst", "nicht_erfasst"]
    assert all("Einmalzahlung" in e.grund for e in einmal)
    assert not [a for a in server.abrufe if "Einmalzahlung" in a]
    assert {e.status for e in lauf.ergebnisse if e.auswahl[2] == "24"} == {"erfasst"}


def test_andere_markierte_option_als_geklickt_ist_befund(chromium):
    seite = LAUFZEIT_JE_TARIF.replace("LAUFZEITEN", '["24", "24 Monate"]').replace(
        "MARKIERT", '"24"'
    )
    antworte = _je_tarif_und_laufzeit(seite, lambda t, lz: 30)
    karte = _karte({"tarif": "tarif"}, {"rate": "rate", "ratenzahl": "raten"})

    with klickserver(antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), karte)

    aktion = [e for e in lauf.ergebnisse if e.auswahl[2] == "24 Monate"]
    assert [e.status for e in aktion] == ["befund", "befund"]
    assert all(e.befunde[0].feld == "variante.laufzeit" for e in aktion)
    assert all(e.werte.rate is None for e in aktion)


def test_lauf_ohne_einen_gefundenen_knopf_ist_nicht_gelesen(chromium):
    seite = TARIFE.replace('<div id="', '<div class="weg-')

    with klickserver(lambda pfad: html(seite)) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), _karte({"tarif": "tarif"}))

    assert lauf.struktur.anteil_knoepfe == 0.0
    assert lauf.status == "gestoert"
    assert "Strukturbruch" in lauf.grund
    assert [e.status for e in lauf.ergebnisse] == ["nicht_erfasst"]


def _lauf(gefunden, status="gelesen"):
    from telco_radar.collect.geraete.klicklauf import Klicklauf, Strukturbilanz

    return Klicklauf(
        anbieter="Beispielanbieter",
        adresse="https://beispiel.invalid/handy/x",
        status=status,
        struktur=Strukturbilanz(10, gefunden, 70, 70),
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
  if (MUSTER !== "ladesperre") return;
  for (const k of document.querySelectorAll("#tarif button, #laufzeit button")) {
    k.disabled = an;
  }
}
function lade() {
  markiere();
  sperre(true);
  fetch(`/api/preis?tarif=${auswahl.tarif}&laufzeit=${auswahl.laufzeit}`)
    .then(r => r.json())
    .then(d => {
      document.getElementById("preis").innerText =
        `Monatliche Rate ${d.rate},00 € · ${auswahl.laufzeit} Raten`;
      setTimeout(() => sperre(false), 200);
    });
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


@pytest.mark.parametrize(
    ("muster", "erwartet"),
    [
        ("aktiv_gesperrt", "erfasst"),
        ("ladesperre", "erfasst"),
        ("wirklich_gesperrt", "nicht_angeboten"),
    ],
)
def test_gesperrter_knopf_ist_nur_nach_ruhe_nicht_angeboten(chromium, muster, erwartet):
    seite = GESPERRTE_KNOEPFE.replace("MUSTERNAME", muster)
    antworte = _je_tarif_und_laufzeit(seite, lambda t, lz: RATE_JE_KOMBINATION[t, lz])
    knoepfe = {"tarif": "tarif", "laufzeit": "laufzeit"}
    karte = _karte(knoepfe, {"rate": "rate", "ratenzahl": "raten"})

    with klickserver(antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), karte)

    status = {
        (e.variante.tarif, e.variante.laufzeit): e.status for e in lauf.ergebnisse
    }
    assert lauf.status == "gelesen"
    assert status.pop(("S", 36)) == erwartet
    assert set(status.values()) == {"erfasst"}
    assert len(status) == 3
