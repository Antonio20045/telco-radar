"""Die Anmeldeseite und ihre zwei Bestaetigungsseiten.

Drei Seiten, und die zwei kleinen sind die wichtigeren:

`newsletter-bestaetigt.html` und `newsletter-abgemeldet.html` sind **statisch
und kommen ohne den Signup-Dienst aus.** Das ist der Punkt: Render Free faehrt
den Dienst nach 15 Minuten ohne Verkehr herunter, und das Aufwachen dauert
rund eine Minute. Wer auf den Abmeldelink klickt, waehrend der Dienst
schlaeft, wartet sonst vor einem Spinner oder sieht einen Fehler - **und
haelt sich trotzdem fuer abgemeldet.** Der Abmeldelink ist nach Festlegung 5
der EINZIGE Weg; er muss also im kalten Zustand tragen.

Die Anmeldeseite selbst geht erst online, wenn Impressum und
Datenschutzerklaerung vollstaendig sind (`rechtstexte.vollstaendig()`). Bis
dahin wird sie gebaut, sagt sichtbar warum sie gesperrt ist, und steht nicht
in der Navigation - dieselbe Veroeffentlichungsschwelle wie bei der
Geraeteseite.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..newsletter.config import FELD_JE_DIMENSION, NewsletterKatalog
from . import rechtstexte

# Der Satz, der neben jeder Dimension steht. "Leer heisst alles" ist die
# Erwartung fast aller Nutzer - und es ist NICHT die Erwartung der anderen,
# deshalb steht es da. Das ist keine Bedienhilfe, sondern die Regel selbst.
_LEER = "Nichts angekreuzt = alles."

HINWEISE = {
    "bereiche": f"Welche Rubrik des Portals. {_LEER}",
    "regionen": f"Welche Weltregionen. {_LEER}",
    "wettbewerber": ("Nur Meldungen, in denen einer dieser Anbieter vorkommt. "
                     + _LEER),
    "kategorien": f"Worum es gehen soll. {_LEER}",
}


def dimensionen(katalog: NewsletterKatalog) -> list[dict]:
    """Die vier Achsen fuer die Vorlage - Reihenfolge wie im Katalog."""
    label = {"bereiche": "Bereich", "regionen": "Regionen",
             "wettbewerber": "Wettbewerber", "kategorien": "Themen"}
    aus = []
    for dimension, feld in FELD_JE_DIMENSION.items():
        aus.append({
            "key": dimension,
            "feld": feld,
            "label": label[dimension],
            "hinweis": HINWEISE[dimension],
            "optionen": [{"key": a.key, "label": a.label}
                         for a in katalog.eintraege(dimension)],
        })
    return aus


def konfiguration(katalog: NewsletterKatalog, *, dienst_url: str,
                  frei: bool) -> str:
    """Was `app.js` ueber das Formular wissen muss - als JSON im Seitenkopf.

    Bewusst KEIN zweiter Ort fuer die Grenzen: sie stehen in
    `config/newsletter.yaml`, werden hier gerechnet und im Browser nur
    gelesen. Zwei Zahlen fuer dieselbe Grenze waeren zwei Grenzen, und die
    strengere gaebe es nur auf einer Seite.
    """
    return json.dumps({
        "dienst": dienst_url.rstrip("/"),
        "frei": bool(frei),
        "max_stichwoerter": katalog.grenzen.max_stichwoerter,
        "min_laenge": katalog.grenzen.min_stichwort_laenge,
        "warnung_ab": katalog.grenzen.vorschau_warnung_ab,
        "vorschau_tage": katalog.grenzen.vorschau_tage,
    }, ensure_ascii=False)


# ============================================  die zwei statischen Seiten ==

_ABSCHLUSS = {
    "bestaetigt": (
        "Anmeldung bestätigt",
        "Du bekommst den Telco Radar ab der nächsten Ausgabe — dienstags "
        "oder freitags, und nur dann, wenn es zu deinen Themen wirklich "
        "etwas Neues gibt.",
        "Zur aktuellen Ausgabe"),
    "abgemeldet": (
        "Abgemeldet",
        "Du bekommst keine weiteren Ausgaben, deine E-Mail-Adresse wird "
        "gelöscht. Du kannst dich jederzeit wieder anmelden.",
        "Zur aktuellen Ausgabe"),
}


def abschlussseiten() -> dict[str, tuple[str, str, str]]:
    return dict(_ABSCHLUSS)


def einwilligung_absaetze(text: str) -> list[str]:
    """Den Einwilligungstext in Absaetze, ohne die Umbrueche der Quelldatei.

    `content/consent_texts/*.md` ist auf 78 Zeichen umbrochen - so schreibt
    man Textdateien. Auf der Seite steht der Text aber in einer Spalte von
    58 Zeichen, und die harten Umbrueche der Datei stehen dann quer dazu: im
    Screenshot vom 11.08.2026 brach jede zweite Zeile mittendrin ab und sah
    aus wie ein Satzfehler.

    Gerechnet, nicht mit `white-space: pre-line` geloest - der Wortlaut
    bleibt identisch, nur der Umbruch gehoert dem Browser.
    """
    absaetze = []
    for block in (text or "").strip().split("\n\n"):
        zusammen = " ".join(z.strip() for z in block.splitlines() if z.strip())
        if zusammen:
            absaetze.append(zusammen)
    return absaetze


def seite_frei(root: Path) -> bool:
    """Darf die Seite Adressen entgegennehmen?

    Dieselbe Schwelle, die auch den Navigationseintrag schaltet - gerechnet
    an einer Stelle, damit Formular und Navigation nicht auseinanderlaufen
    koennen.
    """
    return rechtstexte.vollstaendig(root)
