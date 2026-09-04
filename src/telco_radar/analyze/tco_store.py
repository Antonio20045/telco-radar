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
Keine Zwei-Stufen-Auslistung (`mark_stale`) und keine Preishistorie. Beides
braucht erst einen Lauf, der Buendel wirklich sammelt - den gibt es noch
nicht, und eine Alterungslogik ohne einen einzigen Lauf waere gegen nichts
gemessen. Bis dahin wird nichts geloescht.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from ..tco_model import Buendel, SimOnlyReferenz, sim_only_id

log = logging.getLogger(__name__)

# Die Felder eines Buendels, die eine Messung sind - sie werden gemeinsam
# geschrieben, siehe Modulkopf.
_MESSFELDER = ("tarif_id", "tarif_id_guete", "tarif_monatlich",
               "geraet_zuzahlung", "geraet_monatsrate",
               "laufzeit_monate", "anschlusspreis", "quelle_url",
               "abgerufen_am")

_REFERENZ_MESSFELDER = ("tarif_id", "tarif_id_guete",
                        "tarif_sim_only_monatlich", "anschlusspreis",
                        "quelle_url", "abgerufen_am")


class TcoDB:
    """data/state/geraete_tco.json - Buendel und SIM-only-Referenzen.

    Format: {"updated": "YYYY-MM-DD", "buendel": [...], "sim_only": [...]}.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._buendel: dict[str, dict] = {}
        self._referenzen: dict[str, dict] = {}
        self.updated = ""
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
        for satz in buendel:
            if not isinstance(satz, Buendel):
                raise TypeError(f"kein Buendel: {type(satz).__name__}")
            if (satz.geraet_zuzahlung is not None
                    or satz.geraet_monatsrate is not None) \
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

    # ---------------------------------------------------------------- save

    def save(self, today: str) -> bool:
        """Schreibt die Datei - aber nur, wenn sie etwas zu sagen hat.

        Ein leerer Bestand legt KEINE Datei an. Solange kein Sammellauf
        Buendel liefert (Phase 6/7 des Strategiedokuments), soll dieser
        Zweig im naechtlichen Lauf nichts hinterlassen: eine Datei mit zwei
        leeren Listen sieht im Repo aus wie ein Ergebnis und ist keins.
        """
        if not self._buendel and not self._referenzen:
            return False
        self.updated = today
        self.path.parent.mkdir(parents=True, exist_ok=True)
        daten = {"updated": today, "buendel": self.buendel(),
                 "sim_only": self.referenzen()}
        self.path.write_text(json.dumps(daten, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        return True
