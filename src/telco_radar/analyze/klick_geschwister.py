"""Name eines Klick-Satzes ohne Gegenstück aus einem Adaptersatz anderer Laufzeit.

1&1 nennt den Tarif im Klick als Kennung (``tariff-anf-s-mvl``), die der Tarifbestand
nicht auflöst; Namen („1&1 All-Net-Flat S“) und Kennung als Slug liest der Adapter von
derselben Produktseite, aber nur für 24+12 (36 Raten). Die Kachel 24, seit dem
08.10.2026 aus der Kachel der Folgeseite bestätigt (``klickkachel``), hätte darum kein
Gegenstück und bliebe ein offener Tarif.

``mit_namen`` gibt einem Klick-Satz ohne Gegenstück SKU, Tarifnamen und Slug
(``felder``) jedes Adaptersatzes mit gleichem Anbieter, Gerät, Speicher und Tarif bei
anderer Laufzeit, je verschiedenem Namen ein Satz; nur wenn der Klick den Tarif so nennt
wie der Slug des Adapters, nicht wie dessen Namen (sonst löst der Klick-Satz selbst
auf, und seine SKU bleibt). Werte übernimmt er nie. Ohne solchen Adaptersatz bleibt der
Satz, wie er ist.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..collect.geraete.klickrohsatz import tarifschluessel

Schluessel = tuple[str, str, int | None, str, int | None]


def geschwister(index: Mapping[Schluessel, list[int]]) -> dict[tuple, set[int]]:
    """Die Stellen der Adaptersätze je Schlüssel ohne Laufzeit."""
    ohne: dict[tuple, set[int]] = {}
    for schluessel, stellen in index.items():
        ohne.setdefault(schluessel[:-1], set()).update(stellen)
    return ohne


def mit_namen(
    satz: dict,
    schluessel: Schluessel,
    adapter: Sequence[dict],
    stellen: Mapping[tuple, set[int]],
    felder: tuple[str, ...],
) -> list[dict]:
    """Der Klick-Satz mit dem Namen jedes passenden Adaptersatzes (siehe Modulkopf)."""
    tarif = schluessel[3]
    passend = [
        adapter[s]
        for s in sorted(stellen.get(schluessel[:-1], ()))
        if tarifschluessel(adapter[s].get("tarif_name")) != tarif
    ]
    namen = dict.fromkeys(tuple(a.get(f) for f in felder) for a in passend)
    if not namen:
        return [satz]
    return [{**satz, **dict(zip(felder, name, strict=True))} for name in namen]
