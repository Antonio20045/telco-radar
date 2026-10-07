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

Die Regeln selbst stehen in ``geraete_regeln``. Im Bündelsatz von ``geraete_tco.json``
steht nur der ``Vermerk`` im Feld ``pruefung``, ein kurzer Text: der Status und die
Nummern der verletzten Regeln (``"quarantaene 3 5"``), bei ``unbekannt`` der Fehler
(``"unbekannt RuntimeError: …"``). Die Sätze je Regel kommen aus ``REGELN``; Lücken und
„nicht prüfbar“ zählen nur die Kennzahlen des Laufs. Ein Satz ohne dieses Feld ist nie
geprüft worden und zählt wie vor der Prüfstelle.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, fields

from ..tarif_model import buendelphasen_aus
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
BUENDEL_NACHLASS = {"o2": 5.00}
"""Belegter Nachlass des Anbieters auf den Tarif im Bündel (normalisierter Name → €
im Monat), sonst 0: o2 stellt den Bündel-Tarifpreis selbst 5 € unter SIM-only,
„attraktiver monatlicher Rabatt auf deinen Tarif“ (``analyze/tco_buendel.py``,
Modulkopf, 21.09.2026). Regel 3 misst gegen SIM-only minus diesen Nachlass."""
GERAETETARIF_MERKMAL = {"o2": "Plus"}
"""Wort im Namen eines Tarifs, den der Anbieter nur mit Gerät führt (normalisierter Name
→ Wort). o2s „… Plus …“ trägt die Tarif-ID des Grundtarifs, ist aber ein eigener Tarif:
zum iPhone 17 Pro kostet Unlimited M Plus 19,99 € statt 39,99 €, SIM-only Unlimited M
29,99 € (o2-Seite am 07.10.2026). Für Regel 3 fehlt sein SIM-only-Preis."""
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
        """Alle Befunde als Zuordnung: Grundlage für Vermerk und Kennzahlen."""
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
    return Buendel(**werte, **listen_aus_satz(satz))


def listen_aus_satz(satz: Mapping) -> dict:
    """Die Listenfelder eines gespeicherten Bündelsatzes als Objekte: Aktionen und die
    am Bündel gemessenen Preisphasen. Eine Stelle für Prüfstelle und Seite."""
    return {
        "aktionen": aktionen_aus(satz.get("aktionen")),
        "tarif_phasen": buendelphasen_aus(satz.get("tarif_phasen")),
    }


def abgelaufene_aktionen(aktionen: Iterable[Aktion], heute: str) -> list[Aktion]:
    """Eingerechnete Aktionen, die der Anbieter vor ``heute`` befristet hat (10)."""
    return [a for a in aktionen if a.eingerechnet and not a.gilt_am(heute)]


def buendel_zaehlt(
    herleitung: str, aktionen: Iterable[Aktion], heute: str, pruefung: object
) -> bool:
    """Darf das Bündel Δ, Referenz oder Sieger stellen (Notbremse, Schritte 1 und 7)?

    Nur gemessen (ohne ``herleitung``), ohne abgelaufene eingerechnete Aktion und mit
    Status gültig oder nie geprüft. Seite und Abnahme teilen diese eine Definition.
    """
    status = lies_vermerk(pruefung).status
    return (
        not herleitung.strip()
        and not abgelaufene_aktionen(aktionen, heute)
        and status in (None, GUELTIG)
    )


def satz_zaehlt(satz: Mapping, heute: str) -> bool:
    """``buendel_zaehlt`` für einen gespeicherten Bündelsatz (``geraete_tco.json``)."""
    return buendel_zaehlt(
        str(satz.get("herleitung") or ""),
        aktionen_aus(satz.get("aktionen")),
        heute,
        satz.get(FELD_PRUEFUNG),
    )


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


def fehlerfeld(exc: BaseException) -> dict:
    """Das Feld eines Bündels, an dem die Prüfstelle gescheitert ist."""
    return {"status": UNBEKANNT, "fehler": f"{type(exc).__name__}: {exc}"}


def status_aus_feld(feld: object) -> str | None:
    """Der Status eines Felds aus ``als_feld`` oder ``fehlerfeld``; None ohne Feld.

    Ein Feld, das keinen der drei Status trägt, ist ``unbekannt``.
    """
    if feld is None:
        return None
    status = feld.get("status") if isinstance(feld, Mapping) else None
    return status if status in STATUS else UNBEKANNT


@dataclass(frozen=True)
class Vermerk:
    """Der gespeicherte Vermerk eines Bündels: Status, verletzte Regeln, Fehler.

    ``status`` ist None, wenn das Bündel nie geprüft worden ist.
    """

    status: str | None
    regeln: tuple[int, ...] = ()
    fehler: str = ""

    def als_text(self) -> str:
        """``"gueltig"``, ``"quarantaene 3 5"`` oder ``"unbekannt <Fehler>"``."""
        if self.status == UNBEKANNT:
            return f"{UNBEKANNT} {self.fehler}".strip()
        return " ".join([str(self.status), *map(str, self.regeln)])


def vermerk(feld: Mapping) -> Vermerk:
    """Der Vermerk eines Felds aus ``als_feld`` oder ``fehlerfeld``."""
    status = status_aus_feld(feld) or UNBEKANNT
    if status == UNBEKANNT:
        return Vermerk(UNBEKANNT, fehler=str(feld.get("fehler") or ""))
    regeln = sorted({int(g["regel"]) for g in feld.get("gruende") or []})
    return Vermerk(status, tuple(regeln))


def lies_vermerk(text: object) -> Vermerk:
    """Der Vermerk aus dem Feld ``pruefung`` eines gespeicherten Bündelsatzes.

    Ohne Feld ist der Status None; ein unlesbarer Vermerk ist ``unbekannt``.
    """
    if text is None:
        return Vermerk(None)
    status, _, rest = str(text).partition(" ")
    if status == UNBEKANNT:
        return Vermerk(UNBEKANNT, fehler=rest)
    teile = rest.split()
    if status not in STATUS or not all(t.isdigit() for t in teile):
        return Vermerk(UNBEKANNT, fehler=f"Vermerk unlesbar: {text}")
    return Vermerk(status, tuple(int(t) for t in teile))


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
