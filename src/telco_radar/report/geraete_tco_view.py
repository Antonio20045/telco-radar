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

from . import geraete_vergleich
from ..geraete_model import VERGLEICHBARE_ZUSTAENDE, Ratenzahlung
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

# Hoechstens so viele TCO-Zeilen ohne Aufklappen. Gerechnet wie
# `geraete_vergleich.UEBERSICHT_MAX_ZEILEN`: die Seite steht unter einem
# Hoehenbudget von 3000 px je Reiter (`pruefe_portal.py` Kriterium 11b), eine
# Zeile dieser Tafel misst mit ihrem Aufklapper rund 84 px, der Kopf der
# Tafel rund 900. Ein Deckel in Zeilen ist immer nur ein Stellvertreter fuer
# eine Grenze in Pixeln (CLAUDE.md § 6) - deshalb misst 11b die WIRKLICH
# ausgelieferte Seite und nicht diese Zahl.
SICHTBAR_MAX = 20

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
        # Der Name kommt aus dem Katalog, und der Weg dorthin fuehrt ueber
        # die LISTUNG derselben SKU - nie ueber ein Zerlegen der `sku_id`.
        # `apple-iphone-16-128gb-blaugruen` liesse sich zwar zu
        # `apple-iphone-16` zurechtschneiden, aber eine Farbe mit Bindestrich
        # ("space-grau") verschoebe den Schnitt, und dann stuende dasselbe
        # Geraet unter zwei Namen in derselben Tabelle. Dieselbe Regel wie
        # in `geraete_model`: die ID kommt aus dem Katalog, nie aus dem Text.
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
_BUENDEL_FELDER = ("sku_id", "anbieter", "tarif_name", "tarif_monatlich",
                   "geraet_zuzahlung", "geraet_monatsrate", "laufzeit_monate",
                   "anschlusspreis", "quelle_url", "abgerufen_am")

_REFERENZ_FELDER = ("anbieter", "tarif_name", "tarif_sim_only_monatlich",
                    "anschlusspreis", "quelle_url", "abgerufen_am")


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


def _offene_posten(zeilen: list) -> list[dict]:
    """Die Vereinigung der Luecken aller Zeilen, in fester Reihenfolge.

    Die VEREINIGUNG und nicht der Durchschnitt: gefragt ist, was der
    Rechnung noch irgendwo fehlt. Ein Posten, den nur die Haelfte der
    Anbieter ausweist, ist eine offene Baustelle und keine erledigte.

    Die Reihenfolge kommt aus `PHASE_JE_LUECKE` und nicht aus einem `set` -
    eine Liste, die je Lauf anders sortiert ist, erzeugt bei jedem Rendern
    einen Diff in `site/` und damit einen Commit ohne Inhalt.
    """
    offen = {n for z in zeilen for n in
             (l["name"] for l in z["luecken"])} if zeilen else set(_OHNE_BUENDEL)
    return [{"name": n, "phase": PHASE_JE_LUECKE[n]}
            for n in PHASE_JE_LUECKE if n in offen]


def aufbereiten(buendel: list, referenzen: list, eintraege: list, katalog,
                lesbar: bool = True) -> dict:
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
    for r in referenzen:
        if isinstance(r, SimOnlyReferenz):
            referenz_je_schluessel[r.id] = r

    # sku_id -> (device_id, speicher). Beides steht an der Listung; ein
    # Buendel traegt nur die `sku_id`, und der Katalogname haengt an der
    # `device_id`.
    geraet_je_sku: dict[str, tuple] = {}
    for e in eintraege:
        if e.get("sku_id"):
            geraet_je_sku.setdefault(e["sku_id"],
                                     (e.get("device_id") or "",
                                      e.get("speicher_gb")))

    zeilen = []
    for b in buendel:
        if not isinstance(b, Buendel) or b.ohne_geraet:
            # Eine SIM-only-Zeile ist kein Angebot dieser Tafel, sondern der
            # Massstab dahinter. Sie steht in `referenzen`.
            continue
        referenz = referenz_je_schluessel.get(
            sim_only_id(b.anbieter, b.tarif_name))
        zeilen.append(_zeile(b, referenz, katalog, geraet_je_sku))

    zeilen.sort(key=lambda z: (not z["belastbar"], z["gesamt"] is None,
                              z["gesamt"] or 0.0, z["geraet"]))
    bereit = _bereitschaft(eintraege)

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
        "offene_posten": _offene_posten(zeilen),
        "horizont": TCO_HORIZONT,
    }


def leer() -> dict:
    """Der Zustand ohne lesbare Geraetedatenbank."""
    return {"hat_tco": False, "zeilen": [], "zeilen_gesamt": 0,
            "delta": [], "bereitschaft": [], "lesbar": True,
            "offene_posten": _offene_posten([]),
            "horizont": TCO_HORIZONT}
