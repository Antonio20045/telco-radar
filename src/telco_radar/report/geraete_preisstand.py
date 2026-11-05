"""Der Chip an einer Bündelzeile, deren Preis nicht von heute ist - und die Lücke
statt einer Zahl, wenn der Preis nicht stehen darf.

Drei Gründe nehmen einer Zeile die Zahl: ein veralteter Preis, ein Preis in
Quarantäne (Prüfstelle: eine Regel ist verletzt, z. B. Regel 5) und ein Plus-Tarif,
dessen Preis ein Zweitprodukt voraussetzt (``ist_bedingter_tarif``; Entscheidung
05.11.2026, Prüfung PR #38 M1). Maßstab: lieber kein Preis als ein falscher - die
Zeile nennt ihren Grund, nicht die Regel.

Preisprüfung 11.10.2026: ein Telekom-Preis vom 10.10. sah aus wie einer von heute.
Eine Zeile, die frisch genug für den Vergleich ist (``geraete_tco_karten.ist_frisch``),
aber nicht von heute, trägt „Preis vom 10.10.2026“; jenseits der Frische gilt
„kein aktueller Stand seit …“ (``geraete_tco_karten.alt_marke_fuer``).
"""

from __future__ import annotations

from .geraete_notbremse import DELTA_BEDINGT


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
    "versand_hinweise",
    "luecken",
    "aktionen",
)
KURZ_VERALTET = "Preis veraltet"
SATZ_VERALTET_OHNE_DATUM = "Preis veraltet – nicht mehr bestätigt."
KURZ_PRUEFUNG = "Preis in Prüfung"
SATZ_PRUEFUNG = "Preis in Prüfung."
KURZ_BEDINGT = DELTA_BEDINGT
SATZ_BEDINGT = f"{DELTA_BEDINGT} – nicht vergleichbar"


def veraltet(frisch: bool | None, veraltet_pruefung: bool) -> bool:
    """DIE Definition von „Preis veraltet“ (Clean Code 7): älter als die Frischegrenze
    oder von der Prüfstelle als veraltet gestempelt (Regel 16) - die zwei Wege, auf
    denen ein alter Preis in die Daten kommt. Zeile, Karte und Export lesen sie hier."""
    return frisch is False or bool(veraltet_pruefung)


def preis_veraltet(karte: dict) -> bool:
    """Ist der Preis der Karte nicht mehr bestätigt? (``veraltet`` an ihren Feldern.)"""
    return veraltet(karte.get("frisch"), karte.get("veraltet_pruefung", False))


def in_pruefung(karte: dict) -> bool:
    """Steht der Preis der Karte in Quarantäne? (``quarantaene`` aus der Notbremse.)"""
    return bool(karte.get("quarantaene"))


def ist_bedingt(karte: dict) -> bool:
    """Setzt der Preis der Karte ein Zweitprodukt voraus? (``bedingter_tarif``.)"""
    return bool(karte.get("bedingter_tarif"))


def grund(stand: str, abgerufen_am: str = "") -> str:
    """Der Satz der Lücke: „Preis veraltet: <Stand>.“, ohne Stand der Hinweis ohne
    Datum. Fehlt die Marke, wird sie aus dem Abrufdatum gebildet."""
    if not stand and abgerufen_am:
        from .geraete_tco_karten import alt_marke_fuer

        stand = alt_marke_fuer(abgerufen_am)
    return f"Preis veraltet: {stand}." if stand else SATZ_VERALTET_OHNE_DATUM


def buendel_luecke(b, heute: str) -> str:
    """Der Lückensatz eines Bündels ohne darstellbaren Preis, sonst ``""``.

    Plus-Tarif (Zweitprodukt), veraltet (Preisstand) oder in Quarantäne (Prüfstelle).
    Dieselbe Entscheidung wie ``anzeige`` an der Karte (``frisch`` aus ``ist_frisch``,
    die Flags aus der Notbremse), für Leser, die keine Karte haben (Export).
    """
    from . import geraete_notbremse
    from .geraete_tco_karten import ist_frisch

    frisch = ist_frisch(b.abgerufen_am, heute)
    flags = geraete_notbremse.felder(b, heute)
    if flags["bedingter_tarif"]:
        return SATZ_BEDINGT
    if veraltet(frisch, flags["veraltet_pruefung"]):
        return grund(marke(b.abgerufen_am, heute, frisch), b.abgerufen_am)
    if in_pruefung(flags):
        return SATZ_PRUEFUNG
    return ""


def anzeige(karte: dict) -> dict:
    """Die Karte für die Zeile: Plus-, veralteter oder geprüfter Preis wird zur Lücke.

    Liefert dieselbe Karte, wenn der Preis gilt; sonst eine Kopie ohne jeden
    Betrag, mit ``belastbar`` falsch und dem Grund in ``leer_grund``. Die Karte
    selbst bleibt unverändert, Auswahl und Δ lesen sie wie bisher.
    """
    if not karte.get("sku_id"):
        return karte
    if ist_bedingt(karte):
        kurz_, satz = KURZ_BEDINGT, SATZ_BEDINGT
    elif preis_veraltet(karte):
        kurz_, satz = (
            KURZ_VERALTET,
            grund(karte.get("alt_marke") or "", karte.get("abgerufen_am") or ""),
        )
    elif in_pruefung(karte):
        kurz_, satz = KURZ_PRUEFUNG, SATZ_PRUEFUNG
    else:
        return karte
    kopie = dict(karte)
    for feld in _PREISFELDER_LEER:
        kopie[feld] = None if feld != "delta_kurz" else ""
    for feld in _PREISFELDER_LISTE:
        kopie[feld] = []
    kopie["belastbar"] = False
    kopie["luecke_kurz"] = kurz_
    kopie["leer_grund"] = satz
    return kopie
