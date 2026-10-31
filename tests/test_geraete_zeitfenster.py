"""TCO-Preisverlauf: rollierende Zeitfenster ohne erfundene Messwerte."""
from datetime import date, timedelta

from telco_radar.report.geraete_zeitreihe import _fenster_serien


def _reihe(start, tage):
    return [
        ((start + timedelta(days=i)).isoformat(), float(i))
        for i in range(tage)
    ]


def test_30_tage_und_7_tage_relativ_zum_heutigen_datum():
    start = date(2025, 1, 1)
    serien = {"Telekom": _reihe(start, 400)}
    ende = (start + timedelta(days=399)).isoformat()
    monat = _fenster_serien(serien, "30t", ende)["Telekom"]
    woche = _fenster_serien(serien, "7t", ende)["Telekom"]
    assert len(monat) == 30
    assert len(woche) == 7
    assert monat[-1] == serien["Telekom"][-1]
    assert woche[0][0] == (start + timedelta(days=393)).isoformat()


def test_jahr_nimmt_letzte_echte_messung_jeder_siebentagesgruppe():
    start = date(2025, 1, 1)
    serien = {"o2": _reihe(start, 400)}
    ende = (start + timedelta(days=399)).isoformat()
    jahr = _fenster_serien(serien, "1j", ende)["o2"]
    assert len(jahr) <= 53
    assert jahr[-1] == serien["o2"][-1]
    assert all(p in serien["o2"] for p in jahr)


def test_keine_werte_erfinden_und_leeres_fenster_bleibt_leer():
    serien = {"Vodafone": [("2025-01-02", 1500.0), ("2025-01-05", 1350.0)]}
    assert _fenster_serien(serien, "7t", "2025-02-01") == {}
    assert _fenster_serien(serien, "alle", "2025-02-01") == serien


def test_ausduennung_nimmt_letzten_messtag_statt_mittelwert():
    serien = {"Telekom": [
        ("2025-04-01", 1000.0), ("2025-04-02", 1200.0),
        ("2025-04-03", 800.0), ("2025-04-04", 900.0),
    ]}
    gefiltert = _fenster_serien(serien, "90t", "2025-04-04")
    punkte = gefiltert["Telekom"]
    assert all(p in serien["Telekom"] for p in punkte)
    assert (sum(p[1] for p in punkte) / len(punkte)) not in {1000.0, 1200.0, 800.0, 900.0} or len(punkte) == 1
