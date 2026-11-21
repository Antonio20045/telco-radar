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
Matrix. Nicht belegt sind Seiten mit eigener Störung in einem sonst gelesenen Lauf
(Seitenform, Kanarienwert): das ist ein Mangel der Erfassung, kein Ausfall, und bleibt
Befund. Ein Anbieter ganz ohne Bündel bleibt ebenso Befund (``anbieter_leer``).
"""

from __future__ import annotations

from pathlib import Path

from ..klick_vertrag import ORDNER, ROTATION_GELESEN, ausfall, lies_ergebnisse

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
            if geraet and seite.get("status") not in ROTATION_GELESEN:
                belegt.setdefault((str(daten.get("name")), str(geraet)), satz)
    return belegt


def luecken_im_repo(root: Path, messtag: str | None) -> dict[tuple, str]:
    """``luecken`` über ``data/state/klick`` unter ``root``."""
    ergebnisse, _ = lies_ergebnisse(root / ORDNER)
    return luecken(ergebnisse, messtag)
