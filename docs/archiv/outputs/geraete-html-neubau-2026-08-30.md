# /geraete.html neu gebaut — Schlussliste, 30.08.2026

Auftrag: „Du baust die Darstellung von `/geraete.html` komplett neu."
Grundlage: `outputs/geraeteradar-wahrheit-2026-08-29.md` und
`outputs/geraete-preisradar-2026-08-10.md` — die im Auftrag genannten
`claude/…`-Pfade liegen im Claude-Projekt, nicht im Repo.

**Stand:** 2147 Tests grün, `pruefe_portal.py` 17 bestanden / 0
durchgefallen, live auf `main` (Deploy #122, `13bfbd9`).

---

## Was die Seite jetzt ist

Vier Reiter statt einer Grafik. Höhen an der **echten** Seite gemessen
(1440 px): Alarme 2949 · Katalog 2893 · Verlauf 2184 · Portfolio 2575 px.

| Reiter | Was er beantwortet |
|---|---|
| **Preis-Alarme** (Start) | „Wo liegen wir zurück?" Vier Kacheln (4/4/16/23 bei 47 Vergleichen), 12 Zeilen nach Prozentabstand, Rest hinter einem Aufklapper. **Kein Diagramm.** |
| **Gerätekatalog** | Der Bestand als flache Tabelle, eine Zeile je (Gerät, Speicher, Farbe, Anbieter). Ersetzt SKU-Matrix und 65 Aufklapper. |
| **Preisverlauf** | Das **einzige** Diagramm. Erst nach Geräteauswahl, eine Linie je Anbieter, höchstens 8 Linien und 8 waagerechte Datumsmarken. |
| **Portfolio** | Generationen je Anbieter, Vodafone in Rot. Lifecycle bleibt unter der Schwelle. |

Gelöscht: `report/geraete_karte.py` (791 Zeilen), `_matrix()`, 30 verwaiste
CSS-Regeln, der tote `--pruefe-etiketten`-Schalter. Live vorher: 72 gedrehte
Etiketten, 248 Punkte. Jetzt: 0 und 0.

---

## Die fünf Fehler, die kein Test gesehen hat

Jeder wurde durch **Ansehen** oder **Nachrechnen an echten Daten** gefunden,
nicht durch die Suite.

1. **Die Prüfungen liefen unabhängig.** Eine als gebraucht verurteilte Zeile
   riss ihren gesunden Nachbarn mit aus dem Vergleich — o2s echte Neupreise
   (883 € / 1225 €) fehlten ganz. `pruefe()` verkettet jetzt sequenziell.
2. **CSS schlägt `hidden`.** Nach „alle anzeigen" zeigte die gefilterte
   Tabelle drei fremde Zeilen, während das Attribut korrekt saß. Und der
   Testhelfer zählte `:not([hidden])` — er war für genau diesen Fehler blind.
3. **Die Preisachse erfand Preise.** Bei 41 von 89 Geräten (Spanne null)
   stand dreimal „1000 €" an der Achse für einen Preis von 999,00 €.
4. **Die X-Achse war ordinal.** Messungen im Abstand von 11 und 8 Tagen
   standen gleich weit auseinander — die Steigung war frei erfunden.
5. **Prüfung und Vergleich hatten verschiedene Sichtbarkeitsmengen.**
   `("aktiv", "beobachtet")` gegen `("aktiv", "vermutlich ausgelistet")`,
   und „beobachtet" ist gar kein Status. Eine Zeile in diesem Zustand wurde
   **nie geprüft, aber gezeigt** — so stand der 577-€-Gebrauchtpreis nach dem
   ersten Deploy wieder LIVE auf der Seite. Gefunden beim Ansehen der
   ausgelieferten Seite.

---

## Adapter: ein gemessener Negativbefund

Keiner der sechs ohne Botumgehung erreichbaren Anbieter liefert einen
vergleichbaren Preis ohne Vertrag. Live gemessen am 30.08.2026:

| Anbieter | Befund |
|---|---|
| otelo | `hardwareEntity`/`tariffMap`/`singlePaymentFee` da (129/229 €), `tariffEntity` auf Übersicht **und** Detailseite leer — Tarif nur als `N43` |
| congstar | ld+json `price: 520` beim iPhone 16 gegen 849,90 € bei Vodafone; „mit Vertrag" ×8, „24 Monate", „Allnet Flat" ×17; **kein Speicher im Namen** |
| klarmobil | `ng-state` 129 kB, 248 Einträge, **null Geräte**; Preise aus dem robots-gesperrten `/shop/rest/` |
| 1&1, smartmobil, Blau | kein Produktschema |
| Telekom, Ceconomy | AWS-WAF bzw. Cloudflare — nicht versucht |

Die Kategorie „gemessen, aber ohne Adapter" ist abgeschafft: `quellenlage`
rechnet drei Zustände (`liefert` / `ohne_daten` / `ohne_hardware`), deren
Summe die Zahl der konfigurierten Anbieter treffen muss. Medimax und
ElectronicPartner haben ihren Grund bekommen (20 Produktseiten, 0
Listungen, sechzehn Nächte — **nicht** die Besuchszeit).

---

## Auftragszahlen, die nicht reproduzieren

| Auftrag | Gemessen |
|---|---|
| „iPhone 16 128 GB / 697 € gilt als neu" | stand bereits korrekt als refurbished |
| „12 Doppelpreise" | 5 Gruppen (Gruppierung ohne Zustand) |
| „S24 Ultra 512 GB billiger als 256 GB" | 0 Inversionen |
| „Seite ist 18.412 px hoch" | 5211 px (die Kürzung vom 29.08. stand schon) |
| „o2 führt 54 Generationen" | die Zeile las „24 Generationen · 54 Modelle" |

Bestätigt: „4 Messtermine" (Änderungspunkte **plus** Bestätigungstage) und
die Kachelwerte, sobald der Zustand stimmt.

---

## Offen

1. **Reiter 2 wird beim Aufklappen sehr lang** (352 Zeilen). Das ist eine
   Nutzerhandlung wie ein `<details>`, kein Vorgabestand — aber wenn es
   stört, gehört dort eine Seitenweise hin.
2. **Medimax/ElectronicPartner**: der Rohsatz-Zähler beantwortet beim
   nächsten Nachtlauf, an welcher Stufe es scheitert. Messen geht nur
   zwischen 02:00 und 08:00 UTC.
3. **Der Preisverlauf ist erst ab etwa 12 Wochen belastbar** — heute vier
   Messtermine über 20 Tage. Die Seite sagt das selbst.
4. **Zuzahlungspreise sind nirgends erprobt**: alle 360 Listungen tragen
   einen Barpreis. Der erste Bündelpreis-Adapter löst die Preisart-Umschaltung
   zum ersten Mal wirklich aus.
