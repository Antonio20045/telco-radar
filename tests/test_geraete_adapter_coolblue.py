"""Coolblue-Adapter: deterministische synthetische Randfälle, KEINE Live-Preise.

Reale Abrufe müssen separat mit robots.txt und Quellenprotokoll geprüft werden.
"""

import json

import pytest

from telco_radar.collect.geraete import ADAPTER
from telco_radar.collect.geraete import coolblue
from telco_radar.collect.geraete.basis import GeraeteAbrufFehler
from telco_radar.geraete_config import lade_quellen

_URL = "https://www.coolblue.de/produkt/986132/apple-iphone-18-pro-256gb-hellblau.html"


def _html(*produkte):
    return "".join(
        '<script type="application/ld+json">'
        + json.dumps(produkt)
        + "</script>"
        for produkt in produkte
    )


def _produkt(url=_URL, preis="1449.00", waehrung="EUR"):
    return {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Apple iPhone 18 Pro 256GB Hellblau",
        "sku": "986132",
        "offers": {
            "@type": "Offer",
            "price": preis,
            "priceCurrency": waehrung,
            "url": url,
            "availability": "https://schema.org/InStock",
        },
    }


def test_coolblue_eindeutiger_barpreis_ohne_falschen_tarif():
    result = coolblue.lies(_html(_produkt()), _URL)
    assert len(result) == 1
    satz = result[0]
    assert satz["preis"] == 1449.0
    assert satz["url"] == _URL
    assert satz["quelle"] == "coolblue_produkt"
    assert satz["verfuegbarkeit"] == "lieferbar"
    assert not any(feld in satz for feld in ("tarif", "monatspreis", "monatsrate", "anzahlung"))


@pytest.mark.parametrize(
    "html",
    ["", "<html>Javascript erforderlich</html>", _html(_produkt(preis=None))],
)
def test_coolblue_unlesbarer_preis_ist_fehler_statt_nullbestand(html):
    with pytest.raises(GeraeteAbrufFehler):
        coolblue.lies(html, _URL)


def test_coolblue_verwirft_fremde_crossselling_produkte():
    andere = _produkt(url="https://www.coolblue.de/produkt/33333/anderes.html")
    result = coolblue.lies(_html(andere, _produkt()), _URL)
    assert len(result) == 1
    assert result[0]["url"] == _URL


def test_coolblue_ohne_originalquelle_keine_preiszuordnung():
    with pytest.raises(GeraeteAbrufFehler):
        coolblue.lies(_html(_produkt()), "https://www.coolblue.de/handys/smartphones")


def test_coolblue_mischung_ohne_eindeutige_zuordnung_ist_fehler():
    with pytest.raises(GeraeteAbrufFehler):
        coolblue.lies(_html(_produkt(), _produkt()), _URL)


def test_coolblue_konfiguriert_und_saturn_18_pro_erfasst():
    from pathlib import Path

    quellen = lade_quellen(Path(__file__).resolve().parents[1])
    cb = quellen.nach_name("Coolblue")
    assert cb is not None and cb.crawlbar
    assert cb.methode == "coolblue_produkt"
    assert cb.typ == "handel"
    assert "coolblue_produkt" in ADAPTER
    assert all(e.url.startswith("https://www.coolblue.de/") for e in cb.einstiege)
    assert all(e.pfadmuster == "/produkt/" for e in cb.einstiege)
    assert any(
        "iphone-18-pro" in e.url
        for e in quellen.nach_name("Saturn").einstiege
    )

def test_coolblue_verwirft_unbelegte_produktidentitaet():
    produkt = _produkt(url="")
    produkt.pop("sku")
    with pytest.raises(GeraeteAbrufFehler):
        coolblue.lies(_html(produkt), _URL)


def test_coolblue_verwirft_falsche_sku_auch_ohne_quelllink():
    produkt = _produkt(url="")
    produkt["sku"] = "123456"
    with pytest.raises(GeraeteAbrufFehler):
        coolblue.lies(_html(produkt), _URL)


def test_coolblue_kategorieseiten_umfassen_16_varianten():
    from pathlib import Path

    q = lade_quellen(Path(__file__).resolve().parents[1]).nach_name("Coolblue")
    assert q is not None
    assert q.max_produkte >= 16
