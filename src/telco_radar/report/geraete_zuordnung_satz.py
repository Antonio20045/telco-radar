"""Der Satz zu Bündeln ohne Gerätezuordnung (aus `geraete_tco_view` ausgelagert,
Zeilenbegrenzung der Wächter)."""

from __future__ import annotations

ANBIETER_UNBEKANNT = "ein unbekannter Anbieter"


def ohne_zuordnung_satz(offen: list, anbieter_anzeige: dict | None = None) -> str:
    """Der Satz zu Buendeln, die auf keinem Geraet stehen - oder `""`.

    Er nennt je Anbieter den Anzeigenamen und die Zahl der Buendel; der
    Schluessel aus der Quellenkonfiguration erscheint nie auf der Seite.
    Ein leerer Anbietername heisst `ANBIETER_UNBEKANNT`, nicht "?"
    (Clean Code 4). Reihenfolge: viele zuerst, dann nach Name.
    """
    anzeige = anbieter_anzeige or {}
    je_name: dict[str, int] = {}
    for o in offen:
        schluessel = o.get("anbieter") or ""
        name = anzeige.get(schluessel) or schluessel or ANBIETER_UNBEKANNT
        je_name[name] = je_name.get(name, 0) + 1
    if not je_name:
        return ""
    teile = [
        f"{zahl} Bündel von {name}"
        for name, zahl in sorted(je_name.items(), key=lambda t: (-t[1], t[0]))
    ]
    return (
        "Nicht auf der Tafel, weil kein Gerät zuzuordnen ist: " + ", ".join(teile) + "."
    )
