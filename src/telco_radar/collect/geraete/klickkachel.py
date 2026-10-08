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

``kachellabels`` liest beim Lesen erneut jedes Label in der Kachel: jedes Element
``wert_in`` darin (ohne ``wert_in`` die Kachel selbst), je Treffer des Musters ein
Wert, ein Element ohne Treffer als ``None``. ``kachel_echo`` übernimmt dann nur den
Bündelbetrag aus dem Text der Kachel, und nur wenn sie genau ein Label nennt und das
genau die gewählte Option ist (sonst Befund ``GRUND_OHNE_LABEL``,
``GRUND_MEHRERE_LABEL`` oder ``GRUND_ANDERES_LABEL``) und der Bündelbetrag im Text
steht (sonst ``GRUND_OHNE_BETRAG``). Die Einmalzahlung ist immer die benannte Lücke
``einmalzahlung``, auch wenn der Text der Kachel eine nennt: Ein Hinweis in der Kachel
kann die Einmalzahlung einer anderen Laufzeit nennen (Prüferbefund zu a1ed9e94), und
keine zweite Quelle ordnet sie zu. Die übrigen Wertfelder sind ebenso Lücken. Herkunft
im Ergebnis (``Kombiergebnis.echo_quelle``) und im Beleg statt eines JSON-Pfads ist
``QUELLE_KACHEL``. Die Prüfung der Seitenwerte (Speicher, Tarif) gilt wie im Echo.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

from .klickecho import Befund, Echo, Variante, gleiche_option, seitenbefunde
from .klickkarte import BUENDELFELDER, WERTFELDER
from .klicktext import Buendelwerte, Preiswerte

if TYPE_CHECKING:
    from playwright.sync_api import Locator

    from .klickantwort import Antwortlesung
    from .klickkarte import Klickkarte

QUELLE_KACHEL = "Kachel der Folgeseite"
NUR_AUS_DER_KACHEL = frozenset({"buendelbetrag"})
GRUND_OHNE_LABEL = "Kachel nennt keine Option für {dimension}"
GRUND_MEHRERE_LABEL = "Kachel nennt {anzahl} Optionen für {dimension}: {labels}"
GRUND_ANDERES_LABEL = "Kachel nennt {label} statt {gewaehlt}"
GRUND_OHNE_BETRAG = "Kachel nennt keinen Bündelbetrag"
Labels = str | tuple[str | None, ...] | None
_LABELS_JS = """(kacheln, art) => kacheln.flatMap((k) => {
  const traeger = !art.wertIn ? [k]
    : [...(k.matches(art.wertIn) ? [k] : []), ...k.querySelectorAll(art.wertIn)];
  return traeger.map((t) => art.wert ? t.getAttribute(art.wert) : t.innerText);
})"""


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


def kachellabels(
    kachel: Locator, karte: Klickkarte, dimension: str
) -> tuple[str | None, ...]:
    """Jedes Label in der Kachel (siehe Modulkopf); leer ohne Label-Element."""
    knopf = karte.knoepfe[dimension]
    art = {"wert": knopf.wert_attribut, "wertIn": knopf.wert_in}
    roh = kachel.evaluate_all(_LABELS_JS, art)
    return tuple(w for r in roh for w in labels_in(r, knopf.muster))


def labels_in(roh: object, muster: re.Pattern[str] | None) -> list[str | None]:
    """Jeder Wert, den ``muster`` in ``roh`` findet; ``[None]`` ohne Treffer."""
    text = " ".join(roh.split()) if isinstance(roh, str) else ""
    if not text:
        return [None]
    if muster is None:
        return [text]
    teile = (t[1] if muster.groups else t[0] for t in muster.finditer(text))
    werte: list[str | None] = [t.strip() for t in teile if t is not None and t.strip()]
    return werte or [None]


def _labelbefund(dimension: str, option: str | None, gelesen: Labels) -> Befund | None:
    feld = f"kachel.{dimension}"
    labels = gelesen if isinstance(gelesen, tuple) else (gelesen,)
    if len(labels) > 1:
        genannt = ", ".join("ohne Wert" if x is None else x for x in labels)
        grund = GRUND_MEHRERE_LABEL.format(
            anzahl=len(labels), dimension=dimension, labels=genannt
        )
        return Befund(feld, grund)
    label = labels[0] if labels else None
    if label is None:
        return Befund(feld, GRUND_OHNE_LABEL.format(dimension=dimension))
    if not gleiche_option(label, option):
        return Befund(feld, GRUND_ANDERES_LABEL.format(label=label, gewaehlt=option))
    return None


def kachel_echo(
    gewaehlt: Variante,
    angezeigt: Variante,
    auswahl: tuple[str, str | None, Labels],
    buendel: Buendelwerte | None,
    entfallen: tuple[str, ...] = (),
) -> Echo:
    """Das Echo aus der Kachel allein; ``auswahl`` ist (Dimension, gewählte Option,
    alle Labels der Kachel aus ``kachellabels`` oder ihr einziges Label)."""
    dimension, option, labels = auswahl
    befunde = list(seitenbefunde(gewaehlt, angezeigt))
    labelbefund = _labelbefund(dimension, option, labels)
    if labelbefund is not None:
        befunde.append(labelbefund)
    betrag = None if buendel is None else buendel.buendelbetrag
    if betrag is None:
        befunde.append(Befund("buendelbetrag", GRUND_OHNE_BETRAG))
    if befunde or buendel is None:
        return Echo(Preiswerte(), tuple(befunde), ())
    ohne = {f: None for f in BUENDELFELDER if f not in NUR_AUS_DER_KACHEL}
    uebernommen = replace(buendel, **ohne)
    luecken = [f for f in WERTFELDER if f not in entfallen]
    luecken += [f for f in BUENDELFELDER if getattr(uebernommen, f) is None]
    return Echo(Preiswerte(), (), tuple(luecken), uebernommen)


def kachelpfade(buendel: Buendelwerte) -> dict[str, str]:
    """Je Bündelwert aus der Kachel ``QUELLE_KACHEL`` statt eines Pfads im Beleg."""
    return {f: QUELLE_KACHEL for f in BUENDELFELDER if getattr(buendel, f) is not None}
