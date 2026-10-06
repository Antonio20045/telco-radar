# Seitenauftrag

Ein Seitenauftrag ändert eine Seite sichtbar und läuft über `tools/auftrag.py` vom roten Abnahmetest bis zum Merge auf `main`. Bei `art: verhalten` schreibt der Auftrag die erwarteten Seiten des goldenen Laufs (`tests/fixtures/golden/<tag>/erwartet.json`) selbst neu und nennt die geänderten Seiten im Commit unter „Seiten neu im goldenen Lauf:“ und in `goldener-lauf.txt` im Laufordner.

## Ablauf

1. Einmal `make pruefen` auf dem Mac. Ohne den Stempel startet kein Auftrag („ungestempelte Commits“).
2. Hat die Leiter dabei `.importlinter` oder Basen unter `pruef/` gesenkt, ist der Arbeitsbaum nicht sauber, und kein Auftrag startet. Dann einmal:
   `git add .importlinter pruef && git commit -m "pruef: Basen der Leiter" && git push origin main`
3. Den Auftrag außerhalb des Repos anlegen, etwa als `~/auftraege/<id>.json` (Felder und Beispiel unten). Eine neue Datei im Repo macht den Arbeitsbaum unsauber, und als Commit wäre sie ungestempelt; beides sperrt den Start. Das Skript legt seine eigene Kopie im Laufordner unter `.git/` ab.
4. Starten: `.venv/bin/python tools/auftrag.py ~/auftraege/<id>.json`

Das Skript endet mit `gemergt` (Exit 0) oder legt `outputs/auftraege/<id>-notiz.md` mit dem Befund an; vor dem nächsten Start die Notiz und die geänderte `kosten.csv` committen (danach `make pruefen`) oder verwerfen, sonst ist der Arbeitsbaum unsauber. Höchstens zwei Aufträge laufen gleichzeitig, und ihre Bereiche dürfen sich nicht überschneiden.

## Mit Planer: ein Satz statt JSON

1. `.venv/bin/python tools/plane.py S2 "Auf der Geräteseite soll …"` startet den Planer (Rolle `suchen`, ändert nichts). Er schreibt `spezifikation.md`, je Unteraufgabe `S2-<nr>.json` und die Reihenfolge `plan.json` nach `~/auftraege/S2/` (anders mit `--ordner`). Jede Unteraufgabe besteht dieselbe Formatprüfung wie oben; ein ungültiger Plan bekommt eine zweite Runde, danach liegt die Antwort in `planer-roh.txt`.
2. `spezifikation.md` lesen. Passt sie nicht, Ordner löschen und den Satz schärfen.
3. `.venv/bin/python tools/auftraege.py ~/auftraege/S2` startet jede Unteraufgabe über `tools/auftrag.py`, sobald ihre Abhängigkeiten gemergt sind; höchstens zwei gleichzeitig und nie mit überschneidendem Bereich. Endet eine nicht mit `gemergt`, startet keine weitere. Ergebnis in `ergebnis.md`, Log je Unteraufgabe als `S2-<nr>.log` im Planordner.

## Pflichtfelder

| Feld | Typ | Inhalt |
|---|---|---|
| `id` | Text | Buchstaben, Ziffern, `-` und `_`, etwa `S1` |
| `art` | Text | `verhalten` für eine sichtbare Änderung; `umbau` ändert keine Seite |
| `ziel` | Text | ein Satz, was danach anders ist |
| `bereich` | Text | Ordner unter `src/telco_radar/` mit `/` am Ende oder ein Modul `.py`; nur dort darf der Bau ändern. Vorlagen: `src/telco_radar/report/templates/` |
| `vorbild` | Text | Datei, an der sich der Bau orientiert |
| `abnahme` | Text | neuer Test `tests/…/test_*.py` |
| `erwarteteDateien` | Liste | Dateien, die der Bau voraussichtlich ändert |
| `seite` | Liste | betroffene Seiten, etwa `geraete.html` |
| `abhaengigVon` | Liste | IDs von Aufträgen, die schon gemergt sein müssen; sonst `[]` |
| `datenquelle` | Objekt | woher die Daten kommen; `{}` genügt |
| `wasDarfNiePassieren` | Objekt | alle vier Fälle als nicht leerer Text: `wiederholung`, `gleichzeitig`, `zeitueberschreitung`, `abbruch` |
| `erwarteterFehler` | Text | bei `verhalten` Pflicht: ein Stück der Fehlermeldung, mit der der Abnahmetest vor dem Bau fachlich scheitert. Bei `umbau` `null` |
| `migration` | Text oder `null` | nur wenn gespeicherte Daten umziehen |

## Abnahmetest

Der Abnahmetest muss die Seite wirklich rendern und die gerenderte Seite prüfen. Eine Vorlage als Text zu lesen ist rot (Regel Verhalten), ein Import privater Namen aus anderen Tests auch (`PLC2701`). Rendern aus dem Bestand:

```python
from bestand_pfad import abbild

from telco_radar.config import load_config
from telco_radar.report.html import render_site


def test_kopfzeile_der_geraeteseite(tmp_path):
    berichte = abbild(tmp_path)
    render_site(tmp_path / "site", berichte, load_config(tmp_path))
    seite = (tmp_path / "site" / "geraete.html").read_text(encoding="utf-8")
    kopf = '<p class="page-kicker">Deutschland · Geräte und Preise'
    assert kopf in seite, "Kopfzeile: erwartet Deutschland · Geräte und Preise"
```

Hält ein bestehender Test einen Text fest, den der Auftrag ändern soll, scheitert der Auftrag: Der Bau ändert keine bestehenden Tests.

## Beispiel

```json
{
 "id": "S1",
 "art": "verhalten",
 "ziel": "Die Kopfzeile der Geräteseite heißt Deutschland · Geräte und Preise",
 "bereich": "src/telco_radar/report/templates/",
 "erwarteteDateien": ["src/telco_radar/report/templates/geraete.html.j2"],
 "vorbild": "src/telco_radar/report/templates/geraete.html.j2",
 "seite": ["geraete.html"],
 "datenquelle": {},
 "abnahme": "tests/test_s1_kopfzeile.py",
 "erwarteterFehler": "Kopfzeile: erwartet Deutschland · Geräte und Preise",
 "abhaengigVon": [],
 "migration": null,
 "wasDarfNiePassieren": {
  "wiederholung": "zweimal gerendert steht dieselbe Kopfzeile da",
  "gleichzeitig": "keine andere Seite ändert ihren Text",
  "zeitueberschreitung": "die Seite rendert ohne Netz",
  "abbruch": "eine fehlende Datenquelle zeigt die Seite mit benannter Lücke"
 }
}
```

## Wenn der goldene Lauf rot ist

„goldener Lauf rot“ heißt: Die Aufnahme kennt eine Anfrage nicht mehr, etwa weil sich eine Quelle oder ein Prompt geändert hat. Das kann nur eine neue Aufnahme heilen (`make golden-aufnehmen`). Die zwei Wiedergaben kosten je Auftrag rund 2 Minuten.
