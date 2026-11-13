"""Reiter "Was kostet es": die Daten fuer Zeitreihe, Export und Notbremse.

Gerechnet wird ausschliesslich in `tco_model`. Dieses Modul ruft
`kosten_ueber()` auf und formt das Ergebnis; es addiert selbst keinen Euro.
Zwei Rechnungen derselben Zahl sind zwei Zahlen. Widerlegte Bündel: `bereinigt`.

Fehlt ein Posten, steht die benannte Luecke statt einer Zahl: "Wenn kein
Anschlusspreis bekannt ist, heisst das nicht kostenlos" (`report/effektivpreis.py`,
`tco_model` § 6.4). Tarifliste, Bereitschaftstabelle und Euro-Differenz gegen
Vodafone: seit 02.11.2026 von der Seite genommen."""

from __future__ import annotations

import logging

from ..analyze.geraete_pruefstatus import listen_aus_satz
from ..analyze.geraete_widerspruch import bereinigt
from ..band_regel import band_fuer
from ..tco_model import (
    TCO_HORIZONT,
    Buendel,
    Rabatt,
    SimOnlyReferenz,
    kosten_ueber,
)
from ..versandkosten import POSTEN_VERSAND
from . import (
    geraete_laufzeit,
    geraete_notbremse,
    geraete_preisstand,
    geraete_stufen,
    geraete_tco_band,
    geraete_tco_grafik,
    geraete_tco_karten,
    geraete_zeilenband,
)
from .geraete_tco_referenz import referenztabelle as _referenztabelle
from .geraete_zuordnung_satz import ANBIETER_UNBEKANNT as ANBIETER_UNBEKANNT
from .geraete_zuordnung_satz import ohne_zuordnung_satz

log = logging.getLogger(__name__)

_KEINE_HISTORIE = {"messtage": 0, "seit": "", "buendel": 0}


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
    "beleg_id",
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

    Hier steht jedes zählende Bündel, auch eines ohne Tarifband und ohne
    auflösbare Gerätezuordnung (Modellspalte dann die SKU, wie `aktuell_csv`).
    Aufgelöst wird wie in der Modelltafel (`geraet_je_sku` plus Katalog), die
    Kostenspalte ist `tco_model.kosten_ueber()` wie auf der Karte; Dezimalkomma
    und Semikolon macht `geraete_export.tco_csv`. Eigene Felder: `sku_id` (A4),
    Zeitraum H (`leitzahl_monate`) mit seinen Tarifmonaten, `status` (Notbremse),
    `luecke` (Posten ohne Zahl), `raten_laufzeit` (Umschalter, gruppiert nach
    ihm) und `versand` (P5). Ein veralteter Preis trägt keinen Betrag.

    Die SIM-only-Zeilen sind DERSELBE Massstab wie auf der Tafel
    (`_referenztabelle`), `ueber_horizont` als ihre TCO-24 (`tco_24` über
    `als_buendel()` samt Anschlusspreis, dieselbe Stelle wie bei den Bündeln)."""
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
                "band": band_von(band_fuer(band_je_tarif, b.tarif_id or "", b.id)),
                "zustand": b.zustand or "",
                "zuzahlung": None if veraltet else b.geraet_zuzahlung,
                "tarif_monatlich": None if veraltet else b.tarif_monatlich,
                "geraet_monatsrate": None if veraltet else b.geraet_monatsrate,
                "buendel_monatlich": None if veraltet else b.buendel_monatlich,
                "laufzeit": b.laufzeit_monate,
                "raten_laufzeit": geraete_laufzeit.raten_laufzeit(b),
                "anschlusspreis": None if veraltet else b.anschlusspreis,
                "versand": None if veraltet else kosten.posten.get(POSTEN_VERSAND, 0.0),
                "tco24": None if veraltet else kosten.gesamt,
                "leitzahl_monate": kosten.monate,
                "tarif_monate": kosten.tarifmonate,
                "abgerufen_am": b.abgerufen_am,
                "quelle_url": b.quelle_url,
                "sku_id": b.sku_id or "",
                "status": geraete_notbremse.kurz(b, heute),
                "luecke": geraete_laufzeit.luecke_export_text(b, kosten, veraltet),
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
    anbieter_anzeige: dict | None = None,
) -> dict:
    """Alles, was der Reiter "Was kostet es" braucht.

    `buendel` und `referenzen` sind die Datensaetze aus `analyze/tco_store.TcoDB`
    - also Woerterbuecher, wie der Speicher sie ablegt.

    `anbieter_typen` (O4) ist {Name: Typ} aus der Quellenkonfiguration -
    der TCO-Export braucht die Spalte, und der Store trägt sie nicht.
    `tco_historie` (O4) ist `TcoDB.historie_lage()` - der ehrliche Satz
    über die Bündel-Historie im Verlaufs-Reiter nennt ihr ECHTES
    Startdatum, nicht das des Entwurfstages. Dazu `schwankend`
    (`analyze/geraete_schwankung.lage_mit_schwankung`): die IDs mit springenden
    Werten; fehlt es, trägt keine Zeile eines unbegrenzten Tarifs ein Band.
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
    buendel = bereinigt(buendel, geraet_je_sku)
    tarife = tarife or {}
    for b in buendel:
        if isinstance(b, Buendel) and b.tarif_id:
            geraete_tco_karten.tarif_anreichern(b, tarife.get(b.tarif_id) or {})

    massstab = _referenztabelle(referenzen)
    leiter = geraete_tco_band.tarifleiter(tarife)
    band_je_tarif = geraete_zeilenband.zeilen_baender(
        tarife, buendel, (tco_historie or {}).get("schwankend"), leiter
    )
    modelle = geraete_tco_karten.modelle(
        buendel, eintraege, referenzen, tarife, katalog, heute, band_je_tarif
    )

    listungen_je_modell: dict[str, list] = {}
    for e in eintraege:
        mid = geraete_tco_karten.modell_schluessel(
            e.get("device_id"), e.get("speicher_gb")
        )
        listungen_je_modell.setdefault(mid, []).append(e)

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
            k["band"] = band_fuer(band_je_tarif, tid, k.get("buendel_id", ""))
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
    geraete_stufen.haenge_an(modelle["modelle"], tarife, band_je_tarif)

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
        "tarifstufen_regel": geraete_stufen.TARIFSTUFEN_REGEL,
        "baender_katalog": geraete_tco_band.baender_katalog(leiter),
        "band_je_tarif": band_je_tarif,
        "export": _export_zeilen(
            buendel, massstab, eintraege, katalog, band_je_tarif, anbieter_typen, heute
        ),
        "historie_lage": {
            k: v
            for k, v in (tco_historie or _KEINE_HISTORIE).items()
            if k != "schwankend"
        },
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
        "tarifstufen_regel": geraete_stufen.TARIFSTUFEN_REGEL,
        "graph_daten": None,
        "baender_katalog": [],
        "band_je_tarif": {},
        "export": {"buendel": [], "sim_only": []},
        "historie_lage": dict(_KEINE_HISTORIE),
    }
