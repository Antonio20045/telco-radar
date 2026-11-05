"""Der MediaMarkt-Adapter: derselbe Ceconomy-Lesekern wie Saturn
(`ceconomy.py`), anderer Cache-Praefix ("Media" statt "Saturn").

Auftrag: `brief-mediamarkt-0511.md` (05.11.2026). JEDE GZIP-FIXTURE IST EIN
GESPEICHERTER ECHTER ABRUF vom 04.11.2026 (siehe
`tests/fixtures/geraete/_herkunft.json` fuer URL, Status und SHA-256,
Herkunft `arbeit/haendler-weg-0411.md`) - kein Bau-Subagent hat sie erfunden
oder inhaltlich veraendert.

Zwei Fixtures, zwei Rollen:
  - `mediamarkt_produkt_samsung_a57.html.gz` ist NICHT der konfigurierte
    Einstieg (der ist die Kampagnenseite), sondern der Beleg fuer
    Abnahmekriterium 1: eine echte Seite, auf der Marktplatzangebote
    NEBEN MediaMarkt-eigenen Angeboten stehen - genau das verlangt der
    Brief als Fixture fuer den Marktplatz-Pflichttest. `lies()` kennt
    keinen Unterschied zwischen Kampagnen- und Produktseite.
  - `mediamarkt_angebote_smartphones.html.gz` IST der konfigurierte
    Einstieg (`direkt=True`) - der Beleg, dass die Produktivkonfiguration
    end-to-end funktioniert.
"""

import gzip
from datetime import UTC, datetime
from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete import (
    ADAPTER,
    GeraeteAbrufFehler,
    mediamarkt,
    sammle_anbieter,
)
from telco_radar.collect.geraete.robots import RobotsWaechter, lies_robots
from telco_radar.geraete_config import lade_farben, lade_katalog, lade_quellen

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

_URL_PRODUKT = (
    "https://www.mediamarkt.de/de/product/"
    "_samsung-galaxy-a57-256-gb-awesome-gray-dual-sim-3039261.html"
)
_URL_ANGEBOTE = "https://www.mediamarkt.de/de/campaign/angebote-smartphones"
_EHRLICHE_UA = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"


def _gz(name: str) -> str:
    with gzip.open(_FIX / name, "rt", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def produkt_html():
    return _gz("mediamarkt_produkt_samsung_a57.html.gz")


@pytest.fixture(scope="module")
def angebote_html():
    return _gz("mediamarkt_angebote_smartphones.html.gz")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


def test_produktseite_hat_fremd_und_eigene_angebote_nebeneinander(produkt_html):
    """Der Rohbefund vor dem Filter: MediaMarkt-eigene UND
    Fremdanbieter-Angebote fuer dasselbe Geraet in derselben Antwort -
    genau die Lage, die Abnahmekriterium 1 als Beleg verlangt."""
    from telco_radar.collect.geraete import ceconomy

    state = ceconomy.preloaded_state(produkt_html, "MediaMarkt")
    alle = ceconomy.preisfeatures(state, "Media")
    eigen = [f for f in alle if f["is_marketplace"] is False]
    fremd = [f for f in alle if f["is_marketplace"] is True]
    unklar = [f for f in alle if f["is_marketplace"] is None]
    assert len(fremd) == 5
    assert len(eigen) == 16
    assert len(unklar) == 1, "ein Tenant-fremder Eintrag ohne das Feld - fail closed"
    assert any(f["amount"] == 445.74 for f in fremd)


def test_produktseite_lies_verwirft_alle_marktplatz_angebote(produkt_html):
    """Abnahmekriterium 1: `isProductOfTypeMarketplace == true` faellt
    heraus, `== false` bleibt - an einer echten Seite mit beiden Faellen."""
    saetze = mediamarkt.lies(produkt_html, _URL_PRODUKT)
    assert len(saetze) == 11
    preise = {s["preis"] for s in saetze}
    fremdpreise = {436.91, 370.49, 350.99, 445.74}
    assert not (preise & fremdpreise)
    telefon = next(s for s in saetze if s["sku"] == "3039261")
    assert telefon["titel"] == "SAMSUNG Galaxy A57 256 GB Awesome Gray Dual SIM"
    assert telefon["preis"] == 389.99
    assert telefon["waehrung"] == "EUR"
    assert telefon["quelle"] == "mediamarkt_angebote"
    assert telefon["url"] == _URL_PRODUKT


def test_marktplatz_feld_fehlt_faellt_ebenfalls_durch():
    """`isProductOfTypeMarketplace` fehlt in dieser Nutzlast ganz - `None`
    ist NICHT dasselbe wie `False` (fail closed, wie bei Saturn)."""
    html = (
        '<script>window.__PRELOADED_STATE__ = {"apolloState": {'
        '"CofrPriceFeature:{\\"id\\":\\"Media:de:999\\"}": '
        '{"id": "Media:de:999", "price": {"amount": 500.0}, '
        '"currency": "EUR"}, '
        '"GraphqlProduct:Media:de-DE:999": '
        '{"title": "SAMSUNG Galaxy S25 256 GB Schwarz Dual SIM", '
        '"url": "/de/product/x.html"}'
        "}};</script>"
    )
    assert mediamarkt.lies(html, _URL_ANGEBOTE) == []


def test_angebotsseite_liest_zwoelf_preisfelder_direkt(angebote_html):
    """Der konfigurierte Produktiv-Einstieg: die Kampagnenseite ist bereits
    ihre eigene Nutzlast (`direkt=True`), kein Nachladen einer Produktseite."""
    saetze = mediamarkt.lies(angebote_html, _URL_ANGEBOTE)
    assert len(saetze) == 12
    telefon = next(s for s in saetze if s["sku"] == "3039261")
    assert telefon["titel"] == "SAMSUNG Galaxy A57 256 GB Awesome Gray Dual SIM"
    assert telefon["preis"] == 389.99
    for s in saetze:
        assert s["waehrung"] == "EUR"
        assert s["quelle"] == "mediamarkt_angebote"


def test_ohne_preloaded_state_wirft():
    with pytest.raises(GeraeteAbrufFehler) as fehler:
        mediamarkt.lies("<html><body>keine Nutzlast hier</body></html>", _URL_ANGEBOTE)
    assert "PRELOADED_STATE" in str(fehler.value)
    assert "MediaMarkt" in str(fehler.value)


def test_leere_apollo_state_liefert_leere_liste_kein_fehler():
    html = '<script>window.__PRELOADED_STATE__ = {"apolloState": {}};</script>'
    assert mediamarkt.lies(html, _URL_ANGEBOTE) == []


def test_ist_direkt_und_ohne_ernte_registriert():
    adapter = ADAPTER["mediamarkt_angebote"]
    assert adapter.direkt is True
    assert adapter.lies is mediamarkt.lies
    assert adapter.confidence == "hoch"


def test_die_ausgelieferte_konfiguration_haelt_was_der_hinweis_verspricht():
    anbieter = lade_quellen(_WURZEL).nach_name("MediaMarkt")
    assert anbieter.aktiv is True
    assert anbieter.crawlbar is True
    assert anbieter.methode == "mediamarkt_angebote"
    assert anbieter.grund == ""
    assert "05.11.2026" in anbieter.hinweis
    assert "isProductOfTypeMarketplace" in anbieter.hinweis
    assert anbieter.user_agent == _EHRLICHE_UA
    assert anbieter.rate_limit_sekunden >= 10
    assert len(anbieter.einstiege) == 1
    assert anbieter.einstiege[0].url == _URL_ANGEBOTE


def test_konfigurierter_einstieg_ist_nach_robots_erlaubt():
    """Abnahmekriterium 2: die Einstiegsseite gegen die gesicherte, echte
    robots.txt von MediaMarkt (Abruf 04.11.2026, Gruppe `User-agent: *`)."""
    robots_text = (_FIX / "mediamarkt_robots.txt").read_text(encoding="utf-8")
    regeln = lies_robots(robots_text)
    anbieter = lade_quellen(_WURZEL).nach_name("MediaMarkt")
    for einstieg in anbieter.einstiege:
        assert regeln.erlaubt(einstieg.url), einstieg.url
    assert regeln.erlaubt("https://www.mediamarkt.de/de/product/irgendein-handy.html")


def test_landet_als_listung_im_bestand(katalog, farben, angebote_html):
    anbieter = lade_quellen(_WURZEL).nach_name("MediaMarkt")
    anbieter.rate_limit_sekunden = 0

    gesehene_user_agents = []

    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /api/v1/msg\n")
        gesehene_user_agents.append(user_agent)
        return (200, angebote_html)

    bilanz = sammle_anbieter(
        anbieter,
        katalog,
        farben,
        hole,
        "2026-11-05",
        RobotsWaechter(hole=hole),
        datetime(2026, 11, 5, 12, tzinfo=UTC),
    )
    assert bilanz.status == "ok"
    assert bilanz.gelesene_einstiege == {_URL_ANGEBOTE}
    treffer = next(
        listung
        for listung in bilanz.listungen
        if listung.sku_id == "samsung-galaxy-a57-256gb-awesome-gray"
    )
    assert treffer.preis_ohne_vertrag == 389.99
    assert treffer.anbieter == "MediaMarkt"
    assert treffer.abgerufen_am == "2026-11-05"
    assert gesehene_user_agents == [_EHRLICHE_UA]


def test_schutzantwort_bricht_still_ab_ohne_wiederholung(katalog, farben):
    """Abnahmekriterium 3: ein 403 fuehrt zu genau EINEM Abruf (kein
    Wiederholen, kein anderer Absender), der Anbieter gilt als
    fehlgeschlagen, es wird keine Ausnahme nach aussen geworfen."""
    anbieter = lade_quellen(_WURZEL).nach_name("MediaMarkt")
    anbieter.rate_limit_sekunden = 0

    versuche = []

    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /api/v1/msg\n")
        versuche.append((url, user_agent))
        return (403, "<html>Schutzseite</html>")

    bilanz = sammle_anbieter(
        anbieter,
        katalog,
        farben,
        hole,
        "2026-11-05",
        RobotsWaechter(hole=hole),
        datetime(2026, 11, 5, 12, tzinfo=UTC),
    )
    assert bilanz.status in ("leer", "fehler")
    assert bilanz.listungen == []
    assert len(versuche) == 1, "ein 403 darf keinen zweiten Versuch ausloesen"
    assert versuche[0][1] == _EHRLICHE_UA, (
        "kein Wechsel des Absenders bei Schutzantwort"
    )
