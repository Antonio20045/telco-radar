# Promo-Quellen in die Breite — Schlussliste, 08.08.2026

Auftrag von Antonio: *„dass man wirklich alle Promo-Aktionen von den einzelnen
Unternehmen auf dem Schirm hat, dafür braucht es wahrscheinlich mehr als eine
Quelle pro Unternehmen, und dass du dir schaust, welche Domains zeigen noch
die Promo-Aktion."* Ausdrücklich **keine neuen Unternehmen** — die 15 Marken
bleiben, die Abdeckung je Marke wird tiefer.

## Das Ergebnis in einer Zeile

**15 Marken, 15 Seiten → 15 Marken, 59 Seiten.** 41 davon statisch abrufbar
(vorher 5), also lokal nachprüfbar und ohne Chromium-Start je Lauf.

| | vorher | nachher |
|---|---|---|
| Marken | 15 | 15 |
| abgefragte Seiten | 15 | **59** |
| davon `static` | 5 | **41** |
| davon `js` | 10 | 18 |
| Marken mit mehr als einer Seite | 0 | **12** |

## Warum eine Seite je Marke zu wenig war

Kein Anbieter zeigt seine laufenden Aktionen auf einer Seite. Gemessen an den
15 bisherigen Quellen: der Gerätedeal steht unter `/handys`, der Wechselbonus
unter `/wechselbonus`, die Prepaid-Aktion unter `/prepaid`, die
Junge-Leute-Aktion noch einmal woanders. Die Übersichtsseite, die bisher als
einzige konfiguriert war, verlinkt sie höchstens — und `extract_text()` wirft
alle `href`-Attribute weg, bevor irgendein Modell sie sieht.

Konkrete Beispiele aus der Recherche: ALDI TALKs `/wechselbonus` (die
Mechanik, die im Wichtigkeits-Score am schwersten wiegt) war nirgends erfasst.
klarmobil war ausschließlich über seine **Presseseite** beobachtet — die
Tarifseiten mit den tatsächlichen Aktionspreisen standen nirgends.

## Wie die Seiten gefunden wurden

Zwei neue Werkzeuge, beide nach dem Muster des Presse-Zweigs:

**`scripts/finde_promo_seiten.py`** — mechanische Breitensuche in zwei Stufen.
Stufe 1 liest die Links der bereits konfigurierten Seiten (eine
Aktionsübersicht verlinkt fast immer genau das, was ihr fehlt); Stufe 2
probiert 24 übliche Pfade auf der Markendomain, aber nur bei Marken, wo Stufe
1 wenig brachte. Ergebnis: **109 Kandidaten über 15 Marken.**

**`scripts/pruefe_promo_seite.py`** — der Abnahme-Check. Acht Kriterien im
Code, nicht im Modell: abrufbar über genau den Pipeline-Pfad · genug Text ·
≥ 4 verschiedene Angebotssignale · Mobilfunk statt Festnetz · eigene Domain
der Marke · noch nicht konfiguriert · **eigenständig** · zweimal stabil.

## Der Trichter

| Stufe | Zahl |
|---|---|
| Kandidaten aus dem Sucher | 109 |
| bestanden im Abnahme-Check | 67 |
| nach inhaltlicher Sichtung übrig | 44 |
| davon lokal per Check abgenommen | 40 |
| Telekom, nur per curl nachgemessen | 4 |

**Kriterium 7 (Eigenständigkeit) hat die Arbeit gemacht.** Es vergleicht jeden
Kandidaten nicht nur gegen den Bestand, sondern auch gegen die bereits
angenommenen Kandidaten derselben Marke — und genau das hat gegriffen:
congstars `prepaid-allnet-s/m/l/xl/xs` sind fünf Seiten mit demselben Gerüst,
vier davon fielen durch. Ohne diesen Vergleich hätten alle fünf bestanden, weil
jede einzelne sich vom *Bestand* unterscheidet. Das ist derselbe Fehler, an dem
Session 5 im Presse-Zweig 15 von 34 „bestandenen" Quellen verloren hat.

Gerechnet wird gegen die **kleinere** der beiden Wortmengen. Gegen die
Vereinigung gerechnet sähe eine Seite, die eine bestehende vollständig
*enthält*, fälschlich neu aus.

## Was verworfen wurde, obwohl es den Check bestand

Der Check prüft Form, nicht Wert — die Bewertung bleibt Handarbeit. Damit es
nicht beim nächsten Mal wieder vorgeschlagen wird, steht es als Kommentar in
der YAML:

* **winsim.de/info/…** — fünf SEO-Ratgeberartikel („Test Handytarife: So
  vergleichen Sie richtig"). Tragen Angebotswörter, aber kein Angebot.
* **o2online.de/internet-festnetz/homespot-tarife**, **alditalk.de/internet-zuhause/…** —
  Festnetzersatz. Genau das, was der Extraktor verwerfen soll.
* **congstar.de/prepaid/tarife/prepaid-allnet-{s,m,l,xl,xs}** — Einzeltarife.
  Die Prepaid-Übersicht deckt sie ab.
* **klarmobil.de/service/vertragsverlaengerung** — dünne Serviceseite.

## Drei Marken haben keine zweite Seite bekommen — und das ist die Antwort

Lücken zeigen statt verstecken:

* **Lidl Connect** ist eine Single-Page-App. `/tarife`, `/aktionen` und
  `/smart-tarife` liefern **byteweise dieselbe Hülle** (167 224 Bytes) wie die
  Startseite. Es *gibt* dort nur eine Seite.
* **simplytel** und **Penny Mobil** führen ihren vollständigen Katalog auf der
  Startseite; jeder Kandidat fiel an Kriterium 7 durch.

## Telekom — die eine dokumentierte Ausnahme

telekom.de beantwortet **jeden httpx-Abruf** mit HTTP 202 und einer 2-KB-
Challenge, auch mit Browser-User-Agent, auch beim zweiten Versuch derselben
Session. Dieselbe URL mit `curl`: HTTP 200 mit vollem Inhalt. Es ist eine
TLS-/Client-Erkennung, keine Sperre gegen dieses Projekt.

`pruefe_promo_seite.py` kann diese vier Seiten deshalb lokal nicht abnehmen.
Nachgemessen wurde per curl:

| Seite | Zeichen | verschiedene Preise |
|---|---|---|
| `/shop/tarife/handyvertrag` | 20 890 | 9 |
| `/shop/tarife/zusatzkarten` | 10 741 | 12 |
| `/shop/tarife/prepaid-tarife` | 8 220 | 6 |
| `/shop/tarife/smartphone-tarife-young` | 595 | 2 (nur JS) |

In Actions läuft der Abruf über Playwright — derselbe Weg, über den Telekoms
Leitseite seit Monaten funktioniert. **Offener Punkt: nach dem nächsten Lauf im
Protokoll nachsehen, ob diese vier Seiten Text geliefert haben.** Wenn nicht,
gehören sie wieder raus.

## Was an der Mechanik geändert werden musste

Drei Stellen, an denen ein Fehler nicht auffällt, sondern still Angebote
löscht — alle drei mit Test abgedeckt (`tests/test_promo_mehrseitig.py`):

1. **Der Snapshot-Schlüssel ist jetzt Marke + URL.** Als Markenschlüssel hätte
   jede Seite den Stand der zuletzt abgerufenen überschrieben; jede Seite hätte
   in jedem Lauf als verändert gegolten. Der alte Markenschlüssel gilt für die
   Leitseite genau einmal weiter, sonst hätte der erste Lauf nach der
   Umstellung eine komplette LLM-Neuextraktion über alle Marken ausgelöst.

2. **`mark_stale()` altert nur Angebote der wirklich gelesenen Seiten.** Das
   ist der teure Fehler gewesen, wenn er nicht gefixt worden wäre: eine Marke
   mit fünf Seiten hat pro Lauf typischerweise *eine* geänderte. Ohne diese
   Einschränkung wären die Angebote der vier unveränderten jedes Mal einen
   Schritt Richtung „ausgelaufen" gerückt — nach zwei Läufen wäre die halbe
   Marke verschwunden, und im Protokoll hätte das wie ein normaler Lauf
   ausgesehen. Jeder Eintrag trägt dafür jetzt seine Herkunftsseite
   (`source_url`); Bestandseinträge ohne eine hängen an der Leitseite.

3. **Die Obergrenze je Extraktion gilt jetzt je Seite, nicht je Marke** — und
   wurde deshalb von 8 auf 6 gesenkt. O2 hat sieben Seiten; 7 × 8 wären 56
   Zeilen unter einem Absender gewesen.

## Kosten

Kein Problem. Anbieter ist DeepSeek: rund **0,002 $ je Extraktion**. Selbst
wenn alle 59 Seiten in jedem Lauf wechselten, wären das ~1 $/Monat. Der
Snapshot-Diff sorgt ohnehin dafür, dass nur geänderte Seiten ein Modell sehen.

## Abnahme

* `pytest -q` → **532 Tests** (vorher 495; +37 neu)
* `scripts/pruefe_portal.py` → **11 von 11 bestanden**
* Trockenlauf der Promo-Stufe ohne LLM: 15 Marken / 59 Seiten abgefragt,
  41 statische Seiten alle erfolgreich; die 18 Fehler sind ausnahmslos
  `kind: js` (in der Sandbox fehlt das Playwright-Binary — dokumentierte
  Einschränkung, in Actions läuft es).

## Offen

1. **Nach dem nächsten Actions-Lauf** die vier Telekom-Seiten und die drei
   mobilcom-debitel-Seiten im Protokoll prüfen — beide Gruppen sind auf
   JS-Rendering angewiesen und lokal nicht abnehmbar.
2. **Nach zwei bis drei Läufen** auswerten, welche der 44 neuen Seiten
   tatsächlich Angebote beisteuern, die auf keiner anderen Seite der Marke
   stehen. Die Datengrundlage dafür ist jetzt da: jeder Eintrag trägt
   `source_url`.
3. `finde_promo_seiten.py` liest nur reines HTTP. Bei JS-lastigen Marken
   (Telekom, mobilcom-debitel, Lidl Connect) findet es deshalb weniger, als
   wirklich da ist. In Actions wäre eine Suchrunde mit Playwright ergiebiger.
