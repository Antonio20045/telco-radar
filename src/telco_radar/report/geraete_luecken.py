"""Der Lückensatz eines Paar-Blocks: wer fehlt, warum, und wo er sonst steht.

Aus `geraete_zeitreihe` ausgelagert (Datenkonzept Geräte Schritt 2). Seit Teil B
gehört jeder Block zu einer Ratenlaufzeit; ein Anbieter, der das Gerät nur mit
anderen Raten führt, steht benannt als „nicht erfasst“, und Alternativen in
anderen Bändern stammen aus derselben Laufzeit.
"""

from __future__ import annotations

import re

from ..analyze.klick_erfassung import (
    SATZ_NICHT_IM_ANGEBOT,
    SATZ_SPEICHER,
    SATZ_SPEICHER_ANGEBOT,
)
from ..tco_model import TCO_HORIZONT
from . import geraete_notbremse as notbremse
from .anbieter_farben import farbe_fuer
from .geraete_laufzeit import (
    ALLE,
    LAUFZEIT_STANDARD,
    LAUFZEITEN,
    NICHT_ERFASST,
    ansicht,
    nur_ueber_24,
)
from .geraete_luecken_alternativen import (
    _alt_zeitraum,
    _alternativen,
    _andere_laufzeiten,
    _stufe,
)
from .geraete_rechenweg import ANBIETER_FOLGE, euro
from .geraete_stufen import KEIN_TARIF_KURZ, KEIN_TARIF_SATZ, stufe_ohne_tarif
from .geraete_zeitraum_wort import zeitraum_wort


def _luecken(
    zeilen: list,
    karten: list,
    band: str,
    fremd: list | None = None,
    gesperrt: list | None = None,
    laufzeit: int | None = None,
    stufen: dict | None = None,
) -> list[dict]:
    """Je erwartetem Anbieter ohne Zeile: der Grund, in EINEM Satz zusammen.

    Antonio 9b.7: „Wenn es nichts gibt, dann brauchst du es nicht
    anzuzeigen von den jeweiligen Anbietern" - die Namen stehen im SAMMEL-
    satz, nie als eigene Zeile mit leerem Inhalt.

    Seit A3 gibt es einen VIERten Grund: der Anbieter führt ein Bündel,
    aber nur mit altem Abruf - „kein Bündel in diesem Band" waere gelogen
    (harte Regel 9), der alte Preis darf aber auch nicht als heutiger
    Alternative-Betrag stehen.

    S2-3 (Diff-Prüfung 21.09.2026): gefragt ist DIESES Band - die
    Frische-Prüfung muss die Karten DES BANDES meinen, nicht alle Karten
    des Anbieters. Vorher gewann der Anbieter-Weitblick: Telekom mit
    einem alten Klein-Bündel (720,76 EUR vom 15.09.) und einem frischen
    Groß-Bündel bekam im Band klein „kein-belastbares" - die Seite sagte
    „Kein Bündel in diesem Band: Telekom", obwohl die alte Klein-Karte
    als alt-Zeile direkt darüber steht. Reihenfolge jetzt: gar kein
    Bündel - kein Bündel in DIESEM Band - nur alter Stand in diesem
    Band - frisch im Band, aber nicht belastbar.

    P0-B-h3 (Befund 3): und als letzter Grund `anderer-zeitraum` - das
    Bündel ist da und belastbar, seine Leitzahl trägt nur einen anderen
    Zeitraum als diese Tafel (1&1, 36 Monate). Er steht ZULETZT, weil er
    die Fälle mit vorhandenem Bündel aufteilt: erst seit P0-B-h3 fällt
    eine solche Karte aus `band_zeilen` heraus, und "Kein Bündel in
    diesem Band" wäre für sie falsch. `fremd` ist dabei genau der Eimer,
    den das Tor in `band_zeilen` gefüllt hat - dieselbe Menge, keine
    zweite Ableitung.

    Datenkonzept Geräte Schritt 2: in der Ansicht `laufzeit` zählen nur
    Karten dieser Ratenlaufzeit. Führt ein Anbieter das Gerät nur mit anderen
    Raten, heißt das `nicht-erfasst` - „bietet 12 Monate nicht an“ dürfte nur
    stehen, wenn der Sammler die fehlende Option auf der Seite gesehen hätte.
    Ebenso, wenn das Band selbst nur mit anderen Raten erfasst ist: „Nur in
    anderen Bändern“ wäre dann falsch.

    `stufen` (`geraete_stufen.tarife_je_stufe`) trägt je Anbieter die Zahl seiner
    gemessenen Tarife je Tarifstufe; `stufe_ohne_tarif` ist wahr nur bei null.
    """
    gesehen = {z["anbieter"] for z in zeilen}
    luecken = []
    for anbieter in ANBIETER_FOLGE:
        if anbieter in gesehen:
            continue
        alle = [
            k
            for k in karten
            if k["anbieter"] == anbieter and (k.get("sku_id") or k.get("naeherung"))
        ]
        eigene = [k for k in alle if laufzeit is None or ansicht(k) == laufzeit]
        namen = notbremse.namen(
            [k for k in gesperrt or [] if k["anbieter"] == anbieter]
        )
        if not alle:
            grund = "gar-kein-buendel"
        elif not eigene and any(
            nur_ueber_24(k) and k.get("raten_laufzeit") == laufzeit for k in alle
        ):
            grund = "nur-24"
        elif not eigene:
            grund = "nicht-erfasst"
        elif not any(k.get("band") == band for k in eigene):
            im_band = [k for k in alle if k.get("band") == band]
            grund = "nicht-erfasst" if im_band else "anderes-band"
        elif not any(k.get("frisch", True) for k in eigene if k.get("band") == band):
            grund = "nur-alte"
        elif namen:
            grund = "zaehlt-nicht"
        else:
            grund = "kein-belastbares"
        monate = None
        fremde = sorted(
            k["leitzahl_monate"]
            for k in (fremd or [])
            if k["anbieter"] == anbieter and k.get("leitzahl_monate") is not None
        )
        if fremde:
            grund, monate = "anderer-zeitraum", fremde[0]
        luecken.append(
            {
                "anbieter": anbieter,
                "grund": grund,
                "monate": monate,
                "alternativ": _alternativen(karten, band, anbieter, laufzeit),
                "gesperrt": namen,
                "laufzeit": laufzeit,
                "andere_laufzeiten": _andere_laufzeiten(alle, band, laufzeit),
                "stufe_ohne_tarif": stufe_ohne_tarif(stufen, anbieter, band),
            }
        )
    return luecken


NICHT_IM_ANGEBOT = "Bietet das Gerät nicht an"
NOCH_NICHT_ERFASST = "Noch nicht erfasst"
RATEN_IM_ANGEBOT = {"o2": (24, 36), "congstar": (24, 36), "1&1": (24, 36)}
"""Laufzeitknöpfe der Klick-Karten; andere Raten sind „nicht im Angebot“."""
KEIN_ANGEBOT_GELESEN = "Von {anbieter} ist zu diesem Gerät noch kein Angebot gelesen."
_NICHT_IM_ANGEBOT_MUSTER = re.compile(
    re.escape(SATZ_NICHT_IM_ANGEBOT)
    .replace(re.escape("{anbieter}"), ".+")
    .replace(re.escape("{datum}"), ".+")
)


_SPEICHER_MUSTER, _SPEICHER_ANGEBOT_MUSTER = (
    re.compile(
        re.escape(satz)
        .replace(re.escape("{anbieter}"), ".+")
        .replace(re.escape("{speicher}"), "(?P<speicher>.+)")
        .replace(re.escape("{datum}"), ".+")
    )
    for satz in (SATZ_SPEICHER, SATZ_SPEICHER_ANGEBOT)
)
_KURZ = {
    "anderes-band": "Nur in anderen Bändern",
    "anderer-zeitraum": "Nur über eine andere Laufzeit",
    "zaehlt-nicht": "Nicht im Vergleich",
    "kein-belastbares": "Kein vollständiger Preis",
    "nur-alte": "Kein aktueller Stand",
    "nur-24": "Nur über 24 Monate verglichen",
}


def _kein_buendel_zeile(lu: dict, band_labels: dict, h: int, erfassung: dict) -> dict:
    """Der Anbieter hat zu diesem Gerät gar kein Bündel: Beleg der Klick-Erfassung,
    sonst - hat er in der Stufe keinen Tarif - dieser Befund, sonst „Noch nicht
    erfasst“."""
    satz = erfassung.get(lu["anbieter"])
    if satz and _NICHT_IM_ANGEBOT_MUSTER.fullmatch(satz):
        return _zeile(lu, NICHT_IM_ANGEBOT, satz)
    if satz and (treffer := _SPEICHER_ANGEBOT_MUSTER.fullmatch(satz)):
        return _zeile(lu, f"Nur mit {treffer['speicher']} im Angebot", satz)
    if satz and (treffer := _SPEICHER_MUSTER.fullmatch(satz)):
        kurz = f"{NOCH_NICHT_ERFASST} (gelesen: {treffer['speicher']})"
        return _zeile(lu, kurz, satz)
    if lu.get("stufe_ohne_tarif"):
        return _ohne_tarif_zeile(lu, band_labels, h)
    satz = satz or KEIN_ANGEBOT_GELESEN.format(anbieter=lu["anbieter"])
    return _zeile(lu, NOCH_NICHT_ERFASST, satz)


def _fehlzeile(lu: dict, band_labels: dict, h: int, erfassung: dict) -> dict:
    """Die Zeile EINES fehlenden Anbieters: kurzer Zustand und ganzer Satz.

    „Bietet das Gerät nicht an“ nur mit dem Beleg der Klick-Erfassung (Übersicht
    ganz gelesen, `klick_erfassung.SATZ_NICHT_IM_ANGEBOT`); ohne Bündel und ohne
    diesen Beleg heißt der Anbieter „Noch nicht erfasst“ (Clean Code 6) - außer er
    hat in der Tarifstufe keinen gemessenen Tarif (`geraete_stufen`, fail-closed)."""
    anbieter, grund = lu["anbieter"], lu["grund"]
    ohne_tarif = bool(lu.get("stufe_ohne_tarif"))
    if grund == "gar-kein-buendel":
        return _kein_buendel_zeile(lu, band_labels, h, erfassung)
    if grund == "nicht-erfasst":
        angebot = RATEN_IM_ANGEBOT.get(anbieter)
        if angebot is not None and lu.get("laufzeit") not in angebot:
            kurz = f"Mit {lu.get('laufzeit')} Raten nicht im Angebot"
            return _zeile(lu, kurz, kurz + ".")
        if ohne_tarif:
            return _ohne_tarif_zeile(lu, band_labels, h)
        kurz = f"Mit {lu.get('laufzeit')} Raten {NICHT_ERFASST}"
        if lu.get("andere_laufzeiten"):
            raten = " und ".join(str(a) for a in lu["andere_laufzeiten"])
            kurz += f" ({raten} Raten erfasst)"
        return _zeile(lu, kurz, kurz + ".")
    if ohne_tarif and grund in ("anderes-band", "nur-24"):
        return _ohne_tarif_zeile(lu, band_labels, h)
    kurz = _KURZ.get(grund, _KURZ["anderes-band"])
    if grund == "anderer-zeitraum" and lu.get("monate") is not None:
        kurz = f"Nur über {zeitraum_wort([lu['monate']])}"
    if grund == "zaehlt-nicht" and lu.get("gesperrt"):
        satz = f"{kurz}: {', '.join(lu['gesperrt'])}."
    else:
        satz = f"{kurz}."
    if lu.get("alternativ") and grund != "anderer-zeitraum":
        alt = " · ".join(
            f"{_stufe(band_labels, a['band'])} {euro(a['tco'])}"
            f"{_alt_zeitraum(a.get('monate'), h)}"
            for a in lu["alternativ"]
        )
        kurz += f": {alt}"
        satz = f"{kurz}."
    return _zeile(lu, kurz, satz)


def _ohne_tarif_zeile(lu: dict, band_labels: dict, h: int) -> dict:
    """Der Anbieter hat in dieser Datenstufe keinen Tarif (`geraete_stufen`),
    anders als „Noch nicht erfasst“ ist das keine Messlücke. Preise desselben
    Geräts in anderen Stufen bleiben als Hinweis stehen."""
    kurz = KEIN_TARIF_KURZ
    satz = KEIN_TARIF_SATZ.format(anbieter=lu["anbieter"])
    if lu.get("alternativ"):
        alt = " · ".join(
            f"{_stufe(band_labels, a['band'])} {euro(a['tco'])}"
            f"{_alt_zeitraum(a.get('monate'), h)}"
            for a in lu["alternativ"]
        )
        kurz += f" · in anderen Datenstufen: {alt}"
        satz += f". In anderen Datenstufen: {alt}"
    return _zeile(lu, kurz, satz + ".") | {"grund": "stufe-ohne-tarif"}


def _zeile(lu: dict, kurz: str, satz: str) -> dict:
    return {
        "anbieter": lu["anbieter"],
        "grund": lu["grund"],
        "kurz": kurz,
        "satz": satz,
    }


def fehlzeilen(
    luecken: list,
    band_labels: dict,
    h: int = TCO_HORIZONT,
    erfassung: dict | None = None,
    belegt: dict | None = None,
) -> list[dict]:
    """Je fehlendem Anbieter eines Blocks seine Zeile, in `ANBIETER_FOLGE`.

    Antonio 10.10.2026: „dass die trotzdem in der Liste stehen, aber steht nicht
    vorhanden bei Telekom“. Jeder große Anbieter steht in der Bündelliste, auch
    ohne Preis; der Grund ist derselbe wie im früheren Lückensatz. Eine belegte
    Lücke aus der Config (`geraete_luecken_beleg.fuer_modell`) nennt ihren Grund
    samt Prüfdatum und geht jedem Erfassungsgrund vor."""
    belegt = belegt or {}
    return [
        _zeile(lu, belegt[lu["anbieter"]]["kurz"], belegt[lu["anbieter"]]["satz"])
        | {"grund": "belegt", "detail": belegt[lu["anbieter"]].get("detail", "")}
        if lu["anbieter"] in belegt
        else _fehlzeile(lu, band_labels, h, erfassung or {})
        for lu in luecken
    ]


def tafelzeilen(paare: list) -> dict[str, list[dict]]:
    """Je Modell die Zeilen fehlender Anbieter für die Bündelliste der Tafel.

    Jede Zeile trägt Band und Ansicht (`laufzeit`, wie `data-lz`); unter „alle“
    steht ein Anbieter nur, wenn er im Band unter keiner Ratenlaufzeit eine Zeile
    hat. Sein Grund kommt dann aus der Standardansicht, eine Laufzeitlücke
    („mit 12 Raten nicht erfasst“) tritt hinter einen echten Grund zurück, und
    Alternativbeträge fallen weg, weil sie je Laufzeit gelten."""
    zeilen: dict[str, list[dict]] = {}
    je_band: dict[tuple, dict[int, dict]] = {}
    for paar in paare:
        for f in paar.get("fehlen") or []:
            zeilen.setdefault(paar["modell"], []).append(
                {**f, "band": paar["band"], "laufzeit": str(paar["laufzeit"])}
            )
            schluessel = (paar["modell"], paar["band"], f["anbieter"])
            je_band.setdefault(schluessel, {})[paar["laufzeit"]] = f
    folge = sorted(LAUFZEITEN, key=lambda lz: lz != LAUFZEIT_STANDARD)
    for (modell, band, _), nach_lz in je_band.items():
        if set(nach_lz) != set(LAUFZEITEN):
            continue
        f = next(
            (nach_lz[lz] for lz in folge if nach_lz[lz]["grund"] != "nicht-erfasst"),
            nach_lz[LAUFZEIT_STANDARD],
        )
        if f["grund"] == "anderes-band":
            f = {
                **f,
                "kurz": _KURZ["anderes-band"],
                "satz": _KURZ["anderes-band"] + ".",
            }
        elif f["grund"] == "stufe-ohne-tarif":
            f = {
                **f,
                "kurz": KEIN_TARIF_KURZ,
                "satz": KEIN_TARIF_SATZ.format(anbieter=f["anbieter"]) + ".",
            }
        zeilen[modell].append({**f, "band": band, "laufzeit": ALLE})
    for liste in zeilen.values():
        for z in liste:
            z["anb_farbe"] = farbe_fuer(z["anbieter"])
    return zeilen


def ohne_tafelzeile(fehlen: list[dict], zeilen: list[dict]) -> list[dict]:
    """Die Zeilen fehlender Anbieter ohne die, deren Anbieter in derselben Ansicht
    schon eine Bündelzeile hat (alt, ohne belastbare Zahl, nicht im Vergleich):
    die steht selbst da und nennt ihren Zustand. Sichtbar ist eine Bündelzeile
    nach derselben Regel wie in app.js (`stelleZeilen`). Eine belegte Lücke
    („nicht im Sortiment“) betrifft das Neugerät, eine Aufarbeitung ersetzt sie
    nicht, und ein von der Lücke überholter Preis (`nicht_im_sortiment`, nur noch
    „veraltet 17“ ohne Grund und Prüfdatum) auch nicht."""

    def sichtbar(z: dict, band: str, lz: str) -> bool:
        return z.get("band") in (None, band) and (
            lz == ALLE or z.get("laufzeit_sichtbar") in (None, "", lz)
        )

    return [
        f
        for f in fehlen
        if not any(
            z.get("anbieter") == f["anbieter"]
            and sichtbar(z, f["band"], f["laufzeit"])
            and (
                f.get("grund") != "belegt"
                or (
                    z.get("zustand") in (None, "", "neu")
                    and not z.get("nicht_im_sortiment")
                )
            )
            for z in zeilen
        )
    ]


def fehlen_im_paar(
    modell: dict, satz: dict, band: str, laufzeit: int, band_labels: dict, h: int
) -> list[dict]:
    """Die Fehlzeilen eines Paares (Modell, Band, Ratenlaufzeit) aus `_luecken`."""
    luecken = _luecken(
        satz["zeilen"],
        modell.get("karten") or [],
        band,
        fremd=satz.get("fremd") or [],
        gesperrt=satz.get("gesperrt"),
        laufzeit=laufzeit,
        stufen=modell.get("stufen"),
    )
    return fehlzeilen(
        luecken,
        band_labels,
        h,
        modell.get("erfassung"),
        modell.get("belegte_luecken"),
    )


def haenge_an(modelle: list, paare: list) -> None:
    """Gibt jedem Modell seine Fehlzeilen (`fehlzeilen`) für die Bündelliste."""
    je_modell = tafelzeilen(paare)
    for modell in modelle:
        modell["fehlzeilen"] = ohne_tafelzeile(
            je_modell.get(modell["id"], []), modell.get("zeilen_band") or []
        )
