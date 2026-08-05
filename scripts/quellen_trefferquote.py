#!/usr/bin/env python3
"""Trefferquote je Quelle - ausgewertet ueber das vorhandene Berichtsarchiv.

Warum es das gibt (AUFTRAG_SKALIERUNG_1000.md Abschnitt 4): "Meldungen je
Quelle" sagt nur, wie VIEL eine Quelle liefert, nicht wie viel davon taugt.
Ohne die zweite Zahl ist ein Ausbau auf 1000 Quellen blind - man wuerde in
Kategorien investieren, von denen niemand weiss, ob sie je im Bericht landen.

Gemessen wird je Quelle ueber alle Laeufe in data/reports/*.json:

    gesammelt    Summe der "count"-Werte aus dem Laufprotokoll
    bewertet     Meldungen, die ein Analyst ueberhaupt aufgenommen hat
                 (jedes Highlight in report["regions"][*]["highlights"])
    rel>=3/4     davon mit der jeweiligen Dringlichkeit
    im Bericht   Highlights, deren URL im Prosa-Wochenbericht auftaucht
    leer/Fehler  Laeufe mit status "empty" bzw. "fail"

    Trefferquote = bewertet / gesammelt

GRENZE DER RUECKSCHAU, ausdruecklich benannt: bis einschliesslich Lauf #67
tragen die Meldungen nur den ANZEIGENAMEN ihrer Quelle (Item.source_name =
Betreibername), nicht deren URL. Ein Betreiber mit Newsroom UND Investor
Relations erscheint deshalb rueckwirkend als EINE Quelle. Ab dem naechsten
Lauf stempelt collect/__init__.py jede Meldung mit source_url, dann rechnet
dieses Skript automatisch je Kanal (Spalte "Kanaele" zeigt, wie viele
zusammengefasst wurden).

Aufruf:
    python scripts/quellen_trefferquote.py                    # Tabelle nach stdout
    python scripts/quellen_trefferquote.py --md outputs/x.md  # Markdown-Bericht
    python scripts/quellen_trefferquote.py --json data/state/trefferquote.json
    python scripts/quellen_trefferquote.py --min-laeufe 3     # nur belastbare Zeilen
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Quellenbilanz:
    """Was ein einzelner Kanal (oder Anzeigename) ueber alle Laeufe geliefert hat."""

    schluessel: str
    anzeigename: str = ""
    origin: str = ""
    kind: str = ""
    region: str = ""
    urls: set[str] = field(default_factory=set)
    laeufe: int = 0
    laeufe_ok: int = 0
    laeufe_leer: int = 0
    laeufe_fehler: int = 0
    gesammelt: int = 0
    neu: int = 0
    bewertet: int = 0
    rel3: int = 0
    rel4: int = 0
    im_bericht: int = 0
    # Kam `neu` aus dem Laufprotokoll (ab Lauf #68) oder aus dem Altbestand des
    # Seen-Stores? Nur der erste Weg rechnet je Lauf und je Kanal.
    neu_aus_protokoll: bool = False

    @property
    def trefferquote(self) -> float | None:
        """Anteil der NEUEN Meldungen, die ein Analyst aufgenommen hat.

        Der Nenner ist bewusst `neu` und nicht `gesammelt`: ein Newsroom
        liefert bei jedem Abruf dieselben 30 Meldungen, ein schneller
        Fachpresse-Feed jedes Mal andere. Gegen `gesammelt` gerechnet wuerde
        die statische Seite bestraft, obwohl sie nichts falsch macht - die
        Kennzahl haette dann die Aktualisierungsfrequenz gemessen, nicht den
        Wert der Quelle.
        """
        if not self.neu:
            return None
        return self.bewertet / self.neu

    @property
    def berichtsquote(self) -> float | None:
        if not self.neu:
            return None
        return self.im_bericht / self.neu

    @property
    def neu_quote(self) -> float | None:
        """Wie viel eines Abrufs ueberhaupt neu ist - Mass fuer Leerlauf."""
        if not self.gesammelt:
            return None
        return self.neu / self.gesammelt

    @property
    def ausfallquote(self) -> float | None:
        if not self.laeufe:
            return None
        return (self.laeufe_leer + self.laeufe_fehler) / self.laeufe

    def als_dict(self) -> dict:
        d = asdict(self)
        d["urls"] = sorted(self.urls)
        d["kanaele"] = len(self.urls)
        d["trefferquote"] = self.trefferquote
        d["berichtsquote"] = self.berichtsquote
        d["neu_quote"] = self.neu_quote
        d["ausfallquote"] = self.ausfallquote
        return d


def _berichte_laden(reports_dir: Path) -> list[dict]:
    berichte = []
    for pfad in sorted(reports_dir.glob("*.json")):
        try:
            berichte.append(json.loads(pfad.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return berichte


def _hat_kanalzuordnung(bericht: dict) -> bool:
    """Traegt dieser Lauf die Quellen-URL je Highlight? (ab Lauf #68)"""
    for region in (bericht.get("regions") or {}).values():
        for h in region.get("highlights") or []:
            if h.get("source_url"):
                return True
    return False


def _verbuchen(bilanzen: dict[str, Quellenbilanz], bericht: dict,
               je_kanal: bool) -> None:
    """Einen Lauf in die Bilanzen einrechnen.

    je_kanal=False schluesselt nach Anzeigename (funktioniert ueber das ganze
    Archiv), je_kanal=True nach Quellen-URL (nur fuer Laeufe ab #68 moeglich).
    """
    lauf = bericht.get("run") or {}
    briefing = bericht.get("briefing_md") or ""

    def hole(schluessel: str, name: str) -> Quellenbilanz:
        if schluessel not in bilanzen:
            bilanzen[schluessel] = Quellenbilanz(schluessel=schluessel,
                                                 anzeigename=name)
        return bilanzen[schluessel]

    # --- Sammelseite: was das Laufprotokoll je Quelle festgehalten hat
    for eintrag in lauf.get("sources") or []:
        name = eintrag.get("name") or eintrag.get("url") or "?"
        url = eintrag.get("url") or ""
        if je_kanal and not url:
            continue
        b = hole(url if je_kanal else name, name)
        if url:
            b.urls.add(url)
        b.origin = eintrag.get("origin") or b.origin
        b.kind = eintrag.get("kind") or b.kind
        b.region = eintrag.get("region") or b.region
        b.laeufe += 1
        status = eintrag.get("status")
        if status == "ok":
            b.laeufe_ok += 1
        elif status == "empty":
            b.laeufe_leer += 1
        elif status == "fail":
            b.laeufe_fehler += 1
        b.gesammelt += int(eintrag.get("count") or 0)
        if "new" in eintrag:
            b.neu += int(eintrag.get("new") or 0)
            b.neu_aus_protokoll = True

    # --- Bewertungsseite: was ein Analyst daraus aufgenommen hat
    for region in (bericht.get("regions") or {}).values():
        for h in region.get("highlights") or []:
            name = h.get("source") or ""
            url = h.get("source_url") or ""
            if je_kanal and not url:
                continue
            if not je_kanal and not name:
                continue
            b = hole(url if je_kanal else name, name or url)
            b.bewertet += 1
            rel = h.get("relevance")
            if isinstance(rel, (int, float)):
                if rel >= 3:
                    b.rel3 += 1
                if rel >= 4:
                    b.rel4 += 1
            if h.get("url") and h["url"] in briefing:
                b.im_bericht += 1


def auswerten(berichte: list[dict]) -> tuple[dict[str, Quellenbilanz],
                                             dict[str, Quellenbilanz],
                                             list[str]]:
    """Alle Laeufe verdichten.

    Liefert (nach_name, nach_kanal, kanal_laeufe). `nach_name` deckt das ganze
    Archiv ab und ist deshalb die belastbare Tabelle; `nach_kanal` ist die
    feinere, aber nur ueber die Laeufe, die source_url je Highlight mitfuehren.
    Beides getrennt zu halten ist Absicht: eine Trefferquote, deren Zaehler aus
    anderen Laeufen stammt als ihr Nenner, waere schlicht falsch.
    """
    nach_name: dict[str, Quellenbilanz] = {}
    nach_kanal: dict[str, Quellenbilanz] = {}
    kanal_laeufe: list[str] = []

    for bericht in berichte:
        _verbuchen(nach_name, bericht, je_kanal=False)
        if _hat_kanalzuordnung(bericht):
            kanal_laeufe.append(bericht.get("date", "?"))
            _verbuchen(nach_kanal, bericht, je_kanal=True)

    return nach_name, nach_kanal, kanal_laeufe


def historie_ergaenzen(bilanzen: dict[str, Quellenbilanz],
                       historie_pfad: Path) -> int:
    """Fuer Quellen ohne `new` im Laufprotokoll den Altbestand nachtragen.

    Bis Lauf #67 hielt das Laufprotokoll nur fest, wie viele Meldungen eine
    Quelle GELIEFERT hat, nicht wie viele davon neu waren. Die Zahl steckte
    stattdessen im alten Seen-Store, den scripts/migriere_seen_store.py vor
    dem Formatwechsel einmal nach Quelle ausgewertet hat. Ohne diesen Nachtrag
    haette die Rueckschau ueber das vorhandene Archiv gar keinen Nenner.

    Grenze, die man kennen muss: die Historie liefert eine SUMME je Quelle
    ueber den ganzen Zeitraum, nicht je Lauf. Sie kann deshalb nur Quellen
    fuellen, fuer die noch KEIN Lauf `new` mitgeschrieben hat - sonst wuerden
    sich beide Quellen doppelt zaehlen.
    """
    if not historie_pfad.exists():
        return 0
    historie = {e["quelle"]: e
                for e in json.loads(historie_pfad.read_text(encoding="utf-8"))}
    ergaenzt = 0
    for b in bilanzen.values():
        if b.neu_aus_protokoll:
            continue
        eintrag = historie.get(b.anzeigename)
        if eintrag:
            b.neu += int(eintrag.get("neu_gesamt") or 0)
            ergaenzt += 1
    return ergaenzt


def _pct(wert: float | None) -> str:
    return "—" if wert is None else f"{wert * 100:4.1f} %"


def tabelle(bilanzen: dict[str, Quellenbilanz], min_laeufe: int = 1,
            grenze: int | None = None) -> list[Quellenbilanz]:
    zeilen = [b for b in bilanzen.values() if b.laeufe >= min_laeufe]
    zeilen.sort(key=lambda b: (-(b.trefferquote or -1), -b.gesammelt))
    return zeilen[:grenze] if grenze else zeilen


def markdown(zeilen: list[Quellenbilanz], berichte: list[dict],
             kanalzeilen: list[Quellenbilanz] | None = None,
             kanal_laeufe: list[str] | None = None) -> str:
    daten = [b.get("date", "?") for b in berichte]
    gesamt_gesammelt = sum(b.gesammelt for b in zeilen)
    gesamt_neu = sum(b.neu for b in zeilen)
    gesamt_bewertet = sum(b.bewertet for b in zeilen)
    gesamt_bericht = sum(b.im_bericht for b in zeilen)

    aus = [
        "# Trefferquote je Quelle",
        "",
        f"Ausgewertet ueber {len(berichte)} Laeufe "
        f"({daten[0] if daten else '?'} bis {daten[-1] if daten else '?'}).",
        "",
        f"- gesammelte Meldungen: **{gesamt_gesammelt}**",
        f"- davon neu (nach Seen-Store und Frischefenster): **{gesamt_neu}** "
        f"({_pct(gesamt_neu / gesamt_gesammelt if gesamt_gesammelt else None)})",
        f"- davon von einem Analysten bewertet: **{gesamt_bewertet}** "
        f"({_pct(gesamt_bewertet / gesamt_neu if gesamt_neu else None)} der neuen)",
        f"- davon im Prosa-Wochenbericht verlinkt: **{gesamt_bericht}** "
        f"({_pct(gesamt_bericht / gesamt_neu if gesamt_neu else None)} der neuen)",
        "",
        "> **Trefferquote = bewertet / NEU**, nicht / gesammelt. Ein Newsroom",
        "> liefert bei jedem Abruf dieselben 30 Meldungen, ein Fachpresse-Feed",
        "> jedes Mal andere - gegen „gesammelt\" gerechnet wuerde die Kennzahl die",
        "> Abrufhaeufigkeit messen statt den Wert der Quelle.",
        ">",
        "> Je ANZEIGENAME, nicht je Kanal: bis Lauf #67 trugen die Meldungen keine",
        "> Quellen-URL. Die Spalte „Kan.\" zeigt, wie viele Kanaele in einer Zeile",
        "> zusammengefasst sind. Die feinere Auswertung je Kanal steht unten und",
        "> deckt nur die Laeufe ab, die source_url mitfuehren.",
        "",
        "## Nach Ebene",
        "",
        "| Ebene | Quellen | gesammelt | neu | bewertet | Trefferquote | im Bericht |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    je_ebene: dict[str, list[Quellenbilanz]] = defaultdict(list)
    for b in zeilen:
        je_ebene[b.origin or "?"].append(b)
    for ebene, gruppe in sorted(je_ebene.items()):
        g = sum(x.gesammelt for x in gruppe)
        n = sum(x.neu for x in gruppe)
        bw = sum(x.bewertet for x in gruppe)
        ib = sum(x.im_bericht for x in gruppe)
        aus.append(f"| {ebene} | {len(gruppe)} | {g} | {n} | {bw} | "
                   f"{_pct(bw / n if n else None)} | {ib} |")

    aus += [
        "",
        "## Je Quelle",
        "",
        "| Quelle | Ebene | Kan. | Laeufe | gesammelt | neu | bewertet "
        "| Trefferquote | rel>=3 | im Bericht | leer/Fehler |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for b in zeilen:
        aus.append(
            f"| {b.anzeigename} | {b.origin} | {len(b.urls)} | {b.laeufe} | "
            f"{b.gesammelt} | {b.neu} | {b.bewertet} | {_pct(b.trefferquote)} | "
            f"{b.rel3} | {b.im_bericht} | {b.laeufe_leer}/{b.laeufe_fehler} |")

    MINDEST_NEU = 10
    tote = [b for b in zeilen if b.neu and not b.bewertet]
    belastbar = sorted([b for b in tote if b.neu >= MINDEST_NEU],
                       key=lambda x: -x.neu)
    duenn = sorted([b for b in tote if b.neu < MINDEST_NEU], key=lambda x: -x.neu)
    leere = [b for b in zeilen if not b.gesammelt]
    aus += [
        "",
        "## Ballast-Kandidaten",
        "",
        f"**{len(tote)} Quellen** haben ueber alle Laeufe NEUE Meldungen "
        "geliefert, von denen KEINE je bewertet wurde. Getrennt nach der Frage, "
        "ob die Stichprobe das ueberhaupt hergibt: bei drei neuen Meldungen in "
        "elf Laeufen ist „nie bewertet\" kein Befund, sondern Zufall.",
        "",
        f"### Belastbar (>= {MINDEST_NEU} neue Meldungen)",
        "",
    ]
    aus += [f"- {b.anzeigename} ({b.neu} neue Meldungen in {b.laeufe} Laeufen)"
            for b in belastbar] or ["- keine"]
    aus += [
        "",
        f"### Zu duenne Datenlage (< {MINDEST_NEU} neue Meldungen) — nicht bewerten",
        "",
        "- " + ", ".join(f"{b.anzeigename} ({b.neu})" for b in duenn)
        if duenn else "- keine",
    ]
    aus += [
        "",
        f"**{len(leere)} Quellen** haben in keinem Lauf eine Meldung geliefert:",
        "",
    ]
    aus += [f"- {b.anzeigename} ({b.laeufe_fehler} Fehler, {b.laeufe_leer} leer)"
            for b in leere] or ["- keine"]

    if kanalzeilen:
        aus += [
            "",
            "## Je Kanal (nur Laeufe mit Quellen-URL)",
            "",
            f"Deckt {len(kanal_laeufe or [])} Lauf/Laeufe ab: "
            f"{', '.join(kanal_laeufe or [])}.",
            "",
            "| Kanal | Quelle | Ebene | Laeufe | gesammelt | neu | bewertet "
            "| Trefferquote |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
        for b in kanalzeilen:
            aus.append(f"| {b.schluessel[:60]} | {b.anzeigename} | {b.origin} | "
                       f"{b.laeufe} | {b.gesammelt} | {b.neu} | {b.bewertet} | "
                       f"{_pct(b.trefferquote)} |")
    return "\n".join(aus) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--md", type=Path, help="Markdown-Bericht hierhin schreiben")
    p.add_argument("--json", type=Path, help="Rohdaten als JSON hierhin schreiben")
    p.add_argument("--min-laeufe", type=int, default=1)
    p.add_argument("--top", type=int, default=None, help="nur die N besten Zeilen")
    args = p.parse_args(argv)

    berichte = _berichte_laden(args.root / "data" / "reports")
    if not berichte:
        print("Keine Berichte in data/reports/ gefunden.")
        return 1
    nach_name, nach_kanal, kanal_laeufe = auswerten(berichte)
    ergaenzt = historie_ergaenzen(
        nach_name, args.root / "data" / "state" / "seen_historie_je_quelle.json")
    if ergaenzt:
        print(f"Hinweis: fuer {ergaenzt} Quellen kam der Nenner aus dem "
              f"Altbestand des Seen-Stores (kein 'new' im Laufprotokoll).")
    zeilen = tabelle(nach_name, args.min_laeufe, args.top)
    kanalzeilen = tabelle(nach_kanal, 1, args.top)

    text = markdown(zeilen, berichte, kanalzeilen, kanal_laeufe)
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(text, encoding="utf-8")
        print(f"Markdown geschrieben: {args.md}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps([b.als_dict() for b in zeilen], ensure_ascii=False, indent=1),
            encoding="utf-8")
        print(f"JSON geschrieben: {args.json}")
    if not args.md and not args.json:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
