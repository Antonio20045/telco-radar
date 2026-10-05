# Kommentarwissen 15-schalterbegruendungen

Stand: Commit 657805b. Begründungen, die hinter einem Werkzeugschalter (`noqa`, `pragma: no cover`) in derselben Kommentarzeile stehen. Paket 19 kürzt solche Zeilen auf den Schalter; das Wissen steht hier. Die übrigen Kommentare dieser Dateien stehen in den Protokollen 01 bis 14.

## Wissen je Datei

### `scripts/lokallauf_congstar.py`
- Zeile 94 (`BLE001`): Ein Fehler im Lokallauf wird protokolliert und danach weitergeworfen, nicht geschluckt.

### `scripts/lokallauf_einsundeins.py`
- Zeile 93 (`BLE001`): Ein Fehler im Lokallauf wird protokolliert und danach weitergeworfen, nicht geschluckt.

### `scripts/lokallauf_einsundeins_simonly.py`
- Zeile 82 (`BLE001`): Ein Fehler im Lokallauf wird protokolliert und danach weitergeworfen, nicht geschluckt.

### `scripts/lokallauf_telekom.py`
- Zeile 139 (`BLE001`): Ein Fehler im Lokallauf wird protokolliert und danach weitergeworfen, nicht geschluckt.

### `scripts/miss_volltext_quellen.py`
- Zeile 111 (`BLE001`): Breites `except` ist hier zulässig, weil das Skript nur misst (Diagnose) und kein Produktionspfad ist.

### `scripts/pruefe_quellenvorschlag.py`
- Zeile 330 (`BLE001`): Der Check soll auch ohne lesbare Konfiguration laufen.
- Zeile 394 (`BLE001`): Eine tote Quelle ist kein Grund, den ganzen Check abzubrechen.

### `src/telco_radar/analyze/competitors.py`
- Zeile 162 (`BLE001`): Ein fehlerhaftes Anbieterprofil darf die übrigen nicht verhindern.

### `src/telco_radar/analyze/vorsortierung.py`
- Zeile 276 (`BLE001`): Fehler-Durchlass wie im Modulkopf beschrieben: Scheitert die Vorsortierung, gehen die Meldungen ungefiltert weiter.

### `src/telco_radar/collect/__init__.py`
- Zeile 185 (`BLE001`): Bewusste Robustheit: Eine einzelne Quelle darf das Sammeln nicht abbrechen.

### `src/telco_radar/collect/ct_log.py`
- Zeile 313 (`pragma: no cover`): Der echte Netzpfad ist von Tests ausgenommen.

### `src/telco_radar/collect/http.py`
- Zeile 80 (`pragma: no cover`): Der Rückfall ohne `certifi` wird nicht getestet, weil `certifi` in `requirements.txt` steht.

### `src/telco_radar/collect/newsroom_js.py`
- Zeile 100 (`BLE001`): Fehlt das Cookie-Banner oder ist es ein anderes, ist das kein Fehler.

### `src/telco_radar/collect/promo_snapshot.py`
- Zeilen 243 und 381 (`BLE001`): Das zusätzliche Signal darf den Abruf nie kippen.

### `src/telco_radar/pipeline.py`
- Zeile 1114 (`BLE001`): Die Linse kippt keinen Lauf.
- Zeile 1210 (`BLE001`): Bilder dürfen nie den Lauf kippen.

### `src/telco_radar/promo_bilder.py`
- Zeile 435 (`BLE001`): Ein Bild kippt keinen Lauf.

### `src/telco_radar/report/bilder.py`
- Zeile 167 (`BLE001`): Jedes kaputte Bild fällt hier durch.
- Zeile 226 (`BLE001`): Ein unlesbares Bild zeigt auch nichts.
- Zeilen 290 und 368 (`BLE001`): Ein kaputtes Bild kippt keinen Lauf.

### `src/telco_radar/report/diff_bilder.py`
- Zeile 201 (`BLE001`): Ein Bild kippt keinen Lauf.

### `src/telco_radar/report/folien.py`
- Zeile 334 (`pragma: no cover`): `kuerze()` schließt den Fall aus; der Zweig steht nur zur Absicherung da.

### `src/telco_radar/report/html.py`
- Zeile 2213 (`BLE001`): Eine fehlende Konfiguration kippt keine Seite.

### `src/telco_radar/uebersetzung/sprache.py`
- Zeile 148 (`BLE001`): Abgefangen wird eine fehlende Bibliothek oder eine fehlende Modelldatei.
- Zeile 173 (`BLE001`): Eine Bibliothek darf den Lauf nicht kosten.

### `src/telco_radar/uebersetzung/stufe.py`
- Zeile 217 (`BLE001`): Ein einzelner Artikel kostet nie den Lauf.

### `src/telco_radar/uebersetzung/volltext.py`
- Zeile 74 (`pragma: no cover`): Der Zweig hängt an der Installation und ist nicht testbar.
- Zeile 87 (`BLE001`): Eine Bibliothek darf nichts kosten.

### `tests/test_differentiation_editor.py`
- Zeile 76 (`B018`): Der Ausdruck steht nur als Dokumentationsbezug da.

### `tests/test_geraete_adapter_congstar.py`
- Zeile 160 (`noqa` ohne Code): Die Schleife bleibt bewusst einfach.
