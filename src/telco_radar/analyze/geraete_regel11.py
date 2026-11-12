"""Regel 11 der Prüfstelle: Sprung zum Vortag, Gerätepreis und Referenz über Tage.

Eigenes Modul, weil ``geraete_regeln`` die Dateigrenze der Leiter (400 Zeilen) nicht
überschreiten darf. Regel 11 ist der einzige Schutz für ein frisches Bündel, dessen
Speicher-Nachbar veraltet ist (Regel 5, ``geraete_regel5``). Sie prüft darum nicht nur
die Gesamtsumme, sondern drei Dinge:

* der Vorgänger ist höchstens ``VORTAG_MAX_ALTER_TAGE`` Tage vor dem Abruf gemessen,
  sonst ist die Regel nicht anwendbar (``nicht prüfbar``, bei veraltetem Nachbarn
  Quarantäne 5). Ein Gesamtsprung über 15 % gegen einen älteren Vorgänger bleibt
  Quarantäne wie auf main: die Regel wird nirgends lockerer;
* Gesamtsumme (24 Monate) und Gerätepreis (Zuzahlung plus Raten) weichen höchstens
  um ``AUSREISSER_VORTAG`` und ``AUSREISSER_GERAET_VORTAG`` vom Vorgänger ab, die
  Summe dämpft den Sprung um den Tarifanteil;
* der Gerätepreis liegt nicht mehr als ``REFERENZ_RUECKGANG`` unter dem Höchstwert
  der ``REFERENZ_TAGE`` Tage davor (schleichendes Sinken, ein seit Tagen gleich
  falscher Preis). Ohne ``REFERENZ_MIN_MESSUNGEN`` Messungen im Fenster entfällt
  dieser Teil, ebenso wenn derselbe Gerätepreis an ``STABIL_TAGE`` Abruftagen in
  Folge gelesen wurde (``_stabil``) **und** der Rückgang höchstens
  ``STABIL_MAX_RUECKGANG`` beträgt: eine echte Senkung (Vodafone Black Week,
  Rate 45 € auf 39 €) soll nicht bis zu sieben Tage gesperrt bleiben, ein seit
  Tagen gleich falsch gelesener Preis aber auch nicht durchkommen. Der Sprung
  zum Vortag und das schleichende Sinken prüfen vorher und bleiben gesperrt.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping

from .. import rechenweise
from ..tarif_model import BUENDELPHASEN
from ..tco_model import Buendel, tco_24
from .geraete_pruefstatus import (
    AUSREISSER_VORTAG,
    NICHT_PRUEFBAR,
    REFERENZ_TAGE,
    VERLETZT,
    Befund,
    Kontext,
    buendel_aus_satz,
    datum,
    eur,
    geraetepreis,
)

REGEL = 11
AUSREISSER_GERAET_VORTAG = 0.10
"""Regel 11: größter Sprung des Gerätepreises (Zuzahlung plus Raten) zum Vortag. Im
Bestand ändert sich der Gerätepreis von Messtag zu Messtag bei 0,9 % der Bündel, über
10 % bei 0,2 %; die Gesamtsumme dämpft den Sprung um den Tarifanteil (``_verletzt``)."""
VORTAG_MAX_ALTER_TAGE = 3
"""Regel 11: höchstes Alter des Vorgängers vor dem Abruf, gleich ``ALT_AB_TAGEN`` der
Geräteseite: ein Vorgänger, der selbst veraltet wäre, ist kein Vortag."""
REFERENZ_MIN_MESSUNGEN = 3
REFERENZ_RUECKGANG = 0.10
"""Regel 11 gegen schleichendes Sinken: der Gerätepreis liegt höchstens so weit unter
dem Höchstwert der ``REFERENZ_TAGE`` Tage vor dem Abruf (mit mindestens
``REFERENZ_MIN_MESSUNGEN`` Messungen im Fenster)."""
STABIL_TAGE = 3
"""Regel 11: so viele Abruftage in Folge mit demselben Gerätepreis (der Abruf selbst
zählt mit) heben den Referenzvergleich auf. Ein Preis, der an drei aufeinander
folgenden Tagen gleich gelesen wurde, ist kein Ausreißer; Tagessprung und
schleichendes Sinken prüfen vorher und bleiben gesperrt."""
STABIL_ABSTAND_EUR = 0.005
"""Regel 11: zwei Gerätepreise gelten als gleich gelesen, wenn sie auf den Cent
übereinstimmen."""
STABIL_MAX_RUECKGANG = 0.25
"""Regel 11: so weit darf der Gerätepreis höchstens unter dem Höchstwert liegen, damit
``STABIL_TAGE`` gleiche Abruftage den Referenzvergleich aufheben. Darüber bleibt die
Quarantäne, auch wenn der Preis seit Tagen gleich gelesen wird: ein Lesefehler auf einer
falschen Seitenvariante steht oft mehrere Tage (Telekom Motorola Edge 70 512 GB,
30.10.-02.11.2026, -39,7 % und -49,2 %). Die Höhe stammt aus der Prüfung von PR 95
(Abschnitte 4 und 5): bei 35 % kam der falsch gelesene Motorola-Preis zwar noch nicht
durch, aber eine Obergrenze ohne Sicherheitsabstand zum belegten Fehler (-39,7 %) ist
fail-closed nicht robust genug. 25 % lässt alle 6 falschen Zeilen gesperrt (Abstand zur
nächsten falschen Zeile 14,7 Punkte) und gibt 195 der 420 echten Vodafone-Senkungen vom
12.11. frei; die übrigen 225 reichen von 25,7 % bis 44,7 % (Pixel 10a, am Original
belegt) und bleiben wie auf main gesperrt, bis der Höchstwert aus dem Fenster wächst.
Eine saubere Trennung zwischen echter Senkung und Lesefehler gibt es nicht; die Grenze
ist der gewählte Punkt zwischen Abdeckung und Fehler."""


def _nicht(satz: str) -> Befund:
    return Befund(REGEL, NICHT_PRUEFBAR, satz)


def _verletzt(satz: str) -> Befund:
    return Befund(REGEL, VERLETZT, satz)


def _tag(text: object) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


def _zeile(satz: Mapping, alt: Mapping) -> Buendel | None:
    """Das Bündel mit den Preisen einer Historienzeile; None, wenn sie unlesbar ist."""
    try:
        return buendel_aus_satz({**satz, BUENDELPHASEN: None, **alt})
    except (TypeError, ValueError):
        return None


def _abstand(neu: float, alt: float) -> float:
    return abs(neu - alt) / alt


def _preise_je_tag(
    satz: Mapping, abruf: dt.date, k: Kontext
) -> dict[dt.date, list[float | None]]:
    """Je Messtag der letzten ``REFERENZ_TAGE`` Tage vor dem Abruf die Gerätepreise
    gleicher Rechenweise; ``None`` für eine Messung, deren Preis nicht lesbar ist."""
    je_tag: dict[dt.date, list[float | None]] = {}
    for zeile in k.verlauf.get(str(satz.get("id") or ""), ()):
        tag = _tag(zeile.get("datum"))
        if tag is None or not 0 < (abruf - tag).days <= REFERENZ_TAGE:
            continue
        if not rechenweise.gleich(satz, zeile):
            continue
        b = _zeile(satz, zeile)
        preis = geraetepreis(b) if b else None
        je_tag.setdefault(tag, []).append(preis or None)
    return je_tag


def _referenz(je_tag: Mapping[dt.date, list[float | None]]) -> float | None:
    """Höchster Gerätepreis im Fenster; None ohne ``REFERENZ_MIN_MESSUNGEN`` lesbare
    Messungen."""
    preise = [p for tag in je_tag.values() for p in tag if p]
    return max(preise) if len(preise) >= REFERENZ_MIN_MESSUNGEN else None


def _stabil(
    je_tag: Mapping[dt.date, list[float | None]], abruf: dt.date, neu: float
) -> bool:
    """Wurde ``neu`` an ``STABIL_TAGE`` Abruftagen in Folge gelesen (der Abruf zählt
    mit)? Fail-closed: ein fehlender Tag, eine unlesbare oder eine abweichende
    Messung desselben Tages zählt nicht als gleich gelesen."""
    for vor_tagen in range(1, STABIL_TAGE):
        preise = je_tag.get(abruf - dt.timedelta(days=vor_tagen))
        if not preise:
            return False
        if any(p is None or abs(p - neu) > STABIL_ABSTAND_EUR for p in preise):
            return False
    return True


def _referenz_befund(
    je_tag: Mapping[dt.date, list[float | None]], abruf: dt.date, neu_g: float
) -> Befund | None:
    """Der Abstand zum Höchstwert der ``REFERENZ_TAGE`` Tage davor; None heißt
    bestanden. Drei gleiche Abruftage heben den Vergleich auf, aber nur bis
    ``STABIL_MAX_RUECKGANG``."""
    hoechst = _referenz(je_tag)
    if hoechst is None or neu_g >= hoechst * (1 - REFERENZ_RUECKGANG):
        return None
    rueckgang = 1 - neu_g / hoechst
    zu_gross = rueckgang > STABIL_MAX_RUECKGANG
    if not zu_gross and _stabil(je_tag, abruf, neu_g):
        return None
    text = f"Gerätepreis {eur(neu_g)}, in den {REFERENZ_TAGE} Tagen davor bis zu "
    text += f"{eur(hoechst)} ({rueckgang:.0%} darunter)"
    if zu_gross:
        ende = f"Rückgang über {STABIL_MAX_RUECKGANG:.0%}, gleiche Abruftage heben "
        ende += "die Quarantäne nicht auf"
    else:
        ende = f"Quarantäne bis zu {STABIL_TAGE} gleichen Abruftagen in Folge"
    return _verletzt(f"{text}, {ende}")


def regel_11_vortag(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    """Regel 11: Sprung zum Vortag und Abstand zur Referenz; None heißt bestanden."""
    alt = k.vortag.get(str(satz.get("id") or ""))
    if alt is None:
        return _nicht("kein Vortageswert")
    abruf, vortag = _tag(b.abgerufen_am), _tag(alt.get("datum"))
    if not rechenweise.gleich(satz, alt):
        return _nicht(rechenweise.BRUCH)
    vorher = _zeile(satz, alt)
    if vorher is None:
        return _nicht("Vortageswert unlesbar")
    neu_t, alt_t = tco_24(b), tco_24(vorher)
    neu_g, alt_g = geraetepreis(b), geraetepreis(vorher)
    if not (neu_t.belastbar and alt_t.belastbar) or neu_t.gesamt is None:
        return _nicht("Gesamtpreis heute oder am Vortag unvollständig")
    if not alt_t.gesamt:
        return _nicht("Gesamtpreis heute oder am Vortag unvollständig")
    tag = datum(str(alt.get("datum") or ""))
    sprung = _abstand(neu_t.gesamt, alt_t.gesamt)
    if sprung > AUSREISSER_VORTAG:
        text = f"{eur(neu_t.gesamt)} statt {eur(alt_t.gesamt)} am {tag} ({sprung:.0%})"
        return _verletzt(f"{text}, Quarantäne bis zum zweiten Abruf")
    if abruf is None or vortag is None:
        return _nicht("Alter des Vortageswerts unbekannt")
    if (abruf - vortag).days > VORTAG_MAX_ALTER_TAGE:
        text = f"Vortageswert vom {tag} zu alt"
        return _nicht(f"{text} (höchstens {VORTAG_MAX_ALTER_TAGE} Tage vor dem Abruf)")
    if neu_g is None or not alt_g:
        return _nicht("Gerätepreis heute oder am Vortag unvollständig")
    sprung = _abstand(neu_g, alt_g)
    if sprung > AUSREISSER_GERAET_VORTAG:
        text = f"Gerätepreis {eur(neu_g)} statt {eur(alt_g)} am {tag} ({sprung:.0%})"
        return _verletzt(f"{text}, Quarantäne bis zum zweiten Abruf")
    return _referenz_befund(_preise_je_tag(satz, abruf, k), abruf, neu_g)
