"""robots.txt - die erste wirklich umgesetzte Pruefung dieses Repos.

Die Fixture ist keine erfundene Datei: sie ist der woertliche Kopf von
https://www.medimax.de/robots.txt, abgerufen am 10.08.2026. Genau dieser
Anbieter hat gezeigt, dass `Disallow` die falsche Haelfte ist - erlaubt ist
dort alles Relevante, aber nur zwischen 02:00 und 08:00 UTC und mit zehn
Sekunden Abstand. Der Wochenlauf startet um 08:30.
"""
from datetime import datetime, timezone

import pytest

from telco_radar.collect.geraete.robots import (
    RobotsWaechter,
    host_von,
    lies_robots,
)

_MEDIMAX = """
# For all robots
User-agent: *

Disallow: /cart
Disallow: /*/cart
Disallow: /checkout
Disallow: /my-account

Request-rate: 1/10              # maximum rate is one page every 10 seconds
Crawl-delay: 10                 # 10 seconds between page requests
Visit-time: 0200-0800           # only visit between 02:00 and 08:00 UTC

Sitemap: https://www.medimax.de/sitemap.xml

User-agent: MJ12bot
Disallow: /
"""

_FREENET = """
Sitemap: https://www.freenet.de/sitemap.xml

User-agent: *
Disallow: /api/
Disallow: /shop/rest/
Disallow: */b/smartphones*
Disallow: /shop/*?sort=*
"""


def _um(stunde: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 11, stunde, minute, tzinfo=timezone.utc)


# --------------------------------------------------------------------------

def test_host_ohne_www():
    assert host_von("https://www.medimax.de/c/116/x") == "medimax.de"
    assert host_von("https://bestellung.norma-connect.de/p") == "bestellung.norma-connect.de"


def test_produktstrecke_ist_erlaubt_warenkorb_nicht():
    r = lies_robots(_MEDIMAX)
    assert r.erlaubt("https://www.medimax.de/c/116/telefon-navi/handy-smartphone/smartphones")
    assert r.erlaubt("https://www.medimax.de/p/1518897/galaxy-a57-5g")
    assert not r.erlaubt("https://www.medimax.de/cart")
    assert not r.erlaubt("https://www.medimax.de/de/cart")   # /*/cart


def test_stern_und_endanker():
    r = lies_robots("User-agent: *\nDisallow: */b/smartphones*\nDisallow: /shop/*?sort=*\n")
    assert not r.erlaubt("https://www.freenet.de/handys-smartphones/b/smartphones/x")
    assert r.erlaubt("https://www.freenet.de/handys-smartphones/p/P-M-4206120")
    assert not r.erlaubt("https://www.freenet.de/shop/liste?sort=preis")


def test_die_gesperrte_listenstrecke_von_freenet():
    """Der reale Fall: /p/ ist erlaubt, die Listenstrecke nicht. Deshalb ist
    die Sitemap der Einstieg und nicht die Kategorieseite."""
    r = lies_robots(_FREENET)
    assert r.erlaubt("https://www.freenet.de/handys-smartphones/p/P-M-4206120")
    assert r.erlaubt("https://www.freenet.de/sitemap.xml")
    assert not r.erlaubt("https://www.freenet.de/handys-smartphones/b/smartphones")


def test_laengster_treffer_gewinnt_und_allow_schlaegt_gleichstand():
    r = lies_robots("User-agent: *\nDisallow: /shop/\nAllow: /shop/produkte/\n")
    assert not r.erlaubt("https://x.de/shop/kasse")
    assert r.erlaubt("https://x.de/shop/produkte/handy")


def test_leeres_disallow_erlaubt_alles():
    r = lies_robots("User-agent: *\nDisallow:\n")
    assert r.erlaubt("https://x.de/irgendwas")


def test_crawl_delay_und_request_rate():
    r = lies_robots(_MEDIMAX)
    assert r.crawl_delay == 10.0


def test_request_rate_allein_ergibt_einen_abstand():
    r = lies_robots("User-agent: *\nRequest-rate: 1/20\n")
    assert r.crawl_delay == 20.0


def test_besuchszeit_wird_gelesen():
    r = lies_robots(_MEDIMAX)
    assert (r.visit_von, r.visit_bis) == (120, 480)
    assert r.fenster_text == "02:00-08:00 UTC"


@pytest.mark.parametrize("stunde,minute,drin", [
    (1, 59, False), (2, 0, True), (3, 10, True), (7, 59, True),
    (8, 0, False), (8, 30, False), (23, 0, False),
])
def test_besuchsfenster(stunde, minute, drin):
    assert lies_robots(_MEDIMAX).im_fenster(_um(stunde, minute)) is drin


def test_fenster_ueber_mitternacht():
    r = lies_robots("User-agent: *\nVisit-time: 2200-0600\n")
    assert r.im_fenster(_um(23, 0)) is True
    assert r.im_fenster(_um(3, 0)) is True
    assert r.im_fenster(_um(12, 0)) is False


def test_ohne_besuchszeit_gilt_immer():
    assert lies_robots(_FREENET).im_fenster(_um(8, 30)) is True


def test_nur_der_stern_block_gilt_uns():
    r = lies_robots(_MEDIMAX)
    # MJ12bot ist komplett gesperrt - das darf uns nicht treffen.
    assert r.erlaubt("https://www.medimax.de/p/1")


def test_mehrere_user_agent_zeilen_hintereinander_bilden_eine_gruppe():
    r = lies_robots("User-agent: Googlebot\nUser-agent: *\nDisallow: /geheim\n")
    assert not r.erlaubt("https://x.de/geheim")


# --------------------------------------------------------------------------
# Der Waechter
# --------------------------------------------------------------------------

def _waechter(antworten):
    aufrufe = []

    def hole(url):
        aufrufe.append(url)
        return antworten[url]

    w = RobotsWaechter(hole=hole)
    return w, aufrufe


def test_gesperrter_pfad_wird_nicht_abgerufen():
    """Akzeptanzkriterium aus Teil E."""
    w, aufrufe = _waechter({"https://x.de/robots.txt": (200, "User-agent: *\nDisallow: /shop/\n")})
    darf, grund = w.darf("https://x.de/shop/handy", _um(12))
    assert darf is False and "gesperrt" in grund
    # Es wurde ausschliesslich die robots.txt geholt, nicht die Seite.
    assert aufrufe == ["https://x.de/robots.txt"]


def test_ausserhalb_der_besuchszeit_ist_kein_fehler_sondern_ein_grund():
    w, _ = _waechter({"https://www.medimax.de/robots.txt": (200, _MEDIMAX)})
    darf, grund = w.darf("https://www.medimax.de/p/1", _um(8, 30))
    assert darf is False
    assert "Besuchszeit" in grund and "02:00-08:00" in grund and "08:30" in grund
    # Im Fenster derselbe Pfad: erlaubt.
    assert w.darf("https://www.medimax.de/p/1", _um(3, 0))[0] is True


def test_robots_wird_je_host_nur_einmal_geholt():
    w, aufrufe = _waechter({"https://x.de/robots.txt": (200, "User-agent: *\n")})
    for _ in range(5):
        w.darf("https://x.de/a", _um(12))
        w.darf("https://www.x.de/b", _um(12))
    assert aufrufe == ["https://x.de/robots.txt"]


def test_fehlende_robots_erlaubt_alles():
    w, _ = _waechter({"https://x.de/robots.txt": (404, "")})
    assert w.darf("https://x.de/shop", _um(12))[0] is True


def test_verweigerte_robots_sperrt():
    """Wer uns die robots.txt mit 403 verweigert, verweigert uns die Seite.
    'Kein Ergebnis' darf nie 'also erlaubt' heissen."""
    w, _ = _waechter({"https://x.de/robots.txt": (403, "")})
    darf, grund = w.darf("https://x.de/shop", _um(12))
    assert darf is False and "403" in grund


def test_netzfehler_beim_holen_sperrt_ebenfalls():
    def hole(url):
        raise OSError("connection reset")
    w = RobotsWaechter(hole=hole)
    darf, grund = w.darf("https://x.de/shop", _um(12))
    assert darf is False and "OSError" in grund


def test_abstand_nimmt_den_groesseren_wert():
    w, _ = _waechter({"https://www.medimax.de/robots.txt": (200, _MEDIMAX)})
    assert w.abstand("https://www.medimax.de/p/1", mindestens=2.0) == 10.0
    w2, _ = _waechter({"https://y.de/robots.txt": (200, "User-agent: *\n")})
    assert w2.abstand("https://y.de/p/1", mindestens=2.0) == 2.0
