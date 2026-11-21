"""Zweiter sichtbarer Kaufweg bei o2: Tarifübersicht -> „Handy hinzufügen“.

Antonio, 21.11.2026: die Geräteseite zeigt nur, was ein Kunde bei o2 selbst wählen
und kaufen kann: die Tarifkacheln der Produktseite UND die Tarife der Tarifübersicht
(https://www.o2online.de/tarife/) mit „Handy hinzufügen“ (Befund
``berichte/o2-nicht-plus.md``). Der o2-Sammler bildet Bündel nach derselben
Definition.

Identität (Prüfung PR 205, Runde 3): Der Tarifname kommt von der Kachel der Übersicht
selbst (``lesen_seiten.o2_tarifuebersicht``), nie aus dem Bestand. Ein gemessener
Tarif gehört zu einer Kachel, wenn sein Grundtarif ihr gleicht oder nur „mit …“
anhängt (``passt``); passt er zu mehreren, ist er „nicht eindeutig zuordenbar“.

Der zweite Weg nennt weder Speicher noch Laufzeit und nicht, welche Geräte er führt.
Darum gibt er kein Soll für den Lückenzähler vor: ein gemessener Preis eines gelesenen
Geräts, dessen Tarif auf der Produktseite fehlt, aber zu einer Kachel passt, gilt als
angeboten (``soll_dazu``, Ebene Modell × Tarif bestätigt; Speicher/Laufzeit dieses
Kaufwegs nicht gezählt). Fällt die Übersicht aus, werden solche Preise nicht
verglichen („Kaufweg Tarifübersicht heute nicht geprüft“), nie als „nicht angeboten“
gezählt.
"""

from __future__ import annotations

from collections import Counter

from .. import geraete_angebot as ga
from ..geraete_tarifschluessel import grundtarif, kern, ohne_variante
from ..geraete_vollstaendigkeit import modell_der_kombination
from .gruende import NICHT_EINDEUTIG
from .lesen_seiten import O2_TARIFUEBERSICHT

ART_PRODUKTSEITE = "browser_auswahl"
ART_TARIFUEBERSICHT = "browser_tarifuebersicht"
NICHT_GEPRUEFT = "Kaufweg Tarifübersicht heute nicht geprüft"
NICHT_GEZAEHLT = "Speicher/Laufzeit für diesen Kaufweg nicht gezählt"


def passt(ist_tarif: str, karte: str) -> bool:
    """Gehört der gemessene Grundtarif zur Kachel? Gleich, oder Kachel + „mit …“."""
    return ist_tarif == karte or ist_tarif.startswith(karte + "-mit-")


def _tarif(schluessel: str) -> str:
    return ohne_variante(kern(schluessel.split("--")[1]))[0]


def vergleiche(
    z: ga.Zaehlung, auswahlen: list, ist_kombis: set[str]
) -> tuple[set[str], dict[str, str], dict]:
    """(bestätigte Angebote des zweiten Wegs, nicht verglichene Preise mit Grund,
    Herkunft je Weg) für die gemessenen Preise der gelesenen Geräte."""
    soll = set().union(*(a.schluessel() for a in auswahlen)) if auswahlen else set()
    auf_seite: dict[str, set[str]] = {}
    for a in auswahlen:
        auf_seite.setdefault(a.modell, set()).update(_tarif(k) for k in a.schluessel())
    karten = {grundtarif(o.text): o for o in z.tarifuebersicht or ()}
    dazu: set[str] = set()
    offen: dict[str, str] = {}
    treffer: Counter[str] = Counter()
    for k in sorted(ist_kombis - soll):
        modell = modell_der_kombination(k)
        tarif = _tarif(k)
        if modell not in auf_seite or tarif in auf_seite[modell]:
            continue
        if z.tarifuebersicht is None:
            offen[k] = NICHT_GEPRUEFT
            continue
        passende = [c for c in karten if passt(tarif, c)]
        if len(passende) == 1:
            dazu.add(k)
            treffer[passende[0]] += 1
        elif passende:
            offen[k] = NICHT_EINDEUTIG
    herkunft = {
        "produktseite": {"art": ART_PRODUKTSEITE},
        "tarifuebersicht": {
            "art": ART_TARIFUEBERSICHT,
            "quelle": O2_TARIFUEBERSICHT,
            "grund": z.tarifuebersicht_grund,
            "hinweis": NICHT_GEZAEHLT,
            "tarife": None
            if z.tarifuebersicht is None
            else [
                {"name": o.text, "slug": o.wert, "gemessen": treffer[c]}
                for c, o in karten.items()
            ],
        },
    }
    return dazu, offen, herkunft
