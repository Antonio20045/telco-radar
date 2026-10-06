"""`kosten_ueber`: was ein Bündel über H Monate kostet (Datenkonzept Geräte 5.3).

H ist der größere Wert aus Ratenlaufzeit N und Tarifbindung; die 36er-Ansicht
rechnet 36 Tarifmonate (Entscheidung 1). Ein gemessener Grundpreis ohne Preisphasen
ist nur für die Tarifbindung belegt (ohne Bindung 24 Monate); jeder Monat danach ohne
belegten Preis ist eine Lücke. Für H = 24 ist es dieselbe Zahl wie `tco_24`,
gegengeprüft an jedem Bündel des Schnappschusses. Die Tests importieren
`kosten_ueber` in der Testfunktion, damit ein fehlender Bau ein roter Test ist.
"""

from __future__ import annotations

import functools
import json

import pytest
from bestand_pfad import ZUSTAND

from telco_radar.report.geraete_tco_karten import phasen_fuer_buendel
from telco_radar.tarif_model import Preisphase
from telco_radar.tco_model import (
    AKTION_GERAETERABATT,
    AKTION_TRADE_IN,
    POSTEN_ANSCHLUSS,
    POSTEN_BUENDEL,
    POSTEN_LAUFZEIT,
    POSTEN_RABATTE,
    POSTEN_RATE,
    POSTEN_TARIF,
    POSTEN_ZUZAHLUNG,
    Aktion,
    Buendel,
    Rabatt,
    aktionen_aus,
    tco_24,
)

TARIF_24 = "Tarif über 24 Monate"
TARIF_36 = "Tarif über 36 Monate"
RATEN_36 = "Geräteraten über 36 Monate"
AB_25 = f"{POSTEN_TARIF} Monat 25–36"


def _o2(**kw) -> Buendel:
    """o2 iPhone 17 Pro 256 GB im L-Tarif: 36 Raten, Tarif 24 Monate gebunden."""
    felder = dict(
        sku_id="apple-iphone-17-pro-256gb-silber",
        anbieter="o2",
        tarif_name="O2 Mobile L Plus mit 150 GB+ (24 Mon.)",
        tarif_id="o2:o2-mobile-l",
        tarif_monatlich=19.99,
        tarif_bindung_monate=24,
        geraet_zuzahlung=1.00,
        geraet_monatsrate=36.50,
        laufzeit_monate=36,
        anschlusspreis=0.00,
    )
    felder.update(kw)
    return Buendel(**felder)


def _blatt(betrag: float) -> list[Preisphase]:
    """Ein Tarifblatt, das den Preis ohne Ende nennt: belegt auch ab Monat 25."""
    return [Preisphase(1, None, betrag)]


def _einsundeins(**kw) -> Buendel:
    """1&1 iPhone 15 im All-Net-Flat L: ein Vertrag, ein Monatsbetrag über 36 Monate."""
    felder = dict(
        sku_id="apple-iphone-15-128gb-blau",
        anbieter="1&1",
        tarif_name="1&1 All-Net-Flat L",
        buendel_monatlich=42.99,
        geraet_zuzahlung=0.00,
        laufzeit_monate=36,
        anschlusspreis=39.90,
    )
    felder.update(kw)
    return Buendel(**felder)


def test_36_raten_bei_24_monaten_bindung_zaehlen_zwoelf_tarifmonate_mehr():
    """1 + 36 × 19,99 + 36 × 36,50 + 0 = 2.034,64 €. `tco_24` zählt 24 Tarifmonate
    (1.794,76 €); der Abstand sind genau zwölf Monate Tarif, 12 × 19,99 = 239,88 €."""
    from telco_radar.tco_model import kosten_ueber

    b = _o2(tarif_phasen=_blatt(19.99))
    k = kosten_ueber(b, 36)
    assert k.posten == {
        TARIF_36: 719.64,
        POSTEN_ZUZAHLUNG: 1.00,
        RATEN_36: 1314.00,
        POSTEN_ANSCHLUSS: 0.00,
    }
    assert k.gesamt == 2034.64
    assert (k.monate, k.ratenlaufzeit, k.luecken) == (36, 36, [])
    assert k.monatlich == 56.52
    assert tco_24(b).gesamt == 1794.76
    assert round(k.gesamt - tco_24(b).gesamt, 2) == round(12 * 19.99, 2) == 239.88

    ausstieg = kosten_ueber(b, 24)
    assert ausstieg.gesamt == tco_24(b).gesamt == 1794.76
    assert ausstieg.posten[RATEN_36] == 1314.00, "alle 36 Raten bleiben geschuldet"


@pytest.mark.parametrize(
    ("bindung", "luecken_36", "luecken_24"),
    [
        (24, [AB_25], []),
        (None, [AB_25], []),
        (0, [AB_25], []),
        (36, [], [AB_25]),
    ],
)
def test_ein_grundpreis_ohne_phasen_ist_nur_fuer_die_bindung_belegt(
    bindung, luecken_36, luecken_24
):
    """Ohne Phasen gilt der gemessene Preis als Phase 1 bis Bindung, ohne Bindung bis
    24; ab Monat 25 nennt ihn die Seite nicht, also wird er nicht fortgeschrieben. Bei
    36 Monaten Bindung sind die Monate 25 bis 36 über 24 Monate geschuldet."""
    from telco_radar.tco_model import kosten_ueber

    b = _o2(tarif_bindung_monate=bindung)
    k = kosten_ueber(b, 36)
    assert k.luecken == luecken_36
    assert k.gesamt == (None if luecken_36 else 2034.64)
    assert (TARIF_36 in k.posten) == (not luecken_36)

    als_phase = _o2(
        tarif_bindung_monate=bindung, tarif_phasen=[Preisphase(1, 24, 19.99)]
    )
    assert kosten_ueber(als_phase, 36).luecken == [AB_25]

    vierundzwanzig = kosten_ueber(b, 24)
    assert vierundzwanzig.luecken == luecken_24
    assert vierundzwanzig.gesamt == (None if luecken_24 else 1794.76)
    assert tco_24(b).gesamt == 1794.76


def test_jeder_tarifmonat_zaehlt_zum_preis_seiner_phase():
    """„23,95 € für 24 Monate, danach 31,95 €“ (Datenkonzept, Regel 3) über 36 Monate:
    0,99 + 24 × 23,95 + 12 × 31,95 + 36 × 42,50 + 0 = 2.489,19 €."""
    from telco_radar.tco_model import kosten_ueber

    felder = dict(tarif_monatlich=23.95, geraet_zuzahlung=0.99, geraet_monatsrate=42.50)
    b = _o2(**felder)
    b.tarif_phasen = [Preisphase(1, 24, 23.95), Preisphase(25, None, 31.95)]
    k = kosten_ueber(b, 36)
    assert k.posten[TARIF_36] == 958.20
    assert k.gesamt == 2489.19
    assert round(k.gesamt - tco_24(b).gesamt, 2) == round(12 * 31.95, 2)

    durchgehend = kosten_ueber(_o2(tarif_phasen=_blatt(23.95), **felder), 36)
    assert durchgehend.gesamt == 2393.19 != k.gesamt
    assert kosten_ueber(_o2(**felder), 36).luecken == [AB_25]


def test_ohne_preis_ab_monat_25_ist_die_36er_zahl_eine_luecke():
    """Nennt die Bestellstrecke den Preis ab Monat 25 nicht, wird er nicht geraten."""
    from telco_radar.tco_model import kosten_ueber

    b = _o2(tarif_monatlich=23.95)
    b.tarif_phasen = [Preisphase(1, 24, 23.95)]
    k = kosten_ueber(b, 36)
    assert (k.gesamt, k.monatlich) == (None, None)
    assert k.luecken == [AB_25]
    assert TARIF_36 not in k.posten

    vierundzwanzig = kosten_ueber(b, 24)
    assert vierundzwanzig.luecken == []
    assert vierundzwanzig.gesamt == tco_24(b).gesamt == 1889.80


def test_eine_phasenluecke_unter_24_monaten_weicht_bewusst_von_tco_24_ab():
    """`tco_24` schreibt den letzten Preis fort (`phasensumme`), `kosten_ueber` nennt
    die Lücke. Im Schnappschuss kommt keine solche Phasenlücke vor."""
    from telco_radar.tco_model import kosten_ueber

    b = _o2(laufzeit_monate=24, tarif_phasen=[Preisphase(1, 12, 19.99)])
    k = kosten_ueber(b, 24)
    assert (k.gesamt, k.luecken) == (None, [f"{POSTEN_TARIF} Monat 13–24"])
    assert tco_24(b).gesamt == round(1 + 24 * 19.99 + 24 * 36.50, 2)


def test_ein_monat_mit_zwei_preisen_ist_eine_luecke():
    """Überlappende Phasen nennen zwei Preise für Monat 13 bis 24; keiner gilt."""
    from telco_radar.tco_model import kosten_ueber

    b = _o2(tarif_monatlich=20.00)
    b.tarif_phasen = [Preisphase(1, 24, 20.00), Preisphase(13, None, 25.00)]
    k = kosten_ueber(b, 36)
    assert k.gesamt is None
    assert k.luecken == [f"{POSTEN_TARIF} Monat 13–24"]

    b.tarif_phasen = [Preisphase(1, 12, 20.00), Preisphase(13, None, 25.00)]
    assert kosten_ueber(b, 36).gesamt == round(1 + 12 * 20 + 24 * 25 + 36 * 36.50, 2)


@pytest.mark.parametrize(
    ("bindung", "luecken", "gesamt"),
    [
        (24, [f"{POSTEN_TARIF} Monat 13–24"], None),
        (None, [f"{POSTEN_TARIF} Monat 13–24"], None),
        (0, [], 1458.40),
    ],
)
def test_ein_zeitraum_unter_der_bindung_laesst_keine_tarifmonate_weg(
    bindung, luecken, gesamt
):
    """Vodafone, 12 Raten, 24 Monate gebunden: über 12 Monate fehlen die geschuldeten
    Tarifmonate 13 bis 24. Pflicht über 24 Monate: 1 + 24 × 41,95 + 12 × 79,50 + 0 =
    1.961,80 €. Ohne Mindestlaufzeit ist nichts geschuldet: 1 + 12 × 41,95 + 954."""
    from telco_radar.tco_model import kosten_ueber

    b = _o2(
        laufzeit_monate=12,
        tarif_monatlich=41.95,
        geraet_monatsrate=79.50,
        tarif_bindung_monate=bindung,
    )
    k = kosten_ueber(b, 12)
    assert (k.gesamt, k.luecken) == (gesamt, luecken)
    assert kosten_ueber(b, 24).gesamt == tco_24(b).gesamt == 1961.80


def test_ein_vertrag_zaehlt_h_mal_den_buendelbetrag():
    """0 + 39,90 + 36 × 42,99 = 1.587,54 €, dieselbe Zahl wie `tco_24` für 1&1."""
    from telco_radar.tco_model import kosten_ueber, zeitraum

    b = _einsundeins()
    assert zeitraum(b) == 36
    k = kosten_ueber(b)
    assert k.posten == {
        f"{POSTEN_BUENDEL} über 36 Monate": 1547.64,
        POSTEN_ZUZAHLUNG: 0.00,
        POSTEN_ANSCHLUSS: 39.90,
    }
    assert (k.gesamt, k.monate, k.ratenlaufzeit) == (1587.54, 36, 36)
    assert k.gesamt == tco_24(b).gesamt
    assert k.monatlich == 44.10


@pytest.mark.parametrize("monate", [24, 48])
def test_ein_vertrag_ueber_einen_anderen_zeitraum_ist_eine_luecke(monate):
    """Vor Monat 36 fehlt die Einmalzahlung bei Kündigung, nach Monat 36 der Preis."""
    from telco_radar.tco_kosten import POSTEN_EINMALZAHLUNG
    from telco_radar.tco_model import kosten_ueber

    erwartet = {
        24: POSTEN_EINMALZAHLUNG,
        48: f"{POSTEN_BUENDEL} Monat 37–48",
    }[monate]
    k = kosten_ueber(_einsundeins(), monate)
    assert (k.gesamt, k.monate, k.luecken) == (None, monate, [erwartet])
    assert kosten_ueber(_einsundeins(), 36).gesamt == 1587.54


@pytest.mark.parametrize(
    ("felder", "erwartet"),
    [
        ({}, 36),
        ({"laufzeit_monate": 12}, 24),
        ({"laufzeit_monate": 24}, 24),
        ({"laufzeit_monate": 24, "tarif_bindung_monate": None}, 24),
        ({"laufzeit_monate": 24, "tarif_bindung_monate": 0}, 24),
        ({"laufzeit_monate": 36, "tarif_bindung_monate": 0}, 36),
        ({"laufzeit_monate": 12, "tarif_bindung_monate": 36}, 36),
    ],
)
def test_der_standardzeitraum_ist_der_groessere_wert(felder, erwartet):
    from telco_radar.tco_model import kosten_ueber, zeitraum

    b = _o2(tarif_phasen=_blatt(19.99), **felder)
    assert zeitraum(b) == erwartet
    k = kosten_ueber(b)
    assert k.monate == erwartet
    assert k.gesamt == kosten_ueber(b, erwartet).gesamt is not None


def test_ohne_ratenlaufzeit_gibt_es_keinen_zeitraum_und_keine_zahl():
    from telco_radar.tco_kosten import POSTEN_ZEITRAUM
    from telco_radar.tco_model import kosten_ueber, zeitraum

    b = _o2(laufzeit_monate=None)
    assert zeitraum(b) is None
    assert kosten_ueber(b).luecken == [POSTEN_ZEITRAUM, POSTEN_LAUFZEIT]
    k = kosten_ueber(b, 24)
    assert (k.gesamt, k.ratenlaufzeit, k.luecken) == (None, None, [POSTEN_LAUFZEIT])
    assert TARIF_24 in k.posten


@pytest.mark.parametrize(
    ("feld", "luecke"),
    [
        ("tarif_monatlich", POSTEN_TARIF),
        ("geraet_zuzahlung", POSTEN_ZUZAHLUNG),
        ("geraet_monatsrate", POSTEN_RATE),
        ("anschlusspreis", POSTEN_ANSCHLUSS),
    ],
)
def test_ein_fehlender_posten_ist_eine_luecke_und_nie_null(feld, luecke):
    from telco_radar.tco_model import kosten_ueber

    voll = kosten_ueber(_o2(), 24)
    assert voll.luecken == [] and voll.gesamt is not None
    k = kosten_ueber(_o2(**{feld: None}), 24)
    assert (k.gesamt, k.monatlich) == (None, None)
    assert k.luecken == [luecke]
    assert len(k.posten) == len(voll.posten) - 1


def test_boni_und_aktionen_gehen_nie_ein():
    """Ein Wechselbonus (6 × 10 €) und ein Trade-in (144 €) ändern nichts; ein
    eingerechneter Gerätrabatt steckt schon in der gemessenen Rate."""
    from telco_radar.tco_model import kosten_ueber

    quelle = "https://www.o2online.de/handys/apple-iphone-17-pro/"
    b = _o2(
        tarif_phasen=_blatt(19.99),
        rabatte=[Rabatt(name="Wechselbonus", betrag_monatlich=10.0, bis_monat=6)],
        aktionen=[
            Aktion(
                art=AKTION_TRADE_IN,
                bedingung="nur mit Eintausch eines Altgeräts",
                quelle_url=quelle,
                betrag=144.0,
            ),
            Aktion(
                art=AKTION_GERAETERABATT,
                bedingung="mit O2 Mobile L",
                quelle_url=quelle,
                betrag=100.0,
                eingerechnet=True,
            ),
        ],
    )
    assert b.rabatte[0].wert(36) == 60.0
    mit = kosten_ueber(b, 36)
    ohne = kosten_ueber(_o2(tarif_phasen=_blatt(19.99)), 36)
    assert (mit.gesamt, mit.posten, mit.luecken) == (ohne.gesamt, ohne.posten, [])
    assert mit.gesamt == 2034.64


def test_ohne_geraet_zaehlen_tarif_und_anschluss():
    """SIM-only: 24 × 29,99 + 39,99 = 759,75 €, wie `tco_24`. Ohne Mindestlaufzeit
    gibt es keinen Standardzeitraum; der Aufrufer nennt ihn."""
    from telco_radar.tco_kosten import POSTEN_ZEITRAUM
    from telco_radar.tco_model import kosten_ueber, zeitraum

    felder = dict(
        anbieter="o2",
        tarif_name="O2 Mobile L",
        tarif_monatlich=29.99,
        anschlusspreis=39.99,
    )
    b = Buendel(**felder)
    k = kosten_ueber(b)
    assert (k.gesamt, k.monate, k.ratenlaufzeit) == (759.75, 24, None)
    assert k.gesamt == tco_24(b).gesamt

    flex = Buendel(tarif_bindung_monate=0, **felder)
    assert zeitraum(flex) is None
    assert kosten_ueber(flex).luecken == [POSTEN_ZEITRAUM]
    assert kosten_ueber(flex, 24).gesamt == 759.75


@pytest.mark.parametrize("monate", [0, -12, True, 24.5, "36"])
def test_ein_zeitraum_ohne_ganze_positive_monatszahl_ist_ein_aufruffehler(monate):
    from telco_radar.tco_model import kosten_ueber

    with pytest.raises(ValueError, match="Zeitraum"):
        kosten_ueber(_o2(), monate)


@functools.cache
def _bestand() -> tuple[Buendel, ...]:
    """Jedes Bündel aus `state/geraete_tco.json`, mit Tarifbindung und Preisphasen aus
    `state/tarife.jsonl` und derselben Anreicherung wie die Seite."""
    tarife = {}
    for zeile in (ZUSTAND / "tarife.jsonl").read_text(encoding="utf-8").splitlines():
        satz = json.loads(zeile)
        tarife[satz.get("tarif_id") or ""] = satz
    stand = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    fertig = []
    for satz in stand["buendel"]:
        tarif = tarife.get(satz.get("tarif_id") or "") or {}
        b = Buendel(
            sku_id=satz["sku_id"],
            anbieter=satz["anbieter"],
            tarif_name=satz["tarif_name"],
            tarif_id=satz.get("tarif_id") or "",
            tarif_monatlich=satz.get("tarif_monatlich"),
            tarif_bindung_monate=tarif.get("laufzeit_monate"),
            buendel_monatlich=satz.get("buendel_monatlich"),
            geraet_zuzahlung=satz.get("geraet_zuzahlung"),
            geraet_monatsrate=satz.get("geraet_monatsrate"),
            laufzeit_monate=satz.get("laufzeit_monate"),
            anschlusspreis=satz.get("anschlusspreis"),
            aktionen=aktionen_aus(satz.get("aktionen")),
        )
        b.tarif_phasen = phasen_fuer_buendel(tarif, b.tarif_monatlich)
        fertig.append(b)
    return tuple(fertig)


def _gebunden_bis_24(b: Buendel) -> bool:
    return b.tarif_bindung_monate is None or b.tarif_bindung_monate <= 24


def _phasenpreis(b: Buendel, monat: int) -> float:
    """Der Preis eines Monats aus der einen Phase, die ihn nennt, ohne `phasensumme`."""
    treffer = [
        p.betrag
        for p in b.tarif_phasen
        if p.von_monat <= monat and (p.bis_monat is None or monat <= p.bis_monat)
    ]
    assert len(treffer) == 1, (b.id, monat)
    return treffer[0]


@pytest.mark.parametrize(("raten", "anzahl", "phasen"), [(24, 2268, 408), (12, 863, 0)])
def test_am_bestand_ist_es_bis_24_raten_dieselbe_zahl_wie_tco_24(raten, anzahl, phasen):
    """Datenkonzept 5.3: die 12er- und die 24er-Ansicht ändern keine Zahl. Preisphasen
    tragen im Schnappschuss nur congstar und Telekom."""
    from telco_radar.tco_model import kosten_ueber

    auswahl = [
        b for b in _bestand() if b.laufzeit_monate == raten and _gebunden_bis_24(b)
    ]
    mit_phasen = 0
    for b in auswahl:
        t = tco_24(b)
        assert set(t.luecken) <= {POSTEN_RABATTE}, (b.id, t.luecken)
        for k in (kosten_ueber(b, 24), kosten_ueber(b)):
            assert (k.gesamt, k.posten, k.luecken) == (t.gesamt, t.bestandteile, []), (
                b.id
            )
            assert (k.monate, k.ratenlaufzeit) == (24, raten), b.id
        mit_phasen += bool(b.tarif_phasen)
    assert (len(auswahl), mit_phasen) == (anzahl, phasen)


def test_am_bestand_zaehlen_36_raten_zwoelf_tarifmonate_nur_mit_belegtem_preis():
    """Jedes 36-Raten-Bündel mit höchstens 24 Monaten Bindung. Nennt ein Tarifblatt den
    Preis ohne Ende (congstar, Telekom), sind Kosten über 36 Monate minus `tco_24` zwölf
    Monate zu diesem Preis. Ohne Phasen ist nur die Bindung belegt, Monat 25 bis 36
    sind eine Lücke: o2, Vodafone (die Bestellstrecke misst 31,95 €, das Blatt nennt
    ohne Smartphone-Zuschlag 29,95 €) und congstar ohne Blatt."""
    from telco_radar.tco_model import kosten_ueber

    auswahl = [
        b
        for b in _bestand()
        if b.buendel_monatlich is None
        and b.laufzeit_monate == 36
        and _gebunden_bis_24(b)
    ]
    belegt = 0
    for b in auswahl:
        k, t = kosten_ueber(b, 36), tco_24(b)
        assert (k.monate, k.ratenlaufzeit) == (36, 36), b.id
        assert kosten_ueber(b).luecken == k.luecken, b.id
        assert k.posten[RATEN_36] == t.bestandteile[RATEN_36], b.id
        if not b.tarif_phasen:
            assert (k.gesamt, k.luecken) == (None, [AB_25]), b.id
            continue
        zwoelf = round(12 * _phasenpreis(b, 25), 2)
        assert k.luecken == [], b.id
        assert round(k.gesamt - t.gesamt, 2) == zwoelf > 0, b.id
        belegt += 1
    assert (len(auswahl), belegt) == (2354, 468)
    assert {b.anbieter for b in auswahl if b.tarif_phasen} == {"congstar", "Telekom"}


def test_am_bestand_rechnet_ein_vertrag_seine_laufzeit_wie_tco_24():
    """1&1: 36 × Bündelbetrag wie `tco_24`; ohne gemessene Anzahlung eine Lücke."""
    from telco_radar.tco_model import kosten_ueber

    vertraege = [b for b in _bestand() if b.buendel_monatlich is not None]
    vollstaendig = 0
    for b in vertraege:
        k, t = kosten_ueber(b), tco_24(b)
        assert (k.monate, k.ratenlaufzeit) == (36, 36), b.id
        if b.geraet_zuzahlung is None:
            assert (k.gesamt, k.luecken) == (None, [POSTEN_ZUZAHLUNG]), b.id
            assert POSTEN_ZUZAHLUNG in t.luecken, b.id
            continue
        assert (k.gesamt, k.posten, k.luecken) == (t.gesamt, t.bestandteile, []), b.id
        vollstaendig += 1
    assert (len(vertraege), vollstaendig) == (456, 75)
