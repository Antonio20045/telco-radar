"""Ein Klick-Ausfall des Messtags als belegte Lücke der Bündelabdeckung.

Klick-Lauf 44840854026 (21.11.2026): der Eintrag ``1und1`` bekam auf der ersten
Tarifdetail-Seite HTTP 502 und las keine Seite; seine 21 Produktseiten blieben
``nicht_besucht``. Die Ergebnisdatei nannte den Ausfall (``klick_vertrag.ausfall``),
der Wächter (``buendel_abdeckung``) las sie aber nicht und meldete zehn Geräte dieser
Seiten als „ohne belegte Lücke“, als hätte niemand nach ihnen gesucht.

``luecken`` macht aus jeder Ergebnisdatei vom Messtag mit Ausfall je Gerät einer
nicht ganz gelesenen Seite eine belegte Lücke ``(Anbieter, Modell)`` mit dem Grund
``GRUND``. Das Datum trägt nur eine Datei, deren Job an diesem Tag lief; sie gilt
nur an diesem Tag und verjährt darum von selbst. Ein
Gerät, das ein anderer Eintrag am selben Tag gelesen hat, steht ohnehin in der
Matrix. Nicht belegt ist, was ``ausfall`` nicht als Ausfall zählt (Seitenform,
Strukturbruch, leer, Verschiebung, ohne Laufstatus oder Grund), und auch im Ausfall
eine Seite, die an ihrer eigenen Form scheiterte: das ist ein Mangel der Erfassung
und bleibt Befund. Ein Anbieter ganz ohne Bündel bleibt Befund (``anbieter_leer``).
"""

from __future__ import annotations

from pathlib import Path

from ..klick_vertrag import (
    LAUF_GESTOERT,
    ORDNER,
    ROTATION_GELESEN,
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


def _vom_ausfall(seite: dict) -> bool:
    """Nicht gelesen, und nicht an der eigenen Form gescheitert."""
    eigene_form = seite.get("status") == LAUF_GESTOERT and (
        seite.get("stoerung") == STOERUNG_SEITE
    )
    return seite.get("status") not in ROTATION_GELESEN and not eigene_form


def luecken_im_repo(root: Path, messtag: str | None) -> dict[tuple, str]:
    """``luecken`` über ``data/state/klick`` unter ``root``."""
    ergebnisse, _ = lies_ergebnisse(root / ORDNER)
    return luecken(ergebnisse, messtag)
