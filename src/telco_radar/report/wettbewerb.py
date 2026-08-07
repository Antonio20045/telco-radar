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
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

# Wie viele Aktionen je Wettbewerber auf der Seite stehen. Der Rest steht
# vollstaendig auf der Promo Uebersicht, dorthin verweist die Zeile darunter.
_MAX_AKTIONEN = 3
# Wie viele Wochen der Themenverlauf zurueckreicht. Vier Profile zeigen die
# Verschiebung ("Ende Juli Router und Streaming, jetzt Glasfaser und Joyn"),
# ohne dass unter jedem Wettbewerber eine halbe Seite Etiketten steht.
_MAX_THEMENWOCHEN = 4
_MAX_THEMEN_JE_WOCHE = 6

_TRACKING = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")


def _anker(name: str) -> str:
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


def _aktion(eintrag: dict, mechaniken: dict) -> dict:
    return {
        "marke": eintrag.get("brand") or "",
        "headline": eintrag.get("headline") or "",
        "url": eintrag.get("url") or "",
        "mechanik": mechaniken.get(eintrag.get("mechanic") or "", ""),
        "score": eintrag.get("score"),
        "highlight": bool(eintrag.get("highlight")),
    }


def _chronik_eintrag(datum: str, rubrik: str, titel: str, url: str,
                     note: str, quelle: str, herkunft: str) -> dict:
    return {"datum": datum, "monat": datum[:7], "rubrik": rubrik or "Sonstiges",
            "titel": titel, "url": url, "note": note, "quelle": quelle,
            "herkunft": herkunft}


def _nach_monaten(eintraege: list[dict]) -> list[dict]:
    """Die Chronik in Monatsgruppen, neueste zuerst.

    Innerhalb eines Monats ebenfalls neueste zuerst. Die Gruppierung ist
    das, was die Seite mit wachsender Historie tragbar haelt: der laufende
    Monat steht offen, alles davor klappt die Vorlage zu.
    """
    gruppen: dict[str, list[dict]] = {}
    for e in sorted(eintraege, key=lambda e: (e["datum"], e["titel"]),
                    reverse=True):
        gruppen.setdefault(e["monat"], []).append(e)
    return [{"monat": monat, "eintraege": gruppen[monat], "n": len(gruppen[monat])}
            for monat in sorted(gruppen, reverse=True)]


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
    from ..analyze.promo_ranker import MECHANICS

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
            "anker": _anker(name),
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
            "aktionen": [_aktion(e, MECHANICS) for e in angebote[:_MAX_AKTIONEN]],
            "aktionen_n": len(angebote),
            "marken": sorted(marken),
        })

    return {
        "wettbewerber": wettbewerber,
        "stand": wochen[-1]["date"] if wochen else "",
        "seit": wochen[0]["date"] if wochen else "",
        "n_wochen": len(wochen),
    }
