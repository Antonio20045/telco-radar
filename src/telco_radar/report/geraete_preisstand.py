"""Der Chip an einer Bündelzeile, deren Preis nicht von heute ist.

Preisprüfung 11.10.2026: ein Telekom-Preis vom 10.10. sah aus wie einer von heute.
Eine Zeile, die frisch genug für den Vergleich ist (``geraete_tco_karten.ist_frisch``),
aber nicht von heute, trägt „Preis vom 10.10.2026“; jenseits der Frische gilt
„kein aktueller Stand seit …“ (``geraete_tco_karten.alt_marke_fuer``).
"""

from __future__ import annotations


def marke(abgerufen_am: str, heute: str, frisch: bool) -> str:
    """Der Chip der Zeile; eine Zeile von heute (oder ohne ``heute``) trägt keinen."""
    from .geraete_tco_karten import alt_marke_fuer, kurz_datum

    if not frisch:
        return alt_marke_fuer(abgerufen_am)
    if not heute or abgerufen_am == heute:
        return ""
    return f"Preis vom {kurz_datum(abgerufen_am)}"


_PREISFELDER_LEER = (
    "gesamt",
    "schnitt_monat",
    "monatlich",
    "buendel_monatlich",
    "zuzahlung",
    "rate",
    "raten_summe",
    "anschlusspreis",
    "nach_bindung",
    "geraetepreis",
    "geraetepreis_art",
    "delta",
    "delta_kurz",
    "aktion_ueberhang",
)
_PREISFELDER_LISTE = (
    "bestandteile",
    "zerlegung",
    "rechnung",
    "rechnung_luecken",
    "luecken",
    "aktionen",
)
KURZ_VERALTET = "Preis veraltet"
SATZ_VERALTET_OHNE_DATUM = "Preis veraltet – nicht mehr bestätigt."


def preis_veraltet(karte: dict) -> bool:
    """Ist der Preis der Karte nicht mehr bestätigt? Entweder älter als die
    Frischegrenze (``frisch``) oder von der Prüfstelle als veraltet gestempelt
    (``veraltet_pruefung``, Regel 16) - die zwei Wege, auf denen ein alter Preis
    in die Daten kommt."""
    return karte.get("frisch") is False or bool(karte.get("veraltet_pruefung"))


def anzeige(karte: dict) -> dict:
    """Die Karte für die Zeile: ein veralteter Preis wird zur benannten Lücke.

    Liefert dieselbe Karte, wenn der Preis gilt; sonst eine Kopie ohne jeden
    Betrag, mit ``belastbar`` falsch und dem Grund in ``leer_grund``. Die Karte
    selbst bleibt unverändert, Auswahl und Δ lesen sie wie bisher.
    """
    if not karte.get("sku_id") or not preis_veraltet(karte):
        return karte
    stand = karte.get("alt_marke") or ""
    if not stand and karte.get("abgerufen_am"):
        from .geraete_tco_karten import alt_marke_fuer

        stand = alt_marke_fuer(karte["abgerufen_am"])
    kopie = dict(karte)
    for feld in _PREISFELDER_LEER:
        kopie[feld] = None if feld != "delta_kurz" else ""
    for feld in _PREISFELDER_LISTE:
        kopie[feld] = []
    kopie["belastbar"] = False
    kopie["luecke_kurz"] = KURZ_VERALTET
    kopie["leer_grund"] = (
        f"Preis veraltet: {stand}." if stand else SATZ_VERALTET_OHNE_DATUM
    )
    return kopie
