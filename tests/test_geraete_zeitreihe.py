"""Der Zeitreihen-Block: der neue Hauptgraph der TCO-Ansicht.

BRIEF_ZEITREIHE (05.09.2026). Vier Abnahmekriterien, vier Testgruppen:

  a. eine Linie nur ab zwei Messpunkten
  b. eine Sammelluecke wird nicht ueberbrueckt - "Linien enden und
     beginnen neu"
  c. die Y-Achse rechnet aus den echten Daten, nicht aus einer Konstante
  d. ein einzelner Messpunkt bleibt ein Punkt, nie eine Linie

Geprueft wird hier die RECHNUNG und das erzeugte SVG-Markup als Text -
dieselbe Ebene wie `tests/test_geraete_verlauf.py` und
`tests/test_geraete_tco_hauptansicht.py`. Dass die Grafik im ECHTEN Browser
zwei sichtbare `<svg>` in der Hauptansicht ergibt (G0 und G1), misst
`tests/test_geraete_reiter_browser.py`.
"""
from __future__ import annotations

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_tco_grafik as grafik
from telco_radar.report import geraete_verlauf as verlauf

_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Apple", modell="iPhone 17 Pro", generation=17,
           speicher=[256], segment="premium"),
])
_GID = "apple-iphone-17-pro"


class _Historie:
    """Nur die eine Methode, die `_punkte` benutzt - wie in
    `tests/test_geraete_verlauf.py`."""

    def __init__(self, reihen=None):
        self._reihen = reihen or {}

    def reihe(self, listung_id):
        return sorted(self._reihen.get(listung_id, []),
                      key=lambda s: s.get("datum", ""))


def _l(kennung, anbieter, preis, *, last_verified="2026-09-05",
       speicher=256, zustand="neu"):
    return {"id": kennung, "anbieter": anbieter, "device_id": _GID,
            "speicher_gb": speicher, "zustand": zustand,
            "preis_ohne_vertrag": preis, "last_verified": last_verified,
            "farbe_normalisiert": "titan"}


def _reihe(anbieter, punkte, farbe="#123456", eigen=False):
    """Eine fertige Reihe, wie sie `geraete_verlauf._reihen` liefert -
    fuer die Tests, die direkt gegen `zeitreihe()` messen und keine
    Listungen/Historie brauchen."""
    return {"anbieter": anbieter, "farbe": farbe, "eigen": eigen,
            "punkte": [{"datum": d, "preis": p} for d, p in punkte]}


# --------------------------------------------------------------------------
# reihen_fuer_listungen - die Filterung vor der Grafik
# --------------------------------------------------------------------------

def test_reihen_fuer_listungen_laesst_gebrauchte_geraete_weg():
    hist = _Historie({"a": [{"datum": "2026-08-29", "preis_ohne_vertrag": 900.0}]})
    listungen = [_l("a", "o2", 899.0, zustand="refurbished")]
    reihen = verlauf.reihen_fuer_listungen(listungen, hist)
    assert reihen == []


def test_reihen_fuer_listungen_laesst_buendel_ohne_barpreis_weg():
    """Ein Buendel-Eintrag ohne `preis_ohne_vertrag` (nur Zuzahlung) ist
    keine Zeile dieser Grafik - sie zeigt den Gerätepreis ohne Vertrag,
    keinen Buendelbestandteil."""
    hist = _Historie()
    listungen = [{"id": "b", "anbieter": "1&1", "device_id": _GID,
                 "speicher_gb": 256, "zustand": "neu",
                 "preis_ohne_vertrag": None, "last_verified": "2026-09-05"}]
    assert verlauf.reihen_fuer_listungen(listungen, hist) == []


def test_reihen_fuer_listungen_baut_reihen_aus_listung_und_historie():
    hist = _Historie({"a": [{"datum": "2026-08-29", "preis_ohne_vertrag": 1315.0}]})
    listungen = [_l("a", "o2", 1315.0, last_verified="2026-09-05")]
    reihen = verlauf.reihen_fuer_listungen(listungen, hist)
    assert len(reihen) == 1
    assert reihen[0]["anbieter"] == "o2"
    assert [p["datum"] for p in reihen[0]["punkte"]] == \
        ["2026-08-29", "2026-09-05"]


# --------------------------------------------------------------------------
# a) Linien nur ab zwei Messpunkten
# --------------------------------------------------------------------------

def test_ein_anbieter_mit_zwei_punkten_bekommt_eine_linie():
    reihen = [_reihe("o2", [("2026-08-29", 1315.0), ("2026-09-05", 1315.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert ergebnis["hat_daten"]
    assert "<path" in ergebnis["svg"]
    assert 'class="gr-g0-linie gr-anb--o2"' in ergebnis["svg"]


def test_ein_anbieter_mit_einem_punkt_bekommt_keine_linie():
    reihen = [_reihe("Telekom", [("2026-09-05", 1197.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert "<path" not in ergebnis["svg"]
    assert "<circle" in ergebnis["svg"]


def test_gemischte_reihen_zeigen_linie_und_punkt_nebeneinander():
    """Genau EIN `<path>` (fuer o2, zwei Punkte), Telekom bleibt Punkt."""
    reihen = [
        _reihe("o2", [("2026-08-29", 1315.0), ("2026-09-05", 1310.0)]),
        _reihe("Telekom", [("2026-09-05", 1197.0)]),
    ]
    ergebnis = grafik.zeitreihe(reihen)
    assert ergebnis["svg"].count("<path") == 1
    # Zwei Linien in der Beleg-Liste, aber nur eine mit >1 Punkt.
    linien = {l["anbieter"]: l["punkte"] for l in ergebnis["linien"]}
    assert linien == {"o2": 2, "Telekom": 1}


# --------------------------------------------------------------------------
# b) Eine Sammelluecke wird nicht ueberbrueckt
# --------------------------------------------------------------------------

def test_die_19_tage_luecke_wird_nicht_ueberbrueckt():
    """mobilcom-debitel: ein Punkt vor der Luecke (10.08.), einer danach
    (05.09.) - dieselbe Lage wie am echten Bestand vom 05.09.2026. Es
    entsteht KEINE Linie, sondern zwei einzelne Punkte."""
    reihen = [_reihe("mobilcom-debitel",
                     [("2026-08-10", 1299.0), ("2026-09-05", 1299.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert "<path" not in ergebnis["svg"]
    assert ergebnis["svg"].count("<circle") == 2
    assert ergebnis["svg"].count("gr-g0-punkt--einzeln") == 2


def test_ein_kurzer_abstand_bleibt_verbunden():
    """Fuenf Tage (dieselbe Spanne wie 29.08. -> 03.09. am echten Bestand)
    sind normale Kadenz, keine Sammelluecke - die Linie bleibt durchgezogen."""
    reihen = [_reihe("congstar",
                     [("2026-08-29", 1225.0), ("2026-09-03", 1225.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert "<path" in ergebnis["svg"]
    assert "gr-g0-punkt--einzeln" not in ergebnis["svg"]


def test_drei_punkte_mit_luecke_ergeben_zwei_getrennte_laeufe():
    """Punkt 1 und 2 liegen nah beieinander (verbunden), Punkt 3 liegt
    hinter der Luecke (einzeln) - EIN `<path>` mit zwei Punkten, dazu ein
    einzelner."""
    reihen = [_reihe("Vodafone", [
        ("2026-08-29", 1199.9), ("2026-09-01", 1199.9),
        ("2026-09-25", 1149.9),
    ])]
    ergebnis = grafik.zeitreihe(reihen)
    assert ergebnis["svg"].count("<path") == 1
    assert ergebnis["svg"].count("gr-g0-punkt--einzeln") == 1
    assert ergebnis["svg"].count("<circle") == 3


def test_die_luecke_bekommt_ein_sichtbares_feld():
    reihen = [_reihe("mobilcom-debitel",
                     [("2026-08-10", 1299.0), ("2026-09-05", 1299.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert "gr-g0-luecke" in ergebnis["svg"]
    assert "Sammellücke" in ergebnis["svg"]


def test_keine_luecke_ohne_grossen_abstand():
    reihen = [_reihe("o2", [("2026-08-29", 1315.0), ("2026-09-05", 1310.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert "gr-g0-luecke" not in ergebnis["svg"]


# --------------------------------------------------------------------------
# c) Die Y-Achse rechnet aus den echten Daten
# --------------------------------------------------------------------------

def test_die_achse_traegt_den_echten_minimal_und_maximalpreis():
    """Fuenf Marken zwischen (Minimum - Polster) und (Maximum + Polster) -
    keine feste Konstante, keine gerundeten 0/1000/… ausser sie treffen
    zufaellig genau."""
    reihen = [_reihe("o2", [("2026-08-29", 1000.0), ("2026-09-05", 1300.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    # Die Spanne 1000-1300 mit 12% Polster ergibt tief=964, hoch=1336 -
    # keine der fuenf Marken faellt auf einen glatten Hunderterwert.
    assert "1.000 €" not in ergebnis["svg"]
    assert "1.300 €" not in ergebnis["svg"]


def test_zwei_verschiedene_geraete_ergeben_zwei_verschiedene_achsen():
    """Dieselbe Rechnung, andere Eingabe, andere Achse - sonst waere die
    Achse eine Konstante und keine Rechnung."""
    billig = grafik.zeitreihe(
        [_reihe("o2", [("2026-08-29", 100.0), ("2026-09-05", 110.0)])])
    teuer = grafik.zeitreihe(
        [_reihe("o2", [("2026-08-29", 1900.0), ("2026-09-05", 1950.0)])])
    assert billig["svg"] != teuer["svg"]
    assert "€" in billig["svg"] and "€" in teuer["svg"]


def test_eine_flache_reihe_bekommt_trotzdem_eine_spanne():
    """Liegt jeder Preis gleich (Minimum == Maximum), darf die Achse nicht
    durch Null teilen - dieselbe Absicherung wie in G2."""
    reihen = [_reihe("o2", [("2026-08-29", 999.0), ("2026-09-05", 999.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert ergebnis["hat_daten"]
    assert "<svg" in ergebnis["svg"]


# --------------------------------------------------------------------------
# d) Ein Punkt bleibt ein Punkt
# --------------------------------------------------------------------------

def test_genau_ein_messpunkt_erzeugt_keine_linie_im_ganzen_bild():
    reihen = [_reihe("Telekom", [("2026-09-05", 1197.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert "<path" not in ergebnis["svg"]
    assert ergebnis["svg"].count("<circle") == 1
    assert ergebnis["messtage"] == 1
    assert ergebnis["seit"] == "2026-09-05"


def test_ohne_jeden_messpunkt_gibt_es_keine_grafik():
    ergebnis = grafik.zeitreihe([])
    assert ergebnis["hat_daten"] is False
    assert ergebnis["svg"] == ""
    assert ergebnis["chrome"] == ""


# --------------------------------------------------------------------------
# Kein nackter Punkt (BRIEF_FADEN, 05.09.2026, Kriterium 5)
#
# Antonios QA-Befund 3: "Telekoms Einzel-Punkt im Zeitreihen-Graph liest
# sich als 'keine Werte' - die ehrliche Luecke sieht aus wie ein Defekt."
# Ein einzelner Messpunkt bekommt seitdem eine sichtbare Beschriftung am
# Punkt statt nur einem Tooltip.
# --------------------------------------------------------------------------

def test_ein_einzelner_messpunkt_traegt_eine_sichtbare_beschriftung():
    reihen = [_reihe("Telekom", [("2026-09-05", 1197.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert ('class="gr-g0-einzeln gr-anb--telekom"' in ergebnis["svg"])
    assert "Serie startet · 1. Messpunkt 05.09.2026" in ergebnis["svg"]


def test_eine_verbundene_linie_traegt_keine_einzelpunkt_beschriftung():
    reihen = [_reihe("o2", [("2026-08-29", 1315.0), ("2026-09-05", 1315.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert "gr-g0-einzeln" not in ergebnis["svg"]
    assert "Serie startet" not in ergebnis["svg"]


def test_nur_der_isolierte_punkt_traegt_die_beschriftung_nicht_die_linie():
    """Wie `test_drei_punkte_mit_luecke_ergeben_zwei_getrennte_laeufe`: zwei
    verbundene Punkte, ein dritter isolierter hinter der Sammelluecke - nur
    der dritte ist "einzeln" und bekommt die Beschriftung."""
    reihen = [_reihe("Vodafone", [
        ("2026-08-29", 1199.9), ("2026-09-01", 1199.9),
        ("2026-09-25", 1149.9),
    ])]
    ergebnis = grafik.zeitreihe(reihen)
    assert ergebnis["svg"].count("gr-g0-einzeln") == 1
    assert ergebnis["svg"].count("Serie startet") == 1
    assert "Serie startet · 1. Messpunkt 25.09.2026" in ergebnis["svg"]


def test_gemischte_reihen_beschriften_nur_den_einzelnen_punkt():
    reihen = [
        _reihe("o2", [("2026-08-29", 1315.0), ("2026-09-05", 1310.0)]),
        _reihe("Telekom", [("2026-09-05", 1197.0)]),
    ]
    ergebnis = grafik.zeitreihe(reihen)
    assert ergebnis["svg"].count("Serie startet") == 1
    assert "Serie startet · 1. Messpunkt 05.09.2026" in ergebnis["svg"]


# --------------------------------------------------------------------------
# Die Chart-Chrome-Zeile - kein Fliesstext, ein einziger Satz
# --------------------------------------------------------------------------

def test_die_chrome_zeile_nennt_messtage_und_das_erste_datum():
    reihen = [
        _reihe("mobilcom-debitel", [("2026-08-10", 1299.0), ("2026-09-05", 1299.0)]),
        _reihe("Vodafone", [("2026-08-29", 1199.9), ("2026-09-05", 1199.9)]),
        _reihe("congstar", [("2026-09-03", 1225.0)]),
    ]
    ergebnis = grafik.zeitreihe(reihen)
    # Vier verschiedene Tage insgesamt: 10.08., 29.08., 03.09., 05.09.
    assert ergebnis["messtage"] == 4
    assert ergebnis["seit"] == "2026-08-10"
    assert ergebnis["chrome"] == "Sammlung läuft · 4 Messtage · seit 10.08.2026"


def test_die_chrome_zeile_beugt_bei_einem_messtag_richtig():
    reihen = [_reihe("Telekom", [("2026-09-05", 1197.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert ergebnis["chrome"] == "Sammlung läuft · 1 Messtag · seit 05.09.2026"


def test_die_chrome_zeile_ist_der_einzige_satz_im_belegtext():
    """Kein Methodentext im Beleg - `linien` traegt nur Anbieter, Punkte,
    Zeitraum je Linie (Kriterium 5)."""
    reihen = [_reihe("o2", [("2026-08-29", 1315.0), ("2026-09-05", 1310.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    assert set(ergebnis["linien"][0]) == {
        "anbieter", "farbe", "eigen", "punkte", "von", "bis", "von_de", "bis_de"}
    assert ergebnis["linien"][0]["von_de"] == "29.08.2026"
    assert ergebnis["linien"][0]["bis_de"] == "05.09.2026"


# --------------------------------------------------------------------------
# Keine erfundenen Zwischenpunkte
# --------------------------------------------------------------------------

def test_es_werden_nur_die_gegebenen_preise_gezeichnet():
    """Zwei Punkte, ein Pfad mit genau zwei Koordinatenbefehlen (M und L) -
    keine dritte, interpolierte Koordinate dazwischen."""
    reihen = [_reihe("o2", [("2026-08-29", 1315.0), ("2026-09-05", 1310.0)])]
    ergebnis = grafik.zeitreihe(reihen)
    pfad = ergebnis["svg"].split('d="')[1].split('"')[0]
    befehle = [c for c in pfad if c in "ML"]
    assert befehle == ["M", "L"]
