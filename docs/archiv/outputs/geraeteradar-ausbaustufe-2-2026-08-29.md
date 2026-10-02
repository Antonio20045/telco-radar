# Geräteradar, Ausbaustufe 2 — Schlussliste

Stand: 29.08.2026. Auftragsgrundlage: „Geräteradar, Ausbaustufe 2"
(28.08.2026), Blöcke G0–G4.

**Stand danach:** 1938 → **1988 Tests**, alle grün. 4 Anbieter mit Daten
(vorher 2), 218 live gesammelte Listungen aus den zwei neuen Adaptern
allein, 83 Katalogmodelle (vorher 46).

---

## G0 — die Diagnose, und sie war der Grund für fast alles andere

Die Seite meldete nach 17 Tagen „bisher 1 Messtermin", obwohl der nächtliche
Gerätezweig **jede Nacht lief** (16 Läufe in Folge, alle erfolgreich). Drei
unabhängige Ursachen, alle am Actions-Log und an der Zustandsdatei gemessen:

| # | Befund | Messung |
|---|---|---|
| 1 | **Die Messtermin-Zählung hing an der Preishistorie.** Die trägt nur ÄNDERUNGSpunkte; bei stabilen Preisen schweigt sie | alle 85 Zeilen von `geraete_preise.jsonl` tragen den 10.08. — vier echte Prüftermine sahen aus wie einer |
| 2 | **`protokolliere_lauf` lief nur für vollständige Läufe.** mobilcom-debitel bestätigt jede Nacht 68–84 Listungen, wird am Zeitbudget aber nie fertig (`status: frist`) — und fehlte deshalb KOMPLETT in der Laufbilanz | `db['anbieter']` kannte genau einen Anbieter: ALDI TALK. `_oft_genug` sperrte damit 84 von 85 Listungen aus der Lifecycle-Auswertung |
| 3 | **Das Zeitbudget war eine gemeinsame Weide.** freenet verbrauchte die vollen 1500 s | Lauf #17: `mobilcom-debitel -> frist, 68 Listungen` und direkt darunter `ALDI TALK -> frist, 0 Listungen aus 0 Produktseiten`. ALDI TALKs letzte Bestätigung blieb der 14.08. |

Ein vierter Befund kam beim Anbinden dazu und ist ebenfalls vorbestehend:

> **`_hole_fabrik` versprach in der eigenen Docstring, 404 von 403 zu
> unterscheiden** — „`collect.http.fetch` wirft bei beidem nicht". Das ist
> falsch: `fetch` ruft `raise_for_status()`. Der Robots-Wächter landete in
> seinem Ausnahmezweig („kein Ergebnis heißt nicht erlaubt") und führte den
> Anbieter als nicht abrufbar. Aufgefallen ist es nie, weil **jeder bisher
> konfigurierte Host eine robots.txt mit 200 ausliefert**; `api.vodafone.de`
> ist der erste ohne. Ein Host ohne robots.txt ist im Web der Normalfall.

**Nebenbefund, der eine offene Frage des Auftrags beantwortet:** Medimax
liefert nicht deshalb nichts, weil es außerhalb der Besuchszeit läge. Lauf
#17 (03:59 UTC, also im Fenster) protokolliert wörtlich
`Medimax -> fehler, 0 Listungen aus 20 Produktseiten`. Die Seiten werden
abgerufen und ergeben null Listungen. Ob die Seiten nichts hergeben oder ob
nichts davon im Katalog steht, sagte das Protokoll nicht — dafür gibt es
jetzt den **Rohsatz-Zähler** je Anbieter. Der nächste Nachtlauf beantwortet
es.

---

## G1 — von 2 auf 4 Anbieter, beide neuen live gemessen

### Vodafone (150 Listungen)

Der Befund vom 11.08. („im Roh-HTML steht kein Preis") stimmt und gilt für
die HTML-Seite. Gelesen wird die Schnittstelle, die die Übersichtsseite
selbst aufruft:

```
GET https://api.vodafone.de/glados/v2/hardware/v2
    ?businessTransaction=newContract&salesChannel=Online.Consumer
GET .../virtualItem/<id>?…
```

Adresse, die zwei Pflichtparameter und der öffentliche Browser-Schlüssel
stehen wörtlich in Vodafones eigenem Skriptbündel
`/simplicity/device-overview/device-overview.bundle.js`. `api.vodafone.de`
hat keine robots.txt (404).

**Zwei Preise, und nur einer ist der Gerätepreis.** Die Liste trägt unter
`prices.composition` ausschließlich Bündelzahlen mit 1 € Anzahlung. Der
Preis ohne Vertrag steht je Variante unter
`atomics[].prices.hardware.priceByType.rate.onetime.withoutDiscounts.gross`.
Deshalb ruft der Adapter je Gerät die Detailnutzlast ab.

### o2 (68 Listungen)

Der Katalog hinter `/e-shop/rest/catalog/…?hwOnly=true` — **eine Antwort,
93 Geräte**. Die vollständige Adresse samt Medientyp
(`application/vnd.commerce.message+json`) steht in der Nutzlast von
`/e-shop/`; die Seite ruft sie selbst auf.

| Falle | Behandlung |
|---|---|
| **18 der 93 Einträge sind Gerät PLUS Zubehör** („iPhone 17 Pro Max mit Watch Ultra 3", 2323 €) | verworfen. Was der Zubehörpreis ist, steht nirgends |
| **`oneTimePrice` ist die Anzahlung, nicht der Preis** (1 € bzw. 7 €) | gespeichert wird `totalPrice`. Nachgerechnet: Anzahlung + 24 Raten geht bei **92 von 93** Einträgen exakt auf |

**robots.txt, und das ist die Stelle, an der jemand später nachsehen wird:**
`Disallow: /e-shop/rest/` steht **ausschließlich in der Gruppe
`User-agent: googlebot`**, zusammen mit `/chat-ui/`, `/ebooking/` und
`/benefit-service/` — das Muster einer Suchmaschinen-Hygiene. Die für uns
gültige Gruppe `User-agent: *` sperrt den Pfad nicht; unser Absender ist
`TelcoRadar/1.0`, und `lies_robots()` liest genau die `*`-Gruppe. Das ist
das Gegenteil der Annahme im Modulkopf von `robots.py` („`*` ist die
strengere und immer gültige Lesart") — bei o2 ist die Googlebot-Gruppe die
strengere. Der Befund steht wörtlich in `geraete_quellen.yaml` und damit auf
`/geraete-quellen.html`.

### Der Katalog stand eine Gerätegeneration hinter dem Markt

Von **126 live geführten Modellnamen** (Vodafone 51 + o2 93 ohne
Zubehörbündel) trafen **67 keinen Katalogeintrag**: Pixel 11, Galaxy S26 FE,
Z Fold8, Xiaomi 17, iPhone Air — live und hier unbekannt, also unsichtbar.

**37 Modelle nachgelegt**, jedes aus den zwei Live-Katalogen abgelesen.
Trefferquote danach **84 %** (90 von 107); der Rest sind Tablets, Router,
MiFi und Zubehörbündel, die in diesen Katalog nicht gehören. Google (12
Modelle statt 6) und Xiaomi (14 statt 4) — die zwei von den Fachkollegen
benannten Lücken — sind damit erfasst.

Jede Verwechslungsfalle ist geprüft: `Pixel 11 Pro XL` / `Pixel 11 Pro Fold`
/ `Pixel 11 Pro` / `Pixel 11` lösen auf vier verschiedene Einträge auf,
ebenso `Redmi Note 17 Pro Max` gegen `Redmi Note 17 Pro`. Das ist die
800-Euro-Sägezahn-Falle vom 10.08., jetzt vierfach.

### expert: von „ohne Adapter" auf „gesperrt, mit Begründung"

Am Nuxt-Payload selbst nachgemessen: der Schlüssel
`pricePds/webcode=<nummer>;storeId=<markt>` löst im flachen Referenz-Array
auf **-1** auf, also auf `undefined`. Der Preis wird im Browser nachgeladen,
und der zugehörige Endpunkt liegt unter `/api/` — genau das sperrt expert in
seiner robots.txt. Im Payload stehen nur **Schwesterartikel** mit eigenem
Webcode; ihre Preise ihrem jeweiligen Artikel zuzuordnen ist nicht belegbar,
weil der Webcode der aufgerufenen Seite nicht darunter steht.

---

## G2 — „Wer ist günstiger als Vodafone?"

Die wörtliche Anforderung. Je (Modell, Speicher, Zustand): eigener Preis,
günstigster Wettbewerber **mit Namen**, Differenz absolut und in Prozent,
Zahl der Anbieter darunter, beide Abrufdaten, beide Quelllinks. Der
Aufklapper nennt **alle** Anbieter unter Vodafone.

Vier Regeln tragen die Rechnung (`report/geraete_vergleich.py`):

1. **Kein Vergleich ohne beide Belege** — eine Zeile entsteht nur, wenn
   BEIDE Seiten Quelladresse und Abrufdatum tragen.
2. **Die zwei Preisarten werden nie gegeneinander gerechnet.**
3. **Der Zustand steht im Schlüssel** — sonst schluckt ein
   refurbished-Preis den Neupreis desselben Geräts.
4. **Verglichen werden Läden, nicht Marken.**

Gegen die 218 live gesammelten Listungen: **62 Geräte im Vergleich, bei 19
ist ein Wettbewerber günstiger, größter Abstand 306,90 €.**

---

## G3.3 — der Gesamtexport

`site/exporte/geraete-aktuell.csv` und `geraete-historie.csv`, beim Rendern
erzeugt, auf der Seite verlinkt mit Zeilenzahl und Größe.

**UTF-8 mit BOM, Semikolon, Dezimalkomma** — alle drei für genau einen
Zweck: dass Excel im deutschen Gebietsschema die Datei per Doppelklick
korrekt öffnet. Ohne BOM wird aus „Größe" ein „GrÃ¶ÃŸe", mit Komma getrennt
landet die Zeile in Spalte A, mit Dezimalpunkt liest Excel 1349.90 als Text.

Die **Preisart steht in einer eigenen Spalte**, nicht in der Preisspalte.

---

## G4 — was schon da war, und warum es unsichtbar war

Der Auftrag nennt die Lifecycle-Schwelle und die Karte „Was diese Woche
auffällt" als fehlend. **Beide stehen seit dem 11.08. im Code.** Sie waren
live unsichtbar, weil die Messtermin-Zählung (G0) sie fälschlich
abschaltete. Sie haben jetzt die Tests, die der Auftrag verlangt: jede Zahl
der Wochenkarte ist aus dem Datensatz herleitbar, und die ganze Seite
entsteht ohne einen einzigen ausgehenden Aufruf.

Neu aus G4.3: die Gerätespalte der SKU-Matrix bleibt beim Waagerechtscrollen
stehen. Die Kachel „0 ausgelistet" blendete sich bereits aus.

---

## Drei Fehler, die NUR das Ansehen des Ergebnisses gezeigt hat

Teil C des Auftrags ist keine Formalie. Alle drei waren bei grünen Tests da:

1. **Alle 150 Vodafone-Quelllinks zeigten auf `api.vodafone.de/privat/…`**
   — Adressen, die es nicht gibt. Die Nutzlast nennt den Pfad relativ, der
   Collector löst ihn gegen die Quelle auf, und die ist bei diesem Adapter
   die Schnittstelle. 31 Adapter-Tests waren grün, und jeder zweite Beleg
   der Seite war tot. Gefunden beim Lesen der **exportierten CSV-Tabelle**.
2. **Die Abrufdaten standen im ISO-Format** („2026-08-29") — auf einer
   Seite für Manager ohne Technikhintergrund, in einem Portal, das sonst
   deutsche Daten schreibt. Zweimal: im Seitenkopf und in der Export-Zeile.
3. **„Nur Fachhandel" leerte die Tabelle kommentarlos**, weil an diesem Tag
   nur Netzbetreiber Daten lieferten. Eine leere Fläche ohne Satz liest sich
   als kaputte Seite.

---

## Was OFFEN bleibt — ehrlich beziffert

1. **Das Akzeptanzkriterium „mindestens 8 Anbieter" ist NICHT erreicht.**
   Es liefern vier: freenet/mobilcom-debitel, ALDI TALK, Vodafone, o2 —
   darunter zwei der drei geforderten Netzbetreiber (Vodafone, o2). Die
   Telekom fehlt: sie antwortet httpx mit einer 202-Challenge (TLS-/
   Client-Erkennung), und ihre strukturierten Daten tragen den Gerätepreis
   nur als Zuzahlung ohne Tarifreferenz.
2. **Die Kategorie „gemessen, aber ohne Adapter" ist verkleinert, nicht
   abgeschafft.** expert ist auf „gesperrt mit Begründung" umgestellt;
   otelo, klarmobil, congstar, smartmobil, WinSIM und Blau stehen weiter
   dort — und zwar zu Recht: ihre Bündelpreise MIT Tarifreferenz sind
   baubar (otelos `hardwareEntity[].tariffMap[].singlePaymentFee` ist der
   naheliegendste Einstieg), sie sind nur nicht gebaut. Sie als „gesperrt"
   zu führen wäre falsch.
3. **Medimax und ElectronicPartner:** 20 abgerufene Produktseiten, 0
   Listungen, seit 16 Nächten. Der Rohsatz-Zähler beantwortet beim nächsten
   Nachtlauf, an welcher Stufe es liegt. **Die Messung geht nur im
   Besuchsfenster (02:00–08:00 UTC)** — diese Sitzung lief außerhalb und hat
   die beiden deshalb nicht angefasst.
4. **G3.1 (Preisverlauf-Chart) und G3.2 (Wochenvergleich als eigener
   Zustand) sind nicht gebaut.** Begründung: die Historie hat je Listung
   genau einen Messtag, das Chart würde sich nach seiner eigenen Schwelle
   ausblenden. Der Wochenvergleich existiert als gerechnete Sektion
   (`_auffaellig`) und speist die Wochenkarte bereits; ihn zusätzlich als
   State zu speichern lohnt erst, wenn mehrere Messtage vorliegen.
5. **Die Veröffentlichungsschwelle kippt beim nächsten Nachtlauf auf
   `True`** (4 Anbieter ≥ 3, 6 Hersteller ≥ 2, >20 SKUs). Die Geräteseite
   trägt sich dann selbst in die Navigation ein — ohne Handgriff, wie
   vorgesehen. **Danach ansehen:** die Navigation hat dann sieben Einträge.
6. **Die unbekannten Farbschreibweisen sind gewachsen** (Frost, Canyon,
   Cobalt Violet, Tiefblau, Pistachio, Hibiscus, Wolkenweiß, Lichtgold,
   Himmelblau, Cosmic Orange, …). Sie sind die Arbeitsliste für
   `config/farben.yaml`. Bewusst NICHT in dieser Sitzung nachgetragen: eine
   neue Farbzuordnung ändert die `sku_id`, und der Altbestand würde als
   ausgelistet gelten und neu entstehen — das ist eine Datenwanderung, keine
   Konfigurationszeile. Für G2 spielt es keine Rolle: dort wird je
   (Modell, Speicher) verglichen, nicht je Farbe.
7. **Der Vodafone-Schlüssel ist eine öffentliche Client-Kennung** aus dem
   eigenen Skriptbündel. Wird er gedreht, fällt der Adapter mit 401/403 auf
   und die eine Zeile in `geraete_quellen.yaml` wird aus demselben Bündel
   neu abgelesen.
