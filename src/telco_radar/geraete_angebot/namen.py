"""Lesbare Namen für Lücken und Preise ohne Angebot: „Samsung Galaxy S26 · 512 GB ·
Mobil XS · 24 Monate“ statt des Vergleichsschlüssels (Seite, aufgeklappt)."""

from __future__ import annotations

from ..geraete_tarifschluessel import NUMMER, PREIS, grundtarif, ohne_variante
from ..geraete_vollstaendigkeit import modell_der_kombination
from .gruende import ZeilenSoll


def _euro(betrag: str) -> str:
    return betrag.replace(".", ",")


def lesbar(schluessel: str, soll: ZeilenSoll) -> tuple[str, str]:
    """(Name, Adresse) einer Lücke: „Samsung Galaxy S26 · 512 GB · Mobil XS · 24
    Monate“ statt des Schlüssels; Adresse ist die Modellseite."""
    teile = schluessel.split("--")
    modell = modell_der_kombination(schluessel)
    info = soll.modelle.get(modell or "") or {}
    ms = teile[0]
    speicher = ms[len(modell) + 1 :] if modell else ""
    gb = speicher.removesuffix("gb")
    stuecke = [info.get("name") or soll.namen.get(modell or "") or ms]
    if gb.isdigit():
        stuecke.append(f"{int(gb) // 1024} TB" if int(gb) >= 1024 else f"{gb} GB")
    if len(teile) > 2 and teile[1]:
        rest, _, nummer = teile[1].partition(NUMMER)
        tarif, _, preis = rest.partition(PREIS)
        name = soll.tarifnamen.get(tarif, tarif)
        if preis:
            geraet, _, monat = preis.partition("-")
            name += f" ({_euro(geraet)} € + {_euro(monat)} €/Monat)"
        stuecke.append(f"{name} ({nummer}.)" if nummer else name)
        stuecke.append(f"{teile[2].removesuffix('m')} Monate")
    return " · ".join(stuecke), str(info.get("url") or "")


def benenne(ebene: dict, soll: ZeilenSoll) -> None:
    """Setzt den lesbaren Namen (und die Adresse) jedes Eintrags einer Ebene."""
    eintraege = [
        *ebene["luecken"],
        *ebene["nicht_im_soll"],
        *(ebene.get("nicht_verglichen") or ()),
    ]
    for eintrag in eintraege:
        eintrag["name"], url = lesbar(eintrag["schluessel"], soll)
        if "url" in eintrag:
            eintrag["url"] = url


def ist_tarifnamen(soll: ZeilenSoll, buendel, zeile: str) -> None:
    """Anzeigenamen für gemessene Tarife, die keine Seite nennt (nur Anzeige, nie
    Soll): „O2 Mobile S mit 15 GB+“ statt ``o2-mobile-s-mit-15gb``."""
    for b in buendel:
        b = b if isinstance(b, dict) else vars(b)
        if b.get("anbieter") == zeile and b.get("tarif_name"):
            name = str(b["tarif_name"])
            soll.tarifnamen.setdefault(
                ohne_variante(grundtarif(name))[0], name.split(" (")[0]
            )
