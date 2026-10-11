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
„Verstehen“ (Schnitt 9) zeigt die Kapitel aus ``KAPITEL``; verlinkt sind
nur die fertigen (``FERTIG``), Linie und Pillen der Fahrt stehen in
``FAHRT_WEG`` und ``STATIONEN``, ``app.js`` zeichnet sie beim Scrollen.
Kapitel 1 (Schnitte 10–12) ist eine eigene Seite aus ``ki_kapitel``.
Die Muster-Prompts (Schnitt 13) lädt ``analyze.ki_inhalte``; Kopfzeile,
Themenzeile und Rubrikleiste lesen dasselbe ``anzahl``. Die Videos
(Schnitte 14 und 15) liest ``analyze.ki_videos.lange``; ``videos()`` ordnet
sie nur an: eins groß links, eins klein rechts, höchstens ``REIHE`` darunter.

Das Modul importiert ``html`` nicht: die Themenerkennung kommt als
Parameter herein.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

from ..analyze import ki_blatt, ki_modelle, ki_videos
from . import ki_kapitel, meldungen_seite

KI_THEMA = "thema:ki"
KI_TAG = "KI / AI"
LINKS = 2
RECHTS = 5
VORLAGE = "ki.html.j2"
REIHE = 6
OHNE_ABRUF = "noch kein Abruf"
KAPITEL = (
    "Wie eine KI antwortet",
    "Was ist eigentlich KI?",
    "Wie eine KI lernt",
    "Warum sie würfelt",
    "Der Schreibtisch",
    "Überzeugend falsch",
    "Erst denken, dann antworten",
    "Sehen und Hören",
    "Nachschlagen lassen",
    "Agenten",
    "Strom, Chips, Rechnung",
    "Sicher arbeiten",
)
FERTIG = frozenset({1})
FAHRT_WEG = "M 20 190 C 140 190 170 70 300 70 S 470 200 600 180 S 760 60 980 80"
STATIONEN = (
    ("Frage", 0.0, "start", 20.0, 190.0),
    ("Wörter", 0.3, "middle", 300.3, 70.0),
    ("Bedeutung", 0.6, "middle", 584.3, 181.7),
    ("Antwort", 0.97, "end", 948.9, 77.9),
)


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


def _video(v: dict) -> dict:
    sekunden = v["dauer_sekunden"]
    return dict(
        v,
        zeit=f"{sekunden // 60}:{sekunden % 60:02d}",
        minuten=(sekunden + 30) // 60,
    )


def videos(store: dict, mit_spalten: bool) -> dict:
    """Eins links, eins rechts, die nächsten in der Reihe; ohne Spalten alle dort."""
    liste = [_video(v) for v in ki_videos.lange(store)]
    spalten = 2 if mit_spalten else 0
    oben = liste[:spalten]
    ausfall = store.get("error")
    if ausfall is None and store.get("stand") is None:
        ausfall = OHNE_ABRUF
    return {
        "links": oben[0] if oben else None,
        "rechts": oben[1] if len(oben) > 1 else None,
        "reihe": liste[spalten : spalten + REIHE],
        "ausfall": ausfall,
        "stand": _tag(store.get("stand")),
    }


def rubriken(ausgabe: dict, modelle: dict, prompts: dict) -> list[dict]:
    """Die Teile der Seite mit ihrer Zahl; ein leerer Teil fehlt in der Leiste."""
    teile = [
        ("meldungen", "Meldungen", ausgabe["anzahl"]),
        ("modelle", "Modelle", len(modelle["top"])),
        ("verstehen", "Verstehen", len(KAPITEL)),
        ("prompts", "Prompts", prompts["anzahl"]),
    ]
    return [{"ziel": z, "name": n, "zahl": k} for z, n, k in teile if k]


def kapitel() -> list[dict]:
    """Die Knoten der Schiene: Nummer, Titel, Ziel nur für fertige Kapitel."""
    return [
        {
            "nr": nr,
            "titel": t,
            "ziel": f"ki-kapitel-{nr}.html" if nr in FERTIG else None,
        }
        for nr, t in enumerate(KAPITEL, start=1)
    ]


def kapitel_seite(env) -> str:
    """Das HTML von ``ki-kapitel-1.html`` (Schnitte 10–12, ``ki_kapitel``)."""
    return ki_kapitel.seite(env, kapitel())


def fahrt(schrift: int = 24) -> dict:
    """Linie und Pillen der Fahrt für die Seite ohne JavaScript."""
    pillen = []
    for wort, an, anker, x, y in STATIONEN:
        breite = len(wort) * schrift * 0.56 + schrift * 1.2
        links = {"start": x - schrift * 0.6, "end": x - breite + schrift * 0.6}
        pillen.append(
            {
                "wort": wort,
                "an": an,
                "anker": anker,
                "x": x,
                "y": y,
                "rx": round(links.get(anker, x - breite / 2), 1),
                "ry": y - schrift * 2.5,
                "ty": y - schrift * 1.25,
                "breite": round(breite, 1),
                "hoehe": schrift * 1.8,
                "schrift": schrift,
            }
        )
    return {"weg": FAHRT_WEG, "pillen": pillen}


def seite(
    env,
    wochen: list[dict],
    cfg,
    tag_tech,
    date_de: str,
    ki_store: dict,
    prompts: dict,
    video_store: dict,
) -> str:
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
        rubriken=rubriken(blatt_ausgabe, band, prompts),
        kapitel=kapitel(),
        fahrt=fahrt(),
        prompts=prompts,
        videos=videos(video_store, blatt_ausgabe["aufmacher"] is not None),
    )
