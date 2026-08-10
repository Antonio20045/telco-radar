"""Die drei Konfigurationsdateien des Geraeteradars.

Zwei Sorten Test: die Loader gegen konstruierte YAML in `tmp_path` (Verhalten
bei Fehlern), und die AUSGELIEFERTEN Dateien gegen ihre eigenen Zusicherungen
(Vorgaengerketten, eindeutige Erkennung, Farbtabelle ohne Widerspruch). Die
zweite Sorte ist die wichtigere: eine Katalogzeile, die zwei Geraete
ununterscheidbar macht, faellt in keinem Einheitstest auf.
"""
from pathlib import Path

import pytest
import yaml

from telco_radar.geraete_config import (
    lade_farben,
    lade_katalog,
    lade_quellen,
    METHODEN,
)
from telco_radar.geraete_model import erkenne_geraet, normalisiere_farbe

_ROOT = Path(__file__).resolve().parents[1]


def _schreibe(tmp_path: Path, name: str, daten) -> Path:
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / name).write_text(
        # sort_keys=False: die Reihenfolge der YAML ist bei der Farbtabelle
        # bedeutungstragend ("die erste gewinnt"), ein sortierender Dump
        # wuerde genau das wegsortieren.
        yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# Loader-Verhalten
# --------------------------------------------------------------------------

def test_fehlende_dateien_sind_kein_fehler(tmp_path):
    """Failsafe wie bei load_promo_config: ohne Datei tut die Stufe nichts."""
    assert lade_katalog(tmp_path).geraete == []
    assert lade_farben(tmp_path) == {}
    assert lade_quellen(tmp_path).anbieter == []


def test_katalogeintrag_ohne_modell_wird_verworfen(tmp_path):
    _schreibe(tmp_path, "geraete_katalog.yaml", {"geraete": [
        {"hersteller": "Apple", "modell": "iPhone 17"},
        {"hersteller": "Apple"},
        {"modell": "irgendwas"},
    ]})
    katalog = lade_katalog(tmp_path)
    assert [g.modell for g in katalog.geraete] == ["iPhone 17"]


def test_speicherliste_nimmt_nur_zahlen(tmp_path):
    _schreibe(tmp_path, "geraete_katalog.yaml", {"geraete": [
        {"hersteller": "Apple", "modell": "iPhone 17",
         "speicher": [128, "256", "viel"]},
    ]})
    assert lade_katalog(tmp_path).geraete[0].speicher == [128, 256]


def test_farbtabelle_kennt_ihre_eigenen_schluessel(tmp_path):
    _schreibe(tmp_path, "farben.yaml", {"farben": {"titan-natur": ["Titannatur"]}})
    tabelle = lade_farben(tmp_path)
    assert normalisiere_farbe("Titan Natur", tabelle) == "titan-natur"
    assert normalisiere_farbe("Titannatur", tabelle) == "titan-natur"


def test_widersprechende_farbschreibweise_gewinnt_nicht_zweimal(tmp_path):
    # Dieselbe Schreibweise unter zwei kanonischen Farben: die erste gewinnt,
    # und es wird gemeldet. Still ueberschreiben waere schlimmer - dann
    # haengt die Zuordnung an der Reihenfolge der YAML.
    _schreibe(tmp_path, "farben.yaml", {"farben": {
        "schwarz": ["Midnight"], "blau": ["Midnight"]}})
    tabelle = lade_farben(tmp_path)
    assert tabelle["midnight"] == "schwarz"


def test_unbekannte_methode_deaktiviert_den_anbieter(tmp_path):
    """Eine vertippte Zeile darf nicht als stumme Nulllieferung mitlaufen."""
    _schreibe(tmp_path, "geraete_quellen.yaml", {"anbieter": [
        {"name": "Testshop", "methode": "hellsehen",
         "einstiege": [{"url": "https://example.de/handys"}]},
    ]})
    a = lade_quellen(tmp_path).anbieter[0]
    assert a.aktiv is False and a.methode == "deaktiviert"
    assert "hellsehen" in a.grund


def test_doppelter_einstieg_wird_nur_einmal_abgefragt(tmp_path):
    _schreibe(tmp_path, "geraete_quellen.yaml", {"anbieter": [
        {"name": "Testshop", "einstiege": [
            {"url": "https://example.de/handys"},
            {"url": "https://example.de/handys/"},
            {"url": "https://example.de/tarife"},
        ]},
    ]})
    assert len(lade_quellen(tmp_path).anbieter[0].einstiege) == 2


def test_deaktivierter_anbieter_ist_nicht_crawlbar_behaelt_aber_seinen_grund(tmp_path):
    _schreibe(tmp_path, "geraete_quellen.yaml", {"anbieter": [
        {"name": "Amazon", "methode": "deaktiviert", "aktiv": False,
         "grund": "erfordert Product-Advertising-API-Zugang",
         "einstiege": [{"url": "https://www.amazon.de/handys"}]},
    ]})
    a = lade_quellen(tmp_path).anbieter[0]
    assert a.crawlbar is False
    assert a.grund
    # Er faellt NICHT aus der Konfiguration - sonst verschwaende er
    # stillschweigend von der Quellenseite.
    assert lade_quellen(tmp_path).anbieter


def test_seiten_zahl_zaehlt_nur_was_wirklich_abgefragt_wird(tmp_path):
    _schreibe(tmp_path, "geraete_quellen.yaml", {"anbieter": [
        {"name": "A", "einstiege": [{"url": "https://a.de/1"}, {"url": "https://a.de/2"}]},
        {"name": "B", "aktiv": False, "grund": "gesperrt",
         "einstiege": [{"url": "https://b.de/1"}]},
    ]})
    assert lade_quellen(tmp_path).seiten_zahl == 2


# --------------------------------------------------------------------------
# Die ausgelieferten Dateien
# --------------------------------------------------------------------------

def test_ausgelieferter_katalog_laedt_und_ist_eindeutig():
    """Katalog.__post_init__ wirft bei doppelter device_id UND bei zwei
    Geraeten mit derselben Wortmarkenfolge. Dass die Datei laedt, ist also
    schon die halbe Zusicherung."""
    katalog = lade_katalog(_ROOT)
    assert len(katalog.geraete) >= 30
    assert len(katalog.hersteller) >= 8


def test_jede_vorgaengerkette_zeigt_auf_ein_geraet_im_katalog():
    """Ein `vorgaenger`, den es im Katalog nicht gibt, ist ein Tippfehler,
    der sich als 'kein Nachfolger-Effekt messbar' tarnt."""
    katalog = lade_katalog(_ROOT)
    kaputt = [
        f"{g.hersteller} {g.modell} -> {g.vorgaenger}"
        for g in katalog.geraete
        if g.vorgaenger and katalog.nach_id(g.vorgaenger_device_id) is None
    ]
    assert kaputt == [], f"Vorgaenger nicht im Katalog: {kaputt}"


def test_katalog_hat_ueberhaupt_gepflegte_ketten():
    # Gegenprobe zum Test darueber: der waere auch gruen, wenn KEIN Geraet
    # einen Vorgaenger traegt.
    katalog = lade_katalog(_ROOT)
    mit_kette = [g for g in katalog.geraete if g.vorgaenger]
    assert len(mit_kette) >= 10


def test_marktstart_ist_entweder_leer_oder_ein_datum():
    import re
    katalog = lade_katalog(_ROOT)
    for g in katalog.geraete:
        assert g.marktstart == "" or re.match(r"^\d{4}-\d{2}-\d{2}$", g.marktstart), \
            f"{g.modell}: {g.marktstart!r}"


def test_katalog_erkennt_echte_haendlertitel():
    """Die eigentliche Abnahme des Katalogs: trifft er, was in einem Shop
    steht? Titel in der Schreibweise, wie deutsche Haendler sie fuehren."""
    katalog = lade_katalog(_ROOT)
    faelle = {
        "Apple iPhone 16 Pro Max 256GB Titanschwarz": "iPhone 16 Pro Max",
        "APPLE iPhone 16 128 GB Ultramarine Dual-SIM": "iPhone 16",
        "SAMSUNG Galaxy S25 Ultra 5G 512 GB Titanium Black": "Galaxy S25 Ultra",
        "Samsung Galaxy Z Fold7 512GB": "Galaxy Z Fold 7",
        "Google Pixel 9 Pro XL 256 GB Obsidian": "Pixel 9 Pro XL",
        "Xiaomi 15 Ultra 512GB Silber": "Xiaomi 15 Ultra",
        "Nothing Phone (3a) 256 GB": "Nothing Phone (3a)",
        "OnePlus 13 512GB Midnight Ocean": "OnePlus 13",
    }
    erkannt = {}
    for titel, erwartet in faelle.items():
        g = erkenne_geraet(titel, katalog)
        erkannt[titel] = g.modell if g else None
    # Ohne diese Zeile waere der Test auch dann gruen, wenn der Lookup ins
    # Leere liefe (CLAUDE.md §6).
    assert len(erkannt) == len(faelle)
    assert erkannt == faelle


def test_katalog_verwechselt_die_nothing_geraete_nicht():
    katalog = lade_katalog(_ROOT)
    assert erkenne_geraet("Nothing Phone (3a) 256 GB", katalog).modell == "Nothing Phone (3a)"
    assert erkenne_geraet("Nothing Phone (3) 512 GB", katalog).modell == "Nothing Phone (3)"


def test_ausgelieferte_farbtabelle_ist_widerspruchsfrei():
    """Jede Schreibweise darf nur EINE kanonische Farbe haben - sonst haengt
    die Zuordnung an der Reihenfolge der Datei."""
    with open(_ROOT / "config" / "farben.yaml", "r", encoding="utf-8") as fh:
        roh = yaml.safe_load(fh)["farben"]
    from telco_radar.geraete_model import normalisiere
    gesehen = {}
    doppelt = []
    for kanonisch, schreibweisen in roh.items():
        for s in [kanonisch] + list(schreibweisen or []):
            k = normalisiere(str(s))
            if k in gesehen and gesehen[k] != normalisiere(kanonisch):
                doppelt.append(f"{s} ({gesehen[k]} / {normalisiere(kanonisch)})")
            gesehen[k] = normalisiere(kanonisch)
    assert doppelt == [], f"mehrdeutige Schreibweisen: {doppelt}"


def test_ausgelieferte_farbtabelle_deckt_die_apple_titanfarben_ab():
    tabelle = lade_farben(_ROOT)
    assert normalisiere_farbe("Natural Titanium", tabelle) == "titan-natur"
    assert normalisiere_farbe("Titannatur", tabelle) == "titan-natur"
    assert normalisiere_farbe("Titan Natur", tabelle) == "titan-natur"


def test_ausgelieferte_quellen_laden_und_haben_jeden_pflichtwert():
    quellen = lade_quellen(_ROOT)
    assert quellen.anbieter, "keine Anbieter konfiguriert"
    for a in quellen.anbieter:
        assert a.methode in METHODEN
        assert a.typ in ("handel", "netzbetreiber", "discount")
        # Kein Anbieter verschwindet stillschweigend: wer nicht abgefragt
        # wird, sagt warum (Akzeptanzkriterium aus Teil E).
        if not a.crawlbar:
            assert a.grund, f"{a.name} ist nicht crawlbar, nennt aber keinen Grund"


def test_amazon_ist_konfiguriert_aber_deaktiviert():
    """Teil C3: Adapter mit klarer Schnittstelle, in der Konfiguration
    deaktiviert ausgeliefert. Kein Scraping-Versuch."""
    amazon = lade_quellen(_ROOT).nach_name("Amazon")
    assert amazon is not None
    assert amazon.crawlbar is False
    assert "api" in amazon.grund.lower()


def test_vodafone_ist_eigene_referenz_und_kein_wettbewerber():
    quellen = lade_quellen(_ROOT)
    vf = quellen.nach_name("Vodafone")
    assert vf is not None and vf.eigen is True
    assert vf not in quellen.wettbewerber


def test_discountmarken_tragen_ihr_netz():
    quellen = lade_quellen(_ROOT)
    discount = [a for a in quellen.anbieter if a.typ == "discount"]
    assert len(discount) >= 8
    ohne_netz = [a.name for a in discount if not a.netz]
    assert ohne_netz == [], f"Discountmarke ohne Netzzuordnung: {ohne_netz}"


def test_die_drei_grossen_netzbetreiber_sind_erfasst():
    quellen = lade_quellen(_ROOT)
    namen = {a.name for a in quellen.anbieter if a.typ == "netzbetreiber"}
    for pflicht in ("Telekom", "o2", "1&1", "Vodafone"):
        assert any(pflicht.lower() in n.lower() for n in namen), pflicht


@pytest.mark.parametrize("stufe", ["handel", "netzbetreiber", "discount"])
def test_alle_drei_beobachtungsebenen_sind_besetzt(stufe):
    quellen = lade_quellen(_ROOT)
    assert [a for a in quellen.anbieter if a.typ == stufe]
