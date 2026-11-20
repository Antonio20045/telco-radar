"""1&1 seit 20.11.2026: ein Weg (Klick), kein Adapter; was vom Adapter bleibt.

Preise misst nur der Klick-Lauf (config/klickkarten/1und1.yaml). Vom Adapter
bleiben die Bereitstellungsgebühr der Tarifdetail-Seite (`klickanschluss`) und
die Rechnung eines Bündels mit nur `buendel_monatlich` (§ 13.2: der Monatsbetrag
wird nicht aufgeteilt).

`einsundeins_tarifdetails_anf_s.html.gz` ist der Tarifdetails-Iframe zu
`chosenTariff=tariff-anf-s-mvl&chosenDevice=hw-apple-iphone-17-pro`
(09.09.2026, HTTP 200, 48 112 B, Absender `TelcoRadar/1.0`).
"""

import gzip
from pathlib import Path

import pytest

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import ADAPTER
from telco_radar.collect.geraete.einsundeins import bereitstellungsgebuehr
from telco_radar.geraete_config import lade_quellen
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import POSTEN_ZUZAHLUNG, Buendel, kosten_ueber

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

_IPHONE_URL = "https://mobile.1und1.de/iphone-17-pro"


def _fixture(name: str) -> str:
    return gzip.open(_FIX / name, "rb").read().decode("utf-8", "replace")


def test_bereitstellungsgebuehr_mit_smartphone_aus_dem_echten_iframe():
    """S2-C, Kriterium 2: der echte Iframe nennt beide Beträge wortgleich
    ("ohne Smartphone: 19,90 € / mit Smartphone: 39,90 €"). Erhoben wird
    der MIT-Smartphone-Preis - das Bündel hat immer ein Gerät; der 19,90-
    Preis gehört zum SIM-only-Tarif und steht im Tarifbestand."""
    assert (
        bereitstellungsgebuehr(_fixture("einsundeins_tarifdetails_anf_s.html.gz"))
        == 39.9
    )


def test_iframe_ohne_die_zeile_setzt_nichts():
    """E1: ein Iframe ohne die Zeile ist eine gültige Tarifseite - None,
    kein Default, keine 0,00."""
    assert (
        bereitstellungsgebuehr(
            "<html><body>Tariftabelle ohne Bereitstellung</body></html>"
        )
        is None
    )


def test_die_einmalzahlung_steht_in_der_leitzahl():
    """S2-C, Kriterium 3: die gemessene Einmalzahlung zählt einmal mit:
    360 + 36 × 44,99 + 39,90 = 2.019,54 €. Ohne sie steht die Lücke, nicht 0,00."""
    komplett = Buendel(
        sku_id="apple-iphone-17-pro-256gb-cosmic-orange",
        anbieter="1&1",
        tarif_name="1&1 All-Net-Flat S",
        buendel_monatlich=44.99,
        geraet_zuzahlung=360.0,
        anschlusspreis=39.9,
        laufzeit_monate=36,
    )
    tco = kosten_ueber(komplett)
    assert tco.gesamt == pytest.approx(360.0 + 36 * 44.99 + 39.9)
    ohne_zuzahlung = Buendel(
        sku_id="apple-iphone-17-pro-256gb-cosmic-orange",
        anbieter="1&1",
        tarif_name="1&1 All-Net-Flat S",
        buendel_monatlich=44.99,
        anschlusspreis=39.9,
        laufzeit_monate=36,
    )
    tco_offen = kosten_ueber(ohne_zuzahlung)
    assert tco_offen.luecken == [POSTEN_ZUZAHLUNG]
    assert tco_offen.gesamt is None


def test_aus_rohsaetzen_reicht_buendel_monatlich_durch():
    """Der Durchgriff: ohne die Zeile in `aus_rohsaetzen` käme ein Satz
    mit EINEM Monatsbetrag still PREISLOS durch die Stufe - `Buendel`
    nimmt den Betrag nur an, wenn ihn jemand durchreicht (derselbe
    Fehlertyp wie die Positivliste `_MESSFELDER` im Store)."""
    bestand = Tarifbestand(
        [
            {
                "tarif_id": "11:1-1-all-net-flat-s",
                "anbieter": "1&1",
                "name": "1&1 All-Net-Flat S",
                "grundgebuehr": 14.99,
            }
        ]
    )
    bilanz = aus_rohsaetzen(
        [
            {
                "anbieter": "1&1",
                "tarif_name": "1&1 All-Net-Flat S",
                "sku_id": "apple-iphone-17-pro-256gb-cosmic-orange",
                "buendel_monatlich": 44.99,
                "laufzeit_monate": 36,
                "quelle_url": _IPHONE_URL,
            }
        ],
        bestand,
        "2026-09-08",
    )
    assert len(bilanz.buendel) == 1
    assert bilanz.buendel[0].buendel_monatlich == 44.99
    assert kosten_ueber(bilanz.buendel[0]).posten == {
        "Bündelpreis (Tarif und Gerät zusammen) über 36 Monate": 1619.64
    }


def test_kein_adapter_fuer_1und1():
    """Ein Weg je Anbieter: 1&1 trägt die Methode `klick`, kein Adapter liest es."""
    anbieter = lade_quellen(_WURZEL).nach_name("1&1")
    assert anbieter.methode == "klick"
    assert "einsundeins_buendel" not in ADAPTER
    assert anbieter.methode not in ADAPTER


def test_die_konfiguration_hat_keinen_einstieg_des_geraetelaufs():
    """Seit 20.11.2026 kein Einstieg des Gerätelaufs für 1&1: die Kategorieseite
    wird nicht mehr geerntet, Preise kommen nur aus dem Klick-Lauf
    (`erfassung: klick`)."""
    quellen = lade_quellen(_WURZEL)
    anbieter = next(a for a in quellen.anbieter if a.name == "1&1")
    assert [e.kind for e in anbieter.einstiege] == []
    assert (anbieter.crawlbar, anbieter.erfassung) == (False, "klick")
