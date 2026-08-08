"""Der siteweite Suchindex - die Datengrundlage der Dossier-Seite.

Antonio am 08.08.2026: *"Die Suchfunktion ist total bescheuert. Wenn ich was
suche, werde ich auf die Unterseite Meldungen weitergeleitet ... Wenn ich suche,
zum Beispiel Telekom oder Perplexity, alle Meldungen super dargestellt, dass ich
einen Ueberblick habe ueber die Entwicklung, auch ueber die Historie. Ich moechte
auch die Meldungen nicht von diesem Band, sondern alle sehen, die mit diesem
Thema zu tun hatten."*

Zwei Dinge folgen daraus, und beide sitzen hier statt in der Vorlage:

1. **Vollstaendigkeit.** Der Index traegt alles, was das Portal ueber ein Thema
   weiss: die bewerteten Meldungen ALLER Ausgaben, die Differenzierungs-
   Bibliothek und die Promo-Aktionen. Bis dahin waren es zwei der drei Quellen
   und die Promo-Seite war unauffindbar - wer "Telekom" suchte, sah nichts von
   den laufenden Aktionen der Marke.
2. **Bilder.** Eine Trefferliste aus grauem Text ist kein Ueberblick. Jede
   Meldung traegt ihr bereits geholtes Bild in den Index; die Dossier-Seite
   baut daraus Karten in derselben Gewichtung wie die Meldungsseite.

Die **Ueberschrift kommt aus `schlagzeile`**, nicht aus `de_title`. Der Rest des
Portals zeigt seit dem 06.08.2026 diese eine Zeile (`html._schlagzeile`), und
zwei verschiedene Ueberschriften fuer dieselbe Meldung sind ein Fehler, den man
erst bemerkt, wenn man beide Seiten nebeneinander legt.

Gesucht wird im Browser (`app.js`), nicht hier - es gibt keinen Suchserver. Der
Index ist ein JSON-Array, das die Seite einmal laedt und dann filtert.
"""
from __future__ import annotations

from urllib.parse import urlsplit

# Die drei Bereiche. Die Reihenfolge ist die der Filterleiste.
BEREICHE = (
    ("bericht", "Meldungen"),
    ("differenzierung", "Differenzierung"),
    ("promo", "Aktionen"),
)


def _text(wert) -> str:
    return " ".join(str(wert or "").split()).strip()


def _domain(url: str) -> str:
    return urlsplit(url or "").netloc.removeprefix("www.")


def _bild(quelle: dict, ordner: str = "images") -> dict:
    """Die Bildfelder eines Eintrags, relativ zum Site-Wurzelverzeichnis.

    Leer, wenn kein Bild da ist - die Vorlage setzt dann eine Schriftkachel.
    Der Pfad steht fertig im Index, damit `app.js` nicht wissen muss, aus
    welchem Ordner welche Gattung ihre Bilder bezieht.
    """
    name = quelle.get("image")
    if not name:
        return {}
    return {"image": f"{ordner}/{name}",
            "image_w": quelle.get("image_w") or 0,
            "image_h": quelle.get("image_h") or 0}


def eintrag_bericht(h: dict, report_date: str) -> dict:
    """Eine bewertete Meldung einer Ausgabe."""
    return {
        "kind": "bericht",
        "title": _text(h.get("schlagzeile") or h.get("title")
                       or h.get("de_title")),
        "summary": _text(h.get("summary")),
        "operator": _text(h.get("operator") or h.get("source_label")),
        "region": _text(h.get("region")),
        "category": _text(h.get("ressort_label") or h.get("category")),
        # Das Datum der MELDUNG, nicht der Ausgabe - eine Chronik, die nach
        # Ausgabetagen sortiert, zeigt vier Ereignisse desselben Tages, die in
        # Wahrheit drei Wochen auseinanderliegen. Fehlt es, traegt der
        # Ausgabetag den Eintrag; ohne Datum faellt er aus dem Verlauf.
        "date": _text(h.get("date")) or report_date,
        "relevance": h.get("relevance") or 0,
        "source_label": _text(h.get("source_label") or h.get("source")
                              or _domain(h.get("url"))),
        "url": h.get("url") or "",
        "deep_link": f"reports/{report_date}.html",
        **_bild(h),
    }


def eintrag_differenzierung(e: dict, hebel_label: str) -> dict:
    """Ein Beispiel aus der Differenzierungs-Bibliothek."""
    theme = e.get("theme") or ""
    return {
        "kind": "differenzierung",
        "title": _text(e.get("what")),
        "summary": _text(e.get("why")),
        "operator": _text(e.get("operator")),
        "region": _text(e.get("region")),
        "category": _text(hebel_label or theme),
        "date": _text(e.get("first_seen") or e.get("last_verified")),
        # Die Bibliothek bewertet nicht nach Dringlichkeit. 3 heisst hier
        # "beobachten" und haelt die Beispiele in der Chronik zwischen den
        # dringenden und den beilaeufigen Meldungen.
        "relevance": 3,
        "source_label": _text(e.get("source") or _domain(e.get("url"))),
        "url": e.get("url") or "",
        "deep_link": f"differenzierung.html#dz-theme-{theme}",
        **_bild(e),
    }


def eintrag_promo(a: dict, mechanik_label: str, marken_anker: str) -> dict:
    """Eine Promo-Aktion einer deutschen Marke."""
    ausgelaufen = (a.get("status") or "") == "ausgelaufen"
    return {
        "kind": "promo",
        "title": _text(a.get("headline")),
        "summary": _text(a.get("description")),
        "operator": _text(a.get("brand")),
        "region": "Deutschland",
        "category": _text(mechanik_label) or "Aktion",
        "date": _text(a.get("first_seen") or a.get("last_verified")),
        "relevance": 2 if ausgelaufen else 4,
        "status": "ausgelaufen" if ausgelaufen else "",
        "source_label": _domain(a.get("url")) or _text(a.get("brand")),
        "url": a.get("url") or "",
        "deep_link": f"promo/index.html#{marken_anker}" if marken_anker
        else "promo/index.html",
        **_bild(a, "promo/images"),
    }


def marken_anker(name: str) -> str:
    """Sprungziel eines Markenblocks auf der Promo-Uebersicht.

    Bewusst hier und nicht in `promo.py`: der Index schreibt den Link, die
    Vorlage setzt den Anker - laufen die zwei auseinander, springt die Suche
    ins Leere. Ein Ort, zwei Aufrufer.
    """
    rein = []
    for zeichen in _text(name).lower():
        if zeichen.isalnum():
            rein.append(zeichen)
        elif rein and rein[-1] != "-":
            rein.append("-")
    return "marke-" + "".join(rein).strip("-")


def bauen(wochen: list[dict], diff_bestand: list[dict],
          hebel_label: dict[str, str], promo_aktionen: list[dict] | None = None,
          mechanik_label: dict[str, str] | None = None) -> list[dict]:
    """Der komplette Index.

    `wochen` ist die Liste `[{"date": ..., "highlights": [...]}]`, die
    `render_site()` beim Rendern der Wochenseiten ohnehin aufbaut - die
    Highlights sind dort schon durch `_flatten()` gelaufen und tragen
    `schlagzeile`, `ressort_label` und die Bildfelder.
    """
    mechanik_label = mechanik_label or {}
    out: list[dict] = []
    for woche in wochen:
        for h in woche.get("highlights") or []:
            # `why_it_matters` ist die interne Analystennotiz und gehoert nicht
            # in eine Datei, die der Browser laedt.
            oeffentlich = {k: v for k, v in h.items() if k != "why_it_matters"}
            out.append(eintrag_bericht(oeffentlich, woche["date"]))
    for e in diff_bestand or []:
        out.append(eintrag_differenzierung(
            e, hebel_label.get(e.get("theme") or "", e.get("theme") or "")))
    for a in promo_aktionen or []:
        if not (a.get("headline") and a.get("url")):
            continue
        out.append(eintrag_promo(
            a, mechanik_label.get(a.get("mechanic") or "", ""),
            marken_anker(a.get("brand") or "")))
    return out


def haeufigste_absender(index: list[dict], anzahl: int = 12) -> list[str]:
    """Die meistgenannten Absender - der Einstieg auf der leeren Suchseite.

    Eine leere Suchseite mit einem blinkenden Cursor ist eine Aufforderung,
    sich selbst etwas auszudenken. Diese Liste sagt stattdessen, worueber das
    Archiv ueberhaupt etwas weiss.

    Gezaehlt werden nur die redaktionellen Bereiche. Die Promo-Aktionen sind
    256 von 1060 Eintraegen und alle deutsch: gezaehlt man sie mit, stuenden
    dort winSIM und simplytel vor AT&T und Reliance Jio - eine Rangliste der
    beobachteten Aktionsseiten, nicht der Themen des Archivs.
    """
    from collections import Counter
    zaehler: Counter = Counter()
    for e in index:
        if e.get("kind") == "promo":
            continue
        name = e.get("operator") or ""
        # Sammelbezeichnungen sind kein Absender, nach dem man sucht.
        if len(name) < 3 or name.lower() in {"branche", "diverse", "mehrere"}:
            continue
        zaehler[name] += 1
    return [name for name, _ in zaehler.most_common(anzahl)]
