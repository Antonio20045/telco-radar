"""Redaktion fuer den globalen Differenzierungsbericht.

Der Bericht beschreibt konkrete Angebote und Projekte von Telkos jenseits von
Netzausbau, Tarifen und Preisen. Er ist keine Vodafone-Empfehlung und spricht
nicht ueber interne Entscheidungen, sondern ordnet beobachtete Beispiele
neutral und quellengebunden ein.
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

Antworte ausschliesslich mit sauberem Markdown, ohne H1 und ohne Vorwort.
Verwende exakt diese H2-Ueberschriften:

## Das Wichtigste
Ein klarer Einstieg mit 2 bis 4 kurzen Absaetzen. Verdichte die auffaelligsten
Entwicklungen im aktuellen Beobachtungszeitraum und verlinke jede konkrete
Aussage ueber einen Betreiber direkt mit der passenden Quelle.

## Wie sich Differenzierung aktuell zeigt
Schreibe hier 3 bis 5 zusammenhaengende Abschnitte in gut lesbaren Absaetzen.
Ordne mehrere Beispiele pro Absatz nach einer gemeinsamen Idee und verknuepfe
sie miteinander. Keine H3-Ueberschriften pro Betreiber, keine Aufzaehlung von
Einzelartikeln und keine Artikelzusammenfassungen hintereinander. Ein Beispiel
ist nur ein Beleg fuer die uebergeordnete Beobachtung. Jede konkrete Aussage
bekommt einen passenden Quellenlink.

## Welche Muster dahinter liegen
Beschreibe 3 bis 5 neutrale, globale Muster, die sich aus den Beispielen
ergeben. Zum Beispiel: Premium-Dienste werden Teil des Tariferlebnisses,
Schutz wird zum Markenversprechen, oder die Telko-App wird zum Zugang zu
mehreren Alltagsdiensten. Belege die Muster mit konkreten Beispielen und
Quellenlinks. Keine Bewertung und keine Empfehlung.

## Quellenbasis
Liste die wichtigsten verwendeten Beispiele als
[Betreiber – Kurzbezeichnung](URL), mit Region und, falls vorhanden, Datum.

Regeln:
- Jede konkrete Aussage ueber einen Betreiber muss einen Link auf eine
  exakte URL aus den gelieferten Daten tragen.
- Keine Vodafone-Empfehlungen, keine Handlungsaufforderungen, kein
  „Fuer Vodafone“, kein „Vodafone sollte“ und kein „Vodafone koennte“.
- Nicht nur Links aufzählen: Die Beispiele muessen in einem lesbaren Bericht
  erklaert und miteinander in Beziehung gesetzt werden.
- Maximal etwa 1.200 Woerter.
"""


_REQUIRED_HEADINGS = (
    "## das wichtigste",
    "## wie sich differenzierung aktuell zeigt",
    "## welche muster dahinter liegen",
    "## quellenbasis",
)
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


def build_digest(entries: list[dict], theme_labels: dict[str, str]) -> str:
    """Build a neutral, source-linked report without an LLM."""
    entries = [e for e in entries if e.get("url") and e.get("what")]
    by_theme: dict[str, list[dict]] = {}
    for entry in entries:
        by_theme.setdefault(entry.get("theme") or "_", []).append(entry)
    ordered = sorted(entries, key=lambda e: (e.get("last_verified") or "",
                                             e.get("first_seen") or ""),
                     reverse=True)
    def examples(keys: tuple[str, ...], limit: int = 3) -> list[dict]:
        result = []
        seen = set()
        for entry in ordered:
            if entry.get("theme") not in keys:
                continue
            identity = (entry.get("operator"), entry.get("what"))
            if identity in seen:
                continue
            result.append(entry)
            seen.add(identity)
            if len(result) >= limit:
                break
        return result

    def linked_examples(items: list[dict]) -> str:
        labels = {
            "ki": "einen KI-Dienst als Bestandteil des Kundenangebots",
            "entertainment": "Streaming als Bestandteil ausgewählter Tarife",
            "cloud": "Cloud-Speicher als integrierte Leistung",
            "gaming": "Cloud-Gaming als gebündelte Leistung",
            "garantie": "eine mehrjährige Preis- oder Ausfallgarantie",
            "security": "Scam- und Spam-Schutz im Telekommunikationsdienst",
            "health": "digitale Gesundheits- und Telemedizin-Dienste",
            "geraete": "ein Upgrade- oder Inzahlungnahmeprogramm für Geräte",
            "loyalty": "Vorteile, Gewinnspiele oder Ticket-Presales",
            "superapp": "eine App als Zugang zu mehreren Alltagsdiensten",
            "fintech": "Bezahlen und Finanzdienste in der Kunden-App",
            "smarthome": "Smart-Home-Steuerung und Sicherheit am Anschluss",
        }
        clauses = [
            f"{entry.get('operator') or 'Ein Betreiber'} nutzt {labels.get(entry.get('theme'), 'ein ergänzendes Kundenerlebnis')} {_source_link(entry)}"
            for entry in items
        ]
        if not clauses:
            return ""
        if len(clauses) == 1:
            return clauses[0] + "."
        if len(clauses) == 2:
            return clauses[0] + " und " + clauses[1] + "."
        return ", ".join(clauses[:-1]) + " und " + clauses[-1] + "."

    lines = ["## Das Wichtigste", ""]
    if ordered:
        lines.append(
            "Im Markt verschiebt sich Differenzierung sichtbar vom reinen "
            "Netzzugang hin zu zusätzlichen Kundenerlebnissen. Telkos machen "
            "Dienste, Schutzversprechen und digitale Zugänge zu einem Teil des "
            "laufenden Angebots – etwa indem sie KI-Assistenten, Streaming oder "
            "Cloud-Speicher mit dem Mobilfunk- oder Breitbandprodukt verbinden.")
        lines.append(
            "Auffällig ist dabei die Spannweite der Ansätze: Manche Anbieter "
            "bündeln etablierte digitale Leistungen, andere bauen eigene "
            "Ökosysteme, Serviceversprechen oder Geräteprogramme auf. Die "
            "folgende Einordnung verbindet diese konkreten Marktbeispiele, "
            "statt sie nur einzeln nebeneinanderzustellen.")
    else:
        lines.append("Der aktuelle Beobachtungszeitraum enthält noch kein belegtes Beispiel.")

    lines += ["", "## Wie sich Differenzierung aktuell zeigt", ""]
    narrative_groups = (
        (
            "Dienste statt Rabatte.",
            "KI, Entertainment und Cloud werden als laufender Bestandteil des "
            "Kundenerlebnisses eingesetzt. Anbieter bündeln beispielsweise "
            "Perplexity-Zugänge oder integrieren KI direkt in ihre Kunden-App. "
            "Parallel machen mehrere Netzbetreiber Streaming-Dienste zu einem "
            "sichtbaren Bestandteil ausgewählter Tarife.",
            ("ki", "entertainment", "cloud", "gaming"),
        ),
        (
            "Vertrauen und Schutz als Leistung.",
            "Ein zweiter Strang ist die Übersetzung von Sicherheit und Verlässlichkeit "
            "in ein konkretes Versprechen. Mehrjährige Preis- oder Ausfallgarantien "
            "stehen neben integriertem Scam- und Spam-Schutz; auch Health-Angebote "
            "erweitern das Leistungsbild über Konnektivität hinaus.",
            ("garantie", "security", "health"),
        ),
        (
            "Geräte und Alltag bleiben im Ökosystem.",
            "Differenzierung entsteht außerdem dort, wo die Beziehung zum Kunden über "
            "den einzelnen Mobilfunkvertrag hinaus verlängert wird. Geräte-Upgrades, "
            "Vorteilsprogramme, Cloud-Speicher, Bezahldienste und Smart Home halten "
            "den Kundenkontakt an mehreren Stellen aufrecht und machen die Telko zur "
            "Zugangsschicht für weitere Dienste.",
            ("geraete", "loyalty", "superapp", "fintech", "smarthome"),
        ),
    )
    for lead, paragraph, keys in narrative_groups:
        samples = examples(keys, 3)
        if not samples:
            continue
        lines.append(f"**{lead}** {paragraph} " + linked_examples(samples))
        lines.append("")

    lines += ["## Welche Muster dahinter liegen", ""]
    if ordered:
        lines.append(
            "Übergreifend werden digitale Leistungen damit vom optionalen Zusatz zum "
            "wiederkehrenden Bestandteil des Telekommunikationsprodukts. Der Zugang "
            "zu KI, Entertainment oder Speicher wird in Apps, Tarife und "
            "Servicebeziehungen eingebettet. "
            + linked_examples(examples(("ki", "entertainment", "cloud"), 2))
        )
        lines.append(
            "Gleichzeitig wird Vertrauen operationalisiert: Eine Garantie, ein "
            "Sicherheitsdienst oder ein Gesundheitsangebot macht ein abstraktes "
            "Markenversprechen im Alltag greifbar. Das knüpft an Nutzung und "
            "Sicherheit an, nicht nur an den Preis. "
            + linked_examples(examples(("garantie", "security", "health"), 2))
        )
        lines.append(
            "Schließlich zeigt sich ein Plattformmuster. Gerätewechsel, "
            "Vorteilsprogramme, Bezahldienste und Smart Home halten den Kundenkontakt "
            "an mehreren Stellen aufrecht und machen die Telko zur Zugangsschicht für "
            "weitere Dienste. "
            + linked_examples(examples(("geraete", "loyalty", "superapp", "fintech", "smarthome"), 2))
        )
    else:
        lines.append("Weitere Muster werden sichtbar, sobald neue Beispiele bestätigt sind.")

    lines += ["", "## Quellenbasis", ""]
    for entry in ordered[:12]:
        lines.append(f"- {_source_link(entry)}{_date_suffix(entry)}")
    if not ordered:
        lines.append("- Noch keine belegte Quelle vorhanden.")
    return "\n".join(lines).strip() + "\n"
