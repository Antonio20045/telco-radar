"""Mitschnitt einer Preisantwort als HAR 1.2: genau ein Eintrag, ohne Zugangsdaten.

Der Beleg je Klick (``klickbeleg``) hält die Antwort fest, die die Seite beim Klick
lädt (Datenkonzept Geräteradar, Abschnitt 10). ``har_aus`` schreibt sie als HAR mit
einem Eintrag: Methode, Adresse, Status, Köpfe und Körper. Cookies, ``Set-Cookie``
und Zugangsköpfe (``OHNE_KOPF``) stehen nie darin, die Cookie-Listen bleiben leer.
Ein Körper, der kein UTF-8 ist, steht in Base64. Playwright spielt die Datei mit
``route_from_har`` ohne Netz ab. ``har_eintrag`` liest den Eintrag zurück,
``zugangskoepfe`` nennt verbotene Köpfe einer gespeicherten Datei. Dieses Modul ruft
kein Netz.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlsplit

HAR_VERSION = "1.2"
HAR_ERZEUGER = "telco-radar Klick-Crawler"
HTTP_VERSION = "HTTP/1.1"
OHNE_KOPF = frozenset(
    {"cookie", "set-cookie", "set-cookie2", "authorization", "proxy-authorization"}
)
BASE64 = "base64"
INHALTSTYP = "content-type"
OHNE_TYP = "application/octet-stream"


class HarFehler(ValueError):
    """Eine HAR-Datei ist nicht lesbar oder hat nicht genau einen Eintrag."""


@dataclass(frozen=True)
class Antwortkopie:
    """Die Preisantwort eines Klicks als Daten, ohne Browserobjekt."""

    methode: str
    url: str
    anfragekopf: Mapping[str, str]
    status: int
    statustext: str
    antwortkopf: Mapping[str, str]
    koerper: bytes
    anfragekoerper: bytes | None = None


def har_aus(kopie: Antwortkopie, zeitpunkt: datetime) -> bytes:
    """Die Antwort als HAR-Datei mit einem Eintrag, ohne Cookies und Zugangsköpfe."""
    eintrag = {
        "startedDateTime": _iso(zeitpunkt),
        "time": 0,
        "request": _anfrage(kopie),
        "response": {
            "status": kopie.status,
            "statusText": kopie.statustext,
            "httpVersion": HTTP_VERSION,
            "cookies": [],
            "headers": _koepfe(kopie.antwortkopf),
            "content": _inhalt(kopie.koerper, _typ(kopie.antwortkopf)),
            "redirectURL": "",
            "headersSize": -1,
            "bodySize": len(kopie.koerper),
        },
        "cache": {},
        "timings": {"send": 0, "wait": 0, "receive": 0},
    }
    erzeuger = {"name": HAR_ERZEUGER, "version": HAR_VERSION}
    har = {"log": {"version": HAR_VERSION, "creator": erzeuger, "entries": [eintrag]}}
    return json.dumps(har, ensure_ascii=False, indent=1).encode("utf-8")


def har_eintrag(daten: bytes) -> tuple[str, int, bytes]:
    """Adresse, Status und Körper des einen Eintrags; ``HarFehler`` sonst."""
    eintraege = _eintraege(daten)
    if len(eintraege) != 1:
        raise HarFehler(f"HAR mit {len(eintraege)} Einträgen statt einem")
    try:
        url = eintraege[0]["request"]["url"]
        antwort = eintraege[0]["response"]
        inhalt = antwort["content"]
        text = inhalt.get("text", "")
        if inhalt.get("encoding") == BASE64:
            koerper = base64.b64decode(text, validate=True)
        else:
            koerper = text.encode("utf-8")
        return str(url), int(antwort["status"]), koerper
    except (KeyError, TypeError, AttributeError, ValueError) as fehler:
        raise HarFehler(f"HAR-Eintrag unvollständig: {fehler}") from fehler


def zugangskoepfe(daten: bytes) -> list[str]:
    """Jeder Cookie- oder Zugangskopf und jede gefüllte Cookie-Liste der Datei."""
    funde = []
    for eintrag in _eintraege(daten):
        for teil in ("request", "response"):
            stueck = eintrag.get(teil) if isinstance(eintrag, dict) else None
            if not isinstance(stueck, dict):
                continue
            for kopf in stueck.get("headers") or []:
                name = (
                    str(kopf.get("name", "")).lower() if isinstance(kopf, dict) else ""
                )
                if name in OHNE_KOPF:
                    funde.append(f"{teil}: Kopf {name}")
            if stueck.get("cookies"):
                funde.append(f"{teil}: Cookies")
    return funde


def _eintraege(daten: bytes) -> list:
    try:
        har = json.loads(daten.decode("utf-8"))
        eintraege = har["log"]["entries"]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as fehler:
        raise HarFehler(f"keine HAR-Datei: {fehler}") from fehler
    if not isinstance(eintraege, list):
        raise HarFehler("keine HAR-Datei: entries ist keine Liste")
    return eintraege


def _anfrage(kopie: Antwortkopie) -> dict:
    frage = parse_qsl(urlsplit(kopie.url).query, keep_blank_values=True)
    anfrage = {
        "method": kopie.methode,
        "url": kopie.url,
        "httpVersion": HTTP_VERSION,
        "cookies": [],
        "headers": _koepfe(kopie.anfragekopf),
        "queryString": [{"name": n, "value": w} for n, w in frage],
        "headersSize": -1,
        "bodySize": len(kopie.anfragekoerper or b""),
    }
    if kopie.anfragekoerper:
        inhalt = _inhalt(kopie.anfragekoerper, _typ(kopie.anfragekopf))
        anfrage["postData"] = {"mimeType": inhalt["mimeType"], "text": inhalt["text"]}
    return anfrage


def _koepfe(kopf: Mapping[str, str]) -> list[dict[str, str]]:
    return [
        {"name": name, "value": wert}
        for name, wert in sorted(kopf.items())
        if name.lower() not in OHNE_KOPF
    ]


def _typ(kopf: Mapping[str, str]) -> str:
    return next((w for n, w in kopf.items() if n.lower() == INHALTSTYP), OHNE_TYP)


def _inhalt(koerper: bytes, typ: str) -> dict:
    try:
        return {"size": len(koerper), "mimeType": typ, "text": koerper.decode("utf-8")}
    except UnicodeDecodeError:
        text = base64.b64encode(koerper).decode("ascii")
        return {"size": len(koerper), "mimeType": typ, "text": text, "encoding": BASE64}


def _iso(zeitpunkt: datetime) -> str:
    utc = zeitpunkt.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"
