"""Nachbesserung PR 86 (Prüfer, 10.11.2026): was die Händlerzeilen NICHT zählen lässt.

M1  eine nicht lieferbare Variante bekommt nie einen Preis,
(2) ein Preiswechsel innerhalb der 24 Monate macht die Zeile unvergleichbar,
(3) Cashback, Senioren und Namen (young, aktion, kids, ...) ebenso,
(4) ein Bonus an der Rufnummernmitnahme wird nicht eingerechnet, steht aber als Hinweis,
(6) Händlerzeilen älter als ein Tag zählen nicht für Sieger oder Abstand,
S3  der Anbietertyp der Händlerzeilen steht im Export,
S5  nur der Tarifwelt-Leser vergibt die Herkunftsmarke.

Alle Regeln hängen an Merkmalen der Schnittstelle, nie an Anbieternamen.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel
from test_geraete_adapter_tarifwelt import LEITER, fixture_hole
from test_geraete_tarifwelt_haendler_mit_tarif import (
    lauf_beide_geraete,
    vodafone_tarife,
)

from telco_radar import tarifwelt_bestand
from telco_radar.analyze.geraete_pruefstatus import HERLEITUNG_DIREKT
from telco_radar.collect.geraete import tarifwelt, tarifwelt_lauf
from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_karten, geraete_view
from telco_radar.report import geraete_tco_view as tco_view
from telco_radar.tco_model import AKTION_WECHSELBONUS, kosten_ueber

HEUTE = "2026-11-08"
KATALOG = lade_katalog(lese_wurzel())
FIXTURES = Path(__file__).parent / "fixtures" / "geraete"
UEBERSICHT_S26 = (
    FIXTURES / "tarifwelt_mm_productdetail_galaxys26_standard_20261108.json"
)


def _hole_geaendert(uebersicht=None, detail=None):
    """Die Fixture-Schnittstelle; `uebersicht` und `detail` ändern die Antwort."""
    hole, aufrufe = fixture_hole()

    def umgestellt(url, **kw):
        antwort = hole(url, **kw)
        rest = url.split("/v1/productdetail/")[1]
        if "/tariff?" in rest:
            return antwort
        aendern = uebersicht if "?" not in rest else detail
        if aendern is None:
            return antwort
        daten = json.loads(antwort[1])
        aendern(daten)
        return type(antwort)(antwort[0], json.dumps(daten))

    return umgestellt, aufrufe


def _lauf(modell="apple-iphone-17", **aenderungen):
    hole, _ = _hole_geaendert(**aenderungen)
    return tarifwelt_lauf.lies_modell(modell, LEITER, hole, HEUTE, warte=lambda s: None)


def _uebersicht(aendern=None) -> str:
    daten = json.loads(UEBERSICHT_S26.read_text())
    if aendern:
        aendern(daten)
    return json.dumps(daten)


def _haendler():
    teile = lauf_beide_geraete()
    return [b for t in teile for b in t.buendel], {
        k: v for t in teile for k, v in t.tarife.items()
    }


def test_vorgewaehlte_variante_ohne_lieferbare_farbe_bekommt_keinen_preis():
    def nichts_lieferbar_bei_256(daten):
        for v in daten["hardware"]["variantFilter"]:
            if v["storage"] == 256:
                v["available"] = False

    ergebnis = tarifwelt_lauf.lies_uebersicht(_uebersicht(nichts_lieferbar_bei_256))
    assert 256 not in ergebnis["je_speicher"]
    assert 256 in ergebnis["nicht_lieferbar"]
    assert 512 in ergebnis["je_speicher"]


def test_gegenprobe_lieferbare_variante_bleibt():
    ergebnis = tarifwelt_lauf.lies_uebersicht(_uebersicht())
    assert set(ergebnis["je_speicher"]) == {256, 512}
    assert ergebnis["nicht_lieferbar"] == []


def test_vorgewaehlte_farbe_nicht_lieferbar_nimmt_eine_lieferbare_der_stufe():
    daten = json.loads(_uebersicht())
    vorgewaehlt = (
        f"{daten['hardware']['id']}_{daten['hardware']['variants'][0]['ebootisId']}"
    )

    def erste_farbe_weg(d):
        for v in d["hardware"]["variantFilter"]:
            if v["hwi"] == vorgewaehlt:
                v["available"] = False

    ergebnis = tarifwelt_lauf.lies_uebersicht(_uebersicht(erste_farbe_weg))
    assert ergebnis["je_speicher"][256]["hwi"] not in (vorgewaehlt, "")
    assert ergebnis["je_speicher"][256]["hwi"].startswith(daten["hardware"]["id"])


def test_ohne_beleg_der_lieferbarkeit_kein_preis():
    """Fehlt `variantFilter`, gibt es keinen Nachweis: die vorgewählte Variante
    gilt nicht als lieferbar (fail-closed)."""
    ergebnis = tarifwelt_lauf.lies_uebersicht(
        _uebersicht(lambda d: d["hardware"].pop("variantFilter"))
    )
    assert ergebnis["je_speicher"] == {}
    assert ergebnis["nicht_lieferbar"] == [256]


def test_lauf_nicht_lieferbares_modell_liefert_keinen_einzigen_preis():
    def nichts_lieferbar(daten):
        for v in daten["hardware"]["variantFilter"]:
            v["available"] = False

    lauf = _lauf("samsung-galaxy-s26", uebersicht=nichts_lieferbar)
    assert lauf.buendel == []
    assert ("samsung-galaxy-s26 256 GB", "nicht lieferbar") in lauf.luecken


def _intervalle(*teile) -> dict:
    return {
        "averagePrice": 0,
        "intervals": [
            {
                "ebootisId": "x",
                "monthInterval": 0,
                "startMonth": s,
                "endMonth": e,
                "price": p,
            }
            for s, e, p in teile
        ],
    }


@pytest.mark.parametrize(
    ("intervalle", "erwartet"),
    [
        (_intervalle((1, 0, 29.99)), False),
        (_intervalle((1, 24, 29.99), (25, 0, 34.99)), False),
        (_intervalle((1, 6, 9.99), (7, 0, 29.99)), True),
        (_intervalle((1, 23, 29.99), (24, 0, 39.99)), True),
        (_intervalle((1, 12, 29.99), (13, 0, 29.99)), False),
        ({"intervals": []}, None),
        (None, None),
    ],
)
def test_preiswechsel_nur_innerhalb_der_24_monate(intervalle, erwartet):
    from telco_radar.collect.geraete.tarifwelt_merkmale import preiswechsel

    assert preiswechsel(intervalle) is erwartet


def _detail_mit(aendern):
    def tu(daten):
        if "tariff" in daten:
            aendern(daten["tariff"])

    return tu


def _band_m_telekom(lauf):
    return [b for b in lauf.buendel if "Telekom" in b.anbieter]


def test_rabatt_nur_in_den_ersten_monaten_ist_nicht_vergleichbar():
    """Telekom-Allnet-Flat: Preis ab Monat 25 höher bleibt (unkritisch). Wechselt er
    schon in Monat 7, bekommt die Variante keinen Preis."""
    vorher = _lauf(detail=None)
    assert _band_m_telekom(vorher)

    def rabatt_sechs_monate(tariff):
        tariff["pricingIntervals"] = _intervalle((1, 6, 9.99), (7, 0, 29.99))

    lauf = _lauf(detail=_detail_mit(rabatt_sechs_monate))
    assert _band_m_telekom(lauf) == []
    assert any("Preis wechselt" in grund for _, grund in lauf.luecken), lauf.luecken


@pytest.mark.parametrize(
    ("feld", "wert", "stichwort"),
    [
        ("cashback", 100, "Cashback"),
        ("seniors", True, "Senioren"),
        ("name", "Allnet Flat Young", "young"),
        ("name", "Allnet Flat Aktion", "aktion"),
        ("name", "Allnet Flat Kids", "kids"),
        ("name", "Allnet Flat Senior", "senior"),
        ("name", "Doppelkarte Allnet", "doppelkarte"),
        ("name", "Allnet Flat 2x", "2x"),
    ],
)
def test_cashback_senioren_und_namen_sind_nicht_vergleichbar(feld, wert, stichwort):
    def setze(tariff):
        tariff[feld] = wert

    lauf = _lauf(detail=_detail_mit(setze))
    assert _band_m_telekom(lauf) == []
    assert any(stichwort.lower() in grund.lower() for _, grund in lauf.luecken), (
        lauf.luecken
    )


def test_gegenprobe_vergleichbarer_tarif_hat_keinen_grund():
    from telco_radar.collect.geraete.tarifwelt_merkmale import unvergleichbar_grund

    for satz in tarifwelt.lies_tarifliste(
        (FIXTURES / "tarifwelt_mm_tarifliste_iphone17_20261108.json").read_text()
    ):
        grund = unvergleichbar_grund(satz)
        assert (grund is not None) == (
            satz["doppelkarte"] or satz["tarif_name"] is None or bool(grund)
        )
    ok = {
        "cashback": 0,
        "seniors": False,
        "tarif_name": "Mobil M",
        "preiswechsel": False,
    }
    assert unvergleichbar_grund(ok) is None
    assert unvergleichbar_grund({**ok, "preiswechsel": None})


def test_tarifliste_laesst_unvergleichbare_nicht_zum_bandsieger_werden():
    liste = tarifwelt.lies_tarifliste(
        (FIXTURES / "tarifwelt_mm_tarifliste_galaxys26_20261108.json").read_text()
    )
    vorher = tarifwelt_lauf.rangliste_tarife(liste, LEITER)
    assert vorher
    gewinner = next(iter(vorher.values()))[0]
    schlechter = [
        {**s, "cashback": 50} if s["tarif_id"] == gewinner["tarif_id"] else s
        for s in liste
    ]
    nachher = tarifwelt_lauf.rangliste_tarife(schlechter, LEITER)
    ids = {s["tarif_id"] for rang in nachher.values() for s in rang}
    assert gewinner["tarif_id"] not in ids


def test_wechselbonus_steht_als_hinweis_und_ist_nicht_eingerechnet():
    lauf = _lauf()
    telekom = _band_m_telekom(lauf)
    assert telekom
    for b in telekom:
        assert [a.art for a in b.aktionen] == [AKTION_WECHSELBONUS]
        aktion = b.aktionen[0]
        assert aktion.eingerechnet is False and aktion.betrag == 50.0
        assert "Rufnummer" in aktion.bedingung or "Bonus" in aktion.bedingung
        ohne = replace(b, aktionen=[])
        assert kosten_ueber(b).gesamt == kosten_ueber(ohne).gesamt
    karte = geraete_tco_karten.aktionen_der_karte(telekom[0], HEUTE)
    assert karte[1] == {"betrag": 50.0, "kurz": "mit Rufnummernmitnahme"}


def test_hinweise_ohne_bonus_machen_keine_aktion():
    from telco_radar.collect.geraete.tarifwelt_merkmale import wechselbonus_aktionen

    assert wechselbonus_aktionen(["50 GB 5G", "VoLTE / Wifi"], "https://x") == []
    assert wechselbonus_aktionen(None, "https://x") == []
    (aktion,) = wechselbonus_aktionen(["25,50 Euro Wechselbonus"], "https://x")
    assert aktion.betrag == 25.5


def _modellzeilen(buendel, tarife, heute):
    ergebnis = tco_view.aufbereiten(
        [asdict(b) for b in buendel],
        [],
        [],
        KATALOG,
        tarife={**tarife, **vodafone_tarife()},
        tco_historie={"schwankend": []},
        heute=heute,
    )
    return [geraete_view._tco_spalte(m, heute) for m in ergebnis["modelle"]]


def test_haendlerzeile_aelter_als_ein_tag_stellt_weder_sieger_noch_abstand():
    buendel, tarife = _haendler()
    assert {b.herleitung for b in buendel} <= HERLEITUNG_DIREKT
    am_tag = _modellzeilen(buendel, tarife, "2026-11-08")
    nach_einem_tag = _modellzeilen(buendel, tarife, "2026-11-09")
    nach_zwei_tagen = _modellzeilen(buendel, tarife, "2026-11-10")
    assert all(z["tco_ab"] is not None for z in am_tag)
    assert all(z["tco_ab"] is not None for z in nach_einem_tag)
    for z in nach_zwei_tagen:
        assert z["tco_ab"] is None and z["tco_anbieter"] is None, z
        assert z["tco_leer"] == geraete_view.TCO_LEER_NUR_ALT


def test_gegenprobe_andere_zeilen_altern_erst_nach_drei_tagen():
    buendel, tarife = _haendler()
    gemessen = [replace(b, herleitung="") for b in buendel]
    zeilen = _modellzeilen(gemessen, tarife, "2026-11-10")
    assert all(z["tco_ab"] is not None for z in zeilen)
    assert geraete_tco_karten.ist_frisch(HEUTE, "2026-11-10") is True
    assert geraete_tco_karten.ist_frisch(HEUTE, "2026-11-11") is True
    assert geraete_tco_karten.ist_frisch(HEUTE, "2026-11-12") is False
    direkt = "tarifwelt_productdetail"
    assert geraete_tco_karten.ist_frisch(HEUTE, "2026-11-09", direkt) is True
    assert geraete_tco_karten.ist_frisch(HEUTE, "2026-11-10", direkt) is False


def test_exportzeile_nach_zwei_tagen_traegt_keinen_betrag():
    buendel, tarife = _haendler()
    ergebnis = tco_view.aufbereiten(
        [asdict(b) for b in buendel],
        [],
        [],
        KATALOG,
        tarife={**tarife, **vodafone_tarife()},
        tco_historie={"schwankend": []},
        heute="2026-11-10",
    )
    zeilen = ergebnis["export"]["buendel"]
    assert zeilen and all(z["tco24"] is None for z in zeilen)


class _Quelle:
    def __init__(self, name, typ, methode=""):
        self.name, self.typ, self.methode = name, typ, methode


def test_haendlerzeilen_tragen_den_typ_ihrer_quelle():
    quellen = [
        _Quelle("Vodafone", "netzbetreiber"),
        _Quelle("MediaMarkt/Saturn Tarifwelt", "handel", tarifwelt_bestand.METHODE),
    ]
    _, tarife = _haendler()
    typen = tarifwelt_bestand.typen_der_anbieter(quellen, tarife)
    zeilen = {t["anbieter"] for t in tarife.values()}
    assert zeilen and all(typen[z] == "handel" for z in zeilen)
    assert typen["Vodafone"] == "netzbetreiber"
    assert tarifwelt_bestand.typen_der_anbieter(quellen[:1], tarife) == {
        "Vodafone": "netzbetreiber"
    }


def test_export_nennt_den_anbietertyp_der_haendlerzeilen():
    buendel, tarife = _haendler()
    quellen = [
        _Quelle("MediaMarkt/Saturn Tarifwelt", "handel", tarifwelt_bestand.METHODE)
    ]
    ergebnis = tco_view.aufbereiten(
        [asdict(b) for b in buendel],
        [],
        [],
        KATALOG,
        tarife={**tarife, **vodafone_tarife()},
        anbieter_typen=tarifwelt_bestand.typen_der_anbieter(quellen, tarife),
        tco_historie={"schwankend": []},
        heute=HEUTE,
    )
    assert {z["anbieter_typ"] for z in ergebnis["export"]["buendel"]} == {"handel"}


def test_nur_der_tarifwelt_leser_vergibt_die_marke():
    """Die Notbremse lässt jede Zeile mit dieser Marke zählen, gleich bei welchem
    Anbieter. Vergeben darf sie nur der Tarifwelt-Leser: jedes seiner Bündel trägt
    sie, kein Bündel der übrigen Leser im Bestand (Schnappschuss mit allen anderen
    Anbietern) trägt sie."""
    marke = next(iter(HERLEITUNG_DIREKT))
    _, tarife = _haendler()
    haendler = [
        b for teil in (_lauf(), _lauf("samsung-galaxy-s26")) for b in teil.buendel
    ]
    assert haendler and {b.herleitung for b in haendler} == {marke}
    bestand = json.loads((ZUSTAND / "geraete_tco.json").read_text())["buendel"]
    anbieter = {b["anbieter"] for b in bestand}
    assert len(anbieter) >= 5, anbieter
    assert [b["id"] for b in bestand if b.get("herleitung") == marke] == []
    assert not any(a.startswith("Saturn/MediaMarkt") for a in anbieter)
    assert tarife
