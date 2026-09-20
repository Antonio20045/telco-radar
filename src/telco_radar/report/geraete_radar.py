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
# E3/S3: 6 statt 20 - die Händler-Sektion ist seit E3 die DRITTE von drei
# gleichwertigen Sektionen der Radar-Tafel und teilt deren 3000-px-Budget
# (am echten Bestand: 20 Zeilen massen 993 px allein, die ganze Seite mit
# 8 Zeilen 3216 px). Der Rest steht im Aufklapper "Alle N Händler-Zeilen",
# nichts geht verloren.
HAENDLER_SICHTBAR_MAX = 6

# E3/S2: der Deckel der MODELL-LISTE im Radar-Reiter von geraete.html.
# Dieselbe Bauform wie `SICHTBAR_MAX` (nichts geloescht, Rest hinter dem
# Knopf "alle N anzeigen"), aber ein EIGENER Wert: die drei Sektionen des
# Radar-Reiters teilen sich DAS Hoehenbudget EINER Tafel (Kriterium 11b
# misst die Seite, nicht die Sektion). Am echten Bestand gemessen
# (17.09.2026, 88 Modelle, Zeile ~78 px wegen der Δ-Zweizeiligkeit):
# 6 Zeilen massen die Seite auf 3216 px - mit 5 bleibt sie unter 3000 px.
MODELLISTE_SICHTBAR = 5

# P4/D1 (STRATEGIE_GERAETE_V3, 18.09.2026): wie viele Balken die GRAFIK
# der Radar-Tafel traegt. Der Deckel ist eine HOEHEN-Rechnung, keine
# Daten-Grenze: 12 Reihen zu 30 px ergeben 360 px Plot plus Kopf - die
# Grafik steht damit samt Ueberschrift ueber der Falz eines 900-px-
# Schirms, und am Telefon (schmale Variante, 40 px je Reihe) bleibt sie
# unter 500 px. Am echten Bestand (18.09.2026) haengt die Wahl nicht an
# einem inhaltlichen Bruch: Die Plaetze 12 bis 16 tragen +150,90 € bis
# +110,90 €, alle dieselbe Richtung - die 13. Zeile haette der Grafik
# Laenge gegeben, keine Aussage. Der Rest steht in der Tabelle im
# Aufklapper unter der Grafik (nichts streichen).
GRAFIK_MAX = 12

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
                "vodafone_grund": ("Keine Vodafone-Kosten über 24 Monate "
                                  "für dieses Gerät "
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


# E3/S2: das Lueckenwort je Gruppen-Status. Es benennt, WARUM keine Zahl
# steht, statt eine leere Zelle zu zeigen - ein Modell ohne Vergleich ist
# eine Aussage (und der Grund steht wortreich in der Detailzeile).
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

    und dazu alles, was die Detailzeile braucht (VF-Basis und ALLE
    Anbieter-Zeilen der Gruppe - kein Anbieter wird weggedeckelt, B.2.5).
    KEINE zweite Rechnung: Prozent und Euro-Betraege sind die Werte der
    Paarzeile, ungekuerzt uebernommen.

    `sichtbar`/`rest` kappen nur die ANSICHT (`MODELLISTE_SICHTBAR`,
    Knopf „alle N anzeigen") - `zeilen` bleibt die vollstaendige Liste.
    """
    zeilen = []
    for g in gruppen:
        paar = next((z for z in g["zeilen"]
                     if z["status"] == STATUS_VERGLEICHBAR), None)
        luecke = ""
        sprung_band = ""
        if paar is None:
            if g["vodafone"] is None:
                luecke = "keine Vodafone-Kosten über 24 Monate erhoben"
            else:
                # band_mismatch ist der AUSSAGEKRAEFTIGSTE Grund (es gibt
                # Karten auf beiden Seiten, nur kein gemeinsames Band) -
                # Platzhalter-kein_buendel-Zeilen stehen in fast jeder
                # Gruppe daneben und wuerden ihn ueberdecken.
                luecke = "kein Vergleich"
                for status in (STATUS_BAND_MISMATCH,
                               STATUS_NICHT_VERGLEICHBAR,
                               STATUS_KEIN_BUENDEL):
                    if any(z["status"] == status for z in g["zeilen"]):
                        luecke = _LUECKE_WORT[status]
                        break
        else:
            sprung_band = paar.get("band") or ""
        zeilen.append({
            "id": g["id"], "titel": g["titel"],
            "hersteller": g["hersteller"], "speicher": g["speicher"],
            # Der TITEL traegt die GB-Stufe meist schon („Xiaomi 17 512 GB")
            # - die Klein-Zeile der Zeile wuerde sie ein zweites Mal setzen
            # („512 GB 512 GB", dieselbe Fehlerklasse wie „2454 Modelle").
            "speicher_klein": ("" if g["speicher"] and
                               f"{g['speicher']} GB" in (g["titel"] or "")
                               else (f"{g['speicher']} GB" if g["speicher"]
                                     else "")),
            "prozent": paar["prozent"] if paar else None,
            "euro": (paar["gesamt"] - paar["vf_gesamt"]) if paar else None,
            # Fertige deutsche Zeichenketten fuer die Zelle - die Vorlage
            # formatiert keine Zahl (S4; und ein zweiter Formatierer im
            # Template waere die zweite Stelle fuer dieselbe Zahl).
            "prozent_text": (_dvorzeichen(paar["prozent"], 1)
                             if paar else ""),
            "euro_text": (_dvorzeichen(paar["gesamt"] - paar["vf_gesamt"])
                          if paar else ""),
            "anbieter": (paar or {}).get("anbieter", ""),
            "tarif": (paar or {}).get("tarif", ""),
            "band_label": (paar or {}).get("band_label", ""),
            "gesamt": (paar or {}).get("gesamt"),
            "vf_gesamt": (paar or {}).get("vf_gesamt"),
            "quelle_url": (paar or {}).get("quelle_url", ""),
            "abgerufen_am": (paar or {}).get("abgerufen_am", ""),
            "luecke": luecke,
            # Das Band des Paares - der Sprung in den Graphen landet direkt
            # im Band, in dem die Abweichung gerechnet wurde (Deep-Link
            # ?modell=…&band=…). Ohne Paar bleibt es leer und der Graph
            # waehlt selbst sein erlaubtes Band.
            "sprung_band": sprung_band,
            "vodafone": g["vodafone"],
            "vodafone_grund": g["vodafone_grund"],
            "gruppe_zeilen": g["zeilen"],
        })
    return {"zeilen": zeilen,
            "sichtbar": zeilen[:MODELLISTE_SICHTBAR],
            "rest": zeilen[MODELLISTE_SICHTBAR:],
            "gesamt": len(zeilen)}


# ---------------------------------------------------------------------------
# P4/D1 (STRATEGIE_GERAETE_V3, 18.09.2026): die Balkengrafik der Radar-Tafel
#
# DIE FRAGE DES REITERS - "Bei welchem Geraet ist Vodafone teurer als der
# Wettbewerb?" - liest sich bis P4 nur als 746-Zeilen-Wand (design.md:
# "100 % Tabelle, 0 % Grafik, 727 rot eingefaerbte Elemente"). Die Grafik
# zeigt dieselbe Zahl als BILD: EIN Balken je Modell(-Speicher)-Zeile,
# Laenge = Abstand in Euro zum Vodafone-Preis, Nulllinie = Vodafone.
#
# Barpreis-Ebene wie die Alarmtabelle (nur vergleichbare Neugeraete, ohne
# Vertrag): gelesen werden die fertigen `zeilen` aus
# `geraete_vergleich.vergleich(..., preisart=OHNE_VERTRAG)` - KEINE zweite
# Preisrechnung, nur die Auswahl des Gegenstuecks je Zeile:
#   delta > 0 VF-Preis minus GUENSTIGSTEN Wettbewerber (VF teuerer),
#   delta < 0 VF-Preis minus guenstigsten der TEUEREREN (VF guenstiger).
# Preisgleichheit ist kein Abstand (STRIKT-Regel des Vergleichs) und
# faellt heraus.
#
# FARBE NACH RICHTUNG (Rot-Deckel, design.md Regel 4): Balken Richtung
# "Wettbewerber guenstiger" in Ink, Richtung "Vodafone guenstiger" in
# Blau (--al-bestpreis, die Positiv-Farbe dieser Tafel); ROT traegt
# genau EIN Balken - der groesste Abstand ZUUNGUNSTEN Vodafones (der
# schaerfste Befund). Ist kein solcher Fall im Bestand, gibt es keinen
# roten Balken - Rot ist Akzent, keine Flaeche. Die Farben prueft der
# Palette-Validator: #e60000/#2b5bd7 gegen #f6f4ee, CVD dE 29,4 (protan),
# Kontrast >= 3:1 (beide PASS, 18.09.2026).
# ---------------------------------------------------------------------------

def _x(text: object) -> str:
    """XML-Escaping fuer SVG-Text (Modelle- und Ladennamen kommen aus dem
    Bestand und duerfen & < > enthalten)."""
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


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
        zeilen.append({
            "device_id": z.get("device_id"), "speicher": z.get("speicher"),
            "modell": z.get("modell") or "", "hersteller": z.get("hersteller"),
            "delta": float(delta), "prozent": float(prozent),
            "laden": gegen.get("laden") or gegen.get("anbieter", ""),
            "vf_preis": vf, "gegen_preis": gegen.get("preis"),
        })
    return zeilen


def _balken_pfad(x_null: float, y: float, laenge: float, hoehe: float,
                 nach_rechts: bool) -> str:
    """Ein Balken mit runder AUSSEN-Seite und eckiger Basis an der
    Nulllinie (Markenspezifikation: Datenende gerundet, Basis quadrat) -
    ein `<rect rx>` rundet beide Enden und stellte die Basis als eigener
    Wert dar. Balken unter 8 px Länge bleiben eckig (kein Rundungszimmer
    in einer Nische)."""
    r = min(3.5, laenge / 2, hoehe / 2) if laenge >= 8 else 0
    if nach_rechts:
        xe = x_null + laenge
        if not r:
            return (f"M{x_null:.1f} {y:.1f}H{xe:.1f}V{y + hoehe:.1f}"
                    f"H{x_null:.1f}Z")
        return (f"M{x_null:.1f} {y:.1f}H{xe - r:.1f}Q{xe:.1f} {y:.1f} "
                f"{xe:.1f} {y + r:.1f}V{y + hoehe - r:.1f}"
                f"Q{xe:.1f} {y + hoehe:.1f} {xe - r:.1f} {y + hoehe:.1f}"
                f"H{x_null:.1f}Z")
    xe = x_null - laenge
    if not r:
        return (f"M{x_null:.1f} {y:.1f}H{xe:.1f}V{y + hoehe:.1f}"
                f"H{x_null:.1f}Z")
    return (f"M{x_null:.1f} {y:.1f}H{xe + r:.1f}Q{xe:.1f} {y:.1f} "
            f"{xe:.1f} {y + r:.1f}V{y + hoehe - r:.1f}"
            f"Q{xe:.1f} {y + hoehe:.1f} {xe + r:.1f} {y + hoehe:.1f}"
            f"H{x_null:.1f}Z")


def _grafik_svg(zeilen: list[dict], spitze_schluessel: tuple | None,
                breit: bool) -> str:
    """Das servergerenderte SVG in zwei Varianten (schirm/mobil) - kein
    Client-Rechnen. Beide stehen im DOM, das Mediaquery zeigt eine
    (derselbe Mechanismus wie die Zeitreihe `svg.gr-zr--breit/schmal`).

    EINE Euro-Skala fuer beide Richtungen (eine Achse, keine zweite
    Rechenvorschrift): der linke Arm ergibt sich aus dem groessten
    Abstand nach links, derselbe Massstab wie rechts.
    """
    n = len(zeilen)
    if breit:
        w, name_breite, wert_raum, neg_raum = 1120, 158, 158, 96
        reihen_hoehe, balken_hoehe, kopf, fuss = 30, 14, 30, 12
    else:
        w, name_breite, wert_raum, neg_raum = 350, 0, 78, 62
        reihen_hoehe, balken_hoehe, kopf, fuss = 40, 12, 26, 8
    h = kopf + n * reihen_hoehe + fuss
    max_abs = max((abs(z["delta"]) for z in zeilen), default=1.0) or 1.0
    neg_arm = max((abs(z["delta"]) for z in zeilen if z["delta"] < 0),
                  default=0.0)
    # Schmal beginnt die Nulllinie mit Einsatz (10 statt 2): eine 1,5-px-
    # Haarlinie direkt an der Kante ist auf dem Telefon unsichtbar (am
    # Screenshot vom 18.09.2026 nachgesehen), mit Einsatz liest sie sich
    # als Achse. Breit steht sie ohnehin frei hinter der Namensspalte.
    start = (2 if breit else 10) + neg_raum * (neg_arm > 0)
    verfuegbar = w - 6 - wert_raum - start
    if breit:
        verfuegbar -= name_breite + 10
        start += name_breite + 10
    skala = verfuegbar / max_abs
    x0 = start + neg_arm * skala

    spitze = None
    if spitze_schluessel is not None:
        spitze = next((z for z in zeilen
                       if (z["device_id"], z["speicher"]) == spitze_schluessel),
                      None)
    teile: list[str] = []
    teile.append(
        f"<svg class='wr-gr wr-gr--{'breit' if breit else 'schmal'}' "
        f"viewBox='0 0 {w} {h}' role='img' "
        f"aria-label='Abstand zum Vodafone-Preis in Euro, {n} Modelle"
        + (f", größter Abstand {_dvorzeichen(spitze['delta'])} Euro "
           f"bei {_x(spitze['modell'])}" if spitze else "")
        + "'>")
    # Die EINE Nulllinie mit dem EINEN Etikett (Auftrag P4/D1): kein
    # Raster und keine zweite Achse - jeder Balken traegt seinen Wert
    # selbst als Beschriftung, die Nulllinie ist die Referenz.
    anker = " text-anchor='middle'" if breit else ""
    teile.append(f"<line class='wr-gr-null' x1='{x0:.1f}' y1='{kopf - 8}' "
                 f"x2='{x0:.1f}' y2='{h - 4:.1f}'/>")
    teile.append(f"<text class='wr-gr-nulltext' x='{x0:.1f}' "
                 f"y='{kopf - 13}'{anker}>Vodafone</text>")
    for i, z in enumerate(zeilen):
        ist_spitze = spitze is not None and spitze is z
        klasse = "wr-gr-balken"
        if ist_spitze:
            klasse += " wr-gr-balken--spitze"
        elif z["delta"] > 0:
            klasse += " wr-gr-balken--teuer"
        else:
            klasse += " wr-gr-balken--gut"
        laenge = abs(z["delta"]) * skala
        wert = f"{_dvorzeichen(z['delta'])} €"
        prozent = f"{z['prozent']:+.1f}".replace(".", ",") + " %"
        titel = (f"{_x(z['modell'])}: {wert} ({prozent}) gegenüber "
                 f"{_x(z['laden'])} – Vodafone {_euro0(z['vf_preis'])}, "
                 f"{_x(z['laden'])} {_euro0(z['gegen_preis'])}")
        if breit:
            y = kopf + i * reihen_hoehe + (reihen_hoehe - balken_hoehe) / 2
            ty = y + balken_hoehe / 2 + 4
            speicher = ""
            if z["speicher"]:
                speicher = (f" <tspan class='wr-gr-name-zusatz'>· "
                            f"{_x(z['speicher'])} GB</tspan>")
            teile.append(f"<text class='wr-gr-name' x='{name_breite}' "
                         f"y='{ty:.1f}' text-anchor='end'>{_x(z['modell'])}"
                         f"{speicher}</text>")
            teile.append(
                f"<path class='{klasse}' d='"
                f"{_balken_pfad(x0, y, laenge, balken_hoehe, z['delta'] > 0)}'>"
                f"<title>{titel}</title></path>")
            if z["delta"] > 0:
                teile.append(
                    f"<text class='wr-gr-wert' x='{x0 + laenge + 8:.1f}' "
                    f"y='{ty:.1f}'>{wert}<tspan class='wr-gr-laden'> · "
                    f"{_x(z['laden'])}</tspan></text>")
            else:
                teile.append(
                    f"<text class='wr-gr-wert' x='{x0 - laenge - 8:.1f}' "
                    f"y='{ty:.1f}' text-anchor='end'>{wert}</text>")
        else:
            ly = kopf + i * reihen_hoehe
            y = ly + 19
            name = _x(z["modell"])
            if z["speicher"]:
                name = (f"{name} <tspan class='wr-gr-name-zusatz'>· "
                        f"{_x(z['speicher'])} GB</tspan>")
            teile.append(f"<text class='wr-gr-name' x='2' y='{ly + 12:.1f}'>"
                         f"{name}</text>")
            teile.append(
                f"<path class='{klasse}' d='"
                f"{_balken_pfad(x0, y, laenge, balken_hoehe, z['delta'] > 0)}'>"
                f"<title>{titel}</title></path>")
            if z["delta"] > 0:
                teile.append(f"<text class='wr-gr-wert' "
                             f"x='{x0 + laenge + 6:.1f}' y='{y + 10:.1f}'>"
                             f"{wert}</text>")
            else:
                teile.append(f"<text class='wr-gr-wert' "
                             f"x='{x0 - laenge - 6:.1f}' y='{y + 10:.1f}' "
                             f"text-anchor='end'>{wert}</text>")
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
        return {"svg_breit": "", "svg_schmal": "", "zeilen": [],
                "n": 0, "basis": 0, "spitze": None,
                "leer_grund": ("Noch keine vergleichbaren Barpreise erhoben "
                               "– die Grafik entsteht mit dem nächsten Lauf.")}
    spitze_kandidat = max((z for z in alle if z["delta"] > 0),
                          key=lambda z: z["delta"], default=None)
    gewaehlt = sorted(alle, key=lambda z: -abs(z["delta"]))[:n]
    if spitze_kandidat is not None:
        schluessel = (spitze_kandidat["device_id"],
                      spitze_kandidat["speicher"])
        if not any((z["device_id"], z["speicher"]) == schluessel
                   for z in gewaehlt):
            # P4-Fix (Code-Pruefung S4): n<=0 (ein kuenftiger Aufrufer)
            # wuerde `gewaehlt[-1]` auf einer LEEREN Liste lesen -
            # IndexError statt Leerzustand. Produktion ruft ohne n
            # (Bestand >= 1), aber die Spitze gehoert auch ins entleerte
            # Bild: dann IST sie die einzige Zeile.
            if gewaehlt:
                gewaehlt[-1] = spitze_kandidat
            else:
                gewaehlt = [spitze_kandidat]
            gewaehlt.sort(key=lambda z: -abs(z["delta"]))
    spitze = None
    if spitze_kandidat is not None:
        spitze = {"device_id": spitze_kandidat["device_id"],
                  "speicher": spitze_kandidat["speicher"],
                  # Der Schluessel fuer die Vorlage: dieselbe Normalisierung
                  # wie in der Alarm-Zeile (None -> ''), sonst traegt die
                  # Spitzen-Markierung an einem Modell ohne Speicherangabe
                  # vorbei ("...|None" trifft nie).
                  "schluessel": (f"{spitze_kandidat['device_id'] or ''}|"
                                 f"{spitze_kandidat['speicher'] or ''}"),
                  "modell": spitze_kandidat["modell"],
                  "delta": spitze_kandidat["delta"],
                  "delta_text": f"{_dvorzeichen(spitze_kandidat['delta'])} €"}
    schluessel = ((spitze["device_id"], spitze["speicher"])
                  if spitze else None)
    return {"svg_breit": _grafik_svg(gewaehlt, schluessel, True),
            "svg_schmal": _grafik_svg(gewaehlt, schluessel, False),
            "zeilen": gewaehlt, "n": len(gewaehlt), "basis": len(alle),
            "spitze": spitze, "leer_grund": ""}


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


def radar(tco: dict, vergleich_ohne_vertrag: dict, quellenlage: dict,
          alarme: dict | None = None, portfolio: dict | None = None) -> dict:
    """Alles fuer die Radar-Tafel der EINEN Geräteseite (#tafel-radar).

    `gruppen`/`haendler` bleiben die VOLLSTAENDIGEN Listen (Test c: nichts
    wird entfernt); `gruppen_sichtbar`/`gruppen_rest` und
    `haendler_sichtbar`/`haendler_rest` sind nur die Kappung der
    ANSICHT - dieselbe Bauform wie `geraete_alarme.zeilen()`
    (`sichtbar`/`rest`).

    `alarme` (seit O2, 11.09.2026) ist die Aufbereitung aus
    `geraete_view.aufbereiten` - die Alarmtabelle steht seither HIER und
    nicht mehr in der Vergleichsansicht der Geraeteseite. Sie wird als
    GANZES durchgereicht, nicht neu gerechnet: dieselbe Tabelle, derselbe
    Deckel, derselbe Ort - nur die Seite ist eine andere. Dazu
    `ohne_vodafone` aus demselben Vergleich: der Sortiments-Aufklapper
    "Bei Wettbewerbern gelistet" antwortet dieselbe Frage ueber das
    Sortiment, die der Radar ueber den Preis stellt.
    """
    band_je_tarif = tco.get("band_je_tarif") or {}
    gruppen = netzbetreiber_gruppen(tco.get("modelle", []), band_je_tarif)
    haendler = haendler_zeilen(vergleich_ohne_vertrag)
    fehlt = nicht_erhebbar(quellenlage)
    hat_vergleichbare = any(z["prozent"] is not None
                            for g in gruppen for z in g["zeilen"])
    ohne = (vergleich_ohne_vertrag or {}).get("ohne_vodafone") or []
    return {
        "gruppen": gruppen,
        "gruppen_sichtbar": gruppen[:SICHTBAR_MAX],
        "gruppen_rest": gruppen[SICHTBAR_MAX:],
        # E3/S2: die Modell-Liste des Radar-Reiters - aus denselben Gruppen
        # abgeleitet, keine zweite Rechnung.
        "modelliste": modellliste(gruppen),
        # P4/D1: die Balkengrafik - servergerendertes SVG ueber den
        # Tabellen, aus denselben Vergleichszeilen wie die Alarmtabelle.
        "grafik": grafik(vergleich_ohne_vertrag),
        "haendler": haendler,
        "haendler_sichtbar": haendler[:HAENDLER_SICHTBAR_MAX],
        "haendler_rest": haendler[HAENDLER_SICHTBAR_MAX:],
        "nicht_erhebbar": fehlt,
        "hat_daten": bool(gruppen),
        "hat_vergleichbare_zeilen": hat_vergleichbare or bool(haendler),
        "anbieter_erwartet": list(NETZ_WETTBEWERBER),
        # O2: die Alarmtabelle - VOLLSTAENDIG durchgereicht (der Deckel
        # kappt nur die Ansicht, `sichtbar` + `rest` ist die ganze Liste).
        "alarme": alarme if alarme is not None else _alarme_leer(),
        # O2: der Sortiments-Aufklapper - "gelistet, aber nicht bei uns"
        # ist die Sortimentshaelfte derselben Radar-Frage.
        "ohne_vodafone": ohne,
        "ohne_vodafone_gesamt": (vergleich_ohne_vertrag or {}).get(
            "ohne_vodafone_gesamt", len(ohne)),
        # O3: die Portfolio-Abschnitte der Geräteseite (Lifecycle,
        # Wochenkarte) - als GANZES durchgereicht, keine zweite Rechnung;
        # `render_site` baut das Dict aus denselben Feldern, die die alte
        # Tafel #tafel-portfolio las (Antonios Entscheidung, Strategie
        # §5.2: Portfolio-Fragen gehören auf die Portfolio-Seite).
        "portfolio": portfolio if portfolio is not None else _portfolio_leer(),
        # O4: der Radar-Export. Der Notzustand steht HIER (die Vorlage darf
        # nie auf einen fehlenden Schluessel treffen, dieselbe Lehre wie bei
        # `_alarme_leer`); `render_site` ueberschreibt ihn nach dem Schreiben
        # der Datei mit deren ECHTEN Angaben - Zeilenzahl und Groesse
        # kommen aus der Datei, nicht aus einer Rechnung.
        "export": {"datei": "", "zeilen": 0, "bytes": 0},
    }


def _portfolio_leer() -> dict:
    """Der Notzustand der Portfolio-Abschnitte - dieselben Schlüssel wie
    das Dict aus `render_site`, damit die Vorlage nie auf ein fehlendes
    Feld trifft (derselbe Grund wie bei `_alarme_leer`)."""
    return {
        "lifecycle": None, "auffaellig": None,
        "lifecycle_sichtbar": 0, "nachfolger_sichtbar": 0, "fenster_tage": 0,
    }


def _alarme_leer() -> dict:
    """Der Notzustand der Alarmtabelle - `geraete_alarme.leer()`, ohne den
    Import quer durch die Tafeln zu ziehen (derselbe Grund wie bei
    `EIGEN` im Modulkopf: eine Abhaengigkeit zwischen zwei Seiten, die
    sonst nichts miteinander zu tun haben)."""
    from . import geraete_alarme
    return geraete_alarme.leer()


def leer() -> dict:
    return {"gruppen": [], "gruppen_sichtbar": [], "gruppen_rest": [],
            "modelliste": {"zeilen": [], "sichtbar": [], "rest": [],
                           "gesamt": 0},
            "grafik": grafik({}),
            "haendler": [], "haendler_sichtbar": [], "haendler_rest": [],
            "nicht_erhebbar": [],
            "hat_daten": False, "hat_vergleichbare_zeilen": False,
            "anbieter_erwartet": list(NETZ_WETTBEWERBER),
            "alarme": _alarme_leer(),
            "ohne_vodafone": [], "ohne_vodafone_gesamt": 0,
            "portfolio": _portfolio_leer(),
            # O4: der Radar-Export - Notzustand mit denselben Schlüsseln,
            # damit die Vorlage nie auf ein fehlendes Feld trifft.
            "export": {"datei": "", "zeilen": 0, "bytes": 0}}
