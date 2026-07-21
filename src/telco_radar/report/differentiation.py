"""Weekly differentiation lens.

Which competitors launched NEW ways to differentiate *beyond price* this week -
consumer-facing external services and ecosystem / platform / super-app moves they
embed into their products (AI assistants, streaming, security, fintech, super-apps,
cloud, smart home, gaming, satellite direct-to-cell, loyalty). Grouped by
differentiation type, each with a best-in-class reference ("Vorbild") and an
inspiration angle for Vodafone ("Impuls").

Computed at render time from the weekly highlights (no LLM), same philosophy as
report/html.py:_stats. The classifier is deliberately PRECISION-first: it keys off
concrete consumer service/brand anchors and hard-excludes the network / B2B /
finance news that dominates the telco feed, so the page shows real product moves,
not infrastructure noise.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# Categories that are never consumer product differentiation.
NON_DIFF_CATEGORIES = {
    "Tarif/Pricing", "Verbal/Pricing", "Finanzen", "Regulierung", "Personal",
    "Sonstiges", "Strategie",
}

# Hard exclusions: network build-out, infrastructure, B2B/enterprise, corporate
# finance and pure network-ops. If any appears in title+summary, the item is not a
# consumer differentiation move, whatever else it matches.
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
    r"data analytics|multi-operator|\bm2m\b|constellation|automotive|agentic network|"
    r"connected vehicle|\bcapex\b|infrastructure upgrade|modernis",
    re.I,
)

# Each theme: key, label, colour, blurb, consumer ANCHORS (a term padded with
# spaces matches a whole token; bare term matches as substring / German compound),
# evergreen "vorbilder" and "impuls".
DIFF_THEMES = [
    {
        "key": "ki", "label": "KI & Assistenten", "color": "#7b3fe4",
        "blurb": "Premium-KI-Assistenten gratis im Tarif oder fest im Gerät.",
        "anchors": ["perplexity", "gemini", "chatgpt", "openai", "copilot",
                    "le chat", "mistral", " claude ", "ai assistant", "ai-assistent",
                    "ki-assistent", "ki assistent", "ai phone", "ai-phone",
                    "natural ai", " adot ", "ai translation", "translation feature",
                    "personal ai", "ai companion", "ai-companion", "sprachassistent",
                    "gen-ai assistant", "smart assistant"],
        "vorbilder": ["Telekom · AI Phone (Perplexity Pro gratis)",
                      "Free/Iliad · Le Chat Pro (Mistral) für alle",
                      "SoftBank · Perplexity + Natural AI Phone",
                      "Jio · Google Gemini gratis 18 Mon."],
        "impuls": "Vodafone hat TOBi als Service-Bot – aber keinen kostenlosen "
                  "Premium-KI-Assistenten als Tarif-Bonus. Ein 'Perplexity/Gemini/"
                  "Mistral gratis'-Bundle wäre ein sofort kopierbares Signal.",
    },
    {
        "key": "entertainment", "label": "Entertainment & Streaming", "color": "#e60000",
        "blurb": "Streaming, Sport- und TV-Rechte als Bindungsanker statt Einzel-Abo.",
        "anchors": ["netflix", "disney", "prime video", "amazon prime", "spotify",
                    "youtube premium", " dazn", "hbo max", "paramount", "apple tv",
                    "apple music", "viaplay", "crunchyroll", "fola play", "u-next",
                    "magentatv", "magenta tv", "tv rights", "tv-rechte", "sportrechte",
                    "world cup", "fifa", "champions league", "bundesliga",
                    "serie a", "free streaming", "streaming channel", "live-tv",
                    "pay-tv", "music streaming", "streaming-dienst", "streaming service",
                    "content bundle", "entertainment bundle", "sport-streaming"],
        "vorbilder": ["Telekom · MagentaTV-Aggregator (ein Interface)",
                      "Telia Play · alle Dienste in einer App",
                      "EE · Inclusive Extras (monatlich wechselbar)",
                      "Rakuten · U-NEXT-Tarif"],
        "impuls": "Vodafone bündelt Disney+/Prime/YouTube als Einzel-Add-ons. Nächster "
                  "Schritt: das Aggregator-Erlebnis – ein Interface über alle Dienste "
                  "plus eigene/exklusive Rechte statt loser Zusatzabos.",
    },
    {
        "key": "security", "label": "Security & Vertrauen", "color": "#2f8f5b",
        "blurb": "Schutz vor Betrug, Spam und Deepfakes – im Netz und per KI.",
        "anchors": ["secure net", "securenet", "norton", "mcafee", "f-secure",
                    " scam", "fraud detection", "betrugserkennung", "phishing",
                    "voice phishing", "anti-spam", "spam detection", "spam alert",
                    "antivirus", "cybersecure", "schutzpaket", "deepfake",
                    "identity protection", "identitätsschutz", "dark web",
                    "fake-anruf", "scam-schutz", "kinderschutz", "parental control",
                    "jugendschutz"],
        "vorbilder": ["Airtel · KI-Spam-/Betrugserkennung im Netz (gratis, auto-an)",
                      "KT · KI gegen Voice-Phishing/Deepfakes",
                      "Orange · Cybersecure (auch für Nicht-Kunden)",
                      "Telekom · Digital-Schutzpaket (ID & Betrug)"],
        "impuls": "Vodafone hat Secure Net. Trend: weg vom Geräte-Antivirus, hin zu "
                  "netz-/identitätsbasiertem Schutz plus KI-Betrugserkennung – ein "
                  "Vertrauens-Asset, das sich als Marke führen lässt.",
    },
    {
        "key": "fintech", "label": "Fintech & Payment", "color": "#c98a00",
        "blurb": "Wallet, Kredit, Versicherung und Banking direkt in der Telco-App.",
        "anchors": ["m-pesa", "mpesa", "vodapay", "paypay", "gcash", " maya ",
                    "paycell", " momo", "mobile money", "e-wallet", " wallet",
                    "digital bank", "payments bank", "paypal", " bnpl",
                    "buy now pay later", "microloan", "micro-loan", "micro-insurance",
                    "mikroversicherung", "digital wallet", "super-wallet",
                    "remittance", "geldbörse"],
        "vorbilder": ["Safaricom/Vodacom · M-Pesa & VodaPay (Mini-App-Marktplatz)",
                      "MTN · MoMo + Ant/Alipay-Mini-Apps",
                      "GCash / Maya · Telco-Fintech-Unicorns",
                      "Turkcell · Paycell"],
        "impuls": "Vodafone hat mit M-Pesa/VodaPay in Afrika das weltweit stärkste "
                  "Telco-Fintech. Impuls: das Mini-App-Marktplatz-Modell in die "
                  "europäischen Apps übertragen.",
    },
    {
        "key": "superapp", "label": "Super-App & Ökosystem", "color": "#3860be",
        "blurb": "Die Telco-App wird zur Alltags-Plattform mit Partner-Diensten.",
        "anchors": ["super app", "super-app", "superapp", "mini-app", "mini app",
                    "mini program", "mini-programm", "ayoba", "myjio", "mytelkomsel",
                    "max it", "one app", "oneapp", "everyday app", "capcut",
                    "video-editing", "content platform", "content-plattform",
                    "in-app", "rewards app", "lifestyle app", "digital hub",
                    "eingebaut in", "integriert die", "in die app", "into its app",
                    "in seine app", "app-ökosystem"],
        "vorbilder": ["Jio · MyJio-Suite",
                      "Turkcell · eigene Digital-Suite (BiP, fizy, TV+, Paycell)",
                      "M-Pesa · 221 Mini-Apps im Ökosystem",
                      "EE · offene EE-ID als Alltags-Gateway",
                      "Orange · Max it (MEA)"],
        "impuls": "MeinVodafone könnte von der Selfcare-App zur Alltags-Plattform "
                  "werden: offene Login-ID, Mini-Apps von Partnern, Services weit "
                  "über den Tarif hinaus.",
    },
    {
        "key": "cloud", "label": "Cloud & Speicher", "color": "#0d9488",
        "blurb": "Kostenloser, oft datensouveräner Cloud-Speicher als Tarif-Extra.",
        "anchors": ["google one", "icloud", "cloud storage", "cloud-speicher",
                    "free storage", "gratis speicher", "fotospeicher", "photo storage",
                    "rakuten drive", "personal cloud", "mycloud", "onedrive bundle",
                    "backup-speicher", "gb gratis", "tb gratis"],
        "vorbilder": ["Rakuten · 50 GB gratis (Rakuten Drive)", "Jio · AI-Cloud gratis",
                      "Swisscom · myCloud (Schweiz-gehostet)", "O2 Spanien · Cloud bis 10 TB"],
        "impuls": "Datensouveräner Cloud-Speicher (EU-gehostet) als kostenloses "
                  "Tarif-Extra – zugleich Vertrauens- und Bindungsanker.",
    },
    {
        "key": "smarthome", "label": "Smart Home & IoT", "color": "#b5551d",
        "blurb": "Sicherheit und Steuerung fürs Zuhause am Router-Anschluss.",
        "anchors": ["smart home", "smarthome", "smart-home", "magenta home",
                    "home security", "überwachungskamera", "smart lock", "türschloss",
                    "thermostat", "connected home", "haussteuerung", "smart wifi",
                    "hausautomation", "smart-home-paket", "alarmanlage"],
        "vorbilder": ["Telekom · Magenta Home (eine App)",
                      "au · au HOME (Kamera, Schloss, Notruf)",
                      "Movistar · Prosegur-Alarm + Digitalschutz", "e& · Smart Home"],
        "impuls": "Smart-Home/-Security als margenstarke Zusatzwelt am Router – "
                  "bindet den ganzen Haushalt an die Vodafone-Konnektivität.",
    },
    {
        "key": "gaming", "label": "Gaming", "color": "#c2185b",
        "blurb": "Cloud-Gaming als sichtbarer Beweis fürs 5G-Netz.",
        "anchors": ["game pass", "gamepass", "geforce now", "cloud gaming",
                    "cloud-gaming", " xbox", "playstation", " ps5", "esports",
                    "e-sports", "spiele-abo", "gaming-plattform", "gameloft",
                    "gaming bundle", "gaming-bundle", "spieleplattform"],
        "vorbilder": ["Telekom · 5G+ Gaming mit GeForce NOW",
                      "EE · Game Pass & Cloud-Gaming-Bundles",
                      "SKT · Xbox Game Pass in T Universe", "MTN · MTN Arcade"],
        "impuls": "Cloud-Gaming beweist niedrige Latenz und Slicing – als Bundle "
                  "(GeForce NOW / Game Pass) statt eigener Plattform.",
    },
    {
        "key": "satellite", "label": "Satellit & Direct-to-Cell", "color": "#5a6b9e",
        "blurb": "Direktverbindung Satellit-zu-Handy – 'nie mehr kein Netz'.",
        "anchors": ["direct-to-cell", "direct to cell", "direct-to-device",
                    "direct to device", " d2c", " d2d", " dtc ", "starlink direct",
                    "starlink", "satellite-to-phone", "text via satellite",
                    "satellite messaging", "spacemobile", "ast spacemobile",
                    "amazon leo", "amazon kuiper", "satelliten-handy",
                    "satelliten-direktverbindung", "sats-to-phone"],
        "vorbilder": ["au · Starlink Direct (gratis für Kunden)",
                      "Vodafone · AST SpaceMobile (Welt-Erst-5G aus dem All)",
                      "T-Mobile US · T-Satellite (Starlink)"],
        "impuls": "Vodafone ist mit AST SpaceMobile technisch vorn. Impuls: "
                  "Vermarktung – Direct-to-Cell als sichtbares 'immer erreichbar'-"
                  "Versprechen positionieren.",
    },
    {
        "key": "loyalty", "label": "Loyalty & Perks", "color": "#ac1811",
        "blurb": "Erlebnis-Perks und Presales, die App-Öffnungen zur Gewohnheit machen.",
        "anchors": ["veryme", "magenta moments", "o2 priority", " priority ",
                    "rewards program", "treueprogramm", "loyalty program", "payback",
                    "tuesdays", "bonga", "cashback", "erlebnis-perks", "presale",
                    "vorteilsprogramm", "bonusprogramm", "kundenvorteil", "reward-app"],
        "vorbilder": ["O2 UK · Priority (Presales, tägliche Perks)",
                      "Telekom · Magenta Moments",
                      "KPN · Voor Jou (wöchentliche Überraschungen)",
                      "Vodafone · VeryMe (schon starke Basis)"],
        "impuls": "Vodafone hat mit VeryMe eine gute Basis. Von O2 Priority lernen: "
                  "exklusive Presales und tägliche, lokale Erlebnis-Perks.",
    },
    {
        "key": "health", "label": "Health & Wellbeing", "color": "#2b7a9e",
        "blurb": "Telemedizin und Wellbeing als Differenzierung mit Nutzenversprechen.",
        "anchors": ["telehealth", "telemedizin", "gesundheits-app", "gesundheitsapp",
                    "konsultamd", "d healthcare", "healthcare app", "wellbeing",
                    " calm ", "mental health app", "digital health app",
                    "fitness-abo", "gesundheitsdienst"],
        "vorbilder": ["Docomo · d Healthcare (Punkte für Schritte)",
                      "Globe · KonsultaMD (Telemedizin)"],
        "impuls": "Gesundheits-Services (Telemedizin, Wellbeing) als Differenzierung "
                  "mit gesellschaftlichem Nutzen – in Wachstumsmärkten erprobt.",
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


def build_differentiation(highlights: list[dict]) -> dict:
    """Classify this week's highlights into differentiation themes (precision-first)."""
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
        # Consumer differentiation is rarely tagged "Netz/Technologie" by the
        # analyst - except satellite direct-to-cell. Drop network-tech items that
        # land in any other theme (they are infrastructure, not a product move).
        if cat == "Netz/Technologie" and best != "satellite":
            continue
        theme = _THEME_BY_KEY[best]
        moves_by_theme[best].append({
            "op": hl.get("operator") or hl.get("source_label") or _domain(hl.get("url")),
            "title": hl.get("title"), "summary": hl.get("summary"),
            "why": hl.get("why_it_matters"), "url": hl.get("url"),
            "region": hl.get("region"), "date": hl.get("date"),
            "cat": cat, "rel": hl.get("relevance") or 0,
            "domain": _domain(hl.get("url")), "color": theme["color"],
            "theme_label": theme["label"],
        })
        total += 1

    themes = []
    for t in DIFF_THEMES:
        mv = sorted(moves_by_theme[t["key"]], key=lambda m: (-m["rel"], m["op"] or ""))
        themes.append({**{k: t[k] for k in
                          ("key", "label", "color", "blurb", "vorbilder", "impuls")},
                       "moves": mv, "n": len(mv)})

    active = sorted([t for t in themes if t["n"]], key=lambda t: (-t["n"], _ORDER[t["key"]]))
    quiet = [t for t in themes if not t["n"]]
    top = sorted([m for t in active for m in t["moves"]], key=lambda m: -m["rel"])[:3]
    return {"total": total, "n_active": len(active),
            "themes": themes, "active": active, "quiet": quiet, "top": top}
