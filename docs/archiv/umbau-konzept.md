Stand: 2. Oktober 2026 – Markdown-Export des Konzepts, Quelle ist das Claude-Doc.

# Agenten-Entwicklungssystem für Telco Radar

Stand Oct 2, 2026 · @Antonio

Telco Radar braucht kein zweites Hermes, sondern drei Dinge in dieser Reihenfolge: eine lokale Prüfleiter auf deinem Mac, die in unter vier Minuten entscheidet, Tests, die nicht mehr am täglich wechselnden Bot-Bestand hängen, und einen Umbau der zwei Gott-Funktionen samt einer Report-Schicht, die nur noch rechnet. Lint, Typabdeckung, Duplikate und toter Code sind schon ordentlich; schlecht sind Struktur und Testaufbau. Bis Prüfleiter und hermetische Tests stehen, entstehen keine neuen Funktionen. Weil du allein arbeitest, fällt alles weg, was bei Hermes nur dazu da war, zwei Menschen und ein Maschinenkonto gegeneinander abzusichern.

## Ausgangslage und Messbefund

Gemessen wurde am 2. Oktober 2026 auf Commit `b7e2e5e` in einer Sandbox mit 2 vCPU und Python 3.13, mit radon, ruff 0.16.8, mypy, vulture, jscpd, eigenen AST-Skripten und einem vollen Testlauf. Dein Eindruck „der Code ist schlecht“ stimmt für die Struktur, aber nicht für das Handwerk im Kleinen. Die Tabelle trennt beides.

| Bereich | Messung | Urteil |
| --- | --- | --- |
| Umfang | `src/` 56.719 Zeilen in 123 Dateien, `tests/` 79.417 Zeilen in 203 Dateien (1,4 : 1), `scripts/` 9.578 | Testmenge reicht, ihr Aufbau nicht |
| Lint | 290 Befunde mit `E,F,W,B,SIM,C90`, davon 20 × F (19 unbenutzte Importe) | ordentlich, Konfiguration fehlt |
| Typen | 82,4 % der Funktionen vollständig annotiert, `mypy` meldet 237 Fehler (63 arg-type, 50 index), keine mypy-Konfiguration | gute Basis, nie geprüft |
| Duplikate | 0,13 % kopierte Zeilen (jscpd), aber `_preis` viermal in den Geräteadaptern | kein Problem |
| Toter Code | 1 Treffer bei Konfidenz 80, 38 Funktionen nur von Tests benutzt | kein Problem |
| Gott-Funktionen | `pipeline.py:517 run` 986 Zeilen, cc 150; `report/html.py:1176 render_site` 966 Zeilen, cc 160; 74 Funktionen mit Rang D bis F | Hauptproblem |
| Dateigröße | 44 Dateien über 400 Zeilen, 13 über 1.000, 3 über 2.000; vier Dateien mit Maintainability Index 0,00 | Hauptproblem |
| Schichtung | 72 Datei- und Netzaufrufe in `report/` (45 in `html.py`), eigene `httpx.Client` in `report/bilder.py:385` und `diff_bilder.py:170`, 3 Importzyklen, 49 Importe in Funktionsrümpfen | Hauptproblem |
| Fehler und Zeit | 79 × `except Exception`, 86 Handler mit `pass`, `continue` oder Leerwert, 94 direkte Uhraufrufe | widerspricht CLAUDE.md Clean Code 5 und Harte Regel 11 |
| Kommentare | 17,4 % Kommentarzeilen, 25,0 % Docstrings, 770 Datumsangaben, 59 × „Antonio“, 48 tote Verweise auf „CLAUDE.md §“ | Änderungsprotokoll statt Erklärung |
| IDs | `promo_store.py:161` hasht Marke plus Überschrift; im Bestand 7 Paare, bei denen dasselbe Angebot aktiv und ausgelaufen zugleich ist | belegter Fehler |
| Tests | 3.981 Tests, 17,6 Minuten seriell, 16 rot, alle 16 wegen des echten `data/state` | Hauptproblem |
| Werkzeuge | kein ruff, kein mypy, kein pre-commit, Edit-Hook mit Exit-Code immer 0, Stop-Hook auf einen Mac-Pfad außerhalb des Repos, `push-live.sh` ohne Tests | Grenze fehlt |
| Git | Historie 145,6 MB, davon 82 % `data/` und `site/`; 82 Remote-Branches; `_to_delete/` mit 7 MB eingecheckt | Ballast |

Drei Befunde tragen das ganze Konzept. Erstens wird die Suite rot, ohne dass sich Code geändert hat: Rund 890 Tests in 48 Dateien lesen `data/state` oder `data/reports`, und der Bot schreibt diese Dateien täglich fort. Ein System, das nur Exit-Codes liest, lernt so, Rot zu übersehen. Zweitens gibt es keine Prüfung, die etwas aufhält: Der einzige Hook endet immer mit Exit 0, und `ci.yml` läuft erst nach dem Push. Drittens konzentriert sich die schlechte Struktur auf wenige Stellen, nämlich zwei Funktionen mit zusammen fast 2.000 Zeilen und die Geräte-Report-Module; dort lässt sich gezielt umbauen, statt das ganze Repo neu zu schreiben.

## Zielbild

Das System hat sechs Schichten, geordnet danach, wie schwer ein Agent sie umgehen kann. Heute trägt bei Telco Radar fast alles die unterste: CLAUDE.md mit 17 harten Regeln und 10 Clean-Code-Regeln, die ein Agent lesen und befolgen soll, und ein Prüf-Agent (`diff-reviewer`) gegen einen Katalog von 565 Zeilen. Das Ziel ist, das Gewicht nach oben zu verschieben, wo ein Exit-Code entscheidet.

*Diagramm: Prüfschichten · nach Durchsetzungskraft geordnet*

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 536" role="img" aria-label="Vier Schichten entscheidet die Maschine, zwei das Modell" font-size="13" font-family="Inter, Arial, sans-serif">
<text x="24" y="34" font-size="15" font-weight="600" fill="#1a1a1a">Vier Schichten entscheidet die Maschine, zwei das Modell</text>
<path d="M172 60H164V308H172" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="152" y="180" text-anchor="end" font-weight="600" fill="#1a1a1a">Maschine</text>
<text x="152" y="196" text-anchor="end" font-size="11.5" fill="#666666">entscheidet</text>
<path d="M172 316H164V436H172" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="152" y="372" text-anchor="end" font-weight="600" fill="#1a1a1a">Modell</text>
<text x="152" y="388" text-anchor="end" font-size="11.5" fill="#666666">entscheidet</text>
<path d="M172 452H164V508H172" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="152" y="476" text-anchor="end" font-weight="600" fill="#1a1a1a">Du</text>
<text x="152" y="492" text-anchor="end" font-size="11.5" fill="#666666">entscheidest</text>
<rect x="180" y="60" width="556" height="56" rx="8" fill="#e60000" fill-opacity="0.12" stroke="#e60000" stroke-width="1.5"/>
<text x="196" y="83" font-weight="600" fill="#1a1a1a">1 · Code und Struktur</text>
<text x="196" y="102" font-size="11.5" fill="#1a1a1a">Schichten collect → analyze → laden → report, Sichtmodelle, Uhr als Argument</text>
<rect x="180" y="124" width="556" height="56" rx="8" fill="#e60000" fill-opacity="0.12" stroke="#e60000" stroke-width="1.5"/>
<text x="196" y="147" font-weight="600" fill="#1a1a1a">2 · Statische Prüfung, Stufen 0 bis 3</text>
<text x="196" y="166" font-size="11.5" fill="#1a1a1a">Wächter, ruff, mypy gegen Basis, import-linter-Verträge, in Sekunden</text>
<rect x="180" y="188" width="556" height="56" rx="8" fill="#e60000" fill-opacity="0.12" stroke="#e60000" stroke-width="1.5"/>
<text x="196" y="211" font-weight="600" fill="#1a1a1a">3 · Tests, Stufen 4 und 5</text>
<text x="196" y="230" font-size="11.5" fill="#1a1a1a">betroffene Tests, volle Suite parallel, Orakel, goldener Lauf, mutmut im Auftrag</text>
<rect x="180" y="252" width="556" height="56" rx="8" fill="#e60000" fill-opacity="0.12" stroke="#e60000" stroke-width="1.5"/>
<text x="196" y="275" font-weight="600" fill="#1a1a1a">4 · Lokale Sperren</text>
<text x="196" y="294" font-size="11.5" fill="#1a1a1a">pre-commit, pre-push mit voller Leiter, deny-Liste, Rollen-Hooks, Stop-Hook</text>
<rect x="180" y="316" width="556" height="56" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="196" y="339" font-weight="600" fill="#1a1a1a">5 · Prüfer-Agent</text>
<text x="196" y="358" font-size="11.5" fill="#666666">Opus mit frischem Kontext, ein Befund zählt nur mit roter Reproduktion</text>
<rect x="180" y="380" width="556" height="56" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="196" y="403" font-weight="600" fill="#1a1a1a">6 · Anweisungen</text>
<text x="196" y="422" font-size="11.5" fill="#666666">CLAUDE.md höchstens 100 Zeilen, Ordner-CLAUDE.md, Wissen erst beim Verstoß</text>
<rect x="180" y="452" width="556" height="56" rx="8" fill="#f1f1f1" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="196" y="475" font-weight="600" fill="#1a1a1a">Antonio</text>
<text x="196" y="494" font-size="11.5" fill="#666666">was die Seite zeigen soll, Namen der Abnahmetests, jede gelockerte Prüfung</text>
</svg>
```

Die oberen vier Schichten laufen ohne Modell und vollständig auf deinem Mac; die Schichten 2 bis 4 sind dieselbe Prüfleiter, nur zu verschiedenen Zeitpunkten aufgerufen. Das Modell urteilt nur dort, wo eine Regel sich nicht mechanisch fassen lässt, etwa ob ein Modulschnitt taugt. Du entscheidest, was du ohne Code beurteilen kannst: welche Zahl die Seite zeigen soll und ob eine Prüfung gelockert wird.

## Die Grenze ist eine lokale Prüfleiter

Bei Hermes ist GitHub die Grenze, weil zwei Menschen, ein Maschinenkonto und mehrere Werkzeuge in dasselbe Repo schreiben. Bei Telco Radar schreibst nur du, mit Claude Code auf deinem Mac, und die Bots in Actions schreiben nur `data/` und `site/`. Die Grenze steht deshalb dort, wo jeder deiner Commits vorbeikommt: in einem einzigen Skript `scripts/pruefleiter.py`, das `make pruefen` aufruft und das Git-Hooks, Claude-Hooks und `tools/auftrag.py` gleichermaßen benutzen. Es gibt keinen zweiten Weg, Tests zu starten, der etwas anderes prüft.

### Die Stufen

Die Leiter läuft von billig nach teuer und bricht bei der ersten roten Stufe ab. So kostet ein Tippfehler zwei Sekunden statt einer vollen Suite.

| Stufe | Werkzeug | Prüft | Ziel auf M4 Pro |
| --- | --- | --- | --- |
| 0 Wächter | eigenes Skript | Dateien über 400 Zeilen nur auf der Schrumpfliste, CLAUDE.md ≤ 100 Zeilen, kein `continue-on-error` und kein `\|\| true` in Workflows außer an benannten Stellen, kein Testzugriff auf `data/state` | unter 1 s |
| 1 Lint | `ruff check` | Regeln aus dem Anhang, nur neue Befunde zählen | unter 2 s |
| 2 Typen | `mypy` gegen `pruef/mypy-basis.txt` | Fehler je Datei und Fehlercode dürfen nicht steigen | 10 bis 20 s, mit Cache |
| 3 Schichten | `lint-imports` (import-linter) | Verträge collect → analyze → laden → report, ein Netzweg, keine Zyklen | unter 3 s |
| 4 Betroffen | `pytest` auf Auswahl | Tests, die ein geändertes Modul direkt importieren, ohne Marker `browser`, `langsam`, `golden`; harte Kappe 45 s | unter 15 s, gerechnet unten |
| 5 Voll | `pytest -n auto` | ganze Suite außer Marker `netz` | unter 4 min, gerechnet 2,3 min |

Stufe 4 wählt Tests über die direkte Zuordnung aus, nicht über alle Wege im Importgraphen. Die transitive Auswahl wäre zu breit: Laut grimp erreicht ein geändertes Modul im Median 68 von 201 Testdateien, `models.py` 133, und dann wäre die schnelle Stufe fast die volle Suite. Direkt importiert wird ein Modul im Median von 2 Testdateien, im 90. Perzentil von 14 und höchstens von 56 (`report/html.py`). Nur für 6 Module gibt es keine direkte Testdatei, und das sind fünf Paket-`__init__` und `collect/newsroom_js.py`; der heutige Hook findet mit seinem Namensmuster für 43 von 116 Modulen nichts. Aus dieser Auswahl fallen Tests mit den Markern `browser`, `langsam` und `golden` heraus. Gerechnet mit den seriellen Zeiten der Messung vom 2. Oktober dauert die Auswahl dann im Median 0,2 s, im 90. Perzentil 9,8 s, im 99. Perzentil 40 s und höchstens 60 s (`report/html.py`). Schätzt die Leiter aus `.pruefleiter/zeiten.json` mehr als 10 s, startet sie die Auswahl mit `-n 4`, was die 40 s auf rund 10 s plus 3 s Start der Worker bringt. Nach 45 s bricht sie ab und meldet „schnelle Stufe unvollständig, pre-push prüft voll“. Das ist eine Warnung und kein Rot, weil die Grenze im pre-push liegt; ein Abbruch darf den Commit nicht blockieren, sonst wird der Hook umgangen. Bei geänderten Vorlagen, `style.css` oder `app.js` nimmt die Stufe die Tests mit Marker `seite` dazu, bei Änderungen an `config/`, `pyproject.toml` oder `conftest.py` springt sie gleich in Stufe 5.

Die Basislinie in Stufe 2 friert die 237 heutigen mypy-Fehler ein, ohne Zeilennummern, damit eine eingefügte Zeile keinen Fehlalarm auslöst. Sinkt eine Zahl, schreibt das Skript die Basis automatisch kleiner; steigen kann sie nur durch eine Handänderung an der Datei, und die steht unter der deny-Liste für Agenten. Dasselbe Verfahren gilt für ruff-Ausnahmen und die Liste der Riesendateien.

### Ausgabe

Bei Erfolg schreibt die Leiter genau eine Zeile, etwa `pruefen: grün · 3.965 Tests · 3 min 12 s`. Bei einem Fehler schreibt sie höchstens 60 Zeilen: die Stufe, je Befund Datei:Zeile, Erwartung und Ergebnis, und wo eine Regel verletzt ist, den Satz „Regel siehe CLAUDE.md, Abschnitt Schichten“. Das volle Protokoll liegt in `.pruefleiter/letzter-lauf.log`, das in `.gitignore` steht. Ein Agent bekommt damit nie 3.981 Zeilen pytest-Ausgabe in den Kontext, sondern nur das, was er reparieren muss.

### Git-Hooks

Die Hooks liegen als Skripte in `.githooks/` und werden mit `git config core.hooksPath .githooks` aktiv. Das setzt `make einrichten` einmal auf dem Mac und ein SessionStart-Hook in `.claude/settings.json` in jeder Claude-Sitzung, auch in Web-Sitzungen, deren Klon diese Einstellung sonst nicht hätte. Ich nehme bewusst nicht das pre-commit-Framework: Es installiert ruff und mypy in eigene Umgebungen mit eigenen Versionen, und dann prüfen Hook und `make pruefen` mit verschiedenen Werkzeugständen.

- **pre-commit** ruft `pruefleiter.py --schnell` auf: Stufen 0, 1 und 4 auf den vorgemerkten Dateien. Gerechnet sind das im 99. Perzentil rund 1 s für Stufen 0 und 1 und höchstens 15 s für Stufe 4; über 30 Sekunden würde er umgangen.
- **pre-push** ruft die volle Leiter auf, Stufen 0 bis 5, auf dem Stand, der gepusht wird. Vorher prüft er, dass der lokale Zweig `origin/main` enthält; sonst bricht er mit „erst `git pull --rebase`“ ab, weil eine grüne Suite auf einem veralteten Stand die Lehre aus P1 wiederholen würde (main war eine halbe Stunde rot, weil nach dem Messen rebased wurde).
- **`--no-verify`** und `git commit -n` stehen in der deny-Liste von Claude Code, ebenso jede Veränderung von `core.hooksPath`. Für dich selbst ist das keine Sperre, und das ist im Solo-Betrieb richtig so. Für Agenten ist es eine Bremse, aber keine Grenze, wie der nächste Absatz zeigt.

Ehrlich gesagt ist lokal nichts eine harte Grenze. Die deny-Liste vergleicht Befehlstexte, und `git -c core.hooksPath=/dev/null push` oder ein `python -c` mit `subprocess` steht auf keiner Liste und umgeht beide Git-Hooks. Die tatsächliche Absicherung ist deshalb eine Erkennung statt einer Sperre. Nach jedem grünen Lauf der vollen Leiter schreibt `pruefleiter.py` einen Stempel mit der Baum-ID des geprüften Stands (`git rev-parse HEAD^{tree}`) nach `.git/pruefleiter/gruen/`. Der SessionStart-Hook und `make stand` listen jeden Commit auf `origin/main` seit dem letzten Abgleich, dessen Baum keinen Stempel hat, und `tools/auftrag.py` startet keinen neuen Auftrag, solange es solche Commits gibt. Ein Agent kann also an den Hooks vorbei pushen, aber nicht unbemerkt; die nächste Sitzung beginnt mit der Zeile „2 Commits auf main ohne grünen Prüflauf“. Der Stop-Hook ist die zweite Erkennung, weil er die schnelle Leiter am Ende jeder Sitzung läuft, unabhängig davon, was vorher committet wurde.

### Zielzeit und warum sie erreichbar ist

Die volle Suite brauchte am 2. Oktober seriell 1.058 Sekunden auf 2 vCPU, ohne den netzgebundenen Test in `test_redaktion_kontinuitaet` (82 s) sind es 976 Sekunden. Von den 928 Sekunden des ersten, nach Dateien aufgeschlüsselten Teils entfallen 531 s auf die 31 Browserdateien, 216 s auf Dateien, die `render_site` aufrufen, 97 s auf reine Logik und 84 s auf den Netztest. Chromium selbst ist dabei billig: Start 0,4 s, neue Seite 0,2 s, gemessen in derselben Sandbox. Teuer ist das Rendern, ein vollständiges `render_site` dauert dort 11,4 s, und `test_newsletter_seite` kopiert für fast jeden seiner 21 Tests `config/` und `data/` und rendert neu, daher seine 211 Sekunden.

Die Zielzeit rechnet sich ohne jede Annahme über schnellere Kerne. Der M4 Pro hat 12 oder 14 Kerne, davon 8 oder 10 Leistungskerne; gerechnet wird mit 10 Workern und 70 % Wirkungsgrad: 976 s / (10 × 0,7) = 139 s, also 2,3 Minuten. Der kritische Pfad ist danach der längste einzelne Test mit 15 s, solange `pytest-xdist` mit `--dist worksteal` verteilt und nicht nach Dateien gruppiert. Mit `--dist loadgroup` wäre allein `test_newsletter_seite` mit 211 s die Untergrenze, deshalb steht diese Option nicht mehr im Anhang. Chromium startet je Worker einmal über eine Session-Fixture, was ohnehin kaum Zeit kostet. Der größere Puffer kommt aus dem Rendern: Render- und Browsertests zusammen kosten 747 s, also grob 65 vollständige Renderläufe. Rendert eine Session-Fixture jede benötigte Variante (Schnappschuss plus Konfiguration) nur einmal, geschätzt zehn Varianten, sinkt die serielle Zeit um rund 600 s. Das ist eine Schätzung; gemessen wird in Schritt 4. Bleibt die Messung trotzdem über vier Minuten, wandern die langsamsten Browsertests in den Marker `langsam`, der nur im pre-push läuft.

### Was bewusst fehlt

Bewusst fehlen ein Ruleset, eine PR-Pflicht, eine Merge-Queue, ein Maschinenkonto, eine Organisation, Blue-Green und Cron-Prüfläufe. Jedes dieser Teile löst bei Hermes ein Problem, das hier nicht existiert. Ein Ruleset und eine PR-Pflicht sichern ab, dass ein Mensch nicht am anderen vorbei mergt; du bist der einzige Mensch, und die Bots schreiben nur generierte Dateien. Eine Merge-Queue löst Konflikte zwischen gleichzeitig grünen Branches, bei höchstens zwei Worktrees reicht `git merge --ff-only` nach einem Prüflauf. Ein Maschinenkonto trennt Rechte zwischen Menschen und Agenten; für einen Einzelnen reichen deny-Liste und Prüfstempel, die einen Agenten zwar nicht hart aufhalten, aber jeden ungeprüften Push sichtbar machen. Blue-Green braucht man für einen Server mit laufenden Anrufen. Telco Radar ist eine statische Seite, deren Rückweg der Revert des Code-Commits und ein von Hand gestarteter `geraete.yml`-Lauf ist, der die Seite neu baut; `site/` selbst fasst dabei niemand an (CLAUDE.md Harte Regeln 1 und 3). Und ein nächtlicher Prüflauf in der Cloud prüft Code, den seit dem letzten Push niemand geändert hat. Jedes dieser Teile müsste gepflegt werden und würde rot werden, ohne dass jemand reagiert, und genau dieses Muster hat bei Hermes die CI zwei Monate lang wertlos gemacht.

## Was GitHub danach noch tut

GitHub Actions bleibt der Ort für die fachlichen Läufe, die Daten holen, rendern und ausliefern, aber nicht mehr für die Prüfung deines Codes. Das ist keine Kostenfrage. GitHub schreibt: „GitHub Actions usage is free for self-hosted runners and for public repositories that use standard GitHub-hosted runners“ ([Quelle](https://docs.github.com/en/billing/concepts/product-billing/github-actions), abgerufen am 2. Oktober 2026). Für das öffentliche `telco-radar` kostet `ci.yml` also nichts. Lokal zu prüfen ist trotzdem richtig, weil die Rückmeldung vor dem Push kommt statt 15 bis 20 Minuten danach, weil ci.yml die Suite seriell unter Python 3.11 auf einem Standard-Runner mit 4 vCPU laufen lässt und weil ein roter CI-Lauf auf `main` nichts mehr aufhält, der Code ist dann schon dort. Die privaten Repos `telco-radar-inbox` und `telco-radar-mail` zahlen dagegen Minuten aus dem Freikontingent, und dort läuft ohnehin keine Testsuite.

| Workflow | Heute | Empfehlung | Grund |
| --- | --- | --- | --- |
| `ci.yml` | jeder Push und PR, kein Timeout, keine Concurrency, kein Pfadfilter | auf `workflow_dispatch` stellen, `timeout-minutes: 30`, Python aus `.python-version` | gelegentlich die Suite auf Linux und 3.11 gegenprüfen, nicht bei jedem Push |
| `deploy.yml` | jeder Push auf `main`, ruft nur den Render-Hook | löschen | redeployt eine unveränderte `site/`; die Bots rufen den Hook selbst |
| `radar.yml` | Mi und Fr 11:00 UTC | bleibt, Render-Fehler muss rot werden | fachlich nötig |
| `geraete.yml` | täglich mit Ersatzterminen | bleibt, Render-Fehler muss rot werden | fachlich nötig |
| `deploy-signup.yml` | Pfadfilter `service/signup/**` | bleibt | fachlich nötig |
| `newsletter_stats.yml` | `repository_dispatch` | bleibt | fachlich nötig, lief mangels Versand noch nie |
| `llm-probe.yml` | manuell | bleibt | kostet nichts, wenn niemand ihn startet |

### Ein gescheiterter Render muss rot sein

Der Auftrag v4 hat genau diesen Fall beschrieben: Ein f-String mit Zeilenumbruch in `geraete_zeitreihe.py` ging lokal unter 3.12 durch, scheiterte in Actions unter 3.11, und die Seite blieb tagelang auf „Preise vom 18.9.“ stehen, während nur die Daten committet wurden. Der Render-Schritt in `geraete.yml` ist seitdem ohne `continue-on-error`, aber drei Wege lassen einen Fehler weiter still durch. Erstens fängt `geraete_view.py:2163` jede Ausnahme der Zeitreihen-Aufbereitung und rendert die Seite ohne Hauptgrafik weiter; das steht im Fortschrittsprotokoll als offener Punkt 3 von P0. Zweitens hat `report/html.py` fünf `except Exception`, darunter `:1909`, das fehlende Tarifquellen zu einer leeren Liste macht. Drittens laufen die Render-Hook-Schritte in beiden Workflows mit `continue-on-error: true` (`geraete.yml:316`, `radar.yml:239`), sodass eine Seite, die gebaut, aber nie ausgeliefert wurde, als grüner Lauf erscheint.

Die Regel dafür ist einfach: `render_site` bekommt einen Rückgabewert mit allen Teilen, die nicht gebaut werden konnten, und der Workflow-Schritt endet rot, wenn diese Liste nicht leer ist. Die Seite selbst wird trotzdem ausgeliefert, mit dem sichtbaren Hinweis aus Regel 9, weil ein Tag ohne Gerätegrafik besser ist als ein Tag ohne Seite. Der Render-Hook bleibt bei Netzfehlern von Render grün, aber erst nach drei Versuchen und nur, wenn danach ein `curl` auf die Live-Seite das Tagesdatum findet; sonst ist der Lauf rot. Damit misst Actions, was CLAUDE.md schon verlangt: Den Live-Stand bestätigt nur das ausgelieferte HTML.

### Eine Python-Version

Lokal läuft 3.13, Actions läuft 3.11, und CLAUDE.md Regel 15 versucht den Unterschied mit einem Satz zu überbrücken. Diese Regel hat den f-String vom September nicht verhindert, weil sie nur gelesen und nirgends geprüft wird. Eine Datei `.python-version` mit `3.11` im Repo, `uv` auf dem Mac für die lokale Umgebung und `python-version-file: .python-version` in allen Workflows machen beide Seiten gleich. Zusätzlich setzt `pyproject.toml` `target-version = "py311"` für ruff, das Syntax ab 3.12 dann schon beim Speichern meldet. Ein späterer Sprung auf 3.13 ist eine Zeile in einer Datei und gilt dann überall zugleich.

## Hermetische Tests

Ein Test darf nur rot werden, wenn sich Code geändert hat, und ein grüner Lauf muss auf jedem Rechner und an jedem Tag dasselbe bedeuten. Heute erfüllt die Suite das nicht: Alle 16 Fehlschläge vom 2. Oktober kommen aus dem echten `data/state`, keiner aus einem Code-Fehler. `test_geraete_tco_hauptansicht` erwartet 1.794,76 €, der Bestand ergibt inzwischen 1.714,75 €; `test_tarif_bezug` vergleicht eine Fixture vom 4. September mit einer Betriebsdatei, die neue Felder bekommen hat; `test_wettbewerbsradar` findet im aktuellen Bestand keinen Mismatch mehr und schlägt deshalb an. Jeder dieser Tests prüft am Ende, wie der Bot gestern gecrawlt hat.

### Eingefrorene Schnappschüsse statt echtem Bestand

22 Testdateien öffnen ausdrücklich `WURZEL/"data"/"state"`, heuristisch berühren rund 890 Tests in 48 Dateien den echten Bestand. Sie lesen künftig aus `tests/fixtures/bestand/<datum>/`, einem Ausschnitt, den `scripts/schnappschuss.py` aus einem benannten Bot-Commit zieht. Das Skript nimmt nur, was die Tests brauchen, etwa die Historie der vier Tor-Geräte aus P0 statt der ganzen 28 MB, und schreibt eine `_herkunft.json` mit Commit, Quelldatei, Zeilenfilter, Datum und sha256 je Datei. Ein Schnappschuss wird nie verändert. Ändert sich das Datenformat, entsteht ein neuer Ordner mit neuem Datum, und die Tests ziehen bewusst um. So bleibt sichtbar, ob ein Test wegen des Codes oder wegen neuer Daten anders rechnet.

Durchgesetzt wird das zweifach. Ein Audit-Hook (`sys.addaudithook`) in `tests/conftest.py` lässt jeden Dateizugriff auf Pfade unter `<repo>/data` und `<repo>/site` mit der Meldung „Tests lesen nur Schnappschüsse, siehe tests/fixtures/bestand“ scheitern. Ein Ersatz für `builtins.open` würde nicht reichen: `src/` liest und schreibt an 107 Stellen über `Path.read_text` und `write_text`, dazu kommen `shutil.copytree` in den Tests und `os.open`. Das Audit-Ereignis `open` meldet alle diese Wege; eine Probe mit `Path.write_text`, `read_text`, `open`, `os.open` und `shutil.copy` hat das bestätigt. Ein Audit-Hook lässt sich nicht wieder entfernen, deshalb prüft er nur, solange die Test-Sitzung eine Variable gesetzt hat. Und `pytest-socket` sperrt alle Netzverbindungen außer `127.0.0.1`, was den Test in `test_redaktion_kontinuitaet` sofort rot macht, der heute über die echte `settings.yaml` telekom.de und das CT-Log abfragt und 82 Sekunden braucht. Für Chromium setzt die Browser-Fixture eine Route, die jede Anfrage außer an den lokalen Testserver abbricht. Die Uhr kommt in Tests aus dem Schnappschuss-Datum, was CLAUDE.md Harte Regel 11 erst prüfbar macht.

### Fixtures mit Herkunft

Die Geräte- und Tariffixtures zeigen, wie es richtig geht: echte, gespeicherte Antworten mit URL, Abrufdatum, Status und sha256 in `_herkunft.json`. Von den 65 Gerätedateien sind aber nur 32 belegt. Die 33 übrigen, darunter 8 handgeschriebene Stücke unter 1 KB für medimax, freenet, alditalk und Shopify und die nachgelieferten `…_2026-09-29`-Dateien, werden ersetzt, wo die Quelle ohne Bot-Schutz erreichbar ist, und sonst mit den Tests gelöscht, die nur für sie existieren. CLAUDE.md nennt den Grund schon als Fallstrick: Ein Subagent, der einen Adapter baut, erfindet notfalls seine Fixture. Stufe 0 der Prüfleiter prüft, dass jede Datei unter `tests/fixtures/` einen Herkunftseintrag mit passendem sha256 hat.

### Schnell, langsam, Browser

Es gibt heute weder `conftest.py` noch Marker noch xdist, und jede Browserdatei startet ihr eigenes Chromium. Künftig startet eine Fixture mit `scope="session"` Chromium einmal je Worker, und Tests bekommen davon nur eine frische Seite. Es gibt fünf Marker.

| Marker | Bedeutung | Läuft in |
| --- | --- | --- |
| ohne | reine Logik, unter einer Sekunde | allen Stufen |
| `seite` | rendert HTML aus einem Schnappschuss | betroffen, voll |
| `browser` | braucht Chromium, wird über die Fixture automatisch gesetzt | betroffen, voll |
| `langsam` | über 5 Sekunden nach dem Umbau | nur pre-push |
| `golden` | goldener Lauf, siehe unten | nur pre-push |

Die Leiter liest nach jedem vollen Lauf `--durations` aus und listet Tests über fünf Sekunden ohne Marker `langsam`. Das ist ein Hinweis, keine Sperre, weil Laufzeiten auf dem Mac schwanken.

### Tests, die rausfliegen oder umziehen

Streng gezählt lesen rund 52 Testfunktionen in 32 Dateien Code, Vorlagen oder Doku als Text, dazu dreimal `inspect.getsource`. `test_geraete_jobbudget` liest die Workflows, `test_archiv_dossier` vergleicht `app.js` mit Python. Solche Tests werden rot, wenn jemand umformuliert, und bleiben grün, wenn das Verhalten bricht. Sie werden gelöscht; wo dahinter eine echte Regel steht, wird sie vorher ein import-linter-Vertrag oder ein Test am Verhalten. Stufe 0 meldet danach jeden Test, der `getsource` benutzt oder Dateien unter `src/`, `.github/` oder `docs/` als Text öffnet. Der Größentest `test_claude_md_groesse.py` zieht in Stufe 0 um, weil er ein Werkzeug prüft und kein Verhalten.

287 Testfunktionen in 66 Dateien greifen auf private Namen wie `_auffaellig` oder `_delta` zu. Sie halten genau die Funktionen fest, die beim Zerlegen der Gott-Funktionen verschwinden sollen. Das wird nicht in einem Schritt behoben, sondern beim Umbau des jeweiligen Moduls: Wer `report/geraete_tco_karten.py` zerlegt, stellt dessen Tests auf den öffentlichen Eingang um. Gezählt wird mit der ruff-Regel `PLC2701` (Import privater Namen), die es nur im Preview-Modus gibt und die am 2. Oktober in `tests/` 227 Treffer meldet, in `src/` keinen. Weil sich Preview-Regeln zwischen ruff-Versionen ändern dürfen, steht sie nicht im Regelsatz des Anhangs. `pruefleiter.py` ruft sie in Stufe 0 getrennt auf (`ruff check --preview --select PLC2701 tests`) und vergleicht die Zahl mit `pruef/privat-basis.txt`, die nur sinken darf. Die ruff-Version ist in `requirements-dev.txt` festgelegt, damit sich die Zählung nicht mit einem Update verschiebt.

### Orakel-Tests

`tests/test_seiten_zahlen.py` ist schon heute das wertvollste Stück der Suite: 145 Tests, die Zahlen aus der gerenderten Geräteseite ziehen und gegen eine zweite, unabhängig geschriebene Rechnung halten. Der Auftrag v4 hat ihn zum Orakel der Geräteseite ausgebaut, nachdem die Scheinanstiege von +387 € an allen Einzeltests vorbeigekommen waren. Er liest aber das echte `data/state` und ist deshalb für 8 der 16 roten Tests verantwortlich. Künftig rendert eine Session-Fixture die Seite einmal aus dem Schnappschuss in ein temporäres Verzeichnis, und die Orakel rechnen aus denselben Rohdateien nach. Orakel liegen in `tests/orakel/`, und ein import-linter-Vertrag verbietet dort jeden Import aus `telco_radar` außer dem Aufruf von `render_site`. Sonst rechnet das Orakel mit dem Code, den es prüfen soll. Dasselbe Muster bekommen Promo-Übersicht und Wochenbericht, für jede Zahl, die ein Manager zitieren könnte (CLAUDE.md Regel 10).

### Goldener Lauf statt Evals

Hermes braucht Evals, weil ein Telefongespräch kein festes Ergebnis hat. Bei Telco Radar ist das Ergebnis eine Datei, also lässt es sich als Ganzes prüfen. Der goldene Lauf startet `pipeline.run` vollständig offline: Ein `httpx.MockTransport` spielt aufgezeichnete Antworten der Quellen ab, ein Ersatz für den LLM-Client spielt aufgezeichnete Antworten ab, die nach dem Hash von Stufe, Modell und Prompt abgelegt sind, und die Uhr steht auf dem Aufnahmetag. Am Ende prüft der Test das gerenderte HTML: welche Meldungen auf `index.html` stehen, dass jede einen Link auf ihre Quelle hat, welche Zahlen auf `geraete.html` und der Promo-Seite stehen, und dass ein zweiter Lauf auf demselben Stand „nichts Neues“ meldet.

Ändert ein Auftrag einen Prompt, findet der Ersatz keine Aufzeichnung und scheitert mit „LLM-Antwort für Stufe editor fehlt, neu aufnehmen mit `make golden-aufnehmen`“. Die Aufnahme ist ein echter Lauf gegen DeepSeek, kostet Cent-Beträge und ist bewusst ein Schritt, den nur du auslöst. Eine zweite Variante läuft mit einem LLM-Client, der HTTP 402 meldet, und prüft den Fallback-Digest aus Lauf 101: Die Seite muss rendern und den Ausfall sichtbar nennen (CLAUDE.md Regel 9).

### Mutationsprüfung auf geändertem Code

Mutationsprüfung beantwortet die Frage, die ein Prompt nicht beantworten kann: ob irgendein Test bemerkt, wenn eine Zeile falsch wird. P1 hat ein Beispiel geliefert, einen Mutanten `trocken=True`, der den Mailkanal abschaltet, während alle 41 Tests grün bleiben. `tools/mutation.py` ermittelt aus dem Diff die Funktionen, deren Zeilen sich geändert haben, und lässt `mutmut` nur deren Mutanten laufen. Ob mutmut 3 die Auswahl nach Funktionsnamen so stabil unterstützt, wie seine Doku es beschreibt, klärt eine Probe im Schritt 6 der Umsetzung; scheitert sie, fällt die Mutationsprüfung weg, statt einen halben Ersatz zu bauen. Sie läuft nur in `tools/auftrag.py` nach dem letzten grünen Test, nicht in jedem Push, weil sie Minuten kostet.

## Struktur gegen schlechten Code

Die Zielarchitektur hat vier Schichten mit einer Richtung: `collect` holt, `analyze` bewertet und speichert, eine neue Schicht `laden` liest den Bestand und baut fertige Sichtmodelle, und `report` rechnet daraus HTML. Nur `collect` darf ins Netz, nur `collect`, `analyze` und `laden` dürfen Dateien lesen und schreiben, und `report` bekommt alles als Argument. Das ist keine neue Idee, sondern das, was `pipeline.py` als Ablauf schon beschreibt und der Code an 72 Stellen in `report/` unterläuft.

*Diagramm: Zielarchitektur · vier Schichten, ein Netzweg, eine neue Ladeschicht*

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 432" role="img" aria-label="Nur collect geht ins Netz, report rechnet nur" font-size="13" font-family="Inter, Arial, sans-serif">
<defs><marker id="ar-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#8a8a8a"/></marker></defs>
<text x="24" y="32" font-size="15" font-weight="600" fill="#1a1a1a">Nur collect geht ins Netz, report rechnet nur</text>
<path d="M102 92V126" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ar-arrow)"/>
<path d="M282 92V126" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ar-arrow)"/>
<path d="M180 180H202" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ar-arrow)"/>
<path d="M360 180H382" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ar-arrow)"/>
<path d="M540 180H562" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ar-arrow)"/>
<path d="M102 232V270" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ar-arrow)"/>
<path d="M282 232V270" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ar-arrow)"/>
<path d="M462 272V234" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ar-arrow)"/>
<path d="M642 232V270" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ar-arrow)"/>
<rect x="24" y="56" width="156" height="36" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1" stroke-dasharray="4 3"/>
<text x="102" y="78" text-anchor="middle" font-size="11.5" fill="#666666">Quellen im Netz</text>
<rect x="204" y="56" width="156" height="36" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1" stroke-dasharray="4 3"/>
<text x="282" y="78" text-anchor="middle" font-size="11.5" fill="#666666">DeepSeek-API</text>
<rect x="24" y="128" width="156" height="104" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="36" y="152" font-weight="600" fill="#1a1a1a">collect</text>
<text x="36" y="174" font-size="11.5" fill="#1a1a1a">Quellen abrufen</text>
<text x="36" y="192" font-size="11.5" fill="#1a1a1a">nur über collect.http</text>
<text x="36" y="210" font-size="11.5" fill="#1a1a1a">robots.txt, Visit-time</text>
<rect x="204" y="128" width="156" height="104" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="216" y="152" font-weight="600" fill="#1a1a1a">analyze</text>
<text x="216" y="174" font-size="11.5" fill="#1a1a1a">Delta, LLM-Bewertung</text>
<text x="216" y="192" font-size="11.5" fill="#1a1a1a">Promo, TCO, Geräte</text>
<text x="216" y="210" font-size="11.5" fill="#1a1a1a">schreibt die Stores</text>
<rect x="384" y="128" width="156" height="104" rx="8" fill="#e60000" fill-opacity="0.12" stroke="#e60000" stroke-width="2"/>
<text x="396" y="152" font-weight="600" fill="#1a1a1a">laden (neu)</text>
<text x="396" y="174" font-size="11.5" fill="#1a1a1a">liest den Bestand</text>
<text x="396" y="192" font-size="11.5" fill="#1a1a1a">baut Sichtmodelle</text>
<text x="396" y="210" font-size="11.5" fill="#1a1a1a">je Seite eines</text>
<rect x="564" y="128" width="156" height="104" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="576" y="152" font-weight="600" fill="#1a1a1a">report</text>
<text x="576" y="174" font-size="11.5" fill="#1a1a1a">Sichtmodell zu HTML</text>
<text x="576" y="192" font-size="11.5" fill="#1a1a1a">kein open, kein Netz</text>
<text x="576" y="210" font-size="11.5" fill="#1a1a1a">Uhr als Argument</text>
<rect x="24" y="272" width="516" height="40" rx="8" fill="#f1f1f1" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="282" y="296" text-anchor="middle" fill="#1a1a1a">data/state · Bestand, vom Bot committet</text>
<rect x="564" y="272" width="156" height="40" rx="8" fill="#f1f1f1" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="642" y="296" text-anchor="middle" fill="#1a1a1a">site/ · HTML</text>
<rect x="24" y="336" width="696" height="40" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="372" y="360" text-anchor="middle" fill="#1a1a1a">Wurzelmodelle: models, tco_model, geraete_model, tarif_model</text>
<text x="24" y="404" font-size="11.5" fill="#666666">Pfeile zeigen den Datenfluss; Importe laufen nur entgegen, von report zu laden zu analyze zu collect, alle auf die Wurzelmodelle.</text>
</svg>
```

Neu ist nur die Schicht `laden`; sie nimmt die 17 Importe aus analyze und die 72 Datei- und Netzaufrufe auf, die heute in `report/` stehen.

### Was die Messung zeigt

Die Importkanten zwischen den Ordnern verlaufen überwiegend richtig. Es gibt nur drei echte Verstöße gegen die Richtung: `collect/ct_log.py:301` und `:303` importieren `analyze.llm`, `analyze/diff_curator.py:29` importiert `report.differentiation`. Das eigentliche Problem liegt eine Ebene tiefer. `report` liest den Zustand selbst: vier Importe aus `collect` (`html.py:1883` und `:1907`, `geraete_view.py:221`, `lieferzeit_view.py:101`), 17 Importe aus `analyze` (7 davon aus den \*\_store-Modulen), 45 Datei- und Netzaufrufe allein in `html.py`, und mit `report/bilder.py:385` und `diff_bilder.py:170` zwei eigene HTTP-Clients, die Bilder aus dem Netz laden, ohne robots.txt und ohne den User-Agent aus `collect.http`. `render_site` importiert 38 interne Module und ist Orchestrator, Datenlader und Renderer zugleich. Deshalb braucht ein Test, der eine Zahl auf der Geräteseite prüfen will, heute das ganze `data/state`.

### Verträge statt Sätze

import-linter macht die Schichtung prüfbar, ruff mit `banned-api` den einen Netzweg, weil import-linter `urllib.request` nicht von `urllib.parse` trennen kann. Beides steht im Anhang; inhaltlich sind es fünf Regeln.

| Vertrag | Regel | Heute verletzt durch |
| --- | --- | --- |
| Schichten | `report` → `laden` → `analyze` → `collect`, nie umgekehrt; Wurzelmodelle (`models`, `tco_model`, `geraete_model`, `tarif_model`) darunter | `ct_log.py:301/303`, `diff_curator.py:29` |
| Report rechnet nur | `report` importiert weder `collect` noch die Store-Module in `analyze` noch `httpx`, `urllib`, `requests` | 27 Importkanten: 7 direkte (`bilder.py:385`, `diff_bilder.py:170`, Stores, `collect`) und 20 über Konstanten aus `analyze` und über Wurzelmodule, Liste unten |
| Ein Netzweg | Abrufe von Quellen nur über `collect.http` (robots.txt, User-Agent, Visit-time); `httpx` und `urllib.request` sonst nur in den benannten API-Clients `analyze/llm.py`, `newsletter/transport.py` und `versand.py` | `analyze/category_sweep.py:74`, `collect/ct_log.py:256`, `collect/newsroom.py`, `promo_bilder.py:359`, `report/bilder.py:385`, `report/diff_bilder.py:170` |
| Unabhängige Adapter | die Geräteadapter unter `collect/geraete/` importieren einander nicht und nicht das Paket-`__init__` | Zyklus aus Paket und 6 Adaptern |
| Orakel unabhängig | `tests/orakel` importiert aus `telco_radar` nur `report.html.render_site` | neu |

Verstöße, die heute bestehen, kommen als `ignore_imports` mit Datei und Ziel in die Konfiguration. Die Liste darf nur schrumpfen; Stufe 0 vergleicht ihre Länge mit dem letzten Commit. Wo ruff, mypy und import-linter etwas nicht fassen, prüft ein kleines AST-Skript in Stufe 0: kein `open`, kein `Path.read_text` und kein `write_text` in `report/`, und kein `datetime.now`, `date.today` oder `time.time` außerhalb von `pipeline.py`, `geraete_pipeline.py` und `collect/http.py`.

Beim Vertrag „Report rechnet nur“ reichen die sieben offensichtlichen Ausnahmen nicht. Gegen den Klon geprüft, meldet `lint-imports` danach noch 13 Wege; grimp zählt 20 weitere direkte Kanten aus `report` heraus, die über andere Module einen verbotenen Baustein erreichen. Erst mit allen 27 Kanten in `ignore_imports` ist der Vertrag gehalten. Die 20 Kanten fallen in vier Gruppen, und drei davon verschwinden ohne die neue Schicht `laden`.

| Gruppe | Kanten | Weg zum Verbotenen | Wie sie verschwindet | Wann |
| --- | --- | --- | --- | --- |
| Konstanten aus `analyze`, die das LLM mitziehen | `html` → `category_sweep`, `promo_ranker`, `promo_editor`, `highlight_topics`, `ctm`; `promo` und `wettbewerb` → `promo_ranker`; `thema` → `highlight_topics` (8) | `report` braucht nur `MECHANICS`, `THEMES`, `DIGEST_MARKER`, `MIND_TREFFER` und zwei Suchfunktionen; die Module importieren `analyze.llm` und damit `httpx` | Konstanten und reine Suchfunktionen in ein Modul ohne LLM-Import, etwa `analyze/begriffe.py`; es steht dann in `report-rechnet-nur` nicht mehr im Weg | Schritt 3, ein kleiner Umbau-Auftrag |
| Wurzelmodule, die `collect` importieren | `html` und `geraete_bewegung` → `geraete_config`; `geraete_view` → `tarif_bezug` (3) | `geraete_config.py:248` → `collect.geraete.autoerkennung`, `tarif_bezug.py:65` → `collect.tarif_crawler` | ein Vertrag „Wurzelmodule importieren keine Schicht“ (Anhang), heute von genau diesen zwei Kanten gebrochen; die zwei Funktionen ziehen nach unten oder die Aufrufe nach `collect` | Schritt 10 |
| `promo_bilder` im Wurzelordner | `html` → `promo_bilder` (1) | `promo_bilder.py:69` importiert `httpx` und `report.bilder` | Bildabruf gehört nach `collect`; `report` bekommt nur den Pfad der abgelegten Datei | Schritt 9, mit `bilder.py` |
| Zustand aus Stores und `collect` | `geraete_bereinigung`, `geraete_pruefung`, `geraete_vergleich` → `geraete_store`; `geraete_view` → `geraete_lifecycle`, `collect.geraete.strukturdaten`; `geraete_zeitreihe` → `tco_store`; `promo` → `promo_store`; `lieferzeit_view` → `collect.lieferzeit` (8) | drei davon holen nur `STATUS_AKTIV` und `STATUS_VERMUTLICH`, `promo` nur `_same_offer` | Status-Konstanten nach `geraete_model`, der Rest mit dem Lader | Status in Schritt 3, Rest in Schritt 9 |

Die 27 Ausnahmen stehen im Anhang als befristete Liste mit dem Schritt, in dem jede verschwindet. Stufe 0 erlaubt nur, dass die Liste kürzer wird, und `make stand` zeigt ihre Länge je Woche; Schritt 9 ist erst fertig, wenn sie leer ist.

Drei Befunde aus der Messung gehören nicht zur Schichtung, aber zur selben Arbeit. `analyze/llm.py:139–158` hält fünf veränderliche Modulvariablen (`_FALLBACKS`, `_VERBRAUCH`, `_PREISE`, `_BUDGET_USD`, `_DEAD_MODELS`), und `reset_model_health()` existiert nur, damit Tests sich nicht gegenseitig beeinflussen. Mit xdist laufen mehrere Tests nacheinander im selben Prozess, sodass ein vergessener Reset einen Test von der Reihenfolge abhängig macht. Die Variablen werden ein Objekt `LlmSitzung`, das `run` anlegt und weiterreicht, im Umbau von Schritt 10. In `collect/newsroom.py:117` steht seit dem 23. September ein Backspace-Zeichen am Ende des Musters `_JUNK_CONTAINS`. Geprüft im Klon passt das Muster deshalb auf keinen echten Titel mehr, weder auf „Sitemap“ noch auf „FAQ“, und der Filter für kurze Nicht-Artikel-Links auf Newsroom-Seiten ist wirkungslos. ruff meldet das als `PLE2510`, dazu viermal `PLE2515` für Zero-Width-Spaces. Das ist ein Fehler und wird in Schritt 3 vor dem Einfrieren der Basis behoben, mit einem Test, der einen Sitemap-Link verwirft. Bei den Farben ist die Arbeit erst zur Hälfte getan: P2-D1 hat die Anbieterfarben in `report/anbieter_farben.py` zusammengeführt (`farbe_fuer`, `:211`), aber Vodafone-Rot `#e60000` steht noch in 9 Dateien unter `src/`, `style.css` hat 59 Hex-Literale, und `CATEGORY_COLORS` (`html.py:61`) und `TIER_COLOR` (`promo.py:51`) sind eigene Paletten. Stufe 0 erlaubt Hex-Farben künftig nur in `anbieter_farben.py` und im `:root`-Block von `style.css`; der Bestand kommt in eine Basis, die nur sinken darf, und schrumpft mit dem Umbau der Seiten in Schritt 9.

Der Beleg für die Netzregel ist `analyze/category_sweep.py:74`: Die Brave-Suche ruft `urllib.request.urlopen` direkt auf, fängt jeden Fehler mit `except Exception` und gibt `[]` zurück. Damit verstößt eine Zeile gegen drei Regeln aus CLAUDE.md: robots.txt und User-Agent gelten nur in `collect.http`, Scheitern ist kein leeres Ergebnis, und ein Ausfall muss auf der Seite sichtbar sein.

### Die zwei Gott-Funktionen zerlegen

`pipeline.py:517 run` hat 986 Zeilen, Komplexität 150, 21 der 79 `except Exception` und 28 der 94 Uhraufrufe. `report/html.py:1176 render_site` hat 966 Zeilen und Komplexität 160. Beide werden nach der Mikado-Methode zerlegt: Ein Agent versucht, einen Schritt herauszulösen, und stößt er auf eine fehlende Voraussetzung, setzt er zurück, notiert die Voraussetzung und erledigt sie zuerst. Jeder Schritt ist ein eigener Commit, nach dem die volle Leiter grün ist und der goldene Lauf dasselbe HTML erzeugt wie vorher. Der goldene Lauf ist hier das Sicherheitsnetz, das die Einzeltests nicht bieten, weil viele von ihnen auf private Funktionen zielen, die beim Zerlegen verschwinden.

Für `run` ergibt sich die Zerlegung aus den Phasen, die das Berichts-JSON schon in `run.phases` misst: Sammeln, Nur Neues, Ereignisse bündeln, Vorsortieren, Bewerten & Schreiben, Einordnen für uns, Wettbewerber-Analyse, Bilder. Jede Phase wird eine Funktion mit einem typisierten Eingang und Ausgang, und `run` wird eine Liste dieser Aufrufe mit einem Zeitbudget je Phase. Für `render_site` ergibt sich die Zerlegung aus den Seiten: Ein Lader in `laden/` baut je Seite ein Sichtmodell (`IndexSicht`, `GeraeteSicht`, `PromoSicht` und so weiter), und `report` bekommt eine Funktion je Seite, die nur ein Sichtmodell und eine Jinja-Umgebung kennt. Erst dabei werden die 17 Importe aus analyze in `report` zu Importen in `laden`.

### IDs, Uhr, Fehler

**IDs entstehen nie aus Titeltext.** `analyze/promo_store.py:161` bildet die ID aus Marke und normalisierter Überschrift. Im Bestand stehen deshalb 7 Angebote zugleich als aktiv und als ausgelaufen, etwa lidl connect „SMART-Tarife mit 5G und Flatrate“ gegen „SMART Tarife mit 5G und Flatrate“; das Fuzzy-Netz `_find_existing_id` (`:187`) fängt das nicht zuverlässig. `models.py:88` nimmt den Titel als Rückfall, wenn eine Meldung keine URL hat. Beides wird der erste Durchstich-Auftrag im neuen Ablauf (Beispiel im Anhang): Promo-ID aus Marke und normalisierter Zielseite, eine Lesemigration, die alte IDs auf neue abbildet, und ein Test aus den 7 echten Paaren. Der Schlüssel ist nicht trivial: Von den 105 aktiven Angeboten teilen sich in 15 von 76 Gruppen mehrere Angebote dieselbe Marke und Zielseite, und auch mit dem Feld \`mechanic\` bleiben 11 Doppelungen, weil es bei 52 Angeboten leer ist. Der Entwurf muss deshalb vor dem Bauen entscheiden, welches zweite Merkmal stabil ist, etwa ein Anker oder eine Produkt-ID auf der Seite; die Messung dazu ist der erste Schritt des Auftrags. Der Anker-Slug in `report/html.py:190` bleibt, weil er nur ein Seitenanker ist.

**Die Uhr wird übergeben.** 94 Aufrufe lesen die Zeit selbst, 7 davon in `analyze` und `report` als Ausweichwert der Form `heute or date.today()`, und `versand.py:99` ruft `datetime.now()` ohne Zeitzone auf. Künftig lesen nur die zwei Einstiegspunkte `pipeline.run` und `geraete_pipeline.run_geraete_stage` die Uhr, einmal, als `datetime` mit `UTC`, und reichen `jetzt` weiter. Die ruff-Regeln `DTZ` verbieten Zeitangaben ohne Zeitzone, das AST-Skript verbietet Uhraufrufe außerhalb der Einstiegspunkte. Damit wird CLAUDE.md Regel 11 („Tests hängen nie vom heutigen Datum ab“) vom Satz zur Prüfung.

**Kein `except Exception` mit Leerwert.** 79 Stellen fangen alles, 86 Handler geben nur `pass`, `continue` oder einen leeren Wert zurück. Jede Stelle bekommt beim Umbau ihres Moduls eine von zwei Formen: eine benannte Ausnahme, die bis zur Seite durchgereicht wird, oder ein benannter Ausfallzustand wie `Ausfall(stufe="tarifquellen", grund=…)`, den die Seite sichtbar anzeigt. ruff prüft das mit `BLE001`, `S110` und `S112`; die heutigen 79 `noqa` kommen in die Basis und dürfen nur sinken. Ausgenommen bleibt der Versand am Ende von `run`, weil eine nicht verschickte Mail keinen veröffentlichten Bericht kosten darf, aber auch er schreibt seinen Ausfall ins Berichts-JSON.

### Große Dateien und Zyklen

44 Dateien haben mehr als 400 Zeilen, die größten sind `report/geraete_zeitreihe.py` mit 2.330, `report/geraete_view.py` mit 2.310 und `report/html.py` mit 2.141. Sie kommen mit ihrer heutigen Zeilenzahl auf `pruef/riesendateien.txt`. Eine Datei auf der Liste darf wachsen, solange sie bei ihrer gelisteten Zahl bleibt; eine neue Datei über 400 Zeilen ist rot. Sinkt eine Datei, schreibt die Leiter die neue Zahl fest. Die Grenze allein ergibt keinen guten Schnitt, deshalb fragt der Prüfer bei jedem neuen Modul, was ein Aufrufer wissen muss, um es zu benutzen.

Von den drei Importzyklen wird der der Geräteadapter zuerst aufgelöst. `collect/geraete/__init__.py` hat 1.422 Zeilen, hält die Registry `ADAPTER` als veränderlichen Modulzustand (`:168`) und wird von allen sechs Adaptern importiert, die wiederum von ihm importiert werden. Die gemeinsamen Teile ziehen nach `collect/geraete/basis.py`, die Registry wird eine Liste in `collect/geraete/register.py`, die die Adapter importiert, ohne von ihnen importiert zu werden. Bei dieser Gelegenheit wird `_preis` einmal geschrieben statt viermal (`vodafone:307`, `o2:121`, `congstar:471`, `telekom:548`). Der Zyklus aus `geraete_view`, `geraete_verlauf`, `geraete_zeitreihe` und `geraete_bewegung` löst sich mit dem Lader, der Zyklus `html` ↔ `thema` mit der Zerlegung von `render_site`.

## Kommentare und Docstrings

Telco Radar übernimmt das Kommentarverbot von Hermes nicht wörtlich, sondern in einer für Python angepassten Form: keine `#`-Kommentare im Code außer Werkzeuganweisungen, Docstrings nur an öffentlichen Eingängen, kein Datum und kein Name in irgendeinem Kommentar oder Docstring.

Die Messung zeigt, warum das nötig ist. In `src/` sind 17,4 % der Zeilen Kommentare und 25,0 % Docstrings; zusammen ist das fast so viel wie der Code selbst (rund 45 %). Darin stehen 770 Datumsangaben, 59-mal „Antonio“ und 48 Verweise auf „CLAUDE.md §“, die laut `CLAUDE.md:9` auf eine Fassung zeigen, die nur noch in der Git-Historie liegt. In `report/geraete_zeitreihe.py:1199–1212` erklären 14 Kommentarzeilen eine Bedingung aus drei Zeilen und verweisen am Ende auf den Test, der die Regel tatsächlich festhält. Das ist ein Änderungsprotokoll, kein Wissen über den Code, und jeder Agent liest es bei jedem Dateizugriff mit.

Null Kommentare wie bei Hermes passen hier aus zwei Gründen nicht, die beide mit Python zu tun haben. Erstens sind Docstrings keine Kommentare, sondern Teil des Programms: `help()`, IDEs und Claude Code zeigen sie beim Aufruf einer Funktion an, ohne die Datei zu öffnen. Ein Satz an `render_site` oder `entry_id` spart einem Agenten das Lesen von 900 Zeilen. Zweitens braucht Python Werkzeugkommentare, die es in TypeScript nicht in dieser Form gibt: `# noqa`, `# type: ignore[code]` und `# pragma: no cover`. Sie bleiben erlaubt, aber nur mit Fehlercode und nur, solange die eingefrorene Basis sie zählt.

| Art | Regel | Prüfung |
| --- | --- | --- |
| `#`-Kommentar | verboten | AST-Skript in Stufe 0, Bestand eingefroren |
| Werkzeugkommentar | nur `noqa: CODE`, `type: ignore[code]`, `pragma: no cover` | ruff `PGH003`, `PGH004` |
| Docstring an öffentlicher Funktion, Klasse, Modul | erlaubt, ein bis drei Sätze, was und wofür, nicht wie | ruff `D` nur für öffentliche Namen |
| Docstring an privater Funktion | verboten | AST-Skript |
| Datum, Name, Phasenkürzel, „CLAUDE.md §“ | verboten in Kommentar und Docstring | AST-Skript mit Mustern |
| Kommentare in YAML und Shell | erlaubt, aber ohne Datum und Name | AST-Skript liest Workflows mit |

Was heute in Kommentaren steht, zieht an einen von vier Orten. Eine Regel, warum etwas so sein muss, wird ein Test, dessen Name die Regel ausspricht; für das Beispiel aus `geraete_zeitreihe.py` existiert er schon. Eine Eigenheit eines Anbieters wird eine benannte Konstante, etwa `TELEKOM_ANTWORTET_MIT_202`, plus ein Fallstrick in der kurzen CLAUDE.md des Ordners. Die Geschichte einer Entscheidung gehört in die Commit-Nachricht. Und ein offener Befund gehört nach `outputs/`, nie in den Code. Die Workflows sind ein Sonderfall: `geraete.yml` hat über 200 Kommentarzeilen, und die wichtigen davon (Visit-time, warum der Render nach dem Commit steht) sind Betriebswissen. Sie ziehen in `docs/betrieb.md`, der Rest wird gelöscht.

Der Abbau läuft wie bei Hermes in zwei getrennten Schritten. Zuerst geht ein Agent je Ordner die Kommentare durch und trägt Wissenswertes an einen der vier Orte, ohne Code zu ändern. Danach löscht `tools/kommentare_loeschen.py` alle `#`-Kommentare und privaten Docstrings mit `libcst`, das Formatierung erhält, und vergleicht je Datei `ast.dump` vor und nach dem Löschen; nur bei gleichem Syntaxbaum schreibt es. Bevor das Skript läuft, müssen die Tests weg sein, die Code als Text lesen, sonst werden sie rot, ohne dass sich Verhalten geändert hat.

## Agenten-Ablauf lokal

Ein Auftrag läuft künftig als JSON-Datei durch `tools/auftrag.py`, ein Python-Skript, das Agenten als eigene `claude -p`-Prozesse startet, ihre Ergebnisse über Exit-Codes prüft und am Ende einen Commit auf `main` zusammenführt oder mit einer Entscheidungsnotiz aufhört. Das ersetzt die Dynamic Workflows aus dem Geräteauftrag v4. Deren Aufbau (Verstehen, Bauen, Prüfen, Nachbessern, Sichttor) bleibt, aber das Urteil „grün“ fällt nicht mehr der Lead im Gespräch, sondern das Skript anhand der Prüfleiter. Das Fortschrittsprotokoll hat gezeigt, warum: Bauer meldeten „2254 Tests grün“ und alle Behauptungen waren formal wahr, während die Seite falsche Zahlen zeigte, und ein Prüfagent hat mit `git checkout --` ungesicherte Arbeit vernichtet.

*Diagramm: Ablauf einer Aufgabe · acht Schritte lokal, drei Rückwege, fünf Ausgänge*

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 668" role="img" aria-label="Nur ein grüner Exit-Code bringt einen Auftrag auf main" font-size="13" font-family="Inter, Arial, sans-serif">
<defs><marker id="ab-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#8a8a8a"/></marker></defs>
<text x="24" y="32" font-size="15" font-weight="600" fill="#1a1a1a">Nur ein grüner Exit-Code bringt einen Auftrag auf main</text>
<path d="M294 112V130" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<path d="M294 188V206" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<path d="M294 264V282" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<path d="M294 340V358" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<path d="M294 416V434" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<path d="M294 492V510" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<path d="M294 568V586" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<path d="M168 312H140" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<path d="M168 388H140" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<path d="M168 464H140V236H166" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<text x="132" y="230" text-anchor="end" font-size="11.5" fill="#666666">zurück</text>
<text x="132" y="306" text-anchor="end" font-size="11.5" fill="#666666">Leiter rot</text>
<text x="132" y="382" text-anchor="end" font-size="11.5" fill="#666666">Befund bestätigt</text>
<text x="132" y="458" text-anchor="end" font-size="11.5" fill="#666666">Mutant überlebt</text>
<rect x="168" y="56" width="252" height="56" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="184" y="80" font-weight="600" fill="#1a1a1a">Auftrags-JSON</text>
<text x="184" y="98" font-size="11.5" fill="#666666">Bereich, Seite, Datenquelle, Art</text>
<rect x="168" y="132" width="252" height="56" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="184" y="156" font-weight="600" fill="#1a1a1a">Roter Abnahmetest</text>
<text x="184" y="174" font-size="11.5" fill="#666666">Testagent, Fehler wie erwartet</text>
<rect x="168" y="208" width="252" height="56" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="184" y="232" font-weight="600" fill="#1a1a1a">Bauen im Worktree</text>
<text x="184" y="250" font-size="11.5" fill="#666666">Fall für Fall, eigene Rolle</text>
<rect x="168" y="284" width="252" height="56" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="184" y="308" font-weight="600" fill="#1a1a1a">Schnelle Leiter</text>
<text x="184" y="326" font-size="11.5" fill="#666666">Stufen 0 bis 4, Exit-Code</text>
<rect x="168" y="360" width="252" height="56" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="184" y="384" font-weight="600" fill="#1a1a1a">Prüfer-Agent</text>
<text x="184" y="402" font-size="11.5" fill="#666666">Opus, frischer Kontext</text>
<rect x="168" y="436" width="252" height="56" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="184" y="460" font-weight="600" fill="#1a1a1a">mutmut</text>
<text x="184" y="478" font-size="11.5" fill="#666666">nur geänderte Funktionen</text>
<rect x="168" y="512" width="252" height="56" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1.25"/>
<text x="184" y="536" font-weight="600" fill="#1a1a1a">Auf main zusammenführen</text>
<text x="184" y="554" font-size="11.5" fill="#666666">rebase, ff-only, Worktree weg</text>
<rect x="168" y="588" width="252" height="56" rx="8" fill="#e60000" fill-opacity="0.12" stroke="#e60000" stroke-width="2"/>
<text x="184" y="612" font-weight="600" fill="#1a1a1a">pre-push und Push</text>
<text x="184" y="630" font-size="11.5" fill="#1a1a1a">volle Leiter, dann origin/main</text>
<rect x="460" y="136" width="276" height="48" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1" stroke-dasharray="4 3"/>
<path d="M420 160H458" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<text x="476" y="156" font-weight="600" fill="#1a1a1a">Fehler passt nicht</text>
<text x="476" y="173" font-size="11.5" fill="#666666">zurück an den Testagenten</text>
<rect x="460" y="212" width="276" height="48" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1" stroke-dasharray="4 3"/>
<path d="M420 236H458" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<text x="476" y="232" font-weight="600" fill="#1a1a1a">Voraussetzung fehlt</text>
<text x="476" y="249" font-size="11.5" fill="#666666">Umbau-Auftrag zuerst, keine rote Runde</text>
<rect x="460" y="288" width="276" height="48" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1" stroke-dasharray="4 3"/>
<path d="M420 312H458" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<text x="476" y="308" font-weight="600" fill="#1a1a1a">Zweimal rot</text>
<text x="476" y="325" font-size="11.5" fill="#666666">Entscheidungsnotiz, Auftrag endet</text>
<rect x="460" y="364" width="276" height="48" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1" stroke-dasharray="4 3"/>
<path d="M420 388H458" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<text x="476" y="384" font-weight="600" fill="#1a1a1a">Befund ohne rote Reproduktion</text>
<text x="476" y="401" font-size="11.5" fill="#666666">verworfen, steht nur im Bericht</text>
<rect x="460" y="592" width="276" height="48" rx="8" fill="none" stroke="#8a8a8a" stroke-width="1" stroke-dasharray="4 3"/>
<path d="M420 616H458" fill="none" stroke="#8a8a8a" stroke-width="1.25" marker-end="url(#ab-arrow)"/>
<text x="476" y="612" font-weight="600" fill="#1a1a1a">pre-push rot</text>
<text x="476" y="629" font-size="11.5" fill="#666666">nichts verlässt den Mac</text>
</svg>
```

Die teure Arbeit, das Urteil eines Modells, kommt erst, wenn die billigen Prüfungen ohne Modell grün sind. Alle drei Rückwege führen zum selben Bauagenten und zählen gemeinsam gegen seine zwei Runden.

### Das Auftragsformat

Das Format übernimmt die Felder aus Hermes (Ziel, Bereich, erwartete Dateien, Vorbild, Abnahmetest, erwarteter Fehler, Abhängigkeiten, „Was darf nie passieren“) und ergänzt vier Felder, die bei Telco Radar fehlen würden. `seite` nennt die betroffenen HTML-Seiten, weil die Leiter dann die passenden Orakel und Sichtprüfungen auswählt. `datenquelle` nennt die Dateien in `data/state`, deren Schnappschuss der Auftrag braucht, und den Bot-Commit, aus dem er stammt. `art` unterscheidet `umbau` von `verhalten`, weil ein Umbau den goldenen Lauf byte-gleich lassen muss und ein Verhaltensauftrag ihn neu aufnehmen darf. Und `migration` beschreibt, wie bestehende Daten im Bestand weiter gelesen werden, wenn sich ein Schlüssel ändert; ohne dieses Feld wäre der Promo-ID-Fix ein Auftrag, der 330 Einträge verwaist. Das vollständige Beispiel steht im Anhang.

`tools/auftrag.py` prüft das Format vor dem Start: Bereich ist ein Ordner unter `src/telco_radar/`, Abnahmetest existiert nicht oder ist rot, jeder Auftrag, der Daten schreibt oder eine Quelle abruft, hat `wasDarfNiePassieren`, und `art` ist genau eines von beiden. Ein Auftrag, der gegen eine dieser Bedingungen verstößt, startet nicht.

### Rollen und Modelle

| Rolle | Modell | Darf schreiben | Gibt zurück |
| --- | --- | --- | --- |
| Entwurf und Zerschneiden | Opus | `outputs/auftraege/` | Entwurf, Auftrags-JSONs |
| Abnahmetest schreiben | Opus | `tests/` | einen roten Test mit dem erwarteten Fehler |
| Bauen: TCO, Datenmodell, Stores, IDs, Migration | Opus | `src/`, nicht `tests/` | Diff und Commit-Nachricht |
| Bauen: Vorlagen, CSS, Adapter-Selektoren | Sonnet | `src/`, nicht `tests/` | Diff und Commit-Nachricht |
| Prüfen | Opus | nichts im Repo, nur `/tmp/pruefer/` | Befunde mit Reproduktion |
| Suchen, Logs, Testausgaben | Haiku | nichts | höchstens fünf Zeilen |
| Grün oder rot | kein Modell | — | Exit-Code der Leiter |

Modell und Denkaufwand stehen fest in den Agent-Definitionen unter `.claude/agents/` und werden in einer Sitzung nie gewechselt. Die Rolle setzt das Skript als Umgebungsvariable (`TELCO_ROLLE=bau`) und übergibt eine Rollendatei mit `--settings`; ein Agent kann seine Rolle nicht selbst wählen.

Neue Orakel für `tests/orakel/` schreibt der Testagent als Teil des Abnahmetests, nicht der Prüfer. Die Unabhängigkeit bleibt trotzdem erhalten, weil der Testagent den Code des Bauers nicht kennt und der import-linter-Vertrag „Orakel unabhängig“ ihm den Import der Rechnung verbietet. Der Prüfer bleibt so ohne jedes Schreibrecht im Repo, und seine Befunde sind Reproduktionen unter `/tmp/pruefer/`, die das Skript ausführt.

Von den vier heutigen Agenten unter `.claude/agents/` bleiben zwei. `repo-scout` (Haiku) wird die Suchrolle der Tabelle, unverändert. `quellen-pruefer` (Haiku, mit WebFetch) bleibt für neue Quellen neben `scripts/pruefe_quellenvorschlag.py`, außerhalb des Auftragsablaufs. `diff-reviewer` und `seiten-pruefer` gehen im neuen `pruefer` auf: Dessen Schritt 2 ist die eigene Rechnung von fünf Seitenzahlen aus dem `seiten-pruefer`, seine Schritte 1 und 3 sind der Teil des `diff-reviewer`, den kein Werkzeug prüft. Damit entfällt CLAUDE.md Clean Code 10, nach der vor jedem Commit der `diff-reviewer` mit `docs/clean-code-referenz.md` läuft und S1/S2 blockieren. An ihre Stelle treten die Prüfleiter vor jedem Commit und der Prüfer mit Reproduktionspflicht in jedem Auftrag. Der Katalog mit 565 Zeilen ist danach keine Pflichtlektüre mehr: Jeder Eintrag wird eine Regel in ruff, import-linter oder Stufe 0, wo das geht, und der Rest eine Zeile in Schritt 3 der Prüfer-Datei. Was keines von beiden wird, fällt weg.

### Regeln im Auftrag

- **Der Test kommt zuerst und ist rot mit dem erwarteten Fehler.** Der Testagent schreibt den Abnahmetest, das Skript führt ihn aus und vergleicht die Fehlermeldung mit `erwarteterFehler`. Scheitert der Test schon beim Import oder an einem Tippfehler, ist er kein Abnahmetest, und der Testagent bekommt ihn zurück. Erst ein fachlich roter Test wird committet, vor dem Bauen, damit die Reparatur im nächsten Commit nachvollziehbar ist.
- **Nach zwei roten Runden schreibt der Agent eine Entscheidungsnotiz.** Ist die Leiter nach zwei Bau-Runden noch rot, schreibt der Bauagent nach `outputs/auftraege/<id>-notiz.md`, was er versucht und beobachtet hat, und hört auf. Das ist die Regel „anhalten, wenn ein Tor zweimal am selben Punkt scheitert“ aus dem Auftrag v4, jetzt vom Skript gezählt statt vom Lead.
- **Eine fehlende Voraussetzung beendet den Auftrag.** Stößt der Bauer auf eine nötige Änderung außerhalb seines Bereichs, endet er mit diesem Ergebnis und einem Satz, was vorher umgebaut werden muss. Das zählt nicht als rote Runde; daraus wird ein Umbau-Auftrag, der zuerst läuft.
- **Ein Prüferbefund zählt nur mit Reproduktion.** Jeder blockierende Befund kommt mit einem Befehl, meist einem Test in `/tmp/pruefer/`, der auf dem Stand des Bauers an einer fachlichen Erwartung scheitert. Das Skript führt ihn aus; grün heißt verworfen. So entscheidet nie ein schwankendes Modellurteil über Rot.
- **Der Diff bleibt klein.** Höchstens rund 400 Zeilen Produktcode, Richtwert 200, Tests zählen nicht mit. Der Diff bleibt im Bereich des Auftrags; Tests, Vorlagen und Konfiguration dieses Bereichs zählen dazu. Abweichungen von den erwarteten Dateien stehen im Bericht, sperren aber nicht.
- **Worktrees bleiben lokal, und höchstens zwei laufen gleichzeitig.** Jeder Auftrag läuft in `../telco-radar-wt/<id>` auf einem Zweig `auftrag/<id>`. Nach Grün führt das Skript ihn mit `git rebase main` und `git merge --ff-only` zusammen, lässt die Leiter noch einmal auf `main` laufen und löscht Worktree und Zweig. Gepusht wird ein Zweig nie; das verhindert, dass wieder 82 Alt-Branches entstehen. Zwei Aufträge laufen nur parallel, wenn ihre Bereiche sich nicht überschneiden.
- **Jeder Worktree bekommt eine eigene Umgebung.** Ein neuer Worktree hat kein `.venv`, und alle Hooks rufen `.venv/bin/python`. `tools/auftrag.py` ruft deshalb nach `git worktree add` zuerst `make venv` im Worktree auf, bevor der erste Agent startet. Mit dem Paket-Cache von `uv` dauert das Sekunden, und Chromium liegt bei Playwright ohnehin im gemeinsamen Cache des Benutzers. Für Web-Sitzungen von Claude Code, die mit einem frischen Klon beginnen, ruft der SessionStart-Hook dasselbe `make venv` auf, wenn `.venv` fehlt.

### Wenn du selbst mit Claude arbeitest

Nicht jede Änderung braucht einen Auftrag. Eine Änderung, die sich in einem Satz beschreiben lässt, machst du direkt in einer Sitzung auf `main`; dieselben Hooks und dieselbe Leiter gelten, nur ohne Entwurf und ohne getrennte Rollen. Ab zwei betroffenen Bereichen, bei allem, was eine Zahl auf einer Seite ändert, und bei jedem Umbau aus diesem Konzept läuft die Arbeit über `tools/auftrag.py`. Die Grenze ist bewusst weich, weil du allein entscheidest, aber sie steht in CLAUDE.md, damit eine Sitzung sie dir vorschlägt.

## Claude-Hooks und Token-Effizienz

Die Claude-Code-Hooks sind die schnelle Rückmeldung vor den Git-Hooks: Sie rufen dieselben Prüfungen früher auf und sparen Runden, aber die Grenze bleibt die Prüfleiter im pre-push. Heute stehen in `.claude/settings.json` zwei Hooks, und beide werden ersetzt.

| Heute | Problem | Künftig |
| --- | --- | --- |
| PostToolUse ruft `scripts/hook_gezielte_tests.py` | findet für 43 von 116 Modulen keine Tests, prüft keine Vorlagen, CSS oder JS, endet immer mit Exit 0, `test_newsletter_seite` sprengt das 120-s-Timeout | PostToolUse ruft `ruff check` und `ruff format --check` nur auf die geänderte Datei, unter einer Sekunde, Exit 2 bei Befund |
| Stop ruft `bash /Users/antonio/Developer/jarvis-ext/scripts/stop-hook-commit.sh` | Mac-Pfad außerhalb des Repos, läuft in Web-Sitzungen ins Leere, erzeugt `wip(auto)`-Commits, für die CLAUDE.md Regel 17 eine Sonderregel braucht | Stop ruft `scripts/pruefleiter.py --schnell` (Stufen 0 bis 4, Stufe 4 mit 45-s-Kappe) und endet mit Exit 2, solange etwas rot ist; Claude arbeitet dann weiter, statt die Sitzung zu beenden |
| keiner | ein Bauagent kann bestehende Tests umschreiben, bis sie zu seinem Code passen | PreToolUse auf Edit und Write prüft die Rolle: `bau` darf unter `tests/` nur neue Dateien anlegen, `test` darf `src/` nicht ändern, `pruefen` schreibt nichts im Repo |
| keiner | Hooks wirken nur, wenn `core.hooksPath` gesetzt ist | SessionStart setzt `core.hooksPath .githooks` und prüft die Python-Version gegen `.python-version` |

Die deny-Liste bekommt zu den heutigen Einträgen (`site/`, `data/state/`, `git add -A`, `git add .`, Force-Push) die Sperren, die die Prüfungen schützen: `--no-verify`, `git commit -n`, `git config core.hooksPath`, Schreiben auf `pruef/**`, `.githooks/**`, `.claude/settings.json`, `.importlinter`, `[tool.*]` in `pyproject.toml` und `tests/fixtures/bestand/**`. Wer eine Prüfung lockern will, bist du, in einer bewussten Handänderung. Die Datei steht im Anhang. Die deny-Liste ist dabei eine Bremse und keine Grenze, weil sie Befehlstexte vergleicht und ein Umweg wie \`git -c core.hooksPath=…\` auf keiner Liste steht; was einen solchen Umweg sichtbar macht, ist der Prüfstempel aus dem Abschnitt zur Prüfleiter. Der Stop-Hook hat eine Schutzgrenze, weil ein dauerhaft roter Zustand sonst eine Endlosschleife ergibt: Nach dem dritten Exit 2 in Folge lässt er die Sitzung enden und schreibt den Befund nach `outputs/`.

`push-live.sh` und `Push Live.command` werden gelöscht. Das Skript macht `git add -- . ':!data/state' ':!data/reports' ':!site'`, committet und pusht auf `main`, ohne einen einzigen Test, und widerspricht damit CLAUDE.md Regel 5. Der Skill `commit-sicher` bleibt, ruft aber `make pruefen` statt `pytest -q` und pusht auf `main`, weil Arbeitszweige nicht mehr gepusht werden.

### Token-Effizienz

Die teuerste Gewohnheit in diesem Repo ist nicht, was Agenten schreiben, sondern was sie immer wieder lesen. Der Geräteauftrag v4 hat das schon bemerkt (CLAUDE.md von 3.840 auf 179 Zeilen gekürzt); die nächsten Hebel sind gemessen.

| Stelle | Gemessen | Maßnahme |
| --- | --- | --- |
| Startkontext | CLAUDE.md 180 Zeilen, 16,8 KB, 35 Fallstricke, davon 15 zu Geräteradar und LLM | Wurzel-CLAUDE.md ≤ 100 Zeilen; Fallstricke in `src/telco_radar/collect/geraete/CLAUDE.md`, `analyze/CLAUDE.md` und `report/CLAUDE.md`, die Claude Code nur lädt, wenn dort gearbeitet wird |
| Riesendateien | drei Dateien über 2.000 Zeilen, `html.py` mit 2.141 | PreToolUse auf Read blockiert das vollständige Lesen von Dateien über 800 Zeilen ohne `offset` und verlangt erst `grep` |
| Kommentare | 42 % der Zeilen in `src/` sind Kommentare oder Docstrings | der Kommentarabbau senkt die Lesekosten jeder Datei fast auf die Hälfte |
| Testausgabe | volle Suite mit 3.981 Tests, `pytest -q` gibt bei Fehlern Tracebacks voller Lokalvariablen | Leiter gibt höchstens 60 Zeilen aus, `--tb=line` im Agentenmodus, volles Log als Datei |
| Wissen in Kommentaren | 48 Verweise auf eine alte CLAUDE.md, die ein Agent mit `git show` nachschlagen soll | Fehlermeldung der Prüfung nennt die Regel und die Stelle in CLAUDE.md; Wissen kommt erst beim Verstoß |
| Alte Berichte im Suchbereich | `outputs/` mit über 60 Sitzungsberichten, `fortschritt-geraeteseite.md` mit 54 KB | erledigte Berichte nach `docs/archiv/`, Lesen dort per deny-Liste gesperrt; Fortschritt je Vorhaben eine Datei, die ersetzt statt verlängert wird |

Dazu kommen vier Regeln für Sitzungen. Nach jedem Auftrag kommt `/clear`, und der Zustand liegt in `outputs/`, nicht im Gespräch. Unteragenten gibt es nur für laute Arbeit wie Suche, Logs von Actions-Läufen und Screenshots, mit höchstens fünf Zeilen Rückgabe. Modell und Denkaufwand werden in einer Sitzung nicht gewechselt, weil das den Zwischenspeicher bricht. Und `tools/auftrag.py` schreibt je Auftrag die Token- und Zeitzahlen aus den `claude -p`-Ausgaben nach `outputs/auftraege/kosten.csv`, damit sich zeigt, ob der Umbau die Kosten je Auftrag senkt.

## Aufräumen zuerst

Bevor die erste Prüfung eingeführt wird, verschwindet, was Agenten nur verwirrt und kein Werkzeug je prüfen soll. Das dauert einen halben Tag und ändert kein Verhalten.

| Was | Gemessen | Maßnahme |
| --- | --- | --- |
| `_to_delete/` | 7 MB: Bundles, Zip, Patches, `git-index.lock.stale` | löschen, Eintrag in `.gitignore` |
| `claude/` im Wurzelordner | eingecheckter Arbeitsordner | Inhalt prüfen, Brauchbares nach `docs/archiv/`, Rest löschen |
| Remote-Branches | 82: `main`, 49 × `claude/*`, 32 × `openclaw/*` | Liste mit `git branch -r --merged origin/main` erzeugen, gemergte löschen; nicht gemergte als Liste mit letztem Commit an dich, du entscheidest einzeln |
| `deploy.yml` | redeployt bei jedem Push eine unveränderte Seite | löschen |
| `ci.yml` | volle Suite bei jedem Push ohne Timeout | auf manuell stellen |
| `push-live.sh`, `Push Live.command` | pusht ohne Tests | löschen |
| Stop-Hook | Mac-Pfad außerhalb des Repos | aus `.claude/settings.json` entfernen, Regel 17 aus CLAUDE.md streichen |
| `docs/STRATEG*_GERAETE*.md`, ältere `outputs/` | vier Strategiedokumente zur Geräteseite, über 60 Sitzungsberichte | erledigte nach `docs/archiv/` |
| `mail_repo/` | Kopie der Dateien für `telco-radar-mail` | bleibt, bis die Newsletter-Kette läuft, dann ins private Repo |

Die Git-Historie hat 145,6 MB bei 930 Commits, davon 68 % `data/` und 14 % `site/`. Das ist die Folge davon, dass die Bots Bestand und Seite committen, und es ist kein Problem, das eine Umschreibung der Historie rechtfertigt: `git filter-repo` würde alle Commit-Hashes ändern, die in `outputs/` und im Fortschrittsprotokoll als Belege stehen, und jeden Klon ungültig machen, auch den von Render. Ein Klon dauert auf dem Mac Sekunden. Für Web-Sitzungen von Claude Code, die das Repo jedes Mal neu klonen, reicht ein flacher Klon. Erst wenn das Repo über ein GB wächst oder GitHub warnt, lohnt sich die Frage, ob `site/` überhaupt im Repo liegen muss oder Render aus einem Build-Artefakt deployen kann.

## Umsetzungsreihenfolge

Zuerst kommt der Grundstand aus Prüfleiter und hermetischen Tests, dann der Ablauf für Agenten, dann die Umbauten. Bis Schritt 5 erfüllt ist, entstehen keine neuen Funktionen; Fehlerbehebungen am Live-Betrieb gehen weiter, aber direkt auf `main` mit der Leiter, soweit sie schon steht. Der Grund ist derselbe wie bei Hermes: Agenten kopieren den Bestand als Vorlage, und solange Tests am Bot-Bestand hängen, lernt jede Sitzung, dass Rot normal ist. Es läuft immer nur ein Umbauschritt, und jeder Schritt endet spätestens beim Doppelten seiner Schätzung mit deiner Entscheidung, ob er kleiner geschnitten, verschoben oder gestrichen wird. Die Fertig-Kriterien prüft `make stand`, ein kleines Skript, das je Schritt „erfüllt“ oder „offen, weil …“ ausgibt; ein erfüllter Schritt wird eine Stufe-0-Prüfung und kann nicht still zurückfallen.

1. **Aufräumen** (ein halber Tag). `_to_delete/`, `push-live.sh`, `Push Live.command`, Stop-Hook und gemergte Alt-Branches weg, Liste der nicht gemergten an dich. Fertig, wenn `git branch -r` nur noch `main` und die von dir behaltenen Zweige zeigt und `_to_delete` nicht mehr existiert.
2. **Workflows und Python-Version** (ein Tag). `.python-version` mit 3.11, `uv` lokal, `deploy.yml` gelöscht, `ci.yml` auf manuell; `render_site` meldet nicht gebaute Teile, der Workflow-Schritt wird dann rot; der Render-Hook prüft das Tagesdatum im Live-HTML. Die Probe läuft ohne `main` und ohne Live-Seite: In einem lokalen Wegwerf-Worktree macht ein Test die Zeitreihen-Aufbereitung kaputt, und der Render-Schritt aus `geraete.yml` läuft dort mit `render_site` in einen temporären Ordner. Fertig, wenn er dort mit Exit-Code ungleich 0 endet, die gebaute Seite den Ausfall sichtbar nennt und der Worktree danach gelöscht ist; der erste echte `geraete.yml`-Lauf nach dem Merge zeigt das Tagesdatum im Live-HTML.
3. **Formatierung, Werkzeuge und Basislinien** (zwei Tage). Zuerst ein einmaliger Lauf `ruff format` über `src/`, `tests/` und `scripts/` als eigener Commit, der nur Formatierung ändert; am 2. Oktober würde ruff 119 von 123 Dateien in `src/` und 244 in `tests/` und `scripts/` umformatieren. Dessen Hash kommt in `.git-blame-ignore-revs`, und `make einrichten` setzt `git config blame.ignoreRevsFile .git-blame-ignore-revs`, damit `git blame` weiter die fachlichen Änderungen zeigt. Ohne diesen Lauf würde der PostToolUse-Hook mit `ruff format --check` jede berührte Datei rot melden. Im selben Schritt werden das Backspace in `newsroom.py:117` und die vier Zero-Width-Spaces behoben und die Status-Konstanten sowie die Begriffe aus `analyze` verschoben, die heute 11 der 27 Ausnahmen von „Report rechnet nur“ erzeugen. Danach `pyproject.toml` mit ruff und mypy, `.importlinter` mit den Verträgen und der befristeten Ausnahmeliste, `pruef/mypy-basis.txt`, `pruef/riesendateien.txt`, `scripts/pruefleiter.py` mit Stufen 0 bis 3, `make pruefen`. Fertig, wenn `ruff format --check` auf dem ganzen Repo grün ist und vier Rot-Proben scheitern: ein neuer unbenutzter Import, ein neuer mypy-Fehler in einer Datei der Basis, ein Import von `collect` in `report`, eine neue Datei mit 401 Zeilen.
4. **Hermetische Tests** (vier bis sechs Tage, der größte Brocken des Grundstands). `conftest.py` mit Schnappschüssen, Audit-Hook gegen `data/` und `site/`, `pytest-socket`, Chromium je Sitzung, Rendern je Variante einmal, Marker und xdist; die 22 Dateien mit `WURZEL/"data"` umgestellt; Fixtures ohne Herkunft ersetzt oder gelöscht; die rund 52 Tests, die Code als Text lesen, gelöscht. Fertig, wenn die volle Suite auf dem M4 Pro zehnmal hintereinander grün ist, die Zeit gemessen ist (gerechnet 2,3 Minuten, Grenze 4) und ein Bot-Commit auf `data/state` keinen einzigen Test ändert.
5. **Hooks und CLAUDE.md** (ein Tag). Git-Hooks, Claude-Hooks, deny-Liste, Prüfstempel, Stufen 4 und 5 der Leiter, CLAUDE.md auf höchstens 100 Zeilen mit Ordner-CLAUDE.md für `collect/geraete`, `analyze` und `report`. Fertig, wenn ein Commit mit rotem Test lokal nicht pushbar ist, eine Claude-Sitzung `--no-verify` nicht ausführen kann, ein mit `git -c core.hooksPath=/dev/null` gepushter Testcommit in der nächsten Sitzung als ungeprüft gemeldet wird und ein Stop mit rotem Lint die Sitzung weiterlaufen lässt.
6. **Auftragsablauf** (vier bis sechs Tage). `tools/auftrag.py` mit `make venv` je Worktree, Rollendateien, Prüfer-Agent mit Reproduktionspflicht, goldener Lauf mit Aufnahme, Probe mit mutmut auf geänderten Funktionen; `diff-reviewer` und `seiten-pruefer` gelöscht, CLAUDE.md Clean Code 10 gestrichen. Fertig, wenn ein kleiner echter Auftrag vom roten Test bis zum Merge auf `main` durchgelaufen ist, jedes „grün“ aus einem vom Skript gelesenen Exit-Code stammt und die mutmut-Probe ein Ergebnis hat: läuft mit gemessener Zeit, oder läuft nicht, mit Grund.
7. **Kommentarabbau** (zwei bis drei Tage). Wissen je Ordner an die vier Orte, dann `tools/kommentare_loeschen.py` mit AST-Vergleich. Fertig, wenn die Kommentarprüfung ohne eingefrorenen Treffer grün ist und für jede Datei ein unveränderter Syntaxbaum gemeldet wurde.
8. **Durchstich Promo-IDs** (zwei bis drei Tage, erster echter Auftrag mit Migration). Fertig, wenn die 7 belegten Paare je einen Eintrag ergeben, alle 330 Einträge des Schnappschusses unter neuer ID lesbar sind, `models.py:88` ohne Titelrückfall auskommt und der Promo-Orakel-Test grün ist. Was am Ablauf dabei nicht funktioniert, wird vor Schritt 9 geändert.
9. **Lader und `render_site` zerlegen** (zwei bis drei Wochen, Seite für Seite, Geräteseite zuerst). Fertig je Seite, wenn ihr Sichtmodell aus `laden/` kommt, `report` für diese Seite keinen Store, kein `collect` und keine Datei mehr berührt und der goldene Lauf dasselbe HTML erzeugt. Insgesamt fertig, wenn die Ausnahmeliste von „Report rechnet nur“ bis auf die drei Wurzelmodul-Kanten leer ist, `promo_bilder.py` in `collect` liegt, die Hex-Basis für Farben bei null steht und `render_site` unter 100 Zeilen hat.
10. **`run` zerlegen, Uhr, Fehler, Netzweg** (ein bis zwei Wochen). Fertig, wenn `run` eine Liste von Phasen unter 100 Zeilen ist, Uhraufrufe nur noch in den zwei Einstiegspunkten stehen, `category_sweep.py` über `collect.http` geht, `llm.py` keinen veränderlichen Modulzustand mehr hat, der Vertrag „Wurzelmodule importieren keine Schicht“ ohne Ausnahme grün ist und die Basis für `BLE001` um die Hälfte gesunken ist.

Einen Monat nach Schritt 6 zählst du, wie viele Prüferbefunde sich per Reproduktion bestätigt haben. Ist es weniger als die Hälfte, wird der Prüfer-Auftrag an den verworfenen Befunden nachgeschärft. Der Grundstand (Schritte 1 bis 5) dauert nach diesen Schätzungen knapp zwei Wochen, mit Schritt 6 bis 8 etwa vier.

### Verhältnis zum Geräteauftrag v4

Laut Git-Historie liegen P0 und P1 seit dem 22. September live, P2-Abschluss (`a380f88`), P3-E1 bis E3 und der P4-Bewegungsblock (`71ad321`) auf `main`. Die Neugestaltung der Geräteseite aus PR #16 wurde am 29. September mit PR #17 zurückgenommen. Offen sind das Tor P3 (eine aktuelle Aktion gegen die Anbieterseite belegt), das Tor P4 (Testversand), das an der nie gelaufenen Newsletter-Kette hängt, und die Neugestaltung.

Vorgezogen wird nur ein Teil, und zwar in Schritt 2: der offene Punkt 3 aus P0, dass ein gescheiterter Zeitreihen-Aufbau die Seite ohne Hauptgrafik und ohne sichtbaren Hinweis ausliefert. Das ist ein Fehler im Live-Betrieb, kein Feature, und er gehört zur selben Änderung wie der rote Render. Ebenfalls im Grundstand landet die Umstellung von `test_seiten_zahlen.py` auf Schnappschüsse, weil sie 8 der 16 roten Tests behebt; der Inhalt der 145 Orakel bleibt.

Die Neugestaltung der Geräteseite schließt sich an Schritt 9 an und ist dessen erste Seite. Wer `geraete_view.py` (2.310 Zeilen), `geraete_zeitreihe.py` (2.330) und `geraete_tco_karten.py` (1.983) ohnehin in Lader und Sichtmodell zerlegt, baut die neue Darstellung gleich auf dem Sichtmodell, statt sie ein zweites Mal in die Riesendateien einzuweben. Das Rückgängigmachen von PR #16 spricht dafür: Ein Umbau dieser Größe ohne goldenen Lauf und ohne hermetische Orakel ließ sich nur als Ganzes zurücknehmen. Tor P3 und Tor P4 sind keine Code-Arbeit im engeren Sinn und können jederzeit als Einzelaufträge laufen, sobald Schritt 6 steht.

## Pre-Mortem

Angenommen, es ist Februar 2027 und das System hat nichts gebracht: Die Suite ist wieder langsam, die Gott-Funktionen stehen noch, und die Seite liegt auf einem Konto, das niemand mehr pflegt. Die sechs Ursachen unten haben jeweils einen Anlass im heutigen Repo oder in diesem Konzept.

| Ursache | Anzeichen heute | Gegenmaßnahme | Woran du es merkst |
| --- | --- | --- | --- |
| **Die Leiter wird langsam und umgangen.** Ein Solo-Entwickler, der vor jedem Push acht Minuten wartet, pusht irgendwann direkt von GitHub im Browser oder setzt `--no-verify`. | Die Testzahl ist von rund 3.300 Mitte September auf 3.981 gestiegen; die Laufzeiten von damals (447 bis 509 s laut \`outputs/\`) stammen von einem anderen Rechner und lassen sich mit den 1.058 s vom 2. Oktober nicht vergleichen. | pre-commit hat ein Budget von 30 s, pre-push von 4 min; die Leiter schreibt ihre Laufzeit nach `.pruefleiter/zeiten.csv` und warnt ab dem Budget. Langsame Tests wandern in `langsam`, nicht in einen Skip. | `make stand` zeigt die Laufzeit der letzten zehn Läufe. |
| **Basislinien wachsen still.** Eine Basis, die jeder Agent bei Bedarf hochsetzen kann, ist keine Prüfung. | 79 `noqa` im Code, jedes eine stille Ausnahme. | Basisdateien stehen in der deny-Liste; Stufe 0 vergleicht ihre Summen mit dem letzten Commit und ist rot, wenn eine steigt. Senken schreibt die Leiter selbst. | Die Summen aller Basislinien stehen in `make stand` und sinken. |
| **Der Umbau frisst Monate.** Schritt 9 trifft die drei größten Dateien, und währenddessen wartet die Abteilung auf die Geräteseite. | PR #16 musste als Ganzes zurückgenommen werden. | Seite für Seite, Geräteseite zuerst und zusammen mit ihrer Neugestaltung; jeder Mikado-Schritt ist ein eigener grüner Commit auf `main`; Zeitgrenze das Doppelte der Schätzung. | Die Zeile von `render_site` in `pruef/riesendateien.txt` sinkt jede Woche. |
| **Das Praktikum endet vor der Übergabe.** Ein gut geprüftes Repo auf einem privaten Konto ist trotzdem weg. | Repo, Render und LLM-Guthaben hängen an dir; Legal und Compliance haben nicht freigegeben. | Die Übergabe ist keine Code-Arbeit und läuft parallel. Der Grundstand hilft ihr: Eine Leiter, die mit `make einrichten` und `make pruefen` auf einem fremden Rechner läuft, ist übergebbar, ein Repo mit Mac-Pfaden im Stop-Hook nicht. | Ein zweiter Rechner bekommt die Suite grün, ohne dass du hilfst. |
| **Der Bot macht `main` still rot.** Bot-Commits lösen keine Prüfung aus, und ein Datenformat ändert sich. | `test_tarif_bezug` scheiterte an zwei neuen Feldern in `tarife.jsonl`. | Schnappschüsse entkoppeln die Tests vom Bot; zusätzlich prüft der goldene Lauf jede neue Aufnahme gegen die aktuelle Datenform, und `geraete.yml` validiert das Schema seines Bestands vor dem Commit. | Ein Formatwechsel erscheint als roter Bot-Lauf, nicht als roter Test eine Woche später. |
| **Agenten weichen auf die nächste Lücke aus.** Was nicht geprüft wird, wird zur Stelle, an der Agenten Probleme ablegen. | `except Exception` mit `[]` ist heute genau so eine Stelle; die Regel dafür steht seit August in CLAUDE.md. | Jede Korrektur, die du zweimal gibst, wird Regel, Test oder Vertrag. Der Prüfer meldet mit Regel-ID, `tools/auftrag.py` zählt Wiederholungen je ID. | Die Liste der häufigsten Befunde in `outputs/auftraege/kosten.csv` ändert sich über die Wochen. |

Was offen bleibt: Ob mutmut 3 mit der Auswahl nach Funktionen schnell genug ist, zeigt erst die Probe in Schritt 6. Und die Zielzeit von 2,3 Minuten ist eine Rechnung aus den seriell gemessenen 976 Sekunden ohne Netztest, 10 Workern und 70 % Wirkungsgrad; die zusätzliche Ersparnis durch einmaliges Rendern ist geschätzt. Gemessen wird beides in Schritt 4.

## Bewusst nicht übernommen aus Hermes

| Baustein bei Hermes | Warum nicht bei Telco Radar |
| --- | --- |
| GitHub als Grenze mit Branch-Schutz, Ruleset und PR-Pflicht | ein einziger Mensch und Bots, die nur generierte Dateien schreiben; die Grenze steht im pre-push |
| Organisation sundartha, Team-Plan, Maschinenkonto | Repo ist öffentlich und gehört einer Person; die deny-Liste trennt Agentenrechte von deinen |
| CODEOWNERS und Freigabeprüfung für Prüfdateien | niemand außer dir könnte freigeben; die Basisdateien stehen stattdessen in der deny-Liste |
| Merge-Queue und Sperre je Bereich | höchstens zwei lokale Worktrees mit getrennten Bereichen, Zusammenführen per `--ff-only` |
| Zwei Server, Umschalter, Blue-Green | statische Seite; der Rückweg ist der Revert des Code-Commits und ein neuer `geraete.yml`-Lauf, der die Seite baut, ohne dass jemand `site/` anfasst |
| Nächtliches Aufräumen, wöchentliche Auswertung, Kartenlauf als Actions | kein Code ändert sich, während du schläfst; ein Lauf, der nichts findet, wird ignoriert |
| Evals für Gesprächsverhalten | das Ergebnis ist eine Datei; der goldene Lauf prüft sie als Ganzes |
| TypeScript-Umstieg | Python hat schon 82,4 % vollständige Annotationen; mypy mit Basis reicht, ein Sprachwechsel brächte nichts |
| Null Kommentare ohne Ausnahme | Docstrings an öffentlichen Eingängen und Werkzeugkommentare sind in Python Teil des Programms |
| Bedrohungskatalog, ZAP-Scan, Penetrationstest | keine Anmeldung, kein Geld, keine Nutzerdaten außer der Newsletter-Adresse im separaten Dienst |
| Squawk und versionierte Migrationen | keine Datenbank; Formatwechsel im Bestand laufen als Lesemigration im Auftragsfeld `migration` |
| Steuerwerkzeug und Funktionskarte | `render_site` in einen Wegwerfordner und `pruefe_portal.py` decken das schon ab |
| Belegdatei, die nur das Skript schreiben darf | Exit-Codes und der Commit selbst sind der Beleg; ein Einzelner muss sich nicht gegen einen zweiten Menschen absichern |
| Testschutz „nur ergänzen“ als CI-Prüfung mit Label | bleibt als Rollenregel im PreToolUse-Hook; eine Label-Freigabe ohne zweite Person ist Zeremonie |

## Entscheidungen für Antonio

| Entscheidung | Empfehlung | Warum |
| --- | --- | --- |
| Neue Funktionen bis Schritt 5 stoppen, also rund zwei Wochen? | ja, nur Fehlerbehebungen im Live-Betrieb | sonst entsteht jede neue Zeile noch unter den alten Regeln und muss danach umgebaut werden |
| Python 3.11 überall oder 3.13 überall? | 3.11 jetzt, Sprung auf 3.13 als eigener Schritt nach Schritt 5 | Actions läuft heute mit 3.11; ein Wechsel während des Umbaus mischt zwei Fehlerquellen |
| Was mit den 32 `openclaw/*`-Zweigen passiert | du gehst die Liste der nicht gemergten einmal durch, alles andere wird gelöscht | der Name deutet auf ein anderes Projekt im selben Repo, das kann nur du beurteilen |
| Neugestaltung der Geräteseite erst mit Schritt 9 | ja, als erste Seite des Lader-Umbaus | PR #16 zeigt, dass sie in den Riesendateien nicht prüfbar war |
| Wann die Übergabe von Repo, Render und LLM-Guthaben geklärt wird | jetzt, parallel und mit festem Termin vor dem Praktikumsende | sie ist die einzige Ursache im Pre-Mortem, die kein Code verhindert |

## Anhang: Bausteine

Das sind Skizzen für die Schritte 3 bis 6, auf Telco Radar zugeschnitten und ohne Kommentare. Jeder Baustein gilt erst als aktiv, wenn eine Rot-Probe gezeigt hat, dass er anschlägt: ein absichtlicher Verstoß, der danach wieder entfernt wird.

### `pyproject.toml`, Werkzeugteil

```toml
[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src", "tests", "scripts"]
extend-exclude = ["site", "data", "_to_delete", "mail_repo"]

[tool.ruff.lint]
select = ["E", "F", "W", "B", "SIM", "C90", "I", "UP", "DTZ", "BLE", "S110", "S112", "PGH", "TID251", "D1"]
ignore = ["D105", "D107"]

[tool.ruff.lint.mccabe]
max-complexity = 12

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"httpx".msg = "Quellen nur ueber telco_radar.collect.http abrufen, siehe CLAUDE.md, Abschnitt Schichten"
"requests".msg = "Quellen nur ueber telco_radar.collect.http abrufen, siehe CLAUDE.md, Abschnitt Schichten"
"urllib.request".msg = "Quellen nur ueber telco_radar.collect.http abrufen, siehe CLAUDE.md, Abschnitt Schichten"

[tool.ruff.lint.per-file-ignores]
"src/telco_radar/collect/http.py" = ["TID251"]
"src/telco_radar/analyze/llm.py" = ["TID251"]
"src/telco_radar/newsletter/transport.py" = ["TID251"]
"src/telco_radar/versand.py" = ["TID251"]
"tests/**" = ["D1", "TID251"]
"scripts/**" = ["D1"]

[tool.mypy]
python_version = "3.11"
mypy_path = "src"
packages = ["telco_radar"]
check_untyped_defs = true
warn_unused_ignores = true
warn_redundant_casts = true
no_implicit_optional = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
addopts = "-q --strict-markers --disable-socket --allow-hosts=127.0.0.1 -n auto --dist worksteal -m 'not netz'"
markers = [
  "seite: rendert HTML aus einem Schnappschuss",
  "browser: braucht Chromium",
  "langsam: laenger als 5 s, nur im pre-push",
  "golden: goldener Lauf, nur im pre-push",
  "netz: echter Abruf, laeuft nie automatisch",
]
```

Die Option `--dist worksteal` statt `loadgroup` ist Absicht, weil sonst eine einzelne Datei wie `test_newsletter_seite` mit 211 s die Laufzeit bestimmt (Abschnitt Zielzeit). Die Netzregel steht bewusst bei ruff und nicht bei import-linter: import-linter behandelt Standardbibliothek und Fremdpakete nur als ganze Pakete und könnte `urllib.request` nicht von `urllib.parse` trennen. ruff hat keine eingebaute Basislinie; `pruefleiter.py` vergleicht deshalb die JSON-Ausgabe je Datei und Regel mit `pruef/ruff-basis.json`, genau wie bei mypy. Die Entwicklungsabhängigkeiten (`ruff`, `mypy`, `import-linter`, `pytest-xdist`, `pytest-socket`, `mutmut`, `libcst`) stehen in `requirements-dev.txt` mit festen Versionen.

### import-linter-Verträge (`.importlinter`)

```ini
[importlinter]
root_packages =
    telco_radar
    tests
include_external_packages = True

[importlinter:contract:schichten]
name = Schichten collect, analyze, laden, report
type = layers
layers =
    telco_radar.report
    (telco_radar.laden)
    telco_radar.analyze
    telco_radar.collect
ignore_imports =
    telco_radar.collect.ct_log -> telco_radar.analyze.llm
    telco_radar.analyze.diff_curator -> telco_radar.report.differentiation

[importlinter:contract:wurzel-unten]
name = Wurzelmodule importieren keine Schicht
type = forbidden
source_modules =
    telco_radar.models
    telco_radar.tco_model
    telco_radar.geraete_model
    telco_radar.tarif_model
    telco_radar.geraete_config
    telco_radar.tarif_bezug
forbidden_modules =
    telco_radar.collect
    telco_radar.analyze
    telco_radar.report
ignore_imports =
    telco_radar.geraete_config -> telco_radar.collect.geraete.autoerkennung
    telco_radar.tarif_bezug -> telco_radar.collect.tarif_crawler

[importlinter:contract:report-rechnet-nur]
name = Report laedt nichts und ruft kein Netz
type = forbidden
source_modules =
    telco_radar.report
forbidden_modules =
    telco_radar.collect
    telco_radar.analyze.promo_store
    telco_radar.analyze.tco_store
    telco_radar.analyze.geraete_store
    telco_radar.analyze.diff_curator
    httpx
    requests
ignore_imports =
    telco_radar.report.html -> telco_radar.analyze.category_sweep
    telco_radar.report.html -> telco_radar.analyze.promo_ranker
    telco_radar.report.html -> telco_radar.analyze.promo_editor
    telco_radar.report.html -> telco_radar.analyze.highlight_topics
    telco_radar.report.html -> telco_radar.analyze.ctm
    telco_radar.report.promo -> telco_radar.analyze.promo_ranker
    telco_radar.report.wettbewerb -> telco_radar.analyze.promo_ranker
    telco_radar.report.thema -> telco_radar.analyze.highlight_topics
    telco_radar.report.geraete_bereinigung -> telco_radar.analyze.geraete_store
    telco_radar.report.geraete_pruefung -> telco_radar.analyze.geraete_store
    telco_radar.report.geraete_vergleich -> telco_radar.analyze.geraete_store
    telco_radar.report.html -> telco_radar.geraete_config
    telco_radar.report.geraete_bewegung -> telco_radar.geraete_config
    telco_radar.report.geraete_view -> telco_radar.tarif_bezug
    telco_radar.report.html -> telco_radar.promo_bilder
    telco_radar.report.bilder -> httpx
    telco_radar.report.diff_bilder -> httpx
    telco_radar.report.html -> telco_radar.collect.lieferzeit
    telco_radar.report.html -> telco_radar.collect.tarif_crawler
    telco_radar.report.html -> telco_radar.analyze.diff_curator
    telco_radar.report.lieferzeit_view -> telco_radar.collect.lieferzeit
    telco_radar.report.geraete_view -> telco_radar.analyze.tco_store
    telco_radar.report.geraete_view -> telco_radar.analyze.geraete_store
    telco_radar.report.geraete_view -> telco_radar.analyze.geraete_lifecycle
    telco_radar.report.geraete_view -> telco_radar.collect.geraete.strukturdaten
    telco_radar.report.geraete_zeitreihe -> telco_radar.analyze.tco_store
    telco_radar.report.promo -> telco_radar.analyze.promo_store

[importlinter:contract:adapter-unabhaengig]
name = Geraeteadapter kennen einander nicht
type = independence
modules =
    telco_radar.collect.geraete.vodafone
    telco_radar.collect.geraete.o2
    telco_radar.collect.geraete.telekom
    telco_radar.collect.geraete.congstar
    telco_radar.collect.geraete.einsundeins
    telco_radar.collect.geraete.saturn

[importlinter:contract:orakel]
name = Orakel rechnen ohne den Code, den sie pruefen
type = forbidden
source_modules =
    tests.orakel
forbidden_modules =
    telco_radar.tco_model
    telco_radar.geraete_model
    telco_radar.analyze
    telco_radar.collect
allow_indirect_imports = True
```

Die Ausnahmeliste von `report-rechnet-nur` ist vollständig und gegen den Klon geprüft: Mit genau diesen 27 Kanten meldet `lint-imports` den Vertrag als gehalten, mit den ersten sieben allein bleiben 13 Verstöße. Die Reihenfolge entspricht dem Plan im Abschnitt „Verträge statt Sätze“: Die ersten elf Zeilen fallen in Schritt 3 weg, die drei Wurzelmodul-Kanten in Schritt 10, der Rest in Schritt 9. `wurzel-unten` ist heute von genau zwei Kanten gebrochen, die hier als Ausnahme stehen. Stufe 0 vergleicht die Länge aller `ignore_imports` mit dem letzten Commit. Der Vertrag „Kein Zyklus im Adapterpaket“ ergibt sich aus `adapter-unabhaengig` zusammen mit der Regel, dass `collect/geraete/__init__.py` nach dem Umbau keine Adapter mehr importiert; bis dahin steht dieser Import ebenfalls in den Ausnahmen.

### Git-Hooks (`.githooks/`) und `Makefile`

```sh
#!/bin/sh
exec .venv/bin/python scripts/pruefleiter.py --schnell --nur-vorgemerkt
```

```sh
#!/bin/sh
git fetch --quiet origin main || exit 1
if ! git merge-base --is-ancestor origin/main HEAD; then
  echo "pre-push: origin/main ist neuer, erst git pull --rebase origin main"
  exit 1
fi
exec .venv/bin/python scripts/pruefleiter.py --voll
```

```make
einrichten: venv
	git config core.hooksPath .githooks
	git config blame.ignoreRevsFile .git-blame-ignore-revs

venv:
	uv venv --python-preference only-managed --python $$(cat .python-version)
	uv pip install -r requirements.txt -r requirements-dev.txt
	.venv/bin/playwright install chromium

pruefen:
	.venv/bin/python scripts/pruefleiter.py --voll

schnell:
	.venv/bin/python scripts/pruefleiter.py --schnell

stand:
	.venv/bin/python scripts/stand.py

golden-aufnehmen:
	.venv/bin/python scripts/golden_aufnehmen.py
```

Die erste Datei ist `pre-commit`, die zweite `pre-push`. Beide sind absichtlich dünn: Die Logik steht nur in `pruefleiter.py`, damit Hook, Claude-Hook und Auftragsskript nie verschiedene Dinge prüfen.

`make venv` ist getrennt von `make einrichten`, weil `tools/auftrag.py` und der SessionStart-Hook in jedem neuen Worktree und jedem frischen Klon nur die Umgebung brauchen; die Git-Einstellungen gelten ohnehin für alle Worktrees eines Repos.

### `.claude/settings.json`

```json
{
  "permissions": {
    "allow": [
      "Bash(make pruefen)", "Bash(make schnell)", "Bash(make stand)",
      "Bash(.venv/bin/python -m pytest*)", "Bash(git status*)", "Bash(git diff*)", "Bash(git log*)",
      "Edit(src/**)", "Edit(tests/**)", "Edit(config/**)", "Edit(outputs/**)"
    ],
    "deny": [
      "Read(.env*)", "Read(docs/archiv/**)",
      "Edit(site/**)", "Edit(data/**)",
      "Edit(pruef/**)", "Edit(.githooks/**)",
      "Edit(.claude/settings.json)", "Edit(.claude/hooks/**)", "Edit(.importlinter)", "Edit(pyproject.toml)",
      "Edit(tests/fixtures/bestand/**)",
      "Bash(git add -A*)", "Bash(git add .*)", "Bash(git push --force*)", "Bash(git push -f*)",
      "Bash(*--no-verify*)", "Bash(git commit -n*)", "Bash(git config core.hooksPath*)",
      "Bash(git checkout -- *)", "Bash(git reset --hard*)", "Bash(rm -rf*)"
    ]
  },
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sitzung.py", "timeout": 30}]}],
    "PreToolUse": [
      {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/rolle.py", "timeout": 10}]},
      {"matcher": "Read", "hooks": [{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/grosse_datei.py", "timeout": 10}]}
    ],
    "PostToolUse": [{"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/nach_edit.py", "timeout": 20}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.venv/bin/python \"$CLAUDE_PROJECT_DIR\"/scripts/pruefleiter.py --schnell --hook", "timeout": 300}]}]
  }
}
```

`sitzung.py` setzt `core.hooksPath`, prüft die Python-Version und schreibt eine Zeile mit dem Stand von `make stand`. `rolle.py` liest `TELCO_ROLLE` und den Zielpfad aus stdin und endet mit Exit 2 und einer Begründung, wenn die Rolle dort nicht schreiben darf; ohne gesetzte Rolle, also in deinen eigenen Sitzungen, lässt er alles durch, was die deny-Liste erlaubt. `nach_edit.py` ruft `ruff check` und `ruff format --check` auf die eine Datei und endet bei Befund mit Exit 2. `grosse_datei.py` blockiert ein Read ohne `limit` auf Dateien über 800 Zeilen. `git checkout --` und `git reset --hard` stehen in der deny-Liste, weil ein Prüfagent damit am 24. September ungesicherte Arbeit vernichtet hat.

### Prüfer-Agent (`.claude/agents/pruefer.md`)

```markdown
---
name: pruefer
description: Prueft einen fertigen Auftrag gegen Auftrags-JSON, CLAUDE.md und die gerenderte Seite. Sucht den Grund, warum er falsch ist.
tools: Read, Grep, Glob, Bash
model: opus
---

Du bekommst einen Auftrag, der angeblich fertig ist, den Diff und den Pfad des Worktrees.
Dein Urteil ist "nicht bestanden", bis du das Gegenteil nicht widerlegen kannst.

Pruefe in dieser Reihenfolge:
1. Erfuellt der Diff das Ziel und jeden Fall aus wasDarfNiePassieren? Schreib je Fall einen Test nach /tmp/pruefer/, der das Verhalten von aussen prueft.
2. Betrifft der Auftrag eine Seite, rendere sie mit render_site in /tmp/pruefer/site aus dem Schnappschuss und rechne mindestens fuenf angezeigte Zahlen ohne Import aus telco_radar nach.
3. Verletzt der Diff eine Regel aus CLAUDE.md, die kein Werkzeug prueft: Fehlwert als 0, unbekannt als neu, Ausfall ohne sichtbaren Hinweis, ID aus Text.
4. Verbirgt das neue Modul etwas, oder muss ein Aufrufer seine Interna kennen?

Nicht melden: Stil, Formatierung, Kommentare, Namen. Das pruefen ruff und die Leiter.

Antworte nur als JSON:
{"befunde": [{"schwere": "blocker|sollte|hinweis", "regel": "CLAUDE.md Clean Code 3", "datei_zeile": "...", "beschreibung": "...", "reproduktion": "python -m pytest /tmp/pruefer/test_x.py::test_y"}],
 "gesucht_ohne_befund": ["die drei Stellen, an denen du am laengsten gesucht hast"]}

Ein blocker ohne reproduktion wird verworfen. Die reproduktion muss auf dem Worktree an einer fachlichen Erwartung scheitern, nicht beim Import.
Du aenderst keine Datei ausserhalb von /tmp/pruefer/ und fuehrst kein git checkout, git reset oder git stash aus.
```

### Beispielauftrag: Promo-ID ohne Titeltext

```json
{
  "id": "T1",
  "art": "verhalten",
  "ziel": "Ein umformuliertes Angebot derselben Marke auf derselben Aktionsseite behaelt seine ID und ist nie zugleich aktiv und ausgelaufen",
  "bereich": "src/telco_radar/analyze/",
  "erwarteteDateien": ["src/telco_radar/analyze/promo_store.py"],
  "vorbild": "src/telco_radar/analyze/clustering.py",
  "seite": ["promo/index.html"],
  "datenquelle": {"dateien": ["data/state/promo_db.json"], "botCommit": "7ee3f59", "schnappschuss": "tests/fixtures/bestand/2026-09-30/"},
  "abnahme": "tests/test_promo_identitaet.py",
  "erwarteterFehler": "lidl connect: erwartet 1 Eintrag, erhalten 2 (aktiv und ausgelaufen)",
  "abhaengigVon": [],
  "migration": "PromoDB liest Eintraege mit alter ID und bildet sie beim Laden auf die neue ID ab; bei zwei alten Eintraegen mit derselben neuen ID gewinnt der juengere last_verified, der aeltere bleibt als Verlauf erhalten",
  "wasDarfNiePassieren": {
    "wiederholung": "ein zweiter Lauf mit denselben Seiten erzeugt keinen neuen Eintrag und aendert keinen Status",
    "gleichzeitig": "zwei Angebote derselben Marke auf derselben Seite bleiben zwei Eintraege",
    "zeitueberschreitung": "eine nicht gelesene Seite altert keinen ihrer Eintraege (CLAUDE.md Clean Code 6)",
    "abbruch": "bricht der Lauf nach dem Lesen und vor dem Speichern ab, ist promo_db.json unveraendert"
  }
}
```

Das Feld `vorbild` zeigt auf `clustering.py`, weil dort die ID schon richtig aus der normalisierten URL entsteht. Der Fall `gleichzeitig` ist der Grund, warum die Zielseite allein als Schlüssel nicht reicht (15 von 76 Gruppen aktiver Angebote teilen sie); welches zweite Merkmal stabil ist, entscheidet der Entwurf vor diesem Auftrag.

`promo_pipeline.py` steht bewusst nicht unter den erwarteten Dateien. Es liegt außerhalb des Bereichs `analyze/`, benutzt nur `PromoDB` und nicht `entry_id` und muss sich deshalb nicht ändern. Braucht der Bauer doch eine Änderung dort, endet der Auftrag mit „Voraussetzung fehlt“.
