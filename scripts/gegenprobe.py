"""Gegenprobe gespeicherter Bündelpreise im echten Browser (``gegenprobe.yml``).

AUFRUF
------
    PYTHONPATH=src python scripts/gegenprobe.py [--root .] [--datum JJJJ-MM-TT]
        [--anbieter o2|saturn-mediamarkt|... ...] [--plan] [--hoechstens N]
        [--buendel ID ...] [--bilder ORDNER] [--hochladen] [--ausgabe TEIL.jsonl]
        [--job-start EPOCHE] [--job-frist-sekunden 3000]

Reihenfolge und Seitenbesuche: ``gegenprobe_fenster`` (früheste Frist zuerst, ein
Besuch prüft jedes heute noch nicht geöffnete Bündel seiner Seite). Der Leser des
Anbieters (``gegenprobe_sicht.LESER``) liest den sichtbaren Text,
``gegenprobe.vergleiche`` vergleicht mit dem Bestand ``geraete_tco.json``.

``--anbieter`` schneidet den Lauf auf einen Job (``gegenprobe_fenster.job_von``: ein
Job je Host, Saturn/MediaMarkt ist einer); ohne ihn läuft alles in einem Job.
``--plan`` druckt nur die Jobs mit fälligen Bündeln als JSON-Liste (Matrix, ohne
Browser). Ergebnis: ohne ``--ausgabe`` ergänzt der Lauf
``data/state/gegenprobe/<datum>.jsonl`` und die Bilanz
``data/state/gegenprobe/bilanz/<datum>.json`` (``gegenprobe_bilanz.lege_ab``); mit
``--ausgabe`` schreibt er nur seine Teildatei und daneben ``<teil>.lauf.json``, die
``scripts/gegenprobe_ablegen.py`` später ablegt. Bilder gehen mit ``--hochladen`` ins
Release ``gegenprobe-<datum>`` (``beleg_ablage.Gh``), sonst bleiben sie in ``--bilder``.

Zeit (Harte Regel 8): ``--job-frist-sekunden`` ist die Restzeit des Jobs ab
``--job-start``; ein Seitenbesuch beginnt und ein Bündel darin folgt nur, wenn
``ZEIT_JE_BUENDEL_S`` davor noch Platz hat. Eine Preisänderung ohne Besuch steht als
„nicht gegengeprüft“ mit Grund in der Datei, jedes andere offene Bündel als
„überfällig“ in der Bilanz, nie als stilles Fehlen. Verdächtige Seiten (letzter
Versuch gescheitert) besucht ein Lauf je Anbieter höchstens
``gegenprobe_fenster.VERDAECHTIG_JE_NACHT``-mal, den Rest stellt er benannt zurück. Den
ganzen Anbieter stoppt nur eine Sperre oder eine Serie von Serverfehlern
(``gegenprobe_reihe.Schutzschalter``); der Ausfall steht mit Grund in der Bilanz.

Exit-Code 0: gelaufen (auch mit Abweichungen, das sind Befunde); 2: Eingabe unlesbar.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path

import yaml

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_fenster as gf
from telco_radar import tco_historie
from telco_radar.collect.geraete.gegenprobe_browser import (
    Gesperrt,
    Lesung,
)
from telco_radar.collect.geraete.gegenprobe_schritte import tor
from telco_radar.collect.geraete.gegenprobe_wege import lies_gruppe, seite_von
from telco_radar.gegenprobe_bilanz import angezeigte, lege_ab
from telco_radar.gegenprobe_bilanz import gesamt_von as gesamt
from telco_radar.gegenprobe_pruefung import Lesen as Lesen
from telco_radar.gegenprobe_pruefung import anderer_tarif as anderer_tarif
from telco_radar.gegenprobe_pruefung import ohne_lauf as _ohne_lauf
from telco_radar.gegenprobe_pruefung import pruefe as _pruefe
from telco_radar.gegenprobe_reihe import AUS, Schutzschalter, gruppiere

FEHLER_EINGABE = 2
TCO_DATEI = Path("data") / "state" / "geraete_tco.json"
HISTORIE = Path("data") / "state" / "geraete_tco_historie"
QUELLEN = Path("config") / "geraete_quellen.yaml"
JOB_MINUTEN = 60
"""``timeout-minutes`` des Einzeljobs ``gegenprobe`` (ein Wächter hält beide gleich)."""
PUFFER_S = 600
"""Einrichten des Läufers, Hochladen und Commit nach dem letzten Bündel."""
JOB_FRIST_S = JOB_MINUTEN * 60 - PUFFER_S
MATRIX_JOB_MINUTEN = 160
"""``timeout-minutes`` eines Anbieter-Jobs der Matrix (Rechnung im Workflow-Kopf)."""
MATRIX_JOB_FRIST_S = MATRIX_JOB_MINUTEN * 60 - PUFFER_S
HOECHSTE_FRIST_S = max(JOB_FRIST_S, MATRIX_JOB_FRIST_S)
"""Mehr Restzeit glaubt das Skript keinem Aufruf."""
ZEIT_JE_BUENDEL_S = 90
"""So lange darf ein Kundenweg höchstens dauern (Laden, Klicks, Bild)."""
MINDESTABSTAND_S = 5.0
"""Abstand zweier Seitenaufrufe beim selben Host, wenn robots.txt nicht mehr nennt."""
KENNUNG_ROBOTS = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"


def kennungen(root: Path) -> dict[str, str]:
    """User-Agent je Anbieter aus ``geraete_quellen.yaml`` (sonst der des Browsers)."""
    daten = yaml.safe_load((root / QUELLEN).read_text(encoding="utf-8")) or {}
    eintraege = daten.get("quellen") or daten.get("anbieter") or []
    return {
        str(e.get("name")): str(e["user_agent"])
        for e in eintraege
        if isinstance(e, dict) and e.get("user_agent")
    }


def lies_historie(
    ordner: Path, datum: str
) -> tuple[list[dict], list[dict], str | None]:
    """Zeilen des Tages ``datum``, je Bündel die letzte Messung davor
    (``gegenprobe.letzte_messungen``, wie die Seite „Preisänderungen“) und das Datum
    des vorigen Messtags (oder None)."""
    tage = tco_historie.tage(ordner.parent / f"{ordner.name}.jsonl")
    vorher = [(tag, saetze) for tag, saetze in tage if tag < datum]
    heute = next((saetze for tag, saetze in tage if tag == datum), [])
    zuletzt = gp.letzte_messungen(vorher)
    return heute, [dict(z) for z in zuletzt.values()], vorher[-1][0] if vorher else None


def pruefe(
    lesen: Lesen, satz: dict, anlass: str, datum: str, gemessen_um: str | None = None
) -> tuple[gp.Ergebnis, Lesung | None]:
    """``gegenprobe_pruefung.pruefe`` mit der Uhrzeit dieser Prüfung."""
    jetzt = datetime.now(UTC).isoformat(timespec="seconds")
    return _pruefe(lesen, satz, anlass, datum, gemessen_um, jetzt)


def main(argumente: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--datum")
    parser.add_argument("--anbieter", action="append", default=[], help="Job/Schlüssel")
    parser.add_argument("--plan", action="store_true", help="nur fällige Jobs (JSON)")
    parser.add_argument("--hoechstens", type=int)
    parser.add_argument(
        "--buendel", action="append", default=[], help="nur diese Bündel (lokal)"
    )
    parser.add_argument("--bilder", type=Path)
    parser.add_argument("--hochladen", action="store_true")
    parser.add_argument("--ausgabe", type=Path, help="Teildatei statt Tagesdatei")
    parser.add_argument("--aufnehmen", type=Path, help="Ordner für Test-Fixtures")
    parser.add_argument("--job-start", type=float)
    parser.add_argument("--job-frist-sekunden", type=float, default=JOB_FRIST_S)
    args = parser.parse_args(argumente)
    beginn = time.time()
    verstrichen = max(0.0, beginn - (args.job_start or beginn))
    frist = min(args.job_frist_sekunden, HOECHSTE_FRIST_S) - verstrichen
    frist -= ZEIT_JE_BUENDEL_S
    ende = time.monotonic() + max(0.0, frist)
    try:
        bestand = json.loads((args.root / TCO_DATEI).read_text(encoding="utf-8"))
        datum = (
            args.datum or bestand.get("updated") or datetime.now(UTC).date().isoformat()
        )
        date.fromisoformat(datum)
        saetze = {b["id"]: b for b in bestand["buendel"]}
        args.gemessen_um = bestand.get("gemessen_um")
        heute, vortag, vortag_datum = lies_historie(args.root / HISTORIE, datum)
        ua = kennungen(args.root)
        proben = gf.Gegenproben(gp.lies_alle(args.root / gp.ORDNER).values())
    except (OSError, ValueError, KeyError) as fehler:
        print(f"Gegenprobe: Eingabe unlesbar: {fehler}", file=sys.stderr)
        return FEHLER_EINGABE
    angezeigt = angezeigte(bestand["buendel"], datum)
    aenderungen = [bid for bid, _ in gp.auswahl(datum, heute, vortag, 0)]
    nur = gf.schluessel_der_jobs(args.anbieter)
    wahl = gf.kandidaten(datum, angezeigt, gesamt, proben, aenderungen, nur)
    if args.plan:
        print(json.dumps(gf.jobs(wahl)))
        return 0
    seite = partial(_seite, saetze)
    gruppen = gf.plane(wahl[: args.hoechstens], seite)
    if args.buendel:
        eigene = [(b, gp.ANLASS_STICHPROBE) for b in args.buendel if b in saetze]
        gruppen = gruppiere(eigene, seite)
    print(
        f"Gegenprobe {datum} (Vortag {vortag_datum}): {len(wahl)} offen, "
        f"{sum(k.faellig for k in wahl)} fällig, davon "
        f"{sum(k.anlass == gp.ANLASS_AENDERUNG for k in wahl)} Preisänderungen; "
        f"{len(gruppen)} Seitenbesuche geplant; ohne erste Anzeige (sofort fällig): "
        f"{sum(map(gf.ohne_erste_anzeige, angezeigt))}"
    )
    ergebnisse, bilder, laeufe = laufe(args, gruppen, saetze, datum, ua, ende)
    veroeffentliche(args, datum, ergebnisse, bilder)
    if args.ausgabe is not None:
        gp.schreibe_tag(args.ausgabe, ergebnisse)
        lauf_text = json.dumps(laeufe, ensure_ascii=False, indent=1)
        args.ausgabe.with_suffix(".lauf.json").write_text(lauf_text + "\n", "utf-8")
    else:
        lege_ab(args.root, datum, ergebnisse, laeufe, angezeigt)
    for e in ergebnisse:
        print(f"{e.status:20} {e.anbieter:35} {e.buendel_id} {e.grund or ''}")
    for lauf in laeufe:
        print(f"Lauf {lauf}")
    return 0


def _seite(saetze: dict, bid: str) -> str:
    return seite_von(gp.anbieter_aus_id(bid), saetze[bid])


def laufe(args, gruppen, saetze, datum, ua, ende):
    """Geht die Seitenbesuche durch (``Lauf.alle``), solange die Frist reicht. Vor
    jedem Laden gelten robots.txt und der Abstand (``tor``)."""
    from playwright.sync_api import sync_playwright

    vor_laden = tor(KENNUNG_ROBOTS, MINDESTABSTAND_S, lambda: datetime.now(UTC))
    print(f"Gegenprobe: {len(gruppen)} Seitenbesuche", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        lauf = Lauf(args, browser, saetze, datum, ua, ende, vor_laden)
        try:
            lauf.alle(gruppen)
        finally:
            browser.close()
    return lauf.zeilen(gruppen), lauf.bilder, lauf.laeufe()


class Lauf:
    """Was alle Seitenbesuche eines Laufs teilen, was sie gelesen haben, wie lange sie
    je Anbieter brauchten und welcher Anbieter ausfiel (``Schutzschalter``).

    Keine dataclass: Tests laden das Skript ohne Eintrag in ``sys.modules``."""

    def __init__(self, args, browser, saetze, datum, ua, ende, vor_laden) -> None:
        self.args = args
        self.browser = browser
        self.saetze = saetze
        self.datum = datum
        self.ua = ua
        self.ende = ende
        self.vor_laden = vor_laden
        self.ergebnisse: dict[str, gp.Ergebnis] = {}
        self.bilder: dict[str, bytes] = {}
        self.schutz = Schutzschalter()
        self.lauf_id = uuid.uuid4().hex[:12]
        """Kennung dieses Laufs: dieselbe Teildatei zweimal abgelegt zählt einmal."""
        self.verdaechtig: dict[str, int] = defaultdict(int)
        """Je Anbieter besuchte verdächtige Seiten in diesem Lauf."""
        self.zurueckgestellt: dict[str, int] = defaultdict(int)
        """Je Anbieter verdächtige Seiten über ``VERDAECHTIG_JE_NACHT`` hinaus."""
        self.uhr: Callable[[], float] = time.monotonic
        self.zeit: dict[str, list[float]] = defaultdict(lambda: [0, 0.0, 0])
        """Je Anbieter-Schlüssel [Besuche, Sekunden, Bündel]."""

    def alle(self, gruppen: list[list[tuple[str, str]]]) -> None:
        """Jeder Seitenbesuch, solange die Frist reicht; jeder geplante Anbieter
        bekommt einen Lauf-Eintrag, auch mit 0 Besuchen."""
        for gruppe in gruppen:
            self.zeit.setdefault(gp.anbieter_aus_id(gruppe[0][0]), [0, 0.0, 0])
        for gruppe in gruppen:
            if self.uhr() > self.ende:
                return
            self.besuche(gruppe)

    def besuche(self, gruppe: list[tuple[str, str]]) -> None:
        """Ein Seitenbesuch: prüft die Bündel der Gruppe, solange die Frist reicht.
        Eine verdächtige Seite (jedes Bündel ``ANLASS_WIEDERHOLUNG``) nur bis
        ``VERDAECHTIG_JE_NACHT`` je Anbieter, nach einem Ausfall keine mehr."""
        anlass = dict(gruppe)
        schluessel = gp.anbieter_aus_id(gruppe[0][0])
        if self.schutz.stufe(schluessel) == AUS:
            return
        if all(a == gp.ANLASS_WIEDERHOLUNG for _, a in gruppe):
            if self.verdaechtig[schluessel] >= gf.VERDAECHTIG_JE_NACHT:
                self.zurueckgestellt[schluessel] += 1
                return
            self.verdaechtig[schluessel] += 1
        aufnehmen = self.args.aufnehmen is not None
        beginn = self.uhr()
        lesungen = lies_gruppe(
            self.browser,
            schluessel,
            [self.saetze[bid] for bid, _ in gruppe],
            self.ua.get(self.saetze[gruppe[0][0]].get("anbieter") or ""),
            self.vor_laden,
            aufnehmen,
        )
        gelesen_ok, fehler, zahl = False, None, 0
        try:
            for satz, gelesen in lesungen:
                bid = satz["id"]
                zahl += 1
                if isinstance(gelesen, Exception):
                    fehler = fehler or gelesen
                else:
                    gelesen_ok = True
                ergebnis, lesung = pruefe(
                    partial(_gelesen, gelesen),
                    satz,
                    anlass[bid],
                    self.datum,
                    gp.messzeit(self.args.gemessen_um, satz),
                )
                if lesung is not None and lesung.bild is not None:
                    self.bilder[bid] = lesung.bild
                if aufnehmen and lesung is not None and lesung.html:
                    self.args.aufnehmen.mkdir(parents=True, exist_ok=True)
                    datei = self.args.aufnehmen / f"{schluessel}.html"
                    datei.write_text(lesung.html + "\n", encoding="utf-8")
                self.ergebnisse[bid] = ergebnis
                print(f"  {ergebnis.status:20} {bid}", flush=True)
                if self.uhr() > self.ende:
                    break
        finally:
            lesungen.close()
        self._buche(schluessel, beginn, zahl, (gelesen_ok, fehler))

    def _buche(self, schluessel, beginn, zahl, ausgang) -> None:
        gelesen_ok, fehler = ausgang
        zeit = self.zeit[schluessel]
        zeit[0] += 1
        zeit[1] += self.uhr() - beginn
        zeit[2] += zahl
        if gelesen_ok:
            self.schutz.erfolg(schluessel)
        elif fehler is not None:
            sperre = isinstance(fehler, Gesperrt)
            self.schutz.fehler(schluessel, str(fehler), sofort=sperre)

    def zeilen(self, gruppen: list[list[tuple[str, str]]]) -> list[gp.Ergebnis]:
        """Die geprüften Bündel und je nicht geöffnete Preisänderung eine Zeile
        „nicht gegengeprüft“ mit Grund (Ausfall des Anbieters oder Zeitbudget)."""
        out = list(self.ergebnisse.values())
        for gruppe in gruppen:
            for bid, anlass in gruppe:
                if bid in self.ergebnisse or anlass != gp.ANLASS_AENDERUNG:
                    continue
                schluessel = gp.anbieter_aus_id(bid)
                ausfall = self.schutz.grund(schluessel)
                grund = gp.GRUND_ZEITBUDGET if ausfall is None else ausfall
                out.append(_ohne_lauf(self.saetze[bid], anlass, self.datum, grund))
        return out

    def laeufe(self) -> list[dict]:
        """Je Anbieter dieses Laufs Besuche, Sekunden, Bündel und Ausfall."""
        return [
            {
                "datum": self.datum,
                "anbieter": s,
                "besuche": int(self.zeit[s][0]),
                "sekunden": round(self.zeit[s][1], 1),
                "buendel": int(self.zeit[s][2]),
                "ausfall": _verbunden(self.schutz.ausfaelle(s)),
                "zurueckgestellt": self.zurueckgestellt[s],
                "lauf_id": self.lauf_id,
            }
            for s in sorted(set(self.zeit) | set(self.schutz.abgeschaltet()))
        ]


def _verbunden(gruende: list[str]) -> str | None:
    """Die Ausfälle eines Anbieters als ein Text; None, wenn keiner war."""
    return "; ".join(gruende) if gruende else None


def _gelesen(gelesen: Lesung | Exception, _schluessel: str, _satz: dict) -> Lesung:
    """Für ``pruefe``: die Lesung des Seitenbesuchs oder sein Fehler."""
    if isinstance(gelesen, Exception):
        raise gelesen
    return gelesen


def veroeffentliche(args, datum, ergebnisse, bilder) -> None:
    """Legt die Bilder ab und lädt sie mit ``--hochladen`` ins Tages-Release."""
    ordner = args.bilder or Path(tempfile.gettempdir()) / "gegenprobe-bilder" / datum
    ordner.mkdir(parents=True, exist_ok=True)
    dateien: dict[str, Path] = {}
    for e in ergebnisse:
        bild = bilder.get(e.buendel_id)
        if bild is None:
            continue
        endung = "webp" if bild[:4] == b"RIFF" else "png"
        datei = ordner / f"{gp.kennung(e.buendel_id, datum)}.{endung}"
        datei.write_bytes(bild)
        dateien[e.buendel_id] = datei
    if not args.hochladen:
        for e in ergebnisse:
            if e.buendel_id in dateien:
                e.bild_fehlt = f"nicht veröffentlicht (lokal: {dateien[e.buendel_id]})"
        return
    from telco_radar.beleg_ablage import Gh, GhFehler

    gh = Gh()
    tag = gp.release_tag(datum)
    try:
        gh.release_anlegen(tag, f"Gegenprobe {datum}")
    except GhFehler as fehler:
        print(f"Gegenprobe: Release {tag} nicht angelegt (gibt es ihn?): {fehler}")
    try:
        gh.hochladen(tag, list(dateien.values()))
    except GhFehler as fehler:
        print(f"Gegenprobe: Bilder nicht hochgeladen: {fehler}", file=sys.stderr)
        for e in ergebnisse:
            if e.buendel_id in dateien:
                e.bild_fehlt = "Bild nicht veröffentlicht (Release gestört)"
        return
    for e in ergebnisse:
        if e.buendel_id in dateien:
            e.bild = gp.bild_url(datum, dateien[e.buendel_id].name)


if __name__ == "__main__":
    sys.exit(main())
