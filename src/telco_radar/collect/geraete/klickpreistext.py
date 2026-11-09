"""Der Preistext des vierten Schritts der Bildfolge: nur Beträge, die im Bild stehen.

``preistext`` nennt die Zahl, die das Bild hervorhebt (Summe aus Gerät und Tarif, bei o2
„einmalig gesamt“ mit Versand) und die Gerätewerte klar unterschieden; ein Betrag steht
nur im Text, wenn ihn der sichtbare Text des Bildes enthält.
"""

from __future__ import annotations

import re

from .klicktext import (
    Buendelwerte,
    Preiswerte,
    betraege_im_text,
    einmalig_gesamt_im_text,
    versand_im_text,
)

TEXT_OHNE_BETRAG = "Preisbereich der Anbieterseite nach der Wahl"


def euro(betrag: float | None) -> str:
    """Ein Betrag deutsch mit Komma; ``nicht gelesen`` für eine Lücke."""
    if betrag is None:
        return "nicht gelesen"
    ganz, rest = f"{betrag:.2f}".split(".")
    gruppen = f"{int(ganz):,}".replace(",", ".")
    return f"{gruppen},{rest} €"


def preistext(
    werte: Preiswerte, buendel: Buendelwerte | None, bildtext: str | None
) -> str:
    """Die Beträge, die im Bild des Preisbereichs stehen, mit ihrer Bedeutung.

    Gelesen sind Zuzahlung und Monatsrate des Geräts, bei Bündeln Einmalzahlung und
    Monatsbetrag. Zeigt die Seite stattdessen die Summe aus Gerät und Tarif (Zuzahlung
    plus Anschluss, Rate plus erster Tarifpreis), nennt der Text sie. Ein Betrag steht
    nur im Text, wenn ``bildtext`` (der sichtbare Text des Bildes) ihn enthält; ist
    keiner sicher, nennt der Text keine Zahl. Eine selbst gerechnete Einmalsumme
    (Zuzahlung plus Anschluss) nennt der Text nicht, wenn das Bild eine größere Summe
    zeigt, die der Code nicht am Etikett „einmalig gesamt“ erkennt (siehe
    ``_einmalig_sicher``).
    """
    text = bildtext or ""
    gezeigt = betraege_im_text(text)
    einmalig = _einmalig(werte, buendel)
    if not _einmalig_sicher(werte, buendel, text, gezeigt):
        einmalig = None
    zusammen = _gezeigt(
        gezeigt, ("einmalig", einmalig), ("monatlich", _monatlich(werte, buendel))
    )
    geraet = _gezeigt(
        gezeigt,
        ("Zuzahlung", werte.anzahlung),
        ("Monatsrate", werte.rate),
    )
    gesamt = _einmalig_gesamt(werte, buendel, text, gezeigt)
    if gesamt:
        zusammen = [gesamt, *(z for z in zusammen if not z.startswith("einmalig"))]
        if "davon Gerät" in gesamt:
            geraet = [g for g in geraet if not g.startswith("Zuzahlung")]
    if geraet and geraet[-1].startswith("Monatsrate") and werte.ratenzahl is not None:
        raten = rf"(?:[x×]\s*{werte.ratenzahl}\b|\b{werte.ratenzahl}\s*Raten\b)"
        if re.search(raten, text):
            geraet[-1] += f" × {werte.ratenzahl}"
    teile = []
    if zusammen:
        teile.append(" · ".join(zusammen) + " (Gerät und Tarif zusammen)")
    teile.extend(geraet)
    if not teile:
        return TEXT_OHNE_BETRAG
    return "Im Bild: " + " · ".join(teile)


def _einmalig_gesamt(
    werte: Preiswerte,
    buendel: Buendelwerte | None,
    bildtext: str,
    gezeigt: frozenset[int],
) -> str | None:
    """Die Zahl, die das Bild als „einmalig gesamt“ nennt, wenn sie von der Summe aus
    Zuzahlung und Anschluss abweicht (o2: mit Versand), samt Versand und Gerät, nur mit
    Beträgen aus dem Bild; sonst ``None``."""
    gesamt = einmalig_gesamt_im_text(bildtext)
    if gesamt is None or round(gesamt * 100) == _cent(_einmalig(werte, buendel)):
        return None
    text = f"einmalig gesamt {euro(gesamt)}"
    versand = versand_im_text(bildtext)
    if versand is not None:
        summe = _plus(werte.anzahlung, werte.anschluss, versand)
        if summe is not None and round(summe * 100) == round(gesamt * 100):
            text += f" inkl. {euro(versand)} Versand"
    geraet = _gezeigt(gezeigt, ("davon Gerät", werte.anzahlung))
    return "; ".join([text, *geraet])


def _einmalig_sicher(
    werte: Preiswerte,
    buendel: Buendelwerte | None,
    bildtext: str,
    gezeigt: frozenset[int],
) -> bool:
    """Falsch, wenn die selbst gerechnete Einmalsumme (Zuzahlung plus Anschluss) die
    Zahl sein könnte, die das Bild gar nicht hervorhebt: Es nennt einen Betrag, der
    genau diese Summe plus einen weiteren genannten Betrag ist (Versand, Gebühr), und
    der Code erkennt ihn nicht am Etikett „einmalig gesamt“. Das Etikett ist nicht die
    einzige Stütze: Heißt es im Bild anders („Summe“), erkennt das die Summenprobe
    trotzdem, und der Text nennt lieber keinen Einmalbetrag als einen unpassenden.
    Ein gelesener Bündelwert oder ein erkanntes Etikett gilt immer. Bei einer Basis von
    0 wäre jeder Betrag „Summe plus Rest“; dann zählt nur ein genannter Versand."""
    if buendel is not None and buendel.einmalzahlung is not None:
        return True
    if einmalig_gesamt_im_text(bildtext) is not None:
        return True
    basis = _cent(_plus(werte.anzahlung, werte.anschluss))
    if basis is None:
        return True
    if basis == 0:
        versand = versand_im_text(bildtext)
        return versand is None or versand <= 0
    return not any(
        rest > 0 and basis + rest in gezeigt for rest in gezeigt if rest != basis
    )


def _cent(betrag: float | None) -> int | None:
    return None if betrag is None else round(betrag * 100)


def _gezeigt(gezeigt: frozenset[int], *posten: tuple[str, float | None]) -> list[str]:
    """``Name Betrag`` je Posten, dessen Betrag im Bild steht."""
    return [
        f"{name} {euro(betrag)}"
        for name, betrag in posten
        if betrag is not None and round(betrag * 100) in gezeigt
    ]


def _plus(*summanden: float | None) -> float | None:
    """Die Summe; ``None``, sobald ein Summand nicht gelesen ist."""
    if any(s is None for s in summanden):
        return None
    return sum(s for s in summanden if s is not None)


def _einmalig(werte: Preiswerte, buendel: Buendelwerte | None) -> float | None:
    """Einmalbetrag von Gerät und Tarif: Bündelwert, sonst Zuzahlung plus Anschluss."""
    if buendel is not None and buendel.einmalzahlung is not None:
        return buendel.einmalzahlung
    return _plus(werte.anzahlung, werte.anschluss)


def _monatlich(werte: Preiswerte, buendel: Buendelwerte | None) -> float | None:
    """Monatsbetrag von Gerät und Tarif: Bündelwert, sonst Rate plus Tarifpreis."""
    if buendel is not None and buendel.buendelbetrag is not None:
        return buendel.buendelbetrag
    erste = [p.betrag for p in werte.tarifphasen or () if p.von_monat == 1]
    return _plus(werte.rate, erste[0] if erste else None)
