"""congstar: die Nummern-Bruecke vom Bündel zum Pflichtblatt im Tarifbestand.

Ausgelagert aus `congstar.py` (Modulkopf dort, "DER SLUG IST DIE NUMMER DES
PFLICHTBLATTS"). Neu am 20.11.2026: liest der Tarifcrawler dasselbe Blatt an zwei
Tagen unter zwei Namen, steht die Nummer zweimal im Bestand (Blatt 559: am
17.11.2026 `congstar:allnet-flat-s-flex-mit-gb`, am 19.11.2026 eine neue
`tarif_id`). Bis dahin war das eine Mehrdeutigkeit, und 115 Bündel "Allnet Flat
S Flex" fielen unter "ohne aufloesbaren Tarif". Die Brücke bekommt jetzt die
jüngste Lesung des Blatts; zwei Lesungen vom selben Tag oder ohne Datum bleiben
mehrdeutig (dieselbe Regel wie `ueber_slug`: zwei Treffer sind keiner).
"""

from __future__ import annotations

import re

PIB_NR_RE = re.compile(r"Produktinformationsblatt_(\d+)\.pdf")


def _juengste_lesung(gruppe: list[dict]) -> dict | None:
    """Der Satz mit dem jüngsten `abgerufen_am`; `None` bei Gleichstand oder
    fehlendem Datum."""
    if len(gruppe) == 1:
        return gruppe[0]
    tage = [str(s.get("abgerufen_am") or "") for s in gruppe]
    juengster = max(tage)
    if "" in tage or tage.count(juengster) != 1:
        return None
    return gruppe[tage.index(juengster)]


def ergaenze_pib_slug(bestand) -> int:
    """Am congstar-Tarifbestand die Nummern-Bruecke setzen.

    Ergaenzt congstar-Saetzen OHNE `buendel_slug` die Nummer aus ihrer
    Pflichtblatt-Adresse, je Nummer nur der jüngsten Lesung (`_juengste_lesung`).
    Schon gesetzte Werte bleiben unberuehrt. Gibt die Zahl der ergaenzten Saetze
    zurueck.

    Aufgerufen von der Pipeline, direkt nach dem Laden des Bestands. Das ist
    bewusst KEINE dauerhafte Aenderung an `tarife.jsonl`: die Zeitreihe bleibt
    unberuehrt, und die Bruecke entsteht bei jedem Lauf neu aus der Blattnummer,
    die der Anbieter in beide Adressen schreibt.
    """
    nummern: dict[str, list] = {}
    for satz in bestand.je_id.values():
        if str(satz.get("anbieter") or "").lower() != "congstar":
            continue
        treffer = PIB_NR_RE.search(str(satz.get("dokument_url") or ""))
        if treffer:
            nummern.setdefault(treffer.group(1), []).append(satz)
    gesetzt = 0
    for nummer, gruppe in nummern.items():
        satz = _juengste_lesung(gruppe)
        if satz is None or str(satz.get("buendel_slug") or "").strip():
            continue
        satz["buendel_slug"] = nummer
        gesetzt += 1
    return gesetzt
