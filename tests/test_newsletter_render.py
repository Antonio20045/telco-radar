"""Der Mail-Renderer, und vor allem: der Treue-Test.

Die haerteste Anforderung des ganzen Newsletters lautet, dass kein
inhaltstragender Satz in der Mail von dem abweicht, was im Bericht-JSON
steht. Sobald jemand den Editor fuer die Mail "etwas anders" formulieren
laesst, gibt es zwei Wahrheiten - und niemand merkt, welche von beiden
stimmt.

Der Test unterscheidet dafuer zwei Textarten, sonst waere er nicht
erfuellbar: was aus `items[]` stammt, muss im Quell-JSON wiederzufinden
sein; Rahmentexte (Anrede, Kopfzeile, Abmeldehinweis, Impressumszeile,
Stichwort-Markierung) kommen aus `templates/mail/chrome.yaml`, und die kennt
er als Allowlist.
"""
import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from telco_radar.newsletter.filters import Eintrag, Treffer
from telco_radar.newsletter import render as r
from telco_radar.newsletter.quelle import aus_bericht

BERICHT = {
    "date": "2026-08-11",
    "regions": {"Europa": {"highlights": [
        {"headline": "Telekom senkt Preise um zehn Prozent",
         "summary": "Die Deutsche Telekom senkt zum 1. September die Preise "
                    "ihrer MagentaMobil-Tarife. Betroffen sind vier Tarife. "
                    "Der dritte Satz gehört nicht mehr in die Mail.",
         "url": "https://fachpresse.test/telekom", "operator": "Deutsche Telekom",
         "category": "Tarif/Pricing", "relevance": 3, "ctm_bezug": 3,
         "source": "Mobile World Live", "date": "2026-08-10"},
        {"headline": "Starlink startet Mobilfunkdienst",
         "summary": "SpaceX schaltet Direct-to-Cell frei.",
         "url": "https://fachpresse.test/starlink", "operator": "SpaceX",
         "category": "Netz/Technologie", "relevance": 2, "ctm_bezug": 1,
         "source": "Light Reading", "date": "2026-08-09"},
    ]}},
}

BASIS = "https://telco-radar.onrender.com"


def _treffer(*, stichwort=""):
    eintraege = aus_bericht(BERICHT, bericht_url=f"{BASIS}/reports/2026-08-11.html")
    aus = [Treffer(eintrag=e, grund="filter") for e in eintraege]
    if stichwort:
        aus[-1] = Treffer(eintrag=eintraege[-1], grund="stichwort",
                          stichwort=stichwort)
    return aus


def _nachricht(**kw):
    treffer = kw.pop("treffer", None) or _treffer()
    vorgabe = dict(datum_de="11. August 2026",
                   bericht_url=f"{BASIS}/index.html",
                   abmelde_url=f"{BASIS}/newsletter-abgemeldet.html?t=abc",
                   seit_datum="1. August 2026", basis_url=BASIS)
    vorgabe.update(kw)
    return r.baue(treffer, **vorgabe)


# ==============================================  DER TREUE-TEST  ===========

def _bloecke(html: str) -> list[str]:
    """Jeder sichtbare Textblock der Mail, einzeln."""
    from bs4 import Doctype
    soup = BeautifulSoup(html, "html.parser")
    for weg in soup.select("title, style, script"):
        weg.decompose()
    bloecke = []
    for knoten in soup.find_all(string=True):
        if isinstance(knoten, Doctype):
            continue
        text = re.sub(r"\s+", " ", str(knoten)).strip()
        if text:
            bloecke.append(text)
    return bloecke


def _quelltext() -> str:
    """Alles, was im Bericht steht - als eine durchsuchbare Zeichenkette."""
    return json.dumps(BERICHT, ensure_ascii=False)


def _erlaubte_rahmen() -> list[str]:
    """Rahmentexte, Platzhalter durch `.*` ersetzt - als Muster."""
    muster = []
    for satz in r.rahmentexte():
        teile = [re.escape(t) for t in re.split(r"\{[a-z_]+\}", satz)]
        muster.append(re.compile("^" + ".*".join(teile) + "$"))
    return muster


def test_jeder_inhaltstragende_block_steht_so_im_bericht():
    """Der Test, um den es geht.

    Ein Block gilt als in Ordnung, wenn er ENTWEDER im Bericht-JSON steht
    ODER ein Rahmentext aus chrome.yaml ist. Alles andere waere ein Satz,
    den sich der Renderer ausgedacht hat."""
    nachricht = _nachricht()
    quelle = _quelltext()
    rahmen = _erlaubte_rahmen()
    # Zeichen, die keine Aussage sind: Trennzeichen, Nummerierung, URLs.
    unbedenklich = re.compile(
        r"^(?:[\W\d\s]|https?://|&\w+;|Zur Quelle|Im Wochenbericht)+$")
    erfunden = []
    gepruefte = 0
    for block in _bloecke(nachricht.html):
        gepruefte += 1
        if unbedenklich.match(block):
            continue
        if block in quelle:
            continue
        if any(m.match(block) for m in rahmen):
            continue
        # Zusammengesetzte Zeilen: eine Zeile darf aus mehreren erlaubten
        # Teilen bestehen ("Guten Tag, diese Meldungen passen …", oder Kicker
        # plus Ausgabedatum in einer Zeile). Abgezogen wird mit demselben
        # Muster, das auch den Platzhalter kennt - sonst bliebe "Ausgabe vom
        # {datum}" als vermeintlich erfundener Satz stehen.
        rest = block
        for m in sorted(rahmen, key=lambda p: -len(p.pattern)):
            rest = re.sub(m.pattern.strip("^$"), " ", rest)
        if unbedenklich.match(rest or " "):
            continue
        erfunden.append(block)
    assert gepruefte > 10, "kaum Bloecke geprueft - der Test prueft sonst nichts"
    assert not erfunden, f"nicht aus Bericht oder chrome.yaml: {erfunden}"


def test_der_treue_test_wuerde_einen_erfundenen_satz_finden():
    """Die Gegenprobe. Ohne sie belegt der Test oben nur, dass er nie
    ausschlaegt - genau die Falle, an der diese Codebasis schon einmal einen
    gruenen Test bekam, der nichts prueft."""
    treffer = _treffer()
    treffer[0].eintrag.titel = "Ein Satz, den es im Bericht nicht gibt"
    nachricht = _nachricht(treffer=treffer)
    quelle = _quelltext()
    rahmen = _erlaubte_rahmen()
    bloecke = [b for b in _bloecke(nachricht.html)
               if b not in quelle and not any(m.match(b) for m in rahmen)]
    assert any("den es im Bericht nicht gibt" in b for b in bloecke)


def test_die_zusammenfassung_wird_am_satz_gekuerzt_und_bleibt_teilstring():
    """Ohne Ellipse - sonst waere der Text kein Teilstring mehr, und der
    Treue-Test waere unerfuellbar."""
    lang = ("Erster Satz. Zweiter Satz. Dritter Satz.")
    gekuerzt = r.kuerze(lang)
    assert gekuerzt == "Erster Satz. Zweiter Satz."
    assert gekuerzt in lang
    assert "…" not in gekuerzt and "..." not in gekuerzt


def test_ein_deutsches_datum_zerreisst_den_satz_nicht():
    """Gemessen in der Vorschau vom 11.08.2026: die Mail zeigte "Aktion
    gültig bis 12." als ganzen Satz. Ein naiver Trenner `(?<=[.!?])\\s+`
    sieht in "12. September" ein Satzende - Punkt, Leerzeichen,
    Grossbuchstabe. Derselbe Schnitt trifft `_strip_vodafone_advice` im
    Wochenbericht, dort faellt dann eine Satzhaelfte als vermeintlicher Rat
    weg."""
    text = ("Neukunden zahlen einmalig 1 Euro. Gültig bis 12. September 2026 "
            "in allen Shops. Dritter Satz.")
    gekuerzt = r.kuerze(text)
    assert gekuerzt.endswith("in allen Shops.")
    assert gekuerzt in text
    assert "Dritter Satz" not in gekuerzt


def test_ein_echtes_satzende_nach_einer_zahl_bleibt_eines():
    """Die Gegenprobe: geschuetzt wird nur vor einem MONATSNAMEN. Eine Regel,
    die jeden Grossbuchstaben nach einer Zahl schluckt, waere die teurere."""
    from telco_radar.textwerkzeug import saetze
    assert saetze("Die Zahl stieg auf 12. Vodafone reagierte.") == [
        "Die Zahl stieg auf 12.", "Vodafone reagierte."]


def test_der_renderer_ruft_kein_modell_auf(monkeypatch):
    """Die Zusicherung wortwoertlich geprueft: ein LLM-Aufruf im Versandpfad
    wirft."""
    import telco_radar.analyze.llm as llm
    def darf_nicht(*a, **k):
        raise AssertionError("Modellaufruf im Renderpfad")
    gesperrt = [n for n in dir(llm)
                if callable(getattr(llm, n)) and not n.startswith("_")
                and ("chat" in n or "call" in n or "complete" in n)]
    assert gesperrt, "keine Modellfunktion gefunden - der Test prueft nichts"
    for name in gesperrt:
        monkeypatch.setattr(llm, name, darf_nicht)
    _nachricht()
    # ... und im Modul steht auch kein Import darauf.
    quelle = Path(r.__file__).read_text(encoding="utf-8")
    assert "llm" not in quelle


# ==================================================  E-Mail-Handwerk  ======

def test_das_html_haelt_sich_an_email_recht():
    """Outlook rendert mit der Word-Engine: kein Flexbox, kein Grid, keine
    externen Stylesheets, keine Web Fonts, kein Hintergrundbild."""
    html = _nachricht().html
    verboten = ("display:flex", "display:grid", "<link", "@import",
                "background-image", "fonts.googleapis", "position:absolute",
                "<script")
    for muster in verboten:
        assert muster not in html, muster
    # ... und positiv: Tabellenlayout mit Inline-CSS.
    soup = BeautifulSoup(html, "html.parser")
    assert soup.find("table") is not None
    assert soup.select_one("style") is None


def test_die_mail_ist_hoechstens_600_pixel_breit():
    html = _nachricht().html
    assert f"max-width:{r.BREITE}px" in html
    breiten = [int(b) for b in re.findall(r'width="(\d+)"', html)]
    assert breiten and max(breiten) <= r.BREITE


def test_die_mail_ist_dark_mode_tauglich():
    """Ohne diese Angabe invertieren Apple Mail und Outlook die Flaechen
    selbst - invertiertes Rot auf invertiertem Papier ist unlesbar."""
    html = _nachricht().html
    assert 'name="color-scheme"' in html
    assert "supported-color-schemes" in html


def test_kein_bild_ohne_alt_text():
    """Die Mail traegt derzeit keine Bilder - falls jemand eines ergaenzt,
    faellt dieser Test und nicht erst der Screenreader eines Empfaengers."""
    soup = BeautifulSoup(_nachricht().html, "html.parser")
    ohne = [str(b) for b in soup.find_all("img") if b.get("alt") is None]
    assert not ohne, ohne


def test_fremde_ueberschriften_werden_escaped():
    """In einer Meldung steht, was ein beliebiger fremder Newsroom in seinen
    Titel schreibt - und das sind rund 200 Absender."""
    treffer = _treffer()
    treffer[0].eintrag.titel = '<script>alert("x")</script> & mehr'
    html = _nachricht(treffer=treffer).html
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_die_textfassung_ist_eigenstaendig_und_kein_html_strip():
    text = _nachricht().text
    assert "<" not in text and "&amp;" not in text
    # Nummerierung, Absender in Klammern, Links auf eigener Zeile - Merkmale,
    # die ein Strip aus dem HTML nicht hergibt.
    assert re.search(r"^1\. Telekom senkt Preise", text, re.M)
    assert "[Mobile World Live]" in text
    assert re.search(r"^\s+Zur Quelle: https://", text, re.M)


def test_beide_fassungen_tragen_dieselben_meldungen():
    """Eine Textfassung, die eine Meldung weniger zeigt, ist eine zweite
    Auswahl - und damit eine zweite Wahrheit."""
    nachricht = _nachricht()
    for eintrag in aus_bericht(BERICHT):
        assert eintrag.titel in nachricht.html
        assert eintrag.titel in nachricht.text
        assert eintrag.url in nachricht.html
        assert eintrag.url in nachricht.text


# ==============================================  Links und Abmeldung  ======

def test_jeder_eintrag_verlinkt_quelle_und_bericht():
    soup = BeautifulSoup(_nachricht().html, "html.parser")
    ziele = {a["href"] for a in soup.find_all("a")}
    assert "https://fachpresse.test/telekom" in ziele
    assert any("/reports/2026-08-11.html" in z for z in ziele)


def test_der_abmeldelink_steht_sichtbar_in_jeder_ausgabe():
    nachricht = _nachricht()
    soup = BeautifulSoup(nachricht.html, "html.parser")
    abmelde = [a for a in soup.find_all("a") if "abgemeldet" in a["href"]]
    assert abmelde and abmelde[0].get_text(strip=True) == "Abmelden"
    assert "newsletter-abgemeldet.html?t=abc" in nachricht.text


def test_list_unsubscribe_traegt_nur_die_https_url():
    """Kein `mailto:` (kein Postfach da, das es auswerten koennte) und kein
    `List-Unsubscribe-Post` (siehe Festlegung 5 des Konzepts)."""
    headers = _nachricht().headers
    assert headers["List-Unsubscribe"].startswith("<https://")
    assert "mailto:" not in headers["List-Unsubscribe"]
    assert "List-Unsubscribe-Post" not in headers
    assert set(headers) == {"List-Unsubscribe"}


def test_impressum_und_datenschutz_stehen_im_fuss():
    nachricht = _nachricht()
    assert f"{BASIS}/impressum.html" in nachricht.html
    assert f"{BASIS}/datenschutz.html" in nachricht.text


# ================================================  Stichwort-Markierung  ===

def test_ein_stichworttreffer_sagt_warum_er_dasteht():
    nachricht = _nachricht(treffer=_treffer(stichwort="Starlink"))
    assert "Ihr Stichwort: Starlink" in nachricht.html
    assert "Ihr Stichwort: Starlink" in nachricht.text


def test_ein_filtertreffer_traegt_keine_markierung():
    nachricht = _nachricht()
    assert "Ihr Stichwort" not in nachricht.html


def test_dasselbe_stichwort_wird_nur_beim_ersten_der_folge_genannt():
    """In der Vorschau vom 11.08.2026 stand "Ihr Stichwort: Starlink"
    viermal untereinander - Stichworttreffer stehen hinter den
    Filtertreffern, gleiche Marken folgen also zwangslaeufig aufeinander.
    Viermal dieselbe Zeile erklaert nichts mehr, sie trommelt."""
    eintraege = aus_bericht(BERICHT)
    treffer = [Treffer(eintrag=e, grund="stichwort", stichwort="Starlink")
               for e in eintraege]
    assert len(treffer) >= 2, "der Fall tritt sonst gar nicht ein"
    nachricht = _nachricht(treffer=treffer)
    assert nachricht.html.count("Ihr Stichwort: Starlink") == 1
    assert nachricht.text.count("Ihr Stichwort: Starlink") == 1


def test_ein_wechsel_des_stichworts_wird_wieder_genannt():
    """Die Gegenprobe: entdoppelt wird die FOLGE, nicht das Stichwort."""
    eintraege = aus_bericht(BERICHT)
    treffer = [Treffer(eintrag=eintraege[0], grund="stichwort", stichwort="Tarif"),
               Treffer(eintrag=eintraege[1], grund="stichwort", stichwort="Satellit")]
    html = _nachricht(treffer=treffer).html
    assert "Ihr Stichwort: Tarif" in html
    assert "Ihr Stichwort: Satellit" in html


# ==========================================================  Betreff  ======

def test_der_betreff_traegt_die_staerkste_schlagzeile():
    """Nicht "Ihr Newsletter" - der Betreff ist die einzige Zeile, die JEDER
    Empfaenger sieht, auch der, der nicht oeffnet."""
    b = _nachricht().betreff
    assert b.startswith("Telco Radar, 11. August 2026: ")
    assert "Telekom senkt Preise" in b
    assert "(+1 weitere)" in b


def test_der_betreff_bleibt_unter_achtzig_zeichen():
    treffer = _treffer()
    treffer[0].eintrag.titel = "Ein " + "sehr " * 30 + "langer Titel"
    b = _nachricht(treffer=treffer).betreff
    assert len(b) <= 78
    assert not b.endswith("seh")          # an der Wortgrenze gekuerzt


def test_der_betreff_traegt_keinen_markennamen():
    """Kein Markenname vor einer nicht zur Marke gehoerenden Adresse - genau
    das Muster, auf das Konzern-Gateways als Spoofing anschlagen."""
    chrome = r.lade_chrome()
    assert chrome["absender_name"] == "Telco Radar"
    assert "Vodafone" not in _nachricht().betreff


# =========================================================  Transport  =====

def test_der_trockenlauf_verschickt_nichts_und_merkt_sich_alles():
    from telco_radar.newsletter.transport import Trockenlauf
    t = Trockenlauf()
    ergebnis = t.send(_nachricht(), "a@beispiel.test")
    assert ergebnis.ok and ergebnis.message_id.startswith("trocken-")
    assert t.versendet[0][0] == "a@beispiel.test"


class _FakeHTTPError(Exception):
    def __init__(self, code, text=b"{}"):
        self.code = code
        self._text = text
    def read(self):
        return self._text


def _brevo(monkeypatch, antwort):
    import telco_radar.newsletter.transport as tp
    monkeypatch.setattr(tp.urllib.error, "HTTPError", _FakeHTTPError)
    monkeypatch.setattr(tp.urllib.request, "urlopen", antwort)
    monkeypatch.setattr(tp.time, "sleep", lambda s: None)
    return tp.BrevoTransport(api_key="k", absender_adresse="a@b.test")


class _Antwort:
    def __init__(self, koerper, status=201):
        self._k = json.dumps(koerper).encode()
        self.status = status
    def read(self):
        return self._k
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_brevo_gibt_die_message_id_zurueck(monkeypatch):
    """`bounce_sync` ordnet seine Ereignisse darueber zu. Ohne sie ist die
    Bounce-Erkennung blind - und das faellt erst auf, wenn die Reputation
    schon gelitten hat."""
    t = _brevo(monkeypatch, lambda *a, **k: _Antwort({"messageId": "<abc@brevo>"}))
    ergebnis = t.send(_nachricht(), "a@beispiel.test")
    assert ergebnis.ok and ergebnis.message_id == "<abc@brevo>"


def test_ein_4xx_wird_nicht_wiederholt(monkeypatch):
    """Ein "invalid recipient" wird beim vierten Versuch nicht gueltiger -
    der Empfaenger gehoert markiert, nicht angefunkt."""
    versuche = []
    def wirft(*a, **k):
        versuche.append(1)
        raise _FakeHTTPError(400, b'{"message":"invalid recipient"}')
    t = _brevo(monkeypatch, wirft)
    ergebnis = t.send(_nachricht(), "a@beispiel.test")
    assert not ergebnis.ok and ergebnis.dauerhaft and not ergebnis.wiederholbar
    assert len(versuche) == 1


def test_ein_429_wird_wiederholt(monkeypatch):
    """Die Ratengrenze ist voruebergehend. Wer sie wie ein 400 behandelt,
    wirft lebende Adressen weg."""
    versuche = []
    def wirft(*a, **k):
        versuche.append(1)
        raise _FakeHTTPError(429, b'{"message":"rate limit"}')
    t = _brevo(monkeypatch, wirft)
    ergebnis = t.send(_nachricht(), "a@beispiel.test")
    assert ergebnis.wiederholbar and not ergebnis.dauerhaft
    assert len(versuche) == t.versuche == 3


def test_ein_401_nennt_den_90_tage_verfall(monkeypatch):
    """Die Ursache, die man sonst stundenlang im Code sucht."""
    def wirft(*a, **k):
        raise _FakeHTTPError(401, b'{"message":"unauthorized"}')
    ergebnis = _brevo(monkeypatch, wirft).send(_nachricht(), "a@beispiel.test")
    assert "90" in ergebnis.fehler and ergebnis.dauerhaft


def test_die_adresse_steht_in_keiner_logzeile(monkeypatch, caplog):
    """In keinem Log darf je eine Adresse erscheinen."""
    def wirft(*a, **k):
        raise _FakeHTTPError(400, b'{"message":"nope"}')
    t = _brevo(monkeypatch, wirft)
    with caplog.at_level("DEBUG"):
        t.send(_nachricht(), "geheim@beispiel.test")
    assert "geheim@beispiel.test" not in caplog.text


def test_ein_5xx_wird_wiederholt(monkeypatch):
    versuche = []
    def wirft(*a, **k):
        versuche.append(1)
        raise _FakeHTTPError(503, b"gateway")
    ergebnis = _brevo(monkeypatch, wirft).send(_nachricht(), "a@b.test")
    assert ergebnis.wiederholbar and len(versuche) == 3


def test_es_gibt_keinen_smtp_pfad():
    """Kein SMTP, auch nicht als Rueckfall - Render Free sperrt 25/465/587,
    und ein zweiter Versandweg waere ein zweiter Ort fuer Absenderdaten."""
    quelle = (Path(r.__file__).parent / "transport.py").read_text(encoding="utf-8")
    for verboten in ("smtplib", "SMTP(", "starttls", "sendmail"):
        assert verboten not in quelle, verboten
