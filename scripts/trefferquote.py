#!/usr/bin/env python3
"""Trefferquote je Quelle - ausgewertet ueber das vorhandene Berichtsarchiv.

Warum es diese Zahl gibt
------------------------
"Meldungen je Quelle" sagt nur, wie VIEL eine Quelle liefert. Gemessen an
Lauf #67 liefern Betreiber (15,9), Themenfelder (18,6) und Fachpresse (17,6)
praktisch dasselbe - die Zahl taugt also nicht, um zu entscheiden, welche Art
von Quelle den Ausbau verdient. Was fehlt, ist die zweite Zahl: wie viel von
dem, was eine Quelle liefert, ueberhaupt bewertet wird und wie viel davon im
Wochenbericht landet. Genau die baut dieses Skript.

Datengrundlage sind ausschliesslich `data/reports/*.json`, also bereits
gelaufene Laeufe - es wird nichts neu gesammelt und kein Modell aufgerufen.
Je Lauf stehen dort:

  run.sources[]      Status, Zahl gesammelter (und ab Lauf #68 auch neuer)
                     Meldungen je Quelle
  regions[].highlights[]  die BEWERTETEN Meldungen mit Relevanz und Quelle
  briefing_md        der Wochenbericht - eine Meldung gilt als "im Bericht",
                     wenn ihre URL dort verlinkt ist

Zuordnungsgenauigkeit
---------------------
Ab Lauf #68 tragen Meldungen und Highlights `source_url`, also den KANAL.
Aeltere Berichte kennen nur `source` (bei Betreibern der Firmenname). Fuer
diese Laeufe wird ueber den Namen zugeordnet, und zwar nur, wenn der Name im
Lauf eindeutig zu genau einer Quellen-URL gehoert; sonst laeuft die Quelle
unter dem Sammelschluessel `name:<Firma>`. Betreiber mit mehreren Kanaelen
sind in den Altdaten damit nicht trennbar - die Ausgabe weist das je Zeile
mit `~` aus, statt es zu verschweigen.

Aufruf:
    python scripts/trefferquote.py                 # Markdown-Tabelle
    python scripts/trefferquote.py --json data/state/trefferquote.json
    python scripts/trefferquote.py --sortiere bericht --min-laeufe 3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.config import load_config  # noqa: E402
from telco_radar.models import normalize_url  # noqa: E402


@dataclass
class Quellenbilanz:
    """Was eine Quelle ueber alle ausgewerteten Laeufe hinweg geleistet hat."""

    schluessel: str
    name: str = ""
    url: str = ""
    origin: str = ""
    kind: str = ""
    region: str = ""
    laeufe: int = 0
    ok: int = 0
    leer: int = 0
    fehler: int = 0
    gesammelt: int = 0
    neu: int = 0              # nur aus Laeufen, die "new" je Quelle kennen
    laeufe_mit_neu: int = 0   # wie viele Laeufe diese Zahl liefern
    bewertet: int = 0
    rel3: int = 0
    rel4: int = 0
    im_bericht: int = 0
    unscharf: bool = False    # ueber den Namen zugeordnet, nicht ueber die URL
    in_config: bool = False
    letzter_erfolg: str = ""  # Datum des letzten Laufs mit status ok

    @property
    def bewertungsquote(self) -> float:
        """Anteil der gesammelten Meldungen, den ein Analyst bewertet hat."""
        return self.bewertet / self.gesammelt if self.gesammelt else 0.0

    @property
    def berichtsquote(self) -> float:
        """Anteil der gesammelten Meldungen, der im Wochenbericht landet."""
        return self.im_bericht / self.gesammelt if self.gesammelt else 0.0

    @property
    def bewertet_je_lauf(self) -> float:
        return self.bewertet / self.laeufe if self.laeufe else 0.0

    @property
    def bericht_je_lauf(self) -> float:
        return self.im_bericht / self.laeufe if self.laeufe else 0.0

    @property
    def gesammelt_je_lauf(self) -> float:
        return self.gesammelt / self.laeufe if self.laeufe else 0.0

    @property
    def ausfallquote(self) -> float:
        return (self.leer + self.fehler) / self.laeufe if self.laeufe else 0.0


_URL_IN_MARKDOWN = re.compile(r"\((https?://[^)\s]+)\)")


def _berichtete_urls(briefing: str) -> set[str]:
    """Alle im Wochenbericht verlinkten Quellen-URLs, normalisiert."""
    return {normalize_url(u) for u in _URL_IN_MARKDOWN.findall(briefing or "")}


def _lauf_dateien(reports_dir: Path) -> list[Path]:
    return sorted(p for p in reports_dir.glob("*.json") if p.is_file())


def _schluessel(url: str) -> str:
    return normalize_url(url) if url else ""


def auswerten(reports_dir: Path, config_urls: dict[str, dict] | None = None,
              ab: str = "") -> tuple[dict[str, Quellenbilanz], list[dict]]:
    """Alle Berichte einlesen und je Quelle aufsummieren.

    `ab` blendet Laeufe vor diesem Datum aus. Das ist kein Komfortschalter:
    bis zum 21.07.2026 lief eine Keyword-Nachrichtensuche mit, deren Treffer
    ("Yahoo Finance", "NZ Herald") zu keiner heutigen Quelle gehoeren. Sie
    stehen in den alten Berichten als bewertete Meldungen und wuerden die
    Bilanz der echten Quellen verwaessern.

    Liefert (Bilanzen, Lauf-Uebersicht).
    """
    bilanzen: dict[str, Quellenbilanz] = {}
    laeufe: list[dict] = []

    def bilanz(schluessel: str) -> Quellenbilanz:
        if schluessel not in bilanzen:
            bilanzen[schluessel] = Quellenbilanz(schluessel=schluessel)
        return bilanzen[schluessel]

    for pfad in _lauf_dateien(reports_dir):
        try:
            bericht = json.loads(pfad.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  ! {pfad.name} nicht lesbar: {exc}", file=sys.stderr)
            continue
        run = bericht.get("run") or {}
        quellen = run.get("sources") or []
        if not quellen:
            # Sehr alte Berichte ohne Laufprotokoll - fuer die Trefferquote
            # unbrauchbar, weil der Nenner fehlt.
            continue

        datum = bericht.get("date", pfad.stem)
        if ab and datum < ab:
            continue

        # Name -> URL, aber nur wo eindeutig. Ein Betreiber mit zwei Kanaelen
        # laesst sich in Altdaten nicht aufloesen; das wird spaeter als
        # "unscharf" ausgewiesen statt stillschweigend auf einen Kanal geraten.
        namen: dict[str, set[str]] = defaultdict(set)
        for rec in quellen:
            namen[rec.get("name", "")].add(_schluessel(rec.get("url", "")))
        eindeutig = {n: next(iter(u)) for n, u in namen.items() if len(u) == 1}

        for rec in quellen:
            sch = _schluessel(rec.get("url", "")) or f"name:{rec.get('name', '')}"
            b = bilanz(sch)
            if rec.get("status") == "quarantaene":
                # Stillgelegt und deshalb gar nicht abgerufen. Das als Fehler
                # zu zaehlen wuerde die Quarantaene zur selbsterfuellenden
                # Prophezeiung machen: je laenger eine Quelle ruht, desto
                # schlechter saehe ihre Bilanz aus.
                continue
            b.name = rec.get("name") or b.name
            b.url = rec.get("url") or b.url
            b.origin = rec.get("origin") or b.origin
            b.kind = rec.get("kind") or b.kind
            b.region = rec.get("region") or b.region
            b.laeufe += 1
            status = rec.get("status")
            if status == "ok":
                b.ok += 1
                b.letzter_erfolg = max(b.letzter_erfolg, datum)
            elif status == "empty":
                b.leer += 1
            else:
                b.fehler += 1
            b.gesammelt += int(rec.get("count") or 0)
            if "new" in rec:
                b.neu += int(rec.get("new") or 0)
                b.laeufe_mit_neu += 1

        berichtet = _berichtete_urls(bericht.get("briefing_md", ""))
        bewertet_im_lauf = 0
        for region in (bericht.get("regions") or {}).values():
            for h in region.get("highlights") or []:
                if h.get("relevance") is None:
                    continue  # Roh-Digest-Lauf: nichts wurde wirklich bewertet
                bewertet_im_lauf += 1
                quell_url = _schluessel(h.get("source_url", ""))
                unscharf = False
                if not quell_url:
                    quell_url = eindeutig.get(h.get("source", ""), "")
                    unscharf = True
                sch = quell_url or f"name:{h.get('source', '')}"
                b = bilanz(sch)
                if unscharf:
                    b.unscharf = True
                b.bewertet += 1
                try:
                    rel = int(h.get("relevance") or 0)
                except (TypeError, ValueError):
                    rel = 0
                if rel >= 3:
                    b.rel3 += 1
                if rel >= 4:
                    b.rel4 += 1
                if normalize_url(h.get("url", "")) in berichtet:
                    b.im_bericht += 1

        laeufe.append({
            "datum": datum,
            "quellen": len(quellen),
            "gesammelt": (bericht.get("stats") or {}).get("collected", 0),
            "neu": (bericht.get("stats") or {}).get("new", 0),
            "bewertet": bewertet_im_lauf,
            "im_bericht": len(berichtet),
            "sekunden": run.get("duration_seconds"),
        })

    if config_urls:
        for b in bilanzen.values():
            treffer = config_urls.get(b.schluessel)
            if treffer:
                b.in_config = True
                b.name = b.name or treffer.get("name", "")
                b.origin = b.origin or treffer.get("origin", "")
    return bilanzen, laeufe


def config_quellen(root: Path) -> dict[str, dict]:
    """Alle heute konfigurierten Quellen, nach normalisierter URL."""
    cfg = load_config(root)
    out: dict[str, dict] = {}
    for op in cfg.operators:
        for src in op.crawled_sources:
            out[_schluessel(src.url)] = {
                "name": op.name, "origin": "operator",
                "region": op.region_key, "kind": src.kind}
    for src in cfg.news_sources:
        out[_schluessel(src.url)] = {
            "name": src.name, "origin": "industry_news",
            "region": "global", "kind": src.kind}
    for src in cfg.tech_sources:
        if src.crawlable:
            out[_schluessel(src.url)] = {
                "name": src.name, "origin": "tech_watch",
                "region": src.theme, "kind": src.kind}
    return out


SORTIERUNGEN = {
    "bericht": lambda b: (-b.bericht_je_lauf, -b.bewertet_je_lauf),
    "bewertet": lambda b: (-b.bewertet_je_lauf, -b.bericht_je_lauf),
    "quote": lambda b: (-b.bewertungsquote, -b.bewertet_je_lauf),
    "gesammelt": lambda b: -b.gesammelt_je_lauf,
    "ausfall": lambda b: (-b.ausfallquote, -b.laeufe),
}

ORIGIN_LABEL = {
    "operator": "Betreiber",
    "industry_news": "Fachpresse",
    "tech_watch": "Themenfeld",
}


def markdown(bilanzen: dict[str, Quellenbilanz], laeufe: list[dict],
             sortierung: str, min_laeufe: int, top: int | None,
             nur_config: bool) -> str:
    reihen = [b for b in bilanzen.values() if b.laeufe >= min_laeufe]
    if nur_config:
        reihen = [b for b in reihen if b.in_config]
    reihen.sort(key=SORTIERUNGEN[sortierung])

    zeilen: list[str] = []
    zeilen.append("# Trefferquote je Quelle")
    zeilen.append("")
    zeilen.append(f"Ausgewertet: {len(laeufe)} Laeufe "
                  f"({laeufe[0]['datum']} bis {laeufe[-1]['datum']}), "
                  f"{len(bilanzen)} Quellen." if laeufe else "Keine Laeufe.")
    zeilen.append("")
    zeilen.append("`~` heisst: in mindestens einem Lauf nur ueber den "
                  "Quellennamen zugeordnet (Altdaten ohne `source_url`), "
                  "mehrere Kanaele desselben Betreibers sind dort "
                  "zusammengefasst.")
    zeilen.append("")

    # --------------------------------------------------- nicht zuordenbar
    # Bewertete Meldungen, deren Quellenname in keinem Lauf zu einer
    # abgefragten Quelle gehoert. Ueberwiegend Reste der 2026 entfernten
    # Keyword-Nachrichtensuche. Sie hier auszuweisen statt still zu
    # verschlucken ist der Unterschied zwischen einer Messung und einer Zahl.
    waisen = [b for b in bilanzen.values() if b.laeufe == 0 and b.bewertet]
    if waisen:
        summe = sum(b.bewertet for b in waisen)
        alle_bewertet = sum(b.bewertet for b in bilanzen.values())
        zeilen.append("## Nicht zuordenbar")
        zeilen.append("")
        zeilen.append(
            f"{summe} von {alle_bewertet} bewerteten Meldungen "
            f"({summe / max(1, alle_bewertet) * 100:.0f} %) lassen sich keiner "
            "abgefragten Quelle zuordnen - ihr Quellenname taucht im "
            "Laufprotokoll nicht auf. Das sind fast ausschliesslich Treffer "
            "der 2026 entfernten Keyword-Nachrichtensuche. Mit `--ab` lassen "
            "sich die betroffenen Laeufe ausblenden.")
        zeilen.append("")
        zeilen.append("| Name | bewertet | im Bericht |")
        zeilen.append("|---|---:|---:|")
        for b in sorted(waisen, key=lambda b: -b.bewertet)[:15]:
            zeilen.append(f"| {b.schluessel.removeprefix('name:') or '(leer)'} "
                          f"| {b.bewertet} | {b.im_bericht} |")
        zeilen.append("")

    # ------------------------------------------------ Ebenen im Vergleich
    ebenen: dict[str, list[Quellenbilanz]] = defaultdict(list)
    for b in reihen:
        ebenen[b.origin or "?"].append(b)
    zeilen.append("## Ebenen im Vergleich")
    zeilen.append("")
    zeilen.append("| Ebene | Quellen | gesammelt/Lauf | bewertet/Lauf | "
                  "im Bericht/Lauf | Bewertungsquote |")
    zeilen.append("|---|---:|---:|---:|---:|---:|")
    for origin, gruppe in sorted(ebenen.items(),
                                 key=lambda kv: -len(kv[1])):
        n = len(gruppe)
        ges = sum(b.gesammelt_je_lauf for b in gruppe)
        bew = sum(b.bewertet_je_lauf for b in gruppe)
        ber = sum(b.bericht_je_lauf for b in gruppe)
        quote = (sum(b.bewertet for b in gruppe)
                 / max(1, sum(b.gesammelt for b in gruppe)))
        zeilen.append(f"| {ORIGIN_LABEL.get(origin, origin)} | {n} | "
                      f"{ges / n:.1f} | {bew / n:.2f} | {ber / n:.2f} | "
                      f"{quote * 100:.1f} % |")
    zeilen.append("")

    # ------------------------------------------------------ Einzelquellen
    zeilen.append(f"## Quellen, sortiert nach `{sortierung}`")
    zeilen.append("")
    zeilen.append("| # | Quelle | Ebene | Laeufe | gesammelt/Lauf | "
                  "bewertet/Lauf | Bericht/Lauf | Bew.quote | rel>=4 | "
                  "leer+Fehler | URL |")
    zeilen.append("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for i, b in enumerate(reihen if top is None else reihen[:top], 1):
        zeilen.append(
            f"| {i} | {b.name}{' ~' if b.unscharf else ''} | "
            f"{ORIGIN_LABEL.get(b.origin, b.origin)} | {b.laeufe} | "
            f"{b.gesammelt_je_lauf:.1f} | {b.bewertet_je_lauf:.2f} | "
            f"{b.bericht_je_lauf:.2f} | {b.bewertungsquote * 100:.1f} % | "
            f"{b.rel4} | {b.leer + b.fehler} | `{b.url[:70]}` |")
    zeilen.append("")

    # ------------------------------------------------------------ Ballast
    ballast = [b for b in reihen if b.laeufe >= max(3, min_laeufe)
               and b.im_bericht == 0]
    zeilen.append("## Ballast-Kandidaten")
    zeilen.append("")
    zeilen.append("Quellen, die in **keinem** ausgewerteten Lauf eine Meldung "
                  "in den Wochenbericht gebracht haben. Das ist noch kein "
                  "Loeschgrund - eine IR-Seite meldet selten -, aber die "
                  "Liste, die man vor dem naechsten Ausbau ansieht.")
    zeilen.append("")
    zeilen.append("| Quelle | Ebene | Laeufe | gesammelt/Lauf | bewertet | URL |")
    zeilen.append("|---|---|---:|---:|---:|---|")
    for b in sorted(ballast, key=lambda b: -b.gesammelt_je_lauf):
        zeilen.append(f"| {b.name} | {ORIGIN_LABEL.get(b.origin, b.origin)} | "
                      f"{b.laeufe} | {b.gesammelt_je_lauf:.1f} | "
                      f"{b.bewertet} | `{b.url[:70]}` |")
    zeilen.append("")
    return "\n".join(zeilen)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--sortiere", choices=sorted(SORTIERUNGEN),
                   default="bericht")
    p.add_argument("--min-laeufe", type=int, default=1)
    p.add_argument("--ab", default="",
                   help="nur Laeufe ab diesem Datum (JJJJ-MM-TT)")
    p.add_argument("--top", type=int, default=None)
    p.add_argument("--nur-config", action="store_true",
                   help="nur Quellen, die heute noch konfiguriert sind")
    p.add_argument("--json", type=Path, default=None,
                   help="Bilanzen zusaetzlich als JSON schreiben")
    p.add_argument("--out", type=Path, default=None,
                   help="Markdown-Bericht in diese Datei schreiben")
    args = p.parse_args(argv)

    root = args.root.resolve()
    cfg_urls = config_quellen(root)
    bilanzen, laeufe = auswerten(root / "data" / "reports", cfg_urls, args.ab)
    if not laeufe:
        print("Keine auswertbaren Laeufe gefunden.", file=sys.stderr)
        return 1

    text = markdown(bilanzen, laeufe, args.sortiere, args.min_laeufe,
                    args.top, args.nur_config)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"geschrieben: {args.out}")
    else:
        print(text)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        nutzlast = {
            "laeufe": laeufe,
            "quellen": [
                {**asdict(b),
                 "bewertungsquote": round(b.bewertungsquote, 4),
                 "berichtsquote": round(b.berichtsquote, 4),
                 "bewertet_je_lauf": round(b.bewertet_je_lauf, 3),
                 "bericht_je_lauf": round(b.bericht_je_lauf, 3),
                 "gesammelt_je_lauf": round(b.gesammelt_je_lauf, 2)}
                for b in sorted(bilanzen.values(),
                                key=SORTIERUNGEN[args.sortiere])
            ],
        }
        args.json.write_text(
            json.dumps(nutzlast, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"geschrieben: {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
