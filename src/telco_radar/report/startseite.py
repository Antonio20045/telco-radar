"""Die Startseite als Abfolge von Szenen und ihre drei Fenster.

Alles hier ist Darstellung. Die Kapitel entstehen aus dem fertigen
Bericht-HTML, die Fenster aus Titelseite, Geräte- und Promo-Aufbereitung.
Keine Zahl wird hier neu berechnet: eine Zahl im Bericht bekommt nur eine
Hülle, damit die Seite sie hervorheben kann, und die Fenster zeigen Werte,
die ihre Seiten bereits ausweisen.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import re
from datetime import date, timedelta

from .bilder import MIND_BREITE_GROSS

ENDET_BALD_TAGE = 7
ERSATZBILD = "kapitel-global"
STARTBILD = "kapitel-auf-einen-blick"
KAPITEL_BILD = {
    "auf einen blick": STARTBILD,
    "in zwei minuten": STARTBILD,
    "wochenueberblick": STARTBILD,
    "das wichtigste": "kapitel-das-wichtigste",
    "die wichtigsten signale": "kapitel-meldungen",
    "die wichtigsten meldungen": "kapitel-meldungen",
    "europa": "kapitel-europa",
    "deutschland": "kapitel-deutschland",
    "lateinamerika": "kapitel-lateinamerika",
    "nordamerika": "kapitel-nordamerika",
    "asien": "kapitel-asien",
    "global": ERSATZBILD,
    "technologie, geräte & regulierung": "kapitel-technologie",
    "muster der woche": "kapitel-muster",
    "worauf wir warten": "kapitel-worauf-wir-warten",
}
AFRIKA_BILD = "kapitel-afrika-nahost"
UMBENANNT = {"Die wichtigsten Signale": "Die wichtigsten Meldungen"}
REGIONEN = (
    "europa",
    "lateinamerika",
    "nordamerika",
    "asien",
    "afrika",
    "naher osten",
    "nahost",
    "ozeanien",
    "global",
)

_H2 = re.compile(r'<h2 id="([^"]+)">(.*?)</h2>', re.S)
_TAG = re.compile(r"(<[^>]+>)")
_OHNE_TAGS = re.compile(r"<[^>]+>")
_ZAHL = re.compile(
    r"(?<![\w.,/-])(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?"
    r"((?:\s| )?(?:Prozentpunkte|Prozent|%|Mbit/s|Gbit/s|Gbps|MHz|GHz|GB|TB"
    r"|Mio\.|Millionen|Milliarden|Mrd\.|Euro|€|US-Dollar|Dollar|Punkte))(?![\w])"
)
_MONATE = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_PUNKT_DATUM = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})?")
_WORT_DATUM = re.compile(r"(\d{1,2})\.\s*([A-Za-zäÄ]+)(?:\s+(\d{4}))?")
_KURZJAHR = 2000


def bild_fuer(titel: str) -> str:
    """Das feste Kapitelbild zu einer Berichtsüberschrift."""
    schluessel = " ".join(titel.lower().split())
    if schluessel in KAPITEL_BILD:
        return KAPITEL_BILD[schluessel]
    if "afrika" in schluessel or "nahost" in schluessel or "naher osten" in schluessel:
        return AFRIKA_BILD
    if schluessel.startswith("roh-digest"):
        return STARTBILD
    return ERSATZBILD


def ist_region(titel: str) -> bool:
    """Ob eine Überschrift eine Weltregion benennt."""
    klein = titel.lower()
    return any(klein.startswith(r) for r in REGIONEN)


def zahlen_markieren(html: str) -> str:
    """Hüllt Zahlen mit Einheit in eine Markierung, die Seite hebt sie hervor.

    Nur Text zwischen Tags wird angefasst. Der Wert im Attribut ist dieselbe
    Zahl wie im Text, nur maschinenlesbar, damit die Seite sie einmal
    hochzählen kann und danach exakt den Originaltext zeigt.
    """
    teile = _TAG.split(html)
    for i, teil in enumerate(teile):
        if i % 2 == 1 or not teil:
            continue
        teile[i] = _ZAHL.sub(_zahl_huelle, teil)
    return "".join(teile)


def _zahl_huelle(treffer: re.Match) -> str:
    ganz, dezimal, einheit = treffer.group(1), treffer.group(2), treffer.group(3)
    wert = ganz.replace(".", "") + (f".{dezimal}" if dezimal else "")
    stellen = len(dezimal) if dezimal else 0
    zahl = ganz + (f",{dezimal}" if dezimal else "")
    return (
        f'<span class="zahl"><span class="zahl-wert" data-wert="{wert}" '
        f'data-stellen="{stellen}">{zahl}</span>{einheit}</span>'
    )


def kapitel(briefing_html: str) -> list[dict]:
    """Zerlegt den Bericht an seinen h2-Überschriften in Kapitel."""
    if not briefing_html:
        return []
    teile = _H2.split(briefing_html)
    vorlauf = teile[0].strip()
    liste: list[dict] = []
    for i in range(1, len(teile) - 2, 3):
        anker, kopf, koerper = teile[i], teile[i + 1], teile[i + 2]
        titel = html_lib.unescape(_OHNE_TAGS.sub("", kopf)).strip()
        liste.append(
            {
                "art": "text",
                "id": anker,
                "titel": UMBENANNT.get(titel, titel),
                "bild": bild_fuer(titel),
                "region": ist_region(titel),
                "wichtig": titel.lower() == "das wichtigste",
                "html": zahlen_markieren(koerper.strip()),
            }
        )
    if vorlauf and liste:
        liste[0]["html"] = zahlen_markieren(vorlauf) + liste[0]["html"]
    elif vorlauf:
        liste.append(
            {
                "art": "text",
                "id": "bericht",
                "titel": "Der Wochenbericht",
                "bild": STARTBILD,
                "region": False,
                "wichtig": True,
                "html": zahlen_markieren(vorlauf),
            }
        )
    if liste and not any(k["wichtig"] for k in liste):
        liste[0]["wichtig"] = True
    return liste


def szenen(
    kapitel_liste: list[dict],
    *,
    themen: bool,
    deutschland: bool,
    warten: bool,
    zwei_minuten: bool,
) -> list[dict]:
    """Die Reihenfolge der Szenen unter dem ersten Bildschirm.

    In zwei Minuten (falls vorhanden), Auf einen Blick, Themen der Woche, dann
    der Bericht. Deutschland folgt auf Europa, sonst auf die letzte Region.
    Worauf wir warten schließt ab.
    """
    folge: list[dict] = []
    if zwei_minuten:
        folge.append(
            {"art": "zwei", "id": "in-zwei-minuten", "titel": "In zwei Minuten"}
        )
    themen_szene = {
        "art": "themen",
        "id": "themen-der-woche",
        "titel": "Themen der Woche",
    }
    land = {
        "art": "deutschland",
        "id": "deutschland-fokus",
        "titel": "Deutschland",
        "bild": KAPITEL_BILD["deutschland"],
    }
    for k in kapitel_liste:
        folge.append(k)
        if themen and themen_szene not in folge:
            folge.append(themen_szene)
        if deutschland and land not in folge and k["titel"].lower() == "europa":
            folge.append(land)
    if deutschland and land not in folge:
        regionen = [i for i, s in enumerate(folge) if s.get("region")]
        stelle = regionen[-1] + 1 if regionen else len(folge)
        folge.insert(stelle, land)
    if themen and themen_szene not in folge:
        folge.append(themen_szene)
    if warten:
        folge.append(
            {
                "art": "warten",
                "id": "worauf-wir-warten",
                "titel": "Worauf wir warten",
                "bild": KAPITEL_BILD["worauf wir warten"],
            }
        )
    return folge


def frist_datum(text: str, bezug: str) -> date | None:
    """Liest das Enddatum einer Aktion aus ihrer Fristangabe.

    Erkannt werden ``2026-08-31``, ``31.08.2026``, ``31.08.`` und
    ``6. August 2026``. Fehlt das Jahr, gilt das Jahr des Stands. Was nicht
    erkannt wird, ist ``None`` und bekommt keine Markierung.
    """
    if not text:
        return None
    try:
        stand = date.fromisoformat(bezug[:10])
    except ValueError:
        return None
    treffer = _ISO.search(text)
    if treffer:
        return _datum(int(treffer[1]), int(treffer[2]), int(treffer[3]))
    treffer = _PUNKT_DATUM.search(text)
    if treffer:
        jahr = treffer[3]
        j = stand.year
        if jahr:
            j = int(jahr) + _KURZJAHR if len(jahr) == 2 else int(jahr)
        return _datum(j, int(treffer[2]), int(treffer[1]))
    treffer = _WORT_DATUM.search(text)
    if treffer and treffer[2].lower() in _MONATE:
        jahr = int(treffer[3]) if treffer[3] else stand.year
        return _datum(jahr, _MONATE[treffer[2].lower()], int(treffer[1]))
    return None


def _datum(jahr: int, monat: int, tag: int) -> date | None:
    try:
        return date(jahr, monat, tag)
    except ValueError:
        return None


def fristen_markieren(promo_view: dict | None, stand: str) -> None:
    """Markiert jede Aktionskarte, deren Frist in den nächsten Tagen endet."""
    if not promo_view:
        return
    try:
        heute = date.fromisoformat((stand or "")[:10])
    except ValueError:
        return
    grenze = heute + timedelta(days=ENDET_BALD_TAGE)
    eigen = (promo_view.get("eigen") or {}).get("karten") or []
    for karte in [*(promo_view.get("karten") or []), *eigen]:
        ende = frist_datum(karte.get("frist") or "", stand)
        karte["endet_bald"] = bool(ende and heute <= ende <= grenze)
        karte["neu"] = bool((karte.get("offer") or {}).get("neu"))


def fenster(
    ctx: dict,
    geraete: dict | None,
    promo_view: dict | None,
    promo_stand: str | None,
) -> dict:
    """Die drei Fenster des ersten Bildschirms: Meldung, Geräte, Promo."""
    return {
        "meldung": _meldungsfenster(
            ctx.get("front") or {}, ctx.get("highlights") or []
        ),
        "geraete": _geraetefenster(geraete),
        "promo": _promofenster(promo_view, promo_stand or ""),
    }


def _meldungsfenster(front: dict, highlights: list[dict]) -> dict | None:
    aufmacher = (front or {}).get("aufmacher")
    if not aufmacher:
        return None
    return {"h": aufmacher, "anzahl": len(highlights)}


def _geraetefenster(geraete: dict | None) -> dict | None:
    zeitreihe = (geraete or {}).get("zeitreihe") or {}
    block = zeitreihe.get("start_block")
    if not block:
        return None
    daten = zeitreihe.get("daten") or {}
    baender = zeitreihe.get("baender") or {}
    band = block.get("band", "")
    modell = block.get("modell")
    return {
        "modell": (daten.get("titel") or {}).get(modell, modell),
        "band": (baender.get(band) or {}).get("label", band),
        "laufzeit": block.get("laufzeit"),
        "leitzahl_html": block.get("leitzahl_html") or "",
        "antwort_html": block.get("antwort_html") or "",
        "anbieter": block.get("anbieter") or [],
        "stand": (geraete or {}).get("abgerufen_bis") or "",
    }


def _promofenster(promo_view: dict | None, stand: str) -> dict | None:
    karten = (promo_view or {}).get("karten") or []
    if not karten:
        return None
    beste = max(
        karten,
        key=lambda k: (bool(k.get("highlight")), k.get("score") or 0),
    )
    return {
        "karte": beste,
        "neu": sum(1 for k in karten if k.get("neu")),
        "endet_bald": sum(1 for k in karten if k.get("endet_bald")),
        "aktiv": (promo_view or {}).get("active_total"),
        "stand": stand,
    }


def meldung_id(h: dict) -> str:
    """Ein stabiler Anker je Meldung, aus ihrer Adresse - fuer Links aus Mails."""
    adresse = (h.get("url") or h.get("schlagzeile") or "").encode("utf-8")
    return "m-" + hashlib.sha1(adresse, usedforsecurity=False).hexdigest()[:10]


VORLAGEN_HELFER = {
    "szenen": szenen,
    "meldung_id": meldung_id,
    "MIND_BREITE_GROSS": MIND_BREITE_GROSS,
}
