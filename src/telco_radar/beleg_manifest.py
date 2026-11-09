"""Das Manifest der Belegbilder: was die Seite zeigt, abgeleitet aus den
Release-Anhängen.

``baue_manifest`` macht aus der Liste der Release-Anhänge (``beleg_ablage.Gh.anhaenge``)
``data/state/belege_manifest.json``. ``render_site`` liest nur diese Datei, ohne Netz
und ohne LLM. Der Dateiname trägt Gerät, Anbieter und Tag (``beleg_regeln.dateiname``);
der Downloadlink ergibt sich aus Release-Tag und Dateiname. Ein Eintrag kann eine
``bildfolge`` tragen (``beleg_bildfolge``); die Seite zeigt sie statt des Einzelbilds.
Das Einzelbild einer Messung heißt ``…__preis__<kennung>.webp`` und trägt wie jeder
Schritt der Folge die Kennung der Position (``beleg_regeln.folge_dateiname``): eine
Folge besteht nur aus Bildern derselben Kennung. Ein altes Einzelbild ohne Kennung
bleibt ein Einzelbild ohne Folge.

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

from .beleg_bildfolge import PREIS, SCHRITTE
from .beleg_bildfolge import normalisiere as normalisiere_bildfolge
from .beleg_folgen import Folgeninfo
from .beleg_regeln import (
    REPO,
    Folgename,
    ist_abgelaufen,
    ist_gross_tag,
    ist_sichtbar,
    zerlege_dateiname,
    zerlege_folgename,
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


HINWEIS_UNVEROEFFENTLICHT = "Bild nicht veröffentlicht"


def _folge(
    schritte: Mapping[str, str], info: Folgeninfo | None
) -> tuple[list[dict[str, str]], list[str]]:
    """Bildfolge und Lücken einer Position in der Reihenfolge ``SCHRITTE``.

    ``schritte`` sind die veröffentlichten Bilder der Position (Schritt -> Adresse),
    der Schritt ``preis`` ist ihr Einzelbild."""
    texte = info.texte if info else {}
    gruende = info.fehlt if info else {}
    folge: list[dict[str, str]] = []
    fehlt: list[str] = []
    for schritt in SCHRITTE:
        adresse = schritte.get(schritt)
        if adresse is None:
            fehlt.append(
                f"{schritt}: {gruende.get(schritt, HINWEIS_UNVEROEFFENTLICHT)}"
            )
            continue
        folge.append(
            {"datei": adresse, "schritt": schritt, "text": texte.get(schritt, "")}
        )
    return folge, fehlt


def _merke_folge(
    folgebilder: dict[tuple[str, str, str], dict[str, dict[str, str]]],
    folge: Folgename,
    tag: str,
    datei: str,
) -> None:
    """Hält die Adresse eines Bilds der Position fest; liegt es auch im Monats-Release
    (große Änderung), gilt dieses, wie beim alten Einzelbild."""
    stellen = folgebilder.setdefault(folge.paar, {}).setdefault(folge.kennung, {})
    if folge.schritt not in stellen or ist_gross_tag(tag):
        stellen[folge.schritt] = bild_url(tag, datei)


def _setze_positionen(
    gefunden: dict[tuple[str, str, str], dict],
    folgebilder: dict[tuple[str, str, str], dict[str, dict[str, str]]],
    folgen: Mapping[str, Folgeninfo],
) -> int:
    """Setzt Einzelbild und Bildfolge aus den Bildern mit Kennung ein.

    Das Einzelbild einer Position heißt ``…__preis__<kennung>`` und trägt wie jeder
    Schritt die Kennung: eine Folge entsteht nur aus Bildern derselben Kennung, nie aus
    einem Einzelbild und Schritten, die nur zufällig am selben Tag liegen. Ein altes
    Einzelbild ohne Kennung bleibt ein Einzelbild. Folgebilder einer Kennung ohne ihr
    Einzelbild (nicht angekommen) zählen nicht. Zeigen zwei Kennungen mit Einzelbild auf
    dasselbe Paar, ist nicht beweisbar, welche gilt: keines davon, der Fall wird gezählt
    (``folge_verworfen``). Gibt die Zahl dieser Paare zurück."""
    verworfen = 0
    for schluessel, positionen in folgebilder.items():
        mit_einzelbild = {k: s for k, s in positionen.items() if PREIS in s}
        if len(mit_einzelbild) > 1:
            verworfen += 1
        elif mit_einzelbild:
            ((kennung, schritte),) = mit_einzelbild.items()
            url = schritte[PREIS]
            eintrag: dict = {"url": url, "gross": ist_gross_tag(url.rsplit("/", 2)[-2])}
            if len(schritte) > 1:
                eintrag["bildfolge"], eintrag["bildfolge_fehlt"] = _folge(
                    schritte, folgen.get(kennung)
                )
            gefunden[schluessel] = eintrag
    return verworfen


def baue_manifest(
    anhaenge: Mapping[str, Sequence[str]],
    heute: date,
    folgen: Mapping[str, Folgeninfo] | None = None,
) -> dict:
    """Das Manifest für ``heute``; neueste Bilder zuerst, sonst nach Schlüssel.

    ``folgen``: Beschriftung der Folgebilder je Kennung (``beleg_folgen.lies_folgen``);
    ohne sie tragen die Schritte keinen Text und keinen bekannten Lückengrund."""
    gefunden: dict[tuple[str, str, str], dict] = {}
    folgebilder: dict[tuple[str, str, str], dict[str, dict[str, str]]] = {}
    fremd = 0
    for tag in sorted(anhaenge):
        for datei in anhaenge[tag]:
            name = zerlege_dateiname(datei)
            if name is None:
                folge = zerlege_folgename(datei)
                if folge is None:
                    fremd += 1
                elif ist_sichtbar(tag, datei, heute):
                    _merke_folge(folgebilder, folge, tag, datei)
                continue
            if not ist_sichtbar(tag, datei, heute):
                continue
            schluessel = (name.geraet_id, name.anbieter_id, name.datum.isoformat())
            eintrag = gefunden.get(schluessel)
            gross = ist_gross_tag(tag) or bool(eintrag and eintrag["gross"])
            if eintrag is None or ist_gross_tag(tag):
                eintrag = {"url": bild_url(tag, datei)}
            gefunden[schluessel] = {**eintrag, "gross": gross}
    verworfen = _setze_positionen(gefunden, folgebilder, folgen or {})
    belege = [
        {"geraet_id": g, "anbieter_id": a, "datum": d, **rest}
        for (g, a, d), rest in gefunden.items()
    ]
    belege.sort(key=lambda b: (b["geraet_id"], b["anbieter_id"]))
    belege.sort(key=lambda b: b["datum"], reverse=True)
    manifest = {
        "format": FORMAT,
        "erstellt": heute.isoformat(),
        "fremd": fremd,
        "belege": belege,
    }
    if verworfen:
        manifest["folge_verworfen"] = verworfen
    return manifest


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
                normalisiere_bildfolge(b.get("bildfolge"), b.get("bildfolge_fehlt")),
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
