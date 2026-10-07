"""Klick-Bündel im Gerätelauf (``analyze.klick_zusammenfuehrung``), ohne Browser.

Adaptersätze: die 48 echten o2-Rohsätze zum iPhone 17 Pro aus dem Sammler
(``o2_vertiefung_iphone17pro.json.gz``, 29.09.2026, wie in
``test_tco_buendel_ohne_tarifblatt``). Klick-Sätze: Lesungen derselben echten Antworten
(``tests/klickergebnisse.py``). Ein Klick-Satz ersetzt den Adaptersatz mit gleichem
Schlüssel und übernimmt dessen Bündel-ID; der ersetzte zählt als Gegenprobe. Ein
gestörter, alter oder fehlender Anbieter ersetzt nichts.
"""

from __future__ import annotations

import gzip
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from bestand_pfad import WURZEL, ZUSTAND, lese_wurzel
from klickergebnisse import (
    O2_SEITE,
    TELEKOM_SEITE,
    erfasst,
    ergebnisdatei,
    lauf,
    o2_lesung,
    telekom_lesung,
)

from telco_radar.analyze.klick_zusammenfuehrung import (
    STAND,
    UMGEBUNG,
    fuehre_zusammen,
    klickordner,
    zusammenfuehren,
)
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import sammle_anbieter
from telco_radar.collect.geraete.klickergebnis import lies_stand, schreibe
from telco_radar.collect.geraete.klicklauf import LAUF_GESTOERT
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog
from telco_radar.geraete_model import sku_id
from telco_radar.geraete_pipeline import run_geraete_stage
from telco_radar.report.geraete_tco_karten import geraet_aus_sku
from telco_radar.tarif_bezug import Tarifbestand

_FIX = Path(__file__).parent / "fixtures" / "geraete"
HEUTE = "2026-09-29"
M_PLUS = "O2 Mobile Unlimited M Plus"
M_PLUS_ADAPTER = "O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)"
_KATALOG_URL = (
    "https://www.o2online.de/e-shop/rest/catalog/o2shop/"
    "privatkunden/ratenzahlung/default/__not-specified__/"
    "__not-specified__/__not-specified__"
)
LEER = {"format": 1, "seiten": {}, "varianten": {}}


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def bestand():
    return Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")


_O2 = {
    "name": "o2",
    "typ": "netzbetreiber",
    "methode": "o2_katalog",
    "rang": 3,
    "basis_url": "https://www.o2online.de",
    "rate_limit_sekunden": 0,
    "kopfzeilen": {"Accept": "application/vnd.commerce.message+json"},
    "einstiege": [{"url": _KATALOG_URL, "label": "mit Tarif", "kind": "buendel"}],
}
_JETZT = datetime(2026, 9, 29, 3, tzinfo=UTC)


def _hole():
    """Der Mitschnitt vom 29.09.2026 als Abrufer, robots.txt wie damals gültig."""
    with gzip.open(_FIX / "o2_vertiefung_iphone17pro.json.gz", "rt") as fh:
        mitschnitt = json.load(fh)
    antworten = dict(mitschnitt["antworten"])
    antworten[_KATALOG_URL] = json.dumps(mitschnitt["katalog"])

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /postpaid/\n")
        return (200, antworten[url]) if url in antworten else (404, "")

    return hole


@pytest.fixture(scope="module")
def adapter(katalog):
    """Die 48 Rohsätze des o2-Sammlers zum iPhone 17 Pro, mit ``sku_id``."""
    hole = _hole()
    einstiege = [Einstieg(url=e["url"], kind=e["kind"]) for e in _O2["einstiege"]]
    felder = ("name", "typ", "methode", "basis_url", "rate_limit_sekunden")
    anbieter = Anbieter(
        **{f: _O2[f] for f in felder}, kopfzeilen=_O2["kopfzeilen"], einstiege=einstiege
    )
    bilanz = sammle_anbieter(
        anbieter,
        katalog,
        lade_farben(WURZEL),
        hole,
        HEUTE,
        RobotsWaechter(hole=hole),
        _JETZT,
    )
    assert len(bilanz.buendel) == 48
    return bilanz.buendel


def _geraet(katalog):
    return lambda sku: geraet_aus_sku(sku, katalog)


def _o2(*kombinationen, datum=HEUTE, **felder):
    seiten = [(O2_SEITE, lauf(O2_SEITE, list(kombinationen), **felder))]
    return ergebnisdatei("o2", "o2", seiten, datum)


def _klick(saetze):
    return [s for s in saetze if s.get("quelle_art") == "klick"]


def _stand():
    return json.loads(json.dumps(LEER))


def test_klick_ersetzt_den_adaptersatz_und_behaelt_die_buendel_id(
    adapter, katalog, bestand
):
    kombinationen = [
        erfasst(o2_lesung("256 GB", M_PLUS, 36)),
        erfasst(o2_lesung("512 GB", M_PLUS, 24)),
        erfasst(o2_lesung("256 GB", "O2 Mobile Special", 36)),
    ]
    vorher = {b.id for b in aus_rohsaetzen(adapter, bestand, HEUTE).buendel}

    zug = fuehre_zusammen(
        adapter, [_o2(*kombinationen)], katalog, HEUTE, _geraet(katalog), _stand()
    )
    bilanz = aus_rohsaetzen(zug.rohsaetze, bestand, HEUTE)

    klick = _klick(zug.rohsaetze)
    assert len(zug.rohsaetze) == 48 and len(klick) == 3
    assert {s["sku_id"] for s in klick} == {
        "apple-iphone-17-pro-256gb-silber",
        "apple-iphone-17-pro-512gb-silber",
    }
    assert M_PLUS_ADAPTER in {s["tarif_name"] for s in klick}
    assert zug.bilanz["ersetzt"] == 3 and zug.bilanz["ohne_gegenstueck"] == 0
    assert zug.bilanz["gegenprobe"]["gleich"] == 3
    assert zug.bilanz["gegenprobe"]["abweichend"] == 0
    assert bilanz.ohne_tarif == 0
    assert {b.id for b in bilanz.buendel} == vorher
    schluessel = {(s["sku_id"], s["tarif_name"], s["laufzeit_monate"]) for s in klick}
    gemessen = [
        b
        for b in bilanz.buendel
        if (b.sku_id, b.tarif_name, b.laufzeit_monate) in schluessel
    ]
    assert len(gemessen) == 3 and all(not b.herleitung for b in gemessen)
    special = next(b for b in gemessen if "Special" in b.tarif_name)
    assert [(p.von_monat, p.bis_monat, p.betrag) for p in special.tarif_phasen] == [
        (1, 24, 14.99),
        (25, 36, 29.99),
    ]


def test_abweichung_wird_je_feld_gezaehlt(katalog):
    """Telekom ``/v2/details`` nennt je Laufzeit drei Anzahlungsstufen. Der
    Adaptersatz hält die Stufe 458,15 €, der Klick las die Stufe 199 €: dieselbe
    Antwort, zwei Lesarten, und die Gegenprobe nennt beide Felder."""
    stufe = telekom_lesung("36", "458,15").werte
    assert (stufe.anzahlung, stufe.rate) == (458.15, 23.63)
    alt = {
        "sku_id": sku_id("apple-iphone-17-pro", 512, "tiefblau"),
        "anbieter": "Telekom",
        "zustand": "neu",
        "tarif_name": "MagentaMobil M",
        "laufzeit_monate": 36,
        "geraet_zuzahlung": stufe.anzahlung,
        "geraet_monatsrate": stufe.rate,
        "tarif_monatlich": stufe.tarifphasen[0].betrag,
        "anschlusspreis": stufe.anschluss,
    }
    klick = erfasst(telekom_lesung("36", "199"), laufzeit=36)
    datei = ergebnisdatei(
        "Telekom", "telekom", [(TELEKOM_SEITE, lauf(TELEKOM_SEITE, [klick]))], HEUTE
    )

    zug = fuehre_zusammen([alt], [datei], katalog, HEUTE, _geraet(katalog), _stand())

    probe = zug.bilanz["gegenprobe"]
    assert (probe["gleich"], probe["abweichend"]) == (0, 1)
    assert probe["felder"] == {"geraet_zuzahlung": 1, "geraet_monatsrate": 1}
    assert "geraet_monatsrate 30.8 statt 23.63" in probe["beispiele"][0]
    (satz,) = zug.rohsaetze
    assert (satz["geraet_monatsrate"], satz["sku_id"]) == (30.8, alt["sku_id"])


@pytest.mark.parametrize(
    ("datei", "warum"),
    [
        ({"status": LAUF_GESTOERT, "grund": "Abruf gestört (HTTP 403)"}, "gestoert"),
        ({"datum": "2026-09-28"}, "nicht von heute"),
    ],
    ids=["gestoert", "gestern"],
)
def test_gestoerter_oder_alter_anbieter_ersetzt_nichts(adapter, katalog, datei, warum):
    datum = datei.pop("datum", HEUTE)
    ergebnis = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)), datum=datum, **datei)
    stand = _stand()
    stand["varianten"]["o2"] = {
        "o2|apple-iphone-17-pro|512|o2-mobile-unlimited-m-plus|24": "2026-09-28"
    }

    zug = fuehre_zusammen(adapter, [ergebnis], katalog, HEUTE, _geraet(katalog), stand)

    assert zug.rohsaetze == adapter
    assert zug.bilanz["ersetzt"] == 0 and zug.bilanz["frueher_gelesen_ersetzt"] == 0
    assert warum in zug.bilanz["dateien"][0]["warum_nicht"]
    assert zug.stand["seiten"] == {}


@pytest.mark.parametrize(("gelesen", "ersetzt"), [("2026-09-28", 1), ("2026-09-26", 0)])
def test_frische_lesung_haelt_die_ersetzung_ueber_die_rotation(
    adapter, katalog, gelesen, ersetzt
):
    """Heute las der Lauf nur 256 GB/36; 512 GB/24 las er vor einem bzw. drei Tagen."""
    stand = _stand()
    schluessel = "o2|apple-iphone-17-pro|512|o2-mobile-unlimited-m-plus|24"
    stand["varianten"]["o2"] = {schluessel: gelesen}
    heute = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)))

    zug = fuehre_zusammen(adapter, [heute], katalog, HEUTE, _geraet(katalog), stand)

    assert zug.bilanz["frueher_gelesen_ersetzt"] == ersetzt
    assert len(zug.rohsaetze) == 48 - ersetzt
    assert (schluessel in zug.stand["varianten"]["o2"]) == bool(ersetzt)
    neu = "o2|apple-iphone-17-pro|256|o2-mobile-unlimited-m-plus-mit-100-mbit-s|36"
    assert zug.stand["varianten"]["o2"][neu] == HEUTE
    assert zug.stand["seiten"]["o2"] == {O2_SEITE.adresse: HEUTE}


def test_ohne_ordner_bleibt_alles_wie_bisher(adapter, katalog, tmp_path):
    zug = zusammenfuehren(adapter, None, tmp_path, katalog, HEUTE, _geraet(katalog))
    zug.speichere()

    assert zug.rohsaetze == adapter and zug.bilanz is None
    assert list(tmp_path.iterdir()) == []


def test_ordner_wird_gelesen_und_stand_erst_beim_speichern_geschrieben(
    adapter, katalog, tmp_path
):
    ordner = tmp_path / "klick"
    schreibe(
        ordner / "klick-o2" / "o2.json", _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)))
    )
    (ordner / "kaputt.json").write_text("{", encoding="utf-8")
    zustand = tmp_path / "state"
    zustand.mkdir()

    zug = zusammenfuehren(adapter, ordner, zustand, katalog, HEUTE, _geraet(katalog))

    assert len(_klick(zug.rohsaetze)) == 1
    assert zug.bilanz["unlesbar"] == ["kaputt.json: JSONDecodeError"]
    assert not (zustand / STAND).exists()
    zug.speichere()
    assert lies_stand(zustand / STAND)["seiten"]["o2"] == {O2_SEITE.adresse: HEUTE}


@pytest.mark.parametrize("mit_klick", [True, False], ids=["mit", "ohne"])
def test_geraetelauf_fuehrt_klick_zusammen(tmp_path, mit_klick):
    """``run_geraete_stage`` mit dem o2-Mitschnitt als einzigem Anbieter: mit Ordner
    ersetzt die Klick-Lesung einen der 48 Adaptersätze, ohne Ordner bleibt alles wie
    bisher und kein Lesestand entsteht."""
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    for name in ("geraete_katalog.yaml", "farben.yaml"):
        shutil.copy(WURZEL / "config" / name, root / "config" / name)
    quellen = yaml.safe_dump({"anbieter": [_O2]}, allow_unicode=True)
    (root / "config" / "geraete_quellen.yaml").write_text(quellen, encoding="utf-8")
    (root / "data" / "state").mkdir(parents=True)
    shutil.copy(ZUSTAND / "tarife.jsonl", root / "data" / "state" / "tarife.jsonl")
    ordner = tmp_path / "klick"
    schreibe(
        ordner / "klick-o2" / "o2.json", _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)))
    )

    bilanz = run_geraete_stage(
        root,
        {},
        HEUTE,
        jetzt=_JETZT,
        hole=_hole(),
        klick=ordner if mit_klick else None,
    )

    assert (bilanz["rohbuendel"], bilanz["buendel"]) == (48, 48)
    stand = root / "data" / "state" / STAND
    if not mit_klick:
        assert bilanz["klick"] is None and not stand.exists()
        return
    assert bilanz["klick"]["ersetzt"] == 1
    assert bilanz["klick"]["gegenprobe"]["gleich"] == 1
    assert lies_stand(stand)["seiten"]["o2"] == {O2_SEITE.adresse: HEUTE}


def test_klickordner_nur_aus_gesetzter_umgebung():
    assert klickordner({}) is None
    assert klickordner({UMGEBUNG: ""}) is None
    assert klickordner({UMGEBUNG: "klick"}) == Path("klick")
