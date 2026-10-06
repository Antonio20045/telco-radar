"""Lokaler Server für die Tests des Beleg-Archivs: nur 127.0.0.1, kein Netz.

Eine Antwortfunktion bekommt Methode, Pfad, Köpfe und Körper und liefert eine
``Antwort``; der Server merkt jede Anfrage. Er beantwortet GET, PUT, POST und DELETE
und wartet beim Schließen nicht auf Antworten, die absichtlich trödeln.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass(frozen=True)
class Anfrage:
    methode: str
    pfad: str
    kopf: dict[str, str]
    koerper: bytes


@dataclass(frozen=True)
class Antwort:
    status: int = 200
    koerper: bytes = b""
    typ: str = "application/octet-stream"
    verzug: float = 0.0


@dataclass
class Belegserver:
    antworte: Callable[[Anfrage], Antwort]
    port: int = 0
    anfragen: list[Anfrage] = field(default_factory=list)

    def adresse(self, pfad: str = "") -> str:
        return f"http://127.0.0.1:{self.port}{pfad}"


class _Server(ThreadingHTTPServer):
    block_on_close = False
    daemon_threads = True


@contextmanager
def belegserver(antworte: Callable[[Anfrage], Antwort]) -> Iterator[Belegserver]:
    server = Belegserver(antworte)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            return

        def _beantworte(self) -> None:
            laenge = int(self.headers.get("Content-Length") or 0)
            koerper = self.rfile.read(laenge) if laenge else b""
            anfrage = Anfrage(self.command, self.path, dict(self.headers), koerper)
            server.anfragen.append(anfrage)
            antwort = server.antworte(anfrage)
            if antwort.verzug:
                time.sleep(antwort.verzug)
            try:
                self.send_response(antwort.status)
                self.send_header("Content-Type", antwort.typ)
                self.send_header("Content-Length", str(len(antwort.koerper)))
                self.end_headers()
                self.wfile.write(antwort.koerper)
            except (BrokenPipeError, ConnectionResetError):
                return

        do_GET = do_PUT = do_POST = do_DELETE = _beantworte

    httpd = _Server(("127.0.0.1", 0), Handler)
    server.port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, args=(0.02,), daemon=True).start()
    try:
        yield server
    finally:
        httpd.shutdown()
        httpd.server_close()
