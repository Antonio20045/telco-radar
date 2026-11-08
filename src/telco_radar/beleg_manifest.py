"""Das Manifest der Belegbilder: was die Seite zeigt, abgeleitet aus den
Release-Anhängen.

``baue_manifest`` macht aus der Liste der Release-Anhänge (``beleg_ablage.Gh.anhaenge``)
``data/state/belege_manifest.json``. ``render_site`` liest nur diese Datei, ohne Netz
und ohne LLM. Der Dateiname trägt Gerät, Anbieter und Tag (``beleg_regeln.dateiname``);
der Downloadlink ergibt sich aus Release-Tag und Dateiname. Ein Eintrag kann eine
``bildfolge`` tragen (``beleg_bildfolge``); die Seite zeigt sie statt des Einzelbilds.

Ein Bild kann in beiden Releases liegen (Tag und Monat, große Änderung). Die Seite zeigt
es einmal, mit Kennzeichen ``gross``; liegt es nur im Monats-Release, ist es ebenfalls
groß. Die Adresse zeigt dann auf das Monats-Release, das länger lebt. Was
``ist_sichtbar`` verneint, kommt nicht hinein.
Kann der Geräte-Lauf das Manifest nicht erneuern (``gh`` hängt, scheitert), bleibt
der letzte Stand stehen und ``markiere_ausfall`` trägt Grund und Tag ein (Feld
``ausfall``); die Seite nennt ihn als Ausfall „Belegbilder“, statt einen alten
Stand als aktuell zu zeigen. Das
nächste erfolgreiche ``baue_manifest`` löscht den Vermerk.
Fremde Dateien in einem Release (falscher Name) bleiben still außen vor: das ist kein
Fehler der Seite, die Zählung steht in ``fremd``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .beleg_bildfolge import normalisiere as normalisiere_bildfolge
from .beleg_regeln import (
    REPO,
    ist_abgelaufen,
    ist_gross_tag,
    ist_sichtbar,
    zerlege_dateiname,
)

MANIFEST_NAME = "belege_manifest.json"
MANIFEST_DATEI = Path("data") / "state" / MANIFEST_NAME
FORMAT = 1
DOWNLOAD_BASIS = f"https://github.com/{REPO}/releases/download"


class BelegManifestFehler(ValueError):
    """Das Manifest ist unlesbar oder hat ein fremdes Format."""


@dataclass(frozen=True)
class Manifest:
    """Gelesenes Manifest: die Bilder und, falls vermerkt, der Grund der Störung."""

    belege: list[Beleg]
    ausfall: str | None = None


@dataclass(frozen=True)
class Beleg:
    """Ein Bild der Seite; ``gross`` = Aufbewahrung der großen Änderung."""

    geraet_id: str
    anbieter_id: str
    datum: date
    gross: bool
    url: str
    bildfolge: tuple[dict[str, str], ...] = ()

    def sichtbar(self, heute: date) -> bool:
        """Dieselbe Regel wie beim Löschen (``beleg_regeln.ist_abgelaufen``)."""
        return not ist_abgelaufen(self.datum, heute, self.gross)


def bild_url(tag: str, datei: str) -> str:
    """Download-Adresse eines Release-Anhangs."""
    return f"{DOWNLOAD_BASIS}/{tag}/{datei}"


def baue_manifest(anhaenge: Mapping[str, Sequence[str]], heute: date) -> dict:
    """Das Manifest für ``heute``; neueste Bilder zuerst, sonst nach Schlüssel."""
    gefunden: dict[tuple[str, str, str], dict] = {}
    fremd = 0
    for tag in sorted(anhaenge):
        for datei in anhaenge[tag]:
            name = zerlege_dateiname(datei)
            if name is None:
                fremd += 1
                continue
            if not ist_sichtbar(tag, datei, heute):
                continue
            schluessel = (name.geraet_id, name.anbieter_id, name.datum.isoformat())
            eintrag = gefunden.get(schluessel)
            gross = ist_gross_tag(tag) or bool(eintrag and eintrag["gross"])
            if eintrag is None or ist_gross_tag(tag):
                eintrag = {"url": bild_url(tag, datei)}
            gefunden[schluessel] = {**eintrag, "gross": gross}
    belege = [
        {"geraet_id": g, "anbieter_id": a, "datum": d, **rest}
        for (g, a, d), rest in gefunden.items()
    ]
    belege.sort(key=lambda b: (b["geraet_id"], b["anbieter_id"]))
    belege.sort(key=lambda b: b["datum"], reverse=True)
    return {
        "format": FORMAT,
        "erstellt": heute.isoformat(),
        "fremd": fremd,
        "belege": belege,
    }


def schreibe(pfad: Path, manifest: dict) -> None:
    """Schreibt das Manifest als JSON."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def markiere_ausfall(pfad: Path, grund: str, heute: date) -> None:
    """Vermerkt im bestehenden Manifest, dass es nicht erneuert wurde (Bilder bleiben).

    Fehlt das Manifest, entsteht ein leeres mit dem Vermerk: „keine Bilder“ ist dann
    nicht still, sondern benannt. Ein unlesbares Manifest wird nicht angefasst.
    """
    manifest = baue_manifest({}, heute)
    if pfad.is_file():
        try:
            alt = json.loads(pfad.read_text(encoding="utf-8"))
            if alt["format"] != FORMAT:
                raise ValueError(f"Format {alt['format']!r}")
            manifest = alt
        except (OSError, ValueError, KeyError, TypeError):
            return
    manifest["ausfall"] = f"{heute.isoformat()}: {grund}"
    schreibe(pfad, manifest)


def lies_manifest(pfad: Path) -> Manifest:
    """Bilder und Störungsvermerk; fehlt die Datei, ist sie leer; kaputt:
    ``BelegManifestFehler``.

    Eine fehlende Datei ist der Zustand vor dem ersten Lauf, keine Störung. Eine kaputte
    ist nie leer: sie wirft, und der Aufrufer benennt es.
    """
    if not pfad.is_file():
        return Manifest([])
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        if daten["format"] != FORMAT:
            raise BelegManifestFehler(f"Format {daten['format']!r}, erwartet {FORMAT}")
        belege = [
            Beleg(
                str(b["geraet_id"]),
                str(b["anbieter_id"]),
                date.fromisoformat(b["datum"]),
                bool(b["gross"]),
                str(b["url"]),
                normalisiere_bildfolge(b.get("bildfolge"), str(b["url"])),
            )
            for b in daten["belege"]
        ]
        ausfall = daten.get("ausfall")
        return Manifest(belege, str(ausfall) if ausfall else None)
    except (OSError, ValueError, KeyError, TypeError) as fehler:
        raise BelegManifestFehler(f"{pfad}: {fehler}") from fehler


def lies(pfad: Path) -> list[Beleg]:
    """Nur die Bilder (``lies_manifest``)."""
    return lies_manifest(pfad).belege
