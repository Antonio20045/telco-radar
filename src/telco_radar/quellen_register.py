"""Quellenregister: Herkunft, Abnahmedatum, letzter Erfolg - und Quarantaene.

Warum es das gibt
-----------------
Bei 130 Quellen reicht ein deutscher Kommentar je YAML-Eintrag. Bei 1000
nicht mehr: dann weiss in sechs Monaten niemand mehr, welche Quelle
eigentlich noch lebt, wann sie abgenommen wurde und woher sie kam. Und eine
Quelle, die still nichts mehr liefert, faellt in einer Liste dieser Groesse
niemandem auf - die Konfiguration verrottet, ohne dass es jemand merkt.

Das Register (data/state/quellen_register.json) fuehrt deshalb je Quelle
maschinenlesbar mit:

  herkunft        woher der Vorschlag stammt (aus der YAML)
  abgenommen      wann sie den Abnahme-Check bestanden hat (aus der YAML)
  erster_lauf     wann sie zum ersten Mal mitlief
  letzter_erfolg  wann sie zuletzt Inhalt geliefert hat
  laeufe/ok/leer/fehler   die Bilanz
  serie_ohne_inhalt       wie viele Laeufe am Stueck sie nichts lieferte

Quarantaene
-----------
Nach `quarantaene_nach_laeufen` Laeufen ohne Inhalt wird eine Quelle
stillgelegt: sie wird nicht mehr abgerufen, steht aber weiter mit Status
"quarantaene" im Laufprotokoll. Eine still verschwundene Quelle waere
schlimmer als eine tote.

Die Stilllegung ist keine Einbahnstrasse. Alle `quarantaene_probe_alle`
Laeufe bekommt eine stillgelegte Quelle einen Bewaehrungslauf; liefert sie
wieder Inhalt, wird die Quarantaene aufgehoben. Ohne das waere ein
zweiwoechiger Serverausfall beim Betreiber ein dauerhaftes Todesurteil.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

VERSION = 1


class QuellenRegister:
    """Bestand und Gesundheitszustand aller Quellen ueber Laeufe hinweg."""

    def __init__(self, path: Path, quarantaene_nach: int = 6,
                 probe_alle: int = 10):
        self.path = path
        self.quarantaene_nach = int(quarantaene_nach or 0)
        self.probe_alle = max(1, int(probe_alle or 1))
        self.quellen: dict[str, dict] = {}
        self.lauf_nummer = 0
        if path.exists():
            try:
                roh = json.loads(path.read_text(encoding="utf-8"))
                self.quellen = dict(roh.get("quellen") or {})
                self.lauf_nummer = int(roh.get("lauf_nummer") or 0)
            except (json.JSONDecodeError, OSError, TypeError) as exc:
                log.error("Quellenregister nicht lesbar (%s) - es wird neu "
                          "aufgebaut; die Quarantaene beginnt von vorn", exc)

    # ------------------------------------------------------------ Abfragen
    def stillgelegt(self) -> set[str]:
        """URLs, die in DIESEM Lauf nicht abgerufen werden sollen.

        Der Bewaehrungslauf haengt an der Lauf-Nummer, nicht am Zufall: so
        laesst sich im Protokoll nachrechnen, warum eine Quelle gerade
        wieder mitlief.
        """
        naechste = self.lauf_nummer + 1
        return {
            url for url, e in self.quellen.items()
            if e.get("quarantaene_seit") and naechste % self.probe_alle != 0
        }

    def eintrag(self, url: str) -> dict:
        return self.quellen.get(url, {})

    # ----------------------------------------------------------- Fortschreiben
    def aktualisieren(self, ergebnisse: list[dict], datum: str,
                      konfiguration: dict[str, dict] | None = None
                      ) -> dict[str, list[str]]:
        """Ein Laufergebnis einarbeiten.

        Liefert {"neu": [...], "stillgelegt": [...], "befreit": [...]} -
        genau die drei Ereignisse, die ins Laufprotokoll gehoeren.
        """
        self.lauf_nummer += 1
        konfiguration = konfiguration or {}
        ereignisse: dict[str, list[str]] = {"neu": [], "stillgelegt": [],
                                            "befreit": []}
        gesehen: set[str] = set()

        for rec in ergebnisse:
            url = rec.get("url", "")
            if not url:
                continue
            gesehen.add(url)
            neu = url not in self.quellen
            e = self.quellen.setdefault(url, {
                "erster_lauf": datum, "laeufe": 0, "ok": 0, "leer": 0,
                "fehler": 0, "serie_ohne_inhalt": 0,
            })
            if neu:
                ereignisse["neu"].append(url)
            e["name"] = rec.get("name") or e.get("name", "")
            e["origin"] = rec.get("origin") or e.get("origin", "")
            e["region"] = rec.get("region") or e.get("region", "")
            e["kind"] = rec.get("kind") or e.get("kind", "")
            # Herkunft und Abnahmedatum kommen aus der YAML und gewinnen
            # immer: sie sind gepflegte Angaben, keine Messwerte.
            meta = konfiguration.get(url) or {}
            if meta.get("herkunft"):
                e["herkunft"] = meta["herkunft"]
            if meta.get("abgenommen"):
                e["abgenommen"] = meta["abgenommen"]
            e.setdefault("abgenommen", e["erster_lauf"])

            status = rec.get("status")
            if status == "quarantaene":
                continue  # nicht abgerufen - zaehlt fuer nichts

            e["laeufe"] += 1
            e["letzter_lauf"] = datum
            if status == "ok" and rec.get("count"):
                e["ok"] += 1
                e["letzter_erfolg"] = datum
                e["serie_ohne_inhalt"] = 0
                if e.pop("quarantaene_seit", None):
                    e.pop("quarantaene_grund", None)
                    ereignisse["befreit"].append(url)
                    log.info("Quarantaene aufgehoben: %s liefert wieder "
                             "(%s Meldungen)", e.get("name") or url,
                             rec.get("count"))
                continue

            if status == "empty":
                e["leer"] += 1
            else:
                e["fehler"] += 1
                e["letzter_fehler"] = str(rec.get("error", ""))[:200]
            e["serie_ohne_inhalt"] = int(e.get("serie_ohne_inhalt", 0)) + 1

            if (self.quarantaene_nach
                    and e["serie_ohne_inhalt"] >= self.quarantaene_nach
                    and not e.get("quarantaene_seit")):
                e["quarantaene_seit"] = datum
                e["quarantaene_grund"] = (
                    f"{e['serie_ohne_inhalt']} Laeufe ohne Inhalt"
                    + (f" (zuletzt: {e['letzter_fehler'][:80]})"
                       if e.get("letzter_fehler") else ""))
                ereignisse["stillgelegt"].append(url)
                log.warning("Quelle stillgelegt: %s - %s",
                            e.get("name") or url, e["quarantaene_grund"])

        # Quellen, die gar nicht mehr in der Konfiguration stehen, bleiben im
        # Register stehen (Historie), werden aber markiert. Sie zu loeschen
        # wuerde die Bilanz einer spaeter wieder aufgenommenen Quelle
        # faelschlich bei null beginnen lassen.
        for url, e in self.quellen.items():
            if url not in gesehen:
                e["nicht_mehr_konfiguriert_seit"] = \
                    e.get("nicht_mehr_konfiguriert_seit") or datum
            else:
                e.pop("nicht_mehr_konfiguriert_seit", None)
        return ereignisse

    def speichern(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"version": VERSION, "lauf_nummer": self.lauf_nummer,
             "quarantaene_nach_laeufen": self.quarantaene_nach,
             "quarantaene_probe_alle": self.probe_alle,
             "quellen": self.quellen},
            ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    # --------------------------------------------------------------- Bericht
    def uebersicht(self) -> dict:
        """Kennzahlen fuers Laufprotokoll."""
        in_quarantaene = [e for e in self.quellen.values()
                          if e.get("quarantaene_seit")]
        return {
            "quellen_gesamt": len(self.quellen),
            "in_quarantaene": len(in_quarantaene),
            "quarantaene": sorted(
                ({"name": e.get("name", ""), "url": url,
                  "seit": e.get("quarantaene_seit"),
                  "grund": e.get("quarantaene_grund", "")}
                 for url, e in self.quellen.items()
                 if e.get("quarantaene_seit")),
                key=lambda q: q["seit"] or ""),
            "ohne_erfolg": sorted(
                ({"name": e.get("name", ""), "url": url,
                  "laeufe": e.get("laeufe", 0)}
                 for url, e in self.quellen.items()
                 if e.get("laeufe", 0) >= 3 and not e.get("letzter_erfolg")),
                key=lambda q: -q["laeufe"]),
        }
