"""P3-E3: Aktionen als Felder mit Bedingung und Quelle.

Vorlage ist der congstar-TRADE_IN-Fall aus gespeicherten echten Abrufen
(`tests/fixtures/geraete/congstar_*.html.gz`): die Trade-in-Zahlweise
senkt den Gesamtbetrag um `benefit.amount`, aber nur mit Altgeraet - sie
steht neben der Leitzahl, nie in ihr. Die Nachlaesse, die im gemessenen
Preis schon stecken (Geraeterabatt im Tarif, Grundpreisnachlass,
geschenkter Anschlusspreis), stehen als `eingerechnet` daneben.
"""

from __future__ import annotations

import gzip
from dataclasses import asdict
from pathlib import Path

import pytest

from telco_radar.analyze.tco_store import TcoDB
from telco_radar.collect.geraete import congstar
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report.geraete_tco_view import _aus_speicher, _BUENDEL_FELDER
from telco_radar.tco_model import (
    AKTION_ANSCHLUSS_ERLASSEN,
    AKTION_GERAETERABATT,
    AKTION_TARIFRABATT,
    AKTION_TRADE_IN,
    POSTEN_RABATTE,
    Aktion,
    Buendel,
    aktionen_aus,
    tco_24,
)

FIX = Path(__file__).parent / "fixtures" / "geraete"
TARIFSEITE_M = "https://www.congstar.de/handytarife/allnet-flat-tarife/allnet-flat-m/"


def _text(name: str) -> str:
    with gzip.open(FIX / name, "rt", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def saetze_m():
    return congstar.lies_buendel(
        _text("congstar_tarifseite_allnet_flat_m.html.gz"), TARIFSEITE_M
    )


def _satz(saetze, titel_teil, tarif, laufzeit):
    treffer = [
        s
        for s in saetze
        if titel_teil in s["titel"]
        and s["tarif_name"] == tarif
        and s["laufzeit_monate"] == laufzeit
    ]
    assert treffer, f"kein Satz {titel_teil} / {tarif} / {laufzeit}"
    return treffer[0]


def _art(satz, art):
    gefunden = [a for a in satz["aktionen"] if a["art"] == art]
    assert len(gefunden) == 1, (art, satz["aktionen"])
    return gefunden[0]


def test_trade_in_ist_die_differenz_der_zwei_gesamtbetraege(saetze_m):
    """iPhone 17 Pro 512 GB, ANF M: ohne Eintausch 1303 in beiden
    Zahlweisen, mit Eintausch 1033 (36 Raten) bzw. 919 (24 Raten) - die
    Aktion traegt genau die Differenz, nicht eingerechnet."""
    s36 = _satz(saetze_m, "iPhone 17 Pro 512 GB", "Allnet Flat M", 36)
    s24 = _satz(saetze_m, "iPhone 17 Pro 512 GB", "Allnet Flat M", 24)
    t36, t24 = _art(s36, AKTION_TRADE_IN), _art(s24, AKTION_TRADE_IN)
    assert t36["betrag"] == 1303 - 1033 == 270
    assert t24["betrag"] == 1303 - 919 == 384
    assert t36["eingerechnet"] is False and t24["eingerechnet"] is False
    assert t36["bedingung"] == congstar.TRADE_IN_BEDINGUNG
    assert t36["quelle_url"] == TARIFSEITE_M
    assert s36["geraet_monatsrate"] == 33.5
    assert s36["geraet_zuzahlung"] + 36 * s36["geraet_monatsrate"] == 1303


def test_die_eingerechneten_nachlaesse_tragen_ihre_fussnote(saetze_m):
    s = _satz(saetze_m, "iPhone 17 Pro 512 GB", "Allnet Flat M", 36)
    geraet = _art(s, AKTION_GERAETERABATT)
    assert geraet["betrag"] == 6.5 * 36 == 234
    assert geraet["eingerechnet"] is True
    assert geraet["bedingung"].startswith("Bei Abschluss der ANF M")
    tarif = _art(s, AKTION_TARIFRABATT)
    assert tarif["betrag_monatlich"] == 1.0 and "betrag" not in tarif
    assert tarif["gueltig_bis"] == "2026-09-29"
    anschluss = _art(s, AKTION_ANSCHLUSS_ERLASSEN)
    assert anschluss["betrag"] == 15.0 and anschluss["eingerechnet"] is True
    assert s["anschlusspreis"] == 0.0


def test_jede_aktion_des_adapters_ist_ein_gueltiges_feld(saetze_m):
    roh = [a for s in saetze_m for a in s["aktionen"]]
    assert len(aktionen_aus(roh)) == len(roh) > 0


def test_ein_trade_in_dessen_probe_nicht_aufgeht_wird_verworfen():
    """Zahlweisen mit einem `benefit`, der nicht die Differenz ist, sind
    keine Messung - dieselbe Regel wie fuer die Zahlweise selbst."""
    variante = {
        "prices": {
            "paymentVariants": [
                {
                    "type": "INSTALLMENT_PLAN",
                    "subtype": "UNSPECIFIED",
                    "contractDuration": 24,
                    "oneTime": {"discounted": 1},
                    "recurring": {"discounted": 10},
                    "total": 241,
                },
                {
                    "type": "INSTALLMENT_PLAN",
                    "subtype": "TRADE_IN",
                    "contractDuration": 24,
                    "oneTime": {"discounted": 1},
                    "recurring": {"discounted": 8},
                    "total": 193,
                    "benefit": {"amount": 48},
                },
            ]
        }
    }
    formen = congstar._buendelzahlweisen(variante, "https://x.de/t")
    assert [a["betrag"] for a in formen[24]["aktionen"]] == [48.0]
    variante["prices"]["paymentVariants"][1]["benefit"]["amount"] = 50
    formen = congstar._buendelzahlweisen(variante, "https://x.de/t")
    assert formen[24]["aktionen"] == []
    assert formen[24]["rate"] == 10


def test_produktseite_iphone17_liefert_den_vorlagefall():
    """Der Vorlagefall aus der Uebergabe: `congstar_produkt_iphone17`,
    TRADE_IN mit `benefit.amount` 162 bei 36 Raten (811 - 649)."""
    nutzlast = congstar._nutzlast(_text("congstar_produkt_iphone17.html.gz"))
    variante = congstar._varianten(nutzlast)[0]
    formen = congstar._buendelzahlweisen(variante, "https://www.congstar.de/x/")
    trade_in = [a for a in formen[36]["aktionen"] if a["art"] == AKTION_TRADE_IN]
    assert [a["betrag"] for a in trade_in] == [162.0]


def _aktion(**kw):
    werte = {
        "art": AKTION_TRADE_IN,
        "bedingung": "mit Altgerät",
        "quelle_url": "https://x.de/",
        "betrag": 100.0,
    }
    werte.update(kw)
    return Aktion(**werte)


@pytest.mark.parametrize(
    "kw", [{"art": "gutschein"}, {"bedingung": " "}, {"quelle_url": ""}, {"betrag": -1}]
)
def test_eine_aktion_ohne_pflichtangabe_wirft(kw):
    with pytest.raises(ValueError):
        _aktion(**kw)


def test_gilt_am_folgt_dem_genannten_ende():
    a = _aktion(gueltig_bis="2026-09-29")
    assert a.gilt_am("2026-09-29") and not a.gilt_am("2026-09-30")
    assert _aktion().gilt_am("2099-01-01"), "ohne Ende laeuft sie"


def test_aktionen_aus_verwirft_nur_die_kaputte():
    roh = [asdict(_aktion()), {"art": "gutschein", "bedingung": "x", "quelle_url": "y"}]
    assert [a.art for a in aktionen_aus(roh)] == [AKTION_TRADE_IN]


def _buendel(**kw):
    werte = dict(
        sku_id="apple-iphone-17-pro-256gb-schwarz",
        anbieter="congstar",
        tarif_name="Allnet Flat M",
        tarif_id="cs:m",
        tarif_id_guete="hoch",
        tarif_monatlich=24.0,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=41.25,
        laufzeit_monate=24,
        anschlusspreis=0.0,
        quelle_url=TARIFSEITE_M,
        abgerufen_am="2026-09-28",
        zustand="neu",
    )
    werte.update(kw)
    return Buendel(**werte)


def test_keine_aktion_veraendert_die_leitzahl():
    ohne = tco_24(_buendel())
    mit = tco_24(
        _buendel(
            aktionen=[
                _aktion(betrag=324.0),
                _aktion(art=AKTION_GERAETERABATT, betrag=234.0, eingerechnet=True),
            ]
        )
    )
    assert mit.gesamt == ohne.gesamt == 1.0 + 24 * 41.25 + 24 * 24.0


def test_der_speicher_fuehrt_die_aktionen_hin_und_zurueck(tmp_path):
    db = TcoDB(tmp_path / "geraete_tco.json")
    b = _buendel(aktionen=[_aktion(betrag=324.0, gueltig_bis="2026-12-31")])
    db.upsert_buendel([b], today="2026-09-28")
    db.save("2026-09-28")
    db2 = TcoDB(tmp_path / "geraete_tco.json")
    eintrag = db2.buendel()[0]
    assert eintrag["aktionen"][0]["betrag"] == 324.0
    [zurueck] = _aus_speicher([eintrag], Buendel, _BUENDEL_FELDER)
    assert zurueck.aktionen == b.aktionen
    db2.upsert_buendel([_buendel()], today="2026-09-29")
    assert db2.buendel()[0]["aktionen"] == []


def test_der_ueberhang_ist_die_groesste_nicht_eingerechnete_aktion():
    b = _buendel(
        aktionen=[
            _aktion(betrag=324.0),
            _aktion(art=AKTION_GERAETERABATT, betrag=999.0, eingerechnet=True),
            _aktion(
                art=AKTION_TARIFRABATT,
                betrag=None,
                betrag_monatlich=1.0,
                eingerechnet=True,
                gueltig_bis="2026-09-29",
            ),
        ]
    )
    liste, ueberhang = karten.aktionen_der_karte(b, "2026-09-28")
    assert ueberhang == {"betrag": 324.0, "kurz": "mit Altgerät"}
    assert [a["name"] for a in liste] == [
        "Trade-in",
        "Geräterabatt im Tarif",
        "Grundpreisnachlass",
    ]
    liste, _ = karten.aktionen_der_karte(b, "2026-09-30")
    assert "Grundpreisnachlass" not in [a["name"] for a in liste]


def test_nur_eingerechnete_aktionen_haben_keinen_ueberhang():
    b = _buendel(
        aktionen=[_aktion(art=AKTION_GERAETERABATT, betrag=234.0, eingerechnet=True)]
    )
    assert karten.aktionen_der_karte(b, "2026-09-28")[1] is None


def test_mit_aktionen_heisst_boni_nicht_mehr_nicht_gemessen():
    ohne = karten._karte(
        _buendel(), None, None, None, {}, zustand="neu", heute="2026-09-28"
    )
    mit = karten._karte(
        _buendel(aktionen=[_aktion()]),
        None,
        None,
        None,
        {},
        zustand="neu",
        heute="2026-09-28",
    )
    assert POSTEN_RABATTE in ohne["luecken"]
    assert POSTEN_RABATTE not in mit["luecken"]
    assert mit["gesamt"] == ohne["gesamt"]
    assert mit["aktion_ueberhang"]["betrag"] == 100.0
