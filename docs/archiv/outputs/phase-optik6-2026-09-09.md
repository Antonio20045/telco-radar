# Phase OPTIK-6 — TCO-Reiter unter 3000 px (`pruefe_portal` 11b)

**Auftragsgrundlage:** `BRIEF_OPTIK-6` (PM, 09.09.2026), Basis `6143e52` (origin/main).
Ticket ROADMAP OPTIK-6, Klasse C. Branch `openclaw/ticket-optik6`, kein Merge, kein
Deploy (Abnahme PM).

**Eine Änderung trägt das Ticket:** Die Anbieterkarten (TCO-Karten, Referenzkarte,
Leerkarten, Händlerkarten) stehen je Modellblock in EINER standardmäßig
geschlossenen `<details>`-Klappe; Sortierung und Anbieterfilter wandern mit in die
Klappe. Nichts ist gelöscht, kein Daten-Layer angefasst, kein Netzwerk im Spiel —
der Anfangszustand des Reiters hängt damit nicht mehr an der Zahl der Bündel.

---

## 1. Kriterium 1 — 11b grün

`python3 scripts/pruefe_portal.py --site <Render>` (Chromium 1440×900, Klick je
`.gr-reiter [data-tafel]`, `document.documentElement.scrollHeight`):

| Reiter | vor (`6143e52`) | nach | Grenze |
|---|---|---|---|
| `tafel-tco` | **4732 px** | **1959 px** | < 3000 |
| `tafel-katalog` | 1902 px | 1902 px | < 3000 |

```
11b. Reiterhoehen: tco 1959, katalog 1902 px   BESTANDEN
```

Gesamtbild des Laufs: **17 bestanden / 0 durchgefallen / 0 nicht prüfbar**
(gemessen am frischen Vollrender `/tmp/optik6_site_b`; gegen den committeten
`site/`-Ordner in § 7.3 dasselbe Ergebnis).

### Wo die 4732 px saßen (Blockmessung am Altstand, Chromium 1440 px)

Der sichtbare Modellblock des Vorgabemodells war 3758 px hoch, davon:

| Block | Höhe |
|---|---|
| **`.gr-karten` (22 Karten, 4 Spalten)** | **2749 px** |
| Tarifband-Block GRAPH-1 (ein Band sichtbar) | 376 px |
| Zeitreihe G0 | 313 px |
| Antwortzeile | 105 px |
| Überschrift, „Wie gerechnet?“, Händlerzeile, mband, Steuer | ~121 px |
| Rest der Tafel (Auswahl, Details-Klappen zu, Export) | ~749 px Seitenchrom + ~182 px |

Kartenverteilung über alle 88 Modellblöcke: **7 bis 24 Karten** (24×7, 33×9,
10×8, …, je 1×16/21/22/24). Die Anfangshöhe hing also allein am Bündelbestand
(579 Bündel, täglich wachsend) — ein Deckel in Karten wäre eine Auswahl nach
Listenposition gewesen (CLAUDE.md § 6, Fehlerklasse `max_produkte`). Die Klappe
koppelt die Anfangshöhe vom Bestand ab: **1959 px egal wie viele Karten**.

## 2. Kriterium 2 — kein Informationsverlust (E1)

Maschineller Vergleich Alt- vs. Neu-Render **aus derselben Datenbasis**
(`/tmp/optik6_site_a` = `6143e52`, `/tmp/optik6_site_b` = dieser Stand; Skript im
Anhang § 8):

| Größe | Alt | Neu | identisch |
|---|---|---|---|
| Karten je (Modell, Anbieter, Laufzeit, Schnitt, Gesamt, Einmalig, Zustand) | 852 | 852 | ✅ Multiset |
| Tabellenzeilen: Alarm / Leitzahl / SIM-only / Bereitschaft | 98 / 418 / 41 / 10 | 98 / 418 / 41 / 10 | ✅ |
| Euro-Beträge im Reitertext (Multiset) | 11 616 | 11 616 | ✅ |
| Fließtext des Reiters | — | — | einziger Diff: die neuen Summary-Zeilen „Anbieterkarten (N)“ |

Die Zahl in der Klappe zählt die Karten DER KLAPPE (Angebote, Referenzrechnung,
Leerkarten, Händler zusammen — Vorgabemodell: 22); die `gr-mband`-Zeile darüber
nennt die Angebote (19) — zwei verschiedene Mengen mit verschiedenen Wörtern, wie
bei der Legende der alten Positionskarte („Jede Zahl … meint die gezeichnete
Menge“). Ein statischer Test hält die Klammer gegen den Kartenbestand.

## 3. Kriterium 3 — Aufklapp-Verhalten getestet

**Drei neue Tests** (rot auf dem Altstand nachgemessen — Template kurz auf
`HEAD` zurückgesetzt, alle drei FAILED, dann meine Fassung byte-identisch
zurückgeholt):

1. `tests/test_geraete_rahmen.py::test_die_anbieterkarten_stehen_in_einer_geschlossenen_klappe`
   — statisch: Klappe existiert je Modellblock, trägt KEIN `open`, enthält
   `.gr-ksteuer` und alle Karten; keine Karte außerhalb; Klammerzahl == Karten
   der Klappe.
2. `tests/test_geraete_reiter_browser.py::test_die_kartenklappe_startet_geschlossen`
   — Browser: nach Reload ist die Klappe des sichtbaren Modells zu und trägt
   Karten (genau der Zustand, den 11b misst).
3. `tests/test_geraete_reiter_browser.py::test_die_kartenklappe_oeffnet_ohne_netzwerk`
   — Browser: `open = true` macht die erste Karte sichtbar (offsetParent,
   489 px Höhe), und **keine einzige Netzwerkanfrage** entsteht dabei
   (`page.on('request')`-Zähler bleibt leer); danach stellt der Test die Klappe
   wieder zu (Seite hat Modulgültigkeit).

Rot-vor-Nachweis (Altstand `6143e52`-Template):

```
FAILED tests/test_geraete_rahmen.py::test_die_anbieterkarten_stehen_in_einer_geschlossenen_klappe
FAILED tests/test_geraete_reiter_browser.py::test_die_kartenklappe_startet_geschlossen
FAILED tests/test_geraete_reiter_browser.py::test_die_kartenklappe_oeffnet_ohne_netzwerk
```

**Zwei bestehende Tests angepasst, je mit Grund:**

- `tests/test_geraete_reiter_browser.py::_frisch`: öffnet zusätzlich die
  Kartenklappe des sichtbaren Modellblocks — dasselbe Muster, das die Funktion
  schon für die verschachtelten `#gr-details`/`#gr-alarme`-Klappen fährt
  (`<details>` verbirgt Nachfahren transitiv; `select_option` braucht ein
  sichtbares Element). Ohne das fiele `test_die_sortierung_ordnet_nach_dem_rohwert`.
- `tests/test_geraete_rahmen.py::test_ein_block_ohne_graph_…`: die Positionsprüfung
  „Wie gerechnet? steht NACH den Karten“ läuft gegen die KLASPE (direktes Kind
  des Modellblocks), nicht mehr gegen den Kartenbehälter — der ist seit OPTIK-6
  ein Enkel.

**Von Hand durchgespielt** (Chromium, echte Interaktion): Klick auf den Summary
öffnet die Klappe (Seite wächst auf 4758 px — erlaubt, 11b misst den
Anfangszustand), Sortierung „Gerät einmalig“ und Anbieterfilter „congstar“
wirken in der Klappe (8 congstar-Karten sichtbar), Screenshots beider Zustände
angesehen (`/tmp/optik6_aufgeklappt.png`, `schiess_screenshot.py`: „keine
Beanstandungen“). Das Kartenraster (4 Spalten) und alle Kartenfelder — Leitzahl,
Ø/Monat, BAU-Zeile, Pflichtzeile „nach 24 Monaten gezahlt“, „ab Monat 25“,
Delta, Rechenweg-Aufklapper — stehen unverändert.

**Vierter Test nachgelegt** (nach diff-reviewer-Hinweis auf die seit Phase R
ungetestete Filterbahn):
`tests/test_geraete_reiter_browser.py::test_der_anbieterfilter_wirkt_auch_in_der_klappe`
— Klappe auf (über `_frisch`), Anbieterfilter auf einen Anbieter, nur dessen
Karten bleiben; Gegenprobe ohne Filter zeigt mindestens zwei Anbieter.

### diff-reviewer

Lief vor dem Commit über den Diff (Prüfkatalog `docs/clean-code-referenz.md`):
**keine S1, keine S2.** Verifiziert u. a.: Jinja-Präzedenz `|length + |length`
korrekt (alle 88 Klammerzahlen gegen den Kartenbestand des echten
`site/geraete.html` nachgezählt, 0 Abweichungen); `app.js` erreicht Karten und
Steuerung nur über Nachfahren-Sucher (`querySelector`), kein `children`/Sibling-
Pfad; kein `>`-CSS-Selektor auf `.gr-karten`/`.gr-ksteuer`; je Klappe genau ein
`summary` als erstes Kind; `site/geraete.html` byte-identisch aus `render_site`
reproduzierbar. Zwei S3 behoben:

1. `tests/test_geraete_faden.py` — Docstring von
   `test_die_anbieterkarten_stehen_ausserhalb_der_details_aufklappung`
   behauptete noch, die Anbieterkarten dürften „NICHT hinter der Klappe
   verschwinden“; seit OPTIK-6 haben sie die eigene (Karten-)Klappe. Der Satz
   unterscheidet jetzt Analyse-Klappe (`#gr-details`) von Karten-Klappe
   (`gr-karten-auf`) — sonst „repariert“ die nächste Session die Regel zurück.
2. Netzwerk-Assertion des neuen Browser-Tests zählte JEDE Anfrage; späte
   Google-Fonts-Anfragen könnten ihn auf kaltem Runner falsch rot machen.
   Gezählt werden jetzt Same-Origin-Anfragen — der scharfe Maßstab für „kein
   Nachladen von Inhalten“.

## 4. Kriterium 4 — Fremd-byte-unchanged

Vollrender aus `data/` gegen den committeten `site/`-Stand:

```
diff -rq /tmp/optik6_site_b site/  →  nur geraete.html unterscheidet sich
```

`site/tarife.html`, `site/wettbewerbsradar.html`, alle Exporte/CSV,
`site/data/*` (inkl. `keyword-index.json`): **byte-identisch.** In `site/geraete.html`
übernommen; der Diff ist ausschließlich die Karten-Klappe je Modellblock
(88× `gr-ksteuer`+`gr-karten` in `<details class="gr-auf gr-karten-auf">` plus
Einrückung; 1760 der Diff-Zeilen sind leer/reine Einrückung, keine inhaltliche
Zeile außerhalb des Kartenblocks).

## 5. Kriterium 5 — Suite

Vollsuite `PYTHONPATH=src python3 -m pytest -q` (nach allen Review-Korrekturen):

```
2924 passed, 12 skipped in 314.71s   (EXIT=0)
```

Baseline laut Brief: 2920/0/12 (Baum) — also **+4 (drei Klapp-Tests plus der
nachgelegte Anbieterfilter-Test), 0 rot, 12 skipped wie in der Baseline**; die
erlaubte Promo-Abweichung (2918/0/14) war nicht nötig, die zwei
umgebungsabhängigen Roten sind in dieser Umgebung nicht aufgetreten.

Baseline laut Brief: 2920/0/12 (Baum); erlaubte einzige Abweichung: 2918/0/14
(die zwei bekannten umgebungsabhängigen Promo-Roten). Zuwachs durch dieses
Ticket: +3 Tests (alle grün, rot-vor belegt).

## 6. Kriterium 6 — kein Daten-Layer-Touch

`git status` während der ganzen Arbeit: nur
`site/geraete.html`, `src/…/templates/geraete.html.j2`,
`tests/test_geraete_rahmen.py`, `tests/test_geraete_reiter_browser.py` (plus
dieser Bericht). **Kein `data/state/*`, kein `data/reports/*`, kein Sammeln,
keine Requests** (der einzige Browser-Anteil misst lokal über 127.0.0.1).
`uv.lock` unangetastet und uncommittet.

## 7. Bewusst offen / Grenzen

1. **Die Klappe versteckt die Karten im Anfangszustand komplett.** Das ist die
   Klasse-C-Entscheidung des PM („Abschnitte standardmäßig geschlossen klappen“)
   und skaliert mit dem Bündelbestand; die Antwortzeile, G0 und der
   Tarifband-Graph beantworten die Leitfrage weiterhin ohne Klick. Soll künftig
   z. B. die erste Kartenreihe offen bleiben, ist das eine neue
   Produktentscheidung (und braucht JS, das den Split nach jeder Sortierung
   neu verteilt) — nicht gebaut.
2. **Nebenbefund 8b (65 leere Promo-Bilder)** ist NICHT angefasst, wie der Brief
   verlangt — und reproduziert in diesem Worktree nicht: gegen den committeten
   `site/`-Stand (65 Dateien unter `site/promo/images/`, keine davon 0 Byte)
   meldet `pruefe_portal.py` 8b mit **0** leeren Bildern. Der PM-Befund vom
   Morgen betraf vermutlich den Live-Stand; hier nur protokolliert, nicht
   behandelt.
3. **`pruefe_portal.py` auch gegen den committeten `site/`-Ordner** (mit neuem
   `geraete.html`) gemessen: **17 bestanden / 0 durchgefallen / 0 nicht
   prüfbar**, 11b „tco 1959, katalog 1902 px“ — dasselbe Bild wie am
   Vollrender in § 1.
4. **CLAUDE.md § 5** (Zeile zu `geraete.html`) nicht aktualisiert — der Stand
   dort beschreibt ohnehin schon nicht mehr die FADEN-Umbauten vom 05.09.;
   Handover-Pflege ist nicht Teil dieses Tickets.
5. Mobile (390 px): Karten stehen in der Klappe auf 1 Spalte (`@media
   (max-width:900px)` greift unverändert); `schiess_screenshot.py` meldet für
   `geraete-telefon.png` „keine Beanstandungen“.

---

## 8. Anhang — Vergleichsskript E1

```python
from bs4 import BeautifulSoup
from collections import Counter
import re

def schnapp(pfad):
    s = BeautifulSoup(open(pfad, encoding='utf-8').read(), 'html.parser')
    t = s.select_one('#tafel-tco')
    karten = [(m.get('data-modell'), k.get('data-anbieter'), k.get('data-laufzeit'),
               k.get('data-schnitt'), k.get('data-gesamt'), k.get('data-einmalig'),
               k.get('data-zustand'))
              for m in t.select('.gr-tmodell') for k in m.select('.gr-kkarte')]
    zeilen = Counter({tuple(tab.get('class') or []):
                      len(tab.select('tbody tr')) for tab in t.select('table')})
    euros = Counter(re.findall(r'\d[\d.,]*\s*€', t.get_text(' ', strip=True)))
    return karten, zeilen, euros, t.get_text(' ', strip=True)
# alt = Render aus 6143e52, neu = Render aus diesem Stand (gleiche data/-Basis)
# → Counter(ka)==Counter(kb), za==zb, ea==eb; Textdiff: nur „Anbieterkarten (N)“
```

(Ausgeführt am 09.09.2026, 10:5x; Zahlen in § 2.)

## 9. Commits

1. `optik6: Anbieterkarten des TCO-Reiters hinter einer Klappe — 11b 4732 → 1959 px`
   — Template, `site/geraete.html`
2. `optik6: Tests zur Kartenklappe (geschlossen starten, ohne Netz öffnen, Filter) + drei angepasste`
   — `tests/test_geraete_rahmen.py`, `tests/test_geraete_reiter_browser.py`,
   `tests/test_geraete_faden.py`
3. `optik6: Abschlussbericht` — `outputs/phase-optik6-2026-09-09.md`
