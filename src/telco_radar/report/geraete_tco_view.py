"""Reiter "Was kostet es": die TCO-24 auf der Seite (Phase 8, Skelett).

Warum dieser Reiter eine eigene Tafel ist
-----------------------------------------
Die Alarmtabelle beantwortet "wo liegen wir im Preis zurueck". Diese Tafel
beantwortet "was kostet das ueber die Laufzeit". Zwei Fragen, zwei Tafeln -
dieselbe Begruendung wie fuer die vier bestehenden Reiter, und ausdruecklich
KEINE weitere Spalte in der Alarmtabelle (Strategie § 8, Phase 8, Punkt 1).
Eine TCO neben einem Barpreis in derselben Zeile waere genau der Befund, mit
dem dieses Vorhaben angefangen hat: zwei Groessen unter einer Ueberschrift.

Der Stand, gegen den dieses Modul gebaut ist (04.09.2026)
--------------------------------------------------------
`data/state/geraete_tco.json` gibt es noch nicht. Es gibt **null Buendel und
null SIM-only-Referenzen**, weil kein Adapter Tarifpreise sammelt - das ist
Phase 6. Also ist heute **keine einzige TCO-24 rechenbar**, und diese Tafel
zeigt statt einer Zahl die benannte Luecke.

Das ist keine Notloesung, sondern der Punkt. Aus `report/effektivpreis.py`
woertlich uebernommen und in `tco_model` § 6.4 wiederholt: "Wenn kein
Anschlusspreis bekannt ist, heisst das nicht kostenlos." Eine Tafel, die aus
einem Geraetepreis ohne Tarif eine gerundete Gesamtsumme macht, waere eine
Meinung mit Eurozeichen. Sobald Phase 6 die Tarifpreise liefert, fuellt sich
dieselbe Spalte ohne eine Zeile Aenderung an dieser Datei.

Die vier Regeln, die dieses Modul tragen
----------------------------------------
1. **Gerechnet wird ausschliesslich in `tco_model`.** Dieses Modul ruft
   `tco_24()` und `geraeteanteil()` auf und formt das Ergebnis; es addiert
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

from . import geraete_tco_grafik, geraete_tco_karten, geraete_vergleich
from . import geraete_verlauf
from ..geraete_model import (VERGLEICHBARE_ZUSTAENDE, Ratenzahlung,
                             normalisiere)
from ..tarif_model import PREISTYP_LIVE_SHOP
from ..tco_model import (POSTEN_ANSCHLUSS, POSTEN_RABATTE, POSTEN_RATE,
                         POSTEN_TARIF, POSTEN_ZUZAHLUNG, TCO_HORIZONT,
                         _LUECKEN_OHNE_EINFLUSS_AUF_DIE_DIFFERENZ, Buendel,
                         Rabatt, SimOnlyReferenz, geraeteanteil, sim_only_id,
                         tco_24)

log = logging.getLogger(__name__)

# Der eigene Anbieter. Dieselbe Schreibweise wie in `geraete_verlauf._eigen`
# und `geraete_vergleich`; sie steht hier noch einmal, weil ein Import quer
# durch die Reiter eine Abhaengigkeit zwischen zwei Tafeln waere, die sonst
# nichts miteinander zu tun haben.
EIGEN = "vodafone"

# Hoechstens so viele TCO-Zeilen ohne Aufklappen. Die Seite steht unter
# einem Hoehenbudget von 3000 px je Reiter (`pruefe_portal.py` Kriterium
# 11b), und ein Deckel in Zeilen ist immer nur ein Stellvertreter fuer eine
# Grenze in Pixeln (CLAUDE.md § 6) - deshalb misst 11b die WIRKLICH
# ausgelieferte Seite und nicht diese Zahl.
#
# BIS ZUM 04.09.2026 STANDEN HIER 20 UND 12, und die Rechnung daneben
# schaetzte eine Zeile auf 84 px. Beides war an einer Tafel OHNE Buendel
# kalibriert. Mit den ersten 62 Buendeln riss der Reiter das Budget:
# an der echten Seite nachgemessen (37 Referenzen, Chromium 1440x900)
#
#     Zeilen  Referenzen   tafel-tco
#         20          12      4604 px   <- Budget gerissen
#         12          12      3824 px
#          9           4      2997 px   <- 3 px Luft, zu knapp
#          8           4      2900 px   <- gewaehlt
#
# Eine TCO-Zeile misst mit ihrem zugeklappten Aufklapper rund 97 px, eine
# Referenzzeile rund 67 - nicht 84 und 38. Die Schaetzung von damals ist
# durch die Messung ersetzt.
#
# WARUM DIE REFERENZEN MITGEBEN MUSSTEN: mit den zwoelf offenen Referenzen
# passen genau DREI Buendel unter das Budget, und eine Tafel mit dem Titel
# "Was ein Geraet ueber 24 Monate kostet" beantwortet mit drei von 62
# Zeilen ihre eigene Frage nicht. Vor dieser Phase WAREN die Referenzen der
# Inhalt der Tafel - es gab nichts anderes; jetzt sind sie der Massstab
# hinter den Zahlen. Geloescht ist nichts: die uebrigen stehen im
# Aufklapper, der schon vorher dreizehn von ihnen trug.
#
# NULL geht dabei nicht: die Vorlage haengt Ueberschrift, Erklaersatz UND
# den Aufklapper an `{% if geraete.tco.referenzen %}`. Bei 0 verschwaende
# nicht die offene Tabelle, sondern der ganze Abschnitt samt allen Belegen.
#
# Das ist eine Notbremse, keine Loesung: die Tafel braucht Platz fuer ihre
# Buendel, und den schafft nur ein Umbau ihres Aufbaus (Phase R).
SICHTBAR_MAX = 8

# Hoechstens so viele SIM-only-Referenzen offen; der Rest steht zugeklappt
# darunter und ist NICHT geloescht. Gemessen: rund 67 px je Zeile, siehe
# die Tabelle bei `SICHTBAR_MAX`.
REFERENZEN_SICHTBAR = 4

# Welche Phase welchen fehlenden Posten liefert. Die Tafel nennt sie, damit
# eine Luecke ein Datum bekommt statt eines Achselzuckens - "keine
# Tarifdaten" allein ist eine Feststellung, "keine Tarifdaten, Phase 6" ist
# eine Auskunft.
PHASE_JE_LUECKE = {
    POSTEN_TARIF: "Phase 6 (Tarife: Bestand und Bezug)",
    POSTEN_ZUZAHLUNG: "Phase 4 (die Adapter liefern die volle Preisstruktur)",
    POSTEN_RATE: "Phase 4 (die Adapter liefern die volle Preisstruktur)",
    POSTEN_ANSCHLUSS: "Phase 6 (Anschlusspreis aus dem Produktinformationsblatt)",
    # Sichtbarer Text traegt Umlaute und den Gedankenstrich des Portals -
    # nicht die ASCII-Umschrift der Kommentare. Dieselbe Lehre wie bei der
    # Uebersetzungsseite ("Maschinelle Uebersetzung" stand sichtbar auf der
    # Seite, waehrend der Rest des Portals Umlaute schreibt).
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
        # Ein Buendel, dessen SKU heute in keiner Listung steht (der
        # Geraetezweig hat sie ausgelistet, der Tarifzweig fuehrt sie noch),
        # bekaeme sonst "?" als Namen - im Banner wie in der Tabelle. Die
        # SKU ist haesslich, aber sie benennt das Geraet; ein Fragezeichen
        # benennt gar nichts.
        return device_id or rueckfall or "?"
    return f"{g.modell} {speicher} GB" if speicher else g.modell


# --------------------------------------------------------------------------
# Die TCO-Zeilen - aus echten Buendeln, heute null Stueck
# --------------------------------------------------------------------------

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
        # `geraeteanteil` wirft, wenn Anbieter oder Tarif auseinanderlaufen.
        # Das ist ein Fehler im Aufruf und keine Datenluecke - hier kann er
        # nicht auftreten, weil die Referenz ueber genau diesen Schluessel
        # gesucht wurde.
        anteil = geraeteanteil(buendel, referenz)

    return {
        "sku_id": buendel.sku_id,
        # Der Name kommt aus dem Katalog: ueber die LISTUNG derselben SKU,
        # ersatzweise ueber die Katalog-ID am Anfang der SKU
        # (`geraet_aus_sku` - die laengste Katalog-ID vor dem
        # Speichersegment, kein Schnitt am Bindestrich; eine Farbe mit
        # Bindestrich liegt dahinter). Dieselbe Regel wie in
        # `geraete_model`: die ID kommt aus dem Katalog, nie aus dem Text.
        "geraet": _label(katalog, *geraet_je_sku.get(buendel.sku_id,
                                                     ("", None)),
                         rueckfall=buendel.sku_id),
        "anbieter": buendel.anbieter,
        "eigen": _eigen(buendel.anbieter),
        "tarif": buendel.tarif_name,
        "belastbar": ergebnis.belastbar,
        # Die Luecken, die eine DIFFERENZ verschieben - also alle ausser den
        # Rabatten, die auf keiner Seite eingerechnet werden. `Tco.belastbar`
        # reicht dafuer nicht: es verlangt nur den Tarifgrundpreis, und eine
        # Zeile ohne gemessene Geraeterate ist damit "belastbar" und im
        # Delta um den ganzen Geraetepreis zu billig. Dieselbe Schwelle wie
        # `tco_model.Geraeteanteil.belastbar`.
        "delta_luecken": [n for n in ergebnis.luecken
                          if n not in _LUECKEN_OHNE_EINFLUSS_AUF_DIE_DIFFERENZ],
        # Die zwei Zahlen der Seite (E2): TCO-24 gross, Ø/Monat daneben.
        # Beide nur bei belastbar - sonst waere die Zweitzahl der Beleg
        # dafuer, dass die Erstzahl doch eine ist.
        "gesamt": ergebnis.gesamt if ergebnis.belastbar else None,
        "monatlich": ergebnis.monatlich if ergebnis.belastbar else None,
        "bestandteile": [{"name": n, "betrag": b}
                         for n, b in ergebnis.bestandteile.items()],
        "luecken": [{"name": n, "phase": PHASE_JE_LUECKE.get(n, "")}
                    for n in ergebnis.luecken],
        # Was jenseits des Horizonts liegt, steht NEBEN der Zahl statt aus
        # ihr herauszufallen (E2, gegen die CHECK24-Kappung aus § 5.4).
        #
        # DURCHGEREICHT, NICHT AUF None GEDREHT. Ein `or None` haette hier
        # aus dem gemessenen 0.0 ("die Raten laufen genau 24 Monate, es ist
        # nichts offen") eine Luecke gemacht ("nicht gemessen") - genau die
        # Verwechslung, gegen die dieses Modul und `tco_model` gebaut sind.
        # Ob der Satz auf der Seite erscheint, entscheidet die Vorlage an
        # ihrer Wahrheitspruefung; das ist eine Anzeigefrage und keine
        # Aussage ueber die Datenlage.
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
    return (zeile["belastbar"] and zeile["gesamt"] is not None
            and not zeile["delta_luecken"])


def _wesentlich(differenz: float, bezug: float) -> bool:
    """Ist der Abstand eine Meldung wert? ODER, nicht UND - wie nebenan.

    Die Konstanten kommen aus `geraete_vergleich`, damit die zwei Tafeln
    derselben Seite nicht zwei Wesentlichkeitsbegriffe fuehren. Bei 200 EUR
    sind 15 EUR viel und 3 Prozent wenig, bei 2000 EUR umgekehrt.
    """
    abstand = abs(differenz)
    prozent = (abstand / bezug * 100) if bezug else 0.0
    return (prozent >= geraete_vergleich.WESENTLICH_PROZENT
            or abstand >= geraete_vergleich.WESENTLICH_EURO)


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
    # UNSER GUENSTIGSTES Buendel je Geraet ist der Massstab, und die Wahl
    # steht hier ausgeschrieben. Ein blosses Woerterbuch-Verstaendnis
    # (`{z["sku_id"]: z for z in zeilen}`) haette bei zwei Vodafone-Tarifen
    # zum selben Geraet stillschweigend den zuletzt gelesenen genommen -
    # eine Auswahl nach Listenposition, wie sie schon der Uebersetzungs-
    # deckel und `max_produkte` einmal getroffen haben. Der guenstigste ist
    # die Zahl, die wir gegen uns gelten lassen muessen.
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
        # WESENTLICHKEIT, dieselbe Schwelle und dieselbe Begruendung wie in
        # `geraete_vergleich`: unter drei Prozent ODER fuenfzehn Euro ist
        # der Abstand keine Meldung. Ohne sie schrieb das lauteste Element
        # des Reiters bei zwei gleich teuren Buendeln "0,00 EUR teurer als
        # bei uns".
        if not _wesentlich(differenz, unser["gesamt"]):
            continue
        treffer.append({
            "geraet": z["geraet"], "sku_id": z["sku_id"],
            "anbieter": z["anbieter"], "tarif": z["tarif"],
            "fremd": z["gesamt"], "eigen": unser["gesamt"],
            "eigen_tarif": unser["tarif"],
            # BEIDE Quelllinks. Das Banner ist eine Aussage ueber zwei
            # Angebote, und dieses Portal belegt jede Aussage - die
            # Tabelle darunter ist auf `SICHTBAR_MAX` gedeckelt, eine
            # gemeldete Zeile steht also nicht zwingend darin. Ohne die
            # Links waere der Deckel eine stille Beleglosigkeit.
            "quelle_url": z["quelle_url"],
            "eigen_quelle_url": unser["quelle_url"],
            "differenz": differenz,
            # "guenstiger" heisst: guenstiger ALS WIR. Das Vorzeichen steht
            # damit einmal im Wort und einmal in der Zahl; wer nur eines
            # liest, liest dasselbe.
            "guenstiger": differenz < 0,
            "abstand": abs(differenz),
        })
    # Der groesste Abstand zuerst - das ist die Zeile, wegen der jemand
    # diese Tafel oeffnet.
    return sorted(treffer, key=lambda t: -t["abstand"])


# --------------------------------------------------------------------------
# Die Bereitschaft - was von der TCO heute schon gemessen ist
# --------------------------------------------------------------------------

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
        satz = je_anbieter.setdefault(name, {
            "anbieter": name, "eigen": _eigen(name), "listungen": 0,
            "mit_raten": 0, "mit_betrag": 0, "raten_probe_ok": 0,
        })
        satz["listungen"] += 1
        if e.get("preis_ohne_vertrag") is not None:
            satz["mit_betrag"] += 1
        # Die Geraetefinanzierung wird ueber `Ratenzahlung` gelesen und
        # nicht hier nachgerechnet - dieselbe Struktur, die die Listung
        # selbst benutzt (Regel 1).
        raten = _raten(e)
        if raten is not None:
            satz["mit_raten"] += 1
            # `preis_ohne_vertrag` ist ein EIGENES Optional-Feld und haengt
            # nicht an den Ratenfeldern: `geraete_store` schreibt jedes
            # Preisfeld einzeln. Eine Listung mit Ratenform ohne Barpreis
            # ist damit moeglich - und `float(None)` haette hier eine
            # TypeError geworfen, die `render_site` zwar auffaengt, aber mit
            # `geraete_view.leer()`: alle fuenf Reiter leer UND der
            # Navigationseintrag "Geraete" von jeder Seite verschwunden.
            # Genau dieser Fall kommt mit Phase 4 (Zuzahlung mit
            # Tarifreferenz statt Kassenpreis), nicht erst theoretisch.
            #
            # Die Probe rechnet `Ratenzahlung.deckt()` und nicht dieser
            # Renderer - Regel 1 des Modulkopfs.
            if raten.deckt(e.get("preis_ohne_vertrag")):
                satz["raten_probe_ok"] += 1

    zeilen = []
    for satz in je_anbieter.values():
        # Die Geraeteseite der TCO gilt als vollstaendig, wenn eine
        # Ratenzahlung mit ihren drei Feldern vorliegt. Ein reiner Barpreis
        # ist als Kassenzahl vollstaendig, taugt fuer die TCO aber nur, wenn
        # das Geraet ohne Vertrag gekauft wird - er steht deshalb als eigene
        # Preisform da und nicht als Mangel.
        satz["preisform"] = ("Ratenzahlung" if satz["mit_raten"]
                             else "Barkauf" if satz["mit_betrag"] else "-")
        zeilen.append(satz)
    return sorted(zeilen, key=lambda z: (not z["eigen"], -z["listungen"],
                                         z["anbieter"]))


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
        return Ratenzahlung(anzahlung=float(anzahlung), monatsrate=float(rate),
                            laufzeit_monate=int(laufzeit),
                            zins_effektiv=eintrag.get("zins_effektiv"))
    except (TypeError, ValueError):
        # Ein kaputter Satz darf die Tafel nicht kosten. Er zaehlt dann als
        # "keine Ratenzahlung" und faellt in der Bereitschaft auf.
        return None


# --------------------------------------------------------------------------
# Vom Speicher zum Datensatz
# --------------------------------------------------------------------------

# Die Felder, die `TcoDB` je Buendel bzw. je Referenz ablegt. Sie stehen
# hier als Liste und nicht als `**eintrag`, weil der Speicher ZUSAETZLICHE
# Felder fuehrt (`id`, `first_seen`, `last_verified`), die kein Feld des
# Datensatzes sind - ein Sternchen daraus waere ein TypeError, sobald der
# Store ein Betriebsfeld ergaenzt.
_BUENDEL_FELDER = ("sku_id", "anbieter", "tarif_name", "tarif_id",
                   "tarif_id_guete", "tarif_monatlich",
                   "tarif_bindung_monate", "buendel_monatlich",
                   "geraet_zuzahlung", "geraet_monatsrate", "laufzeit_monate",
                   "anschlusspreis", "quelle_url", "abgerufen_am", "zustand")

_REFERENZ_FELDER = ("anbieter", "tarif_name", "tarif_id", "tarif_id_guete",
                    "tarif_sim_only_monatlich",
                    "anschlusspreis", "quelle_url", "abgerufen_am",
                    "quelle_art")


def _rabatte(eintrag: dict) -> list:
    """Die Nachlaesse eines Datensatzes. Ein kaputter faellt weg, die
    uebrigen bleiben - ein Rabatt ohne Namen darf keine Zeile kosten."""
    fertig = []
    for r in (eintrag.get("rabatte") or []):
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
    eine erfundene Zahl in einer Kennzahl, und das ist teurer als eine
    fehlende Zeile.
    """
    fertig = []
    for e in eintraege:
        if not isinstance(e, dict):
            # Schon fertige Datenklassen reicht ein Aufrufer im Test durch.
            fertig.append(e)
            continue
        werte = {f: e.get(f) for f in felder if e.get(f) is not None}
        try:
            satz = typ(**werte, rabatte=_rabatte(e))
        except (TypeError, ValueError) as exc:
            log.warning("TCO-Datensatz %s uebergangen: %s",
                        e.get("id", "?"), exc)
            continue
        fertig.append(satz)
    return fertig


# --------------------------------------------------------------------------
# Der Einstieg
# --------------------------------------------------------------------------

# Was fehlt, solange es ueberhaupt kein Buendel gibt. Aus den Zeilen laesst
# sich das dann nicht rechnen - es gibt keine.
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
        # Gerechnet wird gegen den MASSSTAB, also gegen die Zeilen, die
        # wirklich auf der Seite stehen - nicht gegen die rohe Liste.
        # Eine Referenz ohne Betrag faellt aus `_referenztabelle` heraus;
        # gegen die rohe Liste gerechnet meldete die Seite dann oben "es
        # fehlen die Tarifpreise" und unten "Tarifgrundpreis: erledigt".
        if massstab:
            # Ein Tarifgrundpreis, der im Bestand steht, ist kein offener
            # Posten mehr - auch wenn noch kein Buendel ihn benutzt.
            offen.discard(POSTEN_TARIF)
            # ALLE, nicht IRGENDEINE. Die Docstring dieser Funktion sagt
            # "Vereinigung, nicht Durchschnitt": ein Posten, den nur die
            # Haelfte der Anbieter ausweist, ist eine offene Baustelle. Mit
            # `any` meldete die Seite den Anschlusspreis als erledigt,
            # sobald EIN Tarif von fuenfundzwanzig ihn nennt.
            if all(z["anschlusspreis"] is not None for z in massstab):
                offen.discard(POSTEN_ANSCHLUSS)
    return [{"name": n, "phase": PHASE_JE_LUECKE[n]}
            for n in PHASE_JE_LUECKE if n in offen]


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
        zeilen.append({
            "anbieter": r.anbieter,
            "eigen": _eigen(r.anbieter),
            "tarif": r.tarif_name,
            "tarif_id": r.tarif_id,
            "monatlich": r.tarif_sim_only_monatlich,
            # Ueber den Horizont gerechnet, damit die Zahl in derselben
            # Einheit steht wie die Leitzahl der Tabelle darueber. Gerechnet
            # wird sie hier und nicht im Template - ein Renderer, der
            # multipliziert, ist eine zweite Rechnung.
            "ueber_horizont": round(r.tarif_sim_only_monatlich * TCO_HORIZONT, 2),
            "anschlusspreis": r.anschlusspreis,
            "quelle_url": r.quelle_url,
            "abgerufen_am": r.abgerufen_am,
            "quelle_ist_dokument": r.quelle_art != PREISTYP_LIVE_SHOP,
        })
    return sorted(zeilen, key=lambda z: (not z["eigen"], z["anbieter"],
                                         z["monatlich"]))


# Die drei vom PM benannten Haendler ohne Tarifbuendel (QUELLEN_MAP.md §6,
# Ersterkundung 05.09.2026): fuer sie gibt es keine TCO zu rechnen, nur den
# reinen Geraetepreis. Dieselbe Liste steht in der Vorlage
# (`haendlerkarte`/die Zeitreihen-Legende) - EINE Liste, damit eine
# zukuenftige Ergaenzung nicht an einer der beiden Stellen vergessen wird.
HAENDLER_OHNE_BUENDEL = ("Amazon", "Expert", "Saturn")


def _haendler_ohne_buendel_preise(listungen: list) -> dict:
    """Je Haendler aus `HAENDLER_OHNE_BUENDEL`: der guenstigste NEU-Preis
    dieses Modells, falls schon erhoben - sonst `None`.

    Ein Wert hier ersetzt in der Vorlage die "Beschaffung laeuft
    seit"-Auskunft durch die echte Zahl. Mehrere Farbvarianten desselben
    Modells+Speichers sind unterschiedliche SKUs mit demselben oder sehr
    aehnlichem Preis (dieselbe Konvention wie beim "Guenstigster
    Geraetepreis" der Antwortzeile darueber) - der guenstigste gewinnt,
    nicht der zuletzt gelesene.
    """
    out: dict = {}
    for name in HAENDLER_OHNE_BUENDEL:
        kandidaten = [
            l for l in listungen
            if l.get("anbieter") == name
            and l.get("preis_ohne_vertrag") is not None
            and (l.get("zustand") or "neu") in VERGLEICHBARE_ZUSTAENDE
        ]
        if not kandidaten:
            out[name] = None
            continue
        bester = min(kandidaten, key=lambda l: l["preis_ohne_vertrag"])
        out[name] = {
            "preis": bester["preis_ohne_vertrag"],
            "quelle_url": bester.get("quelle_url", ""),
            "abgerufen_am": bester.get("abgerufen_am", ""),
        }
    return out


def aufbereiten(buendel: list, referenzen: list, eintraege: list, katalog,
                lesbar: bool = True, tarife: dict | None = None,
                historie=None) -> dict:
    """Alles, was der Reiter "Was kostet es" braucht.

    `buendel` und `referenzen` sind die Datensaetze aus
    `analyze/tco_store.TcoDB` - also Woerterbuecher, wie der Speicher sie
    ablegt. Heute sind beide leer (die Datei gibt es nicht), und dann
    besteht die Tafel aus ihrem Erklaertext, der Bereitschaftstabelle und
    der benannten Luecke. Das ist der Zustand, gegen den dieses Modul gebaut
    ist.
    """
    buendel = _aus_speicher(buendel, Buendel, _BUENDEL_FELDER)
    referenzen = _aus_speicher(referenzen, SimOnlyReferenz, _REFERENZ_FELDER)

    referenz_je_schluessel = {}
    # ZWEITER Index ueber (Anbieter, tarif_id). Er ist der Weg, der bei o2
    # ueberhaupt trifft: die SIM-only-Kachel heisst "O2 Mobile on Demand M",
    # der Geraetekatalog nennt denselben Tarif "…M Plus mit 50 GB+
    # (24 Mon.)", und `sim_only_id` schluesselt auf den NAMEN. Ueber den
    # Namen bliebe der Geraeteanteil fuer jedes o2-Buendel leer.
    #
    # Ein Anbieter, der zu EINER Tarif-ID zwei Referenzen fuehrt, bekommt
    # keine: zwei Massstaebe sind kein schwacher Massstab, sondern gar
    # keiner - dieselbe Regel wie in `tarif_bezug.ueber_betrag`. Vodafone
    # veroeffentlicht jeden Tarif zweimal, der Fall ist real.
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
        log.info("SIM-only-Massstab fuer %s ist nicht eindeutig (%s) - "
                 "kein Geraeteanteil", schluessel[1], schluessel[0])
        referenz_je_id.pop(schluessel, None)

    # sku_id -> (device_id, speicher). Beides steht an der Listung; ein
    # Buendel traegt nur die `sku_id`, und der Katalogname haengt an der
    # `device_id`.
    geraet_je_sku: dict[str, tuple] = {}
    for e in eintraege:
        if e.get("sku_id"):
            geraet_je_sku.setdefault(e["sku_id"],
                                     (e.get("device_id") or "",
                                      e.get("speicher_gb")))
    # Buendel ohne Listung: das Geraet kommt aus dem Katalog, ueber die
    # Katalog-ID am Anfang der SKU (`geraete_tco_karten.geraet_aus_sku`).
    geraete_tco_karten.ergaenze_geraete_aus_katalog(geraet_je_sku, buendel,
                                                    katalog)

    zeilen = []
    for b in buendel:
        if not isinstance(b, Buendel) or b.ohne_geraet:
            # Eine SIM-only-Zeile ist kein Angebot dieser Tafel, sondern der
            # Massstab dahinter. Sie steht in `referenzen`.
            continue
        # Erst der Name, dann die ID - dieselbe Rangfolge wie in
        # `tarif_bezug.loese`: was auf der Seite stand, schlaegt die
        # aufgeloeste Zuordnung, wenn beide etwas sagen.
        referenz = referenz_je_schluessel.get(
            sim_only_id(b.anbieter, b.tarif_name))
        if referenz is None and (b.tarif_id or "").strip():
            referenz = referenz_je_id.get(
                (normalisiere(b.anbieter), b.tarif_id.strip()))
        zeilen.append(_zeile(b, referenz, katalog, geraet_je_sku))

    zeilen.sort(key=lambda z: (not z["belastbar"], z["gesamt"] is None,
                              z["gesamt"] or 0.0, z["geraet"]))
    bereit = _bereitschaft(eintraege)
    massstab = _referenztabelle(referenzen)

    # ---- Phase R: die Hauptansicht -------------------------------------
    #
    # DIE TARIFBINDUNG STEHT NICHT IN DER GERAETENUTZLAST. o2 bindet den
    # Tarif 24 Monate und finanziert das Geraet ueber 36; die 24 stehen im
    # Tarifbestand (`tarife.jsonl`, ueber `tarif_id`). Ohne sie ist keine
    # Karte rechenbar - deshalb wird sie HIER gesetzt und nicht in der
    # Kennzahl geraten (A5.5).
    tarife = tarife or {}
    for b in buendel:
        if isinstance(b, Buendel) and b.tarif_id:
            satz = tarife.get(b.tarif_id) or {}
            laufzeit = satz.get("laufzeit_monate")
            if laufzeit:
                b.tarif_bindung_monate = int(laufzeit)

    modelle = geraete_tco_karten.modelle(buendel, eintraege, referenzen,
                                         tarife, katalog)

    # DER ZEITREIHEN-BLOCK (BRIEF_ZEITREIHE, 05.09.2026) - der neue
    # Hauptgraph ueber den Balkenbloecken. Er braucht die LISTUNGEN je
    # Modell, nicht die Buendel - deshalb einmal vorab gruppiert, statt je
    # Modell erneut ueber `eintraege` zu laufen.
    listungen_je_modell: dict[str, list] = {}
    for e in eintraege:
        mid = geraete_tco_karten.modell_schluessel(e.get("device_id"),
                                                    e.get("speicher_gb"))
        listungen_je_modell.setdefault(mid, []).append(e)

    for modell in modelle["modelle"]:
        # Die Grafik rechnet NUR Geometrie: die Betraege stehen schon in
        # den Karten, und zwei Rechnungen fuer dieselbe Zahl waeren zwei
        # Zahlen.
        modell["svg"] = geraete_tco_grafik.balken(modell)
        modell["legende"] = geraete_tco_grafik.legende(modell)
        reihen = geraete_verlauf.reihen_fuer_listungen(
            listungen_je_modell.get(modell["id"], []), historie
        ) if historie is not None else []
        modell["zeitreihe"] = geraete_tco_grafik.zeitreihe(reihen)
        # A-R3: Amazon, Expert und Saturn fuehren kein Tarifbuendel - sie
        # bekommen keine `tcokarte`. Sobald einer von ihnen fuer DIESES
        # Modell trotzdem einen reinen Geraetepreis liefert (Saturn seit
        # dem 05.09.2026), soll die Karte ihn zeigen statt ihrer
        # "Beschaffung laeuft"-Auskunft zu wiederholen - dieselbe einzelne
        # Zahl, mit der auch die Vorlage die Zeitreihen-Legende entscheidet.
        modell["haendler_ohne_buendel"] = _haendler_ohne_buendel_preise(
            listungen_je_modell.get(modell["id"], []))
        # Fertig gefiltert statt in der Vorlage nachgebaut: welche der drei
        # noch OHNE Preis sind, entscheidet dieselbe eine Zahl wie oben -
        # ein zweiter Filter im Template koennte auseinanderlaufen.
        modell["haendler_offen"] = [
            h for h in HAENDLER_OHNE_BUENDEL
            if modell["haendler_ohne_buendel"].get(h) is None]

    reihen = (geraete_tco_karten.historienreihen(eintraege, historie, katalog)
              if historie is not None else [])
    g2 = geraete_tco_grafik.historie(reihen)

    # DIE TABELLE ALLER BUENDEL KOMMT AUS DENSELBEN KARTEN wie die
    # Hauptansicht - nicht aus einer zweiten Rechnung.
    #
    # Bis zum 04.09.2026 stand hier `zeilen` aus `tco_24()`, und damit
    # trug derselbe Reiter dasselbe Buendel mit ZWEI Gesamtsummen und zwei
    # "Ø je Monat": die Karte "TCO-36 652,75 € · Ø 18,13 €", die Tabelle
    # darunter "TCO 24 Monate 568,75 € · Ø 23,70 €". Zwei Rechnungen fuer
    # dieselbe Zahl sind zwei Zahlen (CLAUDE.md § 6). `zeilen` bleibt als
    # Datenlage-Auskunft (`hat_tco`, `_offene_posten`) - gezeigt wird sie
    # nicht mehr.
    #
    # Die Referenzrechnungen stehen NICHT darin: sie sind kein Buendel,
    # sondern der Massstab daneben.
    tabelle = [k for m in modelle["modelle"] for k in m["karten"]
               if k["belastbar"] and not k["naeherung"]]
    tabelle.sort(key=lambda k: (k["schnitt_monat"] or 9e9, k["geraet"],
                                k["anbieter"]))

    return {
        # "Es gibt eine TCO zu zeigen" - nicht "es gibt Geraetedaten".
        # Die zwei auseinanderzuhalten ist der Grund, warum die Tafel heute
        # ihren Leerzustand kennt.
        "hat_tco": any(z["belastbar"] for z in zeilen),
        "zeilen": zeilen[:SICHTBAR_MAX],
        "zeilen_gesamt": len(zeilen),
        "delta": _delta(zeilen),
        "bereitschaft": bereit,
        # B6: "unlesbar" ist NICHT "noch nichts gefunden". `TcoDB` trennt
        # die zwei ausdruecklich und setzte `lesbar` - nur las das Feld
        # niemand, und die Tafel meldete bei kaputter Datei "es fehlen die
        # Tarifpreise". Die Geraetedatenbank reicht ihr `db_lesbar` an
        # derselben Stelle laengst durch; die Asymmetrie war unbegruendet.
        "lesbar": lesbar,
        # Was der Rechnung WIRKLICH noch fehlt - aus den Zeilen gerechnet,
        # nicht als feste Liste hingeschrieben.
        #
        # Die erste Fassung nannte hier fest Tarifgrundpreis, Anschlusspreis
        # und Boni. Das stimmt, solange es keine Buendel gibt - und wird zur
        # sichtbaren Falschaussage in dem Moment, in dem Phase 6 die
        # Tarifpreise liefert: die Tabelle zeigte dann einen Tarifgrundpreis
        # und der Abschnitt darunter behauptete, er fehle. Aufgefallen beim
        # ANSEHEN der Tafel mit gestellten Buendeln, nicht in einem Test.
        "offene_posten": _offene_posten(zeilen, massstab),
        # Was Phase 6 geliefert hat - der Massstab, auch ohne ein einziges
        # Buendel. Die Tafel war bis zum 04.09.2026 vollstaendig leer, und
        # der Grund stand eine Ebene tiefer: es gab keine Tarifpreise.
        "referenzen": massstab[:REFERENZEN_SICHTBAR],
        "referenzen_gesamt": len(massstab),
        "referenzen_rest": massstab[REFERENZEN_SICHTBAR:],
        "horizont": TCO_HORIZONT,
        # ---- Phase R ---------------------------------------------------
        # Die Hauptansicht: je Modell vier Anbieter und eine Grafik. Sie
        # steht NEBEN den Feldern darueber und ersetzt sie nicht - der
        # Massstab (SIM-only) und die Bereitschaft sind weiterhin die
        # Auskunft ueber die Datenlage, nur nicht mehr der Inhalt der
        # Tafel.
        "modelle": modelle["modelle"],
        "tabelle": tabelle,
        "modell_vorgabe": modelle["vorgabe"],
        "modelle_gesamt": modelle["gesamt"],
        # Buendel, die weder Listung noch Katalog aufloesen - benannt, mit
        # Grund (F-R2-3). Ein Slug als Geraetename war keins von beidem.
        "ohne_zuordnung": modelle["ohne_zuordnung"],
        "anbieter_erwartet": list(geraete_tco_karten.ANBIETER_REIHENFOLGE),
        "g2": g2,
    }


def leer() -> dict:
    """Der Zustand ohne lesbare Geraetedatenbank."""
    return {"hat_tco": False, "zeilen": [], "zeilen_gesamt": 0,
            "delta": [], "bereitschaft": [], "lesbar": True,
            "offene_posten": _offene_posten([]),
            "referenzen": [], "referenzen_gesamt": 0, "referenzen_rest": [],
            "horizont": TCO_HORIZONT,
            "modelle": [], "tabelle": [], "modell_vorgabe": "",
            "modelle_gesamt": 0, "ohne_zuordnung": [],
            "anbieter_erwartet": list(geraete_tco_karten.ANBIETER_REIHENFOLGE),
            "g2": {"svg": "", "tabelle": [], "ereignisse": [], "reihen": 0,
                   "reihen_gesamt": 0, "ausgelassen": []}}
