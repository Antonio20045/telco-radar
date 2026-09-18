# -*- coding: utf-8 -*-
"""E4 Auto-Erkennung: neue Katalog-Eintraege aus strukturierten Live-Namen.

Antonio, 16.09.2026 (AUFTRAG_GERAETE_EINE_SEITE_V2.md, Paragraf 9a): „wenn
neue Modelle oder neue Tarife veroeffentlicht werden, dass man nicht hier
das wieder im Quellcode rumbasteln muss. Das muss automatisch gehen."

Beleg ist der Telekom-Tageslauf vom 15.09.2026: die Kategorieseite lieferte
die Geraete „iPhone 18 Pro" (Feld `name`, variantSlug polar-256-gb, also
Titel „iPhone 18 Pro 256 GB polar") und „iPhone 18 Pro Max" strukturiert -
beide wurden als „Titel ohne Katalogtreffer" protokolliert und VERWORFEN.
Die Launch-Preishistorie begann nicht mit Tag 1, weil Tag 1 nie gespeichert
wurde.

DIE EINE REGEL: Ausloeser ist allein der STRUKTURIERTE Name eines
Live-Katalogs - Telekom `name`, o2 `description`, Vodafone `modelName`,
gesetzt als `strukturierter_name` am Rohsatz (nie der zusammengesetzte
Titel, nie ein HTML-Titel). Titel-Heuristik fuer Handelsseiten (Option a)
bleibt verworfen: die ID eines Geraets kommt aus dem KATALOG, und aus
Titel-Schaetzungen entstuenden jede Woche neue Geraete - die Saegezahn-
Kurve, gegen die die ganze ID-Regel gebaut ist.

HERSTELLER-SCHAELLUNG (aus dem Katalog gerechnet, nicht gepflegt):
  1. Praefix: beginnt der Name mit einem Katalog-Hersteller, faellt dieser
     weg („Apple iPhone 18 Air" -> Apple, „iPhone 18 Air" - konsistent zur
     Schreibweise der Hand-Eintraege).
  2. Serien-Anker: sonst muss die Baureihe des Namens (`serie_aus_modell`)
     im Katalog zu GENAU EINEM Hersteller gehoeren („iPhone 18 Pro" ohne
     Praefix -> Serie „iPhone" -> Apple). Kein Praefex und kein Anker?
     Dann wird NICHTS angelegt - ein unbekannter Hersteller ist geraten.

generation NUR bei eindeutiger, im Katalog bekannter Serie (die Zahl
INNERHALB der Baureihe, CLAUDE.md) - sonst None. marktstart und vorgaenger
BLEIBEN leer: ein geratenes Datum waere schlimmer als ein fehlendes (ein
leeres marktstart schaltet die Nachfolger-Analyse ab - ehrlich).

KOLLISIONSWAECHTER (Hand schlaegt Auto, zweifach): die gleiche device_id
bzw. eine nicht unterscheidbare Schreibweise verweigert `Katalog.ergaenze`
- und `kollidiert_fuzzy` prueft zusaetzlich die MODELLZUSATZ-Falle in der
Stamm-Richtung (der Kandidat ist der Stamm eines Hand-Eintrags MIT
ZUSATZ). Jeder Verwurf steht im Protokoll.

PERSISTENZ: Auto-Eintraege leben im STATE
(data/state/geraete_katalog_auto.json), nicht in der Config; beim Laden
schlaegt der Hand-Eintrag (gleiche device_id). Unbekannte Titel und Farben
zaehlt data/state/geraete_unbekannt.jsonl - angelegt und erweitert vom
Lauf, nie von Hand gepflegt.
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

from ...geraete_model import (
    Geraet, Katalog, device_id, ist_modellzusatz, ist_zubehoer, normalisiere,
    serie_aus_modell, wortmarken,
)

log = logging.getLogger(__name__)

# Ein Name braucht mindestens zwei Wortmarken, um ein GERAET zu benennen -
# eine einzige Marke ist zu duenn als Identitaet fuer eine device_id.
_MINDEST_MARKEN = 2

# Speichersegmente im NAMEN (mit Einheit - "iPhone 18 Pro 256 GB" ist auch
# als Namensfeld denkbar, Vodafones `label` traegt aehnliches). Ohne Einheit
# wird NICHT geschaelt: "Galaxy A57" ist der NAME, nicht 57 GB.
_SPEICHER_SEGMENT = re.compile(r"\b\d{1,4}\s*(?:gb|tb)\b", re.IGNORECASE)

# Funkfaehigkeits-Anhaengsel im NAMEN sind keine IDENTITAET (E4-P1): o2
# schreibt den Zusatz in das description-Feld („Xiaomi Redmi Note 17 Pro
# Max 5G", tests/fixtures/geraete/o2_katalog.json), Telekom `name` und
# Vodafone `modelName` nennen dasselbe Geraet ohne. Sie wie das
# Speichersegment zu schaelen haelt die device_id ueber Anbieter und
# Naechte stabil - ohne diese Schaellung entstand der zweite Eintrag STILL
# (ohne Meldung an die Arbeitsliste), sobald o2 zuerst angelegt hatte (der
# Telekom-202-Ausfall in Actions ist dokumentierte Realitaet) und ein
# spaeterer Anbieter das Geraet ohne Zusatz nannte. Zwei device_ids fuer
# ein Geraet sind die Saegezahn-Klasse, gegen die die ganze ID-Regel
# gebaut ist.
_FUNK_WORTE = frozenset("5g 4g lte".split())
_FUNK_ZUSATZ = re.compile(r"\b(?:" + "|".join(sorted(_FUNK_WORTE)) + r")\b",
                          re.IGNORECASE)


def ist_funkzusatz(wort: str) -> bool:
    """Wortmarken-Zugang zu _FUNK_WORTE fuer den Kollisionswaechter -
    dieselbe Liste wie die Schaellung, aus derselben Quelle (eine zweite
    Kopie derselben Woerter wuerde driften, siehe ist_modellzusatz)."""
    return (wort or "").strip().lower() in _FUNK_WORTE


_ZAHL_AM_WORTENDE = re.compile(r"(\d+)\s*$")

_STATE_DATEI = "geraete_katalog_auto.json"
_UNBEKANNT_DATEI = "geraete_unbekannt.jsonl"


def _serien_anker(katalog: Katalog) -> dict:
    """Baureihe (normalisiert) -> Hersteller (original), nur wo EINDEUTIG.

    Aus dem Katalog gerechnet: jedes Modell benennt seine Baureihe, und
    eine Baureihe, die im Katalog zu zwei Herstellern gehoert, ist kein
    Anker - dann wird kein Hersteller geraten.
    """
    kandidaten: dict[str, set] = {}
    originals: dict[str, str] = {}
    for geraet in katalog.geraete:
        schluessel = normalisiere(serie_aus_modell(geraet.modell))
        if not schluessel:
            continue
        hersteller = normalisiere(geraet.hersteller)
        kandidaten.setdefault(schluessel, set()).add(hersteller)
        originals.setdefault(hersteller, geraet.hersteller)
    return {s: originals[next(iter(h))] for s, h in kandidaten.items()
            if len(h) == 1}


# FESTE FAMILIEN-ANKER (P5/E3, gemessen 17.09.2026): Vodafone nennt seine
# iPads im strukturierten Namen OHNE Hersteller-Praefix - `modelName` ist
# „iPad Pro 11 (2025)", „iPad (2025)", „iPad Pro 11 2024" (data/state/
# geraete_unbekannt.jsonl vom 17.09., quelle vodafone_buendel/vodafone_api).
# Die Serie „iPad" stand in KEINEM Katalog-Eintrag (Hand wie Auto - der
# Hand-Katalog verfolgte bewusst keine Tablets), also griff der Serien-Anker
# nie: die Anker-Luecke aus auto-doku.md. Diese Familien sind keine Raterei,
# sondern Markennamen EINES Herstellers: iPad, Watch und AirPods sind
# Apple-Serien. Watch- und AirPods-Nennungen MIT Praefix liefen ohnehin ueber
# den Praefix-Pfad (17.09.: Watch S12, AirPods 5, auto-angelegt); der
# Familien-Anker traegt nur den Namen OHNE Praefix nach - kuenftige iPads
# („iPad Air", „iPad mini", „iPad Pro 14") werden damit automatisch
# Katalog-Eintraege, ohne dass jemand den Katalog anfasst.
_FESTE_FAMILIEN = {
    "ipad": "Apple",
    "watch": "Apple",
    "airpods": "Apple",
}


def _anker_treffer(serie: Optional[str], anker: dict,
                   katalog: Katalog) -> Optional[str]:
    """Hersteller fuer eine normalisierte Baureihe: der Katalog-Anker
    zuerst, der feste Familien-Anker nur als Lueckenfueller.

    Kennt der Katalog die Reihe - EINDEUTIG oder WIDERSPRUECHLICH -,
    entscheidet er allein: der eindeutige Fall steht im Anker, der
    widerspruechliche bleibt absichtlich ohne Hersteller (nichts geraten),
    und genau dann darf der Familien-Anker nicht eingreifen - sonst ebnete
    er eine gepflegte Zuordnung ein (Hand schlaegt Auto, in beide
    Richtungen). Er greift nur fuer eine Reihe, die in KEINEM Katalog-
    Eintrag vorkommt, und prueft das gegen den Katalog selbst, nicht gegen
    das Anker-Diktat darueber.
    """
    if not serie:
        return None
    treffer = anker.get(serie)
    if treffer is not None:
        return treffer
    if any(normalisiere(serie_aus_modell(g.modell)) == serie
           for g in katalog.geraete):
        return None          # der Katalog kennt die Reihe - er entscheidet
    return _FESTE_FAMILIEN.get(serie.split("-")[0])


def schale(name: str, katalog: Katalog) -> Optional[tuple]:
    """Strukturierter Name -> (Hersteller, Modell) oder None.

    Der Modellname wird aus dem ORIGINAL-String geschaelt (nicht aus den
    normalisierten Marken): er steht spaeter im Katalog und auf der Seite,
    und dort schreibt sich das iPhone gross. Speichersegment und Funk-
    anhaengsel fallen dabei weg - keins von beiden ist Identitaet (o2 nennt
    „Redmi Note 18 Pro Max 5G", die Telekom „Redmi Note 18 Pro Max").
    """
    name = (name or "").strip()
    marken = wortmarken(name)
    if len(marken) < _MINDEST_MARKEN or ist_zubehoer(marken):
        return None

    hersteller: Optional[str] = None
    rest = name
    for kandidat in katalog.hersteller:
        if name.lower().startswith(kandidat.lower() + " "):
            hersteller, rest = kandidat, name[len(kandidat) + 1:].strip()
            break
    if hersteller is None:
        anker = _serien_anker(katalog)
        serie = normalisiere(serie_aus_modell(name))
        treffer = _anker_treffer(serie, anker, katalog)
        if treffer is None:
            return None                    # kein Hersteller, nichts geraten
        hersteller, rest = treffer, name

    rest = _SPEICHER_SEGMENT.sub(" ", rest)
    rest = _FUNK_ZUSATZ.sub(" ", rest)
    rest = re.sub(r"\s{2,}", " ", rest).strip()
    if len(wortmarken(rest)) < _MINDEST_MARKEN:
        return None
    return hersteller, rest


def _generation(modell: str, hersteller: str, katalog: Katalog) -> Optional[int]:
    """Die Nummer INNERHALB der Baureihe - nur wenn die Serie dem Katalog
    bekannt ist (dann ist die Zahl vergleichbar, CLAUDE.md-Regel zu
    `generation`). Eine unbekannte Serie bekommt None, nie eine Rate-Zahl."""
    anker = _serien_anker(katalog)
    serie = normalisiere(serie_aus_modell(modell))
    if not serie or _anker_treffer(serie, anker, katalog) != hersteller:
        return None
    for wort in re.split(r"[\s\-]+", modell):
        treffer = _ZAHL_AM_WORTENDE.search(wort)
        if treffer:
            return int(treffer.group(1))
    return None


def kollidiert_fuzzy(modell: str, katalog: Katalog) -> Optional[str]:
    """Die MODELLZUSATZ-Falle (CLAUDE.md: „Pixel 10 Pro Fold" gegen
    „Pixel 10 Pro") - geprueft fuer die AUTO-ANLAGE.

    Der Kandidat ist der STAMM eines HAND-gepflegten Eintrags (seine
    Wortmarken sind der Anfang der Wortmarken einer bestehenden
    Schreibweise, und das naechste Wort dort ist ein Modellzusatz oder ein
    Funk-Anhaengsel)? Dann wird nichts angelegt: ein Live-Katalog, der nur
    den Stamm nennt, verkuerzt den Namen moeglicherweise nur, und die
    Anlage waere ein Phantom neben dem echten Geraet. Ob es den Stamm
    wirklich als eigenes Geraet gibt, entscheidet die Hand-Pflege (der
    Verwurf steht im Protokoll und der Titel in der Arbeitsliste).

    Das Funk-Anhaengsel gehoert dazu (E4-P1): ist der Hand-Eintrag MIT
    „5G" gepflegt („Galaxy A13 5G" ist real ein eigenes Geraet), legt eine
    Nennung ohne Zusatz kein Duplikat daneben an - dieselbe Stamm-Richtung,
    und die Schaellung allein haette genau diesen Konflikt gegen den
    HAND-Katalog offen gelassen.

    NUR die Stamm-Richtung und NUR gegen Hand-Eintraege:
      * Die Gegenrichtung (Kandidat traegt den Zusatz, „iPhone 18 Pro Max"
        neben gepflegtem „iPhone 18 Pro") ist der Belegfall des Auftrags -
        ein Live-Katalog erweitert Namen nicht, er kuerzt allenfalls.
      * Gegen AUTO-Eintraege wird nicht geprueft: „Pro" und „Pro Max"
        erscheinen im selben Lauf, die Reihenfolge der Nutzlast ist nicht
        garantiert, und hinge der Beleg an ihr, sperrte der Max zuerst
        genannt den Stamm.
    Gibt den Namen des kollidierenden Hand-Eintrags zurueck, sonst None.
    """
    marken = wortmarken(modell)
    if not marken:
        return None
    n = len(marken)
    for bestehend in katalog.geraete:
        if bestehend.auto:
            continue                 # nur der Hand-Katalog schlaegt
        for schreibweise in bestehend.schreibweisen:
            andere = wortmarken(schreibweise)
            if len(andere) > n and andere[:n] == marken \
                    and (ist_modellzusatz(andere[n])
                         or ist_funkzusatz(andere[n])):
                return f"{bestehend.hersteller} {bestehend.modell}"
    return None


def lege_an(name: str, katalog: Katalog, heute: str,
            speicher_gb=None) -> Optional[Geraet]:
    """Aus einem strukturierten Namen einen Katalog-Eintrag anlegen.

    Gibt das (neue oder bereits existierende) Geraet zurueck oder None,
    wenn der Name nicht schaelbar ist. Existiert die device_id schon,
    wird NICHTS angelegt (der Eintrag schlaegt sich selbst nicht) - nur
    die Speicherstufe waechst in einen bestehenden AUTO-Eintrag nach
    (`Katalog.ergaenze_speicher`; Hand-Eintraege bleiben unberuehrt).
    """
    geschaelt = schale(name, katalog)
    if geschaelt is None:
        return None
    hersteller, modell = geschaelt
    gid = device_id(hersteller, modell)

    vorhanden = katalog.nach_id(gid)
    if vorhanden is not None:
        katalog.ergaenze_speicher(gid, speicher_gb)
        return vorhanden

    konflikt = kollidiert_fuzzy(modell, katalog)
    if konflikt is not None:
        log.warning("Auto-Erkennung: %r ist der Stamm des Hand-Eintrags "
                    "%r (Modellzusatz-Falle, CLAUDE.md) - nicht angelegt; "
                    "ob es den Stamm als eigenes Geraet gibt, entscheidet "
                    "die Katalog-Pflege", name, konflikt)
        return None

    stufen: list = []
    try:
        if speicher_gb is not None:
            stufen = [int(speicher_gb)]
    except (TypeError, ValueError):
        stufen = []
    geraet = Geraet(
        hersteller=hersteller, modell=modell,
        generation=_generation(modell, hersteller, katalog),
        speicher=stufen, auto=heute)
    if not katalog.ergaenze(geraet):
        log.info("Auto-Erkennung: %r kollidiert mit einer bestehenden "
                 "Schreibweise - nicht angelegt", name)
        return None
    log.info("Auto-Erkennung: %s %s aus strukturiertem Namen angelegt "
             "(auto:%s, %d Stufe(n) Speicher)", hersteller, modell, heute,
             len(stufen))
    return geraet


# --------------------------------------------------------------------------
# Persistenz der Auto-Eintraege (STATE, nicht Config)
# --------------------------------------------------------------------------

def lade_auto_zusaetze(root: Path, katalog: Katalog) -> int:
    """Gespeicherte Auto-Eintraege in den Katalog mergen.

    Hand schlaegt Auto, zweifach: existiert die device_id schon (Config),
    wird die State-Zeile verworfen - der Mensch hat den Eintrag
    uebernommen. Und der Kollisionswaechter greift auch fuer die
    MODELLZUSATZ-Falle: ist der State-Eintrag inzwischen der Stamm eines
    gepflegten Hand-Eintrags MIT ZUSATZ, wird er ebenfalls verworfen.
    Jeder Verwurf steht im Protokoll - ein stiller Verwurf waere beim
    Nachvollzug des Auto-Bestands unsichtbar. Gibt die Zahl der
    uebernommenen Eintraege zurueck.
    """
    pfad = Path(root) / "data" / "state" / _STATE_DATEI
    if not pfad.exists():
        return 0
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("Auto-Katalog %s unlesbar (%s) - ignoriert", pfad, exc)
        return 0
    uebernommen = 0
    for eintrag in (roh.get("geraete") or []):
        if not isinstance(eintrag, dict):
            continue
        hersteller = str(eintrag.get("hersteller") or "").strip()
        modell = str(eintrag.get("modell") or "").strip()
        auto = str(eintrag.get("auto") or "").strip()
        if not hersteller or not modell or not auto:
            continue
        generation = eintrag.get("generation")
        geraet = Geraet(
            hersteller=hersteller, modell=modell, auto=auto,
            generation=int(generation)
            if str(generation or "").strip().isdigit() else None,
            speicher=[int(s) for s in (eintrag.get("speicher") or [])
                      if str(s).strip().isdigit()])
        konflikt = kollidiert_fuzzy(modell, katalog)
        if konflikt is not None:
            log.info("Auto-Katalog: %s %s (auto:%s) verworfen - Stamm des "
                     "Hand-Eintrags %s (Modellzusatz-Falle), der "
                     "Hand-Eintrag schlaegt",
                     hersteller, modell, auto, konflikt)
            continue
        if not katalog.ergaenze(geraet):
            log.info("Auto-Katalog: %s %s (auto:%s) verworfen - der "
                     "Hand-Eintrag schlaegt (gleiche device_id oder "
                     "nicht unterscheidbare Schreibweise)",
                     hersteller, modell, auto)
            continue
        uebernommen += 1
    return uebernommen


def speichere_auto_zusaetze(root: Path, katalog: Katalog) -> int:
    """Alle Auto-Eintraege des Katalogs in den State schreiben.

    Ersetzt die Datei komplett (der Katalog IST der aktuelle Stand) und
    legt das Verzeichnis bei Bedarf an. Gibt die Zahl der Eintraege
    zurueck.
    """
    eintraege = [g for g in katalog.geraete if g.auto]
    pfad = Path(root) / "data" / "state" / _STATE_DATEI
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps({
        "geraete": [{"hersteller": g.hersteller, "modell": g.modell,
                     "generation": g.generation, "speicher": g.speicher,
                     "auto": g.auto}
                    for g in eintraege]}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return len(eintraege)


# --------------------------------------------------------------------------
# Persistenz unbekannter Titel und Farben
# --------------------------------------------------------------------------

# Tarif-Rauschen in der Arbeitsliste (P5/E3, gemessen 17.09.2026): ALDI TALK
# liefert je Lauf drei Tarifpakete als „Geraet" in den strukturierten Daten
# mit - „Tarif S", „Tarif M", „Tarif L" (quelle microdata). In der Liste vom
# 17.09. stehen sie als 3 Zeilen mit Haeufigkeitssumme 87 von 284 und machen
# den Fruehindikator aus FM 1 taub: wer die Liste nach Anker-Luecken liest
# (iPad-Titel, „HMD Fusion X1"), sortiert erst an 29-mal demselben Tarifnamen
# vorbei. Ein Titel ist Rauschen, wenn er das Wort „Tarif" traegt UND keine
# Ziffer - jedes Geraet benennt sich ueber Modellnummer, Speicher, Jahr oder
# Groesse; „Tarif S" hat nichts davon. Der einzige ziffernlose GERAETEtitel
# des Bestands („Oakley Meta - HSTN Prizm Polarized (AI Glasses)") traegt das
# Wort „Tarif" nicht - die UND-Verknuepfung haelt ihn raus. Zusammengesetzte
# Tarifnamen („Tarifpaket M") bleiben bewusst stehen: das Wort grenzt nicht,
# und lieber bleibt Rauschen stehen, als dass ein Geraet verschwindet.
_TARIF_WORT = re.compile(r"\btarif\b", re.IGNORECASE)


def ist_tarif_titel(titel: str) -> bool:
    """Benennt dieser Titel ein TARIFPAKET statt eines Geraets?

    Die Regel ist eine UND-Verknuepfung aus dem gemessenen Muster (nur
    „Tarif S/M/L", alles andere waere geraten): Wort „Tarif" vorhanden,
    keine Ziffer im Titel. Gilt nur fuer Titel - eine Farbe namens „Tarif"
    gibt es nicht, und die Regel schaut gar nicht erst hin.
    """
    t = (titel or "").strip()
    if not t:
        return False
    return bool(_TARIF_WORT.search(t)) and not re.search(r"\d", t)


def _ist_tarif_eintrag(eintrag: dict) -> bool:
    """Ein `unbekannt`-Satz ist Tarif-Rauschen, wenn er ein TITEL-Satz mit
    Tarifnamen ist - die gemeinsame Formel fuer neue Eintraege und fuer
    Bestandszeilen (eine zweite Kopie derselben Bedingung wuerde driften)."""
    return eintrag.get("art") == "titel" \
        and ist_tarif_titel(str(eintrag.get("wert") or ""))


def persistiere_unbekannte(root: Path, eintraege: list, heute: str) -> int:
    """data/state/geraete_unbekannt.jsonl fuehren: eine Zeile je unbekanntem
    Titel bzw. Farbe, mit Anbieter, Quelle des Feldes, Datum und Haeufigkeit
    - Upsert auf (art, wert, anbieter), damit ein wiederkehrender Titel
    zaehlt statt jede Nacht eine neue Zeile zu machen.

    Tarif-Rauschen (`ist_tarif_titel`) wird beim SCHREIBEN gefiltert: neue
    Tarif-Titel kommen nicht hinein, und bestehende Rausch-Zeilen fallen beim
    Neuschreiben weg. Die Bereinigung des heutigen Bestands (3 Zeilen,
    Haeufigkeitssumme 87) macht damit der NAECHSTE Lauf mit mindestens einem
    Eintrag - data/state wird nur vom Lauf geschrieben, nie von Hand
    (Hausregel). Farb-Zeilen sind von der Regel unberuehrt.
    """
    if not eintraege:
        return 0
    pfad = Path(root) / "data" / "state" / _UNBEKANNT_DATEI
    pfad.parent.mkdir(parents=True, exist_ok=True)
    zeilen: list = []
    if pfad.exists():
        try:
            zeilen = [json.loads(z) for z in
                      pfad.read_text(encoding="utf-8").splitlines() if z.strip()]
        except (json.JSONDecodeError, ValueError):
            zeilen = []            # kaputte Datei: neu anfangen ist besser
            # als stehenbleiben - die Haeufigkeit ist eine Zaehlung, keine
            # Buchfuehrung mit Rechtsfolge.
    bereinigt = sum(1 for z in zeilen if _ist_tarif_eintrag(z))
    zeilen = [z for z in zeilen if not _ist_tarif_eintrag(z)]
    neue = [e for e in eintraege if not _ist_tarif_eintrag(e)]
    verworfen = bereinigt + (len(eintraege) - len(neue))
    if verworfen:
        log.info("Auto-Erkennung: %d Tarif-Titel aus der Arbeitsliste "
                 "gefiltert (%d alte Zeilen bereinigt, %d neue verworfen) - "
                 "die Liste bleibt Fruehindikator fuer Anker-Luecken (P5/E3)",
                 verworfen, bereinigt, len(eintraege) - len(neue))
    index = {(z.get("art"), z.get("wert"), z.get("anbieter")): i
             for i, z in enumerate(zeilen)}
    for eintrag in neue:
        schluessel = (eintrag.get("art"), eintrag.get("wert"),
                      eintrag.get("anbieter"))
        i = index.get(schluessel)
        if i is None:
            zeilen.append({"art": eintrag.get("art"),
                           "wert": eintrag.get("wert"),
                           "anbieter": eintrag.get("anbieter"),
                           "quelle": eintrag.get("quelle") or "",
                           "datum": heute, "haeufigkeit": 1})
            index[schluessel] = len(zeilen) - 1
            continue
        zeile = zeilen[i]
        zeile["haeufigkeit"] = int(zeile.get("haeufigkeit") or 0) + 1
        zeile["datum"] = heute
        zeile["quelle"] = eintrag.get("quelle") or zeile.get("quelle") or ""
    with open(pfad, "w", encoding="utf-8") as fh:
        for zeile in zeilen:
            fh.write(json.dumps(zeile, ensure_ascii=False) + "\n")
    return len(zeilen)
