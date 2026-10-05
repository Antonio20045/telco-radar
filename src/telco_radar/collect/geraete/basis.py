"""Was alle Geraete-Adapter teilen: Bauform, Verzeichnis, Fehlerklasse, Preislesung.

Die sechs anbietereigenen Adapter (vodafone, o2, telekom, congstar,
einsundeins, saturn) importieren aus diesem Paket nur dieses Modul. Das
Paket-`__init__` reicht jeden Namen fuer Bestandsimporte weiter und haelt
damit denselben Gegenstand: es gibt genau EINE Klasse `GeraeteAbrufFehler`,
die `sammle_anbieter` faengt, und genau EIN Verzeichnis `ADAPTER`.

Dieses Modul ruft kein Netz und liest keine Datei.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

ADAPTER: dict = {}


@dataclass
class Adapter:
    """Wie eine Quelle gelesen wird.

    `lies(text, url) -> list[rohsatz]` mit den neun Schluesseln
    (titel, preis, waehrung, verfuegbarkeit, sku, ean, farbe, url, quelle)
    und wahlweise `zuzahlung` + `tarif` fuer Buendelpreise.

    `ernte(text, basis_url, pfadmuster, kind) -> list[str]` nur, wenn die
    Adressen nicht als `<a href>` oder `<loc>` dastehen.

    `direkt=True` heisst: die Einstiegsseite IST die Nutzlast, es werden
    keine Produktseiten nachgeladen (so arbeitet Shopify).

    `lies_buendel(text, url) -> list[rohsatz]` ist die ZWEITE Lesart
    derselben Quelle. Fuer einen Einstieg mit `kind: buendel` (o2: eine
    EIGENE Adresse, die nur Buendel traegt) wird sie ANSTELLE von `lies`
    aufgerufen. Fuer einen NORMALEN Einstieg ohne diesen `kind` wird sie
    ZUSAETZLICH zu `lies` auf JEDER Produktseite aufgerufen, die die
    generische Ernte-Schleife ohnehin schon holt (Vodafone, B1,
    05.09.2026: dieselbe Detailantwort traegt Geraetepreis UND
    Buendelpreise, ein zweiter Abruf waere redundant). Ihre Saetze werden
    KEINE Listungen: sie tragen Zuzahlung, Geraeterate, Tarifbetrag und
    Tarifbezug und gehoeren damit in `geraete_tco.json`, nicht in die
    Preisspalte der Geraeteseite.

    `loese_tarifnamen(hole, kopfzeilen, rohbuendel) -> int` ist OPTIONAL
    und laeuft NICHT waehrend des Sammelns, sondern danach, aus der
    Pipeline heraus (`geraete_pipeline.py`) - ein Adapter bleibt sonst ein
    reiner Text-zu-Daten-Uebersetzer ohne eigenes Netz. Sie darf
    zusaetzliche GETs machen, um einen Tarifnamen aufzuloesen, den die
    Sammelantwort selbst nicht nennt (Vodafone: nur ein `offerCoreHash`,
    keine Klarname - siehe `vodafone.py` Modulkopf, Abschnitt B1).

    `ergaenze_buendel(hole, kopfzeilen, rohbuendel) -> int` ist dieselbe
    Bauform fuer BETRAEGE statt Namen (S2-C, 09.09.2026): 1&1 nennt seine
    Bereitstellungsgebuehr erst im Tarifdetails-Iframe, einer eigenen
    Adresse, die die Geräteseite selbst verlinkt. Der Haken macht EIN GET
    je Tarif-Slug und setzt `anschlusspreis` auf den Saetzen - siehe
    `einsundeins.ergaenze_bereitstellungsgebuehr`.

    `buendel_auf_produktseite` (Voreinstellung True) sagt, ob die zweite
    Lesart auf den Produktseiten des ERNTE-Wegs ueberhaupt sinvoll ist.
    Vodafone traegt seine Buendel in derselben Detailantwort wie die
    Listungen (B1) - dort gehoert der Zusatzaufruf hin, ebenso bei
    congstar (seit 29.09.2026: die Produktseite traegt die ganze
    Tarifmatrix des Geraets). Ein Adapter, dessen Produktseiten keine
    Buendel tragen und der sie auf eigenen `kind: buendel`-Einstiegen
    liest, setzt die Flagge auf False - die Einstiege selbst rufen
    `lies_buendel` natuerlich weiterhin.

    `lies_buendel(text, url, proben=None)` - der dritte Parameter ist die
    PROVIDER-PROBE (FM-2, P5-Auftrag 2): der Collector reicht die Bilanz-
    Zaehler des Anbieters hinein, und ein Adapter, der Feld-Proben kennt
    (o2: metric3+metric2 == monthlyPrice usw., Praezedenz Phase S),
    zaehlt hinein, wie viele der erwarteten Saetze ihre Feldebenen noch
    tragen. Adapter ohne Proben ignorieren ihn. Der Zaehler steht danach
    in `Anbieterbilanz.proben` und wird protokolliert - er loest nichts
    aus, er meldet.
    """

    name: str
    lies: Callable
    ernte: Callable | None = None
    direkt: bool = False
    lies_buendel: Callable | None = None
    buendel_auf_produktseite: bool = True
    loese_tarifnamen: Callable | None = None
    ergaenze_buendel: Callable | None = None
    vertiefe_buendel: Callable | None = None
    fuehre_zusammen: Callable | None = None
    confidence: str = "hoch"


def registriere(methode: str, adapter: Adapter) -> None:
    """Traegt den Adapter unter seiner Methode ein; ein zweites Mal ersetzt ihn."""
    ADAPTER[methode] = adapter


def umgesetzte_methoden() -> tuple:
    """Die eingetragenen Methoden, sortiert."""
    return tuple(sorted(ADAPTER))


class GeraeteAbrufFehler(RuntimeError):
    """Der Abruf ist gescheitert - das ist NICHT dasselbe wie "keine Geraete
    auf der Seite". Eigene Klasse, damit der Aufrufer die Seite als ungelesen
    fuehren kann und `mark_stale` ihre Geraete in Ruhe laesst.

    `status` ist der HTTP-Statuscode, WENN der Abruf bis zu einer Antwort
    kam - sonst `None`. Der Unterschied traegt die Unterscheidung zwischen
    einer TOTEN ADRESSE (der Anbieter antwortet "gibt es nicht") und einem
    ungelesenen Abruf (robots-Sperre, Besuchszeit, Netzfehler - keine
    Antwort, keine Aussage). `None` und nicht 0: 0 waere hier ein erfundener
    Statuscode, und geraten wird nichts (CLAUDE.md Clean Code 3). Der
    Aufrufer fragt das Feld ab, NICHT den Meldungstext - ein Zustand, den
    man an einem String erkennt, kippt bei der ersten Umformulierung.
    """

    def __init__(self, *args, status: int | None = None):
        super().__init__(*args)
        self.status = status


def _preis(wert) -> float | None:
    """Ein Betrag aus einer Anbieter-Nutzlast als Zahl, sonst `None`.

    Zahl und Zahl als Text mit Dezimalpunkt werden gelesen; Komma-Text,
    leerer Text, `None`, Liste und Dict bleiben `None`, nie 0.
    """
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None
