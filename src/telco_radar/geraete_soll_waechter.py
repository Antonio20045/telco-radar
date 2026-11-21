"""Wächter der Soll/Ist-Zählung: rot bei unbenannter Lücke oder fehlender Zählung.

Aufruf (Schritt „Soll/Ist pruefen“ in ``.github/workflows/geraete.yml``, vor
„Buendelabdeckung pruefen“)::

    PYTHONPATH=src python -m telco_radar.geraete_soll_waechter --root . \
        --datum "${{ steps.heute.outputs.datum }}"

Gelesen wird genau die Lauf-Datei des Messtags (``geraete_lauf``). Der Messtag kommt
im Workflow aus dem Schritt „Heute schon gemessen?“ (``--datum``); ohne ``--datum``
(lokal) ist er ``updated`` der Bündeldatei. Rot (Exit 1), wenn

* es für den Messtag keine Lauf-Datei gibt, sie unlesbar ist oder ein anderes Datum
  trägt (eine Datei vom Vortag macht nie grün),
* die Zählung als Ganzes gescheitert ist (``vollstaendigkeit.fehler``),
* ein erwarteter Anbieter (``geraete_vollstaendigkeit.ERWARTET``) keine Zeile hat,
* eine Ebene weder ein Soll noch einen benannten Grund trägt,
* ein Anbieter eine unbenannte Lücke hat,
* ein unabhängiges Soll (``gleiche_quelle_wie_sammler`` falsch) ein erfasstes Modell
  nicht kennt (``nicht_im_soll``): dann zählt die Liste nicht, was angeboten wird.

Stufe 2 (``geraete_angebot.einhaengen``): eine Lücke der Angebotszählung ohne Grund
ist ``unbenannt`` und rot wie oben; eine fehlende Zählung des Tages ist benannt
(„Angebot heute nicht gezählt: …“) und bleibt grün.

Ein benannter Ausfall (Soll nicht zählbar mit Grund, Lücke mit Grund) bleibt grün und
steht in der Ausgabe. Rein lesend, ohne Netz.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import geraete_lauf
from .geraete_vollstaendigkeit import ERWARTET, UNBENANNT


def _zeile(zeile: dict) -> list[str]:
    name = zeile.get("name", "?")
    befunde = []
    for ebene, werte in (zeile.get("ebenen") or {}).items():
        if werte.get("soll") is None and not werte.get("soll_grund"):
            befunde.append(f"{name}: Soll {ebene} fehlt ohne benannten Grund")
    unbenannt = [
        luecke["schluessel"]
        for werte in (zeile.get("ebenen") or {}).values()
        for luecke in werte.get("luecken") or ()
        if luecke.get("grund") == UNBENANNT or not luecke.get("benannt")
    ]
    if zeile.get("unbenannt") or unbenannt:
        zahl = max(int(zeile.get("unbenannt") or 0), len(unbenannt))
        befunde.append(f"{name}: {zahl} Lücken ohne Grund: {', '.join(unbenannt[:12])}")
    quelle = zeile.get("soll_quelle") or {}
    extra = ((zeile.get("ebenen") or {}).get("modelle") or {}).get("nicht_im_soll_zahl")
    if quelle.get("gleiche_quelle_wie_sammler") is False and extra:
        befunde.append(f"{name}: {extra} erfasste Modelle fehlen im unabhängigen Soll")
    return befunde


def pruefe(lauf: dict | None, datum: str) -> list[str]:
    """Die roten Befunde zur Lauf-Datei ``lauf`` des Messtags ``datum``."""
    if lauf is None:
        return [f"keine Lauf-Datei für den Messtag {datum}"]
    if lauf.get("datum") != datum:
        return [f"Lauf-Datei trägt den {lauf.get('datum')}, Messtag ist {datum}"]
    voll = lauf.get("vollstaendigkeit")
    if not isinstance(voll, dict):
        return [f"Lauf-Datei {datum} ohne Vollständigkeit"]
    if voll.get("fehler"):
        return [str(voll["fehler"])]
    zeilen = {z.get("name"): z for z in voll.get("anbieter") or ()}
    befunde = [f"{n}: keine Zählung" for n in ERWARTET if n not in zeilen]
    for zeile in zeilen.values():
        befunde += _zeile(zeile)
    return befunde


def uebersicht(lauf: dict | None) -> list[str]:
    """Je Anbieter eine Zeile für das Log (Modellebene)."""
    zeilen = []
    for z in ((lauf or {}).get("vollstaendigkeit") or {}).get("anbieter") or ():
        m, k = z["ebenen"]["modelle"], z["ebenen"]["kombinationen"]
        if k["soll"] is not None:
            zeilen.append(
                f"{z['name']}: {k['erfasst']} von {k['soll']} Angeboten erfasst, "
                f"{k['luecken_zahl']} Lücken, {k['nicht_im_soll_zahl']} nicht im Soll, "
                f"{(z.get('angebot') or {}).get('nicht_gezaehlt_zahl')} Seiten "
                "nicht gezählt"
            )
        elif m["soll"] is None:
            zeilen.append(
                f"{z['name']}: Soll nicht zählbar "
                f"({m['soll_grund']}; {k['soll_grund']})"
            )
        else:
            zeilen.append(
                f"{z['name']}: {m['erfasst']} von {m['soll']} Modellen erfasst, "
                f"{m['luecken_zahl']} Lücken, {m['nicht_im_soll_zahl']} nicht im Soll"
            )
    return zeilen


def messtag(root: Path) -> str:
    """``updated`` der Bündeldatei, "" wenn sie fehlt oder unlesbar ist."""
    try:
        daten = json.loads(
            (root / "data" / "state" / "geraete_tco.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return ""
    return str(daten.get("updated") or "") if isinstance(daten, dict) else ""


def main(argv: list[str] | None = None) -> int:
    """Liest, prüft, gibt aus; 1 bei rotem Befund."""
    p = argparse.ArgumentParser(description="Soll/Ist-Waechter der Geraeteseite")
    p.add_argument("--root", default=".")
    p.add_argument("--datum", default="")
    args = p.parse_args(argv)
    root = Path(args.root)
    datum = args.datum if args.datum else messtag(root)
    try:
        lauf = geraete_lauf.lies(root / "data" / "state", datum) if datum else None
    except geraete_lauf.LaufDateiFehler as fehler:
        befunde = [f"Lauf-Datei nicht lesbar: {fehler}"]
        lauf = None
    else:
        befunde = pruefe(lauf, datum if datum else "unbekannt")
    for zeile in uebersicht(lauf):
        print(zeile)
    for befund in befunde:
        print(f"::error::Soll/Ist: {befund}")
    return 1 if befunde else 0


if __name__ == "__main__":
    sys.exit(main())
