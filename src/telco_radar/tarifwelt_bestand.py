"""Stammdaten der Tarifwelt-Tarife (Saturn/MediaMarkt) fuer die Band-Zuordnung.

Die Tarife dieser Quelle (`tarif_id` "mediamarkt_tarifwelt:<id>") stehen nicht
in `data/state/tarife.jsonl`: das ist der Bestand der Netzbetreiber-Crawler und
speist auch die Tarifseite, auf der ein Handelstarif nichts zu suchen hat. Ohne
Datenvolumen ordnet der Bericht einem Satz aber kein Tarifband zu. Die
Stammdaten stehen deshalb im Bestand der Buendel selbst (`geraete_tco.json`,
Feld `haendler_tarife`, `TcoDB`): eine eigene Datei kam nie ins Repo (der
Tageslauf sichert nur `geraete_tco.json` und die Historie), das Band fehlte
jeder Zeile, sobald der Bericht ausserhalb des Messlaufs gebaut wurde. Der
Bericht legt sie neben den Tarifbestand und bestimmt das Band mit DERSELBEN
Regel wie bei jedem anderen Tarif (`report.geraete_tco_band.tarif_baender`,
`band_regel.stufe_fuer`).

Wurzelmodul: importiert keine Schicht, damit Sammeln und Bericht es teilen.
"""

from __future__ import annotations

PRAEFIX = "mediamarkt_tarifwelt:"
METHODE = "mediamarkt_tarifwelt"


def lies(roh: object) -> dict[str, dict]:
    """Das Feld `haendler_tarife` aus `geraete_tco.json`; Fehlendes ist leer."""
    if not isinstance(roh, dict):
        return {}
    return {tid: satz for tid, satz in roh.items() if isinstance(satz, dict)}


def feld(tarife: dict[str, dict]) -> dict:
    """Das Feld fuer `geraete_tco.json`, sortiert; ohne Tarife gar keins."""
    return {"haendler_tarife": dict(sorted(tarife.items()))} if tarife else {}


def mit_tarifwelt(tarife: dict | None, zusatz: dict | None) -> dict:
    """Der Tarifbestand der Netzbetreiber PLUS die Tarifwelt-Tarife (`zusatz`, aus
    `TcoDB.haendler_tarife`). Die Schluessel sind getrennt (Praefix); ein
    Netzbetreiber-Tarif wird nie ueberschrieben."""
    plus = {
        tid: satz
        for tid, satz in (zusatz or {}).items()
        if tid.startswith(PRAEFIX) and isinstance(satz, dict)
    }
    return {**plus, **(tarife or {})} if plus else dict(tarife or {})


def typen_der_anbieter(anbieter: list, haendler_tarife: dict | None) -> dict[str, str]:
    """{Anbietername: Typ} aus der Quellenkonfiguration PLUS die Anbieterzeilen der
    Tarifwelt-Tarife ("Saturn/MediaMarkt · o2-Netz"), die den Typ ihrer Quelle
    (Methode `METHODE`) tragen. Ohne die Zeilen blieb "Anbietertyp" im Export leer,
    weil der Name der Quelle nicht der Name der Zeile ist."""
    typen = {a.name: a.typ for a in anbieter}
    typ = next((a.typ for a in anbieter if a.methode == METHODE), None)
    if typ is not None:
        for satz in (haendler_tarife or {}).values():
            if satz.get("anbieter"):
                typen.setdefault(satz["anbieter"], typ)
    return typen
