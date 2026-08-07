"""Anzeige-Vorbereitung fuer eine temporaere Themenseite (reine
Datenaufbereitung, kein LLM - wie report/wettbewerb.py und report/promo.py).

Eine Themenseite entsteht, wenn viele Meldungen dasselbe Ereignis meinen
(analyze/highlight_topics.py). Sie beantwortet genau eine Frage: **was ist
bei dieser einen Sache passiert?** Also braucht sie dieselbe Gewichtung wie
die Titelseite und sonst nichts:

    AUFMACHER      die staerkste Meldung, mit dem groessten Bild.
    ZWEITE REIHE   zwei mittlere.
    ZEILEN         alle uebrigen, je mit Quelle und Datum.
    AKTIONEN       laufende Promo-Angebote, die zum Thema passen - aber nur,
                   wenn sie sich ueber die Suchwoerter des Themas wirklich
                   belegen lassen.

Die Meldungen kommen aus dem Themenspeicher, nicht aus der Wochenausgabe:
ein Thema laeuft ueber mehrere Ausgaben, und genau das ist sein Zweck.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from ..analyze.highlight_topics import MIND_TREFFER, suchmuster, treffer

# Ab welcher Bildbreite ein Bild in Aufmacher oder zweite Reihe darf.
# Gemessen an der gerenderten Seite bei 1440 px: der Aufmacher stellt sein
# Bild 502 px breit dar, die zweite Reihe 552 bis 579 px. Alles darunter
# waere ein hochskaliertes Bild - der sichtbarste Teil des Befunds vom
# 06.08.2026 und Abnahmekriterium 6 (scripts/pruefe_portal.py).
#
# Kleiner als die 800 px der Titelseite, und das ist Absicht: eine
# Themenseite hat nur die Meldungen dieses einen Ereignisses, ihre Positionen
# sind schmaler, und ein Aufmacher ohne Bild ist schlechter als einer mit
# einem Bild, das seine Position gerade traegt.
MIND_BREITE_BILD = 600
MAX_AKTIONEN = 6


def _bildbreite(item: dict) -> int:
    return int(item.get("image_w") or 0) if item.get("image") else 0


def _ohne_zu_kleines_bild(m: dict) -> dict:
    """Ein Bild, das seine Position nicht traegt, wird nicht gezeigt.

    Nicht die MELDUNG faellt - die Position bleibt besetzt, nur eben ohne
    Bild. Die Vorlage kennt dafuer die Klasse `ohne-bild`.
    """
    if 0 < _bildbreite(m) < MIND_BREITE_BILD:
        m = {k: v for k, v in m.items()
             if k not in ("image", "image_w", "image_h")}
    return m


def _aktion(eintrag: dict) -> dict:
    """Ein laufendes Angebot als Zeile - wie auf der Wettbewerbsseite ohne
    den Score: eine Zahl auf einer Skala, die diese Seite nicht erklaert,
    ist fuer die Zielgruppe Jargon (CLAUDE.md §8)."""
    return {"marke": eintrag.get("brand") or "",
            "headline": eintrag.get("headline") or "",
            "beschreibung": eintrag.get("description") or "",
            "url": eintrag.get("url") or ""}


def passende_aktionen(thema: dict, promo_entries) -> list[dict]:
    """Laufende Aktionen, die zum Thema gehoeren.

    Dieselbe Schwelle wie bei der Meldungszuordnung: zwei verschiedene
    Suchwoerter muessen treffen. Mit einem allein haengte unter einem Thema
    zum Samsung-Launch jede Aktion, in der das Wort "Samsung" vorkommt - eine
    falsche Verbindung ist schlimmer als keine (CLAUDE.md §5, roter Faden).
    """
    muster = suchmuster(thema.get("keywords"))
    if not muster:
        return []
    passend = []
    for e in promo_entries or []:
        if e.get("status") != "aktiv":
            continue
        text = (f"{e.get('brand') or ''} {e.get('headline') or ''} "
                f"{e.get('description') or ''}")
        if treffer(text, muster) >= MIND_TREFFER:
            passend.append(e)
    passend.sort(key=lambda e: (e.get("highlight") is True, e.get("score") or 0),
                 reverse=True)
    return [_aktion(e) for e in passend[:MAX_AKTIONEN]]


def build_thema_view(thema: dict, promo_entries=()) -> dict:
    """Die Anzeigedaten einer Themenseite.

    `thema` ist ein Eintrag aus data/state/highlight_topics.json, dessen
    `items` bereits um fehlende Bilddateien bereinigt sind (das macht
    render_site, wie bei den Wochenausgaben auch).
    """
    # Spaet importiert: report/html.py baut diese Ansicht auf, ein Import auf
    # Modulebene waere ein Ring. `_schlagzeile()` ist die eine Stelle, die
    # entscheidet, welche Ueberschrift eine Meldung traegt - sie darf hier
    # nicht ein zweites Mal entstehen (Regel 3 des Designbriefs).
    from .html import _schlagzeile

    meldungen = []
    for item in thema.get("items") or []:
        m = dict(item)
        m["schlagzeile"] = _schlagzeile(item)
        # Die Quelle faellt auf die Domain zurueck, wie `source_label` in
        # `_flatten()`. Ohne diesen Rueckfall stand unter dem Aufmacher
        # "Bild:" ohne Namen dahinter - manche Meldungen tragen kein
        # `source`, weil ihre Quelle keinen Anzeigenamen liefert.
        m["quelle"] = (item.get("source")
                       or urlsplit(item.get("url") or "").netloc.removeprefix("www."))
        m["absender"] = item.get("operator") or m["quelle"]
        meldungen.append(m)

    aufmacher = None
    if meldungen:
        # Das breiteste Bild fuehrt, aber nur wenn es die Position traegt;
        # sonst fuehrt die dringendste Meldung. Die Reihenfolge im Speicher
        # ist bereits nach Dringlichkeit sortiert.
        bebildert = [m for m in meldungen if _bildbreite(m) >= MIND_BREITE_BILD]
        aufmacher = max(bebildert, key=_bildbreite) if bebildert else meldungen[0]

    rest = [m for m in meldungen if m is not aufmacher]
    # In die zweite Reihe zuerst, was ein tragfaehiges Bild hat - sonst steht
    # neben dem Aufmacher zweimal nur Text, waehrend weiter unten Bilder in
    # Zeilen verpuffen. Innerhalb beider Gruppen bleibt die Dringlichkeit.
    zwei = ([m for m in rest if _bildbreite(m) >= MIND_BREITE_BILD]
            + [m for m in rest if _bildbreite(m) < MIND_BREITE_BILD])[:2]
    zeilen = [m for m in rest if m not in zwei]
    aufmacher = _ohne_zu_kleines_bild(aufmacher) if aufmacher else None
    zwei = [_ohne_zu_kleines_bild(m) for m in zwei]

    quellen = {(m.get("quelle") or "").strip() for m in meldungen} - {""}
    return {
        "slug": thema.get("slug") or "",
        "titel": thema.get("title") or "",
        "leitsatz": thema.get("description") or "",
        "seit": thema.get("first_seen") or "",
        "aktuell": thema.get("last_active") or "",
        "aufmacher": aufmacher,
        "zwei": zwei,
        "zeilen": zeilen,
        "n": len(meldungen),
        "n_quellen": len(quellen),
        "aktionen": passende_aktionen(thema, promo_entries),
    }
