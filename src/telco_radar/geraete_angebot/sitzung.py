"""Die Browser-Sitzung der Angebotszählung: Seite öffnen, klicken, Schnappschuss.

Dünne Hülle um eine Playwright-Seite (``page``), damit die Wege (``wege``) nur sagen,
WAS sie tun. Jeder Seitenaufruf geht durch das ``Tor`` (robots.txt, Abstand); jede
geladene Seite wird auf eine Schutzseite geprüft (``tor.schutzgrund``), dann
``Gesperrt``. Einwilligungsbanner werden abgelehnt („Alle ablehnen“, „Verweigern“,
„Nur erforderliche“), nie umgangen oder akzeptiert. Mit ``aufnahme`` legt die Sitzung
jeden gelesenen Zustand als ``<nr>-<name>.html.gz`` ab (Fixtures, Nachweis).
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path

from .tor import Gesperrt, Tor, schutzgrund

WARTE_LADEN_MS = 4000
WARTE_KLICK_MS = 2200
ABLEHNEN = r"^(alle ablehnen|alles ablehnen|ablehnen|verweigern|nur erforderliche)$"

_KLICK_JS = r"""([muster, wurzel]) => {
  const re = new RegExp(muster, 'i');
  const basis = wurzel ? document.querySelector(wurzel) : document;
  if (!basis) return null;
  const b = [...basis.querySelectorAll('button, a, label, [role=button], [role=radio]')]
    .find(x => re.test((x.innerText || '').trim()) && x.offsetParent !== null
               && !x.disabled);
  if (!b) return null;
  const t = (b.innerText || '').trim(); b.click(); return t;
}"""
_RADIO_JS = r"""([name, wert]) => {
  const re = new RegExp(name, 'i');
  const i = [...document.querySelectorAll('input[type=radio]')]
    .find(x => re.test(x.name || '') && x.value === wert);
  if (!i) return false;
  const f = i.id && document.querySelector(`label[for="${i.id}"]`);
  const l = f || i.closest('label');
  (l || i).click(); return true;
}"""
_SCROLL_JS = r"""(s) => {
  const it = [...document.querySelectorAll(s)];
  if (it.length) it[it.length - 1].scrollIntoView();
  window.scrollBy(0, 300);
}"""
_HAT_JS = r"""(muster) => {
  const re = new RegExp(muster, 'i');
  return [...document.querySelectorAll('button, a, [role=button]')]
    .some(x => re.test((x.innerText || '').trim()) && x.offsetParent !== null);
}"""
_TEXT_JS = "() => document.body ? document.body.innerText : ''"
_SCHLANK_JS = r"""() => {
  const k = document.documentElement.cloneNode(true);
  k.querySelectorAll('script,style,svg,noscript,link,meta,iframe,img,picture,source')
   .forEach(e => e.remove());
  return '<!doctype html>' + k.outerHTML;
}"""


class Sitzung:
    """Eine Seite des Browsers mit Tor und optionaler Aufnahme."""

    def __init__(self, page, tor: Tor, aufnahme: Path | None = None) -> None:
        """``page`` ist eine Playwright-Seite, ``tor`` das Tor des Anbieters."""
        self.page, self.tor, self.aufnahme = page, tor, aufnahme
        self.nummer = 0
        self.abgelehnt: set[str] = set()

    def oeffne(self, url: str) -> None:
        """Seite laden (durch das Tor), Schutzseite erkennen, Banner ablehnen."""
        self.tor.passiere(url)
        antwort = self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(WARTE_LADEN_MS)
        self.pruefe_schutz(antwort.status if antwort is not None else None)
        host = url.split("/")[2]
        if host not in self.abgelehnt:
            self.abgelehnt.add(host)
            self.lehne_ab()

    def lehne_ab(self) -> bool:
        """Einwilligung ablehnen; der Locator sucht auch im Shadow-DOM (o2)."""
        knopf = self.page.get_by_role("button", name=re.compile(ABLEHNEN, re.I))
        for i in range(knopf.count()):
            if knopf.nth(i).is_visible():
                knopf.nth(i).evaluate("e => e.click()")
                self.page.wait_for_timeout(800)
                return True
        if self.klicke_text(ABLEHNEN):
            self.page.wait_for_timeout(800)
            return True
        return False

    def pruefe_schutz(self, status: int | None = None) -> None:
        """``Gesperrt``, wenn die aktuelle Seite eine Schutzseite ist."""
        grund = schutzgrund(status, self.page.title(), self.text())
        if grund:
            raise Gesperrt(grund)

    def navigiere_per_klick(self, muster: str) -> bool:
        """Ein Klick, der eine neue Seite lädt („Zur Tarifauswahl“): erst durch das
        Tor (Abstand), dann klicken und warten."""
        self.tor.passiere(self.page.url)
        if not self.klicke_text(muster):
            return False
        self.page.wait_for_timeout(WARTE_LADEN_MS)
        self.pruefe_schutz()
        return True

    def klicke_text(self, muster: str, wurzel: str | None = None) -> str | None:
        """Klickt das erste sichtbare Bedienelement, dessen Text ``muster`` trifft."""
        return self.page.evaluate(_KLICK_JS, [muster, wurzel])

    def hat_text(self, muster: str) -> bool:
        """Gibt es ein sichtbares Bedienelement, dessen Text ``muster`` trifft?"""
        return bool(self.page.evaluate(_HAT_JS, muster))

    def klicke(self, selektor: str, warte_ms: int = WARTE_KLICK_MS) -> bool:
        """Klickt das erste Element zu ``selektor`` (per DOM-Klick, der auch unter
        einem Banner wirkt); ``False``, wenn es keins gibt."""
        ort = self.page.locator(selektor)
        if ort.count() == 0:
            return False
        ort.first.evaluate("e => e.click()")
        self.page.wait_for_timeout(warte_ms)
        return True

    def waehle_radio(
        self, name: str, wert: str, warte_ms: int = WARTE_KLICK_MS
    ) -> bool:
        """Klickt das Label der Option ``wert`` in der Radiogruppe, deren Name
        ``name`` (regulärer Ausdruck) trifft, wie ein Kunde es tut."""
        getroffen = self.page.evaluate(_RADIO_JS, [name, wert])
        if getroffen:
            self.page.wait_for_timeout(warte_ms)
        return bool(getroffen)

    def text(self) -> str:
        """Sichtbarer Text der Seite (``innerText``)."""
        return str(self.page.evaluate(_TEXT_JS) or "")

    def html(self, name: str) -> str:
        """Das DOM des aktuellen Zustands, ohne Skripte und Bilder; mit Aufnahme."""
        html = str(self.page.evaluate(_SCHLANK_JS))
        if self.aufnahme is not None:
            self.nummer += 1
            self.aufnahme.mkdir(parents=True, exist_ok=True)
            sauber = re.sub(r"[^a-z0-9_-]+", "-", name.lower())[:60]
            ziel = self.aufnahme / f"{self.nummer:03d}-{sauber}.html.gz"
            with gzip.open(ziel, "wt", encoding="utf-8") as datei:
                datei.write(f"<!-- {self.page.url} -->\n{html}")
        return html

    def scrolle_bis_stabil(self, zaehle_js: str, runden: int = 40) -> int:
        """Scrollt zur letzten Kachel, bis sich ihre Zahl zweimal nicht ändert."""
        alt, stabil, n = -1, 0, 0
        for _ in range(runden):
            self.page.evaluate(_SCROLL_JS, zaehle_js)
            self.page.mouse.wheel(0, 600)
            self.page.wait_for_timeout(1500)
            n = int(
                self.page.evaluate(
                    "(s) => document.querySelectorAll(s).length", zaehle_js
                )
            )
            stabil = stabil + 1 if n == alt else 0
            alt = n
            if stabil >= 2:
                break
        return n
