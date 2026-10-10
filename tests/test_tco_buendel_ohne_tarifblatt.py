"""Bündel, deren Tarif kein Tarifblatt im Bestand hat, und Zusatzkarten.

Gerätelauf 07.10.2026 (Actions-Job 112790602987): `tco_buendel.aus_rohsaetzen`
verwarf 1056 Rohsätze „ohne auflösbaren Tarif“, darunter „O2 Mobile Special (24
Mon.)“ (176) und „O2 Mobile Unlimited L Plus mit 300 MBit/s (24 Mon.)“ (148). o2
führt beide nur mit Gerät: Special hat keine SIM-only-Kachel, und die Kachel
„Unlimited L“ verlinkt `o2-mobile-unlimited-l` ohne `-plus`. Antonio hat Unlimited L
Plus am Shop gesehen (iPhone 17 Pro 256 GB, 24 Raten: 54,50 + 29,99 = 84,49 €).

Die Rohsätze stammen aus der echten Vertiefung zum iPhone 17 Pro
(`o2_vertiefung_iphone17pro.json.gz`, 29.09.2026) über den Sammler; der Bestand ist
der Schnappschuss vom 03.10.2026. Die Vodafone-Sätze kommen aus der echten
Tarifschnittstelle (`vodafone_tarif_hardware_geraet_2026-09-29.json`). „Red+ Data“
und „Smart Tech M Sub 9“ stehen nur im Protokoll des Laufs; ihre Sätze hier sind
nachgebaut.
"""

from __future__ import annotations

import gzip
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from bestand_pfad import ZUSTAND, abbild, lese_wurzel

from telco_radar.analyze import tco_buendel
from telco_radar.analyze.geraete_pruefstatus import (
    NICHT_PRUEFBAR,
    Kontext,
    buendel_aus_satz,
)
from telco_radar.analyze.geraete_regeln import pruefe_bestand, sim_only_preis
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.collect.geraete import sammle_anbieter
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.collect.geraete.vodafone import lies_buendel, loese_tarifnamen
from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog
from telco_radar.report.geraete_tco_view import aufbereiten
from telco_radar.report.html import render_site
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import HOCH
from telco_radar.tco_model import POSTEN_TARIF, kosten_ueber

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent
_HEUTE = "2026-09-29"
NUR_MIT_GERAET = "nur_mit_geraet"
"""Die Güte, wie sie in `geraete_tco.json` steht (`tarif_model.NUR_MIT_GERAET`)."""
_SPECIAL = "O2 Mobile Special (24 Mon.)"
_L_PLUS = "O2 Mobile Unlimited L Plus mit 300 MBit/s (24 Mon.)"
_L = "O2 Mobile Unlimited L mit 300 MBit/s (24 Mon.)"
_M_PLUS = "O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)"
_KATALOG_URL = (
    "https://www.o2online.de/e-shop/rest/catalog/o2shop/"
    "privatkunden/ratenzahlung/default/__not-specified__/"
    "__not-specified__/__not-specified__"
)


@pytest.fixture(scope="module")
def bestand():
    return Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")


@pytest.fixture(scope="module")
def o2_roh():
    """Die 48 Rohsätze des Sammlers zum iPhone 17 Pro, mit `sku_id`."""
    with gzip.open(_FIX / "o2_vertiefung_iphone17pro.json.gz", "rt") as fh:
        mitschnitt = json.load(fh)
    antworten = dict(mitschnitt["antworten"])
    antworten[_KATALOG_URL] = json.dumps(mitschnitt["katalog"])

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /postpaid/\n")
        return (200, antworten[url]) if url in antworten else (404, "")

    anbieter = Anbieter(
        name="o2",
        typ="netzbetreiber",
        methode="o2_katalog",
        basis_url="https://www.o2online.de",
        rate_limit_sekunden=0,
        kopfzeilen={"Accept": "application/vnd.commerce.message+json"},
        einstiege=[Einstieg(url=_KATALOG_URL, kind="buendel")],
    )
    bilanz = sammle_anbieter(
        anbieter,
        lade_katalog(lese_wurzel()),
        lade_farben(_WURZEL),
        hole,
        _HEUTE,
        RobotsWaechter(hole=hole),
        datetime(2026, 9, 29, 3, tzinfo=UTC),
    )
    assert len(bilanz.buendel) == 48
    return bilanz.buendel


@pytest.fixture(scope="module")
def o2_bilanz(o2_roh, bestand):
    return aus_rohsaetzen([dict(s) for s in o2_roh], bestand, _HEUTE)


def _je_tarif(bilanz, name):
    return [b for b in bilanz.buendel if b.tarif_name == name]


def _eines(bilanz, name, speicher, laufzeit):
    treffer = [
        b
        for b in _je_tarif(bilanz, name)
        if f"-{speicher}gb-" in b.sku_id and b.laufzeit_monate == laufzeit
    ]
    assert len(treffer) == 1, (name, speicher, laufzeit, treffer)
    return treffer[0]


def test_special_und_unlimited_l_plus_kommen_als_buendel_an(o2_bilanz, bestand):
    assert o2_bilanz.ohne_tarif == 0, o2_bilanz.offene_tarife
    assert len(o2_bilanz.buendel) == 48
    for name, tid in (
        (_SPECIAL, "o2:o2-mobile-special"),
        (_L_PLUS, "o2:o2-mobile-unlimited-l-plus"),
    ):
        saetze = _je_tarif(o2_bilanz, name)
        assert len(saetze) == 4, name
        assert {b.tarif_id for b in saetze} == {tid}
        assert {b.tarif_id_guete for b in saetze} == {NUR_MIT_GERAET}
    assert o2_bilanz.nur_mit_geraet == 8
    for anbieter, slug in (
        ("o2", "o2-mobile-unlimited-m-plus"),
        ("o2", "o2-mobile-unlimited-l"),
        ("Telekom", "o2-mobile-special"),
    ):
        assert tco_buendel.ohne_tarifblatt(bestand, anbieter, slug) is None, slug


def test_kosten_ueber_24_monate_wie_im_shop(o2_bilanz):
    """iPhone 17 Pro 256 GB, 24 Raten: 7,00 Anzahlung, 24 × (54,50 + 29,99)."""
    l_plus = _eines(o2_bilanz, _L_PLUS, 256, 24)
    assert round(l_plus.geraet_monatsrate + l_plus.tarif_monatlich, 2) == 84.49
    kosten = kosten_ueber(l_plus)
    assert (kosten.monate, kosten.gesamt) == (24, 2034.76)
    assert kosten.luecken == []
    special = kosten_ueber(_eines(o2_bilanz, _SPECIAL, 256, 24))
    assert (special.monate, special.gesamt) == (24, 1674.76)


def test_36_raten_ohne_tarifblatt_zaehlen_24_tarifmonate(o2_bilanz):
    """Ohne Tarifblatt ist der Tarifpreis nach Monat 24 nicht belegt; gebraucht wird
    er nicht, ab Monat 25 zählt nur die Rate (Antonio, 10.10.2026)."""
    b = _eines(o2_bilanz, _L_PLUS, 256, 36)
    kosten = kosten_ueber(b)
    assert kosten.monate == 36 and kosten.luecken == []
    assert kosten.posten["Tarif über 24 Monate"] == round(24 * b.tarif_monatlich, 2)
    assert f"{POSTEN_TARIF} Monat 25–36" not in kosten.luecken


def test_plus_wird_nie_auf_den_tarif_ohne_plus_abgebildet(o2_bilanz, bestand):
    """Gegenprobe: Unlimited L Plus bleibt ein eigener Tarif. Unlimited M Plus
    hängt weiter am Grundtarif, weil o2s Kachel genau diesen Slug verlinkt."""
    assert (
        bestand.loese("o2", _L_PLUS, slug="o2-mobile-unlimited-l-plus", mit_geraet=True)
        is None
    )
    assert "o2:o2-mobile-unlimited-l" not in {
        b.tarif_id for b in _je_tarif(o2_bilanz, _L_PLUS)
    }
    for name, tid in (
        (_L, "o2:o2-mobile-unlimited-l"),
        (_M_PLUS, "o2:o2-mobile-unlimited-m"),
    ):
        saetze = _je_tarif(o2_bilanz, name)
        assert {(b.tarif_id, b.tarif_id_guete) for b in saetze} == {(tid, HOCH)}


def test_ohne_tarifblatt_kein_sim_only_vergleich(o2_bilanz):
    """Auch ein Maßstab unter derselben Tarif-ID zählt nicht: der Tarif hat keinen
    SIM-only-Satz. Gegenprobe: derselbe Schlüssel trifft beim Grundtarif."""
    special = _eines(o2_bilanz, _SPECIAL, 256, 24)
    l_ohne = _eines(o2_bilanz, _L, 256, 24)
    tabelle = {"o2|o2:o2-mobile-special": 9.99, "o2|o2:o2-mobile-unlimited-l": 39.99}
    assert sim_only_preis(special, tabelle) is None
    assert sim_only_preis(l_ohne, tabelle) == 39.99


@pytest.fixture()
def gespeichert(o2_bilanz, tmp_path):
    tco = TcoDB(tmp_path / "geraete_tco.json")
    tco.upsert_buendel(o2_bilanz.buendel, _HEUTE)
    tco.save(_HEUTE)
    return TcoDB(tmp_path / "geraete_tco.json")


def test_speicher_und_pruefstelle_tragen_die_guete(gespeichert):
    saetze = [s for s in gespeichert.buendel() if s["tarif_name"] == _SPECIAL]
    assert len(saetze) == 4
    assert {s["tarif_id_guete"] for s in saetze} == {NUR_MIT_GERAET}
    assert {buendel_aus_satz(s).tarif_id_guete for s in saetze} == {NUR_MIT_GERAET}
    ergebnisse = pruefe_bestand(
        saetze, Kontext(heute=_HEUTE, sim_only={"o2|o2:o2-mobile-special": 9.99})
    )
    for e in ergebnisse.values():
        regel_3 = [b for b in e.befunde if b.regel == 3]
        assert [(b.ergebnis, b.satz) for b in regel_3] == [
            (NICHT_PRUEFBAR, "SIM-only-Preis desselben Tarifs fehlt")
        ]


def test_die_seite_zeigt_den_tarifnamen_ohne_geraeteanteil(gespeichert, bestand):
    """Nichts stürzt ab, der Name steht da, ein Geräteanteil nie - auch nicht mit
    einem Maßstab unter derselben Tarif-ID."""
    referenzen = gespeichert.referenzen() + [
        {
            "anbieter": "o2",
            "tarif_name": "O2 Mobile Special",
            "tarif_id": "o2:o2-mobile-special",
            "tarif_id_guete": HOCH,
            "tarif_sim_only_monatlich": 9.99,
            "anschlusspreis": 0.0,
        }
    ]
    modell = aufbereiten(
        gespeichert.buendel(),
        referenzen,
        [],
        lade_katalog(lese_wurzel()),
        tarife=bestand.je_id_aktuell,
        heute=_HEUTE,
    )
    zeilen = [z for z in modell["zeilen"] if z["tarif"] in (_SPECIAL, _L_PLUS)]
    assert len(zeilen) == 8
    assert all(z["geraeteanteil"] is None for z in zeilen)
    karten = [
        k
        for m in modell["modelle"]
        for k in m["karten"]
        if k.get("tarif") == _L_PLUS and k.get("raten_laufzeit") == 24
    ]
    assert karten and {k["tarif_id_guete"] for k in karten} == {NUR_MIT_GERAET}
    assert 2034.76 in {k["gesamt"] for k in karten}


@pytest.fixture(scope="module")
def ab_monat(o2_bilanz, tmp_path_factory) -> list[tuple[str, str]]:
    """Je Bündelzeile der gerenderten Seite (Schnappschuss plus o2-Bündel): Tarif
    und Text der Zeile „ab Monat …“."""
    site = tmp_path_factory.mktemp("ohne-tarifblatt") / "site"
    berichte = abbild(site.parent)
    tco = TcoDB(site.parent / "data" / "state" / "geraete_tco.json")
    tco.upsert_buendel(o2_bilanz.buendel, _HEUTE)
    tco.save(_HEUTE)
    render_site(site, berichte)
    seite = (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8")
    zeilen = []
    for block in re.findall(r'<details class="gr-bnd.*?</details>', seite, flags=re.S):
        tarif = next((n for n in (_SPECIAL, _L_PLUS, _L) if n in block), None)
        nach = re.search(r'class="gr-kk-nach[^"]*">(.*?)</p>', block, flags=re.S)
        if tarif and nach:
            zeilen.append((tarif, re.sub(r"\s+", " ", nach.group(1)).strip()))
    return zeilen


def test_ab_monat_25_ohne_tarifblatt_nennt_keine_tarifquelle(ab_monat):
    """Prüferbefund zu fb832ba4: die Lücke behauptete eine Tarifquelle, weil die
    Vorlage den Grund an der Tarif-ID festmachte. Gegenprobe: Unlimited L hat ein
    Tarifblatt und behält den Quellengrund."""
    ohne = [z for tarif, z in ab_monat if tarif in (_SPECIAL, _L_PLUS)]
    mit = [z for tarif, z in ab_monat if tarif == _L]
    assert len(ohne) == 8 and mit
    assert not [z for z in ohne + mit if "ab Monat 37" in z]
    for zeile in ohne:
        assert "Tarifquelle" not in zeile and "nicht im Tarifbestand" in zeile, zeile
    assert not [z for z in mit if "nicht im Tarifbestand" in z]


def _bestand_ohne(weg) -> Tarifbestand:
    zeilen = (ZUSTAND / "tarife.jsonl").read_text(encoding="utf-8").splitlines()
    return Tarifbestand(
        [s for z in zeilen if z.strip() and not weg(s := json.loads(z))]
    )


def test_plus_ohne_gelesene_kachel_wechselt_nie_die_tarif_id(o2_roh):
    """Prüferbefund zu fb832ba4: ohne die Kachel "Unlimited M" (Tarifsammler Mi/Fr,
    Gerätelauf täglich) bekam M Plus `o2:...-m-plus`, mit ihr `o2:...-m`. Jetzt
    bleibt der Satz bis zur Kachel ohne Tarif. Gegenprobe: L Plus, dessen
    Grundtarif-Kachel gelesen ist, kommt im selben Bestand an."""
    ohne_kachel = _bestand_ohne(
        lambda s: s.get("buendel_slug") == "o2-mobile-unlimited-m-plus"
    )
    roh = [dict(s) for s in o2_roh if s["tarif_name"] in (_M_PLUS, _L_PLUS)]
    vorher = aus_rohsaetzen(roh, ohne_kachel, _HEUTE)
    assert vorher.offene_tarife == {_M_PLUS: 4}
    assert {(b.tarif_name, b.tarif_id) for b in vorher.buendel} == {
        (_L_PLUS, "o2:o2-mobile-unlimited-l-plus")
    }
    nachher = aus_rohsaetzen(roh, _bestand_ohne(lambda s: False), _HEUTE)
    assert {b.tarif_id for b in nachher.buendel if b.tarif_name == _M_PLUS} == {
        "o2:o2-mobile-unlimited-m"
    }


def test_ohne_gelesene_o2_kacheln_kein_tarif_nur_mit_geraet(o2_roh):
    """Nicht gelesen ist nicht "nur mit Gerät": ohne eine einzige o2-Kachel im
    Bestand bekommt Special keine Tarif-ID."""
    bestand = _bestand_ohne(lambda s: s.get("anbieter") == "o2")
    roh = [dict(s) for s in o2_roh if s["tarif_name"] == _SPECIAL]
    bilanz = aus_rohsaetzen(roh, bestand, _HEUTE)
    assert (bilanz.buendel, bilanz.offene_tarife) == ([], {_SPECIAL: 4})


def _vodafone_roh():
    """Pixel 11 (sechs Varianten) mit allen Angeboten der Tarifschnittstelle."""
    text = (_FIX / "vodafone_virtualitem_2026-09-29.json").read_text(encoding="utf-8")
    roh = [
        {
            **s,
            "anbieter": "Vodafone",
            "sku_id": f"pixel-11-{s['sku']}",
            "zustand": "neu",
            "quelle_url": s["url"],
        }
        for s in lies_buendel(text)
    ]
    antwort = (_FIX / "vodafone_tarif_hardware_geraet_2026-09-29.json").read_text(
        encoding="utf-8"
    )
    loese_tarifnamen(lambda url, kopfzeilen=None: (200, antwort), {}, roh)
    return roh


def test_familycard_bleibt_als_zusatzkarte_draussen(bestand):
    bilanz = aus_rohsaetzen(_vodafone_roh(), bestand, _HEUTE)
    assert bilanz.ohne_tarif == 0, bilanz.offene_tarife
    assert not set(bilanz.offene_tarife)
    assert bilanz.zusatzkarte == 6 * 4
    assert bilanz.zusatzkarten == {
        "FamilyCard S": 6,
        "FamilyCard M": 6,
        "FamilyCard L": 6,
        "FamilyCard XL": 6,
    }
    assert len(bilanz.buendel) == 6 * 15
    assert NUR_MIT_GERAET not in {b.tarif_id_guete for b in bilanz.buendel}
    assert bilanz.verworfen == 6 * 4


def _vodafone_satz(name):
    return {
        "anbieter": "Vodafone",
        "sku_id": "apple-ipad-air-128gb-grau",
        "tarif_name": name,
        "tarif_slug": "3F714701A0",
        "tarif_monatlich": 19.99,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 20.0,
        "laufzeit_monate": 24,
        "anschlusspreis": 0.0,
    }


def test_red_plus_ist_zusatzkarte_smart_tech_bleibt_offen(bestand):
    """Gegenprobe: Vodafones `tarif_slug` ist ein wechselnder Angebots-Hash und kein
    Tarifschlüssel. Ein unbekannter Vodafone-Tarif bekommt deshalb keine Tarif-ID,
    sondern bleibt mit Namen auf der Arbeitsliste."""
    bilanz = aus_rohsaetzen(
        [_vodafone_satz("Red+ Data"), _vodafone_satz("Smart Tech M Sub 9")],
        bestand,
        _HEUTE,
    )
    assert bilanz.offene_tarife == {"Smart Tech M Sub 9": 1}
    assert bilanz.zusatzkarten == {"Red+ Data": 1}
    assert (bilanz.zusatzkarte, bilanz.ohne_tarif, bilanz.buendel) == (1, 1, [])


def test_ein_o2_tarif_ohne_slug_bleibt_offen(bestand):
    """Ohne Slug gibt es keinen stabilen Schlüssel; aus dem Titel wird keine ID."""
    satz = {**_vodafone_satz(_SPECIAL), "anbieter": "o2", "tarif_slug": ""}
    bilanz = aus_rohsaetzen([satz], bestand, _HEUTE)
    assert (bilanz.ohne_tarif, bilanz.buendel) == (1, [])
    assert bilanz.offene_tarife == {_SPECIAL: 1}
