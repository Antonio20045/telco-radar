"""Impressum, Datenschutzerklaerung und die Fassungen des Einwilligungstextes.

Drei Dinge stehen hier, und das dritte ist der eigentliche Grund fuer ein
eigenes Modul.

**Erstens: Inhalt und Code sind getrennt.** Die Rechtstexte liegen als Markdown
unter `content/legal/`, nicht in einer Vorlage. Wer eine Anschrift nachtraegt
oder einen Auftragsverarbeiter ergaenzt, aendert eine Textdatei - keine
Jinja-Vorlage, keinen Python-Code, keinen Test.

**Zweitens: die Fassung des Einwilligungstextes ist versioniert und gehasht.**
Eine Aufsichtsbehoerde fragt nach dem Wortlaut, dem der Betroffene DAMALS
zugestimmt hat, nicht nach dem von heute. `content/consent_texts/<datum>.md`
plus SHA-256 im Abo-Datensatz beantwortet das; ein Text, der sich nachtraeglich
aendert, faellt am Hash auf.

**Drittens - und das ist die Mechanik, die hier wirklich arbeitet: eine
Luecke im Impressum ist keine Formalie, sondern eine Sperre.** Ein Impressum
ohne ladungsfaehige Anschrift ist kein Impressum, und ein Formular, das ohne
eines Adressen einsammelt, sammelt sie rechtswidrig ein. Die Anschrift kann
diese Codebasis nicht selbst wissen - sie ist der eine Punkt, den nur ein
Mensch schliessen kann, wie `config/vodafone_hebel.yaml`.

Deshalb steht sie als Platzhalter `{{ANSCHRIFT}}` im Text, und
`vollstaendig()` rechnet daraus einen Zustand, den `render_site()` als
Jinja-Global setzt: solange ein Platzhalter offen ist, wird das
Anmeldeformular **nicht verlinkt**. Das ist dieselbe Veroeffentlichungsschwelle
wie bei der Geraeteseite, und aus demselben Grund rechnet sie der CODE und
nicht ein Test: eine Regel, die nur ein Test kennt, schaltet keine Navigation.

Die Seiten selbst werden trotzdem gebaut und zeigen die offene Stelle
sichtbar an. Ein Impressum, das seine Luecke benennt, ist ehrlicher als eines,
das sie versteckt - und es ist die Arbeitsliste fuer den Menschen.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

# Der Platzhalter traegt geschweifte Klammern, damit er in gerendertem HTML
# genauso auffaellt wie in der Quelldatei. Bewusst KEINE Jinja-Syntax mit
# Leerzeichen - diese Dateien laufen nie durch Jinja, und ein Muster, das wie
# eine Vorlage aussieht, laedt genau dazu ein, es eines Tages doch durch eine
# zu schicken.
_PLATZHALTER = re.compile(r"\{\{([A-ZÄÖÜ_]+)\}\}")

# Was ein offener Platzhalter im Text anstelle seiner selbst zeigt. Der Leser
# soll sehen, dass etwas fehlt - nicht eine Zeile, die zufaellig kurz aussieht.
_LUECKENTEXT = "— noch nicht eingetragen —"

SEITEN = {
    "impressum": ("impressum.md", "Impressum"),
    "datenschutz": ("datenschutz.md", "Datenschutzerklärung"),
}


@dataclass
class Rechtstext:
    schluessel: str
    titel: str
    markdown: str
    luecken: list[str] = field(default_factory=list)

    @property
    def vollstaendig(self) -> bool:
        return not self.luecken


def _legal_dir(root: Path) -> Path:
    return Path(root) / "content" / "legal"


def _consent_dir(root: Path) -> Path:
    return Path(root) / "content" / "consent_texts"


def lade(root: Path, schluessel: str) -> Rechtstext | None:
    """Einen Rechtstext laden. `None`, wenn die Datei fehlt.

    Eine fehlende Datei kippt keine Seite - sie fuehrt zu genau demselben
    Zustand wie ein offener Platzhalter: die Schwelle ist nicht erreicht.
    """
    datei_name, titel = SEITEN[schluessel]
    datei = _legal_dir(root) / datei_name
    if not datei.exists():
        return None
    roh = datei.read_text(encoding="utf-8")
    luecken = sorted(set(_PLATZHALTER.findall(roh)))
    text = _PLATZHALTER.sub(_LUECKENTEXT, roh)
    # Die Ueberschrift der Datei faellt weg: die Vorlage setzt den Titel als
    # <h1>, und `_md_to_html()` kennt `h1` gar nicht (die Zeile wuerde als
    # nackter Text im Fliesstext stehen). Der Titel der Seite steht in
    # SEITEN - eine Ueberschrift an zwei Orten waeren zwei Titel.
    text = re.sub(r"\A#\s+.*\n+", "", text)
    return Rechtstext(schluessel=schluessel, titel=titel, markdown=text,
                      luecken=luecken)


def alle(root: Path) -> list[Rechtstext]:
    vorhanden = (lade(root, s) for s in SEITEN)
    return [t for t in vorhanden if t is not None]


def vollstaendig(root: Path) -> bool:
    """Sind BEIDE Pflichtseiten da und ohne offene Stelle?

    Das ist die Bedingung, unter der das Anmeldeformular verlinkt werden
    darf. Sie ist absichtlich streng: fehlt die Datenschutzerklaerung, nuetzt
    ein vollstaendiges Impressum nichts - Art. 13 DSGVO verlangt die
    Information zum Zeitpunkt der Erhebung, also bevor jemand auf "Absenden"
    drueckt.
    """
    texte = alle(root)
    if len(texte) < len(SEITEN):
        return False
    return all(t.vollstaendig for t in texte)


def offene_stellen(root: Path) -> list[tuple[str, str]]:
    """(Seite, Platzhalter) fuer jede offene Stelle - die Arbeitsliste."""
    offen: list[tuple[str, str]] = []
    for schluessel, (datei_name, _) in SEITEN.items():
        text = lade(root, schluessel)
        if text is None:
            offen.append((schluessel, f"Datei fehlt: content/legal/{datei_name}"))
            continue
        offen.extend((schluessel, name) for name in text.luecken)
    return offen


# ------------------------------------------------------------ Einwilligung --

@dataclass
class Einwilligung:
    version: str
    text: str

    @property
    def hash(self) -> str:
        """SHA-256 des Wortlauts, mit Praefix wie im Abo-Datensatz.

        Gerechnet wird ueber den Text so, wie er auf der Seite steht -
        `strip()`, damit ein nachtraeglich angehaengter Zeilenumbruch nicht
        wie eine inhaltliche Aenderung aussieht. Anders als bei den
        personenbezogenen Kennwerten ist hier KEIN Pepper noetig und waere
        schaedlich: dieser Hash soll von jedem nachrechenbar sein, der den
        Text hat - genau darin besteht der Nachweis.
        """
        roh = hashlib.sha256(self.text.strip().encode("utf-8")).hexdigest()
        return f"sha256:{roh}"


def einwilligungs_fassungen(root: Path) -> list[Einwilligung]:
    """Alle Fassungen, aelteste zuerst. Der Dateiname IST die Version."""
    ordner = _consent_dir(root)
    if not ordner.exists():
        return []
    fassungen = []
    for datei in sorted(ordner.glob("*.md")):
        fassungen.append(Einwilligung(version=datei.stem,
                                      text=datei.read_text(encoding="utf-8")))
    return fassungen


def aktuelle_einwilligung(root: Path) -> Einwilligung | None:
    """Die juengste Fassung - die, der ein Neuzugang heute zustimmt."""
    fassungen = einwilligungs_fassungen(root)
    return fassungen[-1] if fassungen else None


def einwilligung(root: Path, version: str) -> Einwilligung | None:
    """Eine bestimmte Fassung - fuer den Nachweis zu einem alten Abo."""
    for fassung in einwilligungs_fassungen(root):
        if fassung.version == version:
            return fassung
    return None
