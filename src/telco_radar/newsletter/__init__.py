"""Der Newsletter - ein AUSSPIELKANAL, kein vierter Anwendungsfall.

Das ist die wichtigste Abgrenzung dieses Pakets, weil sie den teuersten
Fehler verhindert: einen zweiten redaktionellen Apparat zu bauen, der eigene
Texte schreibt und dann zwangslaeufig irgendwann etwas anderes sagt als die
Website. Drei Regeln, in der Umsetzung nicht verhandelbar:

  * **Keine neuen Inhalte.** Die Mail enthaelt ausschliesslich Textbausteine,
    die im Bericht schon stehen. Was in der Mail steht, steht wortgleich auf
    der Seite. `tests/test_newsletter_render.py` haelt jeden inhaltstragenden
    Block gegen das Quell-JSON.
  * **Kein Modellaufruf pro Empfaenger.** Ein Verteiler mit 200 Personen
    kostet sonst 200 Editor-Laeufe, dauert laenger als der Radar-Lauf selbst
    und erzeugt 200 leicht verschiedene Wahrheiten. Die Mail ist eine
    Auswahl- und Formatierungsaufgabe.
  * **Die Mail ist ein Anreisser, nicht der Bericht.** Ziel jeder Ausgabe ist
    der Klick auf die Seite.

Aufbau des Pakets:

  `filters.py`      Was bekommt wer? Die vier Dimensionen, die Stichwoerter
                    und die Verknuepfungsregel.
  `subscription.py` Wie sieht ein Abo aus, und was ist ein gueltiges?
  `segments.py`     Zwei Personen mit gleichen Filtern bekommen dieselbe
                    Mail - einmal rendern, N-mal zustellen.
  `render.py`       Aus Bericht + Treffern werden HTML und Text (N3).
  `transport.py`    Der Versandweg hinter einer Schnittstelle (N3).
  `store.py`        Der verschluesselte Abo-Speicher (N5).
  `versand.py`      Sendeplan, Idempotenz, Limit-Waechter (N6).
"""
