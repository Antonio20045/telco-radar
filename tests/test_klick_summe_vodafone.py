"""Monatssumme als Echo für Rate und Tarif (Schnitt 8b Teil 2a).

Die Vodafone-Tarifauswahl nennt im Text nur Anzahlung und die Monatssumme aus Rate und
Tarif von Monat 1 bis 24 (Erkundung 10.10.2026, Zweig klick-erkundung d969c6e1,
klicks-3.json „Standardpreis 84,95 € – Angebotspreis 62,61 €“; mitschnitt-3.json
glados/v2/tariff/v2/hardware, Mobil M: Rate 33 €, Tarif 29,61 € Monat 1–24, Summe
62,61 €; Mobil XS: 33 € + 23,95 € = 56,95 €). Rate und Tarif gelten aus der Antwort
nur, wenn der Text dieselbe Summe nennt wie die Antwort und Rate plus Tarif sie auf den
Cent ergeben; sonst bleibt es ein Befund, nie still übernommen.
"""

from __future__ import annotations

import re

import pytest
from klickbeispiel import karte
from test_geraete_klickfolgeklick import KARTE as FOLGEKARTE
from test_geraete_klickfolgeklick import SUMMENKARTE

from telco_radar.collect.geraete.klickecho import (
    Antwortlesung,
    Variante,
    pruefe_echo,
)
from telco_radar.collect.geraete.klickkarte import KlickkartenFehler
from telco_radar.collect.geraete.klickkartentypen import (
    GRUND_NUR_BUENDEL,
    SUMMENFELD,
)
from telco_radar.collect.geraete.klicktext import Buendelwerte, Preiswerte
from telco_radar.tarif_model import Preisphase

VARIANTE = Variante("256 GB", "269", 36)
MOBIL_M = (1.0, 33.0, 29.61, 62.61)
MOBIL_XS = (1.0, 33.0, 23.95, 56.95)


def _antwort(anzahlung, rate, tarif, summe, phasen=None) -> Antwortlesung:
    werte = Preiswerte(
        anzahlung=anzahlung,
        rate=rate,
        ratenzahl=36,
        tarifphasen=phasen or (Preisphase(1, 24, tarif),),
    )
    return Antwortlesung(werte, {}, Buendelwerte(buendelbetrag=summe))


def _echo(antwort, text_summe, summe=True, anzahlung=1.0):
    text = Preiswerte(anzahlung=anzahlung, ratenzahl=36)
    return pruefe_echo(
        VARIANTE,
        VARIANTE,
        text,
        antwort,
        buendel=Buendelwerte(buendelbetrag=text_summe),
        summe=summe,
    )


@pytest.mark.parametrize("preise", [MOBIL_M, MOBIL_XS], ids=["mobil-m", "mobil-xs"])
def test_summe_bestaetigt_rate_und_tarif(preise):
    anzahlung, rate, tarif, summe = preise

    echo = _echo(_antwort(*preise), summe)

    assert echo.befunde == ()
    assert echo.werte.rate == rate
    assert echo.werte.tarifphasen == (Preisphase(1, 24, tarif),)
    assert echo.werte.anzahlung == anzahlung
    assert echo.buendel.buendelbetrag == summe


def test_gegenprobe_ohne_summe_fehlen_rate_und_tarif_im_text():
    echo = _echo(_antwort(*MOBIL_M), 62.61, summe=False)

    assert {b.feld for b in echo.befunde} == {"rate", "tarifphasen"}
    assert echo.werte.rate is None


def test_gegenprobe_text_nennt_eine_andere_summe():
    echo = _echo(_antwort(*MOBIL_M), 56.95)

    felder = {b.feld for b in echo.befunde}
    assert felder == {SUMMENFELD, "rate", "tarifphasen"}
    assert echo.werte.rate is None


def test_gegenprobe_rate_plus_tarif_ergibt_nicht_die_summe():
    echo = _echo(_antwort(1.0, 33.0, 29.60, 62.61), 62.61)

    gruende = {b.feld: b.grund for b in echo.befunde}
    assert "ergibt nicht die Summe 62,61" in gruende[SUMMENFELD]
    assert {"rate", "tarifphasen"} <= set(gruende)
    assert echo.werte.tarifphasen is None


def test_gegenprobe_zwei_tarifphasen_bestaetigt_die_summe_nicht():
    phasen = (Preisphase(1, 12, 29.61), Preisphase(13, 24, 39.61))
    echo = _echo(_antwort(1.0, 33.0, None, 62.61, phasen), 62.61)

    assert {b.feld for b in echo.befunde} == {"rate", "tarifphasen"}


def test_gegenprobe_text_ohne_summe():
    echo = _echo(_antwort(*MOBIL_M), None)

    assert {b.feld for b in echo.befunde} == {SUMMENFELD, "rate", "tarifphasen"}


ZWEI_VERTRAEGE = {
    "zusammenfassung": {
        "selektor": "#preis",
        "muster": {SUMMENFELD: r"Angebotspreis\s*([\d.,]+)\s*€"},
    },
}


def test_lader_erlaubt_den_buendelbetrag_als_summe_bei_zwei_vertraegen():
    geladen = karte(**SUMMENKARTE)

    assert not geladen.ein_vertrag
    assert geladen.summe
    assert not karte(**FOLGEKARTE).summe
    with pytest.raises(KlickkartenFehler, match=re.escape(GRUND_NUR_BUENDEL)):
        karte(**{**FOLGEKARTE, **ZWEI_VERTRAEGE})


def test_gegenprobe_einmalzahlung_bleibt_ein_buendelfeld():
    daten = {
        "zusammenfassung": {
            "selektor": "#preis",
            "muster": {"einmalzahlung": r"einmalig\s*([\d.,]+)\s*€"},
        }
    }
    with pytest.raises(KlickkartenFehler, match=re.escape(GRUND_NUR_BUENDEL)):
        karte(**{**FOLGEKARTE, **daten})


def test_fundort_der_summe_belegt_rate_und_tarif_nur_wenn_bestaetigt():
    from telco_radar.collect.geraete.klickecho import summenfundorte

    ort = ("#preis", "Angebotspreis 62,61 €")
    eigen = {"anzahlung": ("#preis", "Einmalig 1,00 €"), SUMMENFELD: ort}
    bestaetigt = _echo(_antwort(*MOBIL_M), 62.61).werte
    abgelehnt = _echo(_antwort(1.0, 33.0, 29.60, 62.61), 62.61).werte

    assert summenfundorte(eigen, bestaetigt) == {
        **eigen,
        "rate": ort,
        "tarifphasen": ort,
    }
    assert summenfundorte(eigen, abgelehnt) == eigen
