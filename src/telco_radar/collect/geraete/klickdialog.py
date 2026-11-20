"""Dialog nach einem Klick: erkennen, schließen oder mit Grund melden.

Telekom, 20.11.2026: Der Knopf „Einmalpreis“ öffnet den Dialog „Einmalzahlung“
(``div[role=dialog].ODSDialog`` in einem Floating-UI-Portal, dazu
``div.ODSDialog-Overlay`` über der ganzen Seite). Das Overlay fing jeden weiteren
Klick ab; jeder Knopf danach lief 15 s in die Frist, 622 von 1206 Kombinationen hießen
„nicht klickbar“. ``blockierender_dialog`` erkennt nach einem Klick einen sichtbaren
Dialog (``DIALOG_SELEKTOR``), der den geklickten Knopf verdeckt: an der Mitte des Knopfs
liegt ein fremdes Element. Ein Dialog, der den Knopf frei lässt, stört nicht und bleibt.
``schliesse`` klickt den Schließen-Knopf in diesem Dialog (``SCHLIESSEN_SELEKTOR``
unter ``MARKE``, nie einen anderen der Seite), sonst
drückt sie Escape, und prüft danach erneut. Geht er nicht zu, ist das ein benannter
Grund („Dialog „…“ nicht zu schließen“), keine Kette von Zeitüberschreitungen.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

log = logging.getLogger(__name__)

DIALOG_SELEKTOR = (
    '[aria-modal="true"], dialog[open], [role="dialog"], [role="alertdialog"]'
)
SCHLIESSEN_SELEKTOR = (
    'button[aria-label="Close dialog"], button.ODSDialog-CloseButton, '
    'button[aria-label*="schließen" i], button[aria-label*="close" i]'
)
MARKE = "data-klick-dialog"
"""Markiert den verdeckenden Dialog, damit nur sein eigener Schließen-Knopf zählt."""
TITEL_LAENGE = 60
WARTEN_MS = 500
GRUND_DIALOG = "Dialog"
GRUND_NICHT_ZU = "nicht zu schließen"

_DIALOG_JS = """(knopf, [selektor, marke]) => {
  const sichtbar = (e) => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'
      && s.display !== 'none';
  };
  const dialoge = [...document.querySelectorAll(selektor)].filter(sichtbar);
  if (!dialoge.length) return null;
  const r = knopf.getBoundingClientRect();
  const oben = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  if (oben === null || oben === knopf || knopf.contains(oben)) return null;
  const d = dialoge.find((e) => e.contains(oben)) || dialoge[dialoge.length - 1];
  document.querySelectorAll('[' + marke + ']').forEach((e) => e.removeAttribute(marke));
  d.setAttribute(marke, '');
  const kopf = document.getElementById(d.getAttribute('aria-labelledby') || '')
    || d.querySelector('h1, h2, h3');
  const titel = (d.getAttribute('aria-label') || (kopf && kopf.innerText)
    || d.innerText || '').replace(/\\s+/g, ' ').trim();
  return titel || '(ohne Titel)';
}"""


def blockierender_dialog(knopf: Locator, frist_ms: int) -> str | None:
    """Der Titel des sichtbaren Dialogs, der ``knopf`` verdeckt; sonst ``None``.

    Ist der Knopf nach dem Klick weg (neu gezeichnet, Navigation), gilt: kein Dialog.
    """
    try:
        titel = knopf.evaluate(_DIALOG_JS, [DIALOG_SELEKTOR, MARKE], timeout=frist_ms)
    except PlaywrightFehler:
        return None
    return None if titel is None else str(titel)[:TITEL_LAENGE]


def frei_vor_klick(seite: Page, knopf: Locator, frist_ms: int) -> str | None:
    """Vor dem Klick: ein verdeckender Dialog wird geschlossen; ``None``, wenn der
    Knopf danach frei ist, sonst der Grund (statt einer Zeitüberschreitung)."""
    titel = blockierender_dialog(knopf, frist_ms)
    if titel is None:
        return None
    grund = schliesse(seite, knopf, titel, frist_ms)
    return None if grund is None else f"verdeckt: {grund}"


def nach_klick(
    seite: Page, knopf: Locator, frist_ms: int, dimension: str
) -> str | None:
    """Nach dem Klick: ``None`` ohne verdeckenden Dialog; sonst der Grund der
    Kombination, denn der Klick hat einen Dialog geöffnet statt nur zu wählen."""
    titel = blockierender_dialog(knopf, frist_ms)
    if titel is None:
        return None
    grund = schliesse(seite, knopf, titel, frist_ms)
    return grund or f"{GRUND_DIALOG} „{titel}“ nach Klick auf {dimension} geschlossen"


def schliesse(seite: Page, knopf: Locator, titel: str, frist_ms: int) -> str | None:
    """Schließt den Dialog ``titel``; ``None``, wenn der Knopf danach frei ist, sonst
    der Grund."""
    log.info("Klick-Crawler: Dialog „%s“ nach Klick, wird geschlossen", titel)
    dialog = seite.locator(f"[{MARKE}]")
    schliessen = dialog.locator(SCHLIESSEN_SELEKTOR).filter(visible=True)
    try:
        if schliessen.count() > 0:
            schliessen.first.click(timeout=frist_ms)
        else:
            seite.keyboard.press("Escape")
        seite.wait_for_timeout(WARTEN_MS)
    except PlaywrightFehler as fehler:
        log.warning("Klick-Crawler: Dialog „%s“: %s", titel, fehler)
    if blockierender_dialog(knopf, frist_ms) is None:
        return None
    return f"{GRUND_DIALOG} „{titel}“ {GRUND_NICHT_ZU}"
