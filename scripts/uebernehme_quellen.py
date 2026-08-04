#!/usr/bin/env python3
"""Bestandene Kandidaten in die Konfiguration uebernehmen.

Nimmt die JSON-Ausgabe von `scripts/pruefe_quellenvorschlag.py --json` und
traegt AUSSCHLIESSLICH die Eintraege mit `bestanden: true` ein. Was den
Abnahme-Check nicht bestanden hat, kommt hier gar nicht erst an - das ist der
ganze Punkt der Trennung: der vorschlagende Agent ist der Anwalt, das
Pruefskript der Skeptiker, und dieses Skript nur noch der Schreiber.

Wohin welcher Kandidat geht
---------------------------
  Fachpresse            -> config/news_sources.yaml
  Themenquelle          -> config/tech_sources.yaml (unter ihr Themenfeld)
  Zweitkanal eines
  bestehenden Betreibers-> config/watchlist.yaml, in dessen sources-Liste
  neuer Betreiber       -> config/watchlist_extra.yaml (wird nach Regionen
                           mit der Watchlist verschmolzen; die gepflegte
                           Hauptdatei bleibt damit lesbar)

Jeder Eintrag bekommt `herkunft` und `abgenommen` - ohne die weiss bei 1000
Quellen in sechs Monaten niemand mehr, woher eine Quelle kam. Die Begruendung
steht als deutscher Kommentar darueber.

Sicherheitsnetz: nach dem Schreiben wird die Konfiguration neu geladen und
gezaehlt. Stimmt die Zahl nicht, werden ALLE Dateien aus dem Backup
zurueckgeholt und das Skript bricht ab. Eine kaputte Watchlist ist teurer als
jede fehlende Quelle.

    python scripts/uebernehme_quellen.py ergebnis.json --herkunft "Welle 1"
    python scripts/uebernehme_quellen.py ergebnis.json --probe
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.config import load_config  # noqa: E402
from telco_radar.models import normalize_url  # noqa: E402

# Themenschluessel, die es in config/tech_sources.yaml schon gibt oder die
# dort angelegt werden duerfen. Ein Kandidat mit einem anderen Thema wird
# abgelehnt statt still in ein falsches Feld gelegt.
THEMEN_TITEL = {
    "ki": "KI-Anbieter",
    "geraete": "Geräte",
    "chips": "Chips & Modems",
    "netzausruester": "Netzausrüster",
    "satellit": "Satellit & NTN",
    "regulierung": "Regulierung & Verbände",
    "infrastruktur": "Türme, Glasfaser & Rechenzentren",
    "plattformen": "eSIM-, MVNO- & Kommunikationsplattformen",
}


def _yaml_wert(v) -> str:
    """Ein YAML-Skalar so schreiben, dass es sicher wieder eingelesen wird.

    Zeichenketten IMMER in Anfuehrungszeichen: die Eintraege stehen im
    Fluss-Stil ({name: ..., url: ...}), und dort beendet ein Fragezeichen
    oder Komma in einer URL das Mapping. Genau daran ist der erste Versuch
    gescheitert - abgefangen vom Sicherheitsnetz, aber vermeidbar. JSON ist
    hier zugleich gueltiges YAML mit doppelten Anfuehrungszeichen.
    """
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    return yaml.safe_dump(v, allow_unicode=True, default_flow_style=True,
                          width=10_000).strip().removesuffix("...").strip()


def _felder(e: dict, herkunft: str, datum: str) -> dict:
    """Die Collector-Felder eines Kandidaten, ohne die leeren."""
    felder = {"type": e.get("type", "rss"), "url": e["url"]}
    for schluessel in ("item_selector", "link_template", "headers",
                       "exclude_url_pattern", "timeout_seconds"):
        if e.get(schluessel):
            felder[schluessel] = e[schluessel]
    if e.get("allow_short_titles"):
        felder["allow_short_titles"] = True
    felder["herkunft"] = e.get("herkunft") or herkunft
    felder["abgenommen"] = datum
    return felder


def _kommentar(e: dict, einzug: str) -> list[str]:
    """Deutscher Begruendungskommentar, umgebrochen."""
    text = " ".join(str(e.get("begruendung") or "").split())
    if not text.endswith("."):
        text += "."
    if e.get("ausnahme_domain"):
        text += f" Fremddomain: {e['ausnahme_domain']}."
    if e.get("ausnahme_frische"):
        text += f" Frische-Ausnahme: {e['ausnahme_frische']}."
    text += (f" Abnahme: {e.get('n_items', 0)} Meldungen, "
             f"{e.get('n_datiert', 0)} datiert, {e.get('n_frisch', 0)} im "
             f"Frischefenster.")
    zeilen, aktuell = [], f"{einzug}#"
    for wort in text.split():
        if len(aktuell) + len(wort) + 1 > 78:
            zeilen.append(aktuell)
            aktuell = f"{einzug}#"
        aktuell += " " + wort
    zeilen.append(aktuell)
    return zeilen


# --------------------------------------------------------------- Fachpresse
def fachpresse(pfad: Path, eintraege: list[dict], herkunft: str,
               datum: str) -> int:
    if not eintraege:
        return 0
    text = pfad.read_text(encoding="utf-8").rstrip("\n")
    zeilen = [text, f"  # ---- {herkunft}, abgenommen {datum}"]
    for e in eintraege:
        zeilen.extend(_kommentar(e, "  "))
        felder = {"name": e.get("bezeichnung") or e.get("name") or e["url"],
                  **_felder(e, herkunft, datum)}
        inhalt = ", ".join(f"{k}: {_yaml_wert(v)}"
                           for k, v in felder.items())
        zeilen.append(f"  - {{{inhalt}}}")
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return len(eintraege)


# ------------------------------------------------------------ Themenquellen
def themenquellen(pfad: Path, nach_thema: dict[str, list[dict]],
                  herkunft: str, datum: str) -> int:
    if not nach_thema:
        return 0
    zeilen = pfad.read_text(encoding="utf-8").split("\n")
    geschrieben = 0
    for thema, eintraege in nach_thema.items():
        # Fluss-Stil mit 6 Zeichen Einzug - genau wie der Bestand in dieser
        # Datei. Eine zweite Schreibweise waere zwar gueltiges YAML, macht die
        # Datei aber unlesbar, und gelesen wird sie von Menschen.
        block: list[str] = [f"      # ---- {herkunft}, abgenommen {datum}"]
        for e in eintraege:
            block.extend(_kommentar(e, "      "))
            felder = {"name": e.get("bezeichnung") or e["url"],
                      **_felder(e, herkunft, datum)}
            inhalt = ", ".join(f"{k}: {_yaml_wert(v)}" for k, v in felder.items())
            block.append(f"      - {{{inhalt}}}")
            geschrieben += 1

        marke = f"  {thema}:"
        if marke in zeilen:
            # Ende der quellen-Liste dieses Themas suchen: die letzte Zeile,
            # die tiefer eingerueckt ist als der Themenschluessel.
            start = zeilen.index(marke)
            ende = start + 1
            while ende < len(zeilen) and (not zeilen[ende].strip()
                                          or zeilen[ende].startswith("   ")):
                ende += 1
            zeilen[ende:ende] = block
        else:
            zeilen.append(f"  {thema}:")
            zeilen.append(f"    name: {_yaml_wert(THEMEN_TITEL[thema])}")
            zeilen.append("    quellen:")
            zeilen.extend(block)
    pfad.write_text("\n".join(zeilen).rstrip("\n") + "\n", encoding="utf-8")
    return geschrieben


# --------------------------------------------------------- Zweitkanaele
def zweitkanaele(pfad: Path, nach_operator: dict[str, list[dict]],
                 herkunft: str, datum: str) -> int:
    if not nach_operator:
        return 0
    zeilen = pfad.read_text(encoding="utf-8").split("\n")
    geschrieben = 0
    for operator, eintraege in nach_operator.items():
        marke = f"    - name: {operator}"
        if marke not in zeilen:
            print(f"  ! {operator} steht nicht in der Watchlist - "
                  f"{len(eintraege)} Kanal/Kanaele uebersprungen")
            continue
        start = zeilen.index(marke)
        # sources: dieses Betreibers finden
        quelle_zeile = None
        for i in range(start + 1, len(zeilen)):
            if zeilen[i].startswith("    - name: ") or \
                    (zeilen[i] and not zeilen[i].startswith("     ")
                     and not zeilen[i].startswith("      ")):
                break
            if zeilen[i].strip() == "sources:":
                quelle_zeile = i
                break
        if quelle_zeile is None:
            print(f"  ! {operator} hat keinen sources-Block - uebersprungen")
            continue
        ende = quelle_zeile + 1
        while ende < len(zeilen) and (not zeilen[ende].strip()
                                      or zeilen[ende].startswith("      ")):
            ende += 1

        block: list[str] = [f"      # ---- {herkunft}, abgenommen {datum}"]
        for e in eintraege:
            block.extend(_kommentar(e, "      "))
            felder = _felder(e, herkunft, datum)
            block.append(f"      - type: {_yaml_wert(felder.pop('type'))}")
            for k, v in felder.items():
                block.append(f"        {k}: {_yaml_wert(v)}")
            if e.get("label") or e.get("kanal"):
                block.append(f"        label: "
                             f"{_yaml_wert(e.get('label') or e['kanal'])}")
            geschrieben += 1
        zeilen[ende:ende] = block
    pfad.write_text("\n".join(zeilen).rstrip("\n") + "\n", encoding="utf-8")
    return geschrieben


# ------------------------------------------------------- neue Betreiber
def neue_betreiber(pfad: Path, eintraege: list[dict], herkunft: str,
                   datum: str) -> int:
    if not eintraege:
        return 0
    roh = yaml.safe_load(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}
    regionen = (roh or {}).get("regions") or {}
    if not isinstance(regionen, dict):
        regionen = {}
    nach_name: dict[str, dict] = {
        op["name"]: op
        for r in regionen.values() for op in (r.get("operators") or [])
    }
    for e in eintraege:
        region = e.get("region") or "europe"
        name = e.get("operator") or e.get("bezeichnung") or e["url"]
        eintrag = nach_name.get(name)
        if eintrag is None:
            eintrag = {"name": name, "country": e.get("country", ""),
                       "website": e.get("website", ""),
                       "aliases": e.get("aliases") or [], "sources": []}
            nach_name[name] = eintrag
            regionen.setdefault(region, {"operators": []})
            regionen[region].setdefault("operators", []).append(eintrag)
        eintrag["sources"].append(_felder(e, herkunft, datum))
    kopf = (
        "# Zusaetzliche Betreiber. Wird von config.load_config nach "
        "Regionsschluessel\n"
        "# mit config/watchlist.yaml verschmolzen. Neue Betreiber kommen "
        "hierher,\n"
        "# damit die gepflegte Hauptdatei lesbar bleibt; Zweitkanaele "
        "bestehender\n"
        "# Betreiber gehoeren dagegen in die Watchlist, direkt zu ihrem "
        "Betreiber.\n"
        "# Erzeugt/erweitert von scripts/uebernehme_quellen.py.\n"
    )
    pfad.write_text(kopf + yaml.safe_dump({"regions": regionen},
                                          allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return len(eintraege)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ergebnis", type=Path, help="JSON aus dem Abnahme-Check")
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--herkunft", default="Breitensuche",
                   help="Herkunftsvermerk je Quelle (z. B. 'Welle 1')")
    p.add_argument("--datum", default=date.today().isoformat())
    p.add_argument("--probe", action="store_true", help="nichts schreiben")
    args = p.parse_args(argv)

    root = args.root.resolve()
    cfg_dir = root / "config"
    alle = json.loads(args.ergebnis.read_text(encoding="utf-8"))
    bestanden = [e for e in alle if e.get("bestanden")]
    print(f"{len(bestanden)} von {len(alle)} Kandidaten bestanden")

    vorher = load_config(root)
    bekannt = {normalize_url(s.url) for s, _, _ in vorher.alle_quellen}
    operatoren = {op.name for op in vorher.operators}

    presse: list[dict] = []
    themen: dict[str, list[dict]] = defaultdict(list)
    kanaele: dict[str, list[dict]] = defaultdict(list)
    neue: list[dict] = []
    for e in bestanden:
        if normalize_url(e["url"]) in bekannt:
            print(f"  = schon konfiguriert: {e['url']}")
            continue
        bekannt.add(normalize_url(e["url"]))
        thema = (e.get("thema") or "").strip()
        if thema == "fachpresse":
            presse.append(e)
        elif thema:
            if thema not in THEMEN_TITEL:
                print(f"  ! unbekanntes Thema {thema!r}: {e['url']}")
                continue
            themen[thema].append(e)
        elif e.get("operator") in operatoren:
            kanaele[e["operator"]].append(e)
        elif e.get("operator"):
            neue.append(e)
        else:
            print(f"  ! weder Thema noch Betreiber: {e['url']}")

    print(f"  Fachpresse            {len(presse)}")
    print(f"  Themenquellen         {sum(len(v) for v in themen.values())} "
          f"in {len(themen)} Themenfeld(ern)")
    print(f"  Zweitkanaele          {sum(len(v) for v in kanaele.values())} "
          f"bei {len(kanaele)} Betreiber(n)")
    print(f"  neue Betreiber        {len(neue)}")
    if args.probe:
        return 0

    dateien = ["news_sources.yaml", "tech_sources.yaml", "watchlist.yaml",
               "watchlist_extra.yaml"]
    sicherung = {n: (cfg_dir / n).read_text(encoding="utf-8")
                 for n in dateien if (cfg_dir / n).exists()}

    geschrieben = 0
    try:
        geschrieben += fachpresse(cfg_dir / "news_sources.yaml", presse,
                                  args.herkunft, args.datum)
        geschrieben += themenquellen(cfg_dir / "tech_sources.yaml", themen,
                                     args.herkunft, args.datum)
        geschrieben += zweitkanaele(cfg_dir / "watchlist.yaml", kanaele,
                                    args.herkunft, args.datum)
        geschrieben += neue_betreiber(cfg_dir / "watchlist_extra.yaml", neue,
                                      args.herkunft, args.datum)
        nachher = load_config(root)
        neu_gezaehlt = len(list(nachher.alle_quellen)) - len(list(vorher.alle_quellen))
        if neu_gezaehlt != geschrieben:
            raise RuntimeError(
                f"{geschrieben} Quellen geschrieben, aber {neu_gezaehlt} in "
                f"der neu geladenen Konfiguration - die Dateien werden "
                f"zurueckgesetzt")
    except Exception as exc:  # noqa: BLE001
        for name, inhalt in sicherung.items():
            (cfg_dir / name).write_text(inhalt, encoding="utf-8")
        print(f"ABBRUCH: {exc}")
        print("Alle Konfigurationsdateien wurden zurueckgesetzt.")
        return 1

    print(f"\n{geschrieben} Quellen uebernommen. "
          f"Konfiguration laedt: {len(list(nachher.alle_quellen))} Quellen "
          f"({len(nachher.operators)} Betreiber, "
          f"{len(nachher.news_sources)} Fachpresse, "
          f"{len(nachher.tech_sources)} Themenquellen).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
