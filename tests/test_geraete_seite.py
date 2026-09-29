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


def test_der_export_zeigt_genau_den_bestand(tmp_path):
    """Der Export zeigt den BESTAND, nicht eine eigene Menge.

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

    Seit dem Neuentwurf der Geräteseite (29.09.2026) trägt die Seite keinen
    Katalog mehr; der Vergleich Seite gegen Datei ist mit ihm gefallen.
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

    # Und die zweite Datei fuehrt keine Kurve zu einer Listung, die in der
    # ersten fehlt - sonst steht dort ein Preis ohne Zeile dazu.
    historie = list(csv.reader(io.StringIO(
        (site / "exporte" / "geraete-historie.csv").read_text(
            encoding="utf-8-sig")), delimiter=";"))
    h_kopf = historie[0]
    assert {z[h_kopf.index("Listungs-ID")] for z in historie[1:]} <= gefuehrt


def test_kennzahlen_stimmen_mit_den_daten_ueberein(tmp_path):
    """Der Fehlertyp aus CLAUDE.md §6: ein Etikett und ein Feld, die nicht
    dasselbe meinen.

    Die Bestandszahlen (`bilanz`) werden gegen die Fixture gehalten. Sie
    rechnet auf dem BESTAND, nicht auf dem Rohbestand: die gealterte
    Zwillingshaelfte traegt eine eigene `sku_id` und zaehlte sonst als
    zweite Variante derselben Listung. (Die Alarmkacheln, die bis zum
    Neuentwurf der Geräteseite am 29.09.2026 dagegen standen, sind mit dem
    Radar-Reiter gefallen.)
    """
    _baue(tmp_path)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")
    im_regal = [e for e in _DB["listungen"] if e["id"] in _bestand_ids()]
    # Gegenprobe: Rohbestand und Bestand unterscheiden sich wirklich -
    # sonst prüfte die Zeile unten nicht, welche Menge gezählt wird.
    assert len(_rohbestand_ids()) > len(im_regal)
    assert geraete["bilanz"]["geraete"] == len({e["device_id"] for e in im_regal})
    assert geraete["bilanz"]["skus"] == len({e["sku_id"] for e in im_regal})
    assert geraete["bilanz"]["listungen"] == len(im_regal)


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


def test_modellzeilen_halten_alle_listungen_eines_geraets_im_aufklapper():
    """B6 der Zurueckweisung vom 31.08.2026, auf die P3-Modellebene gehoben:
    "wer ein Geraet sucht, findet seine Zeilen beieinander". Seit P3 ist
    das Modell die ZEILE, seine Listungen stehen im Aufklapper DARUNTER -
    die Zusicherung ist dadurch schaerfer geworden: keine Listung darf
    ausserhalb des Aufklappers ihres Modells landen, und keine darf fehlen.

    Die Fixture verteilt ABSICHTLICH sieben Listungen desselben Geraets
    ueber die Eingabe, dazwischen andere Hersteller - genau das Muster, an
    dem die reine Zeilenmischung der ersten Nachbesserung scheiterte.
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
        # steht vor C-refurbished/799, obwohl 799 < 850). Dieselbe Regel,
        # die bis P3 die sichtbaren Bloecke ordnete, ordnet jetzt den
        # Aufklapper.
        _b_zeile("Samsung", "Galaxy S26 Ultra", anbieter="C", zustand="neu", preis=850),
    ]
    modelle = geraete_view.katalog_modellzeilen(eintraege, katalog)
    assert sum(m["listungen"] for m in modelle) == len(eintraege), (
        "eine Aggregation darf keine Listung verlieren")

    s26 = [m for m in modelle if m["modell"] == "Galaxy S26 Ultra"]
    assert len(s26) == 1, (
        f"das Geraet steht in {len(s26)} Modellzeilen statt einer: "
        f"{[m['schluessel'] for m in s26]}")
    zeilen = s26[0]["zeilen"]
    assert len(zeilen) == 7, len(zeilen)
    # Innerhalb des Aufklappers: "neu" vor dem Rest, dann der Betrag
    # AUFGEHEND (`_katalog_zeile_schluessel`) - der guenstigste Händler
    # zuerst. Und C fuehrt mit seiner NEU-Zeile trotz hoeherem Preis als
    # seiner refurbished (850 steht VOR 799, obwohl 799 < 850): der
    # Zustand ist der fuehrende Schluessel.
    anbieter_je_zeile = [z["anbieter"] for z in zeilen]
    assert anbieter_je_zeile == ["C", "B", "E", "D", "A", "F", "C"], (
        f"die Reihenfolge des Aufklappers ist nicht neu-vor-rest, dann "
        f"Betrag aufgehend: {anbieter_je_zeile}")
    zustaende = [z["zustand"] for z in zeilen]
    assert zustaende == ["neu", "neu", "neu", "neu", "neu",
                         "refurbished", "refurbished"], zustaende


def test_modellzeilen_ordnen_nach_segment_nicht_nach_roher_generation():
    """B1 der Zurueckweisung vom 31.08.2026: innerhalb eines Herstellers
    zaehlt das SEGMENT vor der Generation - eine Galaxy A57 (Generation 57,
    die hoechste Zahl der Fixture) steht hinter beiden flagship-Ultras,
    obwohl `sorted(key=-generation)` sie nach vorn zoege.

    `generation` ist nur INNERHALB einer Baureihe eine Zahl (Hausregel
    seit dem 29.08.2026) - dieselbe Warnung, eine Ebene unveraendert.
    """
    katalog = _b_katalog()
    eintraege = [
        _b_zeile("Samsung", "Galaxy A57"),
        _b_zeile("Samsung", "Galaxy S25 Ultra"),
        _b_zeile("Samsung", "Galaxy S26 Ultra"),
    ]
    modelle = geraete_view.katalog_modellzeilen(eintraege, katalog)
    namen = [m["modell"] for m in modelle]
    assert namen.index("Galaxy A57") > namen.index("Galaxy S26 Ultra"), (
        f"die Mittelklasse A57 steht vor dem Flaggschiff: {namen}")
    # Innerhalb desselben Segments (flagship) zaehlt die Generation: S26
    # Ultra vor S25 Ultra.
    assert namen.index("Galaxy S26 Ultra") < namen.index("Galaxy S25 Ultra"), namen


def test_modellzeilen_mischen_modelle_reihum_je_hersteller():
    """B5, auf Modellebene gemessen: unter den ersten drei MODELLZEILEN
    stehen drei verschiedene Hersteller, obwohl Apple in der Eingabe zuerst
    und mit den meisten Modellen steht. Die Fixture braucht dafuer drei
    EIGENE Apple-Modelle - vier Listungen EINES Modells wuerden zu einer
    Modellzeile aggregiert und den Fall nicht aufspannen.
    """
    from telco_radar.geraete_model import Geraet, Katalog
    katalog = Katalog(geraete=[
        Geraet(hersteller="Apple", modell="Apple X", generation=1,
               segment="flagship"),
        Geraet(hersteller="Apple", modell="Apple Y", generation=2,
               segment="flagship"),
        Geraet(hersteller="Apple", modell="Apple Z", generation=3,
               segment="flagship"),
        Geraet(hersteller="Samsung", modell="Galaxy S26 Ultra",
               generation=26, segment="flagship"),
        Geraet(hersteller="Google", modell="Pixel 11", generation=11,
               segment="flagship"),
    ])
    eintraege = ([_b_zeile("Apple", f"Apple {n}") for n in "XYZ"]
                 + [_b_zeile("Samsung", "Galaxy S26 Ultra")]
                 + [_b_zeile("Google", "Pixel 11")])
    modelle = geraete_view.katalog_modellzeilen(eintraege, katalog)
    erste_drei = []
    for m in modelle:
        if m["hersteller"] not in erste_drei:
            erste_drei.append(m["hersteller"])
        if len(erste_drei) == 3:
            break
    assert set(erste_drei) == {"Apple", "Samsung", "Google"}, (
        [m["hersteller"] for m in modelle])


def test_modellzeilen_sind_deterministisch_bei_gleichstand():
    """B8 der Zurueckweisung: ohne Farbe als Tiebreak blieb die Reihenfolge
    der AUFKLAPPER-Zeilen bei gleichem Betrag/Anbieter unterbestimmt und
    hing an der Eingabereihenfolge. Zwei Listungen desselben Modells,
    desselben Anbieters, desselben Preises - nur die Farbe unterscheidet
    sie."""
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
        modelle = geraete_view.katalog_modellzeilen(gemischt, katalog)
        farben = tuple(z["farbe"] for z in modelle[0]["zeilen"])
        if erwartet is None:
            erwartet = farben
        assert farben == erwartet, (
            f"die Reihenfolge haengt an der Eingabe: {farben} != {erwartet}")


def test_modellzeilen_stellen_einen_hersteller_ohne_katalogtreffer_ans_ende():
    """B9 der Zurueckweisung: die Docstring behauptete, ein Hersteller ohne
    Katalogtreffer falle ans Ende seiner Gruppe - `hersteller == ""` und
    `sorted(gruppen)` stellten den leeren String aber an den ANFANG, seine
    Modelle eroeffneten das Reihum. Auf Modellebene gilt dieselbe Regel."""
    katalog = _b_katalog()
    eintraege = [
        {"device_id": "unbekanntes-geraet", "anbieter": "A",
         "preis_ohne_vertrag": 1.0, "zuzahlung": None, "speicher_gb": 256,
         "farbe_roh": "Schwarz", "farbe_normalisiert": "schwarz",
         "zustand": "neu", "verfuegbarkeit": "lieferbar", "quelle_url": "",
         "abgerufen_am": ""},
        _b_zeile("Apple", "Apple X"),
    ]
    modelle = geraete_view.katalog_modellzeilen(eintraege, katalog)
    assert modelle[0]["hersteller"] == "Apple", (
        "der Hersteller ohne Katalogtreffer fuehrt das Reihum an: "
        f"{[m['hersteller'] for m in modelle]}")



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
                       / "chromium*/chrome-linux*/chrome"),
                   "/Applications/Chromium.app/Contents/MacOS/Chromium"):
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


@pytest.mark.parametrize("datei", ["geraete_db.json", "geraete_tco.json"])
def test_eine_unlesbare_datenbank_sieht_nicht_aus_wie_nichts_gefunden(
        tmp_path, datei):
    """Befund 13: dieselbe Klasse wie der dokumentierte Fallstrick „Ein
    gescheiterter LLM-Aufruf darf nie wie ‚nichts gefunden' aussehen."

    Seit dem Neuentwurf (29.09.2026) ist die Kosten-Rangliste der Ort: eine
    unlesbare Datei darf dort nicht als „Keine Gerätepreise." erscheinen.
    Die alte Seite trug dafür zwei eigene Zustände (`db_lesbar`,
    `tco.lesbar`); geprüft werden beide Dateien."""
    root = tmp_path
    site = _baue(root)
    (root / "data" / "state" / datei).write_text("{kaputt", encoding="utf-8")
    render_site(site, root / "data" / "reports")
    kosten = _suppe(site, "geraete.html").select_one("#kosten")
    assert kosten is not None, "#kosten fehlt - der Test prüft nichts"
    text = kosten.get_text(" ", strip=True)
    assert "nicht lesbar" in text, text
    assert "Keine Gerätepreise." not in text, text


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


# --------------------------------------------------------------------------
# Die Befunde des dritten Reviews (11.08.2026)
# --------------------------------------------------------------------------



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


# --------------------------------------------------------------------------
# "Wer ist guenstiger als Vodafone?" auf der gerenderten Seite (G2)
# --------------------------------------------------------------------------



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



def test_die_geraeteseite_entsteht_ohne_jeden_netz_oder_modellaufruf(tmp_path,
                                                                     monkeypatch):
    """Der Provider war beim Lauf vom 25.08. ohne Guthaben (HTTP 402). Die
    ganze Geraeteseite - Kosten-Rangliste und Export - muss trotzdem
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
    # Seit dem Neuentwurf (29.09.2026): die Kosten-Rangliste und ihr
    # Export stehen, ohne dass etwas abgerufen wurde.
    seite = _suppe(site, "geraete.html")
    assert seite.select_one("#kosten") is not None
    assert (site / "exporte" / "geraete-tco.csv").exists()


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


# --------------------------------------------------------------------------
# Die Preisform steht an der Zahl (03.09.2026)
# --------------------------------------------------------------------------



