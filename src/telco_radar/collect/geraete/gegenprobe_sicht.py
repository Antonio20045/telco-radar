"""Leser der Gegenprobe: sichtbarer Text des Preisbereichs → ``Sichtwerte``.

Jeder Leser bekommt den ``innerText`` des Preisbereichs, den der Browser nach der
Kundenwahl zeigt (``gegenprobe_browser``), und sonst nichts: keine
Schnittstellenantwort, kein Quelltext. Was nicht im Text steht, bleibt None. Die
Beschriftungen stammen aus den Seiten vom 20.11.2026 (Fixtures unter
``tests/fixtures/gegenprobe/``); Groß- und Kleinschreibung zählt nicht, weil die Seiten
sie per CSS setzen.

Abgeleitet wird nur, was die Seite als Summe ihrer eigenen Posten zeigt, und das steht
am Leser: Telekom nennt Tarif und „Gesamtpreis monatlich“ (Rate = Differenz) und die
„Einmalige Zahlung inkl. Bereitstellung“ (Anzahlung = Differenz), Vodafone den
„Angebotspreis“ aus Rate und Tarif (Tarif = Differenz).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from ...gegenprobe import Sichtwerte

_ZAHL = (
    r"(\d{1,3}(?:\.\d{3})*(?:,(?:\d{1,2}|[–-]{1,2}))?|\d+(?:,(?:\d{1,2}|[–-]{1,2}))?)"
)
_EURO = _ZAHL + r"\s*€"
_I = re.IGNORECASE


def betrag(text: str) -> float:
    """„1.199“, „29,50“, „26,–“ und „0,-“ als Zahl (Euro)."""
    ganz, _, rest = text.strip().partition(",")
    ganz = ganz.replace(".", "")
    cent = rest if rest.isdigit() else "0"
    return round(int(ganz) + int(cent.ljust(2, "0")[:2]) / 100, 2)


def _nach(text: str, beschriftung: str) -> float | None:
    """Der erste Betrag hinter ``beschriftung`` (Regex, ohne Zeilengrenze)."""
    treffer = re.search(beschriftung + r"[^\d€]{0,40}?" + _EURO, text, _I)
    return betrag(treffer.group(1)) if treffer else None


def _differenz(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round(a - b, 2)


def telekom(text: str) -> Sichtwerte:
    """Telekom-Produktseite: Ratenwahl, Tarifkarte, „Einmalige Zahlung“, „Gesamtpreis
    monatlich“. Die Rate ist die gewählte Option, deren Betrag die Differenz aus
    Gesamtpreis monatlich und Tarif ist; ihre Zahl und Anzahlung stehen daneben."""
    s = Sichtwerte()
    tarif = re.search(
        r"\n([^\n]+)\n\s*" + _EURO + r"\s*\n\s*zzgl\.\s*" + _EURO + r"[^\n]*einmalig",
        text,
        _I,
    )
    if tarif:
        s.tarif_name = tarif.group(1).strip()
        s.tarif_monatlich = betrag(tarif.group(2))
        s.roh["Tarif"] = f"{tarif.group(2)} €"
    einmalig = _nach(text, r"Einmalige\s+Zahlung")
    bereitstellung = _nach(text, r"inkl\.\s*Bereitstellung")
    monatlich = _nach(text, r"Gesamtpreis\s+monatlich")
    s.anschlusspreis = bereitstellung
    for name, wert in (
        ("Einmalige Zahlung", einmalig),
        ("Bereitstellung", bereitstellung),
        ("Gesamtpreis monatlich", monatlich),
    ):
        if wert is not None:
            s.roh[name] = _euro_text(wert)
    rate = _differenz(monatlich, s.tarif_monatlich)
    optionen = [
        (betrag(m.group(1)), int(m.group(2)), betrag(m.group(3)))
        for m in re.finditer(
            _EURO + r"\s*mtl\.\s*x\s*(\d+)\s*\+\s*" + _EURO + r"\s*Anzahlung", text, _I
        )
    ]
    passend = [o for o in optionen if rate is not None and abs(o[0] - rate) < 0.005]
    if len(passend) == 1:
        s.geraet_monatsrate, s.laufzeit_monate, anzahlung = passend[0]
        s.roh["Gewählte Rate"] = (
            f"{_euro_text(s.geraet_monatsrate)} mtl. x {s.laufzeit_monate}"
        )
        s.geraet_zuzahlung = _differenz(einmalig, bereitstellung)
        if s.geraet_zuzahlung is None:
            s.geraet_zuzahlung = anzahlung
    return s


def o2(text: str) -> Sichtwerte:
    """o2-Produktseite, Kasten „Dein Angebot“: Gerät monatlich, Ratenzahlung, Tarif
    monatlich, Gerät Anzahlung, einmaliger Anschlusspreis (der erste Betrag; ein
    durchgestrichener steht dahinter), Versandkosten."""
    s = Sichtwerte()
    s.geraet_monatsrate = _nach(text, r"(?m)^\s*Gerät\s+monatlich:")
    raten = re.search(r"Ratenzahlung:?\s*(\d+)\s*Monate", text, _I)
    s.laufzeit_monate = int(raten.group(1)) if raten else None
    s.tarif_monatlich = _nach(text, r"(?m)^\s*Tarif\s+monatlich:")
    s.geraet_zuzahlung = _nach(text, r"Gerät\s+Anzahlung:?")
    s.anschlusspreis = _nach(text, r"einmaliger\s+Anschlusspreis:?")
    s.versand = _nach(text, r"Versandkosten:?")
    _roh(
        s,
        {
            "Gerät monatlich": s.geraet_monatsrate,
            "Tarif monatlich": s.tarif_monatlich,
            "Gerät Anzahlung": s.geraet_zuzahlung,
            "Anschlusspreis": s.anschlusspreis,
            "Versandkosten": s.versand,
        },
    )
    if s.laufzeit_monate is not None:
        s.roh["Ratenzahlung"] = f"{s.laufzeit_monate} Monate"
    return s


def congstar(text: str) -> Sichtwerte:
    """congstar-Produktseite: Kostenübersicht („Tarif“, „Gerät … in den ersten N
    Monaten“, „Summe einmalig“, Versand) und die gewählte Zahlweise mit Anzahlung.
    Der Anschlusspreis ist „Summe einmalig“ ohne die Anzahlung der Zahlweise."""
    s = Sichtwerte()
    _, _, uebersicht = text.rpartition("Summe 1.")
    geraet = re.search(
        r"\nGerät\s*\n\s*" + _EURO + r"\s*\n\s*in den ersten (\d+) Monaten",
        uebersicht,
        _I,
    )
    s.tarif_monatlich = _nach(uebersicht, r"\nTarif\s*\n")
    if geraet:
        s.geraet_monatsrate = betrag(geraet.group(1))
        s.laufzeit_monate = int(geraet.group(2))
    einmalig = _nach(uebersicht, r"Summe\s+einmalig")
    s.versand = _nach(uebersicht, r"zzgl\.") if "Versand" in uebersicht else None
    zahlweisen = [
        (int(m.group(1)), betrag(m.group(2)), betrag(m.group(3)))
        for m in re.finditer(
            r"(\d+)\s*mtl\.\s*Zahlungen\s*Monatliche Kosten\s*"
            + _EURO
            + r"\s*Anzahlung\s*"
            + _EURO,
            text,
            _I,
        )
    ]
    passend = [
        z
        for z in zahlweisen
        if z[0] == s.laufzeit_monate
        and s.geraet_monatsrate is not None
        and abs(z[1] - s.geraet_monatsrate) < 0.005
    ]
    if len(passend) == 1:
        s.geraet_zuzahlung = passend[0][2]
        s.anschlusspreis = _differenz(einmalig, s.geraet_zuzahlung)
    _roh(
        s,
        {
            "Tarif": s.tarif_monatlich,
            "Gerät": s.geraet_monatsrate,
            "Anzahlung": s.geraet_zuzahlung,
            "Summe einmalig": einmalig,
            "Versandkosten": s.versand,
        },
    )
    if s.laufzeit_monate is not None:
        s.roh["Zahlweise"] = f"{s.laufzeit_monate} mtl. Zahlungen"
    return s


def tarifwelt(text: str) -> Sichtwerte:
    """Saturn/MediaMarkt Tarifwelt, Karte „Mein Tarif“: Gerät einmalig, Tarif monatlich,
    Anschlussgebühr; keine Geräterate (die Tarifwelt verkauft das Gerät einmalig)."""
    s = Sichtwerte()
    s.geraet_zuzahlung = _nach(text, r"Gerät\s+einmalig")
    s.tarif_monatlich = _nach(text, r"Tarif\s+monatlich")
    anschluss = re.search(_EURO + r"\s*Anschlussgebühr", text, _I)
    s.anschlusspreis = betrag(anschluss.group(1)) if anschluss else None
    s.versand = _nach(text, r"Lieferung\s*\+?")
    _roh(
        s,
        {
            "Gerät einmalig": s.geraet_zuzahlung,
            "Tarif monatlich": s.tarif_monatlich,
            "Anschlussgebühr": s.anschlusspreis,
            "Lieferung": s.versand,
        },
    )
    return s


VODAFONE_TRENNER = "\n== Tarifauswahl ==\n"
"""Trennt den Text der Produktseite (Rate) von dem der Tarifauswahl (Summe)."""


def vodafone(text: str) -> Sichtwerte:
    """Vodafone, zwei Seiten: Produktseite (gewählte Raten, „Pro Monat“ = Rate,
    „Einmal“) und Tarifauswahl (Tarifname, „Angebotspreis“ = Rate + Tarif Monat 1,
    Anschlusspreis). Der Tarif ist die Differenz aus Angebotspreis und Rate."""
    produkt, _, tarifseite = text.partition(VODAFONE_TRENNER)
    s = Sichtwerte()
    raten = re.search(r"Gewählt:\s*(\d+)\s*Raten", produkt, _I)
    s.laufzeit_monate = int(raten.group(1)) if raten else None
    s.geraet_monatsrate = _nach(produkt, r"Pro\s+Monat")
    s.geraet_zuzahlung = _nach(tarifseite or produkt, r"\bEinmal\b")
    angebot = _nach(tarifseite, r"Angebotspreis")
    if angebot is None:
        angebot = _nach(tarifseite, r"Pro\s+Monat")
    s.tarif_monatlich = _differenz(angebot, s.geraet_monatsrate)
    name = re.search(r"^(Mobil\s+\S+|GigaMobil[^\n]*?)\s+mit\b", tarifseite, re.M)
    s.tarif_name = name.group(1).strip() if name else None
    if re.search(r"Kein\s+Anschlusspreis", tarifseite, _I):
        s.anschlusspreis = 0.0
    else:
        s.anschlusspreis = _nach(tarifseite, r"\n\s*Anschlusspreis")
    s.versand = _nach(tarifseite or produkt, r"Versand")
    _roh(
        s,
        {
            "Rate pro Monat": s.geraet_monatsrate,
            "Einmal": s.geraet_zuzahlung,
            "Angebotspreis (Rate + Tarif)": angebot,
            "Anschlusspreis": s.anschlusspreis,
            "Versand": s.versand,
        },
    )
    if s.laufzeit_monate is not None:
        s.roh["Raten"] = f"{s.laufzeit_monate} Raten"
    return s


def einsundeins(text: str) -> Sichtwerte:
    """1&1-Produktseite, Preisübersicht: Ratenzahlung Hardware (N Monate), Tarifname
    und „Monatliche Gesamtkosten“ (ein Betrag für Tarif und Gerät)."""
    s = Sichtwerte()
    raten = re.search(r"Ratenzahlung\s+Hardware:\s*(\d+)\s*Monate", text, _I)
    s.laufzeit_monate = int(raten.group(1)) if raten else None
    s.buendel_monatlich = _nach(text, r"Monatliche\s+Gesamtkosten")
    name = re.search(r"(1&1\s+[^\n€]*?)\s+" + _EURO, text)
    s.tarif_name = name.group(1).strip() if name else None
    _roh(s, {"Monatliche Gesamtkosten": s.buendel_monatlich})
    if s.laufzeit_monate is not None:
        s.roh["Ratenzahlung Hardware"] = f"{s.laufzeit_monate} Monate"
    return s


def _euro_text(wert: float) -> str:
    zahl = f"{wert:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{zahl} €"


def _roh(s: Sichtwerte, werte: dict[str, float | None]) -> None:
    for name, wert in werte.items():
        if wert is not None:
            s.roh[name] = _euro_text(wert)


@dataclass(frozen=True)
class Leser:
    """Der Leser eines Anbieters und die Posten, die sein Weg zeigen muss."""

    lies: Callable[[str], Sichtwerte]
    pflicht: tuple[str, ...]


GETRENNT = (
    "tarif_monatlich",
    "geraet_monatsrate",
    "laufzeit_monate",
    "geraet_zuzahlung",
    "anschlusspreis",
)
LESER: dict[str, Leser] = {
    "telekom": Leser(telekom, GETRENNT),
    "o2": Leser(o2, GETRENNT),
    "congstar": Leser(congstar, GETRENNT),
    "vodafone": Leser(vodafone, GETRENNT),
    "1-1": Leser(einsundeins, ("buendel_monatlich", "laufzeit_monate")),
    "saturn-mediamarkt-telekom-netz": Leser(
        tarifwelt, ("tarif_monatlich", "geraet_zuzahlung", "anschlusspreis")
    ),
    "saturn-mediamarkt-vodafone-netz": Leser(
        tarifwelt, ("tarif_monatlich", "geraet_zuzahlung", "anschlusspreis")
    ),
    "saturn-mediamarkt-o2-netz": Leser(
        tarifwelt, ("tarif_monatlich", "geraet_zuzahlung", "anschlusspreis")
    ),
}
"""Leser je Anbieter-Schlüssel des Bündels (``gegenprobe.anbieter_aus_id``)."""
