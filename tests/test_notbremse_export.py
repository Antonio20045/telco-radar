"""Notbremse im Bündel-Export: ``geraete-tco.csv`` trägt dieselbe Marke wie die Zeile.

Eine Schätzung oder ein Satz mit abgelaufener Aktion steht in der Spalte „Status“
mit „Schätzung“ bzw. „Aktion abgelaufen“, eine gemessene Zeile mit leerer Zelle -
sonst sortiert der Leser die Datei nach Kosten und nimmt die Schätzung als
günstigstes Angebot (Clean Code 1: Seite und Export lesen dasselbe Feld).

Gerendert aus dem Bestand vom 2026-10-03; eigenes Orakel aus den Rohsätzen
(``herleitung``, eingerechnete Aktion mit ``gueltig_bis`` vor dem Bezugstag).
"""

from __future__ import annotations

import csv
import io
import json

import pytest
from bestand_pfad import abbild

from telco_radar.config import load_config
from telco_radar.report.html import render_site

STATUS = "Status"


@pytest.fixture(scope="module")
def export(tmp_path_factory):
    wurzel = tmp_path_factory.mktemp("notbremse-export")
    berichte = abbild(wurzel)
    render_site(wurzel / "site", berichte, load_config(wurzel))
    text = (wurzel / "site" / "exporte" / "geraete-tco.csv").read_text(
        encoding="utf-8-sig"
    )
    zustand = wurzel / "data" / "state" / "geraete_tco.json"
    roh = json.loads(zustand.read_text(encoding="utf-8"))
    heute = max(
        roh["updated"],
        json.loads(sorted(berichte.glob("*.json"))[-1].read_text())["date"],
    )
    return list(csv.DictReader(io.StringIO(text), delimiter=";")), roh, heute


def _grund(roh: dict, heute: str) -> str:
    if str(roh.get("herleitung") or "").strip():
        return "nicht direkt genannt"
    for a in roh.get("aktionen") or []:
        ende = str(a.get("gueltig_bis") or "").strip()
        if a.get("eingerechnet") and ende and ende < heute:
            return "Aktion abgelaufen"
    return ""


def _gruende_je_zeile(export) -> list[tuple[dict, set[str]]]:
    zeilen, roh, heute = export
    gruende: dict[tuple, set[str]] = {}
    for b in roh["buendel"]:
        schluessel = (
            b["sku_id"],
            b["anbieter"],
            b["tarif_name"],
            str(b["laufzeit_monate"]),
        )
        gruende.setdefault(schluessel, set()).add(_grund(b, heute))
    return [
        (
            z,
            gruende.get(
                (z["SKU-ID"], z["Anbieter"], z["Tarif"], z["Laufzeit Monate"]), set()
            ),
        )
        for z in zeilen
        if z["Art"] == "Bündel"
    ]


def test_der_export_hat_eine_statusspalte(export):
    zeilen, _, _ = export
    assert zeilen and STATUS in zeilen[0], sorted(zeilen[0]) if zeilen else zeilen


@pytest.mark.parametrize("grund", ["nicht direkt genannt", "Aktion abgelaufen"])
def test_buendel_das_nicht_zaehlt_ist_markiert(export, grund):
    betroffen = [z for z, g in _gruende_je_zeile(export) if g == {grund}]
    assert betroffen, f"Fall fehlt: keine Zeile mit {grund} im Export"
    unmarkiert = [
        (z["Anbieter"], z["Tarif"], z.get(STATUS))
        for z in betroffen
        if z.get(STATUS) != grund
    ]
    assert not unmarkiert, (
        f"Bündel-Export: {len(unmarkiert)} von {len(betroffen)} Zeilen ohne Marke "
        f"„{grund}“, z. B. {unmarkiert[:3]}"
    )


def test_gegenprobe_gemessene_buendel_und_sim_only_bleiben_leer(export):
    zeilen, _, _ = export
    gemessen = [z for z, g in _gruende_je_zeile(export) if g == {""}]
    assert gemessen, "Gegenprobe: gemessene Bündel fehlen im Export"
    sim = [z for z in zeilen if z["Art"] == "SIM-only"]
    markiert = [z for z in gemessen + sim if z.get(STATUS)]
    assert not markiert, (
        f"{len(markiert)} gemessene oder SIM-only-Zeilen tragen eine Marke, "
        f"z. B. {[(z['Anbieter'], z['Tarif'], z[STATUS]) for z in markiert[:3]]}"
    )
