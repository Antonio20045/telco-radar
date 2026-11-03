"""Die Modellzeile der Tabelle „Alle Geräte“: Abstand in Worten, Vergleich je Tarif M.

Zwei Felder, die `geraete_view._tco_spalte` nicht selbst rechnet:
`tco_delta_wort` („congstar 193,79 € günstiger · 9,9 %“ statt „−193,79 € · −9,9 %“)
und
`tco_vodafone_teurer`, die Zeile des Blocks „Über 10 % teurer“ auf der Basis
des Diagramms „Preispositionierung“ (Tarif M, 24 Monate, geprüft)."""

from __future__ import annotations

from . import geraete_teurer
from .geraete_preisposition_preise import preise_je_anbieter
from .geraete_tco_grafik import euro

NAEHERUNG = "≈"


def delta_wort(
    betrag: float | None,
    prozent: float | None,
    ungefaehr: bool = False,
    anbieter: str | None = None,
) -> str | None:
    """Der Abstand zur Vodafone-Referenz mit Wort statt Vorzeichen.

    Das Subjekt ist immer der Wettbewerber, dessen Angebot den Abstand trägt
    („o2 181,35 € teurer“ heißt: o2 liegt über Vodafone); ohne Namen bleibt
    der Satz ohne Subjekt.

    Negativ heißt das Angebot ist günstiger, positiv teurer. Eine Näherung
    (`ungefaehr`) bleibt „rund“ und trägt keinen Prozentanteil; fehlt der
    Betrag, gibt es kein Wort (`None`, eine Lücke)."""
    if betrag is None:
        return None
    subjekt = f"{anbieter} " if anbieter else ""
    if not betrag:
        return f"{subjekt}gleich teuer"
    text = f"{euro(abs(betrag))} {'günstiger' if betrag < 0 else 'teurer'}"
    if ungefaehr:
        return f"{subjekt}rund {text}"
    if prozent is not None:
        text += f" · {abs(prozent):,.1f}".replace(".", ",") + " %"
    return subjekt + text


def ergaenze(felder: dict, modell_tco: dict | None) -> dict:
    """Die TCO-Felder einer Modellzeile um Wort und Tarif-M-Vergleich ergänzt.

    Der Vergleich gilt auch, wenn die Zeile selbst kein bestes Bündel nennt;
    ob das Δ eine Näherung ist, sagt dessen Kurzform (`NAEHERUNG`)."""
    kurz = felder.get("tco_delta_kurz")
    wort = (
        delta_wort(
            felder.get("tco_delta"),
            felder.get("tco_delta_prozent"),
            kurz.startswith(NAEHERUNG),
            felder.get("tco_delta_traeger"),
        )
        if kurz
        else None
    )
    return {
        **felder,
        "tco_delta_wort": wort,
        "tco_vodafone_teurer": geraete_teurer.vergleich_m(
            preise_je_anbieter(modell_tco)
        ),
    }
