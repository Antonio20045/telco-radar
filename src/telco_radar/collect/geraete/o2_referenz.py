"""o2: die Referenz der Vertiefung - erster Durchlauf und Proben je Lauf.

DER BEFUND VOM 07.10.2026
-------------------------
`o2.vertiefe_buendel` misst die Referenz (Tarifanzeige -> Slug und
Anschlusspreis) einmal je Lauf am Tarifdurchlauf des ersten Geraets. Die
Tarifliste haengt aber am Geraet: am 29.09.2026 bot das iPhone 18 Pro sieben
Tarife ohne "Plus", das iPhone 17 Pro zwoelf. Eine Option, die die Referenz
nicht kannte, zaehlte `saetze_aus_konfiguration` als `ohne_referenz` und
verwarf sie - bei jedem weiteren Geraet. In `geraete_tco.json` vom
07.10.2026 fehlten so "O2 Mobile Unlimited L Plus mit 300 MBit/s" und
"O2 Mobile Special" bei allen 94 o2-Geraeten.

DIE PROBE
---------
Geprobt wird nur an einer Antwort, deren eigener Tarif zur Referenz passt
(`passt`, dieselbe Pruefung wie in `saetze_aus_konfiguration`); eine
Antwort mit geraeteeigener Aktion schreibt so nichts fuer andere Geraete
fest. Eine Option ohne Referenz wird ueber ihren Link aus der Antwort
abgerufen, mit demselben gebremsten Abruf und nur, solange `weiter()` Zeit
gibt. Antwort und Probe sind ein Durchlauf desselben Geraets; haelt er die
Befunde (`tarife_aus`) und nennt die Probe genau die Anzeige der Option,
kommt die Anzeige mit Slug und Anschlusspreis DER PROBE in die Referenz.
Eine gelesene Probe sperrt die Anzeige fuer den Lauf, ob sie haelt oder
nicht; eine nicht gelesene (Abruffehler) nicht - sie darf an einem anderen
Geraet wiederholt werden, bis `PROBEN_JE_ANZEIGE` Proben ungelesen blieben.

DER BEFUND VOM 17.11.2026: DIE PROBE KAM NIE ZUM ZUG
----------------------------------------------------
Die Probe darf nur an einer Antwort ansetzen, deren eigener Tarif schon in
der Referenz steht - und seit dem Abend des 13.11.2026 ist das genau die
Haelfte des Katalogs, die nichts Neues kennt. o2 bietet die fuenf
"Plus"-Tarife nur an einem Teil der Geraete an, und diese Geraete stehen im
Katalog schon in einem "Plus"-Tarif. Gemessen am 17.11.2026 (Katalog mit
Tarif, 70 Saetze): 8 Saetze stehen in "O2 Mobile on Demand M mit 50 GB+",
ihre Produktseite bietet SIEBEN Tarife (Samsung Galaxy A27 5G, Xiaomi Redmi
Note 17 5G, Apple iPhone 18 Pro Max - je sieben); die anderen 62 stehen in
einem "Plus"-Tarif und bieten ZWOELF. Die Referenz entsteht am ersten
Geraet, und `buendel_prioritaet.nach_prioritaet` stellt die Pflichtmodelle
vorn - also das iPhone 18 Pro Max mit sieben.

Folge in Lauf 44066902790 (17.11.2026): `referenz_tarife` 7,
`referenz_widerspricht` 153 von 185 gemessenen Antworten, 192 abgeleitete
Saetze; am 13.11.2026 morgens waren es mit `referenz_tarife` 12 noch 1864.
83 Geraet-Tarif-Kombinationen vom 16.11. wurden am 17.11. nicht erneuert.

Antwort: `_zweiter_durchlauf` - ein zweiter VOLLSTAENDIGER Tarifdurchlauf am
ersten widersprechenden Geraet, hoechstens `DURCHLAEUFE_JE_LAUF` je Lauf. Er
ergaenzt nur unbekannte Anzeigen und nur, wenn er die Referenz in allen
gemeinsamen Anzeigen bestaetigt (`_bestaetigt`). Damit steht jeder Eintrag
weiter auf einem vollstaendigen, in sich stimmigen Durchlauf EINES Geraets,
und der Schutz des Befundes vom 07.10.2026 bleibt: ein Geraet mit eigener
Aktion weicht im Anschlusspreis ab und sein ganzer Durchlauf faellt weg.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .basis import _gleich

log = logging.getLogger(__name__)

PROBEN_JE_ANZEIGE = 2
DURCHLAEUFE_JE_LAUF = 2
REFERENZ_TARIFE = "referenz_tarife"
DURCHLAUF_ABRUF = "referenz_durchlauf"
DURCHLAUF_ERGAENZT = "referenz_durchlauf_ergaenzt"
DURCHLAUF_VERWORFEN = "referenz_durchlauf_verworfen"
DURCHLAUF_FRIST = "referenz_durchlauf_frist"
PROBE_ABRUF = "referenz_probe"
PROBE_ERGAENZT = "referenz_ergaenzt"
PROBE_VERWORFEN = "probe_verworfen"
PROBE_UNLESBAR = "probe_unlesbar"
PROBE_FRIST = "probe_frist"


def tarife_aus(gemessen: list) -> dict | None:
    """Je Tarifanzeige Slug und Anschlusspreis - nur wenn die Befunde halten.

    `gemessen` sind die Messungen EINES Geraets (ein Speicher, eine
    Laufzeit); ein Eintrag `None` macht den Durchlauf unvollstaendig.
    Befunde: Geraeterate und Anzahlung haengen nicht am Tarif, jede Anzeige
    kommt einmal vor und traegt einen Slug.
    """
    if len(gemessen) < 2 or any(g is None for g in gemessen):
        return None
    if len({g["rate"] for g in gemessen}) != 1:
        return None
    if len({g["anzahlung"] for g in gemessen}) != 1:
        return None
    tarife: dict = {}
    for g in gemessen:
        if not g["slug"] or g["anzeige"] in tarife:
            return None
        tarife[g["anzeige"]] = {"slug": g["slug"], "anschluss": g["anschluss"]}
    return tarife


def passt(referenz: dict, g: dict) -> bool:
    """Der eigene Tarif einer Messung steht so in der Referenz (Slug, Anschluss)."""
    eigen = referenz.get(g["anzeige"])
    return (
        eigen is not None
        and eigen["slug"] == g["slug"]
        and _gleich(eigen["anschluss"], g["anschluss"])
    )


def gleicher_slug(referenz: dict, g: dict) -> bool:
    """Der eigene Tarif einer Messung steht mit demselben Slug in der Referenz.

    Das genügt für die Ableitung (`o2.saetze_aus_konfiguration`): aus der Referenz
    kommt nur der Slug, der Anschlusspreis aus der eigenen Option. `passt` (mit
    Anschlusspreis) bleibt die Bedingung für Proben und Durchläufe der Referenz."""
    eigen = referenz.get(g["anzeige"])
    return eigen is not None and eigen["slug"] == g["slug"]


def angeboten(option) -> bool:
    """Bietet o2 diese Tarifoption zum Gerät an? Jede `pdp:TariffOptionValue` trägt
    `disabled`; die Seite rendert damit den Knopf ihrer Tarifauswahl. Eine Option mit
    `disabled: true` ist kein Angebot: kein Bündel, keine Probe, im Bestand altert sie.
    Ohne das Feld (ältere Mitschnitte) gilt sie als angeboten. Gemessen 21.11.2026:
    2.230 von 2.230 Optionen aus 190 Antworten `false` (test_o2_tarifabdeckung)."""
    return isinstance(option, dict) and option.get("disabled") is not True


def angebotene(pv: dict, z: dict) -> list[dict]:
    """Die angebotenen Tarifoptionen einer Antwort (`angeboten`). Zählt `angeboten`
    und, falls o2 welche sperrt, `nicht_angeboten`; mit `erfasst` ergibt sich die
    Abdeckung je Lauf (`o2.saetze_aus_konfiguration`)."""
    tarif = pv.get("tariff") or {}
    alle = [o for o in tarif.get("tariffOptions") or [] if isinstance(o, dict)]
    optionen = [o for o in alle if angeboten(o)]
    _zaehle(z, "angeboten", len(optionen))
    if len(alle) > len(optionen):
        _zaehle(z, "nicht_angeboten", len(alle) - len(optionen))
    return optionen


def erfasst(z: dict, optionen: list, saetze: list) -> list:
    """Gibt `saetze` zurück und zählt die angebotenen Optionen ohne Satz
    (`nicht_erfasst`); 0 heißt: jeder angebotene Tarif ist ein Bündel."""
    _zaehle(z, "nicht_erfasst", len(optionen) - len(saetze))
    return saetze


def _zaehle(z: dict, name: str, n: int = 1) -> None:
    z[name] = int(z.get(name, 0)) + n


class Referenzstand:
    """Die Referenz eines Laufs samt Proben.

    `abruf(url)` liefert die gelesene Antwort oder `None` (Abruffehler),
    `messe(antwort)` deren Messung oder `None`; `link(option)` und
    `anzeige(text)` lesen eine Tarifoption. Alle vier kommen aus `o2`.
    """

    def __init__(
        self,
        abruf: Callable[[str], dict | None],
        messe: Callable[[dict], dict | None],
        link: Callable[[dict], str],
        anzeige: Callable[[str], str],
        weiter: Callable[[], bool],
        z: dict,
    ) -> None:
        self.tarife: dict | None = None
        self._abruf, self._messe, self._link, self._anzeige = (
            abruf,
            messe,
            link,
            anzeige,
        )
        self._weiter, self._z = weiter, z
        self._versucht = False
        self._durchlaeufe = 0
        self._gesperrt: set = set()
        self._unlesbar_bei: defaultdict[str, set] = defaultdict(set)

    def _durchlauf(self, start: dict) -> dict | None:
        """Je verlinktem Tarif dieser Startantwort ein Abruf, dann `tarife_aus`."""
        self._durchlaeufe += 1
        durchlauf: list = [start]
        for option in (start.get("tariff") or {}).get("tariffOptions") or []:
            if option.get("selected") or not angeboten(option):
                continue
            if not self._link(option):
                continue
            if not self._weiter():
                durchlauf.append(None)
                break
            durchlauf.append(self._abruf(self._link(option)))
        return tarife_aus([self._messe(s) if s else None for s in durchlauf])

    def erster_durchlauf(self, start: dict) -> None:
        """Einmal je Lauf: je verlinktem Tarif der Startantwort ein Abruf."""
        if self._versucht or not self._weiter():
            return
        self._versucht = True
        self.tarife = self._durchlauf(start)
        self._z[REFERENZ_TARIFE] = len(self.tarife or {})
        if self.tarife is None:
            log.warning(
                "o2-Vertiefung: der Referenzdurchlauf haelt die Befunde nicht "
                "(Rate/Anzahlung tarifabhaengig oder eine Probe faellt) - nur "
                "gemessene Saetze"
            )

    def _bestaetigt(self, neu: dict) -> bool:
        """Der Durchlauf nennt in JEDER gemeinsamen Anzeige Slug und
        Anschlusspreis der Referenz - und hat mindestens eine gemeinsame.

        Das ist die Pruefung, die den Befund vom 07.10.2026 haelt: ein
        Geraet mit eigener Aktion weicht in genau diesen Zahlen ab (am
        29.09.2026 gemessen: 0,00 statt 39,99 EUR Anschlusspreis), und
        dann faellt sein ganzer Durchlauf weg, statt fuer andere Geraete
        etwas festzuschreiben.
        """
        gemeinsam = set(neu) & set(self.tarife or {})
        return bool(gemeinsam) and all(
            neu[a]["slug"] == (self.tarife or {})[a]["slug"]
            and _gleich(neu[a]["anschluss"], (self.tarife or {})[a]["anschluss"])
            for a in gemeinsam
        )

    def _zweiter_durchlauf(self, pv: dict) -> None:
        """Ein weiterer vollstaendiger Tarifdurchlauf an einer Antwort, die
        der Referenz widerspricht, weil sie ihren eigenen Tarif nicht kennt.

        Der Befund vom 17.11.2026: o2 bietet die fuenf "Plus"-Tarife nur an
        einem Teil der Geraete an, und GENAU diese Geraete stehen im Katalog
        schon in einem "Plus"-Tarif. Die Referenz entsteht am ersten Geraet,
        also an einem ohne "Plus" (sieben Tarife); `ergaenze` darf nur an
        Antworten proben, deren eigener Tarif der Referenz bekannt ist - das
        sind wieder die Geraete mit sieben Tarifen, die nichts Neues kennen.
        Die Probe von 07.10.2026 kam damit nie zum Zug (Lauf 44066902790:
        `referenz_tarife` 7, `referenz_widerspricht` 153 von 185, 192 statt
        1864 abgeleitete Saetze).

        Darum hier ein zweiter Durchlauf am ersten widersprechenden Geraet,
        hoechstens `DURCHLAEUFE_JE_LAUF` je Lauf. Er ergaenzt nur Anzeigen,
        die die Referenz nicht kennt, und nur wenn er sie in den gemeinsamen
        bestaetigt (`_bestaetigt`) - jeder Eintrag steht damit weiter auf
        einem vollstaendigen, in sich stimmigen Durchlauf EINES Geraets.
        """
        if self._durchlaeufe >= DURCHLAEUFE_JE_LAUF:
            return
        if not self._weiter():
            _zaehle(self._z, DURCHLAUF_FRIST)
            return
        _zaehle(self._z, DURCHLAUF_ABRUF)
        neu = self._durchlauf(pv)
        if neu is None or not self._bestaetigt(neu):
            _zaehle(self._z, DURCHLAUF_VERWORFEN)
            log.info(
                "o2-Vertiefung: der zweite Referenzdurchlauf bestaetigt die "
                "Referenz nicht - sie bleibt bei %d Tarifen",
                len(self.tarife or {}),
            )
            return
        for anzeige, wert in neu.items():
            if self.tarife is not None and anzeige not in self.tarife:
                self.tarife[anzeige] = wert
                _zaehle(self._z, DURCHLAUF_ERGAENZT)
        self._z[REFERENZ_TARIFE] = len(self.tarife or {})

    def ergaenze(self, pv: dict, geraet: str) -> None:
        """Probt die Optionen dieser Antwort, die die Referenz nicht kennt.

        `geraet` ist die Adresse des Katalogbuendels; an ihm wird eine
        ungelesene Probe nicht wiederholt. Kennt die Referenz den eigenen
        Tarif dieser Antwort nicht, entscheidet ein zweiter vollstaendiger
        Durchlauf (`_zweiter_durchlauf`), ob sie ueberhaupt proben darf.
        """
        g = self._messe(pv)
        if self.tarife is None or g is None:
            return
        if not passt(self.tarife, g):
            self._zweiter_durchlauf(pv)
            if not passt(self.tarife, g):
                return
        optionen = [
            o
            for o in (pv.get("tariff") or {}).get("tariffOptions") or []
            if isinstance(o, dict)
        ]
        anzeigen = [self._anzeige(o.get("displayValue") or "") for o in optionen]
        for option, anzeige in zip(optionen, anzeigen, strict=True):
            if not self._probefaehig(option, anzeige, anzeigen, geraet):
                continue
            if not self._weiter():
                _zaehle(self._z, PROBE_FRIST)
                return
            self._probe(g, anzeige, self._link(option), geraet)

    def _probefaehig(
        self, option: dict, anzeige: str, anzeigen: list, geraet: str
    ) -> bool:
        ungelesen = self._unlesbar_bei[anzeige]
        return bool(
            anzeige
            and anzeige not in (self.tarife or {})
            and anzeige not in self._gesperrt
            and geraet not in ungelesen
            and len(ungelesen) < PROBEN_JE_ANZEIGE
            and not option.get("selected")
            and angeboten(option)
            and self._link(option)
            and anzeigen.count(anzeige) == 1
        )

    def _probe(self, g: dict, anzeige: str, url: str, geraet: str) -> None:
        _zaehle(self._z, PROBE_ABRUF)
        seite = self._abruf(url)
        if seite is None:
            self._unlesbar_bei[anzeige].add(geraet)
            _zaehle(self._z, PROBE_UNLESBAR)
            return
        self._gesperrt.add(anzeige)
        neu = tarife_aus([g, self._messe(seite)])
        if neu is None or anzeige not in neu or self.tarife is None:
            _zaehle(self._z, PROBE_VERWORFEN)
            return
        self.tarife[anzeige] = neu[anzeige]
        _zaehle(self._z, PROBE_ERGAENZT)


_EE_RE = re.compile(r"-ee-\d+(?:gb|tb)-")
_ANGEBOT_RE = re.compile(r"^[a-z]+-(?P<geraet>.+?-\d+(?:gb|tb)-.+?)-\d+x\w+$")
_EE_NAME = re.compile(r"\b(?:ee|enterprise)\b", re.IGNORECASE)
_ZUGABE = re.compile(r"\s+mit\s+.*$", re.IGNORECASE)
_MIT_IM_ANGEBOT = re.compile(r"-mit-")


def modellname(h: dict) -> str:
    """Die Gerätebeschreibung eines Katalogeintrags. o2 nennt die Enterprise
    Edition nur im Angebotsnamen (`…-galaxy-s26-ee-256gb-black-…`), die
    Beschreibung heißt wie das normale Modell; ohne den Zusatz liefen ihre
    Preise als normales S26 (Preisprüfung 26.10.2026, 102 € zu hoch).

    Eine Gratis-Zugabe steht nur in der Beschreibung („Google Pixel 11 mit Fitbit
    Charge 6“, Angebotsname `…-pixel-11-256gb-frost-36xhigh`; die Seite: „erhalte die
    Fitbit Charge 6 gratis dazu“, Gerätepreis wie ohne). Ohne `-mit-` im Angebotsnamen
    fällt der Zusatz weg; ein Zubehörbündel trägt ihn im Angebotsnamen
    (`…-mit-pixel-buds-pro-2-…`) und wird weiter verworfen (Befund 21.11.2026)."""
    modell = str(h.get("description") or "").strip()
    if not _MIT_IM_ANGEBOT.search(str(h.get("offerName") or "")):
        modell = _ZUGABE.sub("", modell)
    ee = _EE_RE.search(str(h.get("offerName") or ""))
    if modell and ee and not _EE_NAME.search(modell):
        return f"{modell} Enterprise Edition"
    return modell


def belegadresse(
    url: str, tarif_slug: str, raten: int | None, angebot: str = ""
) -> str:
    """Die Produktseite mit Speicher, Farbe, Tarif und Ratenzahl der Zeile. Alle
    Zeilen eines Geräts trugen sonst die Adresse der Startseite (Preisprüfung
    26.10.2026: bei 1.875 von 2.062 o2-Zeilen ein anderer Tarif, 27.10.: bei 462
    eine kleinere Speichergröße). Den Pfad nennt der Angebotsname:
    ``x-<gerät>-512gb-<farbe>-24xhigh`` zu ``<gerät>-512gb-<farbe>-details``.
    """
    teile = urlsplit(url)
    if not tarif_slug or not teile.path.endswith("-details"):
        return url
    pfad = teile.path
    if m := _ANGEBOT_RE.match(angebot):
        pfad = pfad.rsplit("/", 1)[0] + f"/{m['geraet']}-details"
    frage = dict(parse_qsl(teile.query, keep_blank_values=True))
    frage["tarif"] = tarif_slug
    if raten:
        frage["ratenzahlung"] = str(raten)
    return urlunsplit(teile._replace(path=pfad, query=urlencode(frage)))
