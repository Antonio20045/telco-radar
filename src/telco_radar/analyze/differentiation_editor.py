"""Editor-Agent fuer den woechentlichen Differenzierungsbericht.

Der Agent arbeitet auf der versionierten Differenzierungs-DB, nicht auf den
Roh-Treffern der Websuche. So bleibt der Bericht quellengebunden und kann die
dauerhaft relevanten Moves ueber mehrere Wochen in ein klares Vodafone-Narrativ
verdichten. Ohne LLM entsteht ein deterministischer, ebenfalls belegter
Bericht als Fallback.
"""
from __future__ import annotations

import json
import logging
from collections import Counter

from .llm import complete

log = logging.getLogger(__name__)


class DifferentiationBriefingError(RuntimeError):
    """Raised when the differentiation editor returns unusable Markdown."""


DIFFERENTIATION_EDITOR_SYSTEM = """\
Du bist der Spezial-Editor von „Telco Radar“. Schreibe einen kurzen,
entscheidungsorientierten Differenzierungsbericht fuer Vodafone. Deine
Datenbasis ist eine kuratierte Bibliothek echter, quellenbelegter Moves von
Telekom-Wettbewerbern im Endkundengeschaeft jenseits des Preises: Dienste,
Garantien, Geraete-Programme, KI, Entertainment, Security, Fintech,
Oekosysteme und Kunden-Perks.

Die Leser sind Vodafone-Manager ohne technischen Hintergrund. Schreibe auf
Deutsch, klar und konkret, ohne Marketingfloskeln. Nutze ausschliesslich die
gelieferten Eintraege. Erfinde keine Zahlen, Zeitpunkte, Partnerschaften oder
Vodafone-Produkte. Wenn ein Eintrag kein Datum hat, lasse das Datum weg.

Antworte ausschliesslich mit sauberem Markdown, ohne H1 und ohne Vorwort.
Verwende exakt diese H2-Ueberschriften:

## Auf einen Blick
Genau drei kurze Bulletpoints: Was ist das wichtigste Muster und warum sollte
Vodafone jetzt hinschauen?

## Was sich aktuell abzeichnet
Ein zusammenhaengender Absatz mit dem Gesamtbild ueber mehrere Kategorien und
Regionen. Nenne konkrete Betreiber und Moves. Jede konkrete Aussage bekommt
unmittelbar einen Link im Format [Quelle](URL).

## Die stärksten Differenzierungs-Moves
Waehle die 5 bis 8 wichtigsten oder lehrreichsten Moves. Nutze pro Move eine
fette Zeile mit Betreiber und Kategorie, danach 1-2 Saetze: Was passiert und
was ist daran differenzierend? Jede Faktenaussage bekommt den passenden
Quellenlink aus den Daten.

## Was Vodafone daraus lernen kann
3 bis 5 kurze Abschnitte oder Bulletpoints. Verknuepfe die Beobachtung mit
einem konkreten Lernpunkt fuer Vodafone. Trenne klar zwischen belegter
Beobachtung und Vorschlag.

## Empfehlungen für Vodafone
3 bis 5 priorisierte Empfehlungen, nummeriert. Jeweils ein Satz zum konkreten
naechsten Schritt und ein Satz, welcher belegte Move den Anlass liefert. Keine
unbelegten Behauptungen ueber die aktuelle Vodafone-Strategie.

## Quellenbasis
Eine kompakte Liste der wichtigsten verwendeten Eintraege als
[Betreiber – Kurzbezeichnung](URL), mit Region und, falls vorhanden, Datum.

Regeln:
- Jede faktische Aussage ueber einen Wettbewerber muss einen Link auf eine
  URL aus den gelieferten Daten tragen.
- Nutze nur exakte URLs aus den gelieferten Daten; veraendere sie nicht.
- Berichte nicht einfach alle Artikel nach, sondern verdichte Muster und
  Konsequenzen. Die Quellenliste bleibt als Nachpruefbarkeit erhalten.
- Der Bericht umfasst maximal etwa 1.200 Woerter.
"""


_REQUIRED_HEADINGS = (
    "## auf einen blick",
    "## was sich aktuell abzeichnet",
    "## die staerksten differenzierungs-moves",
    "## was vodafone daraus lernen kann",
    "## empfehlungen fuer vodafone",
    "## quellenbasis",
)


def _heading_key(line: str) -> str:
    return (line.strip().lower().replace("ä", "ae").replace("ö", "oe")
            .replace("ü", "ue").replace("ß", "ss"))


def validate_briefing(markdown: str) -> None:
    """Reject an answer that is not the requested report shape."""
    headings = {_heading_key(line) for line in markdown.splitlines()
                if line.strip().startswith("## ")}
    missing = set(_REQUIRED_HEADINGS) - headings
    if missing:
        raise DifferentiationBriefingError(
            "Differenzierungsbericht unvollstaendig: " + ", ".join(sorted(missing)))
    if "[" not in markdown or "](" not in markdown:
        raise DifferentiationBriefingError(
            "Differenzierungsbericht enthaelt keine Quellenlinks")


def _payload(entries: list[dict], theme_labels: dict[str, str]) -> str:
    rows = []
    for e in entries:
        rows.append({
            "kategorie": theme_labels.get(e.get("theme"), e.get("theme") or ""),
            "betreiber": e.get("operator") or "",
            "region": e.get("region") or "",
            "move": e.get("what") or "",
            "bedeutung_fuer_vodafone": e.get("why") or "",
            "quelle": e.get("url") or "",
            "quellendom" : e.get("source") or "",
            "datum": e.get("date") or "",
            "erstmals_erfasst": e.get("first_seen") or "",
            "zuletzt_geprueft": e.get("last_verified") or "",
        })
    return json.dumps(rows, ensure_ascii=False)


def synthesize(entries: list[dict], theme_labels: dict[str, str], model: str,
               language: str = "Deutsch") -> str:
    """Run the dedicated differentiation editor and validate its Markdown."""
    if not entries:
        return build_digest(entries, theme_labels)
    raw = complete(
        DIFFERENTIATION_EDITOR_SYSTEM + f"\nBerichtssprache: {language}.",
        _payload(entries, theme_labels), model=model, max_tokens=4200)
    markdown = raw.strip()
    validate_briefing(markdown)
    return markdown


def _source_link(entry: dict) -> str:
    operator = entry.get("operator") or entry.get("source") or "Unbekannter Betreiber"
    url = entry.get("url") or ""
    label = entry.get("source") or "Quelle"
    return f"[{operator} – {label}]({url})"


def build_digest(entries: list[dict], theme_labels: dict[str, str]) -> str:
    """Build a useful report without an LLM, using only DB facts and links."""
    entries = [e for e in entries if e.get("url") and e.get("what")]
    by_theme: dict[str, list[dict]] = {}
    for entry in entries:
        by_theme.setdefault(entry.get("theme") or "_", []).append(entry)
    top = sorted(entries, key=lambda e: (e.get("last_verified") or "",
                                         e.get("first_seen") or ""), reverse=True)
    top_by_theme = []
    seen_themes = set()
    for entry in top:
        theme = entry.get("theme") or "_"
        if theme not in seen_themes:
            top_by_theme.append(entry)
            seen_themes.add(theme)
    operators = Counter(e.get("operator") for e in entries if e.get("operator"))
    active_themes = sorted(by_theme, key=lambda key: len(by_theme[key]), reverse=True)

    lines = [
        "## Auf einen Blick", "",
        f"- Die Bibliothek enthält {len(entries)} belegte Moves aus "
        f"{len(active_themes)} Differenzierungskategorien.",
        (f"- Am stärksten vertreten sind {theme_labels.get(active_themes[0], active_themes[0])} "
         f"({len(by_theme[active_themes[0]])} Moves)." if active_themes else
         "- Aktuell ist noch kein belegter Move in der Bibliothek verfügbar."),
        (f"- Die Beobachtung umfasst {len(operators)} benannte Betreiber; die Detailbelege "
         "stehen direkt an den jeweiligen Moves." if operators else
         "- Sobald neue Quellen bestätigt sind, wird dieser Bericht automatisch ergänzt."),
        "",
        "## Was sich aktuell abzeichnet", "",
    ]
    if active_themes:
        theme_text = ", ".join(theme_labels.get(k, k) for k in active_themes[:4])
        lines.append(
            f"Die aktuelle Sammlung verteilt sich vor allem auf {theme_text}. "
            "Sie zeigt damit mehrere Wege, wie Telkos jenseits des Preises einen "
            "zusätzlichen Grund für die Kundenbeziehung schaffen.")
        if top:
            lines.append(f"Ein aktueller belegter Move von {top[0].get('operator', 'einem Betreiber')} "
                         f"ist: {top[0].get('what', '').rstrip('.')} {_source_link(top[0])}.")
    else:
        lines.append("Die Datenbasis enthält derzeit noch keine bestätigten Moves.")
    lines += ["", "## Die stärksten Differenzierungs-Moves", ""]
    for entry in top[:8]:
        label = theme_labels.get(entry.get("theme"), entry.get("theme") or "Differenzierung")
        lines.append(f"**{entry.get('operator', 'Betreiber')} – {label}**")
        lines.append(f"{entry.get('what', '').rstrip('.')} {_source_link(entry)}.")
        if entry.get("why"):
            lines.append(f"Für Vodafone: {entry['why'].rstrip('.')}.")
        lines.append("")
    lines += ["## Was Vodafone daraus lernen kann", ""]
    if active_themes:
        for key in active_themes[:5]:
            sample = by_theme[key][0]
            lines.append(
                f"- **{theme_labels.get(key, key)}:** {sample.get('why') or sample.get('what')} "
                f"({_source_link(sample)}).")
    else:
        lines.append("- Die Bibliothek wird mit dem nächsten bestätigten Web-Sweep aussagekräftiger.")
    lines += ["", "## Empfehlungen für Vodafone", ""]
    if top:
        for i, entry in enumerate(top_by_theme[:4], 1):
            label = theme_labels.get(entry.get("theme"), entry.get("theme") or "Differenzierung")
            lines.append(
                f"{i}. **{label} prüfen:** Einen kleinen Piloten oder ein konkretes "
                f"Angebot zu diesem Hebel bewerten; Anlass ist der belegte Move von "
                f"{entry.get('operator', 'einem Wettbewerber')} {_source_link(entry)}.")
            lines.append("")
    else:
        lines.append("1. Die nächsten bestätigten Moves abwarten und anschließend priorisieren.")
        lines.append("")
    lines += ["## Quellenbasis", ""]
    for entry in top[:12]:
        date = f" · {entry['date']}" if entry.get("date") else ""
        region = f" · {entry['region']}" if entry.get("region") else ""
        lines.append(f"- {_source_link(entry)}{region}{date}")
    if not top:
        lines.append("- Noch keine Quelle in der Differenzierungs-DB.")
    return "\n".join(lines).strip() + "\n"
