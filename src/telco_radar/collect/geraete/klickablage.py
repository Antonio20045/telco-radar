"""Ablage der Klick-Erkundung: ein Ordner je Anbieter und Tag, mit Größengrenze.

``Ablage`` schreibt unter ``erkundung/<anbieter>/<JJJJ-MM-TT>/`` und zählt jedes Byte
gegen ``grenze``; ``RESERVE_INDEX`` bleibt für ``index.json``. Passt eine Datei nicht
mehr, wird sie nicht geschrieben und ``vermerke`` nennt sie; den Mitschnitt kürzt
``passe_mitschnitt`` vorher, indem er die größten Körper weglässt, je mit Vermerk am
Eintrag. Text geht vor dem Schreiben durch ``schwaerze``: jeder je gesehene Cookie-Wert
und jede Kennung, die irgendwo unter einem geheimen Namen stand
(``klickspur.geheime_werte``, etwa die Warenkorb-Kennung aus dem Weiter-Klick), ab
``COOKIE_MINDESTLAENGE`` Zeichen, auch URL-kodiert, wird zu ``GESCHWAERZT``, damit sie
nirgends gespeichert wird, auch nicht im HTML, im Pfad oder unter einem harmlosen
Namen; danach ersetzt ``klickspur.schwaerze_text`` geheime Parameter, JSON-Felder und
Tokens.
Bei JSON gilt das für jeden Text darin einzeln, auch für Antwortkörper.
Ein alter Stand desselben Tages wird vorher geleert, damit der Ordner genau einen Lauf
zeigt. Listen von Adressen (verworfen, gescheitert) stehen mit höchstens
``HOECHSTE_LISTE`` Einträgen in einer Datei; ihre Zahl steht ungekürzt daneben.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from .klickspur import GESCHWAERZT, schwaerze_text

RESERVE_INDEX = 100_000
COOKIE_MINDESTLAENGE = 8
INDEX = "index.json"
GZIP_STUFE = 9
VERMERK_KOERPER = "Körper wegen Größengrenze je Anbieter nicht gespeichert"
HOECHSTE_LISTE = 200


@dataclass
class Ablage:
    """Ordner eines Anbieters mit Größengrenze und Vermerken über Gekürztes."""

    ordner: Path
    grenze: int
    belegt: int = 0
    vermerke: list[str] = field(default_factory=list)
    geheim: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.ordner.mkdir(parents=True, exist_ok=True)
        for alt in self.ordner.iterdir():
            if alt.is_file():
                alt.unlink()

    @property
    def platz(self) -> int:
        """Bytes, die bis zur Grenze noch frei sind, ohne die Reserve des Index."""
        return max(0, self.grenze - RESERVE_INDEX - self.belegt)

    def merke_cookies(self, werte: Iterable[str]) -> None:
        """Merkt Cookie-Werte und Kennungen, die jedes Schreiben schwärzt."""
        self.geheim.update(w for w in werte if len(w) >= COOKIE_MINDESTLAENGE)

    def schwaerze(self, text: str) -> str:
        """Ersetzt jeden gemerkten Cookie-Wert, roh und URL-kodiert, und Geheimes."""
        for wert in sorted(self.geheim, key=len, reverse=True):
            for form in {wert, quote(wert, safe="")}:
                text = text.replace(form, GESCHWAERZT)
        return schwaerze_text(text)

    def json_bytes(self, daten: object) -> bytes:
        """Geschwärztes JSON als UTF-8, jeder Text darin auch einzeln geschwärzt."""
        text = json.dumps(self._sauber(daten), ensure_ascii=False, indent=1)
        return self.schwaerze(text).encode("utf-8")

    def _sauber(self, daten: object) -> object:
        if isinstance(daten, str):
            return self.schwaerze(daten)
        if isinstance(daten, dict):
            return {k: self._sauber(v) for k, v in daten.items()}
        if isinstance(daten, list | tuple):
            return [self._sauber(v) for v in daten]
        return daten

    def schreibe(self, name: str, daten: bytes, platz: int | None = None) -> str | None:
        """Schreibt ``daten``, wenn sie in ``platz`` (Standard: ``self.platz``) passen.

        Gibt den Dateinamen zurück, sonst ``None`` mit Vermerk.
        """
        frei = self.platz if platz is None else min(platz, self.platz)
        if len(daten) > frei:
            self.vermerke.append(
                f"{name} nicht gespeichert: {len(daten)} Bytes, frei {frei}"
                f" (Grenze {self.grenze} Bytes je Anbieter)"
            )
            return None
        (self.ordner / name).write_bytes(daten)
        self.belegt += len(daten)
        return name

    def schreibe_json(
        self, name: str, daten: object, platz: int | None = None
    ) -> str | None:
        """Schreibt geschwärztes JSON, wenn es passt."""
        return self.schreibe(name, self.json_bytes(daten), platz)

    def schreibe_html(
        self, name: str, html: str, platz: int | None = None
    ) -> str | None:
        """Schreibt die geschwärzte Seite gzip-gepackt, wenn sie passt."""
        roh = self.schwaerze(html).encode("utf-8")
        return self.schreibe(name, gzip.compress(roh, GZIP_STUFE, mtime=0), platz)

    def passe_mitschnitt(self, eintraege: list[dict], platz: int) -> list[dict]:
        """Lässt die größten Körper weg, bis der Mitschnitt in ``platz`` passt."""
        weg = 0
        groesse = len(self.json_bytes(eintraege))
        while groesse > platz:
            mit = [e for e in eintraege if _koerpergroesse(e)]
            if not mit:
                break
            for eintrag in sorted(mit, key=_koerpergroesse, reverse=True):
                if groesse <= platz:
                    break
                groesse -= len(self.json_bytes(eintrag["koerper"]))
                eintrag["koerper"], eintrag["grund"] = None, VERMERK_KOERPER
                weg += 1
            groesse = len(self.json_bytes(eintraege))
        if weg:
            self.vermerke.append(
                f"Mitschnitt: {weg} Körper wegen Größengrenze weggelassen"
            )
        return eintraege

    def schreibe_index(self, index: dict) -> None:
        """Schreibt ``index.json`` mit Belegung und Vermerken; zählt zur Grenze."""
        index["groesse_bytes"] = self.belegt
        index["groessengrenze_bytes"] = self.grenze
        index["gekuerzt"] = list(self.vermerke)
        daten = self.json_bytes(index)
        index["groesse_bytes"] = self.belegt + len(daten)
        daten = self.json_bytes(index)
        (self.ordner / INDEX).write_bytes(daten)
        self.belegt += len(daten)


def _koerpergroesse(eintrag: dict) -> int:
    koerper = eintrag.get("koerper")
    return len(koerper) if isinstance(koerper, str) else 0
