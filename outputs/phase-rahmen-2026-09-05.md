# Phase RAHMEN — die Geräteseite im Rahmen der gebilligten Skizze (A-R1/A-R3)

Stand: 05.09.2026. Auftragsgrundlage: `BRIEF_RAHMEN.md`. Branch `openclaw/ticket-rahmen`,
Basis `main == bc1f7e2`. Commits: `8999c6a` (Überschrift), `3614388` (Hauptarbeit),
`3819322` (wip-Rettungscommit, Suite-Warteperiode).

> **Vermerk:** Der Bau-Lauf endete zweimal beim Warten auf Hintergrundsuiten (bekanntes Muster);
> die Arbeit selbst war vollständig. Suite-Messung, Bericht und Branch-Push wurden vom PM
> nachgezogen und sind als solche gekennzeichnet — alle inhaltlichen Aussagen stammen aus den
> Commits bzw. eigenen Messungen des PM am Endstand.

## Geliefert

1. **A-R1 — Erklärtexte raus (seine erste Vorgabe).** Die Absätze „Gerechnet wird, was ein Bündel
   …" und „Die Grenze: verglichen werden Gesamtkosten …" sind aus dem Lesefluss entfernt; ebenso
   die Karten-Erkläzeilen „Monatspreis ‚ab' …" (35×) und „Referenzrechnung, kein Angebot …" (30×).
   Ihr Inhalt steht hinter Aufklappungen (Rechenweg je Karte bzw. seitenweit „Wie gerechnet?").
   PM-Messung am Render: **alle vier Verbotsmarker 0-mal außerhalb von `<details>`-Blöcken**
   (190 Blöcke gesamt).
2. **A-R3 — Händler als benannte Lücken.** Neues `haendlerkarte`-Makro: Amazon, Expert, Saturn
   je Modell als graue Karte ohne Wert mit dem Vermerk „Händler — Beschaffung läuft"
   (**177×** im Render = 59 Modelle × 3) und ein Legenden-Eintrag ohne Linie je G0-Graf.
   Keine erfundene Zahl, keine leere Stelle ohne Namen.
3. **Überschrift (Klasse C, PM 05.09.):** „Dieses Gerät — wo kaufe ich es am günstigsten?"
   (Render 1×; `<title>` mitgeführt). Die Bündel-Sicht-Überschrift ist entfernt.
4. **Zeitreihe und Balkenblöcke unangetastet** — „Sammlung läuft" unverändert 56×, G0/Lücken
   unverändert.
5. **Tests:** 7 neue in `tests/test_geraete_rahmen.py` (Verbotsmarker außerhalb details = 0,
   Händlerkarte je Modell ×3 ohne Betrag, Überschrift). Geraete-Suite des Baus: 977 passed /
   7 skipped. **Volle Suite (PM-Messung, 13:15): 2 failed / 2696 passed / 14 skipped** — die
   zwei Roten `test_promo_seite.py` (vorbestehend, Kriterium 8b, diff-fremd).
6. **Site-Artefakt committet** (`site/geraete.html`, `style.css`; `keyword-index.json` auf
   committeten Stand zurückgesetzt — Datums-Zeitbombe, bekannt).

## Bewusst offen

- Händler-Preise selbst (Beschaffung läuft; QUELLEN_MAP §6).
- Die drei alten Test-Namen der Suite-Vorgabe hießen im Brief test_promo_seite — identisch
  erfüllt; kein weiteres offen.
