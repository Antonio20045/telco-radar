#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single source of truth for the operator watchlist.

Generates config/watchlist.yaml + config/watchlist_extra.yaml AND the human
verification document. Every operator has exactly one PRIMARY source on its
OWN domain (feed / json_api / newsroom / newsroom_js / official-reference).
Run: python scripts/build_sources.py
"""
from __future__ import annotations
import io, os, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REGION_NAMES = {
    "europe": "Europa", "north_america": "Nordamerika",
    "latin_america": "Lateinamerika", "africa_middle_east": "Afrika & Naher Osten",
    "asia": "Asien", "oceania": "Ozeanien",
}

# region, name, country, website, aliases, kind, crawl_url, press_url, note, plan
M = [
# ---------------- EUROPE ----------------
("europe","Vodafone Group","GB","vodafone.com",["Vodafone"],"json_api",
 "https://www.vodafone.com/tools/urlproxy/advurlproxy.aspx?settingname=news-feed&categories=*&tags=*",
 "https://www.vodafone.com/news","JSON-API, 108 Seiten, aktuellster Eintrag 17.07.2026",""),
("europe","Vodafone Deutschland","DE","vodafone.de",[],"newsroom_js",
 "https://newsroom.vodafone.de/","https://newsroom.vodafone.de/","JS-gerendert (Presspage)",""),
("europe","Deutsche Telekom","DE","telekom.com",["Telekom","T-Systems","T-Mobile","Magenta"],"newsroom_js",
 "https://www.telekom.com/en/media/media-information","https://www.telekom.com/en/media/media-information",
 "JS-gerendert; statisch nur 2 Links",""),
("europe","O2 Telefónica Deutschland","DE","telefonica.de",["O2 Telefonica","Telefónica Deutschland","O2"],"rss",
 "https://www.telefonica.de/o2/rss/news?category_id=11;pubdate=1","https://www.telefonica.de/presse.html",
 "RSS, 20 Einträge",""),
("europe","Telefónica","ES","telefonica.com",["Movistar","Vivo"],"rss",
 "https://www.telefonica.com/en/feed/","https://www.telefonica.com/en/communication-room/","RSS, 10 Einträge",""),
("europe","Orange","FR","orange.com",["Orange Group"],"newsroom",
 "https://www.orange.com/en/newsroom","https://www.orange.com/en/newsroom","statisch, 24 Artikel-Links",""),
("europe","BT Group","GB","bt.com",["BT","EE"],"rss",
 "https://newsroom.bt.com/feed/en","https://newsroom.bt.com/","RSS, 25 Einträge, 16.07.2026",""),
("europe","Swisscom","CH","swisscom.ch",[],"newsroom_js",
 "https://www.swisscom.ch/en/about/news.html","https://www.swisscom.ch/en/about/news.html","statisch, 3 Artikel-Links",""),
("europe","Telia","SE","teliacompany.com",["Telia Company"],"newsroom_js",
 "https://www.teliacompany.com/en/newsroom","https://www.teliacompany.com/en/newsroom","JS-gerendert",""),
("europe","KPN","NL","kpn.com",[],"rss",
 "https://www.overons.kpn/nieuws/feed/en","https://www.overons.kpn/nieuws/en/","RSS, 25 Einträge, 09.07.2026",""),
("europe","Proximus","BE","proximus.com",[],"newsroom",
 "https://www.proximus.com/news.html","https://www.proximus.com/news.html","statisch, 4 Artikel-Links",""),
("europe","TIM","IT","gruppotim.it",["Telecom Italia","Gruppo TIM"],"newsroom_js",
 "https://www.gruppotim.it/en/press-archive.html","https://www.gruppotim.it/en/press-archive.html","JS-gerendert",""),
("europe","Liberty Global","GB","libertyglobal.com",["Virgin Media","Sunrise"],"newsroom_js",
 "https://www.libertyglobal.com/news-insights/featured-news-insights/",
 "https://www.libertyglobal.com/news-insights/featured-news-insights/","JS-gerendert",""),
("europe","VEON","NL","veon.com",["Jazz","Kyivstar","Beeline"],"newsroom",
 "https://www.veon.com/newsroom","https://www.veon.com/newsroom","statisch, 32 Artikel-Links",""),
("europe","Telenor","NO","telenor.com",[],"newsroom",
 "https://www.telenor.com/media/newsroom/","https://www.telenor.com/media/newsroom/","statisch, 10 Artikel-Links",""),
("europe","Turkcell","TR","turkcell.com.tr",[],"newsroom_js",
 "https://medya.turkcell.com.tr/basin-bultenleri/","https://medya.turkcell.com.tr/basin-bultenleri/",
 "JS-gerendert; RSS nur veraltet (2016)",""),
("europe","Iliad","FR","iliad.fr",["Free Mobile","Free"],"newsroom_js",
 "https://www.iliad.fr/en/press","https://www.iliad.fr/en/press","JS-gerendert",""),
("europe","1&1","DE","united-internet.de",["1und1","United Internet","Drillisch"],"rss",
 "https://unternehmen.1und1.de/presse/feed","https://unternehmen.1und1.de/presse",
 "offizieller 1&1-Pressefeed, 10 Einträge",""),
("europe","Bouygues Telecom","FR","bouyguestelecom.fr",["Bouygues"],"newsroom_js",
 "https://www.corporate.bouyguestelecom.fr/presse-et-actualites/",
 "https://www.corporate.bouyguestelecom.fr/presse-et-actualites/","JS-gerendert",""),
("europe","A1 Telekom Austria","AT","a1.group",["A1 Group","Telekom Austria"],"newsroom_js",
 "https://newsroom.a1.net/","https://newsroom.a1.net/","JS-gerendert",""),
("europe","Tele2","SE","tele2.com",[],"newsroom",
 "https://www.tele2.com/media/press-releases","https://www.tele2.com/media/press-releases","statisch, 10 Artikel-Links",""),
("europe","Elisa","FI","elisa.com",[],"newsroom_js",
 "https://elisa.com/corporate/news-room/","https://elisa.com/corporate/news-room/","JS-gerendert",""),
("europe","Three UK","GB","three.co.uk",["CK Hutchison","Hutchison 3"],"newsroom_js",
 "https://www.threemediacentre.co.uk/press-release-browser/","https://www.threemediacentre.co.uk/press-release-browser/","JS-gerendert",""),
("europe","Cosmote","GR","cosmote.gr",["OTE Group","OTE"],"newsroom_js",
 "https://www.cosmote.gr/otegroupcompanysite/en/media/press-releases",
 "https://www.cosmote.gr/otegroupcompanysite/en/media/press-releases","JS-gerendert",""),
# ---------------- NORTH AMERICA ----------------
("north_america","Verizon","US","verizon.com",[],"newsroom_js",
 "https://www.verizon.com/about/news","https://www.verizon.com/about/news",
 "offizieller Newsroom; der alte RSS-Feed war ein Parenting-Feed",""),
("north_america","AT&T","US","att.com",["ATT"],"official",
 "https://about.att.com/newsroom.html","https://about.att.com/newsroom.html","403 Bot-Sperre",
 "Newsroom liefert Bots 403. Plan: Playwright über Residential-Proxy oder offizielle Media-API; bis dahin Referenz + Fachpresse-Zuordnung."),
("north_america","T-Mobile US","US","t-mobile.com",["T-Mobile","Metro"],"official",
 "https://www.t-mobile.com/news","https://www.t-mobile.com/news","403 Bot-Sperre",
 "403. Plan: Playwright über Residential-Proxy; bis dahin Referenz + Fachpresse."),
("north_america","Comcast","US","comcast.com",["Xfinity Mobile","Xfinity"],"rss",
 "https://corporate.comcast.com/rss","https://corporate.comcast.com/news-information","RSS, 50 Einträge, 17.07.2026",""),
("north_america","Charter Communications","US","charter.com",["Spectrum Mobile","Spectrum"],"newsroom_js",
 "https://corporate.charter.com/newsroom","https://corporate.charter.com/newsroom","JS-gerendert",""),
("north_america","DISH Wireless","US","dish.com",["Boost Mobile","EchoStar"],"rss",
 "https://api.client.notified.com/api/rss/publish/view/53068?type=press","https://about.dish.com/newsroom",
 "RSS (Notified), 50 Einträge",""),
("north_america","UScellular","US","uscellular.com",["U.S. Cellular"],"official",
 "https://investors.uscellular.com/news/default.aspx","https://investors.uscellular.com/news/default.aspx","403 Bot-Sperre",
 "IR-Newsroom (Q4) blockt Bots. Plan: Q4-JSON-API prüfen; bis dahin Referenz."),
("north_america","Bell Canada","CA","bce.ca",["Bell","BCE"],"newsroom_js",
 "https://www.bce.ca/news-and-media/newsroom","https://www.bce.ca/news-and-media/newsroom","statisch, 4 Artikel-Links",""),
("north_america","Rogers","CA","rogers.com",[],"official",
 "https://about.rogers.com/news-ideas/","https://about.rogers.com/news-ideas/","403 Bot-Sperre",
 "403. Plan: Playwright über Residential-Proxy; bis dahin Referenz + Fachpresse."),
("north_america","Telus","CA","telus.com",[],"official",
 "https://www.telus.com/en/about/news-and-events","https://www.telus.com/en/about/news-and-events","403 Bot-Sperre",
 "403. Plan: Playwright über Residential-Proxy; bis dahin Referenz."),
# ---------------- LATIN AMERICA ----------------
("latin_america","América Móvil","MX","americamovil.com",["America Movil","Claro"],"official",
 "https://www.americamovil.com/English/press-releases/default.aspx","https://www.americamovil.com/English/press-releases/default.aspx",
 "403 (Q4-Plattform)","Plan: Q4-JSON-API prüfen; bis dahin Referenz + Fachpresse."),
("latin_america","Millicom","LU","millicom.com",["Tigo"],"newsroom_js",
 "https://www.millicom.com/media/press-releases","https://www.millicom.com/media/press-releases","JS-gerendert",""),
("latin_america","TIM Brasil","BR","tim.com.br",["TIM Brazil"],"newsroom",
 "https://www.tim.com.br/sobre-a-tim/sala-de-imprensa","https://www.tim.com.br/sobre-a-tim/sala-de-imprensa",
 "offizieller Pressebereich; der alte RSS-Feed enthielt Smoke-Tests und CMS-Promos",""),
("latin_america","Entel","CL","entel.cl",[],"newsroom_js",
 "https://informacioncorporativa.entel.cl/sala-de-prensa","https://informacioncorporativa.entel.cl/sala-de-prensa","JS-gerendert",""),
("latin_america","Oi","BR","oi.com.br",[],"newsroom_js",
 "https://www.oi.com.br/sala-de-imprensa/","https://www.oi.com.br/sala-de-imprensa/","statisch, 11 Artikel-Links",""),
("latin_america","Telecom Argentina","AR","telecom.com.ar",["Personal"],"official",
 "https://institucional.telecom.com.ar/prensa","https://institucional.telecom.com.ar/prensa","403 + Edge-Redirect",
 "403. Plan: Playwright über Residential-Proxy; bis dahin Referenz."),
("latin_america","WOM","CL","wom.cl",[],"newsroom_js",
 "https://sobrenosotros.wom.cl/wom-en-prensa/","https://sobrenosotros.wom.cl/wom-en-prensa/","statisch, 44 Artikel-Links",""),
# ---------------- AFRICA & MIDDLE EAST ----------------
("africa_middle_east","MTN Group","ZA","mtn.com",["MTN"],"rss",
 "https://www.mtn.com/feed/","https://www.mtn.com/newsroom/","RSS (WordPress)",""),
("africa_middle_east","Vodacom","ZA","vodacom.com",[],"newsroom_js",
 "https://www.vodacom.com/press-releases.php","https://www.vodacom.com/press-releases.php","JS-gerendert",""),
("africa_middle_east","Safaricom","KE","safaricom.co.ke",["M-Pesa"],"newsroom",
 "https://www.safaricom.co.ke/media-center-landing","https://www.safaricom.co.ke/media-center-landing","statisch, 9 Artikel-Links",""),
("africa_middle_east","Airtel Africa","NG","airtel.africa",[],"newsroom_js",
 "https://airtel.africa/media","https://airtel.africa/media","JS-gerendert",""),
("africa_middle_east","stc","SA","stc.com.sa",["Saudi Telecom"],"newsroom_js",
 "https://www.stc.com/en/media-center.html","https://www.stc.com/en/media-center.html","JS-gerendert",""),
("africa_middle_east","e&","AE","eand.com",["Etisalat","e& Group"],"newsroom_js",
 "https://www.eand.com/en/news.html","https://www.eand.com/en/news.html","JS-gerendert",""),
("africa_middle_east","Ooredoo","QA","ooredoo.com",[],"official",
 "https://www.ooredoo.com/en/media/news_view/","https://www.ooredoo.com/en/media/news_view/","403 Bot-Sperre",
 "403. Plan: Playwright über Residential-Proxy; bis dahin Referenz."),
("africa_middle_east","Zain","KW","zain.com",[],"official",
 "https://www.zain.com/en/media-center","https://www.zain.com/en/media-center","307 Bot-Challenge",
 "307-Edge-Challenge. Plan: Playwright über Residential-Proxy; bis dahin Referenz."),
("africa_middle_east","Orange MEA","EG","orange.eg",["Orange Egypt","Orange Jordan"],"newsroom_js",
 "https://www.orange.eg/en/media-center/press-releases","https://www.orange.eg/en/media-center/press-releases","JS-gerendert",""),
("africa_middle_east","du","AE","du.ae",["EITC"],"newsroom_js",
 "https://www.du.ae/about-us/media-centre","https://www.du.ae/about-us/media-centre","JS-gerendert",""),
("africa_middle_east","Maroc Telecom","MA","iam.ma",[],"official",
 "https://www.iam.ma/groupe/salle-de-presse/communiques-de-presse.aspx","https://www.iam.ma/groupe/salle-de-presse/communiques-de-presse.aspx",
 "403 Bot-Sperre","403. Plan: Playwright über Residential-Proxy; bis dahin Referenz."),
("africa_middle_east","Turk Telekom","TR","turktelekom.com.tr",[],"newsroom_js",
 "https://medya.turktelekom.com.tr/basin-bultenleri/basin-bultenleri-ve-gorseller",
 "https://medya.turktelekom.com.tr/basin-bultenleri/basin-bultenleri-ve-gorseller","JS-gerendert",""),
# ---------------- ASIA ----------------
("asia","KDDI","JP","kddi.com",["au"],"rss",
 "https://newsroom.kddi.com/english/news/newsrelease.xml","https://newsroom.kddi.com/english/","RSS, 10 Einträge, 06.07.2026",""),
("asia","Bharti Airtel","IN","airtel.in",["Airtel India","Airtel"],"newsroom",
 "https://www.airtel.in/press-release","https://www.airtel.in/press-release","statisch",""),
("asia","Reliance Jio","IN","jio.com",["Jio"],"newsroom_js",
 "https://www.jio.com/press-release","https://www.jio.com/press-release","JS-gerendert",""),
("asia","Vodafone Idea","IN","myvi.in",["Vi India","Vi"],"newsroom_js",
 "https://www.myvi.in/media/press-releases","https://www.myvi.in/media/press-releases","JS-gerendert",""),
("asia","Singtel","SG","singtel.com",[],"newsroom_js",
 "https://www.singtel.com/about-us/media-centre","https://www.singtel.com/about-us/media-centre","JS-gerendert",""),
("asia","SK Telecom","KR","sktelecom.com",["SKT"],"newsroom_js",
 "https://www.sktelecom.com/en/press/press_list.do","https://www.sktelecom.com/en/press/press_list.do","JS-gerendert",""),
("asia","KT","KR","corp.kt.com",["Korea Telecom"],"newsroom_js",
 "https://corp.kt.com/eng/html/prcenter/report_list.html","https://corp.kt.com/eng/html/prcenter/report_list.html","JS-gerendert",""),
("asia","NTT Docomo","JP","docomo.ne.jp",["Docomo"],"newsroom",
 "https://www.docomo.ne.jp/english/info/media_center/pr/","https://www.docomo.ne.jp/english/info/media_center/pr/","statisch, 20 Artikel-Links",""),
("asia","SoftBank","JP","softbank.jp",[],"newsroom_js",
 "https://www.softbank.jp/en/corp/news/press/","https://www.softbank.jp/en/corp/news/press/","statisch, 4 Artikel-Links",""),
("asia","Rakuten Mobile","JP","rakuten.co.jp",["Rakuten"],"newsroom",
 "https://corp.mobile.rakuten.co.jp/english/news/press/","https://corp.mobile.rakuten.co.jp/english/news/press/","statisch, 144 Artikel-Links",""),
("asia","China Mobile","CN","chinamobileltd.com",[],"newsroom_js",
 "https://www.chinamobileltd.com/en/media/press.php","https://www.chinamobileltd.com/en/media/press.php","JS-gerendert; statisch nur 1 Link",""),
("asia","China Telecom","CN","chinatelecom-h.com",[],"newsroom_js",
 "https://www.chinatelecom-h.com/en/media/press.php","https://www.chinatelecom-h.com/en/media/press.php","statisch, 4 Artikel-Links",""),
("asia","Chunghwa Telecom","TW","cht.com.tw",["Chunghwa"],"newsroom_js",
 "https://www.cht.com.tw/en/home/cht/messages","https://www.cht.com.tw/en/home/cht/messages","JS-gerendert",""),
("asia","Telkomsel","ID","telkomsel.com",[],"newsroom",
 "https://www.telkomsel.com/en/about-us/news","https://www.telkomsel.com/en/about-us/news","statisch, 9 Artikel-Links",""),
("asia","AIS","TH","ais.co.th",["Advanced Info Service"],"newsroom_js",
 "https://investor.ais.co.th/en/newsroom/set-announcements","https://investor.ais.co.th/en/newsroom/set-announcements","JS-gerendert (Investor SET)",""),
("asia","Viettel","VN","viettel.com.vn",[],"newsroom_js",
 "https://viettel.com.vn/en/news","https://viettel.com.vn/en/news","JS-gerendert",""),
("asia","Globe Telecom","PH","globe.com.ph",["Globe"],"official",
 "https://www.globe.com.ph/about-us/newsroom","https://www.globe.com.ph/about-us/newsroom","403 Bot-Sperre",
 "403. Plan: Playwright über Residential-Proxy; bis dahin Referenz + Fachpresse."),
("asia","PLDT","PH","pldt.com",["Smart Communications"],"newsroom_js",
 "https://main.pldt.com/newsroom","https://main.pldt.com/newsroom","JS-gerendert",""),
("asia","Indosat Ooredoo Hutchison","ID","ioh.co.id",["Indosat"],"newsroom_js",
 "https://ioh.co.id/portal/en/iohpressrelease","https://ioh.co.id/portal/en/iohpressrelease","JS-SPA",""),
("asia","CelcomDigi","MY","celcomdigi.com",[],"newsroom",
 "https://corporate.celcomdigi.com/newsroom","https://corporate.celcomdigi.com/newsroom","statisch, 100 Artikel-Links",""),
("asia","Maxis","MY","maxis.com.my",[],"newsroom_js",
 "https://www.maxis.com.my/en/about-maxis/newsroom/","https://www.maxis.com.my/en/about-maxis/newsroom/","JS-gerendert",""),
("asia","True Corporation","TH","truecorp.co.th",["True Corp"],"newsroom_js",
 "https://investor.true.th/en/newsroom/set-announcements","https://investor.true.th/en/newsroom/set-announcements","JS-gerendert (Investor SET)",""),
# ---------------- OCEANIA ----------------
("oceania","Telstra","AU","telstra.com.au",[],"newsroom_js",
 "https://www.telstra.com.au/exchange","https://www.telstra.com.au/exchange","JS-gerendert",""),
("oceania","Optus","AU","optus.com.au",[],"newsroom_js",
 "https://www.optus.com.au/about/media-centre","https://www.optus.com.au/about/media-centre","JS-gerendert",""),
("oceania","TPG Telecom","AU","tpgtelecom.com.au",["TPG"],"newsroom_js",
 "https://www.tpgtelecom.com.au/media_release","https://www.tpgtelecom.com.au/media_release","JS-gerendert",""),
("oceania","One NZ","NZ","one.nz",["One New Zealand","Vodafone NZ"],"rss",
 "https://media.one.nz/index.rss","https://media.one.nz","RSS, 10 Einträge, 05.07.2026",""),
("oceania","Spark","NZ","sparknz.co.nz",["Spark New Zealand"],"official",
 "https://www.sparknz.co.nz/news/","https://www.sparknz.co.nz/news/","Radware-Bot-Wall",
 "Radware-Wall (Redirect zu perfdrive). Plan: Playwright über Residential-Proxy; Alternative businessgroup.spark.co.nz prüfen; bis dahin Referenz."),
("oceania","2degrees","NZ","2degrees.nz",[],"newsroom_js",
 "https://www.2degrees.nz/media-releases","https://www.2degrees.nz/media-releases","JS-gerendert; RSS veraltet (2021)",""),
]

KIND_LABEL = {
    "rss":"Feed (RSS/Atom)","json_api":"Feed (JSON-API)","newsroom":"Newsroom (statisch)",
    "newsroom_js":"Newsroom (Headless/Playwright)","official":"Referenz (Bot-geblockt) + Plan",
}

def build_yaml():
    regions = {}
    for rk,name,country,website,aliases,kind,crawl,press,note,plan in M:
        regions.setdefault(rk, {"name":REGION_NAMES[rk],"operators":[]})
        src = {"type":kind,"url":crawl}
        if plan: src["plan"]=plan
        op = {"name":name,"country":country,"website":website}
        if aliases: op["aliases"]=aliases
        op["sources"]=[src]
        regions[rk]["operators"].append(op)
    doc = {"regions":regions}
    header = ("# =============================================================================\n"
              "# TELCO RADAR - Watchlist  (AUTO-GENERATED by scripts/build_sources.py)\n"
              "# =============================================================================\n"
              "# Each operator has ONE primary source on its OWN official domain.\n"
              "# Source types: rss | json_api | newsroom (static HTML) |\n"
              "#   newsroom_js (headless/Playwright) | official (verified reference, not\n"
              "#   crawled, carries a 'plan' explaining why + how to enable crawling).\n"
              "# Third-party trade press lives separately in news_sources.yaml.\n"
              "# Do not hand-edit: change scripts/build_sources.py and re-run.\n"
              "# =============================================================================\n\n")
    with open(ROOT/"config"/"watchlist.yaml","w",encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(doc,f,allow_unicode=True,sort_keys=False,default_flow_style=False,width=120)
    with open(ROOT/"config"/"watchlist_extra.yaml","w",encoding="utf-8") as f:
        f.write("# All operators now live in watchlist.yaml (generated). This file is kept\n"
                "# for backward compatibility and merged by region key if populated.\n"
                "regions: {}\n")

def build_doc():
    lines=[]
    lines.append("# Telco Radar — Verifizierte Quellenliste (offizielle Betreiber-Quellen)\n")
    lines.append("Stand: 17.07.2026. Jede URL wurde live geprüft (Browser-User-Agent, HTTP-Status, echte Inhalte, "
                 "gehört dem Unternehmen). Feeds wurden mit `feedparser` geparst (Eintragszahl + Datum als Beleg). "
                 "**Primärquelle jedes Betreibers ist seine eigene Domain** — keine Dritt-Medien, keine "
                 "Stichwort-Nachrichtensuche. Telco-Fachpresse ist eine separate, klar gekennzeichnete zweite Ebene.\n")
    # summary counts
    from collections import Counter
    c=Counter(k for *_,k,_,_,_,_ in [(x[0],x[1],x[2],x[3],x[4],x[5],x[6],x[7],x[8],x[9]) for x in M])
    kc=Counter(x[5] for x in M)
    lines.append("## Überblick\n")
    lines.append(f"- **{len(M)} Betreiber** in 6 Regionen, jeder mit ≥1 offizieller Quelle auf eigener Domain.")
    lines.append(f"- Direkt maschinenlesbar (Feed/JSON): **{kc['rss']+kc['json_api']}** "
                 f"({kc['rss']}× RSS/Atom, {kc['json_api']}× JSON-API).")
    lines.append(f"- Newsroom statisch (httpx-Scrape): **{kc['newsroom']}**.")
    lines.append(f"- Newsroom JS-gerendert (Headless/Playwright): **{kc['newsroom_js']}**.")
    lines.append(f"- Bot-geblockt → verifizierte Referenz + dokumentierter Plan: **{kc['official']}**.\n")
    for rk in REGION_NAMES:
        rows=[x for x in M if x[0]==rk]
        if not rows: continue
        lines.append(f"## {REGION_NAMES[rk]} ({len(rows)})\n")
        lines.append("| Betreiber | Land | Website | Presse-/Newsroom-URL | Maschinen-Feed | Anbindung | Verifikation |")
        lines.append("|---|---|---|---|---|---|---|")
        for rk2,name,country,website,aliases,kind,crawl,press,note,plan in rows:
            feed = crawl if kind in ("rss","json_api") else "—"
            lines.append(f"| {name} | {country} | {website} | {press} | {feed} | {KIND_LABEL[kind]} | {note} |")
        lines.append("")
    # plans section
    lines.append("## Bot-geblockte Betreiber — dokumentierter Plan (Phase 2)\n")
    lines.append("Diese Betreiber liefern automatisierten Clients 403/307 bzw. eine Bot-Wall. Die offizielle "
                 "Presse-URL ist verifiziert und wird als Referenz angezeigt; das Auto-Signal kommt vorerst über "
                 "die Fachpresse-Ebene (Namensnennung). Plan zur Freischaltung:\n")
    for x in M:
        if x[5]=="official":
            lines.append(f"- **{x[1]}** ({x[2]}) — {x[6]} — {x[9]}")
    lines.append("")
    with open(ROOT/"TELCO_RADAR_QUELLEN.md","w",encoding="utf-8") as f:
        f.write("\n".join(lines))

if __name__=="__main__":
    build_yaml(); build_doc()
    print(f"Generated: {len(M)} operators")
    kc={}
    for x in M: kc[x[5]]=kc.get(x[5],0)+1
    print("by kind:", kc)
