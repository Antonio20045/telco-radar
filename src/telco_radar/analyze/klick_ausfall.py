"""Ein Klick-Ausfall des Messtags als belegte Lücke der Bündelabdeckung.

Klick-Lauf 44840854026 (21.11.2026): der Eintrag ``1und1`` bekam auf der ersten
Tarifdetail-Seite HTTP 502 und las keine Seite; seine 21 Produktseiten blieben
``nicht_besucht``. Die Ergebnisdatei nannte den Ausfall (``klick_vertrag.ausfall``),
der Wächter (``buendel_abdeckung``) las sie aber nicht und meldete zehn Geräte dieser
Seiten als „ohne belegte Lücke“, als hätte niemand nach ihnen gesucht.

``luecken`` macht aus jeder Ergebnisdatei vom Messtag mit Ausfall
(``klick_vertrag.ausfall``) je Gerät einer Seite, die der Ausfall nicht lesen ließ,
eine belegte Lücke ``(Anbieter, Modell)`` mit dem Grund ``GRUND``: gestört nicht an
der eigenen Form, oder nicht besucht, weil der Lauf an einer Störung oder an nicht
ladenden Seiten stoppte. Das Datum trägt nur eine Datei, deren Job an diesem Tag lief;
sie verjährt darum von selbst. Befund bleiben Seiten anderer Form und nicht besuchte
nach einem Stopp an Formbruch, Zeitbudget oder Verschiebung (Nachprüfung zu PR 197),
ebenso ein Anbieter ganz ohne Bündel (``anbieter_leer``).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..klick_vertrag import (
    GRUND_NACH_STOERUNG,
    GRUND_ZEITUEBERSCHREITUNGEN,
    LAUF_GESTOERT,
    ORDNER,
    SEITE_NICHT_BESUCHT,
    STOERUNG_SEITE,
    ausfall,
    lies_ergebnisse,
)

GRUND = "Klick-Lauf {schluessel} ausgefallen: {ausfall}"


def luecken(ergebnisse: list[dict], messtag: str | None) -> dict[tuple, str]:
    """Belegte Lücken ``(Anbieter, Modell) -> Grund`` aus den Ausfällen des Messtags."""
    belegt: dict[tuple, str] = {}
    for daten in ergebnisse:
        grund = ausfall(daten)
        if grund is None or messtag is None or daten.get("datum") != messtag:
            continue
        satz = GRUND.format(schluessel=daten.get("anbieter"), ausfall=grund)
        for seite in daten.get("seiten") or []:
            geraet = seite.get("geraet")
            if geraet and _vom_ausfall(seite):
                belegt.setdefault((str(daten.get("name")), str(geraet)), satz)
    return belegt


_STOPP_DURCH_AUSFALL = re.compile(
    rf"^(?:{re.escape(GRUND_NACH_STOERUNG)}"
    rf"|\d+ {re.escape(GRUND_ZEITUEBERSCHREITUNGEN)})"
)


def _vom_ausfall(seite: dict) -> bool:
    """Gestört nicht an der eigenen Form, oder nicht besucht, weil der Lauf an einem
    Ausfall stoppte (``_STOPP_DURCH_AUSFALL``); ein Stopp an Formbruch, Zeitbudget
    oder Verschiebung belegt nichts."""
    status = seite.get("status")
    if status == LAUF_GESTOERT:
        return seite.get("stoerung") != STOERUNG_SEITE
    if status == SEITE_NICHT_BESUCHT:
        return bool(_STOPP_DURCH_AUSFALL.match(str(seite.get("grund") or "")))
    return False


def luecken_im_repo(root: Path, messtag: str | None) -> dict[tuple, str]:
    """``luecken`` über ``data/state/klick`` unter ``root``."""
    ergebnisse, _ = lies_ergebnisse(root / ORDNER)
    return luecken(ergebnisse, messtag)
