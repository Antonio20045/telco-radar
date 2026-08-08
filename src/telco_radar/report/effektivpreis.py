"""Was ein Tarif wirklich kostet - und was an der Zahl fehlt.

Warum eine Zahl nicht reicht
----------------------------
"6 Monate 9,99 €, danach 29,99 €" ist weder 9,99 € noch 29,99 €, sondern
24,99 €. Genau dieser Aufbau macht die Angebote dieses Marktes
unvergleichbar, und er ist kein Zufall: der beworbene Preis ist der der
ersten Phase, der bezahlte der Durchschnitt.

    Effektivpreis/Monat =
      ( Σ Grundgebühren aller Preisphasen über den Horizont
        + Anschlusspreis
        + Gerätezuzahlung
        − Cashback und Wechselbonus
      ) / Horizont

Der Horizont ist FEST auf 24 Monate, auch fuer Tarife ohne Mindestlaufzeit.
Nicht, weil ein Flex-Tarif 24 Monate laeuft, sondern weil ein Vergleich
einen gemeinsamen Nenner braucht: ein Anschlusspreis von 39,99 € verteilt
sich auf 24 Monate anders als auf einen. Wer den Horizont je Tarif aus der
Laufzeit nimmt, vergleicht zwei verschiedene Rechnungen und nennt das
Ergebnis Preisvergleich.

Warum immer DREI Werte
----------------------
Der Effektivpreis allein belohnt aggressive Drosselung. Ein Tarif mit 5 GB
und danach 64 KBit/s ist pro Monat billig und pro Gigabyte teuer, und ab
dem sechsten Gigabyte ist er unbenutzbar. Deshalb steht neben dem
Effektivpreis immer der Preis je GB **und** die Qualitaetsmerkmale
(Drosselwert, Volumenautomatik, Laufzeitbindung). Eine Rangliste nach
Effektivpreis allein waere eine Rangliste der Drosselung.

Eine fehlende Komponente ist eine LUECKE, keine Null
----------------------------------------------------
Wenn kein Anschlusspreis bekannt ist, heisst das nicht "kostenlos". Der
Datensatz traegt die Luecke mit, die Seite zeigt sie, und ein Tarif mit
Luecken wird nicht stillschweigend gegen einen vollstaendigen gestellt.
Dieselbe Haltung wie ueberall in diesem Projekt: lieber eine sichtbare
Luecke als eine unsichtbare Erfindung.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..tarif_model import Preisphase, Tarif

# Der gemeinsame Nenner jedes Vergleichs. Siehe Modul-Docstring.
VERGLEICHSMONATE = 24


@dataclass
class Qualitaetsflag:
    """Ein Merkmal, das der Preis allein nicht zeigt."""

    schluessel: str
    text: str
    gut: Optional[bool] = None   # True gut, False schlecht, None neutral


@dataclass
class Effektivpreis:
    monatlich: Optional[float] = None
    horizont: int = VERGLEICHSMONATE
    gesamt: Optional[float] = None
    bestandteile: dict = field(default_factory=dict)
    luecken: list[str] = field(default_factory=list)
    preis_je_gb: Optional[float] = None
    flags: list[Qualitaetsflag] = field(default_factory=list)

    @property
    def belastbar(self) -> bool:
        """Ohne Grundgebuehr ist die Zahl keine Aussage."""
        return self.monatlich is not None and "Grundpreis" not in self.luecken


def phasensumme(phasen: list[Preisphase], horizont: int) -> Optional[float]:
    """Die Summe der Monatsentgelte ueber den Horizont.

    Der Kern der Rechnung. Eine Phase ohne Ende laeuft bis zum Horizont;
    eine Phase, die darueber hinausreicht, wird gekappt.
    """
    if not phasen:
        return None
    summe = 0.0
    abgedeckt = 0
    for phase in sorted(phasen, key=lambda p: p.von_monat):
        monate = phase.monate(horizont)
        if monate <= 0:
            continue
        summe += monate * phase.betrag
        abgedeckt += monate
    if abgedeckt <= 0:
        return None
    if abgedeckt < horizont:
        # Der Rest laeuft zum letzten bekannten Preis weiter. Das ist die
        # vorsichtige Annahme: der letzte Preis eines Tarifs ist der
        # Normalpreis, nicht der Rabattpreis.
        letzter = sorted(phasen, key=lambda p: p.von_monat)[-1]
        summe += (horizont - abgedeckt) * letzter.betrag
    return round(summe, 2)


def _flags(tarif: Tarif) -> list[Qualitaetsflag]:
    flags: list[Qualitaetsflag] = []

    if tarif.datenvolumen_gb == float("inf"):
        flags.append(Qualitaetsflag("volumen", "Unbegrenztes Datenvolumen", True))
    elif tarif.datenvolumen_gb is not None:
        menge = int(tarif.datenvolumen_gb) if \
            tarif.datenvolumen_gb == int(tarif.datenvolumen_gb) \
            else tarif.datenvolumen_gb
        flags.append(Qualitaetsflag("volumen", f"{menge} GB Datenvolumen", None))

    if tarif.drossel_down is not None:
        # Unter 1 MBit/s ist die Verbindung fuer die meisten Anwendungen
        # unbrauchbar - das ist der Unterschied zwischen "langsamer" und
        # "vorbei", und er gehoert neben den Preis.
        hart = tarif.drossel_down < 1000
        wert = (f"{tarif.drossel_down / 1000:g} MBit/s" if tarif.drossel_down >= 1000
                else f"{tarif.drossel_down:g} KBit/s")
        flags.append(Qualitaetsflag(
            "drossel", f"Nach dem Volumen nur noch {wert}", not hart))

    if tarif.volumen_automatik:
        flags.append(Qualitaetsflag("automatik", tarif.volumen_automatik, True))

    if tarif.laufzeit_monate == 0:
        flags.append(Qualitaetsflag("laufzeit", "Ohne Mindestlaufzeit", True))
    elif tarif.laufzeit_monate:
        flags.append(Qualitaetsflag(
            "laufzeit", f"{tarif.laufzeit_monate} Monate Bindung", False))

    if tarif.allnet_flat:
        flags.append(Qualitaetsflag("allnet", "Allnet-Flat enthalten", True))
    return flags


def rechne(tarif: Tarif, *, cashback: Optional[float] = None,
           wechselbonus: Optional[float] = None,
           geraetezuzahlung: Optional[float] = None,
           horizont: int = VERGLEICHSMONATE) -> Effektivpreis:
    """Der Effektivpreis eines Tarifs, mit allem, was daran fehlt."""
    ergebnis = Effektivpreis(horizont=horizont, flags=_flags(tarif))

    grund = phasensumme(tarif.preisphasen, horizont)
    if grund is None and tarif.grundgebuehr is not None:
        grund = round(tarif.grundgebuehr * horizont, 2)
    if grund is None:
        ergebnis.luecken.append("Grundpreis")
    else:
        ergebnis.bestandteile["Monatsentgelte"] = grund

    # Fehlt eine Komponente, wird sie als LUECKE vermerkt und nicht als 0
    # angenommen. "Nicht bekannt" und "kostenlos" sind zwei verschiedene
    # Aussagen, und nur eine davon ist belegt.
    if tarif.anschlusspreis is not None:
        ergebnis.bestandteile["Anschlusspreis"] = tarif.anschlusspreis
    elif tarif.anschlusspreis_nach_erstattung is not None:
        ergebnis.bestandteile["Anschlusspreis"] = \
            tarif.anschlusspreis_nach_erstattung
    else:
        ergebnis.luecken.append("Anschlusspreis")

    if geraetezuzahlung is not None:
        ergebnis.bestandteile["Gerätezuzahlung"] = geraetezuzahlung
    if cashback:
        ergebnis.bestandteile["Cashback"] = -abs(cashback)
    if wechselbonus:
        ergebnis.bestandteile["Wechselbonus"] = -abs(wechselbonus)
    if cashback is None and wechselbonus is None:
        ergebnis.luecken.append("Cashback/Wechselbonus")

    if ergebnis.bestandteile:
        ergebnis.gesamt = round(sum(ergebnis.bestandteile.values()), 2)
        ergebnis.monatlich = round(ergebnis.gesamt / horizont, 2)

    if ergebnis.monatlich is not None and tarif.datenvolumen_gb:
        if tarif.datenvolumen_gb == float("inf"):
            ergebnis.preis_je_gb = 0.0
        else:
            ergebnis.preis_je_gb = round(
                ergebnis.monatlich / tarif.datenvolumen_gb, 3)
    return ergebnis


# --------------------------------------------------------------------------- #
# Die Fair-Value-Linie der Positionskarte
# --------------------------------------------------------------------------- #

def regression(punkte: list[tuple[float, float]]
               ) -> Optional[tuple[float, float]]:
    """Ausgleichsgerade y = a + b*x ueber die Punktwolke.

    Sie ist die "faire" Erwartung: was ein Tarif bei diesem Datenvolumen
    ueblicherweise kostet. Punkte darueber sind relativ teuer, Punkte
    darunter relativ guenstig - und DAS ist die Aussage der Karte, nicht die
    absolute Hoehe.

    Weniger als drei Punkte ergeben keine Gerade, sondern eine Verbindung.
    Eine senkrechte Wolke (alle Tarife mit demselben Volumen) auch nicht.
    """
    sauber = [(x, y) for x, y in punkte
              if x is not None and y is not None
              and x not in (float("inf"), float("-inf"))]
    n = len(sauber)
    if n < 3:
        return None
    sx = sum(x for x, _ in sauber)
    sy = sum(y for _, y in sauber)
    sxx = sum(x * x for x, _ in sauber)
    sxy = sum(x * y for x, y in sauber)
    nenner = n * sxx - sx * sx
    if abs(nenner) < 1e-9:
        return None
    b = (n * sxy - sx * sy) / nenner
    a = (sy - b * sx) / n
    return round(a, 4), round(b, 4)
