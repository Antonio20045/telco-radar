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
# und was kostet es?") und gehoert in die Navigation. Die Zahlen sind
# bewusst niedrig und trotzdem hart: drei Anbieter, weil ein Preisvergleich
# mit zwei Spalten kein Vergleich ist; zwei Hersteller, weil eine
# Positionskarte mit einem Hersteller keine Marktverteilung zeigt; zwanzig
# SKUs, weil darunter jede Aussage an einem einzelnen Geraet haengt.
#
# Wer die Seite verlinken will, misst gegen diese Zahlen und aendert diesen
# Test - dieselbe Disziplin wie bei tarife.html und lieferzeit.html
# (CLAUDE.md §5).
SCHWELLE_ANBIETER = 3
SCHWELLE_HERSTELLER = 2
SCHWELLE_SKUS = 20


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


def _baue(tmp_path: Path, db=None):
    """Eine vollstaendige Site rendern - mit echtem Bericht, echtem Zustand.

    `db` ersetzt den Bestand, wenn ein Fall mehr Listungen braucht als die
    fuenf des Normalfalls (etwa: eine volle Spalte der Positionskarte)."""
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
        "\n".join(json.dumps(p) for p in _PUNKTE) + "\n", encoding="utf-8")

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
    modelle = {p.get("data-modell")
               for p in s.select("#gr-ansicht-hersteller .gr-punkt")}
    # Das ausgelistete Galaxy S25 Ultra 512 GB von Medimax faellt raus, das
    # aktive von Vodafone bleibt.
    assert "Galaxy S25 Ultra" in modelle
    punkte = s.select("#gr-ansicht-hersteller .gr-punkt")
    assert len(punkte) == 4


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
    eigen = s.select("#gr-ansicht-anbieter .gr-punkt--eigen")
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
    """Akzeptanzkriterium: unter N Messpunkten kein Trend, sondern ein Satz,
    der das sagt."""
    site = _baue(tmp_path)
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

def test_seite_steht_nicht_in_der_navigation(tmp_path):
    """Solange die Schwelle nicht erreicht ist, wird die Seite gebaut,
    getestet und ist ueber ihren direkten Link erreichbar - aber nicht
    verlinkt. Dieselbe Regel wie bei tarife.html und lieferzeit.html."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    nav = s.select(".subnav a") or s.select("nav a")
    ziele = {a.get("href") for a in nav}
    assert "geraete.html" not in ziele


def test_die_schwelle_ist_beziffert_und_wird_gemessen(tmp_path):
    """Wer die Seite verlinken will, misst hier nach und aendert DIESEN Test.

    Der Zweck der Zeile ist, dass die Zahlen nicht in einer Prosaregel
    stehen, sondern gerechnet werden - eine Schwelle, die niemand misst, ist
    eine Meinung.
    """
    site = _baue(tmp_path)
    root = tmp_path
    geraete = geraete_view.aufbereiten(
        root / "data" / "state", lade_quellen(root), lade_katalog(root),
        heute="2026-08-11")
    erreicht = (geraete["bilanz"]["anbieter"] >= SCHWELLE_ANBIETER
                and geraete["bilanz"]["skus"] >= SCHWELLE_SKUS
                and len(geraete["karte_hersteller"]["spalten"]) >= SCHWELLE_HERSTELLER)
    s = _suppe(site, "geraete.html")
    verlinkt = "geraete.html" in {a.get("href") for a in s.select(".subnav a")}
    assert verlinkt == erreicht, (
        "Navigation und Veroeffentlichungsschwelle sind auseinandergelaufen: "
        f"erreicht={erreicht}, verlinkt={verlinkt}")


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
            page.click(".gr-knopf[data-zeige='anbieter']")
            page.wait_for_timeout(150)
            assert not sichtbar("#gr-ansicht-hersteller")
            assert sichtbar("#gr-ansicht-anbieter")
            # Tap auf einen Punkt fuellt die Detailzeile - auf dem Telefon
            # gibt es kein Hover, und ein <title> allein reicht dort nicht.
            page.click("#gr-ansicht-anbieter .gr-punkt")
            page.wait_for_timeout(150)
            detail = page.inner_text("#gr-detail")
            # Und der Filter blendet, ohne die Achse zu verschieben.
            vorher = page.evaluate(
                "document.querySelector('#gr-ansicht-anbieter .gr-punkt circle')"
                ".getAttribute('cy')")
            page.select_option("#gr-segment", "flagship")
            page.wait_for_timeout(150)
            nachher = page.evaluate(
                "document.querySelector('#gr-ansicht-anbieter .gr-punkt circle')"
                ".getAttribute('cy')")
            browser.close()
    finally:
        httpd.shutdown()
    assert "€" in detail and "bei" in detail, detail
    assert vorher == nachher, "der Filter hat die Achse verschoben"


# --------------------------------------------------------------------------
# Die Befunde des zweiten Reviews (10.08.2026) - je ein Reproduktionsfall
# --------------------------------------------------------------------------

from telco_radar.report.geraete_view import _karte, leer  # noqa: E402


def _punkt(preis, label="Modell · 256 GB", spalte="Apple", eigen=False):
    return {"preis": preis, "label": label, "hersteller": spalte,
            "anbieter": spalte, "eigen": eigen, "segment": "", "speicher": 256}


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
    gleich = _karte([_punkt(499.0), _punkt(499.0), _punkt(499.0)],
                    "hersteller", "H")
    assert gleich["anzahl"] == 3
    # Entzerrt, aber die PUNKTE liegen weiter auf demselben Preis.
    assert len({p["cy"] for p in gleich["punkte"]}) == 1
    assert len({p["ly"] for p in gleich["punkte"]}) == 3


def test_kein_etikett_rutscht_unter_die_nulllinie():
    """Befund 1 des zweiten Reviews: `ly` wuchs unbegrenzt. Bei 60 Punkten in
    einer Spalte standen 31 Etiketten unter der Achse und 26 außerhalb des
    viewBox - der Punkt blieb richtig, das Etikett log."""
    viele = [_punkt(199.0 + i * 20, f"Modell {i} · 256 GB") for i in range(60)]
    k = _karte(viele, "hersteller", "Hersteller")
    unterkante = k["hoehe"] - k["rand_u"]
    assert all(p["ly"] <= unterkante for p in k["punkte"])
    # Was nicht mehr passt, bekommt KEIN Etikett - und wird gezählt.
    assert k["etiketten_verborgen"] > 0
    beschriftet = [p for p in k["punkte"] if p["beschriftet"]]
    assert len(beschriftet) + k["etiketten_verborgen"] == len(k["punkte"])
    assert all(p["label_kurz"] == "" for p in k["punkte"] if not p["beschriftet"])


def test_die_grundlinie_des_etiketts_bleibt_ueber_der_nulllinie():
    """Der erste echte Lauf (10.08.2026) hat gezeigt, dass der Deckel die
    falsche Groesse deckelte: die Vorlage setzte `y="{{ p.ly + 3 }}"`, weil
    ein SVG-Text auf seiner Grundlinie sitzt - der Deckel rechnete aber gegen
    `ly`. Jedes gedeckelte Etikett lag damit drei Pixel unter der Achse;
    Kriterium 11 von `pruefe_portal.py` zaehlte 76 davon und fiel durch.

    Geprueft wird die Zahl, die die Vorlage wirklich schreibt."""
    viele = [_punkt(199.0 + i * 20, f"Modell {i} · 256 GB") for i in range(60)]
    k = _karte(viele, "hersteller", "Hersteller")
    achse = k["hoehe"] - k["rand_u"]
    assert k["etiketten_verborgen"] > 0, "sonst prueft der Fall nichts"
    assert all(p["label_y"] <= achse for p in k["punkte"]), \
        max(p["label_y"] for p in k["punkte"])
    # Und die Grundlinie liegt wirklich UNTER der Zeile - sonst waere der
    # Test auch dann gruen, wenn jemand den Versatz stillschweigend streicht.
    assert all(p["label_y"] > p["ly"] for p in k["punkte"])


def test_ein_punkt_ohne_etikett_zeichnet_keinen_leeren_text(tmp_path):
    """Ein leeres `<text>` ist kein leeres Element: es traegt seine Klasse und
    sein `y`, und genau daran haengen die Wahrheitstests der Positionskarte.
    Vor dem 10.08.2026 stand fuer jeden gedeckelten Punkt eines im HTML - im
    ersten echten Lauf waren das 76 Stueck, und Kriterium 11 von
    `pruefe_portal.py` fiel daran durch.

    Der Bestand des Normalfalls hat fuenf Listungen; damit deckelt nichts,
    und der Test waere gruen, ohne etwas zu pruefen. Deshalb eine volle
    Spalte: 60 Varianten desselben Geraets bei EINEM Anbieter."""
    voll = {"updated": "2026-08-11", "anbieter": {"Medimax": {"laeufe": 4}},
            "listungen": [
                _listung("Medimax", "apple-iphone-17-pro-max",
                         f"apple-iphone-17-pro-max-256gb-farbe-{i}",
                         199.0 + i * 20)
                for i in range(60)]}
    site = _baue(tmp_path, db=voll)
    s = _suppe(site, "geraete.html")
    punkte = s.select("#gr-ansicht-hersteller .gr-punkt")
    etiketten = s.select("#gr-ansicht-hersteller .gr-etikett")
    assert len(punkte) == 60
    assert etiketten and len(etiketten) < len(punkte), \
        "ohne gedeckelte Etiketten prueft der Test nichts"
    assert all(e.get_text(strip=True) for e in etiketten)
    achse = 540 - 70
    assert all(float(e.get("y")) <= achse for e in etiketten)
    # Und die Legende sagt, wie viele kein Etikett tragen - eine stille
    # Kappung waere schlimmer als eine sichtbare Luecke.
    legende = s.select_one("#gr-legende").get_text(" ", strip=True)
    assert "ohne Etikett" in legende.lower() or "Ohne Etikett" in legende


def test_etikett_bleibt_in_seiner_spaltenhaelfte():
    """Befund 2: gekürzt wurde auf die ganze Spaltenbreite, geschrieben wird
    aber ab der Spaltenmitte nach rechts - bei neun Spalten lief das Etikett
    um Faktor zwei in die Nachbarspalte."""
    punkte = [_punkt(500.0 + i, "Galaxy Z Fold 7 · 1024 GB", spalte=f"Marke {i}")
              for i in range(9)]
    k = _karte(punkte, "hersteller", "Hersteller")
    halbe = k["spalten"][0]["breite"] / 2
    for p in k["punkte"]:
        # 5,1 px je Zeichen ist die Näherung aus dem Modul.
        assert len(p["label_kurz"]) * 5.1 <= halbe, p["label_kurz"]


def test_legende_nennt_listungen_und_das_echte_abrufdatum(tmp_path):
    """Befund 3+4: die Legende schrieb „N Geräte" über eine Zahl von
    LISTUNGEN und behauptete als Abrufdatum den Berichtstag."""
    site = _baue(tmp_path)
    s = _suppe(site, "geraete.html")
    legende = s.select_one("#gr-legende").get_text(" ", strip=True)
    assert "Listungen" in legende
    kacheln = {k.find("span").get_text(strip=True): k.find("b").get_text(strip=True)
               for k in s.select(".gr-bilanz .t-kennzahl")}
    # Dieselbe Zahl unter demselben Wort - an beiden Orten.
    assert f"von {kacheln['Geräte beobachtet']} Geräten" in legende
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
    text = s.get_text(" ", strip=True)
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
