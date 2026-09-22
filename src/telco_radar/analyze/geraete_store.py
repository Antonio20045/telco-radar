"""Zustand und Historie des Geraete- und Preisradars.

Zwei Dateien, zwei Aufgaben:

    data/state/geraete_db.json      der AKTUELLE Stand je Listung
    data/state/geraete_preise.jsonl die AENDERUNGSPUNKTE des Preises

Warum getrennt? Der Auftrag verlangt "eine Zeile je (listung_id, Abrufdatum,
Preis), bei unveraendertem Preis keine neue Zeile, nur `zuletzt_gesehen`
aktualisieren". Ein `zuletzt_gesehen`, das sich jede Woche aendert, kann in
einer append-only-Datei nicht wohnen - es wuerde sie genau so fluten, wie die
Regel es verhindern soll. Also: die JSONL traegt ausschliesslich die Punkte,
an denen sich etwas GEAENDERT hat, und `last_verified` in der DB ist die
rechte Kante jeder Kurve. Zusammen ergeben sie eine vollstaendige
Treppenfunktion - bei einem Bruchteil der Zeilen.

DIE ZWEI REGELN, DIE DIESES MODUL TRAGEN
----------------------------------------
1. Ein Fehltreffer listet nichts aus. `mark_stale()` ist die Zwei-Stufen-
   Logik aus `promo_store.py`: aktiv -> vermutlich ausgelistet -> ausgelistet,
   und jede Wiederbestaetigung springt sofort auf aktiv zurueck. Ein einzelner
   Timeout beim Haendler darf nie als Portfolio-Ende in die Lifecycle-
   Statistik eingehen.
2. Ein fehlender Wert ist kein geaenderter Wert. Findet der Extraktor diesmal
   keinen Preis, schreibt die Historie NICHTS - kein Aenderungspunkt, kein
   "auf null gefallen". Dieselbe Lehre wie beim Tarif-Radar (CLAUDE.md §6).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from ..geraete_model import Listung

log = logging.getLogger(__name__)

STATUS_AKTIV = "aktiv"
STATUS_VERMUTLICH = "vermutlich ausgelistet"
STATUS_AUSGELISTET = "ausgelistet"

# Ab wie vielen Laeufen ohne einen einzigen Fund ein Anbieter als "vermarktet
# keine Hardware" gilt. Drei, nicht einer: nach einem leeren Lauf ist die
# wahrscheinlichere Erklaerung eine kaputte Quelle, und ein Anbieter, der zu
# Unrecht als SIM-only gefuehrt wird, verschwindet aus der Geraeteuebersicht,
# ohne dass jemand es merkt.
_LAEUFE_BIS_SIM_ONLY = 3

# --------------------------------------------------------------------------
# ABDECKUNGSWAECHTER (P1/C2, 22.09.2026)
# --------------------------------------------------------------------------
# Die Schwelle hiess bis heute AUSFALL_TAGE = 7: ein Anbieter galt als
# still, wenn er SIEBEN beobachtete Tage lang nichts lieferte. Gemessen an
# der Wirklichkeit war das zu langsam und zu grob - 50 Laeufe von
# `geraete.yml` waren gruen, darunter die sechs Tage, an denen die Telekom
# nichts geliefert hat. Ein Ausfall, der erst nach einer Woche laut wird,
# ist kein Waechter, sondern ein Nachruf. Verglichen wird deshalb mit dem
# VORTAG (genauer: mit dem letzten Messtag davor, siehe
# `GeraeteDB.ausfall_alarme`).
#
# Die vier Lesezustaende stehen im Bestand, weil die Zeilenzahl allein die
# entscheidende Frage nicht beantwortet: 0 Zeilen heisst entweder "gelesen,
# nichts gefunden" - das ist ein Ausfall - oder "gar nicht angefasst" - und
# das ist keine Aussage, sondern eine Luecke (CLAUDE.md Clean Code 4 und 6).
GELESEN = "gelesen"                # Einstieg vollstaendig gelesen
NICHT_GELESEN = "nicht gelesen"    # nicht angefasst: Besuchszeit, nicht
                                   # crawlbar, kein Adapter
LESEFEHLER = "lesefehler"          # Leseversuch gescheitert oder abgebrochen

# DER VIERTE ZUSTAND (S2-1, 22.09.2026). Bis hierher machte EIN einziger am
# Besuchsfenster abgewiesener Abruf den GANZEN Anbieter zu NICHT_GELESEN -
# auch den, der vier Produktseiten gelesen und drei Listungen geliefert
# hatte. Damit fiel er ganz aus dem Vergleich, und der Waechter war fuer
# medimax.de und ep.de im REGELFALL blind: genau diese zwei haengen jede
# Nacht an ihrem Fenster. "Gar nicht angefasst" und "teilweise gelesen,
# dann ging die Tuer zu" sind zwei Auskuenfte. Der Teiltag bleibt im
# Vergleich (er kann heute ausfallen wie jeder andere), taugt aber nicht
# als VERGLEICHSBASIS: was bis zum Fensterende durchkam, ist nicht das
# Sortiment (siehe `Messtag.vergleichsbasis`).
#
# DER PREIS DIESER REGEL, damit ihn niemand suchen muss: haengt ein
# Anbieter MEHRERE Tage hintereinander an seinem Fenster, bleibt er jeden
# dieser Tage ein Befund (die Basis ist ja der letzte vollstaendige Tag).
# Das ist gewollt - ein halb gelesener Anbieter ist eine halbe Abdeckung,
# und die gehoert gemeldet. GEMELDET wird sie deshalb trotzdem nicht
# taeglich: dafuer sorgt die Wiederholungssperre in
# `GeraeteDB.abdeckungsalarm` (S2-B).
TEILGELESEN = "teilweise gelesen"

# Die drei Alarmarten. Alle sind MELDUNG und greifen in nichts ein.
ALARM_AUSFALL = "ausfall"          # gestern Zeilen, heute keine
ALARM_RUECKGANG = "rueckgang"      # heute deutlich weniger Zeilen
# DIE DRITTE ART (S2-B, 22.09.2026). Ein Vergleich, der keine Basis mehr
# hat, ist kein ruhiger Tag - er ist ein blinder Waechter, und das ist
# selbst eine meldepflichtige Lage. Ohne diese Art verstummte der Kanal
# dauerhaft, sobald der letzte vollstaendig gelesene Tag aus dem Journal
# fiel: ein Anbieter, der nur noch Teiltage liefert, hat nach
# `_FUND_HISTORIE_TAGE` Tagen keine Basis mehr, und ein echter
# Totalausfall danach loeste nichts mehr aus.
ALARM_OHNE_BASIS = "ohne_basis"    # seit Tagen kein vollstaendiger Tag
# DIE VIERTE ART (S2-2, 22.09.2026). Seit tote Produktadressen eine
# benannte Luecke sind und keinen Lauf mehr kippen
# (`collect.geraete._MINDESTANTEIL_GELESENER_PRODUKTSEITEN`), kann ein
# Anbieter Nacht fuer Nacht knapp unter der Schwelle bleiben und trotzdem
# verschwinden: 24 % tote Adressen je Nacht reissen weder die Schwelle
# (sie laesst jede vierte zu) noch `ABDECKUNG_RUECKGANG` (der vergleicht
# mit GESTERN, und 24 % sind weniger als 30 %). Nach fuenf Naechten sind
# 0,76^5 = 24 % des Sortiments uebrig, und kein Kanal hat angeschlagen -
# laut wuerde es erst bei null Zeilen (`ALARM_AUSFALL`), also als Nachruf.
# Diese Art meldet deshalb den VERLAUF: nicht "heute weniger als gestern",
# sondern "seit dem aeltesten Messtag im Fenster ist zu viel weg".
ALARM_EROSION = "erosion"          # Sortiment broeselt ueber Tage weg

# Ab welchem ANTEIL Rueckgang gegenueber dem letzten Liefertag gemeldet
# wird. 0.30 und ECHT groesser: Sortiments- und Verfuegbarkeitsrauschen
# liegt darunter, der Verlust einer Kategorieseite darueber.
ABDECKUNG_RUECKGANG = 0.30

# IN WELCHEM ABSTAND EIN BLEIBENDER BEFUND ERNEUT GEMELDET WIRD (S2-B,
# 22.09.2026). Gemessen ueber 45 simulierte Tage: ein vollstaendiger Tag,
# danach nur Teiltage - der Waechter meldete denselben Satz an 29 Tagen
# hintereinander, jeden mit eigener Mail. Ein Kanal, der das tut, ist nach
# der dritten Mail ein Postfachfilter und damit so stumm wie einer, der
# nie meldet. Gemeldet wird deshalb beim ZUSTANDSWECHSEL und sonst an
# jedem siebten KALENDERTAG (`_ist_wiederholungstag`). Sieben, weil der
# Job taeglich laeuft: eine Woche unveraenderter Lage ist die naechste
# Nachfrage wert, ein Tag nicht.
_ALARM_WIEDERHOLUNG_TAGE = 7

# Ab wie vielen BEOBACHTETEN Tagen ohne einen einzigen vollstaendig
# gelesenen Tag die fehlende Vergleichsbasis selbst gemeldet wird
# (`ALARM_OHNE_BASIS`). Drei, nicht einer: ein einzelner Teiltag ist der
# Regelfall an einem Besuchsfenster und noch keine Luecke - drei
# beobachtete Tage ohne vollstaendigen Abruf sind eine.
_OHNE_BASIS_TAGE = 3

# Ueber wie viele MESSTAGE MIT ADRESSAUSKUNFT der Erosionsalarm zurueck
# vergleicht. Sieben, weil der Job taeglich laeuft: eine Woche ist der
# Horizont, in dem die Frage "seit wann eigentlich" noch beantwortbar ist,
# und derselbe Abstand, in dem ein bleibender Befund erneut gemeldet wird
# (`_ALARM_WIEDERHOLUNG_TAGE`). Gezaehlt werden Tage MIT Auskunft und nicht
# Kalendertage: ein Anbieter, der drei Naechte an seinem Besuchsfenster
# haengt, verliert dadurch seine Vergleichsbasis nicht.
#
# Gemessen an der Schwelle: bei 25 % toten Adressen je Nacht - genau dem,
# was `_MINDESTANTEIL_GELESENER_PRODUKTSEITEN` gerade noch durchlaesst -
# ist nach zwei Naechten mehr als `ABDECKUNG_RUECKGANG` weg. Das Fenster
# ist also nicht die Nachweisgrenze, sondern der Rand, bis zu dem auch
# eine LANGSAMERE Erosion (ab rund 5 % je Nacht) noch auffaellt.
_EROSION_FENSTER_TAGE = 7

# Wie viele Tage die Fund-Historie je Anbieter behaelt. Der Waechter
# vergleicht mit dem Vortag und braucht davon genau einen; der Rest traegt
# die Wiederholungssperre, die fehlende Vergleichsbasis und den
# Diagnose-Rand nach hinten (`stille_tage`, die Frage "seit wann eigentlich").
# Gemessen am geschriebenen State (`indent=1`, Eintragsform
# [Tag, Funde, Zustand, Buendel]): 30 Eintraege kosten rund 1,6 kB je
# Anbieter (~53 Byte je Eintrag), ueber alle neun Anbieter also unter
# 20 kB - ein Bruchteil einer einzigen Listung.
_FUND_HISTORIE_TAGE = 30

# Die Felder, deren Aenderung einen neuen Historienpunkt rechtfertigt.
_HISTORIENFELDER = ("preis_ohne_vertrag", "uvp", "preis_mit_vertrag_ab",
                    "zuzahlung", "tarif_referenz", "verfuegbarkeit")

# Welche davon ueberhaupt ein Preis sind - der allererste Messpunkt einer
# Listung wird nur geschrieben, wenn EINER davon einen Wert hat. Frueher
# stand hier nur `preis`/`uvp`, und eine Listung, deren einziger Preis ein
# Vertragspreis ist, bekam nie einen Historienpunkt.
_PREISFELDER = ("preis_ohne_vertrag", "uvp", "preis_mit_vertrag_ab", "zuzahlung")

# Die Felder, die die PREISFORM von `preis_ohne_vertrag` beschreiben. Sie
# gehoeren zusammen und zu genau der Zahl, mit der sie gemessen wurden -
# siehe `GeraeteDB.upsert`.
_PREISFORMFELDER = ("anzahlung", "monatsrate", "laufzeit_monate",
                    "zins_effektiv")


def tag_de(iso: str) -> str:
    """2026-09-21 -> 21.09.2026. Ein unbrauchbares Datum bleibt, wie es ist -
    lieber roh als falsch."""
    teile = str(iso or "").split("-")
    if len(teile) != 3 or not all(teile):
        return str(iso or "")
    return f"{teile[2]}.{teile[1]}.{teile[0]}"


@dataclass(frozen=True)
class Messtag:
    """Was ein Anbieter an EINEM Tag ergeben hat - und ob er gelesen wurde.

    `funde` sind Listungen (die Zahl, an der `stille_tage` und
    `hardware_vermarktung` haengen), `buendel` die Buendelsaetze desselben
    Tages. Der Waechter fragt nach der ABDECKUNG, und die ist beides
    zusammen: die Telekom liefert ausschliesslich Buendel - an ihren
    Listungen gemessen waere sie jeden Tag still, und genau ihr Ausfall
    war der Anlass dieses Waechters. Die Summe steht deshalb an genau
    EINER Stelle, hier.
    """
    tag: str
    funde: int
    buendel: int
    zustand: str
    # Die zwei ADRESSZAHLEN dieses Tages - die Groesse, in der die
    # Leseschwelle der Sammelstufe rechnet
    # (`collect.geraete._MINDESTANTEIL_GELESENER_PRODUKTSEITEN`), und
    # deshalb die einzige, in der sich ihr Verlauf ehrlich vergleichen
    # laesst. `versucht` sind die Produktadressen, an denen der Lauf
    # wirklich war, `tote` die davon, die der Anbieter selbst als nicht
    # mehr vorhanden beantwortet hat (HTTP 404/410).
    #
    # `tote is None` heisst "dieser Tag sagt dazu nichts" - ein Altbestand
    # ohne die Felder, ein uebersprungener Anbieter, ein Adapter ohne
    # Produktseiten. Keine 0: eine 0 waere die Auskunft "versucht, keine
    # war tot" und damit eine Entwarnung, die niemand gemessen hat
    # (CLAUDE.md Clean Code 3).
    versucht: int = 0
    tote: Optional[int] = None

    @property
    def zeilen(self) -> int:
        return self.funde + self.buendel

    @property
    def gelesene_adressen(self) -> Optional[int]:
        """Wie viele Produktadressen an diesem Tag wirklich gelesen wurden -
        oder `None`, wenn der Tag dazu nichts sagt.

        Die EINE Definition, aus der der Erosionsalarm seine Zahlenreihe
        baut (Clean Code 7: keine zweite Liste). `None` bei drei Lagen, und
        alle drei sind "keine Aussage" und nicht "null Adressen":
          * der Tag wurde nicht zu Ende gelesen (`zustand != GELESEN`) -
            dann ist die Zahl abgeschnitten, nicht gemessen, genau wie bei
            `vergleichsbasis`;
          * es wurde keine Produktadresse versucht;
          * der Tag stammt aus dem Altbestand und kennt die Felder nicht.
        """
        if self.zustand != GELESEN or self.versucht <= 0 or self.tote is None:
            return None
        return self.versucht - self.tote

    @property
    def beobachtet(self) -> bool:
        """Ist dieser Tag eine Aussage ueber die ABDECKUNG des Anbieters?

        Ein vollstaendig gelesener Tag ist es immer - auch mit null Zeilen.
        Ein nicht (oder nicht zu Ende) gelesener Tag nur dann, wenn er
        trotzdem etwas hergegeben hat: was da ist, ist gesehen worden.
        """
        return self.zustand == GELESEN or self.zeilen > 0

    @property
    def vergleichsbasis(self) -> bool:
        """Darf dieser Tag der VORTAG eines Vergleichs sein?

        Ein Teiltag nicht. Seine Zeilen sind das, was bis zum Fensterende
        durchkam - keine Aussage ueber die Abdeckung des Anbieters. Als
        Basis genommen senkte er die Messlatte auf seinen eigenen kleinen
        Wert: der echte Totalausfall am Folgetag faende dann nichts mehr,
        wogegen er auffallen koennte (bei 0 Zeilen am Teiltag gar keinen
        Alarm, siehe das dritte Tor in `GeraeteDB._befund`). Verglichen
        wird deshalb mit dem letzten VOLLSTAENDIG gelesenen Tag.

        Bleibt eine solche Basis ganz aus, ist DAS der Befund
        (`ALARM_OHNE_BASIS`) - ein Waechter ohne Vergleich schweigt
        nicht, er meldet seine Blindheit.
        """
        return self.beobachtet and self.zustand != TEILGELESEN

    @property
    def fundtag(self) -> bool:
        """Dieselbe Frage fuer LISTUNGEN statt Zeilen - die Menge, auf der
        `stille_tage` zaehlt.

        Der Unterschied ist genau ein Fall: ein abgebrochener Lauf, der nur
        Buendel mitbrachte. Fuer die Abdeckung ist das ein Lebenszeichen,
        fuer die Frage "wie lange findet dieser Anbieter schon keine
        Geraete mehr" keine Beobachtung - dort zaehlte er auch vor dem
        22.09.2026 nicht mit, weil er gar nicht erst geschrieben wurde.
        """
        return self.zustand == GELESEN or self.funde > 0


@dataclass(frozen=True)
class Abdeckungsalarm:
    """Ein Anbieter, dessen Abdeckung eingebrochen ist - oder fuer den es
    keinen Vergleich mehr gibt (`ALARM_OHNE_BASIS`).

    NUR MELDUNG, KEIN GRIFF: der Alarm altert nichts, loescht nichts und
    schaltet keine Navigation. Er steht im Protokoll, auf der Quellenseite
    und in der Mail - drei Kanaele, EIN Satz (`satz`), damit die Seite nicht
    etwas anderes behauptet als das Log.
    """
    anbieter: str
    art: str
    tag: str
    zeilen: int
    zustand: str
    # Die drei Vergleichsfelder sind `None`, wenn es KEINE Vergleichsbasis
    # gibt (`ALARM_OHNE_BASIS`) - eine benannte Luecke, keine 0 und kein
    # erfundener Tag (Clean Code 3). Bei den beiden anderen Arten sind sie
    # immer gefuellt.
    vortag: Optional[str]
    zeilen_vortag: Optional[int]
    # Anteil 0..1, und zwar der Groesse, die DIESE Alarmart misst: bei
    # `ALARM_AUSFALL`/`ALARM_RUECKGANG` die Zeilen, bei `ALARM_EROSION`
    # die gelesenen Produktadressen. Welche gemeint ist, sagt `satz` mit
    # Worten - hier steht nur die Zahl, damit `prozent` und die Sortierung
    # eine einzige Rechnung haben.
    rueckgang: Optional[float]
    stille_tage: int
    # Wie viele beobachtete Tage in Folge ohne einen einzigen vollstaendig
    # gelesenen Tag - nur bei `ALARM_OHNE_BASIS` eine Aussage.
    ohne_basis_tage: int = 0
    # Die gelesenen PRODUKTADRESSEN heute und am Bezugstag - nur bei
    # `ALARM_EROSION` eine Aussage, sonst `None`. Eigene Felder und nicht
    # `zeilen`/`zeilen_vortag` mitbenutzt: Adressen und Zeilen sind zwei
    # Groessen (45 Adressen trugen 133 Listungen), und ein Feld, das mal
    # das eine und mal das andere bedeutet, ist genau die Verwechslung,
    # gegen die diese Alarmart gebaut wurde.
    adressen: Optional[int] = None
    adressen_vortag: Optional[int] = None

    @property
    def prozent(self) -> Optional[int]:
        if self.rueckgang is None:
            return None
        return int(round(self.rueckgang * 100))

    @property
    def kurz(self) -> str:
        """Das Etikett am Anbieter - die Wortform, die auf der Seite steht."""
        if self.art == ALARM_AUSFALL:
            return "heute nicht erfasst"
        if self.art == ALARM_OHNE_BASIS:
            return "ohne vollständigen Abruf"
        if self.art == ALARM_EROSION:
            return "immer weniger Produktseiten"
        return "heute unvollständig erfasst"

    @property
    def satz(self) -> str:
        if self.art == ALARM_OHNE_BASIS:
            return (f"{self.anbieter}: {self.kurz} – {self.zeilen} Zeilen, "
                    f"seit {self.ohne_basis_tage} beobachteten Tagen kein "
                    f"vollständig gelesener Tag; der Vergleich hat keine "
                    f"Basis (Zustand {self.zustand}).")
        if self.art == ALARM_AUSFALL:
            return (f"{self.anbieter}: {self.kurz} – 0 Zeilen, am "
                    f"{tag_de(self.vortag)} waren es {self.zeilen_vortag} "
                    f"(Zustand {self.zustand}).")
        if self.art == ALARM_EROSION:
            return (f"{self.anbieter}: {self.kurz} – von "
                    f"{self.adressen_vortag} gelesenen Produktseiten am "
                    f"{tag_de(self.vortag)} sind heute {self.adressen} übrig "
                    f"({self.prozent} % weniger), aktuell {self.zeilen} "
                    f"Zeilen.")
        return (f"{self.anbieter}: {self.kurz} – {self.zeilen} Zeilen, am "
                f"{tag_de(self.vortag)} waren es {self.zeilen_vortag} "
                f"({self.prozent} % weniger).")

    def als_dict(self) -> dict:
        """Fuer die Seite: die Felder plus die zwei abgeleiteten Saetze.

        Die Vorlage bekommt fertige Wortformen und rechnet nichts - sonst
        stuenden Pruefung und Anzeige auf zwei Definitionen (Clean Code 7).
        """
        return {"anbieter": self.anbieter, "art": self.art, "tag": self.tag,
                "zeilen": self.zeilen, "zustand": self.zustand,
                "vortag": self.vortag, "zeilen_vortag": self.zeilen_vortag,
                "prozent": self.prozent, "stille_tage": self.stille_tage,
                "ohne_basis_tage": self.ohne_basis_tage,
                "adressen": self.adressen,
                "adressen_vortag": self.adressen_vortag,
                "kurz": self.kurz, "satz": self.satz}


def _befundschluessel(alarm: Abdeckungsalarm) -> tuple:
    """Woran sich erkennen laesst, ob die Lage DIESELBE ist wie gestern.

    Drei Stuecke, mehr nicht: die Alarmart, der Lesezustand und ob
    ueberhaupt Zeilen kamen. Die Zeilenzahl selbst gehoert NICHT dazu -
    sie schwankt taeglich, und jede Schwankung waere sonst ein
    "Zustandswechsel", der die Wiederholungssperre aushebelt.
    """
    return (alarm.art, alarm.zustand, alarm.zeilen > 0)


def _ist_wiederholungstag(tag: str) -> bool:
    """Ist heute der Tag, an dem ein BLEIBENDER Befund erneut gemeldet
    wird?

    Gezaehlt wird am KALENDER und nicht im Journal. Das Journal ist auf
    `_FUND_HISTORIE_TAGE` gedeckelt; jede Zaehlung darin verschiebt sich
    Tag fuer Tag mit seinem Rand, der Wiederholungstag waere dadurch nie
    der heutige, und der Waechter verstummte genau dort, wo er laut sein
    muss. Am Kalender trifft er verlaesslich einen Tag je Woche - egal,
    wie lange die Lage schon dauert und wie oft das Journal schon
    umgebrochen ist.

    Ein unlesbares Datum gilt als Wiederholungstag: lieber einmal zu viel
    gemeldet als einmal zu wenig.
    """
    try:
        ordnungszahl = date.fromisoformat(str(tag)).toordinal()
    except (TypeError, ValueError):
        return True
    return ordnungszahl % _ALARM_WIEDERHOLUNG_TAGE == 0


def _alarm_reihenfolge(alarm: Abdeckungsalarm) -> tuple:
    """Groesster Einbruch zuerst - und ganz vorn der Anbieter, fuer den es
    gar keinen Vergleich mehr gibt.

    Ein Alarm ohne Vergleichsbasis hat keinen messbaren Rueckgang. Ihn mit
    0 zu sortieren machte ihn zur leichtesten Lage; er ist die schwerste,
    denn dort ist der Waechter blind (Clean Code 3: kein erfundener Wert).
    """
    if alarm.rueckgang is None:
        return (0, 0.0, alarm.anbieter)
    return (1, -alarm.rueckgang, alarm.anbieter)


def _ist_ausfall(feld: str, wert) -> bool:
    """Steht dieser Wert fuer "diesmal nicht gemessen"?

    Bei Preisen ist das `None`. Bei der Verfuegbarkeit ist es der String
    "unbekannt" - sie ist nie None, also griff die Ausfallregel dort nie, und
    ein Lauf, der die Verfuegbarkeit nicht parsen konnte, schrieb fuer JEDE
    Listung eine Historienzeile. Aus "lieferbar -> unbekannt -> lieferbar"
    wurde so ein Lieferereignis, das es nie gab.
    """
    if feld == "verfuegbarkeit":
        return wert in (None, "", "unbekannt")
    return wert is None


def _als_listung(x) -> Listung:
    """Rohes dict oder Listung -> Listung.

    Der Umweg ueber den Konstruktor ist Absicht: er ist die Stelle, an der
    "kein Preis ohne Quelle und Abrufdatum" erzwungen wird. Wer ein dict
    hereinreicht, laeuft durch dieselbe Pruefung.
    """
    if isinstance(x, Listung):
        return x
    felder = dict(x)
    # Fehlende Pflichtfelder ausdruecklich leer setzen, statt Python einen
    # TypeError werfen zu lassen: der Aufrufer soll den SATZ hoeren, der die
    # Regel nennt ("kein Preis ohne Beleg"), nicht eine Signaturmeldung.
    felder.setdefault("quelle_url", "")
    felder.setdefault("abgerufen_am", "")
    return Listung(**felder)


# --------------------------------------------------------------------------
# Aktueller Stand
# --------------------------------------------------------------------------

class GeraeteDB:
    """data/state/geraete_db.json - je Listung eine Zeile ihres Lebens.

    Format: {"updated": "YYYY-MM-DD", "listungen": [...], "anbieter": {...}}.
    Es wird nie etwas geloescht; ein ausgelistetes Geraet bleibt stehen, denn
    genau daraus entsteht die Listungsdauer.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._eintraege: dict[str, dict] = {}
        self._anbieter: dict[str, dict] = {}
        self.updated = ""
        # Eine unlesbare Datei ist NICHT dasselbe wie "noch nichts gefunden".
        # Ohne dieses Feld schriebe die Seite "Der Geraetezweig laeuft, hat
        # aber noch keine Listung aufgenommen" - der Fallstrick aus
        # CLAUDE.md §6, nur eine Ebene hoeher.
        self.lesbar = True
        if self.path.exists():
            try:
                roh = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("geraete_db.json unlesbar (%s) - starte leer", exc)
                self.lesbar = False
                roh = {}
            self.updated = roh.get("updated", "")
            for e in (roh.get("listungen") or []):
                if e.get("id"):
                    self._eintraege[e["id"]] = e
            self._anbieter = dict(roh.get("anbieter") or {})

    # -------------------------------------------------------------- lesen

    def eintraege(self, status: Optional[Iterable[str]] = None) -> list[dict]:
        werte = list(self._eintraege.values())
        if status is not None:
            erlaubt = set(status)
            werte = [e for e in werte if e.get("status") in erlaubt]
        return sorted(werte, key=lambda e: (e.get("anbieter", ""), e.get("id", "")))

    def nach_id(self, listung_id: str) -> Optional[dict]:
        return self._eintraege.get(listung_id)

    def _finde_verwandten(self, listung: Listung) -> Optional[dict]:
        """Das Sicherheitsnetz gegen die gespaltene Identitaet.

        Die Farbe steckt in der `sku_id` - sie MUSS dort stecken, sonst waeren
        Titanschwarz und Titannatur dieselbe SKU. Der Preis dafuer: liefert die
        Quelle das Farbfeld in einem Lauf nicht mit (ein Ausfall, kein
        Verschwinden der Farbe), aendert sich die ID, und der Store sieht ein
        brandneues Geraet neben einem, das gerade Richtung "ausgelistet"
        altert. Genau der Fehler, den dieses Radar an keiner Stelle machen
        darf.

        Deshalb: eine unbekannte ID wird mit den Eintraegen desselben
        Anbieters, Geraets und Speichers abgeglichen. Passt genau EINER und
        widerspricht seine Farbe nicht (eine der beiden Seiten hat keine),
        ist es derselbe Artikel. Bei zwei Kandidaten wird nichts geraten -
        dann ist die Zuordnung nicht belegbar.

        Die ID wird dabei NIE umgeschrieben: sie entsteht bei der ersten
        Sichtung und bleibt. Die Farbe ist ein Feld des Eintrags, und ein
        spaeter nachgelieferter Farbwert fuellt es auf.
        """
        neu_farbe = listung.farbe_normalisiert or (listung.farbe_roh or "").lower()
        passend = []
        for e in self._eintraege.values():
            if (e.get("anbieter") != listung.anbieter
                    or e.get("device_id") != listung.device_id
                    or e.get("zustand", "neu") != listung.zustand
                    or e.get("status") not in (STATUS_AKTIV, STATUS_VERMUTLICH)):
                continue
            alt_speicher = e.get("speicher_gb")
            if (alt_speicher is not None and listung.speicher_gb is not None
                    and alt_speicher != listung.speicher_gb):
                continue
            alt_farbe = e.get("farbe_normalisiert") or (e.get("farbe_roh") or "").lower()
            if neu_farbe and alt_farbe and neu_farbe != alt_farbe:
                continue
            passend.append(e)
        return passend[0] if len(passend) == 1 else None

    # ------------------------------------------------------------ schreiben

    def upsert(self, listungen, today: str) -> tuple[int, set]:
        """Listungen aufnehmen oder auffrischen.

        Gibt (Zahl der NEU aufgenommenen, IDs ALLER in diesem Aufruf
        gesehenen) zurueck. Der zweite Wert MUSS an `mark_stale()` gehen -
        wer ihn dort neu berechnet, zaehlt gerade aufgefrischte Eintraege als
        Fehltreffer (dieselbe Falle wie in promo_store.upsert).
        """
        neu = 0
        gesehen: set[str] = set()
        self.kollisionen = []
        # Die ROHSAETZE, die dieser Aufruf wegen einer Kollision NICHT
        # eingetragen hat. Der Aufrufer braucht sie, um fuer sie auch keine
        # Historie zu schreiben - sonst entsteht genau die Saegezahnkurve,
        # die der Kommentar unten verhindern will, nur eine Stufe spaeter
        # (QA-Befund B2, 04.09.2026: ALDI TALKs Galaxy A17 sprang in
        # `geraete_preise.jsonl` jeden Tag zwischen 129 und 159 EUR).
        self.uebergangen: list = []
        for roh in listungen:
            listung = _als_listung(roh)
            lid = listung.listung_id
            eintrag = self._eintraege.get(lid)
            if eintrag is None:
                verwandt = self._finde_verwandten(listung)
                if verwandt is not None:
                    eintrag = verwandt
                    lid = eintrag["id"]
            if lid in gesehen:
                # Zwei Saetze DESSELBEN Laufs auf einer ID. Das kann nur
                # heissen, dass zwei Artikel nicht unterscheidbar waren (etwa
                # zwei Farben, die die Quelle diesmal nicht mitgeliefert hat).
                # Der zweite wird NICHT eingetragen - sonst schriebe die
                # Historie in jedem Lauf zwei Aenderungspunkte hin und zurueck
                # und die Kurve saehe aus wie ein Preiskampf.
                self.kollisionen.append((lid, listung.titel_roh))
                self.uebergangen.append(roh)
                continue
            gesehen.add(lid)
            if eintrag is None:
                eintrag = {
                    "id": lid,
                    "sku_id": listung.sku_id,
                    "device_id": listung.device_id,
                    "anbieter": listung.anbieter,
                    "anbieter_typ": listung.anbieter_typ,
                    "netz": listung.netz,
                    "speicher_gb": listung.speicher_gb,
                    "farbe_roh": listung.farbe_roh,
                    "farbe_normalisiert": listung.farbe_normalisiert,
                    "ean": listung.ean,
                    "zustand": listung.zustand,
                    "first_seen": today,
                    "status": STATUS_AKTIV,
                    "missed_checks": 0,
                    # Der Einfuehrungspreis - der erste Preis, den dieses
                    # Radar je fuer diese Listung gesehen hat. Bewusst NICHT
                    # der UVP: gemessen wird, was der Anbieter verlangt hat,
                    # nicht was der Hersteller empfiehlt.
                    #
                    # Mit seiner PREISART daneben: ein Einfuehrungspreis von
                    # 1449 Euro ohne Vertrag und eine spaetere Zuzahlung von
                    # 49,95 Euro ergaeben sonst 96,6 Prozent "Preisverfall" -
                    # die zwei Preisarten in einer Rechnung, genau das, was
                    # Teil C4 verbietet.
                    "erstpreis": listung.preis,
                    "erstpreis_art": listung.preisart if listung.preis is not None else "",
                    "erstpreis_am": today if listung.preis is not None else "",
                }
                self._eintraege[lid] = eintrag
                neu += 1
            else:
                eintrag["status"] = STATUS_AKTIV
                eintrag["missed_checks"] = 0
                eintrag.pop("stale_since", None)
                if eintrag.get("erstpreis") is None and listung.preis is not None:
                    eintrag["erstpreis"] = listung.preis
                    eintrag["erstpreis_art"] = listung.preisart
                    eintrag["erstpreis_am"] = today
                # Ein Feld, das die Quelle erst spaeter mitliefert, fuellt die
                # Luecke auf - ohne die ID anzufassen. Die entsteht bei der
                # ersten Sichtung und bleibt, sonst zerfaellt die Historie.
                if listung.speicher_gb is not None:
                    eintrag["speicher_gb"] = listung.speicher_gb
                if listung.farbe_roh:
                    eintrag["farbe_roh"] = listung.farbe_roh
                if listung.farbe_normalisiert:
                    eintrag["farbe_normalisiert"] = listung.farbe_normalisiert
                if listung.ean:
                    eintrag["ean"] = listung.ean

            eintrag["last_verified"] = today
            eintrag["letzter_check"] = today
            eintrag["quelle_url"] = listung.quelle_url
            eintrag["abgerufen_am"] = listung.abgerufen_am
            # "unbekannt" heisst "diesmal nicht gelesen", nicht "nicht mehr
            # lieferbar". Ein Ausfall darf den bekannten Wert nicht loeschen.
            if listung.verfuegbarkeit != "unbekannt" or not eintrag.get("verfuegbarkeit"):
                eintrag["verfuegbarkeit"] = listung.verfuegbarkeit
            eintrag["confidence"] = listung.confidence
            # Ein Geraet kann auf mehreren Einstiegsseiten eines Anbieters
            # stehen. Gealtert wird es nur, wenn ALLE davon gelesen wurden -
            # deshalb eine Liste und nicht die zuletzt gesehene Seite.
            if listung.einstieg_url:
                heimat = list(eintrag.get("einstiege") or [])
                if listung.einstieg_url not in heimat:
                    heimat.append(listung.einstieg_url)
                eintrag["einstiege"] = heimat
            if listung.titel_roh:
                eintrag["titel_roh"] = listung.titel_roh
            # Eine Preisform gehoert zu DER Zahl, mit der sie gemessen
            # wurde. Kommt ein ANDERER Preis herein und dieser Lauf nennt
            # keine Laufzeit, ist die gespeicherte Form nicht ausgefallen,
            # sondern ueberholt: sonst traegt ein frischer Barpreis das
            # Etikett "in 24 Raten (0 %)" vom Vortag - genau die
            # Verwechslung, gegen die die Kennzeichnung gebaut ist. Ein
            # falsches Etikett ist schlimmer als keins.
            if (listung.laufzeit_monate is None
                    and listung.preis_ohne_vertrag is not None
                    and eintrag.get("preis_ohne_vertrag") is not None
                    and eintrag["preis_ohne_vertrag"]
                    != listung.preis_ohne_vertrag):
                for feld in _PREISFORMFELDER:
                    eintrag.pop(feld, None)
            # Preisfelder: ein Wert, den der Extraktor diesmal NICHT fand,
            # ueberschreibt den bekannten nicht. Sonst waere jede Luecke in
            # der Extraktion eine Preisaenderung.
            #
            # Die Preisform folgt derselben Regel, solange die Zahl
            # dieselbe bleibt (siehe oben). Sie beschreibt den AKTUELLEN
            # Preis; die Historie in `geraete_preise.jsonl` wird davon
            # nicht angefasst und kein alter Preispunkt umgedeutet.
            for feld in ("preis_ohne_vertrag", "uvp", "preis_mit_vertrag_ab",
                         "zuzahlung") + _PREISFORMFELDER:
                wert = getattr(listung, feld)
                if wert is not None:
                    eintrag[feld] = wert
            if listung.tarif_referenz:
                eintrag["tarif_referenz"] = listung.tarif_referenz
        return neu, gesehen

    def mark_stale(self, anbieter: str, gesehene_ids: set, today: str,
                   gelesene_einstiege: Optional[set] = None,
                   leitseite: str = "") -> int:
        """Zwei-Stufen-Auslistung fuer EINEN Anbieter.

        `gelesene_einstiege` nennt die Einstiegsseiten, die in diesem Lauf
        wirklich gelesen wurden. Ein Eintrag altert nur, wenn JEDE seiner
        Einstiegsseiten darunter ist - genau daran haengt, dass ein
        Teilausfall nicht die halbe Palette eines Haendlers auslistet. None
        heisst ausdruecklich "dieser Anbieter wurde vollstaendig gelesen".

        `leitseite` faengt Bestandseintraege ohne Einstiegsangabe ab -
        dieselbe Konvention wie `promo_store.mark_stale`. Ohne sie alterte
        ein solcher Eintrag NIE und stuende auf ewig als "aktiv" auf der
        Seite.

        Und: je Tag hoechstens ein Schritt. Zwei Aufrufe am selben Datum -
        ein Wiederholungslauf, oder eine Schleife je Einstiegsseite - haetten
        einen Eintrag sonst in einem einzigen Lauf von "aktiv" auf
        "ausgelistet" geschoben. "Zwei Fehltreffer IN FOLGE" ist eine Aussage
        ueber zwei Laeufe.
        """
        gealtert = 0
        for e in self._eintraege.values():
            if e.get("anbieter") != anbieter or e.get("id") in gesehene_ids:
                continue
            if e.get("letzter_check") == today:
                continue
            if gelesene_einstiege is not None:
                heimat = list(e.get("einstiege") or ([leitseite] if leitseite else []))
                if not heimat or any(h not in gelesene_einstiege for h in heimat):
                    continue
            status = e.get("status")
            if status not in (STATUS_AKTIV, STATUS_VERMUTLICH):
                continue
            e["letzter_check"] = today
            e["missed_checks"] = int(e.get("missed_checks", 0)) + 1
            if status == STATUS_AKTIV:
                e["status"] = STATUS_VERMUTLICH
                e["stale_since"] = today
            else:
                e["status"] = STATUS_AUSGELISTET
                e["ended_since"] = today
            gealtert += 1
        return gealtert

    # ------------------------------------------------- Hardware-Vermarktung

    def protokolliere_lauf(self, anbieter: str, today: str, funde: int,
                           vollstaendig: bool = True,
                           zustand: Optional[str] = None,
                           buendel: int = 0,
                           tote_adressen: Optional[int] = None,
                           produkte_versucht: Optional[int] = None) -> None:
        """Buch darueber, wie oft ein Anbieter abgefragt wurde und was dabei
        herauskam. Grundlage von `hardware_vermarktung()` und `messtermine()`.

        `vollstaendig=False` ist ein Teillauf: der Anbieter wurde gelesen,
        aber nicht zu Ende (Zeitbudget, Deckel, einzelne tote Produktseiten).
        Ein solcher Lauf zaehlt NICHT auf `laeufe` - drei Teillaeufe ohne
        Fund duerfen keine Marke zum SIM-only-Anbieter erklaeren. Aber seine
        FUNDE sind echte Beobachtungen: der Tag gehoert in die Messtermine,
        sonst zaehlt die Lifecycle-Auswertung einen Anbieter, der jede Nacht
        84 Listungen bestaetigt und nur nie fertig wird, als nie gemessen.
        Genau das war der Befund vom 28.08.2026: mobilcom-debitel fehlte
        komplett in dieser Bilanz, und `_oft_genug` sperrte 84 von 85
        Listungen aus der Auswertung.

        `zustand` ist der LESEZUSTAND dieses Tages (GELESEN, LESEFEHLER,
        NICHT_GELESEN) und traegt den Abdeckungswaechter. Ohne Angabe wird
        er aus `vollstaendig` abgeleitet - das ist keine Vermutung, sondern
        dieselbe Aussage in anderen Worten: was nicht vollstaendig gelesen
        wurde, ist ein Leseversuch, der nicht durchkam. Ein Anbieter, den
        der Lauf gar nicht angefasst hat (Besuchszeit, nicht crawlbar),
        muss NICHT_GELESEN ausdruecklich mitgeben; er ist sonst nicht von
        einem Fehlschlag zu unterscheiden.

        `buendel` sind die Buendelsaetze desselben Tages. Sie zaehlen NICHT
        auf `funde`/`funde_gesamt` (dort geht es um Listungen und damit um
        die Frage, ob ein Anbieter ueberhaupt Hardware vermarktet), sondern
        nur in die Abdeckung - siehe `Messtag`.

        `tote_adressen` sind die Produktadressen dieses Laufs, die die
        Quelle selbst nennt und die es nicht mehr gibt (HTTP 404/410). Sie
        sind eine BENANNTE LUECKE und kein Ausfall - der Lauf kann damit
        vollstaendig sein (siehe `collect.geraete._einstieg_gelesen`).
        `None` heisst "in diesem Lauf wurde keine Produktseite versucht",
        also keine Aussage; 0 heisst "versucht, keine war tot" und ist
        selbst eine Aussage (CLAUDE.md Clean Code 3).

        `produkte_versucht` ist der NENNER dazu. Beide gehoeren in den
        Messtag und nicht nur in die Laufbilanz: die Laufbilanz kennt nur
        den letzten Stand, der Erosionsalarm braucht die Reihe
        (`ALARM_EROSION`). Auch hier ist `None` "nicht versucht" und
        niemals 0."""
        b = self._anbieter.setdefault(anbieter, {"laeufe": 0, "funde_gesamt": 0})
        if zustand is None:
            zustand = GELESEN if vollstaendig else LESEFEHLER
        if vollstaendig:
            b["laeufe"] = int(b.get("laeufe", 0)) + 1
            b["letzter_lauf"] = today
        b["funde_gesamt"] = int(b.get("funde_gesamt", 0)) + int(funde)
        if vollstaendig or funde:
            b["letzte_funde"] = int(funde)
            termine = b.setdefault("termine", [])
            if today not in termine:
                termine.append(today)
        # DER MESSTAG-JOURNAL, und zwar fuer JEDEN Tag - auch fuer einen,
        # an dem nichts gelesen wurde. Das ist der Unterschied zum Stand
        # vor dem 22.09.2026: damals stand ein Tag nur dann im Bestand,
        # wenn er vollstaendig war oder Funde hatte, und ein Anbieter, der
        # gar nichts lieferte, hinterliess keine Spur. Genau diese Spur
        # braucht der Vortagsvergleich, und sie muss den LESEZUSTAND
        # tragen: ohne ihn ist "heute nicht erfasst" nicht von "heute
        # ausserhalb der Besuchszeit" zu unterscheiden.
        #
        # Gleicher Tag ersetzt seinen Eintrag (idempotent, dieselbe Regel
        # wie die TCO-Historie), ein neuer Tag haengt an; gedeckelt auf den
        # Diagnose-Rand. Eintragsform: [Tag, Funde, Zustand, Buendel].
        historie = [list(e) for e in (b.get("funde_nach_tag") or [])
                    if not (isinstance(e, (list, tuple)) and e
                            and str(e[0]) == today)]
        versucht = 0 if produkte_versucht is None else int(produkte_versucht)
        tote = None if tote_adressen is None else int(tote_adressen)
        historie.append([today, int(funde), zustand, int(buendel), versucht,
                         tote])
        b["funde_nach_tag"] = historie[-_FUND_HISTORIE_TAGE:]
        # DIE LETZTE MESSUNG WIRD NICHT VON EINER NICHT-MESSUNG GELOESCHT
        # (S3, 22.09.2026). Vorher stand hier eine unbedingte Zuweisung:
        # eine Nacht ausserhalb der Besuchszeit schrieb `None` und raeumte
        # damit die gestern gemessenen neun toten Adressen von der
        # Quellenseite ab, obwohl die Luecke unveraendert bestand. "Nicht
        # gemessen" darf eine Messung nicht ueberschreiben (Clean Code 6);
        # der Schluessel wird trotzdem angelegt, damit "noch nie gemessen"
        # als benannte Luecke dasteht und nicht als fehlendes Feld.
        if tote is None:
            b.setdefault("tote_adressen", None)
        else:
            b["tote_adressen"] = tote
        if funde:
            b["letzter_fund"] = today

    def stille_tage(self, anbieter: str) -> int:
        """Wie viele BEOBACHTETE Tage in Folge dieser Anbieter 0 Funde
        geliefert hat - die Zahl hinter dem FM-2-Alarm.

        Gezaehlt werden Tage mit echter Beobachtung, nicht Kalendertage: ein
        Anbieter, der laut robots.txt nur nachts im Besuchszeitfenster dran
        ist, wird tagsueber garnicht angefasst - ein ausgelassener Tag ist
        keine Aussage und zaehlt weder fuer noch gegen den Anbieter.

        Zwei Quellen, eine Wahrheit:
          * `funde_nach_tag` (seit dem FM-2-Auftrag): die Fundzahl je Tag.
          * der ALTBESTAND davor: `letzter_fund` ist per Definition ein Tag
            MIT Funden, und jeder `termine`-Eintrag DANACH ist ein Lauf mit
            null Funden - sonst stuende er als `letzter_fund` darin. Das ist
            Ableitung aus gespeicherten Beobachtungen, keine Erfindung; ohne
            `letzter_fund` (sehr alter Bestand) wird nichts abgeleitet.
        """
        b = self._anbieter.get(anbieter) or {}
        if int(b.get("funde_gesamt", 0)) <= 0:
            # Nie geliefert: das ist der SIM-only-Fall von
            # `hardware_vermarktung`, kein Quellentod.
            return 0
        # Nur BEOBACHTETE Tage. Seit dem 22.09.2026 stehen auch die nicht
        # gelesenen im Journal (der Abdeckungswaechter braucht sie); sie
        # sind hier so unsichtbar wie vorher, als sie gar nicht erst
        # geschrieben wurden - "nicht gelesen" ist nicht "leer".
        paare: dict[str, int] = {m.tag: m.funde for m in self.messtage(anbieter)
                                 if m.fundtag}
        letzter_fund = str(b.get("letzter_fund") or "")
        if letzter_fund and letzter_fund not in paare:
            paare[letzter_fund] = 1              # per Definition > 0
        if letzter_fund:
            for t in (b.get("termine") or []):
                t = str(t)
                if t > letzter_fund and t not in paare:
                    paare[t] = 0
        tage = 0
        for tag in sorted(paare, reverse=True):
            if paare[tag] > 0:
                break
            tage += 1
        return tage

    # ----------------------------------------------- Abdeckung (P1/C2)

    def messtage(self, anbieter: str) -> list:
        """Das Journal eines Anbieters als `Messtag`-Liste, aufsteigend.

        Liest die drei Eintragsformen, die es im Bestand gibt, ohne zu
        raten:
          * `[tag, funde, zustand, buendel, versucht, tote]` - seit dem
            22.09.2026. `tote` darf `null` sein: "keine Produktseite
            versucht" ist keine 0 (Clean Code 3).
          * `[tag, funde, zustand, buendel]` - die Form eines halben Tages
            davor. Adresszahlen kannte sie nicht; sie bleiben `0`/`None`
            und fallen damit aus dem Erosionsvergleich heraus, statt als
            "null Adressen gelesen" einen Einbruch vorzutaeuschen.
          * `[tag, funde]` - der Altbestand. Er entstand AUSSCHLIESSLICH
            fuer vollstaendige Laeufe ODER Laeufe mit Funden, also genau
            fuer BEOBACHTETE Tage; `GELESEN` ist deshalb eine Ableitung
            aus der damaligen Schreibregel, keine Annahme. Ein alter
            Eintrag mit Funden koennte auch ein Teillauf gewesen sein -
            fuer den Waechter macht das keinen Unterschied, er fragt den
            Zustand nur am BEZUGSTAG, und der wird immer frisch
            geschrieben. Buendel kannte diese Form nicht: 0.
        Ein Eintrag, der nicht lesbar ist, faellt LAUT heraus - er wird
        nicht durch einen erfundenen ersetzt. Die Form wird dafuer
        ausdruecklich geprueft und nicht bloss indiziert: ein String
        "2026-09-01" liess sich klaglos zeichenweise lesen ([0] -> Tag
        "2", [1] -> Funde 0) und ergab einen Messtag, den es nie gab -
        still erzeugter Muell statt eines Protokolleintrags (Clean Code 5).
        """
        journal = []
        for eintrag in (self._anbieter.get(anbieter, {}).get("funde_nach_tag")
                        or []):
            if not isinstance(eintrag, (list, tuple)) or len(eintrag) < 2:
                log.warning("Geraeteradar: unlesbarer Messtag bei %s (%r) - "
                            "uebergangen", anbieter, eintrag)
                continue
            try:
                tag, funde = str(eintrag[0]), int(eintrag[1])
                zustand = str(eintrag[2]) if len(eintrag) > 2 else GELESEN
                buendel = int(eintrag[3]) if len(eintrag) > 3 else 0
                versucht = int(eintrag[4]) if len(eintrag) > 4 else 0
                roh_tote = eintrag[5] if len(eintrag) > 5 else None
                tote = None if roh_tote is None else int(roh_tote)
            except (TypeError, ValueError):
                log.warning("Geraeteradar: unlesbarer Messtag bei %s (%r) - "
                            "uebergangen", anbieter, eintrag)
                continue
            journal.append(Messtag(tag=tag, funde=funde, buendel=buendel,
                                   zustand=zustand, versucht=versucht,
                                   tote=tote))
        return sorted(journal, key=lambda m: m.tag)

    def letzter_messtag(self) -> Optional[str]:
        """Der juengste Tag, an dem IRGENDEIN Anbieter gemessen wurde -
        oder `None`, wenn der Bestand keinen kennt. Nie "" und nie heute:
        ein fehlender Wert ist eine Luecke, kein Datum (Clean Code 3)."""
        tage = [m.tag for name in self._anbieter for m in self.messtage(name)]
        return max(tage) if tage else None

    def lesezustand(self, anbieter: str,
                    tag: Optional[str] = None) -> Optional[str]:
        """Der LESEZUSTAND eines Anbieters am Bezugstag - oder `None`.

        Dieselbe Auskunft, aus der auch `abdeckungsalarm` seine Tore baut,
        und damit die EINE Definition, die die Quellenseite fuer ihren
        dritten Zustand braucht (Clean Code 7: keine zweite Liste). `None`
        heisst "dieser Anbieter hat an diesem Tag keinen Messtag" - er war
        nicht an der Reihe, und das ist keine Entwarnung.

        Ohne `tag` gilt der letzte Messtag des Bestands, wie bei
        `ausfall_alarme` - Lauf und Seite fragen so denselben Tag.
        """
        bezug = tag if tag else self.letzter_messtag()
        if not bezug:
            return None
        heutige = [m for m in self.messtage(anbieter) if m.tag == bezug]
        return heutige[-1].zustand if heutige else None

    def _befund(self, anbieter: str, journal: list,
                heute: Messtag) -> Optional[Abdeckungsalarm]:
        """Die LAGE eines Anbieters an EINEM Tag - noch ohne die Frage, ob
        sie an diesem Tag auch gemeldet wird (das entscheidet
        `_alarmlauf`).

        `None` heisst "kein Befund" und NICHT "in Ordnung": ein Anbieter
        ohne Vortagsdaten, ein Anbieter ausserhalb seiner Besuchszeit und
        ein Anbieter, der heute gar nicht an der Reihe war, sind
        unbekannt - und Unbekanntes faellt aus dem Vergleich heraus, statt
        als "geliefert" durchzugehen (Clean Code 4).

        Die Tore, in dieser Reihenfolge:
          1. Heute wurde ueberhaupt etwas gelesen. `NICHT_GELESEN` (gar
             nicht angefasst: Besuchszeit, nicht crawlbar, kein Adapter)
             ist kein Ausfall - "nicht gelesen" ist nicht "leer" (Clean
             Code 6). Ein TEILGELESEN-Tag faellt hier NICHT heraus: an ihm
             ist gelesen worden, er kann also ausfallen wie jeder andere.
          2. Es gibt einen Vortag, der als Basis taugt
             (`Messtag.vergleichsbasis` - beobachtet und kein Teiltag).
             Gibt es KEINEN, ist das ab `_OHNE_BASIS_TAGE` beobachteten
             Tagen selbst der Befund (`ALARM_OHNE_BASIS`): ein Waechter
             ohne Vergleich ist blind, und Blindheit ist keine
             Entwarnung. Vorher - ein einzelner uebersprungener oder
             halber Tag - ist es nur eine Luecke.
          3. Der Vortag hat geliefert. Hat er selbst schon nichts
             geliefert, ist heute kein NEUER Ausfall - die anhaltende
             Stille traegt `stille_tage` und die Quellenseite.
          4. Und wenn nach alledem heute nichts auffaellt: broeselt das
             Sortiment ueber TAGE weg (`_erosionsbefund`)? Dieses Tor
             steht zuletzt, weil es das leiseste ist - ein Ausfall oder
             ein Einbruch von gestern auf heute ist dringender und soll
             den Satz stellen.
        """
        if heute.zustand == NICHT_GELESEN:
            return None
        vorher = [m for m in journal if m.tag < heute.tag]
        vortage = [m for m in vorher if m.vergleichsbasis]
        if not vortage:
            beobachtet = [m for m in vorher if m.beobachtet]
            if len(beobachtet) < _OHNE_BASIS_TAGE:
                return None
            return Abdeckungsalarm(
                anbieter=anbieter, art=ALARM_OHNE_BASIS, tag=heute.tag,
                zeilen=heute.zeilen, zustand=heute.zustand, vortag=None,
                zeilen_vortag=None, rueckgang=None,
                stille_tage=self.stille_tage(anbieter),
                ohne_basis_tage=len(beobachtet))
        vortag = vortage[-1]
        if vortag.zeilen > 0:
            rueckgang = (vortag.zeilen - heute.zeilen) / vortag.zeilen
            art = None
            if heute.zeilen <= 0:
                art = ALARM_AUSFALL
            elif rueckgang > ABDECKUNG_RUECKGANG:
                art = ALARM_RUECKGANG
            if art is not None:
                return Abdeckungsalarm(
                    anbieter=anbieter, art=art, tag=heute.tag,
                    zeilen=heute.zeilen, zustand=heute.zustand,
                    vortag=vortag.tag, zeilen_vortag=vortag.zeilen,
                    rueckgang=rueckgang,
                    stille_tage=self.stille_tage(anbieter))
        return self._erosionsbefund(anbieter, journal, heute)

    def _erosionsbefund(self, anbieter: str, journal: list,
                        heute: Messtag) -> Optional[Abdeckungsalarm]:
        """Broeselt das Sortiment dieses Anbieters ueber TAGE weg?

        DIE LUECKE, DIE DAS SCHLIESST (22.09.2026). Tote Produktadressen
        kippen seit diesem Tag keinen Lauf mehr - bis zu jeder vierten
        darf fehlen (`collect.geraete._MINDESTANTEIL_GELESENER_PRODUKTSEITEN`).
        Damit ist eine LANGSAME Erosion durch jedes Tor gerutscht: 24 %
        tote Adressen je Nacht reissen die Schwelle nicht, und der
        Vortagsvergleich oben sieht nur 24 % weniger Zeilen, also weniger
        als `ABDECKUNG_RUECKGANG`. Nach fuenf Naechten war ein Viertel des
        Sortiments uebrig, der Lauf jeden Tag `ok` und `vollstaendig`, und
        `mark_stale` hat die fehlenden Listungen brav ausgelistet. Laut
        geworden waere es erst bei null Zeilen - als Nachruf.

        WOGEGEN VERGLICHEN WIRD: gegen den AELTESTEN Messtag im Fenster,
        der ueberhaupt eine Adressauskunft hat, nicht gegen gestern. Genau
        darin liegt der Unterschied zu den drei Toren oben - eine Erosion
        ist je Einzelschritt unauffaellig und nur als Verlauf zu sehen.

        WORIN GERECHNET WIRD: in GELESENEN PRODUKTADRESSEN
        (`Messtag.gelesene_adressen`) und nicht in Zeilen. Dieselbe
        Einheit wie die Schwelle, die die Luecke durchlaesst - ein
        Waechter, der in einer anderen Groesse rechnet als die Regel, die
        er absichern soll, begruendet nichts (das war S2-1). Tage ohne
        Adressauskunft fallen heraus, statt als 0 einen Einbruch
        vorzutaeuschen.

        WARUM EINE STABILE LUECKE SCHWEIGT: mobilcom-debitels Sitemap
        fuehrt Nacht fuer Nacht dieselben neun toten Adressen. Gelesen
        werden dabei jede Nacht 36 Seiten - der Vergleich ergibt 0 %, und
        genau so soll es sein. Gemeldet wird die BEWEGUNG, nicht die
        Luecke; die Luecke steht als Zahl auf der Quellenseite.
        """
        gemessen = [m for m in journal
                    if m.tag <= heute.tag and m.gelesene_adressen is not None]
        fenster = gemessen[-_EROSION_FENSTER_TAGE:]
        if len(fenster) < 2 or fenster[-1].tag != heute.tag:
            return None
        basis = fenster[0]
        if basis.gelesene_adressen <= 0:
            # Kein Nenner, kein Anteil - und aus einem Anbieter, der schon
            # damals nichts gelesen hat, wird kein Einbruch konstruiert.
            return None
        schwund = ((basis.gelesene_adressen - heute.gelesene_adressen)
                   / basis.gelesene_adressen)
        if schwund <= ABDECKUNG_RUECKGANG:
            return None
        return Abdeckungsalarm(
            anbieter=anbieter, art=ALARM_EROSION, tag=heute.tag,
            zeilen=heute.zeilen, zustand=heute.zustand, vortag=basis.tag,
            zeilen_vortag=basis.zeilen, rueckgang=schwund,
            stille_tage=self.stille_tage(anbieter),
            adressen=heute.gelesene_adressen,
            adressen_vortag=basis.gelesene_adressen)

    def abdeckungsalarm(self, anbieter: str,
                        tag: str) -> Optional[Abdeckungsalarm]:
        """Der Alarm EINES Anbieters an EINEM Tag - oder `None`.

        `None` heisst "heute nichts zu melden" und nie "in Ordnung":
        entweder gibt es keinen Befund (`_befund`), oder es ist derselbe
        wie gestern und heute kein Wiederholungstag.

        DIE WIEDERHOLUNGSSPERRE (S2-B). Gemeldet wird, wenn sich die Lage
        GEAENDERT hat - Alarmart, Lesezustand oder ob ueberhaupt Zeilen
        kamen -, und sonst an jedem `_ist_wiederholungstag`. Ohne diese
        Sperre meldete der Waechter dieselbe Teillage an 29 Tagen
        hintereinander, jeden mit eigener Mail; nach der dritten ist so
        ein Kanal ein Postfachfilter und damit so stumm wie einer, der
        schweigt. Der WECHSEL bleibt laut: wer von "drei Zeilen, Teiltag"
        auf "null Zeilen, Lesefehler" faellt, meldet sofort.

        DIE GRENZE DIESER SPERRE, damit sie niemand suchen muss: der
        Vortagsbefund wird mit dem HEUTIGEN Journal nachgerechnet. Faellt
        die Vergleichsbasis gerade aus dem gedeckelten Journal, sieht
        auch der Vortag schon keine Basis mehr - der Wechsel von
        `ALARM_RUECKGANG` zu `ALARM_OHNE_BASIS` faellt dann nicht als
        Wechsel auf und wird erst am naechsten Wiederholungstag gemeldet.
        Laenger als `_ALARM_WIEDERHOLUNG_TAGE` Tage bleibt nichts liegen,
        und jede Aenderung an den MESSDATEN (Zeilen, Lesezustand) wird
        sofort laut.
        """
        journal = self.messtage(anbieter)
        heutige = [m for m in journal if m.tag == tag]
        if not heutige:
            return None
        befund = self._befund(anbieter, journal, heutige[-1])
        if befund is None:
            return None
        vorherige = [m for m in journal if m.tag < tag]
        if not vorherige or _ist_wiederholungstag(tag):
            return befund
        gestern = self._befund(anbieter, journal, vorherige[-1])
        if gestern is not None and _befundschluessel(gestern) == \
                _befundschluessel(befund):
            return None
        return befund

    def ausfall_alarme(self, nur: Optional[Iterable[str]] = None,
                       heute: Optional[str] = None) -> list:
        """Alle Anbieter, deren Abdeckung heute gegenueber dem Vortag
        eingebrochen ist: `[Abdeckungsalarm, ...]`, groesster Rueckgang
        zuerst.

        NUR MELDUNG, KEIN GRIFF - der Rueckgabewert geht ins Protokoll
        (`geraete_pipeline.melde_ausfall`), in die Mail und auf die
        Quellenseite; kein Anbieter wird gealtert, geloescht oder sonstwie
        angefasst. Ein Alarm, der Daten loescht, waere schlimmer als die
        Blindheit, die er ersetzt.

        `heute` ist der Bezugstag. Der Lauf uebergibt seinen eigenen; die
        Seite laesst ihn weg und bekommt den letzten Messtag des Bestands.
        Beide rechnen damit ueber DIESELBE Funktion - zwei Definitionen
        waeren zwei Wahrheiten (Clean Code 7).

        `nur` grenzt auf die Anbieter DIESES Laufs ein: ein Anbieter, der
        aus der Konfiguration gefallen ist, wird nicht mehr beobachtet -
        sein eingefrorener Zaehlerstand darf keine Ewigkeitsmeldung geben.
        """
        tag = heute if heute else self.letzter_messtag()
        if not tag:
            return []
        erlaubt = None if nur is None else set(nur)
        alarme = []
        for name in sorted(self._anbieter):
            if erlaubt is not None and name not in erlaubt:
                continue
            alarm = self.abdeckungsalarm(name, tag)
            if alarm is not None:
                alarme.append(alarm)
        return sorted(alarme, key=_alarm_reihenfolge)

    def messtermine(self, anbieter: str) -> list:
        """Alle Tage, an denen Listungen dieses Anbieters wirklich geprueft
        wurden - sortiert, je Tag einmal.

        Quelle sind die `termine` der Laufbilanz PLUS die Datumsfelder der
        Listungen selbst. Der zweite Teil ist keine Redundanz, sondern der
        Altbestand: die Termine-Buchfuehrung gibt es erst seit dem
        28.08.2026, aber `first_seen`, `erstpreis_am`, `last_verified` und
        `letzter_check` sind echte Beobachtungszeitpunkte frueherer Laeufe.
        Abgeleitet wird nur, was wirklich gespeichert wurde - ein Lauf,
        dessen Bestaetigung von einem spaeteren ueberschrieben wurde, ist
        verloren und wird NICHT erfunden."""
        termine = {str(t) for t in (self._anbieter.get(anbieter, {}).get("termine") or [])}
        for feld in ("letzter_lauf", "letzter_fund"):
            wert = self._anbieter.get(anbieter, {}).get(feld)
            if wert:
                termine.add(str(wert))
        for e in self._eintraege.values():
            if e.get("anbieter") != anbieter:
                continue
            # Bewusst NUR die reinen Beobachtungsfelder. `erstpreis_am` und
            # `abgerufen_am` duplizieren first_seen/last_verified und wuerden
            # in einem inkonsistenten Bestand Termine erfinden.
            for feld in ("first_seen", "last_verified", "letzter_check"):
                wert = e.get(feld)
                if wert:
                    termine.add(str(wert))
        return sorted(termine)

    def hardware_vermarktung(self, anbieter: str) -> str:
        """ja | nein | unbekannt - ABGELEITET, nicht von Hand gesetzt.

        Viele Discount- und Zweitmarken vermarkten ausschliesslich SIM-only.
        Das ist selbst ein Befund und gehoert sichtbar auf die Seite - aber
        er entsteht aus Messung: drei Laeufe ohne einen einzigen Fund. Nach
        einem leeren Lauf ist die wahrscheinlichere Erklaerung eine kaputte
        Quelle, und eine zu Unrecht als SIM-only gefuehrte Marke faellt
        stillschweigend aus der Uebersicht.
        """
        b = self._anbieter.get(anbieter)
        if not b:
            return "unbekannt"
        if int(b.get("funde_gesamt", 0)) > 0:
            return "ja"
        if int(b.get("laeufe", 0)) >= _LAEUFE_BIS_SIM_ONLY:
            return "nein"
        return "unbekannt"

    def laufbilanz(self, anbieter: str) -> dict:
        return dict(self._anbieter.get(anbieter) or {})

    # ---------------------------------------------------------------- save

    def save(self, today: str) -> None:
        self.updated = today
        self.path.parent.mkdir(parents=True, exist_ok=True)
        daten = {
            "updated": today,
            "anbieter": self._anbieter,
            "listungen": self.eintraege(),
        }
        self.path.write_text(json.dumps(daten, ensure_ascii=False, indent=1),
                             encoding="utf-8")


# --------------------------------------------------------------------------
# Preishistorie
# --------------------------------------------------------------------------

class Preishistorie:
    """data/state/geraete_preise.jsonl - append-only, nur Aenderungspunkte."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._reihen: dict[str, list[dict]] = {}
        self._neu: list[dict] = []
        if self.path.exists():
            kaputt = 0
            for zeile in self.path.read_text(encoding="utf-8").splitlines():
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    satz = json.loads(zeile)
                except json.JSONDecodeError:
                    kaputt += 1
                    continue
                lid = satz.get("listung_id")
                if lid:
                    self._reihen.setdefault(lid, []).append(satz)
            if kaputt:
                log.warning("geraete_preise.jsonl: %d unlesbare Zeilen uebersprungen",
                            kaputt)

    def reihe(self, listung_id: str) -> list[dict]:
        """Die Aenderungspunkte einer Listung, aelteste zuerst."""
        return sorted(self._reihen.get(listung_id, []), key=lambda s: s.get("datum", ""))

    def letzter(self, listung_id: str) -> Optional[dict]:
        reihe = self.reihe(listung_id)
        return reihe[-1] if reihe else None

    def schreibe(self, listung, today: str) -> bool:
        """Einen Messpunkt anbieten. True, wenn er als Aenderung aufgenommen
        wurde.

        Nicht aufgenommen wird:
          * ein Messpunkt, der sich in keinem Historienfeld vom letzten
            unterscheidet (sonst 52 identische Punkte je Jahr und Geraet),
          * ein FEHLENDER Wert, wo vorher einer stand. Der Extraktor hat
            diesmal nichts gefunden - das ist ein Ausfall, keine Senkung.
        """
        listung = _als_listung(listung)
        lid = listung.listung_id
        vorher = self.letzter(lid)
        satz = {
            "listung_id": lid,
            "sku_id": listung.sku_id,
            "device_id": listung.device_id,
            "anbieter": listung.anbieter,
            "datum": today,
            "preis_ohne_vertrag": listung.preis_ohne_vertrag,
            "uvp": listung.uvp,
            "preis_mit_vertrag_ab": listung.preis_mit_vertrag_ab,
            "zuzahlung": listung.zuzahlung,
            "tarif_referenz": listung.tarif_referenz or None,
            "verfuegbarkeit": listung.verfuegbarkeit,
            "quelle_url": listung.quelle_url,
        }
        if vorher is not None:
            geaendert = False
            for feld in _HISTORIENFELDER:
                neu, alt = satz.get(feld), vorher.get(feld)
                if _ist_ausfall(feld, neu) and not _ist_ausfall(feld, alt):
                    continue          # Ausfall, keine Aenderung
                if neu != alt:
                    geaendert = True
            if not geaendert:
                return False
            # Ein Ausfall darf den bekannten Wert auch in der Historie nicht
            # loeschen: der neue Punkt erbt jeden Wert, den dieser Lauf nicht
            # messen konnte.
            for feld in _HISTORIENFELDER:
                if _ist_ausfall(feld, satz.get(feld)) and not _ist_ausfall(feld, vorher.get(feld)):
                    satz[feld] = vorher[feld]
        elif not any(satz.get(f) is not None for f in _PREISFELDER):
            # Allererster Messpunkt ohne jeden Preis: das ist eine Listung,
            # aber keine Preisbeobachtung. Sie steht in geraete_db.json, nicht
            # in der Kurve.
            return False

        self._reihen.setdefault(lid, []).append(satz)
        self._neu.append(satz)
        return True

    def save(self) -> int:
        """Haengt die neuen Punkte an. Gibt die Zahl der geschriebenen Zeilen
        zurueck."""
        if not self._neu:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            for satz in self._neu:
                fh.write(json.dumps(satz, ensure_ascii=False) + "\n")
        anzahl = len(self._neu)
        self._neu = []
        return anzahl

    @property
    def punkte_gesamt(self) -> int:
        return sum(len(r) for r in self._reihen.values())

    def alle_punkte(self) -> list:
        """Alle Aenderungspunkte, aeltester zuerst - fuer die Auswertung."""
        return sorted((p for reihe in self._reihen.values() for p in reihe),
                      key=lambda s: (s.get("datum", ""), s.get("listung_id", "")))
