# Fortschritt Geräteseite — Lead-Protokoll

Je Phase drei Zeilen: **was gebaut**, **was das Tor GEMESSEN hat**, **was offen ist**.
Eine Behauptung ist keine Messung. Offene Punkte stehen als offen.

Arbeitsweise: Lead plant und prüft, Bau-Subagenten bauen, je Bauer ein
adversarischer Prüfer. Kein Produktionscode vom Lead.

---

## Ausgangsmessung (31.08.2026, vor dem ersten Eingriff)

| Was | Wert |
|---|---|
| Branch | `claude/lead-mode-planning-mh4bo2`, **identisch mit `origin/main`** |
| Live | `site/geraete.html` ist **byte-identisch** mit https://telco-radar.onrender.com/geraete.html (md5 `474670ba…`) |
| Gerätetests | **596 grün** (`pytest tests/test_geraete_*.py`, 451 s, davon 31 echtes Chromium) |
| Bestand | 370 Listungen, 4 Anbieter (Vodafone 150, mobilcom-debitel 140, o2 78, ALDI TALK 2) |
| Hersteller | Samsung 138, Apple 134, Google 70, Xiaomi 20, Fairphone 5, Nothing 3 |
| Chromium | vorhanden (`/opt/pw-browsers/chromium-1194`) → Sicht-Tore ausführbar |

**`claude/geraeteradar-evaluation-august-50sq84` ist vollständig in `main` enthalten**
(`git merge-base --is-ancestor` bestätigt). Die Sorge aus dem Auftrag, Teile der
letzten Sitzung seien nie live geworden, trifft nicht zu: **nichts ist gestrandet.**

---

## Nachmessung der Befundliste (Teil B des Auftrags)

### Bestätigt

| | Befund | Messung |
|---|---|---|
| B1 | Zustandswort in der Farbe | **10 Zeilen**, alle o2, alle `vermutlich ausgelistet` |
| B2 | Dubletten | **genau 10 Paare**: je eine alte Zeile mit verschmutzter Farbe neben einer korrekten neuen |
| B3 | Export widerspricht der Seite | bestätigt — der schwerste Befund, Ursache unten |
| B5 | Katalog öffnet auf Apple/o2/refurbished | bestätigt, Ursache ist die alphabetische Sortierung ab „iPhone 14" |
| B6 | Abrufdaten mischen sich | bestätigt: 344× 30.08., 10× 29.08. (die Paare), 9× 21.08., 7× 14.08. |
| B7 | Quelllink unauffindbar | bestätigt: der Link in der Zeile ist ein nacktes `↗` ohne Text |

### Korrigiert

**K1 — Die Zerlegung `Farbe → (Farbe, Zustand)` IST gebaut.** Der Auftrag hält sie
für fehlend. Vorhanden in `geraete_model.py`: `ohne_zustandswort()` (:494),
`zustand_aus_feldern()` (:535), `zustand_aus_titel()` (:549) mit genau den
geforderten Stichwörtern als Wortmenge, `farbschluessel()` (:319) samt
`_KUERZEL_MAX` für „pistachio bk". Committet am 30.08. (`fe1ce8a`).

Die 10 verschmutzten Zeilen sind **Altbestand vom 29.08., den der heutige Code nicht
mehr erzeugt** — die Zeilen vom 30.08. daneben sind sauber. P0 ist deshalb kein
Parser-, sondern ein Auslieferungsauftrag.

**K2 — B4 trifft nicht zu.** Der Auftrag vermutet hinter den zwei 577,00-€-Zeilen
dieselbe Angebotskachel, zwei Geräten zugeordnet, und schickt den o2-Adapter zur
Untersuchung. Nachgemessen sind es **zwei verschiedene Produktseiten**:

```
…/apple-iphone-14-pro-128gb-space-schwarz-erneuert-details
…/samsung-galaxy-s25-128gb-grau-erneuert-details
```

verschiedene URLs, verschiedene Titel, verschiedene Geräte. Zwei refurbished Geräte
kosten bei einem Händler zufällig gleich viel. **Der o2-Adapter ist an dieser Stelle
in Ordnung und wird nicht angefasst.** Befund widerlegt, nicht behoben.

**K3 — Die Ursache von B3 ist die fehlende Plausibilitätsprüfung im Export.**
Die Seite ruft `geraete_pruefung.pruefe()` (`geraete_view.py:806`), der Export nicht
(`geraete_export.py:97` filtert nur nach Status). Die Sichtbarkeitsmengen sind
inzwischen identisch — die Prüfung ist der Unterschied. An den echten Daten:

```
sichtbar 370 → sauber 366, aussortiert 4
  zustand_veraltet 2   ← die zwei Giftzeilen (Zustand=neu auf Gebrauchtdaten)
  doppelpreis      1   ← Galaxy S26 FE „pistachio" / „pistachio bk", 21,6 %
```

**K4 — Ein Filter allein reicht nicht.** Nach `pruefe()` bleiben **8 der 10**
verschmutzten Zeilen übrig: ihr `zustand` ist bereits korrekt `refurbished`, sie
sind nur doppelt und hässlich. B1/B2 brauchen eine zweite, eigene Korrektur.
Deshalb hat P0 zwei Pakete.

**K5 — 90 Gruppen mit gleichem (Anbieter, Gerät, Speicher, Preis) sind KEINE
Dubletten.** Vodafone führt ein iPhone 17 256 GB in fünf Farben zu 949,90 € — das
ist die von der Fachseite bestellte Granularität. Echte Varianten unterscheiden sich
durch die **`quelle_url`**; die 10 Zwillinge teilen sie sich. Die URL gehört deshalb
in den Dublettenschlüssel, die Farbe nicht.

### Rahmenmessung für P1/P2

**Telekom antwortet diesem Container mit HTTP 202 und leerem Body** — die
AWS-WAF-Challenge, wie im Auftrag für Rechenzentrums-IPs vorhergesagt. Von hier aus
ist der Adapter ohne Umgehung nicht baubar; es wird keine versucht.
**1&1 ist erreichbar, aber nicht auswertbar:** HTTP 200, 553 KB, drei ld+json-Blöcke
— `FAQPage`, `WebSite`, `Organization`, **kein Produktschema**. Erreichbar ist nicht
auswertbar; P1/P2 beginnen deshalb mit einer Messrunde, nicht mit Adapteraufträgen.

---

## P0 — Datenwahrheit

**Gebaut:** zwei Pakete. **P0-b** `report/geraete_bereinigung.py` + 17 Tests
(`79f652a`) — `bereinige()` räumt das Zustandswort aus der Farbe und fasst
Zwillingszeilen zusammen, als reine Lesefunktion ohne Eingriff in den Store.
**P0-a** verdrahtet `pruefe() → bereinige() → Seite UND Export` — *läuft noch*.

**Gemessen (Lead, an der echten Kette, nicht an den Tests der Bauer):**

```
roh 370 → pruefe 366 → bereinige 358
```

| Tor-Kriterium | Ergebnis |
|---|---|
| Zustandswort in der Farbspalte | **0** |
| Identische (Anbieter, Modell, Speicher, Farbe, Preis) | **keine** |
| `Zustand = neu`, dessen Rohdaten gebraucht sagen | **0** |
| Vodafone-Farbvarianten iPhone 17 256 GB | alle **5** erhalten |
| Entfernt | genau **12**, alle o2 — 10 Zwillinge mit überlebendem Partner, 2 Doppelpreis |
| Kollateralschaden | keiner (Vodafone 150, mobilcom-debitel 140, ALDI TALK 2 unverändert) |

Der Bauer hatte **360** gemeldet, weil er gegen die rohen 370 rechnete statt gegen
die 366 nach `pruefe()`. Die Zahl der Auslieferung ist 358. Genau dafür misst der
Lead selbst.

**P0-b ist zurückgewiesen, Runde 1 von 2.** Der adversarische Prüfer hat 12 Befunde
geliefert; die tragenden habe ich selbst nachgemessen und bestätigt:

| | Befund | Meine Messung |
|---|---|---|
| **Blocker** | `ohne_zustandswort()` strippt Aufräumzeichen **unbedingt** | `'Silver Shadow (Enterprise Edition)' → '…Edition'` — der Fall steht im echten Bestand (mobilcom-debitel, 899,00 €) und ginge verstümmelt live |
| schwer | Der Musterbau für mehrteilige Kennzeichen ist kaputt (`geraete_model.py:513`, `[\s\[\s\-]]` trifft nie) | `'Schwarz B-Ware'`, `'wie neu'`, `'second-hand'`, `'Open-Box'` bleiben **unverändert**; 6 von 9 Kennzeichen sind für die Bereinigung tot |
| schwer | 11 von 17 Tests sind grün, wenn `bereinige()` nichts tut | `test_ohne_die_bereinigung_…` ruft `bereinige()` **gar nicht auf** — sein Rumpf befragt zwei Fixture-Literale, seine Docstring nennt ihn „die Gegenprobe" |
| schwer | 8 von 9 Schlüsselbestandteilen wirkungslos | weggelassen bleibt es bei 360 Gruppen; nur ohne Farbe kippt es auf 272 |
| mittel | Die Prämisse des Modulkopfs ist falsch | **keine** der 370 Zeilen trägt das Kennzeichen nur in der Farbe — alle zehn auch in Titel UND URL |
| mittel | Die halbe Preishistorie des Zwillings fällt weg | 10 Punkte vom 29.08. verlassen `geraete-historie.csv` |

Drei Zusicherungen hielten der Prüfung stand und bleiben: kein Verlust echter Ware,
die fünf Farbvarianten überleben, das Ergebnis ist über 20 Shuffles stabil.

**P0-b Runde 2 (`0ab34db`) — vom Lead nachgemessen und angenommen:**

| Behauptung | Meine Messung |
|---|---|
| Farben ohne Kennzeichen kommen zeichengenau zurück | `'Silver Shadow (Enterprise Edition)'`, `'Blau (neu)'`, `'Grau, matt'`, `'Titan-'` — unverändert |
| Mehrwort-Kennzeichen fallen | `B-Ware`, `wie neu`, `second-hand`, `Open-Box`, `2. Wahl`, `geprueft und zertifiziert` — alle gestrichen |
| Ausgelieferte CSV | 358 Zeilen, 15 Spalten (kein `zwilling_ids`), 0 Zustandswörter, Klammerfarbe unversehrt |
| `first_seen` geerbt / `zwilling_ids` | je 8 Zeilen |

**P0-a Prüfung (adversarisch, eigener Worktree auf `4fba9af`) — sieben Befunde.**
S1 (verstümmelte Klammerfarbe) ist durch Runde 2 bereits behoben, an der
ausgelieferten CSV verifiziert. Die übrigen stehen und gehen als **P0-c** zurück:

| | Befund | Messung |
|---|---|---|
| **S5 Blocker** | Die zentrale Regel hält **kein** Test | `export_bestand: belastbar → sichtbar` gesetzt: **alle 2190 Tests bleiben grün**, der Export liefert wieder 370 Zeilen mit zwei Gebrauchtpreisen als „neu". `test_der_export_zeigt_genau_den_bestand_der_seite` behauptet `Export == Rohbestand` — den Zustand, den die Änderung abschafft — und ist grün, weil seine Fixture den Fall nie auslöst |
| S2 | Die Verdrahtung bricht eine Zusage, die auf **zwei ausgelieferten Seiten** steht | o2 Galaxy S26 FE („pistachio"/„pistachio bk") fällt aus der CSV, während `geraete-quellen.html` wörtlich verspricht „Alles bleibt in der CSV-Tabelle … verschwindet nicht" und die Zeile namentlich als Befund führt |
| S3 | Zwei Zahlen für dieselbe Menge, im selben Reiter | Knopf „**Alle** exportieren (358 Zeilen)" gegen Überschrift „370", Historie 361 gegen 373 |
| S4 | Die Begründung des Commits reproduziert nicht | Beide Reihenfolgen liefern **denselben Bestand, Zeile für Zeile**. Der einzige Unterschied ist `zustand_veraltet` 2 gegen 0 im Prüfbericht. Die Reihenfolge bleibt richtig — die Begründung war behauptet, nicht gemessen |
| S6 | Der Farbbericht sieht die Bereinigung nicht | listet weiter `space schwarz erneuert`, `marble gray erneuert`, `titanium black gebraucht` … — genau die Schreibweisen, die `ohne_zustandswort()` dort heraushalten soll |
| S7 | `pruefe()` dokumentiert den alten Vertrag | `geraete_pruefung.py:396` verspricht „Export und SKU-Ansicht sehen weiterhin alles" |

**Die Architekturentscheidung des Leads (P0-c): es sind ZWEI Mengen, nicht eine.**
Gemessen, beide erfüllen alle Tor-Kriterien:

| Menge | Rechnung | Zeilen | Verbraucher |
|---|---|---|---|
| **Bestand** | `bereinige(sichtbar)` | **360** | Katalog, Farbbericht, CSV, Kennzahlen |
| **belastbar** | `bereinige(pruefe(sichtbar))` | **358** | Vergleich, Alarme, Preisgrafik, Lifecycle |

Der Unterschied sind genau die zwei S26-FE-Zeilen. Das ist die Regel des Projekts,
nicht eine Erfindung: die Plausibilitätsprüfung entscheidet, was GEGENEINANDER
gerechnet werden darf — nicht, was es gibt. Damit lösen sich S2, S3, S6 und die
offene Naht an Reiter 2 gemeinsam auf. Ausnahme, die bleibt:
`schwelle_erreicht()` rechnet weiter gegen den Rohbestand — eine
Datenqualitätsheuristik darf keinen Navigationseintrag schalten.

### TOR P0 — bestanden, vom Lead an der gerenderten Ausgabe gemessen

Nicht an den Tests der Bauer. Gerendert nach `/tmp/…/tor3`, `site/` und
`data/state/` unangetastet.

| Kriterium des Auftrags | Messung |
|---|---|
| Kein Zustandswort in der Farbspalte | **0** von 360 |
| Keine zwei Zeilen mit identischem (Anbieter, Modell, Speicher, Farbe, Preis) | **0** |
| Keine Zeile `Zustand = neu`, deren Rohdaten ein Zustandswort tragen | **0** (349 neu / 11 refurbished) |
| Seite und Export nennen dieselben Zahlen | Exportknopf **360**, Katalogüberschrift **360**, Tabellenzeilen **360**, Fußsatz „zusammen **360** Listungen", „alle **360** Zeilen zeigen" |
| B4 als widerlegt protokolliert | oben unter K2, mit beiden URLs |

Dazu, was der Auftrag nicht verlangt, aber die Befundliste meinte:

- **B1/B2/B6 auch auf der SEITE** — Reiter 2 zeigt „space schwarz" statt „space
  schwarz erneuert", keine Dublettenpaare mehr, **alle Abrufdaten auf dem
  30. August** (die 29.08.-Altzeilen sind weg).
- **Der Farbbericht** führt von 59 Schreibweisen **keine** mit Zustandswort mehr.
- **Die Zusage der Vorlagen hält wieder**: die zwei o2-Zeilen Galaxy S26 FE
  („pistachio" 811,00 / „pistachio bk" 667,00) stehen im Bestand und in der CSV,
  aus dem Vergleich fallen sie. `Silver Shadow (Enterprise Edition)` unversehrt.

**Die S5-Mutation habe ich selbst gefahren**, nicht der Bauer:
`"bestand": bestand` → `"bestand": sichtbar` (die vollständige Rücknahme) →
**2 Tests fallen durch** (`test_der_export_zeigt_genau_den_bestand_der_seite`,
`test_jede_zahl_fuer_den_bestand_ist_dieselbe_zahl`). Vorher blieben an derselben
Stelle **alle 2190 grün**. Datei danach zurückgesetzt.

`scripts/pruefe_portal.py`: **17 bestanden, 0 durchgefallen, 0 nicht prüfbar.**
Reiterhöhen 2949 / 2915 / 2184 / 2362 px (Grenze 3000).
Screenshot bei 1440 px gerendert und **angesehen** — Herstellermix in Reiter 1
stimmt (Samsung, Google, Xiaomi), die vier Kacheln summieren sich zu 47 und der
Satz darunter nennt dieselbe 47.

**Ein Fund des Bauers, den niemand beauftragt hatte, und er ist wichtig:** die
Bereinigung löscht das Beweisstück, aus dem der Zustand abgeleitet wird — o2
schreibt „erneuert" bei einem Teil der Strecke nur in die Farbe. Auf dem Bestand,
der nicht mehr durch `pruefe()` läuft, hätte Reiter 2 danach „mitternacht ·
Zustand **neu**" gezeigt. Der Zustand wird jetzt abgeleitet, **bevor** die Farbe
gesäubert wird, und `zustand_der_zeile()` ist die EINE Ableitung für Reiter 2 und
die CSV-Spalte — die vorher dem Store glaubte, also eine dritte Fassung derselben
Regel war.

**Offen aus P0:**
1. **B5 und B7 sind NICHT erledigt** — der Katalog öffnet weiter alphabetisch bei
   Apple/o2, und der Quelllink ist weiter ein nackter Pfeil. Beides ist P4 und
   dort bewusst zurückgestellt, nicht vergessen.
2. Der Doppelpreisfall Galaxy S26 FE bleibt **ungeklärt** (offener Punkt seit dem
   29.08.): der Prüfbericht meldet ihn, der Vergleich lässt ihn aus, der Bestand
   zeigt beide Preise. Welcher stimmt, weiß niemand.
3. `_auffaellig()` und `geraete_lifecycle.auswertung()` lesen weiter `alle`
   inklusive ausgelisteter Zeilen — bewusst: auf `belastbar` gezwungen verlören
   sie genau die Daten, wegen derer es sie gibt (Auslistungen, Verweildauer).

---

## P3 — Datenlage vorab gemessen (vor jedem Bauauftrag)

Die entscheidende Zahl: **die ganze Datenbank kennt drei Messtage** (10.08., 29.08.,
30.08.).

| Frage | Antwort |
|---|---|
| Listungen mit ≥ 4 Messterminen | **0 von 370** (28 haben einen Messtag, 342 haben zwei) |
| Längste Beobachtungsspanne | **20 Tage** gegen eine Schwelle von 21 → 0 erfüllen sie |
| `dauern` / `verfaelle` / `duenn` | 0 / 0 / **True** — die Seite zeigt bereits korrekt den Dünn-Satz |
| Schwelle je Anbieter (heute im Code) | 2 von 370 Zeilen |
| Schwelle je Gerät (wie dokumentiert) | **0 von 370** — die Korrektur leert die Seite **nicht**, sie ist schon leer |
| Portfolio-Tiefe | **trägt vollständig** (o2 24/54/78, Vodafone 20/41/150 `eigen`, mobilcom-debitel 10/18/140, ALDI TALK 2/2/2) |

**Der Nachfolger-Effekt ist strukturell nicht befüllbar.** Es gibt 4 Kandidaten mit
gepflegtem `marktstart`, aber alle Nachfolger kamen **570–710 Tage vor** unserem
ersten Messpunkt auf den Markt: `basis = _preis_am(eigene, start)` ist für alle vier
`None`, weil kein Preis am oder vor dem Stichtag existiert. **Mehr Katalogpflege
löst das nicht** — die Sektion füllt sich erst mit einem Marktstart, der IN unser
Messfenster fällt, realistisch ab Mitte Oktober (30 Tage nach dem Apple-Event am
9. September).

**Entscheidung (Antonio, auf Vorlage des Leads): ehrliche Fassung, Rechnung
vorbereiten.** Gebaut werden (1) die Schwelle je Gerät wie dokumentiert, (2) die
fehlende Hälfte des Nachfolger-Effekts als Rechnung mit Test gegen konstruierte
Daten, (3) ein sichtbarer Satz, warum die Sektion leer ist und ab wann sie füllt.
Die Schwellen werden **nicht** an die heutige Datenlage gesenkt — zwei Messpunkte
ergeben eine Gerade, und eine Gerade durch zwei Punkte sieht aus wie ein Trend.

**Nebenbefund:** `MIND_TERMINE_JE_GERAET` heißt „je Gerät" und der Kommentar
(`geraete_lifecycle.py:62`) sagt es ausdrücklich — `_oft_genug()` (:335) zählt aber
je **Anbieter**. Docstring und Code widersprechen sich.

**Gebaut:** **P3-a** (`4cf7a5d`, `analyze/geraete_lifecycle.py`, Tests 27 → 46) —
Messtage je Listung, Gatter auch vor der Nachfolger-Tabelle,
`verweildauer_nach_nachfolger()` mit Untergrenzen-Kennzeichnung.
**P3-b** (`d846971`, Vorlage + `geraete_view.py`, 4 neue Tests) — der Satz, der die
Leere erklärt, plus die Verweildauer-Spalte.

**Der Bauer hat das Briefing korrigiert, und das war wichtig.** Ich hatte
vorgegeben, die Schwelle je Anbieter ergebe 2 Zeilen — diese Zahl stammt aus dem
**rohen** `termine`-Feld. Die Pipeline rechnet über `db.messtermine()`, das weitere
Prüftage aus den Listungsfeldern ableitet; mobilcom-debitel kennt dadurch fünf statt
zwei. Auf der echten Rechnung sind es **142 je Anbieter gegen 70 je Listung** — die
Korrektur war also nötiger, als meine Zahl vermuten ließ. Eine Anbieterrechnung
hätte 142 Zeilen als belastbar durchgewinkt, von denen keine vier eigene Messtage
hat.

**Die Laufzahl bleibt bewusst ein Boden.** Sie zu streichen lässt
`test_eine_lange_beobachtung_erscheint_sehr_wohl_auf_der_seite` fallen und reißt die
G0-Lehre vom 28.08. wieder auf: `geraete_preise.jsonl` trägt nur Änderungspunkte,
eine Listung aus eigener Kraft hat höchstens zwei Belege.

### TOR P3 — gemessen, Prüfung läuft noch

| Kriterium | Messung |
|---|---|
| `auswertung()` heute | `duenn` True, `dauern` 0, `verfaelle` 0, `nachfolger` 0 — das gewünschte Ergebnis der ehrlichen Fassung |
| Portfolio-Tiefe | trägt: o2 24/54/78 · Vodafone 20/41/150 `eigen` · mcd 10/18/140 · ALDI TALK 2/2/2 |
| Verweildauer, je (Gerät, Anbieter) | 6 Zeilen, **alle `untergrenze=True`** — korrekt: Messbeginn 10.08.2026, beide Nachfolger 549 bzw. 689 Tage davor |
| Der ausgelieferte Satz | sagt was kommt, warum es fehlt, wann es kommt — **kein geratenes Datum** |
| „über eineinhalb Jahren" | nachgerechnet: jüngster Nachfolger 549 Tage = 1,50 Jahre vor Messbeginn. Trägt |
| `pruefe_portal.py` | **17 bestanden, 0 durchgefallen**; Reiterhöhen 2949 / 2915 / 2184 / **2550** px |
| Lifecycle-Tests | 46 grün |

**Ein Fehler, den P3-b nebenbei behoben hat und der teuer geworden wäre:** die Spalte
„vorher" formatierte `n.basis` ungeschützt. P3-a lässt eine Zeile MIT Verweildauer
und OHNE Preisbasis zu — der erste solche Datensatz hätte beim Rendern einen
`TypeError` geworfen und damit nicht die Geräteseite gekostet, sondern **den ganzen
Lauf**. Beide Bauer sind unabhängig auf dieselbe Stelle gekommen.

**Kleinbefund, notiert, nicht behoben:** `_zeitraum_grob` überzeichnet bei exakt 547
Tagen um einen halben Tag (1,5 Jahre sind 547,5 Tage). Praktisch nicht erreichbar.

**Offen:** zwei adversarische Prüfer laufen, je Paket einer, je auf einem
eingefrorenen Commit. Die schärfste Frage an sie: der Erklärsatz erscheint über
`{% elif %}`, also **nur solange die Tabelle leer ist**. Bekommt sie Zeilen,
verschwindet er — dann stünde dort „709 Tage im Regal" ohne den Hinweis, dass wir
21 Tage zugesehen haben. Der Fehler träte erst ein, wenn die Datenlage endlich
trägt, also wenn niemand mehr hinsieht.
