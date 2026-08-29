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

def test_beide_seiten_werden_gerendert(tmp_path):
    site = _baue(tmp_path)
    assert (site / "geraete.html").exists()
    assert (site / "geraete-quellen.html").exists()


def test_kennzahlen_stimmen_mit_den_daten_ueberein(tmp_path):
    """Der Fehlertyp aus CLAUDE.md §6: ein Etikett und ein Feld, die nicht
    dasselbe meinen."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    kacheln = {k.find("span").get_text(strip=True): k.find("b").get_text(strip=True)
               for k in s.select(".gr-bilanz .t-kennzahl")}
    sichtbar = [e for e in _DB["listungen"] if e["status"] != "ausgelistet"]
    assert len(kacheln) == 5           # sonst prueft der Vergleich nichts
    assert kacheln["Geräte beobachtet"] == str(len({e["device_id"] for e in sichtbar}))
    assert kacheln["Varianten (SKUs)"] == str(len({e["sku_id"] for e in sichtbar}))
    assert kacheln["Anbieter mit Daten"] == str(len({e["anbieter"] for e in sichtbar}))
    assert kacheln["Preispunkte in der Historie"] == str(len(_PUNKTE))
    assert kacheln["ausgelistet"] == "1"


def test_ausgelistete_geraete_stehen_nicht_in_der_karte(tmp_path):
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    # EINE Flaeche, nicht die Ansicht: seit dem 11.08.2026 steht jede Ansicht
    # in zwei Darstellungsformen im HTML, und ueber beide gezaehlt waere jede
    # Zahl hier verdoppelt.
    # BEIDE Formen. Aus der Chipform stammen Legende, Ueberschriftszahl und
    # Tabelle - nur die Bandform zu messen hiesse, sie nie zu pruefen.
    for form in ("band", "chip"):
        punkte = s.select(f"#gr-ansicht-hersteller "
                          f".gr-flaeche[data-form='{form}'] .gr-punkt")
        modelle = {p.get("data-modell") for p in punkte}
        # Das ausgelistete Galaxy S25 Ultra 512 GB von Medimax faellt raus,
        # das aktive von Vodafone bleibt.
        assert "Galaxy S25 Ultra" in modelle, form
        assert len(punkte) == 4, form


def test_beide_ansichten_stehen_fertig_im_html(tmp_path):
    """Der Umschalter darf nicht nachladen - beide Ansichten sind gerendert,
    JS blendet nur um."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    assert s.select_one("#gr-ansicht-hersteller") is not None
    assert s.select_one("#gr-ansicht-anbieter") is not None
    assert len(s.select("#gr-ansicht-hersteller .gr-punkt")) == \
        len(s.select("#gr-ansicht-anbieter .gr-punkt"))
    # Genau EINE ist zu Beginn sichtbar.
    aus = [a for a in s.select(".gr-ansicht")
           if "gr-ansicht--aus" in (a.get("class") or [])]
    assert len(aus) == 1


def test_spalten_der_beiden_ansichten_sind_verschieden(tmp_path):
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    hersteller = {t.get_text(strip=True)
                  for t in s.select("#gr-ansicht-hersteller .gr-spaltenname")}
    anbieter = {t.get_text(strip=True)
                for t in s.select("#gr-ansicht-anbieter .gr-spaltenname")}
    assert "Apple" in hersteller and "Samsung" in hersteller
    assert "Medimax" in anbieter and "Vodafone" in anbieter
    assert hersteller != anbieter


def test_kein_cdn_und_keine_chart_bibliothek(tmp_path):
    """Akzeptanzkriterium aus Teil E - und Hausregel des ganzen Portals."""
    site = _baue(tmp_path)
    roh = (site / "geraete.html").read_text(encoding="utf-8")
    assert "<svg" in roh
    for verboten in ("cdn.", "unpkg", "jsdelivr", "chart.js", "d3.", "plotly"):
        assert verboten not in roh.lower(), verboten


def test_die_karte_zeichnet_die_eigenen_punkte_eigen(tmp_path):
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    eigen = s.select("#gr-ansicht-anbieter "
                     ".gr-flaeche[data-form='band'] .gr-punkt--eigen")
    assert len(eigen) == 1
    assert eigen[0].get("data-anbieter") == "Vodafone"


def test_jeder_punkt_traegt_beleg_und_abrufdatum(tmp_path):
    """Kein Preis ohne Quelle und Datum - bis auf die Seite durchgereicht."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    punkte = s.select("#gr-ansicht-hersteller .gr-punkt")
    assert punkte
    for p in punkte:
        assert p.get("data-url", "").startswith("http")
        assert p.get("data-stand")
        assert p.find("title") is not None


def test_buendelpreise_stehen_nicht_in_der_karte(tmp_path):
    """Teil C4: "1 €" mit Vertrag und "1.199 €" ohne duerfen nie in derselben
    Spalte stehen."""
    daten = json.loads(json.dumps(_DB))
    daten["listungen"].append(_listung(
        "Telekom", "apple-iphone-17-pro-max",
        "apple-iphone-17-pro-max-256gb-schwarz", None, farbe="schwarz",
        zuzahlung=1.0, tarif_referenz="MagentaMobil M"))
    root = tmp_path
    site = _baue(root)
    (root / "data" / "state" / "geraete_db.json").write_text(
        json.dumps(daten), encoding="utf-8")
    render_site(site, root / "data" / "reports")
    s = _suppe(site, "geraete.html")
    preise = {p.get("data-preis") for p in s.select(".gr-punkt")}
    assert "1.00" not in preise
    # ... aber in der Matrix steht sie, mit ihrem Tarif daneben.
    assert "MagentaMobil M" in (site / "geraete.html").read_text(encoding="utf-8")


def test_matrix_zeigt_variantenzahl_und_preisspanne(tmp_path):
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    kopf = [th.get_text(strip=True)
            for th in s.select(".gr-matrix-tabelle thead th")]
    assert kopf[0] == "Gerät"
    assert set(kopf[1:]) == {"Medimax", "ElectronicPartner", "Vodafone"}
    zeilen = s.select(".gr-matrix-tabelle tbody tr")
    assert len(zeilen) == 3


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

    Die Preise liegen dicht beieinander (399 bis 468 EUR). Das ist kein
    Schoenheitsfehler: die Listungen unterscheiden sich nur in der FARBE,
    und seit W1.2 (29.08.2026) sortiert die Plausibilitaetspruefung eine
    Gruppe aus, deren Preisspanne bei gleichem Anbieter, Modell, Speicher
    und Zustand ueber SPANNE_GRENZE liegt. Mit dem alten Abstand von 15 EUR
    je Schritt spannten acht Farben eines Geraets 399 bis 744 EUR auf - 86
    Prozent, und die Pruefung raeumte den Bestand voellig zu Recht ab. Dieser
    Test misst die SCHWELLE, nicht die Preislogik; er braucht deshalb Daten,
    die die Preislogik passieren.
    """
    modelle = ("apple-iphone-17-pro-max", "samsung-galaxy-s25-ultra")
    listungen = []
    for i in range(anzahl_skus):
        name = anbieter[i % len(anbieter)]
        device = modelle[i % len(modelle)]
        listungen.append(_listung(name, device, f"{device}-256gb-farbe-{i}",
                                  399.0 + i * 3))
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


def test_die_schwelle_wird_gerechnet_und_nicht_behauptet(tmp_path):
    """Die Navigation und die gerechnete Schwelle duerfen nicht
    auseinanderlaufen - an beiden Zweigen gemessen, nicht nur an dem, der
    heute gilt."""
    for db, erwartet in ((_db_mit(3), False),
                         (_db_mit(24, anbieter=_UEBER_DER_SCHWELLE), True)):
        site = _baue(tmp_path / f"fall{erwartet}", db=db)
        root = tmp_path / f"fall{erwartet}"
        geraete = geraete_view.aufbereiten(
            root / "data" / "state", lade_quellen(root), lade_katalog(root),
            heute="2026-08-11")
        erreicht = geraete_view.schwelle_erreicht(
            anbieter=geraete["bilanz"]["anbieter"],
            skus=geraete["bilanz"]["skus"],
            hersteller=len(geraete["karte_hersteller"]["spalten"]))
        assert erreicht is erwartet, geraete["bilanz"]
        assert geraete["bilanz"]["schwelle_erreicht"] is erwartet
        verlinkt = "geraete.html" in {
            a.get("href") for a in _suppe(site, "geraete.html").select(".subnav a")}
        assert verlinkt == erreicht


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


def test_der_umschalter_blendet_ohne_neuladen_um(_gebaut):
    """Akzeptanzkriterium aus Teil E. Im HTML nicht pruefbar - die zwei
    Ansichten stehen beide da, entscheidend ist, was der Browser zeigt."""
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
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"http://127.0.0.1:{port}/geraete.html")
            page.wait_for_timeout(250)
            sichtbar = lambda wahl: page.evaluate(
                f"document.querySelector('{wahl}').getBoundingClientRect().height > 0")
            assert sichtbar("#gr-ansicht-hersteller")
            assert not sichtbar("#gr-ansicht-anbieter")
            page.click(".gr-knopf[data-schalter='ansicht'][data-wert='anbieter']")
            page.wait_for_timeout(150)
            assert not sichtbar("#gr-ansicht-hersteller")
            assert sichtbar("#gr-ansicht-anbieter")
            # Der zweite Schalter stellt die DARSTELLUNG. Er benutzt dieselbe
            # Mechanik und eine andere Klasse; blendete er `gr-ansicht--aus`,
            # verschwaende die halbe Grafik.
            sichtbare_flaeche = ("#gr-ansicht-anbieter "
                                 ".gr-flaeche:not(.gr-flaeche--aus)")
            form_vorher = page.get_attribute(sichtbare_flaeche, "data-form")
            andere = "chip" if form_vorher == "band" else "band"
            page.click(f".gr-knopf[data-schalter='form'][data-wert='{andere}']")
            page.wait_for_timeout(150)
            assert page.get_attribute(sichtbare_flaeche, "data-form") == andere
            assert sichtbar("#gr-ansicht-anbieter")
            # Genau EINE Flaeche je Ansicht ist offen. Ohne diese Zeile nimmt
            # `get_attribute` stillschweigend die erste von zweien.
            assert page.eval_on_selector_all(
                sichtbare_flaeche, "els => els.length") == 1
            # Tap auf einen Punkt fuellt die Detailzeile - auf dem Telefon
            # gibt es kein Hover, und ein <title> allein reicht dort nicht.
            # Der Punkt muss aus der SICHTBAREN Flaeche kommen, sonst klickt
            # Playwright in die ausgeblendete und meldet "not visible".
            page.click(f"{sichtbare_flaeche} .gr-punkt")
            page.wait_for_timeout(150)
            detail = page.inner_text("#gr-detail")
            # Und der Filter blendet, ohne die Achse zu verschieben. Diese
            # Zusicherung misst "die Y-Achse gehoert dem Preis" im echten
            # Browser und ist nach dem Umbau wichtiger als vorher.
            hole_cy = (f"document.querySelector('{sichtbare_flaeche} "
                       ".gr-punkt circle').getAttribute('cy')")
            vorher = page.evaluate(hole_cy)
            page.select_option("#gr-segment", "flagship")
            page.wait_for_timeout(150)
            nachher = page.evaluate(hole_cy)
            browser.close()
    finally:
        httpd.shutdown()
    assert "€" in detail and "bei" in detail, detail
    assert vorher == nachher, "der Filter hat die Achse verschoben"


# --------------------------------------------------------------------------
# Die Befunde des zweiten Reviews (10.08.2026) - je ein Reproduktionsfall
# --------------------------------------------------------------------------

from telco_radar.report import geraete_karte  # noqa: E402
from telco_radar.report.geraete_view import _karte, leer  # noqa: E402


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


def test_karte_projiziert_linear_und_beginnt_bei_null():
    """Die Projektion hatte kein einziges Unit-Test - nur eine Fixture mit
    fünf Listungen darüber.

    Geprüft wird die Invariante, nicht ein Einzelwert: die Nulllinie liegt
    auf der Achse, und jeder Preis sitzt linear dazwischen. Die Achse hat
    bewusst Luft nach oben (`y_max` ist die nächste 200er-Stufe ÜBER dem
    höchsten Preis), deshalb sitzt der teuerste Punkt nicht am Rand.
    """
    k = _karte([_punkt(0.0), _punkt(450.0), _punkt(800.0)],
               "hersteller", "Hersteller")
    grund = k["hoehe"] - k["rand_u"]
    hoch = k["hoehe"] - k["rand_o"] - k["rand_u"]
    for p in k["punkte"]:
        erwartet = round(grund - p["preis"] / k["y_max"] * hoch, 1)
        assert p["cy"] == erwartet, (p["preis"], p["cy"], erwartet)
    assert {p["cy"] for p in k["punkte"] if p["preis"] == 0} == {float(grund)}
    # Und die Achse fängt wirklich bei null an.
    assert k["y_ticks"][0]["wert"] == 0


def test_karte_haelt_die_achse_bei_guenstigen_geraeten_offen():
    """`Y_MINDEST`: ein Portfolio aus reinen Einstiegsgeräten drängt sich
    sonst im untersten Zehntel."""
    k = _karte([_punkt(129.0), _punkt(199.0)], "hersteller", "Hersteller")
    assert k["y_max"] == 800


def test_karte_kommt_mit_einem_punkt_und_mit_lauter_gleichen_klar():
    assert _karte([_punkt(499.0)], "hersteller", "H")["anzahl"] == 1
    gleich = _karte([_punkt(499.0, "A · 256 GB"), _punkt(499.0, "B · 256 GB"),
                     _punkt(499.0, "C · 256 GB")], "hersteller", "H")
    assert gleich["anzahl"] == 3
    # Gleicher Preis heisst gleiche HOEHE - ausgewichen wird seitlich.
    # Vorher wanderten die Etiketten nach unten (`ly`), der Punkt blieb
    # oben, und die Grafik behauptete drei verschiedene Preise.
    assert len({p["cy"] for p in gleich["punkte"]}) == 1
    assert len({p["cx"] for p in gleich["punkte"]}) == 3
    assert len({(p["cx"], p["cy"]) for p in gleich["punkte"]}) == 3


def test_das_etikett_haengt_am_punkt():
    """Der Kernbefund der Evaluation vom 11.08.2026.

    Vorher wurden Etiketten je Spalte sequenziell nach unten gestapelt,
    waehrend der Punkt auf seinem Preis blieb: gemessen 181 px Versatz in der
    Hersteller- und 235 px in der Anbieteransicht, 87 von 94 Etiketten weiter
    als drei Prozent daneben. Wer die Grafik las, wie man Grafiken liest, las
    um den Faktor sieben falsch.

    Diese Zusicherung ist strenger als die drei, die sie ersetzt: sie
    verlangt nicht mehr, dass das Etikett IRGENDWO oberhalb der Achse landet,
    sondern dass es an SEINEM Punkt haengt.
    """
    for form, daten in (("chip", [_punkt(199.0 + i * 20, f"Modell {i} · 256 GB")
                                  for i in range(60)]),
                        ("band", _bandpunkte())):
        k = _karte(daten, "hersteller", "Hersteller", form=form)
        beschriftet = [p for p in k["punkte"] if p["beschriftet"]]
        for p in beschriftet:
            versatz = abs(p["label_y"] - p["cy"])
            assert versatz <= geraete_karte.MAX_VERSATZ, (form, p["label_kurz"],
                                                          versatz)
        # Kein Punkt liegt deckungsgleich auf einem anderen.
        assert len({(p["cx"], p["cy"]) for p in k["punkte"]}) == len(k["punkte"])
        # Was kein Etikett bekommt, wird gezaehlt und traegt keinen Stummel.
        assert all(p["label_kurz"] == "" for p in k["punkte"]
                   if not p["beschriftet"])


def test_kein_etikett_steht_unter_der_achse_und_kein_bandname_darueber():
    """Die Trennung, an der der Abnahmetest haengt.

    `gr-etikett` traegt eine Preisaussage und liegt im Zeichenbereich;
    `gr-bandname` ist Achsenmoebel und liegt darunter. Geprueft wird
    BEIDSEITIG - sonst waere die Ausnahme ein Schlupfloch, durch das jedes
    unbequeme Etikett unter die Achse wandern koennte.
    """
    for form, daten in (("chip", [_punkt(199.0 + i * 20, f"Modell {i} · 256 GB")
                                  for i in range(60)]),
                        ("band", _bandpunkte())):
        k = _karte(daten, "hersteller", "Hersteller", form=form)
        # Seit dem 11.08.2026 sind die Preiszahlen der Bandform PUNKTE und
        # keine eigenen Knoten neben dem Band: nur so erfassen der Filter und
        # Kriterium 11 sie.
        etiketten = [p["label_y"] for p in k["punkte"] if p["beschriftet"]]
        assert etiketten, form
        # Die Grenze ist `achse + 4`, nicht `achse`: ein Preis von 0 sitzt
        # AUF der Achse, seine Textgrundlinie also knapp darunter.
        assert all(y <= k["achse_y"] + 4 for y in etiketten), form
        assert all(y >= k["rand_o"] - 1 for y in etiketten), form
        assert all(b["name_y"] > k["achse_y"] for b in k["baender"]), form


def test_die_rueckrechnung_trifft_den_echten_preis():
    """Das Akzeptanzkriterium, maschinell.

    Aus der Etikettenhoehe wird der Preis zurueckgerechnet und gegen den
    echten gehalten. Gegen den Stand vom 11.08.2026 gemessen faellt dieser
    Test mit 87 von 94 Etiketten durch; das ist sein Zweck.
    """
    for form, daten in (("chip", [_punkt(199.0 + i * 20, f"Modell {i} · 256 GB")
                                  for i in range(60)]),
                        ("band", _bandpunkte())):
        k = _karte(daten, "hersteller", "Hersteller", form=form)
        proben = [(p["label_y"], p["preis"]) for p in k["punkte"]
                  if p["beschriftet"]]
        assert proben, form
        for label_y, preis in proben:
            gelesen = geraete_karte.preis_aus_hoehe(
                label_y, k["y_max"], k["achse_y"], k["plot_h"])
            grenze = geraete_karte.toleranz(preis, k["y_max"], k["plot_h"])
            assert abs(gelesen - preis) <= grenze, (form, preis, gelesen)


def test_die_alte_stapelei_faellt_durch_die_rueckrechnung():
    """Die Gegenprobe: ohne sie belegt der Test oben nur, dass die aktuelle
    Rechnung zu sich selbst passt.

    Nachgebaut wird die alte Entzerrung (`ly = max(cy, letzte + 14)`) auf
    denselben Daten. Sie MUSS an der 3-Prozent-Grenze scheitern - taete sie
    es nicht, waere die Grenze zu weit und der Test oben wertlos.
    """
    viele = [_punkt(199.0 + i * 20, f"Modell {i} · 256 GB") for i in range(60)]
    k = _karte(viele, "hersteller", "Hersteller", form="chip")
    letzte, daneben = None, 0
    for p in sorted(k["punkte"], key=lambda p: -p["preis"]):
        ly = p["cy"] if letzte is None else max(p["cy"], letzte + 14)
        letzte = ly
        gelesen = geraete_karte.preis_aus_hoehe(
            ly + geraete_karte.BASISLINIE, k["y_max"], k["achse_y"], k["plot_h"])
        if abs(gelesen - p["preis"]) > geraete_karte.toleranz(
                p["preis"], k["y_max"], k["plot_h"]):
            daneben += 1
    assert daneben > len(k["punkte"]) / 2, (
        f"nur {daneben} von {len(k['punkte'])} Etiketten fielen durch - "
        "die Grenze ist zu weit, der Absicherungstest misst dann nichts")


def test_ein_punkt_ohne_etikett_zeichnet_keinen_leeren_text(tmp_path):
    """Ein leeres `<text>` ist kein leeres Element: es traegt seine Klasse und
    sein `y`, und genau daran haengen die Wahrheitstests der Positionskarte.
    Vor dem 10.08.2026 stand fuer jeden gedeckelten Punkt eines im HTML - im
    ersten echten Lauf waren das 76 Stueck, und Kriterium 11 von
    `pruefe_portal.py` fiel daran durch.

    Der Bestand des Normalfalls hat fuenf Listungen; damit deckelt nichts,
    und der Test waere gruen, ohne etwas zu pruefen. Deshalb eine volle
    Spalte - und zwar mit verschiedenen SPEICHERGROESSEN, nicht mit Farben:
    seit dem 11.08.2026 werden Farben verdichtet, sechzig Farben desselben
    Geraets ergaeben genau EINEN Punkt und der Fall traete nie ein.

    Die Preise liegen bewusst DICHT beieinander (zwei Euro Abstand). Mit den
    frueheren zwanzig Euro passten nach dem Umbau alle sechzig Etiketten -
    die Karte ist jetzt 1180 statt 980 px breit und packt waagerecht, statt
    zu stapeln. Ein Deckelfall braucht deshalb echte Enge."""
    voll = {"updated": "2026-08-11", "anbieter": {"Medimax": {"laeufe": 4}},
            "listungen": [
                dict(_listung("Medimax", "apple-iphone-17-pro-max",
                              f"apple-iphone-17-pro-max-{i}gb-schwarz",
                              199.0 + i * 2), speicher_gb=i + 1)
                for i in range(120)]}
    site = _baue(tmp_path, db=voll)
    s = _suppe(site, "geraete.html")
    flaeche = s.select_one("#gr-ansicht-hersteller .gr-flaeche[data-form='chip']")
    punkte = flaeche.select(".gr-punkt")
    etiketten = flaeche.select(".gr-etikett")
    assert len(punkte) == 120
    assert etiketten and len(etiketten) < len(punkte), \
        "ohne gedeckelte Etiketten prueft der Test nichts"
    assert all(e.get_text(strip=True) for e in etiketten)
    # Die Achse kommt aus dem DOM, nicht aus `540 - 70`: die Hoehe waechst
    # jetzt mit der Zahl der Eintraege, und eine feste Zahl misst dann am
    # falschen Ort, ohne es zu merken.
    achse = float(flaeche.get("data-achse"))
    assert all(float(e.get("y")) <= achse + 4 for e in etiketten)
    # Und die Flaeche sagt, wie viele kein Etikett tragen - eine stille
    # Kappung waere schlimmer als eine sichtbare Luecke. Geprueft wird das
    # Attribut, nicht der Legendentext: die Legende gehoert der AKTIVEN
    # Flaeche, und das ist eine andere als die hier gemessene.
    ohne = int(flaeche.get("data-etiketten-verborgen"))
    assert ohne > 0
    assert len(etiketten) + ohne == len(punkte), (len(etiketten), ohne, len(punkte))


def test_farbvarianten_ergeben_einen_punkt(tmp_path):
    """Der zweite Kernbefund der Evaluation: 60 der 85 Kreise lagen exakt
    deckungsgleich aufeinander, weil je Farbvariante ein Punkt gezeichnet
    wurde. Fuenf Farben desselben iPhone 17 mit 512 GB kosten alle 1199 EUR.

    Farbe ist keine Preisdimension. Sie steht im Tooltip - und einzeln
    weiterhin in der SKU-Matrix, die genau dafuer da ist."""
    farbig = {"updated": "2026-08-11", "anbieter": {"Medimax": {"laeufe": 4}},
              "listungen": [
                  dict(_listung("Medimax", "apple-iphone-17-pro-max",
                                f"apple-iphone-17-pro-max-256gb-farbe-{i}",
                                1449.0), farbe_normalisiert=f"farbe{i}")
                  for i in range(12)]}
    site = _baue(tmp_path, db=farbig)
    s = _suppe(site, "geraete.html")
    flaeche = s.select_one("#gr-ansicht-hersteller .gr-flaeche[data-form='chip']")
    punkte = flaeche.select(".gr-punkt")
    assert len(punkte) == 1, "zwoelf Farben sind EIN Preispunkt"
    assert punkte[0].get("data-farben") == "12"
    assert "12 Farben" in punkte[0].find("title").get_text()
    # In der Matrix stehen sie weiterhin einzeln.
    assert len(s.select(".gr-varianten .gr-variante")) >= 12


def test_kein_chip_verlaesst_seine_spalte():
    """Befund 2 des zweiten Reviews, in der schaerferen Fassung.

    Vorher wurde auf die halbe Spaltenbreite GEKUERZT und gehofft; geprueft
    wird jetzt die echte Kastenbreite gegen die echten Spaltengrenzen. Neun
    Spalten sind der Stressfall: dort passt ein langer Modellname nicht mehr,
    und die richtige Antwort ist, das Etikett WEGZULASSEN."""
    punkte = [_punkt(500.0 + i * 40, "Galaxy Z Fold 7 · 1024 GB",
                     spalte=f"Marke {i}") for i in range(9)]
    k = _karte(punkte, "hersteller", "Hersteller", form="chip")
    nach_name = {s["name"]: s for s in k["spalten"]}
    mit_chip = [p for p in k["punkte"] if p["chip"]]
    # Ohne diese Zeile ist der Test gruen, sobald die Chiperzeugung ganz
    # ausfaellt - die Schleife laeuft dann leer (CLAUDE.md §6).
    assert mit_chip, "kein einziger Chip erzeugt - der Test prueft nichts"
    for p in mit_chip:
        s = nach_name[p["spalte"]]
        assert p["chip"]["x"] >= s["x0"], (p["label_kurz"], p["chip"], s)
        assert p["chip"]["x"] + p["chip"]["w"] <= s["x1"], \
            (p["label_kurz"], p["chip"], s)


def test_legende_nennt_listungen_und_das_echte_abrufdatum(tmp_path):
    """Befund 3+4: die Legende schrieb „N Geräte" über eine Zahl von
    LISTUNGEN und behauptete als Abrufdatum den Berichtstag."""
    import re
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    # Zeilenumbrueche der Vorlage einebnen: geprueft wird der SATZ, nicht der
    # Umbruch. Ohne das faellt der Test, sobald jemand die Vorlage anders
    # umbricht - und meldet damit etwas, das niemanden betrifft.
    legende = re.sub(r"\s+", " ", s.select_one("#gr-legende").get_text(" ", strip=True))
    assert "Listungen" in legende
    kacheln = {k.find("span").get_text(strip=True): k.find("b").get_text(strip=True)
               for k in s.select(".gr-bilanz .t-kennzahl")}
    # Dieselbe Zahl unter demselben Wort - an beiden Orten.
    assert f"von {kacheln['Geräte beobachtet']} Geräten" in legende
    # Preispunkte und Listungen sind seit der Verdichtung ZWEI Zahlen. Eine
    # fuer beides waere genau der Fehlertyp aus CLAUDE.md §6: ein Etikett und
    # ein Feld, die nicht dasselbe meinen.
    flaeche = s.select_one(".gr-flaeche[data-form='chip']")
    punkte = len(flaeche.select(".gr-punkt"))
    assert f"{punkte} Preispunkte" in legende, legende
    varianten = sum(int(p.get("data-varianten") or 1)
                    for p in flaeche.select(".gr-punkt"))
    assert f"aus {varianten} Listungen" in legende, legende
    # Und das Abrufdatum kommt aus den Daten, nicht aus dem Bericht.
    staende = {p.get("data-stand") for p in s.select(".gr-punkt")}
    assert len(staende) == 1
    from telco_radar.report.html import _fmt_date_de
    assert _fmt_date_de(next(iter(staende))) in legende


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


def test_der_notzustand_traegt_jedes_feld_der_vorlage():
    """`leer()` muss dieselbe Form haben wie `aufbereiten()` - sonst kippt
    die Vorlage genau dann, wenn sie den Fehler melden soll."""
    notfall = leer("ValueError: irgendwas")
    assert notfall["fehler"]
    assert notfall["hat_daten"] is False
    for schluessel in ("bilanz", "karte_hersteller", "karte_anbieter", "matrix",
                       "lifecycle", "quellenlage", "auffaellig", "katalog"):
        assert schluessel in notfall


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

def test_zwei_marken_eines_ladens_sind_eine_spalte(tmp_path):
    """`shop`/`anzeige` aus der Konfiguration - die eigentliche
    Verhaltensaenderung des Umbaus.

    mobilcom-debitel und freenet sind derselbe Shop; als zwei Spalten
    verglichen sie einen Laden mit sich selbst, und die Aggregation erzeugte
    zwei deckungsgleiche Punkte. Im Testbestand steht ElectronicPartner mit
    `shop: ep` und einem eigenen Anzeigenamen."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    spalten = {x.get_text(strip=True)
               for x in s.select("#gr-ansicht-anbieter .gr-spaltenname")}
    assert "ep.de (ElectronicPartner)" in spalten, spalten
    assert "ElectronicPartner" not in spalten
    # Und der Punkt traegt beide Namen: den Anzeigenamen fuer den Leser, den
    # Rohnamen fuer Filter und Tests.
    punkte = s.select("#gr-ansicht-anbieter .gr-flaeche[data-form='chip'] .gr-punkt")
    paare = {(p.get("data-anbieter"), p.get("data-anbieter-key")) for p in punkte}
    assert ("ep.de (ElectronicPartner)", "ElectronicPartner") in paare, paare


def test_die_schwelle_zaehlt_laeden_und_nicht_marken(tmp_path):
    """Die Kachel "Anbieter mit Daten" und die Spaltenzahl der Karte muessen
    dieselbe Sache zaehlen.

    Mit Marken gezaehlt schaltete sich der Navigationseintrag mit "2
    Anbietern" frei, waehrend die Karte EINE Spalte zeigte - genau der
    Fehlertyp aus CLAUDE.md §6: ein Etikett und ein Feld, die nicht dasselbe
    meinen."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    kacheln = {k.find("span").get_text(strip=True): k.find("b").get_text(strip=True)
               for k in s.select(".gr-bilanz .t-kennzahl")}
    spalten = s.select("#gr-ansicht-anbieter .gr-flaeche[data-form='chip'] "
                       ".gr-spaltenname")
    assert kacheln["Anbieter mit Daten"] == str(len(spalten)), (
        kacheln["Anbieter mit Daten"], len(spalten))


def test_der_achsenhinweis_nennt_die_datengrundlage(tmp_path):
    """"Hersteller" zeigt nicht Apples Portfolio, sondern das, was die
    erfassten Haendler von Apple fuehren. Solange das so ist, sagt es die
    Spaltenzeile selbst."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    hinweise = [x.get_text(" ", strip=True) for x in s.select(".gr-achsname")]
    assert hinweise
    laeden = len(s.select("#gr-ansicht-anbieter .gr-flaeche[data-form='chip'] "
                          ".gr-spaltenname"))
    wort = "Händler" if laeden == 1 else "Händlern"
    assert any(f"Preise von {laeden} {wort}" in h for h in hinweise), hinweise


def test_die_tabelle_zeigt_dieselben_zahlen_wie_die_karte(tmp_path):
    """Die Aufklapptabelle unter der Grafik ist der Zugang fuer alle, die die
    Karte nicht lesen koennen. Sie speist sich aus DERSELBEN Punktliste -
    eine zweite Aufbereitung wuerde driften, und niemand merkte es."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    punkte = s.select("#gr-ansicht-hersteller .gr-flaeche[data-form='chip'] .gr-punkt")
    zeilen = s.select(".gr-tabelle-auf tbody tr")
    assert len(zeilen) == len(punkte), (len(zeilen), len(punkte))
    aus_karte = sorted(p.get("data-preis") for p in punkte)
    aus_tabelle = sorted(
        z.select("td")[3].get_text(strip=True).replace(" €", "") for z in zeilen)
    assert aus_karte == aus_tabelle, (aus_karte[:3], aus_tabelle[:3])
    for z in zeilen:
        assert z.select_one("a[href^='http']") is not None


def test_der_notzustand_traegt_dieselben_flaechen_wie_der_normalfall(tmp_path):
    """`leer()` existiert, damit ein kaputter Eintrag die Seite nicht
    mitreisst. Das kann er nur, wenn er jedes Feld traegt, das die Vorlage
    liest - hier: dieselben vier Flaechen unter denselben Schluesseln."""
    from telco_radar.report.geraete_view import aufbereiten, leer
    root = tmp_path
    _baue(root)
    voll = aufbereiten(root / "data" / "state",
                       lade_quellen(root), lade_katalog(root))
    notzustand = leer("kaputt")
    assert set(notzustand["flaechen"]) == set(voll["flaechen"])
    for schluessel, k in notzustand["flaechen"].items():
        assert set(k) >= set(voll["flaechen"][schluessel]) - {"y_schritt"}, schluessel
    assert notzustand["formen"] == voll["formen"]


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


def test_die_vergleichssektion_nennt_den_guenstigsten_mit_namen(tmp_path):
    """Die woertliche Anforderung: nicht DASS es guenstiger ist, sondern
    BEI WEM."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    abschnitt = s.select_one(".gr-vergleich")
    assert abschnitt is not None, "die Sektion fehlt ganz"
    text = abschnitt.get_text(" ", strip=True)
    assert "Wer ist günstiger als Vodafone?" in text
    assert "Medimax" in text, "der guenstigste Wettbewerber steht mit Namen da"
    assert "150,00" in text, "die Differenz steht da (1349 - 1199)"
    assert "11,1" in text, "und der Prozentsatz"


def test_jede_vergleichszeile_traegt_beide_quellen_und_beide_daten(tmp_path):
    """"Kein Vergleich ohne beide Quelllinks und beide Abrufdaten." Auf der
    Seite gemessen, nicht nur in der Rechnung."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    zeilen = s.select(".gr-vergleich .gr-v-zeile")
    assert zeilen, "keine einzige Vergleichszeile"
    for zeile in zeilen:
        eigen = zeile.select_one(".gr-eigen-spalte")
        assert eigen.select_one("a[href]"), "Vodafone ohne Quelllink"
        assert eigen.select_one(".gr-v-datum"), "Vodafone ohne Abrufdatum"
        bester = zeile.select_one(".gr-v-name")
        if bester is None:
            continue          # "niemand guenstiger" - eine gueltige Zeile
        zelle = bester.parent
        assert zelle.select_one("a[href]"), "Wettbewerber ohne Quelllink"
        assert zelle.select_one(".gr-v-datum"), "Wettbewerber ohne Abrufdatum"


def test_der_aufklapper_listet_alle_guenstigeren(tmp_path):
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    auf = s.select_one(".gr-vergleich .gr-v-alle details")
    assert auf is not None, "zwei guenstigere Anbieter, aber kein Aufklapper"
    namen = [x.get_text(strip=True) for x in auf.select(".gr-v-name")]
    # LADENnamen, nicht Markennamen: die Testkonfiguration fuehrt
    # ElectronicPartner unter `shop: ep`. Verglichen werden Laeden - sonst
    # zaehlte derselbe Shop unter zwei Marken zweimal als "guenstiger".
    assert set(namen) == {"Medimax", "ep"}


def test_die_zeile_ohne_guenstigeren_wettbewerber_bleibt_stehen(tmp_path):
    """"Nirgends guenstiger" ist die Auskunft, wegen der man die Liste liest."""
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    text = s.select_one(".gr-vergleich").get_text(" ", strip=True)
    assert "niemand günstiger" in text


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
    for datum in s.select(".gr-vergleich .gr-v-datum"):
        text = datum.get_text(strip=True)
        if not text or not text[0].isdigit():
            continue
        assert "-" not in text, f"ISO-Datum auf der Seite: {text!r}"


def test_der_anbieterfilter_steht_mit_drei_knoepfen_bereit(tmp_path):
    site = _baue(tmp_path, db=_db_mit_vergleich())
    s = _suppe(site, "geraete.html")
    knoepfe = [k.get("data-typ") for k in
               s.select(".gr-vergleich-filter .gr-filter-knopf")]
    assert knoepfe == ["alle", "netzbetreiber", "handel"]
    # Und jede Zeile sagt, zu welchen Typen ihre guenstigeren Anbieter zaehlen.
    for zeile in s.select(".gr-vergleich .gr-v-zeile"):
        assert zeile.has_attr("data-typen")


def test_ohne_vergleichsdaten_steht_die_sektion_gar_nicht_da(tmp_path):
    """Ein leerer Kasten mit Ueberschrift sagt "kaputt", nicht "noch keine
    Daten"."""
    ohne = {"updated": "2026-08-11", "anbieter": {}, "listungen": []}
    site = _baue(tmp_path, db=ohne, punkte=[])
    s = _suppe(site, "geraete.html")
    assert s.select_one(".gr-vergleich") is None


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
    assert s.select_one(".gr-vergleich") is not None


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

@pytest.mark.parametrize("zustand", ["refurbished", "b-ware", "unbekannt"])
def test_die_preisgrafik_zeigt_nur_neugeraete(zustand):
    """Dieselbe Regel wie im Vergleich, aus demselben Grund: die Karte
    ordnet Punkte nach Preis auf einer Achse. Ein Gebrauchtpreis darunter
    liest sich wie ein guenstiger Neupreis - die Y-Achse traegt keine
    Zustandsangabe."""
    from telco_radar.report.geraete_karte import aggregiere
    punkte = [
        {"device_id": "apple-iphone-17", "speicher": 256, "anbieter": "o2",
         "preis": 899.0, "zustand": "neu", "modell": "iPhone 17",
         "hersteller": "Apple"},
        {"device_id": "apple-iphone-17", "speicher": 256, "anbieter": "o2",
         "preis": 499.0, "zustand": zustand, "modell": "iPhone 17",
         "hersteller": "Apple"},
    ]
    erg = aggregiere(punkte)
    assert [p["preis"] for p in erg] == [899.0], (
        f"{zustand} darf keinen Preispunkt bilden")


def test_die_preisgrafik_behaelt_neugeraete():
    """Gegenprobe: ohne sie waere eine Karte, die ALLES verwirft, gruen."""
    from telco_radar.report.geraete_karte import aggregiere
    punkte = [
        {"device_id": "apple-iphone-17", "speicher": 256, "anbieter": "o2",
         "preis": 899.0, "zustand": "neu", "modell": "iPhone 17",
         "hersteller": "Apple"},
        {"device_id": "apple-iphone-17", "speicher": 256, "anbieter": "freenet",
         "preis": 879.0, "zustand": "neu", "modell": "iPhone 17",
         "hersteller": "Apple"},
    ]
    assert len(aggregiere(punkte)) == 2


def test_die_pruefung_schaltet_die_navigation_nicht(tmp_path):
    """Befund des Reviews vom 29.08.2026: `schwelle_erreicht` nahm die
    Spaltenzahl der Herstelleransicht, und die hängt seit W1.2 an der
    Plausibilitätsprüfung. Damit hätte ein Anbieter, der an einem Tag seine
    Farbvarianten mit großem Abstand bepreist, den Navigationseintrag
    „Geräte" auf JEDER Seite verschwinden lassen – ohne Fehler, ohne
    Warnung. Eine Datenqualitätsheuristik darf keine Navigation schalten.

    Die Fixture spannt genau diesen Fall auf: Preise von 399 bis 744 EUR für
    dieselbe (Anbieter, Modell, Speicher, Zustand)-Gruppe. Die Prüfung räumt
    sie ab – die Schwelle muss trotzdem stehen."""
    db = _db_mit(24, anbieter=_UEBER_DER_SCHWELLE)
    for i, listung in enumerate(db["listungen"]):
        listung["preis_ohne_vertrag"] = 399.0 + i * 15

    site = _baue(tmp_path, db=db)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")

    # Gegenprobe: der Fall tritt wirklich ein, sonst misst der Test nichts.
    assert geraete["pruefung"]["aussortiert"] > 0, "Prüfung greift gar nicht"
    assert geraete["bilanz"]["schwelle_erreicht"] is True
    ziele = {a.get("href") for a in _suppe(site, "index.html").select(".subnav a")}
    assert "geraete.html" in ziele


def test_die_legende_zaehlt_die_listungen_die_wirklich_gezeichnet_werden(tmp_path):
    """"153 Preispunkte aus 348 Listungen" war falsch, sobald die Karte nur
    noch Neugeräte zeichnet: 9 refurbished Listungen standen im Nenner und
    nicht in der Grafik. Auf einer Seite, deren Verkaufsargument der
    Belegzwang ist, ist das die teuerste Sorte falscher Zahl."""
    db = _db_mit(24, anbieter=_UEBER_DER_SCHWELLE)
    for listung in db["listungen"][:6]:
        listung["zustand"] = "refurbished"
        listung["sku_id"] = listung["sku_id"] + "-refurbished"
        listung["id"] = listung["id"] + "-refurbished"

    _baue(tmp_path, db=db)
    geraete = geraete_view.aufbereiten(
        tmp_path / "data" / "state", lade_quellen(tmp_path),
        lade_katalog(tmp_path), heute="2026-08-11")

    assert geraete["bilanz"]["listungen"] == 24
    assert geraete["bilanz"]["aggregiert_aus"] == 18, (
        "die 6 refurbished Listungen gehören nicht in den Nenner der Grafik")
    assert geraete["bilanz"]["in_der_karte"] <= geraete["bilanz"]["aggregiert_aus"]


def test_der_pruefbericht_nennt_dieselben_zahlen_wie_die_pruefung(tmp_path):
    """Die neue Sektion auf /geraete-quellen.html wurde von keinem Test
    gerendert – und zeigte deshalb zweimal die Zahl der BEFUNDE, wo die Zahl
    der aussortierten LISTUNGEN gemeint war. Genau der Fehlertyp aus
    CLAUDE.md §6: ein Etikett und ein Feld, die nicht dasselbe meinen."""
    db = _db_mit(24, anbieter=_UEBER_DER_SCHWELLE)
    for i, listung in enumerate(db["listungen"]):
        listung["preis_ohne_vertrag"] = 399.0 + i * 15
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

def test_eine_spalte_traegt_hoechstens_zwoelf_baender():
    """Die Apple-Spalte trug rund 40 Bänder, die Samsung-Spalte 38. Die
    Bandform war richtig gewählt – sie hatte nur keine Obergrenze. Eine
    Spalte mit 38 Schlitzen gibt jedem Schlitz acht Pixel, und darin steht
    kein Modellname mehr."""
    from telco_radar.report import geraete_karte

    punkte = [{"device_id": f"samsung-galaxy-s{n}", "modell": f"Galaxy S{n}",
               "hersteller": "Samsung", "shop": "o2", "anbieter": "o2",
               "speicher": 256, "preis": 500.0 + n * 10, "zustand": "neu",
               "generation": n, "aktuelle_generation": n == 26}
              for n in range(1, 31)]
    flaeche = geraete_karte.karte(geraete_karte.aggregiere(punkte),
                                  "hersteller", "Hersteller",
                                  form=geraete_karte.FORM_BAND)
    je_spalte = {}
    for b in flaeche["baender"]:
        je_spalte[b["spalte"]] = je_spalte.get(b["spalte"], 0) + 1
    assert je_spalte, "keine Bänder - dann prüft der Test nichts"
    assert max(je_spalte.values()) <= geraete_karte.BAND_MAX_JE_SPALTE


def test_die_kappung_behaelt_die_aktuelle_generation():
    """Gekappt wird nach Rang, nicht nach Listenposition. Die aktuelle
    Generation ist die, wegen der jemand die Grafik ansieht – sie darf nicht
    herausfallen, weil ein Vorgänger alphabetisch vorne steht."""
    from telco_radar.report import geraete_karte

    punkte = [{"device_id": f"samsung-galaxy-s{n}", "modell": f"Galaxy S{n}",
               "hersteller": "Samsung", "shop": "o2", "anbieter": "o2",
               "speicher": 256, "preis": 500.0, "zustand": "neu",
               "generation": n, "aktuelle_generation": n >= 26}
              for n in range(1, 31)]
    flaeche = geraete_karte.karte(geraete_karte.aggregiere(punkte),
                                  "hersteller", "Hersteller",
                                  form=geraete_karte.FORM_BAND)
    gezeigt = {b["name_kurz"] for b in flaeche["baender"]}
    for n in range(26, 31):
        assert f"Galaxy S{n}" in gezeigt, f"Galaxy S{n} fehlt"


def test_eine_kleine_spalte_wird_nicht_gekappt():
    """Gegenprobe: die Grenze darf nur greifen, wo sie gebraucht wird."""
    from telco_radar.report import geraete_karte

    punkte = [{"device_id": f"nothing-phone-{n}", "modell": f"Phone {n}",
               "hersteller": "Nothing", "shop": "o2", "anbieter": "o2",
               "speicher": 256, "preis": 400.0 + n, "zustand": "neu",
               "generation": n, "aktuelle_generation": n == 3}
              for n in range(1, 4)]
    flaeche = geraete_karte.karte(geraete_karte.aggregiere(punkte),
                                  "hersteller", "Hersteller",
                                  form=geraete_karte.FORM_BAND)
    assert len(flaeche["baender"]) == 3
    assert flaeche["baender_uebersprungen"] == 0


def test_beide_ansichten_zeigen_nach_der_kappung_dieselben_punkte():
    """`pruefe_portal.py` Kriterium 11 verlangt seit dem 10.08.2026 gleich
    viele Punkte je Ansicht. Je SPALTE gekappt behielte die
    Herstelleransicht (Spalte = Hersteller) andere Geräte als die
    Anbieteransicht (Spalte = Laden) – zwei Ansichten derselben Daten mit
    verschiedenen Punkten. Die Auswahl fällt deshalb je Hersteller, einmal
    für beide."""
    from telco_radar.report import geraete_karte

    punkte = []
    for n in range(1, 21):
        for shop in ("o2", "freenet", "Vodafone"):
            punkte.append({
                "device_id": f"samsung-galaxy-s{n}", "modell": f"Galaxy S{n}",
                "hersteller": "Samsung", "shop": shop, "anbieter": shop,
                "speicher": 256, "preis": 500.0 + n * 10, "zustand": "neu",
                "generation": n, "aktuelle_generation": n == 20})
    agg = geraete_karte.aggregiere(punkte)
    nach_hersteller = geraete_karte.karte(agg, "hersteller", "Hersteller",
                                          form=geraete_karte.FORM_BAND)
    nach_anbieter = geraete_karte.karte(agg, "shop", "Anbieter",
                                        form=geraete_karte.FORM_BAND)
    # Gegenprobe: die Kappung greift wirklich, sonst prüft der Test nichts.
    assert nach_hersteller["baender_uebersprungen"] > 0
    assert len(nach_hersteller["punkte"]) == len(nach_anbieter["punkte"])
    schluessel = lambda k: {(p["device_id"], p.get("shop"), p.get("speicher"))
                            for p in k["punkte"]}
    assert schluessel(nach_hersteller) == schluessel(nach_anbieter)


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
    for auswahl in (".gr-vergleich", ".gr-matrix", ".gr-karte"):
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


def test_die_grenze_gilt_in_BEIDEN_ansichten():
    """Gekappt wird je Hersteller UND je Laden. Nur je Hersteller gedeckelt
    hielt die Herstelleransicht ihre zwölf, während in der Anbieteransicht
    sechs Hersteller in DERSELBEN Ladenspalte landeten – gemessen am
    29.08.2026: o2 23 Bänder, Vodafone 21. Genau der Befund, der die
    Obergrenze ausgelöst hat, nur eine Ansicht weiter."""
    from telco_radar.report import geraete_karte

    punkte = []
    for hersteller, praefix in (("Apple", "iPhone"), ("Samsung", "Galaxy S"),
                                ("Google", "Pixel")):
        for n in range(1, 16):
            for shop in ("o2", "Vodafone"):
                punkte.append({
                    "device_id": f"{hersteller.lower()}-{n}", "shop": shop,
                    "modell": f"{praefix} {n}", "hersteller": hersteller,
                    "anbieter": shop, "speicher": 256, "zustand": "neu",
                    "preis": 400.0 + n * 20, "generation": n,
                    "aktuelle_generation": n == 15})
    agg = geraete_karte.aggregiere(punkte)
    for feld, achse in (("hersteller", "Hersteller"), ("shop", "Anbieter")):
        flaeche = geraete_karte.karte(agg, feld, achse,
                                      form=geraete_karte.FORM_BAND)
        je_spalte = {}
        for b in flaeche["baender"]:
            je_spalte[b["spalte"]] = je_spalte.get(b["spalte"], 0) + 1
        assert je_spalte, f"{achse}: keine Bänder"
        assert max(je_spalte.values()) <= geraete_karte.BAND_MAX_JE_SPALTE, (
            f"{achse}: {je_spalte}")


def test_die_rettung_eines_ladens_reisst_die_grenze_nicht():
    """Ein Laden darf nicht ganz herausfallen – aber die Rettung VERDRÄNGT,
    sie hängt nicht an. Angehängt stand Samsung mit 13 Bändern da, weil ALDI
    TALKs einzige Listung ein Samsung ist."""
    from telco_radar.report import geraete_karte

    punkte = [{"device_id": f"s{n}", "modell": f"Galaxy S{n}",
               "hersteller": "Samsung", "shop": "o2", "anbieter": "o2",
               "speicher": 256, "zustand": "neu", "preis": 500.0 + n,
               "generation": n, "aktuelle_generation": n == 30}
              for n in range(1, 31)]
    punkte.append({"device_id": "a17", "modell": "Galaxy A17",
                   "hersteller": "Samsung", "shop": "ALDI TALK",
                   "anbieter": "ALDI TALK", "speicher": 128, "zustand": "neu",
                   "preis": 129.0, "generation": 17,
                   "aktuelle_generation": False})
    gezeigt = geraete_karte.gekappt(geraete_karte.aggregiere(punkte))
    laeden = {p["shop"] for p in gezeigt}
    assert laeden == {"o2", "ALDI TALK"}, "ein Laden ist ganz herausgefallen"
    assert len(gezeigt) <= geraete_karte.BAND_MAX_JE_SPALTE


def test_die_kappung_ist_idempotent():
    """Sie läuft an ZWEI Stellen – in `aufbereiten` für Legende und Bilanz,
    in `karte()` für den direkten Aufruf. Wäre sie nicht idempotent, zeigte
    die Grafik weniger als ihre eigene Legende sagt."""
    from telco_radar.report import geraete_karte

    punkte = [{"device_id": f"s{n}", "modell": f"Galaxy S{n}",
               "hersteller": "Samsung", "shop": "o2", "anbieter": "o2",
               "speicher": 256, "zustand": "neu", "preis": 500.0 + n,
               "generation": n, "aktuelle_generation": n == 30}
              for n in range(1, 31)]
    einmal = geraete_karte.gekappt(geraete_karte.aggregiere(punkte))
    assert len(einmal) == geraete_karte.BAND_MAX_JE_SPALTE
    assert len(geraete_karte.gekappt(einmal)) == len(einmal)


def test_ein_punkt_ohne_preis_reisst_die_kappung_nicht():
    """`karte()` filtert preislose Punkte, `gekappt()` tat es nicht – und
    `-p["preis"]` wäre dort gescheitert. `aufbereiten` hätte geworfen,
    `html.py` es abgefangen, und die Geräteseite wäre stumm auf `leer()`
    gefallen, samt Navigationseintrag."""
    from telco_radar.report import geraete_karte

    punkte = [{"device_id": "s1", "modell": "Galaxy S1", "hersteller": "Samsung",
               "shop": "o2", "anbieter": "o2", "speicher": 256,
               "zustand": "neu", "preis": None, "generation": 1},
              {"device_id": "s2", "modell": "Galaxy S2", "hersteller": "Samsung",
               "shop": "o2", "anbieter": "o2", "speicher": 256,
               "zustand": "neu", "preis": 500.0, "generation": 2}]
    assert len(geraete_karte.gekappt(punkte)) == 1


def test_kein_hersteller_faellt_ganz_aus_der_grafik():
    """Dieselbe Regel wie für Läden, eine Achse weiter. Nur Läden zu retten
    ließ „Nothing" ganz aus der Herstelleransicht fallen, sobald der
    Ladendeckel band – eine Spalte, die es im Bestand gibt und in der Grafik
    nicht, ist eine stille Falschaussage über den Markt."""
    from telco_radar.report import geraete_karte

    punkte = []
    # Zwei große Hersteller füllen beide Ladenspalten ...
    for hersteller in ("Apple", "Samsung"):
        for n in range(1, 16):
            for shop in ("o2", "Vodafone"):
                punkte.append({
                    "device_id": f"{hersteller}-{n}", "shop": shop,
                    "modell": f"{hersteller} {n}", "hersteller": hersteller,
                    "anbieter": shop, "speicher": 256, "zustand": "neu",
                    "preis": 900.0 + n, "generation": n,
                    "aktuelle_generation": n == 15})
    # ... und ein kleiner mit einem einzigen, schwach gereihten Gerät.
    punkte.append({"device_id": "nothing-1", "shop": "o2", "anbieter": "o2",
                   "modell": "Nothing Phone (1)", "hersteller": "Nothing",
                   "speicher": 256, "zustand": "neu", "preis": 300.0,
                   "generation": 1, "aktuelle_generation": False})

    gezeigt = geraete_karte.gekappt(geraete_karte.aggregiere(punkte))
    assert {p["hersteller"] for p in gezeigt} == {"Apple", "Samsung", "Nothing"}
    for feld, achse in (("hersteller", "Hersteller"), ("shop", "Anbieter")):
        flaeche = geraete_karte.karte(geraete_karte.aggregiere(punkte), feld,
                                      achse, form=geraete_karte.FORM_BAND)
        je_spalte = {}
        for b in flaeche["baender"]:
            je_spalte[b["spalte"]] = je_spalte.get(b["spalte"], 0) + 1
        assert max(je_spalte.values()) <= geraete_karte.BAND_MAX_JE_SPALTE, (
            f"{achse}: {je_spalte}")
