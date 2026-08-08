"""Der Prueflauf gegen den Originaltext - die Bedingung fuer die CTM-Linse.

Solange das System zusammenfasst, ist ein Fehler eine ungenaue Zeile. Sobald
es FOLGERT ("drueckt die Preisuntergrenze fuer unsere Unlimited-Stufe"),
klingt ein Fehler plausibel und ist trotzdem falsch - und er steht unter
einem Quellenlink, der ihn zu belegen scheint. Das ist die teuerste Art, das
Vertrauen in dieses Portal zu verlieren.

Deshalb laeuft ueber jeden `ctm_satz` ein zweiter, unabhaengiger Durchgang:
Steht die Behauptung wirklich in der Quelle, oder hat das Modell sie
dazugelegt? Geprueft werden drei Dinge getrennt, weil sie verschieden
scheitern:

  1. **Zahlen.** Jede Zahl im Satz muss in Titel oder Zusammenfassung stehen.
     Das rechnet der CODE, nicht das Modell - eine erfundene Zahl ist der
     haeufigste und der am leichtesten nachweisbare Fehler.
  2. **Aussage.** Traegt die Quelle die Folgerung? Das entscheidet das Modell.
  3. **Sicherheitswort.** "sehr wahrscheinlich" ueber einer Quelle, die nur
     eine Absicht nennt, ist eine Uebertreibung - auch wenn jedes einzelne
     Wort belegt ist.

**Fail closed.** Kann der Prueflauf nicht stattfinden (Anbieter weg, Antwort
unlesbar), faellt der Satz - er erscheint NICHT ungeprueft. Ein ungeprueft
veroeffentlichter Folgerungssatz waere genau das Risiko, gegen das dieser
Durchgang steht; ein fehlender Satz kostet dagegen nur eine Zeile. Die Zahl
der so gefallenen Saetze steht im Laufprotokoll, damit ein stiller
Dauerausfall auffaellt.
"""
from __future__ import annotations

import json
import logging
import re

from .llm import complete, extract_json

log = logging.getLogger(__name__)

STAPEL = 10          # Saetze je Pruefaufruf

# Zahlen im Satz, die belegt sein muessen. Prozentangaben, Preise, Volumen.
# Einstellige Zahlen bleiben aussen vor: "5G", "die ersten drei" und
# Aufzaehlungen sind keine Behauptung ueber die Quelle.
_ZAHL_IM_SATZ = re.compile(r"\d+(?:[.,]\d+)*")

_SICHERHEIT = ("sehr wahrscheinlich", "wahrscheinlich", "möglich")

_SYSTEM = """\
Du pruefst Folgerungssaetze gegen ihre Quelle.

Zu jedem Eintrag bekommst du den Originaltitel und die Zusammenfassung einer
Meldung sowie EINEN Satz, den ein Analyst daraus gefolgert hat.

Der Satz ist BELEGT, wenn alles, was er ueber die Meldung behauptet, aus
Titel oder Zusammenfassung hervorgeht. Eine Schlussfolgerung fuer das eigene
Unternehmen ("drueckt die Preisuntergrenze", "muessten wir kontern") ist
erlaubt und macht den Satz NICHT unbelegt - sie ist der Zweck des Satzes.

Der Satz ist NICHT belegt, wenn er
- eine Zahl, einen Preis, ein Datum oder einen Namen nennt, der in der
  Quelle nicht vorkommt,
- ein Ereignis behauptet, das die Quelle nicht berichtet,
- aus einer Absicht eine Entscheidung macht ("wird einfuehren", wo die
  Quelle "prueft" sagt),
- den Markt oder das Land verwechselt.

Antworte mit NUR diesem JSON, ohne Markdown:
{"urteile": [{"id": <id>, "belegt": true oder false, "grund": "<hoechstens 8 Woerter, nur wenn nicht belegt>"}]}

Im Zweifel belegt=false.
"""


def _zahlen_gedeckt(satz: str, quelle: str) -> str | None:
    """Nennt der Satz eine Zahl, die in der Quelle nicht steht?"""
    quelle_zahlen = {z.replace(".", "").replace(",", ".")
                     for z in _ZAHL_IM_SATZ.findall(quelle or "")}
    for roh in _ZAHL_IM_SATZ.findall(satz or ""):
        normal = roh.replace(".", "").replace(",", ".")
        if len(normal.replace(".", "")) <= 1:
            continue
        # "35 Euro" deckt "34,95 Euro" nicht ab, aber "5G" deckt "5G" ab -
        # verglichen wird der reine Zahlenwert, gerundete Naeherungen zaehlen
        # als gedeckt, wenn die Quelle denselben Betrag ganzzahlig enthaelt.
        if normal in quelle_zahlen:
            continue
        try:
            wert = float(normal)
        except ValueError:
            return roh
        if any(abs(wert - float(q)) < 1.0 for q in quelle_zahlen
               if _ist_zahl(q)):
            continue
        return roh
    return None


def _ist_zahl(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _uebertreibt(satz: str, quelle: str) -> bool:
    """"sehr wahrscheinlich" ueber einer Quelle, die nur eine Absicht nennt."""
    if "sehr wahrscheinlich" not in (satz or "").lower():
        return False
    q = (quelle or "").lower()
    absicht = ("prüft", "prueft", "erwägt", "erwaegt", "plant", "will ",
               "könnte", "koennte", "denkt über", "considering", "explores",
               "may ", "plans to")
    entschieden = ("startet", "führt ein", "senkt", "erhöht", "kostet",
                   "ab dem", "ab sofort", "launches", "cuts", "raises",
                   "announced", "available from")
    return any(a in q for a in absicht) and not any(e in q for e in entschieden)


def pruefe(highlights: list[dict], *, model: str, use_llm: bool) -> dict:
    """Prueft alle `ctm_satz` und entfernt die unbelegten. Liefert die Bilanz.

    Aendert die Meldungen an Ort und Stelle: ein durchgefallener Satz wird
    geloescht und der Grund unter `ctm_satz_verworfen` vermerkt - sichtbar im
    Berichts-JSON, damit sich nachlesen laesst, WARUM eine Zeile fehlt.
    """
    kandidaten = [h for h in highlights if (h.get("ctm_satz") or "").strip()]
    bilanz = {"geprueft": len(kandidaten), "belegt": 0, "verworfen": 0,
              "gruende": {}}
    if not kandidaten:
        return bilanz

    def verwirf(h: dict, grund: str) -> None:
        h["ctm_satz_verworfen"] = grund
        h.pop("ctm_satz", None)
        bilanz["verworfen"] += 1
        bilanz["gruende"][grund] = bilanz["gruende"].get(grund, 0) + 1

    # ---- Stufe 1 und 3 rechnet der Code. Sie kosten nichts und fangen den
    # haeufigsten Fehler, bevor ein Modellaufruf ihn beurteilen muss.
    offen = []
    for h in kandidaten:
        quelle = f"{h.get('title') or ''} {h.get('summary') or ''}"
        erfunden = _zahlen_gedeckt(h["ctm_satz"], quelle)
        if erfunden:
            verwirf(h, f"Zahl {erfunden} steht nicht in der Quelle")
            continue
        if _uebertreibt(h["ctm_satz"], quelle):
            verwirf(h, "Sicherheitswort übertreibt die Quelle")
            continue
        offen.append(h)

    if not offen:
        return bilanz

    if not use_llm or not model:
        # Fail closed: ungeprueft erscheint kein Folgerungssatz.
        for h in offen:
            verwirf(h, "nicht geprüft (kein Modell verfügbar)")
        return bilanz

    # ---- Stufe 2: traegt die Quelle die Folgerung?
    for start in range(0, len(offen), STAPEL):
        stapel = offen[start:start + STAPEL]
        nutzlast = json.dumps([
            {"id": i,
             "titel": h.get("title") or "",
             "zusammenfassung": (h.get("summary") or "")[:600],
             "satz": h["ctm_satz"]}
            for i, h in enumerate(stapel)], ensure_ascii=False)
        try:
            # 8000 ist die Untergrenze, die sich bewaehrt hat (Laeufe #83-85):
            # ein denkendes Modell ist mit einem kleineren Budget fertig,
            # bevor die Antwort anfaengt, und liefert einen leeren String.
            roh = complete(_SYSTEM, nutzlast, model=model, max_tokens=8000)
            urteile = {int(u.get("id", -1)): u
                       for u in (extract_json(roh).get("urteile") or [])}
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            log.warning("Beleg-Pruefung fehlgeschlagen (%s) - die Saetze "
                        "dieses Stapels erscheinen NICHT", str(exc)[:140])
            for h in stapel:
                verwirf(h, "Prüfung nicht möglich")
            continue
        for i, h in enumerate(stapel):
            urteil = urteile.get(i)
            if urteil is None:
                verwirf(h, "kein Prüfurteil erhalten")
            elif urteil.get("belegt"):
                h["ctm_satz_geprueft"] = True
                bilanz["belegt"] += 1
            else:
                verwirf(h, " ".join(str(urteil.get("grund")
                                        or "nicht belegt").split())[:60])

    log.info("Beleg-Pruefung: %d Saetze, %d belegt, %d verworfen (%s)",
             bilanz["geprueft"], bilanz["belegt"], bilanz["verworfen"],
             ", ".join(f"{g}: {n}" for g, n in
                       sorted(bilanz["gruende"].items(),
                              key=lambda kv: -kv[1])[:3]) or "keine")
    return bilanz
