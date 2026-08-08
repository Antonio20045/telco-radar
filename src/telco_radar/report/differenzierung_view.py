"""Anzeige-Vorbereitung fuer die Differenzierungs-Seite (reine
Datenaufbereitung, kein LLM - Muster: report/promo.py).

Die Frage der Seite ist eine einzige: **womit heben sich Telkos ab, jenseits
von Preis und Datenvolumen?** Antonio am 08.08.2026: "Es geht darum, was
Telco-Unternehmen weltweit tun, um sich JENSEITS von Preis und Gigabytes zu
differenzieren - zusaetzliche externe Services usw. ... Genau sowas will ich
als Radar auf dem Schirm haben, als Inspiration von allen Telco-Unternehmen
der Welt."

Ein Radar zeigt Beispiele, keinen Essay. Daraus folgt die Gliederung:

    MARKTBILD           die Auswertung ueber den ganzen Bestand: welcher Hebel
                        wird wie oft gezogen, wer ist am breitesten
                        aufgestellt, aus welchen Regionen kommen die
                        Beispiele. Das ist die Antwort auf "was machen die
                        anderen", bevor man 71 Einzelbeispiele liest.
    NEU AUF DEM RADAR   die juengsten Funde, prominent - das ist der
                        Nachrichtenwert der Seite. Gibt es keine, stehen
                        stattdessen die zuletzt nachgeprueften.
    BIBLIOTHEK          je Hebel eine Rubrik, darunter die Beispiele
                        GEWICHTET: ein Aufmacher, ein paar Karten, der Rest
                        als Zeilen. Ein Hebel ohne Beispiele erscheint NICHT -
                        ein leerer Kasten sagt nichts.

**Warum es das Marktbild und die Gewichtung gibt.** Bis zum 08.08.2026 war die
Seite eine 9060 px hohe Wand aus 77 gleich grossen Textkaertchen ohne ein
einziges Bild. Antonio: *"Es ist total unuebersichtlich, sich das anzugucken.
Keine Bilder, es ist schwer zu verstehen ... damit nicht so viel kognitive
Arbeit darin besteht, erstmal zu verstehen, was die Differenzierung ist."*
Gleich grosse Kaertchen sind eine Liste, keine Analyse: sie behaupten, dass
alle 77 Beispiele gleich wichtig sind, und ueberlassen das Sortieren dem Leser.
Deshalb steht die Auswertung jetzt VOR den Beispielen, jeder Hebel sagt in
EINEM Satz, was er ueberhaupt bedeutet (`blurb` aus `report/differentiation.py`
- dieselbe Quelle wie die Hebel-Farbe, damit die Erklaerung nicht an zwei
Orten auseinanderlaufen kann), und innerhalb eines Hebels traegt das juengste
belegte Beispiel den Abschnitt.

**Der Grund, warum es dieses Modul gibt: die Seite las bis zum 08.08.2026 nur
EINEN der zwei vorhandenen Speicher.**

    differentiation_db.json   (DiffDB, analyze/category_sweep) - der
                              rotierende Web-Sweep. Wurde gerendert.
    differentiation.jsonl     (DiffStore, analyze/diff_curator) - der Kurator
                              ueber den woechentlichen Presse-Crawl. Wurde
                              NICHT gerendert; er lief jede Woche umsonst.

Beide beschreiben dasselbe (ein belegter Differenzierungs-Move mit Quelle),
nur in zwei Feldnamen-Dialekten. `merge()` fuehrt sie auf EINEN Bestand
zusammen; bei gleicher URL gewinnt der DiffDB-Eintrag, weil seine Felder
bereits fuer die Anzeige geschrieben sind (`what` ist dort ein fertiger
deutscher Satz, kein Rohtitel).

**Warum die Hauptzeile eines Presse-Eintrags aus `summary` kommt und nicht
aus `title`:** gemessen am Bestand vom 08.08.2026 sind die Originaltitel
mehrsprachig und tragen oft ein angehaengtes Datum - "Akses Nonton Piala
Dunia FIFA 2026 Lebih Fleksibel und Terjangkau, Telkomsel Hadirkan Paket
Bundling Eksklusif bersama FOLA PLAY 13 Jun 2026". Auf einer deutschen Seite
fuer Leser ohne Technik-Hintergrund (CLAUDE.md §8) ist das keine
Schlagzeile. `summary` ist der deutsche Satz, der beschreibt, worum es geht -
also genau die Rolle, die `what` im DiffDB-Eintrag hat. Nur so sehen die
Karten beider Herkuenfte gleich aus, und Vergleichen heisst Gleiches
nebeneinander legen. Der Originaltitel geht nicht verloren: die Hauptzeile
verlinkt auf die Quelle.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from ..models import normalize_url
from ..textwerkzeug import ohne_vodafone_rat
from .differentiation import DIFF_THEMES

# Wie lange ein Eintrag als "neu" gilt, gerechnet ab dem Stand der Ausgabe.
# Zehn Tage, weil die Pipeline zweimal die Woche laeuft: ein Fund bleibt so
# ueber mindestens zwei Ausgaben sichtbar und verschwindet nicht, bevor ihn
# jemand gesehen hat.
NEU_TAGE = 10
# Wie viele Karten oben stehen. Drei, seit sie ein Bild tragen und in voller
# Breite stehen - sechs Bildkarten waeren wieder eine Kachelwand, nur bunter.
MAX_NEU = 3
# Die Gewichtung innerhalb eines Hebels: ein Aufmacher, dann GENAU EINE Reihe
# Karten, dann Zeilen. Drei Karten sind bei 1440 px diese eine Reihe. Mit
# fuenf war die Seite 15 100 px hoch - Bilder machen eine Karte dreimal so
# hoch wie das Textkaertchen von vorher, also muessen es weniger Karten
# werden, nicht gleich viele mit Bild.
KARTEN_JE_HEBEL = 3
# Was am Stueck sichtbar bleibt, bevor der Rest in den Aufklapper geht. Der
# groesste Hebel hatte am 08.08.2026 17 Beispiele - als 17 Kaertchen war er
# allein zwei Bildschirme hoch.
ZEILEN_OFFEN = 5

# Was ein Hebel ueberhaupt bedeutet, in einem Satz. Quelle ist bewusst
# `DIFF_THEMES` (report/differentiation.py) - dort steht schon die Farbe des
# Hebels, und eine Erklaerung, die an einem zweiten Ort gepflegt wird, sagt
# nach dem dritten Hebel etwas anderes als die Klassifikation.
HEBEL_ERKLAERUNG = {t["key"]: " ".join(str(t.get("blurb") or "").split())
                    for t in DIFF_THEMES}


# Woerter, nach denen ein Punkt KEIN Satzende ist. Ohne diese Liste endete
# "AT&T Guarantee: Gutschriften bei Ausfaellen, auf rund 50 Mio. Kunden
# ausgeweitet." nach "50 Mio." - drei von 51 Bestandssaetzen traf das.
_ABKUERZUNGEN = {"Mio", "Mrd", "Nr", "ca", "bzw", "inkl", "exkl", "evtl",
                 "ggf", "usw", "vgl", "bspw", "Bsp", "Abb", "Dr", "Prof",
                 "St", "Str", "Jh", "Tsd"}
_MOEGLICHES_SATZENDE = re.compile(r"[.!?](?=\s+[A-ZÄÖÜ„])")
_LETZTES_WORT = re.compile(r"[\wÄÖÜäöüß]+$")


def _text(wert) -> str:
    return " ".join(str(wert or "").split()).strip()


def erster_satz(text: str) -> str:
    """Der erste vollstaendige Satz eines Fliesstextes.

    Eine Karte traegt eine Aussage, keinen Absatz. Der Presse-Zweig liefert
    aber Zusammenfassungen und Begruendungen aus zwei bis drei Saetzen; die
    zweite Haelfte ist regelmaessig der Nachsatz ("Vodafone sollte pruefen,
    ob ..."), der auf einer Uebersichtsseite nichts entscheidet.

    Das ist ausdruecklich KEIN Kuerzen: was stehen bleibt, ist ein
    vollstaendiger Satz mit Schlusspunkt, nie ein abgebrochener mit "…"
    (CLAUDE.md §5, Abnahmekriterium 5).
    """
    text = _text(text)
    for treffer in _MOEGLICHES_SATZENDE.finditer(text):
        wort = _LETZTES_WORT.search(text[:treffer.start()])
        wort = wort.group(0) if wort else ""
        # Einzelbuchstaben und Versalien sind Initialen oder Kuerzel
        # ("z.B.", "U.S."), kein Satzende.
        if len(wort) < 2 or wort.isupper() or wort in _ABKUERZUNGEN:
            continue
        return text[:treffer.end()]
    return text


def _domain(url: str) -> str:
    return urlsplit(url or "").netloc.removeprefix("www.")


def _aus_db(e: dict) -> dict:
    """Ein Sweep-Eintrag - er ist bereits in Anzeigeform geschrieben."""
    return {
        "theme": e.get("theme") or "",
        "operator": _text(e.get("operator")),
        "region": _text(e.get("region")),
        "what": _text(e.get("what")),
        "why": ohne_vodafone_rat(_text(e.get("why"))),
        "url": e.get("url") or "",
        "source": _domain(e.get("url")) or _text(e.get("source")),
        "date": e.get("date") or "",
        "first_seen": e.get("first_seen") or "",
        "last_verified": e.get("last_verified") or e.get("first_seen") or "",
        "herkunft": "sweep",
    }


def _aus_store(e: dict) -> dict:
    """Ein Kurator-Eintrag aus dem Presse-Crawl, auf dieselbe Kartenform
    gebracht (Feldbegruendung siehe Modulkopf)."""
    return {
        "theme": e.get("theme") or "",
        "operator": _text(e.get("operator")),
        "region": _text(e.get("region")),
        "what": erster_satz(e.get("summary")) or _text(e.get("title")),
        # Erst den Rat streichen, dann kuerzen: steht der Ratschlag im
        # ERSTEN Satz, nimmt die umgekehrte Reihenfolge den Befund mit.
        "why": erster_satz(ohne_vodafone_rat(e.get("why_it_matters"))),
        "url": e.get("url") or "",
        "source": _domain(e.get("url")) or _text(e.get("source")),
        "date": e.get("date") or "",
        "first_seen": e.get("first_seen") or "",
        # Der Presse-Zweig verifiziert nicht nach; der Fund IST die Pruefung.
        "last_verified": e.get("first_seen") or "",
        "herkunft": "presse",
    }


def merge(db_entries, store_entries) -> list[dict]:
    """Beide Speicher zu einem Bestand. Bei gleicher URL gewinnt die DiffDB.

    Verglichen wird die NORMALISIERTE URL, nicht die rohe - dieselbe Meldung
    steht in den zwei Speichern schon einmal mit und einmal ohne "www."
    (`models.normalize_url` ist derselbe Schluessel, den beide Speicher
    intern zum Deduplizieren benutzen).
    """
    bestand: dict[str, dict] = {}
    for roh in db_entries or []:
        eid = normalize_url(roh.get("url") or "") or roh.get("id")
        if eid:
            bestand[eid] = _aus_db(roh)
    for roh in store_entries or []:
        eid = normalize_url(roh.get("url") or "") or roh.get("id")
        if eid and eid not in bestand:
            bestand[eid] = _aus_store(roh)
    return list(bestand.values())


def _neuheitsgrenze(stichtag: str, tage: int = NEU_TAGE) -> str:
    try:
        return (datetime.fromisoformat(stichtag)
                - timedelta(days=tage)).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _juengste_zuerst(e: dict) -> tuple:
    return (e.get("first_seen") or "", e.get("last_verified") or "",
            e.get("operator") or "")


def kachelwort(e: dict) -> str:
    """Die Aufschrift der Schriftkachel, wenn ein Beispiel kein Bild hat.

    Dieselbe Regel wie auf der Promo-Uebersicht (CLAUDE.md §5): jede Karte
    traegt ein Motiv, und die Schriftkachel ist die zweite gueltige Form -
    nicht der Notnagel fuer ein fehlendes Bild. Sie zeigt den Absender, denn
    das ist die Information, nach der auf dieser Seite verglichen wird
    ("machen das nur die Amerikaner?").
    """
    name = _text(e.get("operator"))
    if not name:
        return _text(e.get("source")) or "Beispiel"
    # Mehrfach-Absender ("Deutsche Telekom, e&, Singtel Group, SK Telecom,
    # SoftBank") sind auf einer Kachel nicht lesbar - dann steht dort der
    # erste und die Zahl der uebrigen.
    teile = [t.strip() for t in name.split(",") if t.strip()]
    if len(teile) > 1:
        return f"{teile[0]} +{len(teile) - 1}"
    return name


def _operatoren(e: dict) -> list[str]:
    """Die einzelnen Absender eines Beispiels. Ein Joint Venture von fuenf
    Konzernen ist fuenf Betreibern zuzurechnen, nicht einem Namen mit
    Kommata - sonst zaehlt das Marktbild jede Allianz als eigenen Anbieter."""
    return [t.strip() for t in _text(e.get("operator")).split(",") if t.strip()]


def _balken(zaehler: dict[str, int]) -> list[dict]:
    """Gezaehlte Werte als Balken, relativ zum groessten. Reine Anzeige-
    Rechnung; die Breite steht als Prozentzahl in der Vorlage."""
    hoechste = max(zaehler.values(), default=0)
    return [{"name": name, "n": n,
             "w": round(100 * n / hoechste) if hoechste else 0}
            for name, n in sorted(zaehler.items(),
                                  key=lambda p: (-p[1], p[0]))]


def marktbild(bestand: list[dict], hebel: list[dict],
              max_anbieter: int = 8) -> dict:
    """Die Auswertung ueber den GANZEN Bestand - was die Beispiele zusammen
    sagen, bevor man sie einzeln liest.

    Drei Fragen, drei Zahlenreihen:

      Welcher Hebel?   wie oft ein Feld ueberhaupt bespielt wird.
      Wer?             welcher Anbieter am breitesten aufgestellt ist. Gezaehlt
                       wird nach BEISPIELEN, gereiht nach der Zahl der
                       verschiedenen Hebel - wer denselben Hebel achtmal zieht,
                       hat eine Kampagne, wer vier verschiedene zieht, eine
                       Strategie.
      Wo?              aus welchen Regionen die Beispiele stammen.
    """
    hebel_zaehler = {h["label"]: h["n"] for h in hebel}
    regionen: dict[str, int] = {}
    je_anbieter: dict[str, dict] = {}
    for e in bestand:
        region = _text(e.get("region"))
        if region:
            regionen[region] = regionen.get(region, 0) + 1
        label = _text(e.get("hebel_label"))
        for name in _operatoren(e):
            eintrag = je_anbieter.setdefault(name, {"name": name, "n": 0,
                                                    "hebel": set()})
            eintrag["n"] += 1
            if label:
                eintrag["hebel"].add(label)
    aktivste = sorted(je_anbieter.values(),
                      key=lambda a: (len(a["hebel"]), a["n"], a["name"]),
                      reverse=True)[:max_anbieter]
    return {
        "gesamt": len(bestand),
        "n_anbieter": len(je_anbieter),
        "n_regionen": len(regionen),
        "n_hebel": len(hebel),
        "n_neu": sum(1 for e in bestand if e.get("neu")),
        "n_bild": sum(1 for e in bestand if e.get("image")),
        "hebel_balken": _balken(hebel_zaehler),
        "regionen": _balken(regionen),
        "aktivste": [{"name": a["name"], "n": a["n"],
                      "hebel": sorted(a["hebel"]),
                      "n_hebel": len(a["hebel"])} for a in aktivste],
    }


def _gewichten(eintraege: list[dict], schon_oben: set | None = None) -> dict:
    """Ein Hebel-Abschnitt in drei Gewichtsstufen.

    Der Aufmacher ist das juengste Beispiel MIT Bild - und **nur** ein
    Beispiel mit Bild kann Aufmacher sein. Ohne Bild bekommt der Hebel
    keinen: eine Schriftkachel ueber 46 % Breite fuellt die groesste Position
    des Abschnitts nicht, sie laesst daneben eine halbe Spalte leer, und
    genau dieser Eindruck ("da fehlen bei einigen die Bilder, das wirkt so
    richtig scheisse", 08.08.2026 zur Promo Uebersicht) soll nicht
    wiederkommen. Dann stehen alle Beispiele gleichrangig im Kartenraster -
    eine Stufe weniger ist ehrlicher als eine leere Stufe.

    `schon_oben` sind die URLs der Radar-Karten. Ein Beispiel, das oben schon
    gross steht, fuehrt seinen Hebel nicht auch noch an - sonst steht dieselbe
    Karte zweimal auf einem Bildschirm. Es faellt deshalb nicht weg (die
    Rubrikzahl meint alle Beispiele des Hebels), es steht nur eine Stufe
    tiefer.
    """
    if not eintraege:
        return {"lead": None, "karten": [], "zeilen": [], "zeilen_offen": [],
                "zeilen_rest": []}
    schon_oben = schon_oben or set()
    lead = next((e for e in eintraege
                 if e.get("image") and e.get("url") not in schon_oben), None)
    rest = [e for e in eintraege if e is not lead]
    # Ohne Aufmacher ruecken die Karten eine Reihe hoch: der Abschnitt hat
    # dann sechs statt fuenf Karten, nicht eine Luecke.
    deckel = KARTEN_JE_HEBEL if lead else KARTEN_JE_HEBEL + 1
    karten = rest[:deckel]
    zeilen = rest[deckel:]
    return {"lead": lead, "karten": karten, "zeilen": zeilen,
            "zeilen_offen": zeilen[:ZEILEN_OFFEN],
            "zeilen_rest": zeilen[ZEILEN_OFFEN:]}


def aufbereiten(db_entries, store_entries, themes, stichtag: str,
                farben: dict | None = None, einordnung: dict | None = None,
                bilder: dict | None = None,
                vorhandene_bilder: set | None = None) -> dict:
    """Der fertige Seitenzustand: Marktbild, Radar-Karten und Hebel-Rubriken.

    `themes` ist die Hebel-Liste (key, label) aus analyze/category_sweep -
    sie gibt die Reihenfolge der Rubriken vor. `farben` bildet Hebel auf die
    Akzentfarbe ab; sie erscheint nur als schmale Linie, nie als Flaeche
    (CLAUDE.md §5). `einordnung` bildet Hebel auf den Absatz des
    Differenzierungsberichts ab, der zu ihm gehoert - so steht der Bericht
    dort, wo seine Beispiele stehen, statt als ein langer Block am Seitenende
    (siehe report/differenzierung_bericht.py).

    `bilder` ist der Bildindex aus `diff_bilder.lade_index()`. Er muss HIER
    hinein und darf nicht nachtraeglich ueber den Bestand gestempelt werden:
    `merge()` legt neue Dicts an, und die Gewichtung entscheidet anhand des
    Bildes, welches Beispiel einen Hebel anfuehrt. Genau daran ist der erste
    Anlauf gescheitert - die Bilder standen auf den Karten, aber KEIN
    Abschnitt hatte einen Aufmacher, weil zum Zeitpunkt der Gewichtung noch
    kein Eintrag ein Bild trug. Beschafft werden sie in der Pipeline; dieses
    Modul fasst nie das Netz an.
    """
    farben = farben or {}
    einordnung = einordnung or {}
    grenze = _neuheitsgrenze(stichtag)
    bestand = merge(db_entries, store_entries)
    if bilder:
        from . import diff_bilder
        diff_bilder.verteile(bestand, bilder, vorhandene_bilder)
    for e in bestand:
        e["neu"] = bool(grenze and (e.get("first_seen") or "") > grenze)
        e["kachelwort"] = kachelwort(e)

    label_map = dict(themes)
    # Erst die Etiketten, dann die Radar-Karten, dann die Gewichtung: die
    # Gewichtung eines Hebels muss wissen, was oben schon gross steht.
    for e in bestand:
        key = e.get("theme")
        e["hebel_label"] = label_map.get(key, "")
        e["farbe"] = farben.get(key, "")

    neu = sorted((e for e in bestand if e["neu"]),
                 key=_juengste_zuerst, reverse=True)[:MAX_NEU]
    rueckfall = not neu
    if rueckfall:
        # Eine ruhige Woche darf die Seite nicht enthaupten. Dann stehen oben
        # die zuletzt nachgeprueften Beispiele - und die Ueberschrift sagt es.
        neu = sorted(bestand, key=lambda e: (e.get("last_verified") or "",
                                             e.get("first_seen") or ""),
                     reverse=True)[:MAX_NEU]
    oben = {e.get("url") for e in neu}

    hebel = []
    for key, label in themes:
        eintraege = sorted((e for e in bestand if e.get("theme") == key),
                           key=_juengste_zuerst, reverse=True)
        if not eintraege:
            # Ein Hebel ohne Beispiel steht nicht auf der Seite. "Noch keine
            # bestaetigten Beispiele" war zwoelfmal derselbe leere Kasten.
            continue
        hebel.append({"key": key, "label": label, "n": len(eintraege),
                      "farbe": farben.get(key, ""), "eintraege": eintraege,
                      "erklaerung": ohne_vodafone_rat(
                          HEBEL_ERKLAERUNG.get(key, "")),
                      "einordnung": ohne_vodafone_rat(
                          _text(einordnung.get(key))),
                      "n_bild": sum(1 for e in eintraege if e.get("image")),
                      **_gewichten(eintraege, oben)})

    return {"bestand": bestand, "hebel": hebel, "neu": neu,
            "neu_ist_rueckfall": rueckfall, "gesamt": len(bestand),
            "n_hebel": len(hebel),
            "marktbild": marktbild(bestand, hebel)}
