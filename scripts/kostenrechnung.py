#!/usr/bin/env python3
"""Was ein Lauf kostet - heute und bei 1000 Quellen.

Antonio zahlt die Modellaufrufe privat, und das Projekt hat den Anspruch,
kostenlos bzw. sehr guenstig zu bleiben. Diese Rechnung steht deshalb im
Repo und nicht in einer Chatnachricht: wenn sich Preise, Stapelgroesse oder
die Zahl der Bereiche aendern, wird sie neu gerechnet statt neu geschaetzt.

Alle Mengengeruestwerte sind entweder gemessen (Lauf #67, 04.08.2026) oder
aus gemessenen Werten hochgerechnet; jede Annahme steht als Kommentar dabei.

    python scripts/kostenrechnung.py
    python scripts/kostenrechnung.py --quellen 1000 --stosszeit
"""
from __future__ import annotations

import argparse

# Preis je 1M Token (DeepSeek, Stand 08/2026). Zu Pekinger Stosszeiten
# (9-12 und 14-18 Uhr) kuendigt DeepSeek doppelte Preise an - der Cron laeuft
# um 08:30 UTC, also 16:30 Peking und damit MITTEN in der zweiten Stosszeit.
# Deshalb ist --stosszeit nicht der Ausnahme-, sondern der Regelfall.
PREISE = {
    "flash": {"ein": 0.14, "aus": 0.28},
    "pro": {"ein": 0.435, "aus": 0.87},
}

# --- gemessen in Lauf #67 (130 Quellen) --------------------------------------
GEMESSEN_QUELLEN = 130
GEMESSEN_GESAMMELT = 2161        # Meldungen je Lauf
GEMESSEN_NEU = 124               # davon neu
GEMESSEN_BEWERTET = 36           # davon von einem Analysten bewertet
BATCH = 15                       # Meldungen je Analysten-Aufruf

# --- Token je Aufruf, aus echten Prompts abgeschaetzt ------------------------
# Analyst: 15 Meldungen a ~500 Zeichen (Titel, Quelle, Datum, URL, 300 Zeichen
# Anriss) plus ~3200 Zeichen Systemprompt -> ~2,7k Token ein. Ausgabe: nur die
# Meldungen mit Relevanz >= 2, gemessen rund ein Drittel, a ~400 Zeichen.
ANALYST_EIN = 2700
ANALYST_AUS = 1500
# Bereichsredakteur: alle bewerteten Meldungen SEINES Bereichs a ~750 Zeichen
# plus Systemprompt. Ausgabe: Abschnitt (~900 Woerter) plus Kurzfassung, Top
# und Themenliste als JSON.
BEREICH_EIN_JE_MELDUNG = 190     # 750 Zeichen / 4
BEREICH_EIN_GRUNDLAST = 1200
BEREICH_AUS = 2500
# Chefredaktion: je Bereich Kurzfassung (5 Saetze) und 5 Top-Meldungen.
CHEF_EIN_JE_BEREICH = 400
CHEF_EIN_GRUNDLAST = 1500        # Themengedaechtnis, Systemprompt
CHEF_AUS = 3000


def rechne(quellen: int, bereiche: int, stosszeit: bool,
           laeufe_pro_woche: float = 2.0, erstlauf: bool = False) -> dict:
    faktor = 2.0 if stosszeit else 1.0
    skala = quellen / GEMESSEN_QUELLEN

    gesammelt = GEMESSEN_GESAMMELT * skala
    # Im Regelbetrieb sind 5,7 % der gesammelten Meldungen neu (gemessen,
    # 124 von 2161). Beim ERSTEN Lauf nach einer Ausbauwelle liefern die
    # neuen Quellen ihr volles Frischefenster auf einmal - dann ist praktisch
    # alles neu. Das ist der teuerste und laengste Lauf ueberhaupt und der
    # einzige, bei dem die Rechnung wirklich gross wird.
    neu = gesammelt if erstlauf else GEMESSEN_NEU * skala
    bewertet = neu * (GEMESSEN_BEWERTET / GEMESSEN_NEU)

    analysten = -(-int(neu) // BATCH)          # aufrunden
    je_bereich = bewertet / max(1, bereiche)

    posten = [
        ("Analysten", analysten, ANALYST_EIN, ANALYST_AUS, "flash"),
        ("Bereichsredaktion", bereiche,
         BEREICH_EIN_GRUNDLAST + BEREICH_EIN_JE_MELDUNG * je_bereich,
         BEREICH_AUS, "flash"),
        ("Chefredaktion", 1,
         CHEF_EIN_GRUNDLAST + CHEF_EIN_JE_BEREICH * bereiche,
         CHEF_AUS, "pro"),
    ]

    zeilen = []
    summe = 0.0
    for name, anzahl, ein, aus, modell in posten:
        p = PREISE[modell]
        kosten = faktor * anzahl * (ein * p["ein"] + aus * p["aus"]) / 1_000_000
        summe += kosten
        zeilen.append({"posten": name, "aufrufe": anzahl, "modell": modell,
                       "token_ein": int(ein), "token_aus": int(aus),
                       "kosten": kosten})
    return {
        "quellen": quellen, "bereiche": bereiche, "stosszeit": stosszeit,
        "erstlauf": erstlauf,
        "gesammelt": int(gesammelt), "neu": int(neu), "bewertet": int(bewertet),
        "zeilen": zeilen, "je_lauf": summe,
        "je_monat": summe * laeufe_pro_woche * 52 / 12,
        "je_jahr": summe * laeufe_pro_woche * 52,
    }


def drucke(e: dict) -> None:
    print(f"\n{e['quellen']} Quellen, {e['bereiche']} Bereiche"
          f"{' - ERSTLAUF nach Ausbauwelle' if e.get('erstlauf') else ''}"
          f"{' (Pekinger Stosszeit, doppelter Preis)' if e['stosszeit'] else ''}")
    print(f"  {e['gesammelt']} Meldungen gesammelt, {e['neu']} neu, "
          f"{e['bewertet']} bewertet")
    print(f"  {'Posten':20} {'Aufrufe':>7} {'Modell':>6} {'Token ein':>10} "
          f"{'Token aus':>10} {'USD':>8}")
    for z in e["zeilen"]:
        print(f"  {z['posten']:20} {z['aufrufe']:>7} {z['modell']:>6} "
              f"{z['token_ein']:>10} {z['token_aus']:>10} {z['kosten']:>8.4f}")
    print(f"  {'je Lauf':20} {'':>7} {'':>6} {'':>10} {'':>10} "
          f"{e['je_lauf']:>8.4f}")
    print(f"  {'je Monat (2/Woche)':20} {'':>7} {'':>6} {'':>10} {'':>10} "
          f"{e['je_monat']:>8.2f}")
    print(f"  {'je Jahr':20} {'':>7} {'':>6} {'':>10} {'':>10} "
          f"{e['je_jahr']:>8.2f}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--quellen", type=int, action="append",
                   help="mehrfach angebbar (Standard: 130, 300, 600, 1000)")
    p.add_argument("--bereiche", type=int, default=0,
                   help="0 = mit der Quellenzahl wachsen lassen")
    p.add_argument("--stosszeit", action="store_true")
    p.add_argument("--erstlauf", action="store_true",
                   help="erster Lauf nach einer Ausbauwelle: alle Quellen "
                        "liefern ihr volles Frischefenster auf einmal")
    args = p.parse_args(argv)

    stufen = args.quellen or [130, 300, 600, 1000]
    for quellen in stufen:
        # Die Bereiche wachsen nicht linear mit den Quellen: 6 Regionen bleiben
        # 6 Regionen. Realistisch kommen Themenfelder dazu, nicht Regionen.
        bereiche = args.bereiche or (12 if quellen < 400 else
                                     16 if quellen < 800 else 20)
        for stoss in ({False, True} if not args.stosszeit else {True}):
            drucke(rechne(quellen, bereiche, stoss,
                          erstlauf=args.erstlauf))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
