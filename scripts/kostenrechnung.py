#!/usr/bin/env python3
"""Was ein Lauf kostet - heute und bei 1000 Quellen.

Warum es das gibt (AUFTRAG_SKALIERUNG_1000.md 3.4 und Abzuliefern 7): Antonio
zahlt die API privat, und das Projekt hat den Anspruch, kostenlos bzw. sehr
guenstig zu bleiben. Eine Verzehnfachung der Quellen ist deshalb auch eine
Kostenfrage, und sie soll ausgerechnet und nicht geschaetzt werden.

Gerechnet wird aus dem, was im Laufprotokoll steht: Zahl der Analysten-Stapel,
Zahl der bewerteten Meldungen, gemessene Zeichenzahl je Meldung. Die
Hochrechnung skaliert diese Groessen mit der Zahl der Quellen und rechnet die
zweistufige Redaktion mit ein - sie ist der Posten, der sich beim Umbau
geaendert hat.

    python scripts/kostenrechnung.py
    python scripts/kostenrechnung.py --quellen 1000 --md outputs/kosten.md
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

# Preise je 1 Mio Token, Stand 08/2026 (api-docs.deepseek.com). DeepSeek
# kuendigt zu Pekinger Stosszeiten (9-12 und 14-18 Uhr) doppelte Preise an -
# der Cron laeuft um 08:30 UTC, also 16:30 Peking und damit MITTEN in der
# zweiten Stosszeit. Deshalb wird beides ausgewiesen.
PREISE = {
    "deepseek-v4-flash": {"ein": 0.14, "aus": 0.28},
    "deepseek-v4-pro": {"ein": 0.435, "aus": 0.87},
}
ZEICHEN_JE_TOKEN = 4

# Aus dem Analysten-Prompt (analyze/agents.py) und einem echten Lauf gemessen.
ANALYST_SYSTEM_TOKEN = 900     # ANALYST_SYSTEM/TECH_ANALYST_SYSTEM
ANALYST_JE_MELDUNG_TOKEN = 120  # Titel + Betreiber + Quelle + Datum + Anriss
ANALYST_AUSGABE_JE_HIGHLIGHT = 190
BATCH_SIZE = 15


def _neuester_lauf(root: Path) -> dict:
    dateien = sorted(glob.glob(str(root / "data" / "reports" / "*.json")))
    if not dateien:
        raise SystemExit("Kein Bericht in data/reports/ gefunden")
    return json.loads(Path(dateien[-1]).read_text(encoding="utf-8"))


def _kosten(modell: str, ein_token: float, aus_token: float) -> float:
    p = PREISE[modell]
    return ein_token / 1e6 * p["ein"] + aus_token / 1e6 * p["aus"]


def rechne(quellen: int, neue_meldungen: float, bewertete: float,
           bereiche: int, zweistufig: bool,
           zeichen_je_meldung: int = 716) -> dict:
    """Ein Lauf, aufgeschluesselt nach Posten."""
    # --- Analysten (flash): ein Aufruf je Stapel a 15 Meldungen
    stapel = max(1, round(neue_meldungen / BATCH_SIZE + 0.49))
    analyst_ein = stapel * ANALYST_SYSTEM_TOKEN + \
        neue_meldungen * ANALYST_JE_MELDUNG_TOKEN
    analyst_aus = bewertete * ANALYST_AUSGABE_JE_HIGHLIGHT
    analyst = _kosten("deepseek-v4-flash", analyst_ein, analyst_aus)

    # --- Redaktion (pro)
    if zweistufig:
        # Stufe 1: je Bereich nur SEINE Meldungen; Stufe 2 nur die
        # Kurzfassungen und fuenf Meldungen je Bereich.
        bereich_ein = bewertete * zeichen_je_meldung / ZEICHEN_JE_TOKEN + \
            bereiche * 700
        bereich_aus = bereiche * 700
        chef_ein = bereiche * (150 + 5 * zeichen_je_meldung / ZEICHEN_JE_TOKEN) + 900
        chef_aus = 1400
        redaktion = _kosten("deepseek-v4-pro", bereich_ein + chef_ein,
                            bereich_aus + chef_aus)
        redaktion_aufrufe = bereiche + 1
    else:
        ein = bewertete * zeichen_je_meldung / ZEICHEN_JE_TOKEN + 1500
        redaktion = _kosten("deepseek-v4-pro", ein, 3500)
        redaktion_aufrufe = 1

    return {
        "quellen": quellen,
        "neue_meldungen": round(neue_meldungen),
        "bewertete": round(bewertete),
        "bereiche": bereiche,
        "redaktion": "zweistufig" if zweistufig else "einstufig",
        "analysten_aufrufe": stapel,
        "redaktions_aufrufe": redaktion_aufrufe,
        "kosten_analysten": analyst,
        "kosten_redaktion": redaktion,
        "kosten_lauf": analyst + redaktion,
        "kosten_monat": (analyst + redaktion) * 2 * 4.33,
        "kosten_monat_stosszeit": (analyst + redaktion) * 2 * 4.33 * 2,
    }


def _zeile(e: dict) -> str:
    return (f"| {e['quellen']} | {e['neue_meldungen']} | {e['bewertete']} | "
            f"{e['redaktion']} | {e['analysten_aufrufe']} + "
            f"{e['redaktions_aufrufe']} | {e['kosten_lauf']:.3f} $ | "
            f"{e['kosten_monat']:.2f} $ | {e['kosten_monat_stosszeit']:.2f} $ |")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--quellen", type=int, default=1000)
    p.add_argument("--md", type=Path)
    args = p.parse_args(argv)

    bericht = _neuester_lauf(args.root)
    stats = bericht["stats"]
    lauf = bericht["run"]
    ist_quellen = stats["sources_total"]
    ist_neu = stats["new"]
    ist_bewertet = sum(len(r.get("highlights") or [])
                       for r in bericht["regions"].values())
    ist_bereiche = len(lauf.get("analysts") or []) or len(bericht["regions"])

    je_quelle_neu = ist_neu / ist_quellen
    bewertungsquote = ist_bewertet / ist_neu if ist_neu else 0.0

    ist = rechne(ist_quellen, ist_neu, ist_bewertet, ist_bereiche,
                 zweistufig=False)
    ziel_neu = je_quelle_neu * args.quellen
    ziel_bewertet = ziel_neu * bewertungsquote
    # Mehr Quellen heissen nicht mehr Regionen, aber mehr Themenfelder. Zwei
    # neue Kategorien sind in dieser Session dazugekommen; 16 Bereiche sind
    # eine vorsichtige Annahme.
    ziel_bereiche = 16
    ziel_einstufig = rechne(args.quellen, ziel_neu, ziel_bewertet,
                            ziel_bereiche, zweistufig=False)
    ziel_zweistufig = rechne(args.quellen, ziel_neu, ziel_bewertet,
                             ziel_bereiche, zweistufig=True)

    zeilen = [
        "# Kostenrechnung",
        "",
        f"Grundlage: Lauf vom {bericht['date']} "
        f"({ist_quellen} Quellen, {stats['collected']} gesammelt, {ist_neu} neu, "
        f"{ist_bewertet} bewertet). Analysten auf `deepseek-v4-flash`, "
        "Redaktion auf `deepseek-v4-pro`.",
        "",
        f"Hochgerechnet mit den gemessenen Verhaeltnissen: "
        f"{je_quelle_neu:.2f} neue Meldungen je Quelle und Lauf, "
        f"{bewertungsquote:.0%} davon werden bewertet.",
        "",
        "| Quellen | neu | bewertet | Redaktion | LLM-Aufrufe | je Lauf | "
        "je Monat | je Monat zur Stosszeit |",
        "|---:|---:|---:|---|---|---:|---:|---:|",
        _zeile(ist),
        _zeile(ziel_einstufig),
        _zeile(ziel_zweistufig),
        "",
        "Zwei Laeufe die Woche, 4,33 Wochen im Monat. Die letzte Spalte ist der "
        "ehrliche Fall: der Cron laeuft um 08:30 UTC, also 16:30 Pekinger Zeit "
        "und damit mitten in DeepSeeks zweiter Stosszeit, fuer die doppelte "
        "Preise angekuendigt sind.",
        "",
        "## Was daraus folgt",
        "",
        f"- Der Ausbau auf {args.quellen} Quellen ist **kein Kostenproblem**. "
        f"Auch im teuersten Fall bleibt der Monat unter "
        f"{max(ziel_einstufig['kosten_monat_stosszeit'], ziel_zweistufig['kosten_monat_stosszeit']):.0f} $.",
        "- Die zweistufige Redaktion kostet "
        f"{ziel_zweistufig['kosten_redaktion'] / ziel_einstufig['kosten_redaktion']:.1f}-mal "
        "so viel wie die einstufige - absolut sind das "
        f"{(ziel_zweistufig['kosten_lauf'] - ziel_einstufig['kosten_lauf']):.3f} $ "
        "je Lauf. Dafuer haengt die Eingabe der Chefredaktion nicht mehr an der "
        "Zahl der Meldungen, und ein Fehlschlag kostet einen Abschnitt statt "
        "des ganzen Wochenberichts.",
        f"- Der eigentliche Engpass bleibt die LAUFZEIT und das Rate-Limit: "
        f"{ziel_zweistufig['analysten_aufrufe']} Analysten-Aufrufe je Lauf statt "
        f"heute {ist['analysten_aufrufe']}. Bei den heutigen 12 gleichzeitigen "
        f"Aufrufen sind das rund "
        f"{round(ziel_zweistufig['analysten_aufrufe'] / 12)} Runden.",
        "",
        "## Vorbehalte",
        "",
        "- Die Token-Zahlen je Meldung sind aus dem Prompt und einem echten Lauf "
        "abgeleitet, nicht vom Anbieter abgerechnet. Ein Faktor 2 Irrtum aendert "
        "an der Groessenordnung nichts.",
        "- Nicht enthalten sind die Nebenstufen (Wettbewerber-Profile, "
        "Differenzierungs-Kurator, Kategorie-Sweep, Promo-Uebersicht). Sie "
        "haengen nicht an der Zahl der Quellen und aendern sich mit dem Ausbau "
        "nicht.",
        "- Reasoning-Token zaehlen bei DeepSeek als Ausgabe. Die Ausgabeposten "
        "oben sind deshalb eher zu niedrig als zu hoch.",
    ]
    text = "\n".join(zeilen) + "\n"
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(text, encoding="utf-8")
        print(f"Geschrieben: {args.md}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
