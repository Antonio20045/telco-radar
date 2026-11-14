# Saturn/MediaMarkt Tarifwelt: drei Pflichtmodelle ohne lieferbare Variante (13.11.2026)

Lauf 43401542782 (13.11.2026) war unter anderem rot, weil Galaxy S26+, Galaxy A57
und Pixel 10a in ALLEN DREI Netzzeilen (Telekom, Vodafone, o2) ohne Bündel
dastanden. Gleich bei allen Netzen heißt nach CLAUDE.md Regel 11 zuerst
"Erfassungslücke" — deshalb am Original nachgemessen.

## Messung

Abruf am 13.11.2026 mit ehrlicher Kennung (`TelcoRadar/1.0`), ein GET je Modell,
nur die öffentliche Übersicht, kein Warenkorb, kein `/pks`, kein `/checkout`:

    https://tarife-api2.mediamarkt.de/v1/productdetail/galaxy-s26-plus
    https://tarife-api2.mediamarkt.de/v1/productdetail/galaxy-a57
    https://tarife-api2.mediamarkt.de/v1/productdetail/pixel-10a
    https://tarife-api2.mediamarkt.de/v1/productdetail/galaxy-s26      (Gegenprobe)

Alle vier antworten mit HTTP 200. `variantfilter-2026-11-13.json` enthält aus
jeder Antwort den Knoten `hardware.variantFilter` — Speicherstufe, Farbe und
`available`.

## Befund

| Modell | Stufen | lieferbare Varianten |
|---|---|---|
| Galaxy S26+ | 512 GB | **0 von 4** (alle `available: false`) |
| Galaxy A57 | 128 GB | **0 von 1** |
| Pixel 10a | 128 GB, 256 GB | **0 von 8** |
| Galaxy S26 (Gegenprobe) | 256 GB, 512 GB | 8 von 8 |

Ohne lieferbare Variante liefert die Tarifwelt keine Tarifliste: der Tageslauf
holt für diese drei Modelle gar keine Tarifabrufe mehr (im Lauf-Protokoll steht
je Modell nur der eine Übersichtsabruf). Es gibt also kein Bündel zu messen —
das ist eine echte Lücke, kein Adapter- oder Messfehler. Die Gegenprobe Galaxy
S26 zeigt, dass der Leser auf derselben Nutzlastform einwandfrei liest.

Weil die Quelle hier "nicht lieferbar" sagt und NICHT "nicht im Sortiment",
stehen die Einträge in `config/geraete_abdeckung.yaml` bewusst OHNE
`art: nicht_im_portfolio`: die Portfolio-Ansicht zeigt sie als Messlücke, nicht
als Sortimentsaussage. Kommt eine Variante zurück, warnt der Wächter "überholt".
