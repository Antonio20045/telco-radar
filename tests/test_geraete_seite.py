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
]}

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


def test_kennzahlen_stimmen_mit_den_daten_ueberein(tmp_path):
    """Der Fehlertyp aus CLAUDE.md §6: ein Etikett und ein Feld, die nicht
    dasselbe meinen.

    Gemessen werden die vier Alarmkacheln. Sie haben am 30.08.2026 die fuenf
    Betriebskacheln ("59 Geraete beobachtet", "250 Varianten") vom besten
    Platz der Seite abgeloest - eine Zahl, die zu keiner Handlung fuehrt,
    gehoert nicht dorthin. Die Betriebszahlen stehen jetzt als Satz am Fuss.
    """
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    kacheln = {k.find("span").get_text(strip=True): k.find("b").get_text(strip=True)
               for k in s.select(".gr-kacheln .gr-kachel")}
    assert set(kacheln) == {"Kritisch", "Mittel", "Gering", "Bestpreis"}

    # Die Summe der vier Kacheln IST die Zahl der verglichenen Geraete. Zwei
    # Zahlen, die dasselbe meinen muessen, gehoeren gegeneinander gehalten.
    fuss = s.select_one(".gr-bilanz").get_text(" ", strip=True)
    sichtbar = [e for e in _DB["listungen"] if e["status"] != "ausgelistet"]
    assert str(len({e["device_id"] for e in sichtbar})) in fuss
    assert str(len({e["sku_id"] for e in sichtbar})) in fuss


def test_die_vier_kacheln_zaehlen_genau_die_verglichenen_geraete(tmp_path):
    """Eine Kachel, die anders zaehlt als die Tabelle unter ihr, ist derselbe
    Fehlertyp. Und ein Geraet ohne Wettbewerber ist NICHT unser Bestpreis -
    es ist gar nicht verglichen."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    summe = sum(int(k.find("b").get_text(strip=True))
                for k in s.select(".gr-kacheln .gr-kachel"))
    tafel = " ".join(s.select_one("#tafel-alarme").get_text(" ", strip=True).split())
    assert f"{summe} Modelle mit ihren Speichergrößen stehen einem Wettbewerber gegenüber" in tafel


def test_kein_cdn_und_keine_chart_bibliothek(tmp_path):
    """Akzeptanzkriterium aus Teil E - und Hausregel des ganzen Portals."""
    site = _baue(tmp_path)
    roh = (site / "geraete.html").read_text(encoding="utf-8")
    assert "<svg" in roh
    for verboten in ("cdn.", "unpkg", "jsdelivr", "chart.js", "d3.", "plotly"):
        assert verboten not in roh.lower(), verboten


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
    # Eine Zeile je SICHTBARER Listung, nicht je Gerät - das ist der ganze
    # Punkt der flachen Form. Ausgelistete Bestände bleiben in der Datenbank
    # (sie wird per Design nie geleert), gehören aber nicht ins Regal.
    sichtbar = [l for l in _DB["listungen"]
                if l.get("status") in ("aktiv", "beobachtet")]
    assert len(sichtbar) < len(_DB["listungen"]), (
        "die Fixture hat keine ausgelistete Zeile - dann misst dieser "
        "Vergleich nicht, dass der Status wirklich filtert")
    assert len(zeilen) == len(sichtbar), len(zeilen)
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
    "0 Tage" und "+0.0 %"."""
    site = _baue(tmp_path, db=_DB_DUENN, punkte=_PUNKTE_DUENN)
    s = _suppe(site, "geraete.html")
    basis = s.select_one(".gr-basis")
    assert basis is not None
    # Die Klasse war im CSS angelegt und kam im HTML NULL Mal vor.
    assert "gr-basis--duenn" in (basis.get("class") or [])
    assert not s.select(".gr-dauern li"), "Verweildauer ohne Datenbasis"
    assert not s.select(".gr-verfall li"), "Preisverfall ohne Datenbasis"
    text = s.select_one(".gr-lifecycle").get_text(" ", strip=True)
    assert "0 Tage" not in text
    assert "+0.0 %" not in text
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
    # Die Kachel "0 ausgelistet" ist ohne Vorlauf keine Aussage.
    kacheln = {k.find("span").get_text(strip=True)
               for k in s.select(".gr-bilanz .t-kennzahl")}
    assert "ausgelistet" not in kacheln


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
    tafel = s.select_one("#tafel-alarme")
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
    zeile = s.select_one("#tafel-alarme .gr-a-zeile")
    assert zeile is not None, "keine einzige Alarmzeile"
    assert "%" in zeile.select_one(".gr-a-prozent").get_text(strip=True)
    assert "€" in zeile.select_one(".gr-a-euro").get_text(strip=True)


def test_jede_alarmzeile_traegt_quelle_und_abrufdatum(tmp_path):
    """"Kein Vergleich ohne beide Quelllinks und beide Abrufdaten." Auf der
    Seite gemessen, nicht nur in der Rechnung."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    zeilen = s.select("#tafel-alarme .gr-a-zeile")
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
    zeile = s.select_one("#tafel-alarme .gr-a-zeile")
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
    tafel = s.select_one("#tafel-alarme")
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


def test_die_abrufdaten_stehen_deutsch_nicht_als_iso(tmp_path):
    """Zielgruppe sind Manager ohne Technikhintergrund - der Rest des
    Portals schreibt deutsche Daten, diese Sektion tat es zuerst nicht.
    Beim ANSEHEN des Screenshots aufgefallen, nicht im Test."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    gemessen = 0
    for datum in s.select("#tafel-alarme .gr-a-klein, #tafel-alarme .gr-a-liste span"):
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
    felder = [f.get("data-filter") for f in s.select("#tafel-alarme [data-filter]")]
    assert felder == ["marke", "modell", "speicher", "suche"]

    fest = [e.get_text(" ", strip=True)
            for e in s.select("#tafel-alarme .gr-filter label.gr-filter--an")]
    assert fest == ["Zustand: neu", "Preisart: ohne Vertrag"]

    # Jede Zeile traegt die Werte, nach denen gefiltert wird.
    for zeile in s.select("#tafel-alarme .gr-a-zeile"):
        assert zeile.has_attr("data-marke")
        assert zeile.has_attr("data-modell")
        assert zeile.has_attr("data-speicher")


def test_ohne_vergleichsdaten_steht_die_sektion_gar_nicht_da(tmp_path):
    """Ein leerer Kasten mit Ueberschrift sagt "kaputt", nicht "noch keine
    Daten"."""
    ohne = {"updated": "2026-08-11", "anbieter": {}, "listungen": []}
    site = _baue(tmp_path, db=ohne, punkte=[])
    s = _suppe(site, "geraete.html")
    assert s.select_one("#tafel-alarme") is None


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
    assert s.select_one("#tafel-alarme") is not None


def test_die_geraetespalte_der_matrix_bleibt_beim_scrollen_stehen(tmp_path):
    """Ab vier Anbietern - und erst recht ab acht - scrollt man sonst eine
    Zeile nach rechts und weiss nicht mehr, zu welchem Geraet sie gehoert."""
    site = _baue(tmp_path)
    css = (site / "style.css").read_text(encoding="utf-8")
    assert ".gr-matrix-tabelle th[scope=row]" in css
    block = css.split(".gr-matrix-tabelle th[scope=row]", 1)[1].split("}", 1)[0]
    assert "position:sticky" in block and "left:0" in block
    # Ohne eigenen Hintergrund scheinen die Zellen darunter durch.
    assert "background:" in block


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


def test_die_preisspanne_der_sku_matrix_zeigt_keinen_gebrauchtpreis(tmp_path):
    """Die Zelle sagt „ab N €" – das ist eine Preisaussage und folgt
    derselben Regel wie Vergleich und Grafik. Vorher stand dort der
    Gebrauchtpreis ohne jede Kennzeichnung; nur die aufgeklappte
    Variantenzeile trug „· refurbished"."""
    db = _db_mit(24, anbieter=_UEBER_DER_SCHWELLE)
    billig = db["listungen"][0]
    billig["zustand"] = "refurbished"
    billig["preis_ohne_vertrag"] = 99.0
    billig["sku_id"] += "-refurbished"
    billig["id"] += "-refurbished"

    _baue(tmp_path, db=db)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")

    spannen = [z for zeile in geraete["matrix"]["zeilen"]
               for z in zeile["zellen"] if not z.get("leer")]
    assert spannen, "keine Zellen - dann prüft der Test nichts"
    assert all(z.get("ab") is None or z["ab"] >= 399.0 for z in spannen), (
        "ein Gebrauchtpreis steht in der Preisspanne einer Zelle")
    # Gegenprobe: die Variante selbst bleibt sichtbar, nur gekennzeichnet.
    varianten = [v for zeile in geraete["matrix"]["zeilen"]
                 for z in zeile["zellen"] if not z.get("leer")
                 for v in z.get("varianten", [])]
    assert any(v["zustand"] == "refurbished" for v in varianten)


# --------------------------------------------------------------------------
# W2: die Grafik zeigt eine Aussage, keine Tapete
# --------------------------------------------------------------------------

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

    site = _baue(tmp_path, db=db)
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
    for auswahl in ("#tafel-alarme", ".gr-katalog", "#tafel-katalog"):
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
    assert zustaende <= {"liefert", "gesperrt", "ohne_hardware"}, zustaende
    assert q["liefernd"] + q["gesperrt"] + q["ohne_hardware_zahl"] == \
        q["konfiguriert"], q

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
    gesperrt = [z for z in geraete["quellenlage"]["zeilen"]
                if z["zustand"] == "gesperrt"]
    assert gesperrt, "die Fixture hat keinen gesperrten Anbieter"
    ohne_grund = [z["name"] for z in gesperrt if not (z.get("grund") or "").strip()]
    assert not ohne_grund, ohne_grund
