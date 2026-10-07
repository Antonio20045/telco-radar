"""Bestand der Buendel und der SIM-only-Referenzen - `geraete_tco.json`.

Warum eine EIGENE Datei
-----------------------
`data/state/geraete_db.json` traegt seit dem 10.08.2026 die Listungen, also was ein
Anbieter fuer ein GERAET verlangt. Ein Buendel ist ein anderer Sachverhalt: es kommt von
einer Tarifseite, hat einen anderen Lebenszyklus und eine andere Identitaet (SKU x
Anbieter x Tarif x Ratenlaufzeit statt SKU x Anbieter). Es steht deshalb in

    data/state/geraete_tco.json    Buendel, SIM-only-Referenzen und unter `pruefung`
                                   die Kennzahlen der Pruefstelle (`TcoDB.pruefung`)

und nicht als weiterer Abschnitt in der Listungsdatei. Der Grund ist nicht
Ordnungsliebe, sondern Risiko: `geraete_db.json` traegt 391 gewachsene Listungen und
haengt an `geraete_preise.jsonl`, das die ganze Preishistorie haelt. Eine neue Entitaet,
die diese Datei umschreibt, kann eine `listung_id` verschieben - und eine verschobene ID
zerreisst still den Verlauf, dieselbe Fehlerklasse wie ein neu vergebener Farbschluessel
(`geraete_model.farbe_aus_titel`). Zwei Dateien koennen das strukturell nicht: dieses
Modul oeffnet die andere gar nicht.

Die IDs koennen sich ebenfalls nicht ueberschneiden, und zwar an ihrer Form
(`tco_model.buendel_id`): eine `listung_id` hat zwei Bestandteile, ein Buendel seit B1
fuenf (die Ratenlaufzeit ist dazugekommen; vorher vier), eine Referenz drei.

Der Altbestand traegt weiterhin die vierteilige ID - beide Dateien dieses Moduls werden
NICHT umgeschrieben (harte Regeln 2 und 3). Ein Alt-Satz wird beim LESEN dem heutigen
Buendel zugeordnet (`id_aus_satz` unten, ueber `laufzeit_monate`); die neue Form
entsteht in der Stand-Datei erst durch das naechste regulaere `save()`, und in der
Historie ueberhaupt nicht - eine geschriebene Zeile bleibt, wie sie war.

Die eine Regel, die dieses Modul von `geraete_store` unterscheidet
------------------------------------------------------------------
**Ein Buendeldatensatz zeigt EINE Messung.** Wo `GeraeteDB.upsert` einen Wert, den ein
Lauf nicht fand, stehen laesst (ein Ausfall der Extraktion ist keine Preisaenderung),
schreibt ein Lauf hier ALLE Preisfelder eines Buendels gemeinsam - auch als `None`. Der
Grund ist die Kennzahl: TCO-24 ist eine SUMME. Ein Tarifpreis von gestern plus eine
Geraeterate von heute ergibt einen Betrag, der an keinem Tag gegolten hat, und niemand
koennte ihm ansehen, dass er aus zwei Messungen stammt. Lieber eine sichtbare Luecke
(`tco_model.Tco.luecken`) als eine unsichtbare Mischung - und genau derselbe Befund hat
am 03.09.2026 die Preisform an ihre Zahl gebunden. Ebenso gemeinsam: die Kennzeichen
eines Klick-Buendels (`tco_buendel.KLICKFELDER`), die ein Adapterwert abraeumt.

`first_seen` bleibt unberuehrt: seit wann ein Angebot beobachtet wird, misst kein Lauf.

Was hier bewusst NICHT steht
----------------------------
Keine Loesch- oder Alterungslogik fuer BUENDEL. Die Alterung alter Werte ist seit A3
(STRATEGIE_GERAETE_V4, 20.09.2026) eine ENTSCHEIDUNG DER ANSICHT, nicht des Bestands:
`report/geraete_tco_karten.ist_frisch` (gegen `ALT_AB_TAGEN`) faellt ein Angebot aus
ab-Preis, Delta und Ranking, die Zeile bleibt ausgegraut mit Abrufdatum stehen. Der
Store haelt die Messung unveraendert bereit - zurueck in den Vergleich kommt ein
Angebot allein durch einen neuen Lauf, nie durch Loeschen.
`mark_stale` bleibt fuer LISTUNGEN reserviert (`geraete_pipeline`): "Nicht gelesen"
ist nicht "leer" (CLAUDE.md, Fallstricke).

Die Preishistorie steht hier sehr wohl - seit P2 (11.09.2026)
-------------------------------------------------------------
`geraete_tco.json` bleibt der AKTUELLE Stand je Buendel: die Seite liest weiter nur ihn.
Daneben waechst `data/state/geraete_tco_historie.jsonl`, eine Zeile je (buendel_id,
datum) mit den Messfeldern, der gerechneten Leitzahl `gesamt` (eingefroren aus
`tco_model.tco_24`, damit P5 die Reihe zeichnen kann, ohne die Rechnung frueherer Laeufe
nachzubauen), `abgerufen_am` und `rechenweise.FELD` (auch im Stand). Die Schreibregeln:

* gleiches Datum je Buendel -> die Zeile wird ERSETZT. Ein wiederholter Lauf am selben
  Tag ist dieselbe Messung, kein zweiter Punkt (sonst luege die Reihe ab P5 um die Zahl
  der Nachtlaeufe, nicht um den Markt).
* neues Datum -> neue Zeile dazu; ALTE Tage bleiben unveraendert stehen. Ein Messtag ist
  nicht nachholbar - deshalb wird die Datei beim Zusammenfuehren gelesen und nie blind
  neu geschrieben.
* Es gibt keine Rueckrechnung aus den frueheren Stand-Commits (Entscheidung 3 im
  Strategiedokument): die Reihe beginnt ehrlich mit dem ersten Lauf nach der Umstellung.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .. import rechenweise
from ..tarif_model import schreibe_buendelphasen
from ..tco_model import (
    Buendel,
    SimOnlyReferenz,
    buendel_id_aktuell,
    buendel_id_ohne_laufzeit,
    sim_only_id,
    tco_24,
)
from .tco_buendel import KLICKFELDER

log = logging.getLogger(__name__)

_MESSFELDER = (
    "tarif_id",
    "tarif_id_guete",
    "tarif_monatlich",
    "tarif_listenpreis",
    "tarif_bindung_monate",
    "buendel_monatlich",
    "geraet_zuzahlung",
    "geraet_monatsrate",
    "laufzeit_monate",
    "anschlusspreis",
    "quelle_url",
    "abgerufen_am",
    "zustand",
    "herleitung",
)

_REFERENZ_MESSFELDER = (
    "tarif_id",
    "tarif_id_guete",
    "tarif_sim_only_monatlich",
    "anschlusspreis",
    "quelle_url",
    "abgerufen_am",
    "quelle_art",
    "bindung_monate",
    "volumen_gb",
)

_HISTORIE_NAME = "geraete_tco_historie.jsonl"


def id_aus_satz(satz: dict) -> Optional[str]:
    """Die heutige Buendel-ID eines GESPEICHERTEN Satzes - die Lesemigration.

    Nimmt einen Stand-Eintrag aus `geraete_tco.json` ODER eine Zeile aus
    `geraete_tco_historie.jsonl` - beide tragen `id` und `laufzeit_monate`,
    und genau diese zwei Felder braucht `tco_model.buendel_id_aktuell`, um
    eine ID von VOR B1 (vier Segmente, ohne Laufzeit) demselben Buendel
    zuzuordnen wie die Zeilen von heute.

    Die Zuordnung steht HIER und nicht beim Lesen der Datei, weil beide
    Dateien diesem Modul gehoeren: eine zweite Migration in der Ansicht
    waere eine zweite Wahrheit ueber denselben Schluessel.

    `None` heisst "nicht zuordenbar" und ist protokolliert - der Aufrufer
    zaehlt solche Saetze und nennt sie, statt sie still fallen zu lassen.
    """
    if not isinstance(satz, dict):
        log.warning(
            "Lesemigration B1: Satz ist kein Woerterbuch (%s)", type(satz).__name__
        )
        return None
    neu_ = buendel_id_aktuell(satz.get("id") or "", satz.get("laufzeit_monate"))
    if neu_ is None:
        log.warning(
            "Lesemigration B1: ID %r hat weder die alte noch die "
            "heutige Form - nicht zuordenbar",
            satz.get("id"),
        )
    return neu_


def basis_aus_satz(satz: dict) -> Optional[str]:
    """Der laufzeitfreie Teil der ID eines gespeicherten Satzes.

    Der Notweg der Zeitreihe: eine gemessene Laufzeit, die im heutigen
    Stand nicht mehr steht, findet ueber ihn wenigstens Anbieter, SKU und
    Tarifnamen ihrer Schwestervariante - alles Angaben, die von der
    Laufzeit nicht abhaengen. Ein Messtag wird nicht verschwiegen, weil
    ein Anbieter seine Ratenlaufzeit geaendert hat.
    """
    if not isinstance(satz, dict):
        return None
    return buendel_id_ohne_laufzeit(satz.get("id") or "")


class TcoDB:
    """data/state/geraete_tco.json - Buendel und SIM-only-Referenzen.

    Format: {"updated": "YYYY-MM-DD", "buendel": [...], "sim_only": [...]}.

    Daneben fuehrt der Store die Preishistorie
    `geraete_tco_historie.jsonl` (Attribut `historie_path`): eine Zeile je
    (buendel_id, datum), siehe Modulkopf.
    """

    def __init__(self, path: Path, historie_path: Optional[Path] = None):
        self.path = Path(path)
        self.historie_path = (
            Path(historie_path)
            if historie_path is not None
            else self.path.parent / _HISTORIE_NAME
        )
        self._buendel: dict[str, dict] = {}
        self._referenzen: dict[str, dict] = {}
        self.updated = ""
        self.pruefung: dict | None = None
        self._historie_pendente: dict[tuple[str, str], dict] = {}
        self.lesbar = True
        if not self.path.exists():
            return
        try:
            roh = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("geraete_tco.json unlesbar (%s) - starte leer", exc)
            self.lesbar = False
            return
        self.updated = roh.get("updated", "")
        pruefung = roh.get("pruefung")
        self.pruefung = pruefung if isinstance(pruefung, dict) else None
        migriert = 0
        for eintrag in roh.get("buendel") or []:
            bid = id_aus_satz(eintrag)
            if bid is None:
                if eintrag.get("id"):
                    self._buendel[eintrag["id"]] = eintrag
                continue
            if bid != eintrag.get("id"):
                migriert += 1
                eintrag["id"] = bid
            self._buendel[bid] = eintrag
        if migriert:
            log.info(
                "Lesemigration B1: %d von %d Buendel-Eintraegen auf "
                "die Laufzeit-ID gehoben (%s bleibt bis zum naechsten "
                "save() unveraendert)",
                migriert,
                len(self._buendel),
                self.path.name,
            )
        for eintrag in roh.get("sim_only") or []:
            if eintrag.get("id"):
                self._referenzen[eintrag["id"]] = eintrag

    def buendel(self) -> list[dict]:
        return sorted(
            self._buendel.values(),
            key=lambda e: (e.get("anbieter", ""), e.get("id", "")),
        )

    def referenzen(self) -> list[dict]:
        return sorted(
            self._referenzen.values(),
            key=lambda e: (e.get("anbieter", ""), e.get("id", "")),
        )

    def nach_id(self, buendel_id: str) -> Optional[dict]:
        return self._buendel.get(buendel_id)

    def referenz(self, anbieter: str, tarif_name: str) -> Optional[dict]:
        """Der Massstab fuer ein Buendel dieses Anbieters und Tarifs."""
        return self._referenzen.get(sim_only_id(anbieter, tarif_name))

    def historie_lage(self) -> dict:
        """Die Lage der Buendel-Historie: seit wann sie laeuft, wie viele
        Messtage und Buendel stehen (O4, STRATEGIE_GERAETE_OPTIK §3).

        Der ehrliche Satz im Verlaufs-Reiter ("Die TCO-24-Historie je
        Buendel beginnt mit dem ersten naechtlichen Lauf am …") nennt das
        ECHTE Datum aus dieser Datei - das '12.09.2026' des Entwurfs ist
        der Stand des Entwurfstages, keine Wahrheit ueber jeden Bestand.
        Gelesen wird hier und nicht im Renderer, weil der Pfad dieser
        Datei hier zuhause ist (derselbe Grund wie bei `historie_path`).
        Eine fehlende oder leere Datei ist kein Fehler, sondern der
        Zustand vor dem ersten Lauf.
        """
        tage: set[str] = set()
        ids: set[str] = set()
        if self.historie_path.exists():
            try:
                text = self.historie_path.read_text(encoding="utf-8")
            except OSError:
                text = ""
            for zeile in text.splitlines():
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    satz = json.loads(zeile)
                except json.JSONDecodeError:
                    continue
                if satz.get("datum"):
                    tage.add(str(satz["datum"]))
                bid = id_aus_satz(satz) if satz.get("id") else None
                if bid:
                    ids.add(bid)
                elif satz.get("id"):
                    ids.add(str(satz["id"]))
        return {
            "messtage": len(tage),
            "seit": min(tage) if tage else "",
            "buendel": len(ids),
        }

    def upsert_buendel(self, buendel, today: str) -> tuple[int, set]:
        """Buendel aufnehmen oder auffrischen.

        Gibt (Zahl der NEU aufgenommenen, IDs aller in diesem Aufruf gesehenen) zurueck
        - dieselbe Bauform wie `GeraeteDB.upsert`, damit ein spaeterer Sammellauf beide
        gleich behandeln kann.
        """
        neu = 0
        gesehen: set[str] = set()
        for satz in buendel:
            if not isinstance(satz, Buendel):
                raise TypeError(f"kein Buendel: {type(satz).__name__}")
            if (
                satz.geraet_zuzahlung is not None
                or satz.geraet_monatsrate is not None
                or satz.buendel_monatlich is not None
            ) and not (satz.tarif_id or "").strip():
                raise ValueError(
                    f"Geraetepreis ohne aufloesbaren Tarif: {satz.id} "
                    f"(tarif_name={satz.tarif_name!r}). Ein Buendelpreis "
                    f"ohne tarif_id wird verworfen, nicht gespeichert."
                )

        for satz in buendel:
            bid = satz.id
            eintrag = self._buendel.get(bid)
            if eintrag is None:
                eintrag = {
                    "id": bid,
                    "sku_id": satz.sku_id,
                    "anbieter": satz.anbieter,
                    "tarif_name": satz.tarif_name,
                    "first_seen": today,
                }
                self._buendel[bid] = eintrag
                neu += 1
            gesehen.add(bid)
            self._schreibe_messung(eintrag, satz, _MESSFELDER)
            for f in KLICKFELDER:
                eintrag.pop(f, None)
                eintrag.update({f: getattr(satz, f)} if getattr(satz, f) else {})
            eintrag["rabatte"] = [asdict(r) for r in satz.rabatte]
            eintrag["aktionen"] = [asdict(a) for a in satz.aktionen]
            eintrag["last_verified"] = today
            self._historie_pendente[(bid, today)] = self._historie_zeile(satz, today)
        return neu, gesehen

    def setze_referenzen(
        self, referenzen, today: str, anbieter: Optional[set] = None
    ) -> int:
        """SIM-only-Referenzen aufnehmen oder auffrischen. Gibt die Zahl der
        neu aufgenommenen zurueck.

        `anbieter` (Optional, Menge von Anbieternamen wie im Tarifbestand)
        grenzt den Schreibzug ein: Referenzen ANDERER Anbieter werden weder
        aufgenommen noch veraendert. Der Default `None` bedeutet alle -
        das Verhalten des naechtlichen Gesamtlaufs, der den Massstab als
        EIN Ganzes neu ableitet.
        """
        neu = 0
        for satz in referenzen:
            if anbieter is not None and satz.anbieter not in anbieter:
                continue
            if not isinstance(satz, SimOnlyReferenz):
                raise TypeError(f"keine SimOnlyReferenz: {type(satz).__name__}")
            rid = satz.id
            eintrag = self._referenzen.get(rid)
            if eintrag is None:
                eintrag = {
                    "id": rid,
                    "anbieter": satz.anbieter,
                    "tarif_name": satz.tarif_name,
                    "first_seen": today,
                }
                self._referenzen[rid] = eintrag
                neu += 1
            self._schreibe_messung(eintrag, satz, _REFERENZ_MESSFELDER)
            eintrag["rabatte"] = [asdict(r) for r in satz.rabatte]
            eintrag["last_verified"] = today
        return neu

    def ersetze_referenzen(
        self, referenzen, today: str, anbieter: Optional[set] = None
    ) -> tuple[int, int]:
        """Den Referenzbestand VOLLSTAENDIG neu setzen. Gibt (neu, entfernt).

        Warum hier ersetzt und sonst nirgends in diesem Projekt gelöscht
        wird: die SIM-only-Referenzen sind ABGELEITET. Sie entstehen bei
        jedem Lauf neu aus `data/state/tarife.jsonl` und sind kein eigener
        Messwert - anders als eine Listung, deren Verschwinden selbst eine
        Nachricht ist (`GeraeteDB.mark_stale` altert deshalb in zwei
        Stufen, statt zu loeschen).

        Ohne diese Methode waechst der Bestand bei jeder Umbenennung: am
        04.09.2026 standen nach zwei Laeufen 40 Referenzen zu 32 Tarifen
        auf der Seite, darunter fuenfzehn, die aus dem Tarifbestand
        laengst verschwunden waren. Aufgefallen ist es beim ANSEHEN der
        Tafel - kein Test hat es gemeldet, weil beide Laeufe fuer sich
        richtig gerechnet haben.

        Sobald eine ZWEITE Quelle Referenzen liefert (etwa ein Adapter,
        der den SIM-only-Preis von der Anbieterseite liest), gehoert an
        diese Stelle eine Herkunft und kein pauschales Ersetzen mehr.
        Heute gibt es genau eine Quelle.

        `anbieter` schraenkt die Ersetzung auf die genannten Anbieter ein
        (Lokallauf eines EINZELNEN Anbieters, siehe run_geraete_stage):
        Fremde Bestandssaetze werden weder aufgefrischt noch datiert noch
        als veraltet entfernt - ein Lauf, der einen Anbieter misst, hat
        ueber die anderen nichts auszusagen. Das ist KEIN Widerspruch zum
        Ersetzen: innerhalb des Scopes gilt weiterhin die volle Semantik,
        inklusive Wegnehmen umbenannter Tarife.
        """
        neu = self.setze_referenzen(referenzen, today, anbieter=anbieter)
        gewuenscht = {satz.id for satz in referenzen}
        veraltet = [
            rid
            for rid, eintrag in self._referenzen.items()
            if rid not in gewuenscht
            and (anbieter is None or eintrag.get("anbieter") in anbieter)
        ]
        for rid in veraltet:
            del self._referenzen[rid]
        return neu, len(veraltet)

    @staticmethod
    def _schreibe_messung(eintrag: dict, satz, felder: tuple) -> None:
        """Alle Messfelder gemeinsam, auch die leeren - siehe Modulkopf."""
        eintrag.update({feld: getattr(satz, feld) for feld in felder})
        schreibe_buendelphasen(eintrag, satz)
        eintrag.update(rechenweise.felder(satz))

    @staticmethod
    def _historie_zeile(satz: Buendel, datum: str) -> dict:
        """Eine Zeile der Preishistorie - siehe Modulkopf (P2).

        Die Messfelder kommen aus derselben Positivliste wie der Stand (`_MESSFELDER`):
        ein neues Messfeld muss in BEIDEN landen, sonst klaffe Stand und Historie
        auseinander. `gesamt` ist die Leitzahl der Messung, eingefroren aus
        `tco_model.tco_24` - die Rechnung bleibt dort, hier steht nur ihr Ergebnis von
        damals. Sie kann `None` sein (Messung ohne jeden Posten); das ist eine ehrliche
        Luecke und kein Fehler.
        """
        zeile = {"id": satz.id, "datum": datum}
        TcoDB._schreibe_messung(zeile, satz, _MESSFELDER)
        zeile["gesamt"] = tco_24(satz).gesamt
        return zeile

    def save(self, today: str) -> bool:
        """Schreibt die Datei - aber nur, wenn sie etwas zu sagen hat.

        Ein leerer Bestand legt KEINE Datei an. Solange kein Sammellauf Buendel liefert
        (Phase 6/7 des Strategiedokuments), soll dieser Zweig im naechtlichen Lauf
        nichts hinterlassen: eine Datei mit zwei leeren Listen sieht im Repo aus wie ein
        Ergebnis und ist keins.

        Seit P2 schreibt `save` ZUSAETZLICH die vorgemerkten Historienzeilen dieses
        Laufs in `geraete_tco_historie.jsonl`. Die Stand-Datei wird ZUERST gesichert:
        ein Fehler an der Historie darf den Messtag der Gegenwart nicht kosten (der
        Rueckgabewert bleibt an der Stand-Datei gebunden).
        """
        if not self._buendel and not self._referenzen:
            return False
        self.updated = today
        self.path.parent.mkdir(parents=True, exist_ok=True)
        daten = {
            "updated": today,
            "buendel": self.buendel(),
            "sim_only": self.referenzen(),
            **({"pruefung": self.pruefung} if self.pruefung else {}),
        }
        self.path.write_text(
            json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        self._schreibe_historie()
        return True

    def _schreibe_historie(self) -> bool:
        """Fuegt die Messungen dieses Laufs in die Historie ein.

        True heisst geschrieben, False heisst "nichts zu schreiben" ODER
        "nicht angefasst" - eine unlesbare Historie wird uebersprungen und
        NICHT durch eine nur-neue ersetzt: das Zusammenfuegen haette den
        Rest der Datei vernichtet, gegen genau das ist P2 gebaut. Der
        Schaden ist im Protokoll sichtbar, der Bestand trotzdem gesichert.

        Ein Schreibfehler (Platte, Rechte) wirft dagegen - er darf nicht
        als Erfolg durchgehen.
        """
        if not self._historie_pendente:
            return False
        zusammen: dict[tuple[str, str], dict] = {}
        if self.historie_path.exists():
            try:
                text = self.historie_path.read_text(encoding="utf-8")
                saetze = [
                    json.loads(zeile) for zeile in text.splitlines() if zeile.strip()
                ]
            except (json.JSONDecodeError, OSError) as exc:
                log.warning(
                    "%s unlesbar (%s) - Historie NICHT angefasst, "
                    "nur der Stand geschrieben",
                    self.historie_path.name,
                    exc,
                )
                return False
            if any(
                not isinstance(satz, dict)
                or not (satz.get("id") or "").strip()
                or not (satz.get("datum") or "").strip()
                for satz in saetze
            ):
                log.warning(
                    "%s enthaelt Zeilen ohne (id, datum) - Historie NICHT angefasst",
                    self.historie_path.name,
                )
                return False
            for satz in saetze:
                zusammen[(satz["id"], satz["datum"])] = satz
        zusammen.update(self._historie_pendente)
        self.historie_path.parent.mkdir(parents=True, exist_ok=True)
        self.historie_path.write_text(
            "".join(
                json.dumps(satz, ensure_ascii=False) + "\n"
                for satz in zusammen.values()
            ),
            encoding="utf-8",
        )
        return True
