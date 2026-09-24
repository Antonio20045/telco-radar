"""Der Versandschritt des Abdeckungswaechters: `scripts/geraete_abdeckung_mail.py`.

WARUM ES DIESE DATEI GIBT
-------------------------
Das ist die Datei, die `geraete.yml` wirklich ausfuehrt - und sie hatte
keinen einzigen Test. Ungeprueft waren genau die Zweige, an denen dieser
Waechter steht oder faellt: was passiert, wenn der Bestand keinen Messtag
kennt, was passiert, wenn ein Alarm vorliegt, und was passiert, wenn die
Zustellung scheitert. Ein Versandschritt, der still 0 zurueckgibt, ist
dieselbe Fehlerklasse wie die 50 gruenen Laeufe ohne Telekom-Zeile.

KEIN MESSTAG IST EIN AUSFALL, KEINE ENTWARNUNG
----------------------------------------------
Der Schritt laeuft hinter dem Lauf, der den Bestand schreibt. Kennt der
Bestand danach keinen einzigen Messtag, dann hat entweder der Lauf nichts
geschrieben oder der Pfad stimmt nicht - beides Befunde, und beide sind
unsichtbar, wenn der Schritt gruen ausgeht. Er faellt deshalb mit
`EXIT_KEIN_MESSTAG` aus, nicht mit 0.

Kein Test hier haengt am heutigen Datum (CLAUDE.md Regel 11), und keiner
spricht mit einem Mailserver: `versand.sende_mail` ist die eine Stelle,
die ersetzt wird.
"""
import importlib.util
import logging
import sys
from pathlib import Path

from telco_radar import versand
from telco_radar.analyze.geraete_store import GeraeteDB
from test_geraete_pipeline import _root

_PFAD = Path(__file__).resolve().parents[1] / "scripts" / "geraete_abdeckung_mail.py"
_spec = importlib.util.spec_from_file_location("geraete_abdeckung_mail", _PFAD)
mail = importlib.util.module_from_spec(_spec)
sys.modules["geraete_abdeckung_mail"] = mail
_spec.loader.exec_module(mail)


def _tag(n: int) -> str:
    return f"2026-09-{n:02d}"


def _bestand(tmp_path, *, mit_alarm: bool) -> Path:
    """Ein Wurzelverzeichnis mit Konfiguration UND Bestand.

    `Medimax` steht in `_QUELLEN` des Pipeline-Tests - der Alarm wird nur
    fuer konfigurierte Anbieter gemeldet, ein Bestand allein reicht nicht.
    """
    root = _root(tmp_path)
    (root / "data" / "state").mkdir(parents=True, exist_ok=True)
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    db.protokolliere_lauf("Medimax", _tag(1), funde=20, vollstaendig=True)
    db.protokolliere_lauf("Medimax", _tag(2), funde=0 if mit_alarm else 20,
                          vollstaendig=True)
    db.save(_tag(2))
    return root


def _faengt_mail(monkeypatch) -> list:
    """Die Attrappe merkt sich AUCH den Trockenschalter.

    Ohne ihn war `trocken=True` ein stiller Mutant: die Mail ging nie
    hinaus, der Workflow-Schritt blieb gruen - ein stummgeschalteter
    Alarmkanal, genau die Fehlerklasse, gegen die dieser Waechter gebaut
    ist.
    """
    gesendet: list = []

    def _fake(betreff, text, html, *, trocken=False):
        gesendet.append((betreff, text, html, trocken))
        return "an 1 Empfänger"

    monkeypatch.setattr(versand, "sende_mail", _fake)
    return gesendet


# --------------------------------------------------------------------------
# Fall 1: kein Messtag
# --------------------------------------------------------------------------

def test_ohne_messtag_meldet_der_schritt_einen_ausfall(tmp_path, monkeypatch,
                                                       caplog):
    """Ein Bestand ohne einen einzigen Messtag ist keine Entwarnung. Der
    Schritt geht rot aus und sagt warum - sonst ist der Tag, an dem der
    Lauf gar nichts geschrieben hat, von einem ruhigen Tag nicht zu
    unterscheiden."""
    root = _root(tmp_path)
    gesendet = _faengt_mail(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="geraete_abdeckung_mail"):
        code = mail.main(["--root", str(root)])
    assert code != 0
    assert code == mail.EXIT_KEIN_MESSTAG
    assert "keinen Messtag" in caplog.text
    # Gegenprobe: es ist auch keine Mail hinausgegangen.
    assert gesendet == []


# --------------------------------------------------------------------------
# Fall 2: ein Alarm liegt vor
# --------------------------------------------------------------------------

def test_mit_alarm_geht_genau_eine_mail_hinaus_und_der_schritt_ist_gruen(
        tmp_path, monkeypatch, caplog):
    root = _bestand(tmp_path, mit_alarm=True)
    gesendet = _faengt_mail(monkeypatch)
    with caplog.at_level(logging.WARNING,
                         logger="telco_radar.geraete_pipeline"):
        code = mail.main(["--root", str(root)])
    assert code == 0
    assert len(gesendet) == 1
    betreff, text, _, trocken = gesendet[0]
    # OHNE `--trocken` geht die Mail WIRKLICH hinaus.
    assert trocken is False
    assert "02.09.2026" in betreff
    assert "Medimax: heute nicht erfasst" in text
    # Derselbe Satz steht im Protokoll - drei Kanaele, eine Wortform.
    assert "Medimax: heute nicht erfasst" in caplog.text


def test_ohne_alarm_geht_keine_mail_hinaus(tmp_path, monkeypatch):
    """Die Gegenprobe: ein ruhiger Tag verschickt nichts - und meldet
    trotzdem Erfolg, denn der Bestand kennt einen Messtag."""
    root = _bestand(tmp_path, mit_alarm=False)
    gesendet = _faengt_mail(monkeypatch)
    assert mail.main(["--root", str(root)]) == 0
    assert gesendet == []


# --------------------------------------------------------------------------
# Fall 3: die Zustellung scheitert
# --------------------------------------------------------------------------

def test_ein_zustellfehler_faellt_mit_rueckgabecode_zwei(tmp_path, monkeypatch,
                                                         caplog):
    """Scheitern ist kein leeres Ergebnis (Clean Code 5): ein Alarmkanal,
    der still nicht zustellt, ist die Fehlerklasse, gegen die dieser
    Waechter gebaut ist."""
    root = _bestand(tmp_path, mit_alarm=True)

    def _wirft(*a, **k):
        raise versand.VersandFehler("SMTP_HOST fehlt")

    monkeypatch.setattr(versand, "sende_mail", _wirft)
    with caplog.at_level(logging.ERROR, logger="geraete_abdeckung_mail"):
        code = mail.main(["--root", str(root)])
    assert code == 2
    assert code == mail.EXIT_NICHT_ZUGESTELLT
    assert "NICHT zugestellt" in caplog.text
    assert "SMTP_HOST fehlt" in caplog.text


# --------------------------------------------------------------------------
# Fall 3b: der Kanal ist gar nicht erst eingerichtet (P1/C2-Nachtrag,
# 24.09.2026) - NICHT dieselbe Fehlerklasse wie Fall 3 oben.
# --------------------------------------------------------------------------

def test_fehlende_smtp_secrets_faellen_nur_als_warnung_nicht_rot(
        tmp_path, monkeypatch, capsys, caplog):
    """Solange dieses Repo keine SMTP-Secrets traegt, ist JEDER Lauf
    betroffen - ein Schritt, der dafuer rot ausfaellt, ist ein Signal, das
    immer an ist und deshalb keins mehr (dieselbe Fehlerklasse wie "50
    Laeufe gruen ohne Daten", nur umgekehrt). Der Alarm bleibt trotzdem
    sichtbar: Protokollzeile UND GitHub-Annotation, nur der Rueckgabecode
    wird 0."""
    root = _bestand(tmp_path, mit_alarm=True)

    def _nicht_eingerichtet(*a, **k):
        raise versand.VersandNichtEingerichtet(
            "SMTP_HOST, MAIL_FROM oder MAIL_TO fehlen - keine Mail verschickt")

    monkeypatch.setattr(versand, "sende_mail", _nicht_eingerichtet)
    with caplog.at_level(logging.WARNING, logger="geraete_abdeckung_mail"):
        code = mail.main(["--root", str(root)])
    assert code == 0
    assert code == mail.EXIT_OK
    # Die GitHub-Annotation steht auf stdout, nicht nur im Log.
    ausgabe = capsys.readouterr().out
    assert "::warning::" in ausgabe
    assert "NICHT zugestellt" in ausgabe
    assert "NICHT zugestellt" in caplog.text
    assert "nicht eingerichtet" in caplog.text


def test_ein_echter_zustellfehler_bleibt_von_der_warnung_unterscheidbar(
        tmp_path, monkeypatch, caplog):
    """Gegenprobe zu Fall 3 und 3b zusammen: nur `VersandNichtEingerichtet`
    wird zur Warnung - ein gewoehnlicher `VersandFehler` (Kanal
    eingerichtet, SMTP antwortet trotzdem nicht) bleibt Exit 2 und rot,
    wie test_ein_zustellfehler_faellt_mit_rueckgabecode_zwei es bereits
    zeigt. Diese zweite Probe haelt zusaetzlich fest, dass die neue
    Ausnahmeklasse dafuer NICHT greift."""
    root = _bestand(tmp_path, mit_alarm=True)

    def _smtp_antwortet_nicht(*a, **k):
        raise versand.VersandFehler("SMTP: [Errno 110] Connection timed out")

    monkeypatch.setattr(versand, "sende_mail", _smtp_antwortet_nicht)
    with caplog.at_level(logging.ERROR, logger="geraete_abdeckung_mail"):
        code = mail.main(["--root", str(root)])
    assert code == mail.EXIT_NICHT_ZUGESTELLT
    assert "Connection timed out" in caplog.text


def test_mit_trocken_wird_nichts_verschickt(tmp_path, monkeypatch):
    """Die andere Haelfte desselben Schalters: `--trocken` baut die Mail
    und stellt sie NICHT zu. Beide Tests zusammen nageln den Wert fest -
    einer allein laesst ihn durchrutschen."""
    root = _bestand(tmp_path, mit_alarm=True)
    gesendet = _faengt_mail(monkeypatch)
    assert mail.main(["--root", str(root), "--trocken"]) == 0
    assert len(gesendet) == 1
    assert gesendet[0][3] is True


# --------------------------------------------------------------------------
# Fall 4: ein Anbieter, den die Konfiguration nicht mehr kennt
# --------------------------------------------------------------------------

def test_ein_nicht_konfigurierter_anbieter_loest_keine_mail_aus(tmp_path,
                                                                monkeypatch):
    """`nur` grenzt auf die Anbieter der Konfiguration ein. Ein Anbieter,
    der aus `geraete_quellen.yaml` gefallen ist, wird nicht mehr
    beobachtet - sein eingefrorener Zaehlerstand darf keine
    Ewigkeitsmail geben. Ohne diese Eingrenzung verschickt der Schritt
    hier eine Mail."""
    root = _root(tmp_path)
    (root / "data" / "state").mkdir(parents=True, exist_ok=True)
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    db.protokolliere_lauf("Medimax", _tag(1), funde=20, vollstaendig=True)
    db.protokolliere_lauf("Medimax", _tag(2), funde=20, vollstaendig=True)
    # "Gespenst" steht nicht in der Konfiguration des Testwurzelordners.
    db.protokolliere_lauf("Gespenst", _tag(1), funde=40, vollstaendig=True)
    db.protokolliere_lauf("Gespenst", _tag(2), funde=0, vollstaendig=True)
    db.save(_tag(2))
    gesendet = _faengt_mail(monkeypatch)
    assert mail.main(["--root", str(root)]) == 0
    assert gesendet == []
    # Gegenprobe: der Alarm selbst ist da - nur eben nicht fuer diesen Lauf.
    assert [a.anbieter for a in db.ausfall_alarme(heute=_tag(2))] == \
        ["Gespenst"]
