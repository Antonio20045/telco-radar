"""Aus Bericht-JSON und Promo-Speicher werden `Eintrag`e.

Die Uebersetzung steht an EINER Stelle, weil die beiden Quellen nicht ein
einziges Feld gleich benennen: die Meldung hat `headline`/`source`/`region`,
die Aktion `headline`/`brand`/nichts. Wer das im Renderer noch einmal
uebersetzt, hat zwei Fassungen davon, was ein "Absender" ist.

**Hier entsteht kein Text.** Titel und Zusammenfassung werden uebernommen,
nicht formuliert - das ist die Bedingung dafuer, dass der Test in N3 jeden
inhaltstragenden Block als Teilstring im Quell-JSON wiederfindet. Gekuerzt
wird erst beim Rendern, und dann nur an Wortgrenzen.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..textwerkzeug import slug
from .filters import Eintrag

_IST_PLATZHALTER = re.compile(
    r"(kein|keine|k\.?a\.?|n/a|none|branche|mehrere|verschiedene|divers)\b.*", re.I
)

_THEMENFELD_REGION = "global"
GEWICHT_JE_CTM_STUFE = 10
PROMO_SCORE_TEILER = 3
PROMO_REGION = "europa"
PROMO_RESSORT = "tarife"
_BEKANNTE_REGIONEN = {
    "europa",
    "nordamerika",
    "lateinamerika",
    "afrika-naher-osten",
    "asien",
    "ozeanien",
    "global",
}


def region_schluessel(label: str) -> str:
    s = slug(label or "")
    return s if s in _BEKANNTE_REGIONEN else _THEMENFELD_REGION


def aus_bericht(bericht: dict, *, bericht_url: str = "") -> list[Eintrag]:
    """Die Meldungen einer Ausgabe.

    Erwartet die Form von `data/reports/<datum>.json`. Bewusst NICHT
    `report/html._flatten()`: das Modul zieht den halben Renderer nach sich
    (Bilder, Ressortlabels, Explorer-JSON) und lebt im oeffentlichen Repo -
    der Versand laeuft im privaten. Was der Newsletter davon braucht, ist
    das Ressort, und das ist eine Zuordnung von Kategorien.
    """
    from ..report.html import _ressort, _schlagzeile

    datum = bericht.get("date") or ""
    aus: list[Eintrag] = []
    for region_label, region in (bericht.get("regions") or {}).items():
        for h in region.get("highlights") or []:
            url = h.get("url") or ""
            if not url:
                continue
            betreiber = (h.get("operator") or "").strip()
            if _IST_PLATZHALTER.fullmatch(betreiber):
                betreiber = ""
            try:
                ctm = int(h.get("ctm_bezug"))
            except (TypeError, ValueError):
                ctm = 1
            try:
                relevanz = int(h.get("relevance") or 0)
            except (TypeError, ValueError):
                relevanz = 0
            aus.append(
                Eintrag(
                    id=f"markt:{_id_aus_url(url)}",
                    bereich="marktrecherche",
                    titel=_schlagzeile(h),
                    text=h.get("summary") or "",
                    url=url,
                    absender=h.get("source")
                    or urlsplit(url).netloc.removeprefix("www."),
                    region=region_schluessel(region_label),
                    ressort=_ressort(h),
                    betreiber=betreiber,
                    gewicht=ctm * GEWICHT_JE_CTM_STUFE + relevanz,
                    datum=h.get("date") or datum,
                    anker=f"{bericht_url}#{slug(region_label)}" if bericht_url else "",
                )
            )
    return aus


def aus_promo(
    entries, *, marken_anker: dict | None = None, nur_aktiv: bool = True
) -> list[Eintrag]:
    """Die laufenden Aktionen aus `data/state/promo_db.json`.

    `nur_aktiv` haelt ausgelaufene Aktionen heraus - eine Mail, die auf ein
    abgelaufenes Angebot zeigt, ist schlechter als eine ohne diesen Eintrag.
    """
    anker = marken_anker or {}
    aus: list[Eintrag] = []
    for e in entries or []:
        if nur_aktiv and (e.get("status") or "") != "aktiv":
            continue
        url = e.get("url") or ""
        marke = (e.get("brand") or "").strip()
        try:
            score = int(e.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        aus.append(
            Eintrag(
                id=f"promo:{e.get('id') or _id_aus_url(url)}",
                bereich="promo",
                titel=e.get("headline") or marke,
                text=e.get("description") or "",
                url=url,
                absender=marke,
                region=PROMO_REGION,
                ressort=PROMO_RESSORT,
                betreiber=marke,
                gewicht=score // PROMO_SCORE_TEILER,
                datum=e.get("last_verified") or e.get("first_seen") or "",
                anker=anker.get(marke, ""),
            )
        )
    return aus


def _id_aus_url(url: str) -> str:
    import hashlib

    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:16]
