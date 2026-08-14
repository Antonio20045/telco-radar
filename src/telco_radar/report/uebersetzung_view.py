"""Die Uebersetzungen fuer die Website aufbereiten.

Zwei Aufgaben, und beide haengen an derselben Rechnung:

  `zuordnung()`   URL einer Meldung -> Pfad ihrer Uebersetzungsseite
  `seiten()`      was gerendert werden muss

Die Zuordnung laeuft ueber `Item.id`, also SHA-256 ueber die NORMALISIERTE
URL. Das ist derselbe Schluessel, den der Seen-Store und die Pipeline
benutzen - und genau deshalb ist er richtig: rechnete die Website ihren
eigenen Schluessel (etwa aus dem Titel), zeigten alte Berichte nach dem
ersten Titel-Umbau ins Leere. Das ist Premortem 6.
"""
from __future__ import annotations

from pathlib import Path

from ..models import Item
from ..uebersetzung.sprache import sprachname, sprachname_dativ
from ..uebersetzung.store import UebersetzungsStore

ORDNER = "uebersetzung"


def seiten_pfad(item_id: str) -> str:
    return f"{ORDNER}/{item_id}.html"


def id_fuer_url(url: str) -> str:
    """Dieselbe ID, die die Pipeline dem Item gegeben haette.

    Ueber `Item` gerechnet und nicht mit einer eigenen Hash-Zeile: eine
    zweite Rechnung fuer denselben Schluessel ist eine zweite Wahrheit,
    und sie laeuft beim ersten Umbau von `normalize_url` auseinander.
    """
    return Item(title="", url=url, source_name="").id


def lade(state_dir: Path) -> UebersetzungsStore:
    return UebersetzungsStore(Path(state_dir) / "uebersetzungen.jsonl")


def zuordnung(store: UebersetzungsStore) -> dict[str, str]:
    """{URL der Meldung: Pfad ihrer Uebersetzungsseite}.

    Geschluesselt auf die URL und nicht auf die ID, weil die Vorlagen die
    URL haben und nicht die ID. Die ID steht trotzdem dazwischen - sie ist
    der stabile Teil.
    """
    raus: dict[str, str] = {}
    for u in store.alle():
        if u.url and u.absaetze:
            raus[u.url] = seiten_pfad(u.item_id)
    return raus


def seiten(store: UebersetzungsStore) -> list[dict]:
    """Je Uebersetzung ein Rendermodell."""
    raus = []
    for u in store.alle():
        if not u.absaetze:
            continue
        raus.append({
            "dateiname": f"{u.item_id}.html",
            "u": u,
            "sprachname": sprachname(u.sprache),
            "sprachname_dativ": sprachname_dativ(u.sprache),
        })
    return raus
