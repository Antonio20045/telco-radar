# Kommentarwissen 12-tests-b

Stand: Commit aaa8b0d, 49 Dateien, 1542 Kommentarzeilen.

## Übernahmen in Code
- keine (Testdateien: alle Kommentare tragen Begründung, Messwert oder Geschichte; keine unbenannte Konstante im Test, keine Umbenennung nötig, kein neuer Test hermetisch begründbar).

## Für docs/betrieb.md
- Die Geräteseite rendert täglich (`geraete.yml`, 02:17 UTC), `render_site` bekommt aber als `heute` das Datum des jüngsten RADAR-Berichts (Mi/Fr, `radar.yml`); Frische-Bezug der Geräteseite ist deshalb der spätere von Berichtstag und `updated` des Bündel-Stores. Produktionsbeweis 20.09.2026: Bestand `updated=2026-09-20`, jüngster Bericht 16.09. (Quelle `tests/test_geraete_tco_alterung.py:528`)
- Der Telekom-202-Ausfall in Actions ist dokumentierte Realität; legt o2 allein an, entsteht bei späterem Telekom-Lauf sonst ein zweiter Geräteeintrag (Quelle `tests/test_geraete_autoerkennung.py:658`)
- Im GitHub-Actions-Lauf (`GITHUB_ACTIONS` gesetzt) gibt das Newsletter-Versandskript `::add-mask::` aus (Quelle `tests/test_newsletter_bewegung.py:321`)
- Die Fensterprüfung (Besuchszeit) gilt je Abruf, auch für Nachbearbeitungs-Haken (`loese_tarifnamen`, `ergaenze_buendel`), seit 22.09.2026 (Quelle `tests/test_geraete_besuchsfenster.py:462`)
- Diagnose G0 vom 28.08.2026: mobilcom-debitel wurde am Zeitbudget nie fertig; Teilläufe zählen als Messtermin, nicht als Lauf (Quelle `tests/test_geraete_store.py:602`)
- Der Promo-Ausfall seit 14.08.2026 stand bis 27.08.2026 in keiner Statistik, nur im Actions-Log; seitdem drei Zahlen im Laufprotokoll (Quelle `tests/test_promo_pipeline.py:46`)

## Widersprüche
- keine

## Wissen je Datei

### `tests/test_analyst_budget.py`
- `test_eine_ueberschrittene_schwelle_stoppt_keinen_stapel` (Zeile 62): Die Schwelle gilt als überschritten ab der ersten gezählten Antwort.
- `test_grosse_stapel_sparen_denkspur` (Zeile 112): Das Ausgabebudget trägt Denkspur PLUS Antwort des größeren Stapels.

### `tests/test_browser_konsole.py`
- Abschnittskopf (Zeile 35-46): Es gibt genau einen befreiten Konsolenfall (Netzfehler beim Schriftenpaket); alles andere ist ausdrücklich nicht befreit.
- `test_konsole_sammeln_hoert_beide_kanaele` (Zeile 150-189): Die Verdrahtung ist der Teil, an dem der Reiter-Test blind war. Die Kanalmarke steht im Test, damit ein roter Test nennt, WELCHER Kanal gefeuert hat.

### `tests/test_ctm.py`
- nichts übernommen: nur Abschnittsüberschriften und Kurzhinweise ("ohne Satz", "darf nicht werfen"), die der Testname trägt.

### `tests/test_diff_bilder.py`
- `test_der_fehlversuch_wird_gemerkt_und_nicht_sofort_wiederholt` (Zeile 119): Nach der Frist ist ein zweiter Anlauf erlaubt, weil Redaktionssysteme `og:image` auch nachträglich bekommen.

### `tests/test_differenzierung_view.py`
- `test_store_eintrag_wird_auf_die_kartenform_gebracht` (Zeile 104): Der Store führt als Quelle ein LABEL ("Telkomsel"), die Karte zeigt die Domain aus der URL wie überall sonst.
- `test_why_kommt_aus_why_it_matters` (Zeile 131): Ein Punkt in einer Zahlangabe ist kein Satzende; drei von 51 Bestandssätzen haben genau diese Form.
- `test_jeder_hebel_traegt_zahl_farbe_und_etikett` (Zeile 236): Die Karten oben mischen die Hebel und müssen ihren Hebel selbst benennen.
- Zeile 269-274: Beide Speicher liefern Begründungen, die Vodafone etwas RATEN (Kurator-Prompt fragt "why it matters"); auf der öffentlichen Seite hat das nichts verloren (CLAUDE.md §8, beobachtend statt empfehlend). Die Regel steht in `textwerkzeug.ohne_vodafone_rat`; der Test prüft, dass die Karten sie anwenden.

### `tests/test_editor_themenabschnitt.py`
- `fake_complete` (Zeile 76): Die aktiven Themenfelder stehen namentlich im Prompt, damit der Editor weiß, worüber er den Abschnitt schreibt.

### `tests/test_fruehwarnung.py`
- `test_aktive_fragen_stehen_oben` (Zeile 106): Die zweite Frage muss VOR `fenster_ausgaben` stehen; danach ist die YAML-Liste `fragen` beendet und ein weiterer Eintrag wäre ungültiges YAML.

### `tests/test_geraete_alarme.py`
- nichts übernommen: vier Stufen (kritisch, mittel, gering, bestpreis), Grenze gehört der schärferen Stufe; Prozent-Sortierung (10 %, 25 %) statt Euro; Testnamen tragen es.

### `tests/test_geraete_anbieterzaehlung.py`
- Zeile 40: Das Muster "Zahl + Wort Anbieter" ist aus der Vergleichsansicht vollständig entfernt (O1).
- `test_keine_dropdown_option_nennt_eine_anbieterzahl_mehr` (Zeile 72): E2: der Selektor ist das Suchfeld; wählbar ist, was der Zeitreihen-Knoten als erlaubt trägt. Keine Anbieterzahl im Namen, eindeutige IDs für den Deep-Link.
- `test_der_startzustand_ist_derselbe_im_knoten_und_im_serverblock` (Zeile 106): Der Antwort-Satz nennt das Startgerät beim Kurznamen; der Titel ist "Hersteller Modell Speicher GB", geprüft wird das Modellstück.
- `test_modell_ohne_zeitreihe_steht_ohne_widerspruch_da` (Zeile 124): E2: Ein Modell ohne Bündel-Band ist in der Zeitreihenansicht nicht wählbar (erlaubt leer), hat keinen Graph-Zustand und keine Band-Zeilen. Der Katalog zeigt seine Listungen; die Modell-Liste der Seite kommt mit E3 (S2: Abweichungstabelle).
- Abschnitt (Zeile 137): `zeitreihe()` liefert ihre Reihenzahl als Feld (eine Rechnung, Clean Code 1).

### `tests/test_geraete_autoerkennung.py`
- `_telekom_html` (Zeile 70): Beleg vom 15.09.: das iPhone-Duo, das der Katalog noch nicht kannte.
- `_mini_katalog` (Zeile 95): Die Schälung kennt nur Katalog-Hersteller (nichts geraten); deshalb steht ein Xiaomi-Modell darin.
- `test_beleg_iphone_18_duo_wird_automatisch_angelegt` (Zeile 147-167): ZWEI Einträge: "Pro Max" ist ein eigenes Gerät, kein Modellzusatz des angelegten "Pro" (die `_MODELLZUSATZ`-Sperre hätte beide unter "iPhone 18 Pro" verschmolzen, dieselbe Falle wie "Pixel 10 Pro Fold" gegen "Pixel 10 Pro"). Marker ist das ISO-Datum des anlegenden Laufs. marktstart und vorgaenger bleiben leer (leeres marktstart schaltet die Nachfolger-Analyse ab; ein geratenes Datum wäre schlimmer, Katalogregel). generation nur bei eindeutiger Serie ("iPhone" ist Apple-Serie im Katalog, Zahl 18).
- `test_beleg_listung_traegt_speicher_und_farbe` (Zeile 190): Der Auto-Eintrag kennt die gemessene Speicherstufe; sie ist der Filter, gegen den ein späterer Titel ohne strukturiertes Speicherfeld gelesen wird.
- `test_hand_eintrag_schlaegt_auto` (Zeile 212): Nur das Pro-Gerät steht im Katalog; der Pro Max nicht (wird zu Recht auto-angelegt), sonst würde die Aussage verwässert.
- `test_hersteller_pruefix_wird_geschaelt` (Zeile 263): Serie "iPhone" ist bekannt, Zahl 18; der Name der Variante endet auf "Air", generation bleibt die der Serie.
- `test_wortmarken_kollision_verhindert_die_anlage` (Zeile 292): "iPhone 18 Pro" noch einmal: keine zweite Anlage; die zweite Stufe erweitert die speicher-Liste des Auto-Eintrags.
- `test_hand_schlaegt_auto_beim_laden` (Zeile 369): Der Mensch pflegt dasselbe Gerät von Hand in die Config; Hand gewinnt.
- `test_die_drei_adapter_nennen_ihr_namensfeld` (Zeile 417): o2: Name in `description`, Titel wird mit Speicher und Farbe aus dem Angebots-Slug zusammengesetzt. Vodafone: Name in `modelName` der Detailnutzlast.
- E4-P1 Funk-Anhängsel (Zeile 651-663): o2 schreibt "5G" ins description-Feld ("Xiaomi Redmi Note 17 Pro Max 5G", `tests/fixtures/geraete/o2_katalog.json`); Telekom `name` und Vodafone `modelName` nennen dasselbe Gerät ohne Zusatz. Im selben Lauf schützt die Config-Reihenfolge; der Bruch käme über die nächsten Nächte: legt o2 zuerst/allein an (Telekom-202-Ausfall in Actions ist dokumentierte Realität) und nennt ein späterer strukturierter Anbieter das Gerät ohne Zusatz, entsteht der zweite Eintrag STILL, ohne Signal an die Arbeitsliste. Zwei device_ids für ein Gerät sind die Sägezahn-Klasse, gegen die die ID-Regel gebaut ist.
- `test_funk_anhang_wird_aus_dem_modellnamen_geschaelt` (Zeile 683): Nennung OHNE Zusatz (Telekom-`name`-Schreibweise) bleibt unberührt.
- P5/E3 Tarif-Rauschen (Zeile 837-848): ALDI TALK liefert je Lauf drei Tarifpakete als "Gerät" ("Tarif S", "Tarif M", "Tarif L", quelle microdata). Am 17.09.2026 standen sie als 3 Zeilen mit Häufigkeitssumme 87 von 284 in `data/state/geraete_unbekannt.jsonl` (je 29 Zählungen; der Auftrag nennt "87 von 284 Zeilen" und meint diese Vorkommen). Die Liste ist Frühindikator für Anker-Lücken (FM 1); Rauschen macht sie taub. Alle Titel der Sektion sind die echten gespeicherten vom 17.09., als Fixture `tests/fixtures/geraete/unbekannte_titel_2026-09-17.jsonl` (145 Titel-Zeilen, Herkunft in `_herkunft.json`). Nichts erfunden.
- `test_tarif_titel_erkennen` (Zeile 859): Echte Gerätetitel der Liste bleiben stehen, auch die von ALDI TALK selbst.
- `test_bestaende_werden_beim_naechsten_schreiben_bereinigt` (Zeile 985-1003): Die gezählte Häufigkeit der Rausch-Zeilen (29 je, Summe 87) verhindert ihr Verschwinden nicht; sie war eine Zählung, keine Buchführung.
- `test_ueber_den_ganzen_echten_bestand_vom_17_09` (Zeile 1018-1028): Fixture ist der ganze Bestand; jeder andere Titel bleibt stehen, 142 von 145. Ziffernlose Gerätetitel tragen kein "Tarif" und fallen nicht durch die UND-Regel.
- P5/E3 Familien-Anker (Zeile 1037-1064): Vodafone nennt iPads im strukturierten Namen ohne Hersteller-Präfix (`modelName`: "iPad Pro 11 (2025)", "iPad (2025)", "iPad Pro 11 2024", Stand 17.09.). Serie "iPad" stand in keinem Katalogeintrag, der Serien-Anker griff nie (Anker-Lücke aus auto-doku.md). iPad, Watch und AirPods sind Apple-Serien: der feste Familien-Anker ist Markennamen-Fakt, keine Raterei, und greift nur, wo der Katalog die Reihe nicht kennt (Hand schlägt Auto bleibt). Auto-Regeln unverändert: marktstart und vorgaenger bleiben leer.

### `tests/test_geraete_bereinigung.py`
- `test_das_zustandswort_faellt_auch_aus_der_kanonischen_farbe` (Zeile 111): Fall, an dem die unbedingte Interpunktionsreinigung eine Farbe beschädigt hat, die nie ein Kennzeichen trug; steht so im Livebestand (mobilcom-debitel, Galaxy S25 128 GB).
- `test_der_aktive_eintrag_ueberlebt_den_gealterten` (Zeile 176): Das jüngere Datum liegt absichtlich beim GEALTERTEN, sonst gewänne der aktive Eintrag auch ohne die Statusregel.
- Abschnitt (Zeile 229): Der Schlüssel hat neun Bestandteile, je einer je Test.
- `test_die_kette_haelt_ihre_zwei_zahlen_an_einer_gestellten_lage` (Zeile 520): Zwei Preise für dieselbe Farbe desselben Geräts sind ein Widerspruch mit sich selbst; `pruefe()` wirft ihn als Doppelpreis heraus, beide Hälften, weil der Datensatz nicht sagt, welche stimmt.
- `test_der_zwilling_faellt_und_die_echte_ware_daneben_bleibt` (Zeile 634): Gegenprobe: ohne Zwillingseigenschaft fällt keine Zeile.

### `tests/test_geraete_besuchsfenster.py`
- `hole` (Zeile 115): Jeder Abruf wird mit seiner Wanduhrzeit protokolliert; nur so lässt sich die Regel "kein Abruf außerhalb des Fensters" prüfen statt eines Symptoms.
- `test_fenster_geht_waehrend_des_laufs_zu` (Zeile 208): Gegenprobe zuerst: der Einstieg lag noch im Fenster und wurde geholt; sonst wäre der Test auch bei leerer Fixture grün (CLAUDE.md Regel 10).
- `test_teilweise_gelesen_altert_nur_die_wirklich_gelesene_seite` (Zeile 270): Start 07:30, jeder Seitenabruf kostet 300 s; erster Einstieg (1 + 3 Seiten) fertig um 07:50, mitten im zweiten geht um 08:00 die Tür zu.
- `test_kein_einziger_abruf_verlaesst_das_fenster` (Zeile 407): Gegenproben: es wurde gecrawlt und der Lauf hat das Fenster überdauert.
- Zeile 462-472 (S2-3): Die Nachbearbeitungs-Haken der Adapter (`loese_tarifnamen`, `ergaenze_buendel`) riefen bis zum 22.09.2026 mit dem ROHEN `hole` ab, ohne Disallow, Crawl-delay und Fensterprüfung. Sie laufen nach `sammle()`, wo ein Fenster am ehesten zu ist. Die Zusage "Fensterprüfung gilt je Abruf" (Modulkopf des Collectors, geraete.yml) galt für sie nicht.
- `haken` (Zeile 603): Ohne eigenen Absender bleibt es beim Aufruf ohne.

### `tests/test_geraete_browser_fixture.py`
- `_baue`-Fixture (Zeile 31-95): Drei Modelle, drei Lagen. Vorgabemodell ist das Leitfrage-Gerät (`geraete_tco_karten.LEITFRAGE_MODELL`), sobald es zwei Anbieter hat. Modell A Band Klein: drei Anbieter, Vodafone teuerstes und damit Referenz UNTER den Zeilen (o2/congstar negatives Δ). Modell A Band Mittel: nur congstar, Vodafone fehlt, keine Δ-Angabe. Modell B Band Klein: nur 1&1. Modell C: Bündel in Tarif ohne Datenvolumen, kein Band.
- `_baue` (Zeile 145): Barpreise nur bei zweien Modellen, damit der Test den Leerzustand einer Zahl sieht (Modell C ohne Barpreis).

### `tests/test_geraete_buendel_congstar.py`
- `test_achtunddreissig_saetze_aus_zwei_planvarianten_neun_speichern_zwei_laufzeiten` (Zeile 110): Keine Dublette je (Tarif, Variante, Laufzeit); 4 Geräte mit zusammen 9 Speichergrößen (256/512/1024 kommen bei mehreren Geräten vor).
- `test_jede_ratenform_geht_gegen_die_rohantwort_auf` (Zeile 180): Lookup-Schlüssel ist (Plan, Variante): dieselbe Variante steht in BEIDEN PlanVarianten einer Seite mit verschiedenen Zahlweisen (M subventioniert die Rate stärker als M Flex). Nur über die Variante zu schlüsseln nähme die Zahlweise des letzten Plans.
- Produktseiten-Abschnitt (Zeile 251-259): Die Produktseite trägt die ganze Tarifmatrix (29.09.2026). Fixtures `congstar_produkt_iphone17_20260929.html.gz` und `congstar_produkt_pixel11pro_20260929.html.gz` sind echte Abrufe vom 29.09.2026 (HTTP 200, TelcoRadar/1.0, reiner GET) von /geraete/apple/apple-iphone-17/ und /geraete/google/google-pixel-11-pro/. Bis dahin warf `lies_buendel` auf jeder Produktseite, und congstar lieferte nur die vier Aufmachergeräte der Tarifseiten (10 SKUs).
- `test_die_produktseite_liefert_jeden_tarif_jeden_speicher_jede_laufzeit` (Zeile 300): Jede PlanVariant verlinkt ihr eigenes Pflichtblatt; die Brücke zum Tarifbestand steht an jedem Satz.
- `test_eine_laufzeit_als_zeichenkette_ist_dieselbe_laufzeit` (Zeile 490): Die Laufzeit steht als ZAHL im Satz; `buendel_id` und die Etiketten rechnen mit ihr.
- Zeile 513: PIB-Nummern-Brücke: tarif_slug -> buendel_slug am Bestandssatz.
- `test_adapter_registry_traegt_congstars_buendelhaken` (Zeile 732): Der Tarifname steht in derselben Antwort (prefetchedPlan.variants[].title); congstar braucht anders als Vodafone keinen Haken zur Namensauflösung nach dem Sammeln, derselbe Grund wie bei der Telekom.
- `test_die_konfiguration_liest_buendel_von_den_produktseiten` (Zeile 823): Die Tarifseiten führen nur vier Aufmachergeräte; die Produktseiten decken sie vollständig ab, die Tarifseiten sind keine Einstiege mehr. Der ehrliche Absender ist per Anbieter überschrieben (B2-Muster), sonst gingen die Produktseiten mit der globalen Chrome-Kennung hinaus.

### `tests/test_geraete_buendel_o2_vertiefung.py`
- `test_zwoelf_tarife_zwei_speicher_zwei_laufzeiten` (Zeile 87): Gegenprobe: der alte Stand kannte genau ein Bündel für dieses Gerät.
- `test_abrufe_je_geraet_und_nur_verlinkte_adressen` (Zeile 94): Abrufe je Gerät = 1 Produktseite + 1 Speicher + 2 Laufzeitschalter + 11 Referenztarife.
- `test_iphone_17_pro_256_zwei_tarife_gegen_die_seite` (Zeile 141): 24 Raten: eigene Rate und eigene Anzahlung, derselbe Tarifbetrag.
- `test_tarifabhaengige_rate_verhindert_jede_ableitung` (Zeile 210): Eine Antwort mit anderer Rate, in sich stimmig (Probe geht auf), verhindert die Ableitung.
- `test_plus_wird_nie_auf_den_tarif_ohne_plus_geraten` (Zeile 428): Der Kachel-Slug bleibt der stärkere Weg.
- Abschnitt iPhone 18 Pro (Zeile 330-364): TB, Tracking; die Preiszusammenfassung schlägt den Trackingblock.

### `tests/test_geraete_collect.py`
- `test_ausverkauft_ist_keine_auslistung` (Zeile 200): Teil F: Eine Verfügbarkeitsstufe ist kein Portfolio-Ende; das Wort "ausgelistet" darf aus einer einzelnen Seite gar nicht entstehen.
- `hole` (Zeile 552): Eine lesbare Kategorieseite, von deren Produkten keins lesbar war, gilt NICHT als vollständig gelesen.
- `test_sammle_geht_alle_anbieter_durch_und_meldet_jeden` (Zeile 683): Kein Anbieter fällt stillschweigend weg; jeder nicht gelaufene nennt einen Grund (Akzeptanzkriterium Teil E).
- Befunde des Reviews vom 10.08.2026 (Zeile 691-733): abgeschnittene Seite gilt nicht als gelesen; der Deckel meldet sich (keine stille Kappung, CLAUDE.md §6); ein gedeckelter Anbieter heißt nicht "kein Einstieg lesbar" (nichts darf altern); "kein Einstieg lesbar" bleibt für den echten Ausfall (404); unter dem Deckel gilt die Seite weiter als gelesen (die Sperre darf den Normalfall nicht lahmlegen).
- Zeile 779-898: Das Zeitbudget ist keine gemeinsame Weide (Diagnose G0 vom 28.08.2026). Testfall: jeder Abruf kostet 30 s; 240 s für vier Anbieter reichen nicht für alle, aber die ersten müssen etwas bekommen, nicht null.

### `tests/test_geraete_export_mobil_browser.py`
- `test_der_kicker_bricht_auf_dem_telefon_nicht_um` (Zeile 260): Das Datum endet rechtsbündig an derselben Kante wie der Kopf (Grid-Spalte, `justify-self:end`); es steht UNTER der Schlagzeile, nicht mehr am Flex-Grund neben dem Text-Block.

### `tests/test_geraete_karten_band_browser.py`
- `_tarif` (Zeile 160): A1: Liegt eine Preisphase vor, rechnet die Leitzahl PHASENGEWICHTET und ignoriert `tarif_monatlich` des Bündels; deshalb trägt jede Phase denselben Betrag wie ihr Bündel-Tarif, sonst wäre jede Zahl der Fixture nur über die Phase erklärbar.
- `_baue` (Zeile 193-240): congstar und 1&1 haben KEINE Listung; congstars Gerätepreis kann nur aus Zuzahlung + Raten kommen (der TCO-1-Fall). 36 Monate Raten: Finanzierungssumme 1,00 + 36 x 25,00 = 901,00 EUR; Kosten über 24 Monate (A1, alle Raten der eigenen Laufzeit) = 1 + 24x24 + 36x25 = 1.477,00 EUR. Tarif steht nicht in tarife.jsonl: kein Datenvolumen, kein Band. "Unbegrenzt" liegt außerhalb aller Bänder (§7); json schreibt dafür Infinity wie der echte Tarifbestand.
- `test_die_zeilenliste_aendert_sich_bei_bandwechsel` (Zeile 326): congstar führt nur ein Mittel-Band-Bündel; in Klein gehört es nicht in die Auswahl.
- Aufträge 1 bis 4 (Zeile 314-533): Auftrag 2 Bandwahl filtert die Kartenansicht; Auftrag 1 Karten ohne Band als eigene, klar markierte Gruppe; Auftrag 3 TCO-24 ohne Hover, Desktop und Mobil; Auftrag 4 congstar trennt Finanzierungssumme und Gerätepreis (§3).
- `test_die_tco_werte_des_bands_stehen_ohne_hover_im_dom` (Zeile 433): Vodafone 1 + 24x26,99 + 24x15 = 1.008,76; congstar (A1, 36 Raten) 1 + 24x24 + 36x25 = 1.477,00.
- `test_der_antwort_satz_nennt_die_zahl_der_guenstigsten_zeile` (Zeile 454): Der ERSTE Betrag nach dem ersten Doppelpunkt ist die Leitzahl des Satzes; der Satzanfang nennt Gerät und Band und enthält selbst Ziffern ("iPhone 17 Pro 256 GB"), die keine Betragsparser füttern dürfen.
- `test_die_finanzierungssumme_heisst_so_und_nicht_geraetepreis` (Zeile 501-533): Der Rechenweg steht im geschlossenen Aufklapper; innerText zeigt ihn nur bei offener Zeile (Transitivität der `<details>`-Regel). Die Spalte heißt die Zahl Finanzierung (1,00 € Zuzahlung + 36 x 25,00 € Raten), nicht "Gerätepreis"; die Zeile behauptet keinen reinen Gerätepreis ohne Vertrag, die Lücke steht im Rechenweg. Die Leitzahl ("Kosten über 24 Monate", alle 36 Raten) bleibt die zweite, getrennte Zahl (1.477,00).
- `test_ein_gemessener_barpreis_fuehrt_weiter_als_geraetepreis` (Zeile 551): Ein gemessener Barpreis steht ohne Finanzierungs-Etikett in der Spalte; nur die tarifabhängige Summe heißt Finanzierung.
- Zeile 574: Randnotiz aus der Audit-Gegenprobe: doppelt-escapte Tooltips heilen.
- `test_der_graph_traegt_keine_tooltips_mehr` (Zeile 591): Mit Historie zeigt auch das SVG gedruckte Werte; ohne Historie (diese Fixture) trägt der Antwort-Satz sie allein.

### `tests/test_geraete_katalog_modelle.py`
- `_karte` (Zeile 110-131): `leitzahl_monate` ist der ZEITRAUM, den `gesamt` trägt (P0-B-h1); jede echte Karte aus `geraete_tco_karten.modelle()` trägt ihn, die TCO-Spalte des Katalogs filtert darauf (P0-B-h2). Die TARIFLAUFZEIT der Rechnung ist auf jeder echten Karte 24 (`geraete_tco_karten.LAUFZEIT`), nicht der Zeitraum der Leitzahl; `_delta_faellig` liest sie aus der EINEN Definition.
- Zeile 141: DIE EINE REGEL: keine Modellzeile ohne Preisform.
- `test_eine_zeile_je_modell_mit_ab_preis_und_beleg` (Zeile 170-182): Anderer Speicher = zweite Zeile; je Anbieter das Minimum (A: 1000, B: 990), dann Gesamt-Minimum; der Aufklapper trägt alle vier Listungen des Modells.
- `test_refurbished_stellt_keinen_ab_preis_b1` (Zeile 203): Die erneuerte Zeile bleibt im Aufklapper, mit Etikett.
- `test_nur_im_buendel_statt_ohne_preis` (Zeile 225): Die Listungs-Zeile im Aufklapper trägt dieselbe Angabe; "ohne Preis" existiert auf dieser Ebene nicht mehr.
- `test_unlesbarer_store_fraegt_die_listungen_ab_s2_1` (Zeile 309): Mit Barpreis kein Fallback und kein Satz (eine Listung MIT Preis ist kein Bündel-Hinweis); "nur im Bündel" statt "ohne Preis", mit dem Beleg DER LISTUNG.
- `test_tco_felder_waehlen_das_beste_vergleichbare_angebot` (Zeile 402-438): Billiger, aber ERNEUERT darf nicht gewinnen (B1). A2-Nachbesserung, Prüf-Befund 20.09.2026: Gewann das EIGENE Bündel das Minimum der Zeile, behauptete die Delta-Zelle "keine Referenz", obwohl die TCO-Zelle "bei Vodafone" sagte. 20 von 48 "keine Referenz"-Zeilen des Bestands waren eigene Marktführung, kein Referenzmangel (Galaxy A57 256: Vodafone 1.199,80 EUR vor 1&1 1.207,54 EUR, Abstand +7,74 als Annäherung).
- `test_unser_angebot_fuehrt_der_delta_traegt_der_wettbewerber` (Zeile 448-466): Das eigene Bündel IST die Referenz (`_delta` liefert None, B4), stellt aber die Leitzahl der Zeile; der Abstand der Zelle gehört dem günstigsten FREMDEN Angebot.
- `test_wettbewerber_mit_anderer_laufzeit_wird_benannt_statt_still` (Zeile 542-567): 1&1 nennt EINEN Monatsbetrag für Tarif und Gerät über 36 Monate; die Karte trägt deshalb 36 und bekommt von `_delta` keinen Betrag. Leitzahl bleibt die 24-Monats-Zahl des eigenen Angebots; die Zelle ist nicht stumm.
- `test_gegenprobe_die_24_monats_karte_stellt_die_spalte` (Zeile 631): Die kleinere Summe trägt 36 Monate, ist keine Zahl dieser Spalte und darf ihr Minimum nicht stellen.
- `test_alte_referenz_traegt_ihren_eigenen_grund` (Zeile 682): Die Näherung ist nur frisch, wenn BEIDE Belege frisch sind; hier beide vom 01.08., Bestand vom 17.09.
- `test_tco_leerzustaende_benannt` (Zeile 719): Apple: Bündel da, aber keine vergleichbare Karte (nur erneuert). Pixel: gar kein Bündel. Samsung: gesund.
- `test_modell_barpreis_csv_eine_preisform_je_zeile` (Zeile 800): Niemals beide Preisformen in EINER Zeile.
- `test_modell_tco_csv_traegt_den_grund_statt_einer_luecke` (Zeile 819): Klartext wie auf der Seite (S4-1): Chip der Vergleichsansicht sagt "XS", nicht "xs"; zwei Sprachen für dieselbe Sache wären der O4-Befund wieder.
- `test_modell_tco_csv_nennt_den_delta_leergrund` (Zeile 859): Lücke ohne Wettbewerb: Leitzahl da, Abstand ohne Etikett wäre stumm; der Grund heißt beim Wettbewerb, nicht bei der Referenz.

### `tests/test_geraete_laufzeit_filter.py`
- `_baue` (Zeile 183): P3-E1: Die Testleiter (XS 5 / M 36 / L 85 GB) legt 15 GB in XS.
- `seite` (Zeile 259): Sichtbarkeit wird im Browser GEMESSEN (Boxhöhe), nicht am Attribut (CLAUDE.md, Tests und Abnahme).
- `test_der_trade_in_steht_neben_der_leitzahl_und_im_rechenweg` (Zeile 320): Die Leitzahl ist die ohne Eintausch: 1 + 24 x 41,25 + 24 x 24; die 36-Monats-Zeile ohne Aktion trägt keinen Überhang.
- `test_jede_wahl_zeigt_je_angebot_genau_eine_zeile` (Zeile 64): je Wahl und Angebot genau EINE Zeile.

### `tests/test_geraete_preis_mehrdeutig.py`
- nichts übernommen: Regel (derselbe Preis zweimal; Messlücke statt gezeichneter Kurve; Gegenprobe ohne zweiten Preis je Tag) steht in den Testnamen.

### `tests/test_geraete_radar_tafel.py`
- Fixture (Zeile 40-44): Feste Fälle je Zeile (sku, hersteller, modell, speicher): VF + o2 klein vergleichbar; nur o2: kein VF-TCO-24; VF klein, o2 groß: Mismatch.
- `satz` (Zeile 75): P3-E1: Testleiter XS/M/L (5/36/85 GB) legt die Stufen dorthin, wo die alten Bänder lagen (XS 10/18 GB, L 100 GB).
- `_katalog` (Zeile 169): Die generischen Geräte reißen den Deckel der Modellliste; ihre Zahl hängt am Modulwert, nicht an einer abgeschriebenen Konstante (wie `SICHTBAR_MAX` in test_geraete_reiter_browser).
- `test_drei_sektionen_in_folge_jede_mit_ihrem_satz` (Zeile 375-402): S3: drei gleichwertige Sektionen, jede erklärt in einem Satz ihre Frage. Stand 28.09.2026: erst "Mit Tarif" (die Leitzahl darüber stammt aus dieser Liste), dann die drei Barpreis-Sektionen "Ohne Vertrag", dieselben Begriffe wie die Reiter.
- Zeile 409: P4/D1 (STRATEGIE_GERAETE_V3, 18.09.2026): Grafik, Legende, Rot-Deckel.
- `test_die_radar_tafel_traegt_eine_balkengrafik` (Zeile 431): Ein Balken trägt beide Zahlen selbst (Wert an der Spitze); der `<title>` nennt beide Preise der Messung (Nachprüfbarkeit).
- `test_die_haendler_sektion_sagt_was_sie_misst` (Zeile 519): Händler steht mit Namen und Abweichung da; dieselbe %-Logik, nie gegen eine TCO gerechnet.
- `test_der_tafelkopf_polt_nur_die_sektionen_mit_vorzeichen` (Zeile 567-576): Pauschalbehauptung "mit Vorzeichen" für alle drei ist weg; Alarme sind als BETRAG benannt. P4/D4 (18.09.2026) hat den Kopf von drei Sätzen auf EINEN gestrafft (Falz-Regel: vor dem ersten Datenelement höchstens ein Satz; die Leitzahl darüber sagt die Richtung ohne Worte). Der Test hält die AUSSAGE, nicht den Wortlaut. Alarmtabelle zeigt Beträge: jede sichtbare Prozentzahl ist positiv (Wettbewerber günstiger).
- `test_die_modellliste_sortiert_nach_robwerten` (Zeile 586-644): S2: die Abweichungstabelle IST die Modell-Liste. Prozent-ROHWERT trägt den Punkt, die ZELLE das deutsche Komma (Zelle formatiert, Rohwert sortiert).
- `test_je_modellzeile_ein_sprung_in_den_graphen` (Zeile 663): Eine vergleichbare Zeile nennt ihr Band; der Graph springt direkt in das Band, in dem das Paar gerechnet wurde.
- `test_die_detailzeile_zeigt_alle_anbieter_der_gruppe` (Zeile 698): Nur Zeilen MIT td zählen; der html.parser setzt die thead-Zeile der Tabelle-in-Zelle neben den tbody (Browser-Test deckt das DOM).
- `test_die_leitzahl_der_uebersicht_liest_sich_wie_die_balken` (Zeile 785-792): Gegenprobe: Fixture hat echten Abstand, sonst prüft der Vorzeichenvergleich nichts. Dieselbe Zahl steht in der Quellzeile darunter; das Wort zur Zahl kommt aus derselben Differenz.
- `test_die_balken_tragen_das_vorzeichen_der_seite` (Zeile 846): Richtung und Vorzeichen aus derselben Größe: negative Werte links der Vodafone-Linie (Anker am Ende), positive rechts.

### `tests/test_geraete_rahmen.py`
- Zeile 26: Wortlaut wie im Auftrag (BRIEF_RAHMEN, Kriterium 1); die typografischen Anführungszeichen sind Absicht, ein glatter Apostroph träfe den Satz im Repo nicht.
- `test_wie_gerechnet_ist_weg_so_gerechnet_steht_genau_einmal` (Zeile 96): Die alte seitenweite Aufklappung bleibt verboten.
- `test_die_buendel_stehen_als_zeilen_unter_dem_graphen` (Zeile 134-151): E2: Tabelle hängt am eigenen Abschnitt, nicht mehr am Modellblock-Div (mit der Zeitreihe gefallen). Keine Zähler in der Tabellenüberschrift: eine Klammer, die anders zählt als der Bestand darunter, bleibt verboten (O1-Regel; der Modellname mit seiner GB-Zahl ist kein Zähler).
- Kriterium 2 (Zeile 159): Händler als benannte Lücke. Kriterium 3 (Zeile 195-204): Seitenüberschrift. BRIEF_FADEN (05.09.2026, PM/Seneca): Die Frage-Überschrift aus BRIEF_RAHMEN ist gescheitert (Antonio: "Digga, spinnst du?" - flapsig, "ich" mehrdeutig) und wich der sachlichen "Gerätepreise im Vergleich". Seit 28.09.2026 nur noch "Gerätepreise", weil "Vergleich" zugleich Name eines Reiters war (Antonio fand keinen roten Faden). Der Test hielt bis dahin die ältere Entscheidung fest, jetzt die neuere (CLAUDE.md §6: eine falsche Vorgabe kassiert).

### `tests/test_geraete_seite.py`
- Veröffentlichungsschwelle (Zeile 36-45, 1374-1380): Ab der Schwelle beantwortet die Seite ihre Frage ("was bieten die Wettbewerber an, und was kostet es?") und gehört in die Navigation. Die Zahlen stehen seit 11.08.2026 im MODUL; eine Schwelle, die nur ein Test kennt, kann keine Navigation schalten (die Seite war live, vollständig und unauffindbar, weil das Eintragen Handarbeit blieb). Test importiert sie und prüft BEIDE Zweige; Fixtures leiten die Zahl der Läden aus der Konstante ab.
- Zeile 101: Zwei Marken, EIN Laden: der Fall, wegen dem es `shop`/`anzeige` gibt; ohne ihn wäre der Pfad nur über die Identitätsabbildung getestet.
- Fixture Zwilling und Doppelpreis (Zeile 230-284, 31.08.2026): Ohne die zwei Fälle ist `bereinige(sichtbar)` zeilengleich `bereinige(pruefe(sichtbar))`, und jeder Test über den Unterschied der Mengen ist grün ohne zu prüfen. Daran scheiterte `test_der_export_zeigt_genau_den_bestand_der_seite`: Prüfer konnte `aufbereiten()` auf den Rohbestand zurückdrehen, 2190 Tests blieben grün. (1) ZWILLINGSPAAR, echter Fall: o2 nimmt das Zustandswort aus der Farbe, `sku_id` ändert sich, Store legt neu an und altert die alte Zeile; beide sichtbar, gleicher Preis, gleiche Adresse; die gealterte trägt den falschen Store-Zustand "neu" und ginge als Neupreis in Vergleich und CSV. `bereinige()` fasst das Paar in BEIDEN Mengen zusammen. (2) DOPPELPREIS, echter Fall: o2 führt das Galaxy S26 FE 128 GB als "pistachio" (811,00) und "pistachio bk" (667,00); `farbschluessel()` erkennt das Kürzel, `pruefe()` wirft die GANZE Gruppe aus den Preisaussagen. Beide Listungen stehen im Bestand und fehlen in `belastbar`; der Unterschied der zwei Mengen ist genau zwei Zeilen groß, hier wie im echten Bestand.
- Zeile 307: Die drei Mengen der Fixture stehen ALS ERWARTUNG ausgeschrieben, nicht mit `bereinige()`/`pruefe()` nachgerechnet (sonst grün, wenn beide falsch).
- `_modell_schluessel_fixture` (Zeile 384): Dünner Bestand: seit gestern gelistet, EIN Lauf. Der Normalfall `_DB` ist seit 11.08.2026 kein dünner Fall (läuft seit 01.07., vier Läufe, belastbare Verweildauer).
- `test_der_notzustand_traegt_dieselben_schluessel_wie_der_normalfall` (Zeile 529): Drei erlaubte Abweichungen: `export` setzt erst `render_site` nach, `fehler` nur im Notzustand, `pruefung`/`pruefbefunde` nur im Normalfall.
- `test_die_fixture_loest_beide_stufen_wirklich_aus` (Zeile 622-628): Ausgeschriebene Erwartungen treffen die gerechneten Mengen, sonst ist jede Zahl falsch. Zwilling wird ZUSAMMENGEFASST, nicht gelöscht: überlebende Zeile trägt früheres `first_seen` und richtigen Zustand.
- `test_der_export_zeigt_genau_den_bestand_der_seite` (Zeile 674-706): Seite zeigt den Markt auf MODELL-Ebene (P3): Katalog eine Zeile je (Gerät, Speicher), Export eine je Listung; zusammengehalten über die Zahl der Listungen je Modellzeile (Summe = Zeilenzahl der Datei). Bis P3 stand dort `len(.gr-k-zeile) == len(gefuehrt)`. Die zweite Datei führt keine Kurve zu einer Listung, die in der ersten fehlt.
- `test_jede_zahl_fuer_den_bestand_ist_dieselbe_zahl` (Zeile 739-765): Ebene LISTUNG: Export-Knopf. Ebene MODELL: Rubrik-Zahl, DOM-Zeilen, Aufklapper-Anzahl (paarweise `gr-a-rest`, wandern bei Sortierung zusammen). Der "alle N Zeilen zeigen"-Knopf bezieht sich auf die Gesamtzahl der Modellzeilen gegen `KATALOG_SICHTBAR` (seit P3 ohne Block-Deckel, `BLOCK_SICHTBAR` entfallen); diese Fixture liegt mit fünf Modellen darunter, der Knopf darf nicht stehen. Über-Deckel-Zweig: `test_geraete_reiter_browser.py::test_b3_alle_anzeigen_liefert_...` (28 Modelle der B5-Fixture).
- `test_kennzahlen_stimmen_mit_den_daten_ueberein` (Zeile 795-814): Summe der vier Kacheln IST die Zahl der verglichenen Geräte. Betriebszahlensatz am Fuß fiel am 03.09.2026 von der Seite (Antonio: keine Erklärkommentare auf der Geräteseite); Bestandszahlen stehen nur noch in der Aufbereitung und rechnen auf dem BESTAND, nicht Rohbestand (gealterte Zwillingshälfte mit eigener `sku_id` zählte sonst als zweite Variante). Kachelsumme kann nie über dem Bestand liegen (Fehlertyp S3: "2454 Modelle").
- `test_modellzeilen_halten_alle_listungen_eines_geraets_im_aufklapper` (Zeile 940-964): `_katalog_zeile_schluessel` bevorzugt "neu" INNERHALB desselben Anbieters unabhängig vom Preis (C-neu/850 vor C-refurbished/799); dieselbe Regel ordnete bis P3 die sichtbaren Blöcke, jetzt den Aufklapper; danach Betrag aufsteigend, günstigster Händler zuerst; Zustand ist der führende Schlüssel.
- `test_modellzeilen_ordnen_nach_segment_nicht_nach_roher_generation` (Zeile 1002): Im selben Segment (flagship) zählt die Generation: S26 Ultra vor S25 Ultra.
- `test_der_katalog_ist_eine_tabelle_auf_modellebene` (Zeile 1127-1187): Kind-Selektor, weil Aufklapper-Tabellen im SELBEN tbody liegen (Nachfahren-Selektor zählte ihre Köpfe mit); Leitzahl-Etikett bricht in zwei Zeilen ("Kosten über / 24 Monate"), gezählt wird normalisierter Text. Eine Zeile je MODELL des BESTANDS: ausgelistete Bestände bleiben per Design in der Datenbank, gehören nicht ins Regal; gealterte Zwillingshälfte zählt nicht; gezählt gegen `_modell_schluessel_fixture()`. Jede Modellzeile trägt Modellname und eine PREIS-DARSTELLUNG ("ab"-Preis mit Abrufdatum, Bündel-Zustand oder benannter Leerzustand; refurbished-Zeile des iPhone 16 Pro Max 512 bleibt als einzige übrig, B1: kein "ab" aus Gebraucht-Preisen, ohne Bündelstore "kein Preis gemessen"). Zu jeder Modellzeile genau EIN Aufklapper (paarweise `gr-a-rest`, gemeinsames `data-auf`). Alte Matrix und flache Listungs-Haupttabelle stehen nicht mehr auf der Seite.
- `test_eine_unbekannte_verfuegbarkeit_ist_kein_alarm` (Zeile 1216): Gegenprobe: belegte Verfügbarkeit bleibt Pille mit Wort (lieferbar), die Stille trifft nur die Lücke.
- `test_jeder_nicht_angebundene_anbieter_nennt_seinen_grund` (Zeile 1281): Gegenprobe gegen leere Schleife.
- `test_zahlen_im_text_liest_deutsche_und_englische_schreibweise` (Zeile 1318): Seite formatiert mit Punkt, deutscher Fließtext schreibt Komma.
- `test_kein_satz_der_karte_nennt_eine_ungedeckte_zahl` (Zeile 1361): Zahlen der Eigennamen gehören dazu, sonst prüft der Test nur, ob Modellnamen Ziffern enthalten.
- `test_unter_der_schwelle_steht_die_seite_nicht_in_der_navigation` (Zeile 1429): Gegenprobe, dass der Fall wirklich UNTER der Schwelle liegt.
- `_punkt` (Zeile 1553): `device_id` und `shop` sind seit 11.08.2026 Aggregations- und Bandschlüssel; ohne sie fielen alle Testpunkte zu EINEM zusammen.
- `test_alte_preisbewegung_steht_nicht_unter_diese_woche` (Zeile 1581-1599): Nur der Abschnitt "Was diese Woche auffällt". Bis 28.08.2026 suchte der Test im GESAMTEN Seitentext; seit die Seite eine Vergleichssektion mit "günstiger" in der Überschrift hat, hätte er ohne alte Preisbewegung angeschlagen. Gegenstand gleich, Zielscheibe jetzt richtig.
- Befunde des dritten Reviews 11.08.2026 (Zeile 1738-1784): `_hat_echte_null`: negativer Lookbehind auf Ziffer ("20 Tage" hat vor der 0 eine 2); Klasse war im CSS angelegt und kam im HTML NULL Mal vor; Testbestand enthält "20 Tage" (Nachfolger-Hinweis), die alte Teilkettensuche fiele hier durch; echte Null-Zeile muss weiter auffallen; die zwei Textfehler von damals kommen nicht zurück.
- `test_ohne_vorlauf_sagt_die_wochenkarte_was_sie_zeigt` (Zeile 1795-1841): EIN Messtag, Listungen erstmals an diesem Tag gesehen, sonst gäbe es Vorlauf. Die Kachel "0 ausgelistet" fiel am 03.09.2026 mit der ganzen Betriebszahlen-Sektion von der Seite. Eine Ersatz-Assertion gegen die Wochenkarten-Sätze wurde bewusst NICHT gebaut: kein Satztemplate dieses Abschnitts (geraete_view, Sätze 542-623) kann das Wort "ausgelistet" tragen; ein Test, der nie schlagen kann, prüft nichts (CLAUDE.md 6).
- G2 "Wer ist günstiger als Vodafone?" (Zeile 1873-2004): `_db_mit_vergleich`: Vodafone ist der günstigste, die Zeile bleibt trotzdem stehen; ein Gerät, das Vodafone gar nicht führt. `.gr-a-datum`, nicht `.gr-a-klein` (zweite Klasse trägt auch die Speichergröße, Zusicherung war wirkungslos). Aufklapper trägt BEIDE Seiten. LADENnamen, nicht Markennamen (Testkonfiguration führt ElectronicPartner unter `shop: ep`; sonst zählte derselbe Shop unter zwei Marken doppelt als "günstiger"). Gegenprobe: es MUSS ein Gerät geben, bei dem niemand unterbietet.
- G4 Wochenkarte (Zeile 2102-2180, 29.08.2026): rechnet, erzählt nicht. `test_jede_zahl_der_wochenkarte_steht_so_im_datensatz`: belegbare Preise, Deltas, Anzahlen; Zählwerte höchstens so viele wie Listungen/Punkte; geprüft werden MESSWERTE (mit Einheit Euro oder als Zählwert vor Substantiv), nicht jede Ziffer ("iPhone 16 Pro Max" trägt eine 16 zum Namen). P4/2a: Wochenkarte steht im Reiter PREISVERLAUF (bis P4 auf dem Radar), Tafeln auf der Geräteseite; geprüft wird beides. W1.1: Preisgrafik zeigt nur Neugeräte.
- `test_die_pruefung_schaltet_die_navigation_nicht` (Zeile 2221): DIESELBE Farbe: seit 30.08.2026 ist nur das ein Doppelpreis; weite Spanne über verschiedene Farben ist der Markt.
- `test_der_pruefbericht_nennt_dieselben_zahlen_wie_die_pruefung` (Zeile 2251): Zweite Befundart, damit die Vorlage nicht nur ihren ersten Zweig zeigt; der `zustand_veraltet`-Fall hat weder `preise` noch `median` und lief bis zum Review in den Ausreißer-Zweig mit Jinja-Fehler, der die ganze Seite riss.
- `test_die_katalogzeile_nennt_den_ABGELEITETEN_zustand` (Zeile 2307-2348): Echter o2-Fall: Kennzeichen steht NUR in der Farbe, Store trägt weiter "neu". Gefiltert auf Zeilen MIT Zellen (html.parser hängt die Kopfzeile des Aufklappers an denselben Selektor, sonst Crash auf der th-Zeile). Das Wort steht nicht mehr zusätzlich in der Farbe; dieselbe Aussage zweimal, einmal an falscher Stelle, war der Anlass für `geraete_bereinigung`.
- `test_keine_geraetezahl_auf_der_seite_ist_groesser_als_der_bestand` (Zeile 2381-2437): Fixture muss mehr Vergleichszeilen als Geräte erzeugen (ein Gerät mit zwei Speichergrößen). ERSTLAUF statt Normalfall: Betriebszahlensatz am Fuß ("59 Geräte in 250 Varianten") fiel am 03.09.2026 von der Seite; lebender Ort der Gerätezahl ist die Wochenkarte ("wurden N Geräte erstmals erfasst"), die nur ohne früheren Stand entsteht. Gegenprobe: Fixture muss die Abschnitte wirklich rendern (zweiter Fall stand in "62 Geräte im Vergleich"). O3: Scan liest Radar und Geräteseite.
- `test_jeder_anbieter_steht_in_genau_einem_von_drei_zustaenden` (Zeile 2474): Gezählt über die KONFIGURIERTEN; ein nur noch in der Datenbank stehender (umbenannt, entfernt) Anbieter steht in `zeilen`, gehört nicht in die Summe, sonst bräche die Invariante beim Umbenennen. Gegenprobe: Fixture besetzt mehr als einen Zustand.
- Nachbesserung 30.08.2026 (Zeile 2530, "Durchklicken der Live-Seite"): `test_zwei_zahlen_nebeneinander_tragen_ein_trennzeichen`: `get_text()` OHNE Trenner ist die Browser-Zeichenkette; mit " " ist der Test blind. `test_die_portfolio_zeile_nennt_generationen_und_modelle_getrennt`: Vorlage muss Zahlen aus dem Modell nehmen. `test_der_alarmreiter_traegt_keine_verfuegbarkeitsspalte`: Zellenzahl muss zur Kopfzeile passen (Spalte aus Kopf nehmen, Zelle stehen lassen verschiebt jede Zeile). Katalog behält die Auskunft seit P3 im Zeilen-Aufklapper unter "Bestand" (Hauptzeile fasst Anbieter zusammen; Lieferauskunft ist Eigenschaft der EINZELNEN Listung), ein Wort je Zustand.
- `test_ein_zustand_hat_auf_der_ganzen_seite_ein_wort` (Zeile 2730-2744): Normalfall der Fixture ist "lieferbar" (dann keine Pille, Test bewiese nichts). 1) Unbekannte Verfügbarkeit ist kein WORT mehr. 2) Jede Verfügbarkeits-Pille trägt EIN bekanntes Wort; die ZUSTANDS-Pille "neu" ist andere Spalte (--bestpreis/--mittel, nicht --gering/--kritisch/--unklar).
- `test_die_spaltenkoepfe_sind_sortierbar` (Zeile 2780-2812): O2: Alarm-Tabelle auf dem Radar, Katalog auf der Geräteseite. LEER ist so schlecht wie fehlend: `parseFloat("")` ist NaN, Sortierung schiebt NaN absteigend ans Ende, aufsteigend an den ANFANG. Radar kennt keine benannten Leerzustände, dort harter Wert-Assert. Katalog: Zellklassen `gr-sp--barpreis`/`gr-sp--tco`; dritte Barpreis-Zelle ist die Spanne, ersten drei TCO-Zellen TCO-24 / Ø €/Monat / Delta.
- Vorlauf (Zeile 2853-2990): Normalfall der Fixture misst seit 01.07. bis 11.08. = 41 Tage (über der Schwelle, Tabelle kehrt zurück). Kurzer Vorlauf: zwei Messtage eine Woche auseinander mit echter Preisbewegung, Vergleichsstand vorhanden aber kurz; Bewegungsteil in EINEM Satz statt Aufzählung; eine Auslistung darf daneben stehen (stärkstes Signal, unabhängig von Messdauer). Gegenprobe: Fixture muss wirklich in diesen Zweig fallen.
- P3 Nachfolger (Zeile 2998-3035, 31.08.2026, nach Runde 1 der Zurückweisung): "Was der Nachfolger mit dem Preis macht": Hinweis bei leerer Sektion, Verweildauer-Spalte sonst, Zeilendeckel gegen 3000-px-Grenze. `analyze/geraete_lifecycle.py` bewusst nicht angefasst (Parallelpaket liefert `anbieter`, `zustand`, `verweildauer_tage`, `verweildauer_untergrenze`, `noch_gelistet`, `beobachtet_seit`, `zuletzt_bestaetigt` je Zeile). Die alte, falsche Begründung des Leer-Hinweises darf nicht wiederkommen. h4, nicht h3: seit E3 Schritt 3 ist der Lifecycle-Sektionstitel die summary des zugeklappten Aufklappers, Unterlisten eine Ebene tiefer; `#tafel-radar h3.gr-unter` gehören den drei S3-Sektionen (test_geraete_radar_tafel zählt sie).
- `test_b2_spalte_zeigt_gemessenen_anteil_und_kollidiert_nicht_mit_verweildauer` (Zeile 3245-3270): Anbieter steht in eigener Spalte (nicht doppelt im Text der letzten Zelle); "Verweildauer" darf in dieser Tabelle nirgends stehen, nur in der Liste "Verweildauer im Regal" darüber.
- `test_die_zustandsspalte_erscheint_nur_bei_mehr_als_einem_zustand` (Zeile 3281): Fall 1 alle Zeilen "neu": keine Spalte.
- `test_b4_die_tabelle_bleibt_unter_der_hoehengrenze_bei_vielen_zeilen` (Zeile 3338-3448): Mehr als jeder bisherige `LIFECYCLE_SICHTBAR`-Wert; `NACHFOLGER_SICHTBAR = 0`: keine sichtbare Tabelle oberhalb des Aufklappers, nur EINE im Aufklapper. Zahlenregel (30.08.2026-Vorfall): zwei Zahlen ohne Zeichen dazwischen lesen sich im Browser als EINE, geprüft OHNE Trenner; "22241" wäre die verschmolzene Form.
- `_ohne_die_neuen_felder` (Zeile 3487): Fehlt der Anbieterwert, steht ein Gedankenstrich, nicht leerer Inhalt oder Ausnahme. `_kaputte_felder` (Zeile 3524): `marktstart=None` durchläuft den Datumsfilter nicht (kein Datum hinter "Test B").
- Preisform an der Zahl (Zeile 3531-3565, 03.09.2026): `test_ein_ratengesamtbetrag_wird_auf_der_seite_als_solcher_gezeigt`; ein Barpreis bekommt den Zusatz NICHT (Bestand trägt vier Händlerzeilen ohne Ratenfelder).

### `tests/test_geraete_sichtbarkeit_p5.py`
- Zeile 39: Dasselbe Auto-Eintrag-Format wie in test_geraete_zeitreihe_ansicht: State, nicht Config (Produktionsweg der E4-Auto-Erkennung).
- `_baue_buendel_modell` (Zeile 97): Ein Bündel im Store entsteht nur bei Messungen; die bündellose Lage (Watches/Tabs/AirPods) hat KEIN Bündel, nur die Listung. Ein Bündel OHNE Messtag wäre eine dritte Lage; nach der Heimregel "Tag 1 ist gespeichert" kommt sie im Bestand nicht vor.
- (a) Katalog (Zeile 222-275): Bündel ODER Listung genügt. Die Händler-Spalte nennt die Bündel-Anbieter, nicht "0 Händler" (widerspräche "nur im Bündel bei o2"). Ohne Listung keine Detailzeile: `data-auf` trifft ins Leere (app.js bewacht mit `if (p.auf)`), kein Aufklapp-Zeiger. Gegenprobe: das Modell steht in KEINEM Wahl-Eingang.
- (b) Zeitreihen-WAHL (Zeile 308): erst ab 2 Bündel-Messtagen; die 12 bündellosen Auto-Modelle (Watches, Tabs, AirPods) bleiben draußen.
- (c) R3 der P5-Live-Prüfung (Zeile 351-372): Neu-Hinweis am Ort der Wahl; WAHLBARE Modelle stehen nicht im Neu-Hinweis, das bündellose Pixel (Listung ohne Bündel) ebenso nicht.

### `tests/test_geraete_store.py`
- `_listung` (Zeile 39): Das Gerät wird aus der SKU abgeleitet, sonst trüge jede Testlistung dieselbe device_id und der Verwandtenabgleich (`_finde_verwandten`) legte zwei absichtlich verschiedene Artikel zusammen.
- `test_ungelesene_einstiegsseite_altert_ihre_geraete_nicht` (Zeile 174): Nur /handys wurde gelesen, /tarife fiel aus. `test_ohne_angabe_gelesener_einstiege_altert_alles` (Zeile 183): Der Aufrufer sagt damit ausdrücklich "ich habe diesen Anbieter vollständig gelesen".
- Befunde des Reviews 10.08.2026 (Zeile 364-467): Fehlendes Farbfeld spaltet die Identität nicht (ID von der ersten Sichtung, nichts gelöscht); nachgeliefertes Farbfeld füllt die Lücke ohne die ID zu ändern (ID ist Schlüssel). Bei zwei Kandidaten wird nichts geraten: eigener Eintrag statt geratener Verschmelzung. `test_ein_echter_verfuegbarkeitswechsel_wird_weiterhin_geschrieben`: Gegenprobe zum Test darüber.
- Messtermine, Diagnose G0 vom 28.08.2026 (Zeile 602-643): Die Seite meldete nach 17 Tagen und vier echten Prüfterminen "bisher 1 Messtermin", die Lifecycle-Auswertung sperrte 84 von 85 Listungen aus. Zwei Ursachen: Laufbilanz verbuchte nur VOLLSTÄNDIGE Läufe (mobilcom-debitel wurde am Zeitbudget nie fertig und fehlte komplett), und die Messtermin-Zählung hing an der Preishistorie, die bei unverändertem Preis schweigt. Funde aus einem Teillauf sind echte Funde (die Marke vermarktet Hardware). Altbestand: Bilanz absichtlich löschen, wie Läufe vor der Termine-Buchführung aussahen.

### `tests/test_geraete_tarifstufen_einsundeins.py`
- `test_die_uebersichten_verlinken_sieben_geraeteraster` (Zeile 119): Warenkorb-Parameter reisen nicht mit.
- `test_die_geraeteseite_nennt_vorauswahl_und_angezeigten_preis` (Zeile 165): S26 Ultra: Seite ZEIGT 44,99 (mit vorab angehakten Galaxy Buds 4), die Preiskarte nennt 42,99 für das Gerät allein.
- `test_alle_tarife_mal_alle_speichergroessen` (Zeile 185-188): iPhone 18 Pro 4 Größen, S26 Ultra 3 Größen, sechs einheitliche Tarife außer Default: 7 x 5 = 35, dazu Unlimited XL je Gerät 1 Satz. Abrufe: zwei Übersichten, sieben Raster.
- `test_der_aufschlag_kommt_auf_die_preiskarte_der_groesse` (Zeile 205-229): 512 GB im Default-Tarif 56,99 (Preiskarte) + Aufschlag M 5,00; Einmalzahlung steht nur für den Default-Tarif auf der Seite; vorausgewählte Größe trifft das Raster selbst (54,99); Default-Satz bleibt unangetastet.
- `test_jeder_gelieferte_tarif_loest_im_echten_bestand_auf` (Zeile 306): Der Name MIT Volumenklammer löst nicht auf; ohne die Bereinigung wären die Sätze verworfen worden.
- `hole_mit_iframe` (Zeile 326): Ein Tarifdetails-Abruf je Tarif-Slug: sieben.

### `tests/test_geraete_tco_alterung.py`
- Frische-Grenze (Zeile 61, 148-169): 3 Tage alt = noch frisch, 4 Tage = alt (jenseits der 3-Tage-Grenze); 0 Tage ist frisch.
- `test_altes_angebot_faellt_aus_ab_delta_und_ranking` (Zeile 197-231): Pflichtfall: alt fällt aus ab, Delta und Ranking, Zeile bleibt mit Datum und Marke. Delta der frischen Wettbewerber rechnet gegen die frische Referenz: 1.320,76 - 1.224,76 = 96,00. Modell ist nicht "alles alt", Hinweis bleibt aus.
- `test_alles_alt_nennt_den_letzten_stand_mit_datum` (Zeile 267-302): "alles alt" sichtbar statt "nichts gefunden". Letzter Stand ist der späteste Abruf: 16.09.2026 (o2/Telekom); Vodafone ist älter (15.09.) und darf den Satz nicht stellen. Alles fällt aus der Bewertung, ohne Zeile zu verlieren; Marke an der ältesten Zeile nennt ihr Datum.
- `test_band_und_radar_rechnen_nur_mit_frischen_karten` (Zeile 322-350): Band, Balken und Radar: dieselbe Auswahl; der günstigste Wert DES BANDES ist der frische, nicht das alte 1.200,76-Angebot von o2. Katalogspalte nimmt das frische Angebot (1.224,76), NICHT das billigere alte (1.200,76).
- `test_buendelzeilen_sortieren_alte_nach_hinten` (Zeile 400): P3-E1: ohne Vodafone-Tarifleiter gäbe es keine Stufe; eine einzige Stufe genügt, alle drei Tarife fallen hinein.
- `test_zeitreihe_band_mit_nur_alten_angeboten_bleibt_waehlbar` (Zeile 423-454): Kachel zeigt keinen "ab"-Preis, sondern den alten Stand; Lücke nennt die drei Anbieter beim alten Stand; 1&1 und congstar führen das Gerät gar nicht im Bündel.
- VERDRAHTUNG (Zeile 528-547, Prüfer-Befund "hoch", 20.09.2026): Bezugstag darf nicht der Berichtstag sein. `render_site` gibt das Datum des jüngsten RADAR-Berichts (Mi/Fr) als `heute` weiter, die Geräteseite rendert aber TÄGLICH (`geraete.yml`, 02:17 UTC) und fasst die Berichte nicht an. Produktionsbeweis 20.09.: Bestand `updated=2026-09-20`, jüngster Bericht 16.09.; mit ihm als `heute` waren die Telekom-Bündel vom 15.09. "einen Tag alt" und führten frisch Antwortzeile und Spanne; die 3-Tage-Regel war regelmäßig (So-Mi) wirkungslos. Bezug ist der SPÄTERE der beiden Uhren (Berichtstag und `updated` des Bündel-Stores), wie `_auffaellig`. Test geht durch `render_site`, weil der Fehler in der Verdrahtung saß (html.py -> aufbereiten -> geraete_tco_view -> karten). Telekom-Abruf muss vom STAND aus alt (5 Tage), vom BERICHTSTAG frisch (1 Tag) sein; 15.09. ist der ECHTE Telekom-Messtag des Bestands.
- `_buendel` (Zeile 728): Derselbe `heute`, den `render_site` aus reports[0]["date"] durchreicht; der Test stellt die Uhr nicht freundlicher als Produktion.
- `test_spaeterer_tag_liest_nur_lesbare_uhren` (Zeile 749): Bericht NEUER als der Stock (radar.yml läuft, der nächtliche Lauf nicht): Stock altert ehrlich gegen den Berichtstag. `test_gleiche_uhren_altern_nicht_ueber_die_grenze`: beide Uhren 20.09., Telekom 17.09. = Tag 3.
- `test_render_site_traegt_die_marke_in_die_seite` (Zeile 789): "alles alt"-Satz der Gruppe steht NICHT; Marke kommt von der einzelnen Zeile, nicht vom Notzustand des Modells.
- `test_radar_zeigt_alte_karte_als_beleg_nicht_als_paar` (Zeile 841-891): `leitzahl_monate` an der Karte und `monate` an der Basis wie am echten Bestand (P0-B-h1/h3): Radar vergleicht seit P0-B-h3 nur über denselben Zeitraum, unbekannter Zeitraum ist nie gleich; eine Fixture ohne die zwei Felder prüfte das Tor, nicht die Frische. Frische Karte = Paar mit Prozent (1.080,76 gegen 1.320,76 = -18,2 %, Telekom billiger).
- Nachbesserung "ab-Auswahl" (Zeile 901-913, Prüfer-Befund "hoch", 20.09.2026): Dieselbe Frische-Definition (`ist_frisch`, Clean Code 7) gilt für den ab-Preis des KATALOGS. Gemessene Fälle: "ab 1.299,00 EUR bei mobilcom-debitel, 14. August 2026" (37 Tage, aktiv) und "ab 289,00 EUR bei Medimax, 6. September 2026" unterbot das frische ElectronicPartner-Angebot (299,00 EUR vom 19.09.). Alter Wert fällt aus "ab" und Spanne heraus, oder trägt die Marke (harte Regel 9). Tage 14/1/37.
- `test_katalog_ab_*` (Zeile 954-1018): Nur ein frischer Anbieter = keine Spanne; alte Zeile bleibt im Aufklapper mit Datum; ohne frischen Beleg kein Rückfall auf "nur im Bündel" (es GIBT Barpreis-Belege); Tag 4 fällt auch bei Tag-3-Beleg: "ab" bleibt als letzter Stand mit Marke.
- `test_render_site_traegt_die_katalog_marke_in_die_seite` (Zeile 1062): Leitzahl des Regals fehlt; ihr Block ist der EINZIGE mit Klasse `gr-leit--katalog` ("günstigster" taugt nicht als Gegenprobe, steht auch am Tabellenkopf des Vergleichs).
- Zweite Prüfrunde (Zeile 1114-1347, diff-reviewer 21.09.2026): 3×S2 (blockierend) und 3×S3; jeder Test war gegen den zurückgewiesenen Stand ROT, Repro-Zahlen des Prüfers in den Fixtures (12 Tage vor HEUTE = S2-1-Repro; 5 Tage Telekoms altes Klein-Bündel; 1 Tag frisches Groß-Bündel). S2-1: Näherung altert über ihre beiden Belege; alte Näherung ist keine Zahl von heute, Karte bleibt (Regel 9), aber alter Barpreis führt NICHT die Antwortzeile und kein frisches Delta rechnet gegen die alte Referenz. S2-2: Radar-Beleg je Anbieter nimmt die FRISCHE Karte, nicht die alte billige. S2-3: keine falsche Existenzaussage in der Zeitreihe; Satz nennt letzten Stand MIT Datum. S3b: `abgerufen_am: null` ist unbekannt, kein Notzustand. S3c: Berichts-JSON ohne "date" rendert statt zu crashen. S3d (Pin): Wochenkarte hängt an der Berichts-Uhr (13 Tage vor REPORT_STAND).

### `tests/test_geraete_tco_band.py`
- Zeile 31: Vorgabefall aus BRIEF_GRAPH1: dasselbe Modell, das die Hauptansicht ohne Klick zeigt (`geraete_tco_karten.LEITFRAGE_MODELL`).
- `test_drei_echte_tarifsaetze_treffen_ihre_stufe` (Zeile 61): unbegrenzt (Infinity), 18 GB (über den Namen), 60 GB, 150 GB.
- `bestand` (Zeile 106): Dieselbe Anreicherung wie `geraete_tco_view.aufbereiten`; Tarifbindung steht nicht in der Gerätenutzlast, sondern im Tarifbestand (A5.5).
- `test_vorgabefall_zeigt_genau_die_anbieter_mit_echten_buendeln` (Zeile 158-188): Jeder erwartete Anbieter steht GENAU EINMAL, als Linie oder benannte Lücke, nie beides und nie keins. Nur ECHTE Bündel zeichnen eine Linie, keine Näherungskarte; Telekom, congstar und 1&1 stehen als benannte Lücke (niemand wird still weggelassen).
- Zeile 263: Kein TCO-36 im gerenderten Artefakt.

### `tests/test_geraete_tco_orakel.py`
- `test_keine_leitzahl_unter_dem_eigenen_barpreis` (Zeile 81-99): belegter Rabatt darf unterbieten; Gegenprobe: der Lauf hat wirklich eine Vergleichsmenge gesehen.
- `test_widerspruch_pib_und_shopmessung_festgehaltene_messung` (Zeile 142-165): Befundsfall als festgehaltene Messung vom 20.09.2026, nicht als Suche im Bestand: seit P3 (28.09.) hängen Vodafone-Bündel am Blatt "mit Smartphone", seit 29.09. liest der Adapter alle Tarife neu; ein Lookup im täglich wechselnden Bestand liefe ins Leere. Echt bleibt das Blatt (kommt aus dem ausgelieferten Tarifbestand); Gegenprobe: es hat Phasen, der Konflikt ist real.
- `test_kein_tarifposten_wider_die_gemessene_monatsrate` (Zeile 223): Das Blatt, das dieses Angebot beschreibt, ist erlaubt.

### `tests/test_geraete_tco_zustand.py`
- `vorlage_text` (Zeile 65): BRIEF_RAHMEN2_R3 (05.09.2026): zweites Modell OHNE Listung in `geraete_db.json` und OHNE Preishistorie, über den Katalog nachgetragen (F-R2-3): belastbare Karte, aber `zeitreihe.hat_daten == False`; derselbe Slug wie einer der drei echten graphlosen Blöcke im Bestand.
- `_tarife` (Zeile 154-165): o2 mit `preisphasen: []` wie die echte Kachel-Lesart (preistyp live_shop): Quelle schweigt über die Zeit nach der Mindestlaufzeit, die Karte muss die Lücke BENENNEN (F5). O1 (11.09.2026): ein Datenvolumen je Tarif, damit die Fixture Bänder hat und der Graph Zeilen rendert.
- `test_neu_und_erneuert_sind_zwei_karten_und_nur_das_neue_konkurriert` (Zeile 224-236): Beide tragen eine Zahl; erneuert ist Angebot, aber kein Konkurrent (Delta nur für Neugerät). Band zählt beide und nennt das erneuerte; Spanne gehört den Neugeräten; erneuertes steht HINTER dem Vergleich.
- `test_das_etikett_steht_am_g1_balken` (Zeile 245): Genau einmal; der neue o2-Balken trägt kein Etikett.
- `test_die_zustandsstrecke_der_sku_belegt_erneuert_aber_nie_neu` (Zeile 278): Feld am Bündel schlägt alles; Listung schlägt das Suffix.
- `test_ein_erneuertes_eigenes_buendel_wird_nicht_zur_referenz` (Zeile 323): Steht als etikettierte Karte daneben. `test_der_zustand_ueberlebt_speicher_und_leser` (Zeile 339): Leser der Tafel nimmt das Feld mit.
- `_baue` (Zeile 544-634): Bewusst KEINE Listung in `geraete_db.json` und KEIN Punkt in `geraete_preise.jsonl`; `geraet_aus_sku()` löst es über den Katalog auf, Karte rechnet, `listungen_je_modell` bleibt leer. O1: Tarif des Bündels ohne Datenvolumen, Modell bleibt "ohne Graph" (Graph hängt an Bändern, nicht mehr an der Zeitreihe). § 13.2: NUR der kombinierte Monatsbetrag, keine Aufteilung (Bauweise der echten 1&1-Sätze: 44,99 €/36 Monate, siehe test_geraete_buendel_einsundeins); `tarif_id` leer, weil 1&1-Tarife nicht im Tarifbestand stehen (F5-Kommentar im Template). E2 (16.09.2026): TCO-HISTORIE, sonst hätte die Hauptansicht keine Zeitreihe und jeder Graph-Test prüfte einen Leerzustand; drei Messtage für das NEUE o2-Bündel (Band mittel, 50 GB); erneuertes und 1&1-Bündel absichtlich ohne Punkt.
- `test_die_gerenderte_seite_traegt_das_etikett_auf_zeile_und_rechenweg` (Zeile 694-716): G1 wird nicht mehr gerendert; G0 (Zeitreihe) ist die einzige Grafik je Modellblock (BRIEF_FADEN, Kriterium 1); Rechnung bleibt korrekt, nur nicht aufgerufen. Die alte "Alle Bündel als Tabelle" (`.gr-t-zustand`) ging mit O2 in die Zeilen-Tabelle auf; die gr-mband-Zeile ("2 Angebote · davon 1 erneuert") entfiel mit O1: die fünf Zählsysteme der Vergleichsansicht sind auf EINE Fußnote unter dem Graphen gesammelt, die Geräte nennt, keine Angebote. Die leere Vodafone-Zeile gibt es hier nicht; die gefüllte ist die Referenzrechnung und heißt nicht "unser Angebot" (S3).
- F1/F5 (Zeile 732-767): `test_jede_karte_mit_zahl_nennt_den_preis_nach_der_laufzeit_oder_die_luecke`. F1 Stufe 1: die Referenz spricht dem Anbieter nichts ab, nennt sich Näherung und den Bündelpreis "nicht erhoben". Seit P4-Fix (template-Pool) sieht `get_text()` den Rechenweg NICHT mehr; "not in"-Check läuft gegen den VORLAGEN-Text (CLAUDE.md §6).
- A2 (20.09.2026, Zeile 772-942): Geist-Messung in der Angebots-Dedupe, kleines Delta mit ≈ statt Strich. `test_eine_veraltete_messung_verdraengt_kein_aktuelles_angebot`: Geist-Messung ALLEIN bleibt Karte mit eigener Zahl (Neuigkeits-Stufe bricht nur den Gleichstand verschiedener Messungen desselben Slots); gleich alt, verschieden teuer: Preis entscheidet (blau 28 statt grün 30: 1.775,80 EUR). Kleiner Abstand: "≈ ±0,00 €" (1.799,80 EUR), keine Richtung; echter Abstand (Anschluss 40,00 -> +40,00 EUR) ist keine Annäherung (Schwelle sortiert, streicht nicht). Ohne Vodafone-Bündel und ohne eigenen Barpreis keine Referenz: KEIN Delta (None); Strich meint "kein Angebot zum Vergleich", nicht "Abstand zu klein".
- `test_delta_kurz_und_der_graph_traegen_das_ungefaehr` (Zeile 981): Delta mit Prozent bleibt (Band-Graph, Antwort-Satz); Prozent kommt als ABSOLUTER Wert, Vorzeichen liefert der Euro-Betrag.
- `test_ueber_zwei_zeitraeume_steht_kein_betrag_sondern_der_zustand` (Zeile 1075-1099): Referenz mit 36 Monaten (1&1-Bauform), per `monate` simuliert, weil Vodafone im Bestand kein zusammengelegtes Bündel verkauft. Gegenprobe: gleicher Zeitraum, kleiner Abstand: Annäherung bleibt, kein benannter Zustand. Am ECHTEN Makro: Zustand in der Δ-Spalte und als Satz im Rechenweg, `data-delta` leer, kein "≈", kein Euro-Betrag.

### `tests/test_geraete_tote_adressen.py`
- Abschnitte 1-9 (Zeile 135-602): (1) Neun tote Produktadressen kippen keinen gelesenen Lauf; die Lücke ist BENANNT, nicht still 0 (Clean Code 3), jede tote Adresse mit Statuscode. (2) Unter der Schwelle ist der Lauf unvollständig, das Protokoll sagt woran es lag, nicht "kein Einstieg lesbar". (3) Nur eine Antwort des Anbieters ist eine tote Adresse. (4) Der Einstieg selbst bleibt ein Fehler. (5) Die Zahl steht im Protokoll und auf der Quellenseite; Lauf zählt wieder als vollständiger Lauf, Lücke ist gebucht, nicht verschwiegen. (6) Lesezustand GELESEN, nicht TEILGELESEN. (7) Keine tote Adresse sind Wege ohne Statuscode; `test_die_besuchszeit_beendet_den_lauf_ohne_tote_adresse`: die ersten Abrufe liegen im Fenster, danach ist es 09:00 (die Uhr läuft während des Laufs weiter, wie in echt). (8) Mehrere Einstiege: Schwelle rechnet je Einstieg. (9) "Nicht gemessen" steht auch im PROTOKOLL als Lücke.

### `tests/test_geraete_verlauf.py`
- `test_der_eigene_anbieter_faellt_nie_aus_der_kappung` (Zeile 161): Gegenprobe: ohne die Ausnahme hätte er wirklich weichen müssen.
- `test_ein_anbieter_behaelt_seine_farbe_ueber_geraete_hinweg` (Zeile 329): Gerät A: o2 hat mehr Punkte, steht zuerst; Gerät B: Reihenfolge dreht sich um.
- `test_zwei_bekannte_anbieter_eines_diagramms_sehen_nie_gleich_aus` (Zeile 372): Gegenprobe: die drei Service-Provider TEILEN wirklich eine Farbe.
- `test_zwei_preise_an_einem_tag_sind_eine_messluecke_kein_punkt` (Zeile 419-431): Kein Punkt, auch nicht der bestätigte aus der Datenbank; Lücke benannt mit beiden Beträgen; zweiter eindeutiger Tag derselben Listung bleibt.
- Nachbesserung 30.08.2026 (Zeile 449): Messtermine je Gerät.
- `test_die_schwelle_fuers_diagramm_steht_im_modul` (Zeile 498): Leerzustand muss DIESELBEN Schlüssel tragen wie der Normalfall; ein fehlender ist in Jinja kein Fehler, sondern eine stumm leere Seite.

### `tests/test_geraete_zeitreihe_seite.py`
- `test_zwischen_wahl_leiste_und_graph_steht_nur_der_antwort_satz` (Zeile 112-119): DOM-Reihenfolge Wahl < Kacheln < Antwort < Graph (§4.2); der Antwort-Satz ist das EINZIGE Element dazwischen, das kein Aufklapper und keine Tabelle ist.
- `test_jede_karte_traegt_preis_und_anbieter_punkte` (Zeile 156-167): Alle sichtbaren Preislagen zugleich, eine Karte zeigt EIN Band. Eine Bewegung steht nur, wenn sich etwas bewegt hat (28.09.2026).
- `test_kein_weiterer_aufklapper_ueber_dem_graphen` (Zeile 184): Der Fuß-Aufklapper "Maßstab & Datenlage" (§3.1c) umfasst mehr.
- `test_das_fragment_traegt_alle_pare_und_den_startzustand` (Zeile 265): ALLE Paare, auch die des Startzustands; der Rückweg nach einem Wechsel hat genau EINE Quelle (kein Vorgabe-Klon, keine S2-Falle).

### `tests/test_highlight_themen.py`
- `_meldung`/Fixtures (Zeile 56-87): Ein Ereignis = sechs Meldungen aus vier Quellen über denselben Launch. Rauschen: normale Ausgabe ohne gemeinsames Ereignis, bewusst mit verschiedenen Wörtern; zwölf Meldungen mit demselben Satzbau prüften den Häufigkeitsdeckel statt der Gruppenbildung.
- `stelle` (Zeile 132): Bei jeder neuen Antwort von vorn zählen, sonst prüft ein Test gegen die Aufrufe des Laufs davor, ob der Agent NICHT gefragt wurde.
- `test_zuordnung_verlangt_zwei_suchwoerter` (Zeile 195): Ein einzelner Treffer reicht nicht, sonst zieht "Samsung" jede Gerätemeldung des Herstellers in den Launch. Wortgrenzen: "Foldables" ist nicht "Fold8", "Galaxys" schon.
- `test_neue_meldungen_wandern_per_suchwort_ins_thema` (Zeile 225): Die Woche steht an der Meldung; ein Thema läuft über mehrere Ausgaben.
- Archiv (Zeile 261-286): Ohne Archiv sind drei Meldungen des laufenden Laufs zu wenig; Archiv älter als das Fenster zählt nicht (25 Tage vor "heute").
- `test_der_seltenheitsdeckel_rechnet_je_ausgabe` (Zeile 355): Untergrenze doppelte Mindestgruppe, auch bei winzigen Ausgaben.
- `test_spezifitaet_gewichtet_ereignis_vor_rauschen` (Zeile 370): Zwei Wörter ohne Ereignis-/Datumssprache sind eine Firma, kein Vorgang, ohne dass das Modul eine Firmenliste braucht. `test_grosse_finanzgruppen_verdraengen_die_produktgruppe_nicht` (Zeile 444): reinste Rauschgruppe (nur zwei Finanzwörter als Bindeglied) steht nicht vor ihr, fällt hier ganz heraus.
- Antizipation (Zeile 546-641): Voraussetzung ausgeschrieben: OHNE Deckel wären es mehr als drei Gruppen, sonst prüfte der Test seine Fixture; höchstens drei Antizipationsgruppen; vergangene Datumsangabe ist kein bevorstehendes Ereignis (Gegenprobe mit bevorstehendem Termin); Antizipation konkurriert nicht um `MAX_KANDIDATEN` (Agent sah zwei Kandidaten).
- Alterung (Zeile 674-812): Thema endet nach vier Läufen ohne Zuwachs; beendet heißt nicht gelöscht (Speicher bleibt das Gedächtnis); beendetes Thema wird nicht neu entdeckt, auch wenn der Agent wieder zustimmte (Agent wird gar nicht gefragt). Halluziniertes Event-Datum: ein Termin jenseits des Horizonts ist Roadmap, kein Termin, wird nicht übernommen und schützt auch als Bestandsdatum (Lauf vor dieser Regel) nicht; normale Alterung greift.
- Failsafe (Zeile 826-871): Nachschlag trägt ZWEI Dinge: neue Fold8-Meldungen (wandern per Suchwort ins bestehende Thema, bilden keinen neuen Kandidaten, `_schon_erfasst`) und ein fremdes Ereignis als Kandidat des gescheiterten Agenten. Die Pflege braucht kein Modell: ein Anbieter-Aussetzer darf ein laufendes Thema nicht altern lassen, obwohl neue Meldungen da waren.
- Rendern (Zeile 973-1076): Jede Meldung des Themas steht auf der Seite, keine doppelt; Titelseite führt hin, nicht die Archivwoche; endet das Thema, verschwindet die Seite (Ordner spiegelt den Speicher wie `site/images/`). Themenseite zeigt nur belegbare Aktionen (Fixture: nur A; B trifft ein Suchwort, C läuft nicht mehr). Kein zu kleines Bild in einer großen Position; ein tragfähiges Bild bleibt und führt.

### `tests/test_newsletter_bewegung.py`
- `_send` (Zeile 321): Ohne GITHUB_ACTIONS: dort gibt das Skript `::add-mask::` aus (eigener Test); der Test hängt nicht davon ab, wo er läuft.
- `test_die_zahlen_der_zeile_kommen_aus_dem_block` (Zeile 226): o2: Abstand -600 -> -840, Änderung 240; Telekom: 300 -> 420, 120.
- Rest (Zeile 168, 181, 314): `_rahmen_bewegung` jeder Platzhalter belegt; `_erfunden` Zeilen aus mehreren Rahmenteilen wie im Treue-Test nebenan; Block steht nur in der ersten Ausgabe der Woche (Testname trägt es).

### `tests/test_newsletter_versand.py`
- `test_eine_kaputte_zeile_kippt_nicht_den_ganzen_verteiler` (Zeile 70): Der Inhalt der kaputten Zeile steht NICHT im Log (sonst stünde dort eine Adresse).
- `test_zusammenfuehren_laesst_den_juengeren_satz_gewinnen` (Zeile 87): unabhängig von der Reihenfolge der Argumente.
- `test_dieselbe_adresse_bekommt_in_24_stunden_nur_eine_mail` (Zeile 148-161): 24-Stunden-Sperre (Mailbomben); eine ANDERE Adresse ist nicht gesperrt.
- `anhaengen` (Zeile 260): Wiederanlauf: derselbe Plan, dasselbe Log (Idempotenz). `test_der_waechter_addiert_was_heute_schon_raus_ist` (Zeile 414): Limit-Wächter, 280, passt. `test_der_waechter_laeuft_vor_der_ersten_zustellung` (Zeile 506).
- `test_der_versand_wird_gedrosselt` (Zeile 523): Zwei Pausen bei drei Zustellungen; nach der letzten wird nicht mehr gewartet.
- `test_keine_jsonl_im_repo_enthaelt_ein_adressmuster` (Zeile 618): Die eigene Adresse des Absenders steht bewusst in den Rechtstexten und im Absender, sie ist kein Abonnent.

### `tests/test_promo_pipeline.py`
- Zeile 46-50: Die drei Zahlen fürs Laufprotokoll (27.08.2026, Strategie B6/E10b): Der Promo-Ausfall seit 14.08.2026 stand in KEINER Statistik, nur im Actions-Log. `run_promo_stage()` bleibt bewusst ungetestet (siehe Modulkopf); die AGGREGATION ist reine Rechnung auf den Rückläufen und direkt prüfbar.
- `test_angebote_neu_summiert_ueber_alle_seiten` (Zeile 69): kein `new_items`-Feld. `test_eine_ruhige_woche_ist_nicht_dasselbe_wie_ein_ausfall` (Zeile 106): so wie die Pipeline sie weiterreicht; Zeile 116: was ins Laufprotokoll kommt und was NICHT.

### `tests/test_pruefleiter.py`
- nichts übernommen: Hermetik kommt aus `tests/conftest.py`; Gegenproben (beide grünen Tests als Untergrenze; ohne Hook ist der rote Test rot gemeldet, nicht der Kanarienvogel; ohne den roten Test ist dieselbe Auswahl grün) stehen in den Testnamen.

### `tests/test_quellen_register.py`
- `test_bewaehrungsabruf_nach_zehn_laeufen` (Zeile 107): Läufe, in denen die Quelle gar nicht vorkommt (weil übersprungen), zählen für die Bewährung nicht. Rest nur Abschnittsköpfe.

### `tests/test_rechtstexte.py`
- `test_einwilligung_ist_versioniert_und_nachrechenbar` (Zeile 105): Der Nachweis besteht darin, dass JEDER ihn nachrechnen kann, der den Text hat, also ohne Pepper und ohne Projektwissen.
- `test_die_seite_nennt_die_drei_auftragsverarbeiter` (Zeile 199): Echter Text des Repos, nicht die Fixture. `test_die_luecke_steht_oben_auf_der_seite` (Zeile 226): VOR dem Fließtext. `test_ohne_content_verzeichnis_kippt_keine_seite` (Zeile 253): Kein Link auf eine Seite, die es nicht gibt.

### `tests/test_redaktion_kontinuitaet.py`
- `test_letzte_gueltige_redaktion_findet_den_juengsten_treffer` (Zeile 132): Vor dem 08-10 gesucht: der 08-15er zählt nicht, der 08-05er ist ungültig, übrig bleibt der 08-01er.
- `test_uebernehmen_greift_nur_bei_null_bewerteten_meldungen` (Zeile 156): Hat die aktuelle Runde selbst etwas geliefert, wird nichts ersetzt.
- `test_titelseite_zeigt_die_uebernommene_redaktion_mit_stand` (Zeile 208-229): Brief Kriterium 1: alter Aufmacher UND alter Wochenbericht stehen da; Kriterium 1 (Stand) und 2 (Ehrlichkeit): das Datum der echten Redaktion steht sichtbar, zweimal (Aufmacher-Bereich + Wochenbericht); nicht die alten, ehrlosen Leerzustände.
- `test_transparenzseite_behauptet_keine_bewertung_die_nicht_stattfand` (Zeile 247-260): "1 relevante Meldungen aus 12 neuen" wären zwei Zahlen aus zwei verschiedenen Läufen in einem Satz: die 12 sind von HEUTE (`stats.new` der Fixture), die übernommene Meldung von der Ausgabe vom 1.8.
- `test_meldungenseite_zeigt_die_uebernommene_redaktion_mit_stand` (Zeile 318): Überschrift trägt weiter das Datum der HEUTIGEN (leeren) Runde; keine Falschaussage, solange der Hinweis daneben steht.
- `leeres_projekt` (Zeile 339-355): Die Nebenstufen lesen eigene Konfigurationen (Tarifseiten, CT-Log, Warenkörbe) und gingen sonst ins Netz; ohne Netz hing der Test. Kein API-Schlüssel in der Umgebung: die Runde darf keinen echten Netzaufruf machen, auch keinen versehentlichen.
- `test_pipeline_behaelt_redaktion_bei_leerer_quellenliste` (Zeile 327-397): Brief verlangte Simulation `pipeline.run()` mit `quellen=[]`; Kriterium 3: kein Datenverlust, die alte Ausgabe liegt unverändert im Archiv; heutige Runde hat 0 bewertete Meldungen (echte, ehrliche Zahlen) und trotzdem Titelseite mit Redaktion, übernommen mit Hinweis.

### `tests/test_search_index.py`
- nichts übernommen: nur Abschnittskopf "was am 08.08.2026 dazukam".

### `tests/test_seen_store_format.py`
- `test_neuer_store_schreibt_kompakt` (Zeile 49): 3 Hashes + Kopfzeile + ein Zeitstempel, deutlich unter dem alten Format. Zeile 20 ist `# noqa: E402` (bleibt).

### `tests/test_startseite_kurzpfad.py`
- `test_stufe_zwei_ohne_zahl_kommt_nicht_hinein` (Zeile 95): Ohne die Verschärfung bleibt es beim alten Verhalten; die Mail nutzt denselben Aufruf und soll sich nicht mitändern.
- `test_der_kasten_steht_in_der_spalte_nicht_ueber_der_seite` (Zeile 229): Nirgends sonst; eine zweite Fassung außerhalb der Spalte wäre genau die Verdopplung, die hier abgeräumt wurde.
- `test_die_foliensatz_zeile_steht_am_fuss_des_berichts` (Zeile 265): Im Bericht, nicht davor.
- `test_keine_meldung_steht_zweimal_in_der_rechten_spalte` (Zeile 314): Gegenprobe im selben Test: ohne Sperre steht die Meldung zweimal; ohne sie wäre nicht zu sehen, ob die Zusicherung greift oder der Fall gar nicht eintritt (so war der Test zuerst gebaut und grün, bevor er etwas prüfte).
- `test_breko_steht_nicht_vor_den_meldungen_mit_hoeherem_ctm_bezug` (Zeile 448-488): Befund vom 8. August in strengerer Fassung: keine BREKO-Zeile vor einer Meldung mit höherem CTM-Bezug. Grund, warum BREKO diese Spalte anführen DARF: Meldungen mit direktem Portfoliobezug stehen in den zwei obersten Bildstufen oder VOR ihr in derselben Spalte. Gemessen wird OHNE `belegt`: der Kurzpfad steht über derselben Spalte und `gesperrt` hält seine Meldungen aus dem Digest, nimmt aber nur Meldungen mit GEPRÜFTEM Folgerungssatz und ist über die 17 archivierten Ausgaben in 16 leer; ein Test mit ihm prüfte den Normalfall gerade nicht. Vor jeder Meldung mit geringerem Bezug.

### `tests/test_tarif_einsundeins_simonly.py`
- Zeile 51: Fixture-Tupel (Name, Monatspreis, Volumen in GB oder None, Aktionsphase oder None).
- `test_die_ids_treffen_den_tarifbestand_des_repos` (Zeile 157): Die Zählung NAGELT den Join fest; ohne sie fände der Test bei null Treffern dieselbe leere Menge "übereinstimmend".
- `test_aktionsphase_ist_ein_rabatt_und_kein_preis` (Zeile 199): Referenzpreis bleibt der Dauerpreis; 24 Monate zu einem 3-Monats-Aktionspreis zu rechnen wäre die falsche Zahl.
- `test_sammle_holt_details_nur_fuer_verlinkte_slug_adressen` (Zeile 252): Nur verlinkte Adressen (§ 87b): jeder Abruf ist die Seite selbst, eine robots.txt oder eine Details-Adresse aus einem data-iframe derselben Antwort; nichts kombiniert, nichts hochgezählt.

### `tests/test_uebersetzung_auswahl.py`
- Zeile 38: Deutscher Fließtext ab 200 Zeichen ist vorgefiltert und kein Kandidat, egal ob vor oder nach dem 27.08.2026.
- `test_die_reihenfolge_folgt_dem_bericht` (Zeile 101): Bericht sortiert nach Relevanz; die Stufe darf nicht umsortieren.
- `test_die_spracherkennung_bekommt_das_item_nicht_das_highlight` (Zeile 144): Gegenprobe, dass der Fall eintritt: die deutsche Fassung des Analysten ist lang genug, dass die Vorauswahl auf ihr messen WÜRDE.
- `test_deckel_kommt_aus_settings_und_faellt_auf_sechzig_zurueck` (Zeile 282): Expliziter Wert aus settings gewinnt gegen die Vorgabe (60). Eigener Store-Pfad, sonst gelten die 50 Meldungen von oben als "schon übersetzt".
- `test_ueber_deckel_zaehlt_nur_was_wirklich_wegfaellt` (Zeile 303): Fünf spanische, zwei deutsche; deutsche sind vorgefiltert und stehen nicht über dem Deckel. Bis 27.08.2026 stand hier Englisch; seit MUTTERSPRACHEN nur noch "de" enthält, wäre ein englisches Beispiel selbst sicher fremdsprachig.
- `test_der_analyst_sieht_deutlich_mehr_als_dreihundert_zeichen` (Zeile 360): Vollständig, nicht bei 300 Zeichen abgeschnitten.
- `test_ein_stapel_bleibt_im_eingabebudget` (Zeile 412-418): Je Meldung gekappter Text plus Metafelder; absolut: ~4 Zeichen je Token, die konfigurierten Modelle tragen 1M Kontext, ein Stapel muss weit darunter bleiben.

### `tests/test_uebersetzung_link_browser.py`
- Zeile 42-46: Eine Zeile Text bei 11.5 px in der Grotesk; zwei Zeilen wären rund 28 px. Die Grenze liegt bewusst dazwischen und nicht auf einem exakten Wert: die echte Schrift lädt in der Sandbox nicht, gemessen wird die Rücklaufschrift, und eine Kalibrierung auf eine Schrift ist eine Wette (siehe CLAUDE.md zum Zeitungskopf).
- `_links` (Zeile 133): Die Ressortblöcke sind `<details>` und liefern zugeklappt keine Maße.

### `tests/test_waechter.py`
- `test_von_hand_gelockerte_liste_ist_rot_im_arbeitsstand_und_committet` (Zeile 208): Ein späterer Commit macht die Lockerung nicht wieder unsichtbar.
- Zeile 379-408: Fälle "Gegen 6ceb9cd ungezählt": Abschalter von ruff, mypy und isort; Plugins über `globals()` und `addopts` (Verdeckung); Eingriffe in pytest und die Leiter; weitergereichte Uhr, Uhren ohne Zeitangabe; Uhr über Importaliase. Commit 6ceb9cd ist der Stand, gegen den diese Wächterfälle als ungezählt galten.
