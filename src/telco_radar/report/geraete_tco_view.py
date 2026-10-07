"""Reiter "Was kostet es": die TCO-24 auf der Seite (Phase 8, Skelett).

Warum dieser Reiter eine eigene Tafel ist
-----------------------------------------
Die Alarmtabelle beantwortet "wo liegen wir im Preis zurueck". Diese Tafel
beantwortet "was kostet das ueber die Laufzeit". Zwei Fragen, zwei Tafeln -
dieselbe Begruendung wie fuer die vier bestehenden Reiter, und ausdruecklich
KEINE weitere Spalte in der Alarmtabelle (Strategie § 8, Phase 8, Punkt 1).
Eine TCO neben einem Barpreis in derselben Zeile waere genau der Befund, mit
dem dieses Vorhaben angefangen hat: zwei Groessen unter einer Ueberschrift.

Fehlt ein Posten, zeigt die Tafel die benannte Luecke statt einer Zahl:
"Wenn kein Anschlusspreis bekannt ist, heisst das nicht kostenlos"
(`report/effektivpreis.py`, `tco_model` § 6.4).

Die vier Regeln, die dieses Modul tragen
----------------------------------------
1. **Gerechnet wird ausschliesslich in `tco_model`.** Dieses Modul ruft
   `kosten_ueber()` und `geraeteanteil()` auf und formt das Ergebnis; es addiert
   selbst keinen Euro. Zwei Rechnungen fuer dieselbe Zahl sind zwei Zahlen
   (CLAUDE.md § 6) - und die eine davon stuende in einer Vorlage, wo sie
   niemand testet.
2. **Keine Zahl ohne `belastbar`.** `Tco.gesamt` ist auch dann eine Zahl,
   wenn der Tarifgrundpreis fehlt - dann ist es aber der Geraetebetrag und
   keine TCO. Diese Tafel zeigt `gesamt` und `monatlich` NUR bei
   `Tco.belastbar`; sonst steht dort die Luecke. Der Unterschied ist der
   ganze Sinn des Reiters.
3. **Das Euro-Delta braucht auf BEIDEN Seiten eine belastbare Zahl.**
   Ein Banner "129 EUR guenstiger als Vodafone", dessen eine Haelfte eine
   Luecke hat, ist eine Falschaussage mit Vorzeichen.
4. **Die Bereitschaftstabelle ist eine Auskunft ueber die DATEN, keine
   ueber den Markt.** Sie sagt, welcher Posten je Anbieter schon gemessen
   ist - damit die leere Tafel erklaerbar ist, statt nur leer zu sein.
"""

from __future__ import annotations

import logging

from . import geraete_tco_band, geraete_tco_grafik, geraete_tco_karten
from . import geraete_laufzeit, geraete_notbremse, geraete_vergleich
from ..analyze.geraete_pruefstatus import listen_aus_satz
from ..geraete_model import VERGLEICHBARE_ZUSTAENDE, Ratenzahlung, normalisiere
from ..tarif_model import NUR_MIT_GERAET, PREISTYP_LIVE_SHOP, vertrag_basis
from ..tco_model import (
    POSTEN_ANSCHLUSS,
    POSTEN_RABATTE,
    POSTEN_RATE,
    POSTEN_TARIF,
    POSTEN_ZUZAHLUNG,
    TCO_HORIZONT,
    _LUECKEN_OHNE_EINFLUSS_AUF_DIE_DIFFERENZ,
    Buendel,
    Rabatt,
    SimOnlyReferenz,
    geraeteanteil,
    kosten_ueber,
    sim_only_id,
    tco_24,
)

log = logging.getLogger(__name__)

EIGEN = "vodafone"

REFERENZEN_SICHTBAR = 4

PHASE_JE_LUECKE = {
    POSTEN_TARIF: "Phase 6 (Tarife: Bestand und Bezug)",
    POSTEN_ZUZAHLUNG: "Phase 4 (die Adapter liefern die volle Preisstruktur)",
    POSTEN_RATE: "Phase 4 (die Adapter liefern die volle Preisstruktur)",
    POSTEN_ANSCHLUSS: "Phase 6 (Anschlusspreis aus dem Produktinformationsblatt)",
    POSTEN_RABATTE: "offen – Boni stehen bei allen Anbietern im Fließtext",
}


def _eigen(anbieter: str) -> bool:
    return (anbieter or "").strip().lower() == EIGEN


def _label(katalog, device_id: str, speicher, rueckfall: str = "") -> str:
    """Der Geraetename aus dem KATALOG, nie aus dem Titel der Listung.

    Dieselbe Regel wie in `geraete_model`: Haendler benennen denselben
    Artikel staendig um. Ein Label aus `titel_roh` liesse dasselbe Geraet
    unter zwei Namen in derselben Tabelle stehen.
    """
    g = katalog.nach_id(device_id) if katalog else None
    if not g:
        return device_id or rueckfall or "?"
    return f"{g.modell} {speicher} GB" if speicher else g.modell


def _zeile(buendel: Buendel, referenz, katalog, geraet_je_sku) -> dict:
    """Eine Zeile der Tafel aus EINEM Buendel.

    `gesamt` und `monatlich` sind `None`, sobald die Rechnung nicht
    belastbar ist - siehe Regel 2 im Modulkopf. Die Bestandteile stehen
    trotzdem da: was gemessen ist, bleibt sichtbar, es ergibt nur noch keine
    Kennzahl.
    """
    ergebnis = tco_24(buendel)
    anteil = None
    if referenz is not None:
        anteil = geraeteanteil(buendel, referenz)

    return {
        "sku_id": buendel.sku_id,
        "geraet": _label(
            katalog,
            *geraet_je_sku.get(buendel.sku_id, ("", None)),
            rueckfall=buendel.sku_id,
        ),
        "anbieter": buendel.anbieter,
        "eigen": _eigen(buendel.anbieter),
        "tarif": buendel.tarif_name,
        "belastbar": ergebnis.belastbar,
        "delta_luecken": [
            n
            for n in ergebnis.luecken
            if n not in _LUECKEN_OHNE_EINFLUSS_AUF_DIE_DIFFERENZ
        ],
        "gesamt": ergebnis.gesamt if ergebnis.belastbar else None,
        "monatlich": ergebnis.monatlich if ergebnis.belastbar else None,
        "bestandteile": [
            {"name": n, "betrag": b} for n, b in ergebnis.bestandteile.items()
        ],
        "luecken": [
            {"name": n, "phase": PHASE_JE_LUECKE.get(n, "")} for n in ergebnis.luecken
        ],
        "restbetrag": ergebnis.restbetrag,
        "rabatte_offen": ergebnis.rabatte_offen,
        "geraeteanteil": anteil.betrag if anteil and anteil.belastbar else None,
        "quelle_url": buendel.quelle_url,
        "abgerufen_am": buendel.abgerufen_am,
    }


def _vergleichbar(zeile: dict) -> bool:
    """Darf diese Zeile in eine DIFFERENZ eingehen?

    Strenger als `Tco.belastbar`, und das ist der Punkt: belastbar heisst
    "die Zahl ist eine TCO", vergleichbar heisst "sie ist mit einer anderen
    verrechenbar". Eine Zeile, der die Geraeterate fehlt, ist das erste und
    nicht das zweite - ihre Differenz zu einer vollstaendigen Zeile ist der
    fehlende Geraetepreis und kein Preisvorteil.
    """
    return (
        zeile["belastbar"]
        and zeile["gesamt"] is not None
        and not zeile["delta_luecken"]
    )


def _zeilen_rang(karte: dict) -> tuple:
    return (
        not karte["belastbar"],
        karte["naeherung"],
        not karte.get("frisch", True),
        karte["gesamt"] if karte["gesamt"] is not None else 9e9,
        karte["anbieter"],
    )


def _wesentlich(differenz: float, bezug: float) -> bool:
    """Ist der Abstand eine Meldung wert? ODER, nicht UND - wie nebenan.

    Die Konstanten kommen aus `geraete_vergleich`, damit die zwei Tafeln
    derselben Seite nicht zwei Wesentlichkeitsbegriffe fuehren. Bei 200 EUR
    sind 15 EUR viel und 3 Prozent wenig, bei 2000 EUR umgekehrt.
    """
    abstand = abs(differenz)
    prozent = (abstand / bezug * 100) if bezug else 0.0
    return (
        prozent >= geraete_vergleich.WESENTLICH_PROZENT
        or abstand >= geraete_vergleich.WESENTLICH_EURO
    )


def _delta(zeilen: list) -> list[dict]:
    """Das Euro-Delta gegen Vodafone, je Geraet - Regel 3 des Modulkopfs.

    Verglichen wird die TCO-24 desselben GERAETS bei einem anderen Anbieter
    gegen unsere eigene. Beide Seiten muessen belastbar sein; eine Zeile mit
    Luecke traegt kein Vorzeichen.

    Was hier bewusst NICHT geprueft wird, ist die Vergleichbarkeit der
    TARIFE - und genau deshalb steht der Satz darueber auf der Seite: eine
    TCO vergleicht Gesamtkosten, keine Leistungen. Ein Tarif mit mehr
    Datenvolumen kostet zu Recht mehr, und dieses Modul kann das nicht
    wissen, solange ein Buendel seinen Tarif nur beim Namen kennt (§ 6.2
    Nr. 7: die Nutzlast nennt keinen Tarif-Fremdschluessel).
    """
    eigene: dict = {}
    for z in zeilen:
        if not (z["eigen"] and _vergleichbar(z)):
            continue
        bisher = eigene.get(z["sku_id"])
        if bisher is None or z["gesamt"] < bisher["gesamt"]:
            eigene[z["sku_id"]] = z
    if not eigene:
        return []

    treffer = []
    for z in zeilen:
        if z["eigen"] or not _vergleichbar(z):
            continue
        unser = eigene.get(z["sku_id"])
        if unser is None:
            continue
        differenz = round(z["gesamt"] - unser["gesamt"], 2)
        if not _wesentlich(differenz, unser["gesamt"]):
            continue
        treffer.append(
            {
                "geraet": z["geraet"],
                "sku_id": z["sku_id"],
                "anbieter": z["anbieter"],
                "tarif": z["tarif"],
                "fremd": z["gesamt"],
                "eigen": unser["gesamt"],
                "eigen_tarif": unser["tarif"],
                "quelle_url": z["quelle_url"],
                "eigen_quelle_url": unser["quelle_url"],
                "differenz": differenz,
                "guenstiger": differenz < 0,
                "abstand": abs(differenz),
            }
        )
    return sorted(treffer, key=lambda t: -t["abstand"])


def _bereitschaft(eintraege: list) -> list[dict]:
    """Je Anbieter: welcher Posten der TCO steht schon, welcher fehlt.

    Regel 4 des Modulkopfs: eine Auskunft ueber die DATEN. Ohne sie ist
    diese Tafel heute nur leer, und eine leere Tafel ohne Grund sieht aus
    wie ein Fehler - der Leser kann nicht unterscheiden, ob niemand gemessen
    hat oder ob es nichts zu messen gab.

    Gezaehlt wird auf Neugeraeten (`VERGLEICHBARE_ZUSTAENDE`): ein
    Gebrauchtpreis ist eine andere Preisdimension und beantwortet die Frage
    dieser Tafel nicht.
    """
    je_anbieter: dict[str, dict] = {}
    for e in eintraege:
        if (e.get("zustand") or "neu") not in VERGLEICHBARE_ZUSTAENDE:
            continue
        name = e.get("anbieter") or "?"
        satz = je_anbieter.setdefault(
            name,
            {
                "anbieter": name,
                "eigen": _eigen(name),
                "listungen": 0,
                "mit_raten": 0,
                "mit_betrag": 0,
                "raten_probe_ok": 0,
            },
        )
        satz["listungen"] += 1
        if e.get("preis_ohne_vertrag") is not None:
            satz["mit_betrag"] += 1
        raten = _raten(e)
        if raten is not None:
            satz["mit_raten"] += 1
            if raten.deckt(e.get("preis_ohne_vertrag")):
                satz["raten_probe_ok"] += 1

    zeilen = []
    for satz in je_anbieter.values():
        satz["preisform"] = (
            "Ratenzahlung"
            if satz["mit_raten"]
            else "Barkauf"
            if satz["mit_betrag"]
            else "-"
        )
        zeilen.append(satz)
    return sorted(
        zeilen, key=lambda z: (not z["eigen"], -z["listungen"], z["anbieter"])
    )


def _raten(eintrag: dict):
    """Die Ratenzahlung einer Listung, oder None.

    Sie wird aus denselben drei Feldern gebaut wie ueberall sonst. Ein
    unvollstaendiger Satz ergibt KEINE Ratenzahlung - eine Rate ohne
    Laufzeit ist keine Finanzierung, sondern eine Zahl.
    """
    anzahlung = eintrag.get("anzahlung")
    rate = eintrag.get("monatsrate")
    laufzeit = eintrag.get("laufzeit_monate")
    if anzahlung is None or rate is None or not laufzeit:
        return None
    try:
        return Ratenzahlung(
            anzahlung=float(anzahlung),
            monatsrate=float(rate),
            laufzeit_monate=int(laufzeit),
            zins_effektiv=eintrag.get("zins_effektiv"),
        )
    except (TypeError, ValueError):
        return None


_BUENDEL_FELDER = (
    "sku_id",
    "anbieter",
    "tarif_name",
    "tarif_id",
    "tarif_id_guete",
    "tarif_monatlich",
    "tarif_bindung_monate",
    "buendel_monatlich",
    "geraet_zuzahlung",
    "geraet_monatsrate",
    "laufzeit_monate",
    "anschlusspreis",
    "quelle_url",
    "abgerufen_am",
    "zustand",
    "herleitung",
    "pruefung",
)

_REFERENZ_FELDER = (
    "anbieter",
    "tarif_name",
    "tarif_id",
    "tarif_id_guete",
    "tarif_sim_only_monatlich",
    "anschlusspreis",
    "quelle_url",
    "abgerufen_am",
    "quelle_art",
)


def _rabatte(eintrag: dict) -> list:
    """Die Nachlaesse eines Datensatzes. Ein kaputter faellt weg, die
    uebrigen bleiben - ein Rabatt ohne Namen darf keine Zeile kosten."""
    fertig = []
    for r in eintrag.get("rabatte") or []:
        try:
            fertig.append(Rabatt(**r))
        except (TypeError, ValueError):
            continue
    return fertig


def _aus_speicher(eintraege: list, typ, felder: tuple) -> list:
    """Speicherdatensaetze in ihre Datenklasse - unlesbare fallen weg.

    Die Datenklassen setzen ihre Zusicherungen im Konstruktor durch
    (`Buendel.__post_init__`: kein Anbieter, kein Tarif, kein Geraetepreis
    ohne SKU). Ein Satz, der sie verletzt, ist kaputt und darf die TAFEL
    nicht kosten - er wird uebergangen, nicht repariert. Repariert stuende
    eine erfundene Zahl in einer Kennzahl, teurer als eine fehlende Zeile.
    """
    fertig = []
    for e in eintraege:
        if not isinstance(e, dict):
            fertig.append(e)
            continue
        werte = {f: e.get(f) for f in felder if e.get(f) is not None}
        if typ is Buendel:
            werte.update(listen_aus_satz(e))
        try:
            satz = typ(**werte, rabatte=_rabatte(e))
        except (TypeError, ValueError) as exc:
            log.warning("TCO-Datensatz %s uebergangen: %s", e.get("id", "?"), exc)
            continue
        fertig.append(satz)
    return fertig


_OHNE_BUENDEL = (POSTEN_TARIF, POSTEN_ANSCHLUSS, POSTEN_RABATTE)


def _offene_posten(zeilen: list, massstab: list | None = None) -> list[dict]:
    """Die Vereinigung der Luecken aller Zeilen, in fester Reihenfolge.

    Die VEREINIGUNG und nicht der Durchschnitt: gefragt ist, was der
    Rechnung noch irgendwo fehlt. Ein Posten, den nur die Haelfte der
    Anbieter ausweist, ist eine offene Baustelle und keine erledigte.

    Die Reihenfolge kommt aus `PHASE_JE_LUECKE` und nicht aus einem `set` -
    eine Liste, die je Lauf anders sortiert ist, erzeugt bei jedem Rendern
    einen Diff in `site/` und damit einen Commit ohne Inhalt.

    OHNE Buendel wird die Liste aus dem gerechnet, was der Bestand HAT.
    Vorher stand dort fest "Tarifgrundpreis fehlt, Phase 6" - und genau das
    ist am 04.09.2026 falsch geworden, als Phase 6 32 Tarife von vier
    Anbietern lieferte. Dieselbe Fehlerklasse, gegen die dieser Abschnitt
    ueberhaupt gerechnet statt hingeschrieben wird (B-Befund vom
    04.09.2026, gefunden beim ANSEHEN der Tafel).
    """
    if zeilen:
        offen = {n for z in zeilen for n in (l["name"] for l in z["luecken"])}
    else:
        offen = set(_OHNE_BUENDEL)
        if massstab:
            offen.discard(POSTEN_TARIF)
            if all(z["anschlusspreis"] is not None for z in massstab):
                offen.discard(POSTEN_ANSCHLUSS)
    return [
        {"name": n, "phase": PHASE_JE_LUECKE[n]} for n in PHASE_JE_LUECKE if n in offen
    ]


def _referenztabelle(referenzen: list) -> list[dict]:
    """Der Massstab, den Phase 6 geliefert hat: was der Tarif ALLEIN kostet.

    Diese Zahl ist der Grund, warum ein effektiver Geraetepreis ueberhaupt
    rechenbar ist (`tco_model.SimOnlyReferenz`) - und sie steht in keiner
    Werbung. Meistens kommt sie aus dem Produktinformationsblatt nach § 1
    TK-TransparenzV, dem einzigen Dokument dieses Marktes, das rechtlich
    wahrheitsbewehrt ist - seit dem 05.09.2026 kann sie auch aus einer
    LIVE-Shop-Seite stammen (`Tarif.preistyp == "live_shop"`,
    `analyze/tarif_referenzen.py`). `quelle_ist_dokument` traegt das an die
    Vorlage weiter: nur ein Pflichtdokument heisst dort
    "Produktinformationsblatt", eine Shop-Seite heisst "Shop-Seite" - ein
    Beleglink, der das falsche Wort traegt, ist selbst eine Falschangabe.

    Sortiert wird der EIGENE Anbieter zuerst, dann nach Anbietername und
    Betrag - dieselbe Ordnung wie auf jeder anderen Tafel dieser Seite. Es
    ist ausdruecklich KEINE Rangliste nach Guenstigkeit: ein Tarif mit mehr
    Datenvolumen kostet zu Recht mehr, und diese Tafel rechnet das nicht
    heraus.
    """
    zeilen = []
    for r in referenzen:
        if not isinstance(r, SimOnlyReferenz):
            continue
        if r.tarif_sim_only_monatlich is None:
            continue
        kennzahl = tco_24(r.als_buendel())
        zeilen.append(
            {
                "anbieter": r.anbieter,
                "eigen": _eigen(r.anbieter),
                "tarif": r.tarif_name,
                "tarif_id": r.tarif_id,
                "monatlich": r.tarif_sim_only_monatlich,
                "ueber_horizont": (kennzahl.gesamt if kennzahl.belastbar else None),
                "leitzahl_monate": kennzahl.leitzahl_monate,
                "anschlusspreis": r.anschlusspreis,
                "quelle_url": r.quelle_url,
                "abgerufen_am": r.abgerufen_am,
                "quelle_ist_dokument": r.quelle_art != PREISTYP_LIVE_SHOP,
            }
        )
    return sorted(zeilen, key=lambda z: (not z["eigen"], z["anbieter"], z["monatlich"]))


HAENDLER_OHNE_BUENDEL = geraete_tco_karten.HAENDLER_OHNE_BUENDEL
_haendler_ohne_buendel_preise = geraete_tco_karten._haendler_geraetepreise


def _nach_ratenlaufzeit(zeile: dict) -> tuple:
    """Sortierschlüssel des Exports: Ratenlaufzeit aufsteigend, ohne zuletzt."""
    laufzeit = zeile["laufzeit"]
    return (laufzeit is None, laufzeit if laufzeit is not None else 0)


def _export_zeilen(
    buendel: list,
    massstab: list,
    eintraege: list,
    katalog,
    band_je_tarif: dict,
    anbieter_typen: dict | None,
    heute: str = "",
) -> dict:
    """Die Zeilen des TCO-Gesamtexports (O4) - WERTE, keine Form.

    Hier steht JEDES Bündel des Bestands, auch eines ohne Tarifband und ohne
    auflösbare Gerätezuordnung (Modellspalte dann die SKU, wie `aktuell_csv`).
    Aufgelöst wird wie in der Modelltafel (`geraet_je_sku` plus Katalog), die
    Kostenspalte ist `tco_model.kosten_ueber()` wie auf der Karte; Dezimalkomma
    und Semikolon macht `geraete_export.tco_csv`. Eigene Felder: `sku_id` (A4),
    der Zeitraum H (`leitzahl_monate`, P0-B-h4), `status` (Notbremse, dasselbe
    Wort wie an der Bündelzeile), `luecke` (Posten ohne Zahl) und
    `raten_laufzeit` (die Ansicht des Umschalters, `geraete_laufzeit`). Die
    Bündelzeilen stehen nach Ratenlaufzeit gruppiert, sonst in Bestandsfolge.

    Die SIM-only-Zeilen sind DERSELBE Massstab wie auf der Tafel
    (`_referenztabelle`), `ueber_horizont` als ihre TCO-24 (`tco_24` über
    `als_buendel()` samt Anschlusspreis, dieselbe Stelle wie bei den Bündeln).
    """
    geraet_je_sku: dict = {}
    for e in eintraege:
        if e.get("sku_id"):
            geraet_je_sku.setdefault(
                e["sku_id"], (e.get("device_id") or "", e.get("speicher_gb"))
            )
    geraete_tco_karten.ergaenze_geraete_aus_katalog(geraet_je_sku, buendel, katalog)
    typen = anbieter_typen or {}
    band_von = geraete_tco_band.band_label

    zeilen = []
    for b in buendel:
        if not isinstance(b, Buendel):
            continue
        device_id, speicher = geraet_je_sku.get(b.sku_id) or ("", None)
        g = katalog.nach_id(device_id) if (katalog and device_id) else None
        kosten = kosten_ueber(b)
        zeilen.append(
            {
                "modell": (getattr(g, "modell", "") or device_id or b.sku_id),
                "hersteller": getattr(g, "hersteller", "") if g else "",
                "speicher": speicher,
                "anbieter": b.anbieter,
                "anbieter_typ": typen.get(b.anbieter, ""),
                "tarif": b.tarif_name,
                "band": band_von(band_je_tarif.get(b.tarif_id or "")),
                "zustand": b.zustand or "",
                "zuzahlung": b.geraet_zuzahlung,
                "tarif_monatlich": b.tarif_monatlich,
                "geraet_monatsrate": b.geraet_monatsrate,
                "buendel_monatlich": b.buendel_monatlich,
                "laufzeit": b.laufzeit_monate,
                "raten_laufzeit": geraete_laufzeit.raten_laufzeit(b),
                "anschlusspreis": b.anschlusspreis,
                "tco24": kosten.gesamt,
                "leitzahl_monate": kosten.monate,
                "abgerufen_am": b.abgerufen_am,
                "quelle_url": b.quelle_url,
                "sku_id": b.sku_id or "",
                "status": geraete_notbremse.kurz(b, heute),
                "luecke": ", ".join(kosten.luecken),
            }
        )
    zeilen.sort(key=_nach_ratenlaufzeit)
    sim = []
    for r in massstab:
        sim.append(
            {
                "anbieter": r["anbieter"],
                "anbieter_typ": typen.get(r["anbieter"], ""),
                "tarif": r["tarif"],
                "band": band_von(band_je_tarif.get(r.get("tarif_id") or "")),
                "tarif_monatlich": r["monatlich"],
                "anschlusspreis": r["anschlusspreis"],
                "tco24": r["ueber_horizont"],
                "leitzahl_monate": r["leitzahl_monate"],
                "abgerufen_am": r["abgerufen_am"],
                "quelle_url": r["quelle_url"],
            }
        )
    return {"buendel": zeilen, "sim_only": sim}


def aufbereiten(
    buendel: list,
    referenzen: list,
    eintraege: list,
    katalog,
    lesbar: bool = True,
    tarife: dict | None = None,
    anbieter_typen: dict | None = None,
    tco_historie: dict | None = None,
    heute: str = "",
) -> dict:
    """Alles, was der Reiter "Was kostet es" braucht.

    `buendel` und `referenzen` sind die Datensaetze aus
    `analyze/tco_store.TcoDB` - also Woerterbuecher, wie der Speicher sie
    ablegt.

    `anbieter_typen` (O4) ist {Name: Typ} aus der Quellenkonfiguration -
    der TCO-Export braucht die Spalte, und der Store trägt sie nicht.
    `tco_historie` (O4) ist `TcoDB.historie_lage()` - der ehrliche Satz
    über die Bündel-Historie im Verlaufs-Reiter nennt ihr ECHTES
    Startdatum, nicht das des Entwurfstages.
    `heute` (A3, "YYYY-MM-DD") schaltet die Alterung ein - ohne das
    Datum (Default) altert nichts (`geraete_tco_karten.ist_frisch`).
    """
    buendel = _aus_speicher(buendel, Buendel, _BUENDEL_FELDER)
    referenzen = _aus_speicher(referenzen, SimOnlyReferenz, _REFERENZ_FELDER)

    referenz_je_schluessel = {}
    referenz_je_id: dict[tuple, object] = {}
    mehrdeutig: set = set()
    for r in referenzen:
        if not isinstance(r, SimOnlyReferenz):
            continue
        referenz_je_schluessel[r.id] = r
        if (r.tarif_id or "").strip():
            schluessel = (normalisiere(r.anbieter), r.tarif_id.strip())
            if schluessel in referenz_je_id:
                mehrdeutig.add(schluessel)
            referenz_je_id[schluessel] = r
    for schluessel in mehrdeutig:
        log.info(
            "SIM-only-Massstab fuer %s ist nicht eindeutig (%s) - kein Geraeteanteil",
            schluessel[1],
            schluessel[0],
        )
        referenz_je_id.pop(schluessel, None)

    geraet_je_sku: dict[str, tuple] = {}
    for e in eintraege:
        if e.get("sku_id"):
            geraet_je_sku.setdefault(
                e["sku_id"], (e.get("device_id") or "", e.get("speicher_gb"))
            )
    geraete_tco_karten.ergaenze_geraete_aus_katalog(geraet_je_sku, buendel, katalog)

    tarife = tarife or {}
    for b in buendel:
        if isinstance(b, Buendel) and b.tarif_id:
            geraete_tco_karten.tarif_anreichern(b, tarife.get(b.tarif_id) or {})

    zeilen = []
    for b in buendel:
        if not isinstance(b, Buendel) or b.ohne_geraet:
            continue
        anb, tid = normalisiere(b.anbieter), (b.tarif_id or "").strip()
        referenz = referenz_je_schluessel.get(sim_only_id(b.anbieter, b.tarif_name))
        for schluessel in [(anb, tid), (anb, vertrag_basis(tid))] if tid else []:
            if referenz is None:
                referenz = referenz_je_id.get(schluessel)
        if b.tarif_id_guete == NUR_MIT_GERAET:
            referenz = None
        zeilen.append(_zeile(b, referenz, katalog, geraet_je_sku))

    zeilen.sort(
        key=lambda z: (
            not z["belastbar"],
            z["gesamt"] is None,
            z["gesamt"] or 0.0,
            z["geraet"],
        )
    )
    bereit = _bereitschaft(eintraege)
    massstab = _referenztabelle(referenzen)

    modelle = geraete_tco_karten.modelle(
        buendel, eintraege, referenzen, tarife, katalog, heute=heute
    )

    listungen_je_modell: dict[str, list] = {}
    for e in eintraege:
        mid = geraete_tco_karten.modell_schluessel(
            e.get("device_id"), e.get("speicher_gb")
        )
        listungen_je_modell.setdefault(mid, []).append(e)

    leiter = geraete_tco_band.tarifleiter(tarife)
    band_je_tarif = geraete_tco_band.tarif_baender(tarife, leiter)
    gb_je_tarif = {
        tid: (satz or {}).get("datenvolumen_gb") for tid, satz in (tarife or {}).items()
    }

    for modell in modelle["modelle"]:
        modell["svg"] = geraete_tco_grafik.balken(modell)
        modell["legende"] = geraete_tco_grafik.legende(modell)
        modell["haendler_ohne_buendel"] = _haendler_ohne_buendel_preise(
            listungen_je_modell.get(modell["id"], [])
        )
        modell["haendler_offen"] = [
            h
            for h in HAENDLER_OHNE_BUENDEL
            if modell["haendler_ohne_buendel"].get(h) is None
        ]
        for k in modell["karten"]:
            tid = (k.get("tarif_id") or "").strip()
            k["band"] = band_je_tarif.get(tid)
            k["band_gb_text"] = geraete_tco_band.gb_text(gb_je_tarif.get(tid))
            k["delta_kurz"] = (
                geraete_tco_band.delta_text(
                    k["delta"].get("betrag"),
                    k["delta"].get("prozent"),
                    ungefaehr=bool(k["delta"].get("ungefaehr")),
                )
                if k.get("delta")
                else None
            )
        echte = [k for k in modell["karten"] if k.get("sku_id") or k["naeherung"]]
        modell["zeilen_band"] = sorted(
            (k for k in echte if k.get("band")), key=_zeilen_rang
        )
        modell["zeilen_ohne_band"] = sorted(
            (k for k in echte if not k.get("band")), key=_zeilen_rang
        )
        je_laufzeit = {
            lz: geraete_tco_band.baender_fuer_modell(
                modell, band_je_tarif, gb_je_tarif, leiter, lz
            )
            for lz in geraete_laufzeit.LAUFZEITEN
        }
        modell["baender_je_laufzeit"] = je_laufzeit
        modell["baender"] = je_laufzeit[geraete_laufzeit.LAUFZEIT_STANDARD]
        leer = geraete_tco_band.band_leer_text(leiter)
        modell["band_leer"] = None if any(je_laufzeit.values()) else leer

    graph_daten = {
        "stand": max(
            (getattr(b, "abgerufen_am", "") or "" for b in buendel), default=""
        ),
        "gesamt": modelle["gesamt"],
        "vorgabe": modelle["vorgabe"],
        "modelle": [
            {
                "id": modell["id"],
                "titel": modell["titel"],
                "antwort": {
                    "geraetepreis": (
                        geraete_tco_grafik.euro(modell["antwort"]["geraetepreis"])
                        if modell["antwort"]["geraetepreis"] is not None
                        else None
                    ),
                    "geraetepreis_anbieter": modell["antwort"]["geraetepreis_anbieter"],
                    "tarif_gesamt": (
                        geraete_tco_grafik.euro(modell["antwort"]["tarif_gesamt"])
                        if modell["antwort"]["tarif_gesamt"] is not None
                        else None
                    ),
                    "tarif_anbieter": modell["antwort"]["tarif_anbieter"],
                },
                "baender": {
                    lz: {
                        b["key"]: {
                            "label": b["label"],
                            "bereich": b["bereich"],
                            "chip": b["chip"],
                            "unterzeile": b["unterzeile"],
                            "zeilen": b["balken"]["zeilen"],
                            "luecke_text": b["balken"]["luecke_text"],
                            "bnd_titel": (
                                f"Alle Bündel im Band {b['label']} – {modell['titel']}"
                            ),
                        }
                        for b in baender
                    }
                    for lz, baender in modell["baender_je_laufzeit"].items()
                },
                "band_leer": modell.get("band_leer"),
                "bnd_titel_ohne": f"Alle Bündel – {modell['titel']}",
            }
            for modell in modelle["modelle"]
        ],
    }

    return {
        "zeilen": zeilen,
        "delta": _delta(zeilen),
        "bereitschaft": bereit,
        "lesbar": lesbar,
        "offene_posten": _offene_posten(zeilen, massstab),
        "referenzen": massstab[:REFERENZEN_SICHTBAR],
        "referenzen_gesamt": len(massstab),
        "referenzen_rest": massstab[REFERENZEN_SICHTBAR:],
        "horizont": TCO_HORIZONT,
        "modelle": modelle["modelle"],
        "modell_vorgabe": modelle["vorgabe"],
        "modelle_gesamt": modelle["gesamt"],
        "graph_daten": graph_daten,
        "haendler_seit": geraete_tco_band.HAENDLER_SEIT,
        "ohne_zuordnung": modelle["ohne_zuordnung"],
        "anbieter_erwartet": list(geraete_tco_karten.ANBIETER_REIHENFOLGE),
        "baender_katalog": geraete_tco_band.baender_katalog(leiter),
        "band_je_tarif": band_je_tarif,
        "export": _export_zeilen(
            buendel, massstab, eintraege, katalog, band_je_tarif, anbieter_typen, heute
        ),
        "historie_lage": tco_historie
        if tco_historie is not None
        else {"messtage": 0, "seit": "", "buendel": 0},
    }


def leer() -> dict:
    """Der Zustand ohne lesbare Geraetedatenbank."""
    return {
        "zeilen": [],
        "delta": [],
        "bereitschaft": [],
        "lesbar": True,
        "offene_posten": _offene_posten([]),
        "referenzen": [],
        "referenzen_gesamt": 0,
        "referenzen_rest": [],
        "horizont": TCO_HORIZONT,
        "modelle": [],
        "modell_vorgabe": "",
        "modelle_gesamt": 0,
        "ohne_zuordnung": [],
        "graph_daten": None,
        "haendler_seit": geraete_tco_band.HAENDLER_SEIT,
        "anbieter_erwartet": list(geraete_tco_karten.ANBIETER_REIHENFOLGE),
        "baender_katalog": [],
        "band_je_tarif": {},
        "export": {"buendel": [], "sim_only": []},
        "historie_lage": {"messtage": 0, "seit": "", "buendel": 0},
    }
