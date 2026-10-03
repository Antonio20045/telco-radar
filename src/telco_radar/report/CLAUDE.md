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

## Leitzahl der Geräteseite (Ziel, noch nicht umgesetzt)

Kosten über 24 Monate = Anzahlung + 24 Monate Tarif + alle Geräteraten inklusive Restschuld nach Monat 24 + Anschlusspreis.

Erfasst werden alle angebotenen Ratenlaufzeiten: Telekom 6/12/24/36, o2 24/36, congstar 24/36, 1&1 „24+12“ mit Schlusszahlung, Vodafone 12/24/36. Die Laufzeit gehört in den Bündelschlüssel, sonst überschreiben sich die Varianten. Das ist nicht der Ist-Stand von `tco_model.py` (`tco_24()`, `tco_bindung()`); wer daran arbeitet, gleicht Code, Etiketten und Tests an und prüft, dass Rechenweg-Panel und Katalog dieselbe Zahl zeigen.
