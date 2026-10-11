"""Baut Foto und Masken der programmierten Campus-Szene (Antonio, 11.10.2026).

Die Startseite zeigt EIN Foto des Vodafone-Turms in der blauen Stunde. Himmel,
Tageszeit, Wetter und Jahreszeit rechnet der Browser darüber (``app.js``,
Abschnitt DER CAMPUS LEBT). Dafür braucht er neben dem Foto drei Masken in
einem PNG:

    R  Himmel   – wird durch den gerechneten Himmel ersetzt
    G  Lichter  – abends beleuchtete Fenster, Foyer und Laternen
    B  Laub     – Bäume und Hecken, die die Jahreszeit färbt

Das Skript läuft einmal von Hand, wenn das Foto getauscht wird; die Website
liest nur die fertigen Dateien. Es braucht ``opencv-python`` und ``numpy``,
die nicht zu den Laufzeitabhängigkeiten gehören.

    python scripts/campus_szene_bauen.py <foto.png>

Feste Stellen im Foto (Pixel bei 2400 px Breite): ``LOGO`` bleibt immer wie im
Foto; das ``LINKES_GEBAEUDE`` hat glatte Glasflächen, die wie Himmel aussehen;
Laub gibt es nur in den ``LAUB_RECHTECKE``n, außerhalb ist Grünstich Glas oder
Fassade; im ``HORIZONT_STREIFEN`` über den Bäumen rechts (x0, y0, x1, y1) ist
alles Helle Himmel, denn Laub ist dort dunkel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ZIEL_BREITE = 2400
VORLAGEN = Path(__file__).resolve().parents[1] / "src/telco_radar/report/templates/static"
FOTO = VORLAGEN / "bilder" / "campus-turm.jpg"
MASKE = VORLAGEN / "campus" / "campus-maske.png"
MASKE_KLEIN = VORLAGEN / "campus" / "campus-maske-1200.png"

LOGO = (1206, 252, 54)
LINKES_GEBAEUDE = [(0, 0), (15, 0), (350, 400), (460, 500), (556, 650), (528, 780),
                   (508, 840), (472, 905), (472, 1340), (0, 1340)]
LAUB_RECHTECKE = [((1760, 600), (2400, 1340)), ((0, 1120), (2400, 1340)), ((430, 980), (780, 1180))]
FOYER = ((770, 1020), (1690, 1185))
HORIZONT_STREIFEN = (1772, 690, 2400, 1012)


def _geleitet(bild: np.ndarray, p: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Kantenerhaltender Weichzeichner (Guided Filter) für weiche Maskenränder."""
    def box(x: np.ndarray) -> np.ndarray:
        return cv2.boxFilter(x, -1, (r, r))
    mi, mp = box(bild), box(p)
    a = (box(bild * p) - mi * mp) / (box(bild * bild) - mi * mi + eps)
    b = mp - a * mi
    return box(a) * bild + box(b)


def _himmelsmodell(lab: np.ndarray, sicher: np.ndarray) -> np.ndarray:
    """Glatter Farbverlauf des Himmels (Polynom über x, y), angepasst an sichere Himmelspixel."""
    h, w = lab.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    x, y = xx / w, yy / h
    f = np.stack([np.ones_like(x), x, y, x * x, x * y, y * y, x**3, x * x * y, x * y * y, y**3], -1)
    idx = np.flatnonzero(sicher.ravel())
    idx = np.random.default_rng(0).choice(idx, min(len(idx), 200_000), replace=False)
    a = f.reshape(-1, 10)[idx]
    kanaele = [f @ np.linalg.lstsq(a, lab[..., c].ravel()[idx], rcond=None)[0] for c in range(3)]
    return np.linalg.norm(lab - np.stack(kanaele, -1), axis=-1)


def _wachse(kern: np.ndarray, erlaubt: np.ndarray, schritte: int) -> np.ndarray:
    """Lässt eine Maske Pixel für Pixel in erlaubte Nachbarn wachsen."""
    maske = kern.copy()
    kreuz = np.ones((3, 3), np.uint8)
    for _ in range(schritte):
        neu = cv2.dilate(maske.astype(np.uint8), kreuz).astype(bool) & erlaubt & ~maske
        if not neu.any():
            break
        maske |= neu
    return maske


def himmel(bild: np.ndarray) -> np.ndarray:
    """Weiche Himmelsmaske 0..1; Antennen, Kanten und Bäume bleiben Vordergrund."""
    h, w = bild.shape[:2]
    lab = cv2.cvtColor((bild * 255).astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    hell = lab[..., 0]
    mu = cv2.blur(hell, (9, 9))
    streu = np.sqrt(np.maximum(cv2.blur(hell * hell, (9, 9)) - mu * mu, 0))
    y = np.mgrid[0:h, 0:w][0] / h
    blau, gruen, rot = bild[..., 0], bild[..., 1], bild[..., 2]
    sicher = (y < 0.45) & (streu < 2.0) & (blau > rot + 0.05) & (blau > gruen)
    for _ in range(4):
        rest = _himmelsmodell(lab, sicher)
        sicher = (rest < 9) & (streu < 3.0) & (y < 0.85)
    _, marke = cv2.connectedComponents(((rest < 11) & (streu < 4.5)).astype(np.uint8), connectivity=4)
    oben = set(np.unique(marke[:3, :])) - {0}
    kern = np.isin(marke, list(oben))
    lb, a, b = lab[..., 0] * 100 / 255, lab[..., 1] - 128, lab[..., 2] - 128
    glatt = cv2.GaussianBlur(lb, (0, 0), 1.0)
    kante = np.hypot(cv2.Sobel(glatt, cv2.CV_32F, 1, 0), cv2.Sobel(glatt, cv2.CV_32F, 0, 1))
    heiss = (rot > 0.85) & (gruen > 0.7)
    wolkig = ((b < -4) | (a > 6)) & (lb > 25) & (kante < 14) & ~heiss
    maske = _wachse(kern, wolkig, 400)
    xx = np.mgrid[0:h, 0:w][1]
    horizont = (lb > 50) & (kante < 12) & (y * h < 1010) & (xx > 1650)
    maske = _wachse(maske, horizont, 200)
    hell_rgb = 0.2126 * rot + 0.7152 * gruen + 0.0722 * blau
    streifen = (xx >= HORIZONT_STREIFEN[0]) & (xx < HORIZONT_STREIFEN[2])
    streifen &= (y * h >= HORIZONT_STREIFEN[1]) & (y * h < HORIZONT_STREIFEN[3])
    maske |= streifen & (hell_rgb > 0.30) & ~heiss
    m8 = maske.astype(np.uint8) * 255
    cv2.fillPoly(m8, [np.array(LINKES_GEBAEUDE, np.int32)], 0)
    grau = cv2.cvtColor(bild, cv2.COLOR_BGR2GRAY)
    return np.clip(_geleitet(grau, (m8 > 127).astype(np.float32), 4, 2e-4), 0, 1)


def lichter(bild: np.ndarray, himmel_m: np.ndarray) -> np.ndarray:
    """Warme, helle Pixel: beleuchtete Fenster, Foyer, Laternen und der Lichthof ums Logo."""
    blau, gruen, rot = bild[..., 0], bild[..., 1], bild[..., 2]
    hell = 0.2126 * rot + 0.7152 * gruen + 0.0722 * blau
    warm = rot - blau
    licht = np.clip((hell - 0.26) / 0.24, 0, 1) * np.clip((warm - 0.025) / 0.13, 0, 1)
    licht = np.maximum(licht, np.clip((hell - 0.80) / 0.12, 0, 1))
    licht[himmel_m > 0.5] = 0
    h, w = licht.shape
    yy, xx = np.mgrid[0:h, 0:w]
    abstand = np.hypot(xx - LOGO[0], yy - LOGO[1])
    licht[abstand < LOGO[2]] = 0
    ring = (abstand >= LOGO[2]) & (abstand < 100) & (warm > 0.05)
    licht[ring] = np.maximum(licht[ring], 0.85)
    return cv2.GaussianBlur(licht.astype(np.float32), (0, 0), 0.8)


def laub(bild: np.ndarray, himmel_m: np.ndarray, licht: np.ndarray) -> np.ndarray:
    """Grüne bis gelbe, gesättigte Pixel in den Laubbereichen."""
    hsv = cv2.cvtColor((bild * 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    ton, satt, wert = hsv[..., 0] * 2, hsv[..., 1] / 255, hsv[..., 2] / 255
    gruen = ((ton > 35) & (ton < 110) & (satt > 0.18) & (wert > 0.06) & (wert < 0.75)).astype(np.float32)
    gruen[(himmel_m > 0.5) | (licht > 0.3)] = 0
    bereich = np.zeros_like(gruen)
    for oben, unten in LAUB_RECHTECKE:
        cv2.rectangle(bereich, oben, unten, 1, -1)
    cv2.rectangle(bereich, FOYER[0], FOYER[1], 0, -1)
    gruen = cv2.morphologyEx(gruen * bereich, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return cv2.GaussianBlur(gruen, (0, 0), 1.2)


def entsaeumen(bild: np.ndarray, himmel_m: np.ndarray) -> np.ndarray:
    """Entfernt den alten Abendhimmel aus den Randpixeln, damit kein heller Saum bleibt."""
    def gefaltet(gewicht: np.ndarray, sigma: float) -> np.ndarray:
        zaehler = cv2.GaussianBlur(bild * gewicht[..., None], (0, 0), sigma)
        nenner = cv2.GaussianBlur(gewicht, (0, 0), sigma)[..., None]
        return zaehler / np.maximum(nenner, 1e-4)
    a = himmel_m[..., None]
    alt = gefaltet((himmel_m > 0.98).astype(np.float32), 12)
    verlaengert = gefaltet((himmel_m < 0.03).astype(np.float32), 2.5)
    vorne = np.clip((bild - a * alt) / np.maximum(1 - a, 1e-3), 0, 1)
    w = np.clip((a - 0.55) / 0.35, 0, 1)
    vorne = vorne * (1 - w) + verlaengert * w
    aus = bild.copy()
    rand = himmel_m > 0.01
    aus[rand] = vorne[rand]
    return aus


def main(quelle: Path) -> None:
    """Liest das Foto, schreibt Foto, Handyfassung und Masken in die Vorlagen."""
    roh = cv2.imread(str(quelle), cv2.IMREAD_COLOR)
    if roh is None:
        raise SystemExit(f"Foto nicht lesbar: {quelle}")
    hoehe = round(roh.shape[0] * ZIEL_BREITE / roh.shape[1])
    bild = cv2.resize(roh, (ZIEL_BREITE, hoehe), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    himmel_m = himmel(bild)
    licht = lichter(bild, himmel_m)
    gruen = laub(bild, himmel_m, licht)
    maske = (np.clip(np.dstack([gruen, licht, himmel_m]), 0, 1) * 255).astype(np.uint8)
    MASKE.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(MASKE), maske, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    klein = cv2.resize(maske, (1200, round(hoehe / 2)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(MASKE_KLEIN), klein, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    foto = (np.clip(entsaeumen(bild, himmel_m), 0, 1) * 255).astype(np.uint8)
    cv2.imwrite(str(FOTO), foto, [cv2.IMWRITE_JPEG_QUALITY, 86, cv2.IMWRITE_JPEG_PROGRESSIVE, 1])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from telco_radar.bild_vorschau import schreibe_kleine_fassung

    print(FOTO, schreibe_kleine_fassung(FOTO), MASKE, MASKE_KLEIN)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
