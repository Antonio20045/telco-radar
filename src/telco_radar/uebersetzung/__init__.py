"""Volltext-Uebersetzung fremdsprachiger Artikel.

Vier Stufen, in dieser Reihenfolge, und jede darf leer ausgehen:

  sprache.py   erkennt die Sprache - NIE auf dem Titel, immer auf dem Text
  volltext.py  beschafft den Artikeltext (Feed zuerst, dann die Artikelseite)
  store.py     merkt sich, was schon uebersetzt ist - je Item UND je Textstand
  uebersetzer.py  ruft das Modell, in Abschnitten, mit erhaltenen Absaetzen

Die Stufe haengt als Ganzes am Schalter `uebersetzung_enabled` und laeuft
mit einem Zeitbudget, das gegen die RESTZEIT DES JOBS rechnet. Ein Bericht
darf nie an einer Uebersetzung scheitern.
"""
from .sprache import erkenne_sprache, ist_fremdsprachig, SPRACHNAMEN
from .volltext import hole_volltext, VolltextErgebnis
from .store import UebersetzungsStore, Uebersetzung
from .uebersetzer import uebersetze, UebersetzungFehlgeschlagen

__all__ = [
    "erkenne_sprache", "ist_fremdsprachig", "SPRACHNAMEN",
    "hole_volltext", "VolltextErgebnis",
    "UebersetzungsStore", "Uebersetzung",
    "uebersetze", "UebersetzungFehlgeschlagen",
]
