"""Den Differenzierungsbericht zerlegen, damit die Seite ihn VERTEILEN kann.

Antonio am 08.08.2026: *"eigentlich hat es noch einen Bericht, und Bericht finde
ich auch gut - aber nicht einfach so reinpasten, dieser eine lange Bereich. Das
muss intelligent sein."*

Bis dahin lag der Bericht als ein zugeklappter Block am Seitenende, und er war
in einer Hinsicht schlimmer als nutzlos: er sagte **dasselbe noch einmal**. Sein
Abschnitt "Konkrete Entwicklungen" ist eine Aufzaehlung aller Moves mit
Inline-Links - also genau der Bestand, der zwei Bildschirme weiter oben schon
als Karten steht, nur ohne Bild, ohne Gliederung und in Absaetzen von 2000
Zeichen. Seine Rubrik "Quellenbasis" wiederholt die Quellen ein drittes Mal.

Was ein Bericht auf dieser Seite beitragen KANN, ist das, was die Karten nicht
zeigen: die Lage in wenigen Saetzen, die wiederkehrenden Muster und je Hebel
eine Einordnung. Genau diese Gliederung schreibt der Redakteur seit dem
08.08.2026 (`analyze/differentiation_editor.py`), und dieses Modul schneidet sie
in die Teile, die die Vorlage an drei verschiedenen Stellen einsetzt:

    lage        oben, unter der Ueberschrift - der Einstieg in die Seite.
    muster      als eigener Block neben dem gerechneten Marktbild.
    einordnung  je Hebel EIN Absatz, direkt ueber dessen Beispielen.

**Alte Berichte bleiben lesbar.** Die Berichte in `data/reports/differenzierung/`
sind Monate alt und tragen die alte Gliederung; bis zum naechsten Pipeline-Lauf
ist der neueste davon einer. Findet dieses Modul keinen der neuen Abschnitte,
liefert es `alt_md` - und die Seite zeigt den Bericht wie bisher zugeklappt am
Ende, statt eine leere Zeile zu behaupten. Kein Lauf muss abgewartet werden,
damit die Seite steht.
"""
from __future__ import annotations

import re

# Die H2-Ueberschriften der neuen Gliederung. Geschrieben werden sie vom
# Redakteur; `analyze/differentiation_editor.validate_briefing` erzwingt sie.
# Wer hier etwas aendert, muss dort mitziehen - die zwei Stellen sind ein
# Schalter, kein Paar (dieselbe Kopplung wie beim Wochen-Editor, CLAUDE.md §6).
H2_LAGE = "das bild"
H2_MUSTER = "muster"
H2_EINORDNUNG = "einordnung"
# Was aus einem alten Bericht ausdruecklich NICHT uebernommen wird: eine
# Quellenliste, die jede Karte der Seite ein zweites Mal auffuehrt.
H2_UEBERSPRINGEN = ("quellenbasis",)

_H2 = re.compile(r"^##\s+(.*?)\s*$")
_H3 = re.compile(r"^###\s+(.*?)\s*$")
_FETT_AM_ANFANG = re.compile(r"^\*\*(.+?)\*\*\s*(.*)$", re.S)


def _schluessel(text: str) -> str:
    """Ueberschrift auf einen vergleichbaren Kern reduzieren."""
    text = text.strip().lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def _abschnitte(markdown: str) -> list[tuple[str, list[str]]]:
    """Das Dokument in (H2-Ueberschrift, Zeilen) zerlegen."""
    out: list[tuple[str, list[str]]] = []
    titel = ""
    zeilen: list[str] = []
    for zeile in (markdown or "").splitlines():
        m = _H2.match(zeile)
        if m:
            out.append((titel, zeilen))
            titel, zeilen = m.group(1), []
        else:
            zeilen.append(zeile)
    out.append((titel, zeilen))
    return [(t, z) for t, z in out if t or any(x.strip() for x in z)]


def _absaetze(zeilen: list[str]) -> list[str]:
    text = "\n".join(zeilen).strip()
    return [a.strip() for a in re.split(r"\n\s*\n", text) if a.strip()]


def _muster(zeilen: list[str]) -> list[dict]:
    """Die Muster-Absaetze als (Titel, Text).

    Der Redakteur schreibt sie als `**Musterwort** Text`. Ein Absatz ohne
    fettes Musterwort ist kein Fehler - er bekommt schlicht keinen Titel und
    steht als reiner Text. Ihn zu verwerfen hiesse, eine Aussage wegen ihrer
    Formatierung zu unterschlagen.
    """
    out = []
    for absatz in _absaetze(zeilen):
        m = _FETT_AM_ANFANG.match(absatz)
        if m:
            out.append({"titel": m.group(1).strip(),
                        "text": " ".join(m.group(2).split())})
        else:
            out.append({"titel": "", "text": " ".join(absatz.split())})
    return out


def _einordnung(zeilen: list[str], label_map: dict[str, str]) -> dict[str, str]:
    """Je Hebel den Absatz, der unter seiner H3-Ueberschrift steht.

    Zugeordnet wird ueber das Hebel-LABEL, nicht ueber die Reihenfolge: der
    Redakteur laesst Hebel aus, zu denen ihm nichts einfaellt, und eine
    Zuordnung nach Position haengte dann jeden folgenden Absatz an den
    falschen Hebel - eine falsche Verbindung ist schlimmer als keine
    (dieselbe Lehre wie beim roten Faden, CLAUDE.md §5).
    """
    nach_label = {_schluessel(label): key for key, label in label_map.items()}
    out: dict[str, str] = {}
    key = ""
    puffer: list[str] = []

    def ablegen() -> None:
        if key and puffer:
            text = " ".join(" ".join(puffer).split())
            if text:
                out.setdefault(key, text)

    for zeile in zeilen:
        m = _H3.match(zeile)
        if m:
            ablegen()
            key, puffer = nach_label.get(_schluessel(m.group(1)), ""), []
        else:
            puffer.append(zeile)
    ablegen()
    return out


def zerlegen(markdown: str, label_map: dict[str, str]) -> dict:
    """Der Bericht in seinen verteilbaren Teilen.

    `label_map` bildet Hebel-Key auf Anzeige-Label ab (analyze/category_sweep
    THEMES). Rueckgabe:

        lage        Markdown-Absaetze fuer den Seitenkopf ("" wenn keine)
        muster      [{titel, text}] fuer den Marktbild-Block
        einordnung  {hebel_key: text} fuer die Hebel-Rubriken
        alt_md      der ganze Bericht, falls NICHTS davon gefunden wurde -
                    dann zeigt ihn die Seite zugeklappt wie bisher
    """
    lage = ""
    muster: list[dict] = []
    einordnung: dict[str, str] = {}
    erkannt = False

    for titel, zeilen in _abschnitte(markdown):
        kern = _schluessel(titel)
        if not kern:
            continue
        if kern in H2_UEBERSPRINGEN:
            erkannt = erkannt or False
            continue
        if kern.startswith(H2_LAGE):
            lage = "\n\n".join(_absaetze(zeilen))
            erkannt = True
        elif kern.startswith(H2_MUSTER):
            muster = _muster(zeilen)
            erkannt = erkannt or bool(muster)
        elif kern.startswith(H2_EINORDNUNG):
            einordnung = _einordnung(zeilen, label_map)
            erkannt = erkannt or bool(einordnung)

    return {"lage": lage, "muster": muster, "einordnung": einordnung,
            "alt_md": "" if erkannt else (markdown or "").strip()}
