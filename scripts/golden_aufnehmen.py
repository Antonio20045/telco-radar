"""Nimmt den goldenen Lauf auf: echte Quellen, echtes LLM, feste Uhr.

Startet nur Antonio, über ``make golden-aufnehmen`` oder den Workflow ``golden.yml``.
Braucht Netz und den LLM-Schlüssel. Schreibt ``tests/fixtures/golden/<tag>/`` neu,
nie über eine bestehende Aufnahme, und gibt sie erst frei, wenn zwei Wiedergaben
in frischen Prozessen ohne Lücke dieselben Seiten ergeben; erst dann entsteht
``erwartet.json``. ``--pruefen ORDNER`` ist diese Wiedergabe allein. Läuft mit
``PYTHONPATH=src``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import yaml

from telco_radar import golden, pipeline
from telco_radar.analyze import llm
from telco_radar.collect import http
from telco_radar.naehte import PRODUKTION, Naehte

WURZEL = Path(__file__).resolve().parents[1]
ZIEL = WURZEL / "tests" / "fixtures" / "golden"
BESTAND = "tests/fixtures/bestand/2026-10-03"
ERWARTET = "erwartet.json"
# Wenige Quellen, die über collect.http laufen, und keine Stufe mit eigenem Netzweg:
# klein genug für das Repo, groß genug, dass jede LLM-Stufe etwas bekommt.
BETREIBER = {"Vodafone Deutschland", "Deutsche Telekom", "O2 Telefónica Deutschland"}
FACHPRESSE = {"teltarif", "Telecom Handel"}
THEMENQUELLEN = {"OpenAI", "Apple"}
EINSTELLUNGEN = {
    "aenderungsradar_aktiv": False,
    "lieferzeit_radar_aktiv": False,
    "ct_radar_aktiv": False,
    "tarif_radar_aktiv": False,
    "promo_enabled": False,
    "geraete_enabled": False,
    "lookback_days": 3,
    "collect_max_workers": 1,
    "llm_max_workers": 1,
    "analyst_batch_workers": 1,
}
LLM_PFADE = ("/completions", "/messages")


def konfiguration(ziel: Path) -> dict[str, str]:
    """Kopiert ``config/`` und engt Quellen und Stufen ein; gibt die Filter zurück."""
    shutil.copytree(WURZEL / "config", ziel)

    def umschreiben(name: str, aendern: Callable[[dict], None]) -> None:
        pfad = ziel / name
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        aendern(daten)
        pfad.write_text(yaml.safe_dump(daten, allow_unicode=True), encoding="utf-8")

    def watchlist(daten: dict) -> None:
        for region in daten["regions"].values():
            region["operators"] = [
                {**o, "sources": [s for s in o["sources"] if s["type"] == "rss"]}
                for o in region["operators"]
                if o["name"] in BETREIBER
            ]

    def themen(daten: dict) -> None:
        for thema in daten["themen"].values():
            thema["quellen"] = [
                q for q in thema["quellen"] if q["name"] in THEMENQUELLEN
            ]

    def fachpresse(daten: dict) -> None:
        daten["news_sources"] = [
            q for q in daten["news_sources"] if q["name"] in FACHPRESSE
        ]

    umschreiben("settings.yaml", lambda d: d.update(EINSTELLUNGEN))
    umschreiben("watchlist.yaml", watchlist)
    umschreiben("tech_sources.yaml", themen)
    umschreiben("news_sources.yaml", fachpresse)
    return {
        "settings.yaml": json.dumps(EINSTELLUNGEN, sort_keys=True),
        "watchlist.yaml": "nur RSS von " + ", ".join(sorted(BETREIBER)),
        "news_sources.yaml": "nur " + ", ".join(sorted(FACHPRESSE)),
        "tech_sources.yaml": "nur " + ", ".join(sorted(THEMENQUELLEN)),
    }


def aufnehmen(
    ordner: Path,
    uhr: datetime,
    http_innen: http.Transport | None = None,
    llm_innen: golden.LlmClient | None = None,
) -> None:
    """Ein echter Lauf mit fester Uhr; Netz und LLM landen auf den Bändern."""
    filter_je_datei = konfiguration(ordner / "config")
    netz, antworten = golden.Band(), golden.Band()
    tag = uhr.date().isoformat()
    naehte = Naehte(
        transport=http.Aufnahme(netz, http_innen),
        bilder=http.KEIN_BILD,
        llm_client=golden.LlmBand(antworten, tag, llm_innen or llm._dispatch),
        uhr=lambda: uhr,
        stoppuhr=lambda: 0.0,
    )
    vorhanden = [name for name in golden.SCHLUESSEL if os.environ.get(name)]
    with tempfile.TemporaryDirectory() as tmp:
        wurzel = golden.wurzel_bauen(Path(tmp), ordner, WURZEL / BESTAND)
        try:
            with (
                golden.umgebung(vorhanden),
                golden.time_machine.travel(uhr, tick=False),
            ):
                pipeline.run(wurzel, use_llm=True, naehte=naehte)
        finally:
            PRODUKTION.setzen()
    if not any("antwort" in e for liste in antworten.eintraege.values() for e in liste):
        sys.exit("Keine einzige LLM-Antwort; ein Ausfall ist kein goldener Lauf")
    for schluessel in [k for k in netz.eintraege if k[1].endswith(LLM_PFADE)]:
        del netz.eintraege[schluessel]
    golden.schreibe_band(ordner / golden.HTTP_DATEI, netz)
    golden.schreibe_band(ordner / golden.LLM_DATEI, antworten)
    ohne_geheimnis(ordner, vorhanden)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=WURZEL, capture_output=True, text=True
    ).stdout.strip()
    angaben = {
        "zeit": uhr.isoformat(),
        "commit": commit,
        "bestand": BESTAND,
        "umgebung": vorhanden,
        "lauf": os.environ.get("GITHUB_RUN_ID", "lokal"),
        "eintraege": [],
    }
    schreibe_herkunft(ordner, angaben, filter_je_datei)


def ohne_geheimnis(ordner: Path, vorhanden: list[str]) -> None:
    """Verwirft die Aufnahme, wenn ein Schlüssel im Klartext darin steht."""
    for pfad in [p for p in ordner.rglob("*") if p.is_file()]:
        roh = pfad.read_bytes()
        roh = golden.gzip.decompress(roh) if pfad.suffix == ".gz" else roh
        if any(os.environ[name].encode() in roh for name in vorhanden):
            shutil.rmtree(ordner)
            sys.exit(f"Schlüssel in {pfad.name}; Aufnahme verworfen")


def schreibe_herkunft(ordner: Path, angaben: dict, filter_je_datei: dict) -> None:
    """Je Ordner ``_herkunft.json`` mit sha256 und Beleg je Datei, wie Stufe 0 es
    für Fixtures verlangt; im Aufnahmeordner zusätzlich Uhr, Umgebung, Bestand."""
    aufnahme = f"goldener Lauf {angaben['zeit']}, Lauf {angaben['lauf']}"
    je_ordner: dict[Path, list[dict]] = {ordner: []}
    for pfad in sorted(p for p in ordner.rglob("*") if p.is_file()):
        if pfad.name == golden.HERKUNFT:
            continue
        roh = pfad.read_bytes()
        if pfad.suffix == ".gz":
            roh = golden.gzip.decompress(roh)
        if pfad.parent.name == "config":
            beleg = {"abgeleitet_aus": f"config/{pfad.name} @ {angaben['commit']}"}
        elif pfad.name == ERWARTET:
            beleg = {"abgeleitet_aus": "zwei Wiedergaben der Aufnahme, gleiche Seiten"}
        else:
            beleg = {"quelle": aufnahme}
        je_ordner.setdefault(pfad.parent, []).append(
            {
                "datei": pfad.name,
                **beleg,
                "commit": angaben["commit"],
                "filter": filter_je_datei.get(pfad.name),
                "sha256_roh": hashlib.sha256(roh).hexdigest(),
            }
        )
    for ziel, eintraege in je_ordner.items():
        inhalt = {**angaben, "eintraege": eintraege} if ziel == ordner else {}
        inhalt.setdefault("eintraege", eintraege)
        text = json.dumps(inhalt, indent=1, sort_keys=True, ensure_ascii=False)
        (ziel / golden.HERKUNFT).write_text(text + "\n", encoding="utf-8")


def pruefen(ordner: Path) -> dict[str, str]:
    """Eine Wiedergabe in einem frischen Ordner; Lücken und Netz beenden mit Exit 1."""
    netz: list[str] = []

    def kein_netz(ereignis: str, argumente: tuple) -> None:
        if ereignis == "socket.connect":
            netz.append(f"Netzzugriff in der Wiedergabe: {argumente[1]}")
            raise OSError(netz[-1])

    sys.addaudithook(kein_netz)
    with tempfile.TemporaryDirectory() as tmp:
        bestand = WURZEL / golden.herkunft(ordner)["bestand"]
        wurzel = golden.wurzel_bauen(Path(tmp), ordner, bestand)
        band = golden.lauf(ordner, wurzel)
        if band.fehlend or netz:
            sys.exit("\n".join((band.fehlend + netz)[:20]))
        return golden.seiten(wurzel)


def freigeben(ordner: Path) -> None:
    """Zwei Wiedergaben in eigenen Prozessen; nur gleiche Seiten werden erwartet."""
    umgebung = {
        k: v
        for k, v in os.environ.items()
        if k not in golden.UMGEBUNG and not k.startswith(("GITHUB_", "RUNNER_"))
    }
    ergebnisse = []
    for samen in ("1", "2"):
        lauf = subprocess.run(
            [sys.executable, __file__, "--pruefen", str(ordner)],
            env={**umgebung, "PYTHONHASHSEED": samen},
            capture_output=True,
            text=True,
        )
        if lauf.returncode:
            sys.exit(f"Wiedergabe {samen} gescheitert:\n{lauf.stderr[-4000:]}")
        ergebnisse.append(json.loads(lauf.stdout.splitlines()[-1]))
    abweichend = sorted(
        k for k in ergebnisse[0] if ergebnisse[0][k] != ergebnisse[1].get(k)
    )
    if abweichend or ergebnisse[0].keys() != ergebnisse[1].keys():
        sys.exit("Wiedergaben weichen ab: " + ", ".join(abweichend[:20]))
    text = json.dumps(ergebnisse[0], indent=1, sort_keys=True)
    (ordner / ERWARTET).write_text(text + "\n", encoding="utf-8")
    angaben = golden.herkunft(ordner)
    alt = golden.herkunft(ordner / "config")["eintraege"]
    schreibe_herkunft(ordner, angaben, {e["datei"]: e["filter"] for e in alt})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pruefen", type=Path, help="nur wiedergeben, Seiten als JSON")
    args = parser.parse_args()
    if args.pruefen:
        print(json.dumps(pruefen(args.pruefen), sort_keys=True))
        return 0
    if not os.environ.get("LLM_API_KEY"):
        sys.exit("LLM_API_KEY fehlt; die Aufnahme ist ein echter Lauf")
    uhr = datetime.now(UTC).replace(microsecond=0)
    ordner = ZIEL / uhr.date().isoformat()
    if ordner.exists():
        sys.exit(f"{ordner} gibt es schon; Aufnahmen werden ersetzt, nicht geändert")
    aufnehmen(ordner, uhr)
    freigeben(ordner)
    print(f"Aufnahme freigegeben: {ordner.relative_to(WURZEL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
