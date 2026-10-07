"""Befunde der Prüferrunde zu Klick-Karte Format 2, je mit Gegenprobe.

1. HTTP 202 auf die Preisanfrage nach einem Klick (Karte mit ``laden``) beendet den Lauf
   als gestört; danach geht keine Anfrage mehr hinaus (CLAUDE.md Regel 4).
2. Eine Option als Adresse gilt nur mit einem Echo, das nicht aus der eigenen Adresse
   stammt: ignoriert die Seite den Parameter, trägt Tarif M nie die Preise von S. Ein
   Antwortpfad mit dem Platzhalter der eigenen Dimension ist kein Echo.
3. Eine angezeigte Option, auf die ``muster`` nicht passt, bleibt ``nicht_erfasst`` mit
   Grund stehen und zählt im Strukturwächter als fehlender Knopf.
4. Die Lesung aus mehreren Antworten schwärzt die Cookie-Werte aller Antworten.

BEISPIEL-Seiten, von Hand geschrieben; keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from klickbeispiel import KARTE, antworter, karte, laufe_mit, nach_auswahl, preis, seite
from klickserver import html

from telco_radar.collect.geraete.klickhar import har_aus
from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten
from telco_radar.collect.geraete.klickquellen import Quellenleser

GEWAEHLT = {"attribut": "aria-pressed", "wert": "true"}
SPEICHER = """
<div id="speicher">
  <button type="button" aria-pressed="true" data-wert="128">128 GB</button>
  <button type="button" aria-pressed="false" data-wert="256">256 GB</button>
  <button type="button" aria-pressed="false" data-wert="512">512 GB</button>
</div>
<section id="preis"></section>"""
SPEICHER_SKRIPT = """
const auswahl = {speicher: "128", tarif: "S", laufzeit: "36"};
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    for (const a of document.querySelectorAll("#speicher button")) {
      a.setAttribute("aria-pressed", String(a === k));
    }
    auswahl.speicher = k.dataset.wert;
    lade(auswahl).catch(() => {});
  });
}
lade(auswahl);"""
SPERRSEITE = "<!doctype html><html><body>Bitte warten</body></html>"


def _speicherpreis(frage: dict[str, str]) -> dict:
    s = frage["speicher"]
    return {
        "preis": preis(s if s in ("128", "256") else "256", "S", 36),
        "auswahl": {"speicher": s},
    }


@pytest.mark.browser
@pytest.mark.parametrize("sperre", [True, False])
def test_202_auf_preisanfrage_nach_klick_beendet_den_lauf(chromium, sperre):
    basis = antworter(seite(SPEICHER, SPEICHER_SKRIPT), _speicherpreis)

    def antworte(pfad: str):
        if sperre and pfad.startswith("/api/preis") and "speicher=256" in pfad:
            return html(SPERRSEITE, 202)
        return basis(pfad)

    knoepfe = {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"fest": "S"},
        "laufzeit": {"fest": 36},
        "gewaehlt": GEWAEHLT,
    }
    antwort = {
        **KARTE["antwort"],
        "laden": True,
        "variante": {"speicher": "auswahl.speicher"},
    }
    lauf, server = laufe_mit(
        chromium, antworte, karte(knoepfe=knoepfe, antwort=antwort)
    )

    nach_sperre = [p for p in server.abrufe if "speicher=512" in p]
    if sperre:
        assert lauf.status == "gestoert"
        assert "HTTP 202" in lauf.grund
        assert nach_sperre == []
    else:
        assert lauf.status == "gelesen", lauf.grund
        assert nach_sperre != []


TARIFE = """
<nav id="tarife">
  <a href="/handy/x?tariffId=S">Tarif S</a>
  <a href="/handy/x?tariffId=M">Tarif M</a>
</nav>
<div id="speicher">
  <button type="button" aria-pressed="true" data-wert="128">128 GB</button>
</div>
<section id="preis"></section>"""
SEITE_FOLGT = """
const tarif = new URLSearchParams(location.search).get("tariffId") || "S";
lade({speicher: "128", tarif: tarif, laufzeit: "36"});"""
SEITE_IGNORIERT = """
lade({speicher: "128", tarif: "S", laufzeit: "36"});"""


def _tarifpreis(frage: dict[str, str]) -> dict:
    s, t = frage["speicher"], frage["tarif"]
    return {
        "preis": preis(s, t, 36),
        "auswahl": {"speicher": s, "tarif": t},
        "namen": {"S": "S", "M": "M"},
    }


@pytest.mark.browser
@pytest.mark.parametrize(
    ("skript", "echo", "grund"),
    [
        (SEITE_IGNORIERT, None, "Nur die Adresse nennt tarif M"),
        (SEITE_IGNORIERT, "namen.{tarif}", "Nur die Adresse nennt tarif M"),
        (SEITE_IGNORIERT, "auswahl.tarif", "Antwort nennt S statt M"),
        (SEITE_FOLGT, "auswahl.tarif", None),
    ],
    ids=["ohne_echo", "platzhalter", "antwort_widerspricht", "gegenprobe"],
)
def test_option_als_adresse_braucht_ein_eigenes_echo(chromium, skript, echo, grund):
    variante = {"speicher": "auswahl.speicher"}
    if echo is not None:
        variante["tarif"] = echo
    knoepfe = {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"adressen": {"selektor": "#tarife a", "parameter": "tariffId"}},
        "laufzeit": {"fest": 36},
        "gewaehlt": GEWAEHLT,
    }
    k = karte(knoepfe=knoepfe, antwort={**KARTE["antwort"], "variante": variante})
    lauf, _ = laufe_mit(chromium, antworter(seite(TARIFE, skript), _tarifpreis), k)

    m = nach_auswahl(lauf)[("128", "M", 36)]
    if grund is None:
        assert m.status == "erfasst", m.grund
        assert m.werte.tarifphasen[0].betrag == 29.99
    else:
        assert m.status == "befund"
        assert grund in m.grund
        assert m.werte.tarifphasen is None


LAUFZEITEN = """
<div id="laufzeit">
  <button type="button" aria-pressed="true">36 Monate</button>
  <button type="button" aria-pressed="false">24 Monate</button>
  <button type="button" aria-pressed="false">12 Mon.</button>
</div>
<section id="preis"></section>"""
LAUFZEIT_SKRIPT = """
const auswahl = {speicher: "128", tarif: "S", laufzeit: "36"};
for (const k of document.querySelectorAll("#laufzeit button")) {
  k.addEventListener("click", () => {
    for (const a of document.querySelectorAll("#laufzeit button")) {
      a.setAttribute("aria-pressed", String(a === k));
    }
    auswahl.laufzeit = k.innerText.split(" ")[0];
    lade(auswahl);
  });
}
lade(auswahl);"""


def _laufzeitpreis(frage: dict[str, str]) -> dict:
    lz = int(frage["laufzeit"])
    return {
        "preis": preis("128", "S", lz),
        "auswahl": {"speicher": "128", "tarif": "S", "laufzeit": lz},
    }


@pytest.mark.browser
@pytest.mark.parametrize(
    ("muster", "grund", "zaehlt"),
    [
        (r"^(\d+)\s*Monate", "„12 Mon.“ für laufzeit passt nicht auf das Muster", True),
        (None, "Laufzeit „12 Mon.“ nicht lesbar", False),
        (r"^(\d+)\s*Mon", None, False),
    ],
    ids=["muster_passt_nicht", "ohne_muster", "muster_passt"],
)
def test_unlesbare_option_bleibt_benannte_luecke(chromium, muster, grund, zaehlt):
    laufzeit = {"selektor": "#laufzeit button"}
    if muster is not None:
        laufzeit["muster"] = muster
    knoepfe = {
        "speicher": {"fest": "128"},
        "tarif": {"fest": "S"},
        "laufzeit": laufzeit,
        "gewaehlt": GEWAEHLT,
    }
    k = karte(knoepfe=knoepfe, antwort={**KARTE["antwort"]})
    seite_html = seite(LAUFZEITEN, LAUFZEIT_SKRIPT)
    lauf, _ = laufe_mit(chromium, antworter(seite_html, _laufzeitpreis), k)

    gesehen = [(e.auswahl[2], e.status, e.grund) for e in lauf.ergebnisse]
    assert len(gesehen) == 3, gesehen
    letzte = gesehen[-1]
    if grund is None:
        assert [s for _, s, _ in gesehen] == ["erfasst"] * 3, gesehen
    else:
        assert letzte[1] == "nicht_erfasst"
        assert grund in letzte[2]
    fehlend = lauf.struktur.knoepfe_gesucht - lauf.struktur.knoepfe_gefunden
    assert (fehlend > 0) is zaehlt


SITZUNG = "a1b2c3d4e5f6g7h8"
KOERPER = [
    {"data": {"plans": [{"id": "540", "preis": 19.99, "kunde": SITZUNG}]}},
    {"data": {"matrix": [{"plan": "540", "rate": 30.0, "kunde": SITZUNG}]}},
]


class _Anfrage:
    method = "GET"
    post_data_buffer = None

    def all_headers(self):
        return {"cookie": f"sid={SITZUNG}"}


class _Antwort:
    status = 200
    status_text = "OK"
    request = _Anfrage()

    def __init__(self, daten):
        self.url = "https://www.beispiel.de/graphql"
        self._daten = daten

    def json(self):
        return self._daten

    def body(self):
        return json.dumps(self._daten).encode("utf-8")

    def all_headers(self):
        return {"content-type": "application/json", "set-cookie": f"sid={SITZUNG}"}


class _Mitschnitt:
    def __init__(self, antworten):
        self._antworten = antworten

    def antworten_seit(self, seit):
        return self._antworten[seit:]


class _Seite:
    url = "https://www.beispiel.de/handy/x"


PLAN = {
    "url_muster": "/graphql$",
    "laden": True,
    "erkennung": "data.plans",
    "pfade": {"tarifphasen": "data.plans[id={tarif}].preis"},
}
MATRIX = {
    "url_muster": "/graphql$",
    "laden": True,
    "erkennung": "data.matrix",
    "pfade": {"rate": "data.matrix[plan={tarif}].rate"},
}


@pytest.mark.parametrize(
    ("quellen", "antworten"),
    [([PLAN], KOERPER[:1]), ([PLAN, MATRIX], KOERPER)],
    ids=["eine_antwort", "lesung_aus_zwei"],
)
def test_cookie_wert_steht_nie_im_har_beleg(quellen, antworten):
    k = klickkarte_aus_daten(
        {
            "anbieter": "B",
            "knoepfe": {
                "speicher": {"fest": "128"},
                "tarif": {"fest": "540"},
                "laufzeit": {"fest": 36},
            },
            "zusammenfassung": {"selektor": "#preis"},
            "antwort": quellen,
            "kanarie": {"selektor": "#k", "enthaelt": "X"},
            "seite": {"tarif": {"parameter": "planId"}},
        },
        "B",
    )
    leser = Quellenleser(_Seite(), k, _Mitschnitt([_Antwort(d) for d in antworten]))

    lesung = leser.lies(0, True, {"tarif": "540"}, 0)
    har = har_aus(lesung.kopie, datetime(2026, 10, 7, tzinfo=UTC))

    assert lesung.lesung.werte.tarifphasen is not None
    assert SITZUNG.encode() not in har
    assert b"30.0" in har or len(antworten) == 1
