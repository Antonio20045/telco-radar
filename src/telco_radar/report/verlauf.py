"""Was waechst, was kippt - die Zeitachse der Differenzierungs-Bibliothek.

Die Seite sagte: "71 Beispiele, Entertainment 17, KI 12". Sie sagte nie, ob
KI im Juni noch 4 war. Genau diese Ableitung ist der eigentliche Wert einer
Datenbank, die seit Juli laeuft - jede einzelne Ansicht davor zeigte einen
ZUSTAND.

Gerechnet, nicht geschaetzt
---------------------------
Das Rohmaterial liegt vor: jeder Eintrag der Bibliothek traegt `first_seen`,
also den Monat, in dem er aufgenommen wurde. Mehr braucht es nicht - kein
neuer Speicher, kein Modellaufruf, keine zusaetzliche Stufe in der Pipeline.

Warum ANTEILE und nicht Zahlen
------------------------------
Die Bibliothek waechst; jeder Hebel hat im letzten Monat mehr Eintraege als
im ersten. Absolute Zahlen zeigen deshalb immer "alles waechst" - das ist
eine Aussage ueber die Sammelmenge, nicht ueber den Markt. Verglichen wird
der ANTEIL eines Hebels an den Aufnahmen des jeweiligen Monats.

Der Vorbehalt, den die Seite mitnennen muss
-------------------------------------------
Ein Monat mit wenigen Aufnahmen hat einen wackligen Anteil. Deshalb
`_MIND_JE_MONAT`: Monate darunter werden gezeigt, aber NICHT fuer die
Trendaussage benutzt. Ein "Fintech verdoppelt sich" aus zwei Beispielen ist
keine Beobachtung, sondern eine Rundung.
"""
from __future__ import annotations

from collections import defaultdict

# Wie viele Monate der Verlauf zeigt. Sechs sind ein halbes Jahr und passen
# als Balkenreihe nebeneinander.
MAX_MONATE = 6

# Unter so vielen Aufnahmen im Monat ist der Anteil eines einzelnen Hebels
# Rauschen. Der Monat steht trotzdem im Verlauf - er wird nur nicht fuer die
# Aussage "waechst/kippt" herangezogen.
_MIND_JE_MONAT = 5

# Um wie viele Prozentpunkte sich ein Anteil verschieben muss, damit es eine
# Bewegung heisst. Darunter ist es dieselbe Lage in anderer Rundung.
_SCHWELLE_PUNKTE = 5.0

MONATE_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
             "August", "September", "Oktober", "November", "Dezember"]


def _monat_label(iso_monat: str) -> str:
    try:
        jahr, monat = iso_monat.split("-")
        return f"{MONATE_DE[int(monat) - 1][:3]} {jahr[2:]}"
    except (ValueError, IndexError):
        return iso_monat


def aufbereiten(bestand: list[dict], theme_label: dict[str, str]) -> dict:
    """Der Verlauf je Hebel plus die Bewegungen des letzten Monats."""
    je_monat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in bestand:
        monat = str(e.get("first_seen") or "")[:7]
        thema = str(e.get("theme") or "")
        if len(monat) == 7 and thema:
            je_monat[monat][thema] += 1

    monate = sorted(je_monat)[-MAX_MONATE:]
    if len(monate) < 2:
        # Ein einzelner Monat ist kein Verlauf. Lieber nichts zeigen als eine
        # Linie mit einem Punkt.
        return {"aktiv": False, "monate": [], "reihen": [],
                "waechst": [], "kippt": []}

    gesamt = {m: sum(je_monat[m].values()) for m in monate}
    belastbar = [m for m in monate if gesamt[m] >= _MIND_JE_MONAT]

    reihen = []
    for key, label in theme_label.items():
        punkte = []
        for m in monate:
            n = je_monat[m].get(key, 0)
            anteil = 100.0 * n / gesamt[m] if gesamt[m] else 0.0
            punkte.append({"monat": m, "label": _monat_label(m), "n": n,
                           "anteil": round(anteil, 1),
                           "belastbar": m in belastbar})
        if not any(p["n"] for p in punkte):
            continue
        reihen.append({"key": key, "label": label, "punkte": punkte,
                       "gesamt": sum(p["n"] for p in punkte)})
    reihen.sort(key=lambda r: -r["gesamt"])

    # Die Bewegung: letzter belastbarer Monat gegen den Durchschnitt der
    # belastbaren Monate davor. Gegen den VORMONAT allein zu rechnen macht
    # jede Schwankung zur Nachricht.
    waechst, kippt = [], []
    if len(belastbar) >= 2:
        letzter = belastbar[-1]
        davor = belastbar[:-1]
        for reihe in reihen:
            je = {p["monat"]: p["anteil"] for p in reihe["punkte"]}
            jetzt = je.get(letzter, 0.0)
            basis = sum(je.get(m, 0.0) for m in davor) / len(davor)
            delta = round(jetzt - basis, 1)
            eintrag = {"label": reihe["label"], "key": reihe["key"],
                       "jetzt": jetzt, "vorher": round(basis, 1),
                       "delta": delta}
            if delta >= _SCHWELLE_PUNKTE:
                waechst.append(eintrag)
            elif delta <= -_SCHWELLE_PUNKTE:
                kippt.append(eintrag)
        waechst.sort(key=lambda e: -e["delta"])
        kippt.sort(key=lambda e: e["delta"])

    return {
        "aktiv": True,
        "monate": [{"monat": m, "label": _monat_label(m), "n": gesamt[m],
                    "belastbar": m in belastbar} for m in monate],
        "reihen": reihen[:8],
        "waechst": waechst[:3],
        "kippt": kippt[:3],
        # Damit die Seite den Vorbehalt nennen kann, statt ihn zu verschweigen.
        "duenne_monate": [_monat_label(m) for m in monate
                          if m not in belastbar],
        "mind_je_monat": _MIND_JE_MONAT,
    }
