"""Kundenwege der Gegenprobe je Anbieter: öffnen, wählen wie ein Kunde, lesen.

Ein Weg öffnet die Seite, die der Bestand als Quelle nennt (``quelle_url``), wählt per
Klick auf den sichtbaren Text Speicher, Zahlweise und Tarif und nennt die Anker des
Preisbereichs; ``lies`` gibt dessen ``innerText`` und ein Bild zurück. Die Werkzeuge
(Öffnen, Klicken, Bereich, Bild) stehen in ``gegenprobe_browser``; dort steht auch,
was Harte Regel 4 hier bedeutet.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING

from .gegenprobe_browser import (
    FENSTER,
    KLICKFRIST_MS,
    NACH_KLICK_MS,
    SPRACHE,
    Lesung,
    NichtPruefbar,
    bild_von,
    klicke,
    lehne_einwilligung_ab,
    oeffne,
    ruhe,
    sichtbares_html,
    speicher_aus_sku,
    text_von,
)
from .gegenprobe_sicht import VODAFONE_TRENNER

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

HOECHSTE_TARIFKACHELN = 8


def _text_gleich(text: str) -> re.Pattern:
    return re.compile(r"^\s*" + re.escape(text) + r"\s*$", re.I)


@dataclass(frozen=True)
class Weg:
    """Kundenweg eines Anbieters: Klicks, dann Text- und Bildbereich."""

    waehle: Callable[[Page, dict], str]
    """Öffnet und wählt; gibt zusätzlichen sichtbaren Text vorab zurück (oft leer)."""
    text_anker: tuple[tuple[str, ...], ...]
    """Je Bereich die Anker; die Texte der Bereiche stehen untereinander."""
    bild_anker: tuple[str, ...]


def _telekom(seite: Page, b: dict) -> str:
    oeffne(seite, b["quelle_url"])
    n = b.get("laufzeit_monate")
    if not n:
        raise NichtPruefbar("Ratenzahl fehlt im Bestand")
    muster = re.compile(rf"mtl\.\s*x\s*{n}\s*$")
    klicke(seite, seite.get_by_text(muster), f"{n} Raten")
    return ""


def _o2(seite: Page, b: dict) -> str:
    oeffne(seite, b["quelle_url"])
    return ""


def _congstar(seite: Page, b: dict) -> str:
    url = b["quelle_url"]
    oeffne(seite, url)
    speicher = speicher_aus_sku(b.get("sku_id") or "")
    if speicher:
        klicke(seite, seite.get_by_text(_text_gleich(speicher)), speicher)
    if "planId=" not in url:
        name = b.get("tarif_name") or ""
        klicke(seite, seite.get_by_text(_text_gleich(name)), name)
    if "installmentPlanId=" not in url and b.get("laufzeit_monate"):
        n = b["laufzeit_monate"]
        klicke(seite, seite.get_by_text(f"{n} mtl. Zahlungen"), f"{n} Zahlungen")
    bindung = b.get("tarif_bindung_monate")
    if bindung is None:
        raise NichtPruefbar("Tariflaufzeit steht nicht im Bestand")
    wahl = "24 Monate Laufzeit" if bindung else "Ohne Laufzeit"
    klicke(seite, seite.get_by_text(wahl), wahl)
    return ""


def _tarifwelt(seite: Page, b: dict) -> str:
    oeffne(seite, b["quelle_url"])
    return ""


def _vodafone(seite: Page, b: dict) -> str:
    oeffne(seite, b["quelle_url"])
    speicher = speicher_aus_sku(b.get("sku_id") or "")
    n = b.get("laufzeit_monate")
    if not speicher or not n:
        raise NichtPruefbar("Speicher oder Ratenzahl fehlt im Bestand")
    kapazitaet = seite.locator(
        "#device-details-option-picker-capacity label", has_text=speicher
    )
    klicke(seite, kapazitaet, speicher)
    raten = seite.locator(
        "#device-details-option-picker-financing-duration label",
        has_text=re.compile(rf"^\s*{n}\s*Raten"),
    )
    klicke(seite, raten, f"{n} Raten")
    gewaehlt = seite.locator(
        "#device-details-option-picker-financing-duration "
        "div:has(input:checked) > label"
    )
    gewaehlt_text = gewaehlt.first.inner_text() if gewaehlt.count() else ""
    produkt = text_von(seite, ("Preisübersicht", "Pro Monat", "Zur Tarifauswahl"))
    weiter = seite.locator(
        "#device-details-offer-summary-card a", has_text="Zur Tarifauswahl"
    )
    klicke(seite, weiter, "Zur Tarifauswahl")
    ruhe(seite)
    lehne_einwilligung_ab(seite)
    ziel = (b.get("tarif_name") or "").strip()
    kacheln = seite.locator('div:has(> input[name="option-picker-gm-tariff"])')
    for stelle in range(min(kacheln.count(), HOECHSTE_TARIFKACHELN)):
        kacheln.nth(stelle).click(timeout=KLICKFRIST_MS)
        seite.wait_for_timeout(NACH_KLICK_MS)
        name = seite.get_by_text(re.compile(rf"^\s*{re.escape(ziel)}\s+mit\b"))
        if name.count() and name.first.is_visible():
            kopf = "Gewählt: " + " ".join(gewaehlt_text.split()[:2])
            return f"{kopf}\n{produkt}{VODAFONE_TRENNER}{name.first.inner_text()}\n"
    raise NichtPruefbar(f"Tarif {ziel} steht auf der Tarifauswahl nicht zur Wahl")


def _einsundeins(seite: Page, b: dict) -> str:
    oeffne(seite, b["quelle_url"])
    speicher = speicher_aus_sku(b.get("sku_id") or "")
    n = b.get("laufzeit_monate")
    if not n:
        raise NichtPruefbar("Ratenzahl fehlt im Bestand")
    if speicher:
        klicke(seite, seite.get_by_text(_text_gleich(speicher)), speicher)
    reiter = seite.locator("button.contract-toggle__contract", has_text=f"{n} Monate")
    klicke(seite, reiter, f"{n} Monate")
    klicke(seite, seite.get_by_text(f"{n} Monate Fix"), f"{n} Monate Fix")
    uebersicht = seite.locator("button.price-summary-overlay__modal-trigger")
    klicke(seite, uebersicht, "Preisübersicht anzeigen")
    return ""


WEGE: dict[str, Weg] = {
    "telekom": Weg(
        _telekom,
        (
            ("Zahlungsoptionen", "Gesamtpreis des Geräts"),
            ("Einmalige Zahlung", "Gesamtpreis monatlich", "Tarif ändern"),
        ),
        ("Einmalige Zahlung", "Gesamtpreis monatlich", "Tarif ändern"),
    ),
    "o2": Weg(
        _o2,
        (("Dein Angebot", "Gerät monatlich", "einmalig gesamt"),),
        ("Dein Angebot", "Gerät monatlich", "einmalig gesamt"),
    ),
    "congstar": Weg(
        _congstar,
        (
            ("Wie möchtest du dein Gerät bezahlen", "Einmalzahlung"),
            ("Summe einmalig", "in den ersten"),
        ),
        ("Summe einmalig", "in den ersten"),
    ),
    "vodafone": Weg(
        _vodafone,
        (("Preisübersicht", "Angebotspreis", "Weiter mit diesem Angebot"),),
        ("Preisübersicht", "Angebotspreis", "Weiter mit diesem Angebot"),
    ),
    "1-1": Weg(
        _einsundeins,
        (("Monatliche Gesamtkosten", "Ratenzahlung Hardware"),),
        ("Monatliche Gesamtkosten", "Ratenzahlung Hardware"),
    ),
    **{
        f"saturn-mediamarkt-{netz}-netz": Weg(
            _tarifwelt,
            (("Mein Tarif", "Gerät einmalig", "Anschlussgebühr"),),
            ("Mein Tarif", "Gerät einmalig", "Anschlussgebühr"),
        )
        for netz in ("telekom", "vodafone", "o2")
    },
}
"""Wege je Anbieter-Schlüssel (``gegenprobe.anbieter_aus_id``)."""


def lies(
    browser: Browser,
    schluessel: str,
    buendel: dict,
    kennung: str | None,
    aufnehmen: bool = False,
) -> Lesung:
    """Geht den Kundenweg für ``buendel`` in einem frischen Kontext und liest den Preis.

    Wirft ``Gesperrt`` bei Bot-Schutz und ``NichtPruefbar`` mit Grund, wenn der Weg
    nicht bis zum Preis kommt; andere Browserfehler gehen als ``NichtPruefbar`` weiter.
    """
    from playwright.sync_api import Error as PlaywrightFehler

    weg = WEGE.get(schluessel)
    if weg is None:
        raise NichtPruefbar("Für diesen Anbieter gibt es noch keinen Kundenweg")
    kontext = browser.new_context(
        viewport=FENSTER, locale=SPRACHE, user_agent=kennung, service_workers="block"
    )
    try:
        seite = kontext.new_page()
        try:
            vorab = weg.waehle(seite, buendel)
            text = vorab + "\n".join(text_von(seite, a) for a in weg.text_anker)
            html = ""
            if aufnehmen:
                zeilen = "".join(f"<div>{escape(z)}</div>" for z in vorab.splitlines())
                html = "\n".join(
                    [zeilen, *(sichtbares_html(seite, a) for a in weg.text_anker)]
                )
        except PlaywrightFehler as fehler:
            raise NichtPruefbar(
                f"Browser: {str(fehler).splitlines()[0][:160]}"
            ) from fehler
        bild, bild_fehlt = bild_von(seite, weg.bild_anker)
        return Lesung(text, seite.url, bild, bild_fehlt, html)
    finally:
        kontext.close()
