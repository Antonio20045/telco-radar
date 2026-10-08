"""Die Kachel der Folgeseite als eigene Quelle (Entscheidung 08.10.2026, umkehrbar).

1&1 nennt den Betrag für 24 Monate nur in der Kachel der Folgeseite (Erkundung
07.10.2026, Commit c8ce1f77, Seite 3: „59 , 99 €/Mon.“ in der Kachel „Weiter mit
HW24“). Die zweite Lesung, die Globalen der Produktseite, gilt für 24+12
(``currentHardwareOfferDuration = '36'``) und kann 24 nie bestätigen. Label und Betrag
stehen aber im selben Kachel-Element; das ersetzt hier das Echo.

``kacheldimension`` nennt die Dimension, für die die Kachel eigene Quelle wird: nur
mit ``weiter``, nur wenn die zweite Lesung gelesen ist und für die Kacheldimension eine
andere Option nennt als die gewählte. Nennt sie dieselbe (1&1: 24+12) oder keine, gilt
das Echo gegen die zweite Lesung wie bisher; eine Abweichung bleibt dort Befund.

``kachel_echo`` übernimmt dann nur, was die Kachel selbst nennt: Das Label in der
Kachel, beim Lesen erneut gelesen, muss genau die gewählte Option nennen (sonst
Befund ``GRUND_ANDERES_LABEL`` oder ohne Label ``GRUND_OHNE_LABEL``), und der
Bündelbetrag muss im Text der Kachel stehen (sonst ``GRUND_OHNE_BETRAG``). Die
Einmalzahlung kommt nur aus derselben Kachel; nennt sie keine, ist sie die benannte
Lücke ``einmalzahlung``, nie der Wert der zweiten Lesung. Die übrigen Wertfelder
bestätigt keine zweite Quelle; sie sind Lücken. Herkunft im Ergebnis
(``Kombiergebnis.echo_quelle``) und im Beleg statt eines JSON-Pfads ist
``QUELLE_KACHEL``. Die Prüfung der Seitenwerte (Speicher, Tarif) gilt wie im Echo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .klickecho import Befund, Echo, Variante, gleiche_option, seitenbefunde
from .klickkarte import BUENDELFELDER, WERTFELDER
from .klickoptionen import optionen_in
from .klicktext import Buendelwerte, Preiswerte

if TYPE_CHECKING:
    from playwright.sync_api import Locator

    from .klickantwort import Antwortlesung
    from .klickkarte import Klickkarte

QUELLE_KACHEL = "Kachel der Folgeseite"
GRUND_OHNE_LABEL = "Kachel nennt keine Option für {dimension}"
GRUND_ANDERES_LABEL = "Kachel nennt {label} statt {gewaehlt}"
GRUND_OHNE_BETRAG = "Kachel nennt keinen Bündelbetrag"


def kacheldimension(
    karte: Klickkarte, gewaehlt: Variante, antwort: Antwortlesung | None
) -> str | None:
    """Die Kacheldimension, wenn die zweite Lesung dort eine andere Option nennt."""
    dimension = karte.kacheldimension
    if dimension is None or antwort is None:
        return None
    genannt = antwort.variante.get(dimension)
    soll = getattr(gewaehlt, dimension)
    if genannt is None or soll is None or gleiche_option(genannt, soll):
        return None
    return dimension


def kachellabel(kachel: Locator, karte: Klickkarte, dimension: str) -> str | None:
    """Die Option, die das Label in der Kachel jetzt nennt; ``None`` ohne Label."""
    optionen = optionen_in(kachel, karte, dimension)
    return optionen[0].wert if len(optionen) == 1 else None


def kachel_echo(
    gewaehlt: Variante,
    angezeigt: Variante,
    auswahl: tuple[str, str | None, str | None],
    buendel: Buendelwerte | None,
    entfallen: tuple[str, ...] = (),
) -> Echo:
    """Das Echo aus der Kachel allein; ``auswahl`` ist (Dimension, gewählte Option,
    Label der Kachel)."""
    dimension, option, label = auswahl
    befunde = list(seitenbefunde(gewaehlt, angezeigt))
    if label is None:
        grund = GRUND_OHNE_LABEL.format(dimension=dimension)
        befunde.append(Befund(f"kachel.{dimension}", grund))
    elif not gleiche_option(label, option):
        grund = GRUND_ANDERES_LABEL.format(label=label, gewaehlt=option)
        befunde.append(Befund(f"kachel.{dimension}", grund))
    betrag = None if buendel is None else buendel.buendelbetrag
    if betrag is None:
        befunde.append(Befund("buendelbetrag", GRUND_OHNE_BETRAG))
    if befunde or buendel is None:
        return Echo(Preiswerte(), tuple(befunde), ())
    luecken = [f for f in WERTFELDER if f not in entfallen]
    luecken += [f for f in BUENDELFELDER if getattr(buendel, f) is None]
    return Echo(Preiswerte(), (), tuple(luecken), buendel)


def kachelpfade(buendel: Buendelwerte) -> dict[str, str]:
    """Je Bündelwert aus der Kachel ``QUELLE_KACHEL`` statt eines Pfads im Beleg."""
    return {f: QUELLE_KACHEL for f in BUENDELFELDER if getattr(buendel, f) is not None}
