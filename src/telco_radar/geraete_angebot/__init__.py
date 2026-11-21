"""Angebotszählung im Browser: was ein Kunde am Messtag beim Anbieter wählen kann.

Abnahmekriterium 1, Stufe 2 (Antonio, 21.11.2026): Soll = Kombinationen Modell ×
Speicher × Tarif × Laufzeit, die der Anbieter am Messtag selbst anbietet, gezählt aus
seiner eigenen Übersicht und Auswahl, unabhängig vom Sammler. Dieses Paket ist der
Zähler: eigener Code, eigene Leser (``lesen``), eigene Wege durch die Seiten
(``wege``), eigenes Tor für robots.txt (``tor``). Es importiert nichts aus
``collect.geraete`` und nichts aus der Gegenprobe (``tests/test_geraete_angebot.py``
prüft das in einem frischen Interpreter); Klick-Karten und Selektoren des Sammlers
kommen nicht vor.

Ablauf (``scripts/angebot_zaehlen.py``, Workflow-Vorlage ``angebot.yml``): je Anbieter
ein Job, der die Smartphone-Übersicht bis zum Ende lädt (Kacheln, „mehr anzeigen“,
Herstellerfilter), dann je Modellseite die sichtbare Auswahl liest (Speicher, Tarife,
Laufzeiten; Farben nur gezählt; nicht wählbare Optionen getrennt) und das Ergebnis
als ``data/state/angebot/<messtag>-<schluessel>.json`` schreibt. Der Gerätelauf
desselben Messtags hängt es ein (``einhaengen``) – vor dem Soll/Ist-Wächter.

Messtag ist das Datum in Europe/Berlin beim Start der Zählung: die Zählung läuft ab
23:05 UTC (00:05 bzw. 01:05 Uhr in Berlin), also am selben Kalendertag wie der
Gerätelauf ab etwa 03:00 UTC, und endet vor dem Klick-Lauf (``KLICK_FENSTER``,
``TARIFWELT_FENSTER``).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

FORMAT = 1
ORDNER = "angebot"
ZONE = ZoneInfo("Europe/Berlin")

GELESEN = "gelesen"
TEILWEISE = "teilweise"
GESPERRT = "gesperrt"
GESTOERT = "gestoert"
ZEITGRENZE = "zeitgrenze"
NICHT_GELESEN = "nicht_gelesen"

KENNUNG = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
"""Wird an die Kennung des Browsers angehängt; nie verborgen, nie getauscht."""
MINDESTABSTAND_S = 5.0
"""Mindestabstand zweier Seitenaufrufe am selben Host, wenn robots.txt und die
Anbieterkonfiguration weniger verlangen."""
SEKUNDEN_JE_SEITE_RESERVE = 90.0
"""Eine Modellseite beginnt nur, wenn danach noch so viel Zeit bleibt."""


@dataclass(frozen=True)
class Anbieter:
    """Ein Anbieter des Zählers: Schlüssel (Dateiname, Matrix), Anzeigename der
    Bündel, Übersicht und Sperrfenster (Stunde UTC von, bis) anderer Läufe auf
    denselben Hosts."""

    schluessel: str
    name: str
    uebersicht: str
    sperrfenster: tuple[int, int]
    zeilen: tuple[str, ...] = ()
    abstand_konfig: str = ""

    def anbieterzeilen(self) -> tuple[str, ...]:
        """Die Zeilen der Lauf-Datei, die diese Zählung trägt."""
        return self.zeilen if self.zeilen else (self.name,)


SATURN_NETZE = {
    "o2": "Saturn/MediaMarkt · o2-Netz",
    "telekom": "Saturn/MediaMarkt · Telekom-Netz",
    "vodafone": "Saturn/MediaMarkt · Vodafone-Netz",
}
NETZ_ALIAS = {"telefonica": "o2"}
"""Der Netzfilter der Tarifwelt führt Telefónica neben o2; beides ist das o2-Netz."""

KLICK_FENSTER = (0, 7)
"""00:00-07:00 UTC: Klick-Lauf (bis etwa 03:00), Gerätelauf, Gegenprobe (Matrix, bis
160 Minuten nach dem Gerätelauf) auf denselben Hosts."""
TARIFWELT_FENSTER = (2, 7)
"""02:00-07:00 UTC: Tarifwelt-Stufe des Gerätelaufs und Gegenprobe."""

ANBIETER: dict[str, Anbieter] = {
    a.schluessel: a
    for a in (
        Anbieter(
            "telekom",
            "Telekom",
            "https://www.telekom.de/shop/geraete/smartphones",
            KLICK_FENSTER,
            abstand_konfig="Telekom",
        ),
        Anbieter(
            "vodafone",
            "Vodafone",
            "https://www.vodafone.de/privat/handys-tablets-tarife/alle-smartphones.html",
            KLICK_FENSTER,
            abstand_konfig="Vodafone",
        ),
        Anbieter(
            "o2",
            "o2",
            "https://www.o2online.de/e-shop/",
            KLICK_FENSTER,
            abstand_konfig="o2",
        ),
        Anbieter(
            "1und1",
            "1&1",
            "https://mobile.1und1.de/smartphones",
            KLICK_FENSTER,
            abstand_konfig="1&1",
        ),
        Anbieter(
            "congstar",
            "congstar",
            "https://www.congstar.de/geraete/handy/",
            KLICK_FENSTER,
            abstand_konfig="congstar",
        ),
        Anbieter(
            "tarifwelt",
            "Saturn/MediaMarkt",
            "https://tarife.mediamarkt.de/smartphones/",
            TARIFWELT_FENSTER,
            zeilen=tuple(SATURN_NETZE.values()),
            abstand_konfig="MediaMarkt/Saturn Tarifwelt",
        ),
    )
}


@dataclass
class Option:
    """Eine sichtbare Option; ``waehlbar`` falsch heißt ausgegraut/„nicht vorhanden“."""

    text: str
    wert: str
    waehlbar: bool = True


@dataclass
class Seite:
    """Eine Modellseite: was sichtbar wählbar ist. ``kombinationen`` nennt die
    wählbaren (speicher, tarif, monate[, netz]) ausdrücklich, wenn die Seite
    Abhängigkeiten zeigt; sonst gilt das Kreuzprodukt aus Speicher, Tarifen und
    Laufzeiten. ``ausserhalb`` sind sichtbare Zahlweisen außerhalb des Vergleichs
    (Einmalzahlung, Flex), gezählt, nicht multipliziert. ``ausgeschlossen`` nennt, was
    die Seite selbst ausschließt ([Tarif, Monate]); ``unvollstaendig``, wo die Seite
    mehr nennt als gelesen wurde (dann ist die Zählung dieser Seite nicht vollständig).
    Tarifwelt: ein Kombinationseintrag trägt Netz und Preis-Code als 4./5. Wert."""

    url: str
    titel: str
    status: str = NICHT_GELESEN
    grund: str | None = None
    speicher: list[Option] = field(default_factory=list)
    tarife: list[Option] = field(default_factory=list)
    laufzeiten: list[Option] = field(default_factory=list)
    farben: int | None = None
    farben_nicht_waehlbar: int | None = None
    ausserhalb: list[str] = field(default_factory=list)
    kombinationen: list[list] | None = None
    annahmen: list[str] = field(default_factory=list)
    sekunden: float | None = None
    ausgeschlossen: list[list] = field(default_factory=list)
    unvollstaendig: list[str] = field(default_factory=list)


@dataclass
class Kachel:
    """Eine Kachel der Übersicht: ein Produkt, wie der Kunde es sieht."""

    url: str
    titel: str
    paket: bool = False


@dataclass
class Zaehlung:
    """Die Zählung eines Anbieters an einem Messtag (eine Datei). ``genannt`` ist die
    Trefferzahl, die die Übersicht selbst nennt; ``uebersicht_ende`` der Beleg, dass
    sie bis zum Ende gelesen wurde (kein Nachlade-Knopf mehr, Filterzahlen erreicht);
    ``konkurrenz`` das Ergebnis der Prüfung auf parallele Läufe (``konkurrenz``)."""

    schluessel: str
    messtag: str
    gezaehlt_von: str
    gezaehlt_bis: str | None = None
    laufstatus: str = NICHT_GELESEN
    grund: str | None = None
    uebersicht: str = ""
    kacheln: list[Kachel] = field(default_factory=list)
    genannt: int | None = None
    seiten: list[Seite] = field(default_factory=list)
    sekunden_uebersicht: float | None = None
    uebersicht_ende: str | None = None
    konkurrenz: str | None = None

    def als_dict(self) -> dict:
        """Die Datei als Dict (Format ``FORMAT``)."""
        return {"format": FORMAT, **asdict(self)}


def uebersicht_pruefung(z: Zaehlung) -> tuple[bool, str]:
    """Ist die Übersicht belegt bis zum Ende gelesen? (Prüfung PR 205)

    Nennt der Anbieter eine Zahl, muss sie der Zahl gelesener Kacheln gleichen
    („Übersicht nennt 95, gelesen 1“); ohne genannte Zahl braucht es den Beleg
    ``uebersicht_ende`` (kein Nachlade-Knopf mehr, Filterzahlen erreicht). Ohne beides
    ist die Zählung nicht vollständig, das Soll kann still geschrumpft sein."""
    gelesen = len(z.kacheln)
    if z.genannt is not None and z.genannt != gelesen:
        return False, f"Übersicht nennt {z.genannt}, gelesen {gelesen}"
    if z.genannt is not None:
        return True, f"Übersicht nennt {z.genannt}, gelesen {gelesen}"
    if z.uebersicht_ende:
        return True, z.uebersicht_ende
    return False, f"kein Beleg, dass die Übersicht ganz gelesen ist ({gelesen} Kacheln)"


class AngebotsdateiFehler(ValueError):
    """Die Datei ist da, aber nicht lesbar oder hat ein fremdes Format."""


def messtag(jetzt_utc: datetime) -> str:
    """Das Datum in Europe/Berlin (ISO) zum Zeitpunkt ``jetzt_utc``."""
    return jetzt_utc.astimezone(ZONE).date().isoformat()


def sperre_ab(jetzt_utc: datetime, fenster: tuple[int, int]) -> datetime | None:
    """Beginn des nächsten Sperrfensters ab ``jetzt_utc``; ``None``, wenn
    ``jetzt_utc`` schon darin liegt (dann wird nicht gezählt)."""
    von, bis = fenster
    if von <= jetzt_utc.hour < bis:
        return None
    beginn = jetzt_utc.replace(hour=von, minute=0, second=0, microsecond=0)
    return beginn if beginn > jetzt_utc else beginn + timedelta(days=1)


def pfad(state_dir: Path, tag: str, schluessel: str) -> Path:
    """``data/state/angebot/<messtag>-<schluessel>.json``."""
    return Path(state_dir) / ORDNER / f"{tag}-{schluessel}.json"


def schreibe(state_dir: Path, zaehlung: Zaehlung) -> Path:
    """Schreibt die Datei des Anbieters für den Messtag vollständig neu."""
    ziel = pfad(state_dir, zaehlung.messtag, zaehlung.schluessel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(zaehlung.als_dict(), ensure_ascii=False, indent=1)
    zwischen = ziel.with_suffix(".json.neu")
    zwischen.write_text(text + "\n", encoding="utf-8")
    zwischen.replace(ziel)
    return ziel


def _seite(d: dict) -> Seite:
    felder = dict(d)
    for name in ("speicher", "tarife", "laufzeiten"):
        felder[name] = [Option(**o) for o in d.get(name) or ()]
    return Seite(**felder)


def aus_dict(daten: dict) -> Zaehlung:
    """Die Zählung aus einer gelesenen Datei; fremdes Format wirft."""
    if not isinstance(daten, dict) or daten.get("format") != FORMAT:
        raise AngebotsdateiFehler("unbekanntes Format")
    felder = {k: v for k, v in daten.items() if k != "format"}
    felder["kacheln"] = [Kachel(**k) for k in daten.get("kacheln") or ()]
    felder["seiten"] = [_seite(s) for s in daten.get("seiten") or ()]
    try:
        return Zaehlung(**felder)
    except TypeError as fehler:
        raise AngebotsdateiFehler(str(fehler)) from fehler


def lies(state_dir: Path, tag: str, schluessel: str) -> Zaehlung | None:
    """Die Datei des Messtags; ``None``, wenn es keine gibt."""
    ziel = pfad(state_dir, tag, schluessel)
    try:
        daten = json.loads(ziel.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as fehler:
        raise AngebotsdateiFehler(f"{ziel.name}: {fehler}") from fehler
    return aus_dict(daten)


def juengste(state_dir: Path, schluessel: str) -> str | None:
    """Der jüngste Messtag mit einer Datei dieses Anbieters."""
    tage = sorted(
        p.name[:10] for p in (Path(state_dir) / ORDNER).glob(f"*-{schluessel}.json")
    )
    return tage[-1] if tage else None
