"""Bot-Schutz im Klick-Crawler: jede Challenge beendet den Lauf als gestört.

CLAUDE.md Regel 4: Bot-Schutz wird nicht umgangen. Fälle aus der dritten Prüfrunde zu
Schritt 4: die Hauptseite wird nach einem Klick auf eine Prüfseite geschickt (HTTP 403
oder eine Challenge unter HTTP 200), die von selbst zurückleiten würde; die
Produktseite selbst ist eine Challenge unter HTTP 200; die Preisschnittstelle
antwortet mit einer Challenge unter HTTP 200. In keinem Fall kommt die Prüfseite im
Browser an, danach geht nichts mehr hinaus, und der Lauf heißt gestört. Ein lokaler
Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand geschrieben.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from klickserver import Antwort, html, karte, klickserver, laufe

OFFEN = "User-agent: *\nDisallow:\n"
FRIST_MS = 3000
SEITE = """<!doctype html><html><body>
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
const PRUEFE = "PRUEFTARIF";
function lade(tarif) {
  fetch(`/api/preis?tarif=${tarif}`).then(r => r.json()).then(d => {
    document.getElementById("preis").innerText = `Monatliche Rate ${d.rate},00 €`;
  }).catch(() => {});
}
for (const k of document.querySelectorAll("#tarif button")) {
  k.addEventListener("click", () => {
    if (k.dataset.wert === PRUEFE && !sessionStorage.getItem("geprueft")) {
      sessionStorage.setItem("geprueft", "1");
      location.href = "/pruefung";
      return;
    }
    for (const j of document.querySelectorAll("#tarif button")) {
      j.setAttribute("aria-pressed", String(j === k));
    }
    lade(k.dataset.wert);
  });
}
lade("S");
</script></body></html>"""
ZURUECK = '<script>setTimeout(() => location.replace("/handy/x"), 300);</script>'
PRUEFSEITE = f"<!doctype html><html><body>Einen Moment bitte …{ZURUECK}</body></html>"
RADWARE = (
    "<!doctype html><html><head><title>Radware Bot Manager Captcha</title></head>"
    f'<body><script src="/challenge.js"></script>{ZURUECK}</body></html>'
)
RATE = {"S": 20, "M": 30, "L": 40}
ANTWORT = {
    "url_muster": r"/api/preis\?",
    "pfade": {"rate": "rate"},
    "parameter": {"tarif": "tarif"},
}


def _preis(pfad: str) -> Antwort:
    tarif = parse_qs(urlsplit(pfad).query)["tarif"][0]
    return Antwort(200, "application/json", json.dumps({"rate": RATE[tarif]}))


@pytest.mark.parametrize(
    "pruefung",
    [html(PRUEFSEITE, 403), html(RADWARE, 200), html(PRUEFSEITE, 202)],
    ids=["403", "radware_200", "202"],
)
def test_challenge_der_hauptseite_im_lauf_beendet_den_lauf(chromium, pruefung):
    def antworte(pfad: str) -> Antwort:
        teil = urlsplit(pfad).path
        if teil == "/handy/x":
            return html(SEITE.replace("PRUEFTARIF", "M"))
        if teil == "/pruefung":
            return pruefung
        if teil == "/api/preis":
            return _preis(pfad)
        return Antwort(200, "text/javascript", "")

    with klickserver(antworte) as server:
        lauf = laufe(
            chromium,
            server.adresse("/handy/x"),
            karte(ANTWORT),
            OFFEN,
            frist_ms=FRIST_MS,
        )

    danach = server.abrufe[server.abrufe.index("/pruefung") + 1 :]
    assert danach == []
    assert lauf.status == "gestoert"
    assert "Abruf gestört" in lauf.grund
    assert str(pruefung.status) in lauf.grund
    erfasst = [e.variante.tarif for e in lauf.ergebnisse if e.status == "erfasst"]
    assert erfasst == ["S"]


def test_produktseite_als_challenge_unter_200_kommt_nie_im_browser_an(chromium):
    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(RADWARE.replace("<body>", '<body><h1 id="kanarie">X</h1>'))
        return Antwort(200, "text/javascript", "")

    k = karte(ANTWORT)
    with klickserver(antworte) as server:
        lauf = laufe(chromium, server.adresse("/handy/x"), k, OFFEN, frist_ms=FRIST_MS)

    assert server.abrufe == ["/handy/x"]
    assert lauf.status == "gestoert"
    assert lauf.http_status == 200
    assert "Challenge" in lauf.grund
    assert lauf.ergebnisse == []


@pytest.mark.parametrize(
    "challenge",
    [
        Antwort(200, "text/html; charset=utf-8", RADWARE),
        Antwort(200, "text/html", "<html><body>Bitte warten</body></html>"),
        Antwort(
            200,
            "application/json",
            json.dumps({"url": "https://geo.captcha-delivery.com/captcha/?x=1"}),
        ),
    ],
    ids=["radware_html", "html_statt_json", "captcha_json"],
)
def test_challenge_der_preisschnittstelle_beendet_den_lauf(chromium, challenge):
    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(SEITE)
        return challenge

    with klickserver(antworte) as server:
        lauf = laufe(
            chromium,
            server.adresse("/handy/x"),
            karte(ANTWORT),
            OFFEN,
            frist_ms=FRIST_MS,
        )

    assert server.mit("/api/preis") == ["/api/preis?tarif=S"]
    assert lauf.status == "gestoert"
    assert lauf.grund.startswith("Preisantwort: Abruf gestört")
    assert lauf.ergebnisse == []


@pytest.mark.parametrize(
    ("status", "typ", "koerper", "json_erwartet", "gestoert"),
    [
        (200, "application/json", '{"rate": 25}', True, False),
        (200, "text/html; charset=utf-8", "<p>Beispielhandy X</p>", False, False),
        (200, "text/html; charset=utf-8", "<p>Rate 25,00 €</p>", True, True),
        (200, "text/html", "<title>Radware Bot Manager Captcha</title>", False, True),
        (
            200,
            "application/json",
            '{"url": "https://validate.perfdrive.com/x"}',
            True,
            True,
        ),
        (202, "text/html", "", False, True),
        (403, "application/json", "{}", True, True),
        (None, "", "", False, True),
    ],
)
def test_bot_schutz_nach_status_typ_und_muster(
    status, typ, koerper, json_erwartet, gestoert
):
    from telco_radar.collect.geraete.klicklauf import bot_schutz

    grund = bot_schutz(status, typ, koerper, json_erwartet=json_erwartet)

    assert (grund is not None) is gestoert
    if gestoert:
        assert grund.startswith("Abruf gestört")
