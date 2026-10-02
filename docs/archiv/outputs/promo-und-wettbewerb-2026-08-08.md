# Promo Übersicht & Wettbewerb — Schlussliste, 08.08.2026

Antonios Auftrag, wörtlich:

> „arbeite an der promo seite weiter, da fehlen bei einigen aktionen die
> bilder, das wirkt so richtig scheiße, außerdem will ich die größten
> anbieter wie telekom etc. an erster stelle haben, soll also nach
> wichtigkeit der anbieter geordnet werden, außerdem die namen der
> wettbewerber prominenter, zu dezent, das gleiche bei wettbewerb, namen
> prominenter und mach wettbewerb das layout besser, so das man nicht so
> viel runterscrollen muss"

Fünf Punkte, alle erledigt. Alle elf Prüfungen von `scripts/pruefe_portal.py`
grün, **673 Tests** (vorher 658).

---

## 1. Die fehlenden Bilder — zwei getrennte Probleme

Gemessen, nicht geschätzt: von **77 Karten hatten 37 an der Motivstelle gar
nichts**. Das waren zwei Fehler in einem.

**(a) Die Vorlage ließ die Lücke zu.** Nur die große Karte bekam ohne Bild
eine Schriftkachel; für die kleinen war „reine Textkarte" ausdrücklich als
Absicht dokumentiert — und Kriterium 8c von `pruefe_portal.py` prüfte
deshalb nur die großen. Weil eine Rasterzeile so hoch ist wie ihre höchste
Karte, stand neben jedem Bild eine handbreite Lücke mit einer Schlagzeile
darin. **Jetzt trägt jede Karte ein Motiv** — Kampagnenbild oder
Schriftkachel mit der Kernzahl („20 GB · 6,99 €"). Dazu `align-items:start`:
eine kurze Karte wird nicht mehr auf die Höhe der höchsten ihrer Reihe
gedehnt, der Zwischenraum liegt zwischen den Karten statt in ihnen.

**(b) Es waren wirklich zu wenige Bilder.** Stufe 4 der Zuordnung (das
Bühnenbild einer Seite) vergab **ein Motiv je MARKE** — die Rechnung von
vorgestern, als eine Marke eine Seite hatte. Seit dem 08.08. hat sie bis zu
sieben, und jede bringt ihr eigenes Motiv mit: congstar liefert über vier
Seiten 80 Bildkandidaten und bekam höchstens eins. Jetzt rechnet Stufe 4 **je
Aktionsseite** (`promo_bilder._seitenmotive`), das Motiv geht an das stärkste
noch unbebilderte Angebot dieser Seite.

Gemessen über alle 59 konfigurierten Seiten, soweit statisch abrufbar (in der
Sandbox kommt Chromium nicht ins Netz):

| | Angebote mit Bild |
|---|---|
| vorher | 41 von 77 |
| nachher | **49 von 77** (14 davon Seitenmotive) |

In GitHub Actions kommen die JS-gerenderten Seiten dazu (Telekom,
mobilcom-debitel, klarmobil, Lidl Connect) — **nach dem nächsten Lauf die
`Promo-Bilder:`-Zeile im Protokoll ansehen.**

Zwei Befunde nebenbei, beide auf der Seite sichtbar gewesen:

* „Smartphone Deals ab 1 Euro einmalig" ergab die Kachel **„1 Eur"** — `EUR`
  ohne Wortgrenze schnitt mitten aus „Euro". Behoben.
* **Lidl Connect zeigte dieselbe Aktion zweimal** („SMART Tarife mit 5G und
  Flatrate" / „SMART-Tarife mit 5G und Flatrate", dazu zweimal
  „Jahrestarife"). Die Erkennung im Store (`_find_existing_id`) greift erst
  beim nächsten Upsert; was davor entstanden ist, liegt doppelt in der
  Datenbank. Beim Rendern werden solche Zwillinge jetzt zusammengefasst —
  dieselbe Heuristik wie im Store, **ohne die Datenbank anzufassen**, und das
  Motiv der Dublette erbt die bleibende Karte. 77 → 71 Karten.

## 2. Reihenfolge nach Wichtigkeit des Anbieters

Bis dahin sortierten die Blöcke nach dem **Score der stärksten Aktion**. Das
ist eine Rangliste der Angebote, keine des Marktes, und sie hängt an einem
einzigen Lauf: **Otelo stand auf Platz eins, die Telekom auf Platz zehn**,
weil deren JS-Seiten an dem Tag nur zwei Angebote hergaben.

Neues Feld `rang` in `config/promo_sources.yaml`, **gepflegt statt
gerechnet** — Marktgewicht steht in keiner Zahl dieses Projekts. Zwei Regeln,
im YAML-Kopf begründet: Netzbetreiber vor Zweitmarken, danach die Konzerne in
der Reihenfolge ihrer Netzbetreiber. Die Seite steht jetzt so:

    Telekom · O2/Telefónica · 1&1 · congstar · Otelo · Blau · ALDI TALK ·
    mobilcom-debitel · Lidl Connect · Penny Mobil · winSIM · PremiumSIM ·
    simplytel        (Vodafone selbst weiterhin am Ende, als Vergleichsanker)

Der Score ordnet weiterhin **innerhalb** einer Marke und trägt die
Hervorhebung „wichtig". `tests/test_promo_seite.py` hält fest, dass eine
Spitzenaktion des kleinsten Anbieters die Seite nicht umsortiert, und prüft
die Konfiguration selbst auf vollständige, eindeutige Ränge.

## 3. Die Namen prominenter (beide Seiten)

Der Markenname stand als 11,5-px-Grotesketikett über einem Block voller
16-px-Schlagzeilen — kleiner als alles unter ihm, auf einer Seite, die nach
Anbietern gegliedert ist. Jetzt: **Serife, 26–34 px, schwarz**, mit
Tier und Konzern als leises Etikett am rechten Rand („Discount- und
Zweitmarke · Deutsche Telekom" — dass congstar zur Telekom gehört, ist die
halbe Aussage). Die Linie darüber trägt weiterhin die Tier-Farbe.

Auf `wettbewerb.html` dieselbe Bauform (`.wb-kopf`/`.wb-name`, 28–38 px).
Beide Seiten beantworten dieselbe Frage — „wer" — und zeigen den Namen
jetzt zuerst.

## 4. Wettbewerb: halb so lang

**6777 px → 4169 px (−38 %)**, ohne dass eine Meldung wegfällt. Der laufende
Monat der Telekom allein war 2600 px: 30 Chronikzeilen über die volle
Satzbreite, jede 86 px hoch für zwei halbleere Zeilen.

| Stellschraube | Wirkung |
|---|---|
| Chronik **zweispaltig** | halbe Höhe je Monat. Datum, Ressort und Quelle bilden eine leise Kopfzeile über der Schlagzeile statt zweier Spalten davor — nebeneinander blieben in einer 570-px-Spalte 400 px für den Text |
| laufender Monat zeigt **12 Meldungen** | der Rest einen Klick tiefer, dieselbe Mechanik wie bei älteren Monaten (`_OFFEN_JE_MONAT`) |
| Einordnung auf **2 Zeilen** begrenzt | drei Zeilen Fließtext je Eintrag waren die Höhe, die den Umbau ausgelöst hat |
| Themenverlauf **3 statt 4** Ausgaben | die Verschiebung ist auch an drei Zeilen ablesbar |

Ein Fallstrick, der in zwei Spalten neu ist: die alte Regel „Tageszahl nur
beim ersten Eintrag ihres Tages" **zerreißt am Spaltenumbruch** — oben in
Spalte zwei stünden Meldungen ohne Datum. Jede Zeile trägt ihr Datum jetzt
selbst, dafür kurz („7.8.").

## 5. Was geprüft wurde

```
python -m pytest -q                 673 Tests
python scripts/pruefe_portal.py     11 von 11 bestanden
```

`pruefe_portal.py` Kriterium **8c prüft jetzt ALLE Karten** auf ein Motiv,
nicht nur die großen — die alte Fassung hat genau die Lücke gedeckt, die
Antonio gesehen hat. Neue Wahrheitstests: Motiv je Aktionsseite,
Leitseiten-Rückfall für Bestandsangebote ohne `source_url`, kein Motiv
zweimal, keine zwei gleichen Schriftkacheln in einem Block, Dubletten-Merge
samt Bildvererbung, Rangfolge der Konfiguration, Faltung des laufenden
Monats ohne Meldungsverlust.

## Offen

* **Nach dem nächsten Actions-Lauf** die Zeile `Promo-Bilder:` im Protokoll
  ansehen: wie viele Angebote bekommen mit den JS-gerenderten Seiten ein
  Motiv? Die 49 von 77 sind die Untergrenze aus reinem HTTP.
* Die **Dubletten in `promo_db.json` bleiben in den Daten** — sie werden nur
  beim Rendern zusammengefasst. Wer sie an der Wurzel loswerden will, braucht
  einen Merge-Lauf über den Store; das ist eine Datenmigration und keine
  Anzeigefrage.
* Aus dem Auftrag vom 08.08. weiterhin offen: prüfen, ob die vier Telekom-
  und drei mobilcom-debitel-Seiten in Actions Text liefern.
