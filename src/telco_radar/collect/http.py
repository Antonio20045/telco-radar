"""Gemeinsamer HTTP-Abruf: ehrliche Kennung, keine Umgehung von Bot-Schutz.

Eine Schutzantwort (403, 406, 429, eine 503 mit Challenge) beendet den Abruf
nach GENAU EINER Anfrage: kein Wechsel von User-Agent oder Kopfzeilen, keine
Wiederholung. Bis zum 05.11.2026 wechselte `fetch` nach 403/406 auf eine
Chrome-Kennung mit Client-Hints (oder umgekehrt) und versuchte es erneut; das
war ein Umweg um eine Sperre (CLAUDE.md Regel 4).

Ausnahme 429: ein Header `Retry-After` von hoechstens 60 Sekunden wird EINMAL
abgewartet; alles andere bricht ab. Serverfehler (500, 502, 503 ohne Challenge)
sind keine Schutzantwort und werden mit kurzem Backoff wiederholt, mit
derselben Kennung.
"""

from __future__ import annotations

import hashlib
import logging
import random
import ssl
import threading
import time
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit

import httpx

from .schutz import RETRY_AFTER_MAX, SCHUTZ_STATUSES, ist_challenge, retry_after

log = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
BOT_UA = "TelcoRadar/1.0 (+https://github.com/Antonio20045/telco-radar)"

_CLIENT_HINTS = {
    "sec-ch-ua": '"Chromium";v="126", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


def _ca_bundle():
    try:
        import certifi

        return certifi.where()
    except ImportError:
        log.warning("certifi fehlt - benutze den Zertifikatsspeicher des Systems")
        return True


_ENDGUELTIGE_STATUSES = {404, 410}
_BACKOFF_WAITS = (4.0, 9.0)
Transport = httpx.BaseTransport
TRANSPORT: Transport | None = None
_WEG = {"content-encoding", "content-length", "transfer-encoding", "set-cookie"}


def _ist_ehrliche_kennung(ua: str) -> bool:
    """True, wenn `ua` sich als das Programm ausgibt statt als Browser.

    Jede `TelcoRadar/1.0`-Kennung zaehlt (`BOT_UA`, der Anbieter-Override mit
    anderer Kontaktadresse); nur ein Browser-UA bekommt Client-Hints."""
    return (ua or "").startswith("TelcoRadar/1.0")


class HostGate:
    """Begrenzt gleichzeitige Abrufe je Host und haelt einen Mindestabstand."""

    def __init__(self, max_parallel: int = 2, min_interval: float = 0.0):
        self.max_parallel = max(1, int(max_parallel))
        self.min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._gates: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}

    @staticmethod
    def host_of(url: str) -> str:
        try:
            return urlsplit(url).netloc.lower().removeprefix("www.")
        except ValueError:
            return url

    def _fuer(self, host: str):
        with self._lock:
            if host not in self._semaphores:
                self._semaphores[host] = threading.BoundedSemaphore(self.max_parallel)
                self._gates[host] = threading.Lock()
            return self._semaphores[host], self._gates[host]

    @contextmanager
    def slot(self, url: str):
        host = self.host_of(url)
        sem, gate = self._fuer(host)
        sem.acquire()
        try:
            if self.min_interval:
                with gate:
                    zuletzt = self._last.get(host)
                    jetzt = time.monotonic()
                    if zuletzt is not None:
                        rest = self.min_interval - (jetzt - zuletzt)
                        if rest > 0:
                            time.sleep(rest)
                            jetzt = time.monotonic()
                    self._last[host] = jetzt
            yield
        finally:
            sem.release()


_gate = HostGate(max_parallel=1_000_000, min_interval=0.0)


def configure_throttle(max_parallel: int, min_interval: float) -> HostGate:
    """Host-Drosselung fuer diesen Prozess setzen (aus settings.yaml)."""
    global _gate
    _gate = HostGate(max_parallel=max_parallel, min_interval=min_interval)
    log.info(
        "Host-Drosselung: max. %d gleichzeitig je Host, min. %.1fs Abstand",
        _gate.max_parallel,
        _gate.min_interval,
    )
    return _gate


def active_gate() -> HostGate:
    return _gate


_frist = threading.local()


@contextmanager
def deadline(sekunden: float | None):
    """Frist fuer alle fetch()-Aufrufe dieses Threads."""
    vorher = getattr(_frist, "ende", None)
    _frist.ende = (time.monotonic() + sekunden) if sekunden else None
    try:
        yield
    finally:
        _frist.ende = vorher


def _frist_abgelaufen() -> bool:
    ende = getattr(_frist, "ende", None)
    return ende is not None and time.monotonic() >= ende


def _frist_reicht_fuer(sekunden: float) -> bool:
    ende = getattr(_frist, "ende", None)
    return ende is None or time.monotonic() + sekunden < ende


def _hole(url: str, **art: Any) -> httpx.Response:
    """GET ins echte Netz, über die Naht ``TRANSPORT``, wenn sie gesetzt ist."""
    if TRANSPORT is None:
        return httpx.get(url, verify=_ca_bundle(), **art)
    with httpx.Client(transport=TRANSPORT) as client:
        return client.get(url, **art)


_MAX_WEITERLEITUNGEN = 3


def _hole_gepruefte_weiterleitung(
    url: str, vor_weiterleitung: Any, **art: Any
) -> httpx.Response:
    """GET, der Weiterleitungen nicht blind folgt.

    Vor JEDEM Sprung auf eine andere Adresse ruft er `vor_weiterleitung(ziel)`;
    wirft die Pruefung (robots.txt, Abstand), endet der Abruf dort und der
    Sprung wird nicht ausgefuehrt. Mehr als `_MAX_WEITERLEITUNGEN` Spruenge
    sind ein Fehler. Der Aufruf laeuft schon im Slot von `fetch`.
    """
    antwort = _hole(url, follow_redirects=False, **art)
    for _ in range(_MAX_WEITERLEITUNGEN):
        ziel = antwort.headers.get("location")
        if not antwort.is_redirect or not ziel:
            return antwort
        adresse = str(antwort.url.join(ziel))
        vor_weiterleitung(adresse)
        antwort = _hole(adresse, follow_redirects=False, **art)
    if antwort.is_redirect:
        raise httpx.TooManyRedirects(
            "zu viele Weiterleitungen", request=antwort.request
        )
    return antwort


Zeitueberschreitung = httpx.TimeoutException
HttpFehler = httpx.HTTPError
StatusFehler = httpx.HTTPStatusError


Antwort = httpx.Response


class SchutzAntwort(httpx.HTTPStatusError):
    """Schutzantwort (403/406/429, 503 mit Challenge); ein StatusFehler."""


def schutz(resp: httpx.Response, text: str) -> SchutzAntwort:
    """Die Schutzantwort-Ausnahme zu `resp`."""
    return SchutzAntwort(text, request=resp.request, response=resp)


def get(url: str, **art: Any) -> httpx.Response:
    """Ein GET ohne Kennungswechsel und Backoff, über Drossel und Naht."""
    with _gate.slot(url):
        return _hole(url, **art)


def _tls() -> ssl.SSLContext | bool:
    """TLS-Prüfung gegen das Bündel von ``_ca_bundle`` als Kontext."""
    buendel = _ca_bundle()
    return ssl.create_default_context(cafile=buendel) if buendel is not True else True


def sende(
    methode: str, url: str, inhalt: bytes, kopf: dict[str, str], frist: float
) -> httpx.Response:
    """Ein Aufruf mit Körper an einen eigenen Dienst (Ablage, Zeitstempel), über
    Drossel und Naht; ohne Kennungswechsel, Backoff und Umleitung."""
    with _gate.slot(url):
        if TRANSPORT is None:
            return httpx.request(
                methode,
                url,
                content=inhalt,
                headers=kopf,
                timeout=frist,
                verify=_tls(),
            )
        with httpx.Client(transport=TRANSPORT) as client:
            return client.request(
                methode, url, content=inhalt, headers=kopf, timeout=frist
            )


def fetch(
    url: str,
    http_cfg: dict,
    timeout_override: float | None = None,
    extra_headers: dict | None = None,
    schnell: bool = False,
    vor_weiterleitung: Any = None,
) -> httpx.Response:
    """GET mit EINER Kennung; Schutzantwort endet nach einem Abruf.

    404/410 sind endgueltig. 403, 406, 503 mit Challenge und jede Antwort mit
    `cf-mitigated`: `SchutzAntwort`, eine Anfrage, keine andere Kennung, keine
    anderen Kopfzeilen. 429: keine Wiederholung, ausser `Retry-After` nennt
    hoechstens `RETRY_AFTER_MAX` Sekunden (einmal warten, einmal wiederholen).
    500/502/503 ohne Challenge und Netzfehler: Backoff `_BACKOFF_WAITS`.

    `schnell=True`: ein Versuch, kein Backoff, kein `Retry-After`-Warten
    (Breitensuche, Adapter mit Abbruch bei Schutzantwort).
    `vor_weiterleitung(ziel)` legt jede Weiterleitung vorab zur Pruefung vor
    (siehe `_hole_gepruefte_weiterleitung`).
    """
    timeout = float(timeout_override or http_cfg.get("timeout_seconds", 20))
    ua = http_cfg.get("user_agent", BOT_UA)
    site_root = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/"
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/rss+xml;q=0.9,application/atom+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Referer": site_root,
    }
    if not _ist_ehrliche_kennung(ua):
        headers.update(_CLIENT_HINTS)
    if extra_headers:
        headers.update(extra_headers)

    backoff = [] if schnell else list(_BACKOFF_WAITS)
    retry_after_genutzt = False
    last_exc: Exception | None = None
    wait = 0.0
    while True:
        if wait:
            if _frist_abgelaufen():
                break
            time.sleep(wait)
        if _frist_abgelaufen():
            break
        try:
            with _gate.slot(url):
                if vor_weiterleitung is None:
                    resp = _hole(
                        url, timeout=timeout, headers=headers, follow_redirects=True
                    )
                else:
                    resp = _hole_gepruefte_weiterleitung(
                        url, vor_weiterleitung, timeout=timeout, headers=headers
                    )
        except httpx.HTTPError as exc:
            last_exc = exc
            if not backoff:
                break
            wait = backoff.pop(0) + random.uniform(0, 1.0)
            continue

        status = resp.status_code
        if status in _ENDGUELTIGE_STATUSES:
            raise httpx.HTTPStatusError(
                f"status {status}", request=resp.request, response=resp
            )
        if status in SCHUTZ_STATUSES or (status >= 400 and ist_challenge(resp)):
            raise schutz(resp, f"Schutzantwort {status}, kein zweiter Versuch")
        if status == 429:
            pause = retry_after(resp)
            if (
                schnell
                or retry_after_genutzt
                or pause is None
                or pause > RETRY_AFTER_MAX
                or not _frist_reicht_fuer(pause)
            ):
                raise schutz(resp, "Schutzantwort 429, keine Wiederholung")
            retry_after_genutzt = True
            wait = pause
            continue
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if not backoff:
                break
            wait = backoff.pop(0) + random.uniform(0, 1.0)
            continue
        return resp
    raise last_exc if last_exc else RuntimeError(f"fetch failed: {url}")


def anfrage_schluessel(anfrage: httpx.Request) -> tuple[str, ...]:
    """Methode, Adresse, Kennung und Hash des Inhalts: so findet die Wiedergabe."""
    inhalt = hashlib.sha256(anfrage.read()).hexdigest()
    kennung = anfrage.headers.get("user-agent", "")
    return (anfrage.method, str(anfrage.url), kennung, inhalt)


class Aufnahme(httpx.BaseTransport):
    """Reicht jede Anfrage ins echte Netz und schreibt die Antwort auf ``band``."""

    def __init__(self, band, innen: Transport | None = None) -> None:
        self.band = band
        self.innen = innen or httpx.HTTPTransport(verify=_ca_bundle())

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Antwort samt Status und Köpfen, ohne Cookies und Transportköpfe."""
        schluessel = anfrage_schluessel(request)
        try:
            antwort = self.innen.handle_request(request)
            inhalt = antwort.read()
        except httpx.HTTPError as exc:
            self.band.merke(schluessel, {"fehler": type(exc).__name__})
            raise
        kopf = {k: v for k, v in antwort.headers.items() if k.lower() not in _WEG}
        eintrag = {"status": antwort.status_code, "kopf": kopf, "inhalt": inhalt}
        self.band.merke(schluessel, eintrag)
        return httpx.Response(antwort.status_code, headers=kopf, content=inhalt)


class Wiedergabe(httpx.BaseTransport):
    """Antwortet aus ``band``; mit ``guthaben_leer`` jeder LLM-Endpunkt mit 402."""

    def __init__(self, band, guthaben_leer: bool = False) -> None:
        self.band = band
        self.guthaben_leer = guthaben_leer

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Die aufgenommene Antwort, ihr Fehler oder ein Verbindungsfehler."""
        llm = request.url.path.endswith(("/completions", "/messages"))
        if self.guthaben_leer and request.method == "POST" and llm:
            return httpx.Response(402, json={"error": "Insufficient Balance"})
        meldung = f"HTTP-Antwort für {request.method} {request.url}"
        eintrag = self.band.naechste(anfrage_schluessel(request), meldung)
        if eintrag is None:
            raise httpx.ConnectError(f"{meldung} fehlt", request=request)
        if "fehler" in eintrag:
            art = getattr(httpx, eintrag["fehler"], httpx.TransportError)
            raise art("aufgenommen", request=request)
        return httpx.Response(
            eintrag["status"], headers=eintrag["kopf"], content=eintrag["inhalt"]
        )


KEIN_BILD = httpx.MockTransport(lambda _: httpx.Response(404))
