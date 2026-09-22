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

### Die Prüfung hat beide Pakete zerlegt — und mein eigenes Tor mit

**Alle sieben Behauptungen von P3-b waren formal wahr** (2254 Tests grün,
Portalcheck 17/0, kein Test angefasst) **und das Paket war trotzdem falsch.** Der
Prüfer dazu, und es ist die Zusammenfassung dieser Sitzung:

> Die Suite ist mit 2254 grünen Tests genau so grün wie am 30.08., als „o2 2454
> Modelle" ausgeliefert wurde. Sie beweist, dass der Code tut, was der Ersteller
> gemessen hat; sie sagt nichts darüber, ob die Aussage stimmt.

**Mein Tor hat versagt, und der Grund ist lehrreich:** ich habe auf dem heutigen
Datenstand gemessen — genau dem Zustand, in dem das Feature schläft. Beide Prüfer
haben unabhängig denselben Griff gemacht: **einen Nachtlauf simulieren und dann
messen.** Das ist seitdem Pflicht in jedem Auftrag und in jedem Tor.

Was ein einziger Nachtlauf ausgeliefert hätte:

```
duenn False | dauern 85 (alle "21 Tage") | verfaelle 85 (alle "+0,0 %")
85 Zeilen -> nur 11 unterscheidbare Texte
   12x  "iPhone 17 Pro Max bei mobilcom-debitel - 21 Tage"
Portfolio-Reiter 2550 -> 3441 px  (Kriterium 11b faellt durch)
erste Nachfolger-Zeile: ein REFURBISHED iPhone 15
```

Ein gemeldeter Blocker war dagegen **keiner**: der „Renderabsturz beim nächsten
Lauf" war gegen den Commit vor dem Parallelpaket gemessen; auf HEAD fängt
`{% if n.basis %}` ihn ab. Ich habe es nachgestellt — läuft durch. Ungeprüft
weitergereicht hätte ich einen Bauer auf ein Phantom angesetzt.

### P3-a Runde 2 (`a36919c`) — von mir gegen den simulierten Nachtlauf gemessen

| | vorher | nachher |
|---|---|---|
| `dauern` | 85 | **1** (verdient: ALDI TALK hat vier vollständige Läufe) |
| `verfaelle` | 85 | **0**, dazu `ohne_bewegung: 1` als ehrlicher Zähler |
| `nachfolger` | 1 (refurbished) | **0** |

Drei Ursachen geschlossen: die Schwelle maß Dauer und Zahl der Blicke, **nie ob der
Preis sich bewegt hat**; die Verweildauer zählte je Farbvariante statt je
Regalplatz; und die Messtermine waren **zu 100 % zugerechnet** — keine der 370
Listungen hat aus eigenem Beleg mehr als zwei Messtage, alle 68 mit Schwelle nahmen
sie über Anbieter-Lauftage, und die Begründung dafür gilt für mobilcom-debitel nicht
(`laeufe: 0`, `mark_stale` lief für ihn nie). Mutationsprobe 17 → 26 ohne Lücke.

### P3-c (`04580e9`) — sieben Marktstartdaten, jedes belegt

Pixel 11 und die Pro-Reihe auf **2026-08-20** (Vodafone UK und Three UK, beide
publ. 20.08., „now available"), Galaxy Z Fold8/Flip8 auf **2026-08-07** (Samsung
Newsroom, „ab dem 7. August"). Sechs weitere sind **nicht belegbar** und stehen als
Negativliste im Dateikopf.

**Meine Vorgabe war falsch**, und das ist der Grund für dieses Paket: ich hatte
beiden Bauern geschrieben, mehr Katalogpflege löse das Problem nicht. Nachgemessen
hatten 13 beobachtete Geräte einen Nachfolger ohne Datum. Mein Mess-Subagent hatte
nur die Nachfolger *mit* gepflegtem `marktstart` betrachtet — die dreizehn ohne
werden im Code stumm verworfen und waren für die Messung unsichtbar.

**Entschieden (Lead):** 20.08. statt 25.08. Zwei unabhängige Betreibermitteilungen
mit „now available" sind direkter Kaufbarkeitsbeleg, und ein Händler kann nicht vor
dem Marktstart verkaufen. Der Widerspruch (Googles eigener Beitrag datiert 25.08.)
steht mit allen Belegen im Katalog. **Verzerrungsrichtung notiert:** ein früherer
Marktstart macht die Verweildauer länger, also in die Richtung, die unsere eigene
These stützt. Alle betroffenen Zeilen sind Untergrenzen ohne Preisbasis.

**Das Datum war nötig, aber nicht hinreichend.** Der zweite Blocker sitzt auf den
Vorgänger-Listungen: Vodafone und o2 beobachten Pixel 10 erst seit dem 29.08. (zwei
Regaltage gegen 21). Und mobilcom-debitel, der Pixel 10 **seit dem 10.08.** führt —
zehn Tage vor dem Pixel-11-Start —, wird von seinem eigenen `laeufe: 0` ausgesperrt.
Genau diese drei Zeilen wären die einzigen im Bestand, die den Nachfolger-Effekt als
**echte Messung statt als Untergrenze** liefern (Basis 999,00 / 1199,00 / 1429,00 €,
`untergrenze: False`). Ursache ist das Zeitbudget des Nachtlaufs, kein Rechenfehler.
Projektion: ab **19.09.2026** steigt die Tabelle von 5 auf 14 Zeilen.

---

## P1/P2 — Abdeckung: die Frage ist beantwortet, und die Antwort ist ein belegtes Nein

**Messrunde (`3009983`), 13 Anbieter, 33 echte gespeicherte Antworten** mit
`_herkunft.json` (URL, Datum, Status, SHA-256).

| Einstufung | Anbieter |
|---|---|
| **liefert** | congstar · Blau · klarmobil (dünn) |
| **gesperrt mit Messung** | 1&1, otelo, smartmobil, WinSIM — alle nur Bündelzahlen |
| **ohne Hardware-Vermarktung** | Edeka smart, Norma Connect, fraenk, SIMon mobile |
| nicht messbar | Medimax, ElectronicPartner (Besuchszeit 02:00–08:00 UTC, Lauf war 13:10) |

**Das Kriterium „mindestens 8 Anbieter" ist nachweislich nicht erreichbar** — aus
Marktgründen, nicht aus technischen: vier führen gar keine Hardware, vier verkaufen
Geräte nur im Bündel. Die Kategorie „gemessen, aber ohne Adapter" ist leer.

**Zwei Befunde wiegen schwerer als die Zahl:**

1. **Blau und klarmobil sind keine unabhängigen Marktpunkte.** 56 der 65
   Blau-Preise stehen 1:1 auch bei o2; klarmobil trifft freenet in beiden geprüften
   Fällen exakt. Wer Blau als achten Anbieter zählt, zählt Telefónica doppelt —
   dieselbe Lage, für die das Projekt bei freenet/mobilcom-debitel längst „Läden
   statt Marken" entschieden hat. **Deshalb bewusst nicht gebaut.**
2. **Die bisherigen Medimax-Fixtures sind handgeschrieben, nicht abgerufen** —
   „www.fremd.de", „Fremder Shop", erfundene GTIN `0194253000000`. Selbst
   nachgesehen. Die Frage „Selektoren oder wirklich nichts da?" war aus diesen
   Dateien **nie** beantwortbar, auch nicht in 16 Nächten. Der billigste Fix ist kein
   Adapter, sondern eine Zeile im Nachtlauf: die erste Rohantwort je Anbieter als
   Artefakt ablegen.

**Gebaut: congstar (`c3114a0`).** Der einzige mit echter neuer Information — er liegt
im **Telekom-Netz**, und die Telekom selbst fehlt der Datenbank mangels Zugang. Von
mir gegen die Fixtures nachgemessen:

| Gerät | `listed` (richtig) | `discounted` (Falle) |
|---|---|---|
| iPhone 17 256 GB | **919,00** ✓ | 811 — nicht in der Ausgabe |
| Galaxy S25 128 GB | **699,00** ✓ | 519 — nicht in der Ausgabe |
| Pixel 11 256 GB | **991,00** ✓ | 757 — nicht in der Ausgabe |
| Redmi Note 17 Pro 256 GB | **477,00** ✓ | 225 — nicht in der Ausgabe |

Anbieter mit Daten **4 → 5**. Die Falle ist echt: die `discounted`-Werte stehen in
den Rohdaten, der Adapter schließt sie aus, und ein Test fällt sofort durch, wenn
jemand umstellt.

**Offen:** dass das Gerät auch ganz ohne SIM-Vertrag zu diesem Preis an der Kasse zu
haben ist, ließ sich **statisch nicht beweisen** — die Kauflabels rendert React nach.
Belegt sind `contractDuration: 0` und `recurring.listed: 0`, und der Marktvergleich
stützt es. Die Einschränkung steht im Modulkopf und auf `/geraete-quellen.html`.

---

## P4 Runde 3 und Tor P4 — 03.09.2026 (`f47d3a3`)

**Runde 2 war zurückgewiesen worden**, und zwar gezielt: sie hatte die Blöcke
zusammengeführt (69 zerrissene Geräte → 0), damit aber die erste Bildschirmseite
verloren. Gemessen im echten Chromium bei 1440×900, Katalog an den Seitenanfang
gescrollt: **12 sichtbare Zeilen, davon 7 Farbvarianten des iPhone 17 Pro und 5 des
Fairphone 6 — ZWEI Hersteller**, gefordert sind drei.

**Warum der Test des Bauers grün blieb:** seine Fixture trug sieben *Geräte* je
Hersteller, die echten Daten tragen sieben *Farben eines Geräts*. Derselbe Fehlertyp
wie am 30.08. (`get_text(" ")`): das Prüfmittel bildet die Fehlerklasse nicht ab.

**Entscheidung (Lead, statt einer dritten Schleife):** der Block deckelt sich selbst.
In der Standardansicht zeigt ein Geräteblock höchstens **zwei** Zeilen
(`BLOCK_SICHTBAR`), „alle anzeigen" zeigt weiterhin alles, vollständig gruppiert.
Innerhalb des Blocks wird **reihum je Anbieter** genommen — sonst füllte der
günstigste Laden beide Zeilen mit seinen eigenen Farbvarianten, und die Preisspalte
verglich nichts.

### Tor P4, gemessen am ausgelieferten Ergebnis — NACH dem Rebase auf `main`

Der Rebase brachte vier Commits: zwei Nachtläufe des Gerätezweigs und den Radarlauf
vom 02.09. **Die Daten unter allen Toren haben sich damit geändert, deshalb ist jedes
Tor ein zweites Mal gemessen worden**, nicht fortgeschrieben.

| Tor | Messung |
|---|---|
| Erste Bildschirmseite (1440×900) | 12 Zeilen, **6 Hersteller** — Apple, Fairphone, Google, Nothing, Samsung, Xiaomi (vorher 2) |
| Zusammenhalt der Blöcke | 90 Geräte, **0 zerrissen** (Runde 1: 69) |
| `pruefe_portal.py --site` | **16 bestanden, 1 durchgefallen** |
| Kriterium 11b (Reiterhöhen) | 2928 / 2875 / 2162 / 2729 px, Grenze 3000 — **bestanden** |
| Kriterium 11 | 26 Alarmzeilen, 4 Kacheln über 46 Vergleichen, kein Diagramm auf der Startansicht |
| Export gegen Seite | 378 Zeilen, **0** Zustandswörter in der Farbe, **0** echte Dubletten, **0** Zeilen `Zustand = neu` auf Gebrauchtdaten |
| Drei Zeilen gegen Quelle und CSV | iPhone 17 Pro/Vodafone, Fairphone 6/ALDI TALK, Galaxy S26 Plus/o2 — Farbe, Zustand, Preis, Verfügbarkeit, Abrufdatum **identisch**; Quelllinks auf die echten Produktseiten (`vodafone.de`, `alditalk.de`, `o2online.de`), **kein** `api.vodafone.de` |
| Screenshots 1440 und 390 px | selbst angesehen. Blick-Test in fünf Sekunden beantwortet: „am weitesten zurück" = Redmi Note 15 Pro, 45,7 % bei freenet |
| `pytest tests/test_geraete_seite.py tests/test_geraete_reiter_browser.py` | **135 grün** |

**Der eine Durchfaller ist Kriterium 6** (14 px Hochskalierung eines Bildes auf
`meldungen.html`, `f1b13df9668f39bf-1280.jpg`). Er betrifft die Geräteseite nicht,
hängt am Bildbestand des Radarlaufs vom 02.09. und ist die vom 15.08. bekannte,
datenabhängige Fehlerklasse. **Nicht in dieser Phase behoben, weil nicht in ihrem
Zuschnitt** — nicht, weil er unwichtig wäre.

### Was der Rebase an der Datenlage geändert hat

- **Medimax und ElectronicPartner liefern zum ersten Mal** (je 2 Listungen, erster
  Messtermin 02.09.). Damit ist die offene Frage vom 29.08. nach 16 stummen Nächten
  beantwortet: es lag nicht an den Selektoren. **6 Anbieter**, 389 Listungen.
- **Fünf Messtermine statt zwei.** Die P3-Schwelle (4) greift jetzt: die
  Lifecycle-Abschnitte sind aufgewacht, der Portfolio-Reiter wuchs von 875 auf
  1076 px (eigene Messung) bzw. steht bei 2729 px nach Kriterium 11b — **unter**
  der Grenze, aber das ist die Stelle, die beim nächsten Zuwachs zuerst reißt.
- Die Nachfolger-Tabelle steht weiter in ihrer **ehrlichen leeren Fassung** und nennt
  den echten Grund: „Bei 7 Geräten fehlt das Marktstart-Datum ihres Nachfolgers."

### Offen — als offen, nicht als erledigt

1. **Die einzige Verweildauer-Zeile ist ein refurbished Gerät und sagt es nicht.**
   „Verweildauer im Regal · 23 Tage · iPhone 15 bei ALDI TALK" — diese Listung trägt
   im Store `zustand: refurbished`. Die Zahl ist richtig (die Listung stand wirklich
   23 Tage), aber wer die Zeile liest, denkt an ein Neugerät. **Ein fehlendes
   Etikett, keine falsche Zahl** — deshalb nicht kurz vor dem Merge nachgeschoben,
   sondern hier notiert.
2. **Derselbe Laden heißt auf zwei Reitern verschieden.** Die Alarmtabelle nennt
   „freenet", der Katalog „mobilcom-debitel" — `config/geraete_quellen.yaml` führt
   `name: mobilcom-debitel`, `shop: freenet`, `anzeige: freenet (mobilcom-debitel)`.
   **Das dafür gebaute Feld `anzeige` benutzt keine der beiden Stellen.** Wer in der
   Alarmtabelle „freenet" liest und im Katalog danach filtert, findet ihn nicht.
   Nicht behoben, weil der Alarm-Reiter mit 2928 px nur 72 px unter der 3000er
   Grenze liegt und der längere Name eine Höhenmessung wert ist, keine Randnotiz.
3. **Kriterium 6** (siehe oben), vorbestehend und datenabhängig.
4. Unverändert offen aus P1/P2: Telekom, MediaMarkt/Saturn und expert brauchen
   Adapter **plus Fixture-Rekorder für einen lokalen Lauf bei Antonio** — dieser
   Container bekommt HTTP 202 (AWS-WAF). Von hier aus kein Versuch, keine
   Challenge-Umgehung.
5. `mobilcom-debitel` steht weiter auf `laeufe: 0` (Zeitbudget), womit die drei
   Zeilen fehlen, die dem Nachfolger-Effekt eine gemessene Grundlage gäben.

---

## Nachlauf 03.09.2026: die vier Tests, die der neue Datenstand umgeworfen hat

Nach dem Rebase war die volle Suite **2312 grün, 4 rot**. Alle vier hingen an der
Datenänderung der Nacht, keiner an der ausgelieferten Seite. Ein Opus-Bauer hat sie
umgebaut, mit der ausdrücklichen Vorgabe **scharf machen, nicht grün machen**.

| Test | Fall | Was jetzt geprüft wird |
|---|---|---|
| `…kette_der_auslieferung…` | Zustand festgenagelt | Die festen `(370, 366, 358)` sind weg. Geprüft werden Beziehungen: `fertig ⊆ geprueft ⊆ sichtbar`, `|gestrichen| == zahlen["aussortiert"]`, jede gestrichene Zeile hat einen Überlebenden mit demselben Zwillingsschlüssel. Die exakten Zahlen stehen jetzt an einer **gestellten** Lage |
| `…verliert_nur_o2_zeilen…` | Fall existiert nicht mehr | Die zehn o2-Zwillinge sind ausgelistet, `bereinige()` nimmt am 03.09. **null** Zeilen weg. Die Zusicherung prüft jetzt eine konstruierte Zwillingsmenge (mit Gegenprobe: gleiche Zeilen, verschiedene Preise → niemand fällt); gegen die echten Daten bleibt nur, was dauerhaft gilt — kein fremder Anbieter fällt, auch bei null Zwillingen |
| `…traegt_heute_keine_lifecycle_zeile` | Schwelle genommen | Umbenannt: eine Zeile entsteht **erst ab** `MIND_TAGE_JE_GERAET`. Fixture mit 20 und mit 21 Tagen, beide mit denselben vier Terminen, damit die Termin-Bedingung nicht mitentscheidet |
| `…gegenprobe_je_anbieter_gegen_je_listung` | **kein Produktionsfehler** | siehe unten |

**Der vierte war der einzige Kandidat für einen echten Fehler, und er war keiner.**
Meine eigene Hypothese — die Galaxy A17 nehme die Schwelle über zugerechnete
Anbietertermine — ist **widerlegt**: die Listung trägt fünf **eigene** Preispunkte.
Die Gegenprobe sah eine A17-Zeile nur, weil sie selbst `first_seen` aller Listungen
auf 2020 zurückdreht, um die Tages-Schwelle aus der Messung zu nehmen. Sie
verwechselte „keine zugerechneten Termine" mit „keine Zeilen".

**Selbst nachgerechnet, unabhängig vom Bauer:** `auswertung()` liefert auf den echten
Daten **genau eine** `dauern`-Zeile — „iPhone 15 · ALDI TALK · refurbished ·
23 Tage", dieselbe, die auf der Seite steht. Keine A17-Zeile, weder erzeugt noch
weggefiltert.

**Mutationsprobe, von mir selbst durchgeführt** (nicht die gemeldete): Tages-Schwelle
in `geraete_lifecycle.py:736` entfernt → **6 Tests rot**, darunter beide neuen. Datei
danach wiederhergestellt.

Stand: `tests/test_geraete_bereinigung.py` + `tests/test_geraete_lifecycle.py`
**100 grün**, restliche Suite **2219 grün / 2 übersprungen / 0 rot**.

### Neuer Befund, oberster offener Punkt: zwei Telefone unter einer `sku_id`

Beim Nachrechnen des A17-Falls gefunden, **vorbestehend und heute schon live**:

ALDI TALK führt unter der einen Listung `aldi-talk--samsung-galaxy-a17-128gb-schwarz`
**zwei verschiedene Geräte**:

| Quell-URL | Preis |
|---|---|
| `…a17-**lte**-128-gb-black-**sm-a175f**-dsb--beclad-starter-kit…` | **129,00 €** |
| `…a17-**5g**-128-gb-black-**sm-a176b**-ds…` | 155,00 € → 159,00 € |

Vodafones Vergleichsseite ist `samsung-galaxy-a17-**5g**.html`, 219,90 €. Die
Alarmzeile auf der Startansicht — **„Galaxy A17 · ALDI TALK · 219,90 gegen 129,00 ·
41,3 % · KRITISCH"** — vergleicht damit **ein 5G-Gerät mit einem LTE-Gerät**. Gegen
ALDIs echtes 5G-Modell wären es 159,00 €, also **27,7 %**. Die Zeile bleibt der
Sache nach richtig (ALDI ist billiger), die **Zahl ist es nicht**.

Nebenwirkung: jeder Nachtlauf schreibt beide Preise als Änderungspunkt (129 → 159 →
129 …) — zwei Punkte je Datum an allen fünf Messtagen. Es ist die dokumentierte
Sägezahn-Klasse, nur eine Stufe früher: nicht ein falsch getroffener Katalogeintrag,
sondern **zwei Produkte auf einer `sku_id`**.

**Warum die Plausibilitätsprüfung es durchlässt, ist genau benennbar:** 129 € gegen
159 € ist eine Spanne von **23,3 %**, und `SPANNE_GRENZE` steht auf 30 % — kalibriert
an echten Farbaufschlägen (5,7–21,6 %) gegen echte Fehler (53 % und 112 %). Der Fall
liegt in der Lücke. **Die Schwelle zu senken wäre die falsche Antwort** — sie löschte
wahre Farbpreise. Die Wurzel ist die fehlende Variantendimension (LTE/5G) in der
`sku_id`, und die zu ändern ist laut CLAUDE.md eine **Datenwanderung**: der
Altbestand gälte als ausgelistet und entstünde neu, Listungsdauer und Preisverlauf
jedes betroffenen Geräts fielen auf null.

**Deshalb hier nicht gebaut.** Es ist ein eigenes Paket mit eigener Migration, kein
Nebenfix vor einem Merge. Es ist die einzige betroffene Listung im ganzen Bestand.

---

## P5 — Abschluss, 03.09.2026

| | |
|---|---|
| Merge nach `main` | `6c75dfe`, konfliktfrei |
| `deploy.yml` | **success** (08:45:51Z) — Render-Hook ausgelöst |
| `ci.yml` auf `main` | **success** (08:51:12Z) |
| Volle Suite lokal | 2312 grün → nach der Testreparatur alles grün |
| `pruefe_portal.py` | 16 bestanden, 1 durchgefallen (Kriterium 6, vorbestehend, `meldungen.html`) |

**Was live ist und was nicht — der Unterschied ist wichtig.** Der *Code* liegt auf
`main` und ist deployt. Die *Seite* ist es nicht: `curl … /geraete.html | md5sum`
ist byte-identisch mit dem `site/geraete.html` im Repo, also mit dem Stand **vor**
dieser Arbeit. `site/` wird nicht von Hand committet, sondern vom Radarlauf
gerendert — und der läuft Mi + Fr 11:00 UTC. **Der planmäßige Lauf am Fr 04.09.
11:00 UTC baut die Seite mit dem neuen Code und veröffentlicht sie.**

**Ein Lauf ist bewusst NICHT von Hand angestoßen worden.** Begründung mit Zahlen:
der Lauf vom 02.09. hat 68 Meldungen bewertet, aber `editor_used: False` — der
Prosabericht fehlt bereits in der heute sichtbaren Ausgabe. Ein heute angestoßener
Lauf hätte wegen des gefüllten Seen-Stores eine **dünnere** Titelseite als der von
gestern und mit hoher Wahrscheinlichkeit wieder keinen Prosabericht; er würde also
die Geräteseite einen Tag früher zeigen und die Titelseite dabei verschlechtern.
Der Freitagslauf hat zwei Tage Nachrichten und ist die bessere Ausgabe.
`llm-probe.yml` taugt als Gegenprobe nicht — es zeigt noch auf NVIDIA.

### Offener Punkt außerhalb dieses Auftrags, aber sichtbar

**Der Prosabericht fehlt wieder.** `editor_used` über die letzten Läufe:

| Ausgabe | `editor_used` | Kosten | bewertete Meldungen |
|---|---|---|---|
| 27.08. | False | – | 362 |
| 28.08. | **True** | 0,2448 $ | 21 |
| 02.09. | **False** | 0,2175 $ | 68 |

Der 02.09. ist der aussagekräftige Fall: die Analysten haben gearbeitet (68
Highlights), DeepSeek hat geantwortet (149 Aufrufe, keine toten Modelle, Budget
nicht überschritten) — und die Redaktionsstufe hat trotzdem keinen Bericht
geliefert. CLAUDE.md nennt den Prosabericht „das Herzstück". **Das gehört als
erstes in die nächste Sitzung**, und es ist keine Geldfrage: 0,22 $ von 1,50 $
Budget.

---

## v4 — TCO-Radar, das man im Meeting zitieren kann (ab 20.09.2026)

Auftrag: P0 Vertrauen (falsche Zahlen) → P1 Telekom täglich + Ausfall-Alarm →
P2 Darstellung ohne Erklärtexte → P3 Vodafone-Tarifleiter, Aktionen → P4 Push.
Plan: `outputs/strategie-geraete-v4-2026-09-20/plan.md`. Arbeitsweise: je Phase
ein Dynamic Workflow (Bauer je Paket im eigenen Worktree, adversarialer
`seiten-pruefer`, max. 2 Nachbesserungen), Tore misst der Lead selbst an der
gerenderten Seite und am Live-HTML.

### Schritt 0 (20.09., gemessen)

| | |
|---|---|
| CLAUDE.md | Regel 17 ergänzt (wip(auto) nie mergen/rebasen/pushen; Worktree-Branches nach Übernehmen löschen), 180 Zeilen/16,8 kB, Größenregel grün, diff-reviewer PASS, `d3f009d` auf main, ci.yml **success** |
| Stop-Hook | gelesen: wirkt NUR in Worktrees, committet wip(auto), pusht nie; Hauptcheckout no-op. Behalten (Antonio), Absicherung Regel 17 |
| commit-sicher | pusht auf aktuellen Branch → auf main korrekt, unverändert |
| seiten-pruefer | `.claude/agents/seiten-pruefer.md` angelegt (opus; adversarial, eigene Rechnung, ändert keinen Code) |
| Live-Basis | Vorher: Live = Stand 18.9., Renderfix `8133b02` lief durch keinen Actions-Lauf. Manueller `geraete.yml`-Lauf `35518497506`: **success**, „Seite neu gebaut 2026-09-20" (`0e1a75d`), Live-HTML trägt „20. September" (1072 Fundstellen) — **Gegenprobe bestanden** |

**Korrekturen an der Auftragsannahme (Erkundung, 20.09.):** ALDI-Scheinsprung ist
die am 03.09. dokumentierte Doppelbelegung einer `sku_id` (LTE SM-A175F 129 € /
5G SM-A176B 155→159 €), zusätzlich leakt o2 „5g schwarz" in den Farb-Slug
(zwei SKU-Töpfe desselben Geräts). `--al-*` in `style.css` sind Alarmstufen,
keine Anbieterfarben (bleiben). Die −15/−18 € sind 1&1 (dort als unbewiesen
abgelehnt), o2s Fall ist −5 €. Ausfall-Alarm existiert (7 Null-Tage,
log-only). Vodafone `_periode0()` ignoriert die niedrigere Rate ab Monat 25
(Messfehler).

### P0 — läuft

Workflow `p0-bau` gestartet, zuerst nur Paket A1 (Leitzahl „Kosten über
24 Monate", opus) als Skript-Bewährung; A2–A4 (Bewegung/Δ/Referenz, Altern,
Exporte) danach. P0-B (Laufzeiten in den Bündelschlüssel, Collectoren,
Telekom-Tarifsätze) anschließend. Tor offen.

---

## P0 — Vertrauen, abgeschlossen 22.09.2026

**Gebaut.** A1–A4 (Leitzahl mit Restschuld, Bewegung je Anbieter, Alterung,
eindeutiger Export) lagen vor. Dazu B1 (Ratenlaufzeit im Bündelschlüssel plus
Lesemigration), B2a/B2b/B3 (Laufzeiterfassung, o2-Härtung, Telekom-Tarifsätze
über `tarif_bezug.py`), vier Behebungspakete und sechs Horizont-Pakete. Der
eigentliche Befund der Phase stand nicht im Auftrag: **die Seite trug zwei
verschiedene Zeiträume unter einer Beschriftung.** Ein Bündel mit kombiniertem
Monatsbetrag (1&1, `buendel_monatlich`) rechnet über seine ganze Ratenlaufzeit
— 36 Monate —, alle anderen über 24. Der Zeitraum wird jetzt an einer Stelle
bestimmt (`tco_model.monatsschnitt`, `zeitraum_vergleichbar`, Feld
`Tco.leitzahl_monate`) und von jedem Leser gelesen: Etikett, Ø/Monat, Δ-Tor,
Kartenschlüssel, Katalogspalte, Radar, Balkengrafik, Zeitreihe samt
Kurvenetiketten und zugänglichem Namen, und beide CSV-Exporte.

**Gemessen.**
- 81 von 81 Bündeln der vier Tor-Geräte (iPhone 17 Pro 256, iPhone 17 256,
  Galaxy S26 Ultra 256, Pixel 10 Pro), alle Bänder, alle Anbieter: eigene
  Rechnung direkt aus `geraete_tco_historie.jsonl` ohne `tco_model`, jede Zahl
  auf der Seite gefunden. Pflichtfall congstar XS · iPhone 17 Pro 256 =
  1 + 24×15 + 36×30,50 = **1.459,00 €**, Ø 60,79 €/Monat.
- 506 gerenderte Zeilen „Kosten über N Monate X € · Ø Y €/Monat", **null** mit
  Ø × Zeitraum ≠ Summe. „84,15" (Summe/24 bei 36 Monaten) kommt nicht mehr vor.
- o2-Rücknahme exakt: Summe der Leitzahl der 72 o2-Bündel 98.768,16 € wie vor
  P0-B, Differenz je Bündel `Counter({0.0: 72})`. Zwischenstand P0-B waren
  108.956,16 € — +120 bis +276 € je Bündel ohne Preisänderung.
- Historie nicht gerissen: 305 Reihen / 2064 Punkte / 9 Messtage vorher =
  nachher. Ohne B1s Lesemigration: 0 von 3854 Zeilen zuordenbar.
- Export `geraete-tco.csv`: 837 Zeilen, 763 unter „Kosten über 24 Monate EUR"
  (ausschließlich Zeitraum 24), 74 unter „Kosten über die Bündellaufzeit EUR",
  0 ohne Wert, 0 Zahlen unter falschem Kopf.
- Geräte-Suite **1677 grün / 1 übersprungen / 0 rot** (Start der Sitzung: 1588
  grün / 4 rot). Orakel `test_seiten_zahlen.py` 133 grün / 0 rot.
- `pruefe_portal.py` 21 von 21. Screenshots 1440 px und 390 px angesehen.

**Offen.**
1. **Kein Netz zu den Anbieterseiten** (Egress-Policy dieser Umgebung, Gateway
   403 auf CONNECT für telekom.de, congstar.de, 1und1.de, vodafone.de,
   o2online.de). Deshalb unbestätigt: welcher Telekom-Tarifsatz gilt (PIB
   2021–2024 sagt S=6/M=12/L=80 GB, `live_shop` 15.09. sagt 30/50/100 GB — die
   Vorrangregel ist gebaut, der Wert nicht belegt) und was congstars
   „Upgrade-Versprechen" ist.
2. **Erfassungslücke bleibt benannt, nicht behoben** (CLAUDE.md Fallstrick 16).
   0 von 792 Gruppen (Anbieter, SKU, Tarif) tragen zwei Ratenlaufzeiten.
   Telekom, o2, congstar und 1&1 ausnahmslos 36 Monate. In den gespeicherten
   echten Abrufen belegt: congstar 24+36, Vodafone 12/24/36. NICHT belegt:
   Telekom (nur 36), o2 Bündel (nur 36), 1&1 (nur 36). Die Plan-Annahme
   „1&1 24+12 mit Schlusszahlung" ist **widerlegt** — null Treffer für
   Schlusszahlung/Restzahlung/„24+12" über 374 kB gespeicherte Seiten.
3. **Ein gescheiterter Zeitreihen-Aufbau bleibt unsichtbar.** Ein TypeError in
   `geraete_view` rendert die Seite OHNE Hauptgrafik weiter; sichtbar ist nur
   `ERROR … Zeitreihen-Aufbereitung gescheitert`. Verstoß gegen Regel 9,
   vorbestehend, eigenes Paket.
4. **Kein Live-Nachweis.** Diese Sitzung arbeitet auf
   `claude/festive-goodall-cs669e`, `geraete.yml` läuft auf `main`. Der Merge
   ist Antonios Entscheidung.
5. Δ im Block „Ohne Tarifband" vergleicht einen Unlimited-Tarif gegen Vodafone
   Mobil XS 18 GB (P3). Mobil: X-Achsenlabels überlappen, Alterungs-Abzeichen
   bricht in Einzelkästchen, Reiter abgeschnitten, drei Erklärsätze stehen (P2).

### Sitzung 22.09. — P0 auf main, Netzlage gemessen

**Gebaut:** nichts Neues. Diese Sitzung hat den P0-Stand von
`claude/festive-goodall-cs669e` (25 Commits) nach `main` gemergt — konfliktfrei,
ohne `data/`- oder `site/`-Datei. Antonio hat das Arbeiten auf `main` freigegeben
(Regel 6); damit ist offener Punkt 8 („kein Live-Nachweis") erledigt.

**Gemessen:**

| | |
|---|---|
| Geräte-Suite auf gemergtem main | 1677 grün / 1 übersprungen / 0 rot |
| Orakel `test_seiten_zahlen.py` | 133 grün / 0 rot |
| Volle Suite (wie `ci.yml`) | 3589 grün / 4 übersprungen / 0 rot, 11:46 |
| Umgebung | Container war leer; `requirements.txt` neu installiert, Python 3.11.15 |
| Live vor dem Push | Live-`geraete.html` md5-identisch mit `site/geraete.html`, „21. September 2026" |

**Netzsperre aufgehoben — aber nicht überall.** Der dokumentierte `curl`-Test
liefert kein `000` mehr: o2online.de, congstar.de und 1und1.de antworten mit 200
und echtem Inhalt. **telekom.de antwortet 202** (`x-amzn-waf-action: challenge`,
CloudFront), **vodafone.de 403** (Incapsula). Beides ist Bot-Schutz beim Anbieter,
keine Sandbox-Grenze, und wird nach Regel 7 nicht umgangen.

**Offener Punkt 1 (Telekom-Laufzeit-Parameter) ist beantwortet: es gibt ihn nicht.**
Belegt in `outputs/befund-telekom-laufzeit-2026-09-22.md` an beiden Fixtures und
allen acht `beleg-telekom-*.json`: `numberOfInstallments` 19× von 19 auf 36,
`installments` nie länger als 1, die Auswahl 6/12/24/36 nur im Rechtstext des
Konfigurators, dessen Zustandsfelder leer vom Server kommen; Listenfilter laufen
nicht über Query-Parameter und kennen keinen Laufzeitfilter. Nicht entscheidbar
bleibt der BFF (`/shop/api/eshop/bff-de`) — seine Parameternamen liegen in
externen JS-Bündeln hinter der Challenge. **Die Annahme des Auftrags („hol den
Parameternamen, dann liefert der Collector alle Pläne") ist damit widerlegt.**

**Offener Punkt 3 (congstar „Allnet Flat XL mit Upgrade-Versprechen") ist
beantwortet: kein Tarif.** Das heutige Portfolio ist XS/S/M/L mit 15/50/125/200 GB;
„Upgrade-Versprechen" ist eine Zusicherung auf M und L, kein Tarifname. 25 GB bei
35 € gibt es nicht — die Zeilen 31/32 in `tarife.jsonl` stammen aus PIB 546/550
(16.09.) und sind ungültig. Einschränkung: die Grundpreise waren **nicht**
belegbar, congstar lädt sie per JavaScript nach; belegt sind Volumina und Zusage.

**Offen:** Punkt 2 (Telekom-Tarifsätze am Netz belegen) bleibt hinter der
Challenge; die Hälfte davon — schlägt die Vorrangregel aus `tarif_bezug.py` bis in
die Bündelkarten durch? — ist ohne Netz prüfbar. Punkte 4–7, 9, 10 unverändert.

**Nachtrag 22.09.: auch Punkt 2 und Punkt 6 sind kein Defekt, sondern ein
fehlender Lauf.** Beide zeigten dasselbe Muster, und beide sind gemessen:

- Punkt 6: alle 4353 Zeilen in `geraete_tco_historie.jsonl` tragen vier
  Segmente ohne Laufzeit; die heutige Kette erzeugt fünf
  (`buendel--congstar--304327--allnet-flat-m--24m` gegen `--36m`). Adapter
  liefert beide Laufzeiten (echte SKUs aus der Fixture), `_mit_sku()` ist 1:1,
  `laufzeit_segment` unterscheidet, der Store hält beide.
- Punkt 2: dieselben Daten, nur anderer Code. `site/geraete.html` (gerendert
  am 21.09.) zeigt „MagentaMobil S · 6 GB"; derselbe Bestand mit dem heutigen
  Code in einen Wegwerfordner gerendert zeigt „MagentaMobil S · 30 GB". Die
  Vorrangregel aus `tarif_bezug.py:146–148` wirkt; behoben hat es der
  P0-B-Commit `ac80e83` („je_id_aktuell auch unter der eigenen tarif_id
  erreichbar").

Gemeinsame Ursache: P0-B lag bis heute nicht auf main, und `geraete.yml` hat
seit dem Merge nicht gelaufen. **Wer diese Punkte als Defekt baut, baut einen
intakten Weg um.** Die Messung, die beide abschließt, ist der erste
Produktionslauf mit P0-B.

Nebenbefund zum Betrieb: am 22.09. war um 08:13 UTC noch kein `geraete.yml`-Lauf
gestartet (letzter: 21.09., 08:50 UTC). Der 03:10-Cron ist damit erneut über
fünf Stunden im Verzug — der P1-Befund aus dem Auftragsdokument bestätigt sich.
