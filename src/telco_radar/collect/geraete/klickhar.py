"""Mitschnitt einer Preisantwort als HAR 1.2: genau ein Eintrag, ohne Zugangsdaten.

Der Beleg je Klick (``klickbeleg``) hält die Antwort fest, die die Seite beim Klick
lädt (Datenkonzept Geräteradar, Abschnitt 10). ``har_aus`` schreibt sie als HAR mit
einem Eintrag: Methode, Adresse, Status, Köpfe und Körper. Cookies, ``Set-Cookie``
und Zugangsköpfe (``OHNE_KOPF``) stehen nie darin, die Cookie-Listen bleiben leer.
``schwaerze`` ersetzt in Antwort- und Anfragekörper die Werte dieser Köpfe (roh und
URL-kodiert, ab ``GEHEIM_MINDESTLAENGE`` Zeichen) und die Werte geheimer Schlüssel
(``GEHEIMER_SCHLUESSEL``: ``session*``, ``*token*``, ``auth*``, ``jwt*``, ``*csrf*``
und ähnliche) durch ``GESCHWAERZT``: in JSON über die Struktur, sonst in
``"schlüssel": "wert"`` und ``name="…" content="…"``. Ein Körper, der kein UTF-8 ist,
steht in Base64. Playwright spielt die Datei mit ``route_from_har`` ab.
``har_eintrag`` liest den Eintrag zurück, ``zugangskoepfe`` nennt verbotene Köpfe
einer gespeicherten Datei. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote, urlsplit

HAR_VERSION = "1.2"
HAR_ERZEUGER = "telco-radar Klick-Crawler"
HTTP_VERSION = "HTTP/1.1"
OHNE_KOPF = frozenset(
    {"cookie", "set-cookie", "set-cookie2", "authorization", "proxy-authorization"}
)
BASE64 = "base64"
INHALTSTYP = "content-type"
OHNE_TYP = "application/octet-stream"
GESCHWAERZT = "[geschwärzt]"
GEHEIM_MINDESTLAENGE = 8
GEHEIMER_SCHLUESSEL = re.compile(
    r"^(?:session|auth|jwt)|token|csrf|xsrf|secret|passw|api_?key", re.IGNORECASE
)
COOKIE_KOPF = frozenset({"cookie"})
SET_COOKIE_KOPF = frozenset({"set-cookie", "set-cookie2"})
_PAAR = re.compile(
    r"""(?P<k>"[^"\\\n]{1,80}"|'[^'\\\n]{1,80}')(?P<t>\s*:\s*)"""
    r"""(?P<v>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')"""
)
_ATTRIBUT = re.compile(
    r"""(?<=name=)(?P<k>"[^"\n]{1,80}"|'[^'\n]{1,80}')(?P<t>\s+(?:content|value)=)"""
    r"""(?P<v>"[^"\n]*"|'[^'\n]*')"""
)


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
    koerper = schwaerze(kopie.koerper, kopie.anfragekopf, kopie.antwortkopf)
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
            "content": _inhalt(koerper, _typ(kopie.antwortkopf)),
            "redirectURL": "",
            "headersSize": -1,
            "bodySize": len(koerper),
        },
        "cache": {},
        "timings": {"send": 0, "wait": 0, "receive": 0},
    }
    erzeuger = {"name": HAR_ERZEUGER, "version": HAR_VERSION}
    har = {"log": {"version": HAR_VERSION, "creator": erzeuger, "entries": [eintrag]}}
    return json.dumps(har, ensure_ascii=False, indent=1).encode("utf-8")


def schwaerze(koerper: bytes, *koepfe: Mapping[str, str]) -> bytes:
    """Der Körper ohne Cookie- und Zugangswerte der Köpfe und ohne geheime Werte."""
    for wert in sorted(_zugangswerte(koepfe), key=len, reverse=True):
        for form in dict.fromkeys((wert, quote(wert, safe=""))):
            koerper = koerper.replace(form.encode("utf-8"), GESCHWAERZT.encode("utf-8"))
    try:
        text = koerper.decode("utf-8")
    except UnicodeDecodeError:
        return koerper
    try:
        daten = json.loads(text)
    except ValueError:
        neu = _ATTRIBUT.sub(_ersetze, _PAAR.sub(_ersetze, text))
        return koerper if neu == text else neu.encode("utf-8")
    geschwaerzt, geaendert = _schwaerze_json(daten)
    if not geaendert:
        return koerper
    return json.dumps(geschwaerzt, ensure_ascii=False).encode("utf-8")


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
        koepfe = (kopie.anfragekopf, kopie.antwortkopf)
        koerper = schwaerze(kopie.anfragekoerper, *koepfe)
        anfrage["bodySize"] = len(koerper)
        inhalt = _inhalt(koerper, _typ(kopie.anfragekopf))
        anfrage["postData"] = {"mimeType": inhalt["mimeType"], "text": inhalt["text"]}
    return anfrage


def _zugangswerte(koepfe: tuple[Mapping[str, str], ...]) -> set[str]:
    """Cookie-Werte, Set-Cookie-Werte und Zugangsdaten ab der Mindestlänge."""
    werte = set()
    for kopf in koepfe:
        for name, inhalt in kopf.items():
            klein = name.lower()
            if klein in COOKIE_KOPF:
                stuecke = [s.partition("=")[2] for s in inhalt.split(";")]
            elif klein in SET_COOKIE_KOPF:
                zeilen = inhalt.splitlines()
                stuecke = [z.split(";", 1)[0].partition("=")[2] for z in zeilen]
            elif klein in OHNE_KOPF:
                stuecke = [inhalt, *inhalt.split()[1:]]
            else:
                continue
            for stueck in stuecke:
                wert = stueck.strip().strip('"')
                if len(wert) >= GEHEIM_MINDESTLAENGE:
                    werte.add(wert)
    return werte


def _schwaerze_json(wert: object) -> tuple[object, bool]:
    if isinstance(wert, dict):
        neu: dict[str, object] = {}
        geaendert = False
        for schluessel, inhalt in wert.items():
            if GEHEIMER_SCHLUESSEL.search(schluessel) and _geheim(inhalt):
                neu[schluessel] = GESCHWAERZT
                geaendert = True
            else:
                neu[schluessel], teil = _schwaerze_json(inhalt)
                geaendert = geaendert or teil
        return neu, geaendert
    if isinstance(wert, list):
        teile = [_schwaerze_json(inhalt) for inhalt in wert]
        return [t for t, _ in teile], any(g for _, g in teile)
    return wert, False


def _geheim(inhalt: object) -> bool:
    """Ein Wert, der etwas verraten kann: nicht leer, kein Wahrheitswert."""
    if inhalt is None or isinstance(inhalt, bool):
        return False
    return inhalt not in ("", GESCHWAERZT)


def _ersetze(treffer: re.Match[str]) -> str:
    if not GEHEIMER_SCHLUESSEL.search(treffer["k"][1:-1]):
        return treffer[0]
    zeichen = treffer["v"][0]
    return f"{treffer['k']}{treffer['t']}{zeichen}{GESCHWAERZT}{zeichen}"


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
