"""Der Saturn-Adapter: Preis aus ld+json UND dem Apollo-Cache derselben
Markenseite.

Bauanleitung: `outputs/saturn-spike-2026-09-05.md` (Spike, kein
Produktionscode) und `scripts/spike_saturn_geraetepreis.py` (der
funktionierende Prototyp). Dieser Adapter ist die Produktivfassung.

JEDE GZIP-FIXTURE IST EIN GESPEICHERTER ECHTER ABRUF vom 05.09.2026 (siehe
`tests/fixtures/geraete/_herkunft.json` fuer URL, Status und SHA-256) - kein
Bau-Subagent hat sie erfunden oder inhaltlich veraendert (die Lehre vom
11.08.2026, CLAUDE.md §6: eine damals erfundene Fixture wurde erst durch
einen adversarischen Pruefdurchgang aufgedeckt).

Die kleinen, im Code stehenden JSON-Schnipsel weiter unten sind KEINE
Messungen und geben sich auch nicht als solche aus - sie stellen Randfaelle
nach (fehlendes Marktplatz-Feld, kaputtes JSON), die man an echten Daten
nicht zuverlaessig herbeimessen kann.
"""
import gzip
from datetime import datetime, timezone
from pathlib import Path

import pytest

from telco_radar.collect.geraete import ADAPTER, GeraeteAbrufFehler, sammle_anbieter
from telco_radar.collect.geraete import saturn
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import lade_farben, lade_katalog, lade_quellen
from telco_radar.geraete_model import farbe_aus_titel

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

_URL_17_PRO = "https://www.saturn.de/de/brand/apple/iphone/iphone-17-pro"
_URL_17 = "https://www.saturn.de/de/brand/apple/iphone/iphone-17"


def _gz(name: str) -> str:
    with gzip.open(_FIX / name, "rt", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def iphone17pro_html():
    return _gz("saturn_produkt_iphone17_pro.html.gz")


@pytest.fixture(scope="module")
def iphone17_html():
    return _gz("saturn_produkt_iphone17.html.gz")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(_WURZEL)


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


# ==========================================================================
# Die Markenseite ohne Marktplatz-Mix: vier Saturn-eigene Preise
# ==========================================================================

def test_iphone17pro_liefert_die_vier_saturn_eigenen_preise(iphone17pro_html):
    """Spike-Gegenprobe: Tiefblau 256 GB kostet 1.179,00 EUR, UVP-Streichpreis
    1.299,00 EUR (nicht Teil der Rueckgabe, siehe Modulkopf - kein Adapter
    liest bisher `uvp`). Vier Varianten insgesamt, alle Saturn-eigen."""
    saetze = saturn.lies(iphone17pro_html, _URL_17_PRO)
    assert len(saetze) == 4
    preise = {(s["titel"], s["preis"]) for s in saetze}
    assert ("APPLE iPhone 17 Pro 5G 256 GB Tiefblau Dual SIM", 1179.0) in preise
    assert ("APPLE iPhone 17 Pro 5G 256 GB Silber Dual SIM", 1179.0) in preise
    assert ("APPLE iPhone 17 Pro 5G 1 TB Tiefblau Dual SIM", 1589.0) in preise
    assert ("APPLE iPhone 17 Pro 5G 512 GB Silber Dual SIM", 1419.0) in preise
    for s in saetze:
        assert s["waehrung"] == "EUR"
        assert s["quelle"] == "saturn_brand"
        assert s["url"].startswith("https://www.saturn.de/de/product/_apple-iphone-17-pro")


def test_iphone17pro_jede_zeile_traegt_ihre_eigene_produktseite(iphone17pro_html):
    """Der Quelllink ist die PRODUKTSEITE der jeweiligen Variante, nicht die
    Markenseite - eine spezifischere Adresse fuer denselben Preis."""
    saetze = saturn.lies(iphone17pro_html, _URL_17_PRO)
    urls = {s["url"] for s in saetze}
    assert len(urls) == 4          # vier verschiedene Produktseiten
    assert _URL_17_PRO not in urls


# ==========================================================================
# Abnahmekriterium 2: der Marktplatz-Filter
# ==========================================================================

def test_iphone17_hat_zwoelf_gelistete_aber_nur_fuenf_saturn_eigene(iphone17_html):
    """Rohbefund vor dem Filter (Spike §1/§2): 12 Angebote insgesamt, 7
    davon Marktplatz-Drittanbieter (bis zu 2.036 EUR fuer dasselbe Geraet,
    das Saturn selbst fuer 939,99 EUR fuehrt)."""
    state = saturn._preloaded_state(iphone17_html)
    alle = saturn._preisfeatures(state)
    assert len(alle) == 12
    eigen = [f for f in alle if f["is_marketplace"] is False]
    fremd = [f for f in alle if f["is_marketplace"] is True]
    assert len(eigen) == 5
    assert len(fremd) == 7
    # Der teuerste Fremdanbieter (Media-Reich GmbH) - siehe Spike-Tabelle.
    assert any(f["amount"] == 2036.0 for f in fremd)


def test_iphone17_lies_verwirft_alle_marktplatz_angebote(iphone17_html):
    """Die Fixture, die Abnahmekriterium 2 verlangt: `is_marketplace: true`
    wird verworfen, `false` durchgelassen - hier an einer echten Seite mit
    beiden Faellen nebeneinander."""
    saetze = saturn.lies(iphone17_html, _URL_17)
    assert len(saetze) == 5
    preise = {s["preis"] for s in saetze}
    assert preise == {939.99}
    # Keiner der sieben bekannten Fremdanbieter-Preise darf durchrutschen.
    fremdpreise = {1084.06, 1142.41, 1319.37, 2036.0, 1095.0, 1102.0, 1080.0}
    assert not (preise & fremdpreise)


def test_marktplatz_feld_fehlt_faellt_ebenfalls_durch():
    """`isProductOfTypeMarketplace` fehlt in dieser Nutzlast ganz - `None`
    ist NICHT dasselbe wie `False` und gilt nicht als sicher (fail closed,
    siehe Modulkopf)."""
    html = (
        '<script>window.__PRELOADED_STATE__ = {"apolloState": {'
        '"CofrPriceFeature:{\\"id\\":\\"Saturn:de:999\\"}": '
        '{"id": "Saturn:de:999", "price": {"amount": 500.0}, '
        '"currency": "EUR"}, '
        '"GraphqlProduct:Saturn:de-DE:999": '
        '{"title": "APPLE iPhone 17 256 GB Schwarz Dual SIM", '
        '"url": "/de/product/x.html"}'
        '}};</script>')
    assert saturn.lies(html, _URL_17) == []


def test_dedupe_behaelt_den_eintrag_mit_ratenplan():
    """Dieselbe `product_id` unter zwei Apollo-Schluesseln (Spike §2b) - der
    vollstaendigere Eintrag (mit `installment`) gewinnt, keine zweite
    Preiszeile fuer dieselbe SKU."""
    ohne_raten = {"product_id": "42", "amount": 1179.0,
                  "installment_present": False, "apollo_key": "a"}
    mit_raten = {"product_id": "42", "amount": 1179.0,
                 "installment_present": True, "apollo_key": "b"}
    ergebnis = saturn._dedupe_by_product_id([ohne_raten, mit_raten])
    assert len(ergebnis) == 1
    assert ergebnis[0]["apollo_key"] == "b"
    # Reihenfolge darf das Ergebnis nicht aendern.
    ergebnis2 = saturn._dedupe_by_product_id([mit_raten, ohne_raten])
    assert len(ergebnis2) == 1
    assert ergebnis2[0]["apollo_key"] == "b"


# ==========================================================================
# Die Farbe: strukturiert aus dem Titel gelesen, nicht dem generischen
# Rueckfall ueberlassen
# ==========================================================================

def test_farbe_mit_umlaut_wird_richtig_gelesen(iphone17_html):
    """Regressionstest gegen einen echten Befund: der generische
    Titel-Rueckfall (`geraete_model.farbe_aus_titel`) findet "Weiss" NIE in
    einem Titel, der "Weiß" schreibt - er vergleicht ASCII-gefaltete
    Schreibweisen gegen den UNGEFALTETEN Titeltext. Dieser Adapter liest die
    Farbe deshalb selbst aus einer festen Position im Titel."""
    saetze = saturn.lies(iphone17_html, _URL_17)
    weiss = next(s for s in saetze if "Weiß" in s["titel"])
    assert weiss["farbe"] == "Weiß"
    # Der Befund, der die Sonderbehandlung rechtfertigt: der generische
    # Rueckfall waere hier leer ausgegangen.
    assert farbe_aus_titel(weiss["titel"], lade_farben(_WURZEL)) == ("", None)


def test_farbe_landet_als_kanonische_farbe_in_der_sku(katalog, farben):
    from telco_radar.geraete_model import lies_listung

    listung = lies_listung(
        titel="APPLE iPhone 17 5G 256 GB Weiß Dual SIM", anbieter="Saturn",
        anbieter_typ="handel", quelle_url="https://www.saturn.de/de/product/x.html",
        abgerufen_am="2026-09-05", katalog=katalog, farben=farben,
        confidence="hoch", farbe_roh="Weiß", preis_ohne_vertrag=939.99)
    assert listung is not None
    assert listung.farbe_normalisiert == "weiss"
    assert listung.sku_id == "apple-iphone-17-256gb-weiss"


# ==========================================================================
# Ehrliche Ausfaelle
# ==========================================================================

def test_ohne_preloaded_state_wirft():
    with pytest.raises(GeraeteAbrufFehler) as fehler:
        saturn.lies("<html><body>keine Nutzlast hier</body></html>", _URL_17)
    assert "PRELOADED_STATE" in str(fehler.value)


def test_leere_antwort_wirft():
    with pytest.raises(GeraeteAbrufFehler):
        saturn.lies("", _URL_17)


def test_kaputtes_zustandsobjekt_wirft():
    with pytest.raises(GeraeteAbrufFehler) as fehler:
        saturn.lies(
            "<script>window.__PRELOADED_STATE__ = {kaputt;</script>", _URL_17)
    assert "unlesbar" in str(fehler.value)


def test_leere_apollo_state_liefert_leere_liste_kein_fehler():
    """Die Messgrenze aus dem Bericht: sechs der 17 konfigurierten
    Markenseiten liefern strukturell einwandfrei, aber ohne eine einzige
    Saturn-eigene Listung (Stand 05.09.2026) - das ist ein leeres Ergebnis,
    kein Abruffehler."""
    html = ('<script>window.__PRELOADED_STATE__ = '
            '{"apolloState": {}};</script>')
    assert saturn.lies(html, _URL_17) == []


# ==========================================================================
# Der ganze Weg, mit der AUSGELIEFERTEN Konfiguration
# ==========================================================================

def test_landet_als_listung_im_bestand(katalog, farben, iphone17pro_html,
                                       iphone17_html):
    """Ein Lauf ueber zwei der 17 konfigurierten Markenseiten: neun
    Listungen (4 + 5), jede mit Preis, Beleglink und Abrufdatum."""
    anbieter = lade_quellen(_WURZEL).nach_name("Saturn")
    assert anbieter.aktiv and anbieter.methode == "saturn_brand"
    anbieter.einstiege = [e for e in anbieter.einstiege
                          if e.url in (_URL_17_PRO, _URL_17)]
    anbieter.rate_limit_sekunden = 0

    seiten = {_URL_17_PRO: iphone17pro_html, _URL_17: iphone17_html}
    gesehene_user_agents = []

    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /api/v1/msg\n")
        gesehene_user_agents.append(user_agent)
        return (200, seiten[url])

    bilanz = sammle_anbieter(anbieter, katalog, farben, hole, "2026-09-05",
                             RobotsWaechter(hole=hole),
                             datetime(2026, 9, 5, 12, tzinfo=timezone.utc))
    assert bilanz.status == "ok"
    assert bilanz.gelesene_einstiege == {_URL_17_PRO, _URL_17}
    assert len(bilanz.listungen) == 9
    treffer = next(l for l in bilanz.listungen
                  if l.sku_id == "apple-iphone-17-pro-256gb-tiefblau")
    assert treffer.preis_ohne_vertrag == 1179.0
    assert treffer.anbieter == "Saturn"
    assert treffer.confidence == "hoch"
    assert treffer.abgerufen_am == "2026-09-05"
    assert treffer.quelle_url.startswith("https://www.saturn.de/de/product/")
    # R2-Regressionstest (EVAL_saturn-adapter-r1.md Befund 1): der
    # Anbieter reicht seine ehrliche Kennung an JEDEN Markenseiten-Abruf
    # weiter - unabhaengig davon, was `http_cfg` global traegt (das ist
    # hier `hole()`s Sache, siehe test_saturn_ua_ist_primary_auch_bei_
    # globaler_chrome_konfiguration unten fuer die Kopfzeilenprobe).
    assert gesehene_user_agents == [
        "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"] * 2


def test_ist_direkt_und_ohne_ernte_registriert():
    """Die Markenseite IST die Nutzlast - keine Produktseite wird
    nachgeladen, kein separates `ernte` noetig."""
    adapter = ADAPTER["saturn_brand"]
    assert adapter.direkt is True
    assert adapter.lies is saturn.lies
    assert adapter.confidence == "hoch"


def test_die_ausgelieferte_konfiguration_haelt_was_der_hinweis_verspricht():
    anbieter = lade_quellen(_WURZEL).nach_name("Saturn")
    assert anbieter.aktiv is True
    assert anbieter.crawlbar is True
    assert anbieter.methode == "saturn_brand"
    assert anbieter.grund == ""
    assert "05.09.2026" in anbieter.hinweis
    assert "isProductOfTypeMarketplace" in anbieter.hinweis
    # R2 (EVAL_saturn-adapter-r1.md Befund 1): die ausgelieferte
    # Konfiguration traegt die per-Anbieter-Kennung, unabhaengig davon, was
    # config/settings.yaml global sagt.
    assert anbieter.user_agent == \
        "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
    # Start-Scope laut Auftrag: alle Apple-iPhone-Serien des Katalogs.
    assert len(anbieter.einstiege) == 17
    assert all("/de/brand/apple/iphone/" in e.url for e in anbieter.einstiege)


# ==========================================================================
# R2: die ehrliche Kennung als PRIMARY - der belegte UA auf Kopfzeilenebene
# ==========================================================================
# EVAL_saturn-adapter-r1.md Befund 1 (Schwere 1): R1 behauptete im Bericht,
# `collect.http.fetch` sende `TelcoRadar/1.0 (+https://telco-radar.
# onrender.com/ueber)` - tatsaechlich ging als PRIMARY die volle
# Chrome-Vortaeuschung aus config/settings.yaml:549 hinaus, weil der Adapter
# das globale `http_cfg` unveraendert benutzte. Diese Tests messen die
# WIRKLICH GESENDETE Kopfzeile auf httpx-Ebene, nicht nur, was der Code
# behauptet zu tun - genau der Punkt, an dem R1 widerlegt wurde.

_CHROME_UA_R1 = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_EHRLICHE_UA = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"


def _fake_response(status_code=200, text="<html></html>"):
    import httpx as _httpx

    request = _httpx.Request("GET", "https://www.saturn.de/de/brand/apple/iphone/iphone-17")
    response = _httpx.Response(status_code, text=text, request=request)
    return response


def test_saturn_ua_ist_primary_auch_bei_globaler_chrome_konfiguration(monkeypatch):
    """Genau der R1-Fall: `http_cfg` traegt global die Chrome-Kennung aus
    config/settings.yaml (hier nachgebaut, nicht die Datei selbst, damit der
    Test nicht an ihr haengt) - und trotzdem muss die ERSTE (Primary)
    ausgehende Kopfzeile fuer Saturn die Brief-UA-Zeichenkette tragen."""
    import httpx

    from telco_radar.geraete_pipeline import _hole_fabrik

    gesehene_kopfzeilen = []

    def fake_get(url, timeout=None, headers=None, follow_redirects=None,
                verify=None):
        gesehene_kopfzeilen.append(dict(headers or {}))
        return _fake_response()

    monkeypatch.setattr(httpx, "get", fake_get)

    # Das globale http_cfg, wie es aus config/settings.yaml kommt - Chrome,
    # exakt der Wert, den der Evaluator gegen R1 nachgemessen hat.
    http_cfg = {"user_agent": _CHROME_UA_R1}
    hole = _hole_fabrik(http_cfg)

    status, _text = hole(
        "https://www.saturn.de/de/brand/apple/iphone/iphone-17",
        user_agent=_EHRLICHE_UA)

    assert status == 200
    assert len(gesehene_kopfzeilen) == 1, \
        "ein 200er darf keinen zweiten (Fallback-)Versuch ausloesen"
    primary_header = gesehene_kopfzeilen[0]["User-Agent"]
    assert primary_header == _EHRLICHE_UA
    assert primary_header != _CHROME_UA_R1


def test_ohne_per_anbieter_override_bleibt_das_globale_http_cfg_primary(monkeypatch):
    """Gegenprobe: OHNE `user_agent`-Override (jeder andere Anbieter) sendet
    `hole()` weiterhin genau das globale `http_cfg` als Primary - die
    Fallback-Architektur ist unangetastet, nur Saturn bekommt die
    Ausnahme."""
    import httpx

    from telco_radar.geraete_pipeline import _hole_fabrik

    gesehene_kopfzeilen = []

    def fake_get(url, timeout=None, headers=None, follow_redirects=None,
                verify=None):
        gesehene_kopfzeilen.append(dict(headers or {}))
        return _fake_response()

    monkeypatch.setattr(httpx, "get", fake_get)

    http_cfg = {"user_agent": _CHROME_UA_R1}
    hole = _hole_fabrik(http_cfg)

    status, _text = hole("https://www.example.de/irgendeine-produktseite")

    assert status == 200
    assert gesehene_kopfzeilen[0]["User-Agent"] == _CHROME_UA_R1


def test_saturn_anbieter_reicht_seine_ehrliche_kennung_bis_zur_kopfzeile(monkeypatch):
    """Der ganze Weg von der ausgelieferten Konfiguration bis zur
    httpx-Kopfzeile, ohne Testattrappe dazwischen: `sammle_anbieter` mit dem
    ECHTEN Saturn-Anbieter und dem ECHTEN `_hole_fabrik(http_cfg)` - das
    globale `http_cfg` traegt Chrome (der R1-Fall), die Markenseite
    antwortet trotzdem mit der ehrlichen Kennung als Primary."""
    import httpx

    from telco_radar.geraete_config import lade_quellen
    from telco_radar.geraete_pipeline import _hole_fabrik

    anbieter = lade_quellen(_WURZEL).nach_name("Saturn")
    anbieter.einstiege = [e for e in anbieter.einstiege if e.url == _URL_17]
    anbieter.rate_limit_sekunden = 0

    gesehene_kopfzeilen = []

    def fake_get(url, timeout=None, headers=None, follow_redirects=None,
                verify=None):
        gesehene_kopfzeilen.append(dict(headers or {}))
        if url.endswith("/robots.txt"):
            return _fake_response(200, "User-agent: *\nDisallow: /api/v1/msg\n")
        return _fake_response(200, ('<script>window.__PRELOADED_STATE__ = '
                                    '{"apolloState": {}};</script>'))

    monkeypatch.setattr(httpx, "get", fake_get)

    hole = _hole_fabrik({"user_agent": _CHROME_UA_R1})
    bilanz = sammle_anbieter(anbieter, katalog=None, farben={}, hole=hole,
                             heute="2026-09-05",
                             waechter=RobotsWaechter(hole=hole),
                             jetzt=datetime(2026, 9, 5, 12, tzinfo=timezone.utc))

    assert bilanz.status == "leer"          # leere Apollo-State, kein Fehler
    assert len(gesehene_kopfzeilen) == 2    # robots.txt + eine Markenseite
    # Robots.txt-Abruf UND Markenseiten-Abruf: robots.txt geht ueber die
    # unveraenderte, globale Konfiguration (Chrome bleibt dort Primary -
    # dieselbe Bewusstheit wie bei `kopfzeilen`, siehe Modulkopf von
    # `collect/geraete/__init__.py`), die Markenseite bekommt die ehrliche
    # Kennung.
    assert gesehene_kopfzeilen[0]["User-Agent"] == _CHROME_UA_R1   # robots.txt
    assert gesehene_kopfzeilen[1]["User-Agent"] == _EHRLICHE_UA    # Markenseite
