#!/usr/bin/env python3
"""Macht aus der Sonnet-Recherche eine Firmenliste fuer die mechanische Suche.

Warum getrennt
--------------
Der Auftrag trennt die Rollen strikt (AUFTRAG_1000_QUELLEN_WELLE3.md
Abschnitt 5): recherchierende Agents sagen nur, WO gesucht werden soll - Name
und Domain, mehr nicht. Was davon taugt, entscheidet allein die mechanische
Suche und danach der Abnahme-Check. Dieses Skript ist die Naht dazwischen und
enthaelt deshalb bewusst KEINE Bewertung, nur Formpruefung und Entdopplung.

Eingabe ist das Zeilenformat, das die Agents liefern:

    Name|domain.tld|LL|kategorie|Begruendung

Warum Zeilen und nicht JSON: der erste Anlauf liess die Agents ein
StructuredOutput-Werkzeug mit JSON-Schema aufrufen. Alle vierzehn scheiterten
daran - sie hatten recherchiert (rund 960 000 Token, 205 Werkzeugaufrufe) und
konnten das Ergebnis nicht abliefern, die Antwort war weg. Ein Format, das
sich nicht validieren laesst, kann auch nicht an der Validierung sterben.

Aufruf
------
    python scripts/recherche_zu_firmenliste.py rohdaten.txt --out firmen.yaml
    python scripts/recherche_zu_firmenliste.py rohdaten.txt --out firmen.yaml \\
        --nur regulierer,fachpresse
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.config import load_config  # noqa: E402

KATEGORIEN = {"betreiber", "regulierer", "fachpresse", "verband",
              "infrastruktur", "plattform"}
# Kategorie -> Themenfeld in tech_sources.yaml. "betreiber" bekommt stattdessen
# eine Region und landet in der Watchlist.
THEMA_JE_KATEGORIE = {
    "regulierer": "regulierung",
    "verband": "regulierung",
    "infrastruktur": "infrastruktur",
    "plattform": "mvno",
}
_DOMAIN_OK = re.compile(r"^[a-z0-9][a-z0-9.-]{1,60}\.[a-z]{2,}$")


def _domain(roh: str) -> str:
    d = (roh or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.removeprefix("www.").split("/")[0].split("?")[0].strip().rstrip(".")
    return d if _DOMAIN_OK.match(d) else ""


def lies_zeilen(text: str) -> list[dict]:
    raus: list[dict] = []
    for roh in text.splitlines():
        teile = [t.strip() for t in roh.split("|")]
        if len(teile) < 4:
            continue
        name, domain_roh, land, kategorie = teile[:4]
        begruendung = " | ".join(teile[4:])
        domain = _domain(domain_roh)
        kategorie = kategorie.lower()
        # Formpruefung, keine Wertpruefung: ein zu langer "Name" ist eine
        # Fliesstextzeile, die zufaellig Striche enthaelt.
        if not name or len(name) > 60 or not domain:
            continue
        if kategorie not in KATEGORIEN:
            continue
        raus.append({"name": name, "domain": domain,
                     "country": land.upper()[:2], "kategorie": kategorie,
                     "begruendung": begruendung})
    return raus


def bekannte_domains(root: Path) -> set[str]:
    """Firmen, die schon eine Quelle stellen - die sucht niemand noch mal."""
    from urllib.parse import urlsplit
    try:
        cfg = load_config(root)
    except Exception:  # noqa: BLE001
        return set()

    def _dom(url: str) -> str:
        host = urlsplit(url).netloc.lower().removeprefix("www.")
        teile = host.split(".")
        return ".".join(teile[-3:]) if len(teile) >= 3 and len(teile[-1]) == 2 \
            and teile[-2] in {"co", "com", "net", "org", "gov", "ac"} \
            else ".".join(teile[-2:])

    raus: set[str] = set()
    for op in cfg.operators:
        if op.website:
            raus.add(_domain(op.website))
        for s in op.sources:
            raus.add(_dom(s.url))
    for s in list(cfg.news_sources) + list(cfg.tech_sources):
        raus.add(_dom(s.url))
    return {d for d in raus if d}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("datei", type=Path, help="Rohdaten im Zeilenformat")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--nur", default="",
                   help="nur diese Kategorien, mit Komma getrennt")
    args = p.parse_args(argv)

    eintraege = lies_zeilen(args.datei.read_text(encoding="utf-8"))
    print(f"{len(eintraege)} formal gueltige Zeilen gelesen")

    if args.nur:
        gewuenscht = {k.strip().lower() for k in args.nur.split(",")}
        vorher = len(eintraege)
        eintraege = [e for e in eintraege if e["kategorie"] in gewuenscht]
        print(f"{vorher - len(eintraege)} Zeilen wegen --nur uebersprungen")

    bekannt = bekannte_domains(args.root.resolve())
    gesehen: set[str] = set()
    firmen: list[dict] = []
    doppelt = schon_da = 0
    for e in eintraege:
        if e["domain"] in gesehen:
            doppelt += 1
            continue
        gesehen.add(e["domain"])
        if e["domain"] in bekannt:
            schon_da += 1
            continue
        eintrag = {"name": e["name"], "domain": e["domain"],
                   "country": e["country"],
                   "herkunft": f"Sonnet-Recherche Welle 3 ({e['kategorie']})"}
        thema = THEMA_JE_KATEGORIE.get(e["kategorie"])
        if thema:
            eintrag["thema"] = thema
        firmen.append(eintrag)

    print(f"{doppelt} Dubletten in der Recherche, "
          f"{schon_da} bereits konfiguriert")
    print(f"{len(firmen)} Suchauftraege -> {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump({"firmen": firmen}, allow_unicode=True,
                       sort_keys=False),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
