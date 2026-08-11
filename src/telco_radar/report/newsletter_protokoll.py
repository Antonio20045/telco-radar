"""Der Newsletter-Abschnitt der Quellenseite: nur Zahlen, nie Adressen.

**Warum das auf `transparenz.html` steht und nicht in einem eigenen
Dashboard.** Nach acht Wochen prueft niemand mehr Zustellquote, Rueckläufer
und Abmeldungen - das ist der Normalfall und keine Nachlaessigkeit. Ein
eigenes Dashboard waere ein zweiter Ort, an den niemand geht. Die
Quellenseite ist der Ort, an dem in diesem Projekt ohnehin nachgesehen wird,
wenn etwas komisch aussieht.

**Zwei Warnschwellen, und die zweite ist die, die im Alltag zuerst
anschlaegt:**

  * Zustellquote unter 95 Prozent oder mehr als drei harte Rueckläufer in
    einem Lauf - schleichender Verfall der Absenderreputation.
  * **Ab 80 Prozent des Tageskontingents.** Brevos Free-Plan erlaubt 300
    Mails am Tag; das ist keine ferne Grenze, sondern die
    Verteilerobergrenze, und sie wird beim 301. Abonnenten gerissen. Der
    Abstand steht in JEDER Zeile, damit sichtbar wird, wann der Verteiler an
    die Grenze waechst - nicht erst, wenn er sie gerissen hat.

`data/state/newsletter_stats.jsonl` traegt ausschliesslich Summen. Ein
CI-Test prueft die Datei gegen ein Adressmuster; er ist die zweite
Sicherung, nachdem die erste (die Trennung der Repositories) schon greift.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Aus versand.py gespiegelt, damit die Seite nicht das Versandmodul importieren
# muss (das lebt im Lauf, nicht im Renderer). Ein Test haelt beide gegeneinander
# - zwei Zahlen fuer dasselbe Limit waeren zwei Limits.
TAGESLIMIT = 300
WARNUNG_AB_ANTEIL = 0.80
MIN_ZUSTELLQUOTE = 0.95
MAX_HARTE_FEHLER = 3


@dataclass
class Ausgabe:
    datum: str
    segmente: int = 0
    geplant: int = 0
    zugestellt: int = 0
    uebersprungen: int = 0
    fehler: int = 0
    dauerhaft_fehl: int = 0
    abstand_zum_limit: int = TAGESLIMIT
    neu: int = 0
    abmeldungen: int = 0
    bounces: int = 0

    @property
    def zustellquote(self) -> float:
        versucht = self.geplant - self.uebersprungen
        return round(self.zugestellt / versucht, 4) if versucht else 1.0

    @property
    def quote_prozent(self) -> int:
        return int(round(self.zustellquote * 100))

    @property
    def auslastung(self) -> int:
        """Wie viel des Tageskontingents dieser Lauf gebraucht hat, in Prozent."""
        gebraucht = TAGESLIMIT - self.abstand_zum_limit
        return int(round(100 * gebraucht / TAGESLIMIT)) if TAGESLIMIT else 0

    @property
    def warnungen(self) -> list[str]:
        """Die Saetze, die ueber der Tabelle stehen. Leer ist der Normalfall.

        Formuliert als BEFUND mit Zahl, nicht als Handlungsaufforderung -
        dieselbe Regel wie auf jeder anderen Seite dieses Portals.
        """
        aus = []
        if self.geplant and self.zustellquote < MIN_ZUSTELLQUOTE:
            aus.append(f"Zustellquote {self.quote_prozent} % — unter "
                       f"{int(MIN_ZUSTELLQUOTE * 100)} %.")
        if self.dauerhaft_fehl > MAX_HARTE_FEHLER:
            aus.append(f"{self.dauerhaft_fehl} dauerhaft gescheiterte "
                       f"Zustellungen in einem Lauf.")
        if self.auslastung >= int(WARNUNG_AB_ANTEIL * 100):
            aus.append(f"{self.auslastung} % des Tageskontingents gebraucht "
                       f"({TAGESLIMIT} Mails/Tag im Brevo-Free-Plan). Ab hier "
                       f"lohnt der Blick in docs/mail-setup.md, Ausbaustufe B.")
        return aus


def lade(pfad: Path, *, grenze: int = 12) -> list[Ausgabe]:
    """Die letzten `grenze` Ausgaben, juengste zuerst.

    Eine fehlende Datei ist der Normalzustand vor dem ersten Versand und
    kein Fehler - die Seite zeigt dann den Abschnitt gar nicht.
    """
    if not Path(pfad).exists():
        return []
    aus: list[Ausgabe] = []
    for zeile in Path(pfad).read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            daten = json.loads(zeile)
        except json.JSONDecodeError:
            log.warning("newsletter_stats.jsonl: Zeile nicht lesbar")
            continue
        aus.append(Ausgabe(
            datum=str(daten.get("date") or ""),
            segmente=int(daten.get("segments") or 0),
            geplant=int(daten.get("planned") or 0),
            zugestellt=int(daten.get("delivered") or 0),
            uebersprungen=int(daten.get("skipped") or 0),
            fehler=int(daten.get("failed") or 0),
            dauerhaft_fehl=int(daten.get("hard_fail") or 0),
            abstand_zum_limit=int(daten.get("limit_left") or TAGESLIMIT),
            neu=int(daten.get("new") or 0),
            abmeldungen=int(daten.get("unsubscribed") or 0),
            bounces=int(daten.get("bounced") or 0)))
    aus.sort(key=lambda a: a.datum, reverse=True)
    return aus[:grenze]


def aufbereiten(pfad: Path, *, grenze: int = 12) -> dict:
    """Was die Vorlage braucht. `None`-frei, damit kein `if` in der Vorlage."""
    ausgaben = lade(pfad, grenze=grenze)
    return {
        "vorhanden": bool(ausgaben),
        "ausgaben": ausgaben,
        "tageslimit": TAGESLIMIT,
        # Die Warnungen der JUENGSTEN Ausgabe stehen oben. Aeltere Warnungen
        # sind Geschichte; wer sie sucht, liest die Tabelle.
        "warnungen": ausgaben[0].warnungen if ausgaben else [],
        "summe_zugestellt": sum(a.zugestellt for a in ausgaben),
    }


def vermerken(pfad: Path, lauf: dict) -> None:
    """Eine Zeile anhaengen. **Nur Zahlen** - der Filter ist hier, nicht dort.

    Der Versandlauf lebt im privaten Repo und reicht sein Ergebnis per
    `repository_dispatch` herueber. Was von dort kommt, ist nicht
    vertrauenswuerdiger als jede andere Fremddaten-Quelle in diesem Projekt:
    also werden hier die BEKANNTEN Felder als Zahlen uebernommen und alles
    andere fallengelassen. Ein Feld mehr im Payload darf nicht bedeuten, dass
    eine Adresse ins oeffentliche Repo wandert.
    """
    felder = ("segments", "planned", "delivered", "skipped", "failed",
              "hard_fail", "limit_left", "new", "unsubscribed", "bounced")
    datum = str(lauf.get("date") or "")[:10]
    if not datum:
        raise ValueError("Laufzahlen ohne Datum")
    zeile = {"date": datum}
    for feld in felder:
        try:
            zeile[feld] = int(lauf.get(feld) or 0)
        except (TypeError, ValueError):
            zeile[feld] = 0
    Path(pfad).parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "a", encoding="utf-8") as datei:
        datei.write(json.dumps(zeile, sort_keys=True) + "\n")
