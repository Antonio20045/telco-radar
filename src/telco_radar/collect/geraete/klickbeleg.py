"""Beleg je Klick: Screenshot, Mitschnitt, Fundstellen und eine ``beleg_id`` aus Inhalt.

Datenkonzept Geräteradar, Abschnitt 10. Nach jeder gelesenen Kombination baut der
Klick-Crawler einen Beleg (``baue_beleg``): den Screenshot des Preisbereichs als WebP
(kann Pillow kein WebP, bleibt er PNG und heißt so), die Preisantwort als HAR
(``klickhar``), Zeitpunkt in UTC, Adresse der Produktseite und der Seite beim Lesen,
HTTP-Status von Seite und Antwort, die gelesenen Werte und je Wert seine Fundstellen:
im sichtbaren Text Selektor und Ausschnitt (``klicktext.fundstellen``, bei einem
Textmuster der Karte dessen Fundort), in der Antwort der JSON-Pfad der Klick-Karte
(bei mehreren Quellen mit Stelle und Ort davor, ``klickquellen``). Die ``beleg_id``
ist SHA-256 über beide Dateien, nie aus Titeltext. Fehlt Screenshot, Antwort oder
eine Fundstelle oder trägt die Kombination Bündelwerte (``ein_vertrag``, das Schema
kennt sie nicht), gibt es keinen Beleg, sondern einen Grund; ein Wert ohne Beleg ist
nicht gültig (``klicklauf.mit_beleg``). ``Beleg`` ist zugleich das Schema einer
Manifestzeile (``belegmanifest``). Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import hashlib
import io
import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from PIL import Image, UnidentifiedImageError, features
from playwright.sync_api import Error as PlaywrightFehler

from ...tarif_model import Preisphase
from .klickecho import Variante
from .klickhar import Antwortkopie, har_aus
from .klickkarte import WERTFELDER, Klickkarte, Phasenpfad, Wertpfad
from .klicktext import Buendelwerte, Preiswerte, fundstellen

if TYPE_CHECKING:
    from playwright.sync_api import Response

log = logging.getLogger(__name__)

BELEG_VERSION = 1
WEBP = "image/webp"
PNG = "image/png"
HAR = "application/json"
ENDUNG = {WEBP: "webp", PNG: "png", HAR: "har"}
UNBEGRENZT = "unbegrenzt"
GRUND_OHNE_BILD = "Beleg fehlt: kein Screenshot des Preisbereichs"
GRUND_OHNE_ANTWORT = "Beleg fehlt: keine Preisantwort mitgeschnitten"
GRUND_OHNE_WERTE = "Beleg fehlt: keine gelesenen Werte"
GRUND_BUENDEL = (
    f"Beleg fehlt: Bündelwerte passen nicht in Beleg Version {BELEG_VERSION}"
)


@dataclass(frozen=True)
class Fundstelle:
    """Wo ein Wert stand: Selektor und Ausschnitt im Text, Pfad in der Antwort."""

    feld: str
    selektor: str
    ausschnitt: str
    json_pfad: str


@dataclass(frozen=True)
class Belegdatei:
    """Eine Datei des Belegs mit Name in der Ablage, Typ, SHA-256 und Größe."""

    name: str
    typ: str
    sha256: str
    groesse: int


@dataclass(frozen=True)
class Beleg:
    """Eine Manifestzeile: ein Klick mit Zeitpunkt, Adresse, Werten und Dateien.

    ``werte`` hält jedes Wertfeld, ``None`` ist eine benannte Lücke; ``zeitpunkt`` ist
    UTC im Format ``JJJJ-MM-TTTHH:MM:SSZ``.
    """

    beleg_id: str
    anbieter: str
    zeitpunkt: str
    adresse: str
    seite: str
    http_status: int | None
    antwort_url: str
    antwort_status: int
    variante: Mapping[str, str | int | None]
    status: str
    werte: Mapping[str, Any]
    fundstellen: tuple[Fundstelle, ...]
    bild: Belegdatei
    mitschnitt: Belegdatei
    version: int = BELEG_VERSION


@dataclass(frozen=True)
class Belegpaket:
    """Ein Beleg mit den Bytes seiner beiden Dateien, bis die Ablage sie nimmt."""

    beleg: Beleg
    bild: bytes = field(repr=False)
    mitschnitt: bytes = field(repr=False)


@dataclass(frozen=True)
class Belegquelle:
    """Was der Crawler zu einer gelesenen Kombination weiß."""

    anbieter: str
    adresse: str
    seite: str
    http_status: int | None
    variante: Variante
    status: str
    werte: Preiswerte
    text: str | None
    screenshot_png: bytes | None
    antwort: Antwortkopie | None
    json_pfade: Mapping[str, str] | None = None
    fundorte: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    buendel: Buendelwerte | None = None


def baue_beleg(
    quelle: Belegquelle, karte: Klickkarte, zeitpunkt: datetime, webp: bool = True
) -> tuple[Belegpaket | None, str | None]:
    """Der Beleg einer gelesenen Kombination oder ``None`` mit dem Grund."""
    if quelle.screenshot_png is None:
        return None, GRUND_OHNE_BILD
    if quelle.antwort is None:
        return None, GRUND_OHNE_ANTWORT
    if quelle.buendel is not None and quelle.buendel != Buendelwerte():
        return None, GRUND_BUENDEL
    stellen, grund = belegstellen(
        quelle.werte,
        quelle.text or "",
        karte,
        json_pfade=quelle.json_pfade,
        fundorte=quelle.fundorte,
    )
    if grund is not None:
        return None, grund
    bild, typ = bild_fuer_beleg(quelle.screenshot_png, webp)
    har = har_aus(quelle.antwort, zeitpunkt)
    kennung = beleg_id(bild, har)
    beleg = Beleg(
        beleg_id=kennung,
        anbieter=quelle.anbieter,
        zeitpunkt=zeitpunkt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        adresse=quelle.adresse,
        seite=quelle.seite,
        http_status=quelle.http_status,
        antwort_url=quelle.antwort.url,
        antwort_status=quelle.antwort.status,
        variante={
            "speicher": quelle.variante.speicher,
            "tarif": quelle.variante.tarif,
            "laufzeit": quelle.variante.laufzeit,
        },
        status=quelle.status,
        werte=werte_als_json(quelle.werte),
        fundstellen=stellen,
        bild=Belegdatei(f"{kennung}.{ENDUNG[typ]}", typ, sha256(bild), len(bild)),
        mitschnitt=Belegdatei(f"{kennung}.{ENDUNG[HAR]}", HAR, sha256(har), len(har)),
    )
    return Belegpaket(beleg, bild, har), None


def belegstellen(
    werte: Preiswerte,
    text: str,
    karte: Klickkarte,
    *,
    json_pfade: Mapping[str, str] | None = None,
    fundorte: Mapping[str, tuple[str, str]] | None = None,
) -> tuple[tuple[Fundstelle, ...], str | None]:
    """Je gelesenem Wert die Fundstellen; fehlt eine, der Grund.

    ``fundorte`` nennt je Feld Selektor und Ausschnitt aus einem Textmuster,
    ``json_pfade`` je Feld den Pfad; ohne sie gelten Text und Pfade der Karte.
    """
    gelesen = [f for f in WERTFELDER if getattr(werte, f) is not None]
    if not gelesen:
        return (), GRUND_OHNE_WERTE
    ausschnitte = {f: (karte.zusammenfassung, a) for f, a in fundstellen(text).items()}
    ausschnitte.update({} if fundorte is None else fundorte)
    if json_pfade is None:
        json_pfade = {f: pfadtext(p) for f, p in karte.antwort.pfade.items()}
    stellen = []
    for feld in gelesen:
        if feld not in ausschnitte:
            return (), f"Beleg fehlt: {feld} ohne Fundstelle im Text"
        if feld not in json_pfade:
            return (), f"Beleg fehlt: {feld} ohne Pfad in der Antwort"
        selektor, ausschnitt = ausschnitte[feld]
        stellen.append(Fundstelle(feld, selektor, ausschnitt, json_pfade[feld]))
    return tuple(stellen), None


def beleg_id(bild: bytes, mitschnitt: bytes) -> str:
    """SHA-256 über Screenshot und Mitschnitt, je mit Länge davor."""
    summe = hashlib.sha256()
    for teil in (bild, mitschnitt):
        summe.update(len(teil).to_bytes(8, "big"))
        summe.update(teil)
    return summe.hexdigest()


def sha256(daten: bytes) -> str:
    """SHA-256 einer Datei als Hex."""
    return hashlib.sha256(daten).hexdigest()


def bild_fuer_beleg(png: bytes, webp: bool = True) -> tuple[bytes, str]:
    """Der Screenshot als verlustfreies WebP; ohne WebP in Pillow bleibt er PNG."""
    if not webp or not features.check("webp"):
        return png, PNG
    try:
        with Image.open(io.BytesIO(png)) as bild:
            ziel = io.BytesIO()
            bild.save(ziel, "WEBP", lossless=True, exact=True)
    except (OSError, UnidentifiedImageError):
        return png, PNG
    return ziel.getvalue(), WEBP


def pfadtext(pfad: str | Wertpfad | Phasenpfad) -> str:
    """Der JSON-Pfad einer Fundstelle; eine Phasenliste mit ihren Feldnamen."""
    if isinstance(pfad, Phasenpfad):
        return f"{pfad.liste}[*].{{{pfad.von},{pfad.bis},{pfad.betrag}}}"
    if isinstance(pfad, Wertpfad):
        return pfad.pfad
    return pfad


def werte_als_json(werte: Preiswerte) -> dict[str, Any]:
    """Jedes Wertfeld als JSON-Wert; unbegrenztes Volumen heißt ``unbegrenzt``."""
    daten: dict[str, Any] = {}
    for feld in WERTFELDER:
        wert = getattr(werte, feld)
        if isinstance(wert, tuple):
            wert = [[p.von_monat, p.bis_monat, p.betrag] for p in wert]
        elif isinstance(wert, float) and math.isinf(wert):
            wert = UNBEGRENZT
        daten[feld] = wert
    return daten


def werte_aus_json(daten: Mapping[str, Any]) -> Preiswerte:
    """Die Werte einer Manifestzeile zurück als ``Preiswerte``."""
    werte: dict[str, Any] = {}
    for feld in WERTFELDER:
        wert = daten.get(feld)
        if isinstance(wert, list):
            wert = tuple(Preisphase(v, b, betrag) for v, b, betrag in wert)
        elif wert == UNBEGRENZT:
            wert = math.inf
        werte[feld] = wert
    return Preiswerte(**werte)


def kopie_aus(antwort: Response | None) -> Antwortkopie | None:
    """Die Preisantwort als Daten; ``None`` ohne Antwort, lesbaren Körper oder Köpfe.

    Die Köpfe kommen aus ``all_headers`` samt Cookies, damit ``klickhar.schwaerze``
    deren Werte auch im Körper findet; in die HAR-Datei kommen sie nie.
    """
    if antwort is None:
        return None
    anfrage = antwort.request
    try:
        koerper = antwort.body()
        anfragekopf = anfrage.all_headers()
        antwortkopf = antwort.all_headers()
    except PlaywrightFehler as fehler:
        log.info("Klick-Crawler: Körper von %s fehlt: %s", antwort.url, fehler)
        return None
    return Antwortkopie(
        methode=anfrage.method,
        url=antwort.url,
        anfragekopf=anfragekopf,
        status=antwort.status,
        statustext=antwort.status_text,
        antwortkopf=antwortkopf,
        koerper=koerper,
        anfragekoerper=anfrage.post_data_buffer,
    )
