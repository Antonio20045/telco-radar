"""Lader der Klick-Karte: liest jeden Teil der YAML-Daten und wirft mit Punktpfad.

``Kartenleser`` prüft Form und Namen; jedes fehlende, leere oder falsch geformte
Pflichtfeld und jedes unbekannte Feld wirft ``KlickkartenFehler`` mit der Stelle. Das
Format beschreibt ``klickkarte``. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .klickkartentypen import (
    DIMENSIONEN,
    GEWAEHLT,
    GRUND_ENTWEDER,
    GRUND_FEHLT,
    GRUND_FEST_UND_KNOPF,
    GRUND_KEIN_TEXT,
    GRUND_KEINE_LISTE,
    GRUND_KEINE_ZUORDNUNG,
    GRUND_MUSTER,
    GRUND_OHNE_MARKE,
    GRUND_OHNE_VARIANTE,
    GRUND_PLATZHALTER,
    GRUND_UNBEKANNT,
    PHASENFELD,
    PHASENTEILE,
    PLATZHALTER_MODELL,
    WERTFELDER,
    Antwortmuster,
    Auswahlmarke,
    Kanarie,
    KlickkartenFehler,
    Knopf,
    Phasenpfad,
    Textlesung,
    Vorbereitung,
)

KNOPFTEILE = ("selektor", "wert", "wert_in", "muster", GEWAEHLT, "fest")
MARKENTEILE = ("attribut", "wert", "passt")
VORBEREITUNGSTEILE = ("klick", "bis", "pruefe")
LESUNGSTEILE = ("selektor", "oeffnen", "schliessen")
KANARIENTEILE = ("selektor", "enthaelt", "attribut")
ANTWORTTEILE = ("url_muster", "pfade", "variante", "parameter")
_PLATZHALTER = re.compile(r"\{([^{}]*)\}")


class Kartenleser:
    """Liest Felder der Roh-Daten und wirft mit Quelle und Punktpfad."""

    def __init__(self, quelle: str) -> None:
        self.quelle = quelle

    def fehler(self, feld: str, grund: str) -> KlickkartenFehler:
        """Der Fehler an ``feld`` mit ``grund``."""
        return KlickkartenFehler(self.quelle, feld, grund)

    def zuordnung(self, wert: object, feld: str, erlaubt: tuple[str, ...]) -> Mapping:
        """``wert`` als Zuordnung mit nur erlaubten Schlüsseln."""
        if wert is None:
            raise self.fehler(feld, GRUND_FEHLT)
        if not isinstance(wert, Mapping):
            raise self.fehler(feld, GRUND_KEINE_ZUORDNUNG)
        for schluessel in wert:
            if schluessel not in erlaubt:
                raise self.fehler(stelle(feld, str(schluessel)), GRUND_UNBEKANNT)
        return wert

    def liste(self, wert: object, feld: str) -> list:
        """``wert`` als nicht leere Liste."""
        if wert is None or wert == []:
            raise self.fehler(feld, GRUND_FEHLT)
        if not isinstance(wert, list):
            raise self.fehler(feld, GRUND_KEINE_LISTE)
        return wert

    def wahlweise_text(self, daten: Mapping, schluessel: str, feld: str) -> str | None:
        """Text an ``schluessel`` oder ``None``, wenn er fehlt."""
        if daten.get(schluessel) is None:
            return None
        return self.text(daten, schluessel, feld)

    def text(self, daten: Mapping, schluessel: str, feld: str) -> str:
        """Nicht leerer Text an ``schluessel``; Zahl und Wahrheitswert als Text."""
        ort = stelle(feld, schluessel)
        wert = daten.get(schluessel)
        if isinstance(wert, bool):
            return "true" if wert else "false"
        if isinstance(wert, int | float):
            return str(wert)
        if wert is not None and not isinstance(wert, str):
            raise self.fehler(ort, GRUND_KEIN_TEXT)
        if wert is None or not wert.strip():
            raise self.fehler(ort, GRUND_FEHLT)
        return wert.strip()

    def muster(self, daten: Mapping, schluessel: str, feld: str) -> re.Pattern[str]:
        """Regulärer Ausdruck an ``schluessel``."""
        try:
            return re.compile(self.text(daten, schluessel, feld))
        except re.error as fehler:
            grund = f"{GRUND_MUSTER} ({fehler})"
            raise self.fehler(stelle(feld, schluessel), grund) from fehler

    def wahlweise_muster(
        self, daten: Mapping, schluessel: str, feld: str
    ) -> re.Pattern[str] | None:
        """Regulärer Ausdruck an ``schluessel`` oder ``None``, wenn er fehlt."""
        if daten.get(schluessel) is None:
            return None
        return self.muster(daten, schluessel, feld)

    def knoepfe(self, roh: object) -> tuple[dict[str, Knopf], Auswahlmarke | None]:
        """Die Knöpfe je Dimension und die Standardmarke."""
        knoepfe = self.zuordnung(roh, "knoepfe", (*DIMENSIONEN, GEWAEHLT))
        je_dimension = {d: self.knopf(knoepfe, d) for d in DIMENSIONEN}
        feld = f"knoepfe.{GEWAEHLT}"
        if knoepfe.get(GEWAEHLT) is not None:
            return je_dimension, self.marke(knoepfe[GEWAEHLT], feld)
        if any(k.fest is None and k.marke is None for k in je_dimension.values()):
            raise self.fehler(feld, GRUND_OHNE_MARKE)
        return je_dimension, None

    def knopf(self, knoepfe: Mapping, dimension: str) -> Knopf:
        """Die Knöpfe einer Dimension oder ihr fester Wert."""
        feld = f"knoepfe.{dimension}"
        daten = self.zuordnung(knoepfe.get(dimension), feld, KNOPFTEILE)
        if daten.get("fest") is not None:
            andere = [str(k) for k in daten if k != "fest"]
            if andere:
                raise self.fehler(stelle(feld, andere[0]), GRUND_FEST_UND_KNOPF)
            return Knopf(selektor=None, fest=self.text(daten, "fest", feld))
        marke = daten.get(GEWAEHLT)
        return Knopf(
            selektor=self.text(daten, "selektor", feld),
            wert_attribut=self.wahlweise_text(daten, "wert", feld),
            wert_in=self.wahlweise_text(daten, "wert_in", feld),
            muster=self.wahlweise_muster(daten, "muster", feld),
            marke=None if marke is None else self.marke(marke, f"{feld}.{GEWAEHLT}"),
        )

    def marke(self, roh: object, feld: str) -> Auswahlmarke:
        """Attribut mit Wert oder CSS-Selektor ``passt``."""
        daten = self.zuordnung(roh, feld, MARKENTEILE)
        if daten.get("passt") is None:
            return Auswahlmarke(
                attribut=self.text(daten, "attribut", feld),
                wert=self.text(daten, "wert", feld),
            )
        if daten.get("attribut") is not None or daten.get("wert") is not None:
            raise self.fehler(stelle(feld, "passt"), GRUND_ENTWEDER)
        return Auswahlmarke(passt=self.text(daten, "passt", feld))

    def vorbereitung(self, roh: object) -> tuple[Vorbereitung, ...]:
        """Die Zustände vor jeder Lesung; ohne Feld keine."""
        if roh is None:
            return ()
        schritte = []
        for nummer, eintrag in enumerate(self.liste(roh, "vorbereitung")):
            feld = f"vorbereitung.{nummer}"
            daten = self.zuordnung(eintrag, feld, VORBEREITUNGSTEILE)
            schritte.append(
                Vorbereitung(
                    klick=self.text(daten, "klick", feld),
                    bis=self.text(daten, "bis", feld),
                    pruefe=self.wahlweise_text(daten, "pruefe", feld),
                )
            )
        return tuple(schritte)

    def textlesung(self, roh: object) -> Textlesung:
        """Bereiche der Preiszusammenfassung und der Dialog davor."""
        feld = "zusammenfassung"
        daten = self.zuordnung(roh, feld, LESUNGSTEILE)
        return Textlesung(
            selektoren=(self.text(daten, "selektor", feld),),
            oeffnen=self.wahlweise_text(daten, "oeffnen", feld),
            schliessen=self.wahlweise_text(daten, "schliessen", feld),
        )

    def kanarie(self, roh: object) -> Kanarie:
        """Kanarienwert mit erlaubtem Platzhalter ``{modell}``."""
        feld = "kanarie"
        daten = self.zuordnung(roh, feld, KANARIENTEILE)
        enthaelt = self.text(daten, "enthaelt", feld)
        for name in _PLATZHALTER.findall(enthaelt):
            if name != PLATZHALTER_MODELL:
                raise self.fehler(f"{feld}.enthaelt", f"{GRUND_PLATZHALTER} {{{name}}}")
        return Kanarie(
            selektor=self.text(daten, "selektor", feld),
            enthaelt=enthaelt,
            attribut=self.wahlweise_text(daten, "attribut", feld),
        )

    def antwort(self, roh: object) -> Antwortmuster:
        """Die mitzuschneidende Antwort, ihre Pfade und woran sie die Variante nennt."""
        antwort = self.zuordnung(roh, "antwort", ANTWORTTEILE)
        url_muster = self.muster(antwort, "url_muster", "antwort")
        pfade = self.zuordnung(antwort.get("pfade"), "antwort.pfade", WERTFELDER)
        if not pfade:
            raise self.fehler("antwort.pfade", GRUND_FEHLT)
        variante = self._dimensionen(antwort, "variante")
        parameter = self._dimensionen(antwort, "parameter")
        if not variante and not parameter:
            raise self.fehler("antwort.variante", GRUND_OHNE_VARIANTE)
        return Antwortmuster(
            url_muster=url_muster,
            pfade={feld: self._pfad(pfade, feld) for feld in pfade},
            variante=variante,
            parameter=parameter,
        )

    def _dimensionen(self, antwort: Mapping, schluessel: str) -> dict[str, str]:
        if antwort.get(schluessel) is None:
            return {}
        ort = f"antwort.{schluessel}"
        zuordnung = self.zuordnung(antwort[schluessel], ort, DIMENSIONEN)
        return {d: self.text(zuordnung, d, ort) for d in zuordnung}

    def _pfad(self, pfade: Mapping, feld: str) -> str | Phasenpfad:
        if feld != PHASENFELD or not isinstance(pfade.get(feld), Mapping):
            return self.text(pfade, feld, "antwort.pfade")
        ort = f"antwort.pfade.{feld}"
        teile = self.zuordnung(pfade[feld], ort, PHASENTEILE)
        liste, von, bis, betrag = (self.text(teile, t, ort) for t in PHASENTEILE)
        return Phasenpfad(liste=liste, von=von, bis=bis, betrag=betrag)


def stelle(feld: str, schluessel: str) -> str:
    """Punktpfad von ``schluessel`` unter ``feld``."""
    return f"{feld}.{schluessel}" if feld else schluessel
