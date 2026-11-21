"""o2: Tarife ohne „Plus“ werden gemessen und zählen im Gesamtkosten-Vergleich.

Entscheidung Antonio (21.11.2026): Im Vergleich zählt bei o2 der Tarif ohne „Plus“
(Preis ohne Bedingung). Bis hierher war jedes o2-Bündel außer dem gewählten Tarif einer
Antwort abgeleitet (`herleitung` „tarifsumme_minus_geraeterate“) und damit eine
Schätzung, die nicht zählt; o2 stand bei 8 von 102 Geräten im Vergleich.

Gemessen wird ein solches Bündel an seiner eigenen Seite (`geraete_o2_anschluss`,
Preiszusammenfassung mit gewähltem Tarif): Tarife ohne „Plus“ zuerst, weil nur sie
zählen. Eine Messung gilt `ANSCHLUSS_GUELTIG_TAGE` Tage für dasselbe Angebot (Rate,
Anzahlung, Tarifpreis, Raten); in dieser Zeit ist das Bündel gemessen, mit dem
Messdatum in `anschluss_gemessen_am`. Fixture: Redmi-17-Seite vom 21.11.2026.
"""

from __future__ import annotations

import gzip
from dataclasses import replace
from pathlib import Path

from test_geraete_o2_anschluss_stufe import ANGEBOT, HEUTE

from telco_radar import geraete_o2_anschluss as stufe_o2
from telco_radar.analyze.geraete_pruefstatus import buendel_zaehlt
from telco_radar.collect.geraete import o2
from telco_radar.tco_model import Buendel

PLUS = "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)"
_REDMI = (
    Path(__file__).parent
    / "fixtures"
    / "geraete"
    / ("o2_redmi17_tarifoptionen_20261121.json.gz")
)
_URL = (
    "https://www.o2online.de/e-shop/xiaomi/xiaomi-redmi-17-128gb-blue-5g-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36"
    "&vertragsart=ratenzahlung&tarif=o2-mobile-on-demand-m"
)


def _offen(**mehr) -> Buendel:
    felder = dict(
        sku_id="xiaomi-redmi-17-128gb-blue-5g",
        anbieter="o2",
        tarif_name="O2 Mobile on Demand M mit 50 GB+ (24 Mon.)",
        tarif_id="o2:o2-mobile-on-demand-m",
        tarif_monatlich=19.99,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=7.0,
        laufzeit_monate=36,
        quelle_url=_URL,
        abgerufen_am=HEUTE,
        herleitung=o2.HERLEITUNG_TARIFSUMME,
    )
    return Buendel(**{**felder, **mehr})


def _seite(url: str) -> str:
    return gzip.decompress(_REDMI.read_bytes()).decode()


def _zaehlt(b) -> bool:
    return buendel_zaehlt(
        b.herleitung, b.aktionen, HEUTE, b.pruefung, b.anbieter, b.tarif_name
    )


def test_gemessenes_angebot_der_woche_fuellt_die_heutige_luecke_und_zaehlt():
    """Gestern an der eigenen Seite gemessen, heute dasselbe Angebot ohne Anschluss."""
    alt = {
        "anschlusspreis": 39.99,
        "anschluss_gemessen_am": "2026-11-20",
        "herleitung": "",
        **ANGEBOT,
    }
    heute = _offen()
    assert heute.anschlusspreis is None and not _zaehlt(heute)
    b = stufe_o2.uebernimm(heute, alt, HEUTE)
    assert (b.herleitung, b.anschlusspreis, b.anschluss_gemessen_am) == (
        "",
        39.99,
        "2026-11-20",
    )
    assert _zaehlt(b)


def test_heute_gelesener_wert_wird_nie_ueberschrieben():
    """Clean Code 6 (Prüfung PR 207): 0,00 € heute aus der Fußnote gelesen, die Messung
    von gestern nennt 39,99 €. Der heutige Wert bleibt, das Bündel bleibt abgeleitet
    und wird nachgemessen; nennt er denselben Betrag, ist es gemessen."""
    alt = {
        "anschlusspreis": 39.99,
        "anschluss_gemessen_am": "2026-11-20",
        "herleitung": "",
        **ANGEBOT,
    }
    b = stufe_o2.uebernimm(_offen(anschlusspreis=0.0), alt, HEUTE)
    assert (b.anschlusspreis, b.herleitung, b.anschluss_gemessen_am) == (
        0.0,
        o2.HERLEITUNG_TARIFSUMME,
        "",
    )
    gleich = stufe_o2.uebernimm(_offen(anschlusspreis=39.99), alt, HEUTE)
    assert (gleich.herleitung, gleich.anschluss_gemessen_am) == ("", "2026-11-20")


def test_gegenprobe_geaendertes_angebot_bleibt_geschaetzt():
    alt = {"anschluss_gemessen_am": "2026-11-20", "herleitung": "", **ANGEBOT}
    alt["anschlusspreis"] = 39.99
    b = stufe_o2.uebernimm(_offen(tarif_monatlich=24.99), alt, HEUTE)
    assert b.herleitung == o2.HERLEITUNG_TARIFSUMME
    assert not _zaehlt(b)


def test_gegenprobe_nur_uebernommener_anschluss_ist_keine_messung():
    """Ein Bestandseintrag, der selbst abgeleitet blieb, macht nichts gemessen."""
    alt = {
        "anschlusspreis": 39.99,
        "anschluss_gemessen_am": "2026-11-20",
        "herleitung": o2.HERLEITUNG_TARIFSUMME,
        **ANGEBOT,
    }
    b = stufe_o2.uebernimm(_offen(anschlusspreis=0.0), alt, HEUTE)
    assert b.herleitung == o2.HERLEITUNG_TARIFSUMME


def test_vom_sammler_gemessener_tarif_gilt_ab_seinem_abrufdatum():
    """Der gewählte Tarif einer Antwort ist gemessen (`herleitung` leer), sein
    Messdatum ist `abgerufen_am`."""
    alt = {"anschlusspreis": 0.0, "abgerufen_am": "2026-11-19", "herleitung": ""}
    b = stufe_o2.uebernimm(_offen(anschlusspreis=0.0), {**alt, **ANGEBOT}, HEUTE)
    assert (b.herleitung, b.anschluss_gemessen_am) == ("", "2026-11-19")
    alt_acht = {**alt, "abgerufen_am": "2026-11-13", **ANGEBOT}
    assert stufe_o2.uebernimm(_offen(), alt_acht, HEUTE).herleitung != ""


def test_tarife_ohne_plus_werden_zuerst_gemessen():
    saetze = [_offen(tarif_name=PLUS), _offen(anschlusspreis=0.0), _offen()]
    assert stufe_o2.reihenfolge(saetze) == [2, 1, 0]


def test_messung_an_der_seite_macht_das_buendel_zaehlend():
    z: dict = {}
    (b,) = stufe_o2.nachmessen([_offen()], _seite, HEUTE, lambda: True, z)
    assert b.herleitung == "" and _zaehlt(b)
    plus = replace(b, tarif_name=PLUS)
    assert not _zaehlt(plus)
