"""Wettläufe nach dem Weiter-Klick der Erkundung, stets ausgelöst.

Leitet der Server die Navigation des Klicks um, merkt das Tor das Ziel
(``Tor.umleitung``) und beantwortet die Navigation mit einer Leerseite; diese kommt
erst danach im Browser an. Endete das Warten schon mit der Meldung des Tors, lud die
Erkundung das Ziel, bevor die Leerseite da war, und ihre Ankunft unterbrach das Laden:
Seite 2 „gestoert“, Grund „…interrupted by another navigation to …/tarife/start“ (in
der vollen Leiter etwa einer von 5 bis 20 Läufen von
``test_link_folgt_der_umleitung_und_laesst_andere_links_liegen``).

Hier hält die BEISPIEL-Ausgangsseite den Wechsel 1,5 s an (``pagehide`` rechnet), also
kommt die Leerseite stets spät an. Erwartet wie ohne Verzögerung: die Folgeseite
gelesen. Gegenprobe: ohne Umleitung (Link direkt auf die Folgeseite) gilt dasselbe.

Zweiter Wettlauf derselben Art: sperrt robots.txt das Ziel des Links, bricht das Tor
die Navigation ab, und der Browser zeigt danach eine Fehlerseite. Las die Erkundung die
Seite vorher, scheiterte das Lesen (Seite 2 „gestoert“, „Browserfehler: Page.content:
… the page is navigating“, unter Last 2 von 30 Läufen von
``test_robots_sperrt_das_ziel_des_klicks``). Hier bricht das Tor erst 1 s nach dem
Eintrag in ``verworfen`` ab, also sieht die Erkundung die Sperre stets vor der
Fehlerseite. Erwartet: ``gesperrt``, gelesen wird erst die Fehlerseite. Keine Anfrage
verlässt den Rechner.
"""

from __future__ import annotations

import pytest
import test_geraete_klickfolgeseite as erkundung
from klickserver import klickserver

ANHALTEN = """<script>addEventListener("pagehide", () => {
  const bis = Date.now() + 1500; while (Date.now() < bis) {} });</script>"""


@pytest.mark.browser
@pytest.mark.parametrize(
    ("start", "abrufe"),
    [
        ("/tarife/start", ["/tarife/start", "/tarife/alle.html"]),
        ("/tarife/alle.html", ["/tarife/alle.html"]),
    ],
    ids=["umleitung", "gegenprobe-direkt"],
)
def test_folgeseite_gelesen_auch_wenn_die_leerseite_spaet_ankommt(
    chromium, tmp_path, start, abrufe
):
    links = erkundung.LINKS.replace('href="/tarife/start"', f'href="{start}"')
    with klickserver(erkundung._antworte(links + ANHALTEN)) as server:
        ziel = erkundung._ziel(server, erkundung.LINK, "/handy/x")
        index = erkundung._erkunde(chromium, ziel, tmp_path)

    folge = index["seiten"][1]
    assert (folge["status"], folge["grund"]) == ("gelesen", None)
    assert folge["endadresse"] == server.adresse("/tarife/alle.html")
    assert server.mit("/tarife") == abrufe


@pytest.mark.browser
def test_gesperrtes_ziel_liest_erst_die_fehlerseite(chromium, tmp_path, monkeypatch):
    from telco_radar.collect.geraete import klicktor

    abbrechen = klicktor._schliesse

    def spaeter(route, code: str) -> None:
        route.request.frame.page.wait_for_timeout(1000)
        abbrechen(route, code)

    monkeypatch.setattr(klicktor, "_schliesse", spaeter)
    regeln = "User-agent: *\nDisallow: /tarife/\n"
    with klickserver(erkundung._antworte(erkundung.LINKS)) as server:
        ziel = erkundung._ziel(server, erkundung.LINK, "/handy/x")
        index = erkundung._erkunde(chromium, ziel, tmp_path, regeln)

    folge = index["seiten"][1]
    assert folge["status"] == "gesperrt", folge["grund"]
    assert folge["grund"].startswith(f"Weiter-Knopf: GET {server.adresse('/tarife/')}")
    assert folge["endadresse"] != server.adresse("/handy/x")
    assert server.mit("/tarife") == []
