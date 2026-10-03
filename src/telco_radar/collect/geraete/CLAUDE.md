# Geräteradar: Adapter und Katalog

- Geräte-IDs kommen nur aus `config/geraete_katalog.yaml`; der Titel dient nur zum Finden des Katalogeintrags. Anbieter stehen mit Methode und Grund in `config/geraete_quellen.yaml`.
- Der Zustand (neu, refurbished, B-Ware) ist eine Preisdimension in der `sku_id`; verglichen wird nur `neu`. o2 schreibt „(gebraucht)“ und „(erneuert)“.
- `generation` ist die Nummer innerhalb einer Baureihe; gezählt und gefiltert wird je (Hersteller, Baureihe) über `serie_aus_modell()`.
- Ein Modellzusatz hinter dem Katalogtreffer („Fold“, „FE“, „Edge“) verwirft die Zuordnung (`_MODELLZUSATZ`). Der Zubehörfilter braucht zwei Listen.
- Bei Netzbetreibern steht der Gerätepreis selten im naheliegenden Feld (Anzahlung gegen Gesamtpreis); Bündel aus Gerät plus Zubehör werden verworfen.
- Adapter liefern Quelllinks absolut; relative Adressen aus einer API-Nutzlast werden gegen die Website aufgelöst, nicht gegen die API.
- `laeufe` zählt nur vollständige Läufe, `termine` jeden Tag mit gesehenen Listungen. Jeder Anbieter bekommt `_MINDEST_JE_ANBIETER` Zeit.
- „Nicht gelesen“ ist nicht „leer“: Altern (`mark_stale`) und Ersetzen nur für wirklich gelesene Seiten, auch bei einem wegen Visit-time übersprungenen Anbieter. Ein Deckel schneidet nach der Vorprüfung ab, nie den Scan.
- Die Extraktionslogik arbeitet auf Text, nicht auf PDF; `pdftotext` ist ein externes Binary und gehört nicht in die Tests.
- Ist ein Wert bei allen Anbietern gleich (etwa nur 36-Monats-Raten), ist das zuerst eine Erfassungslücke.
