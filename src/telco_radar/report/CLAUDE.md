# Seiten: render_site, Vorlagen, Geräteseite

- `render_site()` gibt die nicht gebauten Teile zurück; die Seite nennt den Ausfall sichtbar. Gerätezahlen rechnet nur `tco_model.py`, `report/` rechnet nichts nach und importiert weder `collect` noch Stores (Vertrag `report-rechnet-nur`).
- Sichtbarkeit und Farbe werden im Browser gemessen (computed `display`, Boxhöhe, computed color), nie am Attribut: eine `display`-Regel übersteuert `[hidden]`.
- Eine Rechnung, die im Browser läuft, wird im echten Chromium getestet, nicht in Python nachgebaut.
- Wer oberhalb der Falz etwas einfügt, prüft `scripts/pruefe_portal.py` Kriterium 1. Nach einem `--no-llm`-Lauf fällt Kriterium 4 durch; vorher `git restore site data`.
- Seitenhöhen strukturell begrenzen (Zeilendeckel im Modul, zugeklappte `<details>`), sonst kippt der Höhentest mit dem Bestand.
- In der Cloud laden Google Fonts nicht; Layout-Tests prüfen Eigenschaften (kein Überlauf bei verbreitertem Text), keine Pixelbreiten.
- Der niedrigste Preis ist der wahrscheinlichste Fehler: `geraete_pruefung.py` sortiert Selbstwidersprüche aus; Ausreißer gegen den Markt werden gemeldet, nicht gelöscht.
- Eine Datenqualitätsheuristik schaltet nie die Navigation; die Veröffentlichungsschwelle rechnet gegen den Bestand.
- Arbeitsstand der Geräteseite: `outputs/fortschritt-geraeteseite.md`.

## Leitzahl der Geräteseite

Kernzahl jeder Bündelzeile ist `tco_model.kosten_ueber()`: Anzahlung + Tarif über H Monate + alle Geräteraten + Anschlusspreis, H = größerer Wert aus Ratenlaufzeit und Tarifbindung (12 → 24, 24 → 24, 36 → 36; 1&1 über 24: Bündelbetrag + Ablöse). Der Tarif zählt nur seine Bindung (höchstens 24 Monate, § 56 TKG); bei 36 Raten zählen Monat 25–36 nur die Rate (Antonio, 10.10.2026). Karte, Zeitreihe, Rechenweg und Export rufen dieselbe Funktion (`docs/datenkonzept-geraete.md` Abschnitt 5).

Erfasst werden alle angebotenen Ratenlaufzeiten: Telekom 6/12/24/36, o2 24/36, congstar 24/36, 1&1 „24+12“ mit Schlusszahlung (24 Monate, kein 24+12 mit 36 Monaten; Manager, 05.11.2026), Vodafone 12/24/36. Die 1&1-Ablöse ist ein Gerätewert je Speichergröße; weicht sie zwischen Tarifen ab, wird der Preis fail-closed zur Lücke „1&1-Wert widersprüchlich, neu messen“ (`analyze/geraete_widerspruch.mit_einheitlicher_einmalzahlung`). Die Laufzeit gehört in den Bündelschlüssel, sonst überschreiben sich die Varianten.

Verglichen wird nur innerhalb einer Ratenlaufzeit (`geraete_laufzeit.py`; 6 Raten stehen unter 24): Sieger, Δ zu Vodafone (gleiches Band, gleiche Laufzeit), Spanne, Kacheln, Grafik und Radar je Ansicht 12/24/36; laufzeitübergreifend gibt es keinen Sieger. Ohne Bündel in einer Laufzeit heißt ein Anbieter „nicht erfasst“. Auf der Seite wählt `#gr-zr-laufzeiten` die Ansicht für die ganze Tafel (`?laufzeit=12|24|36|alle`, Standard 24); jede Zeile steht nur unter ihrer eigenen Laufzeit (`data-lz` aus `setze_ansicht`), „alle“ gruppiert ohne Sieger und Δ. Bandgraph (`baender_je_laufzeit`) und Bündel-Export (`geraete-tco-<N>.csv`, Link `#gr-export-tco`) folgen dem Umschalter; `geraete-tco.csv` ist „alle“.

Der jüngste Zeitreihen-Punkt einer 1&1-Linie zeigt nie einen Wert, den die Tafel von heute als widersprüchlich führt - nur dieser eine Punkt fällt weg, ältere (12.09.–03.11.2026, damals einheitlich) bleiben (`geraete_zeitreihe_auswahl.py`).

Belege (Screenshots): `geraete_belege.installiere()` liest nur `data/state/belege_manifest.json` (Schreiber: Schritt „Belege-Manifest“ in `geraete.yml`, Quelle ist die Asset-Liste der Releases `belege-JJJJ-MM-TT` und `belege-gross-JJJJ-MM`); kein Netz, kein LLM. Sichtbarkeit und Löschfrist teilen `beleg_regeln`. Der Beleg folgt der gewählten Kombination (Gerät × Speicher × Tarifband × Laufzeit × Anbieter): `belegpaare` in `_geraete_buendel.html.j2` zeigt je Anbieter nur Bilder, deren Preiszeile (`geraete_zeilenbelege`) zu Band und Laufzeit passt (`stelleBelege` in `app.js`), sonst „Für diese Kombination liegt noch kein Screenshot vor“; das Paar-Bild ist nie Ersatz. Ein Beleg mit `bildfolge` (`beleg_bildfolge`) zeigt alle Bilder in Reihenfolge; Einzelbild (`…__preis__<kennung>`) und Folgebilder liegen im Release mit derselben Kennung im Namen (`beleg_regeln.folge_dateiname`), eine Folge besteht nur aus Bildern einer Kennung, und die Zeile zeigt sie nur, wenn die Kennung zur `beleg_id` passt (`fremd_zur_kennung`, sonst Vermerk); das Manifest nimmt nur Anhänge, die dort liegen, und nennt fehlende Schritte mit Grund (`bildfolge_fehlt`), nie einen Link ohne Datei. Ein unlesbares Manifest wird als Ausfall genannt.
