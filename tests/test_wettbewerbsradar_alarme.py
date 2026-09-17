"""O2 (STRATEGIE_GERAETE_OPTIK §3, 11.09.2026): die Alarmtabelle wandert
von der Vergleichsansicht der Geräteseite auf den Wettbewerbs-Radar.

E3 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1d, 17.09.2026) korrigiert den Ort des
Sortiments-Aufklappers "Bei Wettbewerbern gelistet, bei Vodafone nicht":
Er steht jetzt IM GERÄTEKATALOG-REITER der Geräteseite - im Vier-Reiter-
Gerüst der EINEN Seite ist der Katalog der Sortiments-Reiter, und "nur bei
Wettbewerbern im Regal" ist die Komplementäraussage zu dessen Tabelle
(S1/S3), keine Radar-Frage. Auf der Schwesterseite bleibt er weg: umgezogen,
nicht kopiert (§4.6). Die Alarmtabelle bleibt Radar-Inhalt (E3 Schritt 2
montiert sie in den Radar-Reiter derselben Seite).

Gemessen wird am gerenderten Paar (beide Seiten derselben Site), damit der
Test auch den Umzug selbst hält: weg von der einen, da auf der anderen.
Die Fixture baut dieselbe Datenlage wie `test_wettbewerbsradar._seite`,
plus einem Gerät, das NUR der Wettbewerb führt (für den
Sortiments-Aufklapper).
"""
from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view, geraete_radar as wr
from telco_radar.report.html import render_site

WURZEL = pathlib.Path(__file__).resolve().parents[1]
HEUTE = "2026-09-11"

SKU_M1 = "apple-iphone-15-128gb-schwarz"    # Saturn guenstiger als Vodafone
SKU_M2 = "apple-iphone-15-256gb-schwarz"    # nur Saturn - kein Vodafone

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 15", "generation": 15,
     "marktstart": "2023-09-22", "speicher": [128, 256], "segment": "premium"},
]}
_FARBEN = {"farben": {"schwarz": ["Schwarz", "Black"]}}
_QUELLEN = {"anbieter": [
    {"name": "o2", "typ": "netzbetreiber", "rang": 1,
     "methode": "json_endpunkt", "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/e-shop/",
                    "label": "Katalog", "kind": "static"}]},
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 2, "eigen": True,
     "methode": "json_endpunkt", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://api.vodafone.de/glados/v2/hardware",
                    "label": "Liste", "kind": "static"}]},
    {"name": "Saturn", "typ": "handel", "gruppe": "Ceconomy", "rang": 2,
     "methode": "saturn_brand", "aktiv": True,
     "basis_url": "https://www.saturn.de",
     "einstiege": [{"url": "https://www.saturn.de/handys",
                    "label": "Handys", "kind": "static"}]},
]}


def _listung(anbieter, sku, preis):
    speicher = int(sku.split("-")[-2].replace("gb", ""))
    return {"id": f"{anbieter.lower()}--{sku}", "sku_id": sku,
            "device_id": "-".join(sku.split("-")[:-2]),
            "anbieter": anbieter,
            "anbieter_typ": ("handel" if anbieter == "Saturn"
                             else "netzbetreiber"),
            "speicher_gb": speicher, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-08-20", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-20",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{sku}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/l"]}


def _seite(tmp_path: pathlib.Path) -> dict[str, str]:
    root = tmp_path / "site-bau"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    listungen = [
        _listung("Vodafone", SKU_M1, 709.90),
        _listung("Saturn", SKU_M1, 679.90),
        # NUR der Wettbewerb - Vodafone führt dieses Gerät nicht: der Fall
        # des Sortiments-Aufklappers.
        _listung("Saturn", SKU_M2, 829.00),
    ]
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE, "anbieter": {
            n: {"laeufe": 4, "funde_gesamt": 1}
            for n in ("Vodafone", "Saturn")},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text(
        "".join(json.dumps({"listung_id": e["id"], "datum": HEUTE,
                            "preis_ohne_vertrag": e["preis_ohne_vertrag"],
                            "quelle_url": e["quelle_url"]}) + "\n"
                for e in listungen), encoding="utf-8")
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": [], "sim_only": []}),
        encoding="utf-8")
    (state / "tarife.jsonl").write_text("", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return {name: (site / name).read_text(encoding="utf-8")
            for name in ("wettbewerbsradar.html", "geraete.html")}


def _suppe(seiten: dict, name: str) -> BeautifulSoup:
    return BeautifulSoup(seiten[name], "html.parser")


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


# --------------------------------------------------------------------------
# Die Alarmtabelle auf dem Radar
# --------------------------------------------------------------------------

def test_die_alarmtabelle_steht_als_eigener_abschnitt_auf_dem_radar(tmp_path):
    """E3 Schritt 3 (17.09.2026): die Alt-URL ist eine Weiterleitung -
    „auf dem Radar" heißt seitdem: im Radar-REITER von geraete.html
    (erster Abschnitt der Tafel, S3)."""
    seiten = _seite(tmp_path)
    geraete = _suppe(seiten, "geraete.html")
    abschnitt = geraete.select_one("#tafel-radar #wr-alarme")
    assert abschnitt is not None, "der Abschnitt fehlt im Radar-Reiter"
    assert abschnitt.select_one("h3") is not None
    zeilen = abschnitt.select(".gr-a-zeile")
    assert zeilen, "keine Alarmzeile im Radar-Reiter"
    # Der Inhalt ist der GANZE (kein Funktionsverlust): Filter, Suche,
    # Sortierung, Zeilenaufklapper und die vier Kacheln stehen mit da.
    assert abschnitt.select_one(".gr-chips") is not None
    assert abschnitt.select_one("[data-filter='marke']") is not None
    assert abschnitt.select_one("[data-filter='suche']") is not None
    assert abschnitt.select(".gr-sort"), "keine sortierbare Spalte"
    for z in zeilen:
        auf = geraete.select_one("#" + z["data-auf"])
        assert auf is not None, "Zeile ohne Aufklapper"


def test_die_alarmzeile_nennt_den_guenstigsten_mit_namen(tmp_path):
    """Die Anforderung der Tabelle selbst - nicht DASS jemand guenstiger
    ist, sondern BEI WEM - gilt am neuen Ort unveraendert."""
    seiten = _seite(tmp_path)
    geraete = _suppe(seiten, "geraete.html")
    text = _text(geraete.select_one("#tafel-radar #wr-alarme"))
    assert "Saturn" in text
    assert "679,90" in text
    assert "709,90" in text
    assert "4,2" in text, "der Prozentsatz (709,90 → 679,90 = −4,2 %)"


def test_jede_alarmzeile_traegt_quelle_und_abrufdatum(tmp_path):
    """Belegzwang am neuen Ort. Der Lookup läuft gegen den Radar-Reiter
    und ZAEHLT die Zeilen vorher - auf der Weiterleitungs-Alt-URL wäre die
    Schleife leer und der Test grün, ohne etwas zu prüfen (CLAUDE.md §6)."""
    seiten = _seite(tmp_path)
    geraete = _suppe(seiten, "geraete.html")
    zeilen = geraete.select("#tafel-radar #wr-alarme .gr-a-zeile")
    assert zeilen, "keine Alarmzeile im Radar-Reiter - Test prüft nichts"
    for zeile in zeilen:
        assert zeile.select_one("a.gr-a-quelle[href]"), \
            "Wettbewerber ohne Quelllink"
        assert zeile.select_one(".gr-a-datum"), "Zeile ohne Abrufdatum"


def test_die_geraeteseite_traegt_keine_alarmtabelle_mehr(tmp_path):
    """Der Umzug, nicht die Kopie. Bis O2 (11.09.2026) hieß das: auf
    geraete.html bleibt NICHTS von der Tabelle. Seit E3 Schritt 2 (S3)
    steht sie als erste Sektion IM RADAR-REITER derselben Seite - der Test
    hält jetzt den E3-Zustand: GENAU EINMAL (#tafel-radar), nicht in der
    Vergleichsansicht, nicht im Katalog. (`.gr-a-zeile` ist auf der Seite
    mehrdeutig - Katalog- UND Radar-Zeilen tragen sie: geprüft wird je
    TAFEL, nie die Klasse allein.)"""
    seiten = _seite(tmp_path)
    geraete = _suppe(seiten, "geraete.html")
    assert len(geraete.select("#wr-alarme")) == 1, \
        "die Alarm-Sektion steht nicht genau einmal auf der Seite"
    radar = geraete.select_one("#tafel-radar")
    assert radar is not None and radar.select_one("#wr-alarme") is not None, \
        "die Alarm-Sektion steht nicht im Radar-Reiter"
    for marker in ("#gr-alarme",):
        assert geraete.select_one(marker) is None, marker
    tafel = geraete.select_one("#tafel-tco")
    assert tafel is not None
    assert tafel.select_one(".gr-a-zeile") is None, \
        "Alarmzeilen stehen noch in der Vergleichsansicht"
    katalog = geraete.select_one("#tafel-katalog")
    assert katalog is not None and katalog.select_one("#wr-alarme") is None, \
        "die Alarm-Sektion steht im Katalog-Reiter"


# --------------------------------------------------------------------------
# "Bei Wettbewerbern gelistet" - E3: im Gerätekatalog-Reiter der EINEN Seite
# --------------------------------------------------------------------------

def test_bei_wettbewerbern_gelistet_steht_im_geraetekatalog(tmp_path):
    """E3 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1d): EINE Seite, vier Reiter -
    der Sortiments-Aufklapper steht im KATALOG-Reiter („nur bei
    Wettbewerbern im Regal" ist die Komplementäraussage zu dessen
    Tabelle) und nicht mehr auf der Schwesterseite: umgezogen, nicht
    kopiert (§4.6)."""
    seiten = _seite(tmp_path)
    geraete = _suppe(seiten, "geraete.html")
    abschnitt = geraete.select_one("#gr-sortiment")
    assert abschnitt is not None, "der Sortiments-Aufklapper fehlt"
    assert geraete.select_one("#tafel-katalog #gr-sortiment") is not None, (
        "der Aufklapper steht außerhalb des Katalog-Reiters")
    text = _text(abschnitt)
    assert "Bei Wettbewerbern gelistet, bei Vodafone nicht" in text
    assert "iPhone 15" in text, "das nur-wettbewerbliche Gerät fehlt"
    assert "829,00" in text, "ohne ab-Preis ist die Zeile keine Aussage"
    link = abschnitt.select_one("a[href]")
    assert link, "ohne Beleglink"
    assert "↗" in link.get_text(), "Beleglink ohne ↗ (E3/S4 Beleg-Stil)"


def test_der_aufklapper_steht_nicht_zweite_mal_auf_dem_radar(tmp_path):
    """E3: dieselbe Aussage an zwei Orten wäre die Doppel-Darstellung aus
    §4.6. Bis E3 Schritt 3 prüfte das die Schwesterseite; seit sie eine
    Weiterleitung ist, ist der Dopplungsschutz am NEUEN Ort: der Aufklapper
    steht GENAU EINMAL auf der EINEN Geräteseite - im Katalog-Reiter, und
    nicht zusätzlich im Radar-Reiter."""
    seiten = _seite(tmp_path)
    geraete = _suppe(seiten, "geraete.html")
    assert len(geraete.select("#gr-sortiment")) == 1, \
        "der Sortiments-Aufklapper steht nicht genau einmal auf der Seite"
    assert geraete.select_one("#tafel-radar #gr-sortiment") is None, \
        "der Aufklapper steht zusätzlich im Radar-Reiter (Doppel-Darstellung)"
    # Die Alt-URL ist Weiterleitung und trägt keine Tafel-Inhalte mehr.
    alt = _suppe(seiten, "wettbewerbsradar.html")
    assert alt.select_one("#gr-sortiment") is None
    assert alt.select_one(".wr-sektion") is None


# --------------------------------------------------------------------------
# Am echten Bestand: Vollständigkeit des Umzugs (keine Tageszählung - die
# Zeilenzahl der Seite wird gegen die Aufbereitung gehalten, nicht auf eine
# Zahl festgenagelt, die jede Nacht wächst). View-Ebene wie der `echt`-
# Fixture der Nachbardatei: die gerenderte Form deckt die Fixture oben ab.
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def echt():
    state = WURZEL / "data" / "state"
    if not (state / "geraete_db.json").exists():
        pytest.skip("kein Gerätebestand im Checkout")
    view = geraete_view.aufbereiten(state, lade_quellen(WURZEL),
                                    lade_katalog(WURZEL), heute="")
    radar = wr.radar(view["tco"], view["vergleich"]["ohne_vertrag"],
                     view["quellenlage"], alarme=view["alarme"])
    return {"view": view, "radar": radar}


def test_am_echten_bestand_traegt_der_radar_alle_alarmzeilen(echt):
    """Der Deckel (`SICHTBAR_MAX`) kappt nur die ANSICHT - die View führt
    die volle Liste. Ein Umzug, der nur die sichtbaren Zeilen nimmt,
    verlöre den Rest still."""
    alarme = echt["view"]["alarme"]
    if not alarme["gesamt"]:
        pytest.skip("Bestand ohne Alarmzeile")
    ueber = echt["radar"]["alarme"]
    assert ueber["gesamt"] == alarme["gesamt"]
    assert len(ueber["sichtbar"]) + len(ueber["rest"]) == alarme["gesamt"]


def test_am_echten_bestand_traegt_der_radar_die_sortimentsluecke(echt):
    ohne = echt["view"]["vergleich"]["ohne_vertrag"]
    if not ohne["ohne_vodafone_gesamt"]:
        pytest.skip("Bestand ohne Sortimentslücke")
    assert echt["radar"]["ohne_vodafone_gesamt"] == \
        ohne["ohne_vodafone_gesamt"]
    assert len(echt["radar"]["ohne_vodafone"]) == \
        len(ohne["ohne_vodafone"])
