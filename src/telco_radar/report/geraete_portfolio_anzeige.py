"""Darstellung des Portfolio-Vergleichs: aus den eingeteilten Geräten werden
Kacheln, Gruppen und Sätze. Hier wird nichts entschieden und nichts gerechnet -
die Einteilung steht in `geraete_portfolio.py`.

KACHELN (Paket C, 17.11.2026): Antonio über die alte Darstellung: „der portfolio
vergleich ist ne katastrophe … ich will pro modell ein foto haben schöne cleane
darstellung ohne dass ich zwei stunden nach unten scrollen muss". Die belegten
Unterschiede stehen deshalb als flaches Kachelraster - je Gerät eine Kachel mit
Foto-Platz, Hersteller, Modellname und wenigen Worten -, nicht mehr als
Herstellergruppen untereinander. Der Höhendeckel `KACHELN_SICHTBAR` sitzt hier
im Modul, nicht im Stylesheet: was darüber liegt, legt die Vorlage in ein
zugeklapptes `<details>`, das auch ohne JavaScript aufgeht.

Die Messlücken bleiben eine Liste nach Hersteller (`gruppiert`): sie stehen
ohnehin zugeklappt und tragen je Gerät einen ganzen Satz.
"""

from __future__ import annotations

from .anbieter_farben import legendenname
from .geraete_hersteller import HERSTELLER_VORAN
from .geraete_sortiment import GRUND_OHNE
from .geraete_sortiment import datum_de as _datum

KACHELN_SICHTBAR = 6
"""Kacheln je Liste, die ohne Aufklappen stehen - der Höhendeckel des
Abschnitts (zwei Reihen auf 1440 px, drei Reihen am Handy)."""

FEHLT_SATZ = (
    "{wer} führt es (Preis gemessen). Für {fehlt} liegt kein {beleg} vor{grund}."
)
IN_PRUEFUNG_SATZ = (
    "{wer} führt es (Preis gemessen). {fehlt} führt es ebenfalls, der Preis "
    "steht noch in Prüfung."
)


def beleg_text(b: dict) -> dict:
    """Der Beleg einer Kachel: Grund, Daten, Link - und die beiden Fassungen
    `kurz` (auf der Kachel) und `titel` (ganzer Wortlaut)."""
    text = {"grund": b["grund"], "geprueft": _datum(b["geprueft"].isoformat())}
    if b.get("beleg"):
        text["url"] = b["beleg"]
    if b.get("original"):
        text["original"] = b["original"]
    if b.get("bis"):
        text["bis"] = _datum(b["bis"].isoformat())
    text["kurz"] = kurz_satz(text)
    text["titel"] = voller_satz(text)
    return text


def kurz_satz(text: dict) -> str:
    """Die wenigen Worte unter dem Modellnamen einer Kachel. Mit Screenshot
    steht dort das Prüfdatum (der Link „Beleg" daneben), ohne Screenshot das
    Lesedatum der Geräteübersicht; der ganze Wortlaut steht im `titel`."""
    wort = "geprüft" if text.get("url") else "gelesen"
    return f"{wort} {text['geprueft']}"


def voller_satz(text: dict) -> str:
    """Der ganze Beleg als eine Zeile (`title` der Kachel).

    Ohne Screenshot (Erfassungsauszug) steht auf der Kachel selbst nur der
    Gerätename - die Überschrift der Liste trägt die Aussage schon
    (RUHIGER-RUNDE2-1717 Aufgabe 5) -, und der ganze Auszug steht hier."""
    if text.get("url"):
        teile = [text["grund"], f"geprüft {text['geprueft']}"]
        if text.get("bis"):
            teile.append(f"gültig bis {text['bis']}")
        return " · ".join(teile)
    kurz = text["grund"].split(" (")[0].replace("Bei ", "bei ", 1)
    return f"{kurz} (Auszug: {text['grund']} · gelesen {text['geprueft']})"


def _rang(hersteller: str) -> tuple[int, str]:
    voran = list(HERSTELLER_VORAN)
    stelle = voran.index(hersteller) if hersteller in voran else len(voran)
    return (stelle, hersteller)


def kacheln(zeilen: list[dict]) -> list[dict]:
    """Die Kacheln einer Liste: die großen Hersteller zuerst, dann nach Name.

    Flach, nicht nach Hersteller gruppiert: der Hersteller steht auf der Kachel
    selbst, Zwischenüberschriften würden die Liste nur länger machen."""
    return sorted(zeilen, key=lambda z: (*_rang(z["hersteller"]), z["name"]))


def mehr_satz(n: int) -> str:
    """Beschriftung des zugeklappten Rests einer Kachelliste."""
    return "1 weiteres Gerät zeigen" if n == 1 else f"{n} weitere Geräte zeigen"


def rest(zeilen: list[dict]) -> str:
    """Der Satz für den zugeklappten Rest, leer unterhalb des Deckels."""
    n = len(zeilen) - KACHELN_SICHTBAR
    return mehr_satz(n) if n > 0 else ""


def gruppiert(zeilen: list[dict]) -> list[dict]:
    """Messlücken nach Hersteller: die großen drei zuerst, dann nach Zahl, Name."""
    je: dict[str, list[dict]] = {}
    for z in zeilen:
        je.setdefault(z["hersteller"], []).append(z)
    voran = [h for h in HERSTELLER_VORAN if h in je]
    ohne = sorted((h for h in je if h not in voran), key=lambda h: (-len(je[h]), h))
    return [
        {"hersteller": h, "geraete": sorted(je[h], key=lambda z: z["name"])}
        for h in [*voran, *ohne]
    ]


def geraete_zahl(n: int) -> str:
    """„1 Gerät" oder „N Geräte" - der Singular steht nie als „1 Geräte"."""
    return "1 Gerät" if n == 1 else f"{n} Geräte"


def kopfzeile(w: str, n_w: int, n_v: int) -> str:
    """Kopfzahlen je Paar: X nur beim Wettbewerber, Y nur bei Vodafone. Jede
    dieser Zahlen steht in der Vorlage mit `kontext` direkt darunter."""
    return f"{geraete_zahl(n_w)} nur bei {legendenname(w)}, {n_v} nur bei Vodafone"


def kontext(n_belegt: int, n_offen: int) -> str:
    """Der Satz neben den Kopfzahlen: was die Null wirklich bedeutet."""
    offen = (
        "1 aktuelles Gerät ist noch nicht gemessen und wird"
        if n_offen == 1
        else f"{n_offen} aktuelle Geräte sind noch nicht gemessen und werden"
    )
    return f"Bisher belegt: {geraete_zahl(n_belegt)}; {offen} nicht gezählt."


def fehlt_satz(fuehrt: str, fehlt: str, grund: str) -> str:
    """Zeile einer Messlücke: wer das Gerät nachweislich führt (gemessener Preis
    im Bestand) und dass für den anderen Anbieter kein Beleg vorliegt."""
    ohne = grund == GRUND_OHNE
    return FEHLT_SATZ.format(
        wer=legendenname(fuehrt),
        fehlt=legendenname(fehlt),
        beleg="Beleg" if ohne else "gültiger Beleg",
        grund="" if ohne else f": {grund}",
    )


def in_pruefung_satz(fuehrt: str, fehlt: str) -> str:
    """Zeile einer Quarantäne-Lücke (P3, 13.11.2026): `fehlt` führt das Gerät
    nachweislich (eine Karte in Quarantäne ist kein fehlendes Gerät), nur der
    Preis steht noch nicht fest - nie der Satz „liegt kein Beleg vor", der sich
    wie „hat das Gerät nicht" liest."""
    return IN_PRUEFUNG_SATZ.format(wer=legendenname(fuehrt), fehlt=legendenname(fehlt))
