# Kommentarwissen 11-pipeline-docstrings

Docstrings aus `src/telco_radar/pipeline.py`, die Paket 32 auf die Docstring-Regel aus `docs/umbau/plan.md` gekürzt hat (private Namen ohne Docstring, öffentliche ein bis drei Sätze). Wortlaut unverändert.

## `geraete_budget`

    Wie viel Zeit die Geraetestufe im Wochenlauf noch bekommt.

    `None` heisst "nicht anfangen". Gerechnet wird gegen die RESTZEIT DES
    JOBS, nicht gegen das eigene Budget - genau daran ist Lauf 31422689829
    gescheitert. Die Reserve gehoert dem Rendern, Committen und Deployen;
    sie ist der Teil, den ein Nutzer zu sehen bekommt.

## `_waehle_anbieter`

    Legt den LLM-Anbieter fest und liefert seinen Namen.

    "auto" behaelt die alte Reihenfolge (Bedrock > OpenAI-kompatibel >
    Anthropic) und nimmt damit, welcher Schluessel gerade da ist. Genau das
    ist das Problem, das llm_provider loest: solange der NVIDIA-Schluessel im
    Repo liegt, gewinnt er, und Anthropic kaeme nie zum Zug.

    Bei einer expliziten Wahl werden die Schluessel der unterlegenen Anbieter
    aus der Prozessumgebung entfernt. Das ist noetig, weil llm.py seinen
    Backend allein aus der Umgebung ableitet - sonst wuerde hier der eine
    Anbieter die Modell-IDs bestimmen, waehrend dort der andere aufgerufen
    wird. Nur die Kopie dieses Prozesses ist betroffen.

## `_modelle_fuer_anbieter`

    Liefert (Analystenmodell, Editormodell) des GEWAEHLTEN Anbieters.

    Als eigene Funktion herausgezogen, weil das Auseinanderlaufen von
    Anbieter und Modell-ID sich nicht selbst meldet: der Endpunkt antwortet
    einfach mit "unbekanntes Modell", die aufrufende Stufe faengt den Fehler
    ab, und der Lauf gilt als erfolgreich. Genau so stand die
    Wettbewerber-Seite zwei Laeufe lang leer da (siehe unten im
    Wettbewerber-Zweig). Jede Stufe holt ihr Modell ab jetzt hier.

## `_mechanik_modell`

    Das Modell der MECHANIK-Stufen (Uebersetzung, Clustering-Pruefung,
    Beleg-Pruefung, Promo-Extraktion/-Score, Kategorie-Sweep, CT-Radar,
    Diff-Kurator).

    Diese Stufen brauchen kein Urteil, nur Fleiss - und ein Denkspur-Modell
    wie deepseek-v4-pro bezahlt je Aufruf ~8-9k Token Nachdenken, egal wie
    klein die Aufgabe ist (18.08.2026, der groesste Kostenposten des Laufs).
    Der Schluessel folgt demselben Muster wie _modelle_fuer_anbieter
    (`<anbieter>_mechanik_model`); fehlt er, laeuft alles wie bisher auf dem
    uebergebenen Modell - ein Anbieter ohne den Eintrag verhaelt sich exakt
    wie vor dieser Aenderung.

## `anker_modelle`

    (Redaktionsanker, Mechanikanker) - oder ("", ""), wenn abgeschaltet.

    Eine Stelle, an der die zwei Namen herkommen: `_registriere_anker` haengt
    sie an die Ketten, und der Analyst bekommt seinen ueber `ausweich=` je
    Aufruf mitgegeben (siehe dort). Zwei Ableseorte waeren zwei Wahrheiten.

## `_registriere_ausweichmodell`

    Das anbietereigene Ausweichmodell `editor -> analyst`, wenn es taugt.

    Es taugt genau dann NICHT, wenn der Claude-Anker aktiv ist: Analyst und
    Redaktion haengen am selben Anbieterkonto, ein HTTP 402 toetet beide
    zugleich, und ein Ausweichmodell auf demselben leeren Konto ist keins.
    Frueher hat `_registriere_anker` diese Zusicherung nachtraeglich
    ueberschrieben - das war die Stelle, an der eine ECHTE Praeferenzkette
    (`bedrock_model_chain`) mit ueberschrieben wurde. Die Entscheidung
    gehoert hierher, wo bekannt ist, dass beide Modelle demselben Anbieter
    gehoeren; `_registriere_anker` sieht nur Namen.

## `_registriere_anker`

    Haengt an das ENDE jeder Modellkette einen Claude-Anker.

    Der Anker greift NUR, wenn das Primaermodell hart gescheitert ist - im
    Normalfall kostet er nichts. Er existiert, weil eine Kette innerhalb
    EINES Anbieters keine leere Kasse ueberlebt: Analyst, Redaktion und
    Mechanik haengen am selben DeepSeek-Konto, und ein HTTP 402 toetet sie
    zugleich.

    **Ans Ende, nicht an den Kopf.** `set_fallback(modell, anker)` ersetzt den
    Nachfolger, den `modell` schon hatte - und das ist bei einer echten
    Praeferenzkette ein stiller Verlust: `bedrock_model_chain` registriert
    "das beste Modell, das dieses Konto wirklich bedient" als
    a -> b -> c, und ein Anker am Kopf wirft b und c weg, ohne dass es
    irgendwo auffiele. Ein Bedrock-403 ("not available for this account") ist
    gerade KEINE leere Kasse, sondern eine Aussage ueber genau ein Modell -
    die Kette ist die Antwort darauf und muss stehen bleiben. Der Anker ist
    das, was NACH ihr kommt.

    Text entsteht in der Redaktion, deshalb endet sie in einem grossen
    Modell; die Mechanik im kleinsten - sie macht die allermeisten Aufrufe.

    In JEDER heutigen Provider-Konfiguration ist `analyst_model ==
    editor_model` ("deepseek-v4-pro", ebenso die beiden openai_*_model), und
    `llm._FALLBACKS` haengt am MODELLNAMEN, nicht an der Rolle des Aufrufers:
    fuer denselben Namen kann es nur EINEN Nachfolger geben, und der gehoert
    der Redaktion (ein ausgefallener Bericht wiegt schwerer). Der Analyst
    bekommt seinen kleineren Anker deshalb NICHT hier, sondern je Aufruf
    ueber `agents.analyze_region(..., ausweich=...)` - siehe `llm._kette`.
    Genau daran hing der Fehler bis zum 27.08.2026: der Analyst, die mit
    Abstand aufrufstaerkste Stufe, waere im Ernstfall auf Sonnet gelandet.

## `_protokolliere_kosten`

    Was der Lauf verbraucht hat - je Modell, im Actions-Log.

    Die Summe allein sagt nichts: teuer wird ein Lauf an EINER Stufe (am
    27.08.2026 waren ~90 % der 1,95 $ der Analyst auf v4-pro), und ohne die
    Zeile je Modell ist nicht zu sehen, an welcher.

## `_redaktion_zweistufig`

    Entscheidet, ob die zweistufige Redaktion laeuft.

    Beides hat seine Groesse: bei 36 bewerteten Meldungen (Lauf #67) schreibt
    EIN Aufruf einen besseren, zusammenhaengenderen Bericht als dreizehn, und
    er kostet ein Zwoelftel. Ab ein paar hundert Meldungen kippt es - dann kann
    ein einzelner Aufruf nicht mehr abwaegen, sondern nur noch aufzaehlen, und
    ein Fehlschlag kostet den ganzen Wochenbericht.

    Deshalb eine Schwelle statt einer Grundsatzentscheidung. "auto" ist der
    Normalfall; "einstufig"/"zweistufig" erzwingen einen Modus, was der
    Abnahme neuer Wellen dient (ein echter Lauf mit erzwungener Zweistufigkeit,
    bevor die Meldungsmenge sie ohnehin ausloest).

## `zu_merkende_meldungen`

    Welche Meldungen als "gesehen" abgelegt werden duerfen.

    Der Seen-Store ist ein Einbahnschild: was hineingeht, gilt als erledigt
    und wird nie wieder gesammelt. Zwei Schutzstufen gab es dafuer schon (die
    komplett ausgefallene Region aus Lauf #64, der einzelne gescheiterte
    Stapel aus Lauf #67); mit dem Ereignis-Clustering kommt eine dritte dazu.

    Ein BELEG wird nie einzeln bewertet - er haengt an seinem Vertreter. Ohne
    diese Umleitung waeren gebuendelte Meldungen der teuerste Fall ueberhaupt:
    der Vertreter kaeme beim naechsten Lauf wieder, seine drei Belege nie, und
    das Protokoll saehe normal aus. Als eigene Funktion herausgezogen, damit
    genau das ein Test halten kann.

## `vorsortierung_budget`

    Wie viel Zeit die Vorsortierung bekommt, oder None fuer "nicht
    anfangen".

    Dieselbe Rechnung wie `geraete_budget()` und `uebersetzung.stufe.budget()`
    und aus demselben Grund: gerechnet wird gegen die RESTZEIT DES JOBS, nicht
    gegen das eigene Budget. Der Unterschied zu jenen beiden ist die
    POSITION - die Vorsortierung steht VOR dem Analysten, also vor der
    laengsten Stufe des Laufs. Ein festes `vorsortierung_frist_sekunden` ist
    deshalb die eigentliche Sicherung; die Restzeit-Rechnung faengt nur den
    Fall ab, dass der Job ohnehin schon knapp ist.

## `vorsortieren`

    Die Vorsortierung so, wie der Lauf sie aufruft - und nur deshalb eine
    eigene Funktion: der Aufrufer sitzt mitten in `run()`, und was dort steht,
    haelt kein Test. Dieselbe Ueberlegung wie bei `zu_merkende_meldungen`.

    Ohne Modell, ohne Meldungen oder mit abgeschaltetem Schalter bleibt die
    Abbildung unveraendert und die Bilanz leer - dann verhaelt sich der Lauf
    exakt wie vor dem 27.08.2026.

    Zwei Sicherungen liegen hier und nicht im Modul, weil nur der Lauf sie
    kennt:

    * **Das Zeitbudget** (`vorsortierung_budget`) - die Stufe steht vor dem
      Analysten, und eine Stufe, die ihre Zeit ueberzieht, kostet nicht ein
      paar Meldungen, sondern den Bericht (Lauf 31422689829).
    * **Das try/except** - eine Stufe, die MELDUNGEN ENTFERNT, darf nie der
      Grund sein, dass der Lauf ausfaellt. Faellt sie aus, gehen alle
      Meldungen unveraendert zum Analysten; das ist teurer, aber vollstaendig.

## `promo_stats`

    Die Promo-Zahlen fuers Laufprotokoll - leer, wenn die Stufe nicht lief.

    Bewusst in `stats`, nicht nur im Log: der Promo-Ausfall seit dem
    14.08.2026 (43 gescheiterte Extraktionen an einem Tag) stand in KEINER
    Statistik, weil `stats` kein `promo_*`-Feld kannte. Dieselbe Lehre wie
    beim Geraeteradar.

    Zwei Regeln, und beide unterscheiden Faelle, die sonst gleich aussehen:

    1. **Kein Ergebnis, keine Felder.** Ein abgeschalteter
       (`promo_enabled: false`) oder uebersprungener Zweig liefert `{}`, und
       daraus wuerde ohne diese Regel "0 Aktionsseiten gelesen, 0 Angebote"
       auf transparenz.html - die Aussage eines Totalausfalls fuer eine
       Stufe, die es in diesem Lauf gar nicht gab. Die Seite, die Vertrauen
       herstellen soll, darf "gab es nicht" und "hat nichts gefunden" nicht
       verwechseln.
    2. **Neu UND bestaetigt.** Eine ruhige Woche (nichts neu, siebzig
       Aktionen bestaetigt) meldete als einzelne Zahl dasselbe wie ein
       stiller Ausfall der Extraktion.

    Als eigene Funktion herausgezogen, damit ein Test das halten kann -
    dieselbe Ueberlegung wie bei `zu_merkende_meldungen` und `vorsortieren`.

## `_sort_key`

    Freshest first; undated items last.

## `_interleave_by_source`

    Order a region's items so every operator gets a slot before any
    operator gets a second one.

    The analyst reads at most `max_items_per_region` items, so the order here
    decides what is even looked at. Straight recency ordering let one
    high-volume feed take the whole budget: in the 2026-07-31 run 220 new
    items produced only 70 analysed ones, and the operator newsrooms - the
    entire point of the watchlist - lost every slot to the trade press.
    Round-robin over the sources keeps the breadth; within a source the
    freshest item still comes first.
