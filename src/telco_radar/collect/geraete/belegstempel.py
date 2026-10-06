"""Zeitstempel für ein Manifest: RFC 3161 bei freetsa.org und OpenTimestamps.

Datenkonzept Geräteradar, Abschnitt 10: das Manifest eines Tages wird gestempelt.
``stemple_rfc3161`` baut die Anfrage mit ``openssl ts -query`` über den Digest, schickt
sie an ``FREETSA`` und nimmt die Antwort nur, wenn ``openssl ts -reply`` sie als
„Granted“ mit demselben Digest liest. ``stemple_ots`` schickt den Digest an jeden
Calendar-Server in ``OTS_KALENDER`` (HTTP-POST an ``/digest``, wie der
OpenTimestamps-Client) und nimmt jede Antwort, die eine ausstehende Bestätigung trägt.
Jeder Ausfall (openssl fehlt oder scheitert, Server antwortet nicht in der Frist oder
nicht mit 200, Antwort unlesbar) ist ein ``Stempel`` im Zustand ``ausgefallen`` mit
Grund, nie eine Ausnahme: der Lauf geht weiter. Die Antworten stehen als Base64 im
Stempel. HTTP geht über ``collect.http.sende``.
"""

from __future__ import annotations

import base64
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .. import http

log = logging.getLogger(__name__)

FREETSA = "https://freetsa.org/tsr"
OTS_KALENDER = (
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://a.pool.eternitywall.com",
    "https://ots.btc.catallaxy.com",
)
RFC3161 = "rfc3161"
OPENTIMESTAMPS = "opentimestamps"
GESTEMPELT = "gestempelt"
AUSGEFALLEN = "ausgefallen"
STEMPEL_FRIST_S = 20.0
OPENSSL_FRIST_S = 20.0
OTS_HOECHSTENS = 10000
OTS_AUSSTEHEND = bytes.fromhex("83dfe30d2ef90c8e")
TSA_ANFRAGE = "application/timestamp-query"
OTS_ANNAHME = "application/vnd.opentimestamps.v1"
OTS_INHALT = "application/x-www-form-urlencoded"
GEWAEHRT = "Status: Granted."
DIGEST_LAENGE = 32
_ABSCHNITT = re.compile(r"^Message data:\n((?:[ \t].*\n?)+)", re.M)
_ASCII_SPALTE = re.compile(r"\s{3,}")


@dataclass(frozen=True)
class Stempel:
    """Ein Zeitstempel oder sein Ausfall: Verfahren, Dienst, Zustand, Grund, Token."""

    verfahren: str
    dienst: str
    zustand: str
    grund: str | None = None
    token: str | None = None


def stemple(
    digest: str,
    *,
    tsa: str = FREETSA,
    kalender: tuple[str, ...] = OTS_KALENDER,
    openssl: str = "openssl",
    frist: float = STEMPEL_FRIST_S,
) -> tuple[Stempel, ...]:
    """Beide Verfahren für einen SHA-256-Digest in Hex; wirft nie."""
    return (
        stemple_rfc3161(digest, tsa=tsa, openssl=openssl, frist=frist),
        *stemple_ots(digest, kalender=kalender, frist=frist),
    )


def stemple_rfc3161(
    digest: str, *, tsa: str = FREETSA, openssl: str = "openssl", frist: float
) -> Stempel:
    """RFC-3161-Stempel über ``openssl ts`` und den Dienst ``tsa``; wirft nie."""
    if shutil.which(openssl) is None:
        return _aus(RFC3161, tsa, f"openssl fehlt ({openssl})")
    anfrage, grund = _openssl(
        openssl, ["-query", "-digest", digest, "-sha256", "-cert"]
    )
    if grund is not None:
        return _aus(RFC3161, tsa, f"Anfrage nicht gebaut: {grund}")
    antwort, grund = _post(tsa, anfrage, {"Content-Type": TSA_ANFRAGE}, frist)
    if grund is not None:
        return _aus(RFC3161, tsa, grund)
    grund = _pruefe_tsa(openssl, antwort, digest)
    if grund is not None:
        return _aus(RFC3161, tsa, grund)
    return Stempel(RFC3161, tsa, GESTEMPELT, token=_b64(antwort))


def stemple_ots(
    digest: str, *, kalender: tuple[str, ...] = OTS_KALENDER, frist: float
) -> tuple[Stempel, ...]:
    """Je Calendar-Server ein OpenTimestamps-Stempel oder sein Ausfall; wirft nie."""
    try:
        roh = bytes.fromhex(digest)
    except ValueError:
        roh = b""
    if len(roh) != DIGEST_LAENGE:
        falsch = "Digest ist kein SHA-256 in Hex"
        return tuple(_aus(OPENTIMESTAMPS, k, falsch) for k in kalender)
    kopf = {"Accept": OTS_ANNAHME, "Content-Type": OTS_INHALT}
    stempel = []
    for adresse in kalender:
        antwort, grund = _post(f"{adresse.rstrip('/')}/digest", roh, kopf, frist)
        if grund is None and len(antwort) > OTS_HOECHSTENS:
            grund = f"Antwort zu lang ({len(antwort)} Bytes)"
        if grund is None and OTS_AUSSTEHEND not in antwort:
            grund = "Antwort unlesbar: keine ausstehende Bestätigung"
        if grund is not None:
            stempel.append(_aus(OPENTIMESTAMPS, adresse, grund))
        else:
            stempel.append(
                Stempel(OPENTIMESTAMPS, adresse, GESTEMPELT, token=_b64(antwort))
            )
    return tuple(stempel)


def _post(
    url: str, inhalt: bytes, kopf: dict[str, str], frist: float
) -> tuple[bytes, str | None]:
    try:
        antwort = http.sende("POST", url, inhalt, kopf, frist)
    except http.Zeitueberschreitung:
        log.warning("Stempel: %s antwortet nicht in %s s", url, frist)
        return b"", f"keine Antwort in {frist:g} s"
    except http.HttpFehler as fehler:
        log.warning("Stempel: %s nicht erreichbar: %s", url, type(fehler).__name__)
        return b"", f"nicht erreichbar ({type(fehler).__name__})"
    if antwort.status_code != 200:
        log.warning("Stempel: %s antwortet HTTP %s", url, antwort.status_code)
        return b"", f"HTTP {antwort.status_code}"
    return antwort.content, None


def _pruefe_tsa(openssl: str, antwort: bytes, digest: str) -> str | None:
    with tempfile.TemporaryDirectory() as ordner:
        datei = Path(ordner) / "antwort.tsr"
        datei.write_bytes(antwort)
        text, grund = _openssl(openssl, ["-reply", "-in", str(datei), "-text"])
    if grund is not None:
        return f"Antwort unlesbar: {grund}"
    ausgabe = text.decode("utf-8", "replace")
    if GEWAEHRT not in ausgabe:
        return "Antwort unlesbar: Stempel nicht gewährt"
    if _digest_aus(ausgabe) != digest.lower():
        return "Antwort stempelt einen anderen Digest"
    return None


def _digest_aus(ausgabe: str) -> str | None:
    abschnitt = _ABSCHNITT.search(ausgabe)
    if abschnitt is None:
        return None
    hexteile = []
    for zeile in abschnitt[1].splitlines():
        _, trenner, rest = zeile.partition(" - ")
        if trenner:
            hexteile.append(_ASCII_SPALTE.split(rest.strip(), maxsplit=1)[0])
    try:
        return bytes.fromhex(" ".join(hexteile).replace("-", " ")).hex()
    except ValueError:
        return None


def _openssl(openssl: str, argumente: list[str]) -> tuple[bytes, str | None]:
    befehl = [openssl, "ts", *argumente]
    try:
        lauf = subprocess.run(
            befehl, capture_output=True, timeout=OPENSSL_FRIST_S, check=False
        )
    except subprocess.TimeoutExpired:
        return b"", f"openssl antwortet nicht in {OPENSSL_FRIST_S:g} s"
    except OSError as fehler:
        return b"", f"openssl startet nicht ({type(fehler).__name__})"
    if lauf.returncode != 0:
        meldung = lauf.stderr.decode("utf-8", "replace").strip().splitlines()
        letzte = meldung[-1] if meldung else f"Exit {lauf.returncode}"
        return b"", f"openssl scheitert: {letzte}"
    return lauf.stdout, None


def _aus(verfahren: str, dienst: str, grund: str) -> Stempel:
    log.warning("Stempel %s bei %s ausgefallen: %s", verfahren, dienst, grund)
    return Stempel(verfahren, dienst, AUSGEFALLEN, grund=grund)


def _b64(daten: bytes) -> str:
    return base64.b64encode(daten).decode("ascii")
