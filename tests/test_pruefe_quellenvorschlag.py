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

from telco_radar.config import Source
from telco_radar.models import Item, normalize_url

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
        # Leer heisst "kein Index aufgebaut" - dann prueft der Check die
        # Inhaltsdublette wie bisher live (siehe Kriterium 10).
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
    from telco_radar.config import Source
    gleiche = _items(10)
    bestand = FakeBestand(je_operator={
        "Beispiel": [Source(type="rss", url="https://example.com/alt")]})
    k = pq.Kandidat(url="https://example.com/neu", type="rss",
                    operator="Beispiel", website="example.com")
    b = _pruefe(k, gleiche, bestand, overlap=True)
    assert not b.bestanden
    assert "100%" in _grund(b, 7, "Inhaltsdublette")["detail"]


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


# =========================================================================== #
# Massenbetrieb (Kriterium 10): Wiederaufnahme, Cache, Dubletten-Index.
#
# Bei 1000 Kandidaten ist der Check selbst ein Engpass. Vorher rief die
# Inhaltsdublettenpruefung fuer JEDEN Kandidaten alle bestehenden Quellen
# seines Betreibers live ab, und ein Abbruch nach 800 Kandidaten bedeutete,
# von vorn anzufangen.
# =========================================================================== #

def _kandidat(url="https://a.de/feed", **kw):
    return pq.Kandidat(url=url, **kw)


def test_cache_schluessel_trennt_verschiedene_anlaeufe():
    """Dieselbe URL mit anderem Selektor ist ein ANDERER Vorschlag - sonst
    wuerde der zweite Anlauf das Ergebnis des ersten erben."""
    a = _kandidat(type="newsroom")
    b = _kandidat(type="newsroom", item_selector=".card")
    c = _kandidat(type="rss")
    assert len({pq._cache_schluessel(k) for k in (a, b, c)}) == 3


def test_cache_schluessel_ignoriert_url_kosmetik():
    assert (pq._cache_schluessel(_kandidat("https://www.a.de/feed/"))
            == pq._cache_schluessel(_kandidat("https://a.de/feed")))


def test_cache_wird_geschrieben_und_gelesen(tmp_path):
    pfad = tmp_path / "cache.json"
    befund = pq.Befund(kandidat=_kandidat(), bestanden=True, n_items=9)
    pq.schreibe_cache(pfad, [befund.as_dict()], {})

    gelesen = pq.lade_cache(pfad)
    assert len(gelesen) == 1
    assert gelesen[pq._cache_schluessel(_kandidat())]["n_items"] == 9


def test_cache_behaelt_frueher_geprueftes(tmp_path):
    """Wiederaufnahme nach Abbruch: Welle 2 darf Welle 1 nicht ueberschreiben."""
    pfad = tmp_path / "cache.json"
    erste = pq.Befund(kandidat=_kandidat("https://a.de/feed"), bestanden=True)
    pq.schreibe_cache(pfad, [erste.as_dict()], {})

    vorher = pq.lade_cache(pfad)
    zweite = pq.Befund(kandidat=_kandidat("https://b.de/feed"), bestanden=False)
    pq.schreibe_cache(pfad, [zweite.as_dict()], vorher)

    assert len(pq.lade_cache(pfad)) == 2


def test_defekter_cache_wird_ignoriert(tmp_path):
    pfad = tmp_path / "cache.json"
    pfad.write_text("{kaputt", encoding="utf-8")
    assert pq.lade_cache(pfad) == {}


def test_fehlender_cache_ist_leer(tmp_path):
    assert pq.lade_cache(tmp_path / "gibt-es-nicht.json") == {}
    assert pq.lade_cache(None) == {}


def test_dublette_wird_gegen_den_index_erkannt(monkeypatch):
    """Ohne Live-Abruf der bestehenden Quelle - das ist der ganze Punkt."""
    abrufe = []

    def _collect(source, *a, **k):
        abrufe.append(source.url)
        return _items(10)

    monkeypatch.setattr(pq, "collect_source", _collect)
    bestand = FakeBestand(item_index={"Alpha": {
        "https://alpha.de/presse": {normalize_url(i.url) for i in _items(10)}}})

    befund = pq._pruefe_einen(
        _kandidat("https://alpha.de/news", operator="Alpha",
                  website="alpha.de", type="rss"),
        bestand, 8, True)

    dublette = [k for k in befund.kriterien if k["name"] == "keine Inhaltsdublette"]
    assert dublette and not dublette[0]["ok"]
    # nur der Kandidat selbst wurde geholt, nicht die Vergleichsquelle
    assert abrufe == ["https://alpha.de/news"]


def test_ohne_index_wird_live_verglichen(monkeypatch):
    abrufe = []

    def _collect(source, *a, **k):
        abrufe.append(source.url)
        return _items(10)

    monkeypatch.setattr(pq, "collect_source", _collect)
    bestand = FakeBestand(je_operator={"Alpha": [
        Source(type="rss", url="https://alpha.de/presse", name="Alpha")]})

    pq._pruefe_einen(_kandidat("https://alpha.de/news", operator="Alpha",
                               website="alpha.de", type="rss"),
                     bestand, 8, True)
    assert "https://alpha.de/presse" in abrufe


def test_dublette_wird_ueber_die_domain_erkannt(monkeypatch):
    """Die teuerste Luecke des ersten Massendurchgangs.

    Der Index war nach BETREIBER geschluesselt, Themenquellen tragen aber
    keinen Betreiber - fuer sie lief die Inhaltspruefung deshalb gar nicht.
    Ergebnis: 15 von 34 "bestandenen" Kandidaten waren blosse URL-Varianten
    bereits konfigurierter Quellen (newsroom.arm.com/feed neben
    newsroom.arm.com/rss). Ueber die Domain greift die Pruefung auch ohne
    Betreiber.
    """
    monkeypatch.setattr(pq, "collect_source", lambda *a, **k: _items(10))
    bestand = FakeBestand(item_index={"arm.com": {
        "https://newsroom.arm.com/rss": {normalize_url(i.url)
                                         for i in _items(10)}}})

    befund = pq._pruefe_einen(
        pq.Kandidat(url="https://newsroom.arm.com/feed", type="rss",
                    thema="chips", name="Arm"),
        bestand, 8, True)

    assert not befund.bestanden
    dublette = [k for k in befund.kriterien if k["name"] == "keine Inhaltsdublette"]
    assert dublette and not dublette[0]["ok"]


def test_zweiter_kanal_derselben_domain_bleibt_erlaubt(monkeypatch):
    """Nicht jede zweite URL auf derselben Domain ist eine Dublette: der
    Technik-Blog neben dem Presse-Newsroom ist genau der Zugewinn, den der
    Auftrag sucht. Entscheidend ist die Ueberschneidung der MELDUNGEN."""
    monkeypatch.setattr(pq, "collect_source", lambda *a, **k: _items(10))
    andere = {f"https://example.com/ganz-anders-{i}" for i in range(10)}
    bestand = FakeBestand(item_index={"arm.com": {
        "https://newsroom.arm.com/rss": andere}})

    befund = pq._pruefe_einen(
        pq.Kandidat(url="https://newsroom.arm.com/blog/feed", type="rss",
                    thema="chips", name="Arm"),
        bestand, 8, True)
    assert befund.bestanden, befund.durchgefallen


def test_nicht_pruefbare_dublette_ist_kein_pass(monkeypatch):
    """overons.kpn/nieuws/feed/en/feed/ bestand, obwohl .../nieuws/feed/en
    bereits konfiguriert war: die bestehende Quelle lieferte beim Indexbau
    nichts, der Vergleich fiel still aus. Ein nicht durchgefuehrter Vergleich
    darf nicht wie ein bestandener aussehen."""
    monkeypatch.setattr(pq, "collect_source", lambda *a, **k: _items(10))
    bestand = FakeBestand(item_index={})
    bestand.domains_mit_quelle = {"overons.kpn"}

    befund = pq._pruefe_einen(
        pq.Kandidat(url="https://www.overons.kpn/nieuws/feed/en/feed/",
                    type="rss", operator="KPN", website="overons.kpn"),
        bestand, 8, True)
    assert not befund.bestanden
    dublette = [k for k in befund.kriterien if k["name"] == "keine Inhaltsdublette"]
    assert dublette and "nicht pruefbar" in dublette[0]["detail"]


def test_domain_ganz_ohne_bestand_bleibt_erlaubt(monkeypatch):
    """Eine voellig neue Firma hat keine Vergleichsquelle - das ist der
    Normalfall beim Ausbau und kein Ablehnungsgrund."""
    monkeypatch.setattr(pq, "collect_source", lambda *a, **k: _items(10))
    bestand = FakeBestand(item_index={})
    bestand.domains_mit_quelle = {"andere.de"}

    befund = pq._pruefe_einen(
        pq.Kandidat(url="https://neu.de/feed", type="rss", operator="Neu",
                    website="neu.de"),
        bestand, 8, True)
    assert befund.bestanden, befund.durchgefallen


def test_obermenge_einer_bestehenden_quelle_ist_eine_dublette(monkeypatch):
    """libertyglobal.com/wp-json liefert 25 Meldungen und enthaelt alle 10 des
    konfigurierten libertyglobal.com/feed. Gegen die Kandidatenmenge gerechnet
    waeren das unauffaellige 40 %."""
    kandidat_items = _items(25)
    monkeypatch.setattr(pq, "collect_source", lambda *a, **k: kandidat_items)
    bestehende = {normalize_url(i.url) for i in kandidat_items[:10]}
    bestand = FakeBestand(item_index={"example.com": {
        "https://www.example.com/feed/": bestehende}})
    bestand.domains_mit_quelle = {"example.com"}

    befund = pq._pruefe_einen(
        pq.Kandidat(url="https://www.example.com/wp-json/wp/v2/posts",
                    type="json_api", operator="Beispiel", website="example.com"),
        bestand, 8, True)
    assert not befund.bestanden
    dublette = [k for k in befund.kriterien if k["name"] == "keine Inhaltsdublette"]
    assert dublette and "100%" in dublette[0]["detail"]


# --------------------------------------------------------------------------- #
# Kriterium 6 hat lange gar nicht gegriffen
# --------------------------------------------------------------------------- #

def test_host_versteht_auch_eine_blosse_domain():
    """Die Vergleichs-Website steht ueberall als blosse Domain.

    urlsplit("casa-systems.com") liest das als PFAD, netloc bleibt leer - und
    Kriterium 6 fiel dadurch in den Zweig "keine Vergleichs-Website
    hinterlegt", also auf PASS. In Welle 3 sind so zwei Kandidaten
    durchgelaufen, deren Domain gar nicht zur Firma gehoerte.
    """
    assert pq._host("casa-systems.com") == "casa-systems.com"
    assert pq._host("www.casa-systems.com") == "casa-systems.com"
    assert pq._host("https://www.commscope.com/news-center/") == "commscope.com"
    assert pq._host("") == ""


def test_fremde_domain_faellt_an_kriterium_6_durch(monkeypatch):
    """casa-systems.com leitet nach der Uebernahme auf commscope.com."""
    kand = pq.Kandidat(url="https://www.commscope.com/news-center/",
                       type="newsroom", operator="Casa Systems",
                       website="casa-systems.com")
    befund = pq._pruefe_einen(kand, FakeBestand(), 8, False)
    k6 = [k for k in befund.kriterien if k["nr"] == 6]
    assert k6 and not k6[0]["ok"]
    assert not befund.bestanden


def test_eigene_domain_besteht_kriterium_6(monkeypatch):
    monkeypatch.setattr(pq, "collect_source",
                        lambda *a, **k: _items(8, dated=8))
    kand = pq.Kandidat(url="https://newsroom.ee.co.uk/", type="newsroom",
                       operator="EE", website="ee.co.uk")
    befund = pq._pruefe_einen(kand, FakeBestand(), 8, False)
    k6 = [k for k in befund.kriterien if k["nr"] == 6]
    assert k6 and k6[0]["ok"]
