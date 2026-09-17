# P3-Re-Check — Notiz (frischer Prüfer, 18.09.2026)

Gegenstand: Fix-Notiz `p3/fix.md` gegen `p3/pruefung-code.md` + `p3/pruefung-sicht.md`.
Basis: HEAD `64a8f2a` + uncommitteter P3-Diff. `render_site(..., cfg)` neu gerendert
→ **byte-identisch** zu `site/` (md5 geraete.html/app.js/style.css/beide Modell-CSVs).
Nichts committet, nichts unter `data/state` geschrieben. Messungen am echten
Server 127.0.0.1:8769 (Playwright-Chromium, 1440×900 und 390×844) plus statische
Vollzählung (BeautifulSoup).

## 1. Umschalter-Klicks beider Ansichten nachgestellt — beide Fixes wirken

**Fall 1 (Sicht W1, „Sortierung hängt an unsichtbarer Spalte"):** Default
Barpreis (Knopf `aria-pressed=true`) → Klick Sortierkopf „Einzelgerätepreis"
(=ab, aria descending, sichtbar; Barpreis monoton 3.099,90 → 2.197,00) →
Wechsel auf TCO: aktiver Kopf **tco**, sichtbar, TCO **monoton fallend
3.357,66 → 2.927,80 → 2.705,66 → 2.243,66 → 2.051,80 … → 1.895,80** — exakt
die Werte aus fix.md. Entfaltet (111 Zeilen): alle 92 Werte monoton, die
19 leeren an Position 92–110 (Regel „ohne Zahl ans Ende" greift; letzte
Zahl davor 511,66).

**Fall 2:** In TCO nach „Δ zu Vodafone" sortiert (delta/ab/descending,
sichtbar) → Wechsel auf Barpreis: **0 Pfeile** (`data-vor` überall entfernt),
Reihenfolge == Server-Ordnung nach Reload (iPhone 17 Pro 256 / Fairphone 6 /
Pixel 11 256 / Nothing Phone (3) 256 …) — exakt die fix.md-Reihenfolge.

**Wechsel ohne Reload:** Marker-Fenster bleibt über beide Wechsel gesetzt.
Beide Knöpfe auf 390 px nebeneinander sichtbar (Sicht-Prüfer), Querscroll
unten bestätigt.

## 2. Abnahme DIE EINE REGEL — Vollmenge, beide Ansichten

Statisch über alle 111 Modellzeilen (`textContent`, sieht auch die
ausgeblendete Spalte): **„ohne Preis" 0×** (auch get_text: 0), „kein Preis
gemessen" 0×. **110× „ab X € bei Y ↗ Datum" + 1× „nur im Bündel ab 25,99
€/Monat bei 1&1 · Beleg"** (Nothing Phone (4a) Pro 128 GB — dieselbe Zeile
trägt TCO 803,66 / Ø 33,49). **TCO: 92× Zahl + 19× „kein Bündel gemessen"**;
Delta: 54 Werte + **38× „keine Referenz"** + 19× „–" (bündellos, Grund steht
in der TCO-Zelle) = 111. Spanne: 49 + **40× „ein Preis"** + 22× „–".
Preisformate je Spalte normalisiert: Barpreis 110/1 (Regelform plus der
benannte Bündel-Zustand), TCO 92/19 — ein Format je Spalte je Ansicht.

## 3. Stichproben gegen die Stores nachgerechnet

- **Barpreis 5/5 OK** (min über NEU-Listungen, aktuelle Messung):
  Pixel 10 Pro Fold 256 → 1.603,00 o2 · Xiaomi 17T Pro 512 → 865,00
  congstar · iPhone Air 256 → 891,00 congstar · Fairphone 6 256 → 539,00
  ALDI TALK · Galaxy A17 128 → **169,00 ALDI TALK**. Die A17 führte kurz auf
  eine „Abweichung": DB-`erstpreis` 129,00 ist die ERSTE Messung; die Seite
  nimmt die rechte Kante der Historie (17.09.: 169,00, 5G-Variante).
  Messartefakt meiner ersten Probe, Seite korrekt.
- **Refurbished draußen (B1):** iPhone 14 128 zeigt 721,00 (neu), obwohl
  zwei refurbished-Listungen 445,00 tragen.
- **TCO 6/6 auf den Cent** (`tco_24` selbst nachgerechnet aus
  `geraete_tco.json`-Sätzen): iPhone 18 Pro Max 2048 → 3.357,66 (1&1) ·
  Z Fold8 256 → 1.573,00 (congstar) · iPhone Air 256 → 1.060,75 (o2) ·
  iPhone 17 256 → 949,00 (congstar; o2-refurbished 1.048,75 bleibt draußen) ·
  Xiaomi 17T 256 → 760,75 · Galaxy A17 128 → 511,66.
- **„nur im Bündel":** 25,99 €/Monat = Store-Satz 1&1 „1&1 All-Net-Flat S"
  (mtl. 25,99, Zuzahlung 140, 36 Monate) — mit Beleglink.

## 4. S1/S2/S4 aus pruefung-code.md

- **S2-1 behoben und scharf getestet:** `geraete_view.py:1645` hält die
  Bündel-Quelle konditional (`tco_db.buendel() if tco_db.lesbar else
  _buendel_aus_listungen(bestand)`, Funktion Zeile 899–929). E2E-Test
  `test_seiten_zahlen.py::test_der_katalog_uebersteht_einen_unlesbaren_
  tco_store` schreibt WIRKLICH kaputtes JSON (`'[KAPUTT'`), rendert neu und
  assertet 0× „ohne Preis" + Bündel-Angabe mit Listungs-Beleg — 1 passed.
  Unit-Test `test_unlesbarer_store_fraegt_die_listungen_ab_s2_1` grün.
- **S4-1 behoben:** `geraete-modell-tco.csv` Tarifband **Klein 48 / Mittel
  41 / Groß 3 / leer 19** (= bündellos); beide CSVs 111 Zeilen, BOM,
  Semikolon, Dezimalkomma.
- **S4-4** (Kommentar „BEWUSST ohne cfg", `test_seiten_zahlen.py:2162`) und
  **S4-6** (Guard-Kommentar `geraete_view.py:964`) vorhanden.
- S4-2/S4-3/S4-5 bewusst offen (Lead-/P4-Entscheidung) — Begründungen
  nachvollziehbar.

## 5. Mehr-Button (Sicht W2 „nicht reproduzierbar") — Fix-Position bestätigt

Vor Klick sichtbar („alle 111 Zeilen zeigen"); nach Klick `gr-alarm--alle`
gesetzt, 111 Zeilen sichtbar, Button **unsichtbar** (offsetParent null; der
ganze Erklärabsatz wird versteckt). Der vom Sicht-Prüfer beschriebene
„stehen gebliebene" Button existiert am gerenderten Stand nicht. Kein Fix
nötig — Dokumentation der Fix-Notiz stimmt.

## 6. Suite und Abnahme

- `-k geraete`: **1429 passed / 3 failed / 6 skipped** (215 s) — exakt der
  Fix-Stand; die 3 Roten sind die dokumentierten vorbestehenden (Galaxy Tab
  S11 Ultra Auto-Katalog; Nachtlauf-Nullzeilen; iPhone-18-Querlinks auf
  `apple-iphone-18-pro-*`), am Stand reproduziert, NICHT gefixt (Auftrag).
- `tests/test_seiten_zahlen.py`: **104 passed**.
- `pruefe_portal.py`: **18 bestanden / 0 durchgefallen / 0 nicht prüfbar**
  (11b: tco 2593 / radar 2997 / verlauf 1809 / **katalog 1924 px** < 3000;
  11c Graphfalz 834 < 844).
- Screenshots (angesehen): `screenshots/recheck-1440-tco.png` (TCO-Ansicht,
  Knopf rot aktiv, Zeilen „ab X € bei Y" mit Datum) und
  `screenshots/recheck-1440-sortiert-tco.png` (nach Sortierung+Wechsel:
  iPhone 18 Pro Max 2048 führt, TCO-Spalte absteigend, aktiver Kopf) —
  Layout sauber, kein Überlapp/Schnitt.

## 7. Rest (nichts davon ein FAIL der P3-Abnahme)

1. **fix.md-Zahl falsch:** Erklärsatz misst **23 Wörter**, nicht 18 (Satz ist
   derselbe wie zitiert). Richtung stimmt (33 → 23); Sicht-Prüfers Ziel ~15
   nur teilerfüllt — Wortzahl ist kein Abnahmekriterium, F1-Text-Deckel
   kommt in P4.
2. **Kein Deep-Link-Parameter für die Ansicht** (`?ansicht=tco` fehlt) —
   externe Links landen immer auf der Barpreis-Ansicht. P4 2c (Sprungziele/
   Querlinks) ist der natürliche Ort.
3. Bewusst offen vom Fix geführt (Lead/P4): S4-2 Export-Knopf-Einheiten,
   Kleineres 6 (sticky Modellkopf mobil), Kleineres 7 (19 bündellose
   sammeln), S4-3/S4-5.
4. Beobachtung Datenpflege (kein P3-Thema): ALDI Galaxy A17 LTE (129) und
   5G (169) laufen in EINER `listung_id` — die Seite zeigt korrekt die
   letzte Messung, aber die SKU-Trennung bleibt die bekannte B2-Klasse.
5. Der leere Vorlagen-Zweig „kein Preis gemessen" bleibt unbesetzt (0×) —
   bewusst (Regel bleibt laut, Bau-Kommentar).
