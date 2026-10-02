"""Abdeckung der Bündel: welcher Anbieter liefert welches Gerät in welchem
Tarif, und was ist seit dem letzten Messtag weggefallen oder gesprungen.

Der ältere Wächter (`GeraeteDB.ausfall_alarme`) prüft Listungen und schlägt
nur an, wenn ein Anbieter GESTERN noch lieferte. Die Telekom lieferte seit
dem 15.09.2026 kein Bündel mehr, und kein Lauf wurde rot: wer schon
ausgefallen ist, fällt diesem Vergleich nie wieder auf. Diese Prüfung misst
deshalb gegen eine feste Pflichtliste (`config/geraete_abdeckung.yaml`),
nicht gegen den Vortag, und sie misst die Bündel, aus denen die Leitzahl
„Kosten über 24 Monate“ entsteht.

Vier Befundarten, jede für sich rot:

* ``anbieter_leer``     ein Pflichtanbieter hat am Messtag kein Bündel
* ``modell_fehlt``      ein Pflichtmodell fehlt bei einem Pflichtanbieter,
                        ohne dass eine belegte Lücke in der Config steht
* ``kombis_weg``        gegenüber dem vorigen Messtag fehlen mehr als
                        `KOMBI_VERLUST_ANTEIL` der Kombinationen
* ``preissprung``       die Leitzahl einer Kombination springt um mehr als
                        `PREISSPRUNG_ANTEIL` gegenüber dem vorigen Messtag

Eine belegte Lücke (Anbieter führt das Gerät nicht, Anbieter nicht
erreichbar) ist kein Befund, sie steht aber mit ihrem Grund in der Matrix.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from ..geraete_model import normalisiere

# Anteil der Kombinationen des vorigen Messtags, der fehlen darf, bevor der
# Lauf rot wird. Ein Anbieter nimmt jede Woche einzelne Farben aus dem
# Programm; ein Zehntel auf einen Schlag ist ein Erfassungsfehler.
KOMBI_VERLUST_ANTEIL = 0.10
# Unter so vielen verlorenen Kombinationen schlägt der Anteil nicht an: bei
# einem Anbieter mit zwölf Bündeln wären zwei ausgelaufene Farben sonst rot.
KOMBI_VERLUST_MINDEST = 5
# Relative Änderung der Leitzahl, ab der ein Sprung gemeldet wird. Eine
# Aktion senkt die Kosten über 24 Monate selten um mehr als ein Viertel;
# ein Sprung darüber ist zuerst ein Verdacht auf ein geändertes Feld.
PREISSPRUNG_ANTEIL = 0.25
# So viele Beispiele je Befund stehen im Bericht; die Zahl davor ist immer
# vollständig.
BEISPIELE = 8

_SKU_MUSTER = re.compile(r"^(?P<modell>.+?)-(?P<speicher>\d+gb|ohne-speicher)-")


@dataclass
class Befund:
    art: str
    anbieter: str
    text: str


@dataclass
class Abdeckung:
    messtag: Optional[str]
    vortag: Optional[str]
    # (modell, anbieter) -> {"speicher": set, "tarife": set, "laufzeiten": set}
    matrix: dict = field(default_factory=dict)
    anbieter_zahl: dict = field(default_factory=dict)
    luecken: dict = field(default_factory=dict)
    befunde: list = field(default_factory=list)

    @property
    def rot(self) -> bool:
        return bool(self.befunde)


def modell_und_speicher(sku_id: str) -> tuple[Optional[str], Optional[str]]:
    """Katalogmodell und Speicherstufe aus der SKU-ID
    (`geraete_model.sku_id`: Gerät-Speicher-Farbe[-Zustand])."""
    treffer = _SKU_MUSTER.match(sku_id or "")
    if not treffer:
        return None, None
    return treffer.group("modell"), treffer.group("speicher")


def lade_pflicht(pfad: Path) -> dict:
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    luecken = {}
    for eintrag in daten.get("belegte_luecken") or []:
        grund = str(eintrag.get("grund") or "").strip()
        if not grund:
            raise ValueError(f"belegte Lücke ohne Grund: {eintrag}")
        modelle = eintrag.get("modelle") or ["*"]
        for modell in modelle:
            luecken[(eintrag["anbieter"], modell)] = grund
    return {
        "anbieter": list(daten.get("pflicht_anbieter") or []),
        "modelle": list(daten.get("pflicht_modelle") or []),
        "luecken": luecken,
    }


def _anbieter_aus_id(buendel_id: str, namen: dict) -> Optional[str]:
    teile = (buendel_id or "").split("--")
    return namen.get(teile[1]) if len(teile) > 1 else None


def pruefe(tco: dict, historie: list[dict], pflicht: dict) -> Abdeckung:
    """Rechnet Matrix und Befunde. Rein: liest nur, was übergeben wird."""
    messtag = tco.get("updated")
    ergebnis = Abdeckung(messtag=messtag, vortag=None, luecken=dict(pflicht["luecken"]))
    heute = [
        b
        for b in tco.get("buendel") or []
        if b.get("last_verified") == messtag and (b.get("zustand") or "neu") == "neu"
    ]

    for b in heute:
        modell, speicher = modell_und_speicher(b.get("sku_id"))
        if modell is None:
            continue
        zelle = ergebnis.matrix.setdefault(
            (modell, b["anbieter"]),
            {"speicher": set(), "tarife": set(), "laufzeiten": set()},
        )
        zelle["speicher"].add(speicher)
        zelle["tarife"].add(b.get("tarif_name"))
        zelle["laufzeiten"].add(b.get("laufzeit_monate"))
        ergebnis.anbieter_zahl[b["anbieter"]] = (
            ergebnis.anbieter_zahl.get(b["anbieter"], 0) + 1
        )

    def belegt(anbieter: str, modell: str) -> bool:
        return (anbieter, modell) in ergebnis.luecken or (
            anbieter,
            "*",
        ) in ergebnis.luecken

    for anbieter in pflicht["anbieter"]:
        if ergebnis.anbieter_zahl.get(anbieter):
            continue
        if belegt(anbieter, "*"):
            continue
        ergebnis.befunde.append(
            Befund(
                "anbieter_leer",
                anbieter,
                f"{anbieter}: kein einziges Bündel am Messtag {messtag}",
            )
        )

    for anbieter in pflicht["anbieter"]:
        if not ergebnis.anbieter_zahl.get(anbieter):
            continue
        fehlend = [
            m
            for m in pflicht["modelle"]
            if (m, anbieter) not in ergebnis.matrix and not belegt(anbieter, m)
        ]
        if fehlend:
            ergebnis.befunde.append(
                Befund(
                    "modell_fehlt",
                    anbieter,
                    f"{anbieter}: {len(fehlend)} Pflichtmodelle ohne Bündel "
                    f"und ohne belegte Lücke: {', '.join(fehlend[:BEISPIELE])}",
                )
            )

    _vergleiche_vortag(ergebnis, historie, pflicht["anbieter"], messtag)
    return ergebnis


def _vergleiche_vortag(
    ergebnis: Abdeckung, historie: list[dict], anbieter_liste: list[str], messtag: str
) -> None:
    namen = {normalisiere(a): a for a in anbieter_liste}
    je_tag: dict = defaultdict(lambda: defaultdict(dict))
    for zeile in historie:
        anbieter = _anbieter_aus_id(zeile.get("id"), namen)
        if anbieter is None or zeile.get("zustand", "neu") not in ("", "neu"):
            continue
        je_tag[anbieter][zeile.get("datum")][zeile["id"]] = zeile.get("gesamt")

    vortage = set()
    for anbieter, tage in je_tag.items():
        if messtag not in tage:
            continue
        frueher = sorted(t for t in tage if t and t < messtag)
        if not frueher:
            continue
        vortag = frueher[-1]
        vortage.add(vortag)
        alt, neu = tage[vortag], tage[messtag]
        weg = sorted(set(alt) - set(neu))
        if len(weg) >= KOMBI_VERLUST_MINDEST and len(weg) > KOMBI_VERLUST_ANTEIL * len(
            alt
        ):
            ergebnis.befunde.append(
                Befund(
                    "kombis_weg",
                    anbieter,
                    f"{anbieter}: {len(weg)} von {len(alt)} Kombinationen vom "
                    f"{vortag} fehlen am {messtag}, z. B. "
                    f"{', '.join(weg[:BEISPIELE])}",
                )
            )
        spruenge = []
        for bid in sorted(set(alt) & set(neu)):
            a, n = alt[bid], neu[bid]
            if not a or n is None:
                continue
            if abs(n - a) / a > PREISSPRUNG_ANTEIL:
                spruenge.append(f"{bid} {a:.2f} → {n:.2f} €")
        if spruenge:
            ergebnis.befunde.append(
                Befund(
                    "preissprung",
                    anbieter,
                    f"{anbieter}: {len(spruenge)} Leitzahlen springen um mehr "
                    f"als {PREISSPRUNG_ANTEIL:.0%} gegenüber {vortag}: "
                    f"{'; '.join(spruenge[:BEISPIELE])}",
                )
            )
    ergebnis.vortag = max(vortage) if vortage else None


def lade_und_pruefe(root: Path) -> Abdeckung:
    zustand = root / "data" / "state"
    tco = json.loads((zustand / "geraete_tco.json").read_text("utf-8"))
    historie = []
    pfad = zustand / "geraete_tco_historie.jsonl"
    if pfad.exists():
        with pfad.open(encoding="utf-8") as f:
            historie = [json.loads(z) for z in f if z.strip()]
    pflicht = lade_pflicht(root / "config" / "geraete_abdeckung.yaml")
    return pruefe(tco, historie, pflicht)


def _zelle_text(zelle: Optional[dict]) -> str:
    if not zelle:
        return ""
    laufzeiten = "/".join(
        str(z) for z in sorted(z for z in zelle["laufzeiten"] if z is not None)
    )
    return (
        f"{len(zelle['speicher'])} Sp · {len(zelle['tarife'])} Tarife · "
        f"{laufzeiten or '?'} M"
    )


def als_markdown(ergebnis: Abdeckung, pflicht: dict) -> str:
    anbieter = pflicht["anbieter"]
    zeilen = [f"# Bündelabdeckung am {ergebnis.messtag}", ""]
    zeilen.append(
        "**Ergebnis:** "
        + (f"rot, {len(ergebnis.befunde)} Befunde" if ergebnis.rot else "grün")
    )
    zeilen.append("")
    zeilen.append("| Anbieter | Bündel am Messtag |")
    zeilen.append("|---|---:|")
    for a in anbieter:
        zeilen.append(f"| {a} | {ergebnis.anbieter_zahl.get(a, 0)} |")
    zeilen.append("")
    zeilen.append("| Modell | " + " | ".join(anbieter) + " |")
    zeilen.append("|---" * (len(anbieter) + 1) + "|")
    for modell in pflicht["modelle"]:
        zellen = []
        for a in anbieter:
            text = _zelle_text(ergebnis.matrix.get((modell, a)))
            if not text:
                grund = ergebnis.luecken.get((a, modell)) or ergebnis.luecken.get(
                    (a, "*")
                )
                text = "belegt: " + grund if grund else "**fehlt**"
            zellen.append(text)
        zeilen.append(f"| {modell} | " + " | ".join(zellen) + " |")
    if ergebnis.befunde:
        zeilen += ["", "## Befunde", ""]
        zeilen += [f"- {b.text}" for b in ergebnis.befunde]
    return "\n".join(zeilen) + "\n"
