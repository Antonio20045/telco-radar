# Welle 3 — Schlussliste

Auftrag: `AUFTRAG_1000_QUELLEN_WELLE3.md`. Dieser Text ist Abschnitt 8.9:
was wirklich erreicht wurde, was nicht, und mit welchen Zahlen belegt.

**Jede Zahl hier stammt aus einem Skript oder einem Laufprotokoll.** Die
Rohdaten liegen daneben (`befund_*.json`, `messung_datumsparser.json`,
`kandidaten_firmen_welle3.yaml`).

> *Dieser Text wird am Ende der Session fertiggestellt; die Abschnitte unten
> werden mit den Schlusszahlen gefüllt.*

---

## 1. Die Zahl

| | Quellen |
|---|---:|
| Stand vor Welle 3 | 205 |
| nach Welle 3a (Rubrikfeeds) | 238 |
| nach Welle 3b (Newsroom-Suche) | 249 |

Gezählt mit `python scripts/quellen_zaehlen.py` — crawlbare Quellen, also
was ein Lauf wirklich abfragt.

---

## 2. Zwei Dinge, die diese Session nicht geschafft hat

Beides gehört an den Anfang, nicht ans Ende.

**Das Ziel 1000 ist nicht erreicht, und es war in einer Session auch nicht
erreichbar.** Warum, steht in Abschnitt 5 — mit der Rechnung dazu.

**Die Session hat sich selbst einen Container gekostet.** Mitten in der
Arbeit wurde die Arbeitsumgebung zurückgesetzt und mit ihr das gesamte
Arbeitsverzeichnis: der bereits gebaute Sucher, die Tests, die Konfiguration
und rund eine Stunde Suchergebnisse. Wiederhergestellt wurde alles aus dem
Kopf, nicht aus einem Backup. **Konsequenz für die nächste Session: nach
jedem abgeschlossenen Schritt committen UND pushen.** Nur was auf GitHub
liegt, überlebt. `.welle3/` ist bewusst gitignored, die Ergebnisse daraus
liegen deshalb zusätzlich unter `outputs/welle3/`.
