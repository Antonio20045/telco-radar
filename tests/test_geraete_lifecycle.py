"""Die Lifecycle-Auswertung - deterministisch, ohne Modell.

Das eigentliche Wertversprechen der Seite und zugleich die Stelle, an der
sich am leichtesten luegen laesst: aus zwei Messpunkten eine Kurve zu
zeichnen ist trivial, und sie sieht gut aus. Deshalb steht in jedem
Ergebnis, worauf es beruht, und unter `_MIND_PUNKTE` Messpunkten heisst es
"Datenbasis noch duenn" - nicht "Trend".
"""
import pytest

from telco_radar.analyze.geraete_lifecycle import (
    MIND_PUNKTE,
    MIND_WOCHEN,
    auswertung,
    listungsdauer,
    nachfolger_effekt,
    portfolio_tiefe,
    preisverfall,
)
from telco_radar.analyze.geraete_store import (
    STATUS_AKTIV,
    STATUS_AUSGELISTET,
)
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
