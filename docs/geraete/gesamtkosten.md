# Gesamtkosten eines Bündels (Gerät + Tarif)

Stand 20.11.2026. Gerechnet wird nur in `tco_kosten.kosten_ueber()`. Seite, Export
(`geraete-tco*.csv`), Preishistorie (`gesamt`), Regel 11, SIM-only-Referenz und
Belegwahl rufen diese Funktion. `tco_24`, `tco_bindung` und `geraeteanteil` sind
entfallen.

## Definition

**Gesamtkosten sind eine Vergleichsbasis: was der Tarif über seine Mindestlaufzeit und
das Gerät bis zur letzten Rate kosten. Ohne Mindestlaufzeit oder ohne bekannte
Bindung zählt der Tarif 24 Vergleichsmonate.** Für gebundene Tarife ist das zugleich
der Betrag, den man mindestens zahlt, um den Tarif zu nutzen und das Gerät danach
schuldenfrei zu besitzen; für monatlich kündbare Tarife ist es eine Annahme von 24
Nutzungsmonaten, damit alle Angebote über denselben Zeitraum stehen.

    Gesamtkosten = Einmalzahlung Gerät (Anzahlung bzw. Gerätepreis einmalig)
                 + Tarif Monat 1 … T   (je Monat der Preis seiner Phase)
                 + alle N Geräteraten
                 + Anschlusspreis
                 + Pflichtversand

    Ein-Vertrag (1&1: ein Betrag für Tarif und Gerät) = Einmalzahlung Gerät
                 + N × Bündelbetrag + Anschlusspreis + Versand

- **T** (Tarifmonate) = Mindestlaufzeit des Tarifs; unbekannt oder 0 (congstar
  „monatlich kündbar“, SIM-only ohne Bindung) = 24 Vergleichsmonate. § 56 TKG erlaubt
  höchstens 24.
- **N** = Zahl der Geräteraten. Der Ratenkauf ist ein eigener Vertrag, alle Raten sind
  geschuldet, auch nach dem Tarifende. Bei 36 Raten zählen Monat 1–24 Tarif und Rate,
  Monat 25–36 nur die Rate; bei 12 Raten Monat 1–12 Tarif und Rate, 13–24 nur der
  Tarif.
- **H** (Zeitraum der Zahl, „Kosten über H Monate“) = max(N, T); Ø/Monat = Summe / H.
  Verglichen wird nur innerhalb einer Ratenlaufzeit.
- 1&1 nennt nur einen Betrag für Tarif und Gerät. Bei „36 Monate Fix“ stecken in
  Monat 25–36 deshalb auch die Tarifmonate (zum Fixpreis), die getrennt nicht
  ausweisbar sind.
- Fehlt ein Posten, gibt es **keine** Gesamtkosten; die Lücke wird benannt
  (`Kosten.luecken`). 0,00 € ist ein gemessener Betrag, kein Platzhalter.

## Belege an den Anbieterseiten (abgerufen 20.11.2026)

| Anbieter | Sichtbarer Text | Folgerung |
|---|---|---|
| Vodafone (`/privat/handys/iphone-16.html`) | „Mindestlaufzeit des Tarifs: 24 Monate“; „Entscheidest Du Dich für 36 Monatsraten, zahlst Du ab dem 25. Monat weiter für Dein Smartphone.“; „Die Laufzeit ist unabhängig von der Laufzeit Deines Mobilfunk-Vertrags.“; „Du musst die Raten auch dann zahlen, wenn Dein Vertrag früher endet.“; „1 € einmal“, „Standard-Versand 9,98 €“, „Kein Anschlusspreis“ (Aktion; sonst „einmalig 39,99 Euro als Anschlusspreis“) | alle N Raten, Tarif 24 Monate, Versand 9,98 € einmalig |
| Telekom (`/shop/geraet/apple/apple-iphone-16/ultramarin-128-gb`, MagentaMobil L) | „MagentaMobil L 59,95 €“, „24 Monate Vertragslaufzeit“, „zzgl. 39,95 € pro Karte einmalig“, „Einmalige Zahlung 40,95 € inkl. Bereitstellung 39,95 €“ (also 1 € Anzahlung), „Anzahlung und bis zu 36 monatliche Raten“, „Gesamtpreis des Geräts 969 €“, „Geräte-Rabatt im Ratenkauf −200 € angewendet“ | Anzahlung 1 €, Anschluss 39,95 €, Rabatt steckt schon in der Rate |
| congstar (`/geraete/apple/apple-iphone-16/`) | „36 mtl. Zahlungen“, „Monatliche Kosten 20,00 €“, „Anzahlung 1,00 €“, „721,00 € Gesamtpreis“ (ebenso 24 × 30,00 € + 1 €); „Die Dauer der Gerätelaufzeit hat keine Auswirkung auf die Tariflaufzeit.“; Tarif „24 Monate Laufzeit“ oder „Ohne Laufzeit“, „Einmalige Kosten 0,00 €“ | Gerätegesamtpreis = Anzahlung + N × Rate; Tarif getrennt; ohne Laufzeit 24 Vergleichsmonate |
| 1&1 (`/iphone-16`, Datenblock `hwdVariantsHardwarePrices`) | „24 Monate Fix 42,– €/Mon.“, „36 Monate Fix 28,– €“ (dazu der Tarifpreis der Stufe), „+ 12 Monate Flex“ als freiwillige Verlängerung; „Sofortkauf 1008,– €“ = 24 × 42 = 36 × 28; `tariff.contractduration` 24; keine einmalige Gerätezahlung außer der Bereitstellung | N × Bündelbetrag + Bereitstellung; „Flex“ und Rückgabe zählen nicht |
| o2 (`/e-shop/samsung/samsung-galaxy-s25-ultra-256gb-titanium-gray-details`, Browser 21.11.2026) | „Gerät monatlich: 45,00 €“, „Ratenzahlung: 24 Monate“, „Gesamtpreis Gerät: 1.081,00 €“, „Tarif monatlich: 24,99 € (Mindestlaufzeit 24 Monate)“, „Gerät Anzahlung: 1,00 €“, „einmaliger Anschlusspreis 0,00 € 39,99 €“ (durchgestrichen), „Versandkosten: 6,99 €“ | Regel wie Vodafone/Telekom; Versand 6,99 € |
| Saturn/MediaMarkt Tarifwelt (`tarife.mediamarkt.de`) | übersprungen: Single-Page-App ohne Text im HTML. Beleg ist die Schnittstellenantwort vom 08.11.2026 (`tests/fixtures/geraete/tarifwelt_mm_productdetail_*`): `oneTimeCosts` = Gerät 1 €, „Anschlusspreis Tarif“ 39,99 €, „Versandkosten“ 5,95 €; `monthlyCosts` = „Grundpreis Tarif“; `contractTerm` 24 | Gerätepreis einmalig + 24 × Grundpreis + Anschluss + Versand; Geräterate aus `hardware.variants[0].monthlyPrice` (bisher immer 0,00 €), fehlt sie, ist die Zeile eine Lücke |

## Felder je Anbieter

| Anbieter | Einmalzahlung Gerät | Tarif | Raten | Anschluss | Versand |
|---|---|---|---|---|---|
| Telekom | `geraet_zuzahlung` (Anzahlung) | `tarif_monatlich` / Phasen, 24 | `geraet_monatsrate` × 6/12/24/36 | `anschlusspreis` (Bereitstellung) | 0 € (Lieferung kostenlos) |
| Vodafone | `geraet_zuzahlung` (Anzahlung) | Online-Aktionsphasen (`tarif_phasen`), 24 | × 12/24/36 | `anschlusspreis` (Aktion 0 €) | 9,98 € |
| o2 | `geraet_zuzahlung` (Anzahlung) | `tarif_monatlich`, 24 | × 24/36 | `anschlusspreis` | 6,99 € |
| congstar | `geraet_zuzahlung` (Anzahlung) | `tarif_monatlich`/Phasen; Bindung 24, ohne Laufzeit 24 Vergleichsmonate | × 24/36 (Tarifrabatt auf die Rate eingerechnet) | `anschlusspreis` | 4,99 € |
| 1&1 Ein-Vertrag | `geraet_zuzahlung` | `buendel_monatlich` × 24/36 (Tarif und Gerät) | (im Bündelbetrag) | `anschlusspreis` (39,90 €) | 0 € |
| Saturn/MediaMarkt | `geraet_zuzahlung` (Gerätepreis einmalig) | `tarif_monatlich`, 24 | `geraet_monatsrate` × 24 (gelesen, bisher 0 €) | `anschlusspreis` | 5,95 € |

Der Export nennt die Spalte deshalb „Gerät einmalig EUR“, nicht „Anzahlung“.

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
- **Rückgabedeal / Flex** (Telekom Schlussrate, 1&1 „+ 12 Monate Flex“) zählt nicht:
  wer das Gerät zurückgibt, besitzt es nicht.

## Was sich am 20.11.2026 geändert hat

- Preishistorie und Regel 11 rechneten mit `tco_24` (bei 1&1 „24+12“ 36 Bündelbeträge
  **plus** Ablöse). Jetzt dieselbe Zahl wie Seite und Export.
- Die 1&1-Ablöse nach Monat 24 („24+12“) ist entfallen: 1&1 verkauft seit 20.11.2026
  „24/36 Monate Fix“, der Adapter misst beides (#171). Zeilen davor trennt
  `rechenweise` (1&1 Stufe 2) von heutigen; Bündelwächter, Regel 11 und Zeitreihe
  vergleichen nicht über diesen Bruch.
- Ohne Mindestlaufzeit zählt der Tarif auch bei 12 Raten und ohne Gerät 24
  Vergleichsmonate (vorher 12 Monate bzw. Lücke „Zeitraum“).
- Die SIM-only-Referenz zeigt ohne belegten Anschlusspreis keine Zahl mehr statt eines
  Teilbetrags.
- Unbelegter Versand ist eine Lücke statt 0 € (betrifft heute keinen Anbieter).
- o2: Ein abgeleiteter Tarif (`tarifsumme_minus_geraeterate`) nimmt den Anschlusspreis
  nicht mehr vom Referenzgerät, sondern aus seiner eigenen Tarifoption
  (`o2_anschluss`): Listenpreis 0 € in der Fußnote zählt 0 €, ein höherer oder keiner
  ist die Lücke „Anschlusspreis“ (Gegenprobe 20.11.2026: iPhone 14 erneuert, S Special
  Plus, gespeichert 39,99 €, Seite 0,00 €). Seit 21.11.2026 auch dann die Lücke, wenn
  die Antwort ihren gewählten Tarif über dessen Fußnote hebt (Redmi 17, on Demand M:
  Fußnote 0 €, berechnet 39,99 €).
