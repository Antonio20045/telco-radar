"""Der Gesamtexport des Geraeteradars - zwei CSV-Dateien, kein Klickpfad.

DIE BESCHWERDE, DIE HIER BEANTWORTET WIRD
-----------------------------------------
Die interne Loesung gibt Daten nur je Einzelprodukt oder je Marke heraus.
Wer den Markt ueberblicken will, klickt sich durch Dutzende Downloads und
setzt sie von Hand zusammen. Hier steht der ganze Bestand in EINER Datei,
und die Historie in einer zweiten.

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
Disziplin wie in der Positionskarte und im Preisvergleich.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Optional

# Mit BOM, damit Excel UTF-8 erkennt.
KODIERUNG = "utf-8-sig"
TRENNER = ";"

# Ein sichtbarer Bestand ist einer, der noch im Regal steht.
_SICHTBAR = ("aktiv", "vermutlich ausgelistet")

SPALTEN_AKTUELL = [
    "Anbieter", "Anbietertyp", "Hersteller", "Modell", "Speicher GB", "Farbe",
    "Zustand", "Preis EUR", "Preisart", "Tarifreferenz", "Verfuegbarkeit",
    "Quelle", "Abgerufen am", "Listungs-ID", "SKU-ID",
]

SPALTEN_HISTORIE = [
    "Listungs-ID", "SKU-ID", "Anbieter", "Hersteller", "Modell", "Datum",
    "Preis EUR", "Preisart", "Tarifreferenz", "Verfuegbarkeit", "Quelle",
]


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


def aktuell_csv(eintraege: list, katalog) -> tuple[str, int]:
    """Alle sichtbaren Listungen des letzten Standes. (Inhalt, Zeilenzahl)"""
    zeilen = []
    for e in sorted(eintraege, key=lambda x: (x.get("anbieter") or "",
                                              x.get("device_id") or "",
                                              x.get("speicher_gb") or 0)):
        if e.get("status") not in _SICHTBAR:
            continue
        preis, art, tarif = _preis_und_art(e)
        g = katalog.nach_id(e.get("device_id")) if katalog else None
        zeilen.append([
            e.get("anbieter", ""), e.get("anbieter_typ", ""),
            g.hersteller if g else "", g.modell if g else e.get("device_id", ""),
            e.get("speicher_gb") or "",
            e.get("farbe_normalisiert") or e.get("farbe_roh") or "",
            e.get("zustand") or "neu",
            preis, art, tarif,
            e.get("verfuegbarkeit", ""), e.get("quelle_url", ""),
            e.get("abgerufen_am", ""), e.get("id", ""), e.get("sku_id", ""),
        ])
    return _schreibe(SPALTEN_AKTUELL, zeilen), len(zeilen)


def historie_csv(punkte: list, eintraege: list, katalog) -> tuple[str, int]:
    """Die gesamte Preishistorie, eine Zeile je (Listung, Datum, Preis).

    Hersteller und Modell kommen aus der Datenbank bzw. dem Katalog, nicht
    aus dem Historienpunkt: der traegt nur `device_id`, und eine Tabelle mit
    einer Spalte voller Kennungen ist in Excel unbrauchbar.
    """
    nach_id = {e.get("id"): e for e in eintraege}
    zeilen = []
    for p in sorted(punkte, key=lambda x: (x.get("datum") or "",
                                           x.get("listung_id") or "")):
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
                     stand: str = "") -> dict:
    """Beide Dateien nach `site/exporte/`. Gibt die Angaben fuer die Seite.

    Die Zeilenzahl steht NEBEN dem Link, nicht nur in der Datei: wer einen
    Export herunterlaedt, will vorher wissen, ob er sich lohnt - und ein
    leerer Download ist der teuerste Weg, das herauszufinden.
    """
    ordner = Path(site_dir) / "exporte"
    ordner.mkdir(parents=True, exist_ok=True)

    inhalt_a, zeilen_a = aktuell_csv(eintraege, katalog)
    inhalt_h, zeilen_h = historie_csv(punkte, eintraege, katalog)
    (ordner / "geraete-aktuell.csv").write_text(inhalt_a, encoding=KODIERUNG)
    (ordner / "geraete-historie.csv").write_text(inhalt_h, encoding=KODIERUNG)

    return {
        "stand": stand,
        "aktuell": {"datei": "exporte/geraete-aktuell.csv", "zeilen": zeilen_a,
                    "bytes": len(inhalt_a.encode(KODIERUNG))},
        "historie": {"datei": "exporte/geraete-historie.csv", "zeilen": zeilen_h,
                     "bytes": len(inhalt_h.encode(KODIERUNG))},
    }


def leer() -> dict:
    return {"stand": "",
            "aktuell": {"datei": "", "zeilen": 0, "bytes": 0},
            "historie": {"datei": "", "zeilen": 0, "bytes": 0}}
