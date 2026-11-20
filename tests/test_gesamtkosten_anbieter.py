"""Gesamtkosten je Anbieter von Hand, mit den Zahlen der Anbieterseiten (20.11.2026).

Definition und Belege: `docs/geraete/gesamtkosten.md`. Gesamtkosten = was man mindestens
zahlt, um den Tarif über seine Mindestlaufzeit zu nutzen und das Gerät danach zu
besitzen. Jeder Fall nennt die sichtbaren Zahlen der Seite und rechnet sie ohne
`kosten_ueber` nach. Rot gegen den Stand vor dem 20.11.2026: `Buendel.anzahlung`/
`abloese` gab es nicht, und die Preishistorie fror für 1&1 „24+12“ die alte `tco_24`
ein (36 Beträge plus Ablöse), eine andere Zahl als Seite und Export.
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


def _einsundeins_24_plus_12() -> Buendel:
    """1und1.de, iPhone 16 128 GB, All-Net-Flat S, „24 + 12 Monate Flex“: Gerät
    28,– €/Mon., Tarif 11,99 €, Mindestlaufzeit 24 (`contractduration`); wer das
    Gerät nach Monat 24 behält, zahlt „12 weitere Raten“ = 336 € (Ablöse);
    Bereitstellung 39,90 €, kein Versand."""
    return _b(
        "1&1",
        tarif_name="1&1 All-Net-Flat S",
        buendel_monatlich=39.99,
        geraet_zuzahlung=336.0,
        laufzeit_monate=36,
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
    "einsundeins_24_plus_12": (_einsundeins_24_plus_12, 24 * 39.99 + 336 + 39.9, 24),
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
        "einsundeins_24_plus_12": 1335.66,
        "tarifwelt_24": 1354.73,
    }


def test_1und1_flex_gleich_ob_als_vertrag_oder_getrennt():
    """Dieselbe 1&1-Seite getrennt gelesen (24 × 11,99 Tarif + 36 × 28 Raten +
    39,90) ergibt dieselbe Zahl wie der Vertrag mit Ablöse."""
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
    assert (
        kosten_ueber(getrennt).gesamt == kosten_ueber(_einsundeins_24_plus_12()).gesamt
    )


def test_die_zuzahlung_ist_anzahlung_oder_abloese_nie_beides():
    eins = _einsundeins_24_plus_12()
    assert (eins.mit_abloese, eins.anzahlung, eins.abloese) == (True, None, 336.0)
    tk = _telekom_24()
    assert (tk.mit_abloese, tk.anzahlung, tk.abloese) == (False, 1.0, None)
    vierundzwanzig = _b(
        "1&1",
        buendel_monatlich=52.99,
        geraet_zuzahlung=0.0,
        laufzeit_monate=24,
        anschlusspreis=39.9,
    )
    assert (vierundzwanzig.anzahlung, vierundzwanzig.abloese) == (0.0, None)
    assert kosten_ueber(vierundzwanzig).gesamt == round(24 * 52.99 + 39.9, 2)


def test_seite_export_und_historie_tragen_dieselbe_zahl():
    """Ein Bündel, drei Leser: Karte der Seite, Zeile in `geraete-tco.csv`, Zeile der
    Preishistorie. Rot gegen den alten Stand: die Historie fror für 1&1 „24+12“
    36 × 39,99 + 336 + 39,90 = 1.815,54 € ein, Seite und Export zeigten 1.335,66 €."""
    for bauen, soll, _ in FAELLE.values():
        b = bauen()
        seite = karten._karte(b, None, None, None, {}, zustand="neu", heute=HEUTE)
        zeilen = geraete_tco_view._export_zeilen([b], [], [], None, {}, None, HEUTE)
        text, _ = tco_csv(zeilen)
        (export,) = list(csv.DictReader(io.StringIO(text), delimiter=";"))
        historie = TcoDB._historie_zeile(b, HEUTE)
        zahl = float(leitzahl_aus_zeile(export).replace(".", "").replace(",", "."))
        assert seite["gesamt"] == zahl == historie["gesamt"] == round(soll, 2), b.id
        assert historie[rechenweise.LEITZAHL_FELD] == rechenweise.LEITZAHL_REGEL


def test_export_trennt_anzahlung_und_abloese():
    zeilen = geraete_tco_view._export_zeilen(
        [_einsundeins_24_plus_12(), _telekom_24()], [], [], None, {}, None, HEUTE
    )
    text, _ = tco_csv(zeilen)
    je = {r["Anbieter"]: r for r in csv.DictReader(io.StringIO(text), delimiter=";")}
    assert (je["1&1"]["Anzahlung EUR"], je["1&1"]["Ablöse nach Monat 24 EUR"]) == (
        "",
        "336,00",
    )
    assert (
        je["Telekom"]["Anzahlung EUR"],
        je["Telekom"]["Ablöse nach Monat 24 EUR"],
    ) == (
        "1,00",
        "",
    )


def test_eine_historie_mit_anderer_regel_ist_kein_preissprung():
    """Die erste Zeile nach der Umstellung trägt `leitzahl_regel: 2`, die von gestern
    keine: der Bündelwächter vergleicht sie nicht (`rechenweise.gleiche_leitzahl`)."""
    alt = {"gesamt": 1815.54}
    neu = {"gesamt": 1335.66, **rechenweise.leitzahl(1335.66)}
    assert not rechenweise.gleiche_leitzahl(alt, neu)
    assert rechenweise.gleiche_leitzahl(neu, dict(neu))
    assert rechenweise.gleiche_leitzahl(alt, {"gesamt": 1800.0})
