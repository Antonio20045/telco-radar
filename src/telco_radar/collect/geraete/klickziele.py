"""Ziele der Klick-Erkundung: je Anbieter ein bis zwei Produktseiten aus der Config.

``config/klick_erkundung.yaml`` nennt je Anbieter einen Schlüssel (Ordnername und
Workflow-Eingabe), den Namen aus ``config/geraete_quellen.yaml`` und höchstens
``HOECHSTE_SEITEN`` Seiten mit Gerät und Adresse. ``lade_ziele`` prüft jede Zeile gegen
Quellen und Katalog (``geraete_config``): der Anbieter steht in den Quellen, das Gerät
im Katalog, der Speicher beim Gerät, die Adresse ist https (http nur für
``LOKALE_HOSTS``, den Trockenlauf) und liegt auf dem Host der ``basis_url``. Eine
Seite darf ``weiter`` tragen (``Weiter``): Selektor und, wenn angegeben, sichtbarer Text
genau eines Knopfs oder Links zum nächsten Schritt der Bestellstrecke
(``klickfolgeseite``). Jeder Verstoß wirft ``ErkundungszielFehler`` mit der Stelle; ein
Ziel wird nie still übergangen. User-Agent und Abrufabstand kommen aus den Quellen.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from ...geraete_config import lade_katalog, lade_quellen
from ...geraete_model import Katalog
from .robots import host_von

DATEI = Path("config") / "klick_erkundung.yaml"
HOECHSTE_SEITEN = 2
ALLE = "alle"
SCHEMA = "https"
LOKALE_HOSTS = frozenset({"127.0.0.1", "localhost"})
WEITER_FELDER = frozenset({"selektor", "text"})


class ErkundungszielFehler(ValueError):
    """Die Erkundungskonfiguration ist unvollständig oder widerspricht den Quellen."""


@dataclass(frozen=True)
class Weiter:
    """Der eine Knopf oder Link zur Folgeseite: CSS-Selektor, erwarteter Text."""

    selektor: str
    text: str | None = None


@dataclass(frozen=True)
class Seitenziel:
    """Eine Produktseite: Gerät aus dem Katalog, Speicherstufe, Adresse, Weiter, Modell.

    ``modell`` ist der Modellname aus dem Katalog für ``{modell}`` im Kanarienwert.
    """

    geraet: str
    speicher_gb: int | None
    adresse: str
    weiter: Weiter | None = None
    modell: str | None = None


@dataclass(frozen=True)
class Erkundungsziel:
    """Ein Anbieter mit seinen Seiten, Kennung und eigenem Abrufabstand."""

    schluessel: str
    name: str
    seiten: tuple[Seitenziel, ...]
    kennung: str | None
    rate_limit_sekunden: float


def lade_ziele(root: Path) -> list[Erkundungsziel]:
    """Alle Ziele aus ``config/klick_erkundung.yaml``, geprüft an Quellen, Katalog."""
    pfad = root / DATEI
    try:
        roh = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as fehler:
        raise ErkundungszielFehler(f"{DATEI}: nicht lesbar ({fehler})") from fehler
    eintraege = roh.get("anbieter") if isinstance(roh, dict) else None
    if not isinstance(eintraege, list) or not eintraege:
        raise ErkundungszielFehler(f"{DATEI}: keine Anbieter")
    quellen, katalog = lade_quellen(root), lade_katalog(root)
    ziele: list[Erkundungsziel] = []
    for stelle, eintrag in enumerate(eintraege):
        ort = f"{DATEI}, anbieter[{stelle}]"
        if not isinstance(eintrag, dict):
            raise ErkundungszielFehler(f"{ort}: keine Zuordnung")
        schluessel = _text(eintrag, "schluessel", ort)
        name = _text(eintrag, "name", ort)
        anbieter = quellen.nach_name(name)
        if anbieter is None:
            raise ErkundungszielFehler(f"{ort}: {name!r} fehlt in geraete_quellen.yaml")
        roh_seiten = eintrag.get("seiten")
        if not isinstance(roh_seiten, list) or not roh_seiten:
            raise ErkundungszielFehler(f"{ort}: keine Seiten")
        if len(roh_seiten) > HOECHSTE_SEITEN:
            grund = f"{len(roh_seiten)} Seiten, höchstens {HOECHSTE_SEITEN}"
            raise ErkundungszielFehler(f"{ort}: {grund}")
        seiten = tuple(
            _seite(s, f"{ort}.seiten[{i}]", katalog, anbieter.basis_url)
            for i, s in enumerate(roh_seiten)
        )
        ziele.append(
            Erkundungsziel(
                schluessel=schluessel,
                name=anbieter.name,
                seiten=seiten,
                kennung=anbieter.user_agent if anbieter.user_agent else None,
                rate_limit_sekunden=anbieter.rate_limit_sekunden,
            )
        )
    schluessel_alle = [z.schluessel for z in ziele]
    doppelt = {s for s in schluessel_alle if schluessel_alle.count(s) > 1}
    if doppelt:
        raise ErkundungszielFehler(f"{DATEI}: Schlüssel doppelt: {sorted(doppelt)}")
    return ziele


def waehle(ziele: list[Erkundungsziel], auswahl: str) -> list[Erkundungsziel]:
    """Die Ziele zu ``auswahl``: ``alle`` oder Schlüssel mit Komma getrennt.

    Ein unbekannter Schlüssel wirft ``ErkundungszielFehler``, statt still weniger zu
    erkunden.
    """
    gewuenscht = [s.strip() for s in auswahl.split(",") if s.strip()]
    if not gewuenscht or gewuenscht == [ALLE]:
        return list(ziele)
    bekannt = {z.schluessel: z for z in ziele}
    unbekannt = [s for s in gewuenscht if s not in bekannt]
    if unbekannt:
        liste = ", ".join(bekannt)
        raise ErkundungszielFehler(
            f"unbekannter Anbieter {', '.join(unbekannt)}; bekannt: {liste}"
        )
    return [bekannt[s] for s in dict.fromkeys(gewuenscht)]


def _seite(roh: object, ort: str, katalog: Katalog, basis_url: str) -> Seitenziel:
    if not isinstance(roh, dict):
        raise ErkundungszielFehler(f"{ort}: keine Zuordnung")
    geraet_id = _text(roh, "geraet", ort)
    adresse = _text(roh, "url", ort)
    geraet = katalog.nach_id(geraet_id)
    if geraet is None:
        raise ErkundungszielFehler(f"{ort}: {geraet_id!r} fehlt im Katalog")
    speicher = roh.get("speicher_gb")
    if speicher is not None and speicher not in (geraet.speicher or []):
        raise ErkundungszielFehler(f"{ort}: {speicher} GB nicht beim Gerät {geraet_id}")
    teile = urlsplit(adresse)
    if teile.scheme != SCHEMA and teile.hostname not in LOKALE_HOSTS:
        raise ErkundungszielFehler(f"{ort}: Adresse ohne {SCHEMA}: {adresse}")
    if host_von(adresse) != host_von(basis_url):
        grund = f"Host {host_von(adresse)} ist nicht {host_von(basis_url)}"
        raise ErkundungszielFehler(f"{ort}: {grund}")
    weiter = _weiter(roh.get("weiter"), ort)
    return Seitenziel(geraet_id, speicher, adresse, weiter, geraet.modell)


def _weiter(roh: object, ort: str) -> Weiter | None:
    if roh is None:
        return None
    ort = f"{ort}.weiter"
    if not isinstance(roh, dict):
        raise ErkundungszielFehler(f"{ort}: keine Zuordnung")
    fremd = sorted(set(roh) - WEITER_FELDER)
    if fremd:
        raise ErkundungszielFehler(f"{ort}: unbekanntes Feld {', '.join(fremd)}")
    text = _text(roh, "text", ort) if "text" in roh else None
    return Weiter(_text(roh, "selektor", ort), text)


def _text(daten: dict, feld: str, ort: str) -> str:
    wert = daten.get(feld)
    if not isinstance(wert, str) or not wert.strip():
        raise ErkundungszielFehler(f"{ort}: {feld} fehlt oder ist leer")
    return wert.strip()
