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

import logging
import random
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BOT_UA = "TelcoRadar/1.0 (+https://github.com/Antonio20045/telco-radar)"

_UA_SWAP_STATUSES = {403, 406}            # try the other UA
_BACKOFF_STATUSES = {429, 500, 502, 503}  # transient -> retry same UA, then give up
_BACKOFF_WAITS = (4.0, 9.0)               # waits used *between* retries


# --------------------------------------------------------------------------- #
# Host-Drosselung
#
# Die Sammelphase ist fast reine Wartezeit auf fremde Server und skaliert
# deshalb mit der Parallelitaet - 130 Quellen bei 8 Workern brauchten 325 s,
# 1000 Quellen waeren bei gleicher Einstellung 42 min und damit allein schon
# ueber dem Job-Timeout. Der Ausweg ist aber NICHT einfach ein groesserer
# Worker-Pool: bei 1000 Quellen liegen zwangslaeufig mehrere Quellen auf
# derselben Domain (blog.google hat heute schon drei), und viele gleichzeitige
# Verbindungen zum selben Host provozieren 429/403. Eine gedrosselte Quelle
# kostet dann drei Versuche mit 4 s und 9 s Backoff - die Parallelitaet macht
# den Lauf langsamer, nicht schneller.
#
# Deshalb: global viele Verbindungen, je Host hoechstens `max_parallel`
# gleichzeitig und dazwischen ein Mindestabstand. Das Gate sitzt bewusst hier
# in fetch() und nicht in collect_all(), damit auch die Wiederholungen der
# Collectors (rss.py holt bei kaputtem XML bis zu drei Mal) und die
# Folgeabrufe der Newsroom-Parser mitgezaehlt werden.
# --------------------------------------------------------------------------- #

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
                # Der Abstand gilt zwischen zwei STARTS zum selben Host. Die
                # Wartezeit laeuft unter dem Host-Lock, damit sich zwei Threads
                # nicht denselben Zeitpunkt teilen und doch gleichzeitig
                # losziehen.
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


# Ein Prozess, ein Gate. Standard ist bewusst wirkungslos (unbegrenzt), damit
# Tests und Einzelabrufe ohne Konfiguration genau so laufen wie bisher; die
# Pipeline setzt es aus settings.yaml.
_gate = HostGate(max_parallel=1_000_000, min_interval=0.0)


def configure_throttle(max_parallel: int, min_interval: float) -> HostGate:
    """Host-Drosselung fuer diesen Prozess setzen (aus settings.yaml)."""
    global _gate
    _gate = HostGate(max_parallel=max_parallel, min_interval=min_interval)
    log.info("Host-Drosselung: max. %d gleichzeitig je Host, min. %.1fs Abstand",
             _gate.max_parallel, _gate.min_interval)
    return _gate


def active_gate() -> HostGate:
    return _gate


def fetch(url: str, http_cfg: dict,
          timeout_override: float | None = None,
          extra_headers: dict | None = None,
          schnell: bool = False) -> httpx.Response:
    """GET with UA fallback + short backoff on rate limits.

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
    fallback = BOT_UA if primary != BOT_UA else BROWSER_UA
    uas = (primary,) if schnell else (primary, fallback)
    wartezeiten = (0.0,) if schnell else (0.0, *_BACKOFF_WAITS)

    # A same-origin Referer mimics a normal in-site navigation. Most sources
    # do not care, but some AEM/CMS "public" backend servlets (e.g. stc's
    # bin/public/assets) reject requests with no Referer at all as a light
    # CSRF/hotlink guard - sending one costs nothing and fixes those.
    site_root = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/"

    last_exc: Exception | None = None
    for ua in uas:
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml,*/*",
            "Accept-Language": "en;q=0.9,de;q=0.8",
            "Referer": site_root,
        }
        if extra_headers:
            headers.update(extra_headers)
        # attempt 0 immediate, then one retry per backoff wait
        for wait in wartezeiten:
            if wait:
                time.sleep(wait + random.uniform(0, 1.0))
            try:
                with _gate.slot(url):
                    resp = httpx.get(url, timeout=timeout, headers=headers,
                                     follow_redirects=True)
                if resp.status_code in _UA_SWAP_STATUSES:
                    last_exc = httpx.HTTPStatusError(
                        f"{resp.status_code} with UA '{ua[:24]}...'",
                        request=resp.request, response=resp)
                    break  # try the other UA (no backoff)
                if resp.status_code in _BACKOFF_STATUSES:
                    last_exc = httpx.HTTPStatusError(
                        f"status {resp.status_code}",
                        request=resp.request, response=resp)
                    continue  # transient -> back off and retry same UA
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as exc:
                last_exc = exc
                continue
        # if the last failure was a transient 5xx/429, a UA swap won't help
        if isinstance(last_exc, httpx.HTTPStatusError) and \
                last_exc.response is not None and \
                last_exc.response.status_code in _BACKOFF_STATUSES:
            break
    raise last_exc if last_exc else RuntimeError(f"fetch failed: {url}")
