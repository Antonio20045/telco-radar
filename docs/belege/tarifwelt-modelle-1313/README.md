# Saturn/MediaMarkt Tarifwelt: Modellabdeckung nachgemessen (13.11.2026, Baupaket P6)

Analyse `analyse-abdeckung-1313.md` (Abschnitt 2a, Baupaket P6): von den 486
Modell-Speicher-Zellen ohne Datensatz UND ohne Beleg entfallen 103–107 je Netz
auf Saturn/MediaMarkt. Ursache: `MODELL_SLUGS`
(`src/telco_radar/collect/geraete/tarifwelt_lauf.py`) versuchte bisher
ausschließlich die 18 Pflichtmodelle (`pflicht_modelle_wenn_aktiv`) - alle
anderen 71 der 89 Katalogmodelle wurden nie abgerufen, egal ob die Tarifwelt
sie führt oder nicht.

## Messung

Zwei Schritte, beide am Original, mit ehrlicher Kennung (`TelcoRadar/1.0
(+https://telco-radar.onrender.com/ueber)`), robots.txt beachtet, nichts im
Warenkorb:

1. **Sitemap** `https://tarife.mediamarkt.de/sitemap.xml` (laut `robots.txt`
   erlaubt; `Disallow` gilt nur für `/*/pks` und `/*/checkout`) - die
   vollständige Geräteliste. `sitemap-smartphones-2026-11-13.txt` enthält alle
   93 `/smartphones/<marke>/<slug>`-Pfade. Keine deutsche iPhone-14/15/16-
   Generation, keine ältere Galaxy-S-Generation (S23–S24), kein Motorola außer
   "edge-70", keine Nothing-, Fairphone-, AirPods- oder Telekom-"T
   Phone"-Einträge - diese Modelle führt die Tarifwelt grundsätzlich nicht
   (Sortimentsaussage, wie bei der bestehenden congstar-Sitemap-Prüfung).

2. **Ein GET je verbleibendem Kandidaten** (28 Modelle, die in der Sitemap
   stehen, aber noch nicht in `MODELL_SLUGS`):

       https://tarife-api2.mediamarkt.de/v1/productdetail/<slug>

   `uebersicht-neue-modelle-2026-11-13.json` zeigt die 20 Modelle, die
   mindestens eine lieferbare Variante trugen (`hardware.variantFilter`,
   `available: true`) - sie stehen jetzt in `MODELL_SLUGS`.
   `variantfilter-nicht-lieferbar-2026-11-13.json` zeigt die 8 Modelle, bei
   denen JEDE Variante `available: false` war (derselbe Befund wie beim
   Präzedenzfall Galaxy S26+/A57/Pixel 10a vom 13.11.2026,
   `docs/belege/tarifwelt-nicht-lieferbar-1311/`) - "nicht lieferbar", nicht
   "nicht im Sortiment", deshalb als belegte Lücke OHNE
   `art: nicht_im_portfolio` und bewusst nicht in `MODELL_SLUGS` (ein
   täglicher Leerlauf-Abruf ohne Nutzen).

## Ergebnis

| Klasse | Anzahl | Verbleib |
|---|---|---|
| bereits in `MODELL_SLUGS` (Pflichtmodelle) | 18 | unverändert |
| in Sitemap, mindestens 1 lieferbare Variante | 20 | neu in `MODELL_SLUGS` (nicht Pflicht) |
| in Sitemap, 0 lieferbare Varianten | 8 | belegte Lücke, ohne `art` |
| nicht in der Sitemap (keine Marke/kein Slug) | 43 | belegte Lücke, `art: nicht_im_portfolio` |

43 + 20 + 8 + 18 = 89 Katalogmodelle, die laut Export-CSV
(`site/exporte/geraete-tco-24.csv`, Zustand "neu") die 133 Modell-Speicher-
Einheiten der Analyse bilden.

Die 20 neuen `MODELL_SLUGS`-Einträge sind bewusst NICHT Teil von
`pflicht_modelle_wenn_aktiv`: eine Erweiterung dieser Liste würde die Modelle
automatisch zu `pflicht_modelle` (unten in `config/geraete_abdeckung.yaml`)
und damit zum CI-Gate für ALLE Netzbetreiber machen - außerhalb des Auftrags
für dieses Paket (Vodafone/congstar bleiben unangetastet). Der Wächter-Test
`tests/test_abdeckung_haendler_modelle.py` prüft seitdem eine Teilmenge
(`pflicht_modelle_wenn_aktiv ⊆ MODELL_SLUGS`) statt Gleichheit.

## Kennzahl vorher/nachher

`python scripts/saturn_abdeckung_bericht.py --vorher-ref origin/main`
(Stand dieses Pakets, Export-CSV unverändert, nur die neuen
`belegte_luecken`-Einträge zählen):

| Zeile | vorher | nachher |
|---|---|---|
| Saturn/MediaMarkt · Vodafone-Netz | 100 | 42 |
| Saturn/MediaMarkt · Telekom-Netz | 97 | 39 |
| Saturn/MediaMarkt · o2-Netz | 102 | 44 |
| **gesamt** | **299** | **125** |

Die verbleibenden 125 Zellen sind die 20 neuen `MODELL_SLUGS`-Modelle (noch
kein Preis, weil der Tageslauf für dieses Paket nicht neu ausgeführt wurde -
der nächste reguläre Lauf liest sie erstmals) sowie Fälle, in denen das Modell
zwar erfassbar ist, aber am Messtag kein Band/Netz trägt (kein Wächter-Thema,
siehe Moduldoku `tarifwelt_lauf.py`).
