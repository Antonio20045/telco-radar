"""Klickliste aus dem Katalog: erkannte neue Modelle kommen ohne Handarbeit hinein.

``config/klick_tageslauf.yaml`` ist von Hand gepflegt; ein neues Modell (iPhone Duo,
02.11.2026) stand darum in keiner Klickliste und bekam nie einen Einzelgerätepreis.
Hier wird der Rest abgeleitet: jedes Telefon der großen Marken (``FAMILIEN``) im
Katalog, einschließlich der Auto-Einträge, das ein Anbieter im Bestand
(``data/state/geraete_tco.json``) führt, aber in der Klickliste dieses Anbieters
fehlt, bekommt dort eine Seite. Die Adresse ist die ``quelle_url`` eines Bündels aus
dem Bestand, nie zusammengesetzt (Regel 4: IDs werden nicht geraten). Sie gilt nur,
wenn sie das Gerät nennt und eine darin genannte Speicherstufe zur SKU passt; ein
Bündel mit Tarifübersicht als Quelle liefert keine Seite. Jeder Anbieter bekommt
höchstens ``HOECHSTE_SEITEN_JE_ANBIETER`` Plätze (Gerät und Stufe), die neuesten Geräte
zuerst. Rein, ohne Netz; ``klickziele.lade_ziele`` prüft die Seiten danach wie die aus
der YAML.

Der Tarif gehört zur Seite (``TARIF_PARAMETER``): Eine Telekom-Produktseite zeigt nur
den Tarif ihrer Startadresse, die Übersicht der übrigen Tarife nur 36 Raten. Ein Gerät
bekommt darum eine Seite je Tarif, den der Bestand für dieses Gerät mit eigener Adresse
führt, jeweils auf der kleinsten Stufe (die Seite liest alle Stufen). Befund 09.11.2026:
das iPhone Duo stand bei Telekom nur mit der Adresse der ersten Fundstelle (Tarif L) in
der Liste, 24 Raten gab es für XS, S, M und XL nicht.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ...geraete_model import Geraet, Katalog

BESTAND = Path("data") / "state" / "geraete_tco.json"
FAMILIEN = {
    "apple": re.compile(r"^iphone\b", re.IGNORECASE),
    "samsung": re.compile(r"^galaxy s\d", re.IGNORECASE),
    "google": re.compile(r"^pixel \d", re.IGNORECASE),
}
HOECHSTE_SEITEN_JE_ANBIETER = 8
TARIF_PARAMETER = {"Telekom": "tariffId"}
PRUEFUNG_VERALTET = "veraltet"
_SPEICHER_SKU = re.compile(r"^(\d+)gb-")
_SPEICHER_URL = re.compile(r"(?<![a-z0-9])(\d+)[-]?(gb|tb)(?![a-z0-9])")
_GB_JE_TB = 1024
_Schluessel = tuple[str, str, int, str]


class KlicklisteAutoFehler(ValueError):
    """Der Bestand ist da, aber nicht lesbar: das Ergebnis wäre sonst still leer."""


@dataclass(frozen=True)
class AutoSeite:
    """Eine abgeleitete Seite: Anbietername aus den Quellen, Gerät, Stufe, Adresse."""

    anbieter: str
    geraet: str
    speicher_gb: int
    url: str


def ist_grosse_marke(geraet: Geraet) -> bool:
    """Telefon einer der Familien in ``FAMILIEN``; Zubehör und Tablets nicht."""
    muster = FAMILIEN.get(geraet.hersteller.strip().lower())
    return muster is not None and muster.match(geraet.modell.strip()) is not None


def leite_ab(
    root: Path, katalog: Katalog, vorhanden: set[tuple[str, str]]
) -> list[AutoSeite]:
    """Die fehlenden Seiten; ``vorhanden`` sind Paare (Anbieter, Geräte-ID) der YAML.

    Fehlt der Bestand, gibt es nichts abzuleiten (leere Liste); ist er unlesbar, wirft
    die Funktion ``KlicklisteAutoFehler``.
    """
    buendel = _lies_buendel(root / BESTAND)
    geraete = {g.device_id: g for g in katalog.geraete if ist_grosse_marke(g)}
    kandidaten: dict[_Schluessel, str] = {}
    for eintrag in buendel:
        paar = _paar(eintrag, geraete)
        if paar is None:
            continue
        geraet, speicher = paar
        anbieter = str(eintrag.get("anbieter") or "").strip()
        url = str(eintrag.get("quelle_url") or "").strip()
        if not anbieter or (anbieter, geraet.device_id) in vorhanden:
            continue
        if speicher not in geraet.speicher or not _passt(url, geraet, speicher):
            continue
        schluessel = (
            anbieter,
            geraet.device_id,
            speicher,
            _tarif_kennung(anbieter, url),
        )
        kandidaten.setdefault(schluessel, url)
    return _begrenze(_je_tarif_eine_stufe(_je_adresse_eine_stufe(kandidaten)), geraete)


def _tarif_kennung(anbieter: str, url: str) -> str:
    """Der Tarif, den die Adresse wählt; leer, wo die Seite den Tarif nicht aus der
    Adresse nimmt (``TARIF_PARAMETER``)."""
    parameter = TARIF_PARAMETER.get(anbieter)
    if parameter is None:
        return ""
    werte = parse_qs(urlsplit(url).query).get(parameter)
    return werte[0].strip() if werte else ""


def _je_tarif_eine_stufe(kandidaten: dict[_Schluessel, str]) -> dict[_Schluessel, str]:
    """Wählt die Adresse den Tarif, genügt je (Anbieter, Gerät, Tarif) die kleinste
    Stufe: die Seite liest alle Stufen. Ohne Tarifkennung bleibt jede Stufe."""
    einzeln: dict[tuple[str, str, str], _Schluessel] = {}
    for schluessel in sorted(kandidaten, key=lambda s: s[2]):
        anbieter, gid, _, tarif = schluessel
        if tarif:
            einzeln.setdefault((anbieter, gid, tarif), schluessel)
    waehlt_tarif = set(einzeln.values())
    return {s: u for s, u in kandidaten.items() if not s[3] or s in waehlt_tarif}


def _je_adresse_eine_stufe(
    kandidaten: dict[_Schluessel, str],
) -> dict[_Schluessel, str]:
    """Steht eine Adresse für mehrere Stufen (Geräteseite ohne Stufe in der Adresse),
    bleibt die kleinste: der Crawler klickt alle Varianten einer Seite ohnehin."""
    einzeln: dict[tuple[str, str, str], _Schluessel] = {}
    for schluessel in sorted(kandidaten, key=lambda s: s[2]):
        anbieter, gid, _, _ = schluessel
        einzeln.setdefault((anbieter, gid, kandidaten[schluessel]), schluessel)
    return {s: kandidaten[s] for s in einzeln.values()}


def _lies_buendel(pfad: Path) -> list[dict]:
    try:
        text = pfad.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as fehler:
        raise KlicklisteAutoFehler(f"{pfad}: nicht lesbar ({fehler})") from fehler
    try:
        daten = json.loads(text)
    except json.JSONDecodeError as fehler:
        raise KlicklisteAutoFehler(f"{pfad}: kein JSON ({fehler})") from fehler
    liste = daten.get("buendel") if isinstance(daten, dict) else None
    if not isinstance(liste, list):
        raise KlicklisteAutoFehler(f"{pfad}: Feld buendel fehlt")
    return [
        b
        for b in liste
        if isinstance(b, dict)
        and not str(b.get("pruefung") or "").startswith(PRUEFUNG_VERALTET)
    ]


def _paar(eintrag: dict, geraete: dict[str, Geraet]) -> tuple[Geraet, int] | None:
    """Gerät und Speicherstufe der SKU, über die längste Katalog-ID davor."""
    sku = str(eintrag.get("sku_id") or "")
    treffer: tuple[Geraet, int] | None = None
    for gid, geraet in geraete.items():
        if not sku.startswith(gid + "-"):
            continue
        stufe = _SPEICHER_SKU.match(sku[len(gid) + 1 :])
        if stufe is None:
            continue
        if treffer is None or len(gid) > len(treffer[0].device_id):
            treffer = (geraet, int(stufe.group(1)))
    return treffer


def _passt(url: str, geraet: Geraet, speicher: int) -> bool:
    """Die Adresse nennt das Gerät (nicht nur eine Tarifübersicht), Stufe stimmt."""
    if not url.startswith("https://"):
        return False
    adresse = url.lower().split("#")[0]
    kurz = geraet.device_id.removeprefix(
        re.sub(r"[^a-z0-9]+", "-", geraet.hersteller.lower()) + "-"
    )
    for name in {geraet.device_id, kurz}:
        if re.search(
            rf"(?<![a-z0-9-]){re.escape(name)}(?=$|[/.?#]|-\d+-?[gt]b)", adresse
        ):
            break
    else:
        return False
    pfad = adresse.split("?")[0]
    stufen = {
        int(zahl) * (_GB_JE_TB if einheit == "tb" else 1)
        for zahl, einheit in _SPEICHER_URL.findall(pfad)
    }
    return not stufen or stufen == {speicher}


def _begrenze(
    kandidaten: dict[_Schluessel, str], geraete: dict[str, Geraet]
) -> list[AutoSeite]:
    """Höchstens ``HOECHSTE_SEITEN_JE_ANBIETER`` Plätze (Gerät und Stufe) je Anbieter,
    neueste Geräte zuerst; die Tarifseiten eines Platzes zählen zusammen als einer."""

    def rang(schluessel: _Schluessel) -> tuple:
        anbieter, gid, speicher, tarif = schluessel
        g = geraete[gid]
        return (
            anbieter,
            -(g.generation or 0),
            g.marktstart == "",
            gid,
            speicher,
            tarif,
        )

    plaetze: dict[str, set[tuple[str, int]]] = {}
    ergebnis: list[AutoSeite] = []
    for schluessel in sorted(kandidaten, key=rang):
        anbieter, gid, speicher, _ = schluessel
        belegt = plaetze.setdefault(anbieter, set())
        if (gid, speicher) not in belegt and len(belegt) >= HOECHSTE_SEITEN_JE_ANBIETER:
            continue
        belegt.add((gid, speicher))
        ergebnis.append(AutoSeite(anbieter, gid, speicher, kandidaten[schluessel]))
    return ergebnis
