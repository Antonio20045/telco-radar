"""Reiter "Was kostet es": die Daten fuer Zeitreihe, Export und Notbremse.

Gerechnet wird ausschliesslich in `tco_model`. Dieses Modul ruft
`kosten_ueber()` auf und formt das Ergebnis; es addiert selbst keinen Euro.
Zwei Rechnungen fuer dieselbe Zahl sind zwei Zahlen (CLAUDE.md § 6) - und die
eine davon stuende in einer Vorlage, wo sie niemand testet.

Fehlt ein Posten, steht die benannte Luecke statt einer Zahl: "Wenn kein
Anschlusspreis bekannt ist, heisst das nicht kostenlos"
(`report/effektivpreis.py`, `tco_model` § 6.4). Die Tarifliste, die
Bereitschaftstabelle und die Euro-Differenz gegen Vodafone sind seit dem
02.11.2026 von der Seite genommen und hier nicht mehr gerechnet.
"""

from __future__ import annotations

import logging

from ..analyze.geraete_pruefstatus import listen_aus_satz
from ..tarif_model import PREISTYP_LIVE_SHOP
from ..tco_model import (
    TCO_HORIZONT,
    Buendel,
    Rabatt,
    SimOnlyReferenz,
    kosten_ueber,
    tco_24,
)
from . import (
    geraete_laufzeit,
    geraete_notbremse,
    geraete_preisstand,
    geraete_tco_band,
    geraete_tco_grafik,
    geraete_tco_karten,
)

log = logging.getLogger(__name__)

EIGEN = "vodafone"


def _eigen(anbieter: str) -> bool:
    return (anbieter or "").strip().lower() == EIGEN


def _zeilen_rang(karte: dict) -> tuple:
    return (
        not karte["belastbar"],
        karte["naeherung"],
        not karte.get("frisch", True),
        karte["gesamt"] if karte["gesamt"] is not None else 9e9,
        karte["anbieter"],
    )


_BUENDEL_FELDER = (
    "sku_id",
    "anbieter",
    "tarif_name",
    "tarif_id",
    "tarif_id_guete",
    "tarif_monatlich",
    "tarif_listenpreis",
    "tarif_bindung_monate",
    "buendel_monatlich",
    "geraet_zuzahlung",
    "geraet_monatsrate",
    "laufzeit_monate",
    "anschlusspreis",
    "quelle_url",
    "abgerufen_am",
    "quelle_art",
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
        if not isinstance(r, SimOnlyReferenz) or r.tarif_sim_only_monatlich is None:
            continue
        kennzahl, allein = tco_24(r.als_buendel()), tco_24(r.als_buendel(False))
        zeilen.append(
            {
                "anbieter": r.anbieter,
                "eigen": _eigen(r.anbieter),
                "tarif": r.tarif_name,
                "tarif_id": r.tarif_id,
                "monatlich": r.tarif_sim_only_monatlich,
                "ueber_horizont": (kennzahl.gesamt if kennzahl.belastbar else None),
                "tarif_ueber_horizont": allein.gesamt if allein.belastbar else None,
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
    Zeitraum H (`leitzahl_monate`), `status` (Notbremse), `luecke` (Posten ohne
    Zahl) und `raten_laufzeit` (Umschalter); nach Ratenlaufzeit gruppiert. Ein
    veralteter Preis (`geraete_preisstand.buendel_luecke`) trägt keinen Betrag.

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
        veraltet = geraete_preisstand.buendel_luecke(b, heute)
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
                "zuzahlung": None if veraltet else b.geraet_zuzahlung,
                "tarif_monatlich": None if veraltet else b.tarif_monatlich,
                "geraet_monatsrate": None if veraltet else b.geraet_monatsrate,
                "buendel_monatlich": None if veraltet else b.buendel_monatlich,
                "laufzeit": b.laufzeit_monate,
                "raten_laufzeit": geraete_laufzeit.raten_laufzeit(b),
                "anschlusspreis": None if veraltet else b.anschlusspreis,
                "tco24": None if veraltet else kosten.gesamt,
                "leitzahl_monate": kosten.monate,
                "abgerufen_am": b.abgerufen_am,
                "quelle_url": b.quelle_url,
                "sku_id": b.sku_id or "",
                "status": geraete_notbremse.kurz(b, heute),
                "luecke": veraltet or ", ".join(kosten.luecken),
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


ANBIETER_UNBEKANNT = "ein unbekannter Anbieter"


def ohne_zuordnung_satz(offen: list, anbieter_anzeige: dict | None = None) -> str:
    """Der Satz zu Buendeln, die auf keinem Geraet stehen - oder `""`.

    Er nennt je Anbieter den Anzeigenamen und die Zahl der Buendel; der
    Schluessel aus der Quellenkonfiguration erscheint nie auf der Seite.
    Ein leerer Anbietername heisst `ANBIETER_UNBEKANNT`, nicht "?"
    (Clean Code 4). Reihenfolge: viele zuerst, dann nach Name.
    """
    anzeige = anbieter_anzeige or {}
    je_name: dict[str, int] = {}
    for o in offen:
        schluessel = o.get("anbieter") or ""
        name = anzeige.get(schluessel) or schluessel or ANBIETER_UNBEKANNT
        je_name[name] = je_name.get(name, 0) + 1
    if not je_name:
        return ""
    teile = [
        f"{zahl} Bündel von {name}"
        for name, zahl in sorted(je_name.items(), key=lambda t: (-t[1], t[0]))
    ]
    return (
        "Nicht auf der Tafel, weil kein Gerät zuzuordnen ist: " + ", ".join(teile) + "."
    )


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
    anbieter_anzeige: dict | None = None,
) -> dict:
    """Alles, was der Reiter "Was kostet es" braucht.

    `buendel` und `referenzen` sind die Datensaetze aus `analyze/tco_store.TcoDB`
    - also Woerterbuecher, wie der Speicher sie ablegt.

    `anbieter_typen` (O4) ist {Name: Typ} aus der Quellenkonfiguration -
    der TCO-Export braucht die Spalte, und der Store trägt sie nicht.
    `tco_historie` (O4) ist `TcoDB.historie_lage()` - der ehrliche Satz
    über die Bündel-Historie im Verlaufs-Reiter nennt ihr ECHTES
    Startdatum, nicht das des Entwurfstages.
    `anbieter_anzeige` ist {Schluessel: Anzeigename} fuer den Satz zu
    Buendeln ohne Geraet (`ohne_zuordnung_satz`).
    `heute` (A3, "YYYY-MM-DD") schaltet die Alterung ein - ohne das
    Datum (Default) altert nichts (`geraete_tco_karten.ist_frisch`).
    """
    buendel = _aus_speicher(buendel, Buendel, _BUENDEL_FELDER)
    referenzen = _aus_speicher(referenzen, SimOnlyReferenz, _REFERENZ_FELDER)

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
        "lesbar": lesbar,
        "horizont": TCO_HORIZONT,
        "modelle": modelle["modelle"],
        "modell_vorgabe": modelle["vorgabe"],
        "graph_daten": graph_daten,
        "ohne_zuordnung": modelle["ohne_zuordnung"],
        "ohne_zuordnung_satz": ohne_zuordnung_satz(
            modelle["ohne_zuordnung"], anbieter_anzeige
        ),
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
        "lesbar": True,
        "horizont": TCO_HORIZONT,
        "modelle": [],
        "modell_vorgabe": "",
        "ohne_zuordnung": [],
        "ohne_zuordnung_satz": "",
        "graph_daten": None,
        "baender_katalog": [],
        "band_je_tarif": {},
        "export": {"buendel": [], "sim_only": []},
        "historie_lage": {"messtage": 0, "seit": "", "buendel": 0},
    }
