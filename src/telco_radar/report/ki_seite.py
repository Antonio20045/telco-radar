"""Die KI-Seite (Pitch 9, Entwurf 10, Schnitt 1).

KI-Meldung ist, was in der Themenregion der KI-Anbieter steht
(``cfg.theme_names["thema:ki"]``) oder in Titel und Kurztext das Technikthema
„KI / AI“ trägt. Gelesen werden alle Berichte, jede URL einmal, die neueste
Meldung zuerst; innerhalb eines Tages entscheidet die Priorität. Die Seite
zeigt die Meldungen wie die Meldungen-Seite in drei Spalten, aber ohne
fremde Fotos. Ressort und Archiv rechnet ``analyze.ki_blatt``: je Ressort
höchstens zwölf Meldungen im Blatt, die älteren im zugeklappten Archiv.
Das Band „Modelle“ zeigt den Store aus ``analyze.ki_modelle`` (Schnitt 6),
``app.js`` zeichnet daraus die Leiter (Schnitt 7). Die Rubrikleiste
(Schnitt 8) zählt je Abschnitt dasselbe Feld, das der Abschnitt zeigt.

Das Modul importiert ``html`` nicht: die Themenerkennung kommt als
Parameter herein.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

from ..analyze import ki_blatt, ki_modelle
from . import meldungen_seite

KI_THEMA = "thema:ki"
KI_TAG = "KI / AI"
LINKS = 2
RECHTS = 5
VORLAGE = "ki.html.j2"


def ki_region(cfg) -> str | None:
    """Der Name der Themenregion „KI-Anbieter“; None ohne Konfiguration."""
    if cfg is None:
        return None
    return cfg.theme_names.get(KI_THEMA)


def ist_ki(h: dict, region: str | None, tag_tech: Callable[[str], list[str]]) -> bool:
    """Steht die Meldung bei den KI-Anbietern oder handelt sie von KI?"""
    if region is not None and h.get("region") == region:
        return True
    return KI_TAG in tag_tech(f"{h.get('title', '')} {h.get('summary', '')}")


def ki_meldungen(
    wochen: Iterable[dict], region: str | None, tag_tech: Callable[[str], list[str]]
) -> list[dict]:
    """Alle KI-Meldungen aller Berichte, je URL einmal, neueste zuerst."""
    gesehen: set[str] = set()
    out: list[dict] = []
    for woche in sorted(wochen, key=lambda w: w["date"], reverse=True):
        for h in woche["highlights"]:
            url = h.get("url")
            if not url or url in gesehen or not ist_ki(h, region, tag_tech):
                continue
            gesehen.add(url)
            out.append(dict(h, ki_datum=str(h.get("date") or woche["date"])[:10]))
    out.sort(key=lambda h: (h["ki_datum"], h["relevance"]), reverse=True)
    return out


def ausgabe(
    meldungen: list[dict], stand: str, archiv: list[dict] | None = None
) -> dict:
    """Verteilt das Blatt auf Aufmacher, links, „Auch wichtig“ und Liste."""
    aufmacher = meldungen[0] if meldungen else None
    links = meldungen[1 : 1 + LINKS]
    rechts = meldungen[1 + LINKS : 1 + LINKS + RECHTS]
    return {
        "kw": meldungen_seite.kalenderwoche(stand),
        "aufmacher": aufmacher,
        "links": links,
        "rechts": rechts,
        "liste": meldungen[1 + LINKS + RECHTS :],
        "anzahl": len(meldungen),
        "je_ressort": ki_blatt.HOECHSTENS_JE_RESSORT,
        "archiv": archiv or [],
    }


def _tag(iso: str | None) -> str | None:
    return date.fromisoformat(iso).strftime("%d.%m.%Y") if iso else None


def modelle_band(store: dict) -> dict:
    """Rangliste, Stand und je ausgefallener Quelle Name und Tag des Versuchs."""
    quellen = store.get("quellen") or {}
    ausfall = [
        (ki_modelle.QUELLEN_NAMEN.get(k, k), _tag(q.get("versucht")))
        for k, q in quellen.items()
        if q.get("error")
    ]
    top = store.get("top") or []
    return {
        "top": top,
        "leiter": [{k: m[k] for k in ("platz", "name", "farbe")} for m in top],
        "stand": _tag(store.get("stand")),
        "urls": {k: q.get("url") for k, q in quellen.items()},
        "ausfall": ausfall,
        "fehler": store.get("error"),
    }


def rubriken(ausgabe: dict, modelle: dict) -> list[dict]:
    """Die Teile der Seite mit ihrer Zahl; ein leerer Teil fehlt in der Leiste."""
    teile = [
        ("meldungen", "Meldungen", ausgabe["anzahl"]),
        ("modelle", "Modelle", len(modelle["top"])),
    ]
    return [{"ziel": z, "name": n, "zahl": k} for z, n, k in teile if k]


def seite(env, wochen: list[dict], cfg, tag_tech, date_de: str, ki_store: dict) -> str:
    """Das HTML von ``ki.html``; Stand ist der neueste Bericht."""
    stand = max((w["date"] for w in wochen), default="")
    meldungen = ki_meldungen(wochen, ki_region(cfg), tag_tech)
    blatt, archiv = ki_blatt.blatt(meldungen, ki_blatt.netzbetreiber(cfg))
    blatt_ausgabe = ausgabe(blatt, stand, archiv)
    band = modelle_band(ki_store)
    return env.get_template(VORLAGE).render(
        prefix="",
        date_de=date_de,
        ausgabe=blatt_ausgabe,
        modelle=band,
        rubriken=rubriken(blatt_ausgabe, band),
    )
