"""Die IP-Bremse - und die ehrliche Aussage darueber, was sie NICHT ist.

Sie ist eine **erste Bremse gegen Ungeschicklichkeit und billige Skripte**,
keine Schutzmassnahme. Der Zaehler liegt im Arbeitsspeicher, und Render Free
faehrt die Instanz nach 15 Minuten ohne Verkehr herunter: nach jedem
Spin-down und nach jedem Deploy ist er leer. Wer ihn umgehen will, wartet
sechzehn Minuten.

**Die harte Sperre liegt deshalb woanders**: `doi.yml` im privaten Repo
prueft einen gepfefferten Adress-Kennwert gegen `doi_log.jsonl` und verwirft
stillschweigend, wenn dieselbe Adresse in 24 Stunden schon eine
Bestaetigungsmail bekommen hat. Nur dort gibt es Zustand, der einen
Spin-down ueberlebt - und nur dort greift der Schutz gegen die
Mailbomben-Nutzung, bei der jemand ein fremdes Postfach zumuellt.

Wer das hier fuer die Schutzmassnahme haelt, baut die Sperre an der einzigen
Stelle ein, an der sie sicher nicht wirkt.
"""
from __future__ import annotations

import time
from collections import deque


class IPBremse:
    """Hoechstens `erlaubt` Anfragen je Absender im gleitenden Fenster."""

    def __init__(self, erlaubt: int = 5, fenster: int = 600,
                 max_absender: int = 5000):
        self.erlaubt = erlaubt
        self.fenster = fenster
        # Deckel gegen den einfachsten Speicherangriff: ohne ihn legt eine
        # Anfrageflut mit wechselnden Absendern die Instanz lahm, und dafuer
        # braucht es nicht einmal boese Absicht - ein Proxy mit rotierenden
        # Adressen reicht.
        self.max_absender = max_absender
        self._spuren: dict[str, deque] = {}

    def erlaubt_jetzt(self, absender: str, *, jetzt: float | None = None) -> bool:
        t = jetzt if jetzt is not None else time.time()
        spur = self._spuren.setdefault(absender or "?", deque())
        while spur and t - spur[0] > self.fenster:
            spur.popleft()
        if len(spur) >= self.erlaubt:
            return False
        spur.append(t)
        self._aufraeumen(t)
        return True

    def _aufraeumen(self, jetzt: float) -> None:
        if len(self._spuren) <= self.max_absender:
            return
        # Alles wegwerfen, was aus dem Fenster gelaufen ist. Reicht das
        # nicht, faellt der aelteste Rest mit - eine zu grosszuegige Bremse
        # ist besser als eine Instanz, die nicht mehr antwortet.
        veraltet = [a for a, s in self._spuren.items()
                    if not s or jetzt - s[-1] > self.fenster]
        for a in veraltet:
            self._spuren.pop(a, None)
        while len(self._spuren) > self.max_absender:
            self._spuren.pop(next(iter(self._spuren)))
