"""Der Abnahme-Check muss selbst geprueft sein.

Er ist die einzige Instanz, die im Quellen-Ausbau "ja" sagen darf. Ein Fehler
hier laesst genau die Quellen durch, gegen die er gebaut wurde: die, die ueber
den echten Collector 0 Meldungen liefern, undatiert sind oder in Wahrheit
Navigationslabels als "Ueberschriften" ausgeben.

Kein Netz noetig - collect_source wird ersetzt.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from telco_radar.models import Item

_PFAD = Path(__file__).resolve().parents[1] / "scripts" / "pruefe_quellenvorschlag.py"
_spec = importlib.util.spec_from_file_location("pruefe_quellenvorschlag", _PFAD)
pq = importlib.util.module_from_spec(_spec)
sys.modules["pruefe_quellenvorschlag"] = pq
_spec.loader.exec_module(pq)


class FakeBestand:
    """Ein Bestand ohne Config und ohne Netz."""

    def __init__(self, bekannt: dict | None = None, je_operator: dict | None = None,
                 item_index: dict | None = None):
        self.http_cfg: dict = {}
        self.lookback = 8
        self._bekannt = bekannt or {}
        self.je_operator = je_operator or {}
        # Meldungs-URL -> Quelle. Seit dem Massenbetrieb wird die
        # Inhaltsdublette gegen diesen einmal aufgebauten Index geprueft,
        # nicht mehr gegen Live-Abrufe je Kandidat.
        self.item_index = item_index or {}

    def kennt(self, url: str) -> str:
        return self._bekannt.get(url, "")


def _items(n: int, *, datiert: int | None = None, frisch: int = 3,
           titel: str = "Betreiber startet neuen Tarif mit 50 GB Datenvolumen"):
    """n Meldungen, davon `datiert` mit Datum und `frisch` im Fenster."""
    datiert = n if datiert is None else datiert
    jetzt = datetime.now(timezone.utc)
    out = []
    for i in range(n):
        if i < frisch:
            pub = jetzt - timedelta(days=1)
        elif i < datiert:
            pub = jetzt - timedelta(days=200)
        else:
            pub = None
        out.append(Item(title=f"{titel} Nr. {i}", url=f"https://example.com/a{i}",
                        source_name="X", published=pub))
    return out


def _pruefe(kand: pq.Kandidat, items, bestand=None, overlap=False,
            zweimal=False, zweite=None):
    """`zweite` erlaubt es, dem zweiten Abruf ein ANDERES Ergebnis zu geben -
    genau der Fall, den Kriterium 1b faengt."""
    original = pq.collect_source
    antworten = [items] if zweite is None else [items, zweite]

    def fake(*a, **k):
        return antworten.pop(0) if len(antworten) > 1 else antworten[0]

    pq.collect_source = fake
    try:
        return pq._pruefe_einen(kand, bestand or FakeBestand(), 8, overlap,
                                zweimal)
    finally:
        pq.collect_source = original


def test_wechselhafte_quelle_faellt_beim_zweiten_abruf_durch():
    """newswire.ca, 04.08.2026: erster Abruf 23 von 23 datiert, zweiter Abruf
    30 Meldungen ganz ohne Datum. Ein Check, der nur einmal hinsieht, laesst
    so etwas durch - und undatierte Meldungen liest kein Analyst je."""
    k = pq.Kandidat(url="https://example.com/presse", type="newsroom",
                    operator="Beispiel", website="example.com")
    gut = _items(23)
    schlecht = _items(30, datiert=0, frisch=0)
    b = _pruefe(k, gut, zweimal=True, zweite=schlecht)
    assert not b.bestanden
    assert not _grund(b, 1, "zweiter Abruf")["ok"]
    # Ohne den zweiten Abruf haette dieselbe Quelle bestanden.
    assert _pruefe(k, gut).bestanden


def test_stabile_quelle_besteht_auch_den_zweiten_abruf():
    k = pq.Kandidat(url="https://example.com/presse", type="newsroom",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, _items(23), zweimal=True, zweite=_items(23))
    assert b.bestanden, b.durchgefallen


def test_zweiter_abruf_gilt_nur_fuer_geparste_seiten():
    """Ein RSS-Feed hat das Problem nicht - der doppelte Abruf waere nur
    doppelte Last."""
    k = pq.Kandidat(url="https://example.com/feed", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, _items(12), zweimal=True)
    assert b.bestanden
    assert not [x for x in b.kriterien if "zweiter Abruf" in x["name"]]


def _grund(befund, nr, name_enthaelt=""):
    """Kriterium 7 wird zweimal geprueft (URL-Dublette und Inhaltsdublette) -
    deshalb optional zusaetzlich nach dem Namen filtern."""
    treffer = [k for k in befund.kriterien if k["nr"] == nr
               and name_enthaelt in k["name"]]
    assert treffer, f"Kriterium {nr} ({name_enthaelt!r}) wurde nicht geprueft"
    return treffer[0]


# ------------------------------------------------------------------ Kriterien
def test_gute_quelle_besteht():
    k = pq.Kandidat(url="https://example.com/feed", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, _items(12))
    assert b.bestanden, b.durchgefallen
    assert (b.n_items, b.n_datiert, b.n_frisch) == (12, 12, 3)
    assert len(b.titelprobe) == 3


def test_zu_wenige_meldungen_fallen_durch():
    k = pq.Kandidat(url="https://example.com/feed", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, _items(4))
    assert not b.bestanden
    assert not _grund(b, 2)["ok"]


def test_undatierte_meldungen_fallen_durch():
    """Kriterium 3: undatiert sortiert ans Ende und ist faktisch unsichtbar."""
    k = pq.Kandidat(url="https://example.com/feed", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, _items(10, datiert=7))
    assert not b.bestanden
    assert "7/10" in _grund(b, 3)["detail"]


def test_keine_frische_meldung_faellt_durch_ohne_ausnahme():
    k = pq.Kandidat(url="https://example.com/feed", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, _items(10, frisch=0))
    assert not b.bestanden
    assert not _grund(b, 4)["ok"]


def test_belegte_ausnahme_ersetzt_die_frische():
    k = pq.Kandidat(url="https://example.com/ir", type="rss",
                    operator="Beispiel", website="example.com",
                    ausnahme_frische="IR-Seite, publiziert quartalsweise")
    b = _pruefe(k, _items(10, frisch=0))
    assert b.bestanden, b.durchgefallen
    assert "quartalsweise" in _grund(b, 4)["detail"]


def test_navigationslabels_fallen_durch():
    k = pq.Kandidat(url="https://example.com/presse", type="newsroom",
                    operator="Beispiel", website="example.com")
    nav = [Item(title=t, url=f"https://example.com/n{i}", source_name="X",
                published=datetime.now(timezone.utc))
           for i, t in enumerate(
               ["Mehr erfahren", "Presse", "12.03.2026", "Alle anzeigen",
                "Kontakt", "Datenschutz",
                "Betreiber startet neuen Tarif mit 50 GB Datenvolumen"])]
    b = _pruefe(k, nav)
    assert not b.bestanden
    assert not _grund(b, 5)["ok"]


def test_identische_titel_fallen_durch():
    """Gemessen am SEC-EDGAR-Feed von AT&T: 40 sauber datierte Meldungen,
    alle mit dem Titel "8-K - Current report". Technisch tadellos, inhaltlich
    wertlos - und die Navigationslabel-Regel greift dort nicht."""
    k = pq.Kandidat(url="https://www.sec.gov/edgar", type="rss",
                    operator="Beispiel", website="example.com",
                    ausnahme_domain="SEC EDGAR")
    from datetime import datetime, timezone
    formulare = [Item(title="8-K - Current report",
                      url=f"https://www.sec.gov/e{i}", source_name="X",
                      published=datetime.now(timezone.utc)) for i in range(20)]
    b = _pruefe(k, formulare)
    assert not b.bestanden
    assert not _grund(b, 5, "unterscheidbar")["ok"]
    # Als Navigationslabel gilt so ein Titel gerade NICHT - genau die Luecke,
    # die dieser Check schliesst.
    assert _grund(b, 5, "echte")["ok"]


def test_fremde_domain_faellt_durch_ohne_ausnahme():
    k = pq.Kandidat(url="https://news.cision.com/beispiel", type="newsroom",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, _items(12))
    assert not b.bestanden
    assert not _grund(b, 6)["ok"]


def test_verbreitungsdienst_mit_begruendung_ist_erlaubt():
    k = pq.Kandidat(url="https://news.cision.com/beispiel", type="newsroom",
                    operator="Beispiel", website="example.com",
                    ausnahme_domain="Cision ist der offizielle Verbreitungsweg")
    b = _pruefe(k, _items(12))
    assert b.bestanden, b.durchgefallen


def test_bekannte_url_ist_eine_dublette():
    bestand = FakeBestand(bekannt={"https://example.com/feed": "Beispiel (rss)"})
    k = pq.Kandidat(url="https://example.com/feed", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, _items(12), bestand)
    assert not b.bestanden
    assert not _grund(b, 7)["ok"]
    # Bei einer Dublette wird gar nicht erst abgerufen.
    assert b.n_items == 0


def test_inhaltsdublette_wird_erkannt():
    """Zwei Pfade derselben Seite sind EINE Quelle, nicht zwei."""
    from telco_radar.models import normalize_url
    gleiche = _items(10)
    bestand = FakeBestand(item_index={
        normalize_url(i.url): "Beispiel (https://example.com/alt)"
        for i in gleiche})
    k = pq.Kandidat(url="https://example.com/neu", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, gleiche, bestand, overlap=True)
    assert not b.bestanden
    assert "100%" in _grund(b, 7, "Inhaltsdublette")["detail"]


def test_inhaltsdublette_greift_auch_ueber_betreiber_hinweg():
    """Die alte Pruefung sah nur Quellen DESSELBEN Betreibers - dieselbe
    Landesgesellschaft unter anderem Namen fiel damit durchs Raster."""
    from telco_radar.models import normalize_url
    gleiche = _items(10)
    bestand = FakeBestand(item_index={
        normalize_url(i.url): "Ganz anderer Betreiber" for i in gleiche})
    k = pq.Kandidat(url="https://example.com/neu", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, gleiche, bestand, overlap=True)
    assert not b.bestanden


def test_teilweise_ueberschneidung_ist_noch_keine_dublette():
    from telco_radar.models import normalize_url
    eigene = _items(10)
    bestand = FakeBestand(item_index={
        normalize_url(i.url): "Bestand" for i in eigene[:3]})
    k = pq.Kandidat(url="https://example.com/neu", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, eigene, bestand, overlap=True)
    assert b.bestanden, b.durchgefallen


def test_newsroom_js_ist_nicht_abnehmbar():
    k = pq.Kandidat(url="https://example.com/news", type="newsroom_js",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, _items(30))
    assert not b.bestanden
    assert not _grund(b, 8)["ok"]
    assert b.n_items == 0  # kein Abruf


def test_abrufsfehler_wird_als_fehler_gemeldet():
    k = pq.Kandidat(url="https://example.com/feed", type="rss",
                    operator="Beispiel", website="example.com")
    original = pq.collect_source

    def boom(*a, **kw):
        raise RuntimeError("404 Not Found")

    pq.collect_source = boom
    try:
        b = pq._pruefe_einen(k, FakeBestand(), 8, False)
    finally:
        pq.collect_source = original
    assert not b.bestanden
    assert "404" in b.fehler
    assert not _grund(b, 1)["ok"]


# ---------------------------------------------------------------- Hilfsstuecke
@pytest.mark.parametrize("titel", [
    "Mehr erfahren", "Read more", "Presse", "Newsroom", "12.03.2026",
    "2026-03-12", "March 12, 2026", "Alle anzeigen", "Cookie-Einstellungen",
    "About Us", "", "   ",
])
def test_navigationslabel_erkannt(titel):
    assert pq._ist_navigationslabel(titel)


@pytest.mark.parametrize("titel", [
    "Telekom startet 5G-Standalone in 200 Staedten",
    "Q1 Results 2026 published by the group board",
    "Vodafone and AST SpaceMobile complete first video call via satellite",
])
def test_echte_ueberschrift_erkannt(titel):
    assert not pq._ist_navigationslabel(titel)


@pytest.mark.parametrize("host,erwartet", [
    ("www.telekom.com", "telekom.com"),
    ("newsroom.bt.com", "bt.com"),
    ("www.three.co.uk", "three.co.uk"),
    ("investors.att.com", "att.com"),
    ("tim.com.br", "tim.com.br"),
    ("example.com", "example.com"),
])
def test_registrierbare_domain(host, erwartet):
    assert pq._registrable(host) == erwartet


# --------------------------------------------------------- Massenbetrieb
# Kriterium 10: bei 1000 Kandidaten muss der Check einen Abbruch ueberleben
# und darf nicht fuer jeden Kandidaten den halben Bestand neu abrufen.

def test_cache_schluessel_haengt_an_den_collector_feldern():
    a = pq.Kandidat(url="https://example.com/news", type="newsroom")
    b = pq.Kandidat(url="https://example.com/news/", type="newsroom")
    c = pq.Kandidat(url="https://example.com/news", type="newsroom",
                    item_selector=".card")
    d = pq.Kandidat(url="https://example.com/news", type="rss")

    assert pq.cache_schluessel(a) == pq.cache_schluessel(b), \
        "dieselbe URL, nur anders geschrieben"
    assert pq.cache_schluessel(a) != pq.cache_schluessel(c), \
        "ein neuer item_selector ist ein neuer Vorschlag"
    assert pq.cache_schluessel(a) != pq.cache_schluessel(d)


def test_cache_ueberlebt_den_abbruch(tmp_path):
    pfad = tmp_path / "cache.json"
    k = pq.Kandidat(url="https://example.com/news", type="newsroom")

    cache = pq.Ergebniscache(pfad)
    assert cache.hole(k) is None
    cache.merke(k, {"url": k.url, "bestanden": True, "n_items": 12})

    # Neuer Prozess, dieselbe Datei - der Kandidat ist erledigt.
    wieder = pq.Ergebniscache(pfad)
    assert wieder.hole(k)["n_items"] == 12


def test_kaputter_cache_kostet_den_lauf_nicht(tmp_path):
    pfad = tmp_path / "cache.json"
    pfad.write_text("{kein json")
    cache = pq.Ergebniscache(pfad)
    assert cache.hole(pq.Kandidat(url="https://example.com/x")) is None


def test_ohne_cachedatei_wird_nichts_geschrieben(tmp_path):
    cache = pq.Ergebniscache(None)
    cache.merke(pq.Kandidat(url="https://example.com/x"), {"bestanden": True})
    assert list(tmp_path.iterdir()) == []
