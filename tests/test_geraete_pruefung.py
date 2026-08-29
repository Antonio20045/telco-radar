"""Die Plausibilitaetspruefung (W1.2, Evaluation vom 29.08.2026).

Der Auftrag: "Der niedrigste Preis ist nicht automatisch der beste
Vergleichswert. Er ist der wahrscheinlichste Fehler."
"""
import pytest

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report.geraete_pruefung import (
    AUSREISSER_ANTEIL,
    SPANNE_GRENZE,
    pruefe,
)

_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Samsung", modell="Galaxy S25", generation=25,
           speicher=[128, 256, 512], segment="premium"),
    Geraet(hersteller="Samsung", modell="Galaxy S26", generation=26,
           speicher=[128, 256], segment="premium"),
    Geraet(hersteller="Apple", modell="iPhone 17", generation=17,
           speicher=[256, 512], segment="flagship"),
])


def _e(anbieter="o2", gid="samsung-galaxy-s25", preis=849.0, speicher=128,
       zustand="neu", farbe="schwarz", status="aktiv"):
    return {
        "anbieter": anbieter, "device_id": gid, "speicher_gb": speicher,
        "zustand": zustand, "farbe_normalisiert": farbe, "status": status,
        "preis_ohne_vertrag": preis,
        "quelle_url": f"https://{anbieter}.de/p/{gid}-{farbe}",
        "abgerufen_am": "2026-08-29",
    }


# --------------------------------------------------------------------------
# Doppelpreis
# --------------------------------------------------------------------------

def test_ein_grosser_doppelpreis_fliegt_aus_dem_vergleich():
    """Der Fall aus der Evaluation: o2 fuehrte dasselbe Geraet fuer 577 und
    883 EUR (53 % Spanne). Welcher der beiden stimmt, sagt der Datensatz
    nicht - also darf keiner von beiden verglichen werden."""
    eintraege = [_e(preis=883.0, farbe="blau"), _e(preis=577.0, farbe="grau")]
    erg = pruefe(eintraege, _KATALOG)
    assert erg["sauber"] == []
    assert erg["zahlen"]["doppelpreise"] == 1
    assert erg["zahlen"]["entfernt"] == 1
    assert erg["befunde"][0]["spanne"] == pytest.approx(53.0, abs=0.5)


def test_ein_farbaufschlag_wird_berichtet_aber_nicht_geloescht():
    """Samsung bepreist Aktionsfarben wirklich verschieden: 955 gegen 1009 EUR
    sind 5,7 % und der Markt, kein Widerspruch. Eine Regel, die auch die
    verwirft, loescht wahre Preise."""
    eintraege = [_e(gid="samsung-galaxy-s26", preis=1009.0, speicher=256,
                    farbe="schwarz"),
                 _e(gid="samsung-galaxy-s26", preis=955.0, speicher=256,
                    farbe="cobalt violet")]
    erg = pruefe(eintraege, _KATALOG)
    assert len(erg["sauber"]) == 2, "ein Farbaufschlag ist kein Fehler"
    assert erg["zahlen"]["doppelpreise"] == 1, "berichtet wird er trotzdem"
    assert erg["zahlen"]["entfernt"] == 0
    assert erg["befunde"][0]["entfernt"] is False


def test_die_schwelle_trennt_die_gemessenen_faelle():
    """Die Grenze ist an echten Daten kalibriert (Modulkopf): Fehler lagen
    bei 53 und 112 Prozent, echte Farbpreise bei 5,7 bis 21,6."""
    assert 0.216 < SPANNE_GRENZE < 0.53


def test_neu_und_refurbished_sind_kein_doppelpreis():
    """Zwei Zustaende sind zwei Artikel. Waeren sie ein Doppelpreis,
    meldete die Pruefung genau das als Fehler, was richtig ist."""
    eintraege = [_e(preis=849.0), _e(preis=399.0, zustand="refurbished")]
    erg = pruefe(eintraege, _KATALOG)
    assert erg["zahlen"]["doppelpreise"] == 0
    assert len(erg["sauber"]) == 2


# --------------------------------------------------------------------------
# Speicherinversion
# --------------------------------------------------------------------------

def test_mehr_speicher_darf_nicht_billiger_sein():
    eintraege = [_e(speicher=256, preis=1081.0), _e(speicher=512, preis=745.0)]
    erg = pruefe(eintraege, _KATALOG)
    assert erg["sauber"] == []
    assert erg["zahlen"]["speicherinversionen"] == 1
    befund = next(b for b in erg["befunde"] if b["art"] == "speicherinversion")
    assert (befund["klein_gb"], befund["gross_gb"]) == (256, 512)


def test_die_normale_speicherstaffel_bleibt_unangetastet():
    """Gegenprobe: ohne sie waere eine Pruefung, die alles verwirft, gruen."""
    eintraege = [_e(speicher=128, preis=849.0), _e(speicher=256, preis=949.0),
                 _e(speicher=512, preis=1149.0)]
    assert len(pruefe(eintraege, _KATALOG)["sauber"]) == 3


def test_eine_inversion_ueber_zwei_zustaende_ist_keine():
    """Der Fall, den die Evaluation als Inversion gemeldet hat: das
    512-GB-Geraet fuer 745 EUR war refurbished. Ueber beide Zustaende
    gerechnet sieht das aus wie ein Widerspruch und ist keiner."""
    eintraege = [_e(speicher=256, preis=1081.0),
                 _e(speicher=512, preis=745.0, zustand="refurbished")]
    erg = pruefe(eintraege, _KATALOG)
    assert erg["zahlen"]["speicherinversionen"] == 0


# --------------------------------------------------------------------------
# Ausreisser
# --------------------------------------------------------------------------

def test_ein_ausreisser_wird_gemeldet_aber_nicht_geloescht():
    """Ein Doppelpreis und eine Speicherinversion sind SELBSTwiderspreche -
    der Datensatz widerspricht sich selbst. Ein Ausreisser widerspricht dem
    MARKT, und ein Discounter, der wirklich 60 Prozent unter dem Median
    liegt, ist genau das Signal, wegen dem diese Seite existiert. Ihn als
    Datenfehler zu entfernen hiesse, den Befund gegen die Erwartung zu
    verwerfen."""
    eintraege = [_e(anbieter="o2", preis=849.0),
                 _e(anbieter="Vodafone", preis=869.0),
                 _e(anbieter="freenet", preis=879.0),
                 _e(anbieter="billig.de", preis=99.0)]
    erg = pruefe(eintraege, _KATALOG)
    assert erg["zahlen"]["ausreisser"] == 1
    assert erg["zahlen"]["aussortiert"] == 0
    assert len(erg["sauber"]) == 4
    assert next(b for b in erg["befunde"]
                if b["art"] == "ausreisser")["entfernt"] is False


def test_die_pruefung_traegt_auch_ohne_listung_id():
    """`_schluessel` faellt auf `id()` zurueck. Ohne diesen Rueckfall waeren
    alle Eintraege ohne Kennung EIN Schluessel, und ein einziger Befund
    raeumte den ganzen Bestand ab."""
    eintraege = [{k: v for k, v in _e(preis=p).items() if k != "id"}
                 for p in (883.0, 577.0)]
    erg = pruefe(eintraege, _KATALOG)
    assert erg["zahlen"]["aussortiert"] == 2


def test_unter_drei_angeboten_wird_kein_median_gerechnet():
    """Bei zwei Werten IST der Median einer der beiden, und jede Abweichung
    waere per Definition gross - die Pruefung wuerde immer anschlagen."""
    eintraege = [_e(anbieter="o2", preis=849.0),
                 _e(anbieter="Vodafone", preis=199.0)]
    assert pruefe(eintraege, _KATALOG)["zahlen"]["ausreisser"] == 0


def test_die_ausreisserschwelle_ist_nicht_scharf_genug_fuer_rabatte():
    """20 Prozent Preisunterschied sind im Handel normal und duerfen nicht
    als Datenfehler gelten."""
    assert AUSREISSER_ANTEIL >= 0.5


# --------------------------------------------------------------------------
# Was die Pruefung NICHT tun darf
# --------------------------------------------------------------------------

def test_der_eingabedatensatz_bleibt_unveraendert():
    """Aussortiert wird fuer Vergleich und Grafik - CSV-Export und
    SKU-Ansicht sehen weiterhin alles."""
    eintraege = [_e(preis=883.0, farbe="blau"), _e(preis=577.0, farbe="grau")]
    vorher = [dict(e) for e in eintraege]
    pruefe(eintraege, _KATALOG)
    assert eintraege == vorher


def test_ein_sauberer_datensatz_meldet_nichts():
    eintraege = [_e(anbieter="o2", preis=849.0),
                 _e(anbieter="Vodafone", preis=869.0),
                 _e(anbieter="freenet", preis=879.0)]
    erg = pruefe(eintraege, _KATALOG)
    assert erg["zahlen"]["befunde"] == 0
    assert erg["zahlen"]["aussortiert"] == 0
    assert len(erg["sauber"]) == 3


# --------------------------------------------------------------------------
# W3: keine Kennzahl darf groesser sein als die Zahl beobachteter Geraete
# --------------------------------------------------------------------------

def test_die_wochenkarte_zaehlt_geraete_und_nicht_listungen():
    """Die Seite meldete am 29.08.2026 "267 Geraete neu im Regal" bei 59
    beobachteten Geraeten. Gezaehlt wurden Listungen - 267 neue GERAETE kann
    es nicht geben, wenn nur 59 ueberhaupt beobachtet werden."""
    from pathlib import Path
    from tempfile import mkdtemp

    from telco_radar.report.geraete_view import _auffaellig
    from telco_radar.analyze.geraete_store import Preishistorie

    # Ein Geraet, drei Anbieter, alle im Fenster erstmals gesehen: das sind
    # drei Listungen und EIN Geraet.
    eintraege = [
        {**_e(anbieter=n), "first_seen": "2026-08-28", "sku_id": f"s-{n}",
         "id": f"{n}--samsung-galaxy-s25-128gb-schwarz"}
        for n in ("o2", "Vodafone", "freenet")
    ]
    historie = Preishistorie(Path(mkdtemp()) / "leer.jsonl")
    erg = _auffaellig(eintraege, historie, _KATALOG, "2026-08-29", laeufe=4)
    assert erg["neu_gelistet_geraete"] == 1
    assert erg["neu_gelistet"] == 3
    text = " ".join(erg["saetze"])
    assert "1 Gerät" in text and "267" not in text


def test_generationen_sind_generationen_und_keine_modelle():
    """Die Seite meldete "o2 fuehrt 54 Generationen" bei 59 beobachteten
    Geraeten insgesamt. Gezaehlt wurden verschiedene `device_id`s.

    Eine Generation ist die Modellreihe eines Herstellers in einem Jahrgang
    (iPhone 17 / iPhone 16 / iPhone 15) - nicht jede Modellvariante. Genau
    darin liegt die Portfolio-Aussage: wer das Vorjahresmodell im Regal
    laesst, hat einen Preiseinstieg, ohne den Preis des neuen Geraets
    anzufassen. Drei Varianten EINES Jahrgangs sind kein Preiseinstieg."""
    from telco_radar.analyze.geraete_lifecycle import portfolio_tiefe

    katalog = Katalog(geraete=[
        Geraet(hersteller="Apple", modell="iPhone 17", generation=17,
               speicher=[256], segment="premium"),
        Geraet(hersteller="Apple", modell="iPhone 17 Pro", generation=17,
               speicher=[256], segment="flagship"),
        Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
               speicher=[256], segment="flagship"),
        Geraet(hersteller="Apple", modell="iPhone 16", generation=16,
               speicher=[256], segment="premium"),
    ])
    eintraege = [
        {**_e(gid=gid), "status": "aktiv"}
        for gid in ("apple-iphone-17", "apple-iphone-17-pro",
                    "apple-iphone-17-pro-max", "apple-iphone-16")
    ]
    tiefe = portfolio_tiefe(eintraege, katalog)[0]
    assert tiefe["modelle_anzahl"] == 4
    assert tiefe["generationen"] == 2, (
        "iPhone 17 / 17 Pro / 17 Pro Max sind EIN Jahrgang, plus iPhone 16")


def test_ein_geraet_ohne_generation_zaehlt_nicht_als_eigene():
    """Ein Katalogeintrag ohne Jahrgang darf keine Generation erfinden -
    sonst zaehlten drei Geraete ohne Angabe als drei Generationen."""
    from telco_radar.analyze.geraete_lifecycle import portfolio_tiefe

    katalog = Katalog(geraete=[
        Geraet(hersteller="Apple", modell="iPhone 17", generation=17,
               speicher=[256], segment="premium"),
        Geraet(hersteller="Nokia", modell="G22", generation=None,
               speicher=[128], segment="einstieg"),
    ])
    eintraege = [{**_e(gid=gid), "status": "aktiv"}
                 for gid in ("apple-iphone-17", "nokia-g22")]
    tiefe = portfolio_tiefe(eintraege, katalog)[0]
    assert tiefe["generationen"] == 1
    assert tiefe["modelle_anzahl"] == 2


def test_keine_kennzahl_ist_groesser_als_die_zahl_beobachteter_geraete():
    """Akzeptanzkriterium der Evaluation vom 29.08.2026. Die Seite meldete
    "267 Geräte neu im Regal" und "o2 54 Generationen" bei 59 beobachteten
    Geraeten - beides arithmetisch ausgeschlossen.

    Der Test prueft die INVARIANTE, nicht die zwei bekannten Stellen: jede
    Kennzahl, die Geraete zaehlt, ist durch die Grundgesamtheit gedeckelt."""
    from pathlib import Path
    from tempfile import mkdtemp

    from telco_radar.analyze.geraete_lifecycle import portfolio_tiefe
    from telco_radar.analyze.geraete_store import Preishistorie
    from telco_radar.report.geraete_view import _auffaellig

    katalog = Katalog(geraete=[
        Geraet(hersteller="Samsung", modell="Galaxy S25", generation=25,
               speicher=[128], segment="premium"),
        Geraet(hersteller="Samsung", modell="Galaxy S26", generation=26,
               speicher=[128], segment="premium"),
    ])
    # Zwei Geraete, vier Anbieter, acht Farben: 64 Listungen, 2 Geraete.
    eintraege = []
    for gid in ("samsung-galaxy-s25", "samsung-galaxy-s26"):
        for anbieter in ("o2", "Vodafone", "freenet", "ALDI TALK"):
            for farbe in range(8):
                eintraege.append({
                    **_e(anbieter=anbieter, gid=gid, farbe=f"farbe{farbe}"),
                    "first_seen": "2026-08-28",
                    "sku_id": f"{gid}-{anbieter}-{farbe}",
                    "id": f"{anbieter}--{gid}-{farbe}",
                })
    beobachtet = len({e["device_id"] for e in eintraege})
    assert beobachtet == 2 and len(eintraege) == 64, "Fixture greift nicht"

    historie = Preishistorie(Path(mkdtemp()) / "leer.jsonl")
    auffaellig = _auffaellig(eintraege, historie, katalog, "2026-08-29",
                             laeufe=4)
    assert auffaellig["neu_gelistet_geraete"] <= beobachtet
    assert auffaellig["verschwunden_geraete"] <= beobachtet
    for t in portfolio_tiefe(eintraege, katalog):
        assert t["generationen"] <= t["modelle_anzahl"] <= beobachtet, t


def test_ein_veralteter_zustand_im_store_faellt_aus_dem_vergleich():
    """Der Store trägt seine alten Werte weiter, bis der Anbieter neu
    gecrawlt wird. Ein Modell, das o2 AUSSCHLIESSLICH gebraucht listet,
    fände kein anderes Netz - es stünde mit dem Gebrauchtpreis allein in der
    Neupreis-Tabelle. Der Zustand wird deshalb gegen den gespeicherten
    Rohtitel neu gerechnet."""
    veraltet = {**_e(preis=577.0),
                "titel_roh": "Samsung Galaxy S25 (erneuert) 128 GB grau erneuert",
                "farbe_normalisiert": "grau erneuert", "zustand": "neu"}
    erg = pruefe([veraltet], _KATALOG)
    assert erg["sauber"] == []
    assert erg["zahlen"]["zustand_veraltet"] == 1
    befund = erg["befunde"][0]
    assert befund["gespeichert"] == "neu" and befund["erkannt"] == "refurbished"


def test_ein_stimmiger_zustand_wird_nicht_angefasst():
    """Gegenprobe: ohne sie wäre eine Prüfung, die jeden Eintrag verwirft,
    grün."""
    gut = {**_e(preis=849.0),
           "titel_roh": "Samsung Galaxy S25 128 GB schwarz",
           "quelle_url": "https://o2.de/p/samsung-galaxy-s25-128gb-schwarz"}
    erg = pruefe([gut], _KATALOG)
    assert len(erg["sauber"]) == 1
    assert erg["zahlen"]["zustand_veraltet"] == 0
