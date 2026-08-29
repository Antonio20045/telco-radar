"""Die zwei Netzbetreiber-Adapter der Ausbaustufe 2 (28.08.2026).

WARUM DIESE ZWEI ZUERST
-----------------------
Ohne Vodafone hat die Frage "wer ist guenstiger als Vodafone?" keinen
Bezugspunkt, und ohne o2 fehlte der groesste Wettbewerber. Beide lesen eine
Schnittstelle, die ihre eigene Uebersichtsseite aufruft.

JEDE FIXTURE IST EIN GESPEICHERTER ECHTER ABRUF vom 28.08.2026, auf wenige
Datensaetze gekuerzt - keine nachgebaute Struktur. Das ist die Lehre vom
11.08.2026: ein Bau-Subagent hatte damals eine Fixture ERFUNDEN (ein
`application/ld+json` auf Telekoms Produktseite, wo live null Treffer
stehen), und nur der adversarische Pruefdurchgang hat es aufgedeckt.
"""
import json
from pathlib import Path

import pytest

from telco_radar.collect.geraete import GeraeteAbrufFehler, o2, vodafone
from telco_radar.geraete_config import lade_katalog, lade_farben
from telco_radar.geraete_model import erkenne_geraet, lies_listung

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent


def _fixture(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(_WURZEL)


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


def _listung(satz, anbieter, katalog, farben, basis=""):
    return lies_listung(
        titel=satz["titel"], anbieter=anbieter, anbieter_typ="netzbetreiber",
        quelle_url=(basis + satz["url"]) or "https://example.de/p",
        abgerufen_am="2026-08-28", katalog=katalog, farben=farben,
        verfuegbarkeit=satz["verfuegbarkeit"], farbe_roh=satz["farbe"],
        speicher_gb=satz.get("speicher_gb"),
        preis_ohne_vertrag=satz["preis"])


# ==========================================================================
# Vodafone
# ==========================================================================

def test_vodafone_erntet_nur_ids_die_die_liste_selbst_nennt():
    """Die Regel "nur verlinkte Adressen, nie hochgezaehlte IDs" (§ 87b UrhG)
    gilt auch, wenn die Adressen in einer JSON-Nutzlast statt in `<a href>`
    stehen."""
    urls = vodafone.ernte(_fixture("vodafone_hardware_liste.json"),
                          "https://api.vodafone.de/glados/v2/hardware/v2?a=1")
    ids = {u.split("/virtualItem/")[1].split("?")[0] for u in urls}
    echte = {str(g["virtualItemId"]) for g in
             json.loads(_fixture("vodafone_hardware_liste.json"))["data"]["devices"]}
    assert ids == echte, "es wird genau das geerntet, was die Liste nennt"
    assert all(u.startswith("https://api.vodafone.de/") for u in urls)
    # Die Pflichtparameter muessen mit - ohne sie antwortet die
    # Schnittstelle mit HTTP 400 und nennt das fehlende Feld beim Namen.
    assert all("businessTransaction=newContract" in u
               and "salesChannel=Online.Consumer" in u for u in urls)


def test_vodafone_liest_den_preis_ohne_vertrag_je_variante(katalog, farben):
    saetze = vodafone.lies(_fixture("vodafone_virtualitem.json"))
    assert saetze, "die Detailnutzlast traegt Varianten"
    preise = sorted({s["preis"] for s in saetze})
    # Gemessen am echten Abruf: 999,90 EUR fuer 256 GB, 1129,90 fuer 512 GB.
    assert preise == [999.9, 1129.9], preise
    # Und NICHT die Buendelzahl: die Liste fuehrt dasselbe Geraet mit 1 EUR
    # Anzahlung. Genau die haelt der Lockpreis-Waechter seit dem 10.08. raus.
    assert 1.0 not in preise


def test_vodafone_baut_den_titel_aus_dem_modellnamen_nicht_aus_dem_label(katalog):
    """Der Befund beim Bauen: `label` lautet fuer eine der Varianten
    "Google Pixel Hibiscus (256 GB)" - die Farbe hat den Generationsteil
    verdraengt. Aus so einem Titel findet die Geraeteerkennung ihren
    Katalogeintrag nie wieder."""
    roh = json.loads(_fixture("vodafone_virtualitem.json"))["data"]
    labels = [a["label"] for a in roh["atomics"]]
    assert any("Pixel Hibiscus" in x for x in labels), \
        "die Fixture muss den Fall enthalten, sonst prueft der Test nichts"

    saetze = vodafone.lies(_fixture("vodafone_virtualitem.json"))
    assert all(erkenne_geraet(s["titel"], katalog) is not None for s in saetze), \
        [s["titel"] for s in saetze]
    # Gegenprobe: aus dem ROHEN label faende die Erkennung nichts.
    schlecht = [x for x in labels if "Pixel Hibiscus" in x][0]
    assert erkenne_geraet(schlecht, katalog) is None


def test_vodafone_variante_ohne_geraetepreis_wird_uebergangen():
    """Eine Zuzahlung ohne Tarifreferenz ist kein Preis - lieber keine Zeile
    als eine Buendelzahl in der Preisspalte."""
    roh = json.loads(_fixture("vodafone_virtualitem.json"))
    roh["data"]["atomics"][0]["prices"].pop("hardware")
    saetze = vodafone.lies(json.dumps(roh))
    assert len(saetze) == len(roh["data"]["atomics"]) - 1


def test_vodafone_zwei_schreibweisen_ergeben_dieselbe_id(katalog, farben):
    """Teil E, unverhandelbar: die sku_id kommt aus dem KATALOG, nie aus
    einem Titel-Hash. Sonst entstuenden jede Woche neue Geraete, die
    Listungsdauer waere immer eine Woche und der Preisverfall immer null."""
    a = {"titel": "Google Pixel 11 256 GB Frost", "preis": 999.9,
         "verfuegbarkeit": "lieferbar", "farbe": "Frost", "speicher_gb": 256,
         "url": "/privat/handys/google-pixel-11.html"}
    b = dict(a, titel="Google Pixel 11 5G 256GB, Frost")
    la = _listung(a, "Vodafone", katalog, farben, "https://www.vodafone.de")
    lb = _listung(b, "Vodafone", katalog, farben, "https://www.vodafone.de")
    assert la is not None and lb is not None
    assert la.sku_id == lb.sku_id == "google-pixel-11-256gb-frost"


def test_vodafone_quelle_zeigt_auf_die_menschenseite(katalog, farben):
    """Die Seite verspricht zu jeder Zahl einen nachpruefbaren Beleg -
    niemand prueft eine JSON-Antwort mit Schluessel nach.

    Und die Adresse muss ABSOLUT auf www.vodafone.de zeigen: die Nutzlast
    nennt den Pfad relativ, der Collector loest ihn gegen die QUELLE auf -
    also gegen api.vodafone.de. Im ersten Lauf standen deshalb 150
    Quelllinks auf "https://api.vodafone.de/privat/handys/..." in der
    Datenbank; Adressen, die es nicht gibt. Aufgefallen beim Lesen der
    exportierten Tabelle, nicht in einem Test - deshalb steht er jetzt hier.
    """
    saetze = vodafone.lies(_fixture("vodafone_virtualitem.json"))
    assert saetze
    for s in saetze:
        assert s["url"].startswith("https://www.vodafone.de/privat/handys/"), \
            s["url"]
    # Und er ueberlebt den urljoin des Collectors gegen die API-Adresse.
    from urllib.parse import urljoin
    api = ("https://api.vodafone.de/glados/v2/hardware/v2/virtualItem/287"
           "?businessTransaction=newContract")
    assert urljoin(api, saetze[0]["url"]).startswith("https://www.vodafone.de/")


def test_vodafone_kaputte_nutzlast_wirft_statt_leer_zurueckzugeben():
    """Ein gescheiterter Abruf darf nie wie "nichts gefunden" aussehen -
    sonst altert `mark_stale` den ganzen Anbieter aus dem Regal."""
    with pytest.raises(GeraeteAbrufFehler):
        vodafone.lies("<html>Wartungsseite</html>")
    with pytest.raises(GeraeteAbrufFehler):
        vodafone.ernte("kein json", "https://api.vodafone.de/x")


def test_vodafone_terabyte_wird_richtig_umgerechnet():
    roh = json.loads(_fixture("vodafone_virtualitem.json"))
    roh["data"]["atomics"][0]["capacity"]["displayLabel"] = "1 TB"
    saetze = vodafone.lies(json.dumps(roh))
    assert saetze[0]["speicher_gb"] == 1024


# ==========================================================================
# o2
# ==========================================================================

def test_o2_liest_den_geraetepreis_und_nicht_die_anzahlung(katalog, farben):
    saetze = o2.lies(_fixture("o2_katalog.json"))
    assert saetze
    roh = json.loads(_fixture("o2_katalog.json"))["hardware"]
    anzahlungen = {h["price"]["oneTimePrice"] for h in roh}
    assert anzahlungen & {1, 1.0, 7.0}, "die Fixture muss Anzahlungen enthalten"
    for s in saetze:
        assert s["preis"] > 100, f"{s['titel']}: {s['preis']} ist eine Anzahlung"
    # Der Preis ist nachrechenbar: Anzahlung plus 24 Monatsraten.
    fuer_titel = {h["description"]: h["price"] for h in roh}
    for s in saetze:
        p = next(v for k, v in fuer_titel.items() if s["titel"].startswith(k))
        assert abs(p["oneTimePrice"] + 24 * p["monthlyPrice"] - s["preis"]) < 0.01


def test_o2_verwirft_zubehoerbuendel():
    """18 der 93 Eintraege sind Geraet PLUS Zubehoer. "Apple iPhone 17 Pro Max
    mit Watch Ultra 3" kostet 2323 EUR - als Geraetepreis gespeichert waere
    das der Preis eines Telefons plus einer Smartwatch."""
    roh = json.loads(_fixture("o2_katalog.json"))["hardware"]
    buendel = [h for h in roh if " mit " in h["description"].lower()]
    assert buendel, "die Fixture muss die Falle enthalten, sonst prueft der Test nichts"

    saetze = o2.lies(_fixture("o2_katalog.json"))
    assert len(saetze) == len(roh) - len(buendel)
    for b in buendel:
        assert not any(s["titel"].startswith(b["description"]) for s in saetze)


def test_o2_liest_speicher_und_farbe_aus_dem_angebotsnamen(katalog, farben):
    saetze = o2.lies(_fixture("o2_katalog.json"))
    ein_iphone = [s for s in saetze if "iPhone 17 Pro Max" in s["titel"]][0]
    assert ein_iphone["speicher_gb"] == 256
    assert ein_iphone["farbe"] == "tiefblau"
    l = _listung(ein_iphone, "o2", katalog, farben)
    assert l is not None and l.sku_id.startswith("apple-iphone-17-pro-max-256gb")


def test_o2_zwei_schreibweisen_ergeben_dieselbe_id(katalog, farben):
    """Teil E fuer den zweiten neuen Adapter."""
    a = {"titel": "Apple iPhone 17 Pro Max 256 GB tiefblau", "preis": 1459.0,
         "verfuegbarkeit": "unbekannt", "farbe": "tiefblau",
         "speicher_gb": 256, "url": "https://www.o2online.de/e-shop/a"}
    b = dict(a, titel="Apple iPhone 17 Pro Max 5G 256GB - Tiefblau")
    la, lb = (_listung(x, "o2", katalog, farben) for x in (a, b))
    assert la is not None and lb is not None
    assert la.sku_id == lb.sku_id


def test_o2_kaputte_nutzlast_wirft_statt_leer_zurueckzugeben():
    with pytest.raises(GeraeteAbrufFehler):
        o2.lies("<html>Fehlerseite</html>")
    with pytest.raises(GeraeteAbrufFehler):
        o2.lies(json.dumps({"irgendwas": []}))


def test_o2_quelle_zeigt_auf_die_seite_ohne_tarif():
    """Die Detailadresse traegt `ohne-tarif=ja` - also genau die Preisart,
    die gespeichert wird. Der Beleg passt zur Zahl."""
    saetze = o2.lies(_fixture("o2_katalog.json"))
    assert all("o2online.de" in s["url"] for s in saetze)
    assert any("ohne-tarif=ja" in s["url"] for s in saetze)


# ==========================================================================
# Der Katalog gegen die LIVE-Namen der zwei Quellen
# ==========================================================================

@pytest.mark.parametrize("titel,erwartet", [
    # Die 800-Euro-Saegezahn-Falle vom 10.08.2026, jetzt vierfach:
    ("Google Pixel 11 Pro XL", "google-pixel-11-pro-xl"),
    ("Google Pixel 11 Pro Fold", "google-pixel-11-pro-fold"),
    ("Google Pixel 11 Pro", "google-pixel-11-pro"),
    ("Google Pixel 11", "google-pixel-11"),
    # Dieselbe Falle bei Xiaomi: "Pro Max" darf nicht auf "Pro" fallen.
    ("Xiaomi Redmi Note 17 Pro Max 5G", "xiaomi-redmi-note-17-pro-max"),
    ("Xiaomi Redmi Note 17 Pro 5G", "xiaomi-redmi-note-17-pro"),
    # und bei Samsung
    ("Samsung Galaxy Z Fold8 Ultra", "samsung-galaxy-z-fold8-ultra"),
    ("Samsung Galaxy Z Fold8", "samsung-galaxy-z-fold8"),
    # Schreibweisen, die die zwei Quellen unterschiedlich fuehren
    ("Samsung Galaxy S26+", "samsung-galaxy-s26-plus"),
    ("Samsung Galaxy A57 5G", "samsung-galaxy-a57"),
    ("Fairphone (Gen.6)", "fairphone-6"),
    ("iPhone Air", "apple-iphone-air"),
    ("Apple iPhone 17e", "apple-iphone-17e"),
])
def test_die_live_namen_treffen_den_richtigen_katalogeintrag(titel, erwartet, katalog):
    """Jeder dieser Namen stand am 28.08.2026 wirklich im Katalog von
    Vodafone oder o2. Vor der Katalogerweiterung traf KEINER von ihnen."""
    g = erkenne_geraet(titel, katalog)
    assert g is not None, f"{titel!r} trifft keinen Katalogeintrag"
    assert g.device_id == erwartet


def test_tablets_und_router_bleiben_draussen(katalog):
    """Der Katalog verfolgt Smartphones. Ein iPad in der Preiskarte wuerde
    die Preisachse strecken, ohne eine Frage zu beantworten."""
    for titel in ("iPad Pro 13 (2025)", "Vodafone GigaCube 5G",
                  "Samsung Galaxy Tab S11 Ultra",
                  "ZTE U60 Pro 5G MiFi-Router"):
        assert erkenne_geraet(titel, katalog) is None, titel


# ==========================================================================
# Kopfzeilen: die zwei Schnittstellen verlangen sie, und ohne sie
# antworten sie mit 404 statt mit Daten
# ==========================================================================

def test_pflichtkopfzeilen_erreichen_den_abruf(katalog, farben):
    """o2 antwortet auf `Accept: application/json` mit einer Weiterleitung
    in die 404-Seite, Vodafones Schnittstelle verlangt den oeffentlichen
    Browser-Schluessel. Beides steht in der Anbieterkonfiguration - und muss
    beim Abruf ankommen, sonst liefert der Adapter still nichts."""
    from datetime import datetime, timezone

    from telco_radar.collect.geraete import sammle_anbieter
    from telco_radar.collect.geraete.robots import RobotsWaechter
    from telco_radar.geraete_config import Anbieter, Einstieg

    gesehen = {}

    def hole(url, kopfzeilen=None):
        gesehen[url] = dict(kopfzeilen or {})
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /cart\n")
        return (200, _fixture("o2_katalog.json"))

    anbieter = Anbieter(
        name="o2", typ="netzbetreiber", methode="o2_katalog",
        basis_url="https://www.o2online.de", rate_limit_sekunden=0,
        kopfzeilen={"Accept": "application/vnd.commerce.message+json"},
        einstiege=[Einstieg(url="https://www.o2online.de/e-shop/rest/catalog/x",
                            kind="static")])
    bilanz = sammle_anbieter(anbieter, katalog, farben, hole, "2026-08-28",
                             RobotsWaechter(hole=hole),
                             datetime(2026, 8, 28, 3, tzinfo=timezone.utc))
    assert bilanz.status == "ok" and bilanz.listungen
    katalogabruf = gesehen["https://www.o2online.de/e-shop/rest/catalog/x"]
    assert katalogabruf["Accept"] == "application/vnd.commerce.message+json"


def test_ohne_konfigurierte_kopfzeilen_bleibt_der_alte_vertrag_gueltig(katalog, farben):
    """Jede bestehende Testattrappe ist `hole(url)` mit EINEM Parameter.
    Ein Anbieter ohne Kopfzeilen darf sie deshalb weiterhin so aufrufen -
    sonst waeren alle vorhandenen Collector-Tests kaputt."""
    from datetime import datetime, timezone

    from telco_radar.collect.geraete import sammle_anbieter
    from telco_radar.collect.geraete.robots import RobotsWaechter
    from telco_radar.geraete_config import Anbieter, Einstieg

    def hole(url):                      # EIN Parameter, wie ueberall sonst
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\n")
        return (200, _fixture("o2_katalog.json"))

    anbieter = Anbieter(
        name="o2", typ="netzbetreiber", methode="o2_katalog",
        basis_url="https://www.o2online.de", rate_limit_sekunden=0,
        einstiege=[Einstieg(url="https://www.o2online.de/e-shop/rest/catalog/x",
                            kind="static")])
    bilanz = sammle_anbieter(anbieter, katalog, farben, hole, "2026-08-28",
                             RobotsWaechter(hole=hole),
                             datetime(2026, 8, 28, 3, tzinfo=timezone.utc))
    assert bilanz.status == "ok" and bilanz.listungen


def test_der_rohsatz_zaehler_trennt_zwei_ausfaelle(katalog, farben):
    """Medimax lieferte 16 Naechte lang "20 Produktseiten, 0 Listungen", und
    das Protokoll sagte nicht, ob die Seiten nichts hergaben oder ob nichts
    davon im Katalog stand. Der Zaehler beantwortet genau das."""
    from datetime import datetime, timezone

    from telco_radar.collect.geraete import sammle_anbieter
    from telco_radar.collect.geraete.robots import RobotsWaechter
    from telco_radar.geraete_config import Anbieter, Einstieg

    # Ein Katalog, den KEINES der Geraete trifft - die Seite gibt sehr wohl
    # Preissaetze her.
    from telco_radar.geraete_model import Katalog
    leer = Katalog(geraete=[])

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\n")
        return (200, _fixture("o2_katalog.json"))

    anbieter = Anbieter(
        name="o2", typ="netzbetreiber", methode="o2_katalog",
        basis_url="https://www.o2online.de", rate_limit_sekunden=0,
        kopfzeilen={"Accept": "x"},
        einstiege=[Einstieg(url="https://www.o2online.de/e-shop/rest/catalog/x",
                            kind="static")])
    bilanz = sammle_anbieter(anbieter, leer, farben, hole, "2026-08-28",
                             RobotsWaechter(hole=hole),
                             datetime(2026, 8, 28, 3, tzinfo=timezone.utc))
    assert bilanz.listungen == [], "kein Katalogtreffer"
    assert bilanz.rohsaetze > 0, \
        "die Seite gab Preissaetze her - das unterscheidet den Ausfall"
