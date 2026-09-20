"""A1 (20.09.2026): das Orakel der Leitzahl gegen den ECHTEN Bestand.

Die Zusicherung des Auftrags, in einer Zeile: KEINE Leitzahl unter dem
Barpreis (`preis_ohne_vertrag`) desselben Anbieters, ohne dass ein
benannter Rabatt die Differenz belegen wuerde. Eine Leitzahl unter dem
eigenen Barpreis hiesse: Tarif plus Raten sind zusammen BILLIGER als das
Gerät allein - das ist entweder eine Subvention (die belegt sein will)
oder ein Erfassungsfehler, und der niedrigste Preis ist immer der
wahrscheinlichste Fehler (CLAUDE.md, Fallstricke Geräteradar).

Warum dieser Test rot war, bevor A1 umgesetzt wurde
---------------------------------------------------
Die alte Leitzahl kappte die Geräteraten bei 24 Monaten - 12 von 36 Raten
fielen aus der Zahl. Am Bestand vom 20.09.2026 lag dadurch JEDE der 88
Verletzungen nur wenige Euro unter dem Barpreis (congstar 57, o2 16,
Vodafone 15, Abstand 2,11 bis 456,00 €): die gekappte Zahl war UM die
Restschuld zu niedrig. Mit der vollständigen Rechnung (alle Raten in der
Leitzahl) ist der Abstand weg - 0 Verletzungen ueber 697 vergleichbare
Bündel. Der Test haelt das fest, damit die Kappung nicht zurueckkommt.

Nur LESPEND: `data/state/` wird von einem Test nie geschrieben (harte
Regel 1 und 2). Fehlt der Bestand (Frisch-Checkout ohne Daten), springt
der Test ueber - sein Lookup laeuft dann nicht ins Leere, sondern prueft
bewusst nichts.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from telco_radar.report import geraete_tco_karten as karten
from telco_radar.tco_model import Buendel, TCO_HORIZONT, tco_24

WURZEL = pathlib.Path(__file__).resolve().parents[1]
ZUSTAND = WURZEL / "data" / "state"

BESTAND_DA = ((ZUSTAND / "geraete_tco.json").exists()
              and (ZUSTAND / "geraete_db.json").exists()
              and (ZUSTAND / "tarife.jsonl").exists())


def _tarife() -> dict:
    tarife = {}
    for zeile in (ZUSTAND / "tarife.jsonl").read_text(
            encoding="utf-8").splitlines():
        if zeile.strip():
            satz = json.loads(zeile)
            tarife[satz.get("tarif_id") or satz.get("id")] = satz
    return tarife


def _barpreise_neu() -> dict:
    """(anbieter, sku_id) -> guenstigster NEU-Barpreis derselben SKU."""
    db = json.loads((ZUSTAND / "geraete_db.json").read_text(encoding="utf-8"))
    beste: dict = {}
    for e in db.get("listungen") or []:
        if e.get("preis_ohne_vertrag") is None:
            continue
        if (e.get("zustand") or "neu") != "neu":
            continue
        key = (e.get("anbieter"), e.get("sku_id"))
        wert = float(e["preis_ohne_vertrag"])
        if key not in beste or wert < beste[key]:
            beste[key] = wert
    return beste


@pytest.mark.skipif(not BESTAND_DA, reason="kein ausgelieferter Bestand")
def test_keine_leitzahl_unter_dem_eigenen_barpreis():
    """Das Orakel: 697 vergleichbare Bündel, 0 Verletzungen.

    Verglichen wird zustandsgleich (Neu-Bündel gegen Neu-Barpreis; Farben
    sind Preisdimensionen, refurbished sowieso). Die Phasen-Anreicherung
    laeuft ueber denselben Weg wie die Seite (`phasen_fuer_buendel` -
    Phasen nur ohne Widerspruch zur Messung, QA-Fix 20.09.2026), sonst
    pruefte der Test eine andere Rechnung als die Tafel zeigt.
    """
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    tarife = _tarife()
    bar = _barpreise_neu()
    geprueft = 0
    verletzungen = []
    for satz in tco.get("buendel") or []:
        if satz.get("rabatte"):
            continue                      # belegter Rabatt darf unterbieten
        if (satz.get("zustand") or "") and satz["zustand"] != "neu":
            continue
        b = _buendel_aus_satz(satz)
        if b is None:
            continue
        b.tarif_phasen = karten.phasen_fuer_buendel(
            tarife.get(b.tarif_id) or {}, b.tarif_monatlich)
        kennzahl = tco_24(b)
        if not kennzahl.belastbar or kennzahl.gesamt is None:
            continue
        barpreis = bar.get((b.anbieter, b.sku_id))
        if barpreis is None:
            continue
        geprueft += 1
        if kennzahl.gesamt < barpreis:
            verletzungen.append((satz.get("id"), kennzahl.gesamt, barpreis))
    # Gegenprobe: der Lauf hat wirklich eine Vergleichsmenge gesehen -
    # sonst waere die Zusicherung gruen, ohne etwas geprueft zu haben.
    assert geprueft >= 600, \
        f"unerwartet duenne Vergleichsmenge: {geprueft} Bündel"
    assert verletzungen == [], \
        f"{len(verletzungen)} Leitzahlen unter dem eigenen Barpreis, " \
        f"z. B. {verletzungen[:3]}"


def _buendel_aus_satz(satz: dict) -> Buendel | None:
    """Ein Bestands-Satz als Buendel - None, wenn er nicht lesbar ist."""
    try:
        return Buendel(
            sku_id=satz.get("sku_id") or "",
            anbieter=satz.get("anbieter") or "?",
            tarif_name=satz.get("tarif_name") or "",
            tarif_id=satz.get("tarif_id") or "",
            tarif_monatlich=satz.get("tarif_monatlich"),
            tarif_bindung_monate=satz.get("tarif_bindung_monate"),
            buendel_monatlich=satz.get("buendel_monatlich"),
            geraet_zuzahlung=satz.get("geraet_zuzahlung"),
            geraet_monatsrate=satz.get("geraet_monatsrate"),
            laufzeit_monate=int(satz.get("laufzeit_monate") or 24),
            anschlusspreis=satz.get("anschlusspreis"),
            zustand=satz.get("zustand") or "",
            quelle_url=satz.get("quelle_url") or "",
            abgerufen_am=satz.get("abgerufen_am") or "")
    except (TypeError, ValueError):
        return None


@pytest.mark.skipif(not BESTAND_DA, reason="kein ausgelieferter Bestand")
def test_widerspruch_pib_und_shopmessung_am_echten_bestand():
    """Der Pruefer-Befund vom 20.09.2026 (schwere "hoch") am echten Bestand:
    Samsung Galaxy Z Fold8 256 an Vodafone Mobil XS misst 31,95 EUR im
    Shop, das Blatt nennt 29,95 EUR (Tarif ohne Smartphone-Zuschlag).

        0,99 + 24 x 31,95 + 36 x 42,50 + 0 = 2.297,79 EUR

    Bis zum Fix entschieden die Phasen des Blatts den Widerspruch still
    fuer sich: 2.249,79 EUR auf der Karte, 718,80 EUR im Posten - neben
    einer Bauteilezeile, die 'monatlich 31,95 EUR' sagte."""
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    tarife = _tarife()
    treffer = [s for s in tco.get("buendel") or []
               if s.get("anbieter") == "Vodafone"
               and "z-fold8-256gb" in (s.get("sku_id") or "")
               and s.get("tarif_id") == "vodafone:vodafone-mobil-xs"
               and s.get("tarif_monatlich") == 31.95
               and s.get("geraet_monatsrate") == 42.5]
    assert treffer, "der Befundsfall fehlt im Bestand - Literal pruefen"
    b = _buendel_aus_satz(treffer[0])
    assert b is not None
    # Gegenprobe: das Blatt HAT Phasen, der Konflikt ist real - sonst
    # pruefte dieser Test den unstrittigen Fall.
    blatt = karten.phasen_aus_tarifsatz(tarife.get(b.tarif_id) or {})
    assert blatt, "das Blatt des Befundsfall hat keine Phasen mehr"
    b.tarif_phasen = karten.phasen_fuer_buendel(
        tarife.get(b.tarif_id) or {}, b.tarif_monatlich)
    assert b.tarif_phasen == [], "der Widerspruch wurde nicht erkannt"
    kennzahl = tco_24(b)
    assert kennzahl.bestandteile["Tarif über 24 Monate"] == 766.8
    assert kennzahl.gesamt == 2297.79
    assert kennzahl.gesamt != 2249.79


@pytest.mark.skipif(not BESTAND_DA, reason="kein ausgelieferter Bestand")
def test_kein_tarifposten_wider_die_gemessene_monatsrate():
    """Das Rechenbarkeits-Orakel ueber den GANZEN Bestand: der Tarifposten
    einer Leitzahl ist entweder flach die gemessene Monatsrate oder
    phasengewichtet aus einem Blatt, dessen Preisspanne die Messung
    enthaelt. Alles andere hiesse: die Karte zeigt einen Preis, die
    Leitzahl rechnet einen anderen (der Befund vom 20.09.2026).

    Gegenproben: der Lauf sieht Konfliktbündel (Blatt ausserhalb der
    Messung - Vodafone Mobil XS/S/M mit Smartphone-Zuschlag) UND
    phasentragende Bündel (Telekom, congstar) - sonst pruefte er nur
    einen Zweig und der andere faelle still um."""
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    tarife = _tarife()
    konflikte = 0
    mit_phasen = 0
    for satz in tco.get("buendel") or []:
        messung = satz.get("tarif_monatlich")
        blatt = karten.phasen_aus_tarifsatz(
            tarife.get(satz.get("tarif_id") or "") or {})
        if messung is None or not blatt:
            continue
        b = _buendel_aus_satz(satz)
        if b is None:
            continue
        b.tarif_phasen = karten.phasen_fuer_buendel(
            tarife.get(b.tarif_id) or {}, b.tarif_monatlich)
        tarifposten = next(
            (v for n, v in tco_24(b).bestandteile.items()
             if n.startswith("Tarif über")), None)
        if tarifposten is None:
            continue
        betraege = [p.betrag for p in blatt]
        if (min(betraege) - karten._PREIS_TOLERANZ <= messung
                <= max(betraege) + karten._PREIS_TOLERANZ):
            mit_phasen += 1
            continue        # das Blatt beschreibt dieses Angebot: erlaubt
        konflikte += 1
        assert tarifposten == round(TCO_HORIZONT * messung, 2), \
            f"{satz.get('id')}: Tarifposten {tarifposten} wider die " \
            f"Messung {messung}"
    assert konflikte >= 400, \
        f"Konfliktmenge duenn ({konflikte}) - Literale pruefen"
    assert mit_phasen >= 100, \
        f"phasentragende Menge duenn ({mit_phasen}) - Literale pruefen"


@pytest.mark.skipif(not BESTAND_DA, reason="kein ausgelieferter Bestand")
def test_der_pflichtfall_steht_wirklich_im_bestand():
    """Die Zahl des Auftrags kommt nicht aus dem Kopf: congstar fuehrt das
    iPhone 17 Pro 256 GB zur Allnet Flat XS mit genau den Posten des
    Pflichtfalls (1 € + 24 × 15,00 € + 36 × 30,50 € + 0 €), und die
    Leitzahl dafuer ist 1.459,00 € - nicht die gekappte 1.093,00 €."""
    tco = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    treffer = [s for s in tco.get("buendel") or []
               if s.get("anbieter") == "congstar"
               and "iphone-17-pro" in (s.get("sku_id") or "")
               and s.get("tarif_monatlich") == 15.0
               and s.get("geraet_monatsrate") == 30.5]
    assert treffer, "der Pflichtfall fehlt im Bestand - Literal pruefen"
    satz = treffer[0]
    b = Buendel(sku_id=satz["sku_id"], anbieter=satz["anbieter"],
                tarif_name=satz["tarif_name"],
                tarif_id=satz.get("tarif_id", ""),
                tarif_monatlich=satz["tarif_monatlich"],
                geraet_zuzahlung=satz.get("geraet_zuzahlung"),
                geraet_monatsrate=satz["geraet_monatsrate"],
                laufzeit_monate=satz.get("laufzeit_monate", 24),
                anschlusspreis=satz.get("anschlusspreis"))
    kennzahl = tco_24(b)
    assert kennzahl.gesamt == 1459.0
    assert kennzahl.gesamt != 1093.0
