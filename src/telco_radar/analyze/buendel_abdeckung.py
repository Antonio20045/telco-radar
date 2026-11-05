"""Abdeckung der Bündel: welcher Anbieter liefert welches Gerät in welchem
Tarif, und was ist seit dem letzten Messtag weggefallen oder gesprungen.

Der ältere Wächter (`GeraeteDB.ausfall_alarme`) prüft Listungen und schlägt
nur an, wenn ein Anbieter GESTERN noch lieferte. Die Telekom lieferte seit
dem 15.09.2026 kein Bündel mehr, und kein Lauf wurde rot: wer schon
ausgefallen ist, fällt diesem Vergleich nie wieder auf. Diese Prüfung misst
deshalb gegen eine feste Pflichtliste (`config/geraete_abdeckung.yaml`),
nicht gegen den Vortag, und sie misst die Bündel, aus denen die Leitzahl
„Kosten über 24 Monate“ entsteht.

Fünf Befundarten, jede für sich rot:

* ``anbieter_leer``     ein Pflichtanbieter hat am Messtag kein Bündel
* ``modell_fehlt``      ein Pflichtmodell fehlt bei einem Pflichtanbieter,
                        ohne dass eine belegte Lücke in der Config steht
* ``kombis_weg``        gegenüber dem vorigen Messtag fehlen mehr als
                        `KOMBI_VERLUST_ANTEIL` der Kombinationen
* ``preissprung``       die Leitzahl einer Kombination springt um mehr als
                        `PREISSPRUNG_ANTEIL` gegenüber dem vorigen Messtag; über
                        einen Bruch der Rechenweise (`rechenweise`) wird nicht
                        verglichen
* ``luecke_abgelaufen`` eine belegte Lücke ist über ihr Ablaufdatum ``bis``
                        hinaus (Messtag > ``bis``): neu prüfen oder streichen

Eine belegte Lücke (Anbieter führt das Gerät nicht, Anbieter nicht
erreichbar) ist kein Befund, sie steht aber mit ihrem Grund in der Matrix.
Jede trägt ``geprueft`` und ``bis``, höchstens ``LUECKE_MAX_TAGE`` Tage nach
``geprueft``: eine Ausnahme verjährt, sie wird nicht vergessen. Ist ein Bündel
für eine belegte Lücke wieder da, ist die Ausnahme überholt: das ist kein
Befund, aber eine laute Warnung (``Abdeckung.warnungen``).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from .. import rechenweise, tco_historie
from ..geraete_model import normalisiere

KOMBI_VERLUST_ANTEIL = 0.10
KOMBI_VERLUST_MINDEST = 5
PREISSPRUNG_ANTEIL = 0.25
BEISPIELE = 8
LUECKE_MAX_TAGE = 14

_SKU_MUSTER = re.compile(r"^(?P<modell>.+?)-(?P<speicher>\d+gb|ohne-speicher)-")


@dataclass
class Befund:
    art: str
    anbieter: str
    text: str


@dataclass
class Abdeckung:
    messtag: str | None
    vortag: str | None
    matrix: dict = field(default_factory=dict)
    anbieter_zahl: dict = field(default_factory=dict)
    luecken: dict = field(default_factory=dict)
    befunde: list = field(default_factory=list)
    warnungen: list = field(default_factory=list)

    @property
    def rot(self) -> bool:
        return bool(self.befunde)


def modell_und_speicher(sku_id: str) -> tuple[str | None, str | None]:
    """Katalogmodell und Speicherstufe aus der SKU-ID
    (`geraete_model.sku_id`: Gerät-Speicher-Farbe[-Zustand])."""
    treffer = _SKU_MUSTER.match(sku_id or "")
    if not treffer:
        return None, None
    return treffer.group("modell"), treffer.group("speicher")


def _datum(eintrag: dict, feld: str) -> date:
    try:
        return date.fromisoformat(str(eintrag.get(feld)))
    except ValueError:
        raise ValueError(f"belegte Lücke ohne Datum '{feld}': {eintrag}") from None


def lade_pflicht(pfad: Path) -> dict:
    """Pflichtliste; ``luecken``: (Anbieter, Modell) -> Grund, ``bis``: -> Datum."""
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    luecken, bis = {}, {}
    for eintrag in daten.get("belegte_luecken") or []:
        grund = str(eintrag.get("grund") or "").strip()
        if not grund:
            raise ValueError(f"belegte Lücke ohne Grund: {eintrag}")
        geprueft, ende = _datum(eintrag, "geprueft"), _datum(eintrag, "bis")
        if not geprueft <= ende <= geprueft + timedelta(days=LUECKE_MAX_TAGE):
            raise ValueError(
                f"belegte Lücke: 'bis' muss höchstens {LUECKE_MAX_TAGE} Tage nach "
                f"'geprueft' liegen: {eintrag}"
            )
        for modell in eintrag.get("modelle") or ["*"]:
            luecken[(eintrag["anbieter"], modell)] = grund
            bis[(eintrag["anbieter"], modell)] = ende
    return {
        "anbieter": list(daten.get("pflicht_anbieter") or []),
        "modelle": list(daten.get("pflicht_modelle") or []),
        "luecken": luecken,
        "bis": bis,
    }


def _pruefe_luecken(ergebnis: Abdeckung, pflicht: dict) -> None:
    """Abgelaufene Ausnahmen sind Befunde, überholte (Bündel wieder da) Warnungen."""
    for (anbieter, modell), ende in sorted(pflicht.get("bis", {}).items()):
        if ergebnis.messtag and ergebnis.messtag > ende.isoformat():
            text = (
                f"{anbieter}: belegte Lücke {modell} ist seit {ende.isoformat()} "
                "abgelaufen: an der Anbieterseite neu prüfen, dann mit neuem "
                f"'geprueft' und 'bis' (höchstens {LUECKE_MAX_TAGE} Tage) verlängern "
                "oder streichen"
            )
            ergebnis.befunde.append(Befund("luecke_abgelaufen", anbieter, text))
        da = (
            ergebnis.anbieter_zahl.get(anbieter)
            if modell == "*"
            else (modell, anbieter) in ergebnis.matrix
        )
        if da:
            ergebnis.warnungen.append(
                Befund(
                    "luecke_ueberholt",
                    anbieter,
                    f"{anbieter}: Ausnahme {modell} ist überholt, am Messtag gibt "
                    "es wieder Bündel: Eintrag in config/geraete_abdeckung.yaml "
                    "(belegte_luecken) streichen",
                )
            )


def _anbieter_aus_id(buendel_id: str, namen: dict) -> str | None:
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

    _pruefe_luecken(ergebnis, pflicht)
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
        je_tag[anbieter][zeile.get("datum")][zeile["id"]] = zeile

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
            if not rechenweise.gleich(alt[bid], neu[bid]):
                continue
            a, n = alt[bid].get("gesamt"), neu[bid].get("gesamt")
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
    if tco_historie.vorhanden(pfad):
        historie = [json.loads(z) for z in tco_historie.zeilen(pfad) if z.strip()]
    pflicht = lade_pflicht(root / "config" / "geraete_abdeckung.yaml")
    return pruefe(tco, historie, pflicht)


def _zelle_text(zelle: dict | None) -> str:
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
    if ergebnis.warnungen:
        zeilen += ["", "## Warnungen", ""]
        zeilen += [f"- {w.text}" for w in ergebnis.warnungen]
    return "\n".join(zeilen) + "\n"
