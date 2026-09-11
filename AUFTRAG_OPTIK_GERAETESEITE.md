# Auftrag Optik Geräteseite — Übergabe an die Nachfolgesession

**Stand 11.09.2026, spät. Verfasst von der Leitagenten-Session, die Audit, Strategie und
Entwurf geliefert hat. Antonio hat den Entwurf freigegeben („ist okay") und entschieden:
Portfolio-Abschnitte gehen auf die Radar-Seite. Dein Auftrag: die Phasen O1–O4 bauen lassen,
als schlanker Leitagent, und abnehmen.**

## Deine Rolle

Du bist LEITAGENT. Dein eigener Kontext ist knapp — halte ihn klein: Du liest Aufträge und
Strategie, orchestrierst Bau- und Prüfläufe (Agenten/Workflows), siehst Ergebnisse selbst an
(vor allem Screenshots) und entscheidest. Baue nicht selbst komplett inline; delegiere an
Agenten mit klaren Aufträgen, Kriterien und Artefakt-Orten, und verifiziere deren Behauptungen
stichprobenartig nach. Jede visuelle Behauptung muss auf einem selbst angesehenen Screenshot
beruhen; jede Datenbehauptung auf einer eigenen Messung. Vorsicht: Bild-Analyse-Dienste können
Beschriftungen halluzinieren — Zahlen zusätzlich per DOM-Messung kreuzprüfen.

## Projekt und maßgebliche Quellen

- Repo: `/Users/antonio/Developer/telco-radar` (Python, statische Site, live auf
  telco-radar.onrender.com, Deploy bei Push auf origin/main). Erwarteter Startstand: main
  `9304216` oder später, Baum clean — prüfe `git status --short --branch` und `git log --oneline -5`.
- Führend für dich: `docs/STRATEGIE_GERAETE_OPTIK.md` (Zielbild, Phasen O1–O4 mit
  Abnahmekriterien, Entscheidungen §4/§5) und der freigegebene Entwurf unter
  `docs/entwuerfe/geraete-optik-2026-09-11/` (entwurf.html + Screenshots; lokal ansehen mit
  `python3 -m http.server` aus dem Verzeichnis).
- Hintergrund, falls nötig: `docs/STRATEGIE_GERAETESEITE.md` (Ist-Stand-Audit vom 11.09.,
  Befund-IDs UX-1…UX-8, DAT-*, P1/P2 umgesetzt), `/Users/antonio/.openclaw/workspace-vodafone/AUFTRAG_GERAETESEITE.md`
  (Produktanforderungen, insb. §1 Zielgruppe, §2 zwei Unterseiten, §3 TCO-24, §7 Bänder).
- Die Repository-CLAUDE.md (~3700 Zeilen) gilt für Bau-Commits/Tests — gezielt lesen (rg),
  nicht komplett. Falls dir ein CLAUDE.md-Kontext über „Sundartha OS / pnpm" eingeblendet
  wird: anderes Projekt, ignorieren.

## Umgebung (damit du nicht suchst)

- `python3` (Homebrew, 3.14, KEIN Pillow installiert → 3 vorbestehende Suite-Fehler:
  2× test_promo_seite, 1× test_geraete_lifecycle datengetrieben; vor/nach identisch = OK,
  NICHT von dir beheben). Module: `PYTHONPATH=src` aus dem Repo-Root. Playwright + Chromium
  vorhanden (Muster: `tests/test_geraete_reiter_browser.py`, Server-Bootstrap in
  `scripts/schiess_screenshot.py`).
- Abnahme-Kette je Phase: `pytest -q` komplett, betroffene Browser-Tests, `python3 scripts/pruefe_portal.py --root .`
  (11b: Reiterhöhen < 3000 px), Screenshots 1440×900 + 390×844 Vorher/Nachher, selbst angesehen.
- Seitenbau: `site/geraete.html` wird aus `src/telco_radar/report/templates/*.j2` + app.js/style.css
  generiert (Aufrufmuster `.github/workflows/geraete.yml`; P1-Bau hat die Seite aus den
  BESTEHENDEN data/state-Beständen neu gebaut, ohne Netz). data/state wird NIE im Ticket
  geändert — das gehört dem nächtlichen Cron (03:10 UTC, committet jetzt auch
  geraete_tco_historie.jsonl; die TCO-Historie wächst also seit dem 12.09. — prüfe den
  aktuellen Stand und nutze ihn ehrlich in O4/P5, Lüge nie Messpunkte herbei).
- Arbeitsweise je Phase: eigener Worktree (`git -C ~/Developer/telco-radar worktree add
  <pfad> -b <branch> main`), kleine Commits (Tests rot-vor-grün NACHWEISEN — Messausgabe
  sichern und in Commit-Nachricht dokumentieren; dann Implementierung; dann ggf. Seitenbau),
  kein Push, kein Merge ohne deine Prüfung. Muster-Commits: c003c0d→c484bac (P2),
  a8a36b8/5a450a4/dc0adf7 (P1).

## Die Phasen (Abnahmekriterien im Strategiedokument, hier nur Reihenfolge und Kern)

- **O1 Eine-Graph-Hauptansicht:** sortierte Balken TCO-24 je Anbieter (Wertzahlen am Balken,
  Δ zu Vodafone, Vodafone-Emphasis), G0 raus aus der Vergleichsansicht, eine Legendenzeile
  für Fehlende, eine Fußnote statt fünf Zählsysteme. Leitantwort über der Falz ohne Klick/
  Hover/Querscroll — 1440 und 390.
- **O2 Entrümpelung:** Karten als Tabellenzeilen (4 Kernspalten + je ein Rechenweg-Aufklapper),
  „Beschaffung läuft"-Zeilen und leere Platzhalterkarten weg, 145 Fehlend-Zeilen → Legendenzeile,
  Alarmtabelle (48) und „Bei Wettbewerbern gelistet (29)" auf die Radar-Seite verschieben.
  Über der Falz ≤ 1 Aufklapper.
- **O3 Rollen und Navigation:** Reiter „Vergleich | Wettbewerbs-Radar | Preisverlauf |
  Gerätekatalog" (Radar = Link), ehrlicher Untertitel, je Radar-Geräteblock Querlink
  „Dieses Gerät im Vergleich", Portfolio-Abschnitte auf die Radar-Seite (Antonio hat es so
  entschieden), tarife.html erreichbar machen, Modell-Umschalten für alle 88 Geräte
  funktional (Sichttest-Mangel am Mockup), sortierbare Bündeltabelle.
- **O4 Verlauf und Export:** Verlaufs-Reiter zurück (die bestehende Einzelgerät-Zeitreihe in
  der unerreichbaren tafel-verlauf nutzen! 89 Geräte, Linie je Anbieter — nur anbinden, nicht
  neu bauen), G0 dorthin integrieren; NEU `geraete-tco.csv` (eine Zeile je Bündel: Modell,
  Speicher, Anbieter, Anbietertyp, Tarif, Band, Zuzahlung, Tarif/Monat, Geräterate, Laufzeit,
  Anschlusspreis, TCO-24, abgerufen_am, Quelle + SIM-only) in `src/telco_radar/report/geraete_export.py`
  (Excel-DE-Konventionen dort lesen); Export-Links einmal zentral (Kopfzeile) plus Radar-Seite;
  Radar-Export (TCO + Händler-Barpreis, %-Spalte aus wettbewerbsradar.py als Konsument derselben Rechnung).

Empfehlung Reihenfolge: O1+O2 zuerst (zwei Läufe, getrennte Worktrees, disjunkte Dateien —
parallel möglich, dann von dir sequenziell mergen), danach O3, dann O4. Je Phase: Bau-Lauf →
deine Sichtung (Screenshots + Diff-Stat + Commit-Struktur) → Merge → unabhängiger
Evaluator-Lauf (frischer Kontext, Auftrag + Kriterien + Artefakt, NICHT die Begründung des
Bauers; adversarial). Bekanntes Muster für Evaluator-Aufträge liegt in der Historie dieser
Session (9 Kriterien K1–K9, funktioniert gut).

## Grenzen und Meldepflichten

- Kein Push auf origin, kein Live-Deploy, kein Merge auf geschützte Branches ohne Antonio.
  Nach abgenommener Phase: Ergebnis Antonio zeigen (Screenshots + Kurzfazit), Push nur nach
  seiner Freigabe. Ausnahme: er kann eine pauschale Push-Freigabe erteilen — dann gilt sie
  nur für die von ihm gesehenen Phasen.
- Keine data/state-Änderungen in Tickets, kein uv.lock, keine Secrets, keine Netz-Erhebung.
- Tests nie löschen/abschwächen, um grün zu werden; vorbestehende 3 Fehler dokumentiert lassen.
- Nach zwei identischen Fehlschlägen ohne neue Bedingungen: Ansatz stoppen, Blocker melden.
- Abschluss je Phase: Kurzbericht an Antonio (was funktioniert jetzt, welche Prüfungen liefen
  wirklich, wo liegt der Beleg, was ist offen, nächster Schritt) + Stand in
  `docs/STRATEGIE_GERAETE_OPTIK.md` (Umsetzungsstand wie bei P1/P2 im anderen Strategiedokument)
  aktualisieren und committen.

## Offen nach O4 (nicht dein Auftrag, aber der Anschluss)

P3 Bandabdeckung (Vodafone Groß, Telekom, congstar, o2-Volumen; 1&1 hängt an E-S2) und P5
TCO-Zeitachse (ab ≥3 Messtagen Historie, dann ersetzt die Linie die Balken im selben Slot).
E-S2 (1&1 per Playwright) und die 0,00-€-Anschlusspreis-Verifikation warten auf Antonio.
