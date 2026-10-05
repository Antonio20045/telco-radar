"""Die geteilten Textwerkzeuge - hier die Redaktionsregel "beobachtend statt
empfehlend" (CLAUDE.md §8).

Drei Stellen setzen sie durch, mit drei verschiedenen ANTWORTEN, aber seit
dem 08.08.2026 mit demselben Handwerkszeug. Diese Datei nagelt fest, dass die
Antworten verschieden BLEIBEN - die strenge der Wettbewerbsseite und die
feine der Differenzierungs-Karten sind kein Versehen.
"""

import pytest

from telco_radar import textwerkzeug as tw


@pytest.mark.parametrize(
    "text,erwartet",
    [
        (
            "Ein Modell, das Vodafone prüfen könnte: KI-gestützte Mehrwertdienste "
            "könnten die Kundenbindung stärken.",
            "KI-gestützte Mehrwertdienste könnten die Kundenbindung stärken.",
        ),
        (
            "Telkomsel macht seine App zur Content-Plattform – ein Trend, den "
            "Vodafone in Europa beobachten sollte.",
            "Telkomsel macht seine App zur Content-Plattform.",
        ),
        (
            "Zeigt, wie Wettbewerber Sportrechte bündeln; Vodafone sollte prüfen, "
            "wo ähnliche Bundles wirken.",
            "Zeigt, wie Wettbewerber Sportrechte bündeln.",
        ),
        (
            "Ein Breitbandanbieter nutzt KI als Mehrwert. Vodafone könnte dieses "
            "Modell adaptieren.",
            "Ein Breitbandanbieter nutzt KI als Mehrwert.",
        ),
        (
            "Das ist eine Vorlage für Vodafone: Branchenweite Zusammenarbeit gegen "
            "Scams ist auch in Europa denkbar.",
            "Branchenweite Zusammenarbeit gegen Scams ist auch in Europa denkbar.",
        ),
        (
            "Zeigt, wie Telekomanbieter Premium-Sportinhalte nutzen – relevant als "
            "Vorlage für Vodafones eigene Content-Bundling-Strategie in Europa.",
            "Zeigt, wie Telekomanbieter Premium-Sportinhalte nutzen.",
        ),
        (
            "Zeigt die Zugkraft exklusiver Sportrechte. Wir sollten prüfen, ob "
            "eigene Investitionen den Bestand sichern.",
            "Zeigt die Zugkraft exklusiver Sportrechte.",
        ),
        ("Eigene Vodafone-Familie – das Mini-App-Modell nach Europa übertragen.", ""),
        ("Vodafone sollte prüfen, ob ein ähnliches Bundle den Mehrwert erhöht.", ""),
    ],
)
def test_ratschlaege_fallen_der_befund_bleibt(text, erwartet):
    assert tw.ohne_vodafone_rat(text) == erwartet


@pytest.mark.parametrize(
    "text",
    [
        "Vodafone-Afrika-Gesellschaften (Vodacom, Safaricom) könnten Marktanteile "
        "an Reisende verlieren, wenn MTN ein eSIM-Angebot platziert.",
        "Dies ist ein massiver Schlag gegen Vodafone im deutschen TV-Markt: "
        "Telekom nutzt die WM-Exklusivität als Turbo für Neukunden.",
        "Mehrere Streamingdienste gebündelt gratis – Vodafone bündelt bislang "
        "nur lose Add-ons.",
        "Vodafone hat keinen kostenlosen Premium-KI-Assistenten als Tarif-Bonus.",
        "Direkter Wettbewerber bindet Premium-KI ins Kundenportal – ein Pendant "
        "in MeinVodafone ist denkbar.",
        "Zeigt, wie Telekomanbieter Premium-Sportinhalte nutzen, um Kunden zu binden.",
    ],
)
def test_beobachtungen_bleiben_unveraendert(text):
    assert tw.ohne_vodafone_rat(text) == text


def test_ein_bruchstueck_wird_nicht_zum_satz_zusammengeklebt():
    """Der Gedankenstrich-Einschub im Ratschlag darf keinen Rest hinterlassen.

    Erste Fassung lieferte hier ". etwa über die Vodacom-Gruppe – schnell
    umsetzbar ist." - grammatisch Unsinn, und der Leser haette es der Quelle
    zugeschrieben."""
    text = (
        "MTN drängt nach Afrika. Vodafone sollte prüfen, ob ein eigenes "
        "Reise-eSIM-Produkt – etwa über die Vodacom-Gruppe – schnell "
        "umsetzbar ist."
    )
    assert tw.ohne_vodafone_rat(text) == "MTN drängt nach Afrika."


def test_ein_teilsatz_der_neu_anfaengt_wird_grossgeschrieben():
    text = (
        "Vorlage für Vodafone Cash: eine direkte PayPal-Integration "
        "würde Geldtransfers attraktiver machen."
    )
    assert tw.ohne_vodafone_rat(text) == (
        "Eine direkte PayPal-Integration würde Geldtransfers attraktiver machen."
    )


def test_abkuerzungen_zerlegen_den_satz_nicht():
    text = (
        "Rund 50 Mio. Kunden sind betroffen, z. B. in Indien. Vodafone "
        "sollte prüfen, ob das übertragbar ist."
    )
    assert tw.ohne_vodafone_rat(text) == (
        "Rund 50 Mio. Kunden sind betroffen, z. B. in Indien."
    )


def test_die_wettbewerbsseite_bleibt_strenger():
    """Dort verlangt der Prompt "the angle for Vodafone" im selben Satz - was
    hinter der Trennstelle steht, IST der Rat, auch ohne Verb. Die
    Differenzierungs-Karte darf denselben Satz behalten."""
    notiz = "DT testet Drohnen als Basisstationen; für Vodafone entsteht Druck."
    assert tw.ohne_vodafone_teil(notiz) == "DT testet Drohnen als Basisstationen."
    assert tw.ohne_vodafone_rat(notiz) == notiz


def test_saetze_trennt_nicht_an_abkuerzungen():
    assert tw.saetze("Rund 50 Mio. Kunden. Der zweite Satz.") == [
        "Rund 50 Mio. Kunden.",
        "Der zweite Satz.",
    ]


def test_leerer_text_bleibt_leer():
    assert tw.ohne_vodafone_rat("") == ""
    assert tw.ohne_vodafone_rat(None) == ""
