"""Klick-Bündel im Gerätelauf (``analyze.klick_zusammenfuehrung``), ohne Browser.

Adaptersätze: die 48 echten o2-Rohsätze zum iPhone 17 Pro aus dem Sammler
(``o2_vertiefung_iphone17pro.json.gz``, 29.09.2026, wie in
``test_tco_buendel_ohne_tarifblatt``), der Telekom-Satz aus ``/v2/details`` und der
1&1-Satz der gespeicherten Produktseite (``einsundeins.lies_buendel``). Klick-Sätze:
Lesungen derselben echten Antworten (``tests/klickergebnisse.py``). Ein Klick-Satz
ersetzt den Adaptersatz mit gleichem Schlüssel nur, wenn er jedes Wertfeld nennt, und
übernimmt dessen Bündel-ID; eine Klick-Messung von heute hat Vorrang vor dem
Adapterbündel, eine ältere nur, wenn die heutige Messung ihr widerspricht
(``klick_preisgrenze``) - sonst behält die heutige Messung ihren Messtag. Ein
gestörter, veralteter oder fehlender Anbieter ersetzt nichts und ist benannt.
"""

from __future__ import annotations

import gzip
import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from bestand_pfad import WURZEL, ZUSTAND, lese_wurzel
from klickergebnisse import (
    EINSUNDEINS_SEITE,
    FIX,
    O2_SEITE,
    TELEKOM_SEITE,
    einsundeins_lesung,
    erfasst,
    ergebnisdatei,
    lauf,
    o2_lesung,
    telekom_lesung,
)

from telco_radar import tco_historie
from telco_radar.analyze.klick_alter import widerspruch_zeilen
from telco_radar.analyze.klick_preisgrenze import widersprueche
from telco_radar.analyze.klick_zusammenfuehrung import (
    UMGEBUNG,
    fuehre_zusammen,
    klickordner,
    zusammenfuehren,
)
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.collect.geraete import sammle_anbieter
from telco_radar.collect.geraete.einsundeins import lies_buendel
from telco_radar.collect.geraete.klickergebnis import ORDNER, STAND_DATEI, schreibe
from telco_radar.collect.geraete.klicklauf import LAUF_GESTOERT
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog
from telco_radar.geraete_model import sku_id
from telco_radar.geraete_pipeline import run_geraete_stage
from telco_radar.report.geraete_tco_karten import geraet_aus_sku
from telco_radar.tarif_bezug import Tarifbestand

HEUTE = "2026-09-29"
MORGEN = "2026-09-30"
M_PLUS = "O2 Mobile Unlimited M Plus"
M_PLUS_ADAPTER = "O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)"
TARIF_UNBEKANNT_IM_BESTAND = "O2 Mobile Probe Plus"
_KATALOG_URL = (
    "https://www.o2online.de/e-shop/rest/catalog/o2shop/"
    "privatkunden/ratenzahlung/default/__not-specified__/"
    "__not-specified__/__not-specified__"
)
_GESTOERT = {"status": LAUF_GESTOERT, "grund": "Abruf gestört (HTTP 403)"}


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
    with gzip.open(FIX / "o2_vertiefung_iphone17pro.json.gz", "rt") as fh:
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


def _telekom(*kombinationen, datum=HEUTE, **felder):
    seiten = [(TELEKOM_SEITE, lauf(TELEKOM_SEITE, list(kombinationen), **felder))]
    return ergebnisdatei("Telekom", "telekom", seiten, datum)


def _telekom_alt(**felder):
    """Der Adaptersatz zur Anzahlungsstufe 458,15 € derselben Antwort."""
    stufe = telekom_lesung("36", "458,15").werte
    assert (stufe.anzahlung, stufe.rate) == (458.15, 23.63)
    return {
        "sku_id": sku_id("apple-iphone-17-pro", 512, "tiefblau"),
        "anbieter": "Telekom",
        "zustand": "neu",
        "tarif_name": "MagentaMobil M",
        "laufzeit_monate": 36,
        "geraet_zuzahlung": stufe.anzahlung,
        "geraet_monatsrate": stufe.rate,
        "tarif_monatlich": stufe.tarifphasen[0].betrag,
        "anschlusspreis": stufe.anschluss,
        **felder,
    }


def _klick(saetze):
    return [s for s in saetze if s.get("quelle_art") == "klick"]


def _tag(pfad, adapter, dateien, heute, katalog, bestand):
    """Ein Gerätelauf im Kleinen: zusammenführen, Bündel bilden, Bestand speichern."""
    tco = TcoDB(pfad)
    zug = fuehre_zusammen(adapter, dateien, katalog, heute, _geraet(katalog))
    bilanz = zug.buendel(bestand, heute, tco.nach_id)
    tco.upsert_buendel(bilanz.buendel, heute)
    tco.save(heute)
    return zug, bilanz


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
        adapter, [_o2(*kombinationen)], katalog, HEUTE, _geraet(katalog)
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
    assert zug.bilanz["unvollstaendig"] == {"nicht_ersetzt": 0, "felder": {}}
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
    ]


def test_abweichung_wird_je_feld_gezaehlt(katalog):
    """Telekom ``/v2/details`` nennt je Laufzeit drei Anzahlungsstufen. Der
    Adaptersatz hält die Stufe 458,15 €, der Klick las die Stufe 199 €: dieselbe
    Antwort, zwei Lesarten, und die Gegenprobe nennt beide Felder."""
    alt = _telekom_alt()
    klick = erfasst(telekom_lesung("36", "199"), laufzeit=36)

    zug = fuehre_zusammen([alt], [_telekom(klick)], katalog, HEUTE, _geraet(katalog))

    probe = zug.bilanz["gegenprobe"]
    assert (probe["gleich"], probe["abweichend"]) == (0, 1)
    assert probe["felder"] == {"geraet_zuzahlung": 1, "geraet_monatsrate": 1}
    assert "geraet_monatsrate 30.8 statt 23.63" in probe["beispiele"][0]
    (satz,) = zug.rohsaetze
    assert (satz["geraet_monatsrate"], satz["sku_id"]) == (30.8, alt["sku_id"])


def _einsundeins_alt() -> dict:
    """Der Adaptersatz der gespeicherten 1&1-Produktseite: 44,99 € und 360,00 €."""
    html = gzip.decompress(
        (FIX / "einsundeins_produktseite_iphone_17_pro.html.gz").read_bytes()
    ).decode("utf-8")
    (roh,) = [
        r
        for r in lies_buendel(html, EINSUNDEINS_SEITE.adresse)
        if r["speicher_gb"] == 256
    ]
    assert (roh["buendel_monatlich"], roh["geraet_zuzahlung"]) == (44.99, 360.0)
    farbe = sku_id("apple-iphone-17-pro", 256, roh["farbe"])
    return {**roh, "anbieter": "1&1", "zustand": "neu", "sku_id": farbe}


def _einsundeins(einmalzahlung: float | None) -> dict:
    lesung = einsundeins_lesung()
    lesung = replace(
        lesung, buendel=replace(lesung.buendel, einmalzahlung=einmalzahlung)
    )
    kombination = erfasst(lesung, "256", "tariff-anf-s-mvl", 36)
    seite = (EINSUNDEINS_SEITE, lauf(EINSUNDEINS_SEITE, [kombination]))
    return ergebnisdatei("1&1", "1und1", [seite], HEUTE, vertragsform="ein_vertrag")


@pytest.mark.parametrize(
    ("fall", "feld"),
    [("1&1", "geraet_zuzahlung"), ("Telekom", "tarif_bindung_monate")],
)
def test_unvollstaendiger_klicksatz_ersetzt_nicht(katalog, bestand, fall, feld):
    """1&1: die Karte liest nur den Bündelbetrag, der Adapter auch 360,00 €
    Einmalzahlung. Telekom: der Klick liest keine Tarifbindung. Der Adaptersatz bleibt
    ganz, die Bilanz nennt das Feld; nie ein Bündel ohne die 360 €."""
    if fall == "1&1":
        alt, datei = _einsundeins_alt(), _einsundeins(None)
    else:
        klick = erfasst(telekom_lesung("36", "199"), laufzeit=36)
        alt, datei = _telekom_alt(tarif_bindung_monate=24), _telekom(klick)

    zug = fuehre_zusammen([alt], [datei], katalog, HEUTE, _geraet(katalog))

    assert zug.rohsaetze == [alt]
    assert zug.bilanz["ersetzt"] == 0 and zug.bilanz["klick_rohsaetze"] == 0
    assert zug.bilanz["unvollstaendig"] == {"nicht_ersetzt": 1, "felder": {feld: 1}}
    assert zug.bilanz["gegenprobe"]["gleich"] == 0
    if fall == "1&1":
        (b,) = aus_rohsaetzen(zug.rohsaetze, bestand, HEUTE).buendel
        assert (b.buendel_monatlich, b.geraet_zuzahlung) == (44.99, 360.0)


def test_klicksatz_mit_einmalzahlung_ersetzt(katalog):
    """Gegenprobe: nennt die Lesung die Einmalzahlung, ersetzt der Klick-Satz."""
    alt = _einsundeins_alt()

    zug = fuehre_zusammen(
        [alt], [_einsundeins(alt["geraet_zuzahlung"])], katalog, HEUTE, _geraet(katalog)
    )

    (satz,) = zug.rohsaetze
    assert satz["quelle_art"] == "klick" and satz["sku_id"] == alt["sku_id"]
    assert (satz["buendel_monatlich"], satz["geraet_zuzahlung"]) == (44.99, 360.0)
    assert zug.bilanz["ersetzt"] == 1 and zug.bilanz["gegenprobe"]["gleich"] == 1


@pytest.mark.parametrize(
    ("zweite", "anzahl", "mehrdeutig"),
    [
        ("458,15", 0, ["Telekom|apple-iphone-17-pro|512|magentamobil-m|36"]),
        ("199", 1, []),
    ],
    ids=["verschieden", "gleich"],
)
def test_gleicher_schluessel_doppelt(katalog, zweite, anzahl, mehrdeutig):
    """Zwei Lesungen derselben Variante (512 GB, MagentaMobil M, 36 Raten): mit
    verschiedener Anzahlungsstufe gilt keine, mit gleichen Werten eine."""
    a = erfasst(telekom_lesung("36", "199"), laufzeit=36)
    b = erfasst(telekom_lesung("36", zweite), laufzeit=36)

    zug = fuehre_zusammen([], [_telekom(a, b)], katalog, HEUTE, _geraet(katalog))

    assert len(_klick(zug.rohsaetze)) == anzahl
    assert zug.bilanz["mehrdeutig"] == mehrdeutig


@pytest.mark.parametrize(
    ("datei", "warum"),
    [
        (_GESTOERT, "gestoert"),
        ({"datum": "2026-09-28"}, "nicht von heute"),
        ({"datum": "2026-09-26"}, "älter als 3 Tage"),
        ({"datum": "2026-09-30"}, "nach heute"),
        ({"datum": "gestern"}, "Datum der Datei unlesbar"),
    ],
    ids=["gestoert", "gestern", "veraltet", "zukunft", "kein-datum"],
)
def test_gestoerter_oder_alter_anbieter_ersetzt_nichts(adapter, katalog, datei, warum):
    felder = dict(datei)
    datum = felder.pop("datum", HEUTE)
    ergebnis = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)), datum=datum, **felder)

    zug = fuehre_zusammen(adapter, [ergebnis], katalog, HEUTE, _geraet(katalog))

    assert zug.rohsaetze == adapter and zug.bilanz["ersetzt"] == 0
    assert warum in zug.bilanz["dateien"][0]["warum_nicht"]


@pytest.mark.parametrize(
    ("tag1", "buendel_geworden"), [([], 0), (None, 1)], ids=["ohne", "mit"]
)
def test_gestrige_lesung_verwirft_die_heutige_adaptermessung_nicht(
    adapter, katalog, bestand, tmp_path, tag1, buendel_geworden, monkeypatch
):
    """Tag 1 liest der Klick 256 GB/M Plus/36. Ohne Adaptersatz und mit einem Tarif,
    den der Bestand nicht kennt, wird er kein Bündel (``ohne_tarif``; einen bekannten
    löst ``klick_tarifslug`` seit Pitch 3 selbst auf). Tag 2 liefert der Adapter
    wieder, der Klick liest nur 512 GB/24: der Adaptersatz zu 256 GB/36 kommt in den
    Bestand - auch dann, wenn die Lesung von Tag 1 ein Bündel wurde, denn sie ist
    nicht von heute und die heutige Messung widerspricht ihr nicht (Befund
    13.11.2026). Vorrang hat nur eine Messung von HEUTE
    (``test_klickmessung_von_heute_hat_vorrang``) oder ein Widerspruch
    (``test_gestoerter_tag_laesst_die_frische_klickmessung_stehen``). Der Befund
    betraf nur congstar; die Regel wird hier mit den echten o2-Sätzen nachgestellt,
    darum steht die Anbieter-Bedingung (``klick_messtag.ANBIETER_PREISGRENZE``) für
    diesen Test auf ``o2`` (vgl. ``test_o2_bleibt_bei_der_alten_regel``, das denselben
    Anbieter ohne diese Umstellung prüft)."""
    monkeypatch.setattr("telco_radar.analyze.klick_messtag.ANBIETER_PREISGRENZE", "o2")
    pfad = tmp_path / "geraete_tco.json"
    erster = adapter if tag1 is None else tag1
    lesung = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)))
    if tag1 is not None:
        (kombination,) = lesung["seiten"][0]["kombinationen"]
        kombination["variante"]["tarif"] = TARIF_UNBEKANNT_IM_BESTAND
    tag1_bestand = bestand
    if tag1 is not None:
        tag1_bestand = Tarifbestand(
            [{**t, "buendel_slug": ""} for t in bestand.saetze("o2")]
        )
    _, b1 = _tag(pfad, erster, [lesung], HEUTE, katalog, tag1_bestand)
    zweite = _o2(erfasst(o2_lesung("512 GB", M_PLUS, 24)), datum=MORGEN)

    zug, _ = _tag(pfad, adapter, [zweite], MORGEN, katalog, bestand)

    assert b1.ohne_tarif == 1 - buendel_geworden
    assert (zug.bilanz["klick_vorrang"], zug.bilanz["klick_widerspruch"]) == (0, 0)
    (eintrag,) = [
        e
        for e in TcoDB(pfad).buendel()
        if e["sku_id"] == "apple-iphone-17-pro-256gb-silber"
        and e["tarif_name"] == M_PLUS_ADAPTER
        and e["laufzeit_monate"] == 36
    ]
    assert (eintrag.get("quelle_art"), eintrag["abgerufen_am"]) == (None, MORGEN)


def test_klickmessung_von_heute_hat_vorrang(adapter, katalog, bestand, tmp_path):
    """Gegenprobe zum Messtag: der Klick liest HEUTE 256 GB/M Plus/36 und steht mit
    seinem Datum im Bestand. Ein zweiter Durchgang desselben Tages ohne Klick-Datei
    überschreibt ihn nicht - eine Messung von heute ist die Hauptquelle des Tages,
    unabhängig davon, ob der Adapter ihr widerspricht."""
    pfad = tmp_path / "geraete_tco.json"
    lesung = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)))
    _tag(pfad, adapter, [lesung], HEUTE, katalog, bestand)

    zug, _ = _tag(pfad, adapter, [], HEUTE, katalog, bestand)

    assert (zug.bilanz["klick_vorrang"], zug.bilanz["klick_widerspruch"]) == (1, 0)
    (eintrag,) = [
        e
        for e in TcoDB(pfad).buendel()
        if e["sku_id"] == "apple-iphone-17-pro-256gb-silber"
        and e["tarif_name"] == M_PLUS_ADAPTER
        and e["laufzeit_monate"] == 36
    ]
    assert (eintrag.get("quelle_art"), eintrag["abgerufen_am"]) == ("klick", HEUTE)


_ANSCHLUSS_ERLASSEN = {
    "art": "anschluss_erlassen",
    "bedingung": "Anschlusspreis geschenkt",
    "eingerechnet": True,
    "quelle_url": "https://www.o2online.de/",
}


@pytest.mark.parametrize(
    ("rate", "widerspruch"), [(None, 0), (22.0, 1)], ids=["gleich", "widerspruch"]
)
def test_zurueckgehaltener_klicksatz_kostet_keinen_messtag(
    adapter, katalog, bestand, tmp_path, rate, widerspruch, monkeypatch
):
    """Die congstar-Lage vom 13.11.2026, nachgestellt mit den o2-Sätzen: Tag 1 misst
    der Klick, Tag 2 nennt der Adaptersatz eine EINGERECHNETE Aktion, die der Klick
    nicht liest - sein Satz wird zurückgehalten (``unvollstaendig``), und es entsteht
    kein Klick-Bündel von heute. Die heutige Adaptermessung behält trotzdem ihren
    Messtag, weil die heutige Klick-Lesung ihr nicht widerspricht. Gegenprobe:
    widerspricht sie ihr (Rate 22,00 statt 36,50 €), bleibt der ältere Klick-Wert mit
    seinem Datum stehen - lieber kein Preis als ein falscher. Der Befund betraf nur
    congstar; darum steht die Anbieter-Bedingung
    (``klick_messtag.ANBIETER_PREISGRENZE``) hier auf ``o2``, dem Anbieter der echten
    Sätze dieses Tests (vgl. ``test_o2_bleibt_bei_der_alten_regel``)."""
    monkeypatch.setattr("telco_radar.analyze.klick_messtag.ANBIETER_PREISGRENZE", "o2")
    pfad = tmp_path / "geraete_tco.json"

    def passt(s):
        return (
            s["sku_id"] == "apple-iphone-17-pro-256gb-silber"
            and s["laufzeit_monate"] == 36
            and M_PLUS in s["tarif_name"]
        )

    lesung = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)))
    _tag(pfad, adapter, [lesung], HEUTE, katalog, bestand)
    vorher = _eintrag(pfad)
    anders = {"aktionen": [_ANSCHLUSS_ERLASSEN]}
    if rate is not None:
        anders["geraet_monatsrate"] = rate
    mit_aktion = [{**s, **anders} if passt(s) else s for s in adapter]
    morgen = [_o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)), datum=MORGEN)]

    zug, _ = _tag(pfad, mit_aktion, morgen, MORGEN, katalog, bestand)

    assert vorher == ("klick", HEUTE, 36.5)
    assert zug.bilanz["klick_widerspruch"] == widerspruch
    erwartet = ("klick", HEUTE, 36.5) if widerspruch else (None, MORGEN, 36.5)
    assert _eintrag(pfad) == erwartet


def _eintrag(pfad):
    (eintrag,) = [
        e
        for e in TcoDB(pfad).buendel()
        if e["sku_id"] == "apple-iphone-17-pro-256gb-silber"
        and e["tarif_name"] == M_PLUS_ADAPTER
        and e["laufzeit_monate"] == 36
    ]
    return (
        eintrag.get("quelle_art"),
        eintrag["abgerufen_am"],
        eintrag["geraet_monatsrate"],
    )


def test_o2_bleibt_bei_der_alten_regel(adapter, katalog, bestand, tmp_path):
    """Der Befund 13.11.2026 (``klick_messtag.ANBIETER_PREISGRENZE``) betraf nur
    congstar: bei o2 verdrängt eine gestrige, frische Klick-Messung die heutige
    Adaptermessung weiterhin UNBEDINGT, wie vor diesem Befund - auch dann, wenn
    beide Messungen dasselbe sagen und also kein Widerspruch (``klick_preisgrenze``)
    vorliegt. Gälte die Regel anbieterneutral, bliebe die heutige Adaptermessung
    hier stehen, denn sie widerspricht der gestrigen nicht; ``test_o2_vorher`` ist
    mit denselben Sätzen genau dieser PASS-Fall für congstar."""
    pfad = tmp_path / "geraete_tco.json"
    lesung = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)))
    _tag(pfad, adapter, [lesung], HEUTE, katalog, bestand)
    vorher = _eintrag(pfad)

    zug, _ = _tag(pfad, adapter, [], MORGEN, katalog, bestand)

    assert vorher == ("klick", HEUTE, 36.5)
    assert (zug.bilanz["klick_vorrang"], zug.bilanz["klick_widerspruch"]) == (1, 0)
    assert _eintrag(pfad) == ("klick", HEUTE, 36.5)


def test_telekom_bleibt_bei_der_alten_regel(katalog, bestand, tmp_path):
    """Dieselbe Gegenprobe wie ``test_o2_bleibt_bei_der_alten_regel``, mit Telekom:
    Adaptersatz und Klick-Lesung nennen hier sogar genau denselben Preis (kein
    Widerspruch möglich), und trotzdem verdrängt die gestrige Klick-Messung die
    heutige Adaptermessung unbedingt - die Preisgrenze aus #103 gilt nicht für
    Telekom."""
    pfad = tmp_path / "geraete_tco.json"
    stufe = telekom_lesung("36", "199").werte
    alt = _telekom_alt(
        geraet_zuzahlung=stufe.anzahlung,
        geraet_monatsrate=stufe.rate,
        tarif_monatlich=stufe.tarifphasen[0].betrag,
        anschlusspreis=stufe.anschluss,
    )
    klick = erfasst(telekom_lesung("36", "199"), laufzeit=36)
    _tag(pfad, [alt], [_telekom(klick)], HEUTE, katalog, bestand)
    (vorher,) = TcoDB(pfad).buendel()

    zug, _ = _tag(pfad, [alt], [], MORGEN, katalog, bestand)
    (nachher,) = TcoDB(pfad).buendel()

    assert (vorher["quelle_art"], vorher["abgerufen_am"]) == ("klick", HEUTE)
    assert vorher["geraet_monatsrate"] == stufe.rate == alt["geraet_monatsrate"]
    assert (zug.bilanz["klick_vorrang"], zug.bilanz["klick_widerspruch"]) == (1, 0)
    assert (nachher["quelle_art"], nachher["abgerufen_am"]) == ("klick", HEUTE)


def test_gestoerter_tag_laesst_die_frische_klickmessung_stehen(
    katalog, bestand, tmp_path
):
    """Tag 1 ersetzt der Klick (Rate 30,80 bei 199 €) den Adaptersatz (23,63 bei
    458,15 €). Tag 2 ist der Telekom-Klick gestört, Tag 3 fehlt seine Datei: der
    Bestand behält die Messung von Tag 1 mit Datum, ohne Historienzeile. Gegenprobe
    Tag 4: die Messung ist drei Tage alt, der Adapter schreibt wieder."""
    pfad = tmp_path / "geraete_tco.json"
    klick = erfasst(telekom_lesung("36", "199"), laufzeit=36)
    tage = [
        ("2026-09-29", [_telekom(klick, datum="2026-09-29")]),
        ("2026-09-30", [_telekom(klick, datum="2026-09-30", **_GESTOERT)]),
        ("2026-10-01", []),
        ("2026-10-02", []),
    ]

    stand = []
    for heute, dateien in tage:
        zug, _ = _tag(pfad, [_telekom_alt()], dateien, heute, katalog, bestand)
        (eintrag,) = TcoDB(pfad).buendel()
        rate, datum = eintrag["geraet_monatsrate"], eintrag["abgerufen_am"]
        stand.append((rate, datum, zug.bilanz["klick_vorrang"]))

    assert stand == [
        (30.8, "2026-09-29", 0),
        (30.8, "2026-09-29", 1),
        (30.8, "2026-09-29", 1),
        (23.63, "2026-10-02", 0),
    ]
    historie = tco_historie.zeilen(tmp_path / "geraete_tco_historie.jsonl")
    zeilen = [json.loads(z) for z in historie]
    assert [(z["datum"], z["geraet_monatsrate"]) for z in zeilen] == [
        ("2026-09-29", 30.8),
        ("2026-10-02", 23.63),
    ]


def test_fehlender_anbieter_ist_benannt(adapter, katalog, tmp_path):
    """Nur die o2-Datei liegt im Ordner (die anderen Matrix-Jobs ohne Artefakt): die
    Bilanz nennt jeden geplanten Anbieter ohne Datei und reicht ``ueberfaellig`` der
    Datei durch. Gegenprobe: ohne Tagesplan ist nichts geplant, nichts fehlt."""
    ordner = tmp_path / "klick"
    o2 = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)))
    o2["ueberfaellig"] = [O2_SEITE.adresse]
    schreibe(ordner / "klick-o2" / "o2.json", o2)
    root = lese_wurzel()
    geplant = [z.name for z in lade_ziele(root, TAGESDATEI, hoechste=None)]

    zug = zusammenfuehren(adapter, ordner, root, katalog, HEUTE, _geraet(katalog))
    ohne = zusammenfuehren(adapter, ordner, tmp_path, katalog, HEUTE, _geraet(katalog))

    assert "Telekom" in geplant and zug.bilanz["geplant"] == geplant
    assert zug.bilanz["fehlt"] == [name for name in geplant if name != "o2"]
    assert zug.bilanz["dateien"][0]["ueberfaellig"] == [O2_SEITE.adresse]
    assert (ohne.bilanz["geplant"], ohne.bilanz["fehlt"]) == (None, [])


def test_ohne_ordner_bleibt_alles_wie_bisher(adapter, katalog, tmp_path, monkeypatch):
    monkeypatch.delenv(UMGEBUNG, raising=False)
    zug = zusammenfuehren(adapter, None, tmp_path, katalog, HEUTE, _geraet(katalog))

    assert zug.rohsaetze == adapter and zug.bilanz is None
    assert list(tmp_path.iterdir()) == []


def test_standardordner_wird_gelesen_und_nicht_beschrieben(
    adapter, katalog, tmp_path, monkeypatch
):
    monkeypatch.delenv(UMGEBUNG, raising=False)
    ordner = tmp_path / ORDNER
    schreibe(ordner / "o2.json", _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36))))
    schreibe(ordner / STAND_DATEI, {"format": 1, "seiten": {"o2": {}}})
    (ordner / "kaputt.json").write_text("{", encoding="utf-8")
    vorher = {d.name: d.read_bytes() for d in ordner.iterdir()}

    zug = zusammenfuehren(adapter, None, tmp_path, katalog, HEUTE, _geraet(katalog))

    assert len(_klick(zug.rohsaetze)) == 1 and zug.bilanz["ersetzt"] == 1
    assert zug.bilanz["unlesbar"] == ["kaputt.json: JSONDecodeError"]
    assert {d.name: d.read_bytes() for d in ordner.iterdir()} == vorher


@pytest.mark.parametrize("weg", ["genannt", "umgebung"])
def test_genannter_ordner_geht_vor(adapter, katalog, tmp_path, monkeypatch, weg):
    monkeypatch.delenv(UMGEBUNG, raising=False)
    veraltet = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)), datum="2026-09-20")
    schreibe(tmp_path / ORDNER / "o2.json", veraltet)
    artefakte = tmp_path / "artefakte"
    schreibe(
        artefakte / "klick-o2" / "o2.json",
        _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36))),
    )
    standard = zusammenfuehren(
        adapter, None, tmp_path, katalog, HEUTE, _geraet(katalog)
    )
    if weg == "umgebung":
        monkeypatch.setenv(UMGEBUNG, str(artefakte))

    genannt = zusammenfuehren(
        adapter,
        artefakte if weg == "genannt" else None,
        tmp_path,
        katalog,
        HEUTE,
        _geraet(katalog),
    )

    assert genannt.bilanz["ersetzt"] == 1
    assert standard.bilanz["ersetzt"] == 0


def _repo(tmp_path: Path) -> Path:
    """Ein Repo mit dem o2-Mitschnitt als einzigem Anbieter und echtem Tarifbestand."""
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    for name in ("geraete_katalog.yaml", "farben.yaml"):
        shutil.copy(WURZEL / "config" / name, root / "config" / name)
    quellen = yaml.safe_dump({"anbieter": [_O2]}, allow_unicode=True)
    (root / "config" / "geraete_quellen.yaml").write_text(quellen, encoding="utf-8")
    (root / "data" / "state").mkdir(parents=True)
    shutil.copy(ZUSTAND / "tarife.jsonl", root / "data" / "state" / "tarife.jsonl")
    return root


@pytest.mark.parametrize(
    ("datum", "ersetzt"),
    [(HEUTE, 1), ("2026-09-26", 0), (None, None)],
    ids=["heute", "veraltet", "ohne"],
)
def test_geraetelauf_liest_den_klick_ordner_im_repo(
    tmp_path, monkeypatch, datum, ersetzt
):
    """``run_geraete_stage`` ohne ``klick``: liegt ``data/state/klick/o2.json`` im Repo,
    ersetzt die Lesung von heute einen der 48 Adaptersätze, eine veraltete keinen; der
    Gerätelauf schreibt nichts in den Ordner. Im Bestand trägt nur das Klick-Bündel
    ``quelle_art`` und ``beleg_status``; die Adapterbündel bleiben ohne die Felder."""
    monkeypatch.delenv(UMGEBUNG, raising=False)
    root = _repo(tmp_path)
    datei = root / ORDNER / "o2.json"
    if datum is not None:
        schreibe(datei, _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)), datum=datum))

    bilanz = run_geraete_stage(root, {}, HEUTE, jetzt=_JETZT, hole=_hole())

    assert (bilanz["rohbuendel"], bilanz["buendel"]) == (48, 48)
    store = json.loads(
        (root / "data" / "state" / "geraete_tco.json").read_text("utf-8")
    )
    kennzeichen = [
        (b["sku_id"], b.get("quelle_art"), b.get("beleg_status"))
        for b in store["buendel"]
        if "quelle_art" in b or "beleg_status" in b or "beleg_id" in b
    ]
    if datum is None:
        assert bilanz["klick"] is None and not (root / ORDNER).exists()
        assert kennzeichen == []
        return
    assert bilanz["klick"]["ersetzt"] == ersetzt
    assert bilanz["klick"]["gegenprobe"]["gleich"] == ersetzt
    assert [d.name for d in (root / ORDNER).iterdir()] == ["o2.json"]
    erwartet = [("apple-iphone-17-pro-256gb-silber", "klick", "ohne_wert")]
    assert kennzeichen == erwartet[:ersetzt]


def test_klickordner_nur_aus_gesetzter_umgebung():
    assert klickordner({}) is None
    assert klickordner({UMGEBUNG: ""}) is None
    assert klickordner({UMGEBUNG: "klick"}) == Path("klick")


def test_widerspruch_zeilen_benennen_den_anbieter():
    """Weicht eine heutige Adaptermessung einer ÄLTEREN Klick-Messung, weil sie ihr
    widerspricht, fehlt sie im Messtag - das muss im Protokoll stehen
    (Befund 13.11.2026)."""

    class _Satz:
        anbieter = "congstar"
        id = "buendel--congstar--x--y--24m"

    widerspruch = [
        (_Satz(), {"abgerufen_am": "2026-11-11"}, ["geraet_monatsrate 12.5 statt 30"]),
        (_Satz(), {"abgerufen_am": "2026-11-12"}, ["anschlusspreis 0.0 statt 39.9"]),
    ]
    zeilen = widerspruch_zeilen(widerspruch, "2026-11-13")
    assert len(zeilen) == 1
    assert "congstar" in zeilen[0]
    assert "2 heute gemessene" in zeilen[0]
    assert "vor 2 Tag(en)" in zeilen[0]
    assert "2026-11-13" in zeilen[0]
    assert "geraet_monatsrate 12.5 statt 30" in zeilen[0]


def test_vorrang_von_heute_ist_keine_meldung():
    """Gegenprobe: eine Klick-Messung von heute kostet keinen Messtag."""

    class _Satz:
        anbieter = "Telekom"
        id = "buendel--telekom--x--y--24m"

    heute = [(_Satz(), {"abgerufen_am": "2026-11-13"}, ["egal"])]
    assert widerspruch_zeilen(heute, "2026-11-13") == []


@pytest.mark.parametrize(
    ("gemessen", "bezug", "felder"),
    [
        ({"geraet_monatsrate": 12.5}, {"geraet_monatsrate": 12.6}, []),
        ({"anschlusspreis": 0.0}, {"anschlusspreis": 39.9}, ["anschlusspreis"]),
        ({"geraet_monatsrate": 23.63}, {"geraet_monatsrate": 30.8}, ["geraet"]),
        ({"geraet_zuzahlung": 1000.0}, {"geraet_zuzahlung": 1049.0}, []),
        ({"geraet_zuzahlung": 900.0}, {"geraet_zuzahlung": 1049.0}, ["geraet"]),
        ({"geraet_monatsrate": 12.5}, {"anschlusspreis": 0.0}, ["kein gemeinsames"]),
    ],
    ids=["cent", "erlassen", "rate", "unter-grenze", "ueber-grenze", "ohne-vergleich"],
)
def test_preisgrenze_trennt_aenderung_von_widerspruch(gemessen, bezug, felder):
    """5 % ODER 50 € trennen eine Preisänderung von einem Widerspruch. 1000 statt
    1049 € sind 49 € und damit unter beiden Grenzen; 23,63 statt 30,80 € sind 23 %."""
    texte = widersprueche(gemessen, bezug)
    assert len(texte) == len(felder)
    assert all(teil in text for teil, text in zip(felder, texte, strict=True))
