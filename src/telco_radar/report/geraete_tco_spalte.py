"""Die TCO-Felder einer Modellzeile des Geräte-Katalogs (`geraete_view`).

Aus `geraete_view` herausgelöst: die Wahl des besten vergleichbaren Angebots, die
Abstandsfelder und die benannten Lücken, wenn keines zählt.
"""

from __future__ import annotations

from ..tco_model import TCO_HORIZONT, zeitraum_vergleichbar
from . import geraete_notbremse as notbremse
from . import geraete_tco_karten
from .geraete_laufzeit import LAUFZEIT_STANDARD, ansicht
from .geraete_tco_band import band_label

TCO_LEER_KEIN_BUNDEL = "kein Bündel gemessen"
TCO_LEER_KEIN_VERGLEICHBARES = "kein vergleichbares Bündel gemessen"
TCO_LEER_KEIN_BAND = "kein vergleichbares Bündel im Tarif"
TCO_LEER_NUR_ALT = "kein aktueller Bündel-Stand"
TCO_LEER_ANDERE_LAUFZEIT = f"kein Bündel mit {LAUFZEIT_STANDARD} Raten"

TCO_DELTA_LEER_KEINE_REFERENZ = "keine Referenz"
TCO_DELTA_GRUND_KEINE_REFERENZ = (
    "Vodafone listet dieses Modell nicht - deshalb ist kein Abstand "
    "berechenbar (die Referenz fehlt)"
)
TCO_DELTA_LEER_KEIN_WETTBEWERBER = "kein Wettbewerber-Angebot"
TCO_DELTA_GRUND_KEIN_WETTBEWERBER = (
    "Vodafone listet dieses Modell, aber kein Wettbewerber-Angebot ist "
    "vergleichbar erhoben - deshalb ist kein Abstand berechenbar"
)
TCO_DELTA_GRUND_ANDERE_LAUFZEIT = (
    "Das günstigste Wettbewerber-Angebot trägt einen anderen Zeitraum als "
    "die Vodafone-Referenz - über zwei Laufzeiten gibt es keinen Abstand"
)
TCO_DELTA_LEER_ALTE_REFERENZ = "kein aktueller Referenz-Stand"
TCO_DELTA_GRUND_ALTE_REFERENZ = (
    "Die Vodafone-Referenz ist nicht aktuell erhoben - ein Abstand gegen "
    "sie wäre kein Abstand von heute"
)
TCO_DELTA_LEER_UNBESTIMMT = "Abstand unbestimmt"
TCO_DELTA_GRUND_UNBESTIMMT = (
    "Zu diesem Wettbewerber-Angebot ist kein Abstand zur Vodafone-Referenz gerechnet"
)


def tco_leer(grund: str) -> dict:
    """Die TCO-Felder einer Modellzeile ohne bestes Bündel, mit benanntem Grund."""
    return {
        "tco_ab": None,
        "tco_anbieter": None,
        "tco_monat": None,
        "tco_band": None,
        "tco_band_label": "",
        "tco_beleg": None,
        "tco_leer": grund,
        "tco_delta": None,
        "tco_delta_prozent": None,
        "tco_delta_kurz": None,
        "tco_delta_anbieter": None,
        "tco_delta_leer": None,
        "tco_delta_leer_grund": None,
    }


def tco_spalte(
    modell_tco: dict | None, heute: str = "", band: str | None = None
) -> dict:
    """Die TCO-Felder EINER Modellzeile aus der TCO-Aufbereitung.

    `modell_tco` ist ein Eintrag aus `geraete_tco_view.aufbereiten()
    ["modelle"]` - dessen Karten tragen `delta_kurz` und `band` schon
    fertig (beide werden dort NACH `modelle()` gesetzt). Hier wird nichts
    gerechnet, nur das beste vergleichbare Angebot gewaehlt: DIE EINE REGEL
    von P3 - zwei Rechnungen fuer dieselbe Zahl sind zwei Zahlen. Das
    "beste" Angebot ist die guenstigste belastbare, vergleichbare Karte
    ohne Naeherung; `delta_kurz` existiert nur mit Vodafone-Referenz und
    wird unverändert durchgereicht.

    A2-Nachbesserung (Pruef-Befund 20.09.2026, schwer: hoch): die Leitzahl
    und der Abstand haben SEITDEM ZWEI TRAEGER. Gewann das EIGENE Buendel
    das Minimum (20 von 48 "keine Referenz"-Zeilen des Bestands, z. B.
    Galaxy A57 256: Vodafone 1.199,80 vor 1&1 1.207,54), lieferte `_delta`
    fuer die eigene Karte None (B4) - und die Delta-Zelle behauptete die
    fehlende Referenz, obwohl die TCO-Zelle derselben Zeile "bei Vodafone"
    sagte. Jetzt stellt das eigene Angebot weiterhin die Leitzahl; der
    Abstand gehoert dem guenstigsten FREMDEN Angebot (der Wert, den die
    Wr-Zeile desselben Modells schon zeigt). Ist kein fremdes Angebot
    vergleichbar, heisst die Luecke "kein Wettbewerber-Angebot" - nicht
    "keine Referenz", denn die Referenz ist das eigene Angebot selbst.

    P0-B-h2 und Datenkonzept Geräte Schritt 2: DIE SPALTE IST DIE
    STANDARDANSICHT (24 Raten über `TCO_HORIZONT`, wie ihr Kopf und die
    Vodafone-Referenz). Andere Zahlen werden BENANNT: die Zeile sagt "kein
    Bündel mit 24 Raten", die Δ-Zelle "andere Laufzeit".

    Notbremse (Datenkonzept Geräteradar, Schritt 1): Bester und Traeger
    des Abstands sind nur Karten mit `zaehlt`. Zaehlt keine, nennt die
    Zeile den Zustand der Karte ("Schätzung", "Aktion abgelaufen"), die
    Δ-Zelle ebenso, wenn nur ein nicht zaehlendes fremdes Angebot bleibt.

    `band` (Nachbesserung 1&1 24+12): ohne Angabe waehlt die Spalte das
    guenstigste Angebot ALLER Baender (die Katalogkarte nennt es als "ab"
    samt Tarif). Mit Angabe zaehlen nur Karten DIESES Bandes - der Export
    und das Diagramm der Preisposition nennen so fuer jeden Anbieter
    dasselbe Band (M), nie bei einem Anbieter S und bei anderen M. Gibt es
    in dem Band keine Karte, steht die Luecke `TCO_LEER_KEIN_BAND`.
    """
    if not modell_tco:
        return tco_leer(TCO_LEER_KEIN_BUNDEL)
    pool = [
        k
        for k in modell_tco.get("karten") or []
        if (band is None or k.get("band") == band)
        and k.get("vergleichbar")
        and k.get("belastbar")
        and not k.get("naeherung")
        and k.get("gesamt") is not None
    ]
    kandidaten = [k for k in pool if k.get("frisch", True)]
    if not kandidaten:
        if pool:
            return tco_leer(TCO_LEER_NUR_ALT)
        if band is not None and modell_tco.get("karten"):
            return tco_leer(f"{TCO_LEER_KEIN_BAND} {band_label(band)}")
        return tco_leer(TCO_LEER_KEIN_VERGLEICHBARES)
    vergleichbare = [
        k
        for k in kandidaten
        if ansicht(k) == LAUFZEIT_STANDARD
        and zeitraum_vergleichbar(k.get("leitzahl_monate"), TCO_HORIZONT)
    ]
    if not vergleichbare:
        return tco_leer(TCO_LEER_ANDERE_LAUFZEIT)
    zaehlende = list(filter(notbremse.zaehlt, vergleichbare))
    if not zaehlende:
        gesperrt = min(vergleichbare, key=lambda k: k["gesamt"])
        return tco_leer(notbremse.gruende([gesperrt]))
    bester = min(zaehlende, key=lambda k: k["gesamt"])
    fremde = [k for k in zaehlende if not k.get("eigen")]
    traeger = (
        bester
        if not bester.get("eigen")
        else (min(fremde, key=lambda k: k["gesamt"]) if fremde else None)
    )
    im_zeitraum = {id(k) for k in zaehlende}
    ohne_abstand = [
        k for k in kandidaten if not k.get("eigen") and id(k) not in im_zeitraum
    ]
    referenz = modell_tco.get("referenz")
    if traeger is not None and traeger.get("delta_kurz"):
        delta_leer, delta_leer_grund = None, None
    elif referenz is None:
        delta_leer = TCO_DELTA_LEER_KEINE_REFERENZ
        delta_leer_grund = TCO_DELTA_GRUND_KEINE_REFERENZ
    elif not geraete_tco_karten.referenz_ist_frisch(referenz, heute):
        delta_leer = TCO_DELTA_LEER_ALTE_REFERENZ
        delta_leer_grund = TCO_DELTA_GRUND_ALTE_REFERENZ
    elif traeger is None and ohne_abstand:
        zustand = (
            min(ohne_abstand, key=lambda k: k["gesamt"]).get("delta_zustand") or {}
        )
        delta_leer = zustand.get("kurz") or geraete_tco_karten.DELTA_ANDERE_LAUFZEIT
        delta_leer_grund = zustand.get("satz") or TCO_DELTA_GRUND_ANDERE_LAUFZEIT
    elif traeger is None:
        delta_leer = TCO_DELTA_LEER_KEIN_WETTBEWERBER
        delta_leer_grund = TCO_DELTA_GRUND_KEIN_WETTBEWERBER
    else:
        zustand = traeger.get("delta_zustand") or {}
        delta_leer = zustand.get("kurz") or TCO_DELTA_LEER_UNBESTIMMT
        delta_leer_grund = zustand.get("satz") or TCO_DELTA_GRUND_UNBESTIMMT
    delta = (traeger or {}).get("delta") or {}
    delta_traeger = (traeger or {}).get("anbieter")
    return {
        "tco_ab": bester["gesamt"],
        "tco_anbieter": bester.get("anbieter"),
        "tco_monat": bester.get("schnitt_monat"),
        "tco_delta": delta.get("betrag"),
        "tco_delta_prozent": delta.get("prozent"),
        "tco_delta_kurz": (traeger or {}).get("delta_kurz"),
        "tco_delta_anbieter": delta_traeger if bester.get("eigen") else None,
        "tco_delta_traeger": delta_traeger,
        "tco_delta_leer": delta_leer,
        "tco_delta_leer_grund": delta_leer_grund,
        "tco_band": bester.get("band"),
        "tco_band_label": band_label(bester.get("band")),
        "tco_beleg": {
            "quelle_url": bester.get("quelle_url", ""),
            "abgerufen_am": bester.get("abgerufen_am", ""),
        },
        "tco_leer": None,
    }
