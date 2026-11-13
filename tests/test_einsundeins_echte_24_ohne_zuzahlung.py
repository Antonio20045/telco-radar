"""1&1 P4 (Abdeckung 13.11.2026, Baupaket P4): echte 24 Monate sind KEIN „24 + 12“.

Befund der Live-Prüfung (Original + Store, 13.11.2026): 1&1 bietet neben dem
Standardvertrag „24 + 12" (= 36 Monate, Zuzahlung aus der Produktseite bestätigt)
auch eine echte 24-Monats-Laufzeit an (Klick-Erkundung 07.10.2026, Kacheln auf
`/flow2/mobile/ssc-private/tariffContractDuration`, siehe
`tests/test_klickkarte_1und1.py::test_zwei_kacheln_mit_24_und_24_plus_12`). Für
diese echten 24 Monate bestätigt KEINE Quelle eine Gerätezuzahlung: die Globalen
der Produktseite gelten nur für die 36-Monats-Variante
(`test_globale_bestaetigt_kachel_24_nie`), und die Kachel selbst wird seit
a1ed9e94 bewusst nie als Quelle für die Einmalzahlung genommen
(`test_kachel_24_bestaetigt_sich_selbst_ohne_einmalzahlung`). Store-Stichprobe vom
13.11.2026: alle 74 Bündel mit `laufzeit_monate == 24` bei 1&1 haben
`geraet_zuzahlung is None` - 0 von 74 mit einem Wert.

1&1 „24 + 12" ist deshalb fachlich KEINE 24-Monats-Finanzierung und wird nicht so
gezählt; die echte 24-Monats-Variante bleibt eine benannte Lücke
(`tco_kosten.POSTEN_ZUZAHLUNG`), nie ein erfundener Preis. Dieser Test sperrt die
Anzeige dafür fest: ein Satz, der die Lücke erklärt, statt sie stumm zu lassen.
"""

from __future__ import annotations

from telco_radar.report import geraete_laufzeit


def _karte(**overrides) -> dict:
    basis = {
        "anbieter": "1&1",
        "buendel_monatlich": 59.99,
        "zuzahlung": None,
        "raten_laufzeit": 24,
    }
    basis.update(overrides)
    return basis


def test_echte_24_ohne_zuzahlung_wird_erkannt():
    assert geraete_laufzeit.ist_echte_24_ohne_zuzahlung(_karte())


def test_24_plus_12_ist_keine_echte_24_ohne_zuzahlung():
    """36 Monate (= „24 + 12“) mit bestätigter Zuzahlung ist die andere Regel
    (`ist_24_plus_12`), nicht diese - beide schließen sich aus."""
    karte = _karte(zuzahlung=360.0, raten_laufzeit=36)
    assert not geraete_laufzeit.ist_echte_24_ohne_zuzahlung(karte)
    assert geraete_laufzeit.ist_24_plus_12(
        karte["buendel_monatlich"], karte["raten_laufzeit"]
    )


def test_echte_24_mit_zuzahlung_ist_keine_luecke():
    """Fände sich doch einmal eine bestätigte Zuzahlung zu echten 24 Monaten,
    ist das kein Fall dieser Regel - Zuzahlung erfunden wird hier nie."""
    assert not geraete_laufzeit.ist_echte_24_ohne_zuzahlung(_karte(zuzahlung=0.0))


def test_andere_anbieter_bei_24_monaten_ohne_zuzahlung_bleiben_unberuehrt():
    """Die Regel gilt nur bei 1&1 - ein anderer Anbieter ohne Zuzahlungsfeld
    ist ein anderer Fall (z. B. Tarif ohne Geräteanteil)."""
    assert not geraete_laufzeit.ist_echte_24_ohne_zuzahlung(_karte(anbieter="Vodafone"))


def test_regel_satz_erscheint_nur_mit_betroffener_karte():
    ohne = geraete_laufzeit.regel_echte_24_satz(
        [_karte(zuzahlung=360.0, raten_laufzeit=36)]
    )
    mit = geraete_laufzeit.regel_echte_24_satz([_karte()])

    assert ohne == ""
    assert mit == geraete_laufzeit.REGEL_ECHTE_24_OHNE_ZUZAHLUNG
    assert "24 + 12" in mit
    assert "keinen Gesamtpreis" in mit
