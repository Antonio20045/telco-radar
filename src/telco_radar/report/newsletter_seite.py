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

from ..newsletter.config import (
    FELD_JE_DIMENSION,
    MELDUNGEN,
    NUR_MELDUNGEN,
    NewsletterKatalog,
)
from . import rechtstexte

LEER_HEISST_ALLES = "Nichts angekreuzt heißt: alles."

REIHENFOLGE = ("bereiche", "wettbewerber", "regionen", "kategorien")
"""Wettbewerber gilt fuer alle Bereiche und steht deshalb vor den zwei
Achsen, die nur Meldungen einschraenken (`NUR_MELDUNGEN`)."""

LABEL = {
    "bereiche": "Bereiche",
    "regionen": "Regionen",
    "wettbewerber": "Anbieter",
    "kategorien": "Themen",
}

MARKE = {"1und1": "1-1"}
"""Wettbewerber-Schluessel, deren Farbklasse `gr-anb--<slug>` anders heisst."""


def dimensionen(katalog: NewsletterKatalog) -> list[dict]:
    """Die vier Achsen fuer die Vorlage, in der Reihenfolge `REIHENFOLGE`."""
    aus = []
    for dimension in REIHENFOLGE:
        aus.append(
            {
                "key": dimension,
                "feld": FELD_JE_DIMENSION[dimension],
                "label": LABEL[dimension],
                "nur_meldungen": dimension in NUR_MELDUNGEN,
                "optionen": [
                    {
                        "key": a.key,
                        "label": a.label,
                        "marke": MARKE.get(a.key, a.key)
                        if dimension == "wettbewerber"
                        else "",
                    }
                    for a in katalog.eintraege(dimension)
                ],
            }
        )
    return aus


def konfiguration(katalog: NewsletterKatalog, *, dienst_url: str, frei: bool) -> str:
    """Was `app.js` ueber das Formular wissen muss - als JSON im Seitenkopf.

    Bewusst KEIN zweiter Ort fuer die Grenzen: sie stehen in
    `config/newsletter.yaml`, werden hier gerechnet und im Browser nur
    gelesen. Zwei Zahlen fuer dieselbe Grenze waeren zwei Grenzen, und die
    strengere gaebe es nur auf einer Seite.
    """
    return json.dumps(
        {
            "dienst": dienst_url.rstrip("/"),
            "meldungen": MELDUNGEN,
            "frei": bool(frei),
            "max_stichwoerter": katalog.grenzen.max_stichwoerter,
            "min_laenge": katalog.grenzen.min_stichwort_laenge,
            "warnung_ab": katalog.grenzen.vorschau_warnung_ab,
            "vorschau_tage": katalog.grenzen.vorschau_tage,
        },
        ensure_ascii=False,
    )


_ABSCHLUSS = {
    "bestaetigt": (
        "Angemeldet",
        "Die nächste Ausgabe kommt nach dem nächsten Radar-Lauf, "
        "wenn es zu Ihren Themen etwas Neues gibt.",
        "Zum Portal",
    ),
    "abgemeldet": (
        "Abgemeldet",
        "Sie bekommen keine weiteren Ausgaben. Ihre E-Mail-Adresse wird gelöscht.",
        "Zum Portal",
    ),
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
