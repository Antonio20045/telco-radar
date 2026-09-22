# Befund: Telekom-Ratenlaufzeiten aus gespeicherten Belegen (2026-09-22)

Kein Netzabruf. Geprüft: `tests/fixtures/geraete/telekom_kategorie_buendel_magentamobil_s.html.gz` (K-B),
`…_smartphones_ohne_vertrag.html.gz` (K-O), alle acht `outputs/beleg-telekom-{geraete,lokallauf}-*.json` (B-*).
Die B-Dateien sind reine Request-Manifeste ohne Nutzlast und enthalten kein einziges Ratenfeld. Alle Zahlen
stammen aus `window.__INITIAL_STATE__` beider Fixtures, vollständig als JSON geparst, nicht per Regex.

## 1. `numberOfInstallments` ungleich 36? Nein.

Zähler: K-B 9 Einträge mit 36, 0 mit anderem Wert. K-O 10 mit 36, 0 mit anderem Wert.
B-* (8 Dateien): Feld kommt nicht vor.
K-B `.productList.data[0].price`:
`{"installments":[{"id":"RTK-11190-36-1","numberOfInstallments":36,"recurringChargeOccurrence":35,"recurringChargeStartShift":35,"recurringPrice":28.3,"totalPrice":1117.8}],"upfrontPrice":99}`
Das Geschwisterfeld `numberOfInstallment` (Einzahl) steht ebenso 9x/10x auf 36. Alle Ratenplan-IDs tragen im
dritten Segment nur `36`: `RTK-11190-36-1`, `RTK-20590-36-1`, `RTK-7190-36-1`, `RTK-13490-36-1` …

## 2. Mehr als ein Plan je `installments`? Nein.

K-B 9x Länge 1, K-O 10x Länge 1, nie 2 oder mehr. Das einzige leere Array steht unter
`.checkout.paymentV2.paymentGateway.installments = []`, gehört also zum Zahlungs-Gateway, nicht zum Gerät.

## 3. Produktdetail-Nutzlast? Keine.

`productDetailsData` liegt in **beiden Kategorieseiten** vor, ist aber der leere Anfangszustand des Reducers:
`productName:""`, `variants:[]`, `tariffs:[]`, `options:[]`, `totalPrices:[]`, dazu `.productDetailed.loading = true`.
Der Umschalter-Zustand ist durchgehend leer: `.productDetailed.installmentConfiguratorItems = {}`,
`.productDetailed.installmentDropdownData = []`, `.productDetailed.instalmentId = null`,
`.productDetailed.numberOfInstalments = null`, `.productDetailed.isInstallmentConfiguratorOpen = false`.
Korrektur am bisherigen Befund: diese Felder belegen **keine** Produktseite, sie stehen als Leerzustand
auch auf der Kategorieseite.

## 4. API-/Endpunktpfad für Ratenpläne? Keiner.

Weder `/api/`, `_next/data`, `.json`, `graphql` noch ein Pfad mit instalment/installment/financing/rate
kommt vor (Regex über Rohtext und über den geparsten Baum). Gefunden nur Basisadressen und ein Filterschlüssel:
1. `.appData.BFF_EXT = https://www.telekom.de/shop/api/eshop/bff-de`
2. `.appData.GATEWAY_EXT = https://www.telekom.de/shop/api/eshop`
3. `.appData.PAGE_BUILDER_BASE_URL = https://www.telekom.de/shop/api/eshop/builder`
4. `.configuration.cms_configuration.global.prolongation.bffBaseUrl = https://bfftest.yo-digital.com/bff/api`
5. `.configuration.cms_configuration.modules.productList.installmentPriceFilterKey = "instalmentFilter"`
Grund der Fehlanzeige: die Pfade stecken in externen Bündeln wie `…/shop/assets/productlist.e0c5133f.js`.

## 5. Nennt die Seite 6/12/24? Ja — nur als Rechtstext, nie als Datenfeld.

Wörtlich, in beiden Fixtures identisch, unter `.translation.cart.global.common.instalment.configurator.legalNote`
und `.translation.cart.contractJourney.deviceDetail.installmentSheet.legalNote`:
„Beim Ratenkauf wird der Kaufpreis in eine Anzahlung und, abhängig vom Gerät, in wahlweise 6, 12, 24 oder 36
gleiche monatliche Raten aufgeteilt, wobei die Schlussrate abweichen kann."
Übrige Fundstellen sind Etiketten mit Platzhalter: `installmentsZeroPercentInterest` („… bis zu 36 monatliche
Raten …"), `forwardTradeInSubheading` („… Schlussrate im 25. bzw. 37. Monat."), `splitPaymentLabel = "Ratenzahlung über {0} Monate"`.
Einzige 12 in Ratenkontext als Konfigurationswert: `modules.productList.installment = 12` — Bedeutung
**nicht belegbar** (steht bei Anzeigeschaltern wie `itemPerPage`, nicht bei Preisdaten).

## Urteil

**Ein Laufzeit-Parameter für unsere Abrufadresse existiert nicht**: die ausgelieferten Kategorieseiten tragen
je genau einen, immer 36-monatigen Plan, die Auswahl 6/12/24/36 steht nur im Rechtstext des Konfigurators,
und dessen Zustandsfelder kommen leer vom Server. **Nicht entscheidbar** bleibt, ob der BFF
(`/shop/api/eshop/bff-de`) einen solchen Parameter kennt — Endpunkt und Parameternamen stehen in den
externen JS-Bündeln, die nicht Teil der Belege sind.
