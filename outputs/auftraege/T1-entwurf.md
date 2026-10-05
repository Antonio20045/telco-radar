# T1 Entwurf: zweites Merkmal der Promo-ID

Gemessen am Schnappschuss `tests/fixtures/bestand/2026-10-03/state/promo_db.json` (Bot-Commit 9a9b683, gleich dem Stand aus 7ee3f59): 330 Einträge, 105 aktiv, 33 evtl. ausgelaufen, 192 ausgelaufen. Marke und Zielseite (`models.normalize_url(url)`) bilden unter den aktiven 76 Gruppen, 15 davon mit mehr als einem Angebot.

## Vorschlag

Schlüssel = Marke + Zielseite + **Konditionen** + Laufnummer.

- Konditionen: die Menge aller Zahlen der `description` (NFKC, Tausenderpunkt weg, Dezimalkomma als Punkt, ohne führende und abschließende Nullen). Die Zahlen sind Preis, Volumen, Rabatt und Laufzeit, also das Angebot selbst, nicht sein Wortlaut.
- Laufnummer: 1; ab 2 nur, wenn ein Aufruf auf derselben Seite zwei Angebote mit gleichem Schlüssel findet (Fall `gleichzeitig`). In der Migration gelten Einträge mit gleichem Schlüssel, gleichem `first_seen` und gleicher `source_url` als gleichzeitig.
- Die ID entsteht einmal beim Anlegen. `upsert` sucht zuerst den gleichen Schlüssel, danach wie bisher `_same_offer`, aber nur innerhalb derselben Marke und Zielseite.

## Messung je Merkmal

Spalte „verschiedene Angebote“: Paare aktiver Einträge mit gleichem Schlüssel, die nicht dasselbe Angebot sind. Spalte „Umformulierungen“: von 29 von Hand bestimmten Paaren (dasselbe Angebot, einmal aktiv, einmal nicht aktiv, gleiche Marke und Zielseite), wie viele denselben Schlüssel bekommen.

| zweites Merkmal | verschiedene Angebote | Umformulierungen |
|---|---|---|
| keins (nur Marke + Zielseite) | 58 | 29 / 29 |
| `mechanic` | 37 | 18 / 29 |
| `valid_until` | 56 | 27 / 29 |
| `image_url` (meist Logo) | 56 | 29 / 29 |
| `source_url` | 55 | 20 / 29 |
| Zahlen im Titel | 4 | 15 / 29 |
| Beträge mit Einheit im Titel | 6 | 19 / 29 |
| `clustering.zahlenmenge` der Beschreibung | 1 | 12 / 29 |
| **Konditionen (alle Zahlen der Beschreibung)** | **0** | 11 / 29 |
| normalisierter Titel | 0 | 2 / 29 |

Roh gezählt (Paket 21 nachgemessen) sind es unter den 105 aktiven 61 Paare mit gleicher Marke und Zielseite und 38 mit gleichem `mechanic`; die Tabelle zieht davon die von Hand als dasselbe Angebot bestimmten Paare ab. Mit Konditionen teilen sich auch roh nur die zwei bekannten Paare einen Schlüssel, ein drittes doppelt aktives Angebot gibt es nicht.

Verworfen: „eine Zielseite, ein Angebot, solange kein Lauf zwei liefert“ legt 20 weitere Gruppen zusammen, darunter drei mit verschiedenen aktiven Angeboten (Telekom-PlusKarten, congstar Handys, winSIM Tarife). Lebenszeiten als Trennung (nie zusammenlegen, was sich zeitlich überlappt) vereint ohne zweites Merkmal nur 15 der 29 Paare, weil dasselbe Angebot oft im selben Lauf von zwei Quellseiten kommt.

## Ergebnis auf dem Schnappschuss

- 330 Einträge ergeben 294 IDs; 31 Gruppen werden zusammengelegt, alle von Hand gegen Titel und Beschreibung geprüft, keine falsche.
- Unter den 105 aktiven teilen sich keine zwei verschiedenen Angebote einen Schlüssel. Zwei Paare aktiver Einträge teilen ihn, und beide sind dasselbe Angebot von zwei Quellseiten: Vodafone FamilyCard XL (`886c392bc4433289`, `449a6737e39f600f`) und winSIM Unlimited on demand (`69837d8ae72029d6`, `23615f0eeb6abc31`). Danach bleiben 103 aktive.
- 12 Gruppen enthalten einen aktiven Eintrag und werden je ein Eintrag (Liste in `T1.json` unter `gruppen`). Das sind die „Paare“ aus `pakete.md`; gemessen sind es 12 Gruppen mit 15 überzähligen Einträgen statt der geschätzten 7 Paare.
- Bleibt offen: 18 der 29 Umformulierungen ändern auch die Zahlen der Beschreibung und bleiben getrennt, bis der alte Eintrag ausläuft. Für neue Läufe fängt der Rückfall auf `_same_offer` innerhalb von Marke und Zielseite einen Teil davon.

## Abnahme

`outputs/auftraege/T1-abnahme.py` hat der Testagent (Rolle `test`) aus `T1.json` geschrieben. Im Worktree als `tests/test_promo_identitaet.py`: 13 rot, 1 grün; die Zeile `AssertionError: lidl-jahrestarife: erwartet 1 Eintrag, erhalten 2` erfüllt `erwarteterFehler` nach der Regel `FACHLICH` aus `tools/auftrag.py`. Grün bleibt nur der Fall `wiederholung`, der heute schon gilt. Der Entwurf liegt außerhalb von `tests/`, weil ein roter Test auf `main` die Leiter rot macht. Paket 21 legt ihn über `tools/auftrag.py` an (Feld `abnahmeEntwurf`).
