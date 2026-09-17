"""Der Gesamtexport des Geraeteradars - zwei CSV-Dateien, kein Klickpfad.

DIE BESCHWERDE, DIE HIER BEANTWORTET WIRD
-----------------------------------------
Die interne Loesung gibt Daten nur je Einzelprodukt oder je Marke heraus.
Wer den Markt ueberblicken will, klickt sich durch Dutzende Downloads und
setzt sie von Hand zusammen. Hier steht der ganze Bestand in EINER Datei,
und die Historie in einer zweiten.

DIESES MODUL FILTERT NICHT SELBST (31.08.2026)
----------------------------------------------
Es bekommt den BESTAND fertig herein (`geraete_view.bestand_und_belastbar()`,
weitergereicht ueber `geraete["bestand"]`) - dieselbe Menge, die der
Geraetekatalog und der Farbbericht zeigen. Es entscheidet nichts darueber,
WAS in der Datei steht, sondern nur, WIE. Wer hier wieder eine Bedingung
einbaut - `status`, `zustand`, ein Preisfilter -, baut eine zweite Menge
zurueck, und sie wird beim naechsten Mal an einer anderen Stelle
auseinanderlaufen. Genau das ist zweimal passiert:

  * Bis dahin suchte sich der Export seine Zeilen mit einer eigenen
    Statusabfrage zusammen, waehrend die Seite ihren Bestand durch
    `geraete_pruefung.pruefe()` schickte. Zwei Rechnungen fuer dieselbe
    Menge sind zwei Mengen: die zwei o2-Listungen, deren Rohfelder sie als
    "erneuert" ausweisen, fielen auf der Seite heraus und standen hier mit
    `Zustand = neu`.
  * Der naheliegende Ausweg - dem Export die GEPRUEFTE Menge zu geben - war
    die Ueberkorrektur. Der Pruefbericht auf `geraete-quellen.html` nennt
    das o2-Paar Galaxy S26 FE 128 GB namentlich und verweist im selben
    Absatz auf diese Datei; die zwei Zeilen fehlten dort. Die Pruefung
    entscheidet, was gegeneinander gerechnet werden darf, nicht, was es
    gibt.

DIE ZUSTANDSSPALTE WIRD ABGELEITET, nicht aus dem Store uebernommen
-------------------------------------------------------------------
Der Store traegt seinen alten Wert bis zum naechsten erfolgreichen Crawl.
Solange der Export die geprueften Zeilen bekam, raeumte
`geraete_pruefung._zustand_veraltet()` das weg; auf dem Bestand tut es das
nicht mehr - und eine Zusicherung, die an einer anderen Stufe haengt, ist
keine. Gelesen wird deshalb dieselbe Ableitung wie in Reiter 2
(`geraete_bereinigung.zustand_der_zeile`). Zwei Antworten auf dieselbe Zelle
waeren der Fehlertyp aus CLAUDE.md §6.

WARUM SEMIKOLON UND WARUM EIN BOM
---------------------------------
Beides fuer genau einen Zweck: dass die Datei sich in Excel mit deutschem
Gebietsschema per Doppelklick korrekt oeffnet, ohne Importassistent.

  * Excel liest CSV im deutschen Gebietsschema mit SEMIKOLON als Trenner -
    das Komma ist dort Dezimaltrenner. Mit Komma getrennt landet die ganze
    Zeile in Spalte A.
  * Ohne BOM haelt Excel die Datei fuer Windows-1252: aus "Größe" wird
    "GrÃ¶ÃŸe". Das BOM ist die einzige Auskunft, die Excel akzeptiert.

Aus demselben Grund tragen Preise ein DEZIMALKOMMA. Eine Zahl mit Punkt
liest Excel im deutschen Gebietsschema als Text - oder, schlimmer, als
Tausendertrennung: aus 1.349,90 wuerde 134990.

DIE PREISART STEHT IN EINER EIGENEN SPALTE, nicht in der Preisspalte. Wer
eine Tabelle nach Preis sortiert, in der 49,95 (Zuzahlung) neben 1349,90
(Ladenpreis) steht, bekommt eine Rangliste, die nichts bedeutet - dieselbe
Disziplin wie im Preisvergleich.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Optional

from .geraete_bereinigung import zustand_der_zeile

# Mit BOM, damit Excel UTF-8 erkennt.
KODIERUNG = "utf-8-sig"
TRENNER = ";"

SPALTEN_AKTUELL = [
    "Anbieter", "Anbietertyp", "Hersteller", "Modell", "Speicher GB", "Farbe",
    "Zustand", "Preis EUR", "Preisart", "Tarifreferenz", "Verfuegbarkeit",
    "Quelle", "Abgerufen am", "Listungs-ID", "SKU-ID",
]

SPALTEN_HISTORIE = [
    "Listungs-ID", "SKU-ID", "Anbieter", "Hersteller", "Modell", "Datum",
    "Preis EUR", "Preisart", "Tarifreferenz", "Verfuegbarkeit", "Quelle",
]

# O4 (STRATEGIE_GERAETE_OPTIK §3): der TCO-Gesamtexport. Die Spalten der
# Bündel-Zeile stehen im Auftrag; drei kommen ehrlich dazu:
#   * "Art" - die Datei trägt Bündel- UND SIM-only-Zeilen, und zwei
#     Zeilentypen ohne Unterscheidungsmerkmal sind in Excel eine Tabelle,
#     die man nicht filtern kann.
#   * "Zustand" - ein erneuertes Gerät ist ein anderer Preis (B1). Ohne
#     die Spalte stünde ein Gebrauchtpreis als Neupreis in der Datei -
#     derselbe Fehlertyp, der aktuell_csv die ZustandsABLEITUNG brachte.
#   * "Bündel/Monat EUR" - 1&1 nennt EINEN Monatsbetrag für Tarif und
#     Gerät (§ 13.2 der Strategie). Ihn auf Tarif/Monat oder Geräterate
#     zu verteilen wäre eine Rechnung dieses Projekts und keine Angabe
#     des Anbieters; ohne die Spalte wäre die Zeile stumm.
SPALTEN_TCO = [
    "Art", "Modell", "Speicher GB", "Anbieter", "Anbietertyp", "Tarif",
    "Band", "Zustand", "Zuzahlung EUR", "Tarif/Monat EUR", "Geräterate EUR",
    "Bündel/Monat EUR", "Laufzeit Monate", "Anschlusspreis EUR",
    "TCO-24 EUR", "Abgerufen am", "Quelle",
]

# O4: der Radar-Export - TCO-24 der Netzbetreiber UND Händler-Barpreis in
# EINER Datei. Die Abweichungsspalte ist der KONSUMENT derselben Rechnung,
# die die Radar-Seite zeigt (`report/wettbewerbsradar.py`): diese Datei
# rechnet keine einzige Prozentzahl selbst, sie liest sie aus der
# Aufbereitung, die auch die Seite rendert - zwei Rechnungen fuer dieselbe
# Zahl sind zwei Zahlen (CLAUDE.md §6).
#
# E5 (AUFTRAG_GERAETE_EINE_SEITE_V2 §7, 17.09.2026): die PREIS-ALARME
# kommen als dritte Zeilenart dazu - der Radar-Reiter trägt seit E3 drei
# Sektionen (Alarme / Abweichung / Händler), und eine Datei, die zwei von
# dreien deckt, lässt die Frage "welcher Wettbewerb ist günstiger?" in der
# anderen Beantwortung aus. Die Alarmzeilen stehen ERSTEN in der Datei,
# dieselbe Reihenfolge wie die Sektionen der Seite. Ihre Abweichung ist
# der BETRAG ohne Vorzeichen - dieselbe Sprache wie die Alarmtabelle
# (E3-Fix B2: jede Alarmzeile ist per Definition ein Wettbewerber-Vorteil,
# ein Minuszeichen trüge nichts bei); Status trägt die ALARM-STUFE
# (Kritisch/Mittel/Gering), nicht den Vergleichsstatus der TCO-Zeilen.
SPALTEN_RADAR = [
    "Art", "Modell", "Hersteller", "Speicher GB", "Anbieter", "Tarif",
    "Tarifband", "Status", "Abweichung %", "Wettbewerber-Preis EUR",
    "Vodafone-Preis EUR", "Preisart", "Grund", "Abgerufen am", "Quelle",
]

# Die drei Zeilenarten der Radar-Datei - dieselben Wörter, mit denen die
# Sektionen der Seite überschrieben sind (S3). Ein zweites Wort für dieselbe
# Art wäre ein zweites Etikett für eine Sache.
ART_ALARM = "Preis-Alarm"
ART_NETZ = "Netzbetreiber TCO-24"
ART_HAENDLER = "Händler Barpreis"


def _zahl(wert) -> str:
    """Dezimalkomma, zwei Stellen - oder leer.

    Kein Tausenderpunkt: er ist in Excel eine zweite Fehlerquelle und wird
    hier nicht gebraucht, weil die Zelle eine ZAHL werden soll.
    """
    if wert is None or wert == "":
        return ""
    try:
        return f"{float(wert):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def _preis_und_art(satz: dict) -> tuple[str, str, str]:
    """(Preis, Preisart, Tarifreferenz) - genau eine Preisart je Zeile."""
    ohne = satz.get("preis_ohne_vertrag")
    if ohne is not None:
        return _zahl(ohne), "ohne Vertrag", ""
    zuzahlung = satz.get("zuzahlung")
    tarif = (satz.get("tarif_referenz") or "").strip()
    if zuzahlung is not None and tarif:
        return _zahl(zuzahlung), "Zuzahlung im Tarifbuendel", tarif
    return "", "", ""


def _schreibe(spalten: list, zeilen: list) -> str:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=TRENNER, lineterminator="\r\n",
                           quoting=csv.QUOTE_MINIMAL)
    schreiber.writerow(spalten)
    schreiber.writerows(zeilen)
    return puffer.getvalue()


def _prozent(wert) -> str:
    """Eine Prozentzahl mit Dezimalkomma, einer Stelle - oder leer.

    Dasselbe Mass wie die Seite: eine Stelle reicht fuer 'um 10 % teurer',
    und mehr Stellen waeren eine Genauigkeit, die die Messung nicht hat.
    """
    if wert is None:
        return ""
    try:
        return f"{float(wert):.1f}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def tco_csv(zeilen: dict) -> tuple[str, int]:
    """Der TCO-Bestand als CSV - eine Zeile je Bündel, plus SIM-only.

    `zeilen` kommt aus `geraete_tco_view.aufbereiten()["export"]`: WERTE
    (Modellname, Band, TCO-24 aus `tco_24`) sind dort aufgelöst, hier wird
    nur FORM gemacht - Dezimalkomma, Semikolon, leere Zelle fuer eine
    Lücke. Die SIM-only-Zeilen tragen ihre TCO-24 als `ueber_horizont`
    (Tarif × 24), gerechnet in derselben Funktion, die auch die Tafel
    fuettert.
    """
    ausgabe = []
    for z in (zeilen or {}).get("buendel", []):
        ausgabe.append([
            "Bündel",
            z.get("modell", ""), z.get("speicher", "") or "",
            z.get("anbieter", ""), z.get("anbieter_typ", ""),
            z.get("tarif", ""), z.get("band", ""), z.get("zustand", ""),
            _zahl(z.get("zuzahlung")), _zahl(z.get("tarif_monatlich")),
            _zahl(z.get("geraet_monatsrate")),
            _zahl(z.get("buendel_monatlich")),
            z.get("laufzeit", "") or "", _zahl(z.get("anschlusspreis")),
            _zahl(z.get("tco24")), z.get("abgerufen_am", ""),
            z.get("quelle_url", ""),
        ])
    for z in (zeilen or {}).get("sim_only", []):
        ausgabe.append([
            "SIM-only", "", "", z.get("anbieter", ""),
            z.get("anbieter_typ", ""), z.get("tarif", ""), z.get("band", ""),
            "", "", _zahl(z.get("tarif_monatlich")), "", "", "",
            _zahl(z.get("anschlusspreis")), _zahl(z.get("tco24")),
            z.get("abgerufen_am", ""), z.get("quelle_url", ""),
        ])
    return _schreibe(SPALTEN_TCO, ausgabe), len(ausgabe)


def _alarm_zeilen(alarme: dict) -> list[list[str]]:
    """Die Alarmzeilen der Radar-Aufbereitung als Tabellenzeilen.

    `alarme` ist `wettbewerbsradar.radar()["alarme"]` - die Aufbereitung
    aus `geraete_alarme.zeilen()`, VOLLSTAENDIG durchgereicht: `sichtbar`
    und `rest` sind zusammen die ganze Tabelle (der Deckel kappt nur die
    Ansicht). Gelesen wird genau das, was die Zeile der Seite trägt -
    Prozent, beide Preise, Laden, Abrufdatum -, nichts wird hier gerechnet.

    `bestimmt` markiert Ausreißer (`auffaellig` aus `geraete_pruefung`):
    ein Ausreißer wird gemeldet statt gelöscht, und gemeldet heißt in
    einer Datei: in der Grundspalte, am selben Ort, an dem die Seite ihn
    neben die Zahl setzt.
    """
    alarme = alarme or {}
    zeilen = list(alarme.get("sichtbar") or []) + list(alarme.get("rest") or [])
    ausgabe = []
    for z in zeilen:
        bester = z.get("bester") or {}
        unser = z.get("unser") or {}
        ausgabe.append([
            ART_ALARM, z.get("modell", ""), z.get("hersteller", ""),
            z.get("speicher", "") or "", bester.get("laden", ""), "", "",
            z.get("stufe_name", ""),
            _prozent(z.get("prozent")), _zahl(bester.get("preis")),
            _zahl(unser.get("preis")), "Gerätepreis ohne Vertrag",
            ("ungewöhnlich großer Abstand – Quelle prüfen"
             if z.get("auffaellig") else ""),
            bester.get("abgerufen_am", ""), bester.get("url", ""),
        ])
    return ausgabe


def radar_csv(view: dict) -> tuple[str, int]:
    """Der Wettbewerbs-Radar als CSV - Alarme, Netzbetreiber-TCO, Händlerpreis.

    `view` ist die Aufbereitung aus `report/wettbewerbsradar.radar()` -
    dieselbe, die die Seite rendert. Die Abweichungsspalte wird daraus
    GELESEN und nicht hier gerechnet: die eine Division steht in
    `wettbewerbsradar._paar_zeile`/`_zeile_fuer_anbieter`/`haendler_zeilen`,
    und ein Export, der sie nachrechnet, kann von der Seite abweichen,
    ohne dass es ein Test sieht. Nicht vergleichbare Zeilen stehen mit
    ihrem STATUS statt einer Zahl - der Export schreibt den Bestand, die
    Ansicht kappt ihn.

    E5: die Alarmzeilen stehen ERSTEN - dieselbe Reihenfolge wie die drei
    Sektionen des Radar-Reiters (Alarme / Abweichung / Händler). Wer die
    Datei nach der Art spaltet, bekommt die Sektionen der Seite als
    Filterwerte.
    """
    ausgabe = _alarm_zeilen((view or {}).get("alarme"))
    for g in (view or {}).get("gruppen", []):
        for z in g.get("zeilen", []):
            ausgabe.append([
                ART_NETZ, g.get("titel", ""),
                g.get("hersteller", ""), g.get("speicher", "") or "",
                z.get("anbieter", ""), z.get("tarif", ""),
                z.get("band_label", ""), z.get("status", ""),
                _prozent(z.get("prozent")), _zahl(z.get("gesamt")),
                _zahl(z.get("vf_gesamt")), "TCO-24",
                z.get("grund", ""), z.get("abgerufen_am", ""),
                z.get("quelle_url", ""),
            ])
    for z in (view or {}).get("haendler", []):
        ausgabe.append([
            ART_HAENDLER, z.get("modell", ""), z.get("hersteller", ""),
            z.get("speicher", "") or "", z.get("anbieter", ""), "", "", "",
            _prozent(z.get("prozent")), _zahl(z.get("preis")),
            _zahl(z.get("vodafone_preis")), "Gerätepreis ohne Vertrag", "",
            z.get("abgerufen_am", ""), z.get("url", ""),
        ])
    return _schreibe(SPALTEN_RADAR, ausgabe), len(ausgabe)


def aktuell_csv(eintraege: list, katalog) -> tuple[str, int]:
    """Der uebergebene Bestand, eine Zeile je Listung. (Inhalt, Zeilenzahl)

    Ohne eigene Auswahl: geschrieben wird GENAU, was hereinkommt. Die
    Entscheidung darueber faellt einmal, in `geraete_view` - siehe Modulkopf.
    Was hier entschieden wird, ist die DARSTELLUNG einer Zelle, und die
    Zustandsspalte wird dafuer abgeleitet statt dem Store geglaubt.
    """
    zeilen = []
    for e in sorted(eintraege, key=lambda x: (x.get("anbieter") or "",
                                              x.get("device_id") or "",
                                              x.get("speicher_gb") or 0)):
        preis, art, tarif = _preis_und_art(e)
        g = katalog.nach_id(e.get("device_id")) if katalog else None
        zeilen.append([
            e.get("anbieter", ""), e.get("anbieter_typ", ""),
            g.hersteller if g else "", g.modell if g else e.get("device_id", ""),
            e.get("speicher_gb") or "",
            e.get("farbe_normalisiert") or e.get("farbe_roh") or "",
            zustand_der_zeile(e),
            preis, art, tarif,
            e.get("verfuegbarkeit", ""), e.get("quelle_url", ""),
            e.get("abgerufen_am", ""), e.get("id", ""), e.get("sku_id", ""),
        ])
    return _schreibe(SPALTEN_AKTUELL, zeilen), len(zeilen)


def historie_csv(punkte: list, eintraege: list, katalog) -> tuple[str, int]:
    """Die Preishistorie DERSELBEN Listungen, eine Zeile je (Listung, Datum).

    Hersteller und Modell kommen aus der Datenbank bzw. dem Katalog, nicht
    aus dem Historienpunkt: der traegt nur `device_id`, und eine Tabelle mit
    einer Spalte voller Kennungen ist in Excel unbrauchbar.

    Gefiltert wird auf die Kennungen aus `eintraege` - also auf denselben
    Bestand, den `aktuell_csv` schreibt. Ohne diesen Schnitt widersprechen
    sich die zwei Dateien: die Historie fuehrte eine Kurve fuer eine
    Listung, die in der aktuellen Tabelle nicht vorkommt, und wer beide
    nebeneinander legt, findet einen Preis ohne Zeile dazu. Der Preis dafuer
    ist, dass mit einer ausgelisteten oder aussortierten Listung auch ihre
    Historie aus dem Export faellt - im STORE bleibt sie unangetastet, und
    die Verweildauer rechnet weiter auf ihr.
    """
    nach_id = {e.get("id"): e for e in eintraege}
    zeilen = []
    for p in sorted(punkte, key=lambda x: (x.get("datum") or "",
                                           x.get("listung_id") or "")):
        if p.get("listung_id") not in nach_id:
            continue
        g = katalog.nach_id(p.get("device_id")) if katalog else None
        eintrag = nach_id.get(p.get("listung_id")) or {}
        preis, art, tarif = _preis_und_art(p)
        zeilen.append([
            p.get("listung_id", ""), p.get("sku_id", "") or eintrag.get("sku_id", ""),
            p.get("anbieter", ""),
            g.hersteller if g else "", g.modell if g else p.get("device_id", ""),
            p.get("datum", ""), preis, art, tarif,
            p.get("verfuegbarkeit", ""), p.get("quelle_url", ""),
        ])
    return _schreibe(SPALTEN_HISTORIE, zeilen), len(zeilen)


def schreibe_exporte(site_dir: Path, eintraege: list, punkte: list, katalog,
                     stand: str = "", tco: dict | None = None,
                     radar: dict | None = None) -> dict:
    """Alle Export-Dateien nach `site/exporte/`. Gibt die Angaben fuer die Seite.

    `eintraege` ist der FERTIG gepruefte und bereinigte Bestand, also
    dieselbe Menge, aus der die Seite ihre Preisaussagen baut. Eine leere
    Liste ist ein zulaessiger Fall - dann entstehen die Dateien mit ihrer
    Kopfzeile, und die Seite nennt daneben eine Null. Ein fehlender Download
    waere die schlechtere Auskunft als ein leerer.

    O4 (STRATEGIE_GERAETE_OPTIK §3) kommen zwei Dateien dazu:
    `geraete-tco.csv` aus `tco` (die aufgeloesten Zeilen aus
    `geraete_tco_view.aufbereiten()["export"]`) und `wettbewerbsradar.csv`
    aus `radar` (die FERTIGE Radar-Aufbereitung - dieselbe Rechnung wie
    die Seite, hier nur formatiert). Beide duerfen leer sein: dann entstehen
    die Dateien mit Kopfzeile und Null Zeilen, wie bei allen anderen.

    Die Zeilenzahl steht NEBEN dem Link, nicht nur in der Datei: wer einen
    Export herunterlaedt, will vorher wissen, ob er sich lohnt - und ein
    leerer Download ist der teuerste Weg, das herauszufinden.
    """
    ordner = Path(site_dir) / "exporte"
    ordner.mkdir(parents=True, exist_ok=True)

    inhalt_a, zeilen_a = aktuell_csv(eintraege or [], katalog)
    inhalt_h, zeilen_h = historie_csv(punkte or [], eintraege or [], katalog)
    (ordner / "geraete-aktuell.csv").write_text(inhalt_a, encoding=KODIERUNG)
    (ordner / "geraete-historie.csv").write_text(inhalt_h, encoding=KODIERUNG)

    inhalt_t, zeilen_t = tco_csv(tco or {})
    (ordner / "geraete-tco.csv").write_text(inhalt_t, encoding=KODIERUNG)
    inhalt_r, zeilen_r = radar_csv(radar or {})
    (ordner / "wettbewerbsradar.csv").write_text(inhalt_r,
                                                 encoding=KODIERUNG)

    return {
        "stand": stand,
        "aktuell": {"datei": "exporte/geraete-aktuell.csv", "zeilen": zeilen_a,
                    "bytes": len(inhalt_a.encode(KODIERUNG))},
        "historie": {"datei": "exporte/geraete-historie.csv", "zeilen": zeilen_h,
                     "bytes": len(inhalt_h.encode(KODIERUNG))},
        "tco": {"datei": "exporte/geraete-tco.csv", "zeilen": zeilen_t,
                "bytes": len(inhalt_t.encode(KODIERUNG))},
        "radar": {"datei": "exporte/wettbewerbsradar.csv", "zeilen": zeilen_r,
                  "bytes": len(inhalt_r.encode(KODIERUNG))},
    }


def leer() -> dict:
    return {"stand": "",
            "aktuell": {"datei": "", "zeilen": 0, "bytes": 0},
            "historie": {"datei": "", "zeilen": 0, "bytes": 0},
            "tco": {"datei": "", "zeilen": 0, "bytes": 0},
            "radar": {"datei": "", "zeilen": 0, "bytes": 0}}
