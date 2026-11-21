"""Kundenwege der Gegenprobe je Anbieter: öffnen, wählen wie ein Kunde, lesen.

Ein Weg öffnet die Seite des Bündels, wählt per Klick auf den sichtbaren Text
Speicher, Zahlweise und Tarif und nennt die Anker des Preisbereichs; ``lies_gruppe``
gibt dessen ``innerText`` und ein Bild zurück. Die Werkzeuge (Öffnen, Klicken,
Bereich, Bild) stehen in ``gegenprobe_browser``; dort steht auch, was Harte Regel 4
hier bedeutet.

Ein Seitenbesuch prüft alle gewählten Bündel derselben Seite (``Weg.seite``): der Weg
öffnet die Seite einmal und wählt danach je Bündel nur noch auf der offenen Seite
(o2 die Ratenzahl, Telekom die Rate, Vodafone und 1&1 jeden Tarif der Tarifauswahl).
Ein Weg ohne eigene Gruppe prüft je Besuch ein Bündel.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import partial
from html import escape
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from . import gegenprobe_einsundeins as einsundeins
from .gegenprobe_browser import (
    FENSTER,
    KLICKFRIST_MS,
    NACH_KLICK_MS,
    SPRACHE,
    Gesperrt,
    Lesung,
    NichtPruefbar,
    bild_von,
    klicke,
    lehne_einwilligung_ab,
    mit_beleg,
    oeffne,
    ruhe,
    sichtbares_html,
    speicher_aus_sku,
    text_von,
)
from .gegenprobe_schritte import (
    HOECHSTE_TARIFKACHELN,
    Oeffnen,
    Schritte,
    nach_tarif,
    nicht_zur_wahl,
    warte_bis,
)
from .gegenprobe_sicht import VODAFONE_TRENNER

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

GRUND_KEIN_WEG = "Für diesen Anbieter gibt es noch keinen Kundenweg"
GRUND_NICHT_ERREICHT = "Der Seitenbesuch kam nicht bis zu diesem Bündel"


def _text_gleich(text: str) -> re.Pattern:
    return re.compile(r"^\s*" + re.escape(text) + r"\s*$", re.I)


def _je_buendel(b: dict) -> str:
    return b["id"]


def _ohne_parameter(url: str, *namen: str) -> str:
    teile = urlparse(url)
    rest = [(k, v) for k, v in parse_qs(teile.query).items() if k not in namen]
    return urlunparse(teile._replace(query=urlencode(sorted(rest), doseq=True)))


@dataclass(frozen=True)
class Weg:
    """Kundenweg eines Anbieters: Klicks, dann Text- und Bildbereich."""

    waehle: Callable[[Page, list[dict], Oeffnen], Schritte]
    """Öffnet und wählt je Bündel der Gruppe; gibt nach jeder Wahl das Bündel und
    zusätzlichen sichtbaren Text vorab zurück (oder den Grund, warum es nicht ging)."""
    text_anker: tuple[tuple[str, ...], ...]
    """Je Bereich die Anker; die Texte der Bereiche stehen untereinander."""
    bild_anker: tuple[str, ...]
    seite: Callable[[dict], str] = field(default=_je_buendel)
    """Welcher Seitenbesuch das Bündel prüft; gleiche Werte teilen einen Besuch."""


def _einzeln(
    waehle: Callable[[Page, dict, Oeffnen], str],
) -> Callable[[Page, list[dict], Oeffnen], Schritte]:
    """Ein Weg, der je Bündel öffnet und wählt (``waehle`` wirft ``NichtPruefbar``)."""

    def schritte(seite: Page, gruppe: list[dict], oeffnen: Oeffnen) -> Schritte:
        for b in gruppe:
            try:
                yield b, waehle(seite, b, oeffnen)
            except NichtPruefbar as fehler:
                yield b, fehler

    return schritte


def _telekom_seite(b: dict) -> str:
    """Telekom: eine Seite je Gerät und Tarif (``tariffId``); die Rate per Klick."""
    return _ohne_parameter(b["quelle_url"], "instalmentId", "installmentValue")


def _telekom(seite: Page, gruppe: list[dict], oeffnen: Oeffnen) -> Schritte:
    oeffnen(seite, gruppe[0]["quelle_url"])
    for b in gruppe:
        n = b.get("laufzeit_monate")
        if not n:
            yield b, NichtPruefbar("Ratenzahl fehlt im Bestand")
            continue
        muster = re.compile(rf"mtl\.\s*x\s*{n}\s*$")
        try:
            klicke(seite, seite.get_by_text(muster), f"{n} Raten")
        except NichtPruefbar as fehler:
            yield b, fehler
            continue
        yield b, ""


O2_ANKER = ("Dein Angebot", "Gerät monatlich", "einmalig gesamt")


def _o2_seite(b: dict) -> str:
    """o2: eine Seite je Gerät und Tarif (``tarif``), die Ratenzahl wählt die Kachel."""
    return _ohne_parameter(b["quelle_url"], "ratenzahlung")


def _o2_raten(seite: Page) -> int | None:
    try:
        text = text_von(seite, O2_ANKER)
    except NichtPruefbar:
        return None
    treffer = re.search(r"Ratenzahlung:?\s*(\d+)\s*Monate", text, re.I)
    return int(treffer.group(1)) if treffer else None


def _o2_hat_raten(seite: Page, n: int) -> bool:
    return _o2_raten(seite) == n


def _o2(seite: Page, gruppe: list[dict], oeffnen: Oeffnen) -> Schritte:
    oeffnen(seite, gruppe[0]["quelle_url"])
    for b in sorted(gruppe, key=lambda s: s.get("laufzeit_monate") or 0):
        n = b.get("laufzeit_monate")
        if not n:
            yield b, NichtPruefbar("Ratenzahl fehlt im Bestand")
            continue
        if _o2_raten(seite) != n:
            kachel = seite.locator(
                'tef-choice-panel:has(input[name="payment-plans"]) > label',
                has_text=re.compile(rf"^\s*{n}\s*Monate"),
            )
            try:
                klicke(seite, kachel, f"{n} Monate")
            except NichtPruefbar as fehler:
                yield b, fehler
                continue
            if not warte_bis(seite, partial(_o2_hat_raten, seite, n)):
                yield b, NichtPruefbar(f"Die Seite übernimmt {n} Monate nicht")
                continue
        yield b, ""


def _congstar(seite: Page, b: dict, oeffnen: Oeffnen) -> str:
    url = b["quelle_url"]
    oeffnen(seite, url)
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


def _tarifwelt(seite: Page, b: dict, oeffnen: Oeffnen) -> str:
    oeffnen(seite, b["quelle_url"])
    return ""


def _vodafone_seite(b: dict) -> str:
    """Vodafone: Produktseite je Gerät; je Speicher und Raten eine Tarifauswahl, auf
    der jeder gewählte Tarif dieser Kombination nacheinander gelesen wird."""
    speicher = speicher_aus_sku(b.get("sku_id") or "")
    return f"{b['quelle_url']}|{speicher}|{b.get('laufzeit_monate')}"


def _vodafone(seite: Page, gruppe: list[dict], oeffnen: Oeffnen) -> Schritte:
    erstes = gruppe[0]
    speicher = speicher_aus_sku(erstes.get("sku_id") or "")
    n = erstes.get("laufzeit_monate")
    if not speicher or not n:
        for b in gruppe:
            yield b, NichtPruefbar("Speicher oder Ratenzahl fehlt im Bestand")
        return
    oeffnen(seite, erstes["quelle_url"])
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
    kopf = "Gewählt: " + " ".join(gewaehlt_text.split()[:2])
    offen = nach_tarif(gruppe, str.strip)
    kacheln = seite.locator('div:has(> input[name="option-picker-gm-tariff"])')
    for stelle in range(min(kacheln.count(), HOECHSTE_TARIFKACHELN)):
        if not offen:
            return
        kacheln.nth(stelle).click(timeout=KLICKFRIST_MS)
        seite.wait_for_timeout(NACH_KLICK_MS)
        for ziel in list(offen):
            name = seite.get_by_text(re.compile(rf"^\s*{re.escape(ziel)}\s+mit\b"))
            if name.count() and name.first.is_visible():
                vorab = (
                    f"{kopf}\n{produkt}{VODAFONE_TRENNER}{name.first.inner_text()}\n"
                )
                for b in offen.pop(ziel):
                    yield b, vorab
                break
    yield from nicht_zur_wahl(offen)


WEGE: dict[str, Weg] = {
    "telekom": Weg(
        _telekom,
        (
            ("Zahlungsoptionen", "Gesamtpreis des Geräts"),
            ("Einmalige Zahlung", "Gesamtpreis monatlich", "Tarif ändern"),
        ),
        ("Einmalige Zahlung", "Gesamtpreis monatlich", "Tarif ändern"),
        _telekom_seite,
    ),
    "o2": Weg(_o2, (O2_ANKER,), O2_ANKER, _o2_seite),
    "congstar": Weg(
        _einzeln(_congstar),
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
        _vodafone_seite,
    ),
    "1-1": Weg(
        einsundeins.waehle, (einsundeins.ANKER,), einsundeins.ANKER, einsundeins.seite
    ),
    **{
        f"saturn-mediamarkt-{netz}-netz": Weg(
            _einzeln(_tarifwelt),
            (("Mein Tarif", "Gerät einmalig", "Anschlussgebühr"),),
            ("Mein Tarif", "Gerät einmalig", "Anschlussgebühr"),
        )
        for netz in ("telekom", "vodafone", "o2")
    },
}
"""Wege je Anbieter-Schlüssel (``gegenprobe.anbieter_aus_id``)."""


def seite_von(schluessel: str, buendel: dict) -> str:
    """Der Seitenbesuch, der ``buendel`` prüft (``gegenprobe_reihe.gruppiere``)."""
    weg = WEGE.get(schluessel)
    seite = weg.seite(buendel) if weg is not None else buendel["id"]
    return f"{schluessel}|{seite}"


def lies_gruppe(
    browser: Browser,
    schluessel: str,
    gruppe: list[dict],
    kennung: str | None,
    vor_laden: Callable[[str], None] | None = None,
    aufnehmen: bool = False,
) -> Iterator[tuple[dict, Lesung | Exception]]:
    """Ein Seitenbesuch für die Bündel ``gruppe`` in einem frischen Kontext.

    Gibt je Bündel die ``Lesung`` oder den Fehler zurück (``Gesperrt``,
    ``NichtPruefbar`` mit Grund); bricht der Weg ab, gilt sein Fehler für jedes noch
    nicht gelesene Bündel. ``vor_laden(url)`` läuft vor jedem Laden einer Adresse
    (robots.txt, Abstand zum Host) und darf ``NichtPruefbar`` werfen. Wer die Schleife
    früher beendet (Zeitbudget), schließt den Kontext mit ``close()``.
    """
    from playwright.sync_api import Error as PlaywrightFehler

    weg = WEGE.get(schluessel)
    if weg is None:
        for b in gruppe:
            yield b, NichtPruefbar(GRUND_KEIN_WEG)
        return

    def oeffnen(seite: Page, url: str) -> None:
        if vor_laden is not None:
            vor_laden(url)
        oeffne(seite, url)

    offen = {b["id"]: b for b in gruppe}
    kontext = browser.new_context(
        viewport=FENSTER, locale=SPRACHE, user_agent=kennung, service_workers="block"
    )
    try:
        seite = kontext.new_page()
        schritte = weg.waehle(seite, list(gruppe), oeffnen)
        abbruch: Exception = NichtPruefbar(GRUND_NICHT_ERREICHT)
        while offen:
            try:
                b, vorab = next(schritte)
            except StopIteration:
                break
            except (Gesperrt, NichtPruefbar) as fehler:
                abbruch = fehler
                break
            except PlaywrightFehler as fehler:
                abbruch = NichtPruefbar(_browserfehler(fehler))
                break
            if offen.pop(b["id"], None) is not None:
                yield b, _lesung(seite, weg, vorab, aufnehmen)
        for b in list(offen.values()):
            yield b, mit_beleg(abbruch, seite)
    finally:
        kontext.close()


def _browserfehler(fehler: Exception) -> str:
    return f"Browser: {str(fehler).splitlines()[0][:160]}"


def _lesung(
    seite: Page, weg: Weg, vorab: str | Exception, aufnehmen: bool
) -> Lesung | Exception:
    """Text und Bild des Preisbereichs nach einer Wahl, oder warum sie nicht lesbar
    waren (``NichtPruefbar`` mit Adresse und Bild); der Besuch geht danach weiter."""
    from playwright.sync_api import Error as PlaywrightFehler

    if isinstance(vorab, Exception):
        return mit_beleg(vorab, seite)
    try:
        text = vorab + "\n".join(text_von(seite, a) for a in weg.text_anker)
        html = ""
        if aufnehmen:
            zeilen = "".join(f"<div>{escape(z)}</div>" for z in vorab.splitlines())
            html = "\n".join(
                [zeilen, *(sichtbares_html(seite, a) for a in weg.text_anker)]
            )
    except PlaywrightFehler as fehler:
        return mit_beleg(NichtPruefbar(_browserfehler(fehler)), seite)
    except NichtPruefbar as fehler:
        return mit_beleg(fehler, seite)
    bild, bild_fehlt = bild_von(seite, weg.bild_anker)
    return Lesung(text, seite.url, bild, bild_fehlt, html)


def lies(
    browser: Browser,
    schluessel: str,
    buendel: dict,
    kennung: str | None,
    aufnehmen: bool = False,
) -> Lesung:
    """Ein Bündel allein (``lies_gruppe`` mit einer Gruppe aus einem Bündel).

    Wirft ``Gesperrt`` bei Bot-Schutz und ``NichtPruefbar`` mit Grund, wenn der Weg
    nicht bis zum Preis kommt."""
    for _, ergebnis in lies_gruppe(
        browser, schluessel, [buendel], kennung, aufnehmen=aufnehmen
    ):
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return ergebnis
    raise NichtPruefbar(GRUND_NICHT_ERREICHT)
