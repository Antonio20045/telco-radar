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
Gerechnet wird ausschliesslich in `tco_model` (`tco_24()`), gelesen ueber
die fertigen Karten aus `geraete_tco_karten.modelle()` - genau wie
`geraete_tco_band.py` es fuer den Graphen tut. Diese Datei rechnet nur die
EINE zusaetzliche Division (die Abweichung selbst) und vergleicht dafuer
zwei bereits fertige TCO-24-Betraege.

BASIS JE GERAET, BAND ALS SCHRANKE (§2b/§7)
--------------------------------------------
Die Basis ist `modell["referenz"]` - dieselbe EINE Vodafone-Referenz, die
auch die TCO-Hauptansicht und ihr Delta-Banner benutzen (echtes Buendel
schlaegt die gerechnete Naeherung, siehe `geraete_tco_karten._referenzkarte`).
Es gibt also GENAU EINE Vodafone-Basis je Geraet, kein Band-Sammelsurium.

Ein Wettbewerber wird dagegen NUR verglichen, wenn es ein Tarifband gibt,
in dem BEIDE das Geraet fuehren (GRAPH-1-Bandlogik,
`geraete_tco_band.tarif_baender` + `karten_je_band`). Die Abweichung rechnet
dann gegen VODAFONES KARTE IN DIESEM BAND - nicht blind gegen die Referenz:
die Referenz ist Vodafones GUENSTIGSTES Buendel (am echten Bestand 59 von
83 Geraeten im Band Klein), und o2 fuehrt dieselben Geraete dort regelmaessig
nicht. Gegen sie gerechnet waere fast jede Zeile ein Mismatch, OBWOHL echte
Paare existieren (iPhone 15: VF-Basis Klein 1.235,80, aber VF selbst Mittel
1.949,80 gegen o2 Mittel 808,75). Seit RAD-1b (08.09.2026, abends) steht
JEDE echte Karte des Wettbewerbers in JEDEM gemeinsamen Band als eigenes
Paar da - bis dahin zeigte die Seite je Wettbewerber genau EINE Zeile (die
guenstigste Karte eines bevorzugten Bandes), und von den 51 Paaren des
Bestands fehlten 21, alleine 18 davon Telekom XS/S/M im Band Klein.
Liegt der Wettbewerber in keinem gemeinsamen Band oder laesst sich keins
von beiden bestimmen (kein Datenvolumen erhoben, oder unbegrenzt), heisst die
Zeile ehrlich "Band-Mismatch" statt eine Zahl zu erfinden -
AUFTRAG_GERAETESEITE.md §2b: "bei Band-Mismatch ehrlich benennen, nicht
mischen".

WETTBEWERBERKREIS
------------------
Netzbetreiber: Telekom, 1&1, o2 - dieselben drei, die
`geraete_tco_karten.ANBIETER_REIHENFOLGE` neben Vodafone ohnehin auf JEDER
Karte fuehrt (B.2.5: "ein Anbieter, der weggelassen wird, sieht aus wie
einen, den es nicht gibt"). Sie stehen je Modell IMMER da, auch ohne
Bündel (ehrliches kein_buendel statt Weglassen).

Zweitmarken (B3, 08.09.2026): congstar - mit Karte, wo er eine hat, und
OHNE Platzhalter, wo er keine hat. Bis B-3 blieb congstar draussen, weil
er keine Bündel lieferte und eine leere Zeile je Modell nur Lücken
waere ("eine leere Zeile fuer jede denkbare Zweitmarke waere eine Wand
aus Luecken"); seit der Bündelerhebung auf seinen Tarifseiten liefert er
72 Sätze zu 4 Geräten. Wo congstar dasselbe Gerät im selben Band führt
wie Vodafone, entsteht das Vergleichspaar automatisch; wo nicht, entsteht
NICHTS - congstar ist kein Vollsortimenter, und 55 kein_buendel-Zeilen
waere genau die Wand, gegen die die Regel gebaut wurde. Der Unterschied
zu den Netzbetreibern ist also nicht die Marke, sondern der Anspruch:
die drei führen nahezu alle Geräte, congstar führt vier.

Haendler (Gerätepreis, eigener Abschnitt): Saturn, mobilcom-debitel, Amazon
- ausdruecklich im Auftrag genannt. Sie vergleichen GERAETEPREIS gegen
GERAETEPREIS (kein Tarif, keine TCO) und benutzen dieselbe %-Formel gegen
Vodafones Gerätepreis. Datenquelle ist die bestehende
`geraete_vergleich.vergleich()` - keine zweite Preisrechnung, nur ein
zweiter Filter (anbieter_typ == "handel").

DIE SORTIERRICHTUNG, AUSGESCHRIEBEN (Widerspruch im Auftrag aufgeloest)
------------------------------------------------------------------------
BRIEF_RAD1.md nennt in der Einleitung "positiv = Wettbewerber teurer,
negativ = günstiger" UND in den Fachlichen Regeln fuer dieselbe Formel den
Klammerzusatz "(d. h. Wettbewerber am teuersten relativ)" fuer die
Sortierung "zuungunsten Vodafones" - das widerspricht sich: bei fester
Vorzeichendefinition ist "Wettbewerber am teuersten" der POSITIVE, fuer
Vodafone GUENSTIGE Fall, nicht der "zuungunsten"-Fall. Die Normen-Quelle
(AUFTRAG_GERAETESEITE.md §2b) loest den Widerspruch mit ihrem woertlichen
Beispiel auf: "hier ist Vodafone 10 % teurer als der Wettbewerber" ist DER
Fall, fuer den die Seite geoeffnet wird, und das ist rechnerisch der
NEGATIVE Wert (Wettbewerber guenstiger). Sortiert wird deshalb aufsteigend
(negativste/"zuungunsten Vodafones"-Werte zuerst) - siehe
`outputs/rad1-2026-09-08.md` fuer die ausgeschriebene Begruendung.
"""
from __future__ import annotations

from typing import Optional

from . import geraete_tco_band, geraete_tco_karten

# Die drei Netzbetreiber-Wettbewerber - dieselbe Menge, die
# `geraete_tco_karten.modelle()` ohnehin immer (mit oder ohne Zahl) neben
# Vodafone fuehrt.
NETZ_WETTBEWERBER = tuple(a for a in geraete_tco_karten.ANBIETER_REIHENFOLGE
                          if a != "Vodafone")

# Zweitmarken mit Bündelerhebung (B3, siehe Modulkopf "WETTBEWERBERKREIS"):
# Zeile NUR, wo sie eine Karte haben - kein Platzhalter, wo sie keine haben.
ZWEITMARKEN_MIT_BUENDEL = ("congstar",)

# Der Kreis, der Paare bilden KANN (Platzhalter macht allein der
# Netzbetreiber-Kreis, siehe netzbetreiber_gruppen).
ALLE_WETTBEWERBER = NETZ_WETTBEWERBER + ZWEITMARKEN_MIT_BUENDEL

STATUS_VERGLEICHBAR = "vergleichbar"
STATUS_BAND_MISMATCH = "band_mismatch"
STATUS_KEIN_BUENDEL = "kein_buendel"
STATUS_NICHT_VERGLEICHBAR = "nicht_vergleichbar"   # z. B. refurbished

# Wie viele Geraete-Gruppen ohne Aufklappen sichtbar sind. NICHTS wird
# geloescht - der Rest steht im DOM hinter einem <details> (Test c: nicht
# erhebbare/unvergleichbare Zeilen duerfen nie verschwinden, auch nicht
# hinter einer Kappung).
SICHTBAR_MAX = 15
HAENDLER_SICHTBAR_MAX = 20

_BAND_LABEL = {k: l for k, l, _ in geraete_tco_band.BAENDER}
# Einfuegereihenfolge der Baender in einer Gruppe: die Ordnung aus
# `BAENDER` (Klein, Mittel, Gross) - alphabetisch waere "gross, klein,
# mittel" und stuende quer zum Rest des Moduls. Wirkt nur bei
# prozent-Gleichstand (die Endsortierung der Zeilen rechnet nach Prozent).
_BAND_RANG = {k: i for i, (k, _, _) in enumerate(geraete_tco_band.BAENDER)}


def _band_label(band: Optional[str]) -> str:
    if not band:
        return "nicht bestimmbar"
    return _BAND_LABEL.get(band, band)


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
        "tarif": ref.get("tarif", ""),
        "naeherung": not bool(ref.get("aus_buendel")),
        "band": band,
        "band_label": _band_label(band),
        "quelle_url": ref.get("geraet_quelle_url", "") or ref.get("tarif_quelle_url", ""),
        "abgerufen_am": (ref.get("geraet_abgerufen_am", "")
                         or ref.get("tarif_abgerufen_am", "")),
        "tarif_quelle_url": ref.get("tarif_quelle_url", ""),
        "tarif_abgerufen_am": ref.get("tarif_abgerufen_am", ""),
    }


def _zeile_fuer_anbieter(anbieter: str, karte: Optional[dict],
                         basis: dict, band_je_tarif: dict) -> dict:
    """Eine Zeile des Wettbewerbers gegen die Vodafone-Basis dieses Geraets."""
    grund = "" if karte is None else (karte.get("leer_grund") or "")
    if karte is None or not karte.get("belastbar") or karte.get("gesamt") is None:
        return {"anbieter": anbieter, "status": STATUS_KEIN_BUENDEL,
                "prozent": None, "gesamt": None, "tarif": "", "band": None,
                "band_label": "", "grund": grund or
                f"Für dieses Modell ist bei {anbieter} kein Bündel erhoben.",
                **_beleg("", "")}
    if not karte.get("vergleichbar", True):
        return {"anbieter": anbieter, "status": STATUS_NICHT_VERGLEICHBAR,
                "prozent": None, "gesamt": karte["gesamt"], "tarif": karte.get("tarif", ""),
                "band": None, "band_label": "",
                "grund": (f"{anbieter} führt für dieses Gerät nur ein "
                          f"{karte.get('zustand_etikett') or 'nicht neues'} "
                          "Gerät – kein Vergleich gegen ein Neugerät."),
                **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", ""))}

    band = band_je_tarif.get(karte.get("tarif_id") or "")
    if basis["band"] is None or band is None or band != basis["band"]:
        vf_band = basis["band_label"]
        wb_band = _band_label(band)
        grund = (f"Kein Tarifband, in dem beide dieses Gerät führen "
                f"(Vodafone: {vf_band}, {anbieter}: {wb_band}) – "
                "nicht vergleichbar (Tarifband-Mismatch).")
        return {"anbieter": anbieter, "status": STATUS_BAND_MISMATCH,
                "prozent": None, "gesamt": karte["gesamt"],
                "tarif": karte.get("tarif", ""), "band": band,
                "band_label": wb_band, "grund": grund,
                **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", ""))}
    prozent = round((karte["gesamt"] - basis["gesamt"]) / basis["gesamt"] * 100, 1)
    return {"anbieter": anbieter, "status": STATUS_VERGLEICHBAR,
            "prozent": prozent, "gesamt": karte["gesamt"],
            "vf_gesamt": basis["gesamt"],
            "tarif": karte.get("tarif", ""), "band": band,
            "band_label": _band_label(band), "grund": "",
            **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", ""))}


def _paar_zeile(anbieter: str, band: str, wb_karte: dict,
                vf_karte: dict) -> dict:
    """Vergleichbare Zeile: beide Karten liegen im SELBEN Band, und die
    Abweichung rechnet gegen VODAFONES KARTE IN DIESEM BAND - nicht gegen
    die Referenz des Geraets. Der Grund: Vodafones Referenz ist sein
    GUENSTIGSTES Buendel und liegt deshalb bei 59 von 83 Modellen im Band
    Klein, waehrend kein Wettbewerber dort fuehrt - eine Abweichung gegen
    sie waere genau der Apfel-Birnen-Vergleich, den die Bandlogik
    verbietet (iPhone 15: o2 nur Mittel 808,75, VF-Basis Klein 1.235,80,
    VF selbst Mittel 1.949,80). GRAPH-1 vergleicht INNERHALB eines Bandes;
    diese Zeile tut dasselbe und nennt die VF-Gegenkarte im Beleg."""
    if not wb_karte.get("vergleichbar", True):
        return {"anbieter": anbieter, "status": STATUS_NICHT_VERGLEICHBAR,
                "prozent": None, "gesamt": wb_karte["gesamt"],
                "vf_gesamt": vf_karte["gesamt"],
                "tarif": wb_karte.get("tarif", ""), "band": band,
                "band_label": _band_label(band),
                "grund": (f"{anbieter} führt für dieses Gerät nur ein "
                          f"{wb_karte.get('zustand_etikett') or 'nicht neues'} "
                          "Gerät – kein Vergleich gegen ein Neugerät."),
                **_beleg(wb_karte.get("quelle_url", ""),
                         wb_karte.get("abgerufen_am", ""))}
    prozent = round((wb_karte["gesamt"] - vf_karte["gesamt"])
                    / vf_karte["gesamt"] * 100, 1)
    return {"anbieter": anbieter, "status": STATUS_VERGLEICHBAR,
            "prozent": prozent, "gesamt": wb_karte["gesamt"],
            "vf_gesamt": vf_karte["gesamt"],
            "tarif": wb_karte.get("tarif", ""), "band": band,
            "band_label": _band_label(band), "grund": "",
            **_beleg(wb_karte.get("quelle_url", ""),
                     wb_karte.get("abgerufen_am", ""))}


def _guenstigste_echte_karte_je_anbieter(modell: dict) -> dict[str, dict]:
    """Je Wettbewerber seine GUENSTIGSTE echte Karte (Band egal) - die
    Belegzeile fuer einen Band-Mismatch. Dieselbe Auswahlregel wie
    `geraete_tco_band.karten_je_band`, nur ohne die Bandtrennung."""
    beste: dict[str, dict] = {}
    for k in (modell.get("karten") or []):
        a = k["anbieter"]
        if a == "Vodafone" or a not in ALLE_WETTBEWERBER:
            continue
        if not (k.get("belastbar") and not k.get("naeherung")
                and k.get("gesamt") is not None):
            continue
        if a not in beste or k["gesamt"] < beste[a]["gesamt"]:
            beste[a] = k
    return beste


def netzbetreiber_gruppen(modelle: list, band_je_tarif: dict) -> list[dict]:
    """Je Modell eine Zeilengruppe (Aufgabe 3): Vodafone-Basis + Zeilen der
    drei Wettbewerber, IMMER alle drei genannt (kein_buendel statt
    Weglassen), dazu Zweitmarken MIT Karte ohne Platzhalter (B3) - sortiert
    aufsteigend nach %-Abweichung.

    Die Karten des Wettbewerbers und seine VODAFONE-Gegenkarte kommen aus
    der GRAPH-1-Bandlogik (`geraete_tco_band.alle_karten_je_band` /
    `karten_je_band`): verglichen wird im Band, in dem BEIDE das Geraet
    fuehren. Seit RAD-1b steht JEDE echte Karte des Wettbewerbers in
    JEDEM gemeinsamen Band als eigenes Paar da - nicht nur die guenstigste
    Karte eines bevorzugten Bandes (am echten Bestand gemessen, Stand
    08.09.2026: 51 Paare im Bestand, 30 gezeichnet; Telekom fuehrt je
    Geraet XS/S/M, alle drei im Band Klein - die Seite zeigte nur XS).
    Ein erneuertes Geraet im gemeinsamen Band steht als nicht
    vergleichbare Zeile mit Grund daneben (B1-Zustandsregel), es verdraengt
    die vergleichbare Karte nicht mehr. Gibt es kein gemeinsames Band:
    ehrlicher Band-Mismatch mit seiner GUENSTIGSTEN Karte als Beleg."""
    gruppen = []
    for modell in modelle:
        basis = _vodafone_basis(modell, band_je_tarif)
        alle_je_band = geraete_tco_band.alle_karten_je_band(modell,
                                                            band_je_tarif)
        je_band = geraete_tco_band.karten_je_band(modell, band_je_tarif)
        uebrig = _guenstigste_echte_karte_je_anbieter(modell)
        hat_karte = {k.get("anbieter") for k in (modell.get("karten") or [])}
        if basis is None:
            zeilen = [{"anbieter": a, "status": STATUS_KEIN_BUENDEL,
                      "prozent": None,
                      "gesamt": (uebrig.get(a) or {}).get("gesamt"),
                      "tarif": (uebrig.get(a) or {}).get("tarif", ""),
                      "band": None, "band_label": "",
                      "grund": "", **_beleg("", "")}
                     # Zweitmarken auch hier nur MIT Karte (B3, kein
                     # Platzhalter - siehe der Kommentar unten).
                     for a in ALLE_WETTBEWERBER
                     if a in NETZ_WETTBEWERBER or a in hat_karte]
            gruppen.append({
                "id": modell["id"], "titel": modell["titel"],
                "hersteller": modell["hersteller"], "speicher": modell["speicher"],
                "vodafone": None,
                "vodafone_grund": ("Kein Vodafone-TCO-24 für dieses Gerät "
                                  "erhoben – kein Bündel und kein eigener "
                                  "Barpreis."),
                "zeilen": zeilen, "rang": float("inf"),
            })
            continue
        zeilen = []
        for a in ALLE_WETTBEWERBER:
            # ZWEITMARKEN OHNE PLATZHALTER (B3): congstar ist kein
            # Vollsortimenter - führt er das Gerät nicht im Bündel, bleibt
            # die Zeile ganz aus (kein kein_buendel-Platzhalter, siehe
            # Modulkopf). Die Netzbetreiber stehen IMMER da.
            if a not in NETZ_WETTBEWERBER and a not in hat_karte:
                continue
            # ALLE gemeinsamen Baender, ALLE Karten: ein Anbieter, der das
            # Geraet in ZWEI Tarifen desselben Bandes fuehrt, hat auch
            # ZWEI Vergleichspaare (RAD-1b; am Bestand gemessen: Telekom
            # XS/S/M alle im Band Klein - vorher stand nur die guenstigste
            # der drei, 18 von 51 Paaren fehlten auf der Seite). Die
            # VF-Gegenkarte bleibt die GUENSTIGSTE VF-Karte des Bandes -
            # die fuer Vodafone konservative Wahl (eine Behauptung "VF ist
            # X % teurer" muss auch gegen VF's billigstes Angebot im Band
            # halten).
            gemeinsam = {b: je for b, je in alle_je_band.items()
                         if a in je and "Vodafone" in je
                         and je_band[b]["Vodafone"].get("vergleichbar", True)}
            if gemeinsam:
                for b, karten_wb in sorted(gemeinsam.items(),
                                            key=lambda kv: _BAND_RANG[kv[0]]):
                    for karte_wb in karten_wb[a]:
                        zeilen.append(_paar_zeile(
                            a, b, karte_wb, je_band[b]["Vodafone"]))
                continue
            karte_anders = uebrig.get(a)
            if karte_anders is not None:
                zeilen.append(_zeile_fuer_anbieter(a, karte_anders, basis,
                                                   band_je_tarif))
                continue
            zeilen.append(_zeile_fuer_anbieter(a, None, basis, band_je_tarif))
        zeilen.sort(key=lambda z: z["prozent"] if z["prozent"] is not None
                    else float("inf"))
        rang = min((z["prozent"] for z in zeilen if z["prozent"] is not None),
                  default=float("inf"))
        gruppen.append({
            "id": modell["id"], "titel": modell["titel"],
            "hersteller": modell["hersteller"], "speicher": modell["speicher"],
            "vodafone": basis, "vodafone_grund": "",
            "zeilen": zeilen, "rang": rang,
        })
    gruppen.sort(key=lambda g: g["rang"])
    return gruppen


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
            zeilen.append({
                "modell": z.get("modell", ""), "hersteller": z.get("hersteller", ""),
                "speicher": z.get("speicher"),
                "vodafone_preis": vf["preis"], "vodafone_url": vf.get("url", ""),
                "vodafone_abgerufen_am": vf.get("abgerufen_am", ""),
                "anbieter": w.get("laden") or w.get("anbieter", ""),
                "preis": w["preis"], "url": w.get("url", ""),
                "abgerufen_am": w.get("abgerufen_am", ""),
                "prozent": prozent,
            })
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
        out.append({"anbieter": z.get("name", ""), "aktiv": bool(z.get("aktiv")),
                   "grund": z.get("grund") or "Keine Daten erhoben."})
    out.sort(key=lambda x: x["anbieter"])
    return out


def radar(tco: dict, vergleich_ohne_vertrag: dict, quellenlage: dict) -> dict:
    """Alles fuer wettbewerbsradar.html.

    `gruppen`/`haendler` bleiben die VOLLSTAENDIGEN Listen (Test c: nichts
    wird entfernt); `gruppen_sichtbar`/`gruppen_rest` und
    `haendler_sichtbar`/`haendler_rest` sind nur die Kappung der
    ANSICHT - dieselbe Bauform wie `geraete_alarme.zeilen()`
    (`sichtbar`/`rest`).
    """
    band_je_tarif = tco.get("band_je_tarif") or {}
    gruppen = netzbetreiber_gruppen(tco.get("modelle", []), band_je_tarif)
    haendler = haendler_zeilen(vergleich_ohne_vertrag)
    fehlt = nicht_erhebbar(quellenlage)
    hat_vergleichbare = any(z["prozent"] is not None
                            for g in gruppen for z in g["zeilen"])
    return {
        "gruppen": gruppen,
        "gruppen_sichtbar": gruppen[:SICHTBAR_MAX],
        "gruppen_rest": gruppen[SICHTBAR_MAX:],
        "haendler": haendler,
        "haendler_sichtbar": haendler[:HAENDLER_SICHTBAR_MAX],
        "haendler_rest": haendler[HAENDLER_SICHTBAR_MAX:],
        "nicht_erhebbar": fehlt,
        "hat_daten": bool(gruppen),
        "hat_vergleichbare_zeilen": hat_vergleichbare or bool(haendler),
        "anbieter_erwartet": list(NETZ_WETTBEWERBER),
    }


def leer() -> dict:
    return {"gruppen": [], "gruppen_sichtbar": [], "gruppen_rest": [],
            "haendler": [], "haendler_sichtbar": [], "haendler_rest": [],
            "nicht_erhebbar": [],
            "hat_daten": False, "hat_vergleichbare_zeilen": False,
            "anbieter_erwartet": list(NETZ_WETTBEWERBER)}
