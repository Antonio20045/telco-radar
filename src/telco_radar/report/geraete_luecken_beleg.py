"""Belegte Lücken (`config/geraete_abdeckung.yaml`) in der Modellansicht.

Eine belegte Lücke (Gerät oder Speicherstufe „nicht im Sortiment“, mit Prüfdatum)
gilt für alle Anbieter gleich:

* Welcher Preis davon überholt ist, entscheidet allein `geraete_sortiment`
  (`markiere_mit`, Vermerk `veraltet 17`; jünger als die Prüfung = Lücke falsch,
  Warnung, Preis bleibt). Hier steht nur die Fehlzeile des Modells.
* Eine Lücke gilt erst ab ihrem Prüfdatum: ein älterer Stand (`heute` davor)
  kennt sie nicht.
* Fehlt dem Modell danach jeder neue Preis des Anbieters, nennt die Zeile des
  Anbieters den Grund samt Prüfdatum statt „Noch nicht erfasst“.

Gültig ist ein Beleg wie überall (`geraete_sortiment.beleg_fuer`:
Sortiments-Aussage im Grund, heute <= `bis`). Kein Abruf, nur Config und Bündel.
"""

from __future__ import annotations

from ..analyze.klick_erfassung import KEINE_NEUGERAETE, Neugeraete
from .geraete_sortiment import gueltiger_beleg, stufe

KURZ = "Nicht im Sortiment (geprüft {geprueft})"
SATZ = "{grund}. Geprüft {geprueft}, gültig bis {bis}."


def _detail(grund) -> str:
    """Der Grund als sichtbarer Kurztext: steht vor einem „ - “ nur die
    Wiederholung von „nicht im Sortiment (geprüft …)“, zählt der Teil danach;
    sonst der ganze Grund."""
    text = str(grund).strip().rstrip(". ")
    return text.split(" - ", 1)[1] if " - " in text else text


def _tag(wert) -> str:
    return f"{wert.day:02d}.{wert.month:02d}."


def _voll(wert) -> str:
    return f"{_tag(wert)}{wert.year}"


def fuer_modell(
    belege: dict, modell: dict, heute: str, neu: Neugeraete = KEINE_NEUGERAETE
) -> dict[str, dict]:
    """{Anbieter: Lücke} für ein Modell der Seite: gültig belegt und ohne jeden
    gültigen neuen Preis des Anbieters in diesem Modell (ein von der Lücke überholter
    Preis, `nicht_im_sortiment`, zählt nicht) und ohne lieferbares Neugerät derselben
    Kombination im Radar (`neu`, Widerspruchsregel: dann Messlücke)."""
    device_id, gb = modell.get("device_id"), stufe(modell.get("speicher"))
    mit_preis = {
        k.get("anbieter")
        for k in modell.get("karten") or []
        if (k.get("zustand") or "neu") == "neu"
        and k.get("sku_id")
        and not k.get("nicht_im_sortiment")
    }
    aus: dict[str, dict] = {}
    for anbieter in {k[0] for k in belege}:
        if anbieter in mit_preis or not device_id:
            continue
        if (anbieter, device_id, modell.get("speicher")) in neu.speicher:
            continue
        beleg = gueltiger_beleg(belege, anbieter, device_id, heute, gb)
        if beleg:
            aus[anbieter] = {
                "kurz": KURZ.format(geprueft=_tag(beleg["geprueft"])),
                "detail": _detail(beleg["grund"]),
                "satz": SATZ.format(
                    grund=str(beleg["grund"]).rstrip(". "),
                    geprueft=_voll(beleg["geprueft"]),
                    bis=_voll(beleg["bis"]),
                ),
            }
    return aus
