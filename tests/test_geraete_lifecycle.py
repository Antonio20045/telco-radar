"""Die Lifecycle-Auswertung - deterministisch, ohne Modell.

Das eigentliche Wertversprechen der Seite und zugleich die Stelle, an der
sich am leichtesten luegen laesst: aus zwei Messpunkten eine Kurve zu
zeichnen ist trivial, und sie sieht gut aus. Deshalb steht in jedem
Ergebnis, worauf es beruht, und unter `_MIND_PUNKTE` Messpunkten heisst es
"Datenbasis noch duenn" - nicht "Trend".
"""
from pathlib import Path

import pytest

from telco_radar.analyze.geraete_lifecycle import (
    MIND_PUNKTE,
    MIND_TAGE_JE_GERAET,
    MIND_TERMINE_JE_GERAET,
    MIND_WOCHEN,
    auswertung,
    listungsdauer,
    nachfolger_effekt,
    portfolio_tiefe,
    preisverfall,
    verweildauer_nach_nachfolger,
)
from telco_radar.analyze.geraete_store import (
    STATUS_AKTIV,
    STATUS_AUSGELISTET,
    GeraeteDB,
    Preishistorie,
)
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import Geraet, Katalog

_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Apple", modell="iPhone 16 Pro Max", generation=16,
           marktstart="2024-09-20", segment="flagship"),
    Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
           vorgaenger="iPhone 16 Pro Max", marktstart="2025-09-19",
           segment="flagship"),
    Geraet(hersteller="Apple", modell="iPhone 15 Pro Max", generation=15,
           segment="flagship"),          # ohne Marktstart
])


def _eintrag(device="apple-iphone-16-pro-max", anbieter="expert",
             first="2025-06-01", last="2026-08-10", status=STATUS_AKTIV,
             preis=899.0, erstpreis=1449.0, sku=None, **kw):
    e = {
        "id": f"{anbieter}--{sku or device}",
        "sku_id": sku or f"{device}-256gb-schwarz",
        "device_id": device, "anbieter": anbieter, "anbieter_typ": "handel",
        "first_seen": first, "last_verified": last, "status": status,
        "preis_ohne_vertrag": preis, "erstpreis": erstpreis,
        "erstpreis_art": "ohne_vertrag", "erstpreis_am": first,
    }
    e.update(kw)
    return e


def _punkte(*paare, listung_id="expert--apple-iphone-16-pro-max"):
    return [{"listung_id": listung_id, "datum": d, "preis_ohne_vertrag": p,
             "device_id": "apple-iphone-16-pro-max", "anbieter": "expert"}
            for d, p in paare]


# --------------------------------------------------------------------------
# Listungsdauer
# --------------------------------------------------------------------------

def test_listungsdauer_zaehlt_von_der_ersten_bis_zur_letzten_sichtung():
    d = listungsdauer(_eintrag(first="2026-01-01", last="2026-08-10"))
    assert d == 221


def test_ein_ausgelistetes_geraet_endet_am_auslistungstag():
    d = listungsdauer(_eintrag(first="2026-01-01", last="2026-06-01",
                               status=STATUS_AUSGELISTET, ended_since="2026-06-15"))
    # Gezaehlt wird bis zur letzten BESTAETIGUNG, nicht bis zum Tag, an dem
    # der Store aufgegeben hat - sonst zaehlten die zwei Fehltreffer der
    # Auslistungslogik als Portfoliozeit mit.
    assert d == 151


def test_listungsdauer_am_ersten_tag_ist_null():
    assert listungsdauer(_eintrag(first="2026-08-10", last="2026-08-10")) == 0


def test_kaputte_daten_ergeben_keine_dauer():
    assert listungsdauer(_eintrag(first="", last="2026-08-10")) is None
    assert listungsdauer(_eintrag(first="gestern", last="2026-08-10")) is None


# --------------------------------------------------------------------------
# Preisverfall
# --------------------------------------------------------------------------

def test_preisverfall_absolut_und_prozentual():
    """Der Testfall aus Teil D3 des Auftrags."""
    v = preisverfall(_eintrag(erstpreis=899.0, preis=649.0))
    assert v["absolut"] == -250.0
    assert v["prozent"] == pytest.approx(-27.8, abs=0.05)


def test_preisanstieg_wird_genauso_gerechnet():
    v = preisverfall(_eintrag(erstpreis=649.0, preis=699.0))
    assert v["absolut"] == 50.0 and v["prozent"] > 0


def test_ohne_einfuehrungspreis_kein_verfall():
    assert preisverfall(_eintrag(erstpreis=None)) is None
    assert preisverfall(_eintrag(preis=None)) is None


def test_zwei_preisarten_werden_nicht_verrechnet():
    """Teil C4: 1449 Euro ohne Vertrag gegen 49,95 Euro Zuzahlung waeren
    96,6 Prozent "Preisverfall" - die zwei Preisarten in einer Rechnung."""
    e = _eintrag(erstpreis=1449.0, preis=None)
    e["erstpreis_art"] = "ohne_vertrag"
    e["zuzahlung"] = 49.95
    e["tarif_referenz"] = "MagentaMobil M"
    assert preisverfall(e) is None


# --------------------------------------------------------------------------
# Nachfolger-Effekt
# --------------------------------------------------------------------------

def test_nachfolger_effekt_ueber_30_60_90_tage():
    punkte = _punkte(("2025-08-01", 1449.0), ("2025-09-25", 1299.0),
                     ("2025-10-30", 1149.0), ("2025-12-15", 999.0))
    e = nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG, punkte)
    assert e is not None
    assert e["nachfolger"] == "apple-iphone-17-pro-max"
    assert e["marktstart"] == "2025-09-19"
    assert e["basis"] == 1449.0            # letzter Preis VOR dem Start
    assert e["nach"][30] == 1299.0
    assert e["nach"][60] == 1149.0
    assert e["nach"][90] == 999.0
    assert e["prozent"][90] == pytest.approx(-31.1, abs=0.1)


def test_ohne_marktstart_des_nachfolgers_kein_effekt():
    """Ein geratenes Datum ist schlimmer als ein fehlendes - der Katalog
    laesst `marktstart` deshalb leer, und dann gibt es keine Kurve."""
    katalog = Katalog(geraete=[
        Geraet(hersteller="Apple", modell="iPhone 16 Pro Max", generation=16),
        Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
               vorgaenger="iPhone 16 Pro Max"),      # ohne marktstart
    ])
    assert nachfolger_effekt("apple-iphone-16-pro-max", katalog,
                             _punkte(("2026-01-01", 1449.0))) is None


def test_ohne_nachfolger_kein_effekt():
    assert nachfolger_effekt("apple-iphone-17-pro-max", _KATALOG,
                             _punkte(("2026-01-01", 1449.0))) is None


def test_ohne_preis_vor_dem_start_kein_effekt():
    # Wir haben erst nach dem Nachfolger angefangen zu messen - dann gibt es
    # keine Basis, gegen die zu rechnen waere.
    punkte = _punkte(("2025-10-01", 1299.0), ("2025-12-01", 1099.0))
    assert nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG, punkte) is None


def test_noch_nicht_erreichte_fenster_bleiben_leer():
    punkte = _punkte(("2025-08-01", 1449.0), ("2025-09-25", 1299.0))
    # 30 Tage nach dem 19.09. ist der 19.10. - erreicht; 60 und 90 nicht.
    e = nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG, punkte,
                          heute="2025-10-25")
    assert e["nach"][30] == 1299.0
    assert e["nach"][60] is None and e["nach"][90] is None


# --------------------------------------------------------------------------
# Portfolio-Tiefe
# --------------------------------------------------------------------------

def test_portfolio_tiefe_zaehlt_gleichzeitige_generationen():
    """Antonios Beobachtung: Wettbewerber halten das Vorgaengermodell als
    Preiseinstieg im Regal, bei Vodafone wird es meist direkt ersetzt."""
    eintraege = [
        _eintrag(device="apple-iphone-17-pro-max", anbieter="expert"),
        _eintrag(device="apple-iphone-16-pro-max", anbieter="expert"),
        _eintrag(device="apple-iphone-15-pro-max", anbieter="expert"),
        _eintrag(device="apple-iphone-17-pro-max", anbieter="Vodafone"),
    ]
    tiefe = portfolio_tiefe(eintraege, _KATALOG)
    nach_anbieter = {t["anbieter"]: t for t in tiefe}
    assert len(nach_anbieter) == 2
    assert nach_anbieter["expert"]["generationen"] == 3
    assert nach_anbieter["Vodafone"]["generationen"] == 1


def test_ausgelistete_geraete_zaehlen_nicht_zur_tiefe():
    eintraege = [
        _eintrag(device="apple-iphone-17-pro-max", anbieter="expert"),
        _eintrag(device="apple-iphone-16-pro-max", anbieter="expert",
                 status=STATUS_AUSGELISTET),
    ]
    assert portfolio_tiefe(eintraege, _KATALOG)[0]["generationen"] == 1


def test_mehrere_varianten_eines_geraets_sind_eine_generation():
    eintraege = [
        _eintrag(device="apple-iphone-17-pro-max", anbieter="expert",
                 sku="apple-iphone-17-pro-max-256gb-schwarz"),
        _eintrag(device="apple-iphone-17-pro-max", anbieter="expert",
                 sku="apple-iphone-17-pro-max-512gb-schwarz"),
    ]
    t = portfolio_tiefe(eintraege, _KATALOG)[0]
    assert t["generationen"] == 1 and t["skus"] == 2


# --------------------------------------------------------------------------
# Die Ehrlichkeit ueber die Datenbasis
# --------------------------------------------------------------------------

def test_zwei_messpunkte_sind_kein_trend():
    """Akzeptanzkriterium aus Teil E. In den ersten Wochen gibt es schlicht
    keine Historie - dann sagt die Auswertung das, statt aus zwei Punkten
    eine Kurve zu zeichnen.

    Die Listung ist seit dem 11.08.2026 ebenfalls jung. Vorher entschied die
    Zahl der PREISPUNKTE ueber alles; jetzt entscheidet je Kennzahl ihre
    eigene Beobachtungsdauer, und eine seit einem Jahr gelistete Ware mit
    zwei Preispunkten hat sehr wohl eine belastbare Verweildauer."""
    a = auswertung([_eintrag(first="2026-08-03",
                             erstpreis_am="2026-08-03")],
                   _punkte(("2026-08-03", 1449.0), ("2026-08-10", 1399.0)),
                   _KATALOG, heute="2026-08-10")
    assert a["duenn"] is True
    assert a["punkte"] == 2
    assert a["dauern"] == [] and a["verfaelle"] == []
    assert "duenn" in a["hinweis"].lower() or "dünn" in a["hinweis"].lower()
    assert a["trends"] == []


def test_genug_messpunkte_ergeben_einen_trend():
    punkte = _punkte(*[(f"2026-{1 + m // 3:02d}-{1 + (m % 3) * 10:02d}",
                        1449.0 - m * 25) for m in range(15)])
    a = auswertung([_eintrag(first="2026-01-01")], punkte, _KATALOG,
                   heute="2026-08-10")
    assert a["punkte"] >= MIND_PUNKTE
    assert a["duenn"] is False
    assert a["trends"], "genug Punkte, aber kein Trend ausgewiesen"


def test_der_hinweis_nennt_beide_zahlen():
    # Die Listung ist jung (der Hinweis der duennen Basis wird geprueft), die
    # Messreihe reicht aber 21 Tage zurueck.
    a = auswertung([_eintrag(first="2026-08-04", erstpreis_am="2026-08-04")],
                   _punkte(("2026-07-20", 1449.0), ("2026-08-10", 1399.0)),
                   _KATALOG, heute="2026-08-10")
    # "seit N Tagen beobachtet, belastbar ab etwa M Wochen" - beide Zahlen
    # muessen dastehen, sonst ist der Satz eine Ausrede statt einer Auskunft.
    assert a["duenn"] is True, a["hinweis"]
    assert str(MIND_WOCHEN) in a["hinweis"]
    assert "21 Tage" in a["hinweis"], a["hinweis"]


def test_leere_datenbasis_kippt_nicht():
    a = auswertung([], [], _KATALOG, heute="2026-08-10")
    assert a["duenn"] is True and a["punkte"] == 0 and a["trends"] == []
    assert a["portfolio"] == []


# --------------------------------------------------------------------------
# Die Schwelle der Lifecycle-Sektion (Evaluation vom 11.08.2026)
# --------------------------------------------------------------------------

def test_ein_messtag_ergibt_keine_einzige_lifecycle_zeile():
    """Der Befund: die ausgelieferte Seite zeigte zwoelf Zeilen "0 Tage" und
    zwoelf Zeilen "+0.0 %".

    Ursache war, dass `duenn` PREISPUNKTE zaehlte statt MESSTERMINE: 85
    Listungen an EINEM Tag ergaben 85 Punkte, die Basis galt als dick. Gegen
    den alten Stand gemessen faellt dieser Test durch - er ist der
    Reproduktionsfall."""
    eintraege = [
        {"id": f"l{i}", "device_id": "apple-iphone-17-pro-max",
         "anbieter": "Medimax", "status": "aktiv",
         "first_seen": "2026-08-10", "last_verified": "2026-08-10",
         "preis_ohne_vertrag": 1449.0, "erstpreis": 1449.0,
         "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-10"}
        for i in range(12)]
    punkte = [{"listung_id": f"l{i}", "device_id": "apple-iphone-17-pro-max",
               "anbieter": "Medimax", "datum": "2026-08-10",
               "preis_ohne_vertrag": 1449.0} for i in range(12)]

    a = auswertung(eintraege, punkte, _KATALOG, heute="2026-08-10")
    assert a["duenn"] is True, "zwoelf Punkte an EINEM Tag sind keine Basis"
    assert a["dauern"] == [], "keine Verweildauer aus einem einzigen Messtag"
    assert a["verfaelle"] == [] and a["trends"] == []
    assert a["termine"] == 1


def test_die_schwelle_greift_je_geraet():
    """Vier Messtermine ueber 21 Tage - darunter keine Zeile.

    Ein Portfolio, in dem EIN Geraet lange beobachtet wird und ein anderes
    seit gestern, darf nicht fuer beide eine Zahl behaupten."""
    lange = [{"listung_id": "alt", "device_id": "apple-iphone-17-pro-max",
              "anbieter": "Medimax", "datum": d, "preis_ohne_vertrag": p}
             for d, p in (("2026-07-01", 1499.0), ("2026-07-10", 1479.0),
                          ("2026-07-20", 1459.0), ("2026-08-10", 1449.0))]
    kurz = [{"listung_id": "neu", "device_id": "samsung-galaxy-s25-ultra",
             "anbieter": "Medimax", "datum": d, "preis_ohne_vertrag": 1249.0}
            for d in ("2026-08-09", "2026-08-10")]
    eintraege = [
        {"id": "alt", "device_id": "apple-iphone-17-pro-max", "anbieter": "Medimax",
         "status": "aktiv", "first_seen": "2026-07-01",
         "last_verified": "2026-08-10", "preis_ohne_vertrag": 1449.0,
         "erstpreis": 1499.0, "erstpreis_art": "ohne_vertrag",
         "erstpreis_am": "2026-07-01"},
        {"id": "neu", "device_id": "samsung-galaxy-s25-ultra", "anbieter": "Medimax",
         "status": "aktiv", "first_seen": "2026-08-09",
         "last_verified": "2026-08-10", "preis_ohne_vertrag": 1249.0,
         "erstpreis": 1249.0, "erstpreis_art": "ohne_vertrag",
         "erstpreis_am": "2026-08-09"},
    ]
    a = auswertung(eintraege, lange + kurz, _KATALOG, heute="2026-08-10")
    assert a["duenn"] is False, "ein Geraet nimmt die Schwelle"
    assert [d["device_id"] for d in a["dauern"]] == ["apple-iphone-17-pro-max"]
    assert all(v["device_id"] == "apple-iphone-17-pro-max" for v in a["verfaelle"])


def test_eine_lange_beobachtung_ergibt_sehr_wohl_eine_zeile():
    """Die Gegenprobe zur Schwelle - und der Fall, den die erste Fassung
    STILL abgeschaltet haette.

    `geraete_preise.jsonl` traegt nur AENDERUNGSpunkte. Eine Ware, die ein
    halbes Jahr stabil im Regal steht, hat dort genau einen Punkt. Wer
    Aenderungspunkte zaehlt, sperrt genau diese Ware aus - und laesst
    stattdessen die zu, deren Verfuegbarkeit flattert."""
    a = auswertung(
        [_eintrag(first="2026-02-01", last="2026-08-10",
                  erstpreis_am="2026-02-01", erstpreis=1449.0, preis=899.0)],
        _punkte(("2026-02-01", 1449.0)),          # EIN einziger Punkt
        _KATALOG, heute="2026-08-10",
        laeufe_je_anbieter={"expert": 40})
    assert a["duenn"] is False, a["hinweis"]
    assert [d["tage"] for d in a["dauern"]] == [190]
    assert a["verfaelle"] and a["verfaelle"][0]["prozent"] < 0


def test_wenige_laeufe_sperren_die_zeile_trotz_langer_spanne():
    """Vier Messtermine ueber 21 Tage - ein Messtermin ist ein LAUF.

    Ohne die Laufzahl genuegte eine einzige Messung mit weit
    auseinanderliegendem first_seen/last_verified."""
    a = auswertung(
        [_eintrag(first="2026-02-01", last="2026-08-10",
                  erstpreis_am="2026-02-01")],
        _punkte(("2026-02-01", 1449.0)), _KATALOG, heute="2026-08-10",
        laeufe_je_anbieter={"expert": 3})
    assert a["duenn"] is True
    assert a["dauern"] == [] and a["verfaelle"] == []


# --------------------------------------------------------------------------
# Messtermine kommen aus den Pruefterminen, nicht aus der Preishistorie
# (Diagnose G0 vom 28.08.2026)
# --------------------------------------------------------------------------

def test_der_hinweis_zaehlt_prueftermine_statt_aenderungspunkte():
    """Der Reproduktionsfall der Live-Seite vom 28.08.2026: 85 Listungen,
    alle Historienzeilen vom 10.08. (kein Preis hat sich geaendert), aber
    vier echte Prueftermine. Die Seite sagte "bisher 1 Messtermin" - gegen
    den alten Stand faellt dieser Test durch."""
    eintraege = [
        {"id": "l1", "device_id": "apple-iphone-17-pro-max",
         "anbieter": "mobilcom-debitel", "status": "aktiv",
         "first_seen": "2026-08-10", "last_verified": "2026-08-27",
         "preis_ohne_vertrag": 1449.0, "erstpreis": 1449.0,
         "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-10"}]
    punkte = [{"listung_id": "l1", "device_id": "apple-iphone-17-pro-max",
               "anbieter": "mobilcom-debitel", "datum": "2026-08-10",
               "preis_ohne_vertrag": 1449.0}]
    termine = {"mobilcom-debitel": ["2026-08-10", "2026-08-14",
                                    "2026-08-21", "2026-08-27"]}
    a = auswertung(eintraege, punkte, _KATALOG, heute="2026-08-28",
                   termine_je_anbieter=termine)
    assert a["termine"] == 4, a["hinweis"]
    assert "4 Messtermine" in a["hinweis"], a["hinweis"]


def test_vier_prueftermine_ueber_21_tage_schalten_die_sektion_frei():
    """Dieselben Daten wie oben: vier Termine, 17+ Tage Spanne, stabiler
    Preis. Ein stabiler Preis ist ein Messergebnis - die Listungsdauer darf
    daran nicht scheitern."""
    eintraege = [
        {"id": "l1", "device_id": "apple-iphone-17-pro-max",
         "anbieter": "mobilcom-debitel", "status": "aktiv",
         "first_seen": "2026-08-01", "last_verified": "2026-08-27",
         "preis_ohne_vertrag": 1449.0, "erstpreis": 1449.0,
         "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-01"}]
    punkte = [{"listung_id": "l1", "device_id": "apple-iphone-17-pro-max",
               "anbieter": "mobilcom-debitel", "datum": "2026-08-01",
               "preis_ohne_vertrag": 1449.0}]
    termine = {"mobilcom-debitel": ["2026-08-01", "2026-08-10",
                                    "2026-08-21", "2026-08-27"]}
    a = auswertung(eintraege, punkte, _KATALOG, heute="2026-08-28",
                   termine_je_anbieter=termine)
    assert a["duenn"] is False, a["hinweis"]
    assert [d["tage"] for d in a["dauern"]] == [26]


def test_drei_prueftermine_reichen_nicht():
    """Die Schwelle (4 Termine) gilt auch fuer die Termine-Quelle - drei
    Prueftage sind keine Messreihe, egal wie weit sie auseinanderliegen."""
    eintraege = [
        {"id": "l1", "device_id": "apple-iphone-17-pro-max",
         "anbieter": "mobilcom-debitel", "status": "aktiv",
         "first_seen": "2026-08-01", "last_verified": "2026-08-27",
         "preis_ohne_vertrag": 1449.0, "erstpreis": 1449.0,
         "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-01"}]
    a = auswertung(eintraege, [], _KATALOG, heute="2026-08-28",
                   termine_je_anbieter={"mobilcom-debitel":
                                        ["2026-08-01", "2026-08-10",
                                         "2026-08-27"]})
    assert a["dauern"] == [] and a["duenn"] is True


# --------------------------------------------------------------------------
# Die Schwelle zaehlt je LISTUNG, nicht je Anbieter (31.08.2026)
#
# Der Kommentar ueber `MIND_TERMINE_JE_GERAET` versprach seit dem 28.08.2026
# "und zwar JE GERAET"; `_oft_genug` las dagegen
# `termine_je_anbieter[eintrag["anbieter"]]`. Ein einziges lange beobachtetes
# Geraet schaltete damit den ganzen Anbieter frei - also auch die elf, die es
# seit gestern gibt. Gegen den alten Stand fallen
# `test_die_termin_schwelle_zaehlt_je_listung_nicht_je_anbieter` und
# `test_ein_prueftermin_vor_der_ersten_sichtung_zaehlt_nicht_mit` durch; sie
# sind der Reproduktionsfall.
# --------------------------------------------------------------------------

def _termin_eintrag(lid, device="apple-iphone-16-pro-max", anbieter="Medimax",
                    first="2026-01-01", last="2026-04-01", status=STATUS_AKTIV,
                    preis=1199.0, erstpreis=1449.0):
    """Eine Listung mit eigener ID - die Preishistorie ist darauf geschluesselt."""
    return {"id": lid, "sku_id": f"{device}-256gb-schwarz-{lid}",
            "device_id": device, "anbieter": anbieter, "anbieter_typ": "handel",
            "first_seen": first, "last_verified": last, "status": status,
            "preis_ohne_vertrag": preis, "erstpreis": erstpreis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": first}


def test_die_termin_schwelle_zaehlt_je_listung_nicht_je_anbieter():
    """Vier Prueftermine des ANBIETERS, zwei Listungen mit verschiedenen
    Beobachtungsfenstern: nur die, in deren Fenster vier Termine liegen,
    bekommt eine Zeile.

    Die zweite Listung ist ausdruecklich NICHT an der Spanne gescheitert -
    das wird im selben Test nachgewiesen, sonst prueft er die falsche Regel.
    """
    termine = {"Medimax": ["2026-01-01", "2026-02-01", "2026-03-01",
                           "2026-04-01"]}
    lang = _termin_eintrag("lang", first="2026-01-01", last="2026-04-01")
    kurz = _termin_eintrag("kurz", device="apple-iphone-17-pro-max",
                           first="2026-03-01", last="2026-04-01",
                           erstpreis=1299.0, preis=1249.0)

    # Der Fall tritt ohne die Zusicherung wirklich ein: je ANBIETER gerechnet
    # nimmt "kurz" die Termin-Schwelle (vier Termine stehen in der Liste),
    # und die 21-Tage-Spanne nimmt sie ebenfalls.
    assert len(termine["Medimax"]) >= MIND_TERMINE_JE_GERAET
    assert listungsdauer(kurz) == 31 >= MIND_TAGE_JE_GERAET

    a = auswertung([lang, kurz], [], _KATALOG, heute="2026-04-02",
                   termine_je_anbieter=termine)
    zugeordnet = {d["device_id"]: d for d in a["dauern"]}
    assert len(zugeordnet) == len(a["dauern"]) == 1, a["dauern"]
    assert "apple-iphone-16-pro-max" in zugeordnet
    assert zugeordnet["apple-iphone-16-pro-max"]["tage"] == 90
    assert all(v["device_id"] == "apple-iphone-16-pro-max"
               for v in a["verfaelle"])


def test_die_laufzahl_des_anbieters_bleibt_der_boden():
    """Der bewusst verbliebene Rest Anbieterrechnung - und seine Grenze.

    Eine Laufzahl laesst sich keinem Fenster zuordnen, aber sie ist die
    einzige Auskunft, die einen Lauf ueberlebt, dessen Bestaetigung ein
    spaeterer ueberschrieben hat: `last_verified` behaelt nur den juengsten.
    Wer sie streicht, sperrt genau die Ware aus, die ein Jahr lang
    unveraendert im Regal steht (Lehre G0 vom 28.08.2026).

    Was NICHT mehr gilt: die blosse LAENGE der Terminliste des Anbieters.
    Sie gab bis zum 31.08.2026 jeder Listung dieselbe Zahl - auch der, die
    es erst seit dem vorletzten Termin gibt.
    """
    eintrag = _termin_eintrag("l1", first="2026-01-01", last="2026-04-01")
    termine = {"Medimax": ["2026-03-30", "2026-04-01"]}
    assert listungsdauer(eintrag) == 90 >= MIND_TAGE_JE_GERAET

    viele = auswertung([eintrag], [], _KATALOG, heute="2026-04-02",
                       laeufe_je_anbieter={"Medimax": 40},
                       termine_je_anbieter=termine)
    assert [d["tage"] for d in viele["dauern"]] == [90]

    # Die Gegenprobe: dieselben zwei Termine, aber drei Laeufe. Ohne sie
    # belegte der Test nur, dass die Zeile immer erscheint.
    wenige = auswertung([eintrag], [], _KATALOG, heute="2026-04-02",
                        laeufe_je_anbieter={"Medimax": 3},
                        termine_je_anbieter=termine)
    assert wenige["dauern"] == [] and wenige["duenn"] is True


def test_ohne_jede_termininformation_entscheidet_allein_die_spanne():
    """Der Rueckfall, und er ist der Grund, warum die Umstellung keine
    Altbestaende stillegt.

    Liegt gar keine Terminauskunft vor - kein Prueftag, keine Laufzahl, kein
    Preispunkt -, wird die Zahl NICHT erfunden: die Termin-Bedingung
    entfaellt, die Spanne gilt weiter. Ohne diesen Zweig faellt jede Listung
    durch, deren Preis sich nie geaendert hat, denn ihre eigenen Belege sind
    genau zwei (`erstpreis_am` und `last_verified`).
    """
    eintrag = _termin_eintrag("l1", anbieter="expert", first="2026-01-01",
                              last="2026-08-10")
    # Der Fall tritt wirklich ein: aus eigener Kraft hat die Listung zwei
    # Messtage, also weniger als die Schwelle verlangt.
    a = auswertung([eintrag], [], _KATALOG, heute="2026-08-11")
    assert [d["tage"] for d in a["dauern"]] == [221]
    assert a["duenn"] is False

    # Und die Gegenprobe: sobald es eine Terminauskunft GIBT, entscheidet sie.
    b = auswertung([eintrag], [], _KATALOG, heute="2026-08-11",
                   termine_je_anbieter={"expert": ["2026-08-01", "2026-08-10"]})
    assert b["dauern"] == []


def test_ein_prueftermin_vor_der_ersten_sichtung_zaehlt_nicht_mit():
    """Das Fenster ist `first_seen` bis `last_verified`. Ein Lauf, der vor
    der ersten Sichtung dieser Listung stattfand, hat sie nicht gesehen."""
    eintrag = _termin_eintrag("l1", first="2026-03-01", last="2026-04-01")
    termine = {"Medimax": ["2026-01-01", "2026-01-15", "2026-02-01",
                           "2026-03-15", "2026-04-01"]}
    assert len(termine["Medimax"]) >= MIND_TERMINE_JE_GERAET
    a = auswertung([eintrag], [], _KATALOG, heute="2026-04-02",
                   termine_je_anbieter=termine)
    # Im Fenster liegen 15.03. und 01.04.; dazu erstpreis_am (01.03.) - drei.
    assert a["dauern"] == [], a["hinweis"]

    # Gegenprobe: derselbe Anbieter, dieselben Termine, aber ein Fenster,
    # das vier davon enthaelt.
    lang = _termin_eintrag("l2", first="2026-01-01", last="2026-04-01")
    b = auswertung([lang], [], _KATALOG, heute="2026-04-02",
                   termine_je_anbieter=termine)
    assert [d["tage"] for d in b["dauern"]] == [90]


# --------------------------------------------------------------------------
# Die Schwelle gilt auch fuer die Nachfolger-Tabelle
# --------------------------------------------------------------------------

def test_ohne_die_schwelle_keine_nachfolger_zeile():
    """Bis zum 31.08.2026 lief `effekte` durch KEIN Gatter - die einzige
    Sektion, die aus zwei Messpunkten eine Aussage machte."""
    punkte = _punkte(("2025-08-01", 1449.0), ("2025-09-25", 1299.0),
                     ("2025-10-30", 1149.0), ("2025-12-15", 999.0),
                     listung_id="jung")
    jung = _termin_eintrag("jung", anbieter="expert", first="2026-08-01",
                           last="2026-08-10")

    # Der Fall tritt ohne das Gatter wirklich ein: die Preisrechnung allein
    # liefert eine vollstaendige Zeile.
    roh = nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG, punkte)
    assert roh is not None and roh["nach"][90] == 999.0
    assert listungsdauer(jung) == 9 < MIND_TAGE_JE_GERAET

    a = auswertung([jung], punkte, _KATALOG, heute="2026-08-11",
                   termine_je_anbieter={"expert": ["2026-08-01", "2026-08-04",
                                                   "2026-08-07", "2026-08-10"]})
    assert a["nachfolger"] == [], "neun Tage sind keine Lifecycle-Zeile"


def test_ueber_der_schwelle_erscheint_die_nachfolger_zeile():
    """Die Gegenprobe: dieselben Preispunkte, aber eine Listung, die vier
    Prueftermine ueber mehr als 21 Tage hinter sich hat."""
    punkte = _punkte(("2025-08-01", 1449.0), ("2025-09-25", 1299.0),
                     ("2025-10-30", 1149.0), ("2025-12-15", 999.0),
                     listung_id="alt")
    alt = _termin_eintrag("alt", anbieter="expert", first="2025-06-01",
                          last="2026-08-10")
    a = auswertung([alt], punkte, _KATALOG, heute="2026-08-11",
                   termine_je_anbieter={"expert": ["2025-08-01", "2025-09-25",
                                                   "2025-10-30", "2025-12-15"]})
    assert len(a["nachfolger"]) == 1
    zeile = a["nachfolger"][0]
    assert zeile["device_id"] == "apple-iphone-16-pro-max"
    assert zeile["anbieter"] == "expert"
    assert zeile["nachfolger"] == "apple-iphone-17-pro-max"
    assert zeile["basis"] == 1449.0 and zeile["nach"][90] == 999.0
    assert zeile["verweildauer_tage"] == 325
    assert zeile["verweildauer_untergrenze"] is False
    assert zeile["noch_gelistet"] is True


# --------------------------------------------------------------------------
# Die fehlende Haelfte des Nachfolger-Effekts: die Verweildauer
#
# Die Anforderung lautet vollstaendig "Preis des Vorgaengers 30/60/90 Tage
# nach Marktstart des Nachfolgers UND wie lange er danach noch im Regal
# bleibt". Der zweite Halbsatz ist die These der Fachabteilung - und er
# haengt am Preis NICHT.
# --------------------------------------------------------------------------

def _regal(first, last, status=STATUS_AKTIV, anbieter="expert",
           device="apple-iphone-16-pro-max", lid="l1"):
    return _termin_eintrag(lid, device=device, anbieter=anbieter,
                           first=first, last=last, status=status)


def test_der_vorgaenger_verschwindet_vor_dem_marktstart_des_nachfolgers():
    """"Keinen Tag" ist die ehrliche Antwort - und keine negative Dauer.

    Das ist die Vodafone-Seite von Antonios These: das alte Geraet ist aus
    dem Regal, bevor der Nachfolger ueberhaupt kommt.
    """
    v = verweildauer_nach_nachfolger(
        [_regal("2025-01-01", "2025-08-01", status=STATUS_AUSGELISTET)],
        _KATALOG)
    # Der Fall tritt wirklich ein: die letzte Bestaetigung liegt VOR dem
    # Marktstart des Nachfolgers.
    assert v["marktstart"] == "2025-09-19" > "2025-08-01"
    assert v["verweildauer_tage"] == 0
    assert v["noch_gelistet"] is False
    assert v["verweildauer_untergrenze"] is False


def test_der_vorgaenger_bleibt_ueber_den_marktstart_hinaus_im_regal():
    """Die Wettbewerber-Seite derselben These - und die Zahl, die sie
    pruefbar macht."""
    v = verweildauer_nach_nachfolger([_regal("2025-01-01", "2026-08-10")],
                                     _KATALOG)
    assert v["verweildauer_tage"] == 325       # 19.09.2025 -> 10.08.2026
    assert v["noch_gelistet"] is True
    assert v["verweildauer_untergrenze"] is False
    assert v["anbieter"] == "expert"
    assert v["device_id"] == "apple-iphone-16-pro-max"
    assert v["nachfolger"] == "apple-iphone-17-pro-max"
    assert v["nachfolger_modell"] == "iPhone 17 Pro Max"


def test_erst_nach_dem_marktstart_gemessen_ist_eine_untergrenze():
    """Der Fall des echten Bestands: alle Kandidaten haben ihren
    Nachfolger-Marktstart 570 bis 710 Tage vor unserem ersten Messpunkt.

    Belastbar sagen laesst sich dann nur "steht mindestens so lange noch im
    Regal" - eine Untergrenze, kein Verlauf. Eine Zahl, die so tut, als
    haetten wir die ganze Zeit gemessen, waere eine Falschaussage.
    """
    spaet = verweildauer_nach_nachfolger([_regal("2025-11-30", "2026-08-10")],
                                         _KATALOG)
    assert spaet["verweildauer_untergrenze"] is True
    assert spaet["verweildauer_tage"] == 325
    assert spaet["beobachtet_seit"] == "2025-11-30"

    # Gegenprobe im selben Test: dieselbe rechte Kante, aber eine
    # Beobachtung, die VOR dem Marktstart begonnen hat. Ohne sie koennte das
    # Feld konstant True sein und der Test waere trotzdem gruen.
    frueh = verweildauer_nach_nachfolger([_regal("2025-01-01", "2026-08-10")],
                                         _KATALOG)
    assert frueh["verweildauer_untergrenze"] is False
    assert frueh["verweildauer_tage"] == spaet["verweildauer_tage"]


def test_der_beobachtungsbeginn_zaehlt_auch_den_erstpreis():
    """Ein Altbestand kann einen `erstpreis_am` tragen, der aelter ist als
    sein `first_seen`. Der aeltere der beiden Belege ist der Beginn."""
    e = _regal("2025-11-30", "2026-08-10")
    e["erstpreis_am"] = "2025-01-05"
    v = verweildauer_nach_nachfolger([e], _KATALOG)
    assert v["beobachtet_seit"] == "2025-01-05"
    assert v["verweildauer_untergrenze"] is False


def test_die_verweildauer_rechnet_ueber_den_regalplatz_nicht_die_farbe():
    """Acht Farben und drei Speichergroessen sind EIN Regalplatz. Gerechnet
    wird vom fruehesten `first_seen` bis zum spaetesten `last_verified`."""
    gruppe = [_regal("2025-11-30", "2026-02-01", lid="a"),
              _regal("2025-01-01", "2026-08-10", lid="b"),
              _regal("2026-01-01", "2026-03-01", lid="c",
                     status=STATUS_AUSGELISTET)]
    v = verweildauer_nach_nachfolger(gruppe, _KATALOG)
    assert v["beobachtet_seit"] == "2025-01-01"
    assert v["zuletzt_bestaetigt"] == "2026-08-10"
    assert v["verweildauer_tage"] == 325
    assert v["noch_gelistet"] is True          # zwei der drei sind aktiv


def test_ohne_marktstart_des_nachfolgers_keine_verweildauer():
    """Ein geratenes Datum waere schlimmer als ein fehlendes - dieselbe
    Regel wie bei der Preisrechnung."""
    katalog = Katalog(geraete=[
        Geraet(hersteller="Apple", modell="iPhone 16 Pro Max", generation=16),
        Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
               vorgaenger="iPhone 16 Pro Max"),      # ohne marktstart
    ])
    # Der Fall tritt wirklich ein: es GIBT einen Nachfolger, nur kein Datum.
    assert katalog.nachfolger_von("apple-iphone-16-pro-max") is not None
    assert verweildauer_nach_nachfolger([_regal("2025-01-01", "2026-08-10")],
                                        katalog) is None


def test_ohne_nachfolger_keine_verweildauer():
    v = verweildauer_nach_nachfolger(
        [_regal("2025-01-01", "2026-08-10",
                device="apple-iphone-17-pro-max")], _KATALOG)
    assert v is None


def test_ohne_letzte_bestaetigung_keine_verweildauer():
    """Eine Verweildauer ohne rechte Kante waere geraten."""
    e = _regal("2025-01-01", "2026-08-10")
    e["last_verified"] = ""
    assert verweildauer_nach_nachfolger([e], _KATALOG) is None


def test_eine_zeile_ohne_preisbasis_traegt_trotzdem_die_verweildauer():
    """Die Entscheidung des Modulkopfs (Regel 3), an echten Daten
    nachgestellt: alle vier Kandidaten des Bestands vom 31.08.2026 haben
    KEINEN Preis vom oder vor dem Marktstart ihres Nachfolgers.

    Faellt die Zeile daran, verschweigt die Sektion eine echte Messung (die
    Verweildauer) wegen einer fehlenden (dem Preis von damals).
    """
    # Erst ab 2025-11-30 gemessen, der Nachfolger kam am 2025-09-19.
    punkte = _punkte(("2025-11-30", 1199.0), ("2026-06-01", 1099.0),
                     listung_id="l1")
    eintrag = _regal("2025-11-30", "2026-08-10")

    # Der Fall tritt wirklich ein: die Preisrechnung allein gibt None.
    assert nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG, punkte,
                             anbieter="expert") is None

    a = auswertung([eintrag], punkte, _KATALOG, heute="2026-08-11",
                   termine_je_anbieter={"expert": ["2025-11-30", "2026-02-01",
                                                   "2026-06-01", "2026-08-10"]})
    assert len(a["nachfolger"]) == 1
    zeile = a["nachfolger"][0]
    assert zeile["verweildauer_tage"] == 325
    assert zeile["verweildauer_untergrenze"] is True
    assert zeile["noch_gelistet"] is True
    # Die Preisspalten sind LEER, aber vollstaendig: die Darstellung soll nie
    # zwischen zwei Formen unterscheiden muessen.
    assert zeile["basis"] is None
    assert zeile["nach"] == {30: None, 60: None, 90: None}
    assert zeile["prozent"] == {30: None, 60: None, 90: None}


def test_die_nachfolger_zeile_traegt_die_vereinbarten_schluessel():
    """Die Schnittstelle zum Darstellungspaket. Ein fehlendes Feld faellt
    dort erst beim Rendern auf - und dann ohne Fehlermeldung."""
    punkte = _punkte(("2025-08-01", 1449.0), ("2025-10-30", 1149.0),
                     listung_id="l1")
    a = auswertung([_regal("2025-06-01", "2026-08-10")], punkte, _KATALOG,
                   heute="2026-08-11",
                   termine_je_anbieter={"expert": ["2025-08-01", "2025-10-30",
                                                   "2026-02-01", "2026-08-10"]})
    erwartet = {"device_id", "modell", "anbieter", "nachfolger",
                "nachfolger_modell", "marktstart", "basis", "nach", "prozent",
                "verweildauer_tage", "verweildauer_untergrenze",
                "noch_gelistet", "beobachtet_seit", "zuletzt_bestaetigt"}
    assert len(a["nachfolger"]) == 1
    assert erwartet <= set(a["nachfolger"][0])


def test_je_anbieter_eine_eigene_nachfolger_zeile():
    """Die These lautet "Wettbewerber lassen stehen, Vodafone ersetzt" - sie
    ist ohne die Anbieterspalte nicht pruefbar. Und die Preisreihe des einen
    Haendlers darf nie gegen die des anderen gerechnet werden."""
    punkte = (_punkte(("2025-08-01", 1449.0), ("2025-12-15", 999.0),
                      listung_id="a")
              + [{"listung_id": "b", "datum": d, "preis_ohne_vertrag": p,
                  "device_id": "apple-iphone-16-pro-max",
                  "anbieter": "Vodafone"}
                 for d, p in (("2025-08-01", 1399.0), ("2025-12-15", 1349.0))])
    eintraege = [_regal("2025-06-01", "2026-08-10", lid="a"),
                 _regal("2025-06-01", "2025-10-01", lid="b",
                        anbieter="Vodafone", status=STATUS_AUSGELISTET)]
    termine = {"expert": ["2025-08-01", "2025-10-01", "2025-12-15",
                          "2026-08-10"],
               "Vodafone": ["2025-06-01", "2025-08-01", "2025-09-01",
                            "2025-10-01"]}
    a = auswertung(eintraege, punkte, _KATALOG, heute="2026-08-11",
                   termine_je_anbieter=termine)
    zugeordnet = {z["anbieter"]: z for z in a["nachfolger"]}
    assert len(zugeordnet) == len(a["nachfolger"]) == 2, a["nachfolger"]
    assert zugeordnet["expert"]["verweildauer_tage"] == 325
    assert zugeordnet["expert"]["noch_gelistet"] is True
    assert zugeordnet["Vodafone"]["verweildauer_tage"] == 12   # 19.09.-01.10.
    assert zugeordnet["Vodafone"]["noch_gelistet"] is False
    # Getrennte Preisreihen: 999 gegen 1349 am selben Tag.
    assert zugeordnet["expert"]["nach"][90] == 999.0
    assert zugeordnet["Vodafone"]["basis"] == 1399.0


# --------------------------------------------------------------------------
# Der Waechter gegen den ECHTEN Bestand
#
# Er nagelt die Lage vom 31.08.2026 fest: drei Messtage, laengste Spanne 20
# Tage, also keine einzige Lifecycle-Zeile. Faellt er durch, hat sich die
# DATENLAGE geaendert und nicht der Code - dann gehoert die Seite angesehen
# (Handover §8a: "nach etwa zwei weiteren Wochen Nachtlaeufen kippt es von
# selbst, dann ansehen").
# --------------------------------------------------------------------------

_WURZEL = Path(__file__).resolve().parents[1]
_DB = _WURZEL / "data" / "state" / "geraete_db.json"
_HISTORIE = _WURZEL / "data" / "state" / "geraete_preise.jsonl"


@pytest.mark.skipif(not _DB.exists(), reason="kein Geraete-Bestand im Checkout")
def test_der_echte_bestand_traegt_heute_keine_lifecycle_zeile():
    db = GeraeteDB(_DB)
    historie = Preishistorie(_HISTORIE)
    katalog = lade_katalog(_WURZEL)
    alle = db.eintraege()
    punkte = historie.alle_punkte()

    # Dieselbe Vorbereitung wie in `report/geraete_view.py`.
    termine_je_anbieter, laeufe_je_anbieter = {}, {}
    for name in {e.get("anbieter") for e in alle if e.get("anbieter")}:
        termine = set(db.messtermine(name))
        termine.update(p.get("datum") for p in punkte
                       if p.get("anbieter") == name and p.get("datum"))
        termine_je_anbieter[name] = sorted(termine)
        laeufe_je_anbieter[name] = int(db.laufbilanz(name).get("laeufe") or 0)

    a = auswertung(alle, punkte, katalog, heute="2026-08-31",
                   laeufe_je_anbieter=laeufe_je_anbieter,
                   termine_je_anbieter=termine_je_anbieter)

    spannen = [listungsdauer(e) for e in alle]
    laengste = max([s for s in spannen if s is not None], default=0)
    assert laengste < MIND_TAGE_JE_GERAET, (
        f"laengste Beobachtung {laengste} Tage - die Datenlage hat die "
        f"Schwelle genommen. Seite ansehen, nicht den Test anpassen.")

    assert a["duenn"] is True
    assert a["dauern"] == []
    assert a["verfaelle"] == [] and a["trends"] == []
    assert a["nachfolger"] == [], (
        "Nachfolger-Zeilen ohne 4 Messtermine ueber 21 Tage: "
        f"{[z['device_id'] for z in a['nachfolger']]}")
    # Die Portfolio-Tiefe traegt dagegen vollstaendig - sie braucht keine
    # Historie, nur den heutigen Bestand.
    assert a["portfolio"], "ohne Portfolio-Tiefe waere die Sektion leer"
    assert all(t["modelle_anzahl"] >= t["generationen"] for t in a["portfolio"])


def _echter_bestand(nachtlauf: bool = False, laeufe_ueberschreiben=None):
    """Der echte Bestand, wahlweise nach einem simulierten NACHTLAUF.

    Der Zustand von heute ist der, in dem dieses Feature SCHLAEFT: die
    laengste Beobachtung misst 20 Tage, die Schwelle 21. Wer nur ihn misst,
    misst nichts. `nachtlauf=True` bestaetigt jede aktive Listung auf den
    31.08.2026 und ergaenzt den Anbieter-Termin - der Zustand von morgen.
    """
    db = GeraeteDB(_DB)
    historie = Preishistorie(_HISTORIE)
    katalog = lade_katalog(_WURZEL)
    alle = [dict(e) for e in db.eintraege()]
    punkte = historie.alle_punkte()
    termine_je_anbieter, laeufe_je_anbieter = {}, {}
    for name in {e.get("anbieter") for e in alle if e.get("anbieter")}:
        termine = set(db.messtermine(name))
        termine.update(p.get("datum") for p in punkte
                       if p.get("anbieter") == name and p.get("datum"))
        termine_je_anbieter[name] = sorted(termine)
        laeufe_je_anbieter[name] = int(db.laufbilanz(name).get("laeufe") or 0)
    if nachtlauf:
        for e in alle:
            if e.get("status") == STATUS_AKTIV:
                e["last_verified"] = "2026-08-31"
        for name in termine_je_anbieter:
            termine_je_anbieter[name] = sorted(
                set(termine_je_anbieter[name]) | {"2026-08-31"})
    if laeufe_ueberschreiben is not None:
        laeufe_je_anbieter = {n: laeufe_ueberschreiben
                              for n in laeufe_je_anbieter}
    return alle, punkte, katalog, termine_je_anbieter, laeufe_je_anbieter


@pytest.mark.skipif(not _DB.exists(), reason="kein Geraete-Bestand im Checkout")
def test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen():
    """Der Waechter fuer den Zustand von MORGEN.

    Vor dem 31.08.2026 ergab derselbe simulierte Nachtlauf 85 Zeilen
    Verweildauer (alle "21 Tage", 11 unterscheidbare Texte, zwoelfmal
    dasselbe Geraet beim selben Haendler) und 85 Zeilen Preisverfall (alle
    "+0,0 %") - genau die zwei Bildschirmseiten, deren Abschaffung der
    Kommentarblock ueber `MIND_TERMINE_JE_GERAET` beschreibt.
    """
    alle, punkte, katalog, termine, laeufe = _echter_bestand(nachtlauf=True)
    a = auswertung(alle, punkte, katalog, heute="2026-08-31",
                   laeufe_je_anbieter=laeufe, termine_je_anbieter=termine)

    # Der Fall traete ohne die Zusicherungen wirklich ein: es GIBT genug
    # aktive Listungen mit 21 Tagen Spanne und unbewegtem Preis.
    kandidaten = [e for e in alle
                  if e.get("status") == STATUS_AKTIV
                  and listungsdauer(e) is not None
                  and listungsdauer(e) >= MIND_TAGE_JE_GERAET]
    assert len(kandidaten) >= 80, len(kandidaten)
    unbewegt = [e for e in kandidaten
                if preisverfall(e) and preisverfall(e)["absolut"] == 0]
    assert len(unbewegt) >= 80, len(unbewegt)

    # 1. Keine Zeile ohne Preisbewegung.
    assert all(v["absolut"] for v in a["verfaelle"]), \
        [v for v in a["verfaelle"] if not v["absolut"]][:3]
    assert a["ohne_bewegung"] == 0 or a["verfaelle"] == []

    # 2. Jede Verweildauer-Zeile ist ein eigener Regalplatz.
    schluessel = [(d["device_id"], d["anbieter"], d["zustand"])
                  for d in a["dauern"]]
    assert len(schluessel) == len(set(schluessel)), schluessel

    # 3. Keine Nachfolger-Zeile ueber Gebrauchtware.
    assert all(z["zustand"] == "neu" for z in a["nachfolger"]), \
        [(z["device_id"], z["anbieter"], z["zustand"]) for z in a["nachfolger"]]


@pytest.mark.skipif(not _DB.exists(), reason="kein Geraete-Bestand im Checkout")
def test_ohne_vollstaendigen_lauf_wird_nichts_zugerechnet():
    """B2 am echten Bestand: mobilcom-debitel steht bei `laeufe: 0`.

    `mark_stale` laeuft nur `if bilanz.vollstaendig` - aus dem Ausbleiben der
    Alterung folgt fuer diesen Anbieter nichts. Seine Prueftage vom 14. und
    21.08. stammen aus den Feldern ANDERER Listungen; der Lauf war gedeckelt,
    und ein Deckel ist kein Blick.
    """
    alle, punkte, katalog, termine, laeufe = _echter_bestand(nachtlauf=True)
    assert laeufe["mobilcom-debitel"] == 0, laeufe
    assert len(termine["mobilcom-debitel"]) >= MIND_TERMINE_JE_GERAET

    echt = auswertung(alle, punkte, katalog, heute="2026-08-31",
                      laeufe_je_anbieter=laeufe, termine_je_anbieter=termine)
    assert not [d for d in echt["dauern"] if d["anbieter"] == "mobilcom-debitel"]

    # Die Gegenprobe: EIN vollstaendiger Lauf, und dieselben Termine zaehlen.
    # Ohne sie belegte der Test nur, dass die Zeilen nie erscheinen.
    mit_lauf = dict(laeufe, **{"mobilcom-debitel": 1})
    b = auswertung(alle, punkte, katalog, heute="2026-08-31",
                   laeufe_je_anbieter=mit_lauf, termine_je_anbieter=termine)
    zugerechnet = [d for d in b["dauern"] if d["anbieter"] == "mobilcom-debitel"]
    assert zugerechnet, "die Zurechnung greift bei vollstaendigem Lauf"


@pytest.mark.skipif(not _DB.exists(), reason="kein Geraete-Bestand im Checkout")
def test_die_gegenprobe_je_anbieter_gegen_je_listung():
    """Die Messung, wegen der die Zaehlung umgestellt wurde.

    Festgenagelt ist nicht die Zahl (sie waechst mit jedem Nachtlauf),
    sondern die EIGENSCHAFT: verschiebt man dieselbe ANZAHL Prueftermine aus
    dem Fenster der Listungen heraus, muessen Zeilen verschwinden. Unter der
    alten Rechnung aendert sich nichts - sie zaehlt nur die Laenge der Liste.

    Zwei Stellschrauben halten die Messung auf der Termin-Bedingung: die
    Spannen des echten Bestands liegen unter 21 Tagen, deshalb wird
    `first_seen` fuer beide Laeufe gleich weit zurueckgesetzt; und der
    Laufzahl-Boden wuerde einen Anbieter mit >= 4 vollstaendigen Laeufen
    unabhaengig von jedem Termin durchlassen, deshalb steht er hier fuer alle
    auf 1 - das erlaubt die Zurechnung (B2) und traegt keine Zeile allein.
    """
    alle, punkte, katalog, termine_je_anbieter, laeufe = _echter_bestand(
        laeufe_ueberschreiben=1)
    assert all(n < MIND_TERMINE_JE_GERAET for n in laeufe.values())

    gedehnt = [{**e, "first_seen": "2020-01-01"} for e in alle]
    im_fenster = auswertung(gedehnt, punkte, katalog, heute="2026-08-31",
                            laeufe_je_anbieter=laeufe,
                            termine_je_anbieter=termine_je_anbieter)

    # Dieselbe Anzahl Termine je Anbieter, aber allesamt vor der ersten
    # Sichtung. Wer nur zaehlt, sieht keinen Unterschied.
    verschoben = {name: [f"2019-{1 + i % 12:02d}-01" for i in range(len(tage))]
                  for name, tage in termine_je_anbieter.items()}
    assert ([len(v) for v in verschoben.values()]
            == [len(termine_je_anbieter[n]) for n in verschoben]), \
        "die Gegenprobe muss dieselbe ANZAHL Termine stellen"
    ausserhalb = auswertung(gedehnt, punkte, katalog, heute="2026-08-31",
                            laeufe_je_anbieter=laeufe,
                            termine_je_anbieter=verschoben)

    assert im_fenster["dauern"], "ohne Durchlaesser prueft die Gegenprobe nichts"
    assert ausserhalb["dauern"] == [], (
        f"{len(ausserhalb['dauern'])} Zeilen aus Terminen ausserhalb jedes "
        f"Fensters")


# --------------------------------------------------------------------------
# Der Regalplatz, der Zustand und die Preisbewegung (Nachbesserung 31.08.2026)
#
# Drei Befunde eines simulierten Nachtlaufs, alle an echten Daten gemessen:
# 85 Verweildauer-Zeilen mit 11 unterscheidbaren Texten, 85 Preisverfaelle
# mit "+0,0 %", und als einzige Nachfolger-Zeile ein Gebrauchtgeraet.
# --------------------------------------------------------------------------

def _variante(lid, farbe="schwarz", speicher=256, zustand="neu", preis=1199.0,
              erstpreis=1449.0, device="apple-iphone-16-pro-max",
              anbieter="Medimax", first="2026-01-01", last="2026-04-01",
              status=STATUS_AKTIV):
    """Eine Farb-/Speichervariante EINES Regalplatzes."""
    e = _termin_eintrag(lid, device=device, anbieter=anbieter, first=first,
                        last=last, status=status, preis=preis,
                        erstpreis=erstpreis)
    e["sku_id"] = f"{device}-{speicher}gb-{farbe}" + (
        "" if zustand == "neu" else f"-{zustand}")
    e["speicher_gb"] = speicher
    e["farbe_normalisiert"] = farbe
    e["zustand"] = zustand
    return e


_VIER_TERMINE = {"Medimax": ["2026-01-01", "2026-02-01", "2026-03-01",
                             "2026-04-01"]}


def test_acht_farben_sind_ein_regalplatz_keine_acht_zeilen():
    """Der Befund: zwoelfmal "iPhone 17 Pro Max bei mobilcom-debitel -
    21 Tage" untereinander."""
    farben = [_variante(f"l{i}", farbe=f, preis=1199.0, erstpreis=1449.0)
              for i, f in enumerate(("schwarz", "weiss", "blau", "titan"))]
    # Der Fall tritt ohne die Zusicherung wirklich ein: vier Listungen, die
    # jede fuer sich die Schwelle nimmt.
    assert all(listungsdauer(e) == 90 for e in farben)

    a = auswertung(farben, [], _KATALOG, heute="2026-04-02",
                   termine_je_anbieter=_VIER_TERMINE)
    assert len(a["dauern"]) == 1, [d["modell"] for d in a["dauern"]]
    zeile = a["dauern"][0]
    assert zeile["tage"] == 90 and zeile["varianten"] == 4
    assert zeile["zustand"] == "neu"
    # Und der Preisverfall faellt ebenfalls in EINE Zeile, weil alle vier
    # denselben Speicher haben.
    assert len(a["verfaelle"]) == 1, a["verfaelle"]


def test_zwei_speichergroessen_sind_zwei_preise_aber_ein_regalplatz():
    """Der Unterschied zwischen den beiden Listen: 256 und 512 GB sind zwei
    Produkte mit zwei Preisen - ihr Verfall darf nicht in eine Zeile fallen.
    Im Regal steht trotzdem EIN Geraet."""
    gruppe = [_variante("a", speicher=256, preis=1199.0, erstpreis=1449.0),
              _variante("b", speicher=512, preis=1399.0, erstpreis=1749.0)]
    a = auswertung(gruppe, [], _KATALOG, heute="2026-04-02",
                   termine_je_anbieter=_VIER_TERMINE)
    assert len(a["dauern"]) == 1, "ein Regalplatz"
    assert len(a["verfaelle"]) == 2, "zwei Preise"
    assert {v["speicher_gb"] for v in a["verfaelle"]} == {256, 512}


def test_der_zustand_trennt_zwei_regalplaetze():
    """Neu und refurbished sind zwei Preise und zwei Regalplaetze - der
    ganze Geraetezweig fuehrt den Zustand in der `sku_id`, diese Datei war
    bis zum 31.08.2026 die einzige Stelle, die darueber hinweggruppierte."""
    gruppe = [_variante("neu", zustand="neu", preis=1199.0, erstpreis=1449.0),
              _variante("alt", zustand="refurbished", preis=799.0,
                        erstpreis=899.0)]
    a = auswertung(gruppe, [], _KATALOG, heute="2026-04-02",
                   termine_je_anbieter=_VIER_TERMINE)
    assert len(a["dauern"]) == 2
    assert {d["zustand"] for d in a["dauern"]} == {"neu", "refurbished"}
    assert {v["zustand"] for v in a["verfaelle"]} == {"neu", "refurbished"}


def test_ein_unbewegter_preis_ist_kein_preisverfall():
    """"+0,0 % seit 21 Tagen" ist kein Preisverfall, sondern der Beweis,
    dass noch nichts passiert ist. Verschwiegen wird er trotzdem nicht -
    `ohne_bewegung` zaehlt ihn."""
    steht = _variante("a", preis=1449.0, erstpreis=1449.0)
    faellt = _variante("b", speicher=512, preis=1299.0, erstpreis=1449.0)
    # Der Fall tritt wirklich ein: die Zeile waere sonst da, sie ist nur leer.
    assert preisverfall(steht)["prozent"] == 0.0

    a = auswertung([steht, faellt], [], _KATALOG, heute="2026-04-02",
                   termine_je_anbieter=_VIER_TERMINE)
    assert [v["speicher_gb"] for v in a["verfaelle"]] == [512]
    assert a["ohne_bewegung"] == 1
    # Die Verweildauer bleibt: ein Preis, der sich nicht bewegt, ist trotzdem
    # ein Geraet im Regal.
    assert len(a["dauern"]) == 1


def test_der_vertreter_einer_preisgruppe_ist_der_am_laengsten_beobachtete():
    """Nicht der billigste ("Der niedrigste Preis ist der wahrscheinlichste
    Fehler"), nicht der teuerste und nicht der erste der Liste.

    Der Fall ist so gebaut, dass die Regel die EINZIGE ist, die den richtigen
    Eintrag waehlt: die am laengsten beobachtete Variante ist weder die
    billigste noch die teuerste und steht in der Mitte der Liste.
    """
    lang = _variante("lang", farbe="schwarz", first="2026-01-01",
                     preis=1099.0, erstpreis=1449.0)
    kurz = _variante("kurz", farbe="weiss", first="2026-01-15",
                     preis=999.0, erstpreis=1449.0)
    # Der Fall tritt wirklich ein: BEIDE Varianten nehmen die Schwelle, die
    # kuerzere ist die billigere, und ohne die Regel gewaenne sie.
    einzeln = auswertung([kurz], [], _KATALOG, heute="2026-04-02",
                         termine_je_anbieter=_VIER_TERMINE)
    assert [v["aktuell"] for v in einzeln["verfaelle"]] == [999.0]
    assert preisverfall(kurz)["prozent"] < preisverfall(lang)["prozent"]

    # Die laengste steht ABSICHTLICH in der MITTE: sonst gewaenne auch ein
    # "nimm den ersten" oder "nimm den letzten", und der Test misst die
    # Listenreihenfolge statt der Regel.
    mittel = _variante("mittel", farbe="blau", first="2026-01-10",
                       preis=1199.0, erstpreis=1449.0)
    a = auswertung([kurz, lang, mittel], [], _KATALOG, heute="2026-04-02",
                   termine_je_anbieter=_VIER_TERMINE)
    assert len(a["verfaelle"]) == 1
    assert a["verfaelle"][0]["aktuell"] == 1099.0
    assert a["verfaelle"][0]["varianten"] == 3


def test_gebrauchtware_belegt_die_nachfolger_these_nicht():
    """Der Befund: die erste und einzige Zeile der Sektion war ein
    refurbished iPhone 15 bei ALDI TALK.

    Die These lautet "der Wettbewerb laesst das Vorjahresmodell als
    guenstigen EINSTIEG stehen" - ein Gebrauchtgeraet ist kein Einstieg ins
    Neugeraetesortiment."""
    alt = _variante("alt", zustand="refurbished", first="2025-01-01",
                    last="2026-08-10", anbieter="expert")
    a = auswertung([alt], [], _KATALOG, heute="2026-08-11",
                   termine_je_anbieter={"expert": ["2025-01-01", "2025-06-01",
                                                   "2026-01-01", "2026-08-10"]})
    # Der Fall tritt ohne die Zusicherung wirklich ein: die Listung nimmt
    # jede andere Bedingung, und ihr Geraet HAT einen Nachfolger im Katalog.
    assert [d["zustand"] for d in a["dauern"]] == ["refurbished"]
    assert _KATALOG.nachfolger_von("apple-iphone-16-pro-max") is not None
    assert a["nachfolger"] == [], a["nachfolger"]

    # Die Gegenprobe: dieselbe Listung als Neuware.
    neu = {**alt, "zustand": "neu"}
    b = auswertung([neu], [], _KATALOG, heute="2026-08-11",
                   termine_je_anbieter={"expert": ["2025-01-01", "2025-06-01",
                                                   "2026-01-01", "2026-08-10"]})
    assert [z["zustand"] for z in b["nachfolger"]] == ["neu"]


def test_ein_unbestimmbarer_zustand_gilt_nicht_als_neu():
    """"unbekannt" faellt heraus und wird NICHT als neu angenommen -
    dieselbe Regel wie in Vergleich und Preisgrafik."""
    unklar = _variante("u", zustand="unbekannt", first="2025-01-01",
                       last="2026-08-10", anbieter="expert")
    a = auswertung([unklar], [], _KATALOG, heute="2026-08-11",
                   termine_je_anbieter={"expert": ["2025-01-01", "2025-06-01",
                                                   "2026-01-01", "2026-08-10"]})
    assert a["nachfolger"] == []


def test_ein_gebrauchteintrag_nimmt_der_neuware_nicht_die_untergrenze():
    """Der teuerste Fehler, den diese Sektion machen kann - konstruiert.

    Die Neuware wird erst 31 Tage NACH dem Marktstart des Nachfolgers
    gesehen: ihre Verweildauer ist eine Untergrenze. Ein laenger beobachteter
    GEBRAUCHTeintrag desselben Geraets beim selben Haendler wuerde in einer
    gemischten Gruppe das `min(first_seen)` stellen - und aus der Untergrenze
    eine Messung machen.
    """
    # Marktstart des Nachfolgers: 2025-09-19.
    neuware = _variante("neu", zustand="neu", first="2025-10-20",
                        last="2026-08-10", anbieter="expert")
    gebraucht = _variante("alt", zustand="refurbished", first="2024-08-01",
                          last="2026-08-10", anbieter="expert")
    termine = {"expert": ["2024-08-01", "2025-10-20", "2026-01-01",
                          "2026-04-01", "2026-08-10"]}

    allein = auswertung([neuware], [], _KATALOG, heute="2026-08-11",
                        termine_je_anbieter=termine)
    assert len(allein["nachfolger"]) == 1
    assert allein["nachfolger"][0]["verweildauer_untergrenze"] is True

    # Der Fall tritt ohne die Trennung wirklich ein: gemeinsam gerechnet
    # liegt der Beginn 2024-08-01 und damit VOR dem Marktstart.
    gemischt = verweildauer_nach_nachfolger([neuware, gebraucht], _KATALOG)
    assert gemischt is None, "eine gemischte Gruppe darf nicht antworten"

    zusammen = auswertung([neuware, gebraucht], [], _KATALOG,
                          heute="2026-08-11", termine_je_anbieter=termine)
    assert len(zusammen["nachfolger"]) == 1, zusammen["nachfolger"]
    zeile = zusammen["nachfolger"][0]
    assert zeile["zustand"] == "neu"
    assert zeile["verweildauer_untergrenze"] is True, \
        "der Gebrauchteintrag hat der Neuware die Untergrenze genommen"
    assert zeile["beobachtet_seit"] == "2025-10-20"


# --------------------------------------------------------------------------
# Die Preisbasis, und die vier Regeln, die bis zum 31.08.2026 kein Test hielt
# --------------------------------------------------------------------------

def test_die_preisbasis_nimmt_nicht_den_gebrauchtpreis_desselben_tages():
    """Der Befund an echten Punkten:

        2026-08-29  o2  apple-iphone-15  schwarz              721,00  (neu)
        2026-08-29  o2  apple-iphone-15  schwarz-refurbished  613,00

    `_preis_am` nimmt bei gleichem Datum den LETZTEN Treffer der Liste - als
    Basis kaeme der Gebrauchtpreis, allein weil seine Zeile spaeter in der
    Datei steht.
    """
    neu = _variante("neu", zustand="neu", first="2025-01-01",
                    last="2026-08-10", anbieter="o2")
    gebraucht = _variante("alt", zustand="refurbished", first="2025-01-01",
                          last="2026-08-10", anbieter="o2")
    punkte = [
        {"listung_id": "neu", "device_id": "apple-iphone-16-pro-max",
         "anbieter": "o2", "datum": "2025-09-01", "preis_ohne_vertrag": 721.0},
        # Dieselbe Firma, dasselbe Geraet, derselbe Tag - aber gebraucht,
        # und die Zeile steht SPAETER in der Datei.
        {"listung_id": "alt", "device_id": "apple-iphone-16-pro-max",
         "anbieter": "o2", "datum": "2025-09-01", "preis_ohne_vertrag": 613.0},
    ]
    termine = {"o2": ["2025-01-01", "2025-09-01", "2026-01-01", "2026-08-10"]}

    # Der Fall tritt ohne die Zusicherung wirklich ein: ueber (Geraet,
    # Anbieter) gefiltert gewinnt der Gebrauchtpreis.
    ueber_anbieter = nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG,
                                       punkte, heute="2026-08-11",
                                       anbieter="o2")
    assert ueber_anbieter["basis"] == 613.0

    a = auswertung([neu, gebraucht], punkte, _KATALOG, heute="2026-08-11",
                   termine_je_anbieter=termine)
    assert len(a["nachfolger"]) == 1
    assert a["nachfolger"][0]["basis"] == 721.0, "der Neupreis ist die Basis"


def test_eine_fremde_preisreihe_ist_keine_basis():
    """M13 der Mutationsprobe: der Rueckfall von `_eigene_punkte` darf MIT
    Anbieter nicht auf die ganze Liste greifen.

    Die Docstring verspricht es woertlich, und bis zum 31.08.2026 meldete
    kein einziger von 735 Tests etwas, wenn man den Zweig herausnahm.
    """
    fremd = _punkte(("2025-08-01", 1449.0), ("2025-12-15", 999.0),
                    listung_id="fremd")          # anbieter="expert"
    # Der Fall tritt wirklich ein: fuer "expert" ergeben dieselben Punkte
    # sehr wohl eine Basis.
    assert nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG, fremd,
                             heute="2026-01-01", anbieter="expert") is not None
    assert nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG, fremd,
                             heute="2026-01-01", anbieter="Medimax") is None
    # Und ueber die Listungs-IDs derselbe Schutz.
    assert nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG, fremd,
                             heute="2026-01-01",
                             listung_ids={"eigen"}) is None
    assert nachfolger_effekt("apple-iphone-16-pro-max", _KATALOG, fremd,
                             heute="2026-01-01",
                             listung_ids={"fremd"}) is not None


def test_der_lauf_der_die_listung_zum_ersten_mal_sah_zaehlt_mit():
    """M1: die Fenstergrenze ist EINSCHLIESSLICH. Der Lauf, der eine Listung
    erstmals sah, ist ihr erster Messtermin - er hat sie ja gesehen.

    Der Fall ist so gebaut, dass genau dieser eine Tag entscheidet:
    `erstpreis_am` liegt bewusst NICHT auf `first_seen`, sonst faellt der
    Randtermin mit einem eigenen Beleg zusammen und die Regel ist nicht
    messbar. (Der rechte Rand ist immer `last_verified` und damit selbst ein
    eigener Beleg - dort kann die Frage nicht auftreten.)
    """
    eintrag = _termin_eintrag("l1", first="2026-01-01", last="2026-04-01")
    eintrag["erstpreis_am"] = "2026-02-15"
    # Eigene Belege: 15.02. und 01.04. Dazu zwei Prueftermine, einer davon
    # exakt auf `first_seen`.
    termine = {"Medimax": ["2026-01-01", "2026-03-01"]}
    a = auswertung([eintrag], [], _KATALOG, heute="2026-04-02",
                   laeufe_je_anbieter={"Medimax": 1},
                   termine_je_anbieter=termine)
    assert [d["tage"] for d in a["dauern"]] == [90], \
        "der Termin auf `first_seen` ist der vierte Messtag"

    # Der Fall tritt wirklich ein: einen Tag frueher liegt derselbe Termin
    # ausserhalb, und die Zeile faellt.
    davor = {"Medimax": ["2025-12-31", "2026-03-01"]}
    b = auswertung([eintrag], [], _KATALOG, heute="2026-04-02",
                   laeufe_je_anbieter={"Medimax": 1},
                   termine_je_anbieter=davor)
    assert b["dauern"] == []


def test_am_marktstag_selbst_gemessen_ist_keine_untergrenze():
    """M3: die Randbedingung von `beginn > start`.

    Wer am Tag des Marktstarts schon zusieht, hat den Regalplatz von Tag null
    an gemessen - das ist eine Messung, keine Untergrenze. Erst der Tag
    DANACH macht sie zu einer.
    """
    am_tag = verweildauer_nach_nachfolger(
        [_regal("2025-09-19", "2026-08-10")], _KATALOG)   # Marktstart
    assert am_tag["verweildauer_untergrenze"] is False
    einen_tag_spaeter = verweildauer_nach_nachfolger(
        [_regal("2025-09-20", "2026-08-10")], _KATALOG)
    assert einen_tag_spaeter["verweildauer_untergrenze"] is True
    assert am_tag["verweildauer_tage"] == einen_tag_spaeter["verweildauer_tage"]


def test_die_letzte_bestaetigung_ist_ein_messtag():
    """M12: `last_verified` gehoert in die eigenen Belege der Listung.

    Konstruiert so, dass genau er die Schwelle entscheidet: drei Termine im
    Fenster plus `erstpreis_am` ergeben drei verschiedene Tage, mit der
    letzten Bestaetigung sind es vier.
    """
    eintrag = _termin_eintrag("l1", first="2026-01-01", last="2026-04-01")
    termine = {"Medimax": ["2026-01-01", "2026-02-01", "2026-03-01"]}
    a = auswertung([eintrag], [], _KATALOG, heute="2026-04-02",
                   laeufe_je_anbieter={"Medimax": 1},
                   termine_je_anbieter=termine)
    assert [d["tage"] for d in a["dauern"]] == [90]

    # Der Fall tritt wirklich ein: ohne den vierten Tag faellt die Zeile.
    weniger = {"Medimax": ["2026-01-01", "2026-02-01"]}
    b = auswertung([eintrag], [], _KATALOG, heute="2026-04-02",
                   laeufe_je_anbieter={"Medimax": 1},
                   termine_je_anbieter=weniger)
    assert b["dauern"] == []
