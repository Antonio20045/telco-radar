"""Zusatz-Lesepfad B-TELEKOM-PRODUKTSEITE (08.11.2026): die Produktseite MIT
`tariffId` für Pflichtmodell-Varianten, die das Bestseller-Karussell der
Buendel-Kategorieseite an einem Tag nicht zeigt.

VIER ECHTE ABRUFE, ZWEI VARIANTEN x ZWEI TARIFE
------------------------------------------------
`telekom_produktseite_duo_512gb_xs_20261108.html.gz` und
`telekom_produktseite_duo_1tb_xs_20261108.html.gz` (MagentaMobil XS,
tariffId=MF_17779) sowie `..._512gb_s_...` und `..._1tb_s_...`
(MagentaMobil S, tariffId=MF_17785) - Apple iPhone Duo 512 GB/1 TB
Nachthimmel, abgerufen 08.11.2026 (curl, TelcoRadar/1.0, HTTP 200).
Herkunft in `tests/fixtures/geraete/_herkunft.json`.

DIE ERWARTETEN BETRÄGE SIND VON HAND GEGEN DIE ROHANTWORT NACHGERECHNET
------------------------------------------------------------------------
`productDetailed.installmentConfiguratorItems["24"]` trägt je Variante DREI
Anzahlungsstufen (399 / 860,65 / 1.229,50 EUR); die niedrigste gilt (Modulkopf
`telekom_zusatz.py`). Für `nachthimmel-512-gb`: Anzahlung 399,00 EUR, Rate
85,80 EUR (== finalRecurringPrice). Für `nachthimmel-1-tb`: Anzahlung
399,00 EUR, Rate 105,40 EUR. `productDetailsData.tariff.prices` trägt für
MF_17779 (MagentaMobil XS) 39,95 EUR Anschluss und 29,95 EUR/Monat, für
MF_17785 (MagentaMobil S) 39,95 EUR Anschluss und 39,95 EUR/Monat - beide
nur über die `id`, die mit der angefragten `tariffId` beginnt (die drei
weiteren `recurringFee`-Einträge der Seite sind primaryCard/secondaryCard/
kidsCard, keine Tarifgebühr).
"""

import gzip
from pathlib import Path

import pytest

from telco_radar.collect.geraete.basis import GeraeteAbrufFehler
from telco_radar.collect.geraete.telekom_zusatz import (
    lies_zusatz_variante,
    vertiefe_buendel,
)

_FIX = Path(__file__).parent / "fixtures" / "geraete"

_XS = "MF_17779"
_S = "MF_17785"


def _fixture(name: str) -> str:
    pfad = _FIX / name
    return gzip.open(pfad, "rb").read().decode("utf-8", "replace")


def _duo_512_xs() -> str:
    return _fixture("telekom_produktseite_duo_512gb_xs_20261108.html.gz")


def _duo_1tb_xs() -> str:
    return _fixture("telekom_produktseite_duo_1tb_xs_20261108.html.gz")


def _duo_512_s() -> str:
    return _fixture("telekom_produktseite_duo_512gb_s_20261108.html.gz")


def _duo_1tb_s() -> str:
    return _fixture("telekom_produktseite_duo_1tb_s_20261108.html.gz")


def test_512gb_bei_magentamobil_xs_centgenau():
    s = lies_zusatz_variante(
        _duo_512_xs(), "https://x", _XS, "apple-iphone-duo", "nachthimmel-512-gb"
    )
    assert s is not None
    assert s["geraet_zuzahlung"] == 399.0
    assert s["geraet_monatsrate"] == 85.8
    assert s["anschlusspreis"] == 39.95
    assert s["tarif_monatlich"] == 29.95
    assert s["tarif_name"] == "MagentaMobil XS"
    assert s["tarif_slug"] == _XS
    assert s["laufzeit_monate"] == 24
    assert s["speicher_gb"] == 512
    assert s["farbe"] == "nachthimmel"
    assert s["quelle"] == "telekom_produktseite_zusatz"


def test_1tb_bei_magentamobil_xs_centgenau():
    s = lies_zusatz_variante(
        _duo_1tb_xs(), "https://x", _XS, "apple-iphone-duo", "nachthimmel-1-tb"
    )
    assert s is not None
    assert s["geraet_zuzahlung"] == 399.0
    assert s["geraet_monatsrate"] == 105.4
    assert s["anschlusspreis"] == 39.95
    assert s["tarif_monatlich"] == 29.95
    assert s["speicher_gb"] == 1024


def test_512gb_bei_magentamobil_s_anderer_tarifpreis_gleiche_geraeterate():
    """Dieselbe Variante, anderer Tarif: Geraeterate unveraendert (reine
    Geraetefinanzierung, tarifunabhaengig), Tarifpreis ist der von S."""
    s = lies_zusatz_variante(
        _duo_512_s(), "https://x", _S, "apple-iphone-duo", "nachthimmel-512-gb"
    )
    assert s is not None
    assert s["geraet_zuzahlung"] == 399.0
    assert s["geraet_monatsrate"] == 85.8
    assert s["tarif_monatlich"] == 39.95
    assert s["tarif_name"] == "MagentaMobil S"
    assert s["tarif_slug"] == _S


def test_1tb_bei_magentamobil_s_centgenau():
    s = lies_zusatz_variante(
        _duo_1tb_s(), "https://x", _S, "apple-iphone-duo", "nachthimmel-1-tb"
    )
    assert s is not None
    assert s["geraet_zuzahlung"] == 399.0
    assert s["geraet_monatsrate"] == 105.4
    assert s["tarif_monatlich"] == 39.95


def test_gesamtbetrag_24_monate_nachgerechnet():
    """Die volle Rechenprobe: Anzahlung + 24 x (Geraet + Tarif) + Anschluss,
    centgenau gegen die Rohantwort (399 + 24x115,75 + 0, da Anschluss schon
    in den 39,95 EUR steckt - hier getrennt gefuehrt)."""
    s = lies_zusatz_variante(
        _duo_512_xs(), "https://x", _XS, "apple-iphone-duo", "nachthimmel-512-gb"
    )
    gesamt = (
        s["geraet_zuzahlung"]
        + s["anschlusspreis"]
        + s["laufzeit_monate"] * (s["geraet_monatsrate"] + s["tarif_monatlich"])
    )
    assert gesamt == pytest.approx(399.0 + 39.95 + 24 * (85.8 + 29.95), abs=0.005)


def test_falscher_tarif_liefert_keine_zahl():
    """Die Seite ist fuer MF_17779 abgerufen; wird ein anderer Tarif
    angefragt, passt `productDetailsData.tariff.id` nicht - Luecke, kein
    geratener Preis."""
    s = lies_zusatz_variante(
        _duo_512_xs(), "https://x", "MF_99999", "apple-iphone-duo", "nachthimmel-512-gb"
    )
    assert s is None


def test_falsche_variante_liefert_keine_zahl():
    """Der angefragte Variantenslug passt nicht zu `variantSlug` der
    Antwort - keine stille Uebernahme einer fremden Variante."""
    s = lies_zusatz_variante(
        _duo_512_xs(), "https://x", _XS, "apple-iphone-duo", "nachthimmel-1-tb"
    )
    assert s is None


def test_challenge_ohne_initial_state_wirft():
    with pytest.raises(GeraeteAbrufFehler):
        lies_zusatz_variante(
            "<html>Challenge</html>",
            "https://x",
            _XS,
            "apple-iphone-duo",
            "nachthimmel-512-gb",
        )


_ZUSATZ_KONFIG = [
    {
        "marke": "apple",
        "produkt_slug": "apple-iphone-duo",
        "produkt_name": "Apple iPhone Duo",
        "varianten": [
            {"variante_slug": "nachthimmel-512-gb", "speicher_gb": 512},
            {"variante_slug": "nachthimmel-1-tb", "speicher_gb": 1024},
        ],
    }
]


def _katalog_ohne_duo(tarif_slug: str) -> list[dict]:
    return [
        {
            "strukturierter_name": "Apple iPhone Duo",
            "speicher_gb": 256,
            "tarif_slug": tarif_slug,
        },
        {
            "strukturierter_name": "Samsung Galaxy S26",
            "speicher_gb": 256,
            "tarif_slug": tarif_slug,
        },
    ]


def test_vertiefe_holt_nur_die_fehlenden_zellen():
    abgerufen: list[str] = []

    def hole(url: str) -> str:
        abgerufen.append(url)
        if "nachthimmel-512-gb" in url:
            return _duo_512_xs()
        if "nachthimmel-1-tb" in url:
            return _duo_1tb_xs()
        raise AssertionError(f"unerwarteter Abruf: {url}")

    out = vertiefe_buendel(hole, _katalog_ohne_duo(_XS), zusatz=_ZUSATZ_KONFIG)
    assert len(abgerufen) == 2
    assert all(f"tariffId={_XS}" in u for u in abgerufen)
    speicher = {s["speicher_gb"] for s in out}
    assert speicher == {512, 1024}
    assert all(s["tarif_slug"] == _XS for s in out)


def test_vertiefe_ruft_nichts_ab_wenn_schon_vollstaendig():
    """Steht eine Speichergroesse schon im Katalog dieses Tarifs, wird sie
    NICHT erneut abgerufen - genau so viele Seitenaufrufe wie fehlende
    Zellen, nie mehr."""
    katalog = _katalog_ohne_duo(_XS) + [
        {
            "strukturierter_name": "Apple iPhone Duo",
            "speicher_gb": 512,
            "tarif_slug": _XS,
        },
        {
            "strukturierter_name": "Apple iPhone Duo",
            "speicher_gb": 1024,
            "tarif_slug": _XS,
        },
    ]
    abgerufen: list[str] = []

    def hole(url: str) -> str:
        abgerufen.append(url)
        raise AssertionError("keine Zelle fehlt - es darf nichts abgerufen werden")

    out = vertiefe_buendel(hole, katalog, zusatz=_ZUSATZ_KONFIG)
    assert abgerufen == []
    assert out == []


def test_vertiefe_ohne_konfiguration_ruft_nichts_ab():
    def hole(url: str) -> str:
        raise AssertionError("ohne zusatz-Konfiguration darf nichts abgerufen werden")

    assert vertiefe_buendel(hole, _katalog_ohne_duo(_XS), zusatz=[]) == []
    assert vertiefe_buendel(hole, _katalog_ohne_duo(_XS), zusatz=None) == []


def test_vertiefe_nicht_eindeutige_antwort_bleibt_luecke():
    """Ein Abruf, der nicht eindeutig ist (hier: Challenge-Seite statt
    __INITIAL_STATE__), liefert keinen Satz - und keinen Absturz."""

    def hole(url: str) -> str:
        return "<html>Challenge</html>"

    out = vertiefe_buendel(hole, _katalog_ohne_duo(_XS), zusatz=_ZUSATZ_KONFIG)
    assert out == []
