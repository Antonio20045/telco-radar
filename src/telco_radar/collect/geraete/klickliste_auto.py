"""Klickliste aus dem Katalog: erkannte neue Modelle kommen ohne Handarbeit hinein.

``config/klick_tageslauf.yaml`` ist von Hand gepflegt; ein neues Modell (iPhone Duo,
02.11.2026) stand darum in keiner Klickliste und bekam nie einen Einzelgerätepreis.
Hier wird der Rest abgeleitet: jedes Telefon der großen Marken (``FAMILIEN``) im
Katalog, einschließlich der Auto-Einträge, das ein Anbieter im Bestand
(``data/state/geraete_tco.json``) führt, aber in der Klickliste dieses Anbieters
fehlt, bekommt dort eine Seite. Die Adresse ist die ``quelle_url`` eines Bündels aus
dem Bestand, nie zusammengesetzt (Regel 4: IDs werden nicht geraten). Sie gilt nur,
wenn sie das Gerät nennt und eine darin genannte Speicherstufe zur SKU passt; ein
Bündel mit Tarifübersicht als Quelle liefert keine Seite. Jeder Anbieter bekommt
höchstens ``HOECHSTE_SEITEN_JE_ANBIETER`` Plätze (Gerät und Stufe), die neuesten Geräte
zuerst. Rein, ohne Netz; ``klickziele.lade_ziele`` prüft die Seiten danach wie die aus
der YAML.

Der Tarif gehört zur Seite (``TARIF_PARAMETER``): Eine Telekom-Produktseite zeigt nur
den Tarif ihrer Startadresse, die Übersicht der übrigen Tarife nur 36 Raten. Ein Gerät
bekommt darum eine Seite je Tarif, den der Bestand für dieses Gerät mit eigener Adresse
führt, jeweils auf der kleinsten Stufe (die Seite liest alle Stufen). Befund 09.11.2026:
das iPhone Duo stand bei Telekom nur mit der Adresse der ersten Fundstelle (Tarif L) in
der Liste, 24 Raten gab es für XS, S, M und XL nicht.

Ein Bündel bleibt Quelle der Adresse, auch wenn seine Messung veraltet ist
(``pruefung`` „veraltet …“): diese Liste liest nur Adresse, Gerät und Stufe. Ein Platz,
dessen Seite einmal nicht rechtzeitig gelesen wurde, bliebe sonst für immer aus der
Liste, denn nur eine Lesung erneuert das Bündel (Prüfung PR 85, 10.11.2026). Das gilt
``QUELLE_HOECHSTALTER_TAGE`` Tage vor dem jüngsten Bündel des Anbieters, nicht des
Gesamtbestands: Läse nur ein Anbieter 15 Tage lang nicht, blieben sonst alle seine
Seiten für immer weg (Nachprüfung PR 85, S1). Ein Gerät, das der Anbieter nicht mehr
führt (1&1 iPhone 15), bliebe so nicht ewig als tote Seite: nach der Frist fällt es
heraus, als Warnung im Lauf-Log (``log.warning``, wie die Hinweise in ``klickziele``).
Der Anker je Anbieter füllt nur freie Plätze: Zuerst kommen die Plätze, die auch main
zuließe (Frist ab dem jüngsten Bündel des Gesamtbestands, in main-Reihenfolge), erst
danach die nur durch ihn zugelassenen. Sonst verdrängte ein 15 Tage altes Bündel ein
frisch gelesenes Gerät (Prüfung PR 88, 10.11.2026: S25 Ultra gegen iPhone 17 bei
Telekom). Die Plätze (Gerät und Stufe, bei Telekom je Tarif die kleinste Stufe) wählt
allein die Regel von main; ``_frischere_adresse`` ersetzt danach nur die Adresse eines
Platzes durch die eines frischen Bündels derselben Seite. Unter veralteten Bündeln gilt
das jüngste (``_nutzbar``).

Zeitbudget (CLAUDE.md Regel 8): Die Liste hat keine eigene Seitengrenze, nur die
Platzgrenze. Bei Telekom hat ein Platz bis zu fünf Seiten, acht Plätze also bis zu 40;
mehr als ein Matrix-Job von 10.258 s (``klicktageslauf``) lesen kann. Den Rest trägt die
Rotation im Tageslauf (``klicktageslauf.reihenfolge``): nie gelesene Seiten zuerst, dann
die am längsten nicht gelesenen; was nicht passt, heißt ``nicht_besucht`` und kommt am
nächsten Tag zuerst dran. Eine Seitengrenze nach dem Bündelalter im Bestand (PR 85,
Stand 2d15fe31) bliebe bei einer Seite stecken, die kein Bündel mehr liefert: deren
Alter wächst, sie stünde jeden Tag vorn und verdrängte die übrigen.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ...geraete_model import Geraet, Katalog

BESTAND = Path("data") / "state" / "geraete_tco.json"
FAMILIEN = {
    "apple": re.compile(r"^iphone\b", re.IGNORECASE),
    "samsung": re.compile(r"^galaxy s\d", re.IGNORECASE),
    "google": re.compile(r"^pixel \d", re.IGNORECASE),
}
HOECHSTE_SEITEN_JE_ANBIETER = 8
TARIF_PARAMETER = {"Telekom": "tariffId"}
PRUEFUNG_VERALTET = "veraltet"
QUELLE_HOECHSTALTER_TAGE = 14
_SPEICHER_SKU = re.compile(r"^(\d+)gb-")
_SPEICHER_URL = re.compile(r"(?<![a-z0-9])(\d+)[-]?(gb|tb)(?![a-z0-9])")
_GB_JE_TB = 1024
_Schluessel = tuple[str, str, int, str]
log = logging.getLogger(__name__)


class KlicklisteAutoFehler(ValueError):
    """Der Bestand ist da, aber nicht lesbar: das Ergebnis wäre sonst still leer."""


@dataclass(frozen=True)
class AutoSeite:
    """Eine abgeleitete Seite: Anbietername aus den Quellen, Gerät, Stufe, Adresse."""

    anbieter: str
    geraet: str
    speicher_gb: int
    url: str


def ist_grosse_marke(geraet: Geraet) -> bool:
    """Telefon einer der Familien in ``FAMILIEN``; Zubehör und Tablets nicht."""
    muster = FAMILIEN.get(geraet.hersteller.strip().lower())
    return muster is not None and muster.match(geraet.modell.strip()) is not None


def leite_ab(
    root: Path, katalog: Katalog, vorhanden: set[tuple[str, str]]
) -> list[AutoSeite]:
    """Die fehlenden Seiten; ``vorhanden`` sind Paare (Anbieter, Geräte-ID) der YAML.

    Fehlt der Bestand, gibt es nichts abzuleiten (leere Liste); ist er unlesbar, wirft
    die Funktion ``KlicklisteAutoFehler``.
    """
    buendel, ausgeschieden, wie_main = _lies_buendel(root / BESTAND)
    geraete = {g.device_id: g for g in katalog.geraete if ist_grosse_marke(g)}
    _warne_anbieter_ohne_frische(buendel + ausgeschieden)
    kandidaten, frische = _kandidaten(buendel, geraete, vorhanden)
    _warne_ausgeschieden(_kandidaten(ausgeschieden, geraete, vorhanden)[0], kandidaten)
    seiten_main = _seiten(_kandidaten(wie_main, geraete, vorhanden)[0])
    seiten = _seiten(kandidaten)
    belegt = {_seite_von(s, u) for s, u in seiten_main.items()}
    nur_anker = {s: u for s, u in seiten.items() if _seite_von(s, u) not in belegt}
    plaetze = _begrenze({**seiten_main, **nur_anker}, geraete, set(seiten_main))
    return [_frischere_adresse(s, kandidaten, frische) for s in plaetze]


def _seiten(kandidaten: dict[_Schluessel, str]) -> dict[_Schluessel, str]:
    """Die Regel von main: je Adresse und je Tarif die kleinste Stufe."""
    return _je_tarif_eine_stufe(_je_adresse_eine_stufe(kandidaten))


def _seite_von(schluessel: _Schluessel, url: str) -> tuple[str, str, str]:
    """Die Seite hinter einem Platz: der Tarif, sonst die Adresse."""
    anbieter, gid, _, tarif = schluessel
    return anbieter, gid, tarif or url


def _kandidaten(
    buendel: list[dict], geraete: dict[str, Geraet], vorhanden: set[tuple[str, str]]
) -> tuple[dict[_Schluessel, str], set[_Schluessel]]:
    """Adresse je (Anbieter, Gerät, Stufe, Tarif); die erste Nennung gilt, frische
    Bündel stehen vorn. ``frische`` sind die Schlüssel mit mindestens einem frischen
    Bündel."""
    kandidaten: dict[_Schluessel, str] = {}
    frische: set[_Schluessel] = set()
    for eintrag in buendel:
        paar = _paar(eintrag, geraete)
        if paar is None:
            continue
        geraet, speicher = paar
        anbieter = _anbieter(eintrag)
        url = str(eintrag.get("quelle_url") or "").strip()
        if not anbieter or (anbieter, geraet.device_id) in vorhanden:
            continue
        if speicher not in geraet.speicher or not _passt(url, geraet, speicher):
            continue
        schluessel = (
            anbieter,
            geraet.device_id,
            speicher,
            _tarif_kennung(anbieter, url),
        )
        kandidaten.setdefault(schluessel, url)
        if not _ist_veraltet(eintrag):
            frische.add(schluessel)
    return kandidaten, frische


def _warne_ausgeschieden(
    ausgeschieden: dict[_Schluessel, str], kandidaten: dict[_Schluessel, str]
) -> None:
    """Warnung je Anbieter für Plätze (Gerät und Stufe), die nur wegen der Grenze
    ``QUELLE_HOECHSTALTER_TAGE`` keine Seite bekommen."""
    belegt = {s[:3] for s in kandidaten}
    verloren: dict[str, set[tuple[str, int]]] = {}
    for anbieter, gid, speicher, _ in ausgeschieden:
        if (anbieter, gid, speicher) not in belegt:
            verloren.setdefault(anbieter, set()).add((gid, speicher))
    for anbieter, plaetze in sorted(verloren.items()):
        namen = ", ".join(f"{gid} {gb} GB" for gid, gb in sorted(plaetze))
        log.warning(
            "Klickliste auto: %s verliert %d Plätze, deren jüngstes Bündel mehr als "
            "%d Tage vor dem jüngsten Bündel dieses Anbieters liegt (kein Ausfalltag "
            "mehr, Gerät nicht mehr angeboten oder Seite tot?): %s",
            anbieter,
            len(plaetze),
            QUELLE_HOECHSTALTER_TAGE,
            namen,
        )


def _warne_anbieter_ohne_frische(buendel: list[dict]) -> None:
    """Warnung für jeden Anbieter, dessen Bündel alle veraltet sind: Seine Liste bleibt
    (Frist je Anbieter), aber er wird nicht mehr gelesen."""
    frisch = {_anbieter(b) for b in buendel if not _ist_veraltet(b)}
    letzte: dict[str, date | None] = {}
    for eintrag in buendel:
        if name := _anbieter(eintrag):
            tage = [d for d in (letzte.get(name), _datum(eintrag)) if d]
            letzte[name] = max(tage, default=None)
    for name in sorted(set(letzte) - frisch):
        datum = letzte[name]
        log.warning(
            "Klickliste auto: %s hat kein frisches Bündel mehr (jüngstes: %s); seine "
            "Seiten bleiben in der Liste, solange die Bündel nutzbar sind, werden aber "
            "nicht mehr gemessen (Sperre, Strukturbruch, Anbieter nicht mehr gelesen?)",
            name,
            datum.isoformat() if datum else "ohne Datum",
        )


def _frischere_adresse(
    seite: AutoSeite, kandidaten: dict[_Schluessel, str], frische: set[_Schluessel]
) -> AutoSeite:
    """Die Adresse eines Platzes aus einem frischen Bündel derselben Seite (bei Tarif:
    derselbe Tarif; sonst dieselbe Adresse), darunter die kleinste Stufe. Der Platz
    bleibt der, den die Platzgrenze gezählt hat, mit seiner Stufe (die Seite liest alle
    Stufen, ``speicher_gb`` ist nur die Bezeichnung); nur die Adresse ändert sich, und
    nur, wo ein frisches Bündel die bisherige Wahl verdrängt."""
    tarif = _tarif_kennung(seite.anbieter, seite.url)

    def gleiche_seite(schluessel: _Schluessel) -> bool:
        anbieter, gid, _, kennung = schluessel
        if (anbieter, gid) != (seite.anbieter, seite.geraet):
            return False
        return kennung == tarif if tarif else kandidaten[schluessel] == seite.url

    gewaehlt = (seite.anbieter, seite.geraet, seite.speicher_gb, tarif)
    beste = min(
        filter(gleiche_seite, kandidaten),
        key=lambda s: (s not in frische, s[2]),
        default=gewaehlt,
    )
    if beste == gewaehlt or beste not in frische or gewaehlt in frische:
        return seite
    return AutoSeite(seite.anbieter, seite.geraet, seite.speicher_gb, kandidaten[beste])


def _tarif_kennung(anbieter: str, url: str) -> str:
    """Der Tarif, den die Adresse wählt; leer, wo die Seite den Tarif nicht aus der
    Adresse nimmt (``TARIF_PARAMETER``)."""
    parameter = TARIF_PARAMETER.get(anbieter)
    if parameter is None:
        return ""
    werte = parse_qs(urlsplit(url).query).get(parameter)
    return werte[0].strip() if werte else ""


def _je_tarif_eine_stufe(kandidaten: dict[_Schluessel, str]) -> dict[_Schluessel, str]:
    """Wählt die Adresse den Tarif, genügt je (Anbieter, Gerät, Tarif) die kleinste
    Stufe: die Seite liest alle Stufen. Ohne Tarifkennung bleibt jede Stufe."""
    einzeln: dict[tuple[str, str, str], _Schluessel] = {}
    for schluessel in sorted(kandidaten, key=lambda s: s[2]):
        anbieter, gid, _, tarif = schluessel
        if tarif:
            einzeln.setdefault((anbieter, gid, tarif), schluessel)
    waehlt_tarif = set(einzeln.values())
    return {s: u for s, u in kandidaten.items() if not s[3] or s in waehlt_tarif}


def _je_adresse_eine_stufe(
    kandidaten: dict[_Schluessel, str],
) -> dict[_Schluessel, str]:
    """Steht eine Adresse für mehrere Stufen (Geräteseite ohne Stufe in der Adresse),
    bleibt die kleinste: der Crawler klickt alle Varianten einer Seite ohnehin."""
    einzeln: dict[tuple[str, str, str], _Schluessel] = {}
    for schluessel in sorted(kandidaten, key=lambda s: s[2]):
        anbieter, gid, _, _ = schluessel
        einzeln.setdefault((anbieter, gid, kandidaten[schluessel]), schluessel)
    return {s: kandidaten[s] for s in einzeln.values()}


def _lies_buendel(pfad: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Nutzbare Bündel, die ``_nutzbar`` ausscheidet, und die davon, die main auch
    zuließe."""
    try:
        text = pfad.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], [], []
    except OSError as fehler:
        raise KlicklisteAutoFehler(f"{pfad}: nicht lesbar ({fehler})") from fehler
    try:
        daten = json.loads(text)
    except json.JSONDecodeError as fehler:
        raise KlicklisteAutoFehler(f"{pfad}: kein JSON ({fehler})") from fehler
    liste = daten.get("buendel") if isinstance(daten, dict) else None
    if not isinstance(liste, list):
        raise KlicklisteAutoFehler(f"{pfad}: Feld buendel fehlt")
    return _nutzbar([b for b in liste if isinstance(b, dict)])


def _ist_veraltet(eintrag: dict) -> bool:
    return str(eintrag.get("pruefung") or "").startswith(PRUEFUNG_VERALTET)


def _nutzbar(buendel: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Frische Bündel, dann die veralteten, deren Messung höchstens
    ``QUELLE_HOECHSTALTER_TAGE`` hinter dem jüngsten Bündel *desselben Anbieters*
    liegt, das jüngste zuerst (die erste Nennung eines Platzes gilt); dazu die
    ausgeschiedenen und die nutzbaren, die auch main zuließe (Frist ab dem jüngsten
    Bündel des Gesamtbestands)."""
    stand: dict[str, date] = {}
    for eintrag in buendel:
        datum = _datum(eintrag)
        if datum is not None:
            name = _anbieter(eintrag)
            stand[name] = max(stand.get(name, datum), datum)
    frist = timedelta(days=QUELLE_HOECHSTALTER_TAGE)
    gesamt = max(stand.values(), default=None)

    def jung_genug(eintrag: dict, anker: date | None) -> bool:
        datum = _datum(eintrag)
        return datum is not None and anker is not None and datum >= anker - frist

    frisch = [b for b in buendel if not _ist_veraltet(b)]
    alt = [b for b in buendel if _ist_veraltet(b)]
    alt.sort(key=lambda b: _datum(b) or date.min, reverse=True)
    nutzbar = [b for b in alt if jung_genug(b, stand.get(_anbieter(b)))]
    wie_main = [b for b in alt if jung_genug(b, gesamt)]
    rest = [b for b in alt if not jung_genug(b, stand.get(_anbieter(b)))]
    return frisch + nutzbar, rest, frisch + wie_main


def _anbieter(eintrag: dict) -> str:
    return str(eintrag.get("anbieter") or "").strip()


def _datum(eintrag: dict) -> date | None:
    try:
        return date.fromisoformat(str(eintrag.get("abgerufen_am") or "")[:10])
    except ValueError:
        return None


def _paar(eintrag: dict, geraete: dict[str, Geraet]) -> tuple[Geraet, int] | None:
    """Gerät und Speicherstufe der SKU, über die längste Katalog-ID davor."""
    sku = str(eintrag.get("sku_id") or "")
    treffer: tuple[Geraet, int] | None = None
    for gid, geraet in geraete.items():
        if not sku.startswith(gid + "-"):
            continue
        stufe = _SPEICHER_SKU.match(sku[len(gid) + 1 :])
        if stufe is None:
            continue
        if treffer is None or len(gid) > len(treffer[0].device_id):
            treffer = (geraet, int(stufe.group(1)))
    return treffer


def _passt(url: str, geraet: Geraet, speicher: int) -> bool:
    """Die Adresse nennt das Gerät (nicht nur eine Tarifübersicht), Stufe stimmt."""
    if not url.startswith("https://"):
        return False
    adresse = url.lower().split("#")[0]
    kurz = geraet.device_id.removeprefix(
        re.sub(r"[^a-z0-9]+", "-", geraet.hersteller.lower()) + "-"
    )
    for name in {geraet.device_id, kurz}:
        if re.search(
            rf"(?<![a-z0-9-]){re.escape(name)}(?=$|[/.?#]|-\d+-?[gt]b)", adresse
        ):
            break
    else:
        return False
    pfad = adresse.split("?")[0]
    stufen = {
        int(zahl) * (_GB_JE_TB if einheit == "tb" else 1)
        for zahl, einheit in _SPEICHER_URL.findall(pfad)
    }
    return not stufen or stufen == {speicher}


def _begrenze(
    kandidaten: dict[_Schluessel, str],
    geraete: dict[str, Geraet],
    wie_main: set[_Schluessel],
) -> list[AutoSeite]:
    """Höchstens ``HOECHSTE_SEITEN_JE_ANBIETER`` Plätze (Gerät und Stufe) je Anbieter,
    neueste Geräte zuerst; die Tarifseiten eines Platzes zählen zusammen als einer.
    Zuerst kommen die Plätze, die auch main zuließe (``wie_main``, in main-Reihenfolge),
    erst danach die nur durch den Anker je Anbieter zugelassenen (Prüfung PR 88, M1)."""

    def rang(schluessel: _Schluessel) -> tuple:
        anbieter, gid, speicher, tarif = schluessel
        g = geraete[gid]
        return (
            anbieter,
            schluessel not in wie_main,
            -(g.generation or 0),
            g.marktstart == "",
            gid,
            speicher,
            tarif,
        )

    plaetze: dict[str, set[tuple[str, int]]] = {}
    ergebnis: list[AutoSeite] = []
    for schluessel in sorted(kandidaten, key=rang):
        anbieter, gid, speicher, _ = schluessel
        belegt = plaetze.setdefault(anbieter, set())
        if (gid, speicher) not in belegt and len(belegt) >= HOECHSTE_SEITEN_JE_ANBIETER:
            continue
        belegt.add((gid, speicher))
        ergebnis.append(AutoSeite(anbieter, gid, speicher, kandidaten[schluessel]))
    return ergebnis
