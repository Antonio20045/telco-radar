"""Kampagnenbilder fuer die Promo-Uebersicht: das Bild AUS der Aktion, nicht
ein Foto der Seite.

Bis zum 07.08.2026 bekam hier jede MARKE genau ein Bild, und das war ein
Playwright-Screenshot ihrer Aktionsseite (1280x720 aus dem Viewport
geschnitten, siehe den Nachruf in collect/promo_snapshot.py). Antonio:

    "Das Problem ist aber, dass du halt irgendwelche Screenshots von den
    Seiten machst, die total beschissen aussehen. Das ist nicht richtig
    zugeschnitten. Bei vielen sieht man nur die Cookies. Und so ein
    Screenshot hilft ueberhaupt nicht. Bei Marktrecherche hast du halt die
    Bilder genutzt, die in diesem Artikel vorgekommen sind. Wieso kannst du
    das nicht bei Promo aufmachen?"

Genau das macht dieses Modul. Eine Aktionsseite traegt ihr Kampagnenmotiv
selbst - das Familienfoto zum Datenbonus, das Geraetefoto zum Bundle, die
Preisgrafik zur Wechselpraemie. Gemessen an den 15 konfigurierten Quellen
liefert schon das rohe HTML zwischen 3 und 66 Bildkandidaten je Seite.

DIE ZUORDNUNG ist der eigentliche Punkt, denn ein Bild je Marke reicht
nicht: eine Marke hat bis zu acht Angebote, und "wer wirbt gerade womit"
beantwortet sich nur, wenn NEBEN dem Angebot dessen eigenes Motiv steht.
Zugeordnet wird in drei Stufen, staerkstes Signal zuerst:

  1. ANKER  Das Bild steht in einem <a href>, das auf den Tiefenlink des
            Angebots zeigt. Das ist keine Heuristik, sondern die Struktur
            der Seite: der Tiefenlink kommt aus genau denselben Ankern
            (analyze/promo_analyst.py waehlt ihn per Nummer aus
            extract_link_candidates). Bild und Angebot stehen dann im selben
            Kasten der Seite.
  2. PFAD   Derselbe Pfad, andere Parameter/Fragmente - dieselbe Detailseite
            mit anderer Tarifvariante.
  3. TEXT   Seltene gemeinsame Woerter zwischen Angebotstext und Bildkontext
            (alt-Text plus naechste Ueberschrift), gewichtet mit
            1/Haeufigkeit. Dieselbe Rechnung wie beim roten Faden der
            Titelseite (report/html.py::_faden) und aus demselben Grund:
            gezaehlte Uebereinstimmung ordnet "Tarif" und "Handy" jedem
            Angebot zu, ein seltenes Wort wie "Kinder-Smartwatch" beweist
            etwas.

Dazu kommt als vierte Stufe das SEITENMOTIV: das Buehnenbild einer
Aktionsseite geht an deren staerkstes noch unbebildertes Angebot (siehe
_seitenmotive). Es belegt, womit auf dieser Seite geworben wird, nicht
welches ihrer Angebote gemeint ist - die Karte schreibt das dazu.

Was sich nicht belegen laesst, bekommt KEIN Bild - eine falsche Zuordnung
ist schlimmer als keine (dieselbe Regel wie beim roten Faden). Die Vorlage
faengt das ab: eine Aktion ohne Motiv bekommt ihre Kernzahl als
Schriftkachel, nie einen leeren Kasten.

Jedes Kandidatenbild wird hoechstens EINMAL vergeben. Zwei Kacheln
nebeneinander mit demselben Motiv lesen sich als Fehler, und im Zweifel ist
eine Zeile die ehrlichere Darstellung.

Abgelegt wird wie bei der Marktrecherche: gemessen (Pillow), auf
Zeitungsmasse verkleinert, als JPEG unter data/state/promo_images/ mit einem
Namen aus dem Hash der Quell-URL. Damit ist der Abruf ueber Laeufe hinweg
zwischengespeichert, und `raeume_auf()` entfernt, was kein Angebot mehr
braucht.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .report.bilder import _UA, _taugt, lade_und_lege_ab

log = logging.getLogger(__name__)

# Zielbreite. Die groesste Position der Promo-Uebersicht ist der Aufmacher
# mit rund 620 px bei 1440 px Fensterbreite; auf einem Retina-Schirm sind
# das 1240 echte Pixel. Es gibt hier keine zweite, kleinere Stufe wie bei
# der Marktrecherche: die Seite zeigt hoechstens ein paar Dutzend Bilder,
# nicht 190, der Repo-Ballast ist also kein Thema.
BREITE = 1280
# Darunter ist ein Bild als Bild wertlos - es waere in jeder Position
# hochskaliert. Etwas strenger als bei der Marktrecherche (400): eine
# Aktionsseite hat genug Kandidaten, und die schmalen sind hier fast immer
# Geraete-Freisteller oder Zahlungsart-Icons.
MIND_BREITE = 500

# Wortkram fuer die Textstufe.
_WORT_RE = re.compile(r"[A-Za-zÄÖÜäöüß0-9]{3,}")
# Woerter, die auf jeder Tarifseite stehen und deshalb nichts unterscheiden.
# Bewusst kurz gehalten: die Haeufigkeitsgewichtung unten entwertet haeufige
# Woerter ohnehin: diese Liste faengt nur die ab, die auf EINER Seite selten
# und trotzdem bedeutungslos sind.
_STOPP = {"und", "der", "die", "das", "mit", "fuer", "für", "von", "den",
          "dem", "ein", "eine", "einen", "bei", "auf", "aus", "zum", "zur",
          "des", "ist", "sind", "wird", "werden", "sich", "auch", "nur",
          "alle", "allen", "mehr", "jetzt", "neu", "neue", "neuen"}
# Ab welchem Gewicht eine Textuebereinstimmung als Beleg gilt. Ein einzelnes
# Wort, das auf der Seite nur einmal vorkommt, ergibt 1.0; zwei Woerter, die
# je viermal vorkommen, ergeben 0.5. Die Schwelle verlangt also entweder ein
# wirklich seltenes Wort oder mehrere halbwegs seltene.
_MIND_GEWICHT = 0.9
# Woerter, die in mehr als diesem Anteil der Bildkontexte einer Seite
# vorkommen, zaehlen gar nicht erst.
_ZU_HAEUFIG = 0.5

# Stufe 4 (siehe zuordnen()): das Seitenmotiv. Ab dieser angekuendigten
# Breite gilt ein Bild als Buehnenbild und nicht als Beiwerk. 0 heisst "die
# Seite sagt nichts ueber die Breite" und faellt NICHT durch - gemessen wird
# beim Download ohnehin, und gerade die grossen Buehnenbilder tragen oft
# keine width-Angabe (otelo.de: vier Kandidaten, alle ohne Angabe, alle
# 1920 px breit).
_MOTIV_MIND_BREITE = 700
# Bilder, die auf jeder Tarifseite stehen und nie eine Aktion zeigen. Der
# Muellfilter in report/bilder.py greift ueber die URL (logo, sprite,
# favicon); Testsiegel heissen aber nach ihrem Herausgeber
# ("csm_tuev-saarland", "csm_focus-money"). Sie sind ueber ihren alt-Text zu
# fassen, und der ist bei Siegeln zuverlaessig gesetzt - er ist ihr Zweck.
_SIEGEL_RE = re.compile(
    r"(siegel|testsieg|auszeichnung|ausgezeichnet|bewertung|tüv|tuev|"
    r"note\s+sehr\s+gut|leserwahl|award)", re.I)


def bildordner(root: Path) -> Path:
    return Path(root) / "data" / "state" / "promo_images"


def _worte(text: str) -> set[str]:
    return {w.lower() for w in _WORT_RE.findall(text or "")} - _STOPP


def _pfad_signatur(url: str) -> tuple[str, str]:
    """(host, pfad) einer URL, klein und ohne abschliessenden Schraegstrich.

    Query und Fragment fallen weg: `.../iphone-17-serie#angebot` und
    `.../iphone-17-serie?tarif=s` sind dieselbe Detailseite, und genau so
    unterscheiden sich Tiefenlink und Bildanker in der Praxis."""
    try:
        teile = urlsplit(url or "")
    except ValueError:
        return ("", "")
    return (teile.netloc.lower(), (teile.path or "/").rstrip("/").lower())


def rangfolge(angebot: dict, kandidaten: list[dict],
              haeufigkeit: dict[str, int] | None = None) -> list[tuple[float, dict]]:
    """Die Bildkandidaten fuer EIN Angebot, bestes zuerst: [(guete, kand)].

    `guete` ist 3.x fuer einen Ankertreffer, 2.x fuer einen Pfadtreffer und
    1.x fuer einen Textbeleg; Kandidaten ohne jeden Beleg fehlen ganz. Die
    Nachkommastelle traegt das Textgewicht bzw. die angekuendigte Breite,
    damit unter gleich starken Belegen das groessere Bild gewinnt.
    """
    ziel = (angebot.get("url") or "").strip()
    ziel_sig = _pfad_signatur(ziel)
    text = f"{angebot.get('headline') or ''} {angebot.get('description') or ''}"
    angebots_worte = _worte(text)
    haeufigkeit = haeufigkeit or {}

    bewertet: list[tuple[float, dict]] = []
    for kand in kandidaten:
        anker = (kand.get("anchor") or "").strip()
        # Die Breitenangabe der Seite ist nur ein Tiebreaker (und oft 0) -
        # gemessen wird beim Download.
        breiten_bonus = min(0.49, (kand.get("hint_w") or 0) / 4000)
        if ziel and anker:
            if anker == ziel:
                bewertet.append((3.5 + breiten_bonus, kand))
                continue
            if ziel_sig[1] and _pfad_signatur(anker) == ziel_sig:
                bewertet.append((2.5 + breiten_bonus, kand))
                continue
        gemeinsam = angebots_worte & _worte(kand.get("context") or "")
        if not gemeinsam:
            continue
        gewicht = sum(1.0 / max(1, haeufigkeit.get(w, 1)) for w in gemeinsam)
        if gewicht < _MIND_GEWICHT:
            continue
        bewertet.append((1.0 + min(0.99, gewicht / 10) + breiten_bonus / 100, kand))
    bewertet.sort(key=lambda b: -b[0])
    return bewertet


def _haeufigkeiten(kandidaten: list[dict]) -> dict[str, int]:
    """Wie oft jedes Wort in den Bildkontexten DIESER Seite vorkommt.

    Grundlage der 1/Haeufigkeit-Gewichtung. Woerter, die in mehr als der
    Haelfte der Kontexte stehen (Markenname, "Tarif", "Handy"), werden auf
    eine Haeufigkeit gesetzt, die sie unter die Schwelle drueckt - sie
    beweisen nichts."""
    zaehler: Counter = Counter()
    for kand in kandidaten:
        zaehler.update(_worte(kand.get("context") or ""))
    deckel = max(2, int(len(kandidaten) * _ZU_HAEUFIG))
    return {w: (n if n <= deckel else 10_000) for w, n in zaehler.items()}


def _seitenmotive(angebote: list[dict], kandidaten: list[dict],
                  vergeben: set[str], ergebnis: dict[str, dict],
                  leitseite: str) -> None:
    """Stufe 4: das Buehnenbild JE AKTIONSSEITE an das staerkste noch
    unbebilderte Angebot DIESER Seite.

    Viele Aktionsseiten binden ihr Kampagnenmotiv ohne Link und ohne
    alt-Text ein (otelo.de: vier Kandidaten, kein einziger Anker, kein
    einziger alt-Text) - dort greift keine der drei Stufen darueber, obwohl
    das Motiv der laufenden Aktion offen daliegt.

    Bis zum 08.08.2026 wurde hier genau EIN Motiv je MARKE vergeben, und das
    war die Rechnung von vorgestern: damals hatte eine Marke eine einzige
    Seite. Seit sie bis zu sieben hat (promo_config.PromoSource.pages), liegt
    je Seite ein eigenes Buehnenbild bereit - congstar bringt ueber vier
    Seiten 80 Bildkandidaten mit und bekam trotzdem hoechstens ein Motiv.
    Gemessen ueber alle statisch abrufbaren Seiten am 08.08.2026: 41 von 77
    sichtbaren Angeboten hatten ein Bild, mit dieser Stufe je Seite sind es
    deutlich mehr.

    Die Aussage bleibt dieselbe und bleibt belegt: ein Seitenmotiv zeigt,
    WOMIT auf dieser Seite geworben wird - nicht, welches ihrer Angebote
    gemeint ist. Genau deshalb bekommt es das staerkste Angebot der Seite und
    keins darunter, und genau deshalb schreibt die Karte "Motiv der
    Aktionsseite" dazu (siehe promo_index.html.j2).

    Ein Angebot ohne `source_url` (Bestand aus der Zeit vor den Mehrfach-
    seiten) haengt an der Leitseite - dieselbe Konvention wie in
    PromoDB.mark_stale.
    """
    nach_seite: dict[str, list[dict]] = {}
    for kand in kandidaten:
        nach_seite.setdefault(kand.get("page") or "", []).append(kand)

    def _taugt_als_motiv(k: dict) -> bool:
        breite = k.get("hint_w") or 0
        return ((k.get("src") or "") not in vergeben
                and (breite == 0 or breite >= _MOTIV_MIND_BREITE)
                and not _SIEGEL_RE.search(k.get("context") or ""))

    for seite, seiten_kandidaten in nach_seite.items():
        # Kein `page` an den Kandidaten (Bestand, Tests): dann ist "die
        # Seite" die Marke, und es bleibt bei einem Motiv - genau das
        # Verhalten von vor dem 08.08.2026.
        if seite:
            passend = [a for a in angebote
                       if (a.get("source_url") or leitseite) == seite]
        else:
            passend = list(angebote)
        ziel = next((a for a in passend
                     if a.get("id") and not ergebnis.get(a["id"])), None)
        if ziel is None:
            continue
        # Dokumentreihenfolge, nicht Groesse: das Buehnenbild steht oben auf
        # der Seite, die 1920 px breiten Testsiegel stehen unten.
        motive = [k["src"] for k in seiten_kandidaten if _taugt_als_motiv(k)]
        if not motive:
            continue
        ergebnis[ziel["id"]] = {"quellen": motive[:3], "art": "motiv"}
        # Vergeben ist vergeben: sonst steht dasselbe Motiv auf der naechsten
        # Seite noch einmal, und zwei gleiche Kacheln lesen sich als Fehler.
        vergeben.update(motive[:3])


def zuordnen(angebote: list[dict], kandidaten: list[dict],
             leitseite: str = "") -> dict[str, dict]:
    """Ordnet den Angeboten EINER Marke ihre Bildkandidaten zu.

    Gibt {angebots-id: {"quellen": [url, ...], "art": "angebot"|"motiv"}}
    zurueck - je Angebot die belegten Kandidaten in absteigender Guete, damit
    der Abruf den naechsten nehmen kann, wenn der erste zu klein oder kaputt
    ist. Ein Kandidat taucht hoechstens bei EINEM Angebot auf: vergeben wird
    gierig, staerkster Beleg zuerst, und was vergeben ist, ist weg (siehe
    Modul-Docstring).

    "art" sagt, WAS das Bild belegt, und die Seite schreibt es dazu:
    "angebot" = das Bild steht im Kasten dieses Angebots oder nennt es
    (Stufen 1-3), "motiv" = es ist das Buehnenbild der Aktionsseite und
    zeigt, womit dort geworben wird - nicht zwingend dieses eine Angebot
    (Stufe 4, siehe _seitenmotive). Ohne diese Unterscheidung behauptet eine
    Kachel mehr, als belegt ist: Otelos Seitenmotiv wirbt mit "mehr GB,
    gleicher Preis", waehrend die staerkste Aktion die Freundschaftswerbung
    ist.

    `leitseite` ist die URL der Marken-Leitseite. Angebote ohne `source_url`
    (Bestand von vor den Mehrfachseiten) haengen an ihr - dieselbe
    Konvention wie in PromoDB.mark_stale.

    Angebote ohne Beleg fehlen im Ergebnis. Das ist kein Fehlschlag, sondern
    die Aussage "hier gibt es kein passendes Bild" - die Vorlage macht
    daraus eine Zeile statt einer Kachel.
    """
    if not angebote or not kandidaten:
        return {}
    # Logos, Zaehlpixel und Platzhalter sehen aus wie Bilder und sind keine.
    # Aussortiert wird HIER und nicht erst beim Abruf: sonst verbraucht das
    # Markenlogo, das auf jeder Seite ganz oben steht, den Kandidatenplatz
    # des Buehnenbilds (gemessen bei ALDI TALK - `aldilogo.png` stand vor
    # dem Back2School-Motiv und gewann Stufe 4).
    kandidaten = [k for k in kandidaten if _taugt(k.get("src") or "")]
    if not kandidaten:
        return {}
    haeufigkeit = _haeufigkeiten(kandidaten)
    # Alle (Angebot, Kandidat)-Paare mit Beleg, staerkster zuerst. Die
    # Angebotsreihenfolge entscheidet nur bei exakt gleicher Guete - dann
    # bekommt das hoeher bewertete Angebot das Bild.
    paare: list[tuple[float, int, str, dict]] = []
    for rang, angebot in enumerate(angebote):
        eid = angebot.get("id") or ""
        if not eid:
            continue
        for guete, kand in rangfolge(angebot, kandidaten, haeufigkeit):
            paare.append((guete, rang, eid, kand))
    paare.sort(key=lambda p: (-p[0], p[1]))

    vergeben: set[str] = set()
    ergebnis: dict[str, dict] = {}
    for _guete, _rang, eid, kand in paare:
        src = kand.get("src") or ""
        if not src or src in vergeben:
            continue
        # Bis zu drei Kandidaten je Angebot: der erste kann beim Abruf
        # durchfallen (zu klein, 403, kaputt), und ein zweiter Versuch ist
        # billiger als eine leere Kachel.
        eintrag = ergebnis.setdefault(eid, {"quellen": [], "art": "angebot"})
        if len(eintrag["quellen"]) >= 3:
            continue
        eintrag["quellen"].append(src)
        vergeben.add(src)

    # ---- Stufe 4: das Buehnenbild JE AKTIONSSEITE, siehe _seitenmotive().
    _seitenmotive(angebote, kandidaten, vergeben, ergebnis, leitseite)
    return ergebnis


def hole_bilder(zuordnung: dict[str, dict], eintraege: dict[str, dict],
                root: Path) -> Counter:
    """Holt die zugeordneten Bilder und stempelt sie in die Eintraege.

    Setzt je Eintrag `image` (Dateiname im Bildordner), `image_w`,
    `image_h`, `image_src` (die Quell-URL, an der der naechste Lauf erkennt,
    dass sich nichts geaendert hat) und `image_kind` ("angebot" oder
    "motiv", siehe zuordnen()). Ein Eintrag, dessen Bild nicht zu holen ist,
    verliert seine alten Bildfelder - sonst zeigt die Seite auf eine Datei,
    die `raeume_auf()` als unreferenziert loescht. Genau so entstanden am
    06.08.2026 vier Meldungen mit `image`, aber ohne Datei.
    """
    ordner = bildordner(root)
    bilanz: Counter = Counter()
    if not zuordnung:
        return bilanz
    with httpx.Client(headers={"User-Agent": _UA}, timeout=12.0,
                      follow_redirects=True) as client:
        for eid, wahl in zuordnung.items():
            eintrag = eintraege.get(eid)
            if eintrag is None:
                continue
            quellen = wahl.get("quellen") or []
            art = wahl.get("art") or "angebot"
            bilanz["geprueft"] += 1
            # Unveraendert und schon da: nichts tun. Der Abruf ist der teure
            # Teil, und eine Aktionsseite wechselt ihr Motiv selten.
            if (eintrag.get("image_src") in quellen
                    and eintrag.get("image")
                    and (ordner / eintrag["image"]).exists()):
                eintrag["image_kind"] = art
                bilanz["unveraendert"] += 1
                continue
            for feld in ("image", "image_w", "image_h", "image_src",
                         "image_kind"):
                eintrag.pop(feld, None)
            for quelle in quellen:
                try:
                    treffer = lade_und_lege_ab(quelle, ordner, BREITE, client,
                                               mind_breite=MIND_BREITE)
                except Exception as exc:  # noqa: BLE001 - ein Bild kippt keinen Lauf
                    log.debug("Promo-Bild %s: %s", quelle, exc)
                    treffer = None
                if treffer:
                    name, breite, hoehe = treffer
                    eintrag["image"] = name
                    eintrag["image_w"] = breite
                    eintrag["image_h"] = hoehe
                    eintrag["image_src"] = quelle
                    eintrag["image_kind"] = art
                    bilanz["geladen"] += 1
                    break
            else:
                bilanz["ohne_bild"] += 1
    return bilanz


def raeume_auf(root: Path, eintraege: list[dict]) -> int:
    """Loescht Bilder, die kein Eintrag mehr referenziert.

    Ohne das waechst data/state/promo_images/ mit jeder abgeloesten
    Kampagne, und die git-Historie vergisst nie. Gerechnet wird ueber ALLE
    Eintraege der Promo-Datenbank, auch die ausgelaufenen - deren Karten
    stehen zwar nicht mehr auf der Seite, aber ein Bild wieder zu beschaffen
    kostet mehr als es zu behalten, solange der Eintrag existiert."""
    ordner = bildordner(root)
    if not ordner.exists():
        return 0
    gebraucht = {e.get("image") for e in eintraege if e.get("image")}
    geloescht = 0
    for bild in ordner.iterdir():
        if bild.is_file() and bild.name not in gebraucht:
            try:
                bild.unlink()
                geloescht += 1
            except OSError:
                pass
    if geloescht:
        log.info("Promo-Bilder aufgeraeumt: %d nicht mehr referenzierte geloescht",
                 geloescht)
    return geloescht
