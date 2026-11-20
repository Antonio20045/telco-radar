# Gesamtkosten eines Bündels (Gerät + Tarif)

Stand 20.11.2026. Gerechnet wird nur in `tco_kosten.kosten_ueber()`. Seite, Export
(`geraete-tco*.csv`), Preishistorie (`gesamt` mit `leitzahl_regel: 2`), Regel 11,
SIM-only-Referenz und Belegwahl rufen diese Funktion. `tco_24`, `tco_bindung` und
`geraeteanteil` sind entfallen.

## Definition

**Gesamtkosten = was man mindestens zahlt, um den Tarif über seine Mindestlaufzeit zu
nutzen und das Gerät danach schuldenfrei zu besitzen.**

    Gesamtkosten = Anzahlung
                 + Tarif Monat 1 … T   (je Monat der Preis seiner Phase)
                 + alle N Geräteraten
                 + Ablöse              (nur Ein-Vertrag „24+12“, siehe 1&1)
                 + Anschlusspreis
                 + Pflichtversand

- **T** (Tarifmonate) = Mindestlaufzeit des Tarifs. Unbekannte Bindung = 24 (alle
  Netzbetreiber nennen 24 Monate, § 56 TKG höchstens 24). Ohne Mindestlaufzeit
  (congstar „monatlich kündbar“) zählen ebenfalls 24 Vergleichsmonate.
- **N** = Zahl der Geräteraten. Der Ratenkauf ist ein eigener Vertrag, alle Raten sind
  geschuldet, auch nach dem Tarifende. Bei 36 Raten zählen Monat 1–24 Tarif und Rate,
  Monat 25–36 nur die Rate.
- **H** (Zeitraum der Zahl, „Kosten über H Monate“) = max(N, T); Ø/Monat = Summe / H.
  Verglichen wird nur innerhalb einer Ratenlaufzeit.
- Fehlt ein Posten, gibt es **keine** Gesamtkosten; die Lücke wird benannt
  (`Kosten.luecken`). 0,00 € ist ein gemessener Betrag, kein Platzhalter.

## Belege an den Anbieterseiten (abgerufen 20.11.2026)

| Anbieter | Sichtbarer Text | Folgerung |
|---|---|---|
| Vodafone (`/privat/handys/iphone-16.html`) | „Mindestlaufzeit des Tarifs: 24 Monate“; „Entscheidest Du Dich für 36 Monatsraten, zahlst Du ab dem 25. Monat weiter für Dein Smartphone.“; „Die Laufzeit ist unabhängig von der Laufzeit Deines Mobilfunk-Vertrags.“; „Du musst die Raten auch dann zahlen, wenn Dein Vertrag früher endet.“; „1 € einmal“, „Standard-Versand 9,98 €“, „Kein Anschlusspreis“ (Aktion; sonst „einmalig 39,99 Euro als Anschlusspreis“) | alle N Raten, Tarif 24 Monate, Versand 9,98 € einmalig |
| Telekom (`/shop/geraet/apple/apple-iphone-16/ultramarin-128-gb`, MagentaMobil L) | „MagentaMobil L 59,95 €“, „24 Monate Vertragslaufzeit“, „zzgl. 39,95 € pro Karte einmalig“, „Einmalige Zahlung 40,95 € inkl. Bereitstellung 39,95 €“ (also 1 € Anzahlung), „Anzahlung und bis zu 36 monatliche Raten“, „Gesamtpreis des Geräts 969 €“, „Geräte-Rabatt im Ratenkauf −200 € angewendet“ | Anzahlung 1 €, Anschluss 39,95 €, Rabatt steckt schon in der Rate |
| congstar (`/geraete/apple/apple-iphone-16/`) | „36 mtl. Zahlungen“, „Monatliche Kosten 20,00 €“, „Anzahlung 1,00 €“, „721,00 € Gesamtpreis“ (ebenso 24 × 30,00 € + 1 €); „Die Dauer der Gerätelaufzeit hat keine Auswirkung auf die Tariflaufzeit.“; Tarif „24 Monate Laufzeit“ oder „Ohne Laufzeit“, „Einmalige Kosten 0,00 €“ | Gerätegesamtpreis = Anzahlung + N × Rate; Tarif getrennt |
| 1&1 (`/iphone-16`, Datenblock `hwdVariantsHardwarePrices`) | „24 Monate Fix 42,– €/Mon.“, „24 + 12 Monate Flex 28,– €/Mon.“, „36 Monate Fix 28,– €“, „36 + 12 Monate Flex 21,– €“, „Flexibel entscheiden nach 24 Monaten: 12 weitere Raten zahlen“ oder Gerät zurückgeben; „Sofortkauf 1008,– €“; `tariff.contractduration` 24 | Mindestlaufzeit 24; „+12“ ist freiwillig; wer das Gerät behält, zahlt alle Raten bzw. die Ablöse |
| o2 (`/e-shop/apple/…-details`) | übersprungen: die Seite liefert Preise nur per JavaScript, im statischen HTML steht kein Preis | Regel wie Vodafone/Telekom; Versand 6,99 € laut `config/versandkosten.yaml` (Beleg 05.11.2026) |
| Saturn/MediaMarkt Tarifwelt (`tarife.mediamarkt.de`) | übersprungen: Single-Page-App ohne Text im HTML. Beleg ist die Schnittstellenantwort vom 08.11.2026 (`tests/fixtures/geraete/tarifwelt_mm_productdetail_*`): `oneTimeCosts` = Gerät 1 €, „Anschlusspreis Tarif“ 39,99 €, „Versandkosten“ 5,95 €; `monthlyCosts` = „Grundpreis Tarif“; `contractTerm` 24 | Zuzahlung + 24 × Grundpreis + Anschluss + Versand; keine Geräterate (0,00 €) |

## Felder je Anbieter

| Anbieter | Anzahlung | Tarif | Raten | Ablöse | Anschluss | Versand |
|---|---|---|---|---|---|---|
| Telekom | `geraet_zuzahlung` | `tarif_monatlich` / Phasen, 24 | `geraet_monatsrate` × 6/12/24/36 | – | `anschlusspreis` (Bereitstellung) | 0 € (Lieferung kostenlos) |
| Vodafone | `geraet_zuzahlung` | Online-Aktionsphasen (`tarif_phasen`), 24 | × 12/24/36 | – | `anschlusspreis` (Aktion 0 €) | 9,98 € |
| o2 | `geraet_zuzahlung` | `tarif_monatlich`, 24 | × 24/36 | – | `anschlusspreis` | 6,99 € |
| congstar | `geraet_zuzahlung` | `tarif_monatlich`/Phasen; Bindung 24 oder 0 → 24 | × 24/36 (Tarifrabatt auf die Rate eingerechnet) | – | `anschlusspreis` | 4,99 € |
| 1&1 Ein-Vertrag | – | `buendel_monatlich` × 24 | (im Bündelbetrag) | `geraet_zuzahlung` bei Laufzeit > 24 | `anschlusspreis` (39,90 €) | 0 € |
| Saturn/MediaMarkt | `geraet_zuzahlung` (Gerätepreis einmalig) | `tarif_monatlich`, 24 | 0 € | – | `anschlusspreis` | 5,95 € |

`geraet_zuzahlung` kommt roh aus den Adaptern. Sie wird nur über `Buendel.anzahlung`
und `Buendel.abloese` gelesen: Ist das Bündel ein Ein-Vertrag (`buendel_monatlich`)
über mehr als 24 Monate (`Buendel.mit_abloese`), ist sie die Ablöse nach Monat 24,
sonst die Anzahlung. Der Export trägt beide Spalten getrennt („Anzahlung EUR“,
„Ablöse nach Monat 24 EUR“). Die Aufteilung gehört eigentlich in die Adapter
(`collect/geraete/einsundeins*.py`); bis dort zwei Felder entstehen, gilt diese Zuordnung
in der TCO-Schicht.

## Aktionen, Boni, Inzahlungnahme, Versand

- **Preisphasen** (Online-Vorteil, „Monat 1–12 / 13–24“) zählen je Monat mit ihrem
  Preis. Nennt keine Phase einen Monat, ist das eine Lücke; ein letzter Preis wird nie
  fortgeschrieben.
- **Eingerechnete Rabatte** (Telekom „Geräte-Rabatt im Ratenkauf“, congstar
  Hardware-Rabatt beim Tarif) stecken schon im gemessenen Preis und werden nicht noch
  einmal abgezogen.
- **Bedingte Boni** (Wechselbonus per SMS, Rufnummernmitnahme, Treuebonus) und
  **Trade-in/Ankauf** gehen nie ein; sie stehen als „bis −X €“ daneben (`Aktion` mit
  `eingerechnet=False`, `Rabatt`).
- **Versand** zählt einmal, Betrag je Anbieter mit Beleg in `config/versandkosten.yaml`.
  Ein belegter Betrag 0 € zählt 0 €. Ist der Versand eines Anbieters **nicht belegt**,
  gibt es **keine** Gesamtkosten: die Zeile nennt die Lücke „Versand“ (bis 19.11.2026
  zählte er 0 €).
- **Rückgabedeal/Flex-Rückgabe** (Telekom Schlussrate, 1&1 „+12 Flex“) zählt nicht: wer
  das Gerät zurückgibt, besitzt es nicht.

## Was sich am 20.11.2026 geändert hat

- Preishistorie und Regel 11 rechneten mit `tco_24`: bei 1&1 „24+12“ 36 Bündelbeträge
  **plus** Ablöse (iPhone 16 128 GB, All-Net-Flat L: 2.139,54 € statt 1.539,66 € auf der
  Seite). Jetzt dieselbe Zahl wie die Seite. Damit die Umstellung kein „Preissprung“ im
  Bündelwächter ist, trägt jede neue Historienzeile `leitzahl_regel: 2`; Zeilen mit
  verschiedener Regel werden nicht verglichen (`rechenweise.gleiche_leitzahl`).
- Die SIM-only-Referenz zeigt ohne belegten Anschlusspreis keine Zahl mehr statt eines
  Teilbetrags.
- Unbelegter Versand ist eine Lücke statt 0 € (betrifft heute keinen Anbieter, alle
  neun haben einen Beleg).
