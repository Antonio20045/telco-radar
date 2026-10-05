# Auftrag P22: notiz

Ziel: Adapter, registriere, umgesetzte_methoden, ADAPTER und GeraeteAbrufFehler ziehen aus collect/geraete/__init__.py in das neue Modul collect/geraete/basis.py; die vier gleichen _preis aus vodafone.py, o2.py, congstar.py und telekom.py werden die eine Funktion _preis in basis.py. Die sechs Adapter (vodafone, o2, telekom, congstar, einsundeins, saturn) importieren aus dem Paket nur noch .basis statt aus dem Paket-__init__; das __init__ reicht alle Namen für Bestandsimporte weiter und behält _registriere_anbieter_adapter vorerst an seiner Stelle. Der Abnahmetest hält heute fest, was gleich bleiben muss: dieselben Methoden in umgesetzte_methoden(), dieselbe Klasse GeraeteAbrufFehler mit status für jeden Adapter, und dasselbe Ergebnis von _preis je Adapter für Zahl, Zahl als Text, Komma-Text, None, leeren Text, Liste und Dict.

Worktree: /home/claude/telco-radar-wt/P22

## Befund 1

```
Rolle bau darf nicht ändern: pruef/riesendateien.txt
```

## Befund 2

```
Rolle bau darf nicht ändern: pruef/riesendateien.txt
```
