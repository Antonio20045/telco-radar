"""o2: der offene Anschlusspreis eines abgeleiteten Tarifs wird nachgemessen.

Befund 21.11.2026: die automatische Gegenprobe (``data/state/gegenprobe/2026-11-21``)
fand 65 o2-Bündel mit gespeichertem Anschlusspreis ``None``, deren Seite mit gewähltem
Tarif den Betrag zeigt (39,99 € bei „O2 Mobile S“, 0,00 € bei „Special“ und
„Unlimited S Special Plus“). Die Antwort mit diesem Tarif nennt ihn in der
Preiszusammenfassung; ihre Adresse steht in der Tarifoption (``selectCall``). Nach
der Vertiefung holt ``o2_anschluss.nachmesse`` je offenem Satz genau diese Antwort,
solange Zeit ist. Bestätigt die Messung Angebot, Tarif, Rate, Anzahlung und
Tarifbetrag, ist der Satz gemessen; sonst bleibt die Lücke.
"""

import gzip
import json
from pathlib import Path

from telco_radar.collect.geraete import (
    ADAPTER,
    GeraeteAbrufFehler,
    o2,
    o2_anschluss,
    o2_tief,
)
from telco_radar.collect.geraete.o2_anschluss import ADRESSE, nachmesse

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_REDMI = "o2_redmi17_tarifoptionen_20261121.json.gz"
_URL = "https://www.o2online.de/e-shop/xiaomi/xiaomi-redmi-17-128gb-blue-5g-details"


def _satz(**mehr) -> dict:
    satz = {
        "angebot": "privatkunden-x-128gb-blau-36xhigh",
        "tarif_slug": "o2-mobile-s",
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 7.0,
        "tarif_monatlich": 19.99,
        "anschlusspreis": None,
        "herleitung": o2.HERLEITUNG_TARIFSUMME,
        ADRESSE: "https://www.o2online.de/e-shop/rest/configuration/s",
    }
    return {**satz, **mehr}


def _messung(**mehr) -> dict:
    g = {
        "angebot": "privatkunden-x-128gb-blau-36xhigh",
        "slug": "o2-mobile-s",
        "anzahlung": 1.0,
        "rate": 7.0,
        "tarif_rate": 19.99,
        "anschluss": 39.99,
    }
    return {**g, **mehr}


def _lauf(saetze, messung, weiter=lambda: True):
    abrufe: list[str] = []

    def abruf(url):
        abrufe.append(url)
        return {"antwort": url}

    z: dict = {}
    nachmesse(saetze, abruf, lambda pv: messung, weiter, z)
    return abrufe, z


def test_offener_anschluss_wird_gemessen():
    satz = _satz()
    abrufe, z = _lauf([satz], _messung())
    assert abrufe == ["https://www.o2online.de/e-shop/rest/configuration/s"]
    assert satz["anschlusspreis"] == 39.99
    assert "herleitung" not in satz and ADRESSE not in satz
    assert z[o2_anschluss.ZAEHLER_NACHGEMESSEN] == 1


def test_gegenprobe_widersprechende_messung_laesst_die_luecke():
    satz = _satz()
    _, z = _lauf([satz], _messung(rate=8.0))
    assert satz["anschlusspreis"] is None
    assert satz["herleitung"] == o2.HERLEITUNG_TARIFSUMME
    assert z[o2_anschluss.ZAEHLER_NACHMESSUNG_WIDERSPRICHT] == 1


def test_ohne_zeit_kein_abruf_und_keine_adresse_im_satz():
    satz = _satz()
    abrufe, z = _lauf([satz], _messung(), weiter=lambda: False)
    assert abrufe == [] and satz["anschlusspreis"] is None and ADRESSE not in satz
    assert z[o2_anschluss.ZAEHLER_NACHMESSUNG_FRIST] == 1


def test_belegter_anschluss_wird_nicht_nachgemessen():
    satz = _satz(anschlusspreis=0.0)
    abrufe, _ = _lauf([satz], _messung())
    assert abrufe == [] and ADRESSE not in satz


def test_abgeleiteter_satz_traegt_die_adresse_seiner_tarifoption():
    with gzip.open(_FIX / _REDMI, "rt", encoding="utf-8") as fh:
        pv = o2.lies_konfiguration(fh.read())
    optionen = {
        " ".join(o2._ohne_markup(o["displayValue"]).split()): o2._link(o)
        for o in pv["tariff"]["tariffOptions"]
    }
    referenz = {
        anzeige: {"slug": o2._gemessen(pv)["slug"] if i == 0 else f"s{i}"}
        for i, anzeige in enumerate(optionen)
    }
    gewaehlt = o2._gemessen(pv)["anzeige"]
    referenz[gewaehlt] = {"slug": "o2-mobile-on-demand-m", "anschluss": 39.99}
    roh = o2.saetze_aus_konfiguration(pv, {"strukturierter_name": "X"}, referenz, _URL)
    abgeleitet = [s for s in roh if s.get("herleitung")]
    assert abgeleitet
    assert {s[ADRESSE] for s in abgeleitet} <= set(optionen.values())

    abrufe, z = [], {}
    nachmesse(roh, lambda u: abrufe.append(u) or pv, o2._gemessen, lambda: True, z)
    assert len(abrufe) == len(abgeleitet)
    assert z[o2_anschluss.ZAEHLER_NACHMESSUNG_WIDERSPRICHT] == len(abgeleitet)
    assert not [s for s in roh if ADRESSE in s]


def _mitschnitt() -> dict:
    with gzip.open(_FIX / "o2_vertiefung_iphone17pro.json.gz", "rt") as fh:
        return json.load(fh)


def _gelaufen(weiter=None):
    m, protokoll, z = _mitschnitt(), [], {}

    def hole(url):
        protokoll.append(url)
        if url not in m["antworten"]:
            raise GeraeteAbrufFehler("nicht im Mitschnitt", status=404)
        return m["antworten"][url]

    katalog = o2.lies_buendel(json.dumps(m["katalog"]))
    return o2_tief.vertiefe_und_messe(hole, katalog, weiter, z), protokoll, z


def _kombi(saetze, slug):
    (satz,) = [
        s
        for s in saetze
        if (s["speicher_gb"], s["laufzeit_monate"], s["tarif_slug"]) == (256, 36, slug)
    ]
    return satz


def test_der_o2_adapter_misst_nach():
    assert ADAPTER["o2_katalog"].vertiefe_buendel is o2_tief.vertiefe_und_messe


def test_iphone_17_pro_256_wie_die_seite():
    """Mitschnitt 29.09.2026: die Seiten genau dieser Kombination nennen Anschluss
    0,00 € (Unlimited L) und 39,99 € (Mobile S); abgeleitet waren beide die Lücke.
    11 der 44 offenen Antworten liegen im Mitschnitt."""
    saetze, protokoll, z = _gelaufen()
    ul, s = _kombi(saetze, "o2-mobile-unlimited-l"), _kombi(saetze, "o2-mobile-s")
    assert (ul["anschlusspreis"], ul["tarif_monatlich"]) == (0.0, 39.99)
    assert (s["anschlusspreis"], s["tarif_monatlich"]) == (39.99, 14.99)
    assert "herleitung" not in ul and "herleitung" not in s
    assert not [x for x in saetze if ADRESSE in x]
    gemessen = z[o2_anschluss.ZAEHLER_NACHGEMESSEN]
    offen = z[o2_anschluss.ZAEHLER_NACHMESSUNG_WIDERSPRICHT]
    assert (gemessen, gemessen + offen) == (11, len(protokoll) - 15)


def test_gegenprobe_ohne_zeit_bleibt_die_luecke():
    zeit = iter([True] * 16)
    saetze, protokoll, z = _gelaufen(lambda: next(zeit, False))
    assert _kombi(saetze, "o2-mobile-s")["anschlusspreis"] is None
    assert o2_anschluss.ZAEHLER_NACHGEMESSEN not in z
    assert not [x for x in saetze if ADRESSE in x]


def test_nachmessung_endet_an_ihrer_hoechstzeit():
    """Die Uhr springt je Ablesung um 100 s: nach ``NACHMESSUNG_HOECHSTENS_S`` (600 s)
    misst sie nichts mehr, auch wenn die Frist des Anbieters noch Zeit gibt."""
    m = _mitschnitt()
    takt = iter(range(0, 10**6, 100))
    z: dict = {}

    def hole(url):
        if url not in m["antworten"]:
            raise GeraeteAbrufFehler("nicht im Mitschnitt", status=404)
        return m["antworten"][url]

    katalog = o2.lies_buendel(json.dumps(m["katalog"]))
    o2_tief.vertiefe_und_messe(hole, katalog, None, z, uhr=lambda: next(takt))
    versucht = z.get(o2_anschluss.ZAEHLER_NACHGEMESSEN, 0) + z.get(
        o2_anschluss.ZAEHLER_NACHMESSUNG_WIDERSPRICHT, 0
    )
    assert o2_tief.NACHMESSUNG_HOECHSTENS_S == 600.0
    assert versucht == 5 and z[o2_anschluss.ZAEHLER_NACHMESSUNG_FRIST] == 39
