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
from ..collect.geraete.klicklauf import ERFASST, LAUF_GELESEN, NICHT_ANGEBOTEN
from ..collect.geraete.klickrohsatz import Klickausbeute, ausbeute, speicher_gb
from ..geraete_model import Katalog

OFFEN = "offen"


def ausbeute_der_seiten(
    daten: dict, katalog: Katalog, gestoert: bool
) -> tuple[Klickausbeute, dict]:
    """Die Ausbeute der verwendbaren Seiten und die Felder ``verwendet``,
    ``seiten_verwendet``, ``speicher_gelesen`` und ``speicher_seite`` für den
    Bilanzeintrag; ein gestörter Lauf ohne ganz gelesene Seite ist nicht verwendet."""
    seiten = verwendbare_seiten(daten, gestoert)
    aus = ausbeute({**daten, "seiten": seiten}, katalog)
    verwendet = not gestoert or bool(aus.rohsaetze or aus.ohne_tarif)
    anzahl = gelesene_seiten(seiten) if verwendet else 0
    felder = {"verwendet": verwendet, "seiten_verwendet": anzahl}
    return aus, {
        **felder,
        "speicher_gelesen": speicher_gelesen(aus.rohsaetze),
        "speicher_seite": speicher_seite(seiten),
    }


def speicher_seite(seiten: list[dict]) -> dict[str, dict[str, list[int]]]:
    """Je Gerät die Speicher, die eine gelesene Seite gesperrt zeigt
    (``nicht_angeboten``), und die, die sie weder so zeigte noch erfasste (``offen``).
    Ohne offene Speicher belegt die Seite, dass sie nur die gelesenen anbietet."""
    je_geraet: dict[str, dict[str, set[int]]] = {}
    for seite in seiten:
        if seite.get("status") != LAUF_GELESEN or not seite.get("geraet"):
            continue
        ziel = je_geraet.setdefault(str(seite["geraet"]), {NICHT_ANGEBOTEN: set()})
        for k in seite.get("kombinationen") or []:
            gb = speicher_gb((k.get("variante") or {}).get("speicher"))
            if gb is None:
                continue
            art = NICHT_ANGEBOTEN if k.get("status") == NICHT_ANGEBOTEN else OFFEN
            if k.get("status") != ERFASST:
                ziel.setdefault(art, set()).add(gb)
    return {
        g: {art: sorted(gb) for art, gb in arten.items()}
        for g, arten in je_geraet.items()
    }


def speicher_gelesen(rohsaetze: list[dict]) -> dict[str, list[int]]:
    """Je Gerät die Speicher, die der Lauf gelesen hat (``klick_erfassung``)."""
    je_geraet: dict[str, set[int]] = {}
    for satz in rohsaetze:
        je_geraet.setdefault(str(satz["device_id"]), set()).add(satz["speicher_gb"])
    return {g: sorted(gb) for g, gb in je_geraet.items()}


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
