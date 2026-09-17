# P1 — HARTE SICHT-Prüfung (F2 Rechenweg-Panel, F3 Modell-Karten)

Datum: 17.09.2026 · Prüfer: Sicht-Prüfer ohne Bau-Kontext (frischer Blick wie Antonio)
Methode: lokaler Server (`127.0.0.1:8765`, site/-Stand des Working Tree), Playwright/Chromium, 1440×900 und 390×844, echte Klicks, Nachrechnen aller Summen, Abgleich gegen `data/state/geraete_tco_historie.jsonl`.

Screenshots (alle unter `p1/screenshots/`):
- `01-vergleich-desktop-viewport.png` — „nachher", Vergleichs-Reiter 1440×900
- `02-panel-punkt1.png`, `02-panel-preiszahl.png`, `06-panel-nur-element.png` — „panel-offen" (per Punkt, per Satzzahl, Panel als Element)
- `03-karten-nah.png`, `07-kacheln-element.png` — „karten-nah"
- `04-mobil-viewport.png`, `05-mobil-panel.png` — „mobil" 390×844

---

## F2 — Rechenweg je Messung: **PASS mit Auflagen**

### Was bewiesen ist (Klick-für-Klick)

1. **Klick auf einen Kurvenpunkt öffnet den Rechenweg genau dieser Messung.** Jeder Punkt trägt `aria-label="Rechenweg öffnen: Vodafone, Messung 2026-09-12"`, ist 25px groß (hit-Fläche, sichtbar 9px), tastaturerreichbar (Enter öffnet, nach 32 Tab-Stops erreicht).
2. **Die Zahlen sind die von DAMALS — mit dem Antonios-Fall live bewiesen.** o2/1&1 haben im Bestand echte Preissprünge; das Panel zeigt je Messtag die historischen Faktoren:
   - 1&1, iPhone 17 256 GB, **15.09.**: Zuzahlung 280,00 € + 39,90 € + **24 × 37,99 €** = 1.231,66 € TCO-24
   - 1&1, iPhone 17 256 GB, **16.09.**: Zuzahlung 340,00 € + 39,90 € + **24 × 42,99 €** = 1.411,66 € TCO-24
   Das ist wortwörtlich „morgen 38 × 24, übermorgen 43 × 24" — verschiedene Tage, verschiedene Rechenwege, korrekte Beleg-Abrufdaten (15.09./16.09.).
3. **Klick auf die PREISZAHL im Antwort-Satz** (fett, `cursor:pointer`, Klasse `gr-zr-zahl--klick`) öffnet den Rechenweg genau dieser Zahl: Satz nennt congstar 1.093,00 € → Panel zeigt congstar, 24 × 15,00 € Tarif + 24 × 30,50 € Rate + 1,00 € = 1.093,00 €. Passt.
4. **Alle Summen nachgerechnet, alle korrekt** (Vodafone, congstar, Telekom, 1&1; Beispiel Telekom: 99,00 + 39,95 + 718,80 + 712,80 = 1.570,55 ✓). 1&1 zeigt ehrlich „Bündelpreis (Tarif und Gerät zusammen)" statt einer erfundenen Aufteilung.
5. **Verständlichkeit < 10 Sekunden: ja.** Formelzeile „24 × 31,95 € = 766,80 €" liest sich ohne Erklärung; Panel erscheint im selben Viewport unter dem Graph (kein Scroll-Sprung nötig).

### Auflagen (Fix vor Abnahme)

- **A1 — Die Karten-Preiszahl öffnet keinen Rechenweg.** Antonios wörtliche Geste ist „wenn man auf den Preis drückt". Die sechs 21px-Preise der Modell-Karten (die prominentesten Preiszahlen des Reiters) wählen nur das Modell; `cursor` bleibt default, kein Panel. Der Rechenweg ist nur über die 9px-Punkte und die Satzzahl erreichbar.
  **Fix:** `.gr-zr-k-preis` (bzw. die ganze Karten-Preisgruppe) als dritten Eingang an `zrPanelZeigen()` hängen — Rechenweg der Front-Messung (günstigster Anbieter am letzten Messtag, dasselbe Template, das der Satz nutzt), `stopPropagation`, Hover-Unterstreichung am Preis. Aufwand klein, Wirkung groß: drei Eingänge, eine Wahrheit.
- **A2 — Das Panel ist „nur Zeilen" auf toter Halbleite.** 1184px breit, der Inhalt endet bei ~575px; rechte Hälfte komplett leer. Es gibt Trennlinien und eine gerahmte Summe (mehr als Fließtext), aber keine Visualisierung der Posten. Antonio: „Nicht einfach nur Zeilen schreiben, ein bisschen komplizierter."
  **Fix (eine der beiden):** (a) Panel auf ~680px begrenzen — Quittungsformat, die leere Hälfte verschwindet; oder (b) die freie rechte Hälfte mit einem proportionalem Posten-Balken nutzen (Tarif / Geräterate / Zuzahlung gestapelt, Summe = 100%, Vodafone-rot nur am eigenen Angebot). (b) ist das, was F2 eigentlich will.
- **A3 — Die Restschuld fehlt im Panel.** „24 von 36 Raten" steht als 11px-Fußnote; WAS danach noch offen ist (12 × 30,50 € = 366,00 €), steht nur in der Bündelzeile, nicht im Panel. Ausgerechnet die Zahl, die den TCO-24 vergleichbar macht, fehlt an der Stelle, wo man rechnet.
  **Fix:** eigene Zeile „danach noch offen: 12 × 30,50 € = 366,00 €" unter der Summe; „24 von 36 Raten" von 11 auf 13px.
- **A4 — o2 ist in KEINER Zeitreihe klickbar.** Über alle geprüften Modelle (iPhone 17 Pro/17, Pixel 11, S26 Ultra, Z Fold8) zeigen die Charts nur Telekom/Vodafone/1&1/congstar — o2, der Anbieter mit den meisten Bündeln des Bestands, fehlt als Reihe überall (Band-Zuordnung: o2-Unlimited-Tarife tragen keine GB-Zahl → kein Band). Der Rechenweg eines o2-Bündels ist im Vergleichs-Reiter über Punkte unerreichbar.
  **Fix (Daten-Scope, hier gemeldet):** Unlimited-Tarife dem Band „Groß" zuordnen (unbegrenzt > 60 GB) oder als bandlose Reihe mit eigenem Label zeichnen. Ohne das bleibt F2 für den Preiskämpfer Nr. 1 ein Versprechen.
- **A5 — Mobil: Belegzeile klebt an der Kante.** Panel belegt 587–844px, `belegBottom == viewportH == 844` — die letzte Zeile steht ohne einen Pixel Luft an der Unterkante; ein längerer Anbietername wird abgeschnitten.
  **Fix:** nach dem Öffnen `panel.scrollIntoView({block:'nearest'})` plus 12px bottom-padding.

### Detailbefunde (positiv)

- Bandwechsel schließt ein offenes Panel korrekt (verifiziert: Klein/congstar-Panel offen → „Groß" geklickt → Panel `hidden`, Satz neu).
- Belegzeile mit Abrufdatum der Messung und echtem Link (↗) — Nachprüfbarkeit wie gefordert.
- ×-Schließen vorhanden, Panel-Titel nennt Anbieter + Messdatum in einem Zug.

---

## F3 — Modell-Karten prominent: **FAIL**

### Messlatte und Messung

| Vorgabe | Messwert | Urteil |
|---|---|---|
| Preiszahl ≥ 20px | **21px** (`1.093,00 €`), Kartenname 12–13px | knapp erfüllt |
| alle 6 Karten im ersten Viewport bei 1440 | ja — y=528, Höhe 101px, plus Chart-Anfang im selben Bild | erfüllt |
| alle 6 Karten im ersten Viewport bei 390 | **nein** — Karten stehen in einer Querwisch-Reihe (`scrollWidth` 966px bei 306px sichtbar): ~2,5 von 6 Karten sichtbar, Rest nur per Wischen; Karten beginnen zudem erst bei y=608 (über ihnen: Titel, Suche, Bänder, Antwort-Satz, SO GERECHNET) | **verfehlt** |
| aktive Markierung klar | erste Karte: 2–3px dunkler Umriss + `aria-pressed` | funktional ja, optisch schwach |
| „richtig geiles Design, was Spaß macht" | Bildurteil (zwei unabhängige Analysen): „flat, borderless, keine Schatten, kein Karten-Hintergrund — utility chips, nicht Feature"; Design 5/10 | **verfehlt** |

### Befunde

- **B1 — Mobil ist die Kernmesslatte verfehlt.** 390×844 zeigt die Karten als Wischstreifen am unteren Rand des Viewports; „alle 6 im ersten Viewport" gilt dort für keine Karte außer den ersten zweieinhalb. **Fix:** unter 480px ein 2-spaltiges Grid (3 Reihen à 2 Karten ≈ 290px hoch) — alle 6 passen dann OHNE Wischen in einen Viewport, die Messlatte wäre auch mobil erfüllt. Die Wischreihe darf oberhalb 480px bleiben.
- **B2 — Die Karten reagieren nicht auf den TARIFBAND-Umschalter.** Antwort-Satz und Chart wechseln (Klein 1.093 → Groß 1.237), aber die 6 Karten zeigen in allen Bändern denselben bandunabhängigen „ab"-Preis. Für den Nutzer sieht der Umschalter damit „halb tot" aus: die prominenteste Ebene steht still. **Fix:** Karten-Preis auf das gewählte Band umrechnen (leerer Anbieter im Band: „—" mit Punkte-Reihe als Indikator), oder die Kartenreihe beim Bandwechsel mindestens sichtbar neu sortieren/kennzeichnen.
- **B3 — Zu flach für „Spaß".** Im Zeitungsstil (Linien statt Kästen) ist Flatness Programm — aber dann muss die Auswahl stärker tragen: Umriss der aktiven Karte in Vodafone-Rot und/oder 3px plus leicht aufgehellter Kartengrund; inaktive Karten mit Hover-Unterstreichung des Modellnamens. Die Anbieter-Punkte (4 Farbpunkte je Karte) sind mit 8px so dezent, dass sie in der Bildanalyse nicht wahrgenommen wurden → 10px mit 1px Weißrand.
- **B4 — Das Bewegungs-Delta ist die Story und flüstert.** „↑ +215 € in 5 Tagen" (Z FOLD8) ist der emotionalste Fakt jeder Karte — es steht in ~11px und wirkt wie Metadaten. **Fix:** steigt/sinkt farbig (rot/grün) und eine Stufe größer; „±0 €" darf grau und klein bleiben.

---

## F1-Rahmen — Unruhe: **gehalten (nicht verschlechtert)**

- P1 fügt **keine neuen Dauertextblöcke** hinzu: das Panel ist `hidden` bis zum Klick; Karten sind Zahlen-Chips; „Messtage"-Zeile, Legende, Antwort-Satz und „SO GERECHNET" sind E2-Bestand.
- Sichtbare Textblöcke im ersten Desktop-Viewport: 3 (Antwort-Satz 19px, SO GERECHNET-Label, Messtage-Zeile). Chips: 0. Aufklapper standardmäßig zu.
- Der längste Textblock bleibt der 19px-Antwort-Satz — er ist E2 und damit außerhalb des P1-Scopes; festgehalten, weil F1 („Ich will keinen Text sehen") an ihm hängt, nicht an P1.

---

## Verbesserungsliste (Scope: Vergleichs-Reiter — Panel + Karten), bis nichts mehr einfällt

1. **Karten-Preis klickbar** → Rechenweg der Front-Messung (A1, wichtigster Einzelpunkt).
2. **Panel-Quittungsformat** (~680px) oder **proportionaler Posten-Balken** in der freien rechten Hälfte (A2).
3. **Restschuld-Zeile** im Panel („danach noch offen: … €") (A3).
4. **o2-Reihe** ins Chart bringen (Band „Groß" für Unlimited oder bandlos) (A4).
5. **Mobil: Panel-ins-View scrollen + bottom-Padding** (A5).
6. **Mobil: 2-spaltiges Karten-Grid** unter 480px (B1).
7. **Bandgekoppelte Karten-Preise** oder sichtbare Reaktion der Karten auf den Bandwechsel (B2).
8. **Aktive Karte stärker**: roter 3px-Umriss + aufgehellter Grund; Hover-Unterstreichung inaktiver Karten (B3).
9. **Anbieter-Punkte 10px + Weißrand** — sonst sieht sie niemand (B3).
10. **Delta farbig und größer** (steigt rot / sinkt grün, ±0 grau klein) (B4).
11. **Hover-Vorschau am Kurvenpunkt** („congstar · 17.9. · 1.093 €") vor dem Klick — das aria-label existiert, Maus-Nutzer sehen vor dem Klick aber nichts; `<title>` am Kreis genügt als Minimallösung.
12. **Panel-Titel mit Anbieter-Farbpunkt** (dieselbe Farbe wie die Linie/Legende — Kopplung, die das Lesen des Charts lehrt).
13. **Belegzeile rechts unten im Panel ausrichten**, ×-Button auf ≥28px hit-Fläche vergrößern (jetzt 17px Schrift auf kleinem Button).
14. **Tab-Stops zum Punkt** (derzeit 32) — pragmatisch: erst hit-Kreise in die Tab-Ordnung nehmen, bevor Suchfeld/Bänder/Karten kommen, oder `tabindex` der Karten nach den Punkten.
15. **Telekom-Einzelmesstag** (15.09., nur 1 Punkt, keine Linie): im Chart als „erstmals gemessen" kennzeichnen (Punkt-Halo), sobald ein zweiter Tag kommt, wird er zur Linie — Datenlage, aber einen Punkt ohne Kontext liest niemand.

---

## Gesamturteil

**F2: PASS mit Auflagen** — der historische Rechenweg je Messung funktioniert, ist korrekt und ehrlich (1&1-Sprung bewiesen); die Auflagen A1 (Karten-Preis) und A2 („nur Zeilen") sind genau die Punkte, an denen Antonios Zitat hängt.
**F3: FAIL** — Desktop-anordnung ok, aber mobil ist die gesetzte Messlatte (alle 6 im Viewport) klar verfehlt, das Design bleibt „utility chips" statt „geiles Design", und die Karten reagieren nicht auf den Band-Umschalter.
**Unruhe: gehalten.**

**Phase P1 ist NICHT durch** — B1/B2 (F3) und A1 (F2) sind vor der Abnahme zu fixen; alles Weitere ist verbesserbar ohne die Substanz zu gefährden. Die Substanz selbst — Punkte-Panel mit historischen Messwerten, zwei funktionierende Eingänge, korrekte Summen — steht und ist gut.
