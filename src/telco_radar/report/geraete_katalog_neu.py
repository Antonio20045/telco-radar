"""Der Neu-Hinweis am Zeitreihen-Suchfeld (R3 der P5-Live-Prüfung): Katalogmodelle
mit Bündel, aber ohne Zeitreihe (aus `geraete_view` ausgelagert)."""

from __future__ import annotations

from .geraete_tco_band import _MONATE


def _neu_seit(iso: str) -> str:
    """„17. September" - Tag und Monat fuer den Neu-Hinweis am Zeitreihen-
    Suchfeld (R3 der P5-Live-Pruefung). MonatNamen aus derselben Tabelle,
    die die Katalog-Zeile formatiert (`geraete_tco_band._MONATE` - eine
    zweite Kopie der zwolf Namen wuerde driften); ein unlesbares Datum
    steht roh im Satz statt geraten zu werden."""
    try:
        jahr, monat, tag = (int(x) for x in iso.split("-"))
        return f"{tag}. {_MONATE[monat - 1]}"
    except (AttributeError, ValueError, IndexError):
        return iso or ""


def liste(katalog_modelle: list) -> list[dict]:
    """Je Katalogmodell mit Bündel und ohne Zeitreihe: Schlüssel, Titel und das
    früheste Belegdatum (`iso`, `datum` ausgeschrieben)."""
    neu = []
    for m in katalog_modelle:
        if not m.get("hat_buendel") or m.get("zr"):
            continue
        belege = sorted(
            b.get("abgerufen_am")
            for b in (m.get("ab_beleg"), m.get("buendel_beleg"))
            if b and b.get("abgerufen_am")
        )
        neu.append(
            {
                "id": m["schluessel"],
                "titel": m["titel"],
                "datum": _neu_seit(belege[0]) if belege else "",
                "iso": belege[0] if belege else "",
            }
        )
    return neu
