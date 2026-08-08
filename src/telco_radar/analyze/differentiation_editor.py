"""Redaktion fuer den globalen Differenzierungsbericht.

Der Bericht beschreibt konkrete Angebote und Projekte von Telkos jenseits von
Netzausbau, Tarifen und Preisen. Er ist keine Vodafone-Empfehlung und spricht
nicht ueber interne Entscheidungen, sondern ordnet beobachtete Beispiele
neutral und quellengebunden ein.

**Die Gliederung ist am 08.08.2026 gewechselt, und der Grund ist nicht
Geschmack.** Bis dahin verlangte der Prompt "einen direkten Bericht aus 4 bis 6
zusammenhaengenden Absaetzen ... beginne sofort mit konkreten Betreibern,
Angeboten und Projekten" plus eine Rubrik "Quellenbasis". Herausgekommen ist,
was so ein Auftrag hergibt: Absaetze von 2000 Zeichen, in denen zwoelf Moves
mit Semikolon aneinandergereiht sind - und damit exakt derselbe Inhalt, den die
Differenzierungs-Seite darueber schon als Karten zeigt, nur ohne Bild und ohne
Gliederung. Ein Bericht, der die Liste unter ihm nacherzaehlt, ist kein
Bericht. Antonio: *"nicht einfach so reinpasten, dieser eine lange Bereich ...
das muss intelligent sein."*

Der Redakteur schreibt jetzt das, was die Karten NICHT zeigen koennen, und er
schreibt es in drei Teilen, die die Seite an drei verschiedenen Stellen
einsetzt (`report/differenzierung_bericht.zerlegen`):

    ## Das Bild      die Lage in wenigen Saetzen - steht im Seitenkopf.
    ## Muster        die wiederkehrenden Muster - steht neben dem gerechneten
                     Marktbild.
    ## Einordnung    je Hebel ein Absatz unter einer H3 mit dem Hebel-Namen -
                     steht direkt ueber den Beispielen dieses Hebels.

`validate_briefing`, `build_digest` und `report/differenzierung_bericht.py`
haengen an derselben Gliederung. Wer eine Ueberschrift aendert, aendert alle
drei - sonst faellt der Bericht still auf den Notfall-Digest zurueck (dieselbe
Kopplung wie beim Wochen-Editor, CLAUDE.md §6).
"""
from __future__ import annotations

import json
import logging
import re

from .llm import complete

log = logging.getLogger(__name__)


class DifferentiationBriefingError(RuntimeError):
    """Raised when the differentiation editor returns unusable Markdown."""


DIFFERENTIATION_EDITOR_SYSTEM = """\
Du bist der Spezial-Redakteur fuer einen deutschsprachigen globalen
Differenzierungsbericht ueber Telekommunikationsunternehmen.

Der Bericht beantwortet eine einfache Frage: Welche konkreten Angebote,
Programme und Projekte nutzen Telkos weltweit, um sich jenseits von
Netzausbau, 5G, Tarifen und Preisen abzuheben? Interessant sind zum Beispiel
Premium-KI als Kundenvorteil, Garantien und Service-Versprechen,
Geraeteprogramme, Streaming, Betrugsschutz, Cloud, Fintech, Super-Apps,
Loyalty-Programme, Smart Home und Health-Angebote.

Die Leser wollen globale Marktbeobachtung. Schreibe deshalb nicht ueber eine
interne Vodafone-Strategie und gib keinerlei Empfehlungen, Handlungstipps
oder naechste Schritte fuer Vodafone. Verwende auch keine Formulierungen wie
„Vodafone sollte“, „Vodafone koennte“, „Fuer Vodafone“ oder „Empfehlung“.

Nutze ausschliesslich die gelieferten, belegten Eintraege. Erfinde keine
Zahlen, Zeitpunkte, Partnerschaften oder Wirkungen. Wenn ein Datum fehlt,
lasse es weg. Erklaere Fachbegriffe kurz, wenn sie fuer das Verstaendnis
noetig sind. Schreibe anschaulich: „bietet Kunden“, „buendelt“, „integriert“,
„garantiert“, „schuetzt“ und „macht ... zum Bestandteil des Angebots“.
Verwende nicht den abstrakten Begriff „Sammlung“ und nenne keine Anzahl von
Moves, Eintraegen, Kategorien oder Quellen als Selbstzweck.

WICHTIG: Jedes gelieferte Beispiel steht auf der Seite bereits als eigene Karte
mit Betreiber, Beschreibung, Quelle und Bild. Zaehle die Beispiele deshalb NICHT
noch einmal auf. Dein Text beantwortet, was eine Kartenliste nicht beantworten
kann: Was faellt ueber die Beispiele hinweg auf? Was tun mehrere Betreiber
gleichzeitig? Wo unterscheiden sich Regionen? Was ist neu gegenueber dem, was
schon laenger laeuft?

Antworte ausschliesslich mit sauberem Markdown, ohne H1 und ohne Vorwort.
Verwende exakt diese drei H2-Ueberschriften, in dieser Reihenfolge:

## Das Bild
Drei bis fuenf Saetze, ein einziger Absatz: Was zeigt der Bestand insgesamt?
Nenne dabei zwei bis drei Betreiber als Beleg mit Quellenlink, aber schreibe
keine Liste. Beginne nicht mit einer Definition von „Differenzierung“.

## Muster
Zwei bis vier Absaetze. Jeder beginnt mit einem kurzen fettgedruckten
Musterwort und beschreibt dann in zwei bis drei Saetzen EIN wiederkehrendes
Muster - etwas, das mehrere Betreiber unabhaengig voneinander tun. Belege jedes
Muster mit mindestens zwei Betreibern und ihren Quellenlinks. Ein Muster, das
nur ein einziger Betreiber zeigt, ist kein Muster - lass es weg.

## Einordnung
Je Hebel eine H3-Ueberschrift mit GENAU dem Hebel-Namen aus dem Feld „thema“,
darunter zwei bis drei Saetze: Was ist an diesem Hebel gerade charakteristisch,
und wer treibt ihn? Nimm nur Hebel auf, zu denen die Daten mehr hergeben als
ein einzelnes Beispiel. Ein Hebel, zu dem du nichts Eigenstaendiges sagen
kannst, wird ausgelassen - nicht mit einem Satz gefuellt.

Regeln:
- Jede konkrete Aussage ueber einen Betreiber muss einen Link auf eine
  exakte URL aus den gelieferten Daten tragen.
- Keine Vodafone-Empfehlungen, keine Handlungsaufforderungen, kein
  „Fuer Vodafone“, kein „Vodafone sollte“ und kein „Vodafone koennte“.
- Keine Aufzaehlung der Einzelbeispiele, keine Bulletpoints, keine
  Quellenliste am Ende - die Seite zeigt die Quellen bereits.
- H3 nur unter „## Einordnung“, und dort nur mit einem Hebel-Namen.
- Maximal etwa 700 Woerter. Kuerzer ist besser.
"""


_REQUIRED_HEADINGS = (
    "## das bild",
    "## muster",
    "## einordnung",
)
# Ab hier ist ein Absatz keine Prosa mehr, sondern eine Aufzaehlung mit
# Semikolons. Gemessen ohne die Markdown-Links, sonst schlaegt schon ein
# normaler Absatz mit drei Belegen an.
_MAX_ABSATZ_ZEICHEN = 1200
_FORBIDDEN_EDITORIAL_PHRASES = (
    "fuer vodafone", "für vodafone", "vodafone sollte", "vodafone könnte",
    "vodafone koennte", "vodafone muss", "empfehlung", "handlungsaufforderung",
)


def _heading_key(line: str) -> str:
    return (line.strip().lower().replace("ä", "ae").replace("ö", "oe")
            .replace("ü", "ue").replace("ß", "ss"))


def _without_links(markdown: str) -> str:
    """Remove Markdown links before checking editorial wording."""
    return re.sub(r"\[[^\]]*\]\([^)]*\)", "", markdown).lower()


def validate_briefing(markdown: str) -> None:
    """Reject an answer with the wrong structure or Vodafone advice."""
    headings = {_heading_key(line) for line in markdown.splitlines()
                if line.strip().startswith("## ")}
    missing = set(_REQUIRED_HEADINGS) - headings
    if missing:
        raise DifferentiationBriefingError(
            "Differenzierungsbericht unvollstaendig: " + ", ".join(sorted(missing)))
    if "[" not in markdown or "](" not in markdown:
        raise DifferentiationBriefingError(
            "Differenzierungsbericht enthaelt keine Quellenlinks")
    plain = _without_links(markdown)
    if any(phrase in plain for phrase in _FORBIDDEN_EDITORIAL_PHRASES):
        raise DifferentiationBriefingError(
            "Differenzierungsbericht enthaelt eine Vodafone-Empfehlung")
    # Der Rueckfall in die Aufzaehlung ist der wahrscheinlichste Fehlgriff:
    # das Modell bekommt 71 Beispiele geliefert und die alte Fassung hat sie
    # brav alle in einen Absatz gehaengt (gemessen am Bericht vom 07.08.2026:
    # 2 100 Zeichen in einem einzigen Absatz, zwoelf Moves mit Semikolon
    # getrennt). Ein Absatz dieser Laenge ist auf der Seite kein Text mehr,
    # sondern eine Wand - und genau der Zustand, den diese Gliederung ersetzt.
    zu_lang = [a for a in re.split(r"\n\s*\n", _without_links(markdown))
               if len(a.strip()) > _MAX_ABSATZ_ZEICHEN]
    if zu_lang:
        raise DifferentiationBriefingError(
            f"Differenzierungsbericht hat {len(zu_lang)} Absatz/Absaetze ueber "
            f"{_MAX_ABSATZ_ZEICHEN} Zeichen - vermutlich wieder eine Aufzaehlung")


def _payload(entries: list[dict], theme_labels: dict[str, str]) -> str:
    rows = []
    for e in entries:
        rows.append({
            "thema": theme_labels.get(e.get("theme"), e.get("theme") or ""),
            "betreiber": e.get("operator") or "",
            "region": e.get("region") or "",
            "konkretes_beispiel": e.get("what") or "",
            "quelle": e.get("url") or "",
            "quellendom": e.get("source") or "",
            "datum": e.get("date") or "",
            "zuletzt_geprueft": e.get("last_verified") or "",
        })
    return json.dumps(rows, ensure_ascii=False)


def synthesize(entries: list[dict], theme_labels: dict[str, str], model: str,
               language: str = "Deutsch") -> str:
    """Run the dedicated market-observation editor and validate its Markdown."""
    if not entries:
        return build_digest(entries, theme_labels)
    raw = complete(
        DIFFERENTIATION_EDITOR_SYSTEM + f"\nBerichtssprache: {language}.",
        _payload(entries, theme_labels), model=model, max_tokens=4200)
    markdown = raw.strip()
    validate_briefing(markdown)
    return markdown


def _source_link(entry: dict) -> str:
    operator = entry.get("operator") or entry.get("source") or "Betreiber"
    url = entry.get("url") or ""
    label = entry.get("source") or "Quelle"
    return f"[{operator} – {label}]({url})"


def _date_suffix(entry: dict) -> str:
    date = entry.get("date")
    region = entry.get("region")
    bits = [str(x) for x in (region, date) if x]
    return " · " + " · ".join(bits) if bits else ""


def _anbieter(entry: dict) -> list[str]:
    """Die einzelnen Betreiber eines Beispiels - ein Joint Venture von fuenf
    Konzernen steht als ein Feld mit Kommata da."""
    return [t.strip() for t in str(entry.get("operator") or "").split(",")
            if t.strip()]


def _aufzaehlung(namen: list[str]) -> str:
    if not namen:
        return ""
    if len(namen) == 1:
        return namen[0]
    return ", ".join(namen[:-1]) + " und " + namen[-1]


def build_digest(entries: list[dict], theme_labels: dict[str, str]) -> str:
    """Der Bericht ohne LLM - in derselben Gliederung wie die KI-Redaktion.

    Er beschreibt, was sich aus dem Bestand RECHNEN laesst (wie viele
    Beispiele, welcher Hebel wie stark, wer mehrere Hebel bespielt) und
    belegt jede Aussage mit Quellen. Was er nicht kann, behauptet er nicht.

    Er muss dieselbe Gliederung schreiben wie der Prompt, weil die Seite ihn
    genauso zerlegt (report/differenzierung_bericht.py). Faellt der Redakteur
    aus, aendert sich der Ton der Seite, nicht ihr Aufbau.
    """
    entries = [e for e in entries if e.get("url") and e.get("what")]
    ordered = sorted(entries, key=lambda e: (e.get("last_verified") or "",
                                             e.get("first_seen") or ""),
                     reverse=True)

    if not ordered:
        return ("## Das Bild\n\n"
                "Im aktuellen Beobachtungszeitraum liegt noch kein belegtes "
                "Beispiel vor.\n\n"
                "## Muster\n\nNoch kein Muster belegbar.\n\n"
                "## Einordnung\n\n")

    # Je Hebel: die Beispiele, die Anbieter, und ein Beleg je Anbieter.
    je_hebel: dict[str, list[dict]] = {}
    for e in ordered:
        je_hebel.setdefault(e.get("theme") or "", []).append(e)
    nach_groesse = sorted(je_hebel.items(),
                          key=lambda p: (len(p[1]), p[0]), reverse=True)

    alle_anbieter: dict[str, set] = {}
    for e in ordered:
        for name in _anbieter(e):
            alle_anbieter.setdefault(name, set()).add(e.get("theme") or "")
    breit = sorted(alle_anbieter.items(),
                   key=lambda p: (len(p[1]), p[0]), reverse=True)

    def label(key: str) -> str:
        return theme_labels.get(key, key or "Sonstiges")

    def belege(items: list[dict], anzahl: int = 2) -> str:
        """Bis zu `anzahl` Quellenlinks verschiedener Anbieter."""
        gesehen: set[str] = set()
        links = []
        for e in items:
            name = (_anbieter(e) or ["?"])[0]
            if name in gesehen:
                continue
            gesehen.add(name)
            links.append(_source_link(e))
            if len(links) >= anzahl:
                break
        return ", ".join(links)

    zeilen: list[str] = ["## Das Bild", ""]
    fuehrend = nach_groesse[0]
    regionen = {str(e.get("region") or "").strip() for e in ordered}
    regionen.discard("")
    zeilen.append(
        f"Der Bestand umfasst {len(ordered)} belegte Beispiele von "
        f"{len(alle_anbieter)} Anbietern aus {len(regionen)} Regionen. Am "
        f"stärksten bespielt ist {label(fuehrend[0])} mit "
        f"{len(fuehrend[1])} Beispielen, gefolgt von "
        f"{_aufzaehlung([label(k) for k, _ in nach_groesse[1:3]])}. "
        f"Zuletzt hinzugekommen sind {belege(ordered, 3)}.")
    zeilen.append("")

    zeilen += ["## Muster", ""]
    gefunden = False
    for key, items in nach_groesse[:3]:
        anbieter = {n for e in items for n in _anbieter(e)}
        if len(anbieter) < 2:
            # Ein Hebel, den nur ein Anbieter zieht, ist kein Muster.
            continue
        gefunden = True
        zeilen.append(
            f"**{label(key)}** {len(items)} Beispiele von {len(anbieter)} "
            f"Anbietern, darunter {belege(items, 2)}.")
        zeilen.append("")
    if breit and len(breit[0][1]) > 1:
        name, hebel = breit[0]
        gefunden = True
        zeilen.append(
            f"**Mehrere Hebel gleichzeitig** {name} taucht in "
            f"{len(hebel)} verschiedenen Hebeln auf: "
            f"{_aufzaehlung([label(k) for k in sorted(hebel)])}.")
        zeilen.append("")
    if not gefunden:
        zeilen += ["Noch zeigt kein Hebel mehr als einen Anbieter - ein "
                   "Muster laesst sich daraus nicht belegen.", ""]

    zeilen += ["## Einordnung", ""]
    for key, items in nach_groesse:
        if len(items) < 2:
            # Ein einzelnes Beispiel steht als Karte, es braucht keinen
            # Einordnungssatz, der es bloss wiederholt.
            continue
        anbieter = sorted({n for e in items for n in _anbieter(e)})
        genannt = anbieter[:4]
        if len(anbieter) > 4:
            # Als eigenes Glied der Aufzaehlung, nicht angehaengt - sonst
            # steht dort "A, B und C und 3 weiteren".
            genannt = genannt + [f"{len(anbieter) - 4} weiteren"]
        zeilen.append(f"### {label(key)}")
        zeilen.append("")
        zeilen.append(
            f"{len(items)} belegte Beispiele, getragen von "
            f"{_aufzaehlung(genannt)}. "
            f"Zuletzt gesehen: {belege(items, 1)}.")
        zeilen.append("")

    return "\n".join(zeilen).strip() + "\n"
