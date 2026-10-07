"""Monat 25 bis 36: Karte, Tarifblatt und o2-Preiszusammenfassung gegen die Bündelphase.

Reproduktionen der Prüferrunde zu 99398e8d. Die Zeile „ab Monat 25“ liest aus
denselben Phasen wie `kosten_ueber`; ein Tarifblatt mit Phasentabelle bleibt vor der
Bündelphase; nennt o2 „ab dem 25. Monat: 29,99 €“, gilt der alte Preis nur bis
Monat 24. Fixtures: `congstar_produkt_iphone17_20260929.html.gz`,
`o2_vertiefung_iphone17pro.json.gz`, `o2_ratenplan_galaxy_s26_20261007.json.gz`
(Herkunft in `_herkunft.json`), Tarifblätter aus dem Schnappschuss 2026-10-03.
"""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

from bestand_pfad import ZUSTAND

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import congstar, o2
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report import html
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import kosten_ueber

FIX = Path(__file__).parent / "fixtures" / "geraete"
URL = "https://www.congstar.de/geraete/apple/apple-iphone-17/"
SKU = "apple-iphone-17-256gb-weiss"
NICHT_BELEGT = "ab Monat 25: nicht belegt"
LUECKENSATZ = "weist die Quelle nicht aus"
TABELLE = [
    {"von_monat": 1, "bis_monat": 24, "betrag": 15.0},
    {"von_monat": 25, "bis_monat": None, "betrag": 20.0},
]
O2_ANGEBOT = "privatkunden-apple-iphone-17-pro-512gb-silber-36xhigh"


def _json_gz(name: str):
    with gzip.open(FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _xs(raten: int):
    """Allnet Flat XS 256 GB wie im Tageslauf, mit dem Tarifblatt des Bestands."""
    with gzip.open(FIX / "congstar_produkt_iphone17_20260929.html.gz", "rt") as fh:
        saetze = congstar.lies_buendel(fh.read(), URL)
    [roh] = [
        s
        for s in saetze
        if (s["speicher_gb"], s["tarif_name"], s["laufzeit_monate"])
        == (256, "Allnet Flat XS", raten)
    ]
    bestand = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")
    congstar.ergaenze_pib_slug(bestand)
    [b] = aus_rohsaetzen(
        [{**roh, "sku_id": SKU, "anbieter": "congstar"}], bestand, "2026-09-29"
    ).buendel
    return b, bestand.je_id_aktuell[b.tarif_id]


def _zeile(raten: int) -> tuple[dict, str]:
    b, blatt = _xs(raten)
    karten.tarif_anreichern(b, blatt)
    k = karten._karte(b, blatt, None, None, {}, zustand="neu", heute="2026-09-29")
    vorlage = html._env().from_string(
        '{% from "_geraete_buendel.html.j2" import buendelzeile %}{{ buendelzeile(k) }}'
    )
    return k, " ".join(vorlage.render(k=k).split()).replace("&nbsp;", " ")


def test_gegenprobe_24_raten_die_luecke_ab_monat_25_ist_wahr():
    k, zeile = _zeile(24)
    assert (k["laufzeit"], k["nach_bindung"]) == (24, None)
    assert NICHT_BELEGT in zeile


def test_36_raten_zeile_rechnet_monat_25_bis_36_und_nennt_ihn_nicht_unbelegt():
    k, zeile = _zeile(36)
    assert (k["laufzeit"], k["gesamt"], k["nach_bindung"]) == (36, 1585.0, 15.0)
    assert "<span>Tarif über 36 Monate</span><em>540,00" in zeile
    assert [s for s in (NICHT_BELEGT, LUECKENSATZ) if s in zeile] == []


def _tarif_ueber_36(b) -> float | None:
    k = kosten_ueber(b, 36)
    return None if k.luecken else k.posten.get("Tarif über 36 Monate")


def test_gegenprobe_blatt_nur_mit_grundpreis_die_buendelphase_traegt_36_monate():
    b, blatt = _xs(36)
    karten.tarif_anreichern(
        b, {**blatt, "preisphasen": [{**TABELLE[0], "bis_monat": None}]}
    )
    assert _tarif_ueber_36(b) == 36 * 15.0


def test_blatt_nennt_ab_monat_25_zwanzig_euro_dann_nicht_36_mal_fuenfzehn():
    b, blatt = _xs(36)
    karten.tarif_anreichern(b, {**blatt, "preisphasen": TABELLE})
    assert [(p.von_monat, p.bis_monat, p.betrag) for p in b.tarif_phasen] == [
        (1, 24, 15.0),
        (25, None, 20.0),
    ]
    assert _tarif_ueber_36(b) == 24 * 15.0 + 12 * 20.0


def _o2_saetze(mit_zeile_ab_25: bool) -> list[dict]:
    """Die 36-Raten-Antwort (512 GB) vom 29.09. mit dem Ratenplan-Hinweis vom 07.10.;
    auf Wunsch mit der Zeile „ab dem 25. Monat“ der special-online-Antwort."""
    mitschnitt = _json_gz("o2_vertiefung_iphone17pro.json.gz")
    antworten = {
        u: o2.lies_konfiguration(t) for u, t in mitschnitt["antworten"].items()
    }
    [(url, pv)] = [
        (u, copy.deepcopy(a))
        for u, a in antworten.items()
        if a["hardware"]["offerName"] == O2_ANGEBOT
    ]
    galaxy = _json_gz("o2_ratenplan_galaxy_s26_20261007.json.gz")
    pv["hardware"]["contents"] = next(iter(galaxy["antworten"].values()))["hardware"][
        "contents"
    ]
    if mit_zeile_ab_25:
        [zeile] = [
            e
            for a in antworten.values()
            for e in a["priceSummary"]["recurringChargesListEntries"]
            if str(e.get("description")).startswith("ab dem 25. Monat")
        ]
        pv["priceSummary"]["recurringChargesListEntries"].append(zeile)
    basis = o2.lies_buendel(json.dumps(mitschnitt["katalog"]))[0]
    return o2.saetze_aus_konfiguration(pv, basis, None, url, {})


def _spannen(satz: dict) -> list[tuple]:
    return [(p["von_monat"], p["bis_monat"], p["betrag"]) for p in satz["tarif_phasen"]]


def test_gegenprobe_o2_ohne_zeile_ab_25_traegt_der_tarif_die_phase_1_bis_36():
    [satz] = _o2_saetze(mit_zeile_ab_25=False)
    assert _spannen(satz) == [(1, 36, 19.99)]


def test_o2_nennt_ab_monat_25_einen_anderen_preis_dann_keine_phase_bis_36_zum_alten():
    [satz] = _o2_saetze(mit_zeile_ab_25=True)
    assert satz["tarif_monatlich"] == 19.99
    assert _spannen(satz) == [(1, 24, 19.99), (25, 36, 29.99)]
    assert "ab dem 25. Monat: 29,99 €" in satz["tarif_phasen"][1]["beleg"]
