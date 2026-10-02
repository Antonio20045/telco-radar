# P3-Re-Check — Urteil (18.09.2026)

**Prüfer:** frischer Re-Check-Prüfer ohne Bau-Kontext. **Basis:** HEAD `64a8f2a`
+ uncommitteter P3-Diff; `site/` per `render_site(..., cfg)` neu gerendert und
**byte-identisch** bewiesen. Messungen: echter Server 127.0.0.1:8769,
Playwright-Chromium (1440×900, 390×844), statische Vollzählung,
Selbst-Nachrechnung der Stichproben gegen `geraete_db.json` /
`geraete_tco.json` / `geraete_preise.jsonl`. Nichts committet, nichts unter
`data/state` geschrieben, Server gekillt.

## Urteil: FREIGEGEBEN (durch=true)

Jeder FAIL beider Prüfungen ist behoben oder (Wesentliches 2) am gerenderten
Stand widerlegt. Die P3-Abnahmekriterien sind vollständig grün. Keine neuen
Befunde jenseits dokumentierter Reste. Messzahlen und Belege:
`p3/notiz-recheck.md`.

## Die FAILs der Sicht-Prüfung (durch=false-Gründe), einzeln

| # | Befund | Re-Check-Ergebnis |
|---|---|---|
| W1 | Sortierung hängt nach Ansichtwechsel an unsichtbarer Spalte | **BEHOBEN, live nachgestellt.** Fall 1: aktiver Kopf wechselt auf TCO-24 (sichtbar, aria descending), Werte monoton fallend 3.357,66 → 1.895,80 (entfaltet alle 92 monoton, 19 leere an Pos. 92–110). Fall 2: 0 Pfeile, Reihenfolge == Server-Ordnung (über Reload gegengeprüft) |
| W2 | Mehr-Button ohne Zustandswechsel | **AM STAND NICHT REPRODUZIERBAR — Fix-Dokumentation bestätigt.** Nach Klick: `gr-alarm--alle` gesetzt, 111 Zeilen sichtbar, Button verschwindet (offsetParent null). „Steht da und tut nichts" existiert nicht |
| W3 | stummes „–" in der Delta-Spalte | **BEHOBEN.** 38× „keine Referenz" (mit title-Grund), 19× „–" nur bei bündellosen Zeilen, deren TCO-Zelle den Grund nennt; 54 Werte — 54+38+19 = 111 |

Kleineres 4 („ein Preis" statt „–": 40×) und 5 (Erklärsatz gekürzt) umgesetzt;
Kleineres 6/7 als Lead-/P4-Entscheidung geführt — tragfähig begründet.

## S1/S2 aus pruefung-code.md

**S2-1 behoben:** konditionale Bündel-Quelle (`geraete_view.py:1645`,
`_buendel_aus_listungen` :899). Der E2E-Test schreibt wirklich kaputtes JSON,
rendert neu und hält 0× „ohne Preis" samt Bündel-Angabe mit Listungs-Beleg
fest — scharf (die Fixture erzeugt den Fall, nicht nur seine Form).
S4-1 (Tarifband Klein 48 / Mittel 41 / Groß 3 / 19 leer), S4-4- und
S4-6-Kommentare verifiziert; S4-2/S4-3/S4-5 bewusst offen.

## Abnahme P3 (Strategie §P3)

- **0× „ohne Preis"** im gerenderten Katalog (beide Ansichten, Vollmenge,
  versteckte Spalten inklusive) — vorher 36×.
- **Ein Preisformat je Spalte je Ansicht** (normalisiert: Barpreis 110
  Regelform + 1 benannter Bündel-Zustand; TCO 92 + 19 benannter Leerzustand).
- **Reiterhöhe Katalog 1924 px < 3000** (pruefe_portal 11b; 11c 834 < 844).
- **Umschalter ohne Reload** (Marker-Fenster überlebt beide Wechsel),
  Knöpfe auf 390 px nebeneinander sichtbar; **mobil 390 ohne Querscroll**
  in beiden Ansichten, auch entfaltet (scrollWidth = 390 = Viewport).
- **Stichproben gegen die Stores:** Barpreis 5/5 (A17: Seite nimmt die
  letzte Messung 169,00 vom 17.09., nicht den `erstpreis` 129,00 — korrekt),
  TCO 6/6 auf den Cent selbst nachgerechnet, refurbished bleibt draußen
  (iPhone 14: 721 statt 445), „nur im Bündel" 25,99 €/Monat = Store-Satz
  mit Beleg. Beide Modell-CSVs: 111 Zeilen, BOM/Semikolon/Dezimalkomma.
- Screenshots (Auge): `p3/screenshots/recheck-1440-tco.png`,
  `recheck-1440-sortiert-tco.png` — TCO-Ansicht sauber, sortierte Ansicht
  mit sichtbarem aktivem Kopf und absteigender Spalte.

## Suite

`-k geraete`: **1429 passed / 3 failed / 6 skipped** — kein neues Rot.
Die 3 Roten sind die bekannten vorbestehenden (Galaxy Tab S11 Ultra
Auto-Katalog · Nachtlauf-Nullzeilen · iPhone-18-Querlinks), am Stand
reproduziert und dokumentiert, nicht gefixt (Auftrag).
`tests/test_seiten_zahlen.py`: 104 passed. `pruefe_portal.py`: **18/0/0**.

## Rest (keine FAILs, der Lead sollte sie kennen)

1. **fix.md nennt 18 Wörter für den Erklärsatz — real 23.** Richtung stimmt
   (33 → 23), die Zahl ist falsch; Wortzahl ist kein Abnahmekriterium
   (F1-Text-Deckel in P4).
2. **Kein Deep-Link-Parameter für die Ansicht** (`?ansicht=tco`): externe
   Links landen stets auf der Barpreis-Ansicht — P4 2c (Sprungziele) ist
   der natürliche Ort dafür.
3. Bewusst offen (Lead/P4): S4-2 Export-Knopf-Einheiten, Kleineres 6
   (sticky Modellkopf mobil), Kleineres 7 (19 bündellose sammeln).
4. Datenpflege-Beobachtung (P5/Beobachtung, kein P3-Thema): ALDI Galaxy A17
   LTE (129 €) und 5G (169 €) teilen eine `listung_id` — die Seite zeigt
   korrekt die letzte Messung; die SKU-Trennung bleibt die bekannte
   B2-Messlücken-Klasse.
5. Vorlagen-Zweig „kein Preis gemessen" unbesetzt (0×) — bewusst, die Regel
   bleibt laut.
