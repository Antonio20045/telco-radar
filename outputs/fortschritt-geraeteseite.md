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

**Offen:**
1. P0-a (Verdrahtung) läuft noch. Die Prüferbefunde **S1, S3, S4, S8** betreffen
   `belastbarer_bestand`, die Zeilenzahl am Exportknopf und
   `tests/test_geraete_seite.py` — sie wurden gegen den **halbfertigen** Stand
   gemessen und müssen nach dem Abschluss neu gemessen werden, bevor sie als
   Befunde gelten.
2. Der Prüfer meldet, die Katalogtabelle (Reiter 2) lese `sichtbar` statt des
   bereinigten Bestands — dann erreichte die Bereinigung den Leser gar nicht,
   sondern nur die CSV. **Nach P0-a an der gerenderten Seite nachmessen.**
3. Zwei Zahlen für dieselbe Menge: Katalogüberschrift 370 gegen Exportknopf 358.
   Ebenfalls erst nach P0-a beurteilbar.
4. Der Doppelpreisfall Galaxy S26 FE („pistachio" / „pistachio bk", 144 € Abstand)
   ist weiterhin **ungeklärt** — er wird gemeldet und entfernt, nicht aufgelöst.
   Offener Punkt seit dem 29.08.
