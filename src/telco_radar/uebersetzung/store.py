"""Was schon uebersetzt ist - und warum nichts davon je geloescht wird.

Der Schluessel ist `Item.id` (SHA-256 ueber die normalisierte URL, 16
Zeichen) PLUS ein Hash des Quelltexts. Beides zusammen, aus zwei Gruenden:

  - die `id` allein wuerde eine korrigierte Meldung nie neu uebersetzen,
  - der Texthash allein wuerde denselben Artikel unter zwei Adressen
    zweimal ablegen.

**Es wird nichts geloescht.** Ein Bericht aus dem Archiv verlinkt seine
Uebersetzung noch in einem Jahr; ein Aufraeumen nach Alter waere genau
Premortem 6 - tote Links im Archiv. Der Speicher waechst dafuer langsam:
gemessen rund 20-30 Uebersetzungen je Ausgabe.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path

log = logging.getLogger(__name__)


def text_hash(text: str) -> str:
    """Kurzer, stabiler Fingerabdruck des Quelltexts."""
    return hashlib.sha256(" ".join((text or "").split()).encode("utf-8")
                          ).hexdigest()[:12]


@dataclass
class Uebersetzung:
    """Eine fertige Uebersetzung, so wie sie auf der Seite erscheint."""

    item_id: str
    quell_hash: str
    titel_de: str
    absaetze: list[str] = field(default_factory=list)
    sprache: str = ""
    titel_original: str = ""
    url: str = ""
    quelle: str = ""
    datum: str = ""
    modell: str = ""
    erstellt_am: str = ""
    zeichen_original: int = 0
    herkunft: str = ""          # "feed" | "artikel"

    @property
    def zeichen(self) -> int:
        return sum(len(a) for a in self.absaetze)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Uebersetzung":
        bekannt = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in bekannt})


class UebersetzungsStore:
    """JSONL, eine Uebersetzung je Zeile.

    Die HTML-Seiten entstehen beim Rendern aus diesem Speicher - sie werden
    nicht einzeln versioniert. Das ist die Antwort auf Premortem 7: rund 30
    Seiten je Lauf mal 104 Laeufe waeren dreitausend Dateien in der
    git-Historie, und jede Aenderung an der Vorlage schriebe sie alle neu.
    Als JSONL steht je Uebersetzung EINE Zeile, und die aendert sich nie
    wieder.
    """

    def __init__(self, pfad: Path):
        self.pfad = Path(pfad)
        self._eintraege: dict[str, Uebersetzung] = {}
        self._laden()

    def _laden(self) -> None:
        if not self.pfad.exists():
            return
        for zeile in self.pfad.read_text(encoding="utf-8").splitlines():
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                u = Uebersetzung.from_dict(json.loads(zeile))
            except (json.JSONDecodeError, TypeError) as exc:
                log.warning("Uebersetzungsspeicher: Zeile uebersprungen (%s)",
                            exc)
                continue
            self._eintraege[u.item_id] = u

    def __len__(self) -> int:
        return len(self._eintraege)

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._eintraege

    def hat_aktuelle(self, item_id: str, quelltext: str) -> bool:
        """Liegt fuer GENAU diesen Textstand schon eine Uebersetzung vor?"""
        vorhanden = self._eintraege.get(item_id)
        return bool(vorhanden and vorhanden.quell_hash == text_hash(quelltext))

    def get(self, item_id: str) -> Uebersetzung | None:
        return self._eintraege.get(item_id)

    def alle(self) -> list[Uebersetzung]:
        return list(self._eintraege.values())

    def add(self, u: Uebersetzung) -> None:
        self._eintraege[u.item_id] = u

    def speichern(self) -> None:
        """Vollstaendig neu schreiben - der Bestand ist klein genug.

        Ein Anhaengen waere billiger, wuerde aber bei einer NEUEN Fassung
        derselben Meldung zwei Zeilen mit derselben `item_id` hinterlassen;
        beim naechsten Laden gewaenne dann die zufaellige Reihenfolge.
        """
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        zeilen = [json.dumps(u.to_dict(), ensure_ascii=False)
                  for u in self._eintraege.values()]
        self.pfad.write_text("\n".join(zeilen) + ("\n" if zeilen else ""),
                             encoding="utf-8")
