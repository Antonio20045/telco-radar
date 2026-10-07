"""Vom Klick-Ergebnis zum Bündel-Rohsatz (``klickrohsatz``), ohne Browser.

Die Kombinationen kommen aus echten Antworten (``tests/klickergebnisse.py``). Nur
``erfasst`` wird ein Rohsatz; jeder andere Zustand ist eine gezählte, benannte Lücke
und nie ein Nullwert (Clean Code 3–6). Die Rohsätze laufen durch
``tco_buendel.aus_rohsaetzen`` mit dem echten Tarifbestand vom 03.10.2026: Telekom
kommt mit allen drei Ratenlaufzeiten an, ein unbekannter Tarif bleibt nach derselben
Regel wie jeder Adaptersatz draußen.
"""

from __future__ import annotations

import json

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel
from klickergebnisse import (
    EINSUNDEINS_SEITE,
    O2_SEITE,
    TELEKOM_SEITE,
    einsundeins_lesung,
    erfasst,
    ergebnisdatei,
    lauf,
    o2_lesung,
    telekom_lesung,
)

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete.klickbeleg import Beleg, Belegdatei, Belegpaket
from telco_radar.collect.geraete.klickcrawler import GRUND_NICHT_BESUCHT, GRUND_ZEIT
from telco_radar.collect.geraete.klickecho import pruefe_echo, variante_aus
from telco_radar.collect.geraete.klickergebnis import (
    LAUF_LEER,
    LAUF_NICHT_GELESEN,
    kombination_als_daten,
    laufstatus,
    nicht_besucht,
)
from telco_radar.collect.geraete.klicklauf import (
    BEFUND,
    BELEG_OFFEN,
    LAUF_GELESEN,
    LAUF_GESTOERT,
    NICHT_ANGEBOTEN,
    NICHT_ERFASST,
    Kombiergebnis,
)
from telco_radar.collect.geraete.klickrohsatz import (
    LUECKE_NICHT_BESUCHT,
    LUECKE_SEITE,
    LUECKE_SPEICHER,
    LUECKE_TARIF,
    QUELLE,
    ausbeute,
    speicher_gb,
    tarifschluessel,
)
from telco_radar.collect.geraete.klicktext import Preiswerte
from telco_radar.geraete_config import lade_katalog
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import buendelphasen_aus

HEUTE = "2026-10-07"
M_PLUS = "O2 Mobile Unlimited M Plus"
RATEN_BEI_199 = {36: 30.8, 24: 46.2, 12: 92.5}
"""Rate je Laufzeit bei 199 € Anzahlung laut ``/v2/details`` (Kartentest Telekom)."""


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def bestand():
    return Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")


def _o2(*kombinationen, **felder):
    seiten = [(O2_SEITE, lauf(O2_SEITE, list(kombinationen), **felder))]
    return ergebnisdatei("o2", "o2", seiten, HEUTE)


def test_erfasste_o2_kombination_wird_rohsatz_mit_allen_werten(katalog):
    daten = _o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)))

    aus = ausbeute(daten, katalog)

    (satz,) = aus.rohsaetze
    assert aus.luecken == {}
    assert satz["sku_id"] == "apple-iphone-17-pro-256gb-ohne-farbe"
    assert (satz["anbieter"], satz["laufzeit_monate"]) == ("o2", 36)
    assert satz["tarif_name"] == "O2 Mobile Unlimited M Plus mit 100 MBit/s"
    assert (satz["geraet_zuzahlung"], satz["geraet_monatsrate"]) == (1.0, 36.5)
    assert (satz["tarif_monatlich"], satz["tarif_bindung_monate"]) == (19.99, 24)
    assert (satz["anschlusspreis"], satz["buendel_monatlich"]) == (0.0, None)
    assert satz["tarif_phasen"] == []
    assert satz["quelle_art"] == QUELLE
    assert satz["quelle_url"] == O2_SEITE.adresse
    assert satz["abgerufen_am"] == HEUTE
    assert "herleitung" not in satz


def test_offene_letzte_phase_reicht_bis_zur_letzten_rate(katalog):
    special = erfasst(o2_lesung("256 GB", "O2 Mobile Special", 36))

    (satz,) = ausbeute(_o2(special), katalog).rohsaetze

    assert satz["tarif_monatlich"] == 14.99
    phasen = buendelphasen_aus(satz["tarif_phasen"])
    assert [(p.von_monat, p.bis_monat, p.betrag) for p in phasen] == [
        (1, 24, 14.99),
        (25, 36, 29.99),
    ]


def test_quelle_ist_der_beleglink_der_variante(katalog):
    ergebnis = erfasst(o2_lesung("256 GB", M_PLUS, 36))
    seite = O2_SEITE.adresse.replace("ratenzahlung=36", "ratenzahlung=36&token=geheim")
    datei = Belegdatei("b.webp", "image/webp", "ab" * 32, 1)
    beleg = Beleg(
        beleg_id="cd" * 32,
        anbieter="o2",
        zeitpunkt="2026-10-07T03:00:00Z",
        adresse=O2_SEITE.adresse,
        seite=seite,
        http_status=200,
        antwort_url=seite,
        antwort_status=200,
        variante={},
        status="erfasst",
        werte={},
        fundstellen=(),
        bild=datei,
        mitschnitt=datei,
    )
    mit_beleg = Kombiergebnis(
        ergebnis.variante,
        ergebnis.status,
        werte=ergebnis.werte,
        auswahl=ergebnis.auswahl,
        beleg=Belegpaket(beleg, b"bild", b"har"),
        beleg_status=BELEG_OFFEN,
        screenshot_png=b"png",
        text="Gerät mtl. (36 Raten): 36,50 €",
        antwort_url=seite,
    )

    daten = kombination_als_daten(mit_beleg)
    (satz,) = ausbeute(_o2(mit_beleg), katalog).rohsaetze

    assert satz["quelle_url"] == seite.replace("geheim", "ENTFERNT")
    assert satz["beleg_id"] == "cd" * 32
    text = json.dumps(daten)
    assert "geheim" not in text and "png" not in text and "36,50" not in text


def test_telekom_kommt_mit_allen_ratenlaufzeiten_als_buendel_an(katalog, bestand):
    kombinationen = [
        erfasst(telekom_lesung(str(n), "199"), laufzeit=n) for n in RATEN_BEI_199
    ]
    daten = ergebnisdatei(
        "Telekom",
        "telekom",
        [(TELEKOM_SEITE, lauf(TELEKOM_SEITE, kombinationen))],
        HEUTE,
    )

    aus = ausbeute(daten, katalog)
    bilanz = aus_rohsaetzen(aus.rohsaetze, bestand, HEUTE)

    assert bilanz.ohne_tarif == 0 and bilanz.ungueltig == 0
    raten = {b.laufzeit_monate: b.geraet_monatsrate for b in bilanz.buendel}
    assert raten == RATEN_BEI_199
    assert {b.tarif_id for b in bilanz.buendel} == {"telekom:magentamobil-m"}
    assert {b.sku_id for b in bilanz.buendel} == {
        "apple-iphone-17-pro-512gb-ohne-farbe"
    }
    assert {(b.geraet_zuzahlung, b.tarif_monatlich) for b in bilanz.buendel} == {
        (199.0, 49.95)
    }


def test_ein_vertrag_traegt_buendelbetrag_und_unbekannter_tarif_bleibt_luecke(
    katalog, bestand
):
    """1&1 nennt den Tarif als Kennung; ohne Adapter-Gegenstück löst sie nicht auf.

    Gegenprobe: der Satz wird kein Bündel mit 0 €, sondern ein offener Tarif."""
    daten = ergebnisdatei(
        "1&1",
        "1und1",
        [
            (
                EINSUNDEINS_SEITE,
                lauf(
                    EINSUNDEINS_SEITE,
                    [erfasst(einsundeins_lesung(), "256", "tariff-anf-s-mvl", 36)],
                ),
            )
        ],
        HEUTE,
        vertragsform="ein_vertrag",
    )

    (satz,) = ausbeute(daten, katalog).rohsaetze
    bilanz = aus_rohsaetzen([satz], bestand, HEUTE)

    assert (satz["buendel_monatlich"], satz["laufzeit_monate"]) == (44.99, 36)
    assert satz["geraet_monatsrate"] is None and satz["tarif_monatlich"] is None
    assert satz["geraet_zuzahlung"] is None
    assert bilanz.buendel == []
    assert bilanz.offene_tarife == {"tariff-anf-s-mvl": 1}


def test_jeder_andere_zustand_ist_eine_gezaehlte_luecke(katalog):
    lesung = o2_lesung("512 GB", M_PLUS, 24)
    gewaehlt = variante_aus("256 GB", "O2 Mobile Unlimited M Plus mit 100 MBit/s", 24)
    echo = pruefe_echo(gewaehlt, gewaehlt, lesung.werte, lesung)
    zwoelf = variante_aus("256 GB", "O2 Mobile Unlimited M Plus mit 100 MBit/s", 12)
    kombinationen = [
        Kombiergebnis(gewaehlt, BEFUND, "Echo", befunde=echo.befunde),
        Kombiergebnis(zwoelf, NICHT_ANGEBOTEN, "Seite bietet laufzeit 12 nicht an"),
        Kombiergebnis(gewaehlt, NICHT_ERFASST, f"{GRUND_NICHT_BESUCHT}: {GRUND_ZEIT}"),
        Kombiergebnis(gewaehlt, NICHT_ERFASST, "Knöpfe für tarif nicht gefunden (x)"),
    ]

    aus = ausbeute(_o2(*kombinationen), katalog)

    assert echo.befunde
    assert aus.rohsaetze == []
    assert aus.luecken == {
        BEFUND: 1,
        NICHT_ANGEBOTEN: 1,
        LUECKE_NICHT_BESUCHT: 1,
        NICHT_ERFASST: 1,
    }


def test_erfasst_ohne_tarif_oder_mit_fremdem_speicher_ist_luecke(katalog):
    """Vodafone liest den Tarif nicht (Karte: ``unbekannt``); 64 GB hat das
    iPhone 17 Pro nicht."""
    lesung = o2_lesung("256 GB", M_PLUS, 36)
    kombinationen = [
        erfasst(lesung, tarif="unbekannt"),
        erfasst(lesung, speicher="64 GB"),
        erfasst(lesung),
    ]

    aus = ausbeute(_o2(*kombinationen), katalog)

    assert len(aus.rohsaetze) == 1
    assert aus.luecken == {LUECKE_TARIF: 1, LUECKE_SPEICHER: 1}


def test_seite_eines_gestoerten_laufs_liefert_keinen_rohsatz(katalog):
    gestoert = _o2(
        erfasst(o2_lesung("256 GB", M_PLUS, 36)),
        status=LAUF_GESTOERT,
        grund="Abruf gestört (HTTP 403)",
    )

    aus = ausbeute(gestoert, katalog)

    assert aus.rohsaetze == []
    assert aus.luecken == {LUECKE_SEITE: 1}
    assert gestoert["laufstatus"] == LAUF_GESTOERT


@pytest.mark.parametrize(
    ("seiten", "erwartet"),
    [
        ([("gelesen", "erfasst")], LAUF_GELESEN),
        ([("gelesen", "befund")], LAUF_LEER),
        ([("gesperrt", None)], LAUF_NICHT_GELESEN),
        ([("nicht_besucht", None)], LAUF_NICHT_GELESEN),
        ([("gelesen", "erfasst"), ("gestoert", None)], LAUF_GESTOERT),
    ],
)
def test_laufstatus_des_anbieters(seiten, erwartet):
    daten = [
        {
            "adresse": f"https://a.example/{i}",
            "status": status,
            "grund": status,
            "kombinationen": [] if k is None else [{"status": k}],
        }
        for i, (status, k) in enumerate(seiten)
    ]
    assert laufstatus(daten)[0] == erwartet


def test_nicht_besuchte_seite_ist_nie_leer():
    eintrag = nicht_besucht(O2_SEITE, "Zeitbudget des Jobs erschöpft: noch 10 s")
    assert laufstatus([eintrag]) == (LAUF_NICHT_GELESEN, eintrag["grund"])


@pytest.mark.parametrize(
    ("text", "gb"), [("256 GB", 256), ("1 TB", 1024), ("512", 512), ("viel", None)]
)
def test_speicher_aus_dem_knopfwert(text, gb):
    assert speicher_gb(text) == gb


def test_tarifschluessel_ohne_bindungszusatz_und_markup():
    assert tarifschluessel("O2\xa0Mobile Special") == tarifschluessel(
        "O2 Mobile Special (24 Mon.)"
    )
    assert tarifschluessel("O<sub>2</sub> Mobile M") == "o2-mobile-m"
    assert tarifschluessel("O2 Mobile M") != tarifschluessel("O2 Mobile M Plus")
    assert tarifschluessel(Preiswerte()) == ""
