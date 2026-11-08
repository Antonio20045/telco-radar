"""Die Bildfolge eines Belegs: mehrere Bilder entlang des Klickwegs, in Reihenfolge.

Ein Beleg ist entweder ein Bild (Normalfall, ``url``) oder eine Bildfolge: eine Liste
von ``{datei, schritt, text}`` im Manifest-Eintrag oder im Klick-Satz. ``datei`` ist ein
Dateiname im selben Release wie das Einzelbild oder eine vollständige Adresse;
``schritt`` benennt den Schritt des Wegs, ``text`` ist die Beschriftung der Erfassung.
Die Reihenfolge der Liste ist die Reihenfolge der Seite. Ein Eintrag ohne lesbare
Datei fällt weg, ohne die anderen zu verwerfen; es wird nie ein Bild ergänzt, das nicht
in der Liste steht.
"""

from __future__ import annotations

from typing import Any

SCHRITTE = {
    "geraet_speicher": "Gerät und Speicher gewählt",
    "tarif": "Tarif gewählt",
    "laufzeit": "Laufzeit und Raten gewählt",
    "preis": "Zuzahlung und Monatsrate",
}


def normalisiere(roh: Any, basis_url: str = "") -> tuple[dict[str, str], ...]:
    """``roh`` als Liste von ``{url, schritt, name, text}``; keine Liste gibt ``()``.

    ``basis_url`` ist die Adresse des Einzelbilds; ein bloßer Dateiname liegt im selben
    Ordner. Ein Dateiname mit Pfadanteil, ohne Basis oder ohne Namen fällt weg.
    """
    if not isinstance(roh, list | tuple):
        return ()
    ordner = basis_url.rsplit("/", 1)[0] + "/" if "/" in basis_url else ""
    fertig = []
    for eintrag in roh:
        if not isinstance(eintrag, dict):
            continue
        datei = str(eintrag.get("datei") or "").strip()
        if datei.startswith(("https://", "http://")):
            url = datei
        elif datei and "/" not in datei and ordner:
            url = ordner + datei
        else:
            continue
        schritt = str(eintrag.get("schritt") or "").strip()
        fertig.append(
            {
                "url": url,
                "schritt": schritt,
                "name": SCHRITTE.get(schritt, schritt),
                "text": str(eintrag.get("text") or "").strip(),
            }
        )
    return tuple(fertig)
