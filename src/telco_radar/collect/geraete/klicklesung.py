"""Lesung nach einem Klick: Quellen, Text, markierte Optionen und Screenshot.

Der Klick-Crawler (``klickcrawler``) ruft ``Leser.lies``, sobald die Antwort zum Klick
da ist oder die Seite ruht. Der Leser liest erst die Seitenwerte und die Quellen der
zweiten Lesung (``klickquellen``; ihre Platzhalter sind die geklickten Werte, die
Seitenwerte und der Modellname), dann nach zwei Bildern den Text der
Preiszusammenfassung (``klicktextleser``, bei Bedarf in einem Dialog), prüft die roh
markierten Optionen gegen die geklickten, die Seitenwerte mit dem Namen einer Dimension
als „Seite zeigt“ und das Echo (``klickecho``) und macht einen Screenshot des
Preisbereichs. Was der Beleg braucht (Mitschnitt, JSON-Pfade, Fundorte der
Textmuster), legt er in ``belegteile``. Fehlt die Zusammenfassung, heißt die
Kombination ``nicht_erfasst``, ebenso ohne Preiswert (``klicklauf.lesestatus``);
widerspricht sich etwas, ``befund``. Eine feste
Dimension hat keine Markierung. Eine Option als Adresse (``adressen``) braucht ein Echo,
das nicht aus der eigenen Adresse stammt: einen Seitenwert mit Selektor oder einen
Variantenwert der Antwort ohne Platzhalter ihrer Dimension; sonst ist sie ein Befund.
Gefundene Wertfelder zählt der Strukturwächter, ebenso jede angezeigte Option, auf die
das Muster der Karte nicht passt (``unlesbar``); deren Kombination heißt
``nicht_erfasst``. Mit ``weiter`` (``klickweiter``) liest ``vorlesung`` Seitenwerte,
zweite Lesung und Markierung auf der Startseite vor dem Weiter-Klick; ``lies`` nimmt
sie mit und liest auf der Folgeseite nur die Kachel an ``stelle``. Nennt die zweite
Lesung für die Kacheldimension eine andere Option, ist die Kachel selbst die Quelle
(``klickkachel``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klickbeleg import Belegquelle, baue_beleg
from .klickecho import KEINE_AUSWAHL, Befund, Echo, Variante, pruefe_echo, variante_aus
from .klickhar import Antwortkopie
from .klickkachel import (
    QUELLE_KACHEL,
    kachel_echo,
    kacheldimension,
    kachellabels,
    kachelpfade,
)
from .klickkarte import (
    BUENDELFELDER,
    DIMENSIONEN,
    PLATZHALTER_MODELL,
    Klickkarte,
    Wertpfad,
)
from .klicklauf import (
    BEFUND,
    NICHT_ERFASST,
    Klicklauf,
    Kombiergebnis,
    Strukturbilanz,
    lesestatus,
    mit_beleg,
)
from .klickoptionen import Option, angebotene_werte, lies_optionen
from .klickquellen import Quellenleser, Quellenlesung
from .klicktext import Preiswerte
from .klicktextleser import Textleser
from .klicktor import kurz

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from .klickantwort import Antwortlesung
    from .klickwache import Wache

_ZWEI_BILDER_JS = (
    "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
)


@dataclass(frozen=True)
class Belegteile:
    """Was der Beleg einer Lesung braucht außer Werten, Text und Bild."""

    kopie: Antwortkopie | None = None
    json_pfade: Mapping[str, str] = field(default_factory=dict)
    fundorte: Mapping[str, tuple[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Vorlesung:
    """Was die Startseite vor dem Weiter-Klick für alle Kacheln liest."""

    seitenwerte: Mapping[str, str | None]
    zweite: Quellenlesung
    abweichung: tuple[Befund, ...] | None = None


class Leser(Textleser):
    """Liest Optionen, Quellen, Text und die Kombination auf einer Seite nach Karte."""

    def __init__(
        self,
        seite: Page,
        karte: Klickkarte,
        frist_ms: int,
        wache: Wache,
        modell: str | None = None,
    ) -> None:
        super().__init__(seite, karte, frist_ms)
        self.wache, self.modell = wache, modell
        self.quellen = Quellenleser(seite, karte, wache.mitschnitt)
        self.belegteile = Belegteile()
        self.unlesbar: dict[str, set[str]] = {d: set() for d in DIMENSIONEN}

    def optionen(self, dimension: str) -> list[Option]:
        """Die Knöpfe einer Dimension im aktuellen Zustand der Seite."""
        return lies_optionen(self.seite, self.karte, dimension)

    def angebotene(self, dimension: str, struktur: Strukturbilanz) -> list[str | None]:
        """Die angebotenen Werte; eine unlesbare Option zählt als fehlender Knopf."""
        fest = self.karte.knoepfe[dimension].fest
        if fest is not None:
            return [fest]
        optionen = self.optionen(dimension)
        struktur.knopf(bool(optionen))
        for option in optionen:
            if option.unlesbar is not None:
                struktur.knopf(False)
                self.unlesbar[dimension].add(option.unlesbar)
        return angebotene_werte(optionen)

    def unlesbar_in(self, ziel: Mapping[str, str | None]) -> str | None:
        """Der Grund, wenn ``ziel`` eine Option ohne lesbaren Wert enthält."""
        for dimension in DIMENSIONEN:
            wert = ziel[dimension]
            if wert is not None and wert in self.unlesbar[dimension]:
                return f"Option „{wert}“ für {dimension} passt nicht auf das Muster"
        return None

    def vorlesung(
        self,
        ziel: Mapping[str, str | None],
        unberuehrt: bool = False,
        markiert: bool = True,
    ) -> Vorlesung:
        """Seitenwerte und zweite Lesung im jetzigen Zustand, mit ``markiert`` auch
        die Befunde der Markierung."""
        seitenwerte = self.quellen.seitenwerte()
        platz = {**seitenwerte, **ziel, PLATZHALTER_MODELL: self.modell}
        zweite = self.quellen.lies(
            self.wache.seit, unberuehrt, platz, self.wache.geladen
        )
        abweichung = self._abweichung(ziel) if markiert else None
        return Vorlesung(seitenwerte, zweite, abweichung)

    def lies(
        self,
        variante: Variante,
        ziel: dict[str, str | None],
        struktur: Strukturbilanz,
        unberuehrt: bool = False,
        vorab: Vorlesung | None = None,
        stelle: int = 0,
    ) -> Kombiergebnis:
        """Liest Quellen, dann Text: der Antwortkörper ist da, bevor die Seite malt.

        ``unberuehrt`` heißt: seit dem Laden wurde nichts geklickt (``start``-Quellen).
        ``vorab`` ist die Vorlesung der Startseite, ``stelle`` der Treffer des ersten
        Bereichs (die Kachel).
        """
        bereich = self.seite.locator(self.karte.textlesung.selektoren[0]).nth(stelle)
        if vorab is None:
            vorab = self.vorlesung(ziel, unberuehrt, markiert=False)
        seitenwerte, zweite = vorab.seitenwerte, vorab.zweite
        self.belegteile = Belegteile(zweite.kopie, zweite.json_pfade)
        url = None if zweite.kopie is None else zweite.kopie.url
        in_antwort = zweite.lesung.werte if zweite.lesung is not None else None
        self.seite.evaluate(_ZWEI_BILDER_JS)
        dialog = self.oeffne_dialog(bereich)
        text = self.zusammenfassung(bereich) if dialog is None else ""
        if not text:
            self.schliesse_dialog(bereich)
            struktur.felder(0)
            grund = (
                f"Preiszusammenfassung nicht gefunden ({self.karte.zusammenfassung})"
            )
            if dialog is not None:
                grund = dialog
            return Kombiergebnis(
                variante, NICHT_ERFASST, grund, antwort_url=url, antwortwerte=in_antwort
            )
        im_text, buendel, fundorte = self.textwerte(text)
        self.belegteile = Belegteile(zweite.kopie, zweite.json_pfade, fundorte)
        felder = self.karte.lesefelder
        gefunden = sum(
            getattr(buendel if f in BUENDELFELDER else im_text, f) is not None
            for f in felder
        )
        struktur.felder(gefunden, len(felder))
        ein_vertrag = self.karte.ein_vertrag
        textbuendel = buendel if ein_vertrag else None
        if zweite.befund is not None:
            befunde: tuple[Befund, ...] = (zweite.befund,)
            grund = zweite.befund.grund
            return Kombiergebnis(
                variante,
                BEFUND,
                grund,
                befunde=befunde,
                textwerte=im_text,
                textbuendel=textbuendel,
            )
        markierung = vorab.abweichung
        if markierung is None:
            markierung = self._abweichung(ziel)
        abweichung = markierung + self._ohne_echo(ziel, seitenwerte, zweite.lesung)
        angezeigt = self._angezeigt(variante, seitenwerte)
        kachel = kacheldimension(self.karte, variante, zweite.lesung)
        if abweichung:
            echo = Echo(Preiswerte(), abweichung, ())
        elif kachel is not None:
            labels = kachellabels(bereich, self.karte, kachel)
            auswahl = (kachel, ziel[kachel], labels)
            entfallen = self.karte.entfallen
            echo = kachel_echo(variante, angezeigt, auswahl, textbuendel, entfallen)
            pfade = kachelpfade(echo.buendel)
            self.belegteile = Belegteile(zweite.kopie, pfade, fundorte)
        else:
            echo = pruefe_echo(
                variante,
                angezeigt,
                im_text,
                zweite.lesung,
                buendel=textbuendel,
                entfallen=self.karte.entfallen,
            )
        bild, bildbefunde = self._screenshot(bereich)
        self.schliesse_dialog(bereich)
        befunde = echo.befunde + bildbefunde
        gebuendelt = echo.buendel if ein_vertrag else None
        status, erster = lesestatus(
            befunde, echo.werte, gebuendelt, ein_vertrag=ein_vertrag
        )
        antwortbuendel = None
        if ein_vertrag and zweite.lesung is not None:
            antwortbuendel = zweite.lesung.buendel
        return Kombiergebnis(
            variante,
            status,
            erster,
            echo.werte,
            befunde,
            echo.luecken,
            bild,
            url,
            text=text,
            textwerte=im_text,
            antwortwerte=in_antwort,
            buendel=gebuendelt,
            textbuendel=textbuendel,
            antwortbuendel=antwortbuendel,
            echo_quelle=None if kachel is None or echo.befunde else QUELLE_KACHEL,
        )

    def belege(
        self,
        ergebnis: Kombiergebnis,
        variante: Variante,
        lauf: Klicklauf,
        zeitpunkt: datetime,
    ) -> Kombiergebnis:
        """``ergebnis`` mit dem Beleg der letzten Lesung (``klicklauf.mit_beleg``)."""
        teile = self.belegteile
        quelle = Belegquelle(
            anbieter=self.karte.anbieter,
            adresse=lauf.adresse,
            seite=self.seite.url,
            http_status=lauf.http_status,
            variante=variante,
            status=ergebnis.status,
            werte=ergebnis.werte,
            text=ergebnis.text,
            screenshot_png=ergebnis.screenshot_png,
            antwort=teile.kopie,
            json_pfade=teile.json_pfade,
            fundorte=teile.fundorte,
            buendel=ergebnis.buendel,
        )
        paket, ohne = baue_beleg(quelle, self.karte, zeitpunkt)
        return mit_beleg(ergebnis, paket, ohne)

    def _angezeigt(
        self, variante: Variante, seitenwerte: Mapping[str, str | None]
    ) -> Variante:
        """Die Variante, die die Seite zeigt: Seitenwerte mit dem Namen einer
        Dimension, sonst die geklickte."""
        gezeigt = [
            seitenwerte[d] if d in self.karte.seite else getattr(variante, d)
            for d in DIMENSIONEN
        ]
        return variante_aus(*gezeigt)

    def _abweichung(self, ziel: Mapping[str, str | None]) -> tuple[Befund, ...]:
        """Befunde, wo die Seite eine andere Option markiert als die geklickte."""
        befunde = []
        for dimension in DIMENSIONEN:
            knopf = self.karte.knoepfe[dimension]
            if knopf.fest is not None or dimension == self.karte.kacheldimension:
                continue
            gezeigt = self._gewaehlt(dimension)
            if gezeigt != ziel[dimension]:
                zeige = KEINE_AUSWAHL if gezeigt is None else gezeigt
                grund = f"Seite zeigt {zeige} statt {ziel[dimension]}"
                befunde.append(Befund(f"variante.{dimension}", grund))
        return tuple(befunde)

    def _ohne_echo(
        self,
        ziel: Mapping[str, str | None],
        seitenwerte: Mapping[str, str | None],
        lesung: Antwortlesung | None,
    ) -> tuple[Befund, ...]:
        """Ein Befund, wenn nur die eigene Adresse die Option der Adressdimension nennt.

        Die Adresse der Seite (Seitenwert ohne Selektor) und ein Antwortpfad mit dem
        Platzhalter der Dimension sind kein Echo.
        """
        dimension = self.karte.adressdimension
        if dimension is None:
            return ()
        seitenwert = self.karte.seite.get(dimension)
        auf_seite = (
            seitenwert is not None
            and seitenwert.selektor is not None
            and seitenwerte.get(dimension) is not None
        )
        platzhalter = f"{{{dimension}}}"
        quellen = self.karte.lesequellen
        pfade = [q.variante[dimension] for q in quellen if dimension in q.variante]
        in_antwort = (
            lesung is not None
            and dimension in lesung.variante
            and not any(platzhalter in _pfad(p) for p in pfade)
        )
        if auf_seite or in_antwort:
            return ()
        grund = f"Nur die Adresse nennt {dimension} {ziel[dimension]}, die Seite nicht"
        return (Befund(f"variante.{dimension}", grund),)

    def _gewaehlt(self, dimension: str) -> str | None:
        gewaehlt = [o.wert for o in self.optionen(dimension) if o.gewaehlt]
        return gewaehlt[0] if len(gewaehlt) == 1 else None

    def _screenshot(self, bereich: Locator) -> tuple[bytes | None, tuple[Befund, ...]]:
        try:
            return bereich.screenshot(type="png", timeout=self.frist_ms), ()
        except PlaywrightFehler as fehler:
            return None, (Befund("screenshot", f"Screenshot fehlt: {kurz(fehler)}"),)


def _pfad(pfad: str | Wertpfad) -> str:
    return pfad if isinstance(pfad, str) else pfad.pfad
