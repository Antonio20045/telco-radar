# P4-Re-Check — Urteil (18.09.2026)

Prüfer: frisch, hart, ohne Bau-Kontext. Basis: frisch mit `cfg` gerendertes
`site/`, Server 8772, Playwright (1440/390), Suite + Portal am stehenden
Baum. Details und alle Messzahlen: `notiz-recheck.md` (dieses Verzeichnis).
Nichts committet, kein State geschrieben, Server gekillt.

## Ergebnis: **durch = NEIN**

Die Seite ist messbar ruhiger geworden und 8 der 10 geprüften FAIL-Punkte
aus `pruefung-sicht.md` sind behoben — aber es bleiben DREI offene FAILs,
davon einer S1-schwer: der S2-Fix ist **baulich wirkungslos** und wird von
einem Test gedeckt, der das Attribut statt die Sichtbarkeit misst.

## Behoben (nachgestellt, bestätigt)

| Ehemaliger FAIL | Messung jetzt |
|---|---|
| Katalog-Leitzahl Falz 1440 | 60 px `b.gr-leit-zahl` „157,00 €", 4/4 Reiter |
| 390: h1 > Leitzahl | 30 px Leitzahl ist Maximum, 4/4 Reiter |
| Text-Deckel Vergleich 18 048 Z | 992 Z; `pruefe_portal` **21/0/0** |
| Rot Vergleich 19 | 9 (Wash statt Fläche; enge Regel Hue≈0, ohne SVG, initial sichtbar) |
| 10 tote Graph-Sprünge (S1) | 0 tote; 87 Links = 87 Zeitreihen-Modelle; iPhone 18 → „im Katalog →"/„noch keine Zeitreihe" (10×); lebender Sprung Xiaomi 17 → korrekt 880,75 € |
| „keine Angabe" 166× | 0 (stilles „–") |
| Suite-Drift | `-k geraete` 1460/2/6; die 2 = die unangetasteten Vorbestehenden (Galaxy-Tab-S11-Ultra, Nachtlauf-Nullzeilen) |
| Testumstellung Querlinks | stärkend (Wahlmengen- + Lücken-Assert, Gegenproben, Vorher-rot dokumentiert) — der dritte Vorbestehende ist durch den S1-Ursachen-Fix legitim grün |

Dazu bestätigt: Button-Reihen 2/0/1/1, Kachelnamen vollständig (kein
Ellipsis), kein Querscroll 390, Tafelhöhen alle < 3000, Augenschein
(5 Screenshots): Leitzahl dominiert, Radar ist Grafik, ruhig.

## Offene FAILs

1. **S1 — S2-Fix wirkungslos (Leerzustand-Leitzahl).** `#gr-vleit` trägt
   `class="gr-leit"`; `.gr-leit{display:flex}` (style.css:3642) übersteuert
   das Browser-`[hidden]`. Gemessen an BEIDEN Pfaden (Suche „zzzz",
   Von-Datum 2027): `hidden:true`, `display:'flex'`, 81 px hoch — „919,00 €"
   steht sichtbar neben „Kein Gerät gefunden."
   (screenshots-recheck/recheck-s2-leerzustand-1440.png). Der neue Test
   assertet `e.hidden` statt Sichtbarkeit und ist deshalb grün. Fix:
   `.gr-vleit[hidden]{display:none}` (Muster existiert im Stylesheet) +
   Test auf computed display umstellen. Der Nutzwertverstoß der Phase
   („größte Zahl lügt im Leerfall") besteht unverändert.
2. **Katalog-Rot 12 > 10.** 11× `a.gr-sprung` „im Graph ansehen →" initial
   VOLLRot (`rgb(230,0,0)`) + 1 aktiver Knopf. fix.md-Behauptung „graue
   Links, Rot erst im Hover" ist für den Katalog widerlegt; die Zahl „5"
   ist mit keiner Messregel reproduzierbar. Vergleichs-Reiter zeigt, dass
   die Regel richtig umsetzbar ist (19 → 9).
3. **Mobil: Kurve nicht im ersten Viewport.** SVG top 921 px bei Falz 844
   (77 px darunter; harte P4-Abnahme). fix.md deklariert das als bewusst
   nicht gebaut, nennt aber „~35–40 px" — nachgemessen 77 px. 11c misst nur
   den GraphKOPF (838) und meldet deshalb Grün.

## Rest (im Scope Wesentliches, kein FAIL)

- **Kachel-Zahlen im Leerzustand** bleiben stehen (919/1.171/6/11) —
  Erweiterung von Punkt 1: fünf gerätbezogene Zahlen behaupten das
  vorherige Gerät.
- **Rot-Deckel ist nirgends als Messregel genagelt** (nur DOM-Proxy-Test) —
  genau dadurch konnten fix.md („Katalog 5") und Realität (12) auseinander-
  laufen, ohne dass es ein Test meldet. Nachzahlen-fix sollte die Regel
  (Hue≈0, eigenes Rot, ohne SVG, initial sichtbar, Links gezählt) als
  Kriterium oder Test festschreiben.
- Delta-Leitzahl ohne Vorzeichen („466,80 €" + Worte daneben) — bewusst
  offen, pruefung-sicht-Anmerkung steht weiter.
- 6 Kacheln = 3 Modelle (PM-7), Fragment 3,5 MB (PM-6), 2c-Modellmengen —
  alles bewusst offen an den Lead delegiert (fix.md-Liste, plausibel).

## Empfehlung an den Lead

Fix-Runde nur für die drei offenen FAILs (Punkt 1 ist eine CSS-Zeile plus
Test-Umstellung, Punkt 2 die Entsättigung der Katalog-Sprünge wie im
Vergleich bereits geschehen, Punkt 3 eine Layout-Entscheidung über die
Kachel-Reihen mobil). Danach Re-Check nur dieser Punkte — die übrige
Abnahme steht.
