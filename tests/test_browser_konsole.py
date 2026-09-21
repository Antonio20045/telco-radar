"""Gegenprobe zu `browser_konsole`.

Dieser Filter ist eine Ausnahme von "jeder Konsolenfehler ist ein
Fehler". Eine Ausnahme ohne Gegenprobe wird zur Luecke: sie kann still
wachsen, bis sie auch echte Fehler durchlaesst. Deshalb steht hier
BEIDES fest - was durchfaellt und was gerade NICHT durchfaellt.

Alle Wortlaute und Herkuenfte sind am 21.09.2026 in echtem Chromium
gemessen, nicht erfunden.
"""
from __future__ import annotations

from browser_konsole import (FREMDE_HERKUNFT, ZAEHLENDE_TYPEN,
                             ist_seitenfehler, konsole_sammeln)

_FONTS_URL = ("https://fonts.googleapis.com/css2?family=Source+Serif+4:"
              "ital,opsz,wght@0,8..60,400&display=swap")
_NETZ = "Failed to load resource: net::ERR_CERT_AUTHORITY_INVALID"
_STATUS_400 = ("Failed to load resource: the server responded with a "
               "status of 400 (Bad Request)")
_STATUS_404 = ("Failed to load resource: the server responded with a "
               "status of 404 (File not found)")


# --------------------------------------------------------------------------
# Der eine befreite Fall
# --------------------------------------------------------------------------

def test_netzfehler_beim_schriftenpaket_faellt_durch():
    assert ist_seitenfehler("error", _NETZ, {"url": _FONTS_URL}) is False


# --------------------------------------------------------------------------
# Was ausdruecklich NICHT befreit ist
# --------------------------------------------------------------------------

def test_http_status_beim_schriftendienst_bleibt_ein_fehler():
    """Ein Tippfehler in base.html.j2 ist kein fehlendes Netz.

    Google antwortet dann mit 400, die Seite wird ohne Webfont
    ausgeliefert - und genau das soll auffallen, auch in Actions, wo das
    Netz funktioniert.
    """
    assert ist_seitenfehler("error", _STATUS_400,
                            {"url": _FONTS_URL}) is True


def test_eigener_ladefehler_bleibt_ein_fehler():
    assert ist_seitenfehler(
        "error", _STATUS_404,
        {"url": "http://127.0.0.1:8123/app.js"}) is True


def test_eigener_netzfehler_bleibt_ein_fehler():
    """Dieselbe Fehlerart, aber die eigene Herkunft."""
    assert ist_seitenfehler(
        "error", _NETZ,
        {"url": "http://127.0.0.1:8123/style.css"}) is True


def test_fehlende_herkunft_bleibt_ein_fehler():
    """Im Zweifel laut: keine Herkunft heisst nicht "von aussen"."""
    assert ist_seitenfehler("error", _NETZ, None) is True
    assert ist_seitenfehler("error", _NETZ, {}) is True
    assert ist_seitenfehler("error", _NETZ, {"url": ""}) is True


def test_fremde_form_der_herkunft_bleibt_ein_fehler():
    """Aendert Playwright `location` von dict auf Objekt, bricht es in
    die laute Richtung."""
    class Ort:
        url = _FONTS_URL
    assert ist_seitenfehler("error", _NETZ, Ort()) is True


def test_herkunft_als_zeichenkette_bleibt_ein_fehler():
    """Gelesen wird NUR das `location`-dict.

    Bis zum 21.09.2026 nahm die Herkunftspruefung auch eine Zeichenkette
    an - ein Zweig, den kein Aufrufer im Repo benutzte und kein Test
    deckte. Er ist weg, und das haelt dieser Test fest: mit ihm war das
    hier `False` (befreit), ohne ihn `True`.
    """
    assert ist_seitenfehler("error", _NETZ, _FONTS_URL) is True


def test_aehnliche_adresse_wird_nicht_befreit():
    """`startswith` und nicht `in`: ein fremder Host, der die Adresse nur
    im Pfad traegt, bleibt ein Fehler."""
    assert ist_seitenfehler(
        "error", _NETZ,
        {"url": "https://boese.example/https://fonts.googleapis.com/x"}
    ) is True


def test_andere_fremde_adresse_wird_nicht_befreit():
    """CLAUDE.md Regel 8 verbietet CDNs - ein CDN-Ladefehler ist ein
    Befund, keine Randnotiz."""
    assert ist_seitenfehler(
        "error", _NETZ, {"url": "https://cdn.example.com/chart.js"}) is True


def test_console_assert_zaehlt_mit():
    """Chromiums Typ fuer `console.assert(false, ...)` ist "assert", nicht
    "error" (gemessen). Bis zum 21.09.2026 fiel er still heraus."""
    assert ZAEHLENDE_TYPEN == ("error", "assert")
    assert ist_seitenfehler(
        "assert", "Assertion failed: Tafel leer",
        {"url": "http://127.0.0.1:1/app.js"}) is True


def test_warnung_und_protokoll_sind_keine_fehler():
    assert ist_seitenfehler("warning", _NETZ, None) is False
    assert ist_seitenfehler("log", _NETZ, {"url": _FONTS_URL}) is False


def test_liste_bleibt_kurz_und_benannt():
    assert FREMDE_HERKUNFT == ("https://fonts.googleapis.com/",
                               "https://fonts.gstatic.com/")


# --------------------------------------------------------------------------
# Die Verdrahtung - der Teil, an dem der Reiter-Test blind war
# --------------------------------------------------------------------------

class _Seite:
    """Das Stueck Playwright-Seite, das `konsole_sammeln` anfasst."""

    def __init__(self):
        self._horcher = {}

    def on(self, ereignis, rueckruf):
        self._horcher[ereignis] = rueckruf

    def melde_konsole(self, typ, text, ort):
        eintrag = type("M", (), {"type": typ, "text": text, "location": ort})
        self._horcher["console"](eintrag())

    def melde_ausnahme(self, text):
        self._horcher["pageerror"](text)


def test_konsole_sammeln_hoert_beide_kanaele():
    """Ein geworfener Handler-Fehler kommt NUR als `pageerror` an.

    Deshalb sammelt die Verdrahtung beide Kanaele - eine Testdatei, die
    sich ihre Lambda-Zeile selbst schreibt, vergisst genau den zweiten
    (`test_geraete_radar_sprung_browser.py` bis zum 21.09.2026).
    """
    s = _Seite()
    fehler = konsole_sammeln(s)
    assert set(s._horcher) == {"console", "pageerror"}

    s.melde_konsole("error", _NETZ, {"url": _FONTS_URL})   # befreit
    assert fehler == []

    s.melde_ausnahme("TypeError: Cannot read properties of undefined")
    s.melde_konsole("error", _STATUS_404,
                    {"url": "http://127.0.0.1:1/app.js"})
    # Mit Kanalmarke, damit ein roter Test sagt, WELCHER Kanal gefeuert
    # hat - der Unterschied, um den es in dieser Datei geht.
    assert fehler == [
        "pageerror: TypeError: Cannot read properties of undefined",
        f"console: {_STATUS_404}"]
