"""
core/external_tools.py — chemins des logiciels tiers, réglage du LOGICIEL
(un chemin par machine, comme `core/toolchain.py`), pas du projet.

Portée actuelle : quatre chemins configurables depuis l'écran Réglages
(catégorie « External Tools »), pour l'image, le son, la police et le texte
(éditeur de fichiers `.json` & co). « text » sert au clic droit « Edit externally » de
l'onglet Disk (`window._edit_externally`) ; « image » aux boutons « Edit » des écrans
Sprite et Background (`ui/common/external_editor.py`). Un chemin vide s'ouvre dans
l'application par défaut du système. « audio » et « font » attendent leur câblage.
"""
from __future__ import annotations

import json
from core.resources.resource_store import read_config_json
from pathlib import Path

from core.app_paths import config_dir

CONFIG_FILE = config_dir() / "external_tools.json"

# (clé de config, libellé écran) — dans l'ordre d'affichage.
TOOL_KINDS: list[tuple[str, str]] = [
    ("image", "Image editor"),
    ("audio", "Audio editor"),
    ("font",  "Font editor"),
    ("text",  "Text editor"),
]


class ExternalTools:
    """Même forme que `Toolchain` : un petit JSON, chargé une fois, écrit à
    chaque changement."""

    def __init__(self):
        self._config: dict = self._load()

    def _load(self) -> dict:
        return read_config_json(CONFIG_FILE)

    def save(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self._config, indent=2), encoding="utf-8", newline="\n")

    def path(self, kind: str) -> Path | None:
        self._config = self._load()  # le fichier fait foi : un autre écran a pu écrire entre-temps
        if p := self._config.get(kind):
            return Path(p)
        return None

    def set_path(self, kind: str, path: Path | None):
        self._config = self._load()
        if path:
            self._config[kind] = str(path)
        else:
            self._config.pop(kind, None)
        self.save()
