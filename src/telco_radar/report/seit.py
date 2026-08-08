"""Was sich seit der letzten Ausgabe geaendert hat - je Dauerseite.

Die drei Dauerseiten (Wettbewerb, Differenzierung, Promo Uebersicht) zeigen
einen ZUSTAND. Wer sie zum zweiten Mal aufschlaegt, stellt aber eine andere
Frage: was ist neu, seit ich zuletzt hier war? Bis zum 08.08.2026 beantwortete
sie keine der drei - und in dem Drittel neben ihrer Ueberschrift, dem besten
Platz der Seite, stand nur "Stand 7. August 2026".

Gerechnet wird hier, nicht im Modell und nicht in der Vorlage: die drei
Seiten fuehren ihre Neuheiten ohnehin schon mit (`neu` auf den Eintraegen,
`first_seen`, das Datum eines Moves), sie zeigen sie nur nirgends
zusammengefasst.

**Leer heisst leer.** Gibt es nichts Neues, liefert diese Datei eine leere
Zeilenliste, und die Vorlage zeigt wieder nur den Stand. Eine Zeile "0 neue
Beispiele", die jede Woche gleich aussieht, ist Rauschen - dieselbe
Ueberlegung wie beim Zwei-Minuten-Pfad, der bei leerer Lage ganz wegfaellt.
"""
from __future__ import annotations

# Wie viele Zeilen die Spalte hoechstens traegt. Drei, weil sie neben einer
# Ueberschrift steht und nicht neben ihr herunterlaufen darf.
MAX_ZEILEN = 3


def _zeile(n: int, einzahl: str, mehrzahl: str, anker: str) -> dict | None:
    if not n:
        return None
    return {"n": n, "text": einzahl if n == 1 else mehrzahl, "anker": anker}


def _zusammen(*zeilen) -> dict:
    echte = [z for z in zeilen if z][:MAX_ZEILEN]
    return {"zeilen": echte}


def fuer_differenzierung(diff: dict) -> dict:
    """`neu` steht schon an jedem Eintrag (differenzierung_view.aufbereiten)."""
    bestand = diff.get("bestand") or []
    neu = sum(1 for e in bestand if e.get("neu"))
    hebel_neu = len({e.get("theme") for e in bestand if e.get("neu")})
    return _zusammen(
        _zeile(neu, "neues Beispiel", "neue Beispiele", "#neu"),
        _zeile(hebel_neu, "Hebel betroffen", "Hebel betroffen", "#marktbild"),
    )


def fuer_promo(promo_view: dict) -> dict:
    """Neue und ausgelaufene Aktionen. Beides ist eine Bewegung des Marktes -
    eine ausgelaufene Aktion sagt so viel wie eine neue."""
    # Gezaehlt wird auf den ANGEBOTEN, nicht auf den Karten: `neu` und der
    # Status stehen dort (prepare_promo_view stempelt sie beim Aufbereiten),
    # die Karte traegt nur, was sie anzeigt.
    angebote = [k.get("offer") or {} for k in (promo_view.get("karten") or [])]
    neu = sum(1 for a in angebote if a.get("neu"))
    weg = sum(1 for a in angebote
              if (a.get("status") or "").startswith(("ausgelaufen",
                                                     "evtl. ausgelaufen")))
    return _zusammen(
        _zeile(neu, "neue Aktion", "neue Aktionen", "#marken"),
        _zeile(weg, "ausgelaufen", "ausgelaufen", "#marken"),
    )


def fuer_wettbewerb(wettbewerb: dict, stand: str) -> dict:
    """Moves und Meldungen, die auf den Stand der aktuellen Ausgabe datieren.

    Gezaehlt wird das DATUM des Eintrags, nicht seine Position in der Chronik:
    die Chronik reicht ueber das ganze Archiv, und ein Eintrag rutscht darin
    nach unten, ohne alt zu werden.
    """
    n = 0
    betroffene = set()
    for c in (wettbewerb.get("wettbewerber") or []):
        for monat in (c.get("monate") or []):
            for eintrag in (monat.get("eintraege") or []):
                if (eintrag.get("datum") or "") == stand:
                    n += 1
                    betroffene.add(c.get("name"))
    return _zusammen(
        _zeile(n, "neue Meldung", "neue Meldungen", "#chronik"),
        _zeile(len(betroffene), "Wettbewerber betroffen",
               "Wettbewerber betroffen", "#chronik"),
    )
