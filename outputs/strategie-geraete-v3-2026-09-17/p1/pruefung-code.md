# Prüfbericht CODE — Phase P1 (Geräteseite: Rechenweg-Panel, Modell-Karten)

17.09.2026. Prüfer: diff-reviewer (CODE). Grundlage: `git diff` Working
Tree gegen HEAD `9f5235d`, Bau-Notizen A1–A4, `STRATEGIE_GERAETE_V3.md`
§P1, `docs/clean-code-referenz.md`, CLAUDE.md-Hausregeln.
**Ergebnis: 0 × S1, 0 × S2, 5 × S3, 5 × S4.** Die Kernzusicherungen von
P1 halten der Nachrechnung stand.

## Nachgerechnete Kernzusicherungen (alle bestanden)

| Zusicherung | Nachweis |
|---|---|
| Template rechnet JE Messung die Historien-Zeile nach | **Alle 2562** Zeilen `geraete_tco_historie.jsonl` unabhängig nachgerechnet: Posten × Faktor = eingefrorenes `gesamt`, 0 Abweichungen, 0 Zeilen ohne Tarifposten; 49 Template-Stichproben aus `site/data/geraete-zeitreihe.html` gegen die JSONL korrekt (27 eindeutig, 22 mehrdeutige SKU-Farb-Dubletten mit identischer Zahlmenge); Posten-Schlüssel in `_rechung` sind EXAKT die f-String-Konstruktionen von `tco_24` |
| 0 Rechenoperatoren im JS | app.js-Diff komplett gelesen: nur Array-Index, `indexOf`, Attribut-Montage; Panel = `importNode`-Klon des Server-Templates (Browser-Test prüft `isEqualNode`); `parseFloat` nur in der vorbestehenden Bündel-Sortiertabelle |
| Ranking/PM-7 und KACHELN_MAX unverändert | `sorted(kachel_werte, key=(-anbieter, -punkte, id))[:KACHELN_MAX]` wörtlich unverändert; `meta`-Feld war nur Anzeige |
| Delta erster→letzter Messpunkt | `_bewegung`: Front = Minimum je Messtag, `round(,2)`, deutsche Formate (`_euro0`), <2 Messtage → None; Gegenrechnung aus der rohen Historie im Test |
| site/app.js + site/style.css synchron mit templates/ | `diff -q` identisch |
| Kein State-Commit, keine Secrets | Diff enthält kein `data/state/`, keine Credentials |

Suite: `pytest -q -k geraete` = **1402 passed / 3 failed / 6 skipped** —
die 3 Roten sind vorbestehend (A4-Worktree-Beweis am HEAD; Fehler-IDs
`apple-iphone-18-*` bzw. Auto-Katalog-Datenstand vom heutigen Stand-
Commit; keine der Ursachen-Dateien im P1-Diff).

## Befunde

### S3

**S3-1 — Panel-Schrift 11 px unter der 12-px-Regel, von keinem Test erreichbar.**
`src/telco_radar/report/templates/style.css:3400` (`.gr-zr-pk`) und `:3405`
(`.gr-zr-plabel`). Die Klammer „24 von 36 Raten" erklärt den Faktor der
Rechnung und das Etikett „TCO-24" benennt die Summe — das sind LESSENDE
Labels, nicht Meta-Etiketten der dokumentierten Ausnahme (chip, datum,
erst-wert). `test_keine_schrift_unter_zwoelf_pixel_im_sichtbaren_graphen`
misst nur das SVG; `test_keine_beschriftung_unter_zwoelf_pixeln` misst
`#tafel-tco *` — `<template>`-Inhalte leben im DocumentFragment und das
Panel entsteht erst nach Klick: beide Tests sehen die 11-px-Klassen nie.
A3 musste die Karten-Labels für dieselbe Regel auf 12 px anheben.
Auslöser: das erste Öffnen eines Panels. Fix: beide Klassen auf 12 px
stellen und einen der 12-px-Tests um einen geöffneten Panel-Fall ergänzen.

**S3-2 — Fallback zeigt bei fehlendem Template die Vodafone-Näherung für FREMDE Messungen.**
`src/telco_radar/report/templates/app.js` in `zrMessungOeffnen`:
`zrVorlage(anb, m) || zrVorlage('Vodafone', 'naeherung')`. Klick auf
einen o2-/Telekom-Punkt, dessen `_rechung()` None lieferte (Buendel
unlesbar → kein Template, Punkt existiert weiter), öffnet die
„Vodafone · Referenzrechnung" — eine falsche Antwort auf die Frage
„Rechne MIR DIESE Messung vor" in einem Bericht mit Belegzwang. Der
statische Leer-Hinweis („Zu dieser Messung steht kein Rechenweg bereit")
wird dadurch praktisch unerreichbar. Die Kette steht so in
`schnittstelle-rechenweg.md` (A1s Festlegung, A2 baute sie treu) — der
Fehler sitzt in der Festlegung. Auslöser: eine unlesbare Historien-Zeile
(im Bestand 0 von 2562, aber der Pfad existiert).
Fix: Näherungs-Fallback nur bei `anb === 'Vodafone'`, sonst Leer-Hinweis.

**S3-3 — Preiszahl wird bedingungslos klickbar gestylt, auch ohne Template.**
`src/telco_radar/report/templates/app.js` in `zrEingaengeRuesten`:
Klasse `gr-zr-zahl--klick`, `tabindex`, `title` „Rechenweg dieser
Messung öffnen" auf die erste `b.gr-zr-zahl` IMMER. Hat der genannte
Anbieter keine Serie/Templates (Paar mit heutigen Karten, aber ohne
zugeordnete Messung — dafür existiert der ehrliche Leer-Satz
`leer_text`), kehrt `zrPreiszahlOeffnen` lautlos zurück: fokussierbar,
geklickt, nichts. Dieselbe Klasse von Bedienelement, die B.3 bewusst
nicht baute. Auslöser: neues Paar ohne Historie-Zuordnung oder
Teilausfall der Aufbereitung. Fix: Klasse/title/tabindex nur setzen,
wenn `zrAnbieterDerPreiszahl()` einen Anbieter mit `zrVorlagen(anb)`
liefert.

**S3-4 — Karte misst mit zwei Maßstäben ohne Kennzeichnung.**
`src/telco_radar/report/geraete_zeitreihe.py` `aufbereiten()`:
`best_je` = bestes ECHTES Angebot über ALLE Bänder (ab-Preis), `leit_je`
= Leit-Paar nach (Anbieterzahl, Punkte) — `delta_text`/`punkte_html`
kommen aus dem Leit-Paar, das ein ANDERES Band sein kann als der
ab-Preis. Beide Zahlen sind einzeln belegt, aber dieselbe Karte kann
„ab 841 €" (Band klein) mit „↑ +130 €" (Band groß) kombinieren, ohne
dass ein Leser die unterschiedlichen Zuschnitte erkennt.
Auslöser: Modell, dessen günstigstes Bündel und sein reichhaltigstes
Band auseinanderfallen (im heutigen Bestand deckungsgleich — nicht
garantiert). Fix: Delta aus dem Band des ab-Preises rechnen ODER das
Band am Delta nennen (eine Entscheidung, keine Zwei-Maß-Karte).

**S3-5 — tmp_nachpruef/ ist ein 19-MB-Lauf-Artefakt unterm Repo-Wurzelpfad, nicht ignoriert.**
`/Users/antonio/Developer/telco-radar/tmp_nachpruef/` (kompletter
Site-Snapshot eines Nachführ-Agenten, untracked, nicht in `.gitignore`).
Noch nicht verletzt, aber `git add -A` vor dem P1-Commit nähme es mit —
harte CLAUDE.md-Regel „keine Lauf-Artefakte im Commit". Auslöser: der
Commit selbst. Fix: Verzeichnis löschen (Inhalt ist reproduzierbarer
Render) oder in `.gitignore` aufnehmen, bevor der Lead committet.

### S4 (gebündelt)

- **F1**: `_posten(label, betrag, anzahl, einzeln, klammer)` — 5 Argumente
  (lokale Closure in `_rechung`); ein `dataclass`-/dict-Bau würde 3 reichen.
- **P2 (Rand)**: `geraete_zeitreihe.py` trägt jetzt Aufbereitung + SVG +
  Rechenwegzerlegung + Karten-Maße; Hausstil der `report/*`-Module, aber
  das Modul nähert sich der Beschreibbarkeitsgrenze „ohne und/oder".
- **Typografie**: `↓ −130 €` (U+2212) neben `↑ +130 €` (ASCII-Plus) in
  derselben Kartenzeile — zwei Minus-/Plus-Zeichen für ein Muster; Tests
  pinnen beide, eine Schreibweise wäre ruhiger.
- **Rundung**: `_euro0` formatiert mit `:.0f` (half-even) — ein Delta von
  exakt x,50 € kann um 1 € von der kaufmännischen Erwartung abweichen;
  praktisch ohne Wirkung (Deltas sind ganzbetragsnah), nur benannt.
- **Fragmentgröße**: `geraete-zeitreihe.html` +1,84 MB (Faktor ~6 über der
  Strategie-Erwartung +150–300 kB; gzip +72 kB transportiert). Bewusst
  P5/PM-6 überlassen, dreifach dokumentiert (A1, A4, hier bestätigt) —
  keine P1-Korrektheitsfrage, aber die Lead-Entscheidung sollte mit
  dieser Zahl fallen.

### Clean-Code-Katalog, Kategorie für Kategorie

P1 Tests/Duplizierung/Namen/Klassenzahl: PASS (Suite s. o.; einzige
Text-Duplizierung `_NAEHERUNG_SATZ` ist wortgleich-geplant und per Test
an die Bündel-Karte gebunden). P2: FLAG S4 (s. o.). P3/P4: n. z./PASS
(keine neuen Verzweigungs- oder Abhängigkeitsbrüche). C1–C5: PASS
(datierte Regel-Kommentare sind Hauskonvention, keine toten/auskommentierten
Blöcke). E1/E2: n. z. F1: FLAG S4. F2–F4: PASS (keine Output-Args, kein
Flag-Arg, keine toten Funktionen — `_serien` hat Caller). G1: n. z. nach
Hauskonvention (Python baut HTML-Strings wie alle `report/*`). G2/G23:
PASS (Namen sagen was sie tun; `gr-zr-hit`-Fallstrick ist kommentiert).
J: n. z. (Python). N: PASS. T: PASS — Falztest-Umstellung begründet und
SCHÄRFER (Karten-unterkante ≤ 844 statt Chipzeilen-Höhe ≤ 96);
Karten-Zahlen mit `get_text()` OHNE Trenner (Hausregel); Panel-Zahlen
gegen zweiten Aufbereitungs-Lauf mit Negativ-Gegenprobe; kein Test
gelöscht oder abgeschwächt.

### CLAUDE.md harte Regeln

site/ von Hand gerendert: zulässig für Selbsttests, Commit-Entscheidung
beim Lead (Prozess OK). seen.jsonl: n. z. IDs aus Titeltext: n. z. (keine
neuen IDs; Historien-IDs unangetastet). Secrets: keine. Lauf-Artefakte:
S3-5. Kein data/state im Diff: PASS.

### Leer-/Fehler-/Fremdformatfälle

Leerer Zustand (`leer()`, Paar ohne Serie): Panel-Kette passt (S3-3 ist
der Rand). Fragment-Netzfehler: alter Block + Panel bleiben (dokumentiert,
konsistent). Fremdformat: unlesbare JSONL-Zeile wird übersprungen (stiller
Datenverlust im Graphen — aber derselbe vorbestehende Standard wie vor
P1); `geraete_tco.json` unlesbar → `log.warning` + leere Messungen, Seite
bleibt stehen. Buendel unlesbar → Punkt ohne Template → S3-2.

### Stille Verhaltensänderungen

Keine gefunden: `_serien()` Ableitung liefert identische Werte (strikt
`<` unverändert, am Fragment verifiziert); IIFE-Guard vorbestehend;
`meta`-Feld hatte nur einen Consumer (alte Kachel-Vorlage, mitgeändert).
