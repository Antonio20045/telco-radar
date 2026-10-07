"""Eine Definition des Tarifpreises und die Rechenweise der Vodafone-Messung.

Prüferbefunde zu 19ab6bd6. B1/S3: Karte, Katalog und Export lasen `tarif_monatlich`
(31,95 € Listenpreis), die Kernzahl rechnete mit 23,95 € - die Zeile war mit ihrer
eigenen Rechnung nicht nachrechenbar. B2: dieselbe Antwort, neu gelesen, ergab im
Wochenblock, beim Vortag (Regel 11) und beim Preissprung der Abdeckung eine Bewegung,
die Vodafone nie gemacht hat. Die Bündel kommen aus gespeicherten echten Tarifantworten
(Pixel 11, 05.09. und 29.09.2026); `heute` steht fest.
"""

import json
from dataclasses import replace
from pathlib import Path

from bestand_pfad import lese_wurzel

from telco_radar import rechenweise
from telco_radar.analyze.buendel_abdeckung import pruefe
from telco_radar.analyze.geraete_pruefstatus import Kontext
from telco_radar.analyze.geraete_regeln import pruefe_bestand
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.collect.geraete.vodafone import loese_tarifnamen
from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_bewegung, geraete_tco_karten, geraete_view
from telco_radar.tarif_model import buendelphasen_aus
from telco_radar.tco_kosten import kosten_ueber, tarifpreis_im_monat
from telco_radar.tco_model import Buendel, sim_only_id, tco_24

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_PIXEL_0509 = "vodafone_tarif_hardware.json"
_PIXEL_2909 = "vodafone_tarif_hardware_geraet_2026-09-29.json"
_HW = "58060"
_SKU = "google-pixel-11-256gb-frost"
_HEUTE = "2026-10-07"
_VORTAG = "2026-10-06"
_FELDER = (
    "tarif_name",
    "tarif_monatlich",
    "tarif_listenpreis",
    "geraet_zuzahlung",
    "geraet_monatsrate",
    "laufzeit_monate",
    "anschlusspreis",
)
_KATALOG = []


def _katalog():
    if not _KATALOG:
        _KATALOG.append(lade_katalog(lese_wurzel()))
    return _KATALOG[0]


def _daten(datei: str) -> dict:
    return json.loads((_FIX / datei).read_text(encoding="utf-8"))


def _satz(datei: str, tarif: str, raten: int) -> dict:
    """Der Satz der Tarifantwort als Store-Eintrag: Felder, Phasen, Rechenweise."""
    roh = [
        {
            "quelle": "vodafone_buendel",
            "sku": _HW,
            "titel": "Pixel 11",
            "url": "https://www.vodafone.de/privat/handys/google-pixel-11.html",
            "tarif_name": "",
            "tarif_slug": "vorschau",
        }
    ]
    text = (_FIX / datei).read_text(encoding="utf-8")
    loese_tarifnamen(lambda url, kopfzeilen: (200, text), {}, roh)
    [s] = [r for r in roh if (r["tarif_name"], r["laufzeit_monate"]) == (tarif, raten)]
    return {
        "id": f"buendel--vodafone--{_SKU}--{tarif.lower().replace(' ', '-')}--{raten}m",
        "sku_id": _SKU,
        "anbieter": "Vodafone",
        **{f: s[f] for f in _FELDER},
        "tarif_phasen": s["tarif_phasen"],
        "quelle_url": s["url"],
        "abgerufen_am": _HEUTE,
        rechenweise.FELD: 2,
    }


def _buendel(satz: dict) -> Buendel:
    return Buendel(
        sku_id=satz["sku_id"],
        anbieter=satz["anbieter"],
        **{f: satz.get(f) for f in _FELDER},
        quelle_url=satz["quelle_url"],
        abgerufen_am=satz["abgerufen_am"],
        tarif_phasen=buendelphasen_aus(satz.get("tarif_phasen")),
    )


def _alte_lesart(satz: dict) -> dict:
    """Derselbe Satz, wie ihn die Historie bis 06.10.2026 führt: Listenpreis als
    `tarif_monatlich`, keine Phase, keine Rechenweise."""
    alt = {k: v for k, v in satz.items() if k not in ("tarif_phasen", "rechenweise")}
    return {**alt, "tarif_monatlich": satz["tarif_listenpreis"], "datum": _VORTAG}


def _karte(satz: dict) -> dict:
    ergebnis = geraete_tco_karten.modelle(
        [_buendel(satz)], [], [], {}, _katalog(), heute=_HEUTE
    )
    [karte] = [
        k
        for m in ergebnis["modelle"]
        for k in m["karten"]
        if k["anbieter"] == "Vodafone"
    ]
    return karte


def test_die_karte_nennt_als_monatlich_den_tarif_ihrer_rechnung():
    """Mobil XS, 24 Raten: „monatlich …“ und „24 × … Tarif“ sind derselbe Betrag."""
    satz = _satz(_PIXEL_0509, "Mobil XS", 24)
    karte = _karte(satz)
    [tarif] = [s for s in karte["rechnung"] if s["wort"] == "Tarif"]
    assert tarif["anzahl"] == 24
    erster = tarifpreis_im_monat(_buendel(satz), 1)
    assert karte["monatlich"] == tarif["betrag"] == erster == 23.95
    assert karte["gesamt"] == kosten_ueber(_buendel(satz)).gesamt


def test_gegenprobe_der_listenpreis_als_monatlich_widerspricht_der_rechnung():
    satz = _satz(_PIXEL_0509, "Mobil XS", 24)
    karte = _karte({**satz, "tarif_monatlich": satz["tarif_listenpreis"]})
    [tarif] = [s for s in karte["rechnung"] if s["wort"] == "Tarif"]
    assert (karte["monatlich"], tarif["betrag"]) == (31.95, 23.95)


def _katalog_monat(satz: dict) -> float:
    zeilen = geraete_view.katalog_modellzeilen(
        [], _katalog(), buendel=[satz], heute=_HEUTE
    )
    [monat] = [z["buendel_monat"] for z in zeilen if z.get("buendel_monat") is not None]
    return monat


def test_der_katalog_nennt_den_monatspreis_den_vodafone_nennt():
    """Die Gesamtrate mit Rabatt in Monat 1 (der Preis auf vodafone.de), nicht die
    durchgestrichene. Gegenprobe: mit dem Listenpreis wäre es die durchgestrichene."""
    daten = _daten(_PIXEL_0509)
    [anbieter] = [
        k["totalMonthlyRatePrice"]
        for e in daten["data"]
        for t in e["tariffs"]
        if t["tariffName"] == "Mobil XS"
        for a in t["atomics"]
        for k in a["prices"]["composition"]
        if k.get("financingDuration") == 24
    ]
    [mit] = [p["gross"] for p in anbieter["withDiscounts"] if p["recurrenceStart"] == 1]
    [ohne] = [p["gross"] for p in anbieter["withoutDiscounts"]]
    satz = _satz(_PIXEL_0509, "Mobil XS", 24)
    assert _katalog_monat(satz) == mit
    assert (
        _katalog_monat({**satz, "tarif_monatlich": satz["tarif_listenpreis"]}) == ohne
    )
    assert mit < ohne


def _messung(zeile: dict) -> dict:
    kosten = kosten_ueber(_buendel(zeile))
    return {
        "satz": zeile,
        "stand": zeile,
        "wert": kosten.gesamt,
        "monate": kosten.monate,
        "laufzeit": 24,
        "zaehlt": True,
    }


def _wochenblock(alt: dict, neu: dict) -> dict:
    fremd = {"id": "buendel--o2--x--24m", "anbieter": "o2"}
    konstant = {"satz": fremd, "wert": 1500.0, "monate": 24, "laufzeit": 24}
    paar = {
        "Vodafone": {"2026-09-30": _messung(alt), _HEUTE: _messung(neu)},
        "o2": {"2026-09-30": konstant, _HEUTE: konstant},
    }
    return geraete_bewegung.bewegungen(
        {("google-pixel-11-256", "xs", 24): paar},
        {"google-pixel-11-256": ["xs"]},
        {},
        {},
        lambda s: s["id"],
        stichtag=_HEUTE,
    )


def test_die_neue_rechenweise_ist_keine_preisbewegung():
    """Prüferfall: dieselbe Antwort vom 30.09. in der alten Lesart und heute in der
    neuen. Der Wochenblock meldet nichts und nennt den Bruch als Ausfall."""
    neu = _satz(_PIXEL_0509, "Mobil XS", 24)
    block = _wochenblock(_alte_lesart(neu), neu)
    assert block["zeilen"] == []
    assert block["geprueft"] == 0
    assert block["error"] == geraete_bewegung.AUSFALL_RECHENWEISE
    assert block["ohne_aussage"] == {geraete_bewegung.GRUND_RECHENWEISE: 1}


def test_gegenprobe_in_gleicher_rechenweise_ist_es_eine_bewegung():
    neu = _satz(_PIXEL_0509, "Mobil XS", 24)
    block = _wochenblock({**_alte_lesart(neu), rechenweise.FELD: 2}, neu)
    assert block["geprueft"] == 1
    [zeile] = block["zeilen"]
    assert zeile["eigen_delta"] == -192.0


def _regel_11(satz: dict, alt: dict) -> dict:
    k = Kontext(heute=_HEUTE, vortag={satz["id"]: alt})
    return pruefe_bestand([satz], k)[satz["id"]].als_feld()


def test_regel_11_vergleicht_nicht_ueber_den_bruch():
    """Mobil L, 24 Raten (29.09.): 61,95 € Listenpreis, 35,86 € in Monat 1-24. Über
    den Bruch wären das 26 % Sprung und Quarantäne für ein unverändertes Angebot."""
    satz = _satz(_PIXEL_2909, "Mobil L", 24)
    feld = _regel_11(satz, _alte_lesart(satz))
    assert 11 in feld["nicht_pruefbar"]
    assert 11 not in [g["regel"] for g in feld["gruende"]]


def test_gegenprobe_regel_11_sieht_einen_sprung_in_gleicher_rechenweise():
    """Gestern ohne Aktion gemessen, heute mit: die Phase von heute gilt nicht für
    gestern."""
    satz = _satz(_PIXEL_2909, "Mobil L", 24)
    feld = _regel_11(satz, {**_alte_lesart(satz), rechenweise.FELD: 2})
    assert 11 in [g["regel"] for g in feld["gruende"]]


def test_regel_3_misst_den_listenpreis_am_sim_only_preis():
    """Mobil XS 31,95 € ohne Rabatt über SIM-only 29,95 €; die 23,95 € des Online-
    Vorteils wären „unter SIM-only“, obwohl der Tarif derselbe ist."""
    satz = _satz(_PIXEL_0509, "Mobil XS", 24)
    k = Kontext(heute=_HEUTE, sim_only={sim_only_id("Vodafone", "Mobil XS"): 29.95})
    mit = pruefe_bestand([satz], k)[satz["id"]].als_feld()
    ohne = pruefe_bestand([{**satz, "tarif_listenpreis": None}], k)[satz["id"]]
    assert 3 not in [g["regel"] for g in mit["gruende"]]
    assert 3 in [g["regel"] for g in ohne.als_feld()["gruende"]]


def test_der_preissprung_der_abdeckung_vergleicht_nicht_ueber_den_bruch():
    neu = _satz(_PIXEL_2909, "Mobil L", 24)
    alt = _alte_lesart(neu)
    zeilen = [
        {**z, "gesamt": tco_24(_buendel(z)).gesamt, "datum": d}
        for z, d in ((alt, _VORTAG), (neu, _HEUTE))
    ]
    tco = {"updated": _HEUTE, "buendel": []}
    pflicht = {"anbieter": ["Vodafone"], "modelle": [], "luecken": {}}
    arten = [b.art for b in pruefe(tco, zeilen, pflicht).befunde]
    assert "preissprung" not in arten
    zeilen[0][rechenweise.FELD] = 2
    assert "preissprung" in [b.art for b in pruefe(tco, zeilen, pflicht).befunde]


def test_stand_und_historie_tragen_rechenweise_und_listenpreis(tmp_path):
    vodafone = replace(
        _buendel(_satz(_PIXEL_0509, "Mobil XS", 24)),
        tarif_id="vodafone:vodafone-mobil-xs",
    )
    o2 = Buendel(
        sku_id=_SKU,
        anbieter="o2",
        tarif_name="o2 Mobile M",
        tarif_id="o2:o2-mobile-m",
        tarif_monatlich=34.99,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=30.0,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url="https://www.o2online.de/x",
        abgerufen_am=_HEUTE,
    )
    db = TcoDB(tmp_path / "geraete_tco.json")
    db.upsert_buendel([vodafone, o2], _HEUTE)
    db.save(_HEUTE)
    stand = {b["anbieter"]: b for b in db.buendel()}
    assert stand["Vodafone"][rechenweise.FELD] == 2
    assert stand["Vodafone"]["tarif_listenpreis"] == 31.95
    assert stand["o2"][rechenweise.FELD] == rechenweise.ERSTE
    zeilen = [json.loads(z) for z in db.historie_path.read_text().splitlines()]
    assert sorted(rechenweise.der_zeile(z) for z in zeilen) == [1, 2]


def test_nur_die_juengste_rechenweise_zeichnet_die_reihe():
    alt = {"satz": {"datum": _VORTAG}}
    neu = {"satz": {"datum": _HEUTE, rechenweise.FELD: 2}}
    assert rechenweise.juengste({_VORTAG: alt, _HEUTE: neu}) == {_HEUTE: neu}
    gleich = {"satz": {"datum": _HEUTE, rechenweise.FELD: 1}}
    assert rechenweise.juengste({_VORTAG: alt, _HEUTE: gleich}) == {
        _VORTAG: alt,
        _HEUTE: gleich,
    }
    assert rechenweise.fuer_anbieter("Vodafone") == 2
    assert rechenweise.fuer_anbieter("o2") == rechenweise.ERSTE
