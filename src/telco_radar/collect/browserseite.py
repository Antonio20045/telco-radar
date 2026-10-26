"""Eine Seite im echten Browser abrufen, mit ehrlicher Kennung und ohne Tarnung.

CLAUDE.md, Harte Regel 4 (Antonio, 08.10.2026): Eine JavaScript-Prüfung (HTTP 202) darf
der echte Browser mit ehrlicher Kennung durchlaufen, ohne Tarnung, Proxy oder
Captcha-Löser. Die Telekom beantwortet einen Abruf aus GitHub Actions mit dieser Prüfung
(`config/tarif_quellen.yaml`, Eintrag Telekom); ohne Browser blieb ihr Tarifstand seit
dem 15.09.2026 stehen. Ein Captcha oder 403 bleibt ein Fehler.
"""

from __future__ import annotations

from dataclasses import dataclass

NACHLADEZEIT_MS = 3000
_SPERRSTATUS = (401, 403, 429)


class BrowserSeiteGesperrt(RuntimeError):
    """Der Anbieter hat den Abruf abgelehnt; nicht umgehen (Harte Regel 4)."""


@dataclass
class BrowserAntwort:
    """Status und gerenderter DOM, mit den Feldern, die der Sammler protokolliert."""

    status_code: int
    text: str

    @property
    def content(self) -> bytes:
        """Der DOM als Bytes, wie `httpx.Response.content`."""
        return self.text.encode("utf-8")


def hole_im_browser(
    url: str, http_cfg: dict, timeout_s: float = 60.0
) -> BrowserAntwort:
    """Die Seite nach Abschluss ihrer Skripte, mit der Kennung aus `http_cfg` (wie
    `http.fetch`); wirft bei Sperre und Fehlerstatus."""
    from playwright.sync_api import sync_playwright

    user_agent = str(http_cfg.get("user_agent") or "")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            seite = browser.new_page(user_agent=user_agent)
            antwort = seite.goto(
                url, wait_until="networkidle", timeout=int(timeout_s * 1000)
            )
            status = antwort.status if antwort is not None else 0
            if status in _SPERRSTATUS or "captcha" in seite.url.lower():
                raise BrowserSeiteGesperrt(f"{url}: HTTP {status}, {seite.url}")
            if status >= 400:
                raise RuntimeError(f"{url}: HTTP {status}")
            seite.wait_for_timeout(NACHLADEZEIT_MS)
            return BrowserAntwort(status, seite.content())
        finally:
            browser.close()
