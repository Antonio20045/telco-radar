"""Bestand der Buendel und der SIM-only-Referenzen - `geraete_tco.json`.

Warum eine EIGENE Datei
-----------------------
`data/state/geraete_db.json` traegt seit dem 10.08.2026 die Listungen, also
was ein Anbieter fuer ein GERAET verlangt. Ein Buendel ist ein anderer
Sachverhalt: es kommt von einer Tarifseite, hat einen anderen Lebenszyklus
und eine andere Identitaet (SKU x Anbieter x Tarif statt SKU x Anbieter).
Es steht deshalb in

    data/state/geraete_tco.json    Buendel und SIM-only-Referenzen

und nicht als weiterer Abschnitt in der Listungsdatei. Der Grund ist nicht
Ordnungsliebe, sondern Risiko: `geraete_db.json` traegt 391 gewachsene
Listungen und haengt an `geraete_preise.jsonl`, das die ganze Preishistorie
haelt. Eine neue Entitaet, die diese Datei umschreibt, kann eine `listung_id`
verschieben - und eine verschobene ID zerreisst still den Verlauf, dieselbe
Fehlerklasse wie ein neu vergebener Farbschluessel
(`geraete_model.farbe_aus_titel`). Zwei Dateien koennen das strukturell
nicht: dieses Modul oeffnet die andere gar nicht.

Die IDs koennen sich ebenfalls nicht ueberschneiden, und zwar an ihrer Form
(`tco_model.buendel_id`): eine `listung_id` hat zwei Bestandteile, ein
Buendel vier, eine Referenz drei.

Die eine Regel, die dieses Modul von `geraete_store` unterscheidet
------------------------------------------------------------------
**Ein Buendeldatensatz zeigt EINE Messung.** Wo `GeraeteDB.upsert` einen
Wert, den ein Lauf nicht fand, stehen laesst (ein Ausfall der Extraktion ist
keine Preisaenderung), schreibt ein Lauf hier ALLE Preisfelder eines
Buendels gemeinsam - auch als `None`. Der Grund ist die Kennzahl: TCO-24 ist
eine SUMME. Ein Tarifpreis von gestern plus eine Geraeterate von heute ergibt
einen Betrag, der an keinem Tag gegolten hat, und niemand koennte ihm ansehen,
dass er aus zwei Messungen stammt. Lieber eine sichtbare Luecke
(`tco_model.Tco.luecken`) als eine unsichtbare Mischung - und genau derselbe
Befund hat am 03.09.2026 die Preisform an ihre Zahl gebunden.

`first_seen` bleibt davon unberuehrt: seit wann ein Angebot beobachtet wird,
ist keine Messung dieses Laufs.

Was hier bewusst NICHT steht
----------------------------
Keine Zwei-Stufen-Auslistung (`mark_stale`) - eine Alterungslogik ohne
einen einzigen Lauf waere gegen nichts gemessen. Bis dahin wird nichts
geloescht.

Die Preishistorie steht hier sehr wohl - seit P2 (11.09.2026)
-------------------------------------------------------------
`geraete_tco.json` bleibt der AKTUELLE Stand je Buendel: die Seite liest
weiter nur ihn. Daneben waechst

    data/state/geraete_tco_historie.jsonl

eine Zeile je (buendel_id, datum) mit den Messfeldern, der gerechneten
Leitzahl `gesamt` (eingefroren aus `tco_model.tco_24`, damit P5 die Reihe
zeichnen kann, ohne die Rechnung frueherer Laeufe nachzubauen) und
`abgerufen_am`. Die Schreibregeln:

* gleiches Datum je Buendel -> die Zeile wird ERSETZT. Ein wiederholter
  Lauf am selben Tag ist dieselbe Messung, kein zweiter Punkt (sonst
  luege die Reihe ab P5 um die Zahl der Nachtlaeufe, nicht um den Markt).
* neues Datum -> neue Zeile dazu; ALTE Tage bleiben unveraendert stehen.
  Ein Messtag ist nicht nachholbar - deshalb wird die Datei beim
  Zusammenfuehren gelesen und nie blind neu geschrieben.
* Es gibt keine Rueckrechnung aus den frueheren Stand-Commits
  (Entscheidung 3 im Strategiedokument): die Reihe beginnt ehrlich mit
  dem ersten Lauf nach der Umstellung.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from ..tco_model import Buendel, SimOnlyReferenz, sim_only_id, tco_24

log = logging.getLogger(__name__)

# Die Felder eines Buendels, die eine Messung sind - sie werden gemeinsam
# geschrieben, siehe Modulkopf.
# `buendel_monatlich` und `tarif_bindung_monate` STEHEN HIER MIT, seit es
# sie gibt (Phase R). Diese Liste ist eine POSITIVLISTE - dieselbe Falle
# wie `_items_payload` in `analyze/agents.py`: ein neues Feld am Datensatz
# landet hier NICHT von selbst, und ein Buendel, dessen einziger Preis der
# Buendelmonatsbetrag ist (1&1), waere beim Ablegen still preislos
# geworden.
# `zustand` seit dem 04.09.2026 (QA-Befund B1): der Geraetezustand ist eine
# Preisdimension, und ein Buendel, das ihn nicht mitfuehrt, sieht in der
# Tafel aus wie ein Neugeraet.
_MESSFELDER = ("tarif_id", "tarif_id_guete", "tarif_monatlich",
               "tarif_bindung_monate", "buendel_monatlich",
               "geraet_zuzahlung", "geraet_monatsrate",
               "laufzeit_monate", "anschlusspreis", "quelle_url",
               "abgerufen_am", "zustand")

# `bindung_monate` und `volumen_gb` seit S-5 (09.09.2026): dieselbe
# Positivliste-Pflicht wie bei `_MESSFELDER` - ein Messfeld, das hier
# fehlt, wuerde beim naechsten Lauf still geleert, obwohl die Quelle es
# weiterhin nennt.
_REFERENZ_MESSFELDER = ("tarif_id", "tarif_id_guete",
                        "tarif_sim_only_monatlich", "anschlusspreis",
                        "quelle_url", "abgerufen_am", "quelle_art",
                        "bindung_monate", "volumen_gb")

# Die Append-Historie liegt NEBEN der Stand-Datei (P2, 11.09.2026) - siehe
# Modulkopf. Ihr Name ist fest, weil der naechtliche Lauf sie namentlich
# committet (.github/workflows/geraete.yml).
_HISTORIE_NAME = "geraete_tco_historie.jsonl"


class TcoDB:
    """data/state/geraete_tco.json - Buendel und SIM-only-Referenzen.

    Format: {"updated": "YYYY-MM-DD", "buendel": [...], "sim_only": [...]}.

    Daneben fuehrt der Store die Preishistorie
    `geraete_tco_historie.jsonl` (Attribut `historie_path`): eine Zeile je
    (buendel_id, datum), siehe Modulkopf.
    """

    def __init__(self, path: Path, historie_path: Optional[Path] = None):
        self.path = Path(path)
        self.historie_path = (Path(historie_path) if historie_path is not None
                              else self.path.parent / _HISTORIE_NAME)
        self._buendel: dict[str, dict] = {}
        self._referenzen: dict[str, dict] = {}
        self.updated = ""
        # Die Messungen dieses PROZESSES, noch nicht geschrieben: der
        # Schluessel ist (buendel_id, datum), ein zweiter Upsert am selben
        # Tag ersetzt den ersten - dieselbe Idempotenz, die beim
        # Zusammenfuehren mit der Datei gilt.
        self._historie_pendente: dict[tuple[str, str], dict] = {}
        # Eine unlesbare Datei ist NICHT dasselbe wie "noch nichts gefunden" -
        # dieselbe Unterscheidung wie in `GeraeteDB` und aus demselben Grund:
        # sonst meldet die Seite eine leere Datenlage, wo ein Lesefehler war.
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
        for eintrag in (roh.get("buendel") or []):
            if eintrag.get("id"):
                self._buendel[eintrag["id"]] = eintrag
        for eintrag in (roh.get("sim_only") or []):
            if eintrag.get("id"):
                self._referenzen[eintrag["id"]] = eintrag

    # -------------------------------------------------------------- lesen

    def buendel(self) -> list[dict]:
        return sorted(self._buendel.values(),
                      key=lambda e: (e.get("anbieter", ""), e.get("id", "")))

    def referenzen(self) -> list[dict]:
        return sorted(self._referenzen.values(),
                      key=lambda e: (e.get("anbieter", ""), e.get("id", "")))

    def nach_id(self, buendel_id: str) -> Optional[dict]:
        return self._buendel.get(buendel_id)

    def referenz(self, anbieter: str, tarif_name: str) -> Optional[dict]:
        """Der Massstab fuer ein Buendel dieses Anbieters und Tarifs."""
        return self._referenzen.get(sim_only_id(anbieter, tarif_name))

    # ------------------------------------------------------------ schreiben

    def upsert_buendel(self, buendel, today: str) -> tuple[int, set]:
        """Buendel aufnehmen oder auffrischen.

        Gibt (Zahl der NEU aufgenommenen, IDs aller in diesem Aufruf
        gesehenen) zurueck - dieselbe Bauform wie `GeraeteDB.upsert`, damit
        ein spaeterer Sammellauf beide gleich behandeln kann.
        """
        neu = 0
        gesehen: set[str] = set()
        # VOLLSTAENDIG PRUEFEN, BEVOR ETWAS GESCHRIEBEN WIRD. Ein Wurf
        # mitten in der Schleife liesse die schon aufgenommenen Buendel im
        # Speicher stehen - ein Aufrufer, der die Ausnahme faengt und
        # `save()` ruft, schriebe einen halben Messtag in die Datei. Ein
        # Adapter uebergibt seine achtzig Buendel in EINEM Aufruf.
        for satz in buendel:
            if not isinstance(satz, Buendel):
                raise TypeError(f"kein Buendel: {type(satz).__name__}")
            if (satz.geraet_zuzahlung is not None
                    or satz.geraet_monatsrate is not None
                    # Ein Buendelmonatspreis IST ein Geraetepreis - er
                    # traegt Tarif und Geraet in einer Zahl. Ohne ihn hier
                    # haette ein 1&1-Satz die Regel unterlaufen und einen
                    # Preis ohne nachschlagbaren Tarif abgelegt.
                    or satz.buendel_monatlich is not None) \
                    and not (satz.tarif_id or "").strip():
                # Phase 6, Abnahmekriterium 3: kein Buendelpreis im Bestand
                # ohne aufloesbaren Tarif. Die Regel steht HIER und nicht im
                # Datensatz, weil "im Bestand" genau diese Datei meint - ein
                # Buendel zu bauen und festzustellen, dass sein Tarif nicht
                # aufloest, ist ein gueltiger Zwischenschritt; es
                # ABZULEGEN waere eine Zahl, deren Bezugsgroesse niemand
                # nachschlagen kann. Dieselbe Haltung wie
                # `geraete_model.Listung`, die eine Zuzahlung ohne
                # `tarif_referenz` gar nicht erst entstehen laesst.
                raise ValueError(
                    f"Geraetepreis ohne aufloesbaren Tarif: {satz.id} "
                    f"(tarif_name={satz.tarif_name!r}). Ein Buendelpreis "
                    f"ohne tarif_id wird verworfen, nicht gespeichert.")

        for satz in buendel:
            bid = satz.id
            eintrag = self._buendel.get(bid)
            if eintrag is None:
                eintrag = {"id": bid, "sku_id": satz.sku_id,
                           "anbieter": satz.anbieter,
                           "tarif_name": satz.tarif_name,
                           "first_seen": today}
                self._buendel[bid] = eintrag
                neu += 1
            gesehen.add(bid)
            self._schreibe_messung(eintrag, satz, _MESSFELDER)
            eintrag["rabatte"] = [asdict(r) for r in satz.rabatte]
            eintrag["last_verified"] = today
            # Dieselbe Messung auch fuer die Historie vormerken - am `today`
            # dieses Aufrufs, nicht am `save()`-Datum: die Zeile gehoert dem
            # Lauf, der sie gemessen hat. Der Schluessel ersetzt bei
            # wiederholtem Upsert denselben Tag still (idempotent).
            self._historie_pendente[(bid, today)] = self._historie_zeile(
                satz, today)
        return neu, gesehen

    def setze_referenzen(self, referenzen, today: str) -> int:
        """SIM-only-Referenzen aufnehmen oder auffrischen. Gibt die Zahl der
        neu aufgenommenen zurueck."""
        neu = 0
        for satz in referenzen:
            if not isinstance(satz, SimOnlyReferenz):
                raise TypeError(f"keine SimOnlyReferenz: "
                                f"{type(satz).__name__}")
            rid = satz.id
            eintrag = self._referenzen.get(rid)
            if eintrag is None:
                eintrag = {"id": rid, "anbieter": satz.anbieter,
                           "tarif_name": satz.tarif_name, "first_seen": today}
                self._referenzen[rid] = eintrag
                neu += 1
            self._schreibe_messung(eintrag, satz, _REFERENZ_MESSFELDER)
            eintrag["rabatte"] = [asdict(r) for r in satz.rabatte]
            eintrag["last_verified"] = today
        return neu

    def ersetze_referenzen(self, referenzen, today: str) -> tuple[int, int]:
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
        """
        # AUFFRISCHEN, dann wegnehmen - nicht leeren und neu befuellen.
        # Beim Leeren verloere jede Referenz ihr `first_seen`, und dann
        # waere jede von ihnen bei jedem Lauf "seit heute bekannt";
        # ausserdem zaehlte `neu` jedes Mal den ganzen Bestand.
        neu = self.setze_referenzen(referenzen, today)
        gewuenscht = {satz.id for satz in referenzen}
        veraltet = [rid for rid in self._referenzen if rid not in gewuenscht]
        for rid in veraltet:
            del self._referenzen[rid]
        return neu, len(veraltet)

    @staticmethod
    def _schreibe_messung(eintrag: dict, satz, felder: tuple) -> None:
        """Alle Messfelder gemeinsam, auch die leeren - siehe Modulkopf."""
        for feld in felder:
            eintrag[feld] = getattr(satz, feld)

    @staticmethod
    def _historie_zeile(satz: Buendel, datum: str) -> dict:
        """Eine Zeile der Preishistorie - siehe Modulkopf (P2).

        Die Messfelder kommen aus derselben Positivliste wie der Stand
        (`_MESSFELDER`): ein neues Messfeld muss in BEIDEN landen, sonst
        klaffe Stand und Historie auseinander. `gesamt` ist die Leitzahl
        der Messung, eingefroren aus `tco_model.tco_24` - die Rechnung
        bleibt dort, hier steht nur ihr Ergebnis von damals. Sie kann
        `None` sein (Messung ohne jeden Posten); das ist eine ehrliche
        Luecke und kein Fehler.
        """
        zeile = {"id": satz.id, "datum": datum}
        for feld in _MESSFELDER:
            zeile[feld] = getattr(satz, feld)
        zeile["gesamt"] = tco_24(satz).gesamt
        return zeile

    # ---------------------------------------------------------------- save

    def save(self, today: str) -> bool:
        """Schreibt die Datei - aber nur, wenn sie etwas zu sagen hat.

        Ein leerer Bestand legt KEINE Datei an. Solange kein Sammellauf
        Buendel liefert (Phase 6/7 des Strategiedokuments), soll dieser
        Zweig im naechtlichen Lauf nichts hinterlassen: eine Datei mit zwei
        leeren Listen sieht im Repo aus wie ein Ergebnis und ist keins.

        Seit P2 schreibt `save` ZUSAETZLICH die vorgemerkten Historienzeilen
        dieses Laufs in `geraete_tco_historie.jsonl`. Die Stand-Datei wird
        ZUERST gesichert: ein Fehler an der Historie darf den Messtag der
        Gegenwart nicht kosten (der Rueckgabewert bleibt an der Stand-Datei
        gebunden).
        """
        if not self._buendel and not self._referenzen:
            return False
        self.updated = today
        self.path.parent.mkdir(parents=True, exist_ok=True)
        daten = {"updated": today, "buendel": self.buendel(),
                 "sim_only": self.referenzen()}
        self.path.write_text(json.dumps(daten, ensure_ascii=False, indent=1),
                             encoding="utf-8")
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
                saetze = [json.loads(zeile) for zeile in text.splitlines()
                          if zeile.strip()]
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("%s unlesbar (%s) - Historie NICHT angefasst, "
                            "nur der Stand geschrieben",
                            self.historie_path.name, exc)
                return False
            if any(not isinstance(satz, dict)
                   or not (satz.get("id") or "").strip()
                   or not (satz.get("datum") or "").strip()
                   for satz in saetze):
                # Eine Zeile ohne Schluessel liesse sich nicht zusammen-
                # fuehren; sie ueberspringen hiesse sie loeschen.
                log.warning("%s enthaelt Zeilen ohne (id, datum) - "
                            "Historie NICHT angefasst",
                            self.historie_path.name)
                return False
            for satz in saetze:
                # Bestehende Reihenfolge bleibt stehen; ein Doppel-Schluessel
                # aus frueheren Laeufen haelt den INHALT des letzten.
                zusammen[(satz["id"], satz["datum"])] = satz
        # Die Messungen dieses Laufs ERSETZEN einen gleichschluessigen Tag
        # an dessen Stelle und neue Tage haengen hinten an - alte Tage
        # bleiben in Inhalt und Stellung unveraendert.
        zusammen.update(self._historie_pendente)
        self.historie_path.parent.mkdir(parents=True, exist_ok=True)
        self.historie_path.write_text(
            "".join(json.dumps(satz, ensure_ascii=False) + "\n"
                    for satz in zusammen.values()),
            encoding="utf-8")
        return True
