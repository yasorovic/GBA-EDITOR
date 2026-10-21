"""
core/update_check.py — « existe-t-il une version plus récente que celle-ci ? »

Interroge la dernière release publiée du dépôt (`APP_RELEASES_URL`, prérelease
comprises : tant que le produit est en alpha, toutes le sont) et la compare à
`APP_VERSION`. Ne télécharge ni n'installe rien : le résultat porte la page de la
release, que l'appelant ouvre.

Ordre des versions : `X.Y.Z` numérique, puis l'étiquette `alpha < beta < stable`
(cf. `app_info`). Un tag qui ne suit pas cette forme lève `ValueError` plutôt que
d'être deviné.

Bloquant (réseau) : à lancer hors du fil de l'interface.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from core.app_info import APP_NAME, APP_RELEASES_URL, APP_VERSION

_LABEL_RANK = {"alpha": 0, "beta": 1, "stable": 2}


@dataclass(frozen=True)
class LatestRelease:
    version: str    # sans le « v » du tag
    notes: str      # corps Markdown de la release
    page_url: str
    is_newer: bool
    major: bool = False   # `update.json` de la release : mérite une pop-up au lancement
    assets: tuple = ()    # ((nom, adresse de téléchargement), …) des fichiers de la release


CHECK_INTERVAL_SECONDS = 24 * 3600

# Fréquence de la vérification automatique : identifiant -> délai minimal entre deux
# vérifications (en secondes) ; `None` = jamais. Les identifiants sont ceux des réglages.
CHECK_FREQUENCIES = {
    "startup": 0,
    "daily": CHECK_INTERVAL_SECONDS,
    "weekly": 7 * CHECK_INTERVAL_SECONDS,
    "never": None,
}
DEFAULT_CHECK_FREQUENCY = "daily"


def is_due(last_check: float, now: float, frequency: str = DEFAULT_CHECK_FREQUENCY) -> bool:
    """Vrai si la dernière vérification date d'au moins le délai de `frequency` (ou n'a
    jamais eu lieu : 0). `never` n'est jamais dû."""
    interval = CHECK_FREQUENCIES[frequency]
    return interval is not None and now - last_check >= interval


def version_key(version: str) -> tuple:
    """`0.1.0-alpha` → (0, 1, 0, 0), comparable ; `ValueError` si la forme diffère."""
    numbers, _, label = version.removeprefix("v").partition("-")
    parts = numbers.split(".")
    if len(parts) != 3 or label not in _LABEL_RANK:
        raise ValueError(f"Unrecognised version '{version}'.")
    return (*(int(p) for p in parts), _LABEL_RANK[label])


def parse_importance(info: dict) -> bool:
    """Le contenu de `update.json` → « version importante ? ». `ValueError` si la forme diffère.

    `{"importance": "normal" | "major", "reasons": [...]}` ; une version importante
    dit POURQUOI (`feature`, `migration`, `api`), pour qu'on n'en publie pas une sans y penser."""
    importance, reasons = info.get("importance"), info.get("reasons", [])
    if importance not in ("normal", "major"):
        raise ValueError(f"Unknown importance '{importance}'.")
    if not isinstance(reasons, list) or not set(reasons) <= {"feature", "migration", "api"}:
        raise ValueError("'reasons' must be a list of feature, migration or api.")
    if importance == "major" and not reasons:
        raise ValueError("A major release must say why (reasons).")
    return importance == "major"


def _read_major(release: dict) -> bool:
    """`update.json` joint à la release ; absent ou illisible, la version est ordinaire."""
    for asset in release.get("assets", ()):
        if asset.get("name") == "update.json":
            try:
                with urllib.request.urlopen(asset["browser_download_url"], timeout=10) as response:
                    return parse_importance(json.load(response))
            except Exception:
                return False
    return False


def fetch_latest_release() -> LatestRelease:
    """Lève une exception (réseau, tag inconnu) — à l'appelant de l'afficher."""
    if not APP_RELEASES_URL:
        raise RuntimeError("No release source is configured.")
    api = APP_RELEASES_URL.replace("https://github.com/", "https://api.github.com/repos/")
    request = urllib.request.Request(
        f"{api}?per_page=1", headers={"Accept": "application/vnd.github+json",
                 "User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        releases = json.load(response)
    if not releases:  # rien de publié : rien de plus récent
        return LatestRelease(APP_VERSION, "", APP_RELEASES_URL, False)
    latest = releases[0]
    version = latest["tag_name"].removeprefix("v")
    is_newer = version_key(version) > version_key(APP_VERSION)
    return LatestRelease(
        version=version,
        notes=latest.get("body") or "",
        page_url=latest["html_url"],
        is_newer=is_newer,
        major=is_newer and _read_major(latest),
        assets=tuple((a["name"], a["browser_download_url"]) for a in latest.get("assets", ())),
    )
