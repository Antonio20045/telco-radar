"""Bilder fuer die Differenzierungs-Beispiele: beschaffen, ablegen, merken.

Antonio am 08.08.2026 zur Differenzierungs-Seite: *"Es ist total unuebersichtlich,
sich das anzugucken. Keine Bilder, es ist schwer zu verstehen."* Der Befund war
buchstaeblich: die Seite zeigte 77 Karten, davon **null** mit Bild, waehrend
jede Meldung auf der Titelseite eins hatte.

Warum die Bilder nicht einfach mitkamen, obwohl `report/bilder.py` seit dem
06.08.2026 fuer jede Meldung eins holt: die Differenzierungs-Bibliothek ist ein
**persistenter Bestand**, kein Wochenbericht. Ihre 71 Eintraege stammen aus zwei
Speichern (Sweep-DB und Presse-Kurator), leben ueber Monate weiter und stehen in
keiner Berichtsdatei. `report_bilder.raeume_auf()` loescht deshalb genau ihre
Bilder wieder - es behaelt nur, was die letzten vier Ausgaben referenzieren.
Ein eigener Ordner mit eigenem Aufraeumen ist die Konsequenz, nicht eine zweite
Bildpipeline: geholt, gemessen und abgelegt wird mit `bilder.lade_und_lege_ab()`,
also demselben Code, den auch die Promo-Uebersicht benutzt.

Zwei Bezugsquellen, in dieser Reihenfolge:

1. **Ein Bild, das der Wochenbericht schon geholt hat.** Der Presse-Zweig der
   Bibliothek stammt aus genau denselben Meldungen; bei gleicher normalisierter
   URL ist das Bild bereits da, gemessen und verkleinert. Das kostet kein Netz.
2. **`og:image` der Originalseite.** Fuer den Sweep-Zweig (Web-Recherche) die
   einzige Moeglichkeit. Gemessen an den 71 Eintraegen vom 08.08.2026 tragen
   rund 40 % der Seiten ein brauchbares `og:image`.

Was sich nicht belegen laesst, bekommt **kein** Bild, sondern eine Schriftkachel
in der Vorlage - dieselbe Regel wie auf der Promo-Uebersicht (CLAUDE.md §5,
Abnahmekriterium 8c). Ein Platzhalterkasten waere schlimmer als kein Bild.

Der Index (`data/state/diff_bilder.json`) merkt sich auch den **Fehlversuch**.
Ohne das fragte jeder Lauf dieselben 40 Seiten erneut ab, die schon dreimal kein
`og:image` hatten - bei zwei Laeufen die Woche und einem wachsenden Bestand ist
das der Unterschied zwischen einer Minute und fuenf.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from ..models import normalize_url
from . import bilder as report_bilder

log = logging.getLogger(__name__)

# Zielbreite. Die groesste Position der Seite ist die Radar-Karte: bei 1440 px
# Fensterbreite rund 380 px, auf einem Retina-Schirm also 760 echte Pixel.
# 800 deckt das ab, ohne dass der Bestand das Repo aufblaeht.
_BREIT = 800
# Wie viele Eintraege gleichzeitig. Der Bestand ist klein (Groessenordnung 100),
# jeder Eintrag kostet bis zu zwei Abrufe.
_GLEICHZEITIG = 8
_TIMEOUT = 10.0
# So lange gilt ein Fehlversuch. Danach darf eine Seite noch einmal gefragt
# werden - Redaktionssysteme bekommen `og:image` auch nachtraeglich.
_ERNEUT_NACH_TAGEN = 30


def bildordner(root: Path) -> Path:
    return Path(root) / "data" / "state" / "diff_images"


def indexdatei(root: Path) -> Path:
    return Path(root) / "data" / "state" / "diff_bilder.json"


def lade_index(root: Path) -> dict:
    """Der Bildindex: normalisierte URL -> {image, image_w, image_h} bzw.
    {geprueft: <datum>} fuer einen Fehlversuch."""
    pfad = indexdatei(root)
    if not pfad.exists():
        return {}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("diff_bilder.json unlesbar - beginne mit leerem Index")
        return {}
    eintraege = daten.get("bilder") if isinstance(daten, dict) else None
    return eintraege if isinstance(eintraege, dict) else {}


def schreibe_index(root: Path, index: dict, stand: str = "") -> None:
    pfad = indexdatei(root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps({"updated": stand or date.today().isoformat(),
                                "bilder": index}, ensure_ascii=False),
                    encoding="utf-8")


def bild_aus_berichten(reports_dir: Path) -> dict[str, dict]:
    """Was der Wochenbericht schon geholt hat: normalisierte URL -> Bildfelder.

    Gelesen werden ALLE Berichtsdateien, nicht nur die letzte - ein
    Differenzierungs-Beispiel kann Wochen alt sein. Ob die Datei noch existiert,
    prueft der Aufrufer (`nur_vorhandene`); `report_bilder.raeume_auf()` behaelt
    nur die letzten vier Ausgaben.
    """
    import re
    out: dict[str, dict] = {}
    for datei in sorted(Path(reports_dir).glob("*.json")):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datei.stem):
            continue
        try:
            bericht = json.loads(datei.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for region in (bericht.get("regions") or {}).values():
            for h in region.get("highlights") or []:
                if not h.get("image") or not h.get("url"):
                    continue
                out[normalize_url(h["url"])] = {
                    "image": h["image"],
                    "image_w": h.get("image_w") or 0,
                    "image_h": h.get("image_h") or 0,
                }
    return out


def _veraltet(eintrag: dict, heute: str) -> bool:
    """True, wenn ein Fehlversuch alt genug fuer einen zweiten Anlauf ist."""
    try:
        gefragt = datetime.fromisoformat(eintrag.get("geprueft") or "").date()
        return date.fromisoformat(heute) - gefragt > timedelta(days=_ERNEUT_NACH_TAGEN)
    except (TypeError, ValueError):
        return True


def beschaffe(bestand: list[dict], root: Path, reports_dir: Path,
              heute: str = "") -> dict:
    """Sorgt dafuer, dass moeglichst jeder Eintrag ein Bild hat.

    Aendert `bestand` NICHT - Ergebnis ist der Index, den `verteile()` beim
    Rendern anlegt. So bleibt die Netzarbeit in der Pipeline und das Rendern
    (auch in `scripts/pruefe_portal.py`) offline moeglich.
    """
    heute = heute or date.today().isoformat()
    ordner = bildordner(root)
    index = lade_index(root)
    aus_berichten = bild_aus_berichten(reports_dir)

    offen: list[str] = []
    z: Counter = Counter()
    for e in bestand:
        url = (e.get("url") or "").strip()
        if not url:
            continue
        schluessel = normalize_url(url)
        vorhanden = index.get(schluessel)
        if vorhanden and vorhanden.get("image"):
            z["bekannt"] += 1
            continue
        # Das Bild des Wochenberichts kostet kein Netz - immer zuerst.
        geerbt = aus_berichten.get(schluessel)
        if geerbt:
            index[schluessel] = dict(geerbt, quelle="bericht")
            z["aus_bericht"] += 1
            continue
        if vorhanden and not _veraltet(vorhanden, heute):
            z["kuerzlich_erfolglos"] += 1
            continue
        offen.append(url)

    if offen:
        with httpx.Client(headers={"User-Agent": report_bilder._UA},
                          timeout=_TIMEOUT, follow_redirects=True) as client:
            def arbeite(url: str) -> tuple[str, dict]:
                schluessel = normalize_url(url)
                try:
                    og = report_bilder.og_bild(url, client)
                    if og:
                        abgelegt = report_bilder.lade_und_lege_ab(
                            og, ordner, _BREIT, client)
                        if abgelegt:
                            name, breite, hoehe = abgelegt
                            return schluessel, {"image": name, "image_w": breite,
                                                "image_h": hoehe, "quelle": "og",
                                                "geprueft": heute}
                except Exception as exc:  # noqa: BLE001 - ein Bild kippt keinen Lauf
                    log.debug("Differenzierungs-Bild fehlgeschlagen (%s): %s",
                              url, exc)
                return schluessel, {"geprueft": heute}

            with ThreadPoolExecutor(max_workers=_GLEICHZEITIG) as pool:
                for schluessel, ergebnis in pool.map(arbeite, offen):
                    index[schluessel] = ergebnis
                    z["geladen" if ergebnis.get("image") else "kein_bild"] += 1

    # Aufraeumen: was zu keinem Eintrag des Bestands mehr gehoert, fliegt aus
    # Index UND Ordner. Ohne das waechst der Ordner mit jedem Beispiel, das die
    # Bibliothek jemals hatte.
    gebraucht = {normalize_url(e.get("url") or "") for e in bestand}
    index = {k: v for k, v in index.items() if k in gebraucht}
    behalten = {v["image"] for v in index.values() if v.get("image")}
    geloescht = 0
    if ordner.exists():
        for bild in ordner.iterdir():
            if bild.is_file() and bild.name not in behalten:
                try:
                    bild.unlink()
                    geloescht += 1
                except OSError:
                    pass
    z["geloescht"] = geloescht
    schreibe_index(root, index, heute)

    mit_bild = sum(1 for v in index.values() if v.get("image"))
    log.info("Differenzierungs-Bilder: %d von %d Beispielen haben eins (%s)",
             mit_bild, len(bestand),
             ", ".join(f"{k}={v}" for k, v in sorted(z.items())))
    return dict(z, mit_bild=mit_bild, bestand=len(bestand))


def verteile(bestand: list[dict], index: dict,
             vorhandene_bilder: set[str] | None = None) -> int:
    """Stempelt die Bildfelder aus dem Index in den Bestand. Gibt die Zahl der
    Eintraege mit Bild zurueck.

    `vorhandene_bilder` ist die Menge der Dateien, die wirklich ausgeliefert
    werden. Ein Verweis auf eine geloeschte Datei ist schlimmer als kein Bild -
    er zeigt einen leeren Kasten. Genau das passiert regelmaessig bei der ersten
    Bezugsquelle: das geerbte Bericht-Bild faellt weg, sobald seine Ausgabe aus
    dem Aufbewahrungsfenster von `report_bilder.raeume_auf()` rutscht.
    """
    getroffen = 0
    for e in bestand:
        eintrag = index.get(normalize_url(e.get("url") or "")) or {}
        name = eintrag.get("image")
        if not name:
            continue
        if vorhandene_bilder is not None and name not in vorhandene_bilder:
            continue
        e["image"] = name
        e["image_w"] = eintrag.get("image_w") or 0
        e["image_h"] = eintrag.get("image_h") or 0
        getroffen += 1
    return getroffen
