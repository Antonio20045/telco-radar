"""Zweiter sichtbarer Kaufweg bei o2: Tarifübersicht -> „Handy hinzufügen“.

Antonio, 21.11.2026: die Geräteseite zeigt nur, was ein Kunde bei o2 selbst wählen
und kaufen kann. Das sind die Tarifkacheln der Produktseite UND die Tarife der
Tarifübersicht (https://www.o2online.de/tarife/) mit „Handy hinzufügen“
(``/e-shop?tarif=<slug>``; Befund ``berichte/o2-nicht-plus.md``: so ist z. B. „O2 Mobile
Unlimited L“ ohne Plus mit Gerät buchbar). Der o2-Sammler bildet Bündel nach derselben
Definition; das Soll hier zählt beide Wege und nennt die Herkunft (``art``).

Die Tarifübersicht nennt je Tarif nur den Slug. Den Namen, unter dem die Messung ihn
führt, liefert die Adresse des gemessenen Bündels (``quelle_url`` mit ``tarif=<slug>``):
dieselbe Kennung, kein Namensraten. Ohne gemessenes Bündel bleibt der Slug der
Schlüssel; die Kombination wird dann eine sichtbare Lücke. Laufzeiten und Speicher
sind die der Produktseite (Annahme, benannt in ``herkunft``). Fällt die Übersicht aus,
gilt nur die Produktseite, der Ausfall steht in ``unvollstaendig``.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable

from .. import geraete_angebot as ga
from ..geraete_tarifschluessel import grundtarif
from .gruende import ZeilenSoll
from .lesen_seiten import O2_TARIFUEBERSICHT

ART_PRODUKTSEITE = "browser_auswahl"
ART_TARIFUEBERSICHT = "browser_tarifuebersicht"
ANNAHME = "Speicher und Laufzeiten wie auf der Produktseite"


def slug_namen(buendel: Iterable, zeile: str) -> dict[str, str]:
    """Slug -> Grundtarif der Messung, aus ``quelle_url`` der Bündel dieser Zeile."""
    namen: dict[str, str] = {}
    for b in buendel:
        b = b if isinstance(b, dict) else vars(b)
        treffer = re.search(r"[?&]tarif=([a-z0-9-]+)", str(b.get("quelle_url") or ""))
        if b.get("anbieter") == zeile and treffer and b.get("tarif_name"):
            namen.setdefault(treffer.group(1), grundtarif(str(b["tarif_name"])))
    return namen


def _erweitert(auswahl, tarife: list[str]):
    if auswahl.kombinationen is None:
        alle = tuple(dict.fromkeys([*auswahl.tarife, *tarife]))
        return dataclasses.replace(auswahl, tarife=alle)
    paare = dict.fromkeys((s, n) for s, _, n in auswahl.kombinationen)
    dazu = tuple((s, t, n) for s, n in paare for t in tarife)
    vorhanden = set(auswahl.kombinationen)
    neu = tuple(k for k in dazu if k not in vorhanden)
    return dataclasses.replace(auswahl, kombinationen=auswahl.kombinationen + neu)


def ergaenze(z: ga.Zaehlung, soll: ZeilenSoll, buendel: list, zeile: str) -> dict:
    """Erweitert die Auswahl jeder gezählten o2-Seite um die Tarife der Übersicht;
    gibt die Herkunft je Weg zurück (für die Lauf-Datei)."""
    herkunft: dict = {
        "produktseite": {"art": ART_PRODUKTSEITE},
        "tarifuebersicht": {
            "art": ART_TARIFUEBERSICHT,
            "quelle": O2_TARIFUEBERSICHT,
            "tarife": None,
            "grund": z.tarifuebersicht_grund,
            "annahme": ANNAHME,
        },
    }
    if z.tarifuebersicht is None:
        grund = z.tarifuebersicht_grund or "Tarifübersicht nicht gelesen"
        soll.unvollstaendig.append(grund)
        herkunft["tarifuebersicht"]["grund"] = grund
        return herkunft
    namen = slug_namen(buendel, zeile)
    tarife = []
    for option in z.tarifuebersicht:
        schluessel = namen.get(option.wert, grundtarif(option.wert))
        soll.tarifnamen.setdefault(schluessel, option.text)
        tarife.append(schluessel)
    soll.auswahlen = [_erweitert(a, tarife) for a in soll.auswahlen]
    herkunft["tarifuebersicht"]["tarife"] = [o.wert for o in z.tarifuebersicht]
    return herkunft
