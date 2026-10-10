"""Klick-Produktseiten behalten die Cookies wie ein Browser von Seite zu Seite.

Telekom, Klick-Tageslauf 10.10.2026: Nach zwei gelesenen Produktseiten kam auf der
dritten (anderer Tarif, frischer Kontext) eine zweite JavaScript-Prüfung (legalnote-
Skript), und der Anbieter endete. Die Übersichten behalten ihren Zustand seit
09.10.2026 (``klickkontext.Browserzustand``); dieselbe Mappe reicht ``klicke_durch``
jetzt an jeden Kontext weiter. BEISPIEL-Seite aus ``test_geraete_klickbuendel``;
keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import pytest
from klickbeispiel import karte, laufe_mit, seite
from klickserver import Antwort, html
from test_geraete_klickbuendel import KARTE, KOERPER, SKRIPT

from telco_radar.collect.geraete.klickkontext import Browserzustand
from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN

pytestmark = pytest.mark.browser

MERKT = "<script>document.cookie = 'aws-waf-token=probe; path=/';</script>"


def _zwei_seiten(chromium, zustand):
    seite_html = seite(MERKT + KOERPER, SKRIPT.replace("@EINMAL@", "null"))

    def antworte(pfad: str) -> Antwort:
        return html(seite_html) if pfad == "/handy/x" else Antwort(404)

    kopfzeilen = []
    for _ in range(2):
        lauf, server = laufe_mit(chromium, antworte, karte(**KARTE), zustand=zustand)
        assert lauf.status == LAUF_GELESEN, lauf.grund
        kopfzeilen.append([c for pfad, c in server.cookies if pfad == "/handy/x"])
    return kopfzeilen


def test_zweite_produktseite_behaelt_die_cookies_der_ersten(chromium):
    erste, zweite = _zwei_seiten(chromium, Browserzustand())
    assert not any("aws-waf-token" in c for c in erste)
    assert "aws-waf-token=probe" in zweite[0]


def test_ohne_browserzustand_kommt_jede_produktseite_ohne_cookie(chromium):
    erste, zweite = _zwei_seiten(chromium, None)
    assert not any("aws-waf-token" in c for c in erste + zweite)
