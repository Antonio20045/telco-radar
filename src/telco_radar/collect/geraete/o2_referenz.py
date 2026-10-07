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
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable

from .basis import _gleich

log = logging.getLogger(__name__)

PROBEN_JE_ANZEIGE = 2
REFERENZ_TARIFE = "referenz_tarife"
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


def _zaehle(z: dict, name: str) -> None:
    z[name] = int(z.get(name, 0)) + 1


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
        self._gesperrt: set = set()
        self._unlesbar_bei: defaultdict[str, set] = defaultdict(set)

    def erster_durchlauf(self, start: dict) -> None:
        """Einmal je Lauf: je verlinktem Tarif der Startantwort ein Abruf."""
        if self._versucht or not self._weiter():
            return
        self._versucht = True
        durchlauf: list = [start]
        for option in (start.get("tariff") or {}).get("tariffOptions") or []:
            if option.get("selected") or not self._link(option):
                continue
            if not self._weiter():
                durchlauf.append(None)
                break
            durchlauf.append(self._abruf(self._link(option)))
        self.tarife = tarife_aus([self._messe(s) if s else None for s in durchlauf])
        self._z[REFERENZ_TARIFE] = len(self.tarife or {})
        if self.tarife is None:
            log.warning(
                "o2-Vertiefung: der Referenzdurchlauf haelt die Befunde nicht "
                "(Rate/Anzahlung tarifabhaengig oder eine Probe faellt) - nur "
                "gemessene Saetze"
            )

    def ergaenze(self, pv: dict, geraet: str) -> None:
        """Probt die Optionen dieser Antwort, die die Referenz nicht kennt.

        `geraet` ist die Adresse des Katalogbuendels; an ihm wird eine
        ungelesene Probe nicht wiederholt.
        """
        g = self._messe(pv)
        if self.tarife is None or g is None or not passt(self.tarife, g):
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
