"""Notbremse der Geräteseite: welche Karte in Sieger, Δ und Kernzahl zählt.

Datenkonzept Geräteradar, Schritt 1 (docs/datenkonzept-geraete.md): Nur gemessene
Bündel zählen. Ein Bündel mit ``herleitung`` (o2 aus Tarifsumme minus Geräterate)
stand so nie auf der Anbieterseite und ist eine Schätzung. Ausgenommen sind Rechenwege,
die eine Preisliste exakt nachrechnen (``HERLEITUNG_PREISLISTE``, 1&1-Tarifaufschlag):
sie zählen wie gemessene. Ein Bündel, in dessen Preis eine
abgelaufene Aktion steckt, ist veraltet. Ebenso eines, dessen Tarifpreis ein
Zweitprodukt voraussetzt (o2 „Plus“, ``ist_bedingter_tarif``): der Vergleich nennt
Neuvertragspreise ohne Boni, lieber fehlt der o2-Wert als ein zu niedriger. Beide
bleiben als Zeile sichtbar, stellen aber weder Δ noch Referenz noch Sieger, keine
Bewegung und keinen Günstigst-Wert; der Export nennt denselben Zustand.

Schritt 7: Ebenso ein Bündel, dem die Prüfstelle (``analyze/geraete_regeln``) den Status
Quarantäne oder veraltet gegeben hat oder an dem sie gescheitert ist (``unbekannt``);
gelesen wird ihr Vermerk im Feld ``pruefung`` (``geraete_pruefstatus.lies_vermerk``),
die Gründe heißen wie die Regeln (``REGELN``). Ein Bündel ohne Vermerk ist nie geprüft
worden und zählt wie vor der Prüfstelle.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..analyze.geraete_pruefstatus import (
    FELD_PRUEFUNG,
    HERLEITUNG_EINMALZAHLUNG,
    HERLEITUNG_PREISLISTE,
    QUARANTAENE,
    REGEL_ANSCHLUSS,
    REGEL_SORTIMENT,
    REGELN,
    UNBEKANNT,
    VERALTET,
    abgelaufene_aktionen,
    buendel_zaehlt,
    ist_bedingter_tarif,
    ist_schaetzung,
    lies_vermerk,
)
from ..tco_model import Aktion, Buendel, aktionen_aus

DELTA_SCHAETZUNG = "nicht direkt genannt"
SATZ_SCHAETZUNG = (
    "Kein Abstand zur Vodafone-Referenz: der Anbieter nennt diesen Preis nicht "
    "direkt, er ist aus seinen Angaben berechnet."
)
HERLEITUNG_SATZ = {
    "tarifsumme_minus_geraeterate": (
        "{anbieter} nennt den Tarifpreis hier nicht einzeln – berechnet als "
        "Monatspreis minus Geräterate."
    ),
    "tarifaufschlag_aus_tarifraster": (
        "{anbieter} nennt den Monatspreis für diesen Tarif nicht beim Gerät – "
        "berechnet aus dem Grundangebot plus Tarifaufschlag der Preisliste."
    ),
    "schlusszahlung_aus_grundtarif": (
        "{anbieter} nennt die Schlusszahlung nur beim Grundtarif – von dort übernommen."
    ),
    HERLEITUNG_EINMALZAHLUNG: (
        "{anbieter}-Wert widersprüchlich, neu messen – die Einmalzahlung weicht "
        "vom Wert der anderen Tarife desselben Geräts ab."
    ),
}
HERLEITUNG_SATZ_SONST = (
    "{anbieter} nennt diesen Preis nicht direkt – berechnet aus seinen Angaben."
)
DELTA_BEDINGT = "nur mit Zweitprodukt"
SATZ_BEDINGT = (
    "Kein Abstand zur Vodafone-Referenz: der Tarifpreis gilt nur, wenn ein "
    "zweites Produkt gebucht wird."
)
DELTA_AKTION_ABGELAUFEN = "Aktion abgelaufen"
SATZ_AKTION_ABGELAUFEN = (
    "Kein Abstand zur Vodafone-Referenz: die eingerechnete Aktion ist abgelaufen."
)
DELTA_QUARANTAENE = "Quarantäne"
SATZ_QUARANTAENE = (
    "Kein Abstand zur Vodafone-Referenz: dieser Preis verletzt eine Prüfregel."
)
DELTA_SORTIMENT = "nicht im Sortiment"
SATZ_SORTIMENT = (
    "Kein Abstand zur Vodafone-Referenz: der Anbieter führt dieses Gerät nicht mehr."
)
DELTA_VERALTET = "veraltet"
SATZ_VERALTET = "Kein Abstand zur Vodafone-Referenz: dieser Preis ist veraltet."
DELTA_ANSCHLUSS = "Anschlusspreis nicht mehr belegt"
SATZ_ANSCHLUSS = (
    "Kein Abstand zur Vodafone-Referenz: eine neuere Messung dieses Tarifs nennt "
    "einen anderen Anschlusspreis."
)
DELTA_UNGEPRUEFT = "Prüfung gescheitert"
SATZ_UNGEPRUEFT = (
    "Kein Abstand zur Vodafone-Referenz: die Prüfung dieses Preises ist gescheitert."
)
_PRUEFZUSTAENDE = (
    ("nicht_im_sortiment", DELTA_SORTIMENT, SATZ_SORTIMENT),
    ("quarantaene", DELTA_QUARANTAENE, SATZ_QUARANTAENE),
    ("anschluss_widerlegt", DELTA_ANSCHLUSS, SATZ_ANSCHLUSS),
    ("veraltet_pruefung", DELTA_VERALTET, SATZ_VERALTET),
    ("pruefung_gescheitert", DELTA_UNGEPRUEFT, SATZ_UNGEPRUEFT),
)


def felder(b: Buendel, heute: str) -> dict:
    """Die Notbremse-Felder einer Karte: Flags, ``zaehlt``, benannter Zustand.

    Abgelaufen ist eine eingerechnete Aktion, die der Anbieter vor ``heute``
    befristet hat (``Aktion.gilt_am``); ein Platzhalter-Ende wie 2050 läuft weiter.
    """
    return {
        **_felder(
            b.herleitung, b.aktionen, heute, b.pruefung, b.anbieter, b.tarif_name
        ),
        "herleitung_satz": herleitung_satz(b.anbieter, b.herleitung),
        "aus_preisliste": b.herleitung.strip() in HERLEITUNG_PREISLISTE,
    }


def herleitung_satz(anbieter: str, herleitung: str) -> str:
    """Der Satz an der Zeile, wie ein nicht direkt genannter Preis berechnet ist;
    leer für einen gemessenen oder aus der Preisliste exakt nachgerechneten Preis."""
    if not ist_schaetzung(herleitung):
        return ""
    vorlage = HERLEITUNG_SATZ.get(herleitung.strip(), HERLEITUNG_SATZ_SONST)
    return vorlage.format(anbieter=anbieter)


def felder_aus_satz(satz: dict, heute: str) -> dict:
    """Dieselben Felder für einen gelesenen Bündel-Rohsatz (``geraete_tco.json``),
    dessen Aktionen über ``aktionen_aus`` gelesen werden wie im Store."""
    herleitung = str(satz.get("herleitung") or "")
    aktionen = aktionen_aus(satz.get("aktionen"))
    return _felder(
        herleitung,
        aktionen,
        heute,
        satz.get(FELD_PRUEFUNG),
        str(satz.get("anbieter") or ""),
        str(satz.get("tarif_name") or ""),
    )


def _felder(
    herleitung: str,
    aktionen: Iterable[Aktion],
    heute: str,
    pruefung: object,
    anbieter: str = "",
    tarif_name: str = "",
) -> dict:
    aktionen = list(aktionen)
    schaetzung = ist_schaetzung(herleitung)
    veraltet = bool(abgelaufene_aktionen(aktionen, heute))
    vermerk = lies_vermerk(pruefung)
    status = vermerk.status
    flags = {
        "schaetzung": schaetzung,
        "bedingter_tarif": ist_bedingter_tarif(anbieter, tarif_name),
        "veraltet_aktion": veraltet,
        "quarantaene": status == QUARANTAENE,
        "veraltet_pruefung": status == VERALTET,
        "nicht_im_sortiment": status == VERALTET and REGEL_SORTIMENT in vermerk.regeln,
        "anschluss_widerlegt": status == VERALTET and REGEL_ANSCHLUSS in vermerk.regeln,
        "pruefung_gescheitert": status == UNBEKANNT,
        "pruefgruende": [
            f"Regel {n}: {REGELN.get(n, '?')}"
            for n in vermerk.regeln
            if n != REGEL_SORTIMENT
        ],
    }
    return {
        **flags,
        "zaehlt": buendel_zaehlt(
            herleitung, aktionen, heute, pruefung, anbieter, tarif_name
        ),
        "notbremse": zustand(flags),
    }


def zaehlt(karte: dict) -> bool:
    """Darf die Karte Δ, Referenz oder Sieger stellen? Nur ohne Schätzung, ohne
    abgelaufene Aktion und mit Status gültig; Karten ohne die Felder (Listungen ohne
    Bündel) und nie geprüfte Bündel zählen wie bisher."""
    return karte.get("zaehlt", True)


NUR_HEUTE = ("veraltet_aktion", "veraltet_pruefung")
IMMER = (
    "schaetzung",
    "bedingter_tarif",
    "quarantaene",
    "pruefung_gescheitert",
    "nicht_im_sortiment",
)


def zaehlt_am_tag(karte: dict) -> bool:
    """Zählte die Karte an IHREM eigenen Messtag - die Frage einer Zeitreihe.

    ``zaehlt`` beantwortet die Frage für HEUTE. ``NUR_HEUTE`` sind die Urteile
    über den heutigen Stand eines Bündels: „veraltet“ heißt, der Preis ist
    HEUTE zu alt oder die eingerechnete Aktion ist HEUTE abgelaufen. An seinem
    Messtag war beides nicht so; wer sie rückblickend anwendet, löscht mit dem
    heutigen Stand die Vergangenheit (Befund 13.11.2026: congstar stand mit 7
    statt 45 Messtagen in der Herstellergrafik). Ob eine Messung an ihrem Tag
    frisch war, entscheidet ``geraete_tco_karten.ist_frisch`` je Tag. Was in
    ``IMMER`` steht, war auch rückblickend nie ein gültiger Vergleich.
    """
    if karte.get("zaehlt"):
        return True
    if any(karte.get(flag) for flag in IMMER):
        return False
    return any(karte.get(flag) for flag in NUR_HEUTE)


def zustand(karte: dict) -> dict | None:
    """Der benannte Δ-Zustand einer Karte, die nicht zählt, sonst ``None``.

    Ein Zustand der Prüfstelle nennt im Satz jede verletzte Regel mit Nummer.
    """
    if karte.get("schaetzung"):
        return {"kurz": DELTA_SCHAETZUNG, "satz": SATZ_SCHAETZUNG}
    if karte.get("bedingter_tarif"):
        return {"kurz": DELTA_BEDINGT, "satz": SATZ_BEDINGT}
    if karte.get("veraltet_aktion"):
        return {"kurz": DELTA_AKTION_ABGELAUFEN, "satz": SATZ_AKTION_ABGELAUFEN}
    gruende = [f"{g}." for g in karte.get("pruefgruende") or []]
    for flag, kurz_, satz in _PRUEFZUSTAENDE:
        if karte.get(flag):
            return {"kurz": kurz_, "satz": " ".join([satz, *gruende])}
    return None


def kurz(b: Buendel, heute: str) -> str:
    """Der kurze Zustand eines Bündels für eine Tabellenzelle, leer, wenn es zählt."""
    return (felder(b, heute)["notbremse"] or {}).get("kurz", "")


def namen(karten: list) -> list[str]:
    """„1&1 (Schätzung)“ je Anbieter und Grund, wo die Notbremse Karten nimmt."""
    return list(dict.fromkeys(f"{k['anbieter']} ({gruende([k])})" for k in karten))


def gruende(karten: list) -> str:
    """„Schätzung“, „Aktion abgelaufen“, „Quarantäne“ …, je Grund einmal."""
    kurz = (z["kurz"] for k in karten if (z := zustand(k)) is not None)
    return ", ".join(dict.fromkeys(kurz))


def leersatz(slot: dict, kopf: str) -> str | None:
    """Der Satz für ein Paar der Zeitreihe, das nur Messungen hat, die nicht
    zählen (F3, 14.10.2026); `None`, wenn es gar keine Messungen hat."""
    if grund := gruende([m for tage in slot.values() for m in tage.values()]):
        return (
            f"{kopf} liegen nur Preise vor, die nicht im Vergleich zählen "
            f"({grund}). Sie stehen in den Bündel-Zeilen darunter."
        )
    return None


def nur_zaehlende(messungen: dict) -> dict:
    """Die Messungen der Zeitreihe (``{(modell, band): {anbieter: {tag: m}}}``) ohne
    die, deren Bündel nicht zählt; ein Anbieter ohne solche fällt heraus."""
    fertig: dict = {}
    for paar, anbieter in messungen.items():
        for name, slot in anbieter.items():
            if tage := {t: m for t, m in slot.items() if zaehlt(m)}:
                fertig.setdefault(paar, {})[name] = tage
    return fertig
