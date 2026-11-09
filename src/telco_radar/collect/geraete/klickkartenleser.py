"""Lader der Klick-Karte: liest jeden Teil der YAML-Daten und wirft mit Punktpfad.

``Kartenleser`` prüft Form und Namen; jedes fehlende, leere oder falsch geformte
Pflichtfeld und jedes unbekannte Feld wirft ``KlickkartenFehler`` mit der Stelle. Das
Format beschreibt ``klickkarte``. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .klickkartenteile import (
    BELEGLINK_KONFIGURATION,
    GRUND_ART,
    GRUND_NICHT_ZUR_ART,
    GRUND_WEITER_DIMENSION,
    RATENPLAN_ARTEN,
    RATENPLAN_OHNE_RABATTPHASE,
    RATENPLAN_TARIFCODE,
    TARIFSLUG_ARTEN,
    TARIFSLUG_SEITENPARAMETER,
    Ratenplanregel,
    Tarifslugregel,
)
from .klickkartentypen import (
    ADRESSATTRIBUT,
    DIMENSIONEN,
    GEWAEHLT,
    GRUND_ADRESSEN_UND_KNOPF,
    GRUND_DIMENSION,
    GRUND_EINE_ADRESSDIMENSION,
    GRUND_EINZIGE,
    GRUND_ENTWEDER,
    GRUND_FEHLT,
    GRUND_FEST_UND_KNOPF,
    GRUND_KACHEL_BEREICH,
    GRUND_KACHEL_KNOPF,
    GRUND_KACHEL_MARKE,
    GRUND_KACHEL_MUSTER,
    GRUND_KEIN_TEXT,
    GRUND_KEINE_LISTE,
    GRUND_KEINE_ZUORDNUNG,
    GRUND_KLICKEN_KNOPF,
    GRUND_MUSTER,
    GRUND_OHNE_MARKE,
    GRUND_PLATZHALTER,
    GRUND_UNBEKANNT,
    GRUND_WEITER_ADRESSEN,
    GRUND_WEITER_KLICK,
    PLATZHALTER_MODELL,
    Adressen,
    AusgelistetUrl,
    Auswahlmarke,
    Kanarie,
    KlickkartenFehler,
    Knopf,
    Textlesung,
    Vorbereitung,
    Weiterschritt,
)
from .klickquellenleser import lies_bildfolge, lies_textmuster, texte

KNOPFTEILE = (
    "selektor",
    "wert",
    "wert_in",
    "muster",
    GEWAEHLT,
    "fest",
    "adressen",
    "andere_farbe",
)
ADRESSTEILE = ("selektor", "attribut", "parameter")
MARKENTEILE = ("attribut", "wert", "passt", "einzige")
VORBEREITUNGSTEILE = ("klick", "bis", "pruefe", "darf_fehlen")
LESUNGSTEILE = ("selektor", "oeffnen", "schliessen", "ohne", "muster")
KANARIENTEILE = ("selektor", "enthaelt", "attribut", "ausgelistet_url")
AUSGELISTETTEILE = ("host", "pfad")
RATENPLANTEILE = ("art", "teil", "muster", "nachweis")
RATENPLAN_TEILE_JE_ART = {
    RATENPLAN_TARIFCODE: ("teil", "muster"),
    RATENPLAN_OHNE_RABATTPHASE: ("nachweis",),
}
TARIFSLUGTEILE = ("art", "parameter", "beleglink")
KACHELN = "kacheln"
KLICKEN = "klicken"
WEITERTEILE = ("selektor", "text", KACHELN, KLICKEN)
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

    def schalter(self, daten: Mapping, schluessel: str, feld: str) -> bool:
        """Ein wahlweiser Wahrheitswert, ohne Angabe falsch."""
        wert = daten.get(schluessel, False)
        if not isinstance(wert, bool):
            raise self.fehler(stelle(feld, schluessel), "erwartet true oder false")
        return wert

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

    def knoepfe(
        self, roh: object, kacheln: object = None
    ) -> tuple[dict[str, Knopf], Auswahlmarke | None]:
        """Die Knöpfe je Dimension und die Standardmarke; ``kacheln`` braucht keine."""
        knoepfe = self.zuordnung(roh, "knoepfe", (*DIMENSIONEN, GEWAEHLT))
        je_dimension = {d: self.knopf(knoepfe, d) for d in DIMENSIONEN}
        mit_adressen = [d for d, k in je_dimension.items() if k.adressen is not None]
        if len(mit_adressen) > 1:
            ort = f"knoepfe.{mit_adressen[1]}.adressen"
            raise self.fehler(ort, GRUND_EINE_ADRESSDIMENSION)
        feld = f"knoepfe.{GEWAEHLT}"
        if knoepfe.get(GEWAEHLT) is not None:
            return je_dimension, self.marke(knoepfe[GEWAEHLT], feld)
        if any(
            k.selektor is not None and k.marke is None and d != kacheln
            for d, k in je_dimension.items()
        ):
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
        if daten.get("adressen") is not None:
            andere = [str(k) for k in daten if k != "adressen"]
            if andere:
                raise self.fehler(stelle(feld, andere[0]), GRUND_ADRESSEN_UND_KNOPF)
            return Knopf(selektor=None, adressen=self.adressen(daten, feld))
        marke = daten.get(GEWAEHLT)
        return Knopf(
            selektor=self.text(daten, "selektor", feld),
            wert_attribut=self.wahlweise_text(daten, "wert", feld),
            wert_in=self.wahlweise_text(daten, "wert_in", feld),
            muster=self.wahlweise_muster(daten, "muster", feld),
            marke=None if marke is None else self.marke(marke, f"{feld}.{GEWAEHLT}"),
            andere_farbe=self.wahlweise_text(daten, "andere_farbe", feld),
        )

    def adressen(self, daten: Mapping, feld: str) -> Adressen:
        """Selektor, Attribut und Parameter der Adressen einer Dimension."""
        ort = stelle(feld, "adressen")
        teile = self.zuordnung(daten["adressen"], ort, ADRESSTEILE)
        attribut = self.wahlweise_text(teile, "attribut", ort)
        return Adressen(
            selektor=self.text(teile, "selektor", ort),
            parameter=self.text(teile, "parameter", ort),
            attribut=ADRESSATTRIBUT if attribut is None else attribut,
        )

    def marke(self, roh: object, feld: str) -> Auswahlmarke:
        """Attribut mit Wert oder CSS-Selektor ``passt``."""
        daten = self.zuordnung(roh, feld, MARKENTEILE)
        if daten.get("einzige") is not None:
            if daten["einzige"] is not True or len(daten) > 1:
                raise self.fehler(stelle(feld, "einzige"), GRUND_EINZIGE)
            return Auswahlmarke(einzige=True)
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
                    darf_fehlen=self.schalter(daten, "darf_fehlen", feld),
                )
            )
        return tuple(schritte)

    def textlesung(self, roh: object) -> Textlesung:
        """Bereiche der Preiszusammenfassung, Ausschlüsse, Muster und Dialog."""
        feld = "zusammenfassung"
        daten = self.zuordnung(roh, feld, LESUNGSTEILE)
        ohne = () if daten.get("ohne") is None else texte(self, daten, "ohne", feld)
        return Textlesung(
            selektoren=texte(self, daten, "selektor", feld),
            oeffnen=self.wahlweise_text(daten, "oeffnen", feld),
            schliessen=self.wahlweise_text(daten, "schliessen", feld),
            ohne=ohne,
            muster=lies_textmuster(self, daten.get("muster")),
        )

    def weiter(
        self, roh: object, knoepfe: Mapping[str, Knopf], textlesung: Textlesung
    ) -> Weiterschritt | None:
        """Der Klick in die Bestellstrecke und die Dimension der Folgeseite."""
        if roh is None:
            return None
        feld = "weiter"
        daten = self.zuordnung(roh, feld, WEITERTEILE)
        if KLICKEN in daten and KACHELN in daten:
            raise self.fehler(feld, GRUND_WEITER_DIMENSION)
        art = KLICKEN if KLICKEN in daten else KACHELN
        dimension = self.text(daten, art, feld)
        if dimension not in DIMENSIONEN:
            raise self.fehler(f"{feld}.{art}", f"{GRUND_DIMENSION} {dimension}")
        if any(k.adressen is not None for k in knoepfe.values()):
            raise self.fehler(feld, GRUND_WEITER_ADRESSEN)
        knopf, ort = knoepfe[dimension], f"knoepfe.{dimension}"
        if art == KLICKEN:
            if knopf.selektor is None:
                raise self.fehler(ort, GRUND_KLICKEN_KNOPF)
            self._ohne_zweiten_klick(textlesung)
        else:
            self._kacheln(knopf, ort, textlesung)
        return Weiterschritt(
            selektor=self.text(daten, "selektor", feld),
            text=self.text(daten, "text", feld),
            **{art: dimension},
        )

    def _kacheln(self, knopf: Knopf, ort: str, textlesung: Textlesung) -> None:
        """Kacheln: Selektor ohne Marke, Bereich gleich den Kacheln, Muster darin."""
        if knopf.selektor is None:
            raise self.fehler(ort, GRUND_KACHEL_KNOPF)
        if knopf.marke is not None:
            raise self.fehler(f"{ort}.{GEWAEHLT}", GRUND_KACHEL_MARKE)
        if textlesung.selektoren != (knopf.selektor,):
            raise self.fehler("zusammenfassung.selektor", GRUND_KACHEL_BEREICH)
        self._ohne_zweiten_klick(textlesung)
        eigene = [f for f, m in textlesung.muster.items() if m.selektor is not None]
        if eigene:
            ort = f"zusammenfassung.muster.{eigene[0]}"
            raise self.fehler(ort, GRUND_KACHEL_MUSTER)

    def _ohne_zweiten_klick(self, textlesung: Textlesung) -> None:
        klicks = [n for n in ("oeffnen", "schliessen") if getattr(textlesung, n)]
        if klicks:
            raise self.fehler(f"zusammenfassung.{klicks[0]}", GRUND_WEITER_KLICK)

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
            ausgelistet_url=self.ausgelistet_url(daten.get("ausgelistet_url")),
        )

    def ratenplan(self, roh: object) -> Ratenplanregel | None:
        """Die Ratenplan-Regel der Karte oder ``None`` ohne das Feld."""
        if roh is None:
            return None
        daten = self.zuordnung(roh, "ratenplan", RATENPLANTEILE)
        art = self._art(daten, "ratenplan", RATENPLAN_ARTEN)
        self._nur_teile(daten, "ratenplan", RATENPLAN_TEILE_JE_ART[art])
        if art == RATENPLAN_TARIFCODE:
            return Ratenplanregel(
                art=art,
                teil=self.text(daten, "teil", "ratenplan"),
                muster=self.muster(daten, "muster", "ratenplan"),
            )
        return Ratenplanregel(
            art=art, nachweis=self.text(daten, "nachweis", "ratenplan")
        )

    def bildfolge(
        self, roh: object
    ) -> tuple[dict[str, str], dict[str, str], frozenset[str]]:
        """Selektoren je Schritt der Bildfolge, die Gründe der Schritte ohne Bild und
        die Schritte, deren Bild den gemessenen Wert nennen muss."""
        return lies_bildfolge(self, roh)

    def tarifslug(self, roh: object) -> Tarifslugregel | None:
        """Die Tarifslug-Regel der Karte oder ``None`` ohne das Feld."""
        if roh is None:
            return None
        daten = self.zuordnung(roh, "tarifslug", TARIFSLUGTEILE)
        art = self._art(daten, "tarifslug", TARIFSLUG_ARTEN)
        parameter = None
        if art == TARIFSLUG_SEITENPARAMETER:
            parameter = self.text(daten, "parameter", "tarifslug")
        elif "parameter" in daten:
            raise self.fehler("tarifslug.parameter", GRUND_NICHT_ZUR_ART)
        beleglink = self.wahlweise_text(daten, "beleglink", "tarifslug")
        if beleglink not in (None, BELEGLINK_KONFIGURATION):
            raise self.fehler("tarifslug.beleglink", GRUND_ART)
        return Tarifslugregel(art=art, parameter=parameter, beleglink=beleglink)

    def _art(self, daten: Mapping, feld: str, arten: tuple[str, ...]) -> str:
        art = self.text(daten, "art", feld)
        if art not in arten:
            raise self.fehler(stelle(feld, "art"), f"{GRUND_ART} {art}")
        return art

    def _nur_teile(self, daten: Mapping, feld: str, erlaubt: tuple[str, ...]) -> None:
        for schluessel in daten:
            if schluessel != "art" and schluessel not in erlaubt:
                raise self.fehler(stelle(feld, str(schluessel)), GRUND_NICHT_ZUR_ART)

    def ausgelistet_url(self, roh: object) -> AusgelistetUrl | None:
        """Host und Pfadmuster der Übersicht für ausgelistete Geräte, sonst ``None``."""
        if roh is None:
            return None
        feld = "kanarie.ausgelistet_url"
        daten = self.zuordnung(roh, feld, AUSGELISTETTEILE)
        return AusgelistetUrl(
            host=self.text(daten, "host", feld).lower(),
            pfad=self.muster(daten, "pfad", feld),
        )


def stelle(feld: str, schluessel: str) -> str:
    """Punktpfad von ``schluessel`` unter ``feld``."""
    return f"{feld}.{schluessel}" if feld else schluessel
