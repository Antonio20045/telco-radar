"""Quellenregister: Herkunft, Abnahmedatum, letzter Erfolg - und Quarantaene.

Warum das ab dieser Groessenordnung gebraucht wird (AUFTRAG_SKALIERUNG_1000.md
Kriterien 12 und 13): bei 130 Quellen reicht ein deutscher Kommentar je
Eintrag in der YAML, und wenn eine Quelle stirbt, faellt das beim Lesen des
Laufprotokolls auf. Bei 1000 Quellen faellt gar nichts mehr auf. Ohne ein
maschinenlesbares Register weiss in sechs Monaten niemand mehr, welche der
1000 Quellen eigentlich noch lebt, und die Konfiguration verrottet still -
jede tote Quelle kostet dabei weiter Laufzeit.

Arbeitsteilung, bewusst getrennt:

  * Was ein Mensch bei der Abnahme WEISS, steht in der YAML bei der Quelle:
    `herkunft` (wie sie gefunden wurde) und `abgenommen` (wann sie den
    Abnahme-Check bestanden hat). Das ist redaktionelle Angabe, keine Messung.
  * Was der Betrieb MISST, steht hier: seit wann bekannt, wie viele Laeufe,
    wie viele Erfolge, wann zuletzt geliefert, wie lang die aktuelle Fehlserie.

Quarantaene
-----------
Eine Quelle, die in N aufeinanderfolgenden Laeufen nichts oder nur Fehler
liefert, wird stillgelegt und nicht mehr abgerufen. Das ist kein Loeschen: sie
bleibt in der Konfiguration, bleibt im Register sichtbar und bekommt regel-
maessig einen Bewaehrungsabruf. Genau das ist der Unterschied zwischen einer
Quarantaene und einer Falle - Telecompetitor liefert seit Wochen mal 403 und
mal 200, und eine Quelle, die nie wieder probiert wird, waere dauerhaft weg,
obwohl ihr Server nur zeitweise dicht war. Ein einziger Erfolg hebt die
Quarantaene sofort auf.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

# Nach so vielen Laeufen ohne eine einzige Meldung geht eine Quelle in
# Quarantaene. 6 sind bei zwei Laeufen die Woche drei Wochen - lang genug,
# dass ein Relaunch, eine Sommerpause oder eine zeitweise Sperre nicht sofort
# zur Stilllegung fuehrt, kurz genug, dass tote Quellen nicht ein halbes Jahr
# Laufzeit kosten.
QUARANTAENE_NACH_LAEUFEN = 6

# Wie oft eine stillgelegte Quelle einen Bewaehrungsabruf bekommt. 10 Laeufe
# sind rund fuenf Wochen: teuer genug, um sich zu lohnen, selten genug, um bei
# 1000 Quellen nicht ins Gewicht zu fallen.
PROBE_ALLE_LAEUFE = 10


@dataclass
class Quelleneintrag:
    url: str
    name: str = ""
    origin: str = ""
    kind: str = ""
    region: str = ""
    # aus der YAML uebernommen (redaktionell, nicht gemessen)
    herkunft: str = ""
    abgenommen: str = ""
    # gemessen
    erster_lauf: str = ""
    letzter_lauf: str = ""
    letzter_erfolg: str = ""
    laeufe: int = 0
    erfolge: int = 0
    meldungen_gesamt: int = 0
    neu_gesamt: int = 0
    fehlserie: int = 0
    quarantaene_seit: str = ""
    quarantaene_grund: str = ""
    # Laeufe seit dem letzten Bewaehrungsabruf (nur waehrend Quarantaene)
    seit_probe: int = 0

    @property
    def in_quarantaene(self) -> bool:
        return bool(self.quarantaene_seit)

    @property
    def erfolgsquote(self) -> float | None:
        return self.erfolge / self.laeufe if self.laeufe else None


class Quellenregister:
    """Der Bestand als JSON, geschluesselt nach Quellen-URL."""

    def __init__(self, path: Path):
        self.path = path
        self.eintraege: dict[str, Quelleneintrag] = {}
        if path.exists():
            try:
                roh = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log.warning("Quellenregister %s unlesbar - beginne neu", path)
                roh = {}
            for url, rec in (roh.get("quellen") or {}).items():
                bekannt = {f for f in Quelleneintrag.__dataclass_fields__}
                self.eintraege[url] = Quelleneintrag(
                    **{k: v for k, v in rec.items() if k in bekannt})

    def __len__(self) -> int:
        return len(self.eintraege)

    def eintrag(self, url: str) -> Quelleneintrag | None:
        return self.eintraege.get(url)

    # ------------------------------------------------------------ Abrufen

    def wird_abgerufen(self, url: str) -> bool:
        """False nur fuer stillgelegte Quellen ausserhalb ihres Bewaehrungslaufs."""
        e = self.eintraege.get(url)
        if e is None or not e.in_quarantaene:
            return True
        return e.seit_probe >= PROBE_ALLE_LAEUFE

    def stillgelegte(self) -> list[Quelleneintrag]:
        return [e for e in self.eintraege.values() if e.in_quarantaene]

    # ---------------------------------------------------- Lauf verbuchen

    def verbuche_lauf(self, ergebnisse: list[dict], heute: str | None = None,
                      quarantaene_nach: int = QUARANTAENE_NACH_LAEUFEN,
                      quellen_der_config: dict[str, dict] | None = None) -> dict:
        """Ein Laufergebnis einarbeiten. Liefert eine Zusammenfassung.

        `ergebnisse` sind die source_results der Sammelphase. Quellen, die in
        diesem Lauf gar nicht abgerufen wurden (Quarantaene ohne Bewaehrung),
        stehen nicht darin - sie bekommen trotzdem ihren Zaehler hochgesetzt,
        sonst kaeme ihr Bewaehrungsabruf nie.
        """
        heute = heute or date.today().isoformat()
        neu_stillgelegt: list[str] = []
        rehabilitiert: list[str] = []
        abgerufen: set[str] = set()

        for rec in ergebnisse:
            url = rec.get("url") or ""
            if not url:
                continue
            abgerufen.add(url)
            e = self.eintraege.get(url)
            if e is None:
                e = Quelleneintrag(url=url, erster_lauf=heute)
                self.eintraege[url] = e
            e.name = rec.get("name") or e.name
            e.origin = rec.get("origin") or e.origin
            e.kind = rec.get("kind") or e.kind
            e.region = rec.get("region") or e.region
            e.letzter_lauf = heute
            e.laeufe += 1
            e.meldungen_gesamt += int(rec.get("count") or 0)
            e.neu_gesamt += int(rec.get("new") or 0)

            geliefert = rec.get("status") == "ok" and int(rec.get("count") or 0) > 0
            if geliefert:
                e.erfolge += 1
                e.letzter_erfolg = heute
                e.fehlserie = 0
                e.seit_probe = 0
                if e.in_quarantaene:
                    # Ein einziger Erfolg genuegt. Die Quelle lebt.
                    e.quarantaene_seit = ""
                    e.quarantaene_grund = ""
                    rehabilitiert.append(url)
            else:
                e.fehlserie += 1
                e.seit_probe = 0
                if not e.in_quarantaene and e.fehlserie >= quarantaene_nach:
                    e.quarantaene_seit = heute
                    e.quarantaene_grund = (
                        f"{e.fehlserie} Laeufe ohne Meldung "
                        f"(zuletzt {rec.get('status')}"
                        + (f": {str(rec.get('error'))[:80]}" if rec.get("error") else "")
                        + ")")
                    neu_stillgelegt.append(url)

        # Nicht abgerufene (stillgelegte) Quellen: Zaehler zur naechsten Probe
        for url, e in self.eintraege.items():
            if url not in abgerufen and e.in_quarantaene:
                e.seit_probe += 1

        # Redaktionelle Angaben aus der Konfiguration nachziehen
        for url, angaben in (quellen_der_config or {}).items():
            e = self.eintraege.get(url)
            if e is not None:
                e.herkunft = angaben.get("herkunft") or e.herkunft
                e.abgenommen = angaben.get("abgenommen") or e.abgenommen

        if neu_stillgelegt:
            log.warning("Quarantaene: %d Quelle(n) stillgelegt - %s",
                        len(neu_stillgelegt), ", ".join(neu_stillgelegt[:5]))
        if rehabilitiert:
            log.info("Quarantaene aufgehoben fuer %d Quelle(n): %s",
                     len(rehabilitiert), ", ".join(rehabilitiert[:5]))

        return {
            "bekannt": len(self.eintraege),
            "neu_stillgelegt": neu_stillgelegt,
            "rehabilitiert": rehabilitiert,
            "stillgelegt_gesamt": len(self.stillgelegte()),
        }

    def speichern(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        daten = {
            "hinweis": ("Automatisch gepflegt von der Pipeline. herkunft und "
                        "abgenommen stammen aus der YAML, alles andere ist "
                        "gemessen. Siehe src/telco_radar/quellen_register.py."),
            "quellen": {url: asdict(e)
                        for url, e in sorted(self.eintraege.items())},
        }
        self.path.write_text(
            json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")


def quellen_der_config(cfg) -> dict[str, dict]:
    """Redaktionelle Angaben je Quellen-URL aus der geladenen Konfiguration."""
    aus: dict[str, dict] = {}
    for op in cfg.operators:
        for src in op.sources:
            aus[src.url] = {"herkunft": src.herkunft, "abgenommen": src.abgenommen}
    for src in list(cfg.news_sources) + list(cfg.tech_sources):
        aus[src.url] = {"herkunft": src.herkunft, "abgenommen": src.abgenommen}
    return aus
