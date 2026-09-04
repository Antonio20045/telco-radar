"""/geraete.html und /geraete-quellen.html - gegen die gerenderte Seite.

Zwei Sorten Zusicherung:

1. **Jede Zahl auf der Seite wird gegen die Daten gehalten.** CLAUDE.md §6
   dokumentiert sechs falsche Werte, die alle an `pytest -q` vorbeikamen,
   weil kein Test `render_site()` gegen echte Daten laufen liess. Diese
   Datei tut das.
2. **Die Veroeffentlichungsschwelle steht hier beziffert.** Eine Seite kommt
   in die Navigation, wenn sie ihre Frage beantworten kann - nicht wenn sie
   gebaut ist. Solange das Geraeteradar unter der Schwelle liegt, ist es
   ueber seinen direkten Link erreichbar und NICHT verlinkt.
"""
import csv
import io
import json
from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view
from telco_radar.report.geraete_view import (
    pruefe_zahlen,
    zahlen_der_namen,
    zahlen_im_text,
)
from telco_radar.report.html import render_site

_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# DIE VEROEFFENTLICHUNGSSCHWELLE
# ---------------------------------------------------------------------------
# Ab hier beantwortet die Seite ihre Frage ("was bieten die Wettbewerber an,
# und was kostet es?") und gehoert in die Navigation.
#
# Die Zahlen stehen seit dem 11.08.2026 im MODUL, nicht mehr hier - eine
# Schwelle, die nur ein Test kennt, kann keine Navigation schalten, und
# genau daran ist die Seite gescheitert: sie war live, vollstaendig und fuer
# jeden Leser unauffindbar, weil das Eintragen Handarbeit blieb.
# Der Test importiert sie und prueft BEIDE Zweige.
SCHWELLE_ANBIETER = geraete_view.SCHWELLE_ANBIETER
SCHWELLE_HERSTELLER = geraete_view.SCHWELLE_HERSTELLER
SCHWELLE_SKUS = geraete_view.SCHWELLE_SKUS


_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro Max", "generation": 17,
     "vorgaenger": "iPhone 16 Pro Max", "speicher": [256, 512],
     "segment": "flagship"},
    {"hersteller": "Apple", "modell": "iPhone 16 Pro Max", "generation": 16,
     "marktstart": "2024-09-20", "speicher": [256, 512], "segment": "flagship"},
    {"hersteller": "Samsung", "modell": "Galaxy S25 Ultra", "generation": 25,
     "marktstart": "2025-02-07", "speicher": [256, 512], "segment": "flagship"},
]}
_FARBEN = {"farben": {"titan-natur": ["Titannatur"], "schwarz": ["Black"]}}
_QUELLEN = {"anbieter": [
    {"name": "Medimax", "typ": "handel", "methode": "ldjson", "rang": 1,
     "basis_url": "https://www.medimax.de",
     "einstiege": [{"url": "https://www.medimax.de/c/116/smartphones",
                    "label": "Smartphones", "pfadmuster": "/p/"}]},
    {"name": "ElectronicPartner", "typ": "handel", "methode": "ldjson", "rang": 2,
     # Zwei Marken, EIN Laden - der Fall, wegen dem es `shop`/`anzeige` gibt.
     # Ohne ihn im Bestand waere der ganze Pfad nur ueber die
     # Identitaetsabbildung getestet.
     "shop": "ep", "anzeige": "ep.de (ElectronicPartner)",
     "basis_url": "https://www.ep.de",
     "einstiege": [{"url": "https://www.ep.de/c/116/smartphones",
                    "label": "Smartphones", "pfadmuster": "/p/"}]},
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 3, "eigen": True,
     "methode": "json_endpunkt", "aktiv": False,
     "grund": "Preis entsteht erst im Browser"},
    {"name": "Amazon", "typ": "handel", "rang": 4, "methode": "deaktiviert",
     "aktiv": False, "grund": "erfordert Product-Advertising-API-Zugang"},
    {"name": "fraenk", "typ": "discount", "netz": "Telekom", "rang": 5,
     "methode": "kein_hardware", "aktiv": False,
     "grund": "vermarktet keine Hardware"},
]}


def _listung(anbieter, device, sku, preis, farbe="titan-natur", speicher=256,
             status="aktiv", **kw):
    e = {
        "id": f"{anbieter.lower()}--{sku}", "sku_id": sku, "device_id": device,
        "anbieter": anbieter, "anbieter_typ": "handel", "netz": "",
        "speicher_gb": speicher, "farbe_roh": farbe.title(),
        "farbe_normalisiert": farbe, "zustand": "neu",
        "first_seen": "2026-07-01", "last_verified": "2026-08-11",
        "status": status, "missed_checks": 0,
        "preis_ohne_vertrag": preis,
        "erstpreis": (preis + 100.0) if preis is not None else None,
        "erstpreis_art": "ohne_vertrag" if preis is not None else "",
        "erstpreis_am": "2026-07-01" if preis is not None else "",
        "quelle_url": f"https://example.de/p/{sku}",
        "abgerufen_am": "2026-08-11", "verfuegbarkeit": "lieferbar",
        "confidence": "hoch", "einstiege": ["https://example.de/liste"],
    }
    e.update(kw)
    return e


_DB = {"updated": "2026-08-11", "anbieter": {
    "Medimax": {"laeufe": 4, "funde_gesamt": 8},
    "ElectronicPartner": {"laeufe": 4, "funde_gesamt": 4},
    "fraenk": {"laeufe": 4, "funde_gesamt": 0},
}, "listungen": [
    _listung("Medimax", "apple-iphone-17-pro-max",
             "apple-iphone-17-pro-max-256gb-titan-natur", 1449.0),
    _listung("Medimax", "apple-iphone-16-pro-max",
             "apple-iphone-16-pro-max-256gb-schwarz", 899.0, farbe="schwarz"),
    _listung("ElectronicPartner", "apple-iphone-17-pro-max",
             "apple-iphone-17-pro-max-512gb-titan-natur", 1599.0, speicher=512),
    _listung("Vodafone", "samsung-galaxy-s25-ultra",
             "samsung-galaxy-s25-ultra-256gb-schwarz", 1249.0, farbe="schwarz"),
    _listung("Medimax", "samsung-galaxy-s25-ultra",
             "samsung-galaxy-s25-ultra-512gb-schwarz", 1399.0, farbe="schwarz",
             speicher=512, status="ausgelistet", ended_since="2026-08-11"),

    # ------------------------------------------------------------------
    # DIE ZWEI FAELLE, WEGEN DERER ES ZWEI MENGEN GIBT (31.08.2026)
    # ------------------------------------------------------------------
    # Ohne sie ist `bereinige(sichtbar)` Zeile fuer Zeile dasselbe wie
    # `bereinige(pruefe(sichtbar))`, und JEDER Test ueber den Unterschied
    # der beiden Mengen ist gruen, ohne etwas zu pruefen. Genau daran ist
    # `test_der_export_zeigt_genau_den_bestand_der_seite` gescheitert: der
    # Pruefer konnte `aufbereiten()` auf den Rohbestand zurueckdrehen, und
    # 2190 Tests blieben gruen.
    #
    # 1. EIN ZWILLINGSPAAR - dieselbe Listung unter zwei Farbschreibweisen.
    #    Der echte Fall: o2 nimmt das Zustandswort aus der Farbe, die
    #    `sku_id` aendert sich, der Store legt neu an und altert die alte
    #    Zeile. Beide sind sichtbar, beide zeigen denselben Preis unter
    #    derselben Adresse. Die gealterte traegt dazu den falschen
    #    Store-Zustand "neu" - sie ist die Zeile, die als Neupreis in
    #    Vergleich und CSV ginge.
    #    `bereinige()` fasst das Paar in BEIDEN Mengen zusammen.
    _listung("Medimax", "apple-iphone-16-pro-max",
             "apple-iphone-16-pro-max-512gb-mitternacht-erneuert", 445.0,
             speicher=512, status="vermutlich ausgelistet",
             id="medimax--apple-iphone-16-pro-max-512gb-mitternacht-erneuert",
             farbe_roh="Mitternacht erneuert", farbe_normalisiert=None,
             zustand="neu", abgerufen_am="2026-08-10",
             quelle_url="https://example.de/p/iphone-16-pro-max-512gb-"
                        "mitternacht-erneuert"),
    _listung("Medimax", "apple-iphone-16-pro-max",
             "apple-iphone-16-pro-max-512gb-mitternacht", 445.0, speicher=512,
             id="medimax--apple-iphone-16-pro-max-512gb-mitternacht",
             farbe_roh="Mitternacht", farbe_normalisiert=None,
             zustand="refurbished",
             quelle_url="https://example.de/p/iphone-16-pro-max-512gb-"
                        "mitternacht-erneuert"),
    # 2. EIN DOPPELPREIS - derselbe Artikel in derselben Farbe zu zwei
    #    Preisen, unter zwei eigenen Adressen. Der echte Fall: o2 fuehrt das
    #    Galaxy S26 FE 128 GB als "pistachio" (811,00) und "pistachio bk"
    #    (667,00); `farbschluessel()` erkennt das Kuerzel, `pruefe()` wirft
    #    die GANZE Gruppe aus den Preisaussagen - welcher der beiden Preise
    #    stimmt, sagt der Datensatz nicht.
    #    Es sind trotzdem zwei Listungen, die jemand im Regal findet: sie
    #    stehen im Bestand und fehlen in `belastbar`. DAS ist der Unterschied
    #    der zwei Mengen, und er ist genau zwei Zeilen gross - hier wie im
    #    echten Bestand.
    _listung("Medimax", "samsung-galaxy-s25-ultra",
             "samsung-galaxy-s25-ultra-256gb-pistachio", 811.0,
             id="medimax--samsung-galaxy-s25-ultra-256gb-pistachio",
             farbe_roh="Pistachio", farbe_normalisiert=None),
    _listung("Medimax", "samsung-galaxy-s25-ultra",
             "samsung-galaxy-s25-ultra-256gb-pistachio-bk", 667.0,
             id="medimax--samsung-galaxy-s25-ultra-256gb-pistachio-bk",
             farbe_roh="Pistachio BK", farbe_normalisiert=None,
             quelle_url="https://example.de/p/galaxy-s25-ultra-256gb-"
                        "pistachio-bk"),
]}

# Die drei Mengen der Fixture, ALS ERWARTUNG ausgeschrieben - nicht mit
# `bereinige()`/`pruefe()` nachgerechnet. Ein Test, der seine Erwartung aus
# derselben Funktion holt, die er prueft, ist gruen, wenn beide falsch sind.
_ZWILLING_GEALTERT = "medimax--apple-iphone-16-pro-max-512gb-mitternacht-erneuert"
_DOPPELPREIS = frozenset({
    "medimax--samsung-galaxy-s25-ultra-256gb-pistachio",
    "medimax--samsung-galaxy-s25-ultra-256gb-pistachio-bk"})


def _rohbestand_ids(db=None) -> set:
    """Alles, was nicht ausgelistet ist - die Menge, aus der beide anderen
    entstehen. Sie schaltet die Veroeffentlichungsschwelle, und nur die."""
    return {e["id"] for e in (db or _DB)["listungen"]
            if e["status"] != "ausgelistet"}


def _bestand_ids(db=None) -> set:
    """Was es GIBT: Regal, Farbbericht, CSV, Betriebszahlen.

    Der Rohbestand ohne die gealterte Zwillingshaelfte - zwei Schreibweisen
    derselben Listung sind eine Zeile.
    """
    return _rohbestand_ids(db) - {_ZWILLING_GEALTERT}


def _belastbare_ids(db=None) -> set:
    """Was gegeneinander gerechnet werden DARF: Vergleich, Alarme, Verlauf.

    Der Bestand ohne das Doppelpreispaar.
    """
    return _bestand_ids(db) - _DOPPELPREIS

_PUNKTE = [
    {"listung_id": "medimax--apple-iphone-16-pro-max-256gb-schwarz",
     "device_id": "apple-iphone-16-pro-max", "anbieter": "Medimax",
     "datum": "2026-07-01", "preis_ohne_vertrag": 999.0,
     "verfuegbarkeit": "lieferbar", "quelle_url": "https://example.de/p"},
    {"listung_id": "medimax--apple-iphone-16-pro-max-256gb-schwarz",
     "device_id": "apple-iphone-16-pro-max", "anbieter": "Medimax",
     "datum": "2026-08-11", "preis_ohne_vertrag": 899.0,
     "verfuegbarkeit": "lieferbar", "quelle_url": "https://example.de/p"},
]


# Ein ausdruecklich duenner Bestand: seit gestern gelistet, EIN Lauf. Der
# Normalfall `_DB` ist seit dem 11.08.2026 KEIN duenner Fall mehr - er laeuft
# seit dem 01.07. und hat vier Laeufe, also eine belastbare Verweildauer.
_DB_DUENN = {"updated": "2026-08-11",
             "anbieter": {"Medimax": {"laeufe": 1, "funde_gesamt": 2}},
             "listungen": [
                 _listung("Medimax", "apple-iphone-17-pro-max",
                          "apple-iphone-17-pro-max-256gb-titan-natur", 1449.0,
                          first_seen="2026-08-10", erstpreis_am="2026-08-10"),
                 _listung("Medimax", "samsung-galaxy-s25-ultra",
                          "samsung-galaxy-s25-ultra-256gb-schwarz", 1249.0,
                          farbe="schwarz", first_seen="2026-08-10",
                          erstpreis_am="2026-08-10"),
             ]}
_PUNKTE_DUENN = [{"listung_id": "medimax--apple-iphone-17-pro-max-256gb-titan-natur",
                  "device_id": "apple-iphone-17-pro-max", "anbieter": "Medimax",
                  "datum": "2026-08-11", "preis_ohne_vertrag": 1449.0,
                  "verfuegbarkeit": "lieferbar",
                  "quelle_url": "https://example.de/p"}]

def _baue(tmp_path: Path, db=None, punkte=None):
    """Eine vollstaendige Site rendern - mit echtem Bericht, echtem Zustand.

    `db` ersetzt den Bestand, wenn ein Fall mehr Listungen braucht als die
    fuenf des Normalfalls (etwa: eine volle Spalte der Positionskarte).
    `punkte` ersetzt die Preishistorie - noetig fuer jeden Fall, der vom
    ERSTLAUF handelt: der Normalfall hat zwei Messtage, und damit tritt
    "es gibt noch nichts zu vergleichen" nie ein."""
    root = tmp_path
    (root / "config").mkdir(parents=True, exist_ok=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "geraete_db.json").write_text(json.dumps(db or _DB), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps(p) for p in (_PUNKTE if punkte is None else punkte))
        + "\n", encoding="utf-8")

    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "2026-08-11.json").write_text(json.dumps({
        "date": "2026-08-11", "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": [],
    }), encoding="utf-8")
    (reports / "2026-08-11.md").write_text("# Bericht\n", encoding="utf-8")

    site = root / "site"
    render_site(site, reports)
    return site


def _suppe(site: Path, name: str) -> BeautifulSoup:
    return BeautifulSoup((site / name).read_text(encoding="utf-8"), "html.parser")


# --------------------------------------------------------------------------
# Die Seite entsteht
# --------------------------------------------------------------------------

def test_der_notzustand_traegt_dieselben_schluessel_wie_der_normalfall(tmp_path):
    """Ein fehlender Schluessel ist in Jinja kein Fehler, sondern eine stumm
    leere Seite. `leer()` und `aufbereiten()` duerfen deshalb nicht
    auseinanderlaufen - und genau dafuer gibt es den Notzustand.

    Der Test dazu ist beim Umbau am 30.08.2026 geloescht worden, weil er die
    vier Flaechen der Positionskarte verglich; die Zusicherung stand danach
    unbelegt in zwei Docstrings. Er vergleicht jetzt die Schluesselmengen
    selbst.
    """
    site = _baue(tmp_path)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    leer = geraete_view.leer()

    # Drei erlaubte Abweichungen, und alle drei sind aelter als dieser Umbau:
    # `export` setzt erst `render_site` nach (der Notzustand traegt es leer
    # vor), `fehler` gibt es nur im Notzustand, `pruefung`/`pruefbefunde` nur
    # im Normalfall. Alles andere muss beidseitig da sein.
    nur_notzustand = set(leer) - set(geraete)
    nur_normal = set(geraete) - set(leer)
    assert nur_notzustand <= {"export", "fehler"}, nur_notzustand
    assert nur_normal <= {"pruefung", "pruefbefunde"}, nur_normal
    assert set(leer["bilanz"]) <= set(geraete["bilanz"])
    assert set(leer["alarme"]) == set(geraete["alarme"])
    assert site.exists()


def test_die_schwelle_wird_gerechnet_und_nicht_behauptet(tmp_path):
    """Die Navigation und die gerechnete Schwelle duerfen nicht
    auseinanderlaufen - an BEIDEN Zweigen gemessen, nicht nur an dem, der
    heute gilt.

    Die alte Fassung las die Herstellerzahl aus den Spalten der
    Positionskarte; seit die geloescht ist, steht sie in `bilanz.hersteller`.
    """
    for db, erwartet in ((_db_mit(3), False),
                         (_db_mit(24, anbieter=_UEBER_DER_SCHWELLE), True)):
        wurzel = tmp_path / f"fall{erwartet}"
        site = _baue(wurzel, db=db)
        geraete = geraete_view.aufbereiten(
            wurzel / "data" / "state", lade_quellen(wurzel),
            lade_katalog(wurzel), heute="2026-08-11")
        erreicht = geraete_view.schwelle_erreicht(
            anbieter=geraete["bilanz"]["anbieter"],
            skus=geraete["bilanz"]["skus"],
            hersteller=geraete["bilanz"]["hersteller"])
        assert erreicht is erwartet, geraete["bilanz"]
        assert geraete["bilanz"]["schwelle_erreicht"] is erwartet
        verlinkt = "geraete.html" in {
            a.get("href") for a in _suppe(site, "geraete.html").select(".subnav a")}
        assert verlinkt is erreicht


def test_beide_seiten_werden_gerendert(tmp_path):
    site = _baue(tmp_path)
    assert (site / "geraete.html").exists()
    assert (site / "geraete-quellen.html").exists()


def _katalog_objekt(tmp_path) -> object:
    """Der Katalog der Fixture als Objekt, ohne eine Site zu rendern."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "geraete_katalog.yaml").write_text(
        yaml.safe_dump(_KATALOG, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    return lade_katalog(tmp_path)


def test_die_fixture_loest_beide_stufen_wirklich_aus(tmp_path):
    """Der Waechter vor allen Mengen-Tests. Ohne ihn pruefen sie nichts.

    Bis zum 31.08.2026 hatte `_DB` fuenf Listungen, an denen weder
    `bereinige()` noch `pruefe()` etwas zu tun fanden - die drei Mengen
    waren dieselbe Menge. `test_der_export_zeigt_genau_den_bestand_der_seite`
    behauptete deshalb "Export == Rohbestand" und blieb gruen, als ein
    Pruefer die ganze Verdrahtung zurueckdrehte.

    Gemessen wird gegen die ECHTEN Funktionen, nicht gegen die Erwartung:
    hier soll auffallen, wenn die Fixture ihren Fall nicht mehr aufspannt -
    etwa weil jemand die Farbe eines Zwillings aendert oder einen der zwei
    Doppelpreise anfasst.
    """
    from telco_radar.report import geraete_bereinigung

    sichtbar = [e for e in _DB["listungen"] if e["status"] != "ausgelistet"]
    katalog = _katalog_objekt(tmp_path)
    _pruefung, bestand, belastbar = geraete_view.bestand_und_belastbar(
        sichtbar, katalog)

    assert len(bestand) < len(sichtbar), (
        "die Bereinigung findet in dieser Fixture keinen Zwilling - dann "
        "misst kein Test der Seite, dass sie ueberhaupt laeuft")
    assert len(belastbar) < len(bestand), (
        "die Pruefung nimmt in dieser Fixture keine Zeile - dann sind "
        "Bestand und belastbare Menge dasselbe, und der Unterschied, um den "
        "es geht, wird nirgends gemessen")

    # Und die ausgeschriebenen Erwartungen treffen die gerechneten Mengen.
    # Laufen die auseinander, ist ab hier jede Zahl in dieser Datei falsch.
    assert {e["id"] for e in bestand} == _bestand_ids()
    assert {e["id"] for e in belastbar} == _belastbare_ids()
    assert _DOPPELPREIS <= _bestand_ids()
    # Der Zwilling wird ZUSAMMENGEFASST, nicht geloescht: die ueberlebende
    # Zeile traegt das fruehere `first_seen` und den richtigen Zustand.
    ueberlebt = next(e for e in bestand
                     if e["device_id"] == "apple-iphone-16-pro-max"
                     and e["speicher_gb"] == 512)
    assert ueberlebt["zustand"] == "refurbished", ueberlebt["zustand"]
    assert geraete_bereinigung.zustand_der_zeile(ueberlebt) == "refurbished"


def test_der_export_zeigt_genau_den_bestand_der_seite(tmp_path):
    """Die Datei und die Seite duerfen nicht zwei Maerkte zeigen.

    Bis zum 31.08.2026 rechnete jede ihre eigene Menge: die Seite schickte
    ihren Bestand durch `geraete_pruefung.pruefe()`, der Export filterte in
    `geraete_export.aktuell_csv()` selbst nach `status`. Am echten Bestand
    gemessen standen dadurch zwei o2-Listungen, deren Rohfelder sie als
    gebraucht ausweisen, in `geraete-aktuell.csv` mit `Zustand = neu`.

    Die Ueberkorrektur dagegen war, dem Export die GEPRUEFTE Menge zu geben:
    dann fehlen die zwei Zeilen des o2-Doppelpreises, auf die der
    Pruefbericht namentlich verweist. Der Export zeigt den BESTAND
    (`geraete_view.bestand_und_belastbar`) - gemessen an der wirklich
    geschriebenen Datei nach einem vollstaendigen `render_site()`.

    DIE DREI VERGLEICHE SIND DER PUNKT. Nur gegen den Rohbestand geprueft
    faellt eine Rueckdrehung auf `sichtbar` nicht auf; nur gegen den Bestand
    geprueft koennte er die belastbare Menge sein. Beide Nachbarmengen
    stehen deshalb ausdruecklich daneben.
    """
    site = _baue(tmp_path)
    aktuell = list(csv.reader(io.StringIO(
        (site / "exporte" / "geraete-aktuell.csv").read_text(
            encoding="utf-8-sig")), delimiter=";"))
    kopf, zeilen = aktuell[0], aktuell[1:]
    gefuehrt = {z[kopf.index("Listungs-ID")] for z in zeilen}

    assert gefuehrt == _bestand_ids(), gefuehrt ^ _bestand_ids()
    assert len(zeilen) == len(_bestand_ids()), "keine Zeile doppelt"
    # Die zwei Nachbarmengen, jede mit ihrem Fehlerbild:
    assert gefuehrt != _rohbestand_ids(), (
        "der Export fuehrt die gealterte Zwillingshaelfte - dieselbe "
        "Listung stuende zweimal in der Datei")
    assert gefuehrt != _belastbare_ids(), (
        "der Export fuehrt das Doppelpreispaar nicht - es steht namentlich "
        "im Pruefbericht, und der verweist auf genau diese Datei")

    # Die Seite zeigt dieselbe Menge. Zwei Zahlen fuer einen Bestand waeren
    # der Fehlertyp aus CLAUDE.md §6 - und sie standen drei Zeilen
    # auseinander: "Alle exportieren (358 Zeilen)" ueber einer Ueberschrift
    # mit der Zahl 370.
    s = _suppe(site, "geraete.html")
    assert len(s.select("#gr-katalogtabelle .gr-k-zeile")) == len(gefuehrt)

    # Und die zweite Datei fuehrt keine Kurve zu einer Listung, die in der
    # ersten fehlt - sonst steht dort ein Preis ohne Zeile dazu.
    historie = list(csv.reader(io.StringIO(
        (site / "exporte" / "geraete-historie.csv").read_text(
            encoding="utf-8-sig")), delimiter=";"))
    h_kopf = historie[0]
    assert {z[h_kopf.index("Listungs-ID")] for z in historie[1:]} <= gefuehrt


def test_jede_zahl_fuer_den_bestand_ist_dieselbe_zahl(tmp_path):
    """S3: vier Zahlen standen fuer den Bestand auf der Seite, eine davon
    anders - und der Knopf, der weniger lieferte, hiess "Alle exportieren".

    Gemessen wird an der GERENDERTEN Seite, nicht an der Aufbereitung: der
    Fehler entstand zwischen `aufbereiten()` und der Vorlage, und genau da
    sieht ihn ein Test, der Dicts vergleicht, nicht.
    """
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    erwartet = len(_bestand_ids())

    knopf = s.select_one(".gr-export-knoepfe a").get_text(" ", strip=True)
    assert knopf == f"Alle exportieren ({erwartet} Zeilen)", knopf
    assert s.select_one(".gr-katalog h2 .rubrik-zahl").get_text(
        strip=True) == str(erwartet)
    assert len(s.select("#gr-katalogtabelle .gr-k-zeile")) == erwartet
    # Der Betriebszahlensatz am Fuss ist am 03.09.2026 mit der ganzen
    # Sektion "Wie vollstaendig ist das" von der Seite gefallen - der
    # Bestand steht jetzt nur noch an den drei Orten, die dieser Test
    # kennt, und das ist einer weniger als vorher.
    # Der dritte Ort ist der Knopf "alle N Zeilen zeigen". UMGEDREHT durch
    # P1 (dritte Nachbesserung, 31.08.2026, Coordinator-Entscheidung): bis
    # dahin erschien er erst, wenn die GESAMTZAHL ueber `KATALOG_SICHTBAR`
    # lag - diese Fixture liegt mit sieben Zeilen darunter, der Knopf fehlte
    # also. Seitdem deckelt die Standardansicht zusaetzlich JEDEN
    # Geraete-Block auf `BLOCK_SICHTBAR` (2) Zeilen, unabhaengig von der
    # Gesamtzahl - und genau diese Fixture traegt einen Block mit DREI
    # Zeilen (Samsung Galaxy S25 Ultra 256GB: Vodafone plus das
    # Doppelpreis-Paar "pistachio"/"pistachio bk", die BEIDE im Bestand
    # bleiben, siehe Modulkopf von `geraete_bereinigung`). Der Knopf muss
    # also erscheinen, obwohl die Gesamtzahl unter dem Deckel liegt - die
    # alte Zusicherung war eine Aussage ueber die Gesamtzahl, die neue ist
    # eine ueber jeden einzelnen Block.
    assert erwartet <= geraete_view.KATALOG_SICHTBAR, (
        "die Fixture ist ueber den Deckel gewachsen - jetzt gehoert der "
        "Knopf mitgeprueft")
    from collections import Counter
    bloecke = Counter((r["data-marke"], r.select_one(".gr-a-modell").get_text(strip=True),
                       r.get("data-speicher"))
                      for r in s.select("#gr-katalogtabelle .gr-k-zeile"))
    assert max(bloecke.values()) > geraete_view.BLOCK_SICHTBAR, (
        "die Fixture hat keinen Block ueber BLOCK_SICHTBAR mehr - dann "
        "prueft der Knopf-Teil dieses Tests nichts")
    knopf_mehr = s.select_one("#gr-kmehr")
    assert knopf_mehr is not None, (
        "der Knopf fehlt, obwohl ein Block ueber BLOCK_SICHTBAR liegt")
    knopf_text = " ".join(knopf_mehr.get_text(" ", strip=True).split())
    assert knopf_text == f"alle {erwartet} Zeilen zeigen"


def test_kennzahlen_stimmen_mit_den_daten_ueberein(tmp_path):
    """Der Fehlertyp aus CLAUDE.md §6: ein Etikett und ein Feld, die nicht
    dasselbe meinen.

    Gemessen werden die vier Alarmkacheln. Sie haben am 30.08.2026 die fuenf
    Betriebskacheln ("59 Geraete beobachtet", "250 Varianten") vom besten
    Platz der Seite abgeloest - eine Zahl, die zu keiner Handlung fuehrt,
    gehoert nicht dorthin. Der Betriebszahlensatz am Fuss ist am 03.09.2026
    ganz von der Seite gefallen; die Bestandszahlen werden deshalb gegen
    die Aufbereitung gehalten.
    """
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    kacheln = {k.find("span").get_text(strip=True): k.find("b").get_text(strip=True)
               for k in s.select(".gr-kacheln .gr-kachel")}
    assert set(kacheln) == {"Kritisch", "Mittel", "Gering", "Bestpreis"}

    # Die Summe der vier Kacheln IST die Zahl der verglichenen Geraete. Zwei
    # Zahlen, die dasselbe meinen muessen, gehoeren gegeneinander gehalten.
    # Der Betriebszahlensatz am Fuss ist am 03.09.2026 von der Seite gefallen
    # (Antonio: keine Erklaerkommentare auf der Geraeteseite) - die
    # Bestandszahlen stehen jetzt nur noch in der Aufbereitung, und genau da
    # werden sie gehalten. Sie rechnet auf dem BESTAND, nicht auf dem
    # Rohbestand: die gealterte Zwillingshaelfte traegt eine eigene `sku_id`
    # und zaehlte sonst als zweite Variante derselben Listung.
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    im_regal = [e for e in _DB["listungen"] if e["id"] in _bestand_ids()]
    assert geraete["bilanz"]["geraete"] == len({e["device_id"] for e in im_regal})
    assert geraete["bilanz"]["skus"] == len({e["sku_id"] for e in im_regal})
    assert geraete["bilanz"]["listungen"] == len(im_regal)
    # Die Kachelsumme zaehlt verglichene Geraete und kann deshalb nie ueber
    # dem Bestand liegen - der Fehlertyp von S3 ("2454 Modelle").
    assert sum(int(v) for v in kacheln.values()) <= len(im_regal)


def test_die_vier_kacheln_zaehlen_genau_die_verglichenen_geraete(tmp_path):
    """Eine Kachel, die anders zaehlt als die Tabelle unter ihr, ist derselbe
    Fehlertyp. Und ein Geraet ohne Wettbewerber ist NICHT unser Bestpreis -
    es ist gar nicht verglichen."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    summe = sum(int(k.find("b").get_text(strip=True))
                for k in s.select(".gr-kacheln .gr-kachel"))
    tafel = " ".join(s.select_one("#tafel-tco").get_text(" ", strip=True).split())
    assert f"{summe} Modelle mit ihren Speichergrößen stehen einem Wettbewerber gegenüber" in tafel


def test_kein_cdn_und_keine_chart_bibliothek(tmp_path):
    """Akzeptanzkriterium aus Teil E - und Hausregel des ganzen Portals."""
    site = _baue(tmp_path)
    roh = (site / "geraete.html").read_text(encoding="utf-8")
    assert "<svg" in roh
    for verboten in ("cdn.", "unpkg", "jsdelivr", "chart.js", "d3.", "plotly"):
        assert verboten not in roh.lower(), verboten


def _b_katalog(zustand_je_geraet=None):
    """Katalog mit drei Herstellern und je einer flagship- und einer
    mid/entry-Baureihe - genug, um Segment- und Baureihenordnung zu
    unterscheiden."""
    from telco_radar.geraete_model import Geraet, Katalog
    return Katalog(geraete=[
        Geraet(hersteller="Apple", modell="Apple X", generation=1,
               segment="flagship"),
        Geraet(hersteller="Samsung", modell="Galaxy S26 Ultra",
               generation=26, segment="flagship"),
        Geraet(hersteller="Samsung", modell="Galaxy S25 Ultra",
               generation=25, segment="flagship"),
        Geraet(hersteller="Samsung", modell="Galaxy A57", generation=57,
               segment="mid"),
        Geraet(hersteller="Google", modell="Pixel 11", generation=11,
               segment="flagship"),
    ])


def _b_zeile(hersteller, modell, zustand="neu", preis=1.0, anbieter="A",
            farbe="schwarz", speicher=256):
    from telco_radar.geraete_model import device_id
    return {"device_id": device_id(hersteller, modell), "anbieter": anbieter,
            "preis_ohne_vertrag": preis, "zuzahlung": None,
            "speicher_gb": speicher, "farbe_roh": farbe,
            "farbe_normalisiert": farbe, "zustand": zustand,
            "verfuegbarkeit": "lieferbar", "quelle_url": "", "abgerufen_am": ""}


def test_katalogzeilen_haelt_ein_geraet_in_einem_block_zusammen():
    """B6 der Zurueckweisung vom 31.08.2026 (Runde 1 der Nachbesserung war
    zurueckgewiesen worden, weil ihre reine Herstellermischung Zeilen
    DESSELBEN Geraets ueber die ganze Tabelle verteilte - 69 von 90
    Geraeten in bis zu zwoelf Bloecken. "Wer ein Geraet sucht, findet seine
    Zeilen beieinander" ist der Zweck dieses Reiters seit seinem Bau.

    Die Fixture verteilt ABSICHTLICH sieben Zeilen desselben Geraets ueber
    die Eingabe, dazwischen andere Hersteller - genau das Muster, an dem
    die reine Zeilenmischung scheiterte.
    """
    katalog = _b_katalog()
    eintraege = [
        _b_zeile("Samsung", "Galaxy S26 Ultra", anbieter="A", preis=999),
        _b_zeile("Apple", "Apple X"),
        _b_zeile("Samsung", "Galaxy S26 Ultra", anbieter="B", preis=899),
        _b_zeile("Google", "Pixel 11"),
        _b_zeile("Samsung", "Galaxy S26 Ultra", anbieter="C", zustand="refurbished", preis=799),
        _b_zeile("Samsung", "Galaxy A57"),
        _b_zeile("Samsung", "Galaxy S26 Ultra", anbieter="D", preis=949),
        _b_zeile("Apple", "Apple X"),
        _b_zeile("Samsung", "Galaxy S26 Ultra", anbieter="E", preis=929),
        _b_zeile("Samsung", "Galaxy S26 Ultra", anbieter="F", zustand="refurbished", preis=749),
        # Anbieter C ein zweites Mal, diesmal "neu" - deckt zwei Regeln
        # zugleich ab: `_katalog_zeile_schluessel` bevorzugt "neu"
        # INNERHALB desselben Anbieters unabhaengig vom Preis (C-neu/850
        # steht vor C-refurbished/799, obwohl 799 < 850), und C ruecht mit
        # seinem NEU-Preis (850) in die Gruppenreihenfolge ein, nicht mit
        # seinem refurbished-Preis.
        _b_zeile("Samsung", "Galaxy S26 Ultra", anbieter="C", zustand="neu", preis=850),
    ]
    zeilen = geraete_view.katalogzeilen(eintraege, katalog)
    assert len(zeilen) == len(eintraege), "eine Umsortierung darf keine Zeile verlieren"

    positionen = [i for i, z in enumerate(zeilen)
                 if z["hersteller"] == "Samsung" and z["modell"] == "Galaxy S26 Ultra"]
    assert positionen == list(range(positionen[0], positionen[0] + len(positionen))), (
        f"die sieben S26-Ultra-Zeilen stehen nicht zusammenhaengend: {positionen}")

    # Innerhalb des Blocks: REIHUM je Anbieter, dessen guenstigste Zeile
    # zuerst (P1, dritte Nachbesserung, 31.08.2026 -
    # `_interleave_je_anbieter_im_block`). Das ersetzt die fruehere
    # Zusicherung "neu komplett vor dem Rest" - die haette dem guenstigsten
    # ANBIETER erlaubt, mit seinen eigenen Farbvarianten allein die
    # sichtbaren Plaetze zu fuellen, und genau das hat der Coordinator an
    # den echten Daten gemessen (iPhone 17 Pro: 7 Zeilen, 3 Anbieter).
    block = zeilen[positionen[0]:positionen[-1] + 1]
    anbieter_je_zeile = [z["anbieter"] for z in block]
    assert anbieter_je_zeile == ["F", "C", "B", "E", "D", "A", "C"], (
        f"die Reihenfolge ist nicht reihum je Anbieter: {anbieter_je_zeile}")
    zustaende_je_zeile = [z["zustand"] for z in block]
    assert zustaende_je_zeile == ["refurbished", "neu", "neu", "neu", "neu",
                                  "neu", "refurbished"], (
        "C fuehrt nicht mit seiner NEU-Zeile trotz hoeherem Preis: "
        f"{list(zip(anbieter_je_zeile, zustaende_je_zeile))}")
    # Die ERSTEN BLOCK_SICHTBAR Zeilen sind zwei VERSCHIEDENE Anbieter (F,
    # C) - der Zweck der Deckelung.
    from telco_radar.report.geraete_view import BLOCK_SICHTBAR
    sichtbare_anbieter = {z["anbieter"] for z in block[:BLOCK_SICHTBAR]}
    assert len(sichtbare_anbieter) == BLOCK_SICHTBAR, (
        f"die ersten {BLOCK_SICHTBAR} Zeilen sind nicht {BLOCK_SICHTBAR} "
        f"verschiedene Anbieter: {sichtbare_anbieter}")
    block_rest_flags = [z["block_rest"] for z in block]
    assert block_rest_flags == [False, False, True, True, True, True, True], (
        f"block_rest markiert nicht genau die ersten {BLOCK_SICHTBAR} als "
        f"sichtbar: {block_rest_flags}")


def test_katalogzeilen_ordnet_nach_segment_nicht_nach_roher_generation():
    """B1 der Zurueckweisung vom 31.08.2026: die Nachbesserung sortierte
    flach nach `-generation` UEBER den ganzen Hersteller und reproduzierte
    damit den Fehler vom 29.08.2026 eine Ebene hoeher - eine Galaxy A57
    (Generation 57) schlug jede S- oder Z-Reihe (Generation <= 26), weil
    `generation` nur INNERHALB einer Baureihe eine Zahl ist.

    `segment` ist das Feld, das ueber Baureihen hinweg vergleichbar ist -
    diese Fixture haelt eine A57 (mid, Generation 57 - die hoechste Zahl
    der Fixture) gegen zwei flagship-Ultra-Modelle (Generation 25/26).
    """
    katalog = _b_katalog()
    eintraege = [
        _b_zeile("Samsung", "Galaxy A57"),
        _b_zeile("Samsung", "Galaxy S25 Ultra"),
        _b_zeile("Samsung", "Galaxy S26 Ultra"),
    ]
    zeilen = geraete_view.katalogzeilen(eintraege, katalog)
    modelle = [z["modell"] for z in zeilen]
    assert modelle.index("Galaxy A57") > modelle.index("Galaxy S26 Ultra"), (
        f"die Mittelklasse A57 steht vor dem Flaggschiff: {modelle}")
    # Innerhalb desselben Segments (flagship) zaehlt die Generation: S26
    # Ultra vor S25 Ultra.
    assert modelle.index("Galaxy S26 Ultra") < modelle.index("Galaxy S25 Ultra"), modelle


def test_katalogzeilen_mischt_bloecke_reihum_je_hersteller():
    """B5, jetzt auf BLOCK- statt Zeilenebene gemessen: unter den ersten
    drei BLOECKEN (nicht Zeilen) stehen drei verschiedene Hersteller,
    obwohl "Apple" in der Eingabe zuerst und mit den meisten Zeilen steht.
    """
    katalog = _b_katalog()
    eintraege = ([_b_zeile("Apple", "Apple X")] * 4
                + [_b_zeile("Samsung", "Galaxy S26 Ultra")]
                + [_b_zeile("Google", "Pixel 11")])
    zeilen = geraete_view.katalogzeilen(eintraege, katalog)
    erste_drei_hersteller = []
    for z in zeilen:
        if z["hersteller"] not in erste_drei_hersteller:
            erste_drei_hersteller.append(z["hersteller"])
        if len(erste_drei_hersteller) == 3:
            break
    assert set(erste_drei_hersteller) == {"Apple", "Samsung", "Google"}, zeilen


def test_katalogzeilen_ist_deterministisch_bei_gleichstand():
    """B8 der Zurueckweisung: ohne Farbe als Tiebreak blieb die Reihenfolge
    bei gleichem Betrag/Anbieter unterbestimmt und hing an der
    Eingabereihenfolge - 18 von 30 Mischungen derselben Daten lieferten
    eine andere Zeilenfolge. Zwei Zeilen desselben Geraets, derselbe
    Anbieter, derselbe Preis, nur die Farbe unterscheidet sie."""
    import random
    katalog = _b_katalog()
    eintraege = [
        _b_zeile("Apple", "Apple X", anbieter="A", preis=500, farbe="schwarz"),
        _b_zeile("Apple", "Apple X", anbieter="A", preis=500, farbe="blau"),
    ]
    erwartet = None
    random.seed(7)
    for _ in range(20):
        gemischt = list(eintraege)
        random.shuffle(gemischt)
        zeilen = geraete_view.katalogzeilen(gemischt, katalog)
        farben = tuple(z["farbe"] for z in zeilen)
        if erwartet is None:
            erwartet = farben
        assert farben == erwartet, (
            f"die Reihenfolge haengt an der Eingabe: {farben} != {erwartet}")


def test_katalogzeilen_stellt_einen_hersteller_ohne_katalogtreffer_ans_ende():
    """B9 der Zurueckweisung: die Docstring behauptete, eine Zeile ohne
    Katalogtreffer falle ans Ende ihrer Gruppe - `hersteller == ""` und
    `sorted(gruppen)` stellten den leeren String aber an den ANFANG, ihre
    Gruppe eroeffnete das Reihum."""
    katalog = _b_katalog()
    eintraege = [
        {"device_id": "unbekanntes-geraet", "anbieter": "A",
         "preis_ohne_vertrag": 1.0, "zuzahlung": None, "speicher_gb": 256,
         "farbe_roh": "Schwarz", "farbe_normalisiert": "schwarz",
         "zustand": "neu", "verfuegbarkeit": "lieferbar", "quelle_url": "",
         "abgerufen_am": ""},
        _b_zeile("Apple", "Apple X"),
    ]
    zeilen = geraete_view.katalogzeilen(eintraege, katalog)
    assert zeilen[0]["hersteller"] == "Apple", (
        "der Hersteller ohne Katalogtreffer fuehrt das Reihum an: "
        f"{[z['hersteller'] for z in zeilen]}")


def test_der_katalog_ist_eine_flache_tabelle(tmp_path):
    """Reiter 2 zeigt seit dem 30.08.2026 EINE Zeile je (Gerät, Speicher,
    Farbe, Anbieter) statt einer Matrix mit 65 Aufklappern.

    Der Unterschied ist nicht kosmetisch: eine Matrixzelle sagte "3
    Varianten, 799-899 EUR", und wer wissen wollte WELCHE, klappte zweimal
    auf. Jede Zeile trägt jetzt alles, was sie behauptet - Preis, Zustand,
    Verfügbarkeit, Quelle und Abrufdatum.
    """
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    kopf = [th.get_text(strip=True)
            for th in s.select("#gr-katalogtabelle thead th")]
    assert kopf == ["Gerät", "Farbe", "Anbieter", "Preis", "Zustand",
                    "Verfügbar", "Abgerufen"], kopf

    zeilen = s.select("#gr-katalogtabelle .gr-k-zeile")
    # Eine Zeile je Listung des BESTANDS, nicht je Gerät - das ist der ganze
    # Punkt der flachen Form. Ausgelistete Bestände bleiben in der Datenbank
    # (sie wird per Design nie geleert), gehören aber nicht ins Regal.
    #
    # Gezählt wird gegen `_bestand_ids()` und nicht gegen eine eigene
    # Statusabfrage. Die alte Fassung fragte `status in ("aktiv",
    # "beobachtet")` - "beobachtet" ist gar kein Status dieses Stores, und
    # damit fiel die gealterte Zwillingshälfte hier zufällig heraus. Der Test
    # hätte also gestimmt, ohne dass die Bereinigung überhaupt läuft.
    assert len(_bestand_ids()) < len(_DB["listungen"]), (
        "die Fixture hat weder eine ausgelistete Zeile noch einen Zwilling - "
        "dann misst dieser Vergleich nicht, dass wirklich gefiltert wird")
    assert len(zeilen) == len(_bestand_ids()), len(zeilen)
    # (Die Zeilen tragen keine Listungskennung; dass es DIE Kennungen des
    # Bestands sind, misst `test_der_export_zeigt_genau_den_bestand_der_seite`
    # an der CSV, die aus derselben Menge entsteht.)
    for z in zeilen:
        assert z.select_one(".gr-a-modell"), "Zeile ohne Modellnamen"
        assert z.select_one(".gr-a-datum"), "Zeile ohne Abrufdatum"
    # Die alte Matrix steht nicht mehr auf der Seite.
    assert s.select_one(".gr-matrix-tabelle") is None


def test_eine_unbekannte_verfuegbarkeit_ist_kein_alarm(tmp_path):
    """"unbekannt" heißt, dass die Quelle nichts gesagt hat - nicht, dass das
    Gerät fehlt. In Alarmrot gesetzt wäre bei o2 jede der 68 Zeilen rot,
    ohne dass irgendetwas fehlt."""
    db = json.loads(json.dumps(_DB))
    db["listungen"][0]["verfuegbarkeit"] = "unbekannt"
    site = _baue(tmp_path, db=db)
    s = _suppe(site, "geraete.html")
    pillen = [p for p in s.select("#gr-katalogtabelle .gr-pille")
              if "keine Angabe" in p.get_text()]
    assert pillen, "die Fixture spannt den Fall nicht auf"
    for p in pillen:
        klassen = p.get("class") or []
        assert "gr-pille--kritisch" not in klassen, klassen
        assert "gr-pille--unbekannt" in klassen, klassen


def test_lifecycle_sagt_dass_die_datenbasis_duenn_ist(tmp_path):
    """Akzeptanzkriterium: unter der Schwelle kein Trend, sondern ein Satz,
    der das sagt."""
    site = _baue(tmp_path, db=_DB_DUENN, punkte=_PUNKTE_DUENN)
    s = _suppe(site, "geraete.html")
    basis = s.select_one(".gr-basis")
    assert basis is not None
    assert "dünn" in basis.get_text()
    assert "gr-basis--duenn" in (basis.get("class") or [])
    # Und kein Trendblock.
    assert s.select_one(".gr-verfall") is None


def test_portfolio_tiefe_steht_auf_der_seite(tmp_path):
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    balken = s.select(".gr-tiefe li")
    assert balken
    namen = {b.select_one(".dz-balken-name").get_text(strip=True) for b in balken}
    assert "Medimax" in namen and "Vodafone" in namen


# --------------------------------------------------------------------------
# Die Quellenseite
# --------------------------------------------------------------------------

def test_quellenseite_nennt_jeden_konfigurierten_anbieter(tmp_path):
    """Akzeptanzkriterium aus Teil E: kein Anbieter fehlt stillschweigend."""
    site = _baue(tmp_path)
    roh = (site / "geraete-quellen.html").read_text(encoding="utf-8")
    for a in _QUELLEN["anbieter"]:
        assert a["name"] in roh, a["name"]


def test_jeder_nicht_angebundene_anbieter_nennt_seinen_grund(tmp_path):
    """Die Zusicherung der Seite: wer keine Daten liefert, sagt warum.

    Geprueft wird gegen die STAND-Spalte, nicht gegen die Beschaffungsart -
    ein Anbieter, der liefert, braucht keinen Grund, sondern hoechstens
    einen Hinweis. Beides nebeneinander laese sich wie ein Widerspruch
    ("liefert" und daneben "nicht angebunden, weil ...").
    """
    site = _baue(tmp_path)
    s = _suppe(site, "geraete-quellen.html")
    zeilen = s.select(".gr-quellen tbody tr")
    assert zeilen
    ohne_daten = 0
    for tr in zeilen:
        felder = tr.select("td")
        if "liefert" in felder[3].get_text(strip=True):
            continue
        ohne_daten += 1
        assert felder[5].get_text(strip=True), tr.get_text(strip=True)[:60]
    # Gegenprobe: gaebe es keine solche Zeile, pruefte die Schleife nichts.
    assert ohne_daten >= 1


def test_marken_ohne_hardware_stehen_in_einer_zeile_nicht_als_leere_kachel(tmp_path):
    site = _baue(tmp_path)
    s = _suppe(site, "geraete-quellen.html")
    ruhe = s.select_one(".gr-ruhe")
    assert ruhe is not None and "fraenk" in ruhe.get_text()
    # ... und NICHT in der Tabelle darueber.
    tabelle = s.select_one(".gr-quellen tbody").get_text()
    assert "fraenk" not in tabelle


def test_amazon_steht_mit_seinem_grund_da(tmp_path):
    site = _baue(tmp_path)
    roh = (site / "geraete-quellen.html").read_text(encoding="utf-8")
    assert "Product-Advertising-API" in roh


# --------------------------------------------------------------------------
# Der Zahlenwaechter
# --------------------------------------------------------------------------

def test_erfundene_zahl_wird_verworfen():
    """Akzeptanzkriterium aus Teil E, mit dem Gegenbeweis daneben: der Satz
    MIT gedeckten Zahlen besteht, der mit einer erfundenen faellt."""
    erlaubt = {1449.0, 1399.0, 50.0}
    assert pruefe_zahlen("Preis von 1449.00 € auf 1399.00 € gefallen.", erlaubt)
    assert not pruefe_zahlen("Preis von 1449.00 € auf 1299.00 € gefallen.", erlaubt)


def test_zahlen_im_text_liest_deutsche_und_englische_schreibweise():
    assert 1449.0 in zahlen_im_text("1.449,00 €")
    assert 1449.0 in zahlen_im_text("1449.00 EUR")
    assert 27.8 in zahlen_im_text("27,8 % gefallen")
    # Beide Schreibweisen: die Seite formatiert mit Punkt,
    # deutscher Fliesstext schreibt Komma.
    assert 27.8 in zahlen_im_text("27.8 % gefallen")
    assert 31.1 in zahlen_im_text("-31.1 %")
    assert zahlen_im_text("ohne Zahlen") == set()


def test_eine_modellbezeichnung_muss_angemeldet_sein():
    """Zwei Anlaeufe, zwei Fehler, eine Regel.

    Erst las der Waechter die 16 aus "iPhone 16 Pro Max" als Geldbetrag und
    verwarf einen wahren Satz. Dann prüfte er nur noch Zahlen MIT Einheit -
    und war damit fail OPEN: "Das iPhone kostet 999 Euro" kam vollstaendig
    erfunden durch, weil "Euro" ausgeschrieben stand.

    Jetzt wird JEDE Zahl geprueft, und die Zahlen der Eigennamen werden
    ausdruecklich angemeldet. Ein Name ist keine Behauptung - aber er muss
    bekannt sein, nicht ungeprueft.
    """
    satz = "iPhone 16 Pro Max bei Medimax: 100,00 € günstiger."
    assert not pruefe_zahlen(satz, {100.0}), "die 16 kam ungeprueft durch"
    assert pruefe_zahlen(satz, {100.0} | zahlen_der_namen("iPhone 16 Pro Max"))


def test_der_waechter_ist_fail_closed():
    """Der Befund, der den zweiten Anlauf gekippt hat: eine ausgeschriebene
    Einheit ist immer noch eine Behauptung."""
    for satz in ("Das iPhone kostet 999 Euro bei Medimax.",
                 "EUR 1299 bei Medimax.",
                 "Samsung senkt um 30 Prozent.",
                 "Bei o2 sind 12 Geräte ausgelistet."):
        assert not pruefe_zahlen(satz, set()), satz


def test_kein_satz_der_karte_nennt_eine_ungedeckte_zahl(tmp_path):
    """Die Sperre am echten Datensatz."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    daten = {abs(p["preis_ohne_vertrag"]) for p in _PUNKTE}
    daten |= {100.0, 1.0, 2.0, 10.0}
    # Die Zahlen der Eigennamen gehoeren dazu - sonst prueft dieser Test
    # nicht den Waechter, sondern nur, ob Modellnamen Ziffern enthalten.
    for g in _KATALOG["geraete"]:
        daten |= zahlen_der_namen(g["modell"])
    for a in _QUELLEN["anbieter"]:
        daten |= zahlen_der_namen(a["name"])
    saetze = [li.get_text(strip=True) for li in s.select(".gr-saetze li")]
    assert saetze, "keine Saetze - dann prueft dieser Test nichts"
    for satz in saetze:
        assert pruefe_zahlen(satz, daten), satz


# --------------------------------------------------------------------------
# Die Veroeffentlichungsschwelle
# --------------------------------------------------------------------------

# Genau so viele verschiedene LAEDEN, wie die Schwelle verlangt. Aus der
# Konstante abgeleitet und nicht abgeschrieben: wer die Schwelle aendert,
# soll nicht auch noch die Fixtures nachziehen muessen - und der Test soll
# nicht stillschweigend den falschen Zweig messen.
_UEBER_DER_SCHWELLE = ("Medimax", "ElectronicPartner", "Vodafone",
                       "fraenk")[:geraete_view.SCHWELLE_ANBIETER]


def _db_mit(anzahl_skus: int, anbieter: tuple = ("Medimax",)) -> dict:
    """Ein Bestand, der die Schwelle gezielt reisst oder nimmt.

    Jede Listung traegt eine EIGENE Farbe. Bis zum 30.08.2026 stand hier nur
    eine eigene `sku_id` (`farbe-{i}`), waehrend `farbe_normalisiert` bei
    allen auf dem Vorgabewert "titan-natur" blieb - der Fixture-Kommentar
    behauptete also eine Variation, die es nicht gab. Solange die
    Doppelpreisregel die Farbe nicht kannte, fiel das nicht auf; seit sie im
    Schluessel steht, ist ein Bestand aus 24 Preisen fuer EINE Farbe genau
    das, was sie aussortieren soll.

    Dieser Test misst die SCHWELLE, nicht die Preislogik; er braucht deshalb
    Daten, die die Preislogik passieren.
    """
    modelle = ("apple-iphone-17-pro-max", "samsung-galaxy-s25-ultra")
    listungen = []
    for i in range(anzahl_skus):
        name = anbieter[i % len(anbieter)]
        device = modelle[i % len(modelle)]
        listungen.append(_listung(name, device, f"{device}-256gb-farbe-{i}",
                                  399.0 + i * 3, farbe=f"farbe-{i}"))
    return {"updated": "2026-08-11",
            "anbieter": {n: {"laeufe": 4} for n in anbieter},
            "listungen": listungen}


def test_unter_der_schwelle_steht_die_seite_nicht_in_der_navigation(tmp_path):
    """Eine verlinkte Seite verspricht eine Antwort; eine Seite mit drei
    Geraeten gibt eine falsche. Dieselbe Regel wie bei tarife.html und
    lieferzeit.html - die Seite wird gebaut, getestet und ist ueber ihren
    direkten Link erreichbar, aber nicht verlinkt."""
    site = _baue(tmp_path, db=_db_mit(3))
    s = _suppe(site, "geraete.html")
    assert "geraete.html" not in {a.get("href") for a in s.select(".subnav a")}
    # Gegenprobe, dass der Fall wirklich UNTER der Schwelle liegt - sonst
    # prueft der Test bloss, dass drei kleiner als zwanzig ist.
    assert 3 < SCHWELLE_SKUS


def test_ueber_der_schwelle_erscheint_sie_auf_JEDER_seite(tmp_path):
    """Der Fehler vom 11.08.2026: die Schwelle stand nur im Test, also
    musste ein Mensch die Seite von Hand eintragen - und solange er das
    nicht tat, war sie unauffindbar. Jetzt schaltet der Code sie, und zwar
    in `base.html.j2`, also auf allen Seiten. Die Startseite ist die, auf
    der es zaehlt: dort hat Antonio gesucht."""
    site = _baue(tmp_path, db=_db_mit(24, anbieter=_UEBER_DER_SCHWELLE))
    for name in ("index.html", "meldungen.html", "wettbewerb.html",
                 "differenzierung.html", "transparenz.html", "geraete.html"):
        ziele = {a.get("href") for a in _suppe(site, name).select(".subnav a")}
        assert "geraete.html" in ziele, name


def test_die_seite_erklaert_ihre_eigene_bedienung_nicht(tmp_path):
    """Beruhigungsregel des Portals (CLAUDE.md §5)."""
    site = _baue(tmp_path)
    for name in ("geraete.html", "geraete-quellen.html"):
        text = _suppe(site, name).get_text(" ", strip=True).lower()
        for verboten in ("jede kachel zeigt", "klicken sie", "hier klicken",
                         "zum öffnen", "einfach anklicken"):
            assert verboten not in text, f"{name}: {verboten}"


def test_zaehlwerte_tragen_die_hausklasse(tmp_path):
    site = _baue(tmp_path)
    for name in ("geraete.html", "geraete-quellen.html"):
        roh = (site / name).read_text(encoding="utf-8")
        assert "count-badge" not in roh


# --------------------------------------------------------------------------
# Im echten Browser
# --------------------------------------------------------------------------

def _chromium():
    """Dieselbe Suche wie in tests/test_falz_browser.py - zwei Orte, weil es
    zwei Maschinen gibt (Sandbox und GitHub-Runner). Nur den ersten zu
    kennen hiesse, dass dieser Test auf der Maschine schweigt, die Merges
    absichert - und ein Skip sieht im Protokoll aus wie ein Erfolg."""
    import glob
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@pytest.fixture(scope="module")
def _gebaut(tmp_path_factory):
    return _baue(tmp_path_factory.mktemp("geraete-browser"))


@pytest.mark.parametrize("seite", ["geraete.html", "geraete-quellen.html"])
@pytest.mark.parametrize("breite,hoehe", [(1440, 900), (390, 844)])
def test_keine_seite_rollt_waagerecht(_gebaut, seite, breite, hoehe):
    """Die Preistabelle und die Bewegungsliste sind breiter als ein Telefon.
    Sie muessen IN SICH rollen - eine Seite, die waagerecht rollt, ist auf
    dem Telefon unbenutzbar. Gemessen, weil man es im HTML nicht sieht:
    ob ein `<code>application/ld+json</code>` die Seite verbreitert,
    entscheidet der Umbruch, also der Browser."""
    import contextlib
    import functools
    import http.server
    import socket
    import threading

    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    exe = _chromium()
    if exe is None:
        pytest.skip("kein Chromium gefunden")

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(_gebaut))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=exe,
                                         args=["--no-sandbox",
                                               "--disable-dev-shm-usage"])
            page = browser.new_page(viewport={"width": breite, "height": hoehe})
            page.goto(f"http://127.0.0.1:{port}/{seite}")
            page.wait_for_timeout(250)
            rollt = page.evaluate(
                "document.documentElement.scrollWidth > window.innerWidth + 1")
            schuldige = page.evaluate(
                """() => [...document.querySelectorAll('body *')]
                     .filter(e => e.getBoundingClientRect().right > window.innerWidth + 1
                               && !e.closest('.gr-scroll')
                               && !e.closest('.gr-matrix-scroll'))
                     .slice(0, 4)
                     .map(e => e.tagName + '.' + (e.className.baseVal !== undefined
                                                  ? e.className.baseVal : e.className))""")
            browser.close()
    finally:
        httpd.shutdown()
    assert not rollt, f"{seite} bei {breite}px: waagerechter Ueberlauf ({schuldige})"


def _bandpunkte():
    """Vier Modelle mit je vier Speicherstufen - die Lage, fuer die die
    Bandform gebaut ist. Mit sechzig EINZELmodellen in einer Spalte gaebe es
    keine Baender, sondern sechzig Striche, und kein Kappenetikett haette
    Platz; der Test praefte dann nur noch, dass nichts gezeichnet wird."""
    raus = []
    for m in range(4):
        for i, gb in enumerate((128, 256, 512, 1024)):
            p = _punkt(400.0 + m * 500 + i * 220, f"Modell {m} · {gb} GB",
                       device_id=f"modell-{m}")
            p["speicher"] = gb
            p["speicher_kurz"] = str(gb)
            p["modell"] = f"Modell {m}"
            raus.append(p)
    return raus


def _punkt(preis, label="Modell · 256 GB", spalte="Apple", eigen=False,
           device_id=None):
    # `device_id` und `shop` sind seit dem 11.08.2026 der Aggregations- und
    # der Bandschluessel. Ohne sie fielen alle Testpunkte zu EINEM zusammen,
    # und jeder Test hier prueefte nur noch die Verdichtung.
    return {"preis": preis, "label": label, "hersteller": spalte,
            "anbieter": spalte, "shop": spalte, "eigen": eigen, "segment": "",
            "speicher": 256, "modell": label.split(" · ")[0],
            "device_id": device_id or f"{spalte}-{label}".lower()}


def test_alte_preisbewegung_steht_nicht_unter_diese_woche(tmp_path):
    """Befund 5: eine Änderung vom 9. März stand in der Augustausgabe unter
    „Was diese Woche auffällt" - und blieb dort, bis sich der Preis wieder
    änderte."""
    root = tmp_path
    site = _baue(root)
    # Gegenprobe zuerst: mit frischen Punkten IST der Satz da.
    assert _suppe(site, "geraete.html").select(".gr-saetze li")

    alt = [dict(p, datum="2026-03-02" if i == 0 else "2026-03-09")
           for i, p in enumerate(_PUNKTE)]
    (root / "data" / "state" / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps(p) for p in alt) + "\n", encoding="utf-8")
    render_site(site, root / "data" / "reports")
    s = _suppe(site, "geraete.html")
    # NUR der Abschnitt "Was diese Woche auffaellt" - so steht es im Namen
    # dieses Tests und in seiner Beschreibung. Bis zum 28.08.2026 suchte er
    # im GESAMTEN Seitentext; seit die Seite eine Vergleichssektion hat, die
    # das Wort "guenstiger" in ihrer Ueberschrift fuehrt, haette er
    # angeschlagen, ohne dass eine alte Preisbewegung im Blick gestanden
    # haette. Der Gegenstand des Tests ist unveraendert, seine Zielscheibe
    # ist die richtige.
    abschnitt = s.select_one(".gr-auffaellig")
    text = abschnitt.get_text(" ", strip=True) if abschnitt else ""
    assert "günstiger" not in text and "teurer" not in text


def test_ein_anbieter_mit_daten_ohne_konfiguration_fehlt_nicht(tmp_path):
    """Befund 9: das Akzeptanzkriterium aus Teil E, verletzt unter dem Satz,
    der es verspricht. Die Datenbank löscht per Design nie - eine umbenannte
    Quelle bleibt also mit ihren Einträgen stehen."""
    root = tmp_path
    site = _baue(root)
    daten = json.loads(json.dumps(_DB))
    daten["listungen"].append(_listung(
        "Telekom", "apple-iphone-17-pro-max",
        "apple-iphone-17-pro-max-1024gb-schwarz", 1799.0, farbe="schwarz",
        speicher=1024))
    (root / "data" / "state" / "geraete_db.json").write_text(
        json.dumps(daten), encoding="utf-8")
    render_site(site, root / "data" / "reports")
    roh = (site / "geraete-quellen.html").read_text(encoding="utf-8")
    assert "Telekom" in roh
    assert "nicht konfiguriert" in roh


def test_zahl_ueber_der_quellentabelle_zaehlt_ihre_zeilen(tmp_path):
    """Befund 10: „Alle beobachteten Anbieter 23" über 21 Zeilen - der
    Fehlertyp aus CLAUDE.md §6."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete-quellen.html")
    zahl = int(s.select_one(".gr-quellen .rubrik-zahl").get_text(strip=True))
    assert zahl == len(s.select(".gr-quellen tbody tr"))


def test_ein_geraet_ohne_katalogeintrag_erzeugt_keine_namenlose_spalte(tmp_path):
    """Befund 12: `hersteller=""` ergab eine leere linke Spalte und sortierte
    den Slug in der Matrix nach oben."""
    root = tmp_path
    site = _baue(root)
    daten = json.loads(json.dumps(_DB))
    daten["listungen"].append(_listung(
        "Medimax", "xiaomi-redmi-note-14", "xiaomi-redmi-note-14-256gb-schwarz",
        299.0, farbe="schwarz"))
    (root / "data" / "state" / "geraete_db.json").write_text(
        json.dumps(daten), encoding="utf-8")
    render_site(site, root / "data" / "reports")
    s = _suppe(site, "geraete.html")
    spalten = [t.get_text(strip=True)
               for t in s.select("#gr-ansicht-hersteller .gr-spaltenname")]
    assert "" not in spalten, spalten
    # Und die Lücke steht da, statt sich als Modellname zu tarnen.
    assert "xiaomi-redmi-note-14" in (site / "geraete.html").read_text(encoding="utf-8")


def test_eine_unlesbare_datenbank_sieht_nicht_aus_wie_nichts_gefunden(tmp_path):
    """Befund 13: dieselbe Klasse wie der dokumentierte Fallstrick „Ein
    gescheiterter LLM-Aufruf darf nie wie ‚nichts gefunden' aussehen."""
    root = tmp_path
    site = _baue(root)
    (root / "data" / "state" / "geraete_db.json").write_text("{kaputt",
                                                             encoding="utf-8")
    render_site(site, root / "data" / "reports")
    text = _suppe(site, "geraete.html").get_text(" ", strip=True)
    assert "nicht lesbar" in text
    assert "noch keine Listung aufgenommen" not in text


def test_die_seite_entsteht_auch_wenn_die_aufbereitung_scheitert(tmp_path):
    """Befund 6: ein einziger kaputter Eintrag ließ BEIDE Seiten
    verschwinden - und weil site/ committet wird, blieb live die Fassung der
    Vorwoche stehen. Ein Totalausfall, der wie ein grüner Lauf aussieht."""
    root = tmp_path
    site = _baue(root)
    daten = json.loads(json.dumps(_DB))
    kaputt = _listung("Medimax", "apple-iphone-17-pro-max",
                      "kaputt-256gb-schwarz", 999.0)
    kaputt["anbieter"] = None      # so sieht ein halb geschriebener Store aus
    daten["listungen"].append(kaputt)
    (root / "data" / "state" / "geraete_db.json").write_text(
        json.dumps(daten), encoding="utf-8")
    render_site(site, root / "data" / "reports")
    assert (site / "geraete.html").exists()
    assert (site / "geraete-quellen.html").exists()


def test_preisverfall_nennt_seine_preisart(tmp_path):
    """Befund 11: eine Zeile auf Basis Zuzahlung und eine auf Basis
    Ladenpreis standen in derselben Spalte, nicht unterscheidbar - genau
    das, was Teil C4 für die Karte verbietet."""
    root = tmp_path
    site = _baue(root)
    daten = json.loads(json.dumps(_DB))
    punkte = list(_PUNKTE)
    for i in range(12):
        punkte.append({"listung_id": "medimax--apple-iphone-16-pro-max-256gb-schwarz",
                       "device_id": "apple-iphone-16-pro-max", "anbieter": "Medimax",
                       "datum": f"2026-0{1 + i // 3}-{1 + (i % 3) * 10:02d}",
                       "preis_ohne_vertrag": 999.0 - i * 5,
                       "verfuegbarkeit": "lieferbar", "quelle_url": "https://e.de/p"})
    (root / "data" / "state" / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps(p) for p in punkte) + "\n", encoding="utf-8")
    (root / "data" / "state" / "geraete_db.json").write_text(
        json.dumps(daten), encoding="utf-8")
    render_site(site, root / "data" / "reports")
    s = _suppe(site, "geraete.html")
    zeilen = s.select(".gr-verfall .list-row")
    assert zeilen, "genug Messpunkte, aber kein Verfallsblock"
    for li in zeilen:
        assert li.select_one(".gr-klein"), li.get_text(strip=True)[:70]


# --------------------------------------------------------------------------
# Die Befunde des dritten Reviews (11.08.2026)
# --------------------------------------------------------------------------

def test_die_seite_zeigt_keine_null_tage_zeilen(tmp_path):
    """Die Sektion, die zwei Bildschirmseiten lang nichts aussagte.

    Der Testbestand hat genau zwei Messpunkte an zwei Tagen - unter der
    Schwelle. Gegen den alten Stand gemessen stuenden hier Zeilen mit
    "0 Tage" und "+0.0 %".

    Die Pruefung war bis zum 31.08.2026 eine reine Teilkettensuche
    (`"0 Tage" not in text`) - ohne Wortgrenze traf sie auch "20 Tage",
    "30 Tage" oder jede andere Zahl, die auf eine Null endet. Genau das
    passierte, als der Nachfolger-Hinweis (P3) einen Satz mit "20 Tage"
    in dieselbe Sektion brachte: der Test fiel durch, obwohl keine echte
    "0 Tage"-Zeile auf der Seite stand. Repariert wird der TEST, nicht der
    Satz - eine Zahl, die auf 0 endet, ist keine Null. Die Gegenprobe
    unten haelt fest, dass eine ECHTE "0 Tage"-Zeile weiterhin durchfaellt,
    sonst waere die Reparatur nur ein stummgeschalteter Test."""
    import re

    def _hat_echte_null(text: str, muster: str) -> bool:
        # Negative Lookbehind auf eine Ziffer: "20 Tage" hat vor der "0"
        # eine "2", eine echte Null hat davor keine Ziffer.
        return re.search(rf"(?<!\d){re.escape(muster)}", text) is not None

    site = _baue(tmp_path, db=_DB_DUENN, punkte=_PUNKTE_DUENN)
    s = _suppe(site, "geraete.html")
    basis = s.select_one(".gr-basis")
    assert basis is not None
    # Die Klasse war im CSS angelegt und kam im HTML NULL Mal vor.
    assert "gr-basis--duenn" in (basis.get("class") or [])
    assert not s.select(".gr-dauern li"), "Verweildauer ohne Datenbasis"
    assert not s.select(".gr-verfall li"), "Preisverfall ohne Datenbasis"
    text = s.select_one(".gr-lifecycle").get_text(" ", strip=True)
    # Gegenprobe zuerst: der Testbestand ENTHAELT "20 Tage" (aus dem
    # Nachfolger-Hinweis) - waere die Pruefung noch die alte
    # Teilkettensuche, faellt dieser Test schon hier durch.
    assert "20 Tage" in text, "Testfall veraendert - Gegenprobe greift nicht"
    assert not _hat_echte_null(text, "0 Tage"), text
    assert not _hat_echte_null(text, "0.0 %"), text
    # Gegenprobe, dass die Pruefung nicht zahnlos geworden ist: eine ECHTE
    # Null-Zeile muss weiterhin auffallen.
    assert _hat_echte_null("Verweildauer: 0 Tage bei Testshop", "0 Tage")
    assert _hat_echte_null("Preisverfall: +0.0 % seit gestern", "0.0 %")
    # Und die zwei Textfehler von damals kommen nicht zurueck.
    assert "1 Wochen" not in text
    assert "ueber" not in text


def test_ohne_vorlauf_sagt_die_wochenkarte_was_sie_zeigt(tmp_path):
    """Teil B7 Punkt 3: solange es keinen frueheren Stand gibt, zeigt die
    Karte, was NEU ERFASST wurde - und sagt das auch so.

    Vorher stand die Sektion leer da, und "keine Auffaelligkeiten" ist etwas
    anderes als "noch nichts zu vergleichen"."""
    # EIN Messtag, und die Listungen sind an diesem Tag erstmals gesehen
    # worden - sonst gibt es einen Vorlauf und der Fall tritt nie ein.
    frisch = {"updated": "2026-08-11",
              "anbieter": {"Medimax": {"laeufe": 1, "funde_gesamt": 2}},
              "listungen": [
                  _listung("Medimax", "apple-iphone-17-pro-max",
                           "apple-iphone-17-pro-max-256gb-titan-natur", 1449.0,
                           first_seen="2026-08-11"),
                  _listung("Medimax", "samsung-galaxy-s25-ultra",
                           "samsung-galaxy-s25-ultra-256gb-schwarz", 1249.0,
                           farbe="schwarz", first_seen="2026-08-11"),
              ]}
    erstlauf = [{"listung_id": "medimax--apple-iphone-17-pro-max-256gb-titan-natur",
                 "device_id": "apple-iphone-17-pro-max", "anbieter": "Medimax",
                 "datum": "2026-08-11", "preis_ohne_vertrag": 1449.0,
                 "verfuegbarkeit": "lieferbar", "quelle_url": "https://example.de/p"}]
    site = _baue(tmp_path, db=frisch, punkte=erstlauf)
    s = _suppe(site, "geraete.html")
    abschnitt = s.select_one(".gr-auffaellig")
    assert abschnitt is not None, "die Sektion fehlt ganz"
    saetze = [li.get_text(" ", strip=True) for li in abschnitt.select(".gr-saetze li")]
    assert saetze, "kein einziger Satz"
    assert any("erfasst" in x and "vergleichen" in x for x in saetze), saetze
    # Die Kachel "0 ausgelistet" ist am 03.09.2026 mit der ganzen
    # Betriebszahlen-Sektion von der Seite gefallen. Eine Ersatz-Assertion
    # gegen die Wochenkarten-Saetze wurde bewusst NICHT gebaut: kein
    # Satztemplate dieses Abschnitts kann das Wort "ausgelistet" ueberhaupt
    # tragen (geraete_view, Saetze 542-623) - ein Test, der nie schlagen
    # kann, prueft nichts (CLAUDE.md 6).


def test_jede_zahl_der_wochenkarte_stammt_aus_dem_datensatz(tmp_path):
    """Der Zahlenwaechter, mit Gegenprobe: eine erfundene Zahl muss fallen.

    Ohne die Gegenprobe belegt der Test nur, dass die echten Saetze
    durchkommen - nicht, dass der Waechter ueberhaupt greift."""
    from telco_radar.report.geraete_view import pruefe_zahlen
    erlaubt = {85.0, 1449.0}
    assert pruefe_zahlen("85 Geräte erstmals erfasst.", erlaubt)
    assert not pruefe_zahlen("86 Geräte erstmals erfasst.", erlaubt)
    assert not pruefe_zahlen("Der Preis fiel um 12,5 %.", erlaubt)


def test_eine_lange_beobachtung_erscheint_sehr_wohl_auf_der_seite(tmp_path):
    """Die Gegenprobe zur Schwelle: ohne sie belegt der Test oben nur, dass
    die Sektion IMMER leer ist.

    Der Normalfall-Bestand laeuft seit dem 01.07.2026 bei vier Laeufen - das
    ist eine belastbare Verweildauer, und sie gehoert auf die Seite."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    basis = s.select_one(".gr-basis")
    assert "gr-basis--duenn" not in (basis.get("class") or []), basis.get_text()
    zeilen = s.select(".gr-dauern li")
    assert zeilen, "eine 41 Tage alte Listung ergibt sehr wohl eine Zeile"
    assert not any("0 Tage" in z.get_text() for z in zeilen)


# --------------------------------------------------------------------------
# "Wer ist guenstiger als Vodafone?" auf der gerenderten Seite (G2)
# --------------------------------------------------------------------------

def _db_mit_vergleich():
    """Ein Bestand, in dem Vodafone einmal teurer und einmal konkurrenzlos
    ist - beide Faelle muessen auf der Seite stehen."""
    return {"updated": "2026-08-11", "anbieter": {
        "Medimax": {"laeufe": 4, "funde_gesamt": 8},
        "Vodafone": {"laeufe": 4, "funde_gesamt": 4},
    }, "listungen": [
        _listung("Vodafone", "apple-iphone-17-pro-max",
                 "apple-iphone-17-pro-max-256gb-titan-natur", 1349.0),
        _listung("Medimax", "apple-iphone-17-pro-max",
                 "apple-iphone-17-pro-max-256gb-titan-natur-mx", 1199.0),
        _listung("ElectronicPartner", "apple-iphone-17-pro-max",
                 "apple-iphone-17-pro-max-256gb-titan-natur-ep", 1279.0),
        # Hier ist Vodafone der guenstigste - die Zeile bleibt trotzdem stehen.
        _listung("Vodafone", "apple-iphone-16-pro-max",
                 "apple-iphone-16-pro-max-256gb-schwarz-vf", 799.0, farbe="schwarz"),
        _listung("Medimax", "apple-iphone-16-pro-max",
                 "apple-iphone-16-pro-max-256gb-schwarz", 899.0, farbe="schwarz"),
        # Und das hier fuehrt Vodafone gar nicht.
        _listung("Medimax", "samsung-galaxy-s25-ultra",
                 "samsung-galaxy-s25-ultra-256gb-schwarz", 1249.0, farbe="schwarz"),
    ]}


def test_die_alarmtabelle_nennt_den_guenstigsten_mit_namen(tmp_path):
    """Die woertliche Anforderung: nicht DASS es guenstiger ist, sondern
    BEI WEM."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    tafel = s.select_one("#tafel-tco")
    assert tafel is not None, "der Reiter fehlt ganz"
    text = tafel.get_text(" ", strip=True)
    assert "Medimax" in text, "der guenstigste Wettbewerber steht mit Namen da"
    assert "150,00" in text, "die Differenz steht da (1349 - 1199)"
    assert "11,1" in text, "und der Prozentsatz"


def test_der_prozentsatz_steht_groesser_als_der_eurobetrag(tmp_path):
    """Vorgabe des Auftrags, und sie ist richtig: 15 Euro sind bei einem
    200-Euro-Geraet viel und bei einem 2000-Euro-Geraet nichts. Der
    Prozentsatz ist die vergleichbare Zahl, der Euro-Betrag ihr Beleg."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    zeile = s.select_one("#tafel-tco .gr-a-zeile")
    assert zeile is not None, "keine einzige Alarmzeile"
    assert "%" in zeile.select_one(".gr-a-prozent").get_text(strip=True)
    assert "€" in zeile.select_one(".gr-a-euro").get_text(strip=True)


def test_jede_alarmzeile_traegt_quelle_und_abrufdatum(tmp_path):
    """"Kein Vergleich ohne beide Quelllinks und beide Abrufdaten." Auf der
    Seite gemessen, nicht nur in der Rechnung."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    zeilen = s.select("#tafel-tco .gr-a-zeile")
    assert zeilen, "keine einzige Alarmzeile"
    for zeile in zeilen:
        assert zeile.select_one("a.gr-a-quelle[href]"), "Wettbewerber ohne Quelllink"
        # `.gr-a-datum`, nicht `.gr-a-klein`: die zweite Klasse traegt auch
        # die Speichergroesse, und damit war diese Zusicherung wirkungslos.
        assert zeile.select_one(".gr-a-datum"), "Zeile ohne Abrufdatum"
        auf = s.select_one("#" + zeile["data-auf"])
        assert auf is not None, "Zeile ohne Aufklapper"
        # Der Aufklapper traegt BEIDE Seiten - unsere Listung und die fremde.
        assert auf.select("a[href]"), "Aufklapper ohne Quelllink"


def test_der_aufklapper_listet_alle_anbieter_dieses_geraets(tmp_path):
    """Der Klick auf eine Zeile zeigt die ganze Lage, nicht nur den Sieger -
    unseren eigenen Preis eingeschlossen."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    zeile = s.select_one("#tafel-tco .gr-a-zeile")
    auf = s.select_one("#" + zeile["data-auf"])
    namen = [li.find("span").get_text(strip=True) for li in auf.select(".gr-a-liste li")]
    # LADENnamen, nicht Markennamen: die Testkonfiguration fuehrt
    # ElectronicPartner unter `shop: ep`. Verglichen werden Laeden - sonst
    # zaehlte derselbe Shop unter zwei Marken zweimal als "guenstiger".
    assert {"Medimax", "ep"} <= set(namen)
    assert "Vodafone" in namen, "unser eigener Preis fehlt im Aufklapper"


def test_die_zeile_ohne_guenstigeren_wettbewerber_steht_nicht_mehr_da(tmp_path):
    """Die Umkehr vom 30.08.2026, und sie ist der Kern des Auftrags:
    "niemand guenstiger" stand 36-mal in der alten Tabelle. Das ist keine
    Aussage, das ist eine leere Zeile mit Text darin - die Kachel "Bestpreis"
    sagt dasselbe einmal.
    """
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    tafel = s.select_one("#tafel-tco")
    assert "niemand günstiger" not in tafel.get_text(" ", strip=True)

    # Gegenprobe: der Fall tritt wirklich ein, sonst misst der Test nichts -
    # es MUSS ein Geraet geben, bei dem niemand unterbietet.
    bestpreis = next(k for k in s.select(".gr-kacheln .gr-kachel")
                     if k.find("span").get_text(strip=True) == "Bestpreis")
    assert int(bestpreis.find("b").get_text(strip=True)) > 0


def test_was_vodafone_nicht_fuehrt_steht_als_eigener_befund(tmp_path):
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    luecke = s.select_one(".gr-vergleich-luecke")
    assert luecke is not None
    text = luecke.get_text(" ", strip=True)
    assert "Bei Wettbewerbern gelistet, bei Vodafone nicht" in text
    assert "Galaxy S25 Ultra" in text
    # Der Aufklapper ist am 03.09.2026 mit der ganzen Erklaersektion vom
    # Seitenfuss in den Portfolio-Reiter gezogen worden (er ist eine
    # Sortiments-Aussage, kein Kommentar) - und diese Zugehoerigkeit hier
    # festgenagelt, sonst wandert er beim naechsten Umbau unbemerkt zurueck.
    assert any(el.get("id") == "tafel-portfolio" for el in luecke.parents), (
        "der Aufklapper steht nicht im Portfolio-Reiter")


def test_die_abrufdaten_stehen_deutsch_nicht_als_iso(tmp_path):
    """Zielgruppe sind Manager ohne Technikhintergrund - der Rest des
    Portals schreibt deutsche Daten, diese Sektion tat es zuerst nicht.
    Beim ANSEHEN des Screenshots aufgefallen, nicht im Test."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    gemessen = 0
    for datum in s.select("#tafel-tco .gr-a-klein, #tafel-tco .gr-a-liste span"):
        text = datum.get_text(strip=True)
        if not text or not text[0].isdigit():
            continue
        gemessen += 1
        assert "-" not in text, f"ISO-Datum auf der Seite: {text!r}"
    assert gemessen, "kein einziges Datum gemessen - der Test prueft nichts"


def test_die_filterleiste_steht_bereit_und_zeigt_ihren_zuschnitt(tmp_path):
    """Marke, Modell und Speicher sind eine Auswahl; Zustand und Preisart
    sind es NICHT - der Vergleich zeigt ausschliesslich Neugeraete ohne
    Vertrag. Sie stehen deshalb als aktive Etiketten und nicht als
    Auswahlfelder: ein Bedienelement, das nichts aendern kann, ist keins."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    felder = [f.get("data-filter") for f in s.select("#tafel-tco [data-filter]")]
    assert felder == ["marke", "modell", "speicher", "suche"]

    fest = [e.get_text(" ", strip=True)
            for e in s.select("#tafel-tco .gr-filter label.gr-filter--an")]
    assert fest == ["Zustand: neu", "Preisart: ohne Vertrag"]

    # Jede Zeile traegt die Werte, nach denen gefiltert wird.
    for zeile in s.select("#tafel-tco .gr-a-zeile"):
        assert zeile.has_attr("data-marke")
        assert zeile.has_attr("data-modell")
        assert zeile.has_attr("data-speicher")


def test_ohne_vergleichsdaten_steht_die_sektion_gar_nicht_da(tmp_path):
    """Ein leerer Kasten mit Ueberschrift sagt "kaputt", nicht "noch keine
    Daten"."""
    ohne = {"updated": "2026-08-11", "anbieter": {}, "listungen": []}
    site = _baue(tmp_path, db=ohne, punkte=[])
    s = _suppe(site, "geraete.html")
    assert s.select_one("#tafel-tco") is None


# --------------------------------------------------------------------------
# G4: die Wochenkarte rechnet, sie erzaehlt nicht (29.08.2026)
# --------------------------------------------------------------------------

def test_jede_zahl_der_wochenkarte_steht_so_im_datensatz(tmp_path):
    """Der Auftrag verlangt: "Vollstaendig deterministisch, ohne LLM-Aufruf.
    Jede Zahl im Text stammt aus dem Datensatz."

    Bei einer gerechneten Sektion gibt es kein Modell, das etwas erfinden
    koennte - die Zusicherung ist trotzdem pruefbar, und zwar so: jede Zahl,
    die in den Saetzen steht, muss sich aus der Datenbank oder der
    Preishistorie herleiten lassen. Erfundene Zahlen fielen hier auf."""
    import re

    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    abschnitt = s.select_one(".gr-auffaellig")
    assert abschnitt is not None, "die Wochenkarte fehlt"
    saetze = [li.get_text(" ", strip=True)
              for li in abschnitt.select(".gr-saetze li")]
    assert saetze, "kein einziger Satz"

    # Alles, was aus den Daten belegbar ist: Preise, Deltas, Anzahlen.
    erlaubt = set()
    for e in _DB["listungen"]:
        for feld in ("preis_ohne_vertrag", "erstpreis", "speicher_gb"):
            if e.get(feld) is not None:
                erlaubt.add(f"{float(e[feld]):.0f}")
    for p in _PUNKTE:
        if p.get("preis_ohne_vertrag") is not None:
            erlaubt.add(f"{float(p['preis_ohne_vertrag']):.0f}")
    # Zaehlwerte: hoechstens so viele wie Listungen bzw. Punkte.
    erlaubt |= {str(n) for n in range(0, len(_DB["listungen"]) + 1)}
    erlaubt |= {str(n) for n in range(0, len(_PUNKTE) + 1)}
    # Differenzen zwischen zwei belegten Preisen.
    preise = [float(p["preis_ohne_vertrag"]) for p in _PUNKTE
              if p.get("preis_ohne_vertrag") is not None]
    for a in preise:
        for b in preise:
            erlaubt.add(f"{abs(a - b):.0f}")

    # Geprueft werden die MESSWERTE, nicht jede Ziffer: in "iPhone 16 Pro
    # Max" steckt eine 16, die zum Namen gehoert und zu keiner Rechnung.
    # Ein Messwert ist in diesen Saetzen daran erkennbar, dass er eine
    # Einheit traegt (Euro) oder als Zaehlwert vor einem Substantiv steht.
    gemessen = re.findall(r"(\d[\d.]*),\d\d\s*€|(\d[\d.]*)\.\d\d\s*€", " ".join(saetze))
    werte = [a or b for a, b in gemessen]
    assert werte, f"kein einziger Messwert in {saetze!r}"
    for roh in werte:
        zahl = roh.replace(".", "")
        assert zahl in erlaubt, (
            f"Wert {roh!r} in {saetze!r} laesst sich nicht aus dem "
            f"Datensatz herleiten")


def test_die_geraeteseite_entsteht_ohne_jeden_netz_oder_modellaufruf(tmp_path,
                                                                     monkeypatch):
    """Der Provider war beim Lauf vom 25.08. ohne Guthaben (HTTP 402). Die
    ganze Geraeteseite - Wochenkarte, Vergleich, Export - muss trotzdem
    stehen: sie ist gerechnet, nicht geschrieben.

    Geprueft wird an der Wurzel: jeder ausgehende HTTP-Aufruf fliegt. Ein
    Modellaufruf ginge durch dieselbe Tuer."""
    import httpx

    def _verboten(*a, **kw):
        raise AssertionError("die Geraeteseite darf nichts abrufen")

    monkeypatch.setattr(httpx, "get", _verboten, raising=False)
    monkeypatch.setattr(httpx, "post", _verboten, raising=False)
    monkeypatch.setattr(httpx.Client, "request", _verboten, raising=False)

    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    assert s.select_one(".gr-auffaellig .gr-saetze li") is not None
    assert s.select_one("#tafel-tco") is not None


def test_kein_iso_datum_steht_sichtbar_auf_der_geraeteseite(tmp_path):
    """Zielgruppe sind Manager ohne Technikhintergrund, und das Portal
    schreibt sonst deutsche Daten. "2026-08-27" ist eine Maschinenschreibung.

    Beim Ansehen der gerenderten Seite gefunden - zweimal: im Seitenkopf
    ("Stand") und in der Export-Zeile."""
    import re

    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    for knoten in s.select(".page-date, .gr-export-meta, .gr-v-datum"):
        text = knoten.get_text(" ", strip=True)
        assert not re.search(r"\d{4}-\d{2}-\d{2}", text), \
            f"ISO-Datum sichtbar: {text!r}"


# --------------------------------------------------------------------------
# W1.1: die Preisgrafik zeigt nur Neugeraete
# --------------------------------------------------------------------------

def test_die_pruefung_schaltet_die_navigation_nicht(tmp_path):
    """Befund des Reviews vom 29.08.2026: `schwelle_erreicht` nahm die
    Spaltenzahl der Herstelleransicht, und die hängt seit W1.2 an der
    Plausibilitätsprüfung. Damit hätte ein Anbieter, der an einem Tag seine
    Farbvarianten mit großem Abstand bepreist, den Navigationseintrag
    „Geräte" auf JEDER Seite verschwinden lassen – ohne Fehler, ohne
    Warnung. Eine Datenqualitätsheuristik darf keine Navigation schalten.

    Die Fixture spannt genau diesen Fall auf: verschiedene Preise für
    dieselbe (Anbieter, Modell, Speicher, Zustand, FARBE)-Gruppe. Die Prüfung
    räumt sie ab – die Schwelle muss trotzdem stehen."""
    db = _db_mit(24, anbieter=_UEBER_DER_SCHWELLE)
    for i, listung in enumerate(db["listungen"]):
        listung["preis_ohne_vertrag"] = 399.0 + i * 15
        # DIESELBE Farbe: seit dem 30.08.2026 ist nur das ein Doppelpreis.
        # Eine weite Spanne über verschiedene Farben ist der Markt.
        listung["farbe_roh"] = "Titan Natur"
        listung["farbe_normalisiert"] = "titan-natur"

    site = _baue(tmp_path, db=db)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")

    # Gegenprobe: der Fall tritt wirklich ein, sonst misst der Test nichts.
    assert geraete["pruefung"]["aussortiert"] > 0, "Prüfung greift gar nicht"
    assert geraete["bilanz"]["schwelle_erreicht"] is True
    ziele = {a.get("href") for a in _suppe(site, "index.html").select(".subnav a")}
    assert "geraete.html" in ziele


def test_der_pruefbericht_nennt_dieselben_zahlen_wie_die_pruefung(tmp_path):
    """Die neue Sektion auf /geraete-quellen.html wurde von keinem Test
    gerendert – und zeigte deshalb zweimal die Zahl der BEFUNDE, wo die Zahl
    der aussortierten LISTUNGEN gemeint war. Genau der Fehlertyp aus
    CLAUDE.md §6: ein Etikett und ein Feld, die nicht dasselbe meinen."""
    db = _db_mit(24, anbieter=_UEBER_DER_SCHWELLE)
    for i, listung in enumerate(db["listungen"]):
        listung["preis_ohne_vertrag"] = 399.0 + i * 15
        listung["farbe_roh"] = "Titan Natur"
        listung["farbe_normalisiert"] = "titan-natur"
    # Eine zweite Befundart, damit die Vorlage nicht nur ihren ersten Zweig
    # zeigt: der `zustand_veraltet`-Fall hat weder `preise` noch `median`
    # und lief bis zum Review in den Ausreisser-Zweig - mit einem
    # Jinja-Fehler, der die ganze Seite riss.
    db["listungen"][0]["titel_roh"] = "Apple iPhone 17 Pro Max (erneuert) 256 GB"

    site = _baue(tmp_path, db=db)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    zahlen = geraete["pruefung"]
    assert zahlen["zustand_veraltet"] >= 1 and zahlen["doppelpreise"] >= 1, (
        "die Fixture spannt nicht beide Befundarten auf")
    assert zahlen["aussortiert"] != zahlen["entfernt"], (
        "die Fixture trennt die zwei Zahlen nicht - dann misst der Test nichts")

    s = _suppe(site, "geraete-quellen.html")
    abschnitt = s.select_one(".gr-pruefung")
    assert abschnitt is not None, "der Prüfbericht fehlt auf der Seite"
    text = abschnitt.get_text(" ", strip=True)
    assert f"{zahlen['geprueft']} Preiszeilen geprüft" in text
    assert f"{zahlen['aussortiert']} aus dem Vergleich genommen" in text
    assert f"{zahlen['befunde']} Auffälligkeiten" in text
    assert abschnitt.select_one(".rubrik-zahl").get_text(strip=True) == str(
        zahlen["aussortiert"])
    assert len(abschnitt.select("tbody tr")) == zahlen["befunde"]


def test_die_katalogzeile_nennt_den_ABGELEITETEN_zustand(tmp_path):
    """Der Katalog zeigt gebrauchte Geräte bewusst mit - dann muss die Zeile
    auch „refurbished" sagen und nicht den Store-Wert.

    Der Vorgänger dieses Tests hing an der gelöschten SKU-Matrix und prüfte,
    dass deren Preisspanne keinen Gebrauchtpreis enthält. Die flache Tabelle
    trifft eine andere, schärfere Zusicherung: sie zeigt die Zeile, sagt aber
    dazu, was sie ist. Ohne die Ableitung stünde dort „space schwarz
    erneuert · Zustand neu", während der Prüfbericht zwei Reiter weiter
    „refurbished" meldet - die Seite widerspräche sich selbst.

    GEÄNDERT AM 31.08.2026, und zwar am Suchkriterium, nicht an der
    Zusicherung: der Reiter zeigt seit der Trennung der zwei Mengen den
    BEREINIGTEN Bestand, und dort steht das Wort „erneuert" nicht mehr in
    der Farbspalte - das ist der Zweck von `bereinige()`. Über den Text
    gesucht fand der Test seine Zeile deshalb nicht mehr. Gesucht wird sie
    jetzt über Gerät und Anbieter, und die Zusicherung ist dadurch schärfer
    geworden: das Kennzeichen muss von der Farbspalte in die Zustandsspalte
    GEWANDERT sein, nicht verschwunden. Genau das kann es: `bereinige()`
    schreibt den abgeleiteten Zustand fest, bevor es die Farbe säubert.
    """
    db = json.loads(json.dumps(_DB))
    # Der echte o2-Fall: das Kennzeichen steht NUR in der Farbe, der Store
    # trägt weiter "neu".
    db["listungen"][0]["farbe_roh"] = "Space Schwarz erneuert"
    db["listungen"][0]["farbe_normalisiert"] = None
    db["listungen"][0]["zustand"] = "neu"
    assert db["listungen"][0]["zustand"] != "refurbished"
    assert "erneuert" not in db["listungen"][0]["quelle_url"], (
        "die Fixture soll den Fall 'nur in der Farbe' aufspannen")
    site = _baue(tmp_path, db=db)
    s = _suppe(site, "geraete.html")

    zeilen = s.select("#gr-katalogtabelle .gr-k-zeile")
    treffer = [z for z in zeilen
               if z.get("data-anbieter") == "Medimax"
               and "iPhone 17 Pro Max" in (z.get("data-s-geraet") or "")
               and (z.get("data-speicher") or "") == "256"]
    assert treffer, "die Fixture spannt den Fall nicht auf"
    for z in treffer:
        assert z.get("data-zustand") == "refurbished", z.get("data-zustand")
        assert "refurbished" in z.get_text()
        # Und das Wort steht nicht mehr zusätzlich in der Farbe - dieselbe
        # Aussage zweimal, einmal an der falschen Stelle, war der Anlass
        # für `geraete_bereinigung`.
        assert "erneuert" not in (z.get("data-s-farbe") or "").lower()


def test_die_geraetespalte_des_katalogs_bleibt_beim_scrollen_stehen(tmp_path):
    """Die Tabelle rollt waagerecht; ohne festgestellte erste Spalte weiss
    niemand mehr, zu welchem Geraet eine Zeile gehoert."""
    site = _baue(tmp_path)
    css = (site / "style.css").read_text(encoding="utf-8")
    assert ".gr-alarm-scroll" in css
    assert s_hat_scroll(_suppe(site, "geraete.html"))


def s_hat_scroll(suppe):
    behaelter = suppe.select_one("#gr-katalogtabelle")
    return behaelter is not None and behaelter.find_parent(
        class_="gr-alarm-scroll") is not None

def test_keine_geraetezahl_auf_der_seite_ist_groesser_als_der_bestand(tmp_path):
    """Das Akzeptanzkriterium, gemessen an der WIRKLICH gerenderten Seite.

    Zwei Fälle hat diese Regel schon gefangen: „267 Geräte neu im Regal" bei
    59 beobachteten (W3) und „62 Geräte im Vergleich" bei denselben 59 – der
    zweite fiel erst beim Gegenlesen der fertigen Seite auf, weil der Test
    davor nur die zwei bekannten Funktionen prüfte und nicht die Seite.

    Gesucht wird jede Zahl, die unmittelbar vor dem Wort „Gerät"/„Geräte"
    steht. Sie kann nie größer sein als der beobachtete Bestand."""
    import re

    # Die Fixture muss den Fall AUSLOESEN koennen: mehr Vergleichszeilen als
    # Geraete. Das entsteht nur, wenn ein Geraet mit zwei Speichergroessen
    # gelistet ist - mit einer Groesse je Geraet sind Zeilen und Geraete
    # dieselbe Zahl, und der Test misst eine Regel, die gar nicht greifen
    # kann.
    db = _db_mit(24, anbieter=_UEBER_DER_SCHWELLE)
    zusatz = []
    for listung in db["listungen"]:
        weitere = dict(listung)
        weitere["speicher_gb"] = 512
        weitere["sku_id"] = listung["sku_id"] + "-512"
        weitere["id"] = listung["id"] + "-512"
        weitere["preis_ohne_vertrag"] = listung["preis_ohne_vertrag"] + 100
        zusatz.append(weitere)
    db["listungen"] = db["listungen"] + zusatz

    # ERSTLAUF statt Normalfall: Der Betriebszahlensatz am Fuss ("59 Geräte
    # in 250 Varianten"), der letzte garantierte Ort einer Gerätezahl, ist
    # am 03.09.2026 mit der ganzen Erklaersektion von der Seite gefallen.
    # Der lebende Ort ist seitdem die Wochenkarte ("wurden N Geräte erstmals
    # erfasst") - und die entsteht nur ohne frueheren Stand. Ohne diesen
    # Zusatz faende der Test keine einzige Gerätezahl und misste nichts.
    for listung in db["listungen"]:
        listung["first_seen"] = "2026-08-11"
    erste = [{"listung_id": l["id"], "device_id": l["device_id"],
              "anbieter": l["anbieter"], "datum": "2026-08-11",
              "preis_ohne_vertrag": l["preis_ohne_vertrag"],
              "verfuegbarkeit": l.get("verfuegbarkeit", "lieferbar"),
              "quelle_url": l.get("quelle_url", "https://example.de/p")}
             for l in db["listungen"]]

    site = _baue(tmp_path, db=db, punkte=erste)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    bestand = geraete["bilanz"]["geraete"]
    assert bestand, "kein Bestand - dann prüft der Test nichts"

    suppe = _suppe(site, "geraete.html")
    # Gegenprobe: die Fixture muss die Abschnitte WIRKLICH rendern. Ohne sie
    # lief dieser Test an genau der Sektion vorbei, in der der zweite Fall
    # stand („62 Geräte im Vergleich") - ein Test, dessen Lookup ins Leere
    # geht, ist grün und prüft nichts (CLAUDE.md §6).
    for auswahl in ("#tafel-tco", ".gr-katalog", "#tafel-katalog"):
        assert suppe.select_one(auswahl), f"{auswahl} fehlt in der Fixture"
    zeilen = len(geraete["vergleich"]["ohne_vertrag"]["zeilen"])
    assert zeilen > bestand, (
        f"{zeilen} Zeilen bei {bestand} Geraeten - die Fixture kann den Fall "
        f"nicht ausloesen, der Test prueft dann nichts")

    text = suppe.get_text(" ", strip=True)
    treffer = [int(n) for n in re.findall(r"(\d+)\s+Gerät(?:e|en)?\b", text)]
    assert treffer, "keine Gerätezahl gefunden - der Test misst nichts"
    zu_gross = [n for n in treffer if n > bestand]
    assert not zu_gross, (
        f"{zu_gross} übersteigen die {bestand} beobachteten Geräte")



def test_jeder_anbieter_steht_in_genau_einem_von_drei_zustaenden(tmp_path):
    """Der Auftrag, Abschnitt 4.1: "Die Kategorie 'gemessen, aber ohne
    Adapter' wird abgebaut, nicht gepflegt. Am Ende steht jeder Anbieter in
    genau einem von drei Zuständen."

    Die vierte Kategorie sagte nichts aus - sie stand für "könnte man bauen"
    und blieb stehen, ohne dass jemand entschied. Die drei Zahlen müssen sich
    auf die Zahl der konfigurierten Anbieter summieren; damit kann eine
    vierte nicht unbemerkt zurückwachsen.
    """
    _baue(tmp_path)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    q = geraete["quellenlage"]

    zustaende = {z["zustand"] for z in q["zeilen"] + q["ohne_hardware"]}
    assert zustaende <= {"liefert", "ohne_daten", "ohne_hardware"}, zustaende
    # Gezaehlt wird ueber die KONFIGURIERTEN. Ein Anbieter, der nur noch in
    # der Datenbank steht (umbenannt, entfernt), steht in `zeilen`, gehoert
    # aber nicht in diese Summe - sonst braeche die Invariante beim ersten
    # Umbenennen, ohne dass ein Fehler vorlaege.
    assert q["liefernd_konfiguriert"] + q["ohne_daten"] + \
        q["ohne_hardware_zahl"] == q["konfiguriert"], q

    # Gegenprobe: die Fixture besetzt wirklich mehr als einen Zustand, sonst
    # misst der Test nur, dass eine Summe mit sich selbst uebereinstimmt.
    assert len(zustaende) >= 2, zustaende


def test_ein_gesperrter_anbieter_nennt_seinen_grund(tmp_path):
    """"technisch gesperrt, BEGRUENDET". Ein Anbieter ohne Grund waere
    wieder die abgeschaffte Kategorie, nur unter anderem Namen."""
    _baue(tmp_path)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    ohne_daten = [z for z in geraete["quellenlage"]["zeilen"]
                  if z["zustand"] == "ohne_daten"]
    assert ohne_daten, "die Fixture hat keinen Anbieter ohne Daten"
    ohne_grund = [z["name"] for z in ohne_daten
                  if not (z.get("grund") or "").strip()]
    assert not ohne_grund, ohne_grund


def test_kein_anbieter_der_ECHTEN_konfiguration_steht_ohne_grund():
    """Derselbe Test, aber gegen `config/geraete_quellen.yaml` statt gegen
    die Fixture.

    Die Fixture-Fassung war grün, während die echte Konfiguration zwei
    Anbieter ohne Grund führte (Medimax und ElectronicPartner: angebunden,
    aktiv, seit sechzehn Nächten null Funde). Ein Test, der nur seine eigene
    Fixture misst, meldet den nächsten solchen Fall wieder nicht - CLAUDE.md
    §6, "ein Test, dessen Lookup ins Leere geht".
    """
    from pathlib import Path

    from telco_radar.geraete_config import lade_quellen as _lade

    wurzel = Path(__file__).resolve().parents[1]
    ohne_grund = [a.name for a in _lade(wurzel).anbieter
                  if not a.aktiv and not (a.grund or "").strip()]
    assert not ohne_grund, ohne_grund


# ==========================================================================
# NACHBESSERUNG 30.08.2026 - was das Durchklicken der Live-Seite fand
# ==========================================================================

def test_zwei_zahlen_nebeneinander_tragen_ein_trennzeichen(tmp_path):
    """Der Befund, der das Akzeptanzkriterium von 2147 gruenen Tests
    ueberlebt hat: die Seite meldete „o2 2454 Modelle" bei 59 beobachteten
    Geraeten.

    DIE DATEN WAREN RICHTIG. `portfolio_tiefe` lieferte 24 Generationen und
    54 Modelle; im HTML stand
    `<span class="dz-balken-n">24<span class="rubrik-zusatz">54 Modelle`,
    also zwei Inline-Elemente ohne ein Zeichen dazwischen. Der Browser setzt
    das als "2454 Modelle".

    WARUM DER BESTEHENDE TEST GRUEN BLIEB:
    `test_keine_geraetezahl_auf_der_seite_ist_groesser_als_der_bestand`
    liest mit `get_text(" ", strip=True)`. Der Trenner, den er selbst
    einfuegt, macht aus "2454" wieder "24 54" - er hat die Sorte Fehler
    unsichtbar gemacht, gegen die er gebaut war. Dieser Test liest deshalb
    OHNE Trenner, so wie ein Browser Inline-Text zusammensetzt.
    """
    site = _baue(tmp_path, db=_db_mit(24, anbieter=_UEBER_DER_SCHWELLE))
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    bestand = geraete["bilanz"]["geraete"]
    assert bestand, "kein Bestand - dann prueft der Test nichts"

    suppe = _suppe(site, "geraete.html")
    zeilen = suppe.select(".gr-tiefe li")
    assert zeilen, "keine Portfolio-Zeile gerendert - der Test misst nichts"

    import re
    for li in zeilen:
        # `get_text()` OHNE Trenner - genau die Zeichenkette, die im Browser
        # steht. Mit " " als Trenner ist dieser Test blind.
        text = li.get_text()
        for n in (int(x) for x in re.findall(r"\d+", text)):
            assert n <= bestand, (
                f"{n} in {text!r} uebersteigt die {bestand} beobachteten "
                f"Geraete - stehen dort zwei Zahlen ohne Trennzeichen?")


def test_die_portfolio_zeile_nennt_generationen_und_modelle_getrennt(tmp_path):
    """Antonios zweiter Punkt an derselben Zeile: „Die Generationenzahl, um
    die es in dieser Sektion geht, wird nirgends angezeigt."

    Sie stand da - als erste Haelfte der verschmolzenen Zahl, also
    unlesbar. Beide Zahlen tragen jetzt ihr Wort, und die Zusicherung ist
    `Generationen <= Modelle <= Varianten`: ein Jahrgang fasst Modelle
    zusammen, ein Modell fasst Varianten zusammen. Dreht eine dieser
    Rechnungen um, ist die Aussage der Sektion falsch, egal wie die Zahl
    gesetzt ist.
    """
    import re

    site = _baue(tmp_path, db=_db_mit(24, anbieter=_UEBER_DER_SCHWELLE))
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    varianten = geraete["bilanz"]["skus"]
    suppe = _suppe(site, "geraete.html")

    zeilen = suppe.select(".gr-tiefe li")
    assert zeilen, "keine Portfolio-Zeile gerendert"
    # Gegenprobe: die Vorlage muss die Zahlen wirklich aus dem Modell
    # nehmen - ohne diese Zuordnung prueft die Schleife eine leere Menge.
    aus_daten = {t["anbieter"]: t for t in geraete["lifecycle"]["portfolio"]}
    zugeordnet = 0

    for li in zeilen:
        text = li.get_text()
        gen = re.search(r"(\d+)\s+Generatione?n?\b", text)
        mod = re.search(r"(\d+)\s+Modelle?\b", text)
        assert gen, f"keine Generationenzahl in {text!r}"
        assert mod, f"keine Modellzahl in {text!r}"
        g, m = int(gen.group(1)), int(mod.group(1))
        assert g <= m, f"{g} Generationen bei {m} Modellen - {text!r}"
        assert m <= varianten, f"{m} Modelle bei {varianten} Varianten"

        name = li.select_one(".dz-balken-name").get_text(strip=True)
        if name in aus_daten:
            zugeordnet += 1
            assert g == aus_daten[name]["generationen"]
            assert m == aus_daten[name]["modelle_anzahl"]

    assert zugeordnet == len(zeilen), (
        f"nur {zugeordnet} von {len(zeilen)} Zeilen liessen sich den Daten "
        f"zuordnen - ein Lookup, der ins Leere geht, ist gruen und prueft "
        f"nichts (CLAUDE.md §6)")


def test_das_kopfdatum_ist_das_abrufdatum(tmp_path):
    """Der Kopf sagte „Stand 28. August 2026", jede Tabellenzeile darunter
    „30. August 2026". Beide stimmten - der Geraetezweig laeuft naechtlich,
    der Bericht zweimal die Woche -, aber wer zwei Zahlen im selben Blick
    vergleicht, haelt die Seite fuer veraltet.

    Die Fixture muss den Fall AUSLOESEN koennen: im Normalfall ist
    `abgerufen_am` gleich dem Berichtstag, und dann sagen beide Kandidaten
    dasselbe - der Test waere gruen, egal welchen der Kopf traegt."""
    db = _db_mit(24, anbieter=_UEBER_DER_SCHWELLE)
    for listung in db["listungen"]:
        listung["abgerufen_am"] = "2026-08-13"
    site = _baue(tmp_path, db=db)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    abruf = geraete["abgerufen_bis"]
    assert abruf, "kein Abrufdatum im Bestand - der Test misst nichts"
    assert abruf != geraete["stand"], (
        "Abruf- und Berichtstag sind gleich - dann sagt der Test nichts "
        "darueber, welchen der beiden der Kopf traegt")

    kopf = _suppe(site, "geraete.html").select_one(".page-date").get_text(" ", strip=True)
    assert "Preise vom" in kopf, kopf
    assert str(int(abruf.split("-")[2])) in kopf, (
        f"{kopf!r} nennt nicht den Abruftag {abruf}")
    assert str(int(geraete["stand"].split("-")[2])) not in kopf, (
        f"{kopf!r} nennt weiterhin den Berichtstag {geraete['stand']}")


def test_der_alarmreiter_traegt_keine_verfuegbarkeitsspalte(tmp_path):
    """An der Live-Seite gemessen sagte sie in 12 von 13 Zeilen „unbekannt":
    die Netzbetreiber-Schnittstellen liefern das Feld nicht. Eine Spalte,
    die in neun von zehn Faellen nichts sagt, kostet Breite in der Tabelle,
    die die eine Frage dieses Reiters beantworten soll.

    Geloescht ist die Auskunft nicht - der Katalog traegt sie weiter."""
    site = _baue(tmp_path, db=_db_mit(24, anbieter=_UEBER_DER_SCHWELLE))
    suppe = _suppe(site, "geraete.html")

    alarm = suppe.select_one("#tafel-tco .gr-alarm")
    assert alarm, "Alarmtabelle fehlt in der Fixture"
    koepfe = [th.get_text(" ", strip=True).lower() for th in alarm.select("thead th")]
    assert koepfe, "keine Spaltenkoepfe - der Test misst nichts"
    assert not any("verfügbar" in k for k in koepfe), koepfe

    # Und die Zellenzahl muss zur Kopfzeile passen. Eine Spalte aus dem Kopf
    # zu nehmen und die Zelle stehen zu lassen, verschiebt jede Zeile.
    erste = alarm.select_one("tbody .gr-a-zeile")
    assert erste, "keine Datenzeile"
    assert len(erste.select("td")) == len(koepfe), (
        f"{len(erste.select('td'))} Zellen zu {len(koepfe)} Spaltenkoepfen")
    aufklapper = alarm.select_one("tbody .gr-a-auf td")
    assert int(aufklapper["colspan"]) == len(koepfe), (
        f"colspan {aufklapper['colspan']} zu {len(koepfe)} Spalten")

    # Der Katalog behaelt sie - mit EINEM Wort je Zustand.
    katalog = suppe.select_one("#gr-katalogtabelle")
    assert katalog, "Katalogtabelle fehlt"
    kkoepfe = [th.get_text(" ", strip=True).lower() for th in katalog.select("thead th")]
    assert any("verfügbar" in k for k in kkoepfe), kkoepfe


def test_ein_zustand_hat_auf_der_ganzen_seite_ein_wort(tmp_path):
    """Derselbe Zustand hiess in der Alarmtabelle „unbekannt" und im Katalog
    „keine Angabe". Zwei Woerter fuer eine Sache lesen sich wie zwei
    Sachen."""
    # Der Normalfall der Fixture ist "lieferbar" - dann gibt es die Pille
    # gar nicht, und der Test bewiese nichts.
    db = _db_mit(24, anbieter=_UEBER_DER_SCHWELLE)
    for i, listung in enumerate(db["listungen"]):
        if i % 2:
            listung["verfuegbarkeit"] = "unbekannt"
    site = _baue(tmp_path, db=db)
    suppe = _suppe(site, "geraete.html")
    woerter = {p.get_text(" ", strip=True).lower()
               for p in suppe.select(".gr-pille--unbekannt, .gr-pille--unklar")}
    assert woerter, "keine Verfuegbarkeitspille gerendert - Test misst nichts"
    assert len(woerter) == 1, f"zwei Woerter fuer einen Zustand: {woerter}"


def test_die_spaltenkoepfe_sind_sortierbar(tmp_path):
    """Bei sieben Spalten und 24 Zeilen ist „sortiere nach Euro statt nach
    Prozent" die erste Frage vor dieser Tabelle.

    Geprueft wird hier die STATISCHE Voraussetzung: jeder Knopf nennt einen
    Schluessel, und zu jedem Schluessel traegt jede Zeile einen Wert. Ob die
    Sortierung dann richtig ordnet, misst
    `tests/test_geraete_reiter_browser.py` im echten Chromium - eine
    Sortierung, die es nur im Test gibt, sortiert keine Seite."""
    site = _baue(tmp_path, db=_db_mit(24, anbieter=_UEBER_DER_SCHWELLE))
    suppe = _suppe(site, "geraete.html")

    for tafel in ("#tafel-tco", "#tafel-katalog"):
        tabelle = suppe.select_one(f"{tafel} .gr-alarm")
        assert tabelle, f"{tafel}: Tabelle fehlt"
        knoepfe = tabelle.select("thead .gr-sort")
        assert knoepfe, f"{tafel}: kein sortierbarer Spaltenkopf"
        zeilen = tabelle.select("tbody .gr-a-zeile")
        assert zeilen, f"{tafel}: keine Datenzeile"
        for k in knoepfe:
            schluessel = k.get("data-sort")
            assert schluessel, f"{tafel}: Knopf ohne data-sort"
            assert k.get("data-art") in ("zahl", "text"), schluessel
            # LEER ist so schlecht wie fehlend: `parseFloat("")` ist NaN,
            # und die Sortierung schiebt NaN absteigend ans Ende, aber
            # aufsteigend an den ANFANG - eine Zeile ohne Wert stünde dann
            # ganz oben. Deshalb wird auf einen echten Wert geprüft.
            fehlend = [z for z in zeilen
                       if not (z.get(f"data-s-{schluessel}") or "").strip()]
            assert not fehlend, (
                f"{tafel}: {len(fehlend)} Zeilen ohne Wert in "
                f"data-s-{schluessel} - sie sortieren aufsteigend nach oben")


def test_unter_vier_wochen_vorlauf_zeigt_die_wochenkarte_keine_tabelle(tmp_path):
    """Die Karte meldete „59 Geräte neu im Regal" - bei 59 beobachteten
    Geräten. Beides stimmte: die Preishistorie war 20 Tage alt, also war
    JEDES erfasste Gerät innerhalb des Fensters erstmals gesehen worden.
    Der Satz sagte damit nichts über den Markt, sondern über den
    Startzeitpunkt dieses Radars - und stand als Aussage über den Markt da.
    Darunter eine Tabelle mit sieben Spaltenköpfen und genau EINER
    Datenzeile.

    Unter der Schwelle steht ein Satz und keine Tabelle. Die Bewegungen sind
    nicht verloren, sie stehen im Satz."""
    from telco_radar.report.geraete_view import VORLAUF_TAGE

    # Der Normalfall der Fixture misst seit dem 01.07., also 41 Tage - das
    # ist der ANDERE Zweig. Hier zwei Messtage eine Woche auseinander, mit
    # einer echten Preisbewegung dazwischen: es gibt einen Vergleichsstand
    # (sonst greift `ohne_vorlauf`), er ist nur kurz.
    punkte = [
        {"listung_id": "medimax--apple-iphone-16-pro-max-256gb-schwarz",
         "device_id": "apple-iphone-16-pro-max", "anbieter": "Medimax",
         "datum": "2026-08-04", "preis_ohne_vertrag": 999.0,
         "verfuegbarkeit": "lieferbar", "quelle_url": "https://example.de/p"},
        {"listung_id": "medimax--apple-iphone-16-pro-max-256gb-schwarz",
         "device_id": "apple-iphone-16-pro-max", "anbieter": "Medimax",
         "datum": "2026-08-11", "preis_ohne_vertrag": 899.0,
         "verfuegbarkeit": "lieferbar", "quelle_url": "https://example.de/p"},
    ]
    site = _baue(tmp_path, punkte=punkte)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    auf = geraete["auffaellig"]
    # Gegenprobe: die Fixture muss WIRKLICH in diesen Zweig fallen - sonst
    # prüft der Test einen anderen und behauptet diesen.
    assert auf["kurzer_vorlauf"], (
        f"{auf['vorlauf_tage']} Tage Vorlauf - die Fixture löst den Fall "
        f"nicht aus")
    assert auf["vorlauf_tage"] < VORLAUF_TAGE
    assert not auf["ohne_vorlauf"], (
        "das ist der Erstlauf-Zweig, nicht der kurze Vorlauf")

    abschnitt = _suppe(site, "geraete.html").select_one(".gr-auffaellig")
    assert abschnitt is not None, "die Wochenkarte fehlt"
    saetze = [li.get_text(" ", strip=True) for li in abschnitt.select(".gr-saetze li")]
    assert saetze, "kein Satz in der Karte"
    # Der Bewegungsteil steht in EINEM Satz, nicht als Aufzählung je
    # Bewegung - das ist der Punkt dieses Zweiges. Eine Auslistung darf
    # daneben stehen: sie ist das stärkste Signal dieser Seite und hängt
    # nicht daran, wie lange wir schon messen.
    erfasst = [x for x in saetze if "erstmals erfasst" in x]
    assert len(erfasst) == 1, f"ein Satz zur Erfassung erwartet: {saetze}"
    assert all("neu im Regal" not in x for x in saetze), (
        "'neu im Regal' ist bei 20 Tagen Messdauer eine Aussage ueber uns, "
        "nicht ueber den Markt")
    uebrig = [x for x in saetze if x not in erfasst]
    assert all("Portfolio gefallen" in x for x in uebrig), (
        f"unerwarteter Satz in der Karte: {uebrig}")
    assert abschnitt.select_one("table") is None, (
        "unter kurzem Vorlauf gehört in die Wochenkarte keine Tabelle")


def test_ueber_vier_wochen_vorlauf_kommt_die_tabelle_zurueck(tmp_path):
    """Der Gegenzweig. Ohne ihn prüfte der Test darüber nur, dass diese
    Fixture keine Tabelle rendert - und wäre auch dann grün, wenn die
    Tabelle NIE mehr erschiene."""
    from telco_radar.report.geraete_view import VORLAUF_TAGE

    # Der Normalfall der Fixture misst vom 01.07. bis zum 11.08., also
    # 41 Tage - über der Schwelle.
    site = _baue(tmp_path)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    auf = geraete["auffaellig"]
    assert auf["vorlauf_tage"] >= VORLAUF_TAGE, auf["vorlauf_tage"]
    assert not auf["kurzer_vorlauf"]
    assert auf["bewegungen"], (
        "keine Bewegung im Datensatz - dann sagt der Test nichts darüber, "
        "ob die Tabelle zurückkommt")
    abschnitt = _suppe(site, "geraete.html").select_one(".gr-auffaellig")
    assert abschnitt.select_one("table") is not None, (
        "über der Schwelle gehört die Tabelle zurück")


def test_die_wochenkarte_schreibt_preise_mit_komma(tmp_path):
    """Die Sätze schrieben ihre Beträge mit `f"{wert:.2f} €"`, also
    „129.00 €" mit Dezimalpunkt, während jede Tabelle derselben Seite
    „129,00 €" zeigt. Solange die Sätze neben einer Tabelle standen, ging
    das unter; seit die Karte unter kurzem Vorlauf NUR aus einem Satz
    besteht, ist es die erste Zahl, die dort jemand liest."""
    import re

    site = _baue(tmp_path)
    abschnitt = _suppe(site, "geraete.html").select_one(".gr-auffaellig")
    text = " ".join(li.get_text(" ", strip=True)
                    for li in abschnitt.select(".gr-saetze li"))
    assert "€" in text, f"kein Betrag in der Karte: {text!r}"
    punkt = re.findall(r"\d+\.\d\d\s*€", text)
    assert not punkt, f"Dezimalpunkt statt Komma: {punkt} in {text!r}"
    assert re.search(r"\d+,\d\d\s*€", text), text


def test_eine_ruhige_woche_erzeugt_unter_kurzem_vorlauf_gar_keine_karte(tmp_path):
    """Der Ein-Satz-Zweig darf nicht dazu führen, dass die Rubrik „Was diese
    Woche auffällt" IMMER etwas zeigt.

    Ohne die Bedingung stünde in einer ruhigen Woche „Seit dem 10.08. wurden
    0 Geräte erstmals erfasst; eine Preisänderung ist dabei nicht
    aufgefallen." - ein Satz, der nichts sagt. Vorher verschwand die Sektion
    in diesem Fall, und das ist die richtige Antwort: keine Zeile, die nichts
    sagt (dieselbe Regel, mit der „niemand günstiger" aus der Alarmtabelle
    geflogen ist)."""
    class _Historie:
        def alle_punkte(self):
            return [{"datum": "2026-08-20"}]

        def reihe(self, _listung_id):
            return []

    class _Katalog:
        def nach_id(self, _device_id):
            return None

    auf = geraete_view._auffaellig([], _Historie(), _Katalog(),
                                   heute="2026-08-30", laeufe=4)
    # Gegenprobe: der Fall muss WIRKLICH im kurzen Vorlauf liegen, sonst
    # prüft der Test einen anderen Zweig.
    assert auf["kurzer_vorlauf"], auf["vorlauf_tage"]
    assert not auf["saetze"], auf["saetze"]
    assert not auf["hat_daten"], "die Sektion darf gar nicht erscheinen"


# ==========================================================================
# P3 (31.08.2026, nach Runde 1 der Zurueckweisung): "Was der Nachfolger mit
# dem Preis macht" - der Hinweis, wenn die Sektion leer ist, die
# Verweildauer-Spalte, wenn sie es nicht ist, und der Zeilendeckel gegen die
# 3000-px-Grenze. `analyze/geraete_lifecycle.py` ist hier bewusst NICHT
# angefasst - ein Parallelpaket liefert dort `anbieter`, `zustand`,
# `verweildauer_tage`, `verweildauer_untergrenze`, `noch_gelistet`,
# `beobachtet_seit` und `zuletzt_bestaetigt` je Zeile.
# ==========================================================================

def test_b1_leer_hinweis_nennt_die_echte_beobachtungsschwelle(tmp_path):
    """B1: nicht "kein Nachfolger im Messfenster", sondern die echte
    Schwelle (`geraete_lifecycle.MIND_TAGE_JE_GERAET`) - und eine Zahl, die
    an KEINER anderen Stelle der Sektion schon steht (B7)."""
    from telco_radar.analyze import geraete_lifecycle as gl

    site = _baue(tmp_path)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    assert not geraete["lifecycle"]["nachfolger"], "falscher Testfall"
    text = geraete["lifecycle"]["nachfolger_hinweis"]

    grenze = gl.MIND_TAGE_JE_GERAET
    assert f"mindestens {grenze} Tage" in text, text
    # Die alte, falsche Begruendung darf nicht wiederkommen.
    assert "Messfenster" not in text
    assert "kam" not in text or "Katalog kennt" not in text

    suppe = _suppe(site, "geraete.html")
    abschnitt = suppe.select_one("#lifecycle")
    ueberschrift = [h for h in abschnitt.select("h3.gr-unter")
                    if "Nachfolger" in h.get_text()]
    assert ueberschrift, "die Ueberschrift fehlt"
    absatz = ueberschrift[0].find_next_sibling("p")
    assert absatz.get_text(" ", strip=True) == text


def test_b3_zaehlt_geraete_ohne_marktstart_statt_katalogpflege_abzuwerten(tmp_path):
    """B3: die Behauptung "mehr Katalogpflege loest das nicht" war falsch
    und ist gestrichen. Stattdessen zaehlt der Satz die betroffenen Geraete
    - nachgerechnet gegen denselben Testkatalog, nicht angenommen."""
    site = _baue(tmp_path)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    text = geraete["lifecycle"]["nachfolger_hinweis"]
    assert "Katalogpflege" not in text
    assert "löst das nicht" not in text

    katalog = lade_katalog(tmp_path)
    ids = {e["device_id"] for e in _DB["listungen"]}
    ohne_datum = sum(
        1 for gid in ids
        if (nf := katalog.nachfolger_von(gid)) is not None
        and not (nf.marktstart or "").strip())
    assert ohne_datum >= 1, "Gegenprobe: der Testkatalog muss eine Luecke haben"
    wort = "Gerät fehlt" if ohne_datum == 1 else "Geräten fehlt"
    assert f"Bei {ohne_datum} {wort}" in text, text


def test_b6_keine_tatsachenbehauptung_ueber_vodafone_oder_wettbewerb(tmp_path):
    """B6: "waehrend es bei Vodafone meist direkt ersetzt wird" war eine
    unbelegte Behauptung, die der eigene Bestand widerlegt (Vodafone fuehrt
    das iPhone 15 selbst 710 Tage nach dem iPhone-16-Start). Weder im
    leeren noch im gefuellten Zustand darf sie wiederkommen."""
    site_leer = _baue(tmp_path / "leer")
    html_leer = (site_leer / "geraete.html").read_text(encoding="utf-8")
    site_voll = _baue_mit_nachfolger(tmp_path / "voll")
    html_voll = (site_voll / "geraete.html").read_text(encoding="utf-8")

    verboten = ["meist direkt ersetzt", "während es bei Vodafone",
               "waehrend es bei Vodafone"]
    for name, html in (("leer", html_leer), ("voll", html_voll)):
        for fragment in verboten:
            assert fragment not in html, (
                f"unbelegte Behauptung im {name}-Zustand: {fragment!r}")


def _katalog_mit_terminiertem_nachfolger(marktstart: str):
    """Ein eigenstaendiger Katalog (nicht `_KATALOG`): ein Vorgaenger, dessen
    Nachfolger einen `marktstart` traegt - der Fall, den es im echten
    Bestand noch nicht gibt, den die Vorlage aber tragen muss, sobald er
    eintritt."""
    from telco_radar.geraete_model import device_id as did
    return {"geraete": [
        {"hersteller": "Testmarke", "modell": "Fon X", "generation": 1,
         "marktstart": "2025-06-01", "speicher": [128], "segment": "mid"},
        {"hersteller": "Testmarke", "modell": "Fon Y", "generation": 2,
         "vorgaenger": "Fon X", "marktstart": marktstart,
         "speicher": [128], "segment": "mid"},
    ]}, did("Testmarke", "Fon X"), did("Testmarke", "Fon Y")


def _baue_mit_nachfolger(tmp_path: Path, marktstart: str = "2026-01-01",
                         status: str = "vermutlich ausgelistet"):
    """Wie `_baue()`, aber mit einem eigenen Katalog und einer Preishistorie
    des Vorgaengers, die vier Messtage ueber mindestens 21 Tage traegt -
    genau die Schwelle, hinter der die Nachfolger-Zeile steht
    (`geraete_lifecycle._belastbar`). "vermutlich ausgelistet" statt
    "ausgelistet", damit die Listung SICHTBAR bleibt (`_SICHTBAR`) und die
    Seite nicht in ihren Leerzustand faellt."""
    katalog, v_id, _ = _katalog_mit_terminiertem_nachfolger(marktstart)
    root = tmp_path
    (root / "config").mkdir(parents=True, exist_ok=True)
    for name, daten in (("geraete_katalog.yaml", katalog),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    db = {"updated": "2026-08-11", "anbieter": {
        "Medimax": {"laeufe": 4, "funde_gesamt": 3}}, "listungen": [
        _listung("Medimax", v_id, f"{v_id}-128gb-schwarz", 450.0,
                 farbe="schwarz", speicher=128, status=status,
                 first_seen="2026-06-25", last_verified="2026-08-11",
                 erstpreis_am="2026-06-25"),
    ]}
    punkte = [
        {"listung_id": f"medimax--{v_id}-128gb-schwarz", "device_id": v_id,
         "anbieter": "Medimax", "datum": "2026-06-25",
         "preis_ohne_vertrag": 500.0, "verfuegbarkeit": "lieferbar",
         "quelle_url": "https://example.de/p"},
        {"listung_id": f"medimax--{v_id}-128gb-schwarz", "device_id": v_id,
         "anbieter": "Medimax", "datum": "2026-07-10",
         "preis_ohne_vertrag": 480.0, "verfuegbarkeit": "lieferbar",
         "quelle_url": "https://example.de/p"},
        {"listung_id": f"medimax--{v_id}-128gb-schwarz", "device_id": v_id,
         "anbieter": "Medimax", "datum": "2026-08-05",
         "preis_ohne_vertrag": 450.0, "verfuegbarkeit": "lieferbar",
         "quelle_url": "https://example.de/p"},
    ]
    (state / "geraete_db.json").write_text(json.dumps(db), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps(p) for p in punkte) + "\n", encoding="utf-8")

    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "2026-08-11.json").write_text(json.dumps({
        "date": "2026-08-11", "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": [],
    }), encoding="utf-8")
    (reports / "2026-08-11.md").write_text("# Bericht\n", encoding="utf-8")

    site = root / "site"
    render_site(site, reports)
    return site


def test_b2_spalte_zeigt_gemessenen_anteil_und_kollidiert_nicht_mit_verweildauer(tmp_path):
    """B2: kein "mind." mehr (liest sich als Untergrenze, obwohl der
    weitaus groesste Teil der Zahl unbelegt ist), sondern der wirklich
    GEMESSENE Anteil daneben. Und die Spalte heisst nicht "Verweildauer" -
    der Reiter traegt bereits eine Liste dieses Namens."""
    site = _baue_mit_nachfolger(tmp_path, marktstart="2026-01-01",
                                status="vermutlich ausgelistet")
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    eff = geraete["lifecycle"]["nachfolger"]
    assert eff, "die Fixture muss eine echte Nachfolger-Zeile liefern"
    n = eff[0]
    assert n["verweildauer_untergrenze"] is True, n
    assert n["verweildauer_tage"] == 222, n       # 01.01. -> 11.08.2026
    assert n["beobachtet_tage"] == 47, n          # 25.06. -> 11.08.2026

    suppe = _suppe(site, "geraete.html")
    abschnitt = suppe.select_one("#lifecycle")
    tabelle = abschnitt.select_one("table.gr-nachfolger")
    assert tabelle is not None, "die Tabelle haette entstehen muessen"

    kopf_text = tabelle.select_one("thead").get_text()
    assert "Seit dem Nachfolger" in kopf_text
    assert "Verweildauer" not in kopf_text
    assert "Anbieter" in kopf_text

    zeile = tabelle.select("tbody tr")[0]
    zellen = zeile.select("td")
    text_ganze_zeile = zeile.get_text(" ", strip=True)
    assert "222" in text_ganze_zeile and "47" in text_ganze_zeile
    assert "davon" in text_ganze_zeile and "gemessen" in text_ganze_zeile
    assert "mind." not in text_ganze_zeile
    # Anbieter steht jetzt in einer EIGENEN Spalte, nicht mehr zusaetzlich
    # im Text der letzten Zelle ("bei Medimax" waere doppelt gemoppelt).
    assert zellen[1].get_text(strip=True) == "Medimax"
    assert "Medimax" not in zellen[-1].get_text()

    # Kollisionspruefung: "Verweildauer" darf in dieser Tabelle nirgends
    # stehen - nur in der Liste "Verweildauer im Regal" darueber.
    assert "Verweildauer" not in tabelle.get_text()


def test_die_zustandsspalte_erscheint_nur_bei_mehr_als_einem_zustand(tmp_path):
    """Eine Spalte, die immer "neu" sagt, ist Ballast - sie erscheint nur,
    wenn wirklich ein zweiter Zustand vorkommt.

    `effekte` liefert heute ausschliesslich vergleichbare Zustaende ("neu");
    ein zweiter Zustand ist ein Zukunftsfall, den nur ein Monkeypatch
    erzeugen kann - genau dafuer ist er hier."""
    # Fall 1: alle Zeilen "neu" (Standard von `_listung()`) - keine Spalte.
    site = _baue_mit_nachfolger(tmp_path / "einheitlich")
    suppe = _suppe(site, "geraete.html")
    tabelle = suppe.select_one("table.gr-nachfolger")
    assert "Zustand" not in tabelle.select_one("thead").get_text()


def test_die_zustandsspalte_erscheint_bei_einem_zweiten_zustand(tmp_path, monkeypatch):
    """Gegenprobe zum Test oben: kommt ein zweiter Zustand vor, MUSS er
    sichtbar werden."""
    echt = geraete_view.geraete_lifecycle.auswertung

    def _zwei_zustaende(*args, **kwargs):
        erg = echt(*args, **kwargs)
        eff = list(erg["nachfolger"])
        if eff:
            zweite = dict(eff[0])
            zweite["anbieter"] = "o2"
            zweite["zustand"] = "refurbished"
            eff.append(zweite)
        erg["nachfolger"] = eff
        return erg

    monkeypatch.setattr(geraete_view.geraete_lifecycle, "auswertung",
                        _zwei_zustaende)
    site = _baue_mit_nachfolger(tmp_path)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    zustaende = {n.get("zustand") for n in geraete["lifecycle"]["nachfolger"]}
    assert len(zustaende) == 2, (
        f"Gegenprobe: die Fixture muss zwei Zustaende liefern, hat {zustaende}")

    suppe = _suppe(site, "geraete.html")
    tabelle = suppe.select_one("table.gr-nachfolger")
    assert tabelle is not None
    assert "Zustand" in tabelle.select_one("thead").get_text()
    zeilen_texte = [tr.get_text(" ", strip=True)
                    for tr in tabelle.select("tbody tr")]
    assert any("refurbished" in t for t in zeilen_texte), zeilen_texte


def test_b4_die_tabelle_bleibt_unter_der_hoehengrenze_bei_vielen_zeilen(tmp_path):
    """B4: die Tabelle war die einzige Liste des Reiters ohne Zeilendeckel
    und riss die 3000-px-Grenze. `NACHFOLGER_SICHTBAR` steht auf 0 (siehe
    Modulkommentar fuer die Messreihe) - bei vielen Zeilen erscheint deshalb
    GAR KEIN Tabellenkopf oberhalb der Falz, sondern EIN Aufklapper mit der
    vollstaendigen Tabelle. Dieser Test prueft die STRUKTUR (Zeilendeckel
    greift, Hoehe waechst nicht unbegrenzt mit dem Bestand); die tatsaechliche
    Pixelzahl haelt `scripts/pruefe_portal.py` fest (siehe Bericht)."""
    katalog_geraete = []
    listungen = []
    punkte = []
    from telco_radar.geraete_model import device_id as did
    n = 9  # mehr als jeder bisherige LIFECYCLE_SICHTBAR-Wert
    for i in range(1, n + 1):
        katalog_geraete.append({"hersteller": "Testmarke", "modell": f"Fon {i}X",
                                "generation": i, "marktstart": "2025-06-01",
                                "speicher": [128], "segment": "mid"})
        katalog_geraete.append({"hersteller": "Testmarke", "modell": f"Fon {i}Y",
                                "generation": i, "vorgaenger": f"Fon {i}X",
                                "marktstart": "2026-01-01",
                                "speicher": [128], "segment": "mid"})
        vid = did("Testmarke", f"Fon {i}X")
        sku = f"{vid}-128gb-schwarz"
        listungen.append(_listung("Medimax", vid, sku, 450.0, farbe="schwarz",
                                  speicher=128))
        lid = f"medimax--{sku}"
        for datum, preis in (("2026-07-15", 440.0), ("2026-07-25", 430.0)):
            punkte.append({"listung_id": lid, "device_id": vid,
                           "anbieter": "Medimax", "datum": datum,
                           "preis_ohne_vertrag": preis,
                           "verfuegbarkeit": "lieferbar",
                           "quelle_url": "https://example.de/p"})
    root = tmp_path
    (root / "config").mkdir(parents=True, exist_ok=True)
    for name, daten in (("geraete_katalog.yaml", {"geraete": katalog_geraete}),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    db = {"updated": "2026-08-11",
         "anbieter": {"Medimax": {"laeufe": 4, "funde_gesamt": n}},
         "listungen": listungen}
    (state / "geraete_db.json").write_text(json.dumps(db), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps(p) for p in punkte) + "\n", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "2026-08-11.json").write_text(json.dumps({
        "date": "2026-08-11", "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": [],
    }), encoding="utf-8")
    (reports / "2026-08-11.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)

    geraete = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute="2026-08-11")
    eff = geraete["lifecycle"]["nachfolger"]
    assert len(eff) == n, (
        f"Gegenprobe: die Fixture muss {n} Nachfolger-Zeilen liefern, hat {len(eff)}")

    suppe = _suppe(site, "geraete.html")
    abschnitt = suppe.select_one("#lifecycle")
    tabellen = abschnitt.select("table.gr-nachfolger")
    # NACHFOLGER_SICHTBAR = 0: keine sichtbare Tabelle OBERHALB des
    # Aufklappers - nur genau EINE, und die steht IM Aufklapper.
    assert len(tabellen) == 1, (
        f"erwartet genau eine Tabelle (im Aufklapper), gefunden {len(tabellen)}")
    aufklapper = abschnitt.select_one("details.gr-mehrliste:has(table.gr-nachfolger)")
    assert aufklapper is not None, "die Tabelle muss im Aufklapper stehen"
    assert str(n) in aufklapper.select_one("summary").get_text()
    assert len(aufklapper.select("tbody tr")) == n

    # Gegenprobe zur Zahlenregel (CLAUDE.md, 30.08.2026-Vorfall): zwei
    # Zahlen ohne Zeichen dazwischen lesen sich im Browser als EINE. Geprueft
    # wird OHNE Trenner (`get_text()`, kein `get_text(" ")`) - genau die
    # Zeichenkette, die im Browser steht.
    for tr in aufklapper.select("tbody tr")[:2]:
        letzte_zelle = tr.select("td")[-1].get_text()
        assert "222 Tage" in letzte_zelle, letzte_zelle
        assert "davon 41 Tage" in letzte_zelle, letzte_zelle
        # "22241" waere die verschmolzene Form der beiden Zahlen oben -
        # sie darf in der ECHTEN Browser-Zeichenkette nicht vorkommen.
        assert "22241" not in letzte_zelle, letzte_zelle


def test_die_zelle_uebersteht_fehlende_verweildauer_felder(tmp_path, monkeypatch):
    """`.get(...)` statt Punktzugriff: eine Zeile ohne die neuen Felder
    (kuenftiger Aufrufer, der sie nicht liefert) darf die Seite nicht mit
    einer Ausnahme zum Absturz bringen - die Zelle zeigt still einen
    Gedankenstrich, `noch_gelistet` wird bei einem fehlenden Feld NICHT
    stillschweigend zu "steht noch im Regal" (B8)."""
    echt = geraete_view.geraete_lifecycle.auswertung

    def _ohne_die_neuen_felder(*args, **kwargs):
        ergebnis = echt(*args, **kwargs)
        for eintrag in ergebnis["nachfolger"]:
            for feld in ("verweildauer_tage", "verweildauer_untergrenze",
                        "noch_gelistet", "anbieter", "beobachtet_seit",
                        "zuletzt_bestaetigt"):
                eintrag.pop(feld, None)
        return ergebnis

    monkeypatch.setattr(geraete_view.geraete_lifecycle, "auswertung",
                        _ohne_die_neuen_felder)

    site = _baue_mit_nachfolger(tmp_path)
    suppe = _suppe(site, "geraete.html")
    tabelle = suppe.select_one("table.gr-nachfolger")
    assert tabelle is not None, "auch ohne die neuen Felder muss die Zeile stehen"
    zeile = tabelle.select("tbody tr")[0]
    zellen = zeile.select("td")
    assert zellen[-1].get_text(strip=True) == "–", (
        f"ohne die neuen Felder erwartet: '–', bekommen: {zellen[-1].get_text()!r}")
    # Anbieter-Spalte: fehlt der Wert, steht dort ein Gedankenstrich, nicht
    # ein leerer Zellinhalt oder eine Ausnahme.
    assert zellen[1].get_text(strip=True) == "–"


def test_die_zelle_uebersteht_kaputte_preis_und_datumsfelder(tmp_path, monkeypatch):
    """Dieselbe Absicherung fuer `prozent`/`nach`/`marktstart` - keine
    dieser drei Formatierungen darf auf einem fehlenden oder unpassenden
    Wert eine Ausnahme werfen (B8: `prozent[30]=None` bei gesetztem Preis,
    `nach`/`prozent` fehlen ganz, `marktstart=None`)."""
    echt = geraete_view.geraete_lifecycle.auswertung

    def _kaputte_felder(*args, **kwargs):
        erg = echt(*args, **kwargs)
        erg["nachfolger"] = [{
            "device_id": "test-a", "nachfolger": "test-b",
            "nachfolger_modell": "Test B", "marktstart": None,
            "anbieter": "Testshop", "zustand": "neu", "basis": None,
            "modell": "Test A",
        }]
        return erg

    monkeypatch.setattr(geraete_view.geraete_lifecycle, "auswertung",
                        _kaputte_felder)
    site = _baue_mit_nachfolger(tmp_path)
    suppe = _suppe(site, "geraete.html")
    tabelle = suppe.select_one("table.gr-nachfolger")
    assert tabelle is not None
    zeile = tabelle.select("tbody tr")[0]
    zellen = [td.get_text(" ", strip=True) for td in zeile.select("td")]
    assert zellen[0] == "Test A"
    assert zellen[1] == "Testshop"
    # Kein Datum hinter "Test B" - `marktstart=None` durchlaeuft den
    # Datumsfilter nicht.
    assert "Test B" in zeile.get_text()
    assert "None" not in zeile.get_text()


# --------------------------------------------------------------------------
# Die Preisform steht an der Zahl (03.09.2026)
# --------------------------------------------------------------------------

def test_ein_ratengesamtbetrag_wird_auf_der_seite_als_solcher_gezeigt(tmp_path):
    """Der Befund vom 03.09.2026: o2s Preisspalte trug den Gesamtbetrag einer
    24-Monats-Ratenzahlung in derselben Optik wie freenets Barpreis.

    Der Fall hier ist der gemessene: 1,00 EUR Anzahlung plus 24 x 30,00 EUR
    ergeben 721,00 EUR. Auf der Seite muss beides stehen - die Zahl UND
    woraus sie besteht.
    """
    db = json.loads(json.dumps(_DB))
    db["listungen"].append(_listung(
        "o2", "apple-iphone-16-pro-max",
        "apple-iphone-16-pro-max-256gb-schwarz", 721.0, farbe="schwarz",
        id="o2--apple-iphone-16-pro-max-256gb-schwarz",
        anbieter_typ="netzbetreiber", netz="o2",
        anzahlung=1.0, monatsrate=30.0, laufzeit_monate=24,
        zins_effektiv=0.0))

    site = _baue(tmp_path, db=db)
    text = (site / "geraete.html").read_text(encoding="utf-8")
    assert "in 24 Raten (0 %)" in text
    # Und die Zusicherung dahinter: ein Barpreis bekommt den Zusatz NICHT.
    # Der Bestand traegt vier Haendlerzeilen ohne Ratenfelder.
    assert text.count("in 24 Raten") < text.count("gr-a-modell")


def test_die_seite_behauptet_keinen_reinen_barpreisvergleich_mehr(tmp_path):
    """Solange o2 und Vodafone in derselben Spalte stehen, ist "ausschliesslich
    Neugeraete ohne Vertrag" die Behauptung, die Befund A widerlegt hat."""
    site = _baue(tmp_path)
    text = (site / "geraete.html").read_text(encoding="utf-8")
    assert "ausschließlich Neugeräte ohne Vertrag" not in text
    assert "nicht dasselbe wie ein Barpreis" in text
