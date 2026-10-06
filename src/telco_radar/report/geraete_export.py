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

from ..tco_model import TCO_HORIZONT
from .geraete_bereinigung import zustand_der_zeile
from .geraete_laufzeit import export_je_laufzeit
from .geraete_radar import STATUS_VERGLEICHBAR
from .geraete_tco_band import band_label

KODIERUNG = "utf-8-sig"
TRENNER = ";"

SPALTEN_AKTUELL = [
    "Anbieter",
    "Anbietertyp",
    "Hersteller",
    "Modell",
    "Speicher GB",
    "Farbe",
    "Zustand",
    "Preis EUR",
    "Preisart",
    "Tarifreferenz",
    "Verfuegbarkeit",
    "Quelle",
    "Abgerufen am",
    "Listungs-ID",
    "SKU-ID",
]

SPALTEN_HISTORIE = [
    "Listungs-ID",
    "SKU-ID",
    "Anbieter",
    "Hersteller",
    "Modell",
    "Datum",
    "Preis EUR",
    "Preisart",
    "Tarifreferenz",
    "Verfuegbarkeit",
    "Quelle",
]

SPALTE_UEBER_24 = "Kosten über 24 Monate EUR"
SPALTE_UEBER_LAUFZEIT = "Kosten über die Bündellaufzeit EUR"


def leitzahl_aus_zeile(zeile):
    """Die Leitzahl einer TCO-Exportzeile, egal unter welchem Kopf sie steht.

    DER EINE Leseweg fuer beide Spalten. Wer nur `SPALTE_UEBER_24` liest,
    bekommt fuer die 74 Buendel mit kombiniertem Monatsbetrag (1&1) eine
    leere Zelle und haelt sie fuer eine fehlende Messung - sie steht aber
    unter `SPALTE_UEBER_LAUFZEIT`, weil ihr Zeitraum nicht 24 Monate ist.

    `zeile` ist ein dict aus `csv.DictReader`. Rueckgabe ist die
    Zeichenkette, wie sie in der Datei steht (deutsches Dezimalkomma), oder
    "" wenn die Zeile keine Leitzahl traegt - dann ist sie wirklich leer.
    """
    return zeile.get(SPALTE_UEBER_24) or zeile.get(SPALTE_UEBER_LAUFZEIT) or ""


def _leitzahl_spalten(tco24, leitzahl_monate):
    """Die Leitzahl in die Spalte, deren Kopf fuer sie WAHR ist.

    Zwei Koepfe, ein Wert: eine Zahl steht unter "Kosten über 24 Monate
    EUR", wenn ihr Zeitraum 24 Monate ist, und sonst unter "Kosten über
    die Buendellaufzeit EUR". Keine Zeile verliert ihren Wert, und kein
    Kopf traegt eine Zahl, die er falsch beschreibt.

    Der Zeitraum wird hier nicht bestimmt, sondern gelesen
    (`Tco.leitzahl_monate`, P0-B-h1) - es gibt genau eine Stelle, die ihn
    festlegt. Fehlt er, ist er eine Luecke und keine 24: dann steht die
    Zahl in der Laufzeitspalte, weil die 24 nicht belegt ist.
    """
    wert = _zahl(tco24)
    if not wert:
        return "", ""
    if leitzahl_monate == TCO_HORIZONT:
        return wert, ""
    return "", wert


SPALTEN_TCO = [
    "Art",
    "Modell",
    "Speicher GB",
    "Anbieter",
    "Anbietertyp",
    "Tarif",
    "Band",
    "Zustand",
    "Zuzahlung EUR",
    "Tarif/Monat EUR",
    "Geräterate EUR",
    "Bündel/Monat EUR",
    "Laufzeit Monate",
    "Anschlusspreis EUR",
    "Leitzahl-Zeitraum Monate",
    SPALTE_UEBER_24,
    SPALTE_UEBER_LAUFZEIT,
    "Abgerufen am",
    "Quelle",
    "SKU-ID",
    "Status",
    "Lücke",
]

SPALTEN_RADAR = [
    "Art",
    "Modell",
    "Hersteller",
    "Speicher GB",
    "Anbieter",
    "Tarif",
    "Tarifband",
    "Status",
    "Abweichung %",
    "Wettbewerber-Preis EUR",
    "Vodafone-Preis EUR",
    "Preisart",
    "Grund",
    "Abgerufen am",
    "Quelle",
]

SPALTEN_MODELL_BARPREIS = [
    "Hersteller",
    "Modell",
    "Speicher GB",
    "Ab-Preis EUR",
    "Anbieter (ab-Preis)",
    "Anbieterzahl",
    "Spanne von EUR",
    "Spanne bis EUR",
    "Nur im Bündel ab EUR/Monat",
    "Bündel-Anbieter",
    "Abgerufen am",
    "Quelle",
]

SPALTEN_MODELL_TCO = [
    "Hersteller",
    "Modell",
    "Speicher GB",
    "TCO ab EUR",
    "Bester Anbieter",
    "Ø EUR/Monat",
    "Abweichung zu Vodafone EUR",
    "Abweichung %",
    "Tarifband",
    "Status",
    "Abgerufen am",
    "Quelle",
]

ART_ALARM = "Preis-Alarm"
ART_NETZ = "Netzbetreiber"
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
    schreiber = csv.writer(
        puffer, delimiter=TRENNER, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL
    )
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
    (Modellname, Band, Kosten über H aus `kosten_ueber`, SIM-only über
    `als_buendel()`) sind dort aufgelöst, hier wird nur FORM gemacht. Die
    SKU-ID (A4) trennt Farbvarianten; „Status“ nennt die Notbremse wie die
    Bündelzeile („Schätzung“, „Aktion abgelaufen“), „Lücke“ die Posten, ohne
    die es keine Kostenzahl gibt (Clean Code 3: benannt, nie 0).

    Der ZEITRAUM H steht als eigene Spalte (`leitzahl_monate`, gelesen aus
    `Kosten.monate`); die Spalte über 24 Monate trägt die Zahl nur bei
    H = 24, sonst steht sie unter `SPALTE_UEBER_LAUFZEIT`.
    """
    ausgabe = []
    for z in (zeilen or {}).get("buendel", []):
        lz_monate = z.get("leitzahl_monate")
        ueber_24, ueber_laufzeit = _leitzahl_spalten(z.get("tco24"), lz_monate)
        ausgabe.append(
            [
                "Bündel",
                z.get("modell", ""),
                z.get("speicher", "") or "",
                z.get("anbieter", ""),
                z.get("anbieter_typ", ""),
                z.get("tarif", ""),
                z.get("band", ""),
                z.get("zustand", ""),
                _zahl(z.get("zuzahlung")),
                _zahl(z.get("tarif_monatlich")),
                _zahl(z.get("geraet_monatsrate")),
                _zahl(z.get("buendel_monatlich")),
                z.get("laufzeit", "") or "",
                _zahl(z.get("anschlusspreis")),
                lz_monate or "",
                ueber_24,
                ueber_laufzeit,
                z.get("abgerufen_am", ""),
                z.get("quelle_url", ""),
                z.get("sku_id", ""),
                z.get("status", ""),
                z.get("luecke", ""),
            ]
        )
    for z in (zeilen or {}).get("sim_only", []):
        lz_monate = z.get("leitzahl_monate")
        ueber_24, ueber_laufzeit = _leitzahl_spalten(z.get("tco24"), lz_monate)
        ausgabe.append(
            [
                "SIM-only",
                "",
                "",
                z.get("anbieter", ""),
                z.get("anbieter_typ", ""),
                z.get("tarif", ""),
                z.get("band", ""),
                "",
                "",
                _zahl(z.get("tarif_monatlich")),
                "",
                "",
                "",
                _zahl(z.get("anschlusspreis")),
                lz_monate or "",
                ueber_24,
                ueber_laufzeit,
                z.get("abgerufen_am", ""),
                z.get("quelle_url", ""),
                "",
                "",
                "",
            ]
        )
    return _schreibe(SPALTEN_TCO, ausgabe), len(ausgabe)


def _alarm_zeilen(alarme: dict) -> list[list[str]]:
    """Die Alarmzeilen der Radar-Aufbereitung als Tabellenzeilen.

    `alarme` ist `geraete_radar.radar()["alarme"]` - die Aufbereitung
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
        ausgabe.append(
            [
                ART_ALARM,
                z.get("modell", ""),
                z.get("hersteller", ""),
                z.get("speicher", "") or "",
                bester.get("laden", ""),
                "",
                "",
                z.get("stufe_name", ""),
                _prozent(z.get("prozent")),
                _zahl(bester.get("preis")),
                _zahl(unser.get("preis")),
                "Gerätepreis ohne Vertrag",
                (
                    "ungewöhnlich großer Abstand – Quelle prüfen"
                    if z.get("auffaellig")
                    else ""
                ),
                bester.get("abgerufen_am", ""),
                bester.get("url", ""),
            ]
        )
    return ausgabe


def _preisart_netz(z: dict, gruppe: dict) -> str:
    """Preisart einer Netzbetreiber-Zeile - nur mit Zeitraum, wo er BELEGT ist.

    Ein Paar trägt Ratenlaufzeit und Zeitraum seiner Vodafone-Karte selbst
    (Datenkonzept Geräte Schritt 2). Sonst wird ein Zeitraum nur genannt, wenn
    die Zeile per Betragsgleichheit gegen DIESELBE Vodafone-Karte geprüft
    wurde wie `gruppe["vodafone"]` (Clean Code 3: kein geratener Zeitraum).
    """
    if z.get("status") == STATUS_VERGLEICHBAR and z.get("laufzeit") and z.get("monate"):
        return f"Kosten über {z['monate']} Monate · {z['laufzeit']} Raten"
    vf = gruppe.get("vodafone") or {}
    monate = vf.get("monate")
    if (
        z.get("status") == STATUS_VERGLEICHBAR
        and monate
        and z.get("vf_gesamt") == vf.get("gesamt")
    ):
        return f"Kosten über {monate} Monate"
    return "Kosten über die Bündellaufzeit"


def _grund_netz(z: dict, g: dict) -> str:
    """Der Grund einer Netzbetreiber-Zeile - nie eine stille Lücke.

    Traegt die Zeile selbst schon einen Grund (Band-Mismatch, kein
    Bündel, anderer Zustand, anderer Zeitraum - siehe `geraete_radar.py`),
    bleibt er unveraendert. Nur wenn die Zeile KEINEN eigenen Grund traegt
    UND die Gruppe schon sagt, warum es gar keine Vodafone-Basis gibt,
    wird dieser eine, schon vorhandene Satz auch an der Zeile genannt -
    sonst stuende die Zeile mit Strich und ohne jede Erklaerung da.
    """
    grund = z.get("grund", "")
    if grund:
        return grund
    if g.get("vodafone") is None:
        return g.get("vodafone_grund", "")
    return ""


def radar_csv(view: dict) -> tuple[str, int]:
    """Der Wettbewerbs-Radar als CSV - Alarme, Netzbetreiber-TCO, Händlerpreis.

    `view` ist die Aufbereitung aus `report/geraete_radar.radar()` -
    dieselbe, die die Seite rendert. Die Abweichungsspalte wird daraus
    GELESEN und nicht hier gerechnet: die eine Division steht in
    `geraete_radar._paar_zeile`/`_zeile_fuer_anbieter`/`haendler_zeilen`,
    und ein Export, der sie nachrechnet, kann von der Seite abweichen,
    ohne dass es ein Test sieht. Nicht vergleichbare Zeilen stehen mit
    ihrem STATUS statt einer Zahl - der Export schreibt den Bestand, die
    Ansicht kappt ihn.

    E5: die Alarmzeilen stehen ERSTEN - dieselbe Reihenfolge wie die drei
    Sektionen des Radar-Reiters (Alarme / Abweichung / Händler). Wer die
    Datei nach der Art spaltet, bekommt die Sektionen der Seite als
    Filterwerte.

    P0-B-h4: die Preisart-Zelle der Netzbetreiber-Zeilen kommt aus
    `_preisart_netz` und behauptet keinen Zeitraum mehr, den die Zeile
    nicht nachweislich trägt (siehe dort).

    P0-B-z3: `ART_NETZ` nennt nur noch die Sektion ("Netzbetreiber"), nicht
    mehr fest "Kosten über 24 Monate" (Befund 2 - derselbe Zeitraum steht
    in der Preisart-Zelle jeder Zeile). Der Grund kommt aus `_grund_netz`
    (Befund 3): eine Zeile ohne Wert UND ohne eigenen Grund bekommt den
    Grund ihrer Gruppe, statt eine stille Lücke zu bleiben.
    """
    ausgabe = _alarm_zeilen((view or {}).get("alarme"))
    for g in (view or {}).get("gruppen", []):
        for z in g.get("zeilen", []):
            ausgabe.append(
                [
                    ART_NETZ,
                    g.get("titel", ""),
                    g.get("hersteller", ""),
                    g.get("speicher", "") or "",
                    z.get("anbieter", ""),
                    z.get("tarif", ""),
                    z.get("band_label", ""),
                    z.get("status", ""),
                    _prozent(z.get("prozent")),
                    _zahl(z.get("gesamt")),
                    _zahl(z.get("vf_gesamt")),
                    _preisart_netz(z, g),
                    _grund_netz(z, g),
                    z.get("abgerufen_am", ""),
                    z.get("quelle_url", ""),
                ]
            )
    for z in (view or {}).get("haendler", []):
        ausgabe.append(
            [
                ART_HAENDLER,
                z.get("modell", ""),
                z.get("hersteller", ""),
                z.get("speicher", "") or "",
                z.get("anbieter", ""),
                "",
                "",
                "",
                _prozent(z.get("prozent")),
                _zahl(z.get("preis")),
                _zahl(z.get("vodafone_preis")),
                "Gerätepreis ohne Vertrag",
                "",
                z.get("abgerufen_am", ""),
                z.get("url", ""),
            ]
        )
    return _schreibe(SPALTEN_RADAR, ausgabe), len(ausgabe)


def modell_barpreis_csv(modelle: list) -> tuple[str, int]:
    """Die Barpreis-Ansicht des Modell-Katalogs als CSV - eine Zeile je Modell.

    `modelle` kommt aus `geraete_view.katalog_modellzeilen()`: WERTE sind
    dort aufgeloöst (ab-Preis, Anbieter, Spanne, Bündel-Monatspreis mit
    Beleg), hier entsteht nur FORM - Dezimalkomma, Semikolon, leere Zelle
    fuer eine Luecke. Keine Zeile ohne Preisform: der Barpreis ODER der
    benannte Bündel-Zustand ("nur im Bündel, ab X EUR/Monat") - die Spalte
    `Ab-Preis EUR` bleibt leer, wenn er nicht gemessen ist, und die
    Monatsangabe steht in ihrer eigenen.
    """
    ausgabe = []
    for m in modelle or []:
        beleg = m.get("ab_beleg") or {}
        buendel = m.get("buendel_beleg") or {}
        ausgabe.append(
            [
                m.get("hersteller", ""),
                m.get("modell", ""),
                m.get("speicher") or "",
                _zahl(m.get("ab_preis")),
                m.get("ab_anbieter") or "",
                m.get("anbieterzahl") or 0,
                _zahl((m.get("spanne") or [None, None])[0]),
                _zahl((m.get("spanne") or [None, None])[1]),
                _zahl(m.get("buendel_monat")),
                m.get("buendel_anbieter") or "",
                (beleg.get("abgerufen_am") or buendel.get("abgerufen_am") or ""),
                (beleg.get("quelle_url") or buendel.get("quelle_url") or ""),
            ]
        )
    return _schreibe(SPALTEN_MODELL_BARPREIS, ausgabe), len(ausgabe)


def modell_tco_csv(modelle: list) -> tuple[str, int]:
    """Die TCO-Ansicht des Modell-Katalogs als CSV - eine Zeile je Modell.

    Gelesen wird genau das, was die TCO-Spalte der Modellzeile traegt
    (`_tco_spalte` in `geraete_view`): die Leitzahl des besten
    vergleichbaren Angebots, sein Anbieter, sein Ø je Monat, die
    Abweichung des guenstigen Wettbewerber-Angebots zur
    Vodafone-Referenz (wo Vodafone selbst fuehrt, der Abstand des
    naechsten Wettbewerbers) und sein Tarifband. Eine Zeile ohne Zahl
    oder ohne Abstand traegt den benannten Grund in der Statusspalte -
    gerechnet wird hier nichts.
    """
    ausgabe = []
    for m in modelle or []:
        beleg = m.get("tco_beleg") or {}
        ausgabe.append(
            [
                m.get("hersteller", ""),
                m.get("modell", ""),
                m.get("speicher") or "",
                _zahl(m.get("tco_ab")),
                m.get("tco_anbieter") or "",
                _zahl(m.get("tco_monat")),
                _zahl(m.get("tco_delta")),
                _prozent(m.get("tco_delta_prozent")),
                band_label(m.get("tco_band")),
                m.get("tco_leer") or m.get("tco_delta_leer") or "",
                beleg.get("abgerufen_am", ""),
                beleg.get("quelle_url", ""),
            ]
        )
    return _schreibe(SPALTEN_MODELL_TCO, ausgabe), len(ausgabe)


def aktuell_csv(eintraege: list, katalog) -> tuple[str, int]:
    """Der uebergebene Bestand, eine Zeile je Listung. (Inhalt, Zeilenzahl)

    Ohne eigene Auswahl: geschrieben wird GENAU, was hereinkommt. Die
    Entscheidung darueber faellt einmal, in `geraete_view` - siehe Modulkopf.
    Was hier entschieden wird, ist die DARSTELLUNG einer Zelle, und die
    Zustandsspalte wird dafuer abgeleitet statt dem Store geglaubt.
    """
    zeilen = []
    for e in sorted(
        eintraege,
        key=lambda x: (
            x.get("anbieter") or "",
            x.get("device_id") or "",
            x.get("speicher_gb") or 0,
        ),
    ):
        preis, art, tarif = _preis_und_art(e)
        g = katalog.nach_id(e.get("device_id")) if katalog else None
        zeilen.append(
            [
                e.get("anbieter", ""),
                e.get("anbieter_typ", ""),
                g.hersteller if g else "",
                g.modell if g else e.get("device_id", ""),
                e.get("speicher_gb") or "",
                e.get("farbe_normalisiert") or e.get("farbe_roh") or "",
                zustand_der_zeile(e),
                preis,
                art,
                tarif,
                e.get("verfuegbarkeit", ""),
                e.get("quelle_url", ""),
                e.get("abgerufen_am", ""),
                e.get("id", ""),
                e.get("sku_id", ""),
            ]
        )
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
    for p in sorted(
        punkte, key=lambda x: (x.get("datum") or "", x.get("listung_id") or "")
    ):
        if p.get("listung_id") not in nach_id:
            continue
        g = katalog.nach_id(p.get("device_id")) if katalog else None
        eintrag = nach_id.get(p.get("listung_id")) or {}
        preis, art, tarif = _preis_und_art(p)
        zeilen.append(
            [
                p.get("listung_id", ""),
                p.get("sku_id", "") or eintrag.get("sku_id", ""),
                p.get("anbieter", ""),
                g.hersteller if g else "",
                g.modell if g else p.get("device_id", ""),
                p.get("datum", ""),
                preis,
                art,
                tarif,
                p.get("verfuegbarkeit", ""),
                p.get("quelle_url", ""),
            ]
        )
    return _schreibe(SPALTEN_HISTORIE, zeilen), len(zeilen)


def schreibe_exporte(
    site_dir: Path,
    eintraege: list,
    punkte: list,
    katalog,
    stand: str = "",
    tco: dict | None = None,
    radar: dict | None = None,
    modelle: list | None = None,
) -> dict:
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

    P3 (17.09.2026) kommen die zwei Ansichts-Dateien des Modell-Katalogs
    dazu (`modelle` aus `geraete_view.katalog_modellzeilen`):
    `geraete-modell-barpreis.csv` und `geraete-modell-tco.csv` - je Ansicht
    eine Datei, kein Formatmix.

    Die Zeilenzahl steht NEBEN dem Link, nicht nur in der Datei: wer einen
    Export herunterlaedt, will vorher wissen, ob er sich lohnt - und ein
    leerer Download ist der teuerste Weg, das herauszufinden.

    Datenkonzept Geräte 5.4: der Bündel-Export folgt dem Umschalter der
    Ratenlaufzeit. Je Ansicht entsteht `geraete-tco-<N>.csv` mit genau ihren
    Bündeln (`tco_je_laufzeit`, `geraete_laufzeit.export_je_laufzeit`);
    `geraete-tco.csv` bleibt der Gesamtexport für „alle“.
    """
    ordner = Path(site_dir) / "exporte"
    ordner.mkdir(parents=True, exist_ok=True)

    def datei(name: str, inhalt: str, zeilen: int) -> dict:
        (ordner / name).write_text(inhalt, encoding=KODIERUNG)
        groesse = len(inhalt.encode(KODIERUNG))
        return {"datei": f"exporte/{name}", "zeilen": zeilen, "bytes": groesse}

    return {
        "stand": stand,
        "aktuell": datei("geraete-aktuell.csv", *aktuell_csv(eintraege or [], katalog)),
        "historie": datei(
            "geraete-historie.csv",
            *historie_csv(punkte or [], eintraege or [], katalog),
        ),
        "tco": datei("geraete-tco.csv", *tco_csv(tco or {})),
        "tco_je_laufzeit": {
            lz: datei(f"geraete-tco-{lz}.csv", *tco_csv(teil))
            for lz, teil in export_je_laufzeit(tco or {}).items()
        },
        "radar": datei("wettbewerbsradar.csv", *radar_csv(radar or {})),
        "modell_barpreis": datei(
            "geraete-modell-barpreis.csv", *modell_barpreis_csv(modelle or [])
        ),
        "modell_tco": datei("geraete-modell-tco.csv", *modell_tco_csv(modelle or [])),
    }


def leer() -> dict:
    return {
        "stand": "",
        "aktuell": {"datei": "", "zeilen": 0, "bytes": 0},
        "historie": {"datei": "", "zeilen": 0, "bytes": 0},
        "tco": {"datei": "", "zeilen": 0, "bytes": 0},
        "tco_je_laufzeit": {},
        "radar": {"datei": "", "zeilen": 0, "bytes": 0},
        "modell_barpreis": {"datei": "", "zeilen": 0, "bytes": 0},
        "modell_tco": {"datei": "", "zeilen": 0, "bytes": 0},
    }
