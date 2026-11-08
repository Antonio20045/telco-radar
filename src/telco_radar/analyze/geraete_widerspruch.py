"""Ein abgeleiteter Preis, den eine gelesene Zeile widerlegt, zählt nicht.

1&1 leitet die Tarifstufen aus einem Grundangebot und dem Tarifaufschlag ab
(`einsundeins.ergaenze_tarifstufen`); die Ablöse hängt nur an der Gerätevariante.
Steht für dieselbe Variante (`sku_id`) und Ratenlaufzeit eine gelesene Zeile
(`quelle_art == QUELLE_KLICK`) mit anderer Zuzahlung, stammt die Ableitung aus dem
falschen Grundangebot. Ohne gelesene Gegenzeile ist nichts zu widerlegen; andere
Anbieter rechnen die Zuzahlung je Tarif verschieden und fallen nicht darunter
(`HERLEITUNG_PREISLISTE`).

Zweite Regel, `mit_einheitlicher_einmalzahlung` (Manager, 05.11.2026): Die Einmalzahlung
bei Kündigung nach Monat 24 ist bei 1&1 ein Gerätewert und gleich über alle Tarife
desselben Geräts (gleiche Speichergröße). Gilt bei mindestens zwei Tarifen ein anderer
Wert als der häufigste, verliert der abweichende Tarif seine Einmalzahlung und steht
als benannte Lücke (`HERLEITUNG_EINMALZAHLUNG`), nie als Zahl. Ohne eindeutig
häufigsten Wert gilt kein Tarif des Geräts als belegt. Nur ein Tarif je Gerät: keine
Prüfung.

EINE Definition (Clean Code 7): Tabelle, Bild, Teurer-Liste und Export lesen die
Bündelliste, die `bereinigt` übrig lässt. Lieber ein Preis weniger als ein falscher.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import replace

from ..tarif_model import QUELLE_KLICK
from ..tco_model import TCO_HORIZONT, Buendel
from .geraete_pruefstatus import HERLEITUNG_EINMALZAHLUNG, HERLEITUNG_PREISLISTE

log = logging.getLogger(__name__)

ZUZAHLUNG_TOLERANZ = 0.005
EINMALZAHLUNG_ANBIETER = "1&1"


def _variante(b: Buendel) -> tuple:
    """Gerätevariante und Ratenlaufzeit: dafür ist die Ablöse gleich."""
    return (b.anbieter, b.sku_id, b.laufzeit_monate)


def _abgeleitet(b: Buendel) -> float | None:
    """Die abgeleitete Zuzahlung, sonst None."""
    if b.herleitung.strip() in HERLEITUNG_PREISLISTE:
        return b.geraet_zuzahlung
    return None


def _gelesen(b: Buendel) -> float | None:
    """Die gelesene Zuzahlung, sonst None."""
    return b.geraet_zuzahlung if b.quelle_art == QUELLE_KLICK else None


def _widerlegt(abgeleitet: float, gelesen: Iterable[float]) -> bool:
    return any(abs(z - abgeleitet) > ZUZAHLUNG_TOLERANZ for z in gelesen)


def ohne_widerlegte(buendel: Iterable) -> list:
    """Die Bündel ohne die abgeleiteten, deren Zuzahlung eine gelesene Zeile widerlegt.

    Kein Buendel-Objekt (unlesbarer Satz) bleibt unberührt. Jedes Weglassen steht
    im Protokoll."""
    liste = list(buendel)
    gelesen: dict[tuple, list[float]] = {}
    for b in liste:
        if isinstance(b, Buendel) and (z := _gelesen(b)) is not None:
            gelesen.setdefault(_variante(b), []).append(z)
    if not gelesen:
        return liste
    rest = []
    for b in liste:
        abg = _abgeleitet(b) if isinstance(b, Buendel) else None
        if abg is None or not _widerlegt(abg, gelesen.get(_variante(b), ())):
            rest.append(b)
            continue
        log.warning(
            "%s %s %s: abgeleitete Zuzahlung %s widerspricht der gelesenen "
            "Zeile, Bündel zählt nicht",
            b.anbieter,
            b.sku_id,
            b.tarif_name,
            abg,
        )
    return rest


def hat_einmalzahlung_nach_24(b: object) -> bool:
    """Ein 1&1-Vertrag über mehr als 24 Monate mit gemessener Einmalzahlung."""
    return (
        isinstance(b, Buendel)
        and b.anbieter == EINMALZAHLUNG_ANBIETER
        and b.buendel_monatlich is not None
        and (b.laufzeit_monate or 0) > TCO_HORIZONT
        and b.geraet_zuzahlung is not None
        and b.zustand in ("", "neu")
    )


def hat_einmalzahlung_nach_24_satz(satz: Mapping) -> bool:
    """Dieselbe Bedingung wie `hat_einmalzahlung_nach_24`, für einen rohen
    Bündelsatz (``geraete_tco.json``) statt eines `Buendel`-Objekts - EINE Regel
    für die Tafel und die Zeitreihen-Auswahl (`report.geraete_zeitreihe_auswahl`)."""
    return (
        (satz.get("anbieter") or "") == EINMALZAHLUNG_ANBIETER
        and satz.get("buendel_monatlich") is not None
        and (satz.get("laufzeit_monate") or 0) > TCO_HORIZONT
        and satz.get("geraet_zuzahlung") is not None
        and (satz.get("zustand") or "") in ("", "neu")
    )


def _gueltiger_wert(werte: list[float]) -> float | None:
    """Der eindeutig häufigste Wert; None bei Gleichstand."""
    haeufig = Counter(round(w, 2) for w in werte).most_common(2)
    if len(haeufig) > 1 and haeufig[0][1] == haeufig[1][1]:
        return None
    return haeufig[0][0]


def abweichende_einmalzahlungen(werte: list[float]) -> set[float]:
    """Die auf zwei Stellen gerundeten Werte, die vom Gerätewert abweichen.

    Leer, wenn nichts zu prüfen ist (ein Wert, oder alle gleich). Bei Gleichstand
    gibt es keinen Gerätewert, dann weichen alle ab. EINE Regel für die Tafel
    (`mit_einheitlicher_einmalzahlung`) und die Zeitreihe
    (`report.geraete_zeitreihe_auswahl`)."""
    gerundet = [round(w, 2) for w in werte]
    if len(gerundet) < 2 or len(set(gerundet)) < 2:
        return set()
    gueltig = _gueltiger_wert(gerundet)
    return {w for w in gerundet if w != gueltig}


def mit_einheitlicher_einmalzahlung(
    buendel: Iterable, geraet_je_sku: Mapping[str, tuple]
) -> list:
    """Die Bündel, bei denen eine vom Gerät abweichende Einmalzahlung zur Lücke wird.

    ``geraet_je_sku`` ordnet jede SKU (Gerät, Speicher) zu; eine SKU ohne Zuordnung
    wird nicht geprüft. Der abweichende Tarif behält alle Felder außer der
    Einmalzahlung (None) und der Herleitung (`HERLEITUNG_EINMALZAHLUNG`): die Rechnung
    nennt dann die Lücke, die Notbremse den Grund. Jeder Eingriff steht im Protokoll."""
    liste = list(buendel)
    gruppen: dict[tuple, list[float]] = {}
    for b in liste:
        if hat_einmalzahlung_nach_24(b) and (g := geraet_je_sku.get(b.sku_id)):
            gruppen.setdefault((b.anbieter, *g), []).append(b.geraet_zuzahlung)
    abweichend = {
        schluessel: w
        for schluessel, werte in gruppen.items()
        if (w := abweichende_einmalzahlungen(werte))
    }
    if not abweichend:
        return liste
    ergebnis = []
    for b in liste:
        g = geraet_je_sku.get(b.sku_id) if hat_einmalzahlung_nach_24(b) else None
        schluessel = (b.anbieter, *g) if g else None
        if (
            schluessel not in abweichend
            or round(b.geraet_zuzahlung, 2) not in abweichend[schluessel]
        ):
            ergebnis.append(b)
            continue
        log.warning(
            "%s %s %s: Einmalzahlung %s weicht vom Gerätewert ab, Preis wird Lücke",
            b.anbieter,
            b.sku_id,
            b.tarif_name,
            b.geraet_zuzahlung,
        )
        ergebnis.append(
            replace(b, geraet_zuzahlung=None, herleitung=HERLEITUNG_EINMALZAHLUNG)
        )
    return ergebnis


def bereinigt(buendel: Iterable, geraet_je_sku: Mapping[str, tuple]) -> list:
    """Die Bündel, wie jeder Leser sie sehen darf: erst die Einmalzahlung je Gerät, dann
    die Widerlegung. In dieser Reihenfolge, sonst verdrängt ein abweichender Klick-Wert
    die übrigen Tarife (Manager, 05.11.2026)."""
    return ohne_widerlegte(mit_einheitlicher_einmalzahlung(buendel, geraet_je_sku))
