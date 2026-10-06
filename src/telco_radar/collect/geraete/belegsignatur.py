"""AWS Signature Version 4 für S3-kompatible Ablagen (Backblaze B2, Cloudflare R2).

Selbst gerechnet nach der AWS-Beschreibung, ohne Bibliothek: kanonische Anfrage aus
Methode, Pfad, Abfrage, signierten Köpfen und SHA-256 des Körpers, daraus der zu
signierende Text, signiert mit dem abgeleiteten Schlüssel aus Datum, Region und Dienst.
``signiere`` gibt die Köpfe zurück, die zur Anfrage gehören, darunter
``Authorization``; der geheime Schlüssel steht in keinem davon. Dieses Modul ruft kein
Netz und liest keine Uhr: der Zeitpunkt kommt vom Aufrufer.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import quote, unquote, urlsplit

VERFAHREN = "AWS4-HMAC-SHA256"
ABSCHLUSS = "aws4_request"
DIENST = "s3"
_UNRESERVIERT = "-_.~"


def signiere(
    methode: str,
    url: str,
    kopf: Mapping[str, str],
    koerper_sha256: str,
    *,
    schluessel_id: str,
    schluessel: str,
    region: str,
    zeitpunkt: datetime,
    dienst: str = DIENST,
) -> dict[str, str]:
    """Die Köpfe der signierten Anfrage: ``kopf`` plus Host, Datum, Hash, Signatur."""
    teile = urlsplit(url)
    stempel = zeitpunkt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    tag = stempel[:8]
    alle = {
        **kopf,
        "host": teile.netloc,
        "x-amz-date": stempel,
        "x-amz-content-sha256": koerper_sha256,
    }
    kanonisch, signiert = _kanonische_koepfe(alle)
    anfrage = "\n".join(
        [
            methode.upper(),
            quote(unquote(teile.path or "/"), safe="/" + _UNRESERVIERT),
            _kanonische_abfrage(teile.query),
            kanonisch,
            signiert,
            koerper_sha256,
        ]
    )
    bereich = f"{tag}/{region}/{dienst}/{ABSCHLUSS}"
    zu_signieren = "\n".join(
        [VERFAHREN, stempel, bereich, hashlib.sha256(anfrage.encode()).hexdigest()]
    )
    signatur = hmac.new(
        _signierschluessel(schluessel, tag, region, dienst),
        zu_signieren.encode(),
        hashlib.sha256,
    ).hexdigest()
    alle["Authorization"] = (
        f"{VERFAHREN} Credential={schluessel_id}/{bereich}, "
        f"SignedHeaders={signiert}, Signature={signatur}"
    )
    return alle


def _kanonische_koepfe(kopf: Mapping[str, str]) -> tuple[str, str]:
    werte = {name.lower(): " ".join(str(w).split()) for name, w in kopf.items()}
    namen = sorted(werte)
    kanonisch = "".join(f"{name}:{werte[name]}\n" for name in namen)
    return kanonisch, ";".join(namen)


def _kanonische_abfrage(abfrage: str) -> str:
    paare = []
    for teil in filter(None, abfrage.split("&")):
        name, _, wert = teil.partition("=")
        paare.append((_kodiere(name), _kodiere(wert)))
    return "&".join(f"{n}={w}" for n, w in sorted(paare))


def _kodiere(text: str) -> str:
    return quote(unquote(text), safe=_UNRESERVIERT)


def _signierschluessel(schluessel: str, tag: str, region: str, dienst: str) -> bytes:
    stufe = ("AWS4" + schluessel).encode()
    for teil in (tag, region, dienst, ABSCHLUSS):
        stufe = hmac.new(stufe, teil.encode(), hashlib.sha256).digest()
    return stufe
