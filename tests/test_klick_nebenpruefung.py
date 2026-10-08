"""JavaScript-Prüfung eines Nebenabrufs (AWS WAF, HTTP 202) im Klick-Crawler.

Befund Telekom-Lauf 08.10.2026: Die Hauptseite kam ohne Sperre, ein Nebenabruf
derselben Seite (``/opt-in/cookie.php``) antwortete mit 202 und
``x-amzn-waf-action: challenge``, und der Lauf endete. Entscheidung Antonio
08.10.2026: Eine JavaScript-Prüfung darf der Browser so durchlaufen wie jeder
Browser, auch in einem Nebenabruf; sie zählt gegen dieselbe Grenze „eine Prüfung je
Seite“ (``klicksperre.Pruefung``). Eine zweite Prüfung derselben Seite, ein Captcha
und eine 202 ohne Kennzeichen beenden den Lauf wie bisher. Der Beobachter ist der aus
dem Tageslauf (``klickseite.beobachte``). Ein lokaler Server auf 127.0.0.1 liefert
BEISPIEL-Seiten, von Hand geschrieben; keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from klickserver import Antwort, html, karte, laufe
from test_geraete_klickchallenge import ANTWORT, FRIST_MS, OFFEN, PREIS, PRUEFUNG, TOKEN

from telco_radar.collect.geraete.klickseite import beobachte

NEBEN = "/opt-in/cookie.php"
WAF = "x-amzn-waf-action"
SEITE = """<!doctype html><html><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif"><button data-wert="S" aria-pressed="true">Tarif S</button></div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="preis"></section>
<script>
const einwilligung = () => fetch("/opt-in/cookie.php").then(async r => {
  if (r.status !== 202) return;
  const t = await (await fetch("/verify", {method: "POST", body: "b"})).text();
  document.cookie = "aws-waf-token=" + t + "; path=/";
  return einwilligung();
});
einwilligung().then(() => fetch("/api/preis?tarif=S")).then(r => r.json()).then(d => {
  document.getElementById("preis").innerText = `Monatliche Rate ${d.rate},00 €`;
});
</script></body></html>"""


def _pruefung(art: str | None = "challenge") -> Antwort:
    kopf = {} if art is None else {WAF: art}
    return Antwort(202, "text/html; charset=utf-8", PRUEFUNG, kopf)


@contextmanager
def _server(antworte: Callable[[str, str], Antwort]) -> Iterator[list]:
    """Merkt je Abruf Pfad und Cookie-Kopf; ``antworte`` sieht beide."""
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

        def beobachter(anfrage, antwort) -> str | None:
            return beobachte(anfrage, antwort, adresse, set())

        lauf = laufe(
            chromium,
            adresse,
            karte(ANTWORT),
            OFFEN,
            frist_ms=FRIST_MS,
            beobachter=beobachter,
        )
    return lauf, [pfad for pfad, _ in abrufe], abrufe


def _antworter(neben: Callable[[str], Antwort], haupt_pruefung: bool = False):
    def antworte(pfad: str, cookie: str) -> Antwort:
        mit_token = TOKEN in cookie
        if pfad == "/verify":
            return Antwort(200, "text/plain", TOKEN)
        if pfad == "/handy/x":
            return html(SEITE) if mit_token or not haupt_pruefung else _pruefung()
        if pfad == NEBEN:
            return neben(cookie)
        if pfad.startswith("/api/preis"):
            return PREIS
        return Antwort(200, "text/javascript", "")

    return antworte


def _bis_token(cookie: str) -> Antwort:
    return Antwort(200, "text/plain", "ok") if TOKEN in cookie else _pruefung()


def test_pruefung_eines_nebenabrufs_laeuft_im_browser_durch(chromium):
    lauf, pfade, abrufe = _laufe(chromium, _antworter(_bis_token))

    neben = [cookie for pfad, cookie in abrufe if pfad == NEBEN]
    assert len(neben) == 2
    assert f"aws-waf-token={TOKEN}" in neben[1]
    assert lauf.status == "gelesen", lauf.grund
    assert lauf.sperre == "challenge_nebenabruf"
    assert lauf.http_status == 200
    assert [e.status for e in lauf.ergebnisse] == ["erfasst"]


def test_zweite_pruefung_im_nebenabruf_beendet_den_lauf(chromium):
    lauf, pfade, _ = _laufe(chromium, _antworter(lambda cookie: _pruefung()))

    assert pfade.count(NEBEN) == 2
    assert lauf.status == "gestoert"
    assert NEBEN in lauf.grund and "202" in lauf.grund
    assert lauf.sperre == "challenge"
    assert not any(p.startswith("/api/preis") for p in pfade)


def test_nebenpruefung_nach_bestandener_hauptpruefung_ist_die_zweite(chromium):
    antworte = _antworter(lambda cookie: _pruefung(), haupt_pruefung=True)
    lauf, pfade, _ = _laufe(chromium, antworte)

    assert pfade.count("/handy/x") == 2
    assert pfade.count(NEBEN) == 1
    assert lauf.status == "gestoert"
    assert NEBEN in lauf.grund
    assert lauf.sperre == "challenge"


@pytest.mark.parametrize(
    "antwort",
    [_pruefung(None), _pruefung("captcha"), Antwort(403, "text/html", "<p>nein</p>")],
    ids=["202_ohne_kennzeichen", "captcha", "403"],
)
def test_andere_sperre_im_nebenabruf_beendet_den_lauf_wie_bisher(chromium, antwort):
    lauf, pfade, _ = _laufe(chromium, _antworter(lambda cookie: antwort))

    assert pfade.count(NEBEN) == 1
    assert lauf.status == "gestoert"
    assert NEBEN in lauf.grund
    assert lauf.sperre is None
    assert not any(p.startswith("/api/preis") for p in pfade)
