"""Die Adresszahlen eines Geräteradar-Laufs (aus ``geraete_pipeline``)."""


def adressbilanz(bilanz) -> tuple:
    """Die zwei ADRESSZAHLEN eines Laufs - oder zweimal `None`.

    `(produkte_versucht, tote_adressen)`. "Keine Produktadresse versucht"
    ist KEINE Null: ein uebersprungener Anbieter, ein toter Einstieg und
    ein Adapter ohne Produktseiten haben nichts gemessen, und eine 0
    daneben waere die Entwarnung "versucht, keine war tot" - genau die,
    die `test_ein_lauf_ohne_produktseiten_bucht_keine_null` fuer den
    Bestand verbietet und die bis zum 22.09.2026 trotzdem im
    Protokoll-JSON stand (CLAUDE.md Clean Code 3).

    EINE Rechnung fuer beide Kanaele - Bestand und Protokoll -, damit die
    Seite nicht etwas anderes zaehlt als das Log (Clean Code 7). Aus dem
    Bestand wird daraus die Reihe, an der `geraete_store.ALARM_EROSION`
    eine ueber Tage wegbroeselnde Quelle erkennt.
    """
    if bilanz.produkte_versucht <= 0:
        return (None, None)
    return (bilanz.produkte_versucht, len(bilanz.tote_adressen))
