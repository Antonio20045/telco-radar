"""o2 im Gerätelauf: nach dem Sammeln bleiben nur kaufbare Tarife (Entscheidung
Antonio, 21.11.2026; Kopf von `collect/geraete/o2_kaufbar.py`).

Der Weg ist derselbe wie im Nachtlauf: `geraete_pipeline.nachsammle_buendel` ruft
den Nachbearbeitungs-Haken des o2-Adapters mit dem robots-treuen `hole`; der liest
die Tarifübersicht einmal. Gespielt wird der Abruf aus der echten Antwort vom
21.11.2026 (`o2_tarifuebersicht_20261121.html.gz`), robots.txt antwortet 404
(keine Regeln). Die Bündel kommen aus der echten S26-Antwort desselben Tages.
"""

from __future__ import annotations

import gzip
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from telco_radar.collect.geraete import o2
from telco_radar.geraete_abruf import Abruf
from telco_radar.geraete_config import lade_quellen
from telco_radar.geraete_pipeline import nachsammle_buendel

_WURZEL = Path(__file__).resolve().parents[1]
_FIX = _WURZEL / "tests" / "fixtures" / "geraete"
_URL = (
    "https://www.o2online.de/e-shop/samsung/samsung-galaxy-s26-256gb-cobalt-violet"
    "-details?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36"
    "&vertragsart=ratenzahlung&tarif=o2-mobile-on-demand-m-plus"
)
_SLUGS = {
    "O2 Mobile Unlimited L Plus mit 300 MBit/s": "o2-mobile-unlimited-l-plus",
    "O2 Mobile Unlimited M Plus mit 100 MBit/s": "o2-mobile-unlimited-m-plus",
    "O2 Mobile Unlimited S Special Plus mit 15 MBit/s": (
        "o2-mobile-unlimited-s-special-plus"
    ),
    "O2 Mobile L Plus mit 150 GB+": "o2-mobile-l-plus",
    "O2 Mobile on Demand M Plus mit 50 GB+": "o2-mobile-on-demand-m-plus",
    "O2 Mobile Unlimited L mit 300 MBit/s": "o2-mobile-unlimited-l",
    "O2 Mobile Unlimited M mit 100 MBit/s": "o2-mobile-unlimited-m",
    "O2 Mobile Unlimited S Special mit 15 MBit/s": "o2-mobile-unlimited-s-special",
    "O2 Mobile Special": "o2-mobile-special",
    "O2 Mobile L mit 150 GB+": "o2-mobile-l",
    "O2 Mobile on Demand M mit 50 GB+": "o2-mobile-on-demand-m",
    "O2 Mobile S mit 15 GB+": "o2-mobile-s",
}
_NICHT_KAUFBAR = {
    "o2-mobile-unlimited-m",
    "o2-mobile-unlimited-s-special",
    "o2-mobile-special",
    "o2-mobile-l",
    "o2-mobile-on-demand-m",
    "o2-mobile-s",
}


def _gz(name: str) -> str:
    with gzip.open(_FIX / name, "rt", encoding="utf-8") as fh:
        return fh.read()


def _buendel() -> list[dict]:
    pv = o2.lies_konfiguration(_gz("o2_galaxy_s26_tarifoptionen_20261121.json.gz"))
    referenz = {
        o2._ohne_markup(o["displayValue"]): {
            "slug": _SLUGS[o2._ohne_markup(o["displayValue"])],
            "anschluss": 0.0,
        }
        for o in pv["tariff"]["tariffOptions"]
    }
    basis = {"strukturierter_name": "Samsung Galaxy S26", "sku": "x", "url": _URL}
    roh = o2.saetze_aus_konfiguration(pv, basis, referenz, _URL, {})
    return [{**s, "anbieter": "o2"} for s in roh]


def _lauf(antwort_uebersicht) -> tuple[set, list]:
    abrufe: list = []

    def hole(url, **kwargs):
        abrufe.append(url)
        if url.endswith("/robots.txt"):
            return Abruf(404, "")
        return antwort_uebersicht

    def uhr() -> datetime:
        return datetime(2026, 11, 21, 3, 0, tzinfo=UTC)

    bilanz = SimpleNamespace(name="o2", buendel=_buendel())
    nachsammle_buendel([bilanz], lade_quellen(_WURZEL), hole, uhr)
    return {s["tarif_slug"] for s in bilanz.buendel}, abrufe


def test_nachlauf_laesst_nur_kaufbare_o2_tarife():
    slugs, abrufe = _lauf(Abruf(200, _gz("o2_tarifuebersicht_20261121.html.gz")))
    assert not slugs & _NICHT_KAUFBAR
    assert "o2-mobile-unlimited-l" in slugs
    assert len(slugs) == 6
    assert [a for a in abrufe if not a.endswith("/robots.txt")] == [
        "https://www.o2online.de/tarife/"
    ]


def test_nachlauf_bei_ausfall_der_uebersicht_nur_produktseite():
    slugs, _ = _lauf(Abruf(503, ""))
    assert not slugs & (_NICHT_KAUFBAR | {"o2-mobile-unlimited-l"})
    assert len(slugs) == 5
    assert all(s.endswith("-plus") for s in slugs)
