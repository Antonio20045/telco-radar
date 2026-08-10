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

# Die Felder, deren Aenderung einen neuen Historienpunkt rechtfertigt.
_HISTORIENFELDER = ("preis_ohne_vertrag", "uvp", "preis_mit_vertrag_ab",
                    "zuzahlung", "tarif_referenz", "verfuegbarkeit")

# Welche davon ueberhaupt ein Preis sind - der allererste Messpunkt einer
# Listung wird nur geschrieben, wenn EINER davon einen Wert hat. Frueher
# stand hier nur `preis`/`uvp`, und eine Listung, deren einziger Preis ein
# Vertragspreis ist, bekam nie einen Historienpunkt.
_PREISFELDER = ("preis_ohne_vertrag", "uvp", "preis_mit_vertrag_ab", "zuzahlung")


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
        if self.path.exists():
            try:
                roh = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("geraete_db.json unlesbar (%s) - starte leer", exc)
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
            # Preisfelder: ein Wert, den der Extraktor diesmal NICHT fand,
            # ueberschreibt den bekannten nicht. Sonst waere jede Luecke in
            # der Extraktion eine Preisaenderung.
            for feld in ("preis_ohne_vertrag", "uvp", "preis_mit_vertrag_ab",
                         "zuzahlung"):
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

    def protokolliere_lauf(self, anbieter: str, today: str, funde: int) -> None:
        """Buch darueber, wie oft ein Anbieter abgefragt wurde und was dabei
        herauskam. Grundlage von `hardware_vermarktung()`."""
        b = self._anbieter.setdefault(anbieter, {"laeufe": 0, "funde_gesamt": 0})
        b["laeufe"] = int(b.get("laeufe", 0)) + 1
        b["funde_gesamt"] = int(b.get("funde_gesamt", 0)) + int(funde)
        b["letzter_lauf"] = today
        b["letzte_funde"] = int(funde)
        if funde:
            b["letzter_fund"] = today

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
