"""Shared HTTP fetch with user-agent fallback and rate-limit backoff.

Some newsrooms block browser UAs from datacenter IPs, others block anything
that does not look like a browser -> we try the configured UA first and retry
once with the alternate style on 403/406.

News aggregators (notably Google News RSS) throttle bursts of requests from
shared cloud IPs with 429/503. We retry those a couple of times with a short
backoff, which clears the transient throttling that happens when many feeds
fire at once. A UA swap cannot fix a 5xx, so we do not waste a second UA on it.
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


_UA_SWAP_STATUSES = {403, 406}
_ENDGUELTIGE_STATUSES = {404, 410}
_BACKOFF_STATUSES = {429, 500, 502, 503}
_BACKOFF_WAITS = (4.0, 9.0)
Transport = httpx.BaseTransport
TRANSPORT: Transport | None = None
_WEG = {"content-encoding", "content-length", "transfer-encoding", "set-cookie"}


def _ist_ehrliche_kennung(ua: str) -> bool:
    """True, wenn `ua` sich selbst als das Programm ausgibt statt als Browser.

    Bis zum 05.09.2026 gab es dafuer genau EINEN bekannten Wert (`BOT_UA`),
    und die UA-Logik unten verglich stumpf auf Gleichheit damit. Der
    per-Anbieter-UA-Override (BRIEF_SATURN_ADAPTER_R2) fuehrt eine ZWEITE
    ehrliche Kennung ein - dieselbe Projekt-Identitaet
    ("TelcoRadar/1.0"), aber mit einer anderen Kontaktadresse
    (`+https://telco-radar.onrender.com/ueber` statt des Repo-Links). Ein
    reiner Gleichheitsvergleich haette diese zweite Kennung wie eine
    unbekannte, browserfremde UND unehrliche Zeichenkette behandelt: sie
    haette Chrome-Client-Hints bekommen (Widerspruch in sich, siehe unten)
    und als Fallback die ALTE `BOT_UA` gezogen statt des Browser-UA - beides
    das Gegenteil dessen, was ein ehrlicher Absender verspricht. Der
    Praefix-Vergleich erkennt JEDE TelcoRadar-Kennung als ehrlich, ohne die
    bestehenden zwei Werte (`BOT_UA`, `BROWSER_UA`) oder ihre Rollen
    zueinander zu aendern.
    """
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


def _hole(url: str, **art: Any) -> httpx.Response:
    """GET ins echte Netz, über die Naht ``TRANSPORT``, wenn sie gesetzt ist."""
    if TRANSPORT is None:
        return httpx.get(url, verify=_ca_bundle(), **art)
    with httpx.Client(transport=TRANSPORT) as client:
        return client.get(url, **art)


Zeitueberschreitung = httpx.TimeoutException
HttpFehler = httpx.HTTPError
StatusFehler = httpx.HTTPStatusError
Antwort = httpx.Response


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
) -> httpx.Response:
    """GET with UA fallback + short backoff on rate limits; 404 und 410 sind endgültig.

    `schnell=True` schaltet beides ab: ein User-Agent, ein Versuch, kein
    Backoff. Gedacht fuer die BREITENSUCHE (scripts/finde_quellen.py), wo
    neun von zehn geprobten Adressen erwartungsgemaess 404 sind. Dort ist die
    Ausdauer oben nicht Robustheit, sondern der Engpass: eine tote Adresse
    kostet sonst zwei User-Agents mal drei Versuche plus 4 s und 9 s Backoff,
    also ueber eine Minute - mal sechs Adressen je Firma mal hunderte Firmen.
    Fuer den LAUF selbst bleibt die Ausdauer richtig und Standard: dort ist
    jede Quelle ausgewaehlt, und ein verlorener Abruf kostet eine Woche.
    """
    timeout = float(timeout_override or http_cfg.get("timeout_seconds", 20))
    primary = http_cfg.get("user_agent", BROWSER_UA)
    fallback = BROWSER_UA if _ist_ehrliche_kennung(primary) else BOT_UA
    uas = (primary,) if schnell else (primary, fallback)
    wartezeiten = (0.0,) if schnell else (0.0, *_BACKOFF_WAITS)

    site_root = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/"

    last_exc: Exception | None = None
    endgueltig: httpx.HTTPStatusError | None = None
    for ua in uas:
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
        for wait in wartezeiten:
            if wait:
                if _frist_abgelaufen():
                    break
                time.sleep(wait + random.uniform(0, 1.0))
            if _frist_abgelaufen():
                break
            try:
                with _gate.slot(url):
                    resp = _hole(
                        url, timeout=timeout, headers=headers, follow_redirects=True
                    )
                if resp.status_code in _ENDGUELTIGE_STATUSES:
                    endgueltig = httpx.HTTPStatusError(
                        f"status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                    break
                if resp.status_code in _UA_SWAP_STATUSES:
                    last_exc = httpx.HTTPStatusError(
                        f"{resp.status_code} with UA '{ua[:24]}...'",
                        request=resp.request,
                        response=resp,
                    )
                    break
                if resp.status_code in _BACKOFF_STATUSES:
                    last_exc = httpx.HTTPStatusError(
                        f"status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as exc:
                last_exc = exc
                continue
        if endgueltig is not None:
            raise endgueltig
        if (
            isinstance(last_exc, httpx.HTTPStatusError)
            and last_exc.response is not None
            and last_exc.response.status_code in _BACKOFF_STATUSES
        ):
            break
        if _frist_abgelaufen():
            break
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
