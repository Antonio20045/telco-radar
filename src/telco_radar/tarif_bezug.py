"""Der Fremdschluessel: von einer Tarifangabe am Geraet zum Tarif im Bestand.

Wozu
----
Eine Buendelzahl ohne ihren Tarif ist eine Zahl ohne Bedeutung - "iPhone
fuer 1 Euro" sagt nichts, solange niemand weiss, welcher Vertrag daneben
laeuft. `geraete_model.Listung` erzwingt deshalb seit Teil C4 eine
`tarif_referenz`, und `tco_model.Buendel` verlangt einen `tarif_name`.
Beides ist bis heute ein freier Text: der Adapter schreibt hin, was auf der
Produktseite steht.

Ein freier Text ist aber kein Bezug. "MagentaMobil M", "Magenta Mobil M"
und "MagentaMobil M (Mobilfunk)" sind derselbe Tarif, und keiner davon
sagt, was er kostet. Der Grundpreis steht in `data/state/tarife.jsonl` -
gelesen aus dem gesetzlich vorgeschriebenen Produktinformationsblatt,
belegt bis auf die Textzeile. Dieses Modul stellt die Verbindung her.

Zwei Wege, zwei Guetestufen
---------------------------
`hoch`    Ueber den NAMEN. Verglichen wird die kanonische Tarif-ID
          (`collect/tarif_crawler.tarif_id`), also derselbe Schluessel, den
          der Bestand selbst benutzt. Was so trifft, trifft eindeutig.

`mittel`  Ueber den BETRAG. Vodafones Geraetenutzlast nennt unter
          `composition[].priceByComponent.tariff` einen Monatsbetrag und
          KEINEN Tarifnamen (Live 03.09.2026: 41,95 EUR und 31,45 EUR).
          Ein Betrag ist kein Name: er ist nur dann eine Zuordnung, wenn im
          Bestand genau EIN Tarif dieses Anbieters ihn traegt - und selbst
          dann ist er es nur innerhalb des Bestands. Der Anbieter fuehrt
          mehr Tarife, als dieses Projekt liest; ein zweiter mit demselben
          Preis wuerde die Zuordnung falsch machen, ohne dass sich hier
          etwas aendert. Genau das ist der Unterschied zwischen `mittel`
          und `hoch`, und deshalb kann dieser Weg `hoch` nicht erreichen.

Am gemessenen Fall (04.09.2026, Bestand mit 32 Tarifen): **keiner** der
zwei Vodafone-Betraege loest auf, und beide Gruende sind lehrreich.

* **41,95 EUR** steht im Blatt "Vodafone Mobil S" - aber als Zeile "mit
  zusaetzlichem Datenvolumen", also als TARIFOPTION. Der Tarif selbst
  kostet 39,95 EUR. Ein Betrag von einer Produktseite kann eine Option
  meinen, und eine Option ist kein Tarif.
* **31,45 EUR** steht in keinem der zehn gelesenen Blaetter. Am naechsten
  liegt 31,95 EUR - "fast" ist keine Zuordnung.

Dazu ein struktureller Befund: Vodafone veroeffentlicht jeden Tarif
ZWEIMAL, einmal ohne und einmal mit Geraetestaffel ("Vodafone Mobil M" und
"Vodafone Mobil M mit Smartphone"), beide mit demselben Grundpreis. Ein
Betrag trifft dort also regelmaessig zwei Datensaetze - und zwei Treffer
sind keine schwache Zuordnung, sondern gar keine.

Das ist das Ergebnis, nicht der Ausfall: ein blosser Betrag ist ein
schwacher Schluessel, und dieses Modul sagt das, statt eine Zahl
festzuschreiben, die zufaellig passt. Ein Buendelpreis ohne aufloesbaren
Tarif wird verworfen - die Regel aus `geraete_model.py` bleibt, sie
bekommt hier nur ihr Ziel.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .collect.tarif_crawler import tarif_id
from .tarif_model import HOCH, MITTEL

log = logging.getLogger(__name__)

# Wie genau ein Betrag treffen muss. Ein Cent ist kein Rundungsfehler,
# sondern ein anderer Preis; die Toleranz faengt nur die Gleitkommadarstellung.
_CENT = 0.005


@dataclass(frozen=True)
class Bezug:
    """Eine hergestellte Verbindung - mit ihrer Guete und ihrem Weg.

    `grund` ist kein Protokolltext, sondern die Fundstelle des Bezugs: er
    steht spaeter neben der Zahl auf der Seite, so wie `fundstellen` neben
    einem Tarifwert. Wer eine TCO liest, muss sehen koennen, WARUM dieser
    Tarif zu diesem Geraet gehoert.
    """

    tarif_id: str
    tarif_name: str
    guete: str
    grund: str

    @property
    def belastbar(self) -> bool:
        """Ob die Zuordnung ueber den Namen kam.

        Kein Filter, sondern eine Auskunft: eine Betragszuordnung ist
        brauchbar und wird gezeigt, sie traegt nur ihr `mittel` mit sich.
        """
        return self.guete == HOCH


class Tarifbestand:
    """Die letzten bekannten Staende aus `data/state/tarife.jsonl`.

    Die Datei ist eine ZEITREIHE - ein Tarif steht mehrfach darin, einmal
    je Fassung. Fuer einen Bezug zaehlt nur der letzte Stand; die aeltere
    Fassung eines Tarifs ist kein zweiter Tarif. Gelesen wird deshalb von
    vorn nach hinten und ueberschrieben, genau wie `TarifSpeicher.letzter`
    es einzeln tut.
    """

    def __init__(self, saetze: list[dict]) -> None:
        self.je_id: dict[str, dict] = {}
        for satz in saetze:
            if isinstance(satz, dict) and satz.get("tarif_id"):
                self.je_id[satz["tarif_id"]] = satz

    @classmethod
    def aus_datei(cls, pfad: Path) -> "Tarifbestand":
        pfad = Path(pfad)
        saetze: list[dict] = []
        if pfad.exists():
            for zeile in pfad.read_text(encoding="utf-8").splitlines():
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    saetze.append(json.loads(zeile))
                except json.JSONDecodeError:
                    # Eine kaputte Zeile ist kein Grund, den Bestand
                    # wegzuwerfen - dieselbe Haltung wie in TarifSpeicher.
                    continue
        return cls(saetze)

    def __len__(self) -> int:
        return len(self.je_id)

    def saetze(self, anbieter: str = "") -> list[dict]:
        """Alle Staende, wahlweise nur die eines Anbieters."""
        if not anbieter:
            return list(self.je_id.values())
        marke = tarif_id(anbieter, "")
        return [s for s in self.je_id.values()
                if tarif_id(s.get("anbieter", ""), "") == marke]

    # ------------------------------------------------------------- Namen

    def ueber_namen(self, anbieter: str, referenz: str) -> Optional[Bezug]:
        """Der Weg mit Guete `hoch`.

        Verglichen wird die kanonische ID und nicht der Text: sie wirft
        Jahreszahlen und Klammerzusaetze weg, und genau diese Unterschiede
        trennen sonst zwei Schreibweisen desselben Tarifs.
        """
        if not (referenz or "").strip():
            return None
        gesucht = tarif_id(anbieter, referenz)
        satz = self.je_id.get(gesucht)
        if satz is None:
            # Zweiter Versuch: der Anbietername steht im Tarifnamen des
            # Bestands, aber nicht in der Referenz - Vodafone nennt seinen
            # Tarif im PIB "Vodafone Mobil M", auf der Produktseite steht
            # "Mobil M". Umgekehrt kommt es genauso vor.
            marke = tarif_id(anbieter, "")
            ohne_marke = gesucht[len(marke) + 1:] if ":" in gesucht else gesucht
            for tid, kandidat in self.je_id.items():
                if tid == f"{marke}:{marke.split(':')[0]}-{ohne_marke}":
                    satz = kandidat
                    gesucht = tid
                    break
        if satz is None:
            return None
        return Bezug(tarif_id=gesucht, tarif_name=satz.get("name", ""),
                     guete=HOCH,
                     grund=f"Name im Produktinformationsblatt: "
                           f"{satz.get('name', '')}")

    # ------------------------------------------------------------ Betrag

    def ueber_betrag(self, anbieter: str, betrag: Optional[float]
                     ) -> Optional[Bezug]:
        """Der Weg mit Guete `mittel` - und nur bei EINDEUTIGKEIT.

        Treffen zwei Tarife desselben Anbieters denselben Monatsbetrag, ist
        die Zuordnung nicht schwach, sondern gar keine. Dann lieber nichts:
        ein Buendelpreis ohne aufloesbaren Tarif wird verworfen, und das
        ist die richtige Folge.
        """
        if betrag is None:
            return None
        treffer = [s for s in self.saetze(anbieter)
                   if s.get("grundgebuehr") is not None
                   and abs(float(s["grundgebuehr"]) - float(betrag)) < _CENT]
        if len(treffer) != 1:
            if treffer:
                log.info("Tarifbezug ueber Betrag %.2f bei %s ist nicht "
                         "eindeutig (%d Tarife) - verworfen",
                         float(betrag), anbieter, len(treffer))
            return None
        satz = treffer[0]
        return Bezug(
            tarif_id=satz["tarif_id"], tarif_name=satz.get("name", ""),
            guete=MITTEL,
            grund=(f"Monatsbetrag {float(betrag):.2f} EUR trifft im Bestand "
                   f"genau einen Tarif dieses Anbieters"))

    # ------------------------------------------------------------ beides

    def loese(self, anbieter: str, referenz: str = "",
              betrag: Optional[float] = None) -> Optional[Bezug]:
        """Erst der Name, dann der Betrag. Nie umgekehrt.

        Ein Name, der trifft, ist die staerkere Aussage; ihn zugunsten
        eines gleich hohen Betrags zu uebergehen hiesse, eine Messung durch
        eine Wahrscheinlichkeit zu ersetzen.
        """
        return (self.ueber_namen(anbieter, referenz)
                or self.ueber_betrag(anbieter, betrag))
