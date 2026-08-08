"""Anzeige-Vorbereitung fuer die Dauerseite "Der deutsche Wettbewerb"
(reine Datenaufbereitung, kein LLM - wie report/promo.py).

Antonio am 08.08.2026: "Eine ganz genaue Wettbewerbsseite, wo ich fuer
Deutschland ueber Telekom, O2 und 1&1 sehe, was sie gerade machen ...
Interessant auch im historischen Kontext: nicht nur die Meldung dieser
Woche, sondern ueber die Wochen und Monate."

Daraus folgt die Gliederung, und der Schwerpunkt liegt auf dem letzten
Punkt:

    LAGE       Das aktuellste Profil des Wettbewerbers (summary, themes)
               plus die Themen der Wochen davor - was ihn seit Wochen
               beschaeftigt, nicht nur seit Freitag.
    AKTIONEN   Was von ihm gerade beworben wird (aus der Promo-Datenbank,
               ueber die Konzernzuordnung der Marke).
    CHRONIK    Jede Meldung, die ihn seit Beginn der Beobachtung betraf,
               nach Monaten gruppiert. Das ist der Punkt der Seite.

Die Seite entsteht vollstaendig beim Rendern aus dem Berichtsarchiv - es
gibt keinen eigenen Pipeline-State und keinen zusaetzlichen LLM-Aufruf.
Zwei Quellen speisen die Chronik:

  * die `moves` der Wettbewerber-Profile (analyze/competitors.py) - vom
    Analysten ausgewaehlt und mit einer Notiz versehen, und
  * die Meldungen der Wochenberichte selbst, deren Absender zum
    Wettbewerber gehoert.

Beide zusammen, dedupliziert ueber die normalisierte URL. Die ERSTE Woche
gewinnt: das Datum eines Eintrags ist der Tag, an dem die Meldung in den
Radar kam - eine Chronik datiert die Aufnahme, nicht den letzten Abruf.

Die Wochen kommen fertig aufbereitet aus html.render_site(): `highlights`
aus `_flatten()`, `competitors` aus `_prep_competitors()`. Beide haben die
stillgelegten Quellen (`_SUPPRESSED_SOURCE_DOMAINS`) schon aussortiert -
diese Datei filtert deshalb nicht noch einmal danach.
"""
from __future__ import annotations

import html as html_lib
import re
import unicodedata
from urllib.parse import urlsplit

from ..analyze.promo_ranker import MECHANICS
from ..textwerkzeug import ohne_vodafone_teil

# Wie viele Aktionen je Wettbewerber auf der Seite stehen. Der Rest steht
# vollstaendig auf der Promo Uebersicht, dorthin verweist die Zeile darunter.
_MAX_AKTIONEN = 3
# Wie viele Wochen der Themenverlauf zurueckreicht. Vier Profile zeigen die
# Verschiebung ("Ende Juli Router und Streaming, jetzt Glasfaser und Joyn"),
# ohne dass unter jedem Wettbewerber eine halbe Seite Etiketten steht.
_MAX_THEMENWOCHEN = 3
_MAX_THEMEN_JE_WOCHE = 6
# Wie viele Meldungen des laufenden Monats gleich offen stehen. Antonio am
# 08.08.2026: "mach Wettbewerb das Layout besser, sodass man nicht so viel
# runterscrollen muss." Der Monat mit 30 Meldungen war 2600 px hoch, drei
# Wettbewerber darunter machten eine Seite von 6777 px - man scrollte sieben
# Bildschirmhoehen, um den zweiten Wettbewerber ueberhaupt zu sehen. Zwoelf
# Meldungen sind in zwei Spalten sechs Zeilen: genug, um den Monat zu
# erfassen, wenig genug, dass der naechste Wettbewerber in Sichtweite bleibt.
# Der Rest steht vollstaendig einen Klick weiter - nichts faellt weg.
_OFFEN_JE_MONAT = 12

_TRACKING = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")



def anker(name: str) -> str:
    """Stabiler Anker aus einem Wettbewerbernamen ("Telefónica / O2" ->
    "telefonica-o2"). Muss ueber Laeufe hinweg gleich bleiben - die Anker
    stehen in Mails."""
    zerlegt = unicodedata.normalize("NFKD", name or "")
    ascii_name = "".join(c for c in zerlegt if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "wettbewerber"


def _norm_url(url: str) -> str:
    """Zwei Schreibweisen derselben Quelle sind EIN Eintrag.

    Ohne diese Normalisierung stuende dieselbe Meldung mehrfach in der
    Chronik: der Analyst uebernimmt die URL aus der Meldung woertlich, und
    zwischen zwei Laeufen wechseln Feeds zwischen http/https, mit und ohne
    "www." und haengen Kampagnenparameter an.
    """
    teile = urlsplit((url or "").strip().lower())
    host = teile.netloc.removeprefix("www.")
    pfad = teile.path.rstrip("/")
    query = "&".join(sorted(t for t in teile.query.split("&")
                            if t and not t.startswith(_TRACKING)))
    return f"{host}{pfad}" + (f"?{query}" if query else "")


def _klartext(text: str) -> str:
    """Ueberschrift als Text, nicht als Quelltext.

    Die Titel der `moves` kommen woertlich aus dem Feed, und manche Feeds
    liefern ihre Entitaeten doppelt kodiert ("Samsung Galaxy Z8-Serie bei
    1&amp;1"). Jinja escaped beim Einsetzen erneut, auf der Seite stuende
    also "1&amp;1". Einmal aufloesen, dann escapt die Vorlage genau einmal.
    """
    return " ".join(html_lib.unescape(text or "").split())


# Die Notiz ohne den Vodafone-Ratschlag. Die Regel selbst und ihr
# Handwerkszeug stehen in textwerkzeug - dieselbe Frage stellt sich auf der
# Differenzierungs-Seite noch einmal, dort nur mit einer anderen Antwort.
_ohne_vodafone_teil = ohne_vodafone_teil


def _matcher(begriffe) -> list[re.Pattern]:
    """Wortgrenzen-Muster je Name/Alias - dieselbe Regel wie in
    analyze/competitors.py. Ohne die Grenzen faende "O2" jedes "CO2"."""
    muster = []
    for t in begriffe:
        t = (t or "").strip()
        if len(t) >= 2:
            muster.append(re.compile(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)"))
    return muster


def _gehoert_dazu(h: dict, muster: list[re.Pattern]) -> bool:
    """Gehoert diese Meldung zu diesem Wettbewerber?

    Steht ein Absender in der Meldung, muss der Name des Wettbewerbers am
    ANFANG dieses Absenders stehen. Das ist der ganze Unterschied zwischen
    einer Wettbewerbsseite und einer Volltextsuche: gemessen an 14 Wochen
    Archiv zog der blosse Alias "Telekom" auch "A1 Telekom Austria" und
    "Turk Telekom" in die Chronik der Deutschen Telekom - zwei Konzerne, die
    ihr nicht gehoeren. "T-Mobile US" und "T-Mobile (Polen)" bleiben, sie
    beginnen mit dem Namen.

    Nur wenn die Meldung KEINEN Absender traegt (branchenweite Meldungen -
    `_flatten()` leert dort die Platzhalter des Analysten), entscheidet die
    Ueberschrift.
    """
    absender = " ".join((h.get("operator") or "").split()).lower()
    if absender:
        return any(p.match(absender) for p in muster)
    text = f"{h.get('title') or ''} {h.get('headline') or ''}".lower()
    return any(p.search(text) for p in muster)


def _konzern_teile(group: str) -> list[str]:
    """Die Eigentuemer aus dem `group`-Feld einer Promo-Marke.

    `group` nennt Mutterkonzern oder Markenfamilie, manchmal mehrere durch
    "/" getrennt ("1&1 / Drillisch"). Teile, die ein NETZ benennen, zaehlen
    nicht: ALDI TALK steht als "MEDION / Telefónica-Netz" in der Config und
    sendet ueber Telefónica - es gehoert deswegen nicht Telefónica, und
    Penny Mobil ("Telekom-Netz (D1)") gehoert nicht der Telekom. Wer das
    verwechselt, schreibt einem Wettbewerber fremde Aktionen zu.
    """
    teile = [t.strip() for t in (group or "").split("/")]
    return [t for t in teile if t and "netz" not in t.lower()]


def _marken(sources, muster: list[re.Pattern]) -> set[str]:
    """Die Promo-Marken, die zu diesem Wettbewerber gehoeren."""
    treffer = set()
    for src in sources or []:
        if getattr(src, "internal_reference", False):
            continue
        kandidaten = _konzern_teile(getattr(src, "group", "") or "") \
            or [getattr(src, "name", "") or ""]
        if any(p.match(k.lower()) for k in kandidaten for p in muster):
            treffer.add(getattr(src, "name", "") or "")
    return treffer


def _aktion(eintrag: dict) -> dict:
    """Ein Angebot als Zeile - Marke, Schlagzeile, Mechanik, Link.

    Ohne den Score, mit dem die Promo Uebersicht dieselben Angebote sortiert:
    er ist eine Zahl von 0 bis 100 auf einer Skala, die diese Seite nicht
    erklaert, und eine unerklaerte Zahl ist fuer die Zielgruppe Jargon
    (CLAUDE.md §8). Sortiert wird trotzdem danach - die Reihenfolge sagt
    dasselbe, ohne es zu behaupten.
    """
    return {
        "marke": eintrag.get("brand") or "",
        "headline": eintrag.get("headline") or "",
        "url": eintrag.get("url") or "",
        "mechanik": MECHANICS.get(eintrag.get("mechanic") or "", ""),
    }


def _chronik_eintrag(datum: str, rubrik: str, titel: str, url: str,
                     note: str, quelle: str, herkunft: str) -> dict:
    # `tag` steht als Zeilenmarke ueber der Schlagzeile ("7.8."). Bis zum
    # 08.08.2026 stand dort nur die Tageszahl, und sie wurde bei
    # Wiederholung ausgeblendet - das ging, solange die Chronik EINE Spalte
    # war. In zwei Spalten (siehe die Vorlage) zerreisst ein Spaltenumbruch
    # jede solche Gruppe: oben in Spalte zwei stuenden Meldungen ohne Datum.
    # Jede Zeile traegt ihr Datum deshalb selbst, dafuer kurz und leise.
    return {"datum": datum, "monat": datum[:7],
            "tag": f"{int(datum[8:10])}.{int(datum[5:7])}.",
            "rubrik": rubrik or "Sonstiges", "titel": _klartext(titel),
            "url": url, "note": _ohne_vodafone_teil(note), "quelle": quelle,
            "herkunft": herkunft}


def _nach_monaten(eintraege: list[dict]) -> list[dict]:
    """Die Chronik in Monatsgruppen, neueste zuerst.

    Innerhalb eines Monats ebenfalls neueste zuerst; bei gleichem Tag bleibt
    die Reihenfolge, in der die Eintraege entstanden sind - also nach
    Dringlichkeit (`_flatten()` sortiert danach) und danach die Moves des
    Profils. Nach Titel zu sortieren war die erste Fassung und ergab eine
    Tagesgruppe in umgekehrter Alphabetfolge, was nach nichts sortiert
    aussieht. Pythons `sorted` ist stabil, `reverse=True` dreht gleiche
    Schluessel nicht mit.

    Die Gruppierung ist das, was die Seite mit wachsender Historie tragbar
    haelt: der laufende Monat steht offen, alles davor klappt die Vorlage zu.
    """
    gruppen: dict[str, list[dict]] = {}
    for e in sorted(eintraege, key=lambda e: e["datum"], reverse=True):
        gruppen.setdefault(e["monat"], []).append(e)
    monate = []
    for monat in sorted(gruppen, reverse=True):
        eintraege_monat = gruppen[monat]
        monate.append({"monat": monat, "eintraege": eintraege_monat,
                       "n": len(eintraege_monat),
                       # Der offene Monat zeigt seinen Anfang und haelt den
                       # Rest bereit, siehe _OFFEN_JE_MONAT.
                       "offen": eintraege_monat[:_OFFEN_JE_MONAT],
                       "rest": eintraege_monat[_OFFEN_JE_MONAT:]})
    return monate


def _hebel_je_wettbewerber(bestand, muster, theme_label: dict) -> list[dict]:
    """Die Differenzierungs-Hebel, die DIESER Wettbewerber zieht.

    Damit wird die Wettbewerbsseite zu dem, was Klue als Battlecard verkauft -
    nur aus vorhandenen Daten abgeleitet: Positionierung (Lage), laufende
    Aktionen, letzte Moves, Differenzierungs-Hebel. Bis zum 08.08.2026 lagen
    die Hebel eine Seite weiter und waren dort nach THEMA sortiert, also
    genau nicht nach der Frage "was macht dieser eine Anbieter".
    """
    je_hebel: dict[str, dict] = {}
    for e in (bestand or []):
        absender = " ".join(str(e.get("operator") or e.get("company")
                                or e.get("source") or "").split()).lower()
        # Der Name muss am ANFANG des Absenders stehen - dieselbe Regel wie
        # in `_gehoert_dazu`. Ohne sie zog der Alias "Telekom" auch
        # "A1 Telekom Austria" und "Turk Telekom" in dieses Profil.
        if not (absender and any(p.match(absender) for p in muster)):
            continue
        key = str(e.get("theme") or "")
        if not key:
            continue
        h = je_hebel.setdefault(key, {"key": key,
                                      "label": theme_label.get(key, key),
                                      "n": 0, "beispiel": "", "url": ""})
        h["n"] += 1
        if not h["beispiel"]:
            # `what` ist das Feld der Differenzierungs-Bibliothek ("was
            # dieser Anbieter tut"); `headline`/`summary` gibt es dort NICHT -
            # ohne diese Zuordnung blieb die Beispielzeile leer, und der
            # Hebel stand als nackte Zahl da.
            h["beispiel"] = " ".join(str(
                e.get("what") or e.get("headline") or e.get("title")
                or e.get("summary") or "").split())[:120]
            h["url"] = e.get("url") or ""
    return sorted(je_hebel.values(), key=lambda h: (-h["n"], h["label"]))


def build_wettbewerb_view(wochen: list[dict], focus: list[dict],
                          promo_entries=(), promo_sources=(),
                          diff_bestand=(), theme_label=None) -> dict:
    """Baut die Anzeigedaten der Wettbewerbsseite aus dem Berichtsarchiv.

    `wochen` ist je Berichtswoche ein Wörterbuch mit `date`, den bereits
    aufbereiteten `highlights` (siehe html._flatten) und den `competitors`
    dieser Woche. Die Reihenfolge ist egal, hier wird nach Datum sortiert.

    `focus` sind die Fokus-Wettbewerber aus der Konfiguration (Name +
    Aliase). Fehlt sie - etwa beim Rendern ohne Config -, folgt die Seite
    den Profilen des letzten Laufs, statt leer zu bleiben.
    """
    wochen = sorted((w for w in wochen if w.get("date")),
                    key=lambda w: w["date"])
    if not focus:
        letzte = wochen[-1] if wochen else {}
        focus = [{"name": c.get("name")}
                 for c in (letzte.get("competitors") or []) if c.get("name")]

    aktive_angebote = [e for e in (promo_entries or [])
                       if e.get("status") == "aktiv"]

    wettbewerber = []
    for eintrag in focus:
        name = (eintrag.get("name") or "").strip()
        if not name:
            continue
        muster = _matcher([name] + list(eintrag.get("aliases") or []))

        chronik: dict[str, dict] = {}
        summary, profil_datum = "", ""
        themen_verlauf: list[dict] = []
        fehler, fehler_datum = "", ""
        for woche in wochen:
            datum = woche["date"]
            # Die Meldungen der Woche ZUERST, die Profil-Moves danach: beide
            # Quellen nennen dieselbe Meldung, aber die Meldung traegt die
            # vom Analysten geschriebene deutsche Schlagzeile, der Move die
            # Originalueberschrift des Feeds ("DT has 'not yet decided' on EU
            # gigafactory bid"). Fuer eine Leserschaft ohne
            # Technikhintergrund ist das der ganze Unterschied. Das Datum
            # bleibt davon unberuehrt - es ist in beiden Faellen dasselbe.
            for h in (woche.get("highlights") or []):
                if not _gehoert_dazu(h, muster):
                    continue
                url = h.get("url") or ""
                schluessel = _norm_url(url) or (h.get("schlagzeile") or "")
                if not schluessel or schluessel in chronik:
                    continue
                titel = h.get("schlagzeile") or h.get("title") or ""
                note = h.get("de_title") or ""
                chronik[schluessel] = _chronik_eintrag(
                    datum, h.get("category") or "", titel, url,
                    "" if note == titel else note,
                    h.get("source_domain") or h.get("source_label") or "",
                    "meldung")

            profil = next((c for c in (woche.get("competitors") or [])
                           if (c.get("name") or "").strip() == name), None)
            if profil:
                if profil.get("summary"):
                    summary = profil["summary"]
                    profil_datum = datum
                if profil.get("themes"):
                    themen_verlauf.append(
                        {"datum": datum,
                         "themen": [str(t) for t in profil["themes"]][:_MAX_THEMEN_JE_WOCHE]})
                # Der Fehler des JEWEILS letzten Laufs - ein Teilausfall
                # darf nicht aussehen wie ein ruhiger Wettbewerber.
                fehler, fehler_datum = (profil.get("error") or ""), datum
                for m in (profil.get("moves") or []):
                    url = m.get("url") or ""
                    schluessel = _norm_url(url) or (m.get("title") or "")
                    if not schluessel or schluessel in chronik:
                        continue
                    chronik[schluessel] = _chronik_eintrag(
                        datum, m.get("category") or "", m.get("title") or "",
                        url, m.get("note") or "",
                        urlsplit(url).netloc.removeprefix("www."), "profil")

        # Neueste Woche zuerst, und nur so weit zurueck, wie eine
        # Entwicklung ablesbar ist. Die oberste Zeile IST der aktuelle Stand -
        # sie ein zweites Mal als Etikettenreihe daneben zu setzen, waere
        # dieselbe Information in zwei Formen.
        themen_verlauf = list(reversed(themen_verlauf))[:_MAX_THEMENWOCHEN]

        marken = _marken(promo_sources, muster)
        angebote = [e for e in aktive_angebote if (e.get("brand") or "") in marken]
        angebote.sort(key=lambda e: (e.get("highlight") is True,
                                     e.get("score") is not None,
                                     e.get("score") or 0), reverse=True)

        eintraege = list(chronik.values())
        wettbewerber.append({
            "name": name,
            "anker": anker(name),
            "summary": summary,
            "profil_datum": profil_datum,
            "themen_verlauf": themen_verlauf,
            "fehler": fehler,
            "fehler_datum": fehler_datum,
            "monate": _nach_monaten(eintraege),
            "n_chronik": len(eintraege),
            # Seit wann diese Chronik reicht - das Datum der AELTESTEN
            # Aufnahme, nicht der Beobachtungsbeginn des Projekts.
            "seit": min((e["datum"] for e in eintraege), default=""),
            "aktionen": [_aktion(e) for e in angebote[:_MAX_AKTIONEN]],
            "aktionen_n": len(angebote),
            "marken": sorted(marken),
            "hebel": _hebel_je_wettbewerber(diff_bestand, muster,
                                            theme_label or {}),
        })

    # Offene Flanken: Hebel, die ein ANDERER Fokus-Wettbewerber zieht und
    # dieser nicht. Erst im Nachgang berechenbar - vorher steht nicht fest,
    # was die anderen ziehen. Bewusst nur gegen die Fokus-Wettbewerber und
    # nicht gegen den Weltbestand: "Telkomsel hat das auch" ist im deutschen
    # Markt keine Flanke.
    alle_hebel = {h["key"]: h["label"] for c in wettbewerber
                  for h in c.get("hebel") or []}
    for c in wettbewerber:
        eigene = {h["key"] for h in c.get("hebel") or []}
        c["flanken"] = [{"key": k, "label": alle_hebel[k],
                         "wer": sorted(
                             a["name"] for a in wettbewerber
                             if any(h["key"] == k
                                    for h in a.get("hebel") or []))}
                        for k in alle_hebel if k not in eigene]
        c["flanken"].sort(key=lambda f: (-len(f["wer"]), f["label"]))

    return {
        "wettbewerber": wettbewerber,
        # Der Ausgabetag der juengsten Woche - mehr braucht der Seitenkopf
        # nicht. Ein "seit ..." und eine Zahl der Ausgaben standen hier
        # ebenfalls; beide sagt die Kopfzeile jedes Wettbewerbers genauer
        # ("56 Meldungen seit 16. Juli 2026"), und was keine Vorlage liest,
        # wird in dieser Codebasis nicht berechnet.
        "stand": wochen[-1]["date"] if wochen else "",
        # Ohne Promo-Konfiguration (render_site() ohne cfg) gibt es keine
        # Aktionslage - dann zeigt die Seite die Spalte gar nicht, statt
        # "keine Aktion bestaetigt" zu behaupten, wo nichts geprueft wurde.
        "promo_bekannt": bool(promo_sources),
    }
