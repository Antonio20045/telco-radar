"""Klick-Crawler-Gerüst (Datenkonzept Geräteradar, Abschnitt 8, Schritt 4), ohne Netz.

Die Produktseite unter ``tests/fixtures/klickcrawler/`` ist ein BEISPIEL, von Hand
geschrieben, kein echter Anbieter: Knöpfe für Speicher, Tarif und Ratenlaufzeit, eine
per JavaScript geladene Preisantwort, 36 Monate zu Tarif S deaktiviert, ein
Online-Rabatt bei 256 GB, Tarif M und 36 Monaten, den die Antwort nicht nennt, und ein
Zähler unter ``/privat/json/``, den robots.txt sperrt. Chromium lädt sie über
``page.route`` aus den Dateien; keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from telco_radar.collect.geraete.robots import RobotsWaechter

FIXTURES = Path(__file__).parent / "fixtures" / "klickcrawler"
HOST = "beispiel.invalid"
PRODUKTPFAD = "/handy/beispielhandy-x"
ADRESSE = f"https://{HOST}{PRODUKTPFAD}"
JETZT = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)
ROBOTS = "User-agent: *\nDisallow: /privat/json/\n"
FRIST_MS = 5000
KURZE_FRIST_MS = 1000
CHALLENGE = "<html><body>Bitte bestätigen Sie, dass Sie ein Mensch sind.</body></html>"
ERWARTET = {
    ("128", "S", 24): "erfasst",
    ("128", "S", 36): "nicht_angeboten",
    ("128", "M", 24): "erfasst",
    ("128", "M", 36): "erfasst",
    ("256", "S", 24): "erfasst",
    ("256", "S", 36): "nicht_angeboten",
    ("256", "M", 24): "erfasst",
    ("256", "M", 36): "befund",
}
KLICKS_IM_VOLLLAUF = 6


class Beispielserver:
    """Liefert Beispielseite und Preisantworten aus den Fixtures, merkt jeden Abruf."""

    def __init__(self, status_seite: int = 200) -> None:
        self.status_seite = status_seite
        self.abrufe: list[str] = []
        self.preise = json.loads((FIXTURES / "beispiel_preise.json").read_text("utf-8"))
        self.seite = (FIXTURES / "beispiel_produktseite.html").read_text("utf-8")

    def __call__(self, route) -> None:
        teile = urlsplit(route.request.url)
        self.abrufe.append(f"{teile.path}?{teile.query}" if teile.query else teile.path)
        if teile.path == "/api/preis":
            frage = parse_qs(teile.query)
            schluessel = "|".join(
                frage.get(teil, [""])[0] for teil in ("speicher", "tarif", "laufzeit")
            )
            antwort = self.preise.get(schluessel)
            if antwort is None:
                route.fulfill(status=404, body="")
                return
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps(antwort)
            )
            return
        if teile.path == PRODUKTPFAD:
            gut = self.status_seite == 200
            route.fulfill(
                status=self.status_seite,
                content_type="text/html; charset=utf-8",
                body=self.seite if gut else CHALLENGE,
            )
            return
        route.fulfill(status=404, body="")


class Mitschreiber:
    """Reicht an die echte Schleuse weiter und merkt jede Adresse davor."""

    def __init__(self, innen) -> None:
        self.innen = innen
        self.adressen: list[str] = []

    def passiere(self, url: str) -> None:
        self.adressen.append(url)
        self.innen.passiere(url)


def _hole(robots: str):
    def hole(url: str) -> tuple[int, str]:
        return (200, robots) if urlsplit(url).hostname == HOST else (404, "")

    return hole


def _karte(**ersetzt):
    from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten

    daten = yaml.safe_load((FIXTURES / "beispiel_karte.yaml").read_text("utf-8"))
    for pfad, wert in ersetzt.items():
        *weg, letztes = pfad.split("__")
        knoten = daten
        for teil in weg:
            knoten = knoten[teil]
        knoten[letztes] = wert
    return klickkarte_aus_daten(daten, "Beispielkarte")


def _laufe(kontext, *, karte=None, robots=ROBOTS, status_seite=200, **weiter):
    from telco_radar.collect.geraete import Abrufschleuse
    from telco_radar.collect.geraete.klickcrawler import klicke_durch

    server = Beispielserver(status_seite)
    seite = kontext.new_page()
    seite.route(f"https://{HOST}/**", server)
    waechter = RobotsWaechter(hole=_hole(robots))
    schleuse = Mitschreiber(Abrufschleuse(waechter, lambda: JETZT))
    weiter.setdefault("frist_ms", FRIST_MS)
    lauf = klicke_durch(
        seite,
        ADRESSE,
        karte or _karte(),
        waechter,
        lambda: JETZT,
        schleuse=schleuse,
        **weiter,
    )
    seite.close()
    return lauf, server, schleuse


@pytest.fixture(scope="module")
def kontext(chromium):
    """Ein Browserkontext je Modul und Worker; jeder Lauf öffnet eine eigene Seite."""
    kontext = chromium.new_context(viewport={"width": 1280, "height": 900})
    yield kontext
    kontext.close()


@pytest.fixture(scope="module")
def volllauf(kontext):
    """Der volle Lauf über die Beispielseite, einmal je Modul und Worker."""
    gemerkt: dict = {}

    def hole():
        if "lauf" not in gemerkt:
            gemerkt["lauf"] = _laufe(kontext)
        return gemerkt["lauf"]

    return hole


def _je_variante(lauf) -> dict:
    return {
        (e.variante.speicher, e.variante.tarif, e.variante.laufzeit): e
        for e in lauf.ergebnisse
    }


def test_jede_kombination_hat_ein_ergebnis(volllauf):
    lauf, _, _ = volllauf()

    assert lauf.status == "gelesen"
    assert lauf.grund is None
    assert lauf.http_status == 200
    assert {v: e.status for v, e in _je_variante(lauf).items()} == ERWARTET


def test_erfasste_werte_stimmen_mit_der_antwort(volllauf):
    from telco_radar.tarif_model import Preisphase

    lauf, _, _ = volllauf()
    ergebnis = _je_variante(lauf)

    gross = ergebnis[("256", "S", 24)]
    assert gross.befunde == ()
    assert gross.werte.anzahlung == 1099.0
    assert gross.werte.rate == 25.0
    assert gross.werte.ratenzahl == 24
    assert gross.werte.tarifphasen == (
        Preisphase(1, 24, 29.99),
        Preisphase(25, None, 34.99),
    )
    assert gross.werte.tarifbindung == 24
    assert gross.werte.anschluss == 39.99
    assert gross.werte.volumen_gb == 25.0
    assert "speicher=256&tarif=S&laufzeit=24" in gross.antwort_url

    lang = ergebnis[("128", "M", 36)]
    assert (lang.werte.rate, lang.werte.ratenzahl) == (12.5, 36)
    assert lang.werte.anschluss == 0.0
    assert lang.werte.volumen_gb == 1000.0


def test_online_rabatt_ohne_echo_wird_befund(volllauf):
    lauf, _, _ = volllauf()

    befund = _je_variante(lauf)[("256", "M", 36)]

    assert [b.feld for b in befund.befunde] == ["rate"]
    assert "15,00" in befund.befunde[0].grund
    assert "16,00" in befund.befunde[0].grund
    assert befund.werte.rate is None
    assert befund.werte.anzahlung == 999.0


def test_nicht_angeboten_nennt_die_option(volllauf):
    lauf, _, _ = volllauf()

    ergebnis = _je_variante(lauf)[("128", "S", 36)]

    assert ergebnis.grund is not None
    assert "36" in ergebnis.grund
    assert ergebnis.screenshot_png is None
    assert ergebnis.werte.rate is None


def test_screenshot_des_preisbereichs_je_gelesener_kombination(volllauf):
    lauf, _, _ = volllauf()

    gelesen = [e for e in lauf.ergebnisse if e.status in ("erfasst", "befund")]

    assert len(gelesen) == 6
    assert all(e.screenshot_png[:8] == b"\x89PNG\r\n\x1a\n" for e in gelesen)


def test_jeder_klick_geht_durch_die_schleuse(volllauf):
    _, server, schleuse = volllauf()

    assert schleuse.adressen == [ADRESSE] * (1 + KLICKS_IM_VOLLLAUF)
    preisabrufe = [a for a in server.abrufe if a.startswith("/api/preis")]
    assert len(preisabrufe) == 1 + KLICKS_IM_VOLLLAUF


def test_robots_gesperrte_anfragen_gehen_nicht_hinaus(volllauf):
    lauf, server, _ = volllauf()

    assert len(lauf.verworfen) == 1 + KLICKS_IM_VOLLLAUF
    assert all("/privat/json/zaehler" in v.url for v in lauf.verworfen)
    assert all("per robots.txt gesperrt" in v.grund for v in lauf.verworfen)
    assert not [a for a in server.abrufe if a.startswith("/privat/")]


def test_strukturwaechter_findet_alle_knoepfe_und_felder(volllauf):
    lauf, _, _ = volllauf()

    assert lauf.struktur.anteil_knoepfe == 1.0
    assert lauf.struktur.anteil_felder == 1.0
    assert lauf.struktur.felder_gesucht == 6 * 7


def test_fehlende_knoepfe_heissen_nicht_erfasst_und_brechen_die_struktur(
    kontext, volllauf
):
    gut, _, _ = volllauf()
    karte = _karte(knoepfe__tarif={"selektor": "#gibt-es-nicht button"})

    lauf, server, _ = _laufe(kontext, karte=karte, vorlauf=gut.struktur)

    assert {e.status for e in lauf.ergebnisse} == {"nicht_erfasst"}
    assert len(lauf.ergebnisse) == 4
    assert all("tarif" in e.grund for e in lauf.ergebnisse)
    assert all(e.variante.tarif is None for e in lauf.ergebnisse)
    assert lauf.struktur.anteil_knoepfe < 0.5
    assert lauf.status == "gestoert"
    assert "Strukturbruch" in lauf.grund
    assert len([a for a in server.abrufe if a.startswith("/api/preis")]) == 1


@pytest.mark.parametrize("status", [202, 403, 429])
def test_challenge_oder_sperre_heisst_abruf_gestoert(kontext, status):
    lauf, server, schleuse = _laufe(kontext, status_seite=status)

    assert lauf.status == "gestoert"
    assert lauf.http_status == status
    assert str(status) in lauf.grund
    assert lauf.ergebnisse == []
    assert server.abrufe == [PRODUKTPFAD]
    assert schleuse.adressen == [ADRESSE]


def test_fehlender_kanarienwert_heisst_abruf_gestoert(kontext):
    karte = _karte(kanarie__enthaelt="Anderes Handy")

    lauf, _, schleuse = _laufe(kontext, karte=karte, frist_ms=KURZE_FRIST_MS)

    assert lauf.status == "gestoert"
    assert "Kanarienwert" in lauf.grund
    assert lauf.ergebnisse == []
    assert schleuse.adressen == [ADRESSE]


def test_robots_gesperrte_produktseite_wird_nicht_geladen(kontext):
    lauf, server, _ = _laufe(kontext, robots="User-agent: *\nDisallow: /handy/\n")

    assert lauf.status == "gesperrt"
    assert "per robots.txt gesperrt" in lauf.grund
    assert server.abrufe == []
    assert lauf.ergebnisse == []


def test_robots_gesperrte_preisantwort_beendet_den_lauf(kontext):
    robots = "User-agent: *\nDisallow: /api/\nDisallow: /privat/json/\n"

    lauf, server, _ = _laufe(kontext, robots=robots, frist_ms=KURZE_FRIST_MS)

    assert lauf.status == "gesperrt"
    assert "/api/preis" in lauf.grund
    assert not [a for a in server.abrufe if a.startswith("/api/")]
    assert lauf.ergebnisse == []


def test_strukturbilanz_ohne_suche_ist_unbekannt_nicht_null():
    from telco_radar.collect.geraete.klicklauf import Strukturbilanz

    leer = Strukturbilanz()

    assert leer.anteil_knoepfe is None
    assert leer.anteil_felder is None


@pytest.mark.parametrize(
    ("vorher", "jetzt", "bruch"),
    [
        ((10, 10, 70, 70), (10, 10, 70, 70), False),
        ((10, 10, 70, 70), (10, 9, 70, 60), False),
        ((10, 10, 70, 70), (10, 7, 70, 70), True),
        ((10, 10, 70, 70), (10, 10, 70, 40), True),
        ((0, 0, 0, 0), (10, 2, 70, 0), False),
    ],
)
def test_strukturbruch_ist_ein_sprung_gegen_den_vorlauf(vorher, jetzt, bruch):
    from telco_radar.collect.geraete.klicklauf import Strukturbilanz, strukturbruch

    grund = strukturbruch(Strukturbilanz(*jetzt), Strukturbilanz(*vorher))

    assert (grund is not None) is bruch
    if bruch:
        assert "Strukturbruch" in grund


@pytest.mark.parametrize(
    ("status", "gestoert"),
    [(200, False), (204, False), (202, True), (401, True), (403, True), (503, True)],
)
def test_abruf_gestoert_nach_http_status(status, gestoert):
    from telco_radar.collect.geraete.klicklauf import abruf_gestoert

    grund = abruf_gestoert(status)

    assert (grund is not None) is gestoert
    if gestoert:
        assert str(status) in grund
