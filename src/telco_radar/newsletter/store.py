"""Der Abo-Speicher: JSONL-Zeilen, zusammengefuehrt statt gemerged.

**Warum diese Logik im OEFFENTLICHEN Repo liegt, obwohl die Daten im privaten
liegen.** Die naheliegende Aufteilung waere, den Store im privaten Repo zu
programmieren. Sie waere falsch: dort braeuchte er eine Kopie der
Filter-Engine, und eine Kopie driftet. Nach drei Monaten schickte die Mail
etwas anderes als die Website zeigt, und niemand koennte sagen, welche von
beiden stimmt - genau der Fehler, den "kein Modellaufruf im Versandpfad"
verhindern soll, nur eine Ebene tiefer.

Deshalb: **die Logik hier, die DATEN dort.** Der Versand-Workflow im privaten
Repo checkt dieses Repo beim Commit-SHA der Ausgabe aus und ruft diese
Funktionen auf. In diesem Repo liegt keine einzige Adresse - ein Test misst
das.

DIE DREI STELLEN, AN DENEN EIN FEHLER HIER STILL ABOS LOESCHT:

1. **`git pull --rebase` kann eine `age`-verschluesselte Datei NICHT
   zusammenfuehren.** Jeder Ciphertext unterscheidet sich bei jedem
   Schreibvorgang vollstaendig; jeder Konflikt ist ein Binaerkonflikt, und
   "ours" oder "theirs" wirft die halbe Liste weg. Deshalb
   `zusammenfuehren()` auf ZEILENEBENE: entschluesseln, mischen, neu
   verschluesseln.
2. **Beim Mischen gewinnt der juengere Zeitstempel, nicht "der andere".**
   Ein Abo, das gerade abgemeldet wurde, darf nicht von einer aelteren
   Fassung ueberschrieben werden, die es noch als aktiv kennt - sonst
   bekommt jemand nach seinem Widerruf weiter Post.
3. **Ein Abo verschwindet nie ganz.** Der Widerruf loescht die Adresse und
   laesst den Datensatz stehen; ohne ihn wuerde dieselbe Adresse beim
   naechsten Anmeldeversuch wieder angeschrieben, und ein Widerruf, der nach
   vier Wochen verfaellt, ist keiner.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import NewsletterKatalog
from .subscription import Abo, als_dict, aus_dict, jetzt

log = logging.getLogger(__name__)

# Wie lange eine Adresse nach einer Bestaetigungsmail gesperrt ist. Der
# Schutz gegen die Mailbomben-Nutzung, bei der jemand ein fremdes Postfach
# ueber ein offenes Formular zumuellt.
DOI_SPERRE_STUNDEN = 24


# ==========================================================  JSONL lesen  ==

def lies_jsonl(pfad: Path) -> list[dict]:
    """Zeilenweise, fehlertolerant. Eine kaputte Zeile kippt nicht die Datei.

    Das ist keine Bequemlichkeit: der Store wird von mehreren Workflows
    angefasst, und eine halb geschriebene Zeile darf nicht dazu fuehren, dass
    ein Lauf den GANZEN Verteiler fuer leer haelt und ihn neu schreibt.
    """
    if not Path(pfad).exists():
        return []
    aus = []
    for nummer, zeile in enumerate(
            Path(pfad).read_text(encoding="utf-8").splitlines(), 1):
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            daten = json.loads(zeile)
        except json.JSONDecodeError:
            log.error("Zeile %d nicht lesbar - uebersprungen (Inhalt nicht "
                      "geloggt, dort steht eine Adresse)", nummer)
            continue
        if isinstance(daten, dict):
            aus.append(daten)
    return aus


def schreibe_jsonl(pfad: Path, zeilen) -> None:
    Path(pfad).parent.mkdir(parents=True, exist_ok=True)
    Path(pfad).write_text(
        "".join(json.dumps(z, ensure_ascii=False, sort_keys=True) + "\n"
                for z in zeilen), encoding="utf-8")


# ======================================================  Zusammenfuehren  ==

def _zeitstempel(datensatz: dict) -> str:
    """Wann dieser Datensatz zuletzt etwas gesagt hat.

    Der GROESSTE der drei Zeitpunkte, nicht `created_at`: eine Abmeldung ist
    juenger als die Anmeldung, und sie muss gewinnen.
    """
    bounce = (datensatz.get("bounce") or {}).get("last") or ""
    return max(str(datensatz.get("created_at") or ""),
               str(datensatz.get("confirmed_at") or ""),
               str(bounce))


def zusammenfuehren(unsere: list[dict], fremde: list[dict]) -> list[dict]:
    """Zwei Staende auf ZEILENEBENE mischen. Der juengere Satz gewinnt.

    Das ist der Ersatz fuer `git pull --rebase`, der hier nicht arbeiten
    kann (siehe Modulkopf). Bei GLEICHEM Zeitstempel gewinnt der Satz, der
    weiter fortgeschritten ist: abgemeldet schlaegt aktiv, aktiv schlaegt
    pending. Sonst entschiede die Reihenfolge der Argumente, und dann haengt
    ein Widerruf davon ab, welcher Workflow zufaellig zuerst gepusht hat.
    """
    rang = {"unsubscribed": 3, "bounced": 2, "active": 1, "pending": 0}
    nach_id: dict[str, dict] = {}
    for datensatz in list(unsere) + list(fremde):
        schluessel = str(datensatz.get("id") or "")
        if not schluessel:
            continue
        vorhanden = nach_id.get(schluessel)
        if vorhanden is None:
            nach_id[schluessel] = datensatz
            continue
        meins = (_zeitstempel(datensatz),
                 rang.get(str(datensatz.get("state") or ""), 0))
        seins = (_zeitstempel(vorhanden),
                 rang.get(str(vorhanden.get("state") or ""), 0))
        if meins > seins:
            nach_id[schluessel] = datensatz
    # Stabil nach id: der Store wird gepusht und mit sich selbst verglichen.
    return [nach_id[k] for k in sorted(nach_id)]


# ============================================================  Der Store  ==

class AboStore:
    """Der entschluesselte Verteiler - er lebt nur zur Laufzeit im Runner."""

    def __init__(self, pfad: Path, katalog: NewsletterKatalog):
        self.pfad = Path(pfad)
        self.katalog = katalog
        self._roh: list[dict] = lies_jsonl(self.pfad)

    # -- lesen ------------------------------------------------------------
    @property
    def roh(self) -> list[dict]:
        return list(self._roh)

    def alle(self) -> list[Abo]:
        return [aus_dict(z, self.katalog) for z in self._roh]

    def aktive(self) -> list[Abo]:
        """Nur die, an die ueberhaupt zugestellt werden darf."""
        return [a for a in self.alle() if a.aktiv]

    def finde(self, abo_id: str) -> Abo | None:
        for datensatz in self._roh:
            if datensatz.get("id") == abo_id:
                return aus_dict(datensatz, self.katalog)
        return None

    def finde_ueber_kennwert(self, adress_kennwert: str) -> Abo | None:
        """Der Weg, der eine Abmeldung ueberlebt - die Adresse ist dann weg."""
        if not adress_kennwert:
            return None
        for datensatz in self._roh:
            if datensatz.get("email_hmac") == adress_kennwert:
                return aus_dict(datensatz, self.katalog)
        return None

    # -- schreiben --------------------------------------------------------
    def setze(self, abo: Abo) -> None:
        datensatz = als_dict(abo)
        for i, vorhanden in enumerate(self._roh):
            if vorhanden.get("id") == abo.id:
                self._roh[i] = datensatz
                break
        else:
            self._roh.append(datensatz)

    def speichern(self) -> None:
        """Schreiben - nach dem Mischen mit dem Stand auf der Platte.

        Ohne dieses Nachlesen ueberschreibt ein Lauf, der die Datei vor
        zwei Minuten gelesen hat, jede Aenderung, die inzwischen ein anderer
        Workflow geschrieben hat. Die `concurrency`-Gruppe der Workflows
        macht das unwahrscheinlich; sie macht es nicht unmoeglich.
        """
        aktuell = lies_jsonl(self.pfad)
        self._roh = zusammenfuehren(aktuell, self._roh)
        schreibe_jsonl(self.pfad, self._roh)


# =====================================  Die 24-Stunden-Sperre je Adresse ===
# HIER liegt der Mailbomben-Schutz, nicht im Signup-Dienst. Dessen Zaehler
# ist nach jedem Spin-down und jedem Deploy leer - wer ihn dort einbaut,
# baut ihn an der einzigen Stelle ein, an der er sicher nicht wirkt.


def doi_gesperrt(log_pfad: Path, adress_kennwert: str, *,
                 heute: datetime | None = None) -> bool:
    """Hat diese Adresse in den letzten 24 Stunden schon eine Mail bekommen?"""
    if not adress_kennwert:
        return True                     # ohne Kennwert keine Mail
    grenze = (heute or datetime.now(timezone.utc)) - timedelta(
        hours=DOI_SPERRE_STUNDEN)
    for eintrag in lies_jsonl(log_pfad):
        if eintrag.get("addr_hmac") != adress_kennwert:
            continue
        try:
            wann = datetime.fromisoformat(
                str(eintrag.get("at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if wann.tzinfo is None:
            wann = wann.replace(tzinfo=timezone.utc)
        if wann > grenze:
            return True
    return False


def doi_vermerken(log_pfad: Path, adress_kennwert: str, *,
                  token_id: str = "", zeitpunkt: str = "") -> None:
    """Den Versand einer Bestaetigungsmail festhalten.

    Im Log steht NUR der Kennwert, nie die Adresse - diese Datei liegt zwar
    im privaten Repo, aber sie hat keinen Grund, mehr zu wissen als noetig.
    """
    Path(log_pfad).parent.mkdir(parents=True, exist_ok=True)
    zeile = json.dumps({"addr_hmac": adress_kennwert,
                        "token_id": token_id,
                        "at": zeitpunkt or jetzt()},
                       ensure_ascii=False, sort_keys=True)
    with open(log_pfad, "a", encoding="utf-8") as datei:
        datei.write(zeile + "\n")


def doi_aufraeumen(log_pfad: Path, *, tage: int = 30,
                   heute: datetime | None = None) -> int:
    """Alte Eintraege wegwerfen. Gibt zurueck, wie viele gefallen sind.

    Das Log beantwortet genau eine Frage ueber 24 Stunden; alles Aeltere ist
    eine Datensammlung ohne Zweck - und damit nach Art. 5 Abs. 1 lit. e
    DSGVO eine, die nicht sein darf.
    """
    grenze = (heute or datetime.now(timezone.utc)) - timedelta(days=tage)
    eintraege = lies_jsonl(log_pfad)
    behalten = []
    for eintrag in eintraege:
        try:
            wann = datetime.fromisoformat(
                str(eintrag.get("at") or "").replace("Z", "+00:00"))
            if wann.tzinfo is None:
                wann = wann.replace(tzinfo=timezone.utc)
        except ValueError:
            continue                    # unlesbar -> weg
        if wann > grenze:
            behalten.append(eintrag)
    if len(behalten) != len(eintraege):
        schreibe_jsonl(log_pfad, behalten)
    return len(eintraege) - len(behalten)
