"""Anzeige-Vorbereitung fuer die Differenzierungs-Seite (reine
Datenaufbereitung, kein LLM - Muster: report/promo.py).

Die Frage der Seite ist eine einzige: **womit heben sich Telkos ab, jenseits
von Preis und Datenvolumen?** Antonio am 08.08.2026: "Es geht darum, was
Telco-Unternehmen weltweit tun, um sich JENSEITS von Preis und Gigabytes zu
differenzieren - zusaetzliche externe Services usw. ... Genau sowas will ich
als Radar auf dem Schirm haben, als Inspiration von allen Telco-Unternehmen
der Welt."

Ein Radar zeigt Beispiele, keinen Essay. Daraus folgt die Gliederung:

    NEU AUF DEM RADAR   die juengsten Funde, prominent - das ist der
                        Nachrichtenwert der Seite. Gibt es keine, stehen
                        stattdessen die zuletzt nachgeprueften.
    BIBLIOTHEK          je Hebel eine Rubrik, darunter die Beispiele als
                        gleich gebaute Karten. Ein Hebel ohne Beispiele
                        erscheint NICHT - ein leerer Kasten sagt nichts.

**Der Grund, warum es dieses Modul gibt: die Seite las bis zum 08.08.2026 nur
EINEN der zwei vorhandenen Speicher.**

    differentiation_db.json   (DiffDB, analyze/category_sweep) - der
                              rotierende Web-Sweep. Wurde gerendert.
    differentiation.jsonl     (DiffStore, analyze/diff_curator) - der Kurator
                              ueber den woechentlichen Presse-Crawl. Wurde
                              NICHT gerendert; er lief jede Woche umsonst.

Beide beschreiben dasselbe (ein belegter Differenzierungs-Move mit Quelle),
nur in zwei Feldnamen-Dialekten. `merge()` fuehrt sie auf EINEN Bestand
zusammen; bei gleicher URL gewinnt der DiffDB-Eintrag, weil seine Felder
bereits fuer die Anzeige geschrieben sind (`what` ist dort ein fertiger
deutscher Satz, kein Rohtitel).

**Warum die Hauptzeile eines Presse-Eintrags aus `summary` kommt und nicht
aus `title`:** gemessen am Bestand vom 08.08.2026 sind die Originaltitel
mehrsprachig und tragen oft ein angehaengtes Datum - "Akses Nonton Piala
Dunia FIFA 2026 Lebih Fleksibel und Terjangkau, Telkomsel Hadirkan Paket
Bundling Eksklusif bersama FOLA PLAY 13 Jun 2026". Auf einer deutschen Seite
fuer Leser ohne Technik-Hintergrund (CLAUDE.md §8) ist das keine
Schlagzeile. `summary` ist der deutsche Satz, der beschreibt, worum es geht -
also genau die Rolle, die `what` im DiffDB-Eintrag hat. Nur so sehen die
Karten beider Herkuenfte gleich aus, und Vergleichen heisst Gleiches
nebeneinander legen. Der Originaltitel geht nicht verloren: die Hauptzeile
verlinkt auf die Quelle.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from ..models import normalize_url
from ..textwerkzeug import ohne_vodafone_rat

# Wie lange ein Eintrag als "neu" gilt, gerechnet ab dem Stand der Ausgabe.
# Zehn Tage, weil die Pipeline zweimal die Woche laeuft: ein Fund bleibt so
# ueber mindestens zwei Ausgaben sichtbar und verschwindet nicht, bevor ihn
# jemand gesehen hat.
NEU_TAGE = 10
# Wie viele Karten oben stehen. Sechs fuellen bei 1440 px zwei Reihen zu
# dritt - mehr waere wieder eine Kachelwand.
MAX_NEU = 6


# Woerter, nach denen ein Punkt KEIN Satzende ist. Ohne diese Liste endete
# "AT&T Guarantee: Gutschriften bei Ausfaellen, auf rund 50 Mio. Kunden
# ausgeweitet." nach "50 Mio." - drei von 51 Bestandssaetzen traf das.
_ABKUERZUNGEN = {"Mio", "Mrd", "Nr", "ca", "bzw", "inkl", "exkl", "evtl",
                 "ggf", "usw", "vgl", "bspw", "Bsp", "Abb", "Dr", "Prof",
                 "St", "Str", "Jh", "Tsd"}
_MOEGLICHES_SATZENDE = re.compile(r"[.!?](?=\s+[A-ZÄÖÜ„])")
_LETZTES_WORT = re.compile(r"[\wÄÖÜäöüß]+$")


def _text(wert) -> str:
    return " ".join(str(wert or "").split()).strip()


def erster_satz(text: str) -> str:
    """Der erste vollstaendige Satz eines Fliesstextes.

    Eine Karte traegt eine Aussage, keinen Absatz. Der Presse-Zweig liefert
    aber Zusammenfassungen und Begruendungen aus zwei bis drei Saetzen; die
    zweite Haelfte ist regelmaessig der Nachsatz ("Vodafone sollte pruefen,
    ob ..."), der auf einer Uebersichtsseite nichts entscheidet.

    Das ist ausdruecklich KEIN Kuerzen: was stehen bleibt, ist ein
    vollstaendiger Satz mit Schlusspunkt, nie ein abgebrochener mit "…"
    (CLAUDE.md §5, Abnahmekriterium 5).
    """
    text = _text(text)
    for treffer in _MOEGLICHES_SATZENDE.finditer(text):
        wort = _LETZTES_WORT.search(text[:treffer.start()])
        wort = wort.group(0) if wort else ""
        # Einzelbuchstaben und Versalien sind Initialen oder Kuerzel
        # ("z.B.", "U.S."), kein Satzende.
        if len(wort) < 2 or wort.isupper() or wort in _ABKUERZUNGEN:
            continue
        return text[:treffer.end()]
    return text


def _domain(url: str) -> str:
    return urlsplit(url or "").netloc.removeprefix("www.")


def _aus_db(e: dict) -> dict:
    """Ein Sweep-Eintrag - er ist bereits in Anzeigeform geschrieben."""
    return {
        "theme": e.get("theme") or "",
        "operator": _text(e.get("operator")),
        "region": _text(e.get("region")),
        "what": _text(e.get("what")),
        "why": ohne_vodafone_rat(_text(e.get("why"))),
        "url": e.get("url") or "",
        "source": _domain(e.get("url")) or _text(e.get("source")),
        "date": e.get("date") or "",
        "first_seen": e.get("first_seen") or "",
        "last_verified": e.get("last_verified") or e.get("first_seen") or "",
        "herkunft": "sweep",
    }


def _aus_store(e: dict) -> dict:
    """Ein Kurator-Eintrag aus dem Presse-Crawl, auf dieselbe Kartenform
    gebracht (Feldbegruendung siehe Modulkopf)."""
    return {
        "theme": e.get("theme") or "",
        "operator": _text(e.get("operator")),
        "region": _text(e.get("region")),
        "what": erster_satz(e.get("summary")) or _text(e.get("title")),
        # Erst den Rat streichen, dann kuerzen: steht der Ratschlag im
        # ERSTEN Satz, nimmt die umgekehrte Reihenfolge den Befund mit.
        "why": erster_satz(ohne_vodafone_rat(e.get("why_it_matters"))),
        "url": e.get("url") or "",
        "source": _domain(e.get("url")) or _text(e.get("source")),
        "date": e.get("date") or "",
        "first_seen": e.get("first_seen") or "",
        # Der Presse-Zweig verifiziert nicht nach; der Fund IST die Pruefung.
        "last_verified": e.get("first_seen") or "",
        "herkunft": "presse",
    }


def merge(db_entries, store_entries) -> list[dict]:
    """Beide Speicher zu einem Bestand. Bei gleicher URL gewinnt die DiffDB.

    Verglichen wird die NORMALISIERTE URL, nicht die rohe - dieselbe Meldung
    steht in den zwei Speichern schon einmal mit und einmal ohne "www."
    (`models.normalize_url` ist derselbe Schluessel, den beide Speicher
    intern zum Deduplizieren benutzen).
    """
    bestand: dict[str, dict] = {}
    for roh in db_entries or []:
        eid = normalize_url(roh.get("url") or "") or roh.get("id")
        if eid:
            bestand[eid] = _aus_db(roh)
    for roh in store_entries or []:
        eid = normalize_url(roh.get("url") or "") or roh.get("id")
        if eid and eid not in bestand:
            bestand[eid] = _aus_store(roh)
    return list(bestand.values())


def _neuheitsgrenze(stichtag: str, tage: int = NEU_TAGE) -> str:
    try:
        return (datetime.fromisoformat(stichtag)
                - timedelta(days=tage)).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _juengste_zuerst(e: dict) -> tuple:
    return (e.get("first_seen") or "", e.get("last_verified") or "",
            e.get("operator") or "")


def aufbereiten(db_entries, store_entries, themes, stichtag: str,
                farben: dict | None = None) -> dict:
    """Der fertige Seitenzustand: Hebel-Rubriken plus die Karten oben.

    `themes` ist die Hebel-Liste (key, label) aus analyze/category_sweep -
    sie gibt die Reihenfolge der Rubriken vor. `farben` bildet Hebel auf die
    Akzentfarbe ab; sie erscheint nur als schmale Linie, nie als Flaeche
    (CLAUDE.md §5).
    """
    farben = farben or {}
    grenze = _neuheitsgrenze(stichtag)
    bestand = merge(db_entries, store_entries)
    for e in bestand:
        e["neu"] = bool(grenze and (e.get("first_seen") or "") > grenze)

    label_map = dict(themes)
    hebel = []
    for key, label in themes:
        eintraege = sorted((e for e in bestand if e.get("theme") == key),
                           key=_juengste_zuerst, reverse=True)
        if not eintraege:
            # Ein Hebel ohne Beispiel steht nicht auf der Seite. "Noch keine
            # bestaetigten Beispiele" war zwoelfmal derselbe leere Kasten.
            continue
        for e in eintraege:
            e["hebel_label"] = label
            e["farbe"] = farben.get(key, "")
        hebel.append({"key": key, "label": label, "n": len(eintraege),
                      "farbe": farben.get(key, ""), "eintraege": eintraege})

    # Hebel, die es (noch) nicht in die Liste geschafft haben, tragen trotzdem
    # ihr Etikett - die Karten oben mischen alle Hebel und nennen ihren.
    for e in bestand:
        e.setdefault("hebel_label", label_map.get(e.get("theme"), ""))
        e.setdefault("farbe", farben.get(e.get("theme"), ""))

    neu = sorted((e for e in bestand if e["neu"]),
                 key=_juengste_zuerst, reverse=True)[:MAX_NEU]
    rueckfall = not neu
    if rueckfall:
        # Eine ruhige Woche darf die Seite nicht enthaupten. Dann stehen oben
        # die zuletzt nachgeprueften Beispiele - und die Ueberschrift sagt es.
        neu = sorted(bestand, key=lambda e: (e.get("last_verified") or "",
                                             e.get("first_seen") or ""),
                     reverse=True)[:MAX_NEU]

    return {"bestand": bestand, "hebel": hebel, "neu": neu,
            "neu_ist_rueckfall": rueckfall, "gesamt": len(bestand),
            "n_hebel": len(hebel)}
