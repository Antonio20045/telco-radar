"""Gesamtkosten je Anbieter von Hand, mit den Zahlen der Anbieterseiten (20.11.2026).

Definition und Belege: `docs/geraete/gesamtkosten.md` (Vergleichsbasis: Tarif über
seine Mindestlaufzeit, ohne Bindung 24 Monate, Gerät bis zur letzten Rate). Jeder Fall
nennt die sichtbaren Zahlen der Seite und rechnet sie ohne `kosten_ueber` nach. Rot
gegen den Stand vor dem 20.11.2026: die Preishistorie fror die alte `tco_24` ein, eine
andere Zahl als Seite und Export, und 1&1 „36 Monate“ zählte 24 Beträge plus Ablöse.
"""

from __future__ import annotations

import csv
import io

import pytest

from telco_radar import rechenweise, versandkosten
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report import geraete_tco_view
from telco_radar.report.geraete_export import leitzahl_aus_zeile, tco_csv
from telco_radar.tarif_model import Preisphase
from telco_radar.tco_model import Buendel, kosten_ueber

HEUTE = "2026-11-20"


@pytest.fixture(autouse=True)
def _echter_versand(monkeypatch):
    """Diese Fälle rechnen mit dem belegten Versand aus `config/versandkosten.yaml`."""
    monkeypatch.setattr(versandkosten, "_TABELLE", None)


def _b(anbieter: str, **felder) -> Buendel:
    return Buendel(
        sku_id="apple-iphone-16-128gb-ultramarin",
        anbieter=anbieter,
        tarif_name=felder.pop("tarif_name", "Tarif L"),
        quelle_url="https://example.invalid/beleg",
        abgerufen_am=HEUTE,
        zustand="neu",
        **felder,
    )


def _telekom_24() -> Buendel:
    """telekom.de, iPhone 16 128 GB, MagentaMobil L: „59,95 €“, „24 Monate
    Vertragslaufzeit“, „Einmalige Zahlung 40,95 € inkl. Bereitstellung 39,95 €“
    (1 € Anzahlung), Gerät 969 € abzüglich „Geräte-Rabatt im Ratenkauf −200 €“ =
    769 € = 1 € + 24 × 32 €. Lieferung kostenlos."""
    return _b(
        "Telekom",
        tarif_name="MagentaMobil L",
        tarif_monatlich=59.95,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=32.0,
        laufzeit_monate=24,
        anschlusspreis=39.95,
    )


def _vodafone_36() -> Buendel:
    """vodafone.de, iPhone 16, Mobil L, 36 Raten: „Mindestlaufzeit des Tarifs:
    24 Monate“, „ab dem 25. Monat weiter für Dein Smartphone“, „1 € einmal“,
    „Standard-Versand 9,98 €“, „Kein Anschlusspreis“; Online-Preis 33,45 € Monat 1-24,
    Rate 27,00 €."""
    return _b(
        "Vodafone",
        tarif_name="Mobil L",
        tarif_monatlich=33.45,
        tarif_phasen=[Preisphase(1, 24, 33.45)],
        geraet_zuzahlung=1.0,
        geraet_monatsrate=27.0,
        laufzeit_monate=36,
        anschlusspreis=0.0,
    )


def _congstar_36() -> Buendel:
    """congstar.de, iPhone 16: „36 mtl. Zahlungen“, „Monatliche Kosten 20,00 €“,
    „Anzahlung 1,00 €“, „721,00 € Gesamtpreis“; Allnet Flat L „30,00 € mtl.“,
    „24 Monate Laufzeit“, „Einmalige Kosten 0,00 €“; Versand 4,99 €."""
    return _b(
        "congstar",
        tarif_name="Allnet Flat L",
        tarif_monatlich=30.0,
        tarif_bindung_monate=24,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=20.0,
        laufzeit_monate=36,
        anschlusspreis=0.0,
    )


def _einsundeins_36_fix() -> Buendel:
    """1und1.de, iPhone 16 128 GB, All-Net-Flat S, „36 Monate Fix“: Gerät 28,– €/Mon.
    plus Tarif 11,99 € = 39,99 € über 36 Monate (Sofortkauf 1008 € = 36 × 28),
    keine einmalige Gerätezahlung, Bereitstellung 39,90 €, kein Versand."""
    return _b(
        "1&1",
        tarif_name="1&1 All-Net-Flat S",
        buendel_monatlich=39.99,
        geraet_zuzahlung=0.0,
        laufzeit_monate=36,
        anschlusspreis=39.9,
    )


def _einsundeins_24_fix() -> Buendel:
    """Dieselbe Seite, „24 Monate Fix“: 42,– € Gerät plus 10,99 € Tarif."""
    return _b(
        "1&1",
        tarif_name="1&1 All-Net-Flat S",
        buendel_monatlich=52.99,
        geraet_zuzahlung=0.0,
        laufzeit_monate=24,
        anschlusspreis=39.9,
    )


def _tarifwelt_24() -> Buendel:
    """Tarifwelt (Schnittstelle 08.11.2026, `tests/fixtures/geraete/tarifwelt_mm_
    productdetail_iphone17_telekom_magenta_m_20261108.json`): Gerät einmalig 109,99 €,
    „Anschlusspreis Tarif“ 39,99 €, „Versandkosten“ 5,95 €, „Grundpreis Tarif“
    49,95 €, `contractTerm` 24, keine Geräterate."""
    return _b(
        "Saturn/MediaMarkt · Telekom-Netz",
        tarif_name="Magenta Mobil M",
        tarif_monatlich=49.95,
        geraet_zuzahlung=109.99,
        geraet_monatsrate=0.0,
        laufzeit_monate=24,
        anschlusspreis=39.99,
    )


FAELLE = {
    "telekom_24": (_telekom_24, 1 + 24 * 59.95 + 24 * 32 + 39.95, 24),
    "vodafone_36": (_vodafone_36, 1 + 24 * 33.45 + 36 * 27 + 0 + 9.98, 36),
    "congstar_36": (_congstar_36, 721 + 24 * 30 + 0 + 4.99, 36),
    "einsundeins_36_fix": (_einsundeins_36_fix, 36 * 39.99 + 0 + 39.9, 36),
    "einsundeins_24_fix": (_einsundeins_24_fix, 24 * 52.99 + 0 + 39.9, 24),
    "tarifwelt_24": (_tarifwelt_24, 109.99 + 24 * 49.95 + 0 + 39.99 + 5.95, 24),
}


@pytest.mark.parametrize("fall", sorted(FAELLE))
def test_gesamtkosten_wie_von_hand(fall):
    bauen, soll, monate = FAELLE[fall]
    k = kosten_ueber(bauen())
    assert k.luecken == []
    assert k.gesamt == round(soll, 2)
    assert k.monate == monate


def test_die_handzahlen_der_seiten():
    """Die Summen als Literale, damit eine geänderte Formel in FAELLE auffällt."""
    soll = {f: round(s, 2) for f, (_, s, _) in FAELLE.items()}
    assert soll == {
        "telekom_24": 2247.75,
        "vodafone_36": 1785.78,
        "congstar_36": 1445.99,
        "einsundeins_36_fix": 1479.54,
        "einsundeins_24_fix": 1311.66,
        "tarifwelt_24": 1354.73,
    }


def test_1und1_36_fix_als_vertrag_und_getrennt():
    """Getrennt gelesen (Tarif 11,99 € über 24 Monate Bindung + 36 × 28 € Raten) ist es
    die Vergleichsbasis der anderen Anbieter; der Vertrag zählt zusätzlich die
    Tarifmonate 25-36 (12 × 11,99 €), die 1&1 nicht getrennt ausweist."""
    getrennt = _b(
        "1&1",
        tarif_name="1&1 All-Net-Flat S",
        tarif_monatlich=11.99,
        tarif_bindung_monate=24,
        geraet_zuzahlung=0.0,
        geraet_monatsrate=28.0,
        laufzeit_monate=36,
        anschlusspreis=39.9,
    )
    vertrag = kosten_ueber(_einsundeins_36_fix()).gesamt
    assert round(vertrag - kosten_ueber(getrennt).gesamt, 2) == round(12 * 11.99, 2)


def test_seite_export_und_historie_tragen_dieselbe_zahl():
    """Ein Bündel, drei Leser: Karte der Seite, Zeile in `geraete-tco.csv`, Zeile der
    Preishistorie. Rot gegen den alten Stand: die Historie fror `tco_24` ein, die Seite
    rechnete 1&1 „36 Monate“ als 24 Beträge plus Ablöse."""
    for bauen, soll, _ in FAELLE.values():
        b = bauen()
        seite = karten._karte(b, None, None, None, {}, zustand="neu", heute=HEUTE)
        zeilen = geraete_tco_view._export_zeilen([b], [], [], None, {}, None, HEUTE)
        text, _ = tco_csv(zeilen)
        (export,) = list(csv.DictReader(io.StringIO(text), delimiter=";"))
        historie = TcoDB._historie_zeile(b, HEUTE)
        zahl = float(leitzahl_aus_zeile(export).replace(".", "").replace(",", "."))
        assert seite["gesamt"] == zahl == historie["gesamt"] == round(soll, 2), b.id


def test_export_nennt_die_einmalzahlung_des_geraets():
    """Bei der Tarifwelt ist sie der Gerätepreis, sonst die Anzahlung: ein Kopf für
    beide, „Gerät einmalig EUR“."""
    zeilen = geraete_tco_view._export_zeilen(
        [_tarifwelt_24(), _telekom_24()], [], [], None, {}, None, HEUTE
    )
    text, _ = tco_csv(zeilen)
    je = {r["Anbieter"]: r for r in csv.DictReader(io.StringIO(text), delimiter=";")}
    assert je["Saturn/MediaMarkt · Telekom-Netz"]["Gerät einmalig EUR"] == "109,99"
    assert je["Telekom"]["Gerät einmalig EUR"] == "1,00"
    assert not any("Anzahlung" in k or "Ablöse" in k for k in je["Telekom"])


def test_nur_1und1_bricht_am_umstellungstag_die_historie():
    """Die Umstellung vom 20.11.2026 ändert die eingefrorene Zahl nur bei 1&1 (neue
    Lesart „36 Monate Fix“, `rechenweise` Stufe 2). Eine Telekom-Zeile von gestern
    bleibt vergleichbar - ein echter Preissprung würde gemeldet."""
    gestern = {"gesamt": 1999.0}
    telekom = TcoDB._historie_zeile(_telekom_24(), HEUTE)
    eins = TcoDB._historie_zeile(_einsundeins_36_fix(), HEUTE)
    assert rechenweise.gleich(gestern, telekom)
    assert not rechenweise.gleich(gestern, eins)
