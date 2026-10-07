"""Parallellauf-Prüfung der Klick-Erkundung über die GitHub-API.

Die Erkundung ruft dieselben Hosts ab wie ``geraete.yml`` und ``radar.yml``. Zwei Läufe
zugleich hielten zusammen nur den halben Crawl-delay (CLAUDE.md Regel 4). Vor jeder
Seite fragt die Erkundung deshalb eine ``Laufpruefung``: ``None`` heißt frei, sonst
nennt sie den Grund, und der Anbieter ist ``verschoben``. ``GithubLaeufe`` fragt je
Workflow, ob ein Lauf ``queued`` oder ``in_progress`` ist, mit dem ``GITHUB_TOKEN`` des
Workflows (``actions: read``). Ist die API nicht erreichbar, antwortet sie nicht mit 200
oder ist die Antwort unlesbar, ist das ebenso ein Grund: nie still weiter. Das Token
steht in keiner Meldung. Die Erkundung weicht auch dem Klick-Tageslauf (``klick.yml``,
seit 07.10.2026 auf main) aus; der Tageslauf selbst fragt nach ``TAGESLAUF_WORKFLOWS``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .. import http

WORKFLOWS = {
    "geraete.yml": "Gerätelauf",
    "klick.yml": "Klick-Tageslauf",
    "radar.yml": "Radarlauf",
}
TAGESLAUF_WORKFLOWS = {
    "geraete.yml": "Gerätelauf",
    "klick-erkundung.yml": "Klick-Erkundung",
    "radar.yml": "Radarlauf",
}
ZUSTAENDE = ("queued", "in_progress")
API = "https://api.github.com"
API_FRIST_S = 15.0
GRUND_API = "GitHub-API nicht lesbar"
REPO_VARIABLE = "GITHUB_REPOSITORY"
TOKEN_VARIABLE = "GITHUB_TOKEN"
API_VARIABLE = "GITHUB_API_URL"
ANNAHME = "application/vnd.github+json"

Laufpruefung = Callable[[], str | None]
Holer = Callable[[str, dict[str, str]], tuple[int, str]]


def hole(url: str, kopf: dict[str, str]) -> tuple[int, str]:
    """Ein GET an die GitHub-API: Status und Text."""
    antwort = http.get(url, headers=kopf, timeout=API_FRIST_S)
    return antwort.status_code, antwort.text


@dataclass(frozen=True)
class GithubLaeufe:
    """Fragt, ob ein Lauf von ``workflows`` ansteht oder läuft; Grund oder ``None``."""

    repo: str
    token: str = field(repr=False)
    api: str = API
    holer: Holer = hole
    workflows: Mapping[str, str] = field(default_factory=lambda: WORKFLOWS)

    def __call__(self) -> str | None:
        """Grund, wenn ein Lauf ansteht oder läuft oder die API nicht lesbar ist."""
        kopf = {
            "Authorization": f"Bearer {self.token}",
            "Accept": ANNAHME,
            "User-Agent": http.BOT_UA,
        }
        for datei, name in self.workflows.items():
            for zustand in ZUSTAENDE:
                url = (
                    f"{self.api}/repos/{self.repo}/actions/workflows/{datei}/runs"
                    f"?status={zustand}&per_page=1"
                )
                grund = self._frage(url, kopf, datei)
                if isinstance(grund, str):
                    return grund
                if grund > 0:
                    return f"{name} läuft ({datei}, {zustand})"
        return None

    def _frage(self, url: str, kopf: dict[str, str], datei: str) -> int | str:
        """Zahl der Läufe oder der Grund, warum sie nicht lesbar ist."""
        try:
            status, text = self.holer(url, kopf)
        except http.HttpFehler as fehler:
            return f"{GRUND_API} ({datei}: {type(fehler).__name__})"
        if status != 200:
            return f"{GRUND_API} ({datei}: HTTP {status})"
        try:
            return int(json.loads(text)["total_count"])
        except (ValueError, KeyError, TypeError):
            return f"{GRUND_API} ({datei}: Antwort ohne total_count)"


def aus_umgebung(
    umgebung: Mapping[str, str], workflows: Mapping[str, str] = WORKFLOWS
) -> Laufpruefung:
    """Die Prüfung aus den Variablen des Workflows; fehlt eine, ist das der Grund."""
    repo = umgebung.get(REPO_VARIABLE, "")
    token = umgebung.get(TOKEN_VARIABLE, "")
    fehlt = [n for n, w in ((REPO_VARIABLE, repo), (TOKEN_VARIABLE, token)) if not w]
    if fehlt:
        grund = f"{GRUND_API} ({', '.join(fehlt)} fehlt)"
        return lambda: grund
    api = umgebung[API_VARIABLE] if umgebung.get(API_VARIABLE) else API
    return GithubLaeufe(repo, token, api, workflows=workflows)
