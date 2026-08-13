"""Die Pipeline-Stufe: beschaffen, erkennen, uebersetzen, ablegen.

Sie steht VOR `render_site()`, weil der rote Link auf der gerenderten Seite
stehen muss. Genau diese Stelle hat am 10.08.2026 einen ganzen Lauf
gekostet: die Geraete-Nebenstufe startete mit zehn Minuten eigenem Budget
in einen Job, der noch fuenf hatte, und weil sie vor dem Rendern und
Committen steht, wurde von 45 erfolgreichen Minuten NICHTS veroeffentlicht.

Deshalb dieselben zwei Sicherungen wie dort:
  - Das Budget rechnet gegen die RESTZEIT DES JOBS, nicht gegen sich
    selbst, und zieht die Reserve fuers Veroeffentlichen ab.
  - Jeder einzelne Artikel wird gegen die Frist geprueft, nicht nur der
    Anfang der Stufe. Eine Stufe, die ihre Frist nur beim Start liest,
    laeuft mit dem letzten Artikel darueber hinaus.

Und eine dritte, die aus der Natur der Sache kommt: **der Bericht darf nie
an einer Uebersetzung scheitern.** Jeder Fehler eines einzelnen Artikels
wird gezaehlt und protokolliert, nie weitergeworfen.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import date
from pathlib import Path

from .sprache import ist_fremdsprachig, sprachname
from .store import UebersetzungsStore, Uebersetzung, text_hash
from .uebersetzer import uebersetze, UebersetzungFehlgeschlagen
from .volltext import hole_volltext

log = logging.getLogger(__name__)

# Unter so viel Restzeit faengt die Stufe gar nicht erst an. Ein einzelner
# Artikel braucht einen Abruf plus ein bis drei Modellaufrufe.
MINDESTBUDGET = 60.0


def budget(settings: dict, verstrichen: float) -> float | None:
    """Wie viel Zeit die Uebersetzungsstufe noch bekommt, oder None.

    Dieselbe Rechnung wie `pipeline.geraete_budget()` und aus demselben
    Grund: die Reserve gehoert dem Rendern, Committen und Deployen - dem
    Teil also, den ein Leser zu sehen bekommt.
    """
    if not settings.get("uebersetzung_enabled", True):
        return None
    rest = (float(settings.get("job_frist_sekunden", 3000)) - verstrichen
            - float(settings.get("veroeffentlichung_reserve_sekunden", 420)))
    if rest < MINDESTBUDGET:
        return None
    return min(float(settings.get("uebersetzung_frist_sekunden", 600)), rest)


def _kandidaten(items, store: UebersetzungsStore, deckel: int,
                bilanz: dict | None = None):
    """Was ueberhaupt in Frage kommt - vor jedem Abruf und jedem Modellaufruf.

    Die Vorauswahl laeuft auf dem, was ohne Netz da ist: Feed-Volltext oder
    Teaser. Ein Item, das hier schon als deutsch oder englisch erkannt
    wird, kostet keinen Abruf. Sicher ist die Erkennung erst auf dem
    Volltext - deshalb wird sie spaeter wiederholt.
    """
    raus = []
    for item in items:
        if len(raus) >= deckel:
            if bilanz is not None:
                bilanz["ueber_deckel"] += 1
            continue
        if item.id in store:
            if bilanz is not None:
                bilanz["vorgefiltert"] += 1
                bilanz["gruende"]["schon uebersetzt"] += 1
            continue
        probe = item.volltext or item.summary or ""
        if len(probe) >= 200:
            fremd, kuerzel, _ = ist_fremdsprachig(probe, item.title)
            if not fremd:
                # Vorgefiltert OHNE Abruf und ohne Modellaufruf - das ist der
                # Sinn dieser Stufe. Es muss trotzdem gezaehlt werden: ein
                # Protokoll, das "0 uebersetzt, 0 uebersprungen" meldet,
                # laesst offen, ob nichts fremdsprachig war oder ob die
                # Vorauswahl gar nicht erst gelaufen ist.
                if bilanz is not None:
                    bilanz["vorgefiltert"] += 1
                    bilanz["gruende"][
                        f"nicht fremdsprachig ({kuerzel or 'unbestimmt'})"] += 1
                continue
        raus.append(item)
    return raus


def lauf(items, root: Path, settings: dict, modell: str,
         frist_sekunden: float, heute: date | None = None) -> dict:
    """Die Stufe. Gibt die Bilanz zurueck, wirft nichts."""
    t0 = time.monotonic()
    heute = heute or date.today()
    root = Path(root)
    store = UebersetzungsStore(root / "data" / "state" / "uebersetzungen.jsonl")
    http_cfg = dict(settings.get("http", {}) or {})
    artikelabruf = bool(settings.get("uebersetzung_artikelabruf", True))
    deckel = int(settings.get("uebersetzung_max_je_lauf", 40))

    bilanz = {
        "geprueft": 0, "uebersetzt": 0, "uebersprungen": 0, "gescheitert": 0,
        "vorgefiltert": 0, "ueber_deckel": 0,
        "aus_feed": 0, "aus_artikel": 0, "bestand": len(store),
        "gruende": Counter(), "sprachen": Counter(), "sekunden": 0.0,
        "frist_erreicht": False,
    }

    kandidaten = _kandidaten(items, store, deckel, bilanz)
    log.info("Uebersetzung: %d Kandidaten von %d neuen Meldungen "
             "(Bestand: %d, Deckel: %d)",
             len(kandidaten), len(items), len(store), deckel)

    for item in kandidaten:
        if time.monotonic() - t0 > frist_sekunden:
            bilanz["frist_erreicht"] = True
            log.warning("Uebersetzung: Frist von %.0fs erreicht, %d "
                        "Kandidaten nicht mehr bearbeitet.",
                        frist_sekunden, len(kandidaten) - bilanz["geprueft"])
            break
        bilanz["geprueft"] += 1
        try:
            _einer(item, store, http_cfg, artikelabruf, modell, heute, bilanz)
        except Exception as exc:  # noqa: BLE001 - ein Artikel kostet nie den Lauf
            bilanz["gescheitert"] += 1
            bilanz["gruende"][f"Fehler: {type(exc).__name__}"] += 1
            log.warning("Uebersetzung fehlgeschlagen (%s): %s",
                        item.url[:70], exc)

    if bilanz["uebersetzt"]:
        store.speichern()
    bilanz["bestand"] = len(store)
    bilanz["sekunden"] = round(time.monotonic() - t0, 1)
    return bilanz


def _einer(item, store, http_cfg, artikelabruf, modell, heute, bilanz) -> None:
    ergebnis = hole_volltext(item, http_cfg, artikelabruf=artikelabruf)
    if not ergebnis.erfolg:
        bilanz["uebersprungen"] += 1
        bilanz["gruende"][ergebnis.grund or "kein Volltext"] += 1
        return

    # Die ENTSCHEIDENDE Erkennung - auf dem Fliesstext, nicht auf dem
    # Titel und nicht auf dem Teaser. Ein Feed kann eine englische
    # Zusammenfassung zu einem spanischen Artikel tragen, und andersherum
    # sortiert ein kurzer Teaser einen englischen Artikel als fremd ein.
    fremd, kuerzel, _ = ist_fremdsprachig(ergebnis.text, item.title)
    if not fremd:
        bilanz["uebersprungen"] += 1
        bilanz["gruende"][
            f"nicht fremdsprachig ({kuerzel or 'unbestimmt'})"] += 1
        return

    if store.hat_aktuelle(item.id, ergebnis.text):
        bilanz["uebersprungen"] += 1
        bilanz["gruende"]["schon uebersetzt"] += 1
        return

    titel_de, deutsche = uebersetze(ergebnis.text, kuerzel, modell,
                                    titel=item.title)
    store.add(Uebersetzung(
        item_id=item.id,
        quell_hash=text_hash(ergebnis.text),
        titel_de=titel_de or item.title,
        absaetze=deutsche,
        sprache=kuerzel,
        titel_original=item.title,
        url=item.url,
        quelle=item.source_name,
        datum=item.published.date().isoformat() if item.published else "",
        modell=modell,
        erstellt_am=heute.isoformat(),
        zeichen_original=len(ergebnis.text),
        herkunft=ergebnis.herkunft,
    ))
    item.sprache = kuerzel
    bilanz["uebersetzt"] += 1
    bilanz["sprachen"][kuerzel] += 1
    bilanz["aus_feed" if ergebnis.herkunft == "feed" else "aus_artikel"] += 1


def protokollzeile(bilanz: dict) -> str:
    """Eine Zeile fuers Laufprotokoll - uebersetzt, uebersprungen, gescheitert.

    Mit den GRUENDEN. Ein blosses "0 uebersetzt" laesst offen, ob nichts
    fremdsprachig war, ob die Abrufe scheiterten oder ob das Modell
    zusammengefasst hat - und genau diese Frage stellt sich nach dem Lauf.
    """
    gruende = ", ".join(f"{grund}: {n}" for grund, n
                        in bilanz["gruende"].most_common(6))
    sprachen = ", ".join(f"{sprachname(s)} {n}" for s, n
                         in bilanz["sprachen"].most_common())
    teile = [
        f"Uebersetzung: {bilanz['uebersetzt']} uebersetzt "
        f"({bilanz['aus_feed']} aus dem Feed, "
        f"{bilanz['aus_artikel']} aus der Artikelseite), "
        f"{bilanz['uebersprungen']} uebersprungen, "
        f"{bilanz['vorgefiltert']} ohne Abruf vorgefiltert, "
        f"{bilanz['gescheitert']} gescheitert, "
        f"Bestand {bilanz['bestand']}, {bilanz['sekunden']}s"
    ]
    if bilanz.get("ueber_deckel"):
        teile.append(f" [DECKEL: {bilanz['ueber_deckel']} nicht angesehen]")
    if bilanz.get("frist_erreicht"):
        teile.append(" [FRIST ERREICHT]")
    if sprachen:
        teile.append(f"; Sprachen: {sprachen}")
    if gruende:
        teile.append(f"; Gruende: {gruende}")
    return "".join(teile)
