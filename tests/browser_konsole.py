"""Was in der Browser-Konsole ein FEHLER DER SEITE ist - und was nicht.

WARUM ES DAS GIBT. Die Browser-Tests der Geraeteseite behaupten
`fehler == []`. Gemeint ist damit: "unser JavaScript wirft nicht und
unsere Dateien laden". Gemessen wurde aber etwas Weiteres: Chromium
meldet auch dann einen Konsolenfehler, wenn eine EXTERNE Ressource nicht
laedt - und `base.html.j2:14` laedt die Schriften von
fonts.googleapis.com.

Am 21.09.2026 sind daran vier Tests reihenweise rot geworden, alle mit
demselben einen Eintrag:

    error  "Failed to load resource: net::ERR_CERT_AUTHORITY_INVALID"
           location.url = https://fonts.googleapis.com/css2?family=...

Die Ursache lag nicht auf der Seite, sondern in der Sandbox: deren
ausgehender HTTPS-Verkehr laeuft durch einen Proxy, dessen Zertifikat
Chromium nicht kennt. Gemessen am gerenderten Stand war das der EINZIGE
Eintrag - das eigene `app.js` war stumm. In GitHub Actions laedt dieselbe
Anfrage und die Tests sind gruen: genau die Sorte Unterschied, die
CLAUDE.md unter "In der Cloud-Sandbox erreicht Chromium das Netz nicht
und Google Fonts laden nicht" schon notiert.

Ein Test, der an der Erreichbarkeit von Google scheitert, misst nicht die
Seite. Ein Test, der jeden Fehler durchlaesst, misst gar nichts.

ZWEI KANAELE, EINE VERDRAHTUNG
------------------------------
Ein geworfener Handler-Fehler erzeugt in Playwright NUR ein `pageerror`
und KEINEN `console`-Eintrag (gemessen 21.09.2026:
`addEventListener("click", () => { undefined.kaputt; })` -> ein Eintrag,
Typ `pageerror`). Wer nur `console` abhoert, ist blind fuer genau den
Defekt, den ein Reiter- oder Klicktest finden soll -
`test_geraete_radar_sprung_browser.py` war es bis zum 21.09.2026.

Deshalb steht hier nicht nur das Praedikat, sondern die REGISTRIERUNG:
`konsole_sammeln(seite)` haengt BEIDE Kanaele an und gibt die Liste
zurueck. Eine Testdatei, die sich die Lambda-Zeilen selbst schreibt, hat
eine zweite Definition von "Fehler" (Clean Code 7) - und wie man sieht
eine andere.

    s = context.new_page()
    fehler = konsole_sammeln(s)

WAS DURCHFAELLT UND WAS NICHT. Durch fallen nur NETZFEHLER
(`net::ERR_...`) von Adressen, die die Seite absichtlich von aussen holt.
Alles andere bleibt ein Fehler, und zwar ausdruecklich auch:

* ein HTTP-Status vom Schriftendienst ("responded with a status of 400")
  - das ist ein Tippfehler in `base.html.j2`, kein fehlendes Netz, und
  die Seite wird dann ohne Webfont ausgeliefert;
* ein Ladefehler einer EIGENEN Datei (`/app.js`, `/style.css`,
  `/logo.png`) - die gerenderte Seite zeigt auf etwas, das nicht
  ausgeliefert wird;
* eine fehlende oder leere Herkunft - im Zweifel laut, nicht still.
"""
from __future__ import annotations

from typing import Optional

# Die Adressen, die `base.html.j2` bewusst von aussen holt. Kein Muster
# wie "alles mit https": ein falscher absoluter Link auf eine eigene
# Datei soll weiterhin auffallen.
FREMDE_HERKUNFT = (
    "https://fonts.googleapis.com/",
    "https://fonts.gstatic.com/",
)

# Welche Konsolentypen ueberhaupt zaehlen. `error` ist der offensichtliche;
# `assert` ist Chromiums Typ fuer `console.assert(false, ...)` und wurde bis
# zum 21.09.2026 stillschweigend verworfen (gemessen in echtem Chromium:
# `console.assert(false, "x")` -> type == "assert", NICHT "error").
# `warning` und `log` zaehlen nicht - eine Warnung ist kein Bruch.
ZAEHLENDE_TYPEN = ("error", "assert")

# Nur ein NETZfehler wird befreit. Chromium stellt sie als `net::ERR_...`
# in den Text des Konsoleneintrags; ein HTTP-Status steht dort im
# Klartext ("responded with a status of 400"). Der Unterschied ist der
# ganze Punkt: das eine ist die Sandbox, das andere ein Fehler auf
# unserer Seite.
_NETZFEHLER = "net::ERR_"


def _fremder_netzfehler(text: str, herkunft: Optional[dict]) -> bool:
    """Netzfehler UND fremde Herkunft - beides, sonst nicht befreit."""
    if _NETZFEHLER not in (text or ""):
        return False
    url = herkunft.get("url") if isinstance(herkunft, dict) else None
    if not url:
        # Keine Herkunft heisst nicht "von aussen".
        return False
    return any(url.startswith(ort) for ort in FREMDE_HERKUNFT)


def ist_seitenfehler(typ: str, text: str,
                     herkunft: Optional[dict] = None) -> bool:
    """Gehoert dieser Konsoleneintrag der SEITE zur Last?

    `typ` und `text` sind `ConsoleMessage.type` und `.text`, `herkunft`
    ist `ConsoleMessage.location` (ein dict mit "url"). Es zaehlen nur
    die Typen aus `ZAEHLENDE_TYPEN`. Ein `pageerror` laeuft nicht hier
    durch - er zaehlt immer, siehe `konsole_sammeln`.
    """
    if typ not in ZAEHLENDE_TYPEN:
        return False
    return not _fremder_netzfehler(text, herkunft)


def konsole_sammeln(seite) -> list:
    """Haengt beide Fehlerkanaele an `seite` und gibt die Liste zurueck.

    Die Liste fuellt sich weiter, solange die Seite lebt - der Aufrufer
    liest sie nach seinen Klicks, nicht vorher.
    """
    fehler: list = []
    # Mit Kanalmarke: bei rotem Test ist sonst nicht zu sehen, ob die
    # Konsole gemeckert oder ob etwas GEWORFEN hat - und genau dieser
    # Unterschied ist der Grund, warum es diese Datei gibt.
    seite.on("console", lambda m: fehler.append(f"console: {m.text}")
             if ist_seitenfehler(m.type, m.text, m.location) else None)
    seite.on("pageerror", lambda e: fehler.append(f"pageerror: {e}"))
    return fehler
