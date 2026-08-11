"""Loader fuer die drei Konfigurationsdateien des Geraete- und Preisradars.

Bewusst NICHT in `config.py`: die trennt Betreiber-Presse von allem anderen,
und jede weitere Quellenart in diesem Projekt bringt ihren eigenen Loader
neben dem nutzenden Modul mit (promo_config.py, ct_log.lade_domains,
ctm.lade_fokus, tarif_crawler, lieferzeit, aenderungen). Dieselbe Konvention
hier - und dieselbe Failsafe-Regel: eine fehlende Datei ist kein Fehler,
sondern eine leere Konfiguration. Die Geraetestufe tut dann nichts.

    config/geraete_katalog.yaml   die VERFOLGTEN Modelle (nicht der Markt)
    config/farben.yaml            Schreibweise -> kanonische Farbe
    config/geraete_quellen.yaml   wer beobachtet wird und wie
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

import yaml

from .geraete_model import Geraet, Katalog, normalisiere

log = logging.getLogger(__name__)

# Wie eine Quelle beschafft wird - die Rangfolge aus Teil C1 des Auftrags,
# beste zuerst. `deaktiviert` ist ein vollwertiges Ergebnis, kein Mangel:
# eine ehrliche Luecke ist besser als eine Zahl, der niemand trauen kann.
METHODEN = ("api", "ldjson", "shopify", "json_endpunkt", "html", "js",
            "kein_hardware", "deaktiviert")

# Diese zwei sind gueltige Messergebnisse und keine Fehlkonfiguration, aber
# es gibt nichts abzurufen. `kein_hardware` heisst "gemessen: der Anbieter
# verkauft keine Geraete" - genau der Befund, der in der Zeile "Ohne
# Hardware-Vermarktung beobachtet" sichtbar bleiben soll.
_NICHT_CRAWLBAR = ("deaktiviert", "kein_hardware")

ANBIETER_TYPEN = ("handel", "netzbetreiber", "discount")

# Voreinstellung der Host-Bremse je Anbieter. Bewusst konservativ: dieses
# Radar fragt Produktseiten fremder Shops ab, nicht Presse-Feeds.
_RATE_LIMIT_STANDARD = 2.0
_MAX_PRODUKTE_STANDARD = 60


@dataclass
class Einstieg:
    """Eine Seite, von der aus Produktlinks GEERNTET werden duerfen.

    Es wird ausschliesslich abgerufen, was hier steht oder von hier aus
    verlinkt ist - nie eine hochgezaehlte ID. Dieselbe Regel und derselbe
    Grund wie beim Tarif-Sammler (§ 87b UrhG, Datenbankherstellerrecht).
    """
    url: str
    label: str = ""
    kind: str = "static"          # static | sitemap | shopify | js
    pfadmuster: str = ""          # nur Links, deren Pfad das enthaelt

    @property
    def crawlable(self) -> bool:
        return self.kind in ("static", "js", "sitemap", "shopify")


@dataclass
class Anbieter:
    name: str
    typ: str = "handel"
    gruppe: str = ""
    netz: str = ""                # nur bei typ=discount: in wessen Netz
    rang: int = 99                # gepflegt, nicht gerechnet (wie promo rang)
    methode: str = "ldjson"
    aktiv: bool = True
    grund: str = ""               # WARUM nicht aktiv - steht auf der Quellenseite
    eigen: bool = False           # Vodafone: eigene Referenz, kein Wettbewerber
    # Der LADEN hinter dem Namen. mobilcom-debitel und freenet sind derselbe
    # Shop unter zwei Marken - die Positionskarte darf sie nicht als zwei
    # Wettbewerber fuehren, sonst steht dasselbe Sortiment zweimal
    # nebeneinander und der Preisvergleich vergleicht einen Laden mit sich
    # selbst. Dasselbe gilt fuer MediaMarkt und Saturn (Ceconomy).
    #
    # `gruppe` taugt dafuer NICHT: klarmobil traegt ebenfalls `gruppe:
    # freenet`, ist aber ein anderer Laden mit eigenem Sortiment. Aus der
    # Gruppe abgeleitet stuende dort "freenet (klarmobil)". Deshalb wird der
    # Laden ausdruecklich gesetzt, nicht erraten.
    shop: str = ""                # leer = der Anbieter ist sein eigener Laden
    anzeige: str = ""             # leer = der Name steht fuer sich
    basis_url: str = ""
    max_produkte: int = _MAX_PRODUKTE_STANDARD
    rate_limit_sekunden: float = _RATE_LIMIT_STANDARD
    hinweis: str = ""
    einstiege: list = field(default_factory=list)

    @property
    def schluessel(self) -> str:
        return normalisiere(self.name)

    @property
    def crawlbar(self) -> bool:
        return bool(self.aktiv and self.methode not in _NICHT_CRAWLBAR
                    and any(e.crawlable for e in self.einstiege))

    @property
    def crawled_einstiege(self) -> list:
        return [e for e in self.einstiege if e.crawlable]


@dataclass
class QuellenConfig:
    anbieter: list = field(default_factory=list)

    @property
    def crawlbare(self) -> list:
        return [a for a in self.anbieter if a.crawlbar]

    @property
    def wettbewerber(self) -> list:
        return [a for a in self.anbieter if not a.eigen]

    @property
    def seiten_zahl(self) -> int:
        """Zahl der wirklich abgefragten Einstiegsseiten - dieselbe Kennzahl
        wie `PromoConfig.page_count`. Die Zahl der Anbieter sagt nichts
        darueber aus, wie breit wirklich gemessen wird."""
        return sum(len(a.crawled_einstiege) for a in self.crawlbare)

    def nach_name(self, name: str):
        schluessel = normalisiere(name)
        for a in self.anbieter:
            if a.schluessel == schluessel:
                return a
        return None


# --------------------------------------------------------------------------

def lade_katalog(root: Path) -> Katalog:
    """config/geraete_katalog.yaml -> Katalog.

    Ein Eintrag ohne `hersteller` oder `modell` wird verworfen und gemeldet;
    ein doppelter Eintrag laesst den Katalog werfen (Katalog.__post_init__) -
    zwei Zeilen mit derselben device_id wuerden sonst still dieselbe
    Zeitreihe fuellen.
    """
    path = Path(root) / "config" / "geraete_katalog.yaml"
    if not path.exists():
        return Katalog(geraete=[])
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    geraete = []
    for g in (raw.get("geraete") or []):
        if not isinstance(g, dict):
            continue
        hersteller = str(g.get("hersteller") or "").strip()
        modell = str(g.get("modell") or "").strip()
        if not hersteller or not modell:
            log.warning("geraete_katalog: Eintrag ohne hersteller/modell verworfen: %r", g)
            continue
        generation = g.get("generation")
        geraete.append(Geraet(
            hersteller=hersteller,
            modell=modell,
            marktstart=str(g.get("marktstart") or "").strip(),
            generation=int(generation) if str(generation or "").strip().isdigit() else None,
            vorgaenger=str(g.get("vorgaenger") or "").strip(),
            segment=str(g.get("segment") or "").strip(),
            speicher=[int(s) for s in (g.get("speicher") or [])
                      if str(s).strip().isdigit()],
            aliase=[str(a).strip() for a in (g.get("aliase") or []) if str(a).strip()],
        ))
    return Katalog(geraete=geraete)


def lade_farben(root: Path) -> dict:
    """config/farben.yaml -> {normalisierte Schreibweise: kanonische Farbe}.

    Die YAML steht andersherum (kanonisch -> Liste der Schreibweisen), weil
    sie so von Hand pflegbar ist. Der kanonische Name selbst gilt immer als
    Schreibweise seiner selbst, sonst faende die Tabelle ihre eigenen
    Schluessel nicht.
    """
    path = Path(root) / "config" / "farben.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    tabelle: dict[str, str] = {}
    for kanonisch, schreibweisen in (raw.get("farben") or {}).items():
        knorm = normalisiere(str(kanonisch))
        if not knorm:
            continue
        tabelle[knorm] = knorm
        for s in (schreibweisen or []):
            snorm = normalisiere(str(s))
            if not snorm:
                continue
            if snorm in tabelle and tabelle[snorm] != knorm:
                log.warning("farben.yaml: %r steht unter %r UND %r - erste gewinnt",
                            s, tabelle[snorm], knorm)
                continue
            tabelle[snorm] = knorm
    return tabelle


EINSTIEG_ARTEN = ("static", "sitemap", "shopify", "js")


def _parse_einstiege(raw_liste, basis_url: str, anbieter: str = "") -> list:
    gesehen = set()
    out = []
    for e in (raw_liste or []):
        if not isinstance(e, dict):
            continue
        url = str(e.get("url") or "").strip()
        if not url:
            continue
        # Relative Adresse gegen die Basis aufloesen - sonst reichte der
        # Loader sie unaufgeloest an den Collector durch, und der Abruf
        # scheiterte mit einer Meldung, die nach Netzfehler aussieht.
        if basis_url and not url.lower().startswith(("http://", "https://")):
            url = urljoin(basis_url.rstrip("/") + "/", url.lstrip("/"))
        schluessel = url.rstrip("/").lower()
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        kind = str(e.get("kind") or "static").strip()
        if kind not in EINSTIEG_ARTEN:
            # Nicht still verwerfen: ein Tippfehler hier nimmt dem Anbieter
            # seine einzige Einstiegsseite, und er faellt danach als
            # "nicht crawlbar" durch, ohne dass jemand den Grund erfaehrt.
            log.warning("geraete_quellen: %s hat Einstieg %s mit unbekannter "
                        "Art %r - als static gefuehrt", anbieter, url, kind)
            kind = "static"
        out.append(Einstieg(
            url=url, label=str(e.get("label") or "").strip(), kind=kind,
            pfadmuster=str(e.get("pfadmuster") or "").strip()))
    return out


def _als_zahl(wert, standard: float, anbieter: str, feld: str) -> float:
    """Eine unlesbare Zahl kippt nicht den Loader, sondern faellt auf den
    Standard und meldet sich. Und `0` bleibt `0`: mit `or` waere die
    ausdrueckliche Null still zum Standardwert geworden."""
    if wert is None or str(wert).strip() == "":
        return standard
    try:
        return float(str(wert).replace(",", "."))
    except (TypeError, ValueError):
        log.warning("geraete_quellen: %s hat %s=%r - kein Zahlenwert, "
                    "es gilt %s", anbieter, feld, wert, standard)
        return standard


def lade_quellen(root: Path) -> QuellenConfig:
    """config/geraete_quellen.yaml -> QuellenConfig.

    Ein Anbieter mit unbekannter `methode` wird nicht still auf einen
    Standard gebogen, sondern deaktiviert und gemeldet - sonst liefe eine
    vertippte Zeile als stumme Nulllieferung mit.
    """
    path = Path(root) / "config" / "geraete_quellen.yaml"
    if not path.exists():
        return QuellenConfig(anbieter=[])
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    out = []
    for a in (raw.get("anbieter") or []):
        if not isinstance(a, dict) or not str(a.get("name") or "").strip():
            continue
        methode = str(a.get("methode") or "ldjson").strip()
        aktiv = bool(a.get("aktiv", True))
        grund = str(a.get("grund") or "").strip()
        if methode not in METHODEN:
            log.warning("geraete_quellen: %s hat unbekannte methode %r - deaktiviert",
                        a.get("name"), methode)
            grund = grund or f"unbekannte Beschaffungsmethode {methode!r} in der Konfiguration"
            methode, aktiv = "deaktiviert", False
        typ = str(a.get("typ") or "handel").strip()
        if typ not in ANBIETER_TYPEN:
            log.warning("geraete_quellen: %s hat unbekannten typ %r - als handel gefuehrt",
                        a.get("name"), typ)
            typ = "handel"
        basis_url = str(a.get("basis_url") or "").strip()
        name = str(a["name"]).strip()
        einstiege = _parse_einstiege(a.get("einstiege"), basis_url, name)
        # Ein Anbieter, der abgefragt werden SOLL, aber keine brauchbare
        # Einstiegsseite hat, bekommt hier seinen Grund. Sonst stuende er auf
        # der Quellenseite ohne Erklaerung - und die Zusicherung "kein
        # Anbieter verschwindet stillschweigend" haenge allein an einem Test
        # gegen die ausgelieferte Datei.
        if aktiv and methode not in _NICHT_CRAWLBAR and not einstiege:
            grund = grund or ("keine Einstiegsseite konfiguriert - der "
                              "Anbieter wird nicht abgefragt")
        out.append(Anbieter(
            name=name, typ=typ,
            gruppe=str(a.get("gruppe") or "").strip(),
            netz=str(a.get("netz") or "").strip(),
            rang=int(a["rang"]) if str(a.get("rang", "")).strip().isdigit() else 99,
            methode=methode, aktiv=aktiv, grund=grund,
            eigen=bool(a.get("eigen", False)),
            shop=str(a.get("shop") or "").strip() or name,
            anzeige=str(a.get("anzeige") or "").strip() or name,
            basis_url=basis_url,
            max_produkte=int(a["max_produkte"]) if str(a.get("max_produkte", "")).strip().isdigit()
            else _MAX_PRODUKTE_STANDARD,
            rate_limit_sekunden=_als_zahl(a.get("rate_limit_sekunden"),
                                          _RATE_LIMIT_STANDARD, name,
                                          "rate_limit_sekunden"),
            hinweis=str(a.get("hinweis") or "").strip(),
            einstiege=einstiege,
        ))
    return QuellenConfig(anbieter=out)
