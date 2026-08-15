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


def berichtete_items(alle_highlights, by_url: dict) -> list:
    """Die Items hinter den berichteten Meldungen, in Berichtsreihenfolge.

    Der Zuschnitt der ganzen Stufe, und die Stelle, an der sie bis zum
    15.08.2026 ins Leere gelaufen ist: sie bekam `new_items`. Am 14.08.2026
    waren das 944 Meldungen, von denen 58 in den Bericht kamen - und alle
    vier Uebersetzungen des Laufs gehoerten zu Meldungen, die in KEINEM
    Bericht stehen. Der rote Link haengt an der Karte einer Meldung; ohne
    Karte gibt es keinen Ort, an dem er erscheinen koennte.

    Zurueck auf das ITEM und nicht auf das Highlight, weil nur das Item den
    Feed-Volltext und den Teaser in der ORIGINALSPRACHE traegt. Das
    Highlight traegt die deutsche Zusammenfassung des Analysten - auf ihr
    messen Vorauswahl und Spracherkennung "deutsch", und es waere nie wieder
    etwas uebersetzt worden.
    """
    raus, gesehen = [], set()
    for h in alle_highlights:
        item = by_url.get((h.get("url") or ""))
        if item is not None and item.id not in gesehen:
            gesehen.add(item.id)
            raus.append(item)
    return raus


def _kandidaten(items, store: UebersetzungsStore, deckel: int,
                bilanz: dict | None = None):
    """Was ueberhaupt in Frage kommt - vor jedem Abruf und jedem Modellaufruf.

    Die Vorauswahl laeuft auf dem, was ohne Netz da ist: Feed-Volltext oder
    Teaser. Ein Item, das hier schon als deutsch oder englisch erkannt
    wird, kostet keinen Abruf. Sicher ist die Erkennung erst auf dem
    Volltext - deshalb wird sie spaeter wiederholt.

    **Der Deckel schneidet erst NACH dem Scan, und die erkannt
    fremdsprachigen kommen zuerst.** Bis zum 15.08.2026 brach die Schleife
    ab, sobald der Deckel voll war - im Lauf vom 14.08. wurden damit 887 von
    944 Meldungen nie angesehen, und die 40 Plaetze gingen an die ersten
    Meldungen der Liste. Weil ein Item ohne Text (52 der 164 crawlbaren
    Quellen liefern keinen Teaser) unbesehen als Kandidat gilt, waren das
    ueberwiegend textlose englische Newsroom-Meldungen: 40 Abrufe, 35
    Absagen, 4 Uebersetzungen in 415 Sekunden. Wer sicher fremdsprachig ist,
    darf nicht hinter einem "vielleicht" warten.
    """
    sicher, unbestimmt = [], []
    for item in items:
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
            sicher.append(item)
            continue
        unbestimmt.append(item)

    raus = (sicher + unbestimmt)[:deckel]
    if bilanz is not None:
        bilanz["ueber_deckel"] = len(sicher) + len(unbestimmt) - len(raus)
        bilanz["sicher_fremd"] = len(sicher)
    return raus


def lauf(items, root: Path, settings: dict, modell: str,
         frist_sekunden: float, heute: date | None = None) -> dict:
    """Die Stufe. Gibt die Bilanz zurueck, wirft nichts."""
    t0 = time.monotonic()
    heute = heute or date.today()
    root = Path(root)
    # Erst materialisieren, dann zaehlen. `len()` auf einem Generator wirft
    # einen TypeError, und weil die Bilanz ganz oben gebaut wird, faellt die
    # Stufe dann VOR dem ersten Artikel - die Pipeline fangt das und
    # protokolliert "Uebersetzung uebersprungen: TypeError". Die Stufe
    # verschwindet also lautlos, und die Zusicherung "wirft nichts" waere von
    # der Aufrufseite her gebrochen.
    items = list(items)
    store = UebersetzungsStore(root / "data" / "state" / "uebersetzungen.jsonl")
    http_cfg = dict(settings.get("http", {}) or {})
    artikelabruf = bool(settings.get("uebersetzung_artikelabruf", True))
    deckel = int(settings.get("uebersetzung_max_je_lauf", 40))

    bilanz = {
        "geprueft": 0, "uebersetzt": 0, "uebersprungen": 0, "gescheitert": 0,
        "vorgefiltert": 0, "ueber_deckel": 0, "sicher_fremd": 0,
        "aus_feed": 0, "aus_artikel": 0, "bestand": len(store),
        "angeboten": len(items),
        "gruende": Counter(), "sprachen": Counter(), "sekunden": 0.0,
        "frist_erreicht": False,
    }

    kandidaten = _kandidaten(items, store, deckel, bilanz)
    # `sicher_fremd` zaehlt ALLE erkannt fremdsprachigen, auch die, die der
    # Deckel wegschneidet - ein "davon" waere hier falsch, weil die Zahl
    # groesser sein kann als die der Kandidaten. Bei 193 berichteten
    # Meldungen und Deckel 40 ist genau das die Zeile, an der sonst niemand
    # mehr ablesen kann, wie viele sichere Treffer wirklich bearbeitet werden.
    log.info("Uebersetzung: %d berichtete Meldungen -> %d Kandidaten "
             "(erkannt fremdsprachig insgesamt: %d, ueber dem Deckel %d: %d), "
             "Bestand %d",
             len(items), len(kandidaten), bilanz["sicher_fremd"], deckel,
             bilanz["ueber_deckel"], len(store))

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
        f"{bilanz['aus_artikel']} aus der Artikelseite) "
        f"aus {bilanz.get('angeboten', 0)} berichteten Meldungen, "
        f"{bilanz['uebersprungen']} uebersprungen, "
        f"{bilanz['vorgefiltert']} ohne Abruf vorgefiltert, "
        f"{bilanz['gescheitert']} gescheitert, "
        f"Bestand {bilanz['bestand']}, {bilanz['sekunden']}s"
    ]
    if bilanz.get("ueber_deckel"):
        # "nicht bearbeitet", nicht "nicht angesehen": angesehen wird seit dem
        # 15.08.2026 ALLES, der Deckel schneidet erst danach. Die alte
        # Formulierung war die Zahl, an der der Fehler zu erkennen war
        # (`ueber_deckel: 887` bei 40 bearbeiteten) - sie darf jetzt nicht
        # dasselbe Wort fuer etwas anderes benutzen.
        teile.append(f" [DECKEL: {bilanz['ueber_deckel']} nicht bearbeitet]")
    if bilanz.get("frist_erreicht"):
        teile.append(" [FRIST ERREICHT]")
    if sprachen:
        teile.append(f"; Sprachen: {sprachen}")
    if gruende:
        teile.append(f"; Gruende: {gruende}")
    return "".join(teile)
