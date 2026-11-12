"""Händlerpreise gehören zu ihrer Zeile (Auftrag A-U825NA, 12.11.2026).

Befund A2: Die Matrixzeile „iPhone 17e 512 GB, Allnet Flat 50GB, 419,99 €"
verlinkte auf `…/iphone-17e/?speicher=512&tfi=…`. Diese Adresse zeigt im
Browser das iPhone 17e **256 GB Black** für 189,99 € mit dem Hinweis „nicht
verfügbar" — der Shop kennt `speicher` nicht und öffnet die vorgewählte
Variante. Mit `ogi`, `ofi` und `hwi` zeigt dieselbe Seite 512 GB Soft Pink,
419,99 €, „Versand in 2-4 Werktagen" (Messung 12.11.2026, Playwright).

Zweiter Befund: Lieferbarkeit stand nur in der früher gelesenen Übersicht.
Jetzt muss sie in DERSELBEN Antwort stehen wie der Preis (`stock`).

Jede Prüfung hat ihre Gegenprobe: die unveränderte Antwort gibt den Preis.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
from test_geraete_adapter_tarifwelt import LEITER, fixture_hole

from telco_radar.collect.geraete import tarifwelt_lauf

HEUTE = "2026-11-08"
MODELL = "apple-iphone-17"


def _lauf(aendere=None, modell: str = MODELL):
    """Der Lauf gegen die Fixtures; `aendere` verfälscht jede Detailantwort."""
    hole, _ = fixture_hole()

    def umgestellt(url, **kw):
        status, text = hole(url, **kw)
        rest = url.split("/v1/productdetail/")[1]
        if aendere is None or "/tariff?" in rest or "?" not in rest:
            return status, text
        daten = json.loads(text)
        if (daten.get("tariff") or {}).get("_id"):
            aendere(daten)
        return status, json.dumps(daten)

    return tarifwelt_lauf.lies_modell(
        modell, LEITER, umgestellt, HEUTE, warte=lambda s: None
    )


def _gruende(lauf) -> str:
    return " | ".join(grund for _, grund in lauf.luecken)


def _variante(daten: dict) -> dict:
    return daten["hardware"]["variants"][0]


def test_gegenprobe_unveraenderte_antwort_liefert_den_preis():
    lauf = _lauf()
    assert len(lauf.buendel) == 2
    assert all(b.geraet_zuzahlung in (419.99, 369.99) for b in lauf.buendel)


def test_anderes_geraet_in_der_antwort_bekommt_keinen_preis():
    """Der Kostenposten trägt weiter „iPhone 17 … 256 GB", nur die Hardware
    der Antwort ist eine andere. Ohne diese Prüfung wäre der Preis eines
    fremden Geräts nicht vom richtigen zu unterscheiden."""

    def anderes_geraet(daten):
        daten["hardware"]["name"] = "iPhone 17e"

    lauf = _lauf(anderes_geraet)
    assert lauf.buendel == []
    assert "'iPhone 17e' statt 'iPhone 17'" in _gruende(lauf)


def test_andere_hardware_id_bekommt_keinen_preis():
    def fremde_hardware(daten):
        _variante(daten)["ebootisId"] = "HW999999-9"

    lauf = _lauf(fremde_hardware)
    assert lauf.buendel == []
    assert "andere Hardware" in _gruende(lauf)


def test_anderer_speicher_der_variante_bekommt_keinen_preis():
    """Das Text-Label bleibt „256 GB", die gelieferte Variante ist 512 GB."""

    def anderer_speicher(daten):
        _variante(daten)["storage"] = 512

    lauf = _lauf(anderer_speicher)
    assert lauf.buendel == []
    assert "anderer Speicher" in _gruende(lauf)


@pytest.mark.parametrize("bestand", [0, -1])
def test_nicht_lieferbare_variante_bekommt_keinen_preis(bestand):
    def leer(daten):
        _variante(daten)["stock"] = bestand

    lauf = _lauf(leer)
    assert lauf.buendel == []
    assert f"nicht lieferbar (Bestand {bestand})" in _gruende(lauf)


def test_ohne_bestandsangabe_gibt_es_keinen_preis():
    def ohne(daten):
        _variante(daten).pop("stock")

    lauf = _lauf(ohne)
    assert lauf.buendel == []
    assert "kein Beleg fuer die Lieferbarkeit" in _gruende(lauf)


def test_gegenprobe_ein_stueck_auf_lager_genuegt():
    def eins(daten):
        _variante(daten)["stock"] = 1

    assert len(_lauf(eins).buendel) == 2


def test_zuzahlung_muss_der_barpreis_derselben_variante_sein():
    def abweichend(daten):
        _variante(daten)["price"] = 189.99

    lauf = _lauf(abweichend)
    assert lauf.buendel == []
    assert "weicht vom Geraetepreis" in _gruende(lauf)


def test_antwort_mit_mehreren_varianten_bekommt_keinen_preis():
    def zwei(daten):
        varianten = daten["hardware"]["variants"]
        varianten.append(dict(varianten[0], ebootisId="HW110228-2", storage=512))

    lauf = _lauf(zwei)
    assert lauf.buendel == []
    assert "2 Varianten statt 1" in _gruende(lauf)


def test_quelllink_zeigt_genau_diese_variante():
    """`speicher` und `tfi` allein öffnen die vorgewählte Variante; erst
    `ogi`, `ofi` und `hwi` machen den Link zum Beleg der Zeile."""
    lauf = _lauf()
    assert lauf.buendel
    for buendel in lauf.buendel:
        adresse = urlparse(buendel.quelle_url)
        assert adresse.netloc == "tarife.mediamarkt.de"
        werte = parse_qs(adresse.query)
        assert set(werte) == {"speicher", "tfi", "ogi", "ofi", "hwi"}
        assert werte["speicher"] == ["256"]
        assert werte["tfi"] == [buendel.tarif_id.split(":")[1]]
        assert werte["hwi"][0].count("_") == 1
        assert all(wert[0] for wert in werte.values())


def test_shop_url_traegt_die_ids_der_gelesenen_variante():
    ids = {"ogi": "G1", "ofi": "O1", "hwi": "H1_HW2-3"}
    adresse = tarifwelt_lauf.shop_url("apple", "iphone-17e", 512, "T1", ids)
    assert adresse == (
        "https://tarife.mediamarkt.de/smartphones/apple/iphone-17e/"
        "?speicher=512&tfi=T1&ogi=G1&ofi=O1&hwi=H1_HW2-3"
    )
