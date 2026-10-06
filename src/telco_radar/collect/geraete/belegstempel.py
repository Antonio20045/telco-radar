"""Zeitstempel für ein Manifest: RFC 3161 bei freetsa.org und OpenTimestamps.

Datenkonzept Geräteradar, Abschnitt 10: das Manifest eines Tages wird gestempelt.
``stemple_rfc3161`` baut die Anfrage mit ``openssl ts -query`` über den Digest (mit
Nonce), schickt sie an den ``Zeitstempeldienst`` und prüft die Antwort mit ``openssl ts
-verify -queryfile``: Digest und Nonce gegen die eigene Anfrage, Unterschrift und Kette
gegen das festgelegte CA- und TSA-Zertifikat des Dienstes. Die Zertifikate von
freetsa.org gehören nach ``ZERTIFIKATE`` (``config/zeitstempel/``, ``freetsa(wurzel)``).
Nur eine so geprüfte Antwort ist ``gestempelt``. Fehlt ein Zertifikat, prüft openssl die
Antwort nur gegen das mitgeschickte Zertifikat; der Stempel heißt dann
``gestempelt_ungeprueft`` mit Grund, nie ``gestempelt``. Scheitert die Prüfung
(abgelehnt, anderer Digest oder Nonce, fremder Unterzeichner, unlesbar), ist der Stempel
``ungueltig`` mit Grund und ohne Token. ``stemple_ots`` schickt den Digest an jeden
Calendar-Server in ``OTS_KALENDER`` (HTTP-POST an ``/digest``, wie der
OpenTimestamps-Client) und nimmt jede Antwort, die eine ausstehende Bestätigung trägt.
Jeder Ausfall (openssl fehlt, startet nicht oder antwortet nicht, Server antwortet nicht
in der Frist oder nicht mit 200, OTS-Antwort unlesbar) ist ein ``Stempel`` im Zustand
``ausgefallen`` mit Grund, nie eine Ausnahme: der Lauf geht weiter. Die Antworten stehen
als Base64 im Stempel. HTTP geht über ``collect.http.sende``.
"""

from __future__ import annotations

import base64
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .. import http

log = logging.getLogger(__name__)

FREETSA = "https://freetsa.org/tsr"
ZERTIFIKATE = Path("config") / "zeitstempel"
FREETSA_CA = "freetsa-cacert.pem"
FREETSA_TSA = "freetsa-tsa.crt"
OTS_KALENDER = (
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://a.pool.eternitywall.com",
    "https://ots.btc.catallaxy.com",
)
RFC3161 = "rfc3161"
OPENTIMESTAMPS = "opentimestamps"
GESTEMPELT = "gestempelt"
UNGEPRUEFT = "gestempelt_ungeprueft"
UNGUELTIG = "ungueltig"
AUSGEFALLEN = "ausgefallen"
OHNE_ZERTIFIKAT = "gestempelt, Unterschrift ungeprüft"
OHNE_TOKEN = "Antwort ohne lesbares Zeitstempel-Token (abgelehnt oder unlesbar)"
STEMPEL_FRIST_S = 20.0
OPENSSL_FRIST_S = 20.0
OPENSSL_GRUND_HOECHSTENS = 160
OTS_HOECHSTENS = 10000
OTS_AUSSTEHEND = bytes.fromhex("83dfe30d2ef90c8e")
TSA_ANFRAGE = "application/timestamp-query"
OTS_ANNAHME = "application/vnd.opentimestamps.v1"
OTS_INHALT = "application/x-www-form-urlencoded"
DIGEST_LAENGE = 32
_GRUENDE = {
    "message imprint mismatch": "Antwort stempelt einen anderen Digest",
    "nonce mismatch": "Antwort gehört zu einer anderen Anfrage",
    "no time stamp token": "Antwort abgelehnt",
    "certificate verify error": "Unterzeichner nicht vom festgelegten Zertifikat",
}


@dataclass(frozen=True)
class Stempel:
    """Ein Zeitstempel oder sein Ausfall: Verfahren, Dienst, Zustand, Grund, Token."""

    verfahren: str
    dienst: str
    zustand: str
    grund: str | None = None
    token: str | None = None


@dataclass(frozen=True)
class Zeitstempeldienst:
    """Adresse eines RFC-3161-Dienstes und die Zertifikate, die seine Antwort prüfen.

    ``ca`` ist die Wurzel der Kette, ``zertifikat`` das des Unterzeichners.
    """

    adresse: str
    ca: Path
    zertifikat: Path


def freetsa(wurzel: Path = Path()) -> Zeitstempeldienst:
    """freetsa.org mit den Zertifikaten unter ``<wurzel>/config/zeitstempel/``."""
    ordner = wurzel / ZERTIFIKATE
    return Zeitstempeldienst(FREETSA, ordner / FREETSA_CA, ordner / FREETSA_TSA)


FREETSA_DIENST = freetsa()


class OpensslAusfall(Exception):
    """openssl startet nicht oder antwortet nicht in ``OPENSSL_FRIST_S``."""


def stemple(
    digest: str,
    *,
    dienst: Zeitstempeldienst = FREETSA_DIENST,
    kalender: tuple[str, ...] = OTS_KALENDER,
    openssl: str = "openssl",
    frist: float = STEMPEL_FRIST_S,
) -> tuple[Stempel, ...]:
    """Beide Verfahren für einen SHA-256-Digest in Hex; wirft nie."""
    return (
        stemple_rfc3161(digest, dienst=dienst, openssl=openssl, frist=frist),
        *stemple_ots(digest, kalender=kalender, frist=frist),
    )


def stemple_rfc3161(
    digest: str,
    *,
    dienst: Zeitstempeldienst = FREETSA_DIENST,
    openssl: str = "openssl",
    frist: float,
) -> Stempel:
    """RFC-3161-Stempel über ``openssl ts``, geprüft mit ``-verify``; wirft nie."""
    if shutil.which(openssl) is None:
        return _aus(RFC3161, dienst.adresse, f"openssl fehlt ({openssl})")
    with tempfile.TemporaryDirectory() as ordner:
        try:
            return _rfc3161(digest, dienst, openssl, frist, Path(ordner))
        except OpensslAusfall as fehler:
            return _aus(RFC3161, dienst.adresse, str(fehler))


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


def _rfc3161(
    digest: str, dienst: Zeitstempeldienst, openssl: str, frist: float, ordner: Path
) -> Stempel:
    adresse = dienst.adresse
    anfrage = ordner / "anfrage.tsq"
    frage = ("ts", "-query", "-digest", digest, "-sha256", "-cert")
    grund = _openssl(openssl, *frage, "-out", str(anfrage))
    if grund is not None:
        return _aus(RFC3161, adresse, f"Anfrage nicht gebaut: {grund}")
    antwort, grund = _post(
        adresse, anfrage.read_bytes(), {"Content-Type": TSA_ANFRAGE}, frist
    )
    if grund is not None:
        return _aus(RFC3161, adresse, grund)
    datei = ordner / "antwort.tsr"
    datei.write_bytes(antwort)
    fehlend = [str(p) for p in (dienst.ca, dienst.zertifikat) if not p.is_file()]
    if fehlend:
        grund = _pruefe_mitgeschickt(openssl, anfrage, datei, ordner)
    else:
        vertrauen = ("-CAfile", str(dienst.ca), "-untrusted", str(dienst.zertifikat))
        grund = _verify(openssl, anfrage, datei, *vertrauen)
    if grund is not None:
        log.warning("Stempel %s von %s ungültig: %s", RFC3161, adresse, grund)
        return Stempel(RFC3161, adresse, UNGUELTIG, grund=grund)
    if fehlend:
        warum = f"{OHNE_ZERTIFIKAT}: Zertifikat fehlt ({', '.join(fehlend)})"
        log.warning("Stempel %s von %s: %s", RFC3161, adresse, warum)
        return Stempel(RFC3161, adresse, UNGEPRUEFT, grund=warum, token=_b64(antwort))
    return Stempel(RFC3161, adresse, GESTEMPELT, token=_b64(antwort))


def _pruefe_mitgeschickt(
    openssl: str, anfrage: Path, datei: Path, ordner: Path
) -> str | None:
    """Prüft Digest, Nonce und Unterschrift gegen das mitgeschickte Zertifikat."""
    token = ordner / "token.der"
    mitgeschickt = ordner / "mitgeschickt.pem"
    auspacken = ("ts", "-reply", "-in", str(datei), "-token_out", "-out", str(token))
    if _openssl(openssl, *auspacken) is not None:
        return OHNE_TOKEN
    zeigen = ("pkcs7", "-inform", "DER", "-in", str(token), "-print_certs")
    grund = _openssl(openssl, *zeigen, "-out", str(mitgeschickt))
    if grund is not None:
        return grund
    if "BEGIN CERTIFICATE" not in mitgeschickt.read_text("utf-8", "replace"):
        return "Antwort ohne Zertifikat des Unterzeichners"
    return _verify(
        openssl, anfrage, datei, "-CAfile", str(mitgeschickt), "-partial_chain"
    )


def _verify(openssl: str, anfrage: Path, datei: Path, *vertrauen: str) -> str | None:
    """``openssl ts -verify`` gegen die eigene Anfrage: Digest, Nonce, Unterschrift."""
    pruefung = ("ts", "-verify", "-queryfile", str(anfrage), "-in", str(datei))
    return _openssl(openssl, *pruefung, *vertrauen)


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


def _openssl(openssl: str, *argumente: str) -> str | None:
    """Lässt openssl laufen; ``None`` heißt Erfolg, sonst ein lesbarer Grund."""
    try:
        lauf = subprocess.run(
            [openssl, *argumente],
            capture_output=True,
            timeout=OPENSSL_FRIST_S,
            check=False,
        )
    except subprocess.TimeoutExpired as fehler:
        grund = f"openssl antwortet nicht in {OPENSSL_FRIST_S:g} s"
        raise OpensslAusfall(grund) from fehler
    except OSError as fehler:
        grund = f"openssl startet nicht ({type(fehler).__name__})"
        raise OpensslAusfall(grund) from fehler
    if lauf.returncode == 0:
        return None
    return _grund(lauf.stderr.decode("utf-8", "replace"), lauf.returncode)


def _grund(fehlertext: str, code: int) -> str:
    """Grund aus der ersten Fehlerzeile von openssl: Bibliothek, Grund, Zusatz."""
    zeilen = fehlertext.strip().splitlines()
    for zeile in zeilen:
        teile = zeile.split(":", 8)
        if len(teile) > 5 and teile[1] == "error":
            bibliothek, ursache = teile[3], teile[5]
            zusatz = teile[8].strip() if len(teile) > 8 else ""
            roh = f"{ursache}: {zusatz}" if zusatz else ursache
            roh = roh[:OPENSSL_GRUND_HOECHSTENS]
            if ursache in _GRUENDE:
                return f"{_GRUENDE[ursache]} ({roh})"
            if bibliothek.startswith("asn1"):
                return f"Antwort unlesbar ({roh})"
            return f"openssl scheitert: {roh}"
    letzte = zeilen[-1] if zeilen else f"Exit {code}"
    return f"openssl scheitert: {letzte[:OPENSSL_GRUND_HOECHSTENS]}"


def _aus(verfahren: str, dienst: str, grund: str) -> Stempel:
    log.warning("Stempel %s bei %s ausgefallen: %s", verfahren, dienst, grund)
    return Stempel(verfahren, dienst, AUSGEFALLEN, grund=grund)


def _b64(daten: bytes) -> str:
    return base64.b64encode(daten).decode("ascii")
