"""Der echte Abrufweg des Geraetezweigs: `(status, text)` ueber `collect.http.fetch`."""

from __future__ import annotations

from collections.abc import Callable


class Abruf(tuple):
    """`(status, text)` und, ob der Anbieter mit einer Schutzantwort geantwortet hat.

    Ein Tupel aus genau zwei Werten, damit `status, text = hole(...)` bleibt;
    `schutz` kommt als Attribut dazu (403, 406, 429, 503 mit Challenge)."""

    schutz: bool

    def __new__(cls, status: int, text: str, schutz: bool = False):
        """Zweiertupel `(status, text)` mit dem Merkmal `schutz`."""
        self = super().__new__(cls, (status, text))
        self.schutz = schutz
        return self


def hole_fabrik(http_cfg: dict) -> Callable:
    """`(status, text)` statt Response oder Ausnahme.

    Der Waechter muss 404 ("keine robots.txt, also keine Regeln") von 403 ("nicht
    anfassen") unterscheiden koennen. Ein Verbindungsfehler bleibt dagegen eine
    Ausnahme und wird oben als Fehler gewertet, nicht als Freibrief.

    DIESE FUNKTION HAT DAS BIS ZUM 28.08.2026 NICHT GEHALTEN, und ihre eigene Docstring
    behauptete das Gegenteil ("`fetch` wirft bei beidem nicht"). `collect.http.fetch`
    ruft `raise_for_status()` - es wirft bei JEDEM 4xx. Der Waechter bekam damit statt
    eines Status eine Ausnahme, und sein Ausnahmezweig sagt zu Recht "kein Ergebnis
    heisst nicht erlaubt": der Anbieter wurde als nicht abrufbar gefuehrt.

    Aufgefallen ist es nie, weil jeder bisher konfigurierte Host eine robots.txt mit
    HTTP 200 ausliefert. `api.vodafone.de` ist der erste ohne - dort antwortet 404, also
    "keine Regeln", und der ganze Anbieter fiel mit "404 Not Found" aus, obwohl die
    Schnittstelle einwandfrei antwortet. Ein Host ohne robots.txt ist der Normalfall im
    Web, nicht der Sonderfall.
    """
    from .collect.http import SchutzAntwort, StatusFehler, fetch

    def hole(
        url: str,
        kopfzeilen: dict | None = None,
        user_agent: str | None = None,
        einmalig: bool = False,
        vor_weiterleitung: Callable | None = None,
    ):
        """`einmalig=True`: ein Versuch, kein Backoff, kein Warten auf
        `Retry-After` (`fetch(schnell=True)`). Die Kennung wechselt `fetch`
        nie mehr.
        `vor_weiterleitung(ziel)` prueft jede Weiterleitung vor dem Sprung."""
        cfg = http_cfg if not user_agent else {**http_cfg, "user_agent": user_agent}
        try:
            antwort = fetch(
                url,
                cfg,
                extra_headers=kopfzeilen or None,
                schnell=einmalig,
                vor_weiterleitung=vor_weiterleitung,
            )
        except StatusFehler as exc:
            return Abruf(
                exc.response.status_code,
                exc.response.text,
                schutz=isinstance(exc, SchutzAntwort),
            )
        return Abruf(antwort.status_code, antwort.text)

    return hole
