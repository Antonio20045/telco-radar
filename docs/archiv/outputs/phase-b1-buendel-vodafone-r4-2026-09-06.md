# B1 R4 — Render-Abschluss: die 253 Vodafone-Bündel im Site-Artefakt (06.09.2026)

Auftragsgrundlage: `BRIEF_B1_R4_RENDER.md`. Ausgangspunkt Commit `6301a74`
(„fix: B1 R3 - acht Regressionen der echten Vodafone-Buendel behoben"). Der
Vollsuite-Stand von dort (`2 failed / 2777 passed / 14 skipped`, die zwei
bekannten Promo-Screenshot-Fehler) ist laut Auftrag bereits durch die
Fremdabnahme gemessen und wird hier **nicht neu gelaufen** — dieses Ticket
ist ausschließlich das Rendern und Committen des Site-Artefakts.

## Ergebnis in einem Satz

`render_site()` einmal ausgeführt, dabei sind **ausschließlich zwei
HTML-Dateien** entstanden (`site/geraete.html`, `site/geraete-quellen.html`);
`site/data/keyword-index.json` wurde nach dem Render exakt auf den
committeten Stand zurückgesetzt (Diff = 0). Kein Parser, keine Daten-JSON/
JSONL, keine Konfiguration und kein Test wurden angefasst.

## Ausgeführter Befehl

Kein Pipeline-Lauf, kein Netzabruf — reines Neu-Rendern aus dem bereits
committeten Datenbestand, nach der in `CLAUDE.md` §6 dokumentierten Methode
(`render_site()` MIT `cfg`, sonst rendert die Seite stillschweigend halb):

```python
from pathlib import Path
from telco_radar.config import load_config
from telco_radar.report.html import render_site

root = Path(".").resolve()
cfg = load_config(root)
render_site(root / "site", root / "data" / "reports", cfg)
```

Ausgeführt mit `/opt/homebrew/bin/python3` (Homebrew-Python — auf diesem Mac
das einzige mit den Projektabhängigkeiten, siehe lokale Umgebungsnotiz).
Lief ohne Fehler durch, keine Exception, kein Log-Fehler.

## Welche Site-Dateien geändert wurden

```
$ git status --short   (unmittelbar nach dem Render)
 M site/data/keyword-index.json
 M site/geraete-quellen.html
 M site/geraete.html
```

Drei Dateien insgesamt — genau die durch die 253 Vodafone-Bündel (plus die
seit R2 unveränderten 63 o2-Bündel) betroffenen Seiten. Keine andere
HTML-Seite, kein Bild, kein CSS/JS und keine weitere `site/data/*.json` hat
sich verändert.

| Datei | Änderung | Ursache |
|---|---|---|
| `site/geraete.html` | 42.598 → 58.677 Zeilen (24.220 Insertions / 8.141 Deletions) | Der TCO-Reiter zeichnet jetzt 141 echte Vodafone-„unser Angebot"-Bündelkarten (statt bisher 0) sowie die dazugehörigen SIM-only-Referenzen, G1-Balken und die geänderten Näherungs-/Bündel-Zuordnungen aus R3 |
| `site/geraete-quellen.html` | 1 Zeile geändert | Die YAML-Kommentarzeile zu Vodafone (`config/geraete_quellen.yaml`) trägt seit dem 05.09.2026 den B1-Befund zur Tarifnamen-Auflösung (`offerCoreHash` → `/glados/v2/tariff/v2/hardware`, 339/596 aufgelöst, 253 gegen den Bestand gematcht) — die war seit R2/R3 committet, aber nie neu gerendert |
| `site/data/keyword-index.json` | nach Render 1 Zeile Diff (nur `"stand"`-Datum 2026-09-05 → 2026-09-06), **danach per `git checkout -- ` zurückgesetzt** | reine Datums-Zeitbombe wie in `CLAUDE.md` §6 dokumentiert — kein inhaltlicher Unterschied, Wortliste/Meldungszahl identisch |

## Konkreter Vodafone-Beleg im Render

Auszug aus `site/geraete.html` (Modell **Fairphone 6 256 GB**, Zeile
577ff.), eine echte Bündel-Karte mit Tarifname, Zuzahlung, Anschlusspreis
und Bindungsangabe. Im stale Render von `6301a74` stand für dieses Modell
noch die Leerkarte „Kein Bündelpreis erhoben, und kein Barpreis dieses
Geräts – ohne beides gibt es keine Vergleichszahl." — jetzt zeigt dieselbe
Kartenposition ein echtes, erhobenes Vodafone-Bündel:

```html
<article class="gr-kkarte gr-anb--vodafone gr-kkarte--eigen"
         data-anbieter="Vodafone"
         data-laufzeit="36"
         data-schnitt="36.33"
         data-gesamt="1307.8"
         data-einmalig="1.0"
         data-zustand="neu">
  <p class="gr-kk-kopf"><span class="gr-kk-anbieter">Vodafone</span> <span class="gr-kk-marke">unser Angebot</span></p>
  <p class="gr-kk-tarif">Mobil XS</p>
  <p class="gr-kk-leit"><b>Gerätepreis</b> <span>549,90 €</span></p>
  <p class="gr-kk-zweit">mit Tarif: <b>TCO-36</b> 1.307,80 €</p>
  <p class="gr-kk-omonat">Ø 36,33 €/Monat</p>
  <p class="gr-kk-basis">darin 24 von 36
  Monaten Tarif – so lange bindet er</p>
  <p class="gr-kk-bau">monatlich 31,95 € · Gerät einmalig 1,00 € · 540,00 € in 36 Raten à 15,00 € ·
    Anschlusspreis 0,00 €</p>
  <p class="gr-kk-24">nach 24 Monaten gezahlt: <b>1.127,80 €</b> · danach noch offen: 180,00 € (12 Geräteraten)</p>
</article>
```

Über die ganze Seite gezählt, je Vodafone-Kartentyp (`.gr-kk-marke`
unterscheidet echtes Bündel „unser Angebot" von gerechneter Näherung
„Referenzrechnung"; ohne diesen Span steht die Leerkarte „kein Bündelpreis
erhoben, kein Barpreis"):

| Kartentyp | vorher (`6301a74`, stale Render) | nachher (dieser Commit) |
|---|---|---|
| **echtes Vodafone-Bündel** („unser Angebot") | 0 | **141** |
| gerechnete Näherung („Referenzrechnung") | 30 | 1 |
| Leerkarte (keine Daten) | 29 | 23 |
| **Vodafone-Karten insgesamt** | 59 | 165 |
| alle TCO-Karten (`article.gr-kkarte`) | 422 | 672 |

Der Sprung von 0 auf 141 echte Bündelkarten ist die sichtbare Wirkung der
253 in R2 erhobenen und in R3 korrekt zugeordneten Vodafone-Bündel; das eine
verbleibende „Referenzrechnung"-Modell (`google-pixel-10-128`, siehe
R3-Bericht) hat weiterhin kein eigenes Bündel und zeigt deshalb zu Recht die
gerechnete Näherung statt einer erfundenen Zahl.

## `keyword-index.json`-Diff = 0

```
$ git diff --cached -- site/data/keyword-index.json
(kein Output)
$ git status --short
 M  site/geraete-quellen.html
 M  site/geraete.html
```

Die Datei ist nach `git checkout -- site/data/keyword-index.json` wieder
byte-identisch mit dem Stand von Commit `6301a74`; sie taucht im finalen
`git status` nicht mehr auf und wird nicht committet.

## Gezielter Artefakt-Check (statt Vollsuite, wie im Auftrag verlangt)

1. **Diff-Scope**: `git diff --stat -- ':!site'` liefert keine Zeile — kein
   Parser, keine Konfiguration, keine Daten-JSON/JSONL, kein Test wurde
   berührt. Nur `site/geraete.html` und `site/geraete-quellen.html` sind im
   finalen Commit enthalten.
2. **Kein Jinja-Rest**: `grep -c '{{' site/geraete.html` → 0,
   `grep -c '{%' site/geraete.html` → 0 (keine unaufgelösten Template-Marker).
3. **HTML parsebar**: `BeautifulSoup(html, "html.parser")` läuft ohne Fehler,
   Titel liest sich korrekt (`Vodafone Product and Services Insights ·
   Gerätepreise im Vergleich`), 672 `article.gr-kkarte`-Knoten gefunden
   (deckt sich mit dem `grep`-Zählwert).
4. **Vodafone-Bestand im Render sichtbar**: 141 echte Vodafone-Bündelkarten
   (von 165 Vodafone-Karten insgesamt, Rest Näherung/Leerkarte), plus die
   aktualisierte Quellenzeile auf `geraete-quellen.html` — beide direkt aus
   den 253 erhobenen Bündeln (R2) bzw. den acht in R3 korrigierten
   Erwartungswerten abgeleitet, ohne dass dieses Ticket eine Zeile
   Produktionslogik angefasst hat.

## Abnahmekriterien im Einzelnen

1. ✅ `render_site()` von Commit `6301a74` aus ausgeführt; die durch die 253
   Vodafone-Bündel betroffenen Artefakte (`site/geraete.html`,
   `site/geraete-quellen.html`) sind im Commit enthalten.
2. ✅ `site/data/keyword-index.json` exakt auf den Stand vor dem Render
   zurückgesetzt — kein Diff im Abschlusscommit.
3. ✅ Keine Anpassung an Parsern, Daten-JSON/JSONL, Konfiguration oder
   Tests — `git diff --stat -- ':!site'` ist leer.
4. ✅ Vollsuite nicht neu gelaufen; Maßstab bleibt der von der Fremdabnahme
   gemessene Stand `2 failed / 2777 passed / 14 skipped`. Stattdessen der
   gezielte Artefakt-Check oben.
5. ✅ Dieser Bericht.
6. ✅ Branch `openclaw/ticket-b1-buendel-vodafone` committet und gepusht,
   kein Merge nach `main`, kein Deploy-Hook berührt.

## Hausregeln eingehalten

Kein Hintergrundprozess, kein Monitor-Warten — das Rendern lief blockierend
im Vordergrund. Kein weiterer Netzwerkabruf: der gerenderte Bestand kommt
vollständig aus den bereits in R2/R3 committeten `data/state/*`-Dateien.

## Baumzustand

Ein Commit auf `openclaw/ticket-b1-buendel-vodafone`: die zwei neu
gerenderten Site-Dateien plus dieser Bericht. `site/data/keyword-index.json`
ist unverändert und nicht Teil des Commits.
