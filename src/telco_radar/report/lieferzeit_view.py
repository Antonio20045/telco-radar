"""Die Lieferzeit-Seite: Matrix Anbieter x Produkt plus Zeitreihe.

Gerechnet, nie geraten. Der Wert einer solchen Seite haengt vollstaendig
daran, dass jede Zahl nachvollziehbar ist - es gibt keine oeffentliche
Quelle, gegen die jemand sie gegenpruefen koennte, also muss die Seite ihre
eigene Gegenprobe mitliefern: Originaltext, Methode, Belastbarkeit,
Messzeitpunkt.

Was NICHT gezeigt wird
----------------------
Beobachtungen in Quarantaene (unplausibler Wert, Platzhalter statt Zahl,
keine Angabe gefunden). Sie stehen im Speicher und in der Bilanz, aber nicht
in der Matrix - eine Zahl ohne Beleg ist auf dieser Seite schlimmer als eine
Luecke, weil niemand sie nachpruefen kann.
"""
from __future__ import annotations

from datetime import datetime

# Wie viele Messpunkte die Zeitreihe je Paar zeigt. Genug fuer einen Verlauf,
# wenig genug fuer eine Zeile.
MAX_PUNKTE = 14


def _tage_text(b: dict) -> str:
    if b.get("verfuegbarkeit") == "nein":
        return "nicht lieferbar"
    lo, hi = b.get("tage_min"), b.get("tage_max")
    if lo is None and hi is None:
        return "—"
    if lo == hi:
        return "sofort" if lo == 0 else f"{lo} Tage"
    return f"{lo}–{hi} Tage"


def aufbereiten(daten: dict, korb, heute: str = "") -> dict:
    """`daten` ist der Inhalt von data/state/lieferzeit.json."""
    reihen = (daten or {}).get("reihen") or {}
    anbieter: list[str] = []
    for key in reihen:
        marke = key.split("|", 1)[1] if "|" in key else key
        if marke not in anbieter:
            anbieter.append(marke)
    anbieter.sort()

    zeilen = []
    for produkt in korb.produkte:
        felder = []
        for marke in anbieter:
            reihe = [b for b in (reihen.get(f"{produkt.ref}|{marke}") or [])
                     if not b.get("quarantaene")]
            letzte = reihe[-1] if reihe else None
            verlauf = [{"datum": (b.get("zeitstempel") or "")[:10],
                        "tage": b.get("tage_max"),
                        "lage": b.get("verfuegbarkeit")}
                       for b in reihe[-MAX_PUNKTE:]]
            felder.append({
                "anbieter": marke,
                "hat_wert": letzte is not None,
                "text": _tage_text(letzte) if letzte else "nicht erfasst",
                "lage": (letzte or {}).get("verfuegbarkeit") or "",
                "roh": (letzte or {}).get("lieferzeit_roh") or "",
                "methode": (letzte or {}).get("methode") or "",
                "belastbarkeit": (letzte or {}).get("belastbarkeit") or "",
                "gemessen": ((letzte or {}).get("zeitstempel") or "")[:10],
                "url": (letzte or {}).get("url") or "",
                "verlauf": verlauf,
                # Der Sprung, auf den es ankommt - berechnet aus derselben
                # Reihe, damit die Seite nicht auf ein Feld angewiesen ist,
                # das ein Lauf gesetzt haben muss.
                "engpass": _engpass(verlauf),
            })
        zeilen.append({"produkt": produkt.name, "variante": produkt.variante,
                       "typ": produkt.typ, "felder": felder})

    meta = [{"anbieter": marke,
             "ident": (korb.anbieter_meta.get(marke) or {}).get("ident", ""),
             "getrennte_sendung": (korb.anbieter_meta.get(marke) or {})
             .get("getrennte_sendung", False)}
            for marke in anbieter]

    return {
        "aktiv": bool(anbieter and korb.produkte),
        "anbieter": anbieter,
        "zeilen": zeilen,
        "meta": meta,
        "test_plz": korb.test_plz,
        "stand": (daten or {}).get("stand") or heute,
        "n_messpunkte": sum(len(v) for v in reihen.values()),
        "n_quarantaene": sum(1 for v in reihen.values() for b in v
                             if b.get("quarantaene")),
    }


def _engpass(verlauf: list[dict]) -> bool:
    """Ist die Lieferzeit zuletzt deutlich gesprungen?

    Nicht die absolute Zahl ist die Nachricht - manche Anbieter liefern
    grundsaetzlich in zehn Tagen. Die Nachricht ist die Veraenderung.
    """
    from ..collect.lieferzeit import ENGPASS_AB_TAGEN, ENGPASS_SPRUNG
    werte = [p for p in verlauf if p.get("tage") is not None]
    if len(werte) < 2:
        return False
    jetzt, vorher = werte[-1]["tage"], werte[-2]["tage"]
    return jetzt >= ENGPASS_AB_TAGEN and (jetzt - vorher) >= ENGPASS_SPRUNG
