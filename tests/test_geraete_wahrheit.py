"""Die Preiswahrheit des Geraeteradars (B1, 30.08.2026).

Grundlage: `outputs/geraeteradar-wahrheit-2026-08-29.md`. Der Befund, um den
es geht, steht in einem Satz: **Gebrauchtgeraete gewannen den Preisvergleich
gegen unsere Neugeraete.** Bei o2 stand der Gebrauchtzustand nur im
FARBFELD ("grau erneuert"), der Vergleich nahm den niedrigsten Preis, und die
Seite meldete einen Wettbewerbsnachteil, wo ein Vorteil stand.

Die Erkennung war am 29.08.2026 repariert. Was am 30.08.2026 dazukam, hat
erst das Nachrechnen am echten Bestand gezeigt: die Pruefungen liefen
UNABHAENGIG voneinander und vereinigten ihre Streichungen am Ende. Eine
Zeile, die `_zustand_veraltet` bereits verurteilt hatte, stand fuer
`_doppelpreise` trotzdem noch in ihrer Gruppe - und riss den gesunden
Nachbarn mit hinaus.
"""
import pytest

from telco_radar.geraete_model import (Geraet, Katalog, farbschluessel,
                                       zustand_aus_feldern, zustand_aus_titel)
from telco_radar.report import geraete_vergleich
from telco_radar.report.geraete_pruefung import pruefe

_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Samsung", modell="Galaxy S25", generation=25,
           speicher=[128, 256], segment="premium"),
    Geraet(hersteller="Samsung", modell="Galaxy S26 FE", generation=26,
           speicher=[128, 256], segment="premium"),
    Geraet(hersteller="Apple", modell="iPhone 14 Pro", generation=14,
           speicher=[128, 256], segment="flagship"),
])


def _e(gid, preis, farbe_roh, *, kennung, zustand="neu", speicher=128,
       titel="", anbieter="o2"):
    """Eine o2-Listung so, wie sie im Store steht.

    `zustand` ist absichtlich vorbelegt mit "neu": das ist der Fehler, den
    diese Datei beschreibt. Der Store traegt seinen alten Wert weiter, bis
    der naechste erfolgreiche Crawl ihn ueberschreibt.
    """
    return {
        "id": kennung, "anbieter": anbieter, "device_id": gid,
        "speicher_gb": speicher, "zustand": zustand, "status": "aktiv",
        "farbe_roh": farbe_roh, "farbe_normalisiert": None,
        "preis_ohne_vertrag": preis,
        "titel_roh": titel or f"{gid} {speicher} GB {farbe_roh}",
        "quelle_url": f"https://www.o2online.de/p/{kennung}",
        "abgerufen_am": "2026-08-29",
    }


# --------------------------------------------------------------------------
# Die zwei Regressionsfaelle aus dem Auftrag
# --------------------------------------------------------------------------

# (Geraet, Speicher, Gebrauchtpreis, Farbschreibweise, echter Neupreis)
_FAELLE = [
    ("samsung-galaxy-s25", 128, 577.0, "grau erneuert", 883.0),
    ("apple-iphone-14-pro", 128, 577.0, "space schwarz erneuert", 1225.0),
]


@pytest.mark.parametrize("gid,gb,gebraucht,farbe,neu", _FAELLE)
def test_ein_gebrauchtgeraet_gewinnt_keinen_neupreisvergleich(gid, gb,
                                                              gebraucht,
                                                              farbe, neu):
    """Der Kernfall. Das Kennzeichen steht NUR in der Farbe, und der
    gespeicherte Zustand sagt "neu" - trotzdem darf der Gebrauchtpreis
    nicht in den Vergleich."""
    eintraege = [
        _e(gid, neu, "navy", kennung="echt", speicher=gb),
        _e(gid, gebraucht, farbe, kennung="gebraucht", speicher=gb),
    ]
    sauber = {e["id"] for e in pruefe(eintraege, _KATALOG)["sauber"]}
    assert "gebraucht" not in sauber, (
        f"{gebraucht} EUR ist ein Gebrauchtpreis und stand als Sieger auf der Seite")


@pytest.mark.parametrize("gid,gb,gebraucht,farbe,neu", _FAELLE)
def test_der_echte_neupreis_ueberlebt_seinen_gebrauchten_nachbarn(gid, gb,
                                                                  gebraucht,
                                                                  farbe, neu):
    """Der teuerste Nebeneffekt, und er war unsichtbar.

    Bis zum 30.08.2026 liefen die Pruefungen unabhaengig: `_zustand_veraltet`
    verurteilte die Gebrauchtzeile, `_doppelpreise` sah sie aber trotzdem in
    ihrer Gruppe, fand zwei Preise und warf BEIDE hinaus. Damit verschwand
    o2s echter Neupreis aus dem Vergleich - die Seite konnte die richtige
    Aussage ("o2 ist teurer als wir") gar nicht mehr treffen, und im
    Pruefbericht sah es nach sauberer Arbeit aus.
    """
    eintraege = [
        _e(gid, neu, "navy", kennung="echt", speicher=gb),
        _e(gid, gebraucht, farbe, kennung="gebraucht", speicher=gb),
    ]
    erg = pruefe(eintraege, _KATALOG)
    sauber = {e["id"] for e in erg["sauber"]}
    assert "echt" in sauber, (
        f"der echte Neupreis {neu} EUR wurde von seinem gebrauchten "
        f"Nachbarn mitgerissen")
    assert erg["zahlen"]["doppelpreise"] == 0, (
        "nach der Zustandspruefung steht nur noch ein Preis in der Gruppe - "
        "es gibt keinen Doppelpreis mehr zu finden")


def test_ein_ausschliesslich_gebraucht_gelistetes_geraet_faellt_auch():
    """Ohne Neugeraet daneben findet die Doppelpreisregel nichts - dann traegt
    die Zustandspruefung den Fall allein. Genau dieser Fall hatte bis zum
    29.08.2026 kein Netz unter sich."""
    eintraege = [_e("samsung-galaxy-s25", 577.0, "grau erneuert",
                    kennung="nur-gebraucht")]
    assert pruefe(eintraege, _KATALOG)["sauber"] == []


# --------------------------------------------------------------------------
# Die Farbe als Vergleichsschluessel
# --------------------------------------------------------------------------

def test_ein_kuerzel_am_ende_macht_keine_zweite_farbe():
    """"pistachio" und "pistachio bk" sind ein Geraet (Auftrag, Abschnitt 1).
    Als zwei Farben gelesen waeren die 144 EUR Abstand ein legitimer
    Farbaufschlag, und der Vergleich naehme kommentarlos die 667 EUR."""
    assert farbschluessel(None, "pistachio bk") == farbschluessel(None,
                                                                  "pistachio")


def test_ein_ganzes_wort_am_ende_macht_sehr_wohl_eine_zweite_farbe():
    """Die Laengengrenze ist der ganze Schutz der Regel. Ohne sie waeren
    "titan natur" und "titan schwarz" derselbe Schluessel - zwei echte Farben
    eines Geraets saehen wie ein Doppelpreis aus."""
    assert farbschluessel(None, "titan natur") != farbschluessel(None,
                                                                 "titan schwarz")


def test_zwei_schreibweisen_derselben_farbe_sind_ein_doppelpreis():
    """Der offene Punkt aus CLAUDE.md §8a: zwei o2-Adressen, 144 EUR Abstand,
    beide ohne Vertrag. Als eine Farbe gelesen ist das ein Widerspruch, und
    der Datensatz sagt nicht, welcher Preis stimmt."""
    eintraege = [
        _e("samsung-galaxy-s26-fe", 811.0, "pistachio", kennung="a"),
        _e("samsung-galaxy-s26-fe", 667.0, "pistachio bk", kennung="b"),
    ]
    erg = pruefe(eintraege, _KATALOG)
    assert erg["sauber"] == []
    assert erg["zahlen"]["doppelpreise"] == 1


def test_die_kanonische_farbe_schlaegt_die_rohschreibweise():
    """Kennt `config/farben.yaml` die Schreibweise, entscheidet sie - sonst
    waeren "Navy" und "navy blue" zwei Farben."""
    assert farbschluessel("navy", "Navy Blue") == farbschluessel("navy",
                                                                 "Marineblau")


# --------------------------------------------------------------------------
# Der ausgelieferte Datensatz
# --------------------------------------------------------------------------

def test_der_gepruefte_datensatz_traegt_keine_widersprueche_mehr():
    """Die Zusicherung des Auftrags, Abschnitt 6: null Doppelpreise, null
    Speicherinversionen im ausgelieferten Datensatz.

    Gemessen wird die AUSGABE der Pruefung, nicht der Store - der darf seine
    alten Werte weitertragen, bis der naechste Crawl sie ueberschreibt.
    """
    bestand = [
        _e("samsung-galaxy-s25", 883.0, "navy", kennung="a"),
        _e("samsung-galaxy-s25", 577.0, "grau erneuert", kennung="b"),
        _e("samsung-galaxy-s25", 949.0, "navy", kennung="c", speicher=256),
        _e("apple-iphone-14-pro", 1225.0, "dunkellila", kennung="d"),
        _e("apple-iphone-14-pro", 577.0, "space schwarz erneuert", kennung="e"),
    ]
    sauber = pruefe(bestand, _KATALOG)["sauber"]

    # Gegenprobe: der Fall tritt wirklich ein, sonst misst der Test nichts.
    assert len(sauber) < len(bestand), "die Pruefung greift gar nicht"

    je_farbe: dict[tuple, set] = {}
    je_reihe: dict[tuple, dict] = {}
    for e in sauber:
        farbe = farbschluessel(e.get("farbe_normalisiert"), e["farbe_roh"])
        je_farbe.setdefault(
            (e["anbieter"], e["device_id"], e["speicher_gb"], e["zustand"],
             farbe), set()).add(e["preis_ohne_vertrag"])
        reihe = je_reihe.setdefault((e["anbieter"], e["device_id"],
                                     e["zustand"]), {})
        reihe[e["speicher_gb"]] = min(reihe.get(e["speicher_gb"], 1e9),
                                      e["preis_ohne_vertrag"])

    assert all(len(p) == 1 for p in je_farbe.values()), "Doppelpreis geblieben"
    for stufen in je_reihe.values():
        sortiert = sorted(stufen)
        for klein, gross in zip(sortiert, sortiert[1:]):
            assert stufen[gross] >= stufen[klein], "Speicherinversion geblieben"


# --------------------------------------------------------------------------
# Der Zustand steht nicht immer im Titel
# --------------------------------------------------------------------------

@pytest.mark.parametrize("feld,wert", [
    ("Farbe", "space schwarz erneuert"),
    ("itemCondition", "https://schema.org/RefurbishedCondition"),
    ("Kategoriepfad", "Startseite / Gebrauchte Handys"),
    ("Rubrik", "Erneuerte Geräte"),
])
def test_ein_kennzeichen_zaehlt_egal_in_welchem_feld_es_steht(feld, wert):
    """Der Auftrag, Abschnitt 1: die Wörter schlagen durch, egal in welchem
    Feld sie stehen. o2 schrieb "erneuert" AUSSCHLIESSLICH in die Farbe."""
    assert zustand_aus_feldern("Apple iPhone 14 Pro 128 GB", wert) != "neu", feld


@pytest.mark.parametrize("titel", [
    "Gebrauchsanweisung liegt bei",
    "iPhone 17 Erneuerbare Energien Edition",
    "Neuheit im Sortiment",
    "Refurbishment-Programm ab 2027",
])
def test_die_gebeugten_formen_sind_keine_praefixsuche(titel):
    """Die Beugungsregel haengt Endungen an, sie sucht keinen Praefix. Sonst
    faenge "gebraucht" das Wort "Gebrauchsanweisung" und "erneuert" das Wort
    "Erneuerbare" - und ein Neugeraet fiele als Gebrauchtware aus dem
    Vergleich, ohne dass es jemand merkt."""
    assert zustand_aus_titel(titel) == "neu"


def test_ein_unklares_kennzeichen_wird_nicht_zu_neu_geraten():
    """"Nicht sicher bestimmbar heißt zustand: unbekannt und fällt aus dem
    Vergleich. Nie neu annehmen." (Auftrag, Abschnitt 1)

    Gemessen wird am VERGLEICH, nicht an `pruefe`: die Pruefung gibt in
    `sauber` bewusst auch Zeilen zurueck, die sie gar nicht angesehen hat -
    ein unklarer oder gebrauchter Zustand soll im CSV-Export und in der
    Geraeteansicht stehen bleiben. Wer hier gegen `sauber` prueft, prueft
    eine Zusicherung, die diese Funktion nie gegeben hat.
    """
    assert zustand_aus_feldern("iPhone 15 128 GB", "schwarz neuwertig") == "unbekannt"

    billiger_aber_unklar = _e("samsung-galaxy-s25", 399.0, "schwarz",
                              kennung="unklar", zustand="unbekannt")
    eintraege = [
        _e("samsung-galaxy-s25", 849.90, "navy", kennung="wir",
           anbieter="Vodafone"),
        billiger_aber_unklar,
    ]
    def guenstiger(zustand: str) -> set:
        billiger_aber_unklar["zustand"] = zustand
        erg = geraete_vergleich.vergleich(eintraege, _KATALOG)
        return {a["anbieter"] for z in erg["zeilen"]
                for a in z.get("guenstiger", [])}

    # Gegenprobe zuerst: als Neugeraet WUERDE o2 den Vergleich gewinnen. Ohne
    # sie misst der Test nur, dass ein Schluessel fehlt - genau die Falle aus
    # CLAUDE.md, in die die erste Fassung dieses Tests auch gelaufen ist
    # (sie fragte nach "alle", und den Schluessel gibt es nicht).
    assert guenstiger("neu") == {"o2"}, "die Fixture spannt den Fall nicht auf"
    assert guenstiger("unbekannt") == set(), (
        "der niedrigste Preis ist der wahrscheinlichste Fehler - ein Zustand, "
        "den die Quelle nicht deckt, darf keinen Vergleich gewinnen")
    assert guenstiger("refurbished") == set()
