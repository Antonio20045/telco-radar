"""Notbremse im Antwortsatz: „führt nur Vodafone“ nur ohne Wettbewerber im Band.

Zählt im Band nur Vodafone, stehen dort aber Wettbewerber mit Schätzung oder
abgelaufener Aktion, nimmt die Notbremse deren Zahl aus dem Vergleich, nicht ihr
Angebot vom Markt. Der Satz sagt dann „steht nur Vodafone im Vergleich“ und nennt
die übrigen benannt („Nicht im Vergleich: o2 (berechnet)“), statt Exklusivität
vorzutäuschen (harte Regel 6). Fund des Prüfers am Bestand vom 2026-10-03: 53 Paare.

Eigenes Orakel aus den Rohsätzen (``herleitung``, eingerechnete Aktion mit
``gueltig_bis`` vor dem Bezugstag); fester Bezugstag, nie das heutige Datum.
"""

from __future__ import annotations

import html
import json
import re
import shutil

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view

HEUTE = "2026-10-03"
NUR_VODAFONE = "führt nur Vodafone"


@pytest.fixture(scope="module")
def bestand(tmp_path_factory):
    zustand = tmp_path_factory.mktemp("notbremse-antwort") / "state"
    shutil.copytree(ZUSTAND, zustand)
    wurzel = lese_wurzel()
    geraete = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE
    )
    roh = json.loads((zustand / "geraete_tco.json").read_text(encoding="utf-8"))
    return geraete, roh["buendel"]


def _zaehlt_nicht(roh: dict) -> str:
    """„Schätzung“, „Aktion abgelaufen“ oder leer (zählt)."""
    if str(roh.get("herleitung") or "").strip():
        return "berechnet"
    if any(
        a.get("eingerechnet") and a.get("gueltig_bis") and a["gueltig_bis"] < HEUTE
        for a in roh.get("aktionen") or []
    ):
        return "Aktion abgelaufen"
    return ""


def _andere_gesperrt(
    karten: list, band: str, roh: list, laufzeit: int
) -> dict[str, set[str]]:
    """Wettbewerber mit frischem, belastbarem Bündel im Band, das nicht zählt,
    je Anbieter mit ihren Gründen - in der Ratenlaufzeit des Paares
    (Datenkonzept Geräte Schritt 2: ein Paar ist eine Laufzeit-Ansicht)."""
    grund = {
        (
            r.get("anbieter"),
            r.get("sku_id"),
            r.get("tarif_id"),
            r.get("laufzeit_monate"),
        ): g
        for r in roh
        if (g := _zaehlt_nicht(r))
    }
    andere: dict[str, set[str]] = {}
    for k in karten:
        schluessel = (
            k["anbieter"],
            k.get("sku_id"),
            k.get("tarif_id"),
            k.get("raten_laufzeit"),
        )
        if (
            k.get("band") == band
            and k.get("raten_laufzeit") == laufzeit
            and k["anbieter"] != "Vodafone"
            and k.get("sku_id")
            and k.get("belastbar")
            and k.get("vergleichbar")
            and k.get("frisch", True)
            and schluessel in grund
        ):
            andere.setdefault(k["anbieter"], set()).add(grund[schluessel])
    return andere


def _satz(paar: dict) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", paar["antwort_html"]))


def _nur_vodafone_zaehlt(geraete, roh):
    """(Paar, gesperrte Wettbewerber) je Paar, dessen einzige Zeile Vodafone ist."""
    karten = {m["id"]: m["karten"] for m in geraete["tco"]["modelle"]}
    for p in geraete["zeitreihe"]["paare"]:
        satz = _satz(p)
        if NUR_VODAFONE in satz or "steht nur Vodafone im Vergleich" in satz:
            yield (
                p,
                _andere_gesperrt(karten[p["modell"]], p["band"], roh, p["laufzeit"]),
            )


def test_fuehrt_nur_vodafone_nur_wenn_kein_anderer_anbieter_im_band(bestand):
    falsch = [
        f"{p['modell']}/{p['band']}: „{_satz(p)}“ – im Band auch {sorted(andere)}"
        for p, andere in _nur_vodafone_zaehlt(*bestand)
        if andere and NUR_VODAFONE in _satz(p)
    ]
    assert not falsch, (
        f"Antwortsatz täuscht Exklusivität vor in {len(falsch)} Paaren, "
        f"z. B. {falsch[:2]}"
    )


def test_satz_nennt_die_gesperrten_wettbewerber_mit_grund(bestand):
    faelle, ohne_namen = 0, []
    for p, andere in _nur_vodafone_zaehlt(*bestand):
        if not andere:
            continue
        faelle += 1
        satz = _satz(p)
        teil = (
            satz.split("Nicht im Vergleich: ", 1)[-1]
            if "Nicht im Vergleich: " in satz
            else ""
        )
        fehlt = [
            f"{a} ({g})"
            for a, gruende in andere.items()
            for g in gruende
            if f"{a} ({g})" not in teil
        ]
        if "steht nur Vodafone im Vergleich" not in satz or fehlt:
            ohne_namen.append(f"{p['modell']}/{p['band']}: „{satz}“ – fehlt {fehlt}")
    assert faelle, "Fall fehlt: kein Band, in dem neben Vodafone nur Schätzungen stehen"
    assert not ohne_namen, (
        f"{len(ohne_namen)} von {faelle} Sätzen nennen die gesperrten Wettbewerber "
        f"nicht, z. B. {ohne_namen[:2]}"
    )


def test_gegenprobe_nur_vodafone_ohne_andere_bleibt(bestand):
    echt = [
        p
        for p, andere in _nur_vodafone_zaehlt(*bestand)
        if not andere and NUR_VODAFONE in _satz(p)
    ]
    assert echt, "Gegenprobe: ein Band, das wirklich nur Vodafone führt, fehlt"
