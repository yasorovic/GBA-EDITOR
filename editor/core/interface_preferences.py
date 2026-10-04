"""
core/interface_preferences.py — ce que l'interface MONTRE, réglé par machine.

Réglage du LOGICIEL, comme `core/toolchain.py` et `core/external_tools.py` :
un petit JSON dans le dossier de config utilisateur, jamais dans le projet.

**Pourquoi pas dans `ProjectSettings`.** L'affichage des astuces y a vécu un
temps, et deux choses l'ont sorti de là : `project.json` est versionné, donc
couper les astuces les coupait pour toute l'équipe — y compris pour celui qui
arrive et à qui elles s'adressent ; et un réglage de projet passe par
`SetFieldCmd`, donc **annuler une édition de scène pouvait rebasculer une
préférence de machine**. Un réglage d'application n'a rien à faire dans
l'historique d'un projet, et c'est le vrai argument des deux.

Portée actuelle : les astuces (le niveau 3 de `ui/common/notice.py`) et la
langue de l'interface (ROADMAP v0.11). Le fichier existe pour ce qui décrit
l'AFFICHAGE de l'éditeur — pas pour devenir le tiroir de tout ce qui n'a pas
trouvé de place ailleurs : un réglage qui décrit le JEU va dans
`ProjectSettings`, un chemin de machine dans `toolchain`/`external_tools`.
"""
from __future__ import annotations

import json

from core.toolchain import config_dir

CONFIG_FILE = config_dir() / "interface.json"

# Ce qu'une installation neuve montre. Les astuces sont VRAIES par défaut :
# elles s'adressent d'abord à qui découvre l'éditeur, et celui-là n'ira pas
# les allumer dans un écran de réglages qu'il ne connaît pas encore.
_DEFAULTS = {
    "show_tips": True,
    # "" est le catalogue maître. Une langue d'interface est propre à la
    # machine : elle ne dépend ni du jeu ouvert, ni de sa langue de jeu.
    "language": "",
    # "dark" ou "light". Comme la langue : propre à la machine, lu une fois au
    # démarrage (les couleurs sont figées dans les feuilles de style à la
    # construction des écrans), donc le changement prend effet au redémarrage.
    "theme": "dark",
    # Facteur d'échelle de toute l'interface, en pourcents. Lu avant la
    # création de la QApplication : le changement prend effet au redémarrage.
    "scale_percent": 100,
}

SCALE_CHOICES = (75, 100, 125, 150)

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Fichier absent au premier lancement, ou illisible : on repart des
            # défauts plutôt que d'empêcher l'éditeur de démarrer pour une
            # préférence d'affichage.
            _cache = {}
    return _cache


def _save():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(_load(), indent=2), encoding="utf-8")


def tips_shown() -> bool:
    """Les astuces (niveau 3) sont-elles affichées ?"""
    return bool(_load().get("show_tips", _DEFAULTS["show_tips"]))


def set_tips_shown(value: bool):
    _load()["show_tips"] = bool(value)
    _save()


def interface_language() -> str:
    """Code de langue choisi pour l'interface ("" = catalogue maître)."""
    value = _load().get("language", _DEFAULTS["language"])
    return value if isinstance(value, str) else _DEFAULTS["language"]


def interface_theme() -> str:
    """Thème de l'interface : "dark" (défaut) ou "light"."""
    value = _load().get("theme", _DEFAULTS["theme"])
    return value if value in ("dark", "light") else _DEFAULTS["theme"]


def set_interface_theme(mode: str):
    _load()["theme"] = "light" if mode == "light" else "dark"
    _save()


def interface_scale_percent() -> int:
    """Échelle de l'interface en pourcents (75, 100, 125 ou 150)."""
    value = _load().get("scale_percent", _DEFAULTS["scale_percent"])
    return value if value in SCALE_CHOICES else _DEFAULTS["scale_percent"]


def set_interface_scale_percent(percent: int):
    _load()["scale_percent"] = percent if percent in SCALE_CHOICES else _DEFAULTS["scale_percent"]
    _save()


def set_interface_language(code: str):
    """Persiste la langue de l'interface sans la mélanger au projet ouvert."""
    _load()["language"] = str(code or "")
    _save()
