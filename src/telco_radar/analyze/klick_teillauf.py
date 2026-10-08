"""Die verwendbaren Seiten einer Klick-Ergebnisdatei (Pitch 1, Schnitt 3).

Ein Lauf mit Status ``gelesen`` liefert alle Seiten, wie ``klickrohsatz.ausbeute`` sie
liest. Ein heutiger Lauf mit Status ``gestoert`` liefert nur die Seiten, die vor der
Störung ganz gelesen wurden: Seitenstatus ``gelesen`` und mindestens eine erfasste
Kombination. Gestörte, an der Zeitgrenze abgeschnittene und nicht besuchte Seiten
behalten Status und Grund, aber keine Kombination; ``ausbeute`` zählt sie als Lücke.
Der Erfassungsgrund des Anbieters bleibt (``klick_erfassung``).
"""

from __future__ import annotations

from ..collect.geraete.klickergebnis import GELESENE_SEITEN
from ..collect.geraete.klicklauf import ERFASST, LAUF_GELESEN
from ..collect.geraete.klickrohsatz import Klickausbeute, ausbeute
from ..geraete_model import Katalog


def ausbeute_der_seiten(
    daten: dict, katalog: Katalog, gestoert: bool
) -> tuple[Klickausbeute, dict]:
    """Die Ausbeute der verwendbaren Seiten und die Felder ``verwendet`` und
    ``seiten_verwendet`` für den Bilanzeintrag; ein gestörter Lauf ohne ganz
    gelesene Seite ist nicht verwendet."""
    seiten = verwendbare_seiten(daten, gestoert)
    aus = ausbeute({**daten, "seiten": seiten}, katalog)
    verwendet = not gestoert or bool(aus.rohsaetze or aus.ohne_tarif)
    anzahl = gelesene_seiten(seiten) if verwendet else 0
    return aus, {"verwendet": verwendet, "seiten_verwendet": anzahl}


def verwendbare_seiten(daten: dict, gestoert: bool) -> list[dict]:
    """Die Seiten für ``ausbeute``; im gestörten Lauf nur ganz gelesene mit Inhalt."""
    seiten = list(daten.get("seiten") or [])
    if not gestoert:
        return seiten
    return [s if ganz_gelesen(s) else {**s, "kombinationen": []} for s in seiten]


def ganz_gelesen(seite: dict) -> bool:
    """Seitenstatus ``gelesen`` mit mindestens einer erfassten Kombination."""
    kombinationen = seite.get("kombinationen") or []
    return seite.get("status") == LAUF_GELESEN and any(
        k.get("status") == ERFASST for k in kombinationen
    )


def gelesene_seiten(seiten: list[dict]) -> int:
    """Wie viele Seiten Kombinationen beitragen."""
    return sum(
        bool(s.get("kombinationen")) and s.get("status") in GELESENE_SEITEN
        for s in seiten
    )
