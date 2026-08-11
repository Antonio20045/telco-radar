"""Sendeplan, Idempotenz, Limit-Waechter, Bounce-Abgleich.

**Die Idempotenz ist das Wichtigste, wichtiger als alles andere in diesem
Paket.** Der teuerste denkbare Fehler ist, dass zweihundert Manager denselben
Wochenbericht ein zweites Mal bekommen: nicht rueckgaengig zu machen, kostet
sofort Vertrauen, und ein Actions-Re-Run oder ein doppeltes
`repository_dispatch` reicht dafuer aus.

Der naive Satz "nach jeder Zustellung sofort ins Log schreiben" ist in einem
Git-Store nicht umsetzbar. Ein Commit plus Push je Empfaenger waeren
zweihundert Pushes pro Lauf. Ein rein lokaler Schreibvorgang ist bei einem
Runner-Absturz komplett verloren - und der Wiederanlauf begeht dann genau den
Fehler, den das Log verhindern soll. Deshalb DREISTUFIG:

  1. **Vor dem Versand** wird ein deterministischer Sendeplan geschrieben und
     gepusht: alle Idempotenzschluessel des Laufs, Status `geplant`.
  2. **Waehrend des Versands** wird jede Zustellung einzeln ans Log
     angehaengt - ein HTTP-Aufruf ueber die Contents-API mit
     `sha`-Vorbedingung, kein Git-Push. Bei paralleler Aenderung schlaegt er
     FEHL statt zu ueberschreiben.
  3. **Beim Wiederanlauf** gilt: `geplant` ohne Zustellbestaetigung wird
     erneut versucht, alles mit Bestaetigung uebersprungen. Der Zustand
     "gesendet, Log-Schreiben fehlgeschlagen" gilt als GESENDET - im Zweifel
     lieber eine Mail zu wenig als eine zu viel.

**Der Limit-Waechter ist im Alltag naeher als die Idempotenz.** Brevos
Free-Plan erlaubt 300 Mails pro Tag; das ist keine ferne Grenze, sondern die
Verteilerobergrenze, und sie wird beim 301. Abonnenten gerissen. Gezaehlt
wird deshalb VOR dem Start, und zwar die geplanten Zustellungen PLUS das, was
heute laut Sendeprotokoll schon draussen ist - sonst reisst ein Wiederanlauf
oder eine Testausgabe das Limit. Bei Ueberschreitung bricht der Lauf ab. Ein
stiller Teilversand, bei dem die halbe Liste die Ausgabe bekommt und die
andere nicht, ist der schlimmste moegliche Ausgang.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .segments import Segment
from .store import lies_jsonl
from .subscription import jetzt
from .transport import Ergebnis, Transport

log = logging.getLogger(__name__)

# Brevos hartes Tageslimit ist 300. Der Waechter arbeitet gegen 280 - die
# Reserve faengt die Bestaetigungsmails von Neuanmeldungen desselben Tages
# ab, die aus einem anderen Workflow kommen und im Sendeprotokoll des
# Versands gar nicht auftauchen.
TAGESLIMIT = 300
SCHWELLE = 280

# 30 Mails je Minute. Nicht wegen einer Ratengrenze, sondern weil ein
# gleichmaessiger Strom bei Empfaenger-Gateways anders bewertet wird als
# zweihundert Zustellungen in acht Sekunden.
RATE_JE_MINUTE = 30


@dataclass(frozen=True)
class Sendeschluessel:
    """`report_date` + `segment_hash` + `subscriber_id`. Sonst nichts.

    Absichtlich OHNE Zeitstempel und ohne Versuchszaehler: der Schluessel
    muss beim Wiederanlauf denselben Wert ergeben, sonst haelt der Lauf
    seinen eigenen Sendeplan fuer einen fremden.
    """
    datum: str
    segment: str
    abo: str

    def __str__(self) -> str:
        return f"{self.datum}|{self.segment}|{self.abo}"


@dataclass
class Planposten:
    schluessel: Sendeschluessel
    status: str = "geplant"            # geplant | gesendet | dauerhaft_fehl
    message_id: str = ""
    at: str = ""

    def as_dict(self) -> dict:
        return {"key": str(self.schluessel), "date": self.schluessel.datum,
                "segment": self.schluessel.segment, "sub": self.schluessel.abo,
                "status": self.status, "message_id": self.message_id,
                "at": self.at}


def baue_sendeplan(datum: str, segmente: list[Segment]) -> list[Planposten]:
    """Der Plan des Laufs - deterministisch, also beim Wiederanlauf gleich.

    Leere Segmente kommen NICHT hinein. Eine Ausgabe, in der nichts steht,
    wird nicht verschickt: zweimal pro Woche eine leere Mail erzieht zum
    Ignorieren, und zwar nicht nur fuer die leeren Ausgaben.
    """
    plan: list[Planposten] = []
    for segment in segmente:
        if segment.leer:
            continue
        for abo_id in sorted(segment.abo_ids):
            plan.append(Planposten(
                schluessel=Sendeschluessel(datum, segment.hash, abo_id)))
    plan.sort(key=lambda p: str(p.schluessel))
    return plan


# ==========================================  Was schon zugestellt wurde  ===

def bereits_zugestellt(log_pfad: Path) -> set[str]:
    """Jeder Schluessel mit Zustellbestaetigung.

    "Gesendet, Log-Schreiben fehlgeschlagen" laesst sich von aussen nicht von
    "gar nicht gesendet" unterscheiden - deshalb zaehlt hier auch ein
    dauerhaft gescheiterter Versuch als erledigt. Im Zweifel lieber eine Mail
    zu wenig als eine zu viel.
    """
    return {str(e.get("key")) for e in lies_jsonl(log_pfad)
            if e.get("status") in ("gesendet", "dauerhaft_fehl")}


def heute_versendet(log_pfad: Path, *, heute: str = "") -> int:
    """Wie viele Mails HEUTE schon draussen sind - ueber alle Ausgaben.

    Gezaehlt wird der Zeitpunkt der Zustellung (`at`), NICHT das
    Ausgabedatum: ein Wiederanlauf am Folgetag gehoert zum Kontingent des
    Folgetags, und eine nachgeholte Ausgabe vom Dienstag zaehlt am Mittwoch.
    """
    tag = heute or date.today().isoformat()
    return sum(1 for e in lies_jsonl(log_pfad)
               if e.get("status") == "gesendet"
               and str(e.get("at") or "").startswith(tag))


class LimitGerissen(RuntimeError):
    """Der Lauf bricht ab, statt die halbe Liste zu bedienen."""


def pruefe_limit(geplant: int, log_pfad: Path, *, heute: str = "",
                 schwelle: int = SCHWELLE) -> int:
    """Passt der Lauf ins Tageskontingent? Gibt den Abstand zum Limit zurueck.

    Wirft `LimitGerissen`, wenn nicht. Ein stiller Teilversand ist der
    schlimmste moegliche Ausgang: ein Teil der Empfaenger bekommt die
    Ausgabe, der Rest nicht - und zwar stumm.
    """
    schon = heute_versendet(log_pfad, heute=heute)
    summe = schon + geplant
    if summe > schwelle:
        raise LimitGerissen(
            f"{geplant} geplant + {schon} heute bereits versendet = {summe}, "
            f"Schwelle {schwelle} (Brevo Free: {TAGESLIMIT}/Tag). Der Lauf "
            f"bricht ab - ein Teilversand waere schlimmer. Ausbaustufe B "
            f"(zwei Tage oder bezahlter Plan) steht in docs/mail-setup.md.")
    return schwelle - summe


# ===============================================================  Versand ==

@dataclass
class Lauf:
    """Was ein Versandlauf getan hat - die Zahlen fuer die Statuszeile."""
    datum: str
    segmente: int = 0
    geplant: int = 0
    zugestellt: int = 0
    uebersprungen: int = 0
    fehler: int = 0
    dauerhaft_fehl: list[str] = field(default_factory=list)
    abstand_zum_limit: int = 0

    def as_dict(self) -> dict:
        return {"date": self.datum, "segments": self.segmente,
                "planned": self.geplant, "delivered": self.zugestellt,
                "skipped": self.uebersprungen, "failed": self.fehler,
                "hard_fail": len(self.dauerhaft_fehl),
                "limit_left": self.abstand_zum_limit}


def versende(plan: list[Planposten], nachrichten: dict, adressen: dict,
             transport: Transport, *, log_pfad: Path, datum: str,
             protokollieren=None, rate_je_minute: int = RATE_JE_MINUTE,
             schwelle: int = SCHWELLE, heute: str = "",
             schlafen=time.sleep) -> Lauf:
    """Den Plan abarbeiten. `protokollieren(posten)` haengt ans Log an.

    `nachrichten` bildet `segment_hash -> Nachricht` ab, `adressen`
    `abo_id -> E-Mail`. Beide werden vom Aufrufer gestellt: dieses Modul
    kennt weder Store noch Renderer, damit es ohne beides testbar bleibt.
    """
    erledigt = bereits_zugestellt(log_pfad)
    offen = [p for p in plan if str(p.schluessel) not in erledigt]
    lauf = Lauf(datum=datum, geplant=len(plan),
                uebersprungen=len(plan) - len(offen),
                segmente=len({p.schluessel.segment for p in plan}))

    # Der Waechter zaehlt die OFFENEN - was schon draussen ist, geht nicht
    # noch einmal aufs Kontingent.
    lauf.abstand_zum_limit = pruefe_limit(len(offen), log_pfad, heute=heute,
                                          schwelle=schwelle)

    pause = 60.0 / rate_je_minute if rate_je_minute > 0 else 0.0
    for i, posten in enumerate(offen):
        # Zwei Schluessel, und der genauere gewinnt. Gerendert wird EINMAL je
        # Segment - das ist der ganze Sinn der Segmentierung -, aber die
        # Abmelde-URL traegt ein Token je Abo. Der Aufrufer legt die
        # personalisierte Fassung deshalb unter dem vollen Sendeschluessel
        # ab; wo es nichts zu personalisieren gibt (Tests, Trockenlauf),
        # reicht der Segmentschluessel.
        nachricht = (nachrichten.get(str(posten.schluessel))
                     or nachrichten.get(posten.schluessel.segment))
        adresse = adressen.get(posten.schluessel.abo)
        if nachricht is None or not adresse:
            # Ein Abo ohne Adresse ist abgemeldet, ein Segment ohne Nachricht
            # war leer. Beides ist kein Fehler - aber es gehoert ins Log,
            # sonst versucht es jeder Wiederanlauf erneut.
            posten.status = "dauerhaft_fehl"
            posten.at = jetzt()
            lauf.dauerhaft_fehl.append(posten.schluessel.abo)
            if protokollieren:
                protokollieren(posten)
            continue
        ergebnis: Ergebnis = transport.send(nachricht, adresse)
        posten.at = jetzt()
        if ergebnis.ok:
            posten.status = "gesendet"
            posten.message_id = ergebnis.message_id
            lauf.zugestellt += 1
        elif ergebnis.dauerhaft:
            posten.status = "dauerhaft_fehl"
            lauf.dauerhaft_fehl.append(posten.schluessel.abo)
            lauf.fehler += 1
        else:
            # Wiederholbar: NICHT ins Log. Der naechste Lauf findet den
            # Posten als `geplant` ohne Bestaetigung und versucht es erneut -
            # genau dafuer ist der Sendeplan da.
            lauf.fehler += 1
            log.warning("Zustellung fehlgeschlagen (wiederholbar), Status %s",
                        ergebnis.status)
            continue
        if protokollieren:
            protokollieren(posten)
        if pause and i < len(offen) - 1:
            schlafen(pause)
    return lauf


# =========================================================  Bounce-Abgleich

# Ein Hard Bounce oder eine Beschwerde schaltet SOFORT ab. Soft Bounces erst
# nach fuenf in Folge: ein volles Postfach ist in drei Tagen wieder leer, und
# wer dafuer eine lebende Adresse wegwirft, verliert einen Leser fuer immer.
HARTE_EREIGNISSE = {"hard_bounce", "hardBounce", "blocked", "spam",
                    "complaint", "invalid_email", "unsubscribed"}
WEICHE_EREIGNISSE = {"soft_bounce", "softBounce", "deferred", "error"}
SOFT_GRENZE = 5


@dataclass
class Bounceergebnis:
    abgeschaltet: list[str] = field(default_factory=list)
    weich: list[str] = field(default_factory=list)
    unbekannt: int = 0
    letzter_zeitpunkt: str = ""


def werte_ereignisse_aus(ereignisse, message_id_zu_abo: dict,
                         bounce_stand: dict) -> Bounceergebnis:
    """Aus Brevo-Ereignissen wird "diese Abos sind tot".

    Zugeordnet wird ueber die **Message-ID** aus dem Sendeprotokoll, nicht
    ueber die Adresse: die Adresse steht in den Ereignissen zwar drin, aber
    sie muesste dann durch dieses Modul und ins Log - und im Log darf keine
    stehen.

    `bounce_stand` bildet `abo_id -> {"hard": n, "soft": n}` ab und wird
    NICHT veraendert; der Aufrufer entscheidet, was er damit macht.
    """
    ergebnis = Bounceergebnis()
    for ereignis in ereignisse or []:
        typ = str(ereignis.get("event") or "")
        wann = str(ereignis.get("date") or ereignis.get("ts") or "")
        if wann > ergebnis.letzter_zeitpunkt:
            ergebnis.letzter_zeitpunkt = wann
        abo = message_id_zu_abo.get(str(ereignis.get("messageId") or ""))
        if not abo:
            ergebnis.unbekannt += 1
            continue
        if typ in HARTE_EREIGNISSE:
            if abo not in ergebnis.abgeschaltet:
                ergebnis.abgeschaltet.append(abo)
        elif typ in WEICHE_EREIGNISSE:
            stand = int((bounce_stand.get(abo) or {}).get("soft") or 0) + 1
            ergebnis.weich.append(abo)
            if stand >= SOFT_GRENZE and abo not in ergebnis.abgeschaltet:
                ergebnis.abgeschaltet.append(abo)
    return ergebnis


def zustellquote(lauf: Lauf) -> float:
    """Anteil der zugestellten an den versuchten. 1.0, wenn nichts anlag."""
    versucht = lauf.geplant - lauf.uebersprungen
    return round(lauf.zugestellt / versucht, 4) if versucht else 1.0
