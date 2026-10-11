"""Die KI-Seite (Pitch 9, Entwurf 10, Schnitt 1).

KI-Meldung ist, was in der Themenregion der KI-Anbieter steht
(``cfg.theme_names["thema:ki"]``) oder in Titel und Kurztext das Technikthema
„KI / AI“ trägt. Gelesen werden alle Berichte, jede URL einmal, die neueste
Meldung zuerst; innerhalb eines Tages entscheidet die Priorität. Die Seite
zeigt die Meldungen wie die Meldungen-Seite in drei Spalten, aber ohne
fremde Fotos.

Das Modul importiert ``html`` nicht: die Themenerkennung kommt als
Parameter herein.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from . import meldungen_seite

KI_THEMA = "thema:ki"
KI_TAG = "KI / AI"
LINKS = 2
RECHTS = 5
LISTE = 36
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


def ausgabe(meldungen: list[dict], stand: str) -> dict:
    """Verteilt die KI-Meldungen auf Aufmacher, links, „Auch wichtig“ und Liste."""
    aufmacher = meldungen[0] if meldungen else None
    links = meldungen[1 : 1 + LINKS]
    rechts = meldungen[1 + LINKS : 1 + LINKS + RECHTS]
    return {
        "kw": meldungen_seite.kalenderwoche(stand),
        "aufmacher": aufmacher,
        "links": links,
        "rechts": rechts,
        "liste": meldungen[1 + LINKS + RECHTS :][:LISTE],
    }


def seite(env, wochen: list[dict], cfg, tag_tech, date_de: str) -> str:
    """Das HTML von ``ki.html``; Stand ist der neueste Bericht."""
    stand = max((w["date"] for w in wochen), default="")
    meldungen = ki_meldungen(wochen, ki_region(cfg), tag_tech)
    return env.get_template(VORLAGE).render(
        prefix="", date_de=date_de, ausgabe=ausgabe(meldungen, stand)
    )
