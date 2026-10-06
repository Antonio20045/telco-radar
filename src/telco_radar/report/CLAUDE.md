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

Kernzahl jeder Bündelzeile ist `tco_model.kosten_ueber()`: Anzahlung + Tarif über H Monate + alle Geräteraten + Anschlusspreis, H = größerer Wert aus Ratenlaufzeit und Tarifbindung (12 → 24, 24 → 24, 36 → 36; 1&1 ein Vertrag über 36). Ein Tarifmonat nach der Bindung zählt nur mit gemessener Preisphase, sonst ist die Zeile eine benannte Lücke ohne Zahl. Karte, Zeitreihe, Rechenweg und Export rufen dieselbe Funktion (`docs/datenkonzept-geraete.md` Abschnitt 5).

Erfasst werden alle angebotenen Ratenlaufzeiten: Telekom 6/12/24/36, o2 24/36, congstar 24/36, 1&1 „24+12“ mit Schlusszahlung, Vodafone 12/24/36. Die Laufzeit gehört in den Bündelschlüssel, sonst überschreiben sich die Varianten.

Verglichen wird nur innerhalb einer Ratenlaufzeit (`geraete_laufzeit.py`): Sieger, Δ zu Vodafone (gleiches Band, gleiche Laufzeit), Spanne, Kacheln, Grafik und Radar je Ansicht 12/24/36; laufzeitübergreifend gibt es keinen Sieger. Ohne Bündel in einer Laufzeit heißt ein Anbieter „nicht erfasst“. Auf der Seite wählt `#gr-zr-laufzeiten` die Ansicht für die ganze Tafel (`?laufzeit=12|24|36|alle`, Standard 24); jede Zeile steht nur unter ihrer eigenen Laufzeit (`data-lz` aus `setze_ansicht`), „alle“ gruppiert ohne Sieger und Δ. Bandgraph (`baender_je_laufzeit`) und Bündel-Export (`geraete-tco-<N>.csv`, Link `#gr-export-tco`) folgen dem Umschalter; `geraete-tco.csv` ist „alle“.
