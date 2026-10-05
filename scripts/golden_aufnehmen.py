"""Nimmt den goldenen Lauf auf: echte Quellen, echtes LLM, feste Uhr.

Startet nur Antonio, über ``make golden-aufnehmen`` oder den Workflow ``golden.yml``.
Braucht Netz und den LLM-Schlüssel. Schreibt ``tests/fixtures/golden/<tag>/`` neu,
nie über eine bestehende Aufnahme, und gibt sie erst frei, wenn zwei Wiedergaben
in frischen Prozessen ohne Lücke dieselben Seiten ergeben; erst dann entsteht
``erwartet.json``. ``--pruefen ORDNER`` ist diese Wiedergabe allein. Lehnt das LLM
jede Anfrage ab, bricht die Aufnahme ab; nur ``--llm-ausfall`` nimmt diesen Weg
ausdrücklich auf und vermerkt ihn in ``_herkunft.json``. ``--ableiten ALT`` nimmt
ohne Netz aus der Aufnahme ALT neu auf, wenn sich der Code geändert hat; was ALT
nicht kennt, landet als Verbindungsfehler und unter ``luecken``; alte Lücken, die
der neue Lauf noch anfragt, bleiben stehen. ``--seiten-neu ORDNER`` schreibt nach
zwei gleichen Wiedergaben nur ``erwartet.json`` und dessen sha256 neu, die Bänder
bleiben byte-gleich, und gibt die geänderten Seiten als JSON-Liste aus. Läuft mit
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
LLM_AUSFALL = "jede LLM-Anfrage abgelehnt, aufgenommen ist der Weg ohne LLM"


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
    llm_ausfall: bool = False,
    zusatz: dict | None = None,
) -> None:
    """Ein echter Lauf mit fester Uhr; Netz und LLM landen auf den Bändern.

    ``zusatz`` kommt aus ``ableiten`` und ersetzt Umgebung und Lauf der Herkunft.
    """
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
    if zusatz:
        vorhanden = zusatz["umgebung"]
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
    llm_pruefen(antworten, llm_ausfall)
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
        "llm": LLM_AUSFALL if llm_ausfall else "beantwortet",
        **(zusatz or {}),
        "eintraege": [],
    }
    schreibe_herkunft(ordner, angaben, filter_je_datei)


def llm_pruefen(antworten: golden.Band, llm_ausfall: bool) -> None:
    """Ein Ausfall wird nur mit ``--llm-ausfall`` golden, und nur ein ganzer."""
    beantwortet = any("antwort" in e for v in antworten.eintraege.values() for e in v)
    if not beantwortet and not llm_ausfall:
        sys.exit("Keine einzige LLM-Antwort; den Ausfall nimmt nur --llm-ausfall auf")
    if beantwortet and llm_ausfall:
        sys.exit("--llm-ausfall, aber das LLM hat geantwortet; ohne Schalter aufnehmen")


def ohne_geheimnis(ordner: Path, vorhanden: list[str]) -> None:
    """Verwirft die Aufnahme, wenn ein Schlüssel im Klartext darin steht."""
    for pfad in [p for p in ordner.rglob("*") if p.is_file()]:
        roh = pfad.read_bytes()
        roh = golden.gzip.decompress(roh) if pfad.suffix == ".gz" else roh
        werte = [os.environ[name] for name in vorhanden if os.environ.get(name)]
        if any(wert.encode() in roh for wert in werte):
            shutil.rmtree(ordner)
            sys.exit(f"Schlüssel in {pfad.name}; Aufnahme verworfen")


def schreibe_herkunft(ordner: Path, angaben: dict, filter_je_datei: dict) -> None:
    """Je Ordner ``_herkunft.json`` mit sha256 und Beleg je Datei, wie Stufe 0 es
    für Fixtures verlangt; im Aufnahmeordner zusätzlich Uhr, Umgebung, Bestand."""
    aufnahme = f"goldener Lauf {angaben['zeit']}, Lauf {angaben['lauf']}"
    quelle = "abgeleitet_aus" if "abgeleitet_aus" in angaben else "quelle"
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
            beleg = {quelle: aufnahme}
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


def ableiten(alt: Path, ordner: Path) -> None:
    """Neue Aufnahme ohne Netz aus ALT, deren LLM jede Anfrage abgelehnt hat.

    Quellen antworten aus ALT; Anfragen, die ALT nicht kennt, scheitern als
    Verbindungsfehler und stehen unter ``luecken``. Das LLM lehnt ab wie in ALT.
    """
    angaben = golden.herkunft(alt)
    netz = golden.lies_band(alt / golden.HTTP_DATEI)
    fehler = {
        e.get("fehler")
        for v in golden.lies_band(alt / golden.LLM_DATEI).eintraege.values()
        for e in v
    }
    if fehler != {"LLMFatalError"}:
        sys.exit(f"{alt} hat LLM-Antworten {sorted(map(str, fehler))}; nur Ablehnungen")

    def abgelehnt(*_: object) -> str:
        raise llm.LLMFatalError(f"abgelehnt wie in Lauf {angaben['lauf']}")

    lauf, code = angaben["lauf"], angaben["commit"]
    zusatz = {
        "umgebung": angaben["umgebung"],
        "lauf": lauf,
        "abgeleitet_aus": f"Aufnahme aus Lauf {lauf}, Code {code}",
    }
    uhr = datetime.fromisoformat(angaben["zeit"])
    aufnehmen(ordner, uhr, http.Wiedergabe(netz), abgelehnt, True, zusatz)
    neu = golden.lies_band(ordner / golden.HTTP_DATEI)
    luecken = luecken_vereinigen(angaben.get("luecken", []), netz.fehlend, neu)
    angaben = {**golden.herkunft(ordner), "luecken": luecken}
    alt_filter = golden.herkunft(ordner / "config")["eintraege"]
    schreibe_herkunft(ordner, angaben, {e["datei"]: e["filter"] for e in alt_filter})


def luecken_vereinigen(
    alt: list[str], fehlend: list[str], neu: golden.Band
) -> list[str]:
    """Neue Lücken und die alten, deren Anfrage der neue Lauf noch stellt.

    Eine alte Lücke steht im abgeleiteten Band als Verbindungsfehler und gilt der
    nächsten Ableitung als vorhanden; ohne diese Vereinigung ginge sie verloren.
    """
    angefragt = {f"HTTP-Antwort für {k[0]} {k[1]}" for k in neu.eintraege}
    bleiben = {e for e in alt if e.partition(" fehlt, ")[0] in angefragt}
    return sorted(set(fehlend) | bleiben)


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


def wiedergaben(ordner: Path) -> dict[str, str]:
    """Zwei Wiedergaben in eigenen Prozessen; nur gleiche Seiten zählen."""
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
    return ergebnisse[0]


def _erwartet_schreiben(ordner: Path, seiten: dict[str, str]) -> None:
    text = json.dumps(seiten, indent=1, sort_keys=True)
    (ordner / ERWARTET).write_text(text + "\n", encoding="utf-8")


def freigeben(ordner: Path) -> None:
    """Schreibt ``erwartet.json`` aus zwei gleichen Wiedergaben und die Herkunft."""
    _erwartet_schreiben(ordner, wiedergaben(ordner))
    angaben = golden.herkunft(ordner)
    alt = golden.herkunft(ordner / "config")["eintraege"]
    schreibe_herkunft(ordner, angaben, {e["datei"]: e["filter"] for e in alt})


def seiten_neu(ordner: Path) -> list[str]:
    """Neue Seiten aus der bestehenden Aufnahme; gibt die geänderten Pfade zurück.

    Nur ``erwartet.json`` und sein sha256 in ``_herkunft.json`` ändern sich; Bänder,
    Konfiguration und alle übrigen Angaben der Herkunft bleiben, wie sie sind.
    """
    neu = wiedergaben(ordner)
    alt = json.loads((ordner / ERWARTET).read_text(encoding="utf-8"))
    geaendert = sorted(p for p in alt.keys() | neu.keys() if alt.get(p) != neu.get(p))
    if not geaendert:
        return []
    _erwartet_schreiben(ordner, neu)
    pfad = ordner / golden.HERKUNFT
    herkunft = json.loads(pfad.read_text(encoding="utf-8"))
    roh = (ordner / ERWARTET).read_bytes()
    for eintrag in herkunft["eintraege"]:
        if eintrag["datei"] == ERWARTET:
            eintrag["sha256_roh"] = hashlib.sha256(roh).hexdigest()
    text = json.dumps(herkunft, indent=1, sort_keys=True, ensure_ascii=False)
    pfad.write_text(text + "\n", encoding="utf-8")
    return geaendert


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pruefen", type=Path, help="nur wiedergeben, Seiten als JSON")
    parser.add_argument("--llm-ausfall", action="store_true", help=LLM_AUSFALL)
    parser.add_argument("--ableiten", type=Path, help="ohne Netz aus dieser Aufnahme")
    parser.add_argument("--seiten-neu", type=Path, help="nur erwartet.json neu")
    args = parser.parse_args()
    if args.pruefen:
        print(json.dumps(pruefen(args.pruefen), sort_keys=True))
        return 0
    if args.seiten_neu:
        print(json.dumps(seiten_neu(args.seiten_neu.resolve()), ensure_ascii=False))
        return 0
    if args.ableiten:
        if not args.llm_ausfall:
            sys.exit("--ableiten gibt es nur mit --llm-ausfall")
        alt = args.ableiten.resolve()
        with tempfile.TemporaryDirectory() as tmp:
            neu = Path(tmp) / alt.name
            ableiten(alt, neu)
            freigeben(neu)
            shutil.rmtree(alt)
            shutil.copytree(neu, alt)
        print(f"Aufnahme abgeleitet und freigegeben: {alt.relative_to(WURZEL)}")
        return 0
    if not os.environ.get("LLM_API_KEY"):
        sys.exit("LLM_API_KEY fehlt; die Aufnahme ist ein echter Lauf")
    uhr = datetime.now(UTC).replace(microsecond=0)
    ordner = ZIEL / uhr.date().isoformat()
    if ordner.exists():
        sys.exit(f"{ordner} gibt es schon; Aufnahmen werden ersetzt, nicht geändert")
    aufnehmen(ordner, uhr, llm_ausfall=args.llm_ausfall)
    freigeben(ordner)
    print(f"Aufnahme freigegeben: {ordner.relative_to(WURZEL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
