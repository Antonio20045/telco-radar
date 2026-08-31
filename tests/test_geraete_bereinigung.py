"""Der Bestand, wie er angezeigt und exportiert wird (31.08.2026).

Zwei Zusicherungen, und die zweite ist die teurere: das Zustandswort faellt
aus der Farbe, und der Zwilling einer umbenannten Listung faellt weg - ohne
dass eine echte Farbvariante mitfaellt. Am Bestand vom 30.08.2026 gemessen
stehen 10 Zwillingspaare gegen 90 Gruppen gleichpreisiger Farbvarianten:
eine Regel, die den Unterschied nicht trifft, loescht 96 wahre Zeilen, um
10 falsche zu entfernen.
"""
from copy import deepcopy

from telco_radar.report.geraete_bereinigung import bereinige


def _e(anbieter="o2", gid="apple-iphone-15", speicher=128, farbe_roh="schwarz",
       farbe_norm=None, zustand="refurbished", status="aktiv", preis=613.0,
       url=None, abgerufen="2026-08-30", titel=None):
    return {
        "anbieter": anbieter, "device_id": gid, "speicher_gb": speicher,
        "farbe_roh": farbe_roh, "farbe_normalisiert": farbe_norm,
        "zustand": zustand, "status": status, "preis_ohne_vertrag": preis,
        "zuzahlung": None, "tarif_referenz": None,
        "quelle_url": url or f"https://www.o2online.de/e-shop/{gid}-details",
        "abgerufen_am": abgerufen, "titel_roh": titel or "",
    }


def _farben(eintraege):
    return sorted(e["farbe_normalisiert"] or e["farbe_roh"] for e in eintraege)


# --------------------------------------------------------------------------
# 1. Die Farbe ohne Zustandswort
# --------------------------------------------------------------------------

def test_das_zustandswort_faellt_aus_der_rohfarbe():
    """o2 schreibt sein Kennzeichen NUR in die Farbe - dort gelesen, aber
    nicht dort angezeigt."""
    (raus,) = bereinige([_e(farbe_roh="space schwarz erneuert")])
    assert raus["farbe_roh"] == "space schwarz"


def test_das_zustandswort_faellt_auch_aus_der_kanonischen_farbe():
    """Anzeige und Export lesen `farbe_normalisiert or farbe_roh`. Bliebe
    das kanonische Feld ungereinigt, stuende das Wort ueber den Vorrang der
    ersten Haelfte wieder auf der Seite - heute traegt es keins, der naechste
    Adapter kann es."""
    (raus,) = bereinige([_e(farbe_roh="grau erneuert",
                           farbe_norm="grau gebraucht")])
    assert raus["farbe_normalisiert"] == "grau"
    assert raus["farbe_roh"] == "grau"


def test_eine_farbe_ohne_zustandswort_bleibt_wie_sie_ist():
    (raus,) = bereinige([_e(farbe_roh="Titanium Black", farbe_norm="titan-schwarz")])
    assert raus["farbe_roh"] == "Titanium Black"
    assert raus["farbe_normalisiert"] == "titan-schwarz"


def test_eine_farbe_die_nur_aus_dem_zustandswort_besteht_bleibt_stehen():
    """`ohne_zustandswort` gibt die Farbe unveraendert zurueck, wenn nichts
    uebrig bliebe - eine geleerte Farbe verloere die Dimension. Hier
    festgehalten, weil die Anzeige sonst eine leere Zelle zeigte."""
    (raus,) = bereinige([_e(farbe_roh="erneuert")])
    assert raus["farbe_roh"] == "erneuert"


# --------------------------------------------------------------------------
# 2. Zwillinge
# --------------------------------------------------------------------------

def test_der_zwilling_einer_umbenannten_listung_faellt_weg():
    """Der gemessene Regelfall: dieselbe Adresse, derselbe Preis, die alte
    Schreibweise gealtert daneben."""
    alt = _e(farbe_roh="mitternacht erneuert", status="vermutlich ausgelistet",
             abgerufen="2026-08-29", preis=445.0)
    neu = _e(farbe_roh="mitternacht", farbe_norm="schwarz", preis=445.0)
    raus = bereinige([alt, neu])
    assert len(raus) == 1
    assert raus[0]["status"] == "aktiv"


def test_ohne_die_bereinigung_der_farbe_waeren_es_keine_zwillinge():
    """Die Reihenfolge der zwei Schritte ist nicht beliebig: vor dem
    Streichen des Zustandsworts sind die beiden Zeilen zwei Farben. Die
    Gegenprobe steht hier, damit der Test oben nicht aus einem anderen Grund
    gruen ist."""
    alt = _e(farbe_roh="mitternacht erneuert", status="vermutlich ausgelistet",
             abgerufen="2026-08-29")
    neu = _e(farbe_roh="mitternacht", farbe_norm="schwarz")
    assert alt["farbe_roh"] != neu["farbe_roh"]


def test_bei_gleichem_status_gewinnt_das_juengere_abrufdatum():
    frueh = _e(farbe_roh="blau erneuert", abgerufen="2026-08-29")
    spaet = _e(farbe_roh="blau", abgerufen="2026-08-30")
    for reihenfolge in ([frueh, spaet], [spaet, frueh]):
        raus = bereinige(reihenfolge)
        assert len(raus) == 1
        assert raus[0]["abgerufen_am"] == "2026-08-30"


def test_der_gespeicherte_zustand_haelt_den_zwilling_nicht_am_leben():
    """Zwei der zehn gemessenen Paare tragen im Store verschiedene
    Zustaende: die gealterte Zeile sagt "neu", die aktive "refurbished" -
    derselbe Artikel unter derselben Adresse `...-erneuert-details`. Auf den
    GESPEICHERTEN Zustand geschluesselt blieben genau die zwei stehen, bei
    denen die falsche Haelfte als Neugeraet in den Preisvergleich ginge."""
    url = ("https://www.o2online.de/e-shop/apple/"
           "apple-iphone-14-pro-128gb-space-schwarz-erneuert-details")
    alt = _e(gid="apple-iphone-14-pro", farbe_roh="space schwarz erneuert",
             zustand="neu", status="vermutlich ausgelistet",
             abgerufen="2026-08-29", preis=577.0, url=url)
    neu = _e(gid="apple-iphone-14-pro", farbe_roh="space schwarz",
             zustand="refurbished", preis=577.0, url=url)
    raus = bereinige([alt, neu])
    assert len(raus) == 1
    assert raus[0]["zustand"] == "refurbished"


def test_zwei_zustaende_derselben_farbe_sind_keine_zwillinge():
    """Neu- und Gebrauchtpreis sind zwei Preise. Sie stehen unter
    verschiedenen Adressen und tragen verschiedene abgeleitete Zustaende -
    beide bleiben."""
    neu = _e(farbe_roh="schwarz", zustand="neu", preis=899.0,
             url="https://www.o2online.de/e-shop/iphone-15-schwarz-details")
    gebraucht = _e(farbe_roh="schwarz erneuert", zustand="refurbished",
                   preis=613.0,
                   url="https://www.o2online.de/e-shop/iphone-15-schwarz-erneuert-details")
    assert len(bereinige([neu, gebraucht])) == 2


# --------------------------------------------------------------------------
# Die Falle: echte Farbvarianten
# --------------------------------------------------------------------------

def test_fuenf_vodafone_farbvarianten_ueberleben_alle():
    """Vodafone fuehrt das iPhone 17 256 GB in fuenf Farben zu identischen
    949,90 EUR - unter EINER Produktadresse. Die naheliegende
    Unterscheidung "echte Varianten haben verschiedene quelle_url" traegt
    also nicht; was sie trennt, ist die Farbe selbst."""
    url = "https://www.vodafone.de/privat/handys/iphone-17.html"
    varianten = [
        _e(anbieter="Vodafone", gid="apple-iphone-17", speicher=256,
           farbe_roh=farbe, zustand="neu", preis=949.9, url=url)
        for farbe in ("Salbei", "Nebelblau", "Schwarz", "Lavendel", "Weiß")
    ]
    raus = bereinige(varianten)
    assert len(raus) == 5
    assert _farben(raus) == sorted(["Salbei", "Nebelblau", "Schwarz",
                                    "Lavendel", "Weiß"])


def test_eine_farbvariante_ueberlebt_auch_neben_einem_zwillingspaar():
    """Der gemischte Fall - sonst koennte die Regel "immer alles behalten"
    heissen und der Test oben trotzdem gruen sein."""
    url = "https://www.o2online.de/e-shop/iphone-15-mitternacht-erneuert-details"
    alt = _e(farbe_roh="mitternacht erneuert", status="vermutlich ausgelistet",
             abgerufen="2026-08-29", url=url)
    neu = _e(farbe_roh="mitternacht", farbe_norm="schwarz", url=url)
    andere = _e(farbe_roh="blau", farbe_norm="blau",
                url="https://www.o2online.de/e-shop/iphone-15-blau-erneuert-details")
    raus = bereinige([alt, neu, andere])
    assert len(raus) == 2
    assert _farben(raus) == ["blau", "schwarz"]


def test_zwei_adressen_sind_zwei_angebote():
    """Gleiche Farbe, gleicher Preis, verschiedene Adresse: das ist keine
    umbenannte Listung, sondern eine zweite - der Vergleich soll sie
    sehen."""
    a = _e(farbe_roh="schwarz", url="https://www.o2online.de/e-shop/a-details")
    b = _e(farbe_roh="schwarz", url="https://www.o2online.de/e-shop/b-details")
    assert len(bereinige([a, b])) == 2


def test_verschiedene_preise_unter_derselben_adresse_bleiben_beide():
    """Ein Doppelpreis ist ein Befund fuer `geraete_pruefung`, kein Zwilling.
    Hier still zusammengefasst waere die Zahl verschwunden, die dort
    gemeldet werden soll."""
    a = _e(farbe_roh="schwarz", preis=613.0)
    b = _e(farbe_roh="schwarz", preis=745.0)
    assert len(bereinige([a, b])) == 2


# --------------------------------------------------------------------------
# Der Store bleibt unangetastet
# --------------------------------------------------------------------------

def test_die_eingabe_wird_nicht_veraendert():
    """Eine geaenderte Farbe im Store aenderte die `sku_id`: der Altbestand
    gaelte als ausgelistet und entstuende neu, Listungsdauer und
    Preisverlauf begaennen bei null. Bereinigt wird beim LESEN."""
    eingabe = [
        _e(farbe_roh="mitternacht erneuert", status="vermutlich ausgelistet",
           abgerufen="2026-08-29"),
        _e(farbe_roh="mitternacht", farbe_norm="schwarz"),
    ]
    vorher = deepcopy(eingabe)
    bereinige(eingabe)
    assert eingabe == vorher


def test_das_ergebnis_teilt_seine_dicts_nicht_mit_der_eingabe():
    """Auch ohne etwas zu streichen wird kopiert - sonst traefe ein
    Aufrufer, der das Ergebnis nachtraeglich anfasst, je nach Datenlage mal
    den Store und mal nicht."""
    eingabe = [_e(farbe_roh="schwarz")]
    (raus,) = bereinige(eingabe)
    raus["farbe_roh"] = "geaendert"
    assert eingabe[0]["farbe_roh"] == "schwarz"


def test_die_reihenfolge_der_eingabe_bleibt():
    eingabe = [_e(gid="apple-iphone-17", farbe_roh="schwarz"),
               _e(gid="apple-iphone-15", farbe_roh="blau"),
               _e(gid="apple-iphone-16", farbe_roh="weiss")]
    assert [e["device_id"] for e in bereinige(eingabe)] == [
        "apple-iphone-17", "apple-iphone-15", "apple-iphone-16"]


def test_ein_leerer_bestand_bleibt_leer():
    assert bereinige([]) == []
