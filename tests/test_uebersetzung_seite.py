"""Die Uebersetzung auf der Website: Link, Seite, und was NICHT passiert.

Der teuerste Fehler waere hier nicht ein fehlender Link, sondern ein
verschwundener Originallink - die Uebersetzung tritt NEBEN das Original,
nicht an seine Stelle. Das steht deshalb als eigener Test da.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from telco_radar.report import uebersetzung_view as uv
from telco_radar.report.html import render_site, _env
from telco_radar.uebersetzung.store import (
    UebersetzungsStore, Uebersetzung, text_hash)

WURZEL = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------- Schluessel
def test_die_id_kommt_aus_der_normalisierten_url():
    """Premortem 6: der Dateiname folgt der Item-ID, nicht dem Titel.

    Zwei Schreibweisen derselben Adresse muessen auf dieselbe Seite zeigen,
    sonst zerfaellt das Archiv beim ersten Tracking-Parameter.
    """
    a = uv.id_fuer_url("https://beispiel.test/artikel/1")
    b = uv.id_fuer_url("https://www.beispiel.test/artikel/1/?utm_source=x")
    assert a == b
    assert len(a) == 16


def test_die_id_stimmt_mit_der_des_items_ueberein():
    """Die Website darf keinen EIGENEN Schluessel rechnen."""
    from telco_radar.models import Item
    url = "https://beispiel.test/a/2"
    assert uv.id_fuer_url(url) == Item(title="t", url=url, source_name="q").id


# ------------------------------------------------------------------ Zuordnung
def _store(tmp_path, **kw):
    store = UebersetzungsStore(tmp_path / "uebersetzungen.jsonl")
    basis = dict(item_id=uv.id_fuer_url("https://beispiel.test/a/1"),
                 quell_hash=text_hash("q"), titel_de="Deutscher Titel",
                 absaetze=["Erster Absatz.", "Zweiter Absatz."],
                 sprache="es", titel_original="Titulo original",
                 url="https://beispiel.test/a/1", quelle="TeleSemana",
                 datum="2026-08-13", erstellt_am="2026-08-13",
                 zeichen_original=4321, herkunft="artikel")
    basis.update(kw)
    store.add(Uebersetzung(**basis))
    return store


def test_eine_uebersetzung_ohne_absaetze_wird_nicht_verlinkt(tmp_path):
    """Eine leere Seite ist schlimmer als kein Link."""
    store = _store(tmp_path, absaetze=[])
    assert uv.zuordnung(store) == {}
    assert uv.seiten(store) == []


def test_zuordnung_zeigt_auf_den_richtigen_pfad(tmp_path):
    store = _store(tmp_path)
    zuordnung = uv.zuordnung(store)
    url = "https://beispiel.test/a/1"
    assert zuordnung[url] == f"uebersetzung/{uv.id_fuer_url(url)}.html"


# ---------------------------------------------------------------- Die Seite
def _seite(tmp_path) -> str:
    store = _store(tmp_path)
    seite = uv.seiten(store)[0]
    env = _env()
    env.globals.setdefault("geraete_verlinkt", False)
    env.globals.setdefault("newsletter_verlinkt", False)
    env.globals.setdefault("rechtstexte_verlinkt", set())
    # Genau die Felder, die render_site() uebergibt - als handverlesene
    # Liste liefe der Test irgendwann gegen eine andere Vorlage als die
    # Website.
    return env.get_template("uebersetzung.html.j2").render(
        prefix="../", u=seite["u"],
        **{k: v for k, v in seite.items() if k not in ("u", "dateiname")})


def test_die_seite_nennt_die_maschinelle_herkunft(tmp_path):
    html = _seite(tmp_path)
    assert "Maschinelle Uebersetzung" in html or "aschinelle Über" in html


def test_die_seite_verlinkt_das_original(tmp_path):
    """Die Zusicherung, auf die es ankommt."""
    html = _seite(tmp_path)
    assert "https://beispiel.test/a/1" in html
    assert 'target="_blank"' in html


def test_die_seite_nennt_die_ausgangssprache(tmp_path):
    assert "Spanisch" in _seite(tmp_path)


def test_die_seite_traegt_alle_absaetze(tmp_path):
    html = _seite(tmp_path)
    assert "Erster Absatz." in html
    assert "Zweiter Absatz." in html


def test_der_originaltitel_bleibt_sichtbar(tmp_path):
    assert "Titulo original" in _seite(tmp_path)


# ------------------------------------------------- Gegen die gerenderte Site
@pytest.fixture(scope="module")
def gerendert(tmp_path_factory):
    """Eine echte Site mit EINER eingespielten Uebersetzung.

    Gegen die echten Berichte gerendert, nicht gegen eine Attrappe: der
    Link haengt an der URL-Zuordnung, und die trifft nur, wenn beide Seiten
    dieselbe Adresse fuehren.
    """
    reports = sorted((WURZEL / "data" / "reports").glob("*.json"))
    if not reports:
        pytest.skip("keine Berichte im Repo")
    daten = json.loads(reports[-1].read_text(encoding="utf-8"))
    ziel = None
    for region in (daten.get("regions") or {}).values():
        for h in region.get("highlights") or []:
            if h.get("url"):
                ziel = h
                break
        if ziel:
            break
    if not ziel:
        pytest.skip("keine Meldung mit URL")

    basis = tmp_path_factory.mktemp("site")
    shutil.copytree(WURZEL / "data" / "reports", basis / "data" / "reports")
    (basis / "data" / "state").mkdir(parents=True, exist_ok=True)
    store = UebersetzungsStore(basis / "data" / "state" / "uebersetzungen.jsonl")
    store.add(Uebersetzung(
        item_id=uv.id_fuer_url(ziel["url"]), quell_hash=text_hash("q"),
        titel_de="Vollstaendig uebersetzte Probemeldung",
        absaetze=["Ein Absatz."], sprache="es",
        titel_original=ziel.get("title", ""), url=ziel["url"],
        quelle=ziel.get("source", "Quelle"), datum="2026-08-13",
        erstellt_am="2026-08-13", zeichen_original=4321, herkunft="artikel"))
    store.speichern()

    from telco_radar.config import load_config
    cfg = load_config(WURZEL)
    render_site(basis / "site", basis / "data" / "reports", cfg)
    return basis / "site", ziel


def test_die_uebersetzungsseite_wird_geschrieben(gerendert):
    site, ziel = gerendert
    datei = site / "uebersetzung" / f"{uv.id_fuer_url(ziel['url'])}.html"
    assert datei.exists()
    assert "Ein Absatz." in datei.read_text(encoding="utf-8")


def test_der_rote_link_steht_auf_der_meldungsseite(gerendert):
    site, _ = gerendert
    assert "ueb-link" in (site / "meldungen.html").read_text(encoding="utf-8")


def test_der_originallink_bleibt_neben_dem_roten_stehen(gerendert):
    """Die Regel, die nicht verhandelbar ist."""
    site, ziel = gerendert
    html = (site / "meldungen.html").read_text(encoding="utf-8")
    assert ziel["url"] in html, "der Link zur Originalquelle ist verschwunden"
    assert "ueb-link" in html


def test_eine_meldung_ohne_uebersetzung_traegt_keinen_link(gerendert):
    """Sonst wirkt die Funktion kaputt - Premortem 4, von der anderen Seite."""
    site, ziel = gerendert
    html = (site / "meldungen.html").read_text(encoding="utf-8")
    # Genau EINE Meldung hat eine Uebersetzung bekommen.
    assert html.count('class="ueb-link"') == 1


def test_der_explorer_bekommt_die_uebersetzung_mitgeliefert(gerendert):
    """Die Archivwochen zeigen ihre Meldungen ueber app.js, nicht als HTML.

    Der Link entsteht dort im Browser aus `explorer_json` - steht das Feld
    nicht in den Daten, kann er gar nicht erscheinen, und eine statische
    Suche im HTML wuerde das nie melden.
    """
    site, ziel = gerendert
    # Der Explorer steht auf den ARCHIVWOCHEN (reports/<datum>.html), nicht
    # auf meldungen.html - dort listet die Seite ihre Meldungen als HTML.
    seiten = [p for p in sorted((site / "reports").glob("*.html"))
              if 'id="explorer-data">' in p.read_text(encoding="utf-8")]
    assert seiten, "keine Seite traegt einen Explorer-Datensatz"
    html = seiten[-1].read_text(encoding="utf-8")
    daten = html.split('id="explorer-data">', 1)[1].split("</script>", 1)[0]
    eintraege = json.loads(daten)
    passend = [e for e in eintraege if e.get("url") == ziel["url"]]
    assert passend, "die Testmeldung fehlt im Explorer-Datensatz"
    assert passend[0].get("uebersetzung", "").startswith("uebersetzung/")


def test_app_js_rechnet_den_pfad_der_archivwochen(gerendert):
    """Aus reports/<datum>.html muss ein "../" davor stehen.

    Der Explorer steht an zwei Orten mit verschiedener Tiefe; ein fester
    Pfad waere an einem der beiden falsch.
    """
    site, _ = gerendert
    js = (site / "app.js").read_text(encoding="utf-8")
    assert "uebPrefix" in js
    assert "'/reports/'" in js and "'../'" in js


def test_die_archivwoche_verlinkt_mit_der_richtigen_tiefe(tmp_path_factory):
    """Der statische Fall: eine uebersetzte Meldung ALS AUFMACHER.

    Dafuer bekommt jede Meldung der Ausgabe eine Uebersetzung - sonst
    haengt es vom Zufall der Gewichtung ab, ob der Aufmacher einen Link
    traegt, und der Test pruefte mal etwas und mal nichts.
    """
    reports = sorted((WURZEL / "data" / "reports").glob("*.json"))
    if not reports:
        pytest.skip("keine Berichte im Repo")
    basis = tmp_path_factory.mktemp("site_alle")
    shutil.copytree(WURZEL / "data" / "reports", basis / "data" / "reports")
    (basis / "data" / "state").mkdir(parents=True, exist_ok=True)
    store = UebersetzungsStore(basis / "data" / "state" / "uebersetzungen.jsonl")
    daten = json.loads(reports[-1].read_text(encoding="utf-8"))
    n = 0
    for region in (daten.get("regions") or {}).values():
        for h in region.get("highlights") or []:
            if not h.get("url"):
                continue
            n += 1
            store.add(Uebersetzung(
                item_id=uv.id_fuer_url(h["url"]), quell_hash=text_hash("q"),
                titel_de="Probe", absaetze=["Ein Absatz."], sprache="es",
                titel_original=h.get("title", ""), url=h["url"],
                quelle=h.get("source", "Q"), datum="2026-08-13",
                erstellt_am="2026-08-13", zeichen_original=4321,
                herkunft="artikel"))
    if not n:
        pytest.skip("keine Meldung mit URL")
    store.speichern()

    from telco_radar.config import load_config
    render_site(basis / "site", basis / "data" / "reports",
                load_config(WURZEL))

    archivseite = basis / "site" / "reports" / f"{daten['date']}.html"
    assert archivseite.exists()
    html = archivseite.read_text(encoding="utf-8")
    assert "ueb-link" in html, "der Aufmacher der Archivwoche traegt keinen Link"
    assert 'href="../uebersetzung/' in html, (
        "die Archivwoche verlinkt ohne ../ und zeigt damit ins Leere")
    # Und die Startseite dieselbe Meldung OHNE das ../
    start = (basis / "site" / "index.html").read_text(encoding="utf-8")
    assert 'href="uebersetzung/' in start


def test_das_stylesheet_kennt_den_roten_link(gerendert):
    site, _ = gerendert
    import re
    css = (site / "style.css").read_text(encoding="utf-8")
    assert ".ueb-link" in css
    # Der Rotwert wird NICHT neu erfunden, sondern aus der Variablen geholt.
    regel = re.search(r"\.ueb-link a\{([^}]*)\}", css)
    assert regel, "die Regel .ueb-link a fehlt"
    assert "var(--red)" in regel.group(1)
    # Und nirgends im Uebersetzungsblock steht ein eigener Farbwert.
    block = css[css.index("/* =====================================================  UEBERSETZUNG = */"):]
    block = block[:block.index("/* ==========================================================  AUFKLAPPER = */")]
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block), (
        "der Uebersetzungsblock erfindet eine eigene Farbe")


def test_die_sprache_steht_im_richtigen_fall(tmp_path):
    """"aus dem Spanisch" ist falsch - und der Satz steht zweimal pro Seite.

    Erst beim ANSEHEN der gerenderten Seite aufgefallen, nicht in einem
    Test: die Zeichenkette war korrekt, der Satz war es nicht.
    """
    html = _seite(tmp_path)
    assert "aus dem Spanischen" in html
    assert "aus dem Spanisch " not in html
    assert "aus dem Spanisch." not in html


def test_die_seite_schreibt_deutsch_mit_umlauten(tmp_path):
    """Der Rest des Portals tut es auch - ASCII gilt nur fuer Kommentare."""
    html = _seite(tmp_path)
    assert "Vollständige Übersetzung" in html
    assert "Maschinelle Übersetzung" in html
    for falsch in ("Uebersetzung", "uebersetzt", "geprueft", "Absaetze"):
        assert falsch not in html, f"{falsch!r} steht sichtbar auf der Seite"


def test_sprachen_ohne_isch_bleiben_unveraendert():
    from telco_radar.uebersetzung.sprache import sprachname_dativ
    assert sprachname_dativ("hi") == "Hindi"
    assert sprachname_dativ("th") == "Thai"
    assert sprachname_dativ("tr") == "Türkischen"


# --------------------------------------------- Die Titelseite, alle Gewichte
@pytest.fixture(scope="module")
def titelseite_voll(tmp_path_factory):
    """Jede berichtete Meldung bekommt eine Uebersetzung.

    So laesst sich zaehlen, an WELCHEN Gewichtungen der Link ueberhaupt
    erscheinen kann - unabhaengig davon, welche Meldung dieser Woche gerade
    fremdsprachig ist.
    """
    reports = sorted((WURZEL / "data" / "reports").glob("*.json"))
    if not reports:
        pytest.skip("keine Berichte im Repo")
    daten = json.loads(reports[-1].read_text(encoding="utf-8"))
    urls = [h["url"] for region in (daten.get("regions") or {}).values()
            for h in (region.get("highlights") or []) if h.get("url")]
    if len(urls) < 8:
        pytest.skip("zu wenige Meldungen fuer die Zaehlung")

    basis = tmp_path_factory.mktemp("titelseite")
    shutil.copytree(WURZEL / "data" / "reports", basis / "data" / "reports")
    (basis / "data" / "state").mkdir(parents=True, exist_ok=True)
    store = UebersetzungsStore(
        basis / "data" / "state" / "uebersetzungen.jsonl")
    for u in urls:
        store.add(Uebersetzung(
            item_id=uv.id_fuer_url(u), quell_hash=text_hash(u),
            titel_de="Deutsche Fassung", absaetze=["Ein Absatz."],
            sprache="pl", url=u, quelle="Quelle", erstellt_am="2026-08-15",
            herkunft="artikel"))
    store.speichern()

    from telco_radar.config import load_config
    render_site(basis / "site", basis / "data" / "reports",
                load_config(WURZEL))
    return (basis / "site" / "index.html").read_text(encoding="utf-8")


def test_die_titelseite_verlinkt_an_allen_bildgewichtungen(titelseite_voll):
    """Bis zum 15.08.2026 trug nur der Aufmacher den roten Link.

    Damit erschien er auf der Startseite genau dann, wenn die staerkste
    Meldung der Woche zufaellig fremdsprachig war - an der Ausgabe vom
    14.08.2026 gemessen: elf Uebersetzungen, davon null auf der Startseite,
    obwohl acht polnische und zwei franzoesische Meldungen im Bericht
    standen. Aufmacher (1) + zweite Reihe (2) + dritte Reihe (4) = 7.
    """
    assert titelseite_voll.count('class="ueb-link"') >= 7


def test_der_rote_link_verschachtelt_keine_links(titelseite_voll):
    """Ein Link in einem Link ist kein gueltiges HTML - und die Karten der
    zweiten und dritten Reihe sind vollstaendig in einen `<a>` gewickelt."""
    from html.parser import HTMLParser

    class Zaehler(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tief = 0
            self.verschachtelt = 0

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.tief += 1
                if self.tief > 1:
                    self.verschachtelt += 1

        def handle_endtag(self, tag):
            if tag == "a" and self.tief:
                self.tief -= 1

    z = Zaehler()
    z.feed(titelseite_voll)
    assert z.verschachtelt == 0
