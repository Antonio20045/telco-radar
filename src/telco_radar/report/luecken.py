"""Die Gegenfrage der Differenzierungs-Seite: *wer hat etwas, das wir nicht haben?*

Die Seite zeigte 71 Beispiele und wer am breitesten aufgestellt ist -
Deutsche Telekom, Verizon, T-Mobile US, Reliance Jio, AT&T, SK Telecom,
Telkomsel. Vodafone kam darin nicht vor. Sie beantwortete damit die einzige
Frage nie, wegen der ein Portfolio-Manager sie aufschlaegt.

Drei Ansichten, alle gerechnet
------------------------------
1. **Weisse Flecken.** Hebel, die mehrere Wettbewerber ziehen und wir nicht.
   Sortiert nach der Zahl der Wettbewerber - je mehr, desto weniger ist es
   ein Einzelfall.
2. **Direktvergleich.** Eine Zeile je Hebel: was der breiteste Anbieter im
   Bestand hat, was wir haben, mit Quelle.
3. Was seit der letzten Ausgabe dazukam - das rechnet `report/seit.py` und
   steht neben der Ueberschrift.

Die eine Regel
--------------
**Ein weisser Fleck entsteht nur aus einem gepflegten "nein" mit Datum.**
Ein Hebel, zu dem in `config/vodafone_hebel.yaml` nichts steht, ist "noch
nicht erfasst" - er zaehlt NICHT als Luecke. Ein falsches "Vodafone hat das
nicht" bei etwas, das es gibt, kostet mehr Vertrauen als zehn richtige
Eintraege einbringen, und es faellt genau der Person auf, die die Seite
benutzt.

Aus demselben Grund verfaellt ein Eintrag ohne `stand`: eine undatierte
Aussage ueber ein Portfolio ist nach drei Monaten keine Aussage mehr.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

JA, NEIN, OFFEN = "ja", "nein", "offen"

# Ab wie vielen verschiedenen Wettbewerbern ein unbesetzter Hebel ein weisser
# Fleck ist. Einer ist ein Einzelfall, zwei sind eine Bewegung.
MIND_WETTBEWERBER = 2


@dataclass
class EigeneHebel:
    markt: str = ""
    direktvergleich: str = ""
    hebel: dict[str, dict] = field(default_factory=dict)

    def zustand(self, key: str) -> str:
        eintrag = self.hebel.get(key) or {}
        # Ohne Datum keine Aussage - egal, was dasteht.
        if not (eintrag.get("stand") or "").strip():
            return OFFEN
        wert = str(eintrag.get("wir_haben") or OFFEN).strip().lower()
        return wert if wert in (JA, NEIN) else OFFEN

    def beispiel(self, key: str) -> str:
        return str((self.hebel.get(key) or {}).get("beispiel") or "")

    def stand(self, key: str) -> str:
        return str((self.hebel.get(key) or {}).get("stand") or "")

    @property
    def erfasst(self) -> int:
        return sum(1 for k in self.hebel if self.zustand(k) != OFFEN)


def lade_eigene_hebel(root: Path) -> EigeneHebel:
    pfad = Path(root) / "config" / "vodafone_hebel.yaml"
    if not pfad.exists():
        log.info("config/vodafone_hebel.yaml fehlt - die Luecken-Ansicht "
                 "bleibt aus")
        return EigeneHebel()
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    return EigeneHebel(
        markt=str(daten.get("markt") or ""),
        direktvergleich=str(daten.get("direktvergleich") or ""),
        hebel={str(h.get("key")): h for h in (daten.get("hebel") or [])
               if h.get("key")},
    )


def _absender(eintrag: dict) -> str:
    return str(eintrag.get("operator") or eintrag.get("company")
               or eintrag.get("source") or "").strip()


def bauen(bestand: list[dict], theme_label: dict[str, str],
          eigene: EigeneHebel) -> dict:
    """Die drei Ansichten. `bestand` ist der gemischte Differenzierungs-Bestand
    (differenzierung_view.merge), also je Eintrag mindestens `theme`, ein
    Absenderfeld und `url`."""
    je_hebel: dict[str, dict] = {}
    for e in bestand:
        key = str(e.get("theme") or "")
        if not key:
            continue
        eintrag = je_hebel.setdefault(
            key, {"key": key, "label": theme_label.get(key, key),
                  "wettbewerber": set(), "beispiele": []})
        absender = _absender(e)
        if absender:
            eintrag["wettbewerber"].add(absender)
        eintrag["beispiele"].append(e)

    flecken, vergleich = [], []
    for key, label in theme_label.items():
        daten = je_hebel.get(key) or {"wettbewerber": set(), "beispiele": []}
        n_wettbewerber = len(daten["wettbewerber"])
        zustand = eigene.zustand(key)
        zeile = {
            "key": key,
            "label": label,
            "n_wettbewerber": n_wettbewerber,
            "wettbewerber": sorted(daten["wettbewerber"])[:5],
            "zustand": zustand,
            "eigenes": eigene.beispiel(key),
            "stand": eigene.stand(key),
        }
        vergleich.append(zeile)
        # Ein weisser Fleck ist ein gepflegtes "nein" gegen mehrere
        # Wettbewerber - nie ein "offen".
        if zustand == NEIN and n_wettbewerber >= MIND_WETTBEWERBER:
            flecken.append(zeile)

    flecken.sort(key=lambda z: (-z["n_wettbewerber"], z["label"]))
    vergleich.sort(key=lambda z: (-z["n_wettbewerber"], z["label"]))

    # Der Direktvergleich: was der genannte Wettbewerber je Hebel hat.
    gegner = eigene.direktvergleich
    gegner_hebel = []
    if gegner:
        for zeile in vergleich:
            treffer = [e for e in (je_hebel.get(zeile["key"]) or
                                   {"beispiele": []})["beispiele"]
                       if gegner.lower() in _absender(e).lower()]
            if not treffer and zeile["zustand"] == OFFEN:
                continue
            gegner_hebel.append({
                **zeile,
                "gegner_hat": bool(treffer),
                "gegner_beispiel": (treffer[0].get("headline")
                                    or treffer[0].get("title")
                                    or treffer[0].get("summary", "")[:120])
                if treffer else "",
                "gegner_url": treffer[0].get("url") if treffer else "",
            })

    return {
        "aktiv": bool(eigene.hebel),
        "markt": eigene.markt,
        "gegner": gegner,
        "flecken": flecken,
        "vergleich": vergleich,
        "gegner_hebel": gegner_hebel,
        "n_erfasst": eigene.erfasst,
        "n_hebel": len(eigene.hebel),
        # Solange nichts erfasst ist, sagt die Seite das - statt zwoelf
        # weisse Flecken zu behaupten, die niemand geprueft hat.
        "unvollstaendig": eigene.erfasst < len(eigene.hebel),
    }
