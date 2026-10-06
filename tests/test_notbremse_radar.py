"""Notbremse im Wettbewerbsradar: Kernzahl und Wettbewerberzeilen nur aus Karten,
die zählen.

Eine Karte mit ``zaehlt`` False (Schätzung: 1&1 aus dem Tarifraster, o2 aus
Tarifsumme minus Geräterate; oder eine abgelaufene Aktion im Preis) stellt im Radar
weder die Kernzahl noch eine Abweichung noch einen Betrag einer Wettbewerberzeile.
Trägt ein Wettbewerber nur solche Karten, steht er als benannte Lücke da. Gemessen
am Bestand vom 2026-10-03: die Seite über ``render_site``, die Daten über die
öffentlichen Eingänge ``geraete_view.aufbereiten`` und ``geraete_radar.radar``.
"""

from __future__ import annotations

import html
import re
import shutil

import pytest
from bestand_pfad import ZUSTAND, abbild, lese_wurzel

from telco_radar.config import load_config
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_notbremse, geraete_radar, geraete_view
from telco_radar.report.html import render_site

HEUTE = "2026-10-02"
"""Bezugstag der Seite: ``render_site`` nimmt das Datum des jüngsten Berichts."""
MELDUNG = "Kernzahl: erwartet ohne Schätzung"
LEITZAHL = re.compile(
    r'<div class="gr-leit gr-leit--radar"><b class="gr-leit-zahl">(?P<zahl>[^<]*)'
    r'</b><span class="gr-leit-label">(?P<label>[^<]*)</span>'
)


@pytest.fixture(scope="module")
def bestand(tmp_path_factory):
    zustand = tmp_path_factory.mktemp("notbremse-radar") / "state"
    shutil.copytree(ZUSTAND, zustand)
    wurzel = lese_wurzel()
    geraete = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE
    )
    sicht = geraete_radar.radar(
        geraete["tco"], geraete["vergleich"]["ohne_vertrag"], geraete["quellenlage"]
    )
    return sicht, {m["id"]: m["karten"] for m in geraete["tco"]["modelle"]}


@pytest.fixture(scope="module")
def seite(tmp_path_factory):
    ziel = tmp_path_factory.mktemp("notbremse-seite")
    render_site(ziel / "site", abbild(ziel), load_config(ziel))
    return (ziel / "site" / "geraete.html").read_text(encoding="utf-8")


def _aus_nicht_zaehlender(karten: list, anbieter: str, betrag, zeile=None) -> bool:
    """Stammt der Betrag nur aus Karten mit ``zaehlt`` False? Mit ``zeile`` müssen
    auch Tarif und Beleg der Karte zur Radarzeile passen."""
    treffer = [
        k
        for k in karten
        if k["anbieter"] == anbieter
        and k.get("gesamt") == betrag
        and (zeile is None or k.get("tarif", "") == zeile["tarif"])
        and (
            zeile is None
            or not zeile.get("quelle_url")
            or k.get("quelle_url", "") == zeile["quelle_url"]
        )
    ]
    return bool(treffer) and all(k.get("zaehlt") is False for k in treffer)


def _herkunft_falsch(karten: list, zeile: dict) -> bool:
    if zeile["gesamt"] is not None and _aus_nicht_zaehlender(
        karten, zeile["anbieter"], zeile["gesamt"], zeile
    ):
        return True
    vf = zeile.get("vf_gesamt")
    return vf is not None and _aus_nicht_zaehlender(karten, "Vodafone", vf)


def test_kernzahl_der_seite_ohne_schaetzung(bestand, seite):
    sicht, karten = bestand
    spitze = sicht["modelliste"]["zeilen"][0]
    leit = LEITZAHL.search(seite)
    assert leit is not None, "Kernzahl: die Seite zeigt keine Leitzahl des Radars"
    label = html.unescape(leit["label"])
    assert leit["zahl"] == f"{spitze['euro_text']} €", (
        f"Kernzahl: Seite {leit['zahl']} gegen Radar {spitze['euro_text']} €"
    )
    assert spitze["titel"] in label and spitze["anbieter"] in label, label
    assert not _herkunft_falsch(karten[spitze["id"]], spitze), (
        f"{MELDUNG} – {spitze['titel']}: {spitze['anbieter']} {spitze['tarif']} "
        f"{spitze['gesamt']} gegen Vodafone {spitze['vf_gesamt']} "
        f"({leit['zahl']}) stammt aus einer Karte, die nicht zählt"
    )


def test_wettbewerberzeilen_nur_aus_zaehlenden_karten(bestand):
    sicht, karten = bestand
    falsch = [
        f"{g['id']} {z['anbieter']} {z['tarif']} {z['gesamt']} ({z['status']})"
        for g in sicht["gruppen"]
        for z in g["zeilen"]
        if _herkunft_falsch(karten[g["id"]], z)
    ]
    assert not falsch, (
        f"Wettbewerberzeile: erwartet ohne Schätzung – {len(falsch)} Zeilen aus "
        f"Karten, die nicht zählen (z. B. {falsch[:3]})"
    )


def test_gemessene_karten_liefern_weiter_kernzahl_und_abweichung(bestand):
    """Gegenprobe: die Notbremse leert den Radar nicht."""
    sicht, _ = bestand
    assert sicht["modelliste"]["zeilen"][0]["prozent"] is not None, (
        "gemessene Karten liefern keine Kernzahl mehr"
    )
    vergleichbar = {
        z["anbieter"]
        for g in sicht["gruppen"]
        for z in g["zeilen"]
        if z["prozent"] is not None
    }
    assert {"o2", "congstar"} <= vergleichbar, (
        f"gemessene Karten verlieren ihre Abweichung, verglichen: {vergleichbar}"
    )


def test_wettbewerber_ohne_zaehlende_karte_ist_benannte_luecke(bestand):
    """Trägt ein Wettbewerber nur Karten, die nicht zählen, nennt seine Zeile den
    Zustand der Notbremse und keinen Betrag (keine 0, kein „nicht erhoben“)."""
    sicht, karten = bestand
    saetze = {
        geraete_notbremse.SATZ_SCHAETZUNG,
        geraete_notbremse.SATZ_AKTION_ABGELAUFEN,
    }
    erwartet, ohne_luecke = [], []
    for g in sicht["gruppen"]:
        echte = [
            k
            for k in karten[g["id"]]
            if k.get("belastbar")
            and not k.get("naeherung")
            and k.get("gesamt") is not None
            and k["anbieter"] in geraete_radar.ALLE_WETTBEWERBER
        ]
        for anbieter in sorted({k["anbieter"] for k in echte}):
            if any(k["zaehlt"] for k in echte if k["anbieter"] == anbieter):
                continue
            erwartet.append(anbieter)
            zeilen = [z for z in g["zeilen"] if z["anbieter"] == anbieter]
            if not any(
                z["prozent"] is None and z["gesamt"] is None and z["grund"] in saetze
                for z in zeilen
            ):
                ohne_luecke.append(f"{g['id']} {anbieter}")
    assert erwartet, "Bestand ohne Wettbewerber, dessen Karten alle nicht zählen"
    assert not ohne_luecke, (
        f"Lücke: erwartet benannter Zustand statt Zahl – {len(ohne_luecke)} "
        f"Wettbewerber (z. B. {ohne_luecke[:3]})"
    )
