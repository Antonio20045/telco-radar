"""Der Bestand, wie er angezeigt und exportiert wird (31.08.2026).

Zwei Zusicherungen, und die zweite ist die teurere: das Zustandswort faellt
aus der Farbe, und der Zwilling einer umbenannten Listung faellt weg - ohne
dass eine echte Farbvariante mitfaellt. Am Bestand vom 30.08.2026 gemessen
steht der Schluessel dieses Moduls OHNE die Farbe bei 272 statt 360 Zeilen:
eine Regel, die den Unterschied nicht trifft, loescht 88 wahre Zeilen, um
10 falsche zu entfernen.

JEDER Test hier misst, was sein Name behauptet - gepruefte Methode: die
tragende Regel entfernen und nachsehen, dass er durchfaellt. Die neun
Bestandteile des Zwillingsschluessels haben deshalb je einen eigenen Test
mit einem Paar, das sich NUR in diesem einen Feld unterscheidet; auf den
echten Daten ist das bei acht von neun folgenlos, und genau darum steht der
Fall hier gebaut und nicht gemessen.
"""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from telco_radar.geraete_config import lade_katalog
from telco_radar.report.geraete_bereinigung import (_zwillingsschluessel,
                                                    bereinige)
from telco_radar.report.geraete_pruefung import pruefe

_WURZEL = Path(__file__).resolve().parents[1]


def _e(anbieter="o2", gid="apple-iphone-15", speicher=128, farbe_roh="schwarz",
       farbe_norm=None, zustand="refurbished", status="aktiv", preis=613.0,
       zuzahlung=None, tarif=None, url=None, abgerufen="2026-08-30",
       titel=None, first_seen="2026-08-30", kennung=None):
    return {
        "id": kennung or f"{anbieter}--{gid}-{speicher}-{farbe_roh}",
        "anbieter": anbieter, "device_id": gid, "speicher_gb": speicher,
        "farbe_roh": farbe_roh, "farbe_normalisiert": farbe_norm,
        "zustand": zustand, "status": status, "preis_ohne_vertrag": preis,
        "zuzahlung": zuzahlung, "tarif_referenz": tarif,
        "quelle_url": url or f"https://www.o2online.de/e-shop/{gid}-details",
        "abgerufen_am": abgerufen, "titel_roh": titel or "",
        "first_seen": first_seen,
    }


def _farben(eintraege):
    return sorted(e["farbe_normalisiert"] or e["farbe_roh"] for e in eintraege)


def _beide_bleiben(a, b):
    """Zwei Zeilen, die sich in genau einem Schluesselfeld unterscheiden,
    sind zwei Angebote. Die Gegenprobe steht mit im Test: ohne den
    Unterschied waeren es Zwillinge - sonst waere die Zusicherung auch dann
    erfuellt, wenn das Feld gar nichts bewirkt."""
    assert len(bereinige([a, b])) == 2, "Unterschied wurde eingeebnet"
    zwilling = deepcopy(b)
    for feld, wert in a.items():
        if feld != "id":
            zwilling[feld] = wert
    assert len(bereinige([a, zwilling])) == 1, (
        "der Fall loest gar keine Zusammenfassung aus - der Test misst nichts")


# --------------------------------------------------------------------------
# 1. Die Farbe ohne Zustandswort
# --------------------------------------------------------------------------

def test_das_zustandswort_faellt_aus_der_rohfarbe():
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


@pytest.mark.parametrize("farbe", [
    "Titanium Black",
    # Der Fall, an dem die unbedingte Interpunktionsreinigung eine Farbe
    # beschaedigt hat, die nie ein Kennzeichen trug. Steht so im Livebestand
    # (mobilcom-debitel, Galaxy S25 128 GB).
    "Silver Shadow (Enterprise Edition)",
    "Blau/Grau",
    "sunset-gold",
])
def test_eine_farbe_ohne_zustandswort_bleibt_zeichengenau_stehen(farbe):
    (raus,) = bereinige([_e(farbe_roh=farbe, farbe_norm=farbe)])
    assert raus["farbe_roh"] == farbe
    assert raus["farbe_normalisiert"] == farbe


def test_eine_farbe_die_nur_aus_dem_zustandswort_besteht_bleibt_stehen():
    """`ohne_zustandswort` gibt die Farbe unveraendert zurueck, wenn nichts
    uebrig bliebe - eine geleerte Farbe verloere die Dimension. Hier
    festgehalten, weil die Anzeige sonst eine leere Zelle zeigte."""
    (raus,) = bereinige([_e(farbe_roh="erneuert")])
    assert raus["farbe_roh"] == "erneuert"


# --------------------------------------------------------------------------
# 2. Zwillinge - und die Reihenfolge der zwei Schritte
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


def test_erst_die_farbe_bereinigen_dann_die_zwillinge_suchen():
    """Die Reihenfolge der zwei Schritte ist die halbe Mechanik: ROH sind
    die beiden Zeilen zwei verschiedene Schluessel, und nur weil Schritt 1
    vorher laeuft, treffen sie sich. Liefe die Zwillingssuche zuerst, waere
    die zweite Zusicherung dieses Moduls stumm abgeschaltet."""
    alt = _e(farbe_roh="mitternacht erneuert", status="vermutlich ausgelistet",
             abgerufen="2026-08-29")
    neu = _e(farbe_roh="mitternacht", farbe_norm="schwarz")
    assert _zwillingsschluessel(alt) != _zwillingsschluessel(neu)
    assert len(bereinige([alt, neu])) == 1


def test_der_aktive_eintrag_ueberlebt_den_gealterten():
    alt = _e(farbe_roh="blau erneuert", status="vermutlich ausgelistet",
             abgerufen="2026-08-31", kennung="alt")
    neu = _e(farbe_roh="blau", status="aktiv", abgerufen="2026-08-29",
             kennung="neu")
    # Das juengere Datum liegt absichtlich beim GEALTERTEN: sonst gewaenne
    # der aktive Eintrag auch ohne die Statusregel.
    for reihenfolge in ([alt, neu], [neu, alt]):
        (raus,) = bereinige(reihenfolge)
        assert raus["id"] == "neu"


def test_bei_gleichem_status_gewinnt_das_juengere_abrufdatum():
    frueh = _e(farbe_roh="blau erneuert", abgerufen="2026-08-29", kennung="frueh")
    spaet = _e(farbe_roh="blau", abgerufen="2026-08-30", kennung="spaet")
    for reihenfolge in ([frueh, spaet], [spaet, frueh]):
        (raus,) = bereinige(reihenfolge)
        assert raus["id"] == "spaet"


def test_der_ueberlebende_erbt_das_fruehere_first_seen():
    """Eine umbenannte Listung ist nicht neu. Ohne diese Zeile zaehlte die
    Verweildauer im Portfolio-Reiter jede Umbenennung als Zugang - genau der
    Schaden, den das Bereinigen beim Lesen vermeiden soll."""
    alt = _e(farbe_roh="mitternacht erneuert", status="vermutlich ausgelistet",
             abgerufen="2026-08-29", first_seen="2026-08-12")
    neu = _e(farbe_roh="mitternacht", first_seen="2026-08-30")
    (raus,) = bereinige([alt, neu])
    assert raus["first_seen"] == "2026-08-12"


def test_die_kennung_des_aufgeloesten_zwillings_bleibt_auffindbar():
    """Seine Preispunkte haengen an ihr. Wer sie im Export halten will,
    braucht die Angabe von hier - nur diese Funktion weiss, welche Zeile
    welche abgeloest hat."""
    alt = _e(farbe_roh="mitternacht erneuert", status="vermutlich ausgelistet",
             abgerufen="2026-08-29", kennung="alt")
    neu = _e(farbe_roh="mitternacht", kennung="neu")
    (raus,) = bereinige([alt, neu])
    assert raus["zwilling_ids"] == ["alt"]


def test_eine_einzelne_listung_bekommt_kein_zwillingsfeld():
    """Sonst traegt jede der 358 Zeilen ein leeres Feld, und ein Verbraucher
    kann nicht mehr an seiner Anwesenheit ablesen, dass hier etwas
    zusammengefasst wurde."""
    (raus,) = bereinige([_e()])
    assert "zwilling_ids" not in raus


# --------------------------------------------------------------------------
# Die neun Bestandteile des Schluessels, je einer je Test
# --------------------------------------------------------------------------

def test_zwei_anbieter_sind_zwei_angebote():
    _beide_bleiben(_e(anbieter="o2"), _e(anbieter="Vodafone"))


def test_zwei_geraete_sind_zwei_angebote():
    """Beide unter DERSELBEN Adresse - eine Uebersichtsseite fuehrt mehrere
    Geraete. Mit der Vorgabeadresse (sie traegt die device_id) haetten sich
    die zwei schon an der URL unterschieden, und der Test haette die
    device_id nur behauptet."""
    seite = "https://www.o2online.de/e-shop/apple-details"
    _beide_bleiben(_e(gid="apple-iphone-15", url=seite),
                   _e(gid="apple-iphone-16", url=seite))


def test_zwei_speichergroessen_sind_zwei_angebote():
    _beide_bleiben(_e(speicher=128), _e(speicher=256))


def test_neu_und_gebraucht_sind_zwei_angebote():
    """Unterschieden wird am ABGELEITETEN Zustand: beide Zeilen tragen
    denselben gespeicherten Wert, nur der Titel der einen weist sie als
    Gebrauchtgeraet aus. Ohne die Ableitung im Schluessel faellt der
    Gebrauchtpreis mit dem Neupreis zusammen."""
    _beide_bleiben(
        _e(zustand="neu", titel="Apple iPhone 15 128 GB"),
        _e(zustand="neu", titel="Apple iPhone 15 128 GB (gebraucht)"))


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
    (raus,) = bereinige([alt, neu])
    assert raus["zustand"] == "refurbished"


def test_zwei_barpreise_sind_zwei_angebote():
    """Ein Doppelpreis ist ein Befund fuer `geraete_pruefung`, kein
    Zwilling. Hier still zusammengefasst waere die Zahl verschwunden, die
    dort gemeldet werden soll."""
    _beide_bleiben(_e(preis=613.0), _e(preis=745.0))


def test_zwei_zuzahlungen_sind_zwei_angebote():
    _beide_bleiben(_e(preis=None, zuzahlung=1.0), _e(preis=None, zuzahlung=99.0))


def test_dieselbe_zuzahlung_zu_zwei_tarifen_sind_zwei_angebote():
    _beide_bleiben(_e(preis=None, zuzahlung=1.0, tarif="Blau Allnet L"),
                   _e(preis=None, zuzahlung=1.0, tarif="Blau Allnet XL"))


def test_zwei_adressen_sind_zwei_angebote():
    """Gleiche Farbe, gleicher Preis, verschiedene Adresse: das ist keine
    umbenannte Listung, sondern eine zweite - der Vergleich soll sie
    sehen."""
    _beide_bleiben(_e(url="https://www.o2online.de/e-shop/a-details"),
                   _e(url="https://www.o2online.de/e-shop/b-details"))


def test_zwei_farben_sind_zwei_angebote():
    _beide_bleiben(_e(farbe_roh="Salbei"), _e(farbe_roh="Nebelblau"))


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


def test_eine_farbvariante_ueberlebt_neben_einem_zwillingspaar():
    """Der gemischte Fall - sonst koennte die Regel "immer alles behalten"
    heissen und der Test darueber trotzdem gruen sein."""
    url = "https://www.o2online.de/e-shop/iphone-15-mitternacht-erneuert-details"
    alt = _e(farbe_roh="mitternacht erneuert", status="vermutlich ausgelistet",
             abgerufen="2026-08-29", url=url)
    neu = _e(farbe_roh="mitternacht", farbe_norm="schwarz", url=url)
    andere = _e(farbe_roh="blau", farbe_norm="blau", url=url)
    raus = bereinige([alt, neu, andere])
    assert len(raus) == 2
    assert _farben(raus) == ["blau", "schwarz"]


# --------------------------------------------------------------------------
# Der Store bleibt unangetastet
# --------------------------------------------------------------------------

def test_die_eingabe_wird_nicht_veraendert():
    """Eine geaenderte Farbe im Store aenderte die `sku_id`: der Altbestand
    gaelte als ausgelistet und entstuende neu, Listungsdauer und
    Preisverlauf begaennen bei null. Bereinigt wird beim LESEN."""
    eingabe = [
        _e(farbe_roh="mitternacht erneuert", status="vermutlich ausgelistet",
           abgerufen="2026-08-29", first_seen="2026-08-12"),
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


# --------------------------------------------------------------------------
# Gegen die echten Daten
# --------------------------------------------------------------------------

def _echter_bestand():
    db = json.loads((_WURZEL / "data" / "state" / "geraete_db.json").read_text())
    return [e for e in db["listungen"]
            if e.get("status") in ("aktiv", "vermutlich ausgelistet")]


def test_die_kette_der_auslieferung_am_echten_bestand():
    """Die Zahl, die auf der Seite steht - nicht die dieses Teilstuecks.

    Ausgeliefert wird `geraete_view.geprueft_und_bereinigt()`, also
    `pruefe()` UND DANN `bereinige()`. Beide Zahlen auseinanderzuhalten ist
    der Zweck dieses Tests: `bereinige()` allein nimmt zehn Paare, in der
    Kette sind es acht, weil `pruefe()` zwei Haelften vorher als falsch
    gespeicherten Zustand herauswirft.

    Die Zahlen sind am Bestand vom 30.08.2026 gemessen. Aendert ein
    Nachtlauf den Bestand, faellt dieser Test - und dann gehoert nachgesehen,
    ob die Kette noch dasselbe tut, nicht die Zahl blind nachgezogen. Das
    ist der eine Test, der die echten Daten anfasst; die Zusicherungen
    darunter gelten unabhaengig vom Datenstand.
    """
    sichtbar = _echter_bestand()
    geprueft = pruefe(sichtbar, lade_katalog(_WURZEL))["sauber"]
    fertig = bereinige(geprueft)
    assert (len(sichtbar), len(geprueft), len(fertig)) == (370, 366, 358)
    assert len(bereinige(sichtbar)) == 360


def test_am_echten_bestand_bleibt_keine_farbe_mit_zustandswort():
    fertig = bereinige(_echter_bestand())
    uebrig = [e for e in fertig
              for feld in ("farbe_roh", "farbe_normalisiert")
              if any(wort in str(e.get(feld) or "").lower()
                     for wort in ("erneuert", "gebraucht", "refurbished"))]
    assert uebrig == []


def test_am_echten_bestand_verliert_nur_o2_zeilen():
    """Die Zwillinge stammen alle aus o2s Umbenennung. Faellt hier ein
    anderer Anbieter, hat der Schluessel echte Ware eingeebnet - und das
    faellt sonst erst auf, wenn jemand die Seite mit dem Markt vergleicht."""
    sichtbar = _echter_bestand()
    behalten = {e["id"] for e in bereinige(sichtbar)}
    weg = [e for e in sichtbar if e["id"] not in behalten]
    assert weg, "kein einziger Zwilling gefunden - der Test misst nichts"
    assert {e["anbieter"] for e in weg} == {"o2"}


def test_am_echten_bestand_hat_jede_weggefallene_zeile_ihren_ueberlebenden():
    """Zusammengefasst heisst: die Aussage steht weiterhin da. Zu jeder
    entfernten Zeile muss eine bleiben, die DIESELBE Adresse und DENSELBEN
    Preis traegt - sonst ist eine Preisaussage verschwunden."""
    sichtbar = _echter_bestand()
    fertig = bereinige(sichtbar)
    behalten = {e["id"] for e in fertig}
    geblieben = {(e["quelle_url"], e["preis_ohne_vertrag"]) for e in fertig}
    for weg in (e for e in sichtbar if e["id"] not in behalten):
        assert (weg["quelle_url"], weg["preis_ohne_vertrag"]) in geblieben


def test_am_echten_bestand_ueberleben_die_vodafone_farbvarianten():
    fertig = bereinige(_echter_bestand())
    vf = [e for e in fertig if e["anbieter"] == "Vodafone"
          and e["device_id"] == "apple-iphone-17" and e["speicher_gb"] == 256]
    assert len(vf) == 5
    assert len({e["farbe_roh"] for e in vf}) == 5


def test_am_echten_bestand_bleibt_die_klammerfarbe_unversehrt():
    """Die Gegenprobe zu B1 an echten Daten: `.strip(" -,;/()[]")` lief bis
    zum 31.08.2026 unbedingt und haette diese Zeile verstuemmelt
    ausgeliefert."""
    farben = {e.get("farbe_roh") for e in bereinige(_echter_bestand())}
    assert "Silver Shadow (Enterprise Edition)" in farben
