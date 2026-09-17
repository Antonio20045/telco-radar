"""Der Katalog auf MODELL-Ebene (P3, Strategie Geraete v3, 17.09.2026).

`geraete_view.katalog_modellzeilen()` ist die Datenquelle fuer EINE Tabelle
mit Umschalter Einzelgeraepreis/TCO. DIE EINE REGEL des Auftrags steht hier
als Test: KEINE Modellzeile sagt "ohne Preis" - jede traegt einen
Barpreis-Beleg oder den benannten Bündel-Zustand, nie eine Rate als
Barpreis (Hausregel: zwei Preisarten nie mischen; B1: Zustand im Schluessel).

Der Export der beiden Ansichten (`geraete_export`) steht in derselben
Datei, weil er dieselben Zeilen liest - eine Preisform je Zeile, in ihrer
eigenen Spalte.
"""
from pathlib import Path

from telco_radar.geraete_model import Geraet, Katalog, device_id
from telco_radar.report import geraete_export as ex
from telco_radar.report import geraete_view
from telco_radar.report.geraete_tco_karten import modell_schluessel


def _katalog():
    return Katalog(geraete=[
        Geraet(hersteller="Apple", modell="Apple X", generation=1,
               segment="flagship"),
        Geraet(hersteller="Samsung", modell="Galaxy S26 Ultra",
               generation=26, segment="flagship"),
        Geraet(hersteller="Google", modell="Pixel 11", generation=11,
               segment="flagship"),
    ])


def _listung(anbieter, hersteller, modell, sku_suffix, preis,
             zustand="neu", speicher=256, **kw):
    did = device_id(hersteller, modell)
    e = {
        "id": f"{anbieter.lower()}--{did}", "sku_id": f"{did}-{sku_suffix}",
        "device_id": did, "anbieter": anbieter, "anbieter_typ": "handel",
        "speicher_gb": speicher, "farbe_roh": "Schwarz",
        "farbe_normalisiert": "schwarz", "zustand": zustand,
        "status": "aktiv", "missed_checks": 0,
        "preis_ohne_vertrag": preis, "zuzahlung": None,
        "quelle_url": f"https://example.de/{anbieter}/{sku_suffix}",
        "abgerufen_am": "2026-09-17", "verfuegbarkeit": "lieferbar",
    }
    e.update(kw)
    return e


def _buendel(anbieter, hersteller, modell, sku_suffix, monat,
             speicher=256, **kw):
    did = device_id(hersteller, modell)
    b = {
        "sku_id": f"{did}-{sku_suffix}", "anbieter": anbieter,
        "tarif_name": "M", "tarif_id": "anbieter:m",
        "buendel_monatlich": monat, "tarif_monatlich": None,
        "geraet_monatsrate": None, "geraet_zuzahlung": None,
        "zustand": "neu", "laufzeit_monate": 24,
        "quelle_url": f"https://example.de/{anbieter}/buendel",
        "abgerufen_am": "2026-09-17",
    }
    b.update(kw)
    return b


def _tco_modell(mid, karten):
    return {"id": mid, "titel": mid, "karten": karten}


def _karte(anbieter, gesamt, monat=41.0, zustand="neu", vergleichbar=True,
           belastbar=True, delta=None, delta_kurz=None, band="klein"):
    return {"anbieter": anbieter, "gesamt": gesamt, "schnitt_monat": monat,
            "zustand": zustand, "vergleichbar": vergleichbar,
            "belastbar": belastbar, "naeherung": False, "delta": delta,
            "delta_kurz": delta_kurz, "band": band,
            "quelle_url": f"https://example.de/{anbieter}", "sku_id": "s",
            "abgerufen_am": "2026-09-17"}


# ---------------------------------------------------------------------------
# DIE EINE REGEL: keine Modellzeile ohne Preisform
# ---------------------------------------------------------------------------

def test_eine_zeile_je_modell_mit_ab_preis_und_beleg():
    """Fuenf Listungen zweier Farben und zweier Anbieter EINES Modells
    werden EINE Modellzeile - mit dem Minimum ueber die je-Anbieter-Minima
    und dessen Beleg (Betrag, Link, Datum)."""
    eintraege = [
        _listung("A", "Apple", "Apple X", "256gb-schwarz", 1000.0),
        _listung("A", "Apple", "Apple X", "256gb-blau", 1020.0,
                 farbe_normalisiert="blau", farbe_roh="Blau"),
        _listung("B", "Apple", "Apple X", "256gb-schwarz-b", 990.0),
        _listung("B", "Apple", "Apple X", "256gb-blau-b", 1010.0,
                 farbe_normalisiert="blau", farbe_roh="Blau"),
        # Ein ANDERES Modell (anderer Speicher) ist eine zweite Zeile.
        _listung("A", "Apple", "Apple X", "512gb-schwarz", 1200.0,
                 speicher=512),
    ]
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog())
    assert len(zeilen) == 2, "je (Geraet, Speicher) eine Modellzeile"
    zeile = next(z for z in zeilen if z["speicher"] == 256)
    # Je Anbieter das Minimum (A: 1000, B: 990), dann das Gesamt-Minimum.
    assert zeile["ab_preis"] == 990.0
    assert zeile["ab_anbieter"] == "B"
    assert zeile["ab_beleg"]["quelle_url"].endswith("/B/256gb-schwarz-b")
    assert zeile["ab_beleg"]["abgerufen_am"] == "2026-09-17"
    assert zeile["anbieterzahl"] == 2
    # Der Aufklapper traegt ALLE fuenf... vier Listungen des Modells.
    assert zeile["listungen"] == 4
    assert len(zeile["zeilen"]) == 4


def test_refurbished_stellt_keinen_ab_preis_b1():
    """Hausregel B1: der Zustand ist im Aggregations-Schluessel verankert -
    ein refurbished Preis kann den ab-Preis eines Modells nie stellen,
    auch nicht ueber einen anderen Anbieter."""
    eintraege = [
        _listung("A", "Apple", "Apple X", "256gb-schwarz", 850.0),
        _listung("B", "Apple", "Apple X", "256gb-erneuert-b", 500.0,
                 zustand="refurbished"),
    ]
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog())
    (zeile,) = zeilen
    assert zeile["ab_preis"] == 850.0, (
        "der refurbished Preis darf den ab-Preis nicht stellen: "
        f"{zeile['ab_preis']}")
    assert zeile["ab_anbieter"] == "A"
    # Die erneuerte Zeile bleibt im Aufklapper, mit Etikett.
    erneuert = [z for z in zeile["zeilen"] if z["zustand"] == "refurbished"]
    assert len(erneuert) == 1


def test_nur_im_buendel_statt_ohne_preis():
    """DIE EINE REGEL: eine Modellzeile ohne jeden Barpreis traegt den
    benannten Bündel-Zustand aus dem TCO-Store - mit Beleg, nie als Rate
    im Barpreis-Feld."""
    eintraege = [_listung("1&1", "Apple", "Apple X", "256gb-schwarz", None,
                          tarif_referenz="M")]
    buendel = [_buendel("1&1", "Apple", "Apple X", "256gb-andere-farbe",
                        32.99)]
    zeilen = geraete_view.katalog_modellzeilen(
        eintraege, _katalog(), tco_modelle=[], buendel=buendel)
    (zeile,) = zeilen
    assert zeile["ab_preis"] is None, "eine Monatsrate ist kein Barpreis"
    assert zeile["nur_buendel"] is True
    assert zeile["buendel_monat"] == 32.99
    assert zeile["buendel_anbieter"] == "1&1"
    assert zeile["buendel_beleg"]["quelle_url"].endswith("/buendel")
    # Die Listungs-Zeile im Aufklapper traegt dieselbe Angabe - "ohne
    # Preis" existiert auf dieser Ebene nicht mehr.
    (aufklapp,) = zeile["zeilen"]
    assert aufklapp["preis"] is None
    assert aufklapp["buendel_monat"] == 32.99


def test_keine_zeile_ohne_preisform_wenn_buendel_fehlt():
    """Der benannte Leerzustand bleibt, wenn nicht mal ein Bündel da ist -
    aber er ist KEIN 'ohne Preis': das Feld heisst `nur_buendel=False`,
    und die Regel wird vom Aufrufer benannt, nicht vom Datenfeld."""
    eintraege = [_listung("1&1", "Apple", "Apple X", "256gb-schwarz", None,
                          tarif_referenz="M")]
    zeilen = geraete_view.katalog_modellzeilen(
        eintraege, _katalog(), tco_modelle=[], buendel=[])
    (zeile,) = zeilen
    assert zeile["ab_preis"] is None
    assert zeile["buendel_monat"] is None
    assert zeile["nur_buendel"] is False


def test_buendel_monatspreis_nur_vom_selben_anbieter():
    """Eine Zeile ohne Preis holt ihre Bündel-Angabe beim SELBEN Anbieter -
    ein fremdes Bündel desselben Modells ist ein anderes Angebot."""
    eintraege = [
        _listung("1&1", "Apple", "Apple X", "256gb-schwarz", None,
                 tarif_referenz="M"),
        _listung("B", "Apple", "Apple X", "256gb-schwarz-b", 900.0),
    ]
    buendel = [_buendel("B", "Apple", "Apple X", "256gb-x", 20.0)]
    zeilen = geraete_view.katalog_modellzeilen(
        eintraege, _katalog(), tco_modelle=[], buendel=buendel)
    (zeile,) = zeilen
    assert zeile["ab_preis"] == 900.0, "B hat einen Barpreis"
    ohne = [z for z in zeile["zeilen"] if z["preis"] is None]
    assert ohne and ohne[0].get("buendel_monat") is None, (
        "das Bündel des Fremdanbieters darf der 1&1-Zeile nicht ihren "
        "Monatspreis stellen")


def test_buendel_monat_ohne_eigenes_feld_summiert_tarif_und_rate():
    """Fehlt `buendel_monatlich` (so verkauft 1&1 nicht), ist die Summe aus
    Tarif- und Geraeterate die Monatsangabe - zwei Felder, die der
    Anbieter selbst nebeneinander nennt, keine Rechnung dieses Projekts."""
    eintraege = [_listung("o2", "Apple", "Apple X", "256gb-schwarz", None,
                          tarif_referenz="M")]
    buendel = [_buendel("o2", "Apple", "Apple X", "256gb-x", None,
                        tarif_monatlich=19.99, geraet_monatsrate=10.01)]
    zeilen = geraete_view.katalog_modellzeilen(
        eintraege, _katalog(), tco_modelle=[], buendel=buendel)
    assert zeilen[0]["buendel_monat"] == 30.0


def test_unlesbarer_store_fraegt_die_listungen_ab_s2_1():
    """S2-1 der P3-Code-Pruefung: `TcoDB.buendel()` liefert bei unlesbarem
    Store still [] - der Katalog darf dafuer nicht auf "ohne Preis"
    zurueckfallen (Fehlerklasse B6). `_buendel_aus_listungen` baut die
    Bündel-Saetze aus dem, was die Listung selbst traegt: Monatspreis,
    Tarif, Beleg - dieselben Felder, die der Store auch haette. Der Test
    ruft die Funktion so, wie `aufbereiten()` es im Fehlerfall tut."""
    eintraege = [_listung("1&1", "Apple", "Apple X", "256gb-schwarz", None,
                          tarif_referenz="1&1 All-Net S",
                          preis_mit_vertrag_ab=32.99),
                 # Mit Barpreis: braucht keinen Fallback und liefert keinen
                 # Satz (eine Listung MIT Preis ist kein Bündel-Hinweis).
                 _listung("A", "Apple", "Apple X", "256gb-a", 999.0)]
    saetze = geraete_view._buendel_aus_listungen(eintraege)
    assert saetze == [{
        "sku_id": eintraege[0]["sku_id"], "anbieter": "1&1",
        "buendel_monatlich": 32.99, "tarif_name": "1&1 All-Net S",
        "quelle_url": eintraege[0]["quelle_url"],
        "abgerufen_am": "2026-09-17"}]
    # Und durch die Modellzeile gerechnet: "nur im Bündel" statt "ohne
    # Preis", mit dem Beleg DER LISTUNG.
    zeilen = geraete_view.katalog_modellzeilen(
        eintraege, _katalog(), tco_modelle=[], buendel=saetze)
    apple = next(z for z in zeilen if z["speicher"] == 256)
    assert apple["ab_preis"] == 999.0, "A hat einen Barpreis"
    ohne = [r for r in apple["zeilen"] if r["anbieter"] == "1&1"]
    assert ohne and ohne[0]["buendel_monat"] == 32.99, (
        "die 1&1-Aufklapperzeile fällt ohne Store auf 'ohne Preis' zurück")
    assert ohne[0]["buendel_url"] == eintraege[0]["quelle_url"]


# ---------------------------------------------------------------------------
# Spanne und Ordnung
# ---------------------------------------------------------------------------

def test_spanne_nur_wenn_wesentlich():
    eintraege = [
        _listung("A", "Apple", "Apple X", "256gb-a", 1000.0),
        _listung("B", "Apple", "Apple X", "256gb-b", 1005.0),
    ]
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog())
    assert zeilen[0]["spanne"] == [], (
        "5 EUR bei 1000 sind weder 3 % noch 15 EUR - keine Spanne")
    eintraege[1]["preis_ohne_vertrag"] = 1100.0
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog())
    assert zeilen[0]["spanne"] == [1000.0, 1100.0]


def test_modellzeilen_teilen_den_schluessel_mit_der_tco_ansicht():
    eintraege = [_listung("A", "Apple", "Apple X", "256gb-a", 1000.0)]
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog())
    assert zeilen[0]["schluessel"] == modell_schluessel("apple-x", 256)


def test_deckel_zaehlt_modelle_nicht_listungen():
    """`KATALOG_SICHTBAR` zaehlt auf der Modellebene MODELLE - 3 Modelle
    mit je 3 Listungen bleiben 3 sichtbare Zeilen, nicht 9."""
    eintraege = []
    for hersteller, modell in (("Apple", "Apple X"),
                               ("Samsung", "Galaxy S26 Ultra"),
                               ("Google", "Pixel 11")):
        for farbe in ("a", "b", "c"):
            eintraege.append(_listung("A", hersteller, modell,
                                      f"256gb-{farbe}", 100.0 + hash(farbe) % 7))
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog())
    assert len(zeilen) == 3
    assert sum(1 for z in zeilen if not z["zeilen_rest"]) == 3


# ---------------------------------------------------------------------------
# Die TCO-Ansicht
# ---------------------------------------------------------------------------

def test_tco_felder_waehlen_das_beste_vergleichbare_angebot():
    mid = modell_schluessel(device_id("Apple", "Apple X"), 256)
    tco = [_tco_modell(mid, karten=[
        _karte("o2", 1100.0),
        _karte("congstar", 1000.0, monat=41.67,
               delta={"betrag": -100.0, "prozent": 9.1},
               delta_kurz="−100,00 € · −9,1 %"),
        # Billiger, aber ERNEUERT - darf nicht gewinnen (B1).
        _karte("o2", 900.0, zustand="refurbished", vergleichbar=False),
    ])]
    eintraege = [_listung("A", "Apple", "Apple X", "256gb-a", 1000.0)]
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog(),
                                               tco_modelle=tco)
    (zeile,) = zeilen
    assert zeile["tco_ab"] == 1000.0
    assert zeile["tco_anbieter"] == "congstar"
    assert zeile["tco_monat"] == 41.67
    assert zeile["tco_delta_kurz"] == "−100,00 € · −9,1 %"
    assert zeile["tco_delta"] == -100.0
    assert zeile["tco_band"] == "klein"
    assert zeile["tco_leer"] is None


def test_tco_delta_nur_mit_referenz():
    """`delta_kurz` existiert nur mit Vodafone-Referenz - ohne Referenz
    bleiben Betrag und Prozent leer, es wird keine Naeherung gerechnet."""
    mid = modell_schluessel(device_id("Apple", "Apple X"), 256)
    tco = [_tco_modell(mid, karten=[_karte("o2", 1000.0, delta=None,
                                           delta_kurz=None)])]
    eintraege = [_listung("A", "Apple", "Apple X", "256gb-a", 1000.0)]
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog(),
                                               tco_modelle=tco)
    assert zeilen[0]["tco_delta"] is None
    assert zeilen[0]["tco_delta_kurz"] is None
    assert zeilen[0]["tco_ab"] == 1000.0


def test_tco_leerzustaende_benannt():
    eintraege = [
        _listung("A", "Apple", "Apple X", "256gb-a", 1000.0),
        _listung("A", "Samsung", "Galaxy S26 Ultra", "256gb-s", 1100.0),
        _listung("A", "Google", "Pixel 11", "256gb-p", 1200.0),
    ]
    apple_id = modell_schluessel(device_id("Apple", "Apple X"), 256)
    pixel_id = modell_schluessel(device_id("Google", "Pixel 11"), 256)
    # Apple: Bündel da, aber KEINE vergleichbare Karte (nur erneuert).
    # Pixel: gar kein Bündel. Samsung: gesund.
    tco = [
        _tco_modell(apple_id, karten=[_karte("o2", 900.0, zustand="refurbished",
                                             vergleichbar=False)]),
        _tco_modell(modell_schluessel(device_id("Samsung", "Galaxy S26 Ultra"),
                                      256),
                    karten=[_karte("o2", 1100.0)]),
    ]
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog(),
                                               tco_modelle=tco)
    je_id = {z["schluessel"]: z for z in zeilen}
    assert len(je_id) == len(zeilen), "jede Modellzeile genau einmal"
    assert je_id[apple_id]["tco_leer"] == "kein vergleichbares Bündel gemessen"
    assert je_id[pixel_id]["tco_leer"] == "kein Bündel gemessen"
    assert je_id[modell_schluessel(
        device_id("Samsung", "Galaxy S26 Ultra"), 256)]["tco_leer"] is None


def test_ohne_tco_aufbereitung_bleibt_der_katalog_lesbar():
    """Kein TCO-Dict (kaputter Store) darf den Katalog kosten - die Felder
    stehen auf ihrem benannten Leerzustand."""
    eintraege = [_listung("A", "Apple", "Apple X", "256gb-a", 1000.0)]
    zeilen = geraete_view.katalog_modellzeilen(eintraege, _katalog())
    assert zeilen[0]["ab_preis"] == 1000.0
    assert zeilen[0]["tco_leer"] == "kein Bündel gemessen"


# ---------------------------------------------------------------------------
# Der Ansichts-Export
# ---------------------------------------------------------------------------

def _beispiel_zeilen():
    mid_apple = modell_schluessel(device_id("Apple", "Apple X"), 256)
    tco = [_tco_modell(mid_apple, karten=[
        _karte("congstar", 1000.0, delta={"betrag": -100.0, "prozent": 9.1},
               delta_kurz="−100,00 € · −9,1 %")])]
    eintraege = [
        _listung("A", "Apple", "Apple X", "256gb-a", 1000.0),
        _listung("1&1", "Google", "Pixel 11", "256gb-p", None,
                 tarif_referenz="M"),
    ]
    buendel = [_buendel("1&1", "Google", "Pixel 11", "256gb-x", 32.99)]
    return geraete_view.katalog_modellzeilen(eintraege, _katalog(),
                                             tco_modelle=tco,
                                             buendel=buendel)


def test_modell_barpreis_csv_eine_preisform_je_zeile(tmp_path):
    modelle = _beispiel_zeilen()
    inhalt, zahl = ex.modell_barpreis_csv(modelle)
    assert zahl == 2
    roh = inhalt.encode(ex.KODIERUNG)
    assert roh[:3] == b"\xef\xbb\xbf", "BOM fuer Excel"
    zeilen = [z.split(";") for z in inhalt.split("\r\n") if z]
    kopf = zeilen[0]
    assert kopf == ex.SPALTEN_MODELL_BARPREIS
    von_ab = {z[kopf.index("Ab-Preis EUR")] for z in zeilen[1:]}
    assert "1000,00" in von_ab, "Dezimalkomma, kein Punkt"
    apple = next(z for z in zeilen[1:] if z[1] == "Apple X")
    pixel = next(z for z in zeilen[1:] if z[1] == "Pixel 11")
    assert apple[kopf.index("Nur im Bündel ab EUR/Monat")] == ""
    assert pixel[kopf.index("Nur im Bündel ab EUR/Monat")] == "32,99"
    assert pixel[kopf.index("Ab-Preis EUR")] == ""
    assert pixel[kopf.index("Bündel-Anbieter")] == "1&1"
    # Niemals beide Preisformen in EINER Zeile.
    for z in zeilen[1:]:
        assert not (z[kopf.index("Ab-Preis EUR")]
                    and z[kopf.index("Nur im Bündel ab EUR/Monat")])


def test_modell_tco_csv_traegt_den_grund_statt_einer_luecke(tmp_path):
    modelle = _beispiel_zeilen()
    inhalt, zahl = ex.modell_tco_csv(modelle)
    assert zahl == 2
    zeilen = [z.split(";") for z in inhalt.split("\r\n") if z]
    kopf = zeilen[0]
    assert kopf == ex.SPALTEN_MODELL_TCO
    apple = next(z for z in zeilen[1:] if z[1] == "Apple X")
    pixel = next(z for z in zeilen[1:] if z[1] == "Pixel 11")
    assert apple[kopf.index("TCO ab EUR")] == "1000,00"
    assert apple[kopf.index("Abweichung zu Vodafone EUR")] == "-100,00"
    # Klartext wie auf der Seite (S4-1): der Chip der Vergleichsansicht
    # sagt "Klein", nicht "klein" - zwei Sprachen fuer dieselbe Sache
    # waeren der O4-Befund wieder.
    assert apple[kopf.index("Tarifband")] == "Klein"
    assert apple[kopf.index("Status")] == ""
    assert pixel[kopf.index("TCO ab EUR")] == ""
    assert pixel[kopf.index("Status")] == "kein Bündel gemessen"


def test_schreibe_exporte_legt_beide_ansichten_an(tmp_path):
    modelle = _beispiel_zeilen()
    angaben = ex.schreibe_exporte(tmp_path, [], [], _katalog(),
                                  modelle=modelle)
    for schluessel, datei in (("modell_barpreis", "geraete-modell-barpreis.csv"),
                              ("modell_tco", "geraete-modell-tco.csv")):
        pfad = tmp_path / "exporte" / datei
        assert pfad.exists(), f"{datei} fehlt"
        assert angaben[schluessel]["zeilen"] == 2
        assert angaben[schluessel]["bytes"] == pfad.stat().st_size, (
            "die Groessenangabe neben dem Link ist die GEMESSENE Zahl")


def test_leer_zustand_traegt_beide_ansichten():
    angaben = ex.leer()
    assert angaben["modell_barpreis"]["zeilen"] == 0
    assert angaben["modell_tco"]["datei"] == ""
