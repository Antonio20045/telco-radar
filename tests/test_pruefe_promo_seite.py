"""Der Abnahme-Check fuer Promo-Seiten muss selbst geprueft sein.

Gleiche Begruendung wie bei tests/test_pruefe_quellenvorschlag.py: er ist die
einzige Instanz, die im Ausbau dieser Rubrik "ja" sagen darf. Ein Fehler hier
laesst genau die Seiten durch, gegen die er gebaut wurde - Dubletten der
Startseite, Ratgebertexte ohne Angebot, Festnetzseiten.

Besonders scharf geprueft wird der Ueberlappungswert. Er hat im Presse-Zweig
schon einmal falsch gerechnet (gegen die Kandidatenmenge statt gegen die
kleinere), und 15 von 34 "bestandenen" Quellen waren daraufhin Varianten
bereits konfigurierter.

Kein Netz - fetch_snapshot wird ersetzt.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[1] / "scripts" / "pruefe_promo_seite.py"
_spec = importlib.util.spec_from_file_location("pruefe_promo_seite", _PFAD)
pp = importlib.util.module_from_spec(_spec)
sys.modules["pruefe_promo_seite"] = pp
_spec.loader.exec_module(pp)


# Ein Text, der alle Formkriterien erfuellt: lang genug, viele verschiedene
# Angebotssignale, eindeutig Mobilfunk. Der Fuellteil ist bewusst wortREICH:
# der Ueberlappungswert verweigert die Auskunft, wenn eine der beiden Seiten
# unter MIN_WOERTER_VERGLEICH eigene Woerter hat - eine echte Aktionsseite
# liegt bei mehreren hundert, ein viermal wiederholter Absatz nicht.
GUT = ("Handytarife Aktion Sommer. Allnet Flat mit 30 GB fuer 19,99 EUR "
       "monatlich statt 29,99 EUR. Wechselbonus 50 EUR fuer Neukunden mit "
       "Rufnummernmitnahme. Der Aktionspreis gilt nur bis zum 30.09.2026. "
       "Smartphone mit Vertrag im 5G Netz, eSIM kostenlos dazu, Prepaid "
       "Startguthaben geschenkt. Tarif ohne Laufzeit, Rabatt auf die "
       "Grundgebuehr, sparen Sie 120 EUR im ersten Jahr. "
       + " ".join(f"produkt{i} leistung{i} baustein{i}" for i in range(90)))


def _snap(text=GUT, links=3, images=2):
    return {"text": text,
            "links": [{"href": f"https://marke.test/a{i}", "text": "x"}
                      for i in range(links)],
            "images": [{"src": f"https://marke.test/b{i}.jpg"} for i in range(images)],
            "image_url": None}


def _bestand(seiten=None, unerreichbar=None, konfiguriert=None):
    return {"leitseite": "https://marke.test/aktionen",
            "seiten": seiten or {},
            "unerreichbar": unerreichbar or [],
            "konfiguriert": konfiguriert or set()}


def _pruefe(url="https://marke.test/handys", snap=None, bestand=None, snap2=None):
    geholt = {"kandidat": {"marke": "Marke", "url": url, "kind": "static"},
              "snap": snap or _snap()}
    if snap2 is not None:
        geholt["snap2"] = snap2
    return pp.bewerte_kandidat(geholt, bestand or _bestand())


def _fehler(ergebnis) -> set[str]:
    return {k["name"] for k in ergebnis["kriterien"] if not k["ok"]}


# --------------------------------------------------------------- Grundfall
def test_gute_seite_besteht():
    assert _pruefe()["pass"] is True


def test_abrufmisserfolg_ist_ein_durchfaller_kein_absturz():
    e = pp.bewerte_kandidat(
        {"kandidat": {"marke": "M", "url": "https://marke.test/x"},
         "fehler": "HTTPStatusError: 404"}, _bestand())
    assert e["pass"] is False
    assert _fehler(e) == {"abrufbar"}


# ---------------------------------------------------------- Einzelkriterien
def test_zu_wenig_text_faellt_durch():
    e = _pruefe(snap=_snap("Aktion 19,99 EUR monatlich 30 GB Rabatt"))
    assert "genug Text" in _fehler(e)


def test_markenprosa_ohne_angebot_faellt_durch():
    prosa = ("Wir sind ein Unternehmen mit langer Geschichte und einem klaren "
             "Auftrag. Unser Netz verbindet Menschen in ganz Deutschland. "
             "Nachhaltigkeit ist uns wichtig, ebenso die Zufriedenheit "
             "unserer Kundinnen und Kunden im Mobilfunk. ") * 8
    e = _pruefe(snap=_snap(prosa))
    assert "Angebotssignale" in _fehler(e)


def test_festnetzseite_faellt_durch():
    fest = ("Glasfaser und DSL fuer Zuhause. Der Kabel Internet Anschluss mit "
            "1000 Mbit fuer 39,99 EUR monatlich, Router inklusive, "
            "FritzBox gratis. MagentaZuhause Aktion: Rabatt auf den "
            "Hausanschluss, sparen Sie bis zum 30.09.2026. Internet fuer "
            "zuhause mit Glasfaser, Festnetz Flat inklusive. ") * 6
    e = _pruefe(snap=_snap(fest))
    assert "Mobilfunk statt Festnetz" in _fehler(e)


def test_fremde_domain_faellt_durch():
    """Die Quellen-Unterseite sagt zu, dass jede Zeile die EIGENE Seite des
    Anbieters ist. Ein Vergleichsportal darf hier nie durchrutschen."""
    e = _pruefe(url="https://www.check24.de/handytarife/marke")
    assert "eigene Domain der Marke" in _fehler(e)


def test_subdomain_derselben_marke_ist_in_ordnung():
    e = _pruefe(url="https://shop.marke.test/handys")
    assert "eigene Domain der Marke" not in _fehler(e)


def test_bereits_konfigurierte_seite_faellt_durch():
    e = _pruefe(url="https://marke.test/handys",
                bestand=_bestand(konfiguriert={"marke.test/handys"}))
    assert "noch nicht konfiguriert" in _fehler(e)


def test_schraegstrich_und_www_taeuschen_die_dublettenpruefung_nicht():
    e = _pruefe(url="https://www.marke.test/handys/",
                bestand=_bestand(konfiguriert={"marke.test/handys"}))
    assert "noch nicht konfiguriert" in _fehler(e)


# ------------------------------------------------- Kriterium 7: Eigenstaendig
def test_dublette_einer_bestehenden_seite_faellt_durch():
    e = _pruefe(bestand=_bestand(seiten={"https://marke.test/aktionen": GUT}))
    assert "eigenstaendig" in _fehler(e)


def test_seite_die_eine_bestehende_enthaelt_faellt_durch():
    """Der Fehler aus Session 5: gegen die Vereinigung oder gegen die
    Kandidatenmenge gerechnet sieht eine Seite, die eine bestehende
    VOLLSTAENDIG enthaelt, faelschlich neu aus. Gerechnet wird gegen die
    kleinere Menge."""
    kleiner = GUT[:len(GUT) // 3]
    e = _pruefe(snap=_snap(GUT + " Zusaetzlich noch viele weitere Woerter, die "
                                 "es auf der bestehenden Seite gar nicht gibt. " * 20),
                bestand=_bestand(seiten={"https://marke.test/aktionen": kleiner}))
    assert "eigenstaendig" in _fehler(e)


def test_wirklich_andere_seite_besteht():
    # Wortreich genug fuer einen belastbaren Vergleich (echte Aktionsseiten
    # liegen bei mehreren hundert verschiedenen Woertern) und inhaltlich
    # klar etwas anderes als GUT.
    anders = ("Prepaid Startpaket ohne Vertrag. 10 GB fuer 7,99 EUR im Monat, "
              "Guthaben aufladen im Laden. Aktion: doppeltes Datenvolumen "
              "bis zum 15.10.2026 geschenkt fuer Neukunden im Prepaid Tarif. "
              + " ".join(f"stichwort{i} begriff{i} merkmal{i}" for i in range(90)))
    e = _pruefe(snap=_snap(anders),
                bestand=_bestand(seiten={"https://marke.test/aktionen": GUT}))
    assert "eigenstaendig" not in _fehler(e)


def test_duenner_kandidat_gilt_als_nicht_vergleichbar():
    """Die Kehrseite: eine Seite mit zu wenig eigenem Wortschatz laesst sich
    gegen nichts halten - und "nicht pruefbar" ist kein PASS."""
    duenn = "Aktion 19,99 EUR monatlich 30 GB Rabatt Bonus Tarif " * 12
    e = _pruefe(snap=_snap(duenn),
                bestand=_bestand(seiten={"https://marke.test/aktionen": GUT}))
    assert "eigenstaendig" in _fehler(e)


def test_nicht_abrufbare_bestandsseiten_sind_kein_bestehen():
    """"Nicht pruefbar" ist kein PASS. Waeren die Bestandsseiten einer Marke
    gerade nicht erreichbar, haette Kriterium 7 nichts zu vergleichen - und
    jeder Kandidat kaeme ungeprueft durch."""
    e = _pruefe(bestand=_bestand(unerreichbar=["https://marke.test/aktionen"]))
    assert "eigenstaendig" in _fehler(e)


def test_erste_seite_einer_marke_darf_bestehen():
    e = _pruefe(bestand=_bestand())
    assert "eigenstaendig" not in _fehler(e)


def test_angenommener_kandidat_entlarvt_seinen_zwilling():
    """Ohne diesen Vergleich bestuenden prepaid-allnet-s/m/l/xl alle vier:
    jeder unterscheidet sich vom Bestand, untereinander sind sie dasselbe."""
    e = _pruefe(bestand={**_bestand(), "angenommen": {"https://marke.test/x": GUT}})
    assert "eigenstaendig" in _fehler(e)


def test_zu_duenne_seiten_gelten_als_nicht_vergleichbar():
    assert pp.ueberlappung("kurz und knapp", GUT) == -1.0
    e = _pruefe(bestand=_bestand(seiten={"https://marke.test/aktionen": "zu kurz"}))
    assert "eigenstaendig" in _fehler(e)


# ------------------------------------------------- Kriterium 8: zweimal stabil
def test_zweiter_leerer_abruf_faellt_durch():
    """Die Lehre aus newswire.ca im Presse-Zweig, hier mit anderer Folge: ein
    leerer Abruf schiebt saemtliche Angebote dieser Seite in Richtung
    'ausgelaufen'."""
    e = _pruefe(snap2={"text": ""})
    assert "zweimal stabil" in _fehler(e)


def test_zweiter_guter_abruf_besteht():
    e = _pruefe(snap2=_snap())
    assert e["pass"] is True


def test_ohne_zweiten_abruf_gibt_es_das_kriterium_nicht():
    assert {k["nr"] for k in _pruefe()["kriterien"]} == {1, 2, 3, 4, 5, 6, 7}


# ------------------------------------------------------------- Hilfsfunktionen
def test_angebotsbreite_zaehlt_verschiedene_werte():
    preise, gb = pp.angebotsbreite("9,99 € und 9,99 € und 19,99 EUR, 30 GB, 5 GB")
    assert (preise, gb) == (2, 2)


def test_signale_zaehlen_je_art_nur_einmal():
    viele = "Angebot Angebot Angebot Aktion Deal"
    assert pp.signale(viele) == ["aktion"]


def test_registrable_domain():
    assert pp._registrable("www.marke.test") == "marke.test"
    assert pp._registrable("shop.sub.marke.test") == "marke.test"
    assert pp._registrable("marke.test") == "marke.test"
