"""JavaScript-Prüfung der Hauptseite (AWS WAF, HTTP 202) im Klick-Crawler.

Entscheidung Antonio 08.10.2026: Eine reine JavaScript-Prüfung (HTTP 202 mit
``x-amzn-waf-action: challenge``) darf der Browser einmal je Seite so durchlaufen,
wie jeder Browser es tut; das Skript setzt ein Cookie und lädt neu, und das Tor holt
die Seite mit diesem Cookie (``route.fetch`` teilt die Cookies des Kontexts). Eine
zweite Prüfung, ein Captcha oder eine 202 ohne Kennzeichen beenden den Lauf wie
bisher. Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand
geschrieben; er merkt je Abruf Pfad und Cookie-Kopf.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from klickserver import Antwort, html, karte, laufe

OFFEN = "User-agent: *\nDisallow:\n"
FRIST_MS = 3000
TOKEN = "beispieltoken42"
SEITE = """<!doctype html><html><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif"><button data-wert="S" aria-pressed="true">Tarif S</button></div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="preis"></section>
<script>
fetch("/api/preis?tarif=S").then(r => r.json()).then(d => {
  document.getElementById("preis").innerText = `Monatliche Rate ${d.rate},00 €`;
});
</script></body></html>"""
PRUEFUNG = """<!doctype html><html><head><title>Einen Moment</title></head><body>
<script>
fetch("/verify", {method: "POST", body: "beweis"}).then(r => r.text()).then(t => {
  document.cookie = "aws-waf-token=" + t + "; path=/";
  window.location.reload();
});
</script></body></html>"""
CAPTCHA = """<!doctype html><html><body><div id="captcha-container"></div>
<script src="/captcha.js"></script></body></html>"""
WAF = "x-amzn-waf-action"
ANTWORT = {
    "url_muster": r"/api/preis\?",
    "pfade": {"rate": "rate"},
    "parameter": {"tarif": "tarif"},
}
PREIS = Antwort(200, "application/json", json.dumps({"rate": 20}))


def _pruefung(art: str | None = "challenge", koerper: str = PRUEFUNG) -> Antwort:
    kopf = {} if art is None else {WAF: art}
    return Antwort(202, "text/html; charset=utf-8", koerper, kopf)


@contextmanager
def _server(antworte: Callable[[str, str], Antwort]) -> Iterator[list]:
    """Wie ``klickserver``, aber ``antworte`` sieht auch den Cookie-Kopf."""
    abrufe: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            return

        def do_GET(self) -> None:
            cookie = self.headers.get("Cookie") or ""
            abrufe.append((self.path, cookie))
            antwort = antworte(self.path, cookie)
            daten = antwort.koerper.encode("utf-8")
            self.send_response(antwort.status)
            self.send_header("Content-Type", antwort.typ)
            self.send_header("Content-Length", str(len(daten)))
            for name, wert in antwort.kopf.items():
                self.send_header(name, wert)
            self.end_headers()
            self.wfile.write(daten)

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.do_GET()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    abrufe.append(("port", str(httpd.server_address[1])))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield abrufe
    finally:
        httpd.shutdown()
        httpd.server_close()


def _laufe(chromium, antworte: Callable[[str, str], Antwort]):
    with _server(antworte) as abrufe:
        adresse = f"http://127.0.0.1:{abrufe.pop(0)[1]}/handy/x"
        lauf = laufe(chromium, adresse, karte(ANTWORT), OFFEN, frist_ms=FRIST_MS)
    return lauf, abrufe


def test_bestandene_challenge_laedt_die_seite_mit_dem_cookie(chromium):
    def antworte(pfad: str, cookie: str) -> Antwort:
        if pfad == "/verify":
            return Antwort(200, "text/plain", TOKEN)
        if pfad == "/handy/x":
            return html(SEITE) if TOKEN in cookie else _pruefung()
        if pfad.startswith("/api/preis"):
            return PREIS
        return Antwort(200, "text/javascript", "")

    lauf, abrufe = _laufe(chromium, antworte)

    seiten = [cookie for pfad, cookie in abrufe if pfad == "/handy/x"]
    assert len(seiten) == 2
    assert TOKEN not in seiten[0]
    assert f"aws-waf-token={TOKEN}" in seiten[1]
    assert lauf.sperre == "challenge_bestanden"
    assert lauf.http_status == 200
    assert lauf.status == "gelesen", lauf.grund
    assert [e.status for e in lauf.ergebnisse] == ["erfasst"]


def test_zweite_challenge_derselben_seite_beendet_den_lauf(chromium):
    def antworte(pfad: str, cookie: str) -> Antwort:
        if pfad == "/verify":
            return Antwort(200, "text/plain", TOKEN)
        if pfad == "/handy/x":
            return _pruefung()
        return Antwort(200, "text/javascript", "")

    lauf, abrufe = _laufe(chromium, antworte)

    pfade = [pfad for pfad, _ in abrufe]
    assert pfade.count("/handy/x") == 2
    assert pfade[-1] == "/handy/x"
    assert lauf.status == "gestoert"
    assert "202" in lauf.grund
    assert lauf.sperre == "challenge"
    assert lauf.http_status == 202


@pytest.mark.parametrize(
    ("pruefung", "sperre"),
    [
        (_pruefung("captcha"), "captcha"),
        (_pruefung("challenge", CAPTCHA), "captcha"),
        (_pruefung(None), "unbekannt"),
        (Antwort(403, "text/html", "<p>Zugriff verweigert</p>"), "unbekannt"),
    ],
    ids=["captcha_kopf", "captcha_koerper", "202_ohne_kennzeichen", "403"],
)
def test_captcha_und_unbekannte_sperre_kommen_nie_im_browser_an(
    chromium, pruefung, sperre
):
    def antworte(pfad: str, cookie: str) -> Antwort:
        return pruefung if pfad == "/handy/x" else Antwort(200, "text/plain", TOKEN)

    lauf, abrufe = _laufe(chromium, antworte)

    assert [pfad for pfad, _ in abrufe] == ["/handy/x"]
    assert lauf.status == "gestoert"
    assert lauf.sperre == sperre
    assert lauf.http_status == pruefung.status


@pytest.mark.parametrize(
    ("status", "kopf", "koerper", "art"),
    [
        (202, {WAF: "challenge"}, PRUEFUNG, "challenge"),
        (202, {"X-Amzn-Waf-Action": "Challenge"}, "", "challenge"),
        (202, {WAF: "captcha"}, "", "captcha"),
        (202, {WAF: "challenge"}, CAPTCHA, "captcha"),
        (202, {}, PRUEFUNG, "unbekannt"),
        (405, {WAF: "captcha"}, "", "captcha"),
        (403, {}, "", "unbekannt"),
        (200, {}, SEITE, None),
    ],
)
def test_sperrart_aus_kopfzeile_und_koerper(status, kopf, koerper, art):
    from telco_radar.collect.geraete.klicksperre import sperrart

    assert sperrart(status, kopf, koerper) == art
