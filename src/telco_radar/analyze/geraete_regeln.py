"""Prüfstelle der Geräte-Bündel: die 16 Regeln aus Abschnitt 9 des Datenkonzepts.

``pruefe_bestand`` gibt jedem Bündelsatz ein ``Pruefergebnis`` (Status und Befunde,
``geraete_pruefstatus``). Regel 5 (Preis steigt mit dem Speicher) prüft den ganzen
Bestand; Regel 12 (gleicher Wert bei allen Bündeln eines Anbieters, auch eine
Ratenlaufzeit, die bei allen Geräten fehlt) ergibt eine Erfassungslücke je Anbieter
(``erfassungsluecken``), keinen Status. Regel 15 gilt im Vergleich (Sieger, Δ); je
Bündel wird nur geprüft, ob der Zeitraum H bestimmbar ist. Regel 4 prüft das Volumen im
Tarifnamen gegen den Tarifbestand; ob ein Tarif in ein Band mit mehr Volumen fällt,
entscheidet die Bandzuordnung der Ansicht.

Felder, die erst Klick-Crawler und Beleg-Archiv liefern: ``geraet_summe`` (Gerätesumme,
wie die Seite sie nennt), ``echo`` (``klickecho.Echo`` als Zuordnung mit ``werte`` und
``befunde``) und ``beleg_variante`` (``laufzeit``, ``tarif``, ``speicher`` des
Beleglinks). Fehlen sie, ist die Regel nicht prüfbar. Dieses Modul liest keine Datei und
ruft kein Netz; was es aus anderen Stufen braucht, steht im ``Kontext``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..geraete_model import normalisiere
from ..tarif_model import vertrag_basis
from ..tco_model import (
    POSTEN_BUENDEL,
    POSTEN_TARIF,
    Buendel,
    kosten_ueber,
    sim_only_id,
    tco_24,
)
from ..tco_model import zeitraum as zeitraum_h
from .geraete_pruefstatus import (
    AUSREISSER_VORTAG,
    CENT,
    ERLAUBTE_RATENLAUFZEITEN,
    FELD_BELEG_VARIANTE,
    FELD_ECHO,
    FELD_GERAETESUMME,
    LUECKE,
    MIN_BUENDEL_GLEICHWERT,
    NICHT_PRUEFBAR,
    RECHEN_TOLERANZ_EUR,
    UVP_OBEN,
    UVP_UNTEN,
    VERLETZT,
    Befund,
    Kontext,
    Pruefergebnis,
    abgelaufene_aktionen,
    aufzaehlung,
    buendel_aus_satz,
    datum,
    eur,
    gb,
    geraetepreis,
    pflichtfelder,
)


def pruefe_bestand(saetze: Iterable[Mapping], k: Kontext) -> dict[str, Pruefergebnis]:
    """Prüft jeden Bündelsatz (Schlüssel ``id``) gegen alle Regeln und den Bestand.

    Ein Satz, aus dem kein ``Buendel`` wird, ist Quarantäne nach Regel 14.
    """
    ergebnisse: dict[str, Pruefergebnis] = {}
    lesbar: list[tuple[str, Buendel]] = []
    for satz in saetze:
        bid = str(satz.get("id") or "")
        try:
            b = buendel_aus_satz(satz)
        except (TypeError, ValueError) as exc:
            ergebnisse[bid] = Pruefergebnis([_verletzt(14, f"Satz unlesbar: {exc}")])
            continue
        befunde = [x for regel in _JE_BUENDEL if (x := regel(satz, b, k)) is not None]
        ergebnisse[bid] = Pruefergebnis(befunde)
        lesbar.append((bid, b))
    for bid, befund in _speicherstufen(lesbar, k).items():
        ergebnisse[bid].befunde.append(befund)
    return ergebnisse


def erfassungsluecken(saetze: Iterable[Mapping]) -> dict[str, list[str]]:
    """Regel 12 je Anbieter: eine Ratenlaufzeit, die bei allen Geräten fehlt, und ein
    Pflichtwert, der bei allen Bündeln gleich ist oder überall fehlt."""
    je_anbieter: dict[str, list[Buendel]] = {}
    for satz in saetze:
        try:
            b = buendel_aus_satz(satz)
        except (TypeError, ValueError):
            continue
        je_anbieter.setdefault(b.anbieter, []).append(b)
    befunde: dict[str, list[str]] = {}
    for anbieter, liste in sorted(je_anbieter.items()):
        da = {b.laufzeit_monate for b in liste}
        fehlend = [str(n) for n in ERLAUBTE_RATENLAUFZEITEN if n not in da]
        saetze_ = [f"{aufzaehlung(fehlend)} Monate nicht erfasst"] if fehlend else []
        werte: dict[tuple[str, str], list] = {}
        for b in liste:
            for feld, name in pflichtfelder(b):
                if feld != "laufzeit_monate":
                    werte.setdefault((feld, name), []).append(getattr(b, feld))
        for (feld, name), gesehen in werte.items():
            if len(gesehen) >= MIN_BUENDEL_GLEICHWERT and len(set(gesehen)) == 1:
                saetze_.append(_gleichwert(feld, name, gesehen[0], len(gesehen)))
        if saetze_:
            befunde[anbieter] = saetze_
    return befunde


def sim_only_tabelle(referenzen: Iterable[Mapping]) -> dict[str, float]:
    """SIM-only-Monatspreise der gespeicherten Referenzen, je Name und je Tarif-ID.

    Eine Tarif-ID mit zwei Referenzen ist nicht eindeutig und fällt weg, wie auf der
    Tafel (``geraete_tco_view``)."""
    tabelle: dict[str, float] = {}
    doppelt: set[str] = set()
    for r in referenzen:
        preis, tid = r.get("tarif_sim_only_monatlich"), str(r.get("tarif_id") or "")
        if preis is None:
            continue
        tabelle[sim_only_id(r.get("anbieter", ""), r.get("tarif_name", ""))] = preis
        if tid.strip():
            schluessel = _tarif_schluessel(r.get("anbieter", ""), tid.strip())
            if schluessel in tabelle:
                doppelt.add(schluessel)
            tabelle[schluessel] = preis
    return {s: p for s, p in tabelle.items() if s not in doppelt}


def sim_only_preis(b: Buendel, tabelle: Mapping[str, float]) -> float | None:
    """Der SIM-only-Preis desselben Tarifs: über Namen, Tarif-ID oder Vertrag."""
    schluessel = [sim_only_id(b.anbieter, b.tarif_name)]
    if tid := (b.tarif_id or "").strip():
        schluessel.append(_tarif_schluessel(b.anbieter, tid))
        schluessel.append(_tarif_schluessel(b.anbieter, vertrag_basis(tid)))
    return next((tabelle[s] for s in schluessel if s in tabelle), None)


def _tarif_schluessel(anbieter: str, tarif_id: str) -> str:
    return f"{normalisiere(anbieter)}|{tarif_id}"


def _verletzt(regel: int, satz: str) -> Befund:
    return Befund(regel, VERLETZT, satz)


def _nicht(regel: int, satz: str) -> Befund:
    return Befund(regel, NICHT_PRUEFBAR, satz)


def _r1_rechenprobe(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    seite, raten = satz.get(FELD_GERAETESUMME), b.geraeteraten
    if seite is None:
        return _nicht(1, "Gerätesumme der Seite fehlt")
    if raten is None:
        return _nicht(1, "Anzahlung, Rate oder Ratenzahl fehlt")
    if abs(raten.gesamt - float(seite)) <= RECHEN_TOLERANZ_EUR:
        return None
    return _verletzt(
        1,
        f"Anzahlung + {raten.laufzeit_monate} Raten = {eur(raten.gesamt)}, "
        f"die Seite nennt {eur(float(seite))}",
    )


def _r2_uvp(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    uvp, raten = k.uvp.get(b.sku_id), b.geraeteraten
    if not uvp:
        return _nicht(2, "UVP fehlt")
    if raten is None:
        return _nicht(2, "Gerätesumme fehlt")
    anteil = raten.gesamt / uvp
    if UVP_UNTEN <= anteil <= UVP_OBEN:
        return None
    return _verletzt(2, f"Gerätesumme {eur(raten.gesamt)} ist {anteil:.0%} der UVP")


def _r3_sim_only(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    if b.tarif_monatlich is None:
        return _nicht(3, "kein eigener Tarifpreis")
    sim = sim_only_preis(b, k.sim_only)
    if sim is None:
        return _nicht(3, "SIM-only-Preis desselben Tarifs fehlt")
    if b.tarif_monatlich >= sim - CENT:
        return None
    return _verletzt(
        3, f"Tarif mit Gerät {eur(b.tarif_monatlich)} unter SIM-only {eur(sim)}"
    )


def _r4_volumen(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    gemessen = k.volumen.get(b.tarif_id)
    im_namen = k.volumen_im_namen(b.tarif_name) if k.volumen_im_namen else None
    if gemessen is None or im_namen is None:
        return _nicht(4, "Volumen im Tarifnamen oder im Tarifbestand fehlt")
    if im_namen == gemessen:
        return None
    return _verletzt(4, f"Tarifname nennt {gb(im_namen)}, gemessen {gb(gemessen)}")


def _r6_laufzeit(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    n = b.laufzeit_monate
    if n is None:
        return Befund(6, LUECKE, "Ratenlaufzeit fehlt")
    if n not in ERLAUBTE_RATENLAUFZEITEN:
        erlaubt = aufzaehlung([str(x) for x in ERLAUBTE_RATENLAUFZEITEN])
        return _verletzt(6, f"{n} Raten, erlaubt sind {erlaubt}")
    echo = _echo(satz)
    bestaetigt = (echo.get("werte") or {}).get("ratenzahl") if echo else None
    if bestaetigt is None:
        return _nicht(6, "Ratenlaufzeit ohne Echo der Seite")
    return None if bestaetigt == n else _verletzt(6, f"{n} Raten, Seite: {bestaetigt}")


def _r7_bindung(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    if b.tarif_bindung_monate is None:
        return Befund(7, LUECKE, "Tarifbindung fehlt")
    return None


def _r8_phasen(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    kosten = kosten_ueber(b)
    if kosten.monate is None:
        return _nicht(8, "Zeitraum H nicht bestimmbar")
    offen = [
        posten
        for posten in kosten.luecken
        if posten.startswith((POSTEN_TARIF, f"{POSTEN_BUENDEL} Monat"))
    ]
    if not offen:
        return None
    return Befund(8, LUECKE, f"über {kosten.monate} Monate fehlt: {', '.join(offen)}")


def _r9_echo(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    echo = _echo(satz)
    if echo is None:
        return _nicht(9, "keine mitgeschnittene Antwort")
    felder = [str(x.get("feld", "?")) for x in echo.get("befunde") or []]
    if not felder:
        return None
    return _verletzt(9, f"Text und Antwort widersprechen sich: {', '.join(felder)}")


def _r10_aktion(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    if abgelaufen := abgelaufene_aktionen(b.aktionen, k.heute):
        bis = datum(abgelaufen[0].gueltig_bis)
        return _verletzt(10, f"eingerechnete Aktion bis {bis} abgelaufen")
    return None


def _r11_vortag(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    alt = k.vortag.get(str(satz.get("id") or ""))
    if alt is None:
        return _nicht(11, "kein Vortageswert")
    try:
        vorher = tco_24(buendel_aus_satz({**satz, **alt}))
    except (TypeError, ValueError):
        return _nicht(11, "Vortageswert unlesbar")
    jetzt = tco_24(b)
    neu, alt_ = jetzt.gesamt, vorher.gesamt
    if not (jetzt.belastbar and vorher.belastbar) or neu is None or not alt_:
        return _nicht(11, "Gesamtpreis heute oder am Vortag unvollständig")
    sprung = abs(neu - alt_) / alt_
    if sprung <= AUSREISSER_VORTAG:
        return None
    return _verletzt(
        11,
        f"{eur(neu)} statt {eur(alt_)} am {datum(str(alt.get('datum') or ''))} "
        f"({sprung:.0%}), Quarantäne bis zum zweiten Abruf",
    )


def _r13_beleg(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    beleg = satz.get(FELD_BELEG_VARIANTE)
    if not isinstance(beleg, Mapping):
        return _nicht(13, "kein Beleg der Variante")
    speicher = k.geraet_von(b.sku_id)[1] if k.geraet_von else None
    tarif, beleg_speicher = str(beleg.get("tarif") or ""), beleg.get("speicher")
    bekannt = None not in (speicher, beleg_speicher)
    abweichend = [
        name
        for name, anders in (
            ("Ratenlaufzeit", beleg.get("laufzeit") not in (None, b.laufzeit_monate)),
            ("Tarif", normalisiere(tarif) not in ("", normalisiere(b.tarif_name))),
            ("Speicher", bekannt and beleg_speicher != speicher),
        )
        if anders
    ]
    if not abweichend:
        return None
    return _verletzt(13, f"Beleglink zeigt andere {aufzaehlung(abweichend)}")


def _r14_pflicht(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    fehlend = [name for feld, name in pflichtfelder(b) if getattr(b, feld) is None]
    if not fehlend:
        return None
    return Befund(14, LUECKE, f"es fehlt {aufzaehlung(fehlend)}")


def _r15_zeitraum(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    if zeitraum_h(b) is None:
        return Befund(15, LUECKE, "Zeitraum H nicht bestimmbar")
    return None


def _r16_frische(satz: Mapping, b: Buendel, k: Kontext) -> Befund | None:
    if k.frisch is None:
        return _nicht(16, "Frischegrenze fehlt")
    if k.frisch(b.abgerufen_am, k.heute):
        return None
    return _verletzt(16, f"abgerufen am {datum(b.abgerufen_am) or 'unbekannt'}")


_JE_BUENDEL = (
    _r1_rechenprobe,
    _r2_uvp,
    _r3_sim_only,
    _r4_volumen,
    _r6_laufzeit,
    _r7_bindung,
    _r8_phasen,
    _r9_echo,
    _r10_aktion,
    _r11_vortag,
    _r13_beleg,
    _r14_pflicht,
    _r15_zeitraum,
    _r16_frische,
)


def _speicherstufen(lesbar: list[tuple[str, Buendel]], k: Kontext) -> dict[str, Befund]:
    """Regel 5 über den Bestand: beim selben Anbieter, Tarif, Laufzeit und Gerät kostet
    mehr Speicher nie weniger. Beide Bündel eines verletzten Paars sind Quarantäne."""
    befunde: dict[str, Befund] = {}
    stufen: dict[tuple, dict[int, list[tuple[str, float]]]] = {}
    for bid, b in lesbar:
        geraet, speicher = k.geraet_von(b.sku_id) if k.geraet_von else ("", None)
        preis = geraetepreis(b)
        if not geraet or speicher is None or preis is None:
            befunde[bid] = _nicht(5, "Gerät, Speicher oder Gerätepreis fehlt")
            continue
        tarif = b.tarif_id or normalisiere(b.tarif_name)
        reihe = (normalisiere(b.anbieter), tarif, b.laufzeit_monate, geraet)
        stufen.setdefault(reihe, {}).setdefault(speicher, []).append((bid, preis))
    for je_speicher in stufen.values():
        groessen = sorted(je_speicher)
        for i, klein in enumerate(groessen):
            for gross in groessen[i + 1 :]:
                for kid, kp in je_speicher[klein]:
                    for gid, gp in je_speicher[gross]:
                        if gp < kp - CENT:
                            text = f"{gross} GB für {eur(gp)}, {klein} GB für {eur(kp)}"
                            befunde.setdefault(kid, _verletzt(5, text))
                            befunde.setdefault(gid, _verletzt(5, text))
    return befunde


def _echo(satz: Mapping) -> Mapping | None:
    echo = satz.get(FELD_ECHO)
    return echo if isinstance(echo, Mapping) else None


def _gleichwert(feld: str, name: str, wert: float | None, zahl: int) -> str:
    if wert is None:
        return f"{name} fehlt bei allen {zahl} Bündeln"
    text = f"{wert} Monate" if feld == "tarif_bindung_monate" else eur(wert)
    return f"{name} bei allen {zahl} Bündeln {text}"
