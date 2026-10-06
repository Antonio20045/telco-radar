"""Der Lückensatz eines Paar-Blocks: wer fehlt, warum, und wo er sonst steht.

Aus `geraete_zeitreihe` ausgelagert (Datenkonzept Geräte Schritt 2). Seit Teil B
gehört jeder Block zu einer Ratenlaufzeit; ein Anbieter, der das Gerät nur mit
anderen Raten führt, steht benannt als „nicht erfasst“, und Alternativen in
anderen Bändern stammen aus derselben Laufzeit.
"""

from __future__ import annotations

from ..tco_model import TCO_HORIZONT, zeitraum_vergleichbar
from . import geraete_notbremse as notbremse
from .geraete_laufzeit import NICHT_ERFASST, ansicht
from .geraete_rechenweg import ANBIETER_FOLGE, _euro, _zeitraum_wort
from .geraete_tco_band import band_label


def _alternativen(
    karten: list, band: str, anbieter: str, laufzeit: int | None = None
) -> list[dict]:
    """Die besten Bänder EINES Anbieters, der im gewählten Band fehlt.

    §4.5: „fehlende Anbieter MIT NAMEN und Alternativ-Bändern samt Betrag
    in Klammern" - der Leser sieht nicht nur DASS einer fehlt, sondern wo
    er steht. Nur ECHTE Karten (Bündel mit SKU oder die Näherung) sagen
    etwas darüber, wo ein Anbieter steht; die Leerkarte der Festanbieter
    ist kein Angebot. Und seit A3 nur FRISCHE: ein altes Angebot ist keine
    Alternative von heute (`geraete_tco_karten.ist_frisch`, Clean Code 7 -
    dieselbe Definition wie Zeilen und Kacheln). Und nur Karten, die
    zaehlen: eine Schätzung ist auch als Alternative kein Preis.

    P0-B-z1: jede Alternative traegt ihren ZEITRAUM mit
    (`leitzahl_monate`, gelesen). Ohne ihn stand im Luecken-Satz ein
    36-Monats-Betrag als „mittel 2.019,54 €" mitten unter
    24-Monats-Zahlen. Und die Wahl der guenstigsten je Band vergleicht
    nur INNERHALB eines Zeitraums: der Zeitraum des Horizonts zuerst,
    sonst der kuerzeste gemessene - ein Minimum ueber zwei Laufzeiten
    waere dieselbe Rangfolge, die das Tor verbietet. Seit Datenkonzept
    Geräte Schritt 2 nennt eine Ansicht nur Alternativen IHRER Ratenlaufzeit.
    """
    beste: dict[str, dict] = {}
    for karte in karten:
        if karte.get("anbieter") != anbieter:
            continue
        if laufzeit is not None and ansicht(karte) != laufzeit:
            continue
        if not karte.get("frisch", True) or not notbremse.zaehlt(karte):
            continue
        if not (karte.get("sku_id") or karte.get("naeherung")):
            continue
        b = karte.get("band")
        if (
            b is None
            or not karte.get("vergleichbar")
            or karte.get("gesamt") is None
            or b == band
        ):
            continue
        monate = karte.get("leitzahl_monate")
        rang = (
            0 if zeitraum_vergleichbar(monate, TCO_HORIZONT) else 1,
            monate if monate is not None else 10**6,
            karte["gesamt"],
        )
        if b not in beste or rang < beste[b]["rang"]:
            beste[b] = {"rang": rang, "tco": karte["gesamt"], "monate": monate}
    return [
        {"band": b, "tco": v["tco"], "monate": v["monate"]}
        for b, v in sorted(beste.items())
    ]


def _luecken(
    zeilen: list,
    karten: list,
    band: str,
    fremd: list | None = None,
    gesperrt: list | None = None,
    laufzeit: int | None = None,
) -> list[dict]:
    """Je erwartetem Anbieter ohne Zeile: der Grund, in EINEM Satz zusammen.

    Antonio 9b.7: „Wenn es nichts gibt, dann brauchst du es nicht
    anzuzeigen von den jeweiligen Anbietern" - die Namen stehen im SAMMEL-
    satz, nie als eigene Zeile mit leerem Inhalt.

    Seit A3 gibt es einen VIERten Grund: der Anbieter führt ein Bündel,
    aber nur mit altem Abruf - „kein Bündel in diesem Band" waere gelogen
    (harte Regel 9), der alte Preis darf aber auch nicht als heutiger
    Alternative-Betrag stehen.

    S2-3 (Diff-Prüfung 21.09.2026): gefragt ist DIESES Band - die
    Frische-Prüfung muss die Karten DES BANDES meinen, nicht alle Karten
    des Anbieters. Vorher gewann der Anbieter-Weitblick: Telekom mit
    einem alten Klein-Bündel (720,76 EUR vom 15.09.) und einem frischen
    Groß-Bündel bekam im Band klein „kein-belastbares" - die Seite sagte
    „Kein Bündel in diesem Band: Telekom", obwohl die alte Klein-Karte
    als alt-Zeile direkt darüber steht. Reihenfolge jetzt: gar kein
    Bündel - kein Bündel in DIESEM Band - nur alter Stand in diesem
    Band - frisch im Band, aber nicht belastbar.

    P0-B-h3 (Befund 3): und als letzter Grund `anderer-zeitraum` - das
    Bündel ist da und belastbar, seine Leitzahl trägt nur einen anderen
    Zeitraum als diese Tafel (1&1, 36 Monate). Er steht ZULETZT, weil er
    die Fälle mit vorhandenem Bündel aufteilt: erst seit P0-B-h3 fällt
    eine solche Karte aus `_band_zeilen` heraus, und "Kein Bündel in
    diesem Band" wäre für sie falsch. `fremd` ist dabei genau der Eimer,
    den das Tor in `_band_zeilen` gefüllt hat - dieselbe Menge, keine
    zweite Ableitung.

    Datenkonzept Geräte Schritt 2: in der Ansicht `laufzeit` zählen nur
    Karten dieser Ratenlaufzeit. Führt ein Anbieter das Gerät nur mit anderen
    Raten, heißt das `nicht-erfasst` - „bietet 12 Monate nicht an“ dürfte nur
    stehen, wenn der Sammler die fehlende Option auf der Seite gesehen hätte.
    """
    gesehen = {z["anbieter"] for z in zeilen}
    luecken = []
    for anbieter in ANBIETER_FOLGE:
        if anbieter in gesehen:
            continue
        alle = [
            k
            for k in karten
            if k["anbieter"] == anbieter and (k.get("sku_id") or k.get("naeherung"))
        ]
        eigene = [k for k in alle if laufzeit is None or ansicht(k) == laufzeit]
        namen = notbremse.namen(
            [k for k in gesperrt or [] if k["anbieter"] == anbieter]
        )
        if not alle:
            grund = "gar-kein-buendel"
        elif not eigene:
            grund = "nicht-erfasst"
        elif not any(k.get("band") == band for k in eigene):
            grund = "anderes-band"
        elif not any(k.get("frisch", True) for k in eigene if k.get("band") == band):
            grund = "nur-alte"
        elif namen:
            grund = "zaehlt-nicht"
        else:
            grund = "kein-belastbares"
        monate = None
        fremde = sorted(
            k["leitzahl_monate"]
            for k in (fremd or [])
            if k["anbieter"] == anbieter and k.get("leitzahl_monate") is not None
        )
        if fremde:
            grund, monate = "anderer-zeitraum", fremde[0]
        luecken.append(
            {
                "anbieter": anbieter,
                "grund": grund,
                "monate": monate,
                "alternativ": _alternativen(karten, band, anbieter, laufzeit),
                "gesperrt": namen,
                "laufzeit": laufzeit,
            }
        )
    return luecken


def _alt_zeitraum(monate, h: int = TCO_HORIZONT) -> str:
    """ " über 36 Monate" - der Zeitraum eines Alternativ-Betrags, oder "".

    Nur bei ABWEICHUNG vom Horizont: eine 24 hinter jeder Zahl in einem
    Satz, der ohnehin von 24 Monaten spricht, waere dieselbe Angabe
    zweimal am selben Ort. Ein unlesbarer Zeitraum wird BENANNT, nie als
    Horizont angenommen (Clean Code 4).
    """
    if zeitraum_vergleichbar(monate, h):
        return ""
    if monate is None:
        return " über eine nicht gemessene Laufzeit"
    return f" über {_zeitraum_wort([monate])}"


def _stufe(band_labels: dict, band: str) -> str:
    """Der Name der Stufe ("XS") aus dem Katalog, sonst aus dem Schluessel."""
    return (band_labels.get(band) or {}).get("label") or band_label(band)


_EIGENER_EIMER = (
    "gar-kein-buendel",
    "nur-alte",
    "kein-belastbares",
    "nicht-erfasst",
)


def _saetze(h: int, laufzeit) -> tuple:
    """Die Satzanfänge je Grund, in der Reihenfolge der Seite."""
    return (
        ("anderes-band", "Kein Bündel in diesem Band: "),
        ("nicht-erfasst", f"Mit {laufzeit} Raten {NICHT_ERFASST}: "),
        ("anderer-zeitraum", f"Nur über eine andere Laufzeit, nicht über {h} Monate: "),
        ("zaehlt-nicht", "Nicht im Vergleich: "),
        ("kein-belastbares", "Kein vollständiger Preis: "),
        ("nur-alte", "Kein aktueller Stand: "),
    )


def _luecke_text(luecken: list, band_labels: dict, h: int = TCO_HORIZONT) -> str | None:
    """Der EINE Lückensatz eines Blocks; `h` ist der Zeitraum der Ansicht."""
    if not luecken:
        return None
    eimer: dict[str, list[str]] = {}
    for lu in luecken:
        name, grund = lu["anbieter"], lu["grund"]
        if lu["alternativ"]:
            alt = " · ".join(
                f"{_stufe(band_labels, a['band'])} "
                f"{_euro(a['tco'])}"
                f"{_alt_zeitraum(a.get('monate'), h)}"
                for a in lu["alternativ"]
            )
            name += f" ({alt})"
        if grund in ("anderer-zeitraum", "nicht-erfasst"):
            name = lu["anbieter"]
            if lu.get("monate") is not None:
                name += f" ({lu['monate']} Monate)"
        if grund == "zaehlt-nicht":
            eimer.setdefault(grund, []).extend(lu["gesperrt"])
            continue
        if grund not in _EIGENER_EIMER and grund != "anderer-zeitraum":
            grund = "anderes-band"
        eimer.setdefault(grund, []).append(name)
    laufzeit = next((lu.get("laufzeit") for lu in luecken), None)
    teile = [
        p + ", ".join(eimer[g]) + "." for g, p in _saetze(h, laufzeit) if eimer.get(g)
    ]
    gar_nicht = eimer.get("gar-kein-buendel") or []
    if gar_nicht:
        teile.append(
            ", ".join(gar_nicht)
            + (" führt" if len(gar_nicht) == 1 else " führen")
            + " das Gerät gar nicht im Bündel."
        )
    return " ".join(teile) or None
