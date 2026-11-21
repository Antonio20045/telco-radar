"""Kundenweg der Gegenprobe bei 1&1 (Shop seit 20.11.2026).

Die Produktseite wählt Speicher und „N Monate Fix“ (Reiter „36 Monate“, „24 Monate“,
darunter „Fix“ und „+ 12 Monate Flex“); der Tarif steht erst auf der Tarifauswahl
``/flow2/mobile/ssc-private/tariffselect`` nach „Weiter zur Tarifauswahl“. Je Speicher
und Laufzeit ein Besuch (frischer Kontext, ein Warenkorb), darin jede gewählte
Tarifkachel nacheinander: Kachel klicken, bis die Preisleiste ihren Tarif nennt, dann
die Preisübersicht der Leiste öffnen; gelesen wird deren sichtbarer Text
(``gegenprobe_sicht.einsundeins``), nicht die Daten der Kacheln, die der Sammler liest.
Keine Kundendaten, kein weiterer Schritt.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse, urlunparse

from .gegenprobe_bild import GERAET, RATEN, SPEICHER, Aufnahme, Vorab, aufnehme
from .gegenprobe_browser import (
    KLICKFRIST_MS,
    NichtPruefbar,
    klicke,
    lehne_einwilligung_ab,
    ruhe,
    speicher_aus_sku,
)
from .gegenprobe_schritte import (
    HOECHSTE_TARIFKACHELN,
    TAKT_MS,
    Oeffnen,
    Schritte,
    nach_tarif,
    nicht_zur_wahl,
    norm,
    warte_bis,
)
from .gegenprobe_sicht import betrag

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

ANKER = ("Monatliche Gesamtkosten", "Ratenzahlung Hardware")
"""Die Preisübersicht der Preisleiste (Text und Bild)."""
_KACHEL = '.tariffbox:not(.d-none) .content-box:has(input[name="tariff-plan"])'
_EURO_MON = re.compile(r"(\d[\d.]*,(?:\d{2}|[–-]{1,2}))\s*€\s*/\s*Mon", re.I)


def produktseite(url: str) -> str:
    """Die Produktseite eines 1&1-Bündels: ``tariffChangeUrl`` der Tarifauswahl, die
    der Bestand als Quelle nennt, sonst die Quelle selbst (ohne Parameter)."""
    teile = urlparse(url)
    zurueck = parse_qs(teile.query).get("tariffChangeUrl")
    if zurueck:
        ziel = urlparse(zurueck[0], scheme="https")
        return urlunparse(ziel._replace(query="", fragment=""))
    return urlunparse(teile._replace(query="", fragment=""))


def seite(b: dict) -> str:
    """Ein Besuch je Produktseite, Speicher und Laufzeit."""
    speicher = speicher_aus_sku(b.get("sku_id") or "")
    return f"{produktseite(b['quelle_url'])}|{speicher}|{b.get('laufzeit_monate')}"


def leiste_tarif(text: str) -> str | None:
    """Der Tarifname in der Preisleiste („1&1 All-Net-Flat L“) oder None."""
    treffer = re.search(r"^\s*(1&1\s[^\n€]+?)\s*$", text, re.M)
    return treffer.group(1) if treffer else None


def leiste_rate(text: str) -> float | None:
    """Der erste Betrag „… €/Mon.“ (in der Preisleiste die Geräterate) oder None; die
    Seite setzt Euro, Komma und Cent in eigene Zeilen („74\\n,\\n–\\n€/Mon.“)."""
    treffer = _EURO_MON.search(re.sub(r"\s*,\s*", ",", text))
    return betrag(treffer.group(1)) if treffer else None


def _leiste(seite: Page) -> str:
    leiste = seite.locator("#pso")
    return leiste.first.inner_text() if leiste.count() else ""


def _zur_tarifauswahl(seite: Page, b: dict, oeffnen: Oeffnen) -> Aufnahme:
    """Produktseite: Speicher, Reiter „N Monate“, „N Monate Fix“, bis die Preisleiste
    die Rate von Fix zeigt; Bild der Auswahl (Gerät, Speicher, Raten), dann „Weiter
    zur Tarifauswahl“ mit derselben Rate."""
    speicher = speicher_aus_sku(b.get("sku_id") or "")
    n = b.get("laufzeit_monate")
    if not speicher or not n:
        raise NichtPruefbar("Speicher oder Ratenzahl fehlt im Bestand")
    oeffnen(seite, produktseite(b["quelle_url"]))
    kachel = seite.locator(
        "#hwd-configuration-section label.variant-chooser__tile", has_text=speicher
    )
    klicke(seite, kachel, speicher)
    reiter = seite.locator("button.contract-toggle__contract", has_text=f"{n} Monate")
    klicke(seite, reiter, f"{n} Monate")
    fix = seite.locator(
        ".contract-toggle__payment-models:not(.d-none) label.toggle-label",
        has_text=re.compile(rf"{n}\s*Monate\s*Fix", re.I),
    )
    klicke(seite, fix, f"{n} Monate Fix")
    rate = leiste_rate(fix.first.inner_text())
    if rate is None or not warte_bis(
        seite, lambda: leiste_rate(_leiste(seite)) == rate
    ):
        raise NichtPruefbar(f"Die Preisleiste übernimmt „{n} Monate Fix“ nicht")
    auswahl = aufnehme(seite, b, None, (GERAET, SPEICHER, RATEN))
    weiter = seite.locator(
        "#price-summary-overlay-cta > button", has_text="Weiter zur Tarifauswahl"
    )
    klicke(seite, weiter, "Weiter zur Tarifauswahl")
    ruhe(seite)
    lehne_einwilligung_ab(seite)
    if leiste_rate(_leiste(seite)) != rate:
        raise NichtPruefbar(f"Die Tarifauswahl zeigt nicht die Rate von {n} Monate Fix")
    return auswahl


def _waehle_kachel(seite: Page, kachel: Locator) -> str | None:
    """Klickt eine Tarifkachel (höchstens zweimal), bis die Preisleiste einen anderen
    Tarif nennt; gibt den Tarif der Leiste zurück."""
    vorher = leiste_tarif(_leiste(seite))
    if kachel.locator('input[name="tariff-plan"]').is_checked():
        return vorher
    for _ in range(2):
        kachel.locator("label.toggle-label").click(timeout=KLICKFRIST_MS)
        if warte_bis(seite, lambda: leiste_tarif(_leiste(seite)) not in (None, vorher)):
            break
    return leiste_tarif(_leiste(seite))


def waehle(seite: Page, gruppe: list[dict], oeffnen: Oeffnen) -> Schritte:
    """Der Weg: einmal zur Tarifauswahl, dann jede gewählte Kachel lesen."""
    auswahl = _zur_tarifauswahl(seite, gruppe[0], oeffnen)
    offen = nach_tarif(gruppe, norm)
    kacheln = seite.locator(_KACHEL)
    for stelle in range(min(kacheln.count(), HOECHSTE_TARIFKACHELN)):
        if not offen:
            return
        liste = offen.pop(norm(_waehle_kachel(seite, kacheln.nth(stelle)) or ""), [])
        if not liste:
            continue
        uebersicht = seite.locator("button.price-summary-overlay__modal-trigger")
        try:
            klicke(seite, uebersicht, "Preisübersicht anzeigen")
        except NichtPruefbar as fehler:
            for b in liste:
                yield b, fehler
            continue
        for b in liste:
            yield b, Vorab.mit("", auswahl)
        seite.keyboard.press("Escape")
        seite.wait_for_timeout(TAKT_MS * 2)
    yield from nicht_zur_wahl(offen)
