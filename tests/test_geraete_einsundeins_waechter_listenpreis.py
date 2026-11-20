"""1&1: der Listenpreis-Wächter des Tarifaufschlags (E1, Prüfung PR 164).

`ergaenze_tarifstufen` überträgt den Aufschlag S->M vom FLEX-48-Raster auf
den FIX-24-Preis - das setzt voraus, dass der Aufschlag in beiden
Finanzierungsstufen gleich hoch ist, was eine Geräteseite allein nicht
belegt. `waechter_listenpreis` prüft stattdessen gegen die Listenpreise
ohne Gerät aus der Tarifübersicht (`data-tariff-price-hint`, Markup seit
20.11.2026: All-Net-Flat S 14,99 €, M 19,99 €, Differenz 5,00 € - passend
zum Rasteraufschlag aus den echten Fixtures). Die Tests hier nutzen
dieselben echten Abrufe wie `test_geraete_tarifstufen_einsundeins_2011.py`,
einmal unverändert (Wächter lässt durch) und einmal mit einem synthetisch
verschobenen Rasterpreis (Wächter verwirft).
"""

import gzip
from pathlib import Path

from telco_radar.collect.geraete import einsundeins as E
from telco_radar.collect.geraete.einsundeins_raten import (
    geraeteraten_preise,
    listenpreise_je_tarif,
    waechter_listenpreis,
)

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_TAG = "2026-11-20"

_ANF = "https://mobile.1und1.de/all-net-flat-vergleich"
_RASTER_S = "https://mobile.1und1.de/smartphones-all-net-flat-s"
_RASTER_M = "https://mobile.1und1.de/smartphones-all-net-flat-m"

_SEITEN = {
    "iphone-17": "iphone_17",
    "iphone-17e": "iphone_17e",
    "iphone-17-pro": "iphone_17_pro",
    "iphone-17-pro-max": "iphone_17_pro_max",
    "iphone-18-pro": "iphone_18_pro",
    "iphone-18-pro-max": "iphone_18_pro_max",
    "iphone-duo": "iphone_duo",
    "samsung-galaxy-s26": "galaxy_s26",
}


def _fixture(name: str) -> str:
    return gzip.open(_FIX / name, "rb").read().decode("utf-8", "replace")


def _netz() -> dict:
    return {
        _ANF: f"einsundeins_tarifuebersicht_all_net_flat_{_TAG}.html.gz",
        _RASTER_S: f"einsundeins_tarifraster_all_net_flat_s_{_TAG}.html.gz",
        _RASTER_M: f"einsundeins_tarifraster_all_net_flat_m_{_TAG}.html.gz",
    }


class _Hole:
    """Liefert dieselben gespeicherten Antworten wie `test_geraete_tarif
    stufen_einsundeins_2011.py` (echte Abrufe vom 20.11.2026); alles
    andere ist 404."""

    def __init__(self):
        self.netz = _netz()
        self.abgerufen: list = []

    def __call__(self, url, kopfzeilen=None, **kw):
        self.abgerufen.append(url)
        if url not in self.netz:
            return (404, "")
        return (200, _fixture(self.netz[url]))


def _basis() -> list:
    """Die Default-Tarif-Sätze der acht Pflichtmodell-Seiten."""
    out: list = []
    for slug, name in _SEITEN.items():
        url = f"https://mobile.1und1.de/{slug}"
        for satz in E.lies_buendel(
            _fixture(f"einsundeins_produktseite_{name}_{_TAG}.html.gz"), url=url
        ):
            out.append(
                {**satz, "anbieter": "1&1", "sku_id": satz["titel"], "quelle_url": url}
            )
    return out


def test_listenpreise_je_tarif_liest_die_echte_uebersicht():
    """S 14,99, M 19,99 - dieselbe Differenz (5,00) wie der Rasteraufschlag
    in `test_der_aufschlag_ist_die_rasterdifferenz_die_bindung_bleibt`."""
    text = _fixture(_netz()[_ANF])
    preise = listenpreise_je_tarif(text)
    assert preise["1&1 All-Net-Flat S"] == 14.99
    assert preise["1&1 All-Net-Flat M"] == 19.99


def test_waechter_laesst_den_heutigen_stand_unveraendert():
    """Regression: der Wächter darf die 23 hergeleiteten Sätze aus
    `test_die_pflichtmodelle_bekommen_wieder_buendel` nicht verwerfen."""
    saetze = _basis()
    vorher = len(saetze)
    neu = E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    assert neu == vorher == 23
    hergeleitet = [s for s in saetze if s.get("herleitung")]
    assert {s["tarif_name"] for s in hergeleitet} == {"1&1 All-Net-Flat M"}


def test_waechter_verwirft_tarif_bei_auseinanderlaufender_differenz(monkeypatch):
    """Synthetisch: das M-Raster wird um 1,00 € je Gerät angehoben (Aufschlag
    dann 6,00 statt 5,00), die Listenpreisdifferenz der Übersicht bleibt bei
    5,00 - mehr als 1 Cent Abweichung, der Wächter verwirft den ganzen Tarif,
    keine Tarifstufe entsteht."""
    saetze = _basis()
    original = E.lies_tarifraster

    def verschoben(text):
        gelesen = original(text)
        if gelesen.get("tarif_name") != "1&1 All-Net-Flat M":
            return gelesen
        return {
            "tarif_name": gelesen["tarif_name"],
            "preise": {
                hw: (cent + 100, monate)
                for hw, (cent, monate) in gelesen["preise"].items()
            },
        }

    monkeypatch.setattr(E, "lies_tarifraster", verschoben)
    neu = E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    assert neu == 0
    assert not any(s.get("herleitung") for s in saetze)


def test_waechter_laesst_durch_ohne_jede_listenpreis_angabe():
    """Trägt die Übersicht gar kein `data-tariff-price-hint` (ältere
    Fixtures vor dem 20.11.2026), gibt es keine belegte Zweitgröße - der
    Wächter blockiert dann nicht, sonst würde er jede Herleitung aus den
    älteren, noch gültigen Abrufen verwerfen (`test_geraete_tarifstufen_
    einsundeins.py`, echte Abrufe vom 29.09.2026)."""
    urteil = waechter_listenpreis({}, "S", "M", {"hw-1": 500})
    assert urteil == {"ok": True, "grund": "", "differenz_cent": None}


def test_waechter_verwirft_bei_fehlendem_listenpreis_trotz_anderer_eintraege():
    """Kennt die Übersicht zwar Listenpreise, aber nicht für diesen Tarif,
    ist das kein Fall von "keine Angabe" (voriger Test), sondern eine
    Lücke - lieber kein Preis als ein falscher."""
    urteil = waechter_listenpreis({"S": 14.99}, "S", "M", {"hw-1": 500})
    assert urteil["ok"] is False
    assert urteil["grund"] == "Listenpreis nicht lesbar"


def test_geraeteraten_preise_verwirft_mehrdeutige_ratenzahl():
    """Nennen zwei Stufen dieselbe Ratenzahl mit verschiedenen Beträgen,
    ist die Ratenzahl mehrdeutig - sie entfällt ganz, statt dass die erste
    gesehene gewinnt (E2, Prüfung PR 164). "24" und "36/flex" kommen hier
    beide auf 24 Raten (600,00 / 25,00), aber mit verschiedenem Betrag
    (34,99 vs. 37,99) - die Ratenzahl 24 entfällt, 36 bleibt unberührt."""
    eintrag = {
        "24": {
            "fix": {
                "hardwarePricePerMonth": "25.00",
                "hardwareTotalPrice": "600.00",
                "tariffPricePerMonth": "9.99",
                "tariffMonthlyPrices": [{"amount": 9.99, "begin": 1, "end": 24}],
            }
        },
        "36": {
            "fix": {
                "hardwarePricePerMonth": "20.00",
                "hardwareTotalPrice": "720.00",
                "tariffPricePerMonth": "9.99",
                "tariffMonthlyPrices": [{"amount": 9.99, "begin": 1, "end": 36}],
            },
            "flex": {
                "hardwarePricePerMonth": "25.00",
                "hardwareTotalPrice": "600.00",
                "tariffPricePerMonth": "12.99",
                "tariffMonthlyPrices": [{"amount": 12.99, "begin": 1, "end": 24}],
            },
        },
    }
    assert geraeteraten_preise(eintrag) == {36: 29.99}
