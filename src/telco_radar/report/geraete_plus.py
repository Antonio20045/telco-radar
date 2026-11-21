"""o2 „Plus“: eigene Zeile auf der Seite, mit Hinweis, ohne Platz im Vergleich.

ENTSCHEIDUNG ANTONIO (21.11.2026)
---------------------------------
Im Gesamtkosten-Vergleich zählt bei o2 der Tarif ohne „Plus“ (Preis ohne Bedingung).
Ein Plus-Tarif steht als eigene Zeile auf der Seite, mit dem Hinweis „mit
Zweitprodukt x € im Monat günstiger“, zählt aber nicht (``ist_bedingter_tarif``:
Δ, Referenz, Sieger, Spanne). Seine Zahl zeigt die Zeile bis auf Weiteres nicht
(Lücke seit 05.11.2026, ``geraete_preisstand.anzeige``); den Preis selbst zu zeigen,
ändert Export, Legende und Rechnung mit und ist ein eigener Schritt.

Der Befund: die Produktseite bietet Plus und ohne Plus nebeneinander an (iPhone 18
Pro Max, 21.11.2026: bei allen fünf Paaren ist Plus 5,00 € im Monat günstiger), und
die Fußnote sagt „Der o2 Plus Bundle Rabatt gilt solange zeitgleich ein zusätzliches
berechtigtes Zweitprodukt aktiv ist“. Ob das mitgekaufte Gerät als Zweitprodukt
zählt, sagt die Seite nicht.

DER BETRAG, AN EINER STELLE
--------------------------
``vorteil``: Monatsbetrag (Geräterate plus Tarif) des gleichnamigen Tarifs ohne
„Plus“ minus den des Plus-Tarifs, für dasselbe Modell mit Speicher (die Karten eines
Modells), dieselbe Ratenzahl, denselben Zustand und denselben Messtag. Fehlt das
Gegenstück oder ist der Abstand nicht positiv, heißt der Hinweis nur „Rabatt nur mit
Zweitprodukt“ - ohne Betrag, nie geraten.
"""

from __future__ import annotations

from ..analyze.geraete_pruefstatus import GERAETETARIF_MERKMAL, ist_bedingter_tarif
from ..geraete_model import normalisiere

FELD = "plus_vorteil"
KURZ_OHNE_BETRAG = "Rabatt nur mit Zweitprodukt"
KURZ = "mit Zweitprodukt {betrag} € im Monat günstiger"
SATZ = (
    "Zählt nicht im Vergleich: der Plus-Rabatt gilt nur, solange ein Zweitprodukt "
    "aktiv ist."
)
SATZ_BETRAG = SATZ + " Ohne Plus kostet derselbe Tarif {betrag} € im Monat mehr."


def ohne_merkmal(anbieter: str, tarif_name: str) -> str:
    """Der Tarifname ohne das Plus-Wort (``GERAETETARIF_MERKMAL``) des Anbieters."""
    merkmal = GERAETETARIF_MERKMAL.get(normalisiere(anbieter))
    return " ".join(w for w in (tarif_name or "").split() if w != merkmal)


def _monat(karte: dict) -> float | None:
    rate, tarif = karte.get("rate"), karte.get("monatlich")
    if rate is None or tarif is None:
        return None
    return float(rate) + float(tarif)


def _schluessel(karte: dict, name: str) -> tuple:
    return (
        karte.get("anbieter"),
        name,
        karte.get("raten_laufzeit"),
        karte.get("zustand"),
        karte.get("abgerufen_am"),
    )


def vorteil(plus: dict, karten: list[dict]) -> float | None:
    """Der Monatsvorteil des Plus-Tarifs gegenüber seinem Gegenstück - oder None."""
    name = ohne_merkmal(plus.get("anbieter") or "", plus.get("tarif") or "")
    ziel = _schluessel(plus, name)
    eigen = _monat(plus)
    for k in karten:
        name_k = " ".join(str(k.get("tarif") or "").split())
        if k is plus or _schluessel(k, name_k) != ziel:
            continue
        gegen = _monat(k)
        if gegen is None or eigen is None:
            return None
        betrag = round(gegen - eigen, 2)
        return betrag if betrag > 0 else None
    return None


def _euro(betrag: float) -> str:
    return f"{betrag:.2f}".replace(".", ",")


def vermerke(karten: list[dict]) -> list[dict]:
    """Jede Plus-Karte eines Modells bekommt ``FELD``: ihren Abstand (``vorteil``)
    oder None, wenn kein Gegenstück dasteht."""
    for k in karten:
        if ist_bedingter_tarif(k.get("anbieter") or "", k.get("tarif") or ""):
            k[FELD] = vorteil(k, karten)
    return karten


def luecke(karte: dict, kurz: str, satz: str) -> tuple[str, str]:
    """(kurz, Satz) der Plus-Zeile. Eine Karte, die ``vermerke`` nie gesehen hat (ohne
    die Karten ihres Modells), behält ``kurz``/``satz`` des Aufrufers."""
    if FELD not in karte:
        return kurz, satz
    betrag = karte[FELD]
    if betrag is None:
        return KURZ_OHNE_BETRAG, SATZ
    return KURZ.format(betrag=_euro(betrag)), SATZ_BETRAG.format(betrag=_euro(betrag))
