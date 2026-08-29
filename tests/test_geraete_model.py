"""Das Datenmodell des Geraete- und Preisradars.

Der eine Fehler, der dieses Feature killt, steht in Teil F des Auftrags und
hat in diesem Repo schon einmal zugeschlagen: `promo_store.entry_id()` hasht
die Ueberschrift. Fuer eine Aktion geht das gerade noch (dort faengt eine
Fuzzy-Suche die Umformulierung ab), fuer ein Geraet nicht - Haendler
schreiben denselben Artikel jede Woche anders:

    "APPLE iPhone 17 Pro Max 5G 256 GB Titannatur"
    "Apple iPhone 17 Pro Max (256 GB) - Titan Natur"
    "Apple iPhone 17 Pro Max 256GB Natural Titanium"

Aus einem Titel-Hash wuerden drei Geraete, jede Woche neu, und die gesamte
Lifecycle-Auswertung waere Muell. Deshalb entsteht die ID hier NIE aus dem
Titel, sondern aus dem KATALOGEINTRAG, den der Titel trifft, plus den
normalisierten Feldern Speicher und Farbe.
"""
import pytest

from telco_radar.geraete_model import (
    Geraet,
    Katalog,
    Listung,
    Sku,
    VERFUEGBARKEITEN,
    device_id,
    erkenne_geraet,
    farbe_aus_titel,
    lies_listung,
    listung_id,
    normalisiere,
    normalisiere_farbe,
    ohne_zustandswort,
    sku_id,
    speicher_aus_titel,
    wortmarken,
    zustand_aus_titel,
)

# --------------------------------------------------------------------------
# Ein kleiner Katalog, der die drei Fallen enthaelt, an denen eine naive
# Erkennung scheitert: eine Modellfamilie mit gemeinsamem Praefix
# (iPhone 17 / 17 Pro / 17 Pro Max), zwei Hersteller mit derselben Ziffer
# und ein Geraet, dessen Name eine angeklebte Ziffer traegt (Fold7).
# --------------------------------------------------------------------------
_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Apple", modell="iPhone 17", generation=17,
           vorgaenger="iPhone 16", marktstart="2026-09-19",
           speicher=[128, 256, 512], segment="premium"),
    Geraet(hersteller="Apple", modell="iPhone 17 Pro", generation=17,
           vorgaenger="iPhone 16 Pro", marktstart="2026-09-19",
           speicher=[256, 512, 1024], segment="flagship"),
    Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
           vorgaenger="iPhone 16 Pro Max", marktstart="2026-09-19",
           aliase=["Apple iPhone 17 ProMax 5G"],
           speicher=[256, 512, 1024], segment="flagship"),
    Geraet(hersteller="Apple", modell="iPhone 16 Pro Max", generation=16,
           marktstart="2025-09-20", speicher=[256, 512, 1024],
           segment="flagship"),
    Geraet(hersteller="Samsung", modell="Galaxy S25 Ultra", generation=25,
           marktstart="2026-01-24", speicher=[256, 512, 1024],
           segment="flagship"),
    Geraet(hersteller="Samsung", modell="Galaxy Z Fold 7", generation=7,
           marktstart="2026-07-25", speicher=[256, 512],
           segment="flagship"),
])

_FARBEN = {
    "titannatur": "titan-natur",
    "titan-natur": "titan-natur",
    "natural-titanium": "titan-natur",
    "schwarz": "schwarz",
    "phantom-black": "schwarz",
}


# --------------------------------------------------------------------------
# Normalisierung
# --------------------------------------------------------------------------

def test_normalisiere_faltet_umlaute_und_sonderzeichen():
    assert normalisiere("Titan Natur") == "titan-natur"
    assert normalisiere("Grün / Größe") == "gruen-groesse"
    assert normalisiere("  Apple   iPhone  ") == "apple-iphone"
    assert normalisiere("Weiß") == "weiss"


def test_wortmarken_trennen_angeklebte_ziffern_nach_buchstaben():
    # "Fold7" und "Fold 7" muessen dieselbe Marke ergeben, sonst findet der
    # Katalogeintrag "Galaxy Z Fold 7" die Haendlerschreibweise nie.
    assert wortmarken("Galaxy Z Fold7") == wortmarken("Galaxy Z Fold 7")
    assert wortmarken("Galaxy S25 Ultra") == ["galaxy", "s", "25", "ultra"]


def test_wortmarken_lassen_ziffer_buchstabe_zusammen():
    # Umgekehrt darf "3a" NICHT zu "3" + "a" zerfallen: sonst matcht der
    # Katalogeintrag "Nothing Phone 3" auf das "Nothing Phone (3a)" und
    # zwei verschiedene Geraete bekaemen dieselbe ID.
    assert "3a" in wortmarken("Nothing Phone (3a) Pro")
    assert "3" not in wortmarken("Nothing Phone (3a) Pro")
    # Dasselbe schuetzt "5G" davor, als Ziffer 5 gelesen zu werden.
    assert "5g" in wortmarken("iPhone 17 Pro 5G")


# --------------------------------------------------------------------------
# Die ID-Regel
# --------------------------------------------------------------------------

def test_ids_sind_lesbar_und_nicht_gehasht():
    # Klartext statt Hash, dieselbe Begruendung wie bei data/state/ct_seen.jsonl:
    # es sind hunderte Zeilen, nicht Millionen, und der Klartext ist die halbe
    # Diagnose.
    d = device_id("Apple", "iPhone 17 Pro Max")
    assert d == "apple-iphone-17-pro-max"
    s = sku_id(d, 256, "titan-natur")
    assert s == "apple-iphone-17-pro-max-256gb-titan-natur"
    assert listung_id(s, "MediaMarkt") == "mediamarkt--" + s


def test_sku_id_ohne_speicher_oder_farbe_sagt_das_offen():
    d = device_id("Apple", "iPhone 17")
    assert sku_id(d, None, "schwarz") == "apple-iphone-17-ohne-speicher-schwarz"
    assert sku_id(d, 128, None) == "apple-iphone-17-128gb-ohne-farbe"


@pytest.mark.parametrize("titel", [
    "APPLE iPhone 17 Pro Max 5G 256 GB Titannatur Dual-SIM",
    "Apple iPhone 17 Pro Max (256 GB) - Titan Natur",
    "Apple iPhone 17 Pro Max 256GB Natural Titanium, Smartphone",
])
def test_drei_haendlerschreibweisen_ergeben_dieselbe_sku_id(titel):
    """Akzeptanzkriterium 1 aus Teil E."""
    listung = lies_listung(
        titel=titel, anbieter="MediaMarkt", anbieter_typ="handel",
        quelle_url="https://example.de/p/1", abgerufen_am="2026-08-10",
        katalog=_KATALOG, farben=_FARBEN, preis_ohne_vertrag=1449.0)
    assert listung is not None
    assert listung.sku_id == "apple-iphone-17-pro-max-256gb-titan-natur"
    assert listung.device_id == "apple-iphone-17-pro-max"


def test_geaenderter_produkttitel_ergibt_keine_neue_id():
    """Der Kern der Regel: derselbe Artikel, naechste Woche umbenannt."""
    alt = lies_listung(
        titel="Apple iPhone 17 Pro Max 256GB Titannatur", anbieter="expert",
        anbieter_typ="handel", quelle_url="https://example.de/p/1",
        abgerufen_am="2026-08-03", katalog=_KATALOG, farben=_FARBEN,
        preis_ohne_vertrag=1449.0)
    neu = lies_listung(
        titel="Apple iPhone 17 Pro Max 5G 256 GB Titan Natur (Neuware, "
              "sofort lieferbar)", anbieter="expert", anbieter_typ="handel",
        quelle_url="https://example.de/p/1", abgerufen_am="2026-08-10",
        katalog=_KATALOG, farben=_FARBEN, preis_ohne_vertrag=1399.0)
    assert alt is not None and neu is not None
    assert alt.listung_id == neu.listung_id
    # Gegenprobe, damit der Test nicht durch einen leeren Vergleich gruen
    # wird: die Titel sind wirklich verschieden.
    assert alt.titel_roh != neu.titel_roh


def test_verschiedene_speicher_sind_verschiedene_skus():
    ids = {
        lies_listung(titel=f"Apple iPhone 17 Pro Max {gb} GB Titannatur",
                     anbieter="expert", anbieter_typ="handel",
                     quelle_url="https://example.de/p", abgerufen_am="2026-08-10",
                     katalog=_KATALOG, farben=_FARBEN).sku_id
        for gb in (256, 512, 1024)
    }
    assert len(ids) == 3


# --------------------------------------------------------------------------
# Geraeteerkennung
# --------------------------------------------------------------------------

def test_laengster_treffer_gewinnt():
    """"iPhone 17", "iPhone 17 Pro" und "iPhone 17 Pro Max" stehen alle im
    Katalog und passen alle auf denselben Titel. Ohne diese Regel liefe die
    ganze Pro-Max-Klasse unter "iPhone 17"."""
    g = erkenne_geraet("Apple iPhone 17 Pro Max 256 GB", _KATALOG)
    assert g.modell == "iPhone 17 Pro Max"
    assert erkenne_geraet("Apple iPhone 17 Pro 256 GB", _KATALOG).modell == "iPhone 17 Pro"
    assert erkenne_geraet("Apple iPhone 17 128 GB Blau", _KATALOG).modell == "iPhone 17"


def test_alias_greift():
    g = erkenne_geraet("Apple iPhone 17 ProMax 5G 512GB", _KATALOG)
    assert g is not None and g.modell == "iPhone 17 Pro Max"


def test_angeklebte_ziffer_wird_erkannt():
    g = erkenne_geraet("Samsung Galaxy Z Fold7 5G 512 GB", _KATALOG)
    assert g is not None and g.modell == "Galaxy Z Fold 7"


@pytest.mark.parametrize("titel", [
    "Schutzhülle für Apple iPhone 17 Pro Max, transparent",
    "Panzerglas Displayschutz iPhone 17 Pro Max (2er-Pack)",
    "Samsung Galaxy Z Fold 7 Case, schwarz",
    "Ladekabel USB-C für iPhone 17",
])
def test_zubehoer_ist_kein_geraet(titel):
    """Eine Kategorieseite eines Haendlers listet Huellen und Schutzglas
    zwischen den Geraeten. Ohne diesen Filter stuenden 9,99-Euro-Huellen als
    Preispunkt des iPhone 17 Pro Max in der Positionskarte."""
    assert erkenne_geraet(titel, _KATALOG) is None


def test_zubehoerwort_im_geraetetitel_verwirft_nicht():
    # Gegenprobe: "Case" faellt, "Displayschutz ab Werk" im Fliesstext eines
    # echten Geraetetitels darf es nicht - deshalb steht der Filter auf
    # eigenen Woertern, nicht auf Teilketten.
    g = erkenne_geraet("Apple iPhone 17 Pro Max 256 GB Showcase-Modell", _KATALOG)
    assert g is not None and g.modell == "iPhone 17 Pro Max"


def test_unbekanntes_geraet_wird_nicht_erfunden():
    assert erkenne_geraet("Fairphone 6 256 GB", _KATALOG) is None
    assert lies_listung(titel="Fairphone 6 256 GB", anbieter="expert",
                        anbieter_typ="handel", quelle_url="https://example.de/p",
                        abgerufen_am="2026-08-10", katalog=_KATALOG,
                        farben=_FARBEN) is None


def test_teiltreffer_ueber_wortgrenze_zaehlt_nicht():
    # "17" allein darf "iPhone 17" nicht ausloesen. Der Titel darf dafuer
    # KEIN Zubehoerwort enthalten, sonst faellt er schon dort durch und der
    # Test prueft die Wortfolgenpruefung gar nicht.
    from telco_radar.geraete_model import _ist_zubehoer
    titel = "Apple Watch Series 17 GPS 42 mm"
    assert not _ist_zubehoer(wortmarken(titel))
    assert erkenne_geraet(titel, _KATALOG) is None


# --------------------------------------------------------------------------
# Speicher
# --------------------------------------------------------------------------

@pytest.mark.parametrize("titel,erwartet", [
    ("iPhone 17 Pro Max 256GB", 256),
    ("iPhone 17 Pro Max 256 GB", 256),
    ("Galaxy S25 Ultra 1 TB", 1024),
    ("Galaxy S25 Ultra 1TB Titanium", 1024),
])
def test_speicher_aus_titel(titel, erwartet):
    assert speicher_aus_titel(titel) == erwartet


def test_arbeitsspeicher_ist_kein_speicher():
    assert speicher_aus_titel("Galaxy S25 Ultra 12 GB RAM / 512 GB") == 512


def test_5g_ist_keine_speichergroesse():
    # Der Fall muss eine ECHTE Groessenangabe enthalten, sonst prueft er
    # nichts: ein Titel ohne "GB" kann die Regex ohnehin nicht treffen.
    assert speicher_aus_titel("iPhone 17 Pro 5G 256 GB") == 256
    assert wortmarken("iPhone 17 Pro 5G")[-1] == "5g"


def test_zwei_verschiedene_groessen_im_titel_ergeben_keine_vermutung():
    # Eine Sammelseite "256 GB / 512 GB" darf keinen Wert raten.
    assert speicher_aus_titel("iPhone 17 Pro Max 256 GB / 512 GB") is None


def test_1024_gb_und_1_tb_sind_derselbe_wert():
    assert speicher_aus_titel("Galaxy S25 Ultra 1024 GB") == \
        speicher_aus_titel("Galaxy S25 Ultra 1 TB")


# --------------------------------------------------------------------------
# Farben
# --------------------------------------------------------------------------

def test_farbnormalisierung_fasst_schreibweisen_zusammen():
    assert normalisiere_farbe("Titannatur", _FARBEN) == "titan-natur"
    assert normalisiere_farbe("Titan Natur", _FARBEN) == "titan-natur"
    assert normalisiere_farbe("Natural Titanium", _FARBEN) == "titan-natur"


def test_unbekannte_farbe_wird_behalten_und_nicht_geraten():
    assert normalisiere_farbe("Desert Mocha", _FARBEN) is None


def test_unbekannte_farbe_landet_trotzdem_in_der_sku_id():
    """Sonst faendest du zwei Geraete in einem Topf, nur weil niemand die
    Farbtabelle gepflegt hat. Der Preis dafuer steht im Farbbericht am
    Seitenende: zwei unbekannte Schreibweisen sind zwei SKUs."""
    l = lies_listung(titel="Apple iPhone 17 Pro Max 256 GB Desert Mocha",
                     anbieter="expert", anbieter_typ="handel",
                     quelle_url="https://example.de/p", abgerufen_am="2026-08-10",
                     katalog=_KATALOG, farben=_FARBEN, farbe_roh="Desert Mocha")
    assert l.farbe_normalisiert is None
    assert l.farbe_roh == "Desert Mocha"
    assert l.sku_id.endswith("-desert-mocha")


def test_ohne_farbfeld_der_quelle_wird_keine_farbe_erfunden():
    """Gegenstueck zum Test darueber, und der Pfad, der wirklich haeufig ist:
    steht die Farbe NUR im Titel und kennt die Tabelle sie nicht, gibt es
    keine Farbe. Das ist ehrlich - aber es heisst auch, dass der Farbbericht
    am Seitenende sich aus den Farbfeldern der QUELLEN speist, nicht aus
    Titeln."""
    l = lies_listung(titel="Apple iPhone 17 Pro Max 256 GB Desert Mocha",
                     anbieter="expert", anbieter_typ="handel",
                     quelle_url="https://example.de/p", abgerufen_am="2026-08-10",
                     katalog=_KATALOG, farben=_FARBEN)
    assert l.farbe_roh == "" and l.farbe_normalisiert is None
    assert l.sku_id.endswith("-ohne-farbe")


def test_farbe_aus_titel_gibt_die_rohschreibweise_zurueck():
    roh, kanonisch = farbe_aus_titel("Apple iPhone 17 Pro Max 256 GB Titan Natur",
                                     _FARBEN)
    assert roh == "Titan Natur"
    assert kanonisch == "titan-natur"


def test_farbe_aus_titel_ohne_treffer():
    assert farbe_aus_titel("Apple iPhone 17 Pro Max 256 GB", _FARBEN) == ("", None)


# --------------------------------------------------------------------------
# Listung: die harten Zusicherungen
# --------------------------------------------------------------------------

def test_listung_ohne_quelle_laesst_sich_nicht_bauen():
    """Akzeptanzkriterium aus Teil E: kein Preis ohne Quelle und Abrufdatum."""
    with pytest.raises(ValueError, match="quelle_url"):
        Listung(sku_id="x", device_id="x", anbieter="expert",
                anbieter_typ="handel", quelle_url="", abgerufen_am="2026-08-10")


def test_listung_ohne_abrufdatum_laesst_sich_nicht_bauen():
    with pytest.raises(ValueError, match="abgerufen_am"):
        Listung(sku_id="x", device_id="x", anbieter="expert",
                anbieter_typ="handel", quelle_url="https://e.de/p",
                abgerufen_am="")


def test_abrufdatum_muss_ein_datum_sein():
    with pytest.raises(ValueError, match="abgerufen_am"):
        Listung(sku_id="x", device_id="x", anbieter="expert",
                anbieter_typ="handel", quelle_url="https://e.de/p",
                abgerufen_am="gestern")


def test_unbekannte_verfuegbarkeit_wird_abgewiesen():
    with pytest.raises(ValueError, match="verfuegbarkeit"):
        Listung(sku_id="x", device_id="x", anbieter="expert",
                anbieter_typ="handel", quelle_url="https://e.de/p",
                abgerufen_am="2026-08-10", verfuegbarkeit="vielleicht")


def test_ausverkauft_ist_nicht_ausgelistet():
    """Teil F: 'Voruebergehend nicht lieferbar' ist eine eigene Stufe, kein
    Portfolio-Ende. Beide Werte muessen es getrennt geben."""
    assert "ausverkauft" in VERFUEGBARKEITEN
    assert "nicht_lieferbar" in VERFUEGBARKEITEN
    assert "ausgelistet" not in VERFUEGBARKEITEN


def test_negativer_preis_wird_abgewiesen():
    with pytest.raises(ValueError, match="preis"):
        Listung(sku_id="x", device_id="x", anbieter="expert",
                anbieter_typ="handel", quelle_url="https://e.de/p",
                abgerufen_am="2026-08-10", preis_ohne_vertrag=-1.0)


def test_zwei_preisarten_bleiben_getrennt():
    """Teil C4: Geraetepreis ohne Vertrag und Zuzahlung im Buendel sind nicht
    dieselbe Zahl - und eine Zuzahlung ohne Tarifbezug ist bedeutungslos."""
    l = lies_listung(titel="Apple iPhone 17 Pro Max 256 GB Titannatur",
                     anbieter="Telekom", anbieter_typ="netzbetreiber",
                     quelle_url="https://telekom.de/p", abgerufen_am="2026-08-10",
                     katalog=_KATALOG, farben=_FARBEN, zuzahlung=49.95,
                     tarif_referenz="MagentaMobil M")
    assert l.preis_ohne_vertrag is None
    assert l.zuzahlung == 49.95
    assert l.tarif_referenz == "MagentaMobil M"
    assert l.preisart == "buendel"


def test_zuzahlung_ohne_tarifbezug_wird_abgewiesen():
    with pytest.raises(ValueError, match="tarif_referenz"):
        Listung(sku_id="x", device_id="x", anbieter="Telekom",
                anbieter_typ="netzbetreiber", quelle_url="https://e.de/p",
                abgerufen_am="2026-08-10", zuzahlung=1.0)


def test_preisart_ohne_vertrag():
    l = Listung(sku_id="x", device_id="x", anbieter="expert",
                anbieter_typ="handel", quelle_url="https://e.de/p",
                abgerufen_am="2026-08-10", preis_ohne_vertrag=1449.0)
    assert l.preisart == "ohne_vertrag"


def test_listung_ohne_jeden_preis_ist_erlaubt_aber_kennzeichnet_sich():
    # Ein Geraet kann gelistet und gerade nicht bepreist sein
    # ("demnaechst verfuegbar"). Das ist eine Listung, aber kein Preis.
    l = Listung(sku_id="x", device_id="x", anbieter="expert",
                anbieter_typ="handel", quelle_url="https://e.de/p",
                abgerufen_am="2026-08-10", verfuegbarkeit="vorbestellbar")
    assert l.preisart == "kein_preis"
    assert l.preis is None


def test_sku_aus_listung():
    l = lies_listung(titel="Apple iPhone 17 Pro Max 256 GB Titannatur",
                     anbieter="expert", anbieter_typ="handel",
                     quelle_url="https://example.de/p", abgerufen_am="2026-08-10",
                     katalog=_KATALOG, farben=_FARBEN, ean="0194253000000")
    s = l.sku()
    assert isinstance(s, Sku)
    assert s.sku_id == l.sku_id and s.speicher_gb == 256 and s.ean == "0194253000000"


# --------------------------------------------------------------------------
# Katalog: die Vorgaengerkette
# --------------------------------------------------------------------------

def test_vorgaengerkette_wird_auf_device_ids_aufgeloest():
    g = _KATALOG.nach_id("apple-iphone-17-pro-max")
    assert g.vorgaenger_device_id == "apple-iphone-16-pro-max"
    assert _KATALOG.vorgaenger_von("apple-iphone-17-pro-max").modell == "iPhone 16 Pro Max"
    assert _KATALOG.nachfolger_von("apple-iphone-16-pro-max").modell == "iPhone 17 Pro Max"


def test_vorgaenger_ausserhalb_des_katalogs_bleibt_leer():
    # "iPhone 16" steht nicht im Katalog - die Kette bricht, und das darf
    # nicht als Treffer durchgehen.
    assert _KATALOG.vorgaenger_von("apple-iphone-17") is None
    assert _KATALOG.nach_id("apple-iphone-17").vorgaenger_device_id == "apple-iphone-16"


def test_katalog_weist_doppelte_geraete_ab():
    with pytest.raises(ValueError, match="doppelt"):
        Katalog(geraete=[
            Geraet(hersteller="Apple", modell="iPhone 17", marktstart="2026-09-19"),
            Geraet(hersteller="Apple", modell="iPhone  17", marktstart="2026-09-19"),
        ])


# --------------------------------------------------------------------------
# Die Befunde des Reviews vom 10.08.2026, jeder mit seinem Reproduktionsfall.
# Gegen den Stand VOR den Korrekturen faellt jeder dieser Tests durch.
# --------------------------------------------------------------------------

_KATALOG_REVIEW = Katalog(geraete=[
    Geraet(hersteller="Google", modell="Pixel 10 Pro", generation=10,
           speicher=[128, 256], segment="flagship"),
    Geraet(hersteller="Samsung", modell="Galaxy S25", generation=25,
           speicher=[128, 256, 512], segment="premium"),
    Geraet(hersteller="Samsung", modell="Galaxy S25 Plus", generation=25,
           speicher=[256, 512], segment="premium"),
    Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
           speicher=[256, 512, 1024], segment="flagship"),
    Geraet(hersteller="Apple", modell="iPhone 17", generation=17,
           speicher=[256, 512], segment="premium"),
])


@pytest.mark.parametrize("titel", [
    "Google Pixel 10 Pro Fold 256 GB Moonstone",
    "Samsung Galaxy S25 FE 128 GB Icyblue",
    "Samsung Galaxy S25 Edge 256GB",
])
def test_ein_modellzusatz_hinter_dem_treffer_verwirft_die_zuordnung(titel):
    """Befund 1 des Reviews, der teuerste: "Pixel 10 Pro Fold" traf den
    Katalogeintrag "Pixel 10 Pro". Beide stehen beim selben Haendler, liegen
    rund 800 Euro auseinander und teilten sich damit eine listung_id - die
    Preishistorie schrieb in JEDEM Lauf zwei Aenderungspunkte hin und zurueck.
    Eine dauerhafte Saegezahnkurve, die wie ein Preiskampf aussieht."""
    assert erkenne_geraet(titel, _KATALOG_REVIEW) is None


def test_ohne_zusatz_greift_derselbe_titel_weiterhin():
    # Gegenprobe: die Sperre darf nicht den Normalfall verwerfen.
    g = erkenne_geraet("Google Pixel 10 Pro 256 GB Moonstone", _KATALOG_REVIEW)
    assert g is not None and g.modell == "Pixel 10 Pro"


def test_pluszeichen_wird_zu_plus_und_findet_das_richtige_modell():
    """"Galaxy S25+" verlor sein Pluszeichen in der Normalisierung und lief
    als "Galaxy S25" - zwei Geraete, eine ID."""
    g = erkenne_geraet("Samsung Galaxy S25+ 5G 256GB Navy", _KATALOG_REVIEW)
    assert g is not None and g.modell == "Galaxy S25 Plus"


def test_binnenmajuskel_wird_getrennt():
    """"ProMax" zerfiel nicht, der Titel lief als "iPhone 17"."""
    g = erkenne_geraet("Apple iPhone 17 ProMax 256GB Titannatur", _KATALOG_REVIEW)
    assert g is not None and g.modell == "iPhone 17 Pro Max"
    # ... und "iPhone" darf dabei NICHT zu "i Phone" zerfallen.
    assert wortmarken("iPhone")[0] == "iphone"


@pytest.mark.parametrize("titel,modell", [
    ("Apple iPhone 17 Pro Max 256GB Titanschwarz, ohne Netzteil", "iPhone 17 Pro Max"),
    ("Apple iPhone 17 256 GB Blau inkl. Ladekabel", "iPhone 17"),
])
def test_zubehoerwort_hinter_dem_modell_verwirft_kein_geraet(titel, modell):
    """Befund 6: "ohne Netzteil" ist im deutschen Handel eine Pflichtangabe.
    Eine einzige breite Zubehoerliste hat echte Geraete verworfen."""
    g = erkenne_geraet(titel, _KATALOG_REVIEW)
    assert g is not None and g.modell == modell


def test_zubehoerwort_vor_dem_modell_verwirft_weiterhin():
    assert erkenne_geraet("Ladekabel USB-C für Apple iPhone 17", _KATALOG_REVIEW) is None


def test_ram_ohne_trennzeichen_verschluckt_den_speicher_nicht():
    """Befund 7: "12 GB RAM 512 GB" - ohne Schraegstrich fand die
    Rueckwaertssuche das RAM der ERSTEN Angabe und verwarf die zweite."""
    assert speicher_aus_titel("Samsung Galaxy S25 Ultra 12 GB RAM 512 GB") == 512
    assert speicher_aus_titel("Galaxy S25 Ultra 512 GB / 12 GB RAM") == 512
    assert speicher_aus_titel("Arbeitsspeicher: 12 GB, Speicher 512 GB") == 512
    # Gegenprobe: eine reine RAM-Angabe bleibt eine RAM-Angabe.
    assert speicher_aus_titel("Galaxy S25 Ultra 8 GB RAM") is None


def test_katalogstufen_sind_eine_vorliebe_kein_filter():
    """Befund 8: eine im Katalog vergessene Stufe darf den Wert nicht
    verschlucken - sonst faellt die Variante als `ohne-speicher` in einen
    Topf mit jeder anderen ungelesenen."""
    assert speicher_aus_titel("Apple iPhone 17 1 TB Blau", erlaubt=[256, 512]) == 1024


def test_mehrdeutigkeit_wird_ueber_die_katalogstufen_aufgeloest():
    # Zwei Werte, aber nur einer steht im Katalog: dann ist es dieser.
    assert speicher_aus_titel("iPhone 17 mit 64 GB oder 256 GB",
                              erlaubt=[256, 512]) == 256
    # Zwei Werte, beide im Katalog: es wird nichts geraten.
    assert speicher_aus_titel("iPhone 17 256 GB / 512 GB", erlaubt=[256, 512]) is None


def test_farbbruchstueck_wird_nicht_kanonisiert():
    """Befund 13: aus "Titanium Black" wurde ueber das Teilwort "Black" die
    Farbe `schwarz`, waehrend "Black Titanium" - dieselbe Farbe, andere
    Wortstellung - `titan-schwarz` ergab. Zwei SKUs fuer ein Geraet."""
    tabelle = {"schwarz": "schwarz", "black": "schwarz",
               "titan-schwarz": "titan-schwarz", "black-titanium": "titan-schwarz",
               "gold": "gold", "rosa": "rosa", "rose": "rosa"}
    assert farbe_aus_titel("Handy in Black Titanium", tabelle)[1] == "titan-schwarz"
    # "Titanium Black" kennt die Tabelle nicht - dann gibt es keine Farbe,
    # statt das Bruchstueck "Black" zu nehmen.
    assert farbe_aus_titel("Handy in Titanium Black", tabelle)[1] is None
    # "Rose Gold" ist weder Rose noch Gold.
    assert farbe_aus_titel("Handy in Rose Gold", tabelle) == ("", None)


def test_gebrauchtgeraet_ist_eine_eigene_sku():
    """Befund 17: freenet fuehrt eine eigene "-refurbished"-Strecke. Ohne
    diese Dimension teilten sich Neu- und Gebrauchtgeraet eine listung_id,
    und der Preisverlauf sprang zwischen beiden Preisen."""
    neu = lies_listung(titel="Apple iPhone 17 Pro Max 256 GB Titannatur",
                       anbieter="freenet", anbieter_typ="handel",
                       quelle_url="https://f.de/p/iphone-17-pro-max-ohne-vertrag",
                       abgerufen_am="2026-08-10", katalog=_KATALOG_REVIEW,
                       farben=_FARBEN, preis_ohne_vertrag=1449.0)
    alt = lies_listung(titel="Apple iPhone 17 Pro Max 256 GB Titannatur",
                       anbieter="freenet", anbieter_typ="handel",
                       quelle_url="https://f.de/p/iphone-17-pro-max-refurbished-ohne-vertrag",
                       abgerufen_am="2026-08-10", katalog=_KATALOG_REVIEW,
                       farben=_FARBEN, preis_ohne_vertrag=899.0)
    assert neu.zustand == "neu" and alt.zustand == "refurbished"
    assert neu.listung_id != alt.listung_id
    assert alt.sku_id.endswith("-refurbished")


def test_vertragspreis_ohne_tarifbezug_wird_abgewiesen():
    """Befund 12: `zuzahlung` war gesichert, `preis_mit_vertrag_ab` nicht -
    das Schlupfloch, durch das der Lockpreis doch auf die Seite kaeme."""
    with pytest.raises(ValueError, match="tarif_referenz"):
        Listung(sku_id="x", device_id="x", anbieter="o2",
                anbieter_typ="netzbetreiber", quelle_url="https://e.de/p",
                abgerufen_am="2026-08-10", preis_mit_vertrag_ab=1.00)


# --------------------------------------------------------------------------
# Zustand: die Preisdimension, die am 29.08.2026 den Vergleich verdreht hat
# --------------------------------------------------------------------------

@pytest.mark.parametrize("titel,erwartet", [
    # o2 kennzeichnet seine Gebrauchtstrecke in ZWEI Schreibweisen. Die
    # Stichwortliste kannte am 29.08.2026 nur die erste - und genau die zwei
    # Geraete, die o2 "(erneuert)" nennt, liefen als Neugeraet mit und
    # gewannen damit den Preisvergleich gegen Vodafone.
    ("Apple iPhone 14 (gebraucht) 128 GB mitternacht erneuert", "refurbished"),
    ("Apple iPhone 14 Pro (erneuert) 128 GB space schwarz erneuert", "refurbished"),
    ("Samsung Galaxy S25 (erneuert) 128 GB grau erneuert", "refurbished"),
    ("Apple iPhone 16 (gebraucht) 128 GB blau erneuert", "refurbished"),
    # "wie neu" stand in der Liste und konnte nie treffen: ein Zwei-Wort-
    # String wurde gegen eine Menge einzelner Wortmarken geprueft.
    ("Apple iPhone 13 wie neu 128 GB", "refurbished"),
    ("Apple iPhone 15 renewed 128 GB", "refurbished"),
    ("Apple iPhone 15 generalueberholt 128 GB", "refurbished"),
    ("Samsung Galaxy S24 B-Ware 128 GB", "b-ware"),
    # Gegenprobe: ein Neugeraet bleibt neu. "Neuheit" und "erneuerbar"
    # duerfen nicht anschlagen - deshalb Wortmarken statt Teilketten.
    ("Apple iPhone 17 256 GB Titannatur", "neu"),
    ("Samsung Galaxy S25 Neuheit 128 GB", "neu"),
])
def test_zustand_kennt_alle_schreibweisen_des_handels(titel, erwartet):
    assert zustand_aus_titel(titel) == erwartet


def test_zustand_liest_auch_das_farbfeld():
    """Der Zustand steht nicht immer im Titel. Bei einer Quelle, die Farbe
    strukturiert liefert ("grau erneuert"), ist das Farbfeld das einzige
    Signal - und wurde bis zum 29.08.2026 gar nicht befragt."""
    listung = lies_listung(
        titel="Samsung Galaxy S25 128 GB", anbieter="o2",
        anbieter_typ="netzbetreiber",
        quelle_url="https://www.o2online.de/e-shop/samsung/s25-128gb-details",
        abgerufen_am="2026-08-29", katalog=_KATALOG_REVIEW, farben=_FARBEN,
        farbe_roh="grau erneuert", speicher_gb=128, preis_ohne_vertrag=577.0)
    assert listung.zustand == "refurbished"
    assert listung.sku_id.endswith("-refurbished")


@pytest.mark.parametrize("titel,farbe,url,preis", [
    ("Apple iPhone 14 Pro (erneuert) 128 GB space schwarz erneuert",
     "space schwarz erneuert",
     "https://www.o2online.de/e-shop/apple/apple-iphone-14-pro-128gb-space-schwarz-erneuert-details",
     577.0),
    ("Samsung Galaxy S25 (erneuert) 128 GB grau erneuert", "grau erneuert",
     "https://www.o2online.de/e-shop/samsung/samsung-galaxy-s25-128gb-grau-erneuert-details",
     577.0),
    ("Apple iPhone 16 (gebraucht) 128 GB blau erneuert", "blau erneuert",
     "https://www.o2online.de/e-shop/apple/apple-iphone-16-128gb-blau-erneuert-details",
     697.0),
])
def test_die_drei_faelle_der_evaluation_vom_29_august(titel, farbe, url, preis):
    """Regressionsfaelle aus `claude/geraeteradar-evaluation-2026-08-29.md`,
    Abschnitt 1. Alle drei standen live im Export; zwei davon (die
    "(erneuert)"-Schreibweise) liefen als Neugeraet und schlugen damit den
    Vodafone-Preis. Der dritte war korrekt erkannt und belegt, dass der
    Filter im Vergleich greift, sobald der Zustand stimmt."""
    katalog = Katalog(geraete=[
        Geraet(hersteller="Apple", modell="iPhone 14 Pro", generation=14,
               speicher=[128, 256], segment="flagship"),
        Geraet(hersteller="Apple", modell="iPhone 16", generation=16,
               speicher=[128, 256], segment="premium"),
        Geraet(hersteller="Samsung", modell="Galaxy S25", generation=25,
               speicher=[128, 256], segment="premium"),
    ])
    listung = lies_listung(
        titel=titel, anbieter="o2", anbieter_typ="netzbetreiber",
        quelle_url=url, abgerufen_am="2026-08-29", katalog=katalog,
        farben=_FARBEN, farbe_roh=farbe, speicher_gb=128,
        preis_ohne_vertrag=preis)
    assert listung is not None
    assert listung.zustand == "refurbished", (
        f"{titel!r} ist Gebrauchtware und darf den Neupreis-Vergleich "
        f"nicht gewinnen")


def test_der_zustand_wird_aus_der_farbe_herausgeloest():
    """W1.3: "space schwarz erneuert" ist kein Farbname, sondern Farbe plus
    Zustand. Bleibt das Wort in der Farbe stehen, fuehrt der Farbbericht am
    Seitenende eine Schreibweise, die keine Farbe ist, und dieselbe Farbe
    steht als zwei Eintraege da."""
    listung = lies_listung(
        titel="Apple iPhone 17 (erneuert) 256 GB", anbieter="o2",
        anbieter_typ="netzbetreiber", quelle_url="https://o2.de/p/x",
        abgerufen_am="2026-08-29", katalog=_KATALOG_REVIEW, farben=_FARBEN,
        farbe_roh="schwarz erneuert", speicher_gb=256,
        preis_ohne_vertrag=899.0)
    assert listung.zustand == "refurbished"
    assert "erneuert" not in (listung.farbe_roh or "")
    assert listung.farbe_roh == "schwarz"


def test_eine_farbe_die_nur_aus_dem_zustand_besteht_bleibt_stehen():
    """Gegenprobe: die Zerlegung darf das Feld nicht leeren. Bliebe von
    "gebraucht" nichts uebrig, verloere die SKU ihre Farbdimension und zwei
    verschiedene Geraete teilten sich eine ID."""
    listung = lies_listung(
        titel="Apple iPhone 17 256 GB", anbieter="o2",
        anbieter_typ="netzbetreiber", quelle_url="https://o2.de/p/y",
        abgerufen_am="2026-08-29", katalog=_KATALOG_REVIEW, farben=_FARBEN,
        farbe_roh="gebraucht", speicher_gb=256, preis_ohne_vertrag=899.0)
    assert listung.zustand == "refurbished"
    assert listung.farbe_roh == "gebraucht"


@pytest.mark.parametrize("titel", [
    "Apple iPhone 17 256 GB neuwertig",
    "Apple iPhone 17 256 GB Retoure",
    "Apple iPhone 17 256 GB Open Box",
    "Apple iPhone 17 256 GB zweite Wahl",
])
def test_ein_unklares_kennzeichen_wird_nicht_als_neu_durchgewunken(titel):
    """W1.1: "Ein Geraet, dessen Zustand nicht sicher bestimmbar ist,
    bekommt `zustand: unbekannt` und faellt aus dem Preisvergleich heraus -
    es wird nicht als "neu" angenommen."

    "neuwertig", "Retoure" und "Open Box" heissen im deutschen Handel je
    nach Haendler Verschiedenes. Sie auf "refurbished" zu raten waere
    genauso falsch wie sie als neu zu fuehren; beides ist eine Aussage, die
    die Quelle nicht deckt."""
    assert zustand_aus_titel(titel) == "unbekannt"


def test_ein_eindeutiges_kennzeichen_schlaegt_das_unklare():
    """"Apple iPhone 17 neuwertig refurbished" ist refurbished, nicht
    unbekannt: eine eindeutige Angabe wird durch eine unklare daneben nicht
    wieder unklar."""
    assert zustand_aus_titel("Apple iPhone 17 neuwertig refurbished") == "refurbished"


@pytest.mark.parametrize("farbe", ["   ", "", "gebraucht", "- -"])
def test_eine_leere_farbe_reisst_den_nachtlauf_nicht(farbe):
    """`lies_listung` ist der Einstieg fuer JEDEN Adapter, und weder
    `_uebernimm` noch `sammle_anbieter` noch `geraete_pipeline` fangen einen
    UnboundLocalError. Ein einziger Satz mit leerem Farbfeld beendete damit
    den kompletten Geraete-Nachtlauf - ohne Upsert, ohne Historie, ohne
    Protokoll, und in Actions sieht so ein Abbruch aus wie ein Lauf, der nie
    lief.

    Heute loesen ihn die vier ausgelieferten Adapter nicht aus, weil sie die
    Farbe selbst strippen. Die naechsten (otelo, klarmobil, congstar) sind
    noch nicht geschrieben."""
    listung = lies_listung(
        titel="Apple iPhone 17 256 GB", anbieter="o2",
        anbieter_typ="netzbetreiber", quelle_url="https://o2.de/p/x",
        abgerufen_am="2026-08-29", katalog=_KATALOG_REVIEW, farben=_FARBEN,
        farbe_roh=farbe, speicher_gb=256, preis_ohne_vertrag=899.0)
    assert listung is not None
    assert listung.sku_id


@pytest.mark.parametrize("roh,erwartet", [
    ("Schwarz (gebraucht)", "Schwarz"),
    ("schwarz, refurbished", "schwarz"),
    ("space schwarz erneuert", "space schwarz"),
    # Ein unklares Kennzeichen gehoert genauso wenig in die Farbe wie ein
    # eindeutiges - sonst traegt die sku_id "neuwertig" als Farbe.
    ("schwarz neuwertig", "schwarz"),
    # Gegenprobe: eine echte Farbe wird nicht angetastet.
    ("Erneuerbar-Gruen", "Erneuerbar-Gruen"),
    ("gebrauchtgrau", "gebrauchtgrau"),
    ("sunset-gold", "sunset-gold"),
])
def test_ohne_zustandswort_raeumt_auch_die_interpunktion_ab(roh, erwartet):
    assert ohne_zustandswort(roh) == erwartet


def test_ein_unbekannter_zustand_wird_abgewiesen():
    """Seit der Zustand ueber die Sichtbarkeit in Vergleich und Preisgrafik
    entscheidet, laesst ein Adapter mit "Neu" statt "neu" seine Listungen
    fail closed und stillschweigend aus beiden Preisaussagen fallen. Ein
    Tippfehler darf laut sein, nicht unsichtbar."""
    with pytest.raises(ValueError, match="zustand"):
        Listung(sku_id="x", device_id="x", anbieter="o2",
                anbieter_typ="netzbetreiber", quelle_url="https://o2.de/p",
                abgerufen_am="2026-08-29", zustand="Neu")
