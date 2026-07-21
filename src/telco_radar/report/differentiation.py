"""Wöchentlicher Differenzierungs-Radar.

Clustert die (bereits vom Analyse-Agenten bewerteten) Meldungen der letzten Wochen
nach Differenzierungs-Typ: neue, konsumentennahe Services und Ökosystem-Moves, mit
denen sich Wettbewerber JENSEITS DES PREISES abheben (KI-Assistenten, Streaming,
Security, Fintech, Super-App, Cloud, Smart Home, Gaming, Satellit/Direct-to-Cell,
Loyalty, Health). Preis-/Tarif-, Netz-/Infrastruktur- und B2B-Meldungen werden
konsequent ausgeschlossen.

Alles wird zur Render-Zeit in Python berechnet (kein LLM, gratis, lokal testbar) -
dieselbe Philosophie wie report/html.py:_stats. Angezeigt wird durchgehend Deutsch:
die Karten führen mit dem deutschen Meldungstext (dem vom Agenten verfassten
Summary), nicht mit dem fremdsprachigen Original-Titel.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# Kategorien, die nie konsumentennahe Produkt-Differenzierung sind.
NON_DIFF_CATEGORIES = {
    "Tarif/Pricing", "Verbal/Pricing", "Finanzen", "Regulierung", "Personal",
    "Sonstiges", "Strategie",
}

# Harte Ausschlüsse: Netzausbau, Infrastruktur, B2B/Enterprise, Konzernfinanzen,
# reiner Netzbetrieb. Taucht das in Titel+Summary auf, ist es kein Consumer-Move.
_EXCLUDE = re.compile(
    r"ai[- ]ran|open ran|o-ran|\bv-?ran\b|\bran\b|spectrum|backbone|subsea|"
    r"data cent(er|re)|ground station|network slicing|\bslicing\b|outage|"
    r"network operation|network performance|drive test|private network|"
    r"campus network|\btower(s)?\b|fib(er|re) rollout|capex|teleport|core network|"
    r"cell site|base station|quantum|\b6g\b|white paper|patching|greenfield|"
    r"zero trust|\bsase\b|enterprise|b2b|workforce|\bsme(s)?\b|\bsmb(s)?\b|"
    r"critical infrastructure|managed security|\bsoc\b|"
    r"\bipo\b|valuation|merger|acquisition|acquire|\bstake\b|fundrais|"
    r"\bshares\b|\bstock\b|earnings|\brevenue(s)?\b|\bprofit\b|subsidy|"
    r"billion|\bbn\b|\bm\&a\b|invests?\b|investment|raises\s|hires|"
    r"data analytics|multi-operator|\bm2m\b|constellation|automotive|"
    r"connected vehicle|agentic network|infrastructure upgrade|modernis",
    re.I,
)

# Jede Kategorie: key, Label, Farbe, Muster-Text (2 Sätze), Consumer-Anker,
# Vorbilder (Name + kurze deutsche Beschreibung, was sie konkret tun) und ein
# ausformulierter Impuls für Vodafone (bewusst im Wissen, was Vodafone schon hat).
DIFF_THEMES = [
    {
        "key": "ki", "label": "KI & Assistenten", "color": "#7b3fe4",
        "blurb": "Der große Differenzierungs-Trend 2025/26: Wettbewerber verschenken "
                 "eine kostenpflichtige Premium-KI oder bauen sie fest ins Gerät ein "
                 "und machen den KI-Assistenten zum sichtbaren Tarif-Vorteil.",
        "anchors": ["perplexity", "gemini", "chatgpt", "openai", "copilot",
                    "le chat", "mistral", " claude ", "ai assistant", "ai-assistent",
                    "ki-assistent", "ki assistent", "ai phone", "ai-phone",
                    "natural ai", " adot ", "ai translation", "translation feature",
                    "personal ai", "ai companion", "ai-companion", "sprachassistent",
                    "gen-ai assistant", "smart assistant"],
        "vorbilder": [
            {"name": "Telekom · AI Phone", "desc": "gibt jedem Tarifkunden 18 Monate Perplexity Pro gratis – KI fest im Smartphone, eigener Magenta-Knopf."},
            {"name": "Free/Iliad (FR) · Le Chat Pro", "desc": "schenkt allen ~15 Mio. Mobilfunkkunden 12 Monate Mistrals Premium-KI (Thema europäische KI-Souveränität)."},
            {"name": "SoftBank (JP) · Perplexity + Natural AI Phone", "desc": "1 Jahr Perplexity Pro gratis plus ein exklusives, KI-natives Smartphone."},
            {"name": "Jio (IN) · Google Gemini", "desc": "18 Monate Gemini AI Pro + 2 TB Cloud gratis zum 5G-Tarif."},
        ],
        "impuls": "Vodafone hat mit TOBi zwar einen Service-Chatbot, aber keinen "
                  "kostenlosen Premium-KI-Assistenten als Tarif-Bonus. Ein klar "
                  "sichtbares „Perplexity/Gemini/Mistral gratis\"-Bundle wäre ein "
                  "sofort verständliches Differenzierungssignal – technisch andockbar "
                  "an die bestehende Microsoft-/Azure-Partnerschaft.",
    },
    {
        "key": "entertainment", "label": "Entertainment & Streaming", "color": "#e60000",
        "blurb": "Streaming, Sport- und TV-Rechte sind der klassische Bindungsanker. "
                 "Der nächste Schritt der Besten ist nicht „noch ein Abo\", sondern ein "
                 "Aggregator-Erlebnis: alle Dienste in einer Oberfläche.",
        "anchors": ["netflix", "disney", "prime video", "amazon prime", "spotify",
                    "youtube premium", " dazn", "hbo max", "paramount", "apple tv",
                    "apple music", "viaplay", "crunchyroll", "fola play", "u-next",
                    "magentatv", "magenta tv", "tv rights", "tv-rechte", "sportrechte",
                    "world cup", "fifa", "champions league", "bundesliga",
                    "serie a", "free streaming", "streaming channel", "live-tv",
                    "pay-tv", "music streaming", "streaming-dienst", "streaming service",
                    "content bundle", "entertainment bundle", "sport-streaming"],
        "vorbilder": [
            {"name": "Telekom · MagentaTV", "desc": "ein Interface und eine Fernbedienung über lineares TV und alle Streaming-Apps (Netflix, Disney+, RTL+ …)."},
            {"name": "Telia (Nordics) · Telia Play", "desc": "bündelt Netflix, Disney+, HBO Max, Viaplay & Sportrechte in EINER durchsuchbaren App."},
            {"name": "EE (UK) · Inclusive Extras", "desc": "ein wählbarer Premium-Dienst pro Monat (Netflix, Apple One, Game Pass …), alle 30 Tage tauschbar."},
            {"name": "Deutsche Telekom · WM-Rechte", "desc": "exklusive Sportrechte als Neukunden-Turbo (jüngst die FIFA-WM 2030 für Deutschland)."},
        ],
        "impuls": "Vodafone bündelt Disney+/Prime/YouTube heute als lose Einzel-"
                  "Add-ons. Der Hebel ist das Aggregator-Erlebnis (eine Oberfläche "
                  "über alle Dienste) plus punktuell eigene/exklusive Rechte, statt "
                  "beliebig austauschbarer Zusatzabos.",
    },
    {
        "key": "security", "label": "Security & Vertrauen", "color": "#2f8f5b",
        "blurb": "Schutz vor Betrug, Spam und Deepfakes wird vom Antivirus-Add-on zum "
                 "Marken-Asset. Die Vorreiter verlagern ihn ins Netz und machen ihn "
                 "kostenlos und automatisch aktiv.",
        "anchors": ["secure net", "securenet", "norton", "mcafee", "f-secure",
                    " scam", "fraud detection", "betrugserkennung", "phishing",
                    "voice phishing", "anti-spam", "spam detection", "spam alert",
                    "antivirus", "cybersecure", "schutzpaket", "deepfake",
                    "identity protection", "identitätsschutz", "dark web",
                    "fake-anruf", "scam-schutz", "kinderschutz", "parental control",
                    "jugendschutz"],
        "vorbilder": [
            {"name": "Airtel (IN) · KI-Spam-/Betrugserkennung", "desc": "erkennt Spam- und Betrugsanrufe direkt im Netz – gratis und automatisch für alle Kunden aktiv."},
            {"name": "KT (KR) · Voice-Phishing-KI", "desc": "erkennt KI-generierte Fake-Stimmen (Deepfakes) am Telefon in Echtzeit."},
            {"name": "Orange (FR) · Cybersecure", "desc": "Schutzdienst, den sogar Nicht-Kunden nutzen können – Vertrauens-Positionierung über die Marke."},
            {"name": "Telekom · Digital-Schutzpaket", "desc": "geht über Antivirus hinaus: ID-/Darkweb-Monitoring, Betrugsabsicherung, Hilfe bei Cybermobbing."},
        ],
        "impuls": "Vodafone hat mit Secure Net eine Basis. Der Trend geht weg vom "
                  "Geräte-Antivirus hin zu netz- und identitätsbasiertem Schutz plus "
                  "KI-Betrugserkennung – ein Vertrauens-Thema, das sich als eigenes "
                  "Markenversprechen führen und bepreisen lässt.",
    },
    {
        "key": "fintech", "label": "Fintech & Payment", "color": "#c98a00",
        "blurb": "Wallet, Kredit, Versicherung und Banking direkt in der Telco-App. In "
                 "Wachstumsmärkten sind daraus die stärksten Ökosysteme überhaupt "
                 "geworden – mit Mini-App-Marktplätzen obendrauf.",
        "anchors": ["m-pesa", "mpesa", "vodapay", "paypay", "gcash", " maya ",
                    "paycell", " momo", "mobile money", "e-wallet", " wallet",
                    "digital bank", "payments bank", "paypal", " bnpl",
                    "buy now pay later", "microloan", "micro-loan", "micro-insurance",
                    "mikroversicherung", "digital wallet", "super-wallet",
                    "remittance", "geldbörse"],
        "vorbilder": [
            {"name": "Safaricom/Vodacom · M-Pesa & VodaPay", "desc": "Afrikas führendes Telco-Fintech – vom Wallet zum Super-App mit über 220 Mini-Apps (eigene Vodafone-Familie!)."},
            {"name": "MTN (Afrika) · MoMo", "desc": "Fintech-Wallet, das per Alipay-Partnerschaft zum Mini-App-Marktplatz ausgebaut wird."},
            {"name": "GCash / Maya (PH)", "desc": "aus Telcos entstandene Fintech-Unicorns – Wallet, Sparen, Kredit, digitale Bank."},
            {"name": "Turkcell (TR) · Paycell", "desc": "eigenes Bezahlsystem als Teil der hauseigenen Digital-Suite."},
        ],
        "impuls": "Vodafone besitzt mit M-Pesa/VodaPay das weltweit stärkste Telco-"
                  "Fintech – nur eben in Afrika. Der Impuls: das erprobte Mini-App-"
                  "Marktplatz-Modell schrittweise auf die europäischen Vodafone-Apps "
                  "übertragen, statt es als reines Afrika-Thema zu sehen.",
    },
    {
        "key": "superapp", "label": "Super-App & Ökosystem", "color": "#3860be",
        "blurb": "Die Telco-App wird von der Selfcare-App zur Alltags-Plattform mit "
                 "eingebauten Partner-Diensten. Ziel ist tägliche Nutzung statt „nur "
                 "aufladen und abmelden\".",
        "anchors": ["super app", "super-app", "superapp", "mini-app", "mini app",
                    "mini program", "mini-programm", "ayoba", "myjio", "mytelkomsel",
                    "max it", "one app", "oneapp", "everyday app", "capcut",
                    "video-editing", "content platform", "content-plattform",
                    "in-app", "rewards app", "lifestyle app", "digital hub",
                    "eingebaut in", "integriert die", "in die app", "into its app",
                    "in seine app", "app-ökosystem"],
        "vorbilder": [
            {"name": "Jio (IN) · MyJio", "desc": "eine App als Zugang zu einer ganzen Suite: Streaming, Musik, Shopping, Zahlung, Cloud, Games."},
            {"name": "Turkcell (TR)", "desc": "hat eine komplette eigene Digital-Suite gebaut (BiP-Messenger, fizy-Musik, TV+, Lifebox-Cloud, Paycell)."},
            {"name": "EE (UK) · EE-ID", "desc": "offene Login-ID – auch für Nicht-Kunden – als Tor zu Shop, Gaming, Versicherung; „mehr als ein Netz\"."},
            {"name": "Orange · Max it (MEA)", "desc": "Super-App mit Konto, Orange Money, Shopping, Musik, TV und Ticketing in einem."},
        ],
        "impuls": "MeinVodafone könnte von der reinen Selfcare-App zur Alltags-"
                  "Plattform werden: offene Login-ID, Mini-Apps von Partnern und "
                  "Services deutlich über den Tarif hinaus – der klarste „Telco → "
                  "Everyday-App\"-Weg, den EE und Orange gerade vormachen.",
    },
    {
        "key": "cloud", "label": "Cloud & Speicher", "color": "#0d9488",
        "blurb": "Kostenloser, oft datensouveräner Cloud-Speicher als Tarif-Extra – "
                 "günstig in der Herstellung, aber ein guter Bindungs- und "
                 "Vertrauensanker.",
        "anchors": ["google one", "icloud", "cloud storage", "cloud-speicher",
                    "free storage", "gratis speicher", "fotospeicher", "photo storage",
                    "rakuten drive", "personal cloud", "mycloud", "onedrive bundle",
                    "backup-speicher", "gb gratis", "tb gratis"],
        "vorbilder": [
            {"name": "Rakuten (JP) · Rakuten Drive", "desc": "50 GB Cloud-Speicher gratis zum Tarif."},
            {"name": "Jio (IN) · AI-Cloud", "desc": "großzügiger Gratis-Speicher als Teil des 5G-Angebots."},
            {"name": "Swisscom (CH) · myCloud", "desc": "Schweiz-gehosteter Speicher – Datensouveränität als Verkaufsargument."},
            {"name": "O2 (ES) · Cloud", "desc": "Gratis-Speicher für Mobilfunkkunden, jüngst bis 10 TB ausgebaut."},
        ],
        "impuls": "Ein EU-gehosteter Gratis-Cloud-Speicher als Tarif-Extra wäre "
                  "zugleich Vertrauens- und Bindungsanker – gerade im deutschen "
                  "Markt ein glaubwürdiges Datenschutz-Argument.",
    },
    {
        "key": "smarthome", "label": "Smart Home & IoT", "color": "#b5551d",
        "blurb": "Sicherheit und Steuerung fürs Zuhause am Router-Anschluss – eine "
                 "margenstarke Zusatzwelt, die den ganzen Haushalt bindet.",
        "anchors": ["smart home", "smarthome", "smart-home", "magenta home",
                    "home security", "überwachungskamera", "smart lock", "türschloss",
                    "thermostat", "connected home", "haussteuerung", "smart wifi",
                    "hausautomation", "smart-home-paket", "alarmanlage"],
        "vorbilder": [
            {"name": "Telekom · Magenta Home", "desc": "vereinheitlichte Smart-Home-App mit Routinen (Einbruchsalarm, Anwesenheits-Simulation, Heizung)."},
            {"name": "au (JP) · au HOME", "desc": "Kamera, smartes Türschloss, Sensoren und Notruf-Dienst am Anschluss."},
            {"name": "Movistar (ES)", "desc": "Alarmanlage (Prosegur-JV) plus digitaler Schutz aus einer Hand."},
            {"name": "e& (VAE) · Smart Home", "desc": "Überwachung und Gerätesteuerung gebündelt mit dem Heim-Internet."},
        ],
        "impuls": "Smart-Home/-Security als Zusatzwelt am Vodafone-Router bindet den "
                  "Haushalt langfristig an die Vodafone-Konnektivität – margenstark "
                  "und gut mit Kabel/Glasfaser kombinierbar.",
    },
    {
        "key": "gaming", "label": "Gaming", "color": "#c2185b",
        "blurb": "Cloud-Gaming ist der sichtbarste Beweis fürs 5G-Netz: niedrige "
                 "Latenz und Network-Slicing werden zum Erlebnis statt zur Technik-"
                 "Folie.",
        "anchors": ["game pass", "gamepass", "geforce now", "cloud gaming",
                    "cloud-gaming", " xbox", "playstation", " ps5", "esports",
                    "e-sports", "spiele-abo", "gaming-plattform", "gameloft",
                    "gaming bundle", "gaming-bundle", "spieleplattform"],
        "vorbilder": [
            {"name": "Telekom · 5G+ Gaming", "desc": "GeForce NOW gebündelt, vermarktet über 5G-SA, Slicing und niedrige Latenz."},
            {"name": "EE (UK)", "desc": "Game Pass als wählbares Extra plus Cloud-Gaming-Bundles mit Hardware."},
            {"name": "SK Telecom (KR)", "desc": "Xbox Game Pass fest im Abo-Marktplatz T Universe."},
            {"name": "MTN (Afrika) · Arcade", "desc": "Gaming-Abo mit Premium-Titeln zum kleinen Tagespreis."},
        ],
        "impuls": "Cloud-Gaming als Bundle (GeForce NOW / Game Pass) statt eigener "
                  "Plattform – ein kostengünstiger, glaubwürdiger Beweis für die "
                  "Qualität des Vodafone-5G-Netzes.",
    },
    {
        "key": "satellite", "label": "Satellit & Direct-to-Cell", "color": "#5a6b9e",
        "blurb": "Die Direktverbindung Satellit-zu-Handy ist gerade das heißeste "
                 "Netz-Differenzierungsthema: „nie mehr kein Netz\", ganz ohne "
                 "Spezialgerät.",
        "anchors": ["direct-to-cell", "direct to cell", "direct-to-device",
                    "direct to device", " d2c", " d2d", " dtc ", "starlink direct",
                    "starlink", "satellite-to-phone", "text via satellite",
                    "satellite messaging", "spacemobile", "ast spacemobile",
                    "amazon leo", "amazon kuiper", "satelliten-handy",
                    "satelliten-direktverbindung", "sats-to-phone"],
        "vorbilder": [
            {"name": "au (JP) · Starlink Direct", "desc": "Satellit-zu-Handy, für Bestandskunden gratis – erreicht Gebiete ohne Mobilfunk."},
            {"name": "Vodafone · AST SpaceMobile", "desc": "hat den weltweit ersten 5G-Handy-Anruf aus dem All gemacht – Vodafone ist hier technisch vorn."},
            {"name": "T-Mobile US · T-Satellite", "desc": "Direct-to-Cell über Starlink, aggressiv als Abdeckungs-Vorteil vermarktet."},
        ],
        "impuls": "Vodafone ist mit AST SpaceMobile technologisch vorn – die Chance "
                  "liegt in der Vermarktung: Direct-to-Cell als sichtbares „immer "
                  "erreichbar\"-Versprechen für Wandern, Notfälle und Funklöcher "
                  "positionieren, bevor es die Wettbewerber besetzen.",
    },
    {
        "key": "loyalty", "label": "Loyalty & Perks", "color": "#ac1811",
        "blurb": "Erlebnis-Perks und exklusive Vorverkäufe machen das tägliche "
                 "App-Öffnen zur Gewohnheit – Bindung über Nutzen statt über den "
                 "Vertrag.",
        "anchors": ["veryme", "magenta moments", "o2 priority", " priority ",
                    "rewards program", "treueprogramm", "loyalty program", "payback",
                    "tuesdays", "bonga", "cashback", "erlebnis-perks", "presale",
                    "vorteilsprogramm", "bonusprogramm", "kundenvorteil", "reward-app"],
        "vorbilder": [
            {"name": "O2 (UK) · Priority", "desc": "Goldstandard: Ticket-Vorverkäufe und tägliche, lokale Erlebnis-Perks (Kaffee, Kino …)."},
            {"name": "Telekom · Magenta Moments", "desc": "täglich wechselnde Vorteile, Streaming-Trials, Konzert-Presales in der App."},
            {"name": "KPN (NL) · Voor Jou", "desc": "wöchentliche Überraschungen (Event-Tickets, Partner-Perks) als fester App-Anlass."},
            {"name": "Vodafone · VeryMe", "desc": "bereits eine starke Basis – der Ausbau Richtung Erlebnis/Presales fehlt noch."},
        ],
        "impuls": "Vodafone hat mit VeryMe eine gute Grundlage. Von O2 Priority "
                  "lernen: exklusive Presales und tägliche, lokale Erlebnis-Perks, "
                  "die einen echten Grund geben, die App täglich zu öffnen.",
    },
    {
        "key": "health", "label": "Health & Wellbeing", "color": "#2b7a9e",
        "blurb": "Telemedizin und Wellbeing als Differenzierung mit gesellschaftlichem "
                 "Nutzen – in Wachstumsmärkten bereits erfolgreich erprobt.",
        "anchors": ["telehealth", "telemedizin", "gesundheits-app", "gesundheitsapp",
                    "konsultamd", "d healthcare", "healthcare app", "wellbeing",
                    " calm ", "mental health app", "digital health app",
                    "fitness-abo", "gesundheitsdienst"],
        "vorbilder": [
            {"name": "NTT Docomo (JP) · d Healthcare", "desc": "belohnt tägliche Gesundheits-Missionen (Schritte, Blutdruck) mit Punkten – 18 Mio.+ Nutzer."},
            {"name": "Globe (PH) · KonsultaMD", "desc": "Telemedizin-Dienst mit über 1 Mio. Nutzern, gebündelt ins Telco-Ökosystem."},
        ],
        "impuls": "Gesundheits-Services (Telemedizin, Wellbeing) als Differenzierung "
                  "mit klarem Nutzenversprechen – ein Feld mit Wachstum, das in "
                  "anderen Märkten schon Kunden bindet.",
    },
]

_THEME_BY_KEY = {t["key"]: t for t in DIFF_THEMES}
_ORDER = {t["key"]: i for i, t in enumerate(DIFF_THEMES)}


def _norm_tokens(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9äöüß]+", " ", text.lower()).strip() + " "


def _score(text: str) -> dict:
    raw = " " + " ".join(text.lower().split()) + " "
    tok = _norm_tokens(text)
    scores: dict[str, int] = {}
    for theme in DIFF_THEMES:
        n = 0
        for a in theme["anchors"]:
            if a.startswith(" ") or a.endswith(" "):
                if a in tok:
                    n += 1
            elif a in raw:
                n += 1
        if n:
            scores[theme["key"]] = n
    return scores


def _domain(url: str) -> str:
    return urlsplit(url or "").netloc.removeprefix("www.")


def _split_first(text: str) -> tuple[str, str]:
    """Ersten Satz als Headline, Rest als Fließtext (beides deutsch aus dem Summary)."""
    t = " ".join((text or "").split())
    if not t:
        return "", ""
    for sep in (". ", "! ", "? "):
        k = t.find(sep)
        if 8 < k < 160:
            return t[:k + 1], t[k + 2:]
    return t, ""


def build_differentiation(highlights: list[dict]) -> dict:
    """Klassifiziert Highlights (mehrerer Wochen) nach Differenzierungs-Typ.

    `highlights` sind die geflachten Highlight-Dicts aus html._flatten. Rückgabe:
    Struktur für die Seite „Differenzierung" und den Dashboard-Teaser. Deduped nach
    URL, sortiert nach Datum (neueste zuerst)."""
    moves_by_theme: dict[str, list] = {t["key"]: [] for t in DIFF_THEMES}
    seen: set[str] = set()
    total = 0
    for hl in highlights or []:
        cat = (hl.get("category") or "").strip()
        if cat in NON_DIFF_CATEGORIES:
            continue
        text = f"{hl.get('title','')} {hl.get('summary','')}"
        if _EXCLUDE.search(text):
            continue
        scores = _score(text)
        if not scores:
            continue
        key = (hl.get("url") or hl.get("title") or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        best = sorted(scores.items(), key=lambda kv: (-kv[1], _ORDER[kv[0]]))[0][0]
        theme = _THEME_BY_KEY[best]
        head, rest = _split_first(hl.get("summary") or "")
        de_title = head or (hl.get("summary") or hl.get("title") or "")
        moves_by_theme[best].append({
            "op": hl.get("operator") or hl.get("source_label") or _domain(hl.get("url")),
            "de_title": de_title, "rest": rest,
            "summary": hl.get("summary"), "why": hl.get("why_it_matters"),
            "url": hl.get("url"), "region": hl.get("region"), "date": hl.get("date"),
            "cat": cat, "rel": hl.get("relevance") or 0,
            "domain": _domain(hl.get("url")), "color": theme["color"],
            "theme_label": theme["label"],
        })
        total += 1

    themes = []
    for t in DIFF_THEMES:
        mv = sorted(moves_by_theme[t["key"]],
                    key=lambda m: (m.get("date") or "", m["rel"]), reverse=True)
        themes.append({**{k: t[k] for k in
                          ("key", "label", "color", "blurb", "vorbilder", "impuls")},
                       "moves": mv, "n": len(mv)})

    active = sorted([t for t in themes if t["n"]], key=lambda t: (-t["n"], _ORDER[t["key"]]))
    quiet = [t for t in themes if not t["n"]]
    top = sorted([m for t in active for m in t["moves"]],
                 key=lambda m: (m.get("date") or "", m["rel"]), reverse=True)[:3]
    return {"total": total, "n_active": len(active),
            "themes": themes, "active": active, "quiet": quiet, "top": top}
