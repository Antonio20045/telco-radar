"""Tarifwelt (Saturn/MediaMarkt): welches Katalogmodell zu welcher Seite in
https://tarife.mediamarkt.de/sitemap.xml gehoert (Stand 08.11.2026 fuer die
ersten 18 Eintraege, 13.11.2026 fuer die uebrigen). Seiten mit "-aktion" oder
"-online-bonus" sind Aktionen und stehen nie darin. Ausgelagert aus
`tarifwelt_lauf.py`, weil die Zuordnungstabelle allein schon lang ist.

Tupel: (Hersteller, Katalogname, Pfadsegment der Basisseite, Slug[,
api_name]). `api_name` (optional, fuenftes Feld) ist der Name, den die
Schnittstelle fuer DIESES Geraet zurueckgibt (`tarifwelt_pruefung.pruefe`
vergleicht ihn mit `geraet_name` der Antwort); er fehlt, wenn er mit dem
Katalognamen uebereinstimmt. Mehrere Xiaomi- und das Honor-Modell tragen in
der Antwort einen anderen Namen als der Katalog (ohne Marke oder mit
"5G"-Zusatz, siehe
docs/belege/tarifwelt-modelle-1313/uebersicht-neue-modelle-2026-11-13.json).
Die `device_id` entsteht in `tarifwelt_lauf.lies_modell` weiterhin aus dem
Katalognamen (zweites Feld), nur der Antwortvergleich nutzt `api_name`.

Die ersten 18 Eintraege sind die Pflichtmodelle
(`config/geraete_abdeckung.yaml:pflicht_modelle_wenn_aktiv`, Test:
`tests/test_abdeckung_haendler_modelle.py`). Baupaket P6
(13.11.2026, Analyse "analyse-abdeckung-1313.md") deckte auf, dass dieser
Leser bis dahin die restlichen 71 der 89 Katalogmodelle fuer Saturn/
MediaMarkt nie versuchte - unabhaengig davon, ob die Tarifwelt sie fuehrt.
Nachmessung am Original (Methodik und Rohdaten in
docs/belege/tarifwelt-modelle-1313/README.md): die Sitemap fuehrt nur
aktuelle Smartphones (Sortimentsaussage, keine Messluecke fuer die Modelle,
die dort fehlen); die folgenden 20 Modelle stehen dort und lieferten
mindestens eine lieferbare Variante - sie stehen hier zusaetzlich, bewusst
NICHT in `pflicht_modelle_wenn_aktiv` (sonst CI-Gate fuer alle anderen
Netzbetreiber ueber `pflicht_modelle`). Acht weitere Modelle lieferte die
Sitemap zwar, aber jede Variante war `available: false` ("nicht lieferbar",
keine Sortimentsaussage) - sie bleiben hier draussen und stehen nur als
belegte Luecke in `config/geraete_abdeckung.yaml`.
"""

from __future__ import annotations

ModellEintrag = tuple[str, str, str, str] | tuple[str, str, str, str, str]

MODELL_SLUGS: dict[str, ModellEintrag] = {
    "apple-iphone-18-pro": ("Apple", "iPhone 18 Pro", "apple", "iphone-18-pro"),
    "apple-iphone-18-pro-max": (
        "Apple",
        "iPhone 18 Pro Max",
        "apple",
        "iphone-18-pro-max",
    ),
    "apple-iphone-17": ("Apple", "iPhone 17", "apple", "iphone-17"),
    "apple-iphone-17-pro": ("Apple", "iPhone 17 Pro", "apple", "iphone-17-pro"),
    "apple-iphone-17-pro-max": (
        "Apple",
        "iPhone 17 Pro Max",
        "apple",
        "iphone-17-pro-max",
    ),
    "apple-iphone-17e": ("Apple", "iPhone 17e", "apple", "iphone-17e"),
    "apple-iphone-duo": ("Apple", "iPhone Duo", "apple", "iphone-duo"),
    "apple-iphone-air": ("Apple", "iPhone Air", "apple", "iphone-air"),
    "samsung-galaxy-s26": ("Samsung", "Galaxy S26", "samsung", "galaxy-s26"),
    "samsung-galaxy-s26-plus": (
        "Samsung",
        "Galaxy S26 Plus",
        "samsung",
        "galaxy-s26-plus",
    ),
    "samsung-galaxy-s26-ultra": (
        "Samsung",
        "Galaxy S26 Ultra",
        "samsung",
        "galaxy-s26-ultra",
    ),
    "samsung-galaxy-z-fold8": (
        "Samsung",
        "Galaxy Z Fold8",
        "samsung",
        "galaxy-z-fold-8",
    ),
    "samsung-galaxy-z-flip8": (
        "Samsung",
        "Galaxy Z Flip8",
        "samsung",
        "galaxy-z-flip-8",
    ),
    "samsung-galaxy-a57": ("Samsung", "Galaxy A57", "samsung", "galaxy-a57"),
    "google-pixel-11": ("Google", "Pixel 11", "google", "pixel-11"),
    "google-pixel-11-pro": ("Google", "Pixel 11 Pro", "google", "pixel-11-pro"),
    "google-pixel-11-pro-xl": (
        "Google",
        "Pixel 11 Pro XL",
        "google",
        "pixel-11-pro-xl",
    ),
    "google-pixel-10a": ("Google", "Pixel 10a", "google", "pixel-10a"),
    "google-pixel-10": ("Google", "Pixel 10", "google", "pixel-10"),
    "google-pixel-10-pro-xl": (
        "Google",
        "Pixel 10 Pro XL",
        "google",
        "pixel-10-pro-xl",
    ),
    "samsung-galaxy-a37": (
        "Samsung",
        "Galaxy A37",
        "samsung",
        "galaxy-a37",
        "Galaxy A37 5G",
    ),
    "samsung-galaxy-s25": ("Samsung", "Galaxy S25", "samsung", "galaxy-s25"),
    "samsung-galaxy-s25-fe": (
        "Samsung",
        "Galaxy S25 FE",
        "samsung",
        "galaxy-s25-fe",
    ),
    "samsung-galaxy-s25-ultra": (
        "Samsung",
        "Galaxy S25 Ultra",
        "samsung",
        "galaxy-s25-ultra",
    ),
    "samsung-galaxy-s26-fe": (
        "Samsung",
        "Galaxy S26 FE",
        "samsung",
        "galaxy-s26-fe",
    ),
    "samsung-galaxy-z-fold8-ultra": (
        "Samsung",
        "Galaxy Z Fold8 Ultra",
        "samsung",
        "galaxy-z-fold-8-ultra",
    ),
    "honor-600": ("HONOR", "HONOR 600", "honor", "600", "600"),
    "honor-magic8-lite": (
        "HONOR",
        "HONOR Magic8 Lite",
        "honor",
        "magic-8-lite",
        "Magic 8 Lite",
    ),
    "xiaomi-17": ("Xiaomi", "Xiaomi 17", "xiaomi", "17", "17"),
    "xiaomi-17-ultra": (
        "Xiaomi",
        "Xiaomi 17 Ultra",
        "xiaomi",
        "17-ultra",
        "17 Ultra",
    ),
    "xiaomi-17t": ("Xiaomi", "Xiaomi 17T", "xiaomi", "17t", "17T"),
    "xiaomi-17t-pro": ("Xiaomi", "Xiaomi 17T Pro", "xiaomi", "17t-pro", "17T Pro"),
    "xiaomi-redmi-17": ("Xiaomi", "Redmi 17", "xiaomi", "redmi-17"),
    "xiaomi-redmi-17c": (
        "Xiaomi",
        "Redmi 17C",
        "xiaomi",
        "redmi-17-c-5g",
        "Redmi 17C 5G",
    ),
    "xiaomi-redmi-note-15-pro-plus": (
        "Xiaomi",
        "Redmi Note 15 Pro Plus",
        "xiaomi",
        "redmi-note-15-pro-plus-5g",
        "Redmi Note 15 Pro+ 5G",
    ),
    "xiaomi-redmi-note-17": (
        "Xiaomi",
        "Redmi Note 17",
        "xiaomi",
        "redmi-note-17",
    ),
    "xiaomi-redmi-note-17-pro": (
        "Xiaomi",
        "Redmi Note 17 Pro",
        "xiaomi",
        "redmi-note-17-pro-5g",
        "Redmi Note 17 Pro 5G",
    ),
    "xiaomi-redmi-note-17-pro-max": (
        "Xiaomi",
        "Redmi Note 17 Pro Max",
        "xiaomi",
        "redmi-note-17-pro-max-5g",
        "Redmi Note 17 Pro Max 5G",
    ),
}
