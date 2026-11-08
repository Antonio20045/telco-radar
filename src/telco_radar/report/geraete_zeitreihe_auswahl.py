"""Der jüngste Zeitreihen-Punkt einer 1&1-Linie gegen die AKTUELLE Widerspruchsregel.

`_messungen` (`geraete_zeitreihe.py`) prüft je Tag, ob zwei Messungen desselben
Anbieters/Bündels sich widersprechen - das reicht für den jüngsten Punkt einer Linie
nicht: ein Gerät, das heute mit zwei Tarifen gemessen wird, kann an EINEM der beiden
Tage eine Einmalzahlung tragen, die erst im Licht des ANDEREN Tarifs widersprüchlich
wird (Prüfung PR #45, Befund M1: Galaxy S26 256 GB, Tarif S, zeigte in der Zeitreihe
weiter 1.051,66 € mit 220 € Ablöse, obwohl die Tafel vom selben Tag diesen Tarif schon
als "1&1-Wert widersprüchlich, neu messen" führt, weil M/L inzwischen 280 € tragen).

Regel (Manager, 05.11.2026): fällt der JÜNGSTE Punkt einer 1&1-Linie auf eine
Einmalzahlung, die beim HEUTIGEN Gerätestand (`geraete_tco.json`, dieselbe
Gruppierung wie die Tafel, `analyze.geraete_widerspruch.abweichende_einmalzahlungen`)
vom Mehrheitswert abweicht, fällt NUR dieser jüngste Punkt weg. Ältere Punkte bleiben
unverändert sichtbar - im Zeitraum 12.09. bis 03.11.2026 war die Einmalzahlung bei
allen Tarifen noch einheitlich, also kein Widerspruch (Entscheidung 2).
"""

from __future__ import annotations

from ..analyze.geraete_widerspruch import (
    abweichende_einmalzahlungen,
    hat_einmalzahlung_nach_24_satz,
)

EINMALZAHLUNG_ANBIETER = "1&1"


def heute_abweichend(
    heutiger_stand: dict[str, dict], sku_modell: dict[str, str]
) -> dict[str, set[float]]:
    """{Modell-ID: abweichende Einmalzahlungen} nach dem HEUTIGEN Gerätestand.

    Ein Modell ist Gerät + Speicher (`geraete_tco_karten.modell_schluessel`) -
    dieselbe Gruppierung wie `geraete_widerspruch.mit_einheitlicher_einmalzahlung`,
    hier direkt auf den rohen Sätzen aus `geraete_tco.json`."""
    gruppen: dict[str, list[float]] = {}
    for satz in heutiger_stand.values():
        if not hat_einmalzahlung_nach_24_satz(satz):
            continue
        modell = sku_modell.get(satz.get("sku_id") or "")
        if modell is None:
            continue
        gruppen.setdefault(modell, []).append(satz["geraet_zuzahlung"])
    return {
        modell: w
        for modell, werte in gruppen.items()
        if (w := abweichende_einmalzahlungen(werte))
    }


def ohne_widersprochenen_juengsten(
    messungen: dict[tuple, dict], heutiger_stand: dict[str, dict], sku_modell: dict
) -> None:
    """Entfernt NUR den jüngsten Punkt einer 1&1-Linie, deren Einmalzahlung beim
    heutigen Gerätestand widersprüchlich ist - in place, ältere Punkte bleiben.

    `messungen` ist `{(modell, band, laufzeit): {anbieter: {datum: MESSUNG}}}`;
    eine MESSUNG trägt die Historienzeile unter ``"satz"`` (`geraete_zeitreihe.
    _messungen`). Ohne einen Widerspruch für dieses Modell bleibt die Linie
    unberührt - die meisten Modelle haben nie einen."""
    abweichend = heute_abweichend(heutiger_stand, sku_modell)
    for (modell, _band, _laufzeit), je_anbieter in messungen.items():
        werte = abweichend.get(modell)
        if not werte:
            continue
        slot = je_anbieter.get(EINMALZAHLUNG_ANBIETER)
        if not slot:
            continue
        juengstes_datum = max(slot)
        zuzahlung = slot[juengstes_datum]["satz"].get("geraet_zuzahlung")
        if zuzahlung is not None and round(zuzahlung, 2) in werte:
            del slot[juengstes_datum]
