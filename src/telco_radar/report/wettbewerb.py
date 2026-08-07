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

# Wie viele Aktionen je Wettbewerber auf der Seite stehen. Der Rest steht
# vollstaendig auf der Promo Uebersicht, dorthin verweist die Zeile darunter.
_MAX_AKTIONEN = 3
# Wie viele Wochen der Themenverlauf zurueckreicht. Vier Profile zeigen die
# Verschiebung ("Ende Juli Router und Streaming, jetzt Glasfaser und Joyn"),
# ohne dass unter jedem Wettbewerber eine halbe Seite Etiketten steht.
_MAX_THEMENWOCHEN = 4
_MAX_THEMEN_JE_WOCHE = 6

_TRACKING = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")

# Trennzeichen, an dem die Notiz des Analysten ihre zwei Haelften teilt.
# Das Semikolon steht ohne Leerzeichen davor ("Basisstationen; fuer
# Vodafone"), der Halbgeviertstrich mit ("an - Vodafone") - und ein Bindestrich
# ohne Leerzeichen ist keiner ("Wi-Fi-7-Router").
_TRENNER = re.compile(r"\s*[;–—]\s+|\s+-\s+")


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


def _ohne_vodafone_teil(note: str) -> str:
    """Die Notiz ohne den Vodafone-Ratschlag.

    Die Website berichtet, sie beraet nicht (CLAUDE.md §8; im Wochenbericht
    macht das `_strip_vodafone_advice`). Der Wettbewerber-Prompt verlangt
    aber ausdruecklich "what it is and the angle for Vodafone" in EINEM
    Satz, und 82 von 170 Notizen im Archiv nennen Vodafone. Satzweise
    streichen wuerde die Notiz komplett verwerfen - mitsamt dem Befund.

    Die zwei Haelften sind durch Gedankenstrich oder Semikolon getrennt
    ("Telekom bietet Google One mit Rabatt an – Vodafone muss gegenhalten").
    Steht Vodafone nur hinten, faellt das Hintere weg. Steht der Name auch
    vorn oder gibt es keine Trennstelle, faellt die ganze Notiz - lieber
    keine Einordnung als eine Empfehlung auf einer beobachtenden Seite.
    """
    text = " ".join((note or "").split())
    if "vodafone" not in text.lower():
        return text
    teile = _TRENNER.split(text)
    kopf = teile[0].strip(" ,;–—-")
    if len(teile) > 1 and "vodafone" not in kopf.lower():
        return kopf if kopf.endswith((".", "!", "?")) else kopf + "."
    return ""


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
    # `tag` steht als Zeilenmarke links in der Chronik - der Monat steht
    # ueber der Gruppe, das Jahr in ihrer Ueberschrift.
    return {"datum": datum, "monat": datum[:7], "tag": datum[8:10].lstrip("0"),
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
        # Die Tageszahl steht nur beim ERSTEN Eintrag ihres Tages. Ein
        # Lauftag bringt zehn bis dreissig Meldungen mit; zwanzigmal
        # untereinander dieselbe "7." zu setzen macht aus einer Zeilenmarke
        # ein Muster, das man wegsieht.
        letzter = ""
        for e in gruppen[monat]:
            e["tag_zeigen"] = e["datum"] != letzter
            letzter = e["datum"]
        monate.append({"monat": monat, "eintraege": gruppen[monat],
                       "n": len(gruppen[monat])})
    return monate


def build_wettbewerb_view(wochen: list[dict], focus: list[dict],
                          promo_entries=(), promo_sources=()) -> dict:
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
        })

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
