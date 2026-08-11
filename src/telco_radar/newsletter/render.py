"""Aus Bericht und Treffern werden HTML und Text.

**Hier gibt es keinen Modellaufruf.** Das ist keine Sparmassnahme, sondern
die Bedingung dafuer, dass es nur EINE Wahrheit gibt: sobald jemand den
Editor fuer die Mail "etwas anders" formulieren laesst, sagen Mail und
Website verschiedene Dinge, und niemand merkt, welche von beiden stimmt. Der
Renderer liest und kuerzt ausschliesslich - er formuliert nicht.

Deshalb die Trennung, ohne die der Treue-Test gar nicht erfuellbar waere:

  * **Inhaltstragende Bloecke** (alles aus `items[]` - Titel, Zusammenfassung,
    Absender) muessen als Teilstring im Bericht-JSON vorkommen.
  * **Rahmentexte** (Anrede, Kopfzeile, Abmeldehinweis, Impressumszeile,
    Stichwort-Markierung, Leermeldung) stehen naturgemaess nirgends im
    Bericht und kommen ausschliesslich aus `templates/mail/chrome.yaml`.

Zum `List-Unsubscribe`: nur die `https://`-URL. **Kein `mailto:`** - es gibt
in dieser Architektur kein Postfach, das es auswerten koennte. **Kein
`List-Unsubscribe-Post`** nach RFC 8058 - das ist eine Anforderung an
Bulk-Sender ab rund 5.000 Nachrichten pro Tag, bei 300 Mails Tageslimit also
unerreichbar, und der maschinelle Aufruf mit kurzem Timeout wuerde in den
Render-Kaltstart laufen und still fehlschlagen: der Nutzer haelt sich fuer
abgemeldet, die naechste Ausgabe kommt trotzdem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..textwerkzeug import saetze as _saetze
from .filters import Treffer

_VORLAGEN = Path(__file__).resolve().parent / "templates" / "mail"

# Der Satzspiegel der Mail. 600 px ist die Breite, mit der jeder Mailclient
# seit zwanzig Jahren rechnet - Outlooks Leseansicht schneidet darueber ab.
BREITE = 600

# Wie viel Zusammenfassung in die Mail kommt. Gekuerzt wird an der SATZgrenze,
# nicht an der Zeichengrenze: ein abgeschnittener Halbsatz mit "…" liest sich
# wie ein Fehler - und er waere kein Teilstring des Quelltextes mehr, der
# Treue-Test wuerde ihn zu Recht nicht wiederfinden.
MAX_SAETZE = 2


@dataclass
class Nachricht:
    """Eine fertige Mail - unabhaengig davon, wer sie zustellt."""
    betreff: str
    html: str
    text: str
    headers: dict = field(default_factory=dict)


def _env() -> Environment:
    # Zwei Vorlagen, zwei Regeln: das HTML wird escaped (in einer Meldung
    # steht, was ein beliebiger fremder Newsroom in seinen Titel schreibt),
    # die Textfassung nicht - dort waere "&amp;" ein sichtbarer Fehler.
    # `select_autoescape` entscheidet das an der Endung; "j2" MUSS in der
    # Liste stehen, sonst sieht es nur die letzte Endung und escaped nirgends
    # (derselbe Fehler wie am 04.08.2026 im Seiten-Renderer).
    env = Environment(
        loader=FileSystemLoader(_VORLAGEN),
        autoescape=select_autoescape(enabled_extensions=("html.j2",),
                                     default_for_string=False, default=False),
        keep_trailing_newline=True)
    return env


def lade_chrome(pfad: Path | None = None) -> dict:
    """Die Rahmentexte. EINE Datei, versioniert - siehe ihren Kopf."""
    quelle = Path(pfad) if pfad else (_VORLAGEN / "chrome.yaml")
    return yaml.safe_load(quelle.read_text(encoding="utf-8")) or {}


def rahmentexte(chrome: dict | None = None) -> set[str]:
    """Jeder Rahmentext als Zeichenkette - die Allowlist des Treue-Tests."""
    chrome = chrome if chrome is not None else lade_chrome()
    aus: set[str] = set()

    def sammle(wert):
        if isinstance(wert, str):
            aus.add(wert)
        elif isinstance(wert, dict):
            for v in wert.values():
                sammle(v)
        elif isinstance(wert, list):
            for v in wert:
                sammle(v)

    sammle(chrome)
    return aus


# ==========================================================  Kuerzen  ======

def kuerze(text: str, anzahl: int = MAX_SAETZE) -> str:
    """Die ersten `anzahl` Saetze - unveraendert, ohne Ellipse.

    Der gekuerzte Text bleibt damit ein TEILSTRING des Originals, und genau
    daran haengt der Treue-Test. Wer hier "…" anhaengt oder Wortabstaende
    normalisiert, macht ihn unerfuellbar.

    Getrennt wird mit `textwerkzeug.saetze()` und nicht mit einem eigenen
    `(?<=[.!?])\\s+`. Der Unterschied ist nicht theoretisch: ein naiver
    Trenner machte aus "Aktion gültig bis 12. September 2026" den ganzen
    Satz "Aktion gültig bis 12." - gemessen in der Vorschau vom 11.08.2026,
    und dort stand es genau so in der Mail.
    """
    teile = _saetze((text or "").strip())
    return " ".join(t for t in teile[:anzahl] if t).strip()


# ============================================================  Betreff  ====

def betreff(datum_de: str, treffer: list[Treffer], chrome: dict) -> str:
    """"Telco Radar, 11. August: Telekom senkt Preise (+3 weitere)".

    Die staerkste Schlagzeile im Betreff, nicht "Ihr Newsletter" - der
    Betreff ist die einzige Zeile, die JEDER Empfaenger sieht, auch der, der
    nicht oeffnet. Die Schlagzeile kommt aus dem Bericht, die drei
    Rahmenbestandteile aus chrome.yaml.
    """
    marke = (chrome.get("kopf") or {}).get("titel") or "Telco Radar"
    if not treffer:
        return f"{marke}, {datum_de}"
    erste = treffer[0].eintrag.titel.strip()
    rest = len(treffer) - 1
    zusatz = f" (+{rest} weitere)" if rest > 0 else ""
    kopf = f"{marke}, {datum_de}: "
    # Ein Betreff ueber rund 78 Zeichen wird in jeder Liste abgeschnitten -
    # und zwar mitten im Wort, wenn man es nicht selbst tut.
    platz = 78 - len(kopf) - len(zusatz)
    if len(erste) > platz > 20:
        erste = erste[:platz].rsplit(" ", 1)[0]
    return f"{kopf}{erste}{zusatz}"


# ==========================================================  Zusammenbau  ==

def _items(treffer: list[Treffer]) -> list[dict]:
    """Die inhaltstragenden Bloecke - und NUR sie.

    Was hier steht, muss im Bericht-JSON wiederzufinden sein. Deshalb wird
    hier nichts zusammengesetzt ("Telekom: Preise gesenkt"), nichts ergaenzt
    und nichts umgestellt.

    Die eine Ausnahme betrifft nicht den Inhalt, sondern die Markierung:
    **dasselbe Stichwort wird nur beim ERSTEN einer Folge genannt.** In der
    Vorschau vom 11.08.2026 stand "Ihr Stichwort: Starlink" viermal
    untereinander - weil die Stichworttreffer hinter den Filtertreffern
    stehen, folgen gleiche Marken zwangslaeufig aufeinander. Viermal
    dieselbe Zeile erklaert nichts mehr, sie trommelt nur; die erste erklaert
    die ganze Folge. Dieselbe Hausregel wie auf der Website: eine Angabe
    steht je Ort genau einmal.
    """
    aus: list[dict] = []
    vorheriges_stichwort = ""
    for t in treffer:
        stichwort = t.stichwort if t.ueber_stichwort else ""
        zeigen = stichwort if stichwort != vorheriges_stichwort else ""
        vorheriges_stichwort = stichwort
        aus.append({"titel": t.eintrag.titel,
                    "text": kuerze(t.eintrag.text),
                    "absender": t.eintrag.absender,
                    "url": t.eintrag.url,
                    "anker": t.eintrag.anker,
                    "stichwort": zeigen})
    return aus


def baue(treffer: list[Treffer], *, datum_de: str, bericht_url: str,
         abmelde_url: str, seit_datum: str = "", basis_url: str = "",
         chrome: dict | None = None, mit_filter: bool = True) -> Nachricht:
    """Die fertige Nachricht - HTML, Text und Kopfzeilen."""
    chrome = chrome if chrome is not None else lade_chrome()
    basis = (basis_url or "").rstrip("/")
    ctx = {
        "chrome": chrome,
        "items": _items(treffer),
        "betreff": betreff(datum_de, treffer, chrome),
        "datum_de": datum_de,
        "seit_datum": seit_datum or datum_de,
        "bericht_url": bericht_url,
        "abmelde_url": abmelde_url,
        "impressum_url": f"{basis}/impressum.html" if basis else "",
        "datenschutz_url": f"{basis}/datenschutz.html" if basis else "",
        "einleitung": (chrome["einleitung_filter"] if mit_filter
                       else chrome["einleitung_alles"]),
        "breite": BREITE,
    }
    env = _env()
    return Nachricht(
        betreff=ctx["betreff"],
        html=env.get_template("digest.html.j2").render(**ctx),
        text=env.get_template("digest.txt.j2").render(**ctx),
        headers=kopfzeilen(abmelde_url))


def kopfzeilen(abmelde_url: str) -> dict:
    """`List-Unsubscribe` mit der https-URL. Sonst nichts.

    Ein Header, der eine Handlungsmoeglichkeit verspricht, die still
    fehlschlaegt, ist schlimmer als keiner (siehe Modulkopf).
    """
    return {"List-Unsubscribe": f"<{abmelde_url}>"} if abmelde_url else {}
