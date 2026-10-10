"""Wettbewerbs-Radar (RAD-1, 08.09.2026): §2b woertlich.

DIE FRAGE, WEGEN DER DIESE SEITE EXISTIERT
-------------------------------------------
    "Bei welchen Modellen ist Vodafone gerade teurer als der Wettbewerb,
     und um wie viel?" (Antonios Beispiel: "hier ist Vodafone 10 % teurer
     als der Wettbewerber bei dem Modell.")

Leitzahl ist die %-ABWEICHUNG MIT VORZEICHEN, nicht der Absolutpreis:

    (Wettbewerber_TCO24 - Vodafone_TCO24) / Vodafone_TCO24 * 100

positiv = Wettbewerber teurer (gut fuer Vodafone), negativ = Wettbewerber
guenstiger (schlecht fuer Vodafone - "zuungunsten Vodafones", genau der
Fall aus Antonios Beispiel). Sortiert wird deshalb AUFSTEIGEND: die
staerkste Benachteiligung Vodafones (der kleinste, also negativste Wert)
steht zuerst. **Diese Reihenfolge ist eine bewusste Leseentscheidung, kein
Versehen - siehe die Anmerkung am Ende dieses Kopfes.**

WARUM DIESE DATEI KEINE ZWEITE RECHNUNG IST
--------------------------------------------
Gerechnet wird ausschliesslich in `tco_model` (`kosten_ueber()`), gelesen
ueber die fertigen Karten aus `geraete_tco_karten.modelle()`. Diese Datei
rechnet nur die EINE Division der Abweichung aus zwei fertigen Betraegen.

NOTBREMSE (Datenkonzept Geräteradar, Schritt 1)
-----------------------------------------------
Paare, Belegzeilen und damit die Kernzahl nehmen nur Karten, die zaehlen
(`geraete_notbremse.zaehlt`): eine Schaetzung oder ein Preis mit abgelaufener
Aktion stellt keine Zahl. Traegt ein Wettbewerber nur solche Karten, nennt
seine Zeile den Zustand der Notbremse statt eines Betrags.

BASIS JE GERAET, BAND UND LAUFZEIT ALS SCHRANKE (§2b/§7)
---------------------------------------------------------
Die Basis ist `modell["referenz"]` - dieselbe Vodafone-Referenz wie in der
TCO-Hauptansicht (Standardansicht 24 Raten, sonst die Naeherung). Verglichen
wird ein Wettbewerber aber nur in einem Paar (Tarifband, Ratenlaufzeit), in
dem BEIDE das Geraet fuehren, und dann gegen VODAFONES KARTE IN DIESEM PAAR
(Datenkonzept Geraete Schritt 2: 24 Raten nie gegen 36). Gegen die Referenz
gerechnet waere fast jede Zeile ein Mismatch, obwohl echte Paare existieren
(iPhone 15: VF-Basis Klein 1.235,80, aber VF selbst Mittel 1.949,80 gegen o2
Mittel 808,75). JEDE echte Karte des Wettbewerbers steht in JEDEM
gemeinsamen Paar da (RAD-1b); fehlt Vodafone in ihrer Laufzeit, nennt die
Zeile beide Laufzeiten. Ohne gemeinsames Band heisst sie "Band-Mismatch"
(AUFTRAG_GERAETESEITE.md §2b: "ehrlich benennen, nicht mischen").

WETTBEWERBERKREIS
------------------
Netzbetreiber: Telekom, 1&1, o2 (`geraete_tco_karten.ANBIETER_REIHENFOLGE`
ohne Vodafone) - je Modell IMMER da, auch ohne Bündel (ehrliches
kein_buendel statt Weglassen, B.2.5). Die Zweitmarke congstar (B3) nur mit
Karte und ohne Platzhalter: kein Vollsortimenter, keine Wand aus Luecken.
Haendler (Saturn, mobilcom-debitel, Amazon) vergleichen Gerätepreis gegen
Gerätepreis mit derselben %-Formel; Quelle ist `geraete_vergleich.vergleich()`
mit dem Filter anbieter_typ == "handel" - keine zweite Preisrechnung.

DIE SORTIERRICHTUNG (Widerspruch im Auftrag aufgeloest)
-------------------------------------------------------
BRIEF_RAD1.md widerspricht sich bei "zuungunsten Vodafones". Die Normen-Quelle
(AUFTRAG_GERAETESEITE.md §2b) entscheidet mit ihrem Beispiel "hier ist
Vodafone 10 % teurer als der Wettbewerber": das ist der NEGATIVE Wert
(Wettbewerber guenstiger). Sortiert wird deshalb aufsteigend, negativste
Werte zuerst - Begruendung in `outputs/rad1-2026-09-08.md`.
"""

from __future__ import annotations

from typing import Optional

from ..tco_model import zeitraum_vergleichbar
from . import geraete_laufzeit, geraete_tco_band, geraete_tco_karten
from . import geraete_notbremse as notbremse
from .geraete_laufzeit import LAUFZEIT_STANDARD, LAUFZEITEN, ansicht

NETZ_WETTBEWERBER = tuple(
    a for a in geraete_tco_karten.ANBIETER_REIHENFOLGE if a != "Vodafone"
)

ZWEITMARKEN_MIT_BUENDEL = ("congstar",)

ALLE_WETTBEWERBER = NETZ_WETTBEWERBER + ZWEITMARKEN_MIT_BUENDEL

STATUS_VERGLEICHBAR = "vergleichbar"
STATUS_BAND_MISMATCH = "band_mismatch"
STATUS_KEIN_BUENDEL = "kein_buendel"
STATUS_NICHT_VERGLEICHBAR = "nicht_vergleichbar"


def _grund_anderer_zeitraum(
    anbieter: str, karte: dict, vf_monate: Optional[int], raten: tuple
) -> str:
    """Der Satz, der eine Zahl mit fremdem Zeitraum benennt (P0-B-h3).

    Er nennt BEIDE Zeitraeume - "nicht vergleichbar" allein liest sich
    wie ein Mangel des Angebots, und der Strich der Prozentspalte hiesse
    "kein Angebot" (A2). Dieselbe Aussage wie an der Buendelzeile
    (`geraete_tco_karten.delta_zustand`), nur an dieser Tabelle in einem
    Satz statt in zwei Feldern. Ein unbekannter Zeitraum wird benannt,
    nicht als 24 geraten (Clean Code 3/4); `raten` nennt beide Ratenlaufzeiten.
    Ein Betrag für Tarif und Gerät über 36 Monate nennt `fehlt_satz`.
    """
    monate = karte.get("leitzahl_monate")
    if geraete_laufzeit.nur_ueber_24(karte):
        lz = karte.get("raten_laufzeit")
        return geraete_laufzeit.fehlt_satz(anbieter, [karte], lz)
    dieses, gegen = (
        (f"{r} Raten über " if r is not None else "")
        + (f"{m} Monate" if m is not None else "eine nicht gemessene Laufzeit")
        for r, m in zip(raten, (monate, vf_monate), strict=True)
    )
    return (
        f"Die Zahl von {anbieter} trägt {dieses}, die Vodafone-Zahl "
        f"{gegen} – über zwei Laufzeiten gibt es keinen Abstand."
    )


SICHTBAR_MAX = 15
HAENDLER_SICHTBAR_MAX = 6

MODELLISTE_SICHTBAR = 5

GRAFIK_MAX = 12


def _band_label(band: Optional[str]) -> str:
    return geraete_tco_band.band_label(band) or "nicht bestimmbar"


def _band_rang(katalog: list | None) -> dict:
    """Einfuegereihenfolge der Stufen in einer Gruppe: die Leiterfolge aus
    dem Katalog (XS, S, M, L, XL) - alphabetisch stuende "l" vor "xs".
    Wirkt nur bei prozent-Gleichstand (die Endsortierung der Zeilen rechnet
    nach Prozent)."""
    return {b["key"]: i for i, b in enumerate(katalog or [])}


def _beleg(quelle_url: str, abgerufen_am: str) -> dict:
    return {"quelle_url": quelle_url or "", "abgerufen_am": abgerufen_am or ""}


def _vodafone_basis(modell: dict, band_je_tarif: dict) -> Optional[dict]:
    """Die EINE Vodafone-Referenz dieses Geraets, mit ihrem Tarifband.

    `ref["aus_buendel"]` steht nur, wenn `_referenz_aus_buendel` sie gebaut
    hat (ein ECHTES eigenes Buendel) - sonst kommt sie aus
    `_vodafone_referenz` (Tarifgrundpreis + Barpreis, C.1-Naeherung).
    """
    ref = modell.get("referenz")
    if not ref or ref.get("gesamt") is None:
        return None
    band = band_je_tarif.get(ref.get("tarif_id") or "")
    return {
        "gesamt": ref["gesamt"],
        "monate": ref.get("monate"),
        "tarif": ref.get("tarif", ""),
        "naeherung": not bool(ref.get("aus_buendel")),
        "ansicht": ref.get("ansicht"),
        "band": band,
        "band_label": _band_label(band),
        "quelle_url": ref.get("geraet_quelle_url", "")
        or ref.get("tarif_quelle_url", ""),
        "abgerufen_am": (
            ref.get("geraet_abgerufen_am", "") or ref.get("tarif_abgerufen_am", "")
        ),
        "tarif_quelle_url": ref.get("tarif_quelle_url", ""),
        "tarif_abgerufen_am": ref.get("tarif_abgerufen_am", ""),
    }


def _notbremse_satz(karte: dict | None) -> str:
    """Der benannte Zustand einer Karte, die nicht zählt (Schätzung, abgelaufene
    Aktion; `geraete_notbremse`), sonst leer. Sie stellt keine Zahl im Radar."""
    return (notbremse.zustand(karte or {}) or {}).get("satz", "")


def _zeile_fuer_anbieter(
    anbieter: str, karte: Optional[dict], basis: dict, band_je_tarif: dict
) -> dict:
    """Eine Zeile des Wettbewerbers gegen die Vodafone-Basis dieses Geraets."""
    grund = "" if karte is None else (karte.get("leer_grund") or "")
    if karte is None or not karte.get("belastbar") or karte.get("gesamt") is None:
        return {
            "anbieter": anbieter,
            "status": STATUS_KEIN_BUENDEL,
            "prozent": None,
            "gesamt": None,
            "tarif": "",
            "band": None,
            "band_label": "",
            "grund": grund
            or f"Für dieses Modell ist bei {anbieter} kein Bündel erhoben.",
            **_beleg("", ""),
        }
    if satz := _notbremse_satz(karte):
        return {
            "anbieter": anbieter,
            "status": STATUS_NICHT_VERGLEICHBAR,
            "prozent": None,
            "gesamt": None,
            "tarif": "",
            "band": None,
            "band_label": "",
            "grund": satz,
            **_beleg("", ""),
        }
    if karte.get("frisch") is False:
        return {
            "anbieter": anbieter,
            "status": STATUS_NICHT_VERGLEICHBAR,
            "prozent": None,
            "gesamt": karte["gesamt"],
            "tarif": karte.get("tarif", ""),
            "band": None,
            "band_label": "",
            "grund": karte.get("alt_marke", ""),
            **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", "")),
        }
    if not karte.get("vergleichbar", True):
        return {
            "anbieter": anbieter,
            "status": STATUS_NICHT_VERGLEICHBAR,
            "prozent": None,
            "gesamt": karte["gesamt"],
            "tarif": karte.get("tarif", ""),
            "band": None,
            "band_label": "",
            "grund": (
                f"{anbieter} führt für dieses Gerät nur ein "
                f"{karte.get('zustand_etikett') or 'nicht neues'} "
                "Gerät – kein Vergleich gegen ein Neugerät."
            ),
            **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", "")),
        }

    band = band_je_tarif.get(karte.get("tarif_id") or "")
    if basis["band"] is None or band is None or band != basis["band"]:
        vf_band = basis["band_label"]
        wb_band = _band_label(band)
        grund = (
            f"Kein Tarifband, in dem beide dieses Gerät führen "
            f"(Vodafone: {vf_band}, {anbieter}: {wb_band}) – "
            "nicht vergleichbar (Tarifband-Mismatch)."
        )
        return {
            "anbieter": anbieter,
            "status": STATUS_BAND_MISMATCH,
            "prozent": None,
            "gesamt": karte["gesamt"],
            "tarif": karte.get("tarif", ""),
            "band": band,
            "band_label": wb_band,
            "grund": grund,
            **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", "")),
        }

    if ansicht(karte) != basis.get("ansicht") or not zeitraum_vergleichbar(
        karte.get("leitzahl_monate"), basis.get("monate")
    ):
        return {
            "anbieter": anbieter,
            "status": STATUS_NICHT_VERGLEICHBAR,
            "prozent": None,
            "gesamt": karte["gesamt"],
            "vf_gesamt": basis["gesamt"],
            "tarif": karte.get("tarif", ""),
            "band": band,
            "band_label": _band_label(band),
            "grund": _grund_anderer_zeitraum(
                anbieter,
                karte,
                basis.get("monate"),
                (ansicht(karte), basis.get("ansicht")),
            ),
            **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", "")),
        }
    prozent = round((karte["gesamt"] - basis["gesamt"]) / basis["gesamt"] * 100, 1)
    return {
        "anbieter": anbieter,
        "status": STATUS_VERGLEICHBAR,
        "prozent": prozent,
        "gesamt": karte["gesamt"],
        "vf_gesamt": basis["gesamt"],
        "tarif": karte.get("tarif", ""),
        "band": band,
        "band_label": _band_label(band),
        "grund": "",
        **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", "")),
    }


def _paar_zeile(anbieter: str, band: str, wb_karte: dict, vf_karte: dict) -> dict:
    """Vergleichbare Zeile: beide Karten liegen im SELBEN Band, und die
    Abweichung rechnet gegen VODAFONES KARTE IN DIESEM BAND - nicht gegen
    die Referenz des Geraets (Grund im Modulkopf, BASIS JE GERAET).
    GRAPH-1 vergleicht INNERHALB eines Bandes; diese Zeile tut dasselbe
    und nennt die VF-Gegenkarte im Beleg."""
    if not wb_karte.get("vergleichbar", True):
        return {
            "anbieter": anbieter,
            "status": STATUS_NICHT_VERGLEICHBAR,
            "prozent": None,
            "gesamt": wb_karte["gesamt"],
            "vf_gesamt": vf_karte["gesamt"],
            "tarif": wb_karte.get("tarif", ""),
            "band": band,
            "band_label": _band_label(band),
            "grund": (
                f"{anbieter} führt für dieses Gerät nur ein "
                f"{wb_karte.get('zustand_etikett') or 'nicht neues'} "
                "Gerät – kein Vergleich gegen ein Neugerät."
            ),
            **_beleg(wb_karte.get("quelle_url", ""), wb_karte.get("abgerufen_am", "")),
        }
    raten = (ansicht(wb_karte), ansicht(vf_karte))
    if raten[0] != raten[1] or not zeitraum_vergleichbar(
        wb_karte.get("leitzahl_monate"), vf_karte.get("leitzahl_monate")
    ):
        return {
            "anbieter": anbieter,
            "status": STATUS_NICHT_VERGLEICHBAR,
            "prozent": None,
            "gesamt": wb_karte["gesamt"],
            "vf_gesamt": vf_karte["gesamt"],
            "tarif": wb_karte.get("tarif", ""),
            "band": band,
            "band_label": _band_label(band),
            "grund": _grund_anderer_zeitraum(
                anbieter, wb_karte, vf_karte.get("leitzahl_monate"), raten
            ),
            **_beleg(wb_karte.get("quelle_url", ""), wb_karte.get("abgerufen_am", "")),
        }
    prozent = round(
        (wb_karte["gesamt"] - vf_karte["gesamt"]) / vf_karte["gesamt"] * 100, 1
    )
    return {
        "anbieter": anbieter,
        "status": STATUS_VERGLEICHBAR,
        "prozent": prozent,
        "gesamt": wb_karte["gesamt"],
        "vf_gesamt": vf_karte["gesamt"],
        "laufzeit": raten[0],
        "monate": vf_karte.get("leitzahl_monate"),
        "tarif": wb_karte.get("tarif", ""),
        "band": band,
        "band_label": _band_label(band),
        "grund": "",
        **_beleg(wb_karte.get("quelle_url", ""), wb_karte.get("abgerufen_am", "")),
    }


def _guenstigste_echte_karte_je_anbieter(modell: dict) -> dict[str, dict]:
    """Je Wettbewerber seine GUENSTIGSTE echte Karte (Band egal) - die
    Belegzeile fuer einen Band-Mismatch. Dieselbe Auswahlregel wie
    `geraete_tco_band.karten_je_band`, nur ohne die Bandtrennung.

    S2-2: FRISCHE vor Preis - dieselbe Ordnung wie `_angebot_rang` in den
    Karten, sonst verdraengt ein altes Billig-Angebot die frische Karte
    desselben Anbieters als Beleg."""
    beste: dict[str, dict] = {}
    for k in modell.get("karten") or []:
        a = k["anbieter"]
        if a == "Vodafone" or a not in ALLE_WETTBEWERBER:
            continue
        if not (
            k.get("belastbar")
            and not k.get("naeherung")
            and k.get("gesamt") is not None
        ):
            continue
        rang = (not k.get("frisch", True), k["gesamt"])
        if a not in beste or rang < (
            not beste[a].get("frisch", True),
            beste[a]["gesamt"],
        ):
            beste[a] = k
    return beste


def _vf_zaehlt(je: dict) -> bool:
    return "Vodafone" in je and je["Vodafone"][0].get("vergleichbar", True)


def _paar_zeilen(anbieter: str, alle_je: dict, band_rang: dict) -> list[dict]:
    """Jede Karte des Wettbewerbers in einem Band, in dem Vodafone eine Karte
    führt: gegen Vodafones Karte derselben Ratenlaufzeit, sonst als benannte
    Zeile gegen die Vodafone-Karte des Bandes (24 Raten zuerst) - verglichen
    wird nie über zwei Laufzeiten, verschwiegen wird keine Karte."""
    vf_im_band: dict = {}
    for lz in sorted(LAUFZEITEN, key=lambda lz: lz != LAUFZEIT_STANDARD):
        for b, je in alle_je[lz].items():
            if _vf_zaehlt(je):
                vf_im_band.setdefault(b, je["Vodafone"][0])
    zeilen = []
    for _rang, b, lz in sorted(
        (band_rang.get(b, len(band_rang)), b, lz)
        for lz, je_band in alle_je.items()
        for b, je in je_band.items()
        if anbieter in je and b in vf_im_band
    ):
        je = alle_je[lz][b]
        vf = je["Vodafone"][0] if _vf_zaehlt(je) else vf_im_band[b]
        zeilen += [_paar_zeile(anbieter, b, k, vf) for k in je[anbieter]]
    return zeilen


def netzbetreiber_gruppen(
    modelle: list, band_je_tarif: dict, band_rang: dict | None = None
) -> list[dict]:
    """Je Modell eine Zeilengruppe (Aufgabe 3): Vodafone-Basis + Zeilen der
    drei Wettbewerber, IMMER alle drei genannt (kein_buendel statt
    Weglassen), dazu Zweitmarken MIT Karte ohne Platzhalter (B3) - sortiert
    aufsteigend nach %-Abweichung.

    Die Paare kommen aus `_paar_zeilen` (Band und Ratenlaufzeit, RAD-1b),
    gruppiert werden nur Karten, die zaehlen (NOTBREMSE im Modulkopf). Ein
    erneuertes Geraet steht als nicht vergleichbare Zeile mit Grund daneben
    (B1). Ohne gemeinsames Band: Band-Mismatch mit der GUENSTIGSTEN Karte. Ohne
    Karte nennt `modell["erfassung"]` den gestörten Klick-Lauf (`klick_erfassung`)."""
    band_rang = band_rang or {}
    gruppen = []
    for modell in modelle:
        basis = _vodafone_basis(modell, band_je_tarif)
        karten = modell.get("karten") or []
        zaehlend = {**modell, "karten": list(filter(notbremse.zaehlt, karten))}
        alle_je = {
            lz: geraete_tco_band.alle_karten_je_band(zaehlend, band_je_tarif, lz)
            for lz in LAUFZEITEN
        }
        uebrig = _guenstigste_echte_karte_je_anbieter(zaehlend)
        ungefiltert = _guenstigste_echte_karte_je_anbieter(modell)
        hat_karte = {k.get("anbieter") for k in karten}
        erfasst = {a: {"leer_grund": g} for a, g in modell.get("erfassung", {}).items()}
        if basis is None:
            zeilen = [
                {
                    "anbieter": a,
                    "status": STATUS_KEIN_BUENDEL,
                    "prozent": None,
                    "gesamt": (uebrig.get(a) or {}).get("gesamt"),
                    "tarif": (uebrig.get(a) or {}).get("tarif", ""),
                    "band": None,
                    "band_label": "",
                    "grund": _notbremse_satz(uebrig.get(a) or ungefiltert.get(a))
                    or (erfasst.get(a) or {}).get("leer_grund", ""),
                    **_beleg("", ""),
                }
                for a in ALLE_WETTBEWERBER
                if a in NETZ_WETTBEWERBER or a in hat_karte
            ]
            gruppen.append(
                {
                    "id": modell["id"],
                    "titel": modell["titel"],
                    "hersteller": modell["hersteller"],
                    "speicher": modell["speicher"],
                    "vodafone": None,
                    "vodafone_grund": (
                        "Keine Vodafone-Kosten über 24 Monate "
                        "für dieses Gerät "
                        "erhoben – kein Bündel und kein eigener "
                        "Barpreis."
                    ),
                    "zeilen": zeilen,
                    "rang": float("inf"),
                }
            )
            continue
        zeilen = []
        for a in ALLE_WETTBEWERBER:
            if a not in NETZ_WETTBEWERBER and a not in hat_karte:
                continue
            if paare := _paar_zeilen(a, alle_je, band_rang):
                zeilen += paare
                continue
            karte = uebrig.get(a) or ungefiltert.get(a) or erfasst.get(a)
            zeilen.append(_zeile_fuer_anbieter(a, karte, basis, band_je_tarif))
        zeilen.sort(
            key=lambda z: z["prozent"] if z["prozent"] is not None else float("inf")
        )
        rang = min(
            (z["prozent"] for z in zeilen if z["prozent"] is not None),
            default=float("inf"),
        )
        gruppen.append(
            {
                "id": modell["id"],
                "titel": modell["titel"],
                "hersteller": modell["hersteller"],
                "speicher": modell["speicher"],
                "vodafone": basis,
                "vodafone_grund": "",
                "zeilen": zeilen,
                "rang": rang,
            }
        )
    gruppen.sort(key=lambda g: g["rang"])
    return gruppen


_LUECKE_WORT = {
    STATUS_BAND_MISMATCH: "kein gemeinsames Band",
    STATUS_KEIN_BUENDEL: "kein Bündel erhoben",
    STATUS_NICHT_VERGLEICHBAR: "nicht vergleichbar",
}


def _dvorzeichen(betrag: float, stellen: int = 2) -> str:
    """Deutsche Schreibweise MIT Vorzeichen und Tausenderpunkt.

    S4 (einheitliche Sprache): die Seite spricht deutsche Zahlen (Alarm-
    tabelle, Buendelzeilen) - bis E3 standen in der Abweichungsspalte der
    Schwesterseite Punktzahlen (Python-Format ungefiltert). Dasselbe
    Vorzeichen wie ueberall: negativ = Wettbewerber guenstiger.
    """
    text = f"{betrag:+,.{stellen}f}"
    return text.replace(",", "#").replace(".", ",").replace("#", ".")


def _richtung(differenz: float) -> str:
    """„günstiger als", „teurer als" oder „gleich teuer wie" für eine Differenz
    Wettbewerber − Vodafone, auf den angezeigten Cent gerundet (sonst
    hiesse -0,004 € „günstiger" neben „+0,00 €")."""
    cent = round(differenz, 2)
    if cent < 0:
        return "günstiger als"
    if cent > 0:
        return "teurer als"
    return "gleich teuer wie"


def modellliste(gruppen: list[dict]) -> dict:
    """EINE Zeile je Modell - die Modell-Liste des Radar-Reiters (S2).

    Antonio: „Ich musste auch irgendwo sehen können, die ganzen Modelle
    irgendwo aufgelistet." Die Gruppen aus `netzbetreiber_gruppen` tragen
    je Modell ALLE Anbieter-Zeilen (Paare, Mismatches, Platzhalter) - fuer
    die Liste wird daraus EINE Hauptzeile je Modell:

      * die STAERKSTE Abweichung (der `rang` der Gruppe - negativste
        Prozentzahl zuerst, die bewusste Leseentscheidung des Modulkopfs),
        getragen von dem Anbieter-Paar, das sie gerechnet hat,
      * oder das Lueckenwort, wenn kein vergleichbares Paar steht,

    und dazu alles, was die Detailzeile braucht (VF-Basis und ALLE Anbieter-Zeilen der
    Gruppe - kein Anbieter wird weggedeckelt, B.2.5). KEINE zweite Rechnung: Prozent und
    Euro-Betraege sind die Werte der Paarzeile, ungekuerzt uebernommen.

    `sichtbar`/`rest` kappen nur die ANSICHT (`MODELLISTE_SICHTBAR`,
    Knopf „alle N anzeigen") - `zeilen` bleibt die vollstaendige Liste.
    """
    zeilen = []
    for g in gruppen:
        paar = next(
            (z for z in g["zeilen"] if z["status"] == STATUS_VERGLEICHBAR), None
        )
        luecke = ""
        sprung_band = ""
        if paar is None:
            if g["vodafone"] is None:
                luecke = "keine Vodafone-Kosten über 24 Monate erhoben"
            else:
                luecke = "kein Vergleich"
                for status in (
                    STATUS_NICHT_VERGLEICHBAR,
                    STATUS_BAND_MISMATCH,
                    STATUS_KEIN_BUENDEL,
                ):
                    if any(z["status"] == status for z in g["zeilen"]):
                        luecke = _LUECKE_WORT[status]
                        break
        else:
            sprung_band = paar.get("band") or ""
        zeilen.append(
            {
                "id": g["id"],
                "titel": g["titel"],
                "hersteller": g["hersteller"],
                "speicher": g["speicher"],
                "speicher_klein": (
                    ""
                    if g["speicher"] and f"{g['speicher']} GB" in (g["titel"] or "")
                    else (f"{g['speicher']} GB" if g["speicher"] else "")
                ),
                "prozent": paar["prozent"] if paar else None,
                "euro": (paar["gesamt"] - paar["vf_gesamt"]) if paar else None,
                "prozent_text": (_dvorzeichen(paar["prozent"], 1) if paar else ""),
                "euro_text": (
                    _dvorzeichen(paar["gesamt"] - paar["vf_gesamt"]) if paar else ""
                ),
                "richtung": (
                    _richtung(paar["gesamt"] - paar["vf_gesamt"]) if paar else ""
                ),
                "anbieter": (paar or {}).get("anbieter", ""),
                "tarif": (paar or {}).get("tarif", ""),
                "band_label": (paar or {}).get("band_label", ""),
                "gesamt": (paar or {}).get("gesamt"),
                "vf_gesamt": (paar or {}).get("vf_gesamt"),
                "quelle_url": (paar or {}).get("quelle_url", ""),
                "abgerufen_am": (paar or {}).get("abgerufen_am", ""),
                "luecke": luecke,
                "sprung_band": sprung_band,
                "vodafone": g["vodafone"],
                "vodafone_grund": g["vodafone_grund"],
                "gruppe_zeilen": g["zeilen"],
            }
        )
    return {
        "zeilen": zeilen,
        "sichtbar": zeilen[:MODELLISTE_SICHTBAR],
        "rest": zeilen[MODELLISTE_SICHTBAR:],
        "gesamt": len(zeilen),
    }


def _x(text: object) -> str:
    """XML-Escaping fuer SVG-Text (Modelle- und Ladennamen kommen aus dem
    Bestand und duerfen & < > enthalten)."""
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _euro0(betrag: float) -> str:
    """Deutsche Schreibweise eines Betrags OHNE Vorzeichen ( fuer die
    <title>-Tooltips der Grafik: beide Preise der Messung daneben)."""
    text = f"{betrag:,.2f}".replace(",", "#").replace(".", ",")
    return text.replace("#", ".") + " €"


def grafik_zeilen(vergleich_ohne_vertrag: dict) -> list[dict]:
    """Eine Grafik-Zeile je vergleichbarer Zeile des Barpreis-Vergleichs."""
    zeilen = []
    for z in (vergleich_ohne_vertrag or {}).get("zeilen", []):
        vf = (z.get("vodafone") or {}).get("preis")
        if vf is None:
            continue
        if z.get("guenstiger"):
            gegen = z["guenstiger"][0]
            delta = z.get("differenz")
        elif z.get("teurer"):
            gegen = z["teurer"][0]
            delta = round(vf - gegen.get("preis"), 2)
        else:
            continue
        if gegen is None or gegen.get("preis") is None or not delta:
            continue
        prozent = z.get("prozent")
        if prozent is None:
            prozent = round(delta / vf * 100.0, 1)
        zeilen.append(
            {
                "device_id": z.get("device_id"),
                "speicher": z.get("speicher"),
                "modell": z.get("modell") or "",
                "hersteller": z.get("hersteller"),
                "delta": float(delta),
                "prozent": float(prozent),
                "laden": gegen.get("laden") or gegen.get("anbieter", ""),
                "vf_preis": vf,
                "gegen_preis": gegen.get("preis"),
            }
        )
    return zeilen


def _balken_pfad(
    x_null: float, y: float, laenge: float, hoehe: float, nach_rechts: bool
) -> str:
    """Ein Balken mit runder AUSSEN-Seite und eckiger Basis an der
    Nulllinie (Markenspezifikation: Datenende gerundet, Basis quadrat) -
    ein `<rect rx>` rundet beide Enden und stellte die Basis als eigener
    Wert dar. Balken unter 8 px Länge bleiben eckig (kein Rundungszimmer
    in einer Nische)."""
    r = min(3.5, laenge / 2, hoehe / 2) if laenge >= 8 else 0
    if nach_rechts:
        xe = x_null + laenge
        if not r:
            return f"M{x_null:.1f} {y:.1f}H{xe:.1f}V{y + hoehe:.1f}H{x_null:.1f}Z"
        return (
            f"M{x_null:.1f} {y:.1f}H{xe - r:.1f}Q{xe:.1f} {y:.1f} "
            f"{xe:.1f} {y + r:.1f}V{y + hoehe - r:.1f}"
            f"Q{xe:.1f} {y + hoehe:.1f} {xe - r:.1f} {y + hoehe:.1f}"
            f"H{x_null:.1f}Z"
        )
    xe = x_null - laenge
    if not r:
        return f"M{x_null:.1f} {y:.1f}H{xe:.1f}V{y + hoehe:.1f}H{x_null:.1f}Z"
    return (
        f"M{x_null:.1f} {y:.1f}H{xe + r:.1f}Q{xe:.1f} {y:.1f} "
        f"{xe:.1f} {y + r:.1f}V{y + hoehe - r:.1f}"
        f"Q{xe:.1f} {y + hoehe:.1f} {xe + r:.1f} {y + hoehe:.1f}"
        f"H{x_null:.1f}Z"
    )


def _grafik_svg(
    zeilen: list[dict], spitze_schluessel: tuple | None, breit: bool
) -> str:
    """Das servergerenderte SVG in zwei Varianten (schirm/mobil) - kein
    Client-Rechnen. Beide stehen im DOM, das Mediaquery zeigt eine
    (derselbe Mechanismus wie die Zeitreihe `svg.gr-zr--breit/schmal`).

    EINE Euro-Skala fuer beide Richtungen (eine Achse, keine zweite
    Rechenvorschrift): der linke Arm ergibt sich aus dem groessten
    Abstand nach links, derselbe Massstab wie rechts.
    """
    zeilen = [{**z, "delta": -z["delta"], "prozent": -z["prozent"]} for z in zeilen]
    n = len(zeilen)
    if breit:
        w, name_breite, wert_raum, neg_raum = 1120, 158, 158, 190
        reihen_hoehe, balken_hoehe, kopf, fuss = 30, 14, 30, 12
    else:
        w, name_breite, wert_raum, neg_raum = 350, 0, 78, 78
        reihen_hoehe, balken_hoehe, kopf, fuss = 40, 12, 26, 8
    h = kopf + n * reihen_hoehe + fuss
    max_abs = max((abs(z["delta"]) for z in zeilen), default=1.0) or 1.0
    neg_arm = max((abs(z["delta"]) for z in zeilen if z["delta"] < 0), default=0.0)
    start = (2 if breit else 10) + neg_raum * (neg_arm > 0)
    verfuegbar = w - 6 - wert_raum - start
    if breit:
        verfuegbar -= name_breite + 10
        start += name_breite + 10
    skala = verfuegbar / max_abs
    x0 = start + neg_arm * skala

    spitze = None
    if spitze_schluessel is not None:
        spitze = next(
            (z for z in zeilen if (z["device_id"], z["speicher"]) == spitze_schluessel),
            None,
        )
    teile: list[str] = []
    teile.append(
        f"<svg class='wr-gr wr-gr--{'breit' if breit else 'schmal'}' "
        f"viewBox='0 0 {w} {h}' role='img' "
        f"aria-label='Abstand zum Vodafone-Preis in Euro, {n} Modelle"
        + (
            f", größter Abstand {_dvorzeichen(spitze['delta'])} Euro "
            f"bei {_x(spitze['modell'])}"
            if spitze
            else ""
        )
        + "'>"
    )
    anker = " text-anchor='middle'" if breit else ""
    teile.append(
        f"<line class='wr-gr-null' x1='{x0:.1f}' y1='{kopf - 8}' "
        f"x2='{x0:.1f}' y2='{h - 4:.1f}'/>"
    )
    teile.append(
        f"<text class='wr-gr-nulltext' x='{x0:.1f}' "
        f"y='{kopf - 13}'{anker}>Vodafone</text>"
    )
    for i, z in enumerate(zeilen):
        ist_spitze = spitze is not None and spitze is z
        klasse = "wr-gr-balken"
        if ist_spitze:
            klasse += " wr-gr-balken--spitze"
        elif z["delta"] < 0:
            klasse += " wr-gr-balken--teuer"
        else:
            klasse += " wr-gr-balken--gut"
        laenge = abs(z["delta"]) * skala
        wert = f"{_dvorzeichen(z['delta'])} €"
        prozent = f"{z['prozent']:+.1f}".replace(".", ",") + " %"
        titel = (
            f"{_x(z['modell'])}: {wert} ({prozent}) gegenüber "
            f"{_x(z['laden'])} – Vodafone {_euro0(z['vf_preis'])}, "
            f"{_x(z['laden'])} {_euro0(z['gegen_preis'])}"
        )
        if breit:
            y = kopf + i * reihen_hoehe + (reihen_hoehe - balken_hoehe) / 2
            ty = y + balken_hoehe / 2 + 4
            speicher = ""
            if z["speicher"]:
                speicher = (
                    f" <tspan class='wr-gr-name-zusatz'>· "
                    f"{_x(z['speicher'])} GB</tspan>"
                )
            teile.append(
                f"<text class='wr-gr-name' x='{name_breite}' "
                f"y='{ty:.1f}' text-anchor='end'>{_x(z['modell'])}"
                f"{speicher}</text>"
            )
            teile.append(
                f"<path class='{klasse}' d='"
                f"{_balken_pfad(x0, y, laenge, balken_hoehe, z['delta'] > 0)}'>"
                f"<title>{titel}</title></path>"
            )
            if z["delta"] > 0:
                teile.append(
                    f"<text class='wr-gr-wert' x='{x0 + laenge + 8:.1f}' "
                    f"y='{ty:.1f}'>{wert}<tspan class='wr-gr-laden'> · "
                    f"{_x(z['laden'])}</tspan></text>"
                )
            else:
                teile.append(
                    f"<text class='wr-gr-wert' x='{x0 - laenge - 8:.1f}' "
                    f"y='{ty:.1f}' text-anchor='end'>{wert}<tspan "
                    f"class='wr-gr-laden'> · {_x(z['laden'])}</tspan></text>"
                )
        else:
            ly = kopf + i * reihen_hoehe
            y = ly + 19
            name = _x(z["modell"])
            if z["speicher"]:
                name = (
                    f"{name} <tspan class='wr-gr-name-zusatz'>· "
                    f"{_x(z['speicher'])} GB</tspan>"
                )
            teile.append(
                f"<text class='wr-gr-name' x='2' y='{ly + 12:.1f}'>{name}</text>"
            )
            teile.append(
                f"<path class='{klasse}' d='"
                f"{_balken_pfad(x0, y, laenge, balken_hoehe, z['delta'] > 0)}'>"
                f"<title>{titel}</title></path>"
            )
            if z["delta"] > 0:
                teile.append(
                    f"<text class='wr-gr-wert' "
                    f"x='{x0 + laenge + 6:.1f}' y='{y + 10:.1f}'>"
                    f"{wert}</text>"
                )
            else:
                teile.append(
                    f"<text class='wr-gr-wert' "
                    f"x='{x0 - laenge - 6:.1f}' y='{y + 10:.1f}' "
                    f"text-anchor='end'>{wert}</text>"
                )
    teile.append("</svg>")
    return "".join(teile)


def grafik(vergleich_ohne_vertrag: dict, n: int = GRAFIK_MAX) -> dict:
    """Die Balkengrafik-Daten fuer die Radar-Tafel: Top N nach ABSOLUTEM
    Euro-Abstand, die Spitze (groesster Abstand zuungunsten Vodafones)
    immer dabei - auch wenn sie es allein nach Platzierung nicht in die
    Top N schaffte, sonst markierte Rot in der Tabelle ein Modell, das im
    Bild fehlt (und die Alarm-Pille haette keinen Balken)."""
    alle = grafik_zeilen(vergleich_ohne_vertrag)
    if not alle:
        return {
            "svg_breit": "",
            "svg_schmal": "",
            "zeilen": [],
            "n": 0,
            "basis": 0,
            "spitze": None,
            "leer_grund": (
                "Noch keine vergleichbaren Barpreise erhoben "
                "– die Grafik entsteht mit dem nächsten Lauf."
            ),
        }
    spitze_kandidat = max(
        (z for z in alle if z["delta"] > 0), key=lambda z: z["delta"], default=None
    )
    gewaehlt = sorted(alle, key=lambda z: -abs(z["delta"]))[:n]
    if spitze_kandidat is not None:
        schluessel = (spitze_kandidat["device_id"], spitze_kandidat["speicher"])
        if not any((z["device_id"], z["speicher"]) == schluessel for z in gewaehlt):
            if gewaehlt:
                gewaehlt[-1] = spitze_kandidat
            else:
                gewaehlt = [spitze_kandidat]
            gewaehlt.sort(key=lambda z: -abs(z["delta"]))
    spitze = None
    if spitze_kandidat is not None:
        spitze = {
            "device_id": spitze_kandidat["device_id"],
            "speicher": spitze_kandidat["speicher"],
            "schluessel": (
                f"{spitze_kandidat['device_id'] or ''}|"
                f"{spitze_kandidat['speicher'] or ''}"
            ),
            "modell": spitze_kandidat["modell"],
            "delta": spitze_kandidat["delta"],
            "delta_text": f"{_dvorzeichen(-spitze_kandidat['delta'])} €",
        }
    schluessel = (spitze["device_id"], spitze["speicher"]) if spitze else None
    return {
        "svg_breit": _grafik_svg(gewaehlt, schluessel, True),
        "svg_schmal": _grafik_svg(gewaehlt, schluessel, False),
        "zeilen": gewaehlt,
        "n": len(gewaehlt),
        "basis": len(alle),
        "spitze": spitze,
        "leer_grund": "",
    }


def haendler_zeilen(vergleich_ohne_vertrag: dict) -> list[dict]:
    """Der Händler-Abschnitt (Aufgabe: eigener, klar beschrifteter Bereich).

    Liest `geraete_vergleich.vergleich(..., preisart=OHNE_VERTRAG)["zeilen"]`
    - keine zweite Preisrechnung, nur ein Filter auf `anbieter_typ ==
    "handel"` und dieselbe %-Formel wie bei den Netzbetreibern, hier gegen
    Vodafones GERÄTEPREIS statt TCO-24.
    """
    zeilen = []
    for z in (vergleich_ohne_vertrag or {}).get("zeilen", []):
        vf = z.get("vodafone")
        if not vf or vf.get("preis") is None:
            continue
        for w in list(z.get("guenstiger") or []) + list(z.get("teurer") or []):
            if (w.get("typ") or "") != "handel":
                continue
            if w.get("preis") is None:
                continue
            prozent = round((w["preis"] - vf["preis"]) / vf["preis"] * 100, 1)
            zeilen.append(
                {
                    "modell": z.get("modell", ""),
                    "hersteller": z.get("hersteller", ""),
                    "speicher": z.get("speicher"),
                    "vodafone_preis": vf["preis"],
                    "vodafone_url": vf.get("url", ""),
                    "vodafone_abgerufen_am": vf.get("abgerufen_am", ""),
                    "anbieter": w.get("laden") or w.get("anbieter", ""),
                    "preis": w["preis"],
                    "url": w.get("url", ""),
                    "abgerufen_am": w.get("abgerufen_am", ""),
                    "prozent": prozent,
                }
            )
    zeilen.sort(key=lambda r: r["prozent"])
    return zeilen


def nicht_erhebbar(quellenlage: dict) -> list[dict]:
    """Händler, die strukturell keine Daten liefern - NAMENTLICH, nie
    stillschweigend weggelassen (Aufgabe 4/Test c). Liest denselben Satz,
    den `geraete-quellen.html` schon zeigt (`methode`/`grund` aus
    config/geraete_quellen.yaml) - keine zweite Einschätzung."""
    out = []
    for z in (quellenlage or {}).get("zeilen", []):
        if (z.get("typ") or "") != "handel":
            continue
        if z.get("zustand") == "liefert":
            continue
        out.append(
            {
                "anbieter": z.get("name", ""),
                "aktiv": bool(z.get("aktiv")),
                "grund": z.get("grund") or "Keine Daten erhoben.",
            }
        )
    out.sort(key=lambda x: x["anbieter"])
    return out


def radar(
    tco: dict,
    vergleich_ohne_vertrag: dict,
    quellenlage: dict,
    alarme: dict | None = None,
    portfolio: dict | None = None,
) -> dict:
    """Alles fuer die Radar-Tafel der EINEN Geräteseite (#tafel-radar).

    `gruppen`/`haendler` bleiben die VOLLSTAENDIGEN Listen (Test c: nichts wird
    entfernt); `gruppen_sichtbar`/`gruppen_rest` und `haendler_sichtbar`/`haendler_rest`
    sind nur die Kappung der ANSICHT - dieselbe Bauform wie `geraete_alarme.zeilen()`
    (`sichtbar`/`rest`).

    `alarme` (seit O2, 11.09.2026) ist die Aufbereitung aus `geraete_view.aufbereiten` -
    die Alarmtabelle steht seither HIER und nicht mehr in der Vergleichsansicht der
    Geraeteseite. Sie wird als GANZES durchgereicht, nicht neu gerechnet: dieselbe
    Tabelle, derselbe Deckel, derselbe Ort - nur die Seite ist eine andere. Dazu
    `ohne_vodafone` aus demselben Vergleich: der Sortiments-Aufklapper "Bei
    Wettbewerbern gelistet" antwortet dieselbe Frage ueber das Sortiment, die der Radar
    ueber den Preis stellt.
    """
    band_je_tarif = tco.get("band_je_tarif") or {}
    gruppen = netzbetreiber_gruppen(
        tco.get("modelle", []), band_je_tarif, _band_rang(tco.get("baender_katalog"))
    )
    haendler = haendler_zeilen(vergleich_ohne_vertrag)
    fehlt = nicht_erhebbar(quellenlage)
    hat_vergleichbare = any(
        z["prozent"] is not None for g in gruppen for z in g["zeilen"]
    )
    ohne = (vergleich_ohne_vertrag or {}).get("ohne_vodafone") or []
    return {
        "gruppen": gruppen,
        "gruppen_sichtbar": gruppen[:SICHTBAR_MAX],
        "gruppen_rest": gruppen[SICHTBAR_MAX:],
        "modelliste": modellliste(gruppen),
        "grafik": grafik(vergleich_ohne_vertrag),
        "haendler": haendler,
        "haendler_sichtbar": haendler[:HAENDLER_SICHTBAR_MAX],
        "haendler_rest": haendler[HAENDLER_SICHTBAR_MAX:],
        "nicht_erhebbar": fehlt,
        "hat_daten": bool(gruppen),
        "hat_vergleichbare_zeilen": hat_vergleichbare or bool(haendler),
        "anbieter_erwartet": list(NETZ_WETTBEWERBER),
        "alarme": alarme if alarme is not None else _alarme_leer(),
        "ohne_vodafone": ohne,
        "ohne_vodafone_gesamt": (vergleich_ohne_vertrag or {}).get(
            "ohne_vodafone_gesamt", len(ohne)
        ),
        "portfolio": portfolio if portfolio is not None else _portfolio_leer(),
        "export": {"datei": "", "zeilen": 0, "bytes": 0},
    }


def _portfolio_leer() -> dict:
    """Der Notzustand der Portfolio-Abschnitte - dieselben Schlüssel wie
    das Dict aus `render_site`, damit die Vorlage nie auf ein fehlendes
    Feld trifft (derselbe Grund wie bei `_alarme_leer`)."""
    return {
        "lifecycle": None,
        "auffaellig": None,
        "lifecycle_sichtbar": 0,
        "nachfolger_sichtbar": 0,
        "fenster_tage": 0,
    }


def _alarme_leer() -> dict:
    """Der Notzustand der Alarmtabelle - `geraete_alarme.leer()`, ohne den
    Import quer durch die Tafeln zu ziehen (derselbe Grund wie bei
    `EIGEN` im Modulkopf: eine Abhaengigkeit zwischen zwei Seiten, die
    sonst nichts miteinander zu tun haben)."""
    from . import geraete_alarme

    return geraete_alarme.leer()


def leer() -> dict:
    return {
        "gruppen": [],
        "gruppen_sichtbar": [],
        "gruppen_rest": [],
        "modelliste": {"zeilen": [], "sichtbar": [], "rest": [], "gesamt": 0},
        "grafik": grafik({}),
        "haendler": [],
        "haendler_sichtbar": [],
        "haendler_rest": [],
        "nicht_erhebbar": [],
        "hat_daten": False,
        "hat_vergleichbare_zeilen": False,
        "anbieter_erwartet": list(NETZ_WETTBEWERBER),
        "alarme": _alarme_leer(),
        "ohne_vodafone": [],
        "ohne_vodafone_gesamt": 0,
        "portfolio": _portfolio_leer(),
        "export": {"datei": "", "zeilen": 0, "bytes": 0},
    }
