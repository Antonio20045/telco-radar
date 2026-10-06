"""Status, Befund und Grenzen der Prüfstelle für Geräte-Bündel (Datenkonzept, 7).

Jedes Bündel bekommt vor der Veröffentlichung genau einen Status, ``gueltig``,
``quarantaene`` oder ``veraltet``; ``unbekannt`` heißt, die Prüfstelle ist gescheitert,
und das Bündel fällt aus jedem Vergleich (CLAUDE.md, Clean Code 4). Jede Regel aus
Abschnitt 9, die an einem Bündel nicht besteht, hinterlässt einen ``Befund`` mit Nummer
und Satz:

    verletzt        die Regel ist verletzt; ihre Folge (``FOLGE``) setzt den Status
    luecke          ein Pflichtwert fehlt und bleibt benannte Lücke, nie 0
    nicht_pruefbar  die Daten der Regel fehlen heute (Gerätesumme der Seite, UVP,
                    SIM-only-Preis, Echo, Beleg, Vortag); weder gültig noch Quarantäne
                    aus diesem Grund, aber je Regel gezählt

Die Regeln selbst stehen in ``geraete_regeln``. Der Status steht im Bündelsatz von
``geraete_tco.json`` im Feld ``pruefung`` (``Pruefergebnis.als_feld``); ein Satz ohne
dieses Feld ist nie geprüft worden und zählt wie vor der Prüfstelle.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, fields

from ..tco_model import Aktion, Buendel, aktionen_aus, kosten_ueber

GUELTIG = "gueltig"
QUARANTAENE = "quarantaene"
VERALTET = "veraltet"
UNBEKANNT = "unbekannt"
STATUS = (GUELTIG, QUARANTAENE, VERALTET)

VERLETZT = "verletzt"
LUECKE = "luecke"
NICHT_PRUEFBAR = "nicht_pruefbar"

FELD_PRUEFUNG = "pruefung"
FELD_GERAETESUMME = "geraet_summe"
FELD_ECHO = "echo"
FELD_BELEG_VARIANTE = "beleg_variante"

UVP_UNTEN = 0.85
UVP_OBEN = 1.30
AUSREISSER_VORTAG = 0.15
ERLAUBTE_RATENLAUFZEITEN = (6, 12, 24, 36)
RECHEN_TOLERANZ_EUR = 1.00
CENT = 0.005
MIN_BUENDEL_GLEICHWERT = 3

REGELN = {
    1: "Rechenprobe",
    2: "Gerätesumme zur UVP",
    3: "Tarif zum SIM-only-Preis",
    4: "Volumen im Tarifnamen",
    5: "Preis je Speicher",
    6: "Ratenlaufzeit",
    7: "Tarifbindung",
    8: "Preisphasen",
    9: "Text und Antwort",
    10: "Aktion abgelaufen",
    11: "Sprung zum Vortag",
    12: "Gleicher Wert überall",
    13: "Beleglink",
    14: "Pflichtfelder",
    15: "Zeitraum",
    16: "Frische",
}
FOLGE = {n: QUARANTAENE for n in REGELN} | {10: VERALTET, 16: VERALTET}

PFLICHT_GETRENNT = (
    ("geraet_zuzahlung", "Zuzahlung"),
    ("geraet_monatsrate", "Rate"),
    ("laufzeit_monate", "Ratenlaufzeit"),
    ("tarif_monatlich", "Tarif"),
    ("tarif_bindung_monate", "Tarifbindung"),
    ("anschlusspreis", "Anschluss"),
)
PFLICHT_EIN_VERTRAG = (
    ("geraet_zuzahlung", "Zuzahlung"),
    ("buendel_monatlich", "Bündelbetrag"),
    ("laufzeit_monate", "Ratenlaufzeit"),
    ("tarif_bindung_monate", "Tarifbindung"),
    ("anschlusspreis", "Anschluss"),
)
_LISTENFELDER = ("rabatte", "aktionen", "tarif_phasen", FELD_PRUEFUNG)
_SKALARE = tuple(f.name for f in fields(Buendel) if f.name not in _LISTENFELDER)


@dataclass(frozen=True)
class Befund:
    """Eine Regel, die an einem Bündel nicht bestanden hat."""

    regel: int
    ergebnis: str
    satz: str


@dataclass
class Pruefergebnis:
    """Alle Befunde eines Bündels; ohne Befund hat jede Regel bestanden."""

    befunde: list[Befund] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Quarantäne vor veraltet vor gültig, je nach ``FOLGE`` der Verletzungen."""
        folgen = {FOLGE[b.regel] for b in self.je(VERLETZT)}
        return next((s for s in (QUARANTAENE, VERALTET) if s in folgen), GUELTIG)

    def je(self, ergebnis: str) -> list[Befund]:
        """Die Befunde mit diesem Ergebnis, nach Regelnummer."""
        return sorted(
            (b for b in self.befunde if b.ergebnis == ergebnis), key=lambda b: b.regel
        )

    def als_feld(self) -> dict:
        """Das Feld ``pruefung`` im Bündelsatz von ``geraete_tco.json``."""
        return {
            "status": self.status,
            "gruende": [{"regel": b.regel, "satz": b.satz} for b in self.je(VERLETZT)],
            "luecken": sorted({b.regel for b in self.je(LUECKE)}),
            "nicht_pruefbar": sorted({b.regel for b in self.je(NICHT_PRUEFBAR)}),
        }


@dataclass(frozen=True)
class Kontext:
    """Was die Regeln außer dem Bündel brauchen; fehlt etwas, ist sie nicht prüfbar.

    ``sim_only`` SIM-only-Monatspreise (``geraete_regeln.sim_only_tabelle``), ``uvp``
    SKU → UVP, ``volumen`` ``tarif_id`` → gemessenes Volumen in GB, ``vortag`` Bündel-ID
    → Messung des letzten Messtags davor. ``frisch``, ``geraet_von`` (SKU → Gerät und
    Speicher) und ``volumen_im_namen`` kommen aus der Stufe, die sie definiert.
    """

    heute: str
    frisch: Callable[[str, str], bool] | None = None
    geraet_von: Callable[[str], tuple[str, int | None]] | None = None
    volumen_im_namen: Callable[[str], float | None] | None = None
    sim_only: Mapping[str, float] = field(default_factory=dict)
    uvp: Mapping[str, float] = field(default_factory=dict)
    volumen: Mapping[str, float] = field(default_factory=dict)
    vortag: Mapping[str, dict] = field(default_factory=dict)


def buendel_aus_satz(satz: Mapping) -> Buendel:
    """Ein gespeicherter Bündelsatz als ``Buendel``; wirft wie dessen Konstruktor."""
    werte = {f: satz[f] for f in _SKALARE if satz.get(f) is not None}
    return Buendel(**werte, aktionen=aktionen_aus(satz.get("aktionen")))


def abgelaufene_aktionen(aktionen: Iterable[Aktion], heute: str) -> list[Aktion]:
    """Eingerechnete Aktionen, die der Anbieter vor ``heute`` befristet hat (10)."""
    return [a for a in aktionen if a.eingerechnet and not a.gilt_am(heute)]


def geraetepreis(b: Buendel) -> float | None:
    """Was das Gerät im Bündel kostet: Anzahlung plus alle Raten; ein Vertrag ohne
    eigene Rate (1&1) über seine Laufzeit. None, wenn ein Posten fehlt."""
    if b.geraeteraten is not None:
        return b.geraeteraten.gesamt
    if b.buendel_monatlich is not None and b.laufzeit_monate:
        return kosten_ueber(b, b.laufzeit_monate).gesamt
    return None


def pflichtfelder(b: Buendel) -> tuple[tuple[str, str], ...]:
    """Die Pflichtfelder der Preisform des Bündels (Regel 14)."""
    return PFLICHT_EIN_VERTRAG if b.buendel_monatlich is not None else PFLICHT_GETRENNT


def status_aus_feld(pruefung: object) -> str | None:
    """Der Status eines gespeicherten Felds ``pruefung``; None, wenn nie geprüft.

    Ein Feld, das keinen der drei Status trägt, ist ``unbekannt``.
    """
    if pruefung is None:
        return None
    status = pruefung.get("status") if isinstance(pruefung, Mapping) else None
    return status if status in STATUS else UNBEKANNT


def eur(betrag: float) -> str:
    """„1.234,56 €“."""
    text = f"{betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} €"


def gb(menge: float) -> str:
    """„50 GB“ oder „unbegrenzt“."""
    return "unbegrenzt" if menge == float("inf") else f"{menge:g} GB"


def datum(iso: str) -> str:
    """„2026-09-15“ → „15.09.2026“; anderes bleibt, wie es ist."""
    teile = iso.split("-")
    return ".".join(reversed(teile)) if len(teile) == 3 else iso


def aufzaehlung(teile: list[str]) -> str:
    """„6, 12 und 24“."""
    if len(teile) < 2:
        return "".join(teile)
    return f"{', '.join(teile[:-1])} und {teile[-1]}"
