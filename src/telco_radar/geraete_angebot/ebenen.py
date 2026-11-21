"""Die Ebenen Modelle und Modell × Speicher der Angebotszählung und die Gerätezahl
(„1 von 45 Geräten gezählt“); gerechnet für ``einhaengen``."""

from __future__ import annotations

from .. import geraete_angebot as ga
from ..geraete_vollstaendigkeit import Ist, _ebene, _luecke, _modell_ebene
from .gruende import ZeilenSoll

LISTE_HOECHSTENS = 200


def speicher_ebene(soll: ZeilenSoll, ist: Ist, grund) -> dict:
    """Modell × Speicher: wählbare Speicher der gezählten Seiten gegen das Ist."""
    ist_ms = {
        m
        for m in ist.modell_speicher
        if m in soll.speicher or m.rsplit("-", 1)[0] in soll.modelle
    }
    ebene = _ebene(len(soll.speicher), None, len(ist_ms))
    fehlend = sorted(soll.speicher - ist.modell_speicher)
    extra = sorted(ist_ms - soll.speicher)
    ebene.update(
        erfasst=len(soll.speicher & ist.modell_speicher),
        luecken=[_luecke(k, k, "", grund(k + "--")) for k in fehlend][
            :LISTE_HOECHSTENS
        ],
        luecken_zahl=len(fehlend),
        nicht_im_soll=[{"schluessel": k, "name": k} for k in extra][:LISTE_HOECHSTENS],
        nicht_im_soll_zahl=len(extra),
    )
    return ebene


NICHT_IN_UEBERSICHT = "nicht in der Übersicht des Anbieters"
UEBERSICHT_OFFEN = "Übersicht nicht ganz gelesen"
AUSWAHL_OFFEN = "Auswahl dieses Geräts nicht ganz gelesen"


def modell_ebene(zeile: dict, soll: ZeilenSoll, ist: Ist, ganz: bool, args) -> None:
    """Modell-Ebene: erfasste Modelle ohne Kachel stehen genau hier, und nur bei ganz
    gelesener Übersicht als Zahl (sonst „Übersicht nicht ganz gelesen“)."""
    name, signale, ist_je, namen = args
    for schluessel, info in soll.modelle.items():
        if info["im_katalog"] and schluessel in namen:
            info["name"] = namen[schluessel]
    stufe1 = {"modelle": list(soll.modelle.values())}
    ebene = _modell_ebene(name, stufe1, ist, signale, ist_je, namen)
    if not ganz:
        ebene.update(nicht_im_soll=[], nicht_im_soll_zahl=None)
        ebene["nicht_im_soll_grund"] = UEBERSICHT_OFFEN
    else:
        for e in ebene["nicht_im_soll"]:
            e.update(grund=NICHT_IN_UEBERSICHT, benannt=True)
    zeile["ebenen"]["modelle"] = ebene


def geraete_zahl(z: ga.Zaehlung, soll: ZeilenSoll) -> dict:
    """Wie viele Geräte der Übersicht wurden gezählt (Auswahl gelesen)?"""
    if z.schluessel == "tarifwelt":
        alle = set(soll.kachelmodelle)
    else:
        alle = {k for k, m in soll.modelle.items() if not m["nur_paket"]}
    return {"soll": len(alle), "gezaehlt": len(alle & soll.gelesen)}
