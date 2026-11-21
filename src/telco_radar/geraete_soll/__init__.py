"""Soll-Zählung des Geräteradars, Stufe 1: die Modellliste des Anbieters.

Abnahmekriterium 1 (Antonio, 21.11.2026): je Anbieter eine tägliche Soll/Ist-Zählung.
Dieses Paket zählt, getrennt vom Sammler, was eine Liste des Anbieters an Modellen
führt: eigene Adressen (``QUELLEN``), ein Abruf je Quelle über den robots.txt-treuen
Weg (``geraete_abruf``), eigene Leser (``leser``). Es importiert keinen Parser und
keinen Adapter aus ``collect.geraete`` (Test ``test_geraete_soll_leser``); aus
``collect`` nur ``http``. An jeder Zahl stehen ``art``, ``quelle``, ``gezaehlt_um`` und
``gleiche_quelle_wie_sammler``.

Alle vier Listen dieser Stufe (Vodafone, o2, 1&1, congstar) liest auch der Sammler;
sie zeigen also, ob die Messung ihre eigene Liste ganz abgearbeitet hat, nicht, was der
Anbieter unabhängig davon anbietet. Ein unabhängiges Soll zählt Stufe 2 im Browser aus
der sichtbaren Übersicht (``geraete_vollstaendigkeit.SichtbareAuswahl``). Telekom und
Saturn/MediaMarkt haben in dieser Stufe kein Soll (``OHNE_SOLL``): die Telekom-Sitemap
führte am 21.11.2026 14 Modelle, die die Übersicht als nicht im Angebot zeigt, und ließ
21 angebotene weg; die Tarifwelt-Sitemap nennt kein Netz. Ein Soll, das nicht zu zählen
ist, ist ``None`` mit Grund, nie 0 und nie das Ist.

Zeitbudget (CLAUDE.md Regel 8): ``RESERVE_SEKUNDEN`` (Quellen × ``SEKUNDEN_JE_ABRUF``)
hält die Tarifwelt-Stufe nach sich frei (``geraete_tarifwelt.RESERVE_NACH_STUFE``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

from ..collect.http import HttpFehler
from ..geraete_abruf import hole_fuer_anbieter
from ..geraete_model import Katalog, erkenne_geraet
from ..models import normalize_url
from . import leser as _leser
from .leser import Fund, LeserFehler

log = logging.getLogger(__name__)

ART_SITEMAP = "sitemap"
ART_SEITE = "uebersichtsseite"
ART_API = "uebersicht_api"

KENNUNG = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
GRUND_ZEIT = "Zeitbudget des Laufs erschöpft, Liste nicht abgerufen"
SPEICHER_FEHLT = "Die Liste des Anbieters nennt keine Speichergrößen"
GRUND_TELEKOM = "wird in Stufe 2 im Browser aus der Übersicht gezählt"
GRUND_SATURN = (
    "Soll je Netz nicht zählbar (Sitemap ohne Netz); Stufe 2 zählt die "
    "Tarifwelt-Übersicht je Netz im Browser"
)
SEKUNDEN_JE_ABRUF = 45.0
"""Höchstdauer eines Abrufs: robots.txt und Liste je ein Timeout
(``http.timeout_seconds`` in ``config/settings.yaml``, 20 s), plus 5 s."""
SATURN_NETZE = (
    "Saturn/MediaMarkt · Telekom-Netz",
    "Saturn/MediaMarkt · Vodafone-Netz",
    "Saturn/MediaMarkt · o2-Netz",
)


@dataclass(frozen=True)
class Quelle:
    """Eine Liste eines Anbieters; ``zeilen`` sind die Anbieterzeilen, für die sie
    gilt (Saturn/MediaMarkt: eine Sitemap ohne Netz für alle drei Netze)."""

    zeilen: tuple[str, ...]
    konfig: str
    url: str
    art: str
    gleiche_quelle_wie_sammler: bool
    leser: Callable[[str], list[Fund]]
    speicher_grund: str = SPEICHER_FEHLT


QUELLEN: tuple[Quelle, ...] = (
    Quelle(
        ("Vodafone",),
        "Vodafone",
        "https://api.vodafone.de/glados/v2/hardware/v2"
        "?businessTransaction=newContract&salesChannel=Online.Consumer",
        ART_API,
        True,
        _leser.vodafone_liste,
    ),
    Quelle(
        ("o2",),
        "o2",
        "https://www.o2online.de/e-shop/rest/catalog/o2shop/privatkunden/"
        "ratenzahlung/default/__not-specified__/__not-specified__/__not-specified__",
        ART_API,
        True,
        _leser.o2_katalog,
    ),
    Quelle(
        ("1&1",),
        "1&1",
        "https://mobile.1und1.de/smartphones",
        ART_SEITE,
        True,
        _leser.einsundeins_kacheln,
    ),
    Quelle(
        ("congstar",),
        "congstar",
        "https://www.congstar.de/sitemap/devices.xml",
        ART_SITEMAP,
        True,
        _leser.congstar_sitemap,
    ),
)

OHNE_SOLL: dict[str, str] = {
    "Telekom": GRUND_TELEKOM,
    **{netz: GRUND_SATURN for netz in SATURN_NETZE},
}
"""Anbieterzeilen ohne Soll in Stufe 1, mit Grund (Modulkopf)."""

RESERVE_SEKUNDEN = len(QUELLEN) * SEKUNDEN_JE_ABRUF
"""Zeit, die nach der Tarifwelt-Stufe für alle Soll-Abrufe frei bleibt."""


@dataclass
class SollModell:
    """Ein Modell des Solls; ``schluessel`` ist die Katalog-ID oder, ohne
    Katalogtreffer, die normalisierte Adresse."""

    schluessel: str
    name: str
    url: str
    im_katalog: bool
    nur_paket: bool


@dataclass
class Soll:
    """Das Soll einer Quelle; ``modelle`` ``None`` heißt nicht zählbar (``grund``)."""

    art: str | None
    quelle: str | None
    gleiche_quelle_wie_sammler: bool | None
    gezaehlt_um: str
    speicher_grund: str
    modelle: dict[str, SollModell] | None = None
    grund: str | None = None
    funde: int = 0

    def als_dict(self) -> dict:
        """Die Felder für die Lauf-Datei (``geraete_vollstaendigkeit.baue``)."""
        return {
            "art": self.art,
            "quelle": self.quelle,
            "gleiche_quelle_wie_sammler": self.gleiche_quelle_wie_sammler,
            "gezaehlt_um": self.gezaehlt_um,
            "grund": self.grund,
            "speicher_grund": self.speicher_grund,
            "funde": self.funde,
            "modelle": None
            if self.modelle is None
            else [vars(m) for m in self.modelle.values()],
        }


def anzeigename(geraet) -> str:
    """„Google Pixel 10“; ein Modellname, der den Hersteller schon trägt
    („Motorola edge 60 neo“), bekommt ihn nicht doppelt."""
    hersteller, modell = str(geraet.hersteller), str(geraet.modell)
    if modell.lower().startswith(hersteller.lower()):
        return modell
    return f"{hersteller} {modell}"


def ordne_zu(funde: list[Fund], katalog: Katalog) -> dict[str, SollModell]:
    """Funde -> Modelle: über den Katalog (``erkenne_geraet``, Titel nur zum Finden),
    sonst die normalisierte Adresse als Schlüssel. Ein Modell ist ``nur_paket``,
    wenn JEDER seiner Funde ein Paket mit Zubehör ist."""
    modelle: dict[str, SollModell] = {}
    for fund in funde:
        geraet = erkenne_geraet(fund.titel, katalog)
        if geraet is not None:
            schluessel = geraet.device_id
            name = anzeigename(geraet)
        else:
            schluessel, name = normalize_url(fund.url), _leser.lesbar(fund.titel)
        alt = modelle.get(schluessel)
        if alt is None:
            modelle[schluessel] = SollModell(
                schluessel, name, fund.url, geraet is not None, fund.nur_paket
            )
        elif alt.nur_paket and not fund.nur_paket:
            alt.nur_paket, alt.url = False, fund.url
    return modelle


def zaehle(quelle: Quelle, hole: Callable, kopfzeilen: dict, jetzt: str, katalog):
    """Ein Abruf, ein Leser, die Zuordnung; jedes Scheitern wird ``grund``."""
    soll = Soll(
        quelle.art,
        quelle.url,
        quelle.gleiche_quelle_wie_sammler,
        jetzt,
        quelle.speicher_grund,
    )
    try:
        antwort = hole(quelle.url, kopfzeilen or None, einmalig=True)
    except (HttpFehler, RuntimeError) as fehler:
        log.warning("Soll %s: Abruf gescheitert: %s", quelle.konfig, fehler)
        soll.grund = f"Abruf gescheitert ({type(fehler).__name__}: {fehler})"[:300]
        return soll
    status, text = antwort
    if getattr(antwort, "schutz", False):
        soll.grund = f"Schutzantwort des Anbieters (HTTP {status}), nicht umgangen"
        return soll
    if status != 200:
        soll.grund = f"Abruf gescheitert (HTTP {status})"
        return soll
    try:
        funde = quelle.leser(text)
    except LeserFehler as fehler:
        log.warning("Soll %s: Antwort nicht lesbar: %s", quelle.konfig, fehler)
        soll.grund = f"Antwort nicht lesbar: {fehler}"
        return soll
    soll.funde = len(funde)
    soll.modelle = ordne_zu(funde, katalog)
    return soll


def _weg(quellen, quelle: Quelle, hole: Callable, uhr: Callable):
    """Der gebremste Abruf (robots.txt, Crawl-delay, Besuchszeit) mit ehrlicher
    Kennung: die eigene des Anbieters aus der Konfiguration, sonst ``KENNUNG``;
    Kopfzeilen (Vodafone-Schlüssel, o2-Accept) ebenfalls aus der Konfiguration."""
    anbieter = quellen.nach_name(quelle.konfig) if quellen is not None else None
    eigene = str(getattr(anbieter, "user_agent", "") or "").strip()
    kennung = eigene if eigene else KENNUNG
    abstand = getattr(anbieter, "rate_limit_sekunden", 2.0)
    weg = SimpleNamespace(user_agent=kennung, rate_limit_sekunden=abstand)
    kopf = dict(getattr(anbieter, "kopfzeilen", None) or {})
    return hole_fuer_anbieter(hole, weg, uhr), kopf


def zaehle_alle(
    quellen,
    hole: Callable,
    uhr: Callable,
    katalog,
    rest: Callable[[], float],
    mindest_sekunden: float,
) -> dict[str, Soll]:
    """Das Soll je Anbieterzeile. Vor jedem Abruf muss die Restzeit des Jobs
    (``rest``) für Robots-Abruf und Liste reichen (``mindest_sekunden``); sonst steht
    das Soll als ``GRUND_ZEIT`` da (CLAUDE.md Regel 8)."""
    ergebnis: dict[str, Soll] = {}
    for quelle in QUELLEN:
        jetzt = uhr().isoformat(timespec="seconds")
        if rest() < mindest_sekunden:
            soll = Soll(
                quelle.art,
                quelle.url,
                quelle.gleiche_quelle_wie_sammler,
                jetzt,
                quelle.speicher_grund,
                grund=GRUND_ZEIT,
            )
        else:
            gebremst, kopf = _weg(quellen, quelle, hole, uhr)
            soll = zaehle(quelle, gebremst, kopf, jetzt, katalog)
        for zeile in quelle.zeilen:
            ergebnis[zeile] = soll
    jetzt = uhr().isoformat(timespec="seconds")
    for zeile, grund in OHNE_SOLL.items():
        ergebnis[zeile] = Soll(None, None, None, jetzt, grund, grund=grund)
    return ergebnis
