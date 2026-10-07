# Analyse: LLM-Stufen, Editor, Stores

- 402 wird nie wiederholt, sondern als `LLMModelUnavailable` an den nächsten Anbieter der Kette gegeben.
- Eine leere Antwort heißt meist zu kleines `max_tokens`, weil die Denkspur mitzählt; Untergrenze je Stufe 16000.
- Jede Stufe holt ihr Modell aus `_modelle_fuer_anbieter()`; wer einen Anbieter ergänzt, prüft alle Aufrufer.
- `_items_payload` in `agents.py` ist eine Positivliste: ein neues Feld am `Item` erreicht den Analysten erst, wenn es dort steht.
- Stufen, deren Ergebnis an einer Karte hängt (etwa Übersetzung), laufen auf `berichtete_items()`, nicht auf `new_items`.
- Die Sprache wird nie auf der Überschrift erkannt, sondern auf Text ab 200 Zeichen. `py3langid.classify()` liefert eine Log-Wahrscheinlichkeit; Schwellen brauchen `norm_probs=True`.
- Meldungen werden nie gekappt, nur parallelisiert: Scheitert ein Analysten-Stapel, kommen seine Meldungen als `_ungelesen` zurück und bleiben aus dem Seen-Store.
- Wer den Editor-Themenabschnitt ändert, ändert Prompt und `validate_editorial_briefing` gemeinsam.
- `config/ctm_fokus.yaml` sagt, was „für uns wichtig“ heißt, und steuert die Reihenfolge der Startseite.
- Abnahme der Geräteseite (Datenkonzept 11): `geraete_abnahme.stand()`, Goldliste `config/geraete_goldliste.yaml`, Ausgabe `scripts/abnahme_stand.py`. „Zählt“ heißt `geraete_pruefstatus.satz_zaehlt`, dieselbe Definition wie die Notbremse; was Netz, Ablage oder einen Menschen braucht, bleibt `offen`, nie grün.
